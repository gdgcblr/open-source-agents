# BuildDoctor: Complete System Architecture

> **An Evidence-First Diagnostic Gatekeeper and Verification Companion**  
> Bridging **Google Agent Development Kit (Java 17+)** with the **Model Context Protocol (Python 3.10+)** over secure `stdio`.

---

## 1. High-Level Architecture Diagram

```mermaid
flowchart TB
    subgraph Clients["1. Client & Integration Layer"]
        IDE1["Cursor / VS Code<br>(Cursor MCP, Roo-Code)"]
        IDE2["Claude Desktop<br>(Desktop Assistant)"]
        CLI["BuildDoctor CLI & App<br>(BuildDoctorApplication)"]
        ADKAgent["Google ADK Agent<br>(LlmAgent Runner)"]
        Webhook["Observability Webhook<br>(New Relic, Prometheus, Otel)"]
    end

    subgraph Bridge["2. Cross-Language stdio Transport Bridge"]
        StdioPipe["Standard I/O Streams (JSON-RPC 2.0 / MCP Protocol)<br>Auto-Discovered Python Subprocess (.venv/bin/python)"]
    end

    subgraph MCP["3. Python FastMCP Server Engine (build_doctor_mcp.server)"]
        FastMCP["FastMCP Registry & Session Manager"]
        
        subgraph Tools["11 Specialized Read-Only Tools"]
            T1["analyze_failure"]
            T2["inspect_project"]
            T3["inspect_test_reports"]
            T4["summarize_diagnosis"]
            T5["analyze_alert"]
            T6["inspect_ci_annotations"]
            T7["inspect_api_error"]
            T8["compare_diagnoses"]
            T9["verify_alert_signature"]
            T10["verify_resolution"]
            T11["format_incident_email<br>(Google MCP / Gmail Dispatch)"]
        end
    end

    subgraph Security["4. Defense-in-Depth Security Guardrails"]
        Redact["3-Tier Secret Redaction<br>(Bearer, API Keys, Private Keys)"]
        SymlinkCheck["Path & Directory Containment<br>(_is_safe_path, No Symlink Traversal)"]
        XmlGuard["Safe XML Parsing<br>(defusedxml: No XXE / Billion Laughs)"]
        InjectGuard["Prompt Injection Neutralization<br>(ignore instructions -> [UNTRUSTED_TEXT])"]
        OutputCap["Aggregate Output Limits<br>(_bounded_output, MAX_OUTPUT_CHARS)"]
    end

    subgraph Engines["5. Deterministic Diagnostic & Verification Engines"]
        Rules["11 Operational Failure Classifiers<br>(Compilation, Dependency, Test, Runtime/API,<br>Config, Permissions, TLS, Resources,<br>Data/Schema, CI/Runner, Concurrency)"]
        Scorer["Deterministic Evidence Scorer<br>(Weights, Tied Confidence Capping)"]
        Verifier["Deterministic Resolution Engine<br>(Pending unless Before/After Success Verified)"]
    end

    Clients --> StdioPipe
    StdioPipe --> FastMCP
    FastMCP --> Tools
    Tools --> Security
    Security --> Engines
```

---

