import { useCallback, useEffect, useRef } from 'react';
import {
  clearStoredTokens,
  getStoredToken,
  notifyAuthRequired,
  refreshAccessToken,
} from '../lib/api-client';

const MAX_RECONNECT_DELAY_MS = 30000;
const BASE_RECONNECT_DELAY_MS = 3000;
const BACKOFF_MULTIPLIER = 2;
const JITTER_RATIO = 0.2;
const HEARTBEAT_INTERVAL_MS = 30000;
const AUTH_FAILURE_CLOSE_CODE = 1008;

export interface UseWebSocketOptions {
  /** Send a `{"type":"ping"}` heartbeat every 30s while connected. */
  heartbeat?: boolean;
}

/**
 * WebSocket hook for live project updates.
 *
 * Authentication uses the `bearer.<access_token>` WebSocket subprotocol (no
 * token in the query string). On a 1008 policy violation it performs exactly
 * one token refresh and reconnects, then stops. Reconnects use exponential
 * backoff (3s → 30s) with jitter and are cancelled on unmount.
 */
export function useWebSocket(
  projectId: string | undefined,
  onMessage: (data: unknown) => void,
  options: UseWebSocketOptions = {}
) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const authRetryRef = useRef(false);
  const onMessageRef = useRef(onMessage);
  const heartbeatEnabledRef = useRef(Boolean(options.heartbeat));
  const connectRef = useRef<() => void>(() => {});

  // Keep the latest callback without recreating the socket.
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    heartbeatEnabledRef.current = Boolean(options.heartbeat);
  }, [options.heartbeat]);

  const stopHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
  }, []);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (!shouldReconnectRef.current || reconnectTimeoutRef.current) return;

    const base = Math.min(
      BASE_RECONNECT_DELAY_MS * Math.pow(BACKOFF_MULTIPLIER, reconnectAttemptRef.current),
      MAX_RECONNECT_DELAY_MS
    );
    const jitter = base * JITTER_RATIO * Math.random();
    const delay = Math.min(base + jitter, MAX_RECONNECT_DELAY_MS);
    reconnectAttemptRef.current += 1;

    reconnectTimeoutRef.current = setTimeout(() => {
      reconnectTimeoutRef.current = null;
      connectRef.current();
    }, delay);
  }, []);

  const connect = useCallback(() => {
    if (!projectId || !shouldReconnectRef.current) return;

    const existing = wsRef.current;
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/${projectId}`;
    const token = getStoredToken();

    let ws: WebSocket;
    try {
      ws = token ? new WebSocket(url, [`bearer.${token}`]) : new WebSocket(url);
    } catch {
      scheduleReconnect();
      return;
    }

    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttemptRef.current = 0; // Reset backoff on success
      authRetryRef.current = false;
      stopHeartbeat();
      if (heartbeatEnabledRef.current) {
        heartbeatRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, HEARTBEAT_INTERVAL_MS);
      }
    };

    ws.onmessage = (event) => {
      try {
        onMessageRef.current(JSON.parse(event.data as string));
      } catch {
        /* malformed message */
      }
    };

    ws.onerror = () => {
      /* connection error — onclose will trigger reconnect */
    };

    ws.onclose = (event) => {
      stopHeartbeat();
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
      if (!shouldReconnectRef.current) return;

      if (event.code === AUTH_FAILURE_CLOSE_CODE) {
        // Auth rejected: try a single refresh, reconnect once, then give up.
        if (authRetryRef.current) {
          shouldReconnectRef.current = false;
          return;
        }
        authRetryRef.current = true;
        void refreshAccessToken()
          .then(() => {
            if (shouldReconnectRef.current) {
              connectRef.current();
            }
          })
          .catch(() => {
            shouldReconnectRef.current = false;
            clearStoredTokens();
            notifyAuthRequired();
          });
        return;
      }

      scheduleReconnect();
    };
  }, [projectId, scheduleReconnect, stopHeartbeat]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    shouldReconnectRef.current = true;
    authRetryRef.current = false;
    reconnectAttemptRef.current = 0;
    connectRef.current();

    return () => {
      shouldReconnectRef.current = false;
      clearReconnectTimer();
      stopHeartbeat();

      const ws = wsRef.current;
      wsRef.current = null;
      if (ws) {
        // Detach handlers first so onclose cannot schedule a reconnect.
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        try {
          ws.close(1000);
        } catch {
          /* already closed */
        }
      }
    };
  }, [connect, clearReconnectTimer, stopHeartbeat]);
}
