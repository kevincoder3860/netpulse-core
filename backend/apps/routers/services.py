import hashlib
import ipaddress
import logging
import os
import socket
from datetime import datetime

from django.conf import settings
from django.db import OperationalError
from django.utils import timezone
from django.dispatch import Signal

from .models import NAS

logger = logging.getLogger(__name__)
router_status_changed = Signal()

try:  # pragma: no cover - optional dependency for direct MikroTik API use
    import routeros_api
    from routeros_api import RouterOsApiPool  # type: ignore
    from routeros_api.exceptions import (  # type: ignore
        RouterOsApiCommunicationError,
        RouterOsApiConnectionError,
    )
    _ROUTEROS_API_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency not installed in this environment
    routeros_api = None
    RouterOsApiPool = None
    RouterOsApiCommunicationError = Exception  # type: ignore[assignment, misc]
    RouterOsApiConnectionError = Exception  # type: ignore[assignment, misc]
    _ROUTEROS_API_AVAILABLE = False

try:  # pragma: no cover - optional dependency
    from librouteros import connect as librouteros_connect  # type: ignore
except Exception:  # pragma: no cover - dependency is not installed locally
    librouteros_connect = None

try:  # pragma: no cover - optional dependency
    from librouteros.exceptions import LibRouterosError, TrapError  # type: ignore

    _LIBROUTEROS_EXCEPTIONS = (LibRouterosError, TrapError)
except Exception:  # pragma: no cover - dependency is not installed locally
    _LIBROUTEROS_EXCEPTIONS = ()


def _credential_value(value: object) -> str:
    """Decrypt a configured Fernet credential or use its stored plain-text value."""
    raw = str(value or '').strip()
    if not raw:
        return ''
    if not raw.startswith('gAAAA'):
        return raw

    encryption_key = (
        os.environ.get('CREDENTIAL_ENCRYPTION_KEY', '').strip()
        or settings.CREDENTIAL_ENCRYPTION_KEY
    )
    try:
        from cryptography.fernet import Fernet
        return Fernet(encryption_key.encode()).decrypt(raw.encode()).decode().strip()
    except Exception:
        logger.warning('Stored encrypted router credential could not be decrypted; using it as plaintext')
        return raw


def resolve_router_credentials(router, api_username: object = None, api_password: object = None) -> tuple[str, str]:
    api_user = str(api_username).strip() if api_username is not None else _credential_value(router.api_username)
    api_pass = str(api_password).strip() if api_password is not None else _credential_value(router.api_password)
    return api_user, api_pass


def check_router_status(router, *, timeout: float = 5.0) -> dict:
    """Authenticate to a router and persist its current connection status."""
    host = str(getattr(router, 'nas_ip', None) or getattr(router, 'nasname', None) or '').strip()
    was_online = bool(router.is_online)
    previous_last_seen = router.last_seen
    previous_last_ping = router.last_ping
    error = ''
    connection = None

    try:
        if not host:
            raise ValueError('No router IP or hostname is configured.')
        if librouteros_connect is None:
            raise RuntimeError('The librouteros client is unavailable.')

        username, password = resolve_router_credentials(router)
        if not username or not password:
            raise ValueError('Router API credentials are not configured.')

        connection = librouteros_connect(
            host=host,
            username=username,
            password=password,
            port=int(router.api_port or 8728),
            timeout=timeout,
        )
        list(connection.path('system', 'resource')('print'))
        is_online = True
    except Exception as exc:
        is_online = False
        error = str(exc)
    finally:
        if connection is not None and hasattr(connection, 'close'):
            try:
                connection.close()
            except Exception:
                logger.debug('Failed to close RouterOS health-check connection for %s', host, exc_info=True)

    previous_status = 'online' if was_online else 'offline'
    status_value = 'online' if is_online else 'offline'
    update_fields = []
    if router.is_online != is_online:
        router.is_online = is_online
        update_fields.append('is_online')
    if router.status != status_value:
        router.status = status_value
        update_fields.append('status')

    if is_online:
        checked_at = timezone.now()
        router.last_seen = checked_at
        router.last_ping = checked_at
        update_fields.extend(('last_seen', 'last_ping'))
    if update_fields:
        update_fields.append('updated_at')
        try:
            router.save(update_fields=list(dict.fromkeys(update_fields)))
        except OperationalError as exc:
            logger.warning(
                'Router status could not be saved for NAS %s (%s): %s',
                getattr(router, 'pk', '?'),
                host,
                exc,
            )
            router.is_online = was_online
            router.status = previous_status
            router.last_seen = previous_last_seen
            router.last_ping = previous_last_ping
            return {
                'is_online': was_online,
                'status': previous_status,
                'error': str(exc),
                'last_seen': previous_last_seen,
                'last_ping': previous_last_ping,
            }

    if is_online and not was_online:
        router_status_changed.send(
            sender=NAS,
            router=router,
            previous_status=previous_status,
            status=status_value,
        )

    if is_online:
        logger.info('Router %s is ONLINE', host)
    else:
        logger.warning('Router %s is OFFLINE: %s', host, error)
    return {
        'is_online': is_online,
        'status': status_value,
        'error': error,
        'last_seen': router.last_seen,
        'last_ping': router.last_ping,
    }


