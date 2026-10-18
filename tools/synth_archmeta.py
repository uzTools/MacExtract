#!/usr/bin/env python3
"""synth_archmeta.py — archives whose Finder metadata is known, for
tools/run_meta.py's archive lanes (`archive_*` there).

Each builder returns (bytes, want): `want` maps an entry's listed name to
the fields `macextract l --meta` must print for it — finfo, fxinfo
(32 hex digits), backup, ctime, mtime (8 hex digits, Mac seconds, then
`Z` where the format's document makes the date an instant — a Unix time,
a 0x334d date with its GMT offset — and nothing after a wall clock: an
MS-DOS or Macintosh date), lock ('L', 'n'), comment (hex) — with '-'
where the archive states nothing.
The values are built from the layouts' own documents, field by field,
in the WRITING direction; the engine reads them back in the other. Where
a builder starts from a real archive (StuffIt 5, SuperDisk!, Now
Compress), the bytes it changes are the ones the expanders were measured
on (FORMATS.md, *Finder info in the archive*), and what is wanted is
re-read from the copy by a parser that is not the engine's.

What this CANNOT see: whether a real writer puts the same thing in the
same place — that is what the corpus lanes of run_meta.py, against lsar,
and the expander measurements are for. A builder and the reader agreeing
is a check of the reader's arithmetic, not of the format.
"""
import gzip
import io
import os
import struct
import sys
import tarfile
import time
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "vmac"))

MAC_EPOCH = 2082844800


def h(b):
    return b.hex()


def mac_of_unix(t):
    """An instant: `Z` after it (macextract.h, UNC_META_*_UTC)."""
    return "%08x" % (t + MAC_EPOCH) + "Z"


def mac_of_m3(local, gmt):
    """A 0x334d date: with its offset ("local time - UTC", the document's
    *Attributes*), the instant local - offset, marked; without, the
    writer's wall clock as stored."""
    if gmt is None:
        return "%08x" % local
    return "%08x" % ((local - gmt) & 0xFFFFFFFF) + "Z"


def mac_of_dos(y, mo, d, hh, mi, ss):
    """Wall clock as a Mac date, computed with the calendar module rather
    than the engine's own day count."""
    import calendar
    return "%08x" % (calendar.timegm((y, mo, d, hh, mi, ss)) + MAC_EPOCH)


# ------------------------------------------------------------------
# zip: Info-ZIP 0x334d, external attributes, per-file comments, DOS dates
# ------------------------------------------------------------------

def _m3_attribs(fdflags, v, hpos, fldr, fx, crd, mdd, bkd, gmt, path,
                comment):
    """The 0x334d attribute record, little-endian field by field
    (reference/notes/zip_extrafld_infozip.txt, *Attributes*). `fx` is
    (iconID, (r0, r1, r2), script, xflags, cmt, putaway)."""
    icon, res, script, xflags, cmt, putaway = fx
    a = struct.pack("<HhhH", fdflags, v, hpos, fldr)
    a += struct.pack("<HHHHBBHI", icon, res[0], res[1], res[2], script,
                     xflags, cmt, putaway)
    a += bytes([0, 0])                           # FVersNum, ACUser
    a += struct.pack("<III", crd, mdd, bkd)
    if gmt is not None:
        a += struct.pack("<iii", gmt, gmt, gmt)
    a += struct.pack("<H", 0) + path + b"\0" + comment + b"\0"
    return a


def _m3_field(ftype, creator, attribs, gmt):
    flags = 0x0004 | (0 if gmt is not None else 0x0010)   # stored
    body = struct.pack("<IH", len(attribs), flags) + ftype + creator + attribs
    return struct.pack("<HH", 0x334d, len(body)) + body


def _finfo_be(t, c, fdflags, v, hpos, fldr):
    return t + c + struct.pack(">HhhH", fdflags, v, hpos, fldr)


