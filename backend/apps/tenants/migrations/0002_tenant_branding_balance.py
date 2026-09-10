from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('tenants', '0001_initial')]

    operations = [
        migrations.AddField('tenant', 'balance', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
        migrations.AddField('tenant', 'logo_url', models.URLField(blank=True, default='')),
        migrations.AddField('tenant', 'brand_color', models.CharField(default='#14b8a6', max_length=7)),
        migrations.AddField('tenant', 'welcome_headline', models.CharField(blank=True, default='Welcome to our Wi-Fi', max_length=255)),
        migrations.AddField('tenant', 'terms_of_service', models.TextField(blank=True, default='By connecting you agree to our terms of service.')),
    ]