def fetch_router_telemetry(router=None, *, host: str | None = None, username: str | None = None, password: str | None = None, port: int | None = None) -> dict:
    """
    Fetch telemetry statistics from a MikroTik router.

    Uses RouterOsApiPool (routeros_api) when available, with:
      plaintext_login=True  – required for RouterOS v7+ API authentication.
      socket_timeout=3.0    – fast failure on unreachable endpoints.
      port=8728             – standard unencrypted MikroTik API port.

    Falls back to librouteros if routeros_api is unavailable.
    All error paths call pool.disconnect() in a finally block so sockets
    are always released (prevents hitting RouterOS max-sessions=20 limit).
    All error paths return HTTP-200-safe JSON so the React polling loop
    never enters an error state on transient failures.
    """
    if isinstance(router, str):
        target_host = router.strip()
        target_user = username
        target_pass = password
        target_port = int(port or 8728)
    elif router is not None:
        target_host = str(getattr(router, 'nas_ip', None) or getattr(router, 'nasname', None) or '').strip()
        resolved_user, resolved_pass = resolve_router_credentials(router)
        target_user = username or resolved_user
        target_pass = password or resolved_pass
        target_port = int(port or getattr(router, 'api_port', None) or 8728)
    else:
        target_host = ''
        target_user = username
        target_pass = password
        target_port = int(port or 8728)

    # Ensure credentials are provided
    if not target_user or not target_pass:
        raise ValueError("Router credentials must be provided either via DB or caller arguments.")

    target_host = (host or target_host or '192.168.56.20').strip()

    # Strip any stray whitespace from credentials before connecting.
    # resolve_router_credentials already strips via _credential_value,
    # but we do it again here as an explicit safety belt.
    target_user = target_user.strip()
    target_pass = target_pass.strip()

    # ------------------------------------------------------------------
    # Primary path: routeros_api (RouterOS v6 + v7 plaintext login)
    # ------------------------------------------------------------------
    if _ROUTEROS_API_AVAILABLE:
        pool = None
        try:
            pool = RouterOsApiPool(
                target_host,
                username=target_user,
                password=target_pass,
                port=target_port,
                plaintext_login=True,
                socket_timeout=3.0,
            )
            api = pool.get_api()

            # --- Interfaces ---
            rx_bytes = 0
            tx_bytes = 0
            primary_interface = 'unknown'
            try:
                interfaces = api.get_resource('/interface').get()
                if interfaces:
                    top = max(
                        interfaces,
                        key=lambda item: int(item.get('rx-byte', 0) or 0) + int(item.get('tx-byte', 0) or 0),
                        default={},
                    )
                    rx_bytes = int(top.get('rx-byte', 0) or 0)
                    tx_bytes = int(top.get('tx-byte', 0) or 0)
                    primary_interface = top.get('name', 'unknown')
            except Exception:
                pass

            # --- System resource ---
            cpu = 0.0
            memory = 0.0
            try:
                res_list = api.get_resource('/system/resource').get()
                if res_list:
                    res = res_list[0]
                    cpu = float(res.get('cpu-load', 0) or 0)
                    total_mem = float(res.get('total-memory', 0) or 0)
                    free_mem = float(res.get('free-memory', 0) or 0)
                    memory = round(((total_mem - free_mem) / total_mem * 100), 2) if total_mem else 0.0
            except Exception:
                pass

            return {
                'status': 'online',
                'rx_bytes': rx_bytes,
                'tx_bytes': tx_bytes,
                'interface': primary_interface,
                'cpu': cpu,
                'memory': memory,
            }

        except RouterOsApiCommunicationError as exc:
            logger.warning('[Telemetry Auth Error] Router %s: %s', target_host, exc)
            return {'status': 'offline', 'detail': 'Authentication or protocol error'}
        except RouterOsApiConnectionError as exc:
            logger.warning('[Telemetry Auth Error] Router %s: %s', target_host, exc)
            return {'status': 'offline', 'detail': 'Authentication or protocol error'}
        except (socket.timeout, TimeoutError) as exc:
            logger.warning('[Telemetry Warning] Router %s unreachable (timed out)', target_host)
            return {'status': 'offline', 'error': str(exc)}
        except Exception as exc:
            exc_str = str(exc)
            if 'timed out' in exc_str.lower() or 'timeout' in exc_str.lower():
                logger.warning('[Telemetry Warning] Router %s unreachable (timed out)', target_host)
                return {'status': 'offline', 'error': exc_str}
            logger.warning('[Telemetry Auth Error] Router %s: %s', target_host, exc_str)
            return {'status': 'offline', 'detail': 'Authentication or protocol error'}
        finally:
            if pool is not None:
                try:
                    pool.disconnect()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Fallback path: librouteros (no plaintext_login support)
    # ------------------------------------------------------------------
    if librouteros_connect is not None:
        connection = None
        try:
            connection = librouteros_connect(
                host=target_host,
                username=target_user,
                password=target_pass,
                port=target_port,
            )
            interfaces = list(connection.path('interface')('print'))
            resources = list(connection.path('system', 'resource')('print'))
            resource = resources[0] if resources else {}
            interface = max(
                interfaces,
                key=lambda item: int(item.get('rx-byte', 0) or 0) + int(item.get('tx-byte', 0) or 0),
                default={},
            )
            total_memory = int(resource.get('total-memory') or 0)
            free_memory = int(resource.get('free-memory') or 0)
            used_memory = max(total_memory - free_memory, 0)
            return {
                'status': 'online',
                'rx_bytes': int(interface.get('rx-byte', 0) or 0),
                'tx_bytes': int(interface.get('tx-byte', 0) or 0),
                'interface': interface.get('name') or 'unknown',
                'cpu': float(resource.get('cpu-load') or 0),
                'memory': round(used_memory / total_memory * 100, 2) if total_memory else 0.0,
                'free_memory_bytes': free_memory,
                'total_memory_bytes': total_memory,
                'uptime': str(resource.get('uptime') or ''),
            }
        except (socket.timeout, TimeoutError) as exc:
            logger.warning('[Telemetry Warning] Router %s unreachable (timed out)', target_host)
            return {'status': 'offline', 'error': str(exc)}
        except Exception as exc:
            exc_str = str(exc)
            logger.warning('[Telemetry Auth Error] Router %s: %s', target_host, exc_str)
            return {'status': 'offline', 'detail': 'Authentication or protocol error'}
        finally:
            if connection is not None and hasattr(connection, 'close'):
                try:
                    connection.close()
                except Exception:
                    pass

    logger.warning('[Telemetry Warning] Router %s: no RouterOS API library available', target_host)
    return {'status': 'offline', 'detail': 'Authentication or protocol error'}


