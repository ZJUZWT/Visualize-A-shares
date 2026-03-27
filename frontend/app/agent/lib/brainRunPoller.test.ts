import test from "node:test";
import assert from "node:assert/strict";

import { startBrainRunPoller } from "./brainRunPoller.ts";
import type { BrainRun } from "../types.ts";

function makeRun(status: string): BrainRun {
  return {
    id: "run-1",
    portfolio_id: "live",
    run_type: "manual",
    status,
    current_step: status === "running" ? "deciding" : null,
    candidates: null,
    analysis_results: null,
    decisions: null,
    plan_ids: null,
    trade_ids: null,
    thinking_process: null,
    state_before: null,
    state_after: null,
    execution_summary: null,
    error_message: null,
    llm_tokens_used: 0,
    started_at: "2026-03-26T23:00:00",
    completed_at: status === "running" ? null : "2026-03-26T23:01:00",
  };
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

test("startBrainRunPoller waits for each request to finish before polling again", async () => {
  let callCount = 0;
  let concurrent = 0;
  let maxConcurrent = 0;
  const seenStatuses: string[] = [];

  const poller = startBrainRunPoller({
    intervalMs: 5,
    requestTimeoutMs: 100,
    maxPollMs: 1_000,
    loadRun: async (_signal) => {
      concurrent += 1;
      maxConcurrent = Math.max(maxConcurrent, concurrent);
      callCount += 1;
      await delay(20);
      concurrent -= 1;
      return makeRun(callCount >= 3 ? "completed" : "running");
    },
    onUpdate: (run) => {
      seenStatuses.push(run.status);
    },
    onTerminal: (run) => {
      seenStatuses.push(`terminal:${run.status}`);
    },
  });

  await poller.done;

  assert.equal(maxConcurrent, 1);
  assert.equal(callCount, 3);
  assert.deepEqual(seenStatuses, [
    "running",
    "running",
    "completed",
    "terminal:completed",
  ]);
});

test("startBrainRunPoller stop prevents late in-flight responses from updating state", async () => {
  let resolveLoad: ((run: BrainRun) => void) | null = null;
  const seenStatuses: string[] = [];

  const poller = startBrainRunPoller({
    intervalMs: 5,
    requestTimeoutMs: 100,
    maxPollMs: 1_000,
    loadRun: (signal) =>
      new Promise<BrainRun>((resolve, reject) => {
        resolveLoad = resolve;
        signal.addEventListener(
          "abort",
          () => {
            reject(signal.reason ?? new Error("aborted"));
          },
          { once: true }
        );
      }),
    onUpdate: (run) => {
      seenStatuses.push(run.status);
    },
    onTerminal: (run) => {
      seenStatuses.push(`terminal:${run.status}`);
    },
  });

  await delay(0);
  poller.stop();
  resolveLoad?.(makeRun("completed"));
  await poller.done;

  assert.deepEqual(seenStatuses, []);
});

test("startBrainRunPoller aborts a stuck request after the per-attempt timeout", async () => {
  let abortCount = 0;
  let errorCount = 0;

  const poller = startBrainRunPoller({
    intervalMs: 1,
    requestTimeoutMs: 5,
    maxPollMs: 100,
    maxConsecutiveErrors: 2,
    loadRun: (signal) =>
      new Promise<BrainRun>((_resolve, reject) => {
        signal.addEventListener(
          "abort",
          () => {
            abortCount += 1;
            reject(signal.reason ?? new Error("aborted"));
          },
          { once: true }
        );
      }),
    onError: () => {
      errorCount += 1;
    },
  });

  await poller.done;

  assert.equal(abortCount, 2);
  assert.equal(errorCount, 1);
});
