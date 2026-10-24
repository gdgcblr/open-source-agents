"""Allow-listed fixture test registry to prevent arbitrary code execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config.settings import FIXTURES_ROOT


@dataclass(frozen=True)
class RegisteredTestEntry:
    test_id: str
    scenario_id: str
    test_kind: str  # "provider_isolated" | "consumer_isolated" | "combined_integration" | "post_fix_integration"
    label: str
    relative_path: str
    expected_failure: bool = False
    uses_stale_mock: bool = False


ALLOWED_SCENARIO_IDS: frozenset[str] = frozenset(
    {
        "customer_id_rename",
        "safe_optional_field",
    }
)


REGISTERED_TESTS: dict[str, RegisteredTestEntry] = {
    "customer_id_rename:provider_isolated": RegisteredTestEntry(
        test_id="customer_id_rename:provider_isolated",
        scenario_id="customer_id_rename",
        test_kind="provider_isolated",
        label="orders-api Isolated Unit Test (PR #142)",
        relative_path="repos/orders-api/tests/test_provider_unit.py",
        expected_failure=False,
        uses_stale_mock=False,
    ),
    "customer_id_rename:consumer_isolated": RegisteredTestEntry(
        test_id="customer_id_rename:consumer_isolated",
        scenario_id="customer_id_rename",
        test_kind="consumer_isolated",
        label="checkout-client Isolated Unit Test (PR #89 — Stale Mock)",
        relative_path="repos/checkout-client/tests/test_consumer_unit.py",
        expected_failure=False,
        uses_stale_mock=True,
    ),
    "customer_id_rename:combined_integration": RegisteredTestEntry(
        test_id="customer_id_rename:combined_integration",
        scenario_id="customer_id_rename",
        test_kind="combined_integration",
        label="Combined Cross-Repo Integration Check (orders-api + checkout-client)",
        relative_path="repos/checkout-client/tests/test_combined_contract.py",
        expected_failure=True,
        uses_stale_mock=False,
    ),
    "customer_id_rename:post_fix_integration": RegisteredTestEntry(
        test_id="customer_id_rename:post_fix_integration",
        scenario_id="customer_id_rename",
        test_kind="post_fix_integration",
        label="Post-Fix Combined Integration Check (orders-api + remediated checkout-client)",
        relative_path="repos/checkout-client/tests/test_post_fix_contract.py",
        expected_failure=False,
        uses_stale_mock=False,
    ),
    "safe_optional_field:provider_isolated": RegisteredTestEntry(
        test_id="safe_optional_field:provider_isolated",
        scenario_id="safe_optional_field",
        test_kind="provider_isolated",
        label="orders-api Isolated Unit Test (PR #148)",
        relative_path="repos/orders-api/tests/test_provider_unit.py",
        expected_failure=False,
        uses_stale_mock=False,
    ),
    "safe_optional_field:consumer_isolated": RegisteredTestEntry(
        test_id="safe_optional_field:consumer_isolated",
        scenario_id="safe_optional_field",
        test_kind="consumer_isolated",
        label="checkout-client Isolated Unit Test (PR #92)",
        relative_path="repos/checkout-client/tests/test_consumer_unit.py",
        expected_failure=False,
        uses_stale_mock=False,
    ),
    "safe_optional_field:combined_integration": RegisteredTestEntry(
        test_id="safe_optional_field:combined_integration",
        scenario_id="safe_optional_field",
        test_kind="combined_integration",
        label="Combined Cross-Repo Integration Check (orders-api + checkout-client)",
        relative_path="repos/checkout-client/tests/test_combined_contract.py",
        expected_failure=False,
        uses_stale_mock=False,
    ),
}


def resolve_registered_test_path(
    test_id: str,
    fixtures_root: Path = FIXTURES_ROOT,
) -> tuple[RegisteredTestEntry, Path]:
    """Validate and resolve a registered test ID to its safe filesystem path."""
    if test_id not in REGISTERED_TESTS:
        raise PermissionError(
            f"Test ID '{test_id}' is not in the allow-listed fixture registry. "
            "Arbitrary test execution is prohibited."
        )
    entry = REGISTERED_TESTS[test_id]
    scenario_root = (fixtures_root / entry.scenario_id).resolve()
    target_path = (scenario_root / entry.relative_path).resolve()

    if not str(target_path).startswith(str(scenario_root)):
        raise PermissionError(f"Registered test path escapes scenario root: {entry.relative_path}")

    if not target_path.exists() or not target_path.is_file():
        raise FileNotFoundError(f"Registered test file does not exist: {target_path}")

    return entry, target_path
