"""Read live controller-state transitions from a running Pico mapper."""

from __future__ import annotations

import argparse
import time

from tools.pico2mnk_configurator.protocol import (
    BoardConnection,
    RESP_STATE,
    parse_monitor_state,
)


BUTTON_MASKS = (
    (0x000001, "Y"),
    (0x000002, "X"),
    (0x000004, "B"),
    (0x000008, "A"),
    (0x000040, "RB"),
    (0x000080, "RT"),
    (0x000100, "Menu"),
    (0x000200, "Option"),
    (0x000400, "R3"),
    (0x000800, "L3"),
    (0x002000, "Snapshot"),
    (0x010000, "DpadDown"),
    (0x020000, "DpadUp"),
    (0x040000, "DpadRight"),
    (0x080000, "DpadLeft"),
    (0x400000, "LB"),
    (0x800000, "LT"),
)


def button_names(buttons: int) -> str:
    names = [name for mask, name in BUTTON_MASKS if buttons & mask]
    return "+".join(names) if names else "neutral"


def monitor(port: str, duration: float, interval_ms: int) -> int:
    connection = BoardConnection.open(port, timeout=1.5)
    started = time.monotonic()
    deadline = started + duration
    last_buttons: int | None = None
    last_frame_at: float | None = None
    max_gap_ms = 0.0
    frame_count = 0
    transition_count = 0

    try:
        connection.set_monitor(interval_ms)
        print(
            f"Monitoring {port} for {duration:.1f}s at {interval_ms}ms; "
            "printing every button transition.",
            flush=True,
        )

        while time.monotonic() < deadline:
            waiting = int(getattr(connection.ser, "in_waiting", 0) or 0)
            chunk = connection.ser.read(min(max(waiting, 1), 4096))
            if chunk:
                connection._rx_buffer.extend(chunk)

            while True:
                frame = connection._extract_frame()
                if frame is None:
                    break
                command, payload = frame
                if command != RESP_STATE:
                    continue

                now = time.monotonic()
                state = parse_monitor_state(payload)
                frame_count += 1
                if last_frame_at is not None:
                    max_gap_ms = max(max_gap_ms, (now - last_frame_at) * 1000.0)
                last_frame_at = now

                if state.buttons != last_buttons:
                    elapsed_ms = (now - started) * 1000.0
                    dropped = (
                        last_buttons is not None
                        and (last_buttons & 0x800000) != 0
                        and (state.buttons & 0x800000) == 0
                    )
                    marker = " LT_DROP" if dropped else ""
                    print(
                        f"{elapsed_ms:9.1f} ms  sw_btn=0x{state.buttons:06X}  "
                        f"{button_names(state.buttons)}  "
                        f"raw=({state.raw_lx},{state.raw_ly},"
                        f"{state.raw_rx},{state.raw_ry}){marker}",
                        flush=True,
                    )
                    transition_count += 1
                    last_buttons = state.buttons
    finally:
        try:
            connection.set_monitor(0)
        except Exception as exc:
            print(f"Warning: could not stop board monitor cleanly: {exc}", flush=True)
        connection.close()

    print(
        f"Summary: frames={frame_count}, transitions={transition_count}, "
        f"max_frame_gap={max_gap_ms:.1f}ms",
        flush=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM6")
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--interval-ms", type=int, default=10)
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("--duration must be greater than zero")
    if not 10 <= args.interval_ms <= 1000:
        parser.error("--interval-ms must be in 10..1000")
    return monitor(args.port, args.duration, args.interval_ms)


if __name__ == "__main__":
    raise SystemExit(main())
