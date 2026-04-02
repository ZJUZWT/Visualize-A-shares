import test from "node:test";
import assert from "node:assert/strict";

import {
  buildVisibleSessionState,
  reportCancelThenAbort,
  updateSessionHistory,
} from "./expertSessionContinuity.ts";
import type { ExpertMessage, PendingClarification } from "../types/expert.ts";

test("switching session for same expert keeps background stream bound to original session", () => {
  const sessionAMessage: ExpertMessage = {
    id: "expert-a",
    role: "expert",
    content: "原会话回复",
    thinking: [],
    isStreaming: true,
  };
  const sessionBMessage: ExpertMessage = {
    id: "expert-b",
    role: "expert",
    content: "目标会话历史",
    thinking: [],
    isStreaming: false,
  };

  const updated = updateSessionHistory({
    expertType: "data",
    sessionId: "session-a",
    activeSessions: {
      data: "session-b",
      quant: null,
      info: null,
      industry: null,
      rag: null,
      short_term: null,
    },
    chatHistories: {
      data: [sessionBMessage],
      quant: [],
      info: [],
      industry: [],
      rag: [],
      short_term: [],
    },
    sessionHistories: {
      "session-a": [sessionAMessage],
      "session-b": [sessionBMessage],
    },
    updater: (history) =>
      history.map((message) =>
        message.id === "expert-a"
          ? { ...message, content: `${message.content} + 新 token` }
          : message,
      ),
  });

  assert.equal(updated.chatHistories.data[0]?.content, "目标会话历史");
  assert.equal(updated.sessionHistories["session-a"][0]?.content, "原会话回复 + 新 token");
});

test("switching back to the source session restores cached stream state", () => {
  const pendingClarification: PendingClarification = {
    sessionId: "session-a",
    userMessageId: "user-a",
    expertMessageId: "expert-a",
    request: {
      should_clarify: true,
      question_summary: "你更想先看哪个角度？",
      options: [],
      reasoning: "先确认分析方向。",
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
      multi_select: false,
    },
    originalMessage: "帮我分析一下",
    previousSelections: [],
  };

  const next = buildVisibleSessionState({
    expertType: "data",
    sessionId: "session-a",
    activeExpert: "data",
    chatHistories: {
      data: [],
      quant: [],
      info: [],
      industry: [],
      rag: [],
      short_term: [],
    },
    pendingClarifications: {
      data: null,
      quant: null,
      info: null,
      industry: null,
      rag: null,
      short_term: null,
    },
    sessionHistories: {
      "session-a": [
        {
          id: "expert-a",
          role: "expert",
          content: "后台还在继续生成",
          thinking: [],
          isStreaming: true,
        },
      ],
    },
    sessionPendingClarifications: {
      "session-a": pendingClarification,
    },
    sessionStatusMap: {
      "session-a": "thinking",
    },
    sessionErrorMap: {},
  });

  assert.equal(next.chatHistories.data[0]?.content, "后台还在继续生成");
  assert.equal(next.pendingClarifications.data?.expertMessageId, "expert-a");
  assert.equal(next.status, "thinking");
});

test("stop streaming reports user_cancelled before abort", async () => {
  const steps: string[] = [];

  await reportCancelThenAbort({
    reportCancel: async () => {
      steps.push("report");
    },
    abort: () => {
      steps.push("abort");
    },
  });

  assert.deepEqual(steps, ["report", "abort"]);
});
