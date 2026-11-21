from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import hmac
import io
import os
import secrets
from typing import Literal
from uuid import uuid4

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import func
from sqlalchemy.pool import NullPool
from sqlmodel import Field, Session, SQLModel, create_engine, select


Role = Literal["user", "admin"]
Category = Literal["academic", "hostel", "library", "cafeteria", "transport", "it_network", "other"]
ComplaintStatus = Literal["pending", "in_progress", "resolved", "rejected"]
password_hasher = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
ACCESS_MINUTES = 15
REFRESH_DAYS = 7
COOKIE_NAME = "ccms_refresh"
MAX_LOGIN_ATTEMPTS = 5
LOCK_MINUTES = 15


def now() -> datetime:
    return datetime.now(timezone.utc)


def get_secret(name: str, local_default: str | None = None) -> str:
    value = os.getenv(name)
    if value:
        return value
    if os.getenv("VERCEL"):
        raise RuntimeError(f"{name} must be configured in the deployment environment")
    return local_default or secrets.token_urlsafe(48)


JWT_SECRET = get_secret("JWT_SECRET", "local-development-only-change-this-secret-32-bytes")
PASSWORD_PEPPER = get_secret("PASSWORD_PEPPER", "local-development-pepper-change-before-deploy")
JWT_ALGORITHM = "HS256"


def password_material(password: str) -> str:
    return hmac.new(PASSWORD_PEPPER.encode(), password.encode(), hashlib.sha256).hexdigest()


def hash_password(password: str) -> str:
    return password_hasher.hash(password_material(password))


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hasher.verify(password_material(password), encoded)
    except Exception:
        return False


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_access_token(user: "User") -> str:
    issued = now()
    scopes = ["profile:read", "profile:update", "complaint:read", "complaint:create", "complaint:update", "complaint:delete", "group:read", "group:create"]
    if user.role == "admin":
        scopes += ["complaint:moderate", "admin:read", "admin:write", "group:moderate", "audit:read", "export:read"]
    payload = {"sub": user.id, "role": user.role, "scopes": scopes, "iat": issued, "exp": issued + timedelta(minutes=ACCESS_MINUTES)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def audit(session: Session, request: Request, action: str, actor_id: str | None = None, target_type: str | None = None, target_id: str | None = None, details: str | None = None) -> None:
    session.add(AuditLog(actor_id=actor_id, action=action, target_type=target_type, target_id=target_id,
                         details=details, ip_address=request.client.host if request.client else None,
                         user_agent=request.headers.get("user-agent", "")[:500], created_at=now()))


class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    email: str = Field(index=True, max_length=254)
    name: str = Field(max_length=100)
    password_hash: str
    role: str = Field(default="user", max_length=10, index=True)
    is_banned: bool = Field(default=False, index=True)
    ban_reason: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=now, index=True)
    updated_at: datetime = Field(default_factory=now)


class Complaint(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_id: str | None = Field(default=None, foreign_key="user.id", index=True)
    title: str = Field(min_length=5, max_length=100)
    description: str = Field(min_length=10, max_length=2000)
    category: str = Field(max_length=20, index=True)
    status: str = Field(default="pending", max_length=15, index=True)
    admin_response: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=now, index=True)
    updated_at: datetime = Field(default_factory=now)


class RefreshSession(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    token_hash: str = Field(index=True, unique=True)
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=now)
    ip_address: str | None = None
    user_agent: str | None = Field(default=None, max_length=500)


class CampusGroup(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str = Field(max_length=100, index=True)
    description: str = Field(default="", max_length=1000)
    owner_id: str = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=now)


