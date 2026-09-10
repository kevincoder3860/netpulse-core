import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Create a superuser from environment variables if it does not exist'

    def handle(self, *args, **options):
        User = get_user_model()
        
        # Get credentials from environment variables with defaults
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'kevin')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'kevin@gmail.com')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '@123456789')
        
        # Check if user already exists by email or username
        if User.objects.filter(email=email).exists():
            self.stdout.write(
                self.style.WARNING(f'Superuser with email {email} already exists. Skipping creation.')
            )
            return
        
        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(f'Superuser with username {username} already exists. Skipping creation.')
            )
            return
        
        # Create the superuser
        User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created superuser: {username} ({email})')
        )
