# Leave Tracker Project

Complete project guide for the current codebase. This README is written to cover the project end-to-end: architecture, features, roles, data model, APIs, frontend routes, local setup, deployment, desktop EXE launcher, and troubleshooting.

## 1) What This Project Is

Leave Tracker is a multi-organization HR platform with:

- Leave management
- Talent acquisition
- Onboarding management
- Organization directory and hierarchy management
- Admin user management and password controls
- Audit logging
- Advanced architecture modules (workspace, compliance, workflow, control plane)

This repo provides **three user-facing surfaces**:

1. Django server-rendered UI (`/login`, `/dashboard`, `/leave/*`, `/admin-panel/*`)
2. Next.js + shadcn frontend (`frontend/src/app/*`)
3. Windows desktop launcher EXE (`LeaveTrackerLauncher.exe`) that starts backend + frontend locally

## 2) Tech Stack

Backend:
- Django 5
- Django REST Framework
- SimpleJWT (`djangorestframework-simplejwt`)
- `django-cors-headers`
- SQLite (default), PostgreSQL (`DATABASE_URL`)

Frontend:
- Next.js 16 (App Router)
- React 19
- shadcn/ui + Tailwind
- Sonner toasts + Lucide icons

Optional infra:
- Celery + Redis
- S3/R2 file storage via `django-storages` + `boto3`

Desktop:
- PyInstaller for `LeaveTrackerLauncher.exe`

## 3) Repository Structure

Top-level app directories:

- `leave_tracker_project/` Django settings, URL root, ASGI/WSGI, Celery bootstrap
- `users/` custom user model, admin account model, profile, OTP reset, auth views/forms
- `organization/` company and tenant models, org directory structure, context resolution, tenancy helpers
- `leaves/` leave/talent/onboarding models, forms, workflows, signals, data bootstrap command
- `api/` REST API endpoints and serializers used by frontend
- `portal/` dashboard/home/health views for Django template flow
- `auditlog/` core audit event model
- `architecture/` advanced architecture/compliance/workflow/control-plane entities + APIs
- `frontend/` Next.js application
- `desktop_app/` launcher source and logs
- `docs/` architecture docs, diagrams, DBML artifacts

Important root files:

- `manage.py`
- `requirements.txt`
- `Procfile`
- `LeaveTrackerLauncher.spec`
- `LeaveTrackerLauncher.exe`
- `.env.example`

## 4) Core Product Features

### 4.1 Leave Module

- Leave type policies per company
- Leave reason presets per company
- Holiday calendar per company
- Apply/edit/cancel leave
- Approval queue for HR/Admin
- Leave balance calculation by year
- Automatic consume/release of balance on approval status changes
- CSV export
- iCal export
- Team calendar with month/week modes
- Supporting document uploads

### 4.2 Talent & Onboarding

- Candidate pipeline (`APPLIED`, `SCREENING`, `INTERVIEW`, `OFFER`, `HIRED`, `REJECTED`)
- Onboarding task tracking with categories (`HR`, `IT`, `FACILITIES`, `GENERAL`)
- Dynamic form fields (per company/module and optionally per org unit/location)
- Company-scoped ownership and access controls

### 4.3 Organization Workspace

- Company list and active organization context
- Organization + tenant creation (platform admin)
- Org units, locations, cost centers, job levels, positions
- Employee records and manager relationships
- Reporting tree and direct/indirect reporting APIs
- HR scope controls by org unit/location

### 4.4 Admin & Access

- Create users with role and company assignment
- Set tracker access (`MAIN`, `ORGANIZATION`, `BOTH`)
- Admin account levels (`PLATFORM`, `ORGANIZATION`)
- Admin password set/reset endpoint for managed users
- OTP password reset flow for users

### 4.5 Architecture Module

Under `/api/architecture/*` and `/architecture` UI:

- Workspace: threads/comments/mentions/presence
- Compliance: IdP identities, MFA factors, RBAC models, session tokens, immutable audit events
- Workflow: rules, instances, step runs, job queue, notification outbox
- Control: tenant DB connections, tenant provision jobs, tenant schema migrations

## 5) User Model, Roles, And Access Rules

`users.User` adds:

- `role`: `EMPLOYEE | MANAGER | HR`
- `organization`: FK to `organization.Company`
- `manager`: self-reference
- `created_by`, `created_in_organization`
- `portal_access`: `MAIN | ORGANIZATION | BOTH`

