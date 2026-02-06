# Leave Tracker

**Status:** Active  
**License:** Internal Use  
**Tech:** Python, Django, PostgreSQL (Neon), WhiteNoise

Badges (optional):
- Build: `GitHub Actions`
- Python: `3.12`
- Django: `5.x`

---

## Table of Contents

1. Features  
2. Tech Stack  
3. Quick Start (Local)  
4. Authentication & Password Reset  
5. Admin Panel (Portal UI)  
6. Core Pages  
7. Data Model (Simplified)  
8. Admin Management  
9. Environment Variables  
10. Deploy with Neon DB  
11. Deploy on AWS (Neon DB)  
12. Deploy on Railway (Neon DB)  
13. Deploy on Render (Neon DB)  
14. Deploy on Fly.io (Neon DB)  
15. Deploy on Heroku (Neon DB)  
16. Deploy with Docker (ECS/Fargate/Any)  
17. CI/CD (GitHub Actions)  
18. Screenshots (Optional)  
19. Troubleshooting  
20. Roadmap  

An internal, portal-based leave tracking system built with Django. Employees request leave and keep their profile up to date; HR/Admin can review company activity.

This version is **company-controlled**:
- **No public signup**: employees are created by staff via the **Admin Panel** (portal UI).
- **Login uses email-as-username** (Django username field stores the employee email).
- **Password reset uses email OTP** (6-digit code, 10-minute expiry).
- **Profile photos** should be persisted in production using a **Railway Volume** or **S3**.

---

## Features

- **No public signup**: only staff can create employees.
- **Email login**: login uses **email as username** + password.
- **Password reset (OTP)**: "Forgot password?" emails a **6-digit OTP** (10 min expiry) and allows setting a new password.
- **Apply leave**: date range, portion, label, and reason.
- **Company Leave Board**: shows all employees’ leaves (profile card layout).
- **Employee profile**: photo, phone number, current project, and tasks.
- **Admin Panel (portal UI)**: create employees, enable/disable users, delete users.
- **Django Admin**: still available for superusers (advanced management).
- **Days display**: all UI displays leave usage in **days** (not units).

---

## Tech Stack

- **Python** + **Django**
- **SQLite** for local dev
- **PostgreSQL (Neon)** supported via `DATABASE_URL`
- **WhiteNoise** for static files

---

## Quick Start (Local)

### 1) Create venv + install deps
```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

python -m pip install -U pip
python -m pip install -r requirements.txt
```

### 2) Configure environment
Copy `.env.example` → `.env` and edit values as needed:
```env
DEBUG=1
SECRET_KEY=change-me
# Optional: SERVE_MEDIA=1
```

### 3) Migrate + run server
```bash
python manage.py migrate
python manage.py runserver
```

Open:
- `http://127.0.0.1:8000/` (Portal)
- `http://127.0.0.1:8000/admin/` (Admin)

---

## Authentication & Password Reset

- **Login uses email-as-username + password**.
- **Forgot password**: enter your email → receive a **6-digit OTP** → set a new password.
- OTP expiry: **10 minutes**.

Email delivery uses Django’s email backend (configure SMTP via env vars). In local dev, if SMTP is not configured, emails can be printed to the console backend.

---

## Admin Panel (Portal UI)

Staff-only admin panel (same UI as the portal):
- List users
- Create employees
- Enable/disable users
- Delete users

URL:
```
/admin-panel/
```

Employees created here get an unusable password by default and should use **Forgot password** to set their password via OTP.

---

## Core Pages

- **Login**: `/login/`
- **Forgot password**: `/password-reset/`
- **Admin Panel** (staff only): `/admin-panel/`
- **Dashboard**: `/me/`
- **Apply Leave**: `/leave/apply/`
- **Company Leave Board**: `/leave/company/`
- **Admin**: `/admin/`

---

## Data Model (Simplified)

Key model: `LeaveRequest`
- `employee` (User)
- `leave_type` (optional)
- `leave_label`
- `start_date`, `end_date`
- `portion` (full/half/quarter)
- `requested_units` (shown as **days** in UI)
- `reason_text`
- `created_at`

Validation:
- `end_date` must be **>= start_date**

---

## Admin Management

