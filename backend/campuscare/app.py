"""FastAPI application factory."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlmodel import SQLModel

from campuscare.config import ALLOWED_ORIGINS
from campuscare.database import engine
from campuscare import models  # noqa: F401  (registers tables on SQLModel.metadata)
from campuscare.errors import register_error_handlers
from campuscare.routers import (admin_content, admin_reports, admin_users, auth, complaints,
                                groups, health, users)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("VERCEL") and not (os.getenv("DATABASE_URL") and os.getenv("JWT_SECRET") and os.getenv("PASSWORD_PEPPER")):
        raise RuntimeError("DATABASE_URL, JWT_SECRET and PASSWORD_PEPPER must be configured in Vercel")
    SQLModel.metadata.create_all(engine)
    # Upgrade the original MVP complaint table without destroying existing records.
    columns = {column["name"] for column in inspect(engine).get_columns("complaint")}
    if "owner_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE complaint ADD COLUMN owner_id INTEGER REFERENCES "user"(id)'))
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="CampusCare API", version="1.0.0", docs_url="/api/docs",
                  openapi_url="/api/openapi.json", redoc_url=None, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type"])
    register_error_handlers(app)
    for module in (health, auth, users, complaints, groups, admin_users, admin_content, admin_reports):
        app.include_router(module.router)
    return app
