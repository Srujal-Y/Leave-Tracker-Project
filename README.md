# Leave Tracker

A role-based Leave Management System built with Django 5, focused on:
- Employee self-service leave application
- Admin/HR approval-controlled leave lifecycle
- Leave balances and entitlement tracking
- Audit visibility and reporting
- OTP-based password reset
- A themed "Red Samurai" UI

This README is the full operational guide for the current codebase in this repository.

## 1. Tech Stack
- Backend: Django 5 (`Django>=5.2,<6.0`)
- Database: SQLite by default, PostgreSQL via `DATABASE_URL` and `USE_DATABASE_URL=1`
- Queue (optional): Celery + Redis
- Email: SMTP (with console fallback if SMTP host not configured)
- Storage (optional): local media by default, S3/R2 via `django-storages` + `boto3`
- Frontend (existing): Django templates + Bootstrap 5 + custom CSS theme (`static/css/app.css`)
- Frontend (new): Next.js + shadcn/ui (`frontend/`)

## 2. Project Structure
Key directories and files:
- `leave_tracker_project/settings.py`: environment-driven settings and app configuration
- `leave_tracker_project/urls.py`: root URL routing
- `users/`: custom auth model, OTP reset flow, admin user panel, profile
- `leaves/`: leave business models, forms, views, signals, seed command
- `portal/`: dashboard, home redirect, health endpoint
- `auditlog/`: audit event model and admin registration
- `templates/`: UI templates
- `static/css/app.css`: Red Samurai design system
- `api/`: DRF + JWT API endpoints for shadcn frontend
- `frontend/`: Next.js + shadcn/ui app
- `.env.example`: environment template
- `requirements.txt`: Python dependencies

## 3. Core Functional Coverage
Implemented features:
- Custom user model with roles (`Employee`, `Manager`, `HR`)
- Admin-gated portal login (`can_portal_login`)
- Email-or-username login
- OTP password reset (email delivery)
- Employee profile card (photo, phone, project fields, initiatives)
- Leave type policies (`max_days`, `is_paid`, `active`)
- Leave request lifecycle (`Pending`, `Approved`, `Rejected`, `Cancelled`)
- Supporting document uploads on leave requests (max combined upload size 10 GB per submission)
- Entitlement and balance by `(user, leave_type, year)`
- Auto-consume/release balance on status transitions (signals)
- Working-day calculation excluding weekends + configured holidays
- Overlap detection and optional team-off threshold warning
- Company leave board with search + filters + pagination
- CSV export for company board (Admin/HR)
- Monthly/weekly calendar and daily drilldown
- iCal export of approved personal leaves
- Approval queue and review workflow (Admin/HR)
- Public holiday management from portal UI (admin-only create/edit/delete)
- Audit trail UI and model
- `/health/` endpoint for readiness checks

## 4. Data Model Design
Primary models and purpose:

### `users.User`
- Extends `AbstractUser`
- Extra fields:
  - `role`: `EMPLOYEE | MANAGER | HR`
  - `manager`: self FK (limited to Manager role)
  - `can_portal_login`: hard gate for portal access

### `users.EmployeeProfile`
- One-to-one with `User`
- Fields:
  - `photo`
  - `phone_number`
  - `current_project`
  - `project_status`
  - `initiatives_to_take`

### `users.PasswordResetOTP`
- One-time password reset entity
- Fields:
  - `token` (UUID)
  - `code` (6 digits)
  - `expires_at`
  - `used_at`

### `leaves.LeaveType`
- Leave policy master
- Fields:
  - `name`
  - `max_days`
  - `is_paid`
  - `active`

### `leaves.LeaveReasonPreset`
- Controlled leave reason options
- Fields:
  - `label`
  - `active`

### `leaves.Holiday`
- Holiday calendar table used in business-day calculation
- Fields:
  - `name`
  - `date` (unique)

### `leaves.LeaveAttachment`
- Stores uploaded files linked to a leave request
- Fields:
  - `leave_request`
  - `file`
  - `original_name`
  - `size_bytes`
  - `uploaded_by`
  - `uploaded_at`

### `leaves.LeaveBalance`
- Entitlement ledger per `(user, leave_type, year)`
- Fields:
  - `allocated_days`
  - `used_days`
  - computed `remaining_days`

