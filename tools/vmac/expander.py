#!/usr/bin/env python3
"""expander.py — the yardstick: this application beside StuffIt Expander 4.0.2.

Every Mac Plus figure this project publishes is absolute — 141 s for a 278 KB
StuffIt archive — and an absolute number answers the wrong question. What a
user weighs is whether this is faster or slower than the free tool they would
otherwise run on that machine. Until this file existed, nothing here had ever
executed that tool: FORMATS.md, *Compared with StuffIt Expander 4.0.2*, is
Aladdin's documentation set against our measurements, and says so.

This boots both applications on the same emulated Mac Plus, at authentic
7 MHz, over the same archive on the same volume, and times them with one
instrument.

    tools/vmac/expander.py --fetch                  # download 4.0.2, unpack it
    tools/vmac/expander.py --sizes                  # both SIZE resources; no emulator
    tools/vmac/expander.py fixtures/derived-Export.sit
    tools/vmac/expander.py --json y.json --only ours fixtures/*.sit

ONE EMULATOR AT A TIME, and nothing else on this box: at 1x the emulator paces
itself against real time, so a second CPU-heavy process inflates the very
number being measured (tools/vmac/README.md).

The instrument
--------------
Both applications are driven to the same point — a Standard File dialog with
the archive selected — and then timed from **the Return that starts the work**
to **the last screenshot that differed from the one before it**. Expander has
no way to be asked what it took, so the only clock that is fair to both is one
outside them; using ours would flatter it by exactly the interference the
other one pays.

The number is therefore a LOWER bound whose error is one poll interval: the
work stopped somewhere between the last changed frame and the next one. Both
sides pay the same quantisation and the same ~50 ms per poll of stolen CPU, so
the RATIO is the durable part of the result and the absolute seconds are not.
Quoting a figure from here as a Mac Plus time is a mistake — FORMATS.md,
*Measured on a 7 MHz Mac Plus*, is where those come from.

What it cannot see
------------------
- **Whether Expander's output is correct.** The run is graded on whether it
  produced files at all. Nothing here compares its bytes with ours.
- **Anything about the formats Expander cannot open alone.** 4.0.2 needs
  DropStuff with Expander Enhancer — System 7 only, and not free — for zip,
  gzip, tar, uuencode, ARC and the rest, so this compares the four families it
  handles on System 6 by itself. A comparison over the other twenty would be
  measuring an unavailable configuration.
- **Repaint gaps.** "Finished" here is "the screen stopped changing for
  `--quiet` seconds". Both progress indicators repaint far more often than
  that, but neither guarantees it — the output check is what catches a stop
  called too early, by finding the extraction incomplete.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools"))
import run as R                                              # noqa: E402
import checkdisk as CD                                       # noqa: E402
from interactive import Mac, build_interactive_app           # noqa: E402
from arcmac import macbinary                                 # noqa: E402
from mkboot import HFS                                       # noqa: E402
from spacesaver import resources                             # noqa: E402

# StuffIt Expander 4.0.2, April 1996, free — Macintosh Garden's copy, which is
# the one FORMATS.md's capability table was read out of. MacBinary around a
# StuffIt self-extracting archive around a 400K HFS image; `macextract x`
# walks all three, and the image it produces is byte-identical to unar's.
GARDEN_PAGE = "https://macintoshgarden.org/apps/stuffit-expander-402"
DIST_SHA = "00e48e48cabc8a9dd295e12531193b3f37c46f87788daf64d1c219d6b11e01a1"
IMG_MD5 = "888c0ca0b93f6ee0ff67e89926e20f83"   # the 400K image inside it

WORK = os.path.join(R.VMAC_HOME, "expander")
DIST = os.path.join(WORK, "stuffit_expander_4.0.2.sea_.bin")
APPBIN = os.path.join(WORK, "Expander.bin")
APP_NAME = "Expander"           # also the boot-block shell name, max 15 bytes

# The four families 4.0.2 opens with no add-on, and the type/creator a real
# one carries. Standard File is what needs them: our own application asks for
# every file (`SFGetFile(..., -1, ...)`), Expander's dialog filters on type,
# so an archive copied as a plain data fork is invisible to it — which is what
# tools/vmac/cptsegment.py hit first, and mkboot's --macbin exists for.
TYPES = {
    "StuffIt": ("SIT!", "SIT!"),
    "StuffIt 5": ("SIT!", "SIT!"),
    "Compact Pro": ("PACT", "CPCT"),
    "BinHex 4": ("TEXT", "ttxt"),
    "MacBinary": ("BINA", "????"),
}


def cli():
    if not os.path.exists(CD.CLI):
        raise SystemExit(f"expander: no CLI at {CD.CLI} — run `make BUILD=build/rel`")
    return CD.CLI


def sniff(path):
    """The engine's own name for a file's format, e.g. "Compact Pro"."""
    return subprocess.run([cli(), "sniff", path], capture_output=True,
                          text=True).stdout.strip()


# ------------------------------------------------------------------
# Fetching
# ------------------------------------------------------------------

def fetch(force=False):
    """Download the distribution, verify it, and rebuild the application.

    Macintosh Garden signs its download URLs and answers a bare GET with
    HTTP 418, so the page is fetched first with a cookie jar and the signed
    link taken out of it — the same two-step arcmac.py uses.
    """
    os.makedirs(WORK, exist_ok=True)
    if force or not os.path.exists(DIST):
        ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
        jar = os.path.join(WORK, "jar")
        page = os.path.join(WORK, "page.html")
        subprocess.run(["curl", "-sS", "-m", "120", "-L", "-A", ua,
                        "-c", jar, "-b", jar, "-o", page, GARDEN_PAGE],
                       check=True)
        html = open(page, errors="replace").read()
        url = next((u for u in html.split('"')
                    if "download.macintoshgarden.org" in u
                    and "stuffit_expander_4.0.2" in u), None)
        if not url:
            raise SystemExit("expander: no download link on the Garden page")
        subprocess.run(["curl", "-sS", "-m", "300", "-L", "-A", ua, "-c", jar,
                        "-b", jar, "-e", GARDEN_PAGE, "-o", DIST,
                        "https:" + url.lstrip(":")], check=True)
    blob = open(DIST, "rb").read()
    got = hashlib.sha256(blob).hexdigest()
    if got != DIST_SHA:
        raise SystemExit(f"expander: {DIST} has sha256 {got}, expected "
                         f"{DIST_SHA} — the upstream file changed; check it "
                         f"by hand rather than editing this constant")

    tree = os.path.join(WORK, "dist")
    shutil.rmtree(tree, ignore_errors=True)
    subprocess.run([cli(), "x", "-o", tree, DIST], check=True,
                   capture_output=True)
    img = os.path.join(tree, "StuffIt Expander 4.0.2.img")
    if not os.path.exists(img):
        raise SystemExit("expander: no disk image inside the self-extractor")
    md5 = hashlib.md5(open(img, "rb").read()).hexdigest()
    if md5 != IMG_MD5:
        raise SystemExit(f"expander: the image inside is md5 {md5}, expected "
                         f"{IMG_MD5}")
    app = app_from_image(img)
    shutil.copyfile(app, APPBIN)
    d, r = forks(APPBIN)
    print(f"expander: {APPBIN} — {len(r)} B of resources, "
          f"version {version(r)}, SIZE {size_str(r)}")


def app_from_image(img):
    """Copy the application off the 400K HFS image, as MacBinary.

    hfsutils refuses a volume "smaller than 800K", which is the whole of why
    FORMATS.md said this needed "an HFS reader this machine does not have".
    It does not: the image is padded to 800K in a temporary copy and mounts.
    Reading only ever follows the MDB's own extents, so the padding is never
    looked at.
    """
    tmp = os.path.join(WORK, "padded.img")
    shutil.copyfile(img, tmp)
    with open(tmp, "r+b") as f:
        f.truncate(max(os.path.getsize(img), 800 * 1024))
    out = os.path.join(WORK, "app.bin")
    hfs = HFS(tmp)
    try:
        # The application is the one APPL on the volume, found rather than
        # typed: its name carries a trademark sign (MacRoman 0xAA) and it
        # sits in a folder whose name is not the volume's.
        found, stack = None, [hfs.vol + ":"]
        while stack:
            d = stack.pop()
            for isdir, name in hfs.ls(d):
                child = d.rstrip(":") + ":" + name
                if isdir:
                    stack.append(child)
                elif "APPL/SITx" in hfs.run("hdir", child).stdout:
                    found = child
        if not found:
            raise SystemExit("expander: no APPL on the distribution image")
        hfs.run("hcopy", "-m", found, out)
    finally:
        hfs.close()
        os.remove(tmp)
    return out
    return out


# ------------------------------------------------------------------
# Reading an application without running it
# ------------------------------------------------------------------

def forks(macbin):
    """(data, resource) out of a MacBinary file."""
    b = open(macbin, "rb").read()
    dlen, rlen = struct.unpack(">II", b[83:91])
    p = 128 + (dlen + 127) // 128 * 128
    return b[128:128 + dlen], b[p:p + rlen]


def size_res(rsrc):
    """(preferred, minimum) partition in bytes, from 'SIZE' (-1).

    Inside Macintosh VI: a flags word, then the two sizes as longs. This is
    what the Finder's Get Info box shows and what the Process Manager gives
    the application on System 7 and later.
    """
    r = resources(rsrc).get("SIZE", {})
    if -1 not in r:
        return None
    return struct.unpack(">II", r[-1][1][2:10])


def size_str(rsrc):
    s = size_res(rsrc)
    return "unknown" if not s else "%d KB preferred, %d KB minimum" % (
        s[0] // 1024, s[1] // 1024)


def version(rsrc):
    v = resources(rsrc).get("vers", {}).get(1)
    if not v:
        return "unknown"
    n = v[1][6]
    return v[1][7:7 + n].decode("mac-roman", "replace")


def sizes(ours):
    """Both applications' memory partitions. No emulator, no boot."""
    for label, path in (("StuffIt Expander 4.0.2", APPBIN), ("MacExtract", ours)):
        _, r = forks(path)
        print("%-24s %8d B of resources   %s"
              % (label, len(r), size_str(r)))