def _fxinfo_be(fx):
    icon, res, script, xflags, cmt, putaway = fx
    return struct.pack(">HHHHBBHI", icon, res[0], res[1], res[2], script,
                       xflags, cmt, putaway)


def zip_meta():
    out = io.BytesIO()
    want = {}
    z = zipfile.ZipFile(out, "w")

    def add(name, data, host, attr, dt, comment=b"", extra=b"", w=None):
        zi = zipfile.ZipInfo(name, dt)
        zi.create_system = host
        zi.external_attr = attr
        zi.comment = comment
        zi.extra = extra
        z.writestr(zi, data)
        want[name.rstrip("/")] = w

    # A MacZip file: everything 0x334d holds, the Finder comment beside a
    # zip per-file comment (the Finder comment wins), dates local.
    fx = (0x1234, (0x0102, 0x0304, 0x0506), 0x81, 0x40, 0x0777, 0x00010203)
    cr, md, bk = 0xB0000001, 0xB0001002, 0xB0002003
    att = _m3_attribs(0x0120, 0x0040, -0x0010, 0x0005, fx, cr, md, bk,
                      -18000, b"HD:mac.txt", b"a Finder comment")
    add("mac.txt", b"MacZip\n", 7, 0x81240001, (2001, 2, 3, 4, 5, 6),
        comment=b"zip comment", extra=_m3_field(b"TEXT", b"ttxt", att, -18000),
        w=dict(finfo=h(_finfo_be(b"TEXT", b"ttxt", 0x0120, 0x40, -0x10, 5)),
               fxinfo=h(_fxinfo_be(fx)), backup=mac_of_m3(bk, -18000),
               ctime=mac_of_m3(cr, -18000), mtime=mac_of_m3(md, -18000),
               lock="L",
               comment=h(b"a Finder comment")))
    # A MacZip folder: the type and creator slots hold its rectangle, no
    # GMT offsets (flag bit 4), a backup date of 0 ("never": unstated).
    fxd = (0xfffb, (0xffc2, 0, 0), 0, 0, 0, 0)
    att = _m3_attribs(0x03f0, 0x007b, 0x0117, 0x0100, fxd, cr, md, 0, None,
                      b"HD:Fold:", b"")
    rect = struct.pack(">hhhh", 0x2f, 0x0c, 0x154, 0x12b)
    add("Fold/", b"", 7, 0x41ff0010, (2001, 2, 3, 4, 5, 6),
        extra=_m3_field(rect[:4], rect[4:], att, None),
        w=dict(finfo=h(rect + struct.pack(">HhhH", 0x03f0, 0x7b, 0x117,
                                          0x100)),
               fxinfo=h(_fxinfo_be(fxd)), backup="-",
               ctime=mac_of_m3(cr, None), mtime=mac_of_m3(md, None),
               lock="n", comment="-"))
    # Foreign permissions, and DOS dates where no Mac field states one.
    for name, host, attr, lock in (
            ("unix-ro", 3, (0o100444 << 16), "L"),
            ("unix-rw", 3, (0o100644 << 16), "n"),
            ("unix-zero-dosro", 3, 0x01, "L"),        # high half 0: the DOS bit
            ("dos-ro", 0, 0x21, "L"),
            ("dos-rw", 0, 0x20, "n"),
            ("ntfs-ro", 11, 0x01, "L"),
            ("mac-rw", 7, 0x81b60000, "n"),
            ("amiga", 1, 0x01, "-")):
        add(name, b"x", host, attr, (1999, 12, 31, 23, 59, 58),
            comment=b"per-file " + name.encode(),
            w=dict(finfo="-", fxinfo="-", backup="-", ctime="-",
                   mtime=mac_of_dos(1999, 12, 31, 23, 59, 58), lock=lock,
                   comment=h(b"per-file " + name.encode())))
    z.close()
    return out.getvalue(), want


