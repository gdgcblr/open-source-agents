# Known Limitations & Edge Cases

While the DevOps Migration Agent handles complex multi-job workflows, triggers, matrices, and Terraform configurations, the following architectural and platform limitations apply:

1. **Complex GitHub Script Context:**
   - Workflows utilizing `actions/github-script` often call internal GitHub REST APIs (e.g. `github.rest.issues.createComment`).
   - Azure DevOps does not provide an Octokit execution layer. These steps are flagged as `MANUAL_MIGRATION` with placeholders generated in the YAML.

2. **Self-Hosted Runner Pools:**
   - GitHub Actions workflows targeting specialized labels (e.g., `runs-on: [self-hosted, gpu-node]`) require setting up self-hosted agent pools in Azure DevOps with matching agent demands.

3. **Composite & Reusable Workflows:**
   - GitHub Actions nested `workflow_call` invocations must be mapped to Azure DevOps YAML Pipeline Templates (`templates: ...`). This initial release maps the top-level calling workflow.

4. **GitHub Packages / OIDC Federation:**
   - Workflows utilizing `permissions: id-token: write` for GitHub OIDC federated login to Azure require creating an Azure App Registration with Workload Identity Federation (WIF) configured specifically for Azure DevOps Service Connections.

5. **HashFiles Expressions:**
   - GitHub Actions `hashFiles('**/requirements.txt')` syntax is not directly supported by Azure DevOps. Azure DevOps `Cache@2` uses pipe syntax (e.g. `'prefix' | **/requirements.txt`). The agent flags these for operator review.
