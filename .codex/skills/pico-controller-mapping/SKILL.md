---
name: pico-controller-mapping
description: Project-local workflow for the PicoController2MNK repository. Use when Codex is asked to create, change, analyze, or build controller-to-keyboard/mouse mappings for this Pico firmware, including edits to main.c, data.json, CMakeLists.txt, HID report rates, button/stick masks, hold/tap behavior, combos, or UF2 build outputs.
---

# Pico Controller Mapping

## Scope

Use this skill only in the `PicoController2MNK` project. The firmware reads a controller as a USB host on GP0/GP1 and exposes USB HID keyboard/mouse plus CDC as a device.

Primary files:

- `main.c`: HID descriptors, Switch Pro parsing, mapping logic, output rate, mouse movement.
- `data.json`: captured report layout and button/stick masks.
- `CMakeLists.txt`: builds sampler and mapper UF2 targets.
- `tusb_config.h`: TinyUSB device/host settings.

Read `references/project-notes.md` when changing mappings, decoding captures, or tuning latency/rate behavior.

## Workflow

1. Inspect the current state with `rg`/`sed` before editing:
   - `rg -n "SW_BTN_|build_mapper_keycodes|send_mouse|KEYMOUSE|PICO_FIRMWARE_MAPPER" main.c CMakeLists.txt`
   - `python3 -m json.tool data.json >/dev/null` when `data.json` is involved.
2. If the user provides new Serial Monitor captures, parse `sw_btn` values:
   - Neutral is normally `0x008000`.
   - Button delta is `pressed_sw_btn ^ 0x008000` for simple captures.
   - Update `data.json` with the source path, pressed value, delta, report index, bit, and mapping note.
3. Update mapping code in `main.c`:
   - Add or adjust `SW_BTN_*` masks near the existing constants.
   - For ordinary keys, edit `build_mapper_keycodes()`.
   - For hold/tap keys, use `hold_action_t` plus `add_hold_or_tap_key()` or a small dedicated helper.
   - For modifiers such as Ctrl/Shift, return/set the HID modifier byte, not a normal keycode.
   - For mouse buttons or movement, edit `send_mouse_report_at_output_rate()`.
   - For parser state, update `process_switch_pro_report()` and legacy fallback if the new control needs `g_*` booleans.
4. Preserve the two-target build:
   - `pico_cdc_test`: sampler/debug firmware.
   - `pico_kbm_mapper`: hardware mapping firmware with `PICO_FIRMWARE_MAPPER=1`.
5. Keep latency behavior intact:
   - Do not re-enable mapper CDC status logging unless debugging.
   - Only advance report timing after a HID report is successfully queued.
   - Keep mouse integration based on actual successful send interval.
6. Build and verify:
   - `perl -0pi -e 's/\r?\n/\r\n/g' main.c CMakeLists.txt data.json` if touched files have mixed line endings.
   - `python3 -m json.tool data.json >/dev/null` if `data.json` changed.
   - `cmake --build build --parallel`
   - Confirm `build/pico_cdc_test.uf2` and `build/pico_kbm_mapper.uf2`.

## Response Notes

When finished, state the UF2 paths and summarize the mapping/rate changes briefly. Mention any hardware limit that matters, especially that RP2040 full-speed USB HID is effectively capped around 1000 host polls per second even if the internal mapper tick is higher.
