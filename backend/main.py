"""
SafeRoute-AI — FastAPI Backend v2.1
Main application server with all API endpoints.
"""

import asyncio
import hashlib
import hmac
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from functools import partial
from pathlib import Path

from fastapi import FastAPI, Query, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("roadsense")

# Import our modules
from backend.ml_model import get_all_zones, predict, find_nearest_zone, haversine, assign_risk_label
from backend.weather import get_weather
from backend.ai_analyst import get_safety_insight
from backend.route_scorer import score_route

# ─── Tamil Nadu bounds ──────────────────────────────────────────
TN_LAT_MIN, TN_LAT_MAX = 8.0, 13.6
TN_LON_MIN, TN_LON_MAX = 76.0, 80.5


def _in_tamil_nadu(lat: float, lon: float) -> bool:
    return TN_LAT_MIN <= lat <= TN_LAT_MAX and TN_LON_MIN <= lon <= TN_LON_MAX


# ─── Server-side admin auth ────────────────────────────────────
ADMIN_USER = os.getenv("ADMIN_USER", "batch16")
ADMIN_PASS_HASH = hashlib.sha256(
    os.getenv("ADMIN_PASS", "123").encode()
).hexdigest()
_admin_tokens: dict[str, float] = {}  # token -> expiry timestamp
ADMIN_TOKEN_TTL = 3600  # 1 hour


def _verify_admin_token(token: str) -> bool:
    if not token or token not in _admin_tokens:
        return False
    if datetime.now().timestamp() > _admin_tokens[token]:
        _admin_tokens.pop(token, None)
        return False
    return True


# ─── Lifespan ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    """Preload ML model and dataset on startup."""
    log.info("Preloading ML model and zones...")
    try:
        zones = get_all_zones()
        log.info(f"Loaded {len(zones)} accident zones. Server ready.")
    except Exception as e:
        log.error(f"Model preload failed: {e}")
    yield


# FastAPI app
app = FastAPI(
    title="SafeRoute-AI",
    description="Smart Accident Risk Navigation System for Tamil Nadu",
    version="2.1.0",
    lifespan=lifespan,
)

# CORS — restrict to same-origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

FRONTEND_PATH = PROJECT_ROOT / "frontend" / "index.html"
ADMIN_PATH = PROJECT_ROOT / "frontend" / "admin.html"
LOGO_DIR = PROJECT_ROOT / "logo"

# Serve logo files as static assets
app.mount("/static", StaticFiles(directory=str(LOGO_DIR)), name="static")


# ─── Security headers middleware ───────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ─── Request Models ─────────────────────────────────────────────

class RouteRequest(BaseModel):
    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float

    @field_validator("origin_lat", "dest_lat")
    @classmethod
    def lat_in_range(cls, v):
        if not (TN_LAT_MIN <= v <= TN_LAT_MAX):
            raise ValueError("Latitude is outside Tamil Nadu region")
        return v

    @field_validator("origin_lon", "dest_lon")
    @classmethod
    def lon_in_range(cls, v):
        if not (TN_LON_MIN <= v <= TN_LON_MAX):
            raise ValueError("Longitude is outside Tamil Nadu region")
        return v


# ─── Endpoints ───────────────────────────────────────────────────

@app.get("/")
async def serve_frontend():
    """Serve the frontend HTML file."""
    if FRONTEND_PATH.exists():
        return FileResponse(str(FRONTEND_PATH), media_type="text/html")
    return JSONResponse(
        {"error": "Frontend not found. Place index.html in frontend/ folder."},
        status_code=404,
    )


@app.get("/admin")
async def serve_admin():
    """Serve the admin dashboard."""
    if ADMIN_PATH.exists():
        return FileResponse(str(ADMIN_PATH), media_type="text/html")
    return JSONResponse(
        {"error": "Admin page not found."},
        status_code=404,
    )


@app.get("/api/zones")
async def api_zones():
    """Return all accident zones with risk levels for map display."""
    try:
        zones = get_all_zones()
        log.info(f"Serving {len(zones)} zones")
        return JSONResponse(zones)
    except Exception as e:
        log.error(f"Zone fetch failed: {e}", exc_info=True)
        return JSONResponse({"error": "Failed to load zones"}, status_code=500)


@app.get("/api/zone-insight")
async def api_zone_insight(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    hour: int = Query(None, description="Current hour (0-23)"),
    weather: str = Query(None, description="Weather condition"),
):
    """Return Gemini AI safety briefing for the nearest zone."""
    try:
        if hour is None:
            hour = datetime.now().hour
        if weather is None:
            weather_data = get_weather(lat, lon)
            weather = weather_data["condition"]

        nearest_row, distance = find_nearest_zone(lat, lon)
        if nearest_row is None:
            return JSONResponse({
                "zone_name": "No nearby zone",
                "risk_level": "LOW",
                "ai_insight": "You are far from any known accident hotspot. Drive safely.",
                "weather_risk": weather,
                "distance_km": round(distance, 2),
            })

        zone_data = {
            "location": nearest_row["location"],
            "risk_level": assign_risk_label(nearest_row),
            "accident_count": int(nearest_row["accident_count"]),
            "common_cause": nearest_row["common_cause"].strip(),
            "fatality_rate": float(nearest_row["fatality_rate"]),
        }

        insight = get_safety_insight(zone_data, weather, hour)

        return JSONResponse({
            "zone_name": zone_data["location"],
            "risk_level": zone_data["risk_level"],
            "ai_insight": insight,
            "weather_risk": weather,
            "distance_km": round(distance, 2),
            "accident_count": zone_data["accident_count"],
            "fatality_rate": zone_data["fatality_rate"],
        })

    except Exception as e:
        log.error(f"Zone insight failed: {e}", exc_info=True)
        return JSONResponse({"error": "Failed to get zone insight"}, status_code=500)


