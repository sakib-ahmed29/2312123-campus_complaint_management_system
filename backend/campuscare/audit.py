from __future__ import annotations

from fastapi import Request
from sqlmodel import Session

from campuscare.models import AuditEvent
from campuscare.utils import client_ip


def log_event(session: Session, request: Request, event: str, user_id: int | None = None,
              target_type: str | None = None, target_id: str | None = None, detail: str | None = None):
    session.add(AuditEvent(user_id=user_id, event=event, target_type=target_type, target_id=target_id,
                           detail=detail, ip_address=client_ip(request),
                           user_agent=request.headers.get("user-agent")))
