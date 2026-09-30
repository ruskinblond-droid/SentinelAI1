"""
SentinelAI - Personalized Behavioral Anomaly Detection & Multimodal Fusion Engine

Combines SentinelAI's local personalized statistical anomaly detection model
with TypingDNA's cloud biometric authentication verification signal.

Mathematical & Fusion Architecture:
1. SIGNAL A — SentinelAI Local Personalized ML:
   - Evaluates incoming 9-feature keystroke window against the user's stored baseline.
   - Calculates capped z-scores: z_i = min(abs(x_i - mu_i) / max(sigma_i, floor_i), 4.0)
   - Converts to feature contributions: contribution_i = (z_i / 4.0) * 100.0
   - Aggregates with feature weights: local_anomaly_score in [0.0, 100.0]

2. SIGNAL B — TypingDNA Biometric Verification:
   - Verifies TypingDNA typing pattern via official TypingDNA /verify API.
   - Retrieves normalized similarity score (effective_score in [0.0, 100.0]).
   - Converts similarity into anomaly scale:
         typingdna_anomaly_score = 100.0 - typingdna_score

3. MULTIMODAL FUSION:
   - When both signals are available (fusion_mode = "ML_TYPINGDNA"):
         combined_anomaly_score = 0.70 * local_anomaly_score + 0.30 * typingdna_anomaly_score
   - When TypingDNA is omitted or unavailable (fusion_mode = "LOCAL_ONLY"):
         combined_anomaly_score = local_anomaly_score
   - Bounded strictly between 0.0 and 100.0.

4. Explainability & Dynamic Confidence:
   - Identifies and ranks top anomalous features with plain-language diagnostic explanations.
   - Confidence scales with verified baseline depth: 0.65 (N=3) asymptotically reaching 0.95.
"""

import logging
import math
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.database.models import BehaviorProfile, BehaviorSample, Session as SessionModel
from backend.services.typingdna import verify_pattern, TypingDNAError

logger = logging.getLogger(__name__)

# The 9 SentinelAI behavioral features
FEATURE_FIELDS = [
    "typing_speed",
    "mean_hold_time",
    "std_hold_time",
    "mean_flight_time",
    "std_flight_time",
    "backspace_rate",
    "pause_mean",
    "mouse_velocity_mean",
    "click_interval_mean"
]

# Feature importance weights (keystroke timing carries primary biometric weight)
FEATURE_WEIGHTS = {
    "typing_speed": 1.2,
    "mean_hold_time": 1.4,
    "std_hold_time": 1.1,
    "mean_flight_time": 1.4,
    "std_flight_time": 1.1,
    "backspace_rate": 0.8,
    "pause_mean": 0.9,
    "mouse_velocity_mean": 0.6,
    "click_interval_mean": 0.5
}

# Domain-appropriate standard deviation floors to prevent division by zero
# and avoid over-sensitivity when enrollment sample variance is near zero.
STD_FLOORS = {
    "typing_speed": 5.0,           # Keystrokes per minute
    "mean_hold_time": 8.0,         # Milliseconds
    "std_hold_time": 3.0,          # Milliseconds
    "mean_flight_time": 15.0,      # Milliseconds
    "std_flight_time": 8.0,        # Milliseconds
    "backspace_rate": 0.03,        # Ratio (0.0 - 1.0)
    "pause_mean": 25.0,            # Milliseconds
    "mouse_velocity_mean": 0.05,   # Pixels per millisecond
    "click_interval_mean": 50.0    # Milliseconds
}

# Clear human-readable diagnostic explanations for anomalous deviations
FEATURE_EXPLANATIONS = {
    "typing_speed": "Typing speed differs significantly from baseline",
    "mean_hold_time": "Key hold duration differs significantly from baseline",
    "std_hold_time": "Key press hold consistency differs from baseline",
    "mean_flight_time": "Flight time between keystrokes differs from baseline",
    "std_flight_time": "Flight timing rhythm differs from baseline",
    "backspace_rate": "Backspace and correction behavior changed from baseline",
    "pause_mean": "Typing hesitation and pause behavior changed from baseline",
    "mouse_velocity_mean": "Mouse movement speed pattern differs from baseline",
    "click_interval_mean": "Mouse click rhythm differs from baseline"
}

