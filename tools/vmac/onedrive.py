#!/usr/bin/env python3
"""onedrive.py — how many floppy swaps does an extraction cost a one-drive Mac?

Mini vMac normally gives every inserted disk a drive of its own, so no run
anywhere else in this directory can show a swap. `mv-4M-1d` is built with two
drives (tools/vmac/setup.sh): the boot disk and ONE floppy drive. A second
floppy goes in only once the first is out, and the System asks for a disk it
needs by name — "Please insert the disk: ME" — and ejects the one in the drive
to make room, as on the maintainer's LC 475.

The walk, on System 7.0.1:

  1. MacExtract on floppy "ME", launched from it in the Finder;
  2. in its Open dialog, ME ejected and floppy "C" put in;
  3. an archive on C opened, the destination set to the boot disk, Save;
  4. from then on, every "Please insert the disk" answered with the disk it
     names, and recorded.

PASSES when step 4 asks for nothing: the archive's floppy is in the drive and
the output goes to the hard disk, so a request is the application reaching
back to its own floppy. Measured 2026-10-14: the build before `preload` asked
ME, C, ME, C — the progress window's and the closing alert's resources read
from MacExtract's file as each first appeared — and fails here; the build
after asks for nothing (DECISIONS.md 2026-10-14, *the disk the dialogs were
on*).

What it CANNOT see:
  - Archives dropped on an alias of MacExtract, the walk the LC 475 took
    (MANUAL_TESTS.md §4): System 7.0.1's Finder does not take a drop on an
    alias whose application is on an ejected floppy — it copies the files
    into the window instead — so that path is not reproducible here.
  - The swaps BEFORE the Open dialog. Launching from ME with C's window open
    costs ME, C, ME on its own; that is the Finder, not counted, and not this
    application's to change.
  - Which disk is asked for, other than ME or C: the prompt's name is told
    apart by one crop of the "ME" prompt, measured off this walk's frames.

`--drop` is the other walk, and a MEASUREMENT rather than a check: two
archives on C carrying MacExtract's creator, opened together from the
Finder with Cmd-O — the same list of documents a drop on an alias hands
over, which 7.0.1 will not do from an alias here. It answers every prompt,
picks the boot disk at each "Extract into", and prints the whole sequence;
it fails only if it did not reach "Extract into" twice. Measured
2026-10-14: ME C ME C ME C ME C before the first "Extract into" — every ME
before MacExtract's main() runs (a probe build marking the screen at each
step of main() drew nothing yet) — against SimpleText's ten launched the
same way; then the reload's ME between the archives, and one ME more around
the second "Extraction complete." that is neither the alert's resources
nor its icon (DECISIONS.md 2026-10-14, *the swaps that are the System's*).

Usage:
    onedrive.py [--app MacExtract.bin] [-o DIR] [--drop]
"""
import argparse, hashlib, os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import interactive as I                                      # noqa: E402

R = I.R
FIXTURE = os.path.join(R.REPO, "fixtures", "derived-Power_Macintosh_PRs.sit")

# Measured off this walk's own frames (System 7.0.1, 512x342). The prompt is
# the System's disk-switch alert: its icon, and the volume name under the
# message. The crop hashes are of the icon and of the name "ME".
PROMPT_ICON = ("30x30+140+95", "4dbf08ada00e")
PROMPT_NAME = ("60x16+192+118", "13703694b2ba")
ME_ICON = (471, 100)         # the ME floppy on the desktop, below the boot disk
APP_IN_ME = (40, 92)         # MacExtract in ME's window
SF_EJECT = (374, 131)        # Standard File's Eject, System 7
SF_ONLY_ROW = (150, 127)     # the archive: C holds nothing else
SFPUT_DESKTOP = (410, 189)
SFPUT_BOOT_ROW = (190, 173)  # under Desktop: C, then the boot disk
SFPUT_LABEL = ("150x10+128+258", "099b455920dd")   # "Extract into this folder:"
C_ICON = (471, 148)          # floppy C on the desktop, once ME is out
SECOND = os.path.join(R.REPO, "fixtures", "derived-Education7.1.cpt")


