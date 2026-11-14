#!/usr/bin/env python3
"""make_helpers.py — every helper companion/helpers.tsv lists, from one stub build.

    python3 companion/make_helpers.py build/stub/Stub.bin -o DIR
    python3 companion/make_helpers.py build/stub/Stub.bin --zip OUT.zip
    python3 companion/make_helpers.py build/stub/Stub.bin --desktop OUT.bin \
        --app dist/MacExtract.bin --dirid N
    python3 companion/make_helpers.py build/stub/Stub.bin --desktop OUT.bin \
        --app dist/MacExtract.bin --mfs

Writes DIR/<name>.bin, one MacBinary per row: the row's creator and types
stamped onto the build by make_stub.stamp, named in its header as the row
names it; tools/make_dist.sh puts them in the "MacExtract Helpers" folder of
both disk images. --zip writes the same eighteen as ONE download that
MacExtract itself opens: a zip laid out as the Mac OS X Finder writes one,
`MacExtract Helpers/<name>` (an empty data fork) and its sidecar
`__MACOSX/MacExtract Helpers/._<name>` holding the Finder info and the
resource fork, in copyfile's layout (tools/synth_macosx.py, copyfile_sidecar,
which run_meta.py grades MacExtract on). Fixed times, so the same tree
writes the same bytes. tools/check_helpers.py checks both.

--desktop writes, as MacBinary, the invisible Desktop file make_dist.sh puts
on both disks, so that a Mac without a hard disk finds the helpers on the
MacExtract floppy with it ejected: the Finders of System 3.0 to 7.x keep a
floppy's applications in that file, and the 3.0 Finder registers none on
insertion (DECISIONS.md 2026-11-04, *the floppy that is ready*). N is the
"MacExtract Helpers" folder's catalog ID. It carries every application's
bundle too, as System 6.0.8's Finder files them, because a Finder cannot
write them onto a locked floppy (2026-11-14, *the floppy that works
locked*); `--mfs` writes the 400K's, MacExtract's bundle alone.
"""
import argparse, os, struct, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_stub as S                                         # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "vmac"))
import synth_macosx as X                                      # noqa: E402
import deskclaim as D                                         # noqa: E402

FOLDER = "MacExtract Helpers"
WHEN = (1990, 1, 1, 0, 0, 0)

TABLE = os.path.join(HERE, "helpers.tsv")


