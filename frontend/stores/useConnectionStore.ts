/**
 * 连接状态管理 — 管理前端与后端的连接配置 + 用户身份 + JWT 认证
 *
 * 两步式登录流程:
 * 1. URL 输入 → 连接后端 → 获取用户列表
 * 2. 用户选择卡片 → 密码登录 / 注册 / 匿名进入
 *
 * localStorage 持久化:
 * - stockterrain_server_url — 后端地址
 * - stockterrain_token — JWT token（新增）
 * - stockterrain_user — {userId, username}
 * - stockterrain_user_id — 向后兼容 getAuthHeaders fallback
 */

import { create } from "zustand";

const STORAGE_KEY = "stockterrain_server_url";
const TOKEN_KEY = "stockterrain_token";
const USER_STORAGE_KEY = "stockterrain_user";
const USER_ID_KEY = "stockterrain_user_id";

export type AuthStep = "url" | "user_select" | "login" | "register";

export interface UserInfo {
  user_id: string;
  display_name: string;
  created_at: string | null;
  last_login_at: string | null;
}

export interface ConnectionState {
  serverUrl: string | null;
  connected: boolean;
  features: Record<string, boolean> | null;
  serverVersion: string | null;
  llmEnabled: boolean;
  error: string | null;
  loading: boolean;
  userId: string | null;
  username: string | null;
  token: string | null;
  users: UserInfo[];
  authStep: AuthStep;
  selectedUser: string | null;
  // actions
  connectServer: (url: string) => Promise<boolean>;
  fetchUsers: () => Promise<void>;
  login: (username: string, password: string) => Promise<boolean>;
  register: (username: string, password: string, displayName?: string) => Promise<boolean>;
  enterAnonymous: () => void;
  selectUser: (userId: string) => void;
  goToRegister: () => void;
  backToUserSelect: () => void;
  backToUrl: () => void;
  logout: () => void;
  disconnect: () => void;
  bootstrap: () => Promise<boolean>;
}

// ─── localStorage helpers ────────────────────────────

function readStored(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (value) {
      localStorage.setItem(key, value);
    } else {
      localStorage.removeItem(key);
    }
  } catch {}
}

function readStoredUser(): { userId: string; username: string } | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = localStorage.getItem(USER_STORAGE_KEY);
    if (stored) return JSON.parse(stored);
  } catch {}
  return null;
}

function writeStoredUser(userId: string | null, username: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (userId && username) {
      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify({ userId, username }));
      localStorage.setItem(USER_ID_KEY, userId);
    } else {
      localStorage.removeItem(USER_STORAGE_KEY);
      localStorage.removeItem(USER_ID_KEY);
    }
  } catch {}
}

// ─── 初始状态从 localStorage 恢复 ─────────────────────
const storedUser = readStoredUser();
const storedToken = readStored(TOKEN_KEY);

