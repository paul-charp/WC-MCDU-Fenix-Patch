# Changelog

## v1.2.1 (2026-10-30)

- Full install no longer stops with "SimAppPro2 refused to select, convert, save or send the fonts" when SimAppPro2 has no MCDU font set yet: the set is created
- Troubleshooting entry for this message

## v1.2.0 (2026-10-18)

- Start menu: Check only, Full install, Height adjust, Reset
- Height adjust: type an offset (0 = default, positive = text up, negative = down), shown live on the MCDU; kept by later installs
- Reset: WinWing factory settings, or put a backup back (sent to the MCDU)
- Command-line options --install, --offset and --factory-reset; --offset replaces --y
- Release zip renamed WinCtrl-MCDU-Fenix-A320-Patch-<version>.zip
- Fonts under the MIT license; font source added as text bitmaps (fonts/src)

## v1.1.0 (2026-10-17)

FMGC Pixel31n font

- Square bar ends on large E, F, L, 2 and on = (large and small)
- Large 1 moved 1 px left, so digits sit evenly
- Large and small C: lower terminal matches the upper one

## v1.0.1 (2026-10-17)

- Clear message when SimAppPro2 is missing: this setup needs SimAppPro2, not the original SimAppPro (version 1)
- README: step-by-step install instructions, links to the latest release

## v1.0.0 (2026-10-17)

First release.

- FMGC Pixel31m: pixel fonts (large and small) made for the WinWing MCDU to match the Fenix font
- Fenix pages at Y 20 (SimLogic scripts), grid X 16 Y 20 23x31, Fenix web MCDU colours
- Standalone WC-MCDU-Fenix-Patch.exe (one-folder build): install, --check, --y, --restore
- Waits for the MCDU on USB; backs up settings and scripts on every run
