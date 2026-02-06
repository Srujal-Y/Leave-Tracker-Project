# Alemeno Leave Tracker (Dev Run - Windows)

This project uses **SQLite** for local development.

## 1) Create venv + install deps

```powershell
cd "<project folder>"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2) Reset the database (recommended the first time, and after upgrades)

If you previously ran an older ZIP, your `db.sqlite3` may have an older schema.
That commonly causes errors like:
- `sqlite3.OperationalError: no such column: ...`
- `sqlite3.OperationalError: no such table: ...`

**Fix (safe in dev):**

```powershell
Remove-Item .\db.sqlite3 -ErrorAction SilentlyContinue
python manage.py makemigrations
python manage.py migrate
```

## 3) Create an admin user

```powershell
python manage.py createsuperuser
```

## 4) Run

```powershell
python manage.py runserver
```

Open:
- Portal: http://127.0.0.1:8000/
- Admin:  http://127.0.0.1:8000/admin/

## 5) CSS looks broken / plain

This happens when static files are not loading.
Ensure you are running the latest ZIP where `STATIC_URL` is set to `/static/`.
