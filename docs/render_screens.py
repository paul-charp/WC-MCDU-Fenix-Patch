"""Render the README screenshots: the MCDU screen as the device draws it, before and after the patch.
Writes perf-take-off.png, f-pln.png, glyphs.png, and render/mcdu-screen.png + mcdu-bezel.png (the
patched PERF TAKE OFF as two layers, used by render_cover.py for the flightsim.to cover).

  python docs/render_screens.py

Glyphs are decoded from the 1-bit fonts SimAppPro2 sends to the MCDU (.wwf), placed on the
640 x 480 screen at the origin SimLogic sends for the Fenix pages, then put behind SimAppPro2's
MCDU bezel picture. The bezel is scaled so that, with the patched layout, the line-select keys
sit on the data lines as they do on the real MCDU (two 31-px text rows per key):

  before  factory WinWing font (GameExtendDisplay/MCDU/EditSpace/WWT_MCDU), 23x29 cells, origin 52, 37
  after   font set currently sent by setup_mcdu.py (customer/default), 23x31 cells, origin 52, 20

Needs Pillow, and SimAppPro2 with this setup installed (for the "after" font).
"""
import glob
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
MCDU = glob.glob(os.path.join(os.environ["APPDATA"], "SimAppPro2", "profile", "WWTEX_profile", "*",
                              "GameExtendDisplay", "MCDU"))[0]
STOCK_WWF = os.path.join(MCDU, "EditSpace", "WWT_MCDU", "WWT_MCDU.wwf")
PATCHED_WWF = os.path.join(MCDU, "customer", "default", "EditSpace", "WWT_MCDU", "WWT_MCDU.wwf")
BEZEL = glob.glob(os.path.join(os.environ["APPDATA"], "SimAppPro2", "extension", "extensions", "WWTEx_ui",
                               "assets", "MCDU_Screen-*.png"))[0]
BEZEL_CROP_BOTTOM = 1245    # bezel picture rows kept (drops the cut-off key row at the bottom)
# centres of the six line-select keys in the bezel picture (1714 x 1321), measured on their white bars
LSK_Y = (388.5, 524.5, 660.0, 795.5, 931.0, 1066.5)
WINDOW_MARGIN = 3           # MCDU px kept between the window edges and the patched text (top and bottom)

SCREEN_W, SCREEN_H = 640, 480
COLS = 24
SCALE = 3                   # output pixels per MCDU pixel
PATCHED_ORIGIN, STOCK_ORIGIN = (52, 20), (52, 37)
# SimAppPro2 defaults, identical to the Fenix web MCDU colours
COLOURS = {"a": (255, 165, 0), "w": (255, 255, 255), "c": (0, 255, 255), "g": (0, 255, 61),
           "m": (255, 99, 255), "r": (255, 0, 0), "y": (255, 255, 0)}

# 14 rows x 24 columns. Each row: [(column, text, size L/S, colour)]
PERF_TAKE_OFF = [
    [(4, "PERF TAKE OFF", "L", "w")],
    [(1, "V1", "S", "w"), (6, "FLP RETR", "S", "w"), (20, "RWY", "S", "w")],
    [(0, "142", "L", "c"), (6, "F=", "S", "w"), (8, "152", "L", "g"), (20, "26R", "L", "g")],
    [(1, "VR", "S", "w"), (6, "SLT RETR", "S", "w"), (15, "TO SHIFT", "S", "w")],
    [(0, "145", "L", "c"), (6, "S=", "S", "w"), (8, "196", "L", "g"), (15, "[M]", "S", "c"), (18, "[   ]*", "L", "c")],
    [(1, "V2", "S", "w"), (9, "CLEAN", "S", "w"), (15, "FLAPS/THS", "S", "w")],
    [(0, "149", "L", "c"), (6, "O=", "S", "w"), (8, "213", "L", "g"), (17, "1/UP0.8", "L", "c")],
    [(0, "TRANS ALT", "S", "w"), (12, "FLEX TO TEMP", "S", "w")],
    [(0, "5000", "L", "c"), (20, "58\u00b0", "L", "c")],
    [(0, "THR RED/ACC", "S", "w"), (13, "ENG OUT ACC", "S", "w")],
    [(0, "1500/1500", "L", "m"), (19, "1500", "L", "m")],
    [(19, "NEXT", "S", "w")],
    [(0, "\u2610\u2610\u2610", "L", "a"), (18, "PHASE>", "L", "w")],
    [(0, "CHECK TAKE OFF DATA", "L", "a")],
]

