from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('billing', '0002_blockedstknumber_salesagent_commissionrecord')]

    operations = [
        migrations.RenameField(
            model_name='hotspotplan',
            old_name='max_download_kbps',
            new_name='download_speed_kbps',
        ),
        migrations.RenameField(
            model_name='hotspotplan',
            old_name='max_upload_kbps',
            new_name='upload_speed_kbps',
        ),
        migrations.RenameField(
            model_name='hotspotplan',
            old_name='simultaneous_use',
            new_name='simultaneous_devices',
        ),
        migrations.AlterField(
            model_name='hotspotplan',
            name='download_speed_kbps',
            field=models.IntegerField(default=5120),
        ),
        migrations.AlterField(
            model_name='hotspotplan',
            name='upload_speed_kbps',
            field=models.IntegerField(default=2048),
        ),
    ]