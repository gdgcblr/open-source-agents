"""Small local web demo for the PDF-to-SurveyJS agent."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import warnings
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

from pdf_to_surveyjs_agent.workflow import (
    ConfigurationError,
    ConversionError,
    convert_pdf,
)

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DIST = PROJECT_ROOT / "web" / "dist"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def create_app() -> Flask:
    load_dotenv(PROJECT_ROOT / ".env")
    app = Flask(__name__, static_folder=str(WEB_DIST), static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

    logging.getLogger("google.adk.workflow._node_runner").setLevel(logging.CRITICAL)
    logging.getLogger("google.adk.runners").setLevel(logging.CRITICAL)
    warnings.filterwarnings(
        "ignore",
        message=r"\[EXPERIMENTAL\] feature FeatureName\.JSON_SCHEMA_FOR_FUNC_DECL.*",
    )

    @app.post("/api/convert")
    def convert() -> tuple[object, int] | object:
        uploaded = request.files.get("pdf")
        if uploaded is None or not uploaded.filename:
            return jsonify(error="Choose a PDF file first."), 400
        if Path(uploaded.filename).suffix.lower() != ".pdf":
            return jsonify(error="Only PDF files are supported."), 400

        filename = secure_filename(uploaded.filename) or "upload.pdf"
        try:
            raw_retries = request.form.get("maxRetries")
            max_retries = int(raw_retries) if raw_retries is not None and raw_retries != "0" else 1
        except ValueError:
            return jsonify(error="maxRetries must be an integer."), 400

        try:
            with tempfile.TemporaryDirectory(prefix="pdf-survey-") as temp_dir:
                pdf_path = Path(temp_dir) / filename
                uploaded.save(pdf_path)
                result = asyncio.run(convert_pdf(pdf_path, max_retries=max_retries))
        except (ConfigurationError, ConversionError, ValueError) as exc:
            return jsonify(error=str(exc)), 422

        return jsonify(result.to_dict())

    @app.errorhandler(413)
    def upload_too_large(_error: object) -> tuple[object, int]:
        return jsonify(error="PDF exceeds the 15 MB upload limit."), 413

    @app.get("/")
    def index() -> object:
        if not (WEB_DIST / "index.html").exists():
            return (
                "Frontend has not been built. Run: cd web && npm install && npm run build",
                503,
            )
        return send_from_directory(WEB_DIST, "index.html")

    @app.get("/<path:path>")
    def assets(path: str) -> object:
        return send_from_directory(WEB_DIST, path)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
