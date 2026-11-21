from __future__ import annotations

import csv
import hashlib
import hmac
import io
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Annotated, Literal

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import func
from sqlalchemy.pool import NullPool
from sqlmodel import Field, Session, SQLModel, create_engine, select


def now() -> datetime:
    return datetime.now(timezone.utc)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{'/tmp/ccms.db' if os.getenv('VERCEL') else 'ccms.db'}"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
IS_SQLITE = DATABASE_URL.startswith("sqlite")
engine_args = {"connect_args": {"check_same_thread": False} if IS_SQLITE else {"prepare_threshold": None}}
if not IS_SQLITE:
    engine_args["poolclass"] = NullPool
engine = create_engine(DATABASE_URL, **engine_args)

JWT_SECRET = os.getenv("JWT_SECRET", "LOCAL-ONLY-change-this-secret-before-deployment")
PASSWORD_PEPPER = os.getenv("PASSWORD_PEPPER", "")
ACCESS_MINUTES = min(max(int(os.getenv("ACCESS_TOKEN_MINUTES", "15")), 1), 15)
REFRESH_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
COOKIE_NAME = "campuscare_refresh"
password_hasher = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)

Role = Literal["user", "admin"]
Category = Literal["academic", "hostel", "library", "cafeteria", "transport", "it_network", "other"]
Status = Literal["pending", "in_progress", "resolved", "rejected"]


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=254)
    full_name: str = Field(max_length=100)
    password_hash: str
    role: str = Field(default="user", index=True, max_length=10)
    is_banned: bool = Field(default=False, index=True)
    token_version: int = 0
    ban_reason: str | None = None
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


def get_session():
    with Session(engine) as session:
        yield session


def password_input(password: str) -> str:
    return hmac.new(PASSWORD_PEPPER.encode(), password.encode(), hashlib.sha256).hexdigest()


def hash_password(password: str) -> str:
    return password_hasher.hash(password_input(password))


def verify_password(password: str, hashed: str) -> bool:
    return password_hasher.verify(password_input(password), hashed)


def scopes_for(role: str) -> set[str]:
    if role == "admin":
        return {"profile:manage", "complaint:read:all", "complaint:delete:any", "complaint:status",
                "user:read", "user:role", "user:ban", "stats:read", "audit:read", "content:moderate"}
    return {"profile:manage", "complaint:create", "complaint:read:own", "complaint:update:own", "complaint:delete:own"}


def make_access(user: User) -> str:
    issued = now()
    return jwt.encode({"sub": str(user.id), "role": user.role, "iat": issued,
                       "exp": issued + timedelta(minutes=ACCESS_MINUTES),
                       "jti": secrets.token_hex(12), "ver": user.token_version}, JWT_SECRET, algorithm="HS256")


def issue_refresh(session: Session, user: User, request: Request, response: Response) -> None:
    raw = secrets.token_urlsafe(48)
    row = RefreshSession(user_id=user.id, token_hash=digest(raw),
                         expires_at=now() + timedelta(days=REFRESH_DAYS),
                         ip_address=client_ip(request),
                         user_agent=request.headers.get("user-agent"))
    session.add(row)
    response.set_cookie(COOKIE_NAME, raw, httponly=True, secure=COOKIE_SECURE,
                        samesite="lax", path="/api/v1/auth", max_age=REFRESH_DAYS * 86400)


def log_event(session: Session, request: Request, event: str, user_id: int | None = None,
              target_type: str | None = None, target_id: str | None = None, detail: str | None = None):
    session.add(AuditEvent(user_id=user_id, event=event, target_type=target_type, target_id=target_id,
                           detail=detail, ip_address=request.client.host if request.client else None,
                           user_agent=request.headers.get("user-agent")))


def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
                 session: Annotated[Session, Depends(get_session)]) -> User:
    if not credentials:
        raise HTTPException(401, "Authentication required")
    try:
        claims = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Invalid or expired access token")
    user = session.get(User, user_id)
    if not user or user.is_banned or claims.get("ver", 0) != user.token_version:
        raise HTTPException(401, "Session is not valid")
    return user


