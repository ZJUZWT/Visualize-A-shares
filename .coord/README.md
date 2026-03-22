# Local Coordination Protocol

This directory is a lightweight mailbox for parallel Codex or Claude sessions.

## Layout

```text
.coord/
├── README.md
├── templates/
│   ├── commit.txt
│   ├── result.md
│   ├── status.json
│   └── task.md
└── runtime/   # ignored by git
```

## Intent

- Keep worker coordination local to the repo.
- Avoid one shared scratch file that multiple agents can overwrite.
- Separate stable protocol from transient execution output.
- Preserve git worktrees as the only place where source code is edited.

## Runtime Contract

For each worker, create one directory:

```text
.coord/runtime/<worker-name>/
├── task.md
├── status.json
├── result.md
└── commit.txt
```

Typical names:

- `.coord/runtime/worker-a/`
- `.coord/runtime/worker-b/`
- `.coord/runtime/reviewer/`

## Ownership Rules

Coordinator:

- Creates the worker runtime directory.
- Writes `task.md`.
- Reviews worker output and chooses canonical commits.

Worker:

- Must read `.coord/README.md` before starting work.
- Reads only its own assigned runtime directory.
- Updates only its own `status.json`, `result.md`, and `commit.txt`.
- Must not write into another worker's runtime directory.
- Must not treat `.coord/runtime/` as a place to edit project source.

Reviewer:

- Reads worker outputs.
- Maps accepted work to canonical commit hashes.
- Decides integration order.

## Suggested Worker Lifecycle

1. Coordinator copies templates into `.coord/runtime/<worker-name>/`.
2. Coordinator fills in `task.md`.
3. Worker sets `status.json` to `running`.
4. Worker completes work in its git worktree.
5. Worker writes a human-readable completion or blocker summary to `result.md`.
6. Worker writes final commit hash to `commit.txt`.
7. Worker sets `status.json` to `done` or `blocked`.
8. Reviewer reads outputs and performs review/integration.

## Notes

- `.coord/runtime/` is intentionally ignored by git.
- `.coord/templates/` is committed so future sessions can reuse the same protocol.
- If a worker is restarted, rewrite `task.md` rather than appending chat-style history.
- `result.md` is the canonical completion summary file. Chat replies can stay short.
