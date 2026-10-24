"""Estimated AI cost per call, from measured usage and the configured Deepgram rates."""


def estimate_cost_usd(seconds: float, usd_per_minute: float) -> float:
    """Per-minute list price prorated to the second, rounded to a hundredth of a cent."""
    return round(max(seconds, 0.0) / 60 * usd_per_minute, 4)
