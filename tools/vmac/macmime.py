#!/usr/bin/env python3
"""macmime.py — a MIME message written BY a Macintosh, with mpack's own code.

Every message `src/fmt_mime.c` is graded against was built on Linux by
`tools/run_mime.py` or read on Linux by munpack (TESTING.md, *base64 and
MIME*). The half neither can settle is how a real Macintosh laid out the
`application/applefile` part of a `multipart/appledouble` and what it put in
the Finder-info entry — filed in OPEN_ITEMS.md as waiting on a specimen from
somewhere else.

It was not waiting on anything. mpack's Macintosh port is in
`reference/mpack`, and `encode_applefile()` there is that writer.
`tools/macmime/` compiles it and `encode()` verbatim, adds the host glue THINK
C used to supply, and this harness runs the result on an emulated Mac Plus.

    tools/vmac/macmime.py --make     boot System 6.0.8 and write the message
    tools/vmac/macmime.py --check    grade what came off the disk
    tools/vmac/macmime.py            both

The subject carries a resource fork, a type and creator, and Finder flags, so
every entry of the applefile has something in it to be wrong about.

WHAT THIS CANNOT SEE. The specimen is one message from one encoder: it
establishes what mpack's Macintosh port writes, not what Eudora or Claris
Emailer wrote. It also cannot settle line endings on its own — encode.c writes
"\\n" and THINK C's text mode turned that into CR, which Retro68's newlib does
not do, so `--check` MEASURES what came out and prints it rather than
asserting either (DECISIONS.md 2026-08-29, *a Macintosh wrote a MIME
message*).

License: LGPL-2.1-or-later. See LICENSE and NOTICE.
"""
import argparse
import os
import re
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import run as R                                      # noqa: E402
from interactive import Mac                          # noqa: E402
from arcmac import macbinary                         # noqa: E402
from mkboot import FINDER_OWN                        # noqa: E402

SRC = os.path.join(REPO, "tools", "macmime")
BUILD = os.path.join(REPO, "build", "macmime")
OUT = os.path.join(R.VMAC_HOME, "specimens", "macmime")
SHOTS = os.path.join(OUT, "shots")
SYSFOLDER = "System Folder"

# The subject. Both forks are non-empty and neither is a round number of
# anything, so a length copied from the wrong field shows up; the type and
# creator are real ones so the Finder-info entry has something in it that a
# reader can be wrong about.
DATA = b"A Macintosh wrote this message.\r" * 9 + b"Ends without a newline."
RSRC = b"RESOURCE FORK, on a real HFS volume. " * 11
FTYPE, CREATOR = "TEXT", "ttxt"
# Set on the MAC, by kSubjectFlags in tools/macmime/macmime.c, and not in
# the MacBinary below: `hcopy -m` does not carry the Finder flags onto the
# volume (measured — a MacBinary with byte 73 = 0x01 round-trips as 0x00),
# so a flag asked for here would be zero before the Macintosh saw the file.
FINDER_FLAGS = 0x0100                 # hasBeenInited, the everyday one


def build():
    """Build the Retro68 encoder. Nothing in ci.sh does: it makes one
    specimen, and the specimen is what is graded afterwards."""
    tc = os.environ.get("RETRO68", "/opt/Retro68-build/toolchain")
    cmakefile = os.path.join(tc, "m68k-apple-macos", "cmake",
                             "retro68.toolchain.cmake")
    if not os.path.exists(cmakefile):
        raise SystemExit("macmime: no Retro68 toolchain — set RETRO68")
    subprocess.run(["cmake", "-B", BUILD, "-S", SRC,
                    f"-DCMAKE_TOOLCHAIN_FILE={cmakefile}",
                    "-DCMAKE_BUILD_TYPE=Release"],
                   check=True, capture_output=True)
    subprocess.run(["cmake", "--build", BUILD], check=True, capture_output=True)
    binary = os.path.join(BUILD, "macmime.bin")
    if not os.path.exists(binary):
        raise SystemExit("macmime: the build produced no MacBinary")
    return binary


class HFS:
    """hfsutils against one image, with its own $HOME so a stale .hcwd from
    another run cannot point it at the wrong volume (mkboot.py says why)."""

    def __init__(self, image):
        self.home = tempfile.mkdtemp(prefix="hfs-")
        self.env = dict(os.environ, HOME=self.home)
        out = self.run("hmount", image).stdout
        m = re.search(r'Volume name is "(.*)"', out)
        if not m:
            raise SystemExit(f"macmime: cannot read the volume name of {image}")
        self.vol = m.group(1)

    def run(self, *argv, check=True):
        return subprocess.run(argv, env=self.env, check=check,
                              capture_output=True, text=True,
                              errors="surrogateescape")

    def ls(self, folder="", invisible=True):
        """Names in <folder>, one per line.

        `-a` since 2026-09-23: `hls` hides a file whose Finder INVISIBLE
        bit is set, and this list is compared with what the encoder was
        supposed to write, so an invisible output read as one that was
        never made. `FINDER_OWN` drops what the flag brings with it.

        Read as BYTES and split on b"\n" — not `text=True` + splitlines().
        That decode applies universal newlines, so a carriage return
        INSIDE an HFS name becomes a line break and one name arrives as
        two (measured on `cptsegment.read_volume`, where it broke
        `Icon\r` outright).
        """
        argv = [b"hls"] + ([b"-a"] if invisible else []) + [b"-1"]
        out = subprocess.run(argv + [f"{self.vol}:{folder}".encode("mac_roman")],
                             env=self.env, capture_output=True).stdout
        names = [n.decode("mac_roman", "replace")
                 for n in out.split(b"\n") if n.strip()]
        return [n for n in names if not (invisible and n in FINDER_OWN)]

    def get(self, path, dest):
        self.run("hcopy", "-r", f"{self.vol}:{path}", dest)
        return open(dest, "rb").read()

    def close(self):
        self.run("humount", check=False)


