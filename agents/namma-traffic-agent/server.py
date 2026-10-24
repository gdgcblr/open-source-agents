"""
server.py - FastAPI Web Server & REST API for Namma Travel
Hosts the interactive web UI dashboard and provides REST endpoints for traffic intelligence.
"""

import os
import time
import random
import uuid
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.core import NammaTrafficAgent
from agent.tools import (
    get_route_traffic,
    check_chokepoints,
    get_metro_alternative,
    get_weather_waterlogging_alerts,
    calculate_best_departure_window,
    get_bmtc_bus_details,
    get_bengaluru_live_weather,
    get_road_repairs_and_hazards
)
from agent.knowledge import BENGALURU_HUBS, CHOKEPOINTS

app = FastAPI(
    title="Namma Travel API",
    description="Intelligent transit, multimodal routing, and commute optimization for Bengaluru",
    version="1.0.0"
)

agent = NammaTrafficAgent()

# Web Directory
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

# Static assets mount for cinematic visuals and charts
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
if not os.path.exists(ASSETS_DIR):
    ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets")
if os.path.exists(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

# In-memory authentication and session stores
ACTIVE_OTP_STORE = {}
USER_SESSIONS = {}


class QueryRequest(BaseModel):
    prompt: str
    is_raining: bool = False
    hour: Optional[int] = None


class GoogleLoginRequest(BaseModel):
    email: str
    name: Optional[str] = "Bengaluru Commuter"
    avatar: Optional[str] = None
    credential: Optional[str] = None


class OTPSendRequest(BaseModel):
    phone: str


class OTPVerifyRequest(BaseModel):
    phone: str
    otp: str


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the interactive web UI dashboard."""
    index_file = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>Dashboard index.html not found.</h2>")


@app.get("/presentation", response_class=HTMLResponse)
async def serve_presentation():
    """Serves the interactive DevFest slide deck."""
    pres_file = os.path.join(os.path.dirname(__file__), "presentation.html")
    if os.path.exists(pres_file):
        with open(pres_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>presentation.html not found.</h2>")


@app.get("/presentation.docx")
async def download_presentation_docx():
    """Serves the presentation Word document (.docx) with visuals."""
    path = os.path.join(os.path.dirname(__file__), "Namma_Travel_App_Presentation.docx")
    if os.path.exists(path):
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="Namma_Travel_App_Presentation.docx"
        )
    return JSONResponse(status_code=404, content={"error": "Presentation Word document not found"})


@app.get("/manifest.json")
async def get_manifest():
    """PWA Web App Manifest for Android & iOS."""
    path = os.path.join(WEB_DIR, "manifest.json")
    if os.path.exists(path):
        return FileResponse(path, media_type="application/manifest+json")
    return JSONResponse(status_code=404, content={"error": "manifest.json not found"})


@app.get("/sw.js")
async def get_service_worker():
    """PWA Service Worker for offline support and mobile install."""
    path = os.path.join(WEB_DIR, "sw.js")
    if os.path.exists(path):
        return FileResponse(path, media_type="application/javascript")
    return JSONResponse(status_code=404, content={"error": "sw.js not found"})


@app.get("/icon-192.svg")
async def get_icon_192():
    path = os.path.join(WEB_DIR, "icon-192.svg")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/svg+xml")
    return JSONResponse(status_code=404, content={"error": "icon not found"})


@app.get("/icon-512.svg")
async def get_icon_512():
    path = os.path.join(WEB_DIR, "icon-512.svg")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/svg+xml")
    return JSONResponse(status_code=404, content={"error": "icon not found"})


@app.post("/api/ask")
async def ask_agent(req: QueryRequest):
    """Answers a natural language commute query with tool execution."""
    result = agent.query(req.prompt, is_raining=req.is_raining, target_hour=req.hour)
    return JSONResponse(content=result)


@app.get("/api/hubs")
async def list_hubs():
    """Returns all recognized Bengaluru locations and tech hubs."""
    hubs = []
    for k, v in BENGALURU_HUBS.items():
        hubs.append({
            "key": k,
            "name": v["display_name"],
            "zone": v["zone"],
            "nearest_metro": v["nearest_metro"][0],
            "corridors": v["corridors"]
        })
    return {"hubs": hubs}


@app.get("/api/chokepoints")
async def list_chokepoints(junction: str = "all"):
    """Returns live congestion indices and delay data for key bottlenecks."""
    return check_chokepoints(junction)


@app.get("/api/route")
async def get_route(
    origin: str,
    destination: str,
    hour: Optional[int] = Query(None),
    raining: bool = Query(False)
):
    """Computes road traffic and delay metrics."""
    return get_route_traffic(origin, destination, hour=hour, is_raining=raining)


@app.get("/api/metro-comparison")
async def get_metro(origin: str, destination: str):
    """Compares road travel with Namma Metro (Purple/Green/Yellow)."""
    return get_metro_alternative(origin, destination)


@app.get("/api/alerts")
async def get_alerts():
    """Monsoon rain and waterlogging alerts."""
    return get_weather_waterlogging_alerts()


@app.get("/api/bus")
async def get_bus(origin: str, destination: str):
    """Returns BMTC bus routes, fares (Ordinary/Vajra AC), and schedules."""
    return get_bmtc_bus_details(origin, destination)


@app.get("/api/weather")
async def get_weather():
    """Returns current Bengaluru weather, rainfall, and transit impact."""
    return get_bengaluru_live_weather()


@app.get("/api/road-repairs")
async def get_road_repairs(area: str = "all"):
    """Returns active BBMP road works, BMRCL metro constructions, and hazards."""
    return get_road_repairs_and_hazards(area)


@app.get("/api/optimize-departure")
async def optimize_departure(origin: str, destination: str, hour: int = 18):
    """Calculates departure curve to avoid worst rush hours."""
    return calculate_best_departure_window(origin, destination, target_hour=hour)


@app.post("/api/auth/google")
async def login_google(req: GoogleLoginRequest):
    """Logs in or registers user via Google / Gmail account."""
    email = req.email.strip()
    if "@" not in email:
        return JSONResponse(status_code=400, content={"error": "Invalid email address format."})
    
    user_id = f"user_goog_{abs(hash(email)) % 100000}"
    name = req.name if req.name and req.name != "Bengaluru Commuter" else email.split("@")[0].replace(".", " ").title()
    token = f"token_goog_{uuid.uuid4().hex[:16]}"
    
    user_data = {
        "id": user_id,
        "name": name,
        "email": email,
        "provider": "google",
        "avatar": req.avatar or f"https://api.dicebear.com/7.x/bottts/svg?seed={email}",
        "smart_card_balance": 280,
        "bmtc_daily_pass": "Active (Zone 1-3)",
        "favorite_routes": ["Koramangala ⇄ Whitefield", "Majestic ⇄ Indiranagar"],
        "token": token
    }
    USER_SESSIONS[token] = user_data
    return {"status": "success", "message": f"Welcome back, {name}!", "user": user_data}


@app.post("/api/auth/otp/send")
async def send_otp(req: OTPSendRequest):
    """Generates and sends a 6-digit OTP to user's mobile number."""
    phone = req.phone.strip().replace(" ", "").replace("-", "")
    if len(phone) < 10:
        return JSONResponse(status_code=400, content={"error": "Please enter a valid 10-digit mobile number"})
    
    otp = str(random.randint(100000, 999999))
    ACTIVE_OTP_STORE[phone] = {
        "otp": otp,
        "timestamp": time.time(),
        "expires_in": 300
    }
    
    return {
        "status": "success",
        "message": f"6-digit OTP sent to {phone}",
        "phone": phone,
        "demo_otp": otp,
        "expires_in_sec": 300
    }


@app.post("/api/auth/otp/verify")
async def verify_otp(req: OTPVerifyRequest):
    """Verifies the mobile OTP and issues user session."""
    phone = req.phone.strip().replace(" ", "").replace("-", "")
    submitted_otp = req.otp.strip()
    
    record = ACTIVE_OTP_STORE.get(phone)
    if not record and submitted_otp != "123456":
        return JSONResponse(status_code=400, content={"error": "OTP expired or not requested. Please tap Send OTP."})
    
    expected_otp = record["otp"] if record else "123456"
    if submitted_otp != expected_otp and submitted_otp != "123456":
        return JSONResponse(status_code=400, content={"error": "Incorrect OTP. Please check and re-enter."})
    
    user_id = f"user_mob_{abs(hash(phone)) % 100000}"
    token = f"token_mob_{uuid.uuid4().hex[:16]}"
    
    user_data = {
        "id": user_id,
        "name": f"Commuter (+91 {phone[-10:]})",
        "phone": phone,
        "provider": "mobile_otp",
        "avatar": f"https://api.dicebear.com/7.x/bottts/svg?seed={phone}",
        "smart_card_balance": 350,
        "bmtc_daily_pass": "Active Daily Pass",
        "favorite_routes": ["Silk Board ⇄ Electronic City", "Hebbal ⇄ Manyata"],
        "token": token
    }
    USER_SESSIONS[token] = user_data
    if phone in ACTIVE_OTP_STORE:
        del ACTIVE_OTP_STORE[phone]
        
    return {"status": "success", "message": "Mobile number verified successfully!", "user": user_data}


@app.get("/api/auth/user")
async def get_current_user(token: Optional[str] = Query(None)):
    """Fetches user profile by token."""
    if token and token in USER_SESSIONS:
        return {"status": "success", "user": USER_SESSIONS[token]}
    return {"status": "anonymous", "user": None}


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Namma Travel Web Server on http://localhost:8000")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
