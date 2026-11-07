"""A themed, selectable contract reader with no network or execution actions."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from .api import PipelineFieldContract, PipelineTemplateContract
from .ui_theme import COLORS, FONTS, apply_windows_dark_titlebar


LOGGER = logging.getLogger(__name__)


class TemplateContractDialog:
    """Keep the full server contract readable at small window sizes and high DPI."""

    def __init__(self, parent: tk.Misc, contract: PipelineTemplateContract) -> None:
        self._return_focus = parent.focus_get()
        self._closed = False
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("固定模板说明 · ICT 研究工作台")
        self.dialog.after_idle(apply_windows_dark_titlebar, self.dialog)
        self.dialog.configure(background=COLORS["surface"])
        self.dialog.transient(parent)
        self.dialog.protocol("WM_DELETE_WINDOW", self.close)
        self.dialog.bind("<Escape>", self.close)
        self._fit_to_screen(parent)

        panel = ttk.Frame(self.dialog, style="Card.TFrame", padding=(22, 18))
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        header = ttk.Frame(panel, style="Card.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ttk.Label(header, text="模板契约 · 只读", style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(header, text=contract.template_id, style="ProjectTitle.TLabel").pack(anchor="w", pady=(5, 4))
        ttk.Label(header, text="查看输入、输出与执行限制，核对后再回到提案页。", style="Body.TLabel").pack(anchor="w")

        reading_area = ttk.Frame(panel, style="Card.TFrame")
        reading_area.grid(row=1, column=0, sticky="nsew")
        reading_area.rowconfigure(0, weight=1)
        reading_area.columnconfigure(0, weight=1)
        self.body = tk.Text(
            reading_area, wrap="word", width=1, height=1, font=FONTS["ui"],
            background=COLORS["surface"], foreground=COLORS["ink_soft"],
            selectbackground=COLORS["sidebar_active"], selectforeground=COLORS["white"],
            relief="flat", borderwidth=0, highlightthickness=1,
            highlightbackground=COLORS["line"], highlightcolor=COLORS["accent_text"],
            padx=14, pady=10, spacing1=2, spacing3=4, takefocus=True, cursor="xterm",
        )
        self.body.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(reading_area, orient="vertical", command=self.body.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(5, 0))
        self.body.configure(yscrollcommand=self.scrollbar.set)
        self.body.tag_configure("section", foreground=COLORS["ink"], font=FONTS["contract_section"], spacing1=12, spacing3=7)
        self.body.tag_configure("mono", foreground=COLORS["muted"], font=FONTS["mono"], spacing3=8)
        self.body.tag_configure("scope", foreground=COLORS["warning_text"])
        self._populate(contract)
        # Disabled Text still supports selection, copying and keyboard scrolling.
        self.body.configure(state="disabled")
        self.body.bind("<Control-a>", self._select_all)
        self.body.bind("<Control-A>", self._select_all)

        footer = ttk.Frame(panel, style="Card.TFrame")
        footer.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, text="可选择文本复制 · Esc 关闭", style="Muted.TLabel", wraplength=220).grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.close_button = ttk.Button(footer, text="返回提案", style="Quiet.TButton", command=self.close)
        self.close_button.grid(row=0, column=1, sticky="e")
        self.dialog.grab_set()
        self.body.focus_set()
        LOGGER.info("Template contract reader opened; template_id=%s version=%s", contract.template_id, contract.version)

    def _fit_to_screen(self, parent: tk.Misc) -> None:
        screen_width = self.dialog.winfo_screenwidth()
        screen_height = self.dialog.winfo_screenheight()
        width = min(760, max(320, screen_width - 64))
        height = min(680, max(320, screen_height - 100))
        x = max(0, min(parent.winfo_rootx() + (parent.winfo_width() - width) // 2, screen_width - width))
        y = max(0, min(parent.winfo_rooty() + (parent.winfo_height() - height) // 2, screen_height - height - 40))
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
        self.dialog.minsize(min(480, width), min(360, height))

    def _section(self, title: str, text: str, tag: str | None = None) -> None:
        self.body.insert("end", title + "\n", "section")
        self.body.insert("end", text + "\n", tag or ())

    @staticmethod
    def _fields(fields: dict[str, PipelineFieldContract]) -> str:
        lines = []
        for name, field in fields.items():
            details = [field.field_type, "必填" if field.required else "可选"]
            if field.minimum is not None and field.maximum is not None:
                details.append(f"范围 {field.minimum} 到 {field.maximum}")
            elif field.minimum is not None:
                details.append(f"最小值 {field.minimum}")
            elif field.maximum is not None:
                details.append(f"最大值 {field.maximum}")
            if field.const is not None:
                constant = str(field.const).lower() if isinstance(field.const, bool) else str(field.const)
                details.append(f"固定值 {constant}")
            lines.append(name + "\n" + " · ".join(details))
        return "\n\n".join(lines)

    def _populate(self, contract: PipelineTemplateContract) -> None:
        self._section("身份与版本", f"模板：{contract.template_id}\n版本：{contract.version}\n固定执行器：{contract.executor}\n数据版本：{contract.dataset_version}")
        self._section("清单 SHA-256", contract.manifest_sha256, "mono")
        for heading, fields in (("输入", contract.inputs), ("参数", contract.parameters), ("输出", contract.outputs)):
            self._section(heading, self._fields(fields))
        limits = contract.resource_limits
        self._section("权限与资源", "权限：只读，仅读取登记的合成数据集清单。\n"
                      f"并发上限：{limits.max_concurrent_runs}\n软超时：{limits.soft_timeout_seconds} 秒\n硬超时：{limits.hard_timeout_seconds} 秒")
        self._section("状态与错误", "运行状态：" + " → ".join(contract.states) + "\n\n错误代码：\n" + "\n".join(contract.error_codes))
        self._section("适用边界", "synthetic_only=true；research_ready=false。\n不读取真实研究或医疗数据，也不形成医学或科研结论。", "scope")

    def _select_all(self, _event: object = None) -> str:
        self.body.tag_add("sel", "1.0", "end-1c")
        return "break"

    def close(self, _event: object = None) -> str:
        if not self._closed:
            self._closed = True
            if self.dialog.winfo_exists():
                self.dialog.grab_release()
                self.dialog.destroy()
            if self._return_focus is not None and self._return_focus.winfo_exists():
                self._return_focus.focus_set()
            LOGGER.debug("Template contract reader closed")
        return "break"
