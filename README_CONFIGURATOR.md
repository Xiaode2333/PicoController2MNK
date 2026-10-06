# PicoController2MNK Runtime Configurator

This update changes the Pico firmware from hardcoded mappings to runtime
configurable mappings stored in reserved flash sectors. After the one-time
firmware update below, key bindings, macros, settings, and recorded macros are
changed over the existing USB CDC port. No UF2 reflash is needed for those
edits.

## One-time firmware build and flash

Build from WSL or Linux (the project already uses the Pico SDK and CMake):

```bash
cd /mnt/c/XiaodeDocuments/Programs/PicoController2MNK
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
`build_firmware.bat` and flash the stable `pico_kbm_mapper.uf2` (`2.2.0` or
newer for 64 Combo slots and delayed Combo actions; firmware `2.3.0` or newer
is required for **Two keys** bindings).

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
  Tap/While pressed/Hold/Double cell, including stick-direction rows, to replace
  its action. **While pressed** starts immediately; **Hold** starts after the
  global hold threshold or a custom delay of 2-65535 ms. Their default output
  stays pressed until release; the output-state selector can change this.
  These are alternative modes for one binding: editing either column opens a
  **Trigger mode** selector, and choosing one replaces the other for that input.
  Hold cells show their effective activation delay. Existing configs retain
  their original mode and delay.
  Choose **Two keys** to make one controller input hold two ordinary keyboard
  keys together. Their output state can follow input, Click, Toggle, or latch. This
  action requires firmware 2.3.0 or newer.
  The lower panes provide complete combo add/edit/clear controls and a stick
  rule editor. Every combo action has an **Activation delay (ms)**: `0`
  activates immediately, while `1`-`65535` waits that exact time before the
  selected input event/output state applies. With default Hold output, releasing
  any required input releases the output. For automatic breath-hold,
  The default automatic breath-hold Combo requires LT, does not suppress LT's
  ordinary aim output, holds Left Shift after `500` ms, and releases it with LT.
  Profile 2's **Aim / ADS input** selects the controller input held while
  aiming (for example LT). Set it under **Edit stick rules...**; the **ADS**
  speeds and outer-ring acceleration apply while that input is pressed, and
  the base/hip-fire values apply after release. Choose the same input used
  for aim in your game; this setting does not replace its ordinary binding.
  Old configurations default to RB. Choosing another Aim input requires
  firmware **2.4.0** or newer. Future Aim input changes only require
  **Apply live** or **Save to board**.
- **Macros tab**: all eight slots can be renamed and assigned a trigger. Add,
  edit, delete, and reorder keyboard, modifier, multi-key, mouse, wheel turbo,
  alternating 1/2, mouse-mode toggle/swap, and delay steps, or press Record and
  perform the desired sequence. Keyboard steps accept up to six simultaneous
  ordinary keys plus modifiers. Press the reserved **F12** hotkey to stop
  without recording a UI click; the Stop button remains a filtered fallback.
  A Macro cannot call another Macro or Snapshot Macro recursively.
- **Settings tab**: edit stick mode, thresholds, wheel rates, mouse speeds,
  virtual DPI (`100`-`20000`), and deadzones. Virtual DPI is a global relative-count multiplier:
  the factory default is `5000`, while `1000` preserves legacy output. Standard
  USB HID does not send a DPI label to games. For smoother
  aiming at the same turn rate, raise virtual DPI and lower the matching in-game
  mouse sensitivity. **Calibrate center + auto-detect deadzone** runs the same 10-second
  center/static-jitter measurement as the Pico BOOTSEL long press, displays a
  countdown, and updates the local center/deadzone result. Use **Save to board**
  to persist it.
- **Dual mouse modes**: Settings also stores two independent right-stick mouse
  modes, each with a sensitivity percentage and per-axis deadzone. In Bindings,
  assign **Toggle mouse mode + key** to any input's Tap cell (choose `Tab` for
  PUBG inventory), then assign **Swap mouse modes** to the same input's Double
  tap cell. The configurator automatically clears that input's Hold cell and
  installs the Swap action when Toggle is chosen in its Tap cell. A single tap
  alternates mode 1/2 while sending the chosen key. A
  double tap reverses the logical order without sending a key, which re-syncs
  the mouse mode if the game menu and controller state become mismatched. The
  double-click window delays the single-tap output until a second tap can be
  ruled out.
- **Apply live**: sends the whole config to board RAM and activates it
  immediately without touching flash.
- **Save to board**: applies live and writes the two-slot, CRC-protected
  flash config so it survives power cycling.
- **Export JSON / Import JSON**: saves or restores the complete local
  configuration, including all Settings, Bindings, Combos, and Macros. Import
  only updates the editor; use **Apply live** or **Save to board** afterward.
  The JSON envelope carries a format ID and version. Missing fields from older
  files receive current defaults, unknown fields in a supported version are
  ignored, and legacy bare config objects are accepted. Files declaring a
  newer unsupported format version are rejected instead of being partially
  imported and losing data.

## Input events and output states (firmware 2.5.0 / app 0.2.4)

Input and output have separate meanings. **Activation** selects immediate or
delayed recognition; **Input event** selects continuous active state, the
pressed edge, the released edge, or a short Click (release before the global
hold threshold). A short Click input requires immediate activation. Tap and
Double tap cells already select recognized gesture pulses. Stick-direction
bindings use the same rules as physical buttons; automatic WASD is a separate
continuous generator controlled by the stick settings.

For ordinary keyboard keys, modifier combinations, two keys, mouse buttons,
and wheel actions, **Output state** offers:

| State | Result |
| --- | --- |
| Hold | Maintain pressed state while input is active. A discrete input edge emits a Click. |
| Toggle | First activation latches; next activation releases. |
| Click | Press, then release after the selected duration; wheel sends one notch. |
| Pressed | Latch until a matching Released action, Stop, or runtime reset. |
| Released | Clear Pressed/Toggle latches with the same action type and keys/buttons. Other physically held outputs continue. |

Example: **LB+RB**, delay **0**, input **While active**, action **Modifier +
key: Left Alt**, optional key **none**, output **Hold** keeps Alt pressed
until LB or RB is released. An unchanged HID report does not mean a click;
the host keeps the last pressed state until a release report arrives.
Overlapping combos use slot priority (lowest slot first). Suppression cancels
ordinary participant output; changing profiles, disabling output, lost input,
and **Stop macros / release toggles** clear latches. Stop also consumes any
held input until release, preventing immediate restart.

Click duration accepts `0` for the global Tap duration, or `1`-`4095` ms.
Timers begin after the press report is accepted; rapid clicks queue up to
16 pending clicks per action and wait for a delivered release between presses.
Explicit mouse Click/Toggle release bypasses input-drop grace.

Macro slots have **Default playback**; each binding can inherit it or override
On press, On release, While held (repeat; stop immediately on release), or
Toggle (repeat until next activation). Use immediate While pressed activation
for physical press/release control. Tap/Double bindings use gesture pulse edges.
One macro plays at a time; starting another replaces it. Keyboard and mouse
steps set their device's state until its next state step or macro end. A Delay
preserves pressed keys/buttons. Use **Insert keyboard release** or **Insert
mouse release** to create clicks or repeatable sequences. Macro release does
not release other held keys, modifiers, mouse buttons, or wheel output; the
combined keyboard still supports at most six ordinary keys. Macro relative
mouse movement takes precedence over analog stick movement during playback.

New JSON exports use format version 3 to prevent old apps from silently
ignoring these behaviors. This app still imports earlier JSON configurations;
the board payload remains 8816 bytes. Writing new behaviors requires firmware
2.5.0 or newer, and the configurator checks this before applying or saving.

## Board flash config format

- Two 12288-byte slots in reserved RP2040 flash; firmware 2.1.0 also scans and
  migrates the previous two 8192-byte slots on first boot.
- Each record: magic/version/schema/payload size, CRC32, save counter, then
  the 8816-byte packed config payload containing 64 Combo slots.
- Boot chooses the valid record with the highest save counter; if both are
  invalid, compiled defaults are used.

## Diagnostics

The `pico_kbm_mapper_trace` image still contains the old CDC status/capture
path and is intentionally not used by the config protocol. Existing
`tools/diagnose_button_flash.py` continues to work with that image.

## Files added

- Firmware: `mapper_config.h/.c`, `mapper_store.h/.c`,
  `mapper_action.h/.c`, `mapper_protocol.h/.c`
- Desktop: `tools/pico2mnk_configurator/`
- Launchers: `run_configurator.py`, `run_configurator.bat`
