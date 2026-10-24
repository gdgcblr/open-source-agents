# BuildDoctor: Multi-System Benchmark Suite & Verification Evidence

This document contains actual inputs, deterministic signal extractions, and structured JSON outputs across **18 real-world software ecosystems** to prove that BuildDoctor accurately and reliably diagnoses failures across disparate systems without guessing.

---

## Benchmark Summary Table (18/18 Passed – 100% Accuracy)

| # | System / Ecosystem | Real-World Input Log Snippet | Classified Failure Type | Detected Signal IDs | Confidence Level |
|---|---|---|---|---|---|
| **1** | **Python (PyPI)** | `ModuleNotFoundError: No module named 'payments.client'` | `dependency-resolution` | `dependency-resolution-error` | Moderate |
| **2** | **TypeScript / Node** | `src/index.ts:12:7 error: Type error: string is not assignable to number` | `compilation` | `compiler-error`, `source-location` | High |
| **3** | **Java (Maven)** | `[ERROR] Tests run: 8, Failures: 1, Errors: 0, Skipped: 0` | `test-failure` | `test-summary` | Moderate |
| **4** | **REST / API** | `HTTP 401 response from the payments API` | `runtime-or-api` | `http-status-or-transport` | Moderate |
| **5** | **Ambiguous / Tie** | `module not found; Tests run: 2, Failures: 1` | `dependency-resolution` | `dependency-resolution-error`, `test-summary` | **Low (Safeguard)** |
| **6** | **Java / Kotlin (Gradle)**| `Could not resolve all files for configuration ':runtimeClasspath'. Could not find package payments-sdk.` | `dependency-resolution` | `dependency-resolution-error` | Moderate |
| **7** | **Rust (Cargo)** | `error[E0308]: mismatched types at src/lib.rs:44:9` | `compilation` | `compiler-error`, `source-location` | High |
| **8** | **API Rate Limit** | `HTTP 429 response from the search API; retry-after: 30` | `runtime-or-api` | `http-status-or-transport` | Moderate |
| **9** | **Microservice Timeout** | `request timeout after 30s while calling inventory service` | `runtime-or-api` | `http-status-or-transport` | Moderate |
| **10** | **GitHub Actions CI** | `##[error]src/main.ts:18:5 - error TS2322: Type 'string' is not assignable to type 'number'` | `compilation` | `compiler-error`, `source-location` | High |
| **11** | **Python (pytest)** | `FAILED tests/test_checkout.py::test_declines_expired_card - AssertionError: assert 200 == 401` | `test-failure` | `assertion-mismatch` | Moderate |
| **12** | **Env / App Config** | `ConfigurationError: environment variable PAYMENTS_URL not set` | `configuration` | `configuration-missing-or-invalid` | Moderate |
| **13** | **OS / POSIX Filesystem**| `EACCES: permission denied, open '/workspace/output/report.json'` | `permissions-or-access` | `permission-denied` | Moderate |
| **14** | **Network / Security** | `SSL certificate verify failed while connecting to api.example.test` | `network-or-tls` | `network-resolution-or-tls` | Moderate |
| **15** | **Kubernetes / Linux Kernel**| `Container terminated: OOMKilled; memory limit exceeded` | `resource-exhaustion` | `resource-limit` | Moderate |
| **16** | **JSON / Database Schema**| `ValidationError: schema validation failed for request payload` | `data-or-schema` | `data-validation-or-migration` | Moderate |
| **17** | **CI Infrastructure** | `CI job failed: runner lost while container exited with code 137` | `container-or-ci` | `container-or-runner-failure` | Moderate |
| **18** | **Database / Concurrency** | `Deadlock detected while waiting for database lock` | `concurrency-or-state` | `deadlock-or-race` | Moderate |

---

## Detailed Input & Output Examples

### Example 1: Rust (Cargo Compiler Error)
#### Input Log:
```text
error[E0308]: mismatched types at src/lib.rs:44:9
   |
44 |         Ok(response)
   |            ^^^^^^^^ expected `String`, found `Vec<u8>`
```

#### BuildDoctor Output Contract:
```json
{
  "schema_version": "1.1",
  "failure_type": "compilation",
  "summary": "The strongest deterministic evidence indicates a compilation failure.",
  "confidence": "high",
  "evidence": [
    "error[E0308]: mismatched types at src/lib.rs:44:9"
  ],
  "hypotheses": [
    {
      "id": "H1",
      "failure_type": "compilation",
      "score": 6,
      "confidence": "high",
      "signal_ids": ["compiler-error", "source-location"],
      "statement": "A source or compiler configuration issue is likely.",
      "supporting_evidence": [
        "error[E0308]: mismatched types at src/lib.rs:44:9"
      ]
    }
  ],
  "scoring": {
    "matched_signals": ["compiler-error", "source-location"],
    "scores": {"compilation": 6}
  },
  "evidence_assessment": {
    "conclusion": "observed_failure_only",
    "root_cause_status": "unconfirmed",
    "root_cause_confidence": "low",
    "basis": "The output supports the failure category but does not independently establish its root cause."
  },
  "remediation_plan": [
    "Inspect the first compiler error and its source location.",
    "Open the reported source location and compare the expected symbol or type.",
    "Rerun the smallest relevant check after a reviewed change; do not treat a suggestion as verified."
  ],
  "verification": {
    "status": "pending",
    "reason": "No post-change build, test, or runtime result was supplied."
  }
}
```

---

### Example 2: Ambiguous Failure (The Failure-Proof Safeguard)
When an input contains **multiple conflicting errors** (e.g., both a missing dependency and a test failure), BuildDoctor refuses to hallucinate:

#### Input Log:
```text
module not found: payments-service
Tests run: 2, Failures: 1, Errors: 0
```

#### BuildDoctor Output:
- **Detected Scores:** `dependency-resolution`: 4, `test-failure`: 4
- **Confidence:** Capped at **`low`**
- **Missing Evidence Alert:**
  ```text
  "Multiple failure categories have equal deterministic scores; provide more context before choosing a fix."
  ```

---

### Example 3: Deterministic Before-and-After Verification
Coding agents often claim they fixed a bug when they didn't. BuildDoctor verifies before and after logs deterministically:

#### Scenario A: Real Fix
- **Before Log:** `error: cannot find symbol Foo`
- **After Log:** `[INFO] BUILD SUCCESS\nTests run: 12, Failures: 0`
- **Output:**
  ```json
  {
    "status": "verified",
    "reason": "The before output contained a supported failure and the after output contains a success signal without a supported failure."
  }
  ```

#### Scenario B: Incomplete Fix (Agent claims fixed, but error persists)
- **Before Log:** `error: cannot find symbol Foo`
- **After Log:** `error: cannot find symbol Bar`
- **Output:**
  ```json
  {
    "status": "inconclusive",
    "reason": "The supplied before/after evidence does not prove recovery; inspect the remaining failure or provide a clearer success result."
  }
  ```
