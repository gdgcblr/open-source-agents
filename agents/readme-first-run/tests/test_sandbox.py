import io
import os
import re
import stat
import subprocess
import time
from pathlib import Path

import pytest

from firstrun import sandbox
from firstrun.models import Step
from firstrun.sandbox import DockerSandbox, LocalSandbox, build_script, make_sandbox, parse_log


def steps(*commands, long_running=()):
    return [Step(index=i, command=c, long_running=i in long_running) for i, c in enumerate(commands, 1)]


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "hello.txt").write_text("original\n")
    (root / ".venv").mkdir()
    (root / ".venv" / "junk").write_text("should not be copied\n")
    return root


@pytest.fixture
def local(tmp_path):
    return LocalSandbox(watch_seconds=2, pip_cache=tmp_path / "pip-cache")


# --- script building and log parsing --------------------------------------------------------


def test_build_script_writes_one_file_per_step():
    files = build_script(steps("echo hi", "python app.py", long_running={2}), "abc123", 7)
    assert set(files) == {"run.sh", "step_1.sh", "step_2.sh"}
    assert files["step_1.sh"] == "echo hi\n"
    run = files["run.sh"]
    assert "@@FR-abc123" in run
    assert '. "$FR_STATE/step_1.sh"' in run
    assert "__fr_watch 2 7" in run


def test_parse_log_splits_steps_and_drops_marker_blanks():
    t = "tok"
    raw = "\n".join([
        "",
        "@@FR-tok begin 1",
        "installing",
        "",
        "@@FR-tok end 1 0",
        "",
        "@@FR-tok begin 2",
        "serving on 8501",
        "",
        "@@FR-tok alive 2",
        "",
        "@@FR-tok end 2 0",
        "",
        "@@FR-tok begin 3",
        "boom",
        "@@FR-tok end 3 2",
    ])
    results, log = parse_log(raw, steps("pip install x", "streamlit run app.py", "python main.py", "pytest"), t)
    assert [r.status for r in results] == ["passed", "alive", "failed", "not_run"]
    assert results[0].output == "installing"
    assert results[1].exit_code is None
    assert results[2].exit_code == 2 and results[2].output == "boom"
    assert "@@FR" not in log
    assert "$ pip install x" in log
    assert "\n\n" not in log


def test_parse_log_keeps_real_blank_lines_and_flags_unfinished_step():
    raw = "@@FR-t begin 1\na\n\n\nb\n\n@@FR-t begin 2\nstill going"
    results, _ = parse_log(raw, steps("one", "two"), "t")
    assert results[0].status == "failed"  # never ended, caller decides why
    assert results[1].output == "still going"
    assert results[1].status == "failed" and results[1].exit_code is None


def test_make_sandbox():
    assert isinstance(make_sandbox("docker", image="python:3.11-slim"), DockerSandbox)
    assert isinstance(make_sandbox("local"), LocalSandbox)
    with pytest.raises(ValueError):
        make_sandbox("vm")


# --- local sandbox, for real ----------------------------------------------------------------


def test_local_state_persists_and_env_is_clean(local, project, monkeypatch):
    monkeypatch.setenv("FIRSTRUN_TEST_SECRET", "hunter2")
    events = []
    plan = steps(
        "mkdir sub && cd sub",
        "export FOO=bar",
        'pwd && echo "foo=$FOO"',
        "for i in 1 2 3; do\n  echo n$i\ndone",
        'echo "secret=[$FIRSTRUN_TEST_SECRET] given=[$GIVEN]"',
        "python -c \"import sys, importlib.util as u; print(sys.prefix != sys.base_prefix, u.find_spec('pytest') is None)\"",
        "echo changed > ../hello.txt && touch ../new.txt && ls ..",
    )
    res = local.run(project, plan, env={"GIVEN": "yes"}, on_event=lambda k, m, d: events.append((k, m, d)))
    assert res.status == "passed", res.log
    out = [r.output for r in res.results]
    assert out[2].splitlines()[0].endswith("/sub")
    assert out[2].splitlines()[1] == "foo=bar"
    assert out[3] == "n1\nn2\nn3"
    assert out[4] == "secret=[] given=[yes]"
    assert out[5] == "True True"  # fresh venv, nothing from the host venv
    assert ".venv" not in out[6]
    # the original project is untouched
    assert (project / "hello.txt").read_text() == "original\n"
    assert not (project / "new.txt").exists()
    kinds = [e[0] for e in events]
    assert kinds.count("step_start") == 7 and kinds.count("step_end") == 7
    assert ("log", "n2", None) in events
    assert res.sandbox.startswith("local venv (python ")


