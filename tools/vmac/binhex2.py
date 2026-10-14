#!/usr/bin/env python3
"""binhex2.py — make `.hex` and `.hcx` files with Yves Lempereur's BinHex 2.0.

BinHex 2.0 (1984) writes both pre-4.0 encodings: four bits a character
behind `***CHECKSUM:`, and six bits a character behind `***COMPRESSED`
and `***CRC:` — every one of those markers is a string in its own code.
The wild files this project holds are `.hcx` only, so this makes the
`.hex` half, and a `.hcx` from known input, on an emulated Mac.

    binhex2.py --setup      build the volume (BinHex 2.0 + a two-fork subject)
    binhex2.py --explore    boot, launch, photograph each menu
    binhex2.py --make       boot, drive BinHex 2.0, read its output back
    binhex2.py --check      decode what came back with our CLI, against the input

The encoder is `binhex_2.0.bin` from Macintosh Repository (id 1799,
SHA-1 below, not committed); fetch it by hand into `$UNC_VMAC_HOME/
specimens/binhex2/` — the site serves one guest download per ten minutes
behind a form. Specimens and screenshots land beside it.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import arcmac as A                                  # noqa: E402

HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
SPECIMENS = os.path.join(HOME, "specimens", "binhex2")
ENCODER = os.path.join(SPECIMENS, "binhex_2.0.bin")
ENCODER_SHA1 = "8c074b758d9daad345a9531598c4dcb409a0b435"

SUBJECT_NAME = "TwoForks"
SUBJECT_DATA = (b"THIS IS THE DATA FORK of a BinHex 2.0 specimen.\r" * 40
                + bytes(range(256)))
SUBJECT_RSRC = A.make_rsrc(b"\x18BinHex 2.0 fork test....")
# Not TEXT: BinHex 2.0 has a "TEXT filter" item, checked by default.
SUBJECT_TYPE, SUBJECT_CREATOR = "Junk", "Test"


def setup():
    os.makedirs(SPECIMENS, exist_ok=True)
    if not os.path.exists(ENCODER):
        raise SystemExit("binhex2: no %s (see the docstring)" % ENCODER)
    got = hashlib.sha1(open(ENCODER, "rb").read()).hexdigest()
    if got != ENCODER_SHA1:
        raise SystemExit("binhex2: %s has SHA-1 %s" % (ENCODER, got))
    work = tempfile.mkdtemp(prefix="binhex2-")
    try:
        # Re-wrapped from its forks with zeroed Finder info: hcopy -m
        # refuses the download's own MacBinary I header as it stands.
        b = open(ENCODER, "rb").read()
        dlen = int.from_bytes(b[83:87], "big")
        rlen = int.from_bytes(b[87:91], "big")
        roff = 128 + (dlen + 127) // 128 * 128
        app = os.path.join(work, "app.bin")
        open(app, "wb").write(A.macbinary("BinHex 2.0", "APPL", "BNHX",
                                          b[128:128 + dlen],
                                          b[roff:roff + rlen]))
        subj = os.path.join(work, "subject.bin")
        open(subj, "wb").write(A.macbinary(SUBJECT_NAME, SUBJECT_TYPE, SUBJECT_CREATOR,
                                           SUBJECT_DATA, SUBJECT_RSRC))
        img = os.path.join(SPECIMENS, "volume.img")
        A.make_volume(img, "Hex", [app, subj])
        open(os.path.join(SPECIMENS, "in-data"), "wb").write(SUBJECT_DATA)
        open(os.path.join(SPECIMENS, "in-rsrc"), "wb").write(SUBJECT_RSRC)
        print("binhex2: volume ready (%s)" % img)
        return img
    finally:
        shutil.rmtree(work, ignore_errors=True)


def session(system):
    img = os.path.join(SPECIMENS, "volume.img")
    if not os.path.exists(img):
        setup()
    return A.Session(os.path.join(HOME, system), [img],
                     os.path.join(SPECIMENS, "shots"))


def pull(s, x, tag):
    """Hold a menu open long enough to photograph it, then let go."""
    ox, oy = s.mac.origin()
    xd = s.mac._xdo
    xd("mousemove", str(ox + x), str(oy + 8))
    time.sleep(0.4)
    xd("mousedown", "1")
    time.sleep(1.5)
    s.shot("menu-%d" % x)
    xd("mousemove", str(ox + x), str(oy + 8))
    time.sleep(0.5)
    xd("mouseup", "1")
    time.sleep(1.0)


def explore(system):
    s = session(system)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(470, 110, double=True)           # open the volume
        s.shot("volume", wait=8.0)
        s.mac.click(117, 102, double=True)           # launch BinHex 2.0
        s.shot("launched", wait=15.0)
        s.menu(42, 27, "encode")                     # Application -> Upload
        s.shot("sfget", wait=5.0)
        s.mac.click(122, 150, double=True)           # TwoForks
        s.shot("after-open", wait=6.0)
    finally:
        time.sleep(3)
        s.close()


def encode(s, name, row=150):
    """File > Application -> Upload, the file at ROW, and save as NAME.

    Standard File lists the volume by name — BinHex 2.0, Desktop,
    TwoForks, then what this writes, every name chosen to sort after
    TwoForks so that its row (y=150) does not move; XF.hcx is at 166."""
    s.menu(42, 27, "encode-" + name)
    s.shot("sfget-" + name, wait=5.0)
    s.mac.click(122, row, double=True)
    s.shot("sfput-" + name, wait=6.0)
    s.mac._xdo("type", "--delay", "150", name)
    s.shot("named-" + name, wait=1.0)
    s.mac.key("Return")
    s.shot("done-" + name, wait=25.0)
    s.mac.key("Return")                              # "...has been completed!"
    s.shot("dismissed-" + name, wait=3.0)


def make(system):
    """Write the subject compressed (.hcx), then uncompressed (.hex), then
    uncompressed with line feeds, then that .hcx as a .hex (one encoding
    inside the other), and read them back off the disk."""
    setup()                       # a fresh volume: a killed run damages it
    s = session(system)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(470, 110, double=True)           # open the volume
        s.shot("volume", wait=8.0)
        s.mac.click(117, 102, double=True)           # launch BinHex 2.0
        s.shot("launched", wait=15.0)
        encode(s, "XF.hcx")                          # Compressed is checked
        s.menu(42, 107, "uncompressed")              # uncheck Compressed
        encode(s, "XF.hex")
        s.menu(42, 123, "linefeeds")                 # check Send line feeds
        encode(s, "XFlf.hex")
        encode(s, "YN.hex", row=166)                 # XF.hcx, inside a .hex
        pull(s, 42, "menu-state")
        s.mac.command_key("q")
        s.shot("quit", wait=10.0)
        s.shutdown()
        s.shot("off", wait=25.0)
    finally:
        time.sleep(5)
        s.close()
    img = os.path.join(SPECIMENS, "volume.img")
    got = A.read_volume(img, os.path.join(SPECIMENS, "readback"))
    for name, (typ, crt, data, rsrc) in sorted(got.items()):
        print("  %-20s %s/%s  data %7d  rsrc %7d"
              % (name, typ, crt, len(data), len(rsrc)))
        if name.lower().endswith((".hex", ".hcx")):
            open(os.path.join(SPECIMENS, name), "wb").write(data)
    return got


def check():
    """Every file this wrote, through our CLI: the subject's forks must come
    back, and YN.hex must come back as XF.hcx and then as the subject."""
    cli = A.cli()
    want = (open(os.path.join(SPECIMENS, "in-data"), "rb").read(),
            open(os.path.join(SPECIMENS, "in-rsrc"), "rb").read())
    bad = 0
    for name in ("XF.hcx", "XF.hex", "XFlf.hex", "YN.hex"):
        out = tempfile.mkdtemp(prefix="binhex2-out-")
        try:
            # Without -nr: YN.hex is unwrapped twice, to the subject.
            r = subprocess.run([cli, "x", "--forks", "hidden", "-o", out,
                                os.path.join(SPECIMENS, name)],
                               capture_output=True)
            got = []
            for f in sorted(os.listdir(out)):
                if not f.startswith("._"):
                    p = os.path.join(out, f)
                    rp = os.path.join(out, "._" + f)
                    got.append((open(p, "rb").read(),
                                open(rp, "rb").read()
                                if os.path.exists(rp) else b""))
            ok = r.returncode == 0 and got == [want]
            print("  %-10s %s" % (name, "OK" if ok else "MISMATCH %r"
                                  % (r.stderr.decode()[:80],)))
            bad += 0 if ok else 1
        finally:
            shutil.rmtree(out, ignore_errors=True)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--explore", action="store_true")
    ap.add_argument("--make", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--system", default="System6.hfv")
    a = ap.parse_args()
    if a.setup:
        setup()
    if a.explore:
        explore(a.system)
    if a.make:
        make(a.system)
    if a.check:
        return 1 if check() else 0
    if not (a.setup or a.explore or a.make or a.check):
        print(__doc__.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
