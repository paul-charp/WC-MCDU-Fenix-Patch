"""Install the WinWing MCDU setup for the Fenix A320 on SimAppPro2.

  python setup_mcdu.py               install / re-apply everything
  python setup_mcdu.py --check       check the current state, change nothing
  python setup_mcdu.py --y 18        use another vertical text position (default 20)
  python setup_mcdu.py --restore backups\\20261015-213000   put a backup back

Also built as a standalone WC-MCDU-Fenix-Patch.exe (build_exe.py), with the same arguments.

Run it again after every SimAppPro2 update (updates restore the original SimLogic scripts).
"""
import argparse
import glob
import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

FROZEN = getattr(sys, "frozen", False)                 # running as the PyInstaller .exe
# HERE: where backups\ goes (next to the .exe or the script); BUNDLED: where fonts\ is read from
HERE = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
BUNDLED = getattr(sys, "_MEIPASS", HERE)
EXE = os.path.join(os.environ["LOCALAPPDATA"], "SimAppPro2", "SimAppPro2.exe")
ROOT = os.path.join(os.environ["APPDATA"], "SimAppPro2")
EXT = os.path.join(ROOT, "extension", "extensions")
WORKFLOWS = os.path.join(EXT, "WWTEx_simLogic", "dist", "src_func", "workflow")
UI_ASSETS = os.path.join(EXT, "WWTEx_ui", "assets")
DEBUG_PORT = 9333

DEFAULT_Y = 20
LAYOUT = {"scX": 16, "matrixW": 23, "matrixH": 31}      # + scY = chosen Y position
PREVIEW_YBASE = 0       # so the editor's test grid matches what the sim shows
FONT_SLOT = {"xScale": 1, "yScale": 1, "xShift": 0, "yShift": 0}
FENIX_COLOURS = {"amber": "#FFA500FF", "white": "#FFFFFFFF", "cyan": "#00FFFFFF", "green": "#00FF3DFF",
                 "magenta": "#FF63FFFF", "red": "#FF0000FF", "yellow": "#FFFF00FF"}
# MCDU screen block of the SimLogic Fenix scripts: the only one with X 52 (0x34). WinWing hard-codes Y 37.
SIM_POINT = re.compile(r"('XAisPoint':0x34,'YAxisPoint':)(0x[0-9a-f]+|-?\d+)(,'line':0xe,'column':0x18)")
PACKAGES = {"rich": "rich", "websocket": "websocket-client"}   # import name -> pip name
# WinWing USB vendor 0x4098; MCDU product ids by seat (BB32: same unit seen with another id)
MCDU_PIDS = {"BB36": "Captain", "BB3E": "First Officer", "BB3A": "Observer", "BB32": "MCDU"}
MCDU_WAIT = 180         # seconds to wait for the MCDU to be plugged in


class SetupError(Exception):
    pass


# ------------------------------------------------------------------ console UI
def ensure_packages():
    if FROZEN:                                          # bundled in the .exe
        return
    missing = [pip for mod, pip in PACKAGES.items() if importlib.util.find_spec(mod) is None]
    if not missing:
        return
    print(f"First run: installing Python packages ({', '.join(missing)})...", flush=True)
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--quiet", "--disable-pip-version-check",
                        *missing], capture_output=True, text=True)
    if r.returncode != 0:
        raise SetupError("Could not install " + ", ".join(missing) + ":\n" + (r.stderr or r.stdout).strip()[-800:])
    importlib.invalidate_caches()


