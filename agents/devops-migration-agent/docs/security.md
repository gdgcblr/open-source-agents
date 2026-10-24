# Security Architecture & Threat Model

The **DevOps Migration Agent** adheres to strict security and privacy standards.

## Core Security Tenets

1. **Zero Secret Leakage:**
   - The agent scans for `${{ secrets.NAME }}` references and maps them to sanitized Azure DevOps variables (`$(NAME)`).
   - Secret values are **never** logged, dumped, or output to report files.
   - If plaintext credentials or private keys are detected in source files, the agent flags a **CRITICAL** risk factor with deployment blockers, without exposing the raw secret.

2. **No Script Execution:**
   - The agent performs purely static analysis.
   - Shell commands, bash blocks, PowerShell snippets, and inline actions are treated strictly as string data.
   - No workflow scripts are ever executed on the host system during analysis or migration.

3. **Safe Deserialization:**
   - All YAML loading is handled via `yaml.safe_load`.
   - Python code execution via YAML tags (e.g., `!!python/object`) is blocked.

4. **Least-Privilege Azure DevOps Permissions:**
   - When converting workflows with `permissions: write-all`, the agent issues a high-priority security warning.
   - Recommendations explicitly advise scoping the Azure DevOps Project Collection Build Service account to least-privilege repository and pipeline access.

5. **Cloud Infrastructure Safety:**
   - The agent never interacts directly with Azure, AWS, or GCP APIs during analysis.
   - Terraform files are parsed statically with regex analysis; no `terraform init`, `plan`, or `apply` is executed.
