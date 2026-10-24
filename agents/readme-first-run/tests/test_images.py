from pathlib import Path

import pytest

from firstrun import agent
from firstrun.models import Diagnosis, Edit, RunResult, Step, StepResult
from firstrun.sandbox import (
    DEFAULT_IMAGE, NODE_IMAGE, NODE_INSTALL, LocalSandbox, node_prerequisite, pick_image,
)


def steps(*commands):
    return [Step(index=i, command=c) for i, c in enumerate(commands, 1)]


def make(tmp_path, files):
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    return tmp_path


def test_pure_node_project_gets_a_node_image(tmp_path):
    project = make(tmp_path, {"package.json": "{}"})
    image, install_node, reason = pick_image(project, steps("npm install", "npm start"), DEFAULT_IMAGE)
    assert image == NODE_IMAGE and not install_node
    assert "package.json" in reason


def test_mixed_project_keeps_python_and_installs_node(tmp_path):
    project = make(tmp_path, {"package.json": "{}", "requirements.txt": "requests\n"})
    image, install_node, reason = pick_image(
        project, steps("pip install -r requirements.txt", "cd web && npm install"), DEFAULT_IMAGE)
    assert image == DEFAULT_IMAGE and install_node and reason


def test_python_commands_alone_make_it_mixed(tmp_path):
    project = make(tmp_path, {"package.json": "{}"})
    _, install_node, _ = pick_image(project, steps("python -m venv .venv", "npx serve"), DEFAULT_IMAGE)
    assert install_node


def test_python_only_project_is_untouched(tmp_path):
    project = make(tmp_path, {"requirements.txt": "requests\n"})
    assert pick_image(project, steps("pip install -r requirements.txt", "python main.py"), DEFAULT_IMAGE) == (
        DEFAULT_IMAGE, False, None)


def test_npm_leftover_without_package_json_still_runs_and_fails(tmp_path):
    # a stray `npm start` copied from the template is a README problem, not a sandbox one
    project = make(tmp_path, {"requirements.txt": "requests\n"})
    assert pick_image(project, steps("pip install -r requirements.txt", "npm start"), DEFAULT_IMAGE) == (
        DEFAULT_IMAGE, False, None)


@pytest.mark.parametrize("requested", ["node:20", "python:3.11-slim", "python:3.12"])
def test_user_supplied_image_is_respected(tmp_path, requested):
    project = make(tmp_path, {"package.json": "{}"})
    assert pick_image(project, steps("npm install"), requested) == (requested, False, None)


def test_node_prerequisite_goes_first_once():
    out = node_prerequisite(steps("pip install x", "npm install"))
    assert [s.command for s in out] == [NODE_INSTALL, "pip install x", "npm install"]
    assert out[0].provided_by_firstrun and out[0].kind == "prerequisite"
    assert [s.index for s in out] == [1, 2, 3]
    assert node_prerequisite(out) == out


def test_local_sandbox_path_reaches_homebrew_only_when_needed(monkeypatch, tmp_path):
    monkeypatch.setattr("firstrun.sandbox.os.path.isdir", lambda p: p == "/opt/homebrew/bin")
    monkeypatch.setattr("firstrun.sandbox.shutil.which", lambda tool, path=None: None)
    assert LocalSandbox._system_path().endswith(":/opt/homebrew/bin")
    monkeypatch.setattr("firstrun.sandbox.shutil.which", lambda tool, path=None: f"/usr/bin/{tool}")
    assert "/opt/homebrew/bin" not in LocalSandbox._system_path()


# --- wiring inside run_check ---------------------------------------------------------------


class FakeDocker:
    name = "docker"

    def __init__(self, image, fail_first=False):
        self.image = image
        self.fail_first = fail_first
        self.runs = []

    def available(self):
        return True, ""

    def describe(self):
        return f"docker {self.image} + git"

    def run(self, project_dir, steps, *, env=None, label="as documented", on_event=None, timeout=900):
        self.runs.append((label, self.image, [s.command for s in steps]))
        failing = self.fail_first and len(self.runs) == 1
        results = [StepResult(s, "passed", 0, "", 0.1) for s in steps]
        if failing:
            results[-1] = StepResult(steps[-1], "failed", 1, "Error: something", 0.1)
        return RunResult(label, "failed" if failing else "passed", results, 0.5, self.describe(), "")


def wire(monkeypatch, fail_first=False):
    boxes = []

    def factory(kind, *, image, watch_seconds):
        boxes.append(FakeDocker(image, fail_first))
        return boxes[-1]

    monkeypatch.setattr(agent, "make_sandbox", factory)
    monkeypatch.setattr(agent, "get_llm", lambda *a, **k: None)
    monkeypatch.setattr(agent.rules, "static_hints", lambda p: [])
    return boxes


README_NODE = "# app\n\n```bash\nnpm install\nnpm start\n```\n"
README_MIXED = "# app\n\n```bash\npip install -r requirements.txt\nnpm install\nnode index.js\n```\n"


def test_run_check_switches_a_node_project_to_the_node_image(monkeypatch, tmp_path):
    project = tmp_path / "p"
    project.mkdir()
    make(project, {"package.json": "{}", "README.md": README_NODE, "index.js": ""})
    boxes = wire(monkeypatch)
    events = []
    report, _ = agent.run_check(str(project), agent.Settings(sandbox="docker", out_dir=tmp_path / "runs"),
                                on_event=lambda k, m, d: events.append((k, m)))
    assert report.verdict == "passed"
    assert boxes[0].image == NODE_IMAGE
    assert boxes[0].runs[0][1] == NODE_IMAGE
    assert report.settings["image"] == NODE_IMAGE and "package.json" in report.settings["image_reason"]
    assert any(n.startswith("Environment:") for n in report.documented_plan.notes)
    assert any(k == "info" and m.startswith("Environment:") for k, m in events)


def test_run_check_adds_node_to_every_plan_of_a_mixed_project(monkeypatch, tmp_path):
    project = tmp_path / "p"
    project.mkdir()
    make(project, {"package.json": "{}", "requirements.txt": "requests\n", "README.md": README_MIXED,
                   "index.js": ""})
    boxes = wire(monkeypatch, fail_first=True)
    monkeypatch.setattr(agent.rules, "diagnose", lambda d, plan, run: Diagnosis(
        category="code_bug", summary="touch", edits=[Edit("index.js", "", "// fixed\n")]))
    report, _ = agent.run_check(str(project), agent.Settings(sandbox="docker", out_dir=tmp_path / "runs"))
    assert report.verdict == "fixed"
    assert boxes[0].image == DEFAULT_IMAGE
    documented, verify = boxes[0].runs[0][2], boxes[0].runs[1][2]
    assert documented[0] == NODE_INSTALL and verify[0] == NODE_INSTALL
    assert verify.count(NODE_INSTALL) == 1
    assert report.documented_plan.steps[0].provided_by_firstrun


def test_run_check_keeps_explicit_image_and_local_sandbox(monkeypatch, tmp_path):
    project = tmp_path / "p"
    project.mkdir()
    make(project, {"package.json": "{}", "README.md": README_NODE})
    boxes = wire(monkeypatch)
    report, _ = agent.run_check(str(project), agent.Settings(sandbox="docker", image="node:20",
                                                             out_dir=tmp_path / "runs"))
    assert boxes[0].image == "node:20" and "image_reason" not in report.settings
    report, _ = agent.run_check(str(project), agent.Settings(sandbox="local", out_dir=tmp_path / "runs2"))
    assert boxes[1].image == DEFAULT_IMAGE and "image_reason" not in report.settings
