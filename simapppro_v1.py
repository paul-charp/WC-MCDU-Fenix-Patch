"""Experimental SimAppPro 1 backend. Uses its own profile and Electron IPC.

The shared console, USB detection and CDP transport live in setup_mcdu.py.
No vendor files or compiled SimLogic workflows are bundled or rewritten.
"""
import copy
import datetime
import json
import os
import shutil
from pathlib import Path
from urllib.parse import unquote


# Present the v1 synchronous API in the same shape as the v2 RPC API. In v1 an
# empty object is a valid success; undefined and errMsg must never become success.
IPC_API = """(() => {
  const ipc = require('electron').ipcRenderer;
  const methods = ['changeDeviceId', 'getConfig', 'setConfig', 'getFontArray',
    'getPcFontArray', 'setFontSelected', 'setFontConfigByKey',
    'getFontConfigWithPixel', 'saveFontConfigByKey', 'applyFont',
    'resetLayout', 'resetFont', 'resetColor'];
  const api = {};
  for (const method of methods) api['CDU_' + method] = (args = {}) => {
    const r = ipc.sendSync('CDU-' + method, args);
    if (!r || typeof r !== 'object' || Array.isArray(r))
      throw new Error('Unexpected response from CDU-' + method);
    if (r.errMsg) throw new Error('CDU-' + method + ': ' + r.errMsg);
    return {...r, status: 0};
  };
  return {k: api};
})()"""


def discover_exe():
    candidates = []
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
                try:
                    with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\App Paths\SimAppPro.exe",
                                        0, winreg.KEY_READ | view) as key:
                        candidates.append(winreg.QueryValue(key, None))
                except OSError:
                    pass
    except ImportError:
        pass
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        if os.environ.get(env):
            candidates.append(os.path.join(os.environ[env], "SimAppPro", "SimAppPro.exe"))
    return next((p for p in candidates if os.path.isfile(p)), None)


def linked(path):
    """Recognize Windows reparse points, including junctions on older Python 3."""
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False


