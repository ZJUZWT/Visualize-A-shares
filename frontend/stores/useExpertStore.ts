import { create, type StoreApi } from "zustand";
import { getApiBase, getSseBase, apiFetch, getAuthHeaders } from "@/lib/api-base";
import { shouldAutoAdvanceClarification } from "@/lib/clarificationSelection";
import { buildExpertFeedbackPayload } from "@/lib/expertFeedback";
import {
  buildVisibleSessionState,
  reportCancelThenAbort,
  updateSessionHistory,
  type ActiveSessions,
  type SessionErrorMap,
  type SessionHistories,
  type SessionPendingMap,
  type SessionStatusMap,
} from "@/lib/expertSessionContinuity";
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
  ExpertFeedbackDetail,
  ExpertFeedbackResolveResponse,
  ExpertFeedbackSubmitOptions,
  ExpertFeedbackSubmitResponse,
  ExpertFeedbackSummary,
} from "@/types/expert";
import { DEFAULT_EXPERT_PROFILES } from "@/types/expert";

/** 每个 session 独立的 AbortController（同一专家切换会话时不中断原流） */
const _abortMap: Map<string, AbortController> = new Map();
/** 记录每个专家当前运行中的 session，用于保证同专家单流和显示侧边状态。 */
const _streamSessionMap: Map<ExpertType, string> = new Map();
const CLARIFICATION_EXPERTS = new Set<ExpertType>(["rag", "short_term"]);

/** 每个专家独立的对话历史 */
type ChatHistory = Record<ExpertType, ExpertMessage[]>;

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
  /** session 级缓存：后台流继续时，原会话仍能积累最新内容 */
  sessionHistories: SessionHistories;
  sessionPendingClarifications: SessionPendingMap;
  sessionStatusMap: SessionStatusMap;
  sessionErrorMap: SessionErrorMap;

  /** 切换专家 */
  setActiveExpert: (type: ExpertType) => void;
  /** 发送消息（可附带图片） */
  sendMessage: (text: string, images?: string[]) => Promise<void>;
  /** 选择 clarification 选项并继续分析（单选兼容） */
  submitClarification: (selection: ClarificationSelection) => Promise<void>;
  /** 提交多选 clarification 选项并继续分析 */
  submitClarifications: (selections: ClarificationSelection[]) => Promise<void>;
  /** 提交 expert 消息反馈 */
  submitFeedback: (messageId: string, options: ExpertFeedbackSubmitOptions) => Promise<ExpertFeedbackSubmitResponse | null>;
  /** 管理员读取反馈列表 */
  listAdminFeedbackReports: (unresolvedOnly?: boolean, limit?: number) => Promise<ExpertFeedbackSummary[]>;
  /** 管理员读取反馈详情 */
  getAdminFeedbackReport: (feedbackId: string) => Promise<ExpertFeedbackDetail | null>;
  /** 管理员标记反馈已处理 */
  resolveAdminFeedbackReport: (feedbackId: string, resolutionNote?: string) => Promise<boolean>;
  /** 停止当前流式请求 */
  stopStreaming: () => Promise<void>;
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
  resumeReply: (messageId: string, options?: { checkCompleted?: boolean }) => Promise<void>;
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

const EMPTY_SESSION_HISTORIES: SessionHistories = {};
const EMPTY_SESSION_PENDING: SessionPendingMap = {};
const EMPTY_SESSION_STATUS: SessionStatusMap = {};
const EMPTY_SESSION_ERRORS: SessionErrorMap = {};

type ExpertSetState = StoreApi<ExpertStore>["setState"];

