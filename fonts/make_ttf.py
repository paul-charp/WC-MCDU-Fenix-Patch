"""Build the MCDU fonts (fonts/*.ttf) from their text bitmaps (fonts/src/*.txt).

  python fonts/make_ttf.py           build fonts/<name>.ttf from every fonts/src/<name>.txt
  python fonts/make_ttf.py --check   check that fonts/*.ttf match their bitmaps (exit 1 if not)

Each .txt holds a few "key: value" lines (family, copyright, cell, baseline), then one block
per character: a "U+XXXX" line and one row of '#' (lit) / '.' (off) per pixel row of the cell.

SimAppPro2 converts a TrueType font to the MCDU's 1-bit cells by drawing it at the cell height
(times the X/Y scale), centring each glyph on its advance width and lighting every pixel the
outline touches. So each lit pixel becomes a square 100 units wide, inset INSET units from the
pixel edges: with units per em = cell height x 100, scale 1.0 and an advance of the whole cell,
the conversion gives back exactly these bitmaps. Ascent + descent equal one em, so the baseline
lands on `baseline` (in px from the top of the cell) whatever the cell height.

Needs fontTools (pip install fonttools).
"""
import glob
import os
import sys

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
PX = 100     # font units per pixel
INSET = 25   # units between a pixel square and the pixel edges


def read_bitmaps(path):
    """Return (header dict, {char: [row strings]}) from a .txt bitmap file."""
    header, glyphs, rows = {}, {}, None
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line or line.startswith("#!"):
                continue
            if line.startswith("U+"):
                rows = glyphs.setdefault(chr(int(line.split()[0][2:], 16)), [])
            elif rows is None:
                key, _, value = line.partition(":")
                header[key.strip()] = value.strip()
            elif set(line) <= {"#", "."}:
                rows.append(line)
            else:
                sys.exit(f"{path}:{n}: unexpected line {line!r}")
    w, h = map(int, header["cell"].split("x"))
    for ch, rows in glyphs.items():
        if len(rows) != h or any(len(r) != w for r in rows):
            sys.exit(f"{path}: U+{ord(ch):04X} is not {w}x{h}")
    return header, glyphs


def write_bitmaps(path, header, glyphs):
    """Write a .txt bitmap file (used to create it from an existing .ttf)."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("#! Source of fonts/{0}.ttf: build it with `python fonts/make_ttf.py`.\n"
                "#! One block per character: U+code, then one row per pixel row, '#' = lit.\n"
                "#! baseline = px from the top of the cell to the baseline.\n"
                .format(os.path.splitext(os.path.basename(path))[0]))
        for key, value in header.items():
            f.write(f"{key}: {value}\n")
        for ch in sorted(glyphs):
            label = f" {ch}" if ch.isprintable() and not ch.isspace() else ""
            f.write(f"\nU+{ord(ch):04X}{label}\n")
            f.write("\n".join(glyphs[ch]) + "\n")


def square_glyph(rows, baseline):
    pen = TTGlyphPen(None)
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c != "#":
                continue
            x0, x1 = x * PX + INSET, (x + 1) * PX - INSET
            top = round((baseline - y) * PX) - INSET      # font y grows upwards from the baseline
            bot = round((baseline - y - 1) * PX) + INSET
            pen.moveTo((x0, bot))
            pen.lineTo((x0, top))
            pen.lineTo((x1, top))
            pen.lineTo((x1, bot))
            pen.closePath()
    return pen.glyph()


def build(src, out):
    header, glyphs = read_bitmaps(src)
    family, baseline = header["family"], float(header["baseline"])
    w, h = map(int, header["cell"].split("x"))
    upm, advance = h * PX, w * PX
    names, cmap = [".notdef"], {}
    glyf = {".notdef": TTGlyphPen(None).glyph()}
    for ch in sorted(glyphs):
        name = "space" if ch == " " else f"uni{ord(ch):04X}"
        names.append(name)
        cmap[ord(ch)] = name
        glyf[name] = square_glyph(glyphs[ch], baseline)
    ascent = round(baseline * PX)
    descent = upm - ascent
    fb = FontBuilder(upm, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyf)
    hmtx = {}
    for n in names:
        g = fb.font["glyf"][n]
        g.recalcBounds(fb.font["glyf"])
        hmtx[n] = (advance, getattr(g, "xMin", 0))
    fb.setupHorizontalMetrics(hmtx)
    fb.setupHorizontalHeader(ascent=ascent, descent=-descent)
    ps = family.replace(" ", "")
    fb.setupNameTable({"familyName": family, "styleName": "Regular", "uniqueFontIdentifier": ps,
                       "fullName": family, "psName": ps, "version": header.get("version", "Version 1.0"),
                       "copyright": header.get("copyright", "")})
    fb.setupOS2(sTypoAscender=ascent, sTypoDescender=-descent, sTypoLineGap=0,
                usWinAscent=ascent, usWinDescent=descent, fsType=int(header.get("fsType", 0)), version=4)
    fb.setupPost(isFixedPitch=1)
    fb.save(out)
    print(f"{out}: {len(glyphs)} glyphs, {w}x{h}, baseline {baseline} px")


def read_ttf(path):
    """Decode a font built by build() back to (header, {char: rows})."""
    font = TTFont(path)
    upm, advance = font["head"].unitsPerEm, font["hmtx"]["space"][0]
    w, h = advance // PX, upm // PX
    ascent = font["hhea"].ascent
    glyf, names = font["glyf"], font["name"]
    glyphs = {}
    for code, name in font.getBestCmap().items():
        cells = [["."] * w for _ in range(h)]
        g = glyf[name]
        if g.numberOfContours > 0:
            coords, ends = g.getCoordinates(glyf)[:2]
            start = 0
            for end in ends:
                xs = [p[0] for p in coords[start:end + 1]]
                ys = [p[1] for p in coords[start:end + 1]]
                start = end + 1
                x, top = (min(xs) - INSET) // PX, max(ys) + INSET
                cells[(ascent - top) // PX][x] = "#"
        glyphs[chr(code)] = ["".join(r) for r in cells]
    header = {"family": names.getDebugName(1), "copyright": names.getDebugName(0),
              "version": names.getDebugName(5), "fsType": str(font["OS/2"].fsType),
              "cell": f"{w}x{h}", "baseline": f"{ascent / PX:g}"}
    return header, glyphs


def check():
    bad = 0
    for src in sorted(glob.glob(os.path.join(SRC, "*.txt"))):
        ttf = os.path.join(HERE, os.path.splitext(os.path.basename(src))[0] + ".ttf")
        if not os.path.exists(ttf):
            print(f"missing {ttf}")
            bad += 1
            continue
        want_header, want = read_bitmaps(src)
        got_header, got = read_ttf(ttf)
        diff = sorted(ch for ch in set(want) | set(got) if want.get(ch) != got.get(ch))
        diff_header = [k for k in want_header if want_header[k] != got_header.get(k)]
        status = "OK" if not diff and not diff_header else "differs"
        print(f"{os.path.basename(ttf)}: {len(got)} glyphs, {status}"
              + "".join(f"\n  U+{ord(ch):04X}" for ch in diff)
              + "".join(f"\n  {k}: {got_header.get(k)!r} != {want_header[k]!r}" for k in diff_header))
        bad += status != "OK"
    return bad


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        sys.exit(1 if check() else 0)
    if sys.argv[1:]:
        sys.exit(__doc__)
    for src in sorted(glob.glob(os.path.join(SRC, "*.txt"))):
        build(src, os.path.join(HERE, os.path.splitext(os.path.basename(src))[0] + ".ttf"))
