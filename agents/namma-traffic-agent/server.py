"""
server.py - FastAPI Web Server & REST API for Namma Bengaluru Traffic Copilot
Hosts the interactive web UI dashboard and provides REST endpoints for traffic intelligence.
"""

import os
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.core import NammaTrafficAgent
from agent.tools import (
    get_route_traffic,
    check_chokepoints,
    get_metro_alternative,
    get_weather_waterlogging_alerts,
    calculate_best_departure_window
)
from agent.knowledge import BENGALURU_HUBS, CHOKEPOINTS

app = FastAPI(
    title="Namma Bengaluru Traffic Copilot API",
    description="Intelligent traffic, multimodal transit, and bottleneck optimization for Bengaluru",
    version="1.0.0"
)

agent = NammaTrafficAgent()

# Web Directory
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")


class QueryRequest(BaseModel):
    prompt: str
    is_raining: bool = False
    hour: Optional[int] = None


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the interactive web UI dashboard."""
    index_file = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>Dashboard index.html not found.</h2>")


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


@app.get("/api/optimize-departure")
async def optimize_departure(origin: str, destination: str, hour: int = 18):
    """Calculates departure curve to avoid worst rush hours."""
    return calculate_best_departure_window(origin, destination, target_hour=hour)


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Namma Bengaluru Traffic Copilot Web Server on http://localhost:8000")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
