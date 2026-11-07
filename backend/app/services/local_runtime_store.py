"""SQLite persistence for the standalone local workflow runtime."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any
from collections.abc import Iterator
from uuid import uuid4

from app.services.workflow_execution import compile_execution_plan


logger = logging.getLogger("ict.local_runtime.store")


class LocalRuntimeStoreError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class LocalRuntimeStore:
    """Persist local workflow copies, plans, node runs, and append-only events."""

    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "runtime.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        try:
            with self._connection() as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS local_workflow_drafts (
                        workflow_id TEXT PRIMARY KEY,
                        revision INTEGER NOT NULL CHECK(revision >= 1),
                        graph_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS local_projects (
                        project_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        domain TEXT NOT NULL,
                        description TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS local_workflows (
                        workflow_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES local_projects(project_id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS local_reproduction_tasks (
                        task_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        kind TEXT NOT NULL CHECK(kind IN ('paper', 'experiment')),
                        source TEXT NOT NULL,
                        claim TEXT NOT NULL,
                        baseline_json TEXT,
                        criteria_version TEXT,
                        linked_project_id TEXT REFERENCES local_projects(project_id) ON DELETE SET NULL,
                        status TEXT NOT NULL CHECK(status IN (
                            'preparation', 'insufficient_conditions', 'ready_to_run', 'running',
                            'awaiting_review', 'conforms', 'differs', 'undetermined'
                        )),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS ix_local_reproduction_tasks_updated
                        ON local_reproduction_tasks(updated_at);
                    CREATE TABLE IF NOT EXISTS local_reproduction_workflows (
                        workflow_id TEXT PRIMARY KEY REFERENCES local_workflow_drafts(workflow_id) ON DELETE CASCADE,
                        reproduction_task_id TEXT NOT NULL REFERENCES local_reproduction_tasks(task_id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS ix_local_reproduction_workflows_task_updated
                        ON local_reproduction_workflows(reproduction_task_id, updated_at);
                    CREATE TABLE IF NOT EXISTS local_project_sync_state (
                        project_id TEXT PRIMARY KEY REFERENCES local_projects(project_id) ON DELETE CASCADE,
                        status TEXT NOT NULL CHECK(status IN (
                            'pending', 'partial', 'synced', 'failed', 'conflict', 'needs_review'
                        )),
                        platform_project_id TEXT,
                        error_code TEXT,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS local_workflow_sync_state (
                        workflow_id TEXT PRIMARY KEY REFERENCES local_workflows(workflow_id) ON DELETE CASCADE,
                        project_id TEXT NOT NULL REFERENCES local_projects(project_id) ON DELETE CASCADE,
                        status TEXT NOT NULL CHECK(status IN (
                            'pending', 'synced', 'failed', 'conflict', 'needs_review'
                        )),
                        platform_workflow_id TEXT,
                        synced_revision INTEGER CHECK(synced_revision IS NULL OR synced_revision >= 1),
                        source_revision INTEGER CHECK(source_revision IS NULL OR source_revision >= 1),
                        error_code TEXT,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS ix_local_workflows_project_updated
                        ON local_workflows(project_id, updated_at);
                    CREATE TABLE IF NOT EXISTS local_workflow_runs (
                        run_id TEXT PRIMARY KEY,
                        workflow_id TEXT NOT NULL,
                        plan_hash TEXT NOT NULL,
                        execution_plan_json TEXT NOT NULL,
                        target_node_ids_json TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN (
                            'queued', 'running', 'waiting_external', 'succeeded',
                            'partially_succeeded', 'failed', 'cancelled'
                        )),
                        error_code TEXT,
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS ix_local_workflow_runs_workflow_created
                        ON local_workflow_runs(workflow_id, created_at);
                    CREATE TABLE IF NOT EXISTS local_node_output_cache (
                        signature_hash TEXT PRIMARY KEY CHECK(length(signature_hash) = 64),
                        output_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS local_workflow_node_runs (
                        run_id TEXT NOT NULL,
                        node_id TEXT NOT NULL,
                        component_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        error_code TEXT,
                        output_json TEXT,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(run_id, node_id),
                        FOREIGN KEY(run_id) REFERENCES local_workflow_runs(run_id) ON DELETE CASCADE
                    );
                    CREATE TABLE IF NOT EXISTS local_workflow_run_events (
                        run_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        node_id TEXT,
                        status TEXT NOT NULL,
                        error_code TEXT,
                        occurred_at TEXT NOT NULL,
                        PRIMARY KEY(run_id, sequence),
                        FOREIGN KEY(run_id) REFERENCES local_workflow_runs(run_id) ON DELETE CASCADE
                    );
                    """
                )
                run_columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(local_workflow_runs)")
                }
                if "recovered_from_run_id" not in run_columns:
                    # Keep existing local databases compatible; recovery is an additive relation.
                    connection.execute(
                        "ALTER TABLE local_workflow_runs ADD COLUMN recovered_from_run_id TEXT"
                    )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS ix_local_workflow_runs_recovery_parent "
                    "ON local_workflow_runs(recovered_from_run_id, status)"
                )
        except sqlite3.Error as error:
            logger.exception("local_runtime_database_init_failed error_type=%s", type(error).__name__)
            raise LocalRuntimeStoreError(
                "LOCAL_STORE_UNAVAILABLE", "本机运行记录存储无法初始化。", status_code=503
            ) from error

    def create_local_reproduction_task(
        self,
        *,
        title: str,
        kind: str,
        source: str,
        claim: str,
        baseline: dict[str, Any] | None,
        criteria_version: str | None,
        linked_project_id: str | None,
    ) -> dict[str, Any]:
        """Persist a local-only reproduction task without deriving a scientific result."""
        clean_title = title.strip()
        clean_source = source.strip()
        clean_claim = claim.strip()
        clean_criteria_version = criteria_version.strip() if criteria_version is not None else None
        if not clean_title or len(clean_title) > 200 or kind not in {"paper", "experiment"}:
            raise LocalRuntimeStoreError("LOCAL_REPRODUCTION_INVALID", "本机复现任务标题或类型无效。", status_code=422)
        if len(clean_source) > 20_000 or len(clean_claim) > 20_000:
            raise LocalRuntimeStoreError("LOCAL_REPRODUCTION_INVALID", "本机复现任务来源或主张超过长度限制。", status_code=422)
        if clean_criteria_version is not None and len(clean_criteria_version) > 64:
            raise LocalRuntimeStoreError("LOCAL_REPRODUCTION_INVALID", "本机判定规则版本超过长度限制。", status_code=422)
        if baseline is not None and not isinstance(baseline, dict):
            raise LocalRuntimeStoreError("LOCAL_REPRODUCTION_INVALID", "本机基准信息必须是对象。", status_code=422)
        baseline_json = _json(baseline) if baseline is not None else None
        if baseline_json is not None and len(baseline_json.encode("utf-8")) > 64_000:
            raise LocalRuntimeStoreError("LOCAL_REPRODUCTION_INVALID", "本机基准信息超过 64 KB。", status_code=422)

        task_id = f"local-reproduction-{uuid4().hex}"
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                if linked_project_id is not None:
                    linked_project = connection.execute(
                        "SELECT project_id FROM local_projects WHERE project_id = ?",
                        (linked_project_id,),
                    ).fetchone()
                    if linked_project is None:
                        raise LocalRuntimeStoreError(
                            "LOCAL_PROJECT_NOT_FOUND", "关联的本机项目不存在。", status_code=404
                        )
                connection.execute(
                    """
                    INSERT INTO local_reproduction_tasks(
                        task_id, title, kind, source, claim, baseline_json, criteria_version,
                        linked_project_id, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'preparation', ?, ?)
                    """,
                    (
                        task_id,
                        clean_title,
                        kind,
                        clean_source,
                        clean_claim,
                        baseline_json,
                        clean_criteria_version,
                        linked_project_id,
                        now,
                        now,
                    ),
                )
                if linked_project_id is not None:
                    connection.execute(
                        "UPDATE local_projects SET updated_at = ? WHERE project_id = ?",
                        (now, linked_project_id),
                    )
            logger.info("local_reproduction_created task_id=%s kind=%s linked_project=%s", task_id, kind, linked_project_id is not None)
            return self.get_local_reproduction_task(task_id)
        except LocalRuntimeStoreError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as error:
            logger.exception("local_reproduction_create_failed task_id=%s error_type=%s", task_id, type(error).__name__)
            raise LocalRuntimeStoreError(
                "LOCAL_REPRODUCTION_CREATE_FAILED", "本机复现任务创建失败。", status_code=500
            ) from error

    def list_local_reproduction_tasks(self) -> list[dict[str, Any]]:
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    "SELECT * FROM local_reproduction_tasks ORDER BY updated_at DESC, task_id"
                ).fetchall()
            return [self._local_reproduction_payload(row) for row in rows]
        except (sqlite3.Error, json.JSONDecodeError) as error:
            logger.exception("local_reproduction_list_failed error_type=%s", type(error).__name__)
            raise LocalRuntimeStoreError(
                "LOCAL_REPRODUCTION_LIST_FAILED", "本机复现任务目录读取失败。", status_code=500
            ) from error

    def get_local_reproduction_task(self, task_id: str) -> dict[str, Any]:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT * FROM local_reproduction_tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
            if row is None:
                raise LocalRuntimeStoreError("LOCAL_REPRODUCTION_NOT_FOUND", "本机复现任务不存在。", status_code=404)
            return self._local_reproduction_payload(row)
        except LocalRuntimeStoreError:
            raise
        except (sqlite3.Error, json.JSONDecodeError) as error:
            logger.exception("local_reproduction_read_failed task_id=%s error_type=%s", task_id, type(error).__name__)
            raise LocalRuntimeStoreError(
                "LOCAL_REPRODUCTION_READ_FAILED", "本机复现任务读取失败。", status_code=500
            ) from error

    @staticmethod
    def _local_reproduction_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["task_id"],
            "workspace_id": "local",
            "linked_project_id": row["linked_project_id"],
            "title": row["title"],
            "kind": row["kind"],
            "source": row["source"],
            "claim": row["claim"],
            "baseline": json.loads(row["baseline_json"]) if row["baseline_json"] else None,
            "criteria_version": row["criteria_version"],
            "status": row["status"],
            "assessment_state": "not_assessed",
            "sync_state": "local_only",
            "created_by": "local-user",
            "updated_by": "local-user",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_local_reproduction_workflow(
        self,
        task_id: str,
        *,
        name: str,
        description: str,
    ) -> dict[str, Any]:
        clean_name = name.strip()
        clean_description = description.strip()
        if not clean_name or len(clean_name) > 120 or len(clean_description) > 4000:
            raise LocalRuntimeStoreError("LOCAL_WORKFLOW_INVALID", "本机工作流名称或说明无效。", status_code=422)

        workflow_id = f"local-reproduction-workflow-{uuid4().hex}"
        now = datetime.now(UTC).isoformat()
        graph_json = _json({"schema_version": "ict.workflow.v1", "nodes": [], "edges": []})
        try:
            with self._connection() as connection:
                task = connection.execute(
                    "SELECT task_id FROM local_reproduction_tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                if task is None:
                    raise LocalRuntimeStoreError(
                        "LOCAL_REPRODUCTION_NOT_FOUND", "本机复现任务不存在。", status_code=404
                    )
                connection.execute(
                    "INSERT INTO local_workflow_drafts(workflow_id, revision, graph_json, updated_at) VALUES (?, 1, ?, ?)",
                    (workflow_id, graph_json, now),
                )
                connection.execute(
                    """
                    INSERT INTO local_reproduction_workflows(
                        workflow_id, reproduction_task_id, name, description, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (workflow_id, task_id, clean_name, clean_description, now, now),
                )
                connection.execute(
                    "UPDATE local_reproduction_tasks SET status = 'ready_to_run', updated_at = ? WHERE task_id = ?",
                    (now, task_id),
                )
            logger.info("local_reproduction_workflow_created task_id=%s workflow_id=%s", task_id, workflow_id)
            return self.get_local_workflow(workflow_id)
        except LocalRuntimeStoreError:
            raise
        except sqlite3.Error as error:
            logger.exception(
                "local_reproduction_workflow_create_failed task_id=%s workflow_id=%s error_type=%s",
                task_id,
                workflow_id,
                type(error).__name__,
            )
            raise LocalRuntimeStoreError(
                "LOCAL_WORKFLOW_CREATE_FAILED", "本机复现工作流创建失败。", status_code=500
            ) from error

    def list_local_reproduction_workflows(self, task_id: str) -> list[dict[str, Any]]:
        try:
            with self._connection() as connection:
                exists = connection.execute(
                    "SELECT task_id FROM local_reproduction_tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                if exists is None:
                    raise LocalRuntimeStoreError(
                        "LOCAL_REPRODUCTION_NOT_FOUND", "本机复现任务不存在。", status_code=404
                    )
                rows = connection.execute(
                    """
                    SELECT workflow_id, NULL AS project_id, reproduction_task_id,
                           'reproduction' AS owner_type, reproduction_task_id AS owner_id,
                           name, description, created_at, MAX(updated_at, draft_updated_at) AS updated_at,
                           revision, graph_json
                    FROM (
                        SELECT w.workflow_id, w.reproduction_task_id, w.name, w.description,
                               w.created_at, w.updated_at, d.updated_at AS draft_updated_at,
                               d.revision, d.graph_json
                        FROM local_reproduction_workflows AS w
                        JOIN local_workflow_drafts AS d ON d.workflow_id = w.workflow_id
                        WHERE w.reproduction_task_id = ?
                    )
                    ORDER BY updated_at DESC, workflow_id
                    """,
                    (task_id,),
                ).fetchall()
            return [self._local_workflow_payload(row) for row in rows]
        except LocalRuntimeStoreError:
            raise
        except sqlite3.Error as error:
            logger.exception(
                "local_reproduction_workflow_list_failed task_id=%s error_type=%s",
                task_id,
                type(error).__name__,
            )
            raise LocalRuntimeStoreError(
                "LOCAL_WORKFLOW_LIST_FAILED", "本机复现工作流目录读取失败。", status_code=500
            ) from error

    def create_local_project(self, *, name: str, domain: str, description: str) -> dict[str, Any]:
        clean_name = name.strip()
        clean_domain = domain.strip()
        clean_description = description.strip()
        if not clean_name or len(clean_name) > 120 or not clean_domain or len(clean_domain) > 80:
            raise LocalRuntimeStoreError("LOCAL_PROJECT_INVALID", "本机项目名称或研究领域无效。", status_code=422)
        if len(clean_description) > 4000:
            raise LocalRuntimeStoreError("LOCAL_PROJECT_INVALID", "本机项目说明超过长度限制。", status_code=422)

        project_id = f"local-project-{uuid4().hex}"
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO local_projects(project_id, name, domain, description, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (project_id, clean_name, clean_domain, clean_description, now, now),
                )
            logger.info("local_project_created project_id=%s", project_id)
            return self.get_local_project(project_id)
        except LocalRuntimeStoreError:
            raise
        except sqlite3.Error as error:
            logger.exception("local_project_create_failed project_id=%s error_type=%s", project_id, type(error).__name__)
            raise LocalRuntimeStoreError("LOCAL_PROJECT_CREATE_FAILED", "本机项目创建失败。", status_code=500) from error

    def list_local_projects(self) -> list[dict[str, Any]]:
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """
                    SELECT p.project_id, p.name, p.domain, p.description, p.created_at, p.updated_at,
                           COUNT(w.workflow_id) AS workflow_count, COALESCE(s.status, 'local_only') AS sync_state,
                           s.platform_project_id
                    FROM local_projects AS p
                    LEFT JOIN local_workflows AS w ON w.project_id = p.project_id
                    LEFT JOIN local_project_sync_state AS s ON s.project_id = p.project_id
                    GROUP BY p.project_id
                    ORDER BY p.updated_at DESC, p.project_id
                    """
                ).fetchall()
            return [self._local_project_payload(row) for row in rows]
        except sqlite3.Error as error:
            logger.exception("local_project_list_failed error_type=%s", type(error).__name__)
            raise LocalRuntimeStoreError("LOCAL_PROJECT_LIST_FAILED", "本机项目目录读取失败。", status_code=500) from error

    def get_local_project(self, project_id: str) -> dict[str, Any]:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    """
                    SELECT p.project_id, p.name, p.domain, p.description, p.created_at, p.updated_at,
                           COUNT(w.workflow_id) AS workflow_count, COALESCE(s.status, 'local_only') AS sync_state,
                           s.platform_project_id
                    FROM local_projects AS p
                    LEFT JOIN local_workflows AS w ON w.project_id = p.project_id
                    LEFT JOIN local_project_sync_state AS s ON s.project_id = p.project_id
                    WHERE p.project_id = ?
                    GROUP BY p.project_id
                    """,
                    (project_id,),
                ).fetchone()
            if row is None:
                raise LocalRuntimeStoreError("LOCAL_PROJECT_NOT_FOUND", "本机项目不存在。", status_code=404)
            return self._local_project_payload(row, detail=True)
        except LocalRuntimeStoreError:
            raise
        except sqlite3.Error as error:
            logger.exception("local_project_read_failed project_id=%s error_type=%s", project_id, type(error).__name__)
            raise LocalRuntimeStoreError("LOCAL_PROJECT_READ_FAILED", "本机项目读取失败。", status_code=500) from error

    def get_local_project_sync_state(self, project_id: str) -> dict[str, Any]:
        """Read durable outbox state without changing the local project's ownership."""
        try:
            with self._connection() as connection:
                project = connection.execute(
                    "SELECT project_id FROM local_projects WHERE project_id = ?", (project_id,)
                ).fetchone()
                if project is None:
                    raise LocalRuntimeStoreError("LOCAL_PROJECT_NOT_FOUND", "本机项目不存在。", status_code=404)
                project_sync = connection.execute(
                    "SELECT status, platform_project_id, error_code, updated_at "
                    "FROM local_project_sync_state WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
                workflow_rows = connection.execute(
                    """
                    SELECT w.workflow_id, s.status, s.platform_workflow_id, s.synced_revision,
                           s.source_revision, s.error_code, s.updated_at
                    FROM local_workflows AS w
                    LEFT JOIN local_workflow_sync_state AS s ON s.workflow_id = w.workflow_id
                    WHERE w.project_id = ?
                    ORDER BY w.workflow_id
                    """,
                    (project_id,),
                ).fetchall()
            return {
                "project_id": project_id,
                "status": project_sync["status"] if project_sync else "local_only",
                "platform_project_id": project_sync["platform_project_id"] if project_sync else None,
                "error_code": project_sync["error_code"] if project_sync else None,
                "updated_at": project_sync["updated_at"] if project_sync else None,
                "workflows": [
                    {
                        "workflow_id": row["workflow_id"],
                        "status": row["status"] if row["status"] else "local_only",
                        "platform_workflow_id": row["platform_workflow_id"],
                        "synced_revision": row["synced_revision"],
                        "source_revision": row["source_revision"],
                        "error_code": row["error_code"],
                        "updated_at": row["updated_at"],
                    }
                    for row in workflow_rows
                ],
            }
        except LocalRuntimeStoreError:
            raise
        except sqlite3.Error as error:
            logger.exception(
                "local_project_sync_state_read_failed project_id=%s error_type=%s",
                project_id,
                type(error).__name__,
            )
            raise LocalRuntimeStoreError(
                "LOCAL_PROJECT_SYNC_STATE_READ_FAILED", "本机同步状态读取失败。", status_code=500
            ) from error

    def begin_local_project_sync(self, project_id: str, *, allow_pending_retry: bool) -> dict[str, Any]:
        """Atomically claim the local project outbox before any platform write."""
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                if connection.execute(
                    "SELECT 1 FROM local_projects WHERE project_id = ?", (project_id,)
                ).fetchone() is None:
                    raise LocalRuntimeStoreError("LOCAL_PROJECT_NOT_FOUND", "本机项目不存在。", status_code=404)
                current = connection.execute(
                    "SELECT status FROM local_project_sync_state WHERE project_id = ?", (project_id,)
                ).fetchone()
                if current is not None and current["status"] == "pending" and not allow_pending_retry:
                    raise LocalRuntimeStoreError(
                        "LOCAL_SYNC_ALREADY_RUNNING",
                        "此项目已有同步任务或尚未核对的中断任务。",
                        status_code=409,
                    )
                connection.execute(
                    """
                    INSERT INTO local_project_sync_state(project_id, status, error_code, updated_at)
                    VALUES (?, 'pending', NULL, ?)
                    ON CONFLICT(project_id) DO UPDATE SET
                        status = 'pending', error_code = NULL, updated_at = excluded.updated_at
                    """,
                    (project_id, now),
                )
            logger.info(
                "local_project_sync_started project_id=%s resumed_pending=%s",
                project_id,
                current is not None and current["status"] == "pending",
            )
            return self.get_local_project_sync_state(project_id)
        except LocalRuntimeStoreError:
            raise
        except sqlite3.Error as error:
            logger.exception(
                "local_project_sync_start_failed project_id=%s error_type=%s",
                project_id,
                type(error).__name__,
            )
            raise LocalRuntimeStoreError(
                "LOCAL_PROJECT_SYNC_START_FAILED", "本机同步任务无法启动。", status_code=500
            ) from error

    def save_local_project_sync_state(
        self,
        project_id: str,
        *,
        status: str,
        platform_project_id: str | None,
        error_code: str | None,
    ) -> dict[str, Any]:
        allowed = {"pending", "partial", "synced", "failed", "conflict", "needs_review"}
        if status not in allowed:
            raise LocalRuntimeStoreError("LOCAL_SYNC_STATE_INVALID", "本机项目同步状态无效。", status_code=422)
        if platform_project_id is not None and (not platform_project_id.strip() or len(platform_project_id) > 128):
            raise LocalRuntimeStoreError("LOCAL_SYNC_TARGET_INVALID", "平台项目标识无效。", status_code=422)
        if error_code is not None and len(error_code) > 80:
            raise LocalRuntimeStoreError("LOCAL_SYNC_ERROR_INVALID", "同步错误代码无效。", status_code=422)
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                if connection.execute(
                    "SELECT 1 FROM local_projects WHERE project_id = ?", (project_id,)
                ).fetchone() is None:
                    raise LocalRuntimeStoreError("LOCAL_PROJECT_NOT_FOUND", "本机项目不存在。", status_code=404)
                saved_status = status
                if status == "synced":
                    pending_count = connection.execute(
                        """
                        SELECT COUNT(*) AS pending_count
                        FROM local_workflows AS w
                        JOIN local_workflow_drafts AS d ON d.workflow_id = w.workflow_id
                        LEFT JOIN local_workflow_sync_state AS s ON s.workflow_id = w.workflow_id
                        WHERE w.project_id = ? AND (
                            s.workflow_id IS NULL OR s.status != 'synced' OR
                            s.source_revision IS NULL OR s.source_revision != d.revision
                        )
                        """,
                        (project_id,),
                    ).fetchone()["pending_count"]
                    if pending_count:
                        saved_status = "partial"
                connection.execute(
                    """
                    INSERT INTO local_project_sync_state(project_id, status, platform_project_id, error_code, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(project_id) DO UPDATE SET
                        status = excluded.status,
                        platform_project_id = COALESCE(excluded.platform_project_id, local_project_sync_state.platform_project_id),
                        error_code = excluded.error_code,
                        updated_at = excluded.updated_at
                    """,
                    (project_id, saved_status, platform_project_id, error_code, now),
                )
            logger.info(
                "local_project_sync_state_saved project_id=%s status=%s platform_project_id_present=%s error_code=%s",
                project_id,
                saved_status,
                platform_project_id is not None,
                error_code,
            )
            return self.get_local_project_sync_state(project_id)
        except LocalRuntimeStoreError:
            raise
        except sqlite3.Error as error:
            logger.exception(
                "local_project_sync_state_save_failed project_id=%s status=%s error_type=%s",
                project_id,
                status,
                type(error).__name__,
            )
            raise LocalRuntimeStoreError(
                "LOCAL_PROJECT_SYNC_STATE_SAVE_FAILED", "本机项目同步进度保存失败。", status_code=500
            ) from error

    def save_local_workflow_sync_state(
        self,
        project_id: str,
        workflow_id: str,
        *,
        status: str,
        platform_workflow_id: str | None,
        synced_revision: int | None,
        source_revision: int | None,
        error_code: str | None,
    ) -> dict[str, Any]:
        allowed = {"pending", "synced", "failed", "conflict", "needs_review"}
        if status not in allowed or (synced_revision is not None and synced_revision < 1) or (
            source_revision is not None and source_revision < 1
        ):
            raise LocalRuntimeStoreError("LOCAL_SYNC_STATE_INVALID", "本机工作流同步状态无效。", status_code=422)
        if platform_workflow_id is not None and (not platform_workflow_id.strip() or len(platform_workflow_id) > 128):
            raise LocalRuntimeStoreError("LOCAL_SYNC_TARGET_INVALID", "平台工作流标识无效。", status_code=422)
        if error_code is not None and len(error_code) > 80:
            raise LocalRuntimeStoreError("LOCAL_SYNC_ERROR_INVALID", "同步错误代码无效。", status_code=422)
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                workflow = connection.execute(
                    "SELECT project_id FROM local_workflows WHERE workflow_id = ?", (workflow_id,)
                ).fetchone()
                if workflow is None or workflow["project_id"] != project_id:
                    raise LocalRuntimeStoreError("LOCAL_WORKFLOW_NOT_FOUND", "本机工作流不属于此项目。", status_code=404)
                connection.execute(
                    """
                    INSERT INTO local_workflow_sync_state(
                        workflow_id, project_id, status, platform_workflow_id,
                        synced_revision, source_revision, error_code, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(workflow_id) DO UPDATE SET
                        status = excluded.status,
                        platform_workflow_id = COALESCE(excluded.platform_workflow_id, local_workflow_sync_state.platform_workflow_id),
                        synced_revision = COALESCE(excluded.synced_revision, local_workflow_sync_state.synced_revision),
                        source_revision = COALESCE(excluded.source_revision, local_workflow_sync_state.source_revision),
                        error_code = excluded.error_code,
                        updated_at = excluded.updated_at
                    """,
                    (
                        workflow_id,
                        project_id,
                        status,
                        platform_workflow_id,
                        synced_revision,
                        source_revision,
                        error_code,
                        now,
                    ),
                )
            logger.info(
                "local_workflow_sync_state_saved project_id=%s workflow_id=%s status=%s platform_workflow_id_present=%s error_code=%s",
                project_id,
                workflow_id,
                status,
                platform_workflow_id is not None,
                error_code,
            )
            return self.get_local_project_sync_state(project_id)
        except LocalRuntimeStoreError:
            raise
        except sqlite3.Error as error:
            logger.exception(
                "local_workflow_sync_state_save_failed project_id=%s workflow_id=%s status=%s error_type=%s",
                project_id,
                workflow_id,
                status,
                type(error).__name__,
            )
            raise LocalRuntimeStoreError(
                "LOCAL_WORKFLOW_SYNC_STATE_SAVE_FAILED", "本机工作流同步进度保存失败。", status_code=500
            ) from error

    @staticmethod
    def _local_project_payload(row: sqlite3.Row, *, detail: bool = False) -> dict[str, Any]:
        payload = {
            "id": row["project_id"],
            "name": row["name"],
            "domain": row["domain"],
            "role": "operator",
            "visibility": "private",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "description": row["description"],
            "workflow_count": row["workflow_count"],
            "dataset_version_count": 0,
            "recent_run_status": None,
            "last_activity_at": row["updated_at"],
            "source": "local",
            "sync_state": row["sync_state"] if "sync_state" in row.keys() else "local_only",
            "platform_project_id": row["platform_project_id"] if "platform_project_id" in row.keys() else None,
        }
        if detail:
            payload.update({"datasets": [], "pipeline_templates": []})
        return payload

    def create_local_workflow(
        self,
        project_id: str,
        *,
        name: str,
        description: str,
        graph: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_name = name.strip()
        clean_description = description.strip()
        if not clean_name or len(clean_name) > 120 or len(clean_description) > 4000:
            raise LocalRuntimeStoreError("LOCAL_WORKFLOW_INVALID", "本机工作流名称或说明无效。", status_code=422)

        workflow_id = f"local-workflow-{uuid4().hex}"
        now = datetime.now(UTC).isoformat()
        graph_json = _json(graph if graph is not None else {"schema_version": "ict.workflow.v1", "nodes": [], "edges": []})
        if len(graph_json.encode("utf-8")) > 2_000_000:
            raise LocalRuntimeStoreError("WORKFLOW_GRAPH_TOO_LARGE", "工作流图超过本机保存限制。")
        try:
            with self._connection() as connection:
                project = connection.execute(
                    "SELECT project_id FROM local_projects WHERE project_id = ?", (project_id,)
                ).fetchone()
                if project is None:
                    raise LocalRuntimeStoreError("LOCAL_PROJECT_NOT_FOUND", "本机项目不存在。", status_code=404)
                connection.execute(
                    "INSERT INTO local_workflows(workflow_id, project_id, name, description, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (workflow_id, project_id, clean_name, clean_description, now, now),
                )
                connection.execute(
                    "INSERT INTO local_workflow_drafts(workflow_id, revision, graph_json, updated_at) VALUES (?, 1, ?, ?)",
                    (workflow_id, graph_json, now),
                )
                connection.execute(
                    "UPDATE local_project_sync_state SET status = 'partial', error_code = NULL, updated_at = ? "
                    "WHERE project_id = ?",
                    (now, project_id),
                )
                connection.execute("UPDATE local_projects SET updated_at = ? WHERE project_id = ?", (now, project_id))
            logger.info("local_workflow_created project_id=%s workflow_id=%s", project_id, workflow_id)
            return self.get_local_workflow(workflow_id)
        except LocalRuntimeStoreError:
            raise
        except sqlite3.Error as error:
            logger.exception(
                "local_workflow_create_failed project_id=%s workflow_id=%s error_type=%s",
                project_id,
                workflow_id,
                type(error).__name__,
            )
            raise LocalRuntimeStoreError("LOCAL_WORKFLOW_CREATE_FAILED", "本机工作流创建失败。", status_code=500) from error

    def list_local_workflows(self, project_id: str) -> list[dict[str, Any]]:
        try:
            with self._connection() as connection:
                exists = connection.execute(
                    "SELECT project_id FROM local_projects WHERE project_id = ?", (project_id,)
                ).fetchone()
                if exists is None:
                    raise LocalRuntimeStoreError("LOCAL_PROJECT_NOT_FOUND", "本机项目不存在。", status_code=404)
                rows = connection.execute(
                    """
                    SELECT w.workflow_id, w.project_id, NULL AS reproduction_task_id,
                           'project' AS owner_type, w.project_id AS owner_id,
                           w.name, w.description, w.created_at,
                           MAX(w.updated_at, d.updated_at) AS updated_at, d.revision, d.graph_json
                    FROM local_workflows AS w
                    JOIN local_workflow_drafts AS d ON d.workflow_id = w.workflow_id
                    WHERE w.project_id = ?
                    ORDER BY updated_at DESC, w.workflow_id
                    """,
                    (project_id,),
                ).fetchall()
            return [self._local_workflow_payload(row) for row in rows]
        except LocalRuntimeStoreError:
            raise
        except sqlite3.Error as error:
            logger.exception("local_workflow_list_failed project_id=%s error_type=%s", project_id, type(error).__name__)
            raise LocalRuntimeStoreError("LOCAL_WORKFLOW_LIST_FAILED", "本机工作流目录读取失败。", status_code=500) from error

    def get_local_workflow(self, workflow_id: str) -> dict[str, Any]:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM (
                        SELECT w.workflow_id, w.project_id, NULL AS reproduction_task_id,
                               'project' AS owner_type, w.project_id AS owner_id,
                               w.name, w.description, w.created_at,
                               MAX(w.updated_at, d.updated_at) AS updated_at, d.revision, d.graph_json
                        FROM local_workflows AS w
                        JOIN local_workflow_drafts AS d ON d.workflow_id = w.workflow_id
                        UNION ALL
                        SELECT w.workflow_id, NULL AS project_id, w.reproduction_task_id,
                               'reproduction' AS owner_type, w.reproduction_task_id AS owner_id,
                               w.name, w.description, w.created_at,
                               MAX(w.updated_at, d.updated_at) AS updated_at, d.revision, d.graph_json
                        FROM local_reproduction_workflows AS w
                        JOIN local_workflow_drafts AS d ON d.workflow_id = w.workflow_id
                    ) AS workflow_rows
                    WHERE workflow_id = ?
                    """,
                    (workflow_id,),
                ).fetchone()
            if row is None:
                raise LocalRuntimeStoreError("LOCAL_WORKFLOW_NOT_FOUND", "本机工作流不存在。", status_code=404)
            return self._local_workflow_payload(row, detail=True)
        except LocalRuntimeStoreError:
            raise
        except (sqlite3.Error, json.JSONDecodeError) as error:
            logger.exception("local_workflow_read_failed workflow_id=%s error_type=%s", workflow_id, type(error).__name__)
            raise LocalRuntimeStoreError("LOCAL_WORKFLOW_READ_FAILED", "本机工作流读取失败。", status_code=500) from error

    @staticmethod
    def _local_workflow_payload(row: sqlite3.Row, *, detail: bool = False) -> dict[str, Any]:
        payload = {
            "id": row["workflow_id"],
            "workspace_id": "local",
            "owner_type": row["owner_type"],
            "owner_id": row["owner_id"],
            "project_id": row["project_id"],
            "reproduction_task_id": row["reproduction_task_id"],
            "name": row["name"],
            "description": row["description"],
            "revision": row["revision"],
            "current_version": 0,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "source": "local",
            "sync_state": "local_only",
        }
        if detail:
            payload.update({"graph": json.loads(row["graph_json"]), "can_edit": True})
        return payload

    def save_workflow_draft(
        self,
        workflow_id: str,
        *,
        revision: int,
        graph: dict[str, Any],
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        if not workflow_id or len(workflow_id) > 128 or revision < 1:
            raise LocalRuntimeStoreError("LOCAL_WORKFLOW_INVALID", "本机工作流标识或修订号无效。")
        try:
            graph_json = _json(graph)
            if len(graph_json.encode("utf-8")) > 2_000_000:
                raise LocalRuntimeStoreError("WORKFLOW_GRAPH_TOO_LARGE", "工作流图超过本机保存限制。")
            with self._connection() as connection:
                current = connection.execute(
                    "SELECT revision FROM local_workflow_drafts WHERE workflow_id = ?",
                    (workflow_id,),
                ).fetchone()
                if current is not None and revision <= current["revision"]:
                    raise LocalRuntimeStoreError(
                        "LOCAL_WORKFLOW_REVISION_CONFLICT",
                        "本机缓存中的工作流修订号更新，请重新同步后再保存。",
                        status_code=409,
                    )
                connection.execute(
                    """
                    INSERT INTO local_workflow_drafts(workflow_id, revision, graph_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(workflow_id) DO UPDATE SET
                        revision = excluded.revision,
                        graph_json = excluded.graph_json,
                        updated_at = excluded.updated_at
                    """,
                    (workflow_id, revision, graph_json, datetime.now(UTC).isoformat()),
                )
                metadata = connection.execute(
                    "SELECT project_id, name, description FROM local_workflows WHERE workflow_id = ?",
                    (workflow_id,),
                ).fetchone()
                if metadata is None:
                    reproduction_metadata = connection.execute(
                        """
                        SELECT reproduction_task_id, name, description
                        FROM local_reproduction_workflows
                        WHERE workflow_id = ?
                        """,
                        (workflow_id,),
                    ).fetchone()
                else:
                    reproduction_metadata = None
                if metadata is not None:
                    updated_at = datetime.now(UTC).isoformat()
                    connection.execute(
                        "UPDATE local_workflows SET name = ?, description = ?, updated_at = ? WHERE workflow_id = ?",
                        (
                            name.strip() if name is not None else metadata["name"],
                            description.strip() if description is not None else metadata["description"],
                            updated_at,
                            workflow_id,
                        ),
                    )
                    connection.execute(
                        "UPDATE local_projects SET updated_at = ? WHERE project_id = ?",
                        (updated_at, metadata["project_id"]),
                    )
                    linked_workflow = connection.execute(
                        "SELECT platform_workflow_id FROM local_workflow_sync_state WHERE workflow_id = ?",
                        (workflow_id,),
                    ).fetchone()
                    if linked_workflow is not None and linked_workflow["platform_workflow_id"]:
                        connection.execute(
                            "UPDATE local_workflow_sync_state SET status = 'pending', error_code = NULL, updated_at = ? "
                            "WHERE workflow_id = ?",
                            (updated_at, workflow_id),
                        )
                        connection.execute(
                            "UPDATE local_project_sync_state SET status = 'partial', error_code = NULL, updated_at = ? "
                            "WHERE project_id = ?",
                            (updated_at, metadata["project_id"]),
                        )
                elif reproduction_metadata is not None:
                    updated_at = datetime.now(UTC).isoformat()
                    connection.execute(
                        """
                        UPDATE local_reproduction_workflows
                        SET name = ?, description = ?, updated_at = ?
                        WHERE workflow_id = ?
                        """,
                        (
                            name.strip() if name is not None else reproduction_metadata["name"],
                            description.strip() if description is not None else reproduction_metadata["description"],
                            updated_at,
                            workflow_id,
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE local_reproduction_tasks
                        SET status = 'ready_to_run', updated_at = ?
                        WHERE task_id = ?
                        """,
                        (updated_at, reproduction_metadata["reproduction_task_id"]),
                    )
            return {"workflow_id": workflow_id, "revision": revision}
        except LocalRuntimeStoreError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as error:
            logger.exception("local_workflow_draft_save_failed workflow_id=%s", workflow_id)
            raise LocalRuntimeStoreError("LOCAL_WORKFLOW_SAVE_FAILED", "本机工作流保存失败。", status_code=500) from error

    def create_run(
        self,
        workflow_id: str,
        *,
        target_node_ids: list[str],
        validate_plan: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        try:
            with self._connection() as connection:
                draft = connection.execute(
                    "SELECT revision, graph_json FROM local_workflow_drafts WHERE workflow_id = ?",
                    (workflow_id,),
                ).fetchone()
                if draft is None:
                    raise LocalRuntimeStoreError("LOCAL_WORKFLOW_NOT_FOUND", "本机没有已保存的工作流。", status_code=404)
                graph = json.loads(draft["graph_json"])
                plan = compile_execution_plan(graph, target_node_ids=target_node_ids)
                if validate_plan is not None:
                    validate_plan(plan)
                run_id = str(uuid4())
                now = datetime.now(UTC).isoformat()
                connection.execute(
                    """
                    INSERT INTO local_workflow_runs(
                        run_id, workflow_id, plan_hash, execution_plan_json,
                        target_node_ids_json, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'queued', ?)
                    """,
                    (
                        run_id,
                        workflow_id,
                        plan["plan_hash"],
                        _json(plan),
                        _json(plan["target_node_ids"]),
                        now,
                    ),
                )
                for node in plan["nodes"]:
                    connection.execute(
                        """
                        INSERT INTO local_workflow_node_runs(
                            run_id, node_id, component_id, status, updated_at
                        ) VALUES (?, ?, ?, 'WAITING', ?)
                        """,
                        (run_id, node["id"], node["component_id"], now),
                    )
                connection.execute(
                    """
                    INSERT INTO local_workflow_run_events(run_id, sequence, status, occurred_at)
                    VALUES (?, 1, 'QUEUED', ?)
                    """,
                    (run_id, now),
                )
                reproduction = connection.execute(
                    """
                    SELECT reproduction_task_id
                    FROM local_reproduction_workflows
                    WHERE workflow_id = ?
                    """,
                    (workflow_id,),
                ).fetchone()
                if reproduction is not None:
                    connection.execute(
                        "UPDATE local_reproduction_tasks SET status = 'running', updated_at = ? WHERE task_id = ?",
                        (now, reproduction["reproduction_task_id"]),
                    )
            logger.info(
                "local_workflow_run_created run_id=%s workflow_id=%s plan_hash=%s target_count=%s",
                run_id,
                workflow_id,
                plan["plan_hash"],
                len(plan["target_node_ids"]),
            )
            return {"run_id": run_id, "workflow_id": workflow_id, "plan": plan}
        except LocalRuntimeStoreError:
            raise
        except sqlite3.Error as error:
            logger.exception("local_workflow_run_create_failed workflow_id=%s", workflow_id)
            raise LocalRuntimeStoreError("LOCAL_RUN_CREATE_FAILED", "本机运行创建失败。", status_code=500) from error

    def get_recovery_snapshot(self, run_id: str) -> dict[str, Any]:
        """Read a restart-interrupted run and its durably captured node outputs."""
        try:
            with self._connection() as connection:
                run = connection.execute(
                    "SELECT * FROM local_workflow_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if run is None:
                    raise LocalRuntimeStoreError("LOCAL_RUN_NOT_FOUND", "本机运行记录不存在。", status_code=404)
                if run["status"] != "failed" or run["error_code"] != "LOCAL_WORKER_RESTARTED":
                    raise LocalRuntimeStoreError(
                        "LOCAL_RUN_NOT_RECOVERABLE",
                        "只有 Runtime 重启中断的本机运行可以恢复。",
                        status_code=409,
                    )
                node_rows = connection.execute(
                    "SELECT node_id, status, output_json FROM local_workflow_node_runs WHERE run_id = ?",
                    (run_id,),
                ).fetchall()
            outputs: dict[str, Any] = {}
            for node in node_rows:
                if node["status"] not in {"SUCCEEDED", "CACHED", "RESTORED"} or node["output_json"] is None:
                    continue
                try:
                    outputs[node["node_id"]] = json.loads(node["output_json"])
                except json.JSONDecodeError:
                    logger.warning("local_workflow_recovery_output_invalid run_id=%s node_id=%s", run_id, node["node_id"])
            plan = json.loads(run["execution_plan_json"])
            if not isinstance(plan, dict) or plan.get("plan_hash") != run["plan_hash"]:
                raise LocalRuntimeStoreError(
                    "LOCAL_RUN_PLAN_INVALID", "中断运行的执行计划不完整，无法恢复。", status_code=409
                )
            return {
                "run_id": run["run_id"],
                "workflow_id": run["workflow_id"],
                "plan_hash": run["plan_hash"],
                "plan": plan,
                "outputs": outputs,
            }
        except LocalRuntimeStoreError:
            raise
        except (sqlite3.Error, json.JSONDecodeError) as error:
            logger.exception("local_workflow_recovery_snapshot_failed run_id=%s", run_id)
            raise LocalRuntimeStoreError(
                "LOCAL_RUN_READ_FAILED", "中断运行记录读取失败。", status_code=500
            ) from error

    def create_recovery_run(
        self,
        run_id: str,
        *,
        restored_outputs: dict[str, Any],
        validate_plan: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Create one child run from a frozen interrupted plan and validated outputs."""
        try:
            with self._connection() as connection:
                # Serialize duplicate clicks so two clients cannot create active children together.
                connection.execute("BEGIN IMMEDIATE")
                parent = connection.execute(
                    "SELECT * FROM local_workflow_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if parent is None:
                    raise LocalRuntimeStoreError("LOCAL_RUN_NOT_FOUND", "本机运行记录不存在。", status_code=404)
                if parent["status"] != "failed" or parent["error_code"] != "LOCAL_WORKER_RESTARTED":
                    raise LocalRuntimeStoreError(
                        "LOCAL_RUN_NOT_RECOVERABLE",
                        "只有 Runtime 重启中断的本机运行可以恢复。",
                        status_code=409,
                    )
                active_child = connection.execute(
                    """SELECT run_id FROM local_workflow_runs
                       WHERE recovered_from_run_id = ?
                         AND status IN ('queued', 'running', 'waiting_external')
                       ORDER BY created_at DESC LIMIT 1""",
                    (run_id,),
                ).fetchone()
                if active_child is not None:
                    raise LocalRuntimeStoreError(
                        "LOCAL_RUN_RECOVERY_ACTIVE",
                        "此中断运行已有恢复任务正在执行。",
                        status_code=409,
                    )
                plan = json.loads(parent["execution_plan_json"])
                if not isinstance(plan, dict) or plan.get("plan_hash") != parent["plan_hash"]:
                    raise LocalRuntimeStoreError(
                        "LOCAL_RUN_PLAN_INVALID", "中断运行的执行计划不完整，无法恢复。", status_code=409
                    )
                plan_node_ids = {node.get("id") for node in plan.get("nodes", []) if isinstance(node, dict)}
                if set(restored_outputs) - plan_node_ids:
                    raise LocalRuntimeStoreError(
                        "LOCAL_RUN_RECOVERY_OUTPUT_INVALID", "恢复结果包含不属于执行计划的节点。", status_code=409
                    )
                if validate_plan is not None:
                    validate_plan(plan)

                child_run_id = str(uuid4())
                now = datetime.now(UTC).isoformat()
                connection.execute(
                    """INSERT INTO local_workflow_runs(
                           run_id, workflow_id, plan_hash, execution_plan_json,
                           target_node_ids_json, status, created_at, recovered_from_run_id
                       ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)""",
                    (
                        child_run_id,
                        parent["workflow_id"],
                        parent["plan_hash"],
                        parent["execution_plan_json"],
                        parent["target_node_ids_json"],
                        now,
                        run_id,
                    ),
                )
                for node in plan["nodes"]:
                    node_id = node["id"]
                    output = restored_outputs.get(node_id)
                    status = "RESTORED" if node_id in restored_outputs else "WAITING"
                    connection.execute(
                        """INSERT INTO local_workflow_node_runs(
                               run_id, node_id, component_id, status, output_json, updated_at
                           ) VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            child_run_id,
                            node_id,
                            node["component_id"],
                            status,
                            _json(output) if node_id in restored_outputs else None,
                            now,
                        ),
                    )
                connection.execute(
                    """INSERT INTO local_workflow_run_events(run_id, sequence, status, occurred_at)
                       VALUES (?, 1, 'QUEUED', ?)""",
                    (child_run_id, now),
                )
                event_sequence = 1
                for node_id in plan["node_order"]:
                    if node_id not in restored_outputs:
                        continue
                    event_sequence += 1
                    connection.execute(
                        """INSERT INTO local_workflow_run_events(
                               run_id, sequence, node_id, status, occurred_at
                           ) VALUES (?, ?, ?, 'RESTORED', ?)""",
                        (child_run_id, event_sequence, node_id, now),
                    )
                reproduction = connection.execute(
                    "SELECT reproduction_task_id FROM local_reproduction_workflows WHERE workflow_id = ?",
                    (parent["workflow_id"],),
                ).fetchone()
                if reproduction is not None:
                    connection.execute(
                        "UPDATE local_reproduction_tasks SET status = 'running', updated_at = ? WHERE task_id = ?",
                        (now, reproduction["reproduction_task_id"]),
                    )
            logger.info(
                "local_workflow_run_recovery_created run_id=%s recovered_from_run_id=%s plan_hash=%s restored_node_count=%s rerun_node_count=%s",
                child_run_id,
                run_id,
                parent["plan_hash"],
                len(restored_outputs),
                len(plan["nodes"]) - len(restored_outputs),
            )
            return {
                "run_id": child_run_id,
                "workflow_id": parent["workflow_id"],
                "plan": plan,
                "recovered_from_run_id": run_id,
                "restored_node_ids": [node_id for node_id in plan["node_order"] if node_id in restored_outputs],
            }
        except LocalRuntimeStoreError:
            raise
        except (sqlite3.Error, json.JSONDecodeError, TypeError, ValueError) as error:
            logger.exception("local_workflow_run_recovery_create_failed run_id=%s", run_id)
            raise LocalRuntimeStoreError(
                "LOCAL_RUN_RECOVERY_FAILED", "本机恢复运行创建失败。", status_code=500
            ) from error

    def get_cached_node_output(self, signature_hash: str) -> Any | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT output_json FROM local_node_output_cache WHERE signature_hash = ?",
                    (signature_hash,),
                ).fetchone()
            if row is None:
                return None
            return json.loads(row["output_json"])
        except (sqlite3.Error, json.JSONDecodeError):
            logger.exception("local_node_cache_read_failed signature_hash=%s", signature_hash)
            try:
                with self._connection() as connection:
                    connection.execute(
                        "DELETE FROM local_node_output_cache WHERE signature_hash = ?",
                        (signature_hash,),
                    )
            except sqlite3.Error:
                logger.exception("local_node_cache_corrupt_entry_delete_failed signature_hash=%s", signature_hash)
            return None

    def store_cached_node_output(self, signature_hash: str, output: Any) -> None:
        if len(signature_hash) != 64:
            raise LocalRuntimeStoreError("CACHE_SIGNATURE_INVALID", "本机缓存签名无效。")
        try:
            encoded = _json(output)
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO local_node_output_cache(signature_hash, output_json, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(signature_hash) DO UPDATE SET
                        output_json = excluded.output_json,
                        created_at = excluded.created_at
                    """,
                    (signature_hash, encoded, datetime.now(UTC).isoformat()),
                )
        except (sqlite3.Error, TypeError, ValueError):
            logger.exception("local_node_cache_write_failed signature_hash=%s", signature_hash)
            raise LocalRuntimeStoreError("CACHE_WRITE_FAILED", "本机节点缓存写入失败。", status_code=500)

    def get_workflow_draft(self, workflow_id: str) -> dict[str, Any]:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT revision, graph_json FROM local_workflow_drafts WHERE workflow_id = ?",
                    (workflow_id,),
                ).fetchone()
            if row is None:
                raise LocalRuntimeStoreError(
                    "LOCAL_WORKFLOW_NOT_FOUND",
                    "本机没有已保存的工作流。",
                    status_code=404,
                )
            return {"revision": row["revision"], "graph": json.loads(row["graph_json"])}
        except LocalRuntimeStoreError:
            raise
        except (sqlite3.Error, json.JSONDecodeError) as error:
            logger.exception("local_workflow_draft_read_failed workflow_id=%s", workflow_id)
            raise LocalRuntimeStoreError(
                "LOCAL_WORKFLOW_READ_FAILED",
                "本机工作流读取失败。",
                status_code=500,
            ) from error

    def set_run_status(self, run_id: str, status: str, *, error_code: str | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT status, workflow_id FROM local_workflow_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if row is None:
                    raise LocalRuntimeStoreError("LOCAL_RUN_NOT_FOUND", "本机运行记录不存在。", status_code=404)
                started_at = now if status == "running" and row["status"] == "queued" else None
                finished_at = now if status in {"succeeded", "partially_succeeded", "failed", "cancelled"} else None
                connection.execute(
                    """
                    UPDATE local_workflow_runs
                    SET status = ?, error_code = ?,
                        started_at = COALESCE(started_at, ?),
                        finished_at = COALESCE(?, finished_at)
                    WHERE run_id = ?
                    """,
                    (status, error_code, started_at, finished_at, run_id),
                )
                if status == "failed":
                    connection.execute(
                        """
                        UPDATE local_workflow_node_runs
                        SET status = 'FAILED', error_code = ?, updated_at = ?
                        WHERE run_id = ? AND status IN ('WAITING', 'READY', 'RUNNING', 'WAITING_EXTERNAL')
                        """,
                        (error_code or "LOCAL_WORKER_FAILED", now, run_id),
                    )
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence "
                    "FROM local_workflow_run_events WHERE run_id = ?",
                    (run_id,),
                ).fetchone()["next_sequence"]
                connection.execute(
                    """
                    INSERT INTO local_workflow_run_events(run_id, sequence, status, error_code, occurred_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (run_id, sequence, status.upper(), error_code, now),
                )
                if status in {"failed", "cancelled"}:
                    reproduction = connection.execute(
                        """
                        SELECT reproduction_task_id
                        FROM local_reproduction_workflows
                        WHERE workflow_id = ?
                        """,
                        (row["workflow_id"],),
                    ).fetchone()
                    if reproduction is not None:
                        connection.execute(
                            """
                            UPDATE local_reproduction_tasks
                            SET status = 'ready_to_run', updated_at = ?
                            WHERE task_id = ?
                            """,
                            (now, reproduction["reproduction_task_id"]),
                        )
        except LocalRuntimeStoreError:
            raise
        except sqlite3.Error as error:
            logger.exception("local_workflow_run_status_write_failed run_id=%s", run_id)
            raise LocalRuntimeStoreError("LOCAL_RUN_PERSISTENCE_FAILED", "本机运行状态保存失败。", status_code=500) from error

    def record_node_event(self, run_id: str, event: dict[str, Any]) -> None:
        now = str(event.get("occurred_at") or datetime.now(UTC).isoformat())
        status = str(event.get("status") or "FAILED")
        node_id = event.get("node_id")
        error_code = event.get("error_code")
        run_status = "waiting_external" if status == "WAITING_EXTERNAL" else "running"
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    UPDATE local_workflow_node_runs
                    SET status = ?, error_code = ?, updated_at = ?
                    WHERE run_id = ? AND node_id = ?
                    """,
                    (status, error_code, now, run_id, node_id),
                )
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence "
                    "FROM local_workflow_run_events WHERE run_id = ?",
                    (run_id,),
                ).fetchone()["next_sequence"]
                connection.execute(
                    """
                    INSERT INTO local_workflow_run_events(
                        run_id, sequence, node_id, status, error_code, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, sequence, node_id, status, error_code, now),
                )
                connection.execute(
                    "UPDATE local_workflow_runs SET status = ? WHERE run_id = ?",
                    (run_status, run_id),
                )
        except sqlite3.Error as error:
            logger.exception(
                "local_workflow_node_event_persist_failed run_id=%s node_id=%s",
                run_id,
                node_id,
            )
            raise LocalRuntimeStoreError("LOCAL_RUN_PERSISTENCE_FAILED", "本机节点状态保存失败。", status_code=500) from error

    def record_node_result(self, run_id: str, event: dict[str, Any]) -> None:
        """Atomically persist a successful node output and its terminal event."""
        now = str(event.get("occurred_at") or datetime.now(UTC).isoformat())
        node_id = event.get("node_id")
        status = str(event.get("status") or "")
        if status not in {"SUCCEEDED", "CACHED"} or not isinstance(node_id, str) or not node_id:
            raise LocalRuntimeStoreError("LOCAL_NODE_RESULT_INVALID", "本机节点完成记录无效。", status_code=422)
        try:
            output_json = _json(event.get("output"))
            with self._connection() as connection:
                updated = connection.execute(
                    """UPDATE local_workflow_node_runs
                       SET status = ?, error_code = NULL, output_json = ?, updated_at = ?
                       WHERE run_id = ? AND node_id = ?""",
                    (status, output_json, now, run_id, node_id),
                )
                if updated.rowcount != 1:
                    raise LocalRuntimeStoreError(
                        "LOCAL_NODE_RESULT_NOT_FOUND", "本机节点运行记录不存在。", status_code=409
                    )
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence "
                    "FROM local_workflow_run_events WHERE run_id = ?",
                    (run_id,),
                ).fetchone()["next_sequence"]
                connection.execute(
                    """INSERT INTO local_workflow_run_events(
                           run_id, sequence, node_id, status, occurred_at
                       ) VALUES (?, ?, ?, ?, ?)""",
                    (run_id, sequence, node_id, status, now),
                )
                connection.execute(
                    "UPDATE local_workflow_runs SET status = 'running' WHERE run_id = ?",
                    (run_id,),
                )
        except LocalRuntimeStoreError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as error:
            logger.exception(
                "local_workflow_node_result_persist_failed run_id=%s node_id=%s",
                run_id,
                node_id,
            )
            raise LocalRuntimeStoreError(
                "LOCAL_RUN_PERSISTENCE_FAILED", "本机节点产物保存失败。", status_code=500
            ) from error

    def finish_run(self, run_id: str, result: dict[str, Any]) -> None:
        status_map = {
            "SUCCEEDED": "succeeded",
            "PARTIALLY_SUCCEEDED": "partially_succeeded",
            "FAILED": "failed",
            "CANCELLED": "cancelled",
        }
        status = status_map.get(result.get("status"), "failed")
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                run = connection.execute(
                    "SELECT workflow_id FROM local_workflow_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if run is None:
                    raise LocalRuntimeStoreError("LOCAL_RUN_NOT_FOUND", "本机运行记录不存在。", status_code=404)
                for node_run in result.get("node_runs", []):
                    connection.execute(
                        """
                        UPDATE local_workflow_node_runs
                        SET status = ?, error_code = ?, output_json = ?, updated_at = ?
                        WHERE run_id = ? AND node_id = ?
                        """,
                        (
                            node_run["status"],
                            node_run.get("error_code"),
                            _json(node_run.get("output")) if node_run.get("output") is not None else None,
                            now,
                            run_id,
                            node_run["node_id"],
                        ),
                    )
                connection.execute(
                    "UPDATE local_workflow_runs SET status = ?, finished_at = ? WHERE run_id = ?",
                    (status, now, run_id),
                )
                reproduction = connection.execute(
                    """
                    SELECT reproduction_task_id
                    FROM local_reproduction_workflows
                    WHERE workflow_id = ?
                    """,
                    (run["workflow_id"],),
                ).fetchone()
                if reproduction is not None:
                    task_status = "awaiting_review" if status in {"succeeded", "partially_succeeded"} else "ready_to_run"
                    connection.execute(
                        "UPDATE local_reproduction_tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                        (task_status, now, reproduction["reproduction_task_id"]),
                    )
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence "
                    "FROM local_workflow_run_events WHERE run_id = ?",
                    (run_id,),
                ).fetchone()["next_sequence"]
                connection.execute(
                    """
                    INSERT INTO local_workflow_run_events(run_id, sequence, status, occurred_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (run_id, sequence, status.upper(), now),
                )
        except (sqlite3.Error, TypeError, ValueError) as error:
            logger.exception("local_workflow_run_finish_persist_failed run_id=%s", run_id)
            raise LocalRuntimeStoreError("LOCAL_RUN_PERSISTENCE_FAILED", "本机运行结果保存失败。", status_code=500) from error

    def get_run(self, run_id: str) -> dict[str, Any]:
        try:
            with self._connection() as connection:
                run = connection.execute(
                    "SELECT * FROM local_workflow_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if run is None:
                    raise LocalRuntimeStoreError("LOCAL_RUN_NOT_FOUND", "本机运行记录不存在。", status_code=404)
                node_rows = connection.execute(
                    "SELECT * FROM local_workflow_node_runs WHERE run_id = ? ORDER BY rowid",
                    (run_id,),
                ).fetchall()
                event_rows = connection.execute(
                    "SELECT * FROM local_workflow_run_events WHERE run_id = ? ORDER BY sequence",
                    (run_id,),
                ).fetchall()
            return {
                "run_id": run["run_id"],
                "workflow_id": run["workflow_id"],
                "status": run["status"],
                "plan_hash": run["plan_hash"],
                "target_node_ids": json.loads(run["target_node_ids_json"]),
                "execution_plan": json.loads(run["execution_plan_json"]),
                "error_code": run["error_code"],
                "recovered_from_run_id": run["recovered_from_run_id"],
                "created_at": run["created_at"],
                "started_at": run["started_at"],
                "finished_at": run["finished_at"],
                "node_runs": [
                    {
                        "node_id": row["node_id"],
                        "component_id": row["component_id"],
                        "status": row["status"],
                        "error_code": row["error_code"],
                        "output": json.loads(row["output_json"]) if row["output_json"] else None,
                        "updated_at": row["updated_at"],
                    }
                    for row in node_rows
                ],
                "events": [
                    {
                        "sequence": row["sequence"],
                        "node_id": row["node_id"],
                        "status": row["status"],
                        "error_code": row["error_code"],
                        "occurred_at": row["occurred_at"],
                    }
                    for row in event_rows
                ],
            }
        except LocalRuntimeStoreError:
            raise
        except (sqlite3.Error, json.JSONDecodeError) as error:
            logger.exception("local_workflow_run_read_failed run_id=%s", run_id)
            raise LocalRuntimeStoreError("LOCAL_RUN_READ_FAILED", "本机运行记录读取失败。", status_code=500) from error

    def list_runs(self, workflow_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent run summaries scoped to one workflow for its editor history."""
        bounded_limit = max(1, min(int(limit), 100))
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """
                    SELECT run_id, workflow_id, status, plan_hash, target_node_ids_json,
                           error_code, recovered_from_run_id, created_at, started_at, finished_at
                    FROM local_workflow_runs
                    WHERE workflow_id = ?
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT ?
                    """,
                    (workflow_id, bounded_limit),
                ).fetchall()
            return [
                {
                    "run_id": row["run_id"],
                    "workflow_id": row["workflow_id"],
                    "status": row["status"],
                    "plan_hash": row["plan_hash"],
                    "target_node_ids": json.loads(row["target_node_ids_json"]),
                    "error_code": row["error_code"],
                    "recovered_from_run_id": row["recovered_from_run_id"],
                    "created_at": row["created_at"],
                    "started_at": row["started_at"],
                    "finished_at": row["finished_at"],
                }
                for row in rows
            ]
        except (sqlite3.Error, json.JSONDecodeError, TypeError, ValueError) as error:
            logger.exception("local_workflow_run_list_failed workflow_id=%s", workflow_id)
            raise LocalRuntimeStoreError(
                "LOCAL_RUN_READ_FAILED", "本机运行历史读取失败。", status_code=500
            ) from error

    def get_plan(self, run_id: str) -> dict[str, Any]:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT execution_plan_json FROM local_workflow_runs WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
            if row is None:
                raise LocalRuntimeStoreError("LOCAL_RUN_NOT_FOUND", "本机运行记录不存在。", status_code=404)
            return json.loads(row["execution_plan_json"])
        except LocalRuntimeStoreError:
            raise
        except (sqlite3.Error, json.JSONDecodeError) as error:
            logger.exception("local_workflow_plan_read_failed run_id=%s", run_id)
            raise LocalRuntimeStoreError("LOCAL_RUN_READ_FAILED", "本机运行计划读取失败。", status_code=500) from error

    def mark_incomplete_runs_failed(self) -> int:
        """Mark unfinished work as failed after a local runtime process restart."""
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    "SELECT run_id FROM local_workflow_runs WHERE status IN ('queued', 'running', 'waiting_external')"
                ).fetchall()
                for row in rows:
                    run_id = row["run_id"]
                    connection.execute(
                        """UPDATE local_workflow_runs SET status = 'failed', error_code = 'LOCAL_WORKER_RESTARTED',
                           finished_at = ? WHERE run_id = ?""",
                        (now, run_id),
                    )
                    connection.execute(
                        """UPDATE local_workflow_node_runs SET status = 'FAILED',
                           error_code = 'LOCAL_WORKER_RESTARTED', updated_at = ?
                           WHERE run_id = ? AND status IN ('WAITING', 'READY', 'RUNNING', 'WAITING_EXTERNAL')""",
                        (now, run_id),
                    )
                    sequence = connection.execute(
                        "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence "
                        "FROM local_workflow_run_events WHERE run_id = ?",
                        (run_id,),
                    ).fetchone()["next_sequence"]
                    connection.execute(
                        "INSERT INTO local_workflow_run_events(run_id, sequence, status, error_code, occurred_at) "
                        "VALUES (?, ?, 'FAILED', 'LOCAL_WORKER_RESTARTED', ?)",
                        (run_id, sequence, now),
                    )
                    interrupted_workflow = connection.execute(
                        """SELECT reproduction_task_id
                           FROM local_reproduction_workflows
                           WHERE workflow_id = (
                               SELECT workflow_id FROM local_workflow_runs WHERE run_id = ?
                           )""",
                        (run_id,),
                    ).fetchone()
                    if interrupted_workflow is not None:
                        connection.execute(
                            "UPDATE local_reproduction_tasks SET status = 'ready_to_run', updated_at = ? "
                            "WHERE task_id = ?",
                            (now, interrupted_workflow["reproduction_task_id"]),
                        )
            if rows:
                logger.error("local_runtime_recovered_incomplete_runs count=%s", len(rows))
            return len(rows)
        except sqlite3.Error as error:
            logger.exception("local_runtime_recovery_failed error_type=%s", type(error).__name__)
            raise LocalRuntimeStoreError("LOCAL_STORE_UNAVAILABLE", "本机运行恢复检查失败。", status_code=503) from error
