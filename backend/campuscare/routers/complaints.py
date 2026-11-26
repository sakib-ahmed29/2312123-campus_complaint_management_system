from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlmodel import Session, select

from campuscare.audit import log_event
from campuscare.database import get_session
from campuscare.models import Complaint, User
from campuscare.schemas import ComplaintCreate, ComplaintUpdate, StatusUpdate
from campuscare.security import current_user, require_permission
from campuscare.serializers import complaint_out
from campuscare.utils import now


router = APIRouter(prefix="/api/v1/complaints", tags=["complaints"])


ALLOWED_STATUS_CHANGES = {"pending": {"in_progress", "rejected"}, "in_progress": {"resolved", "rejected"},
                          "resolved": set(), "rejected": set()}


def owned_complaint(complaint_id: int, user: User, session: Session, admin_allowed: bool = False) -> Complaint:
    item = session.get(Complaint, complaint_id)
    if not item or (item.owner_id != user.id and not (admin_allowed and user.role == "admin")):
        raise HTTPException(404, "Complaint not found")
    return item


@router.post("", status_code=201)
def create_complaint(payload: ComplaintCreate, request: Request, user: Annotated[User, Depends(require_permission("complaint:create"))],
                     session: Annotated[Session, Depends(get_session)]):
    item = Complaint(owner_id=user.id, title=payload.title.strip(), description=payload.description.strip(),
                     category=payload.category)
    session.add(item)
    session.commit()
    session.refresh(item)
    log_event(session, request, "complaint_create", user.id, "complaint", str(item.id))
    session.commit()
    return complaint_out(item)


@router.get("")
def list_complaints(user: Annotated[User, Depends(current_user)], session: Annotated[Session, Depends(get_session)],
                    status: str | None = None, category: str | None = None,
                    offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    statement = select(Complaint)
    if user.role != "admin":
        statement = statement.where(Complaint.owner_id == user.id)
    if status:
        statement = statement.where(Complaint.status == status)
    if category:
        statement = statement.where(Complaint.category == category)
    rows = session.exec(statement.order_by(Complaint.created_at.desc()).offset(offset).limit(limit)).all()
    return [complaint_out(row) for row in rows]


@router.get("/{complaint_id}")
def get_complaint(complaint_id: int, user: Annotated[User, Depends(current_user)],
                  session: Annotated[Session, Depends(get_session)]):
    return complaint_out(owned_complaint(complaint_id, user, session, admin_allowed=True))


@router.patch("/{complaint_id}")
def update_complaint(complaint_id: int, payload: ComplaintUpdate, user: Annotated[User, Depends(require_permission("complaint:update:own"))],
                     session: Annotated[Session, Depends(get_session)]):
    item = owned_complaint(complaint_id, user, session)
    if item.status != "pending":
        raise HTTPException(409, "Only pending complaints can be edited")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Provide at least one field")
    for key, value in changes.items():
        if value is None:
            raise HTTPException(422, f"{key} cannot be null")
        setattr(item, key, value.strip() if isinstance(value, str) else value)
    item.updated_at = now()
    session.add(item)
    session.commit()
    session.refresh(item)
    return complaint_out(item)


@router.delete("/{complaint_id}", status_code=204)
def delete_complaint(complaint_id: int, request: Request, user: Annotated[User, Depends(current_user)],
                     session: Annotated[Session, Depends(get_session)]):
    item = owned_complaint(complaint_id, user, session, admin_allowed=True)
    if item.status != "pending" and user.role != "admin":
        raise HTTPException(409, "Only pending complaints can be deleted")
    log_event(session, request, "complaint_delete", user.id, "complaint", str(item.id))
    session.delete(item)
    session.commit()
    return Response(status_code=204)


@router.patch("/{complaint_id}/status")
def update_complaint_status(complaint_id: int, payload: StatusUpdate, request: Request,
                            user: Annotated[User, Depends(require_permission("complaint:status"))],
                            session: Annotated[Session, Depends(get_session)]):
    item = session.get(Complaint, complaint_id)
    if not item:
        raise HTTPException(404, "Complaint not found")
    if payload.status not in ALLOWED_STATUS_CHANGES.get(item.status, set()):
        raise HTTPException(409, f"Cannot change status from {item.status} to {payload.status}")
    item.status = payload.status
    if payload.admin_response is not None:
        item.admin_response = payload.admin_response.strip() or None
    item.updated_at = now()
    session.add(item)
    log_event(session, request, "complaint_status_change", user.id, "complaint", str(item.id), payload.status)
    session.commit()
    session.refresh(item)
    return complaint_out(item)
