from django.db import models
from apps.tenants.models import Tenant
from apps.routers.models import NAS


class TrafficSample(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='traffic_samples')
    router = models.ForeignKey(NAS, on_delete=models.CASCADE, related_name='traffic_samples')
    timestamp = models.DateTimeField(auto_now_add=True)
    tx_bytes = models.BigIntegerField(default=0)
    rx_bytes = models.BigIntegerField(default=0)
    cpu_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    memory_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    disk_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    router_memory_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)


class ClientActivity(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='client_activity')
    mac_address = models.CharField(max_length=17)
    activity_date = models.DateField()
    minutes_online = models.PositiveIntegerField(default=0)
    upload_bytes = models.BigIntegerField(default=0)
    download_bytes = models.BigIntegerField(default=0)

    class Meta:
        unique_together = [('tenant', 'mac_address', 'activity_date')]