@app.post("/api/route-risk")
async def api_route_risk(req: RouteRequest):
    """Return full route risk analysis."""
    try:
        log.info("Route risk analysis requested")
        # Run blocking ORS + ML scoring in thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(score_route, req.origin_lat, req.origin_lon, req.dest_lat, req.dest_lon),
        )
        log.info(f"Route scored: {result['overall_risk']} ({result['total_distance_km']}km)")
        return JSONResponse(result)
    except ValueError as e:
        log.warning(f"Route validation error: {e}")
        return JSONResponse({"error": "Invalid route parameters"}, status_code=400)
    except Exception as e:
        log.error(f"Route risk failed: {e}", exc_info=True)
        return JSONResponse({"error": "Route analysis failed"}, status_code=500)


@app.get("/api/nearby-risk")
async def api_nearby_risk(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    """Check if driver is inside any high-risk zone."""
    try:
        current_hour = datetime.now().hour
        weather_data = get_weather(lat, lon)

        prediction = predict(lat, lon, current_hour, weather_data["condition"])

        zone = prediction.get("nearby_zone")
        distance_km = prediction.get("distance_km", 999)

        # Consider "in risk zone" if within 2km of a HIGH zone or 1km of any zone
        in_risk_zone = False
        if zone:
            if prediction["risk_level"] == "HIGH" and distance_km <= 2:
                in_risk_zone = True
            elif distance_km <= 1:
                in_risk_zone = True

        ai_warning = ""
        if in_risk_zone and zone:
            ai_warning = get_safety_insight(zone, weather_data["condition"], current_hour)

        return JSONResponse({
            "in_risk_zone": in_risk_zone,
            "zone_data": zone,
            "ai_warning": ai_warning,
            "distance_m": round(distance_km * 1000, 0),
            "risk_level": prediction["risk_level"],
            "risk_score": prediction["risk_score"],
            "weather": weather_data,
        })

    except Exception as e:
        log.error(f"Nearby risk failed: {e}", exc_info=True)
        return JSONResponse({"error": "Nearby risk check failed"}, status_code=500)


@app.get("/api/weather")
async def api_weather(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    """Return current weather risk for location."""
    try:
        data = get_weather(lat, lon)
        return JSONResponse(data)
    except Exception as e:
        log.error(f"Weather failed: {e}", exc_info=True)
        return JSONResponse({"error": "Weather data unavailable"}, status_code=500)


@app.post("/api/admin/login")
async def api_admin_login(request: Request):
    """Authenticate admin and return session token."""
    try:
        body = await request.json()
        user = body.get("username", "")
        password = body.get("password", "")
        pass_hash = hashlib.sha256(password.encode()).hexdigest()

        if not hmac.compare_digest(user, ADMIN_USER) or not hmac.compare_digest(pass_hash, ADMIN_PASS_HASH):
            return JSONResponse({"error": "Invalid credentials"}, status_code=401)

        token = secrets.token_hex(32)
        _admin_tokens[token] = datetime.now().timestamp() + ADMIN_TOKEN_TTL
        return JSONResponse({"token": token})
    except Exception as e:
        log.error(f"Admin login failed: {e}")
        return JSONResponse({"error": "Login failed"}, status_code=500)


@app.get("/api/admin/stats")
async def api_admin_stats(authorization: str = Header(None)):
    """Return admin statistics about the system (requires auth)."""
    if not _verify_admin_token(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        import joblib
        zones = get_all_zones()
        total = len(zones)
        high = sum(1 for z in zones if z.get("risk_level") == "HIGH")
        medium = sum(1 for z in zones if z.get("risk_level") == "MEDIUM")
        low = sum(1 for z in zones if z.get("risk_level") == "LOW")

        # Load model metadata if available
        meta_path = PROJECT_ROOT / "model" / "model_metadata.pkl"
        accuracy = "N/A"
        if meta_path.exists():
            meta = joblib.load(str(meta_path))
            accuracy = meta.get("accuracy", "N/A")
            if isinstance(accuracy, float):
                accuracy = f"{accuracy * 100:.2f}%"

        return JSONResponse({
            "total_zones": total,
            "high_risk": high,
            "medium_risk": medium,
            "low_risk": low,
            "model_accuracy": accuracy,
            "model_type": "RandomForestClassifier (200 trees, max_depth=10)",
            "server_status": "online",
            "version": "2.1.0",
        })
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Admin stats failed: {e}", exc_info=True)
        return JSONResponse({"error": "Failed to load stats"}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    print("Starting SafeRoute-AI server on http://localhost:8000")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
