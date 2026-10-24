# adk-memshield

> A drop-in Google ADK `BaseMemoryService` that stores long-term semantic memory in PostgreSQL `pgvector` and enforces tenant, user and clearance isolation inside the database with `FORCE ROW LEVEL SECURITY`. A missing or wrong application filter returns fewer rows, never someone else's rows.

[![PyPI](https://img.shields.io/badge/PyPI-adk--memshield%200.1.0-10b981.svg)](https://pypi.org/project/adk-memshield/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](./pyproject.toml)
[![Google ADK](https://img.shields.io/badge/google--adk-%3E%3D2.12-4285F4.svg)](https://github.com/google/adk-python)

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Multi-tenant and multi-agent `google-adk` deployments often keep long-term semantic memory in one shared vector table, and isolation is enforced only by the `WHERE` clause the application remembers to write. That design leaks in two well-documented ways:
  1. **Cross-user semantic leakage.** *MemLeak: Cross-User Semantic Leakage in Multi-Tenant AI Agent Memory* ([arXiv:2610.04195](https://arxiv.org/abs/2610.04195)) shows that similarity search over a pooled store surfaces other users' memories without any exploit. It finds hard ownership gating to be the mitigation that consistently restores the clean baseline.
  2. **Lateral leakage inside agent swarms.** *AgentLeak* ([arXiv:2602.11510](https://arxiv.org/abs/2602.11510)) shows that internal channels between agents are a major leakage path. adk-memshield covers the memory-retrieval slice of that problem: a low-clearance sub-agent must not retrieve shared tenant memories labelled above its clearance.

  `adk-memshield` moves ownership gating out of application code and into PostgreSQL itself.
- **Intended Users**:
  - Developers building multi-user or multi-tenant agents on Google ADK
  - Platform and security engineers who need memory isolation that survives application bugs and prompt-injected tool arguments
  - Teams running agent swarms with different clearance tiers

### Key Features
- **Drop-in `BaseMemoryService`**: Implements `add_session_to_memory`, `add_memory` and `search_memory`, and plugs into `Runner(memory_service=...)` with ADK's built-in `preload_memory_tool` and `load_memory_tool`.
- **Kernel-enforced isolation**: `FORCE ROW LEVEL SECURITY` policies gate `SELECT`, `INSERT`, `UPDATE` and `DELETE` by `app_name`, `tenant_id`, `user_id`, `scope` (`private` / `tenant_shared`) and `min_clearance` (1–5).
- **Pool-safe identity**: Every operation runs in an explicit transaction that binds identity with `set_config('app.*', value, true)`, so identity never bleeds into the next pooled connection.
- **Fail-closed**: With no identity context a query sees 0 rows, and empty `app_name` / `user_id` values are rejected before touching the database.
- **No write-up, no owner spoofing**: An agent cannot write a `tenant_shared` memory above its own clearance, or a row owned by another user. PostgreSQL raises `InsufficientPrivilege` (SQLSTATE `42501`).
- **Escape hatch that stays safe**: `rls_transaction(app_name, user_id)` yields a cursor for custom SQL that is still filtered by RLS, even with no `WHERE` clause.
- **Ready to use**:
  - Local embeddings with FastEmbed `BAAI/bge-small-en-v1.5` (384-d, ONNX, CPU)
  - Idempotent session ingestion
  - Per-query telemetry (`last_query_telemetry`)
  - A `memshield://` URI for ADK's service registry
  - Published on PyPI: `pip install adk-memshield`

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ (the Docker image uses Python 3.12)
- **Agent Framework / Core Library**:
  - Google ADK (`google-adk>=2.12,<3`): `BaseMemoryService`, `Runner`, `preload_memory_tool`, `load_memory_tool`
  - Pydantic v2 (configuration)
  - `psycopg` 3 with `psycopg_pool`
- **Models**:
  - The library calls **no LLM**.
  - Embeddings come from FastEmbed `BAAI/bge-small-en-v1.5` (local ONNX, 384-d), or your own `embed_fn`.
  - Your ADK agent can use any model (Gemini, local Ollama models via LiteLLM, and so on).
  - The test suite uses a scripted mock `BaseLlm`.
- **External APIs / Tools**: PostgreSQL 16 + `pgvector` (`pgvector/pgvector:pg16`) and Docker Compose for the bundled database and test runner.

### Model Assumptions & Token / API Requirements
- **No API keys, no paid services, no GPU.** Embeddings run locally on CPU. The library, tests, benchmark and example all run fully offline once the FastEmbed model has been downloaded; the Docker image pre-caches it.
- Any model cost comes only from the ADK agent you build on top. adk-memshield adds retrieved memory text to that agent's context (up to `top_k`, default 5 rows).

---

## Architecture & Data Flow

```mermaid
flowchart LR
    subgraph ADK["Google ADK Runtime"]
        Agent["ADK Agent / Sub-Agent<br/>(app_name, user_id from Runner)"]
        Service["MemShieldMemoryService<br/>(BaseMemoryService)<br/>tenant_id + clearance from config"]
        Embedder["MemShieldEmbedder<br/>(FastEmbed bge-small-en-v1.5, 384d)"]
    end

    subgraph PG["PostgreSQL 16 + pgvector (role memshield_app, NOBYPASSRLS)"]
        Tx["Explicit transaction"]
        Ctx["Transaction-local identity<br/>set_config('app.*', val, true)"]
        RLS["RLS policies<br/>SELECT / INSERT / UPDATE / DELETE"]
        Vec[("memories<br/>vector(384)")]
    end

    Agent --> Service
    Service --> Embedder
    Service --> Tx
    Tx --> Ctx
    Ctx --> RLS
    RLS --> Vec
```

1. ADK's memory tools call `search_memory(app_name, user_id, query)` with the Runner's authenticated identity. `tenant_id` and `agent_clearance` come from the service's `MemShieldConfig`.
2. The query is embedded locally. Embedding and database I/O run in `asyncio.to_thread`, so the ADK event loop is never blocked.
3. The service opens a transaction on a pooled connection as the least-privilege `memshield_app` role (`NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`). It binds `app.current_app_name`, `app.current_tenant_id`, `app.current_user_id` and `app.agent_clearance` with `set_config(..., true)`.
4. The RLS policies in [`sql/01_schema.sql`](./sql/01_schema.sql) restrict visible rows:
   - `SELECT` allows own rows, plus `tenant_shared` rows with `min_clearance <= app.agent_clearance`.
   - `INSERT` / `UPDATE` (`USING` + `WITH CHECK`) and `DELETE` (`USING`) allow only the caller's own rows, and never a shared row above the writer's clearance.
5. The library's own SQL also filters by user, scope and clearance (defense in depth). The vector-distance `ORDER BY ... LIMIT top_k` runs over policy-visible rows only, and results return to ADK as `MemoryEntry` objects with similarity metadata.

---

## Prerequisites

- **Python 3.10+** and `pip`
- **PostgreSQL 16 with `pgvector`.** The bundled `docker compose` `db` service provides one on `localhost:54329`, so **Docker** with Compose v2 is recommended.
- **No API keys** are required for the library, tests, benchmark or example.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/adk-memshield
   ```

2. **Install the package.**

   From PyPI:
   ```bash
   pip install adk-memshield
   ```

   Or from source for development, in a virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -e ".[dev]"
   ```

3. **Start PostgreSQL + pgvector and apply the schema.** On first start, the bundled database applies `sql/01_schema.sql` and the benchmark-only `sql/02_benchmark_baseline.sql`:
   ```bash
   docker compose -p adk-memshield up -d db
   ```
   For your own PostgreSQL, apply [`sql/01_schema.sql`](./sql/01_schema.sql) as the owner or a superuser, then **rotate the `memshield_app` password**. The schema also ships inside the wheel:
   ```python
   from importlib.resources import files

   schema_sql = (files("adk_memshield") / "sql" / "01_schema.sql").read_text()
   ```

4. **Configure environment variables (optional).** The defaults match the bundled database:
   ```bash
   cp .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `MEMSHIELD_DB_DSN` | No | `postgresql://memshield_app:memshield_pass@localhost:54329/memshield` | Default `MemShieldConfig.dsn`. It **must** be a non-superuser, `NOBYPASSRLS` role. |
| `MEMSHIELD_ADMIN_DSN` | No | `postgresql://postgres:postgres_admin_pass@localhost:54329/memshield` | Admin DSN used only by tests, the benchmark and the example to seed and clean up rows. |
| `MEMSHIELD_TENANT_ID` | No | `acme_corp` | Tenant used by `examples/quickstart.py`. In code, pass `MemShieldConfig(tenant_id=...)`. |
| `MEMSHIELD_AGENT_CLEARANCE` | No | `1` | Agent clearance (1–5) used by `examples/quickstart.py`. In code, pass `MemShieldConfig(agent_clearance=...)`. |
| `FASTEMBED_CACHE_PATH` | No | FastEmbed default | Directory for the cached ONNX embedding model. The Docker image uses `/opt/fastembed_cache`. |

`MemShieldConfig` fields:

| Field | Default | Meaning |
| :--- | :--- | :--- |
| `dsn` | `$MEMSHIELD_DB_DSN` | Connection URI for the RLS-enforced role. |
| `tenant_id` | `default` | Tenant bound to `app.current_tenant_id`. |
| `agent_clearance` | `1` | Clearance bound to `app.agent_clearance` (1–5). |
| `default_scope` | `private` | Scope for new memories without `custom_metadata["scope"]`. |
| `default_min_clearance` | `1` | Read clearance for new `tenant_shared` memories. |
| `top_k` | `5` | Maximum rows returned by `search_memory`. |
| `min_similarity` | `None` | Optional cosine-similarity floor. |
| `table_name` | `memories` | Validated against `^[A-Za-z_][A-Za-z0-9_]*$`. |
| `simulate_missing_app_filter` | `False` | Chaos/testing flag: drop the library's own `WHERE` clause to prove RLS alone isolates. |

---

## How to Run

**Wire it into an ADK `Runner`:**

```python
from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.load_memory_tool import load_memory_tool
from google.adk.tools.preload_memory_tool import preload_memory_tool

from adk_memshield import MemShieldConfig, MemShieldMemoryService

memory_service = MemShieldMemoryService(
    MemShieldConfig(
        dsn="postgresql://memshield_app:memshield_pass@localhost:54329/memshield",
        tenant_id="tenant_alpha",
        agent_clearance=2,
    )
)

runner = Runner(
    app_name="finance_copilot",
    agent=LlmAgent(
        name="assistant",
        model="gemini-2.5-flash",
        tools=[preload_memory_tool, load_memory_tool],
    ),
    session_service=InMemorySessionService(),
    memory_service=memory_service,
)
# Persist a finished session with: await memory_service.add_session_to_memory(session)
```

**Write and search memories directly:**

```python
from google.adk.memory.memory_entry import MemoryEntry
from google.genai import types

await memory_service.add_memory(
    app_name="finance_copilot",
    user_id="alice",
    memories=[
        MemoryEntry(
            content=types.Content(parts=[types.Part(text="Wire routing code is SWIFT-ALPHA-99.")]),
            custom_metadata={"scope": "private"},
        ),
        # Visible to tenant agents with clearance >= 2 (the writer's clearance must be >= 2).
        MemoryEntry(
            content=types.Content(parts=[types.Part(text="Treasury approval threshold is $250k.")]),
            custom_metadata={"scope": "tenant_shared", "min_clearance": 2},
        ),
    ],
)

response = await memory_service.search_memory(
    app_name="finance_copilot", user_id="alice", query="What is my wire routing code?"
)
print(memory_service.last_query_telemetry.to_dict())  # SQL, identity context, latency, rows
```

**Run custom SQL under the caller's RLS identity:**

```python
with memory_service.rls_transaction(app_name="finance_copilot", user_id="alice") as cur:
    cur.execute("SELECT content FROM memories ORDER BY created_at DESC LIMIT 10")
    rows = cur.fetchall()  # only rows alice may read, even though the SQL has no WHERE clause
```

**Use a `memshield://` URI with ADK's service registry:**

```python
from adk_memshield import register_adk_uri
from google.adk.cli.service_registry import get_service_registry

register_adk_uri("memshield")
memory_service = get_service_registry().create_memory_service(
    "memshield://memshield_app:memshield_pass@localhost:54329/memshield?tenant_id=tenant_alpha&agent_clearance=2"
)
```

**Run the bundled example and benchmark:**

```bash
docker compose -p adk-memshield run --rm test python examples/quickstart.py
docker compose -p adk-memshield run --rm test python benchmarks/run_memleak_eval.py
```

---

## Example Input & Output

All output below comes from genuine runs on Windows 11 with Docker Desktop, using the bundled `pgvector:pg16` database.

### Example 1: Isolation in one shared table ([`examples/quickstart.py`](./examples/quickstart.py))

The script writes four memories into one `memories` table:
- Alice's private API key
- Bob's private KMS key
- a `tenant_shared` clearance-1 runbook
- a `tenant_shared` clearance-3 board memo

It then searches as Alice, runs a `WHERE`-less `count(*)` under her identity, and tries to insert a row owned by Bob.

**Input**
```bash
docker compose -p adk-memshield run --rm test python examples/quickstart.py
```

**Output**
```
tenant=acme_corp clearance=1 caller=alice
query: 'What are the production API keys and KMS recovery keys?'

search_memory -> 2 row(s) visible to alice:
  [tenant_shared clr>=1] sim=0.699  Support runbook: API key rotation requests go through the self-service portal.
  [private       clr>=1] sim=0.699  Alice's staging sandbox API key is SANDBOX-ALICE-101.

SELECT count(*) FROM memories  (no WHERE, as alice): 2 of 4 rows
owner-spoof INSERT as bob: REJECTED (SQLSTATE 42501) new row violates row-level security policy for table "memories"
```

Raising the agent's clearance changes only what `tenant_shared` content is visible. Bob's private row stays hidden:

```bash
docker compose -p adk-memshield run --rm -e MEMSHIELD_AGENT_CLEARANCE=3 test python examples/quickstart.py
```
```
search_memory -> 3 row(s) visible to alice:
  [tenant_shared clr>=1] sim=0.699  Support runbook: API key rotation requests go through the self-service portal.
  [private       clr>=1] sim=0.699  Alice's staging sandbox API key is SANDBOX-ALICE-101.
  [tenant_shared clr>=3] sim=0.575  Board memo: Project Titan API platform budget is TITAN-EXEC-300.

SELECT count(*) FROM memories  (no WHERE, as alice): 3 of 4 rows
```

### Example 2: Benchmark, unprotected `pgvector` vs. `adk-memshield`

[`benchmarks/run_memleak_eval.py`](./benchmarks/run_memleak_eval.py) seeds a synthetic enterprise corpus into an ordinary table and into the RLS table. The corpus has **3 tenants, 6 users and 60 memories**:
- API credentials
- compensation and medical/HR records
- query-shaped lure memories
- L3/L4 executive memos

Each scenario runs **the same buggy application-layer SQL** against both tables, under the same transaction-local identity of the authenticated caller. The only variable is whether the database enforces ownership. The run uses `top_k=3`, 75 queries and 5 repeats.

**Input**
```bash
docker compose -p adk-memshield run --rm test python benchmarks/run_memleak_eval.py
```

**Output** (run of 2026-10-24; the leakage and recall figures are deterministic and match earlier runs exactly)

| Scenario | Application-layer mistake | Queries | Unprotected: queries leaking | Unprotected: leaked share of top-k rows | Unprotected: leak at rank 1 | `adk-memshield`: queries leaking | Unprotected clean recall | `adk-memshield` clean recall |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Scenario 1: Shared-Tenant Pool (Incidental Overlap) | Filters `tenant_id` only, omits `user_id`/`scope` | 12 | 100.0% | 44.4% | 8.3% | **0.0%** | 100.0% | **100.0%** |
| Scenario 2: Adversarial Top-K Planted Lure | Same tenant-only filter; co-tenant plants query-shaped lures | 12 | 100.0% | 58.3% | 58.3% | **0.0%** | 100.0% | **100.0%** |
| Scenario 3: Tool-Argument `user_id` Override | Correct filter, but `user_id` taken from attacker-controlled tool args | 9 | 100.0% | 81.5% | 100.0% | **0.0%** | n/a | **n/a** |
| Scenario 4: Low-Clearance Swarm Agent (AgentLeak-style) | Own + `tenant_shared` rows, omits `min_clearance` check | 9 | 100.0% | 44.4% | 66.7% | **0.0%** | 100.0% | **100.0%** |
| Scenario 5: Total Filter Omission | No `WHERE` clause at all (`simulate_missing_app_filter=True`) | 33 | 100.0% | 74.7% | 69.7% | **0.0%** | 72.7% | **100.0%** |
| **Mean of Scenarios 1-5** | | 75 | **100.0%** | **60.7%** | **60.6%** | **0.0%** | **93.2%** | **100.0%** |
| Control: Correct App Filter (no bug) | `MemShieldMemoryService` default filter (user/scope/clearance) | 33 | 0.0% | 0.0% | 0.0% | **0.0%** | 100.0% | **100.0%** |

Retrieval latency (database transaction including `set_config`, 60 rows, ms):

| Scenario | Unprotected p50 / p95 | `adk-memshield` p50 / p95 |
| :--- | :---: | :---: |
| Scenario 1: Shared-Tenant Pool (Incidental Overlap) | 1.22 / 1.99 | 1.05 / 1.70 |
| Scenario 2: Adversarial Top-K Planted Lure | 1.13 / 1.69 | 1.02 / 1.52 |
| Scenario 3: Tool-Argument `user_id` Override | 1.20 / 1.76 | 1.16 / 1.91 |
| Scenario 4: Low-Clearance Swarm Agent (AgentLeak-style) | 1.21 / 1.86 | 1.06 / 1.44 |
| Scenario 5: Total Filter Omission | 1.10 / 1.80 | 1.01 / 1.73 |
| Control: Correct App Filter (no bug) | 1.35 / 2.07 | 0.95 / 1.35 |

**How to read this**
- **RLS removed every unauthorized row in every scenario**, while the identical buggy SQL leaked on the plain table. The control row confirms the classifier reports 0% when the application filter is correct.
- **The leak rate is saturated by fixed top-k.** With no similarity floor, `LIMIT 3` always fills its slots, so every buggy query leaked at least one row. The *leaked share* and *rank-1* columns show how much of the retrieved context was unauthorized.
- **Planted lures hijack rank 1, not recall.** Each Scenario 2 lure restates the target question and adds a malicious payload, modelling a white-box, PoisonedRAG-style attacker. On the plain table a lure took rank 1 in 58.3% of queries. With RLS the lures were never retrieved.
- **Recall gains are specific.** In Scenarios 1, 2 and 4 the caller's own answer still made the top 3, so RLS changed *what else* was in context rather than recall. The gain appears under total filter omission (72.7% → 100%).
- **Scenario 3 has no authorized answer** (pure exfiltration attempts), so recall is n/a. RLS turns the attack into an own-rows-only or empty result; it cannot repair the application's wrong `user_id` argument.
- **Latency.** At 60 rows the RLS overhead is within run-to-run noise: in this run adk-memshield's p50 was slightly *lower*, and an earlier run had it slightly higher. The corpus and queries are synthetic, so treat the numbers as a reproducible illustration of failure modes, not as real-world leak rates.

---

## How to Test

The integration suite has 8 tests and runs against a real PostgreSQL + pgvector instance:
- the ADK session round-trip
- cross-tenant and cross-user isolation
- RLS with the application filter removed
- multi-agent clearance RBAC
- fail-closed behaviour without identity context
- `INSERT` spoofing blocked by RLS
- a real `google.adk` `Runner` driving `preload_memory` and `load_memory`

```bash
docker compose -p adk-memshield up -d db
docker compose -p adk-memshield run --rm test pytest -v
```

Expected output:

```
tests/test_rls_isolation.py::test_adk_session_and_memory_roundtrip PASSED [ 12%]
tests/test_rls_isolation.py::test_cross_tenant_isolation PASSED          [ 25%]
tests/test_rls_isolation.py::test_cross_user_private_isolation PASSED    [ 37%]
tests/test_rls_isolation.py::test_missing_app_filter_rls_protection PASSED [ 50%]
tests/test_rls_isolation.py::test_multi_agent_clearance_rbac PASSED      [ 62%]
tests/test_rls_isolation.py::test_fail_closed_without_session_context PASSED [ 75%]
tests/test_rls_isolation.py::test_insert_spoofing_blocked_by_rls PASSED  [ 87%]
tests/test_rls_isolation.py::test_adk_runner_preload_and_load_memory_integration PASSED [100%]
========================= 8 passed, 1 warning in 4.99s =========================
```

To run locally against the same database (after `pip install -e ".[dev]"`):

```bash
pytest -v
```

---

## Known Limitations

- **Same-tier shared memory poisoning is outside RLS scope.** `tenant_shared` content is trusted by design. A user may publish a shared memory at or below their own clearance, and every agent in the tenant with sufficient clearance will retrieve it. RLS enforces *who may read*, not whether the content is benign. Use write approval, provenance or content moderation for shared scopes.
- **A superuser or `BYPASSRLS` role disables the protection.** Superusers and `BYPASSRLS` roles ignore RLS even under `FORCE ROW LEVEL SECURITY`. Always connect with the `memshield_app` role (or an equivalent `NOSUPERUSER NOBYPASSRLS` role), and never with `postgres`.
- **Caller identity must be bound by the application layer.** `memshield_app` can call `set_config` itself, so a compromised application process holding the database credentials can claim any identity. Keep identity binding inside this service, take `user_id` from the authenticated ADK session (never from prompts or tool arguments), and keep database credentials out of agent-reachable code paths.
- **Tenant and clearance come from service config, not from the ADK session.** `search_memory` receives only `app_name` / `user_id` from ADK, so run one service instance per tenant and clearance tier (or per `Runner`).
- **ANN indexes and RLS.** The schema ships without a vector index; it has a B-tree on `(app_name, tenant_id, user_id)` and exact distance. If you add HNSW/IVFFlat, RLS filters rows *after* the index scan and can return fewer than `top_k` rows. Use pgvector ≥ 0.8 iterative scans (`SET hnsw.iterative_scan = relaxed_order`) and benchmark recall at your scale.
- **Benchmark-only table.** `sql/02_benchmark_baseline.sql` creates an intentionally unprotected table for tests and benchmarks. **Do not apply it in production.**
- **Latency on Docker Desktop is noisy.** Latency figures were measured on Docker Desktop, and p95 values mostly reflect host scheduling jitter. The benchmark does not measure behaviour at 100k+ rows.
- **Platform coverage**: tested on Windows 11 with Docker Desktop (Linux containers). Native installs on Linux/macOS have not been tested in this submission.

---

## Security & Privacy Considerations

- **Secrets handling**:
  - The only credential is the PostgreSQL DSN, read from `MEMSHIELD_DB_DSN` or passed in `MemShieldConfig`; `.env` is git-ignored.
  - The passwords in `docker-compose.yml` and `sql/01_schema.sql` (`memshield_pass`, `postgres_admin_pass`) are **local development defaults**. Rotate them before any shared or production use.
- **Data privacy**:
  - Memory content and embeddings stay in your PostgreSQL instance, and embeddings are computed locally, so nothing is sent to third parties.
  - The FastEmbed model is downloaded once from Hugging Face.
  - All test, benchmark and example data is synthetic.
- **Safety**:
  - The library executes no shell commands and no generated code.
  - All SQL values are bound parameters. The only interpolated identifier (`table_name`) is validated against a strict regex.
  - Ownership columns always come from call arguments and config, never from caller-supplied metadata.

---

## Future Improvements

- [ ] Add an optional HNSW index profile with pgvector ≥ 0.8 iterative scans, and benchmark recall under RLS at 100k+ rows.
- [ ] Derive `tenant_id` / `agent_clearance` from ADK session state so one service instance can serve many tenants.
- [ ] Add an async (`psycopg.AsyncConnection`) code path in place of `asyncio.to_thread`.
- [ ] Add optional write-approval / provenance hooks for `tenant_shared` memories.
- [ ] Add a GitHub Actions workflow that runs the integration suite against `pgvector:pg16`.

---

## License

This subproject is licensed under the **Apache License 2.0**; see [`LICENSE`](./LICENSE). Copyright 2026 [Aalishan](https://github.com/aalishan001). PyPI: [`adk-memshield`](https://pypi.org/project/adk-memshield/). Standalone repository: [aalishan001/adk-memshield](https://github.com/aalishan001/adk-memshield).
