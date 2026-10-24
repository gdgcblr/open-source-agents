# BlastRadius

> An autonomous Change Impact Analysis Agent for Java microservices that inspects Git diffs, maps affected methods and direct callers, recommends test execution targets, and generates structured Markdown blast radius reports.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: When developers update Java microservices, subtle code changes often ripple into dependent methods, controllers, and services. Running entire integration test suites for every commit is slow and computationally expensive, while cherry-picking tests manually is error-prone and leads to untested regression gaps in production.
- **Intended Users**: Software engineers, tech leads, CI/CD DevOps engineers, and PR code reviewers who want immediate, transparent visibility into the exact blast radius of a pull request before merging or triggering extensive test pipelines.

### Key Features
- **Git Diff & Hunk Parsing**: Parses unified Git diffs (`.diff` files or `stdin`) and precisely maps modified line numbers to enclosing Java classes and methods.
- **Direct Caller Discovery**: Statically scans the target Java repository to locate all direct production and test invocation sites without requiring bytecode compilation or heavy IDE environments.
- **Test Impact Recommendation**: Prioritizes test execution targets into High, Medium, and Low tiers based on direct test calls, secondary caller test coverage, and conventional class-matching suites.
- **Automatic Maven Command Synthesis**: Synthesizes ready-to-run selective test commands (e.g., `mvn test -Dtest=OrderServiceTest#testCreateOrderSuccess`).
- **Test Coverage Gap Detection**: Explicitly identifies modified methods that lack discoverable automated test coverage.
- **Model Context Protocol (MCP) Server**: Provides a built-in JSON-RPC 2.0 MCP server enabling AI assistants (Cursor, Claude Desktop, Antigravity) to query blast radius tools interactively.
- **Zero-Dependency Reproducibility**: Implemented 100% in pure Python; requires no JDK, Maven, or JVM installation to analyze Java code or run the agent.
- **Honest Limitations & Evidence**: Every report includes exact line-number evidence and clearly discloses architectural boundaries (polymorphism, reflection, and multi-repo RPCs).

---

## Technical Stack

- **Language & Runtime**: Python 3.9+ (tested on Python 3.9.6)
- **Agent Framework & Protocols**: Native Python Change Impact Engine + Model Context Protocol (MCP) Server (JSON-RPC 2.0)
- **Models / Reasoning Engine**: 100% deterministic offline heuristic risk engine by default (zero paid API keys needed); optional semantic reasoning enrichment via Google Gemini (`GEMINI_API_KEY`) or OpenAI (`OPENAI_API_KEY`)
- **External Dependencies**: None required for core execution (Python standard library); `pytest` supported for test runner convenience.

---

## Architecture & Data Flow

```
[Git Diff (.diff / stdin)] + [Target Java Microservice Repo]
                          │
                          ▼
             ┌─────────────────────────┐
             │       DiffParser        │  Extracts modified files & line intervals
             └────────────┬────────────┘
                          │
                          ▼
             ┌─────────────────────────┐
             │      JavaAnalyzer       │  Maps line intervals to Java method signatures
             └────────────┬────────────┘
                          │
                          ▼
             ┌─────────────────────────┐
             │     Caller Discovery    │  Finds direct production & test call-sites
             └────────────┬────────────┘
                          │
                          ▼
             ┌─────────────────────────┐
             │     TestRecommender     │  Ranks test targets (Direct Test > Caller Test)
             └────────────┬────────────┘
                          │
                          ▼
             ┌─────────────────────────┐
             │    BlastRadiusAgent     │  Computes risk score & builds ImpactReport
             └────────────┬────────────┘
                          │
                          ▼
            [GitHub-Flavored Markdown Report]
```

---

## Prerequisites