MIN_REQUIRED_SAMPLES = 3
ANOMALY_THRESHOLD = 60.0  # Aligns with risk_engine HIGH risk threshold (>= 60)

# Fusion Weights
LOCAL_ML_WEIGHT = 0.70
TYPINGDNA_WEIGHT = 0.30


# =====================================================================
# Normalization & Fusion Helpers
# =====================================================================

def normalize_typingdna_score(typingdna_score: float) -> float:
    """
    Convert a TypingDNA similarity/authentication score (0-100, where 100 = match)
    into SentinelAI's anomaly scale (0-100, where 100 = severe anomaly).

    Formula:
        typingdna_anomaly = 100.0 - typingdna_score
    Clamped strictly between 0.0 and 100.0.
    """
    try:
        val = float(typingdna_score)
    except (ValueError, TypeError):
        val = 0.0

    clamped = max(0.0, min(100.0, val))
    return round(100.0 - clamped, 2)


def fuse_scores(
    local_anomaly_score: float,
    typingdna_score: Optional[float] = None,
    typingdna_error: Optional[str] = None
) -> Dict[str, Any]:
    """
    Combine SentinelAI local ML anomaly score with TypingDNA biometric score.

    Fusion Formula:
        combined_anomaly_score = 0.70 * local_anomaly_score + 0.30 * typingdna_anomaly

    Falls back cleanly to LOCAL_ONLY mode if TypingDNA is not provided or unavailable.
    """
    local_score = max(0.0, min(100.0, round(float(local_anomaly_score), 2)))

    if typingdna_score is not None:
        tdna_score_val = max(0.0, min(100.0, round(float(typingdna_score), 2)))
        tdna_anomaly = normalize_typingdna_score(tdna_score_val)
        combined = (LOCAL_ML_WEIGHT * local_score) + (TYPINGDNA_WEIGHT * tdna_anomaly)
        clamped_combined = max(0.0, min(100.0, round(combined, 2)))

        return {
            "local_anomaly_score": local_score,
            "typingdna_score": tdna_score_val,
            "typingdna_anomaly_score": tdna_anomaly,
            "combined_anomaly_score": clamped_combined,
            "fusion_mode": "ML_TYPINGDNA",
            "typingdna_available": True,
            "typingdna_error": None
        }

    return {
        "local_anomaly_score": local_score,
        "typingdna_score": None,
        "typingdna_anomaly_score": None,
        "combined_anomaly_score": local_score,
        "fusion_mode": "LOCAL_ONLY",
        "typingdna_available": False,
        "typingdna_error": typingdna_error
    }


def calculate_confidence(sample_count: int) -> float:
    """
    Compute model confidence based on verified sample count (N >= 3).
    With 3 enrollment samples, confidence starts conservatively at 0.65.
    Expands smoothly towards 0.95 as sample count increases via adaptive learning.
    """
    if sample_count < MIN_REQUIRED_SAMPLES:
        return 0.0

    delta = sample_count - MIN_REQUIRED_SAMPLES
    # Asymptotic growth: 0.65 base + up to 0.30 additional confidence
    growth = 1.0 - (1.0 / (1.0 + 0.1 * delta))
    confidence = 0.65 + (0.30 * growth)
    return round(min(0.95, confidence), 2)


