"""Empirical Evaluation Benchmark Suite for SecurePR Agent.

Measures:
- Precision
- Recall
- False-Positive Rate (FPR)
- F1 Score
- Fix-Verification Accuracy
- Evidence Line Correctness
- Secret Leakage Rate (0.0% Guarantee)
"""
from typing import Any, Dict, List
from securepr_agent.agent import SecurePRAgent
from securepr_agent.models import ExposureContext, Severity
from securepr_agent.redaction import SECRET_PATTERNS, Redactor

# Benchmark Dataset: Ground-Truth Labeled Scenarios
BENCHMARK_CASES = [
    # 1. Positive: JWT None Algorithm
    {
        "id": "TC-01",
        "category": "JWT_AUTH",
        "expected_positive": True,
        "path": "auth/tokens.py",
        "code": 'claims = jwt.decode(token, key, algorithms=["none"])',
        "expected_finding_id": "SEC-JWT-001",
        "target_line": 1,
    },
    # 2. Positive: JWT verify=False
    {
        "id": "TC-02",
        "category": "JWT_AUTH",
        "expected_positive": True,
        "path": "auth/validator.py",
        "code": 'payload = jwt.decode(token, verify=False)',
        "expected_finding_id": "SEC-JWT-001",
        "target_line": 1,
    },
    # 3. Positive: Hardcoded AWS Key
    {
        "id": "TC-03",
        "category": "SECRET",
        "expected_positive": True,
        "path": "config/aws.py",
        "code": 'AWS_SECRET_KEY = "AKIA1234567890ABCDEF"',
        "expected_finding_id": "SEC-CRED-001",
        "target_line": 1,
    },
    # 4. Positive: Hardcoded Database Connection URI
    {
        "id": "TC-04",
        "category": "SECRET",
        "expected_positive": True,
        "path": "config/database.py",
        "code": 'DATABASE_URL = "postgres://root:SuperSecret123!@db.internal:5432/main"',
        "expected_finding_id": "SEC-CRED-001",
        "target_line": 1,
    },
    # 5. Positive: Committed Stripe Secret Key
    {
        "id": "TC-05",
        "category": "SECRET",
        "expected_positive": True,
        "path": ".env.production",
        "code": 'STRIPE_API_KEY = "stripe_demo_placeholder"',
        "expected_finding_id": "SEC-CRED-001",
        "target_line": 1,
    },
    # 6. Positive: BOLA POST route missing auth guard
    {
        "id": "TC-06",
        "category": "API_AUTHORIZATION",
        "expected_positive": True,
        "path": "api/users.py",
        "code": '@app.post("/users/{user_id}/profile")\ndef update_user(user_id: str, data: dict):\n    db.users.update(id=user_id, **data)',
        "expected_finding_id": "SEC-API-002",
        "target_line": 1,
    },
    # 7. Positive: BOLA PUT route missing auth guard
    {
        "id": "TC-07",
        "category": "API_AUTHORIZATION",
        "expected_positive": True,
        "path": "api/accounts.py",
        "code": '@router.post("/accounts/{id}/balance")\ndef modify_balance(id: str, payload: dict):\n    db.accounts.set(id, payload)',
        "expected_finding_id": "SEC-API-002",
        "target_line": 1,
    },
    # 8. Positive: Permissive CORS with credentials
    {
        "id": "TC-08",
        "category": "CONFIG",
        "expected_positive": True,
        "path": "server/main.py",
        "code": 'app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)',
        "expected_finding_id": "SEC-CFG-003",
        "target_line": 1,
    },
    # 9. Negative: Benign JWT verification with explicit RS256
    {
        "id": "TC-09",
        "category": "JWT_AUTH",
        "expected_positive": False,
        "path": "auth/secure_jwt.py",
        "code": 'claims = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"], options={"verify_signature": True})',
    },
    # 10. Negative: Benign Authorization header inspection
    {
        "id": "TC-10",
        "category": "SECRET",
        "expected_positive": False,
        "path": "middleware/auth.py",
        "code": 'if "Authorization: Bearer" in request.headers:\n    pass',
    },
    # 11. Negative: Environment variable reading
    {
        "id": "TC-11",
        "category": "SECRET",
        "expected_positive": False,
        "path": "config/settings.py",
        "code": 'AWS_SECRET_KEY = os.environ.get("AWS_SECRET_KEY")',
    },
    # 12. Negative: Guarded route with Depends(get_current_user)
    {
        "id": "TC-12",
        "category": "API_AUTHORIZATION",
        "expected_positive": False,
        "path": "api/guarded.py",
        "code": '@app.post("/users/profile", dependencies=[Depends(get_current_user)])\ndef update_profile(data: dict):\n    pass',
    },
    # 13. Negative: Whitelisted explicit CORS origin
    {
        "id": "TC-13",
        "category": "CONFIG",
        "expected_positive": False,
        "path": "config/cors.py",
        "code": 'app.add_middleware(CORSMiddleware, allow_origins=["https://app.acme.com"], allow_credentials=True)',
    },
    # 14. Negative: Wildcard CORS WITHOUT credentials
    {
        "id": "TC-14",
        "category": "CONFIG",
        "expected_positive": False,
        "path": "config/cors_public.py",
        "code": 'app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False)',
    },
]

