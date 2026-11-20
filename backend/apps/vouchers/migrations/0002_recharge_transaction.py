import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_transaction_payment_metadata'),
        ('vouchers', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='recharge',
            name='transaction',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='recharge',
                to='billing.transaction',
            ),
        ),
    ]
