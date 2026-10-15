#!/usr/bin/env python3
"""os9probe.py — does a click land where it is aimed under Mac OS 9?

**Its 2026-08-02 answer, "no", is WITHDRAWN** (BLOCKERS.md; the pointer
positions to within 3 px and clicks, `tools/vmac/os9mouse.py`). Every mouse
probe below fired with the cursor pinned in a corner, because this file asks
for the absolute `usb-tablet` that Mac OS 9 has no driver for, and because a
single large delta to the relative mouse saturates at ±63 px per ADB packet.
The keyboard probes (6-10) are still exactly what they say. The run:

    YES  64.0000  0 the pointer moves at all (whole-screen pixels)
    NO    0.0000  1 held press pulls a menu down
          0.0000  2 menu rolls back up (want ~0 vs base)
    NO    0.0000  3 desktop click changes the app menu
    NO    0.0000  4 single click highlights the volume icon
    NO    0.0000  5 double click opens a window
    YES   0.2662  6 Cmd-Q changes the front application
    YES   0.1553  7 typing 'unc' highlights the volume icon
    YES   0.1284  8 Cmd-Down opens the volume window
    YES   0.0677  9 the application launches
    YES   0.0954 10 extraction runs and reports

Every mouse probe is exactly zero and every keyboard probe works. Probe 0's 64
pixels are the arrow cursor itself, in one screen corner and then the other;
the cursor never reached any of three requested desktop positions — which is
the symptom of a saturated relative delta, not of a dead pointer, and reading
it as the latter is what this file got wrong. `os9.py` drives the Finder from
the keyboard, probes 6-10 are the sequence it uses, and that remains the right
route for fixture runs: it needs no coordinates.

Kept as a diagnostic, not as part of any suite: run it if input ever appears to
stop working, because it says WHICH link broke in one boot.

Why it exists at all: `os9.py --launch` had failed to open the transfer volume
four times, and three explanations had already been published and disproved
(click too slow, relative ADB pointer, Setup Assistant in the foreground — the
last CONFIRMED by screenshot as true, yet clicking the desktop first still
changed nothing).

Every one of those was inferred from the same non-observation: "the volume did
not open". That is the timeout mistake in another costume — an outcome that
did not happen tells you nothing about which link in the chain broke. See
BLOCKERS.md on `macburger-helper.hqx`, where reading a cause into a
non-observation cost three write-ups.

So this measures the primitive instead, on a target whose response is
unambiguous and needs no application to be running, no volume to be mounted
and no double-click timing to be right:

    click a menu bar title -> the menu drops down, or it does not.

A pulled-down menu repaints a large, obvious rectangle immediately below the
title. Diffing that rectangle against the same rectangle before the click is a
yes/no answer about whether a single click reached the guest at the requested
coordinates, with nothing else in the way.

The probes run in one boot, cheapest and most isolating first:

    1  menu bar, held down   -- does ANY press land? (needs nothing else)
    2  released              -- does the menu roll back up? (proves 1 wasn't noise)
    3  empty desktop         -- does the Finder come forward? (app menu title)
    4  volume icon, single   -- does the icon highlight? (proves the coordinate)
    5  volume icon, double   -- does it open? (the thing that has been failing)

Probe 4 is the one the previous attempts skipped: a single click that only
SELECTS separates "the coordinate is wrong" from "the double-click is wrong",
and those two have been conflated in every write-up so far.

Probe 1 screenshots with the button still DOWN. A classic Mac menu tracks the
mouse while held and rolls up on release, so a normal press-and-release can
leave the screen looking untouched even though the press landed perfectly —
the first version of this probe did exactly that and reported a working click
as a failure. Holding removes the ambiguity.

    tools/vmac/os9probe.py -o shots/

Findings go in BLOCKERS.md. This is a diagnostic, not part of any suite.
"""

import argparse, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import os9 as O                                     # noqa: E402
import run as R                                     # noqa: E402

# Full-resolution 1024x768 screen coordinates.
MENU_FILE = (34, 10)        # "File" in the menu bar
DESKTOP = (700, 600)        # bare desktop, clear of every icon
VOLUME = O.XFER_VOLUME_ICON  # the transfer volume icon

# Rectangle repainted when a menu bar title is pulled down: directly below the
# menu bar, wide and tall enough to catch any plausible menu.
MENU_RECT = (300, 260, 0, 20)      # w, h, x, y  (ImageMagick -crop order)
# The application menu title, top right. Changes the moment the front
# application changes, which is exactly what probe 3 asks about.
APPMENU_RECT = (250, 20, 774, 0)
# The volume icon and its label, which invert when the icon is selected.
ICON_RECT = (120, 60, 914, 90)
# Middle of the screen, where a newly opened Finder window, SFGetFile or an
# alert all land. Clear of the menu bar and of the right-hand icon column.
WINDOW_RECT = (600, 500, 200, 100)


