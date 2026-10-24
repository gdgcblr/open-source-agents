"""Unit tests for diagnostic and remediation tools and controlled dispatcher."""

import pytest
from src.simulator import ServiceSimulator
from src.tools import ToolDispatcher


def test_tool_dispatcher_all_tools_exist():
    sim = ServiceSimulator("api-service")
    dispatcher = ToolDispatcher(sim)

    expected_tools = {
        "check_health",
        "get_recent_logs",
        "get_metrics",
        "get_dependency_health",
        "get_config_diff",
        "get_deployment_history",
        "restart_service",
        "rollback_config",
        "verify_recovery",
    }
    assert set(dispatcher.registered_tool_names) == expected_tools


def test_read_only_diagnostic_tools():
    sim = ServiceSimulator("api-service")
    dispatcher = ToolDispatcher(sim)

    # 1. check_health
    res = dispatcher.execute("check_health")
    assert res.success
    assert res.data["status"] == "HEALTHY"

    # 2. get_metrics
    res = dispatcher.execute("get_metrics")
    assert res.success
    assert "error_rate" in res.data
    assert "latency_p95_ms" in res.data

    # 3. get_dependency_health
    res = dispatcher.execute("get_dependency_health")
    assert res.success
    assert isinstance(res.data, list)
    assert len(res.data) >= 3

    # 4. get_config_diff
    res = dispatcher.execute("get_config_diff")
    assert res.success
    assert res.data["has_diff"] is False

    # 5. get_deployment_history
    res = dispatcher.execute("get_deployment_history", {"limit": 5})
    assert res.success
    assert isinstance(res.data, list)

    # 6. get_recent_logs
    res = dispatcher.execute("get_recent_logs", {"limit": 10})
    assert res.success
    assert isinstance(res.data, list)

    # 7. verify_recovery
    res = dispatcher.execute("verify_recovery")
    assert res.success
    assert res.data["is_healthy"] is True


def test_invalid_tool_name_rejected():
    sim = ServiceSimulator("api-service")
    dispatcher = ToolDispatcher(sim)

    res = dispatcher.execute("execute_bash_command", {"command": "rm -rf /"})
    assert not res.success
    assert "Unrecognized tool" in res.error


def test_argument_validation():
    sim = ServiceSimulator("api-service")
    dispatcher = ToolDispatcher(sim)

    # Out of range limit for get_recent_logs (> 100)
    res = dispatcher.execute("get_recent_logs", {"limit": 500})
    assert not res.success
    assert "Invalid arguments" in res.error

    # Out of range limit (< 1)
    res = dispatcher.execute("get_recent_logs", {"limit": 0})
    assert not res.success
    assert "Invalid arguments" in res.error

    # Invalid type
    res = dispatcher.execute("get_recent_logs", {"limit": "not-an-int"})
    assert not res.success
    assert "Invalid arguments" in res.error


def test_remediation_tools_execution():
    sim = ServiceSimulator("api-service")
    dispatcher = ToolDispatcher(sim)

    # Inject bad config
    sim.inject_invalid_config({"db_pool_size": -10})
    assert dispatcher.execute("check_health").data["status"] == "UNHEALTHY"

    # Rollback via dispatcher
    res = dispatcher.execute("rollback_config")
    assert res.success
    assert res.data["success"] is True

    # Verification passes
    v_res = dispatcher.execute("verify_recovery")
    assert v_res.success
    assert v_res.data["is_healthy"] is True
