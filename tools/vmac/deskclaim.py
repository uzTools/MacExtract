#!/usr/bin/env python3
"""deskclaim.py — what does a System 6 Finder hand MacExtract on a double-click?

The experiment behind a companion "claimer" for MacExtract: double-click an
archive whose creator is not MacExtract's and see (1) what launches and (2)
whether the launched application is handed the FILE, or merely started.

    tools/vmac/deskclaim.py FIXTURE -o DIR [--system Sys30.img] --expect E
        --claim               add a SIT! -> MacExtract entry to the Desktop
                              file's APPL list before the boot
        --bundle              ...and a bundle filed under SIT! (needs --claim)
        --creator C           the archive's creator (default SIT!)
        --app-creator C       retag the application FILE's creator (its BNDL
                              is untouched)
        --stub-bundle         ...and its BNDL owner and signature resource
        --doc-icon TYPE       ...and an FREF and icon for document type TYPE
        --doc-icn FILE        ...that icon, not the application's inverted
        --doc-ics FILE        ...and that small icon
        --stub FILE           a real stub in a helpers folder, MacExtract
                              untouched at the root
        --multifinder         System 6 under MultiFinder
        --extra FILE:PATH     another application on the volume (StuffIt)
        --open X,Y            open this folder first (repeatable, in order)
        --app-folder NAME     put the application in a folder never opened
                              (moves the archive's icon: --archive-at X,Y)
        --invisible           set the application's invisible bit
        --no-desktop          no Desktop file (System 7: no Desktop DB/DF):
                              the Finder rebuilds it at boot
        --floppy              the archive on a second floppy
        --expect handed|open|refused|nothing

**What a run is graded on is the dialog, not the volume.** MacExtract
handed a document goes straight to its destination dialog; started without
one, it shows its Open dialog — and the run's own Return then opens the
archive from THAT list, so the entries land on the volume either way. The
first version graded on the volume and passed a run in which nothing was
handed over. The dialogs are told apart by the first solid border row below
the menu bar in `claim-3-launched.png`: the application opens the
destination dialog 30 points below the Open one (`mac/macextract_mac.c`,
`dwhere`), Mac y 82 against 112. `refused` is the Finder's own alert,
positively identified; `nothing` is none of the three.

The `APPL` resource layout is MEASURED, not quoted from a spec: read off
System 6.0.8's own Desktop file on `System6.hfv` (2026-10-10). One resource,
type 'APPL' ID 0, a run of entries, each

    creator  OSType     4 bytes
    dirID    long       the folder the application is in (2 = the root)
    name     Str255     the application's leaf name
    pad      to an even length

newest first, and one creator may appear more than once (MACS does, three
times). The bundle layout `add_bundle` writes is measured the same way.

    claim-1-desktop.png    booted to the Finder
    claim-2-volume.png     boot volume open
    claim-3-launched.png   the archive double-clicked — THE graded frame
    claim-4-done.png       Return pressed and the screen settled
    claim-5-finder.png     back in the Finder

**What it cannot see.** Which entry the Finder prefers when two
applications claim one creator: no StuffIt application is on these
volumes. It drives System 6.0.8 and System 3.0 only (FINDER_ICONS), and
the folder and floppy layouts on System 6.0.8 alone; System
7 keeps its list in `Desktop DB`, which this does not write. And it boots
the stock Desktop file, which predates MacExtract, so icons are whatever
that cache says.
"""
import argparse, os, re, shutil, struct, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402
import interactive as I                                      # noqa: E402
import mkboot as MB                                          # noqa: E402

APP_NAME = "MacExtract"
ROOT_DIRID = 2


# --- MacBinary and resource forks ------------------------------------------
# Source: MacBinary II specification (header layout, CRC-16/XMODEM over
# bytes 0..123 stored at 124); Inside Macintosh: More Macintosh Toolbox,
# Resource Manager, "Resource File Format".

