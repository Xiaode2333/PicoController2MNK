# PicoController2MNK Project Notes

## Report Layout

Switch Pro USB HID reports currently use:

- VID/PID: `057E:2009`
- Input report IDs accepted: `0x30`, `0x21`, `0x31`
- Button word: `sw_btn = report[3] | (report[4] << 8) | (report[5] << 16)`
- Neutral button value: usually `0x008000`
- Left stick:
  - `x = report[6] | ((report[7] & 0x0F) << 8)`
  - `y = (report[7] >> 4) | (report[8] << 4)`
- Right stick:
  - `x = report[9] | ((report[10] & 0x0F) << 8)`
  - `y = (report[10] >> 4) | (report[11] << 4)`

Known button deltas:

- `SW_BTN_Y`: `0x000001`
- `SW_BTN_X`: `0x000002`
- `SW_BTN_B`: `0x000004`
- `SW_BTN_A`: `0x000008`
- `SW_BTN_RB`: `0x000040`
- `SW_BTN_RT`: `0x000080`
- `SW_BTN_MENU`: `0x000100`
- `SW_BTN_OPTION`: `0x000200`
- `SW_BTN_RSTICK`: `0x000400`
- `SW_BTN_LSTICK`: `0x000800`
- `SW_BTN_SNAPSHOT`: `0x002000`
- `SW_BTN_DPAD_DOWN`: `0x010000`
- `SW_BTN_DPAD_UP`: `0x020000`
- `SW_BTN_DPAD_RIGHT`: `0x040000`
- `SW_BTN_DPAD_LEFT`: `0x080000`
- `SW_BTN_LB`: `0x400000`
- `SW_BTN_LT`: `0x800000`

## Code Map

Important locations in `main.c`:

- User config: `PICO_FIRMWARE_MAPPER`, `MOUSE_SPEED_PX_PER_SEC`, `KEYMOUSE_REPORT_RATE_HZ`, deadzones, hold time.
- `SW_BTN_*` constants: controller button bit masks.
- `hold_action_t`: state for tap-vs-hold behaviors.
- `build_mapper_keycodes()`: keyboard mappings, modifiers, combos, and tap/hold dispatch.
- `send_mouse_report_at_output_rate()`: right-stick mouse motion and mouse buttons.
- `process_switch_pro_report()`: Switch Pro raw report parsing and state updates.
- `process_legacy_gamepad_report()`: fallback parser; keep it coherent when adding common controls.
- `main()`: USB device task loop and output scheduling.

## Runtime Profiles

The mapper firmware carries multiple profiles in one UF2:

- BOOTSEL single click: cycle profile `1 -> 2 -> 3 -> 1`.
- BOOTSEL double click: toggle mapper output on/off.
- BOOTSEL hold `2s`: start right-stick runtime center/deadzone calibration. The next `10s` of raw RX/RY samples are averaged into the mapper center; the static jitter range from the same window becomes the runtime right-stick deadzone; reboot resets to default `2048/2048` and the base deadzone.
- Profile switches and output-off transitions request neutral keyboard/mouse reports first to avoid stuck keys/buttons.
- `g_mapper_profile`, `g_mapper_output_enabled`, and `g_mapper_release_pending` hold runtime state.
- `LT+RT+Dpad up/down` are global `10Hz` wheel up/down combos and suppress the normal LT/RT plus matching Dpad output while held.

Current profile intent:

- Profile 1: baseline mapping; X tap `R`, hold `F`.
- Profile 2: alternate movement/action layout; left stick uses stable 4-way WASD with changed-only keyboard reports, not PWM/key pulsing; right-stick speed is X/Y `5000/4166` normally and `3750/2000` while RB is held; no-RB outer-ring adds up to `+4583` X speed after `0.3s`, RB outer-ring waits `0.25s` then ramps up to `+625/+625` X/Y over `1.0s`; LT is Left Ctrl, RT is Space, Dpad-down is wheel-up turbo only unless LB is held, LB+Dpad-down maps to `H`, A is `V`, B is wheel-down turbo, X tap `R`/hold `E`, Option tap `ESC`/hold `M`, Lstick+Y combo `Z`, LB+B combo Left Shift, Rstick tap alternates `1`/`2` and hold is `3`.
- Profile 3: alternate combat layout; X single-click `R`, double-click `F`, custom LT/RT behavior based on LB, LT+RT combo `X`, LB+B combo `U`.

## Mapping Patterns

Direct keyboard key:

```c
if (buttons & SW_BTN_MENU) {
    add_keycode(keycode, &count, HID_KEY_TAB);
}
```

Modifier:

```c
if (buttons & SW_BTN_LSTICK) {
    modifier |= KEYBOARD_MODIFIER_LEFTSHIFT;
}
```

Tap/hold:

```c
add_hold_or_tap_key(
    &g_hold_dpad_up,
    (buttons & SW_BTN_DPAD_UP) != 0,
    HID_KEY_5,
    HID_KEY_G,
    now_us,
    keycode,
    &count
);
```

Combo that suppresses normal button behavior:

```c
bool combo_held = (buttons & SW_BTN_LT) && (buttons & SW_BTN_RT);
bool combo_x = combo_held && (buttons & SW_BTN_X);

if (combo_x) {
    modifier |= KEYBOARD_MODIFIER_LEFTCTRL;
    add_keycode(keycode, &count, HID_KEY_1);
    reset_hold_action(&g_hold_x);
}

add_hold_or_tap_key(
    &g_hold_x,
    (buttons & SW_BTN_X) != 0 && !combo_x,
    HID_KEY_F,
    HID_KEY_R,
    now_us,
    keycode,
    &count
);
```

Mouse button:

```c
if (g_rb) {
    mouse_buttons |= MOUSE_BUTTON_LEFT;
}
```

## Latency And Rate Notes

- The mapper target uses an internal tick above 1000 Hz to check HID readiness more often, but full-speed USB HID host polling is effectively 1 ms minimum.
- Keep `USB_HID_POLL_INTERVAL_MS` at `1`.
- Keep mapper CDC status logging disabled by default with `MAPPER_ENABLE_CDC_STATUS=0`; sampler/debug can still use CDC capture.
- Mouse movement should integrate using elapsed time from the last successful report, not only the configured tick interval.
- Mouse movement dt resets after `100ms` without a successful mouse report; gamepad state release waits up to `300ms` of missing input reports so transient host report gaps do not pulse held mouse buttons.
- Held mouse buttons use a short release confirmation window, including brief `fresh=false` mapper states, so single-report controller button drops do not pulse aim/drag releases.
- Keep cross-core freshness timestamps at 32-bit `time_us_32()` width. RP2040 updates/reads 32-bit values atomically across cores; a shared 64-bit timestamp can tear and falsely expire a still-held controller input.
- The mapper exposes keyboard and mouse as separate HID interfaces/endpoints. Each endpoint is still capped by full-speed 1 ms host polling, but keyboard state changes no longer consume the mouse endpoint's ready window.