def test_local_failure_stops_the_run(local, project):
    res = local.run(project, steps("echo ok", "python -c 'import dotenv'", "echo never"))
    assert res.status == "failed"
    assert [r.status for r in res.results] == ["passed", "failed", "not_run"]
    assert res.failed_step.step.index == 2
    assert res.failed_step.exit_code == 1
    assert "No module named 'dotenv'" in res.failed_step.output
    assert "never" not in res.log


def test_local_exit_inside_step_counts_as_failure(local, project):
    res = local.run(project, steps("echo before", "exit 7", "echo after"))
    assert res.status == "failed"
    assert res.results[1].status == "failed" and res.results[1].exit_code == 7
    assert res.results[2].status == "not_run"


def test_local_long_running_step_is_alive_and_killed(local, project, tmp_path):
    pidfile = tmp_path / "server.pid"
    server = (
        f"python -c \"import os, time; open('{pidfile}', 'w').write(str(os.getpid())); "
        "print('serving', flush=True); time.sleep(60)\""
    )
    started = time.monotonic()
    res = local.run(project, steps("echo setup", server, "echo after", long_running={2}))
    assert time.monotonic() - started < 20
    assert res.status == "passed", res.log
    assert [r.status for r in res.results] == ["passed", "alive", "passed"]
    assert "serving" in res.results[1].output
    assert "Terminated" not in res.log
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_local_long_running_step_that_crashes_fails(local, project):
    res = local.run(project, steps("python -c 'raise SystemExit(3)'", "echo after", long_running={1}))
    assert res.results[0].status == "failed" and res.results[0].exit_code == 3
    assert res.status == "failed"


def test_local_global_timeout(local, project):
    started = time.monotonic()
    res = local.run(project, steps("echo start", "sleep 30", "echo never"), timeout=3)
    assert time.monotonic() - started < 15
    assert res.status == "timeout"
    assert [r.status for r in res.results] == ["passed", "timeout", "not_run"]


def test_local_reports_missing_python(project):
    res = LocalSandbox(python="/nonexistent/python3").run(project, steps("echo hi"))
    assert res.status == "error"
    assert "not found" in res.error
    assert res.results[0].status == "not_run"


# --- docker sandbox, with subprocess mocked ---------------------------------------------------


class FakeProc:
    def __init__(self, data: bytes, rc: int = 0):
        self.stdout = io.BytesIO(data)
        self.returncode = rc
        self.pid = 4242

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        pass


class FakeDocker:
    def __init__(self, image_present=False, daemon_up=True, env_present=False, build_ok=True):
        self.calls = []
        self.image_present = image_present
        self.env_present = env_present
        self.build_ok = build_ok
        self.build_input = None
        self.daemon_up = daemon_up
        self.env_mode = None
        self.env_text = None
        self.env_path = None
        self.copied = {}
        self.state_dir = None

    def run(self, cmd, **kwargs):
        assert cmd[0] == "docker"
        self.calls.append(cmd[1:])
        args = cmd[1:]
        ok = subprocess.CompletedProcess(cmd, 0, "", "")
        if args[0] == "info":
            if not self.daemon_up:
                return subprocess.CompletedProcess(cmd, 1, "", "Cannot connect to the Docker daemon")
            return subprocess.CompletedProcess(cmd, 0, "27.3.1\n", "")
        if args[:2] == ["image", "inspect"]:
            present = self.env_present if args[2].startswith("firstrun-env:") else self.image_present
            return subprocess.CompletedProcess(cmd, 0 if present else 1, "", "No such image")
        if args[0] == "build":
            self.build_input = kwargs.get("input")
            if self.build_ok:
                return ok
            return subprocess.CompletedProcess(cmd, 1, "", "E: Unable to locate package git")
        if args[0] == "create":
            ef = Path(args[args.index("--env-file") + 1])
            self.env_path = ef
            self.env_mode = stat.S_IMODE(ef.stat().st_mode)
            self.env_text = ef.read_text()
            return subprocess.CompletedProcess(cmd, 0, "deadbeef\n", "")
        if args[0] == "cp":
            src = Path(args[1][:-2])  # strip the trailing "/."
            self.copied[args[2].split(":", 1)[1]] = sorted(p.name for p in src.iterdir())
            if args[2].endswith(":/firstrun"):
                self.state_dir = src
                self.run_sh = (src / "run.sh").read_text()
            return ok
        return ok

    def popen(self, cmd, **kwargs):
        assert cmd[:3] == ["docker", "start", "-a"]
        token = re.search(r"@@FR-([0-9a-f]+)", self.run_sh).group(1)
        m = f"@@FR-{token}"
        out = (
            f"\n{m} begin 1\nCollecting colorama\nSuccessfully installed colorama\n\n{m} end 1 0\n"
            f"\n{m} begin 2\nTraceback (most recent call last):\n"
            f"ModuleNotFoundError: No module named 'dotenv'\n\n{m} end 2 1\n"
        )
        return FakeProc(out.encode(), rc=0)


