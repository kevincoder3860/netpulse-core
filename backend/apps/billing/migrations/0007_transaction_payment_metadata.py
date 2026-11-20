from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0006_mpesa_gateway_configuration'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='gateway_receipt',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AddField(
            model_name='transaction',
            name='gateway_fee',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='transaction',
            name='paid_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
