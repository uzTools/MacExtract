#!/usr/bin/env python3
"""arcmac.py — make ArcMac archives with ArcMac, to settle fork order.

An ArcMac entry's payload is ONE compressed stream holding both forks, and
no reachable document says which fork comes first: the header is in
`reference/macutils/macunpack/arc.h`, but macunpack never decoded the
payload and its `arc.c` is absent from the distribution. Two real ArcMac
archives were found in the wild (`--wild` fetches them) and neither
settles it — every entry in both has one empty fork, because ArcMac
distributions hold documents (data only) and applications (resources
only). So the specimen is made here, by the encoder that defined the
format, exactly as `nowcompress.py` derives Now Compress blocks.

The encoder is **ArcMac 1.2a itself**, which arrives inside the very
archive this answers a question about: `ARCMACRC.BIN` on cd.textfiles.com
is a MacBinary-wrapped self-extracting ArcMac archive whose first entry is
the ArcMac application (APPL/`arc*`, empty data fork). `--setup` decodes
that entry with our own CLI and rebuilds the application as MacBinary, so
nothing has to run a self-extractor inside the guest. Shareware, fetched
by URL and checked by hash like the ROM and the System images; nothing
from it is committed.

    arcmac.py --wild     fetch the two archives in the wild, report their forks
    arcmac.py --setup    fetch ArcMac, rebuild the application, build the volume
    arcmac.py --make     boot, drive ArcMac, write an archive, read it back
    arcmac.py --decide   parse that archive and report which fork comes first

Specimens land in `$UNC_VMAC_HOME/specimens/arcmac/`, beside the emulator
rather than under `build/`, which `make clean` removes.

The subject is built to make the answer legible without trusting anything:
its data fork is a run of `THIS IS THE DATA FORK` and its resource fork is
a real resource fork, which identifies itself from its own first 16 bytes
(offset 256 to the data, a map offset that chains onto the length). So
whichever fork the stream starts with, the decompressed bytes say so.
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

# ArcMac 1.2a, shareware, as a MacBinary self-extracting archive. The wiki
# page that named it is justsolve.archiveteam.org/wiki/ArcMac; the site
# serves HTTP only.
ARCMAC_URL = "http://cd.textfiles.com/garbo/MAC/ARCERS/ARCMACRC.BIN"
ARCMAC_SHA = "7d53c623bc255bb435df9730be2063a3d98a460257553056954c9fd16da31c44"

# The second archive in the wild: Macintosh Garden's ArcMac.hqx, a .sit
# holding ArcPop.Arc — itself a self-extracting ArcMac archive. Used by
# --wild only, to show that neither specimen has a two-fork entry.
GARDEN_PAGE = "https://macintoshgarden.org/apps/arcmac"

HOME = R.VMAC_HOME
WORK = os.path.join(HOME, "arcmac")
SPECIMENS = os.path.join(HOME, "specimens", "arcmac")
SELFEXT = os.path.join(WORK, "ARCMACRC.BIN")
APPBIN = os.path.join(WORK, "ArcMac.bin")

# ArcMac header, per reference/macutils/macunpack/arc.h. The fork lengths
# are LITTLE-endian: ARCMAC.DOC marks them, with size/date/time/crc, as
# "stored in archive using Intel 80xxx byte sex", and both archives in the
# wild agree — the little-endian pair sums to size2 on every entry, the
# big-endian pair sums to garbage.
AM_HDR = 88
AM_FNAME, AM_FTYPE, AM_FAUTH = 2, 34, 38
AM_FDATA, AM_FRSRC, AM_MAGIC2 = 50, 54, 59

SUBJECT_DATA = b"THIS IS THE DATA FORK, and it is compressible. " * 90
SUBJECT_NAME = "TwoForks"


def cli():
    for build in ("rel", "san", ""):
        p = os.path.join(REPO, "build", build, "unclassic")
        if os.path.exists(p):
            return p
    raise SystemExit("arcmac: build the CLI first (make)")


# ------------------------------------------------------------------
# Reading ArcMac containers
# ------------------------------------------------------------------

def walk(arc):
    """Every ArcMac entry in a blob: name, type, creator, forks, payload."""
    out, pos = [], 0
    while pos + AM_HDR <= len(arc) and arc[pos] == 0x1B and arc[pos + 1] != 0:
        h = arc[pos:pos + AM_HDR]
        if h[AM_MAGIC2] != 0x1A:
            break
        comp = struct.unpack("<I", h[AM_MAGIC2 + 0x0F:AM_MAGIC2 + 0x13])[0]
        out.append({
            "name": h[AM_FNAME:AM_FNAME + 31].split(b"\0")[0].decode("mac-roman"),
            "kind": h[1],
            "type": h[AM_FTYPE:AM_FTYPE + 4].decode("mac-roman"),
            "creator": h[AM_FAUTH:AM_FAUTH + 4].decode("mac-roman"),
            "data": struct.unpack("<I", h[AM_FDATA:AM_FDATA + 4])[0],
            "rsrc": struct.unpack("<I", h[AM_FRSRC:AM_FRSRC + 4])[0],
            "total": struct.unpack("<I", h[AM_MAGIC2 + 0x19:AM_MAGIC2 + 0x1D])[0],
            "pc": bytes(h[AM_MAGIC2:AM_HDR]),
            "payload": arc[pos + AM_HDR:pos + AM_HDR + comp],
        })
        pos += AM_HDR + comp
    return out


def unpack_entry(e):
    """Decompress one entry with our own engine.

    An ArcMac header CONTAINS a complete PC ARC header at offset 59 — which
    is why non-ArcMac-aware extractors can sometimes read these files — so
    the entry is carved into a plain one-entry .arc and handed to the CLI.
    That exercises the shipped decoder and its CRC check, rather than a
    second implementation written here."""
    pc = bytearray(e["pc"])
    pc[2:15] = b"CARVED.BIN\0\0\0"
    work = tempfile.mkdtemp(prefix="arcmac-carve-")
    try:
        arc = os.path.join(work, "c.arc")
        open(arc, "wb").write(bytes(pc) + e["payload"] + b"\x1a\x00")
        out = os.path.join(work, "out")
        os.makedirs(out)
        r = subprocess.run([cli(), "x", "-o", out, arc], capture_output=True)
        p = os.path.join(out, "CARVED.BIN")
        if r.returncode != 0 or not os.path.exists(p):
            return None
        return open(p, "rb").read()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def looks_like_rsrc(blob, length):
    """Does `blob` begin a resource fork of exactly `length` bytes?

    A resource fork states its own shape in its first 16 bytes: offset to
    the data area, offset to the map, and the two lengths. Both offsets and
    lengths have to chain onto each other and onto the fork length, which
    random data does not do."""
    if len(blob) < 16 or length < 16:
        return False
    doff, moff, dlen, mlen = struct.unpack(">IIII", blob[:16])
    return (doff + dlen == moff and moff + mlen == length
            and 16 <= doff <= 256 and mlen >= 28)


# ------------------------------------------------------------------
# Building the volume
# ------------------------------------------------------------------

def crc16(b):
    """CCITT, as MacBinary II's header checksum uses it."""
    c = 0
    for by in b:
        c ^= by << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


