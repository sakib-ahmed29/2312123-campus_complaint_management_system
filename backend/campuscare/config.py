"""Environment-driven settings."""
from __future__ import annotations

import os

JWT_SECRET = os.getenv("JWT_SECRET", "LOCAL-ONLY-change-this-secret-before-deployment")
PASSWORD_PEPPER = os.getenv("PASSWORD_PEPPER", "")
ACCESS_MINUTES = min(max(int(os.getenv("ACCESS_TOKEN_MINUTES", "15")), 1), 15)
REFRESH_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
COOKIE_NAME = "campuscare_refresh"

# CORS is limited to the deployed frontend origin(s). The frontend normally calls the API
# through the same origin (Vercel rewrites), so this only matters for cross-origin clients.
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
