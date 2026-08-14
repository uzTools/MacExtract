#!/usr/bin/env python3
"""cptsegment.py — make segmented Compact Pro archives on an emulated Mac.

A segmented `.cpt` is the one multi-part scheme this project has no sample
of and no reference implementation for. `unar` and `macunpack` both read
the fields involved and ignore them; The Unarchiver's own format wiki marks
all three "meaning not entirely clear" (reference/notes/cpt_specs_theunarchiver.md).
What IS documented is what the scheme promises, by the author, in
reference/notes/cpt_users_guide.txt: at most 255 segments, each an ordinary
Macintosh file, named and placed freely "since Compact Pro saves information
inside the files to determine their proper ordering", and the FINAL segment
is the one you open.

So the specimen is generated here, by the application itself — the only
implementation that writes this format — and the ground truth is exact
without any reverse engineering: the set is made by segmenting an archive
the differential suite ALREADY adjudicates, so whatever a reader gets out of
the segments must equal what it gets out of the original.

The manual's second route is the one automated here. Segmenting on the fly
by filling a disk needs disk swaps; `Misc > Segment` divides an existing
archive on one volume, which is a dialog and a Save box per segment.

    cptsegment.py --map            photograph the application's menus
    cptsegment.py --case edu3      generate one specimen set
    cptsegment.py --list

Output lands in `$UNC_VMAC_HOME/specimens/<case>/`: every segment as raw
data-fork bytes, plus a `case.json` recording what made it. That is beside
the emulator rather than under `build/`, which `make clean` removes.
"""
import argparse, glob, json, os, shutil, struct, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import run as R                                     # noqa: E402
from interactive import Mac                         # noqa: E402
from mkboot import LISTING_DATE                     # noqa: E402
import synth_wrapped as W                           # noqa: E402

# Compact Pro's own type/creator, measured across 65 corpus entries: an
# archive is PACT/CPCT and the application is APPL/CPCT. The type is why
# the source archive has to arrive as MacBinary — Standard File inside
# another application filters on it, and a data-fork copy is invisible.
CPT_TYPE, CPT_CREATOR = b"PACT", b"CPCT"
APP_TYPE = b"APPL"

APP_NAME = "Compact Pro"
SOURCE_NAME = "Source.cpt"

# The application, and the archive it lives in. Extracted with our own CLI,
# which is circular for the APPLICATION (if we unpacked it wrongly it would
# not run, and that is the check) and not circular for anything measured.
APP_FIXTURE = "compact-pro-151.hqx"
APP_PATH = "Compact Pro 1.51/Compact Pro"

CASES = {
    # case: (source fixture, segment-size choice, what the shape is for)
    "edu3": ("derived-Education7.1.cpt", 24,
             "folders and several entries per segment"),
    "biplane5": ("derived-BiPlane__2_Share.cpt", 24,
                 "ONE entry, so its data straddles every boundary"),
}


def cli():
    exe = os.path.join(REPO, "build", "dev", "unclassic")
    if not os.path.exists(exe):
        R.sh("make", "-C", REPO, "BUILD=build/dev", "all")
    return exe


def extract_app(workdir):
    """Unpack Compact Pro from the corpus, as MacBinary ready for the volume."""
    out = os.path.join(workdir, "app")
    os.makedirs(out, exist_ok=True)
    R.sh(cli(), "x", "-o", out, os.path.join(REPO, "fixtures", APP_FIXTURE))
    data = os.path.join(out, APP_PATH)
    rsrc = data + ".rsrc"
    for p in (data, rsrc):
        if not os.path.exists(p):
            raise SystemExit(f"cptsegment: {APP_FIXTURE} did not yield {p}")
    binpath = os.path.join(workdir, "CompactPro.bin")
    with open(binpath, "wb") as f:
        f.write(W.macbinary(APP_NAME, open(data, "rb").read(),
                            open(rsrc, "rb").read(),
                            ftype=APP_TYPE, creator=CPT_CREATOR))
    return binpath


def source_macbinary(fixture, workdir):
    """The archive to be segmented, as a PACT/CPCT MacBinary file."""
    src = os.path.join(REPO, "fixtures", fixture)
    if not os.path.exists(src):
        raise SystemExit(f"cptsegment: no fixture {fixture}")
    # A .cpt in the corpus is not necessarily a .cpt: alpha401.cpt is a
    # MacBinary file holding one, because that is how it was uploaded. Wrap
    # that and the Mac gets a PACT file whose data fork is an envelope, and
    # Compact Pro says it is "damaged or has a format which this version
    # does not recognize" — six minutes of emulator to learn something the
    # first two bytes say. The derived-* copies are the unwrapped ones.
    head = open(src, "rb").read(8)
    if len(head) < 8 or head[0] != 1 or head[1] != 1:
        raise SystemExit(
            f"cptsegment: {fixture} does not start like a single-volume "
            f"Compact Pro archive (first bytes {head[:4].hex(' ')}) — "
            f"a derived-*.cpt is the unwrapped form")
    out = os.path.join(workdir, "source.bin")
    with open(out, "wb") as f:
        f.write(W.macbinary(SOURCE_NAME, open(src, "rb").read(),
                            ftype=CPT_TYPE, creator=CPT_CREATOR))
    return out


