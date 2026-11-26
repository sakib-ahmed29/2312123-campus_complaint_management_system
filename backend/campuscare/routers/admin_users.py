from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session, select

from campuscare.audit import log_event
from campuscare.database import get_session
from campuscare.models import AuditEvent, Complaint, Group, GroupMember, RefreshSession, User
from campuscare.schemas import BanRequest, RoleChange, SuspendRequest, UnbanRequest
from campuscare.security import account_is_suspended, require_permission
from campuscare.serializers import audit_out, complaint_out, group_out
from campuscare.utils import now


router = APIRouter(prefix="/api/v1/admin", tags=["admin: users"])


@router.get("/users")
def admin_users(admin: Annotated[User, Depends(require_permission("admin:access"))],
                session: Annotated[Session, Depends(get_session)], q: str = "", role: str | None = None,
                status: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    statement = select(User)
    if q:
        statement = statement.where(User.email.contains(q.lower()) | User.full_name.contains(q))
    if role in ("user", "admin"):
        statement = statement.where(User.role == role)
    if status == "banned":
        statement = statement.where(User.is_banned == True)
    elif status == "suspended":
        statement = statement.where(User.is_banned == False, User.suspended_until > now())
    elif status == "active":
        statement = statement.where(User.is_banned == False).where((User.suspended_until == None) | (User.suspended_until <= now()))
    rows = session.exec(statement.order_by(User.created_at.desc()).offset(offset).limit(limit)).all()
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role,
             "is_banned": u.is_banned, "ban_reason": u.ban_reason,
             "suspended_until": u.suspended_until, "suspension_reason": u.suspension_reason,
             "status": "banned" if u.is_banned else ("suspended" if account_is_suspended(u) else "active"),
             "created_at": u.created_at} for u in rows]


@router.get("/users/{user_id}")
def admin_user_detail(user_id: int, admin: Annotated[User, Depends(require_permission("admin:access"))],
                      session: Annotated[Session, Depends(get_session)]):
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    complaints = session.exec(select(Complaint).where(Complaint.owner_id == user_id)).all()
    groups = session.exec(select(Group).join(GroupMember, Group.id == GroupMember.group_id).where(GroupMember.user_id == user_id)).all()
    sessions = session.exec(select(RefreshSession).where(RefreshSession.user_id == user_id)).all()
    activity = session.exec(select(AuditEvent).where(AuditEvent.user_id == user_id).order_by(AuditEvent.created_at.desc()).limit(30)).all()
    return {"user": {"id": target.id, "email": target.email, "full_name": target.full_name, "role": target.role,
                     "is_banned": target.is_banned, "ban_reason": target.ban_reason,
                     "created_at": target.created_at},
            "complaints": [complaint_out(x) for x in complaints],
            "groups": [group_out(x) for x in groups],
            "sessions": [{"id": x.id, "created_at": x.created_at, "expires_at": x.expires_at, "revoked_at": x.revoked_at,
                          "ip_address": x.ip_address, "user_agent": x.user_agent} for x in sessions],
            "activity": [audit_out(x) for x in activity]}


@router.patch("/users/{user_id}/role")
def admin_change_role(user_id: int, payload: RoleChange, request: Request,
                      admin: Annotated[User, Depends(require_permission("admin:access"))], session: Annotated[Session, Depends(get_session)]):
    if payload.role not in ("user", "admin"):
        raise HTTPException(422, "Role must be user or admin")
    if user_id == admin.id:
        raise HTTPException(400, "Administrators cannot change their own role")
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.role == "admin":
        raise HTTPException(403, "An administrator cannot change another administrator's role")
    target.role = payload.role
    target.token_version += 1
    log_event(session, request, "role_change", admin.id, "user", str(user_id), payload.role)
    session.commit()
    return {"id": target.id, "role": target.role}


@router.post("/users/{user_id}/ban")
def admin_ban_user(user_id: int, payload: BanRequest, request: Request,
                   admin: Annotated[User, Depends(require_permission("admin:access"))], session: Annotated[Session, Depends(get_session)]):
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == admin.id or target.role == "admin":
        raise HTTPException(403, "Admins cannot ban themselves or another admin")
    target.is_banned, target.ban_reason = True, payload.reason
    target.token_version += 1
    for token in session.exec(select(RefreshSession).where(RefreshSession.user_id == user_id, RefreshSession.revoked_at == None)).all():
        token.revoked_at = now()
    log_event(session, request, "user_banned", admin.id, "user", str(user_id), payload.reason)
    session.commit()
    return {"id": target.id, "is_banned": target.is_banned}