# ------------------------------------------------------------------
# tar: mode, mtime, a pax mtime and comment
# ------------------------------------------------------------------

def tar_meta():
    out = io.BytesIO()
    want = {}
    with tarfile.open(fileobj=out, mode="w", format=tarfile.PAX_FORMAT) as t:
        def add(name, mode, mtime, pax=None, w=None):
            ti = tarfile.TarInfo(name)
            ti.size, ti.mode, ti.mtime = 1, mode, mtime
            if pax:
                ti.pax_headers = pax
            t.addfile(ti, io.BytesIO(b"z"))
            want[name] = w
        add("ro", 0o444, 981173106,
            w=dict(lock="L", mtime=mac_of_unix(981173106), comment="-",
                   ctime="-", finfo="-"))
        add("rw", 0o644, 1000000000,
            w=dict(lock="n", mtime=mac_of_unix(1000000000), comment="-",
                   ctime="-", finfo="-"))
        # The pax record wins over the header's own mtime, fraction and all.
        add("pax", 0o600, 1000000000,
            pax={"mtime": "1200000000.75", "comment": "a pax comment"},
            w=dict(lock="n", mtime=mac_of_unix(1200000000),
                   comment=h(b"a pax comment"), ctime="-", finfo="-"))
        # And applies to that member only.
        add("after", 0o200, 1100000000,
            w=dict(lock="n", mtime=mac_of_unix(1100000000), comment="-",
                   ctime="-", finfo="-"))
    return out.getvalue(), want


# ------------------------------------------------------------------
# gzip: MTIME and FCOMMENT (RFC 1952, 2.3.1)
# ------------------------------------------------------------------

def gzip_meta(name="member"):
    data = b"gzip metadata\n"
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = co.compress(data) + co.flush()
    mtime = 1234567890
    hdr = (b"\x1f\x8b\x08" + bytes([0x08 | 0x10]) + struct.pack("<I", mtime)
           + b"\x00\x03" + name.encode() + b"\0" + b"a gzip comment\0")
    blob = hdr + body + struct.pack("<II", zlib.crc32(data), len(data))
    return blob, {name: dict(mtime=mac_of_unix(mtime),
                             comment=h(b"a gzip comment"), lock="-",
                             finfo="-", ctime="-")}


# ------------------------------------------------------------------
# Private File: FInfo @260, FXInfo @276 of the decrypted record
# ------------------------------------------------------------------

def pf_meta():
    import synth_pf
    fi = b"TEXTttxt" + struct.pack(">HhhH", 0x0120, 0x30, 0x48, 0)
    fx = struct.pack(">HHHHBBHI", 0x0011, 0x2233, 0x4455, 0x6677, 0x81, 0x00,
                     0x0102, 0x03040506)
    blob = synth_pf.encode("Meta", b"TEXT", b"ttxt", b"pf data\n", b"",
                           b"swordfish", finfo=fi, fxinfo=fx)
    return blob, {"Meta": dict(finfo=h(fi), fxinfo=h(fx), lock="-",
                               backup="-")}


# ------------------------------------------------------------------
# ArcMac: the whole FInfo at 34..49, the PC header's DOS date
# ------------------------------------------------------------------