def fetch_router_metrics(router) -> dict:
    """Fetch detailed live metrics for one authorized MikroTik router."""
    if librouteros_connect is None:
        raise RouterConnectionError(
            'The MikroTik API client is unavailable on the server.',
            'LIBROUTEROS_UNAVAILABLE',
        )

    host = str(router.nas_ip or '').strip()
    if not host:
        raise RouterConnectionError('This router has no management IP configured.', 'ROUTER_IP_MISSING')

    connection = None
    try:
        username, password = resolve_router_credentials(router)
        if not username or not password:
            raise RouterConnectionError('Router API credentials are not configured.', 'ROUTER_CREDENTIALS_MISSING')

        connection = librouteros_connect(
            host=host,
            username=username,
            password=password,
            port=int(router.api_port or 8728),
            timeout=5,
        )
        resources = list(connection.path('system', 'resource')('print'))
        if not resources:
            raise RouterConnectionError('Router returned no system resource data.', 'ROUTER_METRICS_UNAVAILABLE')
        resource = resources[0]

        memory_total = int(resource.get('total-memory') or 0)
        memory_free = int(resource.get('free-memory') or 0)
        memory_used = max(memory_total - memory_free, 0)
        interfaces = [
            {
                'name': str(item.get('name') or 'unknown'),
                'rx_bytes': int(item.get('rx-byte') or 0),
                'tx_bytes': int(item.get('tx-byte') or 0),
            }
            for item in connection.path('interface')('print')
        ]
        active_users = list(connection.path('ip', 'hotspot', 'active')('print'))

        return {
            'router_id': str(router.pk),
            'ip_address': host,
            'cpu_usage_percent': float(resource.get('cpu-load') or 0),
            'memory_used_bytes': memory_used,
            'memory_free_bytes': memory_free,
            'memory_total_bytes': memory_total,
            'memory_usage_percent': round(memory_used / memory_total * 100, 2) if memory_total else 0,
            'uptime': str(resource.get('uptime') or ''),
            'interfaces': interfaces,
            'active_hotspot_users': len(active_users),
            'captured_at': timezone.now().isoformat(),
        }
    except RouterConnectionError:
        raise
    except _LIBROUTEROS_EXCEPTIONS as exc:
        logger.error(
            'RouterOS API error for router %s (%s): %s: %s',
            router.pk,
            host,
            type(exc).__name__,
            exc,
        )
        raise RouterConnectionError(
            'The router rejected or could not process the metrics request.',
            'ROUTEROS_API_ERROR',
        ) from exc
    except (socket.timeout, TimeoutError) as exc:
        logger.error(
            'Router metrics connection failed for router %s (%s): %s: %s',
            router.pk,
            host,
            type(exc).__name__,
            exc,
        )
        raise RouterConnectionError(
            'The router did not respond before the metrics request timed out.',
            'ROUTER_METRICS_TIMEOUT',
        ) from exc
    except Exception as exc:
        logger.error(
            'Router metrics failed for router %s (%s): %s: %s',
            router.pk,
            host,
            type(exc).__name__,
            exc,
        )
        raise RouterConnectionError(
            'Unable to retrieve live metrics from the router.',
            'ROUTER_METRICS_FAILED',
        ) from exc
    finally:
        if connection is not None and hasattr(connection, 'close'):
            try:
                connection.close()
            except Exception:
                logger.warning('Failed to close RouterOS metrics connection for router %s', router.pk, exc_info=True)


