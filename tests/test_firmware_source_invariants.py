import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"unterminated function: {signature}")


class FirmwareSourceInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main_source = (ROOT / "main.c").read_text(encoding="utf-8")

    def test_freshness_clock_is_sampled_after_report_timestamp(self) -> None:
        body = function_body(
            self.main_source,
            "static bool gamepad_input_is_fresh(gamepad_freshness_snapshot_t "
            "*snapshot_out) {",
        )

        lock_index = body.index(
            "critical_section_enter_blocking(&g_mapper_input_lock)"
        )
        valid_index = body.index("snapshot.valid = g_gamepad_valid")
        report_index = body.index(
            "snapshot.last_report_us = g_last_valid_report_us"
        )
        unlock_index = body.index(
            "critical_section_exit(&g_mapper_input_lock)"
        )
        clock_index = body.index("snapshot.now_us = time_us_32()")

        self.assertLess(lock_index, valid_index)
        self.assertLess(valid_index, report_index)
        self.assertLess(report_index, unlock_index)
        self.assertLess(unlock_index, clock_index)
        self.assertNotIn("last_report_us != 0", body)

    def test_freshness_callers_cannot_pass_an_older_clock_sample(self) -> None:
        declarations = re.findall(
            r"gamepad_input_is_fresh\(([^)]*)\)", self.main_source
        )

        self.assertTrue(declarations)
        self.assertNotIn("uint64_t now_us", declarations)
        self.assertNotIn("now_us", declarations)

    def test_capture_clock_is_sampled_after_report_snapshot(self) -> None:
        body = function_body(self.main_source, "static void capture_print_sample(")

        self.assertLess(
            body.index("snapshot_latest_report("),
            body.index("uint64_t now_us = time_us_64()"),
        )


if __name__ == "__main__":
    unittest.main()
