"""
NanoNavs Road Intelligence — Synthetic Data Generator

Produces realistic synthetic sensor telemetry for demonstration and testing.
Simulates a vehicle driving along a route with configurable road conditions,
including embedded anomalies at known locations.

All coordinates use the Bengaluru metro area for realistic demonstration data.
"""

import math
import random
import time
import uuid
from typing import List, Tuple

from models import (
    AccelerometerReading,
    AcousticReading,
    AnomalyType,
    GPSCoordinate,
    SensorFrame,
)


# ── Bengaluru route reference points ─────────────────────────────────────────

BENGALURU_ROUTES = {
    "electronic-city-to-koramangala": {
        "name": "Electronic City → Koramangala (Hosur Road)",
        "start": (12.8399, 77.6770),
        "end": (12.9352, 77.6245),
        "distance_km": 15.2,
        "description": "Major IT corridor connecting Electronic City to central Bengaluru",
    },
    "silk-board-to-marathahalli": {
        "name": "Silk Board → Marathahalli (ORR)",
        "start": (12.9173, 77.6230),
        "end": (12.9591, 77.7012),
        "distance_km": 11.8,
        "description": "Outer Ring Road stretch — notoriously congested and pothole-prone",
    },
    "hebbal-to-airport": {
        "name": "Hebbal → KIA Airport (NH-44)",
        "start": (13.0358, 77.5970),
        "end": (13.1986, 77.7066),
        "distance_km": 25.0,
        "description": "National Highway connecting city to Kempegowda International Airport",
    },
    "jayanagar-to-jp-nagar": {
        "name": "Jayanagar → JP Nagar (Local Roads)",
        "start": (12.9250, 77.5938),
        "end": (12.9100, 77.5850),
        "distance_km": 4.5,
        "description": "Residential area roads with mixed surface quality",
    },
}


# ── Anomaly injection profiles ───────────────────────────────────────────────

ANOMALY_PROFILES = {
    AnomalyType.POTHOLE: {
        "z_spike": (1.5, 2.8),       # G-force range on Z-axis
        "duration_frames": (1, 3),
        "acoustic_db": (80, 95),
        "acoustic_freq": (30, 70),
    },
    AnomalyType.SPEED_BUMP: {
        "z_spike": (1.3, 1.7),
        "duration_frames": (3, 6),
        "acoustic_db": (65, 78),
        "acoustic_freq": (25, 55),
    },
    AnomalyType.CRACK: {
        "z_spike": (1.15, 1.35),
        "duration_frames": (1, 2),
        "acoustic_db": (60, 72),
        "acoustic_freq": (120, 250),
    },
    AnomalyType.SURFACE_DEPRESSION: {
        "z_spike": (1.3, 1.6),
        "duration_frames": (2, 4),
        "acoustic_db": (55, 68),
        "acoustic_freq": (40, 90),
    },
    AnomalyType.DEBRIS: {
        "z_spike": (1.2, 1.5),
        "duration_frames": (1, 2),
        "acoustic_db": (75, 90),
        "acoustic_freq": (500, 1200),
    },
}


