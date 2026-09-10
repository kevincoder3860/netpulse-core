from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from apps.tenants.models import TenantUser


class Command(BaseCommand):
    help = 'Create a NetPulse SuperAdmin account without a vendor tenant.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--password', required=True)

    def handle(self, *args, **options):
        User = get_user_model()
        email = options['email'].strip().lower()
        if User.objects.filter(username=email).exists():
            raise CommandError('A user with this email already exists.')
        user = User.objects.create_superuser(username=email, email=email, password=options['password'])
        TenantUser.objects.create(user=user, role=TenantUser.Role.SUPERADMIN, tenant=None)
        self.stdout.write(self.style.SUCCESS(f'SuperAdmin created: {email}'))
