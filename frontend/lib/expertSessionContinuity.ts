import type {
  ExpertMessage,
  ExpertStatus,
  ExpertType,
  PendingClarification,
} from "../types/expert.ts";

export type ExpertChatHistory = Record<ExpertType, ExpertMessage[]>;
export type ExpertPendingMap = Record<ExpertType, PendingClarification | null>;
export type ActiveSessions = Record<ExpertType, string | null>;
export type SessionHistories = Record<string, ExpertMessage[]>;
export type SessionPendingMap = Record<string, PendingClarification | null>;
export type SessionStatusMap = Record<string, ExpertStatus>;
export type SessionErrorMap = Record<string, string | null>;

interface UpdateSessionHistoryInput {
  expertType: ExpertType;
  sessionId: string;
  activeSessions: ActiveSessions;
  chatHistories: ExpertChatHistory;
  sessionHistories: SessionHistories;
  updater: (history: ExpertMessage[]) => ExpertMessage[];
}

export function updateSessionHistory(input: UpdateSessionHistoryInput) {
  const nextSessionHistory = input.updater(input.sessionHistories[input.sessionId] ?? []);
  const nextSessionHistories: SessionHistories = {
    ...input.sessionHistories,
    [input.sessionId]: nextSessionHistory,
  };

  const nextChatHistories =
    input.activeSessions[input.expertType] === input.sessionId
      ? { ...input.chatHistories, [input.expertType]: nextSessionHistory }
      : input.chatHistories;

  return {
    sessionHistories: nextSessionHistories,
    chatHistories: nextChatHistories,
  };
}

interface BuildVisibleSessionStateInput {
  expertType: ExpertType;
  sessionId: string | null;
  activeExpert: ExpertType;
  chatHistories: ExpertChatHistory;
  pendingClarifications: ExpertPendingMap;
  sessionHistories: SessionHistories;
  sessionPendingClarifications: SessionPendingMap;
  sessionStatusMap: SessionStatusMap;
  sessionErrorMap: SessionErrorMap;
}

export function buildVisibleSessionState(input: BuildVisibleSessionStateInput) {
  const nextHistory = input.sessionId
    ? input.sessionHistories[input.sessionId] ?? []
    : [];
  const nextPending = input.sessionId
    ? input.sessionPendingClarifications[input.sessionId] ?? null
    : null;
  const nextStatus = input.sessionId
    ? input.sessionStatusMap[input.sessionId] ?? "idle"
    : "idle";
  const nextError = input.sessionId
    ? input.sessionErrorMap[input.sessionId] ?? null
    : null;

  return {
    chatHistories: {
      ...input.chatHistories,
      [input.expertType]: nextHistory,
    },
    pendingClarifications: {
      ...input.pendingClarifications,
      [input.expertType]: nextPending,
    },
    ...(input.activeExpert === input.expertType
      ? { status: nextStatus, error: nextError }
      : {}),
  };
}

export function getVisibleSessionStatus(params: {
  sessionId: string | null;
  sessionStatusMap: SessionStatusMap;
}) {
  if (!params.sessionId) return "idle" as const;
  return params.sessionStatusMap[params.sessionId] ?? "idle";
}

export async function reportCancelThenAbort(options: {
  reportCancel: () => Promise<unknown>;
  abort: () => void;
}) {
  try {
    await options.reportCancel();
  } finally {
    options.abort();
  }
}
