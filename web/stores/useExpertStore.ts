import { create } from "zustand";
import type {
  ExpertMessage,
  ExpertStatus,
  ExpertType,
  ExpertProfile,
  Session,
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
/** 每个专家的当前 session ID */
type ActiveSessions = Record<ExpertType, string | null>;

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
  /** 每个专家的 session 列表 */
  sessions: Record<ExpertType, Session[]>;
  /** 每个专家当前激活的 session ID */
  activeSessions: ActiveSessions;

  /** 切换专家 */
  setActiveExpert: (type: ExpertType) => void;
  /** 发送消息 */
  sendMessage: (text: string) => Promise<void>;
  /** 清除当前专家的对话（新建对话） */
  clearChat: () => void;
  /** 清除所有对话 */
  reset: () => void;
  /** 加载专家配置 */
  fetchProfiles: () => Promise<void>;
  /** 加载 session 列表 */
  fetchSessions: (expertType?: ExpertType) => Promise<void>;
  /** 新建 session */
  createSession: (expertType?: ExpertType) => Promise<string | null>;
  /** 切换 session */
  switchSession: (sessionId: string) => Promise<void>;
  /** 删除 session */
  deleteSession: (sessionId: string) => Promise<void>;
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

const EMPTY_SESSIONS: Record<ExpertType, Session[]> = {
  data: [],
  quant: [],
  info: [],
  industry: [],
  rag: [],
};

const EMPTY_ACTIVE: ActiveSessions = {
  data: null,
  quant: null,
  info: null,
  industry: null,
  rag: null,
};

export const useExpertStore = create<ExpertStore>((set, get) => ({
  activeExpert: "rag",
  profiles: DEFAULT_EXPERT_PROFILES,
  chatHistories: { ...EMPTY_HISTORY },
  status: "idle",
  error: null,
  sessions: { ...EMPTY_SESSIONS },
  activeSessions: { ...EMPTY_ACTIVE },

  setActiveExpert: (type: ExpertType) => {
    // 如果当前正在 thinking，先 abort
    if (get().status === "thinking") {
      _abort?.abort();
      _abort = null;
    }
    set({ activeExpert: type, status: "idle", error: null });
    // 加载该专家的 sessions
    get().fetchSessions(type);
  },

  clearChat: () => {
    const { activeExpert } = get();
    set((s) => ({
      chatHistories: { ...s.chatHistories, [activeExpert]: [] },
      activeSessions: { ...s.activeSessions, [activeExpert]: null },
      status: "idle",
      error: null,
    }));
  },

  reset: () => {
    _abort?.abort();
    _abort = null;
    set({
      chatHistories: { ...EMPTY_HISTORY },
      activeSessions: { ...EMPTY_ACTIVE },
      status: "idle",
      error: null,
    });
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

  fetchSessions: async (expertType?: ExpertType) => {
    const type = expertType || get().activeExpert;
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/expert/sessions?expert_type=${type}`
      );
      if (res.ok) {
        const data = await res.json();
        set((s) => ({
          sessions: { ...s.sessions, [type]: data },
        }));
      }
    } catch {
      // ignore
    }
  },

  createSession: async (expertType?: ExpertType) => {
    const type = expertType || get().activeExpert;
    try {
      const res = await fetch(`${API_BASE}/api/v1/expert/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expert_type: type, title: "新对话" }),
      });
      if (res.ok) {
        const session = await res.json();
        if (session.id) {
          set((s) => ({
            sessions: {
              ...s.sessions,
              [type]: [session, ...(s.sessions[type] || [])],
            },
            activeSessions: { ...s.activeSessions, [type]: session.id },
            chatHistories: { ...s.chatHistories, [type]: [] },
          }));
          return session.id;
        }
      }
    } catch {
      // ignore
    }
    return null;
  },

  switchSession: async (sessionId: string) => {
    const { activeExpert } = get();
    set((s) => ({
      activeSessions: { ...s.activeSessions, [activeExpert]: sessionId },
      chatHistories: { ...s.chatHistories, [activeExpert]: [] },
      status: "idle",
      error: null,
    }));

    // 加载该 session 的消息
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/expert/sessions/${sessionId}/messages`
      );
      if (res.ok) {
        const messages: Array<{
          id: string;
          role: string;
          content: string;
          thinking: ThinkingItem[];
        }> = await res.json();
        const expertMessages: ExpertMessage[] = messages.map((m) => ({
          id: m.id,
          role: m.role as "user" | "expert",
          content: m.content,
          thinking: m.thinking || [],
          isStreaming: false,
        }));
        set((s) => ({
          chatHistories: {
            ...s.chatHistories,
            [activeExpert]: expertMessages,
          },
        }));
      }
    } catch {
      // ignore
    }
  },

  deleteSession: async (sessionId: string) => {
    const { activeExpert, activeSessions } = get();
    try {
      await fetch(`${API_BASE}/api/v1/expert/sessions/${sessionId}`, {
        method: "DELETE",
      });
      set((s) => {
        const filtered = (s.sessions[activeExpert] || []).filter(
          (sess) => sess.id !== sessionId
        );
        const newState: Partial<ExpertStore> = {
          sessions: { ...s.sessions, [activeExpert]: filtered },
        };
        // 如果删除的是当前激活的 session，清空对话
        if (activeSessions[activeExpert] === sessionId) {
          newState.activeSessions = {
            ...s.activeSessions,
            [activeExpert]: null,
          };
          newState.chatHistories = {
            ...s.chatHistories,
            [activeExpert]: [],
          };
        }
        return newState;
      });
    } catch {
      // ignore
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

    const { activeExpert, activeSessions } = get();

    // 自动创建 session（如果没有）
    let sessionId = activeSessions[activeExpert];
    if (!sessionId) {
      sessionId = await get().createSession(activeExpert);
    }

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
        [activeExpert]: [
          ...(s.chatHistories[activeExpert] ?? []),
          userMsg,
          expertMsg,
        ],
      },
      status: "thinking",
      error: null,
    }));

    _abort = new AbortController();

    try {
      const res = await fetch(
        `${API_BASE}/api/v1/expert/chat/${activeExpert}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: text,
            session_id: sessionId,
          }),
          signal: _abort.signal,
        }
      );

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
                  {
                    type: "graph_recall" as const,
                    nodes: data.nodes as GraphNode[],
                  },
                ];
              } else if (eventType === "tool_call") {
                msg.thinking = [
                  ...msg.thinking,
                  {
                    type: "tool_call" as const,
                    data: data as unknown as ToolCallData,
                  },
                ];
              } else if (eventType === "tool_result") {
                msg.thinking = [
                  ...msg.thinking,
                  {
                    type: "tool_result" as const,
                    data: data as unknown as ToolResultData,
                  },
                ];
              } else if (eventType === "belief_updated") {
                msg.thinking = [
                  ...msg.thinking,
                  {
                    type: "belief_updated" as const,
                    data: data as unknown as BeliefUpdatedData,
                  },
                ];
              } else if (eventType === "error") {
                msg.content = `错误: ${data.message as string}`;
                msg.isStreaming = false;
              }

              history[idx] = msg;
              return {
                chatHistories: {
                  ...s.chatHistories,
                  [activeExpert]: history,
                },
              };
            });
          }
        }
      }

      // 完成后刷新 session 列表（标题可能更新了）
      if (sessionId) {
        get().fetchSessions(activeExpert);
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