function setExpertStatus(
  set: ExpertSetState,
  expertType: ExpertType,
  sessionId: string | null,
  status: ExpertStatus,
  error: string | null = null
) {
  set((prev) => {
    const newStatusMap = { ...prev.statusMap, [expertType]: status };
    const newErrorMap = { ...prev.errorMap, [expertType]: error };
    const newSessionStatusMap = sessionId
      ? { ...prev.sessionStatusMap, [sessionId]: status }
      : prev.sessionStatusMap;
    const newSessionErrorMap = sessionId
      ? { ...prev.sessionErrorMap, [sessionId]: error }
      : prev.sessionErrorMap;
    const isVisibleSession = sessionId && prev.activeSessions[expertType] === sessionId;
    return {
      statusMap: newStatusMap,
      errorMap: newErrorMap,
      sessionStatusMap: newSessionStatusMap,
      sessionErrorMap: newSessionErrorMap,
      ...(prev.activeExpert === expertType && isVisibleSession ? { status, error } : {}),
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
  const streamKey = sessionId || `${expertType}:${expertMessageId}`;
  const ac = new AbortController();
  _abortMap.set(streamKey, ac);
  if (sessionId) {
    _streamSessionMap.set(expertType, sessionId);
  }

  const applyHistoryUpdate = (updater: (history: ExpertMessage[]) => ExpertMessage[]) => {
    set((s) => {
      if (!sessionId) {
        return {
          chatHistories: {
            ...s.chatHistories,
            [expertType]: updater(s.chatHistories[expertType] ?? []),
          },
        };
      }
      return updateSessionHistory({
        expertType,
        sessionId,
        activeSessions: s.activeSessions,
        chatHistories: s.chatHistories,
        sessionHistories: s.sessionHistories,
        updater,
      });
    });
  };

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

          applyHistoryUpdate((history) => {
            const nextHistory = [...history];
            const idx = nextHistory.findIndex((m) => m.id === expertMessageId);
            if (idx === -1) return history;
            nextHistory[idx] = applyEventToMessage(nextHistory[idx], eventType, data);
            return nextHistory;
          });
        }
      }
    }

    // 流结束后确保 isStreaming=false（防止 reply_complete 事件未到达）
    applyHistoryUpdate((history) => {
      const nextHistory = [...history];
      const idx = nextHistory.findIndex((m) => m.id === expertMessageId);
      if (idx !== -1 && nextHistory[idx].isStreaming) {
        nextHistory[idx] = { ...nextHistory[idx], isStreaming: false };
      }
      return nextHistory;
    });

    if (sessionId) {
      get().fetchSessions(expertType);
    }
  } catch (e: unknown) {
    if ((e as Error).name === "AbortError") {
      applyHistoryUpdate((history) => {
        const nextHistory = [...history];
        const idx = nextHistory.findIndex((m) => m.id === expertMessageId);
        if (idx !== -1) {
          nextHistory[idx] = {
            ...nextHistory[idx],
            isStreaming: false,
            content: nextHistory[idx].content || "（已停止生成）",
          };
        }
        return nextHistory;
      });
      return;
    }

    const errMsg = (e as Error).message;
    applyHistoryUpdate((history) => {
      const nextHistory = [...history];
      if (userMessageId) {
        const userIdx = nextHistory.findIndex((m) => m.id === userMessageId);
        if (userIdx !== -1) {
          nextHistory[userIdx] = { ...nextHistory[userIdx], sendStatus: "failed" };
        }
      }
      const expIdx = nextHistory.findIndex((m) => m.id === expertMessageId);
      if (expIdx !== -1) {
        nextHistory[expIdx] = {
          ...nextHistory[expIdx],
          content: `请求失败: ${errMsg}`,
          isStreaming: false,
          interruptionReason: "server_error",
          interruptionDetail: errMsg,
        };
      }
      return nextHistory;
    });
    setExpertStatus(set, expertType, sessionId, "error", errMsg);
  } finally {
    _abortMap.delete(streamKey);
    if (sessionId && _streamSessionMap.get(expertType) === sessionId) {
      _streamSessionMap.delete(expertType);
    }
    set((s) => {
      if (
        sessionId
        && s.sessionStatusMap[sessionId] !== "error"
        && !s.sessionPendingClarifications[sessionId]
      ) {
        const newStatusMap = { ...s.statusMap, [expertType]: "idle" as ExpertStatus };
        const newSessionStatusMap = { ...s.sessionStatusMap, [sessionId]: "idle" as ExpertStatus };
        const isVisibleSession = s.activeSessions[expertType] === sessionId;
        return {
          statusMap: newStatusMap,
          sessionStatusMap: newSessionStatusMap,
          ...(s.activeExpert === expertType && isVisibleSession ? { status: "idle" as ExpertStatus } : {}),
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
  sessionHistories: { ...EMPTY_SESSION_HISTORIES },
  sessionPendingClarifications: { ...EMPTY_SESSION_PENDING },
  sessionStatusMap: { ...EMPTY_SESSION_STATUS },
  sessionErrorMap: { ...EMPTY_SESSION_ERRORS },

  setActiveExpert: (type: ExpertType) => {
    // 切换专家时 **不中止** 任何请求，让其在后台继续生成
    set((s) => {
      const sessionId = s.activeSessions[type];
      return {
        activeExpert: type,
        ...buildVisibleSessionState({
          expertType: type,
          sessionId,
          activeExpert: type,
          chatHistories: s.chatHistories,
          pendingClarifications: s.pendingClarifications,
          sessionHistories: s.sessionHistories,
          sessionPendingClarifications: s.sessionPendingClarifications,
          sessionStatusMap: s.sessionStatusMap,
          sessionErrorMap: s.sessionErrorMap,
        }),
      };
    });
    // 加载该专家的 sessions
    get().fetchSessions(type);
  },

  clearChat: () => {
    const { activeExpert } = get();
    const activeSessionId = get().activeSessions[activeExpert];
    if (activeSessionId) {
      const ac = _abortMap.get(activeSessionId);
      if (ac) {
        ac.abort();
        _abortMap.delete(activeSessionId);
      }
      if (_streamSessionMap.get(activeExpert) === activeSessionId) {
        _streamSessionMap.delete(activeExpert);
      }
    }
    set((s) => {
      const nextSessionHistories = { ...s.sessionHistories };
      const nextSessionPending = { ...s.sessionPendingClarifications };
      const nextSessionStatus = { ...s.sessionStatusMap };
      const nextSessionErrors = { ...s.sessionErrorMap };
      if (activeSessionId) {
        delete nextSessionHistories[activeSessionId];
        delete nextSessionPending[activeSessionId];
        delete nextSessionStatus[activeSessionId];
        delete nextSessionErrors[activeSessionId];
      }
      return {
        chatHistories: { ...s.chatHistories, [activeExpert]: [] },
        activeSessions: { ...s.activeSessions, [activeExpert]: null },
        pendingClarifications: { ...s.pendingClarifications, [activeExpert]: null },
        sessionHistories: nextSessionHistories,
        sessionPendingClarifications: nextSessionPending,
        sessionStatusMap: nextSessionStatus,
        sessionErrorMap: nextSessionErrors,
        statusMap: { ...s.statusMap, [activeExpert]: "idle" },
        errorMap: { ...s.errorMap, [activeExpert]: null },
        status: "idle",
        error: null,
      };
    });
  },

  reset: () => {
    // 中止所有专家的请求
    for (const ac of _abortMap.values()) ac.abort();
    _abortMap.clear();
    _streamSessionMap.clear();
    set({
      chatHistories: { ...EMPTY_HISTORY },
      activeSessions: { ...EMPTY_ACTIVE },
      pendingClarifications: { ...EMPTY_PENDING },
      sessionHistories: { ...EMPTY_SESSION_HISTORIES },
      sessionPendingClarifications: { ...EMPTY_SESSION_PENDING },
      sessionStatusMap: { ...EMPTY_SESSION_STATUS },
      sessionErrorMap: { ...EMPTY_SESSION_ERRORS },
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
            sessionHistories: { ...s.sessionHistories, [session.id]: [] },
            sessionPendingClarifications: {
              ...s.sessionPendingClarifications,
              [session.id]: null,
            },
            sessionStatusMap: { ...s.sessionStatusMap, [session.id]: "idle" },
            sessionErrorMap: { ...s.sessionErrorMap, [session.id]: null },
            ...(s.activeExpert === type ? { status: "idle" as ExpertStatus, error: null } : {}),
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
      ...buildVisibleSessionState({
        expertType: activeExpert,
        sessionId,
        activeExpert: s.activeExpert,
        chatHistories: s.chatHistories,
        pendingClarifications: s.pendingClarifications,
        sessionHistories: s.sessionHistories,
        sessionPendingClarifications: s.sessionPendingClarifications,
        sessionStatusMap: s.sessionStatusMap,
        sessionErrorMap: s.sessionErrorMap,
      }),
    }));

    const currentState = get();
    const hasCachedHistory = (currentState.sessionHistories[sessionId]?.length ?? 0) > 0;
    const hasCachedPending = !!currentState.sessionPendingClarifications[sessionId];
    const isStreamingSession = _streamSessionMap.get(activeExpert) === sessionId;
    if (hasCachedHistory || hasCachedPending || isStreamingSession) {
      return;
    }

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
          interruption_reason?: ExpertMessage["interruptionReason"];
          interruption_detail?: string;
          last_stream_event_at?: string | null;
        }> = await res.json();
        const expertMessages: ExpertMessage[] = messages.map((m) => ({
          id: m.id,
          dbMessageId: m.id,
          role: m.role as "user" | "expert",
          content: m.content,
          status: (m.role === "expert" ? (m.status as "completed" | "partial") || "completed" : undefined),
          interruptionReason: m.interruption_reason,
          interruptionDetail: m.interruption_detail,
          lastStreamEventAt: m.last_stream_event_at,
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
            sessionHistories: {
              ...s.sessionHistories,
              [sessionId]: expertMessages,
            },
            ...buildVisibleSessionState({
              expertType: activeExpert,
              sessionId,
              activeExpert: s.activeExpert,
              chatHistories: s.chatHistories,
              pendingClarifications: s.pendingClarifications,
              sessionHistories: {
                ...s.sessionHistories,
                [sessionId]: expertMessages,
              },
              sessionPendingClarifications: s.sessionPendingClarifications,
              sessionStatusMap: s.sessionStatusMap,
              sessionErrorMap: s.sessionErrorMap,
            }),
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
      const ac = _abortMap.get(sessionId);
      if (ac) {
        ac.abort();
        _abortMap.delete(sessionId);
      }
      if (_streamSessionMap.get(activeExpert) === sessionId) {
        _streamSessionMap.delete(activeExpert);
      }
      set((s) => {
        const filtered = (s.sessions[activeExpert] || []).filter(
          (sess) => sess.id !== sessionId
        );
        const nextSessionHistories = { ...s.sessionHistories };
        const nextSessionPending = { ...s.sessionPendingClarifications };
        const nextSessionStatus = { ...s.sessionStatusMap };
        const nextSessionErrors = { ...s.sessionErrorMap };
        delete nextSessionHistories[sessionId];
        delete nextSessionPending[sessionId];
        delete nextSessionStatus[sessionId];
        delete nextSessionErrors[sessionId];
        const newState: Partial<ExpertStore> = {
          sessions: { ...s.sessions, [activeExpert]: filtered },
          sessionHistories: nextSessionHistories,
          sessionPendingClarifications: nextSessionPending,
          sessionStatusMap: nextSessionStatus,
          sessionErrorMap: nextSessionErrors,
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
          newState.status = "idle";
          newState.error = null;
        }
        return newState;
      });
    } catch {
      // ignore
    }
  },

  stopStreaming: async () => {
    const { activeExpert, activeSessions, chatHistories } = get();
    const sessionId = activeSessions[activeExpert];
    if (!sessionId) return;

    const ac = _abortMap.get(sessionId);
    if (!ac) return;

    const streamingMessage = [...(chatHistories[activeExpert] ?? [])]
      .reverse()
      .find((message) => message.role === "expert" && message.isStreaming);

    await reportCancelThenAbort({
      reportCancel: async () => {
        await apiFetch(`${getApiBase()}/api/v1/expert/chat/cancel`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            expert_type: activeExpert,
            message_id: streamingMessage?.dbMessageId ?? undefined,
            reason: "user_cancelled",
          }),
        }).catch(() => null);
      },
      abort: () => {
        ac.abort();
        _abortMap.delete(sessionId);
      },
    });

    set((s) => {
      const updated = updateSessionHistory({
        expertType: activeExpert,
        sessionId,
        activeSessions: s.activeSessions,
        chatHistories: s.chatHistories,
        sessionHistories: s.sessionHistories,
        updater: (history) => {
          const nextHistory = [...history];
          const idx = nextHistory.findLastIndex((message) => message.role === "expert" && message.isStreaming);
          if (idx !== -1) {
            nextHistory[idx] = {
              ...nextHistory[idx],
              isStreaming: false,
              content: nextHistory[idx].content || "（已停止生成）",
              interruptionReason: "user_cancelled",
            };
          }
          return nextHistory;
        },
      });
      return {
        ...updated,
        sessionStatusMap: { ...s.sessionStatusMap, [sessionId]: "idle" },
        statusMap: { ...s.statusMap, [activeExpert]: "idle" },
        ...(s.activeExpert === activeExpert && s.activeSessions[activeExpert] === sessionId
          ? { status: "idle" as ExpertStatus }
          : {}),
      };
    });
  },

  retryMessage: async (messageId: string) => {
    const { activeExpert, chatHistories, activeSessions } = get();
    const history = chatHistories[activeExpert] ?? [];
    const failedMsg = history.find((m) => m.id === messageId);
    if (!failedMsg || failedMsg.role !== "user" || failedMsg.sendStatus !== "failed") return;
    const sessionId = activeSessions[activeExpert];

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
      ...(sessionId
        ? {
            sessionHistories: {
              ...s.sessionHistories,
              [sessionId]: newHistory,
            },
          }
        : {}),
    }));
    // 重新发送
    await get().sendMessage(failedMsg.content, failedMsg.images);
  },

  sendMessage: async (text: string, images?: string[]) => {
    const { activeExpert, activeSessions, pendingClarifications, deepThink, useClarification, useTradePlan } = get();
    const expertType = activeExpert; // 闭包捕获，防止中途切走后写错专家
    if (pendingClarifications[expertType]) return;
    const msgImages = images && images.length > 0 ? images : undefined;

    // 如果该专家已有进行中的请求，先中止（同一专家不并发）
    const existingSessionId = _streamSessionMap.get(expertType);
    if (existingSessionId) {
      const existingAc = _abortMap.get(existingSessionId);
      if (existingAc) {
        existingAc.abort();
        _abortMap.delete(existingSessionId);
      }
      _streamSessionMap.delete(expertType);
    }

    // 自动创建 session（如果没有）
    let sessionId = activeSessions[expertType];
    if (!sessionId) {
      sessionId = await get().createSession(expertType);
    }

    const shouldClarify = useClarification && CLARIFICATION_EXPERTS.has(expertType);
    setExpertStatus(set, expertType, sessionId, shouldClarify ? "clarifying" : "thinking");

    const userMsg: ExpertMessage = {
      id: newId(),
      role: "user",
      content: text,
      thinking: [],
      isStreaming: false,
      sendStatus: "pending",
      images: msgImages,
    };
    const expertMsg: ExpertMessage = {
      id: newId(),
      role: "expert",
      content: "",
      thinking: [],
      isStreaming: true,  // 始终显示 loading 动画（clarify 返回后会关闭）
    };

    set((s) => {
      if (!sessionId) {
        return {
          chatHistories: {
            ...s.chatHistories,
            [expertType]: [
              ...(s.chatHistories[expertType] ?? []),
              userMsg,
              expertMsg,
            ],
          },
        };
      }
      const nextHistory = [
        ...(s.sessionHistories[sessionId] ?? []),
        userMsg,
        expertMsg,
      ];
      return {
        sessionHistories: {
          ...s.sessionHistories,
          [sessionId]: nextHistory,
        },
        chatHistories: {
          ...s.chatHistories,
          [expertType]: nextHistory,
        },
        sessionPendingClarifications: {
          ...s.sessionPendingClarifications,
          [sessionId]: null,
        },
        sessionErrorMap: {
          ...s.sessionErrorMap,
          [sessionId]: null,
        },
      };
    });

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
      if (!sessionId) {
        const history = [...(s.chatHistories[expertType] ?? [])];
        const idx = history.findIndex((m) => m.id === userMsg.id);
        if (idx !== -1) {
          history[idx] = { ...history[idx], sendStatus: "sent" };
        }
        return { chatHistories: { ...s.chatHistories, [expertType]: history } };
      }
      return updateSessionHistory({
        expertType,
        sessionId,
        activeSessions: s.activeSessions,
        chatHistories: s.chatHistories,
        sessionHistories: s.sessionHistories,
        updater: (history) => history.map((message) =>
          message.id === userMsg.id
            ? { ...message, sendStatus: "sent" }
            : message,
        ),
      });
    });
    if (shouldClarify) {
      try {
        const res = await apiFetch(`${getApiBase()}/api/v1/expert/clarify/${expertType}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: text,
            images: msgImages || [],
            session_id: sessionId,
            previous_selections: [],
          }),
        });
        const data = await res.json() as ClarificationRequestData;
        const currentRound = data.round ?? 1;

        if (shouldAutoAdvanceClarification(data)) {
          setExpertStatus(set, expertType, sessionId, "thinking");
          await streamExpertReply({
            expertType,
            expertMessageId: expertMsg.id,
            sessionId,
            userMessageId: userMsg.id,
            payload: {
              message: text,
              images: msgImages || [],
              session_id: sessionId,
              deep_think: deepThink,
              use_clarification: useClarification,
              enable_trade_plan: useTradePlan,
            },
            set,
            get,
          });
          return;
        }

        set((s) => {
          if (!sessionId) {
            return s;
          }
          const updated = updateSessionHistory({
            expertType,
            sessionId,
            activeSessions: s.activeSessions,
            chatHistories: s.chatHistories,
            sessionHistories: s.sessionHistories,
            updater: (history) => history.map((message) =>
              message.id === expertMsg.id
                ? {
                    ...message,
                    thinking: [
                      {
                        type: "clarification_request" as const,
                        data,
                        status: "pending" as const,
                        round: currentRound,
                      },
                    ],
                    isStreaming: false,
                  }
                : message,
            ),
          });
          const nextPending = {
            sessionId,
            userMessageId: userMsg.id,
            expertMessageId: expertMsg.id,
            request: data,
            originalMessage: text,
            originalImages: msgImages || [],
            previousSelections: [],
          };
          return {
            ...updated,
            sessionPendingClarifications: {
              ...s.sessionPendingClarifications,
              [sessionId]: nextPending,
            },
            pendingClarifications: {
              ...s.pendingClarifications,
              [expertType]: s.activeSessions[expertType] === sessionId ? nextPending : s.pendingClarifications[expertType],
            },
          };
        });
        setExpertStatus(set, expertType, sessionId, "idle");
        return;
      } catch (e: unknown) {
        const errMsg = (e as Error).message;
        set((s) => {
          if (!sessionId) {
            return s;
          }
          const updated = updateSessionHistory({
            expertType,
            sessionId,
            activeSessions: s.activeSessions,
            chatHistories: s.chatHistories,
            sessionHistories: s.sessionHistories,
            updater: (history) => history.map((message) => {
              if (message.id === userMsg.id) {
                return { ...message, sendStatus: "failed" };
              }
              if (message.id === expertMsg.id) {
                return {
                  ...message,
                  content: `澄清阶段失败: ${errMsg}`,
                  isStreaming: false,
                  interruptionReason: "server_error",
                  interruptionDetail: errMsg,
                };
              }
              return message;
            }),
          });
          return {
            ...updated,
          };
        });
        setExpertStatus(set, expertType, sessionId, "error", errMsg);
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
        images: msgImages || [],
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
    const sessionId = pending.sessionId;
    if (!sessionId) return;

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
      return updateSessionHistory({
        expertType,
        sessionId,
        activeSessions: s.activeSessions,
        chatHistories: s.chatHistories,
        sessionHistories: s.sessionHistories,
        updater: (history) => history.map((message) =>
          message.id === pending.expertMessageId
            ? {
                ...message,
                thinking: message.thinking.map((item) =>
                  item.type === "clarification_request" && item.status === "pending"
                    ? {
                        ...item,
                        status: allSkip ? "skipped" as const : "selected" as const,
                        selectedOption: firstSel,
                        selectedOptions: selections,
                      }
                    : item,
                ),
              }
            : message,
        ),
      });
    });

    // 如果用户选了 skip，或者后端说不需要继续 (needs_more=false)，直接进入 chat
    const needsMore = pending.request.needs_more !== false; // 默认 true（安全）
    if (allSkip || !needsMore) {
      // 清除 pending，进入 chat
      set((s) => ({
        pendingClarifications: { ...s.pendingClarifications, [expertType]: null },
        sessionPendingClarifications: {
          ...s.sessionPendingClarifications,
          [sessionId]: null,
        },
      }));
      setExpertStatus(set, expertType, sessionId, "thinking");

      // 设置 streaming 状态
      set((s) => {
        return updateSessionHistory({
          expertType,
          sessionId,
          activeSessions: s.activeSessions,
          chatHistories: s.chatHistories,
          sessionHistories: s.sessionHistories,
          updater: (history) => history.map((message) =>
            message.id === pending.expertMessageId
              ? { ...message, isStreaming: true }
              : message,
          ),
        });
      });

      await streamExpertReply({
        expertType,
        expertMessageId: pending.expertMessageId,
        sessionId,
        payload: {
          message: pending.originalMessage,
          images: pending.originalImages || [],
          session_id: sessionId,
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
    setExpertStatus(set, expertType, sessionId, "clarifying");
    // 显示 loading 动画等待下一轮选项
    set((s) => {
      return updateSessionHistory({
        expertType,
        sessionId,
        activeSessions: s.activeSessions,
        chatHistories: s.chatHistories,
        sessionHistories: s.sessionHistories,
        updater: (history) => history.map((message) =>
          message.id === pending.expertMessageId
            ? { ...message, isStreaming: true }
            : message,
        ),
      });
    });
    try {
      const res = await fetch(`${getApiBase()}/api/v1/expert/clarify/${expertType}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: pending.originalMessage,
          images: pending.originalImages || [],
          session_id: sessionId,
          previous_selections: allRoundSelections,
        }),
      });
      const nextData = await res.json() as ClarificationRequestData;
      const nextRound = nextData.round ?? (currentRound + 1);

      // 只有后端明确说无需澄清时才自动进入 chat。
      // should_clarify=true 但 options 为空时，前端保持在澄清态，等待用户手动处理/反馈。
      if (shouldAutoAdvanceClarification(nextData)) {
        set((s) => ({
          pendingClarifications: { ...s.pendingClarifications, [expertType]: null },
          sessionPendingClarifications: {
            ...s.sessionPendingClarifications,
            [sessionId]: null,
          },
        }));
        setExpertStatus(set, expertType, sessionId, "thinking");

        set((s) => {
          return updateSessionHistory({
            expertType,
            sessionId,
            activeSessions: s.activeSessions,
            chatHistories: s.chatHistories,
            sessionHistories: s.sessionHistories,
            updater: (history) => history.map((message) =>
              message.id === pending.expertMessageId
                ? { ...message, isStreaming: true }
                : message,
            ),
          });
        });

        await streamExpertReply({
          expertType,
          expertMessageId: pending.expertMessageId,
          sessionId,
          payload: {
            message: pending.originalMessage,
            images: pending.originalImages || [],
            session_id: sessionId,
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
        const updated = updateSessionHistory({
          expertType,
          sessionId,
          activeSessions: s.activeSessions,
          chatHistories: s.chatHistories,
          sessionHistories: s.sessionHistories,
          updater: (history) => history.map((message) =>
            message.id === pending.expertMessageId
              ? {
                  ...message,
                  thinking: [
                    ...message.thinking,
                    {
                      type: "clarification_request" as const,
                      data: nextData,
                      status: "pending" as const,
                      round: nextRound,
                    },
                  ],
                  isStreaming: false,
                }
              : message,
          ),
        });
        const nextPending = {
          sessionId,
          userMessageId: pending.userMessageId,
          expertMessageId: pending.expertMessageId,
          request: nextData,
          originalMessage: pending.originalMessage,
          originalImages: pending.originalImages || [],
          previousSelections: allRoundSelections,
        };
        return {
          ...updated,
          sessionPendingClarifications: {
            ...s.sessionPendingClarifications,
            [sessionId]: nextPending,
          },
          pendingClarifications: {
            ...s.pendingClarifications,
            [expertType]: s.activeSessions[expertType] === sessionId ? nextPending : s.pendingClarifications[expertType],
          },
        };
      });
      setExpertStatus(set, expertType, sessionId, "idle");
    } catch (e: unknown) {
      // 追问失败时降级：直接带已有选择进入 chat
      const errMsg = (e as Error).message;
      console.warn("多轮澄清追问失败，降级进入 chat:", errMsg);
      set((s) => ({
        pendingClarifications: { ...s.pendingClarifications, [expertType]: null },
        sessionPendingClarifications: {
          ...s.sessionPendingClarifications,
          [sessionId]: null,
        },
      }));
      setExpertStatus(set, expertType, sessionId, "thinking");

      set((s) => {
        return updateSessionHistory({
          expertType,
          sessionId,
          activeSessions: s.activeSessions,
          chatHistories: s.chatHistories,
          sessionHistories: s.sessionHistories,
          updater: (history) => history.map((message) =>
            message.id === pending.expertMessageId
              ? { ...message, isStreaming: true }
              : message,
          ),
        });
      });

      await streamExpertReply({
        expertType,
        expertMessageId: pending.expertMessageId,
        sessionId,
        payload: {
          message: pending.originalMessage,
          images: pending.originalImages || [],
          session_id: sessionId,
          deep_think: deepThink,
          clarification_chain: allRoundSelections,
          clarification_selection: firstSel,
        },
        set,
        get,
      });
    }
  },

  submitFeedback: async (messageId: string, options: ExpertFeedbackSubmitOptions) => {
    const { activeExpert, activeSessions, chatHistories, pendingClarifications, sessionStatusMap, sessionErrorMap } = get();
    const sessionId = activeSessions[activeExpert];
    if (!sessionId) return null;

    const history = chatHistories[activeExpert] ?? [];
    const messageIndex = history.findIndex((item) => item.id === messageId || item.dbMessageId === messageId);
    const currentMessage = messageIndex >= 0 ? history[messageIndex] : null;
    if (!currentMessage || currentMessage.role !== "expert") {
      throw new Error("未找到可反馈的 expert 消息");
    }
    let message = currentMessage;

    if (!message.dbMessageId) {
      const syncResponse = await apiFetch(`${getApiBase()}/api/v1/expert/sessions/${sessionId}/messages`);
      if (syncResponse.ok) {
        const serverMessages = await syncResponse.json() as Array<{
          id: string;
          role: "user" | "expert";
          content: string;
          status?: "completed" | "partial";
        }>;
        const matchedMessage = [...serverMessages].reverse().find(
          (item) =>
            item.role === "expert" &&
            item.content === message.content &&
            (item.status || "completed") === (message.status || "completed"),
        );
        if (matchedMessage?.id) {
          message = { ...message, dbMessageId: matchedMessage.id };
          set((s) => {
            return updateSessionHistory({
              expertType: activeExpert,
              sessionId,
              activeSessions: s.activeSessions,
              chatHistories: s.chatHistories,
              sessionHistories: s.sessionHistories,
              updater: (history) => history.map((item, index) =>
                index === messageIndex
                  ? { ...item, dbMessageId: matchedMessage.id }
                  : item,
              ),
            });
          });
        }
      }
    }
    if (!message.dbMessageId) {
      throw new Error("消息尚未落库，请稍后再试");
    }

    const payload = buildExpertFeedbackPayload({
      sessionId,
      expertType: activeExpert,
      issueType: options.issueType,
      userNote: options.userNote,
      reportSource: options.reportSource,
      message,
      history,
      pendingClarification: pendingClarifications[activeExpert],
      expertStatus: sessionStatusMap[sessionId] ?? "idle",
      error: sessionErrorMap[sessionId] ?? null,
    });

    const response = await apiFetch(`${getApiBase()}/api/v1/expert/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.detail || `反馈提交失败 (${response.status})`);
    }

    const data = await response.json() as ExpertFeedbackSubmitResponse;
    if (options.checkResumeAfterSubmit) {
      await get().resumeReply(messageId, {
        checkCompleted: message.status === "completed",
      });
    }
    return data;
  },

  listAdminFeedbackReports: async (unresolvedOnly = true, limit = 50) => {
    const params = new URLSearchParams({
      unresolved_only: unresolvedOnly ? "true" : "false",
      limit: String(limit),
    });
    const response = await apiFetch(`${getApiBase()}/api/v1/expert/feedback/admin?${params.toString()}`);
    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.detail || `反馈列表加载失败 (${response.status})`);
    }
    return await response.json() as ExpertFeedbackSummary[];
  },

  getAdminFeedbackReport: async (feedbackId: string) => {
    const response = await apiFetch(`${getApiBase()}/api/v1/expert/feedback/admin/${feedbackId}`);
    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.detail || `反馈详情加载失败 (${response.status})`);
    }
    return await response.json() as ExpertFeedbackDetail;
  },

  resolveAdminFeedbackReport: async (feedbackId: string, resolutionNote = "") => {
    const response = await apiFetch(`${getApiBase()}/api/v1/expert/feedback/admin/${feedbackId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resolution_note: resolutionNote }),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.detail || `反馈处理失败 (${response.status})`);
    }
    const data = await response.json() as ExpertFeedbackResolveResponse;
    return data.ok === true;
  },

  resumeReply: async (messageId: string, options?: { checkCompleted?: boolean }) => {
    const { activeExpert, activeSessions } = get();
    const expertType = activeExpert;
    const sessionId = activeSessions[expertType];
    if (!sessionId) return;
    const checkCompleted = options?.checkCompleted ?? false;

    // 找到这条 partial 消息
    const history = get().chatHistories[expertType] ?? [];
    const msgIdx = history.findIndex((m) => m.id === messageId || m.dbMessageId === messageId);
    if (msgIdx === -1) return;
    const msg = history[msgIdx];
    if (msg.role !== "expert") return;
    if (msg.status !== "partial" && !(checkCompleted && msg.status === "completed")) return;

    const dbMsgId = msg.dbMessageId;
    if (!dbMsgId) return;

    // 设置为 streaming 状态
    setExpertStatus(set, expertType, sessionId, "thinking");
    set((s) => updateSessionHistory({
      expertType,
      sessionId,
      activeSessions: s.activeSessions,
      chatHistories: s.chatHistories,
      sessionHistories: s.sessionHistories,
      updater: (history) => history.map((message, index) =>
        index === msgIdx
          ? { ...message, isStreaming: true }
          : message,
      ),
    }));

    const ac = new AbortController();
    _abortMap.set(sessionId, ac);
    _streamSessionMap.set(expertType, sessionId);

    const applyHistoryUpdate = (updater: (history: ExpertMessage[]) => ExpertMessage[]) => {
      set((s) => updateSessionHistory({
        expertType,
        sessionId,
        activeSessions: s.activeSessions,
        chatHistories: s.chatHistories,
        sessionHistories: s.sessionHistories,
        updater,
      }));
    };

    try {
      const res = await fetch(`${getSseBase()}/api/v1/expert/chat/resume`, {
        method: "POST",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message_id: dbMsgId,
          check_completed: checkCompleted,
        }),
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
              applyHistoryUpdate((history) => history.map((message) =>
                message.id === messageId || message.dbMessageId === messageId
                  ? {
                      ...message,
                      content: message.content + ((data.token as string) ?? ""),
                    }
                  : message,
              ));
            } else if (eventType === "resume_complete") {
              // 续写完成
              applyHistoryUpdate((history) => history.map((message) =>
                message.id === messageId || message.dbMessageId === messageId
                  ? {
                      ...message,
                      isStreaming: false,
                      status: "completed",
                      interruptionReason: undefined,
                      interruptionDetail: undefined,
                    }
                  : message,
              ));
            } else if (eventType === "error") {
              applyHistoryUpdate((history) => history.map((message) =>
                message.id === messageId || message.dbMessageId === messageId
                  ? { ...message, isStreaming: false }
                  : message,
              ));
            }
          }
        }
      }

      // 流结束后确保 isStreaming=false
      applyHistoryUpdate((history) => history.map((message) =>
        (message.id === messageId || message.dbMessageId === messageId) && message.isStreaming
          ? { ...message, isStreaming: false, status: "completed" }
          : message,
      ));
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") {
        applyHistoryUpdate((history) => history.map((message) =>
          message.id === messageId || message.dbMessageId === messageId
            ? {
                ...message,
                isStreaming: false,
                interruptionReason: "user_cancelled",
              }
            : message,
        ));
        return;
      }
      console.error("resumeReply error:", (e as Error).message);
      const errMsg = (e as Error).message;
      applyHistoryUpdate((history) => history.map((message) =>
        message.id === messageId || message.dbMessageId === messageId
          ? {
              ...message,
              isStreaming: false,
              interruptionReason: "server_error",
              interruptionDetail: errMsg,
            }
          : message,
      ));
      setExpertStatus(set, expertType, sessionId, "error", errMsg);
    } finally {
      _abortMap.delete(sessionId);
      if (_streamSessionMap.get(expertType) === sessionId) {
        _streamSessionMap.delete(expertType);
      }
      set((s) => {
        if (s.sessionStatusMap[sessionId] !== "error") {
          const newStatusMap = { ...s.statusMap, [expertType]: "idle" as ExpertStatus };
          const newSessionStatusMap = { ...s.sessionStatusMap, [sessionId]: "idle" as ExpertStatus };
          return {
            statusMap: newStatusMap,
            sessionStatusMap: newSessionStatusMap,
            ...(s.activeExpert === expertType && s.activeSessions[expertType] === sessionId
              ? { status: "idle" as ExpertStatus }
              : {}),
          };
        }
        return s;
      });
    }
  },
}));
