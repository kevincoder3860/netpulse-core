from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('routers', '0002_nas_mac_address'),
    ]

    operations = [
        migrations.AddField(
            model_name='nas',
            name='api_password',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AddField(
            model_name='nas',
            name='api_port',
            field=models.IntegerField(default=8728),
        ),
        migrations.AddField(
            model_name='nas',
            name='api_username',
            field=models.CharField(default='admin', max_length=64),
        ),
        migrations.AddField(
            model_name='nas',
            name='last_provisioned_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='nas',
            name='nas_ip',
            field=models.CharField(blank=True, default='', help_text='Router LAN/IP used for API access', max_length=45),
        ),
        migrations.AddField(
            model_name='nas',
            name='radius_server_ip',
            field=models.CharField(blank=True, default='10.10.0.5', max_length=45),
        ),
        migrations.AddField(
            model_name='nas',
            name='shared_secret',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AlterField(
            model_name='nas',
            name='nasname',
            field=models.CharField(help_text='Router identity / NAS name', max_length=128),
        ),
        migrations.AlterField(
            model_name='nas',
            name='secret',
            field=models.CharField(help_text='RADIUS shared secret', max_length=60),
        ),
        migrations.AlterField(
            model_name='nas',
            name='shortname',
            field=models.CharField(help_text='Venue location label', max_length=32),
        ),
    ]
