from django.db import models
from django.conf import settings
import base64
import hashlib
import os
from cryptography.fernet import Fernet, InvalidToken
from apps.tenants.models import Tenant
from apps.routers.models import NAS


class MpesaGatewayConfiguration(models.Model):
    class Environment(models.TextChoices):
        SANDBOX = 'sandbox', 'Sandbox'
        PRODUCTION = 'production', 'Production'

    class MerchantType(models.TextChoices):
        PAYBILL = 'CustomerPayBillOnline', 'Paybill'
        BUY_GOODS = 'CustomerBuyGoodsOnline', 'Till / Buy Goods'

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='mpesa_gateway')
    environment = models.CharField(max_length=12, choices=Environment.choices, default=Environment.SANDBOX)
    merchant_type = models.CharField(max_length=32, choices=MerchantType.choices, default=MerchantType.PAYBILL)
    shortcode = models.CharField(max_length=20)
    consumer_key_encrypted = models.TextField()
    consumer_secret_encrypted = models.TextField()
    passkey_encrypted = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @staticmethod
    def _cipher():
        key_material = os.environ.get('MPESA_CREDENTIALS_ENCRYPTION_KEY', '').strip() or settings.SECRET_KEY
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(key_material.encode()).digest())
        return Fernet(derived_key)

    @classmethod
    def encrypt_credential(cls, value):
        return cls._cipher().encrypt(value.encode()).decode()

    @classmethod
    def decrypt_credential(cls, value):
        return cls._cipher().decrypt(value.encode()).decode()

    def set_credentials(self, *, consumer_key=None, consumer_secret=None, passkey=None):
        for field, value in (
            ('consumer_key_encrypted', consumer_key),
            ('consumer_secret_encrypted', consumer_secret),
            ('passkey_encrypted', passkey),
        ):
            if value:
                setattr(self, field, self.encrypt_credential(value))

    def get_credentials(self):
        try:
            return {
                'consumer_key': self.decrypt_credential(self.consumer_key_encrypted),
                'consumer_secret': self.decrypt_credential(self.consumer_secret_encrypted),
                'passkey': self.decrypt_credential(self.passkey_encrypted),
            }
        except InvalidToken:
            raise ValueError(
                'Saved M-Pesa credentials cannot be decrypted. Re-enter the credentials or restore the encryption key.'
            ) from None

    @property
    def is_configured(self):
        return bool(
            self.shortcode
            and self.consumer_key_encrypted
            and self.consumer_secret_encrypted
            and self.passkey_encrypted
        )


class HotspotPlan(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='plans')
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='KES', editable=False)
    duration_minutes = models.IntegerField(default=60)
    duration_value = models.PositiveIntegerField(default=60)
    duration_unit = models.CharField(
        max_length=10,
        choices=(('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days')),
        default='minutes',
    )
    download_speed_kbps = models.IntegerField(default=5120)
    upload_speed_kbps = models.IntegerField(default=2048)
    simultaneous_devices = models.IntegerField(default=1, help_text="Number of devices allowed at the same time")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.tenant.business_name}"

    @property
    def limit_uptime(self):
        minutes = self.duration_minutes
        days = minutes // 1440
        hours = (minutes % 1440) // 60
        mins = minutes % 60
        if days > 0:
            return f"{days}d{hours:02d}:{mins:02d}:00"
        return f"{hours:02d}:{mins:02d}:00"

class Transaction(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='transactions')
    nas = models.ForeignKey(NAS, on_delete=models.SET_NULL, null=True, related_name='transactions')
    plan = models.ForeignKey(HotspotPlan, on_delete=models.SET_NULL, null=True, related_name='transactions')
    
    gross_amount = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2)
    vendor_net_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    payment_method = models.CharField(max_length=50, default='MPESA')
    
    # M-Pesa specific fields
    phone_number = models.CharField(max_length=15)
    merchant_request_id = models.CharField(max_length=64, db_index=True)
    checkout_request_id = models.CharField(max_length=64, db_index=True, unique=True)
    mpesa_receipt_number = models.CharField(max_length=32, null=True, blank=True, unique=True)
    raw_callback_payload = models.JSONField(default=dict, blank=True)
    gateway_receipt = models.CharField(max_length=128, blank=True, default='')
    gateway_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    client_mac = models.CharField(max_length=17, help_text="Client device MAC address")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.checkout_request_id} - {self.status}"


class BlockedSTKNumber(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='blocked_stk_numbers')
    phone_number = models.CharField(max_length=20)
    reason = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class SalesAgent(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='sales_agents')
    name = models.CharField(max_length=120)
    phone_number = models.CharField(max_length=20, blank=True, default='')
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)


class CommissionRecord(models.Model):
    agent = models.ForeignKey(SalesAgent, on_delete=models.CASCADE, related_name='commissions')
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='commission_records')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
