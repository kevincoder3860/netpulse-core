import { useCallback, useEffect, useRef, useState } from 'react';
import type { TelemetryHealth } from '@/lib/api';

const MAX_TRAFFIC_SAMPLES = 20;
const INITIAL_BACKOFF_MS = 2000;
const MAX_BACKOFF_MS = 30000;
const RAPID_CLOSE_MS = 2500;

function resolveWsBaseUrl(): string {
  const configured = import.meta.env.VITE_WS_BASE_URL?.trim();
  if (configured) {
    return configured.replace(/\/+$/, '');
  }

  const apiRoot = (import.meta.env.VITE_API_BASE_URL?.trim() || 'http://127.0.0.1:8000/api/v1')
    .replace(/\/+$/, '')
    .replace(/\/api\/v1$/i, '');

  try {
    const url = new URL(apiRoot);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return url.origin;
  } catch {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.hostname}:8000`;
  }
}

function buildTelemetryUrl(tenantId: string, token: string | null): string {
  const base = resolveWsBaseUrl();
  const path = `/ws/telemetry/${encodeURIComponent(tenantId)}/`;
  const url = new URL(path, `${base}/`);
  if (token) {
    url.searchParams.set('token', token);
  }
  return url.toString();
}

export interface UseTelemetryResult {
  telemetryData: TelemetryHealth | null;
  health: TelemetryHealth | null;
  trafficSamples: TelemetryHealth['traffic'][];
  liveTelemetry: { rx_bytes: number; tx_bytes: number; interface: string } | null;
  routerStats: { total_routers: number; online_routers: number; offline_routers: number };
  connected: boolean;
  error: string | null;
}

/**
 * WebSocket telemetry client with generation-guarded reconnects so Strict Mode
 * remounts and server restarts do not cause CONNECT/DISCONNECT storms.
 */
export function useTelemetry(tenantId: string | null | undefined): UseTelemetryResult {
  const [health, setHealth] = useState<TelemetryHealth | null>(null);
  const [trafficSamples, setTrafficSamples] = useState<TelemetryHealth['traffic'][]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);
  const generationRef = useRef(0);
  const intentionalCloseRef = useRef(false);
  const pausedRef = useRef(typeof document !== 'undefined' && document.visibilityState === 'hidden');
  const connectRef = useRef<() => void>(() => undefined);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const closeSocket = useCallback((intentional = false) => {
    intentionalCloseRef.current = intentional;
    generationRef.current += 1;
    clearReconnectTimer();
    const socket = socketRef.current;
    socketRef.current = null;
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      try {
        socket.close(1000, intentional ? 'client-close' : 'reconnect');
      } catch {
        // Ignore teardown races.
      }
    }
    setConnected(false);
  }, [clearReconnectTimer]);

  const scheduleReconnect = useCallback((generation: number, delayMs: number) => {
    clearReconnectTimer();
    reconnectTimerRef.current = window.setTimeout(() => {
      if (generation !== generationRef.current) return;
      if (pausedRef.current || intentionalCloseRef.current) return;
      connectRef.current();
    }, delayMs);
  }, [clearReconnectTimer]);

  const connect = useCallback(() => {
    if (!tenantId || pausedRef.current) {
      return;
    }

    clearReconnectTimer();
    const existing = socketRef.current;
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const generation = ++generationRef.current;
    intentionalCloseRef.current = false;
    const token = localStorage.getItem('np_access');
    const url = buildTelemetryUrl(tenantId, token);
    const openedAt = Date.now();

    let socket: WebSocket;
    try {
      socket = new WebSocket(url);
    } catch {
      setError('Unable to open telemetry WebSocket');
      const delay = backoffRef.current;
      backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
      scheduleReconnect(generation, delay);
      return;
    }

    socketRef.current = socket;

    socket.onopen = () => {
      if (generation !== generationRef.current) return;
      backoffRef.current = INITIAL_BACKOFF_MS;
      setConnected(true);
      setError(null);
    };

    socket.onmessage = (event) => {
      if (generation !== generationRef.current || pausedRef.current) return;
      try {
        const payload = JSON.parse(event.data) as TelemetryHealth;
        if (!payload?.traffic?.timestamp) return;
        setHealth(payload);
        setTrafficSamples((samples) => [...samples, payload.traffic].slice(-MAX_TRAFFIC_SAMPLES));
      } catch {
        setError('Received invalid telemetry payload');
      }
    };

    socket.onerror = () => {
      if (generation !== generationRef.current) return;
      setError('Telemetry WebSocket error');
    };

    socket.onclose = () => {
      if (generation !== generationRef.current) return;
      setConnected(false);
      if (socketRef.current === socket) {
        socketRef.current = null;
      }
      if (intentionalCloseRef.current || pausedRef.current || !tenantId) {
        return;
      }

      const livedMs = Date.now() - openedAt;
      if (livedMs < RAPID_CLOSE_MS) {
        // Server rejected during handshake (auth fail, ASGI error, etc.).
        // Jump straight to MAX_BACKOFF so we don't hammer the server.
        backoffRef.current = MAX_BACKOFF_MS;
      }
      const delay = backoffRef.current;
      scheduleReconnect(generation, delay);
    };
  }, [clearReconnectTimer, scheduleReconnect, tenantId]);

  connectRef.current = connect;

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'hidden') {
        pausedRef.current = true;
        closeSocket(true);
        return;
      }
      pausedRef.current = false;
      backoffRef.current = INITIAL_BACKOFF_MS;
      connect();
    };

    document.addEventListener('visibilitychange', handleVisibility);
    if (document.visibilityState === 'hidden') {
      pausedRef.current = true;
    } else {
      pausedRef.current = false;
      // Small delay so React Strict Mode's double-mount teardown
      // fires before we open the socket, preventing two parallel connections.
      const initialTimer = window.setTimeout(() => {
        connect();
      }, 150);
      return () => {
        window.clearTimeout(initialTimer);
        document.removeEventListener('visibilitychange', handleVisibility);
        closeSocket(true);
      };
    }

    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      closeSocket(true);
    };
  }, [closeSocket, connect]);

  const routerStats = health?.router_stats ?? {
    total_routers: health?.hotspot_status.total ?? 0,
    online_routers: health?.hotspot_status.active ?? 0,
    offline_routers: health?.hotspot_status.inactive ?? 0,
  };

  return {
    telemetryData: health,
    health,
    trafficSamples,
    liveTelemetry: health?.live_telemetry ?? null,
    routerStats,
    connected,
    error,
  };
}

export default useTelemetry;
