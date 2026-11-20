import logging

from celery import shared_task

from apps.billing.models import MpesaGatewayConfiguration, Transaction
from apps.billing.mpesa import MpesaGatewayError, query_stk_status
from apps.billing.services import process_successful_payment

logger = logging.getLogger(__name__)


@shared_task
def process_mpesa_callback_task(payload):
    """Verify callback transactions with Daraja before changing payment state."""
    try:
        stk_callback = payload.get('Body', {}).get('stkCallback', {})
        checkout_request_id = stk_callback.get('CheckoutRequestID')
        if not isinstance(checkout_request_id, str) or not checkout_request_id:
            logger.warning('M-Pesa callback missing CheckoutRequestID')
            return 'ignored'

        try:
            payment = Transaction.objects.select_related('tenant').get(
                checkout_request_id=checkout_request_id,
            )
        except Transaction.DoesNotExist:
            logger.warning('M-Pesa callback references an unknown checkout request')
            return 'ignored'

        if payment.status != 'PENDING':
            return payment.status.lower()
        try:
            configuration = payment.tenant.mpesa_gateway
        except MpesaGatewayConfiguration.DoesNotExist:
            logger.warning('M-Pesa callback received without tenant gateway configuration')
            return 'retry'
        if not configuration.is_configured:
            logger.warning('M-Pesa callback received with incomplete gateway configuration')
            return 'retry'

        try:
            provider_status = query_stk_status(configuration, checkout_request_id)
        except (MpesaGatewayError, ValueError):
            logger.exception('Could not verify M-Pesa callback with Daraja')
            return 'retry'
        if str(provider_status.get('ResponseCode')) != '0' or provider_status.get('ResultCode') is None:
            logger.info('Daraja has not returned a final result for the callback transaction')
            return 'pending'

        if str(provider_status['ResultCode']) == '0':
            process_successful_payment(str(payment.id))
            return 'completed'
        else:
            payment.status = 'FAILED'
            payment.save(update_fields=['status', 'updated_at'])
            return 'failed'
    except Exception:
        logger.exception('Error processing M-Pesa callback')
        return 'retry'
