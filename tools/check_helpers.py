#!/usr/bin/env python3
"""check_helpers.py — the double-click helper, built and stamped, as the Finder needs it.

    tools/check_helpers.py              build companion/stub, stamp a 'SIT!' helper, check it
    tools/check_helpers.py --file X     check an already-stamped helper (MacBinary)

Nothing else in ci.sh builds companion/ (DECISIONS.md 2026-11-03, *the gate a
helper commit has*). This is the part of a helper that can be read off the
file; whether it hands an archive on is the emulator's (DECISIONS.md
2026-11-01, *the Open item MultiFinder looks for*).

Checked, each from where it is decided:
  - the Finder flags: hasBundle set, inited clear, type APPL, the creator
    (companion/make_stub.py writes them; the Finder registers only a bundle
    it has not inited);
  - one CODE segment, CODE 0 and CODE 1 only (companion/stub/CMakeLists.txt,
    --mac-single);
  - 'SIZE' -1 says canBackground (the helper stays behind MacExtract after
    handing an archive on: companion/stub/stub.c, Odoc);
  - the bundle: 'BNDL' 128 owned by the creator, its signature resource, one
    icon family at ID 128 and nothing else of the six types, the BNDL's
    ICN# list a single pair local 0 -> 128, one 'FREF' per document type,
    every one on local icon 0 (the maintainer, 2026-11-03: the archive
    icon for its documents), and none for APPL: no application icon (the
    maintainer, 2026-11-16), in the stamped helpers, in the shipped zip's
    and in the floppies' Desktop files;
  - 'open' 128 with no types, so Easy Open does not offer the helper for an
    orphaned document (DECISIONS.md 2026-11-13, *the helper that is not
    offered*);
  - 'vers' 1 carrying UNC_VERSION, MacExtract's own (a release bumps both);
  - the size, against a ceiling: a helper is on every floppy twenty times.

What it CANNOT see: whether the Finder of a given System accepts the bundle,
draws the icon, or hands the helper an archive; whether the hand-off to a
running MacExtract arrives. Those are emulator runs, recorded in DECISIONS.md.
"""
import argparse, os, shutil, struct, subprocess, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "vmac"))
import deskclaim as D                                         # noqa: E402

# Ratchet: the MacBinary size of the 'SIT!' helper this tree stamps, measured
# 2026-11-03 (DECISIONS.md 2026-11-01, *What the helper weighs*). Lower it when
# the helper shrinks; raising it is a decision, not a fix. RAISED 2026-11-03,
# 9,344 -> 9,472: MacExtract found through the desktop, wherever it is
# (DECISIONS.md 2026-11-03, *the helper that asks the desktop*); 9,472 ->
# 9,728 the same day, the stub registering its own icons (the same entry).
# LOWERED 2026-11-03, 9,728 -> 6,784: no Retro68 runtime (DECISIONS.md
# 2026-11-03, *the helper without a runtime*). RAISED 2026-11-04, 6,784 ->
# 6,912: 'vers' 1, MacExtract's version (DECISIONS.md 2026-11-04, *the
# helpers in dist*).
CEILING = 6912
FAMILY = (b"ICN#", b"ics#", b"icl4", b"ics4", b"icl8", b"ics8")
CREATOR, TYPES = b"SIT!", (b"SIT!", b"SITD")
HAS_BUNDLE, INITED = 0x2000, 0x0100
CAN_BACKGROUND = 0x1000          # 'SIZE' flags, bit 12 (Processes.r)


def toolchain():
    """The Retro68 toolchain, found as tools/build_mac.sh finds it."""
    env = os.environ.get("RETRO68")
    if env and os.path.isdir(env):
        return env
    gcc = shutil.which("m68k-apple-macos-gcc")
    if gcc:
        return os.path.dirname(os.path.dirname(gcc))
    if os.access("/opt/Retro68-build/toolchain/bin/m68k-apple-macos-gcc", os.X_OK):
        return "/opt/Retro68-build/toolchain"
    return None