class GroupMember(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    group_id: str = Field(foreign_key="campusgroup.id", index=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    can_create: bool = False
    can_edit: bool = False
    can_assign: bool = False
    joined_at: datetime = Field(default_factory=now)


class GroupRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    group_id: str = Field(foreign_key="campusgroup.id", index=True)
    created_by: str = Field(foreign_key="user.id", index=True)
    title: str = Field(max_length=150)
    content: str = Field(max_length=5000)
    assignee_id: str | None = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class AuditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    actor_id: str | None = Field(default=None, index=True)
    action: str = Field(index=True, max_length=80)
    target_type: str | None = Field(default=None, max_length=50)
    target_id: str | None = Field(default=None, max_length=100)
    details: str | None = Field(default=None, max_length=1000)
    ip_address: str | None = Field(default=None, max_length=100, index=True)
    user_agent: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=now, index=True)


class FailedLogin(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, max_length=254)
    ip_address: str | None = Field(default=None, index=True)
    attempted_at: datetime = Field(default_factory=now, index=True)


class SignupInput(SQLModel):
    email: str = Field(min_length=5, max_length=254)
    name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginInput(SQLModel):
    email: str
    password: str


class ProfileUpdate(SQLModel):
    name: str = Field(min_length=2, max_length=100)


class PasswordChange(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ComplaintCreate(SQLModel):
    title: str = Field(min_length=5, max_length=100)
    description: str = Field(min_length=10, max_length=2000)
    category: Category


class ComplaintUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=5, max_length=100)
    description: str | None = Field(default=None, min_length=10, max_length=2000)
    category: Category | None = None


class StatusUpdate(SQLModel):
    status: ComplaintStatus
    admin_response: str | None = Field(default=None, max_length=1000)


class RoleUpdate(SQLModel):
    role: Role


class BanInput(SQLModel):
    reason: str = Field(min_length=3, max_length=500)


class GroupCreate(SQLModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=1000)


class MemberPermissions(SQLModel):
    can_create: bool = False
    can_edit: bool = False
    can_assign: bool = False


class GroupRecordCreate(SQLModel):
    title: str = Field(min_length=3, max_length=150)
    content: str = Field(min_length=1, max_length=5000)


class GroupRecordUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=3, max_length=150)
    content: str | None = Field(default=None, min_length=1, max_length=5000)
    assignee_id: str | None = None


def db_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        if os.getenv("VERCEL"):
            raise RuntimeError("DATABASE_URL must be configured on Vercel; ephemeral SQLite is not supported")
        value = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'ccms.db')}"
    if value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql+psycopg://", 1)
    elif value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


DATABASE_URL = db_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")
engine_options = {"connect_args": {"check_same_thread": False} if IS_SQLITE else {}, "echo": False}
if not IS_SQLITE:
    engine_options["poolclass"] = NullPool
engine = create_engine(DATABASE_URL, **engine_options)


def get_session():
    with Session(engine) as session:
        yield session


@asynccontextmanager
async def lifespan(_: FastAPI):
    from alembic import command
    from alembic.config import Config
    migration_config = Config(str(Path(__file__).resolve().parent / "alembic.ini"))
    command.upgrade(migration_config, "head")
    yield


app = FastAPI(title="CampusCare API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None, lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.scheme == "https" or os.getenv("VERCEL"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer), session: Session = Depends(get_session)) -> User:
    if not credentials:
        raise HTTPException(401, "Authentication required")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("missing subject")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(401, "Invalid or expired access token")
    request.state.token_scopes = payload.get("scopes", [])
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(401, "Invalid or expired access token")
    if user.is_banned:
        raise HTTPException(403, "This account is suspended")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Administrator permission required")
    return user


def require_scope(scope: str):
    def dependency(request: Request, user: User = Depends(current_user)) -> User:
        if scope not in getattr(request.state, "token_scopes", []):
            raise HTTPException(403, f"Missing required scope: {scope}")
        if scope.startswith("admin:") or scope == "complaint:moderate":
            if user.role != "admin":
                raise HTTPException(403, "Administrator permission required")
        return user
    return dependency


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=bool(os.getenv("VERCEL")), samesite="strict",
                        max_age=REFRESH_DAYS * 86400, path="/api/v1/auth")


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/api/v1/auth", httponly=True, secure=bool(os.getenv("VERCEL")), samesite="strict")


def issue_refresh(session: Session, user: User, request: Request) -> str:
    raw = secrets.token_urlsafe(48)
    session.add(RefreshSession(user_id=user.id, token_hash=token_hash(raw), expires_at=now() + timedelta(days=REFRESH_DAYS),
                               ip_address=request.client.host if request.client else None,
                               user_agent=request.headers.get("user-agent", "")[:500]))
    return raw


def member_for(session: Session, group_id: str, user_id: str) -> GroupMember | None:
    return session.exec(select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == user_id)).first()


@app.get("/api/health")
def health():
    return {"status": "ok", "database": "postgresql" if not IS_SQLITE else "sqlite"}


@app.post("/api/v1/auth/signup", status_code=201)
def signup(payload: SignupInput, request: Request, session: Session = Depends(get_session)):
    email = payload.email.strip().lower()
    name = payload.name.strip()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(422, "A valid email address is required")
    if len(name) < 2 or len(payload.password) < 8 or not any(c.isalpha() for c in payload.password) or not any(c.isdigit() for c in payload.password):
        raise HTTPException(422, "Name must have 2 characters and password must include a letter and a number")
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, name=name, password_hash=hash_password(payload.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    audit(session, request, "signup", user.id, "user", user.id)
    session.commit()
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role, "created_at": user.created_at}


