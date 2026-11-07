"""Behavior tests for the native quick-start wizard."""

import importlib
import sys
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_ROOT))


class FakeHealthClient:
    def __init__(self, results=None, gate=None):
        self.results = list(results or [None])
        self.gate = gate
        self.calls = 0

    def check_health(self):
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(timeout=2)
        result = self.results.pop(0) if self.results else None
        if isinstance(result, Exception):
            raise result
        return result


class QuickStartWizardTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.client = FakeHealthClient()
        self.saved_urls = []
        self.connected_tokens = []
        self.team_state = {
            "loading": False,
            "status": "尚未连接团队项目服务",
            "projects": [],
        }
        self.opened_proposals = []
        self.wizard_module = importlib.import_module("ict_desktop.quick_start")

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def make_wizard(self, save_result=None):
        return self.wizard_module.QuickStartWizard(
            self.root,
            initial_service_url="https://api.example.test",
            get_client=lambda: self.client,
            save_service_url=lambda url: self._save_url(url, save_result),
            connect_team=self._connect_team,
            get_team_state=lambda: self.team_state,
            open_proposals=lambda: self.opened_proposals.append("opened"),
        )

    def _save_url(self, url, result):
        self.saved_urls.append(url)
        return result

    def _connect_team(self, token):
        self.connected_tokens.append(token)
        self.team_state.update(loading=True, ready=False, status="正在读取当前账号可访问的项目…")

    def wait_until(self, condition, timeout_seconds=3):
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            self.root.update()
            if condition():
                return True
            time.sleep(0.01)
        self.root.update()
        return condition()

    def test_starts_on_service_address_step_and_rejects_unsaved_address(self):
        wizard = self.make_wizard(save_result="服务地址无效；远程服务必须使用 HTTPS。")
        self.assertEqual(wizard.step, 1)
        self.assertEqual(wizard.service_url_entry.get(), "https://api.example.test")
        self.assertEqual(wizard.service_url_label.cget("text"), "服务地址")
        self.assertEqual(wizard.service_url_label.master, wizard.content)
        self.assertEqual(wizard.service_url_label.winfo_manager(), "pack")

        wizard.service_url_entry.delete(0, "end")
        wizard.service_url_entry.insert(0, "http://api.example.test")
        wizard.save_service_and_continue()

        self.assertEqual(self.saved_urls, ["http://api.example.test"])
        self.assertEqual(wizard.step, 1)
        self.assertIn("HTTPS", wizard.status_label.cget("text"))

    def test_short_wizard_keeps_actions_visible_and_scrolls_long_status(self):
        self.root.deiconify()
        self.root.geometry("900x700")
        wizard = self.make_wizard()
        wizard.dialog.geometry("520x310")
        wizard._step = 3
        wizard._render_step()
        wizard._set_status("连接状态需要进一步核查。" * 25, is_error=True)
        self.root.update()

        self.assertLessEqual(
            wizard.next_button.winfo_rooty() + wizard.next_button.winfo_height(),
            wizard.dialog.winfo_rooty() + wizard.dialog.winfo_height(),
        )
        self.assertLess(wizard.content_canvas.winfo_height(), int(wizard.content_canvas.cget("scrollregion").split()[3]))
        wizard.content_canvas.yview_moveto(1.0)
        self.assertGreater(wizard.content_canvas.yview()[0], 0)

    def test_valid_address_advances_and_health_check_runs_asynchronously(self):
        finished = threading.Event()

        class SlowClient(FakeHealthClient):
            def check_health(inner_self):
                inner_self.calls += 1
                time.sleep(0.05)
                finished.set()

        self.client = SlowClient()
        wizard = self.make_wizard()
        wizard.save_service_and_continue()

        self.assertEqual(wizard.step, 2)
        self.assertFalse(wizard.next_button.instate(["!disabled"]))
        wizard.check_api_button.invoke()

        self.assertTrue(self.wait_until(finished.is_set))
        self.assertTrue(self.wait_until(lambda: "API 可连接" in wizard.status_label.cget("text")))
        self.assertTrue(wizard.next_button.instate(["!disabled"]))

    def test_health_failure_is_safe_and_retry_can_succeed(self):
        self.client = FakeHealthClient([RuntimeError("private backend trace"), None])
        wizard = self.make_wizard()
        wizard.save_service_and_continue()
        with self.assertLogs("ict_desktop.quick_start", level="ERROR") as captured:
            wizard.check_api_button.invoke()
            self.assertTrue(self.wait_until(lambda: "无法连接" in wizard.status_label.cget("text")))
        self.assertNotIn("private backend trace", wizard.status_label.cget("text"))
        self.assertNotIn("private backend trace", "\n".join(captured.output))
        self.assertFalse(wizard.next_button.instate(["!disabled"]))

        wizard.check_api_button.invoke()
        self.assertTrue(self.wait_until(lambda: "API 可连接" in wizard.status_label.cget("text")))
        self.assertEqual(self.client.calls, 2)

    def test_team_token_is_masked_cleared_and_real_roles_are_shown(self):
        wizard = self.make_wizard()
        wizard.save_service_and_continue()
        wizard._health_succeeded = True
        wizard.advance()
        self.assertEqual(wizard.step, 3)
        self.assertEqual(wizard.team_token_entry.cget("show"), "*")
        self.assertEqual(wizard.team_token_label.cget("text"), "团队访问令牌")
        self.assertEqual(wizard.team_token_label.master, wizard.content)
        self.assertEqual(wizard.team_token_label.winfo_manager(), "pack")

        wizard.team_token_entry.insert(0, "secret-team-token")
        wizard.connect_team_button.invoke()

        self.assertEqual(self.connected_tokens, ["secret-team-token"])
        self.assertEqual(wizard.team_token_entry.get(), "")
        self.team_state.update(
            loading=False,
            ready=True,
            status="已连接 · 共 1 个可访问项目",
            projects=[{"name": "合成演示项目", "role": "操作者"}],
        )
        self.assertTrue(self.wait_until(lambda: "操作者" in wizard.team_roles_label.cget("text")))
        self.assertTrue(wizard.next_button.instate(["!disabled"]))

    def test_skipping_team_login_clears_entry_without_connecting(self):
        wizard = self.make_wizard()
        wizard.save_service_and_continue()
        wizard._health_succeeded = True
        wizard.advance()
        wizard.team_token_entry.insert(0, "unsubmitted-token")

        wizard.skip_team_login()

        self.assertEqual(wizard.step, 4)
        self.assertEqual(self.connected_tokens, [])
        self.assertFalse(wizard.team_token_entry.winfo_exists())

    def test_connected_account_with_no_projects_can_continue_with_clear_empty_state(self):
        self.team_state.update(
            ready=True,
            status="当前账号没有可访问的项目。",
            projects=[],
        )
        wizard = self.make_wizard()
        wizard.save_service_and_continue()
        wizard._health_succeeded = True
        wizard.advance()

        self.assertEqual(wizard.step, 3)
        self.assertTrue(wizard.next_button.instate(["!disabled"]))
        self.assertIn("没有可访问", wizard.status_label.cget("text"))

    def test_closing_during_health_check_discards_late_result(self):
        gate = threading.Event()
        self.client = FakeHealthClient(gate=gate)
        wizard = self.make_wizard()
        wizard.save_service_and_continue()
        wizard.check_api_button.invoke()
        self.assertTrue(self.wait_until(lambda: self.client.calls == 1))

        wizard.close()
        gate.set()
        time.sleep(0.08)
        self.root.update()

        self.assertFalse(wizard.dialog.winfo_exists())

    def test_open_proposals_closes_wizard_and_calls_existing_navigation(self):
        wizard = self.make_wizard()
        wizard.save_service_and_continue()
        wizard._health_succeeded = True
        wizard.advance()
        wizard.skip_team_login()

        wizard.open_proposals_page()

        self.assertEqual(self.opened_proposals, ["opened"])
        self.assertFalse(wizard.dialog.winfo_exists())


if __name__ == "__main__":
    unittest.main()
