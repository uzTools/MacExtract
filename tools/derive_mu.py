#!/usr/bin/env python3
"""derive_mu.py — read the UUTool "MU" layout, and its two alphabets, out
of UUTool.

`src/fmt_uu.c` had one citation left that was not a specification or a
permissively licensed reader: macutils' `hexbin/mu.c`, for the layout
that carries both forks of a Macintosh file through a uuencoded posting
and for `mu_convert()`. **The program that defines the layout was in
this corpus the whole time.** `fixtures/uu-tool-24.hqx` is UUTool, by
Bernie Wieser of Octavian Micro Development, and it carries

  * `DATA` 0 — the literal section headers it writes, `begin 0700
    .rsrc\\r` and `begin 0700 .finfo\\r`, with `end\\r`;
  * `TEXT` 129 (2.3.2) or the "UUTool User Manual" beside the
    application (2.0.4) — the author's own prose: "The data fork of a
    file is the first part in the encoded text file, bounded by a
    'begin' and 'end' statement.  This is followed by the resource
    fork, and finally finder information";
  * `HEXA` 128 "PC" and `HEXA` 129 "UNIX" — its two encode tables, 64
    bytes each.

**The tables are the finding.** UUTool encodes with the standard
alphabet only when "use original coding" is set; by DEFAULT it uses
"UNIX", which moves the low values up past 0x5f so that no value
encodes to a space — because, in the manual's words, "some electronic
mailors reformat white space". Two generations shipped: 2.0.4 moves 30
values to 0x60..0x7d, and 2.1 onwards moves 27, to 0x60..0x7a ("changed
UNIX encoding table to ignore {,}" — its own revision log). Every one
of the three tables satisfies `((c - 0x20) & 0x3f) == value`, which is
why one decoder reads all of them and why the mask in `UU_SIXB` is
load-bearing rather than defensive.

Until 2026-10-06 this engine refused every line of it: the test that
told a data line from a line of mail required each character to be in
0x20..0x60, so the default output of the only program that writes the
MU layout sniffed as "not a uu file at all". Two wild specimens, one
per generation, are fixtures now (`uu-wild-dictcol.uu`,
`uu-wild-terrainman.uu`; DECISIONS.md 2026-10-06, *the alphabet nothing
here had seen*).

`fixtures/uu-parser-172.hqx` — UUParser 1.72, a different author — is
the second implementation: it carries BOTH tables as 64-byte arrays,
each behind a 0x40 length byte.

    tools/derive_mu.py --tables    every alphabet, out of every binary
                                   here that carries one
    tools/derive_mu.py --layout    the section headers and the author's
                                   own statement of the order
    tools/derive_mu.py --grade     this engine over the two wild
                                   specimens, against hexbin where it
                                   can read them
    tools/derive_mu.py --fetch     add UUTool 2.3.2 and 2.0.4 from
                                   Macintosh Garden (the only copies of
                                   the earlier table; not committed)
    tools/derive_mu.py             all three, skipping what is absent

Not in `ci.sh`: it needs fixtures, which are copyrighted and not
committed. What IS in `ci.sh` is `tools/run_uu.py`, which generates both
alphabets with `tools/synth_uu.py` and grades the two wild specimens
whenever they are in `fixtures/`.

License: LGPL-2.1-or-later. See LICENSE and NOTICE.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "sdmodule"))

FIXDIR = os.path.join(ROOT, "fixtures")
CACHE = os.path.join(os.environ.get(
    "UNC_VMAC_HOME", os.path.expanduser("~/.cache/macextract/vmac")), "uutool")

# Macintosh Garden signs its download URLs and answers a bare GET with
# HTTP 418, so the referer is the page (tools/vmac/README.md, *The
# yardstick*). `old.mac.gdn` serves the same bytes by name.
GARDEN_PAGE = "http://macintoshgarden.org/apps/uutool-232"
DOWNLOADS = [
    ("UUTool_232.hqx",
     "http://old.mac.gdn/apps/UUTool_232.hqx",
     "1b8871aef0cf223b33d0693febbc1b3f78fa2dfaa22763543e9e3cd533c820b4"),
    ("UUTool_2.0.4.sea_.sit",
     "http://old.mac.gdn/apps/UUTool_2.0.4.sea_.sit",
     "97659c3bc6db919f218221879e565fa7ab1a5993ffc8c228d0431d97638bc865"),
]

# ---------------------------------------------------------------------------
# Where each binary comes from. The corpus two need no network at all;
# the Garden two are the only copies of the 2.0 table in reach.
#
#   name      what it is
#   source    the file to walk, and how many extraction layers deep the
#             application sits (our own CLI does the walking)
#   app       the resource fork to read, by basename
BINARIES = [
    {"name": "UUTool 2.4", "layers": 1,
     "source": os.path.join(FIXDIR, "uu-tool-24.hqx"), "app": "UUTool-FAT"},
    {"name": "UUParser 1.72", "layers": 1,
     "source": os.path.join(FIXDIR, "uu-parser-172.hqx"),
     "app": "UUParser 1.72"},
    {"name": "UUTool 2.3.2", "layers": 1,
     "source": os.path.join(CACHE, "UUTool_232.hqx"), "app": "UUTool 232"},
    {"name": "UUTool 2.0.4", "layers": 2,
     "source": os.path.join(CACHE, "UUTool_2.0.4.sea_.sit"),
     "app": "UUTool 2.0.4"},
]

# ---------------------------------------------------------------------------
# The alphabets, as the binaries hold them. `shift` is how many low
# values are moved up past the standard range: 0 is the standard
# alphabet itself. Every entry is checked by reading the table out of
# the binary, not by rebuilding it here.
TABLES = {
    "UUTool 2.0.4": [("HEXA", 128, "PC", 0), ("HEXA", 129, "UNIX", 30)],
    "UUTool 2.3.2": [("HEXA", 128, "PC", 0), ("HEXA", 129, "UNIX", 27)],
    "UUTool 2.4":   [("HEXA", 128, "PC", 0), ("HEXA", 129, "UNIX", 27)],
}

# UUParser keeps its two in a code resource rather than in resources of
# their own, each behind a 0x40 length byte, so they are searched for.
PARSER_TABLES = [("the standard alphabet", 0), ("UUTool's UNIX table", 27)]

# ---------------------------------------------------------------------------
# The layout, as the application states it. Every needle below is
# checked where it is claimed to be.
LAYOUT_LITERALS = [
    ("UUTool 2.0.4", "DATA", 0, b"begin 0700 .rsrc\r"),
    ("UUTool 2.0.4", "DATA", 0, b"begin 0700 .finfo\r"),
    ("UUTool 2.0.4", "DATA", 0, b"\x04end\r"),
    ("UUTool 2.3.2", "DATA", 0, b"begin 0700 .rsrc\r"),
    ("UUTool 2.3.2", "DATA", 0, b"begin 0700 .finfo\r"),
    ("UUTool 2.3.2", "DATA", 0, b"\x04end\r"),
    ("UUTool 2.3.2", "DATA", 0, b"\x06begin "),
    # 2.4 patches the mode into the template at run time, so the two
    # characters between "07" and the tag are not filled in in the
    # shipped image. The rest of the line is.
    ("UUTool 2.4", "DATA", 0, b"begin 07"),
    ("UUTool 2.4", "DATA", 0, b" .rsrc\r"),
    ("UUTool 2.4", "DATA", 0, b" .finfo\r"),
]

# The author's prose, and which document it is in. The first is the
# layout; the second is why the default alphabet is not the standard
# one; the third is that the mode is a preference and means nothing to
# a Macintosh, which is what lets the tag sit at a fixed offset 10.
# 0xaa is MacRoman's trademark sign, which is how these documents spell
# "UNIX" — the needles are bytes rather than text for that reason.
MANUAL = [
    b"The data fork of a file is the first part in the encoded text "
    b"file, bounded by a 'begin' and 'end' statement.  This is followed "
    b"by the resource fork, and finally finder information",
    b"I suggest not using original coding when using UNIX\xaa machines, "
    b"since some electronic mailors reformat white space",
    b"UNIX\xaa permission defines the file's permission modes if the "
    b"file is to be decoded on a UNIX\xaa machine.  For example, '0700' "
    b"stands for read/write/execute for owner only.  This is ignored on "
    b"the Mac side.",
]

# The two wild specimens and what grades each.
SPECIMENS = [
    {"fixture": "uu-wild-dictcol.uu",
     "what": "the MU layout, UUTool 2.0's table (0x3e..0x7d), LF endings, "
             "a quoted name and mode 0755 in the first line where the "
             "sections keep the literal 0700",
     "entry": "dictcol-test.tex", "type": "TEXT", "creator": "R*ch",
     "data": 5161, "rsrc": 648, "hexbin": True},
    {"fixture": "uu-wild-terrainman.uu",
     "what": "one section, UUTool 2.1's table (0x3b..0x7a), CR endings and "
             "an unquoted name — the UNIX naming preference, which "
             "replaces what it calls dangerous characters",
     "entry": "Terrainman_2.0.1.sit", "type": None, "creator": None,
     "data": 184340, "rsrc": 0, "hexbin": False,
     # hexbin cannot read this one: its mu() walks to the first '"' in
     # the begin line and there is none. What grades it instead is the
     # StuffIt archive its data fork decodes to — the CRCs are the
     # archive's own, so they adjudicate the uu layer without any
     # second uu implementation at all. The posting on that CD is cut,
     # which is a property of the specimen and is asserted here.
     "inner_forks": 27, "inner_truncated": True},
]


def cli():
    for p in (os.path.join(ROOT, "build", "macextract"),
              os.path.join(ROOT, "build", "san", "macextract"),
              os.path.join(ROOT, "macextract")):
        if os.path.exists(p):
            return p
    return None


def fetch():
    """The two Garden copies, in the FOREGROUND — a backgrounded
    download on this machine stalls in poll() with no error."""
    os.makedirs(CACHE, exist_ok=True)
    for name, url, sha in DOWNLOADS:
        dest = os.path.join(CACHE, name)
        if os.path.exists(dest) and \
                hashlib.sha256(open(dest, "rb").read()).hexdigest() == sha:
            print("derive-mu: have %s" % name)
            continue
        subprocess.run(["curl", "-fsSL", "--max-time", "180",
                        "-e", GARDEN_PAGE, "-o", dest, url], check=True)
        got = hashlib.sha256(open(dest, "rb").read()).hexdigest()
        if got != sha:
            raise SystemExit("derive-mu: %s is sha256 %s, expected %s — a "
                             "different build is a different reading"
                             % (name, got, sha))
        print("derive-mu: fetched %s (%d B)" % (name, os.path.getsize(dest)))
    return 0


def forks():
    """Every application in reach, as {name: resource fork bytes}.

    Each is unwrapped with this project's own CLI, one layer at a time,
    so no format knowledge lives here.
    """
    out = {}
    exe = cli()
    if not exe:
        print("derive-mu: no CLI — build it first")
        return out, {}
    docs = {}
    for b in BINARIES:
        if not os.path.exists(b["source"]):
            continue
        work = tempfile.mkdtemp(prefix="dmu-")
        try:
            subprocess.run([exe, "x", "-o", work, b["source"]],
                           capture_output=True)
            for _ in range(b["layers"] - 1):
                for f in sorted(os.listdir(work)):
                    p = os.path.join(work, f)
                    if os.path.isfile(p) and not f.endswith(".rsrc"):
                        subprocess.run([exe, "x", "-o", work, p],
                                       capture_output=True)
            hit = None
            for dirpath, _d, files in os.walk(work):
                for f in files:
                    if f == b["app"] + ".rsrc":
                        hit = os.path.join(dirpath, f)
            if not hit:
                print("derive-mu: %s carries no %s" % (b["source"], b["app"]))
                continue
            out[b["name"]] = open(hit, "rb").read()
            # Any text beside the application: 2.0.4 ships its manual as
            # a separate file rather than as a resource.
            for dirpath, _d, files in os.walk(work):
                for f in files:
                    if f.endswith(".rsrc") or f == b["app"]:
                        continue
                    blob = open(os.path.join(dirpath, f), "rb").read()
                    if b"UUTool" in blob or b"uuencode" in blob:
                        docs.setdefault(b["name"], []).append((f, blob))
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return out, docs


def resources(fork):
    from run_sdmodule import resource_data
    return resource_data(fork)


def sixb_ok(table):
    """The property that lets one decoder read every alphabet."""
    return all(((c - 0x20) & 0x3f) == v for v, c in enumerate(table))


def spelt(table, shift):
    """Is this the standard alphabet with `shift` low values moved up?"""
    return all(c == (0x60 + v if v < shift else 0x20 + v)
               for v, c in enumerate(table))


def tables(app_forks):
    """Every alphabet, out of every binary, at the resource it sits in."""
    bad = seen = 0
    for name, want in sorted(TABLES.items()):
        if name not in app_forks:
            print("  -- %s: not here (--fetch)" % name)
            continue
        res = resources(app_forks[name])
        for rtype, rid, rname, shift in want:
            blob = next((b for i, n, b in res.get(rtype, [])
                         if i == rid and len(b) == 64), None)
            seen += 1
            if blob is None:
                print("  FAIL %s %s %d: no 64-byte table" % (name, rtype, rid))
                bad += 1
                continue
            ok = spelt(blob, shift) and sixb_ok(blob)
            bad += 0 if ok else 1
            print("  %-4s %-13s %s %d %-6s 0x%02x..0x%02x  %d value(s) moved "
                  "up, (c-0x20)&0x3f %s"
                  % ("ok" if ok else "FAIL", name, rtype, rid, repr(rname),
                     min(blob), max(blob), shift,
                     "reads it" if sixb_ok(blob) else "DOES NOT read it"))

    # UUParser is the second implementation, and it is the one that says
    # the UNIX table is not UUTool's private business.
    if "UUParser 1.72" in app_forks:
        fork = app_forks["UUParser 1.72"]
        for what, shift in PARSER_TABLES:
            want = bytes((0x60 + v if v < shift else 0x20 + v)
                         for v in range(64))
            at = fork.find(b"\x40" + want)
            seen += 1
            if at < 0:
                print("  FAIL UUParser 1.72: no table for %s" % what)
                bad += 1
            else:
                print("  ok   UUParser 1.72  @0x%04x in the resource fork, "
                      "behind a 0x40 length byte: %s" % (at, what))
    else:
        print("  -- UUParser 1.72: fixture absent")

    print("derive-mu: %d of %d alphabet(s) hold" % (seen - bad, seen))
    return 1 if bad else 0


def layout(app_forks, docs):
    """The section headers, where they sit, and the author's own prose."""
    bad = seen = 0
    for name, rtype, rid, needle in LAYOUT_LITERALS:
        if name not in app_forks:
            continue
        res = resources(app_forks[name])
        blob = next((b for i, n, b in res.get(rtype, []) if i == rid), b"")
        at = blob.find(needle)
        seen += 1
        bad += 0 if at >= 0 else 1
        print("  %-4s %-13s %s %d @%s %r"
              % ("ok" if at >= 0 else "FAIL", name, rtype, rid,
                 ("0x%04x" % at) if at >= 0 else "  --  ", needle))

    # The prose. 2.3.2 keeps the manual in `TEXT` 129; 2.0.4 ships it as
    # a file beside the application, which is why both are searched.
    text = []
    for name, fork in app_forks.items():
        for rid, _n, blob in resources(fork).get("TEXT", []):
            text.append((name, "TEXT %d" % rid, blob))
    for name, items in docs.items():
        for f, blob in items:
            text.append((name, f, blob))
    for needle in MANUAL:
        where = [(n, w) for n, w, b in text if needle in b]
        seen += 1
        bad += 0 if where else 1
        shown = needle[:60].decode("mac_roman")
        print("  %-4s %s %r"
              % ("ok" if where else "FAIL",
                 ", ".join("%s %s" % (n, w) for n, w in where) or "nowhere",
                 shown + ("..." if len(needle) > 60 else "")))
    print("derive-mu: %d of %d statement(s) hold" % (seen - bad, seen))
    return 1 if bad else 0