def test_docker_run_builds_the_right_commands(monkeypatch, project):
    fake = FakeDocker()
    monkeypatch.setattr(sandbox.subprocess, "run", fake.run)
    monkeypatch.setattr(sandbox.subprocess, "Popen", fake.popen)
    events = []
    box = DockerSandbox(image="python:3.12-slim")
    res = box.run(project, steps("pip install -r requirements.txt", "python main.py", "echo never"),
                  env={"GEMINI_API_KEY": "test-value", "BAD KEY": "x"},
                  on_event=lambda k, m, d: events.append((k, m)))

    assert res.status == "failed"
    assert [r.status for r in res.results] == ["passed", "failed", "not_run"]
    assert "No module named 'dotenv'" in res.failed_step.output
    assert res.sandbox == "docker python:3.12-slim + git"

    verbs = [c[0] if c[0] != "image" else "image inspect" for c in fake.calls]
    assert verbs == ["info", "image inspect", "image inspect", "pull", "build", "create", "cp", "cp", "rm"]
    assert fake.calls[1] == ["image", "inspect", "firstrun-env:python-3.12-slim-v1"]
    assert fake.calls[4] == ["build", "-t", "firstrun-env:python-3.12-slim-v1", "-"]
    assert fake.build_input.startswith("FROM python:3.12-slim\n") and "git ca-certificates" in fake.build_input
    create = next(c for c in fake.calls if c[0] == "create")
    joined = " ".join(create)
    for piece in ("--memory 2g", "--cpus 2", "--pids-limit 512", "-v firstrun-pip-cache:/root/.cache/pip",
                  "-e FR_WORKDIR=/work", "-e FR_STATE=/firstrun",
                  "firstrun-env:python-3.12-slim-v1 bash /firstrun/run.sh"):
        assert piece in joined
    name = create[create.index("--name") + 1]
    assert fake.calls[-1] == ["rm", "-f", name]

    # secrets go through a private temp file that is gone afterwards
    assert fake.env_mode == 0o600
    assert fake.env_text == "GEMINI_API_KEY=test-value\n"
    assert not fake.env_path.exists()
    assert ("warn", "Ignoring environment variable with an unusable name: BAD KEY") in events

    # the project copy looks like a fresh clone
    assert fake.copied["/work"] == ["hello.txt"]
    assert "run.sh" in fake.copied["/firstrun"] and "step_3.sh" in fake.copied["/firstrun"]
    assert any(k == "info" and "Pulling python:3.12-slim" in m for k, m in events)


def test_docker_skips_pull_when_image_is_cached(monkeypatch, project):
    fake = FakeDocker(image_present=True)
    monkeypatch.setattr(sandbox.subprocess, "run", fake.run)
    monkeypatch.setattr(sandbox.subprocess, "Popen", fake.popen)
    DockerSandbox().run(project, steps("echo hi", "python main.py"))
    assert not any(c[0] == "pull" for c in fake.calls)


