"""Tkinter desktop UI for PicoController2MNK."""

from __future__ import annotations

import copy
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from . import config_model as cm
from .device_locator import (
    candidate_ports,
    descriptor_flash_port,
    legacy_mapper_port,
    likely_mapper_port,
)
from .firmware_flasher import find_bootloader_drives, flash_uf2, verify_mapper_uf2
from .protocol import BoardConnection
from .recorder import Recorder


LEFT_STICK_MODE_LABELS = (
    "Off — no automatic WASD",
    "4-way — one WASD key at a time",
    "8-way — diagonals use two WASD keys",
)
ACTIVE_PROFILE_LABELS = ("Profile 1", "Profile 2", "Profile 3")
OUTPUT_STATE_LABELS = (
    "Disabled — release and stop output",
    "Enabled — send mapped keyboard/mouse",
)
WINDOWS_APP_USER_MODEL_ID = "Xiaode2333.PicoController2MNK.Configurator"


def bundled_resource_path(relative_path: str) -> Path:
    """Return a source-tree or PyInstaller path for a bundled resource."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return bundle_root / relative_path


def configure_windows_app_identity() -> None:
    """Give Windows a stable identity before Tk creates the main window."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            WINDOWS_APP_USER_MODEL_ID
        )
    except (AttributeError, OSError):
        pass


def format_action_for_config(config: cm.ConfigPayload, action: cm.Action) -> str:
    text = cm.format_action(action)
    if action.type == cm.ACTION_MACRO and 0 <= action.param1 < len(config.macros):
        return f"Macro #{action.param1 + 1}: {config.macros[action.param1].name}"
    if action.type in (cm.ACTION_WHEEL_UP_TURBO, cm.ACTION_WHEEL_DOWN_TURBO):
        return f"{text} ({config.settings.wheel_turbo_hz} Hz)"
    if action.type in (cm.ACTION_WHEEL_UP_COMBO, cm.ACTION_WHEEL_DOWN_COMBO):
        return f"{text} ({config.settings.wheel_combo_hz} Hz)"
    return text


def build_profile_combo_rows(
    config: cm.ConfigPayload, profile: int
) -> list[tuple[int, str, str, str, str]]:
    rows = []
    for index, combo in enumerate(config.combos):
        if not combo.profile_mask & (1 << profile) or combo.action.type == cm.ACTION_NONE:
            continue
        profiles = ", ".join(
            str(p + 1) for p in range(cm.PROFILE_COUNT) if combo.profile_mask & (1 << p)
        )
        rows.append(
            (
                index,
                profiles,
                cm.format_source_mask(combo.source_mask),
                format_action_for_config(config, combo.action),
                cm.format_source_mask(combo.suppress_sources),
            )
        )
    return rows


def build_profile_stick_rows(config: cm.ConfigPayload, profile: int) -> list[tuple[str, str]]:
    settings = config.settings
    left_modes = dict(enumerate(LEFT_STICK_MODE_LABELS))
    rows = [
        ("Left stick mode", left_modes.get(settings.left_stick_mode[profile], "Unknown")),
        ("Left stick deadzone", f"{settings.left_deadzone:.4f} (shared by all profiles)"),
        (
            "Right stick mouse",
            f"X {settings.mouse_speed_x[profile]} base counts/s, "
            f"Y {settings.mouse_speed_y[profile]} base counts/s",
        ),
        ("Virtual DPI", f"{settings.virtual_dpi} (shared by all profiles)"),
        ("Right stick deadzone", f"{settings.right_deadzone:.4f} (shared by all profiles)"),
        (
            "Right stick center",
            f"X {settings.right_center_x}, Y {settings.right_center_y} (shared by all profiles)",
        ),
        (
            "Direction actions",
            "LStick/RStick direction rows in Direct bindings are editable",
        ),
    ]
    if profile == 1:
        rows.extend(
            [
                (
                    "Right stick while RB",
                    f"X {settings.profile2_rb_speed_x} base counts/s, "
                    f"Y {settings.profile2_rb_speed_y} base counts/s",
                ),
                (
                    "Outer-ring acceleration",
                    "Enabled" if settings.profile2_accel_enabled else "Disabled",
                ),
                (
                    "Outer-ring threshold",
                    f"{settings.profile2_outer_threshold_percent / 100.0:.2f}",
                ),
                (
                    "Outer ring without RB",
                    f"X +{settings.profile2_no_rb_extra_x} base counts/s over "
                    f"{settings.profile2_no_rb_ramp_ms} ms",
                ),
                (
                    "Outer ring with RB",
                    f"wait {settings.profile2_rb_delay_ms} ms, then X/Y "
                    f"+{settings.profile2_rb_extra_x}/+{settings.profile2_rb_extra_y} "
                    "base counts/s "
                    f"over {settings.profile2_rb_ramp_ms} ms",
                ),
            ]
        )
    return rows


def build_profile_macro_rows(
    config: cm.ConfigPayload, profile: int
) -> list[tuple[int, str, str, str, str]]:
    bindings: list[list[str]] = [[] for _ in range(cm.MACRO_MAX)]
    for source, gestures in enumerate(config.bindings[profile]):
        for gesture, action in enumerate(gestures):
            if action.type == cm.ACTION_MACRO and 0 <= action.param1 < cm.MACRO_MAX:
                bindings[action.param1].append(
                    f"{cm.SOURCE_NAMES[source]} ({cm.GESTURE_NAMES[gesture]})"
                )
    for combo in config.combos:
        if (
            combo.profile_mask & (1 << profile)
            and combo.action.type == cm.ACTION_MACRO
            and 0 <= combo.action.param1 < cm.MACRO_MAX
        ):
            bindings[combo.action.param1].append(f"Combo {cm.format_source_mask(combo.source_mask)}")

    return [
        (
            index,
            macro.name,
            cm.MACRO_TRIGGER_NAMES[macro.trigger_mode],
            ", ".join(bindings[index]) or "Not bound in this profile",
            cm.format_macro_sequence(macro),
        )
        for index, macro in enumerate(config.macros)
    ]


class ActionDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str, initial: cm.Action,
                 macro_names: list[str]):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result: Optional[cm.Action] = None
        self.macro_names = macro_names

        self.type_var = tk.StringVar(value=str(initial.type))
        self.param1_var = tk.IntVar(value=initial.param1)
        self.param2_var = tk.IntVar(value=initial.param2)
        self.trigger_var = tk.IntVar(value=initial.trigger_mode)

        frame = ttk.Frame(self, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="Action").grid(row=0, column=0, sticky="w")
        type_box = ttk.Combobox(
            frame,
            textvariable=self.type_var,
            state="readonly",
            values=[f"{key} {name}" for key, name in cm.ACTION_NAMES.items()],
            width=28,
        )
        type_box.current(initial.type)
        type_box.grid(row=0, column=1, sticky="ew", pady=4)
        type_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh())

        self.dynamic = ttk.Frame(frame)
        self.dynamic.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=8)

        self.key_var = tk.IntVar(value=initial.param1 if initial.type == cm.ACTION_KEY else 0)
        self.mod_var = tk.IntVar(
            value=initial.param1 if initial.type == cm.ACTION_MODIFIER_KEY else 0
        )
        self.mod_key_var = tk.IntVar(
            value=initial.param2 if initial.type == cm.ACTION_MODIFIER_KEY else 0
        )
        self.mouse_left = tk.BooleanVar(value=bool(initial.param1 & cm.MOUSE_LEFT))
        self.mouse_right = tk.BooleanVar(value=bool(initial.param1 & cm.MOUSE_RIGHT))
        self.mouse_middle = tk.BooleanVar(value=bool(initial.param1 & cm.MOUSE_MIDDLE))
        self.macro_index = tk.IntVar(
            value=initial.param1 if initial.type == cm.ACTION_MACRO else 0
        )

        self.key_names = ["(none)"] + sorted(
            f"0x{code:02X} {name}" for code, name in cm.HID_KEY_NAMES.items() if code
        )
        self._key_widgets: list[ttk.Widget] = []
        self._refresh()

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=4)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text="OK", command=self._ok).pack(side="right", padx=4)

        self.transient(parent)
        self.grab_set()
        self.wait_visibility()
        self.focus_set()

    def _clear_dynamic(self) -> None:
        for widget in self.dynamic.winfo_children():
            widget.destroy()
        self._key_widgets = []

    def _key_combo(self, row: int, variable: tk.IntVar, label: str) -> ttk.Combobox:
        ttk.Label(self.dynamic, text=label).grid(row=row, column=0, sticky="w", pady=3)
        combo = ttk.Combobox(self.dynamic, state="readonly", values=self.key_names, width=26)
        combo.grid(row=row, column=1, sticky="ew", pady=3)
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _event, var=variable, box=combo: self._set_key_from_label(var, box.get()),
        )
        self._set_key_combo(variable, combo)
        self._key_widgets.append(combo)
        return combo

    @staticmethod
    def _set_key_from_label(variable: tk.IntVar, label: str) -> None:
        if label.startswith("0x"):
            variable.set(int(label[2:4], 16))
        else:
            variable.set(0)

    @staticmethod
    def _set_key_combo(variable: tk.IntVar, combo: ttk.Combobox) -> None:
        code = variable.get()
        if code and any(label.startswith(f"0x{code:02X} ") for label in combo["values"]):
            for label in combo["values"]:
                if label.startswith(f"0x{code:02X} "):
                    combo.set(label)
                    return
        variable.set(0)
        combo.set("(none)")

    def _current_type(self) -> int:
        return int(str(self.type_var.get()).split()[0])

    def _refresh(self) -> None:
        self._clear_dynamic()
        action_type = self._current_type()

        if action_type == cm.ACTION_NONE:
            ttk.Label(self.dynamic, text="Input will produce no output.").grid(row=0, column=0, columnspan=2)
        elif action_type == cm.ACTION_KEY:
            self._key_combo(0, self.key_var, "Key")
        elif action_type == cm.ACTION_MODIFIER_KEY:
            ttk.Label(self.dynamic, text="Modifier").grid(row=0, column=0, sticky="w", pady=3)
            mod_box = ttk.Combobox(
                self.dynamic,
                state="readonly",
                values=[f"0x{code:02X} {name}" for code, name in cm.MODIFIER_NAMES.items()],
                width=26,
            )
            mod_box.grid(row=0, column=1, sticky="ew", pady=3)
            for label in mod_box["values"]:
                if label.startswith(f"0x{self.mod_var.get():02X} "):
                    mod_box.set(label)
                    break
            mod_box.bind(
                "<<ComboboxSelected>>",
                lambda _event, box=mod_box: self.mod_var.set(int(box.get()[2:4], 16)),
            )
            self._key_combo(1, self.mod_key_var, "Key (optional)")
        elif action_type == cm.ACTION_MOUSE_BUTTON:
            ttk.Checkbutton(self.dynamic, text="Left", variable=self.mouse_left).grid(row=0, column=0, sticky="w")
            ttk.Checkbutton(self.dynamic, text="Right", variable=self.mouse_right).grid(row=1, column=0, sticky="w")
            ttk.Checkbutton(self.dynamic, text="Middle", variable=self.mouse_middle).grid(row=2, column=0, sticky="w")
        elif action_type in (
            cm.ACTION_WHEEL_UP_TURBO,
            cm.ACTION_WHEEL_DOWN_TURBO,
            cm.ACTION_WHEEL_UP_COMBO,
            cm.ACTION_WHEEL_DOWN_COMBO,
            cm.ACTION_ALT_TAP_KEY,
            cm.ACTION_SNAPSHOT_MACRO,
        ):
            ttk.Label(self.dynamic, text=cm.ACTION_NAMES[action_type]).grid(row=0, column=0, columnspan=2)
        elif action_type == cm.ACTION_MACRO:
            ttk.Label(self.dynamic, text="Macro").grid(row=0, column=0, sticky="w", pady=3)
            macro_box = ttk.Combobox(
                self.dynamic,
                state="readonly",
                values=[f"{i + 1}: {name}" for i, name in enumerate(self.macro_names)],
                width=26,
            )
            macro_box.grid(row=0, column=1, sticky="ew", pady=3)
            if 0 <= self.macro_index.get() < len(self.macro_names):
                macro_box.current(self.macro_index.get())
            else:
                self.macro_index.set(0)
                macro_box.current(0)
            macro_box.bind(
                "<<ComboboxSelected>>",
                lambda _event, box=macro_box: self.macro_index.set(box.current()),
            )

    def _ok(self) -> None:
        action_type = self._current_type()
        if action_type == cm.ACTION_NONE:
            self.result = cm.Action(type=cm.ACTION_NONE)
        elif action_type == cm.ACTION_KEY:
            self.result = cm.Action(type=cm.ACTION_KEY, param1=self.key_var.get())
        elif action_type == cm.ACTION_MODIFIER_KEY:
            self.result = cm.Action(
                type=cm.ACTION_MODIFIER_KEY,
                param1=self.mod_var.get(),
                param2=self.mod_key_var.get(),
            )
        elif action_type == cm.ACTION_MOUSE_BUTTON:
            buttons = 0
            if self.mouse_left.get():
                buttons |= cm.MOUSE_LEFT
            if self.mouse_right.get():
                buttons |= cm.MOUSE_RIGHT
            if self.mouse_middle.get():
                buttons |= cm.MOUSE_MIDDLE
            self.result = cm.Action(type=cm.ACTION_MOUSE_BUTTON, param1=buttons)
        elif action_type in (
            cm.ACTION_WHEEL_UP_TURBO,
            cm.ACTION_WHEEL_DOWN_TURBO,
            cm.ACTION_WHEEL_UP_COMBO,
            cm.ACTION_WHEEL_DOWN_COMBO,
            cm.ACTION_ALT_TAP_KEY,
            cm.ACTION_SNAPSHOT_MACRO,
        ):
            self.result = cm.Action(type=action_type)
        elif action_type == cm.ACTION_MACRO:
            self.result = cm.Action(
                type=cm.ACTION_MACRO,
                param1=self.macro_index.get(),
                trigger_mode=self.trigger_var.get(),
            )
        self.destroy()


class ComboDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, initial: cm.Combo, macro_names: list[str]):
        super().__init__(parent)
        self.title("Edit combo")
        self.resizable(True, True)
        self.result: Optional[cm.Combo] = None
        self.macro_names = macro_names
        self.action = copy.deepcopy(initial.action)
        self.profile_vars = [
            tk.BooleanVar(value=bool(initial.profile_mask & (1 << profile)))
            for profile in range(cm.PROFILE_COUNT)
        ]
        self.source_vars = [
            tk.BooleanVar(value=bool(initial.source_mask & (1 << source)))
            for source in range(cm.SOURCE_COUNT)
        ]
        self.suppress_vars = [
            tk.BooleanVar(value=bool(initial.suppress_sources & (1 << source)))
            for source in range(cm.SOURCE_COUNT)
        ]

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        profiles = ttk.LabelFrame(body, text="Active profiles", padding=6)
        profiles.pack(fill="x")
        for profile, variable in enumerate(self.profile_vars):
            ttk.Checkbutton(
                profiles, text=f"Profile {profile + 1}", variable=variable
            ).pack(side="left", padx=8)

        required = ttk.LabelFrame(body, text="Required controller inputs", padding=6)
        required.pack(fill="x", pady=(8, 0))
        self._build_source_checks(required, self.source_vars)

        suppressed = ttk.LabelFrame(body, text="Suppress ordinary outputs while active", padding=6)
        suppressed.pack(fill="x", pady=(8, 0))
        self._build_source_checks(suppressed, self.suppress_vars)
        ttk.Button(
            suppressed, text="Use required inputs", command=self._suppress_required
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(5, 0))

        output = ttk.LabelFrame(body, text="Combo output", padding=6)
        output.pack(fill="x", pady=(8, 0))
        self.action_var = tk.StringVar()
        ttk.Label(output, textvariable=self.action_var).pack(side="left", fill="x", expand=True)
        ttk.Button(output, text="Change action...", command=self._change_action).pack(side="right")
        self._refresh_action()

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text="OK", command=self._ok).pack(side="right", padx=4)

        self.transient(parent)
        self.grab_set()
        self.wait_visibility()
        self.focus_set()

    @staticmethod
    def _build_source_checks(parent: ttk.LabelFrame, variables: list[tk.BooleanVar]) -> None:
        for source, variable in enumerate(variables):
            ttk.Checkbutton(
                parent, text=cm.SOURCE_NAMES[source], variable=variable
            ).grid(row=source // 5, column=source % 5, sticky="w", padx=5, pady=2)

    def _suppress_required(self) -> None:
        for source in range(cm.SOURCE_COUNT):
            self.suppress_vars[source].set(self.source_vars[source].get())

    def _refresh_action(self) -> None:
        self.action_var.set(cm.format_action(self.action))

    def _change_action(self) -> None:
        dialog = ActionDialog(self, "Combo output", self.action, self.macro_names)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.action = dialog.result
            self._refresh_action()
        self.grab_set()

    @staticmethod
    def _mask(variables: list[tk.BooleanVar]) -> int:
        result = 0
        for index, variable in enumerate(variables):
            if variable.get():
                result |= 1 << index
        return result

    def _ok(self) -> None:
        profile_mask = self._mask(self.profile_vars)
        source_mask = self._mask(self.source_vars)
        suppress_mask = self._mask(self.suppress_vars)
        if profile_mask == 0:
            messagebox.showerror("Invalid combo", "Select at least one active profile.", parent=self)
            return
        if source_mask == 0:
            messagebox.showerror("Invalid combo", "Select at least one required input.", parent=self)
            return
        if suppress_mask & ~source_mask:
            messagebox.showerror(
                "Invalid combo",
                "Suppressed outputs must also be required inputs for this combo.",
                parent=self,
            )
            return
        if self.action.type == cm.ACTION_NONE:
            messagebox.showerror("Invalid combo", "Choose a combo output action.", parent=self)
            return
        self.result = cm.Combo(profile_mask, source_mask, suppress_mask, self.action)
        self.destroy()


class StickSettingsDialog(tk.Toplevel):
    MODE_LABELS = LEFT_STICK_MODE_LABELS

    def __init__(self, parent: tk.Misc, config: cm.ConfigPayload, profile: int):
        super().__init__(parent)
        self.title(f"Profile {profile + 1} stick rules")
        self.resizable(False, False)
        self.profile = profile
        self.candidate = copy.deepcopy(config)
        self.result: Optional[cm.Settings] = None
        settings = self.candidate.settings
        self.mode_var = tk.StringVar(value=self.MODE_LABELS[settings.left_stick_mode[profile]])
        self.vars: dict[str, tk.Variable] = {}

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Left stick mode").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(
            body,
            textvariable=self.mode_var,
            state="readonly",
            values=self.MODE_LABELS,
            width=42,
        ).grid(row=0, column=1, sticky="ew", padx=8, pady=3)

        fields = [
            ("left_deadzone", "Left radial deadzone (0.0-<1.0; all profiles)", settings.left_deadzone),
            ("right_deadzone", "Right per-axis deadzone (0.0-<1.0; all profiles)", settings.right_deadzone),
            ("mouse_speed_x", "Right-stick base X speed (counts/s at DPI 1000)", settings.mouse_speed_x[profile]),
            ("mouse_speed_y", "Right-stick base Y speed (counts/s at DPI 1000)", settings.mouse_speed_y[profile]),
            ("right_center_x", "Right raw center X (0-4095; all profiles)", settings.right_center_x),
            ("right_center_y", "Right raw center Y (0-4095; all profiles)", settings.right_center_y),
        ]
        if profile == 1:
            fields.extend(
                [
                    ("profile2_rb_speed_x", "While-RB base X speed (counts/s at DPI 1000)", settings.profile2_rb_speed_x),
                    ("profile2_rb_speed_y", "While-RB base Y speed (counts/s at DPI 1000)", settings.profile2_rb_speed_y),
                    (
                        "profile2_outer_threshold_percent",
                        "Outer-ring threshold (1-100%)",
                        settings.profile2_outer_threshold_percent,
                    ),
                    (
                        "profile2_no_rb_ramp_ms",
                        "No-RB outer acceleration ramp (ms)",
                        settings.profile2_no_rb_ramp_ms,
                    ),
                    (
                        "profile2_no_rb_extra_x",
                        "No-RB extra X speed (base counts/s)",
                        settings.profile2_no_rb_extra_x,
                    ),
                    ("profile2_rb_delay_ms", "RB acceleration delay (ms)", settings.profile2_rb_delay_ms),
                    ("profile2_rb_ramp_ms", "RB acceleration ramp (ms)", settings.profile2_rb_ramp_ms),
                    ("profile2_rb_extra_x", "RB extra X speed (base counts/s)", settings.profile2_rb_extra_x),
                    ("profile2_rb_extra_y", "RB extra Y speed (base counts/s)", settings.profile2_rb_extra_y),
                ]
            )

        for row, (key, label, value) in enumerate(fields, start=1):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=3)
            variable = tk.StringVar(value=str(value))
            ttk.Entry(body, textvariable=variable, width=28).grid(
                row=row, column=1, sticky="ew", padx=8, pady=3
            )
            self.vars[key] = variable

        next_row = len(fields) + 1
        if profile == 1:
            self.accel_var = tk.BooleanVar(value=bool(settings.profile2_accel_enabled))
            ttk.Checkbutton(
                body, text="Enable Profile 2 outer-ring acceleration", variable=self.accel_var
            ).grid(row=next_row, column=0, columnspan=2, sticky="w", pady=4)
            next_row += 1
        else:
            self.accel_var = tk.BooleanVar(value=bool(settings.profile2_accel_enabled))

        ttk.Label(
            body,
            text="Set mouse speeds to 0 and left mode to Off to replace analog movement with direction bindings.",
            wraplength=520,
        ).grid(row=next_row, column=0, columnspan=2, sticky="w", pady=(8, 3))
        next_row += 1
        buttons = ttk.Frame(body)
        buttons.grid(row=next_row, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text="OK", command=self._ok).pack(side="right", padx=4)

        self.transient(parent)
        self.grab_set()
        self.wait_visibility()
        self.focus_set()

    def _ok(self) -> None:
        settings = self.candidate.settings
        try:
            settings.left_stick_mode[self.profile] = self.MODE_LABELS.index(self.mode_var.get())
            settings.left_deadzone = float(self.vars["left_deadzone"].get())
            settings.right_deadzone = float(self.vars["right_deadzone"].get())
            settings.mouse_speed_x[self.profile] = int(self.vars["mouse_speed_x"].get())
            settings.mouse_speed_y[self.profile] = int(self.vars["mouse_speed_y"].get())
            settings.right_center_x = int(self.vars["right_center_x"].get())
            settings.right_center_y = int(self.vars["right_center_y"].get())
            if self.profile == 1:
                for key in (
                    "profile2_rb_speed_x",
                    "profile2_rb_speed_y",
                    "profile2_outer_threshold_percent",
                    "profile2_no_rb_ramp_ms",
                    "profile2_no_rb_extra_x",
                    "profile2_rb_delay_ms",
                    "profile2_rb_ramp_ms",
                    "profile2_rb_extra_x",
                    "profile2_rb_extra_y",
                ):
                    setattr(settings, key, int(self.vars[key].get()))
                settings.profile2_accel_enabled = int(self.accel_var.get())
            settings.advanced_stick_version = cm.ADVANCED_STICK_VERSION
            cm.validate_config(self.candidate)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Invalid stick settings", str(exc), parent=self)
            return
        self.result = settings
        self.destroy()