def generate_route_data(
    route_key: str = "silk-board-to-marathahalli",
    num_frames: int = 200,
    anomaly_density: float = 0.08,
    seed: int = 42,
    base_speed_kmh: float = 35.0,
) -> Tuple[List[SensorFrame], dict]:
    """
    Generate synthetic sensor data for a simulated drive along a Bengaluru route.

    Args:
        route_key: Key from BENGALURU_ROUTES to use as the route template.
        num_frames: Total number of sensor frames to generate.
        anomaly_density: Fraction of frames that contain injected anomalies (0.0 to 0.3).
        seed: Random seed for reproducibility.
        base_speed_kmh: Average vehicle speed.

    Returns:
        Tuple of (list of SensorFrames, route metadata dict).
    """
    rng = random.Random(seed)
    route = BENGALURU_ROUTES.get(route_key, BENGALURU_ROUTES["silk-board-to-marathahalli"])

    start_lat, start_lon = route["start"]
    end_lat, end_lon = route["end"]

    # Plan anomaly injection points
    num_anomalies = max(1, int(num_frames * anomaly_density))
    anomaly_indices = set(rng.sample(range(10, num_frames - 5), min(num_anomalies, num_frames - 15)))
    anomaly_types_pool = list(ANOMALY_PROFILES.keys())

    frames: List[SensorFrame] = []
    base_time = time.time() - num_frames * 0.1  # Backdate for realism
    active_anomaly = None
    active_anomaly_remaining = 0

    injected_anomalies = []  # Track ground truth for validation

    for i in range(num_frames):
        progress = i / max(num_frames - 1, 1)

        # ── GPS interpolation with slight jitter ──────────────────────
        lat = start_lat + (end_lat - start_lat) * progress + rng.gauss(0, 0.00005)
        lon = start_lon + (end_lon - start_lon) * progress + rng.gauss(0, 0.00005)
        alt = 900 + rng.gauss(0, 2)  # Bengaluru ~900m elevation
        gps = GPSCoordinate(latitude=lat, longitude=lon, altitude_m=alt, hdop=rng.uniform(0.8, 2.0))

        # ── Speed variation ───────────────────────────────────────────
        speed = base_speed_kmh + rng.gauss(0, 5) + 10 * math.sin(progress * math.pi * 4)
        speed = max(5, min(80, speed))

        # ── Baseline accelerometer (smooth road) ─────────────────────
        base_x = rng.gauss(0, 0.02)
        base_y = rng.gauss(0, 0.03)
        base_z = 1.0 + rng.gauss(0, 0.03)

        # ── Baseline acoustic ────────────────────────────────────────
        base_db = 45 + rng.gauss(0, 3) + speed * 0.2
        base_freq = 200 + rng.gauss(0, 30)

        # ── Inject anomaly if scheduled ──────────────────────────────
        if i in anomaly_indices and active_anomaly_remaining == 0:
            anomaly_type = rng.choice(anomaly_types_pool)
            profile = ANOMALY_PROFILES[anomaly_type]
            active_anomaly = {
                "type": anomaly_type,
                "z_spike": rng.uniform(*profile["z_spike"]),
                "db": rng.uniform(*profile["acoustic_db"]),
                "freq": rng.uniform(*profile["acoustic_freq"]),
            }
            active_anomaly_remaining = rng.randint(*profile["duration_frames"])
            injected_anomalies.append({
                "frame_index": i,
                "type": anomaly_type.value,
                "location": gps.to_dict(),
            })

        if active_anomaly_remaining > 0:
            # Apply anomaly perturbation
            anom = active_anomaly
            base_z = anom["z_spike"] + rng.gauss(0, 0.05)
            base_x += rng.gauss(0, 0.1)
            base_y += rng.gauss(0, 0.08)
            base_db = anom["db"] + rng.gauss(0, 2)
            base_freq = anom["freq"] + rng.gauss(0, 10)
            active_anomaly_remaining -= 1

        timestamp = base_time + i * 0.1  # 10 Hz sampling rate

        accel = AccelerometerReading(x=base_x, y=base_y, z=base_z, timestamp=timestamp)
        acoustic = AcousticReading(
            decibel_level=max(20, base_db),
            dominant_frequency_hz=max(10, base_freq),
            timestamp=timestamp,
        )

        frame = SensorFrame(
            frame_id=f"F-{uuid.uuid4().hex[:6]}",
            timestamp=timestamp,
            gps=gps,
            accelerometer=accel,
            acoustic=acoustic,
            vehicle_speed_kmh=speed,
        )
        frames.append(frame)

    route_metadata = {
        **route,
        "num_frames": num_frames,
        "sampling_rate_hz": 10,
        "anomaly_density": anomaly_density,
        "injected_anomaly_count": len(injected_anomalies),
        "ground_truth": injected_anomalies,
        "seed": seed,
    }

    return frames, route_metadata


def generate_sample_csv(
    route_key: str = "silk-board-to-marathahalli",
    num_frames: int = 200,
    seed: int = 42,
) -> str:
    """
    Generate a CSV string of sensor data for file-based demonstration.

    Returns:
        CSV-formatted string with headers.
    """
    frames, _ = generate_route_data(route_key=route_key, num_frames=num_frames, seed=seed)

    lines = ["frame_id,timestamp,latitude,longitude,accel_x,accel_y,accel_z,speed_kmh,db_level,freq_hz"]
    for f in frames:
        lines.append(
            f"{f.frame_id},{f.timestamp:.3f},{f.gps.latitude:.6f},{f.gps.longitude:.6f},"
            f"{f.accelerometer.x:.4f},{f.accelerometer.y:.4f},{f.accelerometer.z:.4f},"
            f"{f.vehicle_speed_kmh:.1f},"
            f"{f.acoustic.decibel_level:.1f},{f.acoustic.dominant_frequency_hz:.1f}"
        )

    return "\n".join(lines)
