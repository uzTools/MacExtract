#!/usr/bin/env python3
"""maccompress.py — make a MacCompress file with MacCompress, and read it.

MacCompress 3.2 (Lloyd Chambers, May 1989) compresses a file in place, both
forks, and stamps it `ZIVM`/`LZIV`. MacStamp kept the 48-byte head of one it
wrote (its DECISIONS.md 2026-10-14) and that head is field for field the
1990 DiskDoubler header `src/fmt_dd.c` reads (`ab cd 00 30`), which
OPEN_ITEMS.md held as a hypothesis: that this engine already extracts
MacCompress's own format. The program's help says the same in its author's
words — TEXT 310, *MacCompress Format*: "the file can grow by 48 bytes;
forks are copied if they cannot be compressed, but the header is always
used", and the format "is compatible with Unix compress provided the header
is stripped from the file, and the file is split into two files". This
asks the program itself.

    maccompress.py --fetch   download maccompress-32.hqx (Discmaster), check it
    maccompress.py --setup   the application and a two-fork subject on a volume
    maccompress.py --make    boot System 6, compress the subject, read it back
    maccompress.py --check   extract what MacCompress wrote with our CLI

The subject's DATA fork is incompressible on purpose (bytes from a fixed
SHA-256 chain), so MacCompress copies it, and its RESOURCE fork is a small
real resource fork that compresses: one file reaches both of the two ways
the help describes. It is named `Alpha` so that it sorts ahead of the
application in the Standard File list, where the first entry is selected
when the dialog opens: File ▸ Compress File… is ⌘K, and Return takes it.

Specimens land in `$UNC_VMAC_HOME/specimens/maccompress/`. The application
is freeware and is not committed (CLAUDE.md, *Rules*).

What it cannot see: MacCompress's other format (*Unix compress*, a data
fork plus a `ZIVH` resource), which is an ordinary `.Z` this engine reads
already; the Bits setting other than the default 16; and folder
compression.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import arcmac as A                                  # noqa: E402

HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
SPECIMENS = os.path.join(HOME, "specimens", "maccompress")
HQX = os.path.join(SPECIMENS, "maccompress-32.hqx")
# Discmaster's copy of the ftp.uni-potsdam.de mirror's file; the posting's
# own header reads "MacCompress v3.2 by Lloyd Chambers", 6 May 1989.
URL = ("https://discmaster.textfiles.com/file/11960/ftp.uni-potsdam.de.zip/"
       "ftp.uni-potsdam.de/ftp.uni-potsdam.de/Compress-Translate.zip/"
       "Compress-Translate/maccompress-32.hqx")
SHA1 = "782eeb9278af8f70eb33cbfc821cc816b99925e2"

SUBJECT_NAME = "Alpha"


def subject_data():
    out, h = b"", b"MacCompress copies a fork it cannot shrink"
    while len(out) < 3000:
        h = hashlib.sha256(h).digest()
        out += h
    return out[:3000]


SUBJECT_RSRC = A.make_rsrc(b"\x1dMacCompress fork-method test")


def sha1(path):
    return hashlib.sha1(open(path, "rb").read()).hexdigest()


def fetch():
    os.makedirs(SPECIMENS, exist_ok=True)
    if os.path.exists(HQX) and sha1(HQX) == SHA1:
        print("maccompress: have %s" % HQX)
        return
    parts = urllib.parse.urlsplit(URL)
    url = urllib.parse.urlunsplit(parts._replace(
        path=urllib.parse.quote(parts.path)))
    r = subprocess.run(["curl", "-sS", "-m", "120", "-A", "Mozilla/5.0",
                        "-o", HQX, url], capture_output=True, text=True)
    if r.returncode or sha1(HQX) != SHA1:
        raise SystemExit("maccompress: fetch failed or SHA-1 differs (%s)"
                         % (r.stderr.strip() or sha1(HQX)))
    print("maccompress: fetched %s, SHA-1 %s" % (HQX, SHA1))


def setup():
    if not os.path.exists(HQX):
        fetch()
    work = tempfile.mkdtemp(prefix="maccompress-")
    try:
        out = os.path.join(work, "out")
        os.makedirs(out)
        r = subprocess.run([A.cli(), "x", "--forks", "hidden", "-o", out,
                            HQX], capture_output=True)
        if r.returncode:
            raise SystemExit("maccompress: cannot extract the application: "
                             "%s" % r.stderr.decode()[:200])
        name = "MacCompress3.2"
        data = open(os.path.join(out, name), "rb").read()
        rsrc = open(os.path.join(out, "._" + name), "rb").read()
        appbin = os.path.join(work, "app.bin")
        open(appbin, "wb").write(A.macbinary(name, "APPL", "LZIV", data, rsrc))
        subj = os.path.join(work, "subject.bin")
        open(subj, "wb").write(A.macbinary(SUBJECT_NAME, "TEXT", "ttxt",
                                           subject_data(), SUBJECT_RSRC))
        img = os.path.join(SPECIMENS, "volume.img")
        A.make_volume(img, "Comp", [appbin, subj])
        open(os.path.join(SPECIMENS, "in-data"), "wb").write(subject_data())
        open(os.path.join(SPECIMENS, "in-rsrc"), "wb").write(SUBJECT_RSRC)
        print("maccompress: volume ready (%s); subject data %d B, rsrc %d B"
              % (img, len(subject_data()), len(SUBJECT_RSRC)))
        return img
    finally:
        shutil.rmtree(work, ignore_errors=True)


def make(system="System6.hfv", mem="mv-4M"):
    img = os.path.join(SPECIMENS, "volume.img")
    setup()
    s = A.Session(os.path.join(HOME, system), [img],
                  os.path.join(SPECIMENS, "shots"), mem=mem)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(470, 110, double=True)           # open the volume
        s.shot("volume", wait=8.0)
        # The second icon: `Alpha` sorts first and takes the first slot,
        # where MacLHA's application sat (02-volume.png).
        s.mac.click(172, 105, double=True)           # launch MacCompress
        s.shot("launched", wait=25.0)
        s.mac.command_key("k")                       # File ▸ Compress File…
        s.shot("compress-dialog", wait=6.0)
        s.mac.key("Return")                          # the first entry
        s.shot("compressed", wait=30.0)
        s.mac.command_key("q")                       # File ▸ Quit
        s.shot("quit", wait=15.0)
        # Shut Down, not SIGKILL: Mini vMac flushes a volume only when it
        # is ejected (arcmac.Session.shutdown).
        s.shutdown()
        s.shot("off", wait=25.0)
    finally:
        time.sleep(5)
        s.close()
    got = A.read_volume(img, os.path.join(SPECIMENS, "readback"))
    for name, (typ, crt, data, rsrc) in sorted(got.items()):
        print("  %-16s %s/%s  data %6d  rsrc %6d  head %s"
              % (name, typ, crt, len(data), len(rsrc), data[:4].hex()))
        if name == SUBJECT_NAME:
            open(os.path.join(SPECIMENS, "Alpha.mcz"), "wb").write(data)
            open(os.path.join(SPECIMENS, "Alpha.mcz.rsrc"), "wb").write(rsrc)
    return got


def check():
    spec = os.path.join(SPECIMENS, "Alpha.mcz")
    if not os.path.exists(spec):
        raise SystemExit("maccompress: no specimen — run --make first")
    want_d = open(os.path.join(SPECIMENS, "in-data"), "rb").read()
    want_r = open(os.path.join(SPECIMENS, "in-rsrc"), "rb").read()
    b = open(spec, "rb").read()
    print("maccompress: specimen %d B, head %s, header size %d, methods %d/%d,"
          " info1 0x%02x, type %s/%s"
          % (len(b), b[:4].hex(), b[2] << 8 | b[3], b[20], b[21], b[22],
             b[32:36].decode("mac-roman"), b[36:40].decode("mac-roman")))
    sn = subprocess.run([A.cli(), "sniff", spec], capture_output=True,
                        text=True)
    print("maccompress: sniff says %r" % sn.stdout.strip())
    out = tempfile.mkdtemp(prefix="maccompress-out-")
    try:
        r = subprocess.run([A.cli(), "x", "-nr", "--forks", "hidden",
                            "-o", out, spec], capture_output=True)
        files = sorted(os.listdir(out))
        data = [f for f in files if not f.startswith("._")]
        gd = open(os.path.join(out, data[0]), "rb").read() if data else b""
        rs = os.path.join(out, "._" + data[0]) if data else ""
        gr = open(rs, "rb").read() if rs and os.path.exists(rs) else b""
        ok = r.returncode == 0 and gd == want_d and gr == want_r
        print("maccompress: %s — data %d/%d, rsrc %d/%d, files %s%s"
              % ("OK" if ok else "MISMATCH", len(gd), len(want_d), len(gr),
                 len(want_r), files,
                 "" if r.returncode == 0
                 else "  (" + r.stderr.decode()[:120].strip() + ")"))
        return 0 if ok else 1
    finally:
        shutil.rmtree(out, ignore_errors=True)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    for f in ("fetch", "setup", "make", "check"):
        g.add_argument("--" + f, action="store_true")
    a = p.parse_args()
    if a.fetch:
        fetch()
    elif a.setup:
        setup()
    elif a.make:
        make()
    else:
        sys.exit(check())


if __name__ == "__main__":
    main()
