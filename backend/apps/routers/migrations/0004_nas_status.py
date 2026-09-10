from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('routers', '0003_nas_api_password_nas_api_port_nas_api_username_and_more')]

    operations = [
        migrations.AddField(
            model_name='nas',
            name='status',
            field=models.CharField(
                choices=[('online', 'Online'), ('offline', 'Offline')],
                default='offline',
                max_length=16,
            ),
        ),
    ]