# ------------------------------------------------------------------
# One timed run
# ------------------------------------------------------------------

def typed_copy(fixture, workdir):
    """The fixture as MacBinary carrying the type/creator a real one has.

    Both volumes are built from this one file, so the two applications are
    handed a byte-identical disk and the only difference between the runs is
    which application is on it.
    """
    fmt = sniff(fixture)
    if fmt not in TYPES:
        raise SystemExit(
            f"expander: {os.path.basename(fixture)} is {fmt}, which "
            f"Expander 4.0.2 cannot open without DropStuff with Expander "
            f"Enhancer (System 7, not free) — there is no fair run to make")
    ftype, creator = TYPES[fmt]
    name = os.path.basename(fixture)[:31]
    out = os.path.join(workdir, "typed.bin")
    with open(out, "wb") as f:
        f.write(macbinary(name, ftype, creator, data=open(fixture, "rb").read()))
    return out, name, fmt


def last_change(mac, scratch, interval, quiet, timeout, first=None):
    """Seconds until the screen last changed, having then held still.

    Not `Mac.settle`, which returns the whole wait including the quiet
    period. What is wanted here is when the work STOPPED, and the quiet
    period is only how the harness convinces itself of that — so the
    timestamp of the last differing frame is what comes back, and the
    minutes spent proving it are discarded.
    """
    t0 = time.time()
    prev, changed = None, t0
    while time.time() - t0 < timeout:
        time.sleep(interval)
        mac.shot(scratch)
        cur = open(scratch, "rb").read()
        if first and prev is None:
            shutil.copyfile(scratch, first)     # evidence that work started
        if cur != prev:
            prev, changed = cur, time.time()
        elif time.time() - changed >= quiet:
            return changed - t0
    return None


