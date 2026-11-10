#!/usr/bin/env python3
"""make_helpers.py — every helper companion/helpers.tsv lists, from one stub build.

    python3 companion/make_helpers.py build/stub/Stub.bin -o DIR
    python3 companion/make_helpers.py build/stub/Stub.bin --zip OUT.zip
    python3 companion/make_helpers.py --desktop OUT.bin --dirid N

Writes DIR/<name>.bin, one MacBinary per row: the row's creator and types
stamped onto the build by make_stub.stamp, named in its header as the row
names it; tools/make_dist.sh puts them in the "MacExtract Helpers" folder of
both disk images. --zip writes the same seventeen as ONE download that
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
"MacExtract Helpers" folder's catalog ID.
"""
import argparse, os, sys, zipfile

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


def desktop(dirid):
    """The Desktop file, as MacBinary: what System 3.0's Finder writes on a
    floppy ('STR ' 0, "Finder 1.0", attribute $04; measured, the same
    entry), and 'APPL' 0 listing MacExtract at the root (ID 2) and every
    helper in folder `dirid`, in the layout tools/vmac/deskclaim.py measured
    off System 6.0.8's (appl_build). Type FNDR, creator ERIK, invisible, as
    the Finder's own."""
    ents = [(b"MExt", 2, b"MacExtract")] + [
        (creator, dirid, name.encode("mac_roman")) for creator, name, _t in rows()]
    res = [(b"STR ", 0, 0x04, None, b"\nFinder 1.0"),
           (b"APPL", 0, 0, None, D.appl_build(ents))]
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
    a = ap.parse_args()
    if a.desktop:
        open(a.desktop, "wb").write(desktop(a.dirid))
        return
    stub = open(a.stub, "rb").read()
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