def crop(png, rect, out):
    w, h, x, y = rect
    subprocess.run(["convert", png, "-crop", f"{w}x{h}+{x}+{y}", "+repage", out],
                   check=True)
    return out


def differs(a, b, rect, tag, outdir):
    """Fraction of pixels that changed inside `rect` between two screenshots."""
    ca = crop(a, rect, os.path.join(outdir, f"{tag}-a.png"))
    cb = crop(b, rect, os.path.join(outdir, f"{tag}-b.png"))
    # ImageMagick's compare writes the count of differing pixels to stderr.
    p = subprocess.run(["compare", "-metric", "AE", ca, cb, "null:"],
                       capture_output=True, text=True)
    try:
        n = float(p.stderr.strip().split()[0])
    except (ValueError, IndexError):
        raise SystemExit(f"os9probe: cannot read compare output: {p.stderr!r}")
    w, h, _, _ = rect
    return n / (w * h)


def cursor_moves(q, outdir):
    """Probe 0: does the guest's pointer move AT ALL?

    Every probe below assumes the cursor goes where it is told. Nothing has
    ever checked it. The classic Mac cursor is drawn by the guest into its own
    framebuffer, so `screendump` captures it: park the pointer at one corner,
    shoot, park it at the opposite corner, shoot, and any difference at all
    means motion is getting through.

    Deliberately compares the WHOLE screen with no threshold. A cursor is
    ~256 pixels on a 786,432-pixel screen; a fraction-of-pixels test tuned for
    menus would round it away, which is how a dead pointer stayed invisible
    behind four failed launch attempts."""
    q.mon("mouse_move -20000 -20000", 0.6)      # relative: pin to top-left
    q.mon("mouse_move 2000 2000", 0.6)          # absolute: near top-left
    a = os.path.join(outdir, "p0-corner-a.png")
    q.shot(a)
    q.mon("mouse_move 20000 20000", 0.6)
    q.mon("mouse_move 30000 30000", 0.6)
    b = os.path.join(outdir, "p0-corner-b.png")
    q.shot(b)
    p = subprocess.run(["compare", "-metric", "AE", a, b, "null:"],
                       capture_output=True, text=True)
    try:
        return float(p.stderr.strip().split()[0])
    except (ValueError, IndexError):
        return -1.0


def cursor_where(q, outdir, targets):
    """Probe 0b: does the cursor land WHERE it is told, or merely move?

    Probe 0 only proves motion. If the guest binds an absolute device but
    interprets its reports as relative deltas, the cursor still moves — a lot —
    and still ends up nowhere near the requested point, and every click then
    lands on empty desktop and does nothing. That is indistinguishable from
    "clicks are ignored" unless the position is actually read back.

    Parks the cursor at each requested point over bare desktop, and locates it
    by diffing consecutive shots and taking the bounding box of what changed.
    Prints requested vs observed so the two can be compared by eye."""
    seen = []
    prev = None
    for i, (x, y) in enumerate(targets):
        q.mon(f"mouse_move {int(x * 32767 / 1024)} {int(y * 32767 / 768)}", 0.8)
        cur = os.path.join(outdir, f"p0b-{i}.png")
        q.shot(cur)
        if prev:
            d = os.path.join(outdir, f"p0b-diff-{i}.png")
            subprocess.run(["compare", prev, cur, "-compose", "src",
                            "-highlight-color", "white",
                            "-lowlight-color", "black", d],
                           capture_output=True)
            out = subprocess.run(["convert", d, "-trim", "info:"],
                                 capture_output=True, text=True)
            box = "nothing changed"
            for tok in out.stdout.split():
                if "+" in tok and "x" in tok:
                    box = tok
            seen.append(((x, y), box))
        prev = cur
    return seen


def keys(q, outdir, seq, tag, settle=2.5):
    """Send keystrokes and return the screenshot afterwards.

    The Finder is fully drivable from the keyboard — type a name to select an
    icon, Cmd-Down to open it — which sidesteps the pointer completely. That
    is why the keyboard probes are here at all: if probes 0-5 show the pointer
    lands nowhere useful, these still reach the application, and if they show
    it lands correctly then the keyboard route is simply the cheaper one. Which
    of those is true is what this script is being run to find out — nothing
    here assumes it."""
    for k in seq:
        q.mon(f"sendkey {k}", 0.35)
    time.sleep(settle)
    p = os.path.join(outdir, tag + ".png")
    q.shot(p)
    return p