def names_on(img):
    """Every file on an HFS image, as ':'-separated Mac paths."""
    home = tempfile.mkdtemp(prefix="hfs-")
    env = dict(os.environ, HOME=home)
    try:
        if CD.hfs(env, "hmount", img).returncode != 0:
            return []
        got = sorted(CD.mac_path(n) for n in CD.walk(env))
        CD.hfs(env, "humount")
        return got
    finally:
        shutil.rmtree(home, ignore_errors=True)


def run_one(which, appbin, fixture, args, workdir, shots):
    """Boot one application on one archive and time the extraction."""
    typed, macname, fmt = typed_copy(fixture, workdir)
    stock = os.path.join(R.VMAC_HOME, args.system)
    boot = os.path.join(workdir, f"boot-{which}.hfv")
    argv = [sys.executable, os.path.join(HERE, "mkboot.py"), stock, appbin,
            boot, "--macbin", f"{typed}:{macname}"]
    if which == "expander":
        argv += ["--app-name", APP_NAME]
    R.sh(*argv)
    before = set(names_on(boot))     # the stock image is not empty: mkboot's
                                     # walk uses `hdir`, which hides invisible
                                     # files, so custom-icon `Icon` files
                                     # survive in folders it could not remove

    scratch = os.path.join(shots, f".{which}.png")
    shot = lambda n: mac.shot(os.path.join(shots, f"{which}-{n}.png"))  # noqa: E731
    mac = Mac(boot, args.emu, workdir)
    elapsed = None
    try:
        if mac.settle(scratch, interval=5.0, timeout=args.boot_timeout) is None:
            raise SystemExit(f"expander: the {which} machine never booted")
        shot("1-launched")
        # Nothing here has assigned X keyboard focus yet: settle() only
        # screenshots, and origin() is where interactive.py's focus call
        # lives. Without it Command-E goes to the root window and the Mac
        # never sees a keystroke — which looks exactly like an application
        # that ignores its own menu shortcut.
        mac.origin(cached=False)
        if which == "expander":
            # Command-E is "Expand..." (MENU 129, read out of the application
            # itself). Everything Expander does that is not a drag lands
            # there, and a Command key avoids the pointer entirely.
            mac.command_key("e")
            time.sleep(3.0)
            shot("2-open")
            # No click on the file list: Expander's dialog is Standard File
            # with Aladdin's own DLOG, so the list sits ~48 px higher than
            # the stock one and the row interactive.py measured is BELOW the
            # last item. Clicking there picked `System Folder` and Return
            # opened it, photographed. The first row is preselected and
            # mkboot leaves exactly one expandable file on the volume.
            mac.click(*EXPAND_BUTTON)    # Expand -> straight to work
        else:
            mac.click(*R_SF_ROW)
            mac.key("Return")            # Open -> destination dialog
            time.sleep(3.0)
            shot("2-destination")
            mac.key("Return")            # Save -> "beside the archive"
        elapsed = last_change(mac, scratch, args.poll, args.quiet,
                              args.timeout,
                              first=os.path.join(shots, f"{which}-2b-started.png"))
        shot("3-finished")
        if which == "expander":
            # Quit, or the host reads an empty volume. Our own sink calls
            # FlushVol after closing each fork (mac/macextract_mac.c), so its
            # output is on the image the moment the alert goes up; Expander
            # leaves its writes in the File Manager's cache, and SIGKILLing
            # the emulator throws them away. A 278 KB archive expanded for
            # 56 s — the progress window photographed every step of it — and
            # the image afterwards held nothing at all.
            #
            # This is AFTER the measurement, which ends at the last frame
            # that changed, so it costs the comparison nothing.
            mac.command_key("q")
            mac.settle(scratch, interval=3.0, stable=3, timeout=120.0)
            shot("4-quit")
    finally:
        mac.close()
        if os.path.exists(scratch):
            os.remove(scratch)

    written = names_on(os.path.join(workdir, "boot.hfv"))   # Mac()'s own copy
    produced = [n for n in written if n not in before]
    return {"app": which, "fixture": os.path.basename(fixture), "format": fmt,
            "seconds": None if elapsed is None else round(elapsed, 1),
            "output": produced}