def require_role(*roles: str):
    def dependency(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Insufficient permissions")
        return user
    return dependency


def owned_complaint(complaint_id: int, user: User, session: Session, admin_allowed: bool = False) -> Complaint:
    item = session.get(Complaint, complaint_id)
    if not item or (item.owner_id != user.id and not (admin_allowed and user.role == "admin")):
        raise HTTPException(404, "Complaint not found")
    return item


@asynccontextmanager
async def lifespan(_: FastAPI):
    SQLModel.metadata.create_all(engine)
    # Upgrade the original MVP complaint table without destroying existing records.
    from sqlalchemy import inspect, text
    columns = {column["name"] for column in inspect(engine).get_columns("complaint")}
    if "owner_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE complaint ADD COLUMN owner_id INTEGER REFERENCES "user"(id)'))
    if os.getenv("VERCEL") and (not os.getenv("DATABASE_URL") or not os.getenv("JWT_SECRET") or not os.getenv("PASSWORD_PEPPER")):
        raise RuntimeError("DATABASE_URL, JWT_SECRET and PASSWORD_PEPPER must be configured in Vercel")
    yield


app = FastAPI(title="CampusCare API", version="1.0.0", docs_url="/api/docs",
               openapi_url="/api/openapi.json", redoc_url=None, lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/auth/signup", status_code=201)
def signup(payload: Signup, request: Request, session: Annotated[Session, Depends(get_session)]):
    email = payload.email.strip().lower()
    if len(payload.password) < 8 or not any(c.isalpha() for c in payload.password) or not any(c.isdigit() for c in payload.password):
        raise HTTPException(422, "Password must contain at least 8 characters, one letter and one number")
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(409, "Email is already registered")
    user = User(email=email, full_name=payload.full_name.strip(), password_hash=hash_password(payload.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    log_event(session, request, "signup", user.id)
    session.commit()
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}


@app.post("/api/v1/auth/login")
def login(payload: Login, request: Request, response: Response, session: Annotated[Session, Depends(get_session)]):
    email = payload.email.strip().lower()
    ip = client_ip(request)
    cutoff = now() - timedelta(minutes=15)
    attempts = session.exec(select(LoginAttempt).where(LoginAttempt.email_key == email,
        LoginAttempt.ip_address == ip, LoginAttempt.created_at >= cutoff, LoginAttempt.succeeded == False)).all()
    if len(attempts) >= 8:
        raise HTTPException(429, "Too many failed login attempts. Try again in 15 minutes.")
    user = session.exec(select(User).where(User.email == email)).first()
    valid = bool(user and verify_password(payload.password, user.password_hash))
    session.add(LoginAttempt(email_key=email, ip_address=ip, succeeded=valid))
    if not valid or not user or user.is_banned:
        log_event(session, request, "failed_login", user.id if user else None, detail="Invalid credentials or banned account")
        session.commit()
        raise HTTPException(401, "Invalid email or password")
    log_event(session, request, "login", user.id)
    issue_refresh(session, user, request, response)
    session.commit()
    return {"access_token": make_access(user), "token_type": "bearer", "expires_in": ACCESS_MINUTES * 60,
            "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}}


@app.post("/api/v1/auth/refresh")
def refresh(request: Request, response: Response, session: Annotated[Session, Depends(get_session)]):
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        raise HTTPException(401, "Refresh session missing")
    old = session.exec(select(RefreshSession).where(RefreshSession.token_hash == digest(raw))).first()
    if not old or old.revoked_at or old.expires_at < now():
        if old and old.revoked_at:
            for token in session.exec(select(RefreshSession).where(RefreshSession.user_id == old.user_id, RefreshSession.revoked_at == None)).all():
                token.revoked_at = now()
        response.delete_cookie(COOKIE_NAME, path="/api/v1/auth")
        session.commit()
        raise HTTPException(401, "Refresh session expired or revoked")
    user = session.get(User, old.user_id)
    if not user or user.is_banned:
        raise HTTPException(401, "Account is unavailable")
    old.revoked_at = now()
    issue_refresh(session, user, request, response)
    session.commit()
    return {"access_token": make_access(user), "token_type": "bearer", "expires_in": ACCESS_MINUTES * 60}


@app.post("/api/v1/auth/logout", status_code=204)
def logout(request: Request, response: Response, session: Annotated[Session, Depends(get_session)],
           user: Annotated[User, Depends(current_user)]):
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        token = session.exec(select(RefreshSession).where(RefreshSession.token_hash == digest(raw))).first()
        if token and token.user_id == user.id:
            token.revoked_at = now()
    user.token_version += 1
    session.add(user)
    log_event(session, request, "logout", user.id)
    session.commit()
    response.delete_cookie(COOKIE_NAME, path="/api/v1/auth")
    response.status_code = 204
    return response


@app.get("/api/v1/auth/sessions")
def list_sessions(user: Annotated[User, Depends(current_user)], session: Annotated[Session, Depends(get_session)]):
    rows = session.exec(select(RefreshSession).where(RefreshSession.user_id == user.id,
        RefreshSession.revoked_at == None, RefreshSession.expires_at > now())).all()
    return [{"id": r.id, "created_at": r.created_at, "expires_at": r.expires_at,
             "ip_address": r.ip_address, "user_agent": r.user_agent} for r in rows]


@app.delete("/api/v1/auth/sessions/{session_id}", status_code=204)
def revoke_session(session_id: int, user: Annotated[User, Depends(current_user)],
                   session: Annotated[Session, Depends(get_session)]):
    row = session.get(RefreshSession, session_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Session not found")
    row.revoked_at = now()
    user.token_version += 1
    session.add(user)
    session.commit()
    return Response(status_code=204)


@app.get("/api/v1/users/me")
def get_profile(user: Annotated[User, Depends(current_user)]):
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role,
            "created_at": user.created_at}


@app.patch("/api/v1/users/me")
def update_profile(payload: ProfileUpdate, request: Request, user: Annotated[User, Depends(current_user)],
                   session: Annotated[Session, Depends(get_session)]):
    email = payload.email.strip().lower()
    existing = session.exec(select(User).where(User.email == email, User.id != user.id)).first()
    if existing:
        raise HTTPException(409, "Email already in use")
    user.email, user.full_name, user.updated_at = email, payload.full_name.strip(), now()
    session.add(user)
    log_event(session, request, "profile_update", user.id)
    session.commit()
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}


@app.post("/api/v1/users/me/password", status_code=204)
def change_password(payload: PasswordChange, request: Request, response: Response,
                    user: Annotated[User, Depends(current_user)], session: Annotated[Session, Depends(get_session)]):
    if not verify_password(payload.current_password, user.password_hash):
        log_event(session, request, "failed_password_change", user.id)
        session.commit()
        raise HTTPException(400, "Current password is incorrect")
    if len(payload.new_password) < 8 or not any(c.isalpha() for c in payload.new_password) or not any(c.isdigit() for c in payload.new_password):
        raise HTTPException(422, "New password must contain a letter and a number")
    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1
    session.add(user)
    for token in session.exec(select(RefreshSession).where(RefreshSession.user_id == user.id, RefreshSession.revoked_at == None)).all():
        token.revoked_at = now()
    log_event(session, request, "password_change", user.id)
    session.commit()
    response.delete_cookie(COOKIE_NAME, path="/api/v1/auth")
    return Response(status_code=204)


@app.post("/api/v1/complaints", status_code=201)
def create_complaint(payload: ComplaintCreate, request: Request, user: Annotated[User, Depends(require_role("user"))],
                     session: Annotated[Session, Depends(get_session)]):
    item = Complaint(owner_id=user.id, title=payload.title.strip(), description=payload.description.strip(),
                     category=payload.category)
    session.add(item)
    session.commit()
    session.refresh(item)
    log_event(session, request, "complaint_create", user.id, "complaint", str(item.id))
    session.commit()
    return complaint_out(item)


@app.get("/api/v1/complaints")
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


@app.get("/api/v1/complaints/{complaint_id}")
def get_complaint(complaint_id: int, user: Annotated[User, Depends(current_user)],
                  session: Annotated[Session, Depends(get_session)]):
    return complaint_out(owned_complaint(complaint_id, user, session, admin_allowed=True))


@app.patch("/api/v1/complaints/{complaint_id}")
def update_complaint(complaint_id: int, payload: ComplaintUpdate, user: Annotated[User, Depends(require_role("user"))],
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


@app.delete("/api/v1/complaints/{complaint_id}", status_code=204)
def delete_complaint(complaint_id: int, request: Request, user: Annotated[User, Depends(current_user)],
                     session: Annotated[Session, Depends(get_session)]):
    item = owned_complaint(complaint_id, user, session, admin_allowed=True)
    if item.status != "pending" and user.role != "admin":
        raise HTTPException(409, "Only pending complaints can be deleted")
    log_event(session, request, "complaint_delete", user.id, "complaint", str(item.id))
    session.delete(item)
    session.commit()
    return Response(status_code=204)


ALLOWED_STATUS_CHANGES = {"pending": {"in_progress", "rejected"}, "in_progress": {"resolved", "rejected"},
                          "resolved": set(), "rejected": set()}


@app.patch("/api/v1/complaints/{complaint_id}/status")
def update_complaint_status(complaint_id: int, payload: StatusUpdate, request: Request,
                            user: Annotated[User, Depends(require_role("admin"))],
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


@app.get("/api/v1/users/me/dashboard")
def user_dashboard(user: Annotated[User, Depends(current_user)], session: Annotated[Session, Depends(get_session)]):
    rows = session.exec(select(Complaint.status, func.count()).where(Complaint.owner_id == user.id).group_by(Complaint.status)).all()
    return {"user": {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role},
            "complaints": {s: n for s, n in rows}}


@app.get("/api/v1/admin/stats")
def admin_stats(admin: Annotated[User, Depends(require_role("admin"))], session: Annotated[Session, Depends(get_session)]):
    week = now() - timedelta(days=7)
    count_users = session.exec(select(func.count()).select_from(User)).one()
    count_banned = session.exec(select(func.count()).select_from(User).where(User.is_banned == True)).one()
    count_records = session.exec(select(func.count()).select_from(Complaint)).one()
    count_groups = session.exec(select(func.count()).select_from(Group)).one()
    count_new = session.exec(select(func.count()).select_from(User).where(User.created_at >= week)).one()
    new_records = session.exec(select(func.count()).select_from(Complaint).where(Complaint.created_at >= week)).one()
    new_groups = session.exec(select(func.count()).select_from(Group).where(Group.created_at >= week)).one()
    return {"users": count_users, "banned_users": count_banned, "records": count_records,
            "groups": count_groups, "new_users_last_7_days": count_new,
            "new_records_last_7_days": new_records, "new_groups_last_7_days": new_groups}


@app.get("/api/v1/admin/users")
def admin_users(admin: Annotated[User, Depends(require_role("admin"))],
                session: Annotated[Session, Depends(get_session)], q: str = "", role: str | None = None,
                status: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    statement = select(User)
    if q:
        statement = statement.where(User.email.contains(q.lower()) | User.full_name.contains(q))
    if role in ("user", "admin"):
        statement = statement.where(User.role == role)
    if status == "banned":
        statement = statement.where(User.is_banned == True)
    elif status == "active":
        statement = statement.where(User.is_banned == False)
    rows = session.exec(statement.order_by(User.created_at.desc()).offset(offset).limit(limit)).all()
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role,
             "is_banned": u.is_banned, "ban_reason": u.ban_reason, "created_at": u.created_at} for u in rows]


@app.get("/api/v1/admin/users/{user_id}")
def admin_user_detail(user_id: int, admin: Annotated[User, Depends(require_role("admin"))],
                      session: Annotated[Session, Depends(get_session)]):
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    complaints = session.exec(select(Complaint).where(Complaint.owner_id == user_id)).all()
    groups = session.exec(select(Group).join(GroupMember, Group.id == GroupMember.group_id).where(GroupMember.user_id == user_id)).all()
    sessions = session.exec(select(RefreshSession).where(RefreshSession.user_id == user_id)).all()
    activity = session.exec(select(AuditEvent).where(AuditEvent.user_id == user_id).order_by(AuditEvent.created_at.desc()).limit(30)).all()
    return {"user": {"id": target.id, "email": target.email, "full_name": target.full_name, "role": target.role,
                     "is_banned": target.is_banned, "created_at": target.created_at},
            "complaints": [complaint_out(x) for x in complaints],
            "groups": [group_out(x) for x in groups],
            "sessions": [{"id": x.id, "created_at": x.created_at, "revoked_at": x.revoked_at} for x in sessions],
            "activity": [audit_out(x) for x in activity]}


@app.patch("/api/v1/admin/users/{user_id}/role")
def admin_change_role(user_id: int, payload: RoleChange, request: Request,
                      admin: Annotated[User, Depends(require_role("admin"))], session: Annotated[Session, Depends(get_session)]):
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


@app.post("/api/v1/admin/users/{user_id}/ban")
def admin_ban_user(user_id: int, payload: BanRequest, request: Request,
                   admin: Annotated[User, Depends(require_role("admin"))], session: Annotated[Session, Depends(get_session)]):
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


@app.post("/api/v1/admin/users/{user_id}/unban")
def admin_unban_user(user_id: int, payload: UnbanRequest, request: Request, admin: Annotated[User, Depends(require_role("admin"))],
                     session: Annotated[Session, Depends(get_session)]):
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    target.is_banned, target.ban_reason = False, None
    log_event(session, request, "user_unbanned", admin.id, "user", str(user_id), payload.reason)
    session.commit()
    return {"id": target.id, "is_banned": False}


@app.post("/api/v1/admin/users/bulk-ban")
def bulk_ban(payload: list[int], request: Request, admin: Annotated[User, Depends(require_role("admin"))],
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


@app.get("/api/v1/admin/activity")
def admin_activity(admin: Annotated[User, Depends(require_role("admin"))],
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


@app.get("/api/v1/admin/security")
def admin_security(admin: Annotated[User, Depends(require_role("admin"))],
                   session: Annotated[Session, Depends(get_session)]):
    cutoff = now() - timedelta(days=7)
    attempts = session.exec(select(LoginAttempt).where(LoginAttempt.succeeded == False, LoginAttempt.created_at >= cutoff)).all()
    by_ip: dict[str, int] = {}
    by_account: dict[str, int] = {}
    for attempt in attempts:
        by_ip[attempt.ip_address] = by_ip.get(attempt.ip_address, 0) + 1
        by_account[attempt.email_key] = by_account.get(attempt.email_key, 0) + 1
    return {"failed_logins_last_7_days": len(attempts), "by_ip": by_ip, "by_account": by_account}


@app.get("/api/v1/admin/export/{kind}")
def admin_export(kind: str, request: Request, admin: Annotated[User, Depends(require_role("admin"))],
                 session: Annotated[Session, Depends(get_session)], status: str | None = None,
                 role: str | None = None, q: str = "", event: str | None = None):
    output = io.StringIO()
    writer = csv.writer(output)
    if kind == "users":
        writer.writerow(["id", "email", "full_name", "role", "is_banned", "created_at"])
        statement = select(User)
        if role in ("user", "admin"):
            statement = statement.where(User.role == role)
        if q:
            statement = statement.where(User.email.contains(q) | User.full_name.contains(q))
        for u in session.exec(statement).all():
            writer.writerow([u.id, u.email, u.full_name, u.role, u.is_banned, u.created_at.isoformat()])
    elif kind == "records":
        writer.writerow(["id", "owner_id", "title", "category", "status", "created_at"])
        statement = select(Complaint)
        if status:
            statement = statement.where(Complaint.status == status)
        for c in session.exec(statement).all():
            writer.writerow([c.id, c.owner_id, c.title, c.category, c.status, c.created_at.isoformat()])
    elif kind == "activity":
        writer.writerow(["id", "user_id", "event", "ip_address", "user_agent", "created_at"])
        statement = select(AuditEvent)
        if event:
            statement = statement.where(AuditEvent.event == event)
        if q:
            statement = statement.where(AuditEvent.detail.contains(q) | AuditEvent.ip_address.contains(q) | AuditEvent.event.contains(q))
        for a in session.exec(statement).all():
            writer.writerow([a.id, a.user_id, a.event, a.ip_address, a.user_agent, a.created_at.isoformat()])
    else:
        raise HTTPException(404, "Unknown export type")
    log_event(session, request, "data_export", admin.id, kind, detail=f"status={status}; role={role}; event={event}; q={q}")
    session.commit()
    return Response(content=output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="campuscare-{kind}.csv"'})


@app.post("/api/v1/groups", status_code=201)
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


def group_access(group_id: int, user: User, session: Session) -> tuple[Group, GroupMember | None]:
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    member = session.exec(select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == user.id)).first()
    if group.owner_id != user.id and not member:
        raise HTTPException(404, "Group not found")
    return group, member


@app.get("/api/v1/groups")
def list_groups(user: Annotated[User, Depends(current_user)], session: Annotated[Session, Depends(get_session)]):
    return [group_out(g) for g in session.exec(select(Group).join(GroupMember, Group.id == GroupMember.group_id).where(GroupMember.user_id == user.id)).all()]


@app.post("/api/v1/groups/{group_id}/members")
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


@app.patch("/api/v1/groups/{group_id}")
def rename_group(group_id: int, payload: GroupCreate, user: Annotated[User, Depends(current_user)],
                 session: Annotated[Session, Depends(get_session)]):
    group = session.get(Group, group_id)
    if not group or group.owner_id != user.id:
        raise HTTPException(404, "Group not found")
    group.name = payload.name.strip()
    session.add(group)
    session.commit()
    return group_out(group)


@app.delete("/api/v1/groups/{group_id}", status_code=204)
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


@app.get("/api/v1/groups/{group_id}/members")
def group_members(group_id: int, user: Annotated[User, Depends(current_user)],
                  session: Annotated[Session, Depends(get_session)]):
    group, _ = group_access(group_id, user, session)
    members = session.exec(select(GroupMember).where(GroupMember.group_id == group_id)).all()
    return [{"user_id": m.user_id, "can_create": m.can_create, "can_edit": m.can_edit,
             "can_assign": m.can_assign, "is_owner": m.user_id == group.owner_id} for m in members]


@app.post("/api/v1/groups/{group_id}/records", status_code=201)
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


@app.get("/api/v1/groups/{group_id}/records")
def list_group_records(group_id: int, user: Annotated[User, Depends(current_user)],
                       session: Annotated[Session, Depends(get_session)]):
    group_access(group_id, user, session)
    rows = session.exec(select(GroupRecord).where(GroupRecord.group_id == group_id).order_by(GroupRecord.created_at.desc())).all()
    return [record_out(row) for row in rows]


@app.patch("/api/v1/groups/{group_id}/records/{record_id}")
def update_group_record(group_id: int, record_id: int, payload: GroupRecordUpdate,
                        user: Annotated[User, Depends(current_user)], session: Annotated[Session, Depends(get_session)]):
    group, member = group_access(group_id, user, session)
    record = session.get(GroupRecord, record_id)
    if not record or record.group_id != group_id:
        raise HTTPException(404, "Record not found")
    if group.owner_id != user.id and not member.can_edit:
        raise HTTPException(403, "Group edit permission required")
    changes = payload.model_dump(exclude_unset=True)
    if "assignee_id" in changes and group.owner_id != user.id and not member.can_assign:
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


@app.delete("/api/v1/groups/{group_id}/members/{member_user_id}", status_code=204)
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


@app.post("/api/v1/admin/users/bulk-unban")
def bulk_unban(payload: list[int], request: Request, admin: Annotated[User, Depends(require_role("admin"))],
                session: Annotated[Session, Depends(get_session)], reason: str = Query(min_length=3, max_length=500)):
    updated = []
    for user_id in set(payload):
        target = session.get(User, user_id)
        if target and target.role == "user" and target.is_banned:
            target.is_banned, target.ban_reason = False, None
            log_event(session, request, "user_unbanned", admin.id, "user", str(user_id))
            updated.append(user_id)
    session.commit()
    return {"updated_user_ids": updated}


@app.post("/api/v1/admin/users/{user_id}/revoke-sessions")
def admin_revoke_sessions(user_id: int, request: Request, admin: Annotated[User, Depends(require_role("admin"))],
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


@app.get("/api/v1/admin/records")
def admin_records(admin: Annotated[User, Depends(require_role("admin"))],
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


@app.delete("/api/v1/admin/records/{record_id}", status_code=204)
def admin_delete_record(record_id: int, request: Request,
                        admin: Annotated[User, Depends(require_role("admin"))],
                        session: Annotated[Session, Depends(get_session)]):
    record = session.get(Complaint, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    log_event(session, request, "admin_record_delete", admin.id, "complaint", str(record_id))
    session.delete(record)
    session.commit()
    return Response(status_code=204)


@app.get("/api/v1/admin/groups")
def admin_groups(admin: Annotated[User, Depends(require_role("admin"))],
                 session: Annotated[Session, Depends(get_session)], q: str = ""):
    statement = select(Group)
    if q:
        statement = statement.where(Group.name.contains(q))
    return [group_out(row) for row in session.exec(statement.order_by(Group.created_at.desc())).all()]


@app.delete("/api/v1/admin/groups/{group_id}", status_code=204)
def admin_delete_group(group_id: int, request: Request,
                       admin: Annotated[User, Depends(require_role("admin"))],
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


@app.post("/api/v1/admin/records/bulk-delete")
def admin_bulk_delete_records(payload: list[int], request: Request,
                              admin: Annotated[User, Depends(require_role("admin"))],
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


@app.post("/api/v1/admin/groups/bulk-delete")
def admin_bulk_delete_groups(payload: list[int], request: Request,
                             admin: Annotated[User, Depends(require_role("admin"))],
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
