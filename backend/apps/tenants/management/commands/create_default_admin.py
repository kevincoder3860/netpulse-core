from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.tenants.models import TenantUser


class Command(BaseCommand):
    help = 'Create or update the default NetPulse SuperAdmin account.'

    username = 'admin'
    email = 'admin@gmail.com'
    password = 'admin123'

    def handle(self, *args, **options):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=self.username,
            defaults={'email': self.email},
        )

        user.email = self.email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(self.password)
        user.save()

        TenantUser.objects.update_or_create(
            user=user,
            defaults={'role': TenantUser.Role.SUPERADMIN, 'tenant': None},
        )

        action = 'created' if created else 'updated'
        self.stdout.write(self.style.SUCCESS(f'Default SuperAdmin {action}: {self.username} ({self.email})'))