def crc16_xmodem(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def macbin_split(b):
    dl, rl = struct.unpack(">II", b[83:91])
    d0 = 128
    r0 = d0 + (dl + 127) // 128 * 128
    return b[:128], b[d0:d0 + dl], b[r0:r0 + rl]


def macbin_join(header, data, rsrc):
    h = bytearray(header)
    h[83:91] = struct.pack(">II", len(data), len(rsrc))
    h[124:126] = struct.pack(">H", crc16_xmodem(bytes(h[:124])))
    pad = lambda x: x + b"\0" * (-len(x) % 128)
    return bytes(h) + pad(data) + pad(rsrc)


def rsrc_read(r):
    """[(type, id, attrs, name-or-None, data)], plus the map's file attrs."""
    do, mo = struct.unpack(">II", r[:8])
    m = r[mo:]
    fattr = struct.unpack(">H", m[22:24])[0]
    tlo, nlo = struct.unpack(">HH", m[24:28])
    ntypes = struct.unpack(">H", m[tlo:tlo + 2])[0] + 1
    out = []
    for i in range(ntypes):
        t, cnt, ro = struct.unpack(">4sHH", m[tlo + 2 + 8 * i:tlo + 10 + 8 * i])
        for j in range(cnt + 1):
            e = m[tlo + ro + 12 * j:tlo + ro + 12 * j + 12]
            rid, noff = struct.unpack(">hH", e[:4])
            attrs = e[4]
            off = int.from_bytes(e[5:8], "big")
            ln = struct.unpack(">I", r[do + off:do + off + 4])[0]
            data = r[do + off + 4:do + off + 4 + ln]
            name = None
            if noff != 0xFFFF:
                n = m[nlo + noff]
                name = m[nlo + noff + 1:nlo + noff + 1 + n]
            out.append((t, rid, attrs, name, data))
    return out, fattr


def rsrc_write(res, fattr):
    types = []
    for t, *_ in res:
        if t not in types:
            types.append(t)
    data, names, refs = b"", b"", {}
    for k, (t, rid, attrs, name, d) in enumerate(res):
        refs[k] = len(data)
        data += struct.pack(">I", len(d)) + d
    tl = struct.pack(">H", len(types) - 1)
    reflist = b""
    reflist_off = 2 + 8 * len(types)
    entries = []
    for t in types:
        mine = [k for k, r in enumerate(res) if r[0] == t]
        tl += struct.pack(">4sHH", t, len(mine) - 1,
                          reflist_off + len(reflist))
        for k in mine:
            _t, rid, attrs, name, _d = res[k]
            noff = 0xFFFF
            if name is not None:
                noff = len(names)
                names += bytes([len(name)]) + name
            reflist += struct.pack(">hHB", rid, noff, attrs) + \
                refs[k].to_bytes(3, "big") + b"\0\0\0\0"
    tlist = tl + reflist
    map_hdr_len = 28
    do = 256
    mo = do + len(data)
    head = struct.pack(">IIII", do, mo, len(data), 0)
    mp = head + b"\0" * 4 + b"\0\0" + struct.pack(
        ">HHH", fattr, map_hdr_len, map_hdr_len + len(tlist)) + tlist + names
    head = struct.pack(">IIII", do, mo, len(data), len(mp))
    mp = head + mp[16:]
    return head + b"\0" * (256 - 16) + data + mp


def appl_parse(d):
    out, p = [], 0
    while p < len(d):
        cr = d[p:p + 4]
        dirid = struct.unpack(">I", d[p + 4:p + 8])[0]
        n = d[p + 8]
        out.append((cr, dirid, d[p + 9:p + 9 + n]))
        p += 9 + n
        p += p & 1
    return out


def appl_build(entries):
    out = b""
    for cr, dirid, name in entries:
        e = cr + struct.pack(">I", dirid) + bytes([len(name)]) + name
        out += e + b"\0" * (len(e) & 1)
    return out


def desktop_appl(macbin):
    _h, _d, r = macbin_split(macbin)
    res, _ = rsrc_read(r)
    for t, rid, _a, _n, d in res:
        if t == b"APPL" and rid == 0:
            return appl_parse(d)
    return None


def add_bundle(res, creator, doctype):
    """File a minimal bundle under `creator`, the way the Finder files the
    ones it copies out of applications. MEASURED off System 6.0.8's own
    Desktop file, not quoted from a spec: each owner has a BNDL whose
    local IDs map to renumbered ICN# and FREF resources, plus a 6-byte
    resource of type <creator>, ID 0, holding 77231199 (the same in every
    copy on that volume) and then the BNDL's own ID — DMOV's says 0x15BF
    beside BNDL 5567, MSWD's 0x4374 beside BNDL 17268."""
    used = {(t, i) for t, i, *_ in res}
    stamp = None
    for t, i, _a, _n, dd in res:
        if i == 0 and len(dd) == 6 and t != b"APPL":
            stamp = dd[:4]
    icn = next(dd for t, i, _a, _n, dd in res if t == b"ICN#")
    def free(t, start):
        i = start
        while (t, i) in used:
            i += 1
        used.add((t, i))
        return i
    bid, iid, fid = free(b"BNDL", 1000), free(b"ICN#", 1000), free(b"FREF", 1000)
    bndl = creator + struct.pack(">hH", 0, 1) + \
        b"ICN#" + struct.pack(">Hhh", 0, 1, iid) + \
        b"FREF" + struct.pack(">Hhh", 0, 1, fid)
    res += [(b"BNDL", bid, 0x20, None, bndl),
            (b"ICN#", iid, 0x20, None, icn),
            (b"FREF", fid, 0x20, None, doctype + b"\0\1\0"),
            (creator, 0, 0x20, None, stamp + struct.pack(">h", bid))]


def desktop_claim(macbin, creator, dirid, name, front=True, bundle=False):
    h, d, r = macbin_split(macbin)
    res, fattr = rsrc_read(r)
    if bundle:
        add_bundle(res, creator, creator)
    for k, (t, rid, a, n, dd) in enumerate(res):
        if t == b"APPL" and rid == 0:
            ents = appl_parse(dd)
            new = (creator, dirid, name)
            ents = [new] + ents if front else ents + [new]
            res[k] = (t, rid, a, n, appl_build(ents))
            break
    else:
        raise SystemExit("deskclaim: no APPL 0 in the Desktop file")
    r2 = rsrc_write(res, fattr)
    # The rewrite must read back as what was meant, or nothing after it
    # is evidence of anything.
    back, _ = rsrc_read(r2)
    key = lambda xs: sorted((x[0], x[1], x[4]) for x in xs)
    assert key(back) == key(res)
    return macbin_join(h, d, r2)


# --- the run ----------------------------------------------------------------

# Solid black rows (75+ px) that identify each outcome, in Mac pixels,
# measured off this script's own frames on 2026-10-10/11. The Open dialog's
# top border is at SFGetFile's `where` (82) and the destination dialog's 30
# points lower (112); the Finder's "could not be opened/printed (the
# application is busy or missing)" alert has its top border at 72. A frame
# with none of them is `nothing` — a double-click that missed reads that
# way, and was read as a refusal until 2026-10-11, when a moved icon made
# exactly that happen.
# MacExtract's two dialogs by all three rows of their frame (82/85/86 and
# 112/115/116): a single row matched StuffIt Deluxe 3.5.1's archive window,
# whose border is at 80 and 82, and read it as the Open dialog (2026-10-12).
DIALOG_ROWS = (("open", (82, 85, 86)), ("handed", (112, 115, 116)),
               ("refused", (72,)),
               # System 7.0.1's "could not be opened, because the
               # application program that created it could not be found":
               # its borders at 64 and 170. Not 61, which a plain System 7
               # Finder frame has too (2026-10-12).
               ("refused", (64, 170)))


def solid_rows(png, minrun=75):
    px = subprocess.run(["convert", png, "-scale", "512x342!", "-depth", "8",
                         "gray:-"], capture_output=True, check=True).stdout
    w, h = 512, 342
    rows = set()
    for y in range(20, h):
        run = best = 0
        for v in px[y * w:(y + 1) * w]:
            run = run + 1 if v < 128 else 0
            best = max(best, run)
        if best >= minrun:
            rows.add(y)
    return rows


def which_dialog(png):
    rows = solid_rows(png)
    for name, ys in DIALOG_ROWS:
        if all(y in rows for y in ys):
            return name
    return "nothing"


def hfs_get(img, path, out):
    hfs = MB.HFS(img)
    try:
        hfs.run("hcopy", "-m", hfs.path(path), out)
    finally:
        hfs.close()


def bundle_add(bndl, rtype, local, rid):
    """Append one (local ID -> resource ID) pair under `rtype` in a BNDL.
    Source: Inside Macintosh: Macintosh Toolbox Essentials, Finder
    Interface, the bundle resource — owner, owner ID, type count - 1, then
    per type: the type, its pair count - 1 and the pairs."""
    n = struct.unpack(">H", bndl[6:8])[0] + 1
    p = 8
    for _ in range(n):
        t = bndl[p:p + 4]
        c = struct.unpack(">H", bndl[p + 4:p + 6])[0] + 1
        if t == rtype:
            return (bndl[:p + 4] + struct.pack(">H", c) + bndl[p + 6:p + 6 + 4 * c]
                    + struct.pack(">hh", local, rid) + bndl[p + 6 + 4 * c:])
        p += 6 + 4 * c
    raise SystemExit(f"deskclaim: the BNDL maps no {rtype!r}")


def _has_file(img, name):
    hfs = MB.HFS(img)
    try:
        return any(n == name for _d, n in hfs.ls(hfs.path(), invisible=True))
    finally:
        hfs.close()


def stub_bundle(macbin, creator, doc_type=None, doc_icn=None, doc_ics=None):
    """The application as a stub for `creator` would be: file creator,
    BNDL owner and signature resource all `creator`, so the Finder files
    its bundle under the creator it claims — which is what a desktop
    rebuild reads (hypothesis this run tests)."""
    h, d, r = macbin_split(macbin)
    res, fattr = rsrc_read(r)
    sig = h[69:73]
    out = []
    for t, rid, a, n, dd in res:
        if t == b"BNDL" and dd[:4] == sig:
            dd = creator + dd[4:]
        if t == sig and rid == 0:
            t = creator
        out.append((t, rid, a, n, dd))
    if doc_type:
        # A document icon for `doc_type`: MacExtract's own ICN# with the
        # icon INVERTED and the mask kept, so it cannot be mistaken for
        # the application's icon or for any other on the volume.
        icn = next(dd for t, rid, a, n, dd in out if t == b"ICN#" and rid == 128)
        inv = doc_icn or bytes(b ^ 0xFF for b in icn[:128]) + icn[128:]
        out += [(b"ICN#", 200, 0x20, None, inv),
                (b"FREF", 200, 0x20, None, doc_type + b"\0\x07\0")]
        if doc_ics:
            # Same ID as the ICN#: the Finder takes a family's members by ID.
            out.append((b"ics#", 200, 0x20, None, doc_ics))
        for k, (t, rid, a, n, dd) in enumerate(out):
            if t == b"BNDL" and dd[:4] == creator:
                dd = bundle_add(dd, b"ICN#", 7, 200)
                dd = bundle_add(dd, b"FREF", 7, 200)
                out[k] = (t, rid, a, n, dd)
    h = bytearray(h)
    h[69:73] = creator
    return macbin_join(bytes(h), d, rsrc_write(out, fattr))


def dir_id(hfs, parent, name):
    """The catalog ID of folder `name` in `parent`, off `hls -i`."""
    out = hfs.run("hls", "-i", "-a", parent).stdout
    for line in out.splitlines():
        f = line.split(None, 1)
        if len(f) == 2 and f[1] == name:
            return int(f[0])
    raise SystemExit(f"deskclaim: no folder {name!r} in {parent}")


WANT = ("Scrollbar Pattern Editor", "About Scroll Bar Pattern Editor")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixture")
    ap.add_argument("-o", "--outdir", default="vmac-claim")
    ap.add_argument("--app", default=os.path.join(R.REPO, "dist", "MacExtract.bin"))
    ap.add_argument("--system", default="System6.hfv")
    ap.add_argument("--emu", default="mv-4M")
    ap.add_argument("--claim", action="store_true",
                    help="add a SIT! -> MacExtract entry to the Desktop "
                         "file's APPL list (pointing into --app-folder)")
    ap.add_argument("--expect", required=True,
                    choices=("handed", "open", "refused", "nothing"),
                    help="which dialog claim-3 must show: the destination "
                         "one (document handed over), the Open one "
                         "(launched without it), or neither")
    ap.add_argument("--creator", default="SIT!",
                    help="the archive's creator (default SIT!)")
    ap.add_argument("--bundle", action="store_true",
                    help="with --claim, also file a bundle under SIT! in "
                         "the Desktop file")
    ap.add_argument("--app-creator",
                    help="retag the APPLICATION file's creator (its BNDL is "
                         "untouched)")
    ap.add_argument("--stub-bundle", action="store_true",
                    help="with --app-creator, retag the BNDL owner and the "
                         "signature resource too, as a stub would carry them")
    ap.add_argument("--doc-icon", metavar="TYPE",
                    help="with --stub-bundle, declare document type TYPE in "
                         "the stub's bundle with an icon of its own (the "
                         "application's, inverted): does a stub give the "
                         "archives their icon?")
    ap.add_argument("--doc-icn", metavar="FILE",
                    help="with --doc-icon, the 256-byte 'ICN#' to use instead "
                         "of the inverted application icon "
                         "(tools/icon/make_archive_icon.py --icn)")
    ap.add_argument("--doc-ics", metavar="FILE",
                    help="with --doc-icn, the 64-byte 'ics#' to go with it "
                         "(make_archive_icon.py --ics)")
    ap.add_argument("--stub", metavar="FILE",
                    help="a real stub (companion/make_stub.py): MacExtract "
                         "goes at the root UNTOUCHED, and this goes in "
                         "--app-folder (default 'MacExtract Helpers')")
    ap.add_argument("--multifinder", action="store_true",
                    help="System 6: put MultiFinder, DA Handler, "
                         "Backgrounder and Finder Startup back in the System "
                         "Folder (look for the menu bar's application icon "
                         "in claim-1 to know MultiFinder ran)")
    ap.add_argument("--extra", action="append", default=[], metavar="FILE:PATH",
                    help="another MacBinary application onto the boot volume "
                         "at PATH (folders created) — StuffIt beside the stub")
    ap.add_argument("--open", action="append", default=[], metavar="X,Y|NAME",
                    help="double-click this icon (or, on System 7, type-select "
                         "it by NAME and Open) in the volume window before "
                         "the archive, photograph it, and close it (Cmd-W): "
                         "the Finder registers what it sees, in this order")
    ap.add_argument("--app-folder",
                    help="put the application in this folder at the root, "
                         "which the run never opens")
    ap.add_argument("--invisible", action="store_true",
                    help="set the application's Finder invisible bit")
    ap.add_argument("--no-desktop", action="store_true",
                    help="leave the Desktop file deleted, so the Finder "
                         "rebuilds it at boot — what a desktop rebuild sees")
    ap.add_argument("--floppy", action="store_true",
                    help="put the archive on a second floppy, not the boot "
                         "volume, and double-click it there")
    ap.add_argument("--floppy-icon", default="472,110",
                    help="the floppy on the desktop, Mac x,y")
    ap.add_argument("--archive-at",
                    help="the archive in the boot volume's window, Mac x,y "
                         "(or, on System 7, its NAME, type-selected and "
                         "opened), "
                         "when the layout is not FINDER_ICONS' — "
                         "--app-folder moves it. Check claim-2 for it")
    ap.add_argument("--want", nargs="*", default=list(WANT),
                    help="names the archive extracts to; given rather than "
                         "derived, so the run needs no build/rel CLI")
    ap.add_argument("--launch-wait", type=float, default=20.0)
    args = ap.parse_args()
    if args.stub_bundle and not args.app_creator:
        ap.error("--stub-bundle needs --app-creator")
    if args.stub and (args.app_creator or args.stub_bundle):
        ap.error("--stub carries its own creator and bundle")
    if args.stub and not args.app_folder:
        args.app_folder = "MacExtract Helpers"

    I.calibrate(args.system)
    icons = I.FINDER_ICONS[args.system]
    os.makedirs(args.outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="vmac-claim-")
    stock = os.path.join(R.VMAC_HOME, args.system)
    shot = lambda mac, n: mac.shot(os.path.join(args.outdir, n), scale="200%")
    xy = lambda v: tuple(int(c) for c in v.split(","))
    names = lambda ents: [(c.decode("mac_roman"), d, n.decode("mac_roman"))
                          for c, d, n in ents]
    try:
        app = args.app
        if args.stub_bundle:
            app = os.path.join(work, "app.bin")
            open(app, "wb").write(stub_bundle(
                open(args.app, "rb").read(),
                args.app_creator.encode("mac_roman"),
                args.doc_icon.encode("mac_roman") if args.doc_icon else None,
                open(args.doc_icn, "rb").read() if args.doc_icn else None,
                open(args.doc_ics, "rb").read() if args.doc_ics else None))
        boot = os.path.join(work, "boot-claim.hfv")
        extra = ()
        cmd = [sys.executable, os.path.join(HERE, "mkboot.py"), stock, app,
               boot, "--finder", "--app-name", APP_NAME]
        if not args.floppy:
            cmd += ["--data", f"{args.fixture}:archive.sit"]
        R.sh(*cmd)
        if args.floppy:
            flop = os.path.join(work, "floppy.dsk")
            R.make_floppy(flop, "Archives",
                          extras=[(args.fixture, "archive.sit")])
            extra = (flop,)
            fh = MB.HFS(flop)
            try:
                fh.run("hattrib", "-t", "SIT!", "-c", args.creator,
                       fh.path("archive.sit"))
            finally:
                fh.close()

        if args.multifinder:
            # The stock boot blocks already name MultiFinder (their field
            # at 0x5A) with the shell field left at Finder, so nothing is
            # patched: what decides is the Finder's Set Startup choice,
            # kept in `Finder Startup` (hypothesis, which claim-1 settles).
            for n in ("MultiFinder", "DA Handler", "Backgrounder",
                      "Finder Startup"):
                tmp = os.path.join(work, n + ".bin")
                hfs_get(stock, "System Folder:" + n, tmp)
                bh = MB.HFS(boot)
                try:
                    bh.run("hcopy", "-m", tmp, bh.path("System Folder", n))
                finally:
                    bh.close()
        hfs = MB.HFS(boot)
        try:
            where = hfs.path(APP_NAME)
            dirid = ROOT_DIRID
            if args.stub:
                hfs.run("hmkdir", hfs.path(args.app_folder))
                where = hfs.path(args.app_folder, "SIT! Helper")
                hfs.run("hcopy", "-m", args.stub, where)
                dirid = dir_id(hfs, hfs.path(), args.app_folder)
            elif args.app_folder:
                hfs.run("hmkdir", hfs.path(args.app_folder))
                hfs.run("hrename", where, hfs.path(args.app_folder, APP_NAME))
                where = hfs.path(args.app_folder, APP_NAME)
                dirid = dir_id(hfs, hfs.path(), args.app_folder)
            if args.app_creator:
                hfs.run("hattrib", "-c", args.app_creator, where)
            if args.invisible:
                hfs.run("hattrib", "+i", where)
            for spec in args.extra:
                src, _, mpath = spec.partition(":")
                # HFS names are MacRoman bytes; hfsutils takes them as
                # bytes, so "™" has to arrive as 0xAA, not as UTF-8.
                mpath = mpath.encode("mac_roman").decode(
                    sys.getfilesystemencoding(), "surrogateescape")
                parts = mpath.split(":")
                for k in range(1, len(parts)):
                    hfs.run("hmkdir", hfs.path(*parts[:k]), check=False)
                hfs.run("hcopy", "-m", src, hfs.path(*parts))
            if not args.floppy:
                hfs.run("hattrib", "-t", "SIT!", "-c", args.creator,
                        hfs.path("archive.sit"))
            # System 7 keeps the list in `Desktop DB`, which nothing here
            # reads or writes: no `Desktop` file to restore or patch.
            has_desk = _has_file(stock, "Desktop")
            if args.no_desktop:
                # System 7's list: deleted, the Finder rebuilds it at boot
                # as it rebuilds a missing `Desktop` file on System 6.
                for n in ("Desktop DB", "Desktop DF"):
                    hfs.run("hdel", hfs.path(n), check=False)
            if not args.no_desktop and has_desk:
                # mkboot --finder deletes the Desktop file; put the stock
                # one back, patched or not.
                desk = os.path.join(work, "Desktop.bin")
                hfs_get(stock, "Desktop", desk)
                mb = open(desk, "rb").read()
                if args.claim:
                    mb = desktop_claim(mb, b"SIT!", dirid, where.rsplit(":", 1)[1].encode("mac_roman"),
                                       bundle=args.bundle)
                open(desk, "wb").write(mb)
                hfs.run("hcopy", "-m", desk, hfs.path("Desktop"))
                print("deskclaim: APPL on the boot image:",
                      names(desktop_appl(mb))[:3], "...")
            elif args.claim:
                raise SystemExit("deskclaim: --claim needs a Desktop file "
                                 "(System 7's Desktop DB is not written)")
            print("deskclaim: application at", where, "dirID", dirid)
        finally:
            hfs.close()

        mac = I.Mac(boot, args.emu, work, extra=extra)
        try:
            if mac.settle(os.path.join(args.outdir, ".settle.png"),
                          interval=5.0, timeout=300) is None:
                raise SystemExit("deskclaim: never reached the Finder")
            shot(mac, "claim-1-desktop.png")
            if args.floppy:
                # The boot volume first, so the Finder has seen the
                # application the way a user's Finder would have.
                mac.click(*icons["volume"], double=True)
                time.sleep(4.0)
                mac.click(*xy(args.floppy_icon), double=True)
                time.sleep(4.0)
                shot(mac, "claim-2-volume.png")
                # The archive is the floppy's only item: Select All and
                # Open need no coordinate inside a window placed by the
                # Finder.
                mac.command_key("a")
                time.sleep(1.0)
                mac.command_key("o")
            else:
                mac.click(*icons["volume"], double=True)
                time.sleep(4.0)
                shot(mac, "claim-2-volume.png")
                for k, at in enumerate(args.open, 1):
                    if re.fullmatch(r"\d+,\d+", at):
                        mac.click(*xy(at), double=True)
                    else:
                        # System 7 only: type-select the icon by name in
                        # the front window, then Open — no coordinate, so
                        # an icon off the window's edge is still reached.
                        mac._xdo("type", "--delay", "150", at)
                        time.sleep(1.5)
                        mac.command_key("o")
                    time.sleep(4.0)
                    shot(mac, f"claim-2-open{k}.png")
                    mac.command_key("w")
                    time.sleep(2.0)
                if args.archive_at and not re.fullmatch(r"\d+,\d+",
                                                         args.archive_at):
                    mac._xdo("type", "--delay", "150", args.archive_at)
                    time.sleep(1.5)
                    mac.command_key("o")
                else:
                    mac.click(*(xy(args.archive_at) if args.archive_at
                                else icons["archive"]), double=True)
            time.sleep(args.launch_wait)
            shot(mac, "claim-3-launched.png")
            I.accept_destination(mac)
            mac.settle(os.path.join(args.outdir, ".settle.png"),
                       interval=5.0, quiet=30.0, timeout=600)
            shot(mac, "claim-4-done.png")
            # Return dismisses "Extraction complete." and the Open dialog
            # that follows is cancelled, so the Finder comes back and has a
            # chance to write its Desktop file before the image is read.
            mac.key("Return")
            time.sleep(2.0)
            mac.command_key("period")
            time.sleep(args.launch_wait)
            shot(mac, "claim-5-finder.png")
        finally:
            mac.close()

        seen = which_dialog(os.path.join(args.outdir, "claim-3-launched.png"))
        print(f"deskclaim: claim-3 shows: {seen}")
        after = os.path.join(work, "boot.hfv")
        outvol = extra[0] if args.floppy else after
        want = {(n,) for n in args.want}
        have = I.volume_names(outvol)
        got = want <= have and bool(want)
        print("deskclaim: entries on the archive's volume after:",
              "ALL" if got else sorted(want - have))
        d2 = os.path.join(work, "Desktop-after.bin")
        if _has_file(after, "Desktop"):
            hfs_get(after, "Desktop", d2)
            print("deskclaim: APPL after the run:",
                  names(desktop_appl(open(d2, "rb").read())))
        else:
            print("deskclaim: no Desktop file after the run (Desktop DB)")
        # A handed-over document must also have come out; the volume is
        # the second half of that, never the whole of it (docstring).
        ok = seen == args.expect and (seen != "handed" or got)
        print(f"deskclaim: {'PASS' if ok else 'FAIL'} "
              f"(expected {args.expect}, saw {seen})")
        return 0 if ok else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
