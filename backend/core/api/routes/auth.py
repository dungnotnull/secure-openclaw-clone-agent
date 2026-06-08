from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.core.auth.service import AuthService
from backend.core.db.database import get_db
from backend.core.middleware.security import rate_limiter

router = APIRouter(tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TOTPSetupRequest(BaseModel):
    token: str


class TOTPVerifyRequest(BaseModel):
    session_token: str
    totp_code: str


class AuthResponse(BaseModel):
    token: str
    totp_required: bool = False
    totp_setup_url: str | None = None


@router.post("/auth/register", response_model=AuthResponse)
async def register(body: RegisterRequest, _: None = Depends(rate_limiter(10, 300))):
    db = get_db()
    existing = db.get_user_by_username(body.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    password_hash = AuthService.hash_password(body.password)
    salt, totp_secret = AuthService.create_user_credentials(body.password)
    from backend.core.models.user import User
    user = User(
        username=body.username,
        password_hash=password_hash,
        salt=salt,
        totp_secret=totp_secret,
    )
    db.create_user(user)

    session = AuthService.create_session(user.id)
    return AuthResponse(
        token=session.token,
        totp_required=False,
        totp_setup_url=AuthService.get_totp_uri(user) if totp_secret else None,
    )


@router.post("/auth/login", response_model=AuthResponse)
async def login(body: LoginRequest, _: None = Depends(rate_limiter(20, 60))):
    db = get_db()
    user = db.get_user_by_username(body.username)
    if user is None or not AuthService.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    totp_required = user.totp_enabled
    session = AuthService.create_session(user.id)

    return AuthResponse(
        token=session.token if not totp_required else "",
        totp_required=totp_required,
    )


@router.post("/auth/login/totp", response_model=AuthResponse)
async def login_with_totp(body: TOTPVerifyRequest):
    db = get_db()
    session = AuthService.validate_session(body.session_token)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid session")

    user = db.get_user_by_id(session.user_id)
    if user is None or not user.totp_secret:
        raise HTTPException(status_code=401, detail="TOTP not configured")

    if not AuthService.verify_totp(user.totp_secret, body.totp_code):
        raise HTTPException(status_code=401, detail="Invalid TOTP code")

    final_session = AuthService.create_session(user.id)
    AuthService.destroy_session(body.session_token)
    return AuthResponse(token=final_session.token, totp_required=False)


@router.post("/auth/logout")
async def logout(token: str):
    AuthService.destroy_session(token)
    return {"status": "logged_out"}


@router.post("/auth/2fa/setup")
async def setup_2fa(body: TOTPSetupRequest):
    user_id = AuthService.decode_token(body.token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    db = get_db()
    user = db.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "totp_setup_url": AuthService.get_totp_uri(user),
        "totp_enabled": user.totp_enabled,
    }


@router.post("/auth/2fa/enable")
async def enable_2fa(body: TOTPVerifyRequest):
    user_id = AuthService.decode_token(body.session_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    db = get_db()
    user = db.get_user_by_id(user_id)
    if user is None or not user.totp_secret:
        raise HTTPException(status_code=404, detail="User or TOTP secret not found")
    if not AuthService.verify_totp(user.totp_secret, body.totp_code):
        raise HTTPException(status_code=401, detail="Invalid TOTP code")
    user.totp_enabled = True
    from backend.core.db.database import Database
    db.conn.execute(
        "UPDATE users SET totp_enabled=1 WHERE id=?", (user.id,)
    )
    db.commit()
    return {"status": "2fa_enabled"}
