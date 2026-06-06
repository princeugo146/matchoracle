"""
Management command: create_superuser
-------------------------------------
Creates the default MatchOracle admin superuser if one does not already exist.

Usage:
    python manage.py create_superuser

The command is idempotent — running it more than once is safe.  If a user
with username "admin" already exists the command exits without making any
changes.

Credentials created:
    username : admin
    email    : admin@matchoracle.com
    password : Admin@2024Secure!
"""

import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


def _generate_password(length: int = 20) -> str:
    """Return a cryptographically-secure random password."""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    # Guarantee at least one character from each required class.
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.isupper() for c in pwd)
            and any(c.islower() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in string.punctuation for c in pwd)
        ):
            return pwd


class Command(BaseCommand):
    help = (
        "Create the default admin superuser (username=admin, "
        "email=admin@matchoracle.com) if it does not already exist."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--random-password",
            action="store_true",
            default=False,
            help=(
                "Generate a random secure password instead of using the "
                "default one.  The generated password is printed to stdout."
            ),
        )

    def handle(self, *args, **options):
        User = get_user_model()

        username = "admin"
        email = "admin@matchoracle.com"
        default_password = "Admin@2024Secure!"

        # ── Check for existing superuser ──────────────────────────────────────
        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(
                    f'Superuser with username "{username}" already exists. '
                    "No changes were made."
                )
            )
            return

        # ── Determine password ────────────────────────────────────────────────
        if options["random_password"]:
            password = _generate_password()
            password_source = "randomly generated"
        else:
            password = default_password
            password_source = "default"

        # ── Create superuser ──────────────────────────────────────────────────
        try:
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
            )
        except Exception as exc:  # pragma: no cover
            self.stderr.write(
                self.style.ERROR(f"Failed to create superuser: {exc}")
            )
            raise SystemExit(1)

        # ── Success output ────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS("Superuser created successfully."))
        self.stdout.write(f"  Username : {user.username}")
        self.stdout.write(f"  Email    : {user.email}")
        self.stdout.write(f"  Password : {password}  ({password_source})")
        self.stdout.write(
            self.style.WARNING(
                "Remember to change this password after your first login."
            )
        )
