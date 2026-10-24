# Review verdict

- **Model:** `gemini/gemini-3.1-flash-lite`
- **Date:** 2026-10-24
- **Agent:** `oss-adoption-reviewer` (scores computed by `scan_repo`; the model writes the prose)

---

## Request: `Review https://github.com/google-research/harness2`

- **Tool calls:** `clone_repo`, `scan_repo`
- **Wall time:** 15 s

### Agent output (verbatim)

## Usefulness & clarity — 4/5
* The repository provides a clear summary and problem statement for the harness.
* `missing:readme_example`: Including a concrete "getting started" code snippet in the README would help users immediately grasp how to invoke the harness.

## Ease of adoption — 3/5
* The repository includes installation instructions and a dependency manifest.
* `missing:prerequisites`: New adopters need a clear list of system requirements (e.g., Python version, OS dependencies).
* `missing:lockfile`: The lack of a lockfile makes it difficult to ensure consistent, reproducible environments across different machines.
* `missing:env_example`: Providing an `.env.example` file is essential for users to identify and configure necessary API keys or environment variables.

## Maintainability & contributor friction — 3/5
* The project includes a license, contributing guidelines, tests, and linting configuration.
* `missing:code_of_conduct`: A Code of Conduct is vital for fostering an inclusive community and setting behavioral standards.
* `missing:issue_pr_templates`: Standardized templates reduce friction by guiding contributors to provide necessary information upfront.

## Distribution & scale — 1/5
* The repository includes packaging metadata.
* `missing:container`: Providing a Dockerfile would significantly streamline deployment and environment consistency.
* `missing:ci`: Lack of automated CI makes it difficult to ensure code quality and stability for contributors and maintainers.
* `missing:changelog`: A CHANGELOG is essential for tracking progress and helping users understand what has changed between releases.

## Friction red flags — 5/5
* No friction red flags were identified.

## Top 5 fixes
1. **Create an `.env.example` file** to explicitly list required environment variables and their formats (`missing:env_example`).
2. **Add a `requirements.txt` or `poetry.lock`** file to lock dependencies and improve reproducibility (`missing:lockfile`).
3. **Add a GitHub Actions workflow** to automate testing and ensure code quality on PRs (`missing:ci`).
4. **Update the README with a quickstart code snippet** showing the most common usage of the harness (`missing:readme_example`).
5. **Add a `CONTRIBUTING.md` or dedicated folder for Issue and PR templates** to standardize contributions (`missing:issue_pr_templates`).