class MacroStepDialog(tk.Toplevel):
    TYPE_LABELS = ("Delay", "Keyboard state", "Mouse state")

    def __init__(self, parent: tk.Misc, initial: cm.MacroStep):
        super().__init__(parent)
        self.title("Edit macro step")
        self.resizable(False, False)
        self.result: Optional[cm.MacroStep] = None
        self.type_var = tk.StringVar(value=self.TYPE_LABELS[initial.type])
        self.duration_var = tk.StringVar(value=str(initial.duration_ms))
        self.modifier_vars = {
            bit: tk.BooleanVar(value=bool(initial.modifier & bit)) for bit in cm.MODIFIER_NAMES
        }
        initial_keys = list(initial.keys[:6]) + [0] * 6
        self.key_vars = [tk.IntVar(value=initial_keys[index]) for index in range(6)]
        buttons = initial.keys[0] if initial.keys else 0
        self.mouse_button_vars = {
            cm.MOUSE_LEFT: tk.BooleanVar(value=bool(buttons & cm.MOUSE_LEFT)),
            cm.MOUSE_RIGHT: tk.BooleanVar(value=bool(buttons & cm.MOUSE_RIGHT)),
            cm.MOUSE_MIDDLE: tk.BooleanVar(value=bool(buttons & cm.MOUSE_MIDDLE)),
        }
        dx = initial_keys[1] - 256 if initial_keys[1] > 127 else initial_keys[1]
        dy = initial_keys[2] - 256 if initial_keys[2] > 127 else initial_keys[2]
        self.dx_var = tk.StringVar(value=str(dx))
        self.dy_var = tk.StringVar(value=str(dy))
        self.wheel_var = tk.StringVar(value=str(initial.value))

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Step type").grid(row=0, column=0, sticky="w")
        type_box = ttk.Combobox(
            body, textvariable=self.type_var, values=self.TYPE_LABELS, state="readonly", width=24
        )
        type_box.grid(row=0, column=1, sticky="ew", padx=6)
        type_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        ttk.Label(body, text="Duration (ms)").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=self.duration_var, width=26).grid(
            row=1, column=1, sticky="ew", padx=6, pady=4
        )
        self.dynamic = ttk.Frame(body)
        self.dynamic.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=6)
        self._refresh()
        buttons_row = ttk.Frame(body)
        buttons_row.grid(row=3, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons_row, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(buttons_row, text="OK", command=self._ok).pack(side="right", padx=4)

        self.transient(parent)
        self.grab_set()
        self.wait_visibility()
        self.focus_set()

    def _refresh(self) -> None:
        for widget in self.dynamic.winfo_children():
            widget.destroy()
        step_type = self.TYPE_LABELS.index(self.type_var.get())
        if step_type == cm.MACRO_STEP_DELAY:
            ttk.Label(self.dynamic, text="No output; wait for the duration above.").grid(
                row=0, column=0, sticky="w"
            )
        elif step_type == cm.MACRO_STEP_KEYBOARD:
            mods = ttk.LabelFrame(self.dynamic, text="Modifiers", padding=4)
            mods.grid(row=0, column=0, columnspan=2, sticky="ew")
            for index, (bit, name) in enumerate(cm.MODIFIER_NAMES.items()):
                ttk.Checkbutton(mods, text=name, variable=self.modifier_vars[bit]).grid(
                    row=index // 4, column=index % 4, sticky="w", padx=3
                )
            values = ["(none)"] + [
                f"0x{code:02X} {name}" for code, name in sorted(cm.HID_KEY_NAMES.items()) if code
            ]
            for index, variable in enumerate(self.key_vars):
                ttk.Label(self.dynamic, text=f"Key {index + 1}").grid(
                    row=index + 1, column=0, sticky="w", pady=2
                )
                box = ttk.Combobox(self.dynamic, state="readonly", values=values, width=25)
                box.grid(row=index + 1, column=1, sticky="ew", pady=2)
                ActionDialog._set_key_combo(variable, box)
                box.bind(
                    "<<ComboboxSelected>>",
                    lambda _event, var=variable, widget=box: ActionDialog._set_key_from_label(
                        var, widget.get()
                    ),
                )
        else:
            ttk.Label(self.dynamic, text="Buttons").grid(row=0, column=0, sticky="w")
            button_frame = ttk.Frame(self.dynamic)
            button_frame.grid(row=0, column=1, sticky="w")
            for bit, name in (
                (cm.MOUSE_LEFT, "Left"),
                (cm.MOUSE_RIGHT, "Right"),
                (cm.MOUSE_MIDDLE, "Middle"),
            ):
                ttk.Checkbutton(
                    button_frame, text=name, variable=self.mouse_button_vars[bit]
                ).pack(side="left")
            for row, (label, variable) in enumerate(
                (("Move X", self.dx_var), ("Move Y", self.dy_var), ("Wheel", self.wheel_var)),
                start=1,
            ):
                ttk.Label(self.dynamic, text=label).grid(row=row, column=0, sticky="w", pady=2)
                ttk.Entry(self.dynamic, textvariable=variable, width=26).grid(
                    row=row, column=1, sticky="ew", pady=2
                )

    def _ok(self) -> None:
        try:
            step_type = self.TYPE_LABELS.index(self.type_var.get())
            duration = int(self.duration_var.get())
            if not 0 <= duration <= 0xFFFF:
                raise ValueError("duration must be in 0..65535 ms")
            if step_type == cm.MACRO_STEP_DELAY:
                step = cm.MacroStep(type=step_type, duration_ms=duration)
            elif step_type == cm.MACRO_STEP_KEYBOARD:
                modifier = sum(bit for bit, variable in self.modifier_vars.items() if variable.get())
                step = cm.MacroStep(
                    type=step_type,
                    modifier=modifier,
                    keys=tuple(variable.get() for variable in self.key_vars),
                    duration_ms=duration,
                )
            else:
                dx = int(self.dx_var.get())
                dy = int(self.dy_var.get())
                wheel = int(self.wheel_var.get())
                if not -128 <= dx <= 127 or not -128 <= dy <= 127:
                    raise ValueError("mouse X/Y must be in -128..127")
                if not -128 <= wheel <= 127:
                    raise ValueError("wheel must be in -128..127")
                buttons = sum(
                    bit for bit, variable in self.mouse_button_vars.items() if variable.get()
                )
                step = cm.MacroStep(
                    type=step_type,
                    keys=(buttons, dx, dy, 0, 0, 0),
                    value=wheel,
                    duration_ms=duration,
                )
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Invalid macro step", str(exc), parent=self)
            return
        self.result = step
        self.destroy()


class BindingsTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app: "App"):
        super().__init__(parent)
        self.app = app

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=6)
        ttk.Label(toolbar, text="Profile").pack(side="left")
        self.profile_var = tk.StringVar(value="Profile 1")
        profile_box = ttk.Combobox(toolbar, textvariable=self.profile_var, state="readonly",
                                   values=["Profile 1", "Profile 2", "Profile 3"], width=12)
        profile_box.pack(side="left", padx=6)
        profile_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())

        ttk.Label(
            toolbar,
            text="Direct bindings, stick rules, combos and macros below reflect the same board config.",
        ).pack(side="left", padx=12)

        paned = ttk.Panedwindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        direct = ttk.LabelFrame(paned, text="Direct bindings (double-click a Tap/Hold/Double cell to edit)")
        columns = ("input", "tap", "hold", "double")
        self.tree = ttk.Treeview(direct, columns=columns, show="headings", selectmode="browse", height=12)
        self.tree.heading("input", text="Controller input")
        self.tree.heading("tap", text="Tap")
        self.tree.heading("hold", text="Hold / while pressed")
        self.tree.heading("double", text="Double tap")
        self.tree.column("input", width=130)
        self.tree.column("tap", width=200)
        self.tree.column("hold", width=200)
        self.tree.column("double", width=200)
        direct_scroll = ttk.Scrollbar(direct, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=direct_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=5)
        direct_scroll.pack(side="right", fill="y", padx=(0, 5), pady=5)

        self.tree.bind("<Double-1>", self._edit)
        paned.add(direct, weight=3)

        details = ttk.Notebook(paned)
        paned.add(details, weight=2)

        stick_page = ttk.Frame(details)
        stick_toolbar = ttk.Frame(stick_page)
        stick_toolbar.pack(fill="x", padx=5, pady=4)
        ttk.Button(stick_toolbar, text="Edit stick rules...", command=self._edit_sticks).pack(
            side="right"
        )
        self.stick_tree = ttk.Treeview(
            stick_page, columns=("rule", "value"), show="headings", height=8
        )
        self.stick_tree.heading("rule", text="Stick rule")
        self.stick_tree.heading("value", text="Effective value")
        self.stick_tree.column("rule", width=210, stretch=False)
        self.stick_tree.column("value", width=760)
        self.stick_tree.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        details.add(stick_page, text="Stick / mouse rules")

        combo_page = ttk.Frame(details)
        combo_toolbar = ttk.Frame(combo_page)
        combo_toolbar.pack(fill="x", padx=5, pady=4)
        ttk.Button(combo_toolbar, text="Add combo...", command=self._add_combo).pack(side="left")
        ttk.Button(combo_toolbar, text="Edit selected...", command=self._edit_combo).pack(
            side="left", padx=4
        )
        ttk.Button(combo_toolbar, text="Clear selected", command=self._clear_combo).pack(side="left")
        combo_table = ttk.Frame(combo_page)
        combo_table.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        self.combo_tree = ttk.Treeview(
            combo_table,
            columns=("slot", "profiles", "input", "output", "suppress"),
            show="headings",
            selectmode="browse",
            height=8,
        )
        for column, label, width in (
            ("slot", "Slot", 55),
            ("profiles", "Profiles", 75),
            ("input", "Required inputs", 270),
            ("output", "Output", 260),
            ("suppress", "Suppress ordinary output", 300),
        ):
            self.combo_tree.heading(column, text=label)
            self.combo_tree.column(column, width=width, stretch=column not in ("slot", "profiles"))
        combo_xscroll = ttk.Scrollbar(
            combo_table, orient="horizontal", command=self.combo_tree.xview
        )
        self.combo_tree.configure(xscrollcommand=combo_xscroll.set)
        self.combo_tree.pack(fill="both", expand=True)
        combo_xscroll.pack(fill="x")
        self.combo_tree.bind("<Double-1>", lambda _event: self._edit_combo())
        details.add(combo_page, text="Combos")

        macro_page = ttk.Frame(details)
        ttk.Label(
            macro_page, text="All macro slots; double-click one to open its editable step list."
        ).pack(anchor="w", padx=5, pady=4)
        macro_table = ttk.Frame(macro_page)
        macro_table.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        self.macro_tree = ttk.Treeview(
            macro_table,
            columns=("slot", "name", "trigger", "bound", "steps"),
            show="headings",
            selectmode="browse",
            height=8,
        )
        for column, label, width in (
            ("slot", "Slot", 55),
            ("name", "Name", 180),
            ("trigger", "Trigger", 100),
            ("bound", "Bound in profile", 240),
            ("steps", "Complete sequence", 650),
        ):
            self.macro_tree.heading(column, text=label)
            self.macro_tree.column(column, width=width, stretch=column in ("bound", "steps"))
        macro_xscroll = ttk.Scrollbar(
            macro_table, orient="horizontal", command=self.macro_tree.xview
        )
        self.macro_tree.configure(xscrollcommand=macro_xscroll.set)
        self.macro_tree.pack(fill="both", expand=True)
        macro_xscroll.pack(fill="x")
        self.macro_tree.bind("<Double-1>", self._open_macro)
        details.add(macro_page, text="Macros")
        self.refresh()

    def _profile(self) -> int:
        value = str(self.profile_var.get())
        for index, name in enumerate(("Profile 1", "Profile 2", "Profile 3")):
            if value.startswith(name):
                return index
        return 0

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.stick_tree.delete(*self.stick_tree.get_children())
        self.combo_tree.delete(*self.combo_tree.get_children())
        self.macro_tree.delete(*self.macro_tree.get_children())
        profile = self._profile()
        if self.app.config is None:
            return
        for source in range(cm.SOURCE_COUNT):
            tap = format_action_for_config(
                self.app.config, self.app.config.bindings[profile][source][cm.GESTURE_TAP]
            )
            hold_action = self.app.config.bindings[profile][source][cm.GESTURE_HOLD]
            hold = format_action_for_config(self.app.config, hold_action)
            if hold_action.type != cm.ACTION_NONE and hold_action.duration_ms == 1:
                hold = f"While pressed: {hold}"
            double = format_action_for_config(
                self.app.config, self.app.config.bindings[profile][source][cm.GESTURE_DOUBLE]
            )
            input_name = cm.SOURCE_NAMES[source]
            if source >= cm.SRC_LSTICK_UP:
                input_name += " (direction)"
            self.tree.insert("", "end", iid=str(source), values=(input_name, tap, hold, double))

        for index, (rule, value) in enumerate(build_profile_stick_rows(self.app.config, profile)):
            self.stick_tree.insert("", "end", iid=str(index), values=(rule, value))
        for slot, profiles, inputs, output, suppress in build_profile_combo_rows(
            self.app.config, profile
        ):
            self.combo_tree.insert(
                "", "end", iid=str(slot), values=(slot + 1, profiles, inputs, output, suppress)
            )
        for slot, name, trigger, bound, steps in build_profile_macro_rows(self.app.config, profile):
            self.macro_tree.insert(
                "", "end", iid=str(slot), values=(slot + 1, name, trigger, bound, steps)
            )

    def _edit(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        source = int(selection[0])
        profile = self._profile()
        gesture = self.tree.identify_column(self.tree.winfo_pointerx() - self.tree.winfo_rootx())
        column_index = max(0, int(gesture.replace("#", "")) - 1)
        gesture_index = {1: cm.GESTURE_TAP, 2: cm.GESTURE_HOLD, 3: cm.GESTURE_DOUBLE}.get(
            column_index, cm.GESTURE_TAP
        )
        action = self.app.config.bindings[profile][source][gesture_index]
        dialog = ActionDialog(
            self,
            f"{cm.SOURCE_NAMES[source]} - {cm.GESTURE_NAMES[gesture_index]}",
            action,
            [macro.name for macro in self.app.config.macros],
        )
        self.wait_window(dialog)
        if dialog.result is not None:
            if gesture_index == cm.GESTURE_HOLD and dialog.result.type in (
                cm.ACTION_KEY,
                cm.ACTION_MODIFIER_KEY,
                cm.ACTION_MOUSE_BUTTON,
                cm.ACTION_WHEEL_UP_TURBO,
                cm.ACTION_WHEEL_DOWN_TURBO,
                cm.ACTION_WHEEL_UP_COMBO,
                cm.ACTION_WHEEL_DOWN_COMBO,
            ):
                # Keep the firmware's hold delay (0 = global threshold, 1 = immediate).
                dialog.result.duration_ms = action.duration_ms
            self.app.config.bindings[profile][source][gesture_index] = dialog.result
            self.refresh()

    def _edit_sticks(self) -> None:
        if self.app.config is None:
            return
        dialog = StickSettingsDialog(self, self.app.config, self._profile())
        self.wait_window(dialog)
        if dialog.result is not None:
            self.app.config.settings = dialog.result
            self.app.settings_tab.refresh()
            self.refresh()

    def _selected_combo(self) -> Optional[int]:
        selection = self.combo_tree.selection()
        return int(selection[0]) if selection else None

    def _add_combo(self) -> None:
        if self.app.config is None:
            return
        slot = next(
            (
                index
                for index, combo in enumerate(self.app.config.combos)
                if combo.profile_mask == 0 or combo.action.type == cm.ACTION_NONE
            ),
            None,
        )
        if slot is None:
            messagebox.showwarning("No free combo slot", "All 16 combo slots are in use.")
            return
        initial = cm.Combo(profile_mask=1 << self._profile())
        self._show_combo_dialog(slot, initial)

    def _edit_combo(self) -> None:
        if self.app.config is None:
            return
        slot = self._selected_combo()
        if slot is None:
            messagebox.showinfo("Select combo", "Select a combo row first.")
            return
        self._show_combo_dialog(slot, self.app.config.combos[slot])

    def _show_combo_dialog(self, slot: int, combo: cm.Combo) -> None:
        dialog = ComboDialog(
            self, combo, [macro.name for macro in self.app.config.macros]
        )
        self.wait_window(dialog)
        if dialog.result is not None:
            self.app.config.combos[slot] = dialog.result
            self.refresh()

    def _clear_combo(self) -> None:
        if self.app.config is None:
            return
        slot = self._selected_combo()
        if slot is None:
            messagebox.showinfo("Select combo", "Select a combo row first.")
            return
        combo = self.app.config.combos[slot]
        profiles = ", ".join(
            str(profile + 1)
            for profile in range(cm.PROFILE_COUNT)
            if combo.profile_mask & (1 << profile)
        )
        if not messagebox.askyesno(
            "Clear combo",
            f"Clear combo slot {slot + 1} from profile(s) {profiles}?",
        ):
            return
        self.app.config.combos[slot] = cm.Combo()
        self.refresh()

    def _open_macro(self, _event: Optional[tk.Event] = None) -> None:
        selection = self.macro_tree.selection()
        if not selection or not hasattr(self.app, "macros_tab"):
            return
        index = int(selection[0])
        self.app.macros_tab._commit_editor(self.app.macros_tab.selected_index.get())
        self.app.macros_tab.selected_index.set(index)
        self.app.macros_tab.refresh()
        self.app.notebook.select(self.app.macros_tab)


class MacrosTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app: "App"):
        super().__init__(parent)
        self.app = app
        self.recorder: Optional[Recorder] = None
        self.recording_index: Optional[int] = None
        self.selected_index = tk.IntVar(value=0)
        self._refreshing = False
        self._recorder_stop_event = threading.Event()
        self._recorder_messages: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._record_poll_id: Optional[str] = None

        left = ttk.Frame(self)
        left.pack(side="left", fill="y", padx=8, pady=8)
        ttk.Label(left, text="Macros").pack(anchor="w")
        self.listbox = tk.Listbox(left, width=28, height=20, exportselection=False)
        self.listbox.pack(fill="y", expand=True, pady=4)
        self.listbox.bind("<<ListboxSelect>>", self._select)

        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=4)
        self.record_motion_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(buttons, text="Mouse motion", variable=self.record_motion_var).pack(anchor="w")
        ttk.Button(buttons, text="Record", command=self._record).pack(side="left", padx=2)
        self.stop_button = ttk.Button(
            buttons,
            text="Stop (F12)",
            command=lambda: self._stop(discard_stop_click=True),
        )
        self.stop_button.pack(side="left", padx=2)
        ttk.Button(buttons, text="Clear", command=self._clear).pack(side="left", padx=2)

        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        row1 = ttk.Frame(right)
        row1.pack(fill="x")
        ttk.Label(row1, text="Name").pack(side="left")
        self.name_var = tk.StringVar(value="")
        ttk.Entry(row1, textvariable=self.name_var, width=32).pack(side="left", padx=6)
        ttk.Label(row1, text="Trigger").pack(side="left", padx=(12, 0))
        self.trigger_var = tk.StringVar(value=cm.MACRO_TRIGGER_NAMES[0])
        trigger_box = ttk.Combobox(row1, textvariable=self.trigger_var, state="readonly",
                                   values=cm.MACRO_TRIGGER_NAMES, width=14)
        trigger_box.pack(side="left", padx=6)

        step_buttons = ttk.Frame(right)
        step_buttons.pack(fill="x", pady=(8, 2))
        ttk.Button(step_buttons, text="Add step...", command=self._add_step).pack(side="left")
        ttk.Button(step_buttons, text="Edit step...", command=self._edit_step).pack(
            side="left", padx=3
        )
        ttk.Button(step_buttons, text="Delete step", command=self._delete_step).pack(side="left")
        ttk.Button(step_buttons, text="Move up", command=lambda: self._move_step(-1)).pack(
            side="left", padx=(12, 3)
        )
        ttk.Button(step_buttons, text="Move down", command=lambda: self._move_step(1)).pack(
            side="left"
        )
        step_table = ttk.Frame(right)
        step_table.pack(fill="both", expand=True, pady=(0, 8))
        self.steps_tree = ttk.Treeview(
            step_table,
            columns=("number", "step"),
            show="headings",
            selectmode="browse",
            height=16,
        )
        self.steps_tree.heading("number", text="#")
        self.steps_tree.heading("step", text="Complete macro state / delay")
        self.steps_tree.column("number", width=45, stretch=False, anchor="center")
        self.steps_tree.column("step", width=650)
        step_scroll = ttk.Scrollbar(step_table, orient="vertical", command=self.steps_tree.yview)
        self.steps_tree.configure(yscrollcommand=step_scroll.set)
        self.steps_tree.pack(side="left", fill="both", expand=True)
        step_scroll.pack(side="right", fill="y")
        self.steps_tree.bind("<Double-1>", lambda _event: self._edit_step())
        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(right, textvariable=self.status_var).pack(anchor="w")

        self.refresh()

    def refresh(self) -> None:
        self._refreshing = True
        try:
            self.listbox.delete(0, "end")
            if self.app.config is None or not self.app.config.macros:
                return
            for index, macro in enumerate(self.app.config.macros):
                self.listbox.insert("end", f"{index + 1}: {macro.name or 'unnamed'}")
            index = min(max(self.selected_index.get(), 0), len(self.app.config.macros) - 1)
            self.selected_index.set(index)
            self.listbox.selection_set(index)
            self.listbox.activate(index)
            self.listbox.see(index)
            self._load_editor(self.app.config.macros[index])
        finally:
            self._refreshing = False

    def _selected_macro(self) -> Optional[cm.Macro]:
        if self.app.config is None or not self.app.config.macros:
            return None
        index = min(max(self.selected_index.get(), 0), len(self.app.config.macros) - 1)
        return self.app.config.macros[index]

    def _select(self, _event: Optional[tk.Event] = None) -> None:
        if self._refreshing or self.app.config is None:
            return
        selection = self.listbox.curselection()
        if not selection:
            return
        new_index = int(selection[0])
        old_index = self.selected_index.get()
        if new_index != old_index:
            self._commit_editor(old_index)
        self.selected_index.set(new_index)
        macro = self.app.config.macros[new_index]
        self._load_editor(macro)

    def _load_editor(self, macro: cm.Macro) -> None:
        self.name_var.set(macro.name)
        if 0 <= macro.trigger_mode < len(cm.MACRO_TRIGGER_NAMES):
            self.trigger_var.set(cm.MACRO_TRIGGER_NAMES[macro.trigger_mode])
        else:
            self.trigger_var.set(cm.MACRO_TRIGGER_NAMES[0])
        self._render_steps(macro)

    def _commit_editor(self, index: int) -> None:
        if self.app.config is None or not 0 <= index < len(self.app.config.macros):
            return
        macro = self.app.config.macros[index]
        name = self.name_var.get().strip()
        if name:
            macro.name = name
        trigger_name = str(self.trigger_var.get())
        if trigger_name in cm.MACRO_TRIGGER_NAMES:
            macro.trigger_mode = cm.MACRO_TRIGGER_NAMES.index(trigger_name)

    def _render_steps(self, macro: cm.Macro) -> None:
        self.steps_tree.delete(*self.steps_tree.get_children())
        for i, step in enumerate(macro.steps[: macro.step_count]):
            self.steps_tree.insert(
                "", "end", iid=str(i), values=(i + 1, cm.format_macro_step(step))
            )

    def _selected_step_index(self) -> Optional[int]:
        selection = self.steps_tree.selection()
        return int(selection[0]) if selection else None

    def _add_step(self) -> None:
        self._commit_editor(self.selected_index.get())
        macro = self._selected_macro()
        if macro is None:
            return
        if macro.step_count >= cm.MACRO_STEP_MAX:
            messagebox.showwarning("Macro full", f"A macro can contain at most {cm.MACRO_STEP_MAX} steps.")
            return
        dialog = MacroStepDialog(self, cm.MacroStep(type=cm.MACRO_STEP_DELAY, duration_ms=10))
        self.wait_window(dialog)
        if dialog.result is None:
            return
        selected = self._selected_step_index()
        insert_at = macro.step_count if selected is None else selected + 1
        macro.steps.insert(insert_at, dialog.result)
        macro.step_count = len(macro.steps)
        self._render_steps(macro)
        self.steps_tree.selection_set(str(insert_at))
        self._refresh_overview()

    def _edit_step(self) -> None:
        macro = self._selected_macro()
        index = self._selected_step_index()
        if macro is None or index is None or not 0 <= index < macro.step_count:
            messagebox.showinfo("Select step", "Select a macro step first.")
            return
        dialog = MacroStepDialog(self, macro.steps[index])
        self.wait_window(dialog)
        if dialog.result is not None:
            macro.steps[index] = dialog.result
            self._render_steps(macro)
            self.steps_tree.selection_set(str(index))
            self._refresh_overview()

    def _delete_step(self) -> None:
        macro = self._selected_macro()
        index = self._selected_step_index()
        if macro is None or index is None or not 0 <= index < macro.step_count:
            messagebox.showinfo("Select step", "Select a macro step first.")
            return
        del macro.steps[index]
        macro.step_count = len(macro.steps)
        self._render_steps(macro)
        if macro.step_count:
            self.steps_tree.selection_set(str(min(index, macro.step_count - 1)))
        self._refresh_overview()

    def _move_step(self, direction: int) -> None:
        macro = self._selected_macro()
        index = self._selected_step_index()
        if macro is None or index is None:
            messagebox.showinfo("Select step", "Select a macro step first.")
            return
        target = index + direction
        if not 0 <= target < macro.step_count:
            return
        macro.steps[index], macro.steps[target] = macro.steps[target], macro.steps[index]
        self._render_steps(macro)
        self.steps_tree.selection_set(str(target))
        self._refresh_overview()

    def _refresh_overview(self) -> None:
        if hasattr(self.app, "bindings_tab"):
            self.app.bindings_tab.refresh()

    def _save_selected_fields(self) -> None:
        self._commit_editor(self.selected_index.get())
        self.refresh()
        self._refresh_overview()

    def _record(self) -> None:
        if self.app.config is None:
            messagebox.showinfo("Not connected", "Read a board configuration before recording macros.")
            return
        self._save_selected_fields()
        if self.recorder is not None:
            return
        self.recording_index = self.selected_index.get()
        self.recorder = Recorder(record_mouse_motion=bool(self.record_motion_var.get()), max_events=100)
        self._recorder_stop_event.clear()
        while not self._recorder_messages.empty():
            try:
                self._recorder_messages.get_nowait()
            except queue.Empty:
                break
        self.status_var.set("Recording keyboard/mouse... Press F12 when done.")
        try:
            self.recorder.start(
                warn=self._recorder_messages.put,
                stop_requested=self._recorder_stop_event.set,
            )
            self._record_poll_id = self.after(50, self._poll_recorder)
        except Exception as exc:
            self.status_var.set(str(exc))
            messagebox.showerror("Recorder unavailable", str(exc))
            self.recorder = None
            self.recording_index = None

    def _poll_recorder(self) -> None:
        self._record_poll_id = None
        if self.recorder is None:
            return
        while True:
            try:
                message = self._recorder_messages.get_nowait()
            except queue.Empty:
                break
            self.status_var.set(message + " Press F12 to finish.")
        if self._recorder_stop_event.is_set():
            self._stop()
            return
        self._record_poll_id = self.after(50, self._poll_recorder)

    def _stop(self, discard_stop_click: bool = False) -> None:
        if self.recorder is None:
            return
        if self._record_poll_id is not None:
            self.after_cancel(self._record_poll_id)
            self._record_poll_id = None
        stop_region: Optional[tuple[int, int, int, int]] = None
        if discard_stop_click:
            left = self.stop_button.winfo_rootx()
            top = self.stop_button.winfo_rooty()
            stop_region = (
                left,
                top,
                left + self.stop_button.winfo_width(),
                top + self.stop_button.winfo_height(),
            )
        self.recorder.stop()
        if stop_region is not None:
            self.recorder.discard_trailing_click(
                *stop_region,
            )
        self._commit_editor(self.selected_index.get())
        if self.app.config is None:
            self.recorder = None
            self.recording_index = None
            self.status_var.set("Connect to a board before recording macros.")
            return
        index = self.recording_index
        if index is None or not 0 <= index < len(self.app.config.macros):
            self.recorder = None
            self.recording_index = None
            self.status_var.set("Recording slot is no longer available.")
            return
        previous = self.app.config.macros[index]
        try:
            macro = self.recorder.encode(
                name=previous.name or "Recorded macro",
                trigger_mode=previous.trigger_mode,
            )
        except Exception as exc:
            messagebox.showerror("Macro too long", str(exc))
            self.recorder = None
            self.recording_index = None
            self.status_var.set("Recording discarded.")
            return
        self.app.config.macros[index] = macro
        self.recorder = None
        self.recording_index = None
        self.status_var.set(f"Recorded {macro.step_count} steps in slot {index + 1}.")
        self.refresh()
        self._refresh_overview()

    def _clear(self) -> None:
        self._commit_editor(self.selected_index.get())
        macro = self._selected_macro()
        if macro is not None:
            macro.step_count = 0
            macro.steps = []
            self.refresh()
            self._refresh_overview()


