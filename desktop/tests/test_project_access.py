"""Tests for the read-only, token-authenticated team project experience."""

import importlib
import io
import json
import sys
import threading
import time
import tkinter as tk
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_ROOT))

PROJECT_ID = "123e4567-e89b-12d3-a456-426614174000"
TEST_TOKEN = "team-token-never-persist"


class ProjectApiHandler(BaseHTTPRequestHandler):
    last_path = None
    last_authorization = None
    status_code = 200

    def do_GET(self):
        type(self).last_path = self.path
        type(self).last_authorization = self.headers.get("Authorization")
        if type(self).status_code != 200:
            body = json.dumps({"detail": f"unsafe response includes {TEST_TOKEN}"}).encode()
            self.send_response(type(self).status_code)
        elif self.path == "/api/v1/projects":
            body = json.dumps(
                [
                    {
                        "id": PROJECT_ID,
                        "name": "合成演示项目",
                        "domain": "general",
                        "role": "viewer",
                        "created_at": "2026-10-17T00:00:00Z",
                    }
                ]
            ).encode()
            self.send_response(200)
        else:
            body = json.dumps(
                {
                    "id": PROJECT_ID,
                    "name": "合成演示项目",
                    "domain": "general",
                    "description": "仅供接口联调",
                    "role": "viewer",
                    "created_at": "2026-10-17T00:00:00Z",
                    "datasets": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174001",
                            "version": "dataset-synthetic-v1",
                            "source": "synthetic",
                            "license_status": "not_applicable",
                            "manifest_ref": "synthetic://manifest",
                            "schema_ref": "synthetic://schema",
                            "research_ready": False,
                        }
                    ],
                    "pipeline_templates": ["research-smoke-v1"],
                }
            ).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


class FakeProjectClient:
    def __init__(self, api_module):
        self.api_module = api_module
        self.token_seen = None
        self.run_token_seen = None

    def check_health(self):
        return None

    def get_overview(self):
        return self.api_module.DemoProjectOverview(
            project_id="demo-research",
            purpose="合成样例",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )

    def list_projects(self, access_token):
        self.token_seen = access_token
        return [
            self.api_module.ProjectListItem(
                project_id=PROJECT_ID,
                name="合成演示项目",
                domain="general",
                role="viewer",
            )
        ]

    def list_runs(self, access_token):
        self.run_token_seen = access_token
        return []

    def list_run_events(self, access_token, run_id):
        self.run_token_seen = access_token
        return []

    def get_project(self, project_id, access_token):
        self.token_seen = access_token
        dataset = self.api_module.ProjectDatasetVersion(
            version="dataset-synthetic-v1",
            source="synthetic",
            license_status="not_applicable",
            research_ready=False,
        )
        return self.api_module.ProjectDetail(
            project_id=project_id,
            name="合成演示项目",
            domain="general",
            role="viewer",
            datasets=(dataset,),
        )


class ProjectAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ProjectApiHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2)

    def setUp(self):
        ProjectApiHandler.status_code = 200

    def api_module(self):
        return importlib.import_module("ict_desktop.api")

    def test_project_api_uses_bearer_token_and_parses_read_only_responses(self):
        api = self.api_module()
        client = api.DemoProjectApiClient(self.base_url)

        projects = client.list_projects(TEST_TOKEN)
        detail = client.get_project(PROJECT_ID, TEST_TOKEN)

        self.assertEqual(ProjectApiHandler.last_path, f"/api/v1/projects/{PROJECT_ID}")
        self.assertEqual(ProjectApiHandler.last_authorization, f"Bearer {TEST_TOKEN}")
        self.assertEqual(projects[0].role, "viewer")
        self.assertEqual(detail.datasets[0].version, "dataset-synthetic-v1")
        self.assertFalse(detail.datasets[0].research_ready)
        self.assertFalse(hasattr(client, "create_project"))

    def test_project_api_rejects_empty_token_and_invalid_project_id(self):
        api = self.api_module()
        client = api.DemoProjectApiClient(self.base_url)

        with self.assertRaises(api.DesktopApiError) as empty_token:
            client.list_projects(" ")
        with self.assertRaises(api.DesktopApiError) as invalid_id:
            client.get_project("not-a-uuid", TEST_TOKEN)

        self.assertEqual(str(empty_token.exception), "请输入团队访问令牌。")
        self.assertEqual(str(invalid_id.exception), "项目标识无效，无法读取详情。")

    def test_unauthorized_error_does_not_echo_token_or_response_body(self):
        api = self.api_module()
        ProjectApiHandler.status_code = 401

        with self.assertRaises(api.DesktopApiError) as raised:
            api.DemoProjectApiClient(self.base_url).list_projects(TEST_TOKEN)

        self.assertEqual(str(raised.exception), "访问令牌无效或已过期，请重新输入。")
        self.assertNotIn(TEST_TOKEN, str(raised.exception))
        self.assertNotIn("unsafe response", str(raised.exception))

    def test_http_error_closes_response_body_after_safe_error_handling(self):
        api = self.api_module()
        response_body = io.BytesIO(b"unsafe response")
        http_error = HTTPError(self.base_url, 401, "Unauthorized", {}, response_body)

        with patch("ict_desktop.api.urlopen", side_effect=http_error):
            with self.assertRaises(api.DesktopApiError):
                api.DemoProjectApiClient(self.base_url).list_projects(TEST_TOKEN)

        self.assertTrue(response_body.closed)

    def test_team_project_page_keeps_token_in_memory_and_displays_role_and_dataset(self):
        api = self.api_module()
        main_window = importlib.import_module("ict_desktop.main_window")
        root = tk.Tk()
        root.withdraw()
        client = FakeProjectClient(api)
        saved_settings = []
        window = main_window.MainWindow(
            root,
            client=client,
            settings_saver=saved_settings.append,
        )

        def wait_until(condition, timeout_seconds=3):
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                root.update()
                if condition():
                    return True
                time.sleep(0.01)
            root.update()
            return condition()

        try:
            self.assertTrue(wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
            window.team_projects_button.invoke()
            window.team_token_entry.insert(0, TEST_TOKEN)
            window.connect_team_projects_button.invoke()

            self.assertTrue(wait_until(lambda: window.team_projects_tree.get_children()))
            item_id = window.team_projects_tree.get_children()[0]
            self.assertEqual(window.team_projects_tree.set(item_id, "role"), "查看者")
            window.team_projects_tree.selection_set(item_id)
            window.team_projects_tree.event_generate("<<TreeviewSelect>>")

            self.assertTrue(wait_until(lambda: "dataset-synthetic-v1" in window.project_detail_summary.get("1.0", "end-1c")))
            self.assertIn("项目 ID", window.project_detail_summary.get("1.0", "end-1c"))
            self.assertIn("许可状态", window.project_detail_summary.get("1.0", "end-1c"))
            license_label = window.project_detail_summary.search("许可状态", "1.0", "end")
            license_value = window.project_detail_summary.index(f"{license_label} + 1 line")
            self.assertIn("field_value", window.project_detail_summary.tag_names(license_value))
            self.assertNotIn("field_value_warning", window.project_detail_summary.tag_names(license_value))
            self.assertEqual(client.token_seen, TEST_TOKEN)
            self.assertEqual(client.run_token_seen, TEST_TOKEN)
            self.assertEqual(saved_settings, [])
            self.assertEqual(window.team_token_entry.cget("show"), "*")
            self.assertFalse(hasattr(window, "create_project_button"))

            window.clear_team_token_button.invoke()
            self.assertIsNone(window._project_token)
            self.assertEqual(window.team_token_entry.get(), "")
            self.assertEqual(window.team_projects_status.cget("text"), "访问令牌已清除。")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
