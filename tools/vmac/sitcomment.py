#!/usr/bin/env python3
"""sitcomment.py — make the archive that grades `fmt_sit5.c`'s bit 5.

The specimen wanted is one file: a StuffIt 5 archive that is **encrypted
AND carries an archive comment**, because the only place the engine acts
on archive-flag bit 5 is the password-hash offset inside the
`SIT5_ARCH_CRYPTED` branch (`src/fmt_sit5.c`). Three DropStuff 5.0.1
archives already grade bits 7 and 4; none sets bit 5, and nothing here
had written a comment.

**The route this replaces.** OPEN_ITEMS.md said the only software that
can set it is StuffIt Deluxe 5.0.1's comment UI, which Mac OS 9.2
refuses to run, so the row wanted a Mac OS 8.6 boot. Both halves are
wrong: 8.6 does not boot here for a firmware reason nothing about
StuffIt can move (`--macos86`, below, and tools/vmac/README.md,
*Mac OS 8.6 under QEMU*), and 5.0.1 is not the only comment UI. StuffIt
Deluxe **5.5** and **7.0.3 Classic** both carry `Edit Comment…` in their
Archive menu, both describe a clickable comments area in the archive
window, and both declare `comment` as a scriptable property of the
archive — read out of their own resources, no emulator:

    sitcomment.py --read            MENU, STR# and aete of both boxes

Both are already assembled into a Mac OS 9 System Folder by
`sitzip.py`, whose Expander run works, so the box this needs is one that
boots here today.

    sitcomment.py --probe -o <dir>      boot, launch Deluxe 5.5, photograph
    sitcomment.py --prepare86           build the three Mac OS 8.6 images
    sitcomment.py --macos86 -o <dir>    the Mac OS 8.6 boot, for re-testing

**What `--probe` measured, 2026-10-06.** StuffIt Deluxe 5.5 **launches**
on Mac OS 9.2 — its own menu bar, `Archive` on it — so what 9.2 refuses
is 5.0.1 and not Deluxe. It then refuses to RUN on an assembled
installation: `STR# 269` #30, *"This copy of StuffIt Deluxe™ has not
been properly installed"*. That is a wall and not a nag — the alert's OK
is the default button, Return reaches it with no pointer, and dismissing
it quits the application. `sitzip.py`'s Expander runs on the same
volume, so the engine and the seventeen translators are not what is
missing; the same payload carries `Aladdin Compression™`, `Compression
Extension`, `True Finder Integration™`, `Magic Menu™` and a `Text
Encoding Converter`, none of them placed, and `STR# 269` #34 names the
last by itself.

**What is still unmeasured, in order:** which piece the check wants;
whether Stuff will encrypt without a dialog Return cannot reach; and
whether a comment lands in the ARCHIVE header rather than per entry.

**What this cannot see.** Which of those pieces `STR# 269` #30 is
checking for — the alert names none, and nothing here has disassembled
the check, so placing all five answers *whether* and not *which*. And a
frame after a launch is not evidence that anything in the application
works: a dismissed alert and a quit application are the same frame minus
the menu bar, which is the only part of it worth reading. The menu route
is separately measured dead on both guests — `Edit Comment…` has no
Command key in either box, and a keyless menu item is not selectable
here (tools/vmac/README.md, *What the pointer cannot select*) — so the
two routes left to a comment are the archive window's comments AREA,
which is a click, and an Apple event, which is `tools/aetran/`'s
mechanism.
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
    import tempfile
    img = os.path.join(MACOS86, "MacOS8.6-apm-pm31.img")
    if not os.path.exists(img):
        raise SystemExit("sitcomment: no %s — tools/vmac/README.md, "
                         "*Mac OS 8.6 under QEMU*, builds it" % img)
    os.makedirs(outdir, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="sitcomment-")
    mon = os.path.join(scratch, "mon")
    argv = ["qemu-system-ppc", "-M", machine, "-m", "512", "-boot", "c",
            "-g", "1024x768x32", "-display", "none",
            "-monitor", "unix:%s,server,nowait" % mon,
            "-drive", "file=%s,format=raw,media=disk,index=0" % img]
    print("sitcomment: " + " ".join(argv), flush=True)
    q = os9.Qemu.__new__(os9.Qemu)
    q.mon_path, q._scratchdir = mon, scratch
    q.proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True,
                              start_new_session=True)
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
            raise SystemExit("sitcomment: qemu exited:\n" + q.proc.stdout.read())
        time.sleep(0.5)
    try:
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
    q = os9.Qemu([boot, xfer], os.path.join(outdir, "mon.sock"))
    try:
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
        q.close()
    print("\nsitcomment: LOOK at every frame. A registration sheet, an "
          "alert, a Finder desktop and a document window are four different "
          "answers and none of them is 'the screen changed'.")


APP_NAME = "StuffIt Deluxe"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--read", action="store_true",
                    help="what each box says about comments; no emulator")
    ap.add_argument("--probe", action="store_true",
                    help="boot Mac OS 9, launch StuffIt Deluxe 5.5")
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
