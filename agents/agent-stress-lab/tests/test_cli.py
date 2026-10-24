import json

from conftest import SCRIPTED_CONFIG

from murphy.cli import main


def test_init_scaffolds_and_refuses_overwrite(tmp_path, capfd):
    assert main(["init", str(tmp_path)]) == 0
    assert (tmp_path / "murphy.yaml").exists() and (tmp_path / "personas" / "example.yaml").exists()
    assert main(["init", str(tmp_path)]) == 2
    assert "refusing to overwrite" in capfd.readouterr().err


def test_init_output_validates(tmp_path, capfd):
    main(["init", str(tmp_path)])
    assert main(["validate", "-c", str(tmp_path / "murphy.yaml")]) == 0
    assert "1 personas × 2 fault scenarios" in capfd.readouterr().out


def test_config_errors_exit_2(tmp_path, capfd):
    (tmp_path / "murphy.yaml").write_text("version: 1\nname: x\n")
    assert main(["validate", "-c", str(tmp_path / "murphy.yaml")]) == 2
    assert "target" in capfd.readouterr().err


def test_run_report_replay_ui_end_to_end(tmp_path, capfd):
    out = tmp_path / "runs"
    code = main(["run", "-c", str(SCRIPTED_CONFIG), "--out", str(out)])
    text = capfd.readouterr().out
    assert code == 1 and "CI FAIL: 1 run(s) labelled 'dup'" in text
    matrix = (out / "latest").resolve()
    for name in ("report.html", "results.json", "report.md", "junit.xml", "project.json"):
        assert (matrix / name).exists(), name

    assert main(["report", str(matrix)]) == 0
    assert main(["replay", str(matrix / "cooperative__timeout"), "--target", "scripted_agents:fixed_policy",
                 "--no-fallback"]) == 0
    assert "PASS" in capfd.readouterr().out
    data = json.loads((matrix / "results.json").read_text())
    assert data["totals"]["runs"] == 2  # replays are attached, not counted as matrix runs

    assert main(["ui", str(out / "latest"), "--no-open"]) == 0
    assert capfd.readouterr().out.strip().endswith("report.html")


def test_run_with_filters_and_enforced_policy_passes_ci(tmp_path):
    out = tmp_path / "runs"
    assert main(["run", "-c", str(SCRIPTED_CONFIG), "--out", str(out), "--faults", "timeout", "--policy", "enforce"]) == 0
    assert main(["run", "-c", str(SCRIPTED_CONFIG), "--out", str(out), "--faults", "nope"]) == 2


def test_relative_out_dir_still_reaches_tools(tmp_path, monkeypatch):
    # Regression: a relative --out made the proxy resolve proxy.json against its own cwd.
    monkeypatch.chdir(tmp_path)
    assert main(["run", "-c", str(SCRIPTED_CONFIG), "--out", "runs", "--faults", "no-fault"]) == 0
    result = json.loads(next((tmp_path / "runs").glob("*/cooperative__no-fault/result.json")).read_text())
    assert result["passed"] and result["tool_calls"] >= 2


def test_ui_reports_missing_directory_clearly(tmp_path, capfd):
    assert main(["ui", str(tmp_path / "nope"), "--no-open"]) == 2
    assert "does not exist" in capfd.readouterr().err


def test_chat_lets_a_human_play_the_user(tmp_path, monkeypatch, capfd):
    lines = iter(["/help", "Please return my sneakers from order A12", "/done"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    code = main(["chat", "-c", str(SCRIPTED_CONFIG), "--fault", "timeout", "--out", str(tmp_path / "runs")])
    out = capfd.readouterr().out
    assert code == 1
    assert "You are playing: cooperative" in out
    assert "⚙ book_pickup(" in out and "TIMEOUT (injected, but committed)" in out
    assert "agent › Pickup booked" in out
    assert "FAIL dup" in out and "murphy replay" in out
    convo = next((tmp_path / "runs").glob("*/cooperative__timeout/conversation.jsonl")).read_text()
    assert "Please return my sneakers" in convo and '"status": "goal_met"' in convo


def test_chat_quit_and_eof_end_as_give_up(tmp_path, monkeypatch, capfd):
    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert main(["chat", "-c", str(SCRIPTED_CONFIG), "--out", str(tmp_path / "runs")]) == 1
    assert "ended: give_up" in capfd.readouterr().out