def build():
    tc = toolchain()
    cmake = os.path.join(tc or "", "m68k-apple-macos", "cmake", "retro68.toolchain.cmake")
    if not tc or not os.path.isfile(cmake):
        print("helpers: Retro68 m68k toolchain not found — skipping the helper check.")
        return None
    out = os.path.join(ROOT, "build", "stub")
    helper = os.path.join(out, "check-SIT.bin")
    steps = [
        ["cmake", "-B", out, "-S", os.path.join(ROOT, "companion", "stub"),
         "-DCMAKE_TOOLCHAIN_FILE=" + cmake],
        ["cmake", "--build", out],
        [sys.executable, os.path.join(ROOT, "companion", "make_stub.py"),
         os.path.join(out, "Stub.bin"), "--creator", CREATOR.decode(),
         "--types"] + [t.decode() for t in TYPES] + ["-o", helper],
    ]
    for cmd in steps:
        # The build's own output, warnings included, only when it fails.
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.stderr.write(r.stdout + r.stderr)
            raise SystemExit(f"helpers: FAIL: {' '.join(cmd[:2])} exited {r.returncode}")
    return helper


def check(path, creator=CREATOR, types=TYPES, ceiling=CEILING):
    CREATOR, TYPES = creator, tuple(types)
    bad = []
    blob = open(path, "rb").read()
    h, _d, r = D.macbin_split(blob)
    ftype, fcreator = h[65:69], h[69:73]
    flags = (h[73] << 8) | h[101]
    if ftype != b"APPL":
        bad.append(f"file type {ftype!r}, not APPL")
    if fcreator != CREATOR:
        bad.append(f"file creator {fcreator!r}, not {CREATOR!r}")
    if not flags & HAS_BUNDLE:
        bad.append("hasBundle is clear: the Finder will not register it")
    if flags & INITED:
        bad.append("inited is set: the Finder will not read its bundle")

    res, _ = D.rsrc_read(r)
    by = {}
    for t, i, _a, _n, data in res:
        by.setdefault(t, {})[i] = data

    codes = sorted(by.get(b"CODE", {}))
    if codes != [0, 1]:
        bad.append(f"CODE resources {codes}, not one segment (0 and 1)")

    size = by.get(b"SIZE", {}).get(-1)
    if size is None or len(size) < 2:
        bad.append("no 'SIZE' -1")
    elif not struct.unpack(">H", size[:2])[0] & CAN_BACKGROUND:
        bad.append("'SIZE' says cannotBackground: it cannot stay behind MacExtract")

    for t in FAMILY:
        ids = sorted(by.get(t, {}))
        if ids != [128]:
            bad.append(f"{t.decode()} IDs {ids}, not the one family at 128")

    # The version Get Info shows: MacExtract's UNC_VERSION (the maintainer,
    # 2026-11-04; a release bumps it), so a helper that missed a bump fails.
    sys.path.insert(0, os.path.join(ROOT, "companion"))
    import make_stub
    want_v = make_stub.unc_version()
    v = by.get(b"vers", {}).get(1)
    if v is None or len(v) < 7:
        bad.append("no 'vers' 1")
    else:
        short = v[7:7 + v[6]].decode("mac_roman")
        if short != want_v:
            bad.append(f"'vers' 1 says {short!r}, not UNC_VERSION {want_v!r}")

    if 0 not in by.get(CREATOR, {}):
        bad.append(f"no signature resource {CREATOR.decode()} 0")

    # Easy Open offers an application for the types its 'open' lists, its
    # FREFs' when it has none: this one lists none (DECISIONS.md 2026-11-13,
    # *the helper that is not offered*). Source: Inside Macintosh: More
    # Macintosh Toolbox, 7-44, Figure 7-11.
    want_open = make_stub.open_resource(CREATOR, TYPES)
    if by.get(b"open", {}) != {128: want_open}:
        bad.append(f"'open' {by.get(b'open')}, not 'open' 128 listing the "
                   f"types MacExtract's bundle does not claim")

    bndl = by.get(b"BNDL", {}).get(128)
    if bndl is None:
        bad.append("no 'BNDL' 128")
    else:
        # Source: Inside Macintosh: Macintosh Toolbox Essentials, Finder
        # Interface, the bundle resource — the layout make_stub.py writes.
        owner = bndl[:4]
        if owner != CREATOR:
            bad.append(f"BNDL owner {owner!r}, not {CREATOR!r}")
        o, maps = 8, {}
        ntypes = struct.unpack(">H", bndl[6:8])[0] + 1
        for _ in range(ntypes):
            kind = bndl[o:o + 4]
            n = struct.unpack(">H", bndl[o + 4:o + 6])[0] + 1
            pairs = [struct.unpack(">hh", bndl[o + 6 + 4 * k:o + 10 + 4 * k])
                     for k in range(n)]
            maps[kind] = pairs
            o += 6 + 4 * n
        if maps.get(b"ICN#") != [(0, 128)]:
            bad.append(f"BNDL ICN# pairs {maps.get(b'ICN#')}, not [(0, 128)]")
        frefs = maps.get(b"FREF", [])
        kinds = []
        for _local, rid in frefs:
            fr = by.get(b"FREF", {}).get(rid)
            if fr is None:
                bad.append(f"BNDL names FREF {rid}, which is missing")
                continue
            kinds.append(fr[:4])
            local = struct.unpack(">h", fr[4:6])[0]
            if local != 0:
                bad.append(f"FREF {rid} ({fr[:4]!r}) on local icon {local}, not 0")
        if sorted(kinds) != sorted(TYPES):
            bad.append(f"FREF types {kinds}, not {list(TYPES)}")
    bad += [f"an 'APPL' FREF in the {o.decode('mac_roman')} bundle: {APPL_ICON}"
            for o in appl_owners(res)]

    if ceiling and len(blob) > ceiling:
        bad.append(f"{len(blob)} B, over the {ceiling} B ceiling")
    return bad, len(blob)


