---
name: local-parallel-development
description: Use when coordinating or executing parallel development work in this repository, especially when tasks should be split into disjoint write sets with tracked plans in docs/superpowers/plans and runtime handoff files in .coord.
---

# Local Parallel Development

## Overview

This repository uses a fixed parallel-work convention.

- Tracked plans live in `docs/superpowers/plans/`
- Runtime handoff lives in `.coord/runtime/<batch-id>/`
- Current batch pointer lives in `.coord/active-batch.json`

When an agent is told to use this skill, it should resolve the project-local skill path convention first:

- `docs/superpowers/skills/<skill-name>/SKILL.md`

## When To Use

Use this skill for any task that should be planned, executed, or reviewed through multiple parallel workers.

Do not use it for:

- single-file edits
- tightly coupled work that cannot be split into disjoint write sets
- casual brainstorming without implementation handoff

## Modes

### Plan Mode

Use when the main session is preparing a new batch.

Required outcomes:

1. Create a tracked plan at `docs/superpowers/plans/YYYY-MM-DD-<slug>.md`
2. Create a runtime batch folder at `.coord/runtime/<batch-id>/`
3. Write `manifest.json` in that batch folder
4. Write one worker brief per worker
5. Define output files under `outputs/`
6. Update `.coord/active-batch.json`

Rules:

- Prefer disjoint write sets over thematic splitting
- Default to `parallelism=auto`; choose 2-4 workers unless the user specifies a number
- Every worker brief must include:
  - owned files
  - forbidden files
  - tests
  - done condition
  - required summary output path
- The tracked plan must include:
  - mainline
  - worker plans
  - review / integration

### Worker Mode

Use when a worker session is executing one assigned slice.

Execution order:

1. Read `.coord/active-batch.json`
2. Read the pointed `manifest.json`
3. Read only the assigned worker brief
4. Stay inside the owned write set
5. Run the required focused verification
6. Write completion summary to the assigned `outputs/*.md`

Worker rules:

- Do not broaden scope silently
- Do not edit another worker's owned files
- If blocked by an architecture mismatch, record it in the summary instead of freelancing

### Review Mode

Use when the main session is integrating worker output.

Execution order:

1. Read `.coord/active-batch.json`
2. Read `manifest.json`
3. Read each worker summary in `outputs/`
4. Review diffs and commits independently
5. Run fresh regression locally
6. Integrate in the declared merge order

Review rules:

- Never trust worker "done" claims without diff + verification
- Fix small integration mismatches locally when cheaper than redispatch
- Do not merge forbidden-file drift without explicit approval

## Batch Layout

```text
.coord/
  active-batch.json
  runtime/
    <batch-id>/
      manifest.json
      README.md
      worker-a-*.md
      worker-b-*.md
      worker-c-*.md
      outputs/
        worker-a-summary.md
        worker-b-summary.md
        worker-c-summary.md
```

Recommended `manifest.json` fields:

- `batch_id`
- `title`
- `plan_path`
- `parallelism`
- `merge_order`
- `workers`

Each worker entry should include:

- `id`
- `brief_path`
- `output_path`
- `scope`

## Prompt Templates

Use these exact prompts unless the batch needs extra constraints.

Plan mode:

```text
Use project skill local-parallel-development in plan mode for: <task>. parallelism=3
```

Worker mode:

```text
Use project skill local-parallel-development in worker mode as worker-2 on the active batch.
```

Review mode:

```text
Use project skill local-parallel-development in review mode on the active batch.
```

## Repository Convention

For this repository specifically:

- superpowers-authored plans go to `docs/superpowers/plans/`
- specs stay in `docs/superpowers/specs/`
- runtime coordination stays out of git under `.coord/runtime/`
- `.coord/active-batch.json` is a local pointer, not a tracked artifact

## Common Mistakes

- Writing plans into `docs/plans/` instead of `docs/superpowers/plans/`
- Letting two workers edit the same file family
- Having workers report back only in chat instead of writing `outputs/*.md`
- Reviewing worker claims without rerunning verification
