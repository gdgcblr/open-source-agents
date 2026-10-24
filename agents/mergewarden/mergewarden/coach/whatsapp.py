"""Twilio WhatsApp adapter without the Twilio SDK.

Inbound:  POST /twilio/webhook (form: From, Body, NumMedia, MediaUrl0, MediaContentType0)
          -> X-Twilio-Signature checked (HMAC-SHA1 over URL + sorted params, base64)
          -> media downloaded with basic auth (size-capped)
          -> service.handle_message
Outbound: the reply as TwiML <Response><Message>. If the coach needs longer than
          Twilio's webhook timeout, we answer with an empty TwiML and send the
          reply through the Messages REST API when it is ready.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
from typing import Awaitable, Callable
from xml.sax.saxutils import escape

import httpx

from . import config

log = logging.getLogger(__name__)
INLINE_TIMEOUT_S = 11  # Twilio gives up on a webhook after ~15 s
MAX_MESSAGE = 1500  # WhatsApp via Twilio: 1600 chars per message


def valid_signature(auth_token: str, url: str, params: dict[str, str], signature: str) -> bool:
    """Twilio's request signature: base64(HMAC-SHA1(token, url + k1 + v1 + k2 + v2 ...)), keys sorted."""
    if not auth_token or not signature:
        return False
    data = url + "".join(k + params[k] for k in sorted(params))
    expected = base64.b64encode(hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, signature)


def twiml(text: str | None, media_urls: list[str] | None = None) -> str:
    if not text:
        return '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    media = "".join(f"<Media>{escape(u)}</Media>" for u in (media_urls or [])[:1])
    return (f'<?xml version="1.0" encoding="UTF-8"?><Response><Message><Body>{escape(text[:MAX_MESSAGE])}</Body>'
            f"{media}</Message></Response>")


async def download_media(url: str) -> tuple[bytes, str] | None:
    """Fetch a Twilio media URL (basic auth), refusing anything over the audio cap."""
    if not url.startswith("https://api.twilio.com/") and not url.startswith("https://media.twiliocdn.com/"):
        log.warning("refusing media from unexpected host")
        return None
    auth = (config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        async with client.stream("GET", url, auth=auth) as r:
            if r.status_code != 200:
                return None
            mime = r.headers.get("content-type", "").split(";")[0]
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                buf += chunk
                if len(buf) > config.MAX_AUDIO_BYTES:
                    return b"x" * (config.MAX_AUDIO_BYTES + 1), mime  # let the guardrail explain the limit
            return bytes(buf), mime


async def send_message(to: str, text: str) -> None:
    """Send an outbound WhatsApp message through the Twilio REST API (split if long)."""
    if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and config.TWILIO_WHATSAPP_FROM):
        log.error("cannot send async reply: TWILIO_ACCOUNT_SID / TWILIO_WHATSAPP_FROM not set")
        return
    url = f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Messages.json"
    chunks = [text[i:i + MAX_MESSAGE] for i in range(0, len(text), MAX_MESSAGE)] or [""]
    async with httpx.AsyncClient(timeout=20) as client:
        for chunk in chunks:
            r = await client.post(url, auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
                                  data={"From": config.TWILIO_WHATSAPP_FROM, "To": to, "Body": chunk})
            if r.status_code >= 300:
                log.error("twilio send failed: %s", r.status_code)


async def handle_webhook(params: dict[str, str], respond: Callable[..., Awaitable]) -> str:
    """Turn a verified Twilio webhook into TwiML. `respond(user_id, text, audio, mime)` runs the coach."""
    sender = params.get("From", "")
    body = params.get("Body", "")
    audio = mime = None
    if int(params.get("NumMedia", "0") or 0) > 0 and params.get("MediaUrl0"):
        ctype = params.get("MediaContentType0", "")
        if not ctype.startswith("audio/"):
            return twiml("📎 I can read text and listen to voice notes, but not images or files yet.")
        got = await download_media(params["MediaUrl0"])
        if not got:
            return twiml("🎙️ I couldn't download that voice note. Could you try again?")
        audio, mime = got[0], got[1] or ctype

    task = asyncio.ensure_future(respond(sender, body, audio, mime))
    try:
        text = await asyncio.wait_for(asyncio.shield(task), timeout=INLINE_TIMEOUT_S)
        return twiml(text)
    except asyncio.TimeoutError:
        async def later():
            await send_message(sender, await task)
        asyncio.ensure_future(later())
        return twiml(None)