# The maintainer, 2026-11-16: a helper carries no application icon. The
# Finder files icons by creator and type, so a helper's 'APPL' icon became
# the icon of the real program of its creator once the helper had run
# (DECISIONS.md 2026-11-16, *the helper without an application icon*).
APPL_ICON = ("the helper's icon would be drawn for every application of its "
             "creator (DECISIONS.md 2026-11-16, *the helper without an "
             "application icon*)")


def appl_owners(res, keep=()):
    """The owners of every 'BNDL' in `res` (a resource list) that maps a
    'FREF' for 'APPL', but those in `keep`: a helper's fork, or a Desktop
    file's bundle copies. Source: Inside Macintosh: Macintosh Toolbox
    Essentials, Finder Interface, the bundle resource."""
    by = {(t, i): d for t, i, _a, _n, d in res}
    out = []
    for t, _i, _a, _n, b in res:
        if t != b"BNDL" or b[:4] in keep:
            continue
        o = 8
        for _ in range(struct.unpack(">H", b[6:8])[0] + 1):
            kind, n = b[o:o + 4], struct.unpack(">H", b[o + 4:o + 6])[0] + 1
            rids = [struct.unpack(">h", b[o + 8 + 4 * k:o + 10 + 4 * k])[0] for k in range(n)]
            if kind == b"FREF" and any(by.get((b"FREF", r), b"")[:4] == b"APPL" for r in rids):
                out.append(b[:4])
            o += 6 + 4 * n
    return out


def sidecar_fork(ad):
    """The resource fork, entry 2, of an AppleDouble sidecar. Source: RFC
    1740, AppleSingle/AppleDouble: the entry count at 24, then per entry
    its ID, offset and length."""
    for k in range(struct.unpack(">H", ad[24:26])[0]):
        eid, off, ln = struct.unpack(">III", ad[26 + 12 * k:38 + 12 * k])
        if eid == 2:
            return ad[off:off + ln]
    return b""


