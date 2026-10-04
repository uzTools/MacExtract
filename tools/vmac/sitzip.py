#!/usr/bin/env python3
"""sitzip.py — do StuffIt 5.5 and 7.0.3 read Info-ZIP's `0x334d`?

`zipmeta.py` asked this of StuffIt 3.5.2 and got a no, on software four
years older than the field. The two LATER boxes on this disk were read
rather than run (FORMATS.md, *What Aladdin's own software does with the
same bytes*): their zip readers were lifted out of the installers and
searched for the compared immediate, which is evidence about the code and
not about the behaviour.

**This runs them.** Neither StuffIt installer is DRIVEN — the
installation is ASSEMBLED, which is what the method-14 decoder bought
(FORMATS.md, *StuffIt 5's method 14*): this engine now extracts both
installer payloads whole, and `hfsboot.img` is a plain-HFS Mac OS 9 boot
volume the host can write with hfsutils. So the engine, the translators
and the application are placed into a System Folder from Linux, and the
guest is booted with the result. No Aladdin installer, no serial number,
and for 5.5 no pointer at all.

**One thing cannot be placed, and that is `--carbonlib`.** 7.0.3's
Expander refuses to launch under the CarbonLib the image ships, and
Apple's 1.6 update is a self-mounting NDIF image nothing here
decompresses — so the Macintosh mounts it and Apple's own installer is
walked, which is where the pointer and the two licence buttons come in.

**Where each piece goes is read off the software, never guessed.** The 5.5
engine's own `STR# 999` *Aladdin Folder Names* is `Extensions`, `Aladdin`,
`Extensions:Aladdin`; its `STR# 1004` *Path Names* holds `:Extensions` and
`StuffIt Engine™`; its `fld# 999` names the subfolders `Translators`,
`Viewers`, `Magic Menu Extensions`. The installer's own *What was
installed (and where)* draws the same tree in its two `PICT`s. 7.0.3 is
CFM: `StuffItEngineShell` is `shlb`/`SITe` and carries the Pascal string
`StuffIt Plug-Ins` for the folder its format plug-ins live in.

**The subject is `zipmeta.py --make`'s**, and so is the verdict: four
entries cut out of `rexnebular_1_0_0.zip` with their `0x334d` fields
byte-intact, three of them `TEXT/MSWD`. `MSWD` is the discriminator — no
extension table produces it, so either it comes back or the field was not
read. `checksum.md5` agreeing proves nothing.

    sitzip.py --payload 55      extract the installer payload, no emulator
    sitzip.py --assemble 55     build the boot and transfer volumes
    sitzip.py --run 55          boot, expand, read the volume back
    sitzip.py --carbonlib       install CarbonLib 1.6; once, for 7.0.3
    sitzip.py --run 703         the same for StuffIt Deluxe 7.0.3 Classic
    sitzip.py --list -o <dir>   everything a run left on the volume

**What this cannot see.** The same two things `zipmeta.py` cannot: it
grades the Expander of each box and not every reader in it, and it cannot
tell "read the field and ignored it" from "never looked" — both leave the
same volume. The translator's own bytes are what distinguish those, and
that reading is already in FORMATS.md. The keystrokes that lie — a Return
that renames a volume, a Command key the application does not have, a
button that is not the default — are in tools/vmac/README.md, which is
where a harness's traps live.
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

import run as R                                              # noqa: E402
import os9                                                   # noqa: E402
from arcmac import macbinary                                 # noqa: E402
from superdisk import read_forks                             # noqa: E402
from zipmeta import SUBJECT, report                          # noqa: E402

CACHE = os.path.join(os.path.dirname(R.VMAC_HOME), "sitzip")
HFSBOOT = os.path.join(os.path.dirname(R.VMAC_HOME), "sit5", "hfsboot.img")
MACEXTRACT = os.path.join(REPO, "build", "rel", "macextract")

# The two distributions, as `--setup` left them. Both md5s are in
# FORMATS.md (*The last 68k box*, *The last classic box*) and are checked
# here, because an assembled installation is only as good as its parts.
DIST = {
    "55": dict(
        sit=os.path.join(os.path.dirname(R.VMAC_HOME), "stuffit551",
                         "STUFFITDLX551.SIT"),
        md5="27a0b498f5cd7a892e44241db30b2a42",
        # The installer application inside the distribution; its DATA fork
        # is the StuffIt archive everything else comes out of.
        installer="StuffIt Deluxe™ 5.5/StuffIt Deluxe™ 5.5 Installer",
        app="StuffIt Drag and Drop/StuffIt Expander™",
        expand_key="e",
        # Standard File, already in the transfer volume: one letter.
        pick="r",
        # (selector, destination folder on the boot volume). The
        # destinations are the ones the 5.5 engine names itself — see the
        # module docstring. Entries are picked by TYPE and CREATOR rather
        # than by name: an InstallerMaker payload carries a zero-length
        # DIRECTIVE beside most real files — `STde`/`STin`, one per thing
        # the installer deletes or moves — and `! Zip Translator` is one of
        # those. A name pattern selects the directive as happily as the
        # file, and placing it would put an empty file where the engine
        # looks for a translator.
        place=[(dict(name="StuffIt Engine™", type="SITL", creator="SITe"),
                "Extensions"),
               (dict(name="StuffIt Engine™ PowerPlug", type="shlb",
                     creator="SITe"), "Extensions"),
               (dict(type="SITo", creator="SIT!", count=17),
                "Extensions:Aladdin:Translators")],
        folders=["Extensions:Aladdin", "Extensions:Aladdin:Translators"],
    ),
    "703": dict(
        sit=os.path.join(os.path.dirname(R.VMAC_HOME), "stuffit703",
                         "STFDLX703CLASSIC.SIT"),
        md5="7cec7ff83e2bbe984a2b5a152c466e8d",
        # 7.0.3 ships inside a .smi whose data fork is a plain HFS volume
        # (FORMATS.md, *The last classic box*), so the installer is lifted
        # with hfsutils rather than out of a StuffIt archive.
        smi="StuffItDeluxe_7_0_3.smi",
        installer="StuffIt DLX 703 Classic Install",
        app="StuffIt Drag and Drop/StuffIt Expander",
        expand_key="o",
        # Navigation Services, which opens on the Desktop: the volume
        # first, then the archive. Its `Open` button is for FOLDERS and
        # greys out the moment a file is highlighted, so the archive is
        # taken with `Choose` — the only button on this path that Return
        # cannot reach (`15b-typed-r.png`, measured 2026-10-04).
        pick="sr",
        choose=(668, 510),
        place=[(dict(name="StuffItEngineShell", type="shlb", creator="SITe"),
                "Extensions"),
               (dict(prefix="StuffIt Plug-Ins/", type="shlb", count=23),
                "Extensions:StuffIt Plug-Ins")],
        folders=["Extensions:StuffIt Plug-Ins"],
        carbonlib="1.6",
    ),
}

VOLUME = "SitZip"          # the transfer volume; typed at the Finder
SUBJECT_NAME = "Rex.zip"
APP_NAME = "StuffIt Expander"


# --------------------------------------------------------------- payload

def md5(path):
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def payload(ver, force=False):
    """Extract one installer's payload with THIS engine, and index it.

    Returns {mac path: (type, creator, flags, data path, rsrc path)}.
    The index comes from `macextract l --finder`, which prints the type,
    creator and Finder flags as hex — the four-character columns cannot be
    parsed back when a code holds a space, and three of these do."""
    d = DIST[ver]
    out = os.path.join(CACHE, ver)
    data = os.path.join(out, "files")
    if force:
        shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out, exist_ok=True)

    if not os.path.exists(d["sit"]):
        raise SystemExit("sitzip: no distribution at %s" % d["sit"])
    got = md5(d["sit"])
    if got != d["md5"]:
        raise SystemExit("sitzip: %s is md5 %s, not %s — this is not the "
                         "distribution FORMATS.md names"
                         % (d["sit"], got, d["md5"]))

    inst = os.path.join(out, "installer.bin")
    if not os.path.exists(inst):
        _lift_installer(ver, d, out, inst)
    print("sitzip: installer payload %s (%d B)" % (inst, os.path.getsize(inst)))

    if not os.path.isdir(data):
        os.makedirs(data, exist_ok=True)
        # --overwrite: an InstallerMaker archive repeats names on purpose
        # (the "Move Icon" directives appear twice), and without it the
        # first collision ends the walk with every later entry unwritten.
        subprocess.run([MACEXTRACT, "x", "--overwrite", "-o", data, inst],
                       check=True)
    return data, _index(inst)


def _lift_installer(ver, d, out, inst):
    """The installer application's data fork, out of the distribution."""
    if "smi" in d:
        # hfsutils mounts the .smi's data fork directly: it is a plain HFS
        # volume with its MDB at 1024.
        smi = os.path.join(out, "payload.smi")
        if not os.path.exists(smi):
            tmp = os.path.join(out, "smi")
            subprocess.run([MACEXTRACT, "x", "--overwrite", "-o", tmp,
                            d["sit"]], check=True)
            hit = [os.path.join(r, f)
                   for r, _, fs in os.walk(tmp) for f in fs
                   if f == d["smi"]]
            if not hit:
                raise SystemExit("sitzip: no %s in %s" % (d["smi"], d["sit"]))
            shutil.move(hit[0], smi)
        env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        try:
            subprocess.run(["hmount", smi], check=True, capture_output=True,
                           env=env)
            subprocess.run(["hcopy", "-r", d["installer"], inst], check=True,
                           capture_output=True, env=env)
            subprocess.run(["humount"], capture_output=True, env=env)
        finally:
            shutil.rmtree(env["HOME"], ignore_errors=True)
    else:
        tmp = os.path.join(out, "dist")
        subprocess.run([MACEXTRACT, "x", "--overwrite", "-o", tmp,
                        "--only", d["installer"], d["sit"]], check=True)
        leaf = d["installer"].split("/")[-1]
        hit = [os.path.join(r, f)
               for r, _, fs in os.walk(tmp) for f in fs if f == leaf]
        if not hit:
            raise SystemExit("sitzip: no %s in %s" % (leaf, d["sit"]))
        shutil.move(hit[0], inst)