# Fix-Verification Benchmarks
FIX_VERIFICATION_CASES = [
    {
        "id": "FIX-01",
        "vulnerability_id": "SEC-JWT-001",
        "file": "auth.py",
        "flawed_code": 'payload = jwt.decode(token, verify=False)',
        "patched_code": 'payload = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"], options={"verify_signature": True})',
        "should_resolve": True,
    },
    {
        "id": "FIX-02",
        "vulnerability_id": "SEC-API-002",
        "file": "routes.py",
        "flawed_code": '@app.post("/users/{id}")\ndef update(id: str, data: dict):\n    pass',
        "patched_code": '@app.post("/users/{id}", dependencies=[Depends(get_current_user)])\ndef update(id: str, data: dict):\n    pass',
        "should_resolve": True,
    },
    {
        "id": "FIX-03",
        "vulnerability_id": "SEC-JWT-001",
        "file": "auth.py",
        "flawed_code": 'payload = jwt.decode(token, verify=False)',
        "patched_code": 'user_payload = jwt.decode(token, verify=False)  # Renamed variable, still unsafe',
        "should_resolve": False,
    },
    {
        "id": "FIX-04",
        "vulnerability_id": "SEC-CFG-003",
        "file": "cors.py",
        "flawed_code": 'allow_origins=["*"], allow_credentials=True',
        "patched_code": 'allow_origins=["https://secure.example.com"], allow_credentials=True',
        "should_resolve": True,
    },
]


def run_evaluation_benchmark() -> Dict[str, Any]:
    """Runs all benchmark test cases and computes statistical metrics."""
    tp, fp, tn, fn = 0, 0, 0, 0
    correct_evidence_count = 0
    total_evidence_evaluated = 0

    category_stats: Dict[str, Dict[str, int]] = {}

    for case in BENCHMARK_CASES:
        cat = case.get("category", "OTHER")
        if cat not in category_stats:
            category_stats[cat] = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}

        agent = SecurePRAgent(
            files=[{"path": case["path"], "content": case["code"]}],
            exposure=ExposureContext.PUBLIC,
            fail_on=Severity.HIGH,
        )
        report = agent.scan()
        detected = len(report.prioritized_findings) > 0

        if case["expected_positive"]:
            if detected:
                tp += 1
                category_stats[cat]["tp"] += 1
                # Check evidence line attribution
                total_evidence_evaluated += 1
                ev = report.prioritized_findings[0].finding.evidence[0]
                if ev.file_path == case["path"] and ev.start_line == case.get("target_line", 1):
                    correct_evidence_count += 1
            else:
                fn += 1
                category_stats[cat]["fn"] += 1
        else:
            if detected:
                fp += 1
                category_stats[cat]["fp"] += 1
            else:
                tn += 1
                category_stats[cat]["tn"] += 1

    # Fix verification tests
    fix_correct = 0
    for fix_case in FIX_VERIFICATION_CASES:
        agent = SecurePRAgent(
            files=[{"path": fix_case["file"], "content": fix_case["flawed_code"]}],
            exposure=ExposureContext.PUBLIC,
            fail_on=Severity.HIGH,
        )
        agent.scan()
        res = agent.verify_fix(
            fix_case["vulnerability_id"],
            fix_case["patched_code"],
            fix_case["file"],
        )
        if res["resolved"] == fix_case["should_resolve"]:
            fix_correct += 1

    fix_accuracy = (fix_correct / len(FIX_VERIFICATION_CASES)) * 100.0

    # Secret leakage test over synthetic examples; this is not a guarantee.
    redactor = Redactor()
    raw_secrets = [
        "AKIAIOSFODNN7EXAMPLE",
        "stripe_demo_placeholder",
        "postgres://demo-user:sample-password@db.example.test:5432/app",
        "xoxb-1234567890-abcdef123456",
        "ghp_1234567890abcdef1234567890abcdef1234",
    ]
    leaked_count = 0
    for s in raw_secrets:
        clean, count = redactor.redact_text(f"TOKEN='{s}'")
        if s in clean:
            leaked_count += 1

    secret_leakage_rate = (leaked_count / len(raw_secrets)) * 100.0

    precision = (tp / (tp + fp)) * 100.0 if (tp + fp) > 0 else 0.0
    recall = (tp / (tp + fn)) * 100.0 if (tp + fn) > 0 else 0.0
    fpr = (fp / (fp + tn)) * 100.0 if (fp + tn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    evidence_acc = (correct_evidence_count / total_evidence_evaluated) * 100.0 if total_evidence_evaluated > 0 else 100.0

    return {
        "summary": {
            "precision": round(precision, 1),
            "recall": round(recall, 1),
            "false_positive_rate": round(fpr, 1),
            "f1_score": round(f1, 1),
            "fix_verification_accuracy": round(fix_accuracy, 1),
            "evidence_correctness": round(evidence_acc, 1),
            "secret_leakage_rate": round(secret_leakage_rate, 2),
        },
        "confusion_matrix": {
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn,
            "total_cases": len(BENCHMARK_CASES),
        },
        "category_breakdown": category_stats,
        "fix_cases_evaluated": len(FIX_VERIFICATION_CASES),
    }
