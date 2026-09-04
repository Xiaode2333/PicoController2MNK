# PicoController2MNK Runtime Configurator

PicoController2MNK stores runtime-configurable mappings in reserved flash
sectors. After the initial firmware installation, key bindings, macros,
settings, and recorded macros are changed over the existing USB CDC port. No
UF2 reflash is needed for those edits.

## One-time firmware build and flash

Build from WSL or Linux (the project already uses the Pico SDK and CMake):

```bash
git clone --recurse-submodules https://github.com/Xiaode2333/PicoController2MNK.git
cd PicoController2MNK
cmake -S . -B build
cmake --build build --target pico_kbm_mapper -j
```

From Windows Explorer you can also double-click `build_firmware.bat`, which
runs the same build through WSL.

Then use the desktop app **Firmware** tab:

1. Select the old board on its COM port. Legacy VID `0xCAFE` / PID `0x4005`
   is eligible only for this one-time descriptor-verified recovery flash; it
   cannot connect to the runtime config protocol.
2. Select `build/pico_kbm_mapper.uf2`.
3. Click Verify UF2.
4. Hold BOOTSEL and plug the board back in.
5. Click Flash selected UF2.

The app refuses to flash when no verified/recovery board is selected, when the
UF2 is not the stable `pico_kbm_mapper` RP2040 image, or when more than one RP2
bootloader drive is present. Debug and trace UF2 images are rejected.

If you prefer manual flashing, copy `build/pico_kbm_mapper.uf2` to the
`RPI-RP2` drive.

## Desktop app

Install the project and its dependencies with Poetry:

```bash
poetry install
```

Start it:

```bash
poetry run python run_configurator.py
# or
poetry run python -m tools.pico2mnk_configurator
```

Or double-click `run_configurator.bat`.

Run the desktop-side smoke tests with:

```bash
poetry run python -m unittest discover -s tests
```

If a board times out after flashing, run the COM-port probe:

```bash
poetry run python tools/pico2mnk_probe.py
```

It prints the USB serial and firmware version of every likely board. A serial
of `000001`, or a `2.0.0` board that answers PING but times out while reading
configuration, means the pre-fix firmware is still installed. Rebuild with
`build_firmware.bat` and flash the stable `pico_kbm_mapper.uf2` (`2.0.4` or
newer for Virtual DPI).

The app identifies a board by:

1. Stable USB descriptor VID `0xCAFE` / PID `0x4007` when available.
2. A CRC-protected CDC handshake (`P2MNCFG`) carrying protocol version,
   firmware version, product name, and unique board serial.

PID `0x4005` is accepted only as the explicitly documented one-time legacy
descriptor flash path. PID `0x4008` is the trace image and is never treated as
a configurable mapper. Any other COM device is never treated as a board and
is never flashed.

## Daily use

- **Bindings tab**: choose a Profile to see its complete direct bindings,
  stick/mouse rules, active combos, and all eight macros. Double-click any
  Tap/Hold/Double cell, including stick-direction rows, to replace its action.
  The lower panes provide complete combo add/edit/clear controls and a stick
  rule editor; Profile 2's RB speeds and outer-ring acceleration are editable.
- **Macros tab**: all eight slots can be renamed and assigned a trigger. Add,
  edit, delete, and reorder individual keyboard/mouse/delay steps, or press
  Record and perform the desired sequence. Press the reserved **F12** hotkey to
  stop without recording a UI click; the Stop button remains a filtered
  fallback.
- **Settings tab**: edit stick mode, thresholds, wheel rates, mouse speeds,
  virtual DPI (`100`-`20000`), and deadzones. Virtual DPI is a global
  relative-count multiplier:
  `1000` preserves legacy output, `2000` doubles all right-stick mouse counts,
  and so on. Standard USB HID does not send a DPI label to games. For smoother
  aiming at the same turn rate, raise virtual DPI and lower the matching in-game
  mouse sensitivity. **Calibrate center + auto-detect deadzone** runs the same 10-second
  center/static-jitter measurement as the Pico BOOTSEL long press, displays a
  countdown, and updates the local center/deadzone result. Use **Save to board**
  to persist it.
- **Apply live**: sends the whole config to board RAM and activates it
  immediately without touching flash.
- **Save to board**: applies live and writes the two-slot, CRC-protected
  flash config so it survives power cycling.

## Board flash config format

- Two 8192-byte slots at the end of the 2 MiB RP2040 flash.
- Each record: magic/version/schema/payload size, CRC32, save counter, then
  the 8000-byte packed config payload.
- Boot chooses the valid record with the highest save counter; if both are
  invalid, compiled defaults are used.

## Diagnostics

The `pico_kbm_mapper_trace` image still contains the old CDC status/capture
path and is intentionally not used by the config protocol. Existing
`tools/diagnose_button_flash.py` continues to work with that image.

## Repository map

- Firmware: `mapper_config.h/.c`, `mapper_store.h/.c`,
  `mapper_action.h/.c`, `mapper_protocol.h/.c`
- Desktop: `tools/pico2mnk_configurator/`
- Launchers: `run_configurator.py`, `run_configurator.bat`
