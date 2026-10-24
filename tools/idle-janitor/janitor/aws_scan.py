"""AWS adapter \u2014 **fixture-driven** in v1.

Why fixture-driven and not real boto3?
    * We deliberately scoped out AWS credential handling for the hackathon
      demo. Shipping a tool that reads ~/.aws/credentials is a different
      security surface and deserves its own review.
    * The fixture pattern exercises the full architecture end-to-end: cost
      math, MCP tool wiring, policy evaluation, journaling. Swapping in a
      real `ec2.describe_instances()` call is a ~10-line change inside
      `_load_fixture()` and nothing else needs to move.

How to point this at real data today:
    1. Export AWS_FIXTURE_PATH=/path/to/your_fixture.yaml  (handwritten or
       generated nightly by a CI job that calls describe_instances).
    2. Match the schema in aws_fixture.example.yaml.

How to wire real AWS later:
    * Replace `_load_fixture()` with a boto3 call that emits the same dict
      shape. Keep everything else untouched.

Cost + carbon numbers are honest estimates:
    * $/hr per instance_type is the on-demand us-east-1 price from the AWS
      price list (public). Numbers for ap-south-1 differ by ~10-20% in
      reality; we use us-east-1 as the single source of truth to keep the
      demo deterministic and the README honest about the assumption.
    * INR = USD * USD_INR (approximate).
    * CO2 uses a per-region grid intensity table (kg CO2 / kWh).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import cost

DEFAULT_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "aws_fixture.example.yaml"

USD_INR = 83.0

# On-demand us-east-1 Linux pricing, $/hr (public AWS price list, Oct 2024).
# A real boto3-backed version would pull this from the Pricing API.
_INSTANCE_USD_PER_HOUR: dict[str, float] = {
    "t2.micro": 0.0116,
    "t2.small": 0.023,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,
    "c5.large": 0.085,
    "c5.xlarge": 0.17,
    "r5.large": 0.126,
    "r5.xlarge": 0.252,
    "g4dn.xlarge": 0.526,
    "g4dn.2xlarge": 0.752,
    "p3.2xlarge": 3.06,
}
_DEFAULT_USD_PER_HOUR = 0.05

# Rough CPU-average draw in watts per instance family. Numbers are
# conservative mid-points of published vendor estimates for idle Linux VMs.
_INSTANCE_WATTS: dict[str, float] = {
    "t2.micro": 5.0, "t2.small": 7.0,
    "t3.micro": 5.0, "t3.small": 10.0, "t3.medium": 20.0,
    "t3.large": 35.0, "t3.xlarge": 70.0,
    "m5.large": 50.0, "m5.xlarge": 100.0, "m5.2xlarge": 200.0,
    "c5.large": 45.0, "c5.xlarge": 90.0,
    "r5.large": 60.0, "r5.xlarge": 120.0,
    "g4dn.xlarge": 300.0, "g4dn.2xlarge": 450.0,  # GPU boxes dominate
    "p3.2xlarge": 600.0,
}
_DEFAULT_WATTS = 25.0

# Grid carbon intensity by AWS region (kg CO2 / kWh). Rough public figures:
#   https://sustainability.aboutamazon.com/
#   https://ourworldindata.org/grapher/carbon-intensity-electricity
_REGION_CO2_KG_PER_KWH: dict[str, float] = {
    "us-east-1": 0.329,    # N. Virginia, grid-heavy
    "us-east-2": 0.455,    # Ohio, coal-heavy
    "us-west-1": 0.167,    # N. California, cleaner
    "us-west-2": 0.090,    # Oregon, very clean (hydro-heavy)
    "ap-south-1": 0.713,   # Mumbai, India grid
    "ap-southeast-1": 0.400,
    "ap-northeast-1": 0.472,
    "eu-west-1": 0.316,
    "eu-central-1": 0.311,
    "sa-east-1": 0.074,
}
_DEFAULT_CO2_KG_PER_KWH = 0.400


def _load_fixture(path: Path | None = None) -> dict[str, Any]:
    """Load the fixture file. In a real adapter this is where boto3 goes."""
    env_path = os.environ.get("AWS_FIXTURE_PATH")
    target = path or (Path(env_path) if env_path else DEFAULT_FIXTURE_PATH)
    if not target.exists():
        return {"instances": []}
    try:
        return yaml.safe_load(target.read_text()) or {"instances": []}
    except yaml.YAMLError as exc:
        return {"instances": [], "_error": f"invalid YAML in {target}: {exc}"}


def _parse_launch_time(raw: Any) -> datetime | None:
    """Accept either an ISO-8601 string or a datetime (PyYAML auto-parses).

    Always returns a timezone-aware UTC datetime, or None.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        dt = raw
    else:
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _human_time(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins and not days:
        parts.append(f"{mins}m")
    return " ".join(parts) or "<1m"


def list_instances(
    include_stopped: bool = False, fixture_path: Path | None = None
) -> dict[str, Any]:
    """Return every EC2-like instance in the fixture with cost/CO2 estimates.

    Returns:
        {
          "ok": bool,
          "source": "fixture" | "boto3",
          "fixture_path": "...",
          "instances": [ { ... } ],
          "totals": { "usd": ..., "inr": ..., "wh": ..., "co2_g": ... },
        }
    """
    data = _load_fixture(fixture_path)
    env_path = os.environ.get("AWS_FIXTURE_PATH")
    source_path = str(
        fixture_path or (Path(env_path) if env_path else DEFAULT_FIXTURE_PATH)
    )
    raw_instances = data.get("instances") or []

    now = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []
    for inst in raw_instances:
        state = (inst.get("state") or "running").lower()
        if state != "running" and not include_stopped:
            continue

        launch_dt = _parse_launch_time(inst.get("launch_time", ""))
        uptime_s = int((now - launch_dt).total_seconds()) if launch_dt else 0
        uptime_s = max(0, uptime_s)

        instance_type = inst.get("instance_type") or "unknown"
        region = inst.get("region") or "us-east-1"
        tags = inst.get("tags") or {}

        usd_per_hour = _INSTANCE_USD_PER_HOUR.get(instance_type, _DEFAULT_USD_PER_HOUR)
        watts = _INSTANCE_WATTS.get(instance_type, _DEFAULT_WATTS)
        region_co2 = _REGION_CO2_KG_PER_KWH.get(region, _DEFAULT_CO2_KG_PER_KWH)

        wh = cost.wh_from(watts, uptime_s)
        usd = usd_per_hour * (uptime_s / 3600.0)
        inr = usd * USD_INR
        co2_g = (wh / 1000.0) * region_co2 * 1000.0  # kWh * kg/kWh * g/kg

        results.append(
            {
                "id": f"aws:{inst.get('instance_id', '?')}",
                "name": tags.get("Name") or inst.get("instance_id", "?"),
                "kind": "aws",
                "instance_id": inst.get("instance_id"),
                "instance_type": instance_type,
                "region": region,
                "state": state,
                "tags": tags,
                "uptime_seconds": uptime_s,
                "uptime_human": _human_time(uptime_s),
                "usd_per_hour": round(usd_per_hour, 4),
                "estimated_watts": watts,
                "wh": round(wh, 2),
                "usd": round(usd, 2),
                "inr": round(inr, 2),
                "co2_g": round(co2_g, 2),
                "idle": True,  # fixture gives us no CPU% signal; running => potentially idle
            }
        )

    results.sort(key=lambda r: r["inr"], reverse=True)
    totals = {
        "usd": round(sum(r["usd"] for r in results), 2),
        "inr": round(sum(r["inr"] for r in results), 2),
        "wh": round(sum(r["wh"] for r in results), 2),
        "co2_g": round(sum(r["co2_g"] for r in results), 2),
    }

    return {
        "ok": True,
        "source": "fixture",
        "fixture_path": source_path,
        "note": (
            "This adapter is fixture-driven in v1 \u2014 numbers come from the YAML "
            "file above, not a live boto3 call. Replace _load_fixture() with "
            "ec2.describe_instances() to go live. Pricing is on-demand us-east-1 "
            "Linux; CO2 uses per-region grid intensity."
        ),
        "instances": results,
        "totals": totals,
    }


def terminate(instance_id: str, dry_run: bool = True) -> dict[str, Any]:
    """Placeholder for `ec2.stop_instances(InstanceIds=[...])`.

    In v1 we refuse to pretend we actually stopped an AWS instance; a dry-run
    returns what WOULD happen and `dry_run=False` returns a clear error so
    nobody is misled during the demo.
    """
    data = _load_fixture()
    match = next(
        (i for i in data.get("instances") or [] if i.get("instance_id") == instance_id),
        None,
    )
    if not match:
        return {"ok": False, "error": f"instance_id {instance_id} not in fixture"}
    plan = {
        "id": f"aws:{instance_id}",
        "name": (match.get("tags") or {}).get("Name") or instance_id,
        "instance_type": match.get("instance_type"),
        "region": match.get("region"),
    }
    if dry_run:
        return {"ok": True, "dry_run": True, "would_terminate": plan,
                "note": "Fixture-only adapter; a real boto3 call would be ec2.stop_instances."}
    return {
        "ok": False,
        "error": (
            "This v1 build does not call real AWS. Dry-run only. Plug in boto3 "
            "to enable actual stop_instances(). Plan was:"
        ),
        "plan": plan,
    }