def macbinary(name, ftype, creator, data=b"", rsrc=b"", flags=0):
    """MacBinary II. `flags` is the 16-bit Finder flags word, split across
    the two bytes MacBinary keeps it in — and left at 0 here on purpose:
    the ArcMac header's own Finder info has bit 0x40 of the high byte set,
    which is `invisible`, so copying it across put the application on the
    volume where the Finder would not show it."""
    n = name.encode("mac-roman")[:63]
    h = bytearray(128)
    h[1] = len(n)
    h[2:2 + len(n)] = n
    h[65:69] = ftype.encode("mac-roman")
    h[69:73] = creator.encode("mac-roman")
    h[73] = (flags >> 8) & 0xFF
    h[101] = flags & 0xFF
    struct.pack_into(">II", h, 83, len(data), len(rsrc))
    h[122] = h[123] = 129                            # MacBinary II
    struct.pack_into(">H", h, 124, crc16(bytes(h[:124])))
    pad = lambda b: b + b"\0" * (-len(b) % 128)      # noqa: E731
    return bytes(h) + pad(data) + pad(rsrc)


def make_rsrc(text=b"\x14ArcMac fork-order test"):
    """A real, minimal resource fork holding one 'STR ' resource."""
    data = struct.pack(">I", len(text)) + text
    doff, dlen = 256, len(data)
    moff, tloff = doff + dlen, 28
    types = struct.pack(">H", 0) + b"STR " + struct.pack(">HH", 0, 10)
    refs = struct.pack(">HhBBHI", 128, -1, 0, 0, 0, 0)
    nloff = tloff + len(types) + len(refs)
    hdr = struct.pack(">IIII", doff, moff, dlen, nloff)
    mp = hdr + b"\0" * 4 + struct.pack(">HHHH", 0, 0, tloff, nloff) + types + refs
    return hdr + b"\0" * (doff - 16) + data + mp


