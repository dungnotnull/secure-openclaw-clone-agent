from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.auth.service import AuthService
from backend.core.config import settings
from backend.core.db.database import get_db
from backend.core.models.user import UserSession

logger = logging.getLogger(__name__)
security_scheme = HTTPBearer(auto_error=False)

_rate_limit_store: dict[str, list[float]] = defaultdict(list)


def rate_limiter(max_requests: int = 60, window_seconds: int = 60):
    async def _rate_limit(request: Request):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - window_seconds
        _rate_limit_store[client_ip] = [
            t for t in _rate_limit_store[client_ip] if t > window_start
        ]
        if len(_rate_limit_store[client_ip]) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {max_requests} requests per {window_seconds}s",
            )
        _rate_limit_store[client_ip].append(now)
    return _rate_limit


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    session = AuthService.validate_session(token)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return session.user_id


async def audit_logger(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    logger.info(
        "AUDIT method=%s path=%s status=%d duration_ms=%.1f client=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request.client.host if request.client else "-",
    )
    return response
