import test from "node:test";
import assert from "node:assert/strict";

import { inspectSseResponse } from "./sseResponse.ts";

test("inspectSseResponse keeps SSE responses in stream mode", async () => {
  const res = new Response("event: ping\ndata: {}\n\n", {
    status: 200,
    headers: { "Content-Type": "text/event-stream; charset=utf-8" },
  });

  const result = await inspectSseResponse(res);

  assert.deepEqual(result, { ok: true });
});

test("inspectSseResponse surfaces JSON error payloads returned with HTTP 200", async () => {
  const res = new Response(JSON.stringify({ error: "LLM 未配置" }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

  const result = await inspectSseResponse(res);

  assert.deepEqual(result, { ok: false, error: "LLM 未配置" });
});

test("inspectSseResponse falls back to HTTP status when body has no structured error", async () => {
  const res = new Response("upstream unavailable", {
    status: 502,
    headers: { "Content-Type": "text/plain" },
  });

  const result = await inspectSseResponse(res);

  assert.deepEqual(result, { ok: false, error: "HTTP 502" });
});
