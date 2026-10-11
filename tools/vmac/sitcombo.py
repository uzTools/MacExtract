#!/usr/bin/env python3
"""sitcombo.py — ask StuffIt Deluxe 2.0.1 for the combinations nobody had.

Every specimen `sitopt.py` made was one subject per module, chosen
here, at the defaults. A wild archive can only ever add a combination
nobody here asked for — so this asks for them, from the same writer on
the same registered image:

    tools/vmac/sitcombo.py --ps-explore      Photoshop's New dialog and
                                             menus, photographed
    tools/vmac/sitcombo.py --psnew NAME WxH [--gray] [--mode M]
                           [--zoom 2] [--canvas X,Y --margin N]
                                             a document Photoshop 1.0.7
                                             draws and saves
    tools/vmac/sitcombo.py --paintnew NAME   a MacPaint 2.0 painting
    tools/vmac/sitcombo.py --cdocs           coloured documents in
                                             Photoshop's layout, no boot
    tools/vmac/sitcombo.py --run SET         one boot of one script set:
        a  Photoshop 1, Text 1, four Optimizers over a folder
        b  JPEG Lossy and Photoshop 1 over every --psnew document
        c  every Optimizer under DES and NewDE
        d  the ciphers' edges, with a plain control
        e  PassLock, NewDEx and DESex over optimized entries (the GUI)
        k  JPEG Lossy over --cdocs
        p  MacPaint 1 over --paintnew Painting2, every method
        q  JPEG Lossy at --quality Q[,Q...], the first the module takes

It reuses `sitopt.py`'s images, sessions and readers, and adds one thing
that file does not have: a CLOSED-LOOP script runner. A cipher's
password dialogs are recognised on the screen and answered when they
are up, rather than typed blind on a timer, and the run ends when the
Finder's menu bar comes back — the scripts all end in `Quit`.

What this CANNOT see:

- **anything about a document Photoshop did not write.** The subjects
  are drawn and saved by Photoshop 1.0.7 itself (`--psnew`), or are the
  MacPaint/text subjects `sitopt.py` already uses.
- **a dialog it has no reference crop for.** One it does not know is
  answered with Return after the screen has stood still for a minute,
  and photographed first, so the shot is the finding.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sitopt as S                                      # noqa: E402
from arcmac import macbinary, hfs                       # noqa: E402

VOL = S.VOL
SPEC = os.path.join(S.R.VMAC_HOME, "specimens", "sitcombo")
REF = os.path.join(S.SPECIMENS, "psdes1")


def crop_sig(png, box):
    """A thresholded crop's md5: (w, h, x, y)."""
    w, h, x, y = box
    out = subprocess.run(["convert", png, "-crop", "%dx%d+%d+%d" % box,
                          "+repage", "-threshold", "50%", "-depth", "8",
                          "gray:-"], capture_output=True)
    return hashlib.md5(out.stdout).hexdigest()


# Off `specimens/sitopt/psdes1`: the Finder's menu bar, and the two
# password dialogs 2.0.1 puts up for `… with fast des` / `newde` —
# "You are about to secure this archive…" and "Please re-enter…".
# One strip tells both apart, and nothing typed into the field reaches
# it — measured on the scripted prompts and on the Stuff dialog's
# (psex2), whose first prompt differs from the script's higher up.
MENUBAR = (280, 19, 20, 0)
PW2 = (380, 14, 60, 143)


def refs():
    return {
        "finder": crop_sig(os.path.join(REF, "01-desktop.png"), MENUBAR),
        "pw1": crop_sig(os.path.join(REF, "06-running1.png"), PW2),
        "pw2": crop_sig(os.path.join(REF, "07-running2.png"), PW2),
    }


def put(img, items, folders=()):
    """hcopy MacBinary files onto an image: items are (path, folder)."""
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    try:
        hfs(env, "hmount", img)
        for f in folders:
            subprocess.run(["hmkdir", (VOL + ":" + f).encode("mac_roman")],
                           capture_output=True, env=env)
        for p, dest in items:
            got = hfs(env, "hcopy", "-m", p,
                      (VOL + ":" + dest).encode("mac_roman"))
            if got.returncode != 0:
                raise SystemExit("sitcombo: hcopy %s failed" % p)
        hfs(env, "humount")
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)


def take(img, names, outdir):
    for n in names:
        S.read_one(img, n, outdir)


