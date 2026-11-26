from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlmodel import Session

from campuscare.config import ACCESS_MINUTES, COOKIE_NAME, COOKIE_SECURE, JWT_SECRET, PASSWORD_PEPPER, REFRESH_DAYS
from campuscare.database import get_session
from campuscare.models import RefreshSession, User
from campuscare.utils import client_ip, digest, now


password_hasher = PasswordHash.recommended()


bearer = HTTPBearer(auto_error=False)


def password_input(password: str) -> str:
    return hmac.new(PASSWORD_PEPPER.encode(), password.encode(), hashlib.sha256).hexdigest()


def hash_password(password: str) -> str:
    return password_hasher.hash(password_input(password))


def verify_password(password: str, hashed: str) -> bool:
    return password_hasher.verify(password_input(password), hashed)


# Central role-to-permission policy used by every protected route.
ROLE_PERMISSIONS = {
    "user": frozenset({"profile:manage", "complaint:create", "complaint:read:own",
                       "complaint:update:own", "complaint:delete:own", "group:collaborate"}),
    "admin": frozenset({"profile:manage", "admin:access", "complaint:read:all",
                        "complaint:delete:any", "complaint:status", "user:read", "user:manage",
                        "user:role", "stats:read", "audit:read", "security:read",
                        "content:moderate", "export:read"}),
}


def make_access(user: User) -> str:
    issued = now()
    return jwt.encode({"sub": str(user.id), "role": user.role, "iat": issued,
                       "exp": issued + timedelta(minutes=ACCESS_MINUTES),
                       "jti": secrets.token_hex(12), "ver": user.token_version}, JWT_SECRET, algorithm="HS256")


def issue_refresh(session: Session, user: User, request: Request, response: Response) -> None:
    raw = secrets.token_urlsafe(48)
    row = RefreshSession(user_id=user.id, token_hash=digest(raw),
                         expires_at=now() + timedelta(days=REFRESH_DAYS),
                         ip_address=client_ip(request),
                         user_agent=request.headers.get("user-agent"))
    session.add(row)
    response.set_cookie(COOKIE_NAME, raw, httponly=True, secure=COOKIE_SECURE,
                        samesite="lax", path="/api/v1/auth", max_age=REFRESH_DAYS * 86400)


def account_is_suspended(user: User) -> bool:
    deadline = user.suspended_until
    if deadline is None:
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline > now()


def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
                 session: Annotated[Session, Depends(get_session)]) -> User:
    if not credentials:
        raise HTTPException(401, "Authentication required")
    try:
        claims = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Invalid or expired access token")
    user = session.get(User, user_id)
    if not user or user.is_banned or claims.get("ver", 0) != user.token_version:
        raise HTTPException(401, "Session is not valid")
    if account_is_suspended(user):
        raise HTTPException(403, f"Account suspended until {user.suspended_until.isoformat()}")
    return user


def require_permission(permission: str):
    def dependency(user: Annotated[User, Depends(current_user)]) -> User:
        if permission not in ROLE_PERMISSIONS.get(user.role, frozenset()):
            raise HTTPException(403, "Insufficient permissions")
        return user
    return dependency
