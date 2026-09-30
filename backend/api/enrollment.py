import logging
import math
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.database.models import (
    User,
    BehaviorProfile,
    BehaviorSample,
    Session as SessionModel
)
from backend.security.auth import get_current_user
from backend.services.typingdna import save_pattern, TypingDNAError, TypingDNAConfigError

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/enrollment",
    tags=["Enrollment"]
)

REQUIRED_ENROLLMENT_SAMPLES = 3

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


# =====================================================================
# Request / Response Schemas
# =====================================================================

class BehavioralFeatures(BaseModel):
    typing_speed: float
    mean_hold_time: float
    std_hold_time: float
    mean_flight_time: float
    std_flight_time: float
    backspace_rate: float
    pause_mean: float
    mouse_velocity_mean: float
    click_interval_mean: float


class EnrollmentSubmitRequest(BaseModel):
    features: BehavioralFeatures
    typing_pattern: str

    @field_validator("typing_pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("typing_pattern must be a non-empty string")
        return v.strip()

    @model_validator(mode="after")
    def validate_features_payload(self):
        feat_dict = self.features.model_dump()
        for k, v in feat_dict.items():
            if v is None:
                raise ValueError(f"Feature '{k}' cannot be None")
            if math.isnan(v) or math.isinf(v):
                raise ValueError(f"Feature '{k}' must be a finite number, received {v}")
            if v < 0:
                raise ValueError(f"Feature '{k}' cannot be negative")
        return self


# =====================================================================
# Endpoints
# =====================================================================

@router.get("/status")
def get_enrollment_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the enrollment progress and status for the authenticated user.
    """
    profile = (
        db.query(BehaviorProfile)
        .filter(BehaviorProfile.user_id == current_user.id)
        .first()
    )

    samples_collected = profile.sample_count if profile and profile.sample_count else 0
    is_enrolled = samples_collected >= REQUIRED_ENROLLMENT_SAMPLES

    return {
        "is_enrolled": is_enrolled,
        "samples_collected": samples_collected,
        "required_samples": REQUIRED_ENROLLMENT_SAMPLES
    }


@router.post("/submit")
def submit_enrollment_sample(
    data: EnrollmentSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit an enrollment sample (both keystroke features and TypingDNA pattern).
    Requires exactly 3 successful samples to complete enrollment.
    """
    # 1. Check existing enrollment state
    profile = (
        db.query(BehaviorProfile)
        .filter(BehaviorProfile.user_id == current_user.id)
        .first()
    )

    current_count = profile.sample_count if profile and profile.sample_count else 0
    if current_count >= REQUIRED_ENROLLMENT_SAMPLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User has already completed enrollment ({current_count}/{REQUIRED_ENROLLMENT_SAMPLES} samples recorded). Re-enrollment is not permitted."
        )

    # 2. Extract features dictionary
    features_dict = data.features.model_dump()

    # Explicit check for any non-finite numbers
    for name, val in features_dict.items():
        if val is None or math.isnan(val) or math.isinf(val):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid feature '{name}': must be a finite number"
            )

    # 3. Call TypingDNA save_pattern
    try:
        tdna_result = save_pattern(current_user.id, data.typing_pattern)
    except TypingDNAConfigError as e:
        logger.warning(
            "TypingDNA credentials not configured; continuing with local behavioral baseline enrollment for user_id=%s: %s",
            current_user.id, e.message
        )
    except TypingDNAError as e:
        logger.error("TypingDNA save_pattern failed for user_id=%s: %s", current_user.id, e.message)
        raise HTTPException(
            status_code=e.status_code if e.status_code != 500 else status.HTTP_502_BAD_GATEWAY,
            detail=f"TypingDNA enrollment error: {e.message}"
        )
    except Exception as e:
        logger.error("Unexpected error contacting TypingDNA for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to contact TypingDNA enrollment service"
        )

    # 4. Local persistence: Record BehaviorSample and update BehaviorProfile
    try:
        # Find or create active enrollment session
        enrollment_session = (
            db.query(SessionModel)
            .filter(
                SessionModel.user_id == current_user.id,
                SessionModel.status == "ENROLLMENT"
            )
            .first()
        )
        if not enrollment_session:
            enrollment_session = SessionModel(
                user_id=current_user.id,
                status="ENROLLMENT"
            )
            db.add(enrollment_session)
            db.flush()

        # Record individual BehaviorSample
        sample = BehaviorSample(
            session_id=enrollment_session.id,
            typing_speed=features_dict["typing_speed"],
            mean_hold_time=features_dict["mean_hold_time"],
            std_hold_time=features_dict["std_hold_time"],
            mean_flight_time=features_dict["mean_flight_time"],
            std_flight_time=features_dict["std_flight_time"],
            backspace_rate=features_dict["backspace_rate"],
            pause_mean=features_dict["pause_mean"],
            mouse_velocity_mean=features_dict["mouse_velocity_mean"],
            click_interval_mean=features_dict["click_interval_mean"],
            risk_score=0.0,
            risk_level="ENROLLMENT"
        )
        db.add(sample)

        # Update or create BehaviorProfile
        if profile is None:
            profile = BehaviorProfile(
                user_id=current_user.id,
                sample_count=1
            )
            for field in FEATURE_FIELDS:
                setattr(profile, field, features_dict[field])
            db.add(profile)
            new_sample_count = 1
        else:
            old_count = profile.sample_count or 0
            new_sample_count = old_count + 1
            for field in FEATURE_FIELDS:
                old_val = getattr(profile, field) or 0.0
                new_val = features_dict[field]
                updated_val = ((old_val * old_count) + new_val) / new_sample_count
                setattr(profile, field, updated_val)
            profile.sample_count = new_sample_count
            profile.updated_at = datetime.now(timezone.utc)

        # Finalize enrollment session once required sample count is reached
        if new_sample_count >= REQUIRED_ENROLLMENT_SAMPLES:
            enrollment_session.status = "COMPLETED"
            enrollment_session.ended_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(profile)
    except Exception as db_err:
        db.rollback()
        logger.error("Failed to persist local enrollment sample for user_id=%s: %s", current_user.id, str(db_err))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist local behavioral baseline"
        )

    # 5. Build standardized response
    is_enrolled = new_sample_count >= REQUIRED_ENROLLMENT_SAMPLES
    message = "Enrollment completed" if is_enrolled else "Enrollment sample recorded"

    return {
        "message": message,
        "samples_collected": new_sample_count,
        "required_samples": REQUIRED_ENROLLMENT_SAMPLES,
        "is_enrolled": is_enrolled
    }
