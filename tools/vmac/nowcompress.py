#!/usr/bin/env python3
"""nowcompress.py — make Now Compress archives with Now Compress.

Three of the five block shapes had no real archive anywhere: the corpus's
two specimens are "new" LZSS and one Huffman-only block (FORMATS.md ✧), a
name search over 49,000 files on two mirrors found no `.now` at all, and
the shapes could only be checked against XADMaster — the implementation
`fmt_now.c` was transcribed from. So the specimens are made here, by the
encoder that defined the format, exactly as `cptsegment.py` derives a
segmented Compact Pro set.

The compressor is **Now QuickFiler**, the Now Utilities 5 component whose
menu has Compress ▸ Faster/Smaller and Archive ▸ Faster/Smaller. It is
commercial software and is NOT redistributed here: this fetches Macintosh
Garden's Now Utilities 5.0.1 installer image by URL, like the ROM and the
System images, and runs it in demo mode (the installer offers a one-week
demo; no serial number is invented). Nothing from it is committed.

    nowcompress.py --setup      fetch + convert the image, install QuickFiler
    nowcompress.py --case all   run every case, write the specimens
    nowcompress.py --verify     decode each specimen and report its blocks

Specimens land in `$UNC_VMAC_HOME/specimens/now/`, beside the emulator
rather than under `build/`, which `make clean` removes.

**What the encoder writes, measured 2026-08-16** (`--verify` prints it):

| what                          | block flags | shape             |
|-------------------------------|-------------|-------------------|
| Compress ▸ Faster             | 0x10        | LZSS only         |
| Compress ▸ Smaller, text      | 0x1f        | LZSS only         |
| Compress ▸ Smaller, mixed     | 0x3f        | Huffman then LZSS |
| Compress ▸ Smaller, random    | 0x00        | stored            |
| Archive ▸ Smaller (a .sea)    | 0x100/0x140 | stored / new LZSS |

so every shape but Huffman-only — which the corpus's 1993 fixture has —
now exists as real bytes, and our decoder returns the input byte for byte
on all of them. `unar` agrees on every specimen here, which is what makes
them worth keeping: the reading is confirmed against the ENCODER and the
reference at once.

Two things the encoder does that no reading of the reference would tell
you: it REFUSES a wholly incompressible file ("2 file(s) are special
uncompressible files") rather than storing it, so a stored block only
appears inside a file that is compressible somewhere else; and a stored
block carries flag bit 0x100, which no decoder here or in XADMaster
looks at.
"""
import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import run as R                                     # noqa: E402
from interactive import Mac                         # noqa: E402

# Now Utilities 5.0.1, from Macintosh Garden. Commercial software, kept
# out of the repository exactly like the ROM: fetched by URL, checked by
# hash, and used in the demo mode its own installer offers.
NU_URL = "https://old.mac.gdn/apps/Now_Utilitiestm_5.0.1.img_.sit"
NU_MD5 = "50e7fdf62ff3c724a451badff17d75df"

HOME = R.VMAC_HOME
WORK = os.path.join(HOME, "nowcompress")
SPECIMENS = os.path.join(HOME, "specimens", "now")
RAW = os.path.join(WORK, "nu501.img")          # the installer disk, raw HFS
BOOT = os.path.join(WORK, "nu5boot.hfv")       # System 7 + QuickFiler

# Menu geometry, all read off screenshots and all verified by the
# screenshots this script keeps: the QuickFiler menu is the icon at the
# right of Special, its Compress and Archive items open submenus to the
# LEFT because the menu sits against the screen edge.
QF_MENU_X = 281
ITEM_ARCHIVE_Y = 219
ITEM_COMPRESS_Y = 285
SUB_X = 225
SUB_FASTER_Y = {"archive": 225, "compress": 291}
SUB_SMALLER_Y = {"archive": 239, "compress": 305}


def keystream(n, seed=b"unclassic-now"):
    """Incompressible bytes that are the same on every run."""
    out, block = bytearray(), seed
    while len(out) < n:
        block = hashlib.sha256(block).digest()
        out += block
    return bytes(out[:n])


# ------------------------------------------------------------------
# The installer image: NDIF, compressed with ADC
# ------------------------------------------------------------------

