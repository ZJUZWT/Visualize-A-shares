const rawApiBase =
  process.env.NEXT_PUBLIC_API_BASE ??
  process.env.NEXT_PUBLIC_API_URL ??
  "";

export const API_BASE = rawApiBase.replace(/\/+$/, "");

export function buildApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalizedPath}`;
}

export function getWebSocketBase(): string {
  if (API_BASE) {
    return API_BASE.replace(/^http/, "ws");
  }
  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}`;
  }
  return "ws://localhost:8000";
}
