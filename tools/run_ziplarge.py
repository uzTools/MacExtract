#!/usr/bin/env python3
"""run_ziplarge.py — zips with more entries than a 16-bit count can hold.

A zip's end-of-central-directory record counts its entries in 16 bits.
Past 65,535 the real count lives in a Zip64 record, and a reader that
trusts the 16-bit field does not fail: it walks 65,535 entries and
reports success, silently dropping the rest. That is what this checks,
and it is why the archives here are generated rather than harvested —
nothing in the corpus is that large.

Graded three ways, none of them our own output:

  CPython's `zipfile`  wrote the archives, and its `namelist()` is the
                       count that was intended.
  `lsar`               The Unarchiver, an independent reader, over the
                       same file. Skipped if it is not installed.
  the boundary itself  65,535 entries (no Zip64 record) and 65,536
                       (one) are both built, so a reader that ignores
                       Zip64 passes the first and fails the second.

Also checked: a Zip64 locator whose record sits past 4 GB is refused
rather than truncated to something addressable, and a locator whose
record signature does not match falls back to the 16-bit count instead
of erroring — XADMaster's behaviour, which fmt_exo.c follows.

The other Zip64 structure is per ENTRY, and it does not wait for 4 GB:
a central-directory record whose local-header offset passes 2 GB carries
0xFFFFFFFF with the real offset in extra field 0x0001, which is what
CPython's `zipfile` writes (its ZIP64_LIMIT is 2**31-1) and what every
entry behind the boundary in a 2-4 GB archive looks like. `offsets.zip`
below holds entries on both sides of that boundary in one subject,
sparse, so it costs a few kilobytes of disk; before 2026-08-27 every
entry past it failed as UNC_ERR_CORRUPT (BLOCKERS.md).

What this CANNOT see: anything about archives that are actually larger
than 4 GB — the subject here is 2 GB of hole and a handful of real
entries. The over-4-GB refusals are checked synthetically instead, by
setting a high half nothing can address. The size limits themselves are
measured separately (FORMATS.md, *Size limits*).
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib


ZIP64_LIMIT = (1 << 31) - 1     # CPython's, and the boundary tested here


def sparse_ok(tmp):
    q = os.path.join(tmp, "probe")
    with open(q, "wb") as f:
        f.truncate(64 * 1024 * 1024)
    blocks = os.stat(q).st_blocks
    os.remove(q)
    return blocks * 512 < 1024 * 1024


def crc_of_zeros(n):
    """CRC-32 of n zero bytes, without ever holding them."""
    chunk = bytes(1024 * 1024)
    crc = 0
    while n > 0:
        take = min(n, len(chunk))
        crc = zlib.crc32(chunk[:take], crc)
        n -= take
    return crc & 0xFFFFFFFF


def build_offsets(path, hole, tail, escapes=None):
    """A stored zip written by hand, so that one entry's data can be a
    HOLE and the entries behind it land past a chosen offset.

    The first entry is `hole` bytes of zeros; `tail` is [(name, bytes)]
    behind it. A central-directory record whose local-header offset is
    past ZIP64_LIMIT is written the way CPython's zipfile writes it:
    0xFFFFFFFF in the record, the real value in extra field 0x0001.

    `escapes` forces that escape where a writer would not have used one:
    {name: {"off": high_half, "size": high_half}}. A high half of 0 is an
    archive this engine can address through the escape; anything else is
    one it cannot, and must be refused per entry.

    Source for the layouts: PKWARE APPNOTE 4.3.7 (local header), 4.3.12
    (central directory), 4.3.14 and 4.3.15 (Zip64 end of central
    directory record and locator), 4.5.3 (the Zip64 extra field) — the
    same sections fmt_exo.c reads.
    """
    escapes = escapes or {}
    entries = []                       # (name, crc, size, offset)
    with open(path, "wb") as f:
        def put(name, data, size=0, crc=0):
            off = f.tell()
            n = name.encode()
            if data is not None:
                size, crc = len(data), zlib.crc32(data) & 0xFFFFFFFF
            f.write(struct.pack("<IHHHHHIIIHH", 0x04034b50, 20, 0, 0,
                                0, 0, crc, size, size, len(n), 0))
            f.write(n)
            if data is None:
                f.truncate(f.tell() + size)      # the hole
                f.seek(0, os.SEEK_END)
            else:
                f.write(data)
            entries.append((n, crc, size, off))

        put("hole.bin", None, size=hole, crc=crc_of_zeros(hole))
        for name, data in tail:
            put(name, data)

        cdoffs = f.tell()
        for n, crc, size, off in entries:
            esc = escapes.get(n.decode(), {})
            z64 = b""
            cdsz, cdoff = size, off
            # Order is fixed by 4.5.3: uncompressed size, compressed
            # size, local-header offset — and only what is escaped.
            if "size" in esc:
                z64 += struct.pack("<II", size, esc["size"]) * 2
                cdsz = 0xFFFFFFFF
            if "off" in esc or off > ZIP64_LIMIT:
                z64 += struct.pack("<II", off, esc.get("off", 0))
                cdoff = 0xFFFFFFFF
            extra = struct.pack("<HH", 0x0001, len(z64)) + z64 if z64 else b""
            f.write(struct.pack("<IHHHHHHIIIHHHHHII", 0x02014b50, 20, 20,
                                0, 0, 0, 0, crc, cdsz, cdsz, len(n),
                                len(extra), 0, 0, 0, 0, cdoff))
            f.write(n)
            f.write(extra)
        cdsize = f.tell() - cdoffs
        nent = len(entries)
        if cdoffs > ZIP64_LIMIT:
            rec = f.tell()
            f.write(struct.pack("<IQHHIIQQQQ", 0x06064b50, 44, 45, 45,
                                0, 0, nent, nent, cdsize, cdoffs))
            f.write(struct.pack("<IIQI", 0x07064b50, 0, rec, 1))
            cdoffs = 0xFFFFFFFF
        f.write(struct.pack("<IHHHHIIH", 0x06054b50, 0, 0, nent, nent,
                            cdsize, cdoffs, 0))
    return dict((n.decode(), off) for n, _, _, off in entries)


def entry_failures(macextract, path):
    """{name: message} for every entry `t` did not verify, and the exit
    code. A name that is not a key verified."""
    r = subprocess.run([macextract, "t", path], capture_output=True)
    bad = {}
    for line in r.stderr.decode("utf-8", "replace").splitlines():
        if line.startswith("macextract: ") and line.count(": ") >= 2:
            _, name, msg = line.split(": ", 2)
            bad[name] = msg
    return bad, r.returncode


def build(path, n):
    """A stored zip of n one-byte entries. Past 65,535 CPython writes the
    Zip64 record; below it, it does not."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        for i in range(n):
            z.writestr("f%06d.txt" % i, b"x")


