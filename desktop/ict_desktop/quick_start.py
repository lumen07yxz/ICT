"""Native, read-only onboarding wizard for the Windows desktop client."""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from .api import DesktopApiError
from .ui_theme import COLORS, apply_windows_dark_titlebar


LOGGER = logging.getLogger(__name__)


class QuickStartWizard:
    """Guide a user through service setup and existing read-only pages."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        initial_service_url: str,
        get_client: Callable[[], Any],
        save_service_url: Callable[[str], str | None],
        connect_team: Callable[[str], None],
        get_team_state: Callable[[], dict[str, Any]],
        open_proposals: Callable[[], None],
    ) -> None:
        self._get_client = get_client
        self._save_service_url = save_service_url
        self._connect_team = connect_team
        self._get_team_state = get_team_state
        self._open_proposals = open_proposals
        self._service_url = initial_service_url
        self._closed = False
        self._step = 1
        self._health_succeeded = False
        self._health_loading = False
        self._health_request_id = 0
        self._health_result_queue: queue.Queue[tuple[int, bool]] = queue.Queue()
        self._health_poll_after_id: str | None = None
        self._team_poll_after_id: str | None = None
        self._team_ready = False
        self._team_skipped = False
        self._status_message = ""
        self._team_state: dict[str, Any] = {}

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("快速开始 · ICT 研究工作台")
        self.dialog.after_idle(apply_windows_dark_titlebar, self.dialog)
        self._fit_to_screen(parent)
        self.dialog.resizable(True, True)
        self.dialog.configure(background=COLORS["paper"])
        self.dialog.transient(parent)
        self.dialog.protocol("WM_DELETE_WINDOW", self.close)
        self.dialog.bind("<Escape>", lambda _event: self.close())
        self.dialog.bind("<MouseWheel>", self._on_mouse_wheel)

        panel = ttk.Frame(self.dialog, style="Wizard.TFrame", padding=(25, 23, 25, 20))
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)
        header = ttk.Frame(panel, style="Wizard.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        self.step_counter = ttk.Label(header, text="", style="WizardStep.TLabel")
        self.step_counter.pack(anchor="w")
        self.progress_track = tk.Frame(header, background=COLORS["surface"], height=4)
        self.progress_track.pack(fill="x", pady=(8, 15))
        self.progress_segments: list[tk.Frame] = []
        for _index in range(4):
            segment = tk.Frame(self.progress_track, background=COLORS["line"], height=3)
            segment.pack(side="left", fill="x", expand=True, padx=(0, 5))
            self.progress_segments.append(segment)
        self.heading = ttk.Label(header, text="", style="WizardTitle.TLabel")
        self.heading.pack(anchor="w", pady=(0, 14))
        content_host = ttk.Frame(panel, style="Wizard.TFrame")
        content_host.grid(row=1, column=0, sticky="nsew")
        content_host.columnconfigure(0, weight=1)
        content_host.rowconfigure(0, weight=1)
        self.content_canvas = tk.Canvas(
            content_host, background=COLORS["surface"], borderwidth=0, highlightthickness=0,
        )
        self.content_canvas.grid(row=0, column=0, sticky="nsew")
        content_scrollbar = ttk.Scrollbar(content_host, orient="vertical", command=self.content_canvas.yview)
        content_scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.content_canvas.configure(yscrollcommand=content_scrollbar.set)
        self.content = ttk.Frame(self.content_canvas, style="Wizard.TFrame")
        self._content_window = self.content_canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._update_scrollregion)
        self.content_canvas.bind("<Configure>", self._resize_content)

        footer = ttk.Frame(panel, style="Wizard.TFrame")
        footer.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        ttk.Separator(footer, orient="horizontal").pack(fill="x")
        actions = ttk.Frame(footer, style="Wizard.TFrame")
        actions.pack(fill="x", pady=(18, 0))
        self.close_button = ttk.Button(actions, text="关闭", style="Quiet.TButton", command=self.close)
        self.close_button.pack(side="left")
        self.back_button = ttk.Button(actions, text="上一步", style="Quiet.TButton", command=self.previous_step)
        self.next_button = ttk.Button(actions, text="", style="Primary.TButton", command=self.advance)
        self.next_button.pack(side="right")
        self.back_button.pack(side="right", padx=(0, 8))

        self._render_step()
        self.dialog.grab_set()

    def _fit_to_screen(self, parent: tk.Misc) -> None:
        """Keep the wizard inside the visible desktop at high display scaling."""
        screen_width = self.dialog.winfo_screenwidth()
        screen_height = self.dialog.winfo_screenheight()
        width = min(680, max(320, screen_width - 64))
        height = min(480, max(300, screen_height - 100))
        x = max(0, min(parent.winfo_rootx() + (parent.winfo_width() - width) // 2, screen_width - width))
        y = max(0, min(parent.winfo_rooty() + (parent.winfo_height() - height) // 2, screen_height - height - 40))
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
        self.dialog.minsize(min(460, width), min(300, height))
        LOGGER.info("Quick-start viewport; screen=%sx%s window=%sx%s", screen_width, screen_height, width, height)

    def _update_scrollregion(self, _event: tk.Event | None = None) -> None:
        """Follow step and status growth without moving the bottom actions."""
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _resize_content(self, event: tk.Event | None = None) -> None:
        width = event.width if event is not None else self.content_canvas.winfo_width()
        self.content_canvas.itemconfigure(self._content_window, width=width)
        wraplength = max(180, width - 24)
        for widget in self.content.winfo_children():
            if isinstance(widget, ttk.Label) and int(widget.cget("wraplength") or 0):
                widget.configure(wraplength=wraplength)
        self._update_scrollregion()

    def _on_mouse_wheel(self, event: tk.Event) -> None:
        if event.delta:
            self.content_canvas.yview_scroll(-int(event.delta / 120) or (-1 if event.delta > 0 else 1), "units")

    @property
    def step(self) -> int:
        return self._step

    def _render_step(self) -> None:
        if self._closed:
            return
        sync_team_after_render = False
        for child in self.content.winfo_children():
            child.destroy()
        self.step_counter.configure(text=f"第 {self._step} 步 / 共 4 步")
        for index, segment in enumerate(self.progress_segments, start=1):
            segment.configure(background=COLORS["accent_text"] if index <= self._step else COLORS["line"])
        self.back_button.state(["disabled"] if self._step == 1 or self._health_loading else ["!disabled"])
        self.next_button.state(["!disabled"])
        self._status_message = ""

        if self._step == 1:
            self.heading.configure(text="设置后端地址")
            ttk.Label(
                self.content,
                text="输入团队提供的服务地址。本机联调可使用回环地址，远程服务必须使用 HTTPS。这里只保存地址，不保存密码或密钥。",
                style="WizardBody.TLabel",
                wraplength=550,
                justify="left",
            ).pack(anchor="w", pady=(0, 14))
            self.service_url_label = ttk.Label(self.content, text="服务地址", style="InputLabel.TLabel")
            self.service_url_label.pack(anchor="w", pady=(0, 5))
            self.service_url_entry = ttk.Entry(self.content, width=70)
            self.service_url_entry.pack(fill="x")
            self.service_url_entry.insert(0, self._service_url)
            self.next_button.configure(text="保存并继续")

        elif self._step == 2:
            self.heading.configure(text="检测 API")
            ttk.Label(
                self.content,
                text="检测服务是否能够响应。连接成功只表示 API 可访问，不代表项目已经通过数据或科研审核。",
                style="WizardBody.TLabel",
                wraplength=550,
                justify="left",
            ).pack(anchor="w", pady=(0, 14))
            self.check_api_button = ttk.Button(
                self.content,
                text="检测 API",
                style="Primary.TButton",
                command=self.check_api,
            )
            self.check_api_button.pack(anchor="w")
            self.next_button.configure(text="下一步")
            self.next_button.state(["disabled"] if not self._health_succeeded else ["!disabled"])
            if not self._status_message:
                self._status_message = "等待检测。"

        elif self._step == 3:
            self.heading.configure(text="连接团队项目")
            ttk.Label(
                self.content,
                text="团队访问令牌只在本次软件运行期间保存在内存中。连接后只读取当前账号可访问的项目和角色。",
                style="WizardBody.TLabel",
                wraplength=550,
                justify="left",
            ).pack(anchor="w", pady=(0, 12))
            self.team_token_label = ttk.Label(self.content, text="团队访问令牌", style="InputLabel.TLabel")
            self.team_token_label.pack(anchor="w", pady=(0, 5))
            self.team_token_entry = ttk.Entry(self.content, width=70, show="*")
            self.team_token_entry.pack(fill="x")
            team_actions = ttk.Frame(self.content, style="Wizard.TFrame")
            team_actions.pack(anchor="w", pady=(8, 10))
            self.connect_team_button = ttk.Button(
                team_actions,
                text="连接并读取项目",
                style="Primary.TButton",
                command=self.connect_team_projects,
            )
            self.connect_team_button.pack(side="left")
            self.skip_team_button = ttk.Button(
                team_actions,
                text="跳过团队登录",
                style="Quiet.TButton",
                command=self.skip_team_login,
            )
            self.skip_team_button.pack(side="left", padx=(8, 0))
            self.team_roles_label = ttk.Label(
                self.content,
                text="",
                style="WizardBody.TLabel",
                wraplength=550,
                justify="left",
            )
            self.team_roles_label.pack(anchor="w", pady=(2, 0))
            self.next_button.configure(text="继续")
            self._read_team_state()
            sync_team_after_render = True

        else:
            self.heading.configure(text="查看固定模板说明")
            ttk.Label(
                self.content,
                text=(
                    "下一步会打开现有的只读提案页。选择一条当前账号可见的提案，再查看其固定模板说明。"
                    "没有可见提案时，页面会显示空状态。这里不会创建提案、审批提案或启动任务。"
                ),
                style="WizardBody.TLabel",
                wraplength=550,
                justify="left",
            ).pack(anchor="w", pady=(0, 12))
            ttk.Label(
                self.content,
                text="如果跳过团队登录，提案页将按当前未登录状态显示。",
                style="WizardMuted.TLabel",
                wraplength=550,
                justify="left",
            ).pack(anchor="w")
            self.next_button.configure(text="打开提案页")

        self.status_label = ttk.Label(
            self.content,
            text=self._status_message,
            style="SettingsError.TLabel" if self._status_message and "无法" in self._status_message else "WizardMuted.TLabel",
            wraplength=550,
            justify="left",
        )
        self.status_label.pack(anchor="w", pady=(12, 0))
        self._resize_content()
        self.content_canvas.yview_moveto(0)
        if sync_team_after_render:
            self._sync_team_state()

    def _set_status(self, message: str, *, is_error: bool = False) -> None:
        self._status_message = message
        if self._closed or not self.dialog.winfo_exists():
            return
        self.status_label.configure(
            text=message,
            style="SettingsError.TLabel" if is_error else "WizardMuted.TLabel",
        )

    def save_service_and_continue(self) -> None:
        if self._step != 1:
            return
        service_url = self.service_url_entry.get().strip()
        error = self._save_service_url(service_url)
        if error:
            self._set_status(error, is_error=True)
            return
        self._service_url = service_url
        self._step = 2
        self._health_succeeded = False
        self._render_step()

    def check_api(self) -> None:
        if self._step != 2 or self._health_loading:
            return
        self._health_loading = True
        self._health_request_id += 1
        request_id = self._health_request_id
        client = self._get_client()
        self.back_button.state(["disabled"])
        self.check_api_button.state(["disabled"])
        self.next_button.state(["disabled"])
        self._set_status("正在检测 API…")

        def request_health() -> None:
            try:
                client.check_health()
            except DesktopApiError as exc:
                LOGGER.warning("Quick-start health check failed; error_type=%s", type(exc).__name__)
                succeeded = False
            except Exception as exc:
                LOGGER.error("Unexpected quick-start health check failure; error_type=%s", type(exc).__name__)
                succeeded = False
            else:
                succeeded = True
            self._health_result_queue.put((request_id, succeeded))

        threading.Thread(
            target=request_health,
            name="desktop-quick-start-health",
            daemon=True,
        ).start()
        self._health_poll_after_id = self.dialog.after(50, self._poll_health_result)

    def _poll_health_result(self) -> None:
        self._health_poll_after_id = None
        if self._closed or not self.dialog.winfo_exists():
            return
        try:
            request_id, succeeded = self._health_result_queue.get_nowait()
        except queue.Empty:
            self._health_poll_after_id = self.dialog.after(50, self._poll_health_result)
            return
        if request_id != self._health_request_id:
            return
        self._health_loading = False
        self.back_button.state(["!disabled"])
        self.check_api_button.state(["!disabled"])
        self._health_succeeded = succeeded
        self.next_button.state(["!disabled"] if succeeded else ["disabled"])
        if succeeded:
            self._set_status("API 可连接。")
        else:
            self._set_status("无法连接 API。请检查服务地址和网络后重试。", is_error=True)

    def _read_team_state(self) -> None:
        try:
            state = self._get_team_state()
            self._team_state = state if isinstance(state, dict) else {}
        except Exception as exc:
            LOGGER.error("Quick-start team status read failed; error_type=%s", type(exc).__name__)
            self._team_state = {"loading": False, "ready": False, "status": "暂时无法读取团队连接状态。", "projects": []}

    def _sync_team_state(self) -> None:
        if self._step != 3 or self._closed:
            return
        state = self._team_state
        self._team_ready = bool(state.get("ready", False))
        team_loading = bool(state.get("loading", False))
        self.connect_team_button.state(["disabled"] if team_loading else ["!disabled"])
        self.skip_team_button.state(["disabled"] if team_loading else ["!disabled"])
        projects = state.get("projects", [])
        if not isinstance(projects, list):
            projects = []
        role_lines = []
        for project in projects:
            if not isinstance(project, dict):
                continue
            name = str(project.get("name", ""))
            role = str(project.get("role", ""))
            if name and role:
                role_lines.append(f"{name} · {role}")
        if role_lines:
            self.team_roles_label.configure(text="\n".join(role_lines))
        else:
            self.team_roles_label.configure(text=str(state.get("status", "尚未连接团队项目服务")))
        if self._team_ready:
            self.next_button.state(["!disabled"])
            if projects:
                self._set_status("已确认当前账号可访问的项目和角色。")
            else:
                self._set_status(str(state.get("status", "当前账号没有可访问的项目。")))
        elif state.get("loading"):
            self.next_button.state(["disabled"])
            self._set_status("正在读取当前账号可访问的项目…")
            if self._team_poll_after_id is None:
                self._team_poll_after_id = self.dialog.after(50, self._poll_team_state)
        else:
            self.next_button.state(["disabled"])
            status = str(state.get("status", "尚未连接团队项目服务"))
            is_error = any(word in status for word in ("无效", "无法", "失败", "不正确"))
            self._set_status(status, is_error=is_error)

    def _poll_team_state(self) -> None:
        self._team_poll_after_id = None
        if self._closed or not self.dialog.winfo_exists() or self._step != 3:
            return
        self._read_team_state()
        self._sync_team_state()

    def connect_team_projects(self) -> None:
        if self._step != 3:
            return
        token = self.team_token_entry.get().strip()
        if not token:
            self._set_status("请输入团队访问令牌。", is_error=True)
            return
        self.team_token_entry.delete(0, "end")
        self._team_ready = False
        self.next_button.state(["disabled"])
        try:
            self._connect_team(token)
        except Exception as exc:
            LOGGER.error("Quick-start team connection could not start; error_type=%s", type(exc).__name__)
            self._set_status("无法开始团队项目读取，请稍后重试。", is_error=True)
            return
        self._read_team_state()
        self._sync_team_state()

    def skip_team_login(self) -> None:
        if self._step != 3:
            return
        self.team_token_entry.delete(0, "end")
        self._team_skipped = True
        self._step = 4
        self._render_step()

    def previous_step(self) -> None:
        if self._step <= 1:
            return
        if self._step == 2:
            self._step = 1
        elif self._step == 3:
            self._step = 2
        else:
            self._step = 3
        self._render_step()

    def advance(self) -> None:
        if self._step == 1:
            self.save_service_and_continue()
        elif self._step == 2 and self._health_succeeded:
            self._step = 3
            self._render_step()
        elif self._step == 3 and self._team_ready:
            self._step = 4
            self._render_step()
        elif self._step == 4:
            self.open_proposals_page()

    def open_proposals_page(self) -> None:
        if self._step != 4:
            return
        self.close()
        self._open_proposals()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._health_request_id += 1
        for after_id in (self._health_poll_after_id, self._team_poll_after_id):
            if after_id is not None:
                try:
                    self.dialog.after_cancel(after_id)
                except tk.TclError:
                    pass
        self._health_poll_after_id = None
        self._team_poll_after_id = None
        if hasattr(self, "team_token_entry"):
            try:
                self.team_token_entry.delete(0, "end")
            except tk.TclError:
                pass
        try:
            self.dialog.grab_release()
        except tk.TclError:
            pass
        if self.dialog.winfo_exists():
            self.dialog.destroy()
