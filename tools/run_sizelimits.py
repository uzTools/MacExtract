#!/usr/bin/env python3
"""run_sizelimits.py — tars whose members are past the engine's 32-bit reach.

`UncIO` addresses a container with a `uint32` and an entry's size with
another, so two boundaries exist and they are not the same boundary:

  a MEMBER over 2 GB   cannot be extracted — but its header states how
                       long it is, so the member AFTER it is still found.
                       Refused per entry (`UNC_ERR_TOOLARGE`).
  a POSITION over 4 GB cannot be addressed at all, and ends the walk with
                       `UNC_ERR_CORRUPT`. Every format shares this one.

Until 2026-08-27 the first was the second: one oversized member ended the
whole tar, losing every member behind it.

Graded by **GNU tar**, an implementation with none of these limits: it
gives the member list each subject is supposed to have, and our listing is
compared against it. The subjects are generated because nothing in the
corpus is remotely this large, and they are SPARSE — an oversized member
is a hole, so a 4.5 GB archive costs a few kilobytes of disk.

What this CANNOT see: anything about a member whose bytes are real. The
holes are never read, so the read path over a multi-gigabyte entry is
still unexercised — and on the Mac target it is unreachable anyway
(HFS caps a fork at 2 GB, FORMATS.md, *Size limits*).

Skips politely when `tar` is missing or the filesystem has no sparse
files.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

GIB = 1024 * 1024 * 1024


def header(name, size, typeflag=b"0"):
    """One POSIX ustar header block. Source: POSIX.1-1988 ustar, the same
    layout fmt_exo.c reads."""
    h = bytearray(512)
    h[0:len(name)] = name.encode()
    h[100:108] = b"000644 \0"
    h[108:116] = b"000000 \0"
    h[116:124] = b"000000 \0"
    h[124:136] = ("%011o " % size).encode()
    h[136:148] = b"14000000000 "
    h[148:156] = b"        "          # checksum field counts as spaces
    h[156:157] = typeflag
    h[257:263] = b"ustar\0"
    h[263:265] = b"00"
    h[148:156] = ("%06o\0 " % sum(h)).encode()
    return bytes(h)


def build(path, members):
    """A tar of (name, size) members. Anything over 64 KB is written as a
    hole; smaller members get repeating known bytes."""
    with open(path, "wb") as f:
        for name, size in members:
            f.write(header(name, size))
            if size > 65536:
                f.truncate(f.tell() + size)
                f.seek(0, os.SEEK_END)
            else:
                f.write(payload(name, size))
            pad = (-size) % 512
            if pad:
                f.write(b"\0" * pad)
        f.write(b"\0" * 1024)


def payload(name, size):
    """Known bytes for a small member, so extraction can be compared."""
    unit = name.encode() + b" contents\n"
    return (unit * (size // len(unit) + 1))[:size]


def tar_names(path):
    """The member list according to GNU tar."""
    r = subprocess.run(["tar", "tf", path], capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", "replace").split()


def ours_list(macextract, path):
    """(name, size-column) per entry, and the exit code."""
    r = subprocess.run([macextract, "l", path], capture_output=True)
    out = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split(None, 4)
        if len(parts) == 5 and parts[0] in ("f", "d"):
            out.append((parts[4], parts[1]))
    return out, r.returncode


def sparse_ok(tmp):
    p = os.path.join(tmp, "probe")
    with open(p, "wb") as f:
        f.truncate(64 * 1024 * 1024)
    blocks = os.stat(p).st_blocks
    os.remove(p)
    return blocks * 512 < 1024 * 1024


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract", default="build/macextract")
    args = ap.parse_args()

    if not shutil.which("tar"):
        print("sizelimits: skipped (no tar to grade against)")
        return 0

    problems = []
    ran = 0
    tmp = tempfile.mkdtemp()
    try:
        if not sparse_ok(tmp):
            print("sizelimits: skipped (%s has no sparse files)" % tmp)
            return 0

        # 1. An oversized member between two ordinary ones. Every member
        #    is listed, the big one is refused, and BOTH small ones come
        #    out — the third is the one that used to be lost.
        p = os.path.join(tmp, "member.tar")
        build(p, [("small1.bin", 4096),
                  ("huge.bin", 2560 * 1024 * 1024),
                  ("small2.bin", 11)])
        want = tar_names(p)
        got, rc = ours_list(args.macextract, p)
        if want is None:
            problems.append("member.tar: GNU tar would not read the subject")
        elif [n for n, _ in got] != want:
            problems.append("member.tar: listed %s, tar says %s"
                            % ([n for n, _ in got], want))
        elif rc != 0:
            problems.append("member.tar: listing exited %d" % rc)
        elif got[1][1] != "?":
            problems.append("member.tar: huge.bin listed a size of %s"
                            % got[1][1])
        out = os.path.join(tmp, "out")
        os.mkdir(out)
        r = subprocess.run([args.macextract, "x", "-o", out, p],
                           capture_output=True)
        if r.returncode == 0:
            problems.append("member.tar: extraction reported success")
        for name, size in (("small1.bin", 4096), ("small2.bin", 11)):
            f = os.path.join(out, name)
            if not os.path.exists(f):
                problems.append("member.tar: %s was not extracted" % name)
            elif open(f, "rb").read() != payload(name, size):
                problems.append("member.tar: %s differs" % name)
        if os.path.exists(os.path.join(out, "huge.bin")):
            problems.append("member.tar: a 2.5 GB member was written out")
        ran += 1

        # 2. The boundary, from both sides: 2 GiB - 1024 is a size, 2 GiB
        #    (0x80000000) is not. The member behind it survives either way.
        for label, size, sized in (("under", 2 * GIB - 1024, True),
                                   ("at", 2 * GIB, False)):
            p = os.path.join(tmp, "%s.tar" % label)
            build(p, [("big.bin", size), ("after.bin", 7)])
            want = tar_names(p)
            got, rc = ours_list(args.macextract, p)
            if want is None:
                problems.append("%s.tar: GNU tar would not read it" % label)
            elif [n for n, _ in got] != want:
                problems.append("%s.tar: listed %s, tar says %s"
                                % (label, [n for n, _ in got], want))
            elif rc != 0:
                problems.append("%s.tar: listing exited %d" % (label, rc))
            elif sized and got[0][1] != str(size):
                problems.append("%s.tar: %d listed as %s"
                                % (label, size, got[0][1]))
            elif not sized and got[0][1] != "?":
                problems.append("%s.tar: 0x80000000 listed as %s"
                                % (label, got[0][1]))
            ran += 1

        # 3. The other limit, so the two are not confused: a POSITION past
        #    4 GB ends the walk, however small the member sitting there is.
        p = os.path.join(tmp, "over4g.tar")
        build(p, [("a.bin", 3 * GIB // 2), ("b.bin", 3 * GIB // 2),
                  ("c.bin", 3 * GIB // 2), ("d.bin", 5)])
        want = tar_names(p)
        got, rc = ours_list(args.macextract, p)
        if want is None or len(want) != 4:
            problems.append("over4g.tar: GNU tar says %s" % (want,))
        elif [n for n, _ in got] != want[:3]:
            problems.append("over4g.tar: listed %s, wanted the first three "
                            "of %s" % ([n for n, _ in got], want))
        elif rc == 0:
            problems.append("over4g.tar: a member past 4 GB was reported "
                            "as a clean walk")
        ran += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("SIZELIMITS FAIL " + p)
    print("sizelimits: %d case(s) checked, %d problem(s)" % (ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
