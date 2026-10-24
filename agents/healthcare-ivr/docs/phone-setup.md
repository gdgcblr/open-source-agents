# Answering real phone calls

The receptionist answers calls that reach a Twilio phone number. You need a Twilio account with at least one voice-capable number, and a public HTTPS URL for the backend.

## Connect a Twilio number

1. Set `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` in `.env` (Twilio Console → Account info).
2. Start the app with `make dev`. In a second terminal, run `make tunnel` and copy the `https://…` forwarding URL ngrok prints.
3. Set `PUBLIC_BASE_URL` in `.env` to that URL, without a trailing slash, and restart `make dev`.
4. In the Twilio Console, open **Phone Numbers → Manage → Active numbers**. For **each number** the receptionist should answer, set **Voice Configuration → A call comes in** to **Webhook**, `https://<your-tunnel>/api/twilio/voice`, **HTTP POST**. The URL must match `PUBLIC_BASE_URL` exactly, or the signature check rejects Twilio's requests.
5. Call the number and watch the call live on the dashboard's **Calls** page.

The free ngrok plan gives you a new URL each time you restart it; update `PUBLIC_BASE_URL` and the Twilio webhook when it changes.

## Several numbers

Any number of Twilio numbers can point at the same webhook. Each call stores the number that was dialled (`called_number`), so you can tell the lines apart.

## Using numbers you already have

- **Forward them**: set unconditional, busy or no-answer forwarding with your carrier, to a Twilio number connected as above. This is the quickest option and works for mobiles.
- **Port them to Twilio**: a longer process, after which you connect them directly.
- **Connect a hospital PBX over SIP trunking**: possible, but it needs a different integration from the webhook used here.

## What Twilio receives (genuine run against a local backend)

```
$ curl -X POST https://example.ngrok-free.app/api/twilio/voice \
    -H "X-Twilio-Signature: <signature>" \
    -d CallSid=CA1234567890abcdef1234567890abcdef -d From=+15550100
```
```xml
<?xml version="1.0" ?>
<Response>
  <Connect>
    <Stream url="wss://example.ngrok-free.app/api/twilio/media-stream">
      <Parameter name="token" value="353da0f34293f2bd21b29cf118917b2eb387d6f3608303b0749d2c85459cf289"/>
    </Stream>
  </Connect>
  <Say>Sorry, our assistant is unavailable right now. Please try again later. Goodbye.</Say>
</Response>
```

The same request without a valid signature is rejected with `403 {"detail":"Invalid Twilio signature"}`. The `<Say>` only plays if the stream ends while the caller is still on the line, for example when Deepgram can't be reached.

## Recording consent

Calls are recorded (`RECORD_CALLS=true`) so they can be transcribed by speaker afterwards. The default greeting says the call may be recorded; keep that sentence if you set your own `AGENT_GREETING`, check the rules where you operate, or set `RECORD_CALLS=false`.
