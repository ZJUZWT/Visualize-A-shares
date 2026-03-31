import { create, type StoreApi } from "zustand";
import { getApiBase, getSseBase, apiFetch, getAuthHeaders } from "@/lib/api-base";
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
  ClarificationRequestData,
  ClarificationSelection,
  ClarificationRoundSelection,
  PendingClarification,
  ReasoningSummaryData,
  SelfCritiqueData,
} from "@/types/expert";
import { DEFAULT_EXPERT_PROFILES } from "@/types/expert";

/** 每个专家独立的 AbortController（支持并行生成） */
const _abortMap: Map<ExpertType, AbortController> = new Map();
const CLARIFICATION_EXPERTS = new Set<ExpertType>(["rag", "short_term"]);

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
  /** 多轮渐进模式开关 */
  deepThink: boolean;
  /** 澄清开关（AI 是否先询问分析方向） */
  useClarification: boolean;
  /** 策略卡片开关（AI 是否生成交易计划卡片） */
  useTradePlan: boolean;
  /** 每个专家的 session 列表 */
  sessions: Record<ExpertType, Session[]>;
  /** 每个专家当前激活的 session ID */
  activeSessions: ActiveSessions;
  /** 每个专家是否有待确认的 clarification */
  pendingClarifications: Record<ExpertType, PendingClarification | null>;

  /** 切换专家 */
  setActiveExpert: (type: ExpertType) => void;
  /** 发送消息 */
  sendMessage: (text: string) => Promise<void>;
  /** 选择 clarification 选项并继续分析（单选兼容） */
  submitClarification: (selection: ClarificationSelection) => Promise<void>;
  /** 提交多选 clarification 选项并继续分析 */
  submitClarifications: (selections: ClarificationSelection[]) => Promise<void>;
  /** 停止当前流式请求 */
  stopStreaming: () => void;
  /** 重试失败的消息 */
  retryMessage: (messageId: string) => Promise<void>;
  /** 清除当前专家的对话（新建对话） */
  clearChat: () => void;
  /** 清除所有对话 */
  reset: () => void;
  /** 切换多轮渐进模式 */
  toggleDeepThink: () => void;
  /** 切换澄清开关 */
  toggleClarification: () => void;
  /** 切换策略卡片开关 */
  toggleTradePlan: () => void;
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
  /** 续写被中断的 expert 回复 */
  resumeReply: (messageId: string) => Promise<void>;
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
  short_term: [],
};

const EMPTY_SESSIONS: Record<ExpertType, Session[]> = {
  data: [],
  quant: [],
  info: [],
  industry: [],
  rag: [],
  short_term: [],
};

const EMPTY_ACTIVE: ActiveSessions = {
  data: null,
  quant: null,
  info: null,
  industry: null,
  rag: null,
  short_term: null,
};

const EMPTY_STATUS: Record<ExpertType, ExpertStatus> = {
  data: "idle",
  quant: "idle",
  info: "idle",
  industry: "idle",
  rag: "idle",
  short_term: "idle",
};

const EMPTY_ERRORS: Record<ExpertType, string | null> = {
  data: null,
  quant: null,
  info: null,
  industry: null,
  rag: null,
  short_term: null,
};

const EMPTY_PENDING: Record<ExpertType, PendingClarification | null> = {
  data: null,
  quant: null,
  info: null,
  industry: null,
  rag: null,
  short_term: null,
};

type ExpertSetState = StoreApi<ExpertStore>["setState"];

function setExpertStatus(
  set: ExpertSetState,
  expertType: ExpertType,
  status: ExpertStatus,
  error: string | null = null
) {
  set((prev) => {
    const newStatusMap = { ...prev.statusMap, [expertType]: status };
    const newErrorMap = { ...prev.errorMap, [expertType]: error };
    return {
      statusMap: newStatusMap,
      errorMap: newErrorMap,
      ...(prev.activeExpert === expertType ? { status, error } : {}),
    };
  });
}

