# Offline Local Workspace Implementation Plan

> **For agentic workers:** Execute task-by-task with test-first steps. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** By 2026-11-10, close the desktop basic-component loop: create a local project/workflow offline, use the installed CSV components, persist and reopen run artifacts, and sync definitions only after explicit user action.

**Architecture:** Follow V4.0 ENG-7.5: add a local project/workflow catalog to the existing SQLite runtime. The workbench combines platform projects with clearly marked local-only projects; local project creation and editing never silently call platform APIs or upload data. Reconnection does not sync automatically; a user-confirmed action copies project metadata and workflow definitions to a private platform project while local files, runs, and artifacts stay on this device. Existing platform-owned projects continue using their current API and sync/conflict behavior.

**Tech Stack:** FastAPI, Pydantic, SQLite, React, TypeScript, Vitest, pytest, packaged Windows runtime.

---

### Task 1: Specify durable local project/workflow storage

**Files:**
- Create: `backend/tests/test_local_runtime_projects.py`
- Reuse existing baseline: `backend/tests/test_local_runtime_api_copy_20261103_before_same-origin-session.py`

- [x] Add failing tests for project creation/list/detail, local workflow creation/list/detail, empty revision-1 graph, invalid names, unknown project IDs, and persistence after reopening `LocalRuntimeStore`.
- [x] Run `python -m unittest backend.tests.test_local_runtime_projects -v` and confirm failures are missing API/store behavior, not test setup errors.

### Task 2: Add local catalog APIs backed by SQLite

**Files:**
- Modify: `backend/app/services/local_runtime_store.py`
- Modify: `backend/app/local_runtime.py`
- Test: `backend/tests/test_local_runtime_projects.py`

- [x] Add additive SQLite tables for local projects and their workflows; preserve existing run, artifact, and draft tables.
- [x] Add validated create/list/detail methods and authenticated loopback endpoints. Local workflow creation must create an empty durable draft and return local-only ownership metadata.
- [x] Verify same-origin session auth, validation failures, persistence across store reopen, and existing local CSV run tests.

### Task 3: Add typed frontend local catalog access

**Files:**
- Modify: `frontend/src/api/localRuntime.ts`
- Modify: `frontend/src/api/localRuntime.test.ts`

- [x] Define local project/workflow response types and API client methods for list/create/detail.
- [x] Add failing client contract tests, then verify response validation and error propagation.

