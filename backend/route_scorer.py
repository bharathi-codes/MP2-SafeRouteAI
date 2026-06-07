"""
SafeRoute-AI — Route Risk Scorer
Scores entire routes using OpenRouteService geometry + ML predictions + weather.
"""

import logging
import os
import math
import requests
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

log = logging.getLogger("roadsense.route")

ORS_API_KEY = os.getenv("OPENROUTESERVICE_API_KEY", "")
ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"


def _haversine(lat1, lon1, lat2, lon2):
    """Distance in km between two points."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _get_route_geometry(origin_lat, origin_lon, dest_lat, dest_lon):
    """Call OpenRouteService to get route geometry."""
    if not ORS_API_KEY:
        raise ValueError("OpenRouteService API key not configured.")

    log.info(f"Fetching ORS route: ({origin_lat:.4f},{origin_lon:.4f}) -> ({dest_lat:.4f},{dest_lon:.4f})")

    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json; charset=utf-8",
    }
    body = {
        "coordinates": [
            [float(origin_lon), float(origin_lat)],
            [float(dest_lon), float(dest_lat)],
        ],
        "geometry": True,
        "instructions": False,
    }

    resp = requests.post(ORS_URL, json=body, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if not data.get("routes") or len(data["routes"]) == 0:
        raise ValueError("No route found between these points")
    route = data["routes"][0]
    if "summary" not in route:
        raise ValueError("Invalid route response from routing service")
    # Decode geometry — ORS returns encoded polyline or GeoJSON
    geometry = route.get("geometry")

    # ORS returns encoded polyline by default
    if isinstance(geometry, str):
        coords = _decode_polyline(geometry)
    else:
        coords = geometry.get("coordinates", [])
        # ORS GeoJSON is [lon, lat]; convert to [lat, lon]
        coords = [[c[1], c[0]] for c in coords]

    distance_m = route["summary"]["distance"]
    duration_s = route["summary"]["duration"]

    return {
        "coordinates": coords,  # list of [lat, lon]
        "distance_km": round(distance_m / 1000, 2),
        "duration_min": round(duration_s / 60, 1),
    }


def _decode_polyline(encoded, precision=5):
    """Decode an encoded polyline string into a list of [lat, lon] pairs."""
    inv = 1.0 / (10 ** precision)
    decoded = []
    previous = [0, 0]
    i = 0
    while i < len(encoded):
        for dim in range(2):
            shift = 0
            result = 0
            while True:
                char_code = ord(encoded[i]) - 63
                i += 1
                result |= (char_code & 0x1F) << shift
                shift += 5
                if char_code < 0x20:
                    break
            if result & 1:
                result = ~result
            result >>= 1
            previous[dim] += result
        decoded.append([previous[0] * inv, previous[1] * inv])
    return decoded


def _sample_route_points(coords, interval_km=5):
    """
    Sample points along the route at regular intervals.
    Returns list of {lat, lon, km} dicts.
    """
    if not coords:
        return []

    points = [{"lat": coords[0][0], "lon": coords[0][1], "km": 0}]
    cumulative_km = 0
    last_sample_km = 0

    for i in range(1, len(coords)):
        seg_km = _haversine(coords[i-1][0], coords[i-1][1],
                            coords[i][0], coords[i][1])
        cumulative_km += seg_km

        if cumulative_km - last_sample_km >= interval_km:
            points.append({
                "lat": coords[i][0],
                "lon": coords[i][1],
                "km": round(cumulative_km, 1),
            })
            last_sample_km = cumulative_km

    # Always include final point
    if coords:
        points.append({
            "lat": coords[-1][0],
            "lon": coords[-1][1],
            "km": round(cumulative_km, 1),
        })

    return points


def score_route(origin_lat, origin_lon, dest_lat, dest_lon):
    """
    Score an entire route for risk.
    Returns comprehensive route risk report.
    """
    from backend.ml_model import predict, get_all_zones, find_nearest_zone
    from backend.weather import get_weather
    from datetime import datetime

    current_hour = datetime.now().hour

    # Get route geometry
    route_data = _get_route_geometry(origin_lat, origin_lon, dest_lat, dest_lon)
    coords = route_data["coordinates"]
    total_distance_km = route_data["distance_km"]

    # Get weather at origin
    weather = get_weather(origin_lat, origin_lon)
    weather_condition = weather["condition"]
    weather_multiplier = weather["risk_multiplier"]

    # Sample route points every 5km
    sample_points = _sample_route_points(coords, interval_km=5)

    # Score each sample point
    timeline = []
    high_risk_segments = []
    zone_warnings = []
    seen_zones = set()
    risk_scores = []

    for point in sample_points:
        prediction = predict(
            point["lat"], point["lon"],
            current_hour, weather_condition
        )

        # Apply weather multiplier to risk score
        adjusted_score = min(1.0, prediction["risk_score"] * weather_multiplier)
        risk_scores.append(adjusted_score)

        zone_info = prediction.get("nearby_zone")
        zone_name = zone_info["location"] if zone_info else "Open Road"

        entry = {
            "km": point["km"],
            "lat": round(point["lat"], 4),
            "lon": round(point["lon"], 4),
            "location": zone_name,
            "risk": prediction["risk_level"],
            "score": round(adjusted_score, 3),
            "distance_to_zone_km": prediction.get("distance_km", 999),
        }
        timeline.append(entry)

        # Track high and medium risk segments for zone warnings
        if prediction["risk_level"] in ("HIGH", "MEDIUM") and zone_info:
            if prediction["risk_level"] == "HIGH":
                high_risk_segments.append(entry)
            if zone_name not in seen_zones:
                seen_zones.add(zone_name)
                zone_warnings.append({
                    "location": zone_name,
                    "risk_level": prediction["risk_level"],
                    "accident_count": zone_info.get("accident_count", 0),
                    "common_cause": zone_info.get("common_cause", "unknown"),
                    "fatality_rate": zone_info.get("fatality_rate", 0),
                    "km_marker": point["km"],
                })

    # Overall risk assessment
    if risk_scores:
        avg_score = sum(risk_scores) / len(risk_scores)
        max_score = max(risk_scores)
        overall_score = round(0.4 * avg_score + 0.6 * max_score, 3)
    else:
        overall_score = 0.1

    if overall_score > 0.6:
        overall_risk = "HIGH"
    elif overall_score > 0.3:
        overall_risk = "MEDIUM"
    else:
        overall_risk = "LOW"

    # Convert coordinates to polyline format for frontend [lat, lon]
    route_polyline = [[round(c[0], 5), round(c[1], 5)] for c in coords]

    return {
        "overall_risk": overall_risk,
        "overall_score": overall_score,
        "total_distance_km": total_distance_km,
        "duration_min": route_data["duration_min"],
        "weather": weather,
        "high_risk_segments": high_risk_segments,
        "zone_warnings": zone_warnings,
        "route_polyline": route_polyline,
        "timeline": timeline,
    }