def ping_router_with_credentials(router, *, api_ip=None, api_port=None, api_username=None, api_password=None) -> tuple[str, int, str, str]:
    host = str(api_ip or router.nas_ip or router.nasname or '').strip()
    port = int(api_port or router.api_port or 8728)
    api_user, api_pass = resolve_router_credentials(router, api_username, api_password)
    api_user = api_user or 'netpulse_admin'
    api_pass = api_pass or '123'
    host, port, api_user, api_pass, _, _ = validate_provisioning_inputs(
        host, port, api_user, api_pass, router.radius_server_ip or '192.168.56.1', router.shared_secret or router.secret or 'netpulse-secret',
    )
    print(f"[DEBUG] Connecting to MikroTik API at {host}:{port} as user '{api_user}'")
    if librouteros_connect is not None:
        connection = None
        try:
            connection = librouteros_connect(host=host, username=api_user, password=api_pass, port=port)
        finally:
            if connection is not None and hasattr(connection, 'close'):
                connection.close()
    else:
        check_mikrotik_connection(host, port, api_user, api_pass, timeout=8.0)
    return host, port, api_user, api_pass


def _is_duplicate_routeros_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in ('already exists', 'already have such entry', 'failure: already'))


def provision_with_librouteros(router, *, host: str, port: int, username: str, password: str, router_name: str, radius_ip: str, radius_secret: str, venue: str) -> dict:
    from librouteros.query import Key

    if librouteros_connect is None:
        raise RouterConnectionError('librouteros is required for structured RouterOS provisioning.', 'LIBROUTEROS_UNAVAILABLE')

    api = None
    try:
        api = librouteros_connect(host=host, username=username, password=password, port=port)
        api.path('/system/identity').set(name=str(router_name))
        try:
            api.path('/radius').add(service='hotspot', address=str(radius_ip).strip(), secret=str(radius_secret))
        except Exception as exc:
            if not _is_duplicate_routeros_error(exc):
                raise
            logger.warning('RADIUS server already exists on %s; continuing: %s', host, exc)

        incoming = list(api.path('/radius/incoming').select('.id'))
        if incoming:
            api.path('/radius/incoming').set(**{'.id': incoming[0]['.id'], 'accept': 'yes'})
        else:
            try:
                api.path('/radius/incoming').add(accept='yes')
            except Exception as exc:
                if not _is_duplicate_routeros_error(exc):
                    raise
                logger.warning('RADIUS incoming entry already exists on %s; continuing: %s', host, exc)

        profiles = list(api.path('/ip/hotspot/user/profile').select('.id').where(Key('name') == 'default'))
        if profiles:
            api.path('/ip/hotspot/user/profile').set(**{'.id': profiles[0]['.id'], 'shared-users': '1'})
        else:
            try:
                api.path('/ip/hotspot/user/profile').add(name='default', **{'shared-users': '1'})
            except Exception as exc:
                if not _is_duplicate_routeros_error(exc):
                    raise
                logger.warning('Default hotspot profile already exists on %s; continuing: %s', host, exc)

        hotspot_profiles = list(api.path('/ip/hotspot/profile').select('.id').where(Key('name') == 'default'))
        if hotspot_profiles:
            api.path('/ip/hotspot/profile').set(**{'.id': hotspot_profiles[0]['.id'], 'radius-accounting': 'yes', 'use-radius': 'yes'})

        for domain in ('*.m-pesa.co.ke', '*.safaricom.co.ke', '*.mpesa.co.ke'):
            try:
                api.path('/ip/hotspot/walled-garden').add(**{'dst-host': domain, 'comment': 'NetPulse bypass'})
            except Exception as exc:
                if not _is_duplicate_routeros_error(exc):
                    raise
                logger.warning('Walled-garden entry %s already exists on %s; continuing: %s', domain, host, exc)
    except RouterConnectionError:
        raise
    except Exception as exc:
        raise RouterConnectionError(f'RouterOS provisioning failed: {exc}', 'COMMAND_FAILED') from exc
    finally:
        if api is not None and hasattr(api, 'close'):
            api.close()

    router.nas_ip = host
    router.api_port = port
    router.api_username = username
    router.api_password = password
    router.radius_server_ip = radius_ip
    router.shared_secret = radius_secret
    router.secret = radius_secret
    router.shortname = venue
    router.nasname = router_name
    router.is_online = True
    router.status = 'online'
    router.last_ping = timezone.now()
    router.last_provisioned_at = timezone.now()
    router.save()
    return {'ok': True, 'success': True, 'message': 'Router provisioned and marked online!', 'status': 'online'}


