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

**What this measured, 2026-08-23: the cipher is right, both ways.**
Three archives Compact Pro encrypted come back byte-exact through this
engine, and an archive this engine encrypted extracts under Compact Pro
with its own CRC over both decrypted forks passing. FORMATS.md,
*Compact Pro's cipher*.

Encryption is behind the REGISTRATION, which is the only reason this
took two attempts. An unregistered copy answers Extract with *"This
version of Compact Pro cannot validate or extract encrypted files"* and
hides the Add dialog's Encrypt checkbox at a negative rect; Macintosh
Garden publishes a registration for 1.51 and with it both work. There
is still no other IMPLEMENTATION to compare against — CptExpand says it
"will not extract encrypted files", StuffIt's own Compact Pro
translator answers "the file is password protected", and The
Unarchiver's notes call the algorithm unknown — which is why the
application itself has to be the grader.
"""
import argparse
import json
import os
import re
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
from arcmac import FINDER_OWN                        # noqa: E402

# `hdir`'s name column on a BYTES listing — see cptsegment.read_volume for
# why the listing cannot be read as text.
LISTING_DATE_B = re.compile(LISTING_DATE.pattern.encode("ascii"))
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
NAG_REGISTER = (81, 248)
SF_FIRST_ROW = (150, 88)
MENU_Y = 10
MENUS = {"File": 45, "Edit": 80, "Archive": 135, "View": 190, "Misc": 232}

# The Finder's Special menu, and Shut Down in it — arcmac.py's System 6
# coordinates, and it releases 25 pixels to the RIGHT of the title so
# the pointer is inside the menu rather than on its left edge.
SPECIAL_X = 175
SHUT_DOWN_Y = 123

# The Add dialog (DITL 312) as a REGISTERED copy draws it — measured off
# cptmake/m1-add-dialog.png. The Encrypt checkbox is the reason this
# phase needs a registered copy at all: the routine at 0x4864 moves it
# into view, and until then it sits at a negative rect.
ADD_ENCRYPT = (128, 54)
ADD_SUBJECT_ROW = (200, 206)
ADD_BUTTON = (155, 302)
ADD_DONE = (452, 302)
ADD_ALL_BUTTON = (255, 302)
ADD_ROW_H = 15
ADD_PROBE_ROWS = (191, 206, 221)
MADE_NAME = "Made.cpt"

# Archive > Note... — what Compact Pro calls the archive comment. It is
# the last item of that menu and the only step here without a keyboard
# equivalent, so it needs a coordinate; measured off 6-menu-Archive.png,
# which `--explore` photographs.
NOTE_Y = 156
# The Note dialog's OK button, measured off n2-note-dialog.png. Return
# does NOT press it: the note field is multi-line and Return puts a CR
# in the text (measured 2026-08-23 — the first run typed its Save, its
# filename and its quit into a dialog that was still open, and wrote no
# archive at all). So `--note` takes `\n` for a line break and OK is
# clicked.
NOTE_OK = (451, 243)


def cli():
    exe = os.path.join(REPO, "build", "dev", "macextract")
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


def source_macbinary(workdir, password, fixture=None):
    """The archive, as a PACT/CPCT file Standard File will show."""
    if fixture:
        blob = open(os.path.join(REPO, "fixtures", fixture), "rb").read()
        if len(blob) < 8 or blob[0] != 1 or blob[1] != 1:
            raise SystemExit("cptcrypt: %s is not a single-volume .cpt "
                             "(a derived-*.cpt is the unwrapped form)"
                             % fixture)
    else:
        blob = SCPT.build(password.encode("mac_roman") if password else None)
    open(os.path.join(workdir, "Secret.cpt"), "wb").write(blob)
    out = os.path.join(workdir, "source.bin")
    with open(out, "wb") as f:
        f.write(W.macbinary(SOURCE_NAME, blob, ftype=CPT_TYPE,
                            creator=CPT_CREATOR))
    return out


def boot_image(workdir, password, system="System6.hfv", fixture=None,
               make=False, probe=False):
    stock = os.path.join(R.VMAC_HOME, system)
    if not os.path.exists(stock):
        raise SystemExit(f"cptcrypt: no {system} — run tools/vmac/setup.sh")
    img = os.path.join(workdir, "boot-cptcrypt.hfv")
    argv = [sys.executable, os.path.join(HERE, "mkboot.py"), stock,
            extract_app(workdir), img, "--finder", "--app-name", APP_NAME]
    if make:
        for path, nm in make_source(workdir, probe):
            argv += ["--macbin", f"{path}:{nm}"]
    else:
        argv += ["--macbin",
                 f"{source_macbinary(workdir, password, fixture)}:"
                 f"{SOURCE_NAME}"]
    R.sh(*argv)
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


def register(mac, shot, args):
    """Type a registration into the shareware notice.

    Macintosh Garden publishes one for 1.51 (Name "Registered", Code
    35427117), and it is what unlocks ENCRYPTION: with it the refusal
    goes away and the Add dialog's Encrypt checkbox appears. There is a
    `*` test at 0x485e that suggested otherwise — a reading recorded in
    BLOCKERS.md as withdrawn, because one branch of a routine is not the
    routine.
    """
    name, code = args.register.split(":", 1)
    mac.click(*NAG_REGISTER)
    time.sleep(2.5)
    shot(mac, "3c-register-dialog.png")
    mac._xdo("type", "--delay", "150", name)
    time.sleep(1.0)
    shot(mac, "3d-name-typed.png")
    mac.key("Tab")
    time.sleep(0.5)
    mac._xdo("type", "--delay", "150", code)
    time.sleep(1.0)
    shot(mac, "3e-code-typed.png")
    mac.key("Return")
    time.sleep(3.0)
    shot(mac, "3f-registered.png")


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
    if args.register:
        register(mac, shot, args)
    else:
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


# The file the --make phase compresses, and every property of it is
# chosen so that the archive it lands in can be read for its CIPHER
# ALONE. Both forks are pseudo-random, because Compact Pro picks LZH
# when LZH helps and this must come back RLE-only (flags bits 1 and 2
# clear); no byte is 0x81, so the RLE stage is a straight copy; and the
# generator is a fixed LCG, so the specimen is reproducible.
#
# With all three, ciphertext XOR plaintext IS the keystream, which is
# what turns a "wrong password" into a diff.
MAKE_NAME = "Subject"


def _incompressible(n, seed):
    out = bytearray()
    x = seed
    while len(out) < n:
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        b = (x >> 16) & 0xFF
        if b != 0x81:
            out.append(b)
    return bytes(out)


MAKE_DATA = _incompressible(600, 1)
MAKE_RSRC = _incompressible(400, 7)

# The probe set: data forks only, and two lengths chosen to separate the
# possible padding rules. 100 and 103 both round up to 104 under "pad to
# a multiple of eight" but to 104 and 104 under it too, while PKCS#5's
# "always add one to eight" gives 104 and 104 as well — what actually
# separates them is 96, which is already a multiple of eight: it stays
# 96 under the first rule and becomes 104 under the second. All three
# are incompressible, so the RLE stage is a copy and the compressed
# length IS the cipher's.
PROBES = [("P96", _incompressible(96, 11)),
          ("P100", _incompressible(100, 13)),
          ("P103", _incompressible(103, 17))]


def make_source(workdir, probe=False):
    """The file(s) the --make phase compresses, as MacBinary. `probe`
    swaps the one two-fork subject for the three data-fork lengths that
    separate the padding rules."""
    if not probe:
        out = os.path.join(workdir, "subject.bin")
        with open(out, "wb") as f:
            f.write(W.macbinary(MAKE_NAME, MAKE_DATA, MAKE_RSRC, b"TEXT",
                                b"ttxt"))
        return [(out, MAKE_NAME)]
    made = []
    for name, data in PROBES:
        out = os.path.join(workdir, name + ".bin")
        with open(out, "wb") as f:
            f.write(W.macbinary(name, data, b"", b"TEXT", b"ttxt"))
        made.append((out, name))
    return made


def save_specimen(workdir, args):
    """Copy the archive Compact Pro wrote off the volume, with a JSON
    saying what went into it — the specimen this format has never had.

    It lands beside the emulator's other state rather than under
    `build/`, for the reason cptsegment.py's does: the next `./ci.sh`
    runs `make clean`.
    """
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    dest = os.path.join(args.outdir, MADE_NAME)
    try:
        r = subprocess.run(["hmount", os.path.join(workdir, "boot.hfv")],
                           env=env, capture_output=True, text=True,
                           errors="surrogateescape")
        if r.returncode != 0:
            raise SystemExit("cptcrypt: cannot mount the volume back")
        vol = r.stdout.split('Volume name is "', 1)[1].split('"', 1)[0]
        got = subprocess.run(["hcopy", "-r", f"{vol}:{MADE_NAME}", dest],
                             env=env, capture_output=True)
        subprocess.run(["humount"], env=env, capture_output=True)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    if got.returncode != 0 or not os.path.exists(dest):
        print("cptcrypt: the application wrote no archive — look at the "
              "screenshots (a stray Return in Standard File saves into "
              "whatever folder it walked into)")
        return 1
    subjects = ([{"name": n, "data": d.hex()} for n, d in PROBES]
                if args.probe else
                [{"name": MAKE_NAME, "data": MAKE_DATA.hex(),
                  "rsrc": MAKE_RSRC.hex()}])
    meta = {"made_by": "Compact Pro 1.51 on System 6.0.8 under Mini vMac",
            "registered_as": args.register,
            "password": None if args.plain else args.password,
            "note": args.note,
            "probe": bool(args.probe),
            "bytes": os.path.getsize(dest),
            "subjects": subjects}
    with open(os.path.join(args.outdir, "made.json"), "w") as f:
        json.dump(meta, f, indent=1, sort_keys=True)
    print(f"cptcrypt: {os.path.getsize(dest)} bytes -> {dest}")
    print(f"cptcrypt: what went into it -> "
          f"{os.path.join(args.outdir, 'made.json')}")
    return 0


def shutdown(mac, shot):
    """Special > Shut Down, and NOT a kill.

    Mini vMac writes the guest's sectors through buffered stdio and
    flushes on eject, so killing the emulator leaves a volume whose
    files are partly written. arcmac.py and spacesaver.py pick this
    menu for the same reason."""
    ox, oy = mac.origin()
    mac._xdo("mousemove", str(ox + SPECIAL_X), str(oy + 8))
    time.sleep(0.3)
    mac._xdo("mousedown", "1")
    time.sleep(1.0)
    mac._xdo("mousemove", str(ox + SPECIAL_X + 25), str(oy + SHUT_DOWN_Y))
    time.sleep(0.4)
    mac._xdo("mouseup", "1")
    time.sleep(20.0)
    shot(mac, "z-shutdown.png")


def read_volume(image, outdir, skip, invisible=True):
    """Every file Compact Pro left at the boot volume's ROOT, as MacBinary.

    `hdir -a` and an `F` as well as an `f` on the line test, since
    2026-09-22, for the reasons `cptsegment.read_volume` states in full —
    the two walks are the same walk written twice, and `walkprobe.py`
    grades both. Root-only is deliberate and recorded there as well: this
    is a boot volume, and its `System Folder` is not output.
    """
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    got, dropped = {}, []
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
        vb = vol.encode("mac-roman") + b":"
        listing = subprocess.run([b"hdir"] + ([b"-a"] if invisible else [])
                                 + [vb], check=True, env=env,
                                 capture_output=True).stdout
        for line in listing.split(b"\n"):
            if line[:1] not in (b"f", b"F"):   # a directory, or a blank line
                continue
            m = LISTING_DATE_B.search(line)
            if not m:
                continue
            raw = m.group(1)
            name = raw.decode("mac-roman", "replace")
            if invisible and name in FINDER_OWN:
                dropped.append(name)
                continue
            if name in skip:
                continue
            dest = os.path.join(outdir, name.replace("/", "_"))
            subprocess.run([b"hcopy", b"-m", vb + raw,
                            dest.encode() + b".bin"],
                           check=True, env=env, capture_output=True)
            got[name] = dest + ".bin"
        subprocess.run(["humount"], env=env, capture_output=True)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
    # What `-a` cost on THIS harness's own volume, printed rather than
    # assumed: the filter is only right if what it drops is the Finder's.
    print("%s: -a surfaced and FINDER_OWN dropped: %s"
          % ('cptcrypt', ", ".join(sorted(dropped)) or "nothing"))
    return got


def macbinary_forks(path):
    """Data and resource fork out of a MacBinary file hcopy wrote."""
    b = open(path, "rb").read()
    dlen = int.from_bytes(b[83:87], "big")
    rlen = int.from_bytes(b[87:91], "big")
    doff = 128
    roff = doff + ((dlen + 127) // 128) * 128
    return b[doff:doff + dlen], b[roff:roff + rlen]


def set_note(mac, shot, args):
    """Archive > Note... — type the archive's comment into the
    application that writes them.

    The comment is a property of the ARCHIVE, not of any file in it, and
    this is where Compact Pro puts it. Whatever is typed here comes back
    out of the index as `commentlen` bytes (src/fmt_cpt.c), so a run of
    this is the only evidence available that the two are the same thing.
    """
    pull_down(mac, MENUS["Archive"])
    shot(mac, "n1-archive-menu.png")
    release(mac, MENUS["Archive"] + 25, NOTE_Y)
    time.sleep(2.5)
    shot(mac, "n2-note-dialog.png")
    for i, line in enumerate(args.note.split("\\n")):
        if i:
            mac.key("Return")          # a line break IN the note
        mac._xdo("type", "--delay", "120", line)
        time.sleep(0.8)
    time.sleep(1.0)
    shot(mac, "n3-note-typed.png")
    mac.click(*NOTE_OK)
    time.sleep(2.5)
    shot(mac, "n4-note-set.png")


def phase_make(mac, shot, args):
    """Have Compact Pro WRITE an encrypted archive.

    A registered copy can, and this is the specimen the format has never
    had here: an encrypted `.cpt` from the only implementation that
    writes one. Registration leaves an untitled archive window open, so
    there is no File > New to drive, and it also moves the Add dialog's
    Encrypt checkbox into view — the routine at 0x4864 patches DITL 312,
    which is why the coordinates above are measured off a REGISTERED
    copy's screenshot and not off the resource.

    The password is not asked for at Add time. Compact Pro takes it when
    it writes the archive, and asks twice — once for it and once to
    verify — so nothing may be typed blind before then: a stray Return
    lands in Standard File and walks into a folder, which is how the
    first attempt saved nothing anywhere.
    """
    mac.command_key("g")
    time.sleep(3.0)
    shot(mac, "m1-add-dialog.png")
    if not args.plain:
        mac.click(*ADD_ENCRYPT)
    time.sleep(1.0)
    shot(mac, "m2-encrypt-checked.png")
    if args.probe:
        # One click per subject, NOT Add All: the volume also holds the
        # application and the System Folder, and Add All took all nine
        # (which is a long compress and the wrong experiment).
        # Alphabetical, so rows 3, 4 and 5 are P100, P103, P96.
        for row in ADD_PROBE_ROWS:
            mac.click(ADD_SUBJECT_ROW[0], row)
            time.sleep(0.8)
            mac.click(*ADD_BUTTON)
            time.sleep(2.5)
    else:
        mac.click(*ADD_SUBJECT_ROW)
        time.sleep(1.0)
        mac.click(*ADD_BUTTON)
        time.sleep(3.0)
    shot(mac, "m3-added.png")
    mac.click(*ADD_DONE)
    time.sleep(2.5)
    shot(mac, "m4-done.png")

    if args.note:
        set_note(mac, shot, args)

    mac.command_key("s")
    time.sleep(3.0)
    shot(mac, "m5-save-dialog.png")
    mac._xdo("type", "--delay", "150", MADE_NAME)
    time.sleep(1.0)
    shot(mac, "m6-named.png")
    mac.key("Return")
    time.sleep(6.0)
    shot(mac, "m7-password-asked.png")
    # An unencrypted archive is never asked for a password: with --plain
    # the Save has already written it, and typing into the window that
    # is actually there would edit the archive rather than confirm it.
    if not args.plain:
        for i in range(2):                # type it, then verify it
            for ch in args.password:
                mac.key(ch)
            time.sleep(1.0)
            shot(mac, "m8-password-%d.png" % (i + 1))
            mac.key("Return")
            time.sleep(6.0)
    time.sleep(10.0)
    shot(mac, "m9-written.png")


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
    ap.add_argument("--register", metavar="NAME:CODE",
                    help="type a registration into the shareware notice "
                         "before doing anything else. Macintosh Garden "
                         "publishes one for 1.51: 'Registered:35427117'")
    ap.add_argument("--plain", action="store_true",
                    help="write the archive UNENCRYPTED. Isolates the "
                         "container from the cipher: if Compact Pro cannot "
                         "read this one either, the cipher is not what is "
                         "wrong")
    ap.add_argument("--fixture",
                    help="extract a CORPUS archive instead of a generated "
                         "one, to see what the application does with a real "
                         "one on this path (implies --plain)")
    ap.add_argument("--make", action="store_true",
                    help="have Compact Pro WRITE an encrypted archive, "
                         "rather than read one — the specimen this format "
                         "has never had")
    ap.add_argument("--probe", action="store_true",
                    help="with --make: compress three data-fork-only "
                         "subjects of 96, 100 and 103 bytes instead of one "
                         "two-fork file, which is what separates the "
                         "padding rules")
    ap.add_argument("--encrypt-at", metavar="X,Y",
                    help="where the Add dialog's Encrypt checkbox is, "
                         "measured off m1-add-dialog.png from a run "
                         "without this")
    ap.add_argument("--note", metavar="TEXT",
                    help="with --make: type TEXT into Archive > Note..., "
                         "which is Compact Pro's name for the archive "
                         "comment, before the archive is saved. A literal "
                         "\\n is a line break in the note, which the Mac "
                         "stores as CR")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    if args.fixture:
        args.plain = True
    os.makedirs(args.outdir, exist_ok=True)

    def shot(mac, name):
        p = os.path.join(args.outdir, name)
        mac.shot(p)
        print("  " + name)

    workdir = tempfile.mkdtemp(prefix="cptcrypt-")
    try:
        img = boot_image(workdir, None if args.plain else args.password,
                         fixture=args.fixture, make=args.make,
                         probe=args.probe)
        mac = Mac(img, args.emu, workdir)
        try:
            launch(mac, shot, args)
            if args.make:
                phase_make(mac, shot, args)
                mac.command_key("q")
                time.sleep(6.0)
                shot(mac, "m10-quit.png")
                shutdown(mac, shot)
                mac.close()
                return save_specimen(workdir, args)
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
            # "Select Destination Folder..." — Return means Open, which
            # walks INTO whatever folder is selected (it descended into
            # StuffIt Expander's the first time and photographed a
            # working machine doing nothing). The button that accepts
            # the folder shown is Extract, and it has a keyboard
            # equivalent.
            mac.command_key("e")
            time.sleep(4.0)
            shot(mac, "8-password-prompt.png")
            if not args.plain:
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
            # SHUT DOWN, do not just close the emulator. Mini vMac
            # writes the guest's sectors through buffered stdio and
            # flushes on eject; a killed emulator leaves a volume whose
            # forks are PARTLY written — which here looked like Compact
            # Pro corrupting every resource fork 48 bytes in, and cost a
            # long detour into a cipher that was not what was wrong.
            # arcmac.py and spacesaver.py have picked this menu for the
            # same reason.
            shutdown(mac, shot)
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
            # DATA forks are compared strictly. RESOURCE forks are not,
            # and the reason is not Compact Pro: the Mac opens an
            # extracted file's resource fork to draw its icon, and the
            # Resource Manager writes the live fields of the map back —
            # a corpus archive extracted by Compact Pro comes back with
            # the same 22 bytes changed, and these subjects' forks are
            # arbitrary bytes, so it rewrites more. What makes the
            # comparison unnecessary is that Compact Pro checks the
            # entry's CRC-32 over BOTH decrypted forks before it writes
            # anything: a resource fork that decrypted wrongly would
            # have produced "the password supplied is incorrect or the
            # archive is damaged" and no file at all.
            if gd != data:
                print(f"    {name:14s} DATA FORK DIFFERS "
                      f"({len(gd)} vs {len(data)})")
                bad += 1
            else:
                note = "" if gr == rsrc else "  (rsrc restamped by the Mac)"
                print(f"    {name:14s} data {len(gd)}/{len(data)} OK"
                      f"   rsrc {len(gr)}/{len(rsrc)}{note}")
        for name in sorted(set(files) - set(want)):
            print(f"    (also on the volume: {name})")
        if bad:
            print("cptcrypt: Compact Pro did not reproduce the input. If it "
                  "put up 'cannot validate or extract encrypted files', the "
                  "copy is unregistered and this says nothing about the "
                  "cipher; look at 7-extract-dialog.png first.")
            return 1
        print("cptcrypt: Compact Pro 1.51 extracted every entry, and its "
              "own CRC over both decrypted forks passed — the cipher is "
              "confirmed by the application that wrote the format.")
        return 0
    finally:
        if args.keep:
            print(f"cptcrypt: workdir kept at {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
