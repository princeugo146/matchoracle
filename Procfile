web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn matchoracle.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
worker: celery -A matchoracle worker --loglevel=info --concurrency=2
beat: celery -A matchoracle beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
