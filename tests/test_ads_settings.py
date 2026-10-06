import copy
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.pico2mnk_configurator import config_model as cm
from tools.pico2mnk_configurator.app import App, StickSettingsDialog, build_profile_stick_rows


class ADSConfigTests(unittest.TestCase):
    def test_all_aim_inputs_survive_binary_and_json_round_trips(self):
        for source in range(cm.SOURCE_COUNT):
            with self.subTest(source=source):
                config = cm.ConfigPayload()
                config.settings.profile2_aim_source = source
                config.macros[6].name = "Aim header metadata"
                config.macros[6].steps = [cm.MacroStep(duration_ms=75)]
                config.macros[6].step_count = 1
                payload = cm.encode_payload(config)
                self.assertEqual(len(payload), cm.PAYLOAD_SIZE)
                for restored in (cm.decode_payload(payload), cm.config_from_json_document(
                        cm.config_to_json_document(config))):
                    self.assertEqual(restored.settings.profile2_aim_source, source)
                    self.assertEqual(restored.macros[6], config.macros[6])
                    self.assertEqual(restored.settings.mouse_mode_sensitivity, [100, 50])

    def test_legacy_binary_and_json_default_to_rb(self):
        config = cm.ConfigPayload()
        payload = bytearray(cm.encode_payload(config))
        macro_offset = (cm._SETTINGS_STRUCT.size + cm.PROFILE_COUNT * cm.SOURCE_COUNT
                        * cm.GESTURE_COUNT * cm._ACTION_STRUCT.size
                        + cm.COMBO_MAX * cm._COMBO_STRUCT.size)
        macro_size = cm._MACRO_HEAD_STRUCT.size + cm.MACRO_STEP_MAX * cm._MACRO_STEP_STRUCT.size
        offset = macro_offset + 6 * macro_size + cm.MACRO_NAME_MAX + 2
        for value in (0, 0xFFFE):
            payload[offset:offset + 2] = value.to_bytes(2, "little")
            self.assertEqual(cm.decode_payload(bytes(payload)).settings.profile2_aim_source, cm.SRC_RB)
        document = cm.config_to_json_document(config)
        del document["config"]["settings"]["profile2_aim_source"]
        self.assertEqual(cm.config_from_json_document(document).settings.profile2_aim_source, cm.SRC_RB)
        payload[offset:offset + 2] = (cm.PROFILE2_AIM_SOURCE_TAG | cm.SOURCE_COUNT).to_bytes(2, "little")
        with self.assertRaisesRegex(ValueError, "profile2_aim_source"):
            cm.decode_payload(bytes(payload))

    def test_invalid_aim_input_is_rejected_before_saving(self):
        for source in (-1, cm.SOURCE_COUNT, 1.5, True):
            config = cm.ConfigPayload()
            config.settings.profile2_aim_source = source
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "profile2_aim_source"):
                cm.encode_payload(config)

    def test_overview_names_selected_aim_input(self):
        config = cm.ConfigPayload()
        config.settings.profile2_aim_source = cm.SRC_LT
        rows = dict(build_profile_stick_rows(config, 1))
        self.assertEqual(rows["Aim / ADS input"], "LT")
        self.assertIn("3750", rows["Right stick while Aim (ADS)"])

    def test_old_firmware_cannot_silently_ignore_custom_aim_input(self):
        for source, version, accepted in (
            (cm.SRC_RB, (2, 3, 0), True),
            (cm.SRC_LT, (2, 3, 0), False),
            (cm.SRC_LT, (2, 4, 0), True),
        ):
            with self.subTest(source=source, version=version):
                app = object.__new__(App)
                app.config = cm.ConfigPayload()
                app.config.settings.profile2_aim_source = source
                app._commit_local_editors = lambda: None
                app.connection = SimpleNamespace(identity=SimpleNamespace(
                    firmware_major=version[0], firmware_minor=version[1], firmware_patch=version[2]))
                if accepted:
                    self.assertEqual(len(app._collect_local_config()), cm.PAYLOAD_SIZE)
                else:
                    with self.assertRaisesRegex(RuntimeError, "Aim / ADS input requires firmware 2.4.0"):
                        app._collect_local_config()


class ADSDialogTests(unittest.TestCase):
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

    def dialog(self, config, profile=1):
        with patch.object(StickSettingsDialog, "wait_visibility"):
            dialog = StickSettingsDialog(self.root, config, profile)
        self.addCleanup(lambda: dialog.destroy() if dialog.winfo_exists() else None)
        return dialog

    def test_changing_aim_to_lt_preserves_speed_values_and_other_bindings(self):
        config = cm.ConfigPayload()
        before = copy.deepcopy(config)
        dialog = self.dialog(config)
        self.assertEqual(dialog.aim_source_var.get(), "RB")
        dialog.aim_source_var.set("LT")
        dialog._ok()
        self.assertEqual(dialog.result.profile2_aim_source, cm.SRC_LT)
        self.assertEqual(dialog.result.profile2_rb_speed_x, before.settings.profile2_rb_speed_x)
        self.assertEqual(config, before)  # Only installing the result updates the real config.
        reopened = self.dialog(cm.ConfigPayload(settings=dialog.result))
        self.assertEqual(reopened.aim_source_var.get(), "LT")

    def test_cancel_preserves_original_aim_input(self):
        config = cm.ConfigPayload()
        dialog = self.dialog(config)
        dialog.aim_source_var.set("LT")
        dialog.destroy()
        self.assertIsNone(dialog.result)
        self.assertEqual(config.settings.profile2_aim_source, cm.SRC_RB)

    def test_other_profiles_preserve_profile_2_aim_input(self):
        config = cm.ConfigPayload()
        config.settings.profile2_aim_source = cm.SRC_LT
        for profile in (0, 2):
            dialog = self.dialog(config, profile)
            self.assertFalse(hasattr(dialog, "aim_source_var"))
            dialog._ok()
            self.assertEqual(dialog.result.profile2_aim_source, cm.SRC_LT)


if __name__ == "__main__":
    unittest.main()
