#!/usr/bin/env python3
"""relaunch.py — two archives opened at once: are both extracted?

The eager overlay lifetime gives back the decoders an archive's format
cannot want, so a second archive of another format cannot be opened in the
same launch. Until 2026-10-12 the application quit after the first, and the
rest of the Finder's list was lost (DECISIONS.md 2026-10-11, *one archive
per launch*); since then it reads its decoders again between archives of
one list (2026-10-12, *the reload that the list needs*). This opens a
Compact Pro archive and a StuffIt one TOGETHER — the pair that failed on
the LC 475 — and grades both.

    relaunch.py --app build/mac-interactive/MacExtract.bin --expect both \
                --folder-at 115,107                     # System 6.0.8
    relaunch.py --app <a build before 2026-10-12> --expect first   # control
    relaunch.py ... --system Sys30.img --emu mv-512Ke --folder-at 174,95
    relaunch.py ... --system Sys7.img --folder-at In    # type-selected
    relaunch.py ... --multifinder
    relaunch.py ... --keep-inits --folder-at 115,107   # the stock folder
    relaunch.py ... --in-disk 1440 --disk-at 472,107 \
                --first derived-keyAhead.cpt --second derived-a2basic.dmg.sit

The two archives sit alone in a folder `In` (or, with `--in-disk`, alone at
the root of a second disk with room for their output), creator `MExt`, so
Select All and Open hand MacExtract exactly those two, in the Finder's
order (`a.*` first). With a `-D UNC_AT_HEAPLOG` build the `Heap Log` it
wrote beside the application is printed: free total, largest block and
every block that cannot move, at each archive's budget and around the
reload.

    r-1-desktop.png    booted, the volume open
    r-2-in.png         the folder open, both selected
    r-3-first.png      graded: the destination dialog for the first archive
    r-4-first-done.png its "Extraction complete." (or report)
    r-5-second.png     graded: the destination dialog again — or the
                       Finder, if nothing followed
    r-6-second-done.png
    r-7-end.png

Graded on the two dialogs (deskclaim.py's `which_dialog`) AND on every
entry of both archives being on the volume. **What it cannot see:** which
launch extracted which archive beyond the order of the frames; and an
entry refused for memory and one refused for a full disk look the same to
the volume check — read r-6, or give the output room with `--in-disk`.
"""
import argparse, os, shutil, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402
import interactive as I                                      # noqa: E402
import mkboot as MB                                          # noqa: E402
import deskclaim as D                                        # noqa: E402