## 2. End-to-End Diagnostic Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer / Coding Agent
    participant Java as Java ADK Application
    participant stdio as stdio Process Bridge
    participant MCP as FastMCP Server
    participant Rules as Deterministic Rules
    participant Project as Workspace Files

    Dev->>Java: Run failure diagnosis (log + projectPath)
    Java->>stdio: Spawn python -m build_doctor_mcp.server
    stdio->>MCP: ClientSession.initialize()
    MCP-->>Java: Discovered 10 Diagnostic Tools
    
    Java->>stdio: call_tool("summarize_diagnosis", {log, project_path})
    stdio->>MCP: Dispatch tool call
    
    rect rgb(240, 248, 255)
        Note over MCP,Security: Security Boundary & Sanitization
        MCP->>MCP: Redact secrets (Bearer tokens, API keys, private keys)
        MCP->>MCP: Sanitize prompt injection -> [UNTRUSTED_TEXT]
    end

    MCP->>Rules: Score failure patterns against 11 categories
    Rules-->>MCP: Hypotheses, weights, confidence, missing evidence
    
    MCP->>Project: Read root manifests (pom.xml, package.json, etc.)
    Note over MCP,Project: Check _is_safe_path: Reject directory symlinks
    Project-->>MCP: Bounded manifest content
    
    MCP->>Project: Inspect test reports (surefire-reports/*.xml)
    Note over MCP,Project: Parse with defusedxml (No external entities)
    Project-->>MCP: Parsed test counts & failing test names

    MCP-->>stdio: Structured JSON Diagnostic Report
    stdio-->>Java: Map deserialization (RxJava Single)
    Java-->>Dev: Print structured report (verification_status: PENDING)
```

---

## 3. Core Architectural Layers

### Layer 1: Client & Host Integrations
- **Standalone CLI:** `BuildDoctorCli` runs 100% offline with zero dependencies.
- **Java ADK Runner:** `BuildDoctorApplication` initializes the ADK `LlmAgent`, manages stdio subprocess startup, dynamic tool discovery, and deterministic cleanup in a `finally` block.
- **MCP Client Presets:** Plug-and-play presets configured for Cursor (`cursor-mcp.json`), VS Code (`vscode-mcp.json`), and Claude Desktop (`claude-desktop.json`).

### Layer 2: Cross-Language Stdio Bridge
- **Transport:** Standard input/output pipes with JSON-RPC 2.0 framing.
- **Zero Configuration:** Automatically locates `.venv/bin/python` or reads `BUILD_DOCTOR_PYTHON`.
- **Environment Isolation:** Configures `PYTHONPATH` dynamically to mount MCP server sources.

### Layer 3: The 11 MCP Diagnostic Tools
| Tool Name | Responsibility | Safety Guarantee |
|---|---|---|
| `analyze_failure` | Scores deterministic failure signals from raw logs or cURL outputs | Pure text analysis, no side effects |
| `inspect_project` | Extracts root manifests (Maven, Gradle, npm, PyPI, Cargo, Go) | Only allowlisted root manifests; no recursion |
| `inspect_test_reports` | Extracts test suite failures, counts, and error messages | Parsed with `defusedxml`; symlink directories blocked |
| `summarize_diagnosis` | Combines failure analysis, project manifests, and test health | Unified response; aggregate output capped |
| `analyze_alert` | Normalizes New Relic, Prometheus, Otel, CubeAPM alerts | Normalization only; no external provider polling |
| `inspect_ci_annotations` | Normalizes GitHub/GitLab/Azure error and notice annotations | Text extraction; zero CI job triggers |
| `inspect_api_error` | Standardizes HTTP status, correlation ID, and retry-after | Sanitized envelope inspection; zero network retry |
| `compare_diagnoses` | Compares pre/post structured diagnosis without retaining raw logs | Zero raw log storage; private comparison |
| `verify_alert_signature` | Validates HMAC-SHA256 signatures before webhook processing | Fails closed if webhook secret is unset |
| `verify_resolution` | Compares before/after logs to confirm resolution | **Refuses** to mark verified without success proof |
| `format_incident_email` | Generates Google Workspace / Gmail MCP dispatch envelopes | Email formatting only; zero unauthorized network calls |

### Layer 4: The 11 Failure Signal Engines
1. **Compilation (`compilation`)**: Syntax, type mismatches, missing symbols, TypeScript/Rust/javac errors.
2. **Dependency Resolution (`dependency-resolution`)**: Missing modules, repository 404s, lockfile mismatches.
3. **Test Failures (`test-failure`)**: Assertion errors, expected vs. actual mismatches, test count summaries.
4. **Runtime & API (`runtime-or-api`)**: HTTP 4xx/5xx status codes, network timeouts, unhandled exceptions.
5. **Configuration (`configuration`)**: Missing environment variables, config parsing errors, KeyError.
6. **Permissions & Access (`permissions-or-access`)**: EACCES, 403 Forbidden, invalid credentials, policy denial.
7. **Network & TLS (`network-or-tls`)**: DNS failures, SSL certificate expiry, TLS handshake errors.
8. **Resource Exhaustion (`resource-exhaustion`)**: OOMKilled, quota exceeded, disk full, open file limits.
9. **Data & Schema (`data-or-schema`)**: JSON deserialization errors, migration failures, schema violations.
10. **Container & CI (`container-or-ci`)**: Docker build errors, CI runner lost, image pull failure.
11. **Concurrency & State (`concurrency-or-state`)**: Deadlocks, race conditions, lock timeouts.

### Layer 5: Defense-in-Depth Security Model
- **Strictly Read-Only:** Zero subprocess execution by tools, zero file writes, zero network calls.
- **Path & Symlink Containment:** Rejects symlinked directories during report discovery and validates path boundaries against `BUILD_DOCTOR_ALLOWED_ROOT`.
- **Safe XML Parsing:** Uses `defusedxml` to neutralize XXE (XML External Entity) and entity expansion attacks.
- **3-Tier Credential Redaction:**
  1. `Authorization: Bearer <token>` -> `Bearer [REDACTED]`
  2. `apiKey: <secret>`, `password: <secret>`, `client_secret` -> `[REDACTED]`
  3. `-----BEGIN PRIVATE KEY----- ... -----END PRIVATE KEY-----` -> `[REDACTED]`
- **Prompt Injection Neutralization:** Sequences like `ignore previous instructions` or `System Message:` are replaced with `[UNTRUSTED_TEXT]`.
- **Aggregate Output Bounding:** Capped at `BUILD_DOCTOR_MAX_OUTPUT_CHARS` to prevent context explosion and Denial-of-Service.

---

## 4. File-to-Architecture Component Map

```
open-source-agents/
├── agents/build-doctor/                         # Java ADK Implementation
│   ├── pom.xml                                  # Maven dependencies (ADK 1.12.0, RxJava 3)
│   ├── src/main/java/.../BuildDoctorApplication # Full ADK-MCP process lifecycle runner
│   ├── src/main/java/.../BuildDoctorAgent       # ADK LlmAgent builder & instructions
│   ├── src/main/java/.../BuildDoctorTools       # Java local fallback tools & security guards
│   ├── src/main/java/.../BuildDoctorEngine      # Deterministic Java classification engine
│   └── src/test/java/.../BuildDoctorMcpIntegrationTest # Live stdio cross-language test suite
│
└── tools/build-doctor-mcp/                      # Python FastMCP Server Implementation
    ├── pyproject.toml                           # Package manifest (FastMCP, defusedxml)
    ├── src/build_doctor_mcp/server.py           # 10 MCP tools, 11 rules, and security guards
    ├── src/build_doctor_mcp/adapters.py         # Provider webhook normalization adapters
    ├── evaluation/run.py                        # 18-case automated evaluation benchmark
    └── tests/test_mcp_protocol.py               # Real stdio protocol test suite
```
