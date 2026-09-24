#!/usr/bin/env python3
"""derive_lzh.py — read every LZH/LHA header here from the FORMAT's own
published description, and say where that description is silent.

The inventory row for `fmt_lzh.c` said the decoders were lhasa's since
2026-09-19 and that what was left was "a header walk" from
`XADLZHParser.m`. The header walk is **published**, and the document
has been in this tree since the first reference fetch:

    reference/lha/header.doc.euc

Masaru Oki's `header.doc`, LHa for UNIX, 2 March 1992, in EUC-JP —
levels 0, 1 and 2 field by field, the extended-header types, the OS
IDs and the method IDs, with part B credited to Yoshizaki's `lhx.doc`.
What it does not describe is level 3 and three quirks of real writers;
those come from **lhasa (ISC)**, which this file's decoders already
do. Neither is XADMaster.

This reader is written from those two and from nothing else. Every
place it needs something the document does not say is marked
**BEYOND THE DOCUMENT** here and in `docs/formats/lzh-header.md`.

    tools/derive_lzh.py [archive ...]        # default: every one here

The check is two-sided. Structurally, a walk whose fields are wrong
derails immediately: each entry's data must end exactly where the next
header begins, and the last must land on the end-of-archive marker or
on EOF. Independently, `build/lhasa/lhasa -lv` lists the same archives,
and its names, sizes and header levels are compared against this
reader's.

Not in `ci.sh`: it needs `reference/` and the fixtures, and it is a
derivation rather than a test. It skips cleanly without either.
"""
import argparse
import glob
import os
import re
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "reference", "lha", "header.doc.euc")
LHASA = os.path.join(ROOT, "build", "lhasa", "lhasa")

# header.doc, section A: the base header, level by level. Offsets are
# from the start of the header; the document gives them as a column of
# field widths and they add up to these.
H_SIZE, H_SUM, H_METHOD, H_PACKED, H_ORIG = 0, 1, 2, 7, 11
H_TIME, H_ATTR, H_LEVEL, H_NAMELEN = 15, 19, 20, 21
L2_CRC, L2_OS, L2_BASE = 21, 23, 24
L3_BASE = 28                    # BEYOND THE DOCUMENT (lhasa)

# Section A.b, "method ID". -lhd- is not in the list: a directory has
# no bytes to compress and every writer here spells it this way.
DIR_METHOD = b"-lhd-"
# Section A.c, "OS ID". 'm' is Mac, and MacLHA is the reason this
# project reads the format at all.
OS_MAC, OS_OS9_68K, OS_UNSET = ord('m'), ord('K'), None


