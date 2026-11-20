from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('routers', '0004_nas_status')]

    operations = [
        migrations.AddField(
            model_name='nas',
            name='last_seen',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]