from types import SimpleNamespace

import pytest

from mcp_behavior_diff.errors import PolicyViolation
from mcp_behavior_diff.fixture import Call, ServerSpec
from mcp_behavior_diff.policy import build_child_env, decide_call

CALL = Call(id="a", tool="t", arguments={}, read_only=True)


def ann(**kw):
    return SimpleNamespace(destructive_hint=kw.get("destructive"), read_only_hint=kw.get("read_only"))


def test_destructive_annotation_vetoes():
    assert not decide_call(CALL, ann(destructive=True, read_only=True)).allowed


def test_explicit_not_read_only_vetoes():
    assert not decide_call(CALL, ann(read_only=False)).allowed


def test_missing_annotations_allowed_on_fixture_assertion_only():
    decision = decide_call(CALL, None)
    assert decision.allowed and "fixture assertion only" in decision.reason


def test_server_read_only_hint_alone_never_grants_permission():
    unasserted = Call(id="a", tool="t", arguments={}, read_only=False)
    assert not decide_call(unasserted, ann(read_only=True)).allowed


def test_env_passthrough_of_secret_name_needs_explicit_flag():
    spec = ServerSpec(command="x", env_passthrough=("MY_API_KEY",))
    with pytest.raises(PolicyViolation, match="--allow-secret-env"):
        build_child_env(spec, {"MY_API_KEY": "value-123456"})
    env, secrets = build_child_env(spec, {"MY_API_KEY": "value-123456"}, frozenset({"MY_API_KEY"}))
    assert env == {"MY_API_KEY": "value-123456"} and secrets == ("value-123456",)


def test_env_passthrough_requires_variable_to_be_set():
    with pytest.raises(PolicyViolation, match="not set"):
        build_child_env(ServerSpec(command="x", env_passthrough=("LOG_LEVEL",)), {})


def test_parent_environment_is_not_copied():
    env, _ = build_child_env(ServerSpec(command="x", env={"A": "1"}), {"SECRET_THING": "s", "A": "no"})
    assert env == {"A": "1"}