def adc_decompress(src, want):
    """Apple Data Compression, the algorithm NDIF chunks use.
    0x80+ is a literal run, 0x40-0x7f a 3-byte match, below that a
    2-byte match."""
    out = bytearray()
    i = 0
    while i < len(src) and len(out) < want:
        b = src[i]
        i += 1
        if b & 0x80:
            n = (b & 0x7F) + 1
            out += src[i:i + n]
            i += n
        elif b & 0x40:
            n = (b & 0x3F) + 4
            off = struct.unpack(">H", src[i:i + 2])[0] + 1
            i += 2
            for _ in range(n):
                out.append(out[-off])
        else:
            n = ((b & 0x3F) >> 2) + 3
            off = ((b & 0x03) << 8 | src[i]) + 1
            i += 1
            for _ in range(n):
                out.append(out[-off])
    return bytes(out)


def ndif_to_raw(datafork, rsrcfork, out):
    """Rebuild a raw HFS volume from an NDIF image.

    The chunk table lives in the 'bcem' resource and was derived from this
    one specimen — Apple never documented it. Every step is checked
    against something the file states independently: the chunk starts run
    to 2880 sectors (the 'vers' resource says "1440K image"), the
    compressed offsets and lengths chain exactly onto the data fork's
    length, and each chunk must decompress to exactly the sector count the
    next chunk's start implies. The real check is that the result mounts.

      entry: u32 (start sector << 8 | type), u32 offset, u32 length
      type 0x83 = ADC, 0x02 = stored, 0xff = end
    """
    data = open(datafork, "rb").read()
    bcem = _resource(open(rsrcfork, "rb").read(), b"bcem")
    if bcem is None:
        raise SystemExit("nowcompress: no 'bcem' resource — not an NDIF image")
    at = bcem.find(b"\x00\x00\x00\x83")
    entries = []
    while at + 12 <= len(bcem):
        first, off, ln = struct.unpack(">III", bcem[at:at + 12])
        entries.append((first >> 8, first & 0xFF, off, ln))
        at += 12
        if first & 0xFF == 0xFF:
            break
    blob = bytearray()
    for i, (sector, typ, off, ln) in enumerate(entries):
        if typ == 0xFF:
            break
        want = (entries[i + 1][0] - sector) * 512
        chunk = data[off:off + ln]
        got = adc_decompress(chunk, want) if typ == 0x83 else chunk
        if len(got) != want:
            raise SystemExit("nowcompress: chunk at sector %d gave %d bytes, "
                             "not %d" % (sector, len(got), want))
        blob += got
    with open(out, "wb") as f:
        f.write(bytes(blob))
    return len(blob)


def _resource(rsrc, want_type):
    """The first resource of a type, out of a raw resource fork."""
    doff, moff, dlen, mlen = struct.unpack(">IIII", rsrc[:16])
    tloff = struct.unpack(">H", rsrc[moff + 24:moff + 26])[0]
    ntypes = struct.unpack(">H", rsrc[moff + tloff:moff + tloff + 2])[0] + 1
    for t in range(ntypes):
        e = moff + tloff + 2 + 8 * t
        if rsrc[e:e + 4] != want_type:
            continue
        roff = struct.unpack(">H", rsrc[e + 6:e + 8])[0]
        r = moff + tloff + roff
        dataoff = struct.unpack(">I", b"\0" + rsrc[r + 5:r + 8])[0]
        ln = struct.unpack(">I", rsrc[doff + dataoff:doff + dataoff + 4])[0]
        return rsrc[doff + dataoff + 4:doff + dataoff + 4 + ln]
    return None


def cli():
    for build in ("rel", "san", ""):
        p = os.path.join(REPO, "build", build, "unclassic")
        if os.path.exists(p):
            return p
    raise SystemExit("nowcompress: build the CLI first (make)")


