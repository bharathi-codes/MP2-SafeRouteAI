"""
SafeRoute-AI — Gemini AI Safety Analyst
Provides contextual safety briefings using Gemini 2.0 Flash.
"""

import logging
import os
from collections import OrderedDict
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

log = logging.getLogger("roadsense.ai")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# In-memory cache: key = "location|weather|hour" (bounded)
_insight_cache = OrderedDict()
_INSIGHT_CACHE_MAX = 500

# Lazy-init Gemini model
_gemini_model = None


def _init_gemini():
    """Initialize Gemini model on first use."""
    global _gemini_model
    if _gemini_model is not None:
        return _gemini_model

    if not GEMINI_API_KEY:
        log.warning("No Gemini API key configured.")
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel("gemini-2.0-flash")
        log.info("Gemini 2.0 Flash initialized.")
        return _gemini_model
    except Exception as e:
        log.error(f"Failed to initialize Gemini: {e}")
        return None


def _build_prompt(zone, weather, hour):
    """Build the prompt for Gemini."""
    return f"""You are SafeRoute-AI, an expert Tamil Nadu road safety analyst. Give CONCISE, PRACTICAL safety briefings. Max 3 sentences.

Driver approaching: {zone.get('location', 'Unknown Zone')}
Risk level: {zone.get('risk_level', 'UNKNOWN')} | Accidents (3yr): {zone.get('accident_count', 0)}
Current time: {hour}:00 | Weather: {weather}
Main cause: {zone.get('common_cause', 'unknown')} | Fatality rate: {zone.get('fatality_rate', 0)}

Give an urgent, specific safety briefing for this driver RIGHT NOW.
Include: why it's dangerous, what to watch for, one specific action."""


def _fallback_insight(zone, weather, hour):
    """Generate a fallback message when Gemini is unavailable."""
    location = zone.get("location", "this zone")
    risk = zone.get("risk_level", "UNKNOWN")
    cause = zone.get("common_cause", "various factors")
    accident_count = zone.get("accident_count", 0)
    fatality_rate = zone.get("fatality_rate", 0)

    hour_int = int(hour) if hour is not None else 0
    time_warning = ""
    if hour_int >= 20 or hour_int <= 5:
        time_warning = "Night driving increases danger significantly. "

    weather_warning = ""
    if weather in ("rain", "fog", "storm"):
        weather_warning = f"Current {weather} conditions further elevate risk. "

    return (
        f"CAUTION: {location} is a {risk}-risk zone with {accident_count} accidents "
        f"recorded (fatality rate: {fatality_rate:.0%}). Primary cause: {cause}. "
        f"{time_warning}{weather_warning}"
        f"Reduce speed, maintain safe following distance, and stay fully alert."
    )


def get_safety_insight(zone, weather, hour):
    """
    Get an AI-powered safety briefing for a zone.
    
    Args:
        zone: dict with location, risk_level, accident_count, common_cause, fatality_rate
        weather: str - current weather condition (rain/fog/clear/storm)
        hour: int or str - current hour (0-23)
    
    Returns: str - safety briefing text
    """
    # Cache key
    cache_key = f"{zone.get('location', '')}|{weather}|{hour}"
    if cache_key in _insight_cache:
        _insight_cache.move_to_end(cache_key)  # LRU promotion
        return _insight_cache[cache_key]

    # Try Gemini
    model = _init_gemini()
    if model is not None:
        try:
            prompt = _build_prompt(zone, weather, hour)
            response = model.generate_content(prompt)
            insight = response.text.strip()

            # Cache and return (bounded)
            _insight_cache[cache_key] = insight
            if len(_insight_cache) > _INSIGHT_CACHE_MAX:
                _insight_cache.popitem(last=False)
            return insight
        except Exception as e:
            log.error(f"Gemini API error: {e}")

    # Fallback
    insight = _fallback_insight(zone, weather, hour)
    _insight_cache[cache_key] = insight
    if len(_insight_cache) > _INSIGHT_CACHE_MAX:
        _insight_cache.popitem(last=False)
    return insight
