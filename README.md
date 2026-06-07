<h1 align="center">SafeRoute-AI</h1>
<h3 align="center">Smart Accident Risk Navigation System for Tamil Nadu, India</h3>

<p align="center">
  <strong>v2.1.0</strong> &nbsp;|&nbsp; Python &nbsp;|&nbsp; FastAPI &nbsp;|&nbsp; scikit-learn &nbsp;|&nbsp; Gemini AI &nbsp;|&nbsp; Leaflet.js
</p>

---

> A full-stack intelligent navigation system that predicts road accident risk in real time using machine learning, AI-powered safety briefings, live weather data, and interactive mapping — covering **520 accident hotspot zones** across Tamil Nadu.

---

## Table of Contents

- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [ML Pipeline](#ml-pipeline)
- [API Reference](#api-reference)
- [Run Guide](#run-guide)
- [Admin Dashboard](#admin-dashboard)
- [Security](#security)
- [Dataset](#dataset)
- [Screenshots](#screenshots)

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Interactive Risk Map** | Leaflet.js map with 520 color-coded accident zones (HIGH / MEDIUM / LOW), bounded to Tamil Nadu (8.0°–13.6° N, 76.0°–80.5° E) |
| **ML Risk Prediction** | RandomForestClassifier (200 trees, balanced classes) trained on historical accident data with 5-fold cross-validation |
| **AI Safety Analyst** | Google Gemini 2.0 Flash generates contextual 3-sentence safety briefings per zone, with intelligent fallback templates |
| **Route Risk Scoring** | End-to-end route analysis via OpenRouteService — samples every 5 km, applies weather multipliers, produces segment-by-segment timeline |
| **Real-time GPS Tracking** | `watchPosition()` with high accuracy, polls nearby risk every 10 seconds, auto-pans map to user location |
| **Voice Alerts** | Web Speech API (`en-IN` locale) speaks warnings when entering high-risk zones, with cooldown to prevent spam |
| **Weather-Aware Risk** | OpenWeatherMap integration with 10-minute LRU cache; risk multipliers: clear (1.0×), rain (1.3×), fog (1.6×), storm (2.0×) |
| **Admin Dashboard** | Server-side token auth, API health checks, dataset explorer with search, live console, system stats |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  Leaflet.js  │  │  Speech API  │  │  Nominatim Geocoder    │ │
│  │  Map Engine  │  │  Voice Alert │  │  Autocomplete (TN)     │ │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬───────────┘ │
│         │                 │                        │             │
│  ┌──────┴─────────────────┴────────────────────────┴───────────┐ │
│  │                   index.html / admin.html                   │ │
│  │              XSS-safe rendering via esc() helper            │ │
│  └─────────────────────────┬───────────────────────────────────┘ │
└────────────────────────────┼────────────────────────────────────┘
                             │ HTTP (JSON)
┌────────────────────────────┼────────────────────────────────────┐
│                    FastAPI Server (v2.1)                         │
│  ┌─────────────┐  ┌───────┴───────┐  ┌─────────────────────┐   │
│  │  Security   │  │   8 API       │  │  Lifespan Manager   │   │
│  │  Middleware  │  │   Endpoints   │  │  (model preload)    │   │
│  │  (headers)  │  │               │  │                     │   │
│  └─────────────┘  └───┬───┬───┬───┘  └─────────────────────┘   │
│                       │   │   │                                  │
│  ┌────────────────────┘   │   └────────────────────┐            │
│  │                        │                        │            │
│  ▼                        ▼                        ▼            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  ml_model.py │  │  weather.py  │  │  ai_analyst.py       │   │
│  │  RandomForest│  │  OWM + Cache │  │  Gemini 2.0 Flash    │   │
│  │  200 trees   │  │  LRU (200)   │  │  LRU Cache (500)     │   │
│  └──────┬───────┘  └──────────────┘  └──────────────────────┘   │
│         │                                                        │
│  ┌──────┴───────┐  ┌──────────────────────────────────────────┐  │
│  │route_scorer  │  │  Admin Auth (SHA-256 + token sessions)   │  │
│  │  ORS API     │  │  1-hour TTL, hmac.compare_digest         │  │
│  │  5km sampling│  └──────────────────────────────────────────┘  │
│  └──────────────┘                                                │
└──────────────────────────────────────────────────────────────────┘
         │                    │                     │
         ▼                    ▼                     ▼
  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
  │tn_accidents  │  │OpenWeatherMap│  │  Google Gemini API    │
  │  .csv (520)  │  │   API        │  │  gemini-2.0-flash    │
  └──────────────┘  └──────────────┘  └──────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Runtime** | Python 3.11+ | Server-side logic |
| **Web Framework** | FastAPI 0.135.1 + Uvicorn 0.41.0 | Async ASGI server with auto-reload |
| **Machine Learning** | scikit-learn 1.8.0 | RandomForestClassifier for risk prediction |
| **Data Processing** | Pandas 3.0.1, NumPy 2.4.1 | Dataset loading, vectorized haversine |
| **Model Persistence** | Joblib 1.5.3 | Serialization of trained model + metadata |
| **AI / LLM** | Google Generative AI 0.8.6 | Gemini 2.0 Flash safety briefings |
| **HTTP Client** | Requests 2.32.3 | OWM & ORS API calls |
| **Environment** | python-dotenv 1.0.1 | `.env` configuration loading |
| **Async I/O** | Aiofiles 25.1.0 | Async file serving |
| **Frontend** | Vanilla HTML / CSS / JS | Single-page app (no build step) |
| **Mapping** | Leaflet.js + OpenStreetMap | Interactive map with Canvas renderer |
| **Geocoding** | Nominatim OSM | TN-bounded autocomplete search |
| **Routing** | OpenRouteService API | Driving directions + polyline geometry |
| **Weather** | OpenWeatherMap API | Real-time weather conditions |
| **Voice** | Web Speech API | Spoken risk alerts (en-IN) |

---

## Project Structure

```
roadsense-ai/
├── .env                        # API keys & admin credentials (git-ignored)
├── .gitignore                  # Excludes .env, __pycache__, *.pkl, IDE files
├── requirements.txt            # Pinned Python dependencies
├── README.md
│
├── backend/
│   ├── __init__.py             # Package marker
│   ├── main.py                 # FastAPI app — endpoints, middleware, auth, CORS
│   ├── ml_model.py             # ML training pipeline, prediction, zone lookup
│   ├── weather.py              # OpenWeatherMap integration with LRU cache
│   ├── ai_analyst.py           # Gemini AI safety briefing engine
│   └── route_scorer.py         # ORS routing + segment-by-segment risk scoring
│
├── frontend/
│   ├── index.html              # Main SPA — map, search, route analysis, GPS
│   └── admin.html              # Admin dashboard — stats, API tester, dataset explorer
│
├── dataset/
│   └── tn_accidents.csv        # 520 accident hotspot zones across Tamil Nadu
│
├── model/
│   ├── risk_model.pkl          # Trained RandomForest model (auto-generated)
│   └── model_metadata.pkl      # Feature columns, encoders, accuracy metrics
│
└── logo/                       # Static logo assets
```

---

## ML Pipeline

### Algorithm

**RandomForestClassifier** with optimized hyperparameters:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `n_estimators` | 200 | Ensemble of 200 decision trees for stable predictions |
| `max_depth` | 10 | Prevents overfitting on small dataset |
| `min_samples_leaf` | 3 | Ensures leaf nodes are statistically meaningful |
| `class_weight` | `"balanced"` | Handles imbalanced HIGH/MEDIUM/LOW distribution |
| `random_state` | 42 | Full reproducibility |

### Feature Engineering (6 features)

| Feature | Type | Derivation |
|---------|------|-----------|
| `hour_of_day` | int (0–23) | Current hour of prediction request |
| `is_night` | binary | 1 if hour ∈ [20:00–05:00], else 0 |
| `road_type_encoded` | int | highway → 2, urban → 1, rural → 0 |
| `weather_risk_encoded` | int | storm → 3, fog → 2, rain → 1, clear → 0 |
| `accident_density` | float [0, 1] | Min-max normalized accident count |
| `fatality_rate` | float [0, 1] | Ratio of fatalities to total accidents |

### Risk Classification Rules

| Level | Condition |
|-------|-----------|
| **HIGH** | `accident_count > 35` OR `fatality_rate > 0.40` |
| **MEDIUM** | `accident_count > 20` OR `fatality_rate > 0.25` |
| **LOW** | Everything else |

### Risk Score Formula

$$\text{risk\_score} = 0.6 \times \frac{\text{accident\_count} - \min}{\max - \min} + 0.4 \times \text{fatality\_rate}$$

Clipped to [0, 1]. Used for route segment visualization and heatmap intensity.

### Training Pipeline

```
CSV (520 zones) → Label Assignment → Feature Engineering
    → 80/20 Stratified Split → RandomForest Training
    → Test Accuracy + 5-Fold CV → Serialize to .pkl
```

### Evaluation

| Metric | Value |
|--------|-------|
| Test Accuracy | ~100% |
| 5-Fold CV Accuracy | ~98.65% ± 1.68% |
| Classification Report | Precision, Recall, F1 per class |

---

## API Reference

### Public Endpoints

#### `GET /api/zones`
Returns all 520 accident zones with risk data.

**Response:**
```json
[
  {
    "location": "Chennai OMR IT Corridor",
    "lat": 13.0569,
    "lon": 80.2425,
    "risk_level": "HIGH",
    "risk_score": 0.87,
    "accident_count": 45,
    "fatality_rate": 0.42,
    "road_type": "highway",
    "common_cause": "overspeeding",
    "weather_risk": "normal",
    "peak_hour_start": 17,
    "peak_hour_end": 21
  }
]
```

#### `GET /api/zone-insight?lat={lat}&lon={lon}&hour={h}&weather={w}`
Returns Gemini AI safety briefing for the nearest zone.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `lat` | float | Yes | Latitude (8.0–13.6) |
| `lon` | float | Yes | Longitude (76.0–80.5) |
| `hour` | int | No | Hour of day (0–23) |
| `weather` | string | No | Weather condition |

**Response:**
```json
{
  "zone_name": "Chennai OMR IT Corridor",
  "risk_level": "HIGH",
  "ai_insight": "This stretch has 45 accidents in 3 years with 42% fatality...",
  "weather_risk": "normal",
  "distance_km": 2.3,
  "accident_count": 45,
  "fatality_rate": 0.42
}
```

#### `POST /api/route-risk`
Full route risk analysis with segment-by-segment scoring.

**Request:**
```json
{
  "origin_lat": 13.0827,
  "origin_lon": 80.2707,
  "dest_lat": 12.9716,
  "dest_lon": 79.1594
}
```

**Response:**
```json
{
  "overall_risk": "HIGH",
  "overall_score": 0.72,
  "total_distance_km": 508.0,
  "duration_min": 420.5,
  "weather": { "condition": "clear", "temp_c": 30.0, "visibility_km": 10.0, "risk_multiplier": 1.0 },
  "high_risk_segments": [{ "km": 45, "lat": 12.95, "lon": 79.85, "location": "...", "risk": "HIGH", "score": 0.87 }],
  "zone_warnings": [{ "location": "...", "risk_level": "HIGH", "accident_count": 45, "common_cause": "overspeeding" }],
  "route_polyline": [[13.08, 80.27], [13.05, 80.20]],
  "timeline": [{ "km": 0, "lat": 13.08, "lon": 80.27, "risk": "LOW", "score": 0.15 }]
}
```

#### `GET /api/nearby-risk?lat={lat}&lon={lon}`
Checks if the user's GPS location is inside a risk zone.

**Response:**
```json
{
  "in_risk_zone": true,
  "zone_data": { "location": "...", "risk_level": "HIGH" },
  "ai_warning": "Reduce speed immediately...",
  "distance_m": 450,
  "risk_level": "HIGH",
  "risk_score": 0.87,
  "weather": { "condition": "rain", "risk_multiplier": 1.3 }
}
```

#### `GET /api/weather?lat={lat}&lon={lon}`
Returns live weather and risk multiplier.

**Response:**
```json
{
  "condition": "rain",
  "temp_c": 28.7,
  "visibility_km": 6.5,
  "risk_multiplier": 1.3
}
```

### Admin Endpoints

#### `POST /api/admin/login`
Authenticates admin, returns session token.

**Request:**
```json
{ "username": "batch16", "password": "123" }
```

**Response:**
```json
{ "token": "a4f8e2c1d9b3..." }
```

#### `GET /api/admin/stats`
Server statistics (requires `Authorization` header with valid token).

**Response:**
```json
{
  "total_zones": 520,
  "high_risk": 156,
  "medium_risk": 234,
  "low_risk": 130,
  "model_accuracy": 1.0,
  "model_type": "RandomForest",
  "server_status": "running",
  "version": "2.1.0"
}
```

---

## Run Guide

### Prerequisites

- **Python 3.11+** installed (invoked as `py` on Windows)
- API keys for: [Google Gemini](https://aistudio.google.com/), [OpenWeatherMap](https://openweathermap.org/api), [OpenRouteService](https://openrouteservice.org/)

### Step 1 — Navigate to project

```powershell
cd d:\AccidentRiskMap_mp2\roadsense-ai
```

### Step 2 — Install dependencies

```powershell
py -m pip install -r requirements.txt
```

### Step 3 — Configure environment

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_gemini_api_key
OPENWEATHER_API_KEY=your_openweather_api_key
OPENROUTESERVICE_API_KEY=your_ors_api_key
ADMIN_USER=batch16
ADMIN_PASS=123
```

### Step 4 — Train the ML model

```powershell
py backend/ml_model.py
```

Output: model saved to `model/risk_model.pkl` + `model/model_metadata.pkl`

### Step 5 — Start the server

```powershell
$env:PYTHONPATH = "d:\AccidentRiskMap_mp2\roadsense-ai"; py -m uvicorn backend.main:app --reload --port 8000
```

### Step 6 — Open in browser

| Page | URL |
|------|-----|
| Main App | [http://localhost:8000](http://localhost:8000) |
| Admin Dashboard | [http://localhost:8000/admin](http://localhost:8000/admin) |

### Stop the server

```powershell
# Option 1: Press Ctrl+C in the terminal

# Option 2: Kill all Python processes
Get-Process -Name "py","python" -ErrorAction SilentlyContinue | Stop-Process -Force
```

---

## Admin Dashboard

The admin panel at `/admin` provides:

| Tab | Function |
|-----|----------|
| **API Health Check** | Automated testing of all 6 API endpoints with pass/fail results |
| **Dataset Explorer** | Searchable table of all 520 zones — filter by location, view coordinates, road type, cause, fatality rate |
| **Project Info** | System architecture overview, ML model details, endpoint documentation |
| **Live Console** | Real-time API activity log with color-coded timestamps |

**Login:** `POST /api/admin/login` → server issues 64-char hex token (1-hour TTL) → stored in `sessionStorage`

---

## Security

| Layer | Implementation |
|-------|---------------|
| **Authentication** | Server-side SHA-256 password hashing, `hmac.compare_digest` for timing-safe comparison |
| **Session Tokens** | `secrets.token_hex(32)`, 1-hour TTL, in-memory store |
| **XSS Prevention** | `esc()` helper escapes all dynamic HTML via `textContent` → `innerHTML` pattern |
| **Security Headers** | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` |
| **CORS** | `credentials=False`, methods restricted to `GET/POST`, headers to `Content-Type/Authorization` |
| **Input Validation** | Strict Tamil Nadu coordinate bounds (no buffer), Pydantic field validators |
| **Error Handling** | Generic messages to client, full tracebacks logged server-side with `exc_info=True` |
| **Secrets Management** | `.env` file git-ignored, no hardcoded credentials in source |

---

## Dataset

**File:** `dataset/tn_accidents.csv` — **520 accident hotspot zones**

| Column | Type | Description |
|--------|------|-------------|
| `location` | string | Named accident hotspot (e.g., "Chennai OMR IT Corridor") |
| `latitude` | float | GPS latitude (8.0–13.6° N) |
| `longitude` | float | GPS longitude (76.0–80.5° E) |
| `accident_count` | int | 3-year total accident count (range: 18–45) |
| `peak_hour_start` | int | Start of peak accident window (0–23) |
| `peak_hour_end` | int | End of peak accident window (0–23) |
| `road_type` | string | `highway` / `urban` / `rural` |
| `common_cause` | string | Primary cause (overspeeding, drunk_driving, fatigue, etc.) |
| `weather_risk` | string | Baseline weather risk (normal, rain, fog, storm) |
| `fatality_rate` | float | Fatality ratio (0.0–1.0) |

**Coverage:** All major districts — Chennai, Coimbatore, Madurai, Salem, Trichy, Vellore, Thanjavur, Tirunelveli, Kanyakumari, and 30+ more across highways, urban roads, and rural routes.

---

## Screenshots

![SafeRoute-AI Screenshot](screenshot.png)

---

<p align="center">
  Built with FastAPI + scikit-learn + Gemini AI + Leaflet.js<br>
  <strong>SafeRoute-AI v2.1.0</strong> — Batch 16
</p>
# MP2-SafeRouteAI
