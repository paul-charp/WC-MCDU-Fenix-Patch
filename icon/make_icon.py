"""Draw icon/icon.ico (the .exe icon): an MCDU bezel with a few lines of the patched pixel font.

  python icon/make_icon.py

Large sizes use the real FMGC Pixel31m glyphs; 16-32 px are drawn as coloured text bars so they
stay readable. Also writes icon/preview.png (every size, enlarged).
"""
import glob
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = glob.glob(os.path.join(HERE, "..", "fonts", "*-Large.ttf"))[0]
CELL_W, CELL_H = 23, 31
SIZES = (16, 24, 32, 48, 64, 128, 256)

BEZEL_TOP, BEZEL_BOTTOM = (122, 150, 166), (62, 84, 98)
BEZEL_EDGE = (34, 46, 54)
KEY, KEY_BAR = (24, 26, 28), (205, 210, 214)
WHITE, CYAN, GREEN, AMBER = (255, 255, 255), (0, 255, 255), (0, 255, 61), (255, 165, 0)

# layout in 256-px units, shared by every size
BEZEL_BOX = (6, 40, 250, 216)
SCREEN_BOX = (44, 58, 212, 198)
KEY_W, KEY_H, KEY_X = 22, 20, (15, 219)
COLS = 7
TEXT_X = (SCREEN_BOX[0] + SCREEN_BOX[2] - COLS * CELL_W) / 2
TEXT_Y = (SCREEN_BOX[1] + SCREEN_BOX[3] - 3 * CELL_H) / 2 + 2
CAP_TOP, CAP_H = 8, 20                                  # capitals inside a 31-px cell
# screen text: (row, [(column, text, colour)]); the line-select keys point at rows 1 and 2
ROWS = [(0, [(1.5, "MCDU", WHITE)]),
        (1, [(0, "142", CYAN), (4, "26R", GREEN)]),
        (2, [(0, "☐☐", AMBER), (5, "A>", WHITE)])]
KEY_ROWS = (1, 2)


def vertical_gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line((0, y, w, y), fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return img


def row_centre(r):
    return TEXT_Y + r * CELL_H + CAP_TOP + CAP_H / 2


def body(n, keys=True):
    """Bezel, black screen and line-select keys at n x n (drawn 4x larger, then reduced)."""
    ss = 4
    k = n * ss / 256
    N = n * ss
    box = lambda b: tuple(v * k for v in b)
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    mask = Image.new("L", (N, N), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box(BEZEL_BOX), radius=30 * k, fill=255)
    img.paste(vertical_gradient((N, N), BEZEL_TOP, BEZEL_BOTTOM), (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box(BEZEL_BOX), radius=30 * k, outline=BEZEL_EDGE, width=max(ss, round(4 * k)))
    d.rounded_rectangle(box(SCREEN_BOX), radius=9 * k, fill=(0, 0, 0, 255), outline=(22, 30, 36),
                        width=max(ss, round(3 * k)))
    if keys:
        for r in KEY_ROWS:
            y = row_centre(r)
            for x in KEY_X:
                d.rounded_rectangle(box((x, y - KEY_H / 2, x + KEY_W, y + KEY_H / 2)), radius=4 * k, fill=KEY)
                d.rectangle(box((x + 5, y - 2, x + KEY_W - 5, y + 2)), fill=KEY_BAR)
    return img.resize((n, n), Image.LANCZOS)


def glyphs(n):
    """128 and 256 px: the real FMGC Pixel31m glyphs (one font pixel per icon pixel at 256)."""
    text = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    font = ImageFont.truetype(FONT, CELL_H)             # pixel-exact: renders the drawn pixels
    d = ImageDraw.Draw(text)
    d.fontmode = "1"
    for r, segments in ROWS:
        for col, chars, colour in segments:
            for i, ch in enumerate(chars):
                d.text((round(TEXT_X + (col + i) * CELL_W), round(TEXT_Y + r * CELL_H)), ch, font=font, fill=colour)
    img = body(256)
    img.alpha_composite(text)
    return img if n == 256 else img.resize((n, n), Image.LANCZOS)


def blocks(n):
    """16-64 px: each character as a solid block (48-64 px) or each word as a bar (16-32 px)."""
    img = body(n, keys=n >= 24)
    d = ImageDraw.Draw(img)
    k = n / 256
    h = max(1, round(CAP_H * k))
    gap = 1 if n >= 48 else 0
    for r, segments in ROWS:
        y0 = round(row_centre(r) * k - h / 2)
        for col, chars, colour in segments:
            spans = ([(col + i, col + i + 1) for i in range(len(chars))] if gap
                     else [(col, col + len(chars))])
            for a, b in spans:
                x0 = round((TEXT_X + a * CELL_W + 3) * k)
                x1 = round((TEXT_X + b * CELL_W - 3) * k) - gap
                d.rectangle((x0, y0, max(x0, x1 - 1), y0 + h - 1), fill=colour)
    return img


def main():
    images = [blocks(n) if n <= 64 else glyphs(n) for n in SIZES]
    images[-1].save(os.path.join(HERE, "icon.ico"), sizes=[(n, n) for n in SIZES],
                    append_images=images[:-1])
    zoom = 4
    sheet = Image.new("RGBA", (sum(n * zoom + 24 for n in SIZES[:5]) + 24 + 256 + 24, 256 * 1 + 48),
                      (30, 34, 40, 255))
    x = 24
    for n, im in zip(SIZES, images):
        if n in (128,):
            continue
        big = im if n == 256 else im.resize((n * zoom, n * zoom), Image.NEAREST)
        sheet.alpha_composite(big, (x, 24 + (256 - big.height) // 2 if big.height <= 256 else 24))
        x += big.width + 24
    sheet.save(os.path.join(HERE, "preview.png"))
    print("icon/icon.ico", SIZES)


if __name__ == "__main__":
    main()
