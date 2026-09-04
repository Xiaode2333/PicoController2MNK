"""Smoke tests for the desktop-side config model.

Run from the project root:
    poetry run python -m unittest discover -s tests
"""

import struct
import unittest

from tools.pico2mnk_configurator import config_model as cm


class ConfigModelTests(unittest.TestCase):
    def test_action_size(self):
        self.assertEqual(struct.calcsize("<BBBBhH"), 8)

    def test_payload_round_trip(self):
        config = cm.ConfigPayload()
        config.settings.active_profile = 2
        config.settings.virtual_dpi = 2400
        config.bindings[1][cm.SRC_DPAD_UP][cm.GESTURE_HOLD] = cm.Action(
            type=cm.ACTION_KEY, param1=cm.HID_NAME_TO_KEY["Z"]
        )
        data = cm.encode_payload(config)
        self.assertEqual(len(data), cm.PAYLOAD_SIZE)
        macro_offset = (
            cm._SETTINGS_STRUCT.size
            + cm.PROFILE_COUNT * cm.SOURCE_COUNT * cm.GESTURE_COUNT * cm._ACTION_STRUCT.size
            + cm.COMBO_MAX * cm._COMBO_STRUCT.size
        )
        reserved_offset = macro_offset + cm.MACRO_NAME_MAX + 2
        self.assertEqual(
            int.from_bytes(data[reserved_offset : reserved_offset + 2], "little"),
            2400,
        )
        decoded = cm.decode_payload(data)
        self.assertEqual(decoded.settings.active_profile, 2)
        self.assertEqual(decoded.settings.virtual_dpi, 2400)
        self.assertEqual(
            decoded.bindings[1][cm.SRC_DPAD_UP][cm.GESTURE_HOLD].type,
            cm.ACTION_KEY,
        )

    def test_advanced_profile_2_stick_settings_round_trip(self):
        config = cm.ConfigPayload()
        config.settings.profile2_accel_enabled = 0
        config.settings.profile2_outer_threshold_percent = 91
        config.settings.profile2_rb_speed_x = 3210
        config.settings.profile2_rb_speed_y = 1987
        config.settings.profile2_no_rb_ramp_ms = 444
        config.settings.profile2_no_rb_extra_x = 5555
        config.settings.profile2_rb_delay_ms = 222
        config.settings.profile2_rb_ramp_ms = 888
        config.settings.profile2_rb_extra_x = 777
        config.settings.profile2_rb_extra_y = 666

        decoded = cm.decode_payload(cm.encode_payload(config))

        self.assertEqual(decoded.settings.advanced_stick_version, 1)
        self.assertEqual(decoded.settings.profile2_accel_enabled, 0)
        self.assertEqual(decoded.settings.profile2_outer_threshold_percent, 91)
        self.assertEqual(decoded.settings.profile2_rb_speed_x, 3210)
        self.assertEqual(decoded.settings.profile2_rb_speed_y, 1987)
        self.assertEqual(decoded.settings.profile2_no_rb_ramp_ms, 444)
        self.assertEqual(decoded.settings.profile2_no_rb_extra_x, 5555)
        self.assertEqual(decoded.settings.profile2_rb_delay_ms, 222)
        self.assertEqual(decoded.settings.profile2_rb_ramp_ms, 888)
        self.assertEqual(decoded.settings.profile2_rb_extra_x, 777)
        self.assertEqual(decoded.settings.profile2_rb_extra_y, 666)

    def test_legacy_payload_upgrades_advanced_stick_defaults(self):
        payload = bytearray(cm.encode_payload(cm.ConfigPayload()))
        # The v1 payload originally used byte 5 and the final 16 bytes as
        # reserved zeros. Decoding it must restore the old hard-coded behavior.
        payload[5] = 0
        payload[-cm._ADVANCED_STICK_STRUCT.size :] = b"\x00" * cm._ADVANCED_STICK_STRUCT.size

        decoded = cm.decode_payload(bytes(payload))

        self.assertEqual(decoded.settings.advanced_stick_version, 1)
        self.assertEqual(decoded.settings.profile2_rb_speed_x, 3750)
        self.assertEqual(decoded.settings.profile2_rb_speed_y, 2000)
        self.assertEqual(decoded.settings.profile2_no_rb_extra_x, 4583)
        self.assertEqual(decoded.settings.profile2_rb_extra_x, 625)
        self.assertEqual(decoded.settings.profile2_rb_extra_y, 625)

    def test_legacy_zero_virtual_dpi_uses_1000(self):
        payload = bytearray(cm.encode_payload(cm.ConfigPayload()))
        macro_offset = (
            cm._SETTINGS_STRUCT.size
            + cm.PROFILE_COUNT * cm.SOURCE_COUNT * cm.GESTURE_COUNT * cm._ACTION_STRUCT.size
            + cm.COMBO_MAX * cm._COMBO_STRUCT.size
        )
        reserved_offset = macro_offset + cm.MACRO_NAME_MAX + 2
        payload[reserved_offset : reserved_offset + 2] = b"\x00\x00"

        decoded = cm.decode_payload(bytes(payload))

        self.assertEqual(decoded.settings.virtual_dpi, cm.VIRTUAL_DPI_DEFAULT)

    def test_documented_profiles_and_snapshot_macro_are_the_defaults(self):
        config = cm.ConfigPayload()

        self.assertEqual(config.settings.left_stick_mode, [2, 1, 2])
        self.assertEqual(config.settings.mouse_release_grace_ms, 40)

        profile_1_x = config.bindings[0][cm.SRC_X]
        self.assertEqual(profile_1_x[cm.GESTURE_TAP].param1, cm.HID_NAME_TO_KEY["R"])
        self.assertEqual(profile_1_x[cm.GESTURE_HOLD].param1, cm.HID_NAME_TO_KEY["F"])

        profile_2 = config.bindings[1]
        self.assertEqual(profile_2[cm.SRC_LT][cm.GESTURE_HOLD].param1, cm.MOD_LEFTCTRL)
        self.assertEqual(profile_2[cm.SRC_B][cm.GESTURE_HOLD].type,
                         cm.ACTION_WHEEL_DOWN_TURBO)

        profile_3_x = config.bindings[2][cm.SRC_X]
        self.assertEqual(profile_3_x[cm.GESTURE_TAP].param1, cm.HID_NAME_TO_KEY["R"])
        self.assertEqual(profile_3_x[cm.GESTURE_DOUBLE].param1, cm.HID_NAME_TO_KEY["F"])

        for profile in range(cm.PROFILE_COUNT):
            snapshot = config.bindings[profile][cm.SRC_SNAPSHOT][cm.GESTURE_TAP]
            self.assertEqual((snapshot.type, snapshot.param1), (cm.ACTION_MACRO, 0))

        macro = config.macros[0]
        self.assertEqual(macro.name, "Snapshot Alt+RMB")
        self.assertEqual(macro.step_count, 4)
        self.assertEqual(
            [(step.type, step.modifier, step.keys[0], step.duration_ms)
             for step in macro.steps],
            [
                (cm.MACRO_STEP_KEYBOARD, cm.MOD_LEFTALT, 0, 30),
                (cm.MACRO_STEP_MOUSE, 0, cm.MOUSE_RIGHT, 10),
                (cm.MACRO_STEP_MOUSE, 0, 0, 30),
                (cm.MACRO_STEP_KEYBOARD, 0, 0, 1),
            ],
        )

    def test_macro_round_trip(self):
        config = cm.ConfigPayload()
        macro = config.macros[0]
        macro.name = "Test macro"
        macro.step_count = 3
        macro.steps = [
            cm.MacroStep(type=cm.MACRO_STEP_DELAY, duration_ms=10),
            cm.MacroStep(type=cm.MACRO_STEP_KEYBOARD, modifier=0, keys=(4, 0, 0, 0, 0, 0), duration_ms=20),
            cm.MacroStep(type=cm.MACRO_STEP_MOUSE, keys=(1, 0, 0, 0, 0, 0), value=0, duration_ms=5),
        ]
        decoded = cm.decode_payload(cm.encode_payload(config))
        self.assertEqual(decoded.macros[0].name, "Test macro")
        self.assertEqual(decoded.macros[0].step_count, 3)
        self.assertEqual(decoded.macros[0].steps[1].keys[0], 4)

    def test_macro_name_uses_all_24_bytes(self):
        config = cm.ConfigPayload()
        config.macros[0].name = "abcdefghijklmnopqrstuvwx"
        decoded = cm.decode_payload(cm.encode_payload(config))
        self.assertEqual(decoded.macros[0].name, "abcdefghijklmnopqrstuvwx")

    def test_macro_name_truncation_does_not_split_utf8(self):
        config = cm.ConfigPayload()
        config.macros[0].name = "界" * 9
        decoded = cm.decode_payload(cm.encode_payload(config))
        self.assertEqual(decoded.macros[0].name, "界" * 8)
        self.assertEqual(len(decoded.macros[0].name.encode("utf-8")), 24)

    def test_decode_rejects_wrong_payload_size(self):
        payload = cm.encode_payload(cm.ConfigPayload())
        for bad in (payload[:-1], payload + b"\x00"):
            with self.subTest(size=len(bad)):
                with self.assertRaisesRegex(ValueError, "config payload"):
                    cm.decode_payload(bad)

    def test_decode_rejects_macro_step_count_before_reading_steps(self):
        payload = bytearray(cm.encode_payload(cm.ConfigPayload()))
        macro_offset = (
            cm._SETTINGS_STRUCT.size
            + cm.PROFILE_COUNT * cm.SOURCE_COUNT * cm.GESTURE_COUNT * cm._ACTION_STRUCT.size
            + cm.COMBO_MAX * cm._COMBO_STRUCT.size
        )
        payload[macro_offset + cm.MACRO_NAME_MAX] = cm.MACRO_STEP_MAX + 1
        with self.assertRaisesRegex(ValueError, r"macros\[0\]\.step_count"):
            cm.decode_payload(bytes(payload))

    def test_decode_rejects_invalid_utf8_name(self):
        payload = bytearray(cm.encode_payload(cm.ConfigPayload()))
        macro_offset = (
            cm._SETTINGS_STRUCT.size
            + cm.PROFILE_COUNT * cm.SOURCE_COUNT * cm.GESTURE_COUNT * cm._ACTION_STRUCT.size
            + cm.COMBO_MAX * cm._COMBO_STRUCT.size
        )
        payload[macro_offset : macro_offset + 2] = b"\xC3\x28"
        with self.assertRaisesRegex(ValueError, r"macros\[0\]\.name"):
            cm.decode_payload(bytes(payload))

    def test_semantic_validation_has_context(self):
        cases = [
            (lambda c: setattr(c.settings, "output_enabled", 2), "settings.output_enabled"),
            (lambda c: setattr(c.settings, "tap_duration_ms", 0), "settings.tap_duration_ms"),
            (lambda c: setattr(c.settings, "wheel_turbo_hz", 1001), "settings.wheel_turbo_hz"),
            (lambda c: setattr(c.settings, "right_deadzone", float("nan")), "settings.right_deadzone"),
            (lambda c: setattr(c.settings, "right_center_x", 4096), "settings.right_center_x"),
            (lambda c: setattr(c.settings, "virtual_dpi", 99), "settings.virtual_dpi"),
            (lambda c: setattr(c.settings, "virtual_dpi", 20001), "settings.virtual_dpi"),
            (lambda c: setattr(c.combos[0], "profile_mask", 0x08), "combos[0].profile_mask"),
            (lambda c: setattr(c.combos[0], "source_mask", 1 << cm.SOURCE_COUNT), "combos[0].source_mask"),
            (
                lambda c: setattr(
                    c.bindings[0][0][0], "type", cm.ACTION_SNAPSHOT_MACRO + 1
                ),
                "bindings[0][0][0].type",
            ),
        ]
        for mutate, expected in cases:
            config = cm.ConfigPayload()
            mutate(config)
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected.replace("[", r"\[").replace("]", r"\]")):
                    cm.encode_payload(config)

    def test_macro_mouse_button_validation(self):
        config = cm.ConfigPayload()
        config.macros[0] = cm.Macro(
            step_count=1,
            steps=[cm.MacroStep(type=cm.MACRO_STEP_MOUSE, keys=(0x08, 0, 0, 0, 0, 0))],
        )
        with self.assertRaisesRegex(ValueError, "unsupported mouse-button bits"):
            cm.encode_payload(config)

    def test_name_nul_and_missing_steps_are_rejected_cleanly(self):
        config = cm.ConfigPayload()
        config.macros[0].name = "bad\x00name"
        with self.assertRaisesRegex(ValueError, "cannot contain NUL"):
            cm.encode_payload(config)

        config = cm.ConfigPayload()
        config.macros[0].step_count = 1
        config.macros[0].steps = []
        with self.assertRaisesRegex(ValueError, "only 0 steps"):
            cm.encode_payload(config)


if __name__ == "__main__":
    unittest.main()