class RouterConnectionError(Exception):
    def __init__(self, message: str, code: str = 'ROUTER_ERROR'):
        super().__init__(message)
        self.code = code


def encode_word(word: bytes) -> bytes:
    length = len(word)
    if length < 0x80:
        prefix = bytes([length])
    elif length < 0x4000:
        prefix = bytes([(length >> 8) | 0x80, length & 0xff])
    elif length < 0x200000:
        prefix = bytes([(length >> 16) | 0xc0, (length >> 8) & 0xff, length & 0xff])
    elif length < 0x10000000:
        prefix = bytes([(length >> 24) | 0xe0, (length >> 16) & 0xff, (length >> 8) & 0xff, length & 0xff])
    else:
        prefix = b'\xf0' + length.to_bytes(4, 'big')
    return prefix + word


def _read_exact(sock: socket.socket, length: int) -> bytes:
    chunks = []
    while length:
        chunk = sock.recv(length)
        if not chunk:
            raise RouterConnectionError('Router closed while sending a response', 'CONNECTION_CLOSED')
        chunks.append(chunk)
        length -= len(chunk)
    return b''.join(chunks)


def read_word(sock: socket.socket) -> bytes:
    first = sock.recv(1)
    if not first:
        raise RouterConnectionError('Router closed the connection')
    value = first[0]
    if value < 0x80:
        length = value
    elif value < 0xc0:
        length = ((value & 0x3f) << 8) | int.from_bytes(_read_exact(sock, 1), 'big')
    elif value < 0xe0:
        length = ((value & 0x1f) << 16) | int.from_bytes(_read_exact(sock, 2), 'big')
    elif value < 0xf0:
        length = ((value & 0x0f) << 24) | int.from_bytes(_read_exact(sock, 3), 'big')
    else:
        length = int.from_bytes(_read_exact(sock, 4), 'big')
    return _read_exact(sock, length)


def read_sentence(sock: socket.socket) -> list[bytes]:
    words = []
    while True:
        word = read_word(sock)
        if word == b'':
            return words
        words.append(word)


def send_sentence(sock: socket.socket, words: list[bytes]) -> None:
    sock.sendall(b''.join(encode_word(word) for word in words) + encode_word(b''))


def parse_words(words: list[bytes]) -> dict[str, str]:
    result = {}
    for word in words:
        if word.startswith(b'=') and b'=' in word[1:]:
            key, value = word[1:].split(b'=', 1)
            result[key.decode(errors='replace')] = value.decode(errors='replace')
    return result


def _authenticate(sock: socket.socket, username: str, password: str, mode: str) -> None:
    send_sentence(sock, [b'/login'])
    login_response = read_sentence(sock)
    login_words = parse_words(login_response)
    if any(word.startswith(b'!trap') for word in login_response):
        raise RouterConnectionError('Router rejected the login request', 'LOGIN_REJECTED')

    if mode == 'challenge' and 'ret' in login_words:
        try:
            challenge = bytes.fromhex(login_words['ret'])
        except ValueError as exc:
            raise RouterConnectionError('Router returned an invalid MD5 challenge', 'PROTOCOL_ERROR') from exc
        digest = hashlib.md5(b'\x00' + password.encode() + challenge).hexdigest().encode()
        send_sentence(sock, [b'/login', f'=name={username}'.encode(), b'=response=00' + digest])
    else:
        send_sentence(sock, [b'/login', f'=name={username}'.encode(), f'=password={password}'.encode()])

    auth_response = read_sentence(sock)
    if any(word.startswith(b'!trap') for word in auth_response):
        details = parse_words(auth_response)
        category = details.get('category', '')
        code = 'AUTH_CODE_6' if category == '6' else 'AUTH_FAILED'
        raise RouterConnectionError(f"Authentication failed: {details.get('message', 'invalid credentials')} (category {category or 'unknown'})", code)
    if b'!done' not in auth_response:
        raise RouterConnectionError('Authentication failed: no !done response', 'AUTH_FAILED')


def resolve_radius_address(radius_ip: str | None = None, radius_server_ip: str | None = None, address: str | None = None) -> str:
    resolved = next(
        (str(value).strip() for value in (radius_ip, radius_server_ip, address) if isinstance(value, str) and value.strip()),
        '',
    )
    if not resolved:
        raise RouterConnectionError('RADIUS address is required for provisioning.', 'INVALID_RADIUS_ADDRESS')
    try:
        ipaddress.ip_address(resolved)
    except ValueError as exc:
        raise RouterConnectionError('RADIUS address must be a valid IP address.', 'INVALID_RADIUS_ADDRESS') from exc
    return resolved


