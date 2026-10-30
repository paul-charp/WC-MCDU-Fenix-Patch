# SimAppPro v1 port investigation

Tested against **SimAppPro 1.17.11** and
**SimLogic 1.2.60**. A settings-and-IPC backend is a viable porting path.
The experimental backend is implemented in `simapppro_v1.py`, selected with
`--simapppro 1` or the interactive app selector. Physical MCDU output is not yet
verified. V2 remains the default for commands without an explicit app version.

## Verified compatibility

- The v1 font rasterizer reproduces all **222 shipped glyphs** (111 large and
  111 small) exactly at 23 x 31, scale 1, shift 0 and thickness 1. The comparison
  uses the rasterizer's nonzero-alpha rule and the project's bitmap sources.
- All **26 Fenix MCDU workflows** use the supplied
  `CDU_Config.CDU_32NXConfig` origin. Controlled replay at Y = 37, 20, 18, 0 and
  46 produced the requested origin in **130/130 cases**, with X = 52,
  14 rows and 24 columns.
- V1 exposes the font selection, rasterization, save, apply and reset operations
  through synchronous Electron IPC. The argument fields largely match v2.
- V1 scans TTF/OTF files inside its own font-set directories at startup. The
  project's fonts can stay in the SimAppPro profile; Windows font installation
  is unnecessary.
- Live IPC successfully listed available fonts and read the active editor configuration
  and font sets. The native Windows elevation launch and the app's own exit IPC
  were exercised; the original Debug setting and normal startup were restored.
- The implemented profile preparation was exercised on a copied profile using
  the installed app's conversion, font-cache generation and global MCDU settings
  writer. All seven backend state checks passed. No hardware upload was called.

The replay executed copies of the shipped Fenix workflow bytecode under its
matching Electron runtime. Profile input, device output, WebSocket access and
LCD packet encoding were mocked. The font check executed the shipped v1
rasterizer with its PureImage 0.4.18 dependency and disabled application storage
and hardware dependencies. These checks establish conversion and workflow
behavior at those boundaries, not delivery to a physical MCDU.

## Backend differences

| Concern | V2 today | V1 port |
|---|---|---|
| Executable | `%LOCALAPPDATA%\SimAppPro2\SimAppPro2.exe` | Discover `SimAppPro.exe`; observed in `%ProgramFiles(x86)%\SimAppPro` |
| Profile root | `%APPDATA%\SimAppPro2\profile\WWTEX_profile\<id>\GameExtendDisplay` | `%APPDATA%\SimAppPro\GameExtendDisplay` |
| Editor settings | `MCDU\customer\default\default_config.json` | `MCDU\MCDU_config.json` |
| Font set | Under `MCDU\customer\default` | `MCDU\EditSpace\<set>\<set>_config.json` and `<set>.wwf` |
| TTF discovery | `Windows\Fonts` inside the profile | Immediate font-set directories under `MCDU\EditSpace` |
| API | `WWTEx_keyPress.CDU_*` RPC | `ipcRenderer.sendSync('CDU-*', args)` |
| API result | `status: 0` on success | Object with optional `data`; failures use `errMsg`, without a status field |
| Fenix origin | Existing patch changes workflow scripts | Set `CDU_Config.CDU_32NXConfig` in `%APPDATA%\SimAppPro\config.json` through the v1 apply operation |

The v1 workflow files are `.jsc` bytecode behind small `.js` loaders inside
SimLogic's ASAR. The inspected running copy was extracted to a temporary folder
by the packaged SimLogic launcher. Do not patch these transient files or port
the v2 `SIM_POINT` substitution to them: the replay verified the configuration
path directly.

## Implemented install sequence

1. Select a backend explicitly with `--simapppro 1|2`, or use the app selector
   when opening the menu. V2 is the command-line default. V1 mutations require
   the patch to run as administrator; a read-only check does not.
2. Close the selected app using the existing Windows API approach. Treat its
   SimLogic lifecycle separately: the v1 launcher checks for an existing
   `SimLogic.exe`, so closing the UI alone must not be assumed to reload it.
