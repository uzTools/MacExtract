#!/usr/bin/env python3
"""synth_macosx.py — archives laid out as Mac OS X writes them, with
AppleDouble sidecars whose every value is known by construction.

    tools/synth_macosx.py --kind zip -o fixtures/synth-macosx.zip
    tools/synth_macosx.py --kind tar -o fixtures/synth-macosx.tar
    tools/synth_macosx.py --kind zip-edge -o fixtures/synth-macosx-edge.zip
    tools/synth_macosx.py --kind tar-edge -o fixtures/synth-macosx-edge.tar
    tools/synth_macosx.py --describe zip

The archives are written by Info-ZIP zip and GNU tar (`zip -X`, `tar
--format=ustar`, fixed times, as tools/synth_exo.py), from a tree on disk
whose sidecars are files like any other — which is exactly what Mac OS X
hands those programs' own ports:

  zip  the Finder's layout (measured on `Aqua_Candy_Two.zip`, a Finder
       zip of 2006): `dir/name`, then the `__MACOSX/...` folder records
       not yet written, then `__MACOSX/dir/._name`. Departures, each a
       case: `Meta`'s sidecar comes BEFORE its file, `Far`'s at the very
       end, `Ghost`'s names no file, `._NotAD` is a file named like a
       sidecar that is not AppleDouble.
  tar  bsdtar's layout: `dir/._name` immediately before `dir/name`, a
       folder's too (reference/notes/libarchive_write_set_format_pax.c,
       archive_write_pax_header). `Ghost` again names nothing.

The sidecar bodies follow the writer: copyfile's two entries, Finder info
at 50 (32 bytes, then two of padding and the extended-attribute block,
counted in entry 9's length) and the resource fork after it
(reference/notes/copyfile.c, copyfile_pack). `Meta`'s is the RFC 1740
shape instead — entries 9, 4, 8, 10 and 2 — the one other writers of the
same file use, so that every entry the engine reads is exercised.

`--describe` prints, per name the engine must emit, the fields run_meta.py
holds it to; the absent names are the ones it must NOT emit.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synth_as import empty_rsrc, EPOCH_2000  # noqa: E402

MTIME = "199001010000"


def rsrc(tag):
    """An empty resource fork whose application area names the file."""
    f = bytearray(empty_rsrc())
    t = ("Resource fork of %s." % tag).encode().ljust(128, b"\0")
    f[128:256] = t
    return bytes(f)


def copyfile_sidecar(finfo, fork, xattrs=()):
    """copyfile's layout: entry 9 at 50, entry 2 after the attributes."""
    attrs = b""
    if xattrs:
        # The ATTR header (copyfile.c, attr_header_t after the AppleDouble
        # header): magic, debug_tag, total_size, data_start, data_length,
        # three reserved words, flags, num_attrs — then 4-aligned entries.
        ents, data = b"", b""
        start_ents = 50 + 32 + 2 + 36
        elen = sum((11 + len(n) + 1 + 3) & ~3 for n, _ in xattrs)
        dstart = start_ents + elen
        off = dstart
        for n, v in xattrs:
            nb = n.encode() + b"\0"
            e = struct.pack(">IIHB", off, len(v), 0, len(nb)) + nb
            ents += e + b"\0" * (((11 + len(nb) + 3) & ~3) - len(e))
            data += v
            off += len(v)
        total = dstart + len(data)
        attrs = b"\0\0" + struct.pack(">4sIIIIIIIHH", b"ATTR", 0, total,
                                      dstart, len(data), 0, 0, 0, 0,
                                      len(xattrs)) + ents + data
    flen = 32 + len(attrs)
    roff = 50 + flen
    hdr = struct.pack(">II16sH", 0x00051607, 0x00020000, b"Mac OS X        ",
                      2)
    hdr += struct.pack(">III", 9, 50, flen) + struct.pack(">III", 2, roff,
                                                          len(fork))
    return hdr + finfo + attrs + fork


def rfc_sidecar(entries):
    """RFC 1740 appendix A: header, table, then the entries in order."""
    hdr = struct.pack(">II16sH", 0x00051607, 0x00020000, b"\0" * 16,
                      len(entries))
    off = 26 + 12 * len(entries)
    tab, body = b"", b""
    for eid, data in entries:
        tab += struct.pack(">III", eid, off + len(body), len(data))
        body += data
    return hdr + tab + body


def finfo(t, c, flags, v, h, fldr=0, fx=b"\0" * 16):
    return t + c + struct.pack(">HhhH", flags, v, h, fldr) + fx


DOC_FX = struct.pack(">H", 0x0102) + b"\0" * 6 + b"\x00\x00" \
    + struct.pack(">HI", 0, 0)