# Standard File's first row on System 6.0.8, in the STOCK dialog our own
# application uses. Measured by interactive.py off its own frames.
R_SF_ROW = (150, 137)

# The Expand button in Aladdin's dialog, measured off this harness's own
# `expander-2-open.png`. Drive, the nearest button an aimless click could
# reach, is 46 px above it and greyed.
#
# Pressed with the mouse rather than with Return, which is what the three
# lessons in interactive.py argue against — and deliberately, because it is
# what every figure in FORMATS.md was taken with. Return was tried first and
# looked like it did nothing; the volume it left behind was empty for the
# FLUSH reason below, not because of the key, so whether Return works here is
# untested rather than disproved. Re-testing it would cost one boot.
EXPAND_BUTTON = (379, 194)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("fixtures", nargs="*")
    p.add_argument("--fetch", action="store_true",
                   help="download StuffIt Expander 4.0.2 and unpack it")
    p.add_argument("--sizes", action="store_true",
                   help="print both applications' SIZE resources and stop")
    p.add_argument("--only", choices=("ours", "expander"),
                   help="run just one of the two")
    p.add_argument("--emu", default="mv-4M-1x",
                   help="emulator build; only the 1x ones may be quoted")
    p.add_argument("--system", default="System6.hfv")
    p.add_argument("--poll", type=float, default=3.0,
                   help="seconds between screenshots — the measurement's "
                        "quantisation, and ~2%% of the core it steals")
    p.add_argument("--quiet", type=float, default=60.0,
                   help="seconds the screen must hold still before the work "
                        "is called finished")
    p.add_argument("--timeout", type=float, default=2400.0)
    p.add_argument("--boot-timeout", type=float, default=300.0)
    p.add_argument("-o", "--outdir", default="/tmp/expander-shots")
    p.add_argument("--json")
    p.add_argument("--keep", help="build the disks in this directory and "
                                  "leave them there, to be looked at by hand")
    args = p.parse_args()

    if args.fetch:
        fetch()
        if not args.fixtures:
            return 0
    if not os.path.exists(APPBIN):
        raise SystemExit("expander: no Expander.bin — run --fetch first")
    ours = build_interactive_app()
    if args.sizes:
        sizes(ours)
        return 0
    if not args.fixtures:
        p.error("nothing to time")

    os.makedirs(args.outdir, exist_ok=True)
    rows = []
    for fixture in args.fixtures:
        for which, app in (("ours", ours), ("expander", APPBIN)):
            if args.only and args.only != which:
                continue
            workdir = args.keep or tempfile.mkdtemp(prefix="expander-")
            os.makedirs(workdir, exist_ok=True)
            shots = os.path.join(args.outdir,
                                 os.path.basename(fixture).replace(".", "_"))
            os.makedirs(shots, exist_ok=True)
            try:
                row = run_one(which, app, fixture, args, workdir, shots)
            finally:
                if not args.keep:
                    shutil.rmtree(workdir, ignore_errors=True)
            rows.append(row)
            secs = "never settled" if row["seconds"] is None \
                else "%.0f s" % row["seconds"]
            # The names are the evidence that both applications did the
            # same work, and one fixture here writes 312 of them — so the
            # line says how many and shows the first few; --json keeps
            # every one.
            out = row["output"]
            shown = ", ".join(out[:3]) + (" ..." if len(out) > 3 else "")
            print("expander: %-9s %-34s %-12s %8s   wrote %d: %s"
                  % (which, row["fixture"], row["format"], secs,
                     len(out), shown or "NOTHING"))

    print()
    print("%-34s %-12s %10s %10s %7s" % ("Fixture", "Format", "MacExtract",
                                         "Expander", "ratio"))
    ok = True
    for fixture in args.fixtures:
        base = os.path.basename(fixture)
        got = {r["app"]: r for r in rows if r["fixture"] == base}
        a = got.get("ours", {}).get("seconds")
        b = got.get("expander", {}).get("seconds")
        for r in got.values():
            if r["seconds"] is None or not r["output"]:
                ok = False
        ratio = "%.2fx" % (b / a) if a and b else "-"
        print("%-34s %-12s %10s %10s %7s"
              % (base[:34], got.get("ours", got.get("expander"))["format"],
                 "%.0f s" % a if a else "-", "%.0f s" % b if b else "-", ratio))
    print("\nratio > 1 means Expander took longer. Both figures are lower "
          "bounds, accurate to the %.0f s poll." % args.poll)
    if args.json:
        json.dump(rows, open(args.json, "w"), indent=1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
