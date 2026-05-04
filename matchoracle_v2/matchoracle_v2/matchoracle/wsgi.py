"""WSGI config for MatchOracle.

Exposes the WSGI callable as a module-level variable named ``application``.
Gunicorn is pointed at this module via the Procfile / Railway start command.
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matchoracle.settings')

application = get_wsgi_application()

