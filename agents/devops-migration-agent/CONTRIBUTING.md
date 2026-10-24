# Contributing to DevOps Migration Agent

Thank you for your interest in improving the DevOps Migration Agent!

## Development Guidelines

1. **Isolation:** Keep all changes confined within `agents/devops-migration-agent/`. Do not introduce root dependencies.
2. **Environment Setup:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```
3. **Running Tests:**
   ```bash
   pytest --cov=.
   ```
4. **Linting and Formatting:**
   ```bash
   ruff check .
   ruff format .
   ```
5. **Testing Offline Execution:**
   ```bash
   python agent.py --workflow samples/github-action-example.yml --output ./migration-output --offline
   ```
6. **Code Safety:**
   - Never execute user scripts or arbitrary workflow commands.
   - Never commit API keys or private tokens.
   - Use `yaml.safe_load` exclusively.
