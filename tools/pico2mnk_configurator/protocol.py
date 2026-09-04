"""Framed CDC protocol used by the PicoController2MNK firmware."""

from __future__ import annotations

import struct
import threading
import time
import zlib
from dataclasses import dataclass
from typing import Optional

import serial

PROTOCOL_VERSION = 1
SCHEMA_VERSION = 1
MAX_PAYLOAD = 8000
FRAME_MAGIC = 0xA5
HEADER_SIZE = 6
CRC_SIZE = 4

CMD_PING = 0x01
CMD_GET_CONFIG = 0x02
CMD_SET_CONFIG = 0x03
CMD_SAVE_CONFIG = 0x04
CMD_FACTORY_RESET = 0x05
CMD_MONITOR = 0x06
CMD_START_CALIBRATION = 0x07
CMD_CALIBRATION_STATUS = 0x08
RESP_ACK_BASE = 0x80
RESP_STATE = 0x21
RESP_ERROR = 0x7F

ERROR_NAMES = {
    1: "bad CRC",
    2: "bad length",
    3: "bad command",
    4: "invalid config",
    5: "flash write failed",
}

_IDENTITY_STRUCT = struct.Struct("<8sHHHHHHH32s32sB3s")
_STATE_STRUCT = struct.Struct("<IffffHHHH")
_CALIBRATION_STRUCT = struct.Struct("<BHHfI")
_HEADER_STRUCT = struct.Struct("<BBBBH")


@dataclass
class BoardIdentity:
    magic: bytes
    protocol_version: int
    schema_version: int
    firmware_major: int
    firmware_minor: int
    firmware_patch: int
    vid: int
    pid: int
    product: str
    serial: str
    persisted: bool


@dataclass
class MonitorState:
    buttons: int
    lx: float
    ly: float
    rx: float
    ry: float
    raw_lx: int
    raw_ly: int
    raw_rx: int
    raw_ry: int


@dataclass
class CalibrationStatus:
    active: bool
    center_x: int
    center_y: int
    deadzone: float
    remaining_ms: int


