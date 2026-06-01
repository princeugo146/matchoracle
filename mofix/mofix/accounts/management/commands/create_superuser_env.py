"""
Management command: create_superuser_env

Creates a superuser from environment variables. Designed for automated
deployment on Railway where interactive prompts are not available.

Usage:
    python manage.py create_superuser_env

Environment variables:
    DJANGO_SUPERUSER_EMAIL     — superuser email (required)
    DJANGO_SUPERUSER_PASSWORD  — superuser password (required)
    DJANGO_SUPERUSER_USERNAME  — superuser username (defaults to email)
    DJANGO_SUPERUSER_FIRST_NAME — first name (optional)
"""
import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a superuser from environment variables (non-interactive)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            default=os.environ.get('DJANGO_SUPERUSER_EMAIL', ''),
            help='Superuser email (or set DJANGO_SUPERUSER_EMAIL env var)',
        )
        parser.add_argument(
            '--password',
            default=os.environ.get('DJANGO_SUPERUSER_PASSWORD', ''),
            help='Superuser password (or set DJANGO_SUPERUSER_PASSWORD env var)',
        )
        parser.add_argument(
            '--username',
            default=os.environ.get('DJANGO_SUPERUSER_USERNAME', ''),
            help='Superuser username (defaults to email)',
        )
        parser.add_argument(
            '--first-name',
            default=os.environ.get('DJANGO_SUPERUSER_FIRST_NAME', 'Admin'),
            help='Superuser first name',
        )
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update password if user already exists',
        )

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        password = options['password'].strip()
        username = options['username'].strip() or email
        first_name = options['first_name'].strip()

        if not email:
            raise CommandError(
                'Email is required. Set DJANGO_SUPERUSER_EMAIL or pass --email.'
            )
        if not password:
            raise CommandError(
                'Password is required. Set DJANGO_SUPERUSER_PASSWORD or pass --password.'
            )
        if len(password) < 8:
            raise CommandError('Password must be at least 8 characters.')

        if User.objects.filter(email=email).exists():
            if options['update']:
                user = User.objects.get(email=email)
                user.set_password(password)
                user.is_staff = True
                user.is_superuser = True
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Superuser updated: {email}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Superuser already exists: {email} (use --update to change password)')
                )
            return

        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'✓ Superuser created successfully!\n'
                f'  Email:    {email}\n'
                f'  Username: {username}\n'
                f'  Admin panel: /panel/dashboard/\n'
                f'  Django admin: /admin/'
            )
        )
