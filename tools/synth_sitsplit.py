#!/usr/bin/env python3
"""synth_sitsplit.py — synthetic StuffIt segmented ("split") sets.

No segmented archive exists in the harvested corpus: measured on
2026-08-08 and re-measured 2026-08-15 over all 805 fixtures — no file
carries the `B0 56 00` header, all 108 Compact Pro archives are volume 1
and every file entry in them points at volume 1, and no manifest holds a
part-like entry name. So the fixtures for this format are generated, and adjudicated by
`unar`, which implements it (reference/XADMaster/XADStuffItSplitParser.m).

Header layout comes from that parser and nowhere else:

    0  0xB0   1  0x56   2  0x00   3  part number (1-based)
    4  name length of the ORIGINAL file, 1..63
    5  name bytes
   68  type(4) creator(4) flags(2) created(4) modified(4)
       rsrclen(4) datalen(4)          <- the 26 fingerprint bytes
  100  payload

   94  CRC-16/ARC of bytes 0..93, big-endian
   96  CRC-16/ARC of the RESOURCE fork's bytes in parts 1..n, running
   98  CRC-16/ARC of the DATA fork's bytes in parts 1..n, running

The three CRCs are what StuffIt writes: the header's measured 2026-10-24
on 40 parts of seven sets StuffIt itself cut, the two running sums in
StuffIt Deluxe 2.0.1's own code and on the sets it cut from files with
a resource fork that evening (src/fmt_sitseg.c's file comment;
DECISIONS.md 2026-10-24, *the two bytes the writer drew*). This wrote
zero in all three until that day, and until that evening one sum over
both forks together at 98 — which only a file with no resource fork
could tell from the real rule, and every real set then on hand was one.
Bytes 0-1 are NOT measured here: StuffIt draws them from QuickDraw's
Random once per set, and B0 56 is one such value that `unar`, this
suite's oracle, requires. Bytes 5+namelen..67
are zero here and whatever was in StuffIt's buffer there. The sets
StuffIt wrote are graded separately (run_segments.py, REAL_SITSEG). A consequence worth stating — the total part COUNT is
not stored anywhere, so a reader knows the set is complete only by
summing payloads to rsrclen + datalen, which is what our joiner and
XADMaster both do.

Deterministic: no randomness, no timestamps.

Usage:
    synth_sitsplit.py --case basic3 -o DIR
    synth_sitsplit.py --list
"""
import argparse, os, struct, sys

HEAD = 100
MAGIC = b"\xb0\x56\x00"

# Arbitrary but fixed: a plausible Mac file, so the fingerprint bytes
# are not all zero and a mismatch is a real mismatch.
TYPE, CREATOR = b"SIT!", b"SIT!"
FFLAGS = 0x0000
CREATED, MODIFIED = 0xA8B4C1E0, 0xA8B4C2F0


def crc16_arc(data, crc=0):
    """CRC-16/ARC (reflected 0x8005, init 0), as both header CRCs use."""
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def header(part, name, rsrclen, datalen, ftype=TYPE, creator=CREATOR,
           created=CREATED, modified=MODIFIED, flags=FFLAGS, running=0,
           running_rsrc=0):
    """One part's header. `running_rsrc` and `running` are the
    CRC-16/ARCs of the resource fork's and the data fork's bytes in
    parts 1..`part`, this one's included: each is crc16_arc over what
    of that fork has been cut so far, and 0 where none has."""
    if not 1 <= len(name) <= 63:
        raise ValueError("name length must be 1..63")
    if b"\0" in name:
        raise ValueError("name may not contain NUL")
    h = bytearray(HEAD)
    h[0:3] = MAGIC
    h[3] = part
    h[4] = len(name)
    h[5:5 + len(name)] = name
    struct.pack_into(">4s4sHIIII", h, 68, ftype, creator, flags,
                     created, modified, rsrclen, datalen)
    struct.pack_into(">H", h, 94, crc16_arc(h[:94]))
    struct.pack_into(">H", h, 96, running_rsrc)
    struct.pack_into(">H", h, 98, running)
    return bytes(h)


def blob(n, seed=0):
    """Deterministic, compressible-but-not-constant filler."""
    out = bytearray(n)
    x = (seed * 2654435761 + 1) & 0xFFFFFFFF
    for i in range(n):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = (x >> 16) & 0xFF
    return bytes(out)


