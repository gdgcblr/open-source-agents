# Architecture

## Overview

Method Documents AI Agent uses a local ingestion and retrieval pipeline
with Gemini for answer generation. It is intentionally a small MVP
rather than a production document-management integration.

## Request flow

1.  The user asks a question through Streamlit or the CLI.
2.  The retrieval layer loads the generated local JSON index.
3.  The question is tokenized and compared with indexed passage tokens
    using a lightweight cosine-similarity calculation.
4.  The top-ranked passages below the configured relevance threshold are
    filtered out.
5.  If no passages remain, the agent returns a message saying the
    indexed documentation did not provide sufficient evidence.
6.  Otherwise, the question and selected passages are sent to Gemini
    with instructions to answer from evidence and cite source markers.
7.  The UI displays the answer and the source filename, passage number,
    score, and passage text.

## Components

  -----------------------------------------------------------------------
  Component                           Responsibility
  ----------------------------------- -----------------------------------
  `app.py`                            Streamlit user interface, index
                                      refresh action, question input,
                                      answer and source display

  `knowflow/documents.py`             Discover and extract supported file
                                      formats; split text into chunks

  `knowflow/indexer.py`               Tokenization, local index creation,
                                      lexical scoring, and retrieval

  `knowflow/agent.py`                 Filter retrieval results, build
                                      evidence prompt, and return
                                      answer/source metadata

  `knowflow/gemini_client.py`         Call the Gemini API and wrap API
                                      failures in a project-specific
                                      exception

  `knowflow/config.py`                Load environment-based settings

  `knowflow/cli.py`                   Command-line index and question
                                      commands

  `tests/`                            Unit tests for local helper
                                      behavior

  `knowledge_base/`                   Sample documents for safe
                                      evaluation

  `evaluation/`                       Example questions for manual
                                      quality checks
  -----------------------------------------------------------------------

## Index format

The index is written beneath `INDEX_DIR` as `index.json`. Each record
contains the source-relative filename, chunk number, text, and token
list. The index is generated data and should not be committed.

Rebuild the index whenever documents are added or changed:

``` bash
python -m knowflow.cli index
```

## Retrieval behavior

Retrieval is lexical, not semantic. It compares tokens in the question
with tokens in each passage. It is fast and avoids a separate embedding
model, but it may miss paraphrases, synonyms, and conceptually related
passages that share few words with the question.

The score is a ranking heuristic, not a calibrated confidence
probability. Tune `TOP_K` and `MIN_RELEVANCE` against representative
evaluation questions rather than interpreting the score as certainty.

## Answer grounding and citations

Retrieved passages are labeled `[S1]`, `[S2]`, and so on in the prompt.
The model is instructed to cite these markers and to say when the
evidence is insufficient. The UI separately displays retrieved passages
so users can check claims.

Citations currently point to a source file and passage number. They do
not guarantee exact page-level locations in PDFs, nor do they guarantee
that every generated statement is correctly supported. Users must verify
important answers.

## External service boundary

Document parsing and retrieval happen locally. The question and selected
passages are sent to the configured Gemini model. No local LLM or
embedding model is downloaded.

The current implementation does not provide a SharePoint connector,
source-system permission filtering, tenant-level access enforcement, or
production-grade document synchronization.
