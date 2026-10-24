# Testing and Evaluation

## Automated tests

Activate the project's virtual environment and run tests from the
project root:

``` bash
python -m pytest -q
```

Use `python -m pytest` rather than relying on a standalone `pytest`
executable if the latter resolves a different Python environment or
import path.

The unit tests exercise local document and retrieval helpers. They are
intended to run without making live Gemini API requests, so they can be
used in environments where the API is unavailable or quota-limited.

## Manual smoke test

1.  Install dependencies using
    `python -m pip install -r requirements.txt`.

2.  Configure `GEMINI_API_KEY` and a currently supported
    `GEMINI_CHAT_MODEL` in `.env`.

3.  Confirm the sample files exist under `knowledge_base/sample_docs/`.

4.  Build the index:

    ``` bash
    python -m knowflow.cli index
    ```

5.  Ask a sample question:

    ``` bash
    python -m knowflow.cli ask "What should I check when an OData property is a collection?"
    ```

6.  Start the UI and ask the same question:

    ``` bash
    streamlit run app.py
    ```

7.  Verify the answer cites relevant source markers and that the UI
    shows the source passages.

8.  Ask a question unrelated to the sample documents and confirm the app
    does not confidently invent an answer when no relevant evidence is
    retrieved.

## Evaluation questions

The `evaluation/sample_questions.json` file contains sample questions
for manual evaluation. For each question, check:

-   Were relevant passages retrieved?
-   Are cited sources present and actually support the answer?
-   Did the answer avoid inventing details not present in the documents?
-   Does the agent clearly acknowledge when the indexed documents do not
    contain enough information?

This is a manual evaluation set, not a benchmark with measured accuracy.
Do not claim an accuracy score unless a reproducible evaluation has been
run and documented.

## Provider failures

A live smoke test may fail because of network access, model
availability, API quota, or temporary service load. For `404`, check the
configured model name and account availability. For `429`, check quota
and rate limits. For `503`, retry after a delay and check provider
status. These failures are separate from the local unit tests.
