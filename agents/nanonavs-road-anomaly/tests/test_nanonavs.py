"""
NanoNavs Road Intelligence — Test Suite

Comprehensive tests covering:
  1. Data model serialisation and validation
  2. Anomaly detection accuracy and classification
  3. Sensor data generation consistency
  4. Report generation and quality scoring
  5. Edge cases and error handling
  6. CSV analysis pipeline

Run:
    cd agents/nanonavs-road-anomaly
    pytest tests/ -v
"""

import json
import os
import sys

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    AccelerometerReading,
    AcousticReading,
    AnomalyType,
    DetectedAnomaly,
    GPSCoordinate,
    IncidentReport,
    SensorFrame,
    SeverityLevel,
)
from detector import AnomalyDetector
from sensor_data import BENGALURU_ROUTES, generate_route_data, generate_sample_csv
from report_generator import ReportGenerator


# ══════════════════════════════════════════════════════════════════════════════
# 1. DATA MODEL TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestGPSCoordinate:
    def test_to_dict(self):
        gps = GPSCoordinate(latitude=12.9716, longitude=77.5946, altitude_m=920.5)
        d = gps.to_dict()
        assert d["latitude"] == 12.9716
        assert d["longitude"] == 77.5946
        assert d["altitude_m"] == 920.5

    def test_str_representation(self):
        gps = GPSCoordinate(latitude=12.9716, longitude=77.5946)
        s = str(gps)
        assert "12.971600" in s
        assert "77.594600" in s


class TestAccelerometerReading:
    def test_vertical_magnitude_smooth_road(self):
        reading = AccelerometerReading(x=0.0, y=0.0, z=1.0, timestamp=0.0)
        assert reading.vertical_magnitude == pytest.approx(0.0, abs=0.001)

    def test_vertical_magnitude_pothole(self):
        reading = AccelerometerReading(x=0.0, y=0.0, z=1.8, timestamp=0.0)
        assert reading.vertical_magnitude == pytest.approx(0.8, abs=0.001)

    def test_total_magnitude(self):
        reading = AccelerometerReading(x=0.0, y=0.0, z=1.0, timestamp=0.0)
        assert reading.total_magnitude == pytest.approx(1.0, abs=0.001)

    def test_serialisation(self):
        reading = AccelerometerReading(x=0.1, y=-0.2, z=1.5, timestamp=100.0)
        d = reading.to_dict()
        assert "vertical_magnitude" in d
        assert d["z"] == 1.5


class TestDetectedAnomaly:
    def test_default_id_generation(self):
        a1 = DetectedAnomaly()
        a2 = DetectedAnomaly()
        assert a1.anomaly_id != a2.anomaly_id

    def test_serialisation(self):
        anomaly = DetectedAnomaly(
            anomaly_type=AnomalyType.POTHOLE,
            severity=SeverityLevel.HIGH,
            confidence=0.85,
            location=GPSCoordinate(12.9, 77.6),
        )
        d = anomaly.to_dict()
        assert d["anomaly_type"] == "pothole"
        assert d["severity"] == "high"
        assert d["confidence"] == 0.85


class TestIncidentReport:
    def test_default_report_id(self):
        report = IncidentReport()
        assert report.report_id.startswith("RPT-")

    def test_serialisation_empty(self):
        report = IncidentReport(route_name="Test Route")
        d = report.to_dict()
        assert d["anomaly_count"] == 0
        assert d["route_name"] == "Test Route"


