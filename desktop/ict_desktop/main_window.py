"""Tk desktop shell for the synthetic ICT research workbench."""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from .api import (
    HEALTH_PATH,
    DemoProjectApiClient,
    DatasetQualityReport,
    DesktopApiError,
    ProjectDetail,
    ProjectListItem,
    PipelineTemplateContract,
    RunProposal,
    Run,
    RunEvent,
)
from .manifest_quality import ManifestQualityError, ManifestQualityReport, inspect_manifest
from .quick_start import QuickStartWizard
from .report_export import REPORT_TEMPLATE_VERSION, render_run_pdf, render_run_report
from .settings import DEFAULT_API_BASE_URL, save_api_base_url
from .template_dialog import TemplateContractDialog
from .ui_theme import COLORS, FONTS, apply_windows_dark_titlebar, configure_theme


LOGGER = logging.getLogger(__name__)
WORKSPACE_STACK_BREAKPOINT = 900


class _ProposalRequestState:
    """Thread-safe proposal response state that never holds Tk widgets."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.result_queue: queue.Queue[tuple[int, str, object]] = queue.Queue()
        self.request_id = 0


class MainWindow:
    """Native desktop shell for project, reproduction, and research-workflow pages."""

    def __init__(
        self,
        root: tk.Tk,
        client: Any | None = None,
        service_url: str | None = None,
        settings_saver: Callable[[str], None] | None = None,
        manifest_checker: Callable[[str | Path], ManifestQualityReport] | None = None,
    ) -> None:
        self.root = root
        self.api_base_url = service_url if service_url is not None else DEFAULT_API_BASE_URL
        self.client = client or DemoProjectApiClient(self.api_base_url)
        self._settings_saver = settings_saver or save_api_base_url
        self._manifest_checker = manifest_checker or inspect_manifest
        self.service_settings_dialog: tk.Toplevel | None = None
        self.quick_start_wizard: QuickStartWizard | None = None
        self._health_result_queue: queue.Queue[tuple[int, str, object]] = queue.Queue()
        self._health_request_id = 0
        self._health_loading = False
        self._quality_result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._server_quality_result_queue: queue.Queue[tuple[int, str, object]] = queue.Queue()
        self._project_result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._project_detail_result_queue: queue.Queue[tuple[int, str, object]] = queue.Queue()
        self._proposal_request_state = _ProposalRequestState()
        self._proposal_result_queue = self._proposal_request_state.result_queue
        self._proposal_result_lock = self._proposal_request_state.lock
        self._run_result_queue: queue.Queue[tuple[int, str, object]] = queue.Queue()
        self._run_event_result_queue: queue.Queue[tuple[int, str, str, object]] = queue.Queue()
        self._approval_result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._quality_loading = False
        self._server_quality_loading = False
        self._server_quality_request_id = 0
        self._server_quality_poll_after_id: str | None = None
        self._project_loading = False
        self._project_detail_loading = False
        self._proposal_loading = False
        self._run_loading = False
        self._run_refresh_pending = False
        self._approval_loading = False
        self._approval_poll_after_id: str | None = None
        self._project_detail_request_id = 0
        self._proposal_request_id = 0
        self._run_request_id = 0
        self._run_event_request_id = 0
        self._selected_run_event_id: str | None = None
        # Export only the events returned for the currently selected run.
        self._selected_run_events: list[RunEvent] | None = None
        self._run_event_loaded_id: str | None = None
        self._run_event_loading = False
        self._run_event_poll_after_id: str | None = None
        self._project_token: str | None = None
        self._project_cache: dict[str, ProjectListItem] = {}
        self._proposal_cache: dict[str, RunProposal] = {}
        self._template_contract_cache: dict[tuple[str, str], PipelineTemplateContract] = {}
        self._template_error_cache: dict[tuple[str, str], str] = {}
        self._run_cache: dict[str, Run] = {}
        self._recent_run_id: str | None = None
        self._pending_run_id: str | None = None
        self._active_page = "projects"

        self.root.title("ICT 研究工作台")
        self._fit_initial_window_to_screen()
        self.root.configure(background=COLORS["paper"])
        self.root.bind("<Destroy>", self._cancel_pending_callbacks_on_destroy, add="+")
        self._configure_theme()
        self._build_window()
        self.show_workbench()
        self.check_service_health()

    def _configure_theme(self) -> None:
        configure_theme(self.root)

    def _fit_initial_window_to_screen(self) -> None:
        """Fit Tk's screen coordinates, including a DPI-virtualized Windows display."""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        # Leave space for the title bar, taskbar and resize handles on smaller displays.
        width = min(1440, max(320, screen_width - 64))
        height = min(900, max(360, screen_height - 100))
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(min(980, width), min(650, height))
        LOGGER.info("Desktop initial viewport; screen=%sx%s window=%sx%s", screen_width, screen_height, width, height)

    def _bind_responsive_wraplength(self, label: tk.Label | ttk.Label, container: ttk.Frame, *, padding: int = 36) -> None:
        """Keep long guidance readable when a workspace pane is resized."""
        labels = getattr(container, "_responsive_wrap_labels", None)
        if labels is None:
            labels = []
            container._responsive_wrap_labels = labels

            def update_wraplength(event: tk.Event) -> None:
                wraplength = max(120, int(event.width) - padding)
                changed = False
                for responsive_label in tuple(labels):
                    try:
                        if responsive_label.winfo_exists() and int(responsive_label.cget("wraplength") or 0) != wraplength:
                            responsive_label.configure(wraplength=wraplength)
                            changed = True
                    except tk.TclError:
                        continue
                if changed and hasattr(self, "page_canvas"):
                    self.root.after_idle(self._refresh_page_viewport)

            container.bind("<Configure>", update_wraplength, add="+")

        if label not in labels:
            labels.append(label)

    def _create_split_workspace(
        self,
        parent: ttk.Frame,
        attribute: str,
        *,
        left_weight: int = 5,
        right_weight: int = 4,
        fit_content_height: bool = False,
    ) -> tuple[tk.PanedWindow, ttk.Frame, ttk.Frame]:
        """Create a resizable list-and-inspector workspace that adapts to narrow windows."""
        workspace = tk.PanedWindow(
            parent,
            orient="horizontal",
            background=COLORS["paper"],
            borderwidth=0,
            relief="flat",
            sashwidth=5,
            sashrelief="flat",
            showhandle=False,
        )
        setattr(self, attribute, workspace)
        parent._split_workspace = workspace
        workspace._fit_content_height = fit_content_height
        workspace._base_pane_min_sizes = (220, 260)
        # Queue pages favor scanning records; form-oriented pages pass balanced weights explicitly.
        workspace._sash_horizontal_fraction = left_weight / (left_weight + right_weight)
        workspace._sash_vertical_fraction = 0.38
        workspace._sash_resize_after_id: str | None = None
        workspace._sash_reset_pending = True
        # Distinguish the two persistent work surfaces from the flatter cards inside each pane.
        left_panel = ttk.Frame(workspace, style="ListPane.TFrame", padding=16)
        right_panel = ttk.Frame(workspace, style="InspectorPane.TFrame", padding=18)
        workspace.add(left_panel, minsize=220, stretch="always")
        workspace.add(right_panel, minsize=260, stretch="always")
        # Form pages use their content height; record workspaces keep a full-height table viewport.
        workspace.pack(fill="x" if fit_content_height else "both", expand=not fit_content_height)
        orientation = "horizontal"

        def remember_sash_position(_event: tk.Event) -> None:
            """Keep a user's pane balance when the workbench changes orientation."""
            try:
                current_orientation = str(workspace.cget("orient"))
                if current_orientation == "vertical" and fit_content_height:
                    return
                extent = int(
                    workspace.winfo_height()
                    if current_orientation == "vertical"
                    else workspace.winfo_width()
                )
                if extent <= 0:
                    return
                coordinate = workspace.sash_coord(0)
                position = int(coordinate[1] if current_orientation == "vertical" else coordinate[0])
                fraction = position / extent
                attribute = (
                    "_sash_vertical_fraction"
                    if current_orientation == "vertical"
                    else "_sash_horizontal_fraction"
                )
                setattr(workspace, attribute, fraction)
                LOGGER.debug(
                    "Workspace sash preference recorded; workspace=%s orientation=%s fraction=%.3f",
                    attribute,
                    current_orientation,
                    fraction,
                )
            except tk.TclError as exc:
                LOGGER.debug("Workspace sash preference unavailable; error_type=%s", type(exc).__name__)

        workspace.bind("<ButtonRelease-1>", remember_sash_position, add="+")

        def adapt_layout(event: tk.Event) -> None:
            """Stack list and inspector when a narrow window cannot give both usable width."""
            nonlocal orientation
            if not workspace.winfo_ismapped():
                return
            width = int(event.width)
            requested_orientation = "vertical" if width < WORKSPACE_STACK_BREAKPOINT else "horizontal"
            if requested_orientation != orientation:
                previous_orientation = orientation
                orientation = requested_orientation
                workspace.configure(orient=orientation)
                workspace._sash_reset_pending = True
                LOGGER.debug(
                    "Workspace layout changed; workspace=%s previous=%s current=%s width=%d",
                    attribute,
                    previous_orientation,
                    orientation,
                    width,
                )
                self._schedule_workspace_sash_reset(workspace)

        workspace.bind("<Configure>", adapt_layout, add="+")
        return workspace, left_panel, right_panel

    def _schedule_workspace_sash_reset(self, workspace: tk.PanedWindow) -> None:
        """Debounce a responsive sash reset until the window resize has settled."""
        try:
            previous_id = workspace._sash_resize_after_id
            if previous_id is not None:
                self.root.after_cancel(previous_id)
            workspace._sash_resize_after_id = self.root.after(
                120,
                lambda target=workspace: self._finish_workspace_sash_resize(target),
            )
        except tk.TclError as exc:
            LOGGER.debug("Responsive sash debounce skipped; error_type=%s", type(exc).__name__)

    def _finish_workspace_sash_resize(self, workspace: tk.PanedWindow) -> None:
        """Refresh the active page after the final responsive orientation change."""
        try:
            workspace._sash_resize_after_id = None
            if not workspace.winfo_exists():
                return
            workspace._sash_reset_pending = True
            LOGGER.debug("Responsive sash resize settled; workspace=%s", workspace)
            self._schedule_page_viewport_refresh()
        except tk.TclError as exc:
            LOGGER.debug("Responsive sash settle skipped; error_type=%s", type(exc).__name__)

    def _set_connection_status(self, state: str) -> None:
        states = {
            "checking": ("服务连接：检查中", "Connection.TLabel"),
            "ok": ("服务连接：正常", "Connection.Ok.TLabel"),
            # An unavailable service is a connection state, not a data-quality failure.
            "error": ("服务连接：不可用", "Connection.Offline.TLabel"),
        }
        text, style = states[state]
        self.connection_status.configure(text=text, style=style)

    def _build_window(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame")
        shell.pack(fill="both", expand=True)

        main = ttk.Frame(shell, style="App.TFrame")
        main.pack(fill="both", expand=True)
        main.rowconfigure(1, weight=1)
        main.columnconfigure(0, weight=1)

        topbar = ttk.Frame(main, style="Topbar.TFrame", padding=(24, 5, 24, 0))
        topbar.grid(row=0, column=0, sticky="ew")
        brand_row = ttk.Frame(topbar, style="Topbar.TFrame")
        brand_row.pack(side="left", fill="y", padx=(0, 18))
        brand_mark = tk.Canvas(brand_row, width=34, height=34, background=COLORS["surface"], highlightthickness=0)
        brand_mark.pack(side="left", padx=(0, 9))
        brand_mark.create_rectangle(1, 1, 33, 33, fill=COLORS["sidebar_active"], outline=COLORS["sidebar_active"])
        brand_mark.create_line(10, 24, 10, 10, fill=COLORS["accent_text"], width=3)
        brand_mark.create_line(17, 24, 26, 24, fill=COLORS["ink_soft"], width=2)
        brand_mark.create_line(17, 18, 24, 18, fill=COLORS["ink_soft"], width=2)
        brand_copy = ttk.Frame(brand_row, style="Topbar.TFrame")
        brand_copy.pack(side="left", fill="x", expand=True)
        ttk.Label(brand_copy, text="ICT", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(brand_copy, text="科研工作台", style="BrandSub.TLabel").pack(anchor="w", pady=(1, 0))

        self.navigation_buttons = {}
        self.navigation_indicators = {}
        self._active_nav = "workbench"
        primary_nav = ttk.Frame(topbar, style="Topbar.TFrame")
        primary_nav.pack(side="left", fill="y")

        def add_navigation_button(key: str, attribute: str, title: str, command: Callable[[], None]) -> None:
            item = ttk.Frame(primary_nav, style="Topbar.TFrame")
            item.pack(side="left", fill="y", padx=(0, 3))
            button = ttk.Button(item, text=title, style="PrimaryNav.TButton", command=command)
            button.pack(side="top", fill="x", expand=True)
            self._clear_mouse_focus_outline(button)
            indicator = tk.Frame(item, background=COLORS["surface"], height=2)
            indicator.pack(side="bottom", fill="x", padx=7)
            setattr(self, attribute, button)
            self.navigation_buttons[key] = button
            self.navigation_indicators[key] = indicator

        add_navigation_button("workbench", "workbench_button", "工作台", self.show_workbench)
        add_navigation_button("templates", "templates_button", "模板市场", self.show_templates)
        self.repository_entry_button = self._create_topbar_icon_entry(
            primary_nav,
            "repository",
            self.show_repository_notice,
            "仓库 · 当前版本尚未开放",
        )
        self.repository_entry_button.pack(side="left", fill="y", padx=(0, 5))
        add_navigation_button("agent", "agent_button", "Agent 对话", self.show_agent)
        self.compute_support_button = self._create_topbar_icon_entry(
            primary_nav,
            "compute",
            self.show_research_support_notice,
            "科研支持 · 云显卡与大模型算力",
        )
        self.compute_support_button.pack(side="left", fill="y", padx=(0, 5))
        add_navigation_button("settings", "profile_settings_button", "个人信息与设置", self.show_profile_settings)
        self.connection_status = ttk.Label(topbar, text="● 服务检查中", style="Connection.TLabel")
        self.connection_status.pack(side="right", pady=(0, 5))
        tk.Frame(topbar, background=COLORS["line"], height=1).pack(side="bottom", fill="x")

        content = ttk.Frame(main, style="App.TFrame", padding=(30, 22, 30, 15))
        content.grid(row=1, column=0, sticky="nsew")
        self.content_layout = content
        # Keep dashboards readable on ultrawide windows while using the full width on laptops.
        self._content_side_padding: int | None = None

        def center_page_content(event: tk.Event) -> None:
            if event.widget is not main:
                return
            side_padding = max(0, (int(event.width) - 1320) // 2)
            if side_padding != self._content_side_padding:
                self._content_side_padding = side_padding
                content.grid_configure(padx=(side_padding, side_padding))

        main.bind("<Configure>", center_page_content, add="+")
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(2, weight=0)
        content.rowconfigure(3, weight=1)
        heading_row = ttk.Frame(content, style="App.TFrame")
        self.heading_row = heading_row
        heading_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 3))
        self.page_heading = ttk.Label(heading_row, text="工作台", style="Title.TLabel")
        self.page_heading.pack(side="left", padx=(0, 4))
        self.team_connection_button = ttk.Button(
            heading_row,
            text="连接团队账号",
            style="Toolbar.TButton",
            command=self.show_team_connection,
        )
        self.page_context = ttk.Label(
            content,
            text="项目与论文复现是工作台的两个同级入口。",
            style="Intro.TLabel",
            wraplength=860,
        )
        self.page_context.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 12))
        self._bind_responsive_wraplength(self.page_context, content, padding=60)

        # Two peer workbench areas fit a horizontal tab bar better than a mostly empty side rail.
        self.workbench_module_sidebar = ttk.Frame(content, style="TabBar.TFrame")
        self.workbench_module_sidebar.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 11),
        )
        self.workbench_module_buttons: dict[str, ttk.Button] = {}
        self.workbench_module_indicators: dict[str, tk.Frame] = {}
        for module_key, label, command in (
            ("projects", "项目", self.show_projects),
            ("reproductions", "论文复现", self.show_reproductions),
        ):
            item = ttk.Frame(self.workbench_module_sidebar, style="TabBar.TFrame")
            item.pack(side="left", padx=(0, 22))
            button = ttk.Button(item, text=label, style="WorkbenchTab.TButton", command=command)
            button.pack(side="top")
            indicator = tk.Frame(item, background=COLORS["paper"], height=2)
            indicator.pack(side="bottom", fill="x", pady=(4, 0))
            self._clear_mouse_focus_outline(button)
            self.workbench_module_buttons[module_key] = button
            self.workbench_module_indicators[module_key] = indicator
        ttk.Separator(self.workbench_module_sidebar, orient="horizontal").pack(side="bottom", fill="x")

        self.page_viewport = ttk.Frame(content, style="App.TFrame")
        self.page_viewport.grid(row=3, column=0, columnspan=2, sticky="nsew")
        self.page_canvas = tk.Canvas(
            self.page_viewport,
            background=COLORS["paper"],
            borderwidth=0,
            highlightthickness=0,
            takefocus=False,
            yscrollincrement=24,
        )
        self.page_canvas.pack(side="left", fill="both", expand=True)
        self.page_scrollbar = ttk.Scrollbar(
            self.page_viewport,
            orient="vertical",
            command=self.page_canvas.yview,
        )
        self._page_scrollbar_visible = False
        self.page_canvas.configure(yscrollcommand=self.page_scrollbar.set)
        self.page_stack = ttk.Frame(self.page_canvas, style="App.TFrame")
        self.page_stack.rowconfigure(0, weight=1)
        self.page_stack.columnconfigure(0, weight=1)
        self.page_stack_window = self.page_canvas.create_window(
            (0, 0),
            window=self.page_stack,
            anchor="nw",
        )
        self.page_canvas.bind("<Configure>", self._on_page_canvas_configure, add="+")
        self._build_quality_page()
        self._build_projects_page()
        self._build_proposals_page()
        self._build_runs_page()
        self._build_new_navigation_pages()
        self._bind_page_mousewheel(self.page_stack)

        footer = ttk.Frame(main, style="Status.TFrame", padding=(30, 5, 30, 5))
        # Reserve the persistent status strip before the expanding viewport gets space.
        footer.grid(row=2, column=0, sticky="ew")
        self.scope_status_label = ttk.Label(
            footer,
            text="本地演示  ·  合成数据  ·  不用于临床判断",
            style="Status.Scope.TLabel",
        )
        self.scope_status_label.pack(anchor="w", fill="x")
        self._bind_responsive_wraplength(self.scope_status_label, footer, padding=48)

    def _clear_mouse_focus_outline(self, widget: tk.Misc) -> None:
        """Remove mouse-only focus outlines while keeping keyboard focus behavior."""
        widget.bind(
            "<ButtonRelease-1>",
            lambda _event: self.root.after_idle(self.root.focus_set),
            add="+",
        )

    def _create_topbar_icon_entry(
        self,
        parent: ttk.Frame,
        icon_key: str,
        command: Callable[[], None],
        tooltip: str,
    ) -> tk.Canvas:
        """Create a compact, keyboard-usable icon entry for top-level utility areas."""
        canvas = tk.Canvas(
            parent,
            width=36,
            height=40,
            background=COLORS["surface"],
            highlightthickness=0,
            takefocus=True,
            cursor="hand2",
        )

        def draw(color: str) -> None:
            canvas.delete("all")
            if icon_key == "repository":
                canvas.create_line(11, 13, 18, 9, 25, 13, 18, 17, 11, 13, fill=color, width=1.5, joinstyle="round")
                canvas.create_line(11, 13, 11, 24, 18, 28, 25, 24, 25, 13, fill=color, width=1.5, joinstyle="round")
                canvas.create_line(18, 17, 18, 28, fill=color, width=1.4)
                canvas.create_line(14, 20, 18, 22, 22, 20, fill=color, width=1.3)
            elif icon_key == "compute":
                canvas.create_line(18, 8, 18, 26, fill=color, width=1.5)
                canvas.create_line(10, 17, 26, 17, fill=color, width=1.5)
                canvas.create_line(12.3, 11.3, 23.7, 22.7, fill=color, width=1.4)
                canvas.create_line(12.3, 22.7, 23.7, 11.3, fill=color, width=1.4)
                canvas.create_oval(16, 15, 20, 19, fill=COLORS["surface"], outline=color, width=1.2)
            else:
                raise ValueError(f"Unsupported top-bar icon: {icon_key}")

        def set_hover(_event: tk.Event | None = None) -> None:
            canvas.configure(background=COLORS["surface_alt"])
            draw(COLORS["accent_text"])

        def clear_hover(_event: tk.Event | None = None) -> None:
            canvas.configure(background=COLORS["surface"])
            draw(COLORS["ink_soft"])

        def activate(_event: tk.Event | None = None) -> str:
            command()
            return "break"

        draw(COLORS["ink_soft"])
        canvas.bind("<Enter>", set_hover, add="+")
        canvas.bind("<Leave>", clear_hover, add="+")
        canvas.bind("<Button-1>", activate, add="+")
        canvas.bind("<Return>", activate, add="+")
        canvas.bind("<space>", activate, add="+")
        self._bind_icon_tooltip(canvas, tooltip)
        return canvas

    def _bind_icon_tooltip(self, widget: tk.Misc, text: str) -> None:
        """Show the icon name and availability on hover or keyboard focus."""
        def show(_event: tk.Event | None = None) -> None:
            self._hide_icon_tooltip()
            tooltip = tk.Toplevel(self.root)
            tooltip.wm_overrideredirect(True)
            label = tk.Label(
                tooltip,
                text=text,
                background=COLORS["sidebar_hover"],
                foreground=COLORS["sidebar_text"],
                font=FONTS["ui_small"],
                padx=8,
                pady=5,
                relief="solid",
                borderwidth=1,
            )
            label.pack()
            x = widget.winfo_rootx() + max(0, (widget.winfo_width() - label.winfo_reqwidth()) // 2)
            y = widget.winfo_rooty() + widget.winfo_height() + 5
            tooltip.geometry(f"+{x}+{y}")
            self._icon_tooltip = tooltip

        widget.bind("<Enter>", show, add="+")
        widget.bind("<FocusIn>", show, add="+")
        widget.bind("<Leave>", self._hide_icon_tooltip, add="+")
        widget.bind("<FocusOut>", self._hide_icon_tooltip, add="+")

    def _hide_icon_tooltip(self, _event: tk.Event | None = None) -> None:
        tooltip = getattr(self, "_icon_tooltip", None)
        if tooltip is not None:
            try:
                tooltip.destroy()
            except tk.TclError:
                pass
            self._icon_tooltip = None

    def _build_quality_page(self) -> None:
        self.quality_page = ttk.Frame(self.page_stack, style="App.TFrame")
        self.quality_page.grid(row=0, column=0, sticky="nsew")
        _, card, detail = self._create_split_workspace(
            self.quality_page,
            "quality_workspace",
            left_weight=1,
            right_weight=1,
            fit_content_height=True,
        )
        self.quality_local_panel = card
        ttk.Label(card, text="本地文件", style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(card, text="本机 CSV 清单预检", style="CardTitle.TLabel").pack(anchor="w", pady=(7, 0))
        self.quality_report_status = ttk.Label(card, text="暂无质量报告", style="CardTitle.TLabel")
        self.quality_report_status.pack(anchor="w", pady=(14, 5))
        ttk.Label(
            card,
            text="选择通用 CSV 清单后在本机预检；不会上传或修改源文件。检查结果不代表数据已获授权或可用于科研。",
            style="Body.TLabel",
            wraplength=720,
            justify="left",
        ).pack(anchor="w")
        self.manifest_file_label = ttk.Label(card, text="尚未选择清单", style="Muted.TLabel")
        self.manifest_file_label.pack(anchor="w", pady=(14, 4))
        self.select_manifest_button = ttk.Button(
            card,
            text="选择 CSV 清单并检查",
            style="Primary.TButton",
            command=self.choose_manifest_file,
        )
        self.select_manifest_button.pack(anchor="w", pady=(4, 8))
        self.manifest_summary = ttk.Label(
            card,
            text="必需列：record_id、group_id、split、label。",
            style="Body.TLabel",
            wraplength=720,
            justify="left",
        )
        self.manifest_summary.pack(anchor="w", pady=(3, 4))
        self.manifest_issues = ttk.Label(
            card,
            text="",
            style="Muted.TLabel",
            wraplength=720,
            justify="left",
        )
        self.manifest_issues.pack(anchor="w", pady=(3, 0))
        self.manifest_guidance = ttk.Label(
            card,
            text="完成本机预检后显示原因与修复指引。",
            style="Muted.TLabel",
            wraplength=720,
            justify="left",
        )
        self.manifest_guidance.pack(anchor="w", pady=(9, 0))

        ttk.Label(detail, text="所选项目", style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(detail, text="项目登记数据版本", style="CardTitle.TLabel").pack(anchor="w", pady=(7, 0))
        self.quality_dataset_versions = ttk.Label(detail, text="请先在工作台选择项目。", style="Body.TLabel")
        self.quality_dataset_versions.pack(anchor="w", pady=(5, 12))
        ttk.Label(
            detail,
            text="本机 CSV 预检与服务器数据版本相互独立。当前服务端报告接口读取固定合成演示项目，不代表上方所选项目。",
            style="Muted.TLabel",
            wraplength=720,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))
        ttk.Label(detail, text="固定演示项目报告", style="CardTitle.TLabel").pack(anchor="w")
        self.server_quality_status = ttk.Label(detail, text="尚未读取服务器质量报告", style="Muted.TLabel")
        self.server_quality_status.pack(anchor="w", pady=(6, 4))
        self.server_quality_check_button = ttk.Button(
            detail,
            text="读取演示项目质量报告",
            style="Quiet.TButton",
            command=self.request_server_quality_report,
        )
        self.server_quality_check_button.pack(anchor="w", pady=(4, 6))
        self.server_quality_summary = ttk.Label(detail, text="", style="Body.TLabel", wraplength=720, justify="left")
        self.server_quality_summary.pack(anchor="w", pady=(2, 3))
        self.server_quality_issues = ttk.Label(detail, text="", style="Muted.TLabel", wraplength=720, justify="left")
        self.server_quality_issues.pack(anchor="w", pady=(2, 3))
        self.server_quality_guidance = ttk.Label(
            detail,
            text="请先在工作台连接账号以读取固定演示项目报告。",
            style="Muted.TLabel",
            wraplength=720,
            justify="left",
        )
        self.server_quality_guidance.pack(anchor="w", pady=(2, 0))
        for panel in (card, detail):
            for label in panel.winfo_children():
                if isinstance(label, ttk.Label):
                    self._bind_responsive_wraplength(label, panel)
    def _build_projects_page(self) -> None:
        """Build a read-only team project page with an in-memory access token."""
        self.projects_page = ttk.Frame(self.page_stack, style="App.TFrame")
        self.projects_page.grid(row=0, column=0, sticky="nsew")

        access_card = ttk.Frame(self.projects_page, style="AccessStrip.TFrame", padding=(14, 7))
        self.team_access_strip = access_card
        access_body = ttk.Frame(access_card, style="AccessContent.TFrame")
        access_body.pack(fill="x")
        access_body.columnconfigure(0, weight=0, minsize=260)
        access_body.columnconfigure(1, weight=1)

        access_info = ttk.Frame(access_body, style="AccessContent.TFrame")
        access_info.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        ttk.Label(access_info, text="团队账号访问", style="AccessTitle.TLabel").pack(anchor="w", pady=(1, 2))
        self.team_access_description = ttk.Label(
            access_info,
            text="令牌仅保存在当前会话，不写入设置或日志。",
            style="Muted.TLabel",
            wraplength=360,
            justify="left",
        )
        self.team_access_description.pack(anchor="w")
        self._bind_responsive_wraplength(self.team_access_description, access_info, padding=8)

        token_panel = ttk.Frame(access_body, style="AccessContent.TFrame")
        token_panel.grid(row=0, column=1, sticky="nsew")
        token_panel.columnconfigure(0, weight=1)
        token_row = ttk.Frame(token_panel, style="AccessContent.TFrame")
        token_row.grid(row=0, column=0, sticky="ew")
        # Let the field shrink before either connection action loses its space.
        token_row.columnconfigure(1, weight=1)
        self.team_token_label = ttk.Label(token_row, text="访问令牌", style="AccessInputLabel.TLabel")
        self.team_token_label.grid(row=0, column=0, sticky="w", padx=(0, 9))
        self.team_token_entry = ttk.Entry(token_row, show="*", width=1)
        self.team_token_entry.grid(row=0, column=1, sticky="ew")
        self.team_token_entry.bind("<Return>", lambda _event: self.connect_team_projects())
        self.connect_team_projects_button = ttk.Button(
            token_row,
            text="连接并读取项目",
            style="Primary.TButton",
            command=self.connect_team_projects,
        )
        self.connect_team_projects_button.grid(row=0, column=2, padx=(8, 0))
        self.clear_team_token_button = ttk.Button(
            token_row,
            text="清除令牌",
            style="AccessQuiet.TButton",
            command=self.clear_team_project_access,
        )
        self.clear_team_token_button.grid(row=0, column=3, padx=(6, 0))
        self.team_projects_status = ttk.Label(token_panel, text="尚未连接项目服务", style="AccessStatus.TLabel")
        self.team_projects_status.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.project_workspace, list_card, detail_card = self._create_split_workspace(
            self.projects_page,
            "project_workspace",
            left_weight=7,
            right_weight=3,
            # Empty workspaces follow their content; real project lists expand to the viewport.
            fit_content_height=True,
        )
        project_list_header = ttk.Frame(list_card, style="ListPane.TFrame")
        project_list_header.pack(fill="x", pady=(0, 9))
        ttk.Label(project_list_header, text="我的项目", style="CardTitle.TLabel").pack(side="left")
        project_table = ttk.Frame(list_card, style="Card.TFrame")
        self.project_table = project_table
        # The empty state stays content-sized; real project data expands into the available viewport.
        project_table.pack(fill="x", expand=False)
        project_table.rowconfigure(0, weight=1)
        project_table.columnconfigure(0, weight=1)
        self.team_projects_tree = ttk.Treeview(
            project_table,
            columns=("name", "domain", "role"),
            # Do not show an empty table header while the service is disconnected.
            show="",
            selectmode="browse",
            style="ProjectTree.Treeview",
            height=10,
        )
        self._configure_table_rows(self.team_projects_tree)
        self.team_projects_tree.heading("name", text="项目名称")
        self.team_projects_tree.heading("domain", text="领域")
        self.team_projects_tree.heading("role", text="团队角色")
        self.team_projects_tree.column("name", width=148, minwidth=110, anchor="w")
        self.team_projects_tree.column("domain", width=84, minwidth=64, anchor="w")
        self.team_projects_tree.column("role", width=72, minwidth=58, anchor="center")
        self.project_vertical_scrollbar = ttk.Scrollbar(project_table, orient="vertical", command=self.team_projects_tree.yview)
        self.project_horizontal_scrollbar = ttk.Scrollbar(project_table, orient="horizontal", command=self.team_projects_tree.xview)
        self.team_projects_tree.grid(row=0, column=0, sticky="nsew")
        self.project_vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        self.project_horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        self._bind_optional_horizontal_scrollbar(self.team_projects_tree, self.project_horizontal_scrollbar)
        self._bind_optional_vertical_scrollbar(self.team_projects_tree, self.project_vertical_scrollbar)
        self.project_table_empty_state = self._create_table_empty_state(
            project_table,
            "连接团队账号以查看项目",
            "连接后显示当前账号可访问的项目。",
            symbol="projects",
        )
        ttk.Button(
            self.project_table_empty_state[1],
            text="连接团队账号",
            style="Primary.TButton",
            command=self.show_team_connection,
        ).pack(anchor="center", pady=(12, 0))
        self._set_project_table_rows_visible(False)
        self.team_projects_tree.bind("<<TreeviewSelect>>", self._on_project_selected)

        workbench_status = ttk.Frame(detail_card, style="Card.TFrame", padding=(0, 4))
        workbench_status.pack(fill="x")
        activity_heading = ttk.Frame(workbench_status, style="Card.TFrame")
        activity_heading.pack(fill="x", pady=(1, 10))
        ttk.Label(activity_heading, text="近期动态", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(activity_heading, text="账号同步", style="Muted.TLabel").pack(side="right")

        pending_item = ttk.Frame(workbench_status, style="ActivityItem.TFrame", padding=(10, 8))
        pending_item.pack(fill="x", pady=(0, 7))
        ttk.Label(pending_item, text="待处理事项", style="ActivityTitle.TLabel").pack(anchor="w", pady=(0, 3))
        self.workbench_pending_summary = ttk.Label(
            pending_item,
            text="连接后同步待审批提案与待复核任务。",
            style="ActivityBody.TLabel",
            wraplength=310,
            justify="left",
        )
        self.workbench_pending_summary.pack(anchor="w")

        recent_item = ttk.Frame(workbench_status, style="ActivityItem.TFrame", padding=(10, 8))
        recent_item.pack(fill="x")
        ttk.Label(recent_item, text="最近运行", style="ActivityTitle.TLabel").pack(anchor="w", pady=(0, 3))
        self.recent_run_summary = ttk.Label(
            recent_item,
            text="连接后同步所属工作流的最近运行。",
            style="ActivityBody.TLabel",
            wraplength=310,
            justify="left",
        )
        self.recent_run_summary.pack(anchor="w")

        quick_actions = ttk.Frame(workbench_status, style="Card.TFrame")
        quick_actions.pack(fill="x", pady=(13, 0))
        ttk.Label(quick_actions, text="快捷操作", style="Eyebrow.TLabel").pack(anchor="w", pady=(0, 6))
        shortcut_row = ttk.Frame(quick_actions, style="Card.TFrame")
        shortcut_row.pack(fill="x")
        shortcut_row.columnconfigure((0, 1), weight=1, uniform="workbench_shortcut")
        ttk.Button(shortcut_row, text="模板市场", style="Quiet.TButton", command=self.show_templates).grid(
            row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 4)
        )
        ttk.Button(shortcut_row, text="论文复现", style="Quiet.TButton", command=self.show_reproductions).grid(
            row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 4)
        )
        ttk.Button(shortcut_row, text="Agent 对话", style="Quiet.TButton", command=self.show_agent).grid(
            row=1, column=0, columnspan=2, sticky="ew"
        )

        # Object details only appear after the user selects a real accessible project.
        self.project_context_area = ttk.Frame(detail_card, style="Card.TFrame", padding=(2, 12, 2, 2))
        self.project_context_area.pack_forget()
        self.project_detail_title = ttk.Label(self.project_context_area, text="项目详情", style="CardTitle.TLabel")
        self.project_detail_title.pack(anchor="w", pady=(2, 5))
        self.project_detail_summary = self._create_detail_text(self.project_context_area)
        self._set_detail_fields(
            self.project_detail_summary,
            [("项目详情", "选择一个项目查看领域、角色与登记数据版本。", "field_value")],
        )

        project_actions = ttk.Frame(self.project_context_area, style="Card.TFrame", padding=(11, 9))
        project_actions.pack(fill="x", pady=(12, 0))
        ttk.Label(project_actions, text="数据与质量", style="Eyebrow.TLabel").pack(anchor="w")
        self.project_quality_button = ttk.Button(
            project_actions,
            text="打开数据质量检查",
            style="Quiet.TButton",
            command=self.show_quality,
        )
        self.project_quality_button.pack(anchor="w", pady=(6, 0))

        workflow_panel = ttk.Frame(self.project_context_area, style="Card.TFrame", padding=(11, 9))
        workflow_panel.pack(fill="x", pady=(14, 0))
        ttk.Label(workflow_panel, text="项目工作流", style="CardTitle.TLabel").pack(anchor="w")
        self.workflow_project_context = ttk.Label(
            workflow_panel,
            text="尚未选择项目",
            style="Eyebrow.TLabel",
            wraplength=360,
            justify="left",
        )
        self.workflow_project_context.pack(anchor="w", pady=(5, 0))
        ttk.Label(
            workflow_panel,
            text="工作流列表服务尚未接入。运行状态、历史与结果应从所属工作流进入。",
            style="Muted.TLabel",
            wraplength=360,
            justify="left",
        ).pack(anchor="w", pady=(5, 8))
        ttk.Button(
            workflow_panel,
            text="新建工作流（尚未接入）",
            style="Toolbar.TButton",
            state="disabled",
        ).pack(anchor="w")
        self.workflow_preview_button = ttk.Button(
            workflow_panel,
            text="查看工作流编辑器预览",
            style="Quiet.TButton",
            command=self.show_workflow_editor_preview,
            state="disabled",
        )
        self.workflow_preview_button.pack(anchor="w", pady=(7, 0))
        for panel in (access_card, list_card, detail_card):
            for label in panel.winfo_children():
                if isinstance(label, ttk.Label):
                    self._bind_responsive_wraplength(label, panel)

    def _build_proposals_page(self) -> None:
        """Build the proposal review page with approval gated by the current member role."""
        self.proposals_page = ttk.Frame(self.page_stack, style="App.TFrame")
        self.proposals_page.grid(row=0, column=0, sticky="nsew")

        _, card, detail = self._create_split_workspace(self.proposals_page, "proposal_workspace")
        # Reserve a fixed review area before packing the scrolling inspector content.
        self.proposal_actions = ttk.Frame(detail, style="InspectorActions.TFrame")
        self.proposal_actions.pack(side="bottom", fill="x", pady=(12, 0))
        ttk.Separator(self.proposal_actions, orient="horizontal").grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.proposal_actions.columnconfigure(0, weight=1)
        toolbar = ttk.Frame(card, style="Card.TFrame")
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="AgentArts 提案队列", style="Eyebrow.TLabel").pack(side="left")
        self.refresh_proposals_button = ttk.Button(
            toolbar,
            text="刷新",
            style="Quiet.TButton",
            command=self.load_run_proposals,
        )
        self.refresh_proposals_button.pack(side="right")
        self.proposals_list_title = ttk.Label(card, text="提案列表", style="CardTitle.TLabel")
        self.proposals_list_title.pack(anchor="w", pady=(3, 0))
        self.proposals_status = ttk.Label(
            card,
            text="请先在工作台连接账号。",
            style="Muted.TLabel",
        )
        self.proposals_status.pack(anchor="w", pady=(5, 12))

        proposal_table = ttk.Frame(card, style="Card.TFrame")
        proposal_table.pack(fill="both", expand=True)
        proposal_table.rowconfigure(0, weight=1)
        proposal_table.columnconfigure(0, weight=1)
        self.proposals_tree = ttk.Treeview(
            proposal_table,
            columns=("status", "template", "dataset", "expires"),
            show="headings",
            selectmode="browse",
            style="ProjectTree.Treeview",
            height=9,
        )
        self._configure_table_rows(self.proposals_tree)
        self.proposals_tree.heading("status", text="状态")
        self.proposals_tree.heading("template", text="固定模板")
        self.proposals_tree.heading("dataset", text="数据版本")
        self.proposals_tree.heading("expires", text="有效期至")
        self.proposals_tree.column("status", width=64, minwidth=52, anchor="center")
        self.proposals_tree.column("template", width=96, minwidth=72, anchor="w")
        self.proposals_tree.column("dataset", width=78, minwidth=60, anchor="w")
        self.proposals_tree.column("expires", width=88, minwidth=72, anchor="w")
        proposal_scrollbar = ttk.Scrollbar(proposal_table, orient="vertical", command=self.proposals_tree.yview)
        proposal_horizontal_scrollbar = ttk.Scrollbar(proposal_table, orient="horizontal", command=self.proposals_tree.xview)
        self.proposals_tree.configure(yscrollcommand=proposal_scrollbar.set)
        self.proposals_tree.grid(row=0, column=0, sticky="nsew")
        proposal_scrollbar.grid(row=0, column=1, sticky="ns")
        proposal_horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        self._bind_optional_horizontal_scrollbar(self.proposals_tree, proposal_horizontal_scrollbar)
        self.proposal_table_empty_state = self._create_table_empty_state(
            proposal_table,
            "连接团队账号以读取提案",
            "此处显示当前账号可见的 AgentArts 提案及其审核状态。",
            symbol="proposals",
        )
        self.proposals_tree.bind("<<TreeviewSelect>>", self._on_proposal_selected)

        ttk.Label(detail, text="提案检查器", style="Eyebrow.TLabel").pack(anchor="w", pady=(0, 9))
        self.proposal_detail_title = ttk.Label(
            detail,
            text="选择一条提案查看只读详情",
            style="CardTitle.TLabel",
        )
        self.proposal_detail_title.pack(anchor="w", pady=(0, 12))
        ttk.Separator(detail, orient="horizontal").pack(fill="x", pady=(0, 12))
        self.proposal_detail_summary = self._create_detail_text(detail)
        self._set_detail_fields(
            self.proposal_detail_summary,
            [("审核说明", "提案只表示待审核请求，不代表已批准或已运行。", "field_value")],
        )

        self.view_template_button = ttk.Button(
            self.proposal_actions,
            text="查看固定模板说明",
            style="Quiet.TButton",
            command=self.show_selected_template_contract,
            state="disabled",
        )
        self.view_template_button.grid(row=1, column=0, sticky="ew")

        self.approve_proposal_button = ttk.Button(
            self.proposal_actions,
            text="批准并运行固定合成冒烟任务",
            style="Primary.TButton",
            command=self.approve_selected_proposal,
            state="disabled",
        )
        self.approve_proposal_button.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for panel in (card, detail):
            for label in panel.winfo_children():
                if isinstance(label, ttk.Label):
                    self._bind_responsive_wraplength(label, panel)

    def _build_runs_page(self) -> None:
        """Show persisted run state, result and trace correlation without retry controls."""
        self.runs_page = ttk.Frame(self.page_stack, style="App.TFrame")
        self.runs_page.grid(row=0, column=0, sticky="nsew")
        _, card, detail = self._create_split_workspace(self.runs_page, "run_workspace")
        # Keep report actions within the inspector viewport while event text grows.
        self.run_report_actions = ttk.Frame(detail, style="InspectorActions.TFrame")
        self.run_report_actions.pack(side="bottom", fill="x", pady=(12, 0))
        ttk.Separator(self.run_report_actions, orient="horizontal").grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10),
        )
        self.run_report_actions.columnconfigure((0, 1), weight=1)
        toolbar = ttk.Frame(card, style="Card.TFrame")
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="运行记录", style="Eyebrow.TLabel").pack(side="left")
        self.refresh_runs_button = ttk.Button(
            toolbar,
            text="刷新",
            style="Quiet.TButton",
            command=self.load_runs,
        )
        self.refresh_runs_button.pack(side="right")
        self.runs_list_title = ttk.Label(card, text="运行列表", style="CardTitle.TLabel")
        self.runs_list_title.pack(anchor="w", pady=(3, 0))
        self.runs_status = ttk.Label(card, text="请先在工作台连接账号。", style="Muted.TLabel")
        self.runs_status.pack(anchor="w", pady=(5, 8))
        # Let the history scroll independently while the selected run stays alongside it.
        runs_table = ttk.Frame(card, style="Card.TFrame")
        runs_table.pack(fill="both", expand=True)
        runs_table.rowconfigure(0, weight=1)
        runs_table.columnconfigure(0, weight=1)
        self.runs_tree = ttk.Treeview(
            runs_table,
            columns=("status", "template", "created"),
            show="headings",
            selectmode="browse",
            style="ProjectTree.Treeview",
            height=9,
        )
        self._configure_table_rows(self.runs_tree)
        self.runs_tree.heading("status", text="状态")
        self.runs_tree.heading("template", text="固定模板")
        self.runs_tree.heading("created", text="提交时间")
        self.runs_tree.column("status", width=64, minwidth=52, anchor="center")
        self.runs_tree.column("template", width=96, minwidth=72, anchor="w")
        self.runs_tree.column("created", width=112, minwidth=84, anchor="w")
        runs_scrollbar = ttk.Scrollbar(runs_table, orient="vertical", command=self.runs_tree.yview)
        runs_horizontal_scrollbar = ttk.Scrollbar(runs_table, orient="horizontal", command=self.runs_tree.xview)
        self.runs_tree.configure(yscrollcommand=runs_scrollbar.set)
        self.runs_tree.grid(row=0, column=0, sticky="nsew")
        runs_scrollbar.grid(row=0, column=1, sticky="ns")
        runs_horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        self._bind_optional_horizontal_scrollbar(self.runs_tree, runs_horizontal_scrollbar)
        self.runs_table_empty_state = self._create_table_empty_state(
            runs_table,
            "连接团队账号以查看运行",
            "此处仅显示当前账号可见的合成任务状态和提交时间。",
            symbol="runs",
        )
        self.runs_tree.bind("<<TreeviewSelect>>", self._on_run_selected)
        ttk.Label(detail, text="运行检查器", style="Eyebrow.TLabel").pack(anchor="w", pady=(0, 9))
        self.run_detail_title = ttk.Label(detail, text="选择一条运行记录", style="CardTitle.TLabel")
        self.run_detail_title.pack(anchor="w", pady=(0, 12))
        ttk.Separator(detail, orient="horizontal").pack(fill="x", pady=(0, 12))
        self.run_detail_summary = self._create_detail_text(detail)
        self._set_detail_fields(
            self.run_detail_summary,
            [("运行记录", "仅展示固定合成冒烟任务状态，不提供取消或手动重试。", "field_value")],
        )
        ttk.Label(detail, text="状态时间线", style="CardTitle.TLabel").pack(anchor="w", pady=(16, 8))
        timeline_panel = ttk.Frame(detail, style="Timeline.TFrame", padding=(8, 6))
        timeline_panel.pack(fill="x")
        timeline_panel.columnconfigure(0, weight=1)
        self.run_event_timeline = tk.Text(
            timeline_panel,
            width=1,
            height=5,
            wrap="word",
            font=FONTS["ui_small"],
            background=COLORS["surface_alt"],
            foreground=COLORS["ink_soft"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=2,
            pady=1,
            selectbackground=COLORS["sidebar_active"],
            selectforeground=COLORS["white"],
            takefocus=True,
            cursor="xterm",
            state="disabled",
        )
        self.run_event_timeline.grid(row=0, column=0, sticky="nsew")
        timeline_scrollbar = ttk.Scrollbar(timeline_panel, orient="vertical", command=self.run_event_timeline.yview)
        timeline_scrollbar.grid(row=0, column=1, sticky="ns", padx=(5, 0))
        self.run_event_timeline.configure(yscrollcommand=timeline_scrollbar.set)
        self.run_event_timeline.tag_configure("timeline_placeholder", foreground=COLORS["muted"], font=FONTS["ui_small"])
        self.run_event_timeline.tag_configure("timeline_sequence", foreground=COLORS["accent_text"], font=FONTS["mono_small"])
        self.run_event_timeline.tag_configure("timeline_connector", foreground=COLORS["line"], font=FONTS["mono_small"])
        self.run_event_timeline.tag_configure("timeline_timestamp", foreground=COLORS["muted"], font=FONTS["mono_small"])
        self.run_event_timeline.tag_configure("timeline_pending", foreground=COLORS["warning_text"], font=FONTS["ui_bold"])
        self.run_event_timeline.tag_configure("timeline_running", foreground=COLORS["accent_text"], font=FONTS["ui_bold"])
        self.run_event_timeline.tag_configure("timeline_success", foreground=COLORS["moss"], font=FONTS["ui_bold"])
        self.run_event_timeline.tag_configure("timeline_error", foreground=COLORS["danger_text"], font=FONTS["ui_bold"])
        self.run_event_timeline.tag_configure("timeline_error_code", foreground=COLORS["warning_text"], font=FONTS["mono_small"])
        self._set_run_event_timeline("选择一条运行记录查看持久化状态事件。")
        self.export_run_report_button = ttk.Button(
            self.run_report_actions,
            text="导出 HTML 报告",
            style="Quiet.TButton",
            command=self.export_selected_run_report,
            state="disabled",
        )
        self.export_run_report_button.grid(row=1, column=0, sticky="ew", padx=(0, 5))
        self.export_run_pdf_button = ttk.Button(
            self.run_report_actions,
            text="导出 PDF 报告",
            style="Quiet.TButton",
            command=self.export_selected_run_pdf,
            state="disabled",
        )
        self.export_run_pdf_button.grid(row=1, column=1, sticky="ew", padx=(5, 0))
        for panel in (card, detail):
            for label in panel.winfo_children():
                if isinstance(label, ttk.Label):
                    self._bind_responsive_wraplength(label, panel)

    def _build_new_navigation_pages(self) -> None:
        """Build V4 pages with deliberate, honest layouts for services that are not wired yet."""
        self.reproductions_page = ttk.Frame(self.page_stack, style="App.TFrame", padding=(4, 8))
        self.reproductions_page.grid(row=0, column=0, sticky="nsew")
        reproduction_header = ttk.Frame(self.reproductions_page, style="App.TFrame")
        reproduction_header.pack(fill="x", pady=(0, 12))
        reproduction_header.columnconfigure(0, weight=1)
        ttk.Label(reproduction_header, text="复现任务", style="PageSectionTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            reproduction_header,
            text="复现论文主张或核验实验结果；任务可独立建立，也可关联项目。",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.reproduction_new_button = ttk.Button(
            reproduction_header,
            text="新建复现任务",
            style="Primary.TButton",
            state="disabled",
        )
        self.reproduction_new_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))

        service_banner = ttk.Frame(self.reproductions_page, style="ServiceBanner.TFrame", padding=(13, 10))
        service_banner.pack(fill="x", pady=(0, 12))
        service_banner.columnconfigure(0, weight=1)
        ttk.Label(service_banner, text="复现任务服务未连接", style="ServiceBannerTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            service_banner,
            text="目前无法判断账号下是否已有任务；连接服务后才能读取或创建任务。",
            style="ServiceBannerBody.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Button(
            service_banner,
            text="配置服务连接",
            style="Toolbar.TButton",
            command=self.show_service_settings,
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(14, 0))

        process_panel = ttk.Frame(self.reproductions_page, style="ContentPanel.TFrame", padding=(13, 10))
        process_panel.pack(fill="x", pady=(0, 12))
        ttk.Label(process_panel, text="任务核验路径", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        process_strip = ttk.Frame(process_panel, style="ProcessStrip.TFrame")
        process_strip.pack(fill="x")
        process_steps = (
            ("01", "明确核验目标", "记录论文主张或实验基准"),
            ("02", "配置数据与工作流", "复现任务独立于项目，可选关联"),
            ("03", "比较结果并复核", "按预设规则检查并保留溯源"),
        )
        for column, (number, title, description) in enumerate(process_steps):
            process_strip.columnconfigure(column, weight=1, uniform="reproduction_process")
            step = ttk.Frame(process_strip, style="ProcessStrip.TFrame", padding=(8, 2))
            step.grid(row=0, column=column, sticky="nsew", padx=(0, 8) if column < 2 else (0, 0))
            ttk.Label(step, text=number, style="ProcessIndex.TLabel").pack(side="left", anchor="n", padx=(0, 9))
            copy = ttk.Frame(step, style="ProcessStrip.TFrame")
            copy.pack(side="left", fill="x", expand=True)
            ttk.Label(copy, text=title, style="ProcessTitle.TLabel").pack(anchor="w")
            ttk.Label(copy, text=description, style="ProcessBody.TLabel", wraplength=260).pack(
                anchor="w", pady=(3, 0)
            )

        reproduction_results = ttk.Frame(self.reproductions_page, style="ContentPanel.TFrame", padding=(13, 11))
        reproduction_results.pack(fill="x")
        result_heading = ttk.Frame(reproduction_results, style="Card.TFrame")
        result_heading.pack(fill="x", pady=(0, 8))
        ttk.Label(result_heading, text="复现任务", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(result_heading, text="等待服务连接", style="PageEmptyStatus.TLabel").pack(side="right")
        ttk.Separator(reproduction_results, orient="horizontal").pack(fill="x", pady=(0, 2))

        self.reproduction_empty_state = ttk.Frame(reproduction_results, style="InlineEmpty.TFrame", padding=(8, 13))
        self.reproduction_empty_state.pack(fill="x")
        reproduction_symbol = tk.Canvas(
            self.reproduction_empty_state,
            width=44,
            height=44,
            background=COLORS["surface"],
            highlightthickness=0,
            takefocus=False,
        )
        reproduction_symbol.pack(side="left", padx=(0, 13))
        reproduction_symbol.create_rectangle(8, 5, 31, 38, outline=COLORS["line"], width=1.5)
        reproduction_symbol.create_line(13, 13, 26, 13, fill=COLORS["accent"], width=2)
        reproduction_symbol.create_line(13, 19, 26, 19, fill=COLORS["line"], width=1.5)
        reproduction_symbol.create_oval(24, 23, 37, 36, outline=COLORS["accent"], width=1.5)
        reproduction_symbol.create_line(34, 34, 40, 40, fill=COLORS["accent"], width=2)
        empty_copy = ttk.Frame(self.reproduction_empty_state, style="InlineEmpty.TFrame")
        empty_copy.pack(side="left", fill="x", expand=True)
        ttk.Label(empty_copy, text="连接后查看复现任务", style="InlineEmptyTitle.TLabel").pack(anchor="w")
        ttk.Label(
            empty_copy,
            text="服务未连接，因此暂时不能判断任务列表是否为空，也不会生成示例任务或检验结论。",
            style="InlineEmptyBody.TLabel",
            wraplength=760,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        self.templates_page = ttk.Frame(self.page_stack, style="App.TFrame", padding=(4, 8))
        self.templates_page.grid(row=0, column=0, sticky="nsew")
        template_banner = ttk.Frame(self.templates_page, style="ServiceBanner.TFrame", padding=(13, 10))
        template_banner.pack(fill="x", pady=(0, 12))
        template_banner.columnconfigure(0, weight=1)
        ttk.Label(template_banner, text="模板目录暂不可用", style="ServiceBannerTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            template_banner,
            text="连接目录服务后才能读取真实模板；当前不展示演示卡片或虚构模板数量。",
            style="ServiceBannerBody.TLabel",
            wraplength=760,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Button(
            template_banner,
            text="配置服务连接",
            style="Toolbar.TButton",
            command=self.show_service_settings,
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(14, 0))

        template_layout = ttk.Frame(self.templates_page, style="App.TFrame")
        # Keep the disconnected catalog content-sized instead of stretching an empty grid.
        template_layout.pack(fill="x")
        template_layout.columnconfigure(0, minsize=190, weight=0)
        template_layout.columnconfigure(1, weight=1)
        template_layout.rowconfigure(0, weight=0)

        catalog_sidebar = ttk.Frame(template_layout, style="CatalogSidebar.TFrame", padding=(9, 10))
        catalog_sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(catalog_sidebar, text="模板场景", style="ModuleHeading.TLabel").pack(
            anchor="w", padx=7, pady=(3, 9)
        )
        self.template_category_buttons: dict[str, ttk.Button] = {}
        for category_key, category_label in (
            ("all", "全部模板"),
            ("general", "通用科研"),
            ("medical", "医学科研"),
            ("reproduction", "论文复现与审查"),
            ("control", "控制与调度"),
        ):
            category_button = ttk.Button(
                catalog_sidebar,
                text=category_label,
                style="CatalogCategoryActive.TButton" if category_key == "all" else "CatalogCategory.TButton",
                state="disabled",
            )
            category_button.pack(fill="x", pady=2)
            self.template_category_buttons[category_key] = category_button
        ttk.Label(
            catalog_sidebar,
            text="目录连接后可按场景筛选。",
            style="Muted.TLabel",
            wraplength=150,
            justify="left",
        ).pack(anchor="w", padx=7, pady=(12, 0))

        template_content = ttk.Frame(template_layout, style="App.TFrame")
        template_content.grid(row=0, column=1, sticky="ew")
        template_content.columnconfigure(0, weight=1)
        template_results = ttk.Frame(template_content, style="ContentPanel.TFrame", padding=(13, 11))
        template_results.grid(row=0, column=0, sticky="ew")
        result_heading = ttk.Frame(template_results, style="Card.TFrame")
        result_heading.pack(fill="x", pady=(0, 8))
        ttk.Label(result_heading, text="模板目录", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(result_heading, text="尚未读取", style="PageEmptyStatus.TLabel").pack(side="right")
        ttk.Separator(template_results, orient="horizontal").pack(fill="x", pady=(0, 2))
        self.template_empty_state = ttk.Frame(template_results, style="InlineEmpty.TFrame", padding=(8, 15))
        self.template_empty_state.pack(fill="x")
        template_symbol = tk.Canvas(
            self.template_empty_state,
            width=44,
            height=44,
            background=COLORS["surface"],
            highlightthickness=0,
            takefocus=False,
        )
        template_symbol.pack(side="left", padx=(0, 13))
        template_symbol.create_rectangle(7, 6, 35, 38, outline=COLORS["line"], width=1.5)
        template_symbol.create_line(13, 14, 29, 14, fill=COLORS["accent"], width=2)
        template_symbol.create_line(13, 21, 29, 21, fill=COLORS["line"], width=1.5)
        template_symbol.create_line(13, 28, 25, 28, fill=COLORS["line"], width=1.5)
        template_copy = ttk.Frame(self.template_empty_state, style="InlineEmpty.TFrame")
        template_copy.pack(side="left", fill="x", expand=True)
        ttk.Label(template_copy, text="连接后浏览可用模板", style="InlineEmptyTitle.TLabel").pack(anchor="w")
        ttk.Label(
            template_copy,
            text="目录接入后展示真实模板的固定版本、工作流结构、适用范围与依赖。",
            style="InlineEmptyBody.TLabel",
            wraplength=700,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        self.agent_page = ttk.Frame(self.page_stack, style="App.TFrame", padding=(8, 16))
        self.agent_page.grid(row=0, column=0, sticky="nsew")
        agent_layout = ttk.Frame(self.agent_page, style="App.TFrame")
        agent_layout.pack(fill="both", expand=True)
        agent_layout.columnconfigure(0, weight=1)
        agent_layout.columnconfigure(1, minsize=250, weight=0)
        agent_layout.rowconfigure(0, weight=1)

        conversation = ttk.Frame(agent_layout, style="App.TFrame", padding=(14, 12))
        conversation.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        conversation.rowconfigure(1, weight=1)
        conversation.columnconfigure(0, weight=1)
        conversation_header = ttk.Frame(conversation, style="App.TFrame")
        conversation_header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(conversation_header, text="研究对话", style="PageSectionTitle.TLabel").pack(side="left")
        ttk.Label(conversation_header, text="服务未连接", style="PageEmptyStatus.TLabel").pack(side="right")

        # Keep the empty state content-sized and centered; an expanded white frame reads as an empty canvas.
        conversation_empty = ttk.Frame(conversation, style="App.TFrame")
        conversation_empty.grid(row=1, column=0, sticky="nsew")
        self.agent_empty_state = self._create_page_empty_state(
            conversation_empty,
            "开启一次科研讨论",
            "连接后围绕研究问题讨论，并引用项目、复现任务或工作流。",
            "当前不会发送或保存消息。",
            motif="agent",
            empty_style="PageEmpty.TFrame",
        )
        self.agent_empty_state.configure(padding=(24, 22))
        self.agent_empty_state.place(relx=0.5, rely=0.5, anchor="center")
        ttk.Button(
            self.agent_empty_state,
            text="配置服务连接",
            style="Primary.TButton",
            command=self.show_service_settings,
        ).pack(anchor="center", pady=(3, 0))

        context_sidebar = ttk.Frame(agent_layout, style="ContextRail.TFrame", padding=(12, 12))
        context_sidebar.grid(row=0, column=1, sticky="nsew")
        ttk.Label(context_sidebar, text="上下文与记录", style="RailHeading.TLabel").pack(anchor="w")
        ttk.Label(context_sidebar, text="当前引用", style="RailEyebrow.TLabel").pack(anchor="w", pady=(15, 5))
        ttk.Label(
            context_sidebar,
            text="未引用项目、复现任务或工作流。",
            style="RailBody.TLabel",
            wraplength=220,
            justify="left",
        ).pack(anchor="w", pady=(0, 15))
        ttk.Label(context_sidebar, text="提案与工具调用", style="RailEyebrow.TLabel").pack(anchor="w")
        ttk.Label(
            context_sidebar,
            text="连接对话服务后，在此显示相关提案和工具调用记录。",
            style="RailBody.TLabel",
            wraplength=220,
            justify="left",
        ).pack(anchor="w", pady=(5, 9))
        ttk.Button(
            context_sidebar,
            text="查看待审批提案",
            style="Rail.TButton",
            command=self.show_proposals,
        ).pack(anchor="w")

        self.profile_settings_page = ttk.Frame(self.page_stack, style="App.TFrame", padding=(8, 16))
        self.profile_settings_page.grid(row=0, column=0, sticky="nsew")
        settings_layout = ttk.Frame(self.profile_settings_page, style="App.TFrame")
        settings_layout.pack(fill="both", expand=True)
        settings_layout.columnconfigure(0, minsize=205, weight=0)
        settings_layout.columnconfigure(1, weight=1)
        settings_layout.rowconfigure(0, weight=1)

        settings_directory = ttk.Frame(settings_layout, style="CatalogSidebar.TFrame", padding=(8, 8))
        settings_directory.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ttk.Label(settings_directory, text="设置目录", style="ModuleHeading.TLabel").pack(
            anchor="w",
            padx=8,
            pady=(4, 9),
        )
        settings_content = ttk.Frame(settings_layout, style="App.TFrame", padding=(18, 16))
        settings_content.grid(row=0, column=1, sticky="nsew")

        sections = {
            "profile": ("个人资料", "管理显示名称、头像与工作空间身份。", "账号资料服务尚未接入。"),
            "preferences": ("偏好设置", "设置界面语言、外观与默认工作区。", "偏好保存服务尚未接入。"),
            "notifications": ("通知", "配置任务进度、提案审批与系统消息。", "通知服务尚未接入。"),
            "security": ("账号安全", "查看登录方式、会话与安全选项。", "账号安全服务尚未接入。"),
            "workspace": ("工作空间与权限", "管理工作空间成员和资源访问权限。", "工作空间权限服务尚未接入。"),
            "services": ("模型与服务", "配置本地服务连接；模型与算力选项按账号权限开放。", "模型和科研算力服务尚未接入。"),
        }
        self.settings_directory_buttons = {}
        self.settings_section_title = ttk.Label(
            settings_content,
            text="个人资料",
            style="PageSectionTitle.TLabel",
        )
        self.settings_section_title.pack(anchor="w")
        self.settings_section_description = ttk.Label(
            settings_content,
            text="",
            style="SettingsBody.TLabel",
            wraplength=650,
            justify="left",
        )
        self.settings_section_description.pack(anchor="w", pady=(6, 14))
        setting_status_card = ttk.Frame(settings_content, style="ContentPanel.TFrame", padding=(14, 12))
        setting_status_card.pack(fill="x")
        ttk.Label(setting_status_card, text="服务状态", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        setting_status_row = ttk.Frame(setting_status_card, style="SettingStatus.TFrame", padding=(10, 8))
        setting_status_row.pack(fill="x")
        ttk.Frame(setting_status_row, style="SettingStatusRail.TFrame", width=3).pack(
            side="left", fill="y", padx=(0, 10)
        )
        self.settings_section_status = ttk.Label(
            setting_status_row,
            text="",
            style="SettingStatus.TLabel",
            wraplength=650,
            justify="left",
        )
        self.settings_section_status.pack(anchor="w", fill="x")
        settings_actions = ttk.Frame(settings_content, style="App.TFrame")
        self.settings_service_button = ttk.Button(
            settings_actions,
            text="配置服务连接",
            style="Toolbar.TButton",
            command=self.show_service_settings,
        )
        self.settings_service_button.pack(side="left", padx=(0, 8))
        self.settings_quick_start_button = ttk.Button(
            settings_actions,
            text="快速开始",
            style="Toolbar.TButton",
            command=self.show_quick_start,
        )
        self.settings_quick_start_button.pack(side="left")

        def select_settings_section(section_key: str) -> None:
            """Keep the settings directory and detail panel focused on the selected category."""
            section_title, description, status = sections[section_key]
            self.settings_section_title.configure(text=section_title)
            self.settings_section_description.configure(text=description)
            self.settings_section_status.configure(text=status)
            for key, nav_button in self.settings_directory_buttons.items():
                nav_button.configure(
                    style="SettingsNavActive.TButton" if key == section_key else "SettingsNav.TButton"
                )
            if section_key == "services":
                settings_actions.pack(anchor="w", pady=(14, 0))
                self.settings_quick_start_button.pack(side="left")
            else:
                self.settings_quick_start_button.pack_forget()
                settings_actions.pack(anchor="w", pady=(14, 0))

        for section_key, (section_title, _description, _status) in sections.items():
            nav_button = ttk.Button(
                settings_directory,
                text=section_title,
                style="SettingsNav.TButton",
                command=lambda key=section_key: select_settings_section(key),
            )
            nav_button.pack(fill="x", pady=(0, 3))
            self._clear_mouse_focus_outline(nav_button)
            self.settings_directory_buttons[section_key] = nav_button
        select_settings_section("profile")

    def _show_page(self, page_key: str, title: str, context: str, page: ttk.Frame) -> None:
        """Keep the visible page, page context and selected navigation in sync."""
        self._active_page = page_key
        navigation_for_page = {
            "projects": "workbench",
            "reproductions": "workbench",
            "quality": "workbench",
            "runs": "workbench",
            "templates": "templates",
            "agent": "agent",
            "proposals": "agent",
            "settings": "settings",
        }
        self._active_nav = navigation_for_page.get(page_key, "workbench")
        heading_title = "工作台" if page_key == "projects" else title
        self.page_heading.configure(text=heading_title)
        self.page_context.configure(text=context)
        if page_key in ("projects", "reproductions"):
            self.content_layout.columnconfigure(0, minsize=0, weight=1)
            self.workbench_module_sidebar.grid(row=2, column=0, columnspan=2, sticky="ew")
            self.page_viewport.grid(row=3, column=0, columnspan=2, sticky="nsew")
        else:
            self.content_layout.columnconfigure(0, minsize=0, weight=0)
            self.workbench_module_sidebar.grid_remove()
            self.page_viewport.grid(row=3, column=0, columnspan=2, sticky="nsew")
        for key, button in self.workbench_module_buttons.items():
            selected = page_key == key
            button.configure(style="WorkbenchTabActive.TButton" if selected else "WorkbenchTab.TButton")
            self.workbench_module_indicators[key].configure(
                background=COLORS["accent"] if selected else COLORS["paper"]
            )
        show_connection_action = page_key in ("quality", "proposals", "runs") or (
            page_key == "projects" and bool(self._project_token)
        )
        if show_connection_action:
            self.team_connection_button.configure(
                text="管理团队账号" if self._project_token else "连接团队账号"
            )
            self.team_connection_button.pack(side="right")
        else:
            self.team_connection_button.pack_forget()
        for key, button in self.navigation_buttons.items():
            selected = key == self._active_nav
            button.configure(style="PrimaryNavActive.TButton" if selected else "PrimaryNav.TButton")
            self.navigation_indicators[key].configure(
                background=COLORS["accent"] if selected else COLORS["surface"]
            )
        page.tkraise()
        self.root.after_idle(lambda: self._refresh_page_viewport(reset_position=True))

    def _on_page_canvas_configure(self, event: tk.Event) -> None:
        """Keep the page surface as wide as its viewport and refresh its scroll range."""
        self.page_canvas.itemconfigure(self.page_stack_window, width=max(event.width, 1))
        self._refresh_page_viewport()

    def _fit_content_workspace_height(self, page: ttk.Frame) -> None:
        """Keep content-sized split panes tall enough after responsive reflow."""
        workspace = getattr(page, "_split_workspace", None)
        if (
            workspace is None
            or not workspace._fit_content_height
            or not workspace.winfo_exists()
            or not workspace.winfo_ismapped()
        ):
            return
        panes = workspace.winfo_children()
        if len(panes) != 2:
            LOGGER.warning("Content-sized workspace has an unexpected pane count; count=%d", len(panes))
            return

        orientation = str(workspace.cget("orient"))
        pane_heights = tuple(max(1, int(pane.winfo_reqheight())) for pane in panes)
        if orientation == "vertical":
            if pane_heights != getattr(workspace, "_last_fit_pane_heights", None):
                workspace._sash_reset_pending = True
            workspace._last_fit_pane_heights = pane_heights
            minimum_sizes = []
            for pane, required_height in zip(panes, pane_heights):
                workspace.paneconfigure(pane, minsize=required_height)
                minimum_sizes.append(required_height)
            requested_height = sum(minimum_sizes) + int(workspace.cget("sashwidth"))
        else:
            for pane, minimum_width in zip(panes, workspace._base_pane_min_sizes):
                workspace.paneconfigure(pane, minsize=minimum_width)
            requested_height = max(int(pane.winfo_reqheight()) for pane in panes)

        current_height = int(workspace.cget("height") or 0)
        if current_height == requested_height:
            return
        workspace.configure(height=requested_height)
        LOGGER.debug(
            "Content-sized workspace height updated; workspace=%s orientation=%s height=%d",
            workspace,
            orientation,
            requested_height,
        )

    def _reset_workspace_sash(self, workspace: tk.PanedWindow) -> None:
        """Place a responsive sash only after content and scroll geometry have settled."""
        try:
            if not workspace.winfo_exists():
                return
            if not workspace.winfo_ismapped():
                workspace._sash_reset_pending = True
                return
            orientation = str(workspace.cget("orient"))
            extent = int(workspace.winfo_height() if orientation == "vertical" else workspace.winfo_width())
            if extent <= 200:
                workspace._sash_reset_pending = True
                return
            left_panel, right_panel = workspace.winfo_children()
            if orientation == "vertical" and workspace._fit_content_height:
                required_left = int(left_panel.winfo_reqheight())
                required_right = int(right_panel.winfo_reqheight())
                available_for_left = extent - required_right - int(workspace.cget("sashwidth"))
                position = min(required_left, max(1, available_for_left))
            else:
                fraction = (
                    workspace._sash_vertical_fraction
                    if orientation == "vertical"
                    else workspace._sash_horizontal_fraction
                )
                position = round(extent * fraction)
            if orientation == "vertical":
                workspace.sash_place(0, 1, position)
            else:
                workspace.sash_place(0, position, 1)
            LOGGER.debug(
                "Responsive sash positioned; workspace=%s orientation=%s extent=%d position=%d",
                workspace,
                orientation,
                extent,
                position,
            )
        except tk.TclError as exc:
            LOGGER.debug("Responsive sash reset skipped; error_type=%s", type(exc).__name__)

    def _schedule_page_viewport_refresh(self) -> None:
        """Re-measure the active page after asynchronous content changes."""
        def refresh_after_layout() -> None:
            try:
                self.root.update_idletasks()
                self._refresh_page_viewport()
            except tk.TclError:
                return

        try:
            self.root.after_idle(refresh_after_layout)
        except tk.TclError:
            return

    def _refresh_page_viewport(self, *, reset_position: bool = False) -> None:
        """Size the scroll surface to the active page and reveal a bar only on overflow."""
        if not self.page_canvas.winfo_exists():
            return

        pages = {
            "quality": self.quality_page,
            "projects": self.projects_page,
            "proposals": self.proposals_page,
            "runs": self.runs_page,
            "reproductions": self.reproductions_page,
            "templates": self.templates_page,
            "agent": self.agent_page,
            "settings": self.profile_settings_page,
        }
        active_page = pages[self._active_page]
        self._fit_content_workspace_height(active_page)
        requested_height = active_page.winfo_reqheight()
        viewport_height = max(self.page_canvas.winfo_height(), 1)
        needs_scrollbar = requested_height > viewport_height + 1
        if needs_scrollbar != self._page_scrollbar_visible:
            self._page_scrollbar_visible = needs_scrollbar
            if needs_scrollbar:
                self.page_scrollbar.pack(side="right", fill="y", before=self.page_canvas)
            else:
                self.page_scrollbar.pack_forget()
            if reset_position:
                self.root.after_idle(lambda: self._refresh_page_viewport(reset_position=True))
            return

        viewport_width = max(self.page_canvas.winfo_width(), 1)
        scroll_height = max(requested_height, viewport_height)
        self.page_canvas.itemconfigure(
            self.page_stack_window,
            width=viewport_width,
            height=scroll_height,
        )
        self.page_canvas.configure(scrollregion=(0, 0, viewport_width, scroll_height))
        workspace = getattr(active_page, "_split_workspace", None)
        if workspace is not None and workspace._sash_reset_pending:
            workspace._sash_reset_pending = False
            try:
                self.root.after_idle(lambda target=workspace: self._reset_workspace_sash(target))
            except tk.TclError as exc:
                workspace._sash_reset_pending = True
                LOGGER.debug("Responsive sash scheduling skipped; error_type=%s", type(exc).__name__)
        if reset_position:
            self.page_canvas.yview_moveto(0.0)

    def _bind_page_mousewheel(self, widget: tk.Misc) -> None:
        """Bind wheel scrolling to page controls while preserving Treeview scrolling."""
        if not isinstance(widget, ttk.Treeview):
            widget.bind("<MouseWheel>", self._on_page_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_page_mousewheel(child)

    def _on_page_mousewheel(self, event: tk.Event) -> str | None:
        if isinstance(event.widget, ttk.Treeview):
            return None
        # Let long detail inspectors scroll independently before moving the whole page.
        if isinstance(event.widget, tk.Text) and event.delta:
            first, last = event.widget.yview()
            direction = -1 if event.delta > 0 else 1
            can_scroll_text = (direction < 0 and first > 0.0) or (direction > 0 and last < 1.0)
            if can_scroll_text:
                units = max(1, abs(int(event.delta)) // 120)
                event.widget.yview_scroll(direction * units, "units")
                return "break"
        first, last = self.page_canvas.yview()
        if last - first >= 1.0 or event.delta == 0:
            return None
        self.page_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _bind_optional_horizontal_scrollbar(
        self,
        tree: ttk.Treeview,
        scrollbar: ttk.Scrollbar,
    ) -> None:
        """Show horizontal navigation only while a table's columns exceed its viewport."""
        # Preserve the grid options so a later narrow resize can restore the scrollbar in place.
        scrollbar.grid_remove()
        pending_job: str | None = None

        def update_visibility() -> None:
            nonlocal pending_job
            pending_job = None
            try:
                if not tree.winfo_exists():
                    return
                if not tree.winfo_ismapped():
                    scrollbar.grid_remove()
                    return
                first, last = tree.xview()
                is_overflowing = first > 0.001 or last < 0.999
                is_managed = scrollbar.winfo_manager() == "grid"
                if is_overflowing and not is_managed:
                    scrollbar.grid()
                elif not is_overflowing and is_managed:
                    scrollbar.grid_remove()
            except tk.TclError as exc:
                LOGGER.debug(
                    "Optional table scrollbar update skipped; error_type=%s",
                    type(exc).__name__,
                )

        def queue_visibility_update(*fractions: str) -> None:
            nonlocal pending_job
            if fractions:
                scrollbar.set(*fractions)
            if pending_job is not None:
                return
            try:
                pending_job = self.root.after_idle(update_visibility)
            except tk.TclError as exc:
                LOGGER.debug(
                    "Optional table scrollbar scheduling skipped; error_type=%s",
                    type(exc).__name__,
                )

        tree.configure(xscrollcommand=queue_visibility_update)
        tree.bind("<Configure>", lambda _event: queue_visibility_update(), add="+")
        queue_visibility_update()

    def _bind_optional_vertical_scrollbar(
        self,
        tree: ttk.Treeview,
        scrollbar: ttk.Scrollbar,
    ) -> None:
        """Show a vertical scrollbar only when loaded records exceed the visible rows."""
        scrollbar.grid_remove()
        pending_job: str | None = None

        def update_visibility() -> None:
            nonlocal pending_job
            pending_job = None
            try:
                if not tree.winfo_exists():
                    return
                if not tree.winfo_ismapped():
                    scrollbar.grid_remove()
                    return
                first, last = tree.yview()
                is_overflowing = first > 0.001 or last < 0.999
                is_managed = scrollbar.winfo_manager() == "grid"
                if is_overflowing and not is_managed:
                    scrollbar.grid()
                elif not is_overflowing and is_managed:
                    scrollbar.grid_remove()
            except tk.TclError as exc:
                LOGGER.debug(
                    "Optional vertical scrollbar update skipped; error_type=%s",
                    type(exc).__name__,
                )

        def queue_visibility_update(*fractions: str) -> None:
            nonlocal pending_job
            if fractions:
                scrollbar.set(*fractions)
            if pending_job is not None:
                return
            try:
                pending_job = self.root.after_idle(update_visibility)
            except tk.TclError as exc:
                LOGGER.debug(
                    "Optional vertical scrollbar scheduling skipped; error_type=%s",
                    type(exc).__name__,
                )

        tree.configure(yscrollcommand=queue_visibility_update)
        tree.bind("<Configure>", lambda _event: queue_visibility_update(), add="+")
        queue_visibility_update()

    def _set_project_table_rows_visible(self, visible: bool) -> None:
        """Use the empty-state surface in place of an empty, bordered Treeview."""
        try:
            if visible:
                self.team_projects_tree.grid()
                self.root.after_idle(self._sync_project_table_scrollbars)
            else:
                self.team_projects_tree.grid_remove()
                self.project_vertical_scrollbar.grid_remove()
                self.project_horizontal_scrollbar.grid_remove()
        except tk.TclError as exc:
            LOGGER.debug("Project table visibility update skipped; error_type=%s", type(exc).__name__)

    def _set_project_workspace_expanded(self, expanded: bool) -> None:
        """Keep a disconnected workbench compact and let real project data use the viewport."""
        try:
            if not hasattr(self, "project_workspace"):
                return
            self.project_workspace.pack_configure(
                fill="both" if expanded else "x",
                expand=expanded,
            )
            project_table = getattr(self, "project_table", None)
            if project_table is not None:
                project_table.pack_configure(
                    fill="both" if expanded else "x",
                    expand=expanded,
                )
            LOGGER.debug("Project workspace density changed; expanded=%s", expanded)
            self._schedule_page_viewport_refresh()
        except tk.TclError as exc:
            LOGGER.debug("Project workspace density update skipped; error_type=%s", type(exc).__name__)

    def _sync_project_table_scrollbars(self) -> None:
        """Keep project-list scroll controls out of the way until content needs them."""
        try:
            if not self.team_projects_tree.winfo_ismapped():
                self.project_vertical_scrollbar.grid_remove()
                self.project_horizontal_scrollbar.grid_remove()
                return
            for scrollbar, view_method in (
                (self.project_vertical_scrollbar, self.team_projects_tree.yview),
                (self.project_horizontal_scrollbar, self.team_projects_tree.xview),
            ):
                first, last = view_method()
                if first > 0.001 or last < 0.999:
                    scrollbar.grid()
                else:
                    scrollbar.grid_remove()
        except tk.TclError as exc:
            LOGGER.debug("Project-list scrollbar sync skipped; error_type=%s", type(exc).__name__)

    @staticmethod
    def _configure_table_rows(tree: ttk.Treeview) -> None:
        """Add quiet zebra rows and semantic status text colors for quick scanning."""
        tree.tag_configure("row_alt", background=COLORS["surface_row_alt"])
        for tag, foreground in (
            ("status_pending", COLORS["warning_text"]),
            ("status_muted", COLORS["muted"]),
            ("status_info", COLORS["accent_text"]),
            ("status_running", COLORS["accent_text"]),
            ("status_success", COLORS["moss"]),
            ("status_error", COLORS["danger_text"]),
        ):
            tree.tag_configure(tag, foreground=foreground)

    @staticmethod
    def _table_row_tags(tree: ttk.Treeview, status: str | None = None) -> tuple[str, ...]:
        """Combine alternating rows with a readable color cue for recognized states."""
        tags = ["row_alt"] if len(tree.get_children()) % 2 else []
        status_tag = {
            "pending_approval": "status_pending",
            "expired": "status_muted",
            "approved": "status_info",
            "queued": "status_muted",
            "running": "status_running",
            "succeeded": "status_success",
            "failed": "status_error",
        }.get(status)
        if status_tag is not None:
            tags.append(status_tag)
        return tuple(tags)

    def _create_detail_text(self, parent: ttk.Frame) -> tk.Text:
        """Create a selectable, scrollable surface for labeled record metadata."""
        viewport = ttk.Frame(parent, style="Card.TFrame")
        viewport.pack(fill="both", expand=True)
        viewport.rowconfigure(0, weight=1)
        viewport.columnconfigure(0, weight=1)

        text = tk.Text(
            viewport,
            height=10,
            wrap="word",
            background=COLORS["surface"],
            foreground=COLORS["ink_soft"],
            font=FONTS["ui"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            selectbackground=COLORS["sidebar_active"],
            selectforeground=COLORS["white"],
            state="disabled",
        )
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=text.yview)

        def update_scrollbar(first: str, last: str) -> None:
            scrollbar.set(first, last)
            if float(first) > 0.0 or float(last) < 1.0:
                if not scrollbar.winfo_manager():
                    scrollbar.grid(row=0, column=1, sticky="ns", padx=(5, 0))
            elif scrollbar.winfo_manager():
                scrollbar.grid_remove()

        text.configure(yscrollcommand=update_scrollbar)
        text.grid(row=0, column=0, sticky="nsew")
        text.tag_configure(
            "field_label",
            foreground=COLORS["muted"],
            font=FONTS["overline"],
            spacing1=8,
            spacing3=2,
        )
        text.tag_configure("field_value", foreground=COLORS["ink_soft"], font=FONTS["ui"], spacing3=8)
        text.tag_configure("field_value_mono", foreground=COLORS["accent_text"], font=FONTS["mono"], spacing3=8)
        text.tag_configure("field_value_status", foreground=COLORS["accent_text"], font=FONTS["ui_bold"], spacing3=8)
        text.tag_configure("field_value_warning", foreground=COLORS["warning_text"], font=FONTS["ui"], spacing3=8)
        text.tag_configure("field_value_error", foreground=COLORS["danger_text"], font=FONTS["ui"], spacing3=8)
        text.tag_configure("field_value_success", foreground=COLORS["moss"], font=FONTS["ui"], spacing3=8)
        return text

    @staticmethod
    def _set_detail_fields(text: tk.Text, fields: list[tuple[str, str, str]]) -> None:
        """Render metadata as separate, consistently tagged label/value groups."""
        text.configure(state="normal")
        text.delete("1.0", "end")
        for label, value, value_style in fields:
            text.insert("end", f"{label}\n", "field_label")
            text.insert("end", f"{value}\n", value_style)
        text.configure(state="disabled")
        text.yview_moveto(0.0)

    @staticmethod
    def _create_table_empty_state(
        parent: ttk.Frame,
        title: str,
        description: str,
        *,
        symbol: str,
    ) -> tuple[ttk.Frame, ttk.Frame, tk.Canvas, ttk.Label, ttk.Label]:
        """Build a quiet, page-specific mark and explanation for a blank table."""
        frame = ttk.Frame(parent, style="TableEmpty.TFrame")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        content = ttk.Frame(frame, style="TableEmpty.TFrame")
        # Center the complete icon, copy, and action as one composition in tall viewports.
        content.grid(row=0, column=0)
        symbol_canvas = tk.Canvas(
            content,
            width=48,
            height=48,
            background=COLORS["surface_alt"],
            highlightthickness=0,
            takefocus=False,
        )
        MainWindow._draw_table_empty_symbol(symbol_canvas, symbol)
        symbol_canvas.scale("all", 0, 0, 1.3, 1.3)
        symbol_canvas.pack(anchor="center", pady=(0, 9))
        title_label = ttk.Label(content, text=title, style="TableEmptyTitle.TLabel")
        title_label.pack(anchor="center")
        description_label = ttk.Label(
            content,
            text=description,
            style="TableEmptyBody.TLabel",
            wraplength=400,
            justify="center",
        )
        description_label.pack(anchor="center", pady=(5, 0))

        def update_description_wraplength(event: tk.Event) -> None:
            # Keep the explanatory line roomy on wide panes without overflowing narrow ones.
            width = max(180, min(400, int(event.width) - 48))
            if int(description_label.cget("wraplength") or 0) != width:
                description_label.configure(wraplength=width)

        parent.bind("<Configure>", update_description_wraplength, add="+")
        # Use the table's existing grid so the empty state reliably fills its viewport.
        # A placed child can stay visually absent when the parent is re-mapped in Tk.
        frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
        return frame, content, symbol_canvas, title_label, description_label

    @staticmethod
    def _draw_table_empty_symbol(canvas: tk.Canvas, kind: str) -> None:
        """Draw small record-oriented marks; never use fake content to fill a queue."""
        if kind not in {"projects", "proposals", "runs"}:
            raise ValueError(f"Unsupported empty-state symbol: {kind}")

        tags = ("empty-state-symbol", f"empty-state:{kind}")
        line = COLORS["line"]
        accent = COLORS["accent_text"]
        canvas.create_oval(
            2,
            2,
            34,
            34,
            fill=COLORS["surface_alt"],
            outline=line,
            width=1,
            tags=tags,
        )
        if kind == "projects":
            # Four modules echo the project's grid mark and suggest a project catalogue.
            for x, y, color in (
                (10, 10, accent),
                (20, 10, line),
                (10, 20, line),
                (20, 20, accent),
            ):
                canvas.create_rectangle(x, y, x + 6, y + 6, outline=color, width=1.4, tags=tags)
        elif kind == "proposals":
            # A document outline with ruled lines signals a review record, not an AI spark.
            canvas.create_line(12, 8, 22, 8, 28, 14, 28, 28, 12, 28, 12, 8, fill=line, width=1.4, tags=tags)
            canvas.create_line(22, 8, 22, 14, 28, 14, fill=accent, width=1.4, tags=tags)
            canvas.create_line(16, 19, 24, 19, fill=accent, width=1.4, tags=tags)
            canvas.create_line(16, 23, 24, 23, fill=line, width=1.4, tags=tags)
        else:
            # A quiet timeline motif makes the run-history list recognizable while empty.
            canvas.create_line(11, 9, 11, 27, fill=line, width=1.4, tags=tags)
            for y, end_x in ((11, 24), (18, 21), (25, 24)):
                canvas.create_oval(8, y - 3, 14, y + 3, outline=accent, width=1.4, tags=tags)
                canvas.create_line(17, y, end_x, y, fill=line, width=1.4, tags=tags)

    @staticmethod
    def _create_page_empty_state(
        parent: ttk.Frame,
        title: str,
        description: str,
        status: str | None,
        *,
        motif: str,
        empty_style: str = "PageEmpty.TFrame",
    ) -> ttk.Frame:
        """Center a quiet, illustrated empty state without inventing catalog data."""
        background = COLORS["paper"] if empty_style == "PageEmptyQuiet.TFrame" else COLORS["surface"]
        title_style = "PageEmptyQuietTitle.TLabel" if empty_style == "PageEmptyQuiet.TFrame" else "PageEmptyTitle.TLabel"
        body_style = "PageEmptyQuietBody.TLabel" if empty_style == "PageEmptyQuiet.TFrame" else "PageEmptyBody.TLabel"
        status_style = "PageEmptyQuietStatus.TLabel" if empty_style == "PageEmptyQuiet.TFrame" else "PageEmptyStatus.TLabel"
        state = ttk.Frame(parent, style=empty_style, padding=(12, 14))
        symbol = tk.Canvas(
            state,
            width=68,
            height=68,
            background=background,
            highlightthickness=0,
            takefocus=False,
        )
        symbol.pack(anchor="center", pady=(0, 14))
        line = COLORS["line"]
        accent = COLORS["accent_text"]
        soft = COLORS["surface_alt"]
        if motif == "template":
            symbol.create_rectangle(11, 15, 49, 53, fill=soft, outline=line, width=1.4)
            symbol.create_rectangle(18, 10, 56, 48, fill=COLORS["surface"], outline=line, width=1.4)
            symbol.create_line(25, 21, 49, 21, fill=accent, width=2)
            symbol.create_line(25, 28, 48, 28, fill=line, width=1.5)
            symbol.create_line(25, 35, 43, 35, fill=line, width=1.5)
            symbol.create_rectangle(25, 40, 35, 44, fill=soft, outline=accent, width=1)
        elif motif == "reproduction":
            symbol.create_rectangle(15, 8, 47, 56, fill=COLORS["surface"], outline=line, width=1.4)
            symbol.create_line(22, 20, 39, 20, fill=accent, width=2)
            symbol.create_line(22, 28, 40, 28, fill=line, width=1.5)
            symbol.create_line(22, 36, 34, 36, fill=line, width=1.5)
            symbol.create_oval(34, 34, 53, 53, fill=soft, outline=accent, width=1.5)
            symbol.create_line(48, 48, 57, 57, fill=accent, width=2)
        elif motif == "agent":
            symbol.create_rectangle(9, 12, 58, 46, fill=soft, outline=line, width=1.4)
            symbol.create_polygon(20, 45, 17, 57, 31, 46, fill=soft, outline=line)
            for x in (23, 33, 43):
                symbol.create_oval(x - 2, 27, x + 2, 31, fill=accent, outline=accent)
        else:
            raise ValueError(f"Unsupported page empty-state motif: {motif}")

        ttk.Label(state, text=title, style=title_style).pack(anchor="center")
        ttk.Label(
            state,
            text=description,
            style=body_style,
            wraplength=620,
            justify="center",
        ).pack(anchor="center", pady=(6, 10))
        if status:
            ttk.Label(state, text=status, style=status_style).pack(anchor="center")
        state.place(relx=0.5, rely=0.5, anchor="center")
        return state

    @staticmethod
    def _set_table_empty_state(
        state: tuple[ttk.Frame, ttk.Frame, tk.Canvas, ttk.Label, ttk.Label],
        title: str,
        description: str,
        *,
        visible: bool,
    ) -> None:
        """Show or hide a table's contextual no-data explanation."""
        frame, _content, _symbol_canvas, title_label, description_label = state
        title_label.configure(text=title)
        description_label.configure(text=description)
        if visible:
            frame.grid()
            # The tree view is a sibling child in the same table surface; keep
            # the explanatory empty state above visible rows after page remaps.
            frame.tkraise()
        else:
            frame.grid_remove()

    def show_overview(self) -> None:
        """Route older internal callers to the Workbench project tab."""
        self.show_workbench()

    def show_workbench(self) -> None:
        """Open the project's Workbench tab; paper reproduction stays beside it."""
        self.show_projects()

    def show_quality(self) -> None:
        selection = self.team_projects_tree.selection()
        project = self._project_cache.get(selection[0]) if selection else None
        context = (
            f"当前项目：{project.name}；本机 CSV 可独立预检，当前服务端质量报告仅适用于固定演示项目。"
            if project
            else "本机 CSV 预检可独立使用；服务器质量报告目前仅读取固定演示项目。"
        )
        self._show_page("quality", "数据质量", context, self.quality_page)

    def show_projects(self) -> None:
        has_projects = hasattr(self, "team_projects_tree") and bool(self.team_projects_tree.get_children())
        self._set_project_workspace_expanded(has_projects)
        if hasattr(self, "team_projects_tree") and not has_projects:
            title = "连接团队账号以查看项目" if not self._project_token else "当前账号暂无项目"
            body = (
                "连接后查看当前账号可访问的项目，并进入项目资源、成员和科研工作流。"
                if not self._project_token
                else "账号连接成功后没有返回可访问的项目。"
            )
            self._set_table_empty_state(self.project_table_empty_state, title, body, visible=True)
        self._show_page("projects", "项目", "项目、数据资源与各自的科研工作流。", self.projects_page)

    def show_team_connection(self) -> None:
        """Navigate to the existing token field without submitting credentials."""
        self.show_projects()
        if not self.team_access_strip.winfo_manager():
            self.team_access_strip.pack(fill="x", before=self.project_workspace, pady=(0, 8))
        self.root.after_idle(self.team_token_entry.focus_set)

    def show_proposals(self) -> None:
        self._show_page("proposals", "待审批提案", "在 Agent 对话关联的项目上下文中复核提案与审批权限。", self.proposals_page)
        self.load_run_proposals()

    def show_runs(self) -> None:
        """Keep legacy callers on the workbench; run history has no standalone page in V4."""
        LOGGER.info("Standalone run history route suppressed; runs belong to a workflow")
        self.show_workbench()

    def show_workflow_editor_preview(self) -> None:
        """Show the V4 editor layout without implying an executable workflow exists."""
        selection = self.team_projects_tree.selection()
        project = self._project_cache.get(selection[0]) if selection else None
        if project is None:
            LOGGER.warning("Workflow editor preview requested without a selected accessible project")
            return

        preview = tk.Toplevel(self.root)
        preview.title(f"{project.name} · 工作流编辑器预览")
        preview.geometry("1280x780")
        preview.minsize(1020, 640)
        preview.configure(background=COLORS["paper"])
        preview.after_idle(apply_windows_dark_titlebar, preview)

        toolbar = ttk.Frame(preview, style="Topbar.TFrame", padding=(14, 8))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="返回项目", style="Toolbar.TButton", command=preview.destroy).pack(side="left")
        title_block = ttk.Frame(toolbar, style="Topbar.TFrame")
        title_block.pack(side="left", padx=(14, 0))
        ttk.Label(title_block, text="工作流编辑器", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            title_block,
            text=f"项目 / {project.name} / 工作流 · 静态布局预览",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Label(toolbar, text="未保存 · 未接入工作流服务", style="Muted.TLabel").pack(side="left", padx=(18, 0))
        edit_tools = ttk.Frame(toolbar, style="Topbar.TFrame")
        edit_tools.pack(side="left", padx=(12, 0))
        ttk.Label(edit_tools, text="版本 —", style="Muted.TLabel").pack(side="left", padx=(0, 5))
        ttk.Button(edit_tools, text="撤销", style="Toolbar.TButton", state="disabled").pack(side="left", padx=(0, 4))
        ttk.Button(edit_tools, text="重做", style="Toolbar.TButton", state="disabled").pack(side="left")
        ttk.Button(toolbar, text="保存", style="Toolbar.TButton", state="disabled").pack(side="right", padx=(8, 0))
        ttk.Button(toolbar, text="运行", style="Primary.TButton", state="disabled").pack(side="right")
        ttk.Button(toolbar, text="校验", style="Toolbar.TButton", state="disabled").pack(side="right", padx=(0, 8))
        ttk.Button(toolbar, text="运行配置", style="Toolbar.TButton", state="disabled").pack(side="right", padx=(0, 8))
        ttk.Separator(preview, orient="horizontal").pack(fill="x")

        body = ttk.Frame(preview, style="App.TFrame", padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, minsize=208, weight=0)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, minsize=250, weight=0)
        body.rowconfigure(0, weight=1)

        component_panel = ttk.Frame(body, style="Pane.TFrame", padding=(12, 12))
        component_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(component_panel, text="组件目录", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            component_panel,
            text="组件服务未连接，暂时无法列出可用组件。",
            style="Muted.TLabel",
            wraplength=180,
            justify="left",
        ).pack(anchor="w", pady=(5, 12))
        component_search = ttk.Entry(component_panel)
        component_search.pack(fill="x", pady=(0, 8))
        component_search.insert(0, "连接后搜索组件")
        component_search.state(["disabled"])
        ttk.Label(component_panel, text="分类", style="Eyebrow.TLabel").pack(anchor="w", pady=(3, 6))
        for category in (
            "数据输入",
            "数据处理",
            "文献与证据",
            "统计分析",
            "模型训练",
            "模型推理",
            "评价与比较",
            "控制与调度",
            "Agent",
            "可视化",
            "导出与报告",
        ):
            ttk.Label(component_panel, text=category, style="Muted.TLabel", padding=(5, 3)).pack(anchor="w")
        ttk.Label(
            component_panel,
            text="分类来自 V4.0 组件规范；当前未载入组件条目。",
            style="Muted.TLabel",
            wraplength=180,
            justify="left",
        ).pack(anchor="w", pady=(12, 0))

        canvas_host = ttk.Frame(body, style="Pane.TFrame", padding=6)
        canvas_host.grid(row=0, column=1, sticky="nsew", padx=4)
        canvas_host.rowconfigure(1, weight=1)
        canvas_host.columnconfigure(0, weight=1)
        canvas_tools = ttk.Frame(canvas_host, style="Pane.TFrame")
        canvas_tools.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 5))
        ttk.Button(canvas_tools, text="−", width=3, style="Toolbar.TButton", state="disabled").pack(side="left")
        ttk.Label(canvas_tools, text="100%", style="Muted.TLabel").pack(side="left", padx=7)
        ttk.Button(canvas_tools, text="+", width=3, style="Toolbar.TButton", state="disabled").pack(side="left")
        ttk.Button(canvas_tools, text="适配画布", style="Toolbar.TButton", state="disabled").pack(side="right")
        ttk.Button(canvas_tools, text="自动布局", style="Toolbar.TButton", state="disabled").pack(side="right", padx=(0, 6))
        canvas = tk.Canvas(
            canvas_host,
            background=COLORS["paper"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
            borderwidth=0,
            takefocus=False,
        )
        canvas.grid(row=1, column=0, sticky="nsew")
        canvas_items: dict[str, tuple[str, str]] = {}

        inspector = ttk.Frame(body, style="Pane.TFrame", padding=(12, 12))
        inspector.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        ttk.Label(inspector, text="属性面板", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            inspector,
            text="选择或添加节点后，在这里查看参数、输入输出、校验与运行信息。",
            style="Muted.TLabel",
            wraplength=220,
            justify="left",
        ).pack(anchor="w", pady=(5, 12))
        ttk.Separator(inspector, orient="horizontal").pack(fill="x", pady=(0, 10))
        ttk.Label(inspector, text="尚未选择节点", style="Body.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Label(
            inspector,
            text="当前项目没有已载入的工作流节点。",
            style="Muted.TLabel",
            wraplength=220,
            justify="left",
        ).pack(anchor="w")
        ttk.Label(
            inspector,
            text="参数会随当前工作流版本保存；运行状态只在真实任务产生后显示。",
            style="Muted.TLabel",
            wraplength=220,
            justify="left",
        ).pack(anchor="w", pady=(18, 0))

        def draw_canvas(event: tk.Event | None = None) -> None:
            width = max(1, event.width if event else canvas.winfo_width())
            height = max(1, event.height if event else canvas.winfo_height())
            canvas.delete("all")
            for x in range(18, width, 24):
                for y in range(18, height, 24):
                    canvas.create_oval(x, y, x + 1, y + 1, fill=COLORS["line"], outline="")
            center_x = width // 2
            center_y = max(140, height // 2 - 34)
            icon_size = 42
            canvas.create_rectangle(
                center_x - icon_size // 2,
                center_y - icon_size // 2,
                center_x + icon_size // 2,
                center_y + icon_size // 2,
                fill=COLORS["surface"],
                outline=COLORS["line"],
                width=1,
            )
            canvas.create_line(center_x - 9, center_y, center_x + 9, center_y, fill=COLORS["accent"], width=2)
            canvas.create_line(center_x, center_y - 9, center_x, center_y + 9, fill=COLORS["accent"], width=2)
            canvas.create_text(
                center_x,
                center_y + 45,
                text="当前工作流画布为空",
                fill=COLORS["ink"],
                font=FONTS["ui_bold"],
            )
            canvas.create_text(
                center_x,
                center_y + 70,
                text="连接组件目录后添加节点，或从模板市场选择已有流程。",
                fill=COLORS["muted"],
                font=FONTS["ui_small"],
                width=max(240, width - 64),
            )

        canvas.bind("<Configure>", draw_canvas, add="+")

        run_panel = ttk.Frame(preview, style="Pane.TFrame", padding=(14, 10))
        run_panel.pack(fill="x", padx=10, pady=(0, 10))
        run_header = ttk.Frame(run_panel, style="Pane.TFrame")
        run_header.pack(fill="x")
        ttk.Label(run_header, text="工作流运行面板", style="CardTitle.TLabel").pack(side="left")
        for section in ("校验", "运行历史", "日志", "产物"):
            ttk.Button(run_header, text=section, style="Toolbar.TButton", state="disabled").pack(
                side="left", padx=(10, 0)
            )
        ttk.Label(run_header, text="工作流服务未接入", style="Muted.TLabel").pack(side="right")
        ttk.Label(
            run_panel,
            text="运行历史、日志和产物应归属于具体工作流；当前没有工作流版本可供载入。",
            style="Muted.TLabel",
            wraplength=1000,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))
        ttk.Button(run_panel, text="校验", style="Toolbar.TButton", state="disabled").pack(side="right", pady=(5, 0))

    def show_reproductions(self) -> None:
        self._show_page(
            "reproductions",
            "论文复现",
            "独立创建复现任务，核验论文主张或实验结果；关联项目为可选项。",
            self.reproductions_page,
        )

    def show_templates(self) -> None:
        self._show_page(
            "templates",
            "模板市场",
            "浏览内置科研工作流模板，并按固定版本实例化到项目或论文复现任务。",
            self.templates_page,
        )

    def show_agent(self) -> None:
        self._show_page(
            "agent",
            "Agent 对话",
            "显式引用项目、论文复现任务或工作流，查看对话、提案与工具记录。",
            self.agent_page,
        )

    def show_profile_settings(self) -> None:
        self._show_page(
            "settings",
            "个人信息与设置",
            "管理个人资料、界面偏好、通知、账号安全与本地服务配置。",
            self.profile_settings_page,
        )

    def show_repository_notice(self) -> None:
        """Explain the reserved repository icon without opening an empty page."""
        messagebox.showinfo("仓库", "仓库入口已预留；当前桌面版本尚未接入仓库服务。", parent=self.root)

    def show_research_support_notice(self) -> None:
        """Describe the planned research-compute scope without implying availability."""
        messagebox.showinfo(
            "科研支持",
            "科研支持面向云显卡或大模型算力服务。当前桌面版本尚未接入算力服务。",
            parent=self.root,
        )

    def open_recent_run(self) -> None:
        """Keep the recent-run summary in the workbench; do not open a run center."""
        if not self._project_token or not self._recent_run_id:
            return
        LOGGER.info(
            "Recent run cannot deep-link without workflow identity; run_id=%s",
            self._recent_run_id,
        )
        self.show_workbench()

    def connect_team_projects(self) -> None:
        """Use a caller-entered token only for authenticated read-only requests."""
        if self._project_loading:
            return
        token = self.team_token_entry.get().strip()
        if not token:
            self.team_projects_status.configure(text="请输入团队访问令牌。")
            return

        self._project_token = token
        self.team_connection_button.configure(text="管理团队账号")
        self._project_loading = True
        self._clear_run_rows()
        self._set_table_empty_state(
            self.runs_table_empty_state,
            "正在读取项目…",
            "运行记录将在团队账号确认后载入。",
            visible=False,
        )
        self._set_recent_run_summary("正在读取当前账号的最近运行…")
        self.team_projects_status.configure(text="正在读取当前账号可访问的项目…")
        self.connect_team_projects_button.state(["disabled"])
        self.clear_team_token_button.state(["disabled"])
        self._clear_project_rows()
        self._set_table_empty_state(
            self.project_table_empty_state,
            "正在读取项目…",
            "正在核对当前账号可访问的项目。",
            visible=False,
        )
        self._clear_proposal_rows()
        threading.Thread(
            target=self._request_team_projects,
            args=(token,),
            name="desktop-team-project-list",
            daemon=True,
        ).start()
        self.root.after(50, self._poll_team_project_result)

    def clear_team_project_access(self) -> None:
        """Forget the in-memory token and remove all team project details."""
        if self._project_loading:
            return
        self._project_token = None
        self.team_connection_button.configure(text="连接团队账号")
        self._server_quality_request_id += 1
        self._server_quality_loading = False
        self.server_quality_check_button.state(["!disabled"])
        self.server_quality_status.configure(text="尚未读取服务器质量报告")
        self.server_quality_summary.configure(text="")
        self.server_quality_issues.configure(text="")
        self.server_quality_guidance.configure(text="请先在工作台连接账号以读取固定演示项目报告。")
        self.team_token_entry.delete(0, "end")
        self._project_detail_request_id += 1
        self._project_detail_loading = False
        self._clear_project_rows()
        self._clear_proposal_rows()
        self._clear_run_rows()
        self._set_recent_run_summary("访问令牌已清除。")
        self.team_projects_status.configure(text="访问令牌已清除。")
        self.proposals_status.configure(text="访问令牌已清除。")

    def request_server_quality_report(self) -> None:
        """Read the registered synthetic dataset report without blocking Tk events."""
        if self._server_quality_loading:
            return
        if not self._project_token:
            self.server_quality_status.configure(text="尚未连接团队账号")
            self.server_quality_guidance.configure(text="请先在工作台连接账号。")
            return

        self._server_quality_request_id += 1
        request_id = self._server_quality_request_id
        token = self._project_token
        self._server_quality_loading = True
        self.server_quality_status.configure(text="正在读取服务器登记版本…")
        self.server_quality_summary.configure(text="")
        self.server_quality_issues.configure(text="")
        self.server_quality_guidance.configure(text="正在核对报告状态。")
        self.server_quality_check_button.state(["disabled"])
        threading.Thread(
            target=self._request_server_quality_report,
            args=(request_id, token),
            name="desktop-server-quality-report",
            daemon=True,
        ).start()
        self._server_quality_poll_after_id = self.root.after(50, self._poll_server_quality_result)

    def _request_server_quality_report(self, request_id: int, token: str) -> None:
        try:
            report = self.client.get_demo_quality_report(token)
        except DesktopApiError as exc:
            LOGGER.warning("Server quality report failed; route=%s error_type=%s", "/api/v1/projects/demo/{project_key}/datasets/{version}/quality-report", type(exc).__name__)
            self._server_quality_result_queue.put((request_id, "error", str(exc)))
        except Exception as exc:
            LOGGER.error("Unexpected server quality report failure; error_type=%s", type(exc).__name__)
            self._server_quality_result_queue.put((request_id, "error", "暂时无法读取服务器质量报告，请检查连接和账号权限后重试。"))
        else:
            self._server_quality_result_queue.put((request_id, "success", report))

    def _poll_server_quality_result(self) -> None:
        try:
            request_id, outcome, value = self._server_quality_result_queue.get_nowait()
        except queue.Empty:
            if self._server_quality_loading and self.root.winfo_exists():
                self._server_quality_poll_after_id = self.root.after(50, self._poll_server_quality_result)
            return

        self._schedule_page_viewport_refresh()
        if request_id != self._server_quality_request_id:
            return
        self._server_quality_loading = False
        self._server_quality_poll_after_id = None
        self.server_quality_check_button.state(["!disabled"])
        if outcome == "success" and isinstance(value, DatasetQualityReport):
            status_labels = {
                "blocker": "服务器检查：阻断",
                "warning": "服务器检查：警告",
                "success": "服务器检查：通过（合成演示）",
            }
            self.server_quality_status.configure(text=status_labels[value.status])
            split_summary = " / ".join(f"{split} {count}" for split, count in value.split_counts) or "无"
            self.server_quality_summary.configure(
                text=(
                    f"数据版本：{value.dataset_version}；记录数：{value.row_count}；拆分：{split_summary}；"
                    f"类别数：{value.label_category_count}；规则：{value.rule_set_version}；"
                    f"SHA-256：{value.manifest_sha256}"
                )
            )
            issue_lines = []
            for issue in value.issues:
                severity = "警告" if issue.severity == "warning" else "阻断"
                line_text = f"；行号：{', '.join(map(str, issue.line_numbers))}" if issue.line_numbers else ""
                issue_lines.append(f"【{severity}】{issue.message}影响 {issue.count} 项{line_text}。")
            self.server_quality_issues.configure(text="\n".join(issue_lines) or "未发现通用结构问题。")
            guidance_lines = [f"建议：{issue.guidance}" for issue in value.issues]
            guidance_lines.append("结果仅针对登记的合成样例；synthetic_only=true、research_ready=false，不代表科研就绪或医学适用。")
            self.server_quality_guidance.configure(text="\n".join(guidance_lines))
            return

        self.server_quality_status.configure(text="服务器报告暂不可用")
        self.server_quality_summary.configure(text=str(value))
        self.server_quality_issues.configure(text="")
        self.server_quality_guidance.configure(text="检查未完成不会形成审批结果；确认账号和服务状态后重试。")

    def _clear_project_rows(self) -> None:
        self._project_cache.clear()
        self.team_projects_tree.configure(show="")
        self._set_project_table_rows_visible(False)
        if hasattr(self, "project_context_area"):
            self.project_context_area.pack_forget()
        for item_id in self.team_projects_tree.get_children():
            self.team_projects_tree.delete(item_id)
        if hasattr(self, "workflow_project_context"):
            self.workflow_project_context.configure(text="尚未选择项目")
            self.workflow_preview_button.state(["disabled"])
        self.quality_dataset_versions.configure(text="请先在工作台选择项目。")
        self.project_detail_title.configure(text="选择一个项目查看只读详情")
        self._set_detail_fields(
            self.project_detail_summary,
            [("项目详情", "选择一个项目查看领域、角色与登记数据版本。", "field_value")],
        )
        if hasattr(self, "_template_contract_cache"):
            self._template_contract_cache.clear()
            self._template_error_cache.clear()
        if hasattr(self, "approve_proposal_button"):
            self.approve_proposal_button.state(["disabled"])
        if hasattr(self, "view_template_button"):
            self.view_template_button.state(["disabled"])
        if hasattr(self, "project_table_empty_state"):
            self._set_project_workspace_expanded(False)
            title = "连接团队账号以查看项目" if not self._project_token else "当前账号暂无项目"
            body = (
                "连接后查看当前账号可访问的项目，并进入项目资源、成员和科研工作流。"
                if not self._project_token
                else "账号连接成功后没有返回可访问的项目。"
            )
            self._set_table_empty_state(self.project_table_empty_state, title, body, visible=True)

    def _clear_proposal_rows(self) -> None:
        """Discard cached proposal data and invalidate any in-flight response."""
        # Keep invalidation and queue draining atomic with worker result delivery.
        with self._proposal_result_lock:
            self._proposal_request_id += 1
            self._proposal_request_state.request_id = self._proposal_request_id
            while True:
                try:
                    self._proposal_result_queue.get_nowait()
                except queue.Empty:
                    break
        self._proposal_loading = False
        self._proposal_cache.clear()
        self._template_contract_cache.clear()
        self._template_error_cache.clear()
        self.refresh_proposals_button.state(["!disabled"])
        self.approve_proposal_button.state(["disabled"])
        self.view_template_button.state(["disabled"])
        for item_id in self.proposals_tree.get_children():
            self.proposals_tree.delete(item_id)
        self.proposal_detail_title.configure(text="选择一条提案查看只读详情")
        self._set_detail_fields(
            self.proposal_detail_summary,
            [("审核说明", "提案需由项目操作者核对并批准；查看者只能读取。", "field_value")],
        )
        if hasattr(self, "proposal_table_empty_state"):
            title = "连接团队账号以读取提案" if not self._project_token else "当前账号暂无提案"
            body = "此处显示当前账号可见的 AgentArts 提案及其审核状态。" if not self._project_token else "当前账号暂时没有可显示的提案。"
            self._set_table_empty_state(self.proposal_table_empty_state, title, body, visible=True)

    def load_run_proposals(self) -> None:
        """Refresh membership-scoped proposals using the in-memory team token."""
        if self._proposal_loading:
            return
        if not self._project_token:
            self._clear_proposal_rows()
            self.proposals_status.configure(text="请先在工作台连接账号。")
            return

        with self._proposal_result_lock:
            self._proposal_request_id += 1
            request_id = self._proposal_request_id
            self._proposal_request_state.request_id = request_id
        self._proposal_loading = True
        self.proposals_status.configure(text="正在读取当前账号可见的提案…")
        self.refresh_proposals_button.state(["disabled"])
        for item_id in self.proposals_tree.get_children():
            self.proposals_tree.delete(item_id)
        self._proposal_cache.clear()
        self._template_contract_cache.clear()
        self._template_error_cache.clear()
        self.approve_proposal_button.state(["disabled"])
        self.view_template_button.state(["disabled"])
        self._set_table_empty_state(
            self.proposal_table_empty_state, "正在读取提案…", "正在读取当前账号可见的审核请求。", visible=False
        )
        threading.Thread(
            target=MainWindow._request_run_proposals,
            args=(self.client, self._proposal_request_state, request_id, self._project_token),
            name="desktop-run-proposal-list",
            daemon=True,
        ).start()
        self.root.after(50, self._poll_run_proposals)

    @staticmethod
    def _enqueue_proposal_result(state: _ProposalRequestState, request_id: int, outcome: str, value: object) -> None:
        """Queue a response only while its account-scoped request is still current."""
        with state.lock:
            if request_id != state.request_id:
                LOGGER.debug(
                    "Discarded stale run proposal response; route=%s request_id=%s current_request_id=%s",
                    "/api/v1/run-proposals",
                    request_id,
                    state.request_id,
                )
                return
            state.result_queue.put((request_id, outcome, value))

    @staticmethod
    def _request_run_proposals(client: Any, state: _ProposalRequestState, request_id: int, token: str) -> None:
        try:
            proposals = client.list_run_proposals(token)
        except DesktopApiError as exc:
            LOGGER.warning(
                "Run proposal request failed; route=%s error_type=%s",
                "/api/v1/run-proposals",
                type(exc).__name__,
            )
            MainWindow._enqueue_proposal_result(state, request_id, "error", str(exc))
        except Exception as exc:
            # Avoid exception text because a client error can contain request details.
            LOGGER.error(
                "Unexpected run proposal request failure; route=%s error_type=%s",
                "/api/v1/run-proposals",
                type(exc).__name__,
            )
            MainWindow._enqueue_proposal_result(
                state,
                request_id,
                "error",
                "暂时无法读取智能体提案，请检查服务地址和访问令牌后重试。",
            )
        else:
            template_results: dict[tuple[str, str], PipelineTemplateContract | str] = {}
            template_keys = {
                (proposal.project_id, proposal.pipeline_template)
                for proposal in proposals
                if isinstance(proposal, RunProposal)
            }
            for project_id, template_id in template_keys:
                try:
                    contract = client.get_project_template(project_id, template_id, token)
                    if (
                        not isinstance(contract, PipelineTemplateContract)
                        or contract.template_id != template_id
                    ):
                        raise DesktopApiError("模板说明服务返回的数据格式不正确。")
                    template_results[(project_id, template_id)] = contract
                except DesktopApiError as exc:
                    LOGGER.warning(
                        "Template contract request failed; route=%s error_type=%s",
                        "/api/v1/projects/{project_id}/templates/{template_id}",
                        type(exc).__name__,
                    )
                    template_results[(project_id, template_id)] = str(exc)
                except Exception as exc:
                    LOGGER.error(
                        "Unexpected template contract request failure; route=%s error_type=%s",
                        "/api/v1/projects/{project_id}/templates/{template_id}",
                        type(exc).__name__,
                    )
                    template_results[(project_id, template_id)] = (
                        "暂时无法读取模板说明，请检查服务地址和访问令牌后重试。"
                    )
            MainWindow._enqueue_proposal_result(
                state,
                request_id, "success", (proposals, template_results)
            )

    def _poll_run_proposals(self) -> None:
        try:
            request_id, outcome, value = self._proposal_result_queue.get_nowait()
        except queue.Empty:
            if self._proposal_loading:
                self.root.after(50, self._poll_run_proposals)
            return

        self._schedule_page_viewport_refresh()
        if request_id != self._proposal_request_id:
            if self._proposal_loading:
                self.root.after(50, self._poll_run_proposals)
            return

        self._proposal_loading = False
        self.refresh_proposals_button.state(["!disabled"])
        if (
            outcome == "success"
            and isinstance(value, tuple)
            and len(value) == 2
            and isinstance(value[0], list)
            and isinstance(value[1], dict)
        ):
            proposals, template_results = value
            for key, result in template_results.items():
                if not isinstance(key, tuple) or len(key) != 2:
                    continue
                if isinstance(result, PipelineTemplateContract):
                    self._template_contract_cache[key] = result
                elif isinstance(result, str):
                    self._template_error_cache[key] = result

            for proposal in proposals:
                if not isinstance(proposal, RunProposal):
                    LOGGER.warning(
                        "Run proposal response rejected; route=%s error_type=InvalidProposal",
                        "/api/v1/run-proposals",
                    )
                    self._clear_proposal_rows()
                    self.proposals_status.configure(text="团队提案服务返回的数据格式不正确。")
                    self._set_table_empty_state(
                        self.proposal_table_empty_state,
                        "提案数据格式异常",
                        "请刷新提案列表，或联系项目管理员检查服务返回。",
                        visible=True,
                    )
                    return
                self._proposal_cache[proposal.proposal_id] = proposal
                status_label = {
                    "pending_approval": "待审批",
                    "expired": "已过期",
                    "approved": "已批准",
                }.get(proposal.status, "未知")
                self.proposals_tree.insert(
                    "",
                    "end",
                    iid=proposal.proposal_id,
                    tags=self._table_row_tags(self.proposals_tree, proposal.status),
                    values=(
                        status_label,
                        proposal.pipeline_template,
                        proposal.dataset_version,
                        proposal.expires_at.replace("T", " ")[:16],
                    ),
                )
            self._set_table_empty_state(
                self.proposal_table_empty_state,
                "暂无可见提案",
                "当前账号暂时没有可显示的 AgentArts 提案。",
                visible=not bool(proposals),
            )
            if proposals and self._template_error_cache:
                self.proposals_status.configure(
                    text=f"已读取 {len(proposals)} 条提案 · 部分模板说明不可用，相关提案无法批准。"
                )
            elif proposals:
                self.proposals_status.configure(text=f"已读取 {len(proposals)} 条提案 · 当前页面只读")
            else:
                self.proposals_status.configure(text="当前账号暂无可见提案。")
            return

        self._clear_proposal_rows()
        self.proposals_status.configure(text=str(value))
        self._set_table_empty_state(
            self.proposal_table_empty_state,
            "暂时无法读取提案",
            "请检查服务连接和团队账号权限后重试。",
            visible=True,
        )

    def _on_proposal_selected(self, _event: object = None) -> None:
        selection = self.proposals_tree.selection()
        if not selection:
            return
        proposal = self._proposal_cache.get(selection[0])
        if proposal is None:
            return
        status_label = "待审批" if proposal.status == "pending_approval" else "已过期"
        if proposal.status == "approved":
            status_label = "已批准"
        self.proposal_detail_title.configure(
            text=f"{proposal.pipeline_template} · {status_label}"
        )
        template_key = (proposal.project_id, proposal.pipeline_template)
        contract = self._template_contract_cache.get(template_key)
        contract_matches = (
            contract is not None
            and contract.template_id == proposal.pipeline_template
            and contract.dataset_version == proposal.dataset_version
        )
        if contract_matches:
            template_value = f"版本：{contract.version}\n清单 SHA-256：{contract.manifest_sha256}"
            template_style = "field_value_mono"
        elif template_key in self._template_error_cache:
            template_value = f"说明不可用：{self._template_error_cache[template_key]}；批准已禁用。"
            template_style = "field_value_warning"
        elif contract is not None:
            template_value = "模板说明与提案数据版本不匹配；批准已禁用。"
            template_style = "field_value_warning"
        else:
            template_value = "正在读取对应模板说明；读取完成前不能批准。"
            template_style = "field_value_warning"

        detail_fields = [
            (
                "审批状态",
                status_label,
                "field_value_status" if proposal.status in ("pending_approval", "approved") else "field_value_warning",
            ),
            ("数据版本", proposal.dataset_version, "field_value_mono"),
            ("参数", f"sample_limit={proposal.parameters['sample_limit']}", "field_value_mono"),
            ("配置摘要 SHA-256", proposal.config_sha256, "field_value_mono"),
            ("关联 Trace ID", proposal.trace_id, "field_value_mono"),
            ("创建时间", proposal.created_at, "field_value"),
            ("有效期至", proposal.expires_at, "field_value"),
        ]
        if proposal.status == "approved":
            detail_fields.extend((
                ("批准人", proposal.approved_by or "未记录", "field_value"),
                ("批准时间", proposal.approved_at or "未记录", "field_value"),
                ("运行记录", proposal.run_id or "尚未关联运行", "field_value_mono"),
            ))
        else:
            detail_fields.append(("审批说明", "审批前会再次校验有效期与配置摘要；任务只使用固定合成样例。", "field_value"))
        detail_fields.append(("模板契约", template_value, template_style))
        self._set_detail_fields(self.proposal_detail_summary, detail_fields)
        role = self._project_cache.get(proposal.project_id)
        can_view_contract = contract_matches
        self.view_template_button.state(["!disabled"] if can_view_contract else ["disabled"])
        can_approve = (
            proposal.status == "pending_approval"
            and role is not None
            and role.role == "operator"
            and contract_matches
            and not self._approval_loading
        )
        self.approve_proposal_button.state(["!disabled"] if can_approve else ["disabled"])

    def show_selected_template_contract(self) -> None:
        """Show the current server contract in a read-only native dialog."""
        selection = self.proposals_tree.selection()
        proposal = self._proposal_cache.get(selection[0]) if selection else None
        if proposal is None:
            return
        key = (proposal.project_id, proposal.pipeline_template)
        contract = self._template_contract_cache.get(key)
        if (
            contract is None
            or contract.template_id != proposal.pipeline_template
            or contract.dataset_version != proposal.dataset_version
        ):
            self.proposals_status.configure(text="当前提案对应的模板说明尚未成功读取。")
            return

        existing = getattr(self, "template_contract_dialog", None)
        if existing is not None and existing.dialog.winfo_exists():
            existing.close()
        self.template_contract_dialog = TemplateContractDialog(self.root, contract)

    def approve_selected_proposal(self) -> None:
        """Ask for explicit confirmation before sending the fixed approval request."""
        selection = self.proposals_tree.selection()
        proposal = self._proposal_cache.get(selection[0]) if selection else None
        if proposal is None or not self._project_token:
            self.proposals_status.configure(text="请先连接团队账号并选择一条待审批提案。")
            return
        project = self._project_cache.get(proposal.project_id)
        if project is None or project.role != "operator":
            self.proposals_status.configure(text="只有该项目操作者可以批准提案。")
            return
        if proposal.status != "pending_approval":
            self.proposals_status.configure(text="该提案已处理或过期，请刷新列表。")
            return
        contract = self._template_contract_cache.get(
            (proposal.project_id, proposal.pipeline_template)
        )
        if contract is None or contract.dataset_version != proposal.dataset_version:
            self.proposals_status.configure(text="模板说明尚未成功读取，暂时不能批准。")
            self.approve_proposal_button.state(["disabled"])
            return
        confirmed = messagebox.askyesno(
            "确认批准并运行",
            (
                "将批准并提交固定合成冒烟任务。\n"
                f"模板：{proposal.pipeline_template}\n"
                f"合成样例数：{proposal.parameters['sample_limit']}\n"
                "任务不会读取真实研究数据，也不产生医学或科研结论。"
            ),
            parent=self.root,
        )
        if not confirmed:
            return

        self._approval_loading = True
        self.approve_proposal_button.state(["disabled"])
        self.proposals_status.configure(text="正在批准并提交固定合成冒烟任务…")
        threading.Thread(
            target=self._request_proposal_approval,
            args=(proposal.proposal_id, self._project_token),
            name="desktop-proposal-approval",
            daemon=True,
        ).start()
        self._approval_poll_after_id = self.root.after(50, self._poll_proposal_approval)

    def _request_proposal_approval(self, proposal_id: str, token: str) -> None:
        try:
            run = self.client.approve_run_proposal(proposal_id, token)
        except DesktopApiError as exc:
            LOGGER.warning(
                "Proposal approval failed; route=/api/v1/run-proposals/{proposal_id}/approve error_type=%s",
                type(exc).__name__,
            )
            self._approval_result_queue.put(("error", str(exc)))
        except Exception as exc:
            LOGGER.error(
                "Unexpected proposal approval failure; route=/api/v1/run-proposals/{proposal_id}/approve error_type=%s",
                type(exc).__name__,
            )
            self._approval_result_queue.put(("error", "审批服务暂时不可用，请检查服务地址后重试。"))
        else:
            self._approval_result_queue.put(("success", run))

    def _poll_proposal_approval(self) -> None:
        self._approval_poll_after_id = None
        try:
            outcome, value = self._approval_result_queue.get_nowait()
        except queue.Empty:
            if self._approval_loading:
                self._approval_poll_after_id = self.root.after(50, self._poll_proposal_approval)
            return
        self._schedule_page_viewport_refresh()
        self._approval_loading = False
        if outcome == "success" and isinstance(value, Run):
            self._run_cache[value.run_id] = value
            self._recent_run_id = value.run_id
            self.recent_run_summary.configure(
                text=(
                    f"已创建运行 · {value.pipeline_template} · 状态：{value.status} · "
                    "当前记录尚未关联可打开的工作流版本。"
                )
            )
            self.proposals_status.configure(
                text=f"已批准并创建运行 · 状态：{value.status} · trace_id：{value.trace_id}"
            )
            self.show_runs()
            return
        self.proposals_status.configure(text=str(value))
        self.approve_proposal_button.state(["!disabled"])

    def _cancel_pending_callbacks_on_destroy(self, event: tk.Event) -> None:
        """Cancel pending timers before Tk removes their callback commands."""
        if event.widget is not self.root:
            return
        for attribute, operation in (
            ("_approval_poll_after_id", "approval"),
            ("_server_quality_poll_after_id", "server_quality"),
            ("_run_event_poll_after_id", "run_event"),
        ):
            after_id = getattr(self, attribute, None)
            if after_id is None:
                continue
            try:
                self.root.after_cancel(after_id)
            except tk.TclError as exc:
                LOGGER.debug("%s poll cleanup skipped; error_type=%s", operation, type(exc).__name__)
            finally:
                setattr(self, attribute, None)

        # The root owns this Tcl interpreter. Cancel untracked polls and idle layout work too,
        # so Tk cannot execute a callback command after its window has been destroyed.
        pending_ids = self.root.tk.splitlist(self.root.tk.call("after", "info"))
        for after_id in pending_ids:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError as exc:
                LOGGER.debug("Window callback cleanup skipped; callback_id=%s error_type=%s", after_id, type(exc).__name__)
        LOGGER.debug("Desktop window shutdown completed; pending_callbacks_canceled=%d", len(pending_ids))

    def _clear_run_rows(self) -> None:
        """Discard run details when the team token is removed or a request is replaced."""
        self._run_request_id += 1
        self._run_loading = False
        self._run_refresh_pending = False
        self._run_cache.clear()
        self._pending_run_id = None
        self._invalidate_run_events("连接团队账号后查看运行时间线。")
        if hasattr(self, "export_run_report_button"):
            self.export_run_report_button.state(["disabled"])
        if hasattr(self, "export_run_pdf_button"):
            self.export_run_pdf_button.state(["disabled"])
        if hasattr(self, "recent_run_summary"):
            message = "连接团队账号后查看最近运行。" if not self._project_token else "运行记录尚未刷新。"
            self._set_recent_run_summary(message)
        if not hasattr(self, "runs_tree"):
            return
        self.refresh_runs_button.state(["!disabled"])
        for item_id in self.runs_tree.get_children():
            self.runs_tree.delete(item_id)
        self.run_detail_title.configure(text="选择一条运行记录")
        self._set_detail_fields(
            self.run_detail_summary,
            [("运行记录", "仅展示固定合成冒烟任务状态，不提供取消或手动重试。", "field_value")],
        )
        if hasattr(self, "runs_table_empty_state"):
            title = "连接团队账号以查看运行" if not self._project_token else "暂无运行记录"
            body = "此处仅显示当前账号可见的合成任务状态和提交时间。"
            self._set_table_empty_state(self.runs_table_empty_state, title, body, visible=True)

    def _invalidate_run_events(self, message: str) -> None:
        """Invalidate in-flight event reads so stale rows cannot cross run or account changes."""
        self._run_event_request_id += 1
        self._selected_run_event_id = None
        self._selected_run_events = None
        self._run_event_loaded_id = None
        self._run_event_loading = False
        if self._run_event_poll_after_id is not None:
            try:
                self.root.after_cancel(self._run_event_poll_after_id)
            except tk.TclError as exc:
                LOGGER.debug("run_event poll cleanup skipped; error_type=%s", type(exc).__name__)
            self._run_event_poll_after_id = None
        while True:
            try:
                self._run_event_result_queue.get_nowait()
            except queue.Empty:
                break
        if hasattr(self, "run_event_timeline"):
            self._set_run_event_timeline(message)

    def load_runs(self) -> None:
        """Fetch membership-scoped synthetic run records off the Tk event thread."""
        if self._run_loading:
            # Coalesce refreshes so an older in-flight response cannot hide a newly approved run.
            self._run_refresh_pending = True
            return
        if not self._project_token:
            self._clear_run_rows()
            self.runs_status.configure(text="请先在工作台连接账号。")
            return
        self._run_refresh_pending = False
        self._invalidate_run_events("选择运行记录后读取其状态时间线。")
        self._run_request_id += 1
        request_id = self._run_request_id
        self._run_loading = True
        self.runs_status.configure(text="正在读取运行状态…")
        self._set_recent_run_summary("正在读取当前账号的最近运行…")
        self.export_run_report_button.state(["disabled"])
        self.refresh_runs_button.state(["disabled"])
        for item_id in self.runs_tree.get_children():
            self.runs_tree.delete(item_id)
        self._run_cache.clear()
        self._set_table_empty_state(
            self.runs_table_empty_state, "正在读取运行记录…", "正在载入当前账号可见的合成任务。", visible=False
        )
        threading.Thread(
            target=self._request_runs,
            args=(request_id, self._project_token),
            name="desktop-run-list",
            daemon=True,
        ).start()
        self.root.after(50, self._poll_runs)

    def _request_runs(self, request_id: int, token: str) -> None:
        try:
            runs = self.client.list_runs(token)
        except DesktopApiError as exc:
            LOGGER.warning("Run list request failed; route=/api/v1/runs error_type=%s", type(exc).__name__)
            self._run_result_queue.put((request_id, "error", str(exc)))
        except Exception as exc:
            LOGGER.error("Unexpected run list failure; route=/api/v1/runs error_type=%s", type(exc).__name__)
            self._run_result_queue.put((request_id, "error", "暂时无法读取运行记录，请检查服务地址后重试。"))
        else:
            self._run_result_queue.put((request_id, "success", runs))

    def _poll_runs(self) -> None:
        try:
            request_id, outcome, value = self._run_result_queue.get_nowait()
        except queue.Empty:
            if self._run_loading:
                self.root.after(50, self._poll_runs)
            return
        self._schedule_page_viewport_refresh()
        if request_id != self._run_request_id:
            if self._run_loading:
                self.root.after(50, self._poll_runs)
            return
        self._run_loading = False
        if self._run_refresh_pending:
            self._run_refresh_pending = False
            self.load_runs()
            return
        self.refresh_runs_button.state(["!disabled"])
        if outcome == "success" and isinstance(value, list):
            status_labels = {"queued": "排队中", "running": "运行中", "succeeded": "已完成", "failed": "失败"}
            for run in value:
                if not isinstance(run, Run):
                    self._clear_run_rows()
                    self.runs_status.configure(text="运行记录服务返回的数据格式不正确。")
                    self._set_recent_run_summary("运行记录格式异常，暂时无法显示最近运行。")
                    self._set_table_empty_state(
                        self.runs_table_empty_state,
                        "运行数据格式异常",
                        "请刷新运行记录，或联系项目管理员检查服务返回。",
                        visible=True,
                    )
                    return
                self._run_cache[run.run_id] = run
                self.runs_tree.insert(
                    "",
                    "end",
                    iid=run.run_id,
                    tags=self._table_row_tags(self.runs_tree, run.status),
                    values=(status_labels[run.status], run.pipeline_template, run.created_at.replace("T", " ")[:16]),
                )
            self._set_table_empty_state(
                self.runs_table_empty_state,
                "暂无运行记录",
                "当前账号暂时没有可显示的合成任务记录。",
                visible=not bool(value),
            )
            self.runs_status.configure(
                text=f"已读取 {len(value)} 条运行记录 · 结果仅为合成集成冒烟"
                if value else "当前账号暂无运行记录。"
            )
            if value:
                latest = value[0]
                status_label = status_labels[latest.status]
                created = latest.created_at.replace("T", " ")[:16]
                self._recent_run_id = latest.run_id
                self.recent_run_summary.configure(
                    text=(
                        f"{status_label} · {latest.pipeline_template} · {created} · "
                        "当前记录尚未关联可打开的工作流版本。"
                    )
                )
            else:
                self._set_recent_run_summary("当前账号暂无运行记录。")

            pending_run_id = self._pending_run_id
            self._pending_run_id = None
            if pending_run_id and pending_run_id in self._run_cache:
                self.runs_tree.selection_set(pending_run_id)
                self.runs_tree.see(pending_run_id)
                self._on_run_selected()
            return
        self.runs_status.configure(text=str(value))
        self._pending_run_id = None
        self._set_recent_run_summary("暂时无法读取最近运行，请检查服务连接后重试。")
        self._set_table_empty_state(
            self.runs_table_empty_state,
            "暂时无法读取运行记录",
            "请检查服务连接和团队账号权限后重试。",
            visible=True,
        )

    def _set_recent_run_summary(self, message: str) -> None:
        """Show a safe empty/error state in the workbench summary."""
        self._recent_run_id = None
        if not hasattr(self, "recent_run_summary"):
            return
        self.recent_run_summary.configure(text=message)

    def _on_run_selected(self, _event: object = None) -> None:
        selection = self.runs_tree.selection()
        if not selection:
            return
        run = self._run_cache.get(selection[0])
        if run is None:
            return
        self.load_run_events(run.run_id)
        if run.status in ("succeeded", "failed"):
            self.export_run_report_button.state(["!disabled"])
            self.export_run_pdf_button.state(["!disabled"])
        else:
            self.export_run_report_button.state(["disabled"])
            self.export_run_pdf_button.state(["disabled"])
        labels = {"queued": "排队中", "running": "运行中", "succeeded": "已完成", "failed": "失败"}
        self.run_detail_title.configure(text=f"{run.pipeline_template} · {labels[run.status]}")
        if run.result is not None:
            result_text = (
                f"结果仅为合成研究结果（不是正式研究结论） · "
                f"处理合成样例：{run.result['processed_count']} 条 · "
                "synthetic_only=true · research_ready=false"
            )
        elif run.error_code:
            result_text = f"安全错误码：{run.error_code}。请查看服务端脱敏日志；此任务不支持手动重试。"
        else:
            result_text = "任务等待 Worker 更新状态；点击刷新查看最新进度。"
        quality_text = (
            f"质量检查：{run.quality_status} · 规则：{run.quality_rule_set_version}"
            if run.quality_status is not None
            else "质量检查：历史运行未记录服务器质量快照。"
        )
        result_style = (
            "field_value_success"
            if run.result is not None
            else "field_value_error"
            if run.error_code
            else "field_value_warning"
        )
        quality_style = (
            "field_value_success"
            if run.quality_status == "success"
            else "field_value_warning"
            if run.quality_status == "warning"
            else "field_value_error"
            if run.quality_status == "blocker"
            else "field_value"
        )
        self._set_detail_fields(
            self.run_detail_summary,
            [
                ("运行 ID", run.run_id, "field_value_mono"),
                ("提案 ID", run.proposal_id, "field_value_mono"),
                ("Trace ID", run.trace_id, "field_value_mono"),
                ("运行状态", labels[run.status], "field_value_status"),
                ("数据版本", run.dataset_version, "field_value_mono"),
                ("样本上限", str(run.parameters["sample_limit"]), "field_value_mono"),
                ("创建时间", run.created_at, "field_value"),
                ("开始时间", run.started_at or "尚未开始", "field_value"),
                ("完成时间", run.finished_at or "运行中", "field_value"),
                ("质量检查", quality_text, quality_style),
                ("运行结果", result_text, result_style),
            ],
        )

    def load_run_events(self, run_id: str) -> None:
        """Fetch selected run events in the background with a per-selection request ID."""
        if not self._project_token:
            self._invalidate_run_events("连接团队账号后查看运行时间线。")
            return
        if self._selected_run_event_id == run_id and (
            self._run_event_loading or self._run_event_loaded_id == run_id
        ):
            return
        self._run_event_request_id += 1
        request_id = self._run_event_request_id
        token = self._project_token
        self._selected_run_event_id = run_id
        self._selected_run_events = None
        self._run_event_loading = True
        self._set_run_event_timeline("正在读取运行事件…")
        threading.Thread(
            target=self._request_run_events,
            args=(request_id, run_id, token),
            name="desktop-run-event-list",
            daemon=True,
        ).start()
        self._schedule_run_event_poll()

    def _request_run_events(self, request_id: int, run_id: str, token: str) -> None:
        try:
            events = self.client.list_run_events(token, run_id)
        except DesktopApiError as exc:
            LOGGER.warning(
                "Run event request failed; route=/api/v1/runs/{run_id}/events error_type=%s",
                type(exc).__name__,
            )
            self._run_event_result_queue.put((request_id, run_id, "error", str(exc)))
        except Exception as exc:
            LOGGER.error(
                "Unexpected run event request failure; route=/api/v1/runs/{run_id}/events error_type=%s",
                type(exc).__name__,
            )
            self._run_event_result_queue.put(
                (request_id, run_id, "error", "暂时无法读取运行时间线，请检查服务地址和账号权限后重试。")
            )
        else:
            self._run_event_result_queue.put((request_id, run_id, "success", events))

    def _schedule_run_event_poll(self) -> None:
        """Keep a single Tk timer polling the event worker result queue."""
        if self._run_event_poll_after_id is None:
            self._run_event_poll_after_id = self.root.after(50, self._poll_run_events)

    def _set_run_event_timeline(
        self,
        message: str | None = None,
        events: list[RunEvent] | None = None,
    ) -> None:
        """Render persisted run events as a selectable, color-coded vertical trace."""
        timeline = self.run_event_timeline
        timeline.configure(state="normal")
        timeline.delete("1.0", "end")
        if not events:
            timeline.insert("end", message or "", "timeline_placeholder")
        else:
            labels = {
                "queued": ("排队中", "timeline_pending"),
                "running": ("运行中", "timeline_running"),
                "succeeded": ("已完成", "timeline_success"),
                "failed": ("失败", "timeline_error"),
            }
            for index, event in enumerate(events):
                if index:
                    timeline.insert("end", "   │\n", "timeline_connector")
                label, status_tag = labels[event.status]
                timeline.insert("end", f"{event.sequence:02d}  ", "timeline_sequence")
                timeline.insert("end", "●  " + label, status_tag)
                timeline.insert("end", f"    {event.occurred_at}\n", "timeline_timestamp")
                if event.error_code:
                    timeline.insert("end", "      错误码 · ", "timeline_placeholder")
                    timeline.insert("end", event.error_code + "\n", "timeline_error_code")
        timeline.configure(state="disabled")
        timeline.yview_moveto(0.0)

    def _poll_run_events(self) -> None:
        self._run_event_poll_after_id = None
        try:
            request_id, run_id, outcome, value = self._run_event_result_queue.get_nowait()
        except queue.Empty:
            if self._run_event_loading:
                self._schedule_run_event_poll()
            return
        self._schedule_page_viewport_refresh()
        if request_id != self._run_event_request_id or run_id != self._selected_run_event_id:
            if self._run_event_loading:
                self._schedule_run_event_poll()
            return

        self._run_event_loading = False
        if outcome != "success" or not isinstance(value, list) or any(
            not isinstance(event, RunEvent) for event in value
        ):
            self._set_run_event_timeline(
                str(value)
                if outcome == "error" and isinstance(value, str)
                else "运行事件服务返回的数据格式不正确。"
            )
            return

        self._run_event_loaded_id = run_id
        self._selected_run_events = value

        if not value:
            self._set_run_event_timeline("该运行尚无可读取的状态事件。")
            return
        self._set_run_event_timeline(events=value)

    def export_selected_run_report(self) -> None:
        """Save a local HTML report for a selected terminal synthetic run."""
        self._export_selected_run_report("html")

    def export_selected_run_pdf(self) -> None:
        """Save a local PDF report for a selected terminal synthetic run."""
        self._export_selected_run_report("pdf")

    def _export_selected_run_report(self, output_format: str) -> None:
        """Write the selected run as HTML or PDF using its current event snapshot."""
        if output_format not in ("html", "pdf"):
            raise ValueError("不支持的报告格式。")
        selection = self.runs_tree.selection()
        if not selection:
            return
        run = self._run_cache.get(selection[0])
        if run is None or run.status not in ("succeeded", "failed"):
            return

        extension = output_format
        format_label = "PDF" if output_format == "pdf" else "HTML"
        destination = filedialog.asksaveasfilename(
            parent=self.root,
            title=f"导出合成运行 {format_label} 报告",
            defaultextension=f".{extension}",
            initialfile=f"ICTResearchWorkbench-{run.run_id[:8]}-report.{extension}",
            filetypes=((f"{format_label} 报告", f"*.{extension}"),),
        )
        if not destination:
            return

        try:
            # Missing or stale event reads stay explicit in the exported report.
            events = (
                self._selected_run_events
                if self._selected_run_event_id == run.run_id and self._run_event_loaded_id == run.run_id
                else None
            )
            if output_format == "pdf":
                Path(destination).write_bytes(render_run_pdf(run, events=events))
            else:
                Path(destination).write_text(
                    render_run_report(run, events=events),
                    encoding="utf-8",
                    newline="\n",
                )
        except Exception as exc:
            LOGGER.error(
                "Run report export failed; format=%s run_id=%s error_type=%s",
                output_format,
                run.run_id,
                type(exc).__name__,
            )
            messagebox.showerror(
                "报告导出失败",
                "无法保存报告，请检查目标位置后重试。",
                parent=self.root,
            )
            return

        LOGGER.info(
            "Run report export complete; format=%s run_id=%s template_version=%s",
            output_format,
            run.run_id,
            REPORT_TEMPLATE_VERSION,
        )
        messagebox.showinfo(
            "报告已导出",
            "合成运行报告已保存到所选位置。",
            parent=self.root,
        )

    def _request_team_projects(self, token: str) -> None:
        try:
            projects = self.client.list_projects(token)
        except DesktopApiError as exc:
            LOGGER.warning("Team project request failed; route=%s error_type=%s", "/api/v1/projects", type(exc).__name__)
            self._project_result_queue.put(("error", str(exc)))
        except Exception as exc:
            # Avoid exception text here because a third-party error may include request headers.
            LOGGER.error("Unexpected team project request failure; route=%s error_type=%s", "/api/v1/projects", type(exc).__name__)
            self._project_result_queue.put(("error", "暂时无法读取团队项目，请检查服务地址和访问令牌后重试。"))
        else:
            self._project_result_queue.put(("success", projects))

    def _poll_team_project_result(self) -> None:
        try:
            outcome, value = self._project_result_queue.get_nowait()
        except queue.Empty:
            if self._project_loading:
                self.root.after(50, self._poll_team_project_result)
            return

        self._schedule_page_viewport_refresh()
        self._project_loading = False
        self.connect_team_projects_button.state(["!disabled"])
        self.clear_team_token_button.state(["!disabled"])
        if outcome == "success" and isinstance(value, list):
            self.team_projects_tree.configure(show="headings" if value else "")
            for project in value:
                if not isinstance(project, ProjectListItem):
                    LOGGER.warning("Team project response rejected; route=%s error_type=InvalidProjectItem", "/api/v1/projects")
                    self.team_projects_status.configure(text="团队项目服务返回的数据格式不正确。")
                    self._clear_project_rows()
                    self._set_table_empty_state(
                        self.project_table_empty_state,
                        "项目数据格式异常",
                        "请重试连接，或联系项目管理员检查服务返回。",
                        visible=True,
                    )
                    self._set_recent_run_summary("团队项目权限格式异常，无法读取最近运行。")
                    return
                self._project_cache[project.project_id] = project
                role_label = "操作者" if project.role == "operator" else "查看者"
                self.team_projects_tree.insert(
                    "",
                    "end",
                    iid=project.project_id,
                    tags=self._table_row_tags(self.team_projects_tree),
                    values=(project.name, project.domain, role_label),
                )
            self._set_project_table_rows_visible(bool(value))
            self._set_project_workspace_expanded(bool(value))
            self._set_table_empty_state(
                self.project_table_empty_state,
                "当前账号没有可访问的项目",
                "请联系团队管理员确认项目成员权限。",
                visible=not bool(value),
            )
            if value:
                self.team_projects_status.configure(text=f"已连接 · 共 {len(value)} 个可访问项目")
            else:
                self.team_projects_status.configure(text="当前账号没有可访问的项目。")
            self.load_runs()
            return

        self.team_projects_status.configure(text=str(value))
        self._set_recent_run_summary("无法确认团队项目权限，暂时无法读取最近运行。")
        self._set_table_empty_state(
            self.project_table_empty_state,
            "暂时无法读取项目",
            "请检查服务地址、访问令牌和网络后重试。",
            visible=True,
        )

    def _on_project_selected(self, _event: object = None) -> None:
        selection = self.team_projects_tree.selection()
        if not selection:
            self.project_context_area.pack_forget()
            self.workflow_project_context.configure(text="尚未选择项目")
            self.workflow_preview_button.state(["disabled"])
            self.quality_dataset_versions.configure(text="请先在工作台选择项目。")
            return
        if not self._project_token:
            self.project_context_area.pack_forget()
            return
        project_id = selection[0]
        if project_id not in self._project_cache:
            self.project_context_area.pack_forget()
            self.workflow_project_context.configure(text="尚未选择项目")
            self.workflow_preview_button.state(["disabled"])
            self.quality_dataset_versions.configure(text="请先在工作台选择项目。")
            return

        if not self.project_context_area.winfo_manager():
            self.project_context_area.pack(fill="x", pady=(14, 0))
        project = self._project_cache[project_id]
        self.workflow_project_context.configure(text=f"当前项目：{project.name}")
        self.workflow_preview_button.state(["!disabled"])
        self.quality_dataset_versions.configure(text=f"正在读取“{project.name}”的数据版本…")

        self._project_detail_request_id += 1
        request_id = self._project_detail_request_id
        self._project_detail_loading = True
        self.project_detail_title.configure(text="正在读取项目详情…")
        self._set_detail_fields(
            self.project_detail_summary,
            [("读取状态", "正在读取当前项目的领域、角色与数据版本…", "field_value_warning")],
        )
        threading.Thread(
            target=self._request_project_detail,
            args=(request_id, project_id, self._project_token),
            name="desktop-team-project-detail",
            daemon=True,
        ).start()
        self.root.after(50, self._poll_project_detail_result)

    def _request_project_detail(self, request_id: int, project_id: str, token: str) -> None:
        try:
            detail = self.client.get_project(project_id, token)
        except DesktopApiError as exc:
            LOGGER.warning(
                "Team project detail request failed; route=%s error_type=%s",
                "/api/v1/projects/{project_id}",
                type(exc).__name__,
            )
            self._project_detail_result_queue.put((request_id, "error", str(exc)))
        except Exception as exc:
            # Do not write exception text because it may contain credentials or response data.
            LOGGER.error(
                "Unexpected team project detail failure; route=%s error_type=%s",
                "/api/v1/projects/{project_id}",
                type(exc).__name__,
            )
            self._project_detail_result_queue.put((request_id, "error", "暂时无法读取项目详情，请稍后重试。"))
        else:
            self._project_detail_result_queue.put((request_id, "success", detail))

    def _poll_project_detail_result(self) -> None:
        try:
            request_id, outcome, value = self._project_detail_result_queue.get_nowait()
        except queue.Empty:
            if self._project_detail_loading:
                self.root.after(50, self._poll_project_detail_result)
            return

        self._schedule_page_viewport_refresh()
        if request_id != self._project_detail_request_id:
            if self._project_detail_loading:
                self.root.after(50, self._poll_project_detail_result)
            return

        self._project_detail_loading = False
        if outcome != "success" or not isinstance(value, ProjectDetail):
            self.project_detail_title.configure(text="暂时无法读取项目详情")
            self.quality_dataset_versions.configure(text="暂时无法读取所选项目的数据版本。")
            self._set_detail_fields(
                self.project_detail_summary,
                [("读取状态", str(value), "field_value_error")],
            )
            return

        role_label = "操作者" if value.role == "operator" else "查看者"
        self.project_detail_title.configure(text=f"{value.name} · {role_label}")
        dataset_versions = [dataset.version for dataset in value.datasets]
        self.quality_dataset_versions.configure(
            text="、".join(dataset_versions) if dataset_versions else "当前项目暂无登记数据版本。"
        )
        detail_fields = [
            ("项目 ID", value.project_id, "field_value_mono"),
            ("研究领域", value.domain, "field_value"),
            ("当前角色", role_label, "field_value_status"),
        ]
        if value.datasets:
            for index, dataset in enumerate(value.datasets, start=1):
                readiness = "已标记就绪（仍需人工核验）" if dataset.research_ready else "尚未标记就绪"
                detail_fields.extend((
                    (f"数据版本 {index}", dataset.version, "field_value_mono"),
                    ("来源", dataset.source, "field_value"),
                    ("许可状态", dataset.license_status, "field_value"),
                    ("科研就绪", readiness, "field_value_warning"),
                ))
        else:
            detail_fields.append(("数据版本", "暂无登记数据版本", "field_value_warning"))
        detail_fields.append(
            ("核验说明", "许可与就绪状态为项目登记信息；使用前仍需独立核验。", "field_value_warning")
        )
        self._set_detail_fields(self.project_detail_summary, detail_fields)

    def choose_manifest_file(self) -> None:
        """Ask the user to select a CSV; the selected file stays on this computer."""
        if self._quality_loading:
            return
        selected_path = filedialog.askopenfilename(
            parent=self.root,
            title="选择数据清单",
            filetypes=(("CSV 清单", "*.csv"),),
        )
        if selected_path:
            self.run_manifest_check(Path(selected_path))

    def run_manifest_check(self, path: str | Path) -> None:
        """Validate a selected manifest in a worker thread without sending file data."""
        if self._quality_loading:
            return
        manifest_path = Path(path)
        self._quality_loading = True
        self.manifest_file_label.configure(text=manifest_path.name)
        self.quality_report_status.configure(text="正在检查清单…")
        self.manifest_summary.configure(text="正在本机读取 CSV 清单。")
        self.manifest_issues.configure(text="")
        self.manifest_guidance.configure(text="正在整理本机预检结果。")
        self.select_manifest_button.state(["disabled"])
        threading.Thread(
            target=self._inspect_manifest,
            args=(manifest_path,),
            name="desktop-manifest-check",
            daemon=True,
        ).start()
        self.root.after(50, self._poll_manifest_result_queue)

    def _inspect_manifest(self, path: Path) -> None:
        try:
            report = self._manifest_checker(path)
        except ManifestQualityError as exc:
            LOGGER.warning("Local manifest check failed; error_code=%s", exc.code)
            self._quality_result_queue.put(("error", exc))
        except Exception as exc:
            LOGGER.exception("Unexpected local manifest check failure; error_type=%s", type(exc).__name__)
            self._quality_result_queue.put(("error", "无法完成清单检查，请确认文件格式和访问权限后重试。"))
        else:
            self._quality_result_queue.put(("success", report))

    def _poll_manifest_result_queue(self) -> None:
        try:
            outcome, value = self._quality_result_queue.get_nowait()
        except queue.Empty:
            if self._quality_loading:
                self.root.after(50, self._poll_manifest_result_queue)
            return

        self._quality_loading = False
        self.select_manifest_button.state(["!disabled"])
        if outcome == "error" and isinstance(value, ManifestQualityError) and value.severity == "blocker":
            self.quality_report_status.configure(
                text="阻断：清单结构不符合要求",
                style="QualityBlocker.TLabel",
            )
            self.manifest_summary.configure(text=str(value))
            self.manifest_issues.configure(text=f"【阻断】{value}")
            guidance = f"建议：{value.guidance}" if value.guidance else "建议：检查并修正清单结构后重试。"
            self.manifest_guidance.configure(
                text=f"{guidance}\n本机结果未关联或更新服务器数据版本，不能作为科研审批依据。"
            )
            self._schedule_page_viewport_refresh()
            return

        if outcome == "success" and isinstance(value, ManifestQualityReport):
            status_labels = {
                "blocker": ("阻断：存在需修复的问题", "QualityBlocker.TLabel"),
                "warning": ("警告：存在未检查项", "QualityWarning.TLabel"),
                "success": ("通过：通用结构预检", "QualitySuccess.TLabel"),
            }
            status_text, status_style = status_labels[value.status]
            self.quality_report_status.configure(text=status_text, style=status_style)
            split_summary = " / ".join(f"{split} {count}" for split, count in value.split_counts) or "无"
            self.manifest_summary.configure(
                text=(
                    f"记录数：{value.row_count}；拆分：{split_summary}；类别数：{value.label_category_count}；"
                    f"SHA-256：{value.sha256}"
                )
            )
            if value.issues:
                issue_lines = []
                for issue in value.issues:
                    severity = "警告" if issue.severity == "warning" else "阻断"
                    if issue.line_numbers:
                        line_list = ", ".join(map(str, issue.line_numbers))
                        issue_lines.append(f"【{severity}】{issue.message}影响 {issue.count} 项；行号：{line_list}。")
                    else:
                        count_text = f"涉及 {issue.count} 列。" if issue.severity == "warning" else ""
                        issue_lines.append(f"【{severity}】{issue.message}{count_text}")
                self.manifest_issues.configure(text="\n".join(issue_lines))
            else:
                self.manifest_issues.configure(text="未发现缺失必需值、重复编号或分组跨拆分问题。")
            guidance_lines = [f"建议：{issue.guidance}" for issue in value.issues if issue.guidance]
            if value.status == "success":
                guidance_lines.append("通过仅表示通用结构预检无阻断项，不代表数据已获授权或可用于科研。")
            guidance_lines.append("本机结果未关联或更新服务器数据版本，不能作为科研审批依据。")
            self.manifest_guidance.configure(text="\n".join(guidance_lines))
            self._schedule_page_viewport_refresh()
            return

        self.quality_report_status.configure(text="检查未完成")
        self.manifest_summary.configure(text=str(value))
        self.manifest_issues.configure(text="")
        self.manifest_guidance.configure(text="检查未完成不会形成审批结果；请检查文件编码、表头与访问权限后重试。")
        self._schedule_page_viewport_refresh()

    def show_service_settings(self) -> None:
        """Open the small dialog used to configure the backend address."""
        if self.service_settings_dialog is not None and self.service_settings_dialog.winfo_exists():
            self.service_settings_dialog.lift()
            return

        dialog = tk.Toplevel(self.root)
        self.service_settings_dialog = dialog
        dialog.title("服务设置")
        dialog.transient(self.root)
        dialog.after_idle(apply_windows_dark_titlebar, dialog)
        dialog.resizable(True, True)
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        width = min(600, max(320, screen_width - 64))
        height = min(320, max(250, screen_height - 100))
        x = max(0, min(self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2, screen_width - width))
        y = max(0, min(self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2, screen_height - height - 40))
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.minsize(min(440, width), min(285, height))
        LOGGER.info("Service settings viewport; screen=%sx%s window=%sx%s", screen_width, screen_height, width, height)
        dialog.configure(background=COLORS["paper"])

        panel = ttk.Frame(dialog, style="Card.TFrame", padding=(22, 20, 22, 17))
        panel.pack(fill="both", expand=True, padx=13, pady=13)
        ttk.Label(panel, text="服务连接", style="Eyebrow.TLabel").pack(anchor="w", pady=(0, 7))
        ttk.Label(panel, text="后端服务地址", style="CardTitle.TLabel").pack(anchor="w")
        self.service_settings_guidance = ttk.Label(
            panel,
            text="本机测试可使用 http://127.0.0.1；远程服务必须使用 HTTPS。软件只保存服务地址，不保存密码或密钥。",
            style="Body.TLabel",
            wraplength=width - 80,
            justify="left",
        )
        self.service_settings_guidance.pack(anchor="w", pady=(8, 12))

        self.service_url_label = ttk.Label(panel, text="服务地址", style="InputLabel.TLabel")
        self.service_url_label.pack(anchor="w", pady=(0, 5))
        self.service_url_entry = ttk.Entry(panel, width=1)
        self.service_url_entry.pack(fill="x")
        self.service_url_entry.insert(0, self.api_base_url)
        self.service_url_entry.focus_set()

        self.service_settings_error = ttk.Label(panel, text="", style="SettingsError.TLabel", justify="left")

        def resize_guidance(event: tk.Event) -> None:
            # Keep guidance and validation errors inside the available content width.
            wraplength = max(180, int(event.width) - 45)
            self.service_settings_guidance.configure(wraplength=wraplength)
            self.service_settings_error.configure(wraplength=wraplength)

        panel.bind("<Configure>", resize_guidance, add="+")

        actions = ttk.Frame(panel, style="Card.TFrame")
        actions.pack(fill="x", side="bottom", pady=(12, 0))
        ttk.Button(actions, text="取消", style="Quiet.TButton", command=dialog.destroy).pack(side="right")
        self.service_settings_save_button = ttk.Button(actions, text="保存并连接", style="Primary.TButton", command=self.save_service_settings)
        self.service_settings_save_button.pack(side="right", padx=(0, 8))
        dialog.bind("<Return>", lambda _event: self.save_service_settings())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.grab_set()

    def show_quick_start(self) -> None:
        """Open the native onboarding flow on demand, reusing existing read-only pages."""
        if self.quick_start_wizard is not None:
            try:
                if self.quick_start_wizard.dialog.winfo_exists():
                    self.quick_start_wizard.dialog.lift()
                    return
            except tk.TclError:
                pass

        self.quick_start_wizard = QuickStartWizard(
            self.root,
            initial_service_url=self.api_base_url,
            get_client=lambda: self.client,
            save_service_url=self._save_service_url,
            connect_team=self._connect_team_from_quick_start,
            get_team_state=self._quick_start_team_state,
            open_proposals=self.show_proposals,
        )

    def _connect_team_from_quick_start(self, token: str) -> None:
        """Pass the token to the existing in-memory, read-only team connection flow."""
        if self._project_loading:
            return
        self.show_projects()
        self.team_token_entry.delete(0, "end")
        self.team_token_entry.insert(0, token)
        try:
            self.connect_team_projects()
        finally:
            # Keep the token in the existing session field only; never leave it displayed.
            self.team_token_entry.delete(0, "end")

    def _quick_start_team_state(self) -> dict[str, Any]:
        status = self.team_projects_status.cget("text")
        ready = status.startswith("已连接 ·") or status == "当前账号没有可访问的项目。"
        projects = [
            {
                "name": project.name,
                "role": "操作者" if project.role == "operator" else "查看者",
            }
            for project in self._project_cache.values()
        ]
        return {
            "loading": self._project_loading,
            "ready": ready,
            "status": status,
            "projects": projects,
        }

    def _save_service_url(self, service_url: str) -> str | None:
        """Validate and persist a service URL for both settings and quick start."""
        try:
            new_client = DemoProjectApiClient(service_url)
        except DesktopApiError as exc:
            return str(exc)

        try:
            self._settings_saver(service_url)
        except Exception as exc:
            LOGGER.exception("Saving desktop service settings failed; error_type=%s", type(exc).__name__)
            return "无法保存服务地址，请检查本机存储权限后重试。"

        if service_url != self.api_base_url:
            self.quality_dataset_versions.configure(text="服务地址已变更；请重新连接并选择项目。")
        self.api_base_url = service_url
        self.client = new_client
        self.check_service_health()
        return None

    def save_service_settings(self) -> None:
        """Validate, persist, and activate a new backend URL without storing credentials."""
        service_url = self.service_url_entry.get().strip()
        error = self._save_service_url(service_url)
        if error:
            self.service_settings_error.configure(text=error)
            self.service_settings_error.pack(anchor="w", pady=(6, 0))
            return

        dialog = self.service_settings_dialog
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()

    def check_service_health(self) -> None:
        """Refresh the top-bar connection indicator without fetching project data."""
        self._health_request_id += 1
        request_id = self._health_request_id
        client = self.client
        self._health_loading = True
        threading.Thread(
            target=self._request_service_health,
            args=(request_id, client),
            name="desktop-service-health-check",
            daemon=True,
        ).start()
        self.root.after(50, self._poll_service_health_result)

    def _request_service_health(self, request_id: int, client: Any) -> None:
        try:
            client.check_health()
        except DesktopApiError as exc:
            LOGGER.warning(
                "Service health check failed; route=%s error_type=%s",
                HEALTH_PATH,
                type(exc).__name__,
            )
            self._health_result_queue.put((request_id, "error", "无法连接项目服务，请检查服务地址和网络后重试。"))
        except Exception as exc:
            LOGGER.exception("Unexpected service health check failure; error_type=%s", type(exc).__name__)
            self._health_result_queue.put((request_id, "error", "无法连接项目服务，请稍后重试。"))
        else:
            self._health_result_queue.put((request_id, "success", None))

    def _poll_service_health_result(self) -> None:
        try:
            request_id, outcome, _message = self._health_result_queue.get_nowait()
        except queue.Empty:
            if self._health_loading:
                self.root.after(50, self._poll_service_health_result)
            return

        if request_id != self._health_request_id:
            if self._health_loading:
                self.root.after(50, self._poll_service_health_result)
            return

        self._health_loading = False
        self._set_connection_status("ok" if outcome == "success" else "error")
