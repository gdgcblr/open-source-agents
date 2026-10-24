"""
rag_tool.py - In-memory Vector RAG indexing exposed as ADK Tools
"""
import io
import os
import re
import unicodedata
from typing import List, Optional
import httpx
import numpy as np
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

# Global state singleton for the active paper in memory
class PaperIndexState:
    def __init__(self):
        self.chunks: List[str] = []
        self.embeddings: Optional[np.ndarray] = None
        self.encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
        self.paper_title: str = "Unknown"

paper_state = PaperIndexState()

# To sanitize text and prevent prompt injection attacks
def sanitize_text(text: str) -> str:
    """Strips zero-width characters and prompt injections."""
    norm = unicodedata.normalize("NFKC", text)
    patterns = [
        r"ignore\s+previous\s+instructions",
        r"system\s*prompt",
        r"you\s+are\s+now\s+an\s+assistant\s+that",
    ]
    for p in patterns:
        norm = re.sub(p, "[REDACTED_INJECTION]", norm, flags=re.IGNORECASE)
    return norm.strip()

# To load and index a document (PDF/TXT) into in-memory vector store
def load_and_index_document(source: str) -> str:
    """Ingests PDF/TXT, builds in-memory vector index, returns status."""
    raw_text = ""
    if source.startswith("http://") or source.startswith("https://"):
        if "arxiv.org/abs/" in source:
            source = source.replace("arxiv.org/abs/", "arxiv.org/pdf/") + ".pdf"
        headers = {"User-Agent": "ScholarADK/1.0"}
        with httpx.Client(timeout=45.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(source)
            resp.raise_for_status()
            if "application/pdf" in resp.headers.get("content-type", "") or source.endswith(".pdf"):
                reader = PdfReader(io.BytesIO(resp.content))
                raw_text = "\n".join([page.extract_text() or "" for page in reader.pages])
            else:
                raw_text = resp.text
    else:
        if not os.path.exists(source):
            return f"Error: File not found at {source}"
        if source.lower().endswith(".pdf"):
            reader = PdfReader(source)
            raw_text = "\n".join([page.extract_text() or "" for page in reader.pages])
        else:
            with open(source, "r", encoding="utf-8", errors="ignore") as f:
                raw_text = f.read()

    cleaned = sanitize_text(raw_text)
    
    # Chunking: 1200 characters with 200 overlap
    chunk_size = 1200
    overlap = 200
    chunks = []
    start = 0
    while start < len(cleaned):
        chunks.append(cleaned[start:start + chunk_size])
        start += (chunk_size - overlap)
    
    paper_state.chunks = chunks
    paper_state.embeddings = paper_state.encoder.encode(
        chunks,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False
    )
    return f"Indexed {len(chunks)} context passages from {source}."

# --- ADK Tool Functions ---

# To search relevant passages from the ingested research paper using semantic similarity
def search_paper_context(query: str, top_k: int = 3) -> str:
    """
    Search relevant passages from the ingested research paper using semantic similarity.
    Args:
        query: Specific topical inquiry (e.g. 'architecture flowchart', 'experimental benchmark table').
        top_k: Number of relevant chunks to retrieve (default 3).
    """
    if paper_state.embeddings is None or len(paper_state.chunks) == 0:
        return "No paper currently indexed. Ingest a paper first."
    
    q_vec = paper_state.encoder.encode(query, convert_to_numpy=True, normalize_embeddings=True)
    scores = np.dot(paper_state.embeddings, q_vec)
    best_indices = np.argsort(scores)[::-1][:top_k]
    
    retrieved = [paper_state.chunks[i] for i in best_indices]
    return "\n\n---\n\n".join(retrieved)