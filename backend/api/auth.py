from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.database.models import User
from backend.security.auth import hash_password, verify_password, create_access_token


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/register")
def register(
    user_data: RegisterRequest,
    db: Session = Depends(get_db)
):
    existing_user = (
        db.query(User)
        .filter(User.email == user_data.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    new_user = User(
        name=user_data.name,
        email=user_data.email,
        password_hash=hash_password(user_data.password)
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "User registered successfully",
        "user_id": new_user.id,
        "name": new_user.name,
        "email": new_user.email
    }


@router.post("/login")
def login(
    user_data: LoginRequest,
    db: Session = Depends(get_db)
):
    user = (
        db.query(User)
        .filter(User.email == user_data.email)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if not verify_password(
        user_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # Establish authenticated identity via JWT token
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )

    return {
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "name": user.name,
        "email": user.email
    }


class ReauthRequest(BaseModel):
    session_id: int
    email: EmailStr
    password: str


@router.post("/reauthenticate")
def reauthenticate(
    data: ReauthRequest,
    db: Session = Depends(get_db)
):
    from backend.database.models import Session as SessionModel

    session = (
        db.query(SessionModel)
        .filter(SessionModel.id == data.session_id)
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    # Allow re-authentication for ACTIVE or legitimately LOCKED sessions
    if session.status not in ["ACTIVE", "LOCKED"]:
        raise HTTPException(
            status_code=400,
            detail="Session cannot be re-authenticated"
        )

    user = (
        db.query(User)
        .filter(User.email == data.email)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    if not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    # Verify session ownership
    if session.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Session does not belong to this user"
        )

    # If the session was locked, restore to ACTIVE after successful credential verification
    if session.status == "LOCKED":
        session.status = "ACTIVE"
        db.commit()
        db.refresh(session)

    return {
        "message": "Re-authentication successful",
        "session_id": session.id,
        "user_id": user.id,
        "status": "VERIFIED"
    }