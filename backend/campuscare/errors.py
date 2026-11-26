"""Consistent JSON error responses; no stack traces or internals reach the client."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError):
        # One consistent error shape: {"detail": "<message>"}; never echo internals.
        parts = []
        for error in exc.errors()[:5]:
            field = ".".join(str(p) for p in error.get("loc", ()) if p not in ("body", "query", "path"))
            parts.append(f"{field}: {error.get('msg')}" if field else str(error.get("msg")))
        return JSONResponse(status_code=422, content={"detail": "; ".join(parts) or "Invalid request"})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, __: Exception):
        # No stack traces or internal messages are ever sent to the client.
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
