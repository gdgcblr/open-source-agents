"""Aran MCP server: lets any agent read documents only through the privacy gateway.

Security model:
- Documents are exposed as opaque ids (doc_1, doc_2, ...) because filenames often contain names.
- Only files inside ARAN_DOCS_DIR are reachable; the model cannot pass arbitrary paths.
- The session (token vault) is chosen by the host process via ARAN_SESSION_ID, not by the model.
- There is deliberately NO restore tool: real values must never flow back into model context.
  The host restores the final answer locally with `aran.restore(text, session_id)`.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from aran import audit, engine, profiles, readers
from aran.vault import new_session_id

mcp = MCPServer(
    "aran",
    instructions=(
        "Aran is a privacy gateway. Read documents only via redact_document. Values like "
        "<PERSON_1> or <PAN_1> are stable placeholders for hidden personal data: the same "
        "token in two documents means the same real value. Never ask for or guess real values."
    ),
)

SESSION_ID = os.environ.get("ARAN_SESSION_ID") or new_session_id()


def _docs_dir() -> Path:
    return Path(os.environ.get("ARAN_DOCS_DIR", ".")).resolve()


def _catalogue() -> dict[str, Path]:
    root = _docs_dir()
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in readers.SUPPORTED)
    return {f"doc_{i}": p for i, p in enumerate(files, 1)}


_KIND_BY_EXT = {
    **{e: "image (scan/photo)" for e in readers.IMAGE_EXT},
    **{e: "table" for e in readers.TABLE_EXT},
    **{e: "pdf" for e in readers.PDF_EXT},
    **{e: "text" for e in readers.TEXT_EXT},
}


@mcp.tool()
def list_documents() -> list[dict]:
    """List the documents available for this case. Returns opaque ids and file kinds only."""
    return [
        {"doc_id": doc_id, "kind": _KIND_BY_EXT[p.suffix.lower()], "size_kb": round(p.stat().st_size / 1024, 1)}
        for doc_id, p in _catalogue().items()
    ]


@mcp.tool()
def redact_document(doc_id: str, profile: str = "kyc") -> dict:
    """Read a document with all personal data replaced by stable tokens like <PERSON_1>.

    Args:
        doc_id: An id from list_documents, e.g. "doc_1".
        profile: "kyc" (fintech/loans) or "health" (medical). Decides what is hidden.
    """
    if profile not in profiles.available():
        return {"error": f"Unknown profile {profile!r}. Use one of {profiles.available()}."}
    path = _catalogue().get(doc_id)
    if path is None:
        return {"error": f"Unknown doc_id {doc_id!r}. Call list_documents first."}
    result = engine.redact_document(path, profile, SESSION_ID, channel="mcp")
    return {
        "doc_id": doc_id,
        "kind": result.kind,
        "profile": result.profile,
        "text": result.redacted,
        "hidden": result.counts["masked"],
        "generalised": result.counts["generalised"],
    }


@mcp.tool()
def privacy_summary() -> dict:
    """How much personal data Aran has hidden in this session (counts only, no values)."""
    return audit.summarise(audit.read(SESSION_ID))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