class UI:
    """Header, progress bar with one line per finished step, and report tables (rich)."""

    def __init__(self):
        from rich.console import Console
        self.console = Console(highlight=False)

    def header(self, title, rows):
        from rich.panel import Panel
        from rich.table import Table
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="dim")
        grid.add_column()
        for k, v in rows:
            grid.add_row(k, v)
        self.console.print()
        self.console.print(Panel(grid, title=f"[bold]{title}[/]", title_align="left", border_style="cyan",
                                 expand=False, padding=(0, 2)))

    def steps(self, plan):
        return _Steps(self.console, plan)

    def report(self, rows):
        from rich.table import Table
        table = Table(title="Check", title_justify="left", title_style="bold", box=None,
                      padding=(0, 1), show_header=False)
        table.add_column(width=3, justify="right")
        table.add_column(style="bold")
        table.add_column()
        for ok, item, detail in rows:
            table.add_row("[green]✔[/]" if ok else "[red]✘[/]", item, detail if ok else f"[red]{detail}[/]")
        self.console.print()
        self.console.print(table)

    def verdict(self, ok, good, bad):
        from rich.panel import Panel
        self.console.print()
        self.console.print(Panel(good if ok else bad, border_style="green" if ok else "red", expand=False,
                                 padding=(0, 2)))
        self.console.print()

    def notice(self, title, text):
        from rich.panel import Panel
        self.console.print()
        self.console.print(Panel(text, title=f"[bold]{title}[/]", title_align="left", border_style="yellow",
                                 expand=False, padding=(0, 2)))

    def error(self, title, text):
        from rich.panel import Panel
        self.console.print()
        self.console.print(Panel(text, title=f"[bold]{title}[/]", title_align="left", border_style="red",
                                 expand=False, padding=(0, 2)))
        self.console.print()


class _Steps:
    """Runs named steps under one overall progress bar; long steps report their own progress."""

    def __init__(self, console, plan):
        from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn
        self.console = console
        self.plan = plan                                    # [(label, weight)]
        self.total = sum(w for _, w in plan)
        self.base = 0
        self.index = 0
        self.progress = Progress(SpinnerColumn(style="cyan"), TextColumn("{task.description}"),
                                 BarColumn(bar_width=30, complete_style="cyan", finished_style="green"),
                                 TaskProgressColumn(), TimeElapsedColumn(), console=console, transient=True)
        self.task = None

    def __enter__(self):
        self.console.print()
        self.progress.start()
        self.task = self.progress.add_task("", total=self.total)
        return self

    def __exit__(self, *exc):
        self.progress.stop()
        return False

    def run(self, fn, *args):
        """Run one planned step; fn may accept a `tick(fraction, note)` keyword to report progress."""
        label, weight = self.plan[self.index]
        n = f"{self.index + 1}/{len(self.plan)}"
        start = time.monotonic()

        def tick(fraction, note=""):
            fraction = max(0.0, min(1.0, fraction))
            desc = f"[bold]{n}[/] {label}" + (f" [dim]- {note}[/]" if note else "")
            self.progress.update(self.task, completed=self.base + weight * fraction, description=desc)

        tick(0)
        try:
            detail = fn(*args, tick=tick) if "tick" in inspect.signature(fn).parameters else fn(*args)
        except BaseException:
            self.console.print(f"  [red]✘[/] {label}")
            raise
        self.base += weight
        self.index += 1
        self.progress.update(self.task, completed=self.base)
        secs = time.monotonic() - start
        self.console.print(f"  [green]✔[/] {label:<30} {detail or ''}".rstrip()
                           + (f"  [dim]{secs:.0f}s[/]" if secs >= 1 else ""))
        return detail


def wait(seconds, tick, start, end, note):
    """Sleep while moving the progress from `start` to `end`."""
    t0 = time.monotonic()
    while (elapsed := time.monotonic() - t0) < seconds:
        tick(start + (end - start) * elapsed / seconds, note)
        time.sleep(0.2)
    tick(end, note)


# ------------------------------------------------------------------ locations
def gamedisplay_dir():
    hits = sorted(glob.glob(os.path.join(ROOT, "profile", "WWTEX_profile", "*", "GameExtendDisplay", "MCDU")))
    if not hits:
        raise SetupError("SimAppPro2 MCDU profile not found: start SimAppPro2 once with the MCDU plugged in.")
    return os.path.dirname(hits[0])