@router.post("/users/{user_id}/unban")
def admin_unban_user(user_id: int, payload: UnbanRequest, request: Request, admin: Annotated[User, Depends(require_permission("admin:access"))],
                     session: Annotated[Session, Depends(get_session)]):
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    target.is_banned, target.ban_reason = False, None
    log_event(session, request, "user_unbanned", admin.id, "user", str(user_id), payload.reason)
    session.commit()
    return {"id": target.id, "is_banned": False}


@router.post("/users/{user_id}/suspend")
def admin_suspend_user(user_id: int, payload: SuspendRequest, request: Request,
                       admin: Annotated[User, Depends(require_permission("admin:access"))],
                       session: Annotated[Session, Depends(get_session)]):
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == admin.id or target.role == "admin":
        raise HTTPException(403, "Admins cannot suspend themselves or another admin")
    target.suspended_until = now() + timedelta(hours=payload.hours)
    target.suspension_reason = payload.reason
    target.token_version += 1
    for token in session.exec(select(RefreshSession).where(
        RefreshSession.user_id == user_id, RefreshSession.revoked_at == None
    )).all():
        token.revoked_at = now()
    log_event(session, request, "user_suspended", admin.id, "user", str(user_id),
              f"{payload.reason} (until {target.suspended_until.isoformat()})")
    session.commit()
    return {"id": target.id, "status": "suspended", "suspended_until": target.suspended_until}


@router.post("/users/{user_id}/unsuspend")
def admin_unsuspend_user(user_id: int, payload: UnbanRequest, request: Request,
                         admin: Annotated[User, Depends(require_permission("admin:access"))],
                         session: Annotated[Session, Depends(get_session)]):
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    target.suspended_until = None
    target.suspension_reason = None
    log_event(session, request, "user_unsuspended", admin.id, "user", str(user_id), payload.reason)
    session.commit()
    return {"id": target.id, "status": "banned" if target.is_banned else "active"}


@router.post("/users/bulk-ban")
def bulk_ban(payload: list[int], request: Request, admin: Annotated[User, Depends(require_permission("admin:access"))],
              session: Annotated[Session, Depends(get_session)], reason: str = Query(min_length=3, max_length=500)):
    updated = []
    for user_id in set(payload):
        target = session.get(User, user_id)
        if target and target.role != "admin" and target.id != admin.id:
            target.is_banned, target.ban_reason = True, reason
            target.token_version += 1
            for token in session.exec(select(RefreshSession).where(RefreshSession.user_id == user_id, RefreshSession.revoked_at == None)).all():
                token.revoked_at = now()
            log_event(session, request, "user_banned", admin.id, "user", str(user_id), reason)
            updated.append(user_id)
    session.commit()
    return {"updated_user_ids": updated}


@router.post("/users/bulk-unban")
def bulk_unban(payload: list[int], request: Request, admin: Annotated[User, Depends(require_permission("admin:access"))],
                session: Annotated[Session, Depends(get_session)], reason: str = Query(min_length=3, max_length=500)):
    updated = []
    for user_id in set(payload):
        target = session.get(User, user_id)
        if target and target.role == "user" and target.is_banned:
            target.is_banned, target.ban_reason = False, None
            log_event(session, request, "user_unbanned", admin.id, "user", str(user_id), reason)
            updated.append(user_id)
    session.commit()
    return {"updated_user_ids": updated}


@router.post("/users/{user_id}/revoke-sessions")
def admin_revoke_sessions(user_id: int, request: Request, admin: Annotated[User, Depends(require_permission("admin:access"))],
                          session: Annotated[Session, Depends(get_session)]):
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    rows = session.exec(select(RefreshSession).where(RefreshSession.user_id == user_id,
        RefreshSession.revoked_at == None)).all()
    for row in rows:
        row.revoked_at = now()
    target.token_version += 1
    session.add(target)
    log_event(session, request, "sessions_revoked", admin.id, "user", str(user_id), f"{len(rows)} sessions")
    session.commit()
    return {"revoked_sessions": len(rows)}