def _index(inst):
    """Mac path -> (type, creator, flags) off `l --finder`."""
    out = subprocess.run([MACEXTRACT, "l", "--finder", inst],
                         check=True, capture_output=True, text=True).stdout
    idx = {}
    for line in out.splitlines()[1:]:
        parts = line.split(None, 5)
        if len(parts) < 6 or parts[0] != "f":
            continue
        tc, flags, name = parts[3], parts[4], parts[5]
        t, c = tc.split("/")
        idx[name] = (bytes.fromhex(t).decode("mac-roman"),
                     bytes.fromhex(c).decode("mac-roman"), int(flags, 16))
    return idx


# -------------------------------------------------------------- assemble

class Vol:
    """One mounted HFS volume, driven through hfsutils."""

    def __init__(self, img, partition=None):
        self.env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
        cmd = ["hmount", img] + ([str(partition)] if partition else [])
        r = subprocess.run(cmd, capture_output=True, env=self.env, text=True)
        if r.returncode:
            raise SystemExit("sitzip: hmount %s: %s" % (img, r.stderr.strip()))
        self.name = r.stdout.split('"')[1]

    def mkdir(self, path):
        subprocess.run(["hmkdir", "%s:%s" % (self.name, path)],
                       capture_output=True, env=self.env)

    def put(self, blob, dest):
        f = tempfile.mktemp(suffix=".bin")
        open(f, "wb").write(blob)
        try:
            r = subprocess.run([b"hcopy", b"-m", f.encode(),
                                ("%s:%s" % (self.name, dest)).encode()],
                               capture_output=True, env=self.env)
            if r.returncode:
                raise SystemExit("sitzip: hcopy -> %s: %s"
                                 % (dest, r.stderr.decode()))
        finally:
            os.unlink(f)

    def close(self):
        subprocess.run(["humount"], capture_output=True, env=self.env)
        shutil.rmtree(self.env["HOME"], ignore_errors=True)