DINFO = struct.pack(">hhhhHhhH", 40, 30, 240, 330, 0x0100, 90, 120, 0x0100)
DXINFO = struct.pack(">hhI", -3, -5, 0) + b"\0\0" + struct.pack(">HI", 0, 0)
META_DATES = (0x12345678, 0x12345F00, 0x13000000, 0x80000000)
COMMENT = b"A Get Info comment, in a sidecar's entry 4."


def files():
    """(path in the tree, bytes) for the data files, and the sidecars."""
    doc = b"The data fork of Doc.\r" * 40
    data = {
        "Folder/Doc": doc,
        "Folder/Icon": b"",
        "Folder/Meta": b"Meta's data fork.\r" * 12,
        "Folder/Far": b"Far's data fork.\r" * 9,
        "Folder/Zero": b"Zero's data fork.\r" * 5,
        "Folder/NotAD": b"NotAD's data fork.\r" * 5,
    }
    side = {
        "Folder/Doc": copyfile_sidecar(
            finfo(b"TEXT", b"ttxt", 0x0120, 0x50, 0x64, 0, DOC_FX),
            rsrc("Doc"), [("com.apple.metadata:kMDItemWhereFroms",
                           b"bplist00\xa0\x08\0\0\0\0\0\0\x01\x01\0\0\0\0"
                           b"\0\0\0\x01\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\x09")]),
        "Folder/Icon": copyfile_sidecar(
            finfo(b"Icon", b"MACS", 0x4400, 0, 0), rsrc("Icon")),
        "Folder/Meta": rfc_sidecar([
            (9, finfo(b"APPL", b"MEta", 0x2000, 0x30, 0x40, 0,
                      struct.pack(">H", 0x0201) + b"\0" * 14)),
            (4, COMMENT),
            (8, struct.pack(">IIII", *META_DATES)),
            (10, b"\0\0\0\x01"),
            (2, rsrc("Meta")),
        ]),
        "Folder/Far": copyfile_sidecar(
            finfo(b"ttro", b"ttxt", 0x0000, 0x10, 0x20), rsrc("Far")),
        "Folder/Zero": copyfile_sidecar(b"\0" * 32, b""),
        "Folder": copyfile_sidecar(DINFO + DXINFO, b""),
        "Folder/Ghost": copyfile_sidecar(
            finfo(b"TEXT", b"ghst", 0, 0, 0), rsrc("Ghost")),
    }
    return data, side


def sidename(path, macosx):
    d, _, leaf = path.rpartition("/")
    n = (d + "/" if d else "") + "._" + leaf
    return "__MACOSX/" + n if macosx else n


def order(kind):
    """The archive's member order, as (name, is_dir). `zip` and `tar` are
    what `unar` can grade too; the `-edge` kinds hold the cases its
    manifests cannot state (make_manifests.py refuses a name starting
    "._", and every case there leaves one): a sidecar far from its file,
    one naming no file, a file named like a sidecar that is not one."""
    if kind == "zip":
        m = lambda p: sidename(p, True)
        return [("Folder/", 1), ("__MACOSX/", 1), (m("Folder"), 0),
                ("Folder/Doc", 0), ("__MACOSX/Folder/", 1),
                (m("Folder/Doc"), 0),
                ("Folder/Icon", 0), (m("Folder/Icon"), 0),
                (m("Folder/Meta"), 0), ("Folder/Meta", 0),
                ("Folder/Zero", 0), (m("Folder/Zero"), 0)]
    if kind == "zip-edge":
        m = lambda p: sidename(p, True)
        return [("Folder/", 1), ("Folder/Far", 0),
                ("Folder/._NotAD", 0), ("Folder/NotAD", 0),
                ("__MACOSX/", 1), ("__MACOSX/Folder/", 1),
                (m("Folder/Ghost"), 0), (m("Folder/Far"), 0)]
    s = lambda p: sidename(p, False)
    if kind == "tar":
        return [(s("Folder"), 0), ("Folder/", 1),
                (s("Folder/Doc"), 0), ("Folder/Doc", 0),
                (s("Folder/Icon"), 0), ("Folder/Icon", 0),
                (s("Folder/Meta"), 0), ("Folder/Meta", 0),
                (s("Folder/Zero"), 0), ("Folder/Zero", 0)]
    # tar-edge: a sidecar AFTER its file is not bsdtar's order and is not
    # paired here (unc_sidecar.c), so Far's comes out as itself.
    return [("Folder/", 1), ("Folder/._NotAD", 0), ("Folder/NotAD", 0),
            (s("Folder/Ghost"), 0), ("Folder/Far", 0), (s("Folder/Far"), 0)]


