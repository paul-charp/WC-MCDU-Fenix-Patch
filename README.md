# WC MCDU Fenix Patch

One-click setup for the **WinCtrl (WinWing) MCDU** with the **Fenix A320** in MSFS. It turns a
stock SimAppPro2 install into a screen that looks like the Fenix MCDU:

- **FMGC Pixel31m**, a pixel font custom-made for the WinCtrl MCDU to match the Fenix font at
  the pixel level,
- the Fenix colours,
- the Fenix pages moved up so each data line sits on its line-select key.

> **About the fonts.** `FMGC Pixel31m` is not the Fenix font: it was rebuilt pixel by pixel on
> the MCDU's 23 × 31 grid to match the look of the Fenix FMGC font (FlightBus, Jesper
> Giørtz-Behrens). It contains none of the original font files or outlines.

## Before / after

Pixel renders of the MCDU screen (640 × 480), decoded from the font data SimAppPro2 actually
sends to the device and placed at the origin SimLogic sends for the Fenix pages. The screen is
shown behind SimAppPro2's own MCDU bezel picture, scaled as on the real unit: with the patch,
each line-select key sits on its data line. *Before* is a stock SimAppPro2 install; *after* is
this patch. Open an image for full size.

![PERF TAKE OFF page, before and after](docs/perf-take-off.png)

![F-PLN page, before and after](docs/f-pln.png)

Glyph sheet (each square is one MCDU pixel):

![Glyph sheet, before and after](docs/glyphs.png)

## What it changes

| Item | Stock SimAppPro2 | This patch |
|---|---|---|
| Font | WinWing `WWT_MCDU` | `FMGC-Pixel31m-Large` / `-Small`: pixel font custom-made for the WinCtrl MCDU to match the Fenix font at the pixel level, scale 1.0, no shift |
| Cell size | 23 × 29 | 23 × 31 |
| Editor grid | X 16, Y 17, preview yBase 20 | X 16, Y 20, preview yBase 0 (the editor's test grid matches what the sim shows) |
| Fenix page position | X 52, Y 37 (hard-coded in the SimLogic Fenix scripts) | X 52, Y 20 |
| Colours | SimAppPro2 defaults | Fenix web MCDU colours (written explicitly so a changed palette is put back) |

Fenix web MCDU colours: amber `#FFA500`, white `#FFFFFF`, cyan `#00FFFF`, green `#00FF3D`,
magenta `#FF63FF`, red `#FF0000`, yellow `#FFFF00`.

## Requirements

- Windows, MSFS with the Fenix A320, WinWing MCDU
- SimAppPro2 installed and started at least once with the MCDU plugged in
- The MCDU plugged in while the setup runs (it waits up to 3 minutes for it if not)
- Nothing else for the `.exe`. To run the script instead: Python 3 on `PATH`; its first run
  installs the Python packages `rich` and `websocket-client` (`pip install --user`).

## Install

Download `WC-MCDU-Fenix-Patch-<version>.zip` from the repository's **Releases** page (or build
it, see below), unzip it anywhere and double-click **`WC-MCDU-Fenix-Patch.exe`** in the unzipped
folder; keep its `_internal` folder next to it. It takes under a minute, closes SimAppPro2 while
it works, and waits for Enter before closing its window. Backups go to a `backups\` folder next
to the `.exe`.

The `.exe` is not signed: the first time, Windows SmartScreen may show "Windows protected your PC".
Click **More info → Run anyway**.

Without the `.exe`: double-click **`installer.bat`**, or run `python setup_mcdu.py`. Both take the
same arguments as the `.exe`.

```
╭─ WinWing MCDU · Fenix A320 · setup ─────────────────────────╮
│  MCDU        connected (Captain)                            │
│  Fonts       FMGC-Pixel31m-Large / FMGC-Pixel31m-Small      │
│  Grid        X 16  Y 20  23x31 cells                        │
│  Colours     Fenix web MCDU                                 │
│  SimAppPro2  will be closed and restarted (under a minute)  │
╰─────────────────────────────────────────────────────────────╯

  ✔ Close SimAppPro2               closed  6s
  ✔ Back up current settings       backups\20261015-215323
  ✔ Install fonts                  FMGC-Pixel31m-Large / FMGC-Pixel31m-Small
  ✔ Fenix page position            Y 20 in 26 scripts
  ✔ Grid and colours               X 16  Y 20  23x31, Fenix colours
  ✔ Send fonts to the MCDU         font set WWT_MCDU  21s
  ✔ Restart SimAppPro2             running normally  5s

Check
   ✔  Fonts installed         FMGC-Pixel31m-Large / FMGC-Pixel31m-Small
   ✔  Fonts selected          set WWT_MCDU, scale 1, no shift
   ✔  Font sent to MCDU       23x31 cells
   ✔  Grid                    X 16  Y 20  23x31  yBase 0
   ✔  Colours                 Fenix
   ✔  Fenix pages (SimLogic)  Y 20 in all 26 scripts

