#!/usr/bin/env python3
"""synth_cptsplit.py — segmented Compact Pro sets, cut the way the
application cuts them.

The layout this writes is not transcribed from any reference: nothing
documents it. It is DERIVED from real specimens made by Compact Pro 1.51
itself under Mini vMac (`tools/vmac/cptsegment.py`, DECISIONS.md
2026-08-14), and this module is required to reproduce those specimens
byte for byte — `run_segments.py` checks that whenever they are present,
which is what keeps a generator from drifting into being its own
authority.

What the specimens say, and what is written here:

  * every segment begins with the same 8-byte header an ordinary archive
    has: 0x01, a volume number, a 16-bit set identity, an index offset;
  * volume numbers are 1-based and consecutive;
  * the identity is ONE value shared by every segment of the set, and is
    what lets the application find the parts whatever they are called
    (the author's manual, reference/notes/cpt_users_guide.txt);
  * the index offset is 0 in every segment but the LAST, which carries
    it relative to its own start — "you must open the FINAL segment";
  * the payload, each segment minus its 8 header bytes, concatenated, is
    byte-identical to the source archive's data region: segmenting
    re-chunks and rewrites the directory, it does not recompress;
  * an entry is addressed as (volume, offset within that volume's file),
    the offset counted from that segment's start, header included, and
    entry data crosses boundaries freely.

Deterministic: the identity is derived from the source bytes rather than
drawn at random, so a case regenerates identically.

Usage:
    synth_cptsplit.py --in derived-Education7.1.cpt --size 24576 -o DIR
"""
import argparse, os, struct, sys

HDR = 8                      # 01, volume, identity:2, index offset:4
SIG = 1


def parse_index(b):
    """(index offset, [(kind, name, volume, data offset, entry span)])
    for a single-volume archive. Layout: src/fmt_cpt.c, whose sources are
    XADCompactProParser.m and macunpack/cpt.c."""
    off = struct.unpack(">I", b[4:8])[0]
    p = off + 4                                   # past the index CRC
    nent, clen = struct.unpack(">H", b[p:p + 2])[0], b[p + 2]
    p += 3 + clen
    ents = []
    for _ in range(nent):
        here = p
        nl = b[p]; p += 1
        name = b[p:p + (nl & 0x7f)]; p += (nl & 0x7f)
        if nl & 0x80:
            p += 2
            ents.append(("d", name, None, None, here))
        else:
            vol = b[p]
            f = struct.unpack(">I4s4sIIHIHIIII", b[p + 1:p + 45])
            ents.append(("f", name, vol, f[0], here))
            p += 45
    return off, ents, p


def identity(payload):
    """A 16-bit set identity. The application draws one per set — all 68
    single-volume archives in the corpus carry a different value — so any
    number does, as long as every segment of a set shares it. Derived from
    the content here so that a regenerated case is the same bytes."""
    h = 0x1234
    for i, c in enumerate(payload[:4096]):
        h = ((h * 33) ^ (c + i)) & 0xFFFF
    return h or 1


def segment(src, seg_size, ident=None):
    """Cut a single-volume archive into segments of `seg_size` bytes.

    Returns [bytes] in volume order. `seg_size` is the size of a whole
    segment FILE, header included, which is what the application's dialog
    asks for ("24 K" produced 24576-byte files).
    """
    if len(src) < HDR or src[0] != SIG or src[1] != 1:
        raise ValueError("not a single-volume Compact Pro archive")
    if seg_size <= HDR:
        raise ValueError("segment size must exceed the 8-byte header")

    idx_off, ents, idx_end = parse_index(src)
    payload = src[HDR:]
    body = seg_size - HDR
    chunks = [payload[i:i + body] for i in range(0, len(payload), body)] \
        or [b""]
    ident = identity(payload) if ident is None else ident

    # Where each chunk's payload starts, flat: that is what turns an
    # absolute offset in the source into the (volume, offset) pair the
    # segmented directory carries.
    starts, acc = [], 0
    for c in chunks:
        starts.append(acc); acc += len(c)

    def locate(flat):
        for v in range(len(chunks) - 1, -1, -1):
            if flat >= starts[v]:
                return v + 1, flat - starts[v] + HDR
        raise AssertionError("offset before the first segment")

    # Rewrite each file entry's volume and offset, in place, in the copy
    # of the index that will live in the final segment.
    rewritten = bytearray(payload)
    for kind, _name, _vol, off, at in ents:
        if kind != "f":
            continue
        vol, within = locate(off - HDR)
        pos = at - HDR                       # `at` indexes the source file
        nl = rewritten[pos]
        q = pos + 1 + (nl & 0x7f)
        rewritten[q] = vol
        struct.pack_into(">I", rewritten, q + 1, within)

    # The index CRC covers the region from `nentries` to the end of the
    # index (src/fmt_cpt.c): reflected CRC-32, init 0xFFFFFFFF, stored
    # WITHOUT the final xor.
    crc_from, crc_to = idx_off + 4 - HDR, idx_end - HDR
    struct.pack_into(">I", rewritten, idx_off - HDR,
                     cpt_crc32(rewritten[crc_from:crc_to]))

    out, cut = [], 0
    for v, chunk in enumerate(chunks, start=1):
        piece = rewritten[cut:cut + len(chunk)]
        cut += len(chunk)
        last = v == len(chunks)
        head = bytearray(HDR)
        head[0] = SIG
        head[1] = v
        struct.pack_into(">H", head, 2, ident)
        # Only the final segment says where the index is, and says it
        # relative to its own start.
        struct.pack_into(">I", head, 4,
                         idx_off - starts[v - 1] if last else 0)
        out.append(bytes(head) + bytes(piece))
    return out


def cpt_crc32(data):
    """Reflected CRC-32, init 0xFFFFFFFF, no final xor — the form Compact
    Pro compares against (src/fmt_cpt.c)."""
    crc = 0xFFFFFFFF
    for c in data:
        crc ^= c
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return crc


def default_names(base, n):
    """The application's own suggestion: NAME.cpt.#1 ... — measured on the
    specimens, and the convention the manual documents. Nothing reading a
    set may depend on it."""
    return ["%s.#%d" % (base, i + 1) for i in range(n)]


def write_set(src_path, outdir, seg_size, base=None):
    src = open(src_path, "rb").read()
    segs = segment(src, seg_size)
    base = base or os.path.basename(src_path)
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for name, blob in zip(default_names(base, len(segs)), segs):
        p = os.path.join(outdir, name)
        with open(p, "wb") as f:
            f.write(blob)
        paths.append(p)
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--size", type=int, default=24576)
    ap.add_argument("-o", dest="out", required=True)
    ap.add_argument("--base")
    a = ap.parse_args()
    for p in write_set(a.src, a.out, a.size, a.base):
        print("%s  %d bytes" % (os.path.basename(p), os.path.getsize(p)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
