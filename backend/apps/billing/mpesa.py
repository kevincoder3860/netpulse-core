import base64
import json
import logging
import re
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from django.core.cache import cache

logger = logging.getLogger(__name__)


class MpesaGatewayError(Exception):
    def __init__(
        self,
        message,
        *,
        code='MPESA_GATEWAY_ERROR',
        gateway_status=None,
        provider_error_code=None,
    ):
        super().__init__(message)
        self.code = code
        self.gateway_status = gateway_status
        self.provider_error_code = provider_error_code


def _api_root(configuration):
    environment = str(configuration.environment).strip().lower()
    if environment == 'sandbox':
        return 'https://sandbox.safaricom.co.ke'
    if environment == 'production':
        return 'https://api.safaricom.co.ke'
    logger.error('Unsupported M-Pesa environment configured: %r', configuration.environment)
    raise MpesaGatewayError('M-Pesa environment must be either sandbox or production.')


def _request_json(url, *, method='GET', headers=None, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=body, headers=headers or {}, method=method)
    safe_headers = {
        name: '<redacted>' if name.lower() == 'authorization' else value
        for name, value in (headers or {}).items()
    }
    safe_payload = dict(payload) if payload is not None else None
    if safe_payload is not None and 'Password' in safe_payload:
        safe_payload['Password'] = '<redacted>'
    logger.info(
        'Daraja request: method=%s url=%s headers=%s json=%s',
        method,
        url,
        safe_headers,
        json.dumps(safe_payload) if safe_payload is not None else None,
    )
    try:
        with urlopen(request, timeout=15) as response:
            status_code = response.status
            response_text = response.read().decode('utf-8', errors='replace')
    except HTTPError as exc:
        response_text = exc.read().decode('utf-8', errors='replace')
        try:
            error_body = json.loads(response_text)
        except ValueError:
            error_body = {}
        if not isinstance(error_body, dict):
            error_body = {}

        provider_error_code = (
            error_body.get('errorCode')
            or error_body.get('error_code')
            or error_body.get('code')
        )
        provider_message = (
            error_body.get('errorMessage')
            or error_body.get('error_description')
            or error_body.get('message')
            or response_text
            or str(exc.reason)
        )
        if not isinstance(provider_message, str):
            provider_message = str(provider_message)
        logger.error(
            'Daraja HTTP request failed: status=%s url=%s provider_error=%s response=%s',
            exc.code,
            url,
            provider_message,
            response_text or str(exc.reason),
        )
        raise MpesaGatewayError(
            provider_message,
            code='DARAJA_HTTP_ERROR',
            gateway_status=exc.code,
            provider_error_code=str(provider_error_code) if provider_error_code else None,
        ) from None
    except (URLError, TimeoutError, OSError) as exc:
        logger.error(
            'Daraja request failed: status=unavailable url=%s error=%s',
            url,
            str(getattr(exc, 'reason', exc)),
        )
        raise MpesaGatewayError('Unable to reach the M-Pesa gateway. Please try again.') from None
    try:
        result = json.loads(response_text)
    except ValueError:
        logger.error(
            'Daraja returned invalid JSON: status=%s url=%s error=%s',
            status_code,
            url,
            response_text,
        )
        raise MpesaGatewayError('The M-Pesa gateway returned an invalid response.') from None
    if not isinstance(result, dict):
        logger.error(
            'Daraja returned an unexpected response: status=%s url=%s error=%s',
            status_code,
            url,
            response_text,
        )
        raise MpesaGatewayError('The M-Pesa gateway returned an invalid response.')
    return result


def _access_token(configuration):
    cache_key = f'mpesa-access-token-{configuration.pk}-{configuration.environment}'
    token = cache.get(cache_key)
    if token:
        return token

    credentials = configuration.get_credentials()
    auth_value = base64.b64encode(
        f"{credentials['consumer_key']}:{credentials['consumer_secret']}".encode()
    ).decode()
    response = _request_json(
        f'{_api_root(configuration)}/oauth/v1/generate?grant_type=client_credentials',
        headers={'Authorization': f'Basic {auth_value}'},
    )
    token = response.get('access_token')
    if not isinstance(token, str) or not token:
        logger.warning(
            'Daraja OAuth response did not contain an access token: error=%s error_description=%s',
            response.get('error'),
            response.get('error_description'),
        )
        raise MpesaGatewayError('M-Pesa credentials could not be authenticated.')
    try:
        expires_in = max(60, int(response.get('expires_in', 3600)) - 60)
    except (ValueError, TypeError):
        expires_in = 3000
    cache.set(cache_key, token, timeout=expires_in)
    return token


