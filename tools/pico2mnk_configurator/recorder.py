"""Keyboard/mouse macro recorder.

Uses ``pynput`` when available for global low-level input capture. The raw
events are quantized and encoded into the firmware macro step format.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .config_model import (
    HID_NAME_TO_KEY,
    MACRO_STEP_DELAY,
    MACRO_STEP_KEYBOARD,
    MACRO_STEP_MOUSE,
    MACRO_STEP_MAX,
    MACRO_TRIGGER_PRESS,
    MOD_LEFTALT,
    MOD_LEFTCTRL,
    MOD_LEFTGUI,
    MOD_LEFTSHIFT,
    MOD_RIGHTALT,
    MOD_RIGHTCTRL,
    MOD_RIGHTGUI,
    MOD_RIGHTSHIFT,
    MOUSE_LEFT,
    MOUSE_MIDDLE,
    MOUSE_RIGHT,
    Macro,
    MacroStep,
)

VK_TO_HID = {
    0x08: HID_NAME_TO_KEY["Backspace"],
    0x09: HID_NAME_TO_KEY["Tab"],
    0x0D: HID_NAME_TO_KEY["Enter"],
    0x13: HID_NAME_TO_KEY["Pause"],
    0x14: HID_NAME_TO_KEY["Caps Lock"],
    0x1B: HID_NAME_TO_KEY["Escape"],
    0x20: HID_NAME_TO_KEY["Space"],
    0x21: 0x4B,  # PageUp
    0x22: 0x4E,  # PageDown
    0x23: 0x4D,  # End
    0x24: 0x4A,  # Home
    0x25: HID_NAME_TO_KEY["Left Arrow"],
    0x26: HID_NAME_TO_KEY["Up Arrow"],
    0x27: HID_NAME_TO_KEY["Right Arrow"],
    0x28: HID_NAME_TO_KEY["Down Arrow"],
    0x2C: 0x46,  # PrintScreen
    0x2D: 0x49,  # Insert
    0x2E: HID_NAME_TO_KEY["Delete"],
    0x5B: 0xE3,  # Left GUI
    0x5C: 0xE7,  # Right GUI
    0x6A: 0x55,  # Numpad *
    0x6B: 0x57,  # Numpad +
    0x6D: 0x56,  # Numpad -
    0x6E: 0x63,  # Numpad .
    0x6F: 0x54,  # Numpad /
    0x90: 0x53,  # NumLock
}

VK_MODIFIERS = {
    0x10: MOD_LEFTSHIFT,
    0xA0: MOD_LEFTSHIFT,
    0x11: MOD_LEFTCTRL,
    0xA2: MOD_LEFTCTRL,
    0x12: MOD_LEFTALT,
    0xA4: MOD_LEFTALT,
    0x5B: MOD_LEFTGUI,
    0x5C: MOD_RIGHTGUI,
    0xA1: MOD_RIGHTSHIFT,
    0xA3: MOD_RIGHTCTRL,
    0xA5: MOD_RIGHTALT,
}

CHAR_TO_HID = {
    **{chr(ord("a") + index): 0x04 + index for index in range(26)},
    **{str(index): 0x1D + index for index in range(1, 10)},
    "0": 0x27,
    "-": HID_NAME_TO_KEY["-"],
    "=": HID_NAME_TO_KEY["="],
    "[": HID_NAME_TO_KEY["["],
    "]": HID_NAME_TO_KEY["]"],
    "\\": HID_NAME_TO_KEY["Backslash"],
    ";": HID_NAME_TO_KEY[";"],
    "'": HID_NAME_TO_KEY["'"],
    "`": HID_NAME_TO_KEY["`"],
    ",": HID_NAME_TO_KEY[","],
    ".": HID_NAME_TO_KEY["."],
    "/": HID_NAME_TO_KEY["/"],
    " ": HID_NAME_TO_KEY["Space"],
}


def is_stop_hotkey(key: Any) -> bool:
    """F12 is reserved for stopping capture and is never recorded."""
    try:
        vk = int(getattr(key, "vk", 0) or 0)
    except Exception:
        vk = 0
    try:
        name = str(getattr(key, "name", "") or "").lower()
    except Exception:
        name = ""
    return vk == 0x7B or name == "f12"


def key_to_hid(key: Any) -> tuple[int, int]:
    """Return (hid_keycode_or_0, modifier_flags_or_0)."""
    try:
        vk = int(getattr(key, "vk", 0) or 0)
    except Exception:
        vk = 0

    if vk in VK_MODIFIERS:
        return 0, VK_MODIFIERS[vk]

    if vk:
        if 0x30 <= vk <= 0x39:
            return (0x27 if vk == 0x30 else 0x1E + (vk - 0x31)), 0
        if 0x41 <= vk <= 0x5A:
            return 0x04 + (vk - 0x41), 0
        if 0x60 <= vk <= 0x69:
            return 0x59 + (vk - 0x60), 0  # numpad 0..9
        if 0x70 <= vk <= 0x7B:
            return 0x3A + (vk - 0x70), 0  # F1..F12
        mapped = VK_TO_HID.get(vk)
        if mapped is not None:
            return mapped, 0

    try:
        char = str(getattr(key, "char", "") or "")
    except Exception:
        char = ""
    if char and len(char) == 1:
        mapped = CHAR_TO_HID.get(char.lower())
        if mapped is not None:
            return mapped, 0

    try:
        name = getattr(key, "name", None)
    except Exception:
        name = None
    if name and name in HID_NAME_TO_KEY:
        return HID_NAME_TO_KEY[name], 0

    return 0, 0


@dataclass
class RecordedEvent:
    t: float
    kind: str  # key_down, key_up, mouse_down, mouse_up, wheel, move
    key: Any = None
    button: str = ""
    dx: int = 0
    dy: int = 0
    wheel: int = 0
    x: int = 0
    y: int = 0


class Recorder:
    def __init__(self, record_mouse_motion: bool = False, max_events: int = 120):
        self.record_mouse_motion = record_mouse_motion
        self.max_events = max_events
        self.events: list[RecordedEvent] = []
        self._keyboard_listener = None
        self._mouse_listener = None
        self._started = False
        self._last_move: Optional[tuple[int, int]] = None
        self._warn: Optional[Callable[[str], None]] = None
        self._stop_requested: Optional[Callable[[], None]] = None
        self._stop_hotkey_down = False
        self._limit_warned = False

    @property
    def started(self) -> bool:
        return self._started

    def _append(self, event: RecordedEvent) -> bool:
        if len(self.events) >= self.max_events:
            if self._warn and not self._limit_warned:
                self._limit_warned = True
                self._warn("Event limit reached; stop recording.")
            return False
        self.events.append(event)
        return True

    def start(
        self,
        warn: Optional[Callable[[str], None]] = None,
        stop_requested: Optional[Callable[[], None]] = None,
    ) -> None:
        if self._started:
            return
        try:
            from pynput import keyboard, mouse
        except Exception as exc:
            raise RuntimeError(
                "pynput is required for global macro recording. Run `poetry install` "
                "in the project directory."
            ) from exc

        self._warn = warn
        self._stop_requested = stop_requested
        self.events = []
        self._started = True
        self._last_move = None
        self._stop_hotkey_down = False
        self._limit_warned = False

        def on_key_press(key: Any) -> None:
            if not self._started:
                return
            if is_stop_hotkey(key):
                if not self._stop_hotkey_down:
                    self._stop_hotkey_down = True
                    if self._stop_requested:
                        self._stop_requested()
                return
            self._append(RecordedEvent(time.monotonic(), "key_down", key=key))

        def on_key_release(key: Any) -> None:
            if not self._started:
                return
            if is_stop_hotkey(key):
                self._stop_hotkey_down = False
                return
            self._append(RecordedEvent(time.monotonic(), "key_up", key=key))

        def on_click(x: int, y: int, button: Any, pressed: bool) -> None:
            if not self._started:
                return
            name = getattr(button, "name", "unknown")
            self._append(
                RecordedEvent(
                    time.monotonic(),
                    "mouse_down" if pressed else "mouse_up",
                    button=name,
                    x=x,
                    y=y,
                )
            )

        def on_scroll(x: int, y: int, dx: int, dy: int) -> None:
            if not self._started:
                return
            self._append(RecordedEvent(time.monotonic(), "wheel", wheel=int(dy)))

        def on_move(x: int, y: int) -> None:
            if not self._started or not self.record_mouse_motion:
                return
            if self._last_move is not None:
                dx = x - self._last_move[0]
                dy = y - self._last_move[1]
                if dx or dy:
                    self._append(RecordedEvent(time.monotonic(), "move", dx=dx, dy=dy))
            self._last_move = (x, y)

        self._keyboard_listener = keyboard.Listener(on_press=on_key_press, on_release=on_key_release)
        self._mouse_listener = mouse.Listener(
            on_click=on_click, on_scroll=on_scroll, on_move=on_move
        )
        self._keyboard_listener.daemon = True
        self._mouse_listener.daemon = True
        self._keyboard_listener.start()
        self._mouse_listener.start()

    def stop(self) -> None:
        self._started = False
        try:
            if self._keyboard_listener is not None:
                self._keyboard_listener.stop()
                self._keyboard_listener.join(0.2)
            if self._mouse_listener is not None:
                self._mouse_listener.stop()
                self._mouse_listener.join(0.2)
        except Exception:
            pass
        self._keyboard_listener = None
        self._mouse_listener = None

    def discard_trailing_click(
        self,
        left: int,
        top: int,
        right: int,
        bottom: int,
        within_seconds: float = 1.0,
    ) -> None:
        """Remove only the recent click used to activate the UI Stop button."""
        cutoff = time.monotonic() - within_seconds
        start_index: Optional[int] = None
        for index in range(len(self.events) - 1, -1, -1):
            event = self.events[index]
            if event.t < cutoff:
                break
            if (
                event.kind == "mouse_down"
                and left <= event.x < right
                and top <= event.y < bottom
            ):
                start_index = index
                break
        if start_index is not None:
            del self.events[start_index:]

    def encode(
        self,
        name: str = "Recorded macro",
        trigger_mode: int = MACRO_TRIGGER_PRESS,
    ) -> Macro:
        """Quantize events into state steps whose durations reach the next event.

        Firmware state steps take effect first and then remain active for their
        ``duration_ms``. DELAY steps preserve both device states. Encoding the
        gap before a state change would add the prior state's own duration to
        every timestamp, so gaps belong to the preceding state instead.
        """
        if not self.events:
            raise ValueError("no events recorded")

        events = sorted(self.events, key=lambda event: event.t)
        origin = events[0].t
        transitions: list[tuple[int, MacroStep]] = []
        modifier = 0
        keys: list[int] = []
        mouse_buttons = 0

        def keyboard_state() -> tuple[int, tuple[int, ...]]:
            key_tuple = tuple(sorted(set(keys))[:6] + [0] * 6)
            return modifier, key_tuple[:6]

        for event in events:
            ms = max(0, int(round((event.t - origin) * 1000)))

            if event.kind in ("key_down", "key_up"):
                before = keyboard_state()
                hid_key, hid_mod = key_to_hid(event.key)
                if event.kind == "key_down":
                    if hid_mod:
                        modifier |= hid_mod
                    elif hid_key and hid_key not in keys:
                        keys.append(hid_key)
                else:
                    if hid_mod:
                        modifier &= ~hid_mod
                    elif hid_key in keys:
                        keys.remove(hid_key)
                after = keyboard_state()
                if after != before:
                    transitions.append(
                        (
                            ms,
                            MacroStep(
                                type=MACRO_STEP_KEYBOARD,
                                modifier=after[0],
                                keys=after[1],
                            ),
                        )
                    )
            elif event.kind in ("mouse_down", "mouse_up"):
                bit = {
                    "left": MOUSE_LEFT,
                    "right": MOUSE_RIGHT,
                    "middle": MOUSE_MIDDLE,
                    "unknown": 0,
                }.get(str(event.button), 0)
                if bit:
                    before = mouse_buttons
                    if event.kind == "mouse_down":
                        mouse_buttons |= bit
                    else:
                        mouse_buttons &= ~bit
                    if mouse_buttons != before:
                        transitions.append(
                            (
                                ms,
                                MacroStep(
                                    type=MACRO_STEP_MOUSE,
                                    keys=(mouse_buttons, 0, 0, 0, 0, 0),
                                ),
                            )
                        )
            elif event.kind == "wheel":
                wheel = clamp(event.wheel, -8, 8)
                if wheel:
                    transitions.append(
                        (
                            ms,
                            MacroStep(
                                type=MACRO_STEP_MOUSE,
                                keys=(mouse_buttons, 0, 0, 0, 0, 0),
                                value=wheel,
                            ),
                        )
                    )
            elif event.kind == "move" and (event.dx or event.dy):
                transitions.append(
                    (
                        ms,
                        MacroStep(
                            type=MACRO_STEP_MOUSE,
                            keys=(
                                mouse_buttons,
                                clamp(event.dx, -127, 127),
                                clamp(event.dy, -127, 127),
                                0,
                                0,
                                0,
                            ),
                        ),
                    )
                )

        if not transitions:
            raise ValueError("no supported keyboard or mouse events recorded")

        first_ms = transitions[0][0]
        transitions = [(ms - first_ms, step) for ms, step in transitions]
        steps: list[MacroStep] = []

        def append_timed(step: MacroStep, duration_ms: int) -> None:
            duration_ms = max(1, duration_ms)
            step.duration_ms = min(duration_ms, 0xFFFF)
            steps.append(step)
            remaining = duration_ms - step.duration_ms
            while remaining > 0:
                chunk = min(remaining, 0xFFFF)
                steps.append(MacroStep(type=MACRO_STEP_DELAY, duration_ms=chunk))
                remaining -= chunk

        index = 0
        while index < len(transitions):
            group_end = index + 1
            timestamp = transitions[index][0]
            while group_end < len(transitions) and transitions[group_end][0] == timestamp:
                group_end += 1

            next_ms = (
                transitions[group_end][0]
                if group_end < len(transitions)
                else timestamp + 5
            )
            group_duration = max(1, next_ms - timestamp)
            group_size = group_end - index
            for group_index in range(group_size):
                duration = 1
                if group_index == group_size - 1:
                    duration = max(1, group_duration - (group_size - 1))
                append_timed(transitions[index + group_index][1], duration)
            index = group_end

        if len(steps) > MACRO_STEP_MAX:
            raise ValueError(
                f"macro needs {len(steps)} steps; maximum is {MACRO_STEP_MAX}. "
                "Record a shorter macro or disable mouse movement recording."
            )

        return Macro(
            name=name,
            step_count=len(steps),
            trigger_mode=trigger_mode,
            steps=steps,
        )


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))
