import unittest

from tools.pico2mnk_configurator import config_model as cm
from tools.pico2mnk_configurator.app import (
    ACTIVE_PROFILE_LABELS,
    LEFT_STICK_MODE_LABELS,
    OUTPUT_STATE_LABELS,
    build_profile_combo_rows,
    build_profile_macro_rows,
    build_profile_stick_rows,
)


class ProfileOverviewTests(unittest.TestCase):
    def setUp(self):
        self.config = cm.ConfigPayload()

    def test_every_profiles_combo_list_is_complete(self):
        rows = [build_profile_combo_rows(self.config, profile) for profile in range(3)]
        self.assertEqual([len(profile_rows) for profile_rows in rows], [8, 9, 6])
        self.assertEqual(rows[0][0][2], "LT + RT + X")
        self.assertEqual(rows[0][0][3], "Left Ctrl + 1")
        self.assertIn("LT + RT", [row[2] for row in rows[2]])
        self.assertIn("LB + RT", [row[2] for row in rows[2]])

    def test_profile_2_stick_rules_include_advanced_values(self):
        rows = dict(build_profile_stick_rows(self.config, 1))
        self.assertEqual(rows["Left stick mode"], LEFT_STICK_MODE_LABELS[1])
        self.assertEqual(rows["Virtual DPI"], "1000 (shared by all profiles)")
        self.assertEqual(
            rows["Right stick while RB"],
            "X 3750 base counts/s, Y 2000 base counts/s",
        )
        self.assertEqual(rows["Outer-ring acceleration"], "Enabled")
        self.assertEqual(rows["Outer-ring threshold"], "0.95")
        self.assertIn("+4583", rows["Outer ring without RB"])
        self.assertIn("+625/+625", rows["Outer ring with RB"])

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
        self.assertEqual(rows[1][4], "Empty")


if __name__ == "__main__":
    unittest.main()