3. Back up the complete v1 `GameExtendDisplay\MCDU` tree and the original
   `CDU_Config.CDU_32NXConfig` value, including whether that value existed.
   Include backend identity and schema version in the backup manifest; reject
   cross-version restores.
4. Create a dedicated patch font set from the installed default schema. Copy
   the two project TTFs into that set's directory before restarting the app.
   Keep both font IDs from the MCDU default schema (observed: large 5, small 6).
   Use an empty `singleCharConfig` in the new set so previous per-glyph overrides
   cannot replace the patch's glyphs. Preserve the user's old set for restore.
5. Set editor `scX=16`, `scY=20-offset`, `matrixW=23`, `matrixH=31`, preview
   `xBase=36`, `yBase=0`, `row=14`, `col=24`, and the project's palette.
   V1's `setSimAppProConfig` adds the preview bases to the editor coordinates:
   the resulting simulator origin is **X=52, Y=20-offset**.
6. Start the selected app with a loopback CDP endpoint. From its own renderer,
   use the IPC bridge below. Initialize the MCDU config and font list, select
   the patch set, set both font slots, rasterize, save, then apply.
7. Restart normally, verify both profile representations and the generated
   `.wwf`, then verify the real MCDU with Fenix running.

The following illustrates the live-tested renderer bridge. The implementation
also normalizes successful replies to the shared transport's status convention:

```js
function callV1(method, args = {}) {
  const result = require('electron').ipcRenderer.sendSync(`CDU-${method}`, args);
  if (!result || typeof result !== 'object' || Array.isArray(result)) {
    throw new Error(`Unexpected response from CDU-${method}`);
  }
  if (result.errMsg) throw new Error(result.errMsg);
  return result;
}

callV1('changeDeviceId', {deviceId: 'MCDU'});
callV1('getConfig', {isFileSync: true});
callV1('getFontArray');
// Select the prepared set; configure its large and small slots.
// getFontConfigWithPixel -> saveFontConfigByKey -> applyFont
```

The v1 methods are `setFontSelected`, `setFontConfigByKey`,
`getFontConfigWithPixel`, `saveFontConfigByKey` and `applyFont`. Match their
argument names to the inspected handlers. Keep the rasterize-before-save/apply
ordering: selecting a TTF alone does not populate the pixel cache.

## Remaining implementation and live checks

- **Height adjustment:** the implemented v1 height action reapplies the patch
  and resends fonts, as its menu explains. A no-font-resend path remains future
  work; v1's own `applyLayout` also calls `wwfToCDU`.
- **Restart and cache behavior:** workflow setup caches `CDU_Config`. Verify
  the real profile watcher and refresh sequence, including updates while Fenix
  is connected. Do not terminate another app version's SimLogic instance by name.
- **Restore/reset:** isolated tests cover the v1 backup boundary, preservation
  of unrelated global settings, Debug cleanup and deletion of owned sets only.
  Factory reset reads the installed factory schemas, rasterizes, then applies.
  Validate both actions on hardware. The installer does not use v1's
  import/export/delete helpers, which invoke a child-shell archiver internally.
- **Physical validation:** exercise Captain and First Officer where available,
  install, offset, restore, factory reset, restart and update recovery. An IPC
  success or a cached `.wwf` file alone does not establish successful USB output.

## Implementation references

Relevant vendor source locations inside SimAppPro's ASAR:

- `mainsrc/GameExtendDisplay/CDU/CDU.js`: IPC handlers (line 233), font
  conversion (531), rasterizer (679), font discovery (765), global configuration
  writer (1385), apply-layout (1472), apply-font (1503).
- `mainsrc/GameExtendDisplay/game_config_set.js`: profile path and settings I/O.
- `main.js`: SimLogic startup (216) and window creation (275).
- SimLogic: `src_func/workflow/fnx_*/WINWING_MCDU_32-L/R.jsc`, exported
  `ScreenElLcdControl.beg` tested in controlled replay.

WINCTRL also documents fixes to its MCDU font editor in the
[official SimAppPro release notes](https://winwingsim.com/mobileview/simapppro.html).
The compatibility conclusions here are based on the inspected local builds,
not assumed to apply to every historical v1 release.
