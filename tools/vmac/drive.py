#!/usr/bin/env python3
"""drive.py — boot a Mac and take commands from a file, one per line.

    drive.py BOOT.hfv EMU OUTDIR [extra disks...]

Written for uzTools/MacExtract issue #1 (2026-10-21), where the step that
bombed could only be found by looking at each screen before choosing the
next click: the emulator stays up between commands, and every `shot` is a
frame to read. It settles to the first static screen, writes 0-boot.png,
then waits for lines appended to OUTDIR/cmd. Nothing here grades anything;
the screenshots are the result.

Commands are appended to OUTDIR/cmd; each is answered in OUTDIR/log and
the screenshot named by `shot NAME`. Commands:
    click X Y        single click at Mac coords
    dclick X Y       double click
    key KEYS         xdotool key name(s): Return, period ...
    cmd CH           Command-CH
    type TEXT        type text
    shot NAME        screenshot to OUTDIR/NAME.png (2x)
    settle NAME SECS screenshot until unchanged for SECS, then NAME.png
    sleep SECS
    quit
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import interactive as I                                   # noqa: E402
import run as R                                           # noqa: E402

boot, emu, outdir, *extra = sys.argv[1:]
os.makedirs(outdir, exist_ok=True)
cmdf = os.path.join(outdir, "cmd")
logf = os.path.join(outdir, "log")
open(cmdf, "a").close()
def log(m):
    with open(logf, "a") as f:
        f.write(time.strftime("%H:%M:%S ") + m + "\n")
I.Mac.limit = 3600
mac = I.Mac(boot, emu, outdir, extra=tuple(extra))
try:
    log("booted; settling")
    t = mac.settle(os.path.join(outdir, ".settle.png"), interval=5.0, timeout=300)
    mac.shot(os.path.join(outdir, "0-boot.png"), scale="200%")
    log(f"settled after {t}; ready")
    done = 0
    while True:
        lines = open(cmdf).read().splitlines()
        if len(lines) <= done:
            time.sleep(1.0); continue
        c = lines[done]; done += 1
        a = c.split()
        if not a: continue
        try:
            if a[0] == "click":   mac.click(int(a[1]), int(a[2]))
            elif a[0] == "dclick": mac.click(int(a[1]), int(a[2]), double=True)
            elif a[0] == "key":   mac.key(" ".join(a[1:]))
            elif a[0] == "cmd":   mac.command_key(a[1])
            elif a[0] == "type":  mac._xdo("type", "--delay", "150", " ".join(a[1:]))
            elif a[0] == "shot":  mac.shot(os.path.join(outdir, a[1] + ".png"), scale="200%")
            elif a[0] == "settle":
                t = mac.settle(os.path.join(outdir, ".settle.png"), interval=5.0,
                               quiet=float(a[2]), timeout=900)
                mac.shot(os.path.join(outdir, a[1] + ".png"), scale="200%")
                log(f"settled {t}")
            elif a[0] == "sleep": time.sleep(float(a[1]))
            elif a[0] == "quit":  break
            log("done: " + c)
        except Exception as e:
            log(f"error on {c!r}: {e!r}")
finally:
    mac.close()
    log("closed")