# ══════════════════════════════════════════════════════════════════════════════
# 2. ANOMALY DETECTOR TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestAnomalyDetector:
    @staticmethod
    def _make_frame(z_value: float, frame_index: int = 0, speed: float = 40.0) -> SensorFrame:
        """Helper to create a SensorFrame with a specific Z-axis value."""
        return SensorFrame(
            frame_id=f"F-{frame_index:04d}",
            timestamp=1000.0 + frame_index * 0.1,
            gps=GPSCoordinate(12.9 + frame_index * 0.0001, 77.6),
            accelerometer=AccelerometerReading(
                x=0.0, y=0.0, z=z_value, timestamp=1000.0 + frame_index * 0.1
            ),
            acoustic=AcousticReading(
                decibel_level=50.0, dominant_frequency_hz=200.0,
                timestamp=1000.0 + frame_index * 0.1,
            ),
            vehicle_speed_kmh=speed,
        )

    def test_smooth_road_no_detections(self):
        """Smooth road (Z ≈ 1.0g) should produce zero detections."""
        detector = AnomalyDetector()
        frames = [self._make_frame(1.0 + i * 0.001, i) for i in range(20)]
        detections = detector.process_batch(frames)
        assert len(detections) == 0

    def test_pothole_detection(self):
        """Large Z-spike should be detected as a pothole."""
        detector = AnomalyDetector(window_size=5, min_confidence=0.3)

        # Build smooth baseline then inject spike
        frames = [self._make_frame(1.0, i) for i in range(10)]
        frames.append(self._make_frame(1.8, 10))  # Pothole spike
        frames.extend([self._make_frame(1.0, i) for i in range(11, 20)])

        detections = detector.process_batch(frames)
        assert len(detections) >= 1
        assert any(d.anomaly_type == AnomalyType.POTHOLE for d in detections)

    def test_crack_detection(self):
        """Moderate Z-deviation should be detected as a crack."""
        detector = AnomalyDetector(window_size=5, min_confidence=0.3)

        frames = [self._make_frame(1.0, i) for i in range(10)]
        frames.append(self._make_frame(1.2, 10))  # Crack-level spike
        frames.extend([self._make_frame(1.0, i) for i in range(11, 20)])

        detections = detector.process_batch(frames)
        # Should detect as crack or similar minor anomaly
        assert len(detections) >= 1

    def test_confidence_threshold_filtering(self):
        """Detections below min_confidence should be filtered out."""
        detector_strict = AnomalyDetector(min_confidence=0.9)
        detector_loose = AnomalyDetector(min_confidence=0.2)

        frames = [self._make_frame(1.0, i) for i in range(10)]
        frames.append(self._make_frame(1.2, 10))  # Marginal spike
        frames.extend([self._make_frame(1.0, i) for i in range(11, 20)])

        strict_detections = detector_strict.process_batch(frames)
        loose_detections = detector_loose.process_batch(frames)

        assert len(strict_detections) <= len(loose_detections)

    def test_cooldown_prevents_duplicate(self):
        """Cooldown mechanism should prevent double-triggering."""
        detector = AnomalyDetector(window_size=3, min_confidence=0.3)

        frames = [self._make_frame(1.0, i) for i in range(5)]
        # Two adjacent spikes should count as one event
        frames.append(self._make_frame(1.8, 5))
        frames.append(self._make_frame(1.7, 6))
        frames.extend([self._make_frame(1.0, i) for i in range(7, 15)])

        detections = detector.process_batch(frames)
        # Should be 1 detection, not 2 (cooldown active)
        assert len(detections) == 1

    def test_reset_clears_state(self):
        """Reset should clear internal state for a new route."""
        detector = AnomalyDetector()
        frames = [self._make_frame(1.8, i) for i in range(10)]
        detector.process_batch(frames)

        detector.reset()
        assert len(detector._window) == 0
        assert len(detector._detections) == 0

    def test_batch_vs_sequential(self):
        """Batch processing should produce same results as sequential."""
        frames = [self._make_frame(1.0, i) for i in range(10)]
        frames.append(self._make_frame(1.8, 10))
        frames.extend([self._make_frame(1.0, i) for i in range(11, 20)])

        detector1 = AnomalyDetector(min_confidence=0.3)
        batch_results = detector1.process_batch(frames)

        detector2 = AnomalyDetector(min_confidence=0.3)
        sequential_results = []
        for f in frames:
            d = detector2.process_frame(f)
            if d:
                sequential_results.append(d)

        assert len(batch_results) == len(sequential_results)


