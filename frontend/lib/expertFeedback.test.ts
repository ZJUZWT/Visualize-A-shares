import test from "node:test";
import assert from "node:assert/strict";

import { buildExpertFeedbackPayload } from "./expertFeedback.ts";
import type { ExpertMessage, PendingClarification } from "../types/expert.ts";

test("builds expert feedback payload with full message context", () => {
  const history: ExpertMessage[] = [
    {
      id: "u-1",
      role: "user",
      content: "帮我看看这段回复是不是没写完",
      thinking: [],
      isStreaming: false,
      sendStatus: "sent",
    },
    {
      id: "e-1",
      dbMessageId: "db-e-1",
      role: "expert",
      content: "结论：当前估值合理，但后续要重点观察",
      thinking: [
        {
          type: "reasoning_summary",
          data: { summary: "先看估值，再看业绩兑现节奏" },
        },
      ],
      isStreaming: false,
      status: "partial",
    },
  ];

  const pendingClarification: PendingClarification = {
    sessionId: "session-1",
    userMessageId: "u-1",
    expertMessageId: "e-1",
    request: {
      should_clarify: true,
      question_summary: "你更想先确认哪个方向？",
      options: [],
      reasoning: "先聚焦分析角度",
      skip_option: {
        id: "skip",
        label: "S",
        title: "跳过，直接分析",
        description: "直接进入完整分析。",
        focus: "完整分析",
      },
      needs_more: true,
      round: 1,
      max_rounds: 3,
      multi_select: true,
    },
    originalMessage: "继续看看这只票",
    previousSelections: [],
  };

  const payload = buildExpertFeedbackPayload({
    sessionId: "session-1",
    expertType: "rag",
    issueType: "llm_truncated",
    userNote: "load failed 之后看起来像是被截断了",
    message: history[1],
    history,
    pendingClarification,
    expertStatus: "error",
    error: "load failed",
  });

  assert.equal(payload.issue_type, "llm_truncated");
  assert.equal(payload.report_source, "reply");
  assert.equal(payload.message_id, "db-e-1");
  assert.equal(payload.context.history.length, 2);
  assert.equal(payload.context.previous_user_message?.content, "帮我看看这段回复是不是没写完");
  assert.equal(payload.context.message.status, "partial");
  assert.equal(payload.context.pending_clarification?.originalMessage, "继续看看这只票");
  assert.equal(payload.context.latest_error, "load failed");
});
