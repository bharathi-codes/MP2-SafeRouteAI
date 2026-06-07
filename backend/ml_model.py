"""
SafeRoute-AI — ML Risk Prediction Model
Trains a RandomForestClassifier on Tamil Nadu accident data.
Run standalone to train: python backend/ml_model.py
"""

import os
import sys
import logging
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, classification_report
import joblib
import math

log = logging.getLogger("roadsense.ml")

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_PATH = os.path.join(BASE_DIR, "dataset", "tn_accidents.csv")
MODEL_DIR = os.path.join(BASE_DIR, "model")
MODEL_PATH = os.path.join(MODEL_DIR, "risk_model.pkl")
METADATA_PATH = os.path.join(MODEL_DIR, "model_metadata.pkl")

# Global state (loaded at import time or after training)
_model = None
_metadata = None
_zones_df = None
_zone_lats = None  # numpy array for vectorized distance
_zone_lons = None  # numpy array for vectorized distance


def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two lat/lon points."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_dataset():
    """Load and return the accident dataset."""
    df = pd.read_csv(DATASET_PATH, encoding="utf-8")
    df.columns = df.columns.str.strip()
    # Strip quotes from location
    df["location"] = df["location"].str.strip('"').str.strip()
    return df


def engineer_features(df, hour=None, weather_condition=None):
    """
    Feature engineering pipeline.
    If hour/weather_condition are provided, they override the dataset columns
    (used for single-point prediction).
    """
    df = df.copy()

    # Encode road_type
    road_map = {"highway": 2, "urban": 1, "rural": 0}
    mapped = df["road_type"].str.strip().map(road_map)
    unknown = df[mapped.isna()]["road_type"].unique()
    if len(unknown) > 0:
        log.warning(f"Unknown road_type values defaulting to 'urban': {unknown.tolist()}")
    df["road_type_encoded"] = mapped.fillna(1).astype(int)

    # Encode weather_risk
    weather_map = {"fog": 2, "rain": 1, "storm": 3, "normal": 0, "clear": 0}
    if weather_condition is not None:
        df["weather_risk_encoded"] = weather_map.get(weather_condition.lower(), 0)
    else:
        df["weather_risk_encoded"] = df["weather_risk"].str.strip().map(weather_map).fillna(0).astype(int)

    # Hour of day
    if hour is not None:
        df["hour_of_day"] = int(hour)
    else:
        df["hour_of_day"] = df["peak_hour_start"]

    # Is night (20-5)
    df["is_night"] = df["hour_of_day"].apply(lambda h: 1 if (h >= 20 or h <= 5) else 0)

    # Accident density (normalized 0-1)
    max_count = df["accident_count"].max()
    min_count = df["accident_count"].min()
    if abs(max_count - min_count) > 1e-6:
        df["accident_density"] = (df["accident_count"] - min_count) / (max_count - min_count)
    else:
        df["accident_density"] = 0.5

    feature_cols = [
        "hour_of_day", "is_night", "road_type_encoded",
        "weather_risk_encoded", "accident_density", "fatality_rate"
    ]
    return df, feature_cols


def assign_risk_label(row):
    """Assign risk level based on thresholds."""
    if row["accident_count"] > 35 or row["fatality_rate"] > 0.4:
        return "HIGH"
    elif row["accident_count"] > 20 or row["fatality_rate"] > 0.25:
        return "MEDIUM"
    else:
        return "LOW"


def train_model():
    """Train the RandomForest model and save to disk."""
    print("=" * 50)
    print("SafeRoute-AI — ML Model Training")
    print("=" * 50)

    # Load data
    print(f"\n[1/5] Loading dataset from {DATASET_PATH}...")
    df = load_dataset()
    print(f"      Loaded {len(df)} accident zones.")

    # Assign labels
    print("[2/5] Assigning risk labels...")
    df["risk_level"] = df.apply(assign_risk_label, axis=1)
    print(f"      Distribution: {df['risk_level'].value_counts().to_dict()}")

    # Feature engineering
    print("[3/5] Engineering features...")
    df, feature_cols = engineer_features(df)
    X = df[feature_cols].values
    y = df["risk_level"].values

    # Encode target
    le = LabelEncoder()
    y_encoded = le.fit_transform(y)

    # Train/test split
    print("[4/5] Training RandomForestClassifier (n_estimators=200, max_depth=10)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded, test_size=0.2, random_state=42, stratify=y_encoded
    )

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        min_samples_leaf=3,
        random_state=42,
        class_weight="balanced"
    )
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"\n      Test Accuracy: {accuracy:.2%}")

    # Cross-validation for robust accuracy estimate
    cv_scores = cross_val_score(model, X, y_encoded, cv=5, scoring="accuracy")
    print(f"      Cross-Validation Accuracy: {cv_scores.mean():.2%} (+/- {cv_scores.std():.2%})")
    print(f"\n      Classification Report:")
    print(classification_report(y_test, y_pred, target_names=le.classes_))

    # Save model
    print(f"[5/5] Saving model to {MODEL_PATH}...")
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, MODEL_PATH)

    # Save metadata (label encoder, feature cols, normalization params)
    metadata = {
        "label_encoder_classes": le.classes_.tolist(),
        "feature_cols": feature_cols,
        "accident_count_min": int(df["accident_count"].min()),
        "accident_count_max": int(df["accident_count"].max()),
        "accuracy": float(accuracy),
        "cv_accuracy": float(cv_scores.mean()),
        "cv_std": float(cv_scores.std()),
        "total_zones": len(df),
    }
    joblib.dump(metadata, METADATA_PATH)

    print(f"      Model saved successfully!")
    print(f"      Metadata saved to {METADATA_PATH}")
    print("=" * 50)
    print("Training complete. Model ready for predictions.")
    print("=" * 50)

    return model, metadata


