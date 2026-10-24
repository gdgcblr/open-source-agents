import math
import os
import smtplib
import sys
import time
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import cv2
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Setup & Keys
# ---------------------------------------------------------------------------
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY environment variable is missing in .env.")
    sys.exit(1)

client = genai.Client(api_key=api_key)

DC_OFFICE_EMAIL = os.getenv("DC_OFFICE_EMAIL", "dcurban@nic.in")
BMTC_SUPPORT_EMAIL = os.getenv("BMTC_SUPPORT_EMAIL", "complaints@mybmtc.com")
DRY_RUN = os.getenv("DRY_RUN", "True").lower() in ("true", "1", "yes")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")

# Operational Edge Rate-Limit & Cooldown Constants
FRAME_INSPECTION_INTERVAL = 2.5  # Seconds between Gemini visual inspections
MIN_ALERT_COOLDOWN = 15.0         # Seconds to suppress repeat emails
MIN_DISTANCE_METERS = 40.0       # Do not re-report hazards within 40 meters


# ---------------------------------------------------------------------------
# Geofence Deduplication Helper
# ---------------------------------------------------------------------------
def calculate_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine formula to compute ground distance in meters."""
    radius = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


# ---------------------------------------------------------------------------
# Pydantic Schema for Structured Triage
# ---------------------------------------------------------------------------
class ADASRoadHazardAssessment(BaseModel):
    is_hazard_detected: bool = Field(
        description="True if an active road hazard, pothole, or patch failure is visible in the frame"
    )
    hazard_type: str = Field(
        description="'Pothole', 'Failed Patch / Uneven Surface', 'Debris / Obstruction', or 'None'"
    )
    severity_level: str = Field(
        description="'Low', 'Medium', 'High', 'Critical Emergency', or 'N/A'"
    )
    estimated_dimensions: str = Field(
        description="Visual estimate of size/depth/spread in feet or meters"
    )
    risk_factors: list[str] = Field(
        description="Dangers to vehicles, two-wheelers, and low-floor BMTC buses"
    )
    bmtc_transit_impact: str = Field(
        description="Operational risk specifically for BMTC city and Volvo electric buses"
    )
    recommended_fix: str = Field(
        description="Engineering fix (e.g., immediate cold patch, milling, hot-mix asphalt, steel plating)"
    )
    responsible_agency: str = Field(
        description="Responsible department (e.g., BBMP Engineering, DC Infrastructure Cell, Traffic Police)"
    )


# ---------------------------------------------------------------------------
# Gemini Multimodal Inspection
# ---------------------------------------------------------------------------
def analyze_frame_with_gemini(image_bytes: bytes, lat: float, lon: float, speed: float) -> ADASRoadHazardAssessment:
    prompt = (
        "You are an onboard ADAS Road Safety Agent deployed in Bengaluru.\n"
        "Inspect this forward-facing vehicle camera frame.\n\n"
        f"Telemetry:\n"
        f"- GPS Location : {lat:.5f}° N, {lon:.5f}° E\n"
        f"- Vehicle Speed: {speed:.1f} km/h\n\n"
        "Inspection Tasks:\n"
        "1. Identify active road hazards: potholes, collapsed asphalt, open trenches, failed patches, debris.\n"
        "2. Evaluate operational risk for BMTC city and low-floor electric/Volvo transit buses.\n"
        "3. Determine severity and provide concrete civil engineering triage advice."
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ADASRoadHazardAssessment,
            temperature=0.1,
        ),
    )
    return response.parsed


# ---------------------------------------------------------------------------
# Email Dispatcher
# ---------------------------------------------------------------------------
def dispatch_hazard_alert(assessment: ADASRoadHazardAssessment, image_bytes: bytes, lat: float, lon: float, speed: float):
    recipients = [DC_OFFICE_EMAIL, BMTC_SUPPORT_EMAIL]
    gps_str = f"{lat:.5f}° N, {lon:.5f}° E"
    subject = f"[{assessment.severity_level.upper()}] ADAS Road Hazard Alert: Hosur Road ({gps_str})"

    body = f"""AUTOMATED ADAS ROAD DEFECT ALERT
