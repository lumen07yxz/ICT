"""Celery wiring tests verify bounded, ID-only queue dispatch without Redis."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class WorkerDispatchTests(unittest.TestCase):
    def test_dispatch_publishes_only_the_run_id_with_bounded_worker_settings(self) -> None:
        from app import worker

        run_id = uuid4()
        with patch.object(worker.execute_synthetic_smoke, "apply_async") as send:
            worker.enqueue_run(run_id)

        send.assert_called_once_with(args=[str(run_id)], task_id=f"run-{run_id}")
        self.assertEqual(worker.celery_app.conf.task_soft_time_limit, 25)
        self.assertEqual(worker.celery_app.conf.task_time_limit, 30)
        self.assertEqual(worker.celery_app.conf.worker_prefetch_multiplier, 1)
        self.assertTrue(worker.celery_app.conf.task_ignore_result)


if __name__ == "__main__":
    unittest.main()
