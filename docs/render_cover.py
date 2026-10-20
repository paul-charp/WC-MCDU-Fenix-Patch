"""Render the flightsim.to cover from docs/render/cover.html with headless Edge. Needs Pillow and numpy.

    python docs/render_cover.py

Writes docs/render/mcdu-panel.png (the panel with an LCD look on the screen) and docs/cover.png
(1920x1080). Run docs/render_screens.py first for docs/render/mcdu-screen.png and mcdu-bezel.png.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
RENDER = ROOT / "docs" / "render"
PAGE = RENDER / "cover.html"
OUT = ROOT / "docs" / "cover.png"
EDGE = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]


def edge():
    for p in EDGE:
        if p.exists():
            return str(p)
    found = shutil.which("msedge")
    if not found:
        sys.exit("render: Microsoft Edge not found")
    return found


def blur(a, radius):
    """Gaussian blur of a float array (H x W or H x W x 3, 0..1)."""
    if a.ndim == 3:
        return np.stack([blur(a[..., c], radius) for c in range(3)], -1)
    im = Image.fromarray((a.clip(0, 1) * 255 + 0.5).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(radius)), np.float32) / 255


def reflection(box, size, v):
    """Dusk windshield reflected in the cover glass: a slanted pane top right, split by a frame
    post, sky blue at the top to warm near the horizon, blurred and faint."""
    x0, y0, x1, y1 = box
    pt = lambda u, t: (x0 + u * (x1 - x0), y0 + t * (y1 - y0))
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.polygon([pt(0.40, -0.2), pt(1.2, -0.2), pt(1.2, 0.30), pt(0.58, 0.50)], fill=255)
    d.line([pt(0.80, -0.2), pt(0.90, 0.45)], fill=0, width=round((x1 - x0) * 0.035))   # frame post
    pane = blur(np.asarray(mask, np.float32) / 255, 23)
    t = np.clip(v / 0.5, 0, 1)[..., None]
    sky = (1 - t) * np.array([0.42, 0.54, 0.72], np.float32) + t * np.array([0.90, 0.74, 0.58], np.float32)
    return 0.12 * pane[..., None] * sky


def lcd_panel():
    """Screen layer with an LCD look (pixel cells, bloom, backlit black, glass and a reflection), under the bezel,
    which shades the recessed screen along its lip. One MCDU pixel is 3 px here."""
    screen = np.asarray(Image.open(RENDER / "mcdu-screen.png").convert("RGB"), np.float32) / 255
    bezel = np.asarray(Image.open(RENDER / "mcdu-bezel.png").convert("RGBA"), np.float32) / 255
    rgb, alpha = bezel[..., :3], bezel[..., 3]
    h, w = alpha.shape
    ys, xs = np.nonzero(alpha < 0.5)
    inside = (ys > h * 0.1) & (xs > w * 0.1) & (xs < w * 0.9)        # the window, not the picture's corners
    x0, x1, y0, y1 = xs[inside].min(), xs[inside].max(), ys[inside].min(), ys[inside].max()
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = (xx - x0) / (x1 - x0), (yy - y0) / (y1 - y0)                 # 0..1 across the window

    cell = np.array([1.0, 1.0, 0.8], np.float32)                      # dim gap between pixel cells
    cells = cell[(yy.astype(int)) % 3] * cell[(xx.astype(int)) % 3]
    lit = screen * cells[..., None]
    lit += 0.30 * blur(screen, 5) + 0.16 * blur(screen, 24)           # bloom
    backlight = 1.3 - 0.8 * np.clip(((u - 0.5) ** 2 + (v - 0.48) ** 2) * 2.2, 0, 1)
    lit += np.array([0.016, 0.021, 0.025], np.float32) * backlight[..., None]
    # glass: one soft diagonal reflection from the top left
    d = np.clip((u * 0.55 + v) / 0.75, 0, 1)
    lit += (0.055 * (1 - d * d * (3 - 2 * d)))[..., None]
    # the bezel lip over the recessed screen: contact shadow and a wider falloff, light from above
    lip = np.roll(np.roll(alpha, 16, 0), 5, 1)
    lit *= (1 - 0.75 * blur(lip, 10) - 0.45 * blur(lip, 55)).clip(0, 1)[..., None]
    lit += reflection((x0, y0, x1, y1), (w, h), v)

    out = lit.clip(0, 1) * (1 - alpha[..., None]) + rgb * alpha[..., None]
    Image.fromarray((out * 255 + 0.5).astype(np.uint8)).save(RENDER / "mcdu-panel.png", optimize=True)


def main():
    lcd_panel()
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "shot.png"
        subprocess.run([
            edge(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
            f"--user-data-dir={Path(tmp) / 'profile'}", "--window-size=1920,1080", "--force-device-scale-factor=1",
            "--virtual-time-budget=4000", f"--screenshot={png}", PAGE.as_uri(),
        ], check=True, capture_output=True)
        Image.open(png).convert("RGB").save(OUT, optimize=True)
    print(f"render: {OUT.relative_to(ROOT)} 1920x1080")


if __name__ == "__main__":
    main()
