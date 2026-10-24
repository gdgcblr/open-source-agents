"""Hosted entry point. Demo is explicit; real events require persistent storage."""
import os
from urllib.parse import urlsplit
import uvicorn
from app import create_app

if __name__ == "__main__":
    public_url = os.getenv("BUILDBUDDY_PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL", "")
    if public_url:
        parsed = urlsplit(public_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise SystemExit("Public hosting requires an HTTPS BUILDBUDDY_PUBLIC_URL.")
        os.environ["BUILDBUDDY_PUBLIC_URL"] = public_url.rstrip("/")
        os.environ.setdefault("BUILDBUDDY_ALLOWED_HOSTS", f"localhost,127.0.0.1,{parsed.hostname}")
    app = create_app(demo=os.getenv("BUILDBUDDY_DEMO", "false").lower() == "true")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")), access_log=False)
