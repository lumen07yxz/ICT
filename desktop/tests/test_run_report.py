"""Run report tests cover the local, synthetic-only HTML artifact contract."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_ROOT))

from ict_desktop.api import Run, RunEvent
from ict_desktop import report_export
from ict_desktop.report_export import REPORT_TEMPLATE_VERSION, render_run_report


class RunReportTests(unittest.TestCase):
    def make_run(self, status="succeeded", result=None, error_code=None):
        if result is None and status == "succeeded":
            result = {
                "task": "synthetic_smoke",
                "processed_count": 7,
                "synthetic_only": True,
                "research_ready": False,
                "message": "集成冒烟任务完成。",
            }
        return Run(
            run_id="123e4567-e89b-12d3-a456-426614174020",
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

    def test_success_report_contains_run_provenance_and_marks_unavailable_research_fields(self):
        report = render_run_report(
            self.make_run(),
            generated_at=datetime(2026, 10, 19, 1, 2, 3, tzinfo=timezone.utc),
        )

        self.assertIn(REPORT_TEMPLATE_VERSION, report)
        self.assertIn("123e4567-e89b-12d3-a456-426614174020", report)
        self.assertIn("123e4567-e89b-12d3-a456-426614174023", report)
        self.assertIn("dataset-synthetic-v1", report)
        self.assertIn("generic-manifest-v1", report)
        self.assertIn("处理合成样例数", report)
        self.assertIn("研究目标", report)
        self.assertIn("未登记；当前仅验证固定冒烟模板的受控运行与状态回传", report)
        self.assertIn("非 AgentArts 平台 Trace", report)
        self.assertIn("未登记", report)
        self.assertIn("未生成", report)
        self.assertIn("2026-10-19T01:02:03Z", report)
        self.assertIn("research_ready=false", report)

    def test_report_includes_ordered_persisted_status_events(self):
        events = [
            RunEvent(sequence=1, status="queued", error_code=None, occurred_at="2026-10-19T12:00:00Z"),
            RunEvent(sequence=2, status="running", error_code=None, occurred_at="2026-10-19T12:00:01Z"),
            RunEvent(sequence=3, status="failed", error_code="WORKER_EXECUTION_FAILED", occurred_at="2026-10-19T12:00:02Z"),
        ]

        report = render_run_report(
            self.make_run(status="failed", error_code="WORKER_EXECUTION_FAILED"),
            events=events,
        )

        self.assertIn("运行状态时间线", report)
        timeline = report.split("<h2>运行状态时间线</h2>", 1)[1].split("</section>", 1)[0]
        self.assertLess(timeline.index("排队中"), timeline.index("运行中"))
        self.assertLess(timeline.index("运行中"), timeline.index("运行失败"))
        self.assertIn("2026-10-19T12:00:00Z", report)
        self.assertIn("WORKER_EXECUTION_FAILED", report)
        self.assertIn("2026-10-19T12:00:02Z", report)

    def test_report_rejects_malformed_event_error_code_without_crashing(self):
        event = RunEvent(
            sequence=3,
            status="failed",
            error_code=["<script>"],
            occurred_at="2026-10-19T12:00:02Z",
        )

        with self.assertRaises(ValueError):
            render_run_report(self.make_run(status="failed"), events=[event])

    def test_report_distinguishes_unread_events_from_empty_server_timeline(self):
        run = self.make_run()

        unread_report = render_run_report(run)
        empty_report = render_run_report(run, events=[])

        self.assertIn("导出时未能取得运行状态事件", unread_report)
        self.assertIn("服务端未提供状态事件记录", empty_report)

    def test_pdf_report_renderer_returns_a_complete_pdf_document(self):
        renderer = getattr(report_export, "render_run_pdf", None)
        self.assertTrue(callable(renderer), "A native PDF renderer is required for desktop report export.")
        if not callable(renderer):
            return

        document = renderer(
            self.make_run(),
            generated_at=datetime(2026, 10, 19, 1, 2, 3, tzinfo=timezone.utc),
        )

        self.assertIsInstance(document, bytes)
        self.assertTrue(document.startswith(b"%PDF-"))
        self.assertTrue(document.rstrip().endswith(b"%%EOF"))

    def test_report_escapes_result_text_and_does_not_render_html_from_run_data(self):
        result = {
            "task": "synthetic_smoke",
            "processed_count": 7,
            "synthetic_only": True,
            "research_ready": False,
            "message": "<script>alert('x')</script>",
        }
        report = render_run_report(self.make_run(result=result))

        self.assertIn("&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;", report)
        self.assertNotIn("<script>alert", report)

    def test_failed_run_report_shows_failure_and_explicitly_omits_metrics(self):
        report = render_run_report(self.make_run(status="failed", error_code="SYNTHETIC_TASK_FAILED"))

        self.assertIn("运行失败", report)
        self.assertIn("SYNTHETIC_TASK_FAILED", report)
        self.assertIn("科研评价指标", report)
        self.assertIn(">未生成；此冒烟任务不执行模型评价<", report)
        self.assertIn("research_ready=false", report)

    def test_report_rejects_nonterminal_runs(self):
        with self.assertRaises(ValueError):
            render_run_report(self.make_run(status="running", result=None))

    def test_success_report_rejects_a_missing_result_snapshot(self):
        with self.assertRaises(ValueError):
            render_run_report(self.make_run(result={}))


if __name__ == "__main__":
    unittest.main()
