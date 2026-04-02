import test from "node:test";
import assert from "node:assert/strict";

import {
  ACTIVE_AGENT_PORTFOLIO_STORAGE_KEY,
  ACTIVE_AGENT_PORTFOLIO_UPDATED_EVENT,
  pickExpertLearningPortfolio,
  readRememberedAgentPortfolio,
  rememberActiveAgentPortfolio,
} from "./activePortfolio.ts";

function installLocalStorageMock() {
  const store = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
      removeItem: (key: string) => {
        store.delete(key);
      },
    },
    configurable: true,
  });
}

test("pickExpertLearningPortfolio prefers remembered portfolio", () => {
  assert.equal(
    pickExpertLearningPortfolio(
      [{ id: "paper-1" }, { id: "paper-2" }],
      "paper-2",
      null,
    ),
    "paper-2",
  );
  assert.equal(
    pickExpertLearningPortfolio(
      [{ id: "paper-1" }, { id: "paper-2" }],
      "missing",
      "paper-1",
    ),
    "paper-1",
  );
});

test("remembered portfolio helpers round-trip through localStorage", () => {
  installLocalStorageMock();

  rememberActiveAgentPortfolio("paper-9");
  assert.equal(localStorage.getItem(ACTIVE_AGENT_PORTFOLIO_STORAGE_KEY), "paper-9");
  assert.equal(readRememberedAgentPortfolio(), "paper-9");

  rememberActiveAgentPortfolio(null);
  assert.equal(readRememberedAgentPortfolio(), null);
});

test("rememberActiveAgentPortfolio emits update event for same-tab sync", () => {
  installLocalStorageMock();

  const events: Event[] = [];
  Object.defineProperty(globalThis, "dispatchEvent", {
    value: (event: Event) => {
      events.push(event);
      return true;
    },
    configurable: true,
  });

  rememberActiveAgentPortfolio("paper-3");

  assert.equal(events.length, 1);
  assert.equal(events[0]?.type, ACTIVE_AGENT_PORTFOLIO_UPDATED_EVENT);
});
