"""Desktop proposal tests cover strict parsing and a read-only review page."""

import importlib
import gc
import json
import sys
import threading
import time
import tkinter as tk
import unittest
import weakref
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_ROOT))

PROJECT_ID = "123e4567-e89b-12d3-a456-426614174000"
PROPOSAL_ID = "123e4567-e89b-12d3-a456-426614174010"
ACCESS_TOKEN = "proposal-view-test-token"


class ProposalApiHandler(BaseHTTPRequestHandler):
    last_path = None
    last_authorization = None
    last_method = None
    run_payload = {
        "id": "123e4567-e89b-12d3-a456-426614174020",
        "proposal_id": PROPOSAL_ID,
        "project_id": PROJECT_ID,
        "dataset_version": "dataset-synthetic-v1",
        "pipeline_template": "research-smoke-v1",
        "parameters": {"sample_limit": 7},
        "config_sha256": "a" * 64,
        "quality_status": "success",
        "quality_rule_set_version": "generic-manifest-v1",
        "quality_report_sha256": "b" * 64,
        "trace_id": "123e4567-e89b-12d3-a456-426614174030",
        "status": "queued",
        "result": None,
        "error_code": None,
        "created_at": "2026-10-17T12:00:00Z",
        "started_at": None,
        "finished_at": None,
    }
    payload = [
        {
            "id": PROPOSAL_ID,
            "project_id": PROJECT_ID,
            "dataset_version": "dataset-synthetic-v1",
            "pipeline_template": "research-smoke-v1",
            "parameters": {"sample_limit": 7},
            "config_sha256": "a" * 64,
            "trace_id": "123e4567-e89b-12d3-a456-426614174030",
            "status": "pending_approval",
            "approved_by": None,
            "approved_at": None,
            "run_id": None,
            "created_at": "2026-10-17T12:00:00Z",
            "expires_at": "2026-10-17T12:15:00Z",
        }
    ]

    def do_GET(self):
        type(self).last_method = "GET"
        type(self).last_path = self.path
        type(self).last_authorization = self.headers.get("Authorization")
        payload = [type(self).run_payload] if self.path == "/api/v1/runs" else type(self).payload
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        type(self).last_method = "POST"
        type(self).last_path = self.path
        type(self).last_authorization = self.headers.get("Authorization")
        body = json.dumps(type(self).run_payload).encode("utf-8")
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


