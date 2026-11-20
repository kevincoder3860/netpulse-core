import uuid

from django.conf import settings
from django.db import models

from apps.tenants.models import Tenant


class Customer(models.Model):
    class ServiceType(models.TextChoices):
        HOTSPOT = 'hotspot', 'Hotspot'
        PPPOE = 'pppoe', 'PPPoE'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        EXPIRED = 'expired', 'Expired'
        BLOCKED = 'blocked', 'Blocked'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='customers')
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_profile',
    )
    username = models.CharField(max_length=64)
    name = models.CharField(max_length=160)
    phone_number = models.CharField(max_length=20)
    mac_address = models.CharField(max_length=17, blank=True, default='')
    service_type = models.CharField(max_length=16, choices=ServiceType.choices, default=ServiceType.HOTSPOT)
    plan_name = models.CharField(max_length=120, blank=True, default='')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    uptime_seconds = models.PositiveBigIntegerField(default=0)
    download_bytes = models.PositiveBigIntegerField(default=0)
    upload_bytes = models.PositiveBigIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'username'], name='unique_customer_username_per_tenant'),
        ]


class Invoice(models.Model):
    class Status(models.TextChoices):
        PAID = 'PAID', 'Paid'
        UNPAID = 'UNPAID', 'Unpaid'
        OVERDUE = 'OVERDUE', 'Overdue'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='invoices')
    invoice_number = models.CharField(max_length=40, unique=True)
    customer_name = models.CharField(max_length=160)
    customer_phone = models.CharField(max_length=20, blank=True, default='')
    plan_name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UNPAID)
    payment_ref = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']


class SupportTicket(models.Model):
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        URGENT = 'URGENT', 'Urgent'

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        IN_PROGRESS = 'IN_PROGRESS', 'In progress'
        RESOLVED = 'RESOLVED', 'Resolved'
        CLOSED = 'CLOSED', 'Closed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='support_tickets')
    ticket_number = models.CharField(max_length=24, unique=True, editable=False)
    customer_name = models.CharField(max_length=160)
    customer_phone = models.CharField(max_length=20, blank=True, default='')
    subject = models.CharField(max_length=180)
    description = models.TextField()
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            latest_id = SupportTicket.objects.order_by('-created_at').values_list('pk', flat=True).first()
            self.ticket_number = f'TCK-{str(latest_id or 0)[-6:]}-{uuid.uuid4().hex[:4].upper()}'
        super().save(*args, **kwargs)


class TicketMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=160)
    is_staff = models.BooleanField(default=False)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class PlatformSettings(models.Model):
    platform_name = models.CharField(max_length=120, default='NetPulse Cloud Core')
    currency = models.CharField(max_length=8, default='KES')
    default_commission_pct = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    mpesa_paybill = models.CharField(max_length=32, blank=True, default='')
    mpesa_env = models.CharField(max_length=16, choices=(('sandbox', 'Sandbox'), ('production', 'Production')), default='sandbox')
    radius_auth_port = models.PositiveSmallIntegerField(default=1812)
    radius_acct_port = models.PositiveSmallIntegerField(default=1813)
    session_timeout_secs = models.PositiveIntegerField(default=86400)
    support_email = models.EmailField(default='support@netpulse.cloud')
    maintenance_mode = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Platform settings'


class PlatformUser(models.Model):
    class Role(models.TextChoices):
        SUPERADMIN = 'SUPERADMIN', 'Super Admin'
        SUPPORT_AGENT = 'SUPPORT_AGENT', 'Support Agent'
        BILLING_ADMIN = 'BILLING_ADMIN', 'Billing Admin'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='platform_profile')
    role = models.CharField(max_length=20, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)
