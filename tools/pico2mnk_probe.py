#!/usr/bin/env python3
"""Scan COM ports for a PicoController2MNK board.

Usage:
    poetry run python tools/pico2mnk_probe.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.pico2mnk_configurator.device_locator import candidate_ports, likely_mapper_port
from tools.pico2mnk_configurator.protocol import BoardConnection


def main() -> int:
    ports = candidate_ports()
    if not ports:
        print("No COM ports found.")
        return 1

    likely = [p for p in ports if likely_mapper_port(p)]
    print(f"COM ports found: {len(ports)}, likely Pico mapper ports: {len(likely)}")
    print()

    checked = 0
    for candidate in ports:
        if not likely_mapper_port(candidate):
            continue
        checked += 1
        usb_serial = candidate.serial_number or "(unknown)"
        print(f"Trying {candidate.port}  ({candidate.description}) serial={usb_serial}")
        try:
            connection = BoardConnection.open(candidate.port, timeout=1.0)
            identity = connection.identity
            print(
                f"  OK: {identity.product} serial={identity.serial} "
                f"fw={identity.firmware_major}.{identity.firmware_minor}.{identity.firmware_patch} "
                f"persisted={identity.persisted}"
            )
            connection.close()
            return 0
        except Exception as exc:
            print(f"  no handshake: {exc}")
            if candidate.serial_number == "000001":
                print("  USB serial is still '000001': this looks like the OLD firmware.")
                print("  The new firmware was not flashed (or the UF2 build is stale). Rebuild and reflash.")

    if checked == 0:
        print("No likely Pico mapper COM port found.")
        print("Check Device Manager for a new COM port after reboot, or USB VID 0xCAFE.")
    else:
        print()
        print("No port answered the Pico2MNK handshake.")
        print("Possible causes:")
        print("  - The board is still in BOOTSEL mode (shows RPI-RP2 drive, no COM port).")
        print("  - A USB serial number of 000001 means the old firmware was flashed.")
        print("  - Windows assigned a new COM port; refresh Device Manager.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
