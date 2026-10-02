"""Regression tests for choosing and persisting direct-binding activation modes."""

import copy
import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch

from tools.pico2mnk_configurator import config_model as cm
from tools.pico2mnk_configurator.app import (
    ActionDialog, BindingsTab, HOLD_TIMING_LABELS, build_profile_macro_rows,
)


class BindingTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display unavailable: {exc}") from exc
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.app = SimpleNamespace(config=cm.ConfigPayload(), status_var=tk.StringVar())
        self.tab = BindingsTab(ttk.Notebook(self.root), self.app)
        self.addCleanup(self.tab.master.destroy)

    def dialog(self, initial, **kwargs):
        # Hidden test windows never enter the interactive visibility wait.
        with patch.object(ActionDialog, "wait_visibility"):
            dialog = ActionDialog(self.root, "Test binding", initial, ["Macro"] * 8, **kwargs)
        self.addCleanup(lambda: dialog.destroy() if dialog.winfo_exists() else None)
        return dialog

    def binding(self):
        return self.app.config.bindings[0][cm.SRC_A][cm.GESTURE_HOLD]

    def click(self, column, result):
        event = SimpleNamespace(x=10, y=10)
        with patch.object(self.tab.tree, "identify_row", return_value=str(cm.SRC_A)), \
             patch.object(self.tab.tree, "identify_column", return_value=column), \
             patch("tools.pico2mnk_configurator.app.ActionDialog") as factory, \
             patch.object(self.tab, "wait_window"):
            factory.return_value.result = result
            self.tab._edit(event)
            return factory.call_args

    def test_table_splits_immediate_and_delayed_bindings(self):
        self.assertEqual(tuple(self.tab.tree["columns"]),
                         ("input", "tap", "while_pressed", "hold", "double"))
        for duration, expected in ((1, ("Key Q", "None")),
                                   (0, ("None", "After 200 ms: Key Q")),
                                   (750, ("None", "After 750 ms: Key Q"))):
            with self.subTest(duration=duration):
                self.app.config.bindings[0][cm.SRC_A][cm.GESTURE_HOLD] = cm.Action(
                    type=cm.ACTION_KEY, param1=cm.HID_NAME_TO_KEY["Q"], duration_ms=duration)
                self.tab.refresh()
                values = self.tab.tree.item(str(cm.SRC_A), "values")
                self.assertEqual(values[2:4], expected)

    def test_default_hold_display_tracks_global_threshold(self):
        self.app.config.settings.hold_threshold_ms = 450
        self.binding().duration_ms = 0
        self.tab.refresh()
        self.assertIn("After 450 ms:", self.tab.tree.item(str(cm.SRC_A), "values")[3])

    def test_both_columns_enable_timing_editor_and_seed_selected_mode(self):
        self.binding().duration_ms = 750
        for column, duration in (("#3", 1), ("#4", 750)):
            args = self.click(column, None)
            self.assertTrue(args.kwargs["edit_hold_timing"])
            self.assertEqual(args.args[2].duration_ms, duration)
        self.assertEqual(self.binding().duration_ms, 750)  # Cancel preserves the config.
        self.binding().duration_ms = 1
        self.assertEqual(self.click("#4", None).args[2].duration_ms, 0)

    def test_non_action_column_does_not_open_editor(self):
        self.assertIsNone(self.click("#1", None))

    def test_double_column_still_edits_double_tap(self):
        action = cm.Action(type=cm.ACTION_KEY, param1=cm.HID_NAME_TO_KEY["E"])
        args = self.click("#5", action)
        self.assertFalse(args.kwargs["edit_hold_timing"])
        self.assertEqual(self.app.config.bindings[0][cm.SRC_A][cm.GESTURE_DOUBLE], action)

    def test_saved_selection_replaces_old_mode_and_survives_serialization(self):
        original_tap = copy.deepcopy(self.app.config.bindings[0][cm.SRC_A][cm.GESTURE_TAP])
        for duration in (0, 1, 650, 1):
            result = cm.Action(type=cm.ACTION_KEY, param1=4, duration_ms=duration)
            self.click("#3", result)
            self.assertEqual(self.binding(), result)
            binary = cm.decode_payload(cm.encode_payload(self.app.config))
            self.assertEqual(binary.bindings[0][cm.SRC_A][cm.GESTURE_HOLD], result)
            self.assertEqual(self.app.config.bindings[0][cm.SRC_A][cm.GESTURE_TAP], original_tap)

    def test_dialog_reads_existing_mode_and_preserves_custom_delay(self):
        for duration, mode in ((1, 0), (0, 1), (900, 2)):
            with self.subTest(duration=duration):
                dialog = self.dialog(cm.Action(type=cm.ACTION_KEY, param1=4, duration_ms=duration),
                                     edit_hold_timing=True)
                self.assertEqual(dialog.hold_timing_var.get(), HOLD_TIMING_LABELS[mode])
                self.assertEqual(str(dialog.hold_delay_entry["state"]),
                                 "normal" if mode == 2 else "disabled")
                dialog._ok()
                self.assertEqual(dialog.result.duration_ms, duration)

    def test_dialog_can_switch_activation_mode_for_keys_mouse_and_macros(self):
        for action_type in (cm.ACTION_KEY, cm.ACTION_MODIFIER_KEY,
                            cm.ACTION_MOUSE_BUTTON, cm.ACTION_WHEEL_UP_TURBO, cm.ACTION_MACRO):
            for mode, duration in ((0, 1), (1, 0), (2, 600)):
                with self.subTest(action=action_type, mode=mode):
                    dialog = self.dialog(cm.Action(type=action_type, duration_ms=1),
                                         edit_hold_timing=True)
                    dialog.hold_timing_var.set(HOLD_TIMING_LABELS[mode])
                    dialog.hold_delay_var.set("600")
                    dialog._ok()
                    self.assertEqual(dialog.result.type, action_type)
                    self.assertEqual(dialog.result.duration_ms, duration)

    def test_invalid_custom_delays_leave_dialog_and_config_unchanged(self):
        dialog = self.dialog(cm.Action(type=cm.ACTION_KEY, param1=4), edit_hold_timing=True)
        dialog.hold_timing_var.set(HOLD_TIMING_LABELS[2])
        for invalid in ("", "abc", "2.5", "-1", "0", "1", "65536"):
            with self.subTest(invalid=invalid), \
                 patch("tools.pico2mnk_configurator.app.messagebox.showerror") as error:
                dialog.hold_delay_var.set(invalid)
                dialog._ok()
                error.assert_called_once()
                self.assertIsNone(dialog.result)
                self.assertTrue(dialog.winfo_exists())

    def test_custom_delay_limits_are_accepted(self):
        for duration in (2, 65535):
            dialog = self.dialog(cm.Action(type=cm.ACTION_KEY, param1=4), edit_hold_timing=True)
            dialog.hold_timing_var.set(HOLD_TIMING_LABELS[2])
            dialog.hold_delay_var.set(str(duration))
            dialog._ok()
            self.assertEqual(dialog.result.duration_ms, duration)

    def test_clear_action_ignores_invalid_delay(self):
        dialog = self.dialog(cm.Action(duration_ms=500), edit_hold_timing=True)
        dialog.hold_delay_var.set("invalid")
        dialog._ok()
        self.assertEqual(dialog.result, cm.Action())

    def test_non_hold_editor_has_no_activation_controls(self):
        dialog = self.dialog(cm.Action(type=cm.ACTION_KEY, param1=4))
        self.assertFalse(dialog.edit_hold_timing)
        self.assertFalse(hasattr(dialog, "hold_delay_entry"))
        dialog._ok()
        self.assertEqual(dialog.result.duration_ms, 0)

    def test_macro_overview_reports_while_pressed_mode(self):
        self.app.config.bindings[0][cm.SRC_A][cm.GESTURE_HOLD] = cm.Action(
            type=cm.ACTION_MACRO, param1=0, duration_ms=1)
        rows = build_profile_macro_rows(self.app.config, 0)
        self.assertIn("A (While pressed)", rows[0][3])


if __name__ == "__main__":
    unittest.main()
