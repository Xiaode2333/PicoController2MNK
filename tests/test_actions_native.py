"""Verify Python payloads against the actual firmware action engine."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from tools.pico2mnk_configurator import config_model as cm


class NativeActionTests(unittest.TestCase):
    def test_runtime_and_payload_roundtrip(self):
        compiler = shutil.which("cc") or shutil.which("gcc")
        if compiler is None:
            self.skipTest("Native C compiler unavailable; run in WSL.")
        root = Path(__file__).resolve().parents[1]
        native = root / "tests" / "native"
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            executable = directory / "toggle-runtime"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(native / "stubs"), "-I", str(root),
                            str(root / "mapper_config.c"), str(root / "mapper_action.c"),
                            str(native / "test_toggle_runtime.c"), "-lm", "-o", str(executable)], check=True)
            config = cm.ConfigPayload()
            for source, action_type in enumerate(sorted(cm.TOGGLE_ACTION_TYPES)):
                config.bindings[0][source][cm.GESTURE_HOLD] = cm.Action(
                    type=action_type, param1=1, trigger_mode=cm.ACTION_MODE_TOGGLE, duration_ms=1)
            for mode in range(4):
                config.bindings[1][mode][cm.GESTURE_HOLD] = cm.Action(
                    type=cm.ACTION_MACRO, trigger_mode=cm.MACRO_TRIGGER_OVERRIDE | mode, duration_ms=1)
            config.combos[10] = cm.Combo(profile_mask=7, source_mask=3,
                action=cm.Action(type=cm.ACTION_STOP_ALL))
            incoming, outgoing = directory / "in.bin", directory / "out.bin"
            payload = cm.encode_payload(config)
            incoming.write_bytes(payload)
            subprocess.run([str(executable), str(incoming), str(outgoing)], check=True)
            self.assertEqual(outgoing.read_bytes(), payload)
