import os
import io
import httpx
from pypdf import PdfReader

def load_document(source: str) -> str:
    """Fetches document text from an arXiv URL, web link, or local PDF/TXT file."""
    if source.startswith("http://") or source.startswith("https://"):
        if "arxiv.org/abs/" in source:
            source = source.replace("arxiv.org/abs/", "arxiv.org/pdf/") + ".pdf"

        headers = {"User-Agent": "ScholarAgent/1.0"}
        with httpx.Client(timeout=45.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(source)
            resp.raise_for_status()
            
            if "application/pdf" in resp.headers.get("content-type", "") or source.endswith(".pdf"):
                reader = PdfReader(io.BytesIO(resp.content))
                return "\n".join([page.extract_text() or "" for page in reader.pages]).strip()
            return resp.text

    if not os.path.exists(source):
        raise FileNotFoundError(f"Source file not found: {source}")

    if source.lower().endswith(".pdf"):
        reader = PdfReader(source)
        return "\n".join([page.extract_text() or "" for page in reader.pages]).strip()

    with open(source, "r", encoding="utf-8", errors="ignore") as f:
        return f.read().strip()