def mcdu_settings(gx):
    return os.path.join(gx, "MCDU", "customer", "default")


def font_files():
    large = glob.glob(os.path.join(BUNDLED, "fonts", "*-Large.ttf"))
    small = glob.glob(os.path.join(BUNDLED, "fonts", "*-Small.ttf"))
    if len(large) != 1 or len(small) != 1:
        raise SetupError("The fonts\\ folder must hold exactly one *-Large.ttf and one *-Small.ttf.")
    return large[0], small[0]


def font_name(path):
    return os.path.splitext(os.path.basename(path))[0]


def mcdu_workflows():
    if not os.path.isdir(WORKFLOWS):
        return []
    return [os.path.join(d, f) for d in sorted(os.listdir(WORKFLOWS)) if d.startswith("fnx")
            for f in sorted(os.listdir(os.path.join(WORKFLOWS, d)))
            if f.startswith("WINWING_MCDU_32-") and f.endswith(".js")]


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path, data):
    # same format SimAppPro2 writes (indent 2, UTF-8, no escaping)
    with open(path, "wb") as fh:
        fh.write(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))


def selected_font_set(gx):
    """Name, config and font file of the MCDU font set currently selected in SimAppPro2."""
    name = load_json(os.path.join(mcdu_settings(gx), "default_config.json"))["fontConfig"]["fontSelected"]
    folder = os.path.join(mcdu_settings(gx), "EditSpace", name)
    return name, os.path.join(folder, f"{name}_config.json"), os.path.join(folder, f"{name}.wwf")


# ------------------------------------------------------------------ MCDU on USB
def usb_device_ids():
    """Instance ids of the USB devices present now (Windows configuration manager)."""
    import ctypes
    cfg = ctypes.windll.cfgmgr32
    flags = 0x1 | 0x100                                 # CM_GETIDLIST_FILTER_ENUMERATOR | _PRESENT
    size = ctypes.c_ulong()
    if cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(size), "USB", flags) != 0:
        return []
    buf = ctypes.create_unicode_buffer(size.value)
    if cfg.CM_Get_Device_ID_ListW("USB", buf, size.value, flags) != 0:
        return []
    return [i for i in buf[:size.value].split(chr(0)) if i]


def connected_mcdu():
    """Seat name of a WinWing MCDU present on USB, or None."""
    for pid in re.findall(r"VID_4098&PID_([0-9A-F]{4})", " ".join(usb_device_ids()).upper()):
        if pid in MCDU_PIDS:
            return MCDU_PIDS[pid]
    return None


def wait_for_mcdu(ui):
    """Return the MCDU seat name, asking the user to plug it in if it is not connected."""
    name = connected_mcdu()
    if name:
        return name
    ui.notice("Connect the MCDU", "No WinWing MCDU found on USB. Plug it in (and power it on);\n"
                                  "the setup starts by itself as soon as it is detected.\n"
                                  "[dim]Ctrl+C to stop.[/]")
    t0 = time.monotonic()
    with ui.console.status("Waiting for the MCDU...", spinner_style="cyan"):
        while not name:
            if time.monotonic() - t0 > MCDU_WAIT:
                raise SetupError("No WinWing MCDU found on USB. Plug it in, then run this again.")
            time.sleep(1)
            name = connected_mcdu()
        time.sleep(3)                                   # let Windows finish setting it up
    ui.console.print(f"  [green]✔[/] MCDU connected ({name})")
    return name