def arcmac_meta():
    import synth_arc
    data, rsrc = b"ArcMac data fork\n", b"rsrc"
    both = data + rsrc
    fi = b"TEXTttxt" + struct.pack(">HhhH", 0x0100, 0x0012, 0x0080, 0x0003)
    name = b"Forks"
    dosdate = ((2003 - 1980) << 9) | (7 << 5) | 14
    dostime = (13 << 11) | (37 << 5) | (42 // 2)
    hdr = (b"\x1b\x02" + name.ljust(31, b"\0") + b"\0" + fi +
           struct.pack("<II", len(data), len(rsrc)) + b"\0" +
           b"\x1a\x02" + b"FORKS".ljust(13, b"\0") +
           struct.pack("<IHHHI", len(both), dosdate, dostime,
                       synth_arc.crc16(both), len(both)))
    assert len(hdr) == 88
    blob = hdr + both + b"\x1b\x00" + bytes(86)
    return blob, {"Forks": dict(finfo=h(fi), fxinfo="-",
                                mtime=mac_of_dos(2003, 7, 14, 13, 37, 42),
                                lock="-")}


# ------------------------------------------------------------------
# StuffIt 5: the second block's sentinels, with and without its CRC
# ------------------------------------------------------------------

def sit5_meta(path, break_crc=False):
    """A sentinel copy of a StuffIt 5 archive (sitmeta.sit5_sentinel, the
    copy Expander 5.5 was measured on), and what each entry must state:
    its second block's b+4..35 when the block's CRC holds, nothing when
    `break_crc` spoils it. Names are read back through sitmeta's own
    walker, which is not the engine's."""
    import sitmeta
    blob = bytearray(sitmeta.sit5_sentinel(open(path, "rb").read()))
    want = {}
    for e in sitmeta.parse_sit5(bytes(blob)):
        at = e["off"] + e["b2"]
        if break_crc:
            blob[at + 2] ^= 0x5A
        name = "/".join(x.decode("mac-roman") for x in e["path"])
        blk = bytes(blob[at:at + 36])
        fi = bytearray(blk[4:20])
        if e["kind"] == "dir":
            fi[9] &= 0xFE        # frFlags less 0x0001, as Expander 5.5 wrote
        want[name] = (dict(finfo="-", fxinfo="-") if break_crc else
                      dict(finfo=h(bytes(fi)), fxinfo=h(blk[20:36])))
    return bytes(blob), want


# ------------------------------------------------------------------
# Now Compress: +38..53, +62, +66..81 of every record
# ------------------------------------------------------------------

def now_meta():
    """nowmeta.build()'s sentinel archive — the one Now QuickFiler's
    Dearchive was measured on — and its records read off it directly:
    24-byte file header, then 110-byte records in pre-order
    (docs/formats/now-compress.md, *The archive layer*)."""
    import nowmeta
    blob = nowmeta.build()
    n = struct.unpack(">I", blob[8:12])[0]
    want, stack = {}, []
    for i in range(n):
        r = blob[24 + 110 * i:24 + 110 * (i + 1)]
        name = r[1:1 + r[0]].decode("mac-roman")
        while stack and stack[-1][1] == 0:
            stack.pop()
        path = "/".join([s[0] for s in stack] + [name])
        if stack:
            stack[-1][1] -= 1
        want[path] = dict(finfo=h(r[38:54]), fxinfo=h(r[66:82]),
                          backup=h(r[62:66]))
        if r[37] & 0x10:
            stack.append([name, struct.unpack(">H", r[82:84])[0]])
    return blob, want


# ------------------------------------------------------------------
# SuperDisk!: a file's +18..21, a folder's 20 bytes
# ------------------------------------------------------------------

def sd_meta(fixture):
    """sdmeta.build()'s stream — the one the self-extractor was measured
    on — over the corpus's own SuperDisk! stream."""
    import sdmeta
    blob, finfo = sdmeta.build(open(fixture, "rb").read())
    d = sdmeta.DIRINFO
    fi_in = finfo[8:18] + sdmeta.LOC_IN + b"\0\0"
    fi_root = finfo[8:18] + sdmeta.LOC_ROOT + b"\0\0"
    return blob, {
        # The extractor's flags, less 0x0001 (FORMATS.md).
        "SentFold": dict(finfo=h(d[:9] + bytes([d[9] & 0xFE]) + d[10:16]),
                         fxinfo=h(d[16:20] + bytes(12))),
        "SentFold/inner.txt": dict(finfo=h(fi_in), fxinfo="-"),
        "outer.txt": dict(finfo=h(fi_root), fxinfo="-"),
    }
