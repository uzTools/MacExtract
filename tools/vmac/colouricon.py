#!/usr/bin/env python3
"""colouricon.py — boot a COLOUR Finder and photograph what it does.

Mini vMac emulates a Macintosh II as well as a Plus, at a depth chosen when
it is built: `setup.sh` builds `mv-II16` (`-depth 2`, 16 colours) and
`mv-II256` (`-depth 3`, 256), both on the Mac II ROM `MacII.ROM`. That is
how the application's `icl4`/`ics4`, which no other tier here can draw, and
its icons SELECTED, were first seen (DECISIONS.md 2026-10-11, *the icon that
did not darken*).

    colouricon.py [--emu mv-II16|mv-II256] IMAGE OUTPREFIX STEP...

IMAGE is a System 7 that runs on a Mac II — the stock `Sys7.img` is a
"Minimal" Plus install and refuses with *"will not work on this Macintosh
model"*. Steps, in Mac screen coordinates (the screen is 640x480):

    c:X,Y   click            d:X,Y   double-click
    k:KEYS  xdotool keys     w:SECS  wait
    s       photograph, as OUTPREFIX-N.png

**What it cannot see.** It clicks fixed coordinates and photographs
whatever is there: LOOK at every frame, because a click that missed
photographs as a plausible Finder. The machine is a Mac II at one depth,
so it says nothing about a different video card's palette, nor about
4-grey or millions — and nothing about System 7.6.1, which is what the
LC 475 runs. The emulator is killed rather than shut down, so the next
boot of the same image shows the "not shut down properly" alert; copy a
fresh image per run.
"""
import argparse, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                   # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emu", default="mv-II16")
    ap.add_argument("--boot-wait", type=float, default=90.0)
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("steps", nargs="*")
    a = ap.parse_args()

    emu = os.path.join(R.VMAC_HOME, a.emu, "minivmac")
    rom = os.path.join(R.VMAC_HOME, "MacII.ROM")
    for p in (emu, rom):
        if not os.path.exists(p):
            raise SystemExit(f"colouricon: no {p} — run setup.sh")
    dpy = R.Display()
    env = dict(os.environ, DISPLAY=dpy.name)
    proc = subprocess.Popen([emu, "-r", rom, a.image], env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)

    def xdo(*args):
        subprocess.run(["xdotool", *args], env=env, capture_output=True)

    try:
        time.sleep(a.boot_wait)
        geo = subprocess.run(["xdotool", "getwindowgeometry", dpy.window()],
                             env=env, capture_output=True, text=True).stdout
        ox, oy = map(int, geo.split("Position:")[1].split()[0].split(","))
        n = 0
        for st in a.steps:
            kind, _, arg = st.partition(":")
            if kind in ("c", "d"):
                x, y = map(int, arg.split(","))
                xdo("mousemove", str(ox + x), str(oy + y))
                time.sleep(0.4)
                xdo("click", "--repeat", "2" if kind == "d" else "1",
                    "--delay", "120", "1")
                time.sleep(1.5)
            elif kind == "w":
                time.sleep(float(arg))
            elif kind == "k":
                xdo("key", "--delay", "150", *arg.split())
                time.sleep(1.5)
            elif kind == "s":
                dpy.screenshot("%s-%d.png" % (a.out, n))
                n += 1
            else:
                raise SystemExit(f"colouricon: unknown step {st!r}")
        print(f"colouricon: {n} frame(s), screen origin {ox},{oy}")
    finally:
        proc.terminate()
        proc.wait()
        dpy.close()


if __name__ == "__main__":
    main()
