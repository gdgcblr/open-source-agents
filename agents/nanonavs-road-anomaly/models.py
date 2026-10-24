"""
NanoNavs Road Intelligence — Sensor Data Models

Defines the core data structures for road sensor telemetry,
detected anomalies, and generated incident reports.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class AnomalyType(Enum):
    """Classification of road surface anomalies."""
    POTHOLE = "pothole"
    SPEED_BUMP = "speed_bump"
    CRACK = "crack"
    SURFACE_DEPRESSION = "surface_depression"
    MANHOLE_COVER = "manhole_cover"
    ROAD_JOINT = "road_joint"
    DEBRIS = "debris"
    UNKNOWN = "unknown"


class SeverityLevel(Enum):
    """Risk severity classification for detected anomalies."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class GPSCoordinate:
    """Geographic position with precision metadata."""
    latitude: float
    longitude: float
    altitude_m: float = 0.0
    hdop: float = 1.0  # Horizontal dilution of precision

    def to_dict(self) -> dict:
        return {
            "latitude": round(self.latitude, 6),
            "longitude": round(self.longitude, 6),
            "altitude_m": round(self.altitude_m, 2),
            "hdop": self.hdop,
        }

    def __str__(self) -> str:
        return f"({self.latitude:.6f}, {self.longitude:.6f})"


@dataclass
class AccelerometerReading:
    """Three-axis accelerometer sample from a vehicle-mounted sensor."""
    x: float  # Lateral acceleration (g)
    y: float  # Longitudinal acceleration (g)
    z: float  # Vertical acceleration (g)
    timestamp: float  # Unix epoch seconds

    @property
    def vertical_magnitude(self) -> float:
        """Absolute deviation from 1g on the Z-axis (road impact indicator)."""
        return abs(self.z - 1.0)

    @property
    def total_magnitude(self) -> float:
        """Total acceleration magnitude."""
        return (self.x ** 2 + self.y ** 2 + self.z ** 2) ** 0.5

    def to_dict(self) -> dict:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "z": round(self.z, 4),
            "timestamp": self.timestamp,
            "vertical_magnitude": round(self.vertical_magnitude, 4),
        }


@dataclass
class AcousticReading:
    """Microphone-based road noise measurement."""
    decibel_level: float  # dB SPL
    dominant_frequency_hz: float  # Hz
    timestamp: float

    def to_dict(self) -> dict:
        return {
            "decibel_level": round(self.decibel_level, 1),
            "dominant_frequency_hz": round(self.dominant_frequency_hz, 1),
            "timestamp": self.timestamp,
        }


@dataclass
class SensorFrame:
    """A single time-synchronised frame of all sensor inputs."""
    frame_id: str
    timestamp: float
    gps: GPSCoordinate
    accelerometer: AccelerometerReading
    acoustic: Optional[AcousticReading] = None
    vehicle_speed_kmh: float = 0.0

    def to_dict(self) -> dict:
        result = {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "gps": self.gps.to_dict(),
            "accelerometer": self.accelerometer.to_dict(),
            "vehicle_speed_kmh": round(self.vehicle_speed_kmh, 1),
        }
        if self.acoustic:
            result["acoustic"] = self.acoustic.to_dict()
        return result


@dataclass
class DetectedAnomaly:
    """A confirmed road anomaly detection with classification and evidence."""
    anomaly_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    anomaly_type: AnomalyType = AnomalyType.UNKNOWN
    severity: SeverityLevel = SeverityLevel.LOW
    confidence: float = 0.0  # 0.0 to 1.0
    location: Optional[GPSCoordinate] = None
    timestamp: float = 0.0
    peak_vertical_g: float = 0.0
    peak_acoustic_db: float = 0.0
    vehicle_speed_kmh: float = 0.0
    evidence_frames: list = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "anomaly_id": self.anomaly_id,
            "anomaly_type": self.anomaly_type.value,
            "severity": self.severity.value,
            "confidence": round(self.confidence, 3),
            "location": self.location.to_dict() if self.location else None,
            "timestamp": self.timestamp,
            "peak_vertical_g": round(self.peak_vertical_g, 4),
            "peak_acoustic_db": round(self.peak_acoustic_db, 1),
            "vehicle_speed_kmh": round(self.vehicle_speed_kmh, 1),
            "description": self.description,
        }


@dataclass
class IncidentReport:
    """A complete incident report aggregating detected anomalies on a route."""
    report_id: str = field(default_factory=lambda: f"RPT-{uuid.uuid4().hex[:8].upper()}")
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    route_name: str = ""
    total_distance_km: float = 0.0
    total_frames_analysed: int = 0
    anomalies: list = field(default_factory=list)
    road_quality_score: float = 100.0  # 0-100, higher is better
    summary: str = ""
    ai_narrative: str = ""  # Optional Gemini-enhanced narrative

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "route_name": self.route_name,
            "total_distance_km": round(self.total_distance_km, 2),
            "total_frames_analysed": self.total_frames_analysed,
            "anomaly_count": len(self.anomalies),
            "anomalies": [a.to_dict() for a in self.anomalies],
            "road_quality_score": round(self.road_quality_score, 1),
            "summary": self.summary,
            "ai_narrative": self.ai_narrative,
        }
