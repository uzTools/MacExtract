#!/usr/bin/env python3
"""sitcomment.py — StuffIt 5's archive flag byte, bit 5.

`src/fmt_sit5.c` reads bit 5 of header byte 83 as "a comment block is
present", which moves the five-byte password hash four bytes along inside
the `SIT5_ARCH_CRYPTED` branch. Both halves of that are measured as of
2026-10-06 and this file is how:

  * **what the bit means** needed no emulator. `Tutorial Files/Sample
    Archive.sit`, which StuffIt Deluxe 5.5 ships inside its own
    installer, reads 0x30 and carries a 204-byte archive comment —
    `tools/derive_sit5crypt.py` grades it, and the payload it comes from
    is `tools/vmac/sitzip.py --payload 55`'s.
  * **where the hash then sits** needed an archive setting bits 5 AND 7,
    and nothing here had one. `--specimen` boots Mac OS 9.2 and has
    `tools/aesit/` — a Retro68 Apple event sender in aetran.c's shape —
    drive StuffIt Deluxe 7.0.3 into writing two.

    sitcomment.py --read            what each box offers for a comment
    sitcomment.py --aete            both scripting dictionaries, parsed
    sitcomment.py --specimen        boot, drive Deluxe, read the volume
    sitcomment.py --read-back IMG   re-read a finished run's volume
    sitcomment.py --probe           boot, launch Deluxe 5.5
    sitcomment.py --prepare86       build the three Mac OS 8.6 images
    sitcomment.py --macos86         the Mac OS 8.6 boot, for re-testing

**The menu is not the route and never was.** `Edit Comment…` has no
Command key in either later box, and a keyless menu item is not
selectable on either guest (tools/vmac/README.md, *What the pointer
cannot select*) — which is why this drives the Finder only, and lets the
Macintosh do everything after that.

**What this cannot see.** Whether an accepted event changed anything: an
`errn` of 0 says the term was understood and nothing more, so `aesit`
reads byte 83 back off the archive and prints it. Bit 6, which nothing
on this machine sets. And one application per boot — everything measured
through `--specimen` is about 7.0.3, since 5.5 still stops at `STR# 269`
#30 against an installation this project assembled rather than installed
(`--probe`; tools/vmac/README.md has what that would take).
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import run as R                                              # noqa: E402
import os9                                                   # noqa: E402
import guard                                                 # noqa: E402

CACHE = os.path.join(os.path.dirname(R.VMAC_HOME), "sitcomment")
MACOS86 = os.path.join(os.path.dirname(R.VMAC_HOME), "macos86")


# ------------------------------------------------------- reading the boxes

def _resources(path):
    """Resource fork -> {type: [(id, name, body)]}.

    Source: Inside Macintosh — More Macintosh Toolbox, *Resource Manager*,
    the resource file header and map layout. Nothing here is guessed: the
    offsets are the published ones, and the only consumer is this file."""
    import struct
    d = open(path, "rb").read()
    doff, moff, _dlen, mlen = struct.unpack(">IIII", d[:16])
    m = d[moff:moff + mlen]
    tloff = struct.unpack(">H", m[24:26])[0]
    nloff = struct.unpack(">H", m[26:28])[0]
    ntypes = struct.unpack(">H", m[tloff:tloff + 2])[0] + 1
    out = {}
    for i in range(ntypes):
        o = tloff + 2 + i * 8
        rt = m[o:o + 4]
        n = struct.unpack(">H", m[o + 4:o + 6])[0] + 1
        rlo = struct.unpack(">H", m[o + 6:o + 8])[0]
        lst = []
        for j in range(n):
            e = tloff + rlo + j * 12
            rid = struct.unpack(">h", m[e:e + 2])[0]
            noff = struct.unpack(">h", m[e + 2:e + 4])[0]
            doffs = struct.unpack(">I", b"\0" + m[e + 5:e + 8])[0]
            name = ""
            if noff >= 0:
                p = nloff + noff
                name = m[p + 1:p + 1 + m[p]].decode("mac_roman", "replace")
            ln = struct.unpack(">I", d[doff + doffs:doff + doffs + 4])[0]
            lst.append((rid, name, d[doff + doffs + 4:doff + doffs + 4 + ln]))
        out[rt.decode("mac_roman")] = lst
    return out


def _menu_items(body):
    """(title, [(item, command key)]) of one MENU resource."""
    p = 14
    tl = body[p]
    title = body[p + 1:p + 1 + tl].decode("mac_roman", "replace")
    p += 1 + tl
    items = []
    while p < len(body) and body[p]:
        il = body[p]
        txt = body[p + 1:p + 1 + il].decode("mac_roman", "replace")
        p += 1 + il
        key = body[p + 1]
        p += 4
        items.append((txt, chr(key) if 32 <= key < 127 else ""))
    return title, items


def _strings(body):
    n = int.from_bytes(body[0:2], "big")
    p, out = 2, []
    for _ in range(n):
        if p >= len(body):
            break
        ln = body[p]
        out.append(body[p + 1:p + 1 + ln].decode("mac_roman", "replace"))
        p += 1 + ln
    return out


# ------------------------------------------------- the scripting dictionary

class _AE:
    """A reader for one 'aete'. Source: Inside Macintosh —
    Interapplication Communication, *The Terminology Resources*: the
    'aete' layout, strings packed and every other field on a word
    boundary. The alignment is what makes it parse to the last byte, and
    `parse_aete` checks that it does."""

    def __init__(self, b):
        self.b, self.p = b, 0

    def align(self):
        if self.p & 1:
            self.p += 1

    def u16(self):
        import struct
        self.align()
        v = struct.unpack(">H", self.b[self.p:self.p + 2])[0]
        self.p += 2
        return v

    def s16(self):
        import struct
        self.align()
        v = struct.unpack(">h", self.b[self.p:self.p + 2])[0]
        self.p += 2
        return v

    def ot(self):
        self.align()
        v = self.b[self.p:self.p + 4]
        self.p += 4
        return v.decode("mac_roman", "replace")

    def ps(self):
        n = self.b[self.p]
        v = self.b[self.p + 1:self.p + 1 + n]
        self.p += 1 + n
        return v.decode("mac_roman", "replace")


def parse_aete(b):
    """{suites: [...]} — events, classes, properties and enumerations.

    Raises if anything is left over: an 'aete' that does not consume
    exactly its own length has been parsed wrongly, and a dictionary read
    wrongly is worse than no dictionary, because every four-character code
    in it would still look plausible."""
    r = _AE(b)
    r.p = 6
    suites = []
    for _ in range(r.u16()):
        s = {"name": r.ps(), "desc": r.ps(), "code": r.ot(),
             "level": r.s16(), "version": r.s16(),
             "events": [], "classes": [], "enums": []}
        for _ in range(r.u16()):
            e = {"name": r.ps(), "desc": r.ps(), "class": r.ot(),
                 "id": r.ot()}
            e["reply"] = (r.ot(), r.ps(), r.u16())
            e["direct"] = (r.ot(), r.ps(), r.u16())
            e["params"] = [(r.ps(), r.ot(), r.ot(), r.ps(), r.u16())
                           for _ in range(r.u16())]
            s["events"].append(e)
        for _ in range(r.u16()):
            c = {"name": r.ps(), "code": r.ot(), "desc": r.ps()}
            c["props"] = [(r.ps(), r.ot(), r.ot(), r.ps(), r.u16())
                          for _ in range(r.u16())]
            c["elems"] = []
            for _ in range(r.u16()):
                code = r.ot()
                c["elems"].append((code, [r.ot() for _ in range(r.u16())]))
            s["classes"].append(c)
        for _ in range(r.u16()):          # comparisons
            r.ps(), r.ot(), r.ps()
            r.align()
        for _ in range(r.u16()):
            code = r.ot()
            vals = []
            for _ in range(r.u16()):
                vals.append((r.ps(), r.ot(), r.ps()))
                r.align()
            s["enums"].append((code, vals))
        suites.append(s)
    if r.p != len(b):
        raise ValueError("'aete' left %d of %d bytes unread"
                         % (len(b) - r.p, len(b)))
    return {"suites": suites}


def read_aete():
    """Print both boxes' scripting dictionaries. No emulator.

    This is what says the specimen is three events rather than a menu:
    `comment` and `password` are settable properties of the archive in
    both boxes, and both declare a `stuff` event. The codes `aesit.c`
    sends are these."""
    rc = 0
    for ver, path in sorted(BOXES.items()):
        print("=" * 8, "StuffIt Deluxe", ver)
        if not os.path.exists(path):
            print("  no payload — run sitzip.py --payload %s" % ver)
            rc = 1
            continue
        for _rid, _name, body in _resources(path).get("aete", []):
            d = parse_aete(body)
            for s in d["suites"]:
                if not s["events"] and not s["classes"]:
                    continue
                print("  suite %r (%s)" % (s["name"], s["code"]))
                for e in s["events"]:
                    print("    event %-24r %s/%s  direct=%s reply=%s"
                          % (e["name"], e["class"], e["id"],
                             e["direct"][0], e["reply"][0]))
                    for pn, pk, pt, _pd, _pf in e["params"]:
                        print("        param %-22r %s %s" % (pn, pk, pt))
                for c in s["classes"]:
                    if len(c["props"]) == 1 and c["props"][0][1] == "c@#!":
                        continue          # the plural form of a class
                    print("    class %-20r %s" % (c["name"], c["code"]))
                    for pn, pc, pt, _pd, pf in c["props"]:
                        print("        prop %-24r %s %s%s"
                              % (pn, pc, pt,
                                 "" if pf & 0x1000 else "   (read-only)"))
                    for code, forms in c["elems"]:
                        print("        elem %s by %s" % (code, forms))
                for code, vals in s["enums"]:
                    print("    enum %s: %s"
                          % (code, ", ".join("%s=%s" % (n, c)
                                             for n, c, _ in vals)))
    return rc


BOXES = {
    "55": os.path.join(os.path.dirname(R.VMAC_HOME), "sitzip", "55",
                       "files", "StuffIt Deluxe™.rsrc"),
    "703": os.path.join(os.path.dirname(R.VMAC_HOME), "sitzip", "703",
                        "files", "StuffIt Deluxe.rsrc"),
}


def read_boxes():
    """What each box says about comments, without booting anything."""
    rc = 0
    for ver, path in sorted(BOXES.items()):
        print("=" * 8, "StuffIt Deluxe", ver)
        if not os.path.exists(path):
            print("  no payload — run sitzip.py --payload %s" % ver)
            rc = 1
            continue
        r = _resources(path)
        for rid, _name, body in r.get("MENU", []):
            title, items = _menu_items(body)
            for txt, key in items:
                if "omment" in txt and "Feedback" not in txt:
                    print("  MENU %-5d %-10s %-18r command key: %s"
                          % (rid, title, txt, repr(key) if key else "NONE"))
        for rid, name, body in r.get("STR#", []):
            for i, s in enumerate(_strings(body)):
                if "comments attached to this archive" in s:
                    print("  STR# %d (%s) #%d: %s" % (rid, name, i + 1, s))
        # The scripting interface, which is the route a keyless menu item
        # leaves open. The aete is walked for printable Pascal strings
        # rather than parsed: all this has to answer is whether `comment`
        # is a term the application declares.
        for _rid, _name, body in r.get("aete", []):
            i, terms = 0, []
            while i < len(body):
                n = body[i]
                if 2 <= n <= 70 and i + 1 + n <= len(body):
                    s = body[i + 1:i + 1 + n]
                    if all(32 <= c < 127 for c in s):
                        terms.append(s.decode())
                        i += 1 + n
                        continue
                i += 1
            for k, s in enumerate(terms):
                if s in ("comment", "password"):
                    print("  aete term %-9r near: %s"
                          % (s, " | ".join(terms[max(0, k - 2):k + 3])))
    return rc


# --------------------------------------------------------- Mac OS 8.6

BLESS_DIR_ID = 989        # the CD's `System Folder`, out of its own
                          # catalog record: key parent 2, name "System
                          # Folder", cdrType 1, valence 11 — which is
                          # what `hdir` lists. Nothing is guessed.


def prepare86():
    """Build the three Mac OS 8.6 images, each clearing one refusal.

    Source for the two format edits: Inside Macintosh — Files, the HFS
    master directory block (`drFndrInfo[0]` at MDB+0x6C is the blessed
    System Folder's directory ID, and this image carries 0), and
    `mkapmdisk.py`, which already clones a working Apple Partition Map.
    The third is a one-byte edit to a Forth literal in the ROM's own
    `<BOOT-SCRIPT>`, printed so it is never silent."""
    import re
    import shutil
    import struct
    sys.path.insert(0, HERE)
    import mkapmdisk                                          # noqa: E402
    iso = os.path.join(MACOS86, "MacOS8.6.iso")
    if not os.path.exists(iso):
        raise SystemExit("sitcomment: no %s — tools/vmac/README.md, "
                         "*Mac OS 8.6 under QEMU*, has the fetch" % iso)
    blessed = os.path.join(MACOS86, "MacOS8.6-blessed.iso")
    apm = os.path.join(MACOS86, "MacOS8.6-apm.img")
    pm31 = os.path.join(MACOS86, "MacOS8.6-apm-pm31.img")

    if not os.path.exists(blessed):
        shutil.copyfile(iso, blessed)
        with open(blessed, "r+b") as f:
            f.seek(1024 + 0x6C)
            was = struct.unpack(">I", f.read(4))[0]
            f.seek(1024 + 0x6C)
            f.write(struct.pack(">I", BLESS_DIR_ID))
        print("sitcomment: blessed %s (drFndrInfo[0] %d -> %d)"
              % (blessed, was, BLESS_DIR_ID))

    if not os.path.exists(apm):
        donor = os9.DISK
        start = mkapmdisk.find_hfs_start(donor)
        blocks = os.path.getsize(blessed) // mkapmdisk.BLK
        head = mkapmdisk.clone_head(donor, start + blocks, "Mac OS 8.6",
                                    start, blocks)
        with open(apm, "wb") as out, open(blessed, "rb") as src:
            out.write(head)
            shutil.copyfileobj(src, out)
        print("sitcomment: wrote %s (%d B, Apple_HFS at block %d)"
              % (apm, os.path.getsize(apm), start))

    if not os.path.exists(pm31):
        shutil.copyfile(apm, pm31)
        old, new = b"powermac1,1", b"powermac3,1"
        hits, off, prev = [], 0, b""
        with open(pm31, "r+b") as f:
            while True:
                buf = f.read(1 << 22)
                if not buf:
                    break
                d = prev + buf
                hits += [off - len(prev) + m.start()
                         for m in re.finditer(re.escape(old), d)]
                prev, off = d[-32:], off + len(buf)
            for h in hits:
                f.seek(h)
                f.write(new)
        if not hits:
            raise SystemExit("sitcomment: no %r in %s — the ROM's boot "
                             "script is not the one this was measured on"
                             % (old, pm31))
        print("sitcomment: patched %d copies of %r -> %r in %s"
              % (len(hits), old.decode(), new.decode(), pm31))
    print("sitcomment: ready. --macos86 boots %s" % pm31)


def macos86(outdir, machine, shots, interval):
    """Boot the retail Mac OS 8.6 install CD. See tools/vmac/README.md.

    Three gates were measured 2026-10-06 and each one is prepared here, so
    a re-test starts past them: the image carries no Apple Partition Map
    and no blessed folder, and the ROM's own boot script refuses the
    machine. What it stops on is Mac OS itself."""
    import subprocess
    import socket
    img = os.path.join(MACOS86, "MacOS8.6-apm-pm31.img")
    if not os.path.exists(img):
        raise SystemExit("sitcomment: no %s — tools/vmac/README.md, "
                         "*Mac OS 8.6 under QEMU*, builds it" % img)
    os.makedirs(outdir, exist_ok=True)
    # Monitor socket and QEMU's log in a run directory under <repo>/.tmp/
    # (tools/guard.py), pruned to the last few runs.
    scratch = guard.run_dir("sitcomment86")
    mon = os.path.join(scratch, "mon")
    log = os.path.join(scratch, "qemu.log")
    # snapshot=on: the prepared image is never written. It used to be
    # booted writable in place, so every probe changed the image the next
    # one started from.
    argv = ["qemu-system-ppc", "-M", machine, "-m", "512", "-boot", "c",
            "-g", "1024x768x32", "-display", "none",
            "-monitor", "unix:%s,server,nowait" % mon,
            "-drive", "file=%s,format=raw,media=disk,index=0,snapshot=on"
                      % img]
    print("sitcomment: " + " ".join(argv), flush=True)
    q = os9.Qemu.__new__(os9.Qemu)
    q.mon_path, q._scratchdir, q.proc = mon, scratch, None
    try:
        with open(log, "w") as f:
            q.proc = guard.spawn(argv, limit=interval * shots + 300,
                                 stdout=f, stderr=subprocess.STDOUT)
        for _ in range(240):
            if os.path.exists(mon):
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(mon)
                    s.close()
                    break
                except OSError:
                    pass
            if q.proc.poll() is not None:
                with open(log, errors="replace") as f:
                    raise SystemExit("sitcomment: %s:\n%s" % (
                        guard.why(q.proc, "qemu"), f.read()))
            time.sleep(0.5)
        for i in range(shots):
            time.sleep(interval)
            if q.proc.poll() is not None:
                print("sitcomment: qemu exited at t=%ds" % (interval * (i + 1)))
                break
            p = os.path.join(outdir, "t%03d.png" % (interval * (i + 1)))
            print("sitcomment: %s %s"
                  % (p, "ok" if q.shot(p) else "NO SCREENSHOT"), flush=True)
    finally:
        q.close()
    print("sitcomment: look at the frames. A boot that reached Mac OS "
          "prints its own failure on the OpenBIOS console, and a frame "
          "that merely stopped changing is not a boot.")


# ------------------------------------------------------------- the probe

def probe(outdir, args):
    """Assemble StuffIt Deluxe 5.5 onto Mac OS 9 and launch it."""
    import sitzip
    sitzip.DIST["55"]["app"] = "StuffIt Deluxe™"
    sitzip.APP_NAME = APP_NAME
    os.makedirs(outdir, exist_ok=True)
    boot, xfer = sitzip.assemble("55", outdir)
    q = None
    try:
        # The boot volume with snapshot=on, as in sitzip.run().
        q = os9.Qemu([boot, xfer], os.path.join(outdir, "mon.sock"),
                     limit=int(args.boot_wait + args.launch_wait) + 900,
                     snapshot={boot})
        scratch = os.path.join(outdir, ".settle.png")
        waited = q.settle(scratch, timeout=args.boot_wait)
        if waited is None:
            raise SystemExit("sitcomment: the screen never settled, or "
                             "qemu exited")
        print("sitcomment: desktop settled after ~%.0fs" % waited, flush=True)

        def shot(tag, wait=0.0):
            if wait:
                time.sleep(wait)
            p = os.path.join(outdir, tag + ".png")
            q.shot(p)
            print("sitcomment: %s" % p, flush=True)
            return p

        # The same opening sitzip.py uses, and for its reason: this boot
        # volume puts up no Setup Assistant, so a blind Return would edit
        # the selected icon's NAME instead.
        q.key("esc")
        front = shot("10-finder", wait=2.0)
        q.key(*sitzip.VOLUME[:3].lower(), "meta_l-down")
        q.wait_change(front, os9.WINDOW_RECT, scratch, timeout=90.0)
        vol = shot("11-volume")
        # Type-to-select: "stu" is unique on this volume, which carries
        # the application and one subject named `Subject`.
        q.key("s", "t", "u", "meta_l-down")
        frac, secs = q.wait_change(vol, os9.WINDOW_RECT, scratch,
                                   timeout=args.launch_wait, poll=10.0)
        print("sitcomment: %.4f changed in %.0fs after the launch"
              % (frac, secs), flush=True)
        up = shot("12-launched", wait=20.0)
        shot("13-settled", wait=60.0)
        # 5.5's installation alert draws OK as the DEFAULT button — the
        # heavy border in `12-launched.png` — so Return reaches it and no
        # pointer is needed. Whether it is a wall or a nag is the next
        # question and this is the whole of it: the application's own menu
        # bar is already up BEHIND the alert.
        q.key("ret")
        back = shot("14-dismissed", wait=20.0)
        # ⌘S is `Archive ▸ Stuff...` in `MENU` 131, which is the one
        # command on the route to a comment that has a Command key at all.
        q.key("meta_l-s")
        q.wait_change(back, os9.WINDOW_RECT, scratch, timeout=120.0)
        shot("15-stuff", wait=10.0)
    finally:
        if q:
            q.close()
    print("\nsitcomment: LOOK at every frame. A registration sheet, an "
          "alert, a Finder desktop and a document window are four different "
          "answers and none of them is 'the screen changed'.")


# ------------------------------------------------------- the specimen run

# The two archives `aesit` works on, both written by Aladdin's own
# software: one carries an archive comment and no password, the other a
# password and no comment, and either one becomes the specimen if StuffIt
# Deluxe will add the other half. `comment-sample.sit` is lifted out of
# StuffIt Deluxe 5.5's own `Tutorial Files` by `sitzip.py --payload 55`;
# the encrypted three are DropStuff 5.0.1's (FORMATS.md, *StuffIt 5's
# RC4*).
SPECIMENS = os.path.join(os.path.dirname(R.VMAC_HOME), "sit5", "specimens")
SPEC_IN = [("comment-sample.sit", "Comment.sit"),
           ("enc-swordfish.sit", "Encrypted.sit")]
SPEC_SUBJECT = (b"The subject one phase adds to an archive, so that setting "
                b"a password makes StuffIt rewrite it.\r")
SPEC_TYPE = ("SIT5", "SIT!")        # what 5.5 stamps its own archive with


def build_aesit():
    """Cross-compile the Apple event sender. Returns its MacBinary."""
    import subprocess
    src = os.path.join(REPO, "tools", "aesit")
    build = os.path.join(REPO, "build", "aesit")
    mb = os.path.join(build, "aesit.bin")
    chain = os.environ.get("RETRO68") or "/opt/Retro68-build/toolchain"
    cmakefile = os.path.join(chain, "m68k-apple-macos", "cmake",
                             "retro68.toolchain.cmake")
    if not os.path.exists(cmakefile):
        raise SystemExit("sitcomment: no Retro68 toolchain (set RETRO68); "
                         "looked for %s" % cmakefile)
    subprocess.run(["cmake", "-B", build, "-S", src,
                    "-DCMAKE_TOOLCHAIN_FILE=" + cmakefile],
                   check=True, capture_output=True)
    subprocess.run(["cmake", "--build", build], check=True,
                   capture_output=True)
    if not os.path.exists(mb):
        raise SystemExit("sitcomment: aesit did not build")
    print("sitcomment: built %s (%d B)" % (mb, os.path.getsize(mb)))
    return mb


def specimen(outdir, args):
    """Boot Mac OS 9, let `aesit` drive StuffIt Deluxe, read the volume.

    The application is launched by `aesit` rather than by the harness, for
    aetran.c's reason: a coordinate cannot miss if there is no coordinate.
    All this drives is the Finder, with type-to-select and Cmd-Down."""
    import sitzip
    from arcmac import macbinary
    ver = args.box
    d = sitzip.DIST[ver]
    # The name on the volume is the name `aesit.c` has compiled in, and
    # 5.5's really does carry a trademark sign. `macbinary()` encodes it
    # to MacRoman 0xAA, which is the byte `kApp55` holds.
    appname = "StuffIt Deluxe" if ver == "703" else "StuffIt Deluxe\u2122"
    d["app"] = appname
    sitzip.APP_NAME = appname
    os.makedirs(outdir, exist_ok=True)

    # NOT `subject.bin`: `sitzip.assemble` writes its own zip subject to
    # that name in the same directory, and the one written second wins.
    extra = [(build_aesit(), "aesit")]
    for src, leaf in SPEC_IN:
        p = os.path.join(SPECIMENS, src)
        if not os.path.exists(p):
            raise SystemExit("sitcomment: no %s — TESTING.md, "
                             "*derive_sit5crypt.py*, says where it comes "
                             "from" % p)
        mb = os.path.join(outdir, leaf + ".bin")
        open(mb, "wb").write(macbinary(leaf, SPEC_TYPE[0], SPEC_TYPE[1],
                                       open(p, "rb").read()))
        extra.append((mb, leaf))
    sub = os.path.join(outdir, "aesubject.bin")
    open(sub, "wb").write(macbinary("Subject", "TEXT", "ttxt", SPEC_SUBJECT))
    extra.append((sub, "Subject"))
    boot, xfer = sitzip.assemble(ver, outdir, extra=extra)

    q = None
    try:
        # The boot volume with snapshot=on, as in sitzip.run(); `aesit`
        # writes its results to the transfer volume, which is real.
        q = os9.Qemu([boot, xfer], os.path.join(outdir, "mon.sock"),
                     limit=int(args.boot_wait + args.launch_wait
                               + args.interval * args.shots) + 900,
                     snapshot={boot})
        scratch = os.path.join(outdir, ".settle.png")
        waited = q.settle(scratch, timeout=args.boot_wait)
        if waited is None:
            raise SystemExit("sitcomment: the screen never settled, or "
                             "qemu exited")
        print("sitcomment: desktop settled after ~%.0fs" % waited, flush=True)

        def shot(tag, wait=0.0):
            if wait:
                time.sleep(wait)
            p = os.path.join(outdir, tag + ".png")
            q.shot(p)
            print("sitcomment: %s" % p, flush=True)
            return p

        q.key("esc")
        front = shot("10-finder", wait=2.0)
        q.key(*sitzip.VOLUME[:3].lower(), "meta_l-down")
        q.wait_change(front, os9.WINDOW_RECT, scratch, timeout=90.0)
        vol = shot("11-volume")
        # `aes` rather than `ae`: a second run finds `AEResult` on the
        # volume and type-to-select is case-blind.
        q.key("a", "e", "s", "meta_l-down")
        frac, secs = q.wait_change(vol, os9.WINDOW_RECT, scratch,
                                   timeout=args.launch_wait, poll=10.0)
        print("sitcomment: %.4f changed in %.0fs after launching aesit"
              % (frac, secs), flush=True)
        shot("12-aesit")
        # Nothing after this is driven. `aesit` launches StuffIt Deluxe,
        # sends its ladder of events and unmounts the volume itself, so
        # the frames are a record and not a sequence of steps: one every
        # `--interval` seconds until `--shots` of them, or until the log
        # says it is done.
        for i in range(args.shots):
            shot("%02d-t%04d" % (13 + i, args.interval * (i + 1)),
                 wait=args.interval)
    finally:
        if q:
            q.close()

    read_back(xfer, outdir)


def read_back(xfer, outdir):
    """Everything the run left on the transfer volume, off the disk image.

    The volume is read rather than the screen for the reason the Mac OS 9
    tier gives: a frame showing a window is not a file. `aesit` unmounts
    the volume before it stops, which is what flushes it."""
    import subprocess
    import tempfile
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    r = subprocess.run(["hmount", xfer, "1"], capture_output=True, env=env,
                       text=True)
    if r.returncode:
        print("sitcomment: hmount %s: %s — the guest never flushed it"
              % (xfer, r.stderr.strip()))
        return
    name = r.stdout.split('"')[1]
    out = os.path.join(outdir, "volume")
    os.makedirs(out, exist_ok=True)
    listing = subprocess.run(["hdir", "-a", name + ":"], capture_output=True,
                             env=env, text=True).stdout
    print("sitcomment: the transfer volume now holds:\n" + listing)
    # `hdir -a` prints kind, type/creator, both fork sizes and a
    # three-field date before the name, which may itself hold spaces.
    for line in listing.splitlines():
        f = line.split(None, 7)
        if len(f) < 8 or f[0] != "f":
            continue
        leaf = f[7]
        for want, mode in (("AEResult", "-t"), (".sit", "-r")):
            if want in leaf:
                dest = os.path.join(out, leaf.replace("/", "_"))
                subprocess.run(["hcopy", mode, "%s:%s" % (name, leaf), dest],
                               capture_output=True, env=env)
    subprocess.run(["humount"], capture_output=True, env=env)
    log = os.path.join(out, "AEResult")
    if os.path.exists(log):
        print("sitcomment: AEResult ---------------------------")
        print(open(log, "rb").read().decode("mac_roman", "replace")
              .replace("\r", "\n"))
        print("---------------------------------------------")
    else:
        print("sitcomment: NO AEResult — read the frames: an application "
              "waiting on a dialog has written every step before it")
    for f in sorted(os.listdir(out)):
        print("sitcomment: %s (%d B)"
              % (f, os.path.getsize(os.path.join(out, f))))


APP_NAME = "StuffIt Deluxe"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--read", action="store_true",
                    help="what each box says about comments; no emulator")
    ap.add_argument("--aete", action="store_true",
                    help="both boxes' scripting dictionaries; no emulator")
    ap.add_argument("--probe", action="store_true",
                    help="boot Mac OS 9, launch StuffIt Deluxe 5.5")
    ap.add_argument("--specimen", action="store_true",
                    help="boot Mac OS 9 and have aesit drive StuffIt Deluxe")
    ap.add_argument("--box", default="703", choices=("55", "703"),
                    help="which StuffIt Deluxe --specimen drives")
    ap.add_argument("--read-back", metavar="TRANSFER.IMG",
                    help="re-read a finished run's transfer volume")
    ap.add_argument("--prepare86", action="store_true",
                    help="build the three Mac OS 8.6 images")
    ap.add_argument("--macos86", action="store_true",
                    help="boot the Mac OS 8.6 install CD")
    ap.add_argument("--machine", default="mac99,via=pmu")
    ap.add_argument("--shots", type=int, default=12)
    ap.add_argument("--interval", type=int, default=20)
    ap.add_argument("--boot-wait", type=float, default=1200.0)
    ap.add_argument("--launch-wait", type=float, default=420.0)
    ap.add_argument("-o", "--out", default=os.path.join(CACHE, "out"))
    args = ap.parse_args()
    if args.read:
        return read_boxes()
    if args.aete:
        return read_aete()
    if args.read_back:
        return read_back(args.read_back, args.out)
    if args.specimen:
        return specimen(args.out, args)
    if args.prepare86:
        return prepare86()
    if args.macos86:
        return macos86(args.out, args.machine, args.shots, args.interval)
    if args.probe:
        return probe(args.out, args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
