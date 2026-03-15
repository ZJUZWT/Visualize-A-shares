/**
 * 投资专家 Agent 状态管理 (Zustand)
 *
 * 功能：
 * - 管理专家 Agent 的信念、立场、知识图谱
 * - SSE 流式对话
 * - 信念更新和记忆管理
 */

import { create } from "zustand";

const SSE_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// ─── Types ────────────────────────────────────────

export interface BeliefNode {
  id: string;
  type: "belief";
  content: string;
  confidence: number;
  created_at: string;
}

export interface StanceNode {
  id: string;
  type: "stance";
  target: string;
  signal: "bullish" | "bearish" | "neutral";
  score: number;
  confidence: number;
  created_at: string;
}

export interface ExpertMessage {
  id: string;
  role: "user" | "expert";
  content: string;
  timestamp: number;
  isStreaming?: boolean;
}

export interface KnowledgeGraphStats {
  num_nodes: number;
  num_edges: number;
  node_types: Record<string, number>;
  edge_relations: Record<string, number>;
}

interface ExpertState {
  // ─── 对话状态 ────────────────────
  messages: ExpertMessage[];
  isStreaming: boolean;
  error: string | null;

  // ─── 面板状态 ────────────────────
  isPanelOpen: boolean;

  // ─── 专家状态 ────────────────────
  beliefs: BeliefNode[];
  stances: StanceNode[];
  kgStats: KnowledgeGraphStats | null;
  sessionId: string | null;

  // ─── Actions ─────────────────────
  togglePanel: () => void;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
  fetchBeliefs: () => Promise<void>;
  fetchStances: () => Promise<void>;
  fetchKGStats: () => Promise<void>;
  setSessionId: (id: string) => void;
}

let messageCounter = 0;
function nextId() {
  return `expert_msg_${Date.now()}_${++messageCounter}`;
}

function generateSessionId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

export const useExpertStore = create<ExpertState>((set, get) => ({
  messages: [],
  isStreaming: false,
  error: null,

  isPanelOpen: false,

  beliefs: [],
  stances: [],
  kgStats: null,
  sessionId: null,

  togglePanel: () => set((s) => ({ isPanelOpen: !s.isPanelOpen })),

  setSessionId: (id: string) => set({ sessionId: id }),

  fetchBeliefs: async () => {
    try {
      const res = await fetch(`${SSE_API_BASE}/api/v1/expert/beliefs`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      set({ beliefs: data.beliefs || [] });
    } catch (e) {
      console.error("获取信念失败:", e);
      set({ error: "获取信念失败" });
    }
  },

  fetchStances: async () => {
    try {
      const res = await fetch(`${SSE_API_BASE}/api/v1/expert/stances`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      set({ stances: data.stances || [] });
    } catch (e) {
      console.error("获取立场失败:", e);
      set({ error: "获取立场失败" });
    }
  },

  fetchKGStats: async () => {
    try {
      const res = await fetch(
        `${SSE_API_BASE}/api/v1/expert/knowledge-graph/stats`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      set({ kgStats: data });
    } catch (e) {
      console.error("获取知识图谱统计失败:", e);
    }
  },

  sendMessage: async (content: string) => {
    const { messages, sessionId } = get();

    // 生成 session ID（如果没有）
    const finalSessionId = sessionId || generateSessionId();
    if (!sessionId) {
      set({ sessionId: finalSessionId });
    }

    // 添加用户消息
    const userMsg: ExpertMessage = {
      id: nextId(),
      role: "user",
      content,
      timestamp: Date.now(),
    };

    // 添加空的 expert 消息（流式填充）
    const expertMsg: ExpertMessage = {
      id: nextId(),
      role: "expert",
      content: "",
      timestamp: Date.now(),
      isStreaming: true,
    };

    set({
      messages: [...messages, userMsg, expertMsg],
      isStreaming: true,
      error: null,
    });

    try {
      const res = await fetch(`${SSE_API_BASE}/api/v1/expert/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: content,
          session_id: finalSessionId,
        }),
      });

      if (!res.ok) {
        const errBody = await res.text();
        let detail = `HTTP ${res.status}`;
        try {
          detail = JSON.parse(errBody).detail || detail;
        } catch {}
        throw new Error(detail);
      }

      // SSE 流式读取
      const reader = res.body?.getReader();
      if (!reader) throw new Error("浏览器不支持流式读取");

      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) continue;
          if (line.startsWith("data: ")) {
            const data = line.slice(6);
            fullContent += data;

            // 更新 expert 消息内容
            set((s) => ({
              messages: s.messages.map((m) =>
                m.id === expertMsg.id
                  ? { ...m, content: fullContent }
                  : m
              ),
            }));
          }
        }
      }

      // 流结束
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === expertMsg.id
            ? { ...m, content: fullContent || "（空回复）", isStreaming: false }
            : m
        ),
        isStreaming: false,
      }));

      // 更新信念和立场
      await get().fetchBeliefs();
      await get().fetchStances();
      await get().fetchKGStats();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : "发送消息失败";
      set((s) => ({
        error: errorMsg,
        isStreaming: false,
        messages: s.messages.map((m) =>
          m.id === expertMsg.id
            ? { ...m, content: `❌ ${errorMsg}`, isStreaming: false }
            : m
        ),
      }));
    }
  },

  clearMessages: () => set({ messages: [], error: null }),
}));
