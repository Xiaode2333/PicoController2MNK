"""Input events and output state choices survive editing and persistence."""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tools.pico2mnk_configurator import config_model as cm
from tools.pico2mnk_configurator.app import (
    ActionDialog, App, OUTPUT_BEHAVIOR_LABELS, OUTPUT_BEHAVIOR_MODES,
    MACRO_BINDING_TRIGGER_LABELS, config_uses_toggle_options, format_action_for_config,
)


class ActionModelTests(unittest.TestCase):
    def test_all_modes_roundtrip_in_json_and_binary(self):
        config = cm.ConfigPayload()
        for index, mode in enumerate(OUTPUT_BEHAVIOR_MODES):
            config.bindings[0][index][cm.GESTURE_HOLD] = cm.Action(
                type=cm.ACTION_MODIFIER_KEY, param1=cm.MOD_LEFTALT, trigger_mode=mode,
                value=cm.action_behavior_value(cm.INPUT_RELEASED, 125), duration_ms=1)
        for mode in range(4):
            config.bindings[1][mode][cm.GESTURE_HOLD] = cm.Action(
                type=cm.ACTION_MACRO, trigger_mode=cm.MACRO_TRIGGER_OVERRIDE | mode, duration_ms=1)
        payload = cm.encode_payload(config)
        self.assertEqual(cm.encode_payload(cm.decode_payload(payload)), payload)
        self.assertEqual(cm.config_from_json_document(cm.config_to_json_document(config)), config)

    def test_old_firmware_rejects_new_input_and_output_options(self):
        actions = [cm.Action(type=cm.ACTION_KEY, trigger_mode=mode) for mode in OUTPUT_BEHAVIOR_MODES[1:]]
        actions += [cm.Action(type=cm.ACTION_KEY, value=cm.action_behavior_value(cm.INPUT_RELEASED)),
                    cm.Action(type=cm.ACTION_MACRO, trigger_mode=cm.MACRO_TRIGGER_OVERRIDE),
                    cm.Action(type=cm.ACTION_STOP_ALL)]
        for action in actions:
            for version in ((2, 4, 0), (2, 5, 0)):
                with self.subTest(action=action, version=version):
                    app = object.__new__(App)
                    app.config = cm.ConfigPayload()
                    app.config.bindings[0][cm.SRC_A][cm.GESTURE_HOLD] = action
                    app._commit_local_editors = lambda: None
                    app.connection = SimpleNamespace(identity=SimpleNamespace(
                        firmware_major=version[0], firmware_minor=version[1], firmware_patch=version[2]))
                    if version < (2, 5, 0):
                        with self.assertRaisesRegex(RuntimeError, "2.5.0"):
                            app._collect_local_config()
                    else:
                        self.assertEqual(len(app._collect_local_config()), cm.PAYLOAD_SIZE)

    def test_legacy_macro_byte_still_inherits_slot_default(self):
        config = cm.ConfigPayload()
        config.macros[0].trigger_mode = cm.MACRO_TRIGGER_WHILE_HELD
        for legacy in range(4):
            action = cm.Action(type=cm.ACTION_MACRO, trigger_mode=legacy)
            self.assertEqual(cm.effective_macro_trigger(config, action), cm.MACRO_TRIGGER_WHILE_HELD)
        config.bindings[0][0][0] = action
        self.assertFalse(config_uses_toggle_options(config))

    def test_overview_describes_actual_macro_and_output_mode(self):
        config = cm.ConfigPayload()
        action = cm.Action(type=cm.ACTION_MACRO, trigger_mode=cm.MACRO_TRIGGER_OVERRIDE | cm.MACRO_TRIGGER_TOGGLE)
        self.assertIn("Toggle", format_action_for_config(config, action))
        self.assertIn("Toggle", cm.format_action(cm.Action(type=cm.ACTION_KEY, param1=4, trigger_mode=cm.ACTION_MODE_TOGGLE)))

    def test_invalid_behavior_combinations_rejected(self):
        for action in (cm.Action(type=cm.ACTION_KEY, trigger_mode=0x84),
                       cm.Action(type=cm.ACTION_MOUSE_MODE_SWAP, trigger_mode=cm.ACTION_MODE_TOGGLE),
                       cm.Action(type=cm.ACTION_MACRO, value=cm.action_behavior_value(cm.INPUT_RELEASED))):
            config = cm.ConfigPayload()
            config.bindings[0][0][0] = action
            with self.assertRaises(ValueError):
                cm.encode_payload(config)


class ActionDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(str(exc))
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def dialog(self, initial, **kwargs):
        with patch.object(ActionDialog, "wait_visibility"):
            dialog = ActionDialog(self.root, "Test", initial, ["Macro"] * 8, **kwargs)
        self.addCleanup(lambda: dialog.destroy() if dialog.winfo_exists() else None)
        return dialog

    def test_every_output_mode_can_be_selected_and_reopened(self):
        for mode, label in zip(OUTPUT_BEHAVIOR_MODES, OUTPUT_BEHAVIOR_LABELS):
            for action_type in cm.TOGGLE_ACTION_TYPES:
                with self.subTest(mode=mode, type=action_type):
                    dialog = self.dialog(cm.Action(type=action_type, param1=4, duration_ms=1), edit_hold_timing=True)
                    dialog.behavior_var.set(label)
                    dialog._ok()
                    self.assertEqual(dialog.result.trigger_mode, mode)
                    reopened = self.dialog(dialog.result, edit_hold_timing=True)
                    self.assertEqual(reopened.behavior_var.get(), label)

    def test_combo_input_events_preserve_output_and_delay(self):
        for event in range(4):
            dialog = self.dialog(cm.Action(type=cm.ACTION_MODIFIER_KEY, param1=cm.MOD_LEFTALT), edit_combo_delay=True)
            dialog.input_event_var.set(cm.INPUT_EVENT_NAMES[event])
            dialog.click_ms_var.set("125")
            dialog._ok()
            self.assertEqual(cm.action_input_event(dialog.result), event)
            self.assertEqual(dialog.result.param1, cm.MOD_LEFTALT)

    def test_macro_playback_can_be_overridden_or_inherited(self):
        for index, label in enumerate(MACRO_BINDING_TRIGGER_LABELS):
            dialog = self.dialog(cm.Action(type=cm.ACTION_MACRO), edit_combo_delay=True)
            dialog.macro_trigger_var.set(label)
            dialog._ok()
            expected = cm.MACRO_TRIGGER_OVERRIDE | (index - 1) if index else 0
            self.assertEqual(dialog.result.trigger_mode, expected)
            self.assertEqual(self.dialog(dialog.result).macro_trigger_var.get(), label)

    def test_switching_action_types_restores_visible_behavior_controls(self):
        dialog = self.dialog(cm.Action(), edit_combo_delay=True)
        for kind in (cm.ACTION_MACRO, cm.ACTION_STOP_ALL, cm.ACTION_KEY, cm.ACTION_NONE, cm.ACTION_MOUSE_BUTTON):
            dialog.type_var.set(str(kind))
            dialog._refresh()

    def test_invalid_click_settings_are_not_saved(self):
        dialog = self.dialog(cm.Action(type=cm.ACTION_KEY), edit_combo_delay=True)
        dialog.behavior_var.set(OUTPUT_BEHAVIOR_LABELS[2])
        for value in ("abc", "-1", "4096"):
            dialog.click_ms_var.set(value)
            with patch("tools.pico2mnk_configurator.app.messagebox.showerror") as error:
                dialog._ok()
                error.assert_called_once()
                self.assertIsNone(dialog.result)
        dialog.click_ms_var.set("20")
        dialog.input_event_var.set(cm.INPUT_EVENT_NAMES[cm.INPUT_CLICK])
        dialog.combo_delay_var.set("100")
        with patch("tools.pico2mnk_configurator.app.messagebox.showerror") as error:
            dialog._ok()
            error.assert_called_once()
            self.assertIsNone(dialog.result)
