"""
NanoNavs Road Intelligence — Streamlit Dashboard

Interactive web interface for road anomaly detection and visualisation.
Provides real-time sensor data analysis, anomaly mapping, and incident reporting.

Launch:
    streamlit run agents/nanonavs-road-anomaly/app.py
"""

import json
import os
import sys

import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(__file__))

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from detector import AnomalyDetector
from models import AnomalyType, SeverityLevel
from report_generator import ReportGenerator
from sensor_data import BENGALURU_ROUTES, generate_route_data

# ══════════════════════════════════════════════════════════════════════════════
# Page Configuration
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="NanoNavs Road Intelligence",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        color: #8b949e;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px;
        padding: 1.2rem;
        border: 1px solid #30363d;
    }
    .severity-critical { color: #f85149; font-weight: 700; }
    .severity-high { color: #f0883e; font-weight: 600; }
    .severity-moderate { color: #d29922; }
    .severity-low { color: #3fb950; }
    .stMetric > div { background: transparent; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Header
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<p class="main-header">🛣️ NanoNavs Road Intelligence</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">Autonomous road anomaly detection, classification, '
    'and incident reporting powered by multi-sensor fusion</p>',
    unsafe_allow_html=True,
)

# ══════════════════════════════════════════════════════════════════════════════
# Sidebar — Configuration
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("⚙️ Configuration")

    # Route selection
    route_options = {
        key: info["name"] for key, info in BENGALURU_ROUTES.items()
    }
    selected_route = st.selectbox(
        "Select Route",
        options=list(route_options.keys()),
        format_func=lambda k: route_options[k],
        index=1,  # Default to Silk Board
    )

    st.divider()

    # Simulation parameters
    st.subheader("📡 Sensor Parameters")
    num_frames = st.slider("Sensor Frames", 50, 500, 200, step=50)
    anomaly_density = st.slider("Anomaly Density", 0.02, 0.25, 0.08, step=0.02)
    seed = st.number_input("Random Seed", value=42, min_value=1, max_value=999)

    st.divider()

    # Detection parameters
    st.subheader("🔍 Detection Tuning")
    window_size = st.slider("Window Size", 3, 10, 5)
    min_confidence = st.slider("Min Confidence", 0.2, 0.8, 0.4, step=0.05)
    enable_acoustic = st.checkbox("Enable Acoustic Fusion", value=True)

    st.divider()

    # Gemini status
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        st.success("🤖 Gemini AI: Connected")
    else:
        st.info("🤖 Gemini AI: Not configured (optional)")

    run_analysis = st.button("🚀 Run Analysis", use_container_width=True, type="primary")

# ══════════════════════════════════════════════════════════════════════════════
# Main Content
# ══════════════════════════════════════════════════════════════════════════════

if run_analysis:
    route_info = BENGALURU_ROUTES[selected_route]

    # ── Step 1: Generate Data ─────────────────────────────────────────────
    with st.status("🔧 Processing pipeline...", expanded=True) as status:
        st.write("📡 Generating sensor telemetry...")
        frames, metadata = generate_route_data(
            route_key=selected_route,
            num_frames=num_frames,
            anomaly_density=anomaly_density,
            seed=seed,
        )

        st.write(f"✓ {len(frames)} frames generated ({metadata['injected_anomaly_count']} ground-truth anomalies)")

        # ── Step 2: Run Detection ─────────────────────────────────────────
        st.write("🔍 Running anomaly detection...")
        detector = AnomalyDetector(
            window_size=window_size,
            min_confidence=min_confidence,
            enable_acoustic=enable_acoustic,
        )
        detections = detector.process_batch(frames)
        st.write(f"✓ {len(detections)} anomalies detected")

        # ── Step 3: Generate Report ───────────────────────────────────────
        st.write("📋 Generating incident report...")
        generator = ReportGenerator()
        report = generator.generate(
            anomalies=detections,
            route_name=route_info["name"],
            total_distance_km=route_info["distance_km"],
            total_frames=len(frames),
        )
        st.write("✓ Report generated")
        status.update(label="✅ Analysis Complete", state="complete")

    # ── Key Metrics ───────────────────────────────────────────────────────
    st.divider()
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Road Quality", f"{report.road_quality_score}/100")
    with col2:
        st.metric("Anomalies Found", len(detections))
    with col3:
        critical_count = sum(1 for d in detections if d.severity == SeverityLevel.CRITICAL)
        st.metric("Critical Issues", critical_count)
    with col4:
        st.metric("Route Distance", f"{route_info['distance_km']:.1f} km")
    with col5:
        gt = metadata["injected_anomaly_count"]
        detection_rate = f"{min(len(detections)/gt, 1.0):.0%}" if gt > 0 else "N/A"
        st.metric("Detection Rate", detection_rate)

    # ── Visualisations ────────────────────────────────────────────────────
    st.divider()
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Sensor Data", "🗺️ Anomaly Map", "📋 Detections", "📄 Report", "📥 Export"
    ])

    with tab1:
        st.subheader("Accelerometer Z-Axis (Vertical)")

        # Build sensor data DataFrame
        sensor_df = pd.DataFrame({
            "Frame": range(len(frames)),
            "Z-Axis (g)": [f.accelerometer.z for f in frames],
            "X-Axis (g)": [f.accelerometer.x for f in frames],
            "Y-Axis (g)": [f.accelerometer.y for f in frames],
            "Speed (km/h)": [f.vehicle_speed_kmh for f in frames],
        })

        # Mark anomaly frames
        anomaly_frame_ids = set()
        for d in detections:
            anomaly_frame_ids.update(d.evidence_frames)

        st.line_chart(sensor_df, x="Frame", y=["Z-Axis (g)"], height=300)

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Lateral & Longitudinal Acceleration")
            st.line_chart(sensor_df, x="Frame", y=["X-Axis (g)", "Y-Axis (g)"], height=250)
        with col_b:
            st.subheader("Vehicle Speed Profile")
            st.line_chart(sensor_df, x="Frame", y=["Speed (km/h)"], height=250)

        if any(f.acoustic for f in frames):
            st.subheader("Acoustic Profile")
            acoustic_df = pd.DataFrame({
                "Frame": range(len(frames)),
                "Decibels (dB)": [f.acoustic.decibel_level if f.acoustic else 0 for f in frames],
                "Frequency (Hz)": [f.acoustic.dominant_frequency_hz if f.acoustic else 0 for f in frames],
            })
            col_c, col_d = st.columns(2)
            with col_c:
                st.line_chart(acoustic_df, x="Frame", y=["Decibels (dB)"], height=250)
            with col_d:
                st.line_chart(acoustic_df, x="Frame", y=["Frequency (Hz)"], height=250)

    with tab2:
        st.subheader("Anomaly Location Map")

        if detections:
            map_data = pd.DataFrame({
                "lat": [d.location.latitude for d in detections],
                "lon": [d.location.longitude for d in detections],
            })
            st.map(map_data, zoom=12)

            st.caption(
                f"📌 {len(detections)} anomalies plotted along "
                f"{route_info['name']} ({route_info['distance_km']:.1f} km)"
            )
        else:
            st.info("No anomalies detected to map. Try increasing anomaly density.")

    with tab3:
        st.subheader("Detection Details")

        if detections:
            det_data = []
            for d in detections:
                severity_emoji = {
                    "low": "🟢", "moderate": "🟡", "high": "🟠", "critical": "🔴"
                }.get(d.severity.value, "⚪")
                det_data.append({
                    "ID": d.anomaly_id,
                    "Type": d.anomaly_type.value,
                    "Severity": f"{severity_emoji} {d.severity.value}",
                    "Confidence": f"{d.confidence:.0%}",
                    "Impact (g)": f"{d.peak_vertical_g:.3f}",
                    "Speed (km/h)": f"{d.vehicle_speed_kmh:.0f}",
                    "Location": str(d.location),
                })

            det_df = pd.DataFrame(det_data)
            st.dataframe(det_df, use_container_width=True, hide_index=True)

            # Severity distribution
            col_e, col_f = st.columns(2)
            with col_e:
                st.subheader("By Type")
                type_counts = pd.DataFrame(
                    [{"Type": d.anomaly_type.value} for d in detections]
                )["Type"].value_counts()
                st.bar_chart(type_counts)

            with col_f:
                st.subheader("By Severity")
                sev_counts = pd.DataFrame(
                    [{"Severity": d.severity.value} for d in detections]
                )["Severity"].value_counts()
                st.bar_chart(sev_counts)
        else:
            st.info("No anomalies detected.")

    with tab4:
        st.subheader("Incident Report")
        st.text(report.summary)

        if report.ai_narrative:
            st.divider()
            st.subheader("🤖 AI-Enhanced Narrative (Gemini)")
            st.markdown(report.ai_narrative)

    with tab5:
        st.subheader("Export Results")

        col_g, col_h = st.columns(2)
        with col_g:
            report_json = json.dumps(report.to_dict(), indent=2)
            st.download_button(
                label="📥 Download Report (JSON)",
                data=report_json,
                file_name=f"{report.report_id}.json",
                mime="application/json",
                use_container_width=True,
            )
        with col_h:
            st.download_button(
                label="📥 Download Report (Text)",
                data=report.summary + (
                    f"\n\n═══ AI Narrative ═══\n{report.ai_narrative}"
                    if report.ai_narrative else ""
                ),
                file_name=f"{report.report_id}.txt",
                mime="text/plain",
                use_container_width=True,
            )

        st.divider()
        st.subheader("Raw Detection Data")
        st.json(report.to_dict())

else:
    # ── Landing Page ──────────────────────────────────────────────────────
    st.info("👈 Configure parameters in the sidebar and click **Run Analysis** to begin.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 📡 Multi-Sensor Fusion")
        st.markdown(
            "Combines accelerometer, GPS, and acoustic data from vehicle-mounted "
            "sensors for high-confidence anomaly detection."
        )

    with col2:
        st.markdown("### 🔍 Real-Time Detection")
        st.markdown(
            "Sliding-window signal analysis with threshold-based classification. "
            "No cloud dependency — works entirely offline."
        )

    with col3:
        st.markdown("### 🤖 AI-Enhanced Reports")
        st.markdown(
            "Optional Gemini AI integration generates natural-language incident "
            "narratives for municipal road maintenance teams."
        )

    st.divider()
    st.markdown("### 🗺️ Available Routes")

    route_data = []
    for key, info in BENGALURU_ROUTES.items():
        route_data.append({
            "Route": info["name"],
            "Distance": f"{info['distance_km']:.1f} km",
            "Description": info["description"],
        })
    st.table(pd.DataFrame(route_data))