def _timestamp_and_password(configuration):
    credentials = configuration.get_credentials()
    timestamp = datetime.now(ZoneInfo('Africa/Nairobi')).strftime('%Y%m%d%H%M%S')
    password = base64.b64encode(
        f"{configuration.shortcode}{credentials['passkey']}{timestamp}".encode()
    ).decode()
    return timestamp, password


def _normalize_phone_number(phone_number):
    if phone_number is None:
        raise MpesaGatewayError('M-Pesa phone number is required.')

    digits = re.sub(r'\D', '', str(phone_number).strip())
    if not digits:
        raise MpesaGatewayError('M-Pesa phone number is required.')

    if digits.startswith('0'):
        digits = f'254{digits[1:]}'
    elif digits.startswith('+254'):
        digits = digits[1:]
    elif digits.startswith('254'):
        pass
    elif len(digits) == 9:
        digits = f'254{digits}'
    elif not digits.startswith('254'):
        digits = f'254{digits.lstrip("0")}'

    if len(digits) != 12 or not digits.startswith('254'):
        raise MpesaGatewayError('M-Pesa phone number must be a valid Safaricom number.')

    return digits


def initiate_stk_push(configuration, *, phone_number, amount, reference, callback_url):
    transaction_type = configuration.merchant_type
    valid_transaction_types = {
        'CustomerPayBillOnline',
        'CustomerBuyGoodsOnline',
    }
    if transaction_type not in valid_transaction_types:
        raise MpesaGatewayError(
            'M-Pesa merchant type must be CustomerPayBillOnline or CustomerBuyGoodsOnline.'
        )

    normalized_phone_number = _normalize_phone_number(phone_number)
    access_token = _access_token(configuration)
    timestamp, password = _timestamp_and_password(configuration)
    business_shortcode = str(configuration.shortcode)
    payload = {
        'BusinessShortCode': business_shortcode,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': transaction_type,
        'Amount': amount,
        'PartyA': normalized_phone_number,
        'PartyB': business_shortcode,
        'PhoneNumber': normalized_phone_number,
        'CallBackURL': callback_url,
        'AccountReference': reference,
        'TransactionDesc': 'Hotspot Plan Purchase',
    }
    response = _request_json(
        f'{_api_root(configuration)}/mpesa/stkpush/v1/processrequest',
        method='POST',
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        },
        payload=payload,
    )
    if str(response.get('ResponseCode')) != '0':
        logger.warning('Daraja rejected STK request (code %s)', response.get('ResponseCode', 'unknown'))
        message = response.get('CustomerMessage')
        raise MpesaGatewayError(
            message if isinstance(message, str) and message else 'M-Pesa did not accept the payment request.'
        )
    checkout_id = response.get('CheckoutRequestID')
    merchant_id = response.get('MerchantRequestID')
    if not isinstance(checkout_id, str) or not checkout_id or not isinstance(merchant_id, str) or not merchant_id:
        logger.warning('Daraja STK response omitted request identifiers')
        raise MpesaGatewayError('M-Pesa returned an incomplete payment response.')
    return {
        'checkout_request_id': checkout_id,
        'merchant_request_id': merchant_id,
        'message': response.get('CustomerMessage') or 'Check your phone for the M-Pesa prompt.',
    }


def query_stk_status(configuration, checkout_request_id):
    timestamp, password = _timestamp_and_password(configuration)
    access_token = _access_token(configuration)
    return _request_json(
        f'{_api_root(configuration)}/mpesa/stkpushquery/v1/query',
        method='POST',
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        },
        payload={
            'BusinessShortCode': configuration.shortcode,
            'Password': password,
            'Timestamp': timestamp,
            'CheckoutRequestID': checkout_request_id,
        },
    )