def forks(data, macpath):
    """(data fork, resource fork) of one extracted entry.

    The CLI writes a resource fork as NAME.rsrc beside the data fork, and
    writes nothing at all for a fork of length zero."""
    p = os.path.join(data, macpath)
    d = open(p, "rb").read() if os.path.exists(p) else b""
    r = open(p + ".rsrc", "rb").read() if os.path.exists(p + ".rsrc") else b""
    return d, r


def matches(data, idx, sel):
    """Payload entries a `place` selector picks, as (mac path, leaf).

    An entry with both forks empty is never a match: that is the shape of
    an InstallerMaker directive, and every real file here has one."""
    out = []
    for k, (t, c, _flags) in sorted(idx.items()):
        if "name" in sel and k != sel["name"]:
            continue
        if "prefix" in sel and (not k.startswith(sel["prefix"])
                                or "/" in k[len(sel["prefix"]):]):
            continue
        if sel.get("type") not in (None, t) or sel.get("creator") not in (None, c):
            continue
        d, r = forks(data, k)
        if not d and not r:
            continue
        # `/` separates the payload's path components and `:` is a literal
        # slash INSIDE a name — the same convention `ComponentToStr63()`
        # undoes on the Macintosh (tools/vmac/README.md). One translator is
        # `btoa:atob`, and handing that leaf to hcopy as-is builds a path
        # with an extra separator in it: hcopy then fails naming the SOURCE
        # file, which is not where the problem is.
        out.append((k, k.split("/")[-1].replace(":", "/")))
    want = sel.get("count")
    if want is not None and len(out) != want:
        raise SystemExit("sitzip: %r selected %d entries, not the %d this "
                         "box is documented to ship: %s"
                         % (sel, len(out), want, [n for _, n in out]))
    return out


