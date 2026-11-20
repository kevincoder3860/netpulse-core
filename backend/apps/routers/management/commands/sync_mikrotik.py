import logging
from django.core.management.base import BaseCommand
from apps.billing.models import HotspotPlan
from apps.routers.models import NAS

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sync active Hotspot Plans to MikroTik RouterOS as User Profiles'

    def handle(self, *args, **options):
        active_plans = HotspotPlan.objects.filter(is_active=True)
        routers = NAS.objects.filter(is_online=True, type='mikrotik')

        self.stdout.write(f"Starting sync for {active_plans.count()} plans across {routers.count()} routers.")

        for router in routers:
            try:
                from librouteros import connect
                connection = connect(
                    host=router.nas_ip,
                    username=router.api_username,
                    password=router.api_password,
                    port=router.api_port or 8728,
                )
                try:
                    profile_path = connection.path('/ip/hotspot/user/profile')
                    existing_profiles = {p.get('name'): p.get('.id') for p in profile_path}

                    for plan in active_plans.filter(tenant=router.tenant):
                        rate_limit = f"{plan.upload_speed_kbps}k/{plan.download_speed_kbps}k"

                        if plan.name in existing_profiles:
                            profile_path.update(**{
                                '.id': existing_profiles[plan.name],
                                'rate-limit': rate_limit,
                                'shared-users': str(plan.simultaneous_devices)
                            })
                            msg = f"[MikroTik API] Profile updated: {plan.name} on {router.nas_ip}"
                            self.stdout.write(self.style.SUCCESS(msg))
                            logger.info(msg)
                        else:
                            profile_path.add(
                                name=plan.name,
                                **{'rate-limit': rate_limit, 'shared-users': str(plan.simultaneous_devices)}
                            )
                            msg = f"[MikroTik API] Profile created: {plan.name} on {router.nas_ip}"
                            self.stdout.write(self.style.SUCCESS(msg))
                            logger.info(msg)
                finally:
                    connection.close()
            except Exception as exc:
                err_msg = f"[MikroTik API] Failed to connect: {router.nas_ip} - {exc}"
                self.stderr.write(self.style.ERROR(err_msg))
                logger.error(err_msg)

        self.stdout.write(self.style.SUCCESS("MikroTik sync completed."))