`users.AdminAccount` controls admin scope:

- `level`: `PLATFORM` or `ORGANIZATION`
- `organization` (required for organization-level admin)
- `can_manage_users`
- `can_manage_organizations`

Access enforcement:

- API permissions in `api/permissions.py`
- Core checks in `users/permissions.py`
- Context-based scoping in `organization/context.py`
- Per-request org middleware in `organization/middleware.py`

## 6) Multi-Organization/Tenancy Model

Current default model:

- Shared-schema multi-organization architecture
- Data isolation by company IDs + access checks + context resolution

Organization core models:

- `Company`
- `OrganizationDirectory`
- `OrganizationTenant`
- `OrgUnit`
- `Location`
- `CostCenter`
- `JobLevel`
- `Position`
- `EmployeeRecord`
- `ManagerRelationship`
- `OrgAccessScope`
- `IntegrationEvent`
- `OrganizationFormField`

Request context flow:

1. Frontend sends `X-Company-Id` and `X-DTS-SCHEMA`
2. `OrganizationContextMiddleware` resolves/validates active company
3. APIs scope queries to company
4. Optional strict mode can enforce explicit context

Optional PostgreSQL schema tenancy support:

- `ENABLE_POSTGRES_SCHEMA_TENANCY=1`
- `TENANCY_AUTO_CREATE_SCHEMA=1` (optional auto-create)
- Search path switching handled in `organization/tenancy.py`

## 7) Data Model Summary By App

### users

- `User`
- `AdminAccount`
- `EmployeeProfile`
- `PasswordResetOTP`

### leaves

- `LeaveType`
- `LeaveReasonPreset`
- `Holiday`
- `LeaveBalance`
- `LeaveRequest`
- `LeaveAttachment`
- `TalentCandidate`
- `TalentCandidateCustomFieldValue`
- `OnboardingTask`
- `OnboardingTaskCustomFieldValue`

### organization

- `Company`
- `OrganizationDirectory`
- `OrganizationTenant`
- `OrgUnit`
- `Location`
- `CostCenter`
- `JobLevel`
- `Position`
- `EmployeeRecord`
- `ManagerRelationship`
- `OrgAccessScope`
- `IntegrationEvent`
- `OrganizationFormField`

### architecture

- `WorkspaceThread`
- `WorkspaceComment`
- `WorkspaceMention`
- `WorkspacePresence`
- `IdpIdentity`
- `MfaFactor`
- `AccessRole`
- `AccessPermission`
- `RolePermission`
- `UserRoleBinding`
- `SessionToken`
- `ImmutableAuditEvent`
- `WorkflowRule`
- `WorkflowInstance`
- `WorkflowStepRun`
- `JobQueueEntry`
- `NotificationOutbox`
- `TenantConnection`
- `TenantProvisionJob`
- `TenantSchemaMigration`

### auditlog

- `AuditEvent`

## 8) URL Routing

Root routes (`leave_tracker_project/urls.py`):

- `/admin/` Django admin
- `/api/` REST APIs (`api.urls`)
- `/api/architecture/` architecture APIs
- template routes from `portal.urls`, `users.urls`, `leaves.urls`

Template routes:

- `/login/`
- `/logout/`
- `/password-reset/`
- `/password-reset/verify/<uuid:token>/`
- `/dashboard/`
- `/health/`
- `/profile/edit/`
- `/admin-panel/`
- `/admin-panel/create/`
- `/admin-panel/<id>/toggle/`
- `/admin-panel/<id>/delete/`
- `/leave/*`

## 9) API Endpoint Map

Auth:

- `POST /api/auth/login/`
- `POST /api/auth/password-reset/`
- `POST /api/auth/password-reset/verify/<uuid:token>/`
- `POST /api/auth/refresh/`
- `GET /api/auth/me/`

Profile + dashboard:

- `GET /api/dashboard/summary/`
- `PATCH /api/profile/`

Leave:

- `GET /api/leave/types/`
- `PATCH/DELETE /api/leave/types/<id>/`
- `GET /api/leave/reasons/`
- `PATCH/DELETE /api/leave/reasons/<id>/`
- `GET/POST /api/leave/requests/`
- `GET/PATCH/DELETE /api/leave/requests/<id>/`
- `POST /api/leave/requests/<id>/review/`
- `GET/POST /api/leave/holidays/`
- `PATCH/DELETE /api/leave/holidays/<id>/`
- `POST /api/leave/holidays/import-ics/`
- `GET /api/leave/calendar/`
- `GET /api/leave/export.csv`
- `GET /api/leave/ical/`