def build(kind, out):
    data, side = files()
    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, "t")
        names = order(kind)
        for n, isdir in names:
            p = os.path.join(tree, n)
            if isdir:
                os.makedirs(p, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(p), exist_ok=True)
            leaf = os.path.basename(n)
            if n == "Folder/._NotAD":
                body = b"Not AppleDouble: a file whose name starts ._\n"
            elif leaf.startswith("._"):
                tgt = n[len("__MACOSX/"):] if n.startswith("__MACOSX/") \
                    else n
                d, _, l = tgt.rpartition("/")
                body = side[(d + "/" if d else "") + l[2:]]
            else:
                body = data[n]
            with open(p, "wb") as f:
                f.write(body)
        for base, dirs, fs in os.walk(tree):
            for x in dirs + fs:
                subprocess.run(["touch", "-t", MTIME, os.path.join(base, x)],
                               check=True, env=dict(os.environ, TZ="UTC"))
        env = dict(os.environ, TZ="UTC")
        lst = [n for n, _ in names]
        arc = os.path.join(tmp, "arc")
        if kind.startswith("zip"):
            # The folder records go in by name, where the list puts them:
            # the Finder writes them, `zip -r` would write them sorted.
            subprocess.run(["zip", "-X", "-q", "-9", arc + ".zip", "-@"],
                           cwd=tree, env=env, check=True,
                           input="\n".join(lst).encode())
            shutil.move(arc + ".zip", out)
        else:
            subprocess.run(["tar", "--format=ustar", "--owner=0", "--group=0",
                            "--numeric-owner", "--no-recursion",
                            "--mtime=1990-01-01 00:00:00 UTC",
                            "-cf", arc + ".tar", "-T", "-"], cwd=tree,
                           env=env, check=True,
                           input="\n".join(lst).encode())
            shutil.move(arc + ".tar", out)


def describe(kind):
    """{emitted name: fields}, and the names that must not be emitted."""
    data, side = files()
    sha = lambda b: hashlib.sha256(b).hexdigest()
    want = {}
    names = [n.rstrip("/") for n, _ in order(kind)]

    # The lock: every member is written mode 0644 or 0755, and a mode with
    # owner write is "not locked" (the zip and tar readers state it, since
    # 2026-10-17); Meta's sidecar locks it.
    def ent(p, fi=None, fx=None, rs=b"", lock="n", backup="-", comment="-"):
        want[p] = dict(finfo=fi.hex() if fi else "-",
                       fxinfo=fx.hex() if fx else "-", lock=lock,
                       backup=backup, comment=comment,
                       rsrc=sha(rs), rsrc_size=len(rs))

    def ad(p):
        b = side[p]
        roff, rlen = struct.unpack(">II", b[42:50])
        return b[50:66], b[66:82], b[roff:roff + rlen]

    for p in ("Folder/Doc", "Folder/Icon"):
        if p in names:
            ent(p, *ad(p))
    if kind == "zip-edge":
        # Far from its file, and paired all the same: a zip's directory
        # can be searched (src/unc_sidecar.c).
        ent("Folder/Far", *ad("Folder/Far"))
    elif kind == "tar-edge":
        # AFTER its file, which is not bsdtar's order: out as itself.
        ent("Folder/Far")
        ent(sidename("Folder/Far", False))
    if "Folder/Meta" in names:
        ent("Folder/Meta",
            finfo(b"APPL", b"MEta", 0x2000, 0x30, 0x40)[:16],
            struct.pack(">H", 0x0201) + b"\0" * 14, rsrc("Meta"), lock="L",
            # GMT (RFC 1740), so `l --meta` marks it Z.
            backup="%08x" % ((META_DATES[2] + EPOCH_2000) & 0xFFFFFFFF) + "Z",
            comment=COMMENT.hex())
    if "Folder/Zero" in names:
        ent("Folder/Zero")
    if "Folder/NotAD" in names:
        ent("Folder/NotAD")
        ent("Folder/._NotAD")
    fi, fx, _ = ad("Folder")
    if kind in ("zip", "tar"):
        want["Folder"] = dict(finfo=fi.hex(), fxinfo=fx.hex(), lock="n",
                              backup="-", comment="-")
    else:
        want["Folder"] = dict(finfo="-", fxinfo="-", lock="n", backup="-",
                              comment="-")
        ent(sidename("Folder/Ghost", kind == "zip-edge"))
    absent = [n for n in names if n not in want]
    return {"emit": want, "absent": absent}


KINDS = ("zip", "tar", "zip-edge", "tar-edge")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", choices=KINDS)
    ap.add_argument("-o", "--output")
    ap.add_argument("--describe", choices=KINDS)
    a = ap.parse_args()
    if a.describe:
        json.dump(describe(a.describe), sys.stdout, indent=1, sort_keys=True)
        print()
        return 0
    if not a.kind or not a.output:
        ap.error("--kind and -o, or --describe")
    build(a.kind, os.path.abspath(a.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
