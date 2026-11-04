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
    ICN# list a single pair local 0 -> 128, 'FREF' 128 for APPL and one per
    document type, every one on local icon 0 (the maintainer, 2026-11-03:
    the archive icon for the helper and its documents);
  - 'vers' 1 carrying UNC_VERSION, MacExtract's own (a release bumps both);
  - the size, against a ceiling: a helper is on every floppy twenty times.

What it CANNOT see: whether the Finder of a given System accepts the bundle,
draws the icon, or hands the helper an archive; whether the hand-off to a
running MacExtract arrives. Those are emulator runs, recorded in DECISIONS.md.
"""
import argparse, os, shutil, struct, subprocess, sys

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
        if sorted(kinds) != sorted((b"APPL",) + TYPES):
            bad.append(f"FREF types {kinds}, not APPL and {list(TYPES)}")

    if ceiling and len(blob) > ceiling:
        bad.append(f"{len(blob)} B, over the {ceiling} B ceiling")
    return bad, len(blob)


def check_dist(stub):
    """The sixteen helpers dist/ ships: every row of companion/helpers.tsv
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
    elif open(shipped, "rb").read() != open(fresh, "rb").read():
        bad.append("dist/MacExtract-Helpers.zip is STALE: not the zip this tree "
                   "builds — run tools/make_dist.sh")
    if shutil.which("hls") and shutil.which("hmount"):
        names = sorted(n for _, n, _ in want)
        for img in ("MacExtract.dsk", "MacExtract-1440K.img"):
            home = os.path.join(ROOT, ".tmp")
            env = dict(os.environ, HOME=home)
            r = subprocess.run(["hmount", os.path.join(ROOT, "dist", img)], capture_output=True, env=env)
            if r.returncode:
                bad.append(f"dist/{img}: hmount failed")
                continue
            ls = subprocess.run(["hls", "-1", ":MacExtract Helpers"], capture_output=True, text=True,
                                encoding="mac_roman", env=env)
            subprocess.run(["humount"], capture_output=True, env=env)
            got = sorted(ls.stdout.split("\n")[:-1]) if not ls.returncode else None
            if got != names:
                bad.append(f"dist/{img}: MacExtract Helpers holds {got}, not {names}")
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
          f"one CODE segment, one icon family, every FREF on local 0"
          + ("" if a.file else "; the helpers zip and both images current"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
