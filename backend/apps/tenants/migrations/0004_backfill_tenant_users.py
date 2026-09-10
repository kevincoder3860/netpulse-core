from django.db import migrations


def backfill_profiles(apps, schema_editor):
    TenantUser = apps.get_model('tenants', 'TenantUser')
    Tenant = apps.get_model('tenants', 'Tenant')
    User = apps.get_model('auth', 'User')
    for user in User.objects.all():
        if TenantUser.objects.filter(user_id=user.id).exists():
            continue
        if user.is_superuser:
            TenantUser.objects.create(user_id=user.id, role='SUPERADMIN')
            continue
        tenant = Tenant.objects.filter(email__iexact=user.email).first()
        if tenant:
            TenantUser.objects.create(user_id=user.id, tenant_id=tenant.id, role='VENDOR')


class Migration(migrations.Migration):
    dependencies = [('tenants', '0003_tenantuser')]
    operations = [migrations.RunPython(backfill_profiles, migrations.RunPython.noop)]
