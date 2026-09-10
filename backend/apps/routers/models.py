from django.db import models
from apps.tenants.models import Tenant


class NAS(models.Model):
    NAS_TYPE_CHOICES = (
        ('mikrotik', 'MikroTik'),
        ('coovachilli', 'CoovaChilli'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='routers')
    nasname = models.CharField(max_length=128, help_text="Router identity / NAS name")
    shortname = models.CharField(max_length=32, help_text="Venue location label")
    nas_ip = models.CharField(max_length=45, blank=True, default='', help_text="Router LAN/IP used for API access")
    mac_address = models.CharField(max_length=17, blank=True, default='')
    secret = models.CharField(max_length=60, help_text="RADIUS shared secret")
    api_port = models.IntegerField(default=8728)
    api_username = models.CharField(max_length=64, default='admin')
    api_password = models.CharField(max_length=128, blank=True, default='')
    radius_server_ip = models.CharField(max_length=45, blank=True, default='10.10.0.5')
    shared_secret = models.CharField(max_length=128, blank=True, default='')
    type = models.CharField(max_length=30, choices=NAS_TYPE_CHOICES, default='mikrotik')
    is_online = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=(('online', 'Online'), ('offline', 'Offline')), default='offline')
    last_ping = models.DateTimeField(null=True, blank=True)
    last_provisioned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Network Access Server"
        verbose_name_plural = "Network Access Servers"

    def __str__(self):
        return self.shortname or self.nasname
