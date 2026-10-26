from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer


# Simple RAG (Retrieval-Augmented Generation) class for research paper context retrieval
class SimplePaperRAG:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        # Runs on CPU with ~120MB RAM footprint
        self.encoder = SentenceTransformer(model_name, device="cpu")
        self.chunks: List[str] = []
        self.embeddings: np.ndarray = None

    def chunk_document(self, text: str, chunk_size: int = 1200, overlap: int = 200) -> List[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start += (chunk_size - overlap)
        return chunks

    def index(self, raw_text: str):
        self.chunks = self.chunk_document(raw_text)
        self.embeddings = self.encoder.encode(
            self.chunks,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False
        )

    def retrieve(self, queries: List[str], top_k: int = 3) -> str:
        """Retrieves top-k relevant context chunks across target aspects."""
        selected_indices = set()
        for q in queries:
            q_emb = self.encoder.encode(q, convert_to_numpy=True, normalize_embeddings=True)
            scores = np.dot(self.embeddings, q_emb)
            top_idx = np.argsort(scores)[::-1][:top_k]
            selected_indices.update(top_idx)

        # Merge retrieved chunks in chronological document order
        sorted_indices = sorted(list(selected_indices))
        return "\n\n---\n\n".join([self.chunks[i] for i in sorted_indices])