def wait_change(q, before, rect, tag, outdir, timeout=150.0, want=0.02):
    """Poll until `rect` stops looking like `before`, or give up.

    A fixed sleep after a keystroke is the boot-sleep mistake in miniature.
    Opening a Finder window is quick; launching a 68k application through the
    68LC040 emulator is not, and neither duration is a property this harness
    can predict from here — the whole reason `settle()` waits rather than
    sleeps. Judging "did the application launch?" by a 2.5 s screenshot would
    report a slow success as a failure, and this run costs a 20-45 minute boot
    to repeat.

    Returns (fraction changed, seconds waited, screenshot path). The elapsed
    time is itself a result: how long a 68k launch takes under emulation is
    one of the numbers Mac OS 9 has never been measured for."""
    started = time.time()
    p = os.path.join(outdir, tag + ".png")
    frac = 0.0
    while time.time() - started < timeout:
        time.sleep(5.0)
        if not q.shot(p):
            continue
        frac = differs(before, p, rect, tag, outdir)
        if frac >= want:
            break
    return frac, time.time() - started, p


def press(q, x, y, down):
    """Move the pointer and hold the button down, or let it go.

    `Qemu.click` is atomic by design; the menu probe needs to look at the
    screen between the down and the up."""
    if down:
        q.mon(f"mouse_move {int(x * 32767 / 1024)} {int(y * 32767 / 768)}", 0.5)
    q.mon(f"mouse_button {1 if down else 0}", 0.8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--outdir", default="os9probe-out")
    ap.add_argument("--boot-wait", type=float, default=1200.0)
    ap.add_argument("--fixture", default="fixtures/derived-Export.sit")
    ap.add_argument("--pointer", choices=("tablet", "adb"), default="tablet",
                    help="absolute USB tablet, or the machine's built-in "
                         "relative ADB mouse")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    # The volume probes need the transfer volume actually mounted — the first
    # run of this script booted the plain disk and probes 4 and 5 were aimed at
    # bare desktop, which they duly reported as "no icon". Build the same disk
    # `os9.py --launch` builds, so the coordinates mean the same thing.
    from interactive import build_interactive_app
    appbin = build_interactive_app()
    xfer = os.path.join(args.outdir, "transfer.img")
    R.sh(sys.executable, os.path.join(HERE, "mkapmdisk.py"), O.DISK, xfer,
         "32", "MacExtract",
         "--macbinary", f"{appbin}:MacExtract",
         "--data", f"{args.fixture}:archive.sit")

    O.verify_disk()
    boot = O.boot_copy(args.outdir)

    q = None
    results = []
    try:
        q = O.Qemu([boot, xfer], os.path.join(args.outdir, "mon.sock"),
                   tablet=(args.pointer == "tablet"))
        if args.pointer == "tablet":
            print(f"os9probe: absolute pointer is mouse #{q.use_absolute_pointer()}")
        else:
            print("os9probe: using the built-in relative ADB mouse")
        print(q.ask("info mice").strip())
        # A FILE, not the directory: passing the directory made every
        # screenshot fail silently and settle() declare victory mid-boot.
        waited = q.settle(os.path.join(args.outdir, ".settle.png"),
                          timeout=args.boot_wait)
        if waited is None:
            raise SystemExit("os9probe: never reached the Finder desktop")
        print(f"os9probe: desktop settled after ~{waited:.0f}s")

        def shot(name):
            p = os.path.join(args.outdir, name + ".png")
            q.shot(p)
            return p

        # 0. Does the pointer move at all? Everything else assumes it does.
        moved = cursor_moves(q, args.outdir)
        print(f"os9probe: pixels changed by moving the pointer corner to "
              f"corner: {moved:.0f}")
        results.append(("0 the pointer moves at all (whole-screen pixels)",
                        moved, 1.0))

        # 0b. And does it land where asked? Three points on bare desktop,
        #     well apart, all clear of icons.
        for want, box in cursor_where(q, args.outdir,
                                      [(200, 600), (800, 600), (500, 400)]):
            print(f"os9probe: asked for {want}, screen changed at {box}")

        base = shot("00-base")

        # 1. Does any press land at all? Screenshot while still held.
        press(q, *MENU_FILE, down=True)
        p1 = shot("01-menu-open")
        d1 = differs(base, p1, MENU_RECT, "menu1", args.outdir)
        results.append(("1 held press pulls a menu down", d1, 0.02))

        # 2. Release — proves probe 1 was the press, not a coincidence.
        press(q, *MENU_FILE, down=False)
        p2 = shot("02-menu-closed")
        d2 = differs(base, p2, MENU_RECT, "menu2", args.outdir)
        results.append(("2 menu rolls back up (want ~0 vs base)", d2, None))

        # 3. Does clicking the desktop bring the Finder forward?
        q.click(*DESKTOP)
        p3 = shot("03-desktop-click")
        d3 = differs(base, p3, APPMENU_RECT, "appmenu", args.outdir)
        results.append(("3 desktop click changes the app menu", d3, 0.02))

        # 4. Does a SINGLE click on the volume select it? This is the probe
        #    every previous attempt skipped, and the one that separates a bad
        #    coordinate from a bad double-click.
        q.click(*VOLUME)
        p4 = shot("04-volume-single")
        d4 = differs(p3, p4, ICON_RECT, "icon", args.outdir)
        results.append(("4 single click highlights the volume icon", d4, 0.02))

        # 5. And the double click that has been failing all along.
        q.click(*VOLUME, double=True)
        time.sleep(6)
        p5 = shot("05-volume-double")
        d5 = differs(p4, p5, WINDOW_RECT, "window", args.outdir)
        results.append(("5 double click opens a window", d5, 0.02))

        # ---- keyboard, which needs no pointer at all --------------------
        # 6. Cmd-Q. The Setup Assistant is frontmost on every boot (confirmed
        #    by screenshot), so this should quit it and hand the Finder the
        #    foreground — visible in the application menu title.
        #    Cmd-Q alone is not enough: it puts up "Are you sure you want to
        #    quit?" with Quit as the default button, so Return confirms it.
        k6 = keys(q, args.outdir, ["meta_l-q", "ret"], "06-cmd-q")
        d6 = differs(p5, k6, APPMENU_RECT, "cmdq", args.outdir)
        results.append(("6 Cmd-Q changes the front application", d6, 0.02))

        # 7. Type the volume's name: the Finder selects the icon that matches.
        k7 = keys(q, args.outdir, ["u", "n", "c"], "07-type-name")
        d7 = differs(k6, k7, ICON_RECT, "typed", args.outdir)
        results.append(("7 typing 'unc' highlights the volume icon", d7, 0.02))

        # 8. Cmd-Down opens the selection. No pointer, no double-click timing.
        k8 = keys(q, args.outdir, ["meta_l-down"], "08-cmd-down", settle=8.0)
        d8 = differs(k7, k8, WINDOW_RECT, "opened", args.outdir)
        results.append(("8 Cmd-Down opens the volume window", d8, 0.02))

        # 9. Same trick inside the window: select the application by name and
        #    open it. If this paints SFGetFile, the 68k binary is running under
        #    the 68LC040 emulator and Mac OS 9 is no longer untested.
        #    Waited for, not slept through — a 68k launch under emulation has
        #    never been timed on this machine, so there is no figure to sleep.
        for k in ("u", "n", "c", "meta_l-down"):
            q.mon(f"sendkey {k}", 0.35)
        d9, t9, k9 = wait_change(q, k8, WINDOW_RECT, "09-launch", args.outdir)
        print(f"os9probe: screen changed {d9:.4f} within {t9:.0f}s of Cmd-Down "
              f"on the application")
        results.append(("9 the application launches", d9, 0.02))

        # 10. SFGetFile opens with archive.sit already selected, so Return is
        #     "Open". Then the engine runs and the app puts up its result
        #     alert — a 68k engine under the emulator on a fixture that takes
        #     well under a second natively.
        q.mon("sendkey ret", 0.35)
        d10, t10, k10 = wait_change(q, k9, WINDOW_RECT, "10-result", args.outdir)
        print(f"os9probe: screen changed {d10:.4f} within {t10:.0f}s of Return "
              f"in SFGetFile")
        results.append(("10 extraction runs and reports", d10, 0.02))
    finally:
        if q:
            q.close()
        # The boot overlay (os9.boot_copy) is this run's alone.
        if os.path.exists(boot):
            os.remove(boot)

    print("\nos9probe results — fraction of pixels changed in the watched rect:")
    verdict = 0
    for name, frac, want in results:
        if want is None:
            note = "(informational)"
        elif frac >= want:
            note = "YES"
        else:
            note = "NO"
            verdict = 1
        print(f"  {note:>14}  {frac:7.4f}  {name}")
    print("\nScreenshots in", args.outdir)
    return verdict


if __name__ == "__main__":
    sys.exit(main())
