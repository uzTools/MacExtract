#!/usr/bin/env python3
"""decode_log.py <shot.png>... — read qd_repro's framebuffer log back to text.

qd_repro writes its log by poking the 1bpp framebuffer through a 5x7 font,
because the thing under test (QuickDraw) cannot also be the thing that reports
the result. This reverses that: it locates the same cells and matches each
glyph against the same font table — parsed straight out of qd_repro.c, so the
two cannot drift apart — and prints the log as ASCII.

It also counts the marker squares in the top eight scan lines, which is the
number that matters when a run dies: the log line for a probe only appears
once the probe returns, but the marker for the *previous* probe is already
there, so "markers=4, six log lines" localises a bomb precisely.

    tools/quickdraw-repro/decode_log.py qd-repro-shots/*.png

Exits non-zero if any shot fails the pass conditions: all ten markers (one for
the header line, one for each of probes 0-8), and every `W=`/`D=`/`P=` reading
1 with every `ME=` reading 0.
"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Geometry — must match qd_repro.c.
MAC_W, MAC_H = 512, 342
FB_SCALE, FB_CELL_W, FB_CELL_H, FB_LOG_Y0 = 2, 12, 16, 12
QD_TOP = 210
ROWS = (QD_TOP - FB_LOG_Y0) // FB_CELL_H
COLS = (MAC_W - 2) // FB_CELL_W
MARK_X0, MARK_PITCH, MARK_W = 4, 16, 12
MARKERS_EXPECTED = 10          # the header line, then probes 0..8


def font():
    """The glyph table, parsed out of qd_repro.c: {(c0..c4): character}."""
    src = open(os.path.join(HERE, "qd_repro.c")).read()
    body = src.split("static const unsigned char kFont[59][5] = {", 1)[1]
    body = body.split("};", 1)[0]
    rows = re.findall(r"\{((?:0x[0-9A-Fa-f]{2},\s*){4}0x[0-9A-Fa-f]{2})\}", body)
    if len(rows) != 59:
        raise SystemExit(f"decode_log: parsed {len(rows)} glyphs, expected 59")
    table = {}
    for i, r in enumerate(rows):
        cols = tuple(int(v, 16) for v in r.split(","))
        table.setdefault(cols, chr(0x20 + i))
    return table


def load(path):
    pgm = subprocess.run(["convert", path, "-compress", "none", "pgm:-"],
                         capture_output=True, check=True).stdout
    toks = re.sub(rb"#[^\n]*", b"", pgm).split()
    if toks[0] != b"P2":
        raise SystemExit(f"decode_log: {path} is not a greymap")
    w, h = int(toks[1]), int(toks[2])
    return w, h, list(map(int, toks[4:4 + w * h]))


def decode(path):
    w, h, px = load(path)
    if w % MAC_W or h % MAC_H or w // MAC_W != h // MAC_H:
        raise SystemExit(f"decode_log: {path} is {w}x{h}, not a whole multiple "
                         f"of the {MAC_W}x{MAC_H} Mac screen")
    s = w // MAC_W
    glyphs = font()

    def dark(mx, my):
        """Sample the centre of one Mac pixel."""
        x, y = int((mx + 0.5) * s), int((my + 0.5) * s)
        return px[y * w + x] < 128

    markers = 0
    for i in range(16):
        x = MARK_X0 + i * MARK_PITCH
        if x + MARK_W >= MAC_W:
            break
        if dark(x + MARK_W // 2, 5):
            markers += 1

    lines = []
    for r in range(ROWS):
        y0 = FB_LOG_Y0 + r * FB_CELL_H
        out = []
        for c in range(COLS):
            x0 = 2 + c * FB_CELL_W
            cols = tuple(
                sum(1 << bit for bit in range(7)
                    if dark(x0 + col * FB_SCALE, y0 + bit * FB_SCALE))
                for col in range(5))
            out.append(glyphs.get(cols, "�" if any(cols) else " "))
        line = "".join(out).rstrip()
        if line:
            lines.append(line)
    return markers, lines


def verdict(markers, lines):
    """Pass conditions, straight off the log qd_repro writes."""
    why = []
    if markers != MARKERS_EXPECTED:
        why.append(f"{markers} marker(s), expected {MARKERS_EXPECTED} — "
                   f"a probe did not return")
    text = "\n".join(lines)
    if "�" in text:
        why.append("undecodable glyph in the log")
    bad = [m.group(0) for m in re.finditer(r"\bME=(-?\d+)", text)
           if m.group(1) != "0"]
    if bad:
        why.append("non-zero MemError: " + ", ".join(bad))
    for tag in ("W=", "D=", "P="):
        for m in re.finditer(re.escape(tag) + r"(-?\d+)", text):
            if m.group(1) != "1":
                why.append(f"{tag}{m.group(1)} — an allocation returned NULL")
    if "MIX" in text and not re.search(r"OK=(\d+)/\1\b", text):
        why.append("the interleaved rounds did not all complete")
    if "DONE" not in text:
        why.append("the run never reached DONE")
    return why


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    failed = 0
    for path in argv:
        markers, lines = decode(path)
        why = verdict(markers, lines)
        print(f"=== {os.path.basename(path)}  markers={markers}  "
              f"{'PASS' if not why else 'FAIL'}")
        for line in lines:
            print("    " + line)
        for w in why:
            print("    !! " + w)
        failed += bool(why)
    print(f"\n{len(argv) - failed}/{len(argv)} PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