Before running BlastRadius, ensure you have:
- **Python 3.9+** installed (`python3 --version`).
- Standard Python package manager (`pip`).
- *(Note: You do **not** need Java, Maven, or Gradle installed to execute BlastRadius, run the demo, or run automated tests.)*

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/blast-radius
   ```

2. **Set up virtual environment (optional but recommended):**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables (Optional):**
   ```bash
   cp .env.example .env
   ```
   *(No API keys are required for standard offline operation.)*

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No | *None* | API key for Google Gemini semantic enrichment (requires `--enable-llm` or `BLAST_RADIUS_ENABLE_LLM=true`) |
| `BLAST_RADIUS_ENABLE_LLM` | No | `false` | Set to `true` to opt-in to sending diff data to Gemini API |
| `MODEL_NAME` | No | `gemini-2.5-flash` | LLM model identifier when using LLM mode |
| `LOG_LEVEL` | No | `info` | Logging verbosity (`debug`, `info`, `warn`, `error`) |

---

## How to Run

### 1. Run the Reproducible Demos

#### A. Single Microservice Demo
```bash
python3 demo.py
```
This analyzes the bundled sample order microservice and outputs a complete impact report to the console and to `fixtures/demo_output.md`.

#### B. Multi-Microservice Cross-Service Orchestrator Demo
```bash
python3 demo_orchestrator.py
```
Simulates a Pull Request raised on `payment-service`. The **Multi-Service Orchestrator** broadcasts the contract changes to neighbouring service agents (`order-service` and `inventory-service`), aggregates their risk assessments, and generates a cross-service impact matrix saved to `fixtures/multi_service_demo_output.md`.

### 2. Run via CLI Against Custom Diffs and Repositories

```bash
# Single-Service: Analyze a diff file against a local Java repository
python3 -m blast_radius.cli \
  --diff fixtures/changes/payment_logic_update.diff \
  --repo fixtures/sample_repo

# Multi-Service: Cross-service impact across an ecosystem of microservices
python3 -m blast_radius.cli \
  --diff fixtures/changes/payment_service_pr.diff \
  --services-dir fixtures/microservices \
  --target-service payment-service

# Save output directly to a Markdown report
python3 -m blast_radius.cli \
  --diff fixtures/changes/payment_logic_update.diff \
  --repo fixtures/sample_repo \
  --output impact_report.md

# Pipe git diff directly from a git repository
git diff HEAD~1 | python3 -m blast_radius.cli --diff - --repo /path/to/my-java-service

# Emit structured JSON output for CI/CD pipelines
python3 -m blast_radius.cli \
  --diff fixtures/changes/payment_logic_update.diff \
  --repo fixtures/sample_repo \
  --format json
```

### 3. Run as a Model Context Protocol (MCP) Server
BlastRadius can run as an MCP server over stdio to empower AI assistants (Claude Desktop, Cursor, Antigravity):

```bash
# Start MCP server
python3 -m blast_radius.mcp_server
```

#### Connecting to Claude Desktop / Cursor (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "blast-radius": {
      "command": "python3",
      "args": ["-m", "blast_radius.mcp_server"],
      "cwd": "/absolute/path/to/agents/blast-radius"
    }
  }
}
```
Available MCP Tools:
- `analyze_change_impact`: Analyzes a git diff against a Java repository and returns risk metrics, callers, and test targets.
- `find_method_callers`: Finds all direct callers of a Java method across the project.
- `recommend_test_targets`: Returns prioritized test execution commands for a git diff.

---

## Example Input & Output

### Example Input (Diff)
```diff
--- a/src/main/java/com/example/order/PaymentClient.java
+++ b/src/main/java/com/example/order/PaymentClient.java
@@ -8,4 +8,7 @@ public class PaymentClient {
         if (currency == null || currency.isBlank()) {
             throw new IllegalArgumentException("Currency must not be empty");
         }
+        if (amount > 10000.0 && !"USD".equalsIgnoreCase(currency)) {
+            throw new IllegalArgumentException("High-value transactions must be denominated in USD");
+        }
         // Simulated HTTP payment gateway invocation
```

