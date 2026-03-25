import test from "node:test";
import assert from "node:assert/strict";

import {
  formatRuntimeIssues,
  isBadHttpStatus,
  shouldIgnoreConsoleErrorText,
  shouldIgnoreFailedRequestUrl,
  type RuntimeIssue,
} from "./runtimeIssues.ts";

test("shouldIgnoreConsoleErrorText ignores known low-signal dev noise", () => {
  assert.equal(shouldIgnoreConsoleErrorText("Download the React DevTools"), true);
  assert.equal(shouldIgnoreConsoleErrorText("favicon.ico 404"), true);
  assert.equal(shouldIgnoreConsoleErrorText("Unhandled promise rejection"), false);
});

test("shouldIgnoreFailedRequestUrl ignores next dev transport noise only", () => {
  assert.equal(shouldIgnoreFailedRequestUrl("http://127.0.0.1:3000/_next/webpack-hmr"), true);
  assert.equal(shouldIgnoreFailedRequestUrl("http://127.0.0.1:3000/api/v1/agent/state"), false);
});

test("isBadHttpStatus only flags 4xx and 5xx responses", () => {
  assert.equal(isBadHttpStatus(200), false);
  assert.equal(isBadHttpStatus(302), false);
  assert.equal(isBadHttpStatus(404), true);
  assert.equal(isBadHttpStatus(500), true);
});

test("formatRuntimeIssues renders route-prefixed issue lines", () => {
  const issues: RuntimeIssue[] = [
    { source: "console", message: "boom" },
    { source: "requestfailed", message: "GET /api/v1/x" },
  ];

  assert.deepEqual(formatRuntimeIssues("/agent", issues), [
    "[/agent] [console] boom",
    "[/agent] [requestfailed] GET /api/v1/x",
  ]);
});
