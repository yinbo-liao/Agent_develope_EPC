const configured = (import.meta.env.VITE_API_URL ?? "").trim();

/**
 * Empty apiBase means "same origin": nginx proxies /api to the backend.
 * In dev, set VITE_API_URL=http://localhost:8000 (docker-compose does).
 */
const apiBase = configured;

const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";

export const runtimeConfig = {
  apiBase,
  wsBase: configured ? configured.replace(/^http/i, "ws") : `${wsProtocol}://${window.location.host}`,
};