def hfs(env, *args):
    return subprocess.run(args, check=True, capture_output=True, env=env)


def make_volume(path, volname, macbins, size_kb=1400):
    """An HFS volume holding MacBinary files, forks and all."""
    open(path, "wb").truncate(size_kb * 1024)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        hfs(env, "hformat", "-l", volname, path)
        hfs(env, "hmount", path)
        for mb in macbins:
            hfs(env, "hcopy", "-m", os.path.abspath(mb), volname + ":")
        hfs(env, "humount")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


def read_volume(img, out):
    """Every file on the volume, as (type, creator, data fork, rsrc fork)."""
    os.makedirs(out, exist_ok=True)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    got = {}
    try:
        hfs(env, "hmount", img)
        listing = subprocess.run(["hls", "-1"], capture_output=True,
                                 env=env).stdout.decode("mac-roman", "replace")
        for name in [n for n in listing.split("\n") if n.strip()]:
            mb = os.path.join(out, name.replace("/", "_") + ".bin")
            if subprocess.run(["hcopy", "-m", name, mb], capture_output=True,
                              env=env).returncode != 0:
                continue
            blob = open(mb, "rb").read()
            dlen, rlen = struct.unpack(">II", blob[83:91])
            roff = 128 + ((dlen + 127) & ~127)
            got[name] = (blob[65:69].decode("mac-roman"),
                         blob[69:73].decode("mac-roman"),
                         blob[128:128 + dlen], blob[roff:roff + rlen])
        subprocess.run(["humount"], capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    return got


# ------------------------------------------------------------------
# Fetching
# ------------------------------------------------------------------

def fetch():
    """Download the self-extracting ArcMac and rebuild the application.

    Entry 0 of that archive IS ArcMac: an APPL with an empty data fork, so
    the application is exactly its resource fork plus Finder info that the
    ArcMac header already carries."""
    os.makedirs(WORK, exist_ok=True)
    if not os.path.exists(SELFEXT):
        subprocess.run(["curl", "-sS", "-L", "-o", SELFEXT, ARCMAC_URL], check=True)
    blob = open(SELFEXT, "rb").read()
    got = hashlib.sha256(blob).hexdigest()
    if got != ARCMAC_SHA:
        raise SystemExit("arcmac: %s has sha256 %s, expected %s"
                         % (SELFEXT, got, ARCMAC_SHA))
    dlen = struct.unpack(">I", blob[83:87])[0]
    arc = blob[128:128 + dlen]                       # the MacBinary data fork
    open(os.path.join(WORK, "selfext.arc"), "wb").write(arc)
    entries = walk(arc)
    app = next((e for e in entries if e["type"] == "APPL"), None)
    if not app:
        raise SystemExit("arcmac: no application inside the self-extractor")
    rsrc = unpack_entry(app)
    if rsrc is None or len(rsrc) != app["rsrc"]:
        raise SystemExit("arcmac: could not decode the application's resources")
    if not looks_like_rsrc(rsrc, app["rsrc"]):
        raise SystemExit("arcmac: what came out is not a resource fork")
    open(APPBIN, "wb").write(macbinary(app["name"], "APPL", app["creator"],
                                       b"", rsrc))
    print("arcmac: %s — %s %s/%s, %d B of resources"
          % (APPBIN, app["name"], app["type"], app["creator"], len(rsrc)))


def wild():
    """Report the fork lengths of every entry in the archives in the wild.

    This is the check that sent the question to the emulator: if any entry
    anywhere had both forks non-empty, it would decide fork order on its
    own and none of the rest of this file would be needed."""
    os.makedirs(WORK, exist_ok=True)
    fetch()
    found = [("ARCMACRC.BIN (cd.textfiles.com)",
              open(os.path.join(WORK, "selfext.arc"), "rb").read())]

    hqx = os.path.join(WORK, "ArcMac.hqx")
    if not os.path.exists(hqx):
        page = subprocess.run(["curl", "-sS", "-L", "-A", "Mozilla/5.0",
                               GARDEN_PAGE], capture_output=True).stdout.decode(
                                   "utf-8", "replace")
        url = next((l for l in page.split('"')
                    if "download.macintoshgarden.org" in l and ".hqx" in l), None)
        if url:
            subprocess.run(["curl", "-sS", "-L", "-A", "Mozilla/5.0", "-e",
                            GARDEN_PAGE, "-o", hqx, "https:" + url], check=True)
    if os.path.exists(hqx):
        out = os.path.join(WORK, "garden")
        shutil.rmtree(out, ignore_errors=True)
        subprocess.run([cli(), "x", "-o", out, hqx], capture_output=True)
        for root, _, files in os.walk(out):
            for n in files:
                p = os.path.join(root, n)
                blob = open(p, "rb").read()
                if blob[:1] == b"\x1b" and len(blob) > AM_HDR and blob[59] == 0x1A:
                    found.append(("%s (Macintosh Garden)" % n, blob))

    both = 0
    for label, arc in found:
        print("%s:" % label)
        for e in walk(arc):
            both += e["data"] > 0 and e["rsrc"] > 0
            print("  %-22s %s/%s  method %d  data %7d  rsrc %7d%s"
                  % (e["name"], e["type"], e["creator"], e["kind"],
                     e["data"], e["rsrc"],
                     "  <== BOTH FORKS" if e["data"] and e["rsrc"] else ""))
    print("arcmac: %d entr%s with both forks non-empty"
          % (both, "y" if both == 1 else "ies"))
    return both


# ------------------------------------------------------------------
# Driving ArcMac
# ------------------------------------------------------------------

class Session:
    """A booted Mac with screenshots kept per step."""

    def __init__(self, boot, extra, shots, mem="mv-4M"):
        self.work = tempfile.mkdtemp(prefix="arcmac-")
        self.shots = shots
        os.makedirs(shots, exist_ok=True)
        self.n = 0
        self.mac = Mac(boot, mem, self.work, extra=tuple(extra))

    def shot(self, tag, wait=2.0):
        time.sleep(wait)
        self.n += 1
        p = os.path.join(self.shots, "%02d-%s.png" % (self.n, tag))
        for _ in range(30):
            if self.mac.dpy.screenshot(p):
                return p
            time.sleep(0.4)
        raise SystemExit("arcmac: no screenshot")

    def type(self, text):
        """Type a line at ArcMac's shell prompt.

        ArcMac 1.3c is not a dialog-driven application at all: it opens a
        command shell ("Martian Operating System") whose archiving verb is
        `arc a<modifiers> archive [files...]`, documented under *ArcMac
        Command Summary* in ARCMAC.DOC."""
        self.mac._xdo("type", "--delay", "120", text)
        time.sleep(1.0)

    def boot(self):
        self.mac.settle(os.path.join(self.work, "s.png"), interval=8.0,
                        timeout=420.0, stable=3)

    def menu(self, title_x, item_y, tag):
        """Pull a Finder menu down and release on an item."""
        ox, oy = self.mac.origin()
        x = self.mac._xdo
        x("mousemove", str(ox + title_x), str(oy + 8))
        time.sleep(0.4)
        x("mousedown", "1")
        time.sleep(1.2)
        x("mousemove", str(ox + title_x + 25), str(oy + item_y))
        time.sleep(1.0)
        self.shot(tag)
        x("mouseup", "1")
        time.sleep(2.0)

    def shutdown(self):
        """Special ▸ Shut Down, and the whole reason this is not a SIGKILL.

        Mini vMac writes a guest's disk sectors through buffered stdio and
        only flushes when the image is ejected, so killing the emulator
        with the volume still mounted loses everything the guest wrote:
        the Finder showed `Test.ARC` on screen while the host's copy of the
        image did not have it. Shut Down ejects every volume, which
        flushes them."""
        self.menu(175, 123, "shutdown")

    def close(self):
        self.mac.close()


# `a` adds with the best method ArcMac picks; `as` adds STORED, per the
# modifier list in ARCMAC.DOC. The stored one matters: its payload is the
# two forks laid down raw, so fork order is legible without invoking any
# decoder, ours included.
ADD = ["cd Arc:", "arc a Packed TwoForks", "arc as Stored TwoForks", "dir"]


def make(system="System6.hfv", cmds=None):
    """Boot with ArcMac and a two-fork subject, and archive the subject."""
    os.makedirs(SPECIMENS, exist_ok=True)
    if not os.path.exists(APPBIN):
        fetch()
    work = tempfile.mkdtemp(prefix="arcmac-vol-")
    subj = os.path.join(work, "subject.bin")
    open(subj, "wb").write(macbinary(SUBJECT_NAME, "TEXT", "ttxt",
                                     SUBJECT_DATA, make_rsrc()))
    img = os.path.join(SPECIMENS, "volume.img")
    make_volume(img, "Arc", [APPBIN, subj])
    open(os.path.join(SPECIMENS, "in-data"), "wb").write(SUBJECT_DATA)
    open(os.path.join(SPECIMENS, "in-rsrc"), "wb").write(make_rsrc())

    s = Session(os.path.join(HOME, system), [img],
                os.path.join(SPECIMENS, "shots"))
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(470, 110, double=True)           # open the volume
        s.shot("volume", wait=8.0)
        s.mac.click(105, 110, double=True)           # launch ArcMac
        s.shot("launched", wait=25.0)
        for i, cmd in enumerate(cmds or ADD):
            s.type(cmd)
            s.mac.key("Return")
            s.shot("cmd%d" % i, wait=25.0 if cmd.startswith("arc") else 4.0)
        s.type("exit")                               # back to the Finder
        s.mac.key("Return")
        s.shot("quit", wait=20.0)
        s.shutdown()
        s.shot("off", wait=25.0)
    finally:
        time.sleep(5)
        s.close()

    got = read_volume(img, os.path.join(SPECIMENS, "readback"))
    for name, (typ, crt, data, rsrc) in sorted(got.items()):
        print("  %-20s %s/%s  data %7d  rsrc %7d" % (name, typ, crt,
                                                     len(data), len(rsrc)))
        # An ArcMac archive lives in the data fork, so write it out as a
        # plain file: the specimens are only useful if something other
        # than this script can open them.
        if typ == "mArc" and data[:1] == b"\x1b":
            open(os.path.join(SPECIMENS, name), "wb").write(data)
    return got


def decide():
    """Read the archive ArcMac wrote and say which fork comes first."""
    read = os.path.join(SPECIMENS, "readback")
    if not os.path.isdir(read):
        raise SystemExit("arcmac: run --make first")
    want_data = open(os.path.join(SPECIMENS, "in-data"), "rb").read()
    want_rsrc = open(os.path.join(SPECIMENS, "in-rsrc"), "rb").read()
    verdict = None
    for name in sorted(os.listdir(read)):
        blob = open(os.path.join(read, name), "rb").read()
        dlen = struct.unpack(">I", blob[83:87])[0]
        arc = blob[128:128 + dlen]
        if arc[:1] != b"\x1b" or len(arc) < AM_HDR or arc[59] != 0x1A:
            continue
        for e in walk(arc):
            if not (e["data"] and e["rsrc"]):
                print("  %-16s one fork empty — decides nothing" % e["name"])
                continue
            out = unpack_entry(e)
            if out is None:
                print("  %-16s did not decode" % e["name"])
                continue
            print("  %-16s %d B out, forks %d + %d = %d"
                  % (e["name"], len(out), e["data"], e["rsrc"], e["total"]))
            head, tail = out[:e["data"]], out[e["data"]:]
            if head == want_data and tail == want_rsrc:
                verdict = "DATA FORK FIRST"
            elif out[:e["rsrc"]] == want_rsrc and out[e["rsrc"]:] == want_data:
                verdict = "RESOURCE FORK FIRST"
            elif looks_like_rsrc(out, e["rsrc"]):
                verdict = "RESOURCE FORK FIRST (by its own header)"
            elif looks_like_rsrc(tail, e["rsrc"]):
                verdict = "DATA FORK FIRST (resource header at data length)"
            print("  verdict: %s" % (verdict or "UNDECIDED — neither order fits"))
    return verdict


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wild", action="store_true",
                    help="fetch the archives in the wild and report their forks")
    ap.add_argument("--setup", action="store_true",
                    help="fetch ArcMac and rebuild the application")
    ap.add_argument("--make", action="store_true",
                    help="boot, drive ArcMac, archive a two-fork file")
    ap.add_argument("--system", default="System6.hfv",
                    help="boot image for --make (System6.hfv or Sys7.img)")
    ap.add_argument("--cmd", action="append",
                    help="a shell command to run instead of the add sequence; "
                         "repeatable, for probing the shell")
    ap.add_argument("--decide", action="store_true",
                    help="report which fork the payload starts with")
    args = ap.parse_args()
    if args.wild:
        wild()
    if args.setup:
        fetch()
    if args.make:
        make(args.system, args.cmd)
    if args.decide:
        decide()
    if not any((args.wild, args.setup, args.make, args.decide)):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