def assemble(ver, outdir):
    """Build the boot volume and the transfer volume for one version."""
    d = DIST[ver]
    data, idx = payload(ver)
    os.makedirs(outdir, exist_ok=True)

    if not os.path.exists(SUBJECT):
        raise SystemExit("sitzip: no subject — zipmeta.py --make "
                         "fixtures/rexnebular_1_0_0.zip")
    if not os.path.exists(HFSBOOT):
        raise SystemExit("sitzip: no plain-HFS Mac OS 9 boot volume at %s "
                         "(tools/vmac/README.md, *A plain-HFS Mac OS 9 boot "
                         "volume*)" % HFSBOOT)

    # 7.0.3's Expander refuses to launch under CarbonLib 1.4, which is
    # what `hfsboot.img` carries, so that version starts from the volume
    # `--carbonlib` leaves behind.
    base = HFSBOOT
    if d.get("carbonlib"):
        if not os.path.exists(CARBON_BOOT):
            raise SystemExit("sitzip: StuffIt %s needs CarbonLib %s and this "
                             "boot volume has %s — run --carbonlib first"
                             % (ver, d["carbonlib"], carbon_version(HFSBOOT)))
        base = CARBON_BOOT

    boot = os.path.join(outdir, "boot.img")
    if not os.path.exists(boot):
        print("sitzip: copying %s (1 GB)" % base)
        shutil.copyfile(base, boot)
    print("sitzip: CarbonLib on the boot volume: %s" % carbon_version(boot))

    v = Vol(boot, partition=1)
    placed = []
    try:
        for f in d["folders"]:
            v.mkdir("System Folder:" + f)
        for sel, dest in d["place"]:
            hits = matches(data, idx, sel)
            if not hits:
                raise SystemExit("sitzip: nothing in the payload matches %r "
                                 "— the installation would be incomplete"
                                 % sel)
            for macpath, leaf in hits:
                t, c, flags = idx[macpath]
                df, rf = forks(data, macpath)
                v.put(macbinary(leaf, t, c, df, rf, flags),
                      "System Folder:" + dest + ":")
                placed.append((leaf, t, c, len(df), len(rf),
                               "System Folder:" + dest))
    finally:
        v.close()
    print("sitzip: placed %d file(s) in the System Folder:" % len(placed))
    for leaf, t, c, dn, rn, dest in sorted(placed, key=lambda r: r[5] + r[0]):
        print("  %-34s %s/%s  d=%-8d r=%-8d %s" % (leaf, t, c, dn, rn, dest))

    # The application and the subject travel on their own volume, so what
    # the run wrote can be read back without touching the boot volume.
    app = d["app"]
    if app not in idx:
        raise SystemExit("sitzip: no %s in the payload" % app)
    t, c, flags = idx[app]
    df, rf = forks(data, app)
    appbin = os.path.join(outdir, "app.bin")
    open(appbin, "wb").write(macbinary(APP_NAME, t, c, df, rf, flags))
    print("sitzip: %s %s/%s  d=%d r=%d" % (APP_NAME, t, c, len(df), len(rf)))

    # 'ZIP '/'SITx' is what Aladdin's own software stamps a zip with, and
    # the Expand dialog filters on the name (zipmeta.py).
    sub = os.path.join(outdir, "subject.bin")
    open(sub, "wb").write(macbinary(SUBJECT_NAME, "ZIP ", "SITx",
                                    open(SUBJECT, "rb").read()))

    xfer = os.path.join(outdir, "transfer.img")
    if not os.path.exists(xfer):
        R.sh(sys.executable, os.path.join(HERE, "mkapmdisk.py"),
             os9.DISK, xfer, "32", VOLUME,
             "--macbinary", "%s:%s" % (appbin, APP_NAME),
             "--macbinary", "%s:%s" % (sub, SUBJECT_NAME))
    return boot, xfer


