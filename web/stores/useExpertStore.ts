import { create } from "zustand";
import type {
  ExpertMessage,
  ExpertStatus,
  ExpertType,
  ExpertProfile,
  ThinkingItem,
  GraphNode,
  ToolCallData,
  ToolResultData,
  BeliefUpdatedData,
} from "@/types/expert";
import { DEFAULT_EXPERT_PROFILES } from "@/types/expert";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
let _abort: AbortController | null = null;

/** 每个专家独立的对话历史 */
type ChatHistory = Record<ExpertType, ExpertMessage[]>;

interface ExpertStore {
  /** 当前选中的专家类型 */
  activeExpert: ExpertType;
  /** 所有专家的配置信息 */
  profiles: ExpertProfile[];
  /** 每个专家的独立对话历史 */
  chatHistories: ChatHistory;
  /** 当前状态 */
  status: ExpertStatus;
  error: string | null;

  /** 切换专家 */
  setActiveExpert: (type: ExpertType) => void;
  /** 发送消息 */
  sendMessage: (text: string) => Promise<void>;
  /** 清除当前专家的对话 */
  clearChat: () => void;
  /** 清除所有对话 */
  reset: () => void;
  /** 加载专家配置 */
  fetchProfiles: () => Promise<void>;
}

function newId() {
  return Math.random().toString(36).slice(2);
}

const EMPTY_HISTORY: ChatHistory = {
  data: [],
  quant: [],
  info: [],
  industry: [],
  rag: [],
};

export const useExpertStore = create<ExpertStore>((set, get) => ({
  activeExpert: "data",
  profiles: DEFAULT_EXPERT_PROFILES,
  chatHistories: { ...EMPTY_HISTORY },
  status: "idle",
  error: null,

  setActiveExpert: (type: ExpertType) => {
    // 如果当前正在 thinking，先 abort
    if (get().status === "thinking") {
      _abort?.abort();
      _abort = null;
    }
    set({ activeExpert: type, status: "idle", error: null });
  },

  clearChat: () => {
    const { activeExpert } = get();
    set((s) => ({
      chatHistories: { ...s.chatHistories, [activeExpert]: [] },
      status: "idle",
      error: null,
    }));
  },

  reset: () => {
    _abort?.abort();
    _abort = null;
    set({ chatHistories: { ...EMPTY_HISTORY }, status: "idle", error: null });
  },

  fetchProfiles: async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/expert/profiles`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          set({ profiles: data });
        }
      }
    } catch {
      // 使用默认值
    }
  },

  sendMessage: async (text: string) => {
    // 如果上一次请求还在进行，先中止
    if (_abort) {
      _abort.abort();
      _abort = null;
    }
    // 强制重置 status（防止上次卡在 thinking）
    set({ status: "thinking", error: null });

    const { activeExpert } = get();
    const userMsg: ExpertMessage = {
      id: newId(),
      role: "user",
      content: text,
      thinking: [],
      isStreaming: false,
    };
    const expertMsg: ExpertMessage = {
      id: newId(),
      role: "expert",
      content: "",
      thinking: [],
      isStreaming: true,
    };

    set((s) => ({
      chatHistories: {
        ...s.chatHistories,
        [activeExpert]: [...(s.chatHistories[activeExpert] ?? []), userMsg, expertMsg],
      },
      status: "thinking",
      error: null,
    }));

    _abort = new AbortController();

    try {
      const res = await fetch(`${API_BASE}/api/v1/expert/chat/${activeExpert}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: _abort.signal,
      });

      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let eventType = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventType = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            const rawData = line.slice(5).trim();
            if (!rawData) continue;
            let data: Record<string, unknown>;
            try {
              data = JSON.parse(rawData);
            } catch {
              continue;
            }

            set((s) => {
              const history = [...(s.chatHistories[activeExpert] ?? [])];
              const idx = history.findIndex((m) => m.id === expertMsg.id);
              if (idx === -1) return s;
              const msg: ExpertMessage = {
                ...history[idx],
                thinking: [...history[idx].thinking],
              };

              if (eventType === "reply_token") {
                msg.content += (data.token as string) ?? "";
              } else if (eventType === "reply_complete") {
                msg.content = (data.full_text as string) ?? msg.content;
                msg.isStreaming = false;
              } else if (eventType === "graph_recall") {
                msg.thinking = [
                  ...msg.thinking,
                  { type: "graph_recall" as const, nodes: data.nodes as GraphNode[] },
                ];
              } else if (eventType === "tool_call") {
                msg.thinking = [
                  ...msg.thinking,
                  { type: "tool_call" as const, data: data as unknown as ToolCallData },
                ];
              } else if (eventType === "tool_result") {
                msg.thinking = [
                  ...msg.thinking,
                  { type: "tool_result" as const, data: data as unknown as ToolResultData },
                ];
              } else if (eventType === "belief_updated") {
                msg.thinking = [
                  ...msg.thinking,
                  { type: "belief_updated" as const, data: data as unknown as BeliefUpdatedData },
                ];
              } else if (eventType === "error") {
                msg.content = `错误: ${data.message as string}`;
                msg.isStreaming = false;
              }

              history[idx] = msg;
              return {
                chatHistories: { ...s.chatHistories, [activeExpert]: history },
              };
            });
          }
        }
      }
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") return;
      const errMsg = (e as Error).message;
      set((s) => {
        const history = [...(s.chatHistories[activeExpert] ?? [])];
        const idx = history.findIndex((m) => m.id === expertMsg.id);
        if (idx !== -1) {
          history[idx] = {
            ...history[idx],
            content: `请求失败: ${errMsg}`,
            isStreaming: false,
          };
        }
        return {
          chatHistories: { ...s.chatHistories, [activeExpert]: history },
          status: "error",
          error: errMsg,
        };
      });
    } finally {
      set((s) => (s.status !== "error" ? { status: "idle" } : s));
    }
  },
}));
