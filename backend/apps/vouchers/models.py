from django.db import models
from django.utils import timezone
from apps.tenants.models import Tenant
from apps.routers.models import NAS
from apps.billing.models import HotspotPlan


class Voucher(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='vouchers')
    router = models.ForeignKey(NAS, on_delete=models.SET_NULL, null=True, blank=True, related_name='vouchers')
    plan = models.ForeignKey(HotspotPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='vouchers')
    code = models.CharField(max_length=32, unique=True)
    assigned_mac = models.CharField(max_length=17, blank=True, default='')
    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def status(self):
        return 'USED' if self.used_at else 'NOT_USED'


class Recharge(models.Model):
    METHOD_CHOICES = [('SYSTEM', 'System'), ('VOUCHER', 'Voucher'), ('MANUAL', 'Manual')]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='recharges')
    username = models.CharField(max_length=64)
    mac_address = models.CharField(max_length=17, blank=True, default='')
    plan = models.ForeignKey(HotspotPlan, on_delete=models.SET_NULL, null=True, blank=True)
    router = models.ForeignKey(NAS, on_delete=models.SET_NULL, null=True, blank=True)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='SYSTEM')
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def status(self):
        return 'ACTIVE' if self.expires_at and self.expires_at > timezone.now() else 'EXPIRED'