╭─────────────────────────────────╮
│  Done: everything is in place.  │
╰─────────────────────────────────╯
```

The steps:

0. Check that a WinWing MCDU is on USB (vendor `4098`, Captain / First Officer / Observer ids);
   if not, ask to plug it in and start as soon as it is detected.
1. Close SimAppPro2.
2. Back up the MCDU settings and the SimLogic Fenix scripts to `backups\<date-time>\`.
3. Copy the fonts into SimAppPro2's own font folder (`GameExtendDisplay\Windows\Fonts`).
4. Set the Y position in the 26 SimLogic Fenix MCDU scripts (`fnx_*\WINWING_MCDU_32-L/R.js`).
5. Write the grid and colours to the MCDU settings and the selected font set.
6. Restart SimAppPro2 with a local debug port and call its own functions to select the fonts,
   convert them and send them to the MCDU.
7. Restart SimAppPro2 normally and print the check table.

If anything fails, SimAppPro2 is still restarted normally and the previous files stay in `backups\`.

## Commands

Same arguments for `WC-MCDU-Fenix-Patch.exe`, `installer.bat` and `python setup_mcdu.py`:

```
python setup_mcdu.py                                  install / re-apply everything
python setup_mcdu.py --check                          check without changing anything (✘ = needs fixing)
python setup_mcdu.py --y 18                           install with another vertical position
python setup_mcdu.py --restore backups\20261015-215323   put a backup back (then press Apply)
```

When using `--y`, pass the same value to `--check`.

## After a SimAppPro2 update

**Run the `.exe` (or `installer.bat`) again.** Updates replace the SimLogic scripts, so the
Fenix pages go back to Y 37. `WC-MCDU-Fenix-Patch.exe --check` shows whether it is needed.

## Troubleshooting

| Message | Fix |
|---|---|
| `Connect the MCDU` / `No WinWing MCDU found on USB` | Plug the MCDU in (any USB port). The setup continues by itself once Windows sees it. |
| `SimAppPro2 MCDU profile not found` | Start SimAppPro2 once with the MCDU plugged in, then run again. |
| `SimAppPro2 did not create its MCDU settings` | Open the MCDU screen settings page once in SimAppPro2, close it, run again. |
| `SimAppPro2 does not list FMGC-Pixel31m-…` | SimAppPro2 reads its font list at startup: restart it, run again. |
| `Unexpected format in fnx_…` | A SimAppPro2 update changed the scripts; that file was left untouched. The pattern to update is `SIM_POINT` in `setup_mcdu.py`. |
| `SimAppPro2 did not open its debug port` | Something else is using port 9333, or SimAppPro2 failed to start. Close SimAppPro2 and run again. |

To go back to the state before a run: `python setup_mcdu.py --restore backups\<date-time>`,
then press **Apply** on the MCDU font page in SimAppPro2.

## Why this is needed

- The WinWing MCDU is a **640 × 480** text-mode screen: it receives characters and draws the
  glyphs itself from a 1-bit font stored in its memory (`.wwf`).
- SimAppPro2 converts the selected TrueType font by lighting every pixel the outline **touches**,
  even by 1 %, which makes letters blobby. The `Pixel31m` fonts are drawn pixel by pixel so its
  conversion gives back exactly the intended design (verified: 111/111 glyphs per size).
- The text position sent to the MCDU comes from two places: the editor (X/Y/yBase settings)
  **and** SimLogic, which after every Apply re-sends its own position, hard-coded in the Fenix
  scripts (`'XAisPoint':0x34,'YAxisPoint':0x25` = 52, 37). That is why SimAppPro2's X/Y settings
  have no effect on the Fenix pages.
- The line-select keys are 69.5 px apart on the real screen; with 14 lines they cannot all be
  aligned perfectly. Y = 20 was tuned by eye on the real MCDU.

## Repository layout

```
setup_mcdu.py            install / check / restore
installer.bat            runs setup_mcdu.py with the installed Python
build_exe.py             builds dist/WC-MCDU-Fenix-Patch/ and its .zip
icon/                    the .exe icon and make_icon.py, which draws it
.github/workflows/       CI: builds the .zip, publishes releases from version tags
fonts/                   FMGC-Pixel31m-Large.ttf, FMGC-Pixel31m-Small.ttf
docs/                    README screenshots and render_screens.py
backups/                 created by each run (git-ignored)
dist/                    the built .exe folder and .zip (git-ignored)
```

## Building the .exe

```
python build_exe.py            local build, version 0.0.0
python build_exe.py 1.2.0      version 1.2.0
```

Produces `dist\WC-MCDU-Fenix-Patch\` (`WC-MCDU-Fenix-Patch.exe` and its `_internal` folder,
about 25 MB) and `dist\WC-MCDU-Fenix-Patch-<version>.zip` (about 12 MB): a PyInstaller one-folder build
holding Python, `rich`, `websocket-client` and the two fonts from `fonts\`, with Windows version
info. It installs PyInstaller, `rich` and `websocket-client` with `pip --user` if they are
missing. The `dist\` output is git-ignored; releases are built by CI (see below).

It is a one-folder build because Windows Defender's machine-learning heuristics flagged the
one-file version (a self-extracting `.exe`) as `Trojan:Win32/Bearfoos.B!ml`, a false positive.
For the same reason the script calls Windows directly (ctypes) instead of running PowerShell.

## Releases

GitHub Actions (`.github/workflows/build.yml`) builds the zip on Windows for every push to `main`
and every pull request; it is attached to the run as an artifact. Pushing a version tag also
publishes a release with `WC-MCDU-Fenix-Patch-<version>.zip`, the tag message as its notes:

```
git tag -a v1.2.0 -m "- what changed"
git push origin v1.2.0
```

## Updating the screenshots

```
python docs/render_screens.py
```

It reads SimAppPro2's factory WinWing font for *before*, the font set currently sent to the MCDU
for *after*, and the bezel picture from SimAppPro2's UI assets, so run it on a machine where this
setup is installed. Needs Pillow.

## Updating the fonts

For a new version, change the font name (e.g. `Pixel31n`): SimAppPro2 only reads its fonts at
startup and caches the old name. Replace both files in `fonts/` (a single `*-Large.ttf` /
`*-Small.ttf` pair), then rebuild the `.exe`. If the cell size changes, the fonts must be
redrawn for the new grid and `LAYOUT` in `setup_mcdu.py` updated.
