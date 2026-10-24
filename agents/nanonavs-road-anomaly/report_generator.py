"""
NanoNavs Road Intelligence — Report Generator

Produces structured incident reports from detected anomalies.
Includes optional Gemini AI enhancement for natural-language narratives.

The report generator works completely offline. When a Gemini API key is
available, it adds a rich AI-generated narrative; otherwise, it produces
a comprehensive deterministic summary.
"""

import json
import os
import statistics
from datetime import datetime
from typing import List, Optional

from models import (
    AnomalyType,
    DetectedAnomaly,
    IncidentReport,
    SeverityLevel,
)


class ReportGenerator:
    """
    Generates structured incident reports from anomaly detection results.
    """

    def __init__(self, report_dir: str = "reports"):
        self.report_dir = report_dir

    def generate(
        self,
        anomalies: List[DetectedAnomaly],
        route_name: str = "Unknown Route",
        total_distance_km: float = 0.0,
        total_frames: int = 0,
    ) -> IncidentReport:
        """
        Generate a complete incident report from detected anomalies.

        Args:
            anomalies: List of DetectedAnomaly objects.
            route_name: Human-readable route name.
            total_distance_km: Total route distance in kilometres.
            total_frames: Total number of sensor frames analysed.

        Returns:
            An IncidentReport with calculated quality score and summary.
        """
        report = IncidentReport(
            route_name=route_name,
            total_distance_km=total_distance_km,
            total_frames_analysed=total_frames,
            anomalies=anomalies,
        )

        # Calculate road quality score
        report.road_quality_score = self._calculate_quality_score(
            anomalies, total_distance_km, total_frames
        )

        # Generate deterministic summary
        report.summary = self._build_summary(report)

        # Try to enhance with Gemini AI
        report.ai_narrative = self._generate_ai_narrative(report)

        return report

    def _calculate_quality_score(
        self,
        anomalies: List[DetectedAnomaly],
        distance_km: float,
        total_frames: int,
    ) -> float:
        """
        Calculate a 0-100 road quality score.

        Factors in anomaly count, severity distribution, and density.
        """
        if not anomalies or total_frames == 0:
            return 100.0

        # Severity penalty weights
        severity_weights = {
            SeverityLevel.LOW: 2.0,
            SeverityLevel.MODERATE: 5.0,
            SeverityLevel.HIGH: 12.0,
            SeverityLevel.CRITICAL: 25.0,
        }

        total_penalty = sum(
            severity_weights.get(a.severity, 2.0) * a.confidence
            for a in anomalies
        )

        # Normalise by distance (anomalies per km)
        distance_factor = max(distance_km, 0.5)
        density_penalty = (total_penalty / distance_factor) * 2.0

        score = max(0.0, 100.0 - density_penalty)
        return round(score, 1)

    def _build_summary(self, report: IncidentReport) -> str:
        """Build a structured text summary of the report."""
        anomalies = report.anomalies
        if not anomalies:
            return (
                f"Route: {report.route_name}\n"
                f"Distance: {report.total_distance_km:.1f} km\n"
                f"Road Quality Score: {report.road_quality_score}/100\n"
                f"Status: ✅ No anomalies detected. Road surface is in excellent condition."
            )

        # Count by type
        type_counts = {}
        for a in anomalies:
            key = a.anomaly_type.value
            type_counts[key] = type_counts.get(key, 0) + 1

        # Count by severity
        severity_counts = {}
        for a in anomalies:
            key = a.severity.value
            severity_counts[key] = severity_counts.get(key, 0) + 1

        # Most dangerous anomaly
        worst = max(anomalies, key=lambda a: a.peak_vertical_g)

        # Build summary text
        lines = [
            f"═══ NanoNavs Incident Report ═══",
            f"Report ID: {report.report_id}",
            f"Generated: {report.generated_at}",
            f"Route: {report.route_name}",
            f"Distance: {report.total_distance_km:.1f} km",
            f"Frames Analysed: {report.total_frames_analysed}",
            f"",
            f"── Detection Summary ──",
            f"Total Anomalies: {len(anomalies)}",
            f"Road Quality Score: {report.road_quality_score}/100",
            f"",
            f"By Type:",
        ]
        for atype, count in sorted(type_counts.items()):
            lines.append(f"  • {atype}: {count}")

        lines.append(f"\nBy Severity:")
        for sev, count in sorted(severity_counts.items()):
            emoji = {"low": "🟢", "moderate": "🟡", "high": "🟠", "critical": "🔴"}.get(sev, "⚪")
            lines.append(f"  {emoji} {sev}: {count}")

        lines.extend([
            f"",
            f"── Most Severe Anomaly ──",
            f"  Type: {worst.anomaly_type.value}",
            f"  Location: {worst.location}",
            f"  Peak Impact: {worst.peak_vertical_g:.3f}g",
            f"  Confidence: {worst.confidence:.1%}",
        ])

        # Actionable recommendation
        if report.road_quality_score < 30:
            lines.append("\n⚠️ URGENT: Route requires immediate maintenance intervention.")
        elif report.road_quality_score < 60:
            lines.append("\n⚠️ CAUTION: Significant surface degradation. Reduce speed advised.")
        elif report.road_quality_score < 80:
            lines.append("\nℹ️ NOTICE: Minor surface irregularities detected. Standard maintenance recommended.")
        else:
            lines.append("\n✅ Route surface is in acceptable condition.")

        return "\n".join(lines)

    def _generate_ai_narrative(self, report: IncidentReport) -> str:
        """
        Generate an AI-enhanced narrative using Gemini (optional).

        Returns empty string if Gemini is not available.
        """
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            return ""

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)

            prompt = self._build_ai_prompt(report)

            response = client.models.generate_content(
                model=os.getenv("MODEL_NAME", "gemini-2.5-flash"),
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=float(os.getenv("TEMPERATURE", "0.2")),
                    system_instruction=(
                        "You are NanoNavs, an expert road infrastructure analyst. "
                        "Generate a concise, professional incident report narrative. "
                        "Focus on actionable insights for municipal road maintenance teams. "
                        "Be specific about locations, severity, and recommended actions. "
                        "Do not fabricate data — only reference the anomalies provided."
                    ),
                ),
            )
            return response.text if response.text else ""

        except Exception as e:
            return f"[AI narrative unavailable: {e}]"

    def _build_ai_prompt(self, report: IncidentReport) -> str:
        """Build the prompt for Gemini AI narrative generation."""
        anomaly_summaries = []
        for a in report.anomalies[:15]:  # Cap to avoid token overflow
            anomaly_summaries.append(
                f"- {a.anomaly_type.value} at {a.location} | "
                f"Severity: {a.severity.value} | "
                f"Impact: {a.peak_vertical_g:.2f}g | "
                f"Confidence: {a.confidence:.0%}"
            )

        return (
            f"Generate a professional road condition report narrative.\n\n"
            f"Route: {report.route_name}\n"
            f"Distance: {report.total_distance_km:.1f} km\n"
            f"Anomalies Detected: {len(report.anomalies)}\n"
            f"Road Quality Score: {report.road_quality_score}/100\n\n"
            f"Detected Anomalies:\n" + "\n".join(anomaly_summaries) +
            f"\n\nProvide:\n"
            f"1. A brief executive summary (2-3 sentences)\n"
            f"2. Key hotspots requiring immediate attention\n"
            f"3. Recommended maintenance actions\n"
            f"4. Estimated priority level for municipal response"
        )

    def save_report(self, report: IncidentReport, format: str = "json") -> str:
        """
        Save the report to the reports directory.

        Args:
            report: The IncidentReport to save.
            format: Output format ('json' or 'txt').

        Returns:
            Path to the saved report file.
        """
        os.makedirs(self.report_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format == "json":
            filepath = os.path.join(self.report_dir, f"{report.report_id}_{timestamp}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        else:
            filepath = os.path.join(self.report_dir, f"{report.report_id}_{timestamp}.txt")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(report.summary)
                if report.ai_narrative:
                    f.write("\n\n═══ AI-Enhanced Narrative ═══\n")
                    f.write(report.ai_narrative)

        return filepath