Organization:

- `GET /api/org/context/`
- `GET/POST /api/org/companies/`
- `GET /api/org/tenants/`
- `GET/POST/PATCH /api/org/units/`
- `GET/POST/PATCH /api/org/locations/`
- `GET/POST/PATCH /api/org/cost-centers/`
- `GET/POST/PATCH /api/org/job-levels/`
- `GET/POST/PATCH /api/org/positions/`
- `GET/POST /api/org/form-fields/`
- `PATCH/DELETE /api/org/form-fields/<id>/`

HR/reporting:

- `GET/PATCH /api/hr/employees/`
- `POST /api/org/reporting/change-manager/`
- `GET /api/org/reporting/direct-reports/`
- `GET /api/org/reporting/tree/`

Admin:

- `GET/POST /api/admin/accounts/`
- `GET/POST /api/admin/users/`
- `PATCH/DELETE /api/admin/users/<id>/`
- `POST /api/admin/users/<id>/password/`

Talent/onboarding:

- `GET/POST /api/talent/candidates/`
- `GET/PATCH/DELETE /api/talent/candidates/<id>/`
- `GET/POST /api/onboarding/tasks/`
- `GET/PATCH/DELETE /api/onboarding/tasks/<id>/`

Audit:

- `GET /api/audit/events/`

Architecture module:

- `/api/architecture/workspace/*`
- `/api/architecture/compliance/*`
- `/api/architecture/workflow/*`
- `/api/architecture/control/*`

## 10) Frontend Route Map (`frontend/src/app`)

- `/login`
- `/forgot-password`
- `/forgot-password/verify/[token]`
- `/dashboard`
- `/leave/apply`
- `/company-board`
- `/calendar`
- `/approvals`
- `/leave-policies`
- `/admin-users`
- `/talent`
- `/onboarding`
- `/organization`
- `/architecture`
- `/audit-trail`
- `/profile`

## 11) Local Setup (Backend + Frontend)

### 11.1 Prerequisites

- Python 3.12+ (3.13 works in this repo)
- Node.js 20+
- npm
- Optional: Redis (for Celery)

### 11.2 Backend Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py bootstrap_leave_data
python manage.py createsuperuser
python manage.py runserver
```

Backend URLs:

- `http://127.0.0.1:8000/login/`
- `http://127.0.0.1:8000/dashboard/`
- `http://127.0.0.1:8000/admin/`
- `http://127.0.0.1:8000/health/`

### 11.3 Frontend Setup

```powershell
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

Frontend URL:

- `http://127.0.0.1:3000/login`

Default frontend env:

- `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api`

## 12) Desktop EXE Launcher

Launcher:

- `LeaveTrackerLauncher.exe`

Source:

- `desktop_app/launcher.py`

What it does:

1. Locates project root (`manage.py` + `frontend/package.json`)
2. Runs migrations and bootstrap
3. Starts Django (`127.0.0.1:8000`)
4. Starts Next.js dev (`127.0.0.1:3000`)
5. Opens browser to frontend login
6. Logs to `desktop_app/logs/backend.log` and `desktop_app/logs/frontend.log`

Rebuild EXE:

```powershell
.venv\Scripts\python.exe -m pip install -U pyinstaller
.venv\Scripts\python.exe -m PyInstaller LeaveTrackerLauncher.spec --clean --noconfirm
```

## 13) Environment Variables

Reference source:

- `.env.example`
- `leave_tracker_project/settings.py`

Important groups:

Security and hosts:
- `DEBUG`
- `SECRET_KEY`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `TIME_ZONE`

Organization context and tenancy:
- `FRONTEND_ORIGINS`
- `REQUIRE_EXPLICIT_ORG_CONTEXT`
- `ORG_CONTEXT_AUDIT_LOG`
- `ENABLE_POSTGRES_SCHEMA_TENANCY`
- `TENANCY_AUTO_CREATE_SCHEMA`
- `ORG_CONTEXT_EXEMPT_PATHS`
- `ORG_CONTEXT_EXEMPT_PATH_PREFIXES`

Database:
- `USE_DATABASE_URL`
- `DATABASE_URL`

