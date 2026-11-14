#!/usr/bin/env python3
"""lockedfloppy.py — what a Finder shows of a floppy, locked or writable.

Boots a system with one or more floppy images in the drives after it and
runs a short list of steps — clicks and screenshots — so the volume
window, a folder's window and a launch can be photographed on each System.

    lockedfloppy.py dist/MacExtract-800K.img --system Sys30.img --emu mv-1M \\
        -o DIR --steps "settle:desk dclick:472,112 wait:8 shot:vol"
    lockedfloppy.py IMG --writable --save DIR/after.img ...

Each image is attached as a copy in the run's work directory. **Locked**
(the default) is a copy made read-only, which Mini vMac then inserts as a
locked disk (its X11 glue: `fopen(..., "rb+")` fails, it falls back to
"rb" and marks the disk locked); the copy's SHA-256 is compared with the
original's after the run and printed, so a run that changed a locked disk
says so. `--writable` attaches writable copies, and `--save` keeps what
the Finder wrote on the first image once the emulator is gone. An image
written `rw:PATH` is attached writable whatever `--writable` says (an
archive's floppy beside the locked MacExtract one), and `--save-all DIR`
keeps every image as the run left it.

Steps, separated by spaces, Mac-screen coordinates:

    settle:NAME      screenshot until the screen is still (the boot)
    shot:NAME        a screenshot, NAME.png
    wait:S           sleep S seconds
    click:X,Y        dclick:X,Y      drag:X0,Y0,X1,Y1
    cmd:K            Command-K       key:K  an xdotool key (Return)

Not self-checking: the frames are the result, and are looked at.

What it CANNOT see: anything the Finder keeps in memory and does not draw;
a real floppy drive (Mini vMac's locked disk is a read-only file, the
write-protect tab's equivalent as the Sony driver reports it); and what a
Finder does on a second insertion of the same disk, unless steps eject and
the image is attached again, which this does not do.
"""
import argparse, hashlib, os, shutil, stat, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402
import interactive as I                                      # noqa: E402
import guard                                                 # noqa: E402


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+")
    ap.add_argument("--system", default="System6.hfv")
    ap.add_argument("--emu", default="mv-4M")
    ap.add_argument("-o", "--outdir", required=True)
    ap.add_argument("--steps", required=True)
    ap.add_argument("--writable", action="store_true")
    ap.add_argument("--save", help="keep the first image as the run left it")
    ap.add_argument("--save-all", help="keep every image, in this directory")
    ap.add_argument("--flush", type=float, default=20.0,
                    help="seconds to wait before stopping the emulator")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    work = guard.run_dir("lockedfloppy")
    attached, before = [], []
    rw = [img.startswith("rw:") for img in a.images]
    a.images = [img[3:] if w else img for img, w in zip(a.images, rw)]
    for k, img in enumerate(a.images):
        dst = os.path.join(work, f"d{k}-" + os.path.basename(img))
        shutil.copyfile(img, dst)
        before.append(sha(img))
        if not (a.writable or rw[k]):
            os.chmod(dst, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        attached.append(dst)
    mac = I.Mac(os.path.join(R.VMAC_HOME, a.system), a.emu, work, extra=attached)
    try:
        for st in a.steps.split():
            op, _, arg = st.partition(":")
            if op == "settle":
                t = mac.settle(os.path.join(a.outdir, arg + ".png"),
                               interval=8.0, timeout=400.0)
                print(f"lockedfloppy: {arg} settled after {t}")
            elif op == "shot":
                mac.shot(os.path.join(a.outdir, arg + ".png"))
            elif op == "wait":
                time.sleep(float(arg))
            elif op in ("click", "dclick"):
                x, y = (int(v) for v in arg.split(","))
                mac.click(x, y, double=(op == "dclick"))
            elif op == "drag":
                mac.drag(*(int(v) for v in arg.split(",")))
            elif op == "cmd":
                mac.command_key(arg)
            elif op == "key":
                mac.key(arg)
            else:
                raise SystemExit(f"lockedfloppy: unknown step {st!r}")
        time.sleep(a.flush)
    finally:
        mac.close()
    for k, (img, dst, h) in enumerate(zip(a.images, attached, before)):
        now = sha(dst)
        print(f"lockedfloppy: {os.path.basename(img)}"
              f"{'' if a.writable or rw[k] else ' (locked)'}: "
              f"{'UNCHANGED' if now == h else 'CHANGED'} by the run")
        if a.save_all:
            os.makedirs(a.save_all, exist_ok=True)
            shutil.copyfile(dst, os.path.join(a.save_all, os.path.basename(img)))
    if a.save:
        shutil.copyfile(attached[0], a.save)
        print(f"lockedfloppy: saved {a.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
