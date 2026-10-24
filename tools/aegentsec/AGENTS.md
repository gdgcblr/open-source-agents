# Repository Guidelines

These guidelines apply to `tools/aegentsec/`.

## Purpose and scope

AegentSec is a hackathon prototype for **agent identity and access management**. An administrator registers enterprises and agents, assigns approved scopes, and receives each agent's client secret once. Agents exchange their credentials for short lived, RS256 signed access tokens. The service exposes identity and permission queries over authenticated MCP; a separate Python SDK verifies tokens and enforces scopes in external FastAPI applications. The deterministic demo proves both permitted and denied actions. Read this guide together with this directory's `README.md` and the repository's `../../CONTRIBUTING.md`.

The agreed prototype choices take precedence over the original pasted proposal: **SQLite instead of MongoDB**, and the **deterministic demo as the supported walkthrough**; no LLM agent example is shipped yet. Keep configuration in `.env` with sanitized names and examples in `.env.example`. No paid service is required for the deterministic demo.

## Code map and boundaries

- `src/aegentsec/database.py`: async SQLite persistence; enterprise and agent records, uniqueness, and foreign keys.
- `src/aegentsec/services.py`: reusable IAM rules, registration, credential verification, approved scopes, and permission checks. Keep business rules here, outside transport handlers.
- `src/aegentsec/tokens.py`: RSA signing, JWT verification, and public JWKS. `config.py` holds settings.
- `src/aegentsec/api.py`: admin registration and client credentials REST routes. `application.py` creates the FastAPI app, initializes SQLite, publishes metadata/JWKS, and mounts MCP at `/mcp`.
- `src/aegentsec/mcp_server.py`: official MCP SDK Streamable HTTP server with `whoami`, `check_permission`, and `list_my_permissions`. MCP is an interface to IAM, not the policy engine.
- `sdk/aegentsec_sdk/`: independent JWKS based token verifier and FastAPI scope dependencies. External APIs must enforce authorization here even if an agent previously called `check_permission`.
- `examples/inventory_backend.py`: protected mock API. `examples/demo.py`: repeatable two-agent HTTP/MCP walkthrough. `scripts/generate_keys.py` creates local signing keys; `tests/` holds pytest coverage.

## Security invariants

- Deny scopes missing from the admin-managed catalogue, and unknown resources. Scope matching is exact, with no wildcard permissions. Only the admin API key can create enterprises, manage the scope catalogue, or grant agent scopes.
- Generate unique credentials per agent. Store only Argon2 hashes; return plaintext client secrets only at registration. Never place secrets in JWTs, model prompts, tool arguments, or logs.
- Verify JWT signature, RS256 algorithm, key ID, issuer, expiry, and **exact audience**. MCP tokens target `MCP_RESOURCE_URI`; inventory API tokens target `INVENTORY_API_AUDIENCE`. Never reuse one across the other.
- Derive MCP identity from the authenticated bearer token, never from tool input. MCP also checks current agent and enterprise status. The standalone SDK verifies signed claims and does not query IAM state; existing backend tokens have no dynamic revocation.
- Keep `.env`, `keys/`, `data/`, SQLite files, and credentials out of Git. Do not weaken checks to make a demo pass. This prototype needs HTTPS, stronger admin authentication, rotation, and revocation before production use.

## Local workflow

Run from `tools/aegentsec/` with Python 3.12+ and `uv`:

```bash
uv sync --extra dev
cp .env.example .env                 # Set a long, random ADMIN_API_KEY
uv run --env-file .env python scripts/generate_keys.py
uv run --extra dev pytest -q
uv run --extra dev ruff check src sdk examples tests scripts
```

Start the IAM app on port 8000 and the example inventory API on port 8001 using the commands in `README.md`, then run `uv run --env-file .env python examples/demo.py`. Keep the deterministic demo usable without a model.

## Changes and verification

Use four-space indentation, type hints, `snake_case` functions/modules, and `PascalCase` classes; Ruff uses a 100-character line limit. Add focused `tests/test_*.py` coverage for new IAM, JWT, MCP, or SDK behavior, including denial paths and real HTTP boundaries when they change. Document new settings in `.env.example` and `README.md`. Keep changes inside `tools/aegentsec/` except an optional `tools/README.md` index entry; follow `../../CONTRIBUTING.md` and the repository root's `.github/PULL_REQUEST_TEMPLATE.md` for submission.
