import unittest

from tools.pico2mnk_configurator import config_model as cm
from tools.pico2mnk_configurator.app import (
    ACTIVE_PROFILE_LABELS,
    LEFT_STICK_MODE_LABELS,
    OUTPUT_STATE_LABELS,
    build_profile_combo_rows,
    build_profile_macro_rows,
    build_profile_stick_rows,
    config_uses_delayed_combos,
    config_uses_extended_macro_steps,
    config_uses_mouse_mode_actions,
    config_uses_two_key_actions,
    format_combo_action,
    install_mouse_mode_binding,
)


class ProfileOverviewTests(unittest.TestCase):
    def setUp(self):
        self.config = cm.ConfigPayload()

    def test_every_profiles_combo_list_is_complete(self):
        rows = [build_profile_combo_rows(self.config, profile) for profile in range(3)]
        self.assertEqual([len(profile_rows) for profile_rows in rows], [9, 9, 6])
        self.assertEqual(rows[0][0][2], "LB + RB + X")
        self.assertEqual(rows[0][0][3], "Left Ctrl + 1")
        self.assertIn("LT + RT", [row[2] for row in rows[2]])
        self.assertIn("LB + RT", [row[2] for row in rows[2]])

    def test_profile_2_stick_rules_include_advanced_values(self):
        rows = dict(build_profile_stick_rows(self.config, 1))
        self.assertEqual(rows["Left stick mode"], LEFT_STICK_MODE_LABELS[1])
        self.assertEqual(rows["Virtual DPI"], "5000 (shared by all profiles)")
        self.assertEqual(rows["Mouse mode 1"], "100% sensitivity, 0.0200 deadzone")
        self.assertEqual(rows["Mouse mode 2"], "50% sensitivity, 0.0200 deadzone")
        self.assertEqual(
            rows["Right stick while Aim (ADS)"],
            "X 3750 base counts/s, Y 2000 base counts/s",
        )
        self.assertEqual(rows["Outer-ring acceleration"], "Enabled")
        self.assertEqual(rows["Outer-ring threshold"], "0.95")
        self.assertEqual(rows["Aim / ADS input"], "RB")
        self.assertIn("+4583", rows["Outer ring without Aim (hip fire)"])
        self.assertIn("+625/+625", rows["Outer ring while Aim (ADS)"])

    def test_settings_choice_labels_explain_stored_numeric_values(self):
        self.assertEqual(
            LEFT_STICK_MODE_LABELS,
            (
                "Off — no automatic WASD",
                "4-way — one WASD key at a time",
                "8-way — diagonals use two WASD keys",
            ),
        )
        self.assertEqual(ACTIVE_PROFILE_LABELS, ("Profile 1", "Profile 2", "Profile 3"))
        self.assertIn("Disabled", OUTPUT_STATE_LABELS[0])
        self.assertIn("Enabled", OUTPUT_STATE_LABELS[1])

    def test_all_macros_and_complete_sequence_are_listed(self):
        rows = build_profile_macro_rows(self.config, 0)
        self.assertEqual(len(rows), cm.MACRO_MAX)
        self.assertEqual(rows[0][1], "Snapshot Alt+RMB")
        self.assertEqual(rows[0][2], "On press")
        self.assertIn("Snapshot (Tap)", rows[0][3])
        self.assertIn("Keyboard Left Alt for 30 ms", rows[0][4])
        self.assertIn("Mouse Right for 10 ms", rows[0][4])
        self.assertEqual(rows[1][1], "Alt+MB Right")
        self.assertIn("Keyboard Left Alt for 50 ms", rows[1][4])
        self.assertIn("Mouse Right for 50 ms", rows[1][4])

    def test_combo_action_describes_immediate_and_custom_delays(self):
        action = cm.Action(type=cm.ACTION_MODIFIER_KEY, param1=cm.MOD_LEFTSHIFT)
        self.assertEqual(
            format_combo_action(self.config, action),
            "Left Shift",
        )
        action.duration_ms = 500
        self.assertEqual(
            format_combo_action(self.config, action),
            "After 500 ms, hold: Left Shift",
        )

    def test_delayed_combo_feature_detection(self):
        self.assertTrue(config_uses_delayed_combos(self.config))
        self.config.combos[15].action.duration_ms = 0
        self.assertFalse(config_uses_delayed_combos(self.config))
        self.config.combos[0].action.duration_ms = 250
        self.assertTrue(config_uses_delayed_combos(self.config))

    def test_mouse_mode_action_feature_detection(self):
        self.assertFalse(config_uses_mouse_mode_actions(self.config))
        self.config.bindings[0][cm.SRC_MENU][cm.GESTURE_TAP] = cm.Action(
            type=cm.ACTION_MOUSE_MODE_TOGGLE_KEY,
            param1=cm.HID_NAME_TO_KEY["Tab"],
        )
        self.assertTrue(config_uses_mouse_mode_actions(self.config))

    def test_two_key_action_feature_detection(self):
        self.assertFalse(config_uses_two_key_actions(self.config))
        self.config.bindings[0][cm.SRC_A][cm.GESTURE_HOLD] = cm.Action(
            type=cm.ACTION_TWO_KEYS,
            param1=cm.HID_NAME_TO_KEY["Q"],
            param2=cm.HID_NAME_TO_KEY["E"],
        )
        self.assertTrue(config_uses_two_key_actions(self.config))

    def test_extended_macro_step_feature_detection(self):
        self.assertFalse(config_uses_extended_macro_steps(self.config))
        self.config.macros[2] = cm.Macro(
            name="Mode toggle",
            step_count=1,
            steps=[
                cm.MacroStep(
                    type=cm.MACRO_STEP_MOUSE_MODE_TOGGLE_KEY,
                    keys=(cm.HID_NAME_TO_KEY["Tab"], 0, 0, 0, 0, 0),
                )
            ],
        )
        self.assertTrue(config_uses_extended_macro_steps(self.config))

    def test_install_mouse_mode_binding_replaces_conflicting_hold(self):
        self.assertNotEqual(
            self.config.bindings[0][cm.SRC_MENU][cm.GESTURE_HOLD].type,
            cm.ACTION_NONE,
        )

        install_mouse_mode_binding(
            self.config, 0, cm.SRC_MENU, cm.HID_NAME_TO_KEY["Tab"]
        )

        gestures = self.config.bindings[0][cm.SRC_MENU]
        self.assertEqual(gestures[cm.GESTURE_TAP].type,
                         cm.ACTION_MOUSE_MODE_TOGGLE_KEY)
        self.assertEqual(gestures[cm.GESTURE_TAP].param1,
                         cm.HID_NAME_TO_KEY["Tab"])
        self.assertEqual(gestures[cm.GESTURE_HOLD].type, cm.ACTION_NONE)
        self.assertEqual(gestures[cm.GESTURE_DOUBLE].type,
                         cm.ACTION_MOUSE_MODE_SWAP)


if __name__ == "__main__":
    unittest.main()
