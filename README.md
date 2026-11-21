# CampusCare — Secure Campus Complaint Management System

CampusCare is a multi-user campus issue-reporting platform built with React + TypeScript, FastAPI, SQLModel, and Supabase PostgreSQL. It supports student accounts, private complaints, administrator moderation, collaboration groups, and security audit records.

## Technology

- Frontend: React 19, TypeScript, Vite
- API: FastAPI, Python 3.11+
- Data layer: SQLModel / SQLAlchemy
- Database: SQLite for local development; persistent PostgreSQL for deployment
- Authentication: Argon2 password hashing, server-side pepper, 15-minute JWT access tokens, rotating hashed refresh sessions
- Migrations: Alembic
- Deployment: Vercel

## Main features

### Authentication and profile
- Sign up and sign in with email and password
- Argon2 password hashes; plain-text passwords are never stored
- Short-lived JWT access tokens and HttpOnly refresh-token cookies
- Refresh-token rotation and revocation on logout/password change
- Profile name and password updates
- Active/revoked session listing and self-revocation
- Failed-login tracking and temporary login throttling

### Student complaints
- Students can create and view their own complaints only
- Students can edit or delete their own pending complaints
- Other users' complaint IDs return 404
- Students cannot change complaint status
- Administrators can view and moderate all complaints
- Status transitions: pending → in_progress/rejected; in_progress → resolved/rejected; resolved/rejected are final

### Roles and administration
- Roles: user and admin
- Server-side authorization; hiding a UI control is not treated as security
- Admin dashboard statistics, user search/filtering, role changes, bans/unbans, audit log, failed-login summary, and CSV exports
- Administrators cannot change their own role or ban another administrator
- A banned account is denied on its next authenticated request and active refresh sessions are revoked

### Collaboration groups
- Group owner can rename/delete the group and manage membership
- Members have separate create, edit, and assign permission flags
- Group records are visible only to group members

## Run locally (Windows PowerShell)

Use Python 3.11 and Node.js 22 or newer.

### 1. Backend

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set unique local values for `JWT_SECRET` and `PASSWORD_PEPPER`. For local development, `DATABASE_URL=sqlite:///./ccms.db` is sufficient. Do not use the example secrets outside local testing.

Start the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

Open API documentation at `http://127.0.0.1:8000/api/docs`.

### 2. Frontend

Open a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies API calls to the backend on port 8000.

### 3. Run automated backend tests

From the `backend` directory:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The test suite covers missing/invalid tokens, student/admin authorization, complaint ownership, and admin self-role protection. GitHub Actions also runs the backend tests and frontend production build.

## Environment variables

Configure these in Vercel Project → Settings → Environment Variables. Use separate, randomly generated values for the secrets.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Persistent Supabase PostgreSQL connection string |
| `JWT_SECRET` | Random signing secret, at least 32 bytes |
| `PASSWORD_PEPPER` | Separate random password pepper, at least 32 bytes |

Do not put real credentials in this repository, README, screenshots, or chat messages. Do not use SQLite for Vercel production: serverless local storage is temporary. Ensure the Supabase database is reachable from Vercel and that the connection string uses the PostgreSQL/psycopg driver supported by the backend.

Alembic applies the schema migration during API startup. The migration preserves the existing MVP complaint rows and adds a nullable owner reference; old unowned demo rows are visible to admins but not to student accounts.

## First administrator and demo accounts

Public signup always creates a normal `user` role. To create the first administrator, register the account through the app, then promote that account through a trusted Supabase SQL Editor session:

```sql
UPDATE "user" SET role = 'admin' WHERE email = 'the-admin-email@example.com';
```

Create at least two administrator accounts and three normal user accounts for the assessment demonstration. Use unique test passwords and share those credentials only through the instructor's approved submission channel—not in this public repository. Create a sample group, add members, and assign different create/edit/assign permissions before recording the demo.

## API overview

Interactive documentation: `/api/docs`

| Area | Main endpoints |
|---|---|
| Auth | `POST /api/v1/auth/signup`, `/login`, `/refresh`, `/logout` |
| Profile | `GET/PATCH /api/v1/users/me`, `POST /api/v1/users/me/password` |
| Sessions | `GET /api/v1/users/me/sessions`, `DELETE /api/v1/users/me/sessions/{id}` |
| Complaints | `/api/v1/complaints` |
| Groups | `/api/v1/groups` and nested members/records endpoints |
| Admin | `/api/v1/admin/stats`, `/users`, `/audit`, `/security/failed-logins`, `/export/{kind}` |
| Health | `GET /api/health` |

## Deployment

The repository root `vercel.json` routes `/api/*` to FastAPI and other paths to the Vite frontend. Production deployment is intended to follow the `main` branch. Work is developed on `feat/final-project-security` and should be reviewed/tested before merging to `main`.

Before the final demonstration, verify:
1. The deployed homepage loads and browser refresh works on nested URLs.
2. `/api/health` and `/api/docs` load.
3. Signup, login, refresh, logout, and password change work.
4. A student cannot read another student's complaint or change its status.
5. Admin ban/unban, role change, audit view, and CSV exports work.
6. Group member permissions are tested with accounts having different permission combinations.

## Project documentation

- [Product Requirements Document](docs/01-prd.md)
- [Software Requirements Specification](docs/02-srs.md)
- [Technical Design Document](docs/03-tdd.md)
- [Backend security setup](backend/README_SECURITY.md)