# ------------------------------------------------------------------- run

def drive(q, outdir, settle_wait, expand_key, pick, choose=None):
    """Launch the Expander from the keyboard and hand it the subject.

    Keyboard only, for the reason os9.py gives: a menu ITEM is not
    selectable by either emulator's pointer (tools/vmac/README.md), and
    the Finder's type-to-select plus Cmd-Down needs no coordinates. The
    Expand command has a Command key — ⌘E — which is what makes this
    reachable at all."""
    shots = []

    def shot(tag, wait=0.0):
        if wait:
            time.sleep(wait)
        p = os.path.join(outdir, tag + ".png")
        q.shot(p)
        shots.append((tag, p))
        print("sitzip: %s" % p, flush=True)
        return p

    scratch = os.path.join(outdir, ".wait.png")

    def step(before, label, timeout, poll=5.0, rect=os9.WINDOW_RECT):
        frac, secs = q.wait_change(before, rect, scratch,
                                   timeout=timeout, poll=poll)
        tail = "" if frac >= 0.02 else "  <- NO CHANGE, continuing anyway"
        print("sitzip: %s (%.4f changed in %.0fs)%s"
              % (label, frac, secs, tail), flush=True)

    desk = shot("10-desktop")
    # **No blind Return here, which os9.py's sequence opens with.** That
    # one is `Cmd-Q, Return` to quit the Setup Assistant, which the
    # pristine HFS+ master puts up on every boot. `hfsboot.img` does not:
    # its System Folder was dragged onto it from a guest that had already
    # been through the assistant, so the Finder is frontmost from the
    # first frame (`10-desktop.png`). Cmd-Q then does nothing — the
    # Finder cannot quit — and the Return opens the SELECTED icon's name
    # for EDITING. The boot volume is selected on a fresh desktop, so the
    # three letters typed next went into its name and Cmd-Down committed
    # them: measured 2026-10-04, one run, `HFSBoot` renamed to `sit` and
    # its window opened in place of the transfer volume's. Escape alone,
    # which cancels an edit that is somehow in progress and is otherwise
    # inert.
    q.key("esc")
    front = shot("11-finder", wait=2.0)

    q.key(*VOLUME[:3].lower(), "meta_l-down")      # open the transfer volume
    step(front, "transfer volume opened", 90.0)
    vol = shot("12-volume")

    q.key("s", "t", "u", "meta_l-down")            # launch StuffIt Expander
    step(vol, "Expander launched", 300.0)
    up = shot("13-launched")

    # **The Expand command's Command key is not the same in both
    # boxes**, and it is read out of the application rather than
    # assumed: 5.5's `MENU` 129 is `File ▸ Expand… / E`, 7.0.3's is
    # `File ▸ Expand / O`. A chord the application does not have looks
    # exactly like one the guest ignored — 7.0.3 sat on its drop window
    # for 127 s under ⌘E before this was read (2026-10-04).
    q.key("meta_l-" + expand_key)                  # File > Expand
    step(up, "Expand dialog up", 120.0)
    dlg = shot("14-expand-dialog")

    # **The two dialogs are not the same dialog, and it costs a step.**
    # 5.5 puts up Standard File, whose list is already the transfer
    # volume's and where one letter plus Return opens the archive.
    # 7.0.3 puts up NAVIGATION SERVICES, which opens on the Desktop and
    # lists the volumes — so `r` matches nothing there and the Return
    # opens whatever row is highlighted. That is `HFSBoot`, and the run
    # that did it reported a perfectly healthy "expansion started"
    # (2026-10-04, `14-expand-dialog.png`). Each version therefore names
    # the rows it has to walk.
    for i, letter in enumerate(pick):
        q.key(letter)
        shot("15%s-typed-%s" % (chr(ord("a") + i), letter), wait=2.0)
        if choose and i == len(pick) - 1:
            sys.path.insert(0, HERE)
            import os9mouse                                 # noqa: E402
            ptr = os9mouse.Pointer(q.burst, lambda t: q.frame(t, outdir))
            got = ptr.goto(*choose)
            if got is None or abs(got[0] - choose[0]) > 4 \
                    or abs(got[1] - choose[1]) > 4:
                print("sitzip: cursor is at %s, not %s — the Choose click is "
                      "not the click this run means to make" % (got, choose),
                      flush=True)
            shot("15z-at-choose")
            ptr.press(hold=0.9)
        else:
            q.key("ret")
        time.sleep(6)
    step(dlg, "expansion started", 120.0, poll=3.0)
    shot("16-started")

    secs = q.settle(scratch, interval=5.0, timeout=settle_wait)
    print("sitzip: screen still after ~%s s"
          % ("never" if secs is None else "%.0f" % secs), flush=True)
    done = shot("17-settled")

    # No blind Return here either, for the reason above: if the Expander
    # has already gone, the Finder is frontmost and a Return renames
    # whatever is selected. An alert that needs dismissing shows up in
    # `17-settled.png`.
    q.key("meta_l-q")                              # quit the Expander
    step(done, "Expander quit", 120.0)
    shot("18-quit")

    # Flush the transfer volume from inside the guest: close the window,
    # select the volume on the desktop, Put Away. A volume the guest never
    # flushed fails to mount on the host rather than passing quietly, so
    # this is belt and braces and costs three keystrokes.
    q.key("meta_l-w")
    time.sleep(2)
    q.key(*VOLUME[:3].lower())
    time.sleep(2)
    q.key("meta_l-y")
    shot("19-put-away", wait=8.0)
    return shots


