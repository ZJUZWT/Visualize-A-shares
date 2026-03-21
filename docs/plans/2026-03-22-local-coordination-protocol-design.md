# Local Coordination Protocol Design

**Goal:** Add a lightweight local coordination protocol for parallel Codex sessions without introducing scripts or a shared mutable chat file.

**Context**

The repo already has a planning convention for multi-worker execution, but it does not yet define a concrete local handoff format. Recent parallel work showed the main failure mode is not lack of worktrees, but lack of a stable coordination surface: workers continue past their ownership boundary, reviewers have to infer canonical commits from chat, and temporary outputs get mixed into normal project files.

**Decision**

Use a committed `.coord/` directory for protocol and templates, and a git-ignored `.coord/runtime/` directory for ephemeral worker state.

Directory model:

```text
.coord/
├── README.md
├── templates/
│   ├── commit.txt
│   ├── result.md
│   ├── status.json
│   └── task.md
└── runtime/   # ignored
```

**Why this approach**

1. A single shared chat file is too fragile.
   Multiple workers would overwrite each other, append in inconsistent formats, and make ownership unclear.
2. A worker-scoped mailbox keeps write sets disjoint.
   Each worker can read its own `task.md` and only write back its own `status.json`, `result.md`, and `commit.txt`.
3. Keeping the protocol in-repo makes it reusable.
   Any future Codex or Claude session can discover the same contract from disk without relying on prior chat history.
4. Ignoring runtime state keeps git history clean.
   The stable protocol is versioned; transient execution artifacts are not.

**Protocol**

For each worker, the coordinator creates:

```text
.coord/runtime/<worker-name>/
├── task.md
├── status.json
├── result.md
└── commit.txt
```

Rules:

- Coordinator writes `task.md`.
- Worker reads only its assigned directory.
- Worker updates only its own `status.json`, `result.md`, and `commit.txt`.
- Reviewer reads all worker outputs and decides canonical commits.
- Source code changes still happen in isolated git worktrees, not inside `.coord/runtime/`.

**Non-goals**

- No automation scripts in this pass.
- No background watcher or polling daemon.
- No attempt to replace git as the source of truth for code changes.

**Success criteria**

- The repo contains a discoverable, documented coordination protocol.
- Templates exist for task, status, result, and commit handoff.
- Runtime coordination files are excluded from git.