# ══════════════════════════════════════════════════════════════════════════════
# 3. SENSOR DATA GENERATION TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestSensorDataGeneration:
    def test_default_generation(self):
        """Default generation should produce valid frames."""
        frames, metadata = generate_route_data()
        assert len(frames) == 200
        assert metadata["injected_anomaly_count"] > 0

    def test_all_routes_generate(self):
        """All predefined routes should generate data successfully."""
        for route_key in BENGALURU_ROUTES:
            frames, metadata = generate_route_data(route_key=route_key, num_frames=50)
            assert len(frames) == 50
            assert "ground_truth" in metadata

    def test_reproducibility(self):
        """Same seed should produce identical data."""
        frames1, _ = generate_route_data(seed=123, num_frames=50)
        frames2, _ = generate_route_data(seed=123, num_frames=50)

        for f1, f2 in zip(frames1, frames2):
            assert f1.accelerometer.z == f2.accelerometer.z
            assert f1.gps.latitude == f2.gps.latitude

    def test_different_seeds_different_data(self):
        """Different seeds should produce different data."""
        frames1, _ = generate_route_data(seed=1, num_frames=50)
        frames2, _ = generate_route_data(seed=2, num_frames=50)

        z_values1 = [f.accelerometer.z for f in frames1]
        z_values2 = [f.accelerometer.z for f in frames2]
        assert z_values1 != z_values2

    def test_gps_interpolation(self):
        """GPS coordinates should progress from start to end of route."""
        frames, _ = generate_route_data(
            route_key="silk-board-to-marathahalli", num_frames=100
        )
        route = BENGALURU_ROUTES["silk-board-to-marathahalli"]

        first_lat = frames[0].gps.latitude
        last_lat = frames[-1].gps.latitude

        # Should be roughly between start and end latitudes
        assert abs(first_lat - route["start"][0]) < 0.01
        assert abs(last_lat - route["end"][0]) < 0.01

    def test_anomaly_density(self):
        """Higher density should inject more anomalies."""
        _, meta_low = generate_route_data(anomaly_density=0.02, num_frames=200)
        _, meta_high = generate_route_data(anomaly_density=0.20, num_frames=200)

        assert meta_high["injected_anomaly_count"] > meta_low["injected_anomaly_count"]

    def test_csv_generation(self):
        """CSV output should be valid and contain expected columns."""
        csv = generate_sample_csv(num_frames=50)
        lines = csv.strip().split("\n")
        assert len(lines) == 51  # Header + 50 data rows

        header = lines[0]
        assert "frame_id" in header
        assert "accel_z" in header
        assert "latitude" in header


# ══════════════════════════════════════════════════════════════════════════════
# 4. REPORT GENERATOR TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestReportGenerator:
    def test_empty_anomalies(self):
        """Report with no anomalies should have quality score 100."""
        gen = ReportGenerator()
        report = gen.generate(
            anomalies=[],
            route_name="Test Route",
            total_distance_km=10.0,
            total_frames=100,
        )
        assert report.road_quality_score == 100.0
        assert "No anomalies" in report.summary

    def test_quality_score_decreases_with_severity(self):
        """More severe anomalies should lower the quality score."""
        gen = ReportGenerator()

        low_anomalies = [
            DetectedAnomaly(severity=SeverityLevel.LOW, confidence=0.5)
            for _ in range(3)
        ]
        high_anomalies = [
            DetectedAnomaly(severity=SeverityLevel.CRITICAL, confidence=0.9)
            for _ in range(3)
        ]

        report_low = gen.generate(low_anomalies, total_distance_km=10.0, total_frames=100)
        report_high = gen.generate(high_anomalies, total_distance_km=10.0, total_frames=100)

        assert report_low.road_quality_score > report_high.road_quality_score

    def test_summary_contains_route_info(self):
        """Summary should mention the route name."""
        gen = ReportGenerator()
        report = gen.generate(
            anomalies=[DetectedAnomaly(
                anomaly_type=AnomalyType.POTHOLE,
                severity=SeverityLevel.HIGH,
                confidence=0.8,
                peak_vertical_g=0.6,
                location=GPSCoordinate(12.9, 77.6),
            )],
            route_name="Silk Board to Marathahalli",
            total_distance_km=11.8,
            total_frames=200,
        )
        assert "Silk Board" in report.summary

    def test_report_serialisation_roundtrip(self):
        """Report should survive JSON serialisation."""
        gen = ReportGenerator()
        report = gen.generate(
            anomalies=[DetectedAnomaly(
                anomaly_type=AnomalyType.CRACK,
                severity=SeverityLevel.LOW,
                confidence=0.5,
            )],
            route_name="Test",
            total_frames=50,
        )
        json_str = json.dumps(report.to_dict())
        parsed = json.loads(json_str)
        assert parsed["anomaly_count"] == 1
        assert parsed["route_name"] == "Test"

    def test_ai_narrative_without_key(self):
        """Without API key, AI narrative should be empty string."""
        # Ensure no key is set
        old_key = os.environ.pop("GEMINI_API_KEY", None)
        try:
            gen = ReportGenerator()
            report = gen.generate(anomalies=[], route_name="Test", total_frames=10)
            assert report.ai_narrative == ""
        finally:
            if old_key:
                os.environ["GEMINI_API_KEY"] = old_key


