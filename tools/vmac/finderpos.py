#!/usr/bin/env python3
"""finderpos.py — does the Finder keep the icon positions the shell restores?

    tools/vmac/finderpos.py -o DIR [--system Sys7.img] [--emu mv-4M]

The shell writes an entry's FInfo/DInfo whole, icon position included
(DECISIONS.md 2026-10-17, *the metadata, carried to the disk*). Whether the
Finder then SHOWS the icon there depends on the inited bit, 0x0100, which
the shell used to clear on everything. This extracts two subjects with the
autotest build of the CURRENT tree (tools/vmac/run.py --keep-disks), then
boots the Finder with the output volume, opens it and the folder, and
photographs both windows. One subject, an AppleLink package written by
tools/synth_sqp.py's writer, generated per run and not a corpus fixture:

  Spread     a folder with a window rectangle and icon view, holding three
             files placed where the Finder would not put them (far right,
             low left, middle), every one with flags 0x0100 set as a
             Finder leaves them;
  Kept App   THIS repository's own application (dist/MacExtract.bin's
             resource fork, type APPL, creator MExt, hasBundle 0x2000 |
             inited 0x0100), placed at (v 30, h 300) in the volume window
             — the case the bit was being cleared FOR: a Finder registers
             a bundle it has not inited.

After the windows it chooses Special > Shut Down, so whatever the Finder
wrote back (a new position, the inited bit) reaches the image, and reads
the catalog again with tools/vmac/hfscat.py, before and after.

    fp-1-volume.png   the Out window: Kept App and Spread
    fp-2-spread.png   the Spread window: the three placed files
    fp-3-special.png  the Shut Down pick
    fp-4-volume-app.png  System 7: the volume window again, Spread closed —
                      Kept App's icon, its own or a generic one

**What it cannot see.** Any Finder but this System's; how the Finder
places an icon it relocates (only that it did, from the catalog and the
frame); whether an application whose bundle was not registered is fixed
by a later rebuild of the desktop.
"""
import argparse
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
import run as R                                                 # noqa: E402
import interactive as I                                         # noqa: E402
import hfscat                                                   # noqa: E402
import synth_sqp as S                                           # noqa: E402

# Special > Shut Down: System 7.0.1 (spacesaver.py), System 6.0.8
# (arcmac.py; tools/vmac/README.md, *A run that drives the FINDER*).
SHUT_DOWN = {"Sys7.img": (225, 139), "System6.hfv": (175, 123)}

# (name, v, h): positions in the folder window no automatic placement uses
PLACED = (("Far Right", 20, 300), ("Low Left", 160, 10), ("Middle", 90, 150))


