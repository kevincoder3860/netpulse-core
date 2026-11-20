# NetPulse backend

## Running telemetry WebSockets locally

The telemetry endpoint (`/ws/telemetry/<tenant_id>/`) is served by the ASGI
application in `core.asgi`. Django's `manage.py runserver` is WSGI-only in this
project and does not serve WebSocket connections. Use Daphne for local
development instead:

```powershell
cd backend
.\venv\Scripts\python.exe -m daphne -b 127.0.0.1 -p 8000 core.asgi:application
```

If using another Python environment, activate it and run:

```text
daphne -b 127.0.0.1 -p 8000 core.asgi:application
```

The frontend can then use its regular API base URL (for example,
`http://127.0.0.1:8000/api/v1`); the telemetry hook derives the matching
`ws://127.0.0.1:8000` WebSocket origin. Django's HTTP API remains available
through Daphne as well.

## Vendor Paystack M-Pesa configuration

Each vendor configures a Paystack secret key and receipt/settlement email in
**Subscriptions & Payments**. The key is encrypted in the database, accepted
as write-only through the tenant API, and never included in API responses. Set
a stable `PAYSTACK_CREDENTIALS_ENCRYPTION_KEY` in the backend environment; if
it is omitted, the encryption key is derived from `DJANGO_SECRET_KEY`. Back up
and keep this key stable, because changing it makes previously stored
credentials unreadable.

An optional `PAYSTACK_SECRET_KEY` environment variable is used only when a
tenant has no saved Paystack key. A workspace-specific key always takes
precedence.

Run Django migrations after deploying the tenant billing fields. The captive
portal starts a Paystack M-Pesa charge at
`/api/v1/billing/paystack/stk-push/`, using the vendor's configured email and
the selected plan's server-side price. Configure Paystack to send
`charge.success` events to `/api/v1/billing/paystack/webhook/`. The webhook
signature is verified with the matching vendor key, and pending payments are
also verified with Paystack when their status is polled before hotspot access
is provisioned. Use test keys for development; live keys can initiate real
charges.

Router API credentials use `CREDENTIAL_ENCRYPTION_KEY`. Local debug mode has
a development-only test-key fallback; production deployments must set a
stable key and `DEBUG=false` (startup fails if the key is missing).

The older Daraja configuration and callback endpoints are retained for
compatibility with existing integrations. The current captive portal and
vendor settings use Paystack.

In deployments, run an ASGI server against `core.asgi:application`. The
repository's Docker and Render commands use Daphne. Do not use `runserver` when
testing live telemetry; its HTTP 404 for the WebSocket handshake indicates the
wrong server interface, not a missing Channels route.
