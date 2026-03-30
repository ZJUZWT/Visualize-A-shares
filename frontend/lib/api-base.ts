/**
 * API Base URL — 支持编译时环境变量和运行时用户配置
 *
 * 优先级:
 * 1. 环境变量 NEXT_PUBLIC_API_BASE / NEXT_PUBLIC_API_URL (编译时注入)
 * 2. localStorage stockterrain_server_url (运行时用户配置)
 * 3. 空字符串 (未配置)
 */

const ENV_API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE ??
  process.env.NEXT_PUBLIC_API_URL ??
  ""
).replace(/\/+$/, "");

export function getApiBase(): string {
  // 1. 编译时环境变量优先
  if (ENV_API_BASE) return ENV_API_BASE;
  // 2. 运行时 localStorage（用户手动配置的远程后端地址）
  if (typeof window !== "undefined") {
    const stored = localStorage.getItem("stockterrain_server_url");
    if (stored) return stored.replace(/\/+$/, "");
  }
  return "";
}

/**
 * SSE 流式请求专用 Base URL。
 * Next.js rewrites 代理会 buffer 整个 SSE 响应，导致前端看不到流式进度。
 * SSE 请求必须直连后端，跳过 Next.js 代理层。
 */
export function getSseBase(): string {
  const base = getApiBase();
  return base || (typeof window !== "undefined" ? "http://localhost:8000" : "");
}

export function buildApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getApiBase()}${normalizedPath}`;
}

export function getWebSocketBase(): string {
  const base = getApiBase();
  if (base) {
    return base.replace(/^http/, "ws");
  }
  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}`;
  }
  return "ws://localhost:8000";
}

/**
 * 获取当前用户的认证 headers。
 * 优先 JWT Bearer token，向后兼容 X-User-Id。
 */
export function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  // 1. JWT token 优先
  const token = localStorage.getItem("stockterrain_token");
  if (token) return { Authorization: `Bearer ${token}` };
  // 2. 向后兼容 X-User-Id（MCP 等场景）
  const userId = localStorage.getItem("stockterrain_user_id");
  if (userId) return { "X-User-Id": userId };
  return {};
}

/**
 * 带用户认证的 fetch 封装。
 * 自动注入 X-User-Id header，其余行为与原生 fetch 一致。
 */
export async function apiFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const authHeaders = getAuthHeaders();
  const mergedHeaders = {
    ...authHeaders,
    ...(init?.headers instanceof Headers
      ? Object.fromEntries(init.headers.entries())
      : Array.isArray(init?.headers)
        ? Object.fromEntries(init!.headers)
        : (init?.headers as Record<string, string> | undefined) ?? {}),
  };
  return fetch(input, { ...init, headers: mergedHeaders });
}