def run(ver, outdir, args):
    d = DIST[ver]
    boot, xfer = assemble(ver, outdir)
    q = os9.Qemu([boot, xfer], os.path.join(outdir, "mon.sock"),
                 tablet=not d.get("choose"), pointer=bool(d.get("choose")))
    try:
        scratch = os.path.join(outdir, ".settle.png")
        waited = q.settle(scratch, timeout=args.boot_wait)
        if waited is None:
            raise SystemExit("sitzip: the screen never stopped changing "
                             "within %.0fs, or qemu exited" % args.boot_wait)
        print("sitzip: desktop settled after ~%.0fs" % waited, flush=True)
        drive(q, outdir, args.settle_wait, d["expand_key"], d["pick"],
              d.get("choose"))
    finally:
        q.close()

    part = os.path.join(outdir, "transfer.hfs")
    os9.hfs_partition(xfer, part)
    rc = report(part, outdir)
    print("\nsitzip: StuffIt %s, assembled into a Mac OS 9 System Folder"
          % ("Deluxe 5.5" if ver == "55" else "Deluxe 7.0.3 Classic"))
    return rc


CARBON = os.path.join(CACHE, "carbonlib", "CarbonLib_1.6.smi.bin")
CARBON_URL = "https://old.mac.gdn/apps/CarbonLib_1.6.smi_.bin"
CARBON_PAGE = "https://macintoshgarden.org/apps/carbonlib"
CARBON_MD5 = "02aae2b0d7740cbb58e6a7cf03e935f9"
CARBON_BOOT = os.path.join(CACHE, "hfsboot-carbon.img")
# The two buttons Return cannot reach, measured off the screenshots they
# are named for: the disk image's own licence sheet (`c13-licence.png`,
# buttons on y=535, `Agree` centred at x=700) and the installer's
# "you must agree" alert (`c19-agree-alert.png`, `Agree` at 642,450).
AGREE_SMI = (700, 535)
AGREE_INSTALLER = (642, 450)


