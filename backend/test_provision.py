import sys
import os
import traceback
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netpulse.settings')
django.setup()

import librouteros
from django.utils import timezone
from apps.routers.models import Router

def run_diagnostic():
    print("=" * 60)
    print("NETPULSE MIKROTIK PROVISIONING DIAGNOSTIC TEST")
    print("=" * 60)

    simulated_payload = {
        "api_ip": "192.168.56.101",
        "api_port": 8728,
        "api_username": "netpulse_admin",
        "api_password": "123",
        "radius_ip": "192.168.56.1",
        "secret": "AKmtOC4jYuQDCgll",
        "router_name": "router-01"
    }

    target_ip = simulated_payload.get('api_ip')
    target_port = int(simulated_payload.get('api_port', 8728))
    target_user = simulated_payload.get('api_username', 'netpulse_admin').strip()
    target_pass = simulated_payload.get('api_password', '123').strip()
    radius_ip = simulated_payload.get('radius_ip', '192.168.56.1').strip()
    radius_secret = simulated_payload.get('secret', 'AKmtOC4jYuQDCgll').strip()

    print(f"\n[1/4] PARSED PARAMETERS:")
    print(f"      - Target NAS IP:   {target_ip}")
    print(f"      - API Username:    '{target_user}'")

    print(f"\n[2/4] TESTING LIBROUTEROS CONNECTION...")
    try:
        api = librouteros.connect(
            host=target_ip,
            username=target_user,
            password=target_pass,
            port=target_port,
            timeout=10
        )
        print("      SUCCESS: Connected to MikroTik API!")
    except Exception as e:
        print(f"      FAILED: Connection error -> {e}")
        traceback.print_exc()
        return

    print(f"\n[3/4] EXECUTING PROVISIONING COMMANDS...")
    try:
        api.path('/system/identity').set(name=simulated_payload['router_name'])
        radius_path = api.path('/radius')
        existing = list(radius_path.select('.id', 'address').where(address=radius_ip))
        if existing:
            item_id = existing[0]['.id']
            radius_path.set(**{'.id': item_id, 'secret': radius_secret, 'service': 'hotspot'})
        else:
            radius_path.add(service='hotspot', address=radius_ip, secret=radius_secret, comment='NetPulse RADIUS')

        api.close()
        print("         [OK] Commands executed successfully.")
    except Exception as e:
        print(f"      FAILED: API Execution Error -> {e}")
        traceback.print_exc()
        if 'api' in locals():
            api.close()
        return

    print(f"\n[4/4] UPDATING DJANGO DATABASE MODEL...")
    try:
        router = Router.objects.filter(nas_ip=target_ip).first() or Router.objects.first()
        if router:
            router.api_username = target_user
            router.api_password = target_pass
            router.api_port = target_port
            router.is_online = True
            router.status = 'online'
            router.last_ping = timezone.now()
            router.save()
            print(f"      SUCCESS: Router '{router.nasname}' set to ONLINE in DB!")
    except Exception as e:
        print(f"      FAILED: Database status update error -> {e}")
        traceback.print_exc()

    print("\n" + "=" * 60)

if __name__ == '__main__':
    run_diagnostic()
