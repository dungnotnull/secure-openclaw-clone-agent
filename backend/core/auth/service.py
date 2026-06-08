from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from backend.core.config import settings
from backend.core.models.user import User, UserSession

_ph = PasswordHasher(
    time_cost=settings.ARGON2_ITERATIONS,
    memory_cost=settings.ARGON2_MEMORY_KB,
    parallelism=settings.ARGON2_PARALLELISM,
)
_SESSIONS: dict[str, UserSession] = {}


class AuthService:
    """JWT + TOTP 2FA authentication.

    Session tokens are held in memory only — never written to disk.
    """

    # ------------------------------------------------------------------
    # user management
    # ------------------------------------------------------------------
    @staticmethod
    def hash_password(password: str) -> str:
        return _ph.hash(password)

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        try:
            return _ph.verify(password_hash, password)
        except VerifyMismatchError:
            return False

    @staticmethod
    def generate_totp_secret() -> str:
        return pyotp.random_base32()

    @staticmethod
    def verify_totp(secret: str, token: str) -> bool:
        return pyotp.TOTP(secret).verify(token)

    # ------------------------------------------------------------------
    # JWT
    # ------------------------------------------------------------------
    @staticmethod
    def create_access_token(user_id: str, expires_delta: int | None = None) -> str:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=expires_delta or settings.JWT_EXPIRY_MINUTES
        )
        payload = {"sub": user_id, "exp": expire, "iat": datetime.now(timezone.utc)}
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> Optional[str]:
        try:
            payload = jwt.decode(
                token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
            )
            return payload.get("sub")
        except JWTError:
            return None

    # ------------------------------------------------------------------
    # session (in-memory only)
    # ------------------------------------------------------------------
    @classmethod
    def create_session(cls, user_id: str, ip: str | None = None) -> UserSession:
        token = cls.create_access_token(user_id)
        session = UserSession(
            token=token,
            user_id=user_id,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=settings.JWT_EXPIRY_MINUTES),
            ip_address=ip,
        )
        _SESSIONS[token] = session
        return session

    @classmethod
    def validate_session(cls, token: str) -> Optional[UserSession]:
        session = _SESSIONS.get(token)
        if session is None:
            return None
        if session.expires_at < datetime.now(timezone.utc):
            _SESSIONS.pop(token, None)
            return None
        return session

    @classmethod
    def destroy_session(cls, token: str) -> None:
        _SESSIONS.pop(token, None)

    @classmethod
    def create_user_credentials(cls, password: str) -> tuple[bytes, str]:
        import os
        from backend.core.encryption import SecureStorage
        salt = os.urandom(settings.ARGON2_SALT_BYTES)
        key, _ = SecureStorage.derive_key(password, salt)
        totp_secret = cls.generate_totp_secret()
        return salt, totp_secret

    @staticmethod
    def get_totp_uri(user: User) -> str:
        if not user.totp_secret:
            return ""
        return pyotp.TOTP(user.totp_secret).provisioning_uri(
            name=user.username, issuer_name=settings.TOTP_ISSUER
        )
