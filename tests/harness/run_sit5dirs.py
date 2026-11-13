#!/usr/bin/env python3
"""run_sit5dirs.py — StuffIt 5 archives with more folders than fit a table.

`src/fmt_sit5.c` finds an entry's folder by the folder's file offset, as
XADStuffIt5Parser.m does with a dictionary. Until 2026-11-03 it kept the
folders in a fixed table — 256 of them and 16 KB of their paths — and a
folder past either limit was dropped without a word: everything in it
came out at the root, with no error. Nothing in the corpus comes near
(32 StuffIt 5 archives, 12 folders at most, measured 2026-11-03), so the
two shapes are generated here, one per limit:

  * `count` — one folder holding 300 folders, each holding one file;
  * `names` — six folders deep on 31-character names, then 75 sibling
    folders of 31 characters, each holding one file: about 17 KB of
    paths in 81 folders.

Each is graded three ways: the paths and bytes that went in, what `unar`
extracts (its parser keeps every folder), and what this CLI extracts.
Then `count` once more at one byte under its own peak, so that the
folder table cannot grow: what is written must be where it belongs, and
what is not must have failed for memory, not been put at the root.

  Source: reference/notes/sit5_specs_theunarchiver.md (the entry and
          folder headers, the second block), and tools/synth_crypt.py's
          build_sit5_rc4 for the archive header both readers accept.

WHAT IT CANNOT SEE:

  * Whether StuffIt itself writes such an archive this way. The layout
    is the published one and `unar` reads it; no archive with more than
    twelve folders written by StuffIt has been found.
  * Folders whose entries come out of depth-first order: every entry
    written here follows its folder.
  * Which allocation a budget refuses. The third check runs `count` at
    one byte under its own high-water mark and asks only that nothing is
    put at the root and that every entry not written failed for memory;
    it does not ask which folders those were.

In ci.sh (tests/harness/, run by its one loop since 2026-11-13). What ci.sh said of it there:

StuffIt 5 folders past what a fixed table held (256, and 16 KB of
paths), which nothing in the corpus approaches: generated, graded three
ways with `unar`, and once more at one byte under its own peak
(TESTING.md, *StuffIt 5's folders*).
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools")
REPO = os.path.dirname(HERE)

BANNER = (b"StuffIt (c)1997-1998 Aladdin Systems, Inc., "
          b"http://www.aladdinsys.com/StuffIt/\r\n")


def crc16_arc(data, crc=0):
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def folder(name, children):
    return (name, children)


def file(name, data):
    return (name, data)


def _second_block():
    # flags2 (no resource fork), a word, type, creator, Finder flags,
    # then version 1's 22 filler bytes: 36 B, as the reader expects.
    return (struct.pack(">HH", 0, 0) + b"TEXTttxt" + struct.pack(">H", 0)
            + bytes(22))


def build(tree):
    """A version-5 archive of version-1 entries, written depth first:
    each folder's entries straight after it, its parent named by offset."""
    head = bytearray(82)
    head[:len(BANNER)] = BANNER[:82]
    head += bytes([5, 0])
    head += struct.pack(">II", 0, 0)
    head += struct.pack(">H", len(tree))
    head += struct.pack(">I", 0)
    head += struct.pack(">H", 0)
    firstoffs = len(head)
    struct.pack_into(">I", head, 94, firstoffs)
    out = bytearray(head)

    def entry(name, parent, isdir, payload):
        nb = name.encode("mac_roman")
        e = bytearray()
        e += struct.pack(">I", 0xA5A5A5A5)
        e += bytes([1, 0])
        e += struct.pack(">H", 0)                       # header size
        e += bytes([0, 0x40 if isdir else 0])
        e += struct.pack(">II", 0xA5000000, 0xA6000000)
        e += struct.pack(">III", 0, 0, parent)
        e += struct.pack(">H", len(nb))
        e += struct.pack(">H", 0)
        if isdir:
            e += struct.pack(">IIHH", 0, 0, 0, 0)
            e += struct.pack(">H", payload)             # entries inside
        else:
            e += struct.pack(">IIHH", len(payload), len(payload),
                             crc16_arc(payload), 0)
            e += bytes([0, 0])                          # stored, no key
        e += nb
        struct.pack_into(">H", e, 6, len(e))
        e += _second_block()
        if not isdir:
            e += payload
        return e

    def walk(items, parent):
        for name, body in items:
            at = len(out)
            if isinstance(body, list):
                out.extend(entry(name, parent, True, len(body)))
                walk(body, at)
            else:
                out.extend(entry(name, parent, False, body))

    walk(tree, 0)
    struct.pack_into(">I", out, 84, len(out))
    return bytes(out)