Use Django Admin to:
- create staff/superusers
- manage leave types and reason presets
- manage user profiles and photos
- view and manage all leave requests

Create admin user:
```bash
python manage.py createsuperuser
```

---

## Environment Variables

Minimum required:
```env
DEBUG=1
SECRET_KEY=change-me
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

Optional:
```env
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://localhost,https://127.0.0.1

# OTP email delivery (configure for production)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.yourprovider.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_smtp_username
EMAIL_HOST_PASSWORD=your_smtp_password
EMAIL_USE_TLS=1
DEFAULT_FROM_EMAIL=no-reply@yourcompany.com

# Media (profile photos)
# For Railway: set SERVE_MEDIA=1 AND attach a Volume mounted at /app/media for persistence.
SERVE_MEDIA=1
MEDIA_ROOT=/app/media

# Optional: S3 media storage (recommended long-term)
AWS_STORAGE_BUCKET_NAME=your-bucket
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_REGION_NAME=us-east-1
# AWS_S3_CUSTOM_DOMAIN=cdn.yourcompany.com  (optional)
```

---

## Deploy with Neon DB

This app supports Neon PostgreSQL via `DATABASE_URL`.

1. Create a Neon project
2. Copy the **direct** connection string
3. Set it in `.env` or hosting env vars:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

Then:
```bash
python manage.py migrate
```

---

## Deploy on AWS (Neon DB)

You can deploy this app on AWS using **EC2** (manual) or **Elastic Beanstalk** (managed). Below are both options.

### Option A: EC2 (manual Ubuntu server)

1) **Launch EC2**
- Ubuntu 22.04
- Allow inbound **SSH (22)** and **HTTP (80)**, **HTTPS (443)**

2) **SSH into server**
```bash
ssh ubuntu@YOUR_EC2_PUBLIC_IP
```

3) **Install system dependencies**
```bash
sudo apt update && sudo apt -y install python3-venv python3-pip nginx
```

4) **Clone your repo**
```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

5) **Create venv + install deps**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

6) **Set environment variables**
Create `.env`:
```env
DEBUG=0
SECRET_KEY=your_secret
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
ALLOWED_HOSTS=YOUR_EC2_PUBLIC_IP
```

7) **Migrate + collect static**
```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

8) **Run with Gunicorn**
```bash
pip install gunicorn
gunicorn alemeno_hr.wsgi:application --bind 0.0.0.0:8000
```

9) **Configure Nginx reverse proxy**
```bash
sudo nano /etc/nginx/sites-available/leave-tracker
```
Paste:
```
server {
    listen 80;
    server_name YOUR_EC2_PUBLIC_IP;

    location /static/ {
        alias /home/ubuntu/<your-repo>/staticfiles/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Enable:
```bash
sudo ln -s /etc/nginx/sites-available/leave-tracker /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

10) **Create admin**
```bash
python manage.py createsuperuser
```

---

### Option B: Elastic Beanstalk (managed)

1) Install EB CLI:
```bash
pip install awsebcli
```

2) Initialize:
```bash
eb init -p python-3.11 leave-tracker
```

3) Create environment:
```bash
eb create leave-tracker-env
```

4) Set env vars:
```bash
eb setenv DEBUG=0 SECRET_KEY=your_secret DATABASE_URL="postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require"
```

5) Deploy:
```bash
eb deploy
```

---

## Project Structure (High Level)

```
alemeno_hr/
  settings.py
  urls.py
leave/
  models.py
  views.py
portal/
  views.py
  forms.py
templates/
static/
```

---

## Deploy on Railway (Neon DB)

1) Push code to GitHub  
2) Create a Railway project → Deploy from GitHub  
3) Add env vars:
```
DEBUG=0
SECRET_KEY=your_secret
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
```
4) Set build command:
```
pip install -r requirements.txt
```
5) Set start command:
```
python manage.py migrate && python manage.py collectstatic --noinput && gunicorn alemeno_hr.wsgi:application --bind 0.0.0.0:$PORT
```

---

## Deploy on Render (Neon DB)

1) New Web Service → connect GitHub repo  
2) Build command:
```
pip install -r requirements.txt
```
3) Start command:
```
python manage.py migrate && python manage.py collectstatic --noinput && gunicorn alemeno_hr.wsgi:application --bind 0.0.0.0:$PORT
```
4) Add env vars:
```
DEBUG=0
SECRET_KEY=your_secret
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

---

## Deploy on Fly.io (Neon DB)

1) Install Fly CLI  
2) Launch app:
```
fly launch
```
3) Set secrets:
```
fly secrets set DEBUG=0 SECRET_KEY=your_secret DATABASE_URL="postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require"
```
4) Deploy:
```
fly deploy
```

