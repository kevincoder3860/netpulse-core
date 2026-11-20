from django.db import migrations, models


def backfill_duration_value(apps, schema_editor):
    HotspotPlan = apps.get_model('billing', 'HotspotPlan')
    HotspotPlan.objects.all().update(
        duration_value=models.F('duration_minutes'),
        duration_unit='minutes',
    )


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0004_hotspotplan_currency'),
    ]

    operations = [
        migrations.AddField(
            model_name='hotspotplan',
            name='duration_value',
            field=models.PositiveIntegerField(default=60),
        ),
        migrations.AddField(
            model_name='hotspotplan',
            name='duration_unit',
            field=models.CharField(
                choices=[('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days')],
                default='minutes',
                max_length=10,
            ),
        ),
        migrations.RunPython(backfill_duration_value, migrations.RunPython.noop),
    ]