# ══════════════════════════════════════════════════════════════════════════════
# 5. END-TO-END PIPELINE TEST
# ══════════════════════════════════════════════════════════════════════════════


class TestEndToEndPipeline:
    def test_full_pipeline(self):
        """Full pipeline: generate → detect → report should work end-to-end."""
        # Generate
        frames, metadata = generate_route_data(
            route_key="silk-board-to-marathahalli",
            num_frames=200,
            anomaly_density=0.08,
            seed=42,
        )

        # Detect
        detector = AnomalyDetector(window_size=5, min_confidence=0.4)
        detections = detector.process_batch(frames)

        # Report
        gen = ReportGenerator()
        report = gen.generate(
            anomalies=detections,
            route_name="Silk Board → Marathahalli",
            total_distance_km=11.8,
            total_frames=len(frames),
        )

        # Validate
        assert len(frames) == 200
        assert len(detections) > 0
        assert report.road_quality_score >= 0
        assert report.road_quality_score <= 100
        assert report.report_id.startswith("RPT-")
        assert len(report.summary) > 50

    def test_pipeline_all_routes(self):
        """Pipeline should work for every predefined route."""
        for route_key, route_info in BENGALURU_ROUTES.items():
            frames, meta = generate_route_data(route_key=route_key, num_frames=100)
            detector = AnomalyDetector()
            detections = detector.process_batch(frames)
            gen = ReportGenerator()
            report = gen.generate(
                anomalies=detections,
                route_name=route_info["name"],
                total_distance_km=route_info["distance_km"],
                total_frames=len(frames),
            )
            assert report.road_quality_score >= 0


# ══════════════════════════════════════════════════════════════════════════════
# 6. EDGE CASE TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_single_frame(self):
        """Detector should handle a single frame without crashing."""
        detector = AnomalyDetector()
        frame = SensorFrame(
            frame_id="F-0001",
            timestamp=1000.0,
            gps=GPSCoordinate(12.9, 77.6),
            accelerometer=AccelerometerReading(0, 0, 1.0, 1000.0),
            vehicle_speed_kmh=30.0,
        )
        result = detector.process_frame(frame)
        assert result is None  # Not enough data for detection

    def test_zero_distance_report(self):
        """Report generator should handle zero distance gracefully."""
        gen = ReportGenerator()
        report = gen.generate(
            anomalies=[DetectedAnomaly(severity=SeverityLevel.HIGH, confidence=0.8)],
            total_distance_km=0.0,
            total_frames=10,
        )
        assert report.road_quality_score >= 0

    def test_very_high_anomaly_count(self):
        """Should handle large numbers of anomalies."""
        anomalies = [
            DetectedAnomaly(
                anomaly_type=AnomalyType.POTHOLE,
                severity=SeverityLevel.CRITICAL,
                confidence=0.9,
            )
            for _ in range(100)
        ]
        gen = ReportGenerator()
        report = gen.generate(anomalies, total_distance_km=5.0, total_frames=1000)
        assert report.road_quality_score == 0.0  # Should bottom out

    def test_no_acoustic_data(self):
        """Detector should work without acoustic sensors."""
        detector = AnomalyDetector(enable_acoustic=False)
        frames = []
        for i in range(15):
            z = 1.0 if i != 10 else 1.8
            frames.append(SensorFrame(
                frame_id=f"F-{i}",
                timestamp=1000.0 + i * 0.1,
                gps=GPSCoordinate(12.9, 77.6),
                accelerometer=AccelerometerReading(0, 0, z, 1000.0 + i * 0.1),
                vehicle_speed_kmh=35.0,
                # No acoustic data
            ))
        detections = detector.process_batch(frames)
        assert len(detections) >= 1
