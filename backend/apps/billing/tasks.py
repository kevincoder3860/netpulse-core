from celery import shared_task
import logging
from apps.billing.models import Transaction
from apps.billing.services import process_successful_payment

logger = logging.getLogger(__name__)

@shared_task
def process_mpesa_callback_task(payload):
    """
    Processes the M-Pesa STK Push callback asynchronously.
    """
    try:
        # Daraja callback structure: Body.stkCallback
        stk_callback = payload.get('Body', {}).get('stkCallback', {})
        result_code = stk_callback.get('ResultCode')
        checkout_request_id = stk_callback.get('CheckoutRequestID')

        if not checkout_request_id:
            logger.error("M-Pesa callback missing CheckoutRequestID")
            return

        try:
            txn = Transaction.objects.get(checkout_request_id=checkout_request_id)
        except Transaction.DoesNotExist:
            logger.error(f"Transaction not found for CheckoutRequestID: {checkout_request_id}")
            return

        if txn.status == 'COMPLETED':
            logger.warning(f"Transaction {checkout_request_id} already processed")
            return

        # Store raw payload for audit
        txn.raw_callback_payload = payload

        if result_code == 0:
            # Payment successful
            callback_metadata = stk_callback.get('CallbackMetadata', {}).get('Item', [])
            mpesa_receipt_number = None
            for item in callback_metadata:
                if item.get('Name') == 'MpesaReceiptNumber':
                    mpesa_receipt_number = item.get('Value')
                    break
            
            if mpesa_receipt_number:
                txn.mpesa_receipt_number = mpesa_receipt_number
            txn.save()

            # Trigger radius provisioning and complete transaction
            process_successful_payment(str(txn.id))
        else:
            # Payment failed or cancelled
            txn.status = 'FAILED'
            txn.save()

    except Exception as e:
        logger.exception("Error processing M-Pesa callback")
