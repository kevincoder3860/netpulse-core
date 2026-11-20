"""
Telemetry views for MikroTik router statistics.

Supports RouterOS v6 (MD5 challenge) and v7+ (plaintext login) via the
routeros_api library. Socket timeout is capped at 5 s so that unreachable
endpoints fail fast and never block the Django WSGI worker or the React
polling loop.

Error hierarchy handled explicitly:
  RouterOsApiCommunicationError  – auth / protocol handshake failure
  RouterOsApiConnectionError     – TCP connect failure / socket refused
  socket.timeout / TimeoutError  – connection establishment timed out
  Exception (catch-all)          – anything else (e.g. library bugs)

All error paths:
  • log a structured WARNING
  • call pool.disconnect() in finally to avoid socket leaks
  • return HTTP 200 JSON so the React polling loop stays clean
"""

import logging
import socket

from django.db import OperationalError
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import routeros_api library and its exception classes
# ---------------------------------------------------------------------------
try:
    import routeros_api
    from routeros_api import RouterOsApiPool
    from routeros_api.exceptions import (
        RouterOsApiCommunicationError,
        RouterOsApiConnectionError,
    )
    _ROUTEROS_API_AVAILABLE = True
except ImportError:
    routeros_api = None  # type: ignore[assignment]
    RouterOsApiPool = None  # type: ignore[assignment, misc]
    RouterOsApiCommunicationError = Exception  # type: ignore[assignment, misc]
    RouterOsApiConnectionError = Exception  # type: ignore[assignment, misc]
    _ROUTEROS_API_AVAILABLE = False


# ---------------------------------------------------------------------------
# Internal helper: resolve target credentials from a NAS model or plain args
# ---------------------------------------------------------------------------

def _resolve_target(router, host, username, password, port):
    """Return (target_host, target_user, target_pass, target_port)."""
    if isinstance(router, str):
        return router.strip(), username or 'admin', password or '', int(port or 8728)

    if router is not None:
        raw_host = str(
            getattr(router, 'nas_ip', None) or getattr(router, 'nasname', None) or ''
        ).strip()
        try:
            from apps.routers.services import resolve_router_credentials
            resolved_user, resolved_pass = resolve_router_credentials(router)
        except Exception:
            resolved_user = getattr(router, 'api_username', '') or ''
            resolved_pass = getattr(router, 'api_password', '') or ''
        return (
            host or raw_host or '192.168.56.20',
            username or resolved_user or 'admin',
            password or resolved_pass or '',
            int(port or getattr(router, 'api_port', None) or 8728),
        )

    return (
        (host or '192.168.56.20').strip(),
        username or 'admin',
        password or '',
        int(port or 8728),
    )


# ---------------------------------------------------------------------------
# Public helper: fetch telemetry statistics from a MikroTik router
# ---------------------------------------------------------------------------