@app.post("/api/v1/auth/login")
def login(payload: LoginInput, request: Request, response: Response, session: Session = Depends(get_session)):
    email = payload.email.strip().lower()
    ip = request.client.host if request.client else ""
    since = now() - timedelta(minutes=LOCK_MINUTES)
    attempts = session.exec(select(FailedLogin).where(FailedLogin.email == email, FailedLogin.attempted_at >= since)).all()
    ip_attempts = session.exec(select(FailedLogin).where(FailedLogin.ip_address == ip, FailedLogin.attempted_at >= since)).all()
    if len(attempts) >= MAX_LOGIN_ATTEMPTS or len(ip_attempts) >= MAX_LOGIN_ATTEMPTS * 3:
        raise HTTPException(429, "Too many login attempts. Try again in 15 minutes.")
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        session.add(FailedLogin(email=email, ip_address=ip))
        audit(session, request, "login_failed", user.id if user else None, "account", email)
        session.commit()
        raise HTTPException(401, "Invalid email or password")
    if user.is_banned:
        audit(session, request, "login_blocked_banned", user.id, "user", user.id)
        session.commit()
        raise HTTPException(403, "This account is suspended")
    raw = issue_refresh(session, user, request)
    audit(session, request, "login", user.id, "user", user.id)
    session.commit()
    set_refresh_cookie(response, raw)
    return {"access_token": create_access_token(user), "token_type": "bearer", "expires_in": ACCESS_MINUTES * 60,
            "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role}}


@app.post("/api/v1/auth/refresh")
def refresh(request: Request, response: Response, session: Session = Depends(get_session)):
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        raise HTTPException(401, "Refresh session required")
    stored = session.exec(select(RefreshSession).where(RefreshSession.token_hash == token_hash(raw))).first()
    if not stored or stored.revoked_at or stored.expires_at <= now():
        clear_refresh_cookie(response)
        raise HTTPException(401, "Refresh session is invalid or expired")
    user = session.get(User, stored.user_id)
    if not user or user.is_banned:
        stored.revoked_at = now()
        session.add(stored)
        session.commit()
        clear_refresh_cookie(response)
        raise HTTPException(401, "Refresh session is invalid")
    stored.revoked_at = now()
    new_raw = issue_refresh(session, user, request)
    session.add(stored)
    audit(session, request, "token_refresh", user.id, "session", stored.id)
    session.commit()
    set_refresh_cookie(response, new_raw)
    return {"access_token": create_access_token(user), "token_type": "bearer", "expires_in": ACCESS_MINUTES * 60}


@app.post("/api/v1/auth/logout", status_code=204)
def logout(request: Request, response: Response, session: Session = Depends(get_session), user: User = Depends(current_user)):
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        stored = session.exec(select(RefreshSession).where(RefreshSession.token_hash == token_hash(raw), RefreshSession.user_id == user.id)).first()
        if stored:
            stored.revoked_at = now()
            session.add(stored)
    audit(session, request, "logout", user.id, "user", user.id)
    session.commit()
    clear_refresh_cookie(response)
    return Response(status_code=204)


@app.get("/api/v1/users/me")
def my_profile(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role, "created_at": user.created_at}


@app.patch("/api/v1/users/me")
def update_profile(payload: ProfileUpdate, request: Request, session: Session = Depends(get_session), user: User = Depends(current_user)):
    user.name = payload.name.strip()
    user.updated_at = now()
    session.add(user)
    audit(session, request, "profile_updated", user.id, "user", user.id)
    session.commit()
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role, "created_at": user.created_at}


@app.post("/api/v1/users/me/password", status_code=204)
def change_password(payload: PasswordChange, request: Request, response: Response, session: Session = Depends(get_session), user: User = Depends(current_user)):
    if not verify_password(payload.current_password, user.password_hash):
        audit(session, request, "password_change_failed", user.id, "user", user.id)
        session.commit()
        raise HTTPException(400, "Current password is incorrect")
    if len(payload.new_password) < 8 or not any(c.isalpha() for c in payload.new_password) or not any(c.isdigit() for c in payload.new_password):
        raise HTTPException(422, "New password must include at least one letter and one number")
    user.password_hash = hash_password(payload.new_password)
    for item in session.exec(select(RefreshSession).where(RefreshSession.user_id == user.id, RefreshSession.revoked_at == None)).all():
        item.revoked_at = now()
        session.add(item)
    audit(session, request, "password_changed", user.id, "user", user.id)
    session.add(user)
    session.commit()
    clear_refresh_cookie(response)
    return Response(status_code=204)


