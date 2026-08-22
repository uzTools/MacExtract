#!/usr/bin/env python3
"""ddencode.py — grade DiskDoubler methods 3, 4 and 5 by WRITING them.

Those three are the last DiskDoubler methods this engine declines, and
they are not blocked on a reference: macutils implements 3, XADMaster
implements 4 and 5, and each is marked untested by its own author
(OPEN_ITEMS.md). What has never existed is a file to grade a decoder
against — no corpus fixture uses one and no DiskDoubler release from
3.1.2 to 4.1.1 offers one from a menu.

So this closes the loop from the other side, which is the move
`arcmac.py`, `nowcompress.py` and `diskdoubler.py --make` already make
for other formats: **write the file ourselves and have the original
application read it.** If Salient's own 1991 expander turns our
synthetic method 3 fork back into the bytes that went in, the framing,
the escape byte, the checksum convention and the XOR condition are
confirmed by an implementation that was there — and our decoder on the
same file closes the triangle.

    tools/vmac/ddencode.py --build     write the files; round-trip here
    tools/vmac/ddencode.py --probe     photograph the 1991 DD menu
    tools/vmac/ddencode.py --expand    let DDExpand 3.1.2 read them

**What this grades and what it does not.** It grades our reading of the
FORMAT against the vendor: a wrong escape byte, a wrong tree
serialization, a wrong checksum base or a wrong bit order all make the
expander refuse or produce different bytes. It does NOT grade our
decoder against encodings our encoder never emits — a real file may use
run lengths, tree shapes or contexts ours does not. That is why the
subjects below are chosen to be awkward rather than convenient, and why
this stays labelled weaker than a specimen.
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import shutil                                                  # noqa: E402
import time                                                    # noqa: E402


def _emu():
    """Everything that needs the emulator, imported on use.

    `--emit` regenerates a committed fixture and is run by
    `check_docs.py` inside `ci.sh`, where there is no X server and no
    disk image; a module-level import of the harness machinery would
    make the whole of CI depend on them.
    """
    global R, macbinary, Session, make_volume, VOLUME_ICON, read_forks, ndd
    global HOME, WORK, SPECIMENS, BOOT
    import run as R                                            # noqa: F401
    from arcmac import macbinary                               # noqa: F401
    from diskdoubler import Session, make_volume, VOLUME_ICON   # noqa: F401
    from superdisk import read_forks                           # noqa: F401
    import ndd                                                 # noqa: F401
    HOME = R.VMAC_HOME
    WORK = os.path.join(HOME, "ddencode")
    SPECIMENS = os.path.join(HOME, "specimens", "ddencode")
    BOOT = os.path.join(WORK, "ddencboot.hfv")

XOR = 0x5A          # applied when info1 >= 0x2a and info2's high bit is clear
RLE_ESC = 0x90


def crc16_xmodem(data, crc=0):
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


# ------------------------------------------------------------------
# The encoders
# ------------------------------------------------------------------

def enc_rle(data):
    """RLE90 on 0x90: ESC 0 is a literal escape, ESC n is n copies of the
    byte already emitted. Runs are emitted at length 3 and up, because at
    2 the escape costs as much as the byte it saves."""
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        run = 1
        while i + run < len(data) and data[i + run] == b and run < 255:
            run += 1
        if b == RLE_ESC:
            out += bytes([RLE_ESC, 0])
            i += 1
            continue
        out.append(b)
        if run >= 3:
            out += bytes([RLE_ESC, run])
            i += run
        else:
            i += 1
    return bytes(out)


class Bits:
    def __init__(self):
        self.out = bytearray()
        self.acc = 0
        self.n = 0

    def put(self, v, n):
        for k in range(n - 1, -1, -1):
            self.acc = (self.acc << 1) | ((v >> k) & 1)
            self.n += 1
            if self.n == 8:
                self.out.append(self.acc & 0xFF)
                self.acc = 0
                self.n = 0

    def flush(self):
        if self.n:
            self.put(0, 8 - self.n)
        return bytes(self.out)


def enc_huffman(data):
    """StuffIt's bit-serialized Huffman: pre-order, `1`+8 bits for a leaf,
    `0` for an internal node, zero branch before one branch.
    Source: unc_huff_read_tree, which is what reads it back."""
    freq = {}
    for b in data:
        freq[b] = freq.get(b, 0) + 1
    if len(freq) < 2:                      # a one-leaf tree has no root pair
        freq[(min(freq) + 1) & 0xFF] = 1
    nodes = [[c, b] for b, c in freq.items()]
    while len(nodes) > 1:
        nodes.sort(key=lambda x: (x[0], isinstance(x[1], int) and x[1] or 0))
        a, b = nodes.pop(0), nodes.pop(0)
        nodes.append([a[0] + b[0], (a[1], b[1])])
    tree = nodes[0][1]

    codes = {}

    def walk(node, prefix, nbits):
        if isinstance(node, int):
            codes[node] = (prefix, nbits)
            return
        walk(node[0], prefix << 1, nbits + 1)
        walk(node[1], (prefix << 1) | 1, nbits + 1)

    walk(tree, 0, 0)
    bits = Bits()

    def emit(node):
        if isinstance(node, int):
            bits.put(1, 1)
            bits.put(node, 8)
            return
        bits.put(0, 1)
        emit(node[0])
        emit(node[1])

    emit(tree)
    for b in data:
        v, n = codes[b]
        bits.put(v, n)
    return bits.flush()


class Splay:
    """One tree of method 2/5: the complete binary tree over 256 leaves,
    rotated toward the root after each byte."""

    def __init__(self):
        self.p = bytearray(512)
        self.l = [0] * 256
        self.r = [0] * 256
        for j in range(256):
            self.p[2 * j] = j
            self.p[2 * j + 1] = j
            self.l[j] = j * 2
            self.r[j] = j * 2 + 1

    def code(self, byte):
        node, dirs = byte + 0x100, []
        while node != 1:
            parent = self.p[node]
            dirs.append(1 if self.r[parent] == node else 0)
            node = parent
        return dirs[::-1]

    def splay(self, byte):
        node = byte + 0x100
        while True:
            parent = self.p[node]
            if parent == 1:
                break
            grand = self.p[parent]
            uncle = self.l[grand]
            if uncle == parent:
                uncle = self.r[grand]
                self.r[grand] = node
            else:
                self.l[grand] = node
            if self.l[parent] != node:
                self.r[parent] = uncle
            else:
                self.l[parent] = uncle
            self.p[node] = grand
            self.p[uncle] = parent
            node = grand
            if node == 1:
                break


def enc_splay(data, ntrees=256):
    trees = [Splay() for _ in range(ntrees)]
    bits = Bits()
    ctx = 0
    for b in data:
        for d in trees[ctx].code(b):
            bits.put(d, 1)
        trees[ctx].splay(b)
        ctx = b % ntrees
    return bits.flush()


# Methods 1, 2 and 5 XOR the decoded bytes with 0x5a; 3 and 4 do not.
# Measured, not assumed — the first run of --expand XORed all four and
# Salient's 1991 expander handed back exactly `SUBJECT ^ 0x5a` for the
# two that do not (DECISIONS.md, methods 3, 4 and 5).
XOR_METHODS = (1, 2, 5)


def encode(data, method, ntrees=256):
    """The compressed DATA FORK for one method."""
    x = XOR if method in XOR_METHODS else 0
    plain = bytes(b ^ x for b in data)        # what the codec sees
    if method == 3:
        return enc_rle(plain)
    if method == 4:
        return enc_huffman(plain)
    if method == 2:
        return enc_splay(plain)
    if method == 5:
        return bytes([ntrees & 0xFF]) + enc_splay(plain, ntrees)
    raise SystemExit("ddencode: no encoder for method %d" % method)


# ------------------------------------------------------------------
# The container
# ------------------------------------------------------------------

def container(data, method, ntrees=256, ftype="UNCL", creator="UNCL"):
    """A 0xABCD0054 single-file container holding one data fork.

    Field offsets are `dd_parse_filehdr`'s, counted from the magic:
    sizes at +4/+8/+12/+16, methods at +20/+21, info1 at +22, the two
    sums at +48/+50, info2 at +52, and the header's own CRC-16/XMODEM
    over its first 82 bytes at +82 — which `unc_diskdoubler_probe`
    checks, so a container with a stale one is not recognised at all.
    """
    comp = encode(data, method, ntrees)
    h = bytearray(84)
    h[0:4] = b"\xab\xcd\x00\x54"
    struct.pack_into(">IIII", h, 4, len(data), len(comp), 0, 0)
    h[20] = method
    h[21] = 0                                  # no resource fork
    h[22] = 0x2A                               # info1: the XOR applies
    h[32:36] = ftype.encode("mac-roman")
    h[36:40] = creator.encode("mac-roman")
    # The sum is over the bytes the file expands to, whatever the codec
    # saw on the way.
    struct.pack_into(">H", h, 48, sum(data) & 0xFFFF)
    h[52] = 0                                  # info2
    struct.pack_into(">H", h, 82, crc16_xmodem(bytes(h[:82])))
    return bytes(h) + comp


# Awkward on purpose: a run longer than 255 so the encoder has to split
# it, a literal 0x90 that must be escaped, a byte that only ever appears
# once so its Huffman code is long, and enough distinct bytes that
# several splay contexts exist.
SUBJECT = (b"DiskDoubler method probe. " * 12 +
           bytes([0x90]) * 3 +
           b"A" * 300 +
           bytes(range(256)) +
           bytes([0x90, 0x00, 0x90]) +
           b"z" +
           b"the quick brown fox jumps over the lazy dog. " * 6)

SUBJECTS = [("Rle", 3, 256), ("Huff", 4, 256), ("Splay", 5, 256),
            ("Splay16", 5, 16)]


def build(outdir=None):
    """Write one container per method and read each back with our own
    CLI. Encoder and decoder are both ours, so this grades the
    transcription and not the format — but it is the step that has to
    pass before an emulator run is worth booting."""
    outdir = outdir or tempfile.mkdtemp(prefix="ddenc-")
    os.makedirs(outdir, exist_ok=True)
    bad = 0
    for name, method, ntrees in SUBJECTS:
        blob = container(SUBJECT, method, ntrees)
        path = os.path.join(outdir, name)
        open(path, "wb").write(blob)
        h = header(blob)
        tmp = tempfile.mkdtemp(prefix="ddenc-x-")
        r = subprocess.run([cli(), "x", "-o", tmp, path],
                           capture_output=True, text=True)
        got = None
        for f in os.listdir(tmp):
            if not f.endswith(".rsrc"):
                got = open(os.path.join(tmp, f), "rb").read()
        ok = r.returncode == 0 and got == SUBJECT
        print("ddencode: %-8s method %d%s  %s  %s"
              % (name, method,
                 "" if ntrees == 256 else " (%d trees)" % ntrees,
                 describe(h),
                 "round-trips" if ok else "FAILED: %s"
                 % (r.stderr.strip().splitlines()[:1] or ["output differs"])[0]))
        bad += 0 if ok else 1
    print("ddencode: %d of %d round-trip; files in %s"
          % (len(SUBJECTS) - bad, len(SUBJECTS), outdir))
    return outdir, bad


# ------------------------------------------------------------------
# Salient's own 1991 application, as the oracle
# ------------------------------------------------------------------

def disk_files():
    _emu()
    """`DiskDoubler™ INIT` and `DiskDoubler™ App` off the 3.1.2 floppy.

    Both are plain, not DiskDoubler-compressed — unlike everything in
    that disk's Goodies folder — so they come off it as they are.
    """
    img = ndd.dd312_image()
    out = {}
    for path, (ftype, creator, data, rsrc) in read_forks(img).items():
        if path[-1].startswith("DiskDoubler\u2122"):
            out[path[-1]] = (ftype, creator, data, rsrc)
    if len(out) != 2:
        raise SystemExit("ddencode: expected the INIT and the App on the "
                         "3.1.2 disk, found %d" % len(out))
    return out


def install():
    _emu()
    """A System 7 boot image with the 1991 INIT loaded. The INIT is the
    half that does the work; the application beside it is what the menu
    launches, exactly as in 3.7 and 4.1.1."""
    os.makedirs(WORK, exist_ok=True)
    files = disk_files()
    init = [v for k, v in files.items() if v[0] == "INIT"]
    if not init:
        raise SystemExit("ddencode: no INIT on the 3.1.2 disk")
    ftype, creator, data, rsrc = init[0]
    work = tempfile.mkdtemp(prefix="ddencinst-")
    try:
        mb = os.path.join(work, "init.bin")
        open(mb, "wb").write(macbinary("DiskDoubler\u2122 INIT", ftype,
                                       creator, data, rsrc))
        shutil.copyfile(os.path.join(HOME, "Sys7.img"), BOOT)
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            subprocess.run(["hmount", BOOT], check=True, capture_output=True,
                           env=env)
            subprocess.run(["hcopy", "-m", mb, ":System Folder:Extensions:"],
                           check=True, capture_output=True, env=env)
            subprocess.run(["humount"], check=True, capture_output=True,
                           env=env)
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("ddencode: boot image with the 1991 INIT at %s" % BOOT)
    return BOOT


# The subject 3.1.2's own menu compresses, so what "Method A" and
# "Method B" write on a 1991 release is measured rather than inferred
# from the two non-hardware files on its disk.
PLAIN = (b"Salient DiskDoubler 3.1.2 method probe. " * 300 +
         bytes(bytearray(range(256))) * 4)


def session(tag, era="1991"):
    _emu()
    """A booted Mac with the 1991 INIT loaded and a work volume holding
    the application, the four synthetic files and one plain subject."""
    work = tempfile.mkdtemp(prefix="ddencwork-")
    mbs = []
    if era == "1991":
        files = disk_files()
        app = [v for k, v in files.items() if v[0] == "APPL"][0]
        appname = "DiskDoubler\u2122 App"
        boot = BOOT
    else:
        # DiskDoubler 4.1.1, off the Symantec floppy (`ndd.py`). Its
        # extension registers the same `DDF2` types, so the same
        # double-click drives it — a second, later expander for the one
        # thing 1991 would not take.
        name, ftype, creator, data, rsrc = ndd.app_files("norton")[0]
        app = (ftype, creator, data, rsrc)
        appname = name
        boot = ndd.BOOT
        if not os.path.exists(boot):
            ndd.install("norton")
    mb = os.path.join(work, "app.bin")
    open(mb, "wb").write(macbinary(appname, app[0], app[1], app[2], app[3]))
    mbs.append(mb)
    mb = os.path.join(work, "plain.bin")
    open(mb, "wb").write(macbinary("Plain", "TEXT", "ttxt", PLAIN, b""))
    mbs.append(mb)
    for i, (name, method, ntrees) in enumerate(SUBJECTS):
        blob = container(SUBJECT, method, ntrees)
        p = os.path.join(work, "s%d.bin" % i)
        # The type is what makes the Finder hand it to DiskDoubler; the
        # 3.1.2 disk's own compressed files carry DDF2/DDAP.
        open(p, "wb").write(macbinary(name, "DDF2", "DDAP", blob, b""))
        mbs.append(p)
    img = os.path.join(work, "ddencwork.img")
    make_volume(img, "DDenc", mbs, size_kb=8192)
    if era == "1991" and not os.path.exists(boot):
        install()
    s = Session(boot, [img], os.path.join(SPECIMENS, tag))
    return s, work, img


def probe(keep=False):
    _emu()
    """Photograph the 1991 INIT's Finder menu. Every coordinate the
    --expand run uses is measured off these frames, because 3.1.2's menu
    is not 3.7's and not 4.1.1's."""
    s, work, img = session("probe")
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        for x in (250, 281, 300, 320):
            s.peek(x, "menu-x%d" % x)
    finally:
        time.sleep(3)
        s.close()
    print("ddencode: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


def probe_app(keep=False):
    _emu()
    """Launch the 1991 application and photograph ITS menus.

    3.1.2's INIT adds no menu to the Finder's menu bar — that arrived
    with the separate "Finder Menu" extension of 3.7 and 4.x — but it
    does register the `DDF2`/`DDAP` icons, which is how a --probe frame
    shows the extension is loaded at all. The commands live in the
    application: `MENU 200` is Compress…, Expand…, Combine…, Split or
    Join…, File Info…, Settings…, Help…, Quit.
    """
    s, work, img = session("probe-app")
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)
        s.mac.key("Escape")
        time.sleep(0.5)
        s.mac.key("d")                       # type-select DiskDoubler™ App
        time.sleep(1.5)
        s.shot("selected-app", wait=1.0)
        s.mac.command_key("o")               # Open, never Return
        s.shot("app-launched", wait=25.0)
        for x in (40, 80, 120, 160):
            s.peek(x, "appmenu-x%d" % x)
    finally:
        time.sleep(3)
        s.close()
    print("ddencode: screenshots in %s" % s.shots)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)


# The personalization dialog, measured off probe-app/04-app-launched.png
# (System 7, 512x342). 3.1.2 asks on first launch exactly as 3.7 does,
# and until it is answered no command works.
PERS_NAME = (300, 118)
PERS_ORG = (300, 153)
PERS_OK = (416, 237)


def personalize(s):
    s.shot("personalize", wait=20.0)
    s.mac.click(*PERS_NAME)
    s.mac._xdo("type", "--delay", "120", "unclassic")
    s.mac.click(*PERS_ORG)
    s.mac._xdo("type", "--delay", "120", "test")
    s.shot("personalize-filled", wait=1.0)
    s.mac.click(*PERS_OK)
    s.shot("personalized", wait=8.0)


def open_by_name(s, prefix, tag):
    """Type-select in the front window, then Cmd-O.

    Never Return: in the System 7 Finder it opens the selected icon's
    NAME for editing and the next keystroke types into it — the trap
    `ddpro.py` records, which renamed a subject to "a" once.
    """
    s.mac.key("Escape")
    time.sleep(0.6)
    s.mac._xdo("type", "--delay", "120", prefix)
    time.sleep(1.5)
    s.shot("selected-" + tag, wait=0.5)
    s.mac.command_key("o")


def expand(keep=False, era="1991"):
    _emu()
    """Hand our synthetic method 3, 4 and 5 files to Salient's own 1991
    DiskDoubler and read back what it wrote.

    This is the whole point of the module: our encoder and our decoder
    agreeing proves only that the transcription is self-consistent. An
    expander that shipped in 1991 turning the same bytes back into the
    subject is a second implementation, and the only one these three
    methods will ever get short of a real specimen.
    """
    s, work, img = session("expand-" + era, era)
    try:
        s.boot()
        s.shot("desktop", wait=5.0)
        s.mac.click(*VOLUME_ICON, double=True)
        s.shot("volume", wait=10.0)

        # 1. personalize once, then quit: the answer is written into the
        #    application's own resource fork on the work volume, so the
        #    dialog does not come back for the double-clicks below.
        if era == "1991":
            open_by_name(s, "DiskDoubler", "app")
            personalize(s)
            s.mac.command_key("q")
            s.shot("app-quit", wait=10.0)

        # 2. open each compressed file. The INIT registered the DDF2
        #    icons, which the --probe frame shows, so the Finder hands
        #    them to DiskDoubler.
        for prefix, tag in (("Rle", "rle"), ("Huff", "huff"),
                            ("Splay16", "splay16"), ("Splay", "splay")):
            # Click the window's title bar first. After the previous file
            # the front application may not be the Finder, and a Cmd-O
            # sent to whatever IS front opens ITS Open dialog — which is
            # how the first run of this mode expanded one file and then
            # typed the other three names into a standard file dialog.
            s.mac.click(200, 33)
            time.sleep(1.5)
            open_by_name(s, prefix, tag)
            s.shot("opened-" + tag, wait=25.0)
            # The expanded file's type is owned by nothing, so the Finder
            # puts up "could not be opened" — one Return, and we are
            # still in the Finder.
            s.mac.key("Return")
            time.sleep(1.5)
            s.shot("after-" + tag, wait=3.0)

        s.mac.click(*VOLUME_ICON)
        s.mac.command_key("y")                    # Put Away: flush
        s.shot("ejected", wait=15.0)
    finally:
        time.sleep(5)
        s.close()

    got = read_forks(img)
    bad = 0
    os.makedirs(s.shots, exist_ok=True)
    for name, method, ntrees in SUBJECTS:
        found = None
        for path, (ftype, creator, data, rsrc) in got.items():
            if path[-1] == name:
                found = (ftype, creator, data)
        if not found:
            print("ddencode: %-8s GONE from the volume" % name)
            bad += 1
            continue
        ftype, creator, data = found
        # Keep whatever came back: when it differs, the bytes ARE the
        # finding, and the first run of this mode threw them away.
        open(os.path.join(s.shots, name + ".out"), "wb").write(data)
        if header(data):
            print("ddencode: %-8s method %d — still compressed, %s/%s: the "
                  "expander did not take it" % (name, method, ftype, creator))
            bad += 1
        elif data == SUBJECT:
            print("ddencode: %-8s method %d — EXPANDED BY 1991, byte-exact "
                  "(%d B)" % (name, method, len(data)))
        else:
            print("ddencode: %-8s method %d — expanded to %d B, DIFFERS from "
                  "the %d B that went in" % (name, method, len(data),
                                             len(SUBJECT)))
            bad += 1
    print("ddencode: %d of %d confirmed by the %s expander"
          % (len(SUBJECTS) - bad, len(SUBJECTS),
             "1991" if era == "1991" else "4.1.1"))
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if bad else 0


EMIT = {"m3": (3, 256), "m4": (4, 256), "m5": (5, 256)}


def emit(which, out):
    """One container, byte-for-byte reproducible.

    These three are `fixtures/SOURCES.md` entries, so `check_docs.py`
    regenerates them on every CI run and fails if this file ever writes
    different bytes. Only the three Salient's own expander confirmed are
    registered — the 16-tree method 5 variant is NOT, because both
    expanders reject our construction of it (OPEN_ITEMS.md).
    """
    method, ntrees = EMIT[which]
    open(out, "wb").write(container(SUBJECT, method, ntrees))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true",
                    help="write the containers and round-trip them here")
    ap.add_argument("-o", dest="outdir", help="where to write them")
    ap.add_argument("--emit", choices=sorted(EMIT),
                    help="write one container to -o, reproducibly")
    ap.add_argument("--install", action="store_true",
                    help="System 7 + the 1991 INIT")
    ap.add_argument("--probe", action="store_true",
                    help="photograph the 1991 menu")
    ap.add_argument("--probe-app", action="store_true",
                    help="launch the application and photograph its menus")
    ap.add_argument("--expand", action="store_true",
                    help="let Salient's 1991 DiskDoubler read our files")
    ap.add_argument("--era", default="1991", choices=("1991", "411"),
                    help="which expander --expand uses (default 1991)")
    ap.add_argument("--keep", action="store_true", help="keep the work dir")
    a = ap.parse_args()
    if a.emit:
        if not a.outdir:
            raise SystemExit("ddencode: --emit needs -o <path>")
        return emit(a.emit, a.outdir)
    if a.build:
        return build(a.outdir)[1]
    if a.install:
        install()
        return 0
    if a.probe:
        probe(a.keep)
        return 0
    if a.probe_app:
        probe_app(a.keep)
        return 0
    if a.expand:
        return expand(a.keep, a.era)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