def rows(path=TABLE):
    """(creator, name, types) per row, the codes as four bytes each."""
    out = []
    for line in open(path, encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        creator, name, _program, types, _source = line.rstrip("\n").split("\t")
        out.append((S.ostype(creator), name,
                    [S.ostype(t) for t in types.split(",")]))
    return out


def helpers(stub):
    """(name, MacBinary) for every row."""
    out = []
    for creator, name, types in rows():
        if len(name.encode("mac_roman")) > 8:
            raise SystemExit(f"make_helpers: {name!r} is over 8 characters")
        out.append((name, S.stamp(stub, creator, types, name)))
    return out


def sidecar(macbin):
    """The copyfile sidecar for a helper: its Finder info (type, creator,
    flags; no position) and its resource fork."""
    h, _d, r = D.macbin_split(macbin)
    flags = (h[73] << 8) | h[101]
    return X.copyfile_sidecar(X.finfo(h[65:69], h[69:73], flags, 0, 0), r)


def write_zip(path, stub):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        def put(name, data):
            i = zipfile.ZipInfo(name, WHEN)
            i.compress_type = zipfile.ZIP_DEFLATED
            i.external_attr = (0o40755 << 16 | 0x10) if name.endswith("/") else 0o644 << 16
            z.writestr(i, data)
        put(FOLDER + "/", b"")
        hs = helpers(stub)
        for name, _mb in hs:
            put(f"{FOLDER}/{name}", b"")
        put("__MACOSX/", b"")
        put(f"__MACOSX/{FOLDER}/", b"")
        for name, mb in hs:
            put(f"__MACOSX/{FOLDER}/._{name}", sidecar(mb))


# The Finder's own stamp in the 6-byte signature resource it files beside
# each copied bundle: 77231199, then the BNDL's ID. The same four bytes in
# every copy on a disk System 6.0.8's Finder wrote here (2026-11-14) and on
# Apple's 1991 System 6.0.8 "System Tools" disk (tools/vmac/deskclaim.py,
# add_bundle).
STAMP = bytes.fromhex("77231199")


def bundle_copy(macbin, nid):
    """The resources System 6.0.8's Finder files in a floppy's Desktop file
    for one application, as it wrote them (measured 2026-11-14, DECISIONS.md
    *the floppy that works locked*): the BNDL with its local IDs
    renumbered 1..n in FREF order, one FREF copy per FREF on local icon k,
    one ICN# copy per FREF (the icon its FREF named), the 6-byte signature,
    all at attributes 0x24. Resource IDs from nid(type), in order: the
    Finder's are UniqueID's, random, so the build picks its own."""
    _h, _d, r = D.macbin_split(macbin)
    res, _ = D.rsrc_read(r)
    by = {(t, i): dd for t, i, _a, _n, dd in res}
    bndl = next(dd for t, i, _a, _n, dd in res if t == b"BNDL")
    sig = bndl[:4]
    maps, p = {}, 8
    for _ in range(struct.unpack(">h", bndl[6:8])[0] + 1):
        t = bndl[p:p + 4]
        n = struct.unpack(">h", bndl[p + 4:p + 6])[0] + 1
        maps[t] = [struct.unpack(">hh", bndl[p + 6 + 4 * k:p + 10 + 4 * k]) for k in range(n)]
        p += 6 + 4 * n
    icn_of = dict(maps[b"ICN#"])
    out, icns, frefs = [], [], []
    bid = nid(b"BNDL")
    for k, (_local, rid) in enumerate(maps[b"FREF"], 1):
        fr = by[(b"FREF", rid)]
        icon = by[(b"ICN#", icn_of[struct.unpack(">h", fr[4:6])[0]])]
        iid, fid = nid(b"ICN#"), nid(b"FREF")
        icns.append((k, iid))
        frefs.append((k, fid))
        out += [(b"ICN#", iid, 0x24, None, icon),
                (b"FREF", fid, 0x24, None, fr[:4] + struct.pack(">h", k) + fr[6:])]
    body = sig + struct.pack(">hh", 0, 1)
    for t, m in ((b"ICN#", icns), (b"FREF", frefs)):
        body += t + struct.pack(">h", len(m) - 1) + b"".join(struct.pack(">hh", *e) for e in m)
    return [(b"BNDL", bid, 0x24, None, body),
            (sig, 0, 0x24, None, STAMP + struct.pack(">h", bid))] + out


def volume_apps(app, stub, dirid):
    """desktop()'s list for a floppy: MacExtract at the root (ID 2) and
    every helper in the folder whose catalog ID is `dirid`."""
    return [(app, 2)] + [(mb, dirid) for _n, mb in helpers(stub)]


def desktop(apps, appl=True):
    """The Desktop file, as MacBinary: 'STR ' 0 "Finder 1.0", attribute
    $04, as System 3.0's Finder writes it on a floppy (measured, the same
    entry); 'APPL' 0 listing each application with the catalog ID of its
    folder, in the layout tools/vmac/deskclaim.py measured off System
    6.0.8's (appl_build); and each one's bundle as bundle_copy() files it,
    which System 6.0.8's Finder does on an unlocked floppy and nothing can
    on a locked one. `apps` is [(MacBinary, dirid)], MacExtract first.
    `appl=False` leaves the 'APPL' list out, as on an MFS floppy, where
    neither 3.0's Finder nor 6.0.8's writes one (measured 2026-11-14).
    Type FNDR, creator ERIK, invisible, as the Finder's own."""
    counter = {}

    def nid(t):
        counter[t] = counter.get(t, 999) + 1
        return counter[t]
    ents, copies = [], []
    for mb, dirid in apps:
        h = mb[:128]
        ents.append((h[69:73], dirid, h[2:2 + h[1]]))
        copies += bundle_copy(mb, nid)
    res = [(b"STR ", 0, 0x04, None, b"\nFinder 1.0")]
    if appl:
        res.append((b"APPL", 0, 0x04, None, D.appl_build(ents)))
    res += copies
    h = bytearray(128)
    n = b"Desktop"
    h[1] = len(n)
    h[2:2 + len(n)] = n
    h[65:73] = b"FNDRERIK"
    h[73] = 0x40                                   # invisible ($4000)
    return D.macbin_join(bytes(h), b"", D.rsrc_write(res, 0))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stub", nargs="?", help="the stub build's MacBinary (Stub.bin)")
    ap.add_argument("-o", "--outdir")
    ap.add_argument("--zip")
    ap.add_argument("--desktop")
    ap.add_argument("--dirid", type=int)
    ap.add_argument("--app", help="MacExtract's MacBinary, for --desktop")
    ap.add_argument("--mfs", action="store_true",
                    help="--desktop for the MFS floppy: MacExtract alone, no 'APPL' list")
    a = ap.parse_args()
    stub = open(a.stub, "rb").read()
    if a.desktop:
        app = open(a.app, "rb").read()
        d = desktop([(app, 2)], appl=False) if a.mfs else desktop(volume_apps(app, stub, a.dirid))
        open(a.desktop, "wb").write(d)
        return
    if a.outdir:
        os.makedirs(a.outdir, exist_ok=True)
        for name, mb in helpers(stub):
            open(os.path.join(a.outdir, name + ".bin"), "wb").write(mb)
        print(f"make_helpers: {len(rows())} helpers in {a.outdir}")
    if a.zip:
        write_zip(a.zip, stub)
        print(f"make_helpers: {a.zip}, {os.path.getsize(a.zip)} B")


if __name__ == "__main__":
    main()