def build_mikrotik_provisioning_commands(router_name: str, radius_server_ip: str, shared_secret: str, venue: str | None = None, *, radius_ip: str | None = None, address: str | None = None) -> list[str]:
    radius_address = resolve_radius_address(radius_ip, radius_server_ip, address)
    location = venue or router_name
    return [
        f'/system/identity/set =name={router_name}',
        f'/radius/add =service=hotspot =address={radius_address} =secret={shared_secret}',
        '/radius/incoming/set =accept=yes',
        '/ip/hotspot/profile/set [ find default=yes ] =radius-accounting=yes =use-radius=yes',
        '/ip/hotspot/user/profile/set [ find default=yes ] =shared-users=1',
        '/ip/hotspot/walled-garden/add =dst-host="*.m-pesa.co.ke" =comment="M-Pesa bypass"',
        '/ip/hotspot/walled-garden/add =dst-host="*.safaricom.co.ke" =comment="Safaricom bypass"',
        '/ip/hotspot/walled-garden/add =dst-host="*.mpesa.co.ke" =comment="M-Pesa bypass"',
        f'# Location: {location}',
    ]


def _command_as_words(command: str) -> list[bytes]:
    if not command or command.startswith('#'):
        return []
    tokens = command.split()
    if not tokens:
        return []
    return [tokens[0].encode()] + [part.encode() for part in tokens[1:]]


def _read_print_records(sock: socket.socket, path: str) -> list[dict[str, str]]:
    send_sentence(sock, [path.encode(), b'=.proplist=.id,name,default'])
    records = []
    while True:
        sentence = read_sentence(sock)
        if any(word.startswith(b'!done') for word in sentence):
            return records
        if any(word.startswith(b'!trap') for word in sentence):
            details = parse_words(sentence)
            raise RouterConnectionError(details.get('message', 'RouterOS print command failed'), 'COMMAND_FAILED')
        if any(word.startswith(b'!re') for word in sentence):
            records.append(parse_words(sentence))


def _command_words_with_id(sock: socket.socket, command: str) -> tuple[list[bytes], list[bytes] | None]:
    tokens = command.split()
    if not tokens:
        return [], None
    path = tokens[0]
    if not path.endswith('/set'):
        return _command_as_words(command), None

    selector_start = tokens.index('[') if '[' in tokens else None
    selector_end = tokens.index(']') if ']' in tokens else None
    if selector_start is not None and selector_end is not None:
        selector_tokens = tokens[selector_start + 1:selector_end]
        params = tokens[selector_end + 1:]
        selector = dict(part.split('=', 1) for part in selector_tokens if '=' in part)
    else:
        params = tokens[1:]
        selector = {}

    print_path = path[:-4] + '/print'
    records = _read_print_records(sock, print_path)
    record = None
    for candidate in records:
        if all(candidate.get(key, '').lower() == value.lower() for key, value in selector.items()):
            record = candidate
            break
    if record is None and not selector:
        record = records[0] if records else None

    encoded_params = [part.encode() if part.startswith('=') else f'={part}'.encode() for part in params]
    if record and record.get('.id'):
        return [path.encode(), f"=.id={record['.id']}".encode(), *encoded_params], None

    add_path = path[:-4] + '/add'
    return [add_path.encode(), *encoded_params], [path.encode(), *encoded_params]


def _is_nonfatal_routeros_trap(message: str) -> bool:
    normalized = message.lower()
    return any(
        marker in normalized
        for marker in (
            'already exists',
            'already have such entry',
            'no such item',
            'nothing to do',
            'cannot modify',
            'failure: already',
        )
    )


def execute_mikrotik_api_commands(host: str, port: int, username: str, password: str, commands: list[str], timeout: float = 10.0) -> list[dict]:
    results: list[dict] = []
    for mode in ('challenge', 'plaintext'):
        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                sock.settimeout(timeout)
                _authenticate(sock, username, password, mode)
                for command in commands:
                    if command.startswith('#'):
                        continue
                    words, _ = _command_words_with_id(sock, command)
                    if not words:
                        continue
                    try:
                        send_sentence(sock, words)
                        response = read_sentence(sock)
                        if any(word.startswith(b'!trap') for word in response):
                            details = parse_words(response)
                            message = details.get('message', 'command failed')
                            if _is_nonfatal_routeros_trap(message):
                                logger.warning('RouterOS ignored non-fatal command trap for %s: %s', command, message)
                                results.append({'command': command, 'ok': True, 'skipped': True, 'message': message})
                                continue
                            raise RouterConnectionError(f'API command rejected: {message}', 'COMMAND_FAILED')
                        results.append({'command': command, 'ok': True})
                    except RouterConnectionError as exc:
                        if exc.code == 'COMMAND_FAILED' and _is_nonfatal_routeros_trap(str(exc)):
                            logger.warning('RouterOS ignored non-fatal command failure for %s: %s', command, exc)
                            results.append({'command': command, 'ok': True, 'skipped': True, 'message': str(exc)})
                            continue
                        raise
                return results
        except RouterConnectionError as exc:
            if exc.code not in {'AUTH_FAILED', 'AUTH_CODE_6'}:
                raise
            logger.info('Router %s auth mode %s failed (%s); trying fallback', host, mode, exc)
        except socket.timeout as exc:
            raise RouterConnectionError(f'Router API handshake timed out after {timeout:g}s', 'HANDSHAKE_TIMEOUT') from exc
        except OSError as exc:
            raise RouterConnectionError(f'Router socket error: {exc}', 'SOCKET_ERROR') from exc

    raise RouterConnectionError('Authentication failed', 'AUTH_FAILED')


