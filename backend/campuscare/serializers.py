from __future__ import annotations

from campuscare.models import AuditEvent, Complaint, Group, GroupMember, GroupRecord


def complaint_out(row: Complaint) -> dict:
    return {"id": row.id, "owner_id": row.owner_id, "title": row.title, "description": row.description,
            "category": row.category, "status": row.status, "admin_response": row.admin_response,
            "created_at": row.created_at, "updated_at": row.updated_at}


def group_out(row: Group) -> dict:
    return {"id": row.id, "name": row.name, "owner_id": row.owner_id, "created_at": row.created_at}


def member_out(row: GroupMember) -> dict:
    return {"id": row.id, "group_id": row.group_id, "user_id": row.user_id,
            "can_create": row.can_create, "can_edit": row.can_edit, "can_assign": row.can_assign}


def record_out(row: GroupRecord) -> dict:
    return {"id": row.id, "group_id": row.group_id, "created_by": row.created_by, "title": row.title,
            "body": row.body, "assignee_id": row.assignee_id, "created_at": row.created_at,
            "updated_at": row.updated_at}


def audit_out(row: AuditEvent) -> dict:
    return {"id": row.id, "user_id": row.user_id, "event": row.event, "target_type": row.target_type,
            "target_id": row.target_id, "detail": row.detail, "ip_address": row.ip_address,
            "user_agent": row.user_agent, "created_at": row.created_at}
