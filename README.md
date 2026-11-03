# CampusCare — Campus Complaint Management System

CampusCare is a campus issue-reporting MVP built with **React + TypeScript**, **FastAPI**, and **SQLModel**.

Students can submit complaints, browse and filter the complaint list, inspect individual complaints, edit or delete pending complaints, and follow status updates. The API also exposes a status-transition endpoint for the assessment demonstration.

## Technology

- Frontend: React 19, TypeScript, Vite
- Backend: FastAPI
- Database layer: SQLModel
- Local database: SQLite
- Deployment: Vercel (frontend and API routed through `vercel.json`)

## MVP functionality

- Create a complaint
- Read the complaint list (optional status/category filters and pagination)
- Read one complaint by ID
- Update a pending complaint
- Delete a pending complaint
- Update complaint status using the allowed workflow:
  - `pending` → `in_progress` or `rejected`
  - `in_progress` → `resolved` or `rejected`
  - `resolved` and `rejected` are terminal states

## REST API

Interactive Swagger documentation: `/api/docs`

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | API health check |
| POST | `/api/v1/complaints` | Create a complaint |
| GET | `/api/v1/complaints` | List complaints; supports `status`, `category`, `offset`, `limit` |
| GET | `/api/v1/complaints/{id}` | Read one complaint |
| PATCH | `/api/v1/complaints/{id}` | Update a pending complaint |
| DELETE | `/api/v1/complaints/{id}` | Delete a pending complaint |
| PATCH | `/api/v1/complaints/{id}/status` | Change complaint status and optional admin response |

## Run locally

Requirements: Python 3.10+ and Node.js 22+.

### 1. Start the backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
fastapi dev main.py
```

The API runs at `http://localhost:8000`; Swagger is at `http://localhost:8000/api/docs`.

### 2. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` requests to the FastAPI backend.

## Database configuration

By default, the backend creates a local SQLite database at `backend/ccms.db`. To use PostgreSQL, set the backend environment variable `DATABASE_URL` to a SQLAlchemy-compatible PostgreSQL URL, for example a Supabase transaction-pooler URL using the `postgresql+psycopg://` driver, and add the matching driver dependency.

**Deployment note:** Vercel serverless filesystems are temporary. The default SQLite database on Vercel is suitable only for a short-lived demonstration and may reset between deployments or function instances. Configure a persistent PostgreSQL database (such as Supabase) in Vercel Project → Settings → Environment Variables before relying on deployed complaint data.

## Deployment

The repository root contains `vercel.json`. It routes `/api/*` to FastAPI and all other paths to the Vite frontend. Vercel deploys the production branch when changes are merged into `main`.

## Project documentation

- [Product Requirements Document](docs/01-prd.md)
- [Software Requirements Specification](docs/02-srs.md)
- [Technical Design Document](docs/03-tdd.md)
