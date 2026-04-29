#!/bin/bash
echo "Setting up MatchOracle..."
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py collectstatic --noinput
echo ""
echo "Creating superuser (admin account)..."
python manage.py createsuperuser
echo ""
echo "Setup complete! Run: python manage.py runserver"
