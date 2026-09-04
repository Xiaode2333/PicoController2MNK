import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.pico2mnk_configurator import config_model as cm
from tools.pico2mnk_configurator.app import App, MacrosTab
from tools.pico2mnk_configurator.device_locator import CandidatePort


class FakeVar:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeListbox:
    def __init__(self, selection):
        self.selection = selection

    def curselection(self):
        return (self.selection,)


class FakeRecorder:
    def __init__(self):
        self.stopped = False
        self.encode_args = None

    def stop(self):
        self.stopped = True

    def encode(self, *, name, trigger_mode):
        self.encode_args = (name, trigger_mode)
        return cm.Macro(
            name=name,
            trigger_mode=trigger_mode,
            step_count=1,
            steps=[cm.MacroStep(type=cm.MACRO_STEP_DELAY, duration_ms=5)],
        )


class MacroTabLogicTests(unittest.TestCase):
    def make_tab(self):
        tab = object.__new__(MacrosTab)
        tab.app = SimpleNamespace(config=cm.ConfigPayload())
        tab._refreshing = False
        tab.selected_index = FakeVar(0)
        tab.name_var = FakeVar("")
        tab.trigger_var = FakeVar(cm.MACRO_TRIGGER_NAMES[0])
        return tab

    def test_switch_commits_previous_slot_before_loading_new_slot(self):
        tab = self.make_tab()
        tab.selected_index.set(3)
        tab.name_var.set("Unsaved slot four")
        tab.trigger_var.set(cm.MACRO_TRIGGER_NAMES[cm.MACRO_TRIGGER_TOGGLE])
        tab.listbox = FakeListbox(6)
        loaded = []
        tab._load_editor = loaded.append

        MacrosTab._select(tab)

        previous = tab.app.config.macros[3]
        self.assertEqual(previous.name, "Unsaved slot four")
        self.assertEqual(previous.trigger_mode, cm.MACRO_TRIGGER_TOGGLE)
        self.assertEqual(tab.selected_index.get(), 6)
        self.assertIs(loaded[0], tab.app.config.macros[6])

    def test_recording_replaces_captured_slot_and_preserves_its_fields(self):
        tab = self.make_tab()
        tab.selected_index.set(1)
        tab.name_var.set("Current editor")
        tab.trigger_var.set(cm.MACRO_TRIGGER_NAMES[cm.MACRO_TRIGGER_RELEASE])
        tab.recording_index = 5
        tab.app.config.macros[5].name = "Recorded target"
        tab.app.config.macros[5].trigger_mode = cm.MACRO_TRIGGER_TOGGLE
        tab.recorder = FakeRecorder()
        recorder = tab.recorder
        tab._record_poll_id = None
        tab.status_var = FakeVar()
        tab.refresh = lambda: None

        MacrosTab._stop(tab)

        self.assertTrue(recorder.stopped)
        self.assertEqual(
            recorder.encode_args,
            ("Recorded target", cm.MACRO_TRIGGER_TOGGLE),
        )
        target = tab.app.config.macros[5]
        self.assertEqual(target.name, "Recorded target")
        self.assertEqual(target.trigger_mode, cm.MACRO_TRIGGER_TOGGLE)
        self.assertEqual(target.step_count, 1)
        self.assertEqual(tab.app.config.macros[1].name, "Current editor")
        self.assertEqual(tab.app.config.macros[1].trigger_mode, cm.MACRO_TRIGGER_RELEASE)
        self.assertIsNone(tab.recording_index)


class AppConnectionLogicTests(unittest.TestCase):
    def test_connect_never_falls_through_to_a_different_likely_board(self):
        app = object.__new__(App)
        app.port_var = FakeVar("COM2")
        app.identity_var = FakeVar("Not connected.")
        app.status_var = FakeVar("Ready")
        app.connection = None
        app.config = None
        app.descriptor_verified_port = None
        app.refresh_ports = lambda: None
        app.disconnect = lambda: setattr(app, "connection", None)
        app._port_candidate = lambda port: CandidatePort(
            port=port,
            description="Pico KBM Mapper",
            hwid="USB VID:PID=CAFE:4007",
            vid=0xCAFE,
            pid=0x4007,
        )

        attempts = []

        def fail_selected(port, timeout):
            attempts.append((port, timeout))
            raise RuntimeError("selected board did not respond")

        with patch(
            "tools.pico2mnk_configurator.app.BoardConnection.open",
            side_effect=fail_selected,
        ), patch("tools.pico2mnk_configurator.app.messagebox.showerror"):
            App.connect(app)

        self.assertEqual(attempts, [("COM2", 1.5)])
        self.assertEqual(app.descriptor_verified_port, "COM2")


if __name__ == "__main__":
    unittest.main()