def boot_image(fixture, workdir, system="System6.hfv"):
    stock = os.path.join(R.VMAC_HOME, system)
    if not os.path.exists(stock):
        raise SystemExit(f"cptsegment: no {system} — run tools/vmac/setup.sh")
    img = os.path.join(workdir, "boot-cpt.hfv")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"), stock,
         extract_app(workdir), img, "--finder", "--app-name", APP_NAME,
         "--macbin", f"{source_macbinary(fixture, workdir)}:{SOURCE_NAME}")
    return img


# The Finder desktop, on a 512x342 Mac Plus screen. The boot volume icon is
# where the Finder always puts it. The application is the SECOND icon in the
# volume window — measured off 2-volume.png, not guessed: the first version
# of this clicked the fourth icon, which is Source.cpt, and the Finder said
# the archive "could not be opened (the application is busy or missing)".
# That failure at least announced itself; a click on empty window background
# would have opened nothing and looked like a slow launch.
FINDER_VOLUME_ICON = (480, 40)
FINDER_APP_ICON = (105, 105)

# "THIS IS AN UNREGISTERED COPY", with Register and Not Yet. Measured off
# 3-launched.png.
NAG_NOT_YET = (433, 249)

# Menu titles: File Edit Archive View Misc, with Archive and View dimmed
# until an archive is open. The x of each is the CENTRE of its title,
# measured off the pulled-down screenshots — the first set of guesses was
# one menu to the left all the way along, so every shot was mislabelled and
# "6-menu-Misc-open.png" was a photograph of the View menu. A menu map that
# names its own shots wrongly is worse than no map.
MENU_Y = 10
MENUS = {"File": 45, "Edit": 80, "Archive": 135, "View": 190, "Misc": 232}


def launch(mac, shot, args):
    if mac.settle(os.path.join(args.outdir, ".settle.png"),
                  interval=5.0, timeout=args.boot_timeout) is None:
        raise SystemExit("cptsegment: the machine never reached the Finder")
    shot(mac, "1-desktop.png")
    mac.click(*FINDER_VOLUME_ICON, double=True)
    time.sleep(4.0)
    shot(mac, "2-volume.png")
    # Select, photograph, THEN open with Cmd-O. A double-click asks two
    # questions at once — is this the right icon, and did the two clicks
    # arrive inside the Mac's threshold — and answers neither when it fails.
    mac.click(*FINDER_APP_ICON)
    time.sleep(1.0)
    shot(mac, "2b-selected.png")
    mac.command_key("o")
    time.sleep(args.launch_wait)
    shot(mac, "3-launched.png")
    # An unregistered copy opens on a shareware notice. Neither button is
    # the default one, so this is a coordinate rather than a Return.
    mac.click(*NAG_NOT_YET)
    time.sleep(2.0)
    shot(mac, "3b-nag-dismissed.png")


def pull_down(mac, x):
    """Press and HOLD on a menu title, the way System 6 menus are used."""
    ox, oy = mac.origin()
    mac._xdo("mousemove", str(ox + x), str(oy + MENU_Y))
    time.sleep(0.3)
    mac._xdo("mousedown", "1")
    time.sleep(1.0)


def release(mac, x=None, y=None):
    """Let go — over an item to choose it, or where it is to close the menu."""
    if x is not None:
        ox, oy = mac.origin()
        mac._xdo("mousemove", str(ox + x), str(oy + y))
        time.sleep(0.4)
    mac._xdo("mouseup", "1")
    time.sleep(1.0)


def open_source(mac, shot, args):
    """File > Open, then take the archive Standard File offers."""
    mac.command_key("o")
    time.sleep(3.0)
    shot(mac, "5-open-dialog.png")
    mac.click(*SF_FIRST_ROW)
    mac.key("Return")
    time.sleep(args.launch_wait)
    shot(mac, "5b-archive-open.png")


# Standard File inside Compact Pro, not inside our own application. The
# manager is the same but the DIALOG is the application's own resource, and
# this one sits higher and wider than ours: its first row is at y=88 where
# interactive.py's is at 137. Measured off 5-open-dialog.png — the first
# version imported our own constant, clicked below the last row, selected
# nothing, and photographed a dialog with Open dimmed.
SF_FIRST_ROW = (150, 88)