def get_user_baseline_stats(user_id: int, db: Session) -> Optional[Dict[str, Dict[str, float]]]:
    """
    Calculate mean and standard deviation for each feature from the user's
    BehaviorProfile and actual enrollment BehaviorSample records.

    Returns:
        dict: { feature_name: {"mean": float, "std": float} } or None if incomplete.
    """
    profile = (
        db.query(BehaviorProfile)
        .filter(BehaviorProfile.user_id == user_id)
        .first()
    )

    if not profile or (profile.sample_count or 0) < MIN_REQUIRED_SAMPLES:
        return None

    # Retrieve individual enrollment samples to calculate empirical standard deviation
    samples = (
        db.query(BehaviorSample)
        .join(SessionModel, BehaviorSample.session_id == SessionModel.id)
        .filter(SessionModel.user_id == user_id)
        .filter(BehaviorSample.risk_level == "ENROLLMENT")
        .all()
    )

    stats = {}
    for field in FEATURE_FIELDS:
        profile_mean = getattr(profile, field)
        if profile_mean is None:
            profile_mean = 0.0

        # Calculate sample standard deviation from enrollment samples if available
        if samples and len(samples) >= 2:
            vals = [getattr(s, field, 0.0) or 0.0 for s in samples]
            sample_mean = sum(vals) / len(vals)
            variance = sum((v - sample_mean) ** 2 for v in vals) / len(vals)
            empirical_std = math.sqrt(variance)
        else:
            empirical_std = 0.0

        # Enforce domain-calibrated standard deviation floor
        floor = STD_FLOORS.get(field, 5.0)
        effective_std = max(empirical_std, floor)

        stats[field] = {
            "mean": float(profile_mean),
            "std": float(effective_std)
        }

    return stats


# =====================================================================
# Main Prediction Entrypoint
# =====================================================================