def fetch_router_telemetry(
    router=None,
    *,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int | None = None,
) -> dict:
    """
    Connect to a MikroTik router via RouterOsApiPool and return live stats.

    Parameters
    ----------
    router  : NAS model instance, IP string, or None
    host    : override the IP/hostname
    username: override the API username
    password: override the API password
    port    : override the API port (default 8728)

    Returns a dict that always contains ``"status": "online"|"offline"``.
    On failure the dict also contains one of:
      ``"error"``  – low-level error string  (timeout / connection refused)
      ``"detail"`` – human-readable problem   (auth / protocol failure)
    """
    target_host, target_user, target_pass, target_port = _resolve_target(
        router, host, username, password, port
    )

    if not _ROUTEROS_API_AVAILABLE:
        logger.warning('[Telemetry Warning] Router %s: routeros_api library is not installed', target_host)
        return {'status': 'offline', 'detail': 'routeros_api library is not available'}

    pool = None
    try:
        # ------------------------------------------------------------------
        # Build the connection pool.
        # plaintext_login=True  is required for RouterOS v7+ API auth.
        # socket_timeout=5.0    bounds slow API responses without a short timeout.
        # port=8728             is the standard unencrypted MikroTik API port.
        # ------------------------------------------------------------------
        pool = RouterOsApiPool(
            target_host,
            username=target_user,
            password=target_pass,
            port=target_port,
            plaintext_login=True,
            socket_timeout=5.0,
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
                    key=lambda i: int(i.get('rx-byte', 0) or 0) + int(i.get('tx-byte', 0) or 0),
                    default={},
                )
                rx_bytes = int(top.get('rx-byte', 0) or 0)
                tx_bytes = int(top.get('tx-byte', 0) or 0)
                primary_interface = top.get('name', 'unknown')
        except (socket.timeout, TimeoutError):
            raise
        except Exception as exc:
            logger.warning(
                '[Telemetry Query Error] Router %s interface statistics failed: %s',
                target_host,
                exc,
            )

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
        except (socket.timeout, TimeoutError):
            raise
        except Exception as exc:
            logger.warning(
                '[Telemetry Query Error] Router %s system resource query failed: %s',
                target_host,
                exc,
            )

        return {
            'status': 'online',
            'rx_bytes': rx_bytes,
            'tx_bytes': tx_bytes,
            'interface': primary_interface,
            'cpu': cpu,
            'memory': memory,
        }

    # ------------------------------------------------------------------
    # Auth / protocol failure (wrong password, RouterOS v6/v7 mismatch …)
    # ------------------------------------------------------------------
    except RouterOsApiCommunicationError as exc:
        logger.warning('[Telemetry Auth Error] Router %s: %s', target_host, exc)
        return {'status': 'offline', 'detail': 'Authentication or protocol error'}

    # ------------------------------------------------------------------
    # TCP connect failure (host unreachable, port closed, connection refused …)
    # ------------------------------------------------------------------
    except RouterOsApiConnectionError as exc:
        logger.warning('[Telemetry Connection Error] Router %s: %s', target_host, exc)
        return {'status': 'offline', 'detail': 'Authentication or protocol error'}

    # ------------------------------------------------------------------
    # Network timeout (router unreachable, firewall dropping packets …)
    # ------------------------------------------------------------------
    except (socket.timeout, TimeoutError) as exc:
        logger.warning('[Telemetry Timeout] Router %s unreachable (timed out)', target_host)
        return {'status': 'offline', 'error': str(exc)}

    # ------------------------------------------------------------------
    # Catch-all: unexpected library errors, OS errors, etc.
    # ------------------------------------------------------------------
    except Exception as exc:
        exc_str = str(exc)
        if 'timed out' in exc_str.lower() or 'timeout' in exc_str.lower():
            logger.warning('[Telemetry Timeout] Router %s unreachable (timed out)', target_host)
            return {'status': 'offline', 'error': exc_str}
        logger.warning('[Telemetry Auth Error] Router %s: %s', target_host, exc_str)
        return {'status': 'offline', 'detail': 'Authentication or protocol error'}

    # ------------------------------------------------------------------
    # Always disconnect the pool so the socket is released.
    # ------------------------------------------------------------------
    finally:
        if pool is not None:
            try:
                pool.disconnect()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# DRF API view: GET /api/v1/telemetry/ or /api/v1/telemetry/<pk>/
# ---------------------------------------------------------------------------

class TelemetryView(APIView):
    """
    Return live MikroTik telemetry statistics for a router without blocking
    HTTP responses on timeouts.  Always returns HTTP 200 so the React
    polling loop never enters an error state on transient failures.
    """
    permission_classes = [AllowAny]

    def get(self, request, pk=None, *args, **kwargs):
        router_target = None

        if pk is not None:
            try:
                from apps.routers.models import NAS
                router_target = NAS.objects.filter(pk=pk).first()
            except OperationalError as exc:
                logger.warning('Telemetry router lookup failed for %s: %s', pk, exc)
                is_busy = 'locked' in str(exc).lower() or 'busy' in str(exc).lower()
                code = 'DATABASE_BUSY' if is_busy else 'DATABASE_UNAVAILABLE'
                detail = (
                    'Telemetry data is temporarily unavailable because the database is busy.'
                    if is_busy
                    else 'Telemetry data is temporarily unavailable.'
                )
                return Response(
                    {'status': 'offline', 'detail': detail, 'code': code},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        if router_target is None:
            router_target = (
                request.query_params.get('host')
                or request.query_params.get('ip')
                or '192.168.56.20'
            )

        data = fetch_router_telemetry(router_target)
        return Response(data, status=status.HTTP_200_OK)


def telemetry_view(request, pk=None):
    """Function-based view wrapper for TelemetryView."""
    view = TelemetryView.as_view()
    return view(request, pk=pk)