class Backend:
    name = "SimAppPro v1"
    key = "CDU_32NXConfig"

    def __init__(self, shared, exe=None, root=None):
        self.s = shared
        self.exe = os.path.abspath(exe or discover_exe() or "SimAppPro.exe")
        self.root = Path(root or os.path.join(os.environ["APPDATA"], "SimAppPro"))
        self.mcdu = self.root / "GameExtendDisplay" / "MCDU"
        self.config = self.mcdu / "MCDU_config.json"
        self.global_config = self.root / "config.json"
        self.backup_root = Path(self.s.HERE) / "backups" / "simapppro-v1"
        self.session_file = self.backup_root / "setup-session.json"
        self.factory = Path(self.exe).parent / "resources" / "app.asar.unpacked" / "config" / "GameExtendDisplay" / "MCDU"
        self.large, self.small = self.s.font_files()
        self.set_name = self.s.font_name(self.large)[:-len("-Large")]

    def load(self, path):
        return self.s.load_json(str(path))

    def save(self, path, value):
        # Replace atomically: interrupted writes must not leave truncated app JSON.
        path = Path(path)
        temp = path.with_name(path.name + ".mcdu-tmp")
        try:
            self.s.save_json(str(temp), value)
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()

    def set_dir(self, name, base=None):
        if not isinstance(name, str) or not name or name in (".", "..") or any(c in name for c in '/\\:\0'):
            raise self.s.SetupError("Invalid MCDU font-set name in the settings.")
        base = Path(base or self.mcdu) / "EditSpace"
        folder = base / name
        if os.path.commonpath([str(base.resolve()), str(folder.resolve())]) != str(base.resolve()):
            raise self.s.SetupError("The font set points outside the MCDU settings folder.")
        return folder

    def selected(self, base=None):
        base = Path(base or self.mcdu)
        name = self.load(base / "MCDU_config.json")["fontConfig"]["fontSelected"]
        folder = self.set_dir(name, base)
        return name, folder / f"{name}_config.json", folder / f"{name}.wwf"

    def preflight(self):
        if os.path.basename(self.exe).lower() != "simapppro.exe" or not os.path.isfile(self.exe):
            raise self.s.SetupError("SimAppPro v1 not found. Use --simapppro 1 --app-path \"C:\\path\\SimAppPro.exe\".")
        try:
            if linked(self.mcdu):
                raise ValueError("Linked profile")
            cfg = self.load(self.config)
            if not isinstance(self.load(self.global_config).get("CDU_Config", {}), dict):
                raise ValueError("Invalid global configuration")
            for key in ("scX", "scY", "matrixW", "matrixH"):
                cfg["layoutConfig"][key]
            for key in ("xBase", "yBase", "row", "col", "charArray"):
                cfg["previewConfig"][key]
            cfg["colorConfig"]["colorArray"]
            _, font, _ = self.selected()
            self.validate_font(self.load(font))
            stock = self.set_dir("WWT_MCDU") / "WWT_MCDU_config.json"
            self.validate_font(self.load(stock))
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise self.s.SetupError("SimAppPro v1 MCDU settings are missing or incompatible. Open its MCDU "
                                    "screen settings once with the device connected, then try again.") from e

    @staticmethod
    def validate_font(font):
        for key in ("largeFontConfig", "smallFontConfig"):
            if not isinstance(font[key]["fontId"], int):
                raise ValueError("Invalid font ID")
        if not isinstance(font["pixelConfig"], dict) or not isinstance(font["singleCharConfig"], dict):
            raise ValueError("Invalid font configuration")

    def chosen_y(self, y=None):
        cfg = self.load(self.config)
        if y is None:
            y = (cfg["layoutConfig"]["scY"] if cfg["layoutConfig"]["matrixH"] == 31 and
                 cfg["previewConfig"]["yBase"] == 0 else self.s.DEFAULT_Y)
        if type(y) is not int or not self.s.Y_RANGE[0] <= y <= self.s.Y_RANGE[1]:
            raise self.s.SetupError("The saved height is outside the MCDU screen. Supply --offset 0 to reset it.")
        return y

    def scope(self):
        cfg = self.load(self.global_config)
        cdu = cfg.get("CDU_Config", {})
        return {"container_present": "CDU_Config" in cfg, "present": self.key in cdu,
                "value": copy.deepcopy(cdu.get(self.key))}

    def restore_scope(self, scope):
        cfg = self.load(self.global_config)
        cdu = cfg.setdefault("CDU_Config", {})
        if scope["present"]:
            cdu[self.key] = scope["value"]
        else:
            cdu.pop(self.key, None)
        if not scope["container_present"] and not cdu:
            cfg.pop("CDU_Config")
        self.save(self.global_config, cfg)

    def backup(self):
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        dest = self.backup_root / stamp
        dest.mkdir(parents=True)
        shutil.copytree(self.mcdu, dest / "MCDU")
        self.save(dest / "manifest.json", {"schema": 1, "backend": "simapppro-v1", "scope": self.scope()})
        return str(dest)

    def validate_backup(self, src):
        src = Path(src)
        if not src.is_absolute():
            src = Path(self.s.HERE) / src
        try:
            if linked(src) or linked(src / "MCDU"):
                raise ValueError("Linked backup")
            manifest = self.load(src / "manifest.json")
            if manifest.get("schema") != 1 or manifest.get("backend") != "simapppro-v1":
                raise ValueError("Wrong backend")
            scope = manifest["scope"]
            if type(scope["present"]) is not bool or type(scope["container_present"]) is not bool:
                raise ValueError("Invalid scope")
            if scope["present"] and not isinstance(scope["value"], dict):
                raise ValueError("Invalid scope value")
            _, cfg, _ = self.selected(src / "MCDU")
            self.validate_font(self.load(cfg))
            # Never follow links from an edited backup while replacing app settings.
            if any(linked(p) for p in (src / "MCDU").rglob("*")):
                raise ValueError("Linked backup files")
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise self.s.SetupError("This is not a complete SimAppPro v1 backup. V2 backups cannot be restored to v1.") from e
        return src, manifest

    def put_back(self, src):
        # Stage first so a copy failure leaves current settings intact.
        stage = self.mcdu.with_name("MCDU.mcdu-restore")
        previous = self.mcdu.with_name("MCDU.mcdu-previous")
        if stage.exists() or previous.exists() or linked(self.mcdu):
            raise self.s.SetupError("An unfinished MCDU restore or linked profile needs checking before restore.")
        shutil.copytree(src / "MCDU", stage)
        os.replace(self.mcdu, previous)
        try:
            os.replace(stage, self.mcdu)
        except BaseException:
            os.replace(previous, self.mcdu)
            raise
        shutil.rmtree(previous)

    def enable_debug(self):
        if self.session_file.exists():
            raise self.s.SetupError("A previous v1 setup did not finish. Run the same command again after closing SimAppPro.")
        cfg = self.load(self.global_config)
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.save(self.session_file, {"root": str(self.root.resolve()), "present": "Debug" in cfg,
                                      "value": cfg.get("Debug")})
        cfg["Debug"] = True
        self.save(self.global_config, cfg)

    def restore_debug(self):
        if not self.session_file.exists():
            return
        state = self.load(self.session_file)
        if state["root"] != str(self.root.resolve()):
            raise self.s.SetupError("The unfinished v1 setup belongs to a different profile.")
        cfg = self.load(self.global_config)
        if state["present"]:
            cfg["Debug"] = state["value"]
        else:
            cfg.pop("Debug", None)
        self.save(self.global_config, cfg)
        self.session_file.unlink()

    def page_matches(self, page):
        expected = (Path(self.exe).parent / "resources" / "app.asar").as_posix().lower() + "/"
        url = unquote(page.get("url", "")).replace("\\", "/").lower()
        return url.startswith("file:///") and url[8:].startswith(expected)

    def stop(self):
        self.s.stop_app(exe=self.exe)

    def start(self, debug=False, tick=None):
        self.s.start_app(debug=debug, tick=tick, exe=self.exe, page_match=self.page_matches)

    def prepare_patch(self, y):
        folder = self.set_dir(self.set_name)
        marker = folder / "mcdu-patch.json"
        if folder.exists() and (not marker.exists() or self.load(marker).get("backend") != "simapppro-v1"):
            raise self.s.SetupError(f"The font set {self.set_name} already exists and is not owned by this patch.")
        stock = self.load(self.set_dir("WWT_MCDU") / "WWT_MCDU_config.json")
        stock.update(fontName=self.set_name, newFontName=self.set_name, fontFilePath=str(folder),
                     fontOperation=True, isDelete=False, singleCharConfig={})
        stock["pixelConfig"].update(self.s.LAYOUT, scY=y, pixelArrayInSizeChar={})
        for key, font in (("largeFontConfig", self.large), ("smallFontConfig", self.small)):
            stock[key].update(self.s.FONT_SLOT, pcFontSelected=self.s.font_name(font), thickness=1,
                              missCharArray=[], color="white")
        folder.mkdir(parents=True, exist_ok=True)
        for font in (self.large, self.small):
            shutil.copy2(font, folder)
        self.save(folder / f"{self.set_name}_config.json", stock)
        self.save(marker, {"backend": "simapppro-v1", "schema": 1})
        cfg = self.load(self.config)
        cfg["fontConfig"]["fontSelected"] = self.set_name
        cfg["layoutConfig"].update(self.s.LAYOUT, scY=y)
        cfg["previewConfig"].update(xBase=36, yBase=0, row=14, col=24)
        for color in cfg["colorConfig"]["colorArray"]:
            if color["colorName"] in self.s.FENIX_COLOURS:
                color["currentColor"] = self.s.FENIX_COLOURS[color["colorName"]]
        self.save(self.config, cfg)

    def send(self, app, raster=True):
        result = app.call("""
          const c = await api.CDU_getConfig({isFileSync: true});
          await api.CDU_getFontArray();
          const fontName = c.data.fontConfig.fontSelected;
          %s
          const saved = await api.CDU_saveFontConfigByKey({fontName});
          const applied = await api.CDU_applyFont();
          return [saved.status, applied.status];
        """ % ("await api.CDU_getFontConfigWithPixel({fontName, isFileSync: true});" if raster else ""))
        if result != [0, 0]:
            raise self.s.SetupError(f"SimAppPro v1 did not save and apply the font (codes {result}).")

    def reset(self, app):
        # Read factory schemas through the app's JS loader; never ship vendor data.
        defaults = app.call("return [require(%s), require(%s)];" % (
            json.dumps(str(self.factory / "MCDU.js")),
            json.dumps(str(self.factory / "EditSpace" / "WWT_MCDU" / "WWT_MCDU.js"))))
        if not isinstance(defaults, list) or len(defaults) != 2:
            raise self.s.SetupError("SimAppPro v1 factory settings could not be read.")
        cfg, font = defaults
        self.validate_font(font)
        if cfg.get("fontConfig", {}).get("fontSelected") != "WWT_MCDU":
            raise self.s.SetupError("Unexpected SimAppPro v1 factory font.")
        folder = self.set_dir("WWT_MCDU")
        font["fontFilePath"] = str(folder)
        self.save(folder / "WWT_MCDU_config.json", font)
        self.save(self.config, cfg)
        self.send(app)

    def remove_patch_sets(self):
        for marker in (self.mcdu / "EditSpace").glob("*/mcdu-patch.json"):
            if self.load(marker) == {"backend": "simapppro-v1", "schema": 1}:
                folder = self.set_dir(marker.parent.name)
                shutil.rmtree(folder)

    def check(self, y=None):
        y = self.chosen_y(y)
        cfg = self.load(self.config)
        name, font_path, wwf = self.selected()
        font = self.load(font_path)
        folder = font_path.parent
        names = [self.s.font_name(f) for f in (self.large, self.small)]
        slots = [font[k] for k in ("largeFontConfig", "smallFontConfig")]
        plain = all(all(slot.get(k) == v for k, v in dict(self.s.FONT_SLOT, thickness=1).items()) for slot in slots)
        selected = [slot["pcFontSelected"] for slot in slots] == names and plain and not font["singleCharConfig"]
        grid = all(cfg["layoutConfig"].get(k) == v for k, v in dict(self.s.LAYOUT, scY=y).items())
        grid = grid and all(cfg["previewConfig"].get(k) == v for k, v in dict(xBase=36, yBase=0, row=14, col=24).items())
        colors = {c["colorName"]: c["currentColor"].upper() for c in cfg["colorConfig"]["colorArray"]}
        scope = self.scope()["value"] or {}
        position = all(scope.get(k) == v for k, v in dict(XAisPoint=52, YAxisPoint=y, line=14, column=24,
                                                       fontWidth=23, fontHeight=31).items())
        cache_ok = False
        if wwf.exists():
            cached = self.load(wwf)
            cache_ok = all(all(cached[k]["headConfig"].get(field) == val for field, val in
                               dict(matrixW=23, matrixH=31, id=slot["fontId"]).items()) and
                           bool(cached[k].get("pixelUint8Array"))
                           for k, slot in zip(("largeFontConfig", "smallFontConfig"), slots))
        return [(all((folder / (n + ".ttf")).is_file() for n in names), "Fonts installed", " / ".join(names)),
                (selected, "Fonts selected", f"set {name}, scale 1, no shift" if selected else f"set {name}"),
                (cache_ok, "Font cache", "23x31 cells; USB delivery needs the real MCDU" if cache_ok else "not generated for the patch"),
                (grid, "Grid", f"X 16  Y {y}  23x31, preview base 36/0" if grid else "layout differs"),
                (all(colors.get(k) == v for k, v in self.s.FENIX_COLOURS.items()), "Colours", "Fenix palette"),
                (position, "Fenix page position", f"X {scope.get('XAisPoint')}  Y {scope.get('YAxisPoint')}"),
                (not self.session_file.exists(), "Setup mode", "unfinished session needs recovery" if self.session_file.exists() else "normal")]

    def mutate(self, ui, action, y=None, src=None):
        restore = self.validate_backup(src) if action == "restore" else None
        if not self.s.is_admin():
            raise self.s.SetupError("SimAppPro v1 requires administrator access for restart and upload. "
                                    "Right-click the patch executable and choose Run as administrator, "
                                    "or run the source command in an administrator terminal.")
        if self.s.app_pids("SimAppPro2.exe"):
            raise self.s.SetupError("Close SimAppPro2 before configuring the MCDU in SimAppPro v1.")
        self.s.wait_for_mcdu(ui)
        ui.header(f"WinWing MCDU · Fenix A320 · {action}",
                  [("App", f"{self.name} (experimental)"), ("Settings", str(self.config)),
                   ("Height", self.s.fmt_offset(y) if y is not None else "restored/default")])
        app = None
        stopped = False
        restored = False
        uploaded = False
        with ui.steps([("Close SimAppPro v1", 6), ("Back up current settings", 3),
                       ("Prepare settings", 4), ("Send to the MCDU", 70), ("Restart SimAppPro v1", 8)]) as steps:
            try:
                steps.run(self.stop)
                stopped = True
                self.restore_debug()  # recover a previous interrupted setup before changing anything
                steps.run(self.backup)

                def prepare():
                    nonlocal restored
                    if action == "install":
                        self.prepare_patch(y)
                    elif restore:
                        self.put_back(restore[0])
                        self.restore_scope(restore[1]["scope"])
                        restored = True
                    self.enable_debug()

                steps.run(prepare)

                def upload(tick):
                    nonlocal app
                    self.start(debug=True, tick=tick)
                    app = self.s.App(api=IPC_API, name=self.name, page_match=self.page_matches)
                    fonts = app.wait_ready()
                    if action == "install" and any(self.s.font_name(f) not in fonts for f in (self.large, self.small)):
                        raise self.s.SetupError("SimAppPro v1 did not list the patch fonts after restart.")
                    if action == "reset":
                        self.reset(app)
                    else:
                        self.send(app, raster=not restore or self.can_raster())
                    self.s.wait(10, tick, 0.8, 1.0, "waiting for Fenix pages to refresh")
                    return "font, layout and colours applied"

                steps.run(upload)
                uploaded = True
            finally:
                try:
                    if app is not None:
                        try:
                            # V1 handles WM_CLOSE as a UI confirmation. Its own exit IPC
                            # lets the elevated main process perform an orderly shutdown.
                            app.call("require('electron').ipcRenderer.send('WWTHID_WindowALLClose'); return 1;")
                        except Exception:
                            pass  # The CDP socket can close before its final reply; stop() verifies exit.
                        finally:
                            app.close()
                finally:
                    if stopped:
                        self.stop()
                        try:
                            self.restore_debug()
                            if restored:
                                self.restore_scope(restore[1]["scope"])
                            if action == "reset" and uploaded:
                                self.remove_patch_sets()
                        finally:
                            self.start()
            steps.run(lambda: "running normally")
        if action == "install":
            rows = self.check(y)
            ui.report(rows)
            ok = all(r[0] for r in rows)
            ui.verdict(ok, "[bold green]Applied. Check the Fenix page on the real MCDU.[/]",
                       "[bold red]Applied, but an item above needs checking.[/]")
            return ok
        message = "Factory settings applied." if action == "reset" else "Restored."
        ui.verdict(True, f"[bold green]{message}[/] Check the real MCDU.", "")
        return True

    def can_raster(self):
        _, cfg, _ = self.selected()
        font = self.load(cfg)
        used = {font[k]["pcFontSelected"] for k in ("largeFontConfig", "smallFontConfig")}
        used.update(v["pcFontSelected"] for v in font.get("singleCharConfig", {}).values())
        available = {p.stem for p in (self.mcdu / "EditSpace").glob("*/*") if p.suffix.lower() in (".ttf", ".otf")}
        return used <= available

    def show_check(self, ui, y=None):
        rows = self.check(y)
        ui.header("WinWing MCDU · Fenix A320 · check", [("App", f"{self.name} (experimental)"),
                  ("Settings", str(self.config))])
        ui.report(rows)
        ok = all(row[0] for row in rows)
        ui.verdict(ok, "[bold green]Settings are in place.[/]", "Run Full install for SimAppPro v1.")
        return ok

    def menu(self, ui):
        while True:
            ui.header("WinWing MCDU · Fenix A320", [("App", f"{self.name} (experimental)")])
            ui.console.print("  [bold cyan]1[/]  Check only\n  [bold cyan]2[/]  Full install\n"
                             "  [bold cyan]3[/]  Height adjust (resends fonts)\n  [bold cyan]4[/]  Factory reset\n"
                             "  [bold cyan]5[/]  Restore a v1 backup\n  [bold cyan]Q[/]  Quit\n")
            key = self.s.read_key()
            if key in ("q", "esc", "ctrl-c"):
                return -1
            try:
                if key == "1":
                    self.show_check(ui)
                elif key == "2":
                    self.mutate(ui, "install", self.chosen_y())
                elif key == "3":
                    answer = ui.console.input("Offset in pixels (positive = up, negative = down; empty = cancel): ").strip()
                    if not answer:
                        continue
                    try:
                        y = self.chosen_y(self.s.y_of(int(answer)))
                    except ValueError:
                        raise self.s.SetupError("Enter a whole number.")
                    self.mutate(ui, "install", y)
                elif key == "4":
                    self.mutate(ui, "reset")
                elif key == "5":
                    found = sorted(self.backup_root.glob("*/manifest.json"), reverse=True)[:9]
                    for i, p in enumerate(found, 1):
                        ui.console.print(f"  {i}  {p.parent.name}")
                    if not found:
                        ui.notice("No v1 backups", "A v1 install, reset or restore creates one automatically.")
                        continue
                    answer = ui.console.input("Backup number (empty = cancel): ").strip()
                    if answer.isdigit() and 1 <= int(answer) <= len(found):
                        self.mutate(ui, "restore", src=found[int(answer)-1].parent)
                else:
                    continue
            except self.s.SetupError as e:
                ui.error("Stopped", str(e))
            ui.console.input("[dim]Press Enter to return to the menu...[/]")

    def run(self, ui, args):
        self.preflight()
        if args.check:
            return 0 if self.show_check(ui, args.y) else 1
        if args.restore:
            return 0 if self.mutate(ui, "restore", src=args.restore) else 1
        if args.factory_reset:
            return 0 if self.mutate(ui, "reset") else 1
        if args.install or args.y is not None or not self.s.sys.stdin.isatty():
            return 0 if self.mutate(ui, "install", self.chosen_y(args.y)) else 1
        return self.menu(ui)
