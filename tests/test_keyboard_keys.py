"""Keyboard catalogue coverage, editor preservation and config compatibility."""
import tkinter as tk
import unittest
from unittest.mock import patch

from tools.pico2mnk_configurator import config_model as cm
from tools.pico2mnk_configurator.app import ActionDialog, MacroStepDialog


class KeyboardCatalogueTests(unittest.TestCase):
    def test_assigned_keyboard_usages_are_complete_and_unambiguous(self):
        # USB HID Keyboard/Keypad page, excluding errors, reserved and modifiers.
        expected = {0} | set(range(0x04, 0xA5)) | set(range(0xB0, 0xDE))
        self.assertEqual(set(cm.HID_KEY_NAMES), expected)
        self.assertEqual(len(set(cm.HID_KEY_NAMES.values())), len(expected))
        self.assertEqual(cm.HID_NAME_TO_KEY["Page Up"], 0x4B)
        self.assertEqual(cm.HID_NAME_TO_KEY["Page Down"], 0x4E)
        self.assertEqual(cm.HID_NAME_TO_KEY["Numpad 0"], 0x62)
        self.assertEqual(cm.HID_NAME_TO_KEY["F24"], 0x73)

    def test_extended_keys_survive_binary_json_and_display(self):
        config = cm.ConfigPayload()
        codes = [code for code in cm.HID_KEY_NAMES if code]
        for index, code in enumerate(codes):
            profile, remainder = divmod(index, cm.SOURCE_COUNT * cm.GESTURE_COUNT)
            source, gesture = divmod(remainder, cm.GESTURE_COUNT)
            config.bindings[profile][source][gesture] = cm.Action(
                type=cm.ACTION_KEY, param1=code)
            self.assertIn(cm.HID_KEY_NAMES[code], cm.format_action(
                config.bindings[profile][source][gesture]))
        config.combos[0] = cm.Combo(profile_mask=7, source_mask=3,
            action=cm.Action(type=cm.ACTION_TWO_KEYS, param1=0x4B, param2=0xDD))
        config.macros[0] = cm.Macro(step_count=1, steps=[cm.MacroStep(
            type=cm.MACRO_STEP_KEYBOARD, modifier=cm.MOD_RIGHTCTRL,
            keys=(0x46, 0x4B, 0x4E, 0x58, 0x73, 0xDD))])
        decoded = cm.decode_payload(cm.encode_payload(config))
        self.assertEqual(decoded.bindings, config.bindings)
        self.assertEqual(decoded.combos, config.combos)
        self.assertEqual(decoded.macros, config.macros)
        self.assertEqual(cm.config_from_json_document(
            cm.config_to_json_document(config)), config)


class KeyboardEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_binding_editors_offer_and_preserve_extended_keys(self):
        for action in (
            cm.Action(type=cm.ACTION_KEY, param1=0x4B),
            cm.Action(type=cm.ACTION_TWO_KEYS, param1=0x4B, param2=0x4E),
            cm.Action(type=cm.ACTION_MODIFIER_KEY, param1=cm.MOD_LEFTCTRL, param2=0x4A),
            cm.Action(type=cm.ACTION_MOUSE_MODE_TOGGLE_KEY, param1=0x73),
        ):
            with self.subTest(action=action), patch.object(ActionDialog, "wait_visibility"):
                dialog = ActionDialog(self.root, "Test keys", action, ["Macro"] * 8)
                try:
                    self.assertIn("0x4B Page Up", dialog.key_names)
                    self.assertIn("0x4E Page Down", dialog.key_names)
                    self.assertIn("0xDD Numpad Hexadecimal", dialog.key_names)
                    dialog._ok()
                    self.assertEqual(dialog.result.param1, action.param1)
                    self.assertEqual(dialog.result.param2, action.param2)
                finally:
                    if dialog.winfo_exists():
                        dialog.destroy()

    def test_macro_editor_preserves_six_extended_keys_and_modifiers(self):
        step = cm.MacroStep(type=cm.MACRO_STEP_KEYBOARD,
            modifier=cm.MOD_LEFTALT, keys=(0x46, 0x4B, 0x4E, 0x58, 0x73, 0xDD))
        with patch.object(MacroStepDialog, "wait_visibility"):
            dialog = MacroStepDialog(self.root, step)
        try:
            self.assertIn("0x4B Page Up", dialog.key_names)
            self.assertIn("0x4E Page Down", dialog.key_names)
            dialog._ok()
            self.assertEqual(dialog.result, step)
        finally:
            if dialog.winfo_exists():
                dialog.destroy()