# ------------------------------------------------------------------ SimAppPro2
def app_pids(exe_name=None):
    """Process ids of the running processes named exe_name (default SimAppPro2.exe)."""
    exe_name = (exe_name or os.path.basename(EXE)).lower()
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):                      # PROCESSENTRY32W
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)         # TH32CS_SNAPPROCESS
    pids, e = set(), Entry()
    e.dwSize = ctypes.sizeof(Entry)
    try:
        ok = k32.Process32FirstW(wintypes.HANDLE(snap), ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == exe_name:
                pids.add(e.th32ProcessID)
            ok = k32.Process32NextW(wintypes.HANDLE(snap), ctypes.byref(e))
    finally:
        k32.CloseHandle(wintypes.HANDLE(snap))
    return pids


def stop_app():
    """Ask SimAppPro2's windows to close, then end whatever is still running after 3 s."""
    import ctypes
    from ctypes import wintypes
    pids = app_pids()
    if not pids:
        return
    user32, k32 = ctypes.windll.user32, ctypes.windll.kernel32

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def close_window(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd):
            user32.PostMessageW(hwnd, 0x10, 0, 0)       # WM_CLOSE
        return True

    user32.EnumWindows(close_window, 0)
    time.sleep(3)
    k32.OpenProcess.restype = wintypes.HANDLE
    for pid in app_pids():
        h = k32.OpenProcess(0x1, False, pid)            # PROCESS_TERMINATE
        if h:
            k32.TerminateProcess(wintypes.HANDLE(h), 0)
            k32.CloseHandle(wintypes.HANDLE(h))
    time.sleep(2)


def start_app(debug=False, tick=None):
    args = [EXE] + ([f"--remote-debugging-port={DEBUG_PORT}", "--remote-allow-origins=*"] if debug else [])
    env = None
    if FROZEN:
        # The .exe's launcher points the DLL search at its _internal folder and child processes
        # inherit it: SimAppPro2 would load our bundled runtime DLLs (and lock the folder).
        import ctypes
        ctypes.windll.kernel32.SetDllDirectoryW(None)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEI"))}
    # Own folder as working directory (it writes logs there) and no console: its Chromium
    # logs would otherwise end up in ours.
    subprocess.Popen(args, cwd=os.path.dirname(EXE), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    if not debug:
        return
    t0 = time.monotonic()
    while time.monotonic() - t0 < 60:
        if tick:
            tick(min(0.6, (time.monotonic() - t0) / 15), "starting SimAppPro2")
        try:
            pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/list", timeout=2))
            if any(p.get("type") == "page" for p in pages):
                if tick:
                    wait(6, tick, 0.6, 1.0, "waiting for SimAppPro2 to load")
                else:
                    time.sleep(6)
                return
        except OSError:
            pass
        time.sleep(0.5)
    raise SetupError("SimAppPro2 did not open its debug port.")


class App:
    """Calls SimAppPro2's own MCDU functions (WWTEx_keyPress.CDU_*) through its UI."""

    def __init__(self):
        import websocket
        pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/list"))
        page = next(p for p in pages if p.get("type") == "page")
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=120)
        self.n = 0
        mains = [os.path.basename(p) for p in glob.glob(os.path.join(UI_ASSETS, "main-*.js"))]
        # main-*.js exports a getter ('c') that returns the extension API; try 'c' first, then other
        # zero-argument exports. The API is an RPC proxy: returning it as-is from an async function
        # would hang (the promise calls .then on it), hence the {k: api} wrapper.
        self.api = ("(async () => { for (const f of %s) {"
                    " const m = await import(new URL('./assets/' + f, location.href).href);"
                    " for (const k of ['c', ...Object.keys(m).filter(x => x !== 'c')]) { try {"
                    " if (typeof m[k] === 'function' && (k === 'c' || m[k].length === 0)) {"
                    " const o = m[k](); if (o && o.WWTEx_keyPress) return {k: o.WWTEx_keyPress}; } } catch (e) {} } }"
                    " throw new Error('SimAppPro2 API not found'); })()") % json.dumps(mains)

    def call(self, body):
        self.n += 1
        expr = ("(async () => { const api = (await %s).k; await api.CDU_changeDeviceId({deviceId: 'MCDU'}); %s })()"
                % (self.api, body))
        self.ws.send(json.dumps({"id": self.n, "method": "Runtime.evaluate",
                                 "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") != self.n:
                continue
            if "error" in m:
                raise SetupError(f"SimAppPro2: {m['error'].get('message')}")
            r = m["result"]
            if "exceptionDetails" in r:
                raise SetupError(f"SimAppPro2: {r['exceptionDetails'].get('exception', {}).get('description', 'error')}")
            return r.get("result", {}).get("value")

    def wait_ready(self, tick=None, timeout=60):
        """Wait until SimAppPro2's back end answers (its UI loads first, then reports "The peer
        ... is not online" for a few seconds); return the names of the fonts it lists."""
        t0 = time.monotonic()
        while True:
            r = self.call("const r = await api.CDU_getPcFontArray();"
                          " return r && r.status === 0 && r.data ? {fonts: r.data.map(x => x.fontName)}"
                          " : {error: (r && (r.errMsg || r.msg)) || 'no answer'};") or {}
            if "fonts" in r:
                return r["fonts"]
            elapsed = time.monotonic() - t0
            if elapsed > timeout:
                raise SetupError(f"SimAppPro2 is not answering ({r.get('error')}). Close it, then run this again.")
            if tick:
                tick(elapsed / timeout, "waiting for SimAppPro2 to be ready")
            time.sleep(1)


# ------------------------------------------------------------------ steps
def close_app(tick):
    tick(0.2, "closing")
    stop_app()
    return "closed"


def backup(gx):
    dest = os.path.join(HERE, "backups", time.strftime("%Y%m%d-%H%M%S"))
    if os.path.isdir(mcdu_settings(gx)):
        shutil.copytree(mcdu_settings(gx), os.path.join(dest, "customer_default"))
    for rel in mcdu_workflows():
        os.makedirs(os.path.join(dest, "workflow", os.path.dirname(rel)), exist_ok=True)
        shutil.copy2(os.path.join(WORKFLOWS, rel), os.path.join(dest, "workflow", rel))
    return f"[dim]{os.path.relpath(dest, HERE)}[/]"


def install_fonts(gx, large, small):
    folder = os.path.join(gx, "Windows", "Fonts")      # SimAppPro2's own font list, read at startup
    os.makedirs(folder, exist_ok=True)
    for f in (large, small):
        shutil.copy2(f, folder)
    return f"{font_name(large)} / {font_name(small)}"


def patch_simlogic(y):
    scripts = mcdu_workflows()
    if not scripts:
        raise SetupError("SimLogic Fenix scripts not found.")
    for rel in scripts:
        path = os.path.join(WORKFLOWS, rel)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if len(SIM_POINT.findall(text)) != 1:
            raise SetupError(f"Unexpected format in {rel} (SimAppPro2 update?): this file was not changed.")
        new = SIM_POINT.sub(lambda m: f"{m.group(1)}{hex(y)}{m.group(3)}", text, count=1)
        if new != text:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(new)
    return f"Y {y} in {len(scripts)} scripts"


def write_settings(gx, y, tick):
    cfg_path = os.path.join(mcdu_settings(gx), "default_config.json")
    if not os.path.exists(cfg_path):                    # fresh install: let SimAppPro2 create its settings
        start_app(debug=True, tick=tick)
        app = App()
        app.wait_ready()
        app.call("await api.CDU_getConfig({isFileSync: true}); await api.CDU_getFontArray(); return 1;")
        stop_app()
        if not os.path.exists(cfg_path):
            raise SetupError("SimAppPro2 did not create its MCDU settings: open the MCDU screen settings page "
                             "once in SimAppPro2, close it, then run this again.")
    cfg = load_json(cfg_path)
    cfg["layoutConfig"].update(LAYOUT, scY=y)
    cfg["previewConfig"]["yBase"] = PREVIEW_YBASE
    for c in cfg["colorConfig"]["colorArray"]:
        if c["colorName"] in FENIX_COLOURS:
            c["currentColor"] = FENIX_COLOURS[c["colorName"]]
    save_json(cfg_path, cfg)
    _, set_cfg, _ = selected_font_set(gx)
    if os.path.exists(set_cfg):                         # the font set keeps its own copy of the grid
        d = load_json(set_cfg)
        d["pixelConfig"].update(LAYOUT, scY=y)
        save_json(set_cfg, d)
    return f"X {LAYOUT['scX']}  Y {y}  {LAYOUT['matrixW']}x{LAYOUT['matrixH']}, Fenix colours"


def send_fonts(gx, large, small, tick):
    set_name, _, _ = selected_font_set(gx)
    start_app(debug=True, tick=lambda f, n: tick(0.45 * f, n))
    app = App()
    listed = app.wait_ready(tick=lambda f, n: tick(0.45 + 0.1 * f, n))
    missing = [font_name(f) for f in (large, small) if font_name(f) not in listed]
    if missing:
        raise SetupError(f"SimAppPro2 does not list {', '.join(missing)} (restart SimAppPro2, then run this again).")
    tick(0.55, "converting and uploading the fonts")
    slot = ", ".join(f"{k}: {v}" for k, v in FONT_SLOT.items())
    # Selecting a font only records it: SimAppPro2 rasterises it into the font set's pixel cache
    # when the pixels are read (getFontConfigWithPixel); save and apply then send that cache.
    # Without the read, they send the previous font's pixels.
    res = app.call(f"""
        await api.CDU_getConfig({{isFileSync: true}}); await api.CDU_getFontArray();
        const codes = [];
        for (const [key, font] of [['largeFontConfig', {json.dumps(font_name(large))}],
                                   ['smallFontConfig', {json.dumps(font_name(small))}]]) {{
          const r = await api.CDU_setFontConfigByKey({{fontName: {json.dumps(set_name)}, key, sizeChar: '',
                                                      pcFontSelected: font, thickness: 1, {slot}}});
          codes.push(r && r.status);
        }}
        const p = await api.CDU_getFontConfigWithPixel({{fontName: {json.dumps(set_name)}}});
        codes.push(p && p.status);
        const s = await api.CDU_saveFontConfigByKey({{fontName: {json.dumps(set_name)}}});
        const a = await api.CDU_applyFont();
        return codes.concat([s && s.status, a && a.status]);""")
    if res != [0] * 5:
        raise SetupError(f"SimAppPro2 refused to select, convert, save or send the fonts (codes {res}).")
    wait(10, tick, 0.7, 1.0, "SimLogic re-sending the Fenix layout")
    return f"font set {set_name}"


def restart_app(tick):
    tick(0.3, "closing debug session")
    stop_app()
    start_app()
    return "running normally"


def check(gx, y, large, small):
    """Return [(ok, item, detail)] comparing the current state with the setup."""
    rows = []
    expected = dict(LAYOUT, scY=y)
    names = [font_name(large), font_name(small)]

    mirror = os.path.join(gx, "Windows", "Fonts")
    present = [n for n in names if os.path.exists(os.path.join(mirror, n + ".ttf"))]
    rows.append((len(present) == 2, "Fonts installed", " / ".join(names) if len(present) == 2
                 else f"missing {', '.join(sorted(set(names) - set(present)))}"))

    if not os.path.exists(os.path.join(mcdu_settings(gx), "default_config.json")):
        rows.append((False, "MCDU settings", "not created by SimAppPro2 yet"))
    else:
        set_name, set_cfg, wwf = selected_font_set(gx)
        if os.path.exists(set_cfg):
            d = load_json(set_cfg)
            slots = [d["largeFontConfig"], d["smallFontConfig"]]
            sel = [s["pcFontSelected"] for s in slots]
            plain = all(all(s.get(k) == v for k, v in FONT_SLOT.items()) for s in slots)
            rows.append((sel == names and plain, "Fonts selected",
                         f"set {set_name}, scale 1, no shift" if sel == names and plain
                         else f"set {set_name}: {sel[0]} / {sel[1]}" + ("" if plain else ", scale or shift changed")))
        else:
            rows.append((False, "Fonts selected", f"font set {set_name} not found"))
        if os.path.exists(wwf):
            head = load_json(wwf)["largeFontConfig"]["headConfig"]
            cells = (head["matrixW"], head["matrixH"])
            rows.append((cells == (LAYOUT["matrixW"], LAYOUT["matrixH"]), "Font sent to MCDU",
                         f"{cells[0]}x{cells[1]} cells"))
        cfg = load_json(os.path.join(mcdu_settings(gx), "default_config.json"))
        lay = {k: cfg["layoutConfig"][k] for k in expected}
        ybase = cfg["previewConfig"].get("yBase")
        fmt = lambda g, yb: f"X {g['scX']}  Y {g['scY']}  {g['matrixW']}x{g['matrixH']}  yBase {yb}"
        good_grid = lay == expected and ybase == PREVIEW_YBASE
        rows.append((good_grid, "Grid", fmt(lay, ybase) + ("" if good_grid else f"  (expected {fmt(expected, PREVIEW_YBASE)})")))
        cols = {c["colorName"]: c["currentColor"].upper() for c in cfg["colorConfig"]["colorArray"]}
        off = [c for c, v in FENIX_COLOURS.items() if cols.get(c) != v]
        rows.append((not off, "Colours", "Fenix" if not off else f"different: {', '.join(off)}"))

    scripts = mcdu_workflows()
    ys = []
    for rel in scripts:
        with open(os.path.join(WORKFLOWS, rel), encoding="utf-8") as fh:
            m = SIM_POINT.search(fh.read())
        ys.append(int(m.group(2), 0) if m else None)
    good = sum(v == y for v in ys)
    found = ", ".join(f"Y {v}" if v is not None else "unknown format" for v in sorted({*ys}, key=str))
    rows.append((bool(scripts) and good == len(scripts), "Fenix pages (SimLogic)",
                 f"Y {y} in all {len(scripts)} scripts" if scripts and good == len(scripts)
                 else f"{good}/{len(scripts)} scripts at Y {y}  (currently {found or 'no scripts found'})"))
    return rows


# ------------------------------------------------------------------ commands
def cmd_check(ui, gx, y):
    large, small = font_files()
    mcdu = connected_mcdu()
    ui.header("WinWing MCDU · Fenix A320 · status",
              [("SimAppPro2", "found"), ("MCDU", f"connected ({mcdu})" if mcdu else "[yellow]not connected[/]"),
               ("Expected", f"fonts {font_name(large)[:-6]}, Y {y}")])
    rows = check(gx, y, large, small)
    ui.report(rows)
    ok = all(r[0] for r in rows)
    fix = f"run {os.path.basename(sys.executable)} again" if FROZEN else "run installer.bat"
    ui.verdict(ok, "[bold green]Everything is in place.[/]", f"[bold red]Needs fixing:[/] {fix}")
    return ok


def cmd_install(ui, gx, y):
    large, small = font_files()
    mcdu = wait_for_mcdu(ui)                            # the fonts are sent to it in step 6
    ui.header("WinWing MCDU · Fenix A320 · setup",
              [("MCDU", f"connected ({mcdu})"),
               ("Fonts", f"{font_name(large)} / {font_name(small)}"),
               ("Grid", f"X {LAYOUT['scX']}  Y {y}  {LAYOUT['matrixW']}x{LAYOUT['matrixH']} cells"),
               ("Colours", "Fenix web MCDU"),
               ("SimAppPro2", "will be closed and restarted (under a minute)")])
    plan = [("Close SimAppPro2", 6), ("Back up current settings", 3), ("Install fonts", 2),
            ("Fenix page position", 2), ("Grid and colours", 2), ("Send fonts to the MCDU", 70),
            ("Restart SimAppPro2", 8)]
    with ui.steps(plan) as s:
        try:
            s.run(close_app)
            s.run(backup, gx)
            s.run(install_fonts, gx, large, small)
            s.run(patch_simlogic, y)
            s.run(write_settings, gx, y)
            s.run(send_fonts, gx, large, small)
        except BaseException:
            stop_app()                                  # never leave SimAppPro2 closed or in debug mode
            start_app()
            raise
        s.run(restart_app)
    rows = check(gx, y, large, small)
    ui.report(rows)
    ok = all(r[0] for r in rows)
    ui.verdict(ok, "[bold green]Done: everything is in place.[/]",
               "[bold red]Done, but an item is flagged ✘ above.[/]")
    return ok


def cmd_restore(ui, gx, src):
    src = src if os.path.isabs(src) else os.path.join(HERE, src)
    if not os.path.isdir(src):
        raise SetupError(f"Backup not found: {src}")
    ui.header("WinWing MCDU · Fenix A320 · restore", [("Backup", os.path.relpath(src, HERE))])

    def put_back():
        if os.path.isdir(os.path.join(src, "customer_default")):
            shutil.rmtree(mcdu_settings(gx), ignore_errors=True)
            shutil.copytree(os.path.join(src, "customer_default"), mcdu_settings(gx))
        wf = os.path.join(src, "workflow")
        for dp, _, files in os.walk(wf):
            for f in files:
                shutil.copy2(os.path.join(dp, f), os.path.join(WORKFLOWS, os.path.relpath(os.path.join(dp, f), wf)))
        return "settings and SimLogic scripts"

    with ui.steps([("Close SimAppPro2", 4), ("Put the files back", 2), ("Restart SimAppPro2", 2)]) as s:
        s.run(close_app)
        s.run(put_back)
        s.run(lambda: (start_app(), "running")[1])
    ui.verdict(True, "Restored. Press [bold]Apply[/] on the MCDU font page to send these settings to the MCDU.", "")


def main():
    ap = argparse.ArgumentParser(description="WinWing MCDU setup for the Fenix A320 (SimAppPro2)")
    ap.add_argument("--check", action="store_true", help="check the current state without changing anything")
    ap.add_argument("--y", type=int, default=DEFAULT_Y, help=f"vertical text position (default {DEFAULT_Y})")
    ap.add_argument("--restore", metavar="BACKUP", help="put back the files of a backup (backups\\... folder)")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    try:
        ensure_packages()
    except SetupError as e:
        print(f"\nError: {e}")
        return 2
    ui = UI()
    try:
        if not os.path.exists(EXE):
            v1 = (" The original SimAppPro (version 1) is running: it is not supported."
                  if app_pids("SimAppPro.exe") else "")
            raise SetupError(f"SimAppPro2 not found ({EXE}).{v1}\n"
                             "This setup needs SimAppPro2, not the original SimAppPro: install SimAppPro2 "
                             "from WinWing's website, open it once with the MCDU plugged in, then run this again.")
        gx = gamedisplay_dir()
        if a.check:
            return 0 if cmd_check(ui, gx, a.y) else 1
        if a.restore:
            cmd_restore(ui, gx, a.restore)
            return 0
        return 0 if cmd_install(ui, gx, a.y) else 1
    except SetupError as e:
        ui.error("Setup stopped", str(e))
        return 2
    except KeyboardInterrupt:
        ui.error("Interrupted", "Stopped by the user. If the install had started, SimAppPro2 was restarted\n"
                                "normally and the previous files are in backups\\.")
        return 2
    except Exception as e:                              # unexpected: short message instead of a traceback
        ui.error("Unexpected error", f"{type(e).__name__}: {e}\n\nThe previous files are in backups\\ (see --restore).")
        return 3


def own_console():
    """True when the .exe was double-clicked: its console window closes as soon as it exits."""
    if not FROZEN:
        return False
    try:
        import ctypes
        # the one-folder .exe is a single process; started from a shell, the shell is a second one
        return ctypes.windll.kernel32.GetConsoleProcessList((ctypes.c_uint * 8)(), 8) <= 1
    except Exception:
        return True


if __name__ == "__main__":
    code = main()
    if own_console() and sys.stdin.isatty():
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
    sys.exit(code)
