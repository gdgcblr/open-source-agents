import json
import pytest
from scanner import ScanError, parse_semgrep_json, scan_project

def test_parse_semgrep_finding():
    raw = json.dumps({"results": [{"check_id": "python.lang.security.eval", "path": "app.py",
        "start": {"line": 7, "col": 3}, "extra": {"message": "Avoid eval", "severity": "ERROR"}}]})
    findings = parse_semgrep_json(raw)
    assert len(findings) == 1
    assert findings[0].path == "app.py" and findings[0].line == 7
    assert findings[0].severity == "ERROR"

def test_malformed_json():
    with pytest.raises(ScanError, match="malformed JSON"):
        parse_semgrep_json("{")

def test_invalid_target(tmp_path):
    with pytest.raises(ScanError, match="existing directory"):
        scan_project(tmp_path / "missing")

def test_mock_scan_is_offline(tmp_path):
    findings = scan_project(tmp_path, mock=True)
    assert findings and findings[0].rule_id == "MOCK.demo-rule"