def fetch_installer():
    """Download the Now Utilities image and unstuff it. Not committed and
    not redistributed: the URL and the hash are what this repository
    keeps."""
    os.makedirs(WORK, exist_ok=True)
    sit = os.path.join(WORK, "nu501.sit")
    if not os.path.exists(sit):
        subprocess.run(["curl", "-sL", "-A", "Mozilla/5.0 (Macintosh)",
                        "-e", "https://macintoshgarden.org/apps/now-utilities-50",
                        "-o", sit, NU_URL], check=True)
    got = hashlib.md5(open(sit, "rb").read()).hexdigest()
    if got != NU_MD5:
        raise SystemExit("nowcompress: %s has md5 %s, expected %s"
                         % (sit, got, NU_MD5))
    out = os.path.join(WORK, "unstuffed")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    subprocess.run([cli(), "x", "--forks", "hidden", "-o", out, sit],
                   check=True, capture_output=True)
    img = rsrc = None
    for name in os.listdir(out):
        if name.startswith("._"):
            rsrc = os.path.join(out, name)
        else:
            img = os.path.join(out, name)
    if not img or not rsrc:
        raise SystemExit("nowcompress: the .sit did not yield an image + fork")
    n = ndif_to_raw(img, rsrc, RAW)
    print("nowcompress: %s (%d bytes) — mount it to check" % (RAW, n))


# ------------------------------------------------------------------
# Driving the Mac
# ------------------------------------------------------------------

class Session:
    """A booted Mac with screenshots kept per step."""

    def __init__(self, boot, extra, shots, mem="mv-4M"):
        self.work = tempfile.mkdtemp(prefix="nowcompress-")
        self.shots = shots
        os.makedirs(shots, exist_ok=True)
        self.n = 0
        self.mac = Mac(boot, mem, self.work, extra=tuple(extra))

    def shot(self, tag, wait=2.0):
        """Screenshot WITHOUT parking the pointer: parking closes a menu
        that is being held open, which is how the first attempt at this
        photographed an empty desktop every time."""
        time.sleep(wait)
        self.n += 1
        p = os.path.join(self.shots, "%02d-%s.png" % (self.n, tag))
        for _ in range(30):
            if self.mac.dpy.screenshot(p):
                return p
            time.sleep(0.4)
        raise SystemExit("nowcompress: no screenshot")

    def boot(self):
        self.mac.settle(os.path.join(self.work, "s.png"), interval=8.0,
                        timeout=420.0, stable=3)

    def demo(self):
        """Now Utilities asks for a serial number at first boot and offers
        a one-week demo instead. The demo is what this uses."""
        self.mac.click(237, 306)
        time.sleep(15)
        self.mac.key("Return")
        time.sleep(8)

    def menu(self, item_y, sub_y, tag):
        """Pull the QuickFiler menu down and release on a submenu item."""
        ox, oy = self.mac.origin()
        x = self.mac._xdo
        x("mousemove", str(ox + QF_MENU_X), str(oy + 8))
        time.sleep(0.4)
        x("mousedown", "1")
        time.sleep(1.0)
        x("mousemove", str(ox + 330), str(oy + item_y))
        time.sleep(1.8)
        x("mousemove", str(ox + SUB_X), str(oy + sub_y))
        time.sleep(1.2)
        self.shot(tag)
        x("mouseup", "1")
        time.sleep(2.0)

    def close(self):
        self.mac.close()


def make_volume(path, volname, files, folders=()):
    open(path, "wb").truncate(1400 * 1024)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="nowvol-")
    try:
        subprocess.run(["hformat", "-l", volname, path], check=True,
                       capture_output=True, env=env)
        subprocess.run(["hmount", path], check=True, capture_output=True, env=env)
        for name, blob in files.items():
            p = os.path.join(tmp, name)
            open(p, "wb").write(blob)
            subprocess.run(["hcopy", "-r", p, "%s:%s" % (volname, name)],
                           check=True, capture_output=True, env=env)
        for folder, inner in folders:
            subprocess.run(["hmkdir", "%s:%s" % (volname, folder)], check=True,
                           capture_output=True, env=env)
            for name, blob in inner.items():
                p = os.path.join(tmp, name)
                open(p, "wb").write(blob)
                subprocess.run(["hcopy", "-r", p,
                                "%s:%s:%s" % (volname, folder, name)],
                               check=True, capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)


