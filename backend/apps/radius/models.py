from django.db import models

class RadCheck(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=64, default='')
    attribute = models.CharField(max_length=64, default='')
    op = models.CharField(max_length=2, default='==')
    value = models.CharField(max_length=253, default='')

    class Meta:
        managed = False
        db_table = 'radcheck'

class RadReply(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=64, default='')
    attribute = models.CharField(max_length=64, default='')
    op = models.CharField(max_length=2, default='=')
    value = models.CharField(max_length=253, default='')

    class Meta:
        managed = False
        db_table = 'radreply'

class RadAcct(models.Model):
    radacctid = models.BigAutoField(primary_key=True)
    acctsessionid = models.CharField(max_length=64, default='')
    acctuniqueid = models.CharField(max_length=32, default='', unique=True)
    username = models.CharField(max_length=64, default='')
    realm = models.CharField(max_length=64, default='', null=True, blank=True)
    nasipaddress = models.GenericIPAddressField(default='')
    nasportid = models.CharField(max_length=32, null=True, blank=True)
    nasporttype = models.CharField(max_length=32, null=True, blank=True)
    acctstarttime = models.DateTimeField(null=True, blank=True)
    acctupdatetime = models.DateTimeField(null=True, blank=True)
    acctstoptime = models.DateTimeField(null=True, blank=True)
    acctinterval = models.IntegerField(null=True, blank=True)
    acctsessiontime = models.PositiveIntegerField(null=True, blank=True)
    acctauthentic = models.CharField(max_length=32, null=True, blank=True)
    connectinfo_start = models.CharField(max_length=120, null=True, blank=True)
    connectinfo_stop = models.CharField(max_length=120, null=True, blank=True)
    acctinputoctets = models.BigIntegerField(null=True, blank=True)
    acctoutputoctets = models.BigIntegerField(null=True, blank=True)
    calledstationid = models.CharField(max_length=50, default='')
    callingstationid = models.CharField(max_length=50, default='')
    acctterminatecause = models.CharField(max_length=32, default='')
    servicetype = models.CharField(max_length=32, null=True, blank=True)
    framedprotocol = models.CharField(max_length=32, null=True, blank=True)
    framedipaddress = models.GenericIPAddressField(null=True, blank=True)
    framedipv6address = models.GenericIPAddressField(null=True, blank=True)
    framedipv6prefix = models.GenericIPAddressField(null=True, blank=True)
    framedinterfaceid = models.CharField(max_length=44, null=True, blank=True)
    delegatedipv6prefix = models.GenericIPAddressField(null=True, blank=True)
    class_field = models.CharField(db_column='class', max_length=64, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'radacct'

class Nas(models.Model):
    id = models.AutoField(primary_key=True)
    nasname = models.CharField(max_length=128)
    shortname = models.CharField(max_length=32, null=True, blank=True)
    type = models.CharField(max_length=30, default='other')
    ports = models.IntegerField(null=True, blank=True)
    secret = models.CharField(max_length=60)
    server = models.CharField(max_length=64, null=True, blank=True)
    community = models.CharField(max_length=50, null=True, blank=True)
    description = models.CharField(max_length=200, default='RADIUS Client')

    class Meta:
        managed = False
        db_table = 'nas'
