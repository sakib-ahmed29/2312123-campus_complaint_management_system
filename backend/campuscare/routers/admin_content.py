from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlmodel import Session, select

from campuscare.audit import log_event
from campuscare.database import get_session
from campuscare.models import Complaint, Group, GroupMember, GroupRecord, User
from campuscare.security import require_permission
from campuscare.serializers import complaint_out, group_out


router = APIRouter(prefix="/api/v1/admin", tags=["admin: moderation"])


@router.get("/records")
def admin_records(admin: Annotated[User, Depends(require_permission("admin:access"))],
                  session: Annotated[Session, Depends(get_session)], status: str | None = None,
                  category: str | None = None, offset: int = Query(0, ge=0),
                  limit: int = Query(50, ge=1, le=200)):
    statement = select(Complaint)
    if status:
        statement = statement.where(Complaint.status == status)
    if category:
        statement = statement.where(Complaint.category == category)
    rows = session.exec(statement.order_by(Complaint.created_at.desc()).offset(offset).limit(limit)).all()
    return [complaint_out(row) for row in rows]


@router.delete("/records/{record_id}", status_code=204)
def admin_delete_record(record_id: int, request: Request,
                        admin: Annotated[User, Depends(require_permission("admin:access"))],
                        session: Annotated[Session, Depends(get_session)]):
    record = session.get(Complaint, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    log_event(session, request, "admin_record_delete", admin.id, "complaint", str(record_id))
    session.delete(record)
    session.commit()
    return Response(status_code=204)


@router.get("/groups")
def admin_groups(admin: Annotated[User, Depends(require_permission("admin:access"))],
                 session: Annotated[Session, Depends(get_session)], q: str = ""):
    statement = select(Group)
    if q:
        statement = statement.where(Group.name.contains(q))
    return [group_out(row) for row in session.exec(statement.order_by(Group.created_at.desc())).all()]


@router.delete("/groups/{group_id}", status_code=204)
def admin_delete_group(group_id: int, request: Request,
                       admin: Annotated[User, Depends(require_permission("admin:access"))],
                       session: Annotated[Session, Depends(get_session)]):
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    for row in session.exec(select(GroupRecord).where(GroupRecord.group_id == group_id)).all():
        session.delete(row)
    for row in session.exec(select(GroupMember).where(GroupMember.group_id == group_id)).all():
        session.delete(row)
    log_event(session, request, "admin_group_delete", admin.id, "group", str(group_id))
    session.delete(group)
    session.commit()
    return Response(status_code=204)


@router.post("/records/bulk-delete")
def admin_bulk_delete_records(payload: list[int], request: Request,
                              admin: Annotated[User, Depends(require_permission("admin:access"))],
                              session: Annotated[Session, Depends(get_session)]):
    deleted = []
    for record_id in set(payload):
        record = session.get(Complaint, record_id)
        if record:
            log_event(session, request, "admin_record_delete", admin.id, "complaint", str(record_id))
            session.delete(record)
            deleted.append(record_id)
    session.commit()
    return {"deleted_ids": deleted}


@router.post("/groups/bulk-delete")
def admin_bulk_delete_groups(payload: list[int], request: Request,
                             admin: Annotated[User, Depends(require_permission("admin:access"))],
                             session: Annotated[Session, Depends(get_session)]):
    deleted = []
    for group_id in set(payload):
        group = session.get(Group, group_id)
        if not group:
            continue
        for record in session.exec(select(GroupRecord).where(GroupRecord.group_id == group_id)).all():
            session.delete(record)
        for member in session.exec(select(GroupMember).where(GroupMember.group_id == group_id)).all():
            session.delete(member)
        log_event(session, request, "admin_group_delete", admin.id, "group", str(group_id))
        session.delete(group)
        deleted.append(group_id)
    session.commit()
    return {"deleted_ids": deleted}