# Misc menu items, measured off 6-menu-Misc.png. Segment has no keyboard
# equivalent, so it is the one thing here that must be released over.
MISC_SEGMENT = (270, 59)

# The Segment dialog, measured off 7-segment-dialog.png: five radio buttons
# (fill disk / 1390K / 775K / 385K / a size in K) and Cancel + OK. The last
# radio has an editable field beside it, which is what makes a specimen of
# a chosen shape possible at all — the disk sizes would all put this
# 85 KB archive in one segment.
SEG_CUSTOM_RADIO = (166, 187)
SEG_CUSTOM_FIELD = (196, 187)
SEG_OK = (336, 222)


def choose(mac, menu, item_xy):
    """Pull a menu down and release over one of its items."""
    pull_down(mac, MENUS[menu])
    release(mac, *item_xy)


def set_segment_size(mac, shot, size_k):
    """Choose the custom size radio and type the size into its field."""
    mac.click(*SEG_CUSTOM_RADIO)
    time.sleep(0.5)
    # Double-click selects the number already in the field, so typing
    # replaces it. Typing without selecting appends to "100" and asks for
    # 10024K segments, which is one segment and looks like a working run.
    mac.click(*SEG_CUSTOM_FIELD, double=True)
    time.sleep(0.5)
    for ch in str(size_k):
        mac.key(ch)
    shot(mac, "7b-size-typed.png")
    mac.click(*SEG_OK)
    time.sleep(2.0)


def save_each_segment(mac, shot, args):
    """Accept the Save box the application puts up for every segment.

    The manual: "Compact Pro prompts you to name each segment as it creates
    the segment files". The suggested names are its own convention
    (NAME.cpt.#1, #2 ...), which is exactly what a specimen should carry,
    so each box is accepted with Return and nothing is renamed.

    How many boxes there are is not known in advance — it is what the
    segment size and the archive decide — so this stops when the screen
    stops changing rather than counting. A fixed count would either leave a
    dialog up or press Return into the catalog window afterwards.
    """
    prev, saved = None, 0
    for i in range(args.max_segments):
        p = os.path.join(args.outdir, f"8-save-{i + 1:02d}.png")
        mac.shot(p)
        cur = open(p, "rb").read()
        if cur == prev:
            os.remove(p)
            break
        prev = cur
        saved += 1
        print(f"  save box {saved}")
        mac.key("Return")
        time.sleep(args.save_wait)
    else:
        raise SystemExit("cptsegment: the save boxes never stopped coming")
    return saved - 1          # the last shot was the static screen after


def read_volume(image, outdir, skip):
    """Copy every data fork off the boot volume, except the ones we put there.

    Read from the emulator's OWN copy of the image: Mac() boots a private
    copy, and reading the one that was handed to it reports an empty volume
    for a run that worked (tools/vmac/README.md).
    """
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    got = {}
    try:
        # The emulator was SIGKILLed a moment ago and can still have the
        # image open; hmount then fails outright. Seen once in four runs,
        # and it looks exactly like a run that segmented nothing.
        for attempt in range(5):
            r = subprocess.run(["hmount", image], env=env,
                               capture_output=True, text=True,
                               errors="surrogateescape")
            if r.returncode == 0:
                break
            time.sleep(2.0)
        else:
            raise SystemExit(f"cptsegment: cannot mount {image}: {r.stderr}")
        out = r.stdout
        vol = out.split('Volume name is "', 1)[1].split('"', 1)[0]
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
            subprocess.run(["hcopy", "-r", f"{vol}:{name}", dest],
                           check=True, env=env, capture_output=True)
            got[name] = dest
        subprocess.run(["humount"], env=env, capture_output=True)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    return got


def phase_generate(args, workdir, shot):
    """Segment an archive the differential suite already adjudicates."""
    fixture, size_k, why = CASES[args.case]
    img = boot_image(fixture, workdir)
    mac = Mac(img, args.emu, workdir)
    try:
        launch(mac, shot, args)
        open_source(mac, shot, args)
        choose(mac, "Misc", MISC_SEGMENT)
        time.sleep(2.0)
        shot(mac, "7-segment-dialog.png")
        set_segment_size(mac, shot, size_k)
        nseg = save_each_segment(mac, shot, args)
        shot(mac, "9-done.png")
        # Quit, so anything the application still holds is written and the
        # volume is left clean rather than mid-update.
        mac.command_key("q")
        time.sleep(args.save_wait)
        shot(mac, "9b-quit.png")
    finally:
        mac.close()

    dest = os.path.join(args.specimens, args.case)
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    files = read_volume(os.path.join(workdir, "boot.hfv"), dest,
                        skip={APP_NAME, SOURCE_NAME})
    meta = {
        "case": args.case,
        "why": why,
        "source_fixture": fixture,
        "segment_size_k": size_k,
        "made_by": "Compact Pro 1.51 on System 6.0.8 under Mini vMac",
        "save_boxes": nseg,
        "segments": {n: os.path.getsize(p) for n, p in sorted(files.items())},
    }
    with open(os.path.join(dest, "case.json"), "w") as f:
        json.dump(meta, f, indent=1, sort_keys=True)
    print(f"cptsegment: {len(files)} file(s) off the volume -> {dest}")
    for n, p in sorted(files.items()):
        print(f"    {n:28s} {os.path.getsize(p)} bytes")
    if not files:
        raise SystemExit("cptsegment: the volume holds no new files — "
                         "the run did not segment anything")


