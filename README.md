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
- Role changes, ban/unban and session revocation. Administrators cannot change their own role or ban another administrator.
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

The application is organized by feature so screens, API boundaries, shared types and backend responsibilities have clear homes.

```
backend/
  main.py
  campuscare/
    app.py                 FastAPI application factory and middleware
    routers/               auth, users, complaints, groups and admin endpoints
    models.py schemas.py   SQLModel tables and validated request contracts
    security.py            JWT, Argon2 + pepper, permissions and auth dependencies
    database.py config.py  PostgreSQL/SQLite engine and environment settings
    audit.py errors.py     audit recording and consistent API error responses
  migrations/              additive SQL migrations for Supabase
  tests/                   pytest authentication, ownership and RBAC coverage
frontend/src/
  features/
    complaints/            complaint CRUD and status workspace
    admin/                 administrator overview and user management
    profile/               account, sessions and shared-group workspace
  services/                same-origin API client and refresh handling
  types/                   shared TypeScript domain contracts
  utils/                   formatting and hash navigation helpers
  App.tsx                  app shell, session restore and page composition
  main.tsx index.css       React entry point and global styles
docs/                      PRD, SRS, TDD and final report
vercel.json                same-origin /api routing to FastAPI
```

Backend endpoints remain the security boundary: frontend route visibility is only a usability aid; ownership and role checks are enforced on every protected API request.
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

The production database is preconfigured for the FastAPI backend. Public signup always creates a normal `user`; do not promote accounts manually unless you are following the recovery procedure.

For the instructor demonstration, the idempotent `backend/seed_demo.py` script creates two administrators, three students, sample complaints and the shared group `Hostel Maintenance Team`. It uses the same production database URL and password pepper as the deployed API. It does not store or print the demo password. Existing demo account passwords are preserved when the script is re-run.

### Windows PowerShell seeding steps

Run these commands from the repository root. Vercel CLI must be logged in and this repository must be linked to the CampusCare Vercel project:

```powershell
npx vercel login
npx vercel link --project 2312123-campus_complaint_management_system --scope sakib-ahmed-iub
npx vercel env pull .env.production.local --environment production

# Load only the production variables needed by the seed into this terminal process.
Get-Content .env.production.local | ForEach-Object {
    if ($_ -match '^(DATABASE_URL|JWT_SECRET|PASSWORD_PEPPER)=(.*)$') {
        $key = $Matches[1]
        $value = $Matches[2].Trim()
        if ($value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
}

# Enter a demo-only password without putting it in shell history.
$secureDemoPassword = Read-Host "Enter a demo-only password (8+ characters, letters and numbers)" -AsSecureString
$env:DEMO_PASSWORD = [System.Net.NetworkCredential]::new("", $secureDemoPassword).Password

python backend/seed_demo.py

# Remove the local production env file and password from this terminal.
Remove-Item .env.production.local
Remove-Item Env:DEMO_PASSWORD
Remove-Item Env:DATABASE_URL
Remove-Item Env:JWT_SECRET
Remove-Item Env:PASSWORD_PEPPER
```

If Vercel CLI asks to link the project, select the existing project. Do not paste the env file or its values into chat, GitHub, screenshots or the final report.

After the script completes, it prints the account IDs and group ID. Use this table to record the IDs locally for your viva/demo:

| User ID | Role | Email | Group permission |
|---|---|---|---|
| Printed by script | admin | admin1@campuscare.test | Administrator |
| Printed by script | admin | admin2@campuscare.test | Administrator |
| Printed by script | user | student1@campuscare.test | Group owner |
| Printed by script | user | student2@campuscare.test | Create + edit |
| Printed by script | user | student3@campuscare.test | Assign only |

The script is safe to re-run for missing demo data. It does not reset passwords for existing demo users; keep the original demo password in a secure place for the instructor walkthrough.


## Tests

From the repository root:

```powershell
cd backend
pip install -r requirements.txt
pytest -q
```

The regression tests cover missing/expired JWT rejection, complaint ownership, user denial of admin-only status changes, admin status updates, admin safety rules and group permission enforcement. GitHub Actions also runs the backend tests and frontend production build for pushes to this feature branches and pull requests to main.

## Deployment and submission

The Vercel project is configured to route `/api/*` to FastAPI and other paths to the React frontend. Merge the reviewed feature branch into `main` to trigger the production deployment. Before the instructor demo, verify the deployed frontend, `/api/health`, and `/api/docs`, then test every role and group permission using the demo accounts.

Final report: [docs/FINAL_REPORT.md](docs/FINAL_REPORT.md)  
PRD: [docs/01-prd.md](docs/01-prd.md) · SRS: [docs/02-srs.md](docs/02-srs.md) · TDD: [docs/03-tdd.md](docs/03-tdd.md)

**Security note:** Never commit real credentials, private database URLs, demo passwords, access tokens or refresh tokens.
