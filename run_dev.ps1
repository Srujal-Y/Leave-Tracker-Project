# Quick dev run (Windows PowerShell)
# 1) Activate venv
if (Test-Path .\.venv\Scripts\Activate.ps1) {
  . .\.venv\Scripts\Activate.ps1
} else {
  Write-Host "No .venv found. Create it first: py -m venv .venv" -ForegroundColor Yellow
  exit 1
}

python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
