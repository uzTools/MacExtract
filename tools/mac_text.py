#!/usr/bin/env python3
"""mac_text.py — a text to be read on a Macintosh, styled for SimpleText.

    python3 tools/mac_text.py README.md -o OUT/README.bin --split
    python3 tools/mac_text.py dist/README.txt -o OUT/README.txt.bin --split
    python3 tools/mac_text.py docs/floppy-read-me.txt --markdown --disk HFS \\
        --name "Read Me" -o OUT/readme.bin
    python3 tools/mac_text.py --verify OUT/README.bin     # read one back
    python3 tools/mac_text.py --selftest                  # can --verify fail?

Writes a MacBinary II file: the text in its data fork, as Mac Roman with CR
line ends, and a 'styl' resource 128 in its resource fork, the style scrap
SimpleText reads to draw headings, bold and code; TeachText and every other
reader of plain text ignore the resource fork and show the text as it always
was (DECISIONS.md 2026-11-16, *the Read Me in styles*). Typed 'ttro'/'ttxt',
a read-only SimpleText document; --editable types it 'TEXT'.

Two kinds of source:

  Markdown (a .md file, or --markdown): "# " and "## " headings, Setext
  headings, **bold**, *italic*, `code` and fenced code, "- " lists, tables
  (a row per line, cells between " | ", the header bold), [links](url)
  (the text, then the URL in parentheses when it is absolute), and
  <img alt> as "[Picture: alt]"; other HTML tags are dropped.
  docs/floppy-read-me.txt is written in this subset.

  Plain text (anything else): a line underlined with === or --- is a
  heading, and an item indented two spaces ("  NAME  what it is", as
  dist/README.txt lists its files) starts a line with NAME in bold.
  Nothing else in it is markup: dist/README.txt names __MACOSX.

In both, the lines of a paragraph are joined with a space, since SimpleText
and TeachText wrap a paragraph to their window themselves; a blank line ends
a paragraph, and a list item or a table row starts a line of its own. With
--disk HFS or --disk MFS, a line starting {HFS} is kept only for that disk,
{MFS} likewise, the tag removed.

The size limit is the readers': over LIMIT bytes of text it refuses, or with
--split cuts the text at paragraphs into the fewest parts that fit, as even
as the paragraphs allow, written OUT-1.bin, OUT-2.bin... and named
"NAME (1 of 2)"... on the Mac.

What it CANNOT see: how a reader draws the result. --verify reads the
structure back (the count, each run's offset inside the text and in order,
fonts, sizes and heights against the table below, no character the fonts
lack, the size limit); whether SimpleText or TeachText honours it is the
emulator's to show (DECISIONS.md 2026-11-16, *the Read Me in styles*).
"""
import argparse, os, re, struct, sys, time

# What the readers open, measured one boot per size (DECISIONS.md
# 2026-11-14, *the floppy that works locked*): TeachText 1.2 on System
# 6.0.8 at 1 MB opens 32,000 bytes and refuses 32,001 ("This document is
# too large to be opened by TeachText."); SimpleText on 7.0.1 at 4 MB opens
# 31,500 and refuses 31,999. The guard sits 1,500 under the lower; the
# Read Me that was refused on a Mac Plus was 32,436.
LIMIT = 30000

# The style scrap. Source: Retro68's multiversal interface definitions,
# /opt/Retro68/multiversal/defs/TextEdit.yaml (Inside Macintosh: Text,
# "TextEdit"):
#   StScrpRec     scrpNStyles INTEGER, then scrpStyleTab, an array of
#   ScrpSTElement scrpStartChar LONGINT, scrpHeight INTEGER, scrpAscent
#                 INTEGER, scrpFont INTEGER, scrpFace Style (a byte), filler
#                 Byte, scrpSize INTEGER, scrpColor RGBColor (3 x uint16),
#                 size 20.
# Read back off Apple's own SimpleText documents on the System 7.5.5
# install disk ("About System 7.5": 'styl' 128, 1,902 B = 2 + 20 x 95).
# Style bits (QuickDraw.yaml, StyleItem): bold 1, italic 2.
# Font numbers (FontMgr.yaml): kFontIDGeneva 3, kFontIDMonaco 4.
GENEVA, MONACO = 3, 4
BOLD, ITALIC = 1, 2

