# Local Reproduction Run Chain Implementation Plan

> **For agentic workers:** Execute task-by-task with test-first steps. Keep the changes in the current workspace and do not create commits.

**Goal:** Let a user create a paper-reproduction or experiment-check task locally, give it an owned workflow, run that workflow with the existing local executor, and reopen its run trace after restart.

**Architecture:** Add local reproduction-task metadata and a task-workflow ownership table to the existing SQLite runtime. Reuse the existing draft, compiler, scheduler, run, event, cache, ArtifactHandle, and report paths; do not fork a second execution engine. A successful workflow run moves the task to `awaiting_review`; it never declares scientific agreement unless a future comparison slice has actual metric outputs and explicit rules. Local-only records remain local until a user-controlled sync action is implemented; no reconnect or login path uploads them.

**Tech Stack:** FastAPI, SQLite, React, TypeScript, existing local workflow runtime, unittest, Vitest.

---

## Scope and acceptance

- The local runtime supports create/list/detail for paper and experiment tasks, with bounded source, claim, baseline, and optional local-project link fields.
- A local reproduction task owns its workflows. Project-owned workflows keep their current owner and sync behavior.
- Task workflows use the current compiler and local scheduler; their runs, node states, events, artifacts, and reports remain in local storage and can be read after runtime restart.
- The desktop reproduction list and detail page distinguish local-only tasks from platform tasks and provide explicit local task creation, workflow creation, run, and trace navigation.
- A successful run is shown as execution success plus `awaiting_review`, never as `conforms` or `differs` without comparable actual metrics and a declared rule.
- No synthetic examples, fixture values, or guessed conclusions appear as user results. Mobile remains out of scope.

## Files and responsibilities

- `backend/app/services/local_runtime_store.py`: additive SQLite tables, local task/workflow owner queries, status transition after a task-owned workflow run.
- `backend/app/local_runtime.py`: authenticated loopback task and task-workflow routes; reuse existing local draft/run routes.
- `backend/tests/test_local_runtime_reproductions.py`: store/API lifecycle, owner isolation, run persistence, and review-state coverage.
- `frontend/src/api/localRuntime.ts`: runtime task and task-workflow request/response contracts.
- `frontend/src/App.tsx`: explicit local task creation and local task detail/workflow/run display, while preserving the existing platform path.
- `frontend/src/App.localReproduction.test.tsx`: local task creation, disconnected task detail, run trace/report display, and loopback-only request coverage.
- `task.md` and `memory/ict/workflow-runtime.md`: acceptance evidence and remaining scientific-comparison boundary.

## Tasks

### Task 1: Define persistence contracts with failing tests

- [x] Test local task create/list/detail, required title/kind, bounded JSON baseline (64 KB rejection), optional link to an existing local project, and persistence after reopening the same runtime directory.
- [x] Test task-owned workflow creation/list/detail and exact owner metadata (`owner_type=reproduction`, `owner_id=task_id`); reject missing task IDs and keep project workflows visible only under their project.
- [x] Test task workflow draft save and compiler-backed run submission through existing local routes; run history must include node records/events and survive store reopen.
- [x] Test successful run updates the task to `awaiting_review` and does not assign `conforms` or `differs` without an actual comparison record.
- [x] Run `backend/.venv/Scripts/python.exe -m unittest tests.test_local_runtime_reproductions -v` from `backend`; new tests first failed with 404 while routes were absent, then passed after implementation.

### Task 2: Add additive SQLite task ownership and API

- [x] Add `local_reproduction_tasks` and `local_reproduction_workflows` without rebuilding or deleting existing project tables. The workflow owner mapping references the existing durable workflow draft ID and the local reproduction task.
- [x] Extend local workflow reads and draft saves to resolve either the existing project owner or the reproduction owner. Keep project sync-state changes limited to project-owned workflows.
- [x] Add authenticated loopback `GET/POST /api/v1/local/reproductions`, `GET /api/v1/local/reproductions/{task_id}`, and `GET/POST /api/v1/local/reproductions/{task_id}/workflows` routes with strict request validation and bounded baseline JSON.
- [x] After a reproduction-owned run finishes, persist `running` while active and `awaiting_review` on success; preserve a non-conclusive state on failure or cancellation.
- [x] Run the new backend tests and existing local runtime project, workflow, run, and sync tests; complete backend suite passed 106 tests.

### Task 3: Connect desktop local reproduction objects

- [x] Add typed runtime client methods and parsers for local reproduction tasks and their workflows; do not call platform endpoints from these methods.
- [x] Add a visibly labeled “本机新建任务” action to the existing reproduction area. Keep platform task creation unchanged and do not silently switch destinations after any API error.
- [x] Route local task IDs to local runtime detail/workflow APIs; reuse the existing workflow editor, local run controls, and run/artifact readers.
- [x] Show task owner, local-only state, workflow run state, and review state from real runtime data; keep comparison empty until actual comparable metrics exist.
- [x] Inspect the existing Coze/ComfyUI and biomedical dashboard screenshot references before UI edits; follow V4.0 content density and component tokens.
- [x] Add UI tests for explicit local creation, local detail navigation, run trace/report display, review state, and loopback-only requests with no platform write.
- [x] Run frontend typecheck and targeted Vitest files; full frontend suite passed 54 tests with 1 skipped.

### Task 4: Verify the local reproduction vertical slice

- [x] Use a fresh temporary runtime directory with platform API disabled. Create a local experiment task and a task-owned workflow, import a synthetic CSV, execute the supported CSV preflight component, and read its trace and non-research report.
- [x] Reopen the runtime against the same temporary directory and confirm task, workflow revision, run status/events, and report remain readable; the run returns to `awaiting_review`.
- [x] Confirm UI labels the task “待复核” and makes no conformity claim; UI tests confirm requests remain on loopback and no platform write occurs.
- [x] Record completed evidence in `task.md` and `memory/ict/workflow-runtime.md`; metric comparison, evidence adjudication, real paper validity, and local reproduction-task sync remain incomplete.

## Known follow-up boundary

This slice does not add a scientific model executor, actual-metric extraction, conformity adjudication, or the user-confirmed synchronization UI for reproduction tasks. Local task and workflow records remain on device with no automatic upload; a deliberate sync action and its conflict/permission rules are a separate follow-up. Those capabilities require real scientific outputs and an explicitly invoked sync contract; this implementation must not substitute synthetic values.