class Walk:
    """One archive's headers, by the document's rules."""

    def __init__(self, blob):
        self.b = blob
        self.entries = []
        self.note = []
        self.names = self.nuls = 0

    def u16(self, at):
        return struct.unpack_from("<H", self.b, at)[0]

    def u32(self, at):
        return struct.unpack_from("<I", self.b, at)[0]

    def ext_chain(self, at, width, stop):
        """The extended-header chain (section B). Each header is
        `1 ext-type`, its payload, then `2 next-header size` — so the
        size read at `at` is of the header that FOLLOWS it, and a zero
        ends the chain. Returns (name, dirname, total bytes consumed).
        Level 3's sizes are 32-bit: BEYOND THE DOCUMENT (lhasa,
        decode_extended_headers)."""
        name = dirn = None
        used = 0
        while at + width <= stop:
            size = self.u32(at) if width == 4 else self.u16(at)
            if size == 0:
                break
            if size < width + 1 or at + size > stop:
                raise ValueError("extended header runs past the header")
            kind = self.b[at + width]
            body = self.b[at + width + 1:at + size]
            if kind == 0x01:            # filename header
                name = body
            elif kind == 0x02:          # dirname header
                dirn = body
            at += size
            used += size
        return name, dirn, used

    def one(self, pos):
        """Returns (entry, next_pos) or None at the end of the archive."""
        if pos >= len(self.b) or self.b[pos] == 0:
            return None                 # end-of-archive marker
        if pos + L2_BASE > len(self.b):
            raise ValueError("header runs past the end of the file")
        level = self.b[pos + H_LEVEL]
        method = bytes(self.b[pos + H_METHOD:pos + H_METHOD + 5])
        packed = self.u32(pos + H_PACKED)
        orig = self.u32(pos + H_ORIG)
        crc = None
        os_id = OS_UNSET
        name = dirn = None

        if level in (0, 1):
            hsize = self.b[pos + H_SIZE] + 2
            nlen = self.b[pos + H_NAMELEN]
            if 22 + nlen + 2 > hsize:
                raise ValueError("name field runs past the header")
            name = bytes(self.b[pos + 22:pos + 22 + nlen])
            # `fmt_lzh.c` ends the name at the first NUL and treats
            # the rest as the entry's comment — XADMaster's rule, which
            # neither the document nor lhasa has. Counted here because
            # a rule with no specimen cannot be graded either way.
            self.names += 1
            if 0 in name:
                self.nuls += 1
                self.note.append("NUL inside the name field: %r" % name)
            crc = self.u16(pos + 22 + nlen)
            # The document's checksum: "1 header sum", the low byte of
            # the sum of everything after it. lhasa checks it; this
            # engine does not, and neither reading changes an entry.
            got = sum(self.b[pos + 2:pos + hsize]) & 0xff
            if got != self.b[pos + H_SUM]:
                self.note.append("level %d header sum %02x, stored %02x"
                                 % (level, got, self.b[pos + H_SUM]))
            end = pos + hsize
            if level == 1:
                os_id = self.b[pos + 24 + nlen]
                # "4 skip size": level 1's packed size counts the
                # extended headers too, so each one moves the data
                # along and shortens the stream. The chain begins at
                # the "next-header size" word that ENDS the base
                # header, which is inside hsize.
                name2, dirn, used = self.ext_chain(pos + 25 + nlen, 2,
                                                   len(self.b))
                if name2 is not None:
                    name = name2
                packed -= used
                end += used
                if packed < 0:
                    raise ValueError("extended headers longer than the data")
        elif level in (2, 3):
            if level == 2:
                hsize = self.u16(pos + H_SIZE)
                os_id = self.b[pos + L2_OS]
                # BEYOND THE DOCUMENT (lhasa, decode_level2_header):
                # LHA for OS-9/68k 2.01 stores the length of the REST
                # of the header, so its level 2 headers are two bytes
                # short.
                if os_id == OS_OS9_68K:
                    hsize += 2
                at = pos + L2_BASE
                width = 2
            else:
                # BEYOND THE DOCUMENT (lhasa, decode_level3_header):
                # a word-size field that is always 4, a 32-bit total
                # header size at 24, and 32-bit chain sizes.
                if self.u16(pos + H_SIZE) != 4:
                    raise ValueError("level 3 word size is not 4")
                hsize = self.u32(pos + 24)
                os_id = self.b[pos + L2_OS]
                at = pos + L3_BASE
                width = 4
            if hsize < L2_BASE or pos + hsize > len(self.b):
                raise ValueError("header size %d is impossible" % hsize)
            crc = self.u16(pos + L2_CRC)
            # Level 2 and 3 keep the chain INSIDE the header, so it
            # moves neither the data offset nor the size.
            name, dirn, _ = self.ext_chain(at, width, pos + hsize)
            end = pos + hsize
        else:
            raise ValueError("header level %d" % level)

        path = b""
        if dirn:
            path = dirn if dirn.endswith(b"\xff") else dirn + b"\xff"
        path += name or b""
        path = path.replace(b"\xff", b"/").replace(b"\\", b"/")
        if method == DIR_METHOD and not path.endswith(b"/"):
            path += b"/"
        return ({"name": path, "level": level, "method": method,
                 "orig": orig, "packed": packed, "crc": crc, "os": os_id,
                 "data": end}, end + packed)

    def run(self):
        pos = 0
        while True:
            got = self.one(pos)
            if got is None:
                break
            ent, pos = got
            self.entries.append(ent)
            if len(self.entries) > 4096:
                raise ValueError("more than 4096 entries")
        if pos > len(self.b):
            raise ValueError("the last entry runs past the end of the file")
        return self.entries


# lhasa's -lv listing puts the name on its own line and the stats on
# the next, and the stats line has no permissions field when the
# archive was not written on a Unix (`[MS-DOS]` in its place). The one
# thing every stats line has is the header level in brackets at the
# end, so that is what identifies it.
LV_STAT = re.compile(rb"\s(\d+)\s+(?:\d+\.\d+%|\*+)\s.*\[(\d)\]\s*$")