# scrpHeight and scrpAscent per font and size: the bitmap font's own FontRec
# (multiversal FontMgr.yaml), ascent + descent + leading, and ascent, read
# off the 'FONT'/'NFNT' resources of the System files of 3.0, 6.0.8 and
# 7.0.1 and the 7.5.5 Fonts folder, which agree for every size here. The
# same sum reproduces Apple's own entries in "About System 7.5" (Geneva 9
# 12/10, Helvetica 12 14/10, Times 14 15/12), where bold leaves both as
# they are (Helvetica 12 bold: 14/10).
METRIC = {
    (GENEVA, 12): (16, 12),
    (GENEVA, 14): (19, 14),
    (GENEVA, 18): (23, 18),
    (MONACO, 9): (11, 9),
}
BODY = (GENEVA, 12, 0)
CODE_FONT = (MONACO, 9)
HEADING = {1: (GENEVA, 18, BOLD), 2: (GENEVA, 14, BOLD)}   # 3 and below: body, bold

# The Geneva, Monaco and Chicago bitmaps of 3.0, 6.0.8 and 7.0.1 stop at
# 0xD9 (0xD8 for Chicago on 3.0 and 6.0.8), and have no 0xE1 either, so
# nothing above 0xD9 is written. What the sources hold outside Mac Roman, or
# above 0xD9, spelled in characters those fonts have:
SUBST = {"✅": "yes", "\U0001F534": "no", "️": "", "·": "•",
         "→": "->", "←": "<-", "×": "x", " ": " ",
         "‑": "-", "−": "-"}


# ------------------------------------------------------------------ text

def mac_bytes(s, where):
    s = re.sub(r"(\d)½", r"\1 1/2", s).replace("½", "1/2")
    s = "".join(SUBST.get(c, c) for c in s)
    try:
        b = s.encode("mac_roman")
    except UnicodeEncodeError as e:
        sys.exit(f"mac_text: {where}: {s[e.start]!r} (U+{ord(s[e.start]):04X}) "
                 f"is not in Mac Roman; add it to SUBST")
    hi = [c for c in b if c > 0xD9]
    if hi:
        ch = bytes([hi[0]]).decode("mac_roman")
        sys.exit(f"mac_text: {where}: {ch!r} is Mac Roman 0x{hi[0]:02X}, which the "
                 f"bitmap fonts of 3.0-7.0.1 do not draw; add it to SUBST")
    return b


def inline(s, style, out):
    """Markdown inline markup into (text, font, size, face) spans."""
    font, size, face = style
    buf = []

    def flush():
        if buf:
            out.append(("".join(buf), font, size, face))
            buf.clear()

    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n and s[i + 1] in "\\`*_[]()#+-.!<>|":
            buf.append(s[i + 1]); i += 2; continue
        if c == "`":
            tick = re.match(r"`+", s[i:]).group(0)
            j = s.find(tick, i + len(tick))
            if j > 0:
                flush()
                cf = CODE_FONT if size == 12 else (font, size)
                out.append((s[i + len(tick):j].strip(), cf[0], cf[1], face))
                i = j + len(tick); continue
        if s.startswith("**", i) or s.startswith("__", i):
            mk = s[i:i + 2]
            j = s.find(mk, i + 2)
            if j > i + 2 and s[i + 2] != " " and (mk == "**" or not s[i - 1:i].isalnum()):
                flush(); inline(s[i + 2:j], (font, size, face | BOLD), out)
                i = j + 2; continue
        if c in "*_" and i + 1 < n and s[i + 1] not in " " + c and \
                (c == "*" or not s[i - 1:i].isalnum()):
            j = i + 1
            while True:
                j = s.find(c, j)
                if j < 0 or (s[j - 1] != " " and s[j + 1:j + 2] != c and
                             (c == "*" or not s[j + 1:j + 2].isalnum())):
                    break
                j += 2 if s[j + 1:j + 2] == c else 1
            if j > 0:
                flush(); inline(s[i + 1:j], (font, size, face | ITALIC), out)
                i = j + 1; continue
        m = re.match(r"!\[([^\]]*)\]\([^)]*\)", s[i:])
        if m:
            buf.append("[Picture: %s]" % m.group(1)); i += m.end(); continue
        m = re.match(r"\[([^\]]+)\]\(\s*<?([^)\s>]*)>?(?:\s+\"[^\"]*\")?\s*\)", s[i:])
        if m:
            flush()
            inline(m.group(1), style, out)
            url = m.group(2)
            label = re.sub(r"[`*_]", "", m.group(1))
            if re.match(r"[a-z]+:", url) and label != url:
                buf.append(" (%s)" % url)
            i += m.end(); continue
        m = re.match(r"<((?:https?|mailto):[^>\s]+)>", s[i:])
        if m:
            buf.append(m.group(1)); i += m.end(); continue
        m = re.match(r"<img\b[^>]*\balt=\"([^\"]*)\"[^>]*>", s[i:], re.I)
        if m:
            buf.append("[Picture: %s]" % m.group(1)); i += m.end(); continue
        m = re.match(r"</?[A-Za-z][^>]*>", s[i:])
        if m:
            i += m.end(); continue
        buf.append(c); i += 1
    flush()