FIRST = ("derived-keyAhead.cpt", "a.cpt", "PACT", ("keyAhead",))
SECOND = ("derived-ScrollbarPattern.sit", "b.sit", "SIT!",
          ("Scrollbar Pattern Editor", "About Scroll Bar Pattern Editor"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", required=True)
    ap.add_argument("--expect", required=True, choices=("both", "first"))
    ap.add_argument("-o", "--outdir", default="vmac-relaunch")
    ap.add_argument("--system", default="System6.hfv")
    ap.add_argument("--emu", default="mv-4M")
    ap.add_argument("--folder-at", default=None,
                    help="the In folder in the volume window, Mac x,y "
                         "(read it off r-1 once per system), or on System 7 "
                         "its name, type-selected")
    ap.add_argument("--first", help="fixture opened first (default "
                    + FIRST[0] + ")")
    ap.add_argument("--second", help="fixture opened second (default "
                    + SECOND[0] + ")")
    ap.add_argument("--quiet", type=float, default=60.0,
                    help="seconds of unchanged screen that mean an "
                         "extraction finished")
    ap.add_argument("--in-disk", type=int, metavar="KB",
                    help="put the two archives at the root of a second disk "
                         "of this size, so their output has room; open it at "
                         "--disk-at instead of the In folder")
    ap.add_argument("--disk-at", help="that disk's icon on the desktop, x,y")
    ap.add_argument("--keep-inits", action="store_true",
                    help="the stock System Folder as it is (run.py "
                         "--keep-inits): System 6.0.8's carries AppleShare's "
                         "Desktop Mgr INIT, and MultiFinder")
    ap.add_argument("--multifinder", action="store_true",
                    help="System 6 under MultiFinder")
    ap.add_argument("--launch-wait", type=float, default=25.0)
    a = ap.parse_args()

    first, second = FIRST, SECOND
    work0 = tempfile.mkdtemp(prefix="vmac-relaunch-names-")
    def spec(fixture, letter):
        ext = os.path.splitext(fixture)[1]
        typ = {".cpt": "PACT", ".sit": "SIT!", ".zip": "ZIP "}.get(ext, "????")
        names = tuple(sorted("/".join(c) for c in I.expected_names(
            os.path.join(R.REPO, "fixtures", fixture), work0)))
        return (fixture, letter + ext, typ, names)
    if a.first:
        first = spec(a.first, "a")
    if a.second:
        second = spec(a.second, "b")
    shutil.rmtree(work0, ignore_errors=True)
    I.calibrate(a.system)
    icons = I.FINDER_ICONS[a.system]
    os.makedirs(a.outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="vmac-relaunch-")
    shot = lambda mac, n: mac.shot(os.path.join(a.outdir, n), scale="200%")
    try:
        boot = os.path.join(work, "boot-relaunch.hfv")
        fx = lambda n: os.path.join(R.REPO, "fixtures", n)
        extra = ()
        keep = ("--keep-inits",) if a.keep_inits else ()
        if a.in_disk:
            R.sh(sys.executable, os.path.join(HERE, "mkboot.py"),
                 os.path.join(R.VMAC_HOME, a.system), a.app, boot, "--finder",
                 *keep)
            disk = os.path.join(work, "archives.dsk")
            R.make_floppy(disk, "Archives", size_kb=a.in_disk,
                          extras=[(fx(first[0]), first[1]),
                                  (fx(second[0]), second[1])])
            dh = MB.HFS(disk)
            try:
                for _f, n, t, _w in (first, second):
                    dh.run("hattrib", "-t", t, "-c", "MExt", dh.path(n))
            finally:
                dh.close()
            extra = (disk,)
        else:
            R.sh(sys.executable, os.path.join(HERE, "mkboot.py"),
                 os.path.join(R.VMAC_HOME, a.system), a.app, boot, "--finder",
                 *keep, "--data", f"{fx(first[0])}:In:{first[1]}",
                 "--data", f"{fx(second[0])}:In:{second[1]}")
        if a.multifinder:
            # As deskclaim.py --multifinder: the stock boot blocks already
            # name MultiFinder, and the Finder's Set Startup choice is in
            # `Finder Startup`.
            for n in ("MultiFinder", "DA Handler", "Backgrounder",
                      "Finder Startup"):
                tmp = os.path.join(work, n + ".bin")
                D.hfs_get(os.path.join(R.VMAC_HOME, a.system),
                          "System Folder:" + n, tmp)
                bh = MB.HFS(boot)
                try:
                    bh.run("hcopy", "-m", tmp, bh.path("System Folder", n))
                finally:
                    bh.close()
        if not a.in_disk:
            h = MB.HFS(boot)
            try:
                for _f, n, t, _w in (first, second):
                    h.run("hattrib", "-t", t, "-c", "MExt", h.path("In", n))
            finally:
                h.close()

        mac = I.Mac(boot, a.emu, work, extra=extra)
        try:
            if mac.settle(os.path.join(a.outdir, ".settle.png"),
                          interval=5.0, timeout=300) is None:
                raise SystemExit("relaunch: never reached the Finder")
            mac.click(*icons["volume"], double=True)
            time.sleep(4.0)
            shot(mac, "r-1-desktop.png")
            if a.in_disk:
                if not a.disk_at:
                    print("relaunch: no --disk-at; read it off r-1-desktop.png")
                    return 2
                mac.click(*(int(v) for v in a.disk_at.split(",")), double=True)
            elif not a.folder_at:
                print("relaunch: no --folder-at; read In off r-1-desktop.png")
                return 2
            elif "," in a.folder_at:
                mac.click(*(int(v) for v in a.folder_at.split(",")),
                          double=True)
            else:                         # System 7: type-select by name
                mac._xdo("type", "--delay", "150", a.folder_at)
                time.sleep(1.5)
                mac.command_key("o")
            time.sleep(4.0)
            mac.command_key("a")
            time.sleep(1.0)
            shot(mac, "r-2-in.png")
            mac.command_key("o")
            time.sleep(a.launch_wait)
            shot(mac, "r-3-first.png")
            I.accept_destination(mac)
            mac.settle(os.path.join(a.outdir, ".settle.png"),
                       interval=5.0, quiet=a.quiet, timeout=1200)
            shot(mac, "r-4-first-done.png")
            mac.key("Return")                     # "Extraction complete."
            time.sleep(a.launch_wait)             # the relaunch, if any
            shot(mac, "r-5-second.png")
            I.accept_destination(mac)
            mac.settle(os.path.join(a.outdir, ".settle.png"),
                       interval=5.0, quiet=a.quiet, timeout=1200)
            shot(mac, "r-6-second-done.png")
            mac.key("Return")
            time.sleep(a.launch_wait)
            shot(mac, "r-7-end.png")
        finally:
            mac.close()

        d3 = D.which_dialog(os.path.join(a.outdir, "r-3-first.png"))
        d5 = D.which_dialog(os.path.join(a.outdir, "r-5-second.png"))
        have = I.volume_names(extra[0] if a.in_disk else
                              os.path.join(work, "boot.hfv"))
        top = () if a.in_disk else ("In",)
        comp = lambda n: top + tuple(n.split("/"))
        log = os.path.join(work, "heaplog.txt")
        bh = MB.HFS(os.path.join(work, "boot.hfv"))
        try:
            if bh.run("hcopy", "-r", bh.path("Heap Log"), log,
                      check=False).returncode == 0:
                txt = open(log, "rb").read().decode("mac_roman")
                print("relaunch: Heap Log:\n  " + "\n  ".join(
                    l for l in txt.split("\r") if l))
        finally:
            bh.close()
        got1 = all(comp(n) in have for n in first[3])
        got2 = all(comp(n) in have for n in second[3])
        print(f"relaunch: {first[0]} then {second[0]}")
        print(f"relaunch: first archive: dialog {d3}, entries "
              f"{'on the volume' if got1 else 'MISSING'}")
        print(f"relaunch: second archive: dialog {d5}, entries "
              f"{'on the volume' if got2 else 'MISSING'}")
        if a.expect == "both":
            ok = d3 == "handed" and d5 == "handed" and got1 and got2
        else:
            ok = d3 == "handed" and got1 and d5 != "handed" and not got2
        print(f"relaunch: {'PASS' if ok else 'FAIL'} (expected {a.expect})")
        return 0 if ok else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
