# Local Coordination Protocol Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a simple in-repo coordination protocol for parallel Codex sessions using committed docs/templates and git-ignored runtime worker mailboxes.

**Architecture:** Keep stable protocol files under `.coord/` and ignore transient worker state under `.coord/runtime/`. The protocol supplements worktrees rather than replacing them: code changes still happen in isolated branches, while `.coord/runtime/<worker>/` carries task and result handoff.

**Tech Stack:** Markdown, JSON, gitignore

---

### Task 1: Document the protocol

**Files:**
- Create: `docs/plans/2026-03-22-local-coordination-protocol-design.md`
- Create: `.coord/README.md`

**Step 1: Write the design doc**

Describe the directory shape, mailbox contract, ownership rules, and non-goals.

**Step 2: Write the repo-facing README**

Document how coordinator and workers should use `.coord/` in practice.

**Step 3: Verify readability**

Run: `sed -n '1,220p' .coord/README.md`
Expected: clear protocol with worker-scoped runtime directories and no script dependency

### Task 2: Add reusable templates

**Files:**
- Create: `.coord/templates/task.md`
- Create: `.coord/templates/status.json`
- Create: `.coord/templates/result.md`
- Create: `.coord/templates/commit.txt`

**Step 1: Add task template**

Include worker name, worktree, ownership, forbidden files, tests, and done conditions.

**Step 2: Add status template**

Include machine-readable fields for phase, state, blocker, and updated timestamp.

**Step 3: Add result and commit templates**

Keep result human-readable and commit handoff minimal.

**Step 4: Verify files exist**

Run: `find .coord/templates -maxdepth 1 -type f | sort`
Expected: `commit.txt`, `result.md`, `status.json`, `task.md`

### Task 3: Keep runtime output out of git

**Files:**
- Modify: `.gitignore`

**Step 1: Add ignore rule**

Ignore `.coord/runtime/` while leaving `.coord/README.md` and `.coord/templates/` tracked.

**Step 2: Verify ignore intent**

Run: `rg -n "\\.coord/runtime/" .gitignore`
Expected: one ignore entry for `.coord/runtime/`

### Task 4: Final verification

**Files:**
- Modify: `.gitignore`
- Create: `.coord/README.md`
- Create: `.coord/templates/task.md`
- Create: `.coord/templates/status.json`
- Create: `.coord/templates/result.md`
- Create: `.coord/templates/commit.txt`

**Step 1: Check final file tree**

Run: `find .coord -maxdepth 2 -type f | sort`
Expected: README and template files only

**Step 2: Confirm runtime remains absent or ignored**

Run: `git status --short`
Expected: only intended tracked additions/modifications