def grade():
    """This engine over the two wild specimens."""
    exe = cli()
    bad = seen = 0
    if not exe:
        print("  -- no CLI — build it first")
        return 0
    for s in SPECIMENS:
        fx = os.path.join(FIXDIR, s["fixture"])
        if not os.path.exists(fx):
            print("  -- %s: absent (fixtures/SOURCES.md)" % s["fixture"])
            continue
        seen += 1
        print("  %s — %s" % (s["fixture"], s["what"]))
        out = tempfile.mkdtemp(prefix="dmu-g-")
        try:
            r = subprocess.run([exe, "x", "-o", out, fx], capture_output=True)
            df = os.path.join(out, s["entry"])
            rf = df + ".rsrc"
            got_d = open(df, "rb").read() if os.path.exists(df) else None
            got_r = open(rf, "rb").read() if os.path.exists(rf) else b""
            if got_d is None or len(got_d) != s["data"] or \
                    len(got_r) != s["rsrc"]:
                print("    FAIL ours: %s data %s rsrc %s (want %d/%d), "
                      "exit %d %s"
                      % (s["entry"], "none" if got_d is None else len(got_d),
                         len(got_r), s["data"], s["rsrc"], r.returncode,
                         r.stderr.decode()[:120]))
                bad += 1
                continue
            print("    ours: %d B data, %d B resource fork" % (len(got_d),
                                                               len(got_r)))
            if s["hexbin"]:
                if not shutil.which("hexbin"):
                    print("    -- no hexbin (tools/build_macunpack.sh); the "
                          "layout is then graded only by this engine")
                else:
                    hb = tempfile.mkdtemp(prefix="dmu-h-")
                    try:
                        subprocess.run(["hexbin", "-f", os.path.abspath(fx)],
                                       cwd=hb, capture_output=True)
                        blobs = {f: open(os.path.join(hb, f), "rb").read()
                                 for f in os.listdir(hb)}
                        same = [f for f, b in blobs.items()
                                if b in (got_d, got_r)]
                        if len(same) < (2 if s["rsrc"] else 1):
                            print("    FAIL hexbin disagrees: %r"
                                  % {f: len(b) for f, b in blobs.items()})
                            bad += 1
                        else:
                            print("    hexbin: the same %d fork(s), byte for "
                                  "byte" % len(same))
                    finally:
                        shutil.rmtree(hb, ignore_errors=True)
            if s.get("inner_forks"):
                inner = tempfile.mkdtemp(prefix="dmu-i-")
                try:
                    ir = subprocess.run([exe, "x", "-o", inner, df],
                                        capture_output=True)
                    n = sum(len(f) for _d, _s, f in os.walk(inner))
                    cut = b"truncated" in ir.stderr
                    ok = n == s["inner_forks"] and cut == s["inner_truncated"]
                    bad += 0 if ok else 1
                    print("    %s the archive it decodes to: %d fork(s) out, "
                          "CRC-checked against its own, and it %s cut"
                          % ("" if ok else "FAIL", n,
                             "IS" if cut else "is NOT"))
                finally:
                    shutil.rmtree(inner, ignore_errors=True)
        finally:
            shutil.rmtree(out, ignore_errors=True)
    print("derive-mu: %d of %d specimen(s) graded clean" % (seen - bad, seen))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true",
                    help="add UUTool 2.3.2 and 2.0.4 from Macintosh Garden")
    ap.add_argument("--tables", action="store_true",
                    help="every alphabet, out of every binary here")
    ap.add_argument("--layout", action="store_true",
                    help="the section headers and the author's own prose")
    ap.add_argument("--grade", action="store_true",
                    help="this engine over the two wild specimens")
    a = ap.parse_args()

    if a.fetch:
        return fetch()
    rc = 0
    app_forks, docs = forks()
    print("derive-mu: read %d binar%s: %s"
          % (len(app_forks), "y" if len(app_forks) == 1 else "ies",
             ", ".join(sorted(app_forks)) or "none"))
    if a.tables or not (a.layout or a.grade):
        print("derive-mu: the alphabets")
        rc |= tables(app_forks)
    if a.layout or not (a.tables or a.grade):
        print("derive-mu: the layout")
        rc |= layout(app_forks, docs)
    if a.grade or not (a.tables or a.layout):
        print("derive-mu: the specimens")
        rc |= grade()
    return rc


if __name__ == "__main__":
    sys.exit(main())
