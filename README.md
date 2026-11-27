# CampusCare — Campus Complaint Management System

A secure multi-user campus complaint platform built with React + TypeScript, FastAPI, SQLModel and PostgreSQL (Supabase). The final application supports JWT authentication, role-based access control, private complaints, shared groups and an administrator workspace.

## Technology

- Frontend: React 19, TypeScript, Vite
- Backend: FastAPI, SQLModel, SQLAlchemy
- Authentication: JWT access tokens, rotating httpOnly refresh cookies
- Password storage: Argon2 via pwdlib, with a server-side pepper
- Database: Supabase PostgreSQL (persistent) or SQLite for local development
- Deployment: Vercel
- Tests: pytest and GitHub Actions

## Features

### Authentication and profile
- Signup and login; passwords are never stored in plain text.
- Access tokens last no longer than 15 minutes.
- Refresh tokens are stored as hashes in the database and rotated on refresh.
- Logout, session listing and session revocation.
- Profile update and password change (current password required).
- Failed login throttling by email and IP.

### Roles and complaint access
- Roles are `user` and `admin`, stored in the database.
- All protected endpoints validate the bearer token and current database account.
- Users can create, read, edit and delete only their own complaints (edit/delete while pending).
- Admins can read and moderate all complaints and update status.
- Admin-only operations are enforced on the backend, not just hidden in the frontend.

### Groups
- Create and manage shared groups.
- Group owners add members and set create, edit and assign permissions.
- Members can only perform actions granted by the owner.
- Only the owner can rename/delete the group or manage its membership.

### Admin workspace
- Overview statistics and searchable user list.
- Role changes, ban/unban and session revocation.
- Complaint and group moderation.
- Activity/audit history and security summary.
- CSV exports for users, records and activity.

## API endpoints

Swagger documentation: `/api/docs`

| Area | Endpoint examples |
|---|---|
| Health | `GET /api/health` |
| Auth | `POST /api/v1/auth/signup`, `/login`, `/refresh`, `/logout` |
| Sessions | `GET /api/v1/auth/sessions`, `DELETE /api/v1/auth/sessions/{id}` |
| Profile | `GET/PATCH /api/v1/users/me`, `POST /api/v1/users/me/password` |
| Complaints | `/api/v1/complaints` (CRUD and status) |
| Groups | `/api/v1/groups` (groups, members, shared records) |
| Admin | `/api/v1/admin/stats`, `/users`, `/activity`, `/security`, `/records`, `/groups`, `/export/{kind}` |

## Project structure

```
backend/
  main.py                 entrypoint (main:app)
  seed_demo.py            demo accounts and sample data
  campuscare/
    app.py                application factory, CORS, lifespan
    config.py database.py environment settings, engine and session
    models.py schemas.py  database tables, request payloads
    security.py           password hashing, JWT, RBAC permission map and dependencies
    audit.py validation.py errors.py   audit log, input checks, consistent errors
    routers/              auth, users, complaints, groups, admin_users, admin_content, admin_reports
  tests/                  pytest suite
  migrations/             SQL for Supabase
frontend/src/             React + TypeScript app
docs/                     PRD, SRS, TDD and FINAL_REPORT.md
```

## Local setup (Windows PowerShell)

### 1. Backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:JWT_SECRET="local-only-long-random-secret"
$env:PASSWORD_PEPPER="local-only-different-random-secret"
$env:COOKIE_SECURE="false"
fastapi dev main.py
```

The API runs at `http://localhost:8000`; Swagger is at `http://localhost:8000/api/docs`.

### 2. Frontend

Open a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open the Vite URL shown in the terminal (normally `http://localhost:5173`). The Vite development server proxies `/api` to FastAPI.

## Environment variables

Copy `.env.example` to a local `.env` file or configure the values in Vercel Project → Settings → Environment Variables.

| Variable | Required in production | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | Supabase transaction pooler URL; use `postgresql+psycopg://` |
| `JWT_SECRET` | Yes | Long random secret; never commit it |
| `PASSWORD_PEPPER` | Yes | Separate long random secret; never commit it |
| `ACCESS_TOKEN_MINUTES` | No | Defaults to 15; maximum is 15 |
| `REFRESH_TOKEN_DAYS` | No | Defaults to 7 |
| `COOKIE_SECURE` | Yes | Set `true` on HTTPS production; `false` only for local HTTP |
| `ALLOWED_ORIGINS` | Recommended | Comma-separated frontend origins for CORS, e.g. `https://your-app.vercel.app` |

For Vercel, use the Supabase transaction pooler (typically port 6543). The backend uses psycopg 3 and disables prepared statements for transaction-pooler compatibility. Do not expose database credentials or JWT secrets in frontend variables.

The backend creates missing tables and adds the complaint ownership column to an existing MVP complaint table without deleting legacy records. Legacy complaints with no owner remain admin-visible only.

## Initial admin setup and instructor accounts

Public signup always creates a normal `user`. Demo data is created with the idempotent seed script, which reads the demo password from the environment (never stored in the repo). Use the same `DATABASE_URL`, `JWT_SECRET` and `PASSWORD_PEPPER` as production:

```powershell
cd backend
$env:DATABASE_URL="<supabase pooler url>"
$env:JWT_SECRET="<same as Vercel>"
$env:PASSWORD_PEPPER="<same as Vercel>"
$env:DEMO_PASSWORD="<demo-only password with a letter and a number>"
python seed_demo.py
```

It creates 2 admins, 3 normal users, sample complaints, and one shared group, then prints the user IDs. Copy them into the table below (replace the `?` after running the script). Passwords go only in the submission form and the PDF report.

| User ID | Role | Email |
|---|---|---|
| ? | admin | admin1@campuscare.test |
| ? | admin | admin2@campuscare.test |
| ? | user | student1@campuscare.test (owner of the shared group) |
| ? | user | student2@campuscare.test (group member: create + edit) |
| ? | user | student3@campuscare.test (group member: assign only) |

Shared group: **Hostel Maintenance Team**, owned by student1. Only the owner can rename, delete or manage members; student2 can create and edit records; student3 can assign records only.

## Tests

From the repository root:

```powershell
cd backend
pip install -r requirements.txt
pytest -q
```

The regression tests cover missing/expired JWT rejection, complaint ownership, user denial of admin-only status changes, admin status updates, admin safety rules and group permission enforcement. GitHub Actions also runs the backend tests and frontend production build for pushes to this development branch and pull requests to main.

## Deployment and submission

The Vercel project is configured to route `/api/*` to FastAPI and other paths to the React frontend. Merge the reviewed feature branch into `main` to trigger the production deployment. Before the instructor demo, verify the deployed frontend, `/api/health`, and `/api/docs`, then test every role and group permission using the demo accounts.

Final report: [docs/FINAL_REPORT.md](docs/FINAL_REPORT.md)  
PRD: [docs/01-prd.md](docs/01-prd.md) · SRS: [docs/02-srs.md](docs/02-srs.md) · TDD: [docs/03-tdd.md](docs/03-tdd.md)

**Security note:** Never commit real credentials, private database URLs, demo passwords, access tokens or refresh tokens.