def check_dist(stub):
    """The twenty-four helpers dist/ ships: every row of companion/helpers.tsv
    stamped from this tree's stub passes check() for its own creator and
    types; dist/MacExtract-Helpers.zip is byte for byte the zip
    make_helpers.py writes from them (it is reproducible: fixed times), so a
    stale or hand-edited one fails; and both disk images' "MacExtract
    Helpers" folders hold those names, when hfsutils is there to look."""
    sys.path.insert(0, os.path.join(ROOT, "companion"))
    import make_helpers as M
    bad = []
    want = M.rows()
    built = open(stub, "rb").read()
    tmp = os.path.join(ROOT, "build", "stub")
    for (creator, name, types), (_n, mb) in zip(want, M.helpers(built)):
        path = os.path.join(tmp, "check-" + name + ".bin")
        open(path, "wb").write(mb)
        b, _ = check(path, creator, types, ceiling=None)
        bad += [f"{name}: {x}" for x in b]
    shipped = os.path.join(ROOT, "dist", "MacExtract-Helpers.zip")
    fresh = os.path.join(tmp, "check-helpers.zip")
    M.write_zip(fresh, built)
    if not os.path.isfile(shipped):
        bad.append("dist/MacExtract-Helpers.zip is missing — run tools/make_dist.sh")
    else:
        if open(shipped, "rb").read() != open(fresh, "rb").read():
            bad.append("dist/MacExtract-Helpers.zip is STALE: not the zip this tree "
                       "builds — run tools/make_dist.sh")
        # The shipped helpers themselves, read out of the zip.
        with zipfile.ZipFile(shipped) as z:
            for n in z.namelist():
                if "/._" in n:
                    res, _ = D.rsrc_read(sidecar_fork(z.read(n)))
                    if appl_owners(res):
                        bad.append(f"dist/MacExtract-Helpers.zip: {n.split('._')[-1]}: "
                                   f"an 'APPL' FREF: {APPL_ICON}")
    if shutil.which("hls") and shutil.which("hmount"):
        names = sorted(n for _, n, _ in want)
        for img in ("MacExtract-800K.img", "MacExtract-1440K.img"):
            home = os.path.join(ROOT, ".tmp")
            env = dict(os.environ, HOME=home)
            r = subprocess.run(["hmount", os.path.join(ROOT, "dist", img)], capture_output=True, env=env)
            if r.returncode:
                bad.append(f"dist/{img}: hmount failed")
                continue
            ls = subprocess.run(["hls", "-1", ":MacExtract Helpers"], capture_output=True, text=True,
                                encoding="mac_roman", env=env)
            # The Desktop file: MacExtract and every helper, the helpers in
            # the folder's own catalog ID (DECISIONS.md 2026-11-04, *the
            # floppy that is ready*).
            ids = subprocess.run(["hls", "-i", "-a", ":"], capture_output=True, text=True,
                                 encoding="mac_roman", env=env).stdout
            dirid = [int(l.split(None, 1)[0]) for l in ids.splitlines()
                     if l.split(None, 1)[1:] == ["MacExtract Helpers"]]
            got_d = os.path.join(home, "check-Desktop.bin")
            cp = subprocess.run(["hcopy", "-m", ":Desktop", got_d], capture_output=True, env=env)
            subprocess.run(["humount"], capture_output=True, env=env)
            if cp.returncode or not dirid:
                bad.append(f"dist/{img}: no Desktop file, or no helpers folder")
            else:
                # Whole: the APPL list and every bundle copy, which is
                # what a Finder reads off a locked floppy (DECISIONS.md
                # 2026-11-14, *the floppy that works locked*).
                have = open(got_d, "rb").read()
                for o in appl_owners(D.rsrc_read(D.macbin_split(have)[2])[0], keep=(b"MExt",)):
                    bad.append(f"dist/{img}: the Desktop file's {o.decode('mac_roman')} "
                               f"bundle maps an 'APPL' FREF: {APPL_ICON}")
                want_d = M.desktop(M.volume_apps(
                    open(os.path.join(ROOT, "dist", "MacExtract.bin"), "rb").read(),
                    built, dirid[0]))
                if D.macbin_split(have)[2] != D.macbin_split(want_d)[2]:
                    bad.append(f"dist/{img}: the Desktop file is not the one make_helpers.py "
                               f"builds (APPL {D.desktop_appl(have)}) — run tools/make_dist.sh")
            got = sorted(ls.stdout.split("\n")[:-1]) if not ls.returncode else None
            if got != names:
                bad.append(f"dist/{img}: MacExtract Helpers holds {got}, not {names}")
            bad += [f"dist/{img}: {x}" for x in check_layout(os.path.join(ROOT, "dist", img))]
    mfs = os.path.join(ROOT, "dist", "MacExtract-400K.img")
    got_d = os.path.join(ROOT, ".tmp", "check-DesktopMFS.bin")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "vmac", "mkmfs.py"),
                        mfs, "--extract", "Desktop", got_d], capture_output=True)
    want_d = M.desktop([(open(os.path.join(ROOT, "dist", "MacExtract.bin"), "rb").read(), 2)],
                       appl=False)
    if r.returncode or D.macbin_split(open(got_d, "rb").read())[2] != D.macbin_split(want_d)[2]:
        bad.append("dist/MacExtract-400K.img: no Desktop file, or not the one make_helpers.py "
                   "--mfs builds — run tools/make_dist.sh")
    return bad


