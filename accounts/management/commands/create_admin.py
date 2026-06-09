from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Create or update the admin superuser'

    def handle(self, *args, **options):
        email = 'admin@matchoracle.com'
        password = 'MatchOracle@2024'
        
        # Check if user exists
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': 'admin',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        
        # Always update password to ensure it's correct
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.save()
        
        if created:
            self.stdout.write(self.style.SUCCESS(f'✅ Created admin user: {email}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'✅ Updated admin user: {email}'))
        
        self.stdout.write(self.style.SUCCESS(f'Password: {password}'))