def read_volume(img, out):
    """Pull every file off the volume as MacBinary, then split out the
    data fork — which is where a Now Compress archive lives, in a
    compressed file and in a self-extracting one alike."""
    os.makedirs(out, exist_ok=True)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    got = {}
    try:
        subprocess.run(["hmount", img], check=True, capture_output=True, env=env)
        listing = subprocess.run(["hls", "-1"], capture_output=True,
                                 env=env).stdout.decode("mac-roman", "replace")
        for name in [n for n in listing.split("\n") if n.strip()]:
            mb = os.path.join(out, name + ".bin")
            r = subprocess.run(["hcopy", "-m", name, mb], capture_output=True,
                               env=env)
            if r.returncode != 0 or not os.path.exists(mb):
                continue
            blob = open(mb, "rb").read()
            dlen = struct.unpack(">I", blob[0x53:0x57])[0]
            typ = blob[65:69].decode("mac-roman")
            crt = blob[69:73].decode("mac-roman")
            dat = os.path.join(out, name + ".dat")
            open(dat, "wb").write(blob[128:128 + dlen])
            got[name] = (typ, crt, dlen, dat)
        subprocess.run(["humount"], capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    return got


CASES = {
    # name: (files on the volume, what to do, which mode)
    "faster": (lambda: {"prose.txt": PROSE, "runs.bin": RUNS},
               "compress", "faster"),
    "smaller": (lambda: {"prose.txt": PROSE, "runs.bin": RUNS,
                         "half.bin": keystream(8000) + b"A" * 8000},
                "compress", "smaller"),
    "stored": (lambda: {"mixed.bin": keystream(33000) + FOX * 800},
               "compress", "smaller"),
    "archive": (lambda: {"mixed.bin": keystream(33000) + FOX * 800,
                         "one.txt": b"first file, compressible\n" * 300},
                "archive", "smaller"),
}
PROSE = (b"Now Compress was Now Software's, and it shipped with Now "
         b"Utilities. It compresses a fork at a time, in blocks.\n" * 60)
RUNS = b"".join(bytes([0x41 + (i % 5)]) * 37 for i in range(200))
FOX = b"the quick brown fox\n"


def run_case(name):
    files, action, mode = CASES[name]
    files = files()
    dest = os.path.join(SPECIMENS, name)
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    img = os.path.join(dest, "volume.img")
    make_volume(img, "Now", files)
    for n, blob in files.items():
        open(os.path.join(dest, "in-" + n), "wb").write(blob)
    s = Session(BOOT, [img], os.path.join(dest, "shots"))
    try:
        s.boot()
        s.demo()
        s.mac.click(470, 110, double=True)          # open the volume
        time.sleep(8)
        s.mac.command_key("a")
        s.shot("selected", wait=3.0)
        item = ITEM_COMPRESS_Y if action == "compress" else ITEM_ARCHIVE_Y
        sub = (SUB_FASTER_Y if mode == "faster" else SUB_SMALLER_Y)[action]
        s.menu(item, sub, "pick-%s-%s" % (action, mode))
        s.shot("working", wait=40.0)
        s.mac.key("Return")                          # the save box, or a report
        s.shot("done", wait=60.0)
        s.mac.key("Return")
        time.sleep(5)
        s.mac.command_key("w")
        time.sleep(3)
        s.mac.click(470, 110)
        s.mac.command_key("y")                       # Put Away: flush + eject
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()
    got = read_volume(img, dest)
    for name_, (typ, crt, dlen, dat) in sorted(got.items()):
        print("  %-16s %s/%s %7d B  %s" % (name_, typ, crt, dlen,
                                           os.path.basename(dat)))
    return dest


def verify():
    """Decode every specimen with our own CLI and check it against the
    bytes that went in.

    Block SHAPES are not printed here: the engine links no libc and has no
    tracing, deliberately. They were measured once by patching
    `now_next_block` in a throwaway build to print `flags`, and the result
    is the table in this file's docstring; re-measure the same way.
    """
    for case in sorted(os.listdir(SPECIMENS)) if os.path.isdir(SPECIMENS) else []:
        d = os.path.join(SPECIMENS, case)
        for f in sorted(os.listdir(d)):
            if not f.endswith(".dat"):
                continue
            p = os.path.join(d, f)
            r = subprocess.run([cli(), "l", p], capture_output=True, text=True)
            # The format line goes to stderr; the entries to stdout.
            if "Now Compress" not in (r.stdout + r.stderr):
                continue
            out = tempfile.mkdtemp()
            try:
                x = subprocess.run([cli(), "x", "-o", out, p],
                                   capture_output=True)
                names = []
                for root, _, fs in os.walk(out):
                    for n in fs:
                        blob = open(os.path.join(root, n), "rb").read()
                        want = None
                        cand = os.path.join(d, "in-" + n)
                        if os.path.exists(cand):
                            want = open(cand, "rb").read()
                        names.append("%s %s" % (n, "EXACT" if want == blob
                                                else "(%d B)" % len(blob)))
                print("%-10s %-24s rc=%d  %s"
                      % (case, f, x.returncode, ", ".join(names)))
            finally:
                shutil.rmtree(out, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setup", action="store_true",
                    help="fetch the installer image and convert it to raw HFS")
    ap.add_argument("--install", action="store_true",
                    help="install Now QuickFiler onto a System 7 boot image")
    ap.add_argument("--case", help="one of %s, or 'all'" % ", ".join(sorted(CASES)))
    ap.add_argument("--verify", action="store_true",
                    help="decode the specimens and check them against the input")
    args = ap.parse_args()
    if args.setup:
        fetch_installer()
    if args.install:
        install()
    if args.case:
        cases = sorted(CASES) if args.case == "all" else [args.case]
        for c in cases:
            print("case %s:" % c)
            run_case(c)
    if args.verify:
        verify()
    if not any((args.setup, args.install, args.case, args.verify)):
        ap.print_help()
    return 0


def install():
    """Run the Now Utilities installer, selecting Now QuickFiler and the
    Toolbox it needs. The checkbox list is read back off the screen after
    every click: clicking blind is how the first attempt turned QuickFiler
    OFF and left three other components on."""
    import re
    rows = ["Menus", "Save", "Scrapbook", "Profile", "Startup", "Boomerang",
            "WYSIWYG", "Toolbox", "QuickFiler", "FolderMenus", "DragDrop"]
    y0, pitch, want = 110, 13, {"Toolbox", "QuickFiler"}

    def marks(png):
        out = subprocess.run(["convert", png, "-colorspace", "gray", "-crop",
                              "14x140+30+104", "+repage", "txt:-"],
                             capture_output=True, text=True).stdout
        dark = {}
        for line in out.splitlines()[1:]:
            m = re.match(r"(\d+),(\d+): \((\d+)", line)
            if m and int(m.group(3)) < 128:
                y = int(m.group(2)) + 104
                dark[y] = dark.get(y, 0) + 1
        return {n for i, n in enumerate(rows)
                if max(dark.get(y, 0) for y in range(y0 + pitch * i,
                                                     y0 + pitch * i + 6)) >= 3}

    shots = os.path.join(WORK, "install-shots")
    s = Session(os.path.join(HOME, "Sys7.img"), [RAW], shots)
    try:
        s.boot()
        s.mac.click(28, 80, double=True)              # Now Installer
        p = s.shot("installer", wait=25.0)
        state = marks(p)
        for i, name in enumerate(rows):
            if (name in want) == (name in state):
                continue
            s.mac.click(90, y0 + pitch * i + 2)
            time.sleep(1.5)
            state = marks(s.shot("sel-%s" % name, wait=1.0))
        print("nowcompress: installing %s" % sorted(state))
        s.mac.click(370, 271)                         # destination volume
        s.mac.click(455, 305)                         # Install
        s.shot("licence", wait=20.0)
        s.mac.click(403, 249)                         # Agree
        s.shot("copying", wait=60.0)
        s.shot("installed", wait=90.0)
    finally:
        os.makedirs(WORK, exist_ok=True)
        shutil.copyfile(os.path.join(s.work, "boot.hfv"), BOOT)
        s.close()
    print("nowcompress: boot image with QuickFiler at %s" % BOOT)


if __name__ == "__main__":
    sys.exit(main())
