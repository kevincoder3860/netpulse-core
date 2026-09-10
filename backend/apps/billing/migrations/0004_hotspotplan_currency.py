from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('billing', '0003_rename_hotspot_plan_bandwidth_fields')]

    operations = [
        migrations.AddField(
            model_name='hotspotplan',
            name='currency',
            field=models.CharField(default='KES', editable=False, max_length=10),
        ),
    ]