### Example Generated Impact Report
```markdown
# 💥 BlastRadius: Change Impact Analysis Report

> Automated change impact assessment for target repository: `fixtures/sample_repo`

## Executive Summary
- **Overall Risk Rating**: 🟠 **HIGH RISK** (Score: `70/100`)
- **Changed Java Methods**: `1`
- **Discovered Direct Callers**: `1` (1 production, 0 tests)
- **Recommended Tests to Run**: `1`
- **Test Coverage Gaps**: `1` uncovered method(s)

## 🔍 Changed Methods & Direct Impact
| Modified Class | Method Signature | Lines | Return Type | Modifiers |
| :--- | :--- | :--- | :--- | :--- |
| `PaymentClient` | `processPayment(String orderId, double amount, String currency)` | `L5-L14` | `String` | `public` |

## 🌐 Discovered Direct Callers
| Target Method | Caller Location | Type | Invocations Code Snippet |
| :--- | :--- | :--- | :--- |
| `processPayment` | `src/main/java/com/example/order/OrderService.java#L13` (`OrderService#createOrder`) | ⚙️ Production | `String txId = paymentClient.processPayment("ORD-1", totalAmount, "USD");` |

## 🧪 Recommended Test Execution Plan
Execute these test targets to validate your changes before deployment:

| Priority | Test Target | Enclosing Test Method | Rationale |
| :--- | :--- | :--- | :--- |
| 🔴 High | `src/test/java/com/example/order/OrderServiceTest.java` | `testCreateOrderSuccess` | Tests direct caller `OrderService#createOrder` (invoked at line 12) |

### Suggested Maven Test Command
```bash
mvn test -Dtest=OrderServiceTest#testCreateOrderSuccess
```
```

---

## How to Test

BlastRadius includes an automated test suite verifying diff parsing, Java structural analysis, caller discovery, and end-to-end integration:

```bash
# Using standard library unittest (0 external packages needed):
python3 -m unittest discover -s tests

# Or using pytest (if installed):
pytest tests/
```

All 19 automated test cases execute offline in under 0.2 seconds.

---

## Known Limitations

To maintain technical honesty and predictable scope, note the following boundaries:
1. **Polymorphic Dispatch**: Invocations made via shared interfaces with multiple implementations are matched by method name and signature; full bytecode classpath resolution is required to disambiguate dynamic runtime implementations.
2. **Framework Reflection & Dependency Injection**: Spring Bean autowiring (`@Autowired`, `@Resource`, `@Inject`), Spring event publishers (`ApplicationEventPublisher`), and reflective invocations (`Method.invoke`) are not tracked as direct lexical invocations.
3. **External Microservice Boundaries**: Remote RPC, REST endpoints, and messaging consumers (Kafka, RabbitMQ) across external microservice repositories cannot be discovered from local source code alone.
4. **Scope**: Analysis is bounded to Java source files (`.java`) in the specified repository root.

---

## Security & Privacy Considerations

- **Secrets Handling**: Zero credentials, tokens, or environment files are tracked. All configuration is loaded from sanitized environment variables or `.env`.
- **Local & Offline Execution**: By default, BlastRadius runs 100% locally on your machine with zero external network calls or telemetry. Code diffs are never sent to external servers unless an explicit LLM API key is configured.
- **Safe Static Analysis**: BlastRadius operates in read-only mode over the target repository and does not execute compiled Java bytecode or arbitrary scripts.

---

## Future Improvements

- [ ] Add support for Kotlin source files (`.kt`) in microservices.
- [ ] Integration with GitHub Actions PR comments via automated bot workflow.
- [ ] Parse Spring `@RestController` request mappings to map changes directly to public HTTP endpoints.
- [ ] Multi-module Maven project boundary visualization.

---

## License

This project is contributed under the repository's open-source [MIT License](../../LICENSE) &copy; 2026 GDG Cloud Bengaluru Community.