def check_mikrotik_connection(host: str, port: int, username: str, password: str, timeout: float = 5.0) -> dict:
    started = datetime.now().timestamp()
    auth_error = None
    for mode in ('challenge', 'plaintext'):
        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                sock.settimeout(timeout)
                _authenticate(sock, username, password, mode)
                send_sentence(sock, [b'/system/identity/print'])
                command_response = read_sentence(sock)
                if any(word.startswith(b'!trap') for word in command_response):
                    details = parse_words(command_response)
                    raise RouterConnectionError(f"API command rejected: {details.get('message', 'read permission denied')}", 'READ_PERMISSION_DENIED')
                identity = parse_words(command_response)
                return {'host': host, 'port': port, 'identity': identity.get('name', 'unknown'), 'auth_mode': mode, 'elapsed_ms': round((datetime.now().timestamp() - started) * 1000)}
        except RouterConnectionError as exc:
            auth_error = exc
            if exc.code != 'AUTH_FAILED' and exc.code != 'AUTH_CODE_6':
                raise
            logger.info('Router %s authentication mode %s failed (%s); trying fallback', host, mode, exc)
        except socket.timeout as exc:
            raise RouterConnectionError(f'Router API handshake timed out after {timeout:g}s', 'HANDSHAKE_TIMEOUT') from exc
        except OSError as exc:
            raise RouterConnectionError(f'Router socket error: {exc}', 'SOCKET_ERROR') from exc

    raise auth_error or RouterConnectionError('Authentication failed', 'AUTH_FAILED')


def sync_radius_nas_record(nas_ip: str | None = None, shortname: str = '', secret: str = '', router_type: str = 'mikrotik', radius_server_ip: str | None = None, *, nasname: str | None = None) -> dict:
    from apps.radius.models import Nas

    nas_ip = (nas_ip or nasname or '').strip()
    if not nas_ip:
        raise RouterConnectionError('A RADIUS NAS IP is required.', 'INVALID_ADDRESS')
    record, created = Nas.objects.using('radius_db').get_or_create(
        nasname=nas_ip,
        defaults={
            'shortname': shortname or nas_ip,
            'type': router_type,
            'secret': secret,
            'server': radius_server_ip or '127.0.0.1',
            'description': f'Auto-provisioned {router_type} NAS',
        },
    )
    if not created:
        record.shortname = shortname or nas_ip
        record.type = router_type
        record.secret = secret
        record.server = radius_server_ip or '127.0.0.1'
        record.description = f'Auto-provisioned {router_type} NAS'
        record.save(using='radius_db', update_fields=['shortname', 'type', 'secret', 'server', 'description'])
    return {'created': created, 'updated': not created, 'nasname': record.nasname, 'shortname': record.shortname, 'secret': record.secret, 'type': record.type}


def validate_provisioning_inputs(api_ip: str, api_port: int | str, api_username: str, api_password: str, radius_server_ip: str, shared_secret: str) -> tuple[str, int, str, str, str, str]:
    api_ip = str(api_ip or '').strip()
    radius_server_ip = str(radius_server_ip or '').strip()
    api_username = str(api_username or '').strip()
    api_password = str(api_password or '').strip()
    shared_secret = str(shared_secret or '').strip()
    try:
        ipaddress.ip_address(api_ip)
        ipaddress.ip_address(radius_server_ip)
    except ValueError as exc:
        raise RouterConnectionError('Router and RADIUS addresses must be valid IP addresses.', 'INVALID_ADDRESS') from exc
    try:
        api_port = int(api_port)
    except (TypeError, ValueError) as exc:
        raise RouterConnectionError('Router API port must be a number.', 'INVALID_PORT') from exc
    if not 1 <= api_port <= 65535:
        raise RouterConnectionError('Router API port must be between 1 and 65535.', 'INVALID_PORT')
    if not api_username or not api_password or not shared_secret:
        raise RouterConnectionError('Router username, API password, and RADIUS secret are required.', 'INVALID_CREDENTIALS')
    return api_ip, api_port, api_username, api_password, radius_server_ip, shared_secret


