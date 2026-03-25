const rawApiBase =
  process.env.NEXT_PUBLIC_API_BASE ??
  process.env.NEXT_PUBLIC_API_URL ??
  "";

export const API_BASE = rawApiBase.replace(/\/+$/, "");

/**
 * SSE 流式请求专用 Base URL。
 * Next.js rewrites 代理会 buffer 整个 SSE 响应，导致前端看不到流式进度。
 * SSE 请求必须直连后端，跳过 Next.js 代理层。
 */
export const SSE_BASE =
  API_BASE || (typeof window !== "undefined" ? "http://localhost:8000" : "");

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