class SettingsTab(ttk.Frame):
    CHOICE_VALUES = {
        "left_mode_1": LEFT_STICK_MODE_LABELS,
        "left_mode_2": LEFT_STICK_MODE_LABELS,
        "left_mode_3": LEFT_STICK_MODE_LABELS,
        "active_profile": ACTIVE_PROFILE_LABELS,
        "output_enabled": OUTPUT_STATE_LABELS,
    }

    def __init__(self, parent: ttk.Notebook, app: "App"):
        super().__init__(parent)
        self.app = app
        self.vars: dict[str, tk.Variable] = {}
        self._calibration_poll_id: Optional[str] = None

        rows = [
            ("left_mode_1", "Profile 1 left-stick mode", "How the left stick becomes WASD in Profile 1."),
            ("left_mode_2", "Profile 2 left-stick mode", "How the left stick becomes WASD in Profile 2."),
            ("left_mode_3", "Profile 3 left-stick mode", "How the left stick becomes WASD in Profile 3."),
            ("active_profile", "Active profile", "Selects the profile the board uses now."),
            ("output_enabled", "Keyboard/mouse output", "Master switch; Disabled releases and stops mapped output."),
            ("tap_ms", "Tap output duration (ms)", "How long a Tap action stays pressed; 1-60000 ms."),
            ("hold_ms", "Hold activation threshold (ms)", "Default time before a Hold action starts; 1-60000 ms."),
            ("double_ms", "Double-click window (ms)", "Maximum gap used to recognize a double tap; 1-60000 ms."),
            ("turbo_hz", "Turbo wheel rate (events/s)", "Repeat rate for Wheel Up/Down Turbo actions; 1-1000."),
            ("combo_hz", "Combo wheel rate (events/s)", "Repeat rate for Wheel Up/Down Combo actions; 1-1000."),
            ("grace_ms", "Mouse-button release grace (ms)", "Holds any mapped mouse button through brief report gaps; 0-5000 ms."),
            ("left_dz", "Left radial deadzone (all profiles)", "Ignores total left-stick magnitude below this value; 0.0-<1.0."),
            ("right_dz", "Right per-axis deadzone (all profiles)", "Ignores each right-stick axis below this value; 0.0-<1.0."),
            ("virtual_dpi", "Virtual DPI (all profiles)", "Global count multiplier, 100-20000; 1000 preserves legacy speed."),
            ("speed_x_1", "Profile 1 base X speed", "Full-stick horizontal counts/s before the DPI multiplier; 0-65535."),
            ("speed_y_1", "Profile 1 base Y speed", "Full-stick vertical counts/s before the DPI multiplier; 0-65535."),
            ("speed_x_2", "Profile 2 base X speed", "Full-stick horizontal counts/s before the DPI multiplier; 0-65535."),
            ("speed_y_2", "Profile 2 base Y speed", "Full-stick vertical counts/s before the DPI multiplier; 0-65535."),
            ("speed_x_3", "Profile 3 base X speed", "Full-stick horizontal counts/s before the DPI multiplier; 0-65535."),
            ("speed_y_3", "Profile 3 base Y speed", "Full-stick vertical counts/s before the DPI multiplier; 0-65535."),
        ]

        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        content = ttk.Frame(canvas)
        content_window = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(content_window, width=event.width),
        )

        grid = ttk.Frame(content)
        grid.pack(fill="both", expand=True, padx=12, pady=12)
        grid.columnconfigure(2, weight=1)
        self.entries: dict[str, ttk.Widget] = {}
        ttk.Label(grid, text="Setting").grid(row=0, column=0, sticky="w", padx=4, pady=(0, 5))
        ttk.Label(grid, text="Value").grid(row=0, column=1, sticky="w", padx=4, pady=(0, 5))
        ttk.Label(grid, text="Meaning / range").grid(row=0, column=2, sticky="w", padx=8, pady=(0, 5))
        for row, (key, label, description) in enumerate(rows, start=1):
            ttk.Label(grid, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=3)
            values = self.CHOICE_VALUES.get(key)
            if values is not None:
                var = tk.StringVar()
                box = ttk.Combobox(
                    grid,
                    textvariable=var,
                    state="readonly",
                    values=values,
                    width=38,
                )
                box.grid(row=row, column=1, sticky="ew", padx=4)
                self.entries[key] = box
            else:
                var = tk.StringVar()
                entry = ttk.Entry(grid, textvariable=var, width=40)
                entry.grid(row=row, column=1, sticky="ew", padx=4)
                self.entries[key] = entry
            self.vars[key] = var
            ttk.Label(grid, text=description, wraplength=430).grid(
                row=row, column=2, sticky="w", padx=8, pady=3
            )

        ttk.Label(
            grid,
            text=(
                "Virtual DPI scales the relative mouse counts generated by every profile. "
                "Raise it and lower in-game mouse sensitivity for finer angular steps."
            ),
            wraplength=520,
        ).grid(row=len(rows) + 1, column=0, columnspan=3, sticky="w", padx=4, pady=(8, 3))

        calibration = ttk.LabelFrame(content, text="Right-stick calibration", padding=8)
        calibration.pack(fill="x", padx=12, pady=(0, 6))
        self.calibration_button = ttk.Button(
            calibration,
            text="Calibrate center + auto-detect deadzone",
            command=self._start_calibration,
        )
        self.calibration_button.pack(side="left")
        self.calibration_var = tk.StringVar(
            value="Keep the right stick untouched during the 10-second sample."
        )
        ttk.Label(calibration, textvariable=self.calibration_var).pack(
            side="left", padx=10, fill="x", expand=True
        )
        ttk.Button(content, text="Reload from board config", command=self.refresh).pack(
            anchor="e", padx=12, pady=6
        )
        self.refresh()

    def _start_calibration(self) -> None:
        if self.app.connection is None or self.app.config is None:
            messagebox.showinfo(
                "Not connected", "Connect and verify the Pico before starting calibration."
            )
            return
        if not messagebox.askokcancel(
            "Calibrate right stick",
            "Release the right stick and do not touch it for 10 seconds.\n\n"
            "The Pico will measure its center and static jitter, then set the smallest "
            "automatic deadzone that covers that jitter.",
        ):
            return
        try:
            status = self.app.connection.start_calibration()
        except Exception as exc:
            messagebox.showerror(
                "Calibration unavailable",
                f"{exc}\n\nFlash firmware 2.0.3 or newer to use software calibration.",
            )
            return
        self.calibration_button.configure(state="disabled")
        self._show_calibration_status(status)
        self._schedule_calibration_poll()

    def _schedule_calibration_poll(self) -> None:
        if self._calibration_poll_id is not None:
            self.after_cancel(self._calibration_poll_id)
        self._calibration_poll_id = self.after(400, self._poll_calibration)

    def _poll_calibration(self) -> None:
        self._calibration_poll_id = None
        if self.app.connection is None or self.app.config is None:
            self.calibration_button.configure(state="normal")
            self.calibration_var.set("Calibration connection was closed.")
            return
        try:
            status = self.app.connection.calibration_status()
        except Exception as exc:
            self.calibration_button.configure(state="normal")
            self.calibration_var.set(f"Calibration status failed: {exc}")
            return
        self._show_calibration_status(status)
        if status.active:
            self._schedule_calibration_poll()
            return
        settings = self.app.config.settings
        settings.right_center_x = status.center_x
        settings.right_center_y = status.center_y
        settings.right_deadzone = status.deadzone
        self.vars["right_dz"].set(f"{status.deadzone:.6f}")
        self.calibration_button.configure(state="normal")
        self.calibration_var.set(
            f"Done: center {status.center_x}/{status.center_y}, "
            f"auto deadzone {status.deadzone:.6f}. Save to board to persist."
        )
        self.app.bindings_tab.refresh()
        self.app.status_var.set(
            "Right-stick center and automatic deadzone calibrated live; save to board to persist."
        )

    def _show_calibration_status(self, status) -> None:
        if status.active:
            self.calibration_var.set(
                f"Sampling... {status.remaining_ms / 1000.0:.1f}s remaining. Keep stick untouched."
            )

    def cancel_calibration_poll(self) -> None:
        if self._calibration_poll_id is not None:
            self.after_cancel(self._calibration_poll_id)
            self._calibration_poll_id = None
        self.calibration_button.configure(state="normal")

    def refresh(self) -> None:
        settings = self.app.config.settings if self.app.config else cm.Settings()
        self.vars["left_mode_1"].set(LEFT_STICK_MODE_LABELS[settings.left_stick_mode[0]])
        self.vars["left_mode_2"].set(LEFT_STICK_MODE_LABELS[settings.left_stick_mode[1]])
        self.vars["left_mode_3"].set(LEFT_STICK_MODE_LABELS[settings.left_stick_mode[2]])
        self.vars["active_profile"].set(ACTIVE_PROFILE_LABELS[settings.active_profile])
        self.vars["output_enabled"].set(OUTPUT_STATE_LABELS[settings.output_enabled])
        self.vars["tap_ms"].set(str(settings.tap_duration_ms))
        self.vars["hold_ms"].set(str(settings.hold_threshold_ms))
        self.vars["double_ms"].set(str(settings.double_click_ms))
        self.vars["turbo_hz"].set(str(settings.wheel_turbo_hz))
        self.vars["combo_hz"].set(str(settings.wheel_combo_hz))
        self.vars["grace_ms"].set(str(settings.mouse_release_grace_ms))
        self.vars["left_dz"].set(str(settings.left_deadzone))
        self.vars["right_dz"].set(str(settings.right_deadzone))
        self.vars["virtual_dpi"].set(str(settings.virtual_dpi))
        self.vars["speed_x_1"].set(str(settings.mouse_speed_x[0]))
        self.vars["speed_y_1"].set(str(settings.mouse_speed_y[0]))
        self.vars["speed_x_2"].set(str(settings.mouse_speed_x[1]))
        self.vars["speed_y_2"].set(str(settings.mouse_speed_y[1]))
        self.vars["speed_x_3"].set(str(settings.mouse_speed_x[2]))
        self.vars["speed_y_3"].set(str(settings.mouse_speed_y[2]))

    def apply_to_config(self) -> None:
        if self.app.config is None:
            return
        settings = self.app.config.settings
        settings.left_stick_mode[0] = LEFT_STICK_MODE_LABELS.index(
            str(self.vars["left_mode_1"].get())
        )
        settings.left_stick_mode[1] = LEFT_STICK_MODE_LABELS.index(
            str(self.vars["left_mode_2"].get())
        )
        settings.left_stick_mode[2] = LEFT_STICK_MODE_LABELS.index(
            str(self.vars["left_mode_3"].get())
        )
        settings.active_profile = ACTIVE_PROFILE_LABELS.index(
            str(self.vars["active_profile"].get())
        )
        settings.output_enabled = OUTPUT_STATE_LABELS.index(
            str(self.vars["output_enabled"].get())
        )
        settings.tap_duration_ms = int(self.vars["tap_ms"].get())
        settings.hold_threshold_ms = int(self.vars["hold_ms"].get())
        settings.double_click_ms = int(self.vars["double_ms"].get())
        settings.wheel_turbo_hz = int(self.vars["turbo_hz"].get())
        settings.wheel_combo_hz = int(self.vars["combo_hz"].get())
        settings.mouse_release_grace_ms = int(self.vars["grace_ms"].get())
        settings.left_deadzone = float(self.vars["left_dz"].get())
        settings.right_deadzone = float(self.vars["right_dz"].get())
        settings.virtual_dpi = int(self.vars["virtual_dpi"].get())
        settings.mouse_speed_x[0] = int(self.vars["speed_x_1"].get())
        settings.mouse_speed_y[0] = int(self.vars["speed_y_1"].get())
        settings.mouse_speed_x[1] = int(self.vars["speed_x_2"].get())
        settings.mouse_speed_y[1] = int(self.vars["speed_y_2"].get())
        settings.mouse_speed_x[2] = int(self.vars["speed_x_3"].get())
        settings.mouse_speed_y[2] = int(self.vars["speed_y_3"].get())


class FirmwareTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app: "App"):
        super().__init__(parent)
        self.app = app
        self.uf2_path: Optional[str] = None

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(frame, text="Firmware update is safe only after a board has been verified above.").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=4
        )
        ttk.Button(frame, text="Select UF2 ...", command=self._select).grid(row=1, column=0, sticky="w")
        self.file_var = tk.StringVar(value="(no UF2 selected)")
        ttk.Label(frame, textvariable=self.file_var).grid(row=1, column=1, sticky="w", padx=8)

        ttk.Button(frame, text="Verify UF2", command=self._verify).grid(row=2, column=0, sticky="w", pady=6)
        ttk.Button(frame, text="Detect bootloader drive", command=self._detect).grid(row=2, column=1, sticky="w", pady=6)

        self.log_text = tk.Text(frame, height=12, wrap="word", state="disabled")
        self.log_text.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=8)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)

        self.flash_button = ttk.Button(frame, text="Flash selected UF2", command=self._flash, state="disabled")
        self.flash_button.grid(row=4, column=0, columnspan=2, sticky="w")

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _select(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("RP2040 UF2", "*.uf2"), ("All files", "*.*")])
        if path:
            self.uf2_path = path
            self.file_var.set(path)
            self.flash_button.configure(state="normal")
            try:
                blocks, family = verify_mapper_uf2(Path(path))
                self._log(
                    f"Selected stable Pico KBM Mapper UF2: {blocks} blocks, "
                    f"family 0x{family:08X}"
                )
            except Exception as exc:
                self._log(f"UF2 validation failed: {exc}")
                self.flash_button.configure(state="disabled")


    def _verify(self) -> None:
        if not self.uf2_path:
            messagebox.showinfo("No UF2", "Select a .uf2 file first.")
            return
        try:
            blocks, family = verify_mapper_uf2(Path(self.uf2_path))
            self._log(
                f"Stable mapper UF2 OK: {blocks} blocks, family 0x{family:08X}"
            )
            self.flash_button.configure(state="normal")
        except Exception as exc:
            self._log(f"UF2 validation failed: {exc}")
            self.flash_button.configure(state="disabled")

    def _detect(self) -> None:
        drives = find_bootloader_drives()
        if not drives:
            self._log("No RPI-RP2/RP2 bootloader drive detected.")
            return
        for drive in drives:
            self._log(f"Bootloader: {drive.path} ({drive.info_text.strip()!r})")
        if len(drives) > 1:
            self._log("WARNING: multiple bootloader drives present; flashing is disabled.")
            self.flash_button.configure(state="disabled")

    def _flash(self) -> None:
        descriptor_only = (
            self.app.connection is None and self.app.descriptor_verified_port is not None
        )
        if self.app.connection is None and not descriptor_only:
            messagebox.showerror(
                "Not connected",
                "Connect and verify the board first. For the one-time update of old "
                "firmware, select a COM port whose descriptor shows Pico KBM Mapper.",
            )
            return
        if not self.uf2_path:
            return
        confirmation = (
            "Put the board into BOOTSEL mode now.\n\n"
            "The app verifies that exactly one RP2040 bootloader drive is present "
            "and that the selected file is an RP2040 UF2."
        )
        if descriptor_only:
            confirmation = (
                "The selected board is currently identified by USB descriptor only "
                "(old firmware does not speak the config protocol yet).\n\n"
                + confirmation
            )
        if not messagebox.askyesno("Confirm flash", confirmation):
            return
        try:
            flash_uf2(Path(self.uf2_path), progress=self._log)
        except Exception as exc:
            self._log(f"Flash failed: {exc}")
            messagebox.showerror("Flash failed", str(exc))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PicoController2MNK Configurator")
        self._icon_image: Optional[tk.PhotoImage] = None
        icon_png_path = bundled_resource_path("assets/icon.png")
        if icon_png_path.is_file():
            try:
                self._icon_image = tk.PhotoImage(file=str(icon_png_path))
                self.iconphoto(True, self._icon_image)
            except tk.TclError:
                self._icon_image = None
        if sys.platform == "win32":
            icon_ico_path = bundled_resource_path("assets/icon.ico")
            if icon_ico_path.is_file():
                try:
                    self.iconbitmap(default=str(icon_ico_path))
                except tk.TclError:
                    pass
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.connection: Optional[BoardConnection] = None
        self.config: Optional[cm.ConfigPayload] = None
        self.descriptor_verified_port: Optional[str] = None

        self._build_device_bar()
        self._build_tabs()
        self._build_action_bar()
        self.refresh_ports()

    def _build_device_bar(self) -> None:
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        ttk.Label(bar, text="Board").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(bar, textvariable=self.port_var, width=34, state="readonly")
        self.port_box.pack(side="left", padx=6)
        ttk.Button(bar, text="Refresh", command=self.refresh_ports).pack(side="left")
        ttk.Button(bar, text="Connect / Verify", command=self.connect).pack(side="left", padx=6)
        ttk.Button(bar, text="Disconnect", command=self.disconnect).pack(side="left")
        self.identity_var = tk.StringVar(value="Not connected.")
        ttk.Label(bar, textvariable=self.identity_var).pack(side="left", padx=12)

    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.bindings_tab = BindingsTab(self.notebook, self)
        self.macros_tab = MacrosTab(self.notebook, self)
        self.settings_tab = SettingsTab(self.notebook, self)
        self.firmware_tab = FirmwareTab(self.notebook, self)
        self.notebook.add(self.bindings_tab, text="Bindings")
        self.notebook.add(self.macros_tab, text="Macros")
        self.notebook.add(self.settings_tab, text="Settings")
        self.notebook.add(self.firmware_tab, text="Firmware")

    def _build_action_bar(self) -> None:
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x", side="bottom")
        ttk.Button(bar, text="Read from board", command=self.read_board).pack(side="left", padx=4)
        ttk.Button(bar, text="Apply live", command=self.apply_live).pack(side="left", padx=4)
        ttk.Button(bar, text="Save to board", command=self.save_board).pack(side="left", padx=4)
        ttk.Button(bar, text="Factory reset", command=self.factory_reset).pack(side="right", padx=4)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(bar, textvariable=self.status_var).pack(side="right", padx=12)

    def _port_candidate(self, port: str):
        for candidate in candidate_ports():
            if candidate.port == port:
                return candidate
        return None

    def refresh_ports(self) -> None:
        ports = candidate_ports()
        preferred = [p for p in ports if likely_mapper_port(p)]
        legacy = [p for p in ports if legacy_mapper_port(p)]
        rest = [
            p for p in ports
            if not likely_mapper_port(p) and not legacy_mapper_port(p)
        ]
        self.port_box["values"] = [p.port for p in preferred + legacy + rest]
        if not self.port_var.get() and preferred:
            self.port_var.set(preferred[0].port)
        elif not self.port_var.get() and legacy:
            self.port_var.set(legacy[0].port)
        selected = self.port_var.get()
        candidate = self._port_candidate(selected)
        self.descriptor_verified_port = (
            selected if candidate and descriptor_flash_port(candidate) else None
        )
        self.status_var.set(
            f"Found {len(ports)} serial ports, {len(preferred)} configurable mapper(s), "
            f"{len(legacy)} legacy recovery port(s)."
        )

    def connect(self) -> None:
        selected = self.port_var.get().strip()
        if not selected:
            messagebox.showwarning("No port", "Choose a COM port.")
            return

        self.refresh_ports()
        # A connection attempt must never fall through to a different board.
        # The selected port is also the identity authorization used by the
        # firmware tab, so silently substituting another likely mapper would
        # make both the UI state and the later flash confirmation misleading.
        ordered = [selected]

        last_error: Optional[Exception] = None
        last_likely_port: Optional[str] = None

        for port in ordered:
            try:
                self.disconnect()
                self.connection = BoardConnection.open(port, timeout=1.5)
                identity = self.connection.identity
                self.config = cm.decode_payload(self.connection.get_config())
                self.port_var.set(port)
                self.descriptor_verified_port = port
                self.identity_var.set(
                    f"{identity.product}  VID {identity.vid:04X} PID {identity.pid:04X}  "
                    f"serial {identity.serial}  fw {identity.firmware_major}.{identity.firmware_minor}.{identity.firmware_patch}  "
                    f"{'persisted' if identity.persisted else 'defaults'}"
                )
                self.status_var.set(f"Connected and verified {port}.")
                self.bindings_tab.refresh()
                self.macros_tab.refresh()
                self.settings_tab.refresh()
                return
            except Exception as exc:
                if self.connection is not None:
                    self.connection.close()
                self.connection = None
                self.config = None
                last_error = exc
                candidate = self._port_candidate(port)
                if candidate and descriptor_flash_port(candidate):
                    last_likely_port = port

        self.identity_var.set("Not connected.")
        self.descriptor_verified_port = last_likely_port
        detail = str(last_error or "no Pico mapper COM port responded")
        if last_likely_port is not None:
            self.status_var.set(
                f"{detail} Try Device Manager/Refresh. If the board is in BOOTSEL, "
                "remove BOOTSEL and reconnect."
            )
        else:
            self.status_var.set(f"{detail} No likely Pico mapper COM port found.")
        messagebox.showerror(
            "Connection failed",
            f"{detail}\n\nIf you just flashed: press Refresh, ensure the board is not in BOOTSEL mode, "
            "and select the COM port that appeared after reboot.",
        )

    def disconnect(self) -> None:
        if hasattr(self, "settings_tab"):
            self.settings_tab.cancel_calibration_poll()
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None
                self.config = None
                self.identity_var.set("Not connected.")

    def _require_connection(self) -> None:
        if self.connection is None or self.config is None:
            raise RuntimeError("No verified board connection.")

    def read_board(self) -> None:
        try:
            self._require_connection()
            self.config = cm.decode_payload(self.connection.get_config())
            self.bindings_tab.refresh()
            self.macros_tab.refresh()
            self.settings_tab.refresh()
            self.status_var.set("Configuration read from board.")
        except Exception as exc:
            self.status_var.set(str(exc))
            messagebox.showerror("Read failed", str(exc))

    def _collect_local_config(self) -> bytes:
        self.settings_tab.apply_to_config()
        self.macros_tab._save_selected_fields()
        self.bindings_tab.refresh()
        return cm.encode_payload(self.config)

    def apply_live(self) -> None:
        try:
            self._require_connection()
            payload = self._collect_local_config()
            self.connection.set_config(payload)
            self.status_var.set("Applied live. Board RAM now uses the edited configuration.")
        except Exception as exc:
            self.status_var.set(str(exc))
            messagebox.showerror("Apply failed", str(exc))

    def save_board(self) -> None:
        try:
            self._require_connection()
            payload = self._collect_local_config()
            self.connection.set_config(payload)
            self.connection.save_config()
            self.status_var.set("Saved to board flash. Changes survive power cycling.")
            messagebox.showinfo("Saved", "Configuration saved to board flash.")
        except Exception as exc:
            self.status_var.set(str(exc))
            messagebox.showerror("Save failed", str(exc))

    def factory_reset(self) -> None:
        if not messagebox.askyesno(
            "Factory reset",
            "Restore the original built-in mappings and macros, then save them to board flash?",
        ):
            return
        try:
            self._require_connection()
            self.connection.factory_reset()
            self.config = cm.decode_payload(self.connection.get_config())
            self.bindings_tab.refresh()
            self.macros_tab.refresh()
            self.settings_tab.refresh()
            self.status_var.set("Factory defaults restored and saved.")
        except Exception as exc:
            self.status_var.set(str(exc))
            messagebox.showerror("Factory reset failed", str(exc))


def main() -> None:
    try:
        configure_windows_app_identity()
        app = App()
        app.mainloop()
    except Exception as exc:
        messagebox.showerror("PicoController2MNK", str(exc))
        raise


if __name__ == "__main__":
    main()
