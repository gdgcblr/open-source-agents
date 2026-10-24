"""Sample FastAPI application for the RunReady demo.

The ASGI application object lives here as ``src.api:app``. The deployment
configuration (see ``app.yaml`` / ``Procfile``) deliberately references the
WRONG module path, which is the deployment-readiness bug RunReady diagnoses.
"""

from fastapi import FastAPI

app = FastAPI(title="runready-sample")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"health": "ok"}