F_PLN = [
    [(1, "FROM", "S", "w"), (17, "AFR1234", "L", "w")],
    [(8, "UTC", "S", "w"), (15, "SPD/ALT", "S", "w")],
    [(0, "LFPG26R", "L", "g"), (8, "0000", "L", "g"), (15, "---/", "S", "g"), (19, "  392", "L", "g")],
    [(1, "C259°", "S", "g")],
    [(0, "D259F", "L", "g"), (8, "0002", "L", "g"), (15, "155/", "S", "g"), (19, "*3000", "L", "m")],
    [(1, "H226°", "S", "g")],
    [(0, "OKIPA", "L", "g"), (8, "0007", "L", "g"), (15, ".76/", "S", "g"), (19, "FL240", "L", "g")],
    [(1, "UN859", "S", "g"), (19, "68NM", "S", "g")],
    [(0, "RESMI", "L", "g"), (8, "0014", "L", "g"), (15, ".78/", "S", "g"), (19, "FL350", "L", "g")],
    [(0, "---F-PLN DISCONTINUITY--", "S", "w")],
    [(0, "(T/D)", "L", "g"), (8, "0049", "L", "g"), (18, "/", "S", "g"), (19, "FL350", "L", "g")],
    [(0, "DEST", "S", "w"), (8, "UTC", "S", "w"), (14, "DIST", "S", "w"), (20, "EFOB", "S", "w")],
    [(0, "LFMN04L", "L", "w"), (8, "0118", "L", "g"), (14, " 370", "L", "g"), (20, " 5.2", "L", "g")],
    [],
]

GLYPHS = "ABCDEFGHIJKLM", "NOPQRSTUVWXYZ", "0123456789/.-", "+*()[]<>\u2190\u2192\u2191\u2193\u00b0", "\u2610\u0394\u25b2\u25bc\u25c0\u25b6#%:=?_\""


def load_font(path):
    """{(size, char): rows} from a .wwf (per glyph: 4-byte LE code point, then H rows of 3 bytes)."""
    with open(path, encoding="utf-8") as fh:
        wwf = json.load(fh)
    glyphs = {}
    for size, key in (("L", "largeFontConfig"), ("S", "smallFontConfig")):
        head = wwf[key]["headConfig"]
        w, h, step = head["matrixW"], head["matrixH"], head["glyphSize"]
        data = bytes(wwf[key]["pixelUint8Array"])
        for off in range(0, len(data) - step + 1, step):
            cp = int.from_bytes(data[off:off + 4], "little")
            rows = []
            for y in range(h):
                bits = int.from_bytes(data[off + 4 + 3 * y:off + 7 + 3 * y], "big")
                rows.append([(bits >> (23 - x)) & 1 for x in range(w)])
            glyphs[(size, chr(cp))] = rows
    return glyphs, w, h


def draw_screen(page, font, origin):
    glyphs, w, h = font
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), "black")
    px = img.load()
    for r, segments in enumerate(page):
        for col, text, size, colour in segments:
            for i, ch in enumerate(text):
                c = col + i
                if c >= COLS or ch == " ":
                    continue
                cell = glyphs.get((size, ch))
                if cell is None:
                    continue
                x0, y0 = origin[0] + c * w, origin[1] + r * h
                for y, row in enumerate(cell):
                    for x, on in enumerate(row):
                        if on and 0 <= x0 + x < SCREEN_W and 0 <= y0 + y < SCREEN_H:
                            px[x0 + x, y0 + y] = COLOURS[colour]
    return img


def window_box(bezel):
    """Bounding box of the transparent screen window, scanned from the picture's centre."""
    alpha = bezel.getchannel("A")
    cx, cy = bezel.width // 2, bezel.height // 2

    def run(pixel, centre, size):
        """Transparent run through the centre (the picture's own edges can be transparent too)."""
        lo = hi = centre
        while lo > 0 and alpha.getpixel(pixel(lo - 1)) < 128:
            lo -= 1
        while hi < size - 1 and alpha.getpixel(pixel(hi + 1)) < 128:
            hi += 1
        return lo, hi

    x0, x1 = run(lambda x: (x, cy), cx, bezel.width)
    y0, y1 = run(lambda y: (cx, y), cy, bezel.height)
    return x0, y0, x1 + 1, y1 + 1


def calibrate(patched):
    """(k, ax, ay): bezel picture px = (ax, ay) + k * MCDU px.

    Fitted so the capitals of the patched data lines (rows 2, 4 .. 12) are centred on the
    line-select keys, and the text block is centred horizontally in the window. The scale is
    capped and the offset clamped so the capitals of rows 0 to 13 keep WINDOW_MARGIN to the
    window's top and bottom edges."""
    glyphs, w, h = patched
    ink = [y for y, row in enumerate(glyphs[("L", "E")]) if any(row)]
    cap_centre = (ink[0] + ink[-1] + 1) / 2
    lines = [PATCHED_ORIGIN[1] + (2 * i + 2) * h + cap_centre for i in range(len(LSK_Y))]
    n = len(lines)
    mx, my = sum(lines) / n, sum(LSK_Y) / n
    k = sum((x - mx) * (y - my) for x, y in zip(lines, LSK_Y)) / sum((x - mx) ** 2 for x in lines)
    bezel = Image.open(BEZEL).convert("RGBA")
    x0, y0, x1, y1 = window_box(bezel)
    top = PATCHED_ORIGIN[1] + ink[0] - WINDOW_MARGIN                 # MCDU px that must be visible
    bottom = PATCHED_ORIGIN[1] + 13 * h + ink[-1] + 1 + WINDOW_MARGIN
    k = min(k, (y1 - y0) / (bottom - top))
    ay = min(max(my - k * mx, y0 - k * top), y1 - k * bottom)
    return k, (x0 + x1) / 2 - k * (PATCHED_ORIGIN[0] + COLS * w / 2), ay


