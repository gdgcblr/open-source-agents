"""
NanoNavs Road Intelligence — Anomaly Detector

Deterministic signal-processing engine that analyses accelerometer and
acoustic sensor streams to detect and classify road surface anomalies.

This module uses threshold-based detection with sliding-window analysis.
No machine-learning model or external API is required at this layer.
"""

import statistics
from typing import List, Optional

from models import (
    AccelerometerReading,
    AcousticReading,
    AnomalyType,
    DetectedAnomaly,
    GPSCoordinate,
    SensorFrame,
    SeverityLevel,
)


# ── Detection thresholds (empirically calibrated) ────────────────────────────

# Vertical G-force thresholds for anomaly classification
THRESHOLD_POTHOLE_G = 0.45        # Strong downward jolt
THRESHOLD_SPEED_BUMP_G = 0.30     # Moderate sustained bump
THRESHOLD_CRACK_G = 0.15          # Minor surface irregularity
THRESHOLD_NOISE_FLOOR_G = 0.08    # Below this, considered smooth road

# Acoustic thresholds
THRESHOLD_IMPACT_DB = 78.0        # Loud impact noise
THRESHOLD_RUMBLE_DB = 65.0        # Low-frequency rumble

# Classification frequency bands (Hz)
FREQ_POTHOLE_LOW = 20.0
FREQ_POTHOLE_HIGH = 80.0
FREQ_CRACK_LOW = 100.0
FREQ_CRACK_HIGH = 300.0
FREQ_DEBRIS_LOW = 500.0

# Speed-based sensitivity adjustment
SPEED_AMPLIFICATION_FACTOR = 0.02  # Per km/h above 30