def make(mem="mv-4M", timeout=240.0):
    """Boot straight into the encoder and bring back what it wrote."""
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(SHOTS, exist_ok=True)
    app = build()
    work = tempfile.mkdtemp(prefix="macmime-")

    subject = os.path.join(work, "subject.bin")
    open(subject, "wb").write(macbinary("Subject", FTYPE, CREATOR,
                                        DATA, RSRC))
    open(os.path.join(OUT, "Subject.data"), "wb").write(DATA)
    open(os.path.join(OUT, "Subject.rsrc"), "wb").write(RSRC)

    # Mac() copies whatever it is given to <workdir>/boot.hfv and runs the
    # COPY, so the image built here must not already be that path.
    boot = os.path.join(work, "pristine.hfv")
    stock = os.path.join(R.VMAC_HOME, "System6.hfv")
    if not os.path.exists(stock):
        raise SystemExit("macmime: no System6.hfv — run tools/vmac/setup.sh")
    # No Finder and no mouse: mkboot rewrites the boot blocks' shell name, so
    # the ROM hands control to the encoder itself (mkboot.py). That also puts
    # the application in the BLESSED folder rather than at the root, and the
    # default directory a shell application starts in is its own — so the
    # subject goes there too, and Out.mime comes back from there. Measured:
    # with the subject at the root, PBGetCatInfo answered -43.
    subprocess.run([sys.executable, os.path.join(HERE, "mkboot.py"),
                    stock, app, boot, "--app-name", "macmime",
                    "--macbin", f"{subject}:{SYSFOLDER}:Subject"],
                   check=True, capture_output=True)

    mac = Mac(boot, mem, work)
    try:
        # The encoder finishes in seconds and then sits in an event loop, so
        # there is no state to wait FOR on screen: give it a fixed run and
        # photograph the window, which is the only report a run that died
        # before writing a file can make.
        shot = None
        for i, t in enumerate((40.0, 40.0, 40.0)):
            time.sleep(t)
            p = os.path.join(SHOTS, "%02d-run.png" % (i + 1))
            if mac.dpy.screenshot(p):
                shot = p
    finally:
        mac.close()

    live = os.path.join(work, "boot.hfv")     # the copy the emulator wrote to
    h = HFS(live)
    try:
        names = h.ls(SYSFOLDER)
        print("macmime: the blessed folder holds " + ", ".join(sorted(names)))
        if "Out.mime" not in names:
            raise SystemExit("macmime: no Out.mime on the volume — see "
                             + shot)
        msg = h.get(f"{SYSFOLDER}:Out.mime", os.path.join(OUT, "Out.mime"))
    finally:
        h.close()
    print(f"macmime: {len(msg)} bytes written by the Mac -> "
          f"{os.path.join(OUT, 'Out.mime')}")
    return msg


# ---------------------------------------------------------------- checks

# macfile.c's own entry ids, in its own order.
ENT_DFORK, ENT_RFORK, ENT_NAME, ENT_COMMENT, ENT_DATES, ENT_FINFO = \
    1, 2, 3, 4, 8, 9


def applefile_entries(blob):
    """(magic, version, [(id, offset, length)]) of an AppleSingle/Double."""
    magic, version = struct.unpack(">LL", blob[:8])
    count = struct.unpack(">H", blob[24:26])[0]
    out = []
    for i in range(count):
        off = 26 + i * 12
        out.append(struct.unpack(">LLL", blob[off:off + 12]))
    return magic, version, out


