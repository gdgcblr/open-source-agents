"""Runtime builders for fake secrets. Nothing realistic is ever written as a literal in the repo."""

import json

import httpx


def aws() -> str:
    return "AKIA" + "7QXM2KD9" + "TLVP4WNB"


def github() -> str:
    return "gh" + "p_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"


def stripe() -> str:
    return "sk_" + "live_" + "51H" + "x9Qz7LmN2vB4kT8wYpR3aS6dF1gH"


def google() -> str:
    return "AI" + "za" + ("SyD-9tYz1q8LmN2vB4kT8wYpR3aS6dF1gH0jK5x"[:35])


def slack() -> str:
    return "xo" + "xb-" + "1234567890-0987654321-" + "AbCdEfGhIjKlMnOpQrStUvWx"


def pem_header() -> str:
    return "-----BEGIN " + "RSA PRIVATE KEY-----"


PEM_BODY = "MIIEowIBAAKCAQEA" + "7vQz9LmN2vB4kT8wYpR3aS6dF1gH0jK5xC" + "uZ8eW1nM4qR7tY"


def password() -> str:
    return "Zk9" + "-vR4t!" + "Qm27xLp"


def db_url() -> str:
    return "postgres" + "ql://svc_app:" + "Vq83" + "nKd02Lx" + "@db.internal.example.com:5432/prod"


def make_ollama_transport(replies, captured=None, tags=("gemma4:e2b-it-q4_K_M",)):
    """MockTransport: /api/tags lists `tags`; /api/chat pops from `replies` (str or dict)."""
    replies = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": t} for t in tags]})
        body = json.loads(request.content)
        if captured is not None:
            captured.append(body)
        r = replies.pop(0) if len(replies) > 1 else replies[0]
        content = r if isinstance(r, str) else json.dumps(r)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})

    return httpx.MockTransport(handler)


def verdict(v="real", conf=0.9, reason="r", rem="rotate"):
    return {"verdict": v, "confidence": conf, "reason": reason, "remediation": rem}
