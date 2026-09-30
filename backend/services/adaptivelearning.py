from sqlalchemy.orm import Session

from backend.database.models import BehaviorProfile


LEARNING_CONFIDENCE_THRESHOLD = 0.80


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


def update_behavior_profile(
    db: Session,
    user_id: int,
    device_id: int | None,
    features: dict,
    risk_level: str,
    confidence: float
):
    """
    Update the user's behavioral profile only when
    the current behavior is considered trustworthy.
    """

    # Never learn from suspicious behavior
    if risk_level != "LOW":
        return {
            "updated": False,
            "reason": "Risk level is not LOW"
        }

    # Never learn from uncertain predictions
    if confidence < LEARNING_CONFIDENCE_THRESHOLD:
        return {
            "updated": False,
            "reason": "Confidence is too low"
        }

    profile = (
        db.query(BehaviorProfile)
        .filter(
            BehaviorProfile.user_id == user_id,
            BehaviorProfile.device_id == device_id
        )
        .first()
    )

    # --------------------------------
    # Create first behavioral profile
    # --------------------------------

    if profile is None:

        profile = BehaviorProfile(
            user_id=user_id,
            device_id=device_id,
            sample_count=1
        )

        for field in FEATURE_FIELDS:
            setattr(
                profile,
                field,
                features.get(field, 0)
            )

        db.add(profile)

        return {
            "updated": True,
            "reason": "Initial behavioral profile created"
        }

    # --------------------------------
    # Incremental weighted average
    # --------------------------------

    old_count = profile.sample_count or 0
    new_count = old_count + 1

    for field in FEATURE_FIELDS:

        old_value = getattr(profile, field) or 0
        new_value = features.get(field, 0)

        updated_value = (
            (old_value * old_count) + new_value
        ) / new_count

        setattr(
            profile,
            field,
            updated_value
        )

    profile.sample_count = new_count

    return {
        "updated": True,
        "reason": "Behavioral profile updated",
        "sample_count": new_count
    }