export const useConnectionStore = create<ConnectionState>((set, get) => ({
  serverUrl: readStored(STORAGE_KEY),
  connected: false,
  features: null,
  serverVersion: null,
  llmEnabled: false,
  error: null,
  loading: false,
  userId: storedUser?.userId ?? null,
  username: storedUser?.username ?? null,
  token: storedToken,
  users: [],
  authStep: "url",
  selectedUser: null,

  connectServer: async (url: string) => {
    const normalizedUrl = url.replace(/\/+$/, "");
    set({ loading: true, error: null });

    try {
      const resp = await fetch(`${normalizedUrl}/api/v1/app/bootstrap`, {
        method: "GET",
        signal: AbortSignal.timeout(10000),
      });

      if (!resp.ok) {
        throw new Error(`服务器返回 ${resp.status}`);
      }

      const data = await resp.json();

      // 持久化 URL
      writeStored(STORAGE_KEY, normalizedUrl);

      set({
        serverUrl: normalizedUrl,
        features: data.features ?? null,
        serverVersion: data.version ?? null,
        llmEnabled: data.llm_enabled ?? false,
        error: null,
        loading: false,
      });

      // 获取用户列表后进入用户选择步骤
      await get().fetchUsers();
      set({ authStep: "user_select" });

      return true;
    } catch (err) {
      const message =
        err instanceof TypeError
          ? "无法连接到服务器，请检查地址是否正确"
          : err instanceof DOMException && err.name === "AbortError"
          ? "连接超时，请检查网络或服务器状态"
          : err instanceof Error
          ? err.message
          : "连接失败";

      set({
        connected: false,
        error: message,
        loading: false,
      });

      return false;
    }
  },

  fetchUsers: async () => {
    const { serverUrl } = get();
    if (!serverUrl) return;

    try {
      const resp = await fetch(`${serverUrl}/api/v1/app/users`, {
        method: "GET",
        signal: AbortSignal.timeout(10000),
      });
      if (resp.ok) {
        const data = await resp.json();
        set({ users: data.users ?? [] });
      }
    } catch (err) {
      // 用户列表获取失败不阻塞流程
      set({ users: [] });
    }
  },

  login: async (username: string, password: string) => {
    const { serverUrl } = get();
    if (!serverUrl) return false;

    set({ loading: true, error: null });

    try {
      const resp = await fetch(`${serverUrl}/api/v1/app/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        signal: AbortSignal.timeout(10000),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "登录失败" }));
        throw new Error(err.detail || "登录失败");
      }

      const data = await resp.json();

      // 持久化
      writeStored(TOKEN_KEY, data.token);
      writeStoredUser(data.user_id, data.display_name || username);

      set({
        token: data.token,
        userId: data.user_id,
        username: data.display_name || username,
        connected: true,
        error: null,
        loading: false,
      });

      return true;
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "登录失败";
      set({ error: message, loading: false });
      return false;
    }
  },

  register: async (username: string, password: string, displayName?: string) => {
    const { serverUrl } = get();
    if (!serverUrl) return false;

    set({ loading: true, error: null });

    try {
      const resp = await fetch(`${serverUrl}/api/v1/app/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          password,
          display_name: displayName || undefined,
        }),
        signal: AbortSignal.timeout(10000),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "注册失败" }));
        throw new Error(err.detail || "注册失败");
      }

      const data = await resp.json();

      // 持久化
      writeStored(TOKEN_KEY, data.token);
      writeStoredUser(data.user_id, data.display_name || username);

      set({
        token: data.token,
        userId: data.user_id,
        username: data.display_name || username,
        connected: true,
        error: null,
        loading: false,
      });

      return true;
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "注册失败";
      set({ error: message, loading: false });
      return false;
    }
  },

  enterAnonymous: () => {
    writeStored(TOKEN_KEY, null);
    writeStoredUser("anonymous", "anonymous");

    set({
      token: null,
      userId: "anonymous",
      username: null,
      connected: true,
      error: null,
    });
  },

  selectUser: (userId: string) => {
    set({ authStep: "login", selectedUser: userId, error: null });
  },

  goToRegister: () => {
    set({ authStep: "register", error: null });
  },

  backToUserSelect: () => {
    set({ authStep: "user_select", selectedUser: null, error: null });
  },

  backToUrl: () => {
    set({
      authStep: "url",
      serverUrl: null,
      connected: false,
      users: [],
      selectedUser: null,
      error: null,
    });
    writeStored(STORAGE_KEY, null);
  },

  logout: () => {
    writeStored(TOKEN_KEY, null);
    writeStoredUser(null, null);
    set({
      token: null,
      userId: null,
      username: null,
      connected: false,
      authStep: "user_select",
      selectedUser: null,
      error: null,
    });
    // 刷新用户列表
    get().fetchUsers();
  },

  disconnect: () => {
    writeStored(STORAGE_KEY, null);
    writeStored(TOKEN_KEY, null);
    writeStoredUser(null, null);
    set({
      serverUrl: null,
      connected: false,
      features: null,
      serverVersion: null,
      llmEnabled: false,
      error: null,
      loading: false,
      userId: null,
      username: null,
      token: null,
      users: [],
      authStep: "url",
      selectedUser: null,
    });
  },

  bootstrap: async () => {
    const { serverUrl, token, userId } = get();
    if (!serverUrl) return false;

    // 有 JWT token → 尝试自动恢复
    if (token) {
      set({ loading: true, error: null });

      try {
        // 先验证连接
        const bootstrapResp = await fetch(`${serverUrl}/api/v1/app/bootstrap`, {
          method: "GET",
          signal: AbortSignal.timeout(10000),
        });
        if (!bootstrapResp.ok) throw new Error("服务器连接失败");
        const bootstrapData = await bootstrapResp.json();

        // 验证 token 是否有效：用 token 请求 users 端点
        const verifyResp = await fetch(`${serverUrl}/api/v1/app/users`, {
          method: "GET",
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(10000),
        });

        if (verifyResp.ok) {
          set({
            features: bootstrapData.features ?? null,
            serverVersion: bootstrapData.version ?? null,
            llmEnabled: bootstrapData.llm_enabled ?? false,
            connected: true,
            loading: false,
          });
          return true;
        }

        // token 失效 → 清除，显示登录页
        writeStored(TOKEN_KEY, null);
        writeStoredUser(null, null);
        set({
          token: null,
          userId: null,
          username: null,
          connected: false,
          loading: false,
          features: bootstrapData.features ?? null,
          serverVersion: bootstrapData.version ?? null,
          llmEnabled: bootstrapData.llm_enabled ?? false,
        });

        // 获取用户列表供选择
        await get().fetchUsers();
        set({ authStep: "user_select" });
        return false;
      } catch {
        set({ loading: false, error: null });
        return false;
      }
    }

    // anonymous 用户 → 直接连接
    if (userId === "anonymous") {
      return await get().connectServer(serverUrl).then(async (ok) => {
        if (ok) {
          get().enterAnonymous();
          return true;
        }
        return false;
      });
    }

    // 无 token 无 userId → 尝试连接服务器展示用户列表
    if (serverUrl) {
      return await get().connectServer(serverUrl);
    }

    return false;
  },
}));