class ProtocolError(RuntimeError):
    pass


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def build_frame(command: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload too large: {len(payload)}")
    header = _HEADER_STRUCT.pack(FRAME_MAGIC, PROTOCOL_VERSION, command, 0, len(payload))
    return header + payload + struct.pack("<I", crc32(header + payload))


def parse_identity(payload: bytes) -> BoardIdentity:
    if len(payload) != _IDENTITY_STRUCT.size:
        raise ProtocolError(
            f"identity payload is {len(payload)} bytes, expected {_IDENTITY_STRUCT.size}"
        )
    fields = _IDENTITY_STRUCT.unpack(payload)
    return BoardIdentity(
        magic=fields[0],
        protocol_version=fields[1],
        schema_version=fields[2],
        firmware_major=fields[3],
        firmware_minor=fields[4],
        firmware_patch=fields[5],
        vid=fields[6],
        pid=fields[7],
        product=fields[8].rstrip(b"\x00").decode("utf-8", errors="replace"),
        serial=fields[9].rstrip(b"\x00").decode("utf-8", errors="replace"),
        persisted=bool(fields[10]),
    )


def parse_monitor_state(payload: bytes) -> MonitorState:
    if len(payload) != _STATE_STRUCT.size:
        raise ProtocolError(
            f"monitor state is {len(payload)} bytes, expected {_STATE_STRUCT.size}"
        )
    return MonitorState(*_STATE_STRUCT.unpack(payload))


def parse_calibration_status(payload: bytes) -> CalibrationStatus:
    if len(payload) != _CALIBRATION_STRUCT.size:
        raise ProtocolError(
            f"calibration status is {len(payload)} bytes, expected {_CALIBRATION_STRUCT.size}"
        )
    active, center_x, center_y, deadzone, remaining_ms = _CALIBRATION_STRUCT.unpack(payload)
    return CalibrationStatus(bool(active), center_x, center_y, deadzone, remaining_ms)


class BoardConnection:
    """A verified connection to one Pico KBM Mapper board."""

    def __init__(self, ser: serial.Serial):
        self.ser = ser
        self.identity: Optional[BoardIdentity] = None
        self.monitor_state: Optional[MonitorState] = None
        self.monitor_state_received_at: Optional[float] = None
        self._rx_buffer = bytearray()
        self._request_lock = threading.Lock()
        self._last_frame_issue: Optional[str] = None

    @classmethod
    def open(cls, port: str, timeout: float = 1.0) -> "BoardConnection":
        ser = serial.Serial(port, baudrate=115200, timeout=timeout, write_timeout=timeout)
        conn = cls(ser)
        try:
            conn.ping()
        except Exception:
            ser.close()
            raise
        return conn

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass

    def _extract_frame(self) -> Optional[tuple[int, bytes]]:
        """Extract one valid frame, skipping garbage and corrupt candidates."""
        if not self._rx_buffer:
            return None

        magic_byte = bytes((FRAME_MAGIC,))
        positions: list[int] = []
        start = 0
        while True:
            position = self._rx_buffer.find(magic_byte, start)
            if position < 0:
                break
            positions.append(position)
            start = position + 1

        if not positions:
            self._last_frame_issue = (
                f"discarded {len(self._rx_buffer)} non-protocol byte(s)"
            )
            self._rx_buffer.clear()
            return None

        first_incomplete: Optional[int] = None
        for position in positions:
            available = len(self._rx_buffer) - position
            if available < HEADER_SIZE:
                if first_incomplete is None:
                    first_incomplete = position
                continue

            header = bytes(self._rx_buffer[position : position + HEADER_SIZE])
            _magic, version, command, flags, payload_len = _HEADER_STRUCT.unpack(header)
            if version != PROTOCOL_VERSION:
                self._last_frame_issue = f"unsupported protocol version {version}"
                continue
            if flags != 0:
                self._last_frame_issue = f"unsupported response flags 0x{flags:02X}"
                continue
            if payload_len > MAX_PAYLOAD:
                self._last_frame_issue = f"invalid payload length {payload_len}"
                continue

            frame_size = HEADER_SIZE + payload_len + CRC_SIZE
            if available < frame_size:
                if first_incomplete is None:
                    first_incomplete = position
                continue

            frame = bytes(self._rx_buffer[position : position + frame_size])
            expected_crc = struct.unpack_from("<I", frame, HEADER_SIZE + payload_len)[0]
            actual_crc = crc32(frame[: HEADER_SIZE + payload_len])
            if expected_crc != actual_crc:
                self._last_frame_issue = "response CRC mismatch"
                continue

            payload = frame[HEADER_SIZE : HEADER_SIZE + payload_len]
            del self._rx_buffer[: position + frame_size]
            self._last_frame_issue = None
            return command, payload

        if first_incomplete is not None:
            if first_incomplete:
                del self._rx_buffer[:first_incomplete]
                self._last_frame_issue = (
                    f"discarded {first_incomplete} byte(s) before an incomplete frame"
                )
            return None

        self._rx_buffer.clear()
        return None

    def _read_frame(self, deadline: float) -> tuple[int, bytes]:
        while True:
            frame = self._extract_frame()
            if frame is not None:
                command, payload = frame
                if command == RESP_STATE:
                    self.monitor_state = parse_monitor_state(payload)
                    self.monitor_state_received_at = time.monotonic()
                    continue
                return command, payload

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                detail = f" ({self._last_frame_issue})" if self._last_frame_issue else ""
                raise ProtocolError(f"timed out waiting for a response frame{detail}")

            try:
                self.ser.timeout = remaining
                try:
                    waiting = int(getattr(self.ser, "in_waiting", 0) or 0)
                except Exception:
                    waiting = 0
                chunk = self.ser.read(min(max(waiting, 1), HEADER_SIZE + MAX_PAYLOAD + CRC_SIZE))
            except Exception as exc:
                raise ProtocolError(f"serial read failed: {exc}") from exc
            if chunk:
                self._rx_buffer.extend(chunk)

    def _write_frame(self, frame: bytes, deadline: float) -> None:
        offset = 0
        while offset < len(frame):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProtocolError("timed out writing request frame")
            try:
                self.ser.write_timeout = remaining
                written = self.ser.write(frame[offset:])
            except Exception as exc:
                raise ProtocolError(f"serial write failed: {exc}") from exc
            if not written:
                continue
            offset += int(written)
        try:
            self.ser.flush()
        except Exception as exc:
            raise ProtocolError(f"serial flush failed: {exc}") from exc
        if time.monotonic() > deadline:
            raise ProtocolError("timed out writing request frame")

    def request(self, command: int, payload: bytes = b"", timeout: float = 4.0) -> bytes:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        deadline = time.monotonic() + timeout
        if not self._request_lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
            raise ProtocolError("timed out waiting for another request to finish")
        try:
            self._write_frame(build_frame(command, payload), deadline)

            while True:
                resp_command, resp_payload = self._read_frame(deadline)
                if resp_command == RESP_ERROR:
                    code = (
                        int.from_bytes(resp_payload[:4], "little")
                        if len(resp_payload) >= 4
                        else -1
                    )
                    message = resp_payload[4:].rstrip(b"\x00").decode(
                        "utf-8", errors="replace"
                    )
                    raise ProtocolError(
                        f"board error {code}: {ERROR_NAMES.get(code, message) or message}"
                    )
                if resp_command == (RESP_ACK_BASE | command):
                    return resp_payload
                # Ignore unrelated late responses under the same end-to-end deadline.
        finally:
            self._request_lock.release()

    def ping(self) -> BoardIdentity:
        payload = self.request(CMD_PING, timeout=2.0)
        identity = parse_identity(payload)
        if identity.magic != b"P2MNCFG\x00":
            raise ProtocolError("connected device did not answer the Pico2MNK handshake")
        if identity.vid != 0xCAFE or identity.pid != 0x4007:
            raise ProtocolError(
                f"connected device has unexpected USB identity "
                f"VID {identity.vid:04X} PID {identity.pid:04X}"
            )
        if identity.protocol_version != PROTOCOL_VERSION:
            raise ProtocolError(
                f"firmware protocol v{identity.protocol_version} is not supported by this app"
            )
        if identity.schema_version != SCHEMA_VERSION:
            raise ProtocolError(
                f"firmware config schema v{identity.schema_version} is not supported by this app"
            )
        self.identity = identity
        return identity

    def get_config(self) -> bytes:
        payload = self.request(CMD_GET_CONFIG, timeout=5.0)
        if len(payload) != MAX_PAYLOAD:
            raise ProtocolError(
                f"config response is {len(payload)} bytes, expected {MAX_PAYLOAD}"
            )
        return payload

    def set_config(self, payload: bytes) -> None:
        self.request(CMD_SET_CONFIG, payload, timeout=6.0)

    def save_config(self) -> None:
        self.request(CMD_SAVE_CONFIG, timeout=8.0)

    def factory_reset(self) -> None:
        self.request(CMD_FACTORY_RESET, timeout=8.0)

    def set_monitor(self, interval_ms: int) -> None:
        self.request(CMD_MONITOR, struct.pack("<I", int(interval_ms)), timeout=3.0)

    def start_calibration(self) -> CalibrationStatus:
        return parse_calibration_status(self.request(CMD_START_CALIBRATION, timeout=3.0))

    def calibration_status(self) -> CalibrationStatus:
        return parse_calibration_status(self.request(CMD_CALIBRATION_STATUS, timeout=3.0))
