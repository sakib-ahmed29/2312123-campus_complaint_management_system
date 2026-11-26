"""Shared input validation helpers."""
from __future__ import annotations

import re

from fastapi import HTTPException

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.match(email):
        raise HTTPException(422, "Enter a valid email address")
    return email
