"""Shared visual system for the native ICT research workbench."""

from __future__ import annotations

import ctypes
import logging
import os
import tkinter as tk
from tkinter import ttk
from ctypes import wintypes


LOGGER = logging.getLogger(__name__)


COLORS = {
    # Warm-neutral work surfaces keep dense research pages calm and legible.
    "paper": "#F3F5F7",
    "surface": "#FFFFFF",
    "surface_alt": "#F6F8FA",
    "surface_row_alt": "#FAFBFC",
    "ink": "#182433",
    "ink_soft": "#48596B",
    "muted": "#647487",
    "line": "#E4E9EF",
    "sidebar": "#FFFFFF",
    "sidebar_hover": "#F1F5FA",
    "sidebar_active": "#EAF1FC",
    "sidebar_text": "#182433",
    "sidebar_muted": "#647487",
    "accent": "#3268D8",
    "accent_hover": "#2858BE",
    "accent_text": "#2C5DBB",
    "moss": "#15803D",
    "gold": "#B45309",
    "warning_text": "#B45309",
    "error": "#FEF2F2",
    "danger_text": "#B91C1C",
    "white": "#FFFFFF",
}

# Shared font tokens keep matching components on the same readable type scale.
FONTS = {
    "ui": ("Microsoft YaHei UI", 10),
    "ui_small": ("Microsoft YaHei UI", 9),
    "ui_bold": ("Microsoft YaHei UI", 10, "bold"),
    "title": ("Microsoft YaHei UI", 18, "bold"),
    "brand": ("Microsoft YaHei UI", 12, "bold"),
    "overline": ("Segoe UI", 9, "bold"),
    "card_title": ("Microsoft YaHei UI", 11, "bold"),
    "quality_status": ("Microsoft YaHei UI", 11, "bold"),
    "wizard_title": ("Microsoft YaHei UI", 18, "bold"),
    "project_title": ("Microsoft YaHei UI", 16, "bold"),
    "contract_section": ("Microsoft YaHei UI", 10, "bold"),
    "mono": ("Consolas", 9),
    "mono_small": ("Consolas", 8),
}


def apply_windows_dark_titlebar(window: tk.Misc) -> None:
    """Match the native caption to the app palette on supported Windows versions."""
    if os.name != "nt":
        return

    # DWM may accept caption attributes before Tk maps the HWND but ignore their visual state.
    if not window.winfo_ismapped():
        if getattr(window, "_native_caption_map_binding", None):
            return

        def apply_after_map(event: tk.Event) -> None:
            """Apply DWM colors once Tk has exposed the top-level window."""
            if event.widget is not window:
                return
            binding_id = getattr(window, "_native_caption_map_binding", None)
            try:
                if binding_id:
                    window.unbind("<Map>", binding_id)
                window._native_caption_map_binding = None
                window.after_idle(apply_windows_dark_titlebar, window)
            except tk.TclError as exc:
                LOGGER.debug(
                    "Native caption map callback skipped; error_type=%s",
                    type(exc).__name__,
                )

        try:
            window._native_caption_map_binding = window.bind("<Map>", apply_after_map, add="+")
            LOGGER.info("Native caption theme deferred; mapped=False")
        except tk.TclError as exc:
            LOGGER.warning(
                "Native caption theme could not wait for window mapping; error_type=%s",
                type(exc).__name__,
            )
        return

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        get_ancestor = user32.GetAncestor
        get_ancestor.argtypes = (wintypes.HWND, wintypes.UINT)
        get_ancestor.restype = wintypes.HWND
        set_window_attribute = dwmapi.DwmSetWindowAttribute
        set_window_attribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
        set_window_attribute.restype = ctypes.c_long  # HRESULT is a signed 32-bit value on Windows.

        # Tk returns a client HWND; DWM's caption attribute belongs to the root HWND.
        child_hwnd = wintypes.HWND(window.winfo_id())
        root_hwnd = get_ancestor(child_hwnd, 2)  # GA_ROOT
        hwnd = root_hwnd or child_hwnd
        # ctypes may expose an HWND return as either an integer or a c_void_p wrapper.
        hwnd_value = int(getattr(hwnd, "value", hwnd) or 0)
        LOGGER.info(
            "Applying native caption theme; mapped=%s child_hwnd=0x%X root_hwnd=0x%X",
            bool(window.winfo_ismapped()),
            int(child_hwnd.value or 0),
            hwnd_value,
        )
        enabled = wintypes.BOOL(True)
        # DWMWA_USE_IMMERSIVE_DARK_MODE, caption and text colors are native DWM attributes.
        attributes = (
            (20, enabled),
            (34, wintypes.DWORD(_colorref(COLORS["line"]))),
            (35, wintypes.DWORD(_colorref(COLORS["paper"]))),
            (36, wintypes.DWORD(_colorref(COLORS["ink"]))),
        )
        for attribute, value in attributes:
            result = set_window_attribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
            hresult = result & 0xFFFFFFFF
            if result != 0:
                LOGGER.warning(
                    "Native caption attribute unavailable; attribute=%d hresult=0x%08X",
                    attribute,
                    hresult,
                )
            else:
                LOGGER.info(
                    "Native caption attribute applied; hwnd=0x%X attribute=%d hresult=0x%08X",
                    hwnd_value,
                    attribute,
                    hresult,
                )
    except (AttributeError, OSError, tk.TclError):
        # Older Windows builds may not expose this optional DWM attribute.
        LOGGER.warning("Native dark title bar unavailable on this Windows build", exc_info=True)


