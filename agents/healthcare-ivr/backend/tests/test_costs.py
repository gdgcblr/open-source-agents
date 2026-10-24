import pytest

from app.services.costs import estimate_cost_usd


@pytest.mark.parametrize(
    ("seconds", "usd_per_minute", "expected"),
    [
        (90, 0.163, 0.2445),  # 1.5 minutes of an Advanced-tier voice agent
        (60, 0.075, 0.075),  # 1 minute of a Standard-tier voice agent
        (18.4, 0.0043, 0.0013),  # a short recording transcribed with Nova-3
        (-5, 0.163, 0.0),
    ],
)
def test_estimate_cost_usd(seconds: float, usd_per_minute: float, expected: float) -> None:
    assert estimate_cost_usd(seconds, usd_per_minute) == expected