def bezel_layers(screen, cal):
    """(screen, bezel): the 640 x 480 screen at SCALE on black, and the RGBA bezel over it, both
    placed by the calibration."""
    k, ax, ay = cal
    f = SCALE / k                                       # bezel picture px -> output px
    bezel = Image.open(BEZEL).convert("RGBA")
    bezel = bezel.crop((0, 0, bezel.width, min(bezel.height, BEZEL_CROP_BOTTOM)))
    bezel = bezel.resize((round(bezel.width * f), round(bezel.height * f)), Image.LANCZOS)
    out = Image.new("RGBA", bezel.size, (0, 0, 0, 255))
    out.paste(screen.resize((SCREEN_W * SCALE, SCREEN_H * SCALE), Image.NEAREST), (round(ax * f), round(ay * f)))
    return out, bezel


def in_bezel(screen, cal):
    """The screen behind the MCDU bezel."""
    return Image.alpha_composite(*bezel_layers(screen, cal)).convert("RGB")


def draw_glyph_sheet(font, zoom=4):
    """Large glyphs (one line per string) then small, each pixel as a zoomed dot."""
    glyphs, w, h = font
    lines = [("L", s) for s in GLYPHS] + [("S", s) for s in GLYPHS]
    cols = max(len(s) for _, s in lines)
    img = Image.new("RGB", (cols * w * zoom, len(lines) * h * zoom), "black")
    d = ImageDraw.Draw(img)
    for r, (size, text) in enumerate(lines):
        colour = COLOURS["g"] if size == "L" else COLOURS["c"]
        for c, ch in enumerate(text):
            cell = glyphs.get((size, ch))
            x0, y0 = c * w * zoom, r * h * zoom
            d.rectangle((x0, y0, x0 + w * zoom - 1, y0 + h * zoom - 1), outline=(28, 28, 32))
            if cell is None:
                continue
            for y, row in enumerate(cell):
                for x, on in enumerate(row):
                    if on:
                        d.rectangle((x0 + x * zoom, y0 + y * zoom, x0 + (x + 1) * zoom - 2, y0 + (y + 1) * zoom - 2),
                                    fill=colour)
    return img


def stacked(panels, path):
    """Panels [(title, subtitle, image)] one above the other on a dark background."""
    width = max(im.width for _, _, im in panels)
    title_font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", width // 40)
    sub_font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", width // 62)
    pad, head = width // 50, width // 40 + width // 62 + width // 30
    out = Image.new("RGB", (width + 2 * pad, sum(head + im.height + pad for _, _, im in panels) + pad), (13, 17, 23))
    d = ImageDraw.Draw(out)
    y = pad
    for title, sub, im in panels:
        d.text((pad, y), title, font=title_font, fill=(240, 240, 240))
        d.text((pad, y + width // 40 + width // 120), sub, font=sub_font, fill=(150, 160, 170))
        y += head
        out.paste(im, (pad + (width - im.width) // 2, y))
        y += im.height + pad
    # 256-colour palette: same look, under half the size (the bezel's gradients don't need more)
    out.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    print(f"{os.path.relpath(path, HERE)}  {out.size[0]}x{out.size[1]}  {os.path.getsize(path) / 1e6:.1f} MB")


def cover_layers(screen, cal):
    """Screen and bezel layers of the patched panel, for the flightsim.to cover (docs/render_cover.py)."""
    for name, im in zip(("mcdu-screen", "mcdu-bezel"), bezel_layers(screen, cal)):
        path = os.path.join(HERE, "render", f"{name}.png")
        im.save(path, optimize=True)
        print(f"{os.path.relpath(path, HERE)}  {im.width}x{im.height}")


def main():
    stock, patched = load_font(STOCK_WWF), load_font(PATCHED_WWF)
    cal = calibrate(patched)
    before = ("Before: stock SimAppPro2",
              "WinWing stock font, 23×29 cells, Fenix pages at X 52 Y 37")
    after = ("After: this patch",
             "FMGC Pixel31n: pixel font custom-made for the WinCtrl MCDU to match the Fenix font at the pixel level; "
             "23×31 cells, Fenix pages at X 52 Y 20")
    for name, page in (("perf-take-off", PERF_TAKE_OFF), ("f-pln", F_PLN)):
        patched_screen = draw_screen(page, patched, PATCHED_ORIGIN)
        patched_panel = in_bezel(patched_screen, cal)
        stacked([(*before, in_bezel(draw_screen(page, stock, STOCK_ORIGIN), cal)),
                 (*after, patched_panel)], os.path.join(HERE, f"{name}.png"))
        if name == "perf-take-off":
            cover_layers(patched_screen, cal)
    stacked([("Before", "WinWing stock font: large green, small cyan", draw_glyph_sheet(stock, 6)),
             ("After", "FMGC Pixel31n, custom-made to match the Fenix font: large green, small cyan", draw_glyph_sheet(patched, 6))],
            os.path.join(HERE, "glyphs.png"))


if __name__ == "__main__":
    main()