def carbon_version(img, partition=1):
    """CarbonLib's `vers` 1, read off a boot image. The positive check."""
    import struct
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        subprocess.run(["hmount", img, str(partition)], check=True,
                       capture_output=True, env=env)
        t = tempfile.mktemp(suffix=".bin")
        r = subprocess.run(["hcopy", "-m",
                            "HFSBoot:System Folder:Extensions:CarbonLib", t],
                           capture_output=True, env=env)
        subprocess.run(["humount"], capture_output=True, env=env)
        if r.returncode:
            return None
        blob = open(t, "rb").read()
        os.unlink(t)
        dlen, rlen = struct.unpack(">II", blob[83:91])
        roff = 128 + ((dlen + 127) & ~127)
        sys.path.insert(0, HERE)
        from spacesaver import resources                    # noqa: E402
        v = resources(blob[roff:roff + rlen])["vers"][1][1][6:]
        return v[1:1 + v[0]].decode("mac-roman", "replace")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


def carbonlib(outdir, args):
    """Install CarbonLib 1.6 into the plain-HFS boot volume.

    **Why this exists at all.** StuffIt Expander 7.0.3 refuses to run on
    the image as it stands — *"Expander requires CarbonLib 1.6.0 or
    later."*, photographed 2026-10-04 — and `hfsboot.img` carries
    **1.4**, read off its own `vers` resource. 1.6 is an Apple update
    that postdates Mac OS 9.2, not something the system shipped with.

    **And why it needs the guest.** Apple ships it as a self-mounting
    image whose data fork is NDIF: the resource fork carries a `bcem`
    naming the volume `CarbonLib`, so the bytes are compressed and no
    tool on this machine reads them (disk images are out of scope,
    OPEN_ITEMS.md Part 1). The 40 MB `CarbonLib_160_languages.sit` is
    nothing but the same `.smi` once per language. So the image is
    mounted by the only thing that can mount it — the Macintosh.

    The pass condition is read off the DISK afterwards, not off a
    screenshot: `carbon_version()` re-reads the extension's `vers`."""
    os.makedirs(outdir, exist_ok=True)
    if not os.path.exists(CARBON):
        raise SystemExit("sitzip: no %s — fetch it with\n  curl -sSL "
                         "-A 'Mozilla/5.0' -e %s %s -o %s"
                         % (CARBON, CARBON_PAGE, CARBON_URL, CARBON))
    if md5(CARBON) != CARBON_MD5:
        raise SystemExit("sitzip: %s is not the file this was written "
                         "against (md5 %s)" % (CARBON, CARBON_MD5))

    boot = os.path.join(outdir, "boot.img")
    if not os.path.exists(boot):
        print("sitzip: copying %s (1 GB)" % HFSBOOT, flush=True)
        shutil.copyfile(HFSBOOT, boot)
    print("sitzip: CarbonLib on the image before: %s" % carbon_version(boot),
          flush=True)

    xfer = os.path.join(outdir, "transfer.img")
    if not os.path.exists(xfer):
        R.sh(sys.executable, os.path.join(HERE, "mkapmdisk.py"),
             os9.DISK, xfer, "16", VOLUME,
             "--macbinary", "%s:%s" % (CARBON, "CarbonLib.smi"))

    # The pointer, because one of this installer's buttons is not a
    # default: Apple's licence sheet draws `Disagree` and `Agree` with
    # identical frames and Return selects neither (`c13-mounted.png`,
    # measured 2026-10-04). Everything else here is keyboard.
    q = os9.Qemu([boot, xfer], os.path.join(outdir, "mon.sock"),
                 tablet=False, pointer=True)
    try:
        scratch = os.path.join(outdir, ".settle.png")
        if q.settle(scratch, timeout=args.boot_wait) is None:
            raise SystemExit("sitzip: never reached the desktop")
        shots = []

        def shot(tag, wait=0.0):
            if wait:
                time.sleep(wait)
            p = os.path.join(outdir, tag + ".png")
            q.shot(p)
            shots.append(p)
            print("sitzip: %s" % p, flush=True)
            return p

        shot("c10-desktop")
        q.key("esc")
        q.key(*VOLUME[:3].lower(), "meta_l-down")   # open the transfer volume
        shot("c11-volume", wait=10.0)
        q.key("esc")
        q.key("c", "a", "r", "meta_l-down")         # launch CarbonLib.smi
        shot("c12-mounted", wait=90.0)
        before = shot("c13-licence", wait=60.0)

        sys.path.insert(0, HERE)
        import os9mouse                                     # noqa: E402
        ptr = os9mouse.Pointer(q.burst, lambda t: q.frame(t, outdir))

        def click(label, xy, wait=30.0):
            got = ptr.goto(*xy)
            if got is None or abs(got[0] - xy[0]) > 4 or abs(got[1] - xy[1]) > 4:
                print("sitzip: cursor is at %s, not %s — the %s click is not "
                      "the click this run means to make" % (got, xy, label),
                      flush=True)
            shot("c-at-" + label)
            ptr.press(hold=0.9)
            return shot("c-" + label, wait=wait)

        click("agree-smi", AGREE_SMI)
        # Agreeing MOUNTS the volume and opens no window, so the rest is
        # ordinary Finder work: close the transfer volume's window, pick
        # `CarbonLib` off the desktop, open it, and open the first item in
        # it — Tab selects the first icon by name, which on this disk is
        # the installer.
        q.key("meta_l-w")
        time.sleep(2)
        q.key("esc")
        q.key("c", "a", "r", "meta_l-down")
        shot("c16-carbonlib-volume", wait=15.0)
        q.key("tab")
        shot("c17-selected", wait=4.0)
        q.key("meta_l-down")
        shot("c18-installer", wait=60.0)
        # `Apple SW Install`'s own pages DO have default buttons —
        # `Continue`, `Select`, `Install` are all ringed — so Return
        # walks them. The one exception is the same as on the disk
        # image: the *"you must agree to the terms"* alert draws
        # `Disagree` and `Agree` identically and Return selects neither,
        # measured over six presses that moved nothing
        # (`c25-return.png`, 2026-10-04). So one more click.
        q.key("ret")                                   # Continue
        shot("c19-agree-alert", wait=20.0)
        click("agree-installer", AGREE_INSTALLER)
        # Each press is photographed; one that lands nowhere shows up as
        # an unchanged frame rather than as a silent success.
        for i in range(args.returns):
            q.key("ret")
            shot("c2%d-return" % i, wait=40.0)
    finally:
        q.close()

    got = carbon_version(boot)
    print("sitzip: CarbonLib on the image after: %s" % got, flush=True)
    if got and got.startswith("1.6"):
        shutil.copyfile(boot, CARBON_BOOT)
        print("sitzip: kept the installed boot volume as %s" % CARBON_BOOT)
        return 0
    return 1