def subject():
    mb = open(os.path.join(REPO, "dist", "MacExtract.bin"), "rb").read()
    dl, rl = struct.unpack(">II", mb[83:91])
    rsrc = mb[128 + (dl + 127) // 128 * 128:][:rl]
    items = [S.item("Kept App", b"", rsrc, type=b"APPL", creator=b"MExt",
                    finder=0x2100, rest=struct.pack(">hhH", 30, 300, 0)),
             S.item("Spread", folder=True, finder=0x0100,
                    ctime=0xA0000001, mtime=0xA0000002,
                    # frRect top, left, bottom, right; frLocation; frView
                    # 0x0100, which System 7.0.1's own folders hold (its
                    # Extensions folder, read off Sys7.img)
                    rect=struct.pack(">4h", 60, 40, 300, 460),
                    rest=struct.pack(">hhH", 40, 150, 0x0100))]
    for i, (n, v, h) in enumerate(PLACED):
        items.append(S.item(n, S._text(300 + 50 * i, 70 + i), level=2,
                            finder=0x0100, rest=struct.pack(">hhH", v, h, 0)))
    return S.build(items, 1)


def catalog(img, label):
    rows = hfscat.records(open(img, "rb").read())
    for r in rows:
        if r["kind"] == hfscat.FILE:
            loc = struct.unpack(">hh", bytes.fromhex(r["finfo"])[10:14])
            print("finderpos: %-6s f %-18s flags %04x  location v %d h %d"
                  % (label, r["rel"], r["flags"], loc[0], loc[1]))
        else:
            fi = bytes.fromhex(r["finfo"])
            print("finderpos: %-6s d %-18s frFlags %04x  rect %s  view %04x"
                  % (label, r["rel"], struct.unpack(">H", fi[8:10])[0],
                     struct.unpack(">4h", fi[:8]), struct.unpack(">H", fi[14:16])[0]))
    return rows


def finder_session(a, work, disk, shots):
    """Boot the Finder with `disk`, open Out (and Spread on System 7),
    photograph into `shots` (nowhere if None), and Shut Down."""
    shots = shots or os.path.join(work, "seed-shots")
    os.makedirs(shots, exist_ok=True)
    mac = I.Mac(os.path.join(R.VMAC_HOME, a.system), a.emu, work,
                extra=(disk,))
    shot = lambda n: mac.shot(os.path.join(shots, n), scale="200%")
    try:
        if mac.settle(os.path.join(work, ".settle.png"), interval=5.0,
                      timeout=300) is None:
            raise SystemExit("finderpos: never reached the Finder")
        # Keyboard focus comes with the first origin() (interactive.py):
        # without it the typing below went to the X root and the Finder
        # saw nothing, the first run.
        mac.origin(cached=False)
        sys7 = a.system == "Sys7.img"
        if not sys7 and not a.out_at:
            shot("fp-0-desktop.png")
            print("finderpos: no --out-at; read Out off fp-0-desktop.png")
            return 2
        if sys7:
            mac._xdo("type", "--delay", "150", "Out")
            time.sleep(1.5)
            mac.command_key("o")
        else:
            mac.click(*(int(v) for v in a.out_at.split(",")), double=True)
        time.sleep(6.0)
        shot("fp-1-volume.png")
        if sys7:
            mac._xdo("type", "--delay", "150", "Spread")
            time.sleep(1.5)
            mac.command_key("o")
            time.sleep(6.0)
            shot("fp-2-spread.png")
            # Back to the volume window, whatever was open when the Finder
            # started (a seeded volume's window reopens at boot): the
            # application's icon — its own, or a generic one — is there.
            mac.command_key("w")
            time.sleep(3.0)
            shot("fp-4-volume-app.png")
        sx, sy = SHUT_DOWN[a.system]
        ox, oy = mac.origin()
        mac._xdo("mousemove", str(ox + sx), str(oy + 8))
        time.sleep(0.4)
        mac._xdo("mousedown", "1")
        time.sleep(1.2)
        mac._xdo("mousemove", str(ox + sx + 25), str(oy + sy))
        time.sleep(1.0)
        # Not mac.shot(): it parks the pointer off the screen, and a menu
        # released there picks nothing — the first run's image was torn
        # for exactly that.
        png = os.path.join(shots, "fp-3-special.png")
        for _ in range(40):
            if mac.dpy.screenshot(png):
                break
            time.sleep(0.5)
        mac._xdo("mouseup", "1")
        time.sleep(30.0)
    finally:
        mac.close()
    return 0


def registered(img):
    """What the Finder registered for creator MExt: System 6's `Desktop`
    resources holding it (APPL, BNDL, FREF, ICN#, the signature), or the
    count of the four bytes in System 7's `Desktop DB` — a B-tree nothing
    here parses, so a count and not a reading."""
    home = tempfile.mkdtemp(prefix="hfs-", dir=os.path.join(REPO, ".tmp"))
    env = dict(os.environ, HOME=home)
    try:
        subprocess.run(["hmount", img], env=env, capture_output=True)
        for name in ("Desktop", "Desktop DB"):
            mb = os.path.join(home, "f.bin")
            if subprocess.run(["hcopy", "-m", ":" + name, mb], env=env,
                              capture_output=True).returncode:
                continue
            d = open(mb, "rb").read()
            dl, rl = struct.unpack(">II", d[83:91])
            data = d[128:128 + dl]
            rs = d[128 + (dl + 127) // 128 * 128:][:rl]
            if name == "Desktop DB":
                print("finderpos: Desktop DB: %d B, `MExt` %d time(s)"
                      % (len(data), data.count(b"MExt")))
                continue
            doff, moff = struct.unpack(">II", rs[:8])
            m = rs[moff:]
            tl = struct.unpack(">H", m[24:26])[0]
            hits = []
            for i in range(struct.unpack(">H", m[tl:tl + 2])[0] + 1):
                t = m[tl + 2 + 8 * i:tl + 6 + 8 * i]
                n = struct.unpack(">H", m[tl + 6 + 8 * i:tl + 8 + 8 * i])[0] + 1
                ro = struct.unpack(">H", m[tl + 8 + 8 * i:tl + 10 + 8 * i])[0]
                for j in range(n):
                    r = m[tl + ro + 12 * j:tl + ro + 12 * j + 12]
                    off = int.from_bytes(r[5:8], "big")
                    ln = struct.unpack(">I", rs[doff + off:doff + off + 4])[0]
                    body = rs[doff + off + 4:doff + off + 4 + ln]
                    if t == b"MExt" or b"MExt" in body:
                        hits.append(t.decode("mac-roman"))
            print("finderpos: Desktop: resources naming MExt: %s"
                  % (", ".join(sorted(set(hits))) or "none"))
    finally:
        subprocess.run(["humount"], env=env, capture_output=True)
        shutil.rmtree(home, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--outdir", required=True)
    ap.add_argument("--system", default="Sys7.img")
    ap.add_argument("--emu", default="mv-4M")
    ap.add_argument("--seeded", action="store_true",
                    help="extract onto a volume the Finder has ALREADY put "
                         "its desktop on (booted once, opened, shut down), "
                         "the user's-disk case, rather than a blank one")
    ap.add_argument("--out-at", help="System 6: the Out volume's desktop "
                    "icon, Mac x,y — type-select is System 7 only. Without "
                    "it a System 6 run photographs the desktop and stops")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="finderpos-",
                            dir=os.path.join(REPO, ".tmp"))
    subj = os.path.join(work, "finderpos.pkg")
    open(subj, "wb").write(subject())

    # Extracted onto an 8 MB volume (a System 7 floppy has no Desktop DB),
    # the disks kept.
    seed = []
    if a.seeded:
        if a.system != "Sys7.img" and not a.out_at:
            print("finderpos: --seeded on System 6 needs --out-at")
            return 2
        blank = os.path.join(work, "seed.dsk")
        R.make_floppy(blank, "Out", size_kb=8192)
        I.calibrate(a.system)
        finder_session(a, work, blank, None)
        print("finderpos: seeded — the blank Out after one Finder session:")
        registered(blank)
        seed = ["--out-from", blank]
    r = subprocess.run([sys.executable, os.path.join(HERE, "run.py"),
                        "--system", a.system, "--keep-disks", "--expect",
                        "--out-kb", "8192"] + seed + [subj],
                       capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    kept = [l.split("disks kept in ")[1].strip()
            for l in r.stdout.splitlines() if "disks kept in " in l]
    if len(kept) != 1:
        print("finderpos: run.py kept %d run(s), wanted 1" % len(kept))
        return 1
    out = os.path.join(work, "finder.dsk")
    shutil.copy(os.path.join(kept[0], "out.dsk"), out)
    before = catalog(out, "before")

    I.calibrate(a.system)
    if finder_session(a, work, out, a.outdir) == 2:
        return 2
    after = catalog(out, "after")
    b = {r["rel"]: r["finfo"] for r in before}
    moved = [r["rel"] for r in after if b.get(r["rel"]) != r["finfo"]]
    print("finderpos: the Finder rewrote the Finder info of %d item(s): %s"
          % (len(moved), ", ".join(moved) or "none"))
    registered(out)
    shutil.copy(out, os.path.join(a.outdir, "finder-after.dsk"))
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