def write_set(outdir, names, payload, rsrclen, datalen, cuts, name=b"Test.sit",
              **hdrkw):
    """Write one set. `cuts` are payload split offsets; `names` the file
    names to use, in PART order (so a caller can name them misleadingly)."""
    bounds = [0] + list(cuts) + [len(payload)]
    if len(bounds) - 1 != len(names):
        raise ValueError("need one name per part")
    paths = []
    for i in range(len(names)):
        chunk = payload[bounds[i]:bounds[i + 1]]
        p = os.path.join(outdir, names[i])
        cut = bounds[i + 1]                  # payload bytes written so far
        with open(p, "wb") as f:
            f.write(header(i + 1, name, rsrclen, datalen,
                           running_rsrc=crc16_arc(payload[:min(cut, rsrclen)]),
                           running=crc16_arc(payload[rsrclen:cut]),
                           **hdrkw))
            f.write(chunk)
        paths.append(p)
    return paths


def case_basic3(outdir):
    """Three parts, both forks, cuts inside each fork."""
    rsrc, data = blob(9000, 1), blob(21000, 2)
    payload = rsrc + data
    names = ["Test.sit.1", "Test.sit.2", "Test.sit.3"]
    write_set(outdir, names, payload, len(rsrc), len(data), [11000, 22000],
              name=b"Test.sit")
    return b"Test.sit", payload, len(rsrc), len(data)


def case_single(outdir):
    """A set of one part: extractable with no volume source at all."""
    rsrc, data = blob(500, 3), blob(4000, 4)
    payload = rsrc + data
    write_set(outdir, ["Solo.sit.1"], payload, len(rsrc), len(data), [],
              name=b"Solo.sit")
    return b"Solo.sit", payload, len(rsrc), len(data)


def case_forkedge(outdir):
    """A cut exactly on the resource/data fork boundary."""
    rsrc, data = blob(8192, 5), blob(8192, 6)
    payload = rsrc + data
    write_set(outdir, ["Edge.sit.1", "Edge.sit.2"], payload,
              len(rsrc), len(data), [8192], name=b"Edge.sit")
    return b"Edge.sit", payload, len(rsrc), len(data)


def case_dataonly(outdir):
    """No resource fork — the joined stream is the data fork alone."""
    data = blob(30000, 7)
    write_set(outdir, ["Data.sit.1", "Data.sit.2"], data, 0, len(data),
              [12345], name=b"Data.sit")
    return b"Data.sit", data, 0, len(data)


def case_rsrconly(outdir):
    """No data fork."""
    rsrc = blob(20000, 8)
    write_set(outdir, ["Rsrc.sit.1", "Rsrc.sit.2"], rsrc, len(rsrc), 0,
              [7777], name=b"Rsrc.sit")
    return b"Rsrc.sit", rsrc, len(rsrc), 0


def case_many12(outdir):
    """Twelve parts, uneven, one of them empty of payload."""
    rsrc, data = blob(6000, 9), blob(30000, 10)
    payload = rsrc + data
    cuts = [1000, 5000, 5000, 9000, 12000, 15000, 18000, 21000, 24000,
            30000, 33000]
    names = ["Many.sit.%d" % (i + 1) for i in range(len(cuts) + 1)]
    write_set(outdir, names, payload, len(rsrc), len(data), cuts,
              name=b"Many.sit")
    return b"Many.sit", payload, len(rsrc), len(data)


def case_misnamed(outdir):
    """Names that contradict the part order, plus a name-alike intruder.

    Part 1 is called "zzz-last", part 3 "aaa-first", and the extension
    is a lie. A reader that sorts by name, or trusts the extension, or
    trusts the prefix, gets a different answer from one that reads the
    part number out of the header.
    """
    rsrc, data = blob(3000, 11), blob(9000, 12)
    payload = rsrc + data
    names = ["zzz-last.txt", "middle", "aaa-first.sit.1"]
    write_set(outdir, names, payload, len(rsrc), len(data), [4000, 8000],
              name=b"Test.sit")

    # Same original name, different fingerprint: belongs to another set
    # and must never be picked up.
    other = blob(2000, 13)
    with open(os.path.join(outdir, "Test.sit.2"), "wb") as f:
        f.write(header(2, b"Test.sit", 0, len(other), modified=MODIFIED + 1))
        f.write(other)
    return b"Test.sit", payload, len(rsrc), len(data)


CASES = {
    "basic3":   case_basic3,
    "single":   case_single,
    "forkedge": case_forkedge,
    "dataonly": case_dataonly,
    "rsrconly": case_rsrconly,
    "many12":   case_many12,
    "misnamed": case_misnamed,
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", choices=sorted(CASES))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("-o", "--outdir")
    a = ap.parse_args()

    if a.list:
        for k in sorted(CASES):
            print(k)
        return 0
    if not a.case or not a.outdir:
        ap.error("--case and -o are required")
    os.makedirs(a.outdir, exist_ok=True)
    name, payload, rsrclen, datalen = CASES[a.case](a.outdir)
    print("%s: %s, %d bytes payload (rsrc %d, data %d)"
          % (a.case, name.decode("ascii"), len(payload), rsrclen, datalen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
