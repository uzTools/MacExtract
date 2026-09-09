#!/usr/bin/env python3
"""run_dart.py — DART, graded against the disks DART itself was fed.

There is no second reader for DART on this machine — `unar` has no
parser for it and neither does `macunpack` — so the oracle is not
another implementation but the ENCODER's input. CiderPress2 publishes
`TestData/dart/`: two 800K disks compressed by DART 1.5.3 running under
MAME, each in both of DART's methods, **with the source images beside
them**. `tools/fetch_references.sh` fetches the lot into
`reference/ciderpress2/`.

That gives four assertions no amount of self-consistency could:

1. the data halves of what we write equal the source image, byte for
   byte, for "fast" and for "best";
2. the tag halves equal the tags the source Disk Copy file carries
   (`random_t`), or are zero (`test1`, an ordinary HFS disk);
3. the two methods agree with each other over the same disk, which is
   two independent codecs arriving at one answer;
4. `test1-best` keeps its resource fork in the ZIP, so DART's OWN
   checksums — 'CKSM' 1 for the tags and 'CKSM' 2 for the data, written
   by the application in 1993 — are checked against a Disk Copy 4.2
   checksum of what came out.

Only (1), (2) for zero tags and (4) need nothing but Python: `test1-best`
sits in the ZIP as a plain member. The other three DART files live
INSIDE the 1440K images beside them, so they need `hfsutils` — without
it this says so and grades the one specimen it can reach.

`random_t` is the specimen that matters most for the walk rather than
the codecs: its two 256KB files are incompressible junk and its tags are
random, so 18 of its 40 chunks are marked 0xFFFF and stored whole. That
per-chunk fallback is a branch nothing else here would ever take.

Also here, because they have nowhere else to live: the refusal of an
already-uncompressed DART (which is what this engine WRITES, so the
round trip is the test), and a truncation sweep, since DART is not in
the fixture corpus and `tools/run_truncation.py` never sees one.
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REF = os.path.join(ROOT, "reference", "ciderpress2")

CHUNK_DATA = 40 * 512
CHUNK_BYTES = 40 * 524


# ------------------------------------------------------------------ #
# Reading what we wrote                                              #
# ------------------------------------------------------------------ #

def split_stored(path):
    """An UNCOMPRESSED DART, taken apart: (data, tags).

    Deliberately not shared with anything: this is the reader the output
    is graded by, so it is written from the format notes rather than
    from the engine's idea of them.
    """
    d = open(path, "rb").read()
    if len(d) < 4:
        raise ValueError("short file")
    cmp_, typ, kb = d[0], d[1], struct.unpack_from(">H", d, 2)[0]
    if cmp_ != 2:
        raise ValueError("srcCmp is %d, not 2 (not uncompressed)" % cmp_)
    slots = 40 if kb <= 800 else 72
    blocks = kb // 20
    off = 4 + slots * 2
    blen = struct.unpack_from(">%dH" % slots, d, 4)
    for i in range(slots):
        want = 0xFFFF if i < blocks else 0
        if blen[i] != want:
            raise ValueError("slot %d is %04x, wanted %04x"
                             % (i, blen[i], want))
    if len(d) != off + blocks * CHUNK_BYTES:
        raise ValueError("length %d, wanted %d"
                         % (len(d), off + blocks * CHUNK_BYTES))
    data = b"".join(d[off + i * CHUNK_BYTES:off + i * CHUNK_BYTES + CHUNK_DATA]
                    for i in range(blocks))
    tags = b"".join(d[off + i * CHUNK_BYTES + CHUNK_DATA:
                      off + (i + 1) * CHUNK_BYTES] for i in range(blocks))
    return typ, data, tags


def dc42_checksum(d):
    """Disk Copy 4.2's checksum, which DART borrows and files in its
    resource fork. Source: reference/ciderpress2/DART-notes.md,
    *General*."""
    s = 0
    for i in range(0, len(d) - 1, 2):
        s = (s + (d[i] << 8 | d[i + 1])) & 0xFFFFFFFF
        s = ((s >> 1) | (s << 31)) & 0xFFFFFFFF
    return s


def resources(fork):
    """(type, id) -> data, out of a classic resource fork. Enough of the
    map to reach two four-byte resources; not a general reader."""
    do, mo = struct.unpack_from(">II", fork, 0)
    tlo = struct.unpack_from(">H", fork, mo + 24)[0]
    ntypes = struct.unpack_from(">H", fork, mo + tlo)[0] + 1
    out = {}
    for i in range(ntypes):
        off = mo + tlo + 2 + i * 8
        t = fork[off:off + 4].decode("mac_roman")
        n = struct.unpack_from(">H", fork, off + 4)[0] + 1
        ro = struct.unpack_from(">H", fork, off + 6)[0]
        for j in range(n):
            e = mo + tlo + ro + j * 12
            rid = struct.unpack_from(">h", fork, e)[0]
            dofs = struct.unpack_from(">I", fork, e + 4)[0] & 0xFFFFFF
            dlen = struct.unpack_from(">I", fork, do + dofs)[0]
            out[(t, rid)] = fork[do + dofs + 4:do + dofs + 4 + dlen]
    return out


def appledouble_rsrc(path):
    """The resource fork out of a `._name` file, which is how a ZIP made
    on macOS carries one. AppleSingle/AppleDouble entry ID 2."""
    d = open(path, "rb").read()
    if struct.unpack_from(">I", d, 0)[0] not in (0x00051600, 0x00051607):
        return None
    n = struct.unpack_from(">H", d, 24)[0]
    for i in range(n):
        eid, off, ln = struct.unpack_from(">III", d, 26 + i * 12)
        if eid == 2:
            return d[off:off + ln]
    return None


def dc42_payload(path):
    """(data, tags) out of a Disk Copy 4.2 image: 84-byte header, then
    the two areas its header sizes."""
    d = open(path, "rb").read()
    ds, ts = struct.unpack_from(">II", d, 0x40)
    return d[84:84 + ds], d[84 + ds:84 + ds + ts]


# ------------------------------------------------------------------ #
# Specimens                                                          #
# ------------------------------------------------------------------ #

def hfs_extract(image, name, dest):
    """One file's data fork out of an HFS image, via hfsutils. Returns
    False when the tools are not installed."""
    if not (shutil.which("hmount") and shutil.which("hcopy")
            and shutil.which("humount")):
        return False
    env = dict(os.environ, HOME=os.path.dirname(dest))
    if subprocess.run(["hmount", image], capture_output=True,
                      env=env).returncode != 0:
        return False
    try:
        r = subprocess.run(["hcopy", "-r", name, dest], capture_output=True,
                           env=env)
    finally:
        subprocess.run(["humount"], capture_output=True, env=env)
    return r.returncode == 0 and os.path.exists(dest)


def specimens(tmp):
    """Every DART this run can reach, with what it must expand to.

    Each is (label, path, expected data, expected tags-or-None). A tags
    expectation of None means "must be all zero": an HFS disk's tags are
    zero-filled, which DART-notes.md gives as the reason uncompressible
    chunks are rare.
    """
    out = []
    if not os.path.isdir(REF):
        return out
    t1src = os.path.join(REF, "test1-source.img")
    t1best = os.path.join(REF, "test1-best")
    if os.path.exists(t1best) and os.path.exists(t1src):
        out.append(("test1-best", t1best, open(t1src, "rb").read(), None))

    rtsrc = os.path.join(REF, "random_t-source.img")
    rtdata, rttags = (dc42_payload(rtsrc) if os.path.exists(rtsrc)
                      else (None, None))
    for label, image, member, data, tags in (
            ("test1-fast", "test1-images.img", "test1-fast",
             (open(t1src, "rb").read() if os.path.exists(t1src) else None),
             None),
            ("random_t-fast", "random_t-images.img", "random_t-fast",
             rtdata, rttags),
            ("random_t-best", "random_t-images.img", "random_t-best",
             rtdata, rttags)):
        img = os.path.join(REF, image)
        if data is None or not os.path.exists(img):
            continue
        dest = os.path.join(tmp, member)
        if hfs_extract(img, member, dest):
            out.append((label, dest, data, tags))
    return out


# ------------------------------------------------------------------ #
# The cases no specimen reaches                                       #
# ------------------------------------------------------------------ #

def build_dart(kb, cmp_, typ, chunks):
    """A DART header and its chunks. `chunks` is one (blen, bytes) per
    chunk the disk occupies; slots past it are zero."""
    slots = 40 if kb <= 800 else 72
    out = bytearray([cmp_, typ]) + struct.pack(">H", kb)
    out += b"".join(struct.pack(">H", n) for n, _ in chunks)
    out += b"\x00\x00" * (slots - len(chunks))
    for _, b in chunks:
        out += b
    return bytes(out)


def rle_words(block):
    """A DART "fast" chunk: runs of one repeated word as a negative
    count, everything else as a positive count and the words verbatim.

    Both opcodes, deliberately. It is also why the synthetic body below
    has runs in it at all: an ALL-literal chunk encodes to 20,962 bytes,
    two more than it expands to, and DART stores such a chunk under
    0xFFFF rather than writing it — which is the rule src/fmt_dart.c
    enforces and which the last case in `synthetic` asserts.
    """
    words = [block[i:i + 2] for i in range(0, len(block), 2)]
    out = bytearray()
    at = 0
    while at < len(words):
        run = 1
        while (at + run < len(words) and words[at + run] == words[at]
               and run < 0x7FFF):
            run += 1
        if run > 1:
            out += struct.pack(">h", -run) + words[at]
            at += run
            continue
        lit = at
        while (lit < len(words) and lit - at < 0x7FFF
               and (lit + 1 >= len(words) or words[lit + 1] != words[lit])):
            lit += 1
        out += struct.pack(">h", lit - at) + b"".join(words[at:lit])
        at = lit
    return bytes(out)


def synthetic(macextract, tmp):
    """The four things the specimens cannot show, because both of them
    are 800K disks that DART compressed successfully.

    A 400K disk uses twenty of its forty slots, so it is the only shape
    that exercises "entries past the end of the disk are zero" — the
    rule that keeps a table from being read as longer than it is.
    """
    problems = []
    # Compressible, the way a real disk block is: a run, some literals,
    # a longer run, and tags that are zero.
    body = (b"\x00\x00" * 2000
            + bytes(((i * 37 + 11) & 0xFF) for i in range(4096))
            + b"\xA5\x5A" * 3000
            + bytes(((i * 11 + 3) & 0xFF) for i in range(CHUNK_BYTES
                                                        - 4000 - 4096 - 6000)))
    assert len(body) == CHUNK_BYTES
    enc = rle_words(body)
    assert len(enc) <= CHUNK_BYTES, len(enc)
    chunks = [(len(enc) // 2, enc) for _ in range(20)]
    good = build_dart(400, 0, 1, chunks)

    def check(label, blob, want_ok, want_msg=None):
        path = os.path.join(tmp, "syn.dart")
        open(path, "wb").write(blob)
        outdir = os.path.join(tmp, "synout")
        shutil.rmtree(outdir, ignore_errors=True)
        os.makedirs(outdir)
        r = subprocess.run([macextract, "x", path, "-o", outdir],
                           capture_output=True)
        ok = r.returncode == 0
        if ok != want_ok:
            problems.append("400K %s: exit %d, wanted %s"
                            % (label, r.returncode,
                               "success" if want_ok else "failure"))
            return None
        msg = r.stderr.decode("utf-8", "replace")
        if want_msg and want_msg not in msg:
            problems.append("400K %s: %r does not mention %r"
                            % (label, msg.strip(), want_msg))
        if not ok:
            return None
        got = os.path.join(outdir, os.listdir(outdir)[0])
        try:
            return split_stored(got)
        except ValueError as ex:
            problems.append("400K %s: output is not a stored DART: %s"
                            % (label, ex))
            return None

    got = check("runs and literals", good, True)
    if got and got[1] + got[2] != b"".join(
            body[:CHUNK_DATA] for _ in range(20)) + b"".join(
            body[CHUNK_DATA:] for _ in range(20)):
        problems.append("400K runs and literals: wrong bytes came out")

    # A slot past the end of the disk, holding something. The table is
    # forty entries long whatever the disk is, and a reader that sized
    # it from the DATA rather than from srcSize would put the payload
    # 64 bytes out and produce a volume of noise.
    bad = bytearray(good)
    bad[4 + 2 * 25] = 0x01
    path = os.path.join(tmp, "syn.dart")
    open(path, "wb").write(bytes(bad))
    r = subprocess.run([macextract, "sniff", path], capture_output=True)
    if b"DART" in r.stdout:
        problems.append("400K: claimed a table with a slot past the disk set")

    # One chunk stored inside a compressed archive: the 0xFFFF fallback,
    # which `random_t` reaches for real and nothing else does.
    mixed = list(chunks)
    mixed[3] = (0xFFFF, body)
    got = check("a stored chunk among compressed ones",
                build_dart(400, 0, 1, mixed), True)
    if got and got[1][3 * CHUNK_DATA:4 * CHUNK_DATA] != body[:CHUNK_DATA]:
        problems.append("400K: the stored chunk came out wrong")

    # A zero count, which DART-notes.md says can never occur.
    zeroed = list(chunks)
    zeroed[0] = (1, b"\x00\x00")
    check("a zero RLE count", build_dart(400, 0, 1, zeroed), False)

    # A chunk that claims to be longer than what it expands to. DART
    # marks such a chunk 0xFFFF and stores it instead, so a table that
    # states one is not a table DART wrote — and the cap is what bounds
    # the buffer the walk reads a chunk into.
    over = list(chunks)
    over[0] = (CHUNK_BYTES // 2 + 1, enc + b"\x00" * (CHUNK_BYTES + 2
                                                      - len(enc)))
    path = os.path.join(tmp, "syn.dart")
    open(path, "wb").write(build_dart(400, 0, 1, over))
    r = subprocess.run([macextract, "sniff", path], capture_output=True)
    if b"DART" in r.stdout:
        problems.append("400K: claimed a chunk longer than it expands to")

    # And "not compressed", which is the refusal.
    check("an uncompressed archive",
          build_dart(400, 2, 1, [(0xFFFF, body)] * 20), False,
          "already uncompressed")
    return problems


def expand(macextract, src, outdir):
    """Extract one DART and return the path of what came out."""
    os.makedirs(outdir, exist_ok=True)
    r = subprocess.run([macextract, "x", src, "-o", outdir],
                       capture_output=True)
    if r.returncode != 0:
        return None, r.stderr.decode("utf-8", "replace").strip()
    got = os.listdir(outdir)
    if len(got) != 1:
        return None, "wrote %d files, wanted 1: %r" % (len(got), got)
    return os.path.join(outdir, got[0]), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract", default=os.path.join(ROOT, "build",
                                                         "macextract"))
    args = ap.parse_args()
    macextract = os.path.abspath(args.macextract)
    if not os.path.exists(macextract):
        print("run_dart: no macextract binary at %s" % macextract)
        return 1

    problems = []
    ran = 0
    tmp = tempfile.mkdtemp(prefix="dart-")
    try:
        subjects = specimens(tmp)
        if not subjects:
            print("run_dart: reference/ciderpress2 not present "
                  "(tools/fetch_references.sh) — skipping")
            return 0
        if len(subjects) < 4:
            print("run_dart: hfsutils not installed — grading %d of the 4 "
                  "specimens (the other three are inside HFS images)"
                  % len(subjects))

        written = {}
        for label, src, data, tags in subjects:
            outdir = os.path.join(tmp, "out-" + label)
            got, why = expand(macextract, src, outdir)
            ran += 1
            if not got:
                problems.append("%s: %s" % (label, why))
                continue
            if not got.endswith(".dart"):
                problems.append("%s: wrote %s, wanted a .dart name"
                                % (label, os.path.basename(got)))
            try:
                _, gdata, gtags = split_stored(got)
            except ValueError as ex:
                problems.append("%s: output is not a stored DART: %s"
                                % (label, ex))
                continue
            written[label] = (gdata, gtags)
            if gdata != data:
                problems.append("%s: data differs from the source image"
                                % label)
            ran += 1
            if tags is None:
                if any(gtags):
                    problems.append("%s: tags are not zero" % label)
            elif gtags[:len(tags)] != tags:
                problems.append("%s: tags differ from the source image"
                                % label)
            ran += 1

        # The two methods over one disk have to agree. Nothing else here
        # compares two DECODERS; every other assertion compares one
        # decoder with an encoder's input.
        for a, b in (("test1-fast", "test1-best"),
                     ("random_t-fast", "random_t-best")):
            if a in written and b in written:
                if written[a] != written[b]:
                    problems.append("%s and %s disagree over the same disk"
                                    % (a, b))
                ran += 1

        # DART's own checksums, written by the application in 1993.
        ad = os.path.join(REF, "__MACOSX", "._test1-best")
        if "test1-best" in written and os.path.exists(ad):
            fork = appledouble_rsrc(ad)
            res = resources(fork) if fork else {}
            gdata, gtags = written["test1-best"]
            for rid, name, got in ((2, "data", gdata), (1, "tag", gtags)):
                want = res.get(("CKSM", rid))
                if want is None:
                    problems.append("test1-best: no 'CKSM' %d resource" % rid)
                    continue
                if struct.unpack(">I", want)[0] != dc42_checksum(got):
                    problems.append("test1-best: %s checksum is not the one "
                                    "DART recorded" % name)
                ran += 1

        # The round trip, which is the refusal: what we write is exactly
        # the file this engine declines to work on.
        for label in list(written)[:1]:
            done = os.path.join(tmp, "out-" + label)
            already = os.path.join(done, os.listdir(done)[0])
            r = subprocess.run([macextract, "x", already, "-o",
                                os.path.join(tmp, "again")],
                               capture_output=True)
            msg = r.stderr.decode("utf-8", "replace")
            if r.returncode == 0:
                problems.append("an uncompressed DART was extracted rather "
                                "than refused")
            elif "already uncompressed" not in msg:
                problems.append("the refusal does not say what is wrong: %r"
                                % msg.strip())
            ran += 1
            # ...and it is still recognized AS a DART, which is what
            # makes the message possible at all.
            r = subprocess.run([macextract, "sniff", already],
                               capture_output=True)
            if b"DART" not in r.stdout:
                problems.append("an uncompressed DART is not recognized")
            ran += 1

        # A cut archive. DART is not in the fixture corpus, so this is
        # the only place it meets one. The table has to add up to the
        # file, so a cut one is not a DART at all — but it must not be
        # extracted, and it must not be claimed and then half-written.
        label, src = subjects[0][0], subjects[0][1]
        whole = open(src, "rb").read()
        for frac in (2, 5, 10):
            cut = os.path.join(tmp, "cut.dart")
            open(cut, "wb").write(whole[:len(whole) // frac])
            outdir = os.path.join(tmp, "cutout%d" % frac)
            os.makedirs(outdir, exist_ok=True)
            r = subprocess.run([macextract, "x", cut, "-o", outdir],
                               capture_output=True)
            if r.returncode == 0:
                problems.append("%s cut to 1/%d extracted anyway"
                                % (label, frac))
            ran += 1

        # Near-misses. Each changes ONE thing about a header that is
        # otherwise a real DART's, and none of them may still be claimed.
        # An 800K disk fills all forty of its slots, so the rule about
        # slots past the end of the disk is not reachable from these —
        # that one needs a 400K table, which is synthetic below.
        for name, mangle in (
                ("a used slot set to zero",
                 lambda b: b[:4] + b"\x00\x00" + b[6:]),
                ("a slot length changed",
                 lambda b: b[:82] + b"\x01\x00" + b[84:]),
                ("a byte added to the file", lambda b: b + b"\x00"),
                ("a byte taken off the end", lambda b: b[:-1]),
                ("an unknown compression id", lambda b: b"\x03" + b[1:]),
                ("an unknown disk type", lambda b: b[:1] + b"\x09" + b[2:]),
                ("a size no DART disk has",
                 lambda b: b[:2] + b"\x02\x00" + b[4:])):
            bad = os.path.join(tmp, "bad.dart")
            open(bad, "wb").write(mangle(whole))
            r = subprocess.run([macextract, "sniff", bad], capture_output=True)
            if b"DART" in r.stdout:
                problems.append("claimed a DART with %s" % name)
            ran += 1

        problems += synthetic(macextract, tmp)
        ran += 9
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("run_dart: " + p)
    print("DART: %d case(s) checked, %d problem(s)" % (ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
