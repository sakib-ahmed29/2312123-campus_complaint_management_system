"""Database engine and session dependency."""
from __future__ import annotations

import os

from sqlalchemy.pool import NullPool
from sqlmodel import Session, create_engine

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


def get_session():
    with Session(engine) as session:
        yield session
