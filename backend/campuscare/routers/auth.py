from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlmodel import Session, select

from campuscare.audit import log_event
from campuscare.config import ACCESS_MINUTES, COOKIE_NAME
from campuscare.database import get_session
from campuscare.models import LoginAttempt, RefreshSession, User
from campuscare.schemas import Login, Signup
from campuscare.security import account_is_suspended, current_user, hash_password, issue_refresh, make_access, verify_password
from campuscare.utils import client_ip, digest, now
from campuscare.validation import valid_email


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup", status_code=201)
def signup(payload: Signup, request: Request, session: Annotated[Session, Depends(get_session)]):
    email = valid_email(payload.email)
    if len(payload.password) < 8 or not any(c.isalpha() for c in payload.password) or not any(c.isdigit() for c in payload.password):
        raise HTTPException(422, "Password must contain at least 8 characters, one letter and one number")
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(409, "Email is already registered")
    user = User(email=email, full_name=payload.full_name.strip(), password_hash=hash_password(payload.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    log_event(session, request, "signup", user.id)
    session.commit()
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}


@router.post("/login")
def login(payload: Login, request: Request, response: Response, session: Annotated[Session, Depends(get_session)]):
    email = payload.email.strip().lower()
    ip = client_ip(request)
    cutoff = now() - timedelta(minutes=15)
    attempts = session.exec(select(LoginAttempt).where(LoginAttempt.email_key == email,
        LoginAttempt.ip_address == ip, LoginAttempt.created_at >= cutoff, LoginAttempt.succeeded == False)).all()
    if len(attempts) >= 8:
        raise HTTPException(429, "Too many failed login attempts. Try again in 15 minutes.")
    user = session.exec(select(User).where(User.email == email)).first()
    valid = bool(user and verify_password(payload.password, user.password_hash))
    session.add(LoginAttempt(email_key=email, ip_address=ip, succeeded=valid))
    if not valid or not user or user.is_banned or account_is_suspended(user):
        log_event(session, request, "failed_login", user.id if user else None, detail="Invalid credentials or unavailable account")
        session.commit()
        raise HTTPException(401, "Invalid email or password")
    log_event(session, request, "login", user.id)
    issue_refresh(session, user, request, response)
    session.commit()
    return {"access_token": make_access(user), "token_type": "bearer", "expires_in": ACCESS_MINUTES * 60,
            "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}}


@router.post("/refresh")
def refresh(request: Request, response: Response, session: Annotated[Session, Depends(get_session)]):
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        raise HTTPException(401, "Refresh session missing")
    old = session.exec(select(RefreshSession).where(RefreshSession.token_hash == digest(raw))).first()
    if not old or old.revoked_at or old.expires_at < now():
        if old and old.revoked_at:
            for token in session.exec(select(RefreshSession).where(RefreshSession.user_id == old.user_id, RefreshSession.revoked_at == None)).all():
                token.revoked_at = now()
        response.delete_cookie(COOKIE_NAME, path="/api/v1/auth")
        session.commit()
        raise HTTPException(401, "Refresh session expired or revoked")
    user = session.get(User, old.user_id)
    if not user or user.is_banned or account_is_suspended(user):
        raise HTTPException(401, "Account is unavailable")
    old.revoked_at = now()
    issue_refresh(session, user, request, response)
    session.commit()
    return {"access_token": make_access(user), "token_type": "bearer", "expires_in": ACCESS_MINUTES * 60}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, session: Annotated[Session, Depends(get_session)],
           user: Annotated[User, Depends(current_user)]):
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        token = session.exec(select(RefreshSession).where(RefreshSession.token_hash == digest(raw))).first()
        if token and token.user_id == user.id:
            token.revoked_at = now()
    user.token_version += 1
    session.add(user)
    log_event(session, request, "logout", user.id)
    session.commit()
    response.delete_cookie(COOKIE_NAME, path="/api/v1/auth")
    response.status_code = 204
    return response


@router.get("/sessions")
def list_sessions(user: Annotated[User, Depends(current_user)], session: Annotated[Session, Depends(get_session)]):
    rows = session.exec(select(RefreshSession).where(RefreshSession.user_id == user.id,
        RefreshSession.revoked_at == None, RefreshSession.expires_at > now())).all()
    return [{"id": r.id, "created_at": r.created_at, "expires_at": r.expires_at,
             "ip_address": r.ip_address, "user_agent": r.user_agent} for r in rows]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: int, user: Annotated[User, Depends(current_user)],
                   session: Annotated[Session, Depends(get_session)]):
    row = session.get(RefreshSession, session_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Session not found")
    row.revoked_at = now()
    user.token_version += 1
    session.add(user)
    session.commit()
    return Response(status_code=204)
