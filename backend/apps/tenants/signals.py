from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(
    post_save,
    sender=settings.AUTH_USER_MODEL,
    dispatch_uid='tenants.provision_platform_profile',
)
def provision_platform_profile(sender, instance, raw=False, using='default', **_kwargs):
    if raw or sender is not instance.__class__ or _kwargs.get('signal') is not post_save:
        return

    from django.apps import apps

    PlatformUser = apps.get_model('operations', 'PlatformUser')
    profile = PlatformUser.objects.using(using).filter(user_id=instance.pk)
    if instance.is_superuser:
        profile.update_or_create(
            defaults={'role': 'SUPERADMIN'},
            user_id=instance.pk,
        )
    else:
        profile.filter(role='SUPERADMIN').update(role='SUPPORT_AGENT')
