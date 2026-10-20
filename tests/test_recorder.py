import time
import unittest
from types import SimpleNamespace

from tools.pico2mnk_configurator import config_model as cm
from tools.pico2mnk_configurator.recorder import (
    RecordedEvent,
    Recorder,
    is_stop_hotkey,
    key_to_hid,
)


def key(*, vk=0, char="", name=""):
    return SimpleNamespace(vk=vk, char=char, name=name)


class RecorderTests(unittest.TestCase):
    def test_navigation_lock_and_application_virtual_keys(self):
        for vk, name in {
            0x21: "Page Up", 0x22: "Page Down", 0x23: "End", 0x24: "Home",
            0x2C: "Print Screen", 0x2D: "Insert", 0x5D: "Application",
            0x90: "Num Lock", 0x91: "Scroll Lock",
        }.items():
            with self.subTest(name=name):
                self.assertEqual(key_to_hid(key(vk=vk)), (cm.HID_NAME_TO_KEY[name], 0))

    def test_all_numpad_digits_and_function_keys(self):
        for digit in range(10):
            with self.subTest(digit=digit):
                self.assertEqual(key_to_hid(key(vk=0x60 + digit)),
                                 (cm.HID_NAME_TO_KEY[f"Numpad {digit}"], 0))
        for number in range(1, 25):
            with self.subTest(function=number):
                self.assertEqual(key_to_hid(key(vk=0x6F + number)),
                                 (cm.HID_NAME_TO_KEY[f"F{number}"], 0))

    def test_pynput_special_key_enums_and_modifier_names(self):
        for name, code in {"page_up": 0x4B, "page_down": 0x4E,
                           "print_screen": 0x46, "enter": 0x28,
                           "menu": 0x65, "f24": 0x73}.items():
            with self.subTest(name=name):
                self.assertEqual(key_to_hid(SimpleNamespace(
                    name=name, value=key(vk=0))), (code, 0))
        for name, modifier in {"ctrl_l": cm.MOD_LEFTCTRL,
                               "shift_r": cm.MOD_RIGHTSHIFT,
                               "alt_gr": cm.MOD_RIGHTALT,
                               "cmd_r": cm.MOD_RIGHTGUI}.items():
            with self.subTest(name=name):
                self.assertEqual(key_to_hid(SimpleNamespace(
                    name=name, value=key(vk=0))), (0, modifier))

    def test_shifted_punctuation_keeps_underlying_key(self):
        self.assertEqual(key_to_hid(key(vk=0xBB, char="+")), (0x2E, 0))
        self.assertEqual(key_to_hid(key(vk=0xBA, char=":")), (0x33, 0))

    def test_recorded_page_up_with_ctrl_releases_both(self):
        recorder = Recorder()
        ctrl = SimpleNamespace(name="ctrl_l", value=key(vk=0xA2))
        page_up = SimpleNamespace(name="page_up", value=key(vk=0x21))
        recorder.events = [RecordedEvent(0.00, "key_down", key=ctrl),
                           RecordedEvent(0.01, "key_down", key=page_up),
                           RecordedEvent(0.10, "key_up", key=page_up),
                           RecordedEvent(0.11, "key_up", key=ctrl)]
        steps = recorder.encode().steps
        self.assertEqual(steps[1].modifier, cm.MOD_LEFTCTRL)
        self.assertEqual(steps[1].keys, (0x4B, 0, 0, 0, 0, 0))
        self.assertEqual(steps[2].keys, (0, 0, 0, 0, 0, 0))
        self.assertEqual(steps[3].modifier, 0)

    def test_top_row_digit_hid_mapping(self):
        expected = {"0": 0x27, "1": 0x1E, "2": 0x1F, "9": 0x26}
        for digit, hid in expected.items():
            with self.subTest(digit=digit):
                self.assertEqual(key_to_hid(key(vk=ord(digit))), (hid, 0))

    def test_character_backslash_mapping(self):
        self.assertEqual(
            key_to_hid(key(char="\\")),
            (cm.HID_NAME_TO_KEY["Backslash"], 0),
        )

    def test_f12_is_reserved_stop_hotkey(self):
        self.assertTrue(is_stop_hotkey(key(vk=0x7B)))
        self.assertTrue(is_stop_hotkey(key(name="f12")))
        self.assertFalse(is_stop_hotkey(key(vk=0x7A, name="f11")))

    def test_key_state_duration_reaches_next_transition(self):
        recorder = Recorder()
        a = key(vk=ord("A"))
        recorder.events = [
            RecordedEvent(10.0, "key_down", key=a),
            RecordedEvent(10.1, "key_up", key=a),
        ]
        macro = recorder.encode(trigger_mode=cm.MACRO_TRIGGER_TOGGLE)

        self.assertEqual(macro.trigger_mode, cm.MACRO_TRIGGER_TOGGLE)
        self.assertEqual([step.type for step in macro.steps], [1, 1])
        self.assertEqual([step.duration_ms for step in macro.steps], [100, 5])
        self.assertEqual(macro.steps[0].keys[0], cm.HID_NAME_TO_KEY["A"])
        self.assertEqual(macro.steps[1].keys, (0, 0, 0, 0, 0, 0))

    def test_keyboard_and_mouse_states_have_event_timing(self):
        recorder = Recorder()
        a = key(vk=ord("A"))
        recorder.events = [
            RecordedEvent(1.00, "key_down", key=a),
            RecordedEvent(1.02, "mouse_down", button="left"),
            RecordedEvent(1.04, "mouse_up", button="left"),
            RecordedEvent(1.10, "key_up", key=a),
        ]
        macro = recorder.encode()

        self.assertEqual(
            [step.type for step in macro.steps],
            [cm.MACRO_STEP_KEYBOARD, cm.MACRO_STEP_MOUSE,
             cm.MACRO_STEP_MOUSE, cm.MACRO_STEP_KEYBOARD],
        )
        self.assertEqual([step.duration_ms for step in macro.steps], [20, 20, 60, 5])
        self.assertEqual(macro.steps[1].keys[0], cm.MOUSE_LEFT)
        self.assertEqual(macro.steps[2].keys[0], 0)

    def test_long_gap_is_split_without_losing_time(self):
        recorder = Recorder()
        a = key(vk=ord("A"))
        recorder.events = [
            RecordedEvent(0.0, "key_down", key=a),
            RecordedEvent(70.0, "key_up", key=a),
        ]
        macro = recorder.encode()

        self.assertEqual(macro.steps[0].duration_ms, 0xFFFF)
        self.assertEqual(macro.steps[1].type, cm.MACRO_STEP_DELAY)
        self.assertEqual(macro.steps[1].duration_ms, 70000 - 0xFFFF)
        self.assertEqual(sum(step.duration_ms for step in macro.steps[:2]), 70000)

    def test_duplicate_and_unknown_events_do_not_create_state_steps(self):
        recorder = Recorder()
        a = key(vk=ord("A"))
        recorder.events = [
            RecordedEvent(0.0, "key_down", key=a),
            RecordedEvent(0.01, "key_down", key=a),
            RecordedEvent(0.02, "key_down", key=key(char="☃")),
            RecordedEvent(0.03, "key_up", key=a),
        ]
        macro = recorder.encode()
        self.assertEqual(macro.step_count, 2)
        self.assertEqual([step.duration_ms for step in macro.steps], [30, 5])

    def test_trailing_stop_button_click_is_removed_only_from_click_start(self):
        recorder = Recorder()
        now = time.monotonic()
        recorder.events = [
            RecordedEvent(now - 0.2, "key_down", key=key(vk=ord("A"))),
            RecordedEvent(now - 0.02, "mouse_down", button="left", x=120, y=220),
            RecordedEvent(now - 0.01, "mouse_up", button="left", x=120, y=220),
        ]
        recorder.discard_trailing_click(100, 200, 150, 250)
        self.assertEqual(len(recorder.events), 1)
        self.assertEqual(recorder.events[0].kind, "key_down")

    def test_event_limit_warning_is_emitted_once(self):
        warnings = []
        recorder = Recorder(max_events=1)
        recorder._warn = warnings.append
        recorder._append(RecordedEvent(0.0, "wheel", wheel=1))
        recorder._append(RecordedEvent(0.1, "wheel", wheel=1))
        recorder._append(RecordedEvent(0.2, "wheel", wheel=1))
        self.assertEqual(warnings, ["Event limit reached; stop recording."])


if __name__ == "__main__":
    unittest.main()
