# Pull Request Readiness Checklist

Use this checklist before submitting the Method Documents AI Agent
contribution.

## Documentation and setup

-   [ ] The project README follows the repository's shared template
    sections.
-   [ ] Installation and run instructions work from a fresh clone.
-   [ ] `requirements.txt` declares project dependencies.
-   [ ] `.env.example` contains placeholders only and documents required
    settings.
-   [ ] The selected Gemini model is available to the contributor's API
    account.
-   [ ] Limitations, external API use, and privacy implications are
    documented.
-   [ ] The UI branding and project name are consistent.

## Testing

-   [ ] Run `python -m pytest -q`.
-   [ ] Build the index from the sample documents.
-   [ ] Run at least one manual question through the CLI or Streamlit.
-   [ ] Verify that displayed sources support the answer.
-   [ ] Do not claim a live API test passed if it was blocked by
    network, quota, or provider availability.

## Security and repository hygiene

-   [ ] `.env` is not staged.
-   [ ] `.venv/`, `.knowflow_index/`, caches, and generated files are
    not staged.
-   [ ] No private documents, credentials, or API keys are staged.
-   [ ] The PR changes are limited to `agents/method-docs-ai/`, except
    for an explicitly permitted project-index entry.
-   [ ] The shared root contribution guide and pull request template
    have been followed.
