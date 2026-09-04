"""COM-port discovery and board-verification helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from serial.tools import list_ports


@dataclass
class CandidatePort:
    port: str
    description: str
    hwid: str
    vid: Optional[int]
    pid: Optional[int]
    serial_number: str = ""


def candidate_ports() -> list[CandidatePort]:
    result = []
    for port in list_ports.comports():
        vid = getattr(port, "vid", None)
        pid = getattr(port, "pid", None)
        result.append(
            CandidatePort(
                port=port.device,
                description=port.description or "",
                hwid=port.hwid or "",
                vid=vid,
                pid=pid,
                serial_number=getattr(port, "serial_number", None) or "",
            )
        )
    return result


def likely_mapper_port(candidate: CandidatePort) -> bool:
    """Return whether descriptors identify the stable configurable mapper.

    The definitive check is always the CDC PING handshake; this is only used
    to make the UI safer and easier to read.
    """
    text = (candidate.description + " " + candidate.hwid).lower()
    if candidate.vid is not None and candidate.vid != 0xCAFE:
        return False
    if candidate.pid is not None:
        return candidate.pid == 0x4007
    if "trace" in text or "debug" in text or "4008" in text or "4005" in text:
        return False
    return (
        "pico kbm mapper" in text
        or ("cafe" in text and "4007" in text)
    )


def legacy_mapper_port(candidate: CandidatePort) -> bool:
    """Return whether this is the old PID used only for one-time recovery flash.

    PID 0x4005 is never considered configurable because it does not implement
    the framed protocol. Keeping it separate prevents the debug/trace images
    from being offered as normal mapper connections.
    """
    text = (candidate.description + " " + candidate.hwid).lower()
    if candidate.vid is not None and candidate.vid != 0xCAFE:
        return False
    if candidate.pid is not None:
        return candidate.pid == 0x4005
    return "cafe" in text and "4005" in text


def descriptor_flash_port(candidate: CandidatePort) -> bool:
    """Descriptor-only recovery eligibility; never a handshake substitute."""
    return likely_mapper_port(candidate) or legacy_mapper_port(candidate)


def find_likely_ports() -> list[CandidatePort]:
    return [port for port in candidate_ports() if likely_mapper_port(port)]
