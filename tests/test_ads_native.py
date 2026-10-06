"""Compile and exercise real firmware logic with minimal platform stubs."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.pico2mnk_configurator import config_model as cm


class NativeADSTests(unittest.TestCase):
    def test_real_firmware_engine_and_python_payload_compatibility(self):
        compiler = shutil.which("cc") or shutil.which("gcc")
        if compiler is None:
            self.skipTest("Native C compiler unavailable; run this test in Linux/WSL.")
        root = Path(__file__).resolve().parents[1]
        native = root / "tests" / "native"
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            executable = directory / "ads-runtime"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(native / "stubs"), "-I", str(root),
                            str(root / "mapper_config.c"), str(root / "mapper_action.c"),
                            str(native / "test_ads_runtime.c"), "-lm", "-o", str(executable)], check=True)
            config = cm.ConfigPayload()
            config.settings.profile2_aim_source = cm.SRC_LT
            config.settings.profile2_rb_speed_x = 1234
            config.settings.profile2_rb_speed_y = 2345
            config.macros[6].name = "Shared metadata"
            config.macros[6].steps = [cm.MacroStep(duration_ms=75)]
            config.macros[6].step_count = 1
            incoming = directory / "incoming.bin"
            outgoing = directory / "outgoing.bin"
            incoming.write_bytes(cm.encode_payload(config))
            subprocess.run([str(executable), str(incoming), str(outgoing)], check=True)
            restored = cm.decode_payload(outgoing.read_bytes())
            self.assertEqual(restored.settings.profile2_aim_source, cm.SRC_A)
            self.assertEqual(restored.macros[6], config.macros[6])
            self.assertEqual(restored.settings.profile2_rb_speed_x, 1234)


if __name__ == "__main__":
    unittest.main()