def phase_map(args, workdir, shot):
    """Photograph the application and each of its menus.

    Nothing here drives a third-party application, so its menu bar is
    unknown ground: this pulls each title down and photographs it, which is
    one boot instead of one boot per guess. Menu titles are clicked at a
    sweep of x positions along the menu bar rather than at names, because
    the names are what is being looked for.
    """
    img = boot_image(CASES[args.case][0], workdir)
    mac = Mac(img, args.emu, workdir)
    try:
        launch(mac, shot, args)
        # Only with an archive OPEN: three of the five menus are dimmed
        # until there is one, and Segment is a thing you do to an archive.
        open_source(mac, shot, args)
        for name, x in sorted(MENUS.items(), key=lambda kv: kv[1]):
            pull_down(mac, x)
            shot(mac, f"6-menu-{name}.png")
            release(mac)
    finally:
        mac.close()
    print(f"cptsegment: menu map in {args.outdir}")


def phase_verify(args):
    """Check the Python generator against what the application wrote.

    tools/synth_cptsplit.py writes this layout from a description derived
    off these specimens. Reproducing them BYTE FOR BYTE is what stops that
    description from quietly becoming its own authority — a generator
    validated against nothing is a second copy of the reader's
    assumptions. The set identity is the one field that may differ, since
    the application draws one per set and only requires it to be shared,
    so it is forced to the specimen's value and everything else compared.
    """
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import synth_cptsplit as S
    cases = sorted(d for d in os.listdir(args.specimens)
                   if os.path.isdir(os.path.join(args.specimens, d)))
    if not cases:
        raise SystemExit(f"cptsegment: no specimens in {args.specimens} — "
                         f"run --case first")
    bad = 0
    for case in cases:
        d = os.path.join(args.specimens, case)
        meta = json.load(open(os.path.join(d, "case.json")))
        real = [open(p, "rb").read() for p in sorted(
            glob.glob(os.path.join(d, "Source.cpt.#*")),
            key=lambda p: int(p.rsplit("#", 1)[1]))]
        src = open(os.path.join(REPO, "fixtures",
                                meta["source_fixture"]), "rb").read()
        ident = struct.unpack(">H", real[0][2:4])[0]
        mine = S.segment(src, meta["segment_size_k"] * 1024, ident=ident)
        ok = len(mine) == len(real) and all(a == b for a, b in zip(real, mine))
        print("%-10s %d segments made by Compact Pro 1.51: %s"
              % (case, len(real), "reproduced exactly" if ok else "DIFFERS"))
        bad += not ok
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", default="edu3", choices=sorted(CASES))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--map", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--emu", default="mv-4M")
    ap.add_argument("--outdir", default=os.path.join(REPO, "build", "cptseg"))
    # NOT under build/, which `make clean` removes — the first two
    # specimens were made there and the next ci.sh deleted both. Same
    # reasoning setup.sh gives for keeping 80 MB of emulator out of it.
    ap.add_argument("--specimens",
                    default=os.path.join(R.VMAC_HOME, "specimens"))
    ap.add_argument("--boot-timeout", type=float, default=300.0)
    ap.add_argument("--launch-wait", type=float, default=20.0)
    ap.add_argument("--save-wait", type=float, default=8.0)
    ap.add_argument("--max-segments", type=int, default=24)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    if args.verify:
        return phase_verify(args)

    if args.list:
        for k, (fx, size, why) in sorted(CASES.items()):
            print(f"{k:8s} {fx:28s} {size:3d}K segments — {why}")
        return 0

    os.makedirs(args.outdir, exist_ok=True)
    workdir = tempfile.mkdtemp(prefix="cptseg-")

    def shot(mac, name):
        p = os.path.join(args.outdir, name)
        mac.shot(p)
        print("  shot", name)

    try:
        if args.map:
            phase_map(args, workdir, shot)
        else:
            phase_generate(args, workdir, shot)
        return 0
    finally:
        if args.keep:
            print("kept:", workdir)
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
