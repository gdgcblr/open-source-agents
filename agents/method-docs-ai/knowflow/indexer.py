import json
import math
import re
from collections import Counter

from knowflow.config import settings
from knowflow.documents import discover_documents, read_document, chunk_text

INDEX_FILE = "index.json"
_TOKEN_RE = re.compile(r"[a-z0-9_+#.-]+", re.IGNORECASE)
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "for", "from", "how",
    "i", "in", "is", "it", "of", "on", "or", "the", "to", "what", "when",
    "where", "which", "who", "why", "with", "you", "your",
}


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text) if len(t) > 1 and t.lower() not in _STOP_WORDS]


def index_exists() -> bool:
    path = settings.index_dir / INDEX_FILE
    return path.exists() and path.stat().st_size > 2


def build_index() -> int:
    files = discover_documents(settings.knowledge_dir)
    if not files:
        raise RuntimeError(
            f"No supported documents found in '{settings.knowledge_dir}'. Add .txt, .md, .pdf, or .docx files."
        )

    records = []
    for path in files:
        text = read_document(path)
        for chunk_id, chunk in enumerate(
            chunk_text(text, settings.chunk_size, settings.chunk_overlap), start=1
        ):
            records.append({
                "file": str(path.relative_to(settings.knowledge_dir)),
                "chunk_id": chunk_id,
                "text": chunk,
                "tokens": tokenize(chunk),
            })

    if not records:
        raise RuntimeError("Documents were found, but no extractable text was available.")

    settings.index_dir.mkdir(parents=True, exist_ok=True)
    tmp = settings.index_dir / (INDEX_FILE + ".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    tmp.replace(settings.index_dir / INDEX_FILE)
    return len(records)


def load_index() -> list[dict]:
    path = settings.index_dir / INDEX_FILE
    if not path.exists():
        raise RuntimeError("Index does not exist. Build the index first.")
    return json.loads(path.read_text(encoding="utf-8"))


def lexical_score(query_tokens: list[str], document_tokens: list[str]) -> float:
    """Small dependency-free TF-IDF-style cosine score for local retrieval."""
    if not query_tokens or not document_tokens:
        return 0.0
    q_counts = Counter(query_tokens)
    d_counts = Counter(document_tokens)
    vocabulary = set(q_counts) | set(d_counts)
    q_norm = math.sqrt(sum(v * v for v in q_counts.values()))
    d_norm = math.sqrt(sum(v * v for v in d_counts.values()))
    if not q_norm or not d_norm:
        return 0.0
    dot = sum(q_counts[token] * d_counts[token] for token in vocabulary)
    return dot / (q_norm * d_norm)


def search(question: str, top_k: int | None = None) -> list[dict]:
    query_tokens = tokenize(question)
    scored = []
    for record in load_index():
        score = lexical_score(query_tokens, record.get("tokens") or tokenize(record["text"]))
        scored.append({**record, "score": score})
    scored.sort(key=lambda item: item["score"], reverse=True)
    k = top_k or settings.top_k
    return [
        {key: value for key, value in item.items() if key != "tokens"}
        for item in scored[:k]
    ]
