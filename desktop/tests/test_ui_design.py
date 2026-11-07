"""Behavior checks for the Windows research workbench UI refresh."""

from __future__ import annotations

import sys
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from tkinter import font as tkfont
from tkinter import ttk
from unittest.mock import patch


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_ROOT))

from ict_desktop.api import DemoProjectOverview
from ict_desktop.manifest_quality import ManifestIssue, ManifestQualityReport
from ict_desktop.main_window import MainWindow
from ict_desktop.ui_theme import COLORS, FONTS
from ict_desktop import ui_theme


def _contrast_ratio(foreground: str, background: str) -> float:
    def relative_luminance(color: str) -> float:
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return sum(channel * luminance for channel, luminance in zip((0.2126, 0.7152, 0.0722), linear))

    lighter, darker = sorted((relative_luminance(foreground), relative_luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class StubApiClient:
    def check_health(self) -> None:
        return None

    def get_overview(self) -> DemoProjectOverview:
        return DemoProjectOverview(
            project_id="demo-research",
            purpose="仅供软件联调使用的合成研究样例。",
            data_status="synthetic_only",
            research_ready=False,
            dataset_versions=("dataset-synthetic-v1",),
            pipeline_templates=("research-smoke-v1",),
            recent_public_runs=(),
        )


class UiDesignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.callback_errors = []
        self.root.report_callback_exception = lambda error_type, value, _traceback: self.callback_errors.append((error_type, value))
        self.window = MainWindow(self.root, client=StubApiClient())
        deadline = time.monotonic() + 2
        while self.window._loading and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.root.update_idletasks()

    def tearDown(self) -> None:
        try:
            self.root.update_idletasks()
            self.root.destroy()
        except tk.TclError:
            pass
        self.assertEqual(self.callback_errors, [], "Tk layout callbacks must not fail silently")

    def test_navigation_marks_one_page_active_and_updates_context(self) -> None:
        self.window.show_quality()
        self.root.update_idletasks()

        self.assertEqual(self.window.page_heading.cget("text"), "数据质量")
        self.assertEqual(
            self.window.page_context.cget("text"),
            "本机 CSV 预检与服务器登记清单报告。",
        )
        self.assertEqual(self.window.workspace_breadcrumb.cget("text"), "ICT  /  科研工作区")
        self.assertEqual(self.window.page_index_label.cget("text"), "02")
        self.assertEqual(self.window.quality_button.cget("style"), "NavActive.TButton")
        for button in (
            self.window.overview_button,
            self.window.team_projects_button,
            self.window.proposals_button,
            self.window.runs_button,
        ):
            self.assertEqual(button.cget("style"), "Nav.TButton")

        self.window.show_runs()
        self.assertEqual(self.window.runs_button.cget("style"), "NavActive.TButton")
        self.assertEqual(self.window.page_index_label.cget("text"), "05")
        self.assertEqual(self.window.quality_button.cget("style"), "Nav.TButton")

    def test_unavailable_service_uses_subdued_topbar_status(self) -> None:
        self.window._set_connection_status("error")

        status_style = ttk.Style(self.root)
        self.assertEqual(self.window.connection_status.cget("style"), "Connection.Offline.TLabel")
        self.assertIn("不可用", self.window.connection_status.cget("text"))
        self.assertEqual(status_style.lookup("Connection.Offline.TLabel", "background"), COLORS["paper"])
        self.assertEqual(status_style.lookup("Connection.Offline.TLabel", "foreground"), COLORS["muted"])

    def test_error_banner_only_occupies_space_when_it_has_a_message(self) -> None:
        self.assertEqual(self.window.error_message.winfo_manager(), "")

        self.window._set_error_message("无法连接项目服务。")
        self.assertEqual(self.window.error_message.winfo_manager(), "pack")

        self.window._set_error_message("")
        self.assertEqual(self.window.error_message.winfo_manager(), "")

    def test_offline_connection_notice_offers_direct_local_csv_check(self) -> None:
        self.window._set_error_message("无法连接项目服务。本机 CSV 预检仍可使用。")

        self.assertEqual(self.window.offline_quality_button.winfo_manager(), "pack")
        self.window.offline_quality_button.invoke()

        self.assertEqual(self.window._active_page, "quality")
        self.assertIsNone(self.window._project_token)

    def test_overview_connection_notice_does_not_cover_local_quality_work(self) -> None:
        self.window._set_error_message("项目服务连接失败。")
        self.assertEqual(self.window.error_message.winfo_manager(), "pack")

        self.window.show_quality()
        self.assertEqual(self.window.error_message.winfo_manager(), "")
        self.assertEqual(self.window.error_message.cget("text"), "项目服务连接失败。")

        self.window.show_overview()
        self.assertEqual(self.window.error_message.winfo_manager(), "pack")

    def test_failed_refresh_keeps_the_last_loaded_project_snapshot(self) -> None:
        title = self.window.project_title.cget("text")
        versions = self.window.dataset_versions.cget("text")
        self.window._result_queue.put(("health_error", "项目服务连接失败。"))
        self.window._poll_result_queue()

        self.assertEqual(self.window.project_title.cget("text"), title)
        self.assertEqual(self.window.dataset_versions.cget("text"), versions)
        self.assertIn("上次", self.window.error_message.cget("text"))

    def test_offline_overview_opens_local_csv_checks_without_a_service_request(self) -> None:
        self.window._overview = None
        self.window._result_queue.put(("health_error", "项目服务连接失败。"))
        self.window._poll_result_queue()
        action = getattr(self.window, "overview_quality_button", None)
        self.assertIsNotNone(action, "offline users need a direct route to local CSV checks")

        with patch.object(self.window.client, "get_overview") as request:
            action.invoke()
        request.assert_not_called()
        self.assertEqual(self.window._active_page, "quality")
        self.assertTrue(self.window.select_manifest_button.instate(["!disabled"]))

    def test_initial_window_leaves_room_for_screen_edges_at_display_scaling(self) -> None:
        for width, height in ((1280, 720), (1536, 864), (1920, 1080)):
            with self.subTest(screen=(width, height)), patch.object(self.root, "winfo_screenwidth", return_value=width), patch.object(self.root, "winfo_screenheight", return_value=height), patch.object(self.root, "geometry") as geometry:
                self.window._fit_initial_window_to_screen()
                requested_width, requested_height = map(int, geometry.call_args.args[0].split("x"))
                self.assertLessEqual(requested_width, width - 64)
                self.assertLessEqual(requested_height, height - 100)
                self.assertLessEqual(self.root.minsize()[0], requested_width)
                self.assertLessEqual(self.root.minsize()[1], requested_height)

    def test_service_settings_wraps_guidance_when_resized(self) -> None:
        self.root.deiconify()
        self.root.geometry("900x700")
        self.window.show_service_settings()
        dialog = self.window.service_settings_dialog
        dialog.geometry("480x300")
        self.window.service_settings_error.configure(text="服务地址校验失败，请检查输入。" * 10)
        self.window.service_settings_error.pack(anchor="w", pady=(6, 0))
        self.root.update()

        self.assertEqual(dialog.resizable(), (1, 1))
        self.assertLessEqual(self.window.service_settings_guidance.cget("wraplength"), 420)
        self.assertLessEqual(
            self.window.service_settings_save_button.winfo_rooty()
            + self.window.service_settings_save_button.winfo_height(),
            dialog.winfo_rooty() + dialog.winfo_height(),
        )

    def test_overview_identity_and_readiness_stack_in_narrow_viewport(self) -> None:
        self.root.deiconify()
        self.root.minsize(1, 1)
        self.root.geometry("800x680")
        self.root.update()

        self.assertEqual(self.window.overview_header_readiness.grid_info()["row"], 2)
        self.root.geometry("1200x780")
        self.root.update()
        self.assertEqual(self.window.overview_header_readiness.grid_info()["row"], 0)

    def test_overview_resource_panel_fits_the_first_working_viewport(self) -> None:
        self.root.deiconify()
        self.root.geometry("1200x800")
        self.window._set_error_message("无法连接项目服务。")
        self.window.show_overview()
        self.root.update()

        resource_bottom = self.window.overview_resources.winfo_rooty() + self.window.overview_resources.winfo_height()
        viewport_bottom = self.window.page_canvas.winfo_rooty() + self.window.page_canvas.winfo_height()
        self.assertLessEqual(
            resource_bottom,
            viewport_bottom,
            "the overview should show all project resources without scrolling at a working desktop size",
        )

    def test_switching_service_drops_the_previous_servers_overview_snapshot(self) -> None:
        self.assertIsNotNone(self.window._overview)
        self.window._settings_saver = lambda _url: None
        with patch.object(self.window, "load_overview"):
            error = self.window._save_service_url("https://api.example.com")
        self.assertIsNone(error)
        self.assertIsNone(self.window._overview)
        self.assertNotIn("dataset-synthetic-v1", self.window.dataset_versions.cget("text"))

    def test_member_pages_offer_a_direct_connection_without_submitting_credentials(self) -> None:
        action = getattr(self.window, "team_connection_button", None)
        self.assertIsNotNone(action)
        for page in ("quality", "proposals", "runs"):
            with self.subTest(page=page):
                getattr(self.window, f"show_{page}")()
                self.assertEqual(action.winfo_manager(), "pack")
                with patch.object(self.window, "connect_team_projects") as connect:
                    action.invoke()
                connect.assert_not_called()
                self.assertEqual(self.window._active_page, "projects")
                self.assertEqual(self.window.team_token_entry.get(), "")
        self.window.show_overview()
        self.assertEqual(action.winfo_manager(), "")

    def test_settings_error_has_no_empty_red_mark_and_appears_on_validation_failure(self) -> None:
        self.window.show_service_settings()
        self.assertEqual(self.window.service_settings_error.winfo_manager(), "")
        self.window.service_url_entry.delete(0, "end")
        self.window.service_url_entry.insert(0, "http://remote.example.com")
        with patch.object(self.window, "_settings_saver") as save:
            self.window.save_service_settings()
        save.assert_not_called()
        self.assertEqual(self.window.service_settings_error.winfo_manager(), "pack")
        self.assertIn("HTTPS", self.window.service_settings_error.cget("text"))

    def test_workbench_uses_a_deep_graphite_workspace(self) -> None:
        channels = [int(COLORS["paper"][index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        luminance = sum(channel * value for channel, value in zip((0.2126, 0.7152, 0.0722), linear))

        self.assertLess(luminance, 0.03)

    def test_overview_uses_editorial_canvas_and_one_framed_resource_surface(self) -> None:
        style = ttk.Style(self.root)

        self.assertEqual(self.window.overview_header.cget("style"), "App.TFrame")
        self.assertEqual(self.window.overview_header_identity.cget("style"), "App.TFrame")
        self.assertEqual(self.window.overview_header_readiness.cget("style"), "App.TFrame")
        self.assertEqual(style.lookup("Workflow.TFrame", "background"), COLORS["paper"])
        self.assertEqual(self.window.overview_resources.cget("style"), "Pane.TFrame")

    def test_workbench_typography_has_a_clear_readable_scale(self) -> None:
        self.assertGreaterEqual(FONTS["ui"][1], 10)
        self.assertGreaterEqual(FONTS["ui_small"][1], 9)
        self.assertGreaterEqual(FONTS["title"][1], 20)
        self.assertGreater(FONTS["title"][1], FONTS["ui_bold"][1])

    def test_component_styles_follow_the_shared_typographic_hierarchy(self) -> None:
        style = ttk.Style(self.root)
        components = (
            ("Brand.TLabel", "brand"),
            ("Section.TLabel", "overline"),
            ("Eyebrow.TLabel", "overline"),
            ("CardTitle.TLabel", "card_title"),
            ("InputLabel.TLabel", "ui_bold"),
            ("AccessInputLabel.TLabel", "ui_bold"),
            ("QualityWarning.TLabel", "quality_status"),
            ("WizardStep.TLabel", "overline"),
            ("WizardTitle.TLabel", "wizard_title"),
            ("ProjectTitle.TLabel", "project_title"),
        )

        for style_name, token_name in components:
            with self.subTest(style=style_name):
                expected = FONTS[token_name]
                actual = tkfont.Font(root=self.root, font=style.lookup(style_name, "font")).actual()
                self.assertEqual(actual["family"], expected[0])
                self.assertEqual(abs(int(actual["size"])), expected[1])
                self.assertEqual(actual["weight"], "bold" if "bold" in expected[2:] else "normal")

    def test_connection_error_copy_is_at_least_body_text_size(self) -> None:
        actual = tkfont.Font(root=self.root, font=self.window.error_message.cget("font")).actual()

        self.assertGreaterEqual(abs(int(actual["size"])), FONTS["ui"][1])

    def test_overview_workflow_actions_navigate_without_credentials(self) -> None:
        actions = getattr(self.window, "overview_workflow_actions", [])
        self.assertEqual(len(actions), 4, "each real workflow step needs a direct page action")
        expected_pages = ("projects", "quality", "proposals", "runs")

        for action, page in zip(actions, expected_pages):
            with self.subTest(page=page):
                self.assertIsNone(self.window._project_token)
                action.invoke()
                self.assertEqual(self.window._active_page, page)
                self.assertIsNone(self.window._project_token)
                self.window.show_overview()

    def test_synthetic_scope_is_visible_in_the_status_strip(self) -> None:
        scope_status = getattr(self.window, "scope_status_label", None)
        self.assertIsNotNone(scope_status)
        self.assertEqual(scope_status.winfo_manager(), "pack")
        self.assertIn("SYNTHETIC_ONLY", scope_status.cget("text"))
        self.assertIn("research_ready=false", scope_status.cget("text"))

    def test_synthetic_scope_uses_an_informational_accent_with_aa_contrast(self) -> None:
        scope_color = ttk.Style(self.root).lookup("Status.Scope.TLabel", "foreground")

        self.assertEqual(scope_color, COLORS["accent_text"])
        self.assertGreaterEqual(_contrast_ratio(scope_color, COLORS["sidebar"]), 4.5)

    def test_data_pages_use_adjustable_list_and_inspector_workspaces(self) -> None:
        self.root.deiconify()
        self.root.minsize(1, 1)
        self.root.geometry("1366x768")
        self.root.update()

        for page_name, workspace_name in (
            ("quality", "quality_workspace"),
            ("projects", "project_workspace"),
            ("proposals", "proposal_workspace"),
            ("runs", "run_workspace"),
        ):
            with self.subTest(page=page_name):
                getattr(self.window, f"show_{page_name}")()
                self.root.update()
                workspace = getattr(self.window, workspace_name, None)
                self.assertIsInstance(workspace, tk.PanedWindow)
                self.assertEqual(str(workspace.cget("orient")), "horizontal")
                self.assertEqual(len(workspace.panes()), 2)
                self.assertEqual(workspace.cget("background"), COLORS["paper"])
                self.assertEqual(int(workspace.cget("sashwidth")), 5)
                self.assertEqual(workspace.cget("sashrelief"), "flat")

    def test_business_lists_have_clear_titles_without_duplicate_quality_navigation(self) -> None:
        self.assertEqual(self.window.proposals_list_title.cget("text"), "提案列表")
        self.assertEqual(self.window.runs_list_title.cget("text"), "运行列表")
        self.assertFalse(
            any(
                isinstance(widget, ttk.Button) and widget.cget("text") == "返回项目总览"
                for widget in self.window.quality_page.winfo_children()
            ),
            "the persistent sidebar already provides project overview navigation",
        )

    def test_queue_workspaces_prioritize_list_scanning_over_inspector_width(self) -> None:
        for workspace_name in ("project_workspace", "proposal_workspace", "run_workspace"):
            with self.subTest(workspace=workspace_name):
                workspace = getattr(self.window, workspace_name)
                self.assertAlmostEqual(workspace._sash_horizontal_fraction, 5 / 9)

        # The quality page compares two forms and keeps its balanced split.
        self.assertAlmostEqual(self.window.quality_workspace._sash_horizontal_fraction, 0.5)

    def test_inspector_guidance_wraps_to_its_resized_panel(self) -> None:
        self.window.show_quality()
        panel = getattr(self.window, "quality_local_panel", None)
        self.assertIsNotNone(panel)
        self.root.update_idletasks()

        panel.event_generate("<Configure>", width=420, height=260)

        self.assertEqual(int(self.window.manifest_guidance.cget("wraplength")), 384)

    def test_business_inspectors_use_labeled_metadata_rows(self) -> None:
        for attribute in ("project_detail_summary", "proposal_detail_summary", "run_detail_summary"):
            self.assertIsInstance(getattr(self.window, attribute), tk.Text)

        inspector = self.window.project_detail_summary
        self.assertEqual(inspector.cget("state"), "disabled")
        self.assertIn("field_label", inspector.tag_names())
        self.assertIn("field_value", inspector.tag_names())
        label_font = tkfont.Font(root=self.root, font=inspector.tag_cget("field_label", "font")).actual()
        value_font = tkfont.Font(root=self.root, font=inspector.tag_cget("field_value", "font")).actual()
        self.assertLess(abs(int(label_font["size"])), abs(int(value_font["size"])))

    def test_detail_inspector_owns_mousewheel_while_its_content_can_scroll(self) -> None:
        self.window.show_runs()
        inspector = self.window.run_detail_summary
        self.window._set_detail_fields(
            inspector,
            [(f"字段 {index}", "用于滚动验收的详情内容 " * 5, "field_value") for index in range(24)],
        )
        self.root.update_idletasks()
        inspector.yview_moveto(0.0)
        inspector_position = inspector.yview()
        page_position = self.window.page_canvas.yview()

        result = self.window._on_page_mousewheel(SimpleNamespace(widget=inspector, delta=-120))

        self.assertEqual(result, "break")
        self.assertNotEqual(inspector.yview(), inspector_position)
        self.assertEqual(self.window.page_canvas.yview(), page_position)

    def test_destroy_cancels_pending_detail_and_layout_callbacks(self) -> None:
        self.window._project_detail_loading = True
        self.window._poll_project_detail_result()
        self.window.show_quality()
        pending = set(self.root.tk.splitlist(self.root.tk.call("after", "info")))
        self.assertTrue(pending)

        self.root.destroy()
        remaining = set(self.root.tk.splitlist(self.root.tk.call("after", "info")))
        try:
            self.assertFalse(pending & remaining, "destroyed window must leave no queued Tk callbacks")
        finally:
            for after_id in remaining:
                self.root.tk.call("after", "cancel", after_id)

    def test_long_quality_page_has_a_scrollable_viewport(self) -> None:
        self.root.deiconify()
        self.root.geometry("1200x800")
        self.window.show_quality()
        self.window.manifest_guidance.configure(text="\n".join(f"第 {index} 条修复建议" for index in range(35)))
        self.window._schedule_page_viewport_refresh()
        self.root.update()

        page_canvas = getattr(self.window, "page_canvas", None)
        self.assertIsNotNone(page_canvas, "long pages need a scrollable viewport")
        region = tuple(float(value) for value in page_canvas.cget("scrollregion").split())
        self.assertGreaterEqual(region[3] - region[1], self.window.quality_page.winfo_reqheight())
        self.assertEqual(self.window.page_scrollbar.winfo_manager(), "pack")
        page_canvas.yview_moveto(1.0)
        self.assertGreater(page_canvas.yview()[0], 0.0)

    def test_switching_to_short_page_resets_scroll_position(self) -> None:
        self.root.deiconify()
        self.root.geometry("1200x800")
        self.window.show_quality()
        self.window.manifest_guidance.configure(text="\n".join(f"第 {index} 条修复建议" for index in range(35)))
        self.window._schedule_page_viewport_refresh()
        self.root.update()
        page_canvas = getattr(self.window, "page_canvas", None)
        self.assertIsNotNone(page_canvas, "pages need a shared scrollable viewport")

        page_canvas.yview_moveto(1.0)
        self.window.show_overview()
        self.root.update_idletasks()

        self.assertEqual(page_canvas.yview()[0], 0.0)
        region = tuple(float(value) for value in page_canvas.cget("scrollregion").split())
        self.assertLess(region[3] - region[1], self.window.quality_page.winfo_reqheight())

    def test_async_quality_result_expands_scroll_region(self) -> None:
        self.window.show_quality()
        self.root.update_idletasks()
        long_guidance = "\n".join(f"第 {index} 条修复建议" for index in range(30))
        report = ManifestQualityReport(
            row_count=1,
            columns=("record_id", "group_id", "split", "label"),
            sha256="a" * 64,
            split_counts=(("train", 1),),
            label_category_count=1,
            issues=(
                ManifestIssue(
                    code="review_guidance",
                    message="存在需核对的项目。",
                    count=1,
                    line_numbers=(),
                    severity="warning",
                    guidance=long_guidance,
                ),
            ),
        )
        self.window._quality_result_queue.put(("success", report))
        self.window._poll_manifest_result_queue()
        self.root.update_idletasks()

        region = tuple(float(value) for value in self.window.page_canvas.cget("scrollregion").split())
        self.assertGreaterEqual(region[3] - region[1], self.window.quality_page.winfo_reqheight())

    def test_palette_uses_neutral_graphite_and_mineral_teal_identity(self) -> None:
        self.assertEqual(COLORS["paper"], "#151917")
        self.assertEqual(COLORS["surface"], "#1D2420")
        self.assertEqual(COLORS["surface_alt"], "#262F29")
        self.assertEqual(COLORS["accent"], "#356457")
        self.assertEqual(COLORS["accent_hover"], "#2D544A")
        self.assertEqual(COLORS["accent_text"], "#A3D2BC")

    def test_small_theme_text_meets_wcag_aa_contrast(self) -> None:
        text_pairs = {
            "primary button": (COLORS["white"], COLORS["accent"]),
            "muted text on paper": (COLORS["muted"], COLORS["paper"]),
            "muted text on surface": (COLORS["muted"], COLORS["surface"]),
            "muted text on alternate surface": (COLORS["muted"], COLORS["surface_alt"]),
            "success status on surface": (COLORS["moss"], COLORS["surface"]),
            "success connection on alternate surface": (COLORS["moss"], COLORS["surface_alt"]),
            "sidebar text": (COLORS["sidebar_text"], COLORS["sidebar"]),
            "sidebar muted text": (COLORS["sidebar_muted"], COLORS["sidebar"]),
            "scope status on sidebar": (COLORS["accent_text"], COLORS["sidebar"]),
            "error callout text": (COLORS["danger_text"], COLORS["error"]),
            "accent text on workspace": (COLORS["accent_text"], COLORS["paper"]),
            "accent text on panel": (COLORS["accent_text"], COLORS["surface"]),
            "focus ring": (COLORS["accent_text"], COLORS["sidebar"]),
            "primary button hover": (COLORS["white"], COLORS["accent_hover"]),
        }
        for label, (foreground, background) in text_pairs.items():
            with self.subTest(label=label):
                self.assertGreaterEqual(_contrast_ratio(foreground, background), 4.5)

    def test_interactive_focus_indicators_use_the_mineral_accent(self) -> None:
        style = ttk.Style(self.root)
        components = (
            ("TButton", COLORS["surface_alt"]),
            ("Nav.TButton", COLORS["sidebar"]),
            ("NavActive.TButton", COLORS["sidebar_active"]),
            ("WorkflowAction.TButton", COLORS["paper"]),
            ("Primary.TButton", COLORS["accent"]),
            ("Quiet.TButton", COLORS["surface_alt"]),
            ("AccessQuiet.TButton", COLORS["surface"]),
            ("Toolbar.TButton", COLORS["paper"]),
        )

        for style_name, background in components:
            with self.subTest(style=style_name):
                focus_color = style.lookup(style_name, "focuscolor")
                self.assertEqual(focus_color.casefold(), COLORS["accent_text"].casefold())
                self.assertGreaterEqual(_contrast_ratio(focus_color, background), 3.0)

    def test_table_empty_states_have_contextual_noninteractive_symbols(self) -> None:
        states = (
            ("projects", self.window.project_table_empty_state),
            ("proposals", self.window.proposal_table_empty_state),
            ("runs", self.window.runs_table_empty_state),
        )

        for kind, state in states:
            with self.subTest(kind=kind):
                self.assertEqual(len(state), 4, "empty states should include a decorative symbol canvas")
                _frame, symbol, _title, _description = state
                self.assertEqual(str(symbol.cget("takefocus")), "0")
                self.assertEqual(symbol.winfo_manager(), "pack")
                self.assertTrue(
                    symbol.find_withtag(f"empty-state:{kind}"),
                    "each queue needs its own object-specific line mark",
                )

    def test_input_label_styles_meet_aa_contrast_on_their_surfaces(self) -> None:
        style = ttk.Style(self.root)
        components = (
            ("InputLabel.TLabel", COLORS["surface"]),
            ("AccessInputLabel.TLabel", COLORS["surface_alt"]),
        )

        for style_name, expected_background in components:
            with self.subTest(style=style_name):
                foreground = style.lookup(style_name, "foreground")
                background = style.lookup(style_name, "background")
                self.assertEqual(foreground, COLORS["ink"])
                self.assertEqual(background, expected_background)
                self.assertGreaterEqual(_contrast_ratio(foreground, background), 4.5)

    def test_quality_workspace_reflows_without_clipping_either_panel(self) -> None:
        self.root.deiconify()
        self.root.minsize(1, 1)

        for geometry in ("1000x720", "1366x768"):
            with self.subTest(geometry=geometry):
                self.root.geometry(geometry)
                self.window.show_quality()
                self.root.update()
                left_panel, right_panel = self.window.quality_workspace.winfo_children()
                self.assertGreaterEqual(
                    left_panel.winfo_height(),
                    left_panel.winfo_reqheight(),
                    f"local CSV guidance must remain visible at {geometry}",
                )
                self.assertGreaterEqual(
                    right_panel.winfo_height(),
                    right_panel.winfo_reqheight(),
                    f"server quality guidance must remain visible at {geometry}",
                )
    def test_quality_form_workspace_uses_content_height(self) -> None:
        self.root.deiconify()
        self.root.geometry("1400x900")
        self.window.show_quality()
        self.root.update()

        workspace_height = self.window.quality_workspace.winfo_height()
        viewport_height = self.window.page_canvas.winfo_height()
        self.assertLess(
            workspace_height,
            viewport_height - 100,
            "the compact CSV check forms should not stretch into a full-height empty frame",
        )

    def test_proposal_and_run_actions_fit_inside_the_first_viewport(self) -> None:
        self.root.deiconify()
        self.root.geometry("1280x720")

        cases = (
            ("proposals", self.window.approve_proposal_button),
            ("runs", self.window.export_run_report_button),
        )
        for page, action in cases:
            with self.subTest(page=page):
                getattr(self.window, f"show_{page}")()
                self.root.update()
                viewport_top = self.window.page_canvas.winfo_rooty()
                viewport_bottom = viewport_top + self.window.page_canvas.winfo_height()
                action_top = action.winfo_rooty()
                action_bottom = action_top + action.winfo_height()
                self.assertGreaterEqual(action_top, viewport_top)
                self.assertLessEqual(
                    action_bottom,
                    viewport_bottom,
                    "primary inspector actions should be visible without scrolling the whole page",
                )

    def test_business_workspaces_stack_on_narrow_views_and_restore_on_wide_views(self) -> None:
        self.root.deiconify()
        self.root.minsize(1, 1)
        workspaces = {
            "quality": self.window.quality_workspace,
            "projects": self.window.project_workspace,
            "proposals": self.window.proposal_workspace,
            "runs": self.window.run_workspace,
        }

        for width, height, expected in (
            (1000, 720, "vertical"),
            (1200, 800, "horizontal"),
            (1366, 768, "horizontal"),
        ):
            with self.subTest(viewport=(width, height), orientation=expected):
                self.root.geometry(f"{width}x{height}")
                for page, workspace in workspaces.items():
                    getattr(self.window, f"show_{page}")()
                    self.root.update()
                    self.assertEqual(
                        str(workspace.cget("orient")),
                        expected,
                        f"{page} must preserve a usable list and inspector at {width}px work-area width",
                    )
                if expected == "horizontal":
                    # Let the resize debounce place sashes against this final wide viewport.
                    self.root.after(160, self.root.quit)
                    self.root.mainloop()
                    for visible_page, visible_workspace in workspaces.items():
                        getattr(self.window, f"show_{visible_page}")()
                        self.root.update()
                        sash_x, _ = visible_workspace.sash_coord(0)
                        actual_fraction = sash_x / max(visible_workspace.winfo_width(), 1)
                        expected_fraction = 0.5 if visible_page == "quality" else 5 / 9
                        self.assertAlmostEqual(
                            actual_fraction,
                            expected_fraction,
                            delta=0.025,
                            msg=f"{visible_page} must display the intended balance at {width}x{height}",
                        )

    def test_user_adjusted_split_survives_window_resizing(self) -> None:
        self.root.deiconify()
        self.root.geometry("1366x768")
        self.window.show_proposals()
        self.root.update()
        workspace = self.window.proposal_workspace

        chosen_fraction = 0.67
        chosen_position = round(workspace.winfo_width() * chosen_fraction)
        workspace.sash_place(0, chosen_position, 1)
        workspace.event_generate("<ButtonRelease-1>", x=chosen_position, y=1)
        self.root.update()

        self.root.geometry("1000x720")
        self.root.update()
        self.assertEqual(str(workspace.cget("orient")), "vertical")

        self.root.geometry("1500x800")
        self.root.update()
        self.root.after(160, self.root.quit)
        self.root.mainloop()
        sash_x, _ = workspace.sash_coord(0)
        actual_fraction = sash_x / max(workspace.winfo_width(), 1)

        self.assertAlmostEqual(
            actual_fraction,
            chosen_fraction,
            delta=0.025,
            msg="resizing the workbench should preserve the member's chosen list/inspector balance",
        )

    def test_list_and_inspector_surfaces_have_distinct_visual_roles(self) -> None:
        style = ttk.Style(self.root)
        workspaces = (
            self.window.quality_workspace,
            self.window.project_workspace,
            self.window.proposal_workspace,
            self.window.run_workspace,
        )

        for workspace in workspaces:
            with self.subTest(workspace=workspace):
                list_surface, inspector_surface = workspace.winfo_children()
                self.assertEqual(list_surface.cget("style"), "ListPane.TFrame")
                self.assertEqual(inspector_surface.cget("style"), "InspectorPane.TFrame")

        self.assertEqual(str(style.lookup("ListPane.TFrame", "relief")), "flat")
        self.assertEqual(str(style.lookup("InspectorPane.TFrame", "relief")), "solid")
        self.assertGreater(int(style.lookup("InspectorPane.TFrame", "borderwidth")), 0)

    def test_table_horizontal_scrollbars_only_show_when_columns_overflow(self) -> None:
        self.root.deiconify()
        self.root.geometry("1800x1200")

        def horizontal_scrollbar(tree: ttk.Treeview) -> ttk.Scrollbar:
            return next(
                child
                for child in tree.master.winfo_children()
                if isinstance(child, ttk.Scrollbar) and str(child.cget("orient")) == "horizontal"
            )

        cases = (
            ("projects", self.window.team_projects_tree),
            ("proposals", self.window.proposals_tree),
            ("runs", self.window.runs_tree),
        )

        for page, tree in cases:
            with self.subTest(page=page):
                getattr(self.window, f"show_{page}")()
                self.root.update()
                scrollbar = horizontal_scrollbar(tree)
                self.assertFalse(
                    scrollbar.winfo_ismapped(),
                    f"{page} should not reserve a horizontal-scroll row when all columns fit",
                )

        proposal_scrollbar = horizontal_scrollbar(self.window.proposals_tree)
        self.window.proposals_tree.column("template", width=1100, stretch=False)
        self.root.update()
        self.assertTrue(proposal_scrollbar.winfo_ismapped(), "long columns must remain horizontally reachable")

        self.window.proposals_tree.column("template", width=96, stretch=True)
        self.root.update()
        self.assertFalse(proposal_scrollbar.winfo_ismapped(), "the scrollbar should hide again after content fits")

    def test_section_eyebrows_use_the_workbench_accent_for_scan_hierarchy(self) -> None:
        style = ttk.Style(self.root)
        self.assertEqual(
            style.lookup("Eyebrow.TLabel", "foreground"),
            COLORS["accent_text"],
            "section labels should provide a consistent, restrained ICT brand cue",
        )

    def test_review_and_report_actions_are_grouped_in_fixed_inspector_footers(self) -> None:
        cases = (
            (
                self.window.proposal_actions,
                (self.window.view_template_button, self.window.approve_proposal_button),
            ),
            (
                self.window.run_report_actions,
                (self.window.export_run_report_button, self.window.export_run_pdf_button),
            ),
        )

        for footer, actions in cases:
            with self.subTest(footer=footer):
                self.assertEqual(footer.pack_info().get("side"), "bottom")
                for action in actions:
                    self.assertEqual(action.master, footer)

    def test_team_access_is_separated_from_the_project_inspector(self) -> None:
        style = ttk.Style(self.root)
        access_strip = self.window.team_access_strip
        self.assertEqual(access_strip.cget("style"), "AccessStrip.TFrame")
        self.assertEqual(
            style.lookup("AccessStrip.TFrame", "background"),
            COLORS["surface_alt"],
            "credential entry belongs to a distinct, contained access surface",
        )
        self.assertEqual(self.window.team_token_entry.cget("show"), "*")
        self.assertEqual(self.window.team_token_label.cget("text"), "团队访问令牌")
        self.assertEqual(self.window.team_token_label.cget("style"), "AccessInputLabel.TLabel")
        self.assertEqual(self.window.team_token_label.master, access_strip)
        self.assertEqual(self.window.team_token_label.winfo_manager(), "pack")
        self.assertIn("不写入设置文件或日志", self.window.team_access_description.cget("text"))

    def test_service_settings_address_has_a_visible_label(self) -> None:
        self.window.show_service_settings()

        self.assertEqual(self.window.service_url_label.cget("text"), "服务地址")
        self.assertEqual(self.window.service_url_label.cget("style"), "InputLabel.TLabel")
        self.assertEqual(self.window.service_url_label.master, self.window.service_url_entry.master)
        self.assertEqual(self.window.service_url_label.winfo_manager(), "pack")

    def test_proposal_and_run_rows_use_semantic_status_colors(self) -> None:
        cases = (
            (self.window.proposals_tree, "pending_approval", "status_pending", COLORS["warning_text"]),
            (self.window.proposals_tree, "expired", "status_muted", COLORS["muted"]),
            (self.window.proposals_tree, "approved", "status_info", COLORS["accent_text"]),
            (self.window.runs_tree, "queued", "status_muted", COLORS["muted"]),
            (self.window.runs_tree, "running", "status_running", COLORS["accent_text"]),
            (self.window.runs_tree, "succeeded", "status_success", COLORS["moss"]),
            (self.window.runs_tree, "failed", "status_error", COLORS["danger_text"]),
        )

        for tree, status, tag, foreground in cases:
            with self.subTest(status=status):
                tags = self.window._table_row_tags(tree, status)
                self.assertIn(tag, tags)
                self.assertEqual(str(tree.tag_configure(tag, "foreground")), foreground)

    def test_native_caption_results_are_logged_at_info_level(self) -> None:
        class NativeFunction:
            def __init__(self, result=0, return_value=None):
                self.argtypes = None
                self.restype = None
                self.result = result
                self.return_value = return_value

            def __call__(self, *args):
                return self.return_value if self.return_value is not None else self.result

        user32 = SimpleNamespace(GetAncestor=NativeFunction(return_value=None))
        dwmapi = SimpleNamespace(DwmSetWindowAttribute=NativeFunction())

        def load_library(name, **_kwargs):
            return user32 if name == "user32" else dwmapi

        self.root.deiconify()
        self.root.update()
        user32.GetAncestor.return_value = self.root.winfo_id()
        with patch.object(ui_theme.os, "name", "nt"), patch.object(
            ui_theme.ctypes, "WinDLL", side_effect=load_library
        ), self.assertLogs("ict_desktop.ui_theme", level="INFO") as captured:
            ui_theme.apply_windows_dark_titlebar(self.root)

        self.assertTrue(
            any("attribute=20" in line and "hresult=0x00000000" in line for line in captured.output),
            "successful DWM calls must be visible in the INFO-level desktop log for diagnosis",
        )

    def test_native_caption_waits_until_the_window_is_mapped(self) -> None:
        class NativeFunction:
            def __init__(self, return_value=None):
                self.argtypes = None
                self.restype = None
                self.return_value = return_value
                self.calls = 0

            def __call__(self, *_args):
                self.calls += 1
                return self.return_value if self.return_value is not None else 0

        self.root.withdraw()
        user32 = SimpleNamespace(GetAncestor=NativeFunction(self.root.winfo_id()))
        dwmapi = SimpleNamespace(DwmSetWindowAttribute=NativeFunction())

        def load_library(name, **_kwargs):
            return user32 if name == "user32" else dwmapi

        with patch.object(ui_theme.os, "name", "nt"), patch.object(
            ui_theme.ctypes, "WinDLL", side_effect=load_library
        ), self.assertLogs("ict_desktop.ui_theme", level="INFO") as captured:
            ui_theme.apply_windows_dark_titlebar(self.root)
            self.root.update_idletasks()
            self.assertFalse(self.root.winfo_ismapped())
            self.assertEqual(dwmapi.DwmSetWindowAttribute.calls, 0)

            self.root.deiconify()
            self.root.update()

        self.assertEqual(dwmapi.DwmSetWindowAttribute.calls, 4)
        self.assertTrue(
            any("mapped=True" in line for line in captured.output),
            "DWM must receive the final top-level HWND after Tk maps the window",
        )

if __name__ == "__main__":
    unittest.main()