def provision_mikrotik_router(
    router_id,
    *,
    api_ip: str | None = None,
    api_port: int | str | None = None,
    api_username: str | None = None,
    api_password: str | None = None,
    radius_server_ip: str | None = None,
    radius_ip: str | None = None,
    address: str | None = None,
    shared_secret: str | None = None,
    router_name: str | None = None,
    venue: str | None = None,
) -> dict:
    router = NAS.objects.get(pk=router_id)
    api_host = api_ip or router.nas_ip or router.nasname
    port = api_port or router.api_port or 8728
    username, password = resolve_router_credentials(router, api_username, api_password)
    username = username or _credential_value(os.environ.get('MIKROTIK_API_USERNAME', 'admin'))
    password = password or _credential_value(os.environ.get('MIKROTIK_API_PASSWORD', ''))
    radius_address = resolve_radius_address(
        radius_ip,
        radius_server_ip,
        address,
    ) if (radius_ip or radius_server_ip or address) else (router.radius_server_ip or os.environ.get('RADIUS_SERVER_IP', '10.10.0.5')).strip()
    secret = shared_secret or router.shared_secret or router.secret or os.environ.get('RADIUS_SHARED_SECRET', 'netpulse-secret')
    router_name = (router_name or router.nasname or 'MT-NEW').strip()
    venue = (venue or router.shortname or 'Main Venue').strip()
    api_host, port, username, password, radius_address, secret = validate_provisioning_inputs(api_host, port, username, password, radius_address, secret)

    commands = build_mikrotik_provisioning_commands(router_name=router_name, radius_server_ip=radius_address, shared_secret=secret, venue=venue)

    try:
        print(f"[DEBUG] Connecting to MikroTik API at {api_host}:{port} as user '{username}'")
        if librouteros_connect is not None:
            return provision_with_librouteros(
                router,
                host=api_host,
                port=port,
                username=username,
                password=password,
                router_name=router_name,
                radius_ip=radius_address,
                radius_secret=secret,
                venue=venue,
            )
        check_mikrotik_connection(api_host, port, username, password, timeout=8.0)
    except Exception as exc:
        router.is_online = False
        router.status = 'offline'
        router.save(update_fields=['is_online', 'status', 'updated_at'])
        raise RouterConnectionError(f"Unable to connect to RouterOS API at {api_host}:{port}: {exc}", getattr(exc, 'code', 'API_UNREACHABLE')) from exc

    try:
        executed = execute_mikrotik_api_commands(api_host, port, username, password, commands, timeout=10.0)
        sync_result = sync_radius_nas_record(api_host, venue, secret, router_type='mikrotik', radius_server_ip=radius_address)
        router.nas_ip = api_host
        router.api_port = port
        router.api_username = username
        router.api_password = password
        router.radius_server_ip = radius_address
        router.shared_secret = secret
        router.secret = secret
        router.shortname = venue
        router.nasname = router_name
        router.last_provisioned_at = timezone.now()
        router.is_online = True
        router.status = 'online'
        router.last_ping = timezone.now()
        router.save(update_fields=['nas_ip', 'api_port', 'api_username', 'api_password', 'radius_server_ip', 'shared_secret', 'secret', 'shortname', 'nasname', 'last_provisioned_at', 'is_online', 'status', 'last_ping', 'updated_at'])
    except Exception as exc:
        router.is_online = False
        router.status = 'offline'
        router.save(update_fields=['is_online', 'status', 'updated_at'])
        raise RouterConnectionError(f"Router provisioning failed after API connection: {exc}", getattr(exc, 'code', 'PROVISION_FAILED')) from exc

    return {
        'ok': True,
        'success': True,
        'code': 'OK',
        'router': {'id': str(router.id), 'nasname': router.nasname, 'ip': api_host, 'port': port},
        'commands': executed,
        'radius': sync_result,
        'message': 'Router updated, provisioned, and online!',
        'status': 'online',
    }


def update_router_health(nas: NAS, timeout: float = 5.0) -> dict:
    try:
        username = (nas.api_username or os.environ.get('MIKROTIK_API_USERNAME', '')).strip()
        password = (nas.api_password or os.environ.get('MIKROTIK_API_PASSWORD', '')).strip()
        if not username or not password:
            raise RouterConnectionError('Router API credentials are not configured')
        host = nas.nas_ip or nas.nasname
        port = nas.api_port or 8728
        check_mikrotik_connection(host, port, username, password, timeout=timeout)
    except Exception as exc:
        logger.warning('Router health check failed for NAS %s (%s): %s', nas.pk, nas.nasname, exc, exc_info=True)
        NAS.objects.filter(pk=nas.pk).update(is_online=False, status='offline', updated_at=timezone.now())
        return {'is_online': False, 'code': getattr(exc, 'code', 'ROUTER_ERROR'), 'message': str(exc)}
    NAS.objects.filter(pk=nas.pk).update(is_online=True, status='online', last_ping=timezone.now(), updated_at=timezone.now())
    return {'is_online': True, 'code': 'OK', 'message': 'Router API connection healthy'}