function applyEventToMessage(
  message: ExpertMessage,
  eventType: string,
  data: Record<string, unknown>
): ExpertMessage {
  const msg: ExpertMessage = {
    ...message,
    thinking: [...message.thinking],
  };

  if (eventType === "reply_token") {
    msg.content += (data.token as string) ?? "";
  } else if (eventType === "reply_complete") {
    msg.content = (data.full_text as string) ?? msg.content;
    msg.isStreaming = false;
  } else if (eventType === "thinking_round") {
    msg.thinking = [
      ...msg.thinking,
      {
        type: "thinking_round" as const,
        round: data.round as number,
        maxRounds: data.max_rounds as number,
      },
    ];
  } else if (eventType === "graph_recall") {
    msg.thinking = [
      ...msg.thinking,
      {
        type: "graph_recall" as const,
        nodes: data.nodes as GraphNode[],
      },
    ];
  } else if (eventType === "reasoning_summary") {
    msg.thinking = [
      ...msg.thinking,
      {
        type: "reasoning_summary" as const,
        data: data as unknown as ReasoningSummaryData,
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
  } else if (eventType === "self_critique") {
    msg.thinking = [
      ...msg.thinking,
      {
        type: "self_critique" as const,
        data: data as unknown as SelfCritiqueData,
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

  return msg;
}

async function streamExpertReply(opts: {
  expertType: ExpertType;
  expertMessageId: string;
  sessionId: string | null;
  userMessageId?: string;
  payload: Record<string, unknown>;
  set: ExpertSetState;
  get: () => ExpertStore;
}) {
  const { expertType, expertMessageId, sessionId, userMessageId, payload, set, get } = opts;
  const ac = new AbortController();
  _abortMap.set(expertType, ac);

  try {
    const res = await fetch(`${getSseBase()}/api/v1/expert/chat/${expertType}`, {
      method: "POST",
      headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: ac.signal,
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
            const history = [...(s.chatHistories[expertType] ?? [])];
            const idx = history.findIndex((m) => m.id === expertMessageId);
            if (idx === -1) return s;
            history[idx] = applyEventToMessage(history[idx], eventType, data);
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

    // 流结束后确保 isStreaming=false（防止 reply_complete 事件未到达）
    set((s) => {
      const history = [...(s.chatHistories[expertType] ?? [])];
      const idx = history.findIndex((m) => m.id === expertMessageId);
      if (idx !== -1 && history[idx].isStreaming) {
        history[idx] = { ...history[idx], isStreaming: false };
        return { chatHistories: { ...s.chatHistories, [expertType]: history } };
      }
      return s;
    });

    if (sessionId) {
      get().fetchSessions(expertType);
    }
  } catch (e: unknown) {
    if ((e as Error).name === "AbortError") {
      set((s) => {
        const history = [...(s.chatHistories[expertType] ?? [])];
        const idx = history.findIndex((m) => m.id === expertMessageId);
        if (idx !== -1) {
          history[idx] = {
            ...history[idx],
            isStreaming: false,
            content: history[idx].content || "（已停止生成）",
          };
        }
        return {
          chatHistories: { ...s.chatHistories, [expertType]: history },
        };
      });
      return;
    }

    const errMsg = (e as Error).message;
    set((s) => {
      const history = [...(s.chatHistories[expertType] ?? [])];
      if (userMessageId) {
        const userIdx = history.findIndex((m) => m.id === userMessageId);
        if (userIdx !== -1) {
          history[userIdx] = { ...history[userIdx], sendStatus: "failed" };
        }
      }
      const expIdx = history.findIndex((m) => m.id === expertMessageId);
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
      if (s.statusMap[expertType] !== "error" && !s.pendingClarifications[expertType]) {
        const newStatusMap = { ...s.statusMap, [expertType]: "idle" as ExpertStatus };
        return {
          statusMap: newStatusMap,
          ...(s.activeExpert === expertType ? { status: "idle" as ExpertStatus } : {}),
        };
      }
      return s;
    });
  }
}

export const useExpertStore = create<ExpertStore>((set, get) => ({
  activeExpert: "rag",
  profiles: DEFAULT_EXPERT_PROFILES,
  chatHistories: { ...EMPTY_HISTORY },
  statusMap: { ...EMPTY_STATUS },
  errorMap: { ...EMPTY_ERRORS },
  status: "idle",
  error: null,
  deepThink: false,
  useClarification: true,
  useTradePlan: false,
  sessions: { ...EMPTY_SESSIONS },
  activeSessions: { ...EMPTY_ACTIVE },
  pendingClarifications: { ...EMPTY_PENDING },

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
      pendingClarifications: { ...s.pendingClarifications, [activeExpert]: null },
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
      pendingClarifications: { ...EMPTY_PENDING },
      statusMap: { ...EMPTY_STATUS },
      errorMap: { ...EMPTY_ERRORS },
      status: "idle",
      error: null,
    });
  },

  toggleDeepThink: () => {
    set((s) => ({ deepThink: !s.deepThink }));
  },

  toggleClarification: () => {
    set((s) => ({ useClarification: !s.useClarification }));
  },

  toggleTradePlan: () => {
    set((s) => ({ useTradePlan: !s.useTradePlan }));
  },

  fetchProfiles: async () => {
    try {
      const res = await apiFetch(`${getApiBase()}/api/v1/expert/profiles`);
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
      const res = await apiFetch(
        `${getApiBase()}/api/v1/expert/sessions?expert_type=${type}`
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
      const res = await apiFetch(`${getApiBase()}/api/v1/expert/sessions`, {
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
      pendingClarifications: { ...s.pendingClarifications, [activeExpert]: null },
      statusMap: { ...s.statusMap, [activeExpert]: "idle" },
      errorMap: { ...s.errorMap, [activeExpert]: null },
      status: "idle",
      error: null,
    }));

    // 加载该 session 的消息
    try {
      const res = await apiFetch(
        `${getApiBase()}/api/v1/expert/sessions/${sessionId}/messages`
      );
      if (res.ok) {
        const messages: Array<{
          id: string;
          role: string;
          content: string;
          thinking: ThinkingItem[];
          status?: string;
        }> = await res.json();
        const expertMessages: ExpertMessage[] = messages.map((m) => ({
          id: m.id,
          dbMessageId: m.id,
          role: m.role as "user" | "expert",
          content: m.content,
          status: (m.role === "expert" ? (m.status as "completed" | "partial") || "completed" : undefined),
          thinking: (m.thinking || []).map((t: any) => {
            // 兼容旧数据：tool_call 缺少 status 字段时默认设为 "done"（历史数据肯定已完成）
            if (t.type === "tool_call" && !t.status) {
              return {
                type: "tool_call" as const,
                data: t.data,
                result: t.result,
                status: "done" as const,
              };
            }
            if (t.type === "clarification_request" && !t.status) {
              return {
                type: "clarification_request" as const,
                data: t.data,
                status: "selected" as const,
                selectedOption: t.selectedOption,
              };
            }
            return t as ThinkingItem;
          }),
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
      await apiFetch(`${getApiBase()}/api/v1/expert/sessions/${sessionId}`, {
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
          newState.pendingClarifications = {
            ...s.pendingClarifications,
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
    const { activeExpert, activeSessions, pendingClarifications, deepThink, useClarification, useTradePlan } = get();
    const expertType = activeExpert; // 闭包捕获，防止中途切走后写错专家
    if (pendingClarifications[expertType]) return;

    // 如果该专家已有进行中的请求，先中止（同一专家不并发）
    const existingAc = _abortMap.get(expertType);
    if (existingAc) { existingAc.abort(); _abortMap.delete(expertType); }

    // 自动创建 session（如果没有）
    let sessionId = activeSessions[expertType];
    if (!sessionId) {
      sessionId = await get().createSession(expertType);
    }

    const shouldClarify = useClarification && CLARIFICATION_EXPERTS.has(expertType);
    setExpertStatus(set, expertType, shouldClarify ? "clarifying" : "thinking");

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
      isStreaming: true,  // 始终显示 loading 动画（clarify 返回后会关闭）
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
        await apiFetch(`${getApiBase()}/api/v1/expert/sessions/${sessionId}/messages/save-user`, {
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
    if (shouldClarify) {
      try {
        const res = await apiFetch(`${getApiBase()}/api/v1/expert/clarify/${expertType}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: text,
            session_id: sessionId,
            previous_selections: [],
          }),
        });
        const data = await res.json() as ClarificationRequestData;
        const currentRound = data.round ?? 1;
        set((s) => {
          const history = [...(s.chatHistories[expertType] ?? [])];
          const idx = history.findIndex((m) => m.id === expertMsg.id);
          if (idx !== -1) {
            history[idx] = {
              ...history[idx],
              thinking: [
                {
                  type: "clarification_request" as const,
                  data,
                  status: "pending" as const,
                  round: currentRound,
                },
              ],
              isStreaming: false,
            };
          }
          return {
            chatHistories: { ...s.chatHistories, [expertType]: history },
            pendingClarifications: {
              ...s.pendingClarifications,
              [expertType]: {
                sessionId,
                userMessageId: userMsg.id,
                expertMessageId: expertMsg.id,
                request: data,
                originalMessage: text,
                previousSelections: [],
              },
            },
          };
        });
        setExpertStatus(set, expertType, "idle");
        return;
      } catch (e: unknown) {
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
              content: `澄清阶段失败: ${errMsg}`,
              isStreaming: false,
            };
          }
          return {
            chatHistories: { ...s.chatHistories, [expertType]: history },
          };
        });
        setExpertStatus(set, expertType, "error", errMsg);
        return;
      }
    }

    await streamExpertReply({
      expertType,
      expertMessageId: expertMsg.id,
      sessionId,
      userMessageId: userMsg.id,
      payload: {
        message: text,
        session_id: sessionId,
        deep_think: deepThink,
        use_clarification: useClarification,
        enable_trade_plan: useTradePlan,
      },
      set,
      get,
    });
  },

  submitClarification: async (selection: ClarificationSelection) => {
    // 单选兼容包装：转发到 submitClarifications
    await get().submitClarifications([selection]);
  },

  submitClarifications: async (selections: ClarificationSelection[]) => {
    if (selections.length === 0) return;
    const { activeExpert, pendingClarifications, deepThink, useTradePlan } = get();
    const expertType = activeExpert;
    const pending = pendingClarifications[expertType];
    if (!pending) return;

    const existingAc = _abortMap.get(expertType);
    if (existingAc) { existingAc.abort(); _abortMap.delete(expertType); }

    // 当前轮次（从 pending.request 取，默认1）
    const currentRound = pending.request.round ?? 1;

    // 判断是否全部 skip
    const allSkip = selections.every(s => s.skip);

    // 构建这一轮的选择记录（多选 selections 列表 + 旧字段兼容）
    const firstSel = selections[0];
    const thisRoundSelection: ClarificationRoundSelection = {
      round: currentRound,
      selections: selections,
      // 旧字段向后兼容（取第一个选择）
      option_id: firstSel.option_id,
      label: firstSel.label,
      title: firstSel.title,
      focus: firstSel.focus,
      skip: firstSel.skip,
    };

    // 累积所有轮次的选择
    const allRoundSelections = [...pending.previousSelections, thisRoundSelection];

    // 标记当前轮为已选
    set((s) => {
      const history = [...(s.chatHistories[expertType] ?? [])];
      const idx = history.findIndex((m) => m.id === pending.expertMessageId);
      if (idx !== -1) {
        history[idx] = {
          ...history[idx],
          thinking: history[idx].thinking.map((item) =>
            item.type === "clarification_request" && item.status === "pending"
              ? {
                  ...item,
                  status: allSkip ? "skipped" as const : "selected" as const,
                  selectedOption: firstSel,
                  selectedOptions: selections,
                }
              : item
          ),
        };
      }
      return {
        chatHistories: { ...s.chatHistories, [expertType]: history },
      };
    });

    // 如果用户选了 skip，或者后端说不需要继续 (needs_more=false)，直接进入 chat
    const needsMore = pending.request.needs_more !== false; // 默认 true（安全）
    if (allSkip || !needsMore) {
      // 清除 pending，进入 chat
      set((s) => ({
        pendingClarifications: { ...s.pendingClarifications, [expertType]: null },
      }));
      setExpertStatus(set, expertType, "thinking");

      // 设置 streaming 状态
      set((s) => {
        const history = [...(s.chatHistories[expertType] ?? [])];
        const idx = history.findIndex((m) => m.id === pending.expertMessageId);
        if (idx !== -1) {
          history[idx] = { ...history[idx], isStreaming: true };
        }
        return { chatHistories: { ...s.chatHistories, [expertType]: history } };
      });

      await streamExpertReply({
        expertType,
        expertMessageId: pending.expertMessageId,
        sessionId: pending.sessionId,
        payload: {
          message: pending.originalMessage,
          session_id: pending.sessionId,
          deep_think: deepThink,
          enable_trade_plan: useTradePlan,
          clarification_chain: allRoundSelections,
          // 向后兼容：也发送最后一轮的 clarification_selection
          clarification_selection: firstSel,
        },
        set,
        get,
      });
      return;
    }

    // 需要继续追问：调用 /clarify 获取下一轮选项
    setExpertStatus(set, expertType, "clarifying");
    // 显示 loading 动画等待下一轮选项
    set((s) => {
      const history = [...(s.chatHistories[expertType] ?? [])];
      const idx = history.findIndex((m) => m.id === pending.expertMessageId);
      if (idx !== -1) {
        history[idx] = { ...history[idx], isStreaming: true };
      }
      return { chatHistories: { ...s.chatHistories, [expertType]: history } };
    });
    try {
      const res = await fetch(`${getApiBase()}/api/v1/expert/clarify/${expertType}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: pending.originalMessage,
          session_id: pending.sessionId,
          previous_selections: allRoundSelections,
        }),
      });
      const nextData = await res.json() as ClarificationRequestData;
      const nextRound = nextData.round ?? (currentRound + 1);

      // 如果后端返回 should_clarify=false 或没有选项，直接进入 chat
      if (!nextData.should_clarify || !nextData.options?.length) {
        set((s) => ({
          pendingClarifications: { ...s.pendingClarifications, [expertType]: null },
        }));
        setExpertStatus(set, expertType, "thinking");

        set((s) => {
          const history = [...(s.chatHistories[expertType] ?? [])];
          const idx = history.findIndex((m) => m.id === pending.expertMessageId);
          if (idx !== -1) {
            history[idx] = { ...history[idx], isStreaming: true };
          }
          return { chatHistories: { ...s.chatHistories, [expertType]: history } };
        });

        await streamExpertReply({
          expertType,
          expertMessageId: pending.expertMessageId,
          sessionId: pending.sessionId,
          payload: {
            message: pending.originalMessage,
            session_id: pending.sessionId,
            deep_think: deepThink,
            enable_trade_plan: useTradePlan,
            clarification_chain: allRoundSelections,
            clarification_selection: firstSel,
          },
          set,
          get,
        });
        return;
      }

      // 追加新一轮的 clarification_request ThinkingItem
      set((s) => {
        const history = [...(s.chatHistories[expertType] ?? [])];
        const idx = history.findIndex((m) => m.id === pending.expertMessageId);
        if (idx !== -1) {
          history[idx] = {
            ...history[idx],
            thinking: [
              ...history[idx].thinking,
              {
                type: "clarification_request" as const,
                data: nextData,
                status: "pending" as const,
                round: nextRound,
              },
            ],
            isStreaming: false,
          };
        }
        return {
          chatHistories: { ...s.chatHistories, [expertType]: history },
          pendingClarifications: {
            ...s.pendingClarifications,
            [expertType]: {
              sessionId: pending.sessionId,
              userMessageId: pending.userMessageId,
              expertMessageId: pending.expertMessageId,
              request: nextData,
              originalMessage: pending.originalMessage,
              previousSelections: allRoundSelections,
            },
          },
        };
      });
      setExpertStatus(set, expertType, "idle");
    } catch (e: unknown) {
      // 追问失败时降级：直接带已有选择进入 chat
      const errMsg = (e as Error).message;
      console.warn("多轮澄清追问失败，降级进入 chat:", errMsg);
      set((s) => ({
        pendingClarifications: { ...s.pendingClarifications, [expertType]: null },
      }));
      setExpertStatus(set, expertType, "thinking");

      set((s) => {
        const history = [...(s.chatHistories[expertType] ?? [])];
        const idx = history.findIndex((m) => m.id === pending.expertMessageId);
        if (idx !== -1) {
          history[idx] = { ...history[idx], isStreaming: true };
        }
        return { chatHistories: { ...s.chatHistories, [expertType]: history } };
      });

      await streamExpertReply({
        expertType,
        expertMessageId: pending.expertMessageId,
        sessionId: pending.sessionId,
        payload: {
          message: pending.originalMessage,
          session_id: pending.sessionId,
          deep_think: deepThink,
          clarification_chain: allRoundSelections,
          clarification_selection: firstSel,
        },
        set,
        get,
      });
    }
  },

  resumeReply: async (messageId: string) => {
    const { activeExpert, activeSessions } = get();
    const expertType = activeExpert;
    const sessionId = activeSessions[expertType];
    if (!sessionId) return;

    // 找到这条 partial 消息
    const history = get().chatHistories[expertType] ?? [];
    const msgIdx = history.findIndex((m) => m.id === messageId || m.dbMessageId === messageId);
    if (msgIdx === -1) return;
    const msg = history[msgIdx];
    if (msg.role !== "expert" || msg.status !== "partial") return;

    const dbMsgId = msg.dbMessageId;
    if (!dbMsgId) return;

    // 设置为 streaming 状态
    setExpertStatus(set, expertType, "thinking");
    set((s) => {
      const h = [...(s.chatHistories[expertType] ?? [])];
      if (h[msgIdx]) {
        h[msgIdx] = { ...h[msgIdx], isStreaming: true };
      }
      return { chatHistories: { ...s.chatHistories, [expertType]: h } };
    });

    const ac = new AbortController();
    _abortMap.set(expertType, ac);

    try {
      const res = await fetch(`${getSseBase()}/api/v1/expert/chat/resume`, {
        method: "POST",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message_id: dbMsgId }),
        signal: ac.signal,
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

            if (eventType === "resume_token") {
              // 追加 token 到已有 content
              set((s) => {
                const h = [...(s.chatHistories[expertType] ?? [])];
                const idx = h.findIndex((m) => m.id === messageId || m.dbMessageId === messageId);
                if (idx !== -1) {
                  h[idx] = {
                    ...h[idx],
                    content: h[idx].content + ((data.token as string) ?? ""),
                  };
                }
                return { chatHistories: { ...s.chatHistories, [expertType]: h } };
              });
            } else if (eventType === "resume_complete") {
              // 续写完成
              set((s) => {
                const h = [...(s.chatHistories[expertType] ?? [])];
                const idx = h.findIndex((m) => m.id === messageId || m.dbMessageId === messageId);
                if (idx !== -1) {
                  h[idx] = {
                    ...h[idx],
                    isStreaming: false,
                    status: "completed",
                  };
                }
                return { chatHistories: { ...s.chatHistories, [expertType]: h } };
              });
            } else if (eventType === "error") {
              set((s) => {
                const h = [...(s.chatHistories[expertType] ?? [])];
                const idx = h.findIndex((m) => m.id === messageId || m.dbMessageId === messageId);
                if (idx !== -1) {
                  h[idx] = { ...h[idx], isStreaming: false };
                }
                return { chatHistories: { ...s.chatHistories, [expertType]: h } };
              });
            }
          }
        }
      }

      // 流结束后确保 isStreaming=false
      set((s) => {
        const h = [...(s.chatHistories[expertType] ?? [])];
        const idx = h.findIndex((m) => m.id === messageId || m.dbMessageId === messageId);
        if (idx !== -1 && h[idx].isStreaming) {
          h[idx] = { ...h[idx], isStreaming: false, status: "completed" };
        }
        return { chatHistories: { ...s.chatHistories, [expertType]: h } };
      });
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") {
        set((s) => {
          const h = [...(s.chatHistories[expertType] ?? [])];
          const idx = h.findIndex((m) => m.id === messageId || m.dbMessageId === messageId);
          if (idx !== -1) {
            h[idx] = { ...h[idx], isStreaming: false };
          }
          return { chatHistories: { ...s.chatHistories, [expertType]: h } };
        });
        return;
      }
      console.error("resumeReply error:", (e as Error).message);
      set((s) => {
        const h = [...(s.chatHistories[expertType] ?? [])];
        const idx = h.findIndex((m) => m.id === messageId || m.dbMessageId === messageId);
        if (idx !== -1) {
          h[idx] = { ...h[idx], isStreaming: false };
        }
        return { chatHistories: { ...s.chatHistories, [expertType]: h } };
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