@app.get("/api/v1/users/me/sessions")
def my_sessions(user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.exec(select(RefreshSession).where(RefreshSession.user_id == user.id).order_by(RefreshSession.created_at.desc())).all()
    return [{"id": x.id, "created_at": x.created_at, "expires_at": x.expires_at, "revoked": x.revoked_at is not None,
             "ip_address": x.ip_address, "user_agent": x.user_agent} for x in rows]


@app.delete("/api/v1/users/me/sessions/{session_id}", status_code=204)
def revoke_session(session_id: str, request: Request, session: Session = Depends(get_session), user: User = Depends(current_user)):
    item = session.get(RefreshSession, session_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, "Session not found")
    item.revoked_at = now()
    session.add(item)
    audit(session, request, "session_revoked", user.id, "session", session_id)
    session.commit()
    return Response(status_code=204)


ALLOWED_STATUS_CHANGES = {"pending": {"in_progress", "rejected"}, "in_progress": {"resolved", "rejected"}, "resolved": set(), "rejected": set()}


@app.post("/api/v1/complaints", status_code=201)
def create_complaint(payload: ComplaintCreate, user: User = Depends(current_user), session: Session = Depends(get_session)):
    title, description = payload.title.strip(), payload.description.strip()
    if len(title) < 5 or len(description) < 10:
        raise HTTPException(422, "Title or description is too short")
    item = Complaint(owner_id=user.id, title=title, description=description, category=payload.category)
    session.add(item); session.commit(); session.refresh(item)
    return item


@app.get("/api/v1/complaints")
def list_complaints(status_filter: ComplaintStatus | None = Query(default=None, alias="status"), category: Category | None = None,
                    offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100),
                    user: User = Depends(current_user), session: Session = Depends(get_session)):
    statement = select(Complaint)
    if user.role != "admin":
        statement = statement.where(Complaint.owner_id == user.id)
    if status_filter:
        statement = statement.where(Complaint.status == status_filter)
    if category:
        statement = statement.where(Complaint.category == category)
    return session.exec(statement.order_by(Complaint.created_at.desc()).offset(offset).limit(limit)).all()


def get_owned_complaint(complaint_id: int, user: User, session: Session) -> Complaint:
    item = session.get(Complaint, complaint_id)
    if not item or (user.role != "admin" and item.owner_id != user.id):
        raise HTTPException(404, "Complaint not found")
    return item


