web: python scripts/bootstrap_data.py && gunicorn dash_app:server --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120 --access-logfile - --error-logfile -