def listing(outdir):
    """Everything the run left on the transfer volume, for the record."""
    part = os.path.join(outdir, "transfer.hfs")
    if not os.path.exists(part):
        raise SystemExit("sitzip: no %s — run first" % part)
    for path, (t, c, d, r) in sorted(read_forks(part).items()):
        print("  %-50s %s/%s  d=%-8d r=%d"
              % ("/".join(path), t, c, len(d or b""), len(r or b"")))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--payload", choices=sorted(DIST))
    ap.add_argument("--assemble", choices=sorted(DIST))
    ap.add_argument("--run", choices=sorted(DIST))
    ap.add_argument("--list", action="store_true",
                    help="what the last run left on the transfer volume")
    ap.add_argument("--carbonlib", action="store_true",
                    help="install CarbonLib 1.6 into the boot volume, which "
                         "StuffIt Expander 7.0.3 refuses to run without")
    ap.add_argument("--returns", type=int, default=0,
                    help="Return presses to walk the installer with")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--boot-wait", type=float, default=600.0)
    ap.add_argument("--settle-wait", type=float, default=300.0)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    ver = a.payload or a.assemble or a.run
    outdir = a.out or os.path.join(CACHE, "run%s" % (ver or ""))
    if a.payload:
        data, idx = payload(a.payload, force=a.force)
        print("sitzip: %d entries indexed, forks under %s" % (len(idx), data))
    elif a.assemble:
        assemble(a.assemble, outdir)
    elif a.carbonlib:
        sys.exit(carbonlib(a.out or os.path.join(CACHE, "carbon"), a))
    elif a.run:
        sys.exit(run(a.run, outdir, a))
    elif a.list:
        listing(outdir)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
