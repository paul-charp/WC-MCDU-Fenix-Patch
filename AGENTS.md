# Agent notes

One-click setup that makes the WinWing (WinCtrl) MCDU show Fenix A320 pages like the Fenix MCDU:
pixel fonts, Fenix colours, pages moved so data lines sit on the line-select keys. It configures
SimAppPro2 only (never SimAppPro v1, never Fenix or MSFS files). Windows only. User docs:
[README.md](README.md).

## Layout

- `setup_mcdu.py`: the whole setup (install, `--check`, `--y N`, `--restore`). Python 3, `rich` +
  `websocket-client`; runs as the PyInstaller `.exe` too (`FROZEN` / `BUNDLED` paths).
- `fonts/*.ttf`: the shipped pair (exactly one `*-Large.ttf` and one `*-Small.ttf`).
  `fonts/src/*.txt` is their source (23x31 `#`/`.` bitmaps); `fonts/make_ttf.py` builds them,
  `--check` verifies them (CI runs it). Needs fontTools.
- `build_exe.py [X.Y.Z]`: one-folder PyInstaller build + version info, zipped as
  `dist/WinCtrl-MCDU-Fenix-A320-Patch-<version>.zip`.
- `docs/render_screens.py`: README before/after renders (needs SimAppPro2 installed with the
  patch, and Pillow). `docs/flightsim-to.md`: flightsim.to page text.
- `.github/workflows/build.yml`: builds the zip on every push; a pushed `vX.Y.Z` tag publishes a
  release with the tag message as notes.
- `.local/` (git-ignored): private research, third-party fonts, the original font pipeline, old
  backups. See `.local/README.md`. Put new private files there.

## Rules

- Never commit third-party files: Fenix, WinWing/SimAppPro2, SimLogic scripts, McDoo or other
  fonts. Everything from `.local/` stays local.
- README and other tracked files don't mention `.local/` content or the original font pipeline.
- Edit glyphs in `fonts/src/*.txt`, never by rasterising other fonts. Any visible font change
  needs a new font name (`Pixel31n` → `Pixel31o`: rename both `.txt` files and their `family:`
  line, rebuild, delete the old `.ttf` files): SimAppPro2 caches fonts by name.
- Fonts are MIT like the rest (name-table copyright set in the `.txt` headers, `fsType: 0`).
- No PowerShell or other child shells in `setup_mcdu.py`: use ctypes (cfgmgr32, Toolhelp,
  WM_CLOSE). A PowerShell-calling one-file build was flagged by Defender as a trojan.
- Changelogs and tag messages list what changed, not why.

## SimAppPro2 gotchas

- SimLogic's Fenix scripts (`fnx_*/WINWING_MCDU_32-L/R.js`) hard-code the text origin
  (`'XAisPoint':0x34,'YAxisPoint':0x25`); the editor's X/Y never reach Fenix pages. The patch sets
  Y in all 26 scripts (`SIM_POINT`). A SimAppPro2 update restores them.
- The API is reached through Chrome DevTools on port 9333 (SimAppPro2 started with
  `--remote-debugging-port`), as `WWTEx_keyPress.CDU_*` RPC calls. Never return the RPC proxy
  from an async function; wrap it.
- `CDU_setFontConfigByKey` only records a font. Call `CDU_getFontConfigWithPixel` before
  `CDU_saveFontConfigByKey` / `CDU_applyFont`, or the previous font's cached pixels are sent.
- For a few seconds after start the back end answers "The peer 17 is not online": wait for
  `CDU_getPcFontArray` to succeed (`App.wait_ready`).
- SimAppPro2 reads its font list (`GameExtendDisplay/Windows/Fonts`) at startup only.
- Start SimAppPro2 with stdio on DEVNULL, cwd = its install folder, and (frozen) after
  `SetDllDirectoryW(None)`, or it floods the console, drops logs in the cwd, or loads the
  bundle's DLLs.

## Testing

- `python setup_mcdu.py --check`: read-only state check.
- Full install: `python setup_mcdu.py` with the MCDU plugged in (about a minute; closes and
  restarts SimAppPro2). Confirm on the real MCDU with the Fenix running.
- `python fonts/make_ttf.py --check` after any font edit; `python build_exe.py` then
  `dist\WC-MCDU-Fenix-Patch\WC-MCDU-Fenix-Patch.exe --check` for the frozen build.
