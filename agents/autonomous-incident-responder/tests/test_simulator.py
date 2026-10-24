"""Unit tests for the ServiceSimulator and fault-injection mechanics."""

import pytest
from src.models import HealthState
from src.simulator import ServiceSimulator, KNOWN_GOOD_CONFIG


def test_baseline_simulator_health():
    sim = ServiceSimulator("test-service")
    health = sim.check_health()
    assert health.status == HealthState.HEALTHY
    assert health.service == "test-service"
    assert health.active_incidents == 0

    metrics = sim.get_metrics()
    assert metrics.error_rate < 0.05
    assert metrics.latency_p95_ms < 100.0

    diff = sim.get_config_diff()
    assert not diff.has_diff

    deps = sim.get_dependency_health()
    assert all(d.status == HealthState.HEALTHY for d in deps)


def test_invalid_config_fault_and_rollback():
    sim = ServiceSimulator("test-service")
    bad_config = {"db_pool_size": -5, "request_timeout_ms": 0}
    sim.inject_invalid_config(bad_config, author="bad-deployer", reason="Invalid negative pool size")

    health = sim.check_health()
    assert health.status == HealthState.UNHEALTHY
    assert "Invalid negative pool size" in health.message

    diff = sim.get_config_diff()
    assert diff.has_diff
    assert "db_pool_size" in diff.changed_keys
    assert diff.current_values["db_pool_size"] == -5

    # Restarting does NOT fix invalid config
    restart_res = sim.restart_service()
    assert not restart_res.success
    assert sim.check_health().status == HealthState.UNHEALTHY

    # Rollback DOES fix invalid config
    rollback_res = sim.rollback_config()
    assert rollback_res.success
    assert "db_pool_size" in rollback_res.details["reverted_keys"]

    diff_after = sim.get_config_diff()
    assert not diff_after.has_diff
    assert sim.check_health().status == HealthState.HEALTHY

    # Independent verification succeeds
    verification = sim.verify_recovery()
    assert verification.is_healthy


def test_unavailable_dependency_fault():
    sim = ServiceSimulator("test-service")
    sim.inject_unavailable_dependency("auth_service", message="Connection refused on port 8081")

    health = sim.check_health()
    assert health.status == HealthState.DEGRADED
    assert "auth_service" in health.message

    deps = {d.name: d for d in sim.get_dependency_health()}
    assert deps["auth_service"].status == HealthState.UNHEALTHY
    assert deps["primary_db"].status == HealthState.HEALTHY

    # Restart should NOT fix dependency outage
    restart_res = sim.restart_service()
    assert not restart_res.success
    assert "auth_service" in restart_res.message

    # Verification must fail
    verification = sim.verify_recovery()
    assert not verification.is_healthy
    assert "auth_service" in verification.failing_dependencies


def test_elevated_error_rate_and_restart():
    sim = ServiceSimulator("test-service")
    sim.inject_elevated_error_rate(error_rate=0.45, reason="Thread pool starvation")

    health = sim.check_health()
    assert health.status == HealthState.DEGRADED
    assert "Elevated error rate" in health.message

    metrics = sim.get_metrics()
    assert metrics.error_rate == 0.45

    # Verification must fail before remediation
    verification_before = sim.verify_recovery()
    assert not verification_before.is_healthy

    # Restart fixes transient thread pool / memory leak fault
    restart_res = sim.restart_service()
    assert restart_res.success
    assert restart_res.details.get("transient_cleared") is True

    # Verification succeeds after restart
    verification_after = sim.verify_recovery()
    assert verification_after.is_healthy
    assert sim.check_health().status == HealthState.HEALTHY
