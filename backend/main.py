from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from sqlmodel import Field, Session, SQLModel, create_engine, select


Category = Literal["academic", "hostel", "library", "cafeteria", "transport", "it_network", "other"]
Status = Literal["pending", "in_progress", "resolved", "rejected"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Complaint(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(min_length=5, max_length=100)
    description: str = Field(min_length=10, max_length=2000)
    category: str = Field(max_length=20, index=True)
    status: str = Field(default="pending", max_length=15, index=True)
    admin_response: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class ComplaintCreate(SQLModel):
    title: str = Field(min_length=5, max_length=100)
    description: str = Field(min_length=10, max_length=2000)
    category: Category

    def normalized(self):
        self.title = self.title.strip()
        self.description = self.description.strip()
        if len(self.title) < 5 or len(self.description) < 10:
            raise HTTPException(status_code=422, detail="Title must contain at least 5 characters and description at least 10.")
        return self


class ComplaintUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=5, max_length=100)
    description: str | None = Field(default=None, min_length=10, max_length=2000)
    category: Category | None = None


class StatusUpdate(SQLModel):
    status: Status
    admin_response: str | None = Field(default=None, max_length=1000)


class ComplaintRead(SQLModel):
    id: int
    title: str
    description: str
    category: str
    status: str
    admin_response: str | None
    created_at: datetime
    updated_at: datetime


database_url = os.getenv("DATABASE_URL")
if not database_url:
    db_file = Path("/tmp/ccms.db") if os.getenv("VERCEL") else Path(__file__).resolve().parent / "ccms.db"
    database_url = f"sqlite:///{db_file}"
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args, echo=False)


def get_session():
    with Session(engine) as session:
        yield session


@asynccontextmanager
async def lifespan(_: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(
    title="Campus Complaint Management System API",
    description="MVP REST API for submitting and managing campus complaints.",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}


@app.post("/api/v1/complaints", response_model=ComplaintRead, status_code=201, tags=["complaints"])
def create_complaint(payload: ComplaintCreate, session: Session = Depends(get_session)):
    payload.normalized()
    complaint = Complaint(**payload.model_dump())
    session.add(complaint)
    session.commit()
    session.refresh(complaint)
    return complaint


@app.get("/api/v1/complaints", response_model=list[ComplaintRead], tags=["complaints"])
def list_complaints(
    status: Status | None = None,
    category: Category | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    statement = select(Complaint)
    if status:
        statement = statement.where(Complaint.status == status)
    if category:
        statement = statement.where(Complaint.category == category)
    statement = statement.order_by(Complaint.created_at.desc()).offset(offset).limit(limit)
    return session.exec(statement).all()


@app.get("/api/v1/complaints/{complaint_id}", response_model=ComplaintRead, tags=["complaints"])
def get_complaint(complaint_id: int, session: Session = Depends(get_session)):
    complaint = session.get(Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


@app.patch("/api/v1/complaints/{complaint_id}", response_model=ComplaintRead, tags=["complaints"])
def update_complaint(complaint_id: int, payload: ComplaintUpdate, session: Session = Depends(get_session)):
    complaint = session.get(Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if complaint.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending complaints can be edited")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to update")
    for key in ("title", "description"):
        if key in changes and changes[key] is not None:
            changes[key] = changes[key].strip()
            minimum = 5 if key == "title" else 10
            if len(changes[key]) < minimum:
                raise HTTPException(status_code=422, detail=f"{key.capitalize()} must contain at least {minimum} characters")
    for key, value in changes.items():
        setattr(complaint, key, value)
    complaint.updated_at = utc_now()
    session.add(complaint)
    session.commit()
    session.refresh(complaint)
    return complaint


@app.delete("/api/v1/complaints/{complaint_id}", status_code=204, tags=["complaints"])
def delete_complaint(complaint_id: int, session: Session = Depends(get_session)):
    complaint = session.get(Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if complaint.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending complaints can be deleted")
    session.delete(complaint)
    session.commit()
    return Response(status_code=204)


ALLOWED_STATUS_CHANGES = {
    "pending": {"in_progress", "rejected"},
    "in_progress": {"resolved", "rejected"},
    "resolved": set(),
    "rejected": set(),
}


@app.patch("/api/v1/complaints/{complaint_id}/status", response_model=ComplaintRead, tags=["complaints"])
def update_complaint_status(complaint_id: int, payload: StatusUpdate, session: Session = Depends(get_session)):
    complaint = session.get(Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if payload.status not in ALLOWED_STATUS_CHANGES[complaint.status]:
        raise HTTPException(status_code=409, detail=f"Cannot change status from {complaint.status} to {payload.status}")
    complaint.status = payload.status
    if payload.admin_response is not None:
        complaint.admin_response = payload.admin_response.strip() or None
    complaint.updated_at = utc_now()
    session.add(complaint)
    session.commit()
    session.refresh(complaint)
    return complaint
