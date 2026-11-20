import hashlib
import hmac
import json
import logging
import re
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)

PAYSTACK_API_ROOT = 'https://api.paystack.co'


class PaystackGatewayError(Exception):
    def __init__(self, message, *, code='PAYSTACK_GATEWAY_ERROR', gateway_status=None):
        super().__init__(message)
        self.code = code
        self.gateway_status = gateway_status


def normalize_kenyan_phone_number(phone_number):
    digits = re.sub(r'\D', '', str(phone_number or ''))
    if digits.startswith('0'):
        digits = f'254{digits[1:]}'
    elif len(digits) == 9 and digits[0] in '17':
        digits = f'254{digits}'

    if not re.fullmatch(r'254[17]\d{8}', digits):
        raise PaystackGatewayError(
            'Enter a valid Kenyan mobile number, such as 0712345678.',
            code='INVALID_PHONE_NUMBER',
        )
    return f'+{digits}'


def _tenant_secret(tenant):
    try:
        secret_key = tenant.get_paystack_secret_key()
    except ValueError as exc:
        raise PaystackGatewayError(str(exc), code='INVALID_PAYSTACK_CONFIGURATION') from exc
    if not secret_key:
        secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '').strip()
    if not secret_key:
        raise PaystackGatewayError(
            'Paystack is not configured for this vendor.',
            code='PAYSTACK_NOT_CONFIGURED',
        )
    return secret_key


def _request_json(url, *, secret_key, method='GET', payload=None):
    headers = {
        'Authorization': f'Bearer {secret_key}',
        'User-Agent': 'NeonISP-Billing/1.0',
    }
    body = None
    if payload is not None:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(payload).encode('utf-8')
    request = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(request, timeout=15) as response:
            response_text = response.read().decode('utf-8', errors='replace')
            status_code = response.status
    except HTTPError as exc:
        response_text = exc.read().decode('utf-8', errors='replace')
        try:
            error_body = json.loads(response_text)
        except ValueError:
            error_body = {}
        provider_message = error_body.get('message') if isinstance(error_body, dict) else None
        log_message = (
            provider_message
            if isinstance(provider_message, str) and provider_message
            else response_text.strip() or 'No error message returned.'
        )
        logger.warning('Paystack request failed with HTTP %s: %s', exc.code, log_message)
        raise PaystackGatewayError(
            provider_message
            if isinstance(provider_message, str) and provider_message
            else 'Paystack could not process the request.',
            code='PAYSTACK_HTTP_ERROR',
            gateway_status=exc.code,
        ) from None
    except (URLError, TimeoutError, OSError):
        logger.exception('Paystack request could not reach the provider')
        raise PaystackGatewayError(
            'Unable to reach Paystack. Please try again.',
            code='PAYSTACK_UNAVAILABLE',
        ) from None

    try:
        result = json.loads(response_text)
    except ValueError:
        logger.warning('Paystack returned invalid JSON with HTTP %s', status_code)
        raise PaystackGatewayError(
            'Paystack returned an invalid response.',
            code='PAYSTACK_INVALID_RESPONSE',
            gateway_status=status_code,
        ) from None
    if not isinstance(result, dict):
        raise PaystackGatewayError(
            'Paystack returned an invalid response.',
            code='PAYSTACK_INVALID_RESPONSE',
            gateway_status=status_code,
        )
    return result


def initiate_mobile_money_charge(tenant, *, phone_number, amount):
    secret_key = _tenant_secret(tenant)
    email = tenant.billing_email or tenant.email
    if not email:
        raise PaystackGatewayError(
            'Set a billing email in the vendor payment settings.',
            code='PAYSTACK_EMAIL_REQUIRED',
        )

    try:
        amount_cents = int(round(Decimal(str(amount)) * 100))
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise PaystackGatewayError(
            'Payment amount must be a valid KES amount.',
            code='INVALID_PAYMENT_AMOUNT',
        ) from exc
    if amount_cents <= 0:
        raise PaystackGatewayError(
            'Payment amount must be greater than zero.',
            code='INVALID_PAYMENT_AMOUNT',
        )

    normalized_phone = normalize_kenyan_phone_number(phone_number)
    response = _request_json(
        f'{PAYSTACK_API_ROOT}/charge',
        secret_key=secret_key,
        method='POST',
        payload={
            'email': email,
            'amount': amount_cents,
            'currency': 'KES',
            'mobile_money': {
                'phone': normalized_phone,
                'provider': 'mpesa',
            },
        },
    )
    if response.get('status') is not True:
        message = response.get('message')
        logger.warning(
            'Paystack charge was rejected: %s',
            message if isinstance(message, str) and message else 'No error message returned.',
        )
        raise PaystackGatewayError(
            message if isinstance(message, str) and message else 'Paystack did not accept the payment request.',
            code='PAYSTACK_CHARGE_REJECTED',
        )

    data = response.get('data')
    reference = data.get('reference') if isinstance(data, dict) else None
    if not isinstance(reference, str) or not reference.strip() or len(reference) > 64:
        raise PaystackGatewayError(
            'Paystack returned an invalid payment reference.',
            code='PAYSTACK_INVALID_REFERENCE',
        )
    return {
        'reference': reference,
        'phone_number': normalized_phone,
        'amount_cents': amount_cents,
        'message': (
            data.get('display_text')
            if isinstance(data.get('display_text'), str) and data.get('display_text')
            else response.get('message') or 'Check your phone for the M-Pesa payment prompt.'
        ),
    }


def verify_mobile_money_charge(tenant, reference):
    secret_key = _tenant_secret(tenant)
    response = _request_json(
        f'{PAYSTACK_API_ROOT}/transaction/verify/{quote(reference, safe="")}',
        secret_key=secret_key,
    )
    if response.get('status') is not True or not isinstance(response.get('data'), dict):
        message = response.get('message')
        raise PaystackGatewayError(
            message if isinstance(message, str) and message else 'Paystack could not verify the transaction.',
            code='PAYSTACK_VERIFICATION_FAILED',
        )
    return response['data']


def verify_webhook_signature(tenant, raw_body, signature):
    if not isinstance(signature, str) or not signature.strip():
        return False
    secret_key = _tenant_secret(tenant)
    expected = hmac.new(
        secret_key.encode('utf-8'),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())