def drive(s, password, limit, stall=60.0):
    """Answer password dialogs until the Finder is back. Returns a log."""
    r = refs()
    tmp = os.path.join(s.work, "poll.png")
    log = []
    t0 = time.time()
    last, still = None, time.time()
    while time.time() - t0 < limit:
        time.sleep(4.0)
        if not s.mac.dpy.screenshot(tmp):
            continue
        if crop_sig(tmp, MENUBAR) == r["finder"]:
            log.append("finder back at %ds" % (time.time() - t0))
            s.shot("finder-back", wait=1.0)
            return log
        which = None
        sig2 = crop_sig(tmp, PW2)
        if sig2 == r["pw1"]:
            which = "pw1"
        elif sig2 == r["pw2"]:
            which = "pw2"
        if which:
            s.shot(which, wait=0.5)
            s.mac._xdo("type", "--delay", "140", password)
            s.mac.key("Return")
            log.append("%s answered at %ds" % (which, time.time() - t0))
            time.sleep(3.0)
            last, still = None, time.time()
            continue
        sig = hashlib.md5(open(tmp, "rb").read()).hexdigest()
        if sig != last:
            last, still = sig, time.time()
        elif time.time() - still > stall:
            s.shot("stalled", wait=0.5)
            s.mac.key("Return")
            log.append("stalled; Return at %ds" % (time.time() - t0))
            still = time.time()
    log.append("TIMEOUT after %ds" % limit)
    s.shot("timeout", wait=0.5)
    return log


def nsargs(**kw):
    d = dict(launch_wait=40.0, emu="mv-4M")
    d.update(kw)
    return types.SimpleNamespace(**d)


# ------------------------------------------------------------------
# Photoshop: what its New dialog and Mode menu offer
# ------------------------------------------------------------------

PS_MODE_X = 133
PS_IMAGE_X = 190
PS_FILE_X = 47
PS_GRAY = (107, 211)            # off psdoc2/02-new-dialog.png
PS_RGB = (107, 228)
PS_CANCEL = (393, 118)
PS_BLEND = (41, 132)            # the toolbox's gradient tool


def ps_launch(s):
    s.boot()
    s.mac.click(*S.BOOT_ICON, double=True)
    time.sleep(14)
    s.mac.click(*S.PS_ICON)
    time.sleep(3)
    s.mac.command_key("o")
    s.shot("launched", wait=90.0)


# Off explore1: the canvas's top-left on screen at 1:1, how much of it
# the window shows, and the Mode menu's items (an RGB document enables
# all eight).
CANVAS = (63, 39)
VISIBLE = (254, 240)
PTR_FIX = (3, 6)
M = 12          # keep off the window's edges: a stroke that starts on
                # the title bar drags the window instead (ps-PSGray, 1st)
PS_MODES = {"bitmap": 27, "gray": 43, "indexed": 59, "rgb": 75,
            "cmyk": 91, "hsl": 107, "hsb": 123, "multichannel": 139}