def keep_for_disk(lines, disk):
    out = []
    for line in lines:
        for tag in ("{HFS}", "{MFS}"):
            if line.startswith(tag):
                line = line[len(tag):] if disk and tag == "{%s}" % disk else None
                break
        if line is not None:
            out.append(line)
    return out


class Blocks:
    """Paragraphs, each a list of lines, each a list of pieces
    [text, style, markdown?]; a joined line extends its last piece."""

    def __init__(self):
        self.blocks, self.cur = [], None

    def end(self):
        if self.cur:
            self.blocks.append(self.cur)
        self.cur = None

    def line(self, text, style=BODY, md=True):
        if self.cur is None:
            self.cur = []
        self.cur.append([[text, style, md]])

    def piece(self, text, style=BODY, md=True):
        self.cur[-1].append([text, style, md])

    def join(self, text):
        if self.cur is None:
            self.line(text)
        else:
            self.cur[-1][-1][0] += " " + text

    def whole(self, lines):
        self.end()
        if lines:
            self.blocks.append(lines)


SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


def markdown_blocks(lines):
    B = Blocks()
    i = 0
    while i < len(lines):
        L = lines[i].rstrip()
        s = L.strip()
        nxt = lines[i + 1].rstrip() if i + 1 < len(lines) else ""
        if not s:
            B.end(); i += 1; continue
        if s.startswith("```") or s.startswith("~~~"):
            fence = s[:3]
            j = i + 1
            code = []
            while j < len(lines) and not lines[j].strip().startswith(fence):
                code.append(lines[j].rstrip())
                j += 1
            B.whole([[[c or " ", CODE_FONT + (0,), False]] for c in code])
            i = j + 1; continue
        m = re.match(r"(#{1,6})\s+(.*?)\s*#*\s*$", s)
        if m:
            lvl = len(m.group(1))
            B.whole([[[m.group(2), HEADING.get(lvl, (GENEVA, 12, BOLD)), True]]])
            i += 1; continue
        if B.cur is None and re.match(r"^(=+|-+)\s*$", nxt) and not s.startswith("|"):
            B.whole([[[s, HEADING[1 if nxt.strip()[0] == "=" else 2], True]]])
            i += 2; continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip()); i += 1
            out = []
            for k, r in enumerate(rows):
                if SEP.match(r):
                    continue
                cells = [c.strip() for c in r.strip("|").split("|")]
                # "<check mark> for StuffIt" reads "yes, for StuffIt"
                cells = [re.sub("^(✅|\U0001F534)️? (?=[^ *])", "\\1, ", c)
                         for c in cells]
                if k == 0:
                    if any(cells):          # a blank corner cell is left out
                        out.append([[" | ".join(cells[1:] if not cells[0] else cells),
                                     (GENEVA, 12, BOLD), True]])
                else:
                    out.append([[" | ".join(cells), BODY, True]])
            B.whole(out)
            continue
        if s.startswith("<") and not re.match(r"<(https?|mailto):", s):
            pics = []
            while i < len(lines) and lines[i].strip():
                pics += re.findall(r"<img\b[^>]*\balt=\"([^\"]*)\"", lines[i], re.I)
                i += 1
            B.whole([[["[Picture: %s]" % p, BODY, False]] for p in pics])
            continue
        if RULE.match(L):
            B.end(); i += 1; continue
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)", L)
        if m:
            bullet = "•" if m.group(2) in "-*+" else m.group(2)
            B.line("  " * (len(m.group(1)) // 2) + bullet + " " + m.group(3))
            i += 1; continue
        if s.startswith(">"):
            s = s.lstrip("> ").strip()
        if B.cur is None:
            B.line(s)
        else:
            B.join(s)
        i += 1
    B.end()
    return B.blocks


def plain_blocks(lines):
    B = Blocks()
    i = 0
    while i < len(lines):
        L = lines[i].rstrip()
        nxt = lines[i + 1].rstrip() if i + 1 < len(lines) else ""
        if not L.strip():
            B.end(); i += 1; continue
        if B.cur is None and re.match(r"^(=+|-+)\s*$", nxt):
            B.whole([[[L.strip(), HEADING[1 if nxt.strip()[0] == "=" else 2], False]]])
            i += 2; continue
        m = re.match(r"^  (\S.*?)  +(\S.*)$", L)
        if m:
            B.line(m.group(1), (GENEVA, 12, BOLD), False)
            B.piece("  " + m.group(2), BODY, False)
        elif re.match(r"^  \S", L) or L.startswith("- ") or B.cur is None:
            B.line(L.strip(), BODY, False)
        else:
            B.join(L.strip())
        i += 1
    B.end()
    return B.blocks


def spans_of(block):
    """A block's lines as spans, with CR between lines."""
    spans = []
    for k, line in enumerate(block):
        if k:
            spans.append(("\r",) + BODY)
        for text, style, md in line:
            if md:
                inline(text, style, spans)
            else:
                spans.append((text,) + style)
    return spans


def render(blocks, where):
    """(data, runs): runs as (offset, font, size, face), merged. Each line
    break and blank line is in the body style, so a blank line is a body
    line's height."""
    data, runs = bytearray(), []
    for k, block in enumerate(blocks):
        spans = ([("\r\r",) + BODY] if k else []) + spans_of(block)
        for text, font, size, face in spans:
            b = mac_bytes(text, where)
            if not b:
                continue
            if not runs or runs[-1][1:] != (font, size, face):
                if runs and runs[-1][0] == len(data):
                    runs.pop()
                if not runs or runs[-1][1:] != (font, size, face):
                    runs.append((len(data), font, size, face))
            data += b
    data += b"\r"
    return bytes(data), runs or [(0,) + BODY]


def styl(runs):
    out = struct.pack(">h", len(runs))
    for off, font, size, face in runs:
        h, a = METRIC[(font, size)]
        out += struct.pack(">ihhhBBhHHH", off, h, a, font, face, 0, size, 0, 0, 0)
    return out


def split(blocks, limit, where):
    """The fewest parts under limit, cut at paragraphs, as even as they go."""
    sizes = [len(render([b], where)[0]) + 1 for b in blocks]   # +1: the blank line
    total = sum(sizes)
    for k in range(2, len(blocks) + 1):
        if total / k > limit:
            continue
        parts, start = [], 0
        for j in range(1, k):
            target = total * j / k
            cut = min(range(start + 1, len(blocks)),
                      key=lambda c: abs(sum(sizes[:c]) - target))
            parts.append(blocks[start:cut])
            start = cut
        parts.append(blocks[start:])
        if all(p and len(render(p, where)[0]) <= limit for p in parts):
            return parts
    sys.exit(f"mac_text: {where}: one paragraph alone is over {limit} B")


# ------------------------------------------------------- resource, MacBinary

def resource_fork(rtype, rid, body):
    """A resource fork of one resource. Layout: Source: Inside Macintosh:
    More Macintosh Toolbox, "Resource Manager" (Figure 1-12 ff.), as
    tools/vmac/deskclaim.py writes it: the header (data offset, map offset,
    data length, map length), the data (each a length, then the bytes), the
    map (a copy of the header, 6 reserved bytes, attributes, the type list's
    and the name list's offsets, the type list, the reference list)."""
    data = struct.pack(">I", len(body)) + body
    do = 256
    tl = struct.pack(">h4shH", 0, rtype, 0, 10)
    ref = struct.pack(">hHB", rid, 0xFFFF, 0) + (0).to_bytes(3, "big") + b"\0" * 4
    mp_len = 28 + len(tl) + len(ref)
    head = struct.pack(">IIII", do, do + len(data), len(data), mp_len)
    mp = head + b"\0" * 6 + struct.pack(">HHH", 0, 28, mp_len) + tl + ref
    return head + b"\0" * (do - 16) + data + mp


def read_resources(r):
    do, mo, dl, ml = struct.unpack(">IIII", r[:16])
    m = r[mo:mo + ml]
    tlo = struct.unpack(">H", m[24:26])[0]
    n = struct.unpack(">h", m[tlo:tlo + 2])[0] + 1
    out = {}
    for i in range(n):
        t, c, ro = struct.unpack(">4shH", m[tlo + 2 + 8 * i:tlo + 10 + 8 * i])
        for j in range(c + 1):
            e = tlo + ro + 12 * j
            rid = struct.unpack(">h", m[e:e + 2])[0]
            off = int.from_bytes(m[e + 5:e + 8], "big")
            ln = struct.unpack(">I", r[do + off:do + off + 4])[0]
            out[(t, rid)] = r[do + off + 4:do + off + 4 + ln]
    return out


def crc16_xmodem(b):
    crc = 0
    for ch in b:
        crc ^= ch << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def macbinary(name, ftype, creator, data, rsrc):
    """MacBinary II. Header offsets: Source: src/fmt_macbinary.c, itself
    from reference/XADMaster/XADMacArchiveParser.m (as tools/vmac/mkmfs.py)."""
    n = name.encode("mac_roman")
    if not 1 <= len(n) <= 31:
        sys.exit(f"mac_text: the name {name!r} is not 1-31 bytes")
    now = int(time.time()) + 2082844800
    h = bytearray(128)
    h[1] = len(n)
    h[2:2 + len(n)] = n
    h[65:69], h[69:73] = ftype, creator
    struct.pack_into(">IIII", h, 83, len(data), len(rsrc), now, now)
    h[122] = h[123] = 129
    struct.pack_into(">H", h, 124, crc16_xmodem(bytes(h[:124])))
    pad = lambda b: b + b"\0" * (-len(b) % 128)
    return bytes(h) + pad(data) + pad(rsrc)


def verify(mb):
    """What --verify reads back: a list of problems, empty if none."""
    bad = []
    # MacBinary II (byte 122 >= 129) carries a CRC; mkmfs.py --extract
    # writes MacBinary I, which has none.
    if mb[122] >= 129 and crc16_xmodem(mb[:124]) != struct.unpack(">H", mb[124:126])[0]:
        bad.append("MacBinary header CRC")
    dl, rl = struct.unpack(">II", mb[83:91])
    data = mb[128:128 + dl]
    r0 = 128 + (dl + 127) // 128 * 128
    try:
        s = read_resources(mb[r0:r0 + rl]).get((b"styl", 128))
    except (struct.error, IndexError):
        s = None
    if s is None:
        return bad + ["no 'styl' 128"]
    n = struct.unpack(">h", s[:2])[0]
    if n < 1 or len(s) != 2 + 20 * n:
        bad.append(f"'styl' is {len(s)} B for {n} styles")
    last = -1
    for k in range(max(0, min(n, (len(s) - 2) // 20))):
        off, h, a, font, face, fill, size = struct.unpack(">ihhhBBh", s[2 + 20 * k:16 + 20 * k])
        if (k == 0 and off != 0) or off <= last or off >= max(dl, 1):
            bad.append(f"style {k} starts at {off}")
        if METRIC.get((font, size)) != (h, a):
            bad.append(f"style {k}: font {font} size {size} height {h} ascent {a}")
        last = off
    if any(c > 0xD9 or c == 0x0A for c in data):
        bad.append("a byte over 0xD9, or a LF, in the text")
    if dl > LIMIT:
        bad.append(f"{dl} B of text, over {LIMIT}")
    return bad


def selftest():
    """Five broken files, each of which --verify must report."""
    blocks = markdown_blocks(["# Title", "", "Some **bold** and `code`."])
    data, runs = render(blocks, "selftest")
    s = styl(runs)
    mk = lambda d, st: macbinary("t", b"ttro", b"ttxt", d,
                                 resource_fork(b"styl", 128, st) if st else b"")
    if verify(mk(data, s)):
        print("mac_text: selftest: the good file fails:", verify(mk(data, s)))
        return False
    broken = [mk(data, s[:-2]),                                    # cut short
              mk(data, s[:2] + struct.pack(">i", 5) + s[6:]),      # not from 0
              mk(data, s[:6] + struct.pack(">h", 99) + s[8:]),     # wrong height
              mk(data[:-1] + b"\xe1", s),                          # no glyph
              mk(data, None)]                                      # no 'styl'
    caught = sum(bool(verify(b)) for b in broken)
    print(f"mac_text: selftest: {caught} of {len(broken)} broken files caught")
    return caught == len(broken)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--name", help="the name on the Mac (default: the source's)")
    ap.add_argument("--markdown", action="store_true", help="Markdown whatever the extension")
    ap.add_argument("--plain", action="store_true", help="plain text whatever the extension")
    ap.add_argument("--disk", choices=("HFS", "MFS"))
    ap.add_argument("--split", action="store_true", help="cut a text over the limit into parts")
    ap.add_argument("--editable", action="store_true", help="'TEXT', not 'ttro'")
    ap.add_argument("--verify", nargs="+", metavar="MACBINARY")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if a.verify:
        rc = 0
        for p in a.verify:
            bad = verify(open(p, "rb").read())
            print(f"mac_text: {p}: {'; '.join(bad) if bad else 'ok'}")
            rc |= bool(bad)
        sys.exit(rc)
    if not a.src or not a.out:
        ap.error("SRC and -o are needed")
    md = a.markdown or (a.src.lower().endswith(".md") and not a.plain)
    text = open(a.src, encoding="utf-8").read().expandtabs(4)
    blocks = (markdown_blocks if md else plain_blocks)(keep_for_disk(text.split("\n"), a.disk))
    name = a.name or os.path.basename(a.src)
    data, _ = render(blocks, a.src)
    if len(data) <= LIMIT:
        parts = [blocks]
    elif a.split:
        parts = split(blocks, LIMIT, a.src)
    else:
        sys.exit(f"mac_text: {a.src} is {len(data)} B as Mac text, over {LIMIT} "
                 f"(SimpleText refused 31,999, TeachText 32,001); --split cuts it")
    root, ext = os.path.splitext(a.out)
    ftype = b"TEXT" if a.editable else b"ttro"
    for k, part in enumerate(parts, 1):
        data, runs = render(part, a.src)
        rsrc = resource_fork(b"styl", 128, styl(runs))
        mname = name if len(parts) == 1 else "%s (%d of %d)" % (name[:31 - 9], k, len(parts))
        path = a.out if len(parts) == 1 else "%s-%d%s" % (root, k, ext)
        open(path, "wb").write(macbinary(mname, ftype, b"ttxt", data, rsrc))
        print(f"mac_text: {path}: {mname!r}, {len(data)} B of text, "
              f"{len(runs)} styles ({len(rsrc)} B resource fork)")


if __name__ == "__main__":
    main()
