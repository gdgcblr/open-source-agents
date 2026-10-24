import sys

import pytest
from conftest import EXAMPLE_CONFIG

from murphy.config.loader import ConfigError, interpolate, load_config
from murphy.secrets import redact


def write(tmp_path, text, name="murphy.yaml"):
    path = tmp_path / name
    path.write_text(text)
    return path


MINIMAL = """
version: 1
name: demo
target: {type: scripted, policy: "x:y"}
personas: [{id: p, goal: g}]
"""


def test_example_config_loads():
    cfg = load_config(EXAMPLE_CONFIG)
    assert cfg.name == "shop-returns"
    assert {p.id for p in cfg.personas} == {"cooperative", "forgot-order-id", "impatient", "changes-mind", "ineligible-item"}
    assert cfg.persona("cooperative").vars["pickups"] == [{"order_id": "A12", "item_sku": "SNK-42"}]
    assert cfg.tools[0].command[0] == sys.executable  # "python" resolved to the running interpreter
    assert cfg.tools[0].cwd == str(EXAMPLE_CONFIG.parent.parent)
    assert [r.type for r in cfg.policy.rules] == ["idempotent", "requires_before", "max_calls", "budget"]
    assert cfg.checks[0].extras["rule"] == "max_calls_per_key"


def test_minimal_config_defaults(tmp_path):
    cfg = load_config(write(tmp_path, MINIMAL))
    assert [s.id for s in cfg.faults] == ["no-fault"]
    assert cfg.policy.mode == "monitor" and cfg.user.type == "llm"
    assert cfg.max_turns(cfg.personas[0]) == 8


def test_env_interpolation(monkeypatch):
    monkeypatch.setenv("SL_MODEL", "m1")
    doc = {"a": "${SL_MODEL}", "b": ["${SL_MISSING:-dflt}"], "c": "${vars.x}", "n": 3}
    assert interpolate(doc, "f") == {"a": "m1", "b": ["dflt"], "c": "${vars.x}", "n": 3}
    with pytest.raises(ConfigError, match=r"f\.x\[1\]: environment variable SL_NOPE"):
        interpolate({"x": [1, "${SL_NOPE}"]}, "f")


def test_env_values_cannot_change_yaml_structure(tmp_path, monkeypatch):
    # Regression: values were substituted into raw YAML text before parsing.
    monkeypatch.setenv("SL_EVIL", "x\nchecks: []\n# y: z")
    text = MINIMAL + "checks: [{id: c, type: trace, rule: called, tool: \"${SL_EVIL}\"}]\n"
    cfg = load_config(write(tmp_path, text))
    assert len(cfg.checks) == 1 and cfg.checks[0].extras["tool"] == "x\nchecks: []\n# y: z"


def test_python_path_is_appended_not_prepended(tmp_path):
    import sys

    (tmp_path / "lib").mkdir()
    load_config(write(tmp_path, MINIMAL + "python_path: [lib]\n"))
    entry = str((tmp_path / "lib").resolve())
    assert sys.path.index(entry) > sys.path.index(next(p for p in sys.path if "site-packages" in p))


def test_validation_errors_are_readable(tmp_path):
    bad = MINIMAL + "faults: [{id: x, inject: [{tool: t, type: explode}]}]\n"
    with pytest.raises(ConfigError, match=r"murphy.yaml: faults\.0\.inject\.0\.type"):
        load_config(write(tmp_path, bad))


def test_unknown_top_level_key_rejected(tmp_path):
    with pytest.raises(ConfigError, match="tagret"):
        load_config(write(tmp_path, MINIMAL + "tagret: {}\n"))


def test_persona_file_glob_and_duplicates(tmp_path):
    (tmp_path / "personas").mkdir()
    (tmp_path / "personas" / "a.yaml").write_text("id: a\ngoal: g\n")
    text = MINIMAL.replace("personas: [{id: p, goal: g}]", "personas: [{file: personas/*.yaml}, {id: b, goal: g}]")
    assert [p.id for p in load_config(write(tmp_path, text)).personas] == ["a", "b"]
    dup = MINIMAL.replace("[{id: p, goal: g}]", "[{id: p, goal: g}, {id: p, goal: h}]")
    with pytest.raises(ConfigError, match="duplicate ids"):
        load_config(write(tmp_path, dup))


def test_fault_trigger_exclusive(tmp_path):
    bad = MINIMAL + "faults: [{id: x, inject: [{tool: t, type: slow, on_call: 1, rate: 0.5}]}]\n"
    with pytest.raises(ConfigError, match="either on_call or rate"):
        load_config(write(tmp_path, bad))


def test_redaction():
    data = {"api_key": "abc", "args": {"Authorization": "Bearer x", "q": "use sk-abcdefghijklmnop123"}, "n": 1}
    assert redact(data) == {"api_key": "***", "args": {"Authorization": "***", "q": "use ***"}, "n": 1}


def test_redaction_keeps_ordinary_long_ids():
    sha = "a3f9" * 10  # 40-char hash-like id must survive (it was masked before)
    assert redact({"order_id": sha}) == {"order_id": sha}