@app.get("/api/v1/complaints/{complaint_id}")
def get_complaint(complaint_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return get_owned_complaint(complaint_id, user, session)


@app.patch("/api/v1/complaints/{complaint_id}")
def update_complaint(complaint_id: int, payload: ComplaintUpdate, user: User = Depends(current_user), session: Session = Depends(get_session)):
    if user.role == "admin":
        raise HTTPException(403, "Administrators moderate complaints; they do not edit student submissions")
    item = get_owned_complaint(complaint_id, user, session)
    if item.status != "pending":
        raise HTTPException(409, "Only pending complaints can be edited")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Provide at least one field to update")
    for key, value in changes.items():
        if value is None:
            raise HTTPException(422, f"{key} cannot be null")
        if isinstance(value, str):
            value = value.strip()
            if key == "title" and len(value) < 5 or key == "description" and len(value) < 10:
                raise HTTPException(422, f"Invalid {key}")
        setattr(item, key, value)
    item.updated_at = now()
    session.add(item); session.commit(); session.refresh(item)
    return item


@app.delete("/api/v1/complaints/{complaint_id}", status_code=204)
def delete_complaint(complaint_id: int, request: Request, user: User = Depends(current_user), session: Session = Depends(get_session)):
    item = get_owned_complaint(complaint_id, user, session)
    if user.role != "admin" and item.status != "pending":
        raise HTTPException(409, "Only pending complaints can be deleted")
    audit(session, request, "complaint_deleted", user.id, "complaint", str(item.id))
    session.delete(item); session.commit()
    return Response(status_code=204)


@app.patch("/api/v1/complaints/{complaint_id}/status")
def update_complaint_status(complaint_id: int, payload: StatusUpdate, request: Request, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    item = session.get(Complaint, complaint_id)
    if not item:
        raise HTTPException(404, "Complaint not found")
    if payload.status not in ALLOWED_STATUS_CHANGES[item.status]:
        raise HTTPException(409, f"Cannot change status from {item.status} to {payload.status}")
    if payload.status == "rejected" and not (payload.admin_response or "").strip():
        raise HTTPException(422, "An admin response is required when rejecting a complaint")
    item.status = payload.status
    if payload.admin_response is not None:
        item.admin_response = payload.admin_response.strip() or None
    item.updated_at = now()
    session.add(item)
    audit(session, request, "complaint_status_changed", user.id, "complaint", str(item.id), payload.status)
    session.commit(); session.refresh(item)
    return item


@app.get("/api/v1/users/me/dashboard")
def user_dashboard(user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.exec(select(Complaint).where(Complaint.owner_id == user.id)).all()
    return {"total": len(rows), **{s: sum(1 for x in rows if x.status == s) for s in ("pending", "in_progress", "resolved", "rejected")}}


@app.get("/api/v1/admin/stats")
def admin_stats(user: User = Depends(require_admin), session: Session = Depends(get_session)):
    users = session.exec(select(User)).all()
    complaints = session.exec(select(Complaint)).all()
    groups = session.exec(select(CampusGroup)).all()
    seven_days = now() - timedelta(days=7)
    return {"users": {"total": len(users), "admins": sum(x.role == "admin" for x in users),
                      "banned": sum(x.is_banned for x in users), "new_last_7_days": sum(x.created_at >= seven_days for x in users)},
            "complaints": {"total": len(complaints), "new_last_7_days": sum(x.created_at >= seven_days for x in complaints),
                           "by_status": {s: sum(x.status == s for x in complaints) for s in ("pending", "in_progress", "resolved", "rejected")},
                           "by_category": {c: sum(x.category == c for x in complaints) for c in ("academic", "hostel", "library", "cafeteria", "transport", "it_network", "other")}},
            "groups": {"total": len(groups), "new_last_7_days": sum(x.created_at >= seven_days for x in groups)}}


@app.get("/api/v1/admin/users")
def admin_users(search: str | None = None, role: Role | None = None, banned: bool | None = None,
                offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                user: User = Depends(require_admin), session: Session = Depends(get_session)):
    statement = select(User)
    if search:
        statement = statement.where(User.email.contains(search.lower()) | User.name.contains(search))
    if role:
        statement = statement.where(User.role == role)
    if banned is not None:
        statement = statement.where(User.is_banned == banned)
    rows = session.exec(statement.order_by(User.created_at.desc()).offset(offset).limit(limit)).all()
    return [{"id": x.id, "email": x.email, "name": x.name, "role": x.role, "is_banned": x.is_banned,
             "ban_reason": x.ban_reason, "created_at": x.created_at} for x in rows]


@app.patch("/api/v1/admin/users/{target_id}/role")
def change_role(target_id: str, payload: RoleUpdate, request: Request, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    if target_id == user.id:
        raise HTTPException(400, "You cannot change your own role")
    target = session.get(User, target_id)
    if not target:
        raise HTTPException(404, "User not found")
    target.role = payload.role
    target.updated_at = now()
    session.add(target)
    audit(session, request, "role_changed", user.id, "user", target.id, payload.role)
    session.commit()
    return {"id": target.id, "email": target.email, "role": target.role}


@app.post("/api/v1/admin/users/{target_id}/ban")
def ban_user(target_id: str, payload: BanInput, request: Request, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    if target_id == user.id:
        raise HTTPException(400, "You cannot ban yourself")
    target = session.get(User, target_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.role == "admin":
        raise HTTPException(400, "Administrators cannot ban another administrator")
    target.is_banned = True; target.ban_reason = payload.reason.strip()
    for item in session.exec(select(RefreshSession).where(RefreshSession.user_id == target.id, RefreshSession.revoked_at == None)).all():
        item.revoked_at = now(); session.add(item)
    session.add(target); audit(session, request, "user_banned", user.id, "user", target.id, target.ban_reason)
    session.commit()
    return {"id": target.id, "is_banned": True, "reason": target.ban_reason}


@app.post("/api/v1/admin/users/{target_id}/unban")
def unban_user(target_id: str, request: Request, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    target = session.get(User, target_id)
    if not target:
        raise HTTPException(404, "User not found")
    target.is_banned = False; target.ban_reason = None
    session.add(target); audit(session, request, "user_unbanned", user.id, "user", target.id)
    session.commit()
    return {"id": target.id, "is_banned": False}


@app.get("/api/v1/admin/audit")
def admin_audit(action: str | None = None, ip: str | None = None, search: str | None = None,
                offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                user: User = Depends(require_admin), session: Session = Depends(get_session)):
    statement = select(AuditLog)
    if action: statement = statement.where(AuditLog.action == action)
    if ip: statement = statement.where(AuditLog.ip_address == ip)
    if search: statement = statement.where(AuditLog.details.contains(search) | AuditLog.target_id.contains(search))
    rows = session.exec(statement.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)).all()
    return rows


@app.get("/api/v1/admin/security/failed-logins")
def failed_logins(user: User = Depends(require_admin), session: Session = Depends(get_session)):
    since = now() - timedelta(days=7)
    rows = session.exec(select(FailedLogin).where(FailedLogin.attempted_at >= since)).all()
    by_ip: dict[str, int] = {}; by_email: dict[str, int] = {}
    for row in rows:
        by_ip[row.ip_address or "unknown"] = by_ip.get(row.ip_address or "unknown", 0) + 1
        by_email[row.email] = by_email.get(row.email, 0) + 1
    return {"total": len(rows), "by_ip": by_ip, "by_account": by_email}


@app.get("/api/v1/admin/export/{kind}")
def export_csv(kind: Literal["users", "complaints", "activity"], user: User = Depends(require_admin), session: Session = Depends(get_session)):
    output = io.StringIO()
    writer = csv.writer(output)
    if kind == "users":
        writer.writerow(["id", "email", "name", "role", "is_banned", "created_at"])
        for x in session.exec(select(User).order_by(User.created_at.desc())).all():
            writer.writerow([x.id, x.email, x.name, x.role, x.is_banned, x.created_at.isoformat()])
    elif kind == "complaints":
        writer.writerow(["id", "owner_id", "title", "category", "status", "created_at"])
        for x in session.exec(select(Complaint).order_by(Complaint.created_at.desc())).all():
            writer.writerow([x.id, x.owner_id, x.title, x.category, x.status, x.created_at.isoformat()])
    else:
        writer.writerow(["id", "actor_id", "action", "target_type", "target_id", "ip_address", "created_at"])
        for x in session.exec(select(AuditLog).order_by(AuditLog.created_at.desc())).all():
            writer.writerow([x.id, x.actor_id, x.action, x.target_type, x.target_id, x.ip_address, x.created_at.isoformat()])
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="campuscare-{kind}.csv"'})


@app.post("/api/v1/groups", status_code=201)
def create_group(payload: GroupCreate, user: User = Depends(current_user), session: Session = Depends(get_session)):
    group = CampusGroup(name=payload.name.strip(), description=payload.description.strip(), owner_id=user.id)
    session.add(group); session.commit(); session.refresh(group)
    session.add(GroupMember(group_id=group.id, user_id=user.id, can_create=True, can_edit=True, can_assign=True))
    session.commit()
    return group


@app.get("/api/v1/groups")
def list_groups(user: User = Depends(current_user), session: Session = Depends(get_session)):
    memberships = session.exec(select(GroupMember).where(GroupMember.user_id == user.id)).all()
    ids = [x.group_id for x in memberships]
    if not ids: return []
    return session.exec(select(CampusGroup).where(CampusGroup.id.in_(ids))).all()


@app.patch("/api/v1/groups/{group_id}")
def rename_group(group_id: str, payload: GroupCreate, user: User = Depends(current_user), session: Session = Depends(get_session)):
    group = session.get(CampusGroup, group_id)
    if not group: raise HTTPException(404, "Group not found")
    if group.owner_id != user.id: raise HTTPException(403, "Only the group owner can rename it")
    group.name = payload.name.strip(); group.description = payload.description.strip()
    session.add(group); session.commit(); session.refresh(group)
    return group


@app.delete("/api/v1/groups/{group_id}", status_code=204)
def delete_group(group_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    group = session.get(CampusGroup, group_id)
    if not group: raise HTTPException(404, "Group not found")
    if group.owner_id != user.id: raise HTTPException(403, "Only the group owner can delete it")
    for row in session.exec(select(GroupRecord).where(GroupRecord.group_id == group_id)).all(): session.delete(row)
    for row in session.exec(select(GroupMember).where(GroupMember.group_id == group_id)).all(): session.delete(row)
    session.delete(group); session.commit()
    return Response(status_code=204)


@app.put("/api/v1/groups/{group_id}/members/{member_id}")
def set_member_permissions(group_id: str, member_id: str, payload: MemberPermissions, user: User = Depends(current_user), session: Session = Depends(get_session)):
    group = session.get(CampusGroup, group_id)
    if not group: raise HTTPException(404, "Group not found")
    if group.owner_id != user.id: raise HTTPException(403, "Only the group owner can manage members")
    target = session.get(User, member_id)
    if not target: raise HTTPException(404, "User not found")
    membership = member_for(session, group_id, member_id)
    if not membership:
        membership = GroupMember(group_id=group_id, user_id=member_id)
    membership.can_create = payload.can_create; membership.can_edit = payload.can_edit; membership.can_assign = payload.can_assign
    session.add(membership); session.commit()
    return membership


@app.delete("/api/v1/groups/{group_id}/members/{member_id}", status_code=204)
def remove_member(group_id: str, member_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    group = session.get(CampusGroup, group_id)
    if not group: raise HTTPException(404, "Group not found")
    if group.owner_id != user.id: raise HTTPException(403, "Only the group owner can manage members")
    membership = member_for(session, group_id, member_id)
    if not membership: raise HTTPException(404, "Member not found")
    if member_id == group.owner_id: raise HTTPException(400, "The owner cannot be removed")
    session.delete(membership); session.commit()
    return Response(status_code=204)


@app.post("/api/v1/groups/{group_id}/records", status_code=201)
def create_group_record(group_id: str, payload: GroupRecordCreate, user: User = Depends(current_user), session: Session = Depends(get_session)):
    group = session.get(CampusGroup, group_id); membership = member_for(session, group_id, user.id)
    if not group or not membership: raise HTTPException(404, "Group not found")
    if not membership.can_create and group.owner_id != user.id: raise HTTPException(403, "Group create permission required")
    item = GroupRecord(group_id=group_id, created_by=user.id, title=payload.title.strip(), content=payload.content.strip())
    session.add(item); session.commit(); session.refresh(item)
    return item


@app.get("/api/v1/groups/{group_id}/records")
def list_group_records(group_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    group = session.get(CampusGroup, group_id); membership = member_for(session, group_id, user.id)
    if not group or not membership: raise HTTPException(404, "Group not found")
    return session.exec(select(GroupRecord).where(GroupRecord.group_id == group_id).order_by(GroupRecord.created_at.desc())).all()


@app.patch("/api/v1/groups/{group_id}/records/{record_id}")
def update_group_record(group_id: str, record_id: int, payload: GroupRecordUpdate, user: User = Depends(current_user), session: Session = Depends(get_session)):
    group = session.get(CampusGroup, group_id); membership = member_for(session, group_id, user.id)
    item = session.get(GroupRecord, record_id)
    if not group or not membership or not item or item.group_id != group_id: raise HTTPException(404, "Record not found")
    if not membership.can_edit and group.owner_id != user.id: raise HTTPException(403, "Group edit permission required")
    changes = payload.model_dump(exclude_unset=True)
    if "assignee_id" in changes:
        if not membership.can_assign and group.owner_id != user.id: raise HTTPException(403, "Group assign permission required")
        if changes["assignee_id"] and not member_for(session, group_id, changes["assignee_id"]): raise HTTPException(400, "Assignee must be a group member")
    for key, value in changes.items():
        if value is not None and isinstance(value, str): value = value.strip()
        setattr(item, key, value)
    item.updated_at = now(); session.add(item); session.commit(); session.refresh(item)
    return item


@app.get("/api/v1/admin/groups")
def admin_groups(user: User = Depends(require_admin), session: Session = Depends(get_session)):
    return session.exec(select(CampusGroup).order_by(CampusGroup.created_at.desc())).all()


@app.get("/api/v1/admin/users/{target_id}")
def admin_user_detail(target_id: str, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    target = session.get(User, target_id)
    if not target: raise HTTPException(404, "User not found")
    records = session.exec(select(Complaint).where(Complaint.owner_id == target_id)).all()
    memberships = session.exec(select(GroupMember).where(GroupMember.user_id == target_id)).all()
    sessions = session.exec(select(RefreshSession).where(RefreshSession.user_id == target_id).order_by(RefreshSession.created_at.desc())).all()
    activity = session.exec(select(AuditLog).where(AuditLog.actor_id == target_id).order_by(AuditLog.created_at.desc()).limit(20)).all()
    return {"user": {"id": target.id, "email": target.email, "name": target.name, "role": target.role, "is_banned": target.is_banned, "ban_reason": target.ban_reason, "created_at": target.created_at},
            "complaints": records, "groups": memberships, "sessions": sessions, "activity": activity}


@app.delete("/api/v1/admin/groups/{group_id}", status_code=204)
def admin_delete_group(group_id: str, request: Request, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    group = session.get(CampusGroup, group_id)
    if not group: raise HTTPException(404, "Group not found")
    for row in session.exec(select(GroupRecord).where(GroupRecord.group_id == group_id)).all(): session.delete(row)
    for row in session.exec(select(GroupMember).where(GroupMember.group_id == group_id)).all(): session.delete(row)
    session.delete(group); audit(session, request, "group_deleted", user.id, "group", group_id); session.commit()
    return Response(status_code=204)



@app.get("/api/v1/groups/{group_id}/members")
def list_group_members(group_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    group = session.get(CampusGroup, group_id)
    if not group or not member_for(session, group_id, user.id):
        raise HTTPException(404, "Group not found")
    members = session.exec(select(GroupMember).where(GroupMember.group_id == group_id)).all()
    result = []
    for member in members:
        person = session.get(User, member.user_id)
        if person:
            result.append({"user_id": person.id, "name": person.name, "email": person.email,
                           "can_create": member.can_create, "can_edit": member.can_edit, "can_assign": member.can_assign})
    return result


@app.post("/api/v1/groups/{group_id}/members/{member_id}", status_code=201)
def add_group_member(group_id: str, member_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    group = session.get(CampusGroup, group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    if group.owner_id != user.id:
        raise HTTPException(403, "Only the group owner can manage members")
    target = session.get(User, member_id)
    if not target:
        raise HTTPException(404, "User not found")
    if member_for(session, group_id, member_id):
        raise HTTPException(409, "User is already a group member")
    membership = GroupMember(group_id=group_id, user_id=member_id)
    session.add(membership)
    session.commit()
    return {"group_id": group_id, "user_id": member_id, "can_create": False, "can_edit": False, "can_assign": False}


@app.post("/api/v1/admin/users/bulk-ban")
def bulk_ban_users(payload: dict, request: Request, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    ids = payload.get("user_ids", [])
    reason = str(payload.get("reason", "Bulk administrative moderation")).strip()
    if not isinstance(ids, list) or len(ids) > 100 or len(reason) < 3:
        raise HTTPException(422, "Provide up to 100 user IDs and a reason")
    changed = 0
    for target_id in set(ids):
        if target_id == user.id:
            continue
        target = session.get(User, str(target_id))
        if not target or target.role == "admin":
            continue
        target.is_banned = True
        target.ban_reason = reason[:500]
        session.add(target)
        for active in session.exec(select(RefreshSession).where(RefreshSession.user_id == target.id, RefreshSession.revoked_at == None)).all():
            active.revoked_at = now()
            session.add(active)
        audit(session, request, "user_banned", user.id, "user", target.id, reason[:500])
        changed += 1
    session.commit()
    return {"updated": changed}


@app.post("/api/v1/admin/users/bulk-unban")
def bulk_unban_users(payload: dict, request: Request, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    ids = payload.get("user_ids", [])
    if not isinstance(ids, list) or len(ids) > 100:
        raise HTTPException(422, "Provide up to 100 user IDs")
    changed = 0
    for target_id in set(ids):
        target = session.get(User, str(target_id))
        if target and target.is_banned:
            target.is_banned = False
            target.ban_reason = None
            session.add(target)
            audit(session, request, "user_unbanned", user.id, "user", target.id)
            changed += 1
    session.commit()
    return {"updated": changed}


@app.post("/api/v1/admin/complaints/bulk-delete")
def bulk_delete_complaints(payload: dict, request: Request, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    ids = payload.get("complaint_ids", [])
    if not isinstance(ids, list) or len(ids) > 100:
        raise HTTPException(422, "Provide up to 100 complaint IDs")
    deleted = 0
    for complaint_id in set(ids):
        item = session.get(Complaint, complaint_id)
        if item:
            audit(session, request, "complaint_deleted", user.id, "complaint", str(item.id))
            session.delete(item)
            deleted += 1
    session.commit()
    return {"deleted": deleted}


@app.post("/api/v1/admin/sessions/{session_id}/revoke", status_code=204)
def admin_revoke_session(session_id: str, request: Request, user: User = Depends(require_admin), session: Session = Depends(get_session)):
    item = session.get(RefreshSession, session_id)
    if not item:
        raise HTTPException(404, "Session not found")
    item.revoked_at = now()
    session.add(item)
    audit(session, request, "session_revoked_by_admin", user.id, "session", session_id)
    session.commit()
    return Response(status_code=204)