============================================================
GPS Location    : {gps_str}
Speed at Capture: {speed:.1f} km/h
Timestamp       : {datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")}
Hazard Type     : {assessment.hazard_type}
Severity Rating : {assessment.severity_level}
Est. Dimensions : {assessment.estimated_dimensions}
Responsible     : {assessment.responsible_agency}

BMTC TRANSIT IMPACT:
{assessment.bmtc_transit_impact}

IDENTIFIED RISKS:
{chr(10).join(f' - {r}' for r in assessment.risk_factors)}

RECOMMENDED ENGINEERING REPAIR:
{assessment.recommended_fix}

============================================================
* Attached: Live forward camera frame at the time of detection.
* Dispatched automatically by Onboard ADAS Civic Agent.
"""

    if DRY_RUN:
        print("\n" + "=" * 65)
        print(" [DRY-RUN] Dispatched email simulation:")
        print("=" * 65)
        print(f"To         : {', '.join(recipients)}")
        print(f"Subject    : {subject}\n")
        print(body)
        print(f"Attachment : hazard_frame.jpg ({len(image_bytes)} bytes)")
        print("=" * 65 + "\n")
        return

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")

    if not smtp_user or not smtp_password:
        print("[Error] SMTP_USER and SMTP_PASSWORD required for live dispatch.")
        return

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    img_attachment = MIMEImage(image_bytes, name="hazard_frame.jpg")
    img_attachment.add_header("Content-Disposition", "attachment", filename="hazard_frame.jpg")
    msg.attach(img_attachment)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, recipients, msg.as_string())
        print(f"\n[OK] Alert email successfully sent to {', '.join(recipients)}")
    except Exception as e:
        print(f"\n[Error] Dispatch failed: {e}")


# ---------------------------------------------------------------------------
# Synthetic Frame Fallback
# ---------------------------------------------------------------------------
def create_sample_pothole_frame() -> bytes:
    import numpy as np
    img = np.full((720, 1280, 3), 60, dtype=np.uint8)
    cv2.line(img, (200, 720), (550, 300), (255, 255, 255), 4)
    cv2.line(img, (1080, 720), (730, 300), (255, 255, 255), 4)
    cv2.ellipse(img, (640, 580), (140, 60), 0, 0, 360, (20, 20, 20), -1)
    cv2.ellipse(img, (635, 575), (110, 45), 0, 0, 360, (10, 10, 15), -1)
    cv2.putText(
        img,
        "ADAS CAM 01 - 1080P [SIMULATOR MODE]",
        (30, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2,
    )
    _, buffer = cv2.imencode(".jpg", img)
    return buffer.tobytes()


# ---------------------------------------------------------------------------
# Main Execution Loop
# ---------------------------------------------------------------------------
def run_adas_stream_loop(source=0):
    print(f"Connecting to camera source: {source}...")
    cap = cv2.VideoCapture(source)

    is_live_camera = cap.isOpened()
    if not is_live_camera:
        print("[Notice] No physical camera found. Running in ADAS Simulation Mode.\n")

    last_inspection_time = 0.0
    last_alert_time = 0.0
    last_reported_lat = 0.0
    last_reported_lon = 0.0

    current_lat = 12.9172
    current_lon = 77.6228
    current_speed = 38.0

    print("ADAS Monitor Running. Press Ctrl+C (or 'q' in window) to stop.\n")

    try:
        while True:
            current_time = time.time()

            if is_live_camera:
                ret, frame = cap.read()
                if not ret:
                    print("Stream disconnected or ended.")
                    break

                cv2.putText(
                    frame,
                    f"ADAS AI ROAD MONITOR | Speed: {current_speed:.1f} km/h",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2
                )
                cv2.imshow("ADAS Camera View", frame)
                success, buffer = cv2.imencode(".jpg", frame)
                if not success:
                    continue
                frame_bytes = buffer.tobytes()

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                frame_bytes = create_sample_pothole_frame()
                time.sleep(1.0)

            if (current_time - last_inspection_time) >= FRAME_INSPECTION_INTERVAL:
                last_inspection_time = current_time

                current_lat += 0.0001
                current_lon += 0.0001

                print(f"[{datetime.now().strftime('%H:%M:%S')}] Inspecting road surface ({current_lat:.5f}, {current_lon:.5f})...")

                try:
                    assessment = analyze_frame_with_gemini(
                        frame_bytes, current_lat, current_lon, current_speed
                    )
                except Exception as api_err:
                    print(f"  [API Error] Inspection call failed: {api_err}")
                    continue

                if assessment.is_hazard_detected and assessment.severity_level in ("Medium", "High", "Critical Emergency"):
                    print(f"  --> HAZARD DETECTED: {assessment.hazard_type} ({assessment.severity_level})")

                    time_since_last_alert = current_time - last_alert_time
                    if time_since_last_alert < MIN_ALERT_COOLDOWN:
                        print(f"  [Suppressed] Cooldown active ({int(MIN_ALERT_COOLDOWN - time_since_last_alert)}s remaining).")
                        continue

                    dist = calculate_distance_meters(current_lat, current_lon, last_reported_lat, last_reported_lon)
                    if dist < MIN_DISTANCE_METERS:
                        print(f"  [Suppressed] Duplicate spot: only {dist:.1f}m from last reported location.")
                        continue

                    print("  --> Triggering dispatch to DC Office & BMTC Support...")
                    dispatch_hazard_alert(assessment, frame_bytes, current_lat, current_lon, current_speed)

                    last_alert_time = current_time
                    last_reported_lat = current_lat
                    last_reported_lon = current_lon

                    if not is_live_camera:
                        print("\n[Simulation Complete] Hazard identified, structured, and dispatched successfully.")
                        break
                else:
                    print("  --> Road clear / Hazard below report threshold.")

    except KeyboardInterrupt:
        print("\nStopping agent gracefully...")
    finally:
        if is_live_camera:
            cap.release()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    run_adas_stream_loop(source=0)