Email and OTP:
- `EMAIL_BACKEND`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`
- `EMAIL_USE_SSL`
- `EMAIL_TIMEOUT`
- `EMAIL_FAIL_SILENTLY`
- `DEFAULT_FROM_EMAIL`

Leave rules/notifications:
- `MANAGER_EMAILS`
- `LEAVE_EMAIL_NOTIFICATIONS_ENABLED`
- `LEAVE_NOTIFICATION_TARGET`
- `HR_MAILBOX`
- `TEAM_DISTRIBUTION_EMAILS`
- `LEAVE_RATE_LIMIT_PER_MINUTE`
- `LEAVE_TEAM_OFF_THRESHOLD`

Celery:
- `USE_CELERY`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`

S3/R2 storage:
- `AWS_STORAGE_BUCKET_NAME`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_S3_REGION_NAME`
- `AWS_S3_CUSTOM_DOMAIN`

JWT:
- `JWT_ACCESS_MINUTES`
- `JWT_REFRESH_DAYS`

## 14) First-Time Operational Flow

Recommended start:

1. Create/activate superuser
2. Login
3. Open Admin Users page
4. Create company/organization if needed
5. Create HR/Manager/Employee users and assign organization
6. Set portal access (`MAIN`, `ORGANIZATION`, or `BOTH`)
7. User sets password via OTP flow or admin password set endpoint
8. User logs in and uses leave/talent/onboarding features

## 15) Deployment Overview

### Backend (Railway or similar)

- Use `Procfile` web command:
- `python manage.py migrate --noinput && python manage.py bootstrap_leave_data && gunicorn leave_tracker_project.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`

Important:

- Keep migrate/bootstrap in **start command**, not build command
- Set `ALLOWED_HOSTS` to your backend host
- Set `FRONTEND_ORIGINS` and `CSRF_TRUSTED_ORIGINS` correctly
- Verify CORS with preflight `OPTIONS`

### Frontend (Vercel or similar)

- Root directory: `frontend`
- Framework: Next.js
- Required env:
- `NEXT_PUBLIC_API_BASE_URL=https://<your-backend-domain>/api`

## 16) GitHub Push Without Missing Features

Push source/config/migrations, but do not track generated runtime folders.

Recommended `.gitignore` entries:

- `.venv/`
- `__pycache__/`
- `*.pyc`
- `frontend/node_modules/`
- `frontend/.next/`
- `desktop_app/logs/`
- `*.log`

If large generated files were previously tracked, untrack first:

```powershell
git rm -r --cached --ignore-unmatch .venv frontend/node_modules frontend/.next __pycache__ desktop_app/logs
git add -A
git commit -m "Remove generated artifacts from tracking"
```

Then push normally.

## 17) Common Troubleshooting

### Login works locally but fails in deployed frontend

Check:
- `NEXT_PUBLIC_API_BASE_URL` points to correct backend
- Backend CORS/CSRF origins include frontend domain
- Browser devtools preflight has `Access-Control-Allow-Origin`

### Railway error: `'' is not a valid port number`

Cause:
- Gunicorn command running during build without runtime `$PORT`.

Fix:
- Put gunicorn only in start/deploy command.

### OTP email stuck or timeout

Check:
- SMTP host/port/user/password
- TLS/SSL flags
- provider app password (for Gmail)
- network egress rules in hosting platform

### GitHub rejects push due to large files

Cause:
- `node_modules` / `.next` / binaries in git history.

Fix:
- remove from tracking + commit + push
- if needed, fresh orphan snapshot and force push

### Vercel `404 DEPLOYMENT_NOT_FOUND`

Cause:
- old deployment URL opened after new deploy.

Fix:
- open current active deployment URL from Vercel dashboard.

## 18) Related Docs In This Repo

- `docs/ENTIRE_PROJECT_EXPLANATION.md`
- `docs/WORKSPACE_ORGANIZATION_ARCHITECTURE_DOCUMENT.md`
- `docs/WORKSPACE_ORGANIZATION_ARCHITECTURE_DIAGRAM.md`
- `docs/MULTIPLE_ARCHITECTURE_DIAGRAMS.md`
- `docs/leave_tracker_multiorg.dbml`

## 19) Final Notes

- This project is production-capable but still benefits from expanded automated test coverage.
- Organization isolation is robust at app-level and can be hardened further with schema-level tenancy for PostgreSQL.
- For enterprise use, pair this with strict CI/CD checks, monitoring, backups, and security hardening.
