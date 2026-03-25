# Frontend Console Smoke Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a minimal Playwright-based smoke layer for the main frontend routes that fails on browser console errors and uncaught page exceptions.

**Architecture:** Keep the smoke suite narrow and deterministic. Route all `/api/**` traffic to lightweight mocks so the checks validate frontend runtime stability rather than backend availability.

**Tech Stack:** Next.js 15, TypeScript, Playwright, Node/npm

---

### Task 1: Add test entrypoints and dependency plumbing

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/playwright.config.ts`

**Step 1: Write the failing test hook**

Define a new `test:smoke` script and a Playwright config pointing at `tests/smoke`.

**Step 2: Run test to verify it fails**

Run: `npm run test:smoke`
Expected: fail because smoke spec files do not exist yet or Playwright is not configured.

**Step 3: Write minimal implementation**

Add:

- `test:smoke`
- `test:smoke:headed` optional variant
- Playwright config with `webServer` for `next dev --port 3000`

**Step 4: Run test to verify config is picked up**

Run: `npm run test:smoke -- --list`
Expected: Playwright discovers smoke files or reports none found from the configured directory.

### Task 2: Add shared smoke helpers with API mocks

**Files:**
- Create: `frontend/tests/smoke/support/smokeHarness.ts`

**Step 1: Write the failing test**

Create helper API expected by route tests:

- install error listeners
- register `/api/**` mocks
- expose assertion helper for collected errors

**Step 2: Run test to verify it fails**

Run: `npm run test:smoke -- --grep root`
Expected: import/helper missing.

**Step 3: Write minimal implementation**

Implement:

- `attachPageErrorCollectors(page)`
- `mockApi(page)`
- `assertNoRuntimeErrors(errors)`

Use minimal mock payloads only for the known frontend routes.

**Step 4: Run test to verify helper compiles**

Run: `npm run test:smoke -- --list`
Expected: no helper import/type errors.

### Task 3: Add route smoke specs

**Files:**
- Create: `frontend/tests/smoke/routes.spec.ts`

**Step 1: Write the failing test**

Add one test per route:

- `/`
- `/expert`
- `/debate`
- `/agent`
- `/sector`
- `/plans`
- `/tasks`

Each test:

- installs collectors
- installs API mock
- opens the route
- waits for a stable page marker
- asserts zero runtime errors

**Step 2: Run test to verify it fails**

Run: `npm run test:smoke`
Expected: fail until selectors/mocks match real pages.

**Step 3: Write minimal implementation**

Tune per-route selectors and mock payloads so pages render cleanly.

**Step 4: Run test to verify it passes**

Run: `npm run test:smoke`
Expected: all route smoke tests pass.

### Task 4: Keep existing frontend verification green

**Files:**
- No new files required unless verification exposes issues

**Step 1: Run focused frontend checks**

Run: `npm run build`
Expected: PASS

**Step 2: Run existing node-based frontend tests**

Run: `node --test app/agent/lib/*.test.ts app/agent/reflectionFeed.test.ts`
Expected: PASS

**Step 3: Run smoke suite**

Run: `npm run test:smoke`
Expected: PASS

### Task 5: Document usage for local debugging

**Files:**
- Modify: `frontend/package.json`
- Optionally modify: `README.md`

**Step 1: Add usage note**

Document the command a developer should run when they want to catch frontend console errors automatically.

**Step 2: Verify wording against actual commands**

Run: `cat frontend/package.json`
Expected: script names match documentation exactly.