class FakeProposalClient:
    def __init__(self, api):
        self.api = api
        self.token_seen = None
        self.role = "viewer"
        self.template_requests = []
        self.template_started = threading.Event()
        self.template_release = None
        self.template_response = api.PipelineTemplateContract(
            template_id="research-smoke-v1",
            version="1.0.0",
            manifest_sha256="c" * 64,
            executor="synthetic_smoke_v1",
            dataset_version="dataset-synthetic-v1",
            permission_scope="synthetic_dataset_manifest_read_only",
            resource_limits=api.TemplateResourceLimits(1, 25, 30),
            inputs={"dataset_version": api.PipelineFieldContract(
                "string", True, None, None, "dataset-synthetic-v1"
            )},
            parameters={"sample_limit": api.PipelineFieldContract(
                "integer", True, 1, 100, None
            )},
            outputs={
                "task": api.PipelineFieldContract("string", True, None, None, "synthetic_smoke"),
                "processed_count": api.PipelineFieldContract("integer", True, 0, None, None),
                "synthetic_only": api.PipelineFieldContract("boolean", True, None, None, True),
                "research_ready": api.PipelineFieldContract("boolean", True, None, None, False),
                "message": api.PipelineFieldContract("string", True, None, None, None),
            },
            states=("queued", "running", "succeeded", "failed"),
            error_codes=(
                "DATA_QUALITY_BLOCKED", "PROPOSAL_CONFIG_MISMATCH",
                "QUEUE_UNAVAILABLE", "WORKER_EXECUTION_FAILED",
            ),
        )

    def check_health(self):
        return None

    def get_overview(self):
        return self.api.DemoProjectOverview(
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
        return [self.api.ProjectListItem(PROJECT_ID, "合成项目", "general", self.role)]

    def list_run_proposals(self, access_token):
        self.token_seen = access_token
        return [
            self.api.RunProposal(
                proposal_id=PROPOSAL_ID,
                project_id=PROJECT_ID,
                dataset_version="dataset-synthetic-v1",
                pipeline_template="research-smoke-v1",
                parameters={"sample_limit": 7},
                config_sha256="a" * 64,
                trace_id="123e4567-e89b-12d3-a456-426614174030",
                status="pending_approval",
                approved_by=None,
                approved_at=None,
                run_id=None,
                created_at="2026-10-17T12:00:00Z",
                expires_at="2026-10-17T12:15:00Z",
            )
        ]

    def get_project_template(self, project_id, template_id, access_token):
        self.token_seen = access_token
        self.template_requests.append((project_id, template_id, access_token))
        self.template_started.set()
        if self.template_release is not None:
            self.template_release.wait(timeout=3)
        if isinstance(self.template_response, Exception):
            raise self.template_response
        return self.template_response

    def approve_run_proposal(self, proposal_id, access_token):
        self.approved = (proposal_id, access_token)
        return self.api._parse_run(ProposalApiHandler.run_payload)

    def list_runs(self, access_token):
        self.token_seen = access_token
        return getattr(self, "runs", [])

    def list_run_events(self, access_token, run_id):
        self.token_seen = access_token
        return []


class DelayedRunListProposalClient(FakeProposalClient):
    """Hold the first run-list response so approval can race with a stale read."""

    def __init__(self, api):
        super().__init__(api)
        self.runs = []
        self.run_list_calls = 0
        self.first_run_list_started = threading.Event()
        self.release_first_run_list = threading.Event()

    def list_runs(self, access_token):
        self.token_seen = access_token
        self.run_list_calls += 1
        snapshot = list(self.runs)
        if self.run_list_calls == 1:
            self.first_run_list_started.set()
            self.release_first_run_list.wait(timeout=5)
        return snapshot

    def approve_run_proposal(self, proposal_id, access_token):
        run = super().approve_run_proposal(proposal_id, access_token)
        self.runs = [run]
        return run


class RunProposalDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ProposalApiHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2)

    def setUp(self):
        api = self.api_module()
        ProposalApiHandler.payload = [
            {
                "id": PROPOSAL_ID,
                "project_id": PROJECT_ID,
                "dataset_version": "dataset-synthetic-v1",
                "pipeline_template": "research-smoke-v1",
                "parameters": {"sample_limit": 7},
                "config_sha256": "a" * 64,
                "trace_id": "123e4567-e89b-12d3-a456-426614174030",
                "status": "pending_approval",
                "approved_by": None,
                "approved_at": None,
                "run_id": None,
                "created_at": "2026-10-17T12:00:00Z",
                "expires_at": "2026-10-17T12:15:00Z",
            }
        ]
        self.api = api

    def api_module(self):
        return importlib.import_module("ict_desktop.api")

    def test_api_client_reads_only_validated_proposals_with_bearer_auth(self):
        proposals = self.api.DemoProjectApiClient(self.base_url).list_run_proposals(ACCESS_TOKEN)

        self.assertEqual(ProposalApiHandler.last_path, "/api/v1/run-proposals")
        self.assertEqual(ProposalApiHandler.last_authorization, f"Bearer {ACCESS_TOKEN}")
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].status, "pending_approval")
        self.assertEqual(proposals[0].parameters, {"sample_limit": 7})
        self.assertEqual(len(proposals[0].config_sha256), 64)

    def test_api_client_approves_proposal_and_reads_only_validated_run_fields(self):
        client = self.api.DemoProjectApiClient(self.base_url)
        run = client.approve_run_proposal(PROPOSAL_ID, ACCESS_TOKEN)
        runs = client.list_runs(ACCESS_TOKEN)

        self.assertEqual(ProposalApiHandler.last_method, "GET")
        self.assertEqual(ProposalApiHandler.last_path, "/api/v1/runs")
        self.assertEqual(ProposalApiHandler.last_authorization, f"Bearer {ACCESS_TOKEN}")
        self.assertEqual(run.run_id, ProposalApiHandler.run_payload["id"])
        self.assertEqual(run.status, "queued")
        self.assertEqual(len(runs), 1)
        invalid = {**ProposalApiHandler.run_payload, "storage_key": "private://hidden"}
        with self.assertRaises(self.api.DesktopApiError):
            self.api._parse_run(invalid)

    def test_api_client_rejects_unexpected_proposal_fields(self):
        invalid = {**ProposalApiHandler.payload[0], "storage_key": "private://hidden"}
        with self.assertRaises(self.api.DesktopApiError) as raised:
            self.api._parse_run_proposals([invalid])
        self.assertEqual(str(raised.exception), "团队提案服务返回的数据格式不正确。")

    def test_desktop_page_reuses_memory_token_and_only_displays_proposal_details(self):
        window_module = importlib.import_module("ict_desktop.main_window")
        root = tk.Tk()
        root.withdraw()
        client = FakeProposalClient(self.api)
        window = window_module.MainWindow(root, client=client)

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
            window.proposals_button.invoke()
            self.assertIn("团队项目", window.proposals_status.cget("text"))
            window.team_projects_button.invoke()
            window.team_token_entry.insert(0, ACCESS_TOKEN)
            window.connect_team_projects_button.invoke()
            self.assertTrue(wait_until(lambda: bool(window.team_projects_tree.get_children())))

            window.proposals_button.invoke()
            self.assertTrue(wait_until(lambda: bool(window.proposals_tree.get_children())))
            self.assertEqual(client.token_seen, ACCESS_TOKEN)
            self.assertEqual(client.template_requests, [(PROJECT_ID, "research-smoke-v1", ACCESS_TOKEN)])
            proposal_row = window.proposals_tree.get_children()[0]
            self.assertEqual(window.proposals_tree.set(proposal_row, "status"), "待审批")
            window.proposals_tree.selection_set(proposal_row)
            window.proposals_tree.event_generate("<<TreeviewSelect>>")
            self.assertTrue(wait_until(lambda: "配置摘要" in window.proposal_detail_summary.get("1.0", "end-1c")))
            self.assertIn("research-smoke-v1", window.proposal_detail_title.cget("text"))
            proposal_details = window.proposal_detail_summary.get("1.0", "end-1c")
            self.assertIn("审批状态", proposal_details)
            self.assertIn("sample_limit", proposal_details)
            self.assertTrue(hasattr(window, "approve_proposal_button"))
            self.assertIn("disabled", window.approve_proposal_button.state())
            self.assertNotIn("disabled", window.view_template_button.state())
            with patch.object(window_module.messagebox, "showinfo") as show_template:
                window.view_template_button.invoke()
            dialog = getattr(window, "template_contract_dialog", None)
            self.assertIsNotNone(dialog, "template contracts need a themed, scrollable reading window")
            show_template.assert_not_called()
            template_text = dialog.body.get("1.0", "end-1c")
            self.assertIn("版本：1.0.0", template_text)
            self.assertIn("sample_limit", template_text)
            self.assertIn("范围 1 到 100", template_text)
            self.assertIn("research_ready=false", template_text)
            self.assertIn("只读", template_text)
            self.assertIn("并发上限：1", template_text)
            self.assertEqual(dialog.body.cget("state"), "disabled")
            dialog.close()
            self.assertFalse(hasattr(window, "execute_proposal_button"))

            window.clear_team_token_button.invoke()
            self.assertEqual(window.proposals_tree.get_children(), ())
            self.assertIsNone(window._project_token)
        finally:
            root.destroy()

    def test_operator_can_approve_after_confirmation_and_viewer_cannot(self):
        window_module = importlib.import_module("ict_desktop.main_window")
        root = tk.Tk()
        root.withdraw()
        client = FakeProposalClient(self.api)
        client.role = "operator"
        client.template_release = threading.Event()
        window = window_module.MainWindow(root, client=client)

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
            window.team_token_entry.insert(0, ACCESS_TOKEN)
            window.connect_team_projects_button.invoke()
            self.assertTrue(wait_until(lambda: bool(window.team_projects_tree.get_children())))
            window.proposals_button.invoke()
            self.assertTrue(client.template_started.wait(timeout=2))
            self.assertIn("disabled", window.approve_proposal_button.state())
            client.template_release.set()
            self.assertTrue(wait_until(lambda: bool(window.proposals_tree.get_children())))
            window.proposals_tree.selection_set(PROPOSAL_ID)
            window.proposals_tree.event_generate("<<TreeviewSelect>>")
            self.assertTrue(wait_until(lambda: "配置摘要" in window.proposal_detail_summary.get("1.0", "end-1c")))
            self.assertNotIn("disabled", window.approve_proposal_button.state())

            with patch.object(window_module.messagebox, "askyesno", return_value=True) as confirm:
                window.approve_proposal_button.invoke()
                self.assertTrue(wait_until(lambda: hasattr(client, "approved")))

            self.assertEqual(client.approved, (PROPOSAL_ID, ACCESS_TOKEN))
            self.assertIn("固定合成冒烟任务", confirm.call_args.args[1])
            self.assertTrue(window._template_contract_cache)
            window.clear_team_project_access()
            self.assertEqual(window._template_contract_cache, {})
            self.assertIn("disabled", window.approve_proposal_button.state())
        finally:
            if client.template_release is not None:
                client.template_release.set()
            root.destroy()

    def test_template_read_failure_keeps_proposal_visible_but_blocks_approval(self):
        window_module = importlib.import_module("ict_desktop.main_window")
        root = tk.Tk()
        root.withdraw()
        client = FakeProposalClient(self.api)
        client.role = "operator"
        client.template_response = self.api.DesktopApiError("团队服务暂时不可用，请稍后重试。")
        window = window_module.MainWindow(root, client=client)

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
            window.team_token_entry.insert(0, ACCESS_TOKEN)
            window.connect_team_projects_button.invoke()
            self.assertTrue(wait_until(lambda: bool(window.team_projects_tree.get_children())))
            window.proposals_button.invoke()
            self.assertTrue(wait_until(lambda: bool(window.proposals_tree.get_children())))
            window.proposals_tree.selection_set(PROPOSAL_ID)
            window.proposals_tree.event_generate("<<TreeviewSelect>>")

            self.assertIn("不可用", window.proposal_detail_summary.get("1.0", "end-1c"))
            self.assertIn("disabled", window.approve_proposal_button.state())
            self.assertIn("disabled", window.view_template_button.state())
        finally:
            root.destroy()

    def test_pending_proposal_request_does_not_keep_destroyed_window_alive(self):
        window_module = importlib.import_module("ict_desktop.main_window")
        root = tk.Tk()
        root.withdraw()
        client = FakeProposalClient(self.api)
        client.template_release = threading.Event()
        window = window_module.MainWindow(root, client=client)
        window_ref = weakref.ref(window)

        def wait_until(condition, timeout_seconds=3):
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                root.update()
                if condition():
                    return True
                time.sleep(0.01)
            root.update()
            return condition()

        retained_window = None
        try:
            self.assertTrue(wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
            window.team_projects_button.invoke()
            window.team_token_entry.insert(0, ACCESS_TOKEN)
            window.connect_team_projects_button.invoke()
            self.assertTrue(wait_until(lambda: bool(window.team_projects_tree.get_children())))
            window.proposals_button.invoke()
            self.assertTrue(client.template_started.wait(timeout=2))

            root.destroy()
            del window
            del root
            gc.collect()
            retained_window = window_ref()
            client.template_release.set()

            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and any(
                thread.name == "desktop-run-proposal-list" for thread in threading.enumerate()
            ):
                time.sleep(0.01)
            self.assertFalse(
                any(thread.name == "desktop-run-proposal-list" for thread in threading.enumerate()),
                "the proposal worker must finish after its blocked response is released",
            )
        finally:
            client.template_release.set()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and any(
                thread.name == "desktop-run-proposal-list" for thread in threading.enumerate()
            ):
                time.sleep(0.01)
            if "root" in locals() and root.winfo_exists():
                root.destroy()
            if "window" in locals():
                del window
            if "root" in locals():
                del root
            retained_window = None
            gc.collect()

        self.assertIsNone(
            window_ref(),
            "a background proposal request must not retain the destroyed Tk window",
        )

    def test_late_template_response_after_token_clear_does_not_restore_cached_data(self):
        window_module = importlib.import_module("ict_desktop.main_window")
        root = tk.Tk()
        root.withdraw()
        client = FakeProposalClient(self.api)
        client.template_release = threading.Event()
        window = window_module.MainWindow(root, client=client)

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
            window.team_token_entry.insert(0, ACCESS_TOKEN)
            window.connect_team_projects_button.invoke()
            self.assertTrue(wait_until(lambda: bool(window.team_projects_tree.get_children())))
            window.proposals_button.invoke()
            self.assertTrue(client.template_started.wait(timeout=2))
            self.assertTrue(window._proposal_loading)
            old_request_id = window._proposal_request_id

            window.clear_team_project_access()
            self.assertGreater(window._proposal_request_id, old_request_id)
            self.assertEqual(window._template_contract_cache, {})
            self.assertEqual(window._proposal_cache, {})
            client.template_release.set()

            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and any(
                thread.name == "desktop-run-proposal-list"
                for thread in threading.enumerate()
            ):
                time.sleep(0.01)
            self.assertFalse(
                any(thread.name == "desktop-run-proposal-list" for thread in threading.enumerate()),
                "the proposal request must finish before inspecting its result queue",
            )
            self.assertEqual(
                window._proposal_result_queue.qsize(),
                0,
                "a stale template response must not remain queued after the account is cleared",
            )
            for _ in range(3):
                root.update()
                time.sleep(0.02)

            self.assertEqual(window._template_contract_cache, {})
            self.assertEqual(window._template_error_cache, {})
            self.assertEqual(window._proposal_cache, {})
            self.assertEqual(window.proposals_tree.get_children(), ())
            self.assertIn("disabled", window.approve_proposal_button.state())
            self.assertIn("disabled", window.view_template_button.state())
            self.assertIsNone(window._project_token)
        finally:
            if client.template_release is not None:
                client.template_release.set()
            if root.winfo_exists():
                root.destroy()
            # Collect Tk cycles on the thread that created their interpreter.
            del window
            del root
            gc.collect()

    def test_approval_refreshes_runs_after_an_in_flight_stale_run_list(self):
        window_module = importlib.import_module("ict_desktop.main_window")
        root = tk.Tk()
        root.withdraw()
        client = DelayedRunListProposalClient(self.api)
        client.role = "operator"
        window = window_module.MainWindow(root, client=client)

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
            window.team_token_entry.insert(0, ACCESS_TOKEN)
            window.connect_team_projects_button.invoke()
            self.assertTrue(wait_until(lambda: bool(window.team_projects_tree.get_children())))
            if not client.first_run_list_started.wait(timeout=3):
                window.show_runs()
                self.assertTrue(client.first_run_list_started.wait(timeout=3))

            window.proposals_button.invoke()
            self.assertTrue(wait_until(lambda: bool(window.proposals_tree.get_children())))
            window.proposals_tree.selection_set(PROPOSAL_ID)
            window.proposals_tree.event_generate("<<TreeviewSelect>>")
            self.assertTrue(wait_until(lambda: "配置摘要" in window.proposal_detail_summary.get("1.0", "end-1c")))

            with patch.object(window_module.messagebox, "askyesno", return_value=True):
                window.approve_proposal_button.invoke()
                self.assertTrue(wait_until(lambda: window.proposals_status.cget("text").startswith("已批准")))

            client.release_first_run_list.set()
            self.assertTrue(
                wait_until(lambda: "research-smoke-v1" in window.recent_run_summary.cget("text")),
                "the overview should show the run created by the approval after the stale list response",
            )
            self.assertGreaterEqual(client.run_list_calls, 2)
        finally:
            client.release_first_run_list.set()
            if root.winfo_exists():
                root.destroy()

    def test_destroying_window_cancels_pending_approval_poll(self):
        window_module = importlib.import_module("ict_desktop.main_window")
        root = tk.Tk()
        root.withdraw()
        client = FakeProposalClient(self.api)
        client.role = "operator"
        window = window_module.MainWindow(root, client=client)
        destroyed = False

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
            window.team_token_entry.insert(0, ACCESS_TOKEN)
            window.connect_team_projects_button.invoke()
            self.assertTrue(wait_until(lambda: bool(window.team_projects_tree.get_children())))
            window.proposals_button.invoke()
            self.assertTrue(wait_until(lambda: bool(window.proposals_tree.get_children())))
            window.proposals_tree.selection_set(PROPOSAL_ID)
            window.proposals_tree.event_generate("<<TreeviewSelect>>")
            self.assertTrue(wait_until(lambda: "配置摘要" in window.proposal_detail_summary.get("1.0", "end-1c")))

            scheduled_ids = []
            original_after = root.after

            def track_after(*args, **kwargs):
                after_id = original_after(*args, **kwargs)
                scheduled_ids.append(after_id)
                return after_id

            with patch.object(window_module.messagebox, "askyesno", return_value=True):
                with patch.object(root, "after", side_effect=track_after) as schedule:
                    window.approve_proposal_button.invoke()
                self.assertEqual(schedule.call_count, 1)
                self.assertEqual(len(scheduled_ids), 1)
                approval_poll_id = scheduled_ids[0]
            # Let the worker finish without pumping Tk, leaving its poll timer pending.
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and not hasattr(client, "approved"):
                time.sleep(0.01)
            self.assertEqual(client.approved, (PROPOSAL_ID, ACCESS_TOKEN))

            with patch.object(root, "after_cancel", wraps=root.after_cancel) as cancel:
                root.destroy()
                destroyed = True
                cancel.assert_called_once_with(approval_poll_id)
        finally:
            if not destroyed:
                root.destroy()

    def test_run_page_displays_only_the_fixed_synthetic_result(self):
        window_module = importlib.import_module("ict_desktop.main_window")
        root = tk.Tk()
        root.withdraw()
        client = FakeProposalClient(self.api)
        client.runs = [
            self.api.Run(
                run_id="123e4567-e89b-12d3-a456-426614174020",
                proposal_id=PROPOSAL_ID,
                project_id=PROJECT_ID,
                dataset_version="dataset-synthetic-v1",
                pipeline_template="research-smoke-v1",
                parameters={"sample_limit": 7},
                config_sha256="a" * 64,
                trace_id="123e4567-e89b-12d3-a456-426614174030",
                status="succeeded",
                result={
                    "task": "synthetic_smoke",
                    "processed_count": 7,
                    "synthetic_only": True,
                    "research_ready": False,
                    "message": "集成冒烟任务完成。",
                },
                error_code=None,
                created_at="2026-10-17T12:00:00Z",
                started_at="2026-10-17T12:00:01Z",
                finished_at="2026-10-17T12:00:02Z",
            )
        ]
        window = window_module.MainWindow(root, client=client)

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
            window.team_token_entry.insert(0, ACCESS_TOKEN)
            window.connect_team_projects_button.invoke()
            self.assertTrue(wait_until(lambda: bool(window.team_projects_tree.get_children())))
            window.runs_button.invoke()
            self.assertTrue(wait_until(lambda: bool(window.runs_tree.get_children())))
            run_row = window.runs_tree.get_children()[0]
            self.assertEqual(window.runs_tree.set(run_row, "status"), "已完成")
            window.runs_tree.selection_set(run_row)
            window.runs_tree.event_generate("<<TreeviewSelect>>")
            summary = window.run_detail_summary.get("1.0", "end-1c")
            self.assertIn("运行 ID", summary)
            self.assertIn("处理合成样例：7 条", summary)
            self.assertIn("synthetic_only=true", summary)
            self.assertIn("不是正式研究结论", summary)
            self.assertIn("Trace ID", summary)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