def _load_model():
    """Load the trained model and metadata from disk."""
    global _model, _metadata, _zones_df, _zone_lats, _zone_lons
    if _model is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Model not found at {MODEL_PATH}. Run 'python backend/ml_model.py' first."
            )
        _model = joblib.load(MODEL_PATH)
        _metadata = joblib.load(METADATA_PATH)
        _zones_df = load_dataset()
        _zones_df["risk_level"] = _zones_df.apply(assign_risk_label, axis=1)
        # Precompute numpy arrays for vectorized distance calculations
        _zone_lats = _zones_df["latitude"].values
        _zone_lons = _zones_df["longitude"].values
        log.info(f"Model loaded: {len(_zones_df)} zones, accuracy={_metadata.get('accuracy', 'N/A')}")
    return _model, _metadata, _zones_df


def get_all_zones():
    """Return all zones with risk levels for map display."""
    _, metadata, df = _load_model()
    df = df.copy()
    df["risk_level"] = df.apply(assign_risk_label, axis=1)

    # Compute a numeric risk_score 0-1
    max_count = metadata["accident_count_max"]
    min_count = metadata["accident_count_min"]
    if max_count > min_count:
        df["risk_score"] = (
            0.6 * (df["accident_count"] - min_count) / (max_count - min_count) +
            0.4 * df["fatality_rate"]
        )
    else:
        df["risk_score"] = df["fatality_rate"]

    df["risk_score"] = df["risk_score"].clip(0, 1).round(3)

    zones = []
    for _, row in df.iterrows():
        zones.append({
            "location": row["location"],
            "lat": float(row["latitude"]),
            "lon": float(row["longitude"]),
            "risk_level": row["risk_level"],
            "risk_score": float(row["risk_score"]),
            "accident_count": int(row["accident_count"]),
            "fatality_rate": float(row["fatality_rate"]),
            "road_type": row["road_type"].strip(),
            "common_cause": row["common_cause"].strip(),
            "weather_risk": row["weather_risk"].strip(),
            "peak_hour_start": int(row["peak_hour_start"]),
            "peak_hour_end": int(row["peak_hour_end"]),
        })
    return zones


def find_nearest_zone(lat, lon, max_distance_km=50):
    """Find the nearest accident zone to a given lat/lon using vectorized haversine."""
    _, _, df = _load_model()
    # Vectorized haversine using precomputed numpy arrays
    R = 6371
    lat1 = np.radians(lat)
    lon1 = np.radians(lon)
    lat2 = np.radians(_zone_lats)
    lon2 = np.radians(_zone_lons)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    distances = R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    idx = np.argmin(distances)
    best_dist = distances[idx]
    if best_dist > max_distance_km:
        return None, float(best_dist)
    return df.iloc[idx], float(best_dist)


def predict(lat, lon, current_hour, weather_condition):
    """
    Predict risk for a given location, hour, and weather.
    Returns: {risk_level, confidence, nearby_zone, risk_score}
    """
    model, metadata, df = _load_model()

    # Find nearest zone
    nearest_row, distance_km = find_nearest_zone(lat, lon)

    if nearest_row is None:
        return {
            "risk_level": "LOW",
            "confidence": 0.5,
            "risk_score": 0.1,
            "nearby_zone": None,
            "distance_km": distance_km,
        }

    # Build feature vector for this point
    point_df = pd.DataFrame([{
        "accident_count": int(nearest_row["accident_count"]),
        "fatality_rate": float(nearest_row["fatality_rate"]),
        "road_type": nearest_row["road_type"].strip(),
        "weather_risk": nearest_row["weather_risk"].strip(),
        "peak_hour_start": int(nearest_row["peak_hour_start"]),
    }])

    point_df, feature_cols = engineer_features(
        point_df, hour=current_hour, weather_condition=weather_condition
    )

    X_point = point_df[feature_cols].values

    # Predict
    le_classes = metadata["label_encoder_classes"]
    pred_encoded = model.predict(X_point)[0]
    pred_proba = model.predict_proba(X_point)[0]

    risk_level = le_classes[pred_encoded]
    confidence = float(max(pred_proba))

    # Risk score: blend of model confidence and distance decay
    distance_factor = max(0, 1 - (distance_km / 50))
    risk_score = round(confidence * distance_factor, 3)

    zone_data = {
        "location": nearest_row["location"],
        "lat": float(nearest_row["latitude"]),
        "lon": float(nearest_row["longitude"]),
        "accident_count": int(nearest_row["accident_count"]),
        "fatality_rate": float(nearest_row["fatality_rate"]),
        "road_type": nearest_row["road_type"].strip(),
        "common_cause": nearest_row["common_cause"].strip(),
        "weather_risk": nearest_row["weather_risk"].strip(),
        "risk_level": risk_level,
    }

    return {
        "risk_level": risk_level,
        "confidence": round(confidence, 3),
        "risk_score": risk_score,
        "nearby_zone": zone_data,
        "distance_km": round(distance_km, 2),
    }


if __name__ == "__main__":
    train_model()
