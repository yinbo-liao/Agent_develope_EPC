import { useEffect, useRef, useCallback } from 'react';

const MAX_RECONNECT_DELAY_MS = 30000;
const BASE_RECONNECT_DELAY_MS = 3000;
const BACKOFF_MULTIPLIER = 2;

export function useWebSocket(projectId: string | undefined, onMessage: (data: unknown) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);

  const connect = useCallback(() => {
    if (!projectId) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const ws = new WebSocket(`${protocol}//${host}/ws/${projectId}`);
    ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch { /* malformed message */ } };
    ws.onerror = () => { /* connection error — onclose will trigger reconnect */ };
    ws.onclose = () => {
      const delay = Math.min(
        BASE_RECONNECT_DELAY_MS * Math.pow(BACKOFF_MULTIPLIER, reconnectAttemptRef.current),
        MAX_RECONNECT_DELAY_MS,
      );
      reconnectAttemptRef.current += 1;
      reconnectTimeoutRef.current = setTimeout(connect, delay);
    };
    ws.onopen = () => {
      reconnectAttemptRef.current = 0; // Reset backoff on successful connection
    };
    wsRef.current = ws;
  }, [projectId, onMessage]);

  useEffect(() => {
    reconnectAttemptRef.current = 0;
    connect();
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      wsRef.current?.close();
    };
  }, [connect]);
}
