# flightsim.to page

Not published yet.

**Title:** WinCtrl MCDU Fenix A320 Patch

**Category:** Misc / Tools (MSFS 2024)

**File:** `WinCtrl-MCDU-Fenix-A320-Patch-<version>.zip`, the same zip as the GitHub release.

**Short description:** A Fenix-style screen for the WinWing (WinCtrl) MCDU: pixel font, Fenix colours, data lines aligned with the keys. Needs SimAppPro2.

## Description

A one-click setup that makes the **WinWing (WinCtrl) MCDU** screen look like the **Fenix A320** MCDU.

- **FMGC Pixel31n**: a pixel font made for the MCDU to match the Fenix font pixel for pixel. No more blobby letters.
- **Fenix colours**: amber, cyan, green, magenta and the rest, as in the Fenix web MCDU.
- **Lines aligned with the keys**: the Fenix pages are moved up so each data line sits next to its line-select key.

The font isn't the Fenix font: it was redrawn pixel by pixel on the MCDU's grid to match its look.

### ⚠️ SimAppPro2 only

This patch needs **SimAppPro2**, WinWing's newer app. It does **not** work with the original **SimAppPro** (version 1), which most MCDU owners still use. Install SimAppPro2 from WinWing's website and open it once with the MCDU plugged in before running the patch.

## Requirements

- Windows, MSFS and the Fenix A320
- WinWing MCDU, connected by USB
- SimAppPro2 (see above)
- Nothing else to install: no Python, no extra software

## Installation

This is **not** a Community folder addon: don't put it in your Community folder.

1. Unzip the download: right-click it, **Extract All…**, then **Extract**. Keep the `_internal` folder next to the `.exe`.
2. Plug in the MCDU. SimAppPro2 and the sim can stay open.
3. Double-click **`WC-MCDU-Fenix-Patch.exe`**.
   - If Windows shows *"Windows protected your PC"*, click **More info**, then **Run anyway**. The program isn't code-signed.
4. Wait about a minute. SimAppPro2 closes and reopens on its own, so leave it alone.
5. When the window says **Done: everything is in place.**, press **Enter**.

## Good to know

- **After a SimAppPro2 update, run the patch again.** The update resets the Fenix page position. Your fonts and colours stay.
- **Undo:** every run first saves your current settings in a `backups` folder next to the `.exe`. The GitHub page explains how to restore them.
- **Antivirus:** some antivirus tools flag Python-built programs as a false positive. You can allow the program, or check and run the source code from GitHub yourself.
- **What it changes:** only SimAppPro2's MCDU settings, its font folder and its Fenix MCDU scripts (SimLogic). It does **not** touch the Fenix, MSFS or your Community folder.
- Tested on MSFS 2024 with the Captain MCDU.

## Troubleshooting

If the setup stops with a message, the GitHub page has a table with the fix for each message.

## Source and issues

https://github.com/paul-charp/WC-MCDU-Fenix-Patch

Free and open source (MIT license). Not affiliated with WinWing or Fenix Simulations. Use at your own risk.

## Images (upload order)

1. `docs/perf-take-off.png` (cover)
2. `docs/f-pln.png`
3. `docs/glyphs.png`

The photos (`docs/photo-*.jpg`) stay off flightsim.to: its rules don't allow real-life images.
