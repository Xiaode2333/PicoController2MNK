import time
import unittest

from tools.pico2mnk_configurator import protocol as p


class FakeSerial:
    def __init__(self, incoming=b"", max_read=None, max_write=None):
        self.incoming = bytearray(incoming)
        self.max_read = max_read
        self.max_write = max_write
        self.written = bytearray()
        self.timeout = 0.0
        self.write_timeout = 0.0
        self.closed = False
        self.flush_count = 0

    @property
    def in_waiting(self):
        return len(self.incoming)

    def read(self, size):
        if not self.incoming:
            time.sleep(min(float(self.timeout or 0.0), 0.002))
            return b""
        count = min(size, len(self.incoming))
        if self.max_read is not None:
            count = min(count, self.max_read)
        result = bytes(self.incoming[:count])
        del self.incoming[:count]
        return result

    def write(self, data):
        count = len(data)
        if self.max_write is not None:
            count = min(count, self.max_write)
        self.written.extend(data[:count])
        return count

    def flush(self):
        self.flush_count += 1

    def close(self):
        self.closed = True


def identity_payload(pid=0x4007):
    return p._IDENTITY_STRUCT.pack(
        b"P2MNCFG\x00",
        p.PROTOCOL_VERSION,
        p.SCHEMA_VERSION,
        2,
        1,
        3,
        0xCAFE,
        pid,
        b"Pico KBM Mapper".ljust(32, b"\x00"),
        b"0123456789ABCDEF".ljust(32, b"\x00"),
        1,
        b"\x00" * 3,
    )


