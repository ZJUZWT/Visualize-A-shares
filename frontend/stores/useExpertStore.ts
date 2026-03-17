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
/** 每个专家独立的 AbortController（支持并行生成） */
const _abortMap: Map<ExpertType, AbortController> = new Map();

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
  /** 每个专家独立的状态（支持并行） */
  statusMap: Record<ExpertType, ExpertStatus>;
  errorMap: Record<ExpertType, string | null>;
  /** 当前活跃专家的状态（便捷 getter） */
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
  /** 停止当前流式请求 */
  stopStreaming: () => void;
  /** 重试失败的消息 */
  retryMessage: (messageId: string) => Promise<void>;
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

const EMPTY_STATUS: Record<ExpertType, ExpertStatus> = {
  data: "idle",
  quant: "idle",
  info: "idle",
  industry: "idle",
  rag: "idle",
};

const EMPTY_ERRORS: Record<ExpertType, string | null> = {
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
  statusMap: { ...EMPTY_STATUS },
  errorMap: { ...EMPTY_ERRORS },
  status: "idle",
  error: null,
  sessions: { ...EMPTY_SESSIONS },
  activeSessions: { ...EMPTY_ACTIVE },

  setActiveExpert: (type: ExpertType) => {
    // 切换专家时 **不中止** 任何请求，让其在后台继续生成
    set((s) => ({
      activeExpert: type,
      // 同步更新便捷 getter 到目标专家的状态
      status: s.statusMap[type],
      error: s.errorMap[type],
    }));
    // 加载该专家的 sessions
    get().fetchSessions(type);
  },

  clearChat: () => {
    const { activeExpert } = get();
    // 中止当前专家的请求
    const ac = _abortMap.get(activeExpert);
    if (ac) { ac.abort(); _abortMap.delete(activeExpert); }
    set((s) => ({
      chatHistories: { ...s.chatHistories, [activeExpert]: [] },
      activeSessions: { ...s.activeSessions, [activeExpert]: null },
      statusMap: { ...s.statusMap, [activeExpert]: "idle" },
      errorMap: { ...s.errorMap, [activeExpert]: null },
      status: "idle",
      error: null,
    }));
  },

  reset: () => {
    // 中止所有专家的请求
    for (const ac of _abortMap.values()) ac.abort();
    _abortMap.clear();
    set({
      chatHistories: { ...EMPTY_HISTORY },
      activeSessions: { ...EMPTY_ACTIVE },
      statusMap: { ...EMPTY_STATUS },
      errorMap: { ...EMPTY_ERRORS },
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
    // 中止当前专家的流式请求（同一专家内切 session 才需要停）
    const ac = _abortMap.get(activeExpert);
    if (ac) { ac.abort(); _abortMap.delete(activeExpert); }
    set((s) => ({
      activeSessions: { ...s.activeSessions, [activeExpert]: sessionId },
      statusMap: { ...s.statusMap, [activeExpert]: "idle" },
      errorMap: { ...s.errorMap, [activeExpert]: null },
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
        // 只有当 activeSession 还是这个 session 时才更新（防止用户快速切换导致数据错乱）
        if (get().activeSessions[activeExpert] === sessionId) {
          set((s) => ({
            chatHistories: {
              ...s.chatHistories,
              [activeExpert]: expertMessages,
            },
          }));
        }
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

  stopStreaming: () => {
    const { activeExpert } = get();
    // 只中止当前专家的网络请求
    const ac = _abortMap.get(activeExpert);
    if (ac) { ac.abort(); _abortMap.delete(activeExpert); }
    // 将当前专家的 streaming 消息标记为完成
    set((s) => {
      const history = [...(s.chatHistories[activeExpert] ?? [])];
      const streamIdx = history.findIndex((m) => m.isStreaming);
      if (streamIdx !== -1) {
        history[streamIdx] = {
          ...history[streamIdx],
          isStreaming: false,
          content: history[streamIdx].content || "（已停止生成）",
        };
      }
      return {
        chatHistories: { ...s.chatHistories, [activeExpert]: history },
        statusMap: { ...s.statusMap, [activeExpert]: "idle" },
        status: "idle",
      };
    });
  },

  retryMessage: async (messageId: string) => {
    const { activeExpert, chatHistories } = get();
    const history = chatHistories[activeExpert] ?? [];
    const failedMsg = history.find((m) => m.id === messageId);
    if (!failedMsg || failedMsg.role !== "user" || failedMsg.sendStatus !== "failed") return;

    // 找到这条 user 消息和紧跟其后的 expert 消息并移除
    const userIdx = history.findIndex((m) => m.id === messageId);
    const newHistory = [...history];
    // 删除 user + expert pair
    if (userIdx !== -1) {
      const removeCount = userIdx + 1 < newHistory.length && newHistory[userIdx + 1].role === "expert" ? 2 : 1;
      newHistory.splice(userIdx, removeCount);
    }
    set((s) => ({
      chatHistories: { ...s.chatHistories, [activeExpert]: newHistory },
    }));
    // 重新发送
    await get().sendMessage(failedMsg.content);
  },

  sendMessage: async (text: string) => {
    const { activeExpert, activeSessions } = get();
    const expertType = activeExpert; // 闭包捕获，防止中途切走后写错专家

    // 如果该专家已有进行中的请求，先中止（同一专家不并发）
    const existingAc = _abortMap.get(expertType);
    if (existingAc) { existingAc.abort(); _abortMap.delete(expertType); }

    // 辅助函数：更新指定专家的 status
    const setExpertStatus = (s: ExpertStatus, err: string | null = null) => {
      set((prev) => {
        const newStatusMap = { ...prev.statusMap, [expertType]: s };
        const newErrorMap = { ...prev.errorMap, [expertType]: err };
        return {
          statusMap: newStatusMap,
          errorMap: newErrorMap,
          // 只有当该专家是当前活跃专家时才同步便捷 getter
          ...(prev.activeExpert === expertType ? { status: s, error: err } : {}),
        };
      });
    };

    setExpertStatus("thinking");

    // 自动创建 session（如果没有）
    let sessionId = activeSessions[expertType];
    if (!sessionId) {
      sessionId = await get().createSession(expertType);
    }

    const userMsg: ExpertMessage = {
      id: newId(),
      role: "user",
      content: text,
      thinking: [],
      isStreaming: false,
      sendStatus: "pending",
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
        [expertType]: [
          ...(s.chatHistories[expertType] ?? []),
          userMsg,
          expertMsg,
        ],
      },
    }));

    // 立即将用户消息写入 DB
    if (sessionId) {
      try {
        await fetch(`${API_BASE}/api/v1/expert/sessions/${sessionId}/messages/save-user`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: text }),
        });
        get().fetchSessions(expertType);
      } catch {
        // 写入失败不阻塞发送
      }
    }

    // 标记 user 消息为已发送
    set((s) => {
      const history = [...(s.chatHistories[expertType] ?? [])];
      const idx = history.findIndex((m) => m.id === userMsg.id);
      if (idx !== -1) {
        history[idx] = { ...history[idx], sendStatus: "sent" };
      }
      return { chatHistories: { ...s.chatHistories, [expertType]: history } };
    });

    const ac = new AbortController();
    _abortMap.set(expertType, ac);

    try {
      const res = await fetch(
        `${API_BASE}/api/v1/expert/chat/${expertType}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: text,
            session_id: sessionId,
          }),
          signal: ac.signal,
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
              const history = [...(s.chatHistories[expertType] ?? [])];
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
                    status: "pending" as const,
                  },
                ];
              } else if (eventType === "tool_result") {
                const resultData = data as unknown as ToolResultData;
                const callIdx = msg.thinking.findLastIndex(
                  (t) =>
                    t.type === "tool_call" &&
                    t.data.engine === resultData.engine &&
                    t.data.action === resultData.action &&
                    t.status === "pending"
                );
                if (callIdx !== -1) {
                  const callItem = msg.thinking[callIdx] as Extract<typeof msg.thinking[number], { type: "tool_call" }>;
                  msg.thinking = [...msg.thinking];
                  msg.thinking[callIdx] = {
                    ...callItem,
                    result: resultData,
                    status: resultData.hasError ? "error" : "done",
                  };
                } else {
                  msg.thinking = [
                    ...msg.thinking,
                    { type: "tool_result" as const, data: resultData },
                  ];
                }
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
                  [expertType]: history,
                },
              };
            });
          }
        }
      }

      // 完成后刷新 session 列表
      if (sessionId) {
        get().fetchSessions(expertType);
      }
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") {
        // abort 时将 streaming 消息标记为完成
        set((s) => {
          const history = [...(s.chatHistories[expertType] ?? [])];
          const idx = history.findIndex((m) => m.id === expertMsg.id);
          if (idx !== -1) {
            history[idx] = {
              ...history[idx],
              isStreaming: false,
              content: history[idx].content || "（已停止生成）",
            };
          }
          const newStatusMap = { ...s.statusMap, [expertType]: "idle" as ExpertStatus };
          return {
            chatHistories: { ...s.chatHistories, [expertType]: history },
            statusMap: newStatusMap,
            ...(s.activeExpert === expertType ? { status: "idle" as ExpertStatus } : {}),
          };
        });
        return;
      }
      const errMsg = (e as Error).message;
      set((s) => {
        const history = [...(s.chatHistories[expertType] ?? [])];
        const userIdx = history.findIndex((m) => m.id === userMsg.id);
        if (userIdx !== -1) {
          history[userIdx] = { ...history[userIdx], sendStatus: "failed" };
        }
        const expIdx = history.findIndex((m) => m.id === expertMsg.id);
        if (expIdx !== -1) {
          history[expIdx] = {
            ...history[expIdx],
            content: `请求失败: ${errMsg}`,
            isStreaming: false,
          };
        }
        const newStatusMap = { ...s.statusMap, [expertType]: "error" as ExpertStatus };
        const newErrorMap = { ...s.errorMap, [expertType]: errMsg };
        return {
          chatHistories: { ...s.chatHistories, [expertType]: history },
          statusMap: newStatusMap,
          errorMap: newErrorMap,
          ...(s.activeExpert === expertType ? { status: "error" as ExpertStatus, error: errMsg } : {}),
        };
      });
    } finally {
      _abortMap.delete(expertType);
      set((s) => {
        if (s.statusMap[expertType] !== "error") {
          const newStatusMap = { ...s.statusMap, [expertType]: "idle" as ExpertStatus };
          return {
            statusMap: newStatusMap,
            ...(s.activeExpert === expertType ? { status: "idle" as ExpertStatus } : {}),
          };
        }
        return s;
      });
    }
  },
}));