def ps_draw(s, w, h, which, zoom=1, canvas=None, margin=None):
    """A blend across the canvas, then a pencil grid over part of it:
    smooth content and hard edges in one image."""
    ox, oy = s.mac.origin()
    # A document smaller than the window is CENTRED in it, on grey
    # (ps-PSSmall, first), so --canvas gives its top-left.
    cx, cy = ox + (canvas or CANVAS)[0], oy + (canvas or CANVAS)[1]
    # ...and the pointer lands (3, 6) up and left of where it is sent:
    # PSGray's pencil rows, sent to canvas y 12, 18 ..., are document
    # rows 6, 12 ..., and its columns 3 short. Harmless at 256x256 and
    # fatal at 21x13, where every stroke started above the canvas.
    cx, cy = cx + PTR_FIX[0], cy + PTR_FIX[1]
    # A document wider than the screen opens at 1:2 (ps-PSWide, first),
    # so the canvas on screen is half its size.
    vw, vh = min(w // zoom, VISIBLE[0]), min(h // zoom, VISIBLE[1])
    m = M if min(vw, vh) >= 4 * M else 3
    if margin is not None:
        m = margin
    x = s.mac._xdo
    if "grad" in which:
        s.mac.click(*PS_BLEND)
        time.sleep(1.5)
        S.stroke(x, cx, cy, [(m, m), (vw - m, vh - m)])
        s.shot("blended", wait=15.0)
    if "grid" in which:
        s.mac.click(*S.PS_PENCIL)
        time.sleep(1.5)
        for row in range(m, max(vh // 2, m + 1), 6):
            S.stroke(x, cx, cy, [(m, row), (vw - m, row)])
        for col in range(vw // 2, vw - m, 12):
            S.stroke(x, cx, cy, [(col, m), (col, vh - m)])
        S.stroke(x, cx, cy, [(m, vh - m), (vw - m, m)])
        s.shot("gridded", wait=4.0)


def ps_new(args):
    name = args.psnew[0]
    w, h = (int(v) for v in args.psnew[1].lower().split("x"))
    img = os.path.join(S.WORK, "run-combo-%s.hfv" % args.tag)
    shutil.copyfile(S.PS_IMAGE, img)
    outdir = os.path.join(SPEC, args.tag)
    s = S.Session(img, [], outdir, mem="mv-4M")
    try:
        ps_launch(s)
        s.mac.command_key("n")
        time.sleep(8)
        s.mac._xdo("type", "--delay", "140", str(w))
        s.mac.key("Tab")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "140", str(h))
        s.mac.click(*(PS_GRAY if args.gray else PS_RGB))
        s.shot("new-dialog", wait=3.0)
        s.mac.key("Return")
        s.shot("new-doc", wait=20.0)
        ps_draw(s, w, h, args.drawing, args.zoom,
                tuple(int(v) for v in args.canvas.split(","))
                if args.canvas else None, args.margin)
        if args.mode:
            s.menu(PS_MODE_X, PS_MODES[args.mode], "mode-" + args.mode)
            s.shot("converting", wait=10.0)
            if args.mode in ("indexed", "bitmap"):
                s.mac.key("Return")         # its options dialog, defaults
            s.shot("converted", wait=25.0)
        s.mac.command_key("s")
        time.sleep(12)
        s.mac._xdo("type", "--delay", "140", name)
        s.shot("save-named", wait=3.0)
        s.mac.key("Return")
        s.shot("saved", wait=30.0)
        s.mac.command_key("q")
        s.shot("quit", wait=25.0)
        s.menu(S.SPECIAL_X, S.SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        S.read_one(os.path.join(s.work, "boot.hfv"), name, outdir)
    finally:
        time.sleep(3)
        s.close()
    got = os.path.join(outdir, name + ".bin")
    if os.path.exists(got):
        _n, t, c, data, rsrc = mb_info(got)
        print("sitcombo: %s %s/%s data %d rsrc %d" % (name, t, c, len(data),
                                                      len(rsrc)))
    return 0



def ps_explore(args):
    img = os.path.join(S.WORK, "run-psexplore.hfv")
    shutil.copyfile(S.PS_IMAGE, img)
    outdir = os.path.join(SPEC, args.tag)
    s = S.Session(img, [], outdir, mem="mv-4M")
    try:
        ps_launch(s)
        s.mac.command_key("n")
        s.shot("new-dialog", wait=8.0)
        s.mac._xdo("type", "--delay", "140", "203")
        s.mac.key("Tab")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "140", "77")
        s.mac.click(*PS_GRAY)
        s.shot("new-gray", wait=3.0)
        s.mac.key("Return")
        s.shot("new-doc", wait=20.0)
        for x, tag in ((PS_FILE_X, "file"), (70, "edit"),
                       (PS_MODE_X, "mode"), (PS_IMAGE_X, "image"),
                       (245, "select"), (298, "window")):
            s.peek(x, "menu-" + tag)
        s.mac.command_key("q")
        s.shot("quit", wait=15.0)
        s.mac.key("Tab")            # "Don't Save"? photographed, not assumed
        s.shot("quit-2", wait=8.0)
    finally:
        time.sleep(3)
        s.close()
    return 0


# ------------------------------------------------------------------
# Subjects
# ------------------------------------------------------------------

def mb_info(path):
    """(name, type, creator, data, rsrc) of a MacBinary file."""
    d = open(path, "rb").read()
    name = d[2:2 + d[1]].decode("mac_roman")
    data, rsrc = S.forks(path)
    return name, d[65:69].decode("mac_roman"), d[69:73].decode("mac_roman"), \
        data, rsrc


def renamed(path, name, work):
    _n, t, c, data, rsrc = mb_info(path)
    out = os.path.join(work, name + ".bin")
    open(out, "wb").write(macbinary(name, t, c, data, rsrc))
    return out


def textish(n, seed):
    """`n` bytes of deterministic, compressible-but-not-trivially text."""
    words = [b"stuff", b"archive", b"optimizer", b"fork", b"resource",
             b"Macintosh", b"1990", b"cipher", b"block", b"key", b"\r"]
    out, x = bytearray(), seed
    while len(out) < n:
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        out += words[(x >> 16) % len(words)] + b" "
    return bytes(out[:n])


def gen(work, name, data, rsrc=b"", t="TEXT", c="ttxt"):
    out = os.path.join(work, name.replace(":", "_") + ".bin")
    open(out, "wb").write(macbinary(name, t, c, data, rsrc))
    return out


PSDOC = os.path.join(S.SPECIMENS, "psdoc", "PSDoc.bin")
PSDOC2 = os.path.join(S.SPECIMENS, "psdoc2", "PSDoc2.bin")
PAINTING = os.path.join(S.SPECIMENS, "paint2", "Painting.bin")


def sound2(work):
    pcm = bytes((i * 7) % 256 for i in range(8192))
    return gen(work, "Sound2", pcm, S.one_resource("INFO", 1000, bytes(32)),
               "FSSD", "Sd2a")


def psnew_docs():
    """Every document --psnew has written: [(name, path)]."""
    out = []
    if os.path.isdir(SPEC):
        for d in sorted(os.listdir(SPEC)):
            if d.startswith("ps-"):
                n = d[3:]
                p = os.path.join(SPEC, d, n + ".bin")
                if os.path.exists(p):
                    out.append((n, p))
    return out


# ------------------------------------------------------------------
# The script sets, one boot each
# ------------------------------------------------------------------

def L(*lines):
    return list(lines)


def stuff_one(archive, item, how, opt151=False):
    return L('New Archive "{Startup}%s"%s' % (archive,
                                             " 1.5.1" if opt151 else ""),
             'Stuff "{Startup}%s" with %s' % (item, how),
             "Close")


def unstuff_to(folder, archive):
    return L('Destination "{Startup}%s:"' % folder,
             'Open Archive "{Startup}%s"' % archive,
             'UnStuff "*"',
             "Close")


def set_a(work, args=None):
    """Photoshop 1 on Photoshop's own documents, every method; Text 1
    under Best Guess and in a 1.5.1 archive; four Optimizers at once
    over a folder; and 2.0.1's own restore of three of them."""
    items = [(PSDOC, ""), (PSDOC2, ""), (sound2(work), "")]
    mixed = [renamed(PAINTING, "MPaint", work),
             gen(work, "MSubject", S.SUBJECT_DATA, S.make_rsrc()),
             renamed(PSDOC2, "MPhoto", work),
             renamed(sound2(work), "MSound", work),
             gen(work, "MPlain", textish(3000, 7))]
    items += [(m, "Mixed:") for m in mixed]
    sc = ['Enable Optimizer "Photoshop 1"']
    sc += stuff_one("P1Zig.sit", "PSDoc", "fast")
    for how in ("fast", "better", "faster", "optimal", "none", "guess"):
        sc += stuff_one("P1%s.sit" % how.capitalize(), "PSDoc2", how)
    sc += stuff_one("P1Old.sit", "PSDoc2", "fast", opt151=True)
    sc += ['Disable Optimizer "Photoshop 1"', 'Enable Optimizer "Text 1"']
    sc += stuff_one("TGuess.sit", "Subject", "guess")
    sc += stuff_one("TOld.sit", "Subject", "fast", opt151=True)
    sc += ['Enable Optimizer "MacPaint 1"', 'Enable Optimizer "Sound 1"',
           'Enable Optimizer "Photoshop 1"']
    sc += stuff_one("Mixed.sit", "Mixed", "fast")
    sc += ['Disable Optimizer "MacPaint 1"', 'Disable Optimizer "Sound 1"',
           'Disable Optimizer "Photoshop 1"', 'Disable Optimizer "Text 1"']
    sc += unstuff_to("OutF", "P1Fast.sit")
    sc += unstuff_to("OutZ", "P1Zig.sit")
    sc += unstuff_to("OutM", "Mixed.sit")
    names = ["P1Zig.sit"] + ["P1%s.sit" % h.capitalize() for h in
                             ("fast", "better", "faster", "optimal", "none",
                              "guess")]
    names += ["P1Old.sit", "TGuess.sit", "TOld.sit", "Mixed.sit",
              "OutF:PSDoc2", "OutZ:PSDoc"]
    names += ["OutM:Mixed:" + m for m in ("MPaint", "MSubject", "MPhoto",
                                          "MSound", "MPlain")]
    return items, ["Mixed", "OutF", "OutZ", "OutM"], sc, names


CIPHER_OPTS = (("MacPaint 1", "Paint", "Painting"),
               ("Text 1", "Text", "Subject"),
               ("Photoshop 1", "Ps1", "PSDoc2"),
               ("Photoshop/JPEG Lossy", "Jpg", "PSDoc2"),
               ("Sound 1", "Snd", "Sound2"))


def set_c(work, args=None):
    """Every Optimizer under each of the two built-in ciphers."""
    items = [(PSDOC2, ""), (sound2(work), "")]
    sc, names = [], []
    for mod, short, subj in CIPHER_OPTS:
        sc.append('Enable Optimizer "%s"' % mod)
        for word, pre in (("des", "D"), ("newde", "N")):
            sc += stuff_one("%s%s.sit" % (pre, short), subj, "fast " + word)
            names.append("%s%s.sit" % (pre, short))
        sc.append('Disable Optimizer "%s"' % mod)
    return items, [], sc, names


BIG = (("Big1", "fast"), ("Big2", "better"), ("Big3", "faster"),
       ("Big4", "optimal"), ("Big5", "none"), ("Big6", "guess"))


def set_d(work, args=None):
    """The ciphers' edges: empty forks, a fork of exactly eight blocks,
    every method under each cipher, a folder, several entries per
    archive — and a plain control of the same, in the same boot."""
    items = [(gen(work, "Empty", b""), ""),
             (gen(work, "Exact8", textish(64, 3)), ""),
             (gen(work, "RsrcOnly", b"", S.make_rsrc()), "")]
    for n, (name, _how) in enumerate(BIG):
        items.append((gen(work, name, textish(40000 + 777 * n, 11 + n),
                          S.make_rsrc()), ""))
    items.append((gen(work, "First", b"the first file in the folder\r" * 4,
                      S.make_rsrc()), "Papers:"))
    items.append((gen(work, "Second", b"and the second\r" * 7), "Papers:"))
    sc, names = [], []
    for word, arch in (("des", "DMix.sit"), ("newde", "NMix.sit"),
                       ("", "PMix.sit")):
        sec = (" " + word) if word else ""
        sc.append('New Archive "{Startup}%s"' % arch)
        sc.append('Stuff "{Startup}Empty" with fast%s' % sec)
        sc.append('Stuff "{Startup}Exact8" with none%s' % sec)
        sc.append('Stuff "{Startup}RsrcOnly" with fast%s' % sec)
        for name, how in BIG:
            sc.append('Stuff "{Startup}%s" with %s%s' % (name, how, sec))
        sc.append('Stuff "{Startup}Papers" with fast%s' % sec)
        sc.append("Close")
        names.append(arch)
    return items, ["Papers"], sc, names


def set_b(work, args=None):
    """JPEG Lossy and Photoshop 1 on every document --psnew wrote, with
    2.0.1's own restore of each JPEG one."""
    docs = psnew_docs()
    if not docs:
        raise SystemExit("sitcombo: no --psnew documents yet")
    items = [(p, "") for _n, p in docs]
    sc, names, folders = [], [], []
    sc.append('Enable Optimizer "Photoshop/JPEG Lossy"')
    for n, _p in docs:
        sc += stuff_one("J%s.sit" % n, n, "fast")
        names.append("J%s.sit" % n)
    sc.append('Disable Optimizer "Photoshop/JPEG Lossy"')
    sc.append('Enable Optimizer "Photoshop 1"')
    for n, _p in docs:
        sc += stuff_one("P%s.sit" % n, n, "fast")
        names.append("P%s.sit" % n)
    sc.append('Disable Optimizer "Photoshop 1"')
    for n, _p in docs:
        sc += unstuff_to("O" + n, "J%s.sit" % n)
        folders.append("O" + n)
        names.append("O%s:%s" % (n, n))
    return items, folders, sc, names


def set_q(work, args):
    """JPEG Lossy at a quality far from the recommended 20-30, set in the
    module's own dialog before the script runs. The archive is named
    for the run; the Q the module took is in the log and the TIFF."""
    items = [(PSDOC2, "")]
    sc = ['Enable Optimizer "Photoshop/JPEG Lossy"']
    sc += stuff_one("Q.sit", "PSDoc2", "fast")
    sc += ['Disable Optimizer "Photoshop/JPEG Lossy"']
    sc += unstuff_to("OutQ", "Q.sit")
    return items, ["OutQ"], sc, ["Q.sit", "OutQ:PSDoc2"]


# The module's own dialog, by its title line (ps-jpeg3/08): it stays up
# when OK is clicked on a Q it will not take — Q=1 was refused with no
# alert at all, and the script's name then went into the Q field
# (2026-10-11, the first --run q).
JPEG_DLG = (360, 14, 76, 59)


def pre_q(s, args):
    """Try each Q in --quality in turn until the module accepts one."""
    ref = crop_sig(os.path.join(S.SPECIMENS, "ps-jpeg3",
                                "08-module-dialog.png"), JPEG_DLG)
    tmp = os.path.join(s.work, "q.png")
    s.menu(S.EDIT_X, S.EDIT_SWITCH_Y, "expert-menus")
    s.menu(S.OPTIONS_X, S.OPT_OPTIMIZERS_Y, "menu-optimizers")
    s.shot("opt-dialog", wait=8.0)
    s.mac.click(*S.OPT_JPEG_ROW)
    s.shot("module-dialog", wait=6.0)
    first = True
    for q in args.quality.split(","):
        for _ in range(5):
            s.mac.key("BackSpace")
            time.sleep(0.2)
        s.mac._xdo("type", "--delay", "160", q)
        if first:
            s.mac.click(*S.JPEG_Q_PROMPT)       # stop it asking per file
            first = False
        s.shot("q%s-typed" % q, wait=2.0)
        s.mac.click(*S.JPEG_Q_OK)
        time.sleep(5.0)
        s.mac.dpy.screenshot(tmp)
        if crop_sig(tmp, JPEG_DLG) == ref:
            print("sitcombo: the module REFUSED Q=%s" % q)
            s.shot("q%s-refused" % q, wait=0.5)
            continue
        print("sitcombo: the module took Q=%s" % q)
        s.shot("q%s-taken" % q, wait=0.5)
        s.mac.click(*S.OPT_OK)
        s.shot("opt-closed", wait=5.0)
        return
    raise SystemExit("sitcombo: no Q in %s was taken" % args.quality)


def answer(s, password, limit=400.0, settle=30.0):
    """Answer password prompts until none has been up for `settle`
    seconds and the screen has stopped changing. Returns a log."""
    r = refs()
    tmp = os.path.join(s.work, "poll.png")
    log, t0 = [], time.time()
    last, still = None, time.time()
    while time.time() - t0 < limit:
        time.sleep(3.0)
        if not s.mac.dpy.screenshot(tmp):
            continue
        sig2 = crop_sig(tmp, PW2)
        which = {r["pw1"]: "pw1", r["pw2"]: "pw2"}.get(sig2)
        if which:
            s.shot(which, wait=0.5)
            s.mac._xdo("type", "--delay", "140", password)
            s.mac.key("Return")
            log.append("%s answered at %ds" % (which, time.time() - t0))
            time.sleep(3.0)
            last, still = None, time.time()
            continue
        sig = hashlib.md5(open(tmp, "rb").read()).hexdigest()
        if sig != last:
            last, still = sig, time.time()
        elif time.time() - still > settle:
            return log
    log.append("TIMEOUT")
    return log


# Custom Encryption's list, measured in psex2: PassLock, NewDEx, DESex.
GUI_ENC = (("PassLock", 76), ("NewDEx", 92), ("DESex", 108))
GUI_SUBJECTS = ("Painting", "PSDoc2")


def set_e(work, args):
    """The optional disk's two encryptor modules and PassLock, each over
    an entry MacPaint 1 optimized and one Photoshop 1 optimized. The
    modules are reachable only through the Stuff dialog; the Optimizers
    are enabled by a script that does not quit."""
    items = [(PSDOC2, "")]
    encdir = S.opt_encryptors(work)
    for mod in ("NewDEx", "DESex"):
        mb = os.path.join(work, mod + ".bin")
        open(mb, "wb").write(macbinary(mod, "SITe", "SIT!", b"", open(
            os.path.join(encdir, mod + ".rsrc"), "rb").read()))
        items.append((mb, "System Folder:Encryptors:"))
    sc = ['Enable Optimizer "MacPaint 1"', 'Enable Optimizer "Photoshop 1"']
    names = ["G%s.sit" % m for m, _y in GUI_ENC]
    return items, [], sc, names


def gui_e(s, args, log):
    time.sleep(40)                      # the enabling script, no Quit
    s.shot("enabled", wait=1.0)
    s.menu(S.EDIT_X, S.EDIT_SWITCH_Y, "expert-menus")
    for mod, y in GUI_ENC:
        s.menu(S.OPTIONS_X, S.OPT_CUSTOM_ENC_Y, "menu-enc-" + mod)
        s.shot("enc-list-" + mod, wait=8.0)
        s.mac.click(S.ENC_PASSLOCK[0], y)
        s.shot("enc-picked-" + mod, wait=3.0)
        s.mac.click(*S.ENC_OK)
        s.shot("enc-armed-" + mod, wait=5.0)
        s.mac.command_key("n")
        s.shot("new-" + mod, wait=10.0)
        s.mac._xdo("type", "--delay", "140", "G" + mod)
        s.mac.key("Return")
        s.shot("made-" + mod, wait=12.0)
        for subj in GUI_SUBJECTS:
            s.mac.command_key("s")
            s.shot("stuff-%s-%s" % (mod, subj), wait=10.0)
            s.mac._xdo("type", "--delay", "140", subj)
            s.shot("picked-%s-%s" % (mod, subj), wait=3.0)
            s.mac.key("Return")
            for line in answer(s, args.password):
                log.append("%s/%s: %s" % (mod, subj, line))
            s.shot("stuffed-%s-%s" % (mod, subj), wait=1.0)
        s.mac.command_key("w")
        s.shot("closed-" + mod, wait=8.0)
    s.mac.command_key("q")
    s.shot("quit", wait=20.0)



def paint_new(args):
    """A second MacPaint 2.0 document, denser than `Painting`: rows of
    strokes over most of the visible page, so most PackBits rows carry
    ink rather than repeat white."""
    name = args.paintnew
    img = os.path.join(S.WORK, "run-combo-%s.hfv" % args.tag)
    shutil.copyfile(S.PS_IMAGE, img)
    outdir = os.path.join(SPEC, args.tag)
    s = S.Session(img, [], outdir, mem="mv-4M")
    try:
        s.boot()
        s.mac.click(*S.BOOT_ICON, double=True)
        s.shot("volume", wait=14.0)
        s.mac.click(*S.PAINT_ICON)
        s.shot("app-selected", wait=3.0)
        s.mac.command_key("o")
        s.shot("launched", wait=40.0)
        ox, oy = s.mac.origin()
        x = s.mac._xdo
        for row in range(70, 300, 9):
            S.stroke(x, ox, oy, [(40 + (row % 27), row)] +
                     [(px, row + ((px // 10) % 5) * 2)
                      for px in range(60, 470, 14)])
        s.shot("drawn", wait=3.0)
        s.mac.command_key("s")
        s.shot("save-dialog", wait=8.0)
        s.mac._xdo("type", "--delay", "120", name)
        s.mac.key("Return")
        s.shot("saved", wait=10.0)
        s.mac.command_key("q")
        s.shot("quit", wait=10.0)
        s.menu(S.SPECIAL_X, S.SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        S.read_one(os.path.join(s.work, "boot.hfv"), name, outdir)
    finally:
        time.sleep(3)
        s.close()
    got = os.path.join(outdir, name + ".bin")
    if os.path.exists(got):
        _n, t, c, data, rsrc = mb_info(got)
        print("sitcombo: %s %s/%s data %d rsrc %d" % (name, t, c, len(data),
                                                      len(rsrc)))
    return 0


PAINT2 = os.path.join(SPEC, "paint-Painting2", "Painting2.bin")


def set_p(work, args):
    """MacPaint 1 over a second, denser painting, under every method,
    and 2.0.1's own restore of it."""
    items = [(PAINT2, "")]
    sc, names = [], []
    sc += stuff_one("PlainPaint2.sit", "Painting2", "fast")
    sc.append('Enable Optimizer "MacPaint 1"')
    for how in ("fast", "better", "faster", "optimal", "none", "guess"):
        sc += stuff_one("MP%s.sit" % how.capitalize(), "Painting2", how)
        names.append("MP%s.sit" % how.capitalize())
    sc.append('Disable Optimizer "MacPaint 1"')
    sc += unstuff_to("OutP", "MPFast.sit")
    return items, ["OutP"], sc, ["PlainPaint2.sit"] + names + [
        "OutP:Painting2"]



CDOCS = os.path.join(SPEC, "cdocs")

# ------------------------------------------------------------------
# Coloured documents, in Photoshop 1.0's own layout
# ------------------------------------------------------------------

# Every document Photoshop drew here is pencil on white, whose chroma is
# 128 everywhere — which cannot see how the module upsamples or converts
# colour. These are planar channels from ImageMagick's plasma, in PSOdd's
# resource fork with its '8BIM' 1000 (channels, height, width, depth,
# mode) rewritten: Photoshop's layout, byte for byte, but not its pixels.
CDOC_LIST = [("C256", 256, 256, 3), ("C400", 400, 300, 3),
             ("C512", 512, 128, 3), ("C203", 203, 77, 3), ("C40", 40, 40, 3),
             ("C41", 41, 9, 3), ("C24", 24, 10, 3), ("C21", 21, 13, 3),
             ("C17", 17, 9, 3), ("C16", 16, 16, 3), ("C9", 9, 9, 3),
             ("C8", 8, 8, 3), ("C7", 7, 5, 3), ("C1", 1, 1, 3),
             ("G256", 256, 256, 1), ("G203", 203, 77, 1), ("G7", 7, 5, 1),
             ("K128", 128, 128, 4), ("L128", 128, 128, 5),
             ("B128", 128, 128, 6), ("M128", 128, 128, 7)]


def make_cdocs(args):
    import struct
    _d, rs = S.forks(os.path.join(SPEC, "ps-PSOdd", "PSOdd.bin"))
    old = struct.pack(">5H", 3, 77, 203, 8, 3)
    if rs.count(old) != 1:
        raise SystemExit("sitcombo: PSOdd's 8BIM 1000 is not where it was")
    os.makedirs(CDOCS, exist_ok=True)
    for i, (name, w, h, mode) in enumerate(CDOC_LIST):
        space, ch = {1: ("gray", 1), 4: ("cmyk", 4)}.get(mode, ("rgb", 3))
        cmd = ["convert", "-seed", str(100 + i), "-size", "%dx%d" % (w, h),
               "plasma:fractal"]
        if space != "rgb":
            cmd += ["-colorspace", "Gray" if space == "gray" else "CMYK"]
        cmd += ["-depth", "8", space + ":-"]
        raw = subprocess.run(cmd, capture_output=True, check=True).stdout
        data = b"".join(raw[c::ch] for c in range(ch))       # planar
        if len(data) != w * h * ch:
            raise SystemExit("sitcombo: %s came out %d B" % (name, len(data)))
        out = os.path.join(CDOCS, name + ".bin")
        open(out, "wb").write(macbinary(
            name, "8BIM", "8BIM", data,
            rs.replace(old, struct.pack(">5H", ch, h, w, 8, mode))))
        print("sitcombo: %s %dx%d mode %d" % (name, w, h, mode))
    return 0



def set_k(work, args):
    """JPEG Lossy over COLOURED documents in Photoshop 1.0's own layout
    (`cdocs/`, built by --cdocs from PSOdd's resource fork), and
    2.0.1's restore of each. Every document Photoshop drew here is grey
    content, whose chroma is flat 128 — so none of them could see how
    the module upsamples or converts colour."""
    docs = sorted(f[:-4] for f in os.listdir(CDOCS) if f.endswith(".bin"))
    items = [(os.path.join(CDOCS, n + ".bin"), "") for n in docs]
    sc, names, folders = ['Enable Optimizer "Photoshop/JPEG Lossy"'], [], []
    for n in docs:
        sc += stuff_one("J%s.sit" % n, n, "fast")
        names.append("J%s.sit" % n)
    sc.append('Disable Optimizer "Photoshop/JPEG Lossy"')
    for n in docs:
        sc += unstuff_to("O" + n, "J%s.sit" % n)
        folders.append("O" + n)
        names.append("O%s:%s" % (n, n))
    return items, folders, sc, names



SETS = {"a": set_a, "b": set_b, "c": set_c, "d": set_d, "q": set_q,
        "e": set_e, "p": set_p, "k": set_k}
PRE = {"q": pre_q}
GUI = {"e": gui_e}
NOQUIT = {"e"}


def script_mb(work, name, lines, quit=True):
    body = ["; written by tools/vmac/sitcombo.py",
            'Write Status To "{Startup}%sStatus.out"' % name,
            "Continue On Error"] + lines + (["Quit"] if quit else []) + [""]
    out = os.path.join(work, name + "-script.bin")
    open(out, "wb").write(macbinary(name, "TEXT", "SIT!",
                                    "\r".join(body).encode("mac_roman")))
    return out


def run_script(s, name):
    """⌘E and the script's name; the picker type-selects."""
    s.mac.command_key("e")
    s.shot("script-picker", wait=8.0)
    s.mac._xdo("type", "--delay", "120", name)
    s.shot("script-selected", wait=3.0)
    s.mac.key("Return")


def run_set(args):
    outdir = os.path.join(SPEC, args.tag)
    os.makedirs(outdir, exist_ok=True)
    img = os.path.join(S.WORK, "run-combo-%s.hfv" % args.tag)
    shutil.copyfile(S.PS_IMAGE, img)
    work = tempfile.mkdtemp(prefix="sitcombo-")
    sname = "Z" + args.run.upper() + "set"
    if args.run == "q" and not args.quality:
        raise SystemExit("sitcombo: --run q needs --quality Q[,Q...]")
    try:
        items, folders, sc, names = SETS[args.run](work, args)
        items.append((script_mb(work, sname, sc,
                                quit=args.run not in NOQUIT), ""))
        put(img, items, folders)
        open(os.path.join(outdir, "script.txt"), "w").write("\n".join(sc))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    s = S.Session(img, [], outdir, mem="mv-4M")
    t0 = time.time()
    try:
        S.launch(s, nsargs())
        if args.run in PRE:
            PRE[args.run](s, args)
        run_script(s, sname)
        if args.run in GUI:
            log = []
            GUI[args.run](s, args, log)
            log += drive(s, args.password, 120.0)
        else:
            log = drive(s, args.password, args.limit)
        for line in log:
            print("sitcombo: " + line)
        s.menu(S.SPECIAL_X, S.SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        take(os.path.join(s.work, "boot.hfv"),
             names + ["%sStatus.out" % sname], outdir)
    finally:
        time.sleep(3)
        s.close()
    print("sitcombo: %s took %ds" % (args.tag, time.time() - t0))
    st = os.path.join(outdir, "%sStatus.out.bin" % sname)
    if os.path.exists(st):
        data, _r = S.forks(st)
        for line in data.decode("mac-roman", "replace").split("\r"):
            if line.strip():
                print("  " + line)
    return S.show_path(outdir)



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ps-explore", action="store_true")
    ap.add_argument("--psnew", nargs=2, metavar=("NAME", "WxH"))
    ap.add_argument("--paintnew", metavar="NAME")
    ap.add_argument("--cdocs", action="store_true",
                    help="build the coloured documents --run k stuffs")
    ap.add_argument("--gray", action="store_true")
    ap.add_argument("--mode", choices=("bitmap", "gray", "indexed", "rgb",
                                       "cmyk", "hsl", "hsb", "multichannel"),
                    help="convert to this mode after drawing")
    ap.add_argument("--drawing", default="gradgrid")
    ap.add_argument("--canvas", help="x,y of the canvas's top-left")
    ap.add_argument("--margin", type=int)
    ap.add_argument("--zoom", type=int, default=1,
                    help="the new window's reduction, 2 for 1:2")
    ap.add_argument("--run", choices=sorted(SETS))
    ap.add_argument("--password", default="swordfish")
    ap.add_argument("--quality",
                    help="Q values to try in turn, until the module takes one")
    ap.add_argument("--limit", type=float, default=1500.0)
    ap.add_argument("--tag")
    args = ap.parse_args()
    if args.ps_explore:
        args.tag = args.tag or "explore"
        return ps_explore(args)
    if args.psnew:
        args.tag = args.tag or "ps-" + args.psnew[0]
        return ps_new(args)
    if args.cdocs:
        return make_cdocs(args)
    if args.paintnew:
        args.tag = args.tag or "paint-" + args.paintnew
        return paint_new(args)
    if args.run:
        args.tag = args.tag or "set" + args.run + (
            args.quality.split(",")[0] if args.run == "q" else "")
        return run_set(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
