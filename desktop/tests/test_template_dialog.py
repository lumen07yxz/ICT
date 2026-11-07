"""Readable contract dialogs keep long scientific metadata accessible and inert."""

import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import font as tkfont
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ict_desktop import main_window
from ict_desktop.api import PipelineFieldContract, PipelineTemplateContract, TemplateResourceLimits
from ict_desktop.ui_theme import COLORS, FONTS, configure_theme


class TemplateDialogTests(unittest.TestCase):
    def setUp(self):
        self.dialog_class = getattr(main_window, "TemplateContractDialog", None)
        self.assertIsNotNone(self.dialog_class, "the native contract reader has not been implemented")
        self.root = tk.Tk()
        self.root.withdraw()
        configure_theme(self.root)
        field = PipelineFieldContract("string", True, None, None, "dataset-synthetic-v1")
        self.contract = PipelineTemplateContract(
            template_id="research-smoke-v1", version="1.0.0", manifest_sha256="c" * 64,
            executor="synthetic_smoke_v1", dataset_version="dataset-synthetic-v1",
            permission_scope="synthetic_dataset_manifest_read_only",
            resource_limits=TemplateResourceLimits(1, 25, 30), inputs={"dataset_version": field},
            parameters={"sample_limit": PipelineFieldContract("integer", True, 1, 100, None)},
            outputs={"synthetic_only": PipelineFieldContract("boolean", True, None, None, True),
                     "research_ready": PipelineFieldContract("boolean", True, None, None, False)},
            states=("queued", "running", "succeeded", "failed"),
            error_codes=("DATA_QUALITY_BLOCKED", "PROPOSAL_CONFIG_MISMATCH", "QUEUE_UNAVAILABLE", "WORKER_EXECUTION_FAILED"),
        )

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    def test_contract_text_is_selectable_but_cannot_be_edited(self):
        reader = self.dialog_class(self.root, self.contract)
        self.root.update_idletasks()
        text = reader.body.get("1.0", "end-1c")
        reader.body.insert("1.0", "modified")
        reader.body.delete("1.0", "end")
        self.assertEqual(reader.body.get("1.0", "end-1c"), text)
        reader.body.tag_add("sel", "1.0", "1.4")
        self.assertTrue(reader.body.tag_ranges("sel"))
        for value in ("c" * 64, "sample_limit", "范围 1 到 100", "synthetic_only=true", "research_ready=false", "WORKER_EXECUTION_FAILED"):
            self.assertIn(value, text)
        self.assertEqual(reader.body.cget("background"), COLORS["surface"])

    def test_contract_section_headers_use_the_shared_typographic_scale(self):
        reader = self.dialog_class(self.root, self.contract)
        actual = tkfont.Font(root=self.root, font=reader.body.tag_cget("section", "font")).actual()
        expected = FONTS["contract_section"]

        self.assertEqual(actual["family"], expected[0])
        self.assertEqual(abs(int(actual["size"])), expected[1])
        self.assertEqual(actual["weight"], "bold")

    def test_short_screen_keeps_close_action_and_scrollable_content(self):
        # A transient child of a withdrawn root is not mapped, so its footer is 1px.
        # Map this geometry test's parent before measuring the visible widget tree.
        self.root.geometry("800x600+0+0")
        self.root.deiconify()
        self.root.update_idletasks()
        with patch.object(tk.Toplevel, "winfo_screenwidth", return_value=800), patch.object(tk.Toplevel, "winfo_screenheight", return_value=600):
            reader = self.dialog_class(self.root, self.contract)
        self.root.update_idletasks()
        self.assertLessEqual(reader.dialog.winfo_width(), 800 - 64)
        self.assertLessEqual(reader.dialog.winfo_height(), 600 - 100)
        action_bottom = reader.close_button.winfo_rooty() - reader.dialog.winfo_rooty() + reader.close_button.winfo_height()
        self.assertLessEqual(action_bottom, reader.dialog.winfo_height())
        self.assertTrue(reader.dialog.bind("<Escape>"), "Escape must close the reading window")
        reader.body.yview_moveto(1)
        self.assertGreater(reader.body.yview()[0], 0, "long metadata must remain reachable on short displays")

    def test_close_releases_modal_grab_and_can_be_called_twice(self):
        reader = self.dialog_class(self.root, self.contract)
        self.root.update_idletasks()
        reader.close()
        reader.close()
        self.assertFalse(reader.dialog.winfo_exists())
        self.assertIsNone(self.root.grab_current())


if __name__ == "__main__":
    unittest.main()
