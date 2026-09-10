import hashlib
import ipaddress
import logging
import os
import socket
from datetime import datetime

from django.utils import timezone

from .models import NAS

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency for direct MikroTik API use
    from routeros_api import RouterOsApiPool  # type: ignore
except Exception:  # pragma: no cover - optional dependency not installed in this environment
    RouterOsApiPool = None

try:  # pragma: no cover - optional dependency
    from librouteros import connect as librouteros_connect  # type: ignore
except Exception:  # pragma: no cover - dependency is not installed locally
    librouteros_connect = None


def _credential_value(value: object) -> str:
    """Return a usable credential, decrypting Fernet values when configured."""
    raw = str(value or '').strip()
    if not raw:
        return ''
    encryption_key = os.environ.get('CREDENTIAL_ENCRYPTION_KEY', '').strip()
    if encryption_key:
        try:
            from cryptography.fernet import Fernet
            return Fernet(encryption_key.encode()).decrypt(raw.encode()).decode().strip()
        except Exception:
            logger.warning('Stored router credential could not be decrypted; using it as plaintext')
    return raw


def resolve_router_credentials(router, api_username: object = None, api_password: object = None) -> tuple[str, str]:
    api_user = _credential_value(api_username if api_username is not None else router.api_username)
    api_pass = _credential_value(api_password if api_password is not None else router.api_password)
    return api_user, api_pass


def fetch_router_telemetry(router) -> dict:
    if librouteros_connect is None:
        raise RouterConnectionError('librouteros is required for router telemetry.', 'LIBROUTEROS_UNAVAILABLE')

    username, password = resolve_router_credentials(router)
    connection = None
    try:
        connection = librouteros_connect(
            host=str(router.nas_ip or router.nasname).strip(),
            username=username or 'netpulse_admin',
            password=password or '123',
            port=int(router.api_port or 8728),
        )
        interfaces = list(connection.path('/interface').select('name', 'rx-byte', 'tx-byte'))
        if not interfaces:
            return {'rx_bytes': 0, 'tx_bytes': 0, 'interface': 'unknown'}
        interface = max(
            interfaces,
            key=lambda item: int(item.get('rx-byte', 0)) + int(item.get('tx-byte', 0)),
        )
        return {
            'rx_bytes': int(interface.get('rx-byte', 0)),
            'tx_bytes': int(interface.get('tx-byte', 0)),
            'interface': interface.get('name', 'unknown'),
        }
    except (ValueError, TypeError) as exc:
        raise RouterConnectionError(f'Invalid RouterOS interface statistics: {exc}', 'TELEMETRY_INVALID') from exc
    except Exception as exc:
        raise RouterConnectionError(f'RouterOS telemetry request failed: {exc}', 'TELEMETRY_FAILED') from exc
    finally:
        if connection is not None and hasattr(connection, 'close'):
            connection.close()


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

        profiles = list(api.path('/ip/hotspot/user/profile').select('.id').where(name='default'))
        if profiles:
            api.path('/ip/hotspot/user/profile').set(**{'.id': profiles[0]['.id'], 'shared-users': '1'})
        else:
            try:
                api.path('/ip/hotspot/user/profile').add(name='default', **{'shared-users': '1'})
            except Exception as exc:
                if not _is_duplicate_routeros_error(exc):
                    raise
                logger.warning('Default hotspot profile already exists on %s; continuing: %s', host, exc)

        hotspot_profiles = list(api.path('/ip/hotspot/profile').select('.id').where(name='default'))
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
        ipaddress.ip_address(radius_server_ip)
    except ValueError as exc:
        raise RouterConnectionError('RADIUS server address must be a valid IP address.', 'INVALID_ADDRESS') from exc
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