### Task 4: Connect the workbench and canvas to local objects

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api/projects.ts` only if shared project typing needs a local source marker.

- [x] Load local projects independently of platform connectivity and merge them into Workbench without replacing access-controlled platform results.
- [x] When the platform is unavailable, let the existing project form explicitly create a local-only project; show its local-only state.
- [x] Load a local project and its workflows from the local runtime, create a local blank workflow, and open the existing canvas using its durable ID and revision-1 draft.
- [x] Keep local project/workflow edits and runs on loopback; platform-owned objects retain existing save/sync paths.
- [x] When adding a node from the component catalog, pan the viewport slightly only if the new node is occluded by canvas bounds or the bottom run panel; preserve zoom and all other node positions.

### Task 5: Verify the cold offline canvas loop

**Files:**
- Update: `task.md`
- Update: `memory/ict/workflow-runtime.md`

- [x] Use a fresh temporary app-data directory and no seeded browser project cache; make platform API calls return 503.
- [x] Create a local project and workflow, import a synthetic CSV, add CSV source and structural preflight nodes, connect `out:csv` to `in:csv`, and run successfully.
- [x] Restart the local runtime and confirm project, workflow, run, and non-research report remain available; confirm no non-loopback request occurred.
- [x] Build a new packaged EXE in a new directory and record any remaining boundary, especially explicit platform sync for local-only objects.

**Acceptance record (2026-11-03):** Fresh temporary Edge/runtime workspace completed the offline create → edit → CSV run → restart → report-read loop with platform APIs mocked as 503. After restart, the report showed 2 rows, 4 columns, 0 issues, and `research_result=false` / “非科研结果”; no failed requests or page errors. Real desktop canvas checks with the run dock collapsed and expanded confirmed catalog “＋” only pans when clipped, keeps zoom at 1 and existing node graph coordinates unchanged, and reveals the new node. Dragging a catalog item keeps the pointer drop position and viewport unchanged. After manually zooming to `0.578704`, adding an in-bounds catalog node left the viewport transform unchanged. Screenshots: `artifacts/ui/local-workspace-run-report-desktop-20261103.png`, `artifacts/ui/local-workspace-node-reveal-desktop-20261103.png`, `artifacts/ui/local-workspace-node-reveal-expanded-dock-desktop-20261103.png`, and `artifacts/ui/local-workspace-drag-placement-desktop-20261103.png`.

Packaged build: `desktop/dist/workflow-app-20261103-localworkspace/ICTWorkflowWorkbench.exe`, SHA-256 `D336535DEFF981EDBEAE378174CB31B025B9E6AB19FA3810C3E3C8345C8C7D2B`; PyInstaller archive listing confirms the current `frontend/dist` assets and local runtime modules are included. To avoid the existing product instance's mutex and port 8768, a smoke-only onefile executable was rebuilt from the same spec and resource inputs with only its mutex name changed. With `--serve-only`, isolated `LOCALAPPDATA`, and port 18783, the packaged UI cold-started, created a local project/workflow, imported a synthetic CSV, connected the typed source/preflight nodes, ran successfully, and displayed the non-research report. Platform validation returned the mocked 503 twice; 16 local API calls completed, with no non-loopback requests, failed requests, or page errors. The two console errors were the expected mocked 503 responses. Screenshot: `artifacts/ui/workflow-package-offline-workspace-e2e-20261103.png`. The smoke harness terminated its own onefile child by verified temporary executable path and confirmed port 18783 released. The official mutex-name executable was not launched directly. Real platform synchronization and cloud Worker execution remain outside this completed local-only loop.

### Task 6: Add user-controlled sync for offline projects

**Files:**
- Modify: `backend/app/services/local_runtime_store.py`
- Modify: `backend/app/local_runtime.py`
- Modify: `frontend/src/api/localRuntime.ts`
- Create: `frontend/src/api/localProjectSync.ts`
- Modify: `frontend/src/App.tsx` and `frontend/src/App.css`
- Update: `人工文档方案/模块化智能科研平台_开发统一方案_V4.0.md`, `task.md`, and `memory/ict/workflow-runtime.md`

- [x] Keep local projects and workflows local by default; create a durable local outbox record only after the user starts explicit sync.
- [x] Add a confirmation step that lists metadata/graph fields sent and excludes local files, artifact contents, runs, reports, and logs; credentials are used only by the existing API authorization header and are never written to sync content or the local outbox.
- [x] Create a platform project copy and sync each workflow definition; persist remote IDs and both source/platform revisions for resumable attempts. If a create response is ambiguous, allow the user to link the returned platform object ID or explicitly confirm there is no matching object before retrying.
- [x] Preserve local copies. Detect platform ownership/revision changes and stop rather than overwrite; expose partial, failed, conflict, and uncertain-create states.
- [x] If local workflow content changes after sync, mark its outbox state as pending until the user syncs again.
- [x] Isolated integration test runs the frontend sync module against a real temporary SQLite runtime and mock platform: local project/workflow creation, CSV import and local run remain local until `syncLocalProjectToPlatform` is explicitly called; only project metadata and workflow definition are sent; outbox mappings persist and the original run remains readable.
- [x] Six frontend orchestration tests cover first sync, partial retry without duplicate creates, stop on moved remote revision, and manual review before retrying ambiguous project/workflow creates.
- [x] Two runtime API tests cover outbox persistence across runtime restart, exclusive pending sync, and marking edited synced drafts pending; together with local project persistence tests, 4 backend tests pass.
- [x] App UI integration test verifies the project-page dialog: cancel performs no sync write; confirm creates and syncs the platform copy while retaining the local project.
- [x] Rebuild the portable EXE from current source and run isolated startup/API smoke. Health reports local mode with `platform_required=false`, the frontend entry returns HTTP 200, and the authenticated component registry exposes 5 runnable local CSV components (4 primary pipeline components plus the legacy quick-preflight node). SHA-256: `8C602E86B108C3D175BAA6DA5F0CF6B1DB984120633B9020373B7F2D390CF75A`.

**Implementation note:** The platform copy is created as a new private project because an offline-only project has no platform identity to target. A workflow graph may contain local file references; those references are preserved as definition metadata but the corresponding local files remain on this device.

### Task 7: Add an offline built-in CSV workflow template

**Files:**
- Create: `backend/app/services/local_workflow_templates.py`
- Modify: `backend/app/local_runtime.py`
- Modify: `backend/app/services/local_runtime_store.py`
- Modify: `frontend/src/api/localRuntime.ts`
- Modify: `frontend/src/App.tsx` and `frontend/src/App.css`
- Update: `task.md` and `memory/ict/workflow-runtime.md`

- [x] Register a versioned built-in template with the actual local CSV component IDs and typed ports: CSV source → field selection → structural preflight + descriptive summary. The graph uses fresh node/edge IDs for each instance and leaves required file/field parameters empty for the user to configure.
- [x] Add authenticated loopback list and instantiate endpoints. Instantiate only by registered template ID/version, and create workflow metadata plus the complete revision-1 graph in one SQLite transaction; the client cannot submit a graph and template creation does not sync to the platform.
- [x] Add runtime API types and calls, then show a clearly labeled local built-in template in Template Market independently of platform catalog connectivity. The user can choose an existing local project, create the workflow, and open its canvas. Missing local projects route to the Workbench; runtime errors remain visible.
- [x] Run Python syntax compilation and frontend typecheck/build, then perform an isolated temporary-runtime API smoke with a synthetic manifest. The four-node workflow succeeded; preflight returned 2 rows with `research_result=false` and an advisory for the extra `score` column, and descriptive statistics returned 2 rows × 5 columns. Reopening the SQLite store retained workflow revision 2. No automated tests were added or run; browser/packaged visual acceptance remains pending.
- [x] Build the Windows portable EXE into a new versioned output directory and inspect its PyInstaller analysis/archive inputs; do not launch it or claim runtime acceptance.
- [x] Record implementation boundaries and checks in `task.md` and `memory/ict/workflow-runtime.md`.

**Task 7 API smoke boundary:** `FastAPI TestClient` used a temporary data directory and loopback base URL; only local endpoints and four local CSV executors were called. The synthetic manifest contained the required `record_id`, `group_id`, `split`, and `label` fields plus an extra `score` field. The successful preflight warning is expected for that extra field; it does not indicate experiment validation. The package was built but not launched.

### 2026-11-10 basic-component closure

- [x] Current runnable local CSV components: `ict.data.csv_artifact_source`, `ict.data.csv_select_columns`, `ict.data.csv_manifest_preflight_input`, and `ict.data.csv_descriptive_summary`; `ict.data.csv_manifest_preflight` remains as a runnable quick-preflight compatibility node. Reports state that structural preflight is not a research result and descriptive statistics are exploratory only.
- [x] Offline local project/workflow creation, typed CSV workflow run, runtime restart persistence, and report readback have desktop/runtime acceptance records in `task.md`.
- [x] App UI integration test covers cancel and confirm behavior for the explicit sync dialog; no platform write occurs before confirmation.
- [x] Rebuilt current portable EXE into `desktop/dist/workflow-app-20261103-nov10/` and started it with isolated `LOCALAPPDATA`, `--serve-only`, and port 18792; health, frontend serving, local session authentication, and CSV component availability passed. Both the parent and onefile child processes were stopped after verifying their executable paths, and port 18792 was released.
- [x] Packaged UI E2E: in the built EXE, open an isolated local project and workflow, run a typed four-node CSV graph (source → field selection → structural preflight + descriptive summary), and read both reports. After stopping and restarting the exact EXE against the same isolated `LOCALAPPDATA`, the project, revision-5 workflow, successful run `ebc92954-1130-401b-abb3-47053c466dcf`, 4 artifact references and report contents remained readable; browser console errors were 0. The synthetic manifest emitted the expected `unvalidated_extra_columns` advisory for its extra `score` field; reports were labeled non-research/exploratory. No platform or external service was used. This verifies packaged functional UI and persistence, not complete visual sign-off or real platform sync/authentication.
- Scope exclusions for this deadline: mobile UI, real platform Worker, cloud GPU scheduling, independent worker process sandbox, and claims of scientific or paper-reproduction validity.