def check():
    path = os.path.join(OUT, "Out.mime")
    if not os.path.exists(path):
        raise SystemExit("macmime: no specimen yet — run --make")
    raw = open(path, "rb").read()
    data = open(os.path.join(OUT, "Subject.data"), "rb").read()
    rsrc = open(os.path.join(OUT, "Subject.rsrc"), "rb").read()
    problems = []

    def check_one(what, ok, detail=""):
        print(("  ok   " if ok else "  FAIL ") + what
              + (("  — " + detail) if detail else ""))
        if not ok:
            problems.append(what)

    # What line endings a Macintosh actually produced. Asserted nowhere:
    # measured and printed, because the answer depends on the C library the
    # port was compiled against and not on the format.
    crlf, cr, lf = raw.count(b"\r\n"), raw.count(b"\r"), raw.count(b"\n")
    print(f"macmime: line endings — CR {cr - crlf}, LF {lf - crlf}, "
          f"CRLF {crlf}")

    text = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    check_one("it is a multipart/appledouble",
              b"multipart/appledouble" in text)
    check_one("the applefile part is declared",
              b"application/applefile" in text)

    # Pull the applefile part out by hand — this is the specimen's own
    # structure, so nothing here may lean on our reader to find it.
    import base64
    m = re.search(rb"Content-Type: application/applefile\n"
                  rb"Content-Transfer-Encoding: base64\n"
                  rb"Content-MD5: (\S+)\n\n(.*?)\n--=", text, re.S)
    check_one("the applefile part is base64 with an MD5", bool(m))
    if m:
        blob = base64.b64decode(m.group(2))
        import hashlib
        check_one("its Content-MD5 is the digest of the part",
                  base64.b64encode(hashlib.md5(blob).digest()).decode()
                  == m.group(1).decode())
        magic, version, entries = applefile_entries(blob)
        check_one("magic is AppleDouble 00051607", magic == 0x00051607,
                  hex(magic))
        check_one("version is 00020000", version == 0x00020000, hex(version))
        ids = {eid: (off, ln) for eid, off, ln in entries}
        want = {ENT_RFORK, ENT_NAME, ENT_COMMENT, ENT_DATES, ENT_FINFO}
        check_one("five entries: name, finder info, dates, comment, rsrc",
                  set(ids) == want, str(sorted(ids)))

        def entry(eid):
            off, ln = ids[eid]
            return blob[off:off + ln]

        if ENT_RFORK in ids:
            check_one("the resource-fork entry is the fork, byte for byte",
                      entry(ENT_RFORK) == rsrc,
                      "%d bytes, wanted %d" % (ids[ENT_RFORK][1], len(rsrc)))
        if ENT_NAME in ids:
            check_one("the name entry is the file's name",
                      entry(ENT_NAME) == b"Subject", repr(entry(ENT_NAME)))
        if ENT_FINFO in ids:
            fi = entry(ENT_FINFO)
            check_one("the Finder-info entry is 32 bytes (FInfo + FXInfo)",
                      len(fi) == 32, str(len(fi)))
            check_one("type and creator are the Finder's",
                      fi[:8] == b"TEXTttxt", repr(fi[:8]))
            if len(fi) >= 10:
                flags = struct.unpack(">H", fi[8:10])[0]
                check_one("the Finder flags survived",
                          flags & FINDER_FLAGS == FINDER_FLAGS, hex(flags))
        if ENT_DATES in ids:
            check_one("the dates entry is four 32-bit dates",
                      ids[ENT_DATES][1] == 16, str(ids[ENT_DATES][1]))
        if ENT_COMMENT in ids:
            # The one field whose layout this project had to guess — see
            # tools/macmime/macmpack.h. A System 6 volume has no Desktop
            # Manager, so the lookup must have failed and the entry must be
            # empty. If it is not, that struct is what to distrust.
            check_one("the comment entry is empty, as System 6 requires",
                      ids[ENT_COMMENT][1] == 0, str(ids[ENT_COMMENT][1]))

    # And the whole point: our reader, over a message no Linux tool made.
    tmp = tempfile.mkdtemp(prefix="macmime-x-")
    cli = os.path.join(REPO, "build", "rel", "macextract")
    r = subprocess.run([cli, "x", path, "-o", tmp], capture_output=True)
    got = {}
    for root, _, files in os.walk(tmp):
        for f in files:
            got[os.path.relpath(os.path.join(root, f), tmp)] = \
                open(os.path.join(root, f), "rb").read()
    check_one("macextract extracts it", r.returncode == 0,
              r.stderr.decode(errors="replace").strip())
    check_one("the data fork comes back byte-exact",
              any(v == data for v in got.values()),
              str({k: len(v) for k, v in got.items()}))
    check_one("the resource fork comes back byte-exact",
              any(v == rsrc for v in got.values()),
              str({k: len(v) for k, v in got.items()}))

    # munpack, the second implementation, over the same file.
    mun = os.path.join(REPO, "build", "mpack", "munpack")
    if os.path.exists(mun):
        d = tempfile.mkdtemp(prefix="macmime-m-")
        subprocess.run([mun, "-f", os.path.abspath(path)], cwd=d,
                       capture_output=True)
        mgot = {f: open(os.path.join(d, f), "rb").read()
                for f in os.listdir(d)}
        check_one("munpack reads it too",
                  any(v == data for v in mgot.values()),
                  str({k: len(v) for k, v in mgot.items()}))

    print("macmime: %d problem(s)" % len(problems))
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--make", action="store_true",
                    help="boot the Mac and write the message")
    ap.add_argument("--check", action="store_true",
                    help="grade the specimen already in specimens/macmime")
    ap.add_argument("--mem", default="mv-4M",
                    help="emulator build (mv-4M, mv-1M)")
    a = ap.parse_args()
    if a.make or not a.check:
        make(mem=a.mem)
    if a.check or not a.make:
        return check()
    return 0


if __name__ == "__main__":
    sys.exit(main())