class ProtocolTests(unittest.TestCase):
    def test_fragmented_ping_and_partial_write(self):
        response = p.build_frame(p.RESP_ACK_BASE | p.CMD_PING, identity_payload())
        serial = FakeSerial(response, max_read=1, max_write=2)
        connection = p.BoardConnection(serial)
        identity = connection.ping()

        self.assertEqual(identity.pid, 0x4007)
        self.assertEqual(identity.product, "Pico KBM Mapper")
        self.assertEqual(bytes(serial.written), p.build_frame(p.CMD_PING))

    def test_garbage_and_bad_crc_resynchronize_to_valid_frame(self):
        corrupt = bytearray(p.build_frame(p.RESP_ACK_BASE | p.CMD_SAVE_CONFIG, b"old"))
        corrupt[-1] ^= 0xFF
        good = p.build_frame(p.RESP_ACK_BASE | p.CMD_SAVE_CONFIG, b"new")
        serial = FakeSerial(b"console noise\r\n" + corrupt + good, max_read=3)
        connection = p.BoardConnection(serial)

        self.assertEqual(connection.request(p.CMD_SAVE_CONFIG, timeout=0.25), b"new")

    def test_persistent_buffer_keeps_second_frame_for_next_request(self):
        responses = (
            p.build_frame(p.RESP_ACK_BASE | p.CMD_SAVE_CONFIG, b"saved")
            + p.build_frame(p.RESP_ACK_BASE | p.CMD_FACTORY_RESET, b"reset")
        )
        serial = FakeSerial(responses)
        connection = p.BoardConnection(serial)

        self.assertEqual(connection.request(p.CMD_SAVE_CONFIG), b"saved")
        self.assertEqual(connection.request(p.CMD_FACTORY_RESET), b"reset")

    def test_monitor_frame_is_parsed_and_stored_before_ack(self):
        state_payload = p._STATE_STRUCT.pack(
            0x1234, 0.1, -0.2, 0.3, -0.4, 100, 200, 300, 400
        )
        serial = FakeSerial(
            p.build_frame(p.RESP_STATE, state_payload)
            + p.build_frame(p.RESP_ACK_BASE | p.CMD_MONITOR, b"ok")
        )
        connection = p.BoardConnection(serial)

        self.assertEqual(connection.request(p.CMD_MONITOR), b"ok")
        self.assertIsNotNone(connection.monitor_state)
        self.assertEqual(connection.monitor_state.buttons, 0x1234)
        self.assertAlmostEqual(connection.monitor_state.ry, -0.4, places=5)
        self.assertEqual(connection.monitor_state.raw_ry, 400)
        self.assertIsNotNone(connection.monitor_state_received_at)

    def test_bad_monitor_length_is_rejected(self):
        serial = FakeSerial(p.build_frame(p.RESP_STATE, b"short"))
        connection = p.BoardConnection(serial)
        with self.assertRaisesRegex(p.ProtocolError, "monitor state"):
            connection.request(p.CMD_MONITOR, timeout=0.05)

    def test_identity_requires_exact_wire_size(self):
        payload = identity_payload()
        for bad in (payload[:-1], payload + b"\x00"):
            with self.subTest(size=len(bad)):
                with self.assertRaisesRegex(p.ProtocolError, "identity payload"):
                    p.parse_identity(bad)

    def test_trace_pid_fails_handshake(self):
        serial = FakeSerial(
            p.build_frame(p.RESP_ACK_BASE | p.CMD_PING, identity_payload(pid=0x4008))
        )
        connection = p.BoardConnection(serial)
        with self.assertRaisesRegex(p.ProtocolError, "PID 4008"):
            connection.ping()

    def test_request_timeout_is_one_end_to_end_deadline(self):
        unrelated = p.build_frame(p.RESP_ACK_BASE | p.CMD_PING, b"") * 100
        connection = p.BoardConnection(FakeSerial(unrelated))
        started = time.monotonic()
        with self.assertRaisesRegex(p.ProtocolError, "timed out"):
            connection.request(p.CMD_SAVE_CONFIG, timeout=0.03)
        self.assertLess(time.monotonic() - started, 0.2)

    def test_lock_wait_counts_toward_request_timeout(self):
        serial = FakeSerial()
        connection = p.BoardConnection(serial)
        connection._request_lock.acquire()
        try:
            started = time.monotonic()
            with self.assertRaisesRegex(p.ProtocolError, "another request"):
                connection.request(p.CMD_PING, timeout=0.02)
            self.assertLess(time.monotonic() - started, 0.2)
            self.assertEqual(serial.written, b"")
        finally:
            connection._request_lock.release()

    def test_get_config_rejects_truncated_ack(self):
        serial = FakeSerial(
            p.build_frame(p.RESP_ACK_BASE | p.CMD_GET_CONFIG, b"too short")
        )
        connection = p.BoardConnection(serial)
        with self.assertRaisesRegex(p.ProtocolError, "config response"):
            connection.get_config()

    def test_calibration_commands_parse_status(self):
        payload = p._CALIBRATION_STRUCT.pack(1, 2051, 2043, 0.0175, 9876)
        serial = FakeSerial(
            p.build_frame(p.RESP_ACK_BASE | p.CMD_START_CALIBRATION, payload)
            + p.build_frame(p.RESP_ACK_BASE | p.CMD_CALIBRATION_STATUS, payload)
        )
        connection = p.BoardConnection(serial)

        started = connection.start_calibration()
        polled = connection.calibration_status()

        self.assertTrue(started.active)
        self.assertEqual((started.center_x, started.center_y), (2051, 2043))
        self.assertAlmostEqual(started.deadzone, 0.0175, places=6)
        self.assertEqual(started.remaining_ms, 9876)
        self.assertEqual(polled, started)
        self.assertEqual(
            bytes(serial.written),
            p.build_frame(p.CMD_START_CALIBRATION)
            + p.build_frame(p.CMD_CALIBRATION_STATUS),
        )

    def test_calibration_status_requires_exact_wire_size(self):
        payload = p._CALIBRATION_STRUCT.pack(0, 2048, 2048, 0.06, 0)
        for bad in (payload[:-1], payload + b"\x00"):
            with self.subTest(size=len(bad)):
                with self.assertRaisesRegex(p.ProtocolError, "calibration status"):
                    p.parse_calibration_status(bad)


if __name__ == "__main__":
    unittest.main()
