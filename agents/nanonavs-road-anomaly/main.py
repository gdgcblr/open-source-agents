"""
NanoNavs Road Intelligence — Main Application Entry Point

Command-line interface for running the NanoNavs road anomaly detection
pipeline. Supports multiple modes:

  1. demo    — Run a full demonstration with synthetic data
  2. analyse — Analyse a CSV sensor data file
  3. report  — Generate a report from previous detection results

Usage:
    python main.py                    # Run interactive demo
    python main.py --route hebbal     # Demo with specific route
    python main.py --csv data.csv     # Analyse a CSV file
    python main.py --json             # Output results as JSON
"""

import argparse
import json
import os
import sys

# Ensure UTF-8 output encoding across platforms (especially Windows PowerShell/cmd)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv

# Load environment from local .env if available
load_dotenv()

from detector import AnomalyDetector
from models import AnomalyType, SeverityLevel
from report_generator import ReportGenerator
from sensor_data import BENGALURU_ROUTES, generate_route_data, generate_sample_csv


def run_demo(route_key: str, num_frames: int, output_json: bool, save_report: bool):
    """Run a complete demonstration pipeline with synthetic sensor data."""
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║        🛣️  NanoNavs Road Intelligence Agent  🛣️              ║")
    print("║     Autonomous Road Anomaly Detection & Classification      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # Validate route
    route_aliases = {
        "silk-board": "silk-board-to-marathahalli",
        "electronic-city": "electronic-city-to-koramangala",
        "hebbal": "hebbal-to-airport",
        "jayanagar": "jayanagar-to-jp-nagar",
    }
    resolved_key = route_aliases.get(route_key, route_key)

    if resolved_key not in BENGALURU_ROUTES:
        print(f"⚠️  Unknown route: '{route_key}'")
        print(f"   Available routes: {', '.join(BENGALURU_ROUTES.keys())}")
        print(f"   Aliases: {', '.join(route_aliases.keys())}")
        sys.exit(1)

    route_info = BENGALURU_ROUTES[resolved_key]

    print(f"📍 Route: {route_info['name']}")
    print(f"   {route_info['description']}")
    print(f"   Distance: {route_info['distance_km']:.1f} km")
    print()

    # Generate synthetic sensor data
    print(f"📡 Generating {num_frames} sensor frames (10 Hz sampling rate)...")
    frames, metadata = generate_route_data(
        route_key=resolved_key,
        num_frames=num_frames,
        seed=42,
    )
    print(f"   ✓ {len(frames)} frames generated")
    print(f"   ✓ {metadata['injected_anomaly_count']} ground-truth anomalies injected")
    print()

    # Run anomaly detection
    print("🔍 Running anomaly detection pipeline...")
    detector = AnomalyDetector(window_size=5, min_confidence=0.4, enable_acoustic=True)
    detections = detector.process_batch(frames)

    print(f"   ✓ {len(detections)} anomalies detected")

    # Display detections
    if detections:
        print()
        print("── Detected Anomalies ──────────────────────────────────────")
        for i, d in enumerate(detections, 1):
            severity_emoji = {
                SeverityLevel.LOW: "🟢",
                SeverityLevel.MODERATE: "🟡",
                SeverityLevel.HIGH: "🟠",
                SeverityLevel.CRITICAL: "🔴",
            }.get(d.severity, "⚪")
            print(
                f"  {i:2d}. {severity_emoji} {d.anomaly_type.value:<20s} | "
                f"{d.severity.value:<9s} | "
                f"{d.confidence:.0%} conf | "
                f"{d.peak_vertical_g:.2f}g | "
                f"📍 {d.location}"
            )
    print()

    # Generate incident report
    print("📋 Generating incident report...")
    generator = ReportGenerator()
    report = generator.generate(
        anomalies=detections,
        route_name=route_info["name"],
        total_distance_km=route_info["distance_km"],
        total_frames=len(frames),
    )

    if output_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print()
        print(report.summary)

        if report.ai_narrative:
            print()
            print("═══ AI-Enhanced Narrative (Gemini) ═══")
            print(report.ai_narrative)

    # Save report if requested
    if save_report:
        json_path = generator.save_report(report, format="json")
        txt_path = generator.save_report(report, format="txt")
        print(f"\n💾 Reports saved:")
        print(f"   JSON: {json_path}")
        print(f"   Text: {txt_path}")

    # Detection accuracy against ground truth
    print()
    print("── Detection Performance ───────────────────────────────────")
    gt_count = metadata["injected_anomaly_count"]
    det_count = len(detections)
    print(f"   Ground-truth anomalies: {gt_count}")
    print(f"   Detected anomalies:     {det_count}")
    if gt_count > 0:
        recall = min(det_count / gt_count, 1.0)
        print(f"   Detection rate:         {recall:.0%}")
    print(f"   Road Quality Score:     {report.road_quality_score}/100")
    print()

    gemini_status = "✅ Enabled" if os.getenv("GEMINI_API_KEY") else "⬚ Not configured (optional)"
    print(f"🤖 Gemini AI Enhancement: {gemini_status}")
    print()
    print("✅ NanoNavs demonstration complete.")

    return report


def run_csv_analysis(csv_path: str, output_json: bool):
    """Analyse a CSV sensor data file."""
    import csv as csv_module

    if not os.path.exists(csv_path):
        print(f"❌ File not found: {csv_path}")
        sys.exit(1)

    print(f"📂 Loading sensor data from: {csv_path}")

    from models import AccelerometerReading, AcousticReading, GPSCoordinate, SensorFrame

    frames = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv_module.DictReader(f)
        for row in reader:
            try:
                frame = SensorFrame(
                    frame_id=row.get("frame_id", f"F-{len(frames)}"),
                    timestamp=float(row["timestamp"]),
                    gps=GPSCoordinate(
                        latitude=float(row["latitude"]),
                        longitude=float(row["longitude"]),
                    ),
                    accelerometer=AccelerometerReading(
                        x=float(row["accel_x"]),
                        y=float(row["accel_y"]),
                        z=float(row["accel_z"]),
                        timestamp=float(row["timestamp"]),
                    ),
                    acoustic=AcousticReading(
                        decibel_level=float(row.get("db_level", 0)),
                        dominant_frequency_hz=float(row.get("freq_hz", 0)),
                        timestamp=float(row["timestamp"]),
                    ) if row.get("db_level") else None,
                    vehicle_speed_kmh=float(row.get("speed_kmh", 30)),
                )
                frames.append(frame)
            except (ValueError, KeyError) as e:
                print(f"   ⚠️ Skipping malformed row: {e}")

    print(f"   ✓ {len(frames)} frames loaded")

    detector = AnomalyDetector()
    detections = detector.process_batch(frames)

    generator = ReportGenerator()
    report = generator.generate(
        anomalies=detections,
        route_name=os.path.basename(csv_path),
        total_frames=len(frames),
    )

    if output_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.summary)

    return report


