import unittest

from tools.pico2mnk_configurator.device_locator import (
    CandidatePort,
    descriptor_flash_port,
    legacy_mapper_port,
    likely_mapper_port,
)


def candidate(pid=None, *, vid=0xCAFE, description="", hwid=""):
    return CandidatePort("COM1", description, hwid, vid, pid)


class DeviceLocatorTests(unittest.TestCase):
    def test_only_stable_pid_is_configurable(self):
        self.assertTrue(likely_mapper_port(candidate(0x4007)))
        self.assertFalse(likely_mapper_port(candidate(0x4005)))
        self.assertFalse(likely_mapper_port(candidate(0x4008)))
        self.assertFalse(likely_mapper_port(candidate(0x4007, vid=0x1234)))

    def test_legacy_pid_is_descriptor_flash_only(self):
        legacy = candidate(0x4005)
        self.assertTrue(legacy_mapper_port(legacy))
        self.assertTrue(descriptor_flash_port(legacy))
        self.assertFalse(likely_mapper_port(legacy))

    def test_trace_is_never_descriptor_flash_eligible(self):
        trace = candidate(0x4008, description="Pico KBM Mapper Trace")
        self.assertFalse(likely_mapper_port(trace))
        self.assertFalse(legacy_mapper_port(trace))
        self.assertFalse(descriptor_flash_port(trace))

    def test_text_fallback_excludes_debug_and_trace(self):
        stable = candidate(None, vid=None, description="Pico KBM Mapper")
        trace = candidate(None, vid=None, description="Pico KBM Mapper Trace")
        legacy = candidate(None, vid=None, hwid="USB VID:PID=CAFE:4005")
        self.assertTrue(likely_mapper_port(stable))
        self.assertFalse(likely_mapper_port(trace))
        self.assertTrue(legacy_mapper_port(legacy))


if __name__ == "__main__":
    unittest.main()
