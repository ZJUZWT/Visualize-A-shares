import type {
  ExpertFeedbackCreatePayload,
  ExpertFeedbackIssueType,
  ExpertFeedbackSource,
  ExpertMessage,
  ExpertStatus,
  ExpertType,
  PendingClarification,
} from "../types/expert.ts";

export const FEEDBACK_ISSUE_LABELS: Record<ExpertFeedbackIssueType, string> = {
  load_failed: "加载失败",
  llm_truncated: "回复疑似截断",
  resume_misjudged_complete: "误判已完整",
  clarify_missing_options: "问句没有选项",
  clarify_auto_advance: "选一个就自动下一步",
  clarify_subchoice_stuck: "子选项无法取消",
  other: "其他问题",
};

export function deriveFeedbackSource(issueType: ExpertFeedbackIssueType): ExpertFeedbackSource {
  if (issueType.startsWith("clarify_")) {
    return "clarification";
  }
  if (issueType === "resume_misjudged_complete") {
    return "resume";
  }
  return "reply";
}

function serializeMessage(message: ExpertMessage) {
  return {
    id: message.id,
    db_message_id: message.dbMessageId,
    role: message.role,
    content: message.content,
    status: message.status,
    interruption_reason: message.interruptionReason,
    interruption_detail: message.interruptionDetail,
    send_status: message.sendStatus,
    is_streaming: message.isStreaming,
    thinking: message.thinking,
  };
}

export function defaultFeedbackIssueTypeForMessage(
  message: ExpertMessage,
): ExpertFeedbackIssueType {
  if (message.interruptionReason === "provider_error" || message.interruptionReason === "server_error") {
    return "load_failed";
  }
  if (
    message.interruptionReason === "client_disconnected"
    || message.interruptionReason === "resume_interrupted"
    || message.interruptionReason === "unknown_interrupted"
    || message.interruptionReason === "user_cancelled"
    || message.status === "partial"
  ) {
    return "llm_truncated";
  }
  return "other";
}

function findPreviousUserMessage(message: ExpertMessage, history: ExpertMessage[]) {
  const targetIndex = history.findIndex(
    (item) => item.id === message.id || item.dbMessageId === message.dbMessageId,
  );
  const searchRange = targetIndex >= 0 ? history.slice(0, targetIndex + 1) : history;
  for (let idx = searchRange.length - 1; idx >= 0; idx -= 1) {
    const item = searchRange[idx];
    if (item.role === "user") {
      return {
        id: item.dbMessageId || item.id,
        content: item.content,
      };
    }
  }
  return null;
}

export function shouldOfferResumeCheck(issueType: ExpertFeedbackIssueType, message: ExpertMessage): boolean {
  if (!message.dbMessageId) return false;
  if (issueType === "resume_misjudged_complete") return true;
  if (issueType === "load_failed" || issueType === "llm_truncated") {
    return message.status === "partial" || message.status === "completed";
  }
  return false;
}

interface BuildExpertFeedbackPayloadInput {
  sessionId: string;
  expertType: ExpertType;
  issueType: ExpertFeedbackIssueType;
  userNote?: string;
  message: ExpertMessage;
  history: ExpertMessage[];
  pendingClarification: PendingClarification | null;
  expertStatus: ExpertStatus;
  error: string | null;
  reportSource?: ExpertFeedbackSource;
}

export function buildExpertFeedbackPayload(
  input: BuildExpertFeedbackPayloadInput,
): ExpertFeedbackCreatePayload {
  const reportSource = input.reportSource ?? deriveFeedbackSource(input.issueType);
  return {
    session_id: input.sessionId,
    message_id: input.message.dbMessageId || input.message.id,
    expert_type: input.expertType,
    report_source: reportSource,
    issue_type: input.issueType,
    user_note: input.userNote?.trim() ?? "",
    context: {
      message: serializeMessage(input.message),
      previous_user_message: findPreviousUserMessage(input.message, input.history),
      history: input.history.map(serializeMessage),
      pending_clarification: input.pendingClarification,
      expert_status: input.expertStatus,
      latest_error: input.error,
    },
  };
}
