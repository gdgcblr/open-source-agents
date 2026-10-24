# Changelog

All notable changes to the DevOps Migration Agent project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-24

### Added
- **GitHub Actions Parser:** Safely parses workflows, triggers, jobs, steps, environment variables, and matrices.
- **Explainable Compatibility Registry:** Maps 10+ core GitHub Actions to Azure DevOps native tasks.
- **Azure DevOps Pipeline Generator:** Jinja2-based pipeline YAML generator with structural validation.
- **Terraform Static Analysis:** Analyzes `.tf` configurations, detects providers, remote state, and required service connections.
- **Deterministic Risk Assessor:** Quantitative scoring model (0-100) and blockers identification.
- **Report & Deliverables Generator:** Produces `generated-pipeline.yml`, `migration-report.md`, `risk-assessment.md`, `migration-checklist.md`, `migration-summary.json`, and `validation-results.json`.
- **Google ADK Integration:** Built-in Google ADK Agent utilizing Gemini 2.5 Flash with complete offline execution fallback.
- **Automated Test Suite:** Comprehensive test suite with 44 passing unit and integration tests (88% code coverage).
