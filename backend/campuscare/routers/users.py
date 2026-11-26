from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func
from sqlmodel import Session, select

from campuscare.audit import log_event
from campuscare.config import COOKIE_NAME
from campuscare.database import get_session
from campuscare.models import Complaint, RefreshSession, User
from campuscare.schemas import PasswordChange, ProfileUpdate
from campuscare.security import current_user, hash_password, verify_password
from campuscare.utils import now
from campuscare.validation import valid_email


router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me")
def get_profile(user: Annotated[User, Depends(current_user)]):
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role,
            "created_at": user.created_at}


@router.patch("/me")
def update_profile(payload: ProfileUpdate, request: Request, user: Annotated[User, Depends(current_user)],
                   session: Annotated[Session, Depends(get_session)]):
    email = valid_email(payload.email)
    existing = session.exec(select(User).where(User.email == email, User.id != user.id)).first()
    if existing:
        raise HTTPException(409, "Email already in use")
    user.email, user.full_name, user.updated_at = email, payload.full_name.strip(), now()
    session.add(user)
    log_event(session, request, "profile_update", user.id)
    session.commit()
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}


@router.post("/me/password", status_code=204)
def change_password(payload: PasswordChange, request: Request, response: Response,
                    user: Annotated[User, Depends(current_user)], session: Annotated[Session, Depends(get_session)]):
    if not verify_password(payload.current_password, user.password_hash):
        log_event(session, request, "failed_password_change", user.id)
        session.commit()
        raise HTTPException(400, "Current password is incorrect")
    if len(payload.new_password) < 8 or not any(c.isalpha() for c in payload.new_password) or not any(c.isdigit() for c in payload.new_password):
        raise HTTPException(422, "New password must contain a letter and a number")
    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1
    session.add(user)
    for token in session.exec(select(RefreshSession).where(RefreshSession.user_id == user.id, RefreshSession.revoked_at == None)).all():
        token.revoked_at = now()
    log_event(session, request, "password_change", user.id)
    session.commit()
    response.delete_cookie(COOKIE_NAME, path="/api/v1/auth")
    return Response(status_code=204)


@router.get("/me/dashboard")
def user_dashboard(user: Annotated[User, Depends(current_user)], session: Annotated[Session, Depends(get_session)]):
    rows = session.exec(select(Complaint.status, func.count()).where(Complaint.owner_id == user.id).group_by(Complaint.status)).all()
    return {"user": {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role},
            "complaints": {s: n for s, n in rows}}
