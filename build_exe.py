"""Build dist/WC-MCDU-Fenix-Patch/ (the .exe with its _internal folder) and
dist/WinCtrl-MCDU-Fenix-A320-Patch-<version>.zip.

  python build_exe.py            version 0.0.0 (local build)
  python build_exe.py 1.2.0      version stamped in the .exe and the .zip name (CI passes the tag)

One-folder build (not one-file: a self-extracting single .exe is what antivirus heuristics flag
most), with Windows version info. Installs PyInstaller, rich and websocket-client with
pip --user if they are missing.
"""
import glob
import importlib.util
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "WC-MCDU-Fenix-Patch"
ZIP_NAME = "WinCtrl-MCDU-Fenix-A320-Patch"   # release zip, same name on GitHub and flightsim.to
PACKAGES = {"PyInstaller": "pyinstaller", "rich": "rich", "websocket": "websocket-client"}

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={v4}, prodvers={v4}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
          StringStruct('CompanyName', 'Paul Charpentier'),
          StringStruct('FileDescription', 'WinWing MCDU setup for the Fenix A320 (SimAppPro2)'),
          StringStruct('FileVersion', '{v}'),
          StringStruct('InternalName', '{name}'),
          StringStruct('LegalCopyright', 'Paul Charpentier'),
          StringStruct('OriginalFilename', '{name}.exe'),
          StringStruct('ProductName', 'WC MCDU Fenix Patch'),
          StringStruct('ProductVersion', '{v}')])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])])
"""


def parse_version(text):
    parts = text.lstrip("v").split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        sys.exit(f"version must look like 1.2.0, not {text!r}")
    return tuple(int(p) for p in parts)


def main():
    version = parse_version(sys.argv[1] if len(sys.argv) > 1 else "0.0.0")
    missing = [pip for mod, pip in PACKAGES.items() if importlib.util.find_spec(mod) is None]
    if missing:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", *missing], check=True)
    fonts = glob.glob(os.path.join(HERE, "fonts", "*.ttf"))
    if len(fonts) != 2:
        sys.exit("fonts\\ must hold exactly one *-Large.ttf and one *-Small.ttf")
    build, dist = os.path.join(HERE, "build"), os.path.join(HERE, "dist")
    shutil.rmtree(dist, ignore_errors=True)
    os.makedirs(build, exist_ok=True)
    version_file = os.path.join(build, "version_info.txt")
    with open(version_file, "w", encoding="utf-8") as fh:
        fh.write(VERSION_INFO.format(v4=version + (0,), v=".".join(map(str, version)), name=NAME))
    args = [os.path.join(HERE, "setup_mcdu.py"), "--onedir", "--console", "--name", NAME,
            "--distpath", dist, "--workpath", build, "--specpath", build,
            "--version-file", version_file,
            "--collect-submodules", "rich._unicode_data",   # rich loads these tables by name
            "--exclude-module", "pygments",                 # only for rich.syntax / tracebacks, unused
            "--icon", os.path.join(HERE, "icon", "icon.ico"),   # drawn by icon/make_icon.py
            "--noconfirm", "--clean", "--log-level", "WARN"]
    for f in fonts:
        args += ["--add-data", f"{f}{os.pathsep}fonts"]
    import PyInstaller.__main__
    PyInstaller.__main__.run(args)
    shutil.rmtree(build, ignore_errors=True)
    folder = os.path.join(dist, NAME)
    archive = shutil.make_archive(os.path.join(dist, f"{ZIP_NAME}-{'.'.join(map(str, version))}"), "zip", dist, NAME)
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(folder) for f in fs)
    print(f"\n{os.path.relpath(folder, HERE)}\\{NAME}.exe  ({size / 1e6:.1f} MB folder)")
    print(f"{os.path.relpath(archive, HERE)}  {os.path.getsize(archive) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
