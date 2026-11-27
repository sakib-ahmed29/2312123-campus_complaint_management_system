from __future__ import annotations

from typing import Literal

from sqlmodel import Field, SQLModel


Role = Literal["user", "admin"]


Category = Literal["academic", "hostel", "library", "cafeteria", "transport", "it_network", "other"]


Status = Literal["pending", "in_progress", "resolved", "rejected"]


class Signup(SQLModel):
    email: str
    full_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class Login(SQLModel):
    email: str
    password: str


class ProfileUpdate(SQLModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: str


class PasswordChange(SQLModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class RoleChange(SQLModel):
    role: str


class BanRequest(SQLModel):
    reason: str = Field(min_length=3, max_length=500)


class UnbanRequest(SQLModel):
    reason: str = Field(min_length=3, max_length=500)


class SuspendRequest(SQLModel):
    reason: str = Field(min_length=3, max_length=500)
    hours: int = Field(ge=1, le=720)


class ComplaintCreate(SQLModel):
    title: str = Field(min_length=5, max_length=100)
    description: str = Field(min_length=10, max_length=2000)
    category: Category


class ComplaintUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=5, max_length=100)
    description: str | None = Field(default=None, min_length=10, max_length=2000)
    category: Category | None = None


class StatusUpdate(SQLModel):
    status: Status
    admin_response: str | None = Field(default=None, max_length=1000)


class GroupCreate(SQLModel):
    name: str = Field(min_length=2, max_length=100)


class MemberPermissions(SQLModel):
    user_id: int
    can_create: bool = False
    can_edit: bool = False
    can_assign: bool = False


class GroupRecordCreate(SQLModel):
    title: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=1, max_length=2000)


class GroupRecordUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=3, max_length=120)
    body: str | None = Field(default=None, min_length=1, max_length=2000)
    assignee_id: int | None = None