class AnomalyDetector:
    """
    Deterministic road anomaly detector using multi-sensor fusion.

    Processes a stream of SensorFrames and returns classified DetectedAnomaly
    objects with severity ratings and confidence scores.
    """

    def __init__(
        self,
        window_size: int = 5,
        min_confidence: float = 0.4,
        enable_acoustic: bool = True,
    ):
        """
        Args:
            window_size: Number of frames in the sliding analysis window.
            min_confidence: Minimum confidence score to emit a detection.
            enable_acoustic: Whether to use acoustic data for fusion.
        """
        self.window_size = window_size
        self.min_confidence = min_confidence
        self.enable_acoustic = enable_acoustic
        self._window: List[SensorFrame] = []
        self._detections: List[DetectedAnomaly] = []
        self._cooldown_frames = 0

    def process_frame(self, frame: SensorFrame) -> Optional[DetectedAnomaly]:
        """
        Process a single sensor frame through the detection pipeline.

        Returns a DetectedAnomaly if one is found, or None.
        """
        self._window.append(frame)
        if len(self._window) > self.window_size:
            self._window.pop(0)

        # Cooldown prevents double-triggering on the same physical event
        if self._cooldown_frames > 0:
            self._cooldown_frames -= 1
            return None

        if len(self._window) < 3:
            return None

        detection = self._analyse_window(frame)
        if detection and detection.confidence >= self.min_confidence:
            self._detections.append(detection)
            self._cooldown_frames = 2  # Skip next 2 frames
            return detection

        return None

    def process_batch(self, frames: List[SensorFrame]) -> List[DetectedAnomaly]:
        """Process a batch of frames and return all detections."""
        results = []
        for frame in frames:
            detection = self.process_frame(frame)
            if detection:
                results.append(detection)
        return results

    def reset(self):
        """Clear the detector state for a new route."""
        self._window.clear()
        self._detections.clear()
        self._cooldown_frames = 0

    def _analyse_window(self, current_frame: SensorFrame) -> Optional[DetectedAnomaly]:
        """Run multi-sensor analysis on the current sliding window."""
        accel = current_frame.accelerometer
        v_mag = accel.vertical_magnitude

        # Compute window statistics for baseline comparison
        window_z_values = [f.accelerometer.z for f in self._window]
        baseline_std = statistics.stdev(window_z_values) if len(window_z_values) > 1 else 0.0
        z_deviation = abs(accel.z - statistics.mean(window_z_values))

        # Speed-adjusted sensitivity
        speed_factor = 1.0
        if current_frame.vehicle_speed_kmh > 30:
            speed_factor = 1.0 + (current_frame.vehicle_speed_kmh - 30) * SPEED_AMPLIFICATION_FACTOR

        adjusted_v_mag = v_mag * speed_factor

        # ── Primary classification via accelerometer ──────────────────────
        anomaly_type = AnomalyType.UNKNOWN
        base_confidence = 0.0

        if adjusted_v_mag >= THRESHOLD_POTHOLE_G:
            anomaly_type = AnomalyType.POTHOLE
            base_confidence = min(0.6 + (adjusted_v_mag - THRESHOLD_POTHOLE_G) * 1.5, 0.95)
        elif adjusted_v_mag >= THRESHOLD_SPEED_BUMP_G:
            # Distinguish speed bumps from depressions by Z-axis profile
            if self._is_symmetric_bump():
                anomaly_type = AnomalyType.SPEED_BUMP
            else:
                anomaly_type = AnomalyType.SURFACE_DEPRESSION
            base_confidence = min(0.5 + (adjusted_v_mag - THRESHOLD_SPEED_BUMP_G) * 2.0, 0.90)
        elif adjusted_v_mag >= THRESHOLD_CRACK_G:
            anomaly_type = AnomalyType.CRACK
            base_confidence = min(0.4 + (adjusted_v_mag - THRESHOLD_CRACK_G) * 1.8, 0.80)
        else:
            return None  # Below noise floor

        # ── Acoustic fusion (when available) ──────────────────────────────
        acoustic_boost = 0.0
        if self.enable_acoustic and current_frame.acoustic:
            acoustic_boost = self._acoustic_classification(
                current_frame.acoustic, anomaly_type
            )

        final_confidence = min(base_confidence + acoustic_boost, 0.99)

        # ── Severity classification ───────────────────────────────────────
        severity = self._classify_severity(anomaly_type, adjusted_v_mag, final_confidence)

        # ── Build detection ───────────────────────────────────────────────
        detection = DetectedAnomaly(
            anomaly_type=anomaly_type,
            severity=severity,
            confidence=final_confidence,
            location=current_frame.gps,
            timestamp=current_frame.timestamp,
            peak_vertical_g=adjusted_v_mag,
            peak_acoustic_db=(
                current_frame.acoustic.decibel_level if current_frame.acoustic else 0.0
            ),
            vehicle_speed_kmh=current_frame.vehicle_speed_kmh,
            evidence_frames=[f.frame_id for f in self._window],
            description=self._generate_description(anomaly_type, severity, adjusted_v_mag),
        )

        return detection

    def _is_symmetric_bump(self) -> bool:
        """Check if the Z-axis profile is symmetric (characteristic of speed bumps)."""
        if len(self._window) < 3:
            return False

        z_values = [f.accelerometer.z for f in self._window]
        mid = len(z_values) // 2

        # Speed bump: rises then falls symmetrically
        first_half = z_values[:mid]
        second_half = z_values[mid + 1:]

        if not first_half or not second_half:
            return False

        rising = all(
            first_half[i] <= first_half[i + 1]
            for i in range(len(first_half) - 1)
        ) if len(first_half) > 1 else True
        falling = all(
            second_half[i] >= second_half[i + 1]
            for i in range(len(second_half) - 1)
        ) if len(second_half) > 1 else True

        return rising and falling

    def _acoustic_classification(
        self, acoustic: AcousticReading, primary_type: AnomalyType
    ) -> float:
        """Calculate confidence boost from acoustic data corroboration."""
        boost = 0.0
        freq = acoustic.dominant_frequency_hz
        db = acoustic.decibel_level

        if primary_type == AnomalyType.POTHOLE:
            # Potholes produce low-frequency thuds
            if FREQ_POTHOLE_LOW <= freq <= FREQ_POTHOLE_HIGH and db >= THRESHOLD_IMPACT_DB:
                boost = 0.15
            elif db >= THRESHOLD_IMPACT_DB:
                boost = 0.08
        elif primary_type == AnomalyType.CRACK:
            # Cracks produce mid-frequency buzzing
            if FREQ_CRACK_LOW <= freq <= FREQ_CRACK_HIGH and db >= THRESHOLD_RUMBLE_DB:
                boost = 0.10
        elif primary_type in (AnomalyType.SPEED_BUMP, AnomalyType.SURFACE_DEPRESSION):
            # Speed bumps produce sustained low rumble
            if freq <= FREQ_POTHOLE_HIGH and db >= THRESHOLD_RUMBLE_DB:
                boost = 0.12
        elif db >= THRESHOLD_IMPACT_DB and freq >= FREQ_DEBRIS_LOW:
            # High-frequency impact suggests debris
            boost = 0.10

        return boost

    def _classify_severity(
        self, anomaly_type: AnomalyType, v_mag: float, confidence: float
    ) -> SeverityLevel:
        """Determine severity level from anomaly type, magnitude, and confidence."""
        if anomaly_type == AnomalyType.POTHOLE:
            if v_mag >= 0.8 and confidence >= 0.8:
                return SeverityLevel.CRITICAL
            elif v_mag >= 0.6:
                return SeverityLevel.HIGH
            else:
                return SeverityLevel.MODERATE
        elif anomaly_type in (AnomalyType.SPEED_BUMP, AnomalyType.SURFACE_DEPRESSION):
            if v_mag >= 0.5:
                return SeverityLevel.MODERATE
            else:
                return SeverityLevel.LOW
        elif anomaly_type == AnomalyType.CRACK:
            if v_mag >= 0.3:
                return SeverityLevel.MODERATE
            else:
                return SeverityLevel.LOW
        else:
            return SeverityLevel.LOW

    @staticmethod
    def _generate_description(
        anomaly_type: AnomalyType, severity: SeverityLevel, v_mag: float
    ) -> str:
        """Generate a human-readable description of the detected anomaly."""
        descriptions = {
            AnomalyType.POTHOLE: f"Pothole detected with {v_mag:.2f}g vertical impact",
            AnomalyType.SPEED_BUMP: f"Speed bump identified with {v_mag:.2f}g displacement",
            AnomalyType.CRACK: f"Road surface crack detected ({v_mag:.2f}g vibration)",
            AnomalyType.SURFACE_DEPRESSION: f"Surface depression found ({v_mag:.2f}g sag)",
            AnomalyType.MANHOLE_COVER: f"Manhole cover impact ({v_mag:.2f}g jolt)",
            AnomalyType.ROAD_JOINT: f"Road joint expansion gap ({v_mag:.2f}g bump)",
            AnomalyType.DEBRIS: f"Road debris impact detected ({v_mag:.2f}g)",
            AnomalyType.UNKNOWN: f"Unclassified road irregularity ({v_mag:.2f}g)",
        }
        base = descriptions.get(anomaly_type, f"Anomaly ({v_mag:.2f}g)")
        return f"[{severity.value.upper()}] {base}"
