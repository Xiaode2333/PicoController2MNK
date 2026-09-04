"""Safe RP2040 UF2 flasher.

Flashing is deliberately conservative:
1. The app must already have verified a normal Pico KBM Mapper board.
2. Exactly one RP2 bootloader drive must be present.
3. ``INFO_UF2.TXT`` must identify an RP2040 bootloader.
4. The selected file must be a valid RP2040 family UF2.
"""

from __future__ import annotations

import shutil
import string
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

UF2_MAGIC_0 = 0x0A324655
UF2_MAGIC_1 = 0x9E5D5157
UF2_MAGIC_END = 0x0AB16F30
UF2_FLAG_FAMILY_ID_PRESENT = 0x00002000
RP2040_FAMILY_ID = 0xE48BFF56
STABLE_PRODUCT_MARKER = b"Pico KBM Mapper\x00"
REJECTED_PRODUCT_MARKERS = (
    b"Pico KBM Mapper Trace",
    b"Pico KBM Debug Adapter",
)


@dataclass
class BootloaderDrive:
    path: Path
    info_text: str


def _drive_exists(path: Path) -> bool:
    return path.exists()


def find_bootloader_drives() -> list[BootloaderDrive]:
    drives: list[BootloaderDrive] = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        info_path = root / "INFO_UF2.TXT"
        try:
            if not _drive_exists(info_path):
                continue
            text = info_path.read_text(encoding="utf-8", errors="replace")
            drives.append(BootloaderDrive(path=root, info_text=text))
        except OSError:
            continue
    return drives


def verify_uf2(path: Path) -> tuple[int, int]:
    """Return (number_of_blocks, family_id) after validating a UF2 file."""
    data = path.read_bytes()
    if len(data) < 512 or len(data) % 512 != 0:
        raise ValueError(f"{path.name} is not a valid UF2 file (bad size)")
    block_count = len(data) // 512

    family_id: Optional[int] = None
    seen_block_numbers: set[int] = set()
    for index in range(block_count):
        block = data[index * 512 : (index + 1) * 512]
        magic0 = int.from_bytes(block[0:4], "little")
        magic1 = int.from_bytes(block[4:8], "little")
        magic_end = int.from_bytes(block[508:512], "little")
        flags = int.from_bytes(block[8:12], "little")
        payload_size = int.from_bytes(block[16:20], "little")
        block_no = int.from_bytes(block[20:24], "little")
        total_blocks = int.from_bytes(block[24:28], "little")
        block_family = int.from_bytes(block[28:32], "little")

        if magic0 != UF2_MAGIC_0 or magic1 != UF2_MAGIC_1 or magic_end != UF2_MAGIC_END:
            raise ValueError(f"{path.name}: block {index} has an invalid UF2 magic")
        if not flags & UF2_FLAG_FAMILY_ID_PRESENT:
            raise ValueError(f"{path.name}: block {index} has no UF2 family-ID flag")
        if payload_size > 476:
            raise ValueError(f"{path.name}: block {index} has an invalid payload size")
        if total_blocks != block_count or block_no >= total_blocks:
            raise ValueError(f"{path.name}: block numbering is inconsistent")
        if block_no in seen_block_numbers:
            raise ValueError(f"{path.name}: duplicate UF2 block number {block_no}")
        seen_block_numbers.add(block_no)
        if family_id is None:
            family_id = block_family
        elif family_id != block_family:
            raise ValueError(f"{path.name}: mixed UF2 families")

    if seen_block_numbers != set(range(block_count)):
        raise ValueError(f"{path.name}: UF2 block numbering is incomplete")

    if family_id != RP2040_FAMILY_ID:
        raise ValueError(
            f"{path.name} is not an RP2040 UF2 (family 0x{family_id:08X}, "
            f"expected 0x{RP2040_FAMILY_ID:08X})"
        )
    return block_count, family_id


def verify_mapper_uf2(path: Path) -> tuple[int, int]:
    """Validate and accept only the stable configurable mapper image."""
    block_count, family_id = verify_uf2(path)
    data = path.read_bytes()
    searchable = bytearray()
    for index in range(block_count):
        block = data[index * 512 : (index + 1) * 512]
        payload_size = int.from_bytes(block[16:20], "little")
        searchable += block[32 : 32 + payload_size]
    haystack = bytes(searchable)
    rejected = next((marker for marker in REJECTED_PRODUCT_MARKERS if marker in haystack), None)
    if rejected is not None:
        product = rejected.decode("ascii", errors="replace")
        raise ValueError(
            f"{path.name} contains the non-configurable {product} firmware; "
            "select pico_kbm_mapper.uf2 instead."
        )
    if STABLE_PRODUCT_MARKER not in haystack:
        raise ValueError(
            f"{path.name} is an RP2040 UF2 but does not contain a "
            "stable Pico KBM Mapper product marker; refusing to flash it."
        )
    return block_count, family_id


def flash_uf2(uf2_path: Path, progress: Optional[Callable[[str], None]] = None) -> None:
    uf2_path = Path(uf2_path)
    verify_mapper_uf2(uf2_path)

    drives = find_bootloader_drives()
    if not drives:
        raise RuntimeError(
            "No RP2 bootloader drive found. Hold BOOTSEL and plug in the board."
        )
    if len(drives) > 1:
        names = ", ".join(str(drive.path) for drive in drives)
        raise RuntimeError(
            f"Refusing to flash: more than one RP2 bootloader drive is present ({names}). "
            "Disconnect other RP2040 boards."
        )

    drive = drives[0]
    if "RP2040" not in drive.info_text.upper() and "RP2" not in drive.info_text.upper():
        raise RuntimeError(
            f"Drive {drive.path} does not look like an RP2040 bootloader: "
            f"{drive.info_text!r}"
        )

    if progress:
        progress(f"Writing {uf2_path.name} to {drive.path} ...")

    destination = drive.path / uf2_path.name
    shutil.copyfile(uf2_path, destination)

    # Wait for the bootloader to disappear, which means the new image booted.
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        if not _drive_exists(drive.path):
            if progress:
                progress("Flash complete; the board is rebooting.")
            return
        time.sleep(0.2)

    if progress:
        progress("Bootloader drive is still present after 20 seconds; verify the board manually.")