def check_layout(img):
    """Every file and folder on an HFS floppy inited and placed (fdFlags
    0x0100, a location), and every folder's window rectangle set: a placed
    folder with none bombed System 3.0's Finder, ID = 04, and the helpers
    left to the Finder were stacked in one column (DECISIONS.md 2026-11-14,
    *the floppy that works locked*); and every icon inside its folder's
    window with the margins that showed no scroll bars. It cannot see the
    scroll bars themselves, only the emulator's frames do. The Desktop file, invisible, and the
    root, whose rectangle every Finder measured ignores, are not checked."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "vmac"))
    import hfscat
    bad = []
    rects, at = {}, {}
    for r in hfscat.records(open(img, "rb").read()):
        p = ":".join(x.decode("mac_roman") for x in r["path"])
        if len(r["path"]) < 2 or r["path"][-1] == b"Desktop":
            continue
        rec = r["rec"]
        if r.get("type") is not None:                   # a file: FInfo at +4
            fl, v, h = struct.unpack(">Hhh", rec[12:18])
        else:                                           # a folder: DInfo at +22
            top, left, bottom, right, fl, v, h = struct.unpack(">hhhhHhh", rec[22:36])
            if bottom <= top or right <= left:
                bad.append(f"{p}: no window rectangle")
            rects[tuple(r["path"])] = (bottom - top, right - left)
        if not fl & 0x0100 or (v, h) == (0, 0):
            bad.append(f"{p}: not placed (flags 0x{fl:04X}, at {v},{h})")
        at[tuple(r["path"])] = (v, h)
    # Every icon inside its folder's window by the margins measured to show
    # with no scroll bars on 3.0, 6.0.8 and 7.0.1: the last row at v 122 in
    # a window 210 high, the last column at h 330 in one 398 wide
    # (DECISIONS.md 2026-11-14, *the floppy that works locked*).
    for path, (v, h) in at.items():
        size = rects.get(path[:-1])
        if size and (v > size[0] - 88 or h > size[1] - 68):
            bad.append(f"{':'.join(x.decode('mac_roman') for x in path)}: at {v},{h}, "
                       f"outside its window's {size[0]} x {size[1]} without scrolling")
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="check this stamped helper instead of building one")
    a = ap.parse_args()
    path = a.file or build()
    if path is None:
        return 0
    bad, size = check(path)
    if not a.file:
        bad += check_dist(os.path.join(ROOT, "build", "stub", "Stub.bin"))
    for b in bad:
        print(f"helpers: FAIL: {b}")
    if bad:
        return 1
    print(f"helpers: {os.path.basename(path)}: {size} B (ceiling {CEILING}), "
          f"one CODE segment, one icon family, every FREF on local 0, none for APPL"
          + ("" if a.file else "; the helpers zip and both images current"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
