from django.core.management.base import BaseCommand

from apps.routers.models import NAS


class Command(BaseCommand):
    help = 'Delete NAS records by nasname/IP address.'

    def add_arguments(self, parser):
        parser.add_argument('nasname', nargs='?', default='192.168.56.101')

    def handle(self, *args, **options):
        nasname = options['nasname']
        deleted, _ = NAS.objects.filter(nasname=nasname).delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted} record(s) with nasname={nasname}.'))