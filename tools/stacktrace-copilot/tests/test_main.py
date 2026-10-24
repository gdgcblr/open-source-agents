import json
import subprocess
import sys
from pathlib import Path

from main import analyze_text, extract_error, extract_frames


def test_extract_python_exception():
    lines = [
        'Traceback (most recent call last):',
        '  File "/app/service.py", line 42, in process_request',
        "AttributeError: 'NoneType' object has no attribute 'profile'",
    ]

    error = extract_error(lines)

    assert error["type"] == "AttributeError"
    assert "NoneType" in error["message"]


def test_extract_python_stack_frame():
    lines = [
        '  File "/app/service.py", line 42, in process_request'
    ]

    frames = extract_frames(lines)

    assert len(frames) == 1
    assert frames[0]["file"] == "/app/service.py"
    assert frames[0]["line"] == 42
    assert frames[0]["function"] == "process_request"


def test_extract_javascript_stack_frame():
    lines = [
        "    at processRequest (/app/service.js:12:8)"
    ]

    frames = extract_frames(lines)

    assert len(frames) == 1
    assert frames[0]["file"] == "/app/service.js"
    assert frames[0]["line"] == 12
    assert frames[0]["column"] == 8
    assert frames[0]["function"] == "processRequest"


def test_unknown_error_is_handled():
    report = analyze_text("Some unrecognized log message")

    assert report["error"]["type"] == "UnknownError"
    assert report["diagnosis"]["confidence"] == "low"
    assert report["verification_steps"]


def test_module_not_found_suggestions():
    report = analyze_text(
        "ModuleNotFoundError: No module named 'requests'"
    )

    assert report["error"]["type"] == "ModuleNotFoundError"
    assert report["diagnosis"]["suggestions"]
    assert report["diagnosis"]["confidence"] == "medium"


def test_report_has_expected_structure():
    report = analyze_text("ValueError: invalid value")

    assert report["tool"] == "StackTrace Copilot"
    assert "error" in report
    assert "source_frames" in report
    assert "diagnosis" in report
    assert "verification_steps" in report

    # The report should be serializable as JSON.
    json.dumps(report)


def test_cli_json_output(tmp_path):
    log_file = tmp_path / "error.log"
    log_file.write_text(
        "TypeError: unsupported operation",
        encoding="utf-8",
    )

    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "main.py"),
            "--file",
            str(log_file),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    report = json.loads(result.stdout)
    assert report["error"]["type"] == "TypeError"
