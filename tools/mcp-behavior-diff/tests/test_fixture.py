import textwrap

import pytest

from mcp_behavior_diff.errors import FixtureError
from mcp_behavior_diff.fixture import load_fixture

SERVER = "{command: python, args: [s.py]}"


def write(tmp_path, body: str):
    path = tmp_path / "f.yaml"
    path.write_text(textwrap.dedent(body))
    return path


def base(calls="- {id: a, tool: t, read_only: true}", servers=None, extra=""):
    servers = servers or f"old: {SERVER}\n  new: {SERVER}"
    return f"version: 1\nservers:\n  {servers}\ncalls:\n  {calls}\n{extra}"


def test_valid_fixture_loads(tmp_path):
    fx = load_fixture(write(tmp_path, base()))
    assert fx.calls[0].tool == "t" and fx.servers["old"].command == "python"


def test_read_only_assertion_is_mandatory(tmp_path):
    with pytest.raises(FixtureError, match="read_only"):
        load_fixture(write(tmp_path, base(calls="- {id: a, tool: t}")))


@pytest.mark.parametrize("value", ["false", '"true"', "1"])
def test_read_only_must_be_literal_true(tmp_path, value):
    with pytest.raises(FixtureError, match="read_only"):
        load_fixture(write(tmp_path, base(calls=f"- {{id: a, tool: t, read_only: {value}}}")))


def test_unknown_keys_rejected(tmp_path):
    with pytest.raises(FixtureError, match="unknown key"):
        load_fixture(write(tmp_path, base(calls="- {id: a, tool: t, read_only: true, shell: x}")))


def test_python_object_yaml_tags_rejected(tmp_path):
    body = base().replace("python", "!!python/object/apply:os.getcwd []", 1)
    with pytest.raises(FixtureError, match="cannot parse"):
        load_fixture(write(tmp_path, body))


@pytest.mark.parametrize("cmd", ["python; rm -rf /", "a | b", "`id`", "$(id)", "python -c print(1)"])
def test_shell_syntax_in_command_rejected(tmp_path, cmd):
    servers = f"old: {{command: '{cmd}'}}\n  new: {SERVER}"
    with pytest.raises(FixtureError, match="command"):
        load_fixture(write(tmp_path, base(servers=servers)))


def test_secret_looking_env_literal_rejected(tmp_path):
    servers = f"old: {{command: python, env: {{API_KEY: abc}}}}\n  new: {SERVER}"
    with pytest.raises(FixtureError, match="secret"):
        load_fixture(write(tmp_path, base(servers=servers)))


@pytest.mark.parametrize("name", ["LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "PATH", "NODE_OPTIONS", "BASH_ENV"])
def test_loader_hijack_env_rejected(tmp_path, name):
    servers = f"old: {{command: python, env: {{{name}: x}}}}\n  new: {SERVER}"
    with pytest.raises(FixtureError, match="not allowed"):
        load_fixture(write(tmp_path, base(servers=servers)))


def test_cwd_must_stay_inside_fixture_dir(tmp_path):
    servers = f"old: {{command: python, cwd: ..}}\n  new: {SERVER}"
    with pytest.raises(FixtureError, match="inside the fixture directory"):
        load_fixture(write(tmp_path, base(servers=servers)))


def test_limits_cannot_exceed_hard_ceilings(tmp_path):
    with pytest.raises(FixtureError, match="ceiling"):
        load_fixture(write(tmp_path, base(extra="limits: {call_timeout_s: 100000}")))


def test_too_many_calls_rejected(tmp_path):
    calls = "\n  ".join(f"- {{id: c{i}, tool: t, read_only: true}}" for i in range(4))
    with pytest.raises(FixtureError, match="max_calls"):
        load_fixture(write(tmp_path, base(calls=calls, extra="limits: {max_calls: 3}")))


def test_duplicate_ids_rejected(tmp_path):
    calls = "- {id: a, tool: t, read_only: true}\n  - {id: a, tool: u, read_only: true}"
    with pytest.raises(FixtureError, match="duplicate"):
        load_fixture(write(tmp_path, base(calls=calls)))


def test_oversized_fixture_rejected(tmp_path):
    path = write(tmp_path, base())
    path.write_text("# " + "x" * (300 * 1024))
    with pytest.raises(FixtureError, match="larger than"):
        load_fixture(path)


def test_oversized_arguments_rejected(tmp_path):
    big = "x" * 20000
    with pytest.raises(FixtureError, match="max_arg_bytes"):
        load_fixture(write(tmp_path, base(calls=f"- {{id: a, tool: t, read_only: true, arguments: {{v: {big}}}}}")))
