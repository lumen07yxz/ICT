import importlib
import importlib.util
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_ROOT))


class DemoApiHandler(BaseHTTPRequestHandler):
    payload = {
        "project_id": "demo-research",
        "purpose": "用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
        "data_status": "synthetic_only",
        "research_ready": False,
        "dataset_versions": ["dataset-synthetic-v1"],
        "pipeline_templates": ["research-smoke-v1"],
        "recent_public_runs": [],
    }
    health_payload = {"status": "ok", "mode": "synthetic_demo"}
    last_path = None
    last_authorization = None
    quality_payload = {
        "dataset_version": "dataset-synthetic-v1",
        "status": "success",
        "rule_set_version": "generic-manifest-v1",
        "manifest_sha256": "a" * 64,
        "row_count": 4,
        "split_counts": {"test": 1, "train": 2, "validation": 1},
        "label_category_count": 2,
        "issues": [],
        "synthetic_only": True,
        "research_ready": False,
        "checked_at": "2026-10-17T12:00:00+00:00",
    }
    template_payload = {
        "template_id": "research-smoke-v1",
        "version": "1.0.0",
        "manifest_sha256": "c" * 64,
        "executor": "synthetic_smoke_v1",
        "dataset_version": "dataset-synthetic-v1",
        "permission_scope": "synthetic_dataset_manifest_read_only",
        "resource_limits": {
            "max_concurrent_runs": 1,
            "soft_timeout_seconds": 25,
            "hard_timeout_seconds": 30,
        },
        "inputs": {
            "dataset_version": {
                "type": "string",
                "required": True,
                "minimum": None,
                "maximum": None,
                "const": "dataset-synthetic-v1",
            }
        },
        "parameters": {
            "sample_limit": {
                "type": "integer",
                "required": True,
                "minimum": 1,
                "maximum": 100,
                "const": None,
            }
        },
        "outputs": {
            "task": {"type": "string", "required": True, "minimum": None, "maximum": None, "const": "synthetic_smoke"},
            "processed_count": {"type": "integer", "required": True, "minimum": 0, "maximum": None, "const": None},
            "synthetic_only": {"type": "boolean", "required": True, "minimum": None, "maximum": None, "const": True},
            "research_ready": {"type": "boolean", "required": True, "minimum": None, "maximum": None, "const": False},
            "message": {"type": "string", "required": True, "minimum": None, "maximum": None, "const": None},
        },
        "states": ["queued", "running", "succeeded", "failed"],
        "error_codes": [
            "DATA_QUALITY_BLOCKED",
            "PROPOSAL_CONFIG_MISMATCH",
            "QUEUE_UNAVAILABLE",
            "WORKER_EXECUTION_FAILED",
        ],
    }
    run_events_payload = [
        {"sequence": 1, "status": "queued", "error_code": None, "occurred_at": "2026-10-19T12:00:00+00:00"},
        {"sequence": 2, "status": "running", "error_code": None, "occurred_at": "2026-10-19T12:00:01+00:00"},
        {"sequence": 3, "status": "succeeded", "error_code": None, "occurred_at": "2026-10-19T12:00:02+00:00"},
    ]

    def do_GET(self):
        type(self).last_path = self.path
        type(self).last_authorization = self.headers.get("Authorization")
        if self.path == "/health":
            payload = type(self).health_payload
        elif self.path == "/api/v1/projects/demo/demo-research/datasets/dataset-synthetic-v1/quality-report":
            payload = type(self).quality_payload
        elif "/templates/" in self.path:
            payload = type(self).template_payload
        elif self.path.endswith("/events"):
            payload = type(self).run_events_payload
        else:
            payload = type(self).payload
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Keep the test server quiet so request details do not leak into test logs.
        return


class DemoProjectApiClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DemoApiHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2)

    def api_module(self):
        try:
            spec = importlib.util.find_spec("ict_desktop.api")
        except ModuleNotFoundError:
            spec = None
        self.assertIsNotNone(spec, "The desktop API client must be implemented")
        return importlib.import_module("ict_desktop.api")

    def test_reads_only_the_allowlisted_synthetic_project_over_http(self):
        api = self.api_module()
        overview = api.DemoProjectApiClient(self.base_url).get_overview()

        self.assertEqual(DemoApiHandler.last_path, "/api/v1/demo/projects/demo-research/overview")
        self.assertEqual(overview.project_id, "demo-research")
        self.assertEqual(overview.data_status, "synthetic_only")
        self.assertFalse(overview.research_ready)
        self.assertEqual(overview.dataset_versions, ("dataset-synthetic-v1",))

    def test_checks_service_liveness_through_health_endpoint(self):
        api = self.api_module()

        result = api.DemoProjectApiClient(self.base_url).check_health()

        self.assertIsNone(result)
        self.assertEqual(DemoApiHandler.last_path, "/health")

    def test_rejects_unhealthy_service_response_with_safe_message(self):
        api = self.api_module()
        original_payload = DemoApiHandler.health_payload
        try:
            DemoApiHandler.health_payload = {"status": "starting", "detail": "internal detail"}

            with self.assertRaises(api.DesktopApiError) as raised:
                api.DemoProjectApiClient(self.base_url).check_health()

            self.assertEqual(str(raised.exception), "服务当前不可用，请稍后重试。")
            self.assertNotIn("internal detail", str(raised.exception))
        finally:
            DemoApiHandler.health_payload = original_payload

    def test_rejects_responses_that_cross_the_synthetic_only_boundary(self):
        api = self.api_module()
        original_payload = DemoApiHandler.payload
        try:
            DemoApiHandler.payload = {**original_payload, "research_ready": True}

            with self.assertRaises(api.DesktopApiError) as raised:
                api.DemoProjectApiClient(self.base_url).get_overview()

            self.assertEqual(str(raised.exception), "后端返回的数据不符合当前演示范围。")
        finally:
            DemoApiHandler.payload = original_payload

    def test_requires_https_for_non_loopback_api_hosts(self):
        api = self.api_module()

        with self.assertRaises(api.DesktopApiError):
            api.DemoProjectApiClient("http://api.example.com")

        with self.assertRaises(api.DesktopApiError):
            api.DemoProjectApiClient("https://user:secret@example.com")

    def test_reads_and_validates_the_member_scoped_server_quality_report(self):
        api = self.api_module()
        client = api.DemoProjectApiClient(self.base_url)

        report = client.get_demo_quality_report("team-test-token")

        self.assertEqual(report.status, "success")
        self.assertEqual(report.dataset_version, "dataset-synthetic-v1")
        self.assertEqual(dict(report.split_counts), {"test": 1, "train": 2, "validation": 1})
        self.assertEqual(DemoApiHandler.last_authorization, "Bearer team-test-token")
        self.assertEqual(
            DemoApiHandler.last_path,
            "/api/v1/projects/demo/demo-research/datasets/dataset-synthetic-v1/quality-report",
        )

    def test_reads_member_scoped_run_events_with_fixed_fields(self):
        api = self.api_module()
        client = api.DemoProjectApiClient(self.base_url)
        run_id = "123e4567-e89b-12d3-a456-426614174024"

        events = client.list_run_events("team-test-token", run_id)

        self.assertEqual([event.status for event in events], ["queued", "running", "succeeded"])
        self.assertEqual([event.sequence for event in events], [1, 2, 3])
        self.assertEqual(DemoApiHandler.last_authorization, "Bearer team-test-token")
        self.assertEqual(DemoApiHandler.last_path, f"/api/v1/runs/{run_id}/events")

    def test_reads_the_member_scoped_fixed_template_contract(self):
        api = self.api_module()
        client = api.DemoProjectApiClient(self.base_url)
        project_id = "123e4567-e89b-12d3-a456-426614174022"

        contract = client.get_project_template(project_id, "research-smoke-v1", "team-test-token")

        self.assertEqual(
            DemoApiHandler.last_path,
            f"/api/v1/projects/{project_id}/templates/research-smoke-v1",
        )
        self.assertEqual(DemoApiHandler.last_authorization, "Bearer team-test-token")
        self.assertEqual(contract.template_id, "research-smoke-v1")
        self.assertEqual(contract.version, "1.0.0")
        self.assertEqual(contract.manifest_sha256, "c" * 64)
        self.assertEqual(contract.parameters["sample_limit"].minimum, 1)
        self.assertEqual(contract.parameters["sample_limit"].maximum, 100)
        self.assertFalse(contract.outputs["research_ready"].const)
        self.assertEqual(contract.resource_limits.max_concurrent_runs, 1)

    def test_template_contract_rejects_extra_fields_and_unsafe_changes(self):
        api = self.api_module()
        client = api.DemoProjectApiClient(self.base_url)
        project_id = "123e4567-e89b-12d3-a456-426614174022"
        original_payload = DemoApiHandler.template_payload
        try:
            DemoApiHandler.template_payload = {**original_payload, "storage_path": "/private/data"}
            with self.assertRaises(api.DesktopApiError):
                client.get_project_template(project_id, "research-smoke-v1", "team-test-token")

            DemoApiHandler.template_payload = {
                **original_payload,
                "outputs": {
                    **original_payload["outputs"],
                    "research_ready": {"type": "boolean", "required": True, "const": True},
                },
            }
            with self.assertRaises(api.DesktopApiError):
                client.get_project_template(project_id, "research-smoke-v1", "team-test-token")
        finally:
            DemoApiHandler.template_payload = original_payload

    def test_run_event_parser_rejects_extra_private_fields(self):
        api = self.api_module()
        original_payload = DemoApiHandler.run_events_payload
        try:
            DemoApiHandler.run_events_payload = [
                {**original_payload[0], "identity": "private-user"}
            ]
            with self.assertRaises(api.DesktopApiError):
                api.DemoProjectApiClient(self.base_url).list_run_events(
                    "team-test-token", "123e4567-e89b-12d3-a456-426614174024"
                )
        finally:
            DemoApiHandler.run_events_payload = original_payload


if __name__ == "__main__":
    unittest.main()
