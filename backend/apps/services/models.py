from django.db import models
from apps.tenants.models import Tenant


class BurstProfile(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='burst_profiles')
    name = models.CharField(max_length=100)
    rate_limit = models.CharField(max_length=64)
    burst_limit = models.CharField(max_length=64, blank=True, default='')
    burst_threshold = models.CharField(max_length=64, blank=True, default='')
    burst_time = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)


class FUPProfile(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='fup_profiles')
    name = models.CharField(max_length=100)
    quota_gb = models.DecimalField(max_digits=10, decimal_places=2)
    throttled_rate = models.CharField(max_length=64)
    reset_period = models.CharField(max_length=32, default='monthly')
    is_active = models.BooleanField(default=True)
