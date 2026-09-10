from django.db import models
from apps.tenants.models import Tenant
from apps.routers.models import NAS

class HotspotPlan(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='plans')
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='KES', editable=False)
    duration_minutes = models.IntegerField(default=60)
    download_speed_kbps = models.IntegerField(default=5120)
    upload_speed_kbps = models.IntegerField(default=2048)
    simultaneous_devices = models.IntegerField(default=1, help_text="Number of devices allowed at the same time")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.tenant.business_name}"

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