def generate_sample_data_file():
    """Generate and save a sample CSV data file for demonstration."""
    output_dir = os.path.join(os.path.dirname(__file__), "sample_data")
    os.makedirs(output_dir, exist_ok=True)

    for route_key in BENGALURU_ROUTES:
        csv_content = generate_sample_csv(route_key=route_key, num_frames=200, seed=42)
        filepath = os.path.join(output_dir, f"{route_key}.csv")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(csv_content)
        print(f"   ✓ {filepath}")


def main():
    parser = argparse.ArgumentParser(
        prog="nanonavs",
        description="NanoNavs Road Intelligence — Autonomous Road Anomaly Detection Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py                           Run demo with default route\n"
            "  python main.py --route hebbal             Demo with Hebbal-Airport route\n"
            "  python main.py --csv sensor_data.csv      Analyse a CSV file\n"
            "  python main.py --json                     Output as JSON\n"
            "  python main.py --generate-sample-data     Create sample CSV files\n"
        ),
    )

    parser.add_argument(
        "--route",
        default="silk-board-to-marathahalli",
        help="Route key or alias for demo mode (default: silk-board-to-marathahalli)",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=200,
        help="Number of sensor frames to generate (default: 200)",
    )
    parser.add_argument(
        "--csv",
        metavar="FILE",
        help="Path to a CSV file with sensor data to analyse",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save generated reports to the reports/ directory",
    )
    parser.add_argument(
        "--generate-sample-data",
        action="store_true",
        help="Generate sample CSV files for all routes and exit",
    )

    args = parser.parse_args()

    if args.generate_sample_data:
        print("📁 Generating sample data files...")
        generate_sample_data_file()
        print("✅ Sample data generated.")
        return

    if args.csv:
        run_csv_analysis(args.csv, args.json)
    else:
        run_demo(args.route, args.frames, args.json, args.save)


if __name__ == "__main__":
    main()
