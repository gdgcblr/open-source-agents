from __future__ import annotations

import json
import re

import pytest

from main import main


@pytest.fixture(autouse=True)
def no_keys(monkeypatch, tmp_path):
    for i in range(1, 6):
        monkeypatch.delenv(f"WORKER_{i}_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no stray workers.json, .env or database


def test_the_demo_falls_back_to_the_mock_and_completes(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "MOCK gateway" in out
    assert "completed  (5/5 steps)" in out
    assert "raw conversation transfers  0" in out


def test_stop_then_resume(capsys):
    assert main(["--mock", "--stop-after", "2"]) == 0
    out = capsys.readouterr().out
    task_id = re.search(r"--resume (task-\w+)", out).group(1)
    assert "running  (2/5 steps)" in out

    assert main(["--resume", task_id[:9], "--mock"]) == 0
    out = capsys.readouterr().out
    assert "resuming at step 3 of 5" in out
    assert "completed  (5/5 steps)" in out


def test_state_and_list(capsys):
    main(["--mock"])
    task_id = re.search(r"(task-\w+): ", capsys.readouterr().out).group(1)
    assert main(["--state", task_id]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "completed"
    assert main(["--list"]) == 0
    assert task_id in capsys.readouterr().out


def test_custom_objective_and_plan(capsys):
    assert main(["--mock", "--objective", "Plan a launch.",
                 "--task", "Draft the checklist.", "--task", "Review it."]) == 0
    assert "completed  (2/2 steps)" in capsys.readouterr().out


def test_objective_without_steps_is_rejected():
    assert main(["--mock", "--objective", "Plan a launch."]) == 2


def test_unknown_task_is_a_clean_error(capsys):
    assert main(["--resume", "task-nope", "--mock"]) == 1
    assert "no task matches" in capsys.readouterr().err
