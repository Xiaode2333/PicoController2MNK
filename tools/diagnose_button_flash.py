#!/usr/bin/env python3
"""Diagnose short LT/LB/RB dropouts from Pico CDC logs.

The script accepts either saved CDC text logs or a live serial port. It parses
lines printed by the firmware capture/debug paths, decodes controller reports,
and highlights brief pressed -> released -> pressed pulses that can look like
mouse button flashes in game.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator


SW_BTN_LB = 0x400000
SW_BTN_RB = 0x000040
SW_BTN_LT = 0x800000
SWITCH_PRO_NEUTRAL_BUTTON = 0x008000

DPAD_BYTE = 5
AXIS_LX_BYTE = 6
AXIS_LY_BYTE = 7
AXIS_RX_BYTE = 8
AXIS_RY_BYTE = 9
AXIS_RT_BYTE = 10
AXIS_LT_BYTE = 11
BUTTON_BYTE_8 = 8
BUTTON_BYTE_9 = 9
BUTTON_LB_MASK = 0x40
BUTTON_RB_MASK = 0x80
BUTTON_LT_DIGITAL_MASK = 0x01

RAW_RE = re.compile(r"\braw=([0-9A-Fa-f]{2}(?:[ ,:]+[0-9A-Fa-f]{2})*)")
REPORT_RE = re.compile(
    r"\bREPORT\s+#?(?P<num>\d+)?\s*(?:len=(?P<len1>\d+))?\s*:\s*"
    r"(?P<hex>[0-9A-Fa-f]{2}(?:[ ,:]+[0-9A-Fa-f]{2})*)"
)
SW_BTN_RE = re.compile(r"\bsw_btn=([0-9A-Fa-f]{1,8})")
LEGACY_RE = re.compile(r"\bu8_dpad=[0-9A-Fa-f]{2}.*?\bb8=([0-9A-Fa-f]{2})\s+b9=([0-9A-Fa-f]{2})")
CAPTURE_SAMPLE_RE = re.compile(r"\bsample=(\d+)/(\d+)")
REPORT_NUM_RE = re.compile(r"\bREPORT\s+#?(\d+)")
MOUSE_OUT_RE = re.compile(r"\bMOUSE_OUT\b.*?\bbuttons=([0-9A-Fa-f]{2})")
TRACE_TIME_RE = re.compile(r"\bt_us=(\d+)")


@dataclass
class DecodedReport:
    source: str
    line_no: int
    time_s: float
    seq: int | None
    layout: str
    lb: bool
    rb: bool
    lt: bool
    raw: bytes | None
    line: str


@dataclass
class MouseOutput:
    source: str
    line_no: int
    time_s: float
    left: bool
    right: bool
    buttons: int
    line: str


@dataclass
class Pulse:
    button: str
    start: DecodedReport
    end: DecodedReport
    before: DecodedReport | None
    after: DecodedReport | None

    @property
    def duration_ms(self) -> float:
        return (self.end.time_s - self.start.time_s) * 1000.0


def parse_hex_bytes(text: str) -> bytes:
    return bytes(int(part, 16) for part in re.findall(r"[0-9A-Fa-f]{2}", text))


def switch_stick_x(stick: bytes) -> int:
    return stick[0] | ((stick[1] & 0x0F) << 8)


def switch_stick_y(stick: bytes) -> int:
    return (stick[1] >> 4) | (stick[2] << 4)


def switch_report_buttons(report: bytes) -> int | None:
    if len(report) < 12 or report[0] not in (0x30, 0x31, 0x32):
        return None
    return report[3] | (report[4] << 8) | (report[5] << 16)


def legacy_buttons(report: bytes) -> tuple[bool, bool, bool] | None:
    if len(report) <= BUTTON_BYTE_9:
        return None
    b8 = report[BUTTON_BYTE_8]
    b9 = report[BUTTON_BYTE_9]
    return (
        bool(b8 & BUTTON_LB_MASK),
        bool(b8 & BUTTON_RB_MASK),
        bool(b9 & BUTTON_LT_DIGITAL_MASK),
    )


def report_looks_all_zero(report: bytes) -> bool:
    return bool(report) and all(byte == 0 for byte in report)


def switch_fake_disconnect_reason(report: bytes) -> str | None:
    buttons = switch_report_buttons(report)
    if buttons is None:
        return None

    raw_lx = switch_stick_x(report[6:9])
    raw_ly = switch_stick_y(report[6:9])
    raw_rx = switch_stick_x(report[9:12])
    raw_ry = switch_stick_y(report[9:12])

    if buttons == 0 and raw_lx == 0 and raw_ly == 0 and raw_rx == 0 and raw_ry == 0:
        return "switch_zero_state"

    without_neutral = buttons & ~SWITCH_PRO_NEUTRAL_BUTTON
    centered = (
        1920 <= raw_lx <= 2176
        and 1920 <= raw_ly <= 2176
        and 1920 <= raw_rx <= 2176
        and 1920 <= raw_ry <= 2176
    )
    if without_neutral == 0x000001 and centered:
        return "switch_idle_dpad_up"

    return None


def legacy_fake_disconnect_reason(report: bytes) -> str | None:
    if len(report) <= BUTTON_BYTE_9:
        return None
    if all(report[i] == 0 for i in range(DPAD_BYTE, BUTTON_BYTE_9 + 1)):
        return "legacy_zero_state"

    dpad = report[DPAD_BYTE] & 0x0F
    centered = (
        124 <= report[AXIS_LX_BYTE] <= 132
        and 124 <= report[AXIS_LY_BYTE] <= 132
        and 124 <= report[AXIS_RX_BYTE] <= 132
        and 124 <= report[AXIS_RY_BYTE] <= 132
    )
    if (
        dpad == 0
        and centered
        and report[AXIS_RT_BYTE] == 0
        and report[AXIS_LT_BYTE] == 0
        and report[BUTTON_BYTE_8] == 0
        and report[BUTTON_BYTE_9] == 0
    ):
        return "legacy_idle_dpad_up"

    return None


def extract_time(line: str, fallback: float, sample_interval_ms: float) -> float:
    sample = CAPTURE_SAMPLE_RE.search(line)
    if sample:
        return (int(sample.group(1)) - 1) * sample_interval_ms / 1000.0
    return fallback


def extract_seq(line: str) -> int | None:
    report_num = REPORT_NUM_RE.search(line)
    if report_num:
        return int(report_num.group(1))
    sample = CAPTURE_SAMPLE_RE.search(line)
    if sample:
        return int(sample.group(1))
    return None


def decode_line(
    line: str,
    line_no: int,
    source: str,
    fallback_time_s: float,
    sample_interval_ms: float,
    prefer_fallback_time: bool = False,
) -> DecodedReport | None:
    raw: bytes | None = None
    raw_match = RAW_RE.search(line)
    if raw_match:
        raw = parse_hex_bytes(raw_match.group(1))
    else:
        report_match = REPORT_RE.search(line)
        if report_match:
            raw = parse_hex_bytes(report_match.group("hex"))

    time_s = fallback_time_s if prefer_fallback_time else extract_time(line, fallback_time_s, sample_interval_ms)
    seq = extract_seq(line)

    sw_match = SW_BTN_RE.search(line)
    if sw_match:
        buttons = int(sw_match.group(1), 16)
        return DecodedReport(
            source=source,
            line_no=line_no,
            time_s=time_s,
            seq=seq,
            layout="switch",
            lb=bool(buttons & SW_BTN_LB),
            rb=bool(buttons & SW_BTN_RB),
            lt=bool(buttons & SW_BTN_LT),
            raw=raw,
            line=line.rstrip(),
        )

    legacy_match = LEGACY_RE.search(line)
    if legacy_match:
        b8 = int(legacy_match.group(1), 16)
        return DecodedReport(
            source=source,
            line_no=line_no,
            time_s=time_s,
            seq=seq,
            layout="legacy",
            lb=bool(b8 & BUTTON_LB_MASK),
            rb=bool(b8 & BUTTON_RB_MASK),
            lt=bool(int(legacy_match.group(2), 16) & BUTTON_LT_DIGITAL_MASK),
            raw=raw,
            line=line.rstrip(),
        )

    if raw:
        buttons = switch_report_buttons(raw)
        if buttons is not None:
            return DecodedReport(
                source=source,
                line_no=line_no,
                time_s=time_s,
                seq=seq,
                layout="switch",
                lb=bool(buttons & SW_BTN_LB),
                rb=bool(buttons & SW_BTN_RB),
                lt=bool(buttons & SW_BTN_LT),
                raw=raw,
                line=line.rstrip(),
            )

        legacy = legacy_buttons(raw)
        if legacy is not None:
            lb, rb, lt = legacy
            return DecodedReport(
                source=source,
                line_no=line_no,
                time_s=time_s,
                seq=seq,
                layout="legacy",
                lb=lb,
                rb=rb,
                lt=lt,
                raw=raw,
                line=line.rstrip(),
            )

    return None


def decode_mouse_output(
    line: str,
    line_no: int,
    source: str,
    fallback_time_s: float,
) -> MouseOutput | None:
    match = MOUSE_OUT_RE.search(line)
    if not match:
        return None

    buttons = int(match.group(1), 16)
    trace_time = TRACE_TIME_RE.search(line)
    time_s = (
        int(trace_time.group(1)) / 1_000_000.0
        if trace_time
        else fallback_time_s
    )
    return MouseOutput(
        source=source,
        line_no=line_no,
        time_s=time_s,
        left=bool(buttons & 0x01),
        right=bool(buttons & 0x02),
        buttons=buttons,
        line=line.rstrip(),
    )


def iter_file_lines(paths: list[Path]) -> Iterator[tuple[str, int, str, float]]:
    for path in paths:
        start = time.monotonic()
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, 1):
                yield str(path), line_no, line, time.monotonic() - start


def iter_serial_lines(
    port: str,
    baud: int,
    command: str | None,
    repeat_command_s: float | None,
) -> Iterator[tuple[str, int, str, float]]:
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise SystemExit("pyserial is required for --serial. Install with: python3 -m pip install pyserial") from exc

    with serial.Serial(port, baudrate=baud, timeout=0.2) as ser:
        if command:
            ser.write((command.rstrip("\r\n") + "\r\n").encode("utf-8"))
        start = time.monotonic()
        next_command_s = repeat_command_s if command and repeat_command_s else None
        line_no = 0
        while True:
            elapsed_s = time.monotonic() - start
            if next_command_s is not None and elapsed_s >= next_command_s:
                ser.write((command.rstrip("\r\n") + "\r\n").encode("utf-8"))
                next_command_s += repeat_command_s

            data = ser.readline()
            if not data:
                continue
            line_no += 1
            yield port, line_no, data.decode("utf-8", errors="replace"), elapsed_s


def find_pulses(reports: list[DecodedReport], button: str, max_ms: float) -> list[Pulse]:
    pulses: list[Pulse] = []
    attr = button.lower()
    last_pressed: DecodedReport | None = None
    release_start: DecodedReport | None = None
    before_release: DecodedReport | None = None

    for report in reports:
        pressed = bool(getattr(report, attr))
        if pressed:
            if release_start is not None:
                duration_ms = (report.time_s - release_start.time_s) * 1000.0
                if last_pressed is not None and duration_ms <= max_ms:
                    pulses.append(Pulse(button, release_start, report, before_release, report))
                release_start = None
                before_release = None
            last_pressed = report
        else:
            if last_pressed is not None and release_start is None:
                release_start = report
                before_release = last_pressed

    return pulses


def find_mouse_output_pulses(outputs: list[MouseOutput], button: str, max_ms: float) -> list[tuple[MouseOutput, MouseOutput, MouseOutput | None]]:
    pulses: list[tuple[MouseOutput, MouseOutput, MouseOutput | None]] = []
    attr = "left" if button == "left" else "right"
    last_down: MouseOutput | None = None
    release_start: MouseOutput | None = None

    for output in outputs:
        pressed = bool(getattr(output, attr))
        if pressed:
            if release_start is not None:
                duration_ms = (output.time_s - release_start.time_s) * 1000.0
                if last_down is not None and duration_ms <= max_ms:
                    pulses.append((release_start, output, last_down))
                release_start = None
            last_down = output
        else:
            if last_down is not None and release_start is None:
                release_start = output

    return pulses


def report_gap_warnings(reports: list[DecodedReport], gap_ms: float) -> list[tuple[DecodedReport, DecodedReport, float]]:
    gaps = []
    for prev, current in zip(reports, reports[1:]):
        delta_ms = (current.time_s - prev.time_s) * 1000.0
        if delta_ms >= gap_ms:
            gaps.append((prev, current, delta_ms))
    return gaps


def describe_raw(report: DecodedReport) -> str:
    if not report.raw:
        return "no_raw"
    if report_looks_all_zero(report.raw):
        return "all_zero"
    if report.layout == "switch":
        return switch_fake_disconnect_reason(report.raw) or "switch_normal"
    if report.layout == "legacy":
        return legacy_fake_disconnect_reason(report.raw) or "legacy_normal"
    return "unknown"


def print_pulse(pulse: Pulse) -> None:
    start = pulse.start
    end = pulse.end
    print(
        f"[PULSE] {pulse.button} released for {pulse.duration_ms:.2f} ms "
        f"at {start.source}:{start.line_no} -> {end.line_no} "
        f"layout={start.layout} reason={describe_raw(start)}"
    )
    if pulse.before:
        print(f"  before: {pulse.before.line}")
    print(f"  drop:   {start.line}")
    print(f"  back:   {end.line}")


def analyze(reports: list[DecodedReport], max_pulse_ms: float, gap_ms: float) -> int:
    if not reports:
        print("No decodable controller reports found.")
        return 2

    print(f"Decoded reports: {len(reports)}")
    print(f"Layouts: {', '.join(sorted(set(report.layout for report in reports)))}")

    exit_code = 0
    for button in ("LT", "LB", "RB"):
        pressed_count = sum(1 for report in reports if getattr(report, button.lower()))
        pulses = find_pulses(reports, button, max_pulse_ms)
        print(f"{button}: pressed reports={pressed_count}, short release pulses={len(pulses)}")
        for pulse in pulses[:20]:
            print_pulse(pulse)
        if len(pulses) > 20:
            print(f"  ... {len(pulses) - 20} more {button} pulses omitted")
        if pulses:
            exit_code = 1

    gaps = report_gap_warnings(reports, gap_ms)
    print(f"Report gaps >= {gap_ms:.1f} ms: {len(gaps)}")
    for prev, current, delta_ms in gaps[:20]:
        print(
            f"[GAP] {delta_ms:.2f} ms between "
            f"{prev.source}:{prev.line_no} and {current.line_no}"
        )

    fake_counts: dict[str, int] = {}
    for report in reports:
        reason = describe_raw(report)
        if reason not in ("switch_normal", "legacy_normal", "no_raw"):
            fake_counts[reason] = fake_counts.get(reason, 0) + 1

    if fake_counts:
        print("Suspicious raw report counts:")
        for reason, count in sorted(fake_counts.items()):
            print(f"  {reason}: {count}")

    return exit_code


def analyze_mouse_outputs(outputs: list[MouseOutput], max_pulse_ms: float) -> int:
    if not outputs:
        print("Mouse output trace: no MOUSE_OUT lines found.")
        return 0

    print(f"Mouse output changes: {len(outputs)}")
    exit_code = 0

    for button in ("left", "right"):
        pulses = find_mouse_output_pulses(outputs, button, max_pulse_ms)
        pressed_count = sum(1 for output in outputs if getattr(output, button))
        print(f"mouse {button}: pressed changes={pressed_count}, short release pulses={len(pulses)}")

        for release_start, back, before in pulses[:20]:
            duration_ms = (back.time_s - release_start.time_s) * 1000.0
            print(
                f"[MOUSE_PULSE] {button} released for {duration_ms:.2f} ms "
                f"at {release_start.source}:{release_start.line_no} -> {back.line_no}"
            )
            if before is not None:
                print(f"  before: {before.line}")
            print(f"  drop:   {release_start.line}")
            print(f"  back:   {back.line}")

        if pulses:
            exit_code = 1

    return exit_code


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze Pico CDC controller logs for brief LB/RB dropouts."
    )
    parser.add_argument("logs", nargs="*", type=Path, help="Saved CDC log files to analyze.")
    parser.add_argument("--serial", help="Read live CDC serial port, for example /dev/ttyACM0 or COM5.")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate placeholder for CDC.")
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Save raw serial/log lines. Defaults to logs/button_flash_<timestamp>.log in serial mode.",
    )
    parser.add_argument(
        "--command",
        default=None,
        help="Command to send after opening serial. Defaults to 'capture button_flash' in serial mode.",
    )
    parser.add_argument(
        "--repeat-command",
        type=float,
        default=None,
        help="With --serial and --command, resend the command every N seconds. Defaults to 2 seconds in serial mode.",
    )
    parser.add_argument(
        "--sample-interval-ms",
        type=float,
        default=100.0,
        help="Time between CAPTURE samples in current firmware.",
    )
    parser.add_argument(
        "--max-pulse-ms",
        type=float,
        default=120.0,
        help="Pressed -> released -> pressed intervals at or below this are flagged.",
    )
    parser.add_argument(
        "--gap-ms",
        type=float,
        default=40.0,
        help="Warn when decoded report timestamps have gaps at or above this length.",
    )
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=8.0,
        help="With --serial, stop with a hint if no decodable reports arrive for this many seconds.",
    )
    return parser


def main(argv: list[str]) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not args.logs and not args.serial:
        parser.error("provide at least one log file or --serial")

    decoded: list[DecodedReport] = []
    mouse_outputs: list[MouseOutput] = []
    command = args.command
    repeat_command = args.repeat_command
    log_path: Path | None = args.log

    if args.serial and command is None:
        command = "capture button_flash"

    if args.serial and command and repeat_command is None:
        repeat_command = 2.0

    if args.serial and log_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = Path("logs") / f"button_flash_{stamp}.log"

    sources: Iterable[tuple[str, int, str, float]]
    if args.serial:
        print(
            f"Opening {args.serial}; sending '{command}'"
            + (f" every {repeat_command:g}s." if repeat_command else "."),
            file=sys.stderr,
        )
        sources = iter_serial_lines(args.serial, args.baud, command, repeat_command)
    else:
        sources = iter_file_lines(args.logs)

    serial_start = time.monotonic()
    log_handle = None

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("w", encoding="utf-8", errors="replace", newline="")
        print(f"Saving raw log to {log_path}", file=sys.stderr)

    try:
        for source, line_no, line, fallback_time_s in sources:
            if log_handle is not None:
                log_handle.write(line)
                log_handle.flush()

            report = decode_line(
                line,
                line_no,
                source,
                fallback_time_s,
                args.sample_interval_ms,
                prefer_fallback_time=bool(args.serial),
            )
            mouse_output = decode_mouse_output(line, line_no, source, fallback_time_s)

            if mouse_output:
                mouse_outputs.append(mouse_output)

            if report:
                decoded.append(report)
                if args.serial and len(decoded) % 50 == 0:
                    print(f"decoded {len(decoded)} reports...", file=sys.stderr)
            elif args.serial and not decoded and time.monotonic() - serial_start >= args.idle_timeout:
                print(
                    "No decodable reports received from the serial port. "
                    "If this is the trace firmware, check that the controller receiver is connected "
                    "to the Pico host port and that no other serial monitor has the COM port open.",
                    file=sys.stderr,
                )
                break
    except KeyboardInterrupt:
        pass
    finally:
        if log_handle is not None:
            log_handle.close()

    report_result = analyze(decoded, args.max_pulse_ms, args.gap_ms)
    mouse_result = analyze_mouse_outputs(mouse_outputs, args.max_pulse_ms)
    return report_result or mouse_result


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