### `leaves.LeaveRequest`
- Main workflow object
- Fields:
  - `employee` FK
  - `leave_type` FK
  - `start_date`, `end_date`
  - `portion`: `FULL | HALF | QUARTER`
  - `requested_units`
  - `status`: `PENDING | APPROVED | REJECTED | CANCELLED`
  - `approver`, `manager_note`
  - lifecycle timestamps
  - `is_deleted` soft-state flag

### `auditlog.AuditEvent`
- Tracks key leave actions with actor and metadata

## 5. Signals and Automation
Signal behavior:
- `users.signals.ensure_profile`:
  - Creates/ensures `EmployeeProfile` whenever a `User` is saved
- `leaves.signals.create_initial_leave_balances`:
  - On user creation, creates leave balances for all active leave types (current year)
- `leaves.signals.create_leave_type_balances_for_all_users`:
  - On leave type create/update, seeds/updates user balances
- `leaves.signals.maintain_balance_on_status_change`:
  - Auto-consumes balance when request moves to `APPROVED`
  - Releases balance when leaving `APPROVED`

## 6. Role and Access Matrix
- Employee:
  - Login (if `can_portal_login=True`)
  - Apply/edit/cancel own leave requests (edit/cancel only while pending)
  - View dashboard, company board, calendar, own iCal
  - Edit own profile
- Manager:
  - Employee capabilities
  - Plus can be assignment target as `manager`
- HR/Admin (`is_staff` or `is_superuser` or role `HR`):
  - Approval queue and review actions
  - Manage leave policies (types and reason presets)
  - Admin user panel (create/disable/delete users)
  - Audit trail view
  - CSV export

## 7. URL Map
Main routes:
- `/login/`: login page
- `/logout/`: logout
- `/password-reset/`: OTP request
- `/password-reset/verify/<uuid:token>/`: OTP verification + password set
- `/dashboard/`: employee dashboard
- `/health/`: health endpoint
- `/profile/edit/`: employee profile edit
- `/admin-panel/`: user admin panel
- `/leave/apply/`: create leave request
- `/leave/apply/<id>/edit/`: edit leave request
- `/leave/apply/<id>/cancel/`: cancel leave request
- `/leave/company/`: company board
- `/leave/company/export.csv`: CSV export
- `/leave/calendar/`: month/week calendar
- `/leave/approvals/`: approval queue
- `/leave/approvals/<id>/`: approve/reject detail
- `/leave/policies/`: leave policy management
- `/leave/policies/holidays/new/`: add holiday (admin only)
- `/leave/policies/holidays/<id>/edit/`: edit holiday (admin only)
- `/leave/policies/holidays/<id>/delete/`: delete holiday (admin only)
- `/leave/audit-trail/`: audit events
- `/leave/ical/`: personal approved leave iCal export
- `/leave/<id>/`: leave detail
- `/api/*`: REST API for Next.js/shadcn frontend

### API Highlights
- `POST /api/auth/login/`
- `POST /api/auth/refresh/`
- `GET /api/auth/me/`
- `GET /api/dashboard/summary/`
- `GET /api/leave/types/`
- `GET/POST /api/leave/requests/`
- `GET /api/leave/requests/<id>/`
- `POST /api/leave/requests/<id>/review/`
- `GET/POST /api/leave/holidays/` (POST admin only)
- `PATCH/DELETE /api/leave/holidays/<id>/` (admin only)

## 8. Setup and Run (Local)
### Prerequisites
- Python 3.12+ recommended
- `pip`
- Optional for async email: Redis

### Install
```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

### Configure environment
1. Copy `.env.example` to `.env`
2. Fill values (minimum: `SECRET_KEY`, email settings if OTP by inbox is required)

### Run migrations and seed defaults
```bash
python manage.py migrate
python manage.py bootstrap_leave_data
python manage.py createsuperuser
```

### Start application
```bash
python manage.py runserver
```

Open:
- `http://127.0.0.1:8000/login/`
- `http://127.0.0.1:8000/dashboard/`
- `http://127.0.0.1:8000/admin/`
- `http://127.0.0.1:8000/health/`

### Start shadcn frontend
```bash
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

Open:
- `http://127.0.0.1:3000/login`

## 9. First-Time Operational Flow
Recommended sequence:
1. Login as superuser.
2. Go to `Admin Users`.
3. Create managers and employees.
4. For employees, ensure `can_portal_login=True` (handled by admin panel create flow).
5. User clicks `Forgot Password (OTP)` to set initial password.
6. User logs in and applies leave.
7. Admin/HR reviews in `Approval Queue`.

## 10. Environment Variables
Core variables from `.env.example`:

