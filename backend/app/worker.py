"""Celery entry point for the short deterministic synthetic integration job."""

from __future__ import annotations

import os
from uuid import UUID

from celery import Celery
from sqlalchemy.orm import sessionmaker

from app.db.session import build_engine
from app.services.runs import execute_smoke_run
from app.services.template_registry import DEMO_PIPELINE_TEMPLATE, load_template_manifest


BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
_WORKER_TEMPLATE = load_template_manifest(DEMO_PIPELINE_TEMPLATE)
_RESOURCE_LIMITS = _WORKER_TEMPLATE.manifest.resource_limits
celery_app = Celery("ict_research", broker=BROKER_URL)
celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    task_ignore_result=True,
    task_acks_late=False,
    task_soft_time_limit=_RESOURCE_LIMITS.soft_timeout_seconds,
    task_time_limit=_RESOURCE_LIMITS.hard_timeout_seconds,
    worker_concurrency=_RESOURCE_LIMITS.max_concurrent_runs,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="ict.execute_synthetic_smoke", ignore_result=True)
def execute_synthetic_smoke(run_id: str) -> bool:
    """Open a worker-local database connection and execute only the fixed smoke task."""
    safe_run_id = UUID(run_id)
    engine = build_engine()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        return execute_smoke_run(factory, safe_run_id)
    finally:
        engine.dispose()


def enqueue_run(run_id: UUID) -> None:
    """Publish a run identifier only; task configuration remains in the database."""
    execute_synthetic_smoke.apply_async(args=[str(run_id)], task_id=f"run-{run_id}")
