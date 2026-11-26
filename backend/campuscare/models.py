from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from campuscare.utils import now


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=254)
    full_name: str = Field(max_length=100)
    password_hash: str
    role: str = Field(default="user", index=True, max_length=10)
    is_banned: bool = Field(default=False, index=True)
    token_version: int = 0
    ban_reason: str | None = None
    suspended_until: datetime | None = Field(default=None, index=True)
    suspension_reason: str | None = None
    created_at: datetime = Field(default_factory=now, index=True)
    updated_at: datetime = Field(default_factory=now)


class RefreshSession(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    token_hash: str = Field(index=True, unique=True)
    expires_at: datetime = Field(index=True)
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=now)
    ip_address: str | None = None
    user_agent: str | None = None


class AuditEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, index=True)
    event: str = Field(index=True, max_length=60)
    target_type: str | None = None
    target_id: str | None = None
    detail: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime = Field(default_factory=now, index=True)


class LoginAttempt(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email_key: str = Field(index=True)
    ip_address: str = Field(index=True)
    succeeded: bool = False
    created_at: datetime = Field(default_factory=now, index=True)


class Complaint(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_id: int | None = Field(default=None, foreign_key="user.id", index=True)
    title: str = Field(min_length=5, max_length=100)
    description: str = Field(min_length=10, max_length=2000)
    category: str = Field(max_length=20, index=True)
    status: str = Field(default="pending", max_length=15, index=True)
    admin_response: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=now, index=True)
    updated_at: datetime = Field(default_factory=now)


class Group(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, index=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=now)


class GroupMember(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    can_create: bool = False
    can_edit: bool = False
    can_assign: bool = False
    created_at: datetime = Field(default_factory=now)


class GroupRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id", index=True)
    created_by: int = Field(foreign_key="user.id")
    title: str = Field(max_length=120)
    body: str = Field(max_length=2000)
    assignee_id: int | None = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
