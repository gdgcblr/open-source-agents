import importlib.util
import zipfile
from pathlib import Path


def load_guard():
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_release.py"
    spec = importlib.util.spec_from_file_location("release_guard", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_guard_allows_example_configuration_but_rejects_secret_files_and_paths():
    guard = load_guard()
    assert not guard.forbidden("tool/.env.example")
    assert not guard.forbidden("tool/pulseblr_events_mcp/data/sample_events.json")
    for path in (
        "tool/.env",
        "tool/.env.local",
        "tool/private.key",
        "tool/.venv/pyvenv.cfg",
        "../outside",
        "/absolute",
    ):
        assert guard.forbidden(path)


def test_guard_records_rule_and_filename_without_matching_secret_value():
    guard = load_guard()
    fake_google_key = b"AIza" + b"A" * 35
    problems = []
    guard.inspect_bytes("test-config.txt", fake_google_key, problems)
    assert problems == [("test-config.txt", "google-api-key")]
    assert fake_google_key.decode() not in str(problems)


def test_guard_detects_credentialed_database_uri_without_outputting_values():
    guard = load_guard()
    problems = []
    guard.inspect_bytes(
        "config.txt", b"mongodb+srv://" + b"example:fake-password@host/test", problems
    )
    assert problems == [("config.txt", "mongodb-credentials")]


def test_two_wheels_cannot_substitute_for_one_wheel_and_one_sdist(tmp_path, monkeypatch):
    guard = load_guard()
    monkeypatch.setattr(guard, "PROJECT", tmp_path)
    monkeypatch.setattr(
        guard, "git_lines", lambda *args: [str(tmp_path)] if args[0] == "rev-parse" else []
    )
    (tmp_path / "dist").mkdir()
    for name in ("one.whl", "two.whl"):
        with zipfile.ZipFile(tmp_path / "dist" / name, "w") as wheel:
            wheel.writestr("safe.py", "x = 1")
    _, _, problems = guard.check(scan_archives=True)
    assert ("dist/", "expected-one-wheel-and-one-sdist") in problems