def _colorref(hex_color: str) -> int:
    """Convert Tk's RGB hex color to the BGR byte order expected by Win32 COLORREF."""
    red, green, blue = (int(hex_color[index : index + 2], 16) for index in (1, 3, 5))
    return red | (green << 8) | (blue << 16)


def configure_theme(root: tk.Misc) -> None:
    """Configure named styles once so the shell and dialogs share one language."""
    # Use the workbench's geometric mark instead of Tk's default feather icon.
    icon = tk.PhotoImage(master=root, width=32, height=32)
    icon.put(COLORS["sidebar"], to=(0, 0, 32, 32))
    icon.put(COLORS["line"], to=(1, 1, 31, 31))
    icon.put(COLORS["sidebar"], to=(2, 2, 30, 30))
    icon.put(COLORS["accent_text"], to=(8, 8, 11, 24))
    icon.put(COLORS["sidebar_text"], to=(15, 21, 25, 24))
    icon.put(COLORS["sidebar_text"], to=(15, 15, 23, 18))
    root.iconphoto(True, icon)
    root._ict_app_icon = icon  # Tk does not retain the Python image reference.
    root.after_idle(apply_windows_dark_titlebar, root)
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    style.configure("TFrame", background=COLORS["paper"])
    style.configure("TLabel", background=COLORS["surface"], foreground=COLORS["ink"], font=FONTS["ui"])
    style.configure("TButton", background=COLORS["surface_alt"], foreground=COLORS["ink"], padding=(12, 8), font=FONTS["ui_bold"], borderwidth=0, focusthickness=1, focuscolor=COLORS["accent_text"])
    style.map(
        "TButton",
        background=[("disabled", COLORS["surface_alt"]), ("active", COLORS["line"])],
        foreground=[("disabled", COLORS["muted"]), ("active", COLORS["ink"])],
    )
    style.configure("TEntry", fieldbackground=COLORS["surface_alt"], foreground=COLORS["ink"], insertcolor=COLORS["ink"], padding=(9, 7), borderwidth=1, bordercolor=COLORS["line"], lightcolor=COLORS["line"], darkcolor=COLORS["line"])
    style.map("TEntry", fieldbackground=[("disabled", COLORS["surface"]), ("focus", COLORS["surface_alt"])], bordercolor=[("focus", COLORS["accent_text"])])

    style.configure("App.TFrame", background=COLORS["paper"])
    style.configure("Sidebar.TFrame", background=COLORS["sidebar"])
    style.configure("Topbar.TFrame", background=COLORS["surface"])
    style.configure("Card.TFrame", background=COLORS["surface"], relief="flat", borderwidth=0)
    # A quiet queue surface and a bounded inspector make list/detail roles legible at a glance.
    style.configure("ListPane.TFrame", background=COLORS["surface"], relief="flat", borderwidth=0)
    style.configure(
        "InspectorPane.TFrame",
        background=COLORS["surface"],
        relief="flat",
        borderwidth=0,
    )
    style.configure("InspectorActions.TFrame", background=COLORS["surface"], relief="flat", borderwidth=0)
    style.configure("Timeline.TFrame", background=COLORS["surface_alt"], relief="solid", borderwidth=1, bordercolor=COLORS["line"], lightcolor=COLORS["line"], darkcolor=COLORS["line"])
    style.configure(
        "AccessStrip.TFrame",
        background=COLORS["surface"],
        relief="flat",
        borderwidth=0,
    )
    style.configure(
        "AccessContent.TFrame",
        background=COLORS["surface"],
        relief="flat",
        borderwidth=0,
    )
    style.configure(
        "Pane.TFrame",
        background=COLORS["surface"],
        relief="flat",
        borderwidth=0,
    )
    style.configure("Notice.TFrame", background=COLORS["surface_alt"], relief="flat", borderwidth=0)
    style.configure("CategoryActive.TFrame", background=COLORS["sidebar_active"], relief="flat", borderwidth=0)
    style.configure("CatalogSidebar.TFrame", background=COLORS["surface_alt"], relief="flat", borderwidth=0)
    style.configure("WorkbenchModule.TFrame", background=COLORS["surface_alt"], relief="flat", borderwidth=0)
    style.configure("ContextRail.TFrame", background=COLORS["surface_alt"], relief="flat", borderwidth=0)
    style.configure("ActivityItem.TFrame", background=COLORS["surface_alt"], relief="flat", borderwidth=0)
    style.configure("SettingStatus.TFrame", background=COLORS["surface_alt"], relief="flat", borderwidth=0)
    style.configure("SettingStatusRail.TFrame", background=COLORS["accent"], relief="flat", borderwidth=0)
    style.configure("Wizard.TFrame", background=COLORS["surface"])
    style.configure("Workflow.TFrame", background=COLORS["paper"], relief="flat", borderwidth=0)
    style.configure("TableEmpty.TFrame", background=COLORS["surface_alt"], padding=(18, 14))
    style.configure("PageEmpty.TFrame", background=COLORS["surface"], relief="flat", borderwidth=0)
    style.configure("PageEmptyQuiet.TFrame", background=COLORS["paper"], relief="flat", borderwidth=0)
    # Clear page panels help disconnected workspaces feel intentionally composed, not empty.
    style.configure(
        "ContentPanel.TFrame",
        background=COLORS["surface"],
        relief="solid",
        borderwidth=1,
        bordercolor=COLORS["line"],
        lightcolor=COLORS["line"],
        darkcolor=COLORS["line"],
    )
    style.configure("ServiceBanner.TFrame", background=COLORS["sidebar_active"], relief="flat", borderwidth=0)
    style.configure(
        "ServiceBannerTitle.TLabel",
        background=COLORS["sidebar_active"],
        foreground=COLORS["accent_text"],
        font=FONTS["ui_bold"],
    )
    style.configure(
        "ServiceBannerBody.TLabel",
        background=COLORS["sidebar_active"],
        foreground=COLORS["ink_soft"],
        font=FONTS["ui"],
    )
    style.configure("ProcessStrip.TFrame", background=COLORS["surface"], relief="flat", borderwidth=0)
    style.configure(
        "ProcessIndex.TLabel",
        background=COLORS["sidebar_active"],
        foreground=COLORS["accent_text"],
        font=FONTS["ui_bold"],
        padding=(7, 4),
    )
    style.configure("ProcessTitle.TLabel", background=COLORS["surface"], foreground=COLORS["ink"], font=FONTS["ui_bold"])
    style.configure("ProcessBody.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=FONTS["ui_small"])
    style.configure("InlineEmpty.TFrame", background=COLORS["surface"], relief="flat", borderwidth=0)
    style.configure("InlineEmptyTitle.TLabel", background=COLORS["surface"], foreground=COLORS["ink"], font=FONTS["card_title"])
    style.configure("InlineEmptyBody.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=FONTS["ui"])
    style.configure("CatalogCategory.TButton", background=COLORS["surface_alt"], foreground=COLORS["muted"], padding=(9, 8), anchor="w", font=FONTS["ui"], borderwidth=0, focusthickness=0)
    style.map("CatalogCategory.TButton", background=[("disabled", COLORS["surface_alt"])], foreground=[("disabled", COLORS["muted"])])
    style.configure("CatalogCategoryActive.TButton", background=COLORS["sidebar_active"], foreground=COLORS["accent_text"], padding=(9, 8), anchor="w", font=FONTS["ui_bold"], borderwidth=0, focusthickness=0)
    style.map("CatalogCategoryActive.TButton", background=[("disabled", COLORS["sidebar_active"])], foreground=[("disabled", COLORS["accent_text"])])
    style.configure("PageEmptyTitle.TLabel", background=COLORS["surface"], foreground=COLORS["ink"], font=FONTS["card_title"])
    style.configure("PageEmptyBody.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=FONTS["ui"])
    style.configure("PageEmptyStatus.TLabel", background=COLORS["surface_alt"], foreground=COLORS["muted"], font=FONTS["ui_small"], padding=(8, 4))
    style.configure("PageEmptyQuietTitle.TLabel", background=COLORS["paper"], foreground=COLORS["ink"], font=FONTS["card_title"])
    style.configure("PageEmptyQuietBody.TLabel", background=COLORS["paper"], foreground=COLORS["muted"], font=FONTS["ui"])
    style.configure("PageEmptyQuietStatus.TLabel", background=COLORS["paper"], foreground=COLORS["muted"], font=FONTS["ui_small"])
    style.configure("PageSectionTitle.TLabel", background=COLORS["paper"], foreground=COLORS["ink"], font=FONTS["card_title"])
    style.configure("SettingsBody.TLabel", background=COLORS["paper"], foreground=COLORS["ink_soft"], font=FONTS["ui"])
    style.configure("ModuleHeading.TLabel", background=COLORS["surface_alt"], foreground=COLORS["muted"], font=FONTS["overline"])
    style.configure("RailHeading.TLabel", background=COLORS["surface_alt"], foreground=COLORS["ink"], font=FONTS["card_title"])
    style.configure("RailEyebrow.TLabel", background=COLORS["surface_alt"], foreground=COLORS["muted"], font=FONTS["overline"])
    style.configure("RailBody.TLabel", background=COLORS["surface_alt"], foreground=COLORS["ink_soft"], font=FONTS["ui_small"])
    style.configure("ActivityTitle.TLabel", background=COLORS["surface_alt"], foreground=COLORS["ink"], font=FONTS["ui_bold"])
    style.configure("ActivityBody.TLabel", background=COLORS["surface_alt"], foreground=COLORS["muted"], font=FONTS["ui_small"])
    style.configure("SettingStatus.TLabel", background=COLORS["surface_alt"], foreground=COLORS["ink_soft"], font=FONTS["ui"])
    style.configure("Composer.TFrame", background=COLORS["surface"], relief="solid", borderwidth=1, bordercolor=COLORS["line"], lightcolor=COLORS["line"], darkcolor=COLORS["line"])
    style.configure("TSeparator", background=COLORS["line"], lightcolor=COLORS["line"], darkcolor=COLORS["line"])
    style.configure("TScrollbar", background=COLORS["surface_alt"], troughcolor=COLORS["paper"], bordercolor=COLORS["paper"], arrowcolor=COLORS["muted"], lightcolor=COLORS["surface_alt"], darkcolor=COLORS["surface_alt"], arrowsize=12)
    style.map("TScrollbar", background=[("active", COLORS["line"]), ("pressed", COLORS["sidebar_active"])])

    style.configure("Brand.TLabel", background=COLORS["sidebar"], foreground=COLORS["sidebar_text"], font=FONTS["brand"])
    style.configure("BrandSub.TLabel", background=COLORS["sidebar"], foreground=COLORS["sidebar_muted"], font=FONTS["ui_small"])
    style.configure("Section.TLabel", background=COLORS["sidebar"], foreground=COLORS["sidebar_muted"], font=FONTS["overline"])
    style.configure("PrimaryNav.TButton", background=COLORS["surface"], foreground=COLORS["ink_soft"], padding=(10, 10), anchor="center", font=FONTS["ui"], borderwidth=0, focusthickness=0, focuscolor=COLORS["accent"])
    style.map("PrimaryNav.TButton", background=[("active", COLORS["surface_alt"])], foreground=[("active", COLORS["accent_text"])])
    style.configure("PrimaryNavActive.TButton", background=COLORS["surface"], foreground=COLORS["accent_text"], padding=(10, 10), anchor="center", font=FONTS["ui_bold"], borderwidth=0, focusthickness=0, focuscolor=COLORS["accent"])
    style.map("PrimaryNavActive.TButton", background=[("active", COLORS["surface_alt"])], foreground=[("active", COLORS["accent_text"])])
    style.configure("SettingsNav.TButton", background=COLORS["surface_alt"], foreground=COLORS["ink_soft"], padding=(10, 8), anchor="w", font=FONTS["ui"], borderwidth=0, focusthickness=0, focuscolor=COLORS["accent"])
    style.map("SettingsNav.TButton", background=[("active", COLORS["sidebar_hover"])], foreground=[("active", COLORS["accent_text"])])
    style.configure("SettingsNavActive.TButton", background=COLORS["sidebar_active"], foreground=COLORS["accent_text"], padding=(10, 8), anchor="w", font=FONTS["ui_bold"], borderwidth=0, focusthickness=0, focuscolor=COLORS["accent"])
    style.map("SettingsNavActive.TButton", background=[("active", COLORS["sidebar_active"])], foreground=[("active", COLORS["accent_text"])])
    style.configure("WorkbenchModule.TButton", background=COLORS["surface_alt"], foreground=COLORS["ink_soft"], padding=(10, 9), anchor="w", font=FONTS["ui"], borderwidth=0, focusthickness=0, focuscolor=COLORS["accent"])
    style.map("WorkbenchModule.TButton", background=[("active", COLORS["sidebar_hover"])], foreground=[("active", COLORS["accent_text"])])
    style.configure("WorkbenchModuleActive.TButton", background=COLORS["sidebar_active"], foreground=COLORS["accent_text"], padding=(10, 9), anchor="w", font=FONTS["ui_bold"], borderwidth=0, focusthickness=0, focuscolor=COLORS["accent"])
    style.map("WorkbenchModuleActive.TButton", background=[("active", COLORS["sidebar_active"])], foreground=[("active", COLORS["accent_text"])])
    style.configure("Rail.TButton", background=COLORS["surface_alt"], foreground=COLORS["accent_text"], padding=(0, 5), anchor="w", font=FONTS["ui_small"], borderwidth=0, focusthickness=0, focuscolor=COLORS["accent"])
    style.map("Rail.TButton", background=[("active", COLORS["sidebar_hover"])], foreground=[("active", COLORS["accent_hover"])])
    style.configure("IconEntry.TButton", background=COLORS["surface"], foreground=COLORS["ink_soft"], padding=(8, 8), font=("Segoe UI Symbol", 12), borderwidth=0, focusthickness=0, focuscolor=COLORS["accent"])
    style.map("IconEntry.TButton", background=[("active", COLORS["surface_alt"])], foreground=[("active", COLORS["accent"])])

    style.configure("Chrome.Muted.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=FONTS["ui_small"])
    style.configure("Connection.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=FONTS["ui_bold"], padding=(7, 4))
    style.configure("Connection.Ok.TLabel", background=COLORS["surface_alt"], foreground=COLORS["moss"], font=FONTS["ui_bold"], padding=(7, 4))
    style.configure("Connection.Offline.TLabel", background=COLORS["surface_alt"], foreground=COLORS["muted"], font=FONTS["ui_small"], padding=(9, 5))
    style.configure("Connection.Error.TLabel", background=COLORS["error"], foreground=COLORS["danger_text"], font=FONTS["ui_bold"], padding=(7, 4))
    style.configure("Title.TLabel", background=COLORS["paper"], foreground=COLORS["ink"], font=FONTS["title"])
    style.configure("TabBar.TFrame", background=COLORS["paper"], relief="flat", borderwidth=0)
    style.configure("WorkbenchTab.TButton", background=COLORS["paper"], foreground=COLORS["muted"], padding=(4, 4), font=FONTS["ui"], borderwidth=0, focusthickness=0, focuscolor=COLORS["accent"])
    style.map("WorkbenchTab.TButton", background=[("active", COLORS["paper"])], foreground=[("active", COLORS["accent_text"])])
    style.configure("WorkbenchTabActive.TButton", background=COLORS["paper"], foreground=COLORS["ink"], padding=(4, 4), font=FONTS["ui_bold"], borderwidth=0, focusthickness=0, focuscolor=COLORS["accent"])
    style.map("WorkbenchTabActive.TButton", background=[("active", COLORS["paper"])], foreground=[("active", COLORS["ink"])])
    style.configure("PageIndex.TLabel", background=COLORS["paper"], foreground=COLORS["accent_text"], font=FONTS["mono_small"])
    style.configure("Intro.TLabel", background=COLORS["paper"], foreground=COLORS["muted"], font=FONTS["ui"])
    style.configure("WorkspaceEyebrow.TLabel", background=COLORS["paper"], foreground=COLORS["muted"], font=FONTS["overline"])
    style.configure("PageBody.TLabel", background=COLORS["paper"], foreground=COLORS["ink_soft"], font=FONTS["ui"])
    style.configure("PageMono.TLabel", background=COLORS["paper"], foreground=COLORS["ink"], font=FONTS["mono"])
    style.configure("Eyebrow.TLabel", background=COLORS["surface"], foreground=COLORS["ink_soft"], font=FONTS["overline"])
    style.configure("CardTitle.TLabel", background=COLORS["surface"], foreground=COLORS["ink"], font=FONTS["card_title"])
    style.configure("NoticeTitle.TLabel", background=COLORS["surface_alt"], foreground=COLORS["ink"], font=FONTS["card_title"])
    style.configure("NoticeBody.TLabel", background=COLORS["surface_alt"], foreground=COLORS["ink_soft"], font=FONTS["ui_small"])
    style.configure("CategoryActive.TLabel", background=COLORS["sidebar_active"], foreground=COLORS["accent_text"], font=FONTS["ui_bold"])
    # Input labels keep form controls identifiable without competing with section titles.
    style.configure("InputLabel.TLabel", background=COLORS["surface"], foreground=COLORS["ink"], font=FONTS["ui_bold"])
    style.configure("AccessInputLabel.TLabel", background=COLORS["surface"], foreground=COLORS["ink"], font=FONTS["ui_bold"])
    style.configure("AccessTitle.TLabel", background=COLORS["surface"], foreground=COLORS["ink"], font=FONTS["card_title"])
    style.configure("AccessBody.TLabel", background=COLORS["surface"], foreground=COLORS["ink_soft"], font=FONTS["ui"])
    style.configure("AccessStatus.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=FONTS["ui_small"])
    style.configure("Readiness.TLabel", background=COLORS["paper"], foreground=COLORS["accent_text"], font=FONTS["card_title"])
    style.configure("Body.TLabel", background=COLORS["surface"], foreground=COLORS["ink_soft"], font=FONTS["ui"])
    style.configure("Muted.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=FONTS["ui_small"])
    style.configure("Mono.TLabel", background=COLORS["surface"], foreground=COLORS["ink"], font=FONTS["mono"])
    style.configure("TableEmptyTitle.TLabel", background=COLORS["surface_alt"], foreground=COLORS["ink"], font=FONTS["ui_bold"])
    style.configure("TableEmptyBody.TLabel", background=COLORS["surface_alt"], foreground=COLORS["muted"], font=FONTS["ui_small"])
    style.configure("WorkflowHeading.TLabel", background=COLORS["paper"], foreground=COLORS["ink"], font=FONTS["ui_bold"])
    style.configure("WorkflowTitle.TLabel", background=COLORS["paper"], foreground=COLORS["ink"], font=FONTS["ui_bold"])
    style.configure("WorkflowBody.TLabel", background=COLORS["paper"], foreground=COLORS["muted"], font=FONTS["ui_small"])
    style.configure("WorkflowIndex.TLabel", background=COLORS["paper"], foreground=COLORS["accent_text"], font=FONTS["mono_small"])
    style.configure("WorkflowAction.TButton", background=COLORS["paper"], foreground=COLORS["accent_text"], anchor="w", padding=(0, 5), font=FONTS["ui_bold"], borderwidth=0, focusthickness=1, focuscolor=COLORS["accent_text"])
    style.map("WorkflowAction.TButton", background=[("active", COLORS["line"])], foreground=[("active", COLORS["white"])])
    style.configure("QualityBlocker.TLabel", background=COLORS["surface"], foreground=COLORS["danger_text"], font=FONTS["quality_status"])
    style.configure("QualityWarning.TLabel", background=COLORS["surface"], foreground=COLORS["warning_text"], font=FONTS["quality_status"])
    style.configure("QualitySuccess.TLabel", background=COLORS["surface"], foreground=COLORS["moss"], font=FONTS["quality_status"])
    style.configure("SettingsError.TLabel", background=COLORS["error"], foreground=COLORS["danger_text"], font=FONTS["ui_small"])

    style.configure("Primary.TButton", background=COLORS["accent"], foreground=COLORS["white"], padding=(14, 9), font=FONTS["ui_bold"], borderwidth=0, focusthickness=1, focuscolor=COLORS["accent_text"])
    style.map("Primary.TButton", background=[("disabled", COLORS["surface_alt"]), ("active", COLORS["accent_hover"])], foreground=[("disabled", COLORS["muted"]), ("active", COLORS["white"])])
    style.configure("Suggestion.TButton", background=COLORS["surface_alt"], foreground=COLORS["ink_soft"], padding=(12, 8), font=FONTS["ui_small"], borderwidth=0, relief="flat", focusthickness=0, focuscolor=COLORS["accent_text"])
    style.map("Suggestion.TButton", background=[("disabled", COLORS["surface_alt"]), ("active", COLORS["sidebar_hover"])], foreground=[("disabled", COLORS["muted"]), ("active", COLORS["ink"])])
    style.configure("Quiet.TButton", background=COLORS["surface_alt"], foreground=COLORS["ink"], padding=(12, 8), font=FONTS["ui"], borderwidth=0, focusthickness=1, focuscolor=COLORS["accent_text"])
    style.map("Quiet.TButton", background=[("disabled", COLORS["surface_alt"]), ("active", COLORS["line"])], foreground=[("disabled", COLORS["muted"]), ("active", COLORS["ink"])])
    style.configure("AccessQuiet.TButton", background=COLORS["surface"], foreground=COLORS["ink"], padding=(12, 8), font=FONTS["ui"], borderwidth=0, focusthickness=1, focuscolor=COLORS["accent_text"])
    style.map("AccessQuiet.TButton", background=[("disabled", COLORS["surface"]), ("active", COLORS["line"])], foreground=[("disabled", COLORS["muted"]), ("active", COLORS["ink"])])
    style.configure("Toolbar.TButton", background=COLORS["paper"], foreground=COLORS["ink_soft"], padding=(8, 5), font=FONTS["ui"], borderwidth=0, focusthickness=1, focuscolor=COLORS["accent_text"])
    style.map("Toolbar.TButton", background=[("active", COLORS["surface_alt"])], foreground=[("disabled", COLORS["muted"]), ("active", COLORS["ink"])])

    style.configure("ProjectTree.Treeview", background=COLORS["surface"], fieldbackground=COLORS["surface"], foreground=COLORS["ink"], rowheight=42, font=FONTS["ui"], borderwidth=0, relief="flat", bordercolor=COLORS["line"], lightcolor=COLORS["surface"], darkcolor=COLORS["line"])
    style.map("ProjectTree.Treeview", background=[("selected", COLORS["sidebar_active"])], foreground=[("selected", COLORS["accent_text"])])
    style.configure("ProjectTree.Treeview.Heading", background=COLORS["surface_alt"], foreground=COLORS["ink_soft"], font=FONTS["ui_bold"], padding=(10, 9), relief="flat", borderwidth=0)
    style.map("ProjectTree.Treeview.Heading", background=[("active", COLORS["line"])])
    style.configure("WizardStep.TLabel", background=COLORS["surface"], foreground=COLORS["accent_text"], font=FONTS["overline"])
    style.configure("WizardTitle.TLabel", background=COLORS["surface"], foreground=COLORS["ink"], font=FONTS["wizard_title"])
    style.configure("WizardBody.TLabel", background=COLORS["surface"], foreground=COLORS["ink_soft"], font=FONTS["ui"])
    style.configure("WizardMuted.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=FONTS["ui_small"])

    style.configure("Status.TFrame", background=COLORS["surface"])
    style.configure("Status.TLabel", background=COLORS["surface"], foreground=COLORS["sidebar_muted"], font=FONTS["mono_small"])
    # The persistent synthetic-data scope is informational, so reserve gold for real warnings.
    style.configure("Status.Scope.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=FONTS["ui_small"])
    style.configure("Status.TSeparator", background=COLORS["line"])
    style.configure("ProjectTitle.TLabel", background=COLORS["paper"], foreground=COLORS["ink"], font=FONTS["project_title"])
