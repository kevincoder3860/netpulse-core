#!/usr/bin/env python3
"""Diagnose a MikroTik API connection without printing credentials."""
import argparse
import hashlib
import socket
import sys
import time


GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'


def ok(message):
    print(f'{GREEN}[OK]{RESET} {message}')


def fail(message):
    print(f'{RED}[FAIL]{RESET} {message}')


def info(message):
    print(f'{YELLOW}[INFO]{RESET} {message}')


def encode_word(word):
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


def read_exact(sock, count):
    data = bytearray()
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError('Router closed the connection')
        data.extend(chunk)
    return bytes(data)


def read_word(sock):
    first = read_exact(sock, 1)[0]
    if first < 0x80:
        length = first
    elif first < 0xc0:
        length = ((first & 0x3f) << 8) | read_exact(sock, 1)[0]
    elif first < 0xe0:
        length = ((first & 0x1f) << 16) | int.from_bytes(read_exact(sock, 2), 'big')
    elif first < 0xf0:
        length = ((first & 0x0f) << 24) | int.from_bytes(read_exact(sock, 3), 'big')
    else:
        length = int.from_bytes(read_exact(sock, 4), 'big')
    return read_exact(sock, length)


def read_sentence(sock):
    words = []
    while True:
        word = read_word(sock)
        if word == b'':
            return words
        words.append(word)


def send_sentence(sock, words):
    sock.sendall(b''.join(encode_word(word) for word in words) + encode_word(b''))


def attributes(words):
    parsed = {}
    for word in words:
        if word.startswith(b'=') and b'=' in word[1:]:
            key, value = word[1:].split(b'=', 1)
            parsed[key.decode(errors='replace')] = value.decode(errors='replace')
    return parsed


def authenticate(sock, username, password, challenge_mode):
    send_sentence(sock, [b'/login'])
    login_words = read_sentence(sock)
    login_attrs = attributes(login_words)
    if challenge_mode and 'ret' in login_attrs:
        response = hashlib.md5(b'\x00' + password.encode() + bytes.fromhex(login_attrs['ret'])).hexdigest()
        send_sentence(sock, [b'/login', f'=name={username}'.encode(), f'=response=00{response}'.encode()])
    else:
        send_sentence(sock, [b'/login', f'=name={username}'.encode(), f'=password={password}'.encode()])
    return read_sentence(sock)


def check_host(host, port, username, password, timeout):
    print(f'\nTesting {host}:{port}')
    # Step 1: raw TCP reachability.
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(timeout)
    except socket.timeout:
        fail(f'Socket connection refused on {host}:{port}. Check VM network mode (Bridged vs Host-Only) or Docker container routing.')
        print(f'  Reason: TCP timeout after {timeout:g}s')
        return False
    except ConnectionRefusedError:
        fail(f'Socket connection refused on {host}:{port}. Check VM network mode (Bridged vs Host-Only) or Docker container routing.')
        return False
    except OSError as exc:
        fail(f'Socket error connecting to {host}:{port}: {exc}')
        return False
    else:
        ok('STEP 1 TCP socket is reachable')
        sock.close()

    # Step 2: try the v6 challenge flow, then reconnect for v7 plaintext.
    for challenge_mode in (True, False):
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.settimeout(timeout)
            with sock:
                auth_words = authenticate(sock, username, password, challenge_mode)
                if any(word.startswith(b'!trap') for word in auth_words):
                    if challenge_mode:
                        info('Challenge-response rejected; retrying RouterOS v7 plaintext login')
                        continue
                    details = attributes(auth_words).get('message', 'invalid credentials')
                    category = attributes(auth_words).get('category', 'unknown')
                    fail(f'STEP 2 MikroTik authentication failed: {details} (category {category})')
                    return False
                if b'!done' not in auth_words:
                    fail('STEP 2 MikroTik authentication failed: no !done response')
                    return False

                auth_mode = 'challenge-response' if challenge_mode else 'plaintext'
                ok(f'STEP 2 MikroTik API authentication succeeded ({auth_mode})')

                # Step 3: run the read-permission command on the authenticated socket.
                send_sentence(sock, [b'/system/identity/print'])
                words = read_sentence(sock)
                if any(word.startswith(b'!trap') for word in words):
                    fail(f"STEP 3 API command rejected: {attributes(words).get('message', 'read permission denied')}")
                    return False
                identity = attributes(words).get('name', 'unknown')
                ok(f'STEP 3 read command succeeded; router identity: {identity}')
                return True
        except socket.timeout:
            fail(f'STEP 2 API handshake or STEP 3 command timed out after {timeout:g}s')
            return False
        except (OSError, ValueError, ConnectionError) as exc:
            fail(f'STEP 2/3 API diagnostic failed: {exc}')
            return False


def main():
    parser = argparse.ArgumentParser(description='Test MikroTik RouterOS API connectivity')
    parser.add_argument('hosts', nargs='*', default=['192.168.56.20'], help='Router IP(s) to test')
    parser.add_argument('--port', type=int, default=8728)
    parser.add_argument('--username', default='billing_api')
    parser.add_argument('--password', default='123')
    parser.add_argument('--timeout', type=float, default=5.0)
    args = parser.parse_args()
    started = time.monotonic()
    passed = any(check_host(host, args.port, args.username, args.password, args.timeout) for host in args.hosts)
    info(f'Diagnostic completed in {time.monotonic() - started:.2f}s')
    if not passed:
        fail('No router passed all connection checks')
        return 1
    ok('Router API connection is healthy')
    return 0


if __name__ == '__main__':
    sys.exit(main())
