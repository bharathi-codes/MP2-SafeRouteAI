"""
SafeRoute-AI — Weather Module
Fetches live weather data from OpenWeatherMap and computes risk multiplier.
"""

import os
import logging
import time
import requests
from collections import OrderedDict
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

log = logging.getLogger("roadsense.weather")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

# Cache: key = "lat,lon" (rounded), value = (timestamp, data)
_weather_cache = OrderedDict()
CACHE_TTL = 600  # 10 minutes
CACHE_MAX_SIZE = 200  # Max cached locations


def _round_coords(lat, lon):
    """Round coordinates to 2 decimal places for cache key."""
    return f"{round(lat, 2)},{round(lon, 2)}"


def _classify_condition(weather_main, visibility=None):
    """Map OpenWeatherMap main weather to our risk categories."""
    w = weather_main.lower()
    if w in ("thunderstorm",):
        return "storm"
    if w in ("drizzle", "rain"):
        return "rain"
    if w in ("mist", "fog", "haze", "smoke"):
        return "fog"
    if w in ("snow", "squall", "tornado"):
        return "storm"
    # Check low visibility even if condition is 'clear'
    if visibility is not None and visibility < 2000:
        return "fog"
    return "clear"


def _get_risk_multiplier(condition):
    """Return risk multiplier based on weather condition."""
    multipliers = {
        "clear": 1.0,
        "normal": 1.0,
        "rain": 1.3,
        "fog": 1.6,
        "storm": 2.0,
    }
    return multipliers.get(condition, 1.0)


def get_weather(lat, lon):
    """
    Fetch current weather for a location.
    Returns: {condition, temp_c, visibility_km, risk_multiplier}
    """
    cache_key = _round_coords(lat, lon)

    # Check cache
    if cache_key in _weather_cache:
        cached_time, cached_data = _weather_cache[cache_key]
        if time.time() - cached_time < CACHE_TTL:
            _weather_cache.move_to_end(cache_key)  # LRU promotion
            return cached_data
        else:
            del _weather_cache[cache_key]  # Expired

    # Default fallback
    fallback = {
        "condition": "clear",
        "temp_c": 30.0,
        "visibility_km": 10.0,
        "risk_multiplier": 1.0,
    }

    if not OPENWEATHER_API_KEY:
        log.warning("No API key configured, returning default.")
        return fallback

    try:
        resp = requests.get(
            OPENWEATHER_URL,
            params={
                "lat": lat,
                "lon": lon,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        weather_main = data.get("weather", [{}])[0].get("main", "Clear")
        temp_c = data.get("main", {}).get("temp", 30.0)
        temp_c = max(-10, min(55, temp_c))  # Clamp to reasonable range
        visibility = data.get("visibility", 10000)  # meters
        visibility = max(0, min(50000, visibility))  # Clamp to 0-50km
        visibility_km = round(visibility / 1000, 1)

        condition = _classify_condition(weather_main, visibility)
        risk_multiplier = _get_risk_multiplier(condition)

        result = {
            "condition": condition,
            "temp_c": round(temp_c, 1),
            "visibility_km": visibility_km,
            "risk_multiplier": risk_multiplier,
        }

        # Cache it (bounded, LRU promotion)
        _weather_cache[cache_key] = (time.time(), result)
        _weather_cache.move_to_end(cache_key)
        if len(_weather_cache) > CACHE_MAX_SIZE:
            _weather_cache.popitem(last=False)
        return result

    except Exception as e:
        log.error(f"Weather API error: {e}")
        return fallback
