from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0005_hotspotplan_dynamic_duration'),
        ('tenants', '0005_tenant_status_changed_at_tenant_status_reason_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='MpesaGatewayConfiguration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('environment', models.CharField(
                    choices=[('sandbox', 'Sandbox'), ('production', 'Production')],
                    default='sandbox',
                    max_length=12,
                )),
                ('merchant_type', models.CharField(
                    choices=[('CustomerPayBillOnline', 'Paybill'), ('CustomerBuyGoodsOnline', 'Till / Buy Goods')],
                    default='CustomerPayBillOnline',
                    max_length=32,
                )),
                ('shortcode', models.CharField(max_length=20)),
                ('consumer_key_encrypted', models.TextField()),
                ('consumer_secret_encrypted', models.TextField()),
                ('passkey_encrypted', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='mpesa_gateway',
                    to='tenants.tenant',
                )),
            ],
        ),
    ]
