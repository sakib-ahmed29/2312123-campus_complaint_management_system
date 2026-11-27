"""Application entrypoint (`main:app`, used by Vercel and `fastapi dev main.py`).

The implementation lives in the `campuscare` package:
  config / database / models / schemas   settings, engine, tables, request payloads
  security / audit / validation          auth, RBAC permissions, audit log, input checks
  routers/*                              one module per feature area
"""
from campuscare.app import create_app

app = create_app()