def predict(
    features: dict,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
    typing_pattern: Optional[str] = None
) -> Dict[str, Any]:
    """
    Perform personalized behavioral anomaly detection, optionally fused with TypingDNA.

    Args:
        features: Dictionary containing the 9 numerical behavioral features.
        user_id: The authenticated user's ID.
        db: Active SQLAlchemy database session.
        typing_pattern: Optional TypingDNA typing pattern string. When provided,
                        triggers multimodal fusion with TypingDNA /verify API.

    Returns:
        Dict containing anomaly_score, local_anomaly_score, typingdna_score,
        typingdna_anomaly_score, combined_anomaly_score, fusion_mode,
        is_anomaly, confidence, model_type, and top_anomalous_features.
    """
    # 1. Verify user context and enrollment completeness
    if user_id is None or db is None:
        logger.warning("predict() called without user_id or db context")
        return {
            "model_ready": False,
            "reason": "User ID and database session required for personalized prediction",
            "anomaly_score": 0.0,
            "local_anomaly_score": 0.0,
            "typingdna_score": None,
            "typingdna_anomaly_score": None,
            "combined_anomaly_score": 0.0,
            "fusion_mode": "LOCAL_ONLY",
            "typingdna_available": False,
            "typingdna_error": None,
            "is_anomaly": False,
            "confidence": 0.0,
            "model_type": "personalized_statistical",
            "top_anomalous_features": []
        }

    profile = (
        db.query(BehaviorProfile)
        .filter(BehaviorProfile.user_id == user_id)
        .first()
    )

    sample_count = profile.sample_count if profile and profile.sample_count else 0
    if sample_count < MIN_REQUIRED_SAMPLES:
        return {
            "model_ready": False,
            "reason": f"Personal enrollment incomplete ({sample_count}/{MIN_REQUIRED_SAMPLES} samples)",
            "anomaly_score": 0.0,
            "local_anomaly_score": 0.0,
            "typingdna_score": None,
            "typingdna_anomaly_score": None,
            "combined_anomaly_score": 0.0,
            "fusion_mode": "LOCAL_ONLY",
            "typingdna_available": False,
            "typingdna_error": None,
            "is_anomaly": False,
            "confidence": 0.0,
            "model_type": "personalized_statistical",
            "top_anomalous_features": []
        }

    # 2. Extract baseline statistics
    baseline_stats = get_user_baseline_stats(user_id=user_id, db=db)
    if not baseline_stats:
        return {
            "model_ready": False,
            "reason": "Failed to extract user baseline statistics",
            "anomaly_score": 0.0,
            "local_anomaly_score": 0.0,
            "typingdna_score": None,
            "typingdna_anomaly_score": None,
            "combined_anomaly_score": 0.0,
            "fusion_mode": "LOCAL_ONLY",
            "typingdna_available": False,
            "typingdna_error": None,
            "is_anomaly": False,
            "confidence": 0.0,
            "model_type": "personalized_statistical",
            "top_anomalous_features": []
        }

    # 3. Calculate feature-level z-scores and bounded contributions
    feature_contributions = []
    total_weighted_contribution = 0.0
    total_weights = 0.0

    for field in FEATURE_FIELDS:
        current_val = features.get(field, 0.0)
        if current_val is None or math.isnan(current_val) or math.isinf(current_val):
            current_val = 0.0

        personal_mean = baseline_stats[field]["mean"]
        personal_std = baseline_stats[field]["std"]

        # Z-score: distance from personal mean in units of personal standard deviation
        z = abs(current_val - personal_mean) / personal_std

        # Cap z-score at 4.0 to prevent a single extreme outlier from dominating
        z_capped = min(z, 4.0)

        # Normalize contribution to 0-100 range
        contribution = (z_capped / 4.0) * 100.0

        weight = FEATURE_WEIGHTS.get(field, 1.0)
        total_weighted_contribution += weight * contribution
        total_weights += weight

        feature_contributions.append({
            "feature": field,
            "deviation": round(z, 2),
            "contribution": round(contribution, 2),
            "explanation": FEATURE_EXPLANATIONS.get(field, "Behavior differs from baseline")
        })

    # 4. Compute aggregate local anomaly score (0 - 100)
    raw_local_score = total_weighted_contribution / total_weights if total_weights > 0 else 0.0
    final_local_score = max(0.0, min(100.0, round(raw_local_score, 2)))

    # 5. Extract top anomalous features (sorted by deviation descending)
    feature_contributions.sort(key=lambda x: x["deviation"], reverse=True)
    top_anomalous_features = feature_contributions[:3]

    # 6. Compute dynamic confidence
    confidence = calculate_confidence(sample_count)

    # 7. Multimodal Fusion with TypingDNA (if pattern provided)
    tdna_score = None
    tdna_error = None

    if typing_pattern and typing_pattern.strip():
        try:
            tdna_res = verify_pattern(user_id=user_id, typing_pattern=typing_pattern.strip())
            tdna_score = tdna_res.get("effective_score", tdna_res.get("score", 0.0))
        except TypingDNAError as e:
            tdna_error = e.message
            logger.warning("TypingDNA verification error for user_id=%s: %s", user_id, e.message)
        except Exception as e:
            tdna_error = str(e)
            logger.warning("Unexpected error communicating with TypingDNA for user_id=%s: %s", user_id, str(e))

    fusion = fuse_scores(
        local_anomaly_score=final_local_score,
        typingdna_score=tdna_score,
        typingdna_error=tdna_error
    )

    combined_score = fusion["combined_anomaly_score"]

    return {
        "model_ready": True,
        "local_anomaly_score": fusion["local_anomaly_score"],
        "anomaly_score": combined_score,  # backward compatibility alias
        "typingdna_score": fusion["typingdna_score"],
        "typingdna_anomaly_score": fusion["typingdna_anomaly_score"],
        "combined_anomaly_score": combined_score,
        "fusion_mode": fusion["fusion_mode"],
        "typingdna_available": fusion["typingdna_available"],
        "typingdna_error": fusion["typingdna_error"],
        "is_anomaly": bool(combined_score >= ANOMALY_THRESHOLD),
        "confidence": confidence,
        "model_type": "personalized_statistical",
        "top_anomalous_features": top_anomalous_features
    }