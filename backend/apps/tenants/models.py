from django.db import models
from django.conf import settings
import uuid

class Tenant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        SUSPENDED = 'SUSPENDED', 'Suspended'
        CLOSED = 'CLOSED', 'Closed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business_name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    status_reason = models.TextField(blank=True, default='')
    status_changed_at = models.DateTimeField(null=True, blank=True)
    platform_commission_pct = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    payout_details = models.JSONField(default=dict, blank=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    logo_url = models.URLField(blank=True, default='')
    brand_color = models.CharField(max_length=7, default='#14b8a6')
    welcome_headline = models.CharField(max_length=255, blank=True, default='Welcome to our Wi-Fi')
    terms_of_service = models.TextField(blank=True, default='By connecting you agree to our terms of service.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.business_name


class TenantUser(models.Model):
    class Role(models.TextChoices):
        SUPERADMIN = 'SUPERADMIN', 'SuperAdmin'
        VENDOR = 'VENDOR', 'Vendor'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tenant_profile')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name='users')
    role = models.CharField(max_length=20, choices=Role.choices)

    def __str__(self):
        return f'{self.user.username} ({self.role})'


class TenantStaff(models.Model):
    class Role(models.TextChoices):
        MANAGER = 'MANAGER', 'Manager'
        TECHNICIAN = 'TECHNICIAN', 'Technician'
        CASHIER = 'CASHIER', 'Cashier'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='staff_profile')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='staff')
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username} ({self.role})'


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='tenant_audit_actions')
    tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=80)
    reason = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
