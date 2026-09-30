from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.database.models import (
    Session as SessionModel,
    RiskEvent,
    BehaviorSample,
    User
)

from backend.security.auth import get_current_user
from backend.services.ml import predict
from backend.services.risk_engine import calculate_risk
from backend.services.adaptivelearning import update_behavior_profile


router = APIRouter(
    prefix="/verification",
    tags=["Verification"]
)


# ============================================================
# START VERIFICATION
# ============================================================

class StartVerificationRequest(BaseModel):
    user_id: int | None = None
    device_id: int | None = None


@router.post("/start")
def start_verification(
    data: StartVerificationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    new_session = SessionModel(
        user_id=current_user.id,
        device_id=data.device_id,
        status="ACTIVE"
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return {
        "message": "Verification session started",
        "session_id": new_session.id,
        "user_id": new_session.user_id,
        "status": new_session.status
    }


# ============================================================
# BEHAVIORAL FEATURES
# ============================================================

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


class FeatureRequest(BaseModel):

    session_id: int

    features: BehavioralFeatures

    typing_pattern: str | None = None


@router.post("/features")
def process_features(
    data: FeatureRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # --------------------------------------------------------
    # 1. Find session
    # --------------------------------------------------------

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == data.session_id
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Verification session not found"
        )

    # --------------------------------------------------------
    # Verify session ownership
    # --------------------------------------------------------
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Session does not belong to the authenticated user"
        )

    # --------------------------------------------------------
    # 2. Check session status
    # --------------------------------------------------------

    if session.status != "ACTIVE":
        raise HTTPException(
            status_code=400,
            detail="Verification session is not active"
        )


    # --------------------------------------------------------
    # 3. Convert Pydantic object to dictionary
    # --------------------------------------------------------

    features = data.features.model_dump()


    # --------------------------------------------------------
    # 4. ML prediction
    # --------------------------------------------------------

    prediction = predict(
        features=features,
        user_id=session.user_id,
        db=db,
        typing_pattern=data.typing_pattern
    )

    if not prediction.get("model_ready", True):
        return {
            "session_id": data.session_id,
            "model_ready": False,
            "message": prediction.get("reason", "Personal enrollment incomplete"),
            "risk_score": 0.0,
            "risk_level": "PENDING_ENROLLMENT",
            "action": "ENROLLMENT_REQUIRED",
            "confidence": 0.0
        }


    # --------------------------------------------------------
    # 5. Calculate risk
    # --------------------------------------------------------

    risk = calculate_risk(
        prediction["combined_anomaly_score"]
    )
    if risk["risk_level"] == "CRITICAL":
        session.status = "LOCKED"

    # --------------------------------------------------------
    # 6. Adaptive learning
    # --------------------------------------------------------

    if prediction.get("typingdna_error"):
        learning_result = {
            "updated": False,
            "reason": "Adaptive learning suspended during biometric verification error"
        }
    else:
        learning_result = update_behavior_profile(
            db=db,
            user_id=session.user_id,
            device_id=session.device_id,
            features=features,
            risk_level=risk["risk_level"],
            confidence=prediction["confidence"]
        )


    # --------------------------------------------------------
    # 7. Store behavioral sample
    # --------------------------------------------------------

    sample = BehaviorSample(

        session_id=data.session_id,

        typing_speed=features["typing_speed"],

        mean_hold_time=features["mean_hold_time"],
        std_hold_time=features["std_hold_time"],

        mean_flight_time=features["mean_flight_time"],
        std_flight_time=features["std_flight_time"],

        backspace_rate=features["backspace_rate"],
        pause_mean=features["pause_mean"],

        mouse_velocity_mean=features[
            "mouse_velocity_mean"
        ],

        click_interval_mean=features[
            "click_interval_mean"
        ],

        risk_score=risk["risk_score"],
        risk_level=risk["risk_level"]
    )

    db.add(sample)


    # --------------------------------------------------------
    # 8. Store risk event
    # --------------------------------------------------------

    risk_event = RiskEvent(

        session_id=data.session_id,

        risk_score=risk["risk_score"],

        risk_level=risk["risk_level"],

        action=risk["action"],

        reason=f"Behavioral analysis ({prediction.get('fusion_mode', 'LOCAL_ONLY')})"
    )

    db.add(risk_event)


    # --------------------------------------------------------
    # 9. Commit everything
    # --------------------------------------------------------

    db.commit()

    db.refresh(sample)
    db.refresh(risk_event)


    # --------------------------------------------------------
    # 10. Return result
    # --------------------------------------------------------

    return {

        "session_id": data.session_id,

        "sample_id": sample.id,

        "risk_score": risk["risk_score"],

        "risk_level": risk["risk_level"],

        "action": risk["action"],

        "confidence": prediction["confidence"],

        "local_anomaly_score": prediction.get("local_anomaly_score"),

        "typingdna_score": prediction.get("typingdna_score"),

        "typingdna_anomaly_score": prediction.get("typingdna_anomaly_score"),

        "combined_anomaly_score": prediction.get("combined_anomaly_score"),

        "fusion_mode": prediction.get("fusion_mode"),

        "typingdna_available": prediction.get("typingdna_available"),

        "typingdna_error": prediction.get("typingdna_error"),

        "top_anomalous_features": prediction.get("top_anomalous_features", []),

        "learning": learning_result,

        "timestamp": sample.timestamp
    }


# ============================================================
# CHECKPOINT VERIFICATION (Explicit Multimodal Fusion)
# ============================================================

class CheckpointRequest(BaseModel):
    session_id: int
    features: BehavioralFeatures
    typing_pattern: str


@router.post("/checkpoint")
def verify_checkpoint(
    data: CheckpointRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Explicit authentication/checkpoint biometric verification.
    Combines local behavioral ML with TypingDNA verification.
    """
    session = (
        db.query(SessionModel)
        .filter(SessionModel.id == data.session_id)
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Verification session not found"
        )

    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Session does not belong to the authenticated user"
        )

    features = data.features.model_dump()

    prediction = predict(
        features=features,
        user_id=session.user_id,
        db=db,
        typing_pattern=data.typing_pattern
    )

    if not prediction.get("model_ready", True):
        return {
            "session_id": data.session_id,
            "model_ready": False,
            "message": prediction.get("reason", "Personal enrollment incomplete"),
            "risk_score": 0.0,
            "risk_level": "PENDING_ENROLLMENT",
            "action": "ENROLLMENT_REQUIRED",
            "confidence": 0.0
        }

    risk = calculate_risk(
        prediction["combined_anomaly_score"]
    )

    # If the session was locked and checkpoint passes (LOW or MEDIUM), restore session to ACTIVE
    if session.status == "LOCKED" and risk["risk_level"] in ["LOW", "MEDIUM"]:
        session.status = "ACTIVE"
    elif risk["risk_level"] == "CRITICAL":
        session.status = "LOCKED"

    if prediction.get("typingdna_error"):
        learning_result = {
            "updated": False,
            "reason": "Adaptive learning suspended during biometric verification error"
        }
    else:
        learning_result = update_behavior_profile(
            db=db,
            user_id=session.user_id,
            device_id=session.device_id,
            features=features,
            risk_level=risk["risk_level"],
            confidence=prediction["confidence"]
        )

    sample = BehaviorSample(
        session_id=data.session_id,
        typing_speed=features["typing_speed"],
        mean_hold_time=features["mean_hold_time"],
        std_hold_time=features["std_hold_time"],
        mean_flight_time=features["mean_flight_time"],
        std_flight_time=features["std_flight_time"],
        backspace_rate=features["backspace_rate"],
        pause_mean=features["pause_mean"],
        mouse_velocity_mean=features["mouse_velocity_mean"],
        click_interval_mean=features["click_interval_mean"],
        risk_score=risk["risk_score"],
        risk_level=risk["risk_level"]
    )
    db.add(sample)

    risk_event = RiskEvent(
        session_id=data.session_id,
        risk_score=risk["risk_score"],
        risk_level=risk["risk_level"],
        action=risk["action"],
        reason=f"Checkpoint biometric verification ({prediction['fusion_mode']})"
    )
    db.add(risk_event)

    db.commit()
    db.refresh(sample)
    db.refresh(risk_event)

    return {
        "session_id": data.session_id,
        "sample_id": sample.id,
        "risk_score": risk["risk_score"],
        "risk_level": risk["risk_level"],
        "action": risk["action"],
        "confidence": prediction["confidence"],
        "local_anomaly_score": prediction["local_anomaly_score"],
        "typingdna_score": prediction["typingdna_score"],
        "typingdna_anomaly_score": prediction["typingdna_anomaly_score"],
        "combined_anomaly_score": prediction["combined_anomaly_score"],
        "fusion_mode": prediction["fusion_mode"],
        "typingdna_available": prediction["typingdna_available"],
        "typingdna_error": prediction.get("typingdna_error"),
        "top_anomalous_features": prediction.get("top_anomalous_features", []),
        "learning": learning_result,
        "session_status": session.status,
        "timestamp": sample.timestamp
    }


# ============================================================
# SESSION STATUS
# ============================================================

@router.get("/{session_id}/status")
def get_session_status(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id
        )
        .first()
    )

    if not session:

        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Session does not belong to the authenticated user"
        )

    latest_event = (
        db.query(RiskEvent)
        .filter(
            RiskEvent.session_id == session_id
        )
        .order_by(
            RiskEvent.timestamp.desc()
        )
        .first()
    )


    if latest_event:

        return {

            "session_id": session.id,

            "status": session.status,

            "risk_score":
                latest_event.risk_score,

            "risk_level":
                latest_event.risk_level,

            "action":
                latest_event.action
        }


    return {

        "session_id": session.id,

        "status": session.status,

        "risk_score": 0,

        "risk_level": "UNKNOWN",

        "action": "WAITING_FOR_DATA"
    }


# ============================================================
# END SESSION
# ============================================================

@router.post("/{session_id}/end")
def end_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id
        )
        .first()
    )

    if not session:

        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Session does not belong to the authenticated user"
        )

    session.status = "ENDED"

    session.ended_at = datetime.utcnow()

    db.commit()

    return {

        "message":
            "Verification session ended",

        "session_id":
            session_id,

        "status":
            session.status
    }

@router.get("/{session_id}/action")
def get_session_action(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session = (
        db.query(SessionModel)
        .filter(SessionModel.id == session_id)
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Session does not belong to the authenticated user"
        )

    latest_event = (
        db.query(RiskEvent)
        .filter(RiskEvent.session_id == session_id)
        .order_by(RiskEvent.timestamp.desc())
        .first()
    )

    if not latest_event:
        return {
            "session_id": session_id,
            "action": "WAITING",
            "risk_level": "UNKNOWN"
        }

    return {
        "session_id": session_id,
        "action": latest_event.action,
        "risk_level": latest_event.risk_level,
        "risk_score": latest_event.risk_score,
        "session_status": session.status
    }