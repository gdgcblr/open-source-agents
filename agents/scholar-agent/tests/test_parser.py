"""
tests/test_parser.py - Unit tests for document ingestion bounds
"""
import pytest
from parser import load_document

def test_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_document("non_existent_research_paper.pdf")

def test_parses_plain_text(tmp_path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("Abstract: We propose an in-memory RAG pipeline.", encoding="utf-8")
    
    extracted = load_document(str(test_file))
    assert "in-memory RAG pipeline" in extracted