from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('routers', '0001_initial')]

    operations = [
        migrations.AddField('nas', 'mac_address', models.CharField(blank=True, default='', max_length=17)),
    ]