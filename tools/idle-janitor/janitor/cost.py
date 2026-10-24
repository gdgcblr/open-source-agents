"""Cost + energy estimation.

Everything here is a *rough estimate*. We optimize for being honest,
localized to INR + Wh, and emotionally relatable rather than scientifically
precise. The README is explicit about this.
"""

from __future__ import annotations

# Rough idle-draw in watts by image / process family. Numbers are deliberately
# conservative and based on commonly cited idle footprints for a laptop running
# the given workload. These are tunable via estimate_watts().
_IMAGE_WATTS: dict[str, float] = {
    "postgres": 8.0,
    "mysql": 8.0,
    "mariadb": 8.0,
    "mongo": 7.0,
    "redis": 3.0,
    "elasticsearch": 15.0,
    "kafka": 12.0,
    "rabbitmq": 6.0,
    "nginx": 2.0,
    "node": 5.0,
    "python": 5.0,
    "java": 10.0,
    "ollama": 20.0,
}

_PROCESS_WATTS: dict[str, float] = {
    "node": 5.0,
    "next": 7.0,
    "vite": 6.0,
    "webpack": 7.0,
    "python": 5.0,
    "uvicorn": 5.0,
    "flask": 4.0,
    "django": 6.0,
    "ruby": 5.0,
    "rails": 7.0,
    "java": 10.0,
    "gradle": 12.0,
    "ngrok": 2.0,
}

DEFAULT_WATTS = 5.0

# India average residential tariff. Tunable via .env in a future version.
INR_PER_KWH = 8.0

# India grid carbon intensity, kg CO2 per kWh (CEA 2024 average, ~0.713 kg/kWh).
# https://cea.nic.in/wp-content/uploads/baseline/2024/01/User_Guide_Version_19.0.pdf
CO2_KG_PER_KWH = 0.713


def estimate_watts(kind: str, name: str) -> float:
    """Guess idle-draw in watts for a resource.

    kind: "docker" | "process"
    name: image name (docker) or process command/name
    """
    table = _IMAGE_WATTS if kind == "docker" else _PROCESS_WATTS
    needle = (name or "").lower()
    for key, watts in table.items():
        if key in needle:
            return watts
    return DEFAULT_WATTS


def wh_from(watts: float, uptime_seconds: float) -> float:
    """Watt-hours burned over the given uptime."""
    return watts * (uptime_seconds / 3600.0)


def inr_from(wh: float) -> float:
    """Rupees burned for the given Wh at the default tariff."""
    return (wh / 1000.0) * INR_PER_KWH


def co2_g_from(wh: float) -> float:
    """Grams of CO2 emitted for the given Wh at the India grid intensity."""
    return (wh / 1000.0) * CO2_KG_PER_KWH * 1000.0  # kWh * kg/kWh * g/kg


def analogy(wh: float) -> str:
    """A human-relatable comparison for the Wh number.

    Chosen for emotional resonance, not perfect accuracy.
    """
    if wh < 1:
        return "a blink — but it adds up"
    if wh < 5:
        return "a few minutes of LED bulb"
    if wh < 15:
        return "~1 phone charge"
    if wh < 30:
        return "~2 phone charges"
    if wh < 60:
        return "a filter coffee's worth of grid energy"
    if wh < 150:
        return "a half-day of a ceiling fan"
    if wh < 500:
        return "powering a laptop for a workday"
    return "running a fridge for several hours"


def summarize(resources: list[dict]) -> dict:
    """Aggregate per-resource waste into a single human-friendly summary."""
    total_wh = sum(r.get("wh", 0.0) for r in resources)
    total_inr = sum(r.get("inr", 0.0) for r in resources)
    total_co2_g = sum(r.get("co2_g", co2_g_from(r.get("wh", 0.0))) for r in resources)
    return {
        "resource_count": len(resources),
        "total_wh": round(total_wh, 2),
        "total_inr": round(total_inr, 2),
        "total_co2_g": round(total_co2_g, 2),
        "analogy": analogy(total_wh),
        "headline": (
            f"\u20b9{total_inr:.2f}, {total_wh:.1f} Wh, {total_co2_g:.1f} g CO\u2082 "
            f"wasted on {len(resources)} idle resource(s) \u2014 {analogy(total_wh)}."
        ),
    }
