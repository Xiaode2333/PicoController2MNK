import struct
import tempfile
import unittest
from pathlib import Path

from tools.pico2mnk_configurator import firmware_flasher as ff


def uf2_block(
    payload,
    block_no=0,
    total_blocks=1,
    *,
    flags=ff.UF2_FLAG_FAMILY_ID_PRESENT,
    family=ff.RP2040_FAMILY_ID,
    end_magic=ff.UF2_MAGIC_END,
):
    if len(payload) > 476:
        raise ValueError("test payload too large")
    header = struct.pack(
        "<IIIIIIII",
        ff.UF2_MAGIC_0,
        ff.UF2_MAGIC_1,
        flags,
        0x10000000 + block_no * 256,
        len(payload),
        block_no,
        total_blocks,
        family,
    )
    return header + payload.ljust(476, b"\x00") + struct.pack("<I", end_magic)


class FirmwareFlasherTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def write(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_accepts_only_stable_product_marker(self):
        stable = self.write("stable.uf2", uf2_block(ff.STABLE_PRODUCT_MARKER))
        self.assertEqual(ff.verify_mapper_uf2(stable), (1, ff.RP2040_FAMILY_ID))

        for marker in ff.REJECTED_PRODUCT_MARKERS:
            path = self.write("rejected.uf2", uf2_block(marker + b"\x00"))
            with self.subTest(marker=marker):
                with self.assertRaisesRegex(ValueError, "non-configurable"):
                    ff.verify_mapper_uf2(path)

    def test_rejects_missing_family_flag(self):
        path = self.write("no-family.uf2", uf2_block(b"x", flags=0))
        with self.assertRaisesRegex(ValueError, "family-ID flag"):
            ff.verify_uf2(path)

    def test_rejects_bad_end_magic(self):
        path = self.write("bad-end.uf2", uf2_block(b"x", end_magic=0))
        with self.assertRaisesRegex(ValueError, "invalid UF2 magic"):
            ff.verify_uf2(path)

    def test_rejects_duplicate_or_incomplete_block_numbers(self):
        data = uf2_block(b"first", 0, 2) + uf2_block(b"second", 0, 2)
        path = self.write("duplicate.uf2", data)
        with self.assertRaisesRegex(ValueError, "duplicate UF2 block number"):
            ff.verify_uf2(path)

    def test_rejects_wrong_family(self):
        path = self.write("wrong-family.uf2", uf2_block(b"x", family=0x12345678))
        with self.assertRaisesRegex(ValueError, "not an RP2040 UF2"):
            ff.verify_uf2(path)

    def test_current_build_artifacts_have_expected_release_identity(self):
        build = Path(__file__).resolve().parents[1] / "build"
        stable = build / "pico_kbm_mapper.uf2"
        trace = build / "pico_kbm_mapper_trace.uf2"
        debug = build / "pico_cdc_test.uf2"
        if not stable.exists():
            self.skipTest("firmware artifacts have not been built")

        ff.verify_mapper_uf2(stable)
        for path in (trace, debug):
            if path.exists():
                with self.subTest(path=path.name):
                    with self.assertRaises(ValueError):
                        ff.verify_mapper_uf2(path)


if __name__ == "__main__":
    unittest.main()
