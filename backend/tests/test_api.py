"""W0 只读接口的行为验收，使用合成项目且不需要云密钥。"""

import asyncio
import logging
import sys
import unittest
from pathlib import Path

import httpx


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class DemoApiTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from app.main import app
        except ModuleNotFoundError as exc:
            self.fail(f"W0 API 尚未实现: {exc}")
        self.app = app

    def get(self, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.get(path, headers=headers)

        return asyncio.run(send())

    def test_health_reports_live_without_claiming_research_readiness(self) -> None:
        response = self.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "mode": "synthetic_demo"})
        self.assertTrue(response.headers.get("x-request-id"))

    def test_overview_exposes_only_synthetic_demo_catalog(self) -> None:
        response = self.get("/api/v1/demo/projects/demo-research/overview")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["project_id"], "demo-research")
        self.assertEqual(payload["data_status"], "synthetic_only")
        self.assertFalse(payload["research_ready"])
        self.assertEqual(payload["dataset_versions"], ["dataset-synthetic-v1"])
        self.assertEqual(payload["pipeline_templates"], ["research-smoke-v1"])
        self.assertEqual(payload["recent_public_runs"], [])

    def test_unknown_project_is_rejected_without_reflecting_its_identifier(self) -> None:
        with self.assertLogs("ict.api", level="INFO") as captured:
            response = self.get("/api/v1/demo/projects/private-123/overview")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "PROJECT_NOT_ALLOWED")
        self.assertEqual(payload["error"]["request_id"], response.headers["x-request-id"])
        self.assertNotIn("private-123", response.text)
        self.assertIn("error_code=PROJECT_NOT_ALLOWED", "\n".join(captured.output))
        self.assertNotIn("private-123", "\n".join(captured.output))

    def test_auth_header_is_not_written_to_request_logs(self) -> None:
        secret = "test-only-secret-value"

        with self.assertLogs("ict.api", level="INFO") as captured:
            response = self.get("/health", headers={"authorization": f"Bearer {secret}"})

        self.assertEqual(response.status_code, 200)
        joined = "\n".join(captured.output)
        self.assertIn("request_id=", joined)
        self.assertIn("status=200", joined)
        self.assertNotIn(secret, joined)

    def test_request_log_is_emitted_in_normal_runtime(self) -> None:
        """日志在正常服务进程中也必须开启，不能只靠测试捕获器。"""
        records: list[logging.LogRecord] = []

        class RecordHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        logger = logging.getLogger("ict.api")
        handler = RecordHandler()
        logger.addHandler(handler)
        try:
            self.get("/health")
        finally:
            logger.removeHandler(handler)

        self.assertTrue(any("request_complete" in record.getMessage() for record in records))


if __name__ == "__main__":
    unittest.main()
