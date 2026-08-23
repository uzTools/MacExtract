#!/usr/bin/env python3
"""cptcrypt.py — have Compact Pro itself grade our reading of its cipher.

Compact Pro's encryption is the one scheme in this project that no
reference implementation reads and no publication describes ("the
algorithm for this is unknown" — The Unarchiver's own format notes).
src/unc_crypt.c reads it out of Compact Pro 1.51's `CODE` 3, and a
reading like that is a hypothesis until the application says otherwise.

So this hands the application an archive written by tools/synth_cpt.py
with that cipher and a known password, and asks it to extract. If what
lands on the volume is what went in, the reading is right — the same
arrangement that graded DiskDoubler methods 3, 4 and 5 against
Salient's own expander (DECISIONS.md 2026-08-21), and the only kind of
evidence available for a format with one implementation.

    tools/vmac/cptcrypt.py --explore     # photograph each step
    tools/vmac/cptcrypt.py               # run it and compare

Output (screenshots and the files the Mac wrote) lands in
$UNC_VMAC_HOME/specimens/cptcrypt/.

**What this run actually measured, 2026-08-23: Compact Pro 1.51 will
not do it.** It opens the archive, lists all three entries with the
right sizes and marks each encrypted — so the container and the flag
are right — and then answers Extract with

    This selection includes encrypted files.
    This version of Compact Pro cannot validate or extract encrypted
    files.

That is not a build without the code: the decrypt loop is in `CODE` 3
of this very binary, at 0x1f08. It is a REGISTRATION gate. The routine
at 0x47ca stores the personalisation string and, at 0x485e, enables
encryption only when that string ends with `*`; every copy in the
corpus (1.34 and 1.51 in four languages) carries the unregistered
placeholder `********` in `DATA` 0, and the "Encrypt" checkbox in the
Add dialog sits at a negative rect until that flag moves it into view.
Forging a registration is not something this project will do.

So the run is kept for the day somebody has a registered copy — it is
then one command — and the cipher stays a reading of the binary that no
second implementation has graded. There is no other implementation to
try: CptExpand says "it will not extract encrypted files", StuffIt's
own Compact Pro translator answers "the file is password protected",
and The Unarchiver never implemented it. OPEN_ITEMS.md.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import run as R                                       # noqa: E402
from interactive import Mac                           # noqa: E402
from mkboot import LISTING_DATE                       # noqa: E402
import synth_wrapped as W                             # noqa: E402
import synth_cpt as SCPT                              # noqa: E402

APP_FIXTURE = "compact-pro-151.hqx"
APP_PATH = "Compact Pro 1.51/Compact Pro"
APP_NAME = "Compact Pro"
SOURCE_NAME = "Secret.cpt"
CPT_TYPE, CPT_CREATOR, APP_TYPE = b"PACT", b"CPCT", b"APPL"
PASSWORD = "ohsecret"

# Measured off cptsegment.py's screenshots of the same application on the
# same 512x342 screen.
FINDER_VOLUME_ICON = (480, 40)
FINDER_APP_ICON = (105, 105)
NAG_NOT_YET = (433, 249)
SF_FIRST_ROW = (150, 88)
MENU_Y = 10
MENUS = {"File": 45, "Edit": 80, "Archive": 135, "View": 190, "Misc": 232}


def cli():
    exe = os.path.join(REPO, "build", "dev", "unclassic")
    if not os.path.exists(exe):
        R.sh("make", "-C", REPO, "BUILD=build/dev", "all")
    return exe


def extract_app(workdir):
    out = os.path.join(workdir, "app")
    os.makedirs(out, exist_ok=True)
    R.sh(cli(), "x", "-o", out, os.path.join(REPO, "fixtures", APP_FIXTURE))
    data = os.path.join(out, APP_PATH)
    rsrc = data + ".rsrc"
    for p in (data, rsrc):
        if not os.path.exists(p):
            raise SystemExit(f"cptcrypt: {APP_FIXTURE} did not yield {p}")
    binpath = os.path.join(workdir, "CompactPro.bin")
    with open(binpath, "wb") as f:
        f.write(W.macbinary(APP_NAME, open(data, "rb").read(),
                            open(rsrc, "rb").read(),
                            ftype=APP_TYPE, creator=CPT_CREATOR))
    return binpath


def source_macbinary(workdir, password):
    """The encrypted archive, as a PACT/CPCT file Standard File will show."""
    blob = SCPT.build(password.encode("mac_roman"))
    open(os.path.join(workdir, "Secret.cpt"), "wb").write(blob)
    out = os.path.join(workdir, "source.bin")
    with open(out, "wb") as f:
        f.write(W.macbinary(SOURCE_NAME, blob, ftype=CPT_TYPE,
                            creator=CPT_CREATOR))
    return out


def boot_image(workdir, password, system="System6.hfv"):
    stock = os.path.join(R.VMAC_HOME, system)
    if not os.path.exists(stock):
        raise SystemExit(f"cptcrypt: no {system} — run tools/vmac/setup.sh")
    img = os.path.join(workdir, "boot-cptcrypt.hfv")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock,
         extract_app(workdir), img, "--finder", "--app-name", APP_NAME,
         "--macbin", f"{source_macbinary(workdir, password)}:{SOURCE_NAME}")
    return img


def pull_down(mac, x):
    ox, oy = mac.origin()
    mac._xdo("mousemove", str(ox + x), str(oy + MENU_Y))
    time.sleep(0.3)
    mac._xdo("mousedown", "1")
    time.sleep(1.0)


def release(mac, x=None, y=None):
    if x is not None:
        ox, oy = mac.origin()
        mac._xdo("mousemove", str(ox + x), str(oy + y))
        time.sleep(0.4)
    mac._xdo("mouseup", "1")
    time.sleep(1.0)


def launch(mac, shot, args):
    if mac.settle(os.path.join(args.outdir, ".settle.png"),
                  interval=5.0, timeout=args.boot_timeout) is None:
        raise SystemExit("cptcrypt: the machine never reached the Finder")
    shot(mac, "1-desktop.png")
    mac.click(*FINDER_VOLUME_ICON, double=True)
    time.sleep(4.0)
    shot(mac, "2-volume.png")
    mac.click(*FINDER_APP_ICON)
    time.sleep(1.0)
    mac.command_key("o")
    time.sleep(args.launch_wait)
    shot(mac, "3-launched.png")
    mac.click(*NAG_NOT_YET)
    time.sleep(2.0)
    shot(mac, "3b-nag-dismissed.png")


def open_source(mac, shot, args):
    mac.command_key("o")
    time.sleep(3.0)
    shot(mac, "4-open-dialog.png")
    mac.click(*SF_FIRST_ROW)
    mac.key("Return")
    time.sleep(args.launch_wait)
    shot(mac, "5-archive-open.png")


def read_volume(image, outdir, skip):
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    got = {}
    try:
        for _ in range(5):
            r = subprocess.run(["hmount", image], env=env, capture_output=True,
                               text=True, errors="surrogateescape")
            if r.returncode == 0:
                break
            time.sleep(2.0)
        else:
            raise SystemExit(f"cptcrypt: cannot mount {image}: {r.stderr}")
        vol = r.stdout.split('Volume name is "', 1)[1].split('"', 1)[0]
        listing = subprocess.run(["hdir", vol + ":"], check=True, env=env,
                                 capture_output=True, text=True,
                                 errors="surrogateescape").stdout
        for line in listing.splitlines():
            if not line.startswith("f"):
                continue
            m = LISTING_DATE.search(line)
            if not m:
                continue
            name = m.group(1)
            if name in skip:
                continue
            dest = os.path.join(outdir, name.replace("/", "_"))
            subprocess.run(["hcopy", "-m", f"{vol}:{name}", dest + ".bin"],
                           check=True, env=env, capture_output=True)
            got[name] = dest + ".bin"
        subprocess.run(["humount"], env=env, capture_output=True)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    return got


def macbinary_forks(path):
    """Data and resource fork out of a MacBinary file hcopy wrote."""
    b = open(path, "rb").read()
    dlen = int.from_bytes(b[83:87], "big")
    rlen = int.from_bytes(b[87:91], "big")
    doff = 128
    roff = doff + ((dlen + 127) // 128) * 128
    return b[doff:doff + dlen], b[roff:roff + rlen]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emu", default="mv-4M")
    ap.add_argument("--outdir",
                    default=os.path.join(R.VMAC_HOME, "specimens", "cptcrypt"))
    ap.add_argument("--boot-timeout", type=float, default=900.0)
    ap.add_argument("--launch-wait", type=float, default=20.0)
    ap.add_argument("--extract-wait", type=float, default=30.0)
    ap.add_argument("--password", default=PASSWORD)
    ap.add_argument("--explore", action="store_true",
                    help="stop after opening the archive and photograph "
                         "every menu, so the next run knows what to click")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    def shot(mac, name):
        p = os.path.join(args.outdir, name)
        mac.shot(p)
        print("  " + name)

    workdir = tempfile.mkdtemp(prefix="cptcrypt-")
    try:
        img = boot_image(workdir, args.password)
        mac = Mac(img, args.emu, workdir)
        try:
            launch(mac, shot, args)
            open_source(mac, shot, args)
            if args.explore:
                for name, x in sorted(MENUS.items(), key=lambda kv: kv[1]):
                    pull_down(mac, x)
                    shot(mac, f"6-menu-{name}.png")
                    release(mac)
                return 0
            # Select every entry, then Extract. Both have keyboard
            # equivalents (Cmd-A, Cmd-E), so neither needs a coordinate.
            mac.command_key("a")
            time.sleep(1.5)
            shot(mac, "6-selected.png")
            mac.command_key("e")
            time.sleep(4.0)
            shot(mac, "7-extract-dialog.png")
            # The destination is the boot volume, which is where the
            # dialog opens; Return takes it.
            mac.key("Return")
            time.sleep(4.0)
            shot(mac, "8-password-prompt.png")
            for ch in args.password:
                mac.key(ch)
            time.sleep(1.0)
            shot(mac, "8b-password-typed.png")
            mac.key("Return")
            time.sleep(args.extract_wait)
            shot(mac, "9-extracted.png")
            mac.command_key("q")
            time.sleep(6.0)
            shot(mac, "9b-quit.png")
        finally:
            mac.close()

        files = read_volume(os.path.join(workdir, "boot.hfv"), args.outdir,
                            skip={APP_NAME, SOURCE_NAME})
        print(f"cptcrypt: {len(files)} file(s) off the volume")
        want = {n: (d, r) for n, _t, _c, d, r in SCPT.CASES}
        bad = 0
        for name, (data, rsrc) in sorted(want.items()):
            p = files.get(name)
            if p is None:
                print(f"    {name:14s} MISSING")
                bad += 1
                continue
            gd, gr = macbinary_forks(p)
            ok = gd == data and gr == rsrc
            print(f"    {name:14s} data {len(gd)}/{len(data)} "
                  f"rsrc {len(gr)}/{len(rsrc)} {'OK' if ok else 'DIFFERS'}")
            if not ok:
                bad += 1
        for name in sorted(set(files) - set(want)):
            print(f"    (also on the volume: {name})")
        if bad:
            print("cptcrypt: Compact Pro wrote nothing back. On an "
                  "unregistered copy that is expected and is not a verdict "
                  "on the cipher — see 7-extract-dialog.png and this "
                  "file's header. Look at the screenshots before believing "
                  "anything either way.")
            return 1
        print("cptcrypt: Compact Pro 1.51 extracted every entry byte for "
              "byte — the cipher reading is confirmed by the application "
              "that wrote the format.")
        return 0
    finally:
        if args.keep:
            print(f"cptcrypt: workdir kept at {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