def ours_list(macextract, path):
    """Entry names as our CLI lists them, or None if it failed."""
    r = subprocess.run([macextract, "l", path], capture_output=True)
    if r.returncode != 0:
        return None
    names = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split(None, 4)
        if len(parts) == 5 and parts[0] in ("f", "d"):
            names.append(parts[4])
    return names


def lsar_count(path):
    if not shutil.which("lsar"):
        return None
    r = subprocess.run(["lsar", path], capture_output=True)
    if r.returncode != 0:
        return None
    return len(r.stdout.decode("utf-8", "replace").splitlines()) - 1


def check_count(macextract, path, want, label, problems):
    got = ours_list(macextract, path)
    if got is None:
        problems.append("%s: listing failed, expected %d entries" % (label, want))
        return
    if len(got) != want:
        problems.append("%s: listed %d entries, wanted %d" % (label, len(got), want))
        return
    second = lsar_count(path)
    if second is not None and second != want:
        problems.append("%s: lsar says %d entries, zipfile says %d"
                        % (label, second, want))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract", default="build/macextract")
    args = ap.parse_args()

    if not os.path.exists(args.macextract):
        print("ziplarge: no CLI at %s" % args.macextract)
        return 1

    problems = []
    ran = 0
    tmp = tempfile.mkdtemp()
    try:
        # The boundary, from both sides. 65,535 needs no Zip64 record;
        # 65,536 does, and is the case that used to come back short.
        for n in (65535, 65536):
            p = os.path.join(tmp, "n%d.zip" % n)
            build(p, n)
            want = len(zipfile.ZipFile(p).namelist())
            if want != n:                     # the generator itself
                problems.append("n%d.zip: zipfile wrote %d entries" % (n, want))
            check_count(args.macextract, p, n, "n%d.zip" % n, problems)
            ran += 1

        # An ordinary small file that carries Zip64 structures anyway:
        # extraction must be unaffected.
        p = os.path.join(tmp, "small64.zip")
        payload = b"hello from a zip64 container\n" * 10
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            with z.open(zipfile.ZipInfo("hello.txt"), "w", force_zip64=True) as f:
                f.write(payload)
        out = os.path.join(tmp, "out")
        os.mkdir(out)
        r = subprocess.run([args.macextract, "x", "-o", out, p],
                           capture_output=True)
        got = os.path.join(out, "hello.txt")
        if r.returncode != 0 or not os.path.exists(got):
            problems.append("small64.zip: forced-Zip64 file did not extract")
        elif open(got, "rb").read() != payload:
            problems.append("small64.zip: extracted bytes differ")
        ran += 1

        # A locator whose record sits past 4 GB is out of reach: refuse,
        # do not truncate the offset into something addressable.
        p = os.path.join(tmp, "far64.zip")
        build(p, 65536)
        raw = bytearray(open(p, "rb").read())
        loc = raw.rfind(b"PK\x06\x07")
        if loc < 0:
            problems.append("far64.zip: no Zip64 locator to edit")
        else:
            raw[loc + 12:loc + 16] = struct.pack("<I", 1)   # offset high word
            open(p, "wb").write(bytes(raw))
            r = subprocess.run([args.macextract, "l", p], capture_output=True)
            if r.returncode == 0:
                problems.append("far64.zip: a record past 4 GB was accepted")
        ran += 1

        # A locator pointing at something that is not a Zip64 record:
        # fall back to the 16-bit count rather than failing the archive.
        p = os.path.join(tmp, "nosig64.zip")
        build(p, 65536)
        raw = bytearray(open(p, "rb").read())
        rec = raw.rfind(b"PK\x06\x06")
        if rec < 0:
            problems.append("nosig64.zip: no Zip64 record to edit")
        else:
            raw[rec:rec + 4] = b"PK\x06\x05"
            open(p, "wb").write(bytes(raw))
            got = ours_list(args.macextract, p)
            if got is None or len(got) != 65535:
                problems.append("nosig64.zip: expected the 16-bit count "
                                "(65535), got %s"
                                % ("failure" if got is None else len(got)))
        ran += 1

        # The per-ENTRY escape, on both sides of the 2 GB boundary in one
        # subject: a 2 GB hole, one entry just under it, three past it.
        # CPython writes the escape past ZIP64_LIMIT, so everything
        # behind the hole is what a 2-4 GB archive from any of its
        # writers looks like — and every one of those entries failed as
        # UNC_ERR_CORRUPT until 2026-08-27.
        if not sparse_ok(tmp):
            print("ziplarge: offset-boundary cases skipped "
                  "(%s has no sparse files)" % tmp)
        else:
            p = os.path.join(tmp, "offsets.zip")
            under = b"the last entry that needs no Zip64 field\n" * 5
            tail = [("under.txt", under)] + \
                   [("over%d.txt" % i, b"past two gigabytes: %d\n" % i)
                    for i in (1, 2, 3)]
            offs = build_offsets(p, ZIP64_LIMIT - 200 - 38, tail)
            # The subject has to straddle the boundary to be testing it.
            if not (offs["under.txt"] <= ZIP64_LIMIT
                    and min(offs["over%d.txt" % i] for i in (1, 2, 3))
                        > ZIP64_LIMIT):
                problems.append("offsets.zip: subject does not straddle "
                                "the 2 GB boundary: %r" % offs)
            else:
                z = zipfile.ZipFile(p)
                want = z.namelist()
                if z.getinfo("under.txt").extra:
                    problems.append("offsets.zip: under.txt carries a "
                                    "Zip64 field it should not need")
                if not z.getinfo("over1.txt").extra:
                    problems.append("offsets.zip: over1.txt carries no "
                                    "Zip64 field, so nothing is escaped")
                if z.read("over3.txt") != b"past two gigabytes: 3\n":
                    problems.append("offsets.zip: zipfile disagrees with "
                                    "the generator")
                got = ours_list(args.macextract, p)
                if got != want:
                    problems.append("offsets.zip: listed %r, zipfile says %r"
                                    % (got, want))
                bad, rc = entry_failures(args.macextract, p)
                if bad or rc != 0:
                    problems.append("offsets.zip: %d entr(y/ies) failed to "
                                    "verify (%r), exit %d" % (len(bad), bad, rc))
            ran += 1

        # The same escape where the value behind it is honest and small:
        # a writer may use one whenever it likes, and the entry must
        # extract exactly as if it had not.
        p = os.path.join(tmp, "esc0.zip")
        payload = b"escaped, but addressable\n"
        build_offsets(p, 64, [("a.txt", payload), ("b.txt", payload)],
                      escapes={"b.txt": {"off": 0}})
        out = os.path.join(tmp, "esc0out")
        os.mkdir(out)
        r = subprocess.run([args.macextract, "x", "-o", out, p],
                           capture_output=True)
        got = os.path.join(out, "b.txt")
        if r.returncode != 0 or not os.path.exists(got):
            problems.append("esc0.zip: an escaped offset with a zero high "
                            "half did not extract")
        elif open(got, "rb").read() != payload:
            problems.append("esc0.zip: extracted bytes differ")
        ran += 1

        # And where it is not addressable: past 4 GB is refused per
        # ENTRY, and the entries around it are untouched. A position and
        # a size are different refusals, so both are checked.
        for label, esc, want_msg in (
                ("off", {"off": 1}, "32-bit reach"),
                ("size", {"size": 1}, "32-bit reach")):
            p = os.path.join(tmp, "far_%s.zip" % label)
            build_offsets(p, 64, [("a.txt", payload), ("b.txt", payload),
                                  ("c.txt", payload)],
                          escapes={"b.txt": esc})
            got = ours_list(args.macextract, p)
            if got != ["hole.bin", "a.txt", "b.txt", "c.txt"]:
                problems.append("far_%s.zip: the walk did not survive the "
                                "refusal, listed %r" % (label, got))
            bad, rc = entry_failures(args.macextract, p)
            if list(bad) != ["b.txt"]:
                problems.append("far_%s.zip: expected b.txt alone to fail, "
                                "got %r" % (label, bad))
            elif want_msg not in bad["b.txt"]:
                problems.append("far_%s.zip: b.txt failed as %r, wanted %r"
                                % (label, bad["b.txt"], want_msg))
            elif rc == 0:
                problems.append("far_%s.zip: an unreadable entry exited 0"
                                % label)
            ran += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("ZIPLARGE FAIL " + p)
    print("ziplarge: %d case(s) checked, %d problem(s)" % (ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
