import importlib
import importlib.util
import gc
import sys
import tempfile
import time
import tkinter as tk
import unittest
from threading import Event
from unittest.mock import patch
from pathlib import Path

DESKTOP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_ROOT))


class FakeApiClient:
    def __init__(self, responses, health_responses=None, projects=None, runs=None, run_events=None):
        self.responses = list(responses)
        self.health_responses = list(health_responses or [])
        self.projects = list(projects or [])
        self.runs = [] if runs is None else runs
        self.proposal_access_tokens = []
        self.run_events = dict(run_events or {})
        self.project_access_tokens = []
        self.run_access_tokens = []
        self.run_event_access = []
        self.run_event_gates = {}

    def check_health(self):
        if not self.health_responses:
            return None
        response = self.health_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def get_overview(self):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def list_projects(self, access_token):
        self.project_access_tokens.append(access_token)
        return list(self.projects)

    def list_runs(self, access_token):
        self.run_access_tokens.append(access_token)
        if isinstance(self.runs, Exception):
            raise self.runs
        return list(self.runs)

    def list_run_proposals(self, access_token):
        self.proposal_access_tokens.append(access_token)
        return []

    def list_run_events(self, access_token, run_id):
        self.run_event_access.append((access_token, run_id))
        gate = self.run_event_gates.get(run_id)
        if gate is not None:
            gate.wait(timeout=2)
        response = self.run_events.get(run_id, [])
        if isinstance(response, Exception):
            raise response
        return list(response)


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = None

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        # Collect destroyed Tk widget cycles here so a later worker thread cannot
        # run their PhotoImage/Tcl destructors from its own garbage collection.
        try:
            if self.root is not None and self.root.winfo_exists():
                self.root.destroy()
        except tk.TclError:
            pass
        self.root = None
        gc.collect()

    def main_window_module(self):
        try:
            spec = importlib.util.find_spec("ict_desktop.main_window")
        except ModuleNotFoundError:
            spec = None
        self.assertIsNotNone(spec, "The native desktop window must be implemented")
        return importlib.import_module("ict_desktop.main_window")

    def wait_until(self, condition, timeout_seconds=3):
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            self.root.update()
            if condition():
                return True
            time.sleep(0.01)
        self.root.update()
        return condition()

    def run_window_with_member_run(self, api, run):
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )
        client = FakeApiClient(
            [overview],
            projects=[
                api.ProjectListItem(
                    project_id="123e4567-e89b-12d3-a456-426614174022",
                    name="合成演示项目",
                    domain="generic-research",
                    role="viewer",
                )
            ],
            runs=[run],
        )
        return api.MainWindow(self.root, client=client), client

    def run_for_report(self, api, status):
        result = None
        error_code = None
        if status == "succeeded":
            result = {
                "task": "synthetic_smoke",
                "processed_count": 7,
                "synthetic_only": True,
                "research_ready": False,
                "message": "集成冒烟任务完成。",
            }
        elif status == "failed":
            error_code = "SYNTHETIC_TASK_FAILED"
        return api.Run(
            run_id="123e4567-e89b-12d3-a456-426614174024",
            proposal_id="123e4567-e89b-12d3-a456-426614174021",
            project_id="123e4567-e89b-12d3-a456-426614174022",
            dataset_version="dataset-synthetic-v1",
            pipeline_template="research-smoke-v1",
            parameters={"sample_limit": 7},
            config_sha256="a" * 64,
            trace_id="123e4567-e89b-12d3-a456-426614174023",
            status=status,
            result=result,
            error_code=error_code,
            created_at="2026-10-19T00:00:00Z",
            started_at="2026-10-19T00:00:01Z",
            finished_at="2026-10-19T00:00:02Z" if status in ("succeeded", "failed") else None,
            quality_status="success",
            quality_rule_set_version="generic-manifest-v1",
            quality_report_sha256="b" * 64,
        )

    def connect_and_open_run(self, window, run):
        self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
        window.team_token_entry.insert(0, "team-test-token")
        window.connect_team_projects()
        self.assertTrue(self.wait_until(lambda: run.run_id == window._recent_run_id))
        window.open_recent_run_button.invoke()
        self.assertTrue(self.wait_until(lambda: run.run_id in window.run_detail_summary.get("1.0", "end-1c")))

    def test_terminal_run_can_be_exported_as_local_html_report(self):
        window_module = self.main_window_module()
        run = self.run_for_report(window_module, "succeeded")
        window, client = self.run_window_with_member_run(window_module, run)
        client.run_events[run.run_id] = [
            window_module.RunEvent(sequence=1, status="queued", error_code=None, occurred_at="2026-10-19T12:00:00Z"),
            window_module.RunEvent(sequence=2, status="running", error_code=None, occurred_at="2026-10-19T12:00:01Z"),
            window_module.RunEvent(sequence=3, status="succeeded", error_code=None, occurred_at="2026-10-19T12:00:02Z"),
        ]
        try:
            self.connect_and_open_run(window, run)
            self.assertTrue(self.wait_until(lambda: window._run_event_loaded_id == run.run_id))
            self.assertNotIn("disabled", window.export_run_report_button.state())
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "synthetic-run.html"
                with patch.object(window_module.filedialog, "asksaveasfilename", return_value=str(target)) as save_dialog:
                    with patch.object(window_module.messagebox, "showinfo") as saved_message:
                        window.export_run_report_button.invoke()
                save_dialog.assert_called_once()
                saved_message.assert_called_once()
                report = target.read_text(encoding="utf-8")
                self.assertIn("合成冒烟运行报告", report)
                self.assertIn(run.run_id, report)
                self.assertIn("research_ready=false", report)
                self.assertIn("运行状态时间线", report)
                self.assertIn("2026-10-19T12:00:01Z", report)
                self.assertNotIn("team-test-token", report)
        finally:
            if self.root.winfo_exists():
                self.root.destroy()

    def test_run_report_export_is_disabled_for_nonterminal_run(self):
        window_module = self.main_window_module()
        run = self.run_for_report(window_module, "queued")
        window, _client = self.run_window_with_member_run(window_module, run)
        try:
            self.connect_and_open_run(window, run)
            self.assertIn("disabled", window.export_run_report_button.state())
            pdf_button = getattr(window, "export_run_pdf_button", None)
            self.assertIsNotNone(pdf_button, "The desktop client must expose a PDF report action.")
            if pdf_button is not None:
                self.assertIn("disabled", pdf_button.state())
            with patch.object(window_module.filedialog, "asksaveasfilename") as save_dialog:
                window.export_run_report_button.invoke()
            save_dialog.assert_not_called()
        finally:
            if self.root.winfo_exists():
                self.root.destroy()

    def test_terminal_run_can_be_exported_as_a_local_pdf_report(self):
        window_module = self.main_window_module()
        run = self.run_for_report(window_module, "succeeded")
        window, client = self.run_window_with_member_run(window_module, run)
        client.run_events[run.run_id] = [
            window_module.RunEvent(sequence=1, status="queued", error_code=None, occurred_at="2026-10-19T12:00:00Z"),
            window_module.RunEvent(sequence=2, status="running", error_code=None, occurred_at="2026-10-19T12:00:01Z"),
            window_module.RunEvent(sequence=3, status="succeeded", error_code=None, occurred_at="2026-10-19T12:00:02Z"),
        ]
        try:
            self.connect_and_open_run(window, run)
            self.assertTrue(self.wait_until(lambda: window._run_event_loaded_id == run.run_id))
            pdf_button = getattr(window, "export_run_pdf_button", None)
            self.assertIsNotNone(pdf_button, "The desktop client must expose a PDF report action.")
            if pdf_button is None:
                return
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "synthetic-run.pdf"
                with patch.object(window_module.filedialog, "asksaveasfilename", return_value=str(target)) as save_dialog:
                    with patch.object(window_module.messagebox, "showinfo") as saved_message:
                        pdf_button.invoke()
                save_dialog.assert_called_once()
                saved_message.assert_called_once()
                self.assertTrue(target.read_bytes().startswith(b"%PDF-"))
        finally:
            if self.root.winfo_exists():
                self.root.destroy()

    def test_run_report_save_failure_is_logged_without_showing_the_path(self):
        window_module = self.main_window_module()
        run = self.run_for_report(window_module, "failed")
        window, _client = self.run_window_with_member_run(window_module, run)
        try:
            self.connect_and_open_run(window, run)
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "private-location.html"
                with patch.object(window_module.filedialog, "asksaveasfilename", return_value=str(target)):
                    with patch.object(window_module.messagebox, "showerror") as error_message:
                        with patch.object(Path, "write_text", side_effect=OSError("private path detail")):
                            with self.assertLogs(window_module.LOGGER, level="ERROR") as logs:
                                window.export_run_report_button.invoke()
                error_message.assert_called_once()
                self.assertNotIn(str(target), error_message.call_args.args[1])
                self.assertIn("OSError", logs.output[0])
                self.assertNotIn(str(target), logs.output[0])
        finally:
            if self.root.winfo_exists():
                self.root.destroy()

    def test_selected_run_shows_its_persisted_event_timeline(self):
        api = self.main_window_module()
        run = self.run_for_report(api, "succeeded")
        events = [
            api.RunEvent(sequence=1, status="queued", error_code=None, occurred_at="2026-10-19T12:00:00Z"),
            api.RunEvent(sequence=2, status="running", error_code=None, occurred_at="2026-10-19T12:00:01Z"),
            api.RunEvent(sequence=3, status="succeeded", error_code=None, occurred_at="2026-10-19T12:00:02Z"),
        ]
        window, client = self.run_window_with_member_run(api, run)
        client.run_events[run.run_id] = events
        try:
            self.connect_and_open_run(window, run)
            timeline_text = lambda: window.run_event_timeline.get("1.0", "end-1c")
            self.assertTrue(
                self.wait_until(
                    lambda: "排队中" in timeline_text()
                    and "已完成" in timeline_text()
                ),
                f"timeline={timeline_text()!r}, requests={client.run_event_access!r}",
            )
            self.assertIsInstance(window.run_event_timeline, tk.Text)
            self.assertEqual(client.run_event_access, [("team-test-token", run.run_id)])
            self.assertIn("2026-10-19T12:00:01Z", timeline_text())
            self.assertTrue(window.run_event_timeline.tag_ranges("timeline_running"))
            self.assertEqual(window.run_event_timeline.cget("state"), "disabled")
        finally:
            if self.root.winfo_exists():
                self.root.destroy()

    def test_selected_run_details_and_actions_fit_default_window(self):
        api = self.main_window_module()
        run = self.run_for_report(api, "succeeded")
        events = [
            api.RunEvent(sequence=1, status="queued", error_code=None, occurred_at="2026-10-19T12:00:00Z"),
            api.RunEvent(sequence=2, status="running", error_code=None, occurred_at="2026-10-19T12:00:01Z"),
            api.RunEvent(sequence=3, status="succeeded", error_code=None, occurred_at="2026-10-19T12:00:02Z"),
        ]
        window, client = self.run_window_with_member_run(api, run)
        client.run_events[run.run_id] = events
        try:
            self.root.geometry("1180x760")
            self.root.deiconify()
            self.connect_and_open_run(window, run)
            self.assertTrue(self.wait_until(lambda: window._run_event_loaded_id == run.run_id))
            self.root.update_idletasks()

            details = window.run_detail_summary.get("1.0", "end-1c")
            self.assertIn("运行 ID", details)
            self.assertIn("运行状态", details)
            self.assertIn("结果仅为合成研究结果", details)
            self.assertIn("处理合成样例：7 条", details)
            self.assertIn("synthetic_only=true", details)
            self.assertIn("research_ready=false", details)
            for control in (
                window.run_detail_title,
                window.run_detail_summary,
                window.run_event_timeline,
                window.export_run_report_button,
                window.export_run_pdf_button,
            ):
                self.assertTrue(
                    control.winfo_ismapped(),
                    f"{control.winfo_class()} must be visible in the default window",
                )
            viewport_bottom = self.root.winfo_rooty() + self.root.winfo_height()
            summary_bottom = window.run_detail_summary.winfo_rooty() + window.run_detail_summary.winfo_height()
            timeline_bottom = window.run_event_timeline.winfo_rooty() + window.run_event_timeline.winfo_height()
            report_button_bottom = window.export_run_pdf_button.winfo_rooty() + window.export_run_pdf_button.winfo_height()
            self.assertLessEqual(summary_bottom, viewport_bottom, "run result details must fit in the default window")
            self.assertLessEqual(timeline_bottom, viewport_bottom, "the selected run timeline must fit in the default window")
            self.assertLessEqual(report_button_bottom, viewport_bottom, "run report actions must fit in the default window")
        finally:
            if self.root.winfo_exists():
                self.root.destroy()

    def test_late_event_response_cannot_replace_the_selected_run_timeline(self):
        api = self.main_window_module()
        first = self.run_for_report(api, "succeeded")
        second = api.Run(**{**first.__dict__, "run_id": "123e4567-e89b-12d3-a456-426614174025"})
        first_gate = Event()
        client = FakeApiClient(
            [
                api.DemoProjectOverview(
                    project_id="demo-research",
                    purpose="合成演示",
                    data_status="synthetic_only",
                    research_ready=False,
                    dataset_versions=("dataset-synthetic-v1",),
                    pipeline_templates=("research-smoke-v1",),
                    recent_public_runs=(),
                )
            ],
            projects=[api.ProjectListItem(
                project_id=first.project_id,
                name="合成演示项目",
                domain="generic-research",
                role="viewer",
            )],
            runs=[first, second],
            run_events={
                first.run_id: [api.RunEvent(sequence=1, status="queued", error_code=None, occurred_at="first-run-event")],
                second.run_id: [api.RunEvent(sequence=1, status="queued", error_code=None, occurred_at="second-run-event")],
            },
        )
        client.run_event_gates[first.run_id] = first_gate
        window = api.MainWindow(self.root, client=client)
        try:
            self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
            window.team_token_entry.insert(0, "team-test-token")
            window.connect_team_projects()
            self.assertTrue(
                self.wait_until(
                    lambda: first.run_id == window._recent_run_id
                    and second.run_id in window._run_cache
                )
            )
            window.open_recent_run_button.invoke()
            self.assertTrue(self.wait_until(lambda: any(run_id == first.run_id for _, run_id in client.run_event_access)))
            window.runs_tree.selection_set(second.run_id)
            window.runs_tree.event_generate("<<TreeviewSelect>>")
            timeline_text = lambda: window.run_event_timeline.get("1.0", "end-1c")
            self.assertTrue(self.wait_until(lambda: "second-run-event" in timeline_text()))
            first_gate.set()
            self.root.update()
            time.sleep(0.05)
            self.root.update()
            self.assertIn("second-run-event", timeline_text())
            self.assertNotIn("first-run-event", timeline_text())
        finally:
            first_gate.set()
            if self.root.winfo_exists():
                self.root.destroy()

    def test_overview_displays_latest_member_run_and_opens_its_detail(self):
        api = self.main_window_module()
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )

        def make_run(run_id, created_at, status):
            return api.Run(
                run_id=run_id,
                proposal_id="123e4567-e89b-12d3-a456-426614174021",
                project_id="123e4567-e89b-12d3-a456-426614174022",
                dataset_version="dataset-synthetic-v1",
                pipeline_template="research-smoke-v1",
                parameters={"sample_limit": 7},
                config_sha256="a" * 64,
                trace_id="123e4567-e89b-12d3-a456-426614174023",
                status=status,
                result={"processed_count": 7, "message": "本次只处理合成样例。"},
                error_code=None,
                created_at=created_at,
                started_at=created_at,
                finished_at=created_at,
            )

        newest_run = make_run(
            "123e4567-e89b-12d3-a456-426614174024",
            "2026-10-18T12:30:00Z",
            "succeeded",
        )
        older_run = make_run(
            "123e4567-e89b-12d3-a456-426614174025",
            "2026-10-17T12:30:00Z",
            "failed",
        )

        client = FakeApiClient(
            [overview],
            projects=[
                api.ProjectListItem(
                    project_id="123e4567-e89b-12d3-a456-426614174022",
                    name="合成演示项目",
                    domain="generic-research",
                    role="operator",
                )
            ],
            runs=[newest_run, older_run],
        )
        window = api.MainWindow(self.root, client=client)
        try:
            self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
            recent_run_summary = getattr(window, "recent_run_summary", None)
            self.assertIsNotNone(recent_run_summary, "the project overview must show a recent-run summary")

            window.team_token_entry.insert(0, "team-test-token")
            window.connect_team_projects()

            self.assertTrue(
                self.wait_until(
                    lambda: "research-smoke-v1" in recent_run_summary.cget("text")
                    and "2026-10-18 12:30" in recent_run_summary.cget("text")
                )
            )
            self.assertEqual(client.project_access_tokens, ["team-test-token"])
            self.assertEqual(client.run_access_tokens, ["team-test-token"])
            self.assertIn("已完成", recent_run_summary.cget("text"))

            window.open_recent_run_button.invoke()
            self.assertTrue(
                self.wait_until(
                    lambda: window.page_heading.cget("text") == "运行记录"
                    and newest_run.run_id in window.run_detail_summary.get("1.0", "end-1c")
                )
            )
            self.assertIn("synthetic_only=true", window.run_detail_summary.get("1.0", "end-1c"))
            window.clear_team_project_access()
            self.assertIn("连接团队账号", recent_run_summary.cget("text"))
            self.assertEqual(str(window.open_recent_run_button.cget("state")), "disabled")
        finally:
            if self.root.winfo_exists():
                self.root.destroy()

    def test_overview_reports_empty_and_failed_member_run_lists(self):
        api = self.main_window_module()
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )
        project = api.ProjectListItem(
            project_id="123e4567-e89b-12d3-a456-426614174022",
            name="合成演示项目",
            domain="generic-research",
            role="viewer",
        )
        client = FakeApiClient([overview], projects=[project], runs=[])
        window = api.MainWindow(self.root, client=client)
        try:
            self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
            window.team_token_entry.insert(0, "team-test-token")
            window.connect_team_projects()
            self.assertTrue(
                self.wait_until(lambda: "暂无运行记录" in window.recent_run_summary.cget("text"))
            )
            self.assertEqual(str(window.open_recent_run_button.cget("state")), "disabled")

            window.clear_team_project_access()
            client.runs = api.DesktopApiError("安全的授权错误")
            window.team_token_entry.insert(0, "team-test-token")
            window.connect_team_projects()
            self.assertTrue(
                self.wait_until(lambda: "暂时无法读取最近运行" in window.recent_run_summary.cget("text"))
            )
            self.assertNotIn("secret", window.recent_run_summary.cget("text"))
        finally:
            if self.root.winfo_exists():
                self.root.destroy()

    def test_displays_overview_quality_empty_state_and_sidebar_navigation(self):
        api = self.main_window_module()
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )
        window = api.MainWindow(self.root, client=FakeApiClient([overview]))

        try:
            self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
            window.quality_button.invoke()
            self.root.update()

            self.assertEqual(window.page_heading.cget("text"), "数据质量")
            self.assertEqual(window.quality_report_status.cget("text"), "暂无质量报告")
            self.assertIn("dataset-synthetic-v1", window.quality_dataset_versions.cget("text"))

            window.overview_button.invoke()
            self.root.update()
            self.assertEqual(window.page_heading.cget("text"), "项目总览")
        finally:
            self.root.destroy()

    def test_selecting_a_csv_runs_local_quality_check_and_shows_safe_summary(self):
        api = self.main_window_module()
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )
        content = (
            "record_id,group_id,split,label\n"
            "private-record-a,private-group,train,private-label\n"
            "private-record-a,private-group,train,private-label\n"
            "private-record-b,private-group,test,private-label\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.csv"
            manifest_path.write_text(content, encoding="utf-8", newline="")
            window = api.MainWindow(self.root, client=FakeApiClient([overview]))

            try:
                self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
                window.quality_button.invoke()
                self.assertTrue(
                    hasattr(window, "select_manifest_button"),
                    "The data quality page must expose a local manifest selector",
                )
                with patch.object(api.filedialog, "askopenfilename", return_value=str(manifest_path)):
                    window.select_manifest_button.invoke()

                self.assertTrue(self.wait_until(lambda: "阻断" in window.quality_report_status.cget("text")))
                self.assertIn("记录数：3", window.manifest_summary.cget("text"))
                self.assertIn("重复样本编号", window.manifest_issues.cget("text"))
                self.assertIn("分组跨拆分", window.manifest_issues.cget("text"))
                self.assertIn("建议", window.manifest_guidance.cget("text"))
                displayed_text = " ".join(
                    (
                        window.manifest_file_label.cget("text"),
                        window.manifest_summary.cget("text"),
                        window.manifest_issues.cget("text"),
                    )
                )
                self.assertNotIn("private-record", displayed_text)
                self.assertNotIn("private-group", displayed_text)
                self.assertNotIn("private-label", displayed_text)
            finally:
                self.root.destroy()

    def test_quality_page_displays_warning_and_success_with_non_approval_guidance(self):
        api = self.main_window_module()
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )
        with tempfile.TemporaryDirectory() as directory:
            warning_path = Path(directory) / "warning.csv"
            warning_path.write_text(
                "record_id,group_id,split,label,private-extra-header\n"
                "r-1,g-1,train,alpha,private-extra-value\n",
                encoding="utf-8",
                newline="",
            )
            success_path = Path(directory) / "success.csv"
            success_path.write_text(
                "record_id,group_id,split,label\n"
                "r-1,g-1,train,alpha\n",
                encoding="utf-8",
                newline="",
            )
            window = api.MainWindow(self.root, client=FakeApiClient([overview]))

            try:
                self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
                window.quality_button.invoke()
                window.run_manifest_check(warning_path)
                self.assertTrue(self.wait_until(lambda: "警告" in window.quality_report_status.cget("text")))
                self.assertIn("额外列", window.manifest_guidance.cget("text"))
                displayed_text = " ".join((window.manifest_issues.cget("text"), window.manifest_guidance.cget("text")))
                self.assertNotIn("private-extra-header", displayed_text)
                self.assertNotIn("private-extra-value", displayed_text)

                window.run_manifest_check(success_path)
                self.assertTrue(self.wait_until(lambda: "通过" in window.quality_report_status.cget("text")))
                self.assertIn("不代表数据已获授权", window.manifest_guidance.cget("text"))
            finally:
                self.root.destroy()

    def test_quality_page_reads_server_report_using_only_the_in_memory_team_token(self):
        api = self.main_window_module()
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )
        client = FakeApiClient([overview])
        report = api.DatasetQualityReport(
            dataset_version="dataset-synthetic-v1",
            status="success",
            rule_set_version="generic-manifest-v1",
            manifest_sha256="a" * 64,
            row_count=4,
            split_counts=(("test", 1), ("train", 2), ("validation", 1)),
            label_category_count=2,
            issues=(),
            synthetic_only=True,
            research_ready=False,
            checked_at="2026-10-17T12:00:00+00:00",
        )
        requested_tokens = []
        client.get_demo_quality_report = lambda token: requested_tokens.append(token) or report
        window = api.MainWindow(self.root, client=client)

        try:
            self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
            window.quality_button.invoke()
            window._project_token = "team-test-token"
            window.server_quality_check_button.invoke()
            self.assertTrue(self.wait_until(lambda: "通过" in window.server_quality_status.cget("text")))
            self.assertEqual(requested_tokens, ["team-test-token"])
            self.assertIn("generic-manifest-v1", window.server_quality_summary.cget("text"))
            self.assertIn("不代表科研就绪", window.server_quality_guidance.cget("text"))
        finally:
            self.root.destroy()

    def test_missing_required_columns_are_displayed_as_a_blocker(self):
        api = self.main_window_module()
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "missing-columns.csv"
            manifest_path.write_text("record_id,split\nr-1,train\n", encoding="utf-8", newline="")
            window = api.MainWindow(self.root, client=FakeApiClient([overview]))

            try:
                self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
                window.quality_button.invoke()
                window.run_manifest_check(manifest_path)
                self.assertTrue(self.wait_until(lambda: "阻断" in window.quality_report_status.cget("text")))
                self.assertIn("group_id", window.manifest_summary.cget("text"))
                self.assertIn("group_id", window.manifest_guidance.cget("text"))
            finally:
                self.root.destroy()

    def test_shows_backend_health_and_recovers_after_a_failed_check(self):
        api = self.main_window_module()
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )
        client = FakeApiClient(
            [overview],
            health_responses=[api.DesktopApiError("secret health detail"), None],
        )

        try:
            with self.assertLogs("ict_desktop.main_window", level="WARNING") as captured:
                window = api.MainWindow(self.root, client=client)
                self.assertTrue(self.wait_until(lambda: window.connection_status.cget("text") == "服务连接：不可用"))
            log_text = "\n".join(captured.output)
            self.assertIn("route=/health", log_text)
            self.assertNotIn("secret health detail", log_text)
            self.assertNotIn("secret health detail", window.error_message.cget("text"))

            window.reload_button.invoke()

            self.assertTrue(self.wait_until(lambda: window.connection_status.cget("text") == "服务连接：正常"))
            self.assertEqual(window.project_title.cget("text"), "合成研究演示项目")
        finally:
            self.root.destroy()

    def test_saves_a_new_service_address_and_switches_the_client(self):
        api = self.main_window_module()
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )
        saved_urls = []
        window = api.MainWindow(
            self.root,
            client=FakeApiClient([overview]),
            service_url="http://127.0.0.1:8765",
            settings_saver=saved_urls.append,
        )

        try:
            self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
            window.show_service_settings()
            window.service_url_entry.delete(0, "end")
            window.service_url_entry.insert(0, "https://api.example.com")
            window.load_overview = lambda: None

            window.save_service_settings()

            self.assertEqual(saved_urls, ["https://api.example.com"])
            self.assertEqual(window.api_base_url, "https://api.example.com")
            self.assertIsInstance(window.client, api.DemoProjectApiClient)
            self.assertEqual(window.service_settings_dialog.winfo_exists(), 0)
        finally:
            self.root.destroy()

    def test_rejects_remote_http_without_saving_the_address(self):
        api = self.main_window_module()
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )
        saved_urls = []
        window = api.MainWindow(
            self.root,
            client=FakeApiClient([overview]),
            service_url="http://127.0.0.1:8765",
            settings_saver=saved_urls.append,
        )

        try:
            self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
            window.show_service_settings()
            window.service_url_entry.delete(0, "end")
            window.service_url_entry.insert(0, "http://api.example.com")

            window.save_service_settings()

            self.assertEqual(saved_urls, [])
            self.assertEqual(window.api_base_url, "http://127.0.0.1:8765")
            self.assertEqual(window.service_settings_error.cget("text"), "服务地址无效；远程服务必须使用 HTTPS。")
            self.assertNotEqual(window.service_settings_dialog.winfo_exists(), 0)
        finally:
            self.root.destroy()

    def test_hides_internal_errors_and_retries_successfully(self):
        api = self.main_window_module()
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )
        try:
            with self.assertLogs("ict_desktop.main_window", level="WARNING") as captured:
                window = api.MainWindow(self.root, client=FakeApiClient([api.DesktopApiError("secret backend trace"), overview]))
                self.assertTrue(self.wait_until(lambda: bool(window.error_message.cget("text"))))
            safe_message = window.error_message.cget("text")
            log_text = "\n".join(captured.output)
            self.assertNotIn("secret backend trace", safe_message)
            self.assertNotIn("secret backend trace", log_text)
            self.assertIn("error_type=DesktopApiError", log_text)

            window.reload_button.invoke()
            self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
        finally:
            self.root.destroy()

    def test_quick_start_connects_member_and_opens_the_existing_read_only_proposal_page(self):
        api = self.main_window_module()
        project = api.ProjectListItem(
            project_id="123e4567-e89b-12d3-a456-426614174022",
            name="合成演示项目",
            domain="generic-research",
            role="operator",
        )
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )
        client = FakeApiClient([overview], projects=[project], runs=[])
        saved_urls = []
        window = api.MainWindow(
            self.root,
            client=client,
            service_url="https://api.example.test",
            settings_saver=saved_urls.append,
        )

        try:
            self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
            window.load_overview = lambda: None
            window.quick_start_button.invoke()
            wizard = window.quick_start_wizard
            self.assertIsNotNone(wizard)
            self.assertEqual(wizard.step, 1)

            wizard.save_service_and_continue()
            window.client = client
            wizard.check_api_button.invoke()
            self.assertTrue(self.wait_until(lambda: "API 可连接" in wizard.status_label.cget("text")))
            wizard.advance()
            wizard.team_token_entry.insert(0, "quick-start-team-token")
            wizard.connect_team_button.invoke()

            self.assertTrue(self.wait_until(lambda: "操作者" in wizard.team_roles_label.cget("text")))
            self.assertEqual(client.project_access_tokens, ["quick-start-team-token"])
            self.assertEqual(window.team_token_entry.get(), "")
            self.assertTrue(self.wait_until(lambda: not window._run_loading))
            wizard.advance()
            wizard.open_proposals_page()
            self.assertTrue(self.wait_until(lambda: not window._proposal_loading))

            self.assertEqual(wizard.step, 4)
            self.assertEqual(window.page_heading.cget("text"), "智能体提案")
            self.assertEqual(client.proposal_access_tokens, ["quick-start-team-token"])
            self.assertEqual(window.proposals_status.cget("text"), "当前账号暂无可见提案。")
            self.assertEqual(saved_urls, ["https://api.example.test"])
            self.assertFalse(wizard.dialog.winfo_exists())
        finally:
            self.root.destroy()

    def test_quick_start_rejects_remote_http_without_saving(self):
        api = self.main_window_module()
        overview = api.DemoProjectOverview(
            project_id="demo-research",
            purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )
        saved_urls = []
        window = api.MainWindow(
            self.root,
            client=FakeApiClient([overview]),
            service_url="https://api.example.test",
            settings_saver=saved_urls.append,
        )

        try:
            self.assertTrue(self.wait_until(lambda: window.project_title.cget("text") == "合成研究演示项目"))
            window.load_overview = lambda: None
            window.quick_start_button.invoke()
            wizard = window.quick_start_wizard
            wizard.service_url_entry.delete(0, "end")
            wizard.service_url_entry.insert(0, "http://api.example.test")

            wizard.save_service_and_continue()

            self.assertEqual(saved_urls, [])
            self.assertEqual(window.api_base_url, "https://api.example.test")
            self.assertEqual(wizard.step, 1)
            self.assertIn("HTTPS", wizard.status_label.cget("text"))
        finally:
            self.root.destroy()


if __name__ == "__main__":
    unittest.main()
