# Security, Privacy, and Known Limitations

## Data flow

-   Source files are read from the configured local `KNOWLEDGE_DIR`.
-   The generated index stores extracted text and token data under
    `INDEX_DIR`.
-   When a question is answered, the question and selected retrieved
    passages are sent to the Gemini API.
-   The Gemini API key is loaded from the local environment
    configuration.

Before using non-public documents, review your organization's policies
and the current Gemini API terms, data-use terms, and account
configuration.

## Secret handling

-   Keep the actual `.env` file out of version control.
-   Never hard-code API keys in Python source, tests, screenshots, or
    documentation.
-   Commit only `.env.example` with placeholder values.
-   If a key is exposed, revoke or rotate it promptly.
-   Do not include generated indexes or private documents in a pull
    request.

## Document permissions

This MVP does not connect directly to SharePoint or another enterprise
repository. It does not inherit or enforce document-level access
controls. A local folder or synced directory may contain documents that
have different audiences; indexing them together can expose excerpts to
anyone who can use the app and API key.

Use only documents the operator is authorized to process and that are
approved for the chosen model provider. A production connector must
authenticate through an approved mechanism and filter documents
according to the requesting user's effective permissions before
retrieval.

## Prompt injection and untrusted content

Documents can contain misleading or malicious instructions. The system
prompt tells the model to treat retrieved passages as evidence rather
than instructions, but this is only a mitigation. Do not treat this
behavior as a security boundary and do not give the agent tools or
permissions that could perform sensitive actions without separate
controls.

## Known limitations

-   Retrieval is lexical and can miss paraphrases or related concepts.
-   The relevance score is heuristic, not a probability of correctness.
-   Citations identify a file and passage, not an exact PDF page.
-   Scanned PDFs without a text layer may produce little or no
    searchable content.
-   API availability, model names, rate limits, and quota are controlled
    by the provider and can change.
-   Temporary provider errors such as `503` and quota/rate-limit errors
    such as `429` can interrupt answer generation.
-   The current unit tests do not prove end-to-end availability of the
    Gemini service.
-   Windows setup has not been verified by this project documentation.
-   There is no direct SharePoint integration or permission-aware
    retrieval.

## Safe demo checklist

-   [ ] Use synthetic, public, or explicitly approved sample documents.
-   [ ] Verify `.env` is ignored by Git.
-   [ ] Verify `.knowflow_index/` and `.venv/` are ignored by Git.
-   [ ] Do not include real company documents in the repository.
-   [ ] Confirm the configured model is available to the API account.
-   [ ] Verify generated answers against their cited source passages.