def crop(png, geom):
    px = subprocess.run(["convert", png, "-scale", "512x342!", "-crop", geom,
                         "+repage", "-depth", "8", "gray:-"],
                        capture_output=True, check=True).stdout
    return hashlib.md5(px).hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", help="MacBinary to run (default: build the "
                                  "interactive application from this tree)")
    ap.add_argument("-o", "--outdir", default="vmac-onedrive")
    ap.add_argument("--drop", action="store_true",
                    help="open two archives on C with Cmd-O instead, and "
                         "print every disk asked for (a measurement)")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    I.calibrate("Sys7.img")
    appbin = args.app or I.build_interactive_app(())

    work = tempfile.mkdtemp(prefix="onedrive-")
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))

    def hfs(*a):
        subprocess.run(list(a), check=True, capture_output=True, env=env)

    # The application lives on ME only: mkboot.py puts a copy on the boot
    # disk, and the Finder would launch that one.
    boot = os.path.join(work, "boot-src.hfv")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"),
         os.path.join(R.VMAC_HOME, "Sys7.img"), appbin, boot, "--finder")
    hfs("hmount", boot); hfs("hdel", "MacExtract"); hfs("humount")
    me, c = os.path.join(work, "ME.dsk"), os.path.join(work, "C.dsk")
    for img, vol in ((me, "ME"), (c, "C")):
        with open(img, "wb") as f:
            f.truncate(800 * 1024)
        hfs("hformat", "-l", vol, img)
    hfs("hmount", me); hfs("hcopy", "-m", appbin, ":MacExtract"); hfs("humount")
    hfs("hmount", c); hfs("hcopy", "-r", FIXTURE, ":First.sit")
    if args.drop:
        # MacExtract's creator, so that the Finder opens both with it.
        hfs("hcopy", "-r", SECOND, ":Second.cpt")
        hfs("hattrib", "-t", "SITD", "-c", "MExt", "First.sit")
        hfs("hattrib", "-t", "PACT", "-c", "MExt", "Second.cpt")
    else:
        hfs("hattrib", "-t", "SITD", "-c", "SIT!", "First.sit")
    hfs("humount")

    mac = I.Mac(boot, "mv-4M-1d", work)
    n = [0]

    def shot(tag):
        n[0] += 1
        p = os.path.join(args.outdir, "%02d-%s.png" % (n[0], tag))
        mac.shot(p)
        return p

    asked = []
    try:
        if mac.settle(os.path.join(args.outdir, ".s.png"), interval=5.0,
                      timeout=300) is None:
            raise SystemExit("onedrive: the machine never settled")
        if args.drop:
            return drop_walk(mac, me, c, shot)
        I.drop_disk(mac, me); time.sleep(8)
        mac.click(*ME_ICON, double=True); time.sleep(6)
        mac.click(*APP_IN_ME, double=True); time.sleep(20)
        shot("open-dialog")
        mac.click(*SF_EJECT); time.sleep(5)
        I.drop_disk(mac, c); time.sleep(8)
        shot("on-C")
        mac.click(*SF_ONLY_ROW, double=True); time.sleep(6)
        shot("destination")
        mac.click(*SFPUT_DESKTOP); time.sleep(4)
        mac.click(*SFPUT_BOOT_ROW, double=True); time.sleep(3)
        mac.key("Return")
        t0, quiet = time.time(), 0
        while quiet < 4 and time.time() - t0 < 400:
            time.sleep(5)
            p = shot("t")
            if crop(p, PROMPT_ICON[0]) == PROMPT_ICON[1]:
                disk = "ME" if crop(p, PROMPT_NAME[0]) == PROMPT_NAME[1] else "C"
                asked.append(disk)
                quiet = 0
                I.drop_disk(mac, me if disk == "ME" else c); time.sleep(6)
            else:
                quiet += 1
        shot("end")
    finally:
        mac.close()
        shutil.rmtree(work, ignore_errors=True)

    print("onedrive: asked for after Save: "
          + (", ".join(asked) if asked else "nothing"))
    print("onedrive: screenshots in %s — the last one should read "
          "\"Extraction complete.\"" % args.outdir)
    return 0 if not asked else 1


def drop_walk(mac, me, c, shot):
    """--drop: the sequence, printed; 1 if "Extract into" was not reached
    twice. The waits are what the walk needed: ejected sooner, the Finder
    asked for ME back before C could go in."""
    I.drop_disk(mac, me); time.sleep(30)
    mac.click(*ME_ICON, double=True); time.sleep(10)    # ME's window, once
    mac.command_key("w"); time.sleep(5)
    mac.click(*ME_ICON); time.sleep(2)
    mac.command_key("e"); time.sleep(15)
    I.drop_disk(mac, c); time.sleep(30)
    mac.click(*C_ICON, double=True); time.sleep(6)
    shot("C-window")
    mac.command_key("a"); time.sleep(2)
    mac.command_key("o"); time.sleep(4)
    seq, quiet, t0 = [], 0, time.time()
    while time.time() - t0 < 900:
        time.sleep(4)
        p = shot("t")
        if crop(p, PROMPT_ICON[0]) == PROMPT_ICON[1]:
            disk = "ME" if crop(p, PROMPT_NAME[0]) == PROMPT_NAME[1] else "C"
            seq.append(disk); quiet = 0
            I.drop_disk(mac, me if disk == "ME" else c); time.sleep(6)
        elif crop(p, SFPUT_LABEL[0]) == SFPUT_LABEL[1]:
            seq.append("[Extract into]"); quiet = 0
            mac.click(*SFPUT_DESKTOP); time.sleep(4)
            mac.click(*SFPUT_BOOT_ROW, double=True); time.sleep(3)
            mac.key("Return"); time.sleep(4)
        else:
            quiet += 1
            if quiet >= 4:                  # an alert waiting: OK it
                seq.append("[alert]"); quiet = 0
                mac.key("Return")
                if seq.count("[alert]") >= 2:
                    break
    shot("end")
    print("onedrive --drop: " + " ".join(seq))
    return 0 if seq.count("[Extract into]") >= 2 else 1


if __name__ == "__main__":
    sys.exit(main())
