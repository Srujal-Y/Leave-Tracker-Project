web: python manage.py migrate --noinput && python manage.py bootstrap_leave_data && gunicorn leave_tracker_project.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
