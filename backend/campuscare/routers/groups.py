from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select

from campuscare.database import get_session
from campuscare.models import Group, GroupMember, GroupRecord, User
from campuscare.schemas import GroupCreate, GroupRecordCreate, GroupRecordUpdate, MemberPermissions
from campuscare.security import current_user
from campuscare.serializers import group_out, member_out, record_out
from campuscare.utils import now


router = APIRouter(prefix="/api/v1/groups", tags=["groups"])


def group_access(group_id: int, user: User, session: Session) -> tuple[Group, GroupMember | None]:
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    member = session.exec(select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == user.id)).first()
    if group.owner_id != user.id and not member:
        raise HTTPException(404, "Group not found")
    return group, member


@router.post("", status_code=201)
def create_group(payload: GroupCreate, user: Annotated[User, Depends(current_user)],
                 session: Annotated[Session, Depends(get_session)]):
    group = Group(name=payload.name.strip(), owner_id=user.id)
    session.add(group)
    session.commit()
    session.refresh(group)
    session.add(GroupMember(group_id=group.id, user_id=user.id, can_create=True, can_edit=True, can_assign=True))
    session.commit()
    session.refresh(group)
    return group_out(group)


@router.get("")
def list_groups(user: Annotated[User, Depends(current_user)], session: Annotated[Session, Depends(get_session)]):
    return [group_out(g) for g in session.exec(select(Group).join(GroupMember, Group.id == GroupMember.group_id).where(GroupMember.user_id == user.id)).all()]


@router.post("/{group_id}/members")
def add_group_member(group_id: int, payload: MemberPermissions, user: Annotated[User, Depends(current_user)],
                     session: Annotated[Session, Depends(get_session)]):
    group = session.get(Group, group_id)
    if not group or group.owner_id != user.id:
        raise HTTPException(404, "Group not found")
    target = session.get(User, payload.user_id)
    if not target or target.is_banned:
        raise HTTPException(404, "User not found")
    member = session.exec(select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == payload.user_id)).first()
    if not member:
        member = GroupMember(group_id=group_id, user_id=payload.user_id)
    member.can_create, member.can_edit, member.can_assign = payload.can_create, payload.can_edit, payload.can_assign
    session.add(member)
    session.commit()
    session.refresh(member)
    return member_out(member)


@router.patch("/{group_id}")
def rename_group(group_id: int, payload: GroupCreate, user: Annotated[User, Depends(current_user)],
                 session: Annotated[Session, Depends(get_session)]):
    group = session.get(Group, group_id)
    if not group or group.owner_id != user.id:
        raise HTTPException(404, "Group not found")
    group.name = payload.name.strip()
    session.add(group)
    session.commit()
    return group_out(group)


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: int, user: Annotated[User, Depends(current_user)],
                 session: Annotated[Session, Depends(get_session)]):
    group = session.get(Group, group_id)
    if not group or group.owner_id != user.id:
        raise HTTPException(404, "Group not found")
    for row in session.exec(select(GroupRecord).where(GroupRecord.group_id == group_id)).all():
        session.delete(row)
    for row in session.exec(select(GroupMember).where(GroupMember.group_id == group_id)).all():
        session.delete(row)
    session.delete(group)
    session.commit()
    return Response(status_code=204)


@router.get("/{group_id}/members")
def group_members(group_id: int, user: Annotated[User, Depends(current_user)],
                  session: Annotated[Session, Depends(get_session)]):
    group, _ = group_access(group_id, user, session)
    members = session.exec(select(GroupMember).where(GroupMember.group_id == group_id)).all()
    people = {u.id: u for u in session.exec(select(User).where(User.id.in_([m.user_id for m in members]))).all()}
    return [{"user_id": m.user_id, "full_name": people[m.user_id].full_name if m.user_id in people else None,
             "email": people[m.user_id].email if m.user_id in people else None,
             "can_create": m.can_create, "can_edit": m.can_edit,
             "can_assign": m.can_assign, "is_owner": m.user_id == group.owner_id} for m in members]


@router.post("/{group_id}/records", status_code=201)
def create_group_record(group_id: int, payload: GroupRecordCreate, user: Annotated[User, Depends(current_user)],
                        session: Annotated[Session, Depends(get_session)]):
    group, member = group_access(group_id, user, session)
    if group.owner_id != user.id and not member.can_create:
        raise HTTPException(403, "Group create permission required")
    record = GroupRecord(group_id=group_id, created_by=user.id, title=payload.title, body=payload.body)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record_out(record)


@router.get("/{group_id}/records")
def list_group_records(group_id: int, user: Annotated[User, Depends(current_user)],
                       session: Annotated[Session, Depends(get_session)]):
    group_access(group_id, user, session)
    rows = session.exec(select(GroupRecord).where(GroupRecord.group_id == group_id).order_by(GroupRecord.created_at.desc())).all()
    return [record_out(row) for row in rows]


@router.patch("/{group_id}/records/{record_id}")
def update_group_record(group_id: int, record_id: int, payload: GroupRecordUpdate,
                        user: Annotated[User, Depends(current_user)], session: Annotated[Session, Depends(get_session)]):
    group, member = group_access(group_id, user, session)
    record = session.get(GroupRecord, record_id)
    if not record or record.group_id != group_id:
        raise HTTPException(404, "Record not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Provide at least one field to update")
    if group.owner_id != user.id:
        if any(field in changes for field in ("title", "body")) and not member.can_edit:
            raise HTTPException(403, "Group edit permission required")
        if "assignee_id" in changes and not member.can_assign:
            raise HTTPException(403, "Group assign permission required")
    if "assignee_id" in changes and changes["assignee_id"] is not None:
        assigned_member = session.exec(select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == changes["assignee_id"])).first()
        if not assigned_member:
            raise HTTPException(422, "Assignee must be a member of this group")
    for key, value in changes.items():
        setattr(record, key, value)
    record.updated_at = now()
    session.add(record)
    session.commit()
    session.refresh(record)
    return record_out(record)


@router.delete("/{group_id}/members/{member_user_id}", status_code=204)
def remove_group_member(group_id: int, member_user_id: int, user: Annotated[User, Depends(current_user)],
                        session: Annotated[Session, Depends(get_session)]):
    group = session.get(Group, group_id)
    if not group or group.owner_id != user.id:
        raise HTTPException(404, "Group not found")
    member = session.exec(select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == member_user_id)).first()
    if not member:
        raise HTTPException(404, "Member not found")
    if member_user_id == group.owner_id:
        raise HTTPException(400, "Owner cannot be removed")
    session.delete(member)
    session.commit()
    return Response(status_code=204)