Security and host:
- `DEBUG`: `1` local, `0` production
- `SECRET_KEY`: required in non-dev
- `ALLOWED_HOSTS`: comma-separated hosts
- `CSRF_TRUSTED_ORIGINS`: comma-separated origins
- `TIME_ZONE`: default `UTC`

Database:
- `USE_DATABASE_URL`: `0` for SQLite, `1` to use `DATABASE_URL`
- `DATABASE_URL`: PostgreSQL URL when enabled

Email/OTP:
- `EMAIL_BACKEND`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`
- `EMAIL_USE_SSL`
- `EMAIL_FAIL_SILENTLY`
- `DEFAULT_FROM_EMAIL`

Leave notifications/rules:
- `MANAGER_EMAILS`
- `LEAVE_EMAIL_NOTIFICATIONS_ENABLED`
- `LEAVE_NOTIFICATION_TARGET` (`MANAGER|HR|TEAM|BOTH|ALL`)
- `HR_MAILBOX`
- `TEAM_DISTRIBUTION_EMAILS`
- `LEAVE_RATE_LIMIT_PER_MINUTE`
- `LEAVE_TEAM_OFF_THRESHOLD`

Celery/Redis:
- `USE_CELERY`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`

S3/R2 media storage:
- `AWS_STORAGE_BUCKET_NAME`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_S3_REGION_NAME`
- `AWS_S3_CUSTOM_DOMAIN`

## 11. Business Logic Details
Leave submission (`/leave/apply/`):
- Computes working days (Mon-Fri, excluding holidays)
- Computes `requested_units` based on portion:
  - full day = `1.00`
  - half day = `0.50`
  - quarter day = `0.25`
- Validates no overlapping pending/approved leave for same employee
- Enforces per-minute request rate limit
- Checks leave balance across calendar years
- Saves as `PENDING`
- Accepts supporting files; combined file size per submission is capped at 10 GB
- Sends notification to recipients based on settings

Approval:
- Admin/HR approve/reject in `/leave/approvals/`
- Balance consumed only on approval
- Balance released if an already-approved request changes away from approved

## 12. Admin and Audit Operations
Admin can:
- Create users and assign role/manager
- Enable/disable users
- Delete users
- Maintain leave policies and reason presets
- Review and export leave records
- Inspect audit trail

Audit captures:
- `LEAVE_CREATED`
- `LEAVE_EDITED`
- `LEAVE_CANCELLED`
- `LEAVE_APPROVED`
- `LEAVE_REJECTED`

## 13. Useful Commands
List users quickly:
```bash
python manage.py shell -c "from django.contrib.auth import get_user_model; U=get_user_model(); print(list(U.objects.values_list('username','email','role','is_active','can_portal_login')))"
```

Set or reset password:
```bash
python manage.py changepassword <username>
```

Create admin:
```bash
python manage.py createsuperuser
```

Run checks/tests:
```bash
python manage.py check
python manage.py test
```

## 14. Troubleshooting
Common issues and fixes:

### OTP prints in terminal instead of email inbox
Cause:
- `EMAIL_HOST` empty or backend set to console
Fix:
- Configure SMTP values in `.env`
- Use app password for Gmail SMTP
- Restart server after env changes

### "Wrong username/password" even though user exists
Check:
- User `is_active=True`
- `can_portal_login=True` (unless staff/superuser)
- Password is usable (admin-created users initially get unusable password until OTP reset)

### `send_mail` returns `0`
Cause:
- SMTP accepted no recipients or misconfigured transport
Fix:
- Validate `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, recipient email, TLS/SSL flags

### Migration error: `admin.0001_initial applied before users.0001_initial`
Cause:
- DB history created before custom user migration setup
Fix (local dev):
- Remove stale DB and rerun migrations from clean state
- Ensure custom user model is present before first migration in new environments

### Styles look plain or broken
Check:
- `DEBUG=1` in local mode
- `static/css/app.css` exists and loads at `/static/css/app.css`

## 15. Security and Production Notes
- Never commit `.env` or secrets
- Set `DEBUG=0` in production
- Configure strict `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
- Use real SMTP credentials securely
- Prefer managed DB and object storage in production
- Add HTTPS termination (reverse proxy) for deployment

## 16. Current Limitations
- Automated test coverage is minimal and should be expanded for full production confidence
- Desktop EXE launcher source scripts are not currently tracked in this snapshot (only backend web app source is guaranteed here)

## 17. License and Ownership
This repository currently does not include an explicit `LICENSE` file. Add one before public distribution.