def lhasa_list(path):
    """(name, size, level) per entry, from lhasa's own listing."""
    try:
        r = subprocess.run([LHASA, "-lv", path], capture_output=True,
                           timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    out, pending = [], None
    for line in r.stdout.split(b"\n"):
        if line.startswith(b"-----") or line.startswith(b" PERMSSN") \
                or line.startswith(b" Total"):
            continue
        m = LV_STAT.search(line)
        if m:
            if pending is not None:
                out.append((pending, int(m.group(1)), int(m.group(2))))
            pending = None
        elif line.strip():
            pending = line
    return out


def lhasa_normalise(name):
    """What lhasa does to a name for reasons that are not the header's.
    Each is its own function there, and none is in the document:

      `fix_msdos_allcaps`  a name with no lower-case character at all
          is lower-cased whole;
      `collapse_path`      "." and ".." components are removed, so a
          malicious `foo/../../evil.txt` lists as `evil.txt`;
      the listing itself    replaces a byte it will not send to a
          terminal with "?" (`regression/badterm.lzh` is an archive
          whose name is an xterm title-setting escape).

    `unar` does none of the three, and neither does this engine — it is
    the archive's bytes that are compared everywhere else here."""
    out = bytes(c if 0x20 <= c <= 0x7e else ord("?") for c in name)
    if not any(0x61 <= c <= 0x7a for c in out):
        out = out.lower()
    parts = []
    for comp in out.split(b"/"):
        if comp == b".":
            continue
        if comp == b"..":
            if parts:
                parts.pop()
            continue
        parts.append(comp)
    return b"/".join(parts)


def archives(args):
    if args:
        return args
    out = sorted(glob.glob(os.path.join(ROOT, "fixtures", "*.lzh")) +
                 glob.glob(os.path.join(ROOT, "fixtures", "*.lha")))
    for base in ("lhasa/test/archives", "lha"):
        for root, _d, files in os.walk(os.path.join(ROOT, "reference", base)):
            # PMarc and -lhx- are a different family behind the same
            # header shape, and out of scope (OPEN_ITEMS.md part 1).
            if "pmarc" in root:
                continue
            for f in sorted(files):
                if f.lower().endswith((".lzh", ".lha")):
                    out.append(os.path.join(root, f))
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archives", nargs="*")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(DOC):
        print("derive-lzh: no reference/lha/header.doc.euc — run "
              "tools/fetch_references.sh (skipped)")
        return 0
    paths = archives(a.archives)
    if not paths:
        print("derive-lzh: no .lzh here (skipped)")
        return 0
    have_lhasa = os.path.exists(LHASA)
    if not have_lhasa:
        print("derive-lzh: no build/lhasa — names are not cross-checked")

    arcs = ents = checked = bad = unreadable = nolist = lowered = 0
    names = nuls = 0
    levels, methods = {}, {}
    for p in paths:
        with open(p, "rb") as fh:
            blob = fh.read()
        w = Walk(blob)
        try:
            got = w.run()
        except (ValueError, struct.error) as e:
            unreadable += 1
            print("  REFUSED %s: %s" % (os.path.relpath(p, ROOT), e))
            continue
        arcs += 1
        ents += len(got)
        names += w.names
        nuls += w.nuls
        for e in got:
            levels[e["level"]] = levels.get(e["level"], 0) + 1
            methods[e["method"]] = methods.get(e["method"], 0) + 1
        for n in w.note:
            print("  note %s: %s" % (os.path.relpath(p, ROOT), n))
        if not have_lhasa:
            continue
        ref = lhasa_list(p)
        if ref is None:
            continue
        if not ref and got:
            # lhasa's LISTING drops an entry with no filename, and LHa
            # for UNIX 1.14i writes level 0 directory entries whose
            # name length is 0 (`h0_subdir.lzh`: two of those and one
            # real file, which lhasa's -l reports as "0 files"). That
            # is a property of its listing, not of the header, so
            # there is nothing here to compare against.
            nolist += 1
            continue
        checked += 1
        if len(ref) != len(got):
            bad += 1
            print("  DIFFER %s: %d entries, lhasa says %d"
                  % (os.path.relpath(p, ROOT), len(got), len(ref)))
            continue
        for mine, theirs in zip(got, ref):
            # A trailing "/" on a directory is a display convention,
            # and lhasa drops it for the symlinks it spells
            # "name|target" — so it is not compared.
            a_name = mine["name"].rstrip(b"/")
            b_name = theirs[0].rstrip(b"/")
            if a_name != b_name:
                fixed = lhasa_normalise(a_name)
                if fixed == b_name:
                    # A normalisation lhasa applies for its own
                    # reasons, named rather than counted as agreement.
                    lowered += 1
                    a_name = b_name
            if a_name != b_name or mine["level"] != theirs[2] \
                    or (mine["orig"] != theirs[1]
                        and mine["method"] != DIR_METHOD):
                bad += 1
                print("  DIFFER %s: %r %d B level %d, lhasa says %r %d B "
                      "level %d" % (os.path.relpath(p, ROOT), mine["name"],
                                    mine["orig"], mine["level"], theirs[0],
                                    theirs[1], theirs[2]))
        if a.verbose:
            print("  %-56s %3d entries" % (os.path.relpath(p, ROOT), len(got)))

    print("derive-lzh: %d archives walked, %d entries, from header.doc plus "
          "lhasa for level 3" % (arcs, ents))
    print("            levels " + ", ".join("%d:%d" % kv
                                            for kv in sorted(levels.items())))
    print("            methods " + ", ".join(
        "%s:%d" % (k.decode("latin-1"), v)
        for k, v in sorted(methods.items())))
    print("            %d archives cross-checked against lhasa, %d "
          "disagreement(s), %d refused" % (checked, bad, unreadable))
    print("            %d archive(s) lhasa's listing reports as empty, %d "
          "name(s) it normalises" % (nolist, lowered))
    print("            %d level 0/1 name field(s), %d with a NUL in them "
          "(the one rule that is still XADMaster's)" % (names, nuls))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
