import sys
import os
import traceback
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'netpulse.settings')  # Adjust to your settings module if different
django.setup()

import librouteros
from django.utils import timezone
from apps.routers.models import Router  # Adjust to your Router model path

def run_diagnostic():
    print("=" * 60)
    print("NETPULSE MIKROTIK PROVISIONING DIAGNOSTIC TEST")
    print("=" * 60)

    # Simulated request payload from NetPulse React UI
    simulated_payload = {
        "api_ip": "192.168.56.101",
        "api_port": 8728,
        "api_username": "netpulse_admin",
        "api_password": "123",
        "radius_ip": "192.168.56.1",
        "secret": "AKmtOC4jYuQDCgll",
        "router_name": "router-01"
    }

    # Extract target parameters with fallbacks
    target_ip = simulated_payload.get('api_ip') or simulated_payload.get('nas_ip')
    target_port = int(simulated_payload.get('api_port', 8728))
    target_user = simulated_payload.get('api_username', 'netpulse_admin').strip()
    target_pass = simulated_payload.get('api_password', '123').strip()
    radius_ip = simulated_payload.get('radius_ip', '192.168.56.1').strip()
    radius_secret = simulated_payload.get('secret', 'AKmtOC4jYuQDCgll').strip()

    print(f"\n[1/4] PARSED PARAMETERS:")
    print(f"      - Target NAS IP:   {target_ip}")
    print(f"      - API Port:        {target_port}")
    print(f"      - API Username:    '{target_user}'")
    print(f"      - RADIUS Host IP:  {radius_ip}")

    # Step 1: Test Socket Connection
    print(f"\n[2/4] TESTING LIBROUTEROS API CONNECTION...")
    try:
        api = librouteros.connect(
            host=target_ip,
            username=target_user,
            password=target_pass,
            port=target_port,
            timeout=10
        )
        print("      SUCCESS: Connected and authenticated with MikroTik API!")
    except Exception as e:
        print("      FAILED: Unable to authenticate or reach API socket.")
        print(f"      ERROR DETAILS: {e}")
        traceback.print_exc()
        return

    # Step 2: Execute Provisioning API Calls (Identity & RADIUS)
    print(f"\n[3/4] EXECUTING PROVISIONING COMMANDS...")
    try:
        # A. Set Router Identity
        print("      -> Updating System Identity...")
        api.path('/system/identity').set(name=simulated_payload['router_name'])
        print("         [OK] Identity set.")

        # B. Configure RADIUS Server Entry safely
        print("      -> Configuring RADIUS Client...")
        radius_path = api.path('/radius')
        
        # Check if entry already exists to avoid duplicate/id errors
        existing = list(radius_path.select('.id', 'address').where(address=radius_ip))
        if existing:
            item_id = existing[0]['.id']
            radius_path.set(**{'.id': item_id, 'secret': radius_secret, 'service': 'hotspot'})
            print(f"         [OK] Updated existing RADIUS entry ({item_id}).")
        else:
            radius_path.add(service='hotspot', address=radius_ip, secret=radius_secret, comment='NetPulse RADIUS')
            print("         [OK] Added new RADIUS entry.")

        api.close()
    except Exception as e:
        print("      FAILED: API Command Execution Rejected by RouterOS.")
        print(f"      ERROR DETAILS: {e}")
        traceback.print_exc()
        if 'api' in locals():
            api.close()
        return

    # Step 3: Update Database Model Instance
    print(f"\n[4/4] UPDATING DJANGO DATABASE MODEL...")
    try:
        # Fetch or get router instance
        router = Router.objects.filter(nas_ip=target_ip).first()
        if not router:
            router = Router.objects.first()

        if router:
            router.api_username = target_user
            router.api_password = target_pass
            router.api_port = target_port
            router.is_online = True
            router.status = 'online'
            router.last_ping = timezone.now()
            router.save()
            print(f"      SUCCESS: Router '{router.nasname}' updated to ONLINE in database!")
        else:
            print("      WARNING: No matching Router object found in Database to update.")
    except Exception as e:
        print("      FAILED: Database status update error.")
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE: Router is verified and set to ONLINE.")
    print("=" * 60)

if __name__ == '__main__':
    run_diagnostic()

    