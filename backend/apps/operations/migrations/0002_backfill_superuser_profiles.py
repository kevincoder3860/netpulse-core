from django.conf import settings
from django.db import migrations


def backfill_superuser_profiles(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    User = apps.get_model(app_label, model_name)
    PlatformUser = apps.get_model('operations', 'PlatformUser')
    database = schema_editor.connection.alias

    for user in User.objects.using(database).filter(is_superuser=True).iterator():
        PlatformUser.objects.using(database).update_or_create(
            user_id=user.pk,
            defaults={'role': 'SUPERADMIN'},
        )


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(backfill_superuser_profiles, migrations.RunPython.noop),
    ]
