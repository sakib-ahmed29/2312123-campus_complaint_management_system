from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func
from sqlmodel import Session, select

from campuscare.audit import log_event
from campuscare.database import get_session
from campuscare.models import AuditEvent, Complaint, Group, LoginAttempt, User
from campuscare.security import require_permission
from campuscare.serializers import audit_out
from campuscare.utils import now


router = APIRouter(prefix="/api/v1/admin", tags=["admin: reports"])


def _safe_csv_cell(value: object) -> object:
    """Neutralize spreadsheet formulas in untrusted text fields."""
    if isinstance(value, str) and value.lstrip(" \\t\\r\\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@router.get("/stats")
def admin_stats(admin: Annotated[User, Depends(require_permission("admin:access"))], session: Annotated[Session, Depends(get_session)]):
    week = now() - timedelta(days=7)
    count_users = session.exec(select(func.count()).select_from(User)).one()
    count_banned = session.exec(select(func.count()).select_from(User).where(User.is_banned == True)).one()
    count_suspended = session.exec(select(func.count()).select_from(User).where(User.is_banned == False, User.suspended_until > now())).one()
    count_records = session.exec(select(func.count()).select_from(Complaint)).one()
    count_groups = session.exec(select(func.count()).select_from(Group)).one()
    count_new = session.exec(select(func.count()).select_from(User).where(User.created_at >= week)).one()
    new_records = session.exec(select(func.count()).select_from(Complaint).where(Complaint.created_at >= week)).one()
    new_groups = session.exec(select(func.count()).select_from(Group).where(Group.created_at >= week)).one()
    return {"users": count_users, "banned_users": count_banned, "suspended_users": count_suspended, "records": count_records,
            "groups": count_groups, "new_users_last_7_days": count_new,
            "new_records_last_7_days": new_records, "new_groups_last_7_days": new_groups}


@router.get("/activity")
def admin_activity(admin: Annotated[User, Depends(require_permission("admin:access"))],
                   session: Annotated[Session, Depends(get_session)], q: str = "", event: str | None = None,
                   user_id: int | None = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    statement = select(AuditEvent)
    if event:
        statement = statement.where(AuditEvent.event == event)
    if user_id is not None:
        statement = statement.where(AuditEvent.user_id == user_id)
    if q:
        statement = statement.where(AuditEvent.detail.contains(q) | AuditEvent.ip_address.contains(q) | AuditEvent.user_agent.contains(q) | AuditEvent.event.contains(q))
    rows = session.exec(statement.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit)).all()
    return [audit_out(row) for row in rows]


@router.get("/security")
def admin_security(admin: Annotated[User, Depends(require_permission("admin:access"))],
                   session: Annotated[Session, Depends(get_session)]):
    cutoff = now() - timedelta(days=7)
    attempts = session.exec(select(LoginAttempt).where(LoginAttempt.succeeded == False, LoginAttempt.created_at >= cutoff)).all()
    by_ip: dict[str, int] = {}
    by_account: dict[str, int] = {}
    for attempt in attempts:
        by_ip[attempt.ip_address] = by_ip.get(attempt.ip_address, 0) + 1
        by_account[attempt.email_key] = by_account.get(attempt.email_key, 0) + 1
    return {"failed_logins_last_7_days": len(attempts), "by_ip": by_ip, "by_account": by_account}


@router.get("/export/{kind}")
def admin_export(kind: str, request: Request, admin: Annotated[User, Depends(require_permission("admin:access"))],
                 session: Annotated[Session, Depends(get_session)], status: str | None = None,
                 role: str | None = None, q: str = "", event: str | None = None,
                 category: str | None = None, user_id: int | None = None):
    output = io.StringIO(newline="")
    output.write("\\ufeff")
    writer = csv.writer(output)

    def write_row(values: list[object]) -> None:
        writer.writerow([_safe_csv_cell(value) for value in values])
    if kind == "users":
        write_row(["id", "email", "full_name", "role", "is_banned", "created_at"])
        statement = select(User)
        if role in ("user", "admin"):
            statement = statement.where(User.role == role)
        if status == "banned":
            statement = statement.where(User.is_banned == True)
        elif status == "suspended":
            statement = statement.where(User.is_banned == False, User.suspended_until > now())
        elif status == "active":
            statement = statement.where(User.is_banned == False).where((User.suspended_until == None) | (User.suspended_until <= now()))
        if q:
            statement = statement.where(User.email.contains(q.lower()) | User.full_name.contains(q))
        for u in session.exec(statement.order_by(User.id).limit(10000)).all():
            write_row([u.id, u.email, u.full_name, u.role, u.is_banned, u.created_at.isoformat()])
    elif kind == "records":
        write_row(["id", "owner_id", "title", "category", "status", "created_at"])
        statement = select(Complaint)
        if status:
            statement = statement.where(Complaint.status == status)
        if category:
            statement = statement.where(Complaint.category == category)
        for c in session.exec(statement.order_by(Complaint.id).limit(10000)).all():
            write_row([c.id, c.owner_id, c.title, c.category, c.status, c.created_at.isoformat()])
    elif kind == "activity":
        write_row(["id", "user_id", "event", "ip_address", "user_agent", "created_at"])
        statement = select(AuditEvent)
        if event:
            statement = statement.where(AuditEvent.event == event)
        if user_id is not None:
            statement = statement.where(AuditEvent.user_id == user_id)
        if q:
            statement = statement.where(AuditEvent.detail.contains(q) | AuditEvent.ip_address.contains(q) | AuditEvent.user_agent.contains(q) | AuditEvent.event.contains(q))
        for a in session.exec(statement.order_by(AuditEvent.id.desc()).limit(10000)).all():
            write_row([a.id, a.user_id, a.event, a.ip_address, a.user_agent, a.created_at.isoformat()])
    else:
        raise HTTPException(404, "Unknown export type")
    log_event(session, request, "data_export", admin.id, kind, detail=f"status={status}; role={role}; event={event}; user_id={user_id}; category={category}; q={q}")
    session.commit()
    return Response(content=output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="campuscare-{kind}.csv"'})