def expected(tree, prefix=""):
    got = {}
    for name, body in tree:
        path = prefix + name
        if isinstance(body, list):
            got.update(expected(body, path + "/"))
        else:
            got[path] = body
    return got


def shapes():
    count = [folder("R", [folder("d%03d" % i,
                                 [file("f", b"d%03d\n" % i)])
                          for i in range(300)])]
    chain = []
    level = chain
    for k in range(6):
        name = ("%d" % k) * 31
        sub = []
        level.append(folder(name, sub))
        level = sub
    for i in range(75):
        level.append(folder("s%02d" % i + "x" * 28,
                            [file("f", b"s%02d\n" % i)]))
    return {"count": count, "names": chain}


def tree_of(root):
    got = {}
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                got[os.path.relpath(p, root)] = fh.read()
    return got


def compare(label, want, got, problems):
    if want == got:
        return
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    wrong = sorted(k for k in set(want) & set(got) if want[k] != got[k])
    problems.append("%s: %d missing, %d extra, %d differ%s" % (
        label, len(missing), len(extra), len(wrong),
        (" — first missing %s" % missing[0]) if missing else
        (" — first extra %s" % extra[0]) if extra else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract",
                    default=os.path.join(REPO, "build", "rel", "macextract"))
    ap.add_argument("--no-unar", action="store_true")
    args = ap.parse_args()

    problems = []
    work = tempfile.mkdtemp(prefix="sit5dirs-",
                            dir=os.path.join(REPO, ".tmp"))
    try:
        for label, tree in shapes().items():
            want = expected(tree)
            arc = os.path.join(work, label + ".sit")
            with open(arc, "wb") as fh:
                fh.write(build(tree))
            ours = os.path.join(work, label + ".ours")
            os.mkdir(ours)
            r = subprocess.run([args.macextract, "x", "-o", ours, arc],
                               capture_output=True)
            if r.returncode != 0:
                problems.append("%s: macextract exit %d: %s" % (
                    label, r.returncode,
                    r.stderr.decode("utf-8", "replace")[:200]))
            compare(label + " (macextract)", want, tree_of(ours), problems)
            if not args.no_unar:
                theirs = os.path.join(work, label + ".unar")
                r = subprocess.run(["unar", "-q", "-D", "-o", theirs, arc],
                                   capture_output=True)
                if r.returncode != 0:
                    problems.append("%s: unar exit %d" % (label,
                                                          r.returncode))
                compare(label + " (unar)", want, tree_of(theirs), problems)
            if label == "count":
                starved(args.macextract, arc, want, work, problems)
            print("run_sit5dirs: %s: %d files in %d folders" % (
                label, len(want), sum(1 for _ in _folders(tree))))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for p in problems:
        print("run_sit5dirs: FAIL " + p)
    print("run_sit5dirs: %d problem(s)" % len(problems))
    return 1 if problems else 0


def starved(macextract, arc, want, work, problems):
    r = subprocess.run([macextract, "t", "--stats", arc],
                       capture_output=True, text=True)
    peak = None
    for line in (r.stdout + r.stderr).splitlines():
        if "high-water" in line:
            peak = int(line.split("high-water")[1].split()[0])
    if peak is None:
        problems.append("count (starved): no high-water mark in --stats")
        return
    out = os.path.join(work, "count.starved")
    os.mkdir(out)
    r = subprocess.run([macextract, "x", "--budget", str(peak - 1),
                        "-o", out, arc], capture_output=True, text=True)
    got = tree_of(out)
    misplaced = sorted(k for k in got if want.get(k) != got[k])
    failed = [l for l in r.stderr.splitlines()
              if l.startswith("macextract: f: ")]
    notmem = [l for l in failed if "out of memory" not in l]
    if misplaced:
        problems.append("count (starved): %d files where they do not belong"
                        ", first %s" % (len(misplaced), misplaced[0]))
    if notmem:
        problems.append("count (starved): %d entries failed for another "
                        "reason, first %r" % (len(notmem), notmem[0]))
    if len(got) + len(failed) != len(want) or not failed:
        problems.append("count (starved): %d written + %d refused of %d, at "
                        "a budget of %d" % (len(got), len(failed), len(want),
                                            peak - 1))


def _folders(tree):
    for _, body in tree:
        if isinstance(body, list):
            yield 1
            yield from _folders(body)


if __name__ == "__main__":
    sys.exit(main())