---

## Deploy on Heroku (Neon DB)

1) Create app:
```
heroku create
```
2) Set config:
```
heroku config:set DEBUG=0 SECRET_KEY=your_secret DATABASE_URL="postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require"
```
3) Deploy:
```
git push heroku main
```
4) Run migrations:
```
heroku run python manage.py migrate
```

---

## Deploy with Docker (for ECS/Fargate or any container host)

### Dockerfile
Create `Dockerfile`:
```
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -U pip && pip install -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["gunicorn", "alemeno_hr.wsgi:application", "--bind", "0.0.0.0:8000"]
```

### Build + Run
```
docker build -t leave-tracker .
docker run -p 8000:8000 --env-file .env leave-tracker
```

---

## CI/CD (GitHub Actions)

Create `.github/workflows/ci.yml`:
```
name: Django CI
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -U pip
      - run: pip install -r requirements.txt
      - run: python manage.py check
```

---

## Screenshots (Optional)

You can add screenshots by creating a `docs/` folder and referencing images here.
Example:
```
docs/login.png
docs/dashboard.png
docs/company-board.png
```

Then add:
```
![Login](docs/login.png)
```

---

## Troubleshooting

**Migrations fail after deleting db.sqlite3**
```bash
python manage.py migrate
```

**Forgot admin password**
Use:
```bash
python manage.py changepassword <username>
```

---

## Roadmap Ideas

- Email notifications
- Role-based approvals
- Calendar integration
- OTP-based password reset
- Leave balance policies

---

## License / Internal Use

This project is intended for internal company use.


## OTP and Media API Integration (Production)

### OTP email API
You can send OTP using SMTP or Resend. Configure one of the following:

```env
# SMTP
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_gmail_username
EMAIL_HOST_PASSWORD=your_app_password
EMAIL_USE_TLS=1
DEFAULT_FROM_EMAIL=hr@yourcompany.com

# Optional leave notifications
EMAIL_NOTIFY_ON_LEAVE=1
HR_NOTIFICATION_EMAILS=hr@yourcompany.com,team@yourcompany.com

# Resend (optional)
OTP_PROVIDER=resend
RESEND_API_KEY=re_xxx
RESEND_API_URL=https://api.resend.com/emails
```

### Profile photo storage API (S3 / Cloudflare R2)
```env
AWS_STORAGE_BUCKET_NAME=your-bucket
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
AWS_S3_REGION_NAME=auto
AWS_S3_ENDPOINT_URL=https://<accountid>.r2.cloudflarestorage.com
AWS_S3_ADDRESSING_STYLE=path
AWS_S3_SIGNATURE_VERSION=s3v4
```

When these values are set, `django-storages` is enabled automatically and profile photos are served from object storage.


## Railway Raw Variable Script (Copy/Paste)

A full ready-to-paste Railway variables template is included at:

- `railway.env.raw.example`

### Railway CLI quick import
If you use Railway CLI, you can import the same variables by converting this file to your shell env and setting each variable.

Example (macOS/Linux):
```bash
set -a
source railway.env.raw.example
set +a
```
Then configure them in Railway dashboard Raw Editor (or with Railway CLI commands in your workflow).


### Railway crash checklist
If Railway still crashes on startup, verify:

1. `DATABASE_URL` is a **real** connection string (not placeholder text).
2. If using S3/R2, set valid `AWS_*` values; otherwise leave `AWS_*` unset.
3. `SECRET_KEY` is set to a real value.
4. `ALLOWED_HOSTS` includes your Railway/public domain.
5. Startup command runs migrations (`python manage.py migrate`) before gunicorn.

This project now ignores obvious placeholder values for `DATABASE_URL` and optional `AWS_*` so copy/paste templates do not crash startup.
