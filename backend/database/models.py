from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_name = Column(String, nullable=False)
    device_type = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class BehaviorProfile(Base):
    __tablename__ = "behavior_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)

    typing_speed = Column(Float, nullable=True)
    mean_hold_time = Column(Float, nullable=True)
    std_hold_time = Column(Float, nullable=True)
    mean_flight_time = Column(Float, nullable=True)
    std_flight_time = Column(Float, nullable=True)
    backspace_rate = Column(Float, nullable=True)
    pause_mean = Column(Float, nullable=True)
    mouse_velocity_mean = Column(Float, nullable=True)
    click_interval_mean = Column(Float, nullable=True)

    sample_count = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)

    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)
    status = Column(String, default="ACTIVE")


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)

    timestamp = Column(DateTime, server_default=func.now())

    risk_score = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False)
    action = Column(String, nullable=False)
    reason = Column(String, nullable=True)


class BehaviorSample(Base):
    __tablename__ = "behavior_samples"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(
        Integer,
        ForeignKey("sessions.id"),
        nullable=False
    )

    timestamp = Column(
        DateTime,
        server_default=func.now()
    )

    # Keyboard features
    typing_speed = Column(Float, nullable=True)
    mean_hold_time = Column(Float, nullable=True)
    std_hold_time = Column(Float, nullable=True)

    mean_flight_time = Column(Float, nullable=True)
    std_flight_time = Column(Float, nullable=True)

    backspace_rate = Column(Float, nullable=True)
    pause_mean = Column(Float, nullable=True)

    # Mouse features
    mouse_velocity_mean = Column(Float, nullable=True)
    click_interval_mean = Column(Float, nullable=True)

    # Result of the ML/risk analysis
    risk_score = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False)