def test_docker_reuses_the_cached_git_image(monkeypatch, project):
    fake = FakeDocker(env_present=True)
    monkeypatch.setattr(sandbox.subprocess, "run", fake.run)
    monkeypatch.setattr(sandbox.subprocess, "Popen", fake.popen)
    res = DockerSandbox().run(project, steps("echo hi", "python main.py"))
    verbs = [c[0] if c[0] != "image" else "image inspect" for c in fake.calls]
    # the base image is not even looked at once the derived one exists
    assert verbs == ["info", "image inspect", "create", "cp", "cp", "rm"]
    assert res.sandbox == "docker python:3.12-slim + git"


def test_docker_falls_back_to_plain_image_when_git_build_fails(monkeypatch, project):
    fake = FakeDocker(image_present=True, build_ok=False)
    monkeypatch.setattr(sandbox.subprocess, "run", fake.run)
    monkeypatch.setattr(sandbox.subprocess, "Popen", fake.popen)
    events = []
    box = DockerSandbox()
    res = box.run(project, steps("echo hi", "python main.py"), on_event=lambda k, m, d: events.append((k, m)))
    assert res.status == "failed"  # the run itself still happened
    create = next(c for c in fake.calls if c[0] == "create")
    assert "python:3.12-slim" in create and not any(a.startswith("firstrun-env:") for a in create)
    assert res.sandbox == "docker python:3.12-slim"
    assert any(k == "warn" and "Could not add git" in m and "Unable to locate package" in m for k, m in events)
    # a second run in the same check does not retry the build
    fake.calls.clear()
    box.run(project, steps("echo hi", "python main.py"))
    assert not any(c[0] == "build" for c in fake.calls)


def test_docker_leaves_unknown_images_alone(monkeypatch, project):
    fake = FakeDocker(image_present=True)
    monkeypatch.setattr(sandbox.subprocess, "run", fake.run)
    monkeypatch.setattr(sandbox.subprocess, "Popen", fake.popen)
    res = DockerSandbox(image="ghcr.io/acme/custom:1").run(project, steps("echo hi", "python main.py"))
    assert not any(c[0] == "build" for c in fake.calls)
    assert res.sandbox == "docker ghcr.io/acme/custom:1"
    create = next(c for c in fake.calls if c[0] == "create")
    assert "ghcr.io/acme/custom:1" in create


def test_env_tag_is_a_valid_docker_tag():
    assert DockerSandbox.env_tag("python:3.12-slim") == "firstrun-env:python-3.12-slim-v1"
    assert DockerSandbox.env_tag("docker.io/library/node:22-bookworm-slim") == "firstrun-env:node-22-bookworm-slim-v1"


def test_docker_daemon_down_is_an_error(monkeypatch, project):
    fake = FakeDocker(daemon_up=False)
    monkeypatch.setattr(sandbox.subprocess, "run", fake.run)
    res = DockerSandbox().run(project, steps("echo hi"))
    assert res.status == "error"
    assert "not reachable" in res.error and "Cannot connect" in res.error
    assert [c[0] for c in fake.calls] == ["info"]


def test_docker_not_installed(monkeypatch, project):
    def missing(cmd, **kwargs):
        raise FileNotFoundError("docker")
    monkeypatch.setattr(sandbox.subprocess, "run", missing)
    ok, reason = DockerSandbox().available()
    assert not ok and "not installed" in reason


def test_expect_exit_counts_as_passed_and_the_run_goes_on(local, project):
    s = [Step(1, "echo '2 errors'; (exit 1)", expect_exit=1), Step(2, "echo after")]
    res = local.run(project, s)
    assert res.status == "passed"
    assert (res.results[0].status, res.results[0].exit_code) == ("passed", 1)
    assert res.results[1].output == "after"
    assert "-eq 1 ]" in build_script(s, "tok", 5)["run.sh"]


def test_expect_exit_only_accepts_that_code(local, project):
    res = local.run(project, [Step(1, "(exit 2)", expect_exit=1), Step(2, "echo never")])
    assert res.status == "failed"
    assert (res.results[0].status, res.results[0].exit_code) == ("failed", 2)
    assert res.results[1].status == "not_run"
