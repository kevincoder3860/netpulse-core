const LOCAL_API_BASE_URL = 'http://localhost:8000/api/v1';
const PRODUCTION_API_BASE_URL = 'https://netpulse-backend-i9fv.onrender.com/api/v1';

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL?.trim()
  || (import.meta.env.DEV ? LOCAL_API_BASE_URL : PRODUCTION_API_BASE_URL)
).replace(/\/+$/, '');

export const API_FALLBACK_ROOT = import.meta.env.DEV
  ? 'http://127.0.0.1:8000/api/v1'
  : '';

export const API_TOKEN_ROOT = (
  import.meta.env.VITE_API_TOKEN_URL?.trim()
  || `${API_BASE_URL}/auth`
).replace(/\/+$/, '');

export function resolveWebSocketBaseUrl(): string {
  const configured = import.meta.env.VITE_WS_BASE_URL?.trim();
  if (configured) {
    return configured.replace(/\/+$/, '');
  }

  const url = new URL(API_BASE_URL, window.location.origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.origin;
}
