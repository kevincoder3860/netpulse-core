from decimal import Decimal
from django.db import transaction
from apps.billing.models import Transaction
from apps.radius.models import RadCheck, RadReply

def process_successful_payment(transaction_id: str):
    """
    Atomic transaction processing and FreeRADIUS authorization.
    """
    with transaction.atomic():
        txn = Transaction.objects.select_for_update().get(id=transaction_id)
        if txn.status == 'COMPLETED':
            return txn

        plan = txn.plan
        user_mac = txn.phone_number  # Or client MAC address identifier

        # 1. Update Transaction Status
        txn.status = 'COMPLETED'
        txn.save()

        # 2. Insert FreeRADIUS Access Credentials
        RadCheck.objects.using('radius_db').update_or_create(
            username=user_mac,
            attribute='Cleartext-Password',
            defaults={'op': ':=', 'value': user_mac}
        )

        # 3. Set Session Timeout (Validity Duration in Seconds)
        session_seconds = plan.duration_minutes * 60
        RadReply.objects.using('radius_db').update_or_create(
            username=user_mac,
            attribute='Session-Timeout',
            defaults={'op': ':=', 'value': str(session_seconds)}
        )

        # 4. Set Bandwidth Limits (MikroTik Format: Tx/Rx Rate)
        if plan.max_download_kbps or plan.max_upload_kbps:
            download = plan.max_download_kbps or 0
            upload = plan.max_upload_kbps or 0
            rate_limit = f"{upload}k/{download}k"
            RadReply.objects.using('radius_db').update_or_create(
                username=user_mac,
                attribute='Mikrotik-Rate-Limit',
                defaults={'op': ':=', 'value': rate_limit}
            )

        return txn
