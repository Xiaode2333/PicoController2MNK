"""Binary config payload model matching mapper_config.h exactly.

The firmware and desktop app share a packed 8000-byte config payload. All
multi-byte fields are little-endian.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

PROFILE_COUNT = 3
SOURCE_COUNT = 25
GESTURE_COUNT = 3
COMBO_MAX = 16
MACRO_MAX = 8
MACRO_STEP_MAX = 64
MACRO_NAME_MAX = 24
PAYLOAD_SIZE = 8000
ADVANCED_STICK_VERSION = 1
VIRTUAL_DPI_DEFAULT = 1000
VIRTUAL_DPI_MIN = 100
VIRTUAL_DPI_MAX = 20000

# Logical input IDs
(
    SRC_A,
    SRC_B,
    SRC_X,
    SRC_Y,
    SRC_LB,
    SRC_RB,
    SRC_LT,
    SRC_RT,
    SRC_L3,
    SRC_R3,
    SRC_DPAD_UP,
    SRC_DPAD_DOWN,
    SRC_DPAD_LEFT,
    SRC_DPAD_RIGHT,
    SRC_MENU,
    SRC_OPTION,
    SRC_SNAPSHOT,
    SRC_LSTICK_UP,
    SRC_LSTICK_DOWN,
    SRC_LSTICK_LEFT,
    SRC_LSTICK_RIGHT,
    SRC_RSTICK_UP,
    SRC_RSTICK_DOWN,
    SRC_RSTICK_LEFT,
    SRC_RSTICK_RIGHT,
) = range(SOURCE_COUNT)

SOURCE_NAMES = [
    "A",
    "B",
    "X",
    "Y",
    "LB",
    "RB",
    "LT",
    "RT",
    "L3",
    "R3",
    "Dpad Up",
    "Dpad Down",
    "Dpad Left",
    "Dpad Right",
    "Menu",
    "Option",
    "Snapshot",
    "LStick Up",
    "LStick Down",
    "LStick Left",
    "LStick Right",
    "RStick Up",
    "RStick Down",
    "RStick Left",
    "RStick Right",
]

COMBO_DISPLAY_SOURCE_ORDER = (
    SRC_LB, SRC_RB, SRC_LT, SRC_RT, SRC_L3, SRC_R3,
    SRC_A, SRC_B, SRC_X, SRC_Y,
    SRC_DPAD_UP, SRC_DPAD_DOWN, SRC_DPAD_LEFT, SRC_DPAD_RIGHT,
    SRC_MENU, SRC_OPTION, SRC_SNAPSHOT,
    SRC_LSTICK_UP, SRC_LSTICK_DOWN, SRC_LSTICK_LEFT, SRC_LSTICK_RIGHT,
    SRC_RSTICK_UP, SRC_RSTICK_DOWN, SRC_RSTICK_LEFT, SRC_RSTICK_RIGHT,
)

GESTURE_TAP, GESTURE_HOLD, GESTURE_DOUBLE = range(GESTURE_COUNT)
GESTURE_NAMES = ["Tap", "Hold", "Double tap"]

(
    ACTION_NONE,
    ACTION_KEY,
    ACTION_MODIFIER_KEY,
    ACTION_MOUSE_BUTTON,
    ACTION_WHEEL_UP_TURBO,
    ACTION_WHEEL_DOWN_TURBO,
    ACTION_WHEEL_UP_COMBO,
    ACTION_WHEEL_DOWN_COMBO,
    ACTION_MACRO,
    ACTION_ALT_TAP_KEY,
    ACTION_SNAPSHOT_MACRO,
) = range(11)

ACTION_NAMES = {
    ACTION_NONE: "None",
    ACTION_KEY: "Key",
    ACTION_MODIFIER_KEY: "Modifier + key",
    ACTION_MOUSE_BUTTON: "Mouse button",
    ACTION_WHEEL_UP_TURBO: "Wheel up (turbo)",
    ACTION_WHEEL_DOWN_TURBO: "Wheel down (turbo)",
    ACTION_WHEEL_UP_COMBO: "Wheel up (combo)",
    ACTION_WHEEL_DOWN_COMBO: "Wheel down (combo)",
    ACTION_MACRO: "Macro",
    ACTION_ALT_TAP_KEY: "Alternating 1/2",
    ACTION_SNAPSHOT_MACRO: "Snapshot macro",
}

MOD_LEFTCTRL = 0x01
MOD_LEFTSHIFT = 0x02
MOD_LEFTALT = 0x04
MOD_LEFTGUI = 0x08
MOD_RIGHTCTRL = 0x10
MOD_RIGHTSHIFT = 0x20
MOD_RIGHTALT = 0x40
MOD_RIGHTGUI = 0x80

MODIFIER_NAMES = {
    MOD_LEFTCTRL: "Left Ctrl",
    MOD_LEFTSHIFT: "Left Shift",
    MOD_LEFTALT: "Left Alt",
    MOD_LEFTGUI: "Left GUI",
    MOD_RIGHTCTRL: "Right Ctrl",
    MOD_RIGHTSHIFT: "Right Shift",
    MOD_RIGHTALT: "Right Alt",
    MOD_RIGHTGUI: "Right GUI",
}

MOUSE_LEFT = 0x01
MOUSE_RIGHT = 0x02
MOUSE_MIDDLE = 0x04

MACRO_STEP_DELAY, MACRO_STEP_KEYBOARD, MACRO_STEP_MOUSE = range(3)
(
    MACRO_TRIGGER_PRESS,
    MACRO_TRIGGER_RELEASE,
    MACRO_TRIGGER_WHILE_HELD,
    MACRO_TRIGGER_TOGGLE,
) = range(4)

MACRO_TRIGGER_NAMES = ["On press", "On release", "While held", "Toggle"]

# HID keyboard usage codes. This table is intentionally small and explicit.
HID_KEY_NAMES = {
    0x00: "None",
    0x04: "A", 0x05: "B", 0x06: "C", 0x07: "D", 0x08: "E",
    0x09: "F", 0x0A: "G", 0x0B: "H", 0x0C: "I", 0x0D: "J",
    0x0E: "K", 0x0F: "L", 0x10: "M", 0x11: "N", 0x12: "O",
    0x13: "P", 0x14: "Q", 0x15: "R", 0x16: "S", 0x17: "T",
    0x18: "U", 0x19: "V", 0x1A: "W", 0x1B: "X", 0x1C: "Y",
    0x1D: "Z",
    0x1E: "1", 0x1F: "2", 0x20: "3", 0x21: "4", 0x22: "5",
    0x23: "6", 0x24: "7", 0x25: "8", 0x26: "9", 0x27: "0",
    0x28: "Enter", 0x29: "Escape", 0x2A: "Backspace", 0x2B: "Tab",
    0x2C: "Space", 0x2D: "-", 0x2E: "=", 0x2F: "[", 0x30: "]",
    0x31: "Backslash", 0x33: ";", 0x34: "'", 0x35: "`", 0x36: ",",
    0x37: ".", 0x38: "/", 0x39: "Caps Lock",
    0x3A: "F1", 0x3B: "F2", 0x3C: "F3", 0x3D: "F4", 0x3E: "F5",
    0x3F: "F6", 0x40: "F7", 0x41: "F8", 0x42: "F9", 0x43: "F10",
    0x44: "F11", 0x45: "F12", 0x48: "Pause",
    0x4C: "Delete", 0x4F: "Right Arrow", 0x50: "Left Arrow",
    0x51: "Down Arrow", 0x52: "Up Arrow",
}

HID_NAME_TO_KEY = {v: k for k, v in HID_KEY_NAMES.items() if k != 0x00}


@dataclass
class Action:
    type: int = ACTION_NONE
    param1: int = 0
    param2: int = 0
    trigger_mode: int = 0
    value: int = 0
    duration_ms: int = 0


@dataclass
class Combo:
    profile_mask: int = 0
    source_mask: int = 0
    suppress_sources: int = 0
    action: Action = field(default_factory=Action)


@dataclass
class MacroStep:
    type: int = MACRO_STEP_DELAY
    modifier: int = 0
    keys: tuple[int, ...] = (0, 0, 0, 0, 0, 0)
    value: int = 0
    duration_ms: int = 10


@dataclass
class Macro:
    name: str = "New macro"
    step_count: int = 0
    trigger_mode: int = MACRO_TRIGGER_PRESS
    steps: list[MacroStep] = field(default_factory=list)


def _documented_default_bindings() -> list[list[list[Action]]]:
    bindings = [
        [[Action() for _ in range(GESTURE_COUNT)] for _ in range(SOURCE_COUNT)]
        for _ in range(PROFILE_COUNT)
    ]

    def continuous(profile: int, source: int, action: Action) -> None:
        action.duration_ms = 1
        bindings[profile][source][GESTURE_HOLD] = action

    def key(profile: int, source: int, name: str) -> None:
        continuous(profile, source, Action(type=ACTION_KEY, param1=HID_NAME_TO_KEY[name]))

    def modifier(profile: int, source: int, value: int) -> None:
        continuous(profile, source, Action(type=ACTION_MODIFIER_KEY, param1=value))

    def mouse(profile: int, source: int, buttons: int) -> None:
        continuous(profile, source, Action(type=ACTION_MOUSE_BUTTON, param1=buttons))

    def wheel(profile: int, source: int, action_type: int) -> None:
        continuous(profile, source, Action(type=action_type))

    def tap_hold(profile: int, source: int, tap: str, hold: str) -> None:
        bindings[profile][source][GESTURE_TAP] = Action(
            type=ACTION_KEY, param1=HID_NAME_TO_KEY[tap]
        )
        bindings[profile][source][GESTURE_HOLD] = Action(
            type=ACTION_KEY, param1=HID_NAME_TO_KEY[hold]
        )

    # Profile 1
    tap_hold(0, SRC_DPAD_UP, "5", "G")
    tap_hold(0, SRC_DPAD_DOWN, "3", "4")
    key(0, SRC_DPAD_LEFT, "B")
    key(0, SRC_DPAD_RIGHT, "`")
    mouse(0, SRC_LB, MOUSE_RIGHT)
    mouse(0, SRC_RB, MOUSE_LEFT)
    key(0, SRC_LT, "Q")
    key(0, SRC_RT, "E")
    tap_hold(0, SRC_X, "R", "F")
    key(0, SRC_A, "Space")
    tap_hold(0, SRC_B, "C", "Z")
    mouse(0, SRC_Y, MOUSE_MIDDLE)
    modifier(0, SRC_L3, MOD_LEFTSHIFT)
    bindings[0][SRC_R3][GESTURE_TAP] = Action(type=ACTION_ALT_TAP_KEY)
    bindings[0][SRC_R3][GESTURE_HOLD] = Action(
        type=ACTION_KEY, param1=HID_NAME_TO_KEY["X"]
    )
    key(0, SRC_MENU, "Tab")
    bindings[0][SRC_SNAPSHOT][GESTURE_TAP] = Action(type=ACTION_MACRO, param1=0)
    tap_hold(0, SRC_OPTION, "M", "Escape")

    # Profile 2
    key(1, SRC_DPAD_UP, "G")
    key(1, SRC_DPAD_RIGHT, "4")
    wheel(1, SRC_DPAD_DOWN, ACTION_WHEEL_UP_TURBO)
    key(1, SRC_DPAD_LEFT, "B")
    mouse(1, SRC_LB, MOUSE_RIGHT)
    mouse(1, SRC_RB, MOUSE_LEFT)
    modifier(1, SRC_LT, MOD_LEFTCTRL)
    key(1, SRC_RT, "Space")
    tap_hold(1, SRC_X, "R", "E")
    key(1, SRC_A, "V")
    wheel(1, SRC_B, ACTION_WHEEL_DOWN_TURBO)
    mouse(1, SRC_Y, MOUSE_MIDDLE)
    key(1, SRC_L3, "Q")
    bindings[1][SRC_R3][GESTURE_TAP] = Action(type=ACTION_ALT_TAP_KEY)
    bindings[1][SRC_R3][GESTURE_HOLD] = Action(
        type=ACTION_KEY, param1=HID_NAME_TO_KEY["3"]
    )
    key(1, SRC_MENU, "Tab")
    bindings[1][SRC_SNAPSHOT][GESTURE_TAP] = Action(type=ACTION_MACRO, param1=0)
    tap_hold(1, SRC_OPTION, "Escape", "M")

    # Profile 3
    key(2, SRC_DPAD_UP, "L")
    key(2, SRC_DPAD_RIGHT, "5")
    key(2, SRC_DPAD_DOWN, "H")
    key(2, SRC_DPAD_LEFT, "B")
    mouse(2, SRC_LB, MOUSE_RIGHT)
    mouse(2, SRC_RB, MOUSE_LEFT)
    key(2, SRC_LT, "V")
    key(2, SRC_RT, "G")
    bindings[2][SRC_X][GESTURE_TAP] = Action(
        type=ACTION_KEY, param1=HID_NAME_TO_KEY["R"]
    )
    bindings[2][SRC_X][GESTURE_DOUBLE] = Action(
        type=ACTION_KEY, param1=HID_NAME_TO_KEY["F"]
    )
    key(2, SRC_A, "Space")
    tap_hold(2, SRC_B, "C", "Z")
    mouse(2, SRC_Y, MOUSE_MIDDLE)
    modifier(2, SRC_L3, MOD_LEFTSHIFT)
    bindings[2][SRC_R3][GESTURE_TAP] = Action(type=ACTION_ALT_TAP_KEY)
    bindings[2][SRC_R3][GESTURE_HOLD] = Action(
        type=ACTION_KEY, param1=HID_NAME_TO_KEY["X"]
    )
    key(2, SRC_MENU, "Tab")
    bindings[2][SRC_SNAPSHOT][GESTURE_TAP] = Action(type=ACTION_MACRO, param1=0)
    tap_hold(2, SRC_OPTION, "M", "Escape")
    return bindings


def _documented_default_combos() -> list[Combo]:
    combos = [Combo() for _ in range(COMBO_MAX)]

    def mask(*sources: int) -> int:
        result = 0
        for source in sources:
            result |= 1 << source
        return result

    def set_combo(index: int, profiles: int, sources: int, suppress: int,
                  action: Action) -> None:
        combos[index] = Combo(profiles, sources, suppress, action)

    lt_rt = mask(SRC_LT, SRC_RT)
    for index, source, key_name in (
        (0, SRC_X, "1"),
        (1, SRC_Y, "2"),
        (2, SRC_A, "3"),
        (3, SRC_B, "4"),
    ):
        sources = lt_rt | mask(source)
        set_combo(
            index, 0x03, sources, sources,
            Action(type=ACTION_MODIFIER_KEY, param1=MOD_LEFTCTRL,
                   param2=HID_NAME_TO_KEY[key_name]),
        )

    wheel_up = lt_rt | mask(SRC_DPAD_UP)
    wheel_down = lt_rt | mask(SRC_DPAD_DOWN)
    set_combo(4, 0x07, wheel_up, wheel_up, Action(type=ACTION_WHEEL_UP_COMBO))
    set_combo(5, 0x07, wheel_down, wheel_down, Action(type=ACTION_WHEEL_DOWN_COMBO))

    sources = lt_rt | mask(SRC_DPAD_LEFT)
    set_combo(6, 0x01, sources, sources,
              Action(type=ACTION_KEY, param1=HID_NAME_TO_KEY["F4"]))
    sources = lt_rt | mask(SRC_DPAD_RIGHT)
    set_combo(7, 0x01, sources, sources,
              Action(type=ACTION_KEY, param1=HID_NAME_TO_KEY["H"]))

    sources = mask(SRC_L3, SRC_Y)
    set_combo(8, 0x02, sources, sources,
              Action(type=ACTION_KEY, param1=HID_NAME_TO_KEY["Z"]))
    set_combo(9, 0x02, mask(SRC_LB, SRC_B), mask(SRC_B),
              Action(type=ACTION_MODIFIER_KEY, param1=MOD_LEFTSHIFT))
    set_combo(10, 0x02, mask(SRC_LB, SRC_DPAD_DOWN), mask(SRC_DPAD_DOWN),
              Action(type=ACTION_KEY, param1=HID_NAME_TO_KEY["H"]))

    set_combo(11, 0x04, lt_rt, lt_rt,
              Action(type=ACTION_KEY, param1=HID_NAME_TO_KEY["X"]))
    set_combo(12, 0x04, mask(SRC_LB, SRC_B), mask(SRC_B),
              Action(type=ACTION_KEY, param1=HID_NAME_TO_KEY["U"]))
    set_combo(13, 0x04, mask(SRC_LB, SRC_LT), mask(SRC_LT),
              Action(type=ACTION_KEY, param1=HID_NAME_TO_KEY["Q"]))
    set_combo(14, 0x04, mask(SRC_LB, SRC_RT), mask(SRC_RT),
              Action(type=ACTION_KEY, param1=HID_NAME_TO_KEY["E"]))
    return combos


def _documented_default_macros() -> list[Macro]:
    macros = [Macro(name=f"Macro {i + 1}") for i in range(MACRO_MAX)]
    macros[0] = Macro(
        name="Snapshot Alt+RMB",
        step_count=4,
        trigger_mode=MACRO_TRIGGER_PRESS,
        steps=[
            MacroStep(type=MACRO_STEP_KEYBOARD, modifier=MOD_LEFTALT,
                      duration_ms=30),
            MacroStep(type=MACRO_STEP_MOUSE,
                      keys=(MOUSE_RIGHT, 0, 0, 0, 0, 0), duration_ms=10),
            MacroStep(type=MACRO_STEP_MOUSE, duration_ms=30),
            MacroStep(type=MACRO_STEP_KEYBOARD, duration_ms=1),
        ],
    )
    return macros


@dataclass
class Settings:
    left_stick_mode: list[int] = field(default_factory=lambda: [2, 1, 2])
    active_profile: int = 0
    output_enabled: int = 1
    tap_duration_ms: int = 40
    hold_threshold_ms: int = 200
    double_click_ms: int = 250
    wheel_turbo_hz: int = 30
    wheel_combo_hz: int = 10
    mouse_release_grace_ms: int = 40
    left_deadzone: float = 0.10
    right_deadzone: float = 0.06
    mouse_speed_x: list[int] = field(default_factory=lambda: [5000, 5000, 5000])
    mouse_speed_y: list[int] = field(default_factory=lambda: [5000, 4166, 5000])
    virtual_dpi: int = VIRTUAL_DPI_DEFAULT
    right_center_x: int = 2048
    right_center_y: int = 2048
    advanced_stick_version: int = ADVANCED_STICK_VERSION
    profile2_accel_enabled: int = 1
    profile2_outer_threshold_percent: int = 95
    profile2_rb_speed_x: int = 3750
    profile2_rb_speed_y: int = 2000
    profile2_no_rb_ramp_ms: int = 300
    profile2_no_rb_extra_x: int = 4583
    profile2_rb_delay_ms: int = 250
    profile2_rb_ramp_ms: int = 1000
    profile2_rb_extra_x: int = 625
    profile2_rb_extra_y: int = 625


@dataclass
class ConfigPayload:
    settings: Settings = field(default_factory=Settings)
    bindings: list[list[list[Action]]] = field(default_factory=list)
    combos: list[Combo] = field(default_factory=list)
    macros: list[Macro] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.bindings:
            self.bindings = _documented_default_bindings()
        if not self.combos:
            self.combos = _documented_default_combos()
        if not self.macros:
            self.macros = _documented_default_macros()


_ACTION_STRUCT = struct.Struct("<BBBBhH")
_COMBO_STRUCT = struct.Struct("<BII" + "BBBBhH")
_MACRO_STEP_STRUCT = struct.Struct("<BB6sbH")
_SETTINGS_STRUCT = struct.Struct("<3sBBBIIIIIIffHHHHHHHHBB")
_ADVANCED_STICK_STRUCT = struct.Struct("<8H")
_MACRO_HEAD_STRUCT = struct.Struct("<24sBBBB")
_PAYLOAD_STRUCT = None


def _require_int_range(value: object, low: int, high: int, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{path} must be an integer")
    if not low <= value <= high:
        raise ValueError(f"{path} must be in {low}..{high}, got {value}")
    return value


def _require_finite(value: object, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{path} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{path} must be finite")
    return result


def _validate_action(action: Action, path: str) -> None:
    _require_int_range(action.type, ACTION_NONE, ACTION_SNAPSHOT_MACRO, f"{path}.type")
    _require_int_range(action.param1, 0, 0xFF, f"{path}.param1")
    _require_int_range(action.param2, 0, 0xFF, f"{path}.param2")
    _require_int_range(action.trigger_mode, 0, 0xFF, f"{path}.trigger_mode")
    _require_int_range(action.value, -0x8000, 0x7FFF, f"{path}.value")
    _require_int_range(action.duration_ms, 0, 0xFFFF, f"{path}.duration_ms")

    if action.type == ACTION_MACRO and action.param1 >= MACRO_MAX:
        raise ValueError(
            f"{path}.param1 selects macro {action.param1}, maximum is {MACRO_MAX - 1}"
        )
    if action.type == ACTION_MOUSE_BUTTON and action.param1 & ~(
        MOUSE_LEFT | MOUSE_RIGHT | MOUSE_MIDDLE
    ):
        raise ValueError(f"{path}.param1 contains unsupported mouse-button bits")


def _validate_macro_step(step: MacroStep, path: str) -> None:
    _require_int_range(step.type, MACRO_STEP_DELAY, MACRO_STEP_MOUSE, f"{path}.type")
    _require_int_range(step.modifier, 0, 0xFF, f"{path}.modifier")
    if len(step.keys) > 6:
        raise ValueError(f"{path}.keys has {len(step.keys)} entries, maximum is 6")
    for index, key in enumerate(step.keys):
        # Mouse dx/dy are accepted either as signed values from the recorder or
        # as their raw uint8 representation after decoding a payload.
        _require_int_range(key, -0x80, 0xFF, f"{path}.keys[{index}]")
    _require_int_range(step.value, -0x80, 0x7F, f"{path}.value")
    _require_int_range(step.duration_ms, 0, 0xFFFF, f"{path}.duration_ms")
    if step.type == MACRO_STEP_MOUSE:
        buttons = step.keys[0] if step.keys else 0
        if buttons & ~(MOUSE_LEFT | MOUSE_RIGHT | MOUSE_MIDDLE):
            raise ValueError(f"{path}.keys[0] contains unsupported mouse-button bits")


def validate_config(config: ConfigPayload) -> None:
    """Validate all desktop data before it reaches ``struct.pack`` or a board.

    These checks mirror the firmware's semantic validation and also make every
    fixed-width wire-field failure a contextual ``ValueError`` instead of an
    ``IndexError`` or ``struct.error``.
    """
    settings = config.settings
    if len(settings.left_stick_mode) != PROFILE_COUNT:
        raise ValueError(
            f"settings.left_stick_mode must contain {PROFILE_COUNT} entries"
        )
    for index, mode in enumerate(settings.left_stick_mode):
        _require_int_range(mode, 0, 2, f"settings.left_stick_mode[{index}]")
    _require_int_range(
        settings.active_profile, 0, PROFILE_COUNT - 1, "settings.active_profile"
    )
    _require_int_range(settings.output_enabled, 0, 1, "settings.output_enabled")

    for field_name in ("tap_duration_ms", "hold_threshold_ms", "double_click_ms"):
        _require_int_range(getattr(settings, field_name), 1, 60000,
                           f"settings.{field_name}")
    for field_name in ("wheel_turbo_hz", "wheel_combo_hz"):
        _require_int_range(getattr(settings, field_name), 1, 1000,
                           f"settings.{field_name}")
    _require_int_range(settings.mouse_release_grace_ms, 0, 5000,
                       "settings.mouse_release_grace_ms")

    for field_name in ("left_deadzone", "right_deadzone"):
        value = _require_finite(getattr(settings, field_name), f"settings.{field_name}")
        if not 0.0 <= value < 1.0:
            raise ValueError(f"settings.{field_name} must be in [0.0, 1.0)")

    for field_name in ("mouse_speed_x", "mouse_speed_y"):
        values = getattr(settings, field_name)
        if len(values) != PROFILE_COUNT:
            raise ValueError(f"settings.{field_name} must contain {PROFILE_COUNT} entries")
        for index, value in enumerate(values):
            _require_int_range(value, 0, 0xFFFF, f"settings.{field_name}[{index}]")
    _require_int_range(
        settings.virtual_dpi,
        VIRTUAL_DPI_MIN,
        VIRTUAL_DPI_MAX,
        "settings.virtual_dpi",
    )
    _require_int_range(settings.right_center_x, 0, 4095, "settings.right_center_x")
    _require_int_range(settings.right_center_y, 0, 4095, "settings.right_center_y")
    _require_int_range(
        settings.advanced_stick_version,
        0,
        ADVANCED_STICK_VERSION,
        "settings.advanced_stick_version",
    )
    _require_int_range(
        settings.profile2_accel_enabled, 0, 1, "settings.profile2_accel_enabled"
    )
    _require_int_range(
        settings.profile2_outer_threshold_percent,
        1,
        100,
        "settings.profile2_outer_threshold_percent",
    )
    for field_name in (
        "profile2_rb_speed_x",
        "profile2_rb_speed_y",
        "profile2_no_rb_ramp_ms",
        "profile2_no_rb_extra_x",
        "profile2_rb_delay_ms",
        "profile2_rb_ramp_ms",
        "profile2_rb_extra_x",
        "profile2_rb_extra_y",
    ):
        _require_int_range(getattr(settings, field_name), 0, 0xFFFF, f"settings.{field_name}")

    if len(config.bindings) != PROFILE_COUNT:
        raise ValueError(f"bindings must contain {PROFILE_COUNT} profiles")
    for profile, profile_bindings in enumerate(config.bindings):
        if len(profile_bindings) != SOURCE_COUNT:
            raise ValueError(
                f"bindings[{profile}] must contain {SOURCE_COUNT} sources"
            )
        for source, gesture_actions in enumerate(profile_bindings):
            if len(gesture_actions) != GESTURE_COUNT:
                raise ValueError(
                    f"bindings[{profile}][{source}] must contain "
                    f"{GESTURE_COUNT} gestures"
                )
            for gesture, action in enumerate(gesture_actions):
                _validate_action(action, f"bindings[{profile}][{source}][{gesture}]")

    if len(config.combos) != COMBO_MAX:
        raise ValueError(f"combos must contain {COMBO_MAX} entries")
    source_bits = (1 << SOURCE_COUNT) - 1
    profile_bits = (1 << PROFILE_COUNT) - 1
    for index, combo in enumerate(config.combos):
        _require_int_range(combo.profile_mask, 0, 0xFF, f"combos[{index}].profile_mask")
        if combo.profile_mask & ~profile_bits:
            raise ValueError(f"combos[{index}].profile_mask contains unsupported profile bits")
        _require_int_range(combo.source_mask, 0, 0xFFFFFFFF,
                           f"combos[{index}].source_mask")
        if combo.source_mask & ~source_bits:
            raise ValueError(f"combos[{index}].source_mask contains unsupported source bits")
        _require_int_range(combo.suppress_sources, 0, 0xFFFFFFFF,
                           f"combos[{index}].suppress_sources")
        if combo.suppress_sources & ~source_bits:
            raise ValueError(
                f"combos[{index}].suppress_sources contains unsupported source bits"
            )
        _validate_action(combo.action, f"combos[{index}].action")

    if len(config.macros) != MACRO_MAX:
        raise ValueError(f"macros must contain {MACRO_MAX} entries")
    for index, macro in enumerate(config.macros):
        if not isinstance(macro.name, str):
            raise ValueError(f"macros[{index}].name must be text")
        if "\x00" in macro.name:
            raise ValueError(f"macros[{index}].name cannot contain NUL characters")
        _require_int_range(macro.step_count, 0, MACRO_STEP_MAX,
                           f"macros[{index}].step_count")
        _require_int_range(macro.trigger_mode, MACRO_TRIGGER_PRESS, MACRO_TRIGGER_TOGGLE,
                           f"macros[{index}].trigger_mode")
        if macro.step_count > len(macro.steps):
            raise ValueError(
                f"macros[{index}].step_count is {macro.step_count}, but only "
                f"{len(macro.steps)} steps are present"
            )
        for step_index, step in enumerate(macro.steps[: macro.step_count]):
            _validate_macro_step(step, f"macros[{index}].steps[{step_index}]")


def _encode_macro_name(name: str) -> bytes:
    """Encode a name into all 24 available bytes without splitting UTF-8."""
    encoded = name.encode("utf-8")
    if len(encoded) > MACRO_NAME_MAX:
        encoded = encoded[:MACRO_NAME_MAX].decode("utf-8", errors="ignore").encode("utf-8")
    return encoded.ljust(MACRO_NAME_MAX, b"\x00")


def _pack_action(action: Action) -> bytes:
    return _ACTION_STRUCT.pack(
        action.type,
        action.param1,
        action.param2,
        action.trigger_mode,
        action.value,
        action.duration_ms,
    )


def _unpack_action(data: bytes) -> Action:
    return Action(*_ACTION_STRUCT.unpack(data))


def _pack_settings(settings: Settings) -> bytes:
    return _SETTINGS_STRUCT.pack(
        bytes(settings.left_stick_mode),
        settings.active_profile,
        settings.output_enabled,
        settings.advanced_stick_version,
        settings.tap_duration_ms,
        settings.hold_threshold_ms,
        settings.double_click_ms,
        settings.wheel_turbo_hz,
        settings.wheel_combo_hz,
        settings.mouse_release_grace_ms,
        settings.left_deadzone,
        settings.right_deadzone,
        *settings.mouse_speed_x,
        *settings.mouse_speed_y,
        settings.right_center_x,
        settings.right_center_y,
        settings.profile2_accel_enabled,
        settings.profile2_outer_threshold_percent,
    )


def _unpack_settings(data: bytes) -> Settings:
    fields = _SETTINGS_STRUCT.unpack(data)
    return Settings(
        left_stick_mode=list(fields[0]),
        active_profile=fields[1],
        output_enabled=fields[2],
        advanced_stick_version=fields[3],
        tap_duration_ms=fields[4],
        hold_threshold_ms=fields[5],
        double_click_ms=fields[6],
        wheel_turbo_hz=fields[7],
        wheel_combo_hz=fields[8],
        mouse_release_grace_ms=fields[9],
        left_deadzone=fields[10],
        right_deadzone=fields[11],
        mouse_speed_x=list(fields[12:15]),
        mouse_speed_y=list(fields[15:18]),
        right_center_x=fields[18],
        right_center_y=fields[19],
        profile2_accel_enabled=fields[20],
        profile2_outer_threshold_percent=fields[21],
    )


def _pack_macro_step(step: MacroStep) -> bytes:
    keys = [int(key) & 0xFF for key in step.keys] + [0] * 6
    return _MACRO_STEP_STRUCT.pack(
        step.type,
        step.modifier,
        bytes(keys[:6]),
        step.value,
        step.duration_ms,
    )


def _unpack_macro_step(data: bytes) -> MacroStep:
    step_type, modifier, keybytes, value, duration = _MACRO_STEP_STRUCT.unpack(data)
    return MacroStep(
        type=step_type,
        modifier=modifier,
        keys=tuple(keybytes),
        value=value,
        duration_ms=duration,
    )


def _pack_macro(macro: Macro, reserved_value: int = 0) -> bytes:
    name_bytes = _encode_macro_name(macro.name)
    reserved_value &= 0xFFFF
    head = _MACRO_HEAD_STRUCT.pack(name_bytes, min(macro.step_count, MACRO_STEP_MAX),
                                   macro.trigger_mode, reserved_value & 0xFF,
                                   reserved_value >> 8)
    step_bytes = [_pack_macro_step(macro.steps[i]) if i < len(macro.steps)
                  else _MACRO_STEP_STRUCT.pack(MACRO_STEP_DELAY, 0, b"\x00" * 6, 0, 0)
                  for i in range(MACRO_STEP_MAX)]
    return head + b"".join(step_bytes)


def _unpack_macro(data: bytes, index: int) -> Macro:
    expected_size = _MACRO_HEAD_STRUCT.size + MACRO_STEP_MAX * _MACRO_STEP_STRUCT.size
    if len(data) != expected_size:
        raise ValueError(
            f"macros[{index}] is {len(data)} bytes, expected {expected_size}"
        )
    name_bytes, step_count, trigger_mode, _r0, _r1 = _MACRO_HEAD_STRUCT.unpack_from(data)
    if step_count > MACRO_STEP_MAX:
        raise ValueError(
            f"macros[{index}].step_count is {step_count}, maximum is {MACRO_STEP_MAX}"
        )
    if trigger_mode > MACRO_TRIGGER_TOGGLE:
        raise ValueError(
            f"macros[{index}].trigger_mode is {trigger_mode}, maximum is "
            f"{MACRO_TRIGGER_TOGGLE}"
        )
    encoded_name = name_bytes.split(b"\x00", 1)[0]
    try:
        name = encoded_name.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"macros[{index}].name is not valid UTF-8") from exc
    steps = []
    for i in range(step_count):
        offset = _MACRO_HEAD_STRUCT.size + i * _MACRO_STEP_STRUCT.size
        steps.append(_unpack_macro_step(data[offset : offset + _MACRO_STEP_STRUCT.size]))
    return Macro(
        name=name or "New macro",
        step_count=step_count,
        trigger_mode=trigger_mode,
        steps=steps,
    )


def encode_payload(config: ConfigPayload) -> bytes:
    validate_config(config)
    out = bytearray()
    out += _pack_settings(config.settings)

    for profile in range(PROFILE_COUNT):
        for source in range(SOURCE_COUNT):
            for gesture in range(GESTURE_COUNT):
                out += _pack_action(config.bindings[profile][source][gesture])

    for combo in config.combos:
        out += _COMBO_STRUCT.pack(
            combo.profile_mask,
            combo.source_mask,
            combo.suppress_sources,
            combo.action.type,
            combo.action.param1,
            combo.action.param2,
            combo.action.trigger_mode,
            combo.action.value,
            combo.action.duration_ms,
        )

    for macro_index, macro in enumerate(config.macros):
        # The firmware stores global virtual DPI in macro 0's two reserved
        # header bytes. This preserves the established 8000-byte payload and
        # remains compatible with legacy payloads where both bytes are zero.
        reserved_value = config.settings.virtual_dpi if macro_index == 0 else 0
        out += _pack_macro(macro, reserved_value)

    out += _ADVANCED_STICK_STRUCT.pack(
        config.settings.profile2_rb_speed_x,
        config.settings.profile2_rb_speed_y,
        config.settings.profile2_no_rb_ramp_ms,
        config.settings.profile2_no_rb_extra_x,
        config.settings.profile2_rb_delay_ms,
        config.settings.profile2_rb_ramp_ms,
        config.settings.profile2_rb_extra_x,
        config.settings.profile2_rb_extra_y,
    )
    if len(out) != PAYLOAD_SIZE:
        raise ValueError(f"internal error: config payload is {len(out)} bytes, expected {PAYLOAD_SIZE}")
    return bytes(out)


def decode_payload(data: bytes) -> ConfigPayload:
    if len(data) != PAYLOAD_SIZE:
        raise ValueError(f"config payload is {len(data)} bytes, expected {PAYLOAD_SIZE}")

    settings = _unpack_settings(data[: _SETTINGS_STRUCT.size])
    offset = _SETTINGS_STRUCT.size

    bindings = []
    for _profile in range(PROFILE_COUNT):
        profile_bindings = []
        for _source in range(SOURCE_COUNT):
            gesture_actions = []
            for _gesture in range(GESTURE_COUNT):
                gesture_actions.append(_unpack_action(data[offset : offset + _ACTION_STRUCT.size]))
                offset += _ACTION_STRUCT.size
            profile_bindings.append(gesture_actions)
        bindings.append(profile_bindings)

    combos = []
    for _combo in range(COMBO_MAX):
        fields = _COMBO_STRUCT.unpack(data[offset : offset + _COMBO_STRUCT.size])
        offset += _COMBO_STRUCT.size
        combos.append(
            Combo(
                profile_mask=fields[0],
                source_mask=fields[1],
                suppress_sources=fields[2],
                action=Action(*fields[3:]),
            )
        )

    macros = []
    macro_size = _MACRO_HEAD_STRUCT.size + MACRO_STEP_MAX * _MACRO_STEP_STRUCT.size
    for macro_index in range(MACRO_MAX):
        macro_data = data[offset : offset + macro_size]
        macros.append(_unpack_macro(macro_data, macro_index))
        if macro_index == 0:
            _name, _count, _trigger, dpi_lo, dpi_hi = _MACRO_HEAD_STRUCT.unpack_from(
                macro_data
            )
            raw_dpi = dpi_lo | (dpi_hi << 8)
            settings.virtual_dpi = raw_dpi or VIRTUAL_DPI_DEFAULT
        offset += macro_size

    advanced = _ADVANCED_STICK_STRUCT.unpack(
        data[offset : offset + _ADVANCED_STICK_STRUCT.size]
    )
    if settings.advanced_stick_version == ADVANCED_STICK_VERSION:
        (
            settings.profile2_rb_speed_x,
            settings.profile2_rb_speed_y,
            settings.profile2_no_rb_ramp_ms,
            settings.profile2_no_rb_extra_x,
            settings.profile2_rb_delay_ms,
            settings.profile2_rb_ramp_ms,
            settings.profile2_rb_extra_x,
            settings.profile2_rb_extra_y,
        ) = advanced
    else:
        # Schema v1 originally left these bytes as zero. Upgrade old payloads
        # in memory so saving them preserves the legacy hard-coded behavior.
        settings.advanced_stick_version = ADVANCED_STICK_VERSION

    config = ConfigPayload(settings=settings, bindings=bindings, combos=combos, macros=macros)
    validate_config(config)
    return config


def format_action(action: Action) -> str:
    if action.type == ACTION_NONE:
        return "None"
    if action.type == ACTION_KEY:
        return f"Key {HID_KEY_NAMES.get(action.param1, hex(action.param1))}"
    if action.type == ACTION_MODIFIER_KEY:
        mod = MODIFIER_NAMES.get(action.param1, hex(action.param1))
        if action.param2:
            return f"{mod} + {HID_KEY_NAMES.get(action.param2, hex(action.param2))}"
        return mod
    if action.type == ACTION_MOUSE_BUTTON:
        names = []
        if action.param1 & MOUSE_LEFT:
            names.append("Left")
        if action.param1 & MOUSE_RIGHT:
            names.append("Right")
        if action.param1 & MOUSE_MIDDLE:
            names.append("Middle")
        return "Mouse " + "+".join(names) if names else "Mouse ?"
    if action.type in (
        ACTION_WHEEL_UP_TURBO,
        ACTION_WHEEL_DOWN_TURBO,
        ACTION_WHEEL_UP_COMBO,
        ACTION_WHEEL_DOWN_COMBO,
    ):
        return ACTION_NAMES[action.type]
    if action.type == ACTION_MACRO:
        return f"Macro #{action.param1 + 1}"
    return ACTION_NAMES.get(action.type, f"Action {action.type}")


def format_modifier_mask(mask: int) -> str:
    names = [name for bit, name in MODIFIER_NAMES.items() if mask & bit]
    return " + ".join(names) if names else "None"


def format_source_mask(mask: int) -> str:
    names = [SOURCE_NAMES[source] for source in COMBO_DISPLAY_SOURCE_ORDER if mask & (1 << source)]
    return " + ".join(names) if names else "None"


def format_macro_step(step: MacroStep) -> str:
    if step.type == MACRO_STEP_DELAY:
        return f"Delay {step.duration_ms} ms"
    if step.type == MACRO_STEP_KEYBOARD:
        parts = []
        if step.modifier:
            parts.append(format_modifier_mask(step.modifier))
        parts.extend(HID_KEY_NAMES.get(key, f"0x{key:02X}") for key in step.keys if key)
        state = " + ".join(parts) if parts else "neutral"
        return f"Keyboard {state} for {step.duration_ms} ms"
    if step.type == MACRO_STEP_MOUSE:
        buttons = step.keys[0] if step.keys else 0
        dx_raw = step.keys[1] if len(step.keys) > 1 else 0
        dy_raw = step.keys[2] if len(step.keys) > 2 else 0
        dx = dx_raw - 256 if dx_raw > 127 else dx_raw
        dy = dy_raw - 256 if dy_raw > 127 else dy_raw
        parts = []
        if buttons & MOUSE_LEFT:
            parts.append("Left")
        if buttons & MOUSE_RIGHT:
            parts.append("Right")
        if buttons & MOUSE_MIDDLE:
            parts.append("Middle")
        if dx or dy:
            parts.append(f"move {dx},{dy}")
        if step.value:
            parts.append(f"wheel {step.value:+d}")
        state = " + ".join(parts) if parts else "neutral"
        return f"Mouse {state} for {step.duration_ms} ms"
    return f"Unknown step {step.type}"


def format_macro_sequence(macro: Macro) -> str:
    if macro.step_count == 0:
        return "Empty"
    return " -> ".join(format_macro_step(step) for step in macro.steps[: macro.step_count])
