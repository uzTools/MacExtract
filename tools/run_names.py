#!/usr/bin/env python3
"""run_names.py — names longer than the engine or the filesystem takes.

Two caps meet a name on its way to disk, and neither is negotiable:

  the ENGINE's     `UncEntryInfo.name` is UNC_NAME_MAX (255) bytes plus a
                   terminator, inside a struct that travels on a 68000's
                   4 KB stack. A longer name is cut as it is read, and
                   the bytes past the cap are never held anywhere.
  the FILESYSTEM's `pathconf(_PC_NAME_MAX)` per component and
                   `_PC_PATH_MAX` for the whole path — 255 and 4096 on
                   ext4, less on others. 255 bytes of MacRoman become up
                   to 765 of UTF-8, so this one bites where the engine's
                   does not.

The notice is text on a screen, so it is NOT the filesystem's to
constrain: it carries the archive's own name in full wherever the format
still holds it when the cut is made (`UncOptions.long_name`), and the
length alone where the bytes were dropped before the engine saw them.

The CLI's policy since 2026-08-27 is the one a filesystem has always
had: **shorten and carry on**. The file is extracted under the shortened
name, a name that collides because of the shortening is numbered ~1,
~2 … rather than refused, and every shortened name is listed in a notice
at the end of the run. The run exits 0 — nothing failed.

Until that day the engine cut the name and said nothing, so a 457-byte
path extracted as 255 bytes under a name that was not the archive's; for
a few hours after it the entry was refused outright, which lost the file
altogether (DECISIONS.md 2026-08-27, *the name cap*).

The subjects are generated, because **the longest name in 932 fixtures
is 120 bytes** — under half the engine's cap, so neither the
differential suite nor its 9,320 variants could reach either limit.

Graded by readers with no such limit: CPython's `zipfile` and `tarfile`,
which wrote the archives and give the names that were meant, and
`unzip -l` / `tar tf` where they are installed.

Six carriers, because a name is cut in six different places: zip's
central directory, tar's `prefix + '/' + name` (155 + 1 + 100 = 256, one
byte over the engine's cap — which the FORMAT can express and the engine
cannot), uuencode's `begin` line, cut by a 96-byte LINE buffer before
the cap is reached and reported the same way, AppleSingle's real name,
whose MacRoman expands past what one directory entry takes, and the two
Macintosh archive formats that reach the cap by SUMMING a path rather
than by holding one long name: Now Compress (`tools/synth_now.py`) and
DiskDoubler, in both its containers (`tools/synth_dd.py`, 2026-08-28).

What this CANNOT see: SuperDisk!'s path builder, which no fixture nests
deep enough to reach the cap with and which nothing off the Macintosh
reads, so a generated container could only be graded against our own
transcription of it. The Mac application consumes none of this: it
cuts every component at 31 characters and numbers the collision that
creates off the File Manager's `dupFNErr`, telling nobody either way
(`tools/run_macnames.py`).
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import zipfile

CAP = 255                     # UNC_NAME_MAX


def ours(macextract, args):
    """(listed names, stderr, exit code) for one CLI run."""
    r = subprocess.run([macextract] + args, capture_output=True)
    names = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split(None, 4)
        if len(parts) == 5 and parts[0] in ("f", "d"):
            names.append(parts[4])
    return names, r.stderr.decode("utf-8", "replace"), r.returncode


def noted(stderr):
    """The names the end-of-run notice lists as shortened — the first
    line of each pair; the "written as" line under it is the same
    entry."""
    out = []
    for line in stderr.splitlines():
        if (line.startswith("macextract:   ")
                and not line.startswith("macextract:     ")):
            out.append(line[len("macextract:   "):])
    return out


def written(out):
    """Every file under `out`, as paths relative to it."""
    got = []
    for root, _, files in os.walk(out):
        for f in files:
            got.append(os.path.relpath(os.path.join(root, f), out))
    return sorted(got)


def check(problems, cond, msg):
    if not cond:
        problems.append(msg)
    return cond


def zip_cases(macextract, tmp, problems):
    ran = 0

    # 1. A name the engine has to cut is still extracted, under the cut
    #    name, and the entry beside it is untouched.
    p = os.path.join(tmp, "long.zip")
    long_name = "d/" + "x" * 250 + "/" + "y" * 200 + ".txt"
    payload = b"the entry with a nameable name\n"
    cut_payload = b"the entry whose name was cut\n"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(long_name, cut_payload)
        z.writestr("short.txt", payload)
    if check(problems, len(zipfile.ZipFile(p).namelist()) == 2,
             "long.zip: the generator did not write two entries"):
        out = os.path.join(tmp, "longout")
        os.mkdir(out)
        _, err, rc = ours(macextract, ["x", "-o", out, p])
        got = written(out)
        check(problems, len(got) == 2,
              "long.zip: wrote %r, wanted both entries" % got)
        check(problems, rc == 0,
              "long.zip: a shortened name is not a failure, but exit was %d"
              % rc)
        check(problems, len(noted(err)) == 1,
              "long.zip: the notice listed %r" % noted(err))
        check(problems, long_name in err,
              "long.zip: the notice does not carry the archive's own name "
              "in full")
        if len(got) == 2:
            body = sorted(open(os.path.join(out, g), "rb").read()
                          for g in got)
            check(problems, body == sorted([payload, cut_payload]),
                  "long.zip: the extracted bytes are not the archive's")
    ran += 1

    # 2. Two names that differ only PAST the cut collide once shortened.
    #    Both come out; the second is numbered, the way an 8.3 filesystem
    #    numbered what it had to shorten.
    p = os.path.join(tmp, "collide.zip")
    base = "c" * 250 + "/" + "d" * 200
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(base + "A.txt", b"first\n")
        z.writestr(base + "B.txt", b"second\n")
    out = os.path.join(tmp, "collideout")
    os.mkdir(out)
    _, err, rc = ours(macextract, ["x", "-o", out, p])
    got = written(out)
    check(problems, len(got) == 2,
          "collide.zip: wrote %d file(s), wanted 2" % len(got))
    check(problems, any(g.endswith("~1") for g in got),
          "collide.zip: the second name was not numbered: %r"
          % [g[-8:] for g in got])
    check(problems, rc == 0, "collide.zip: exit was %d" % rc)
    check(problems, "numbered" in err,
          "collide.zip: the notice does not say a name was numbered")
    # The two names differ only past the cut, so the notice is the only
    # place they can be told apart at all.
    check(problems, base + "A.txt" in err and base + "B.txt" in err,
          "collide.zip: the notice does not carry both names in full")
    if len(got) == 2:
        body = sorted(open(os.path.join(out, g), "rb").read() for g in got)
        check(problems, body == [b"first\n", b"second\n"],
              "collide.zip: the two files are not the two entries")
    ran += 1

    # 3. The engine's cap from both sides: 255 bytes is carried whole,
    #    256 is one byte too many — and both are written.
    p = os.path.join(tmp, "edge.zip")
    at_cap = "a" * (CAP - 4) + ".txt"          # exactly 255
    over = "b" * (CAP - 3) + ".txt"            # exactly 256
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(at_cap, b"edge\n")
        z.writestr(over, b"edge\n")
    if check(problems, len(at_cap) == CAP and len(over) == CAP + 1,
             "edge.zip: the subject does not straddle the cap"):
        out = os.path.join(tmp, "edgeout")
        os.mkdir(out)
        _, err, rc = ours(macextract, ["x", "-o", out, p])
        check(problems, os.path.exists(os.path.join(out, at_cap)),
              "edge.zip: a name of exactly %d bytes was not written whole"
              % CAP)
        check(problems, len(written(out)) == 2,
              "edge.zip: wrote %r" % written(out))
        check(problems, len(noted(err)) == 1,
              "edge.zip: %d name(s) in the notice, wanted the 256-byte one"
              % len(noted(err)))
        check(problems, rc == 0, "edge.zip: exit was %d" % rc)
    ran += 1
    return ran


def tar_case(macextract, tmp, problems):
    """ustar splits a path into a 155-byte prefix and a 100-byte name, so
    it can state 256 bytes — one more than the engine carries."""
    p = os.path.join(tmp, "long.tar")
    prefix = "p" * 155
    over = prefix + "/" + "n" * 100                  # 256
    at_cap = prefix + "/" + "n" * 99                 # 255
    with tarfile.open(p, "w", format=tarfile.USTAR_FORMAT) as t:
        for name in (at_cap, over):
            info = tarfile.TarInfo(name)
            info.size = 0
            t.addfile(info)
    want = tarfile.open(p).getnames()
    if check(problems, want == [at_cap, over],
             "long.tar: tarfile wrote %r" % [len(n) for n in want]):
        out = os.path.join(tmp, "tarout")
        os.mkdir(out)
        _, err, rc = ours(macextract, ["x", "-o", out, p])
        check(problems, os.path.exists(os.path.join(out, at_cap)),
              "long.tar: the 255-byte member was not written whole")
        check(problems, len(written(out)) == 2,
              "long.tar: wrote %r" % written(out))
        check(problems, len(noted(err)) == 1,
              "long.tar: the notice listed %r" % noted(err))
        check(problems, over in err,
              "long.tar: the notice does not carry the 256-byte name")
        check(problems, rc == 0, "long.tar: exit was %d" % rc)
    return 1


def uu_case(macextract, tmp, problems):
    """uuencode's name is one line of text and reaches the other name
    funnel; its 96-byte line buffer cuts a long one before the engine's
    cap is even in play."""
    p = os.path.join(tmp, "long.uu")
    name = "u" * 300 + ".bin"
    with open(p, "w") as f:
        f.write("begin 644 %s\n" % name)
        f.write("$86)C\n")            # "abc", one 3-byte line
        f.write("`\nend\n")
    out = os.path.join(tmp, "uuout")
    os.mkdir(out)
    _, err, rc = ours(macextract, ["x", "-o", out, p])
    got = written(out)
    check(problems, len(got) == 1 and 0 < len(got[0]) < len(name),
          "long.uu: wrote %r, wanted one file under a shortened name"
          % [len(g) for g in got])
    check(problems, len(noted(err)) == 1,
          "long.uu: the notice listed %r" % noted(err))
    # The name is on a line the 96-byte line buffer cannot hold, so it
    # is kept in the host's buffer as the line streams past rather than
    # dropped: the notice has all 304 bytes of it.
    check(problems, name in err,
          "long.uu: the notice does not carry the whole begin-line name")
    check(problems, rc == 0, "long.uu: exit was %d" % rc)
    return 1


def nested_folder_case(macextract, tmp, problems):
    """The other way a name reaches the cap: not one long name, but a
    path SUMMING past it. The Macintosh formats record one component per
    header — Now Compress at 31 bytes, DiskDoubler at 63, SuperDisk! at
    31 — so nine folders deep is enough, and no single name in the
    archive is remarkable.

    All three assemble the path through the shared `unc_path_leaf`, so
    what this exercises for Now Compress is the code the other two run
    (OPEN_ITEMS.md). Until 2026-08-27 that helper cut the path into its
    own 255-byte buffer as it descended, so the whole name was gone
    before any entry asked for it: the host was told a name had been
    shortened and never told what it was, and `name_full_len` reported
    the CUT length rather than the real one.

    Generated by tools/synth_now.py, whose archives `unar` reads —
    second_reader() below asks it for the same path."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import synth_now                                          # noqa: E402

    comp = "f" * 31                     # the longest component the format has
    payload = b"nine folders deep\n"
    node = synth_now.file("leaf.txt", data=payload)
    for _ in range(9):
        node = synth_now.folder(comp, [node])
    p, want = synth_now.write_one(tmp, "deep-now", [node])
    full = [n for n in want if want[n] is not None][0]
    if not check(problems, len(full) > CAP,
                 "deep-now.now: the generated path is only %d bytes"
                 % len(full)):
        return 1

    out = os.path.join(tmp, "deepout")
    os.mkdir(out)
    _, err, rc = ours(macextract, ["x", "-o", out, p])
    got = written(out)
    check(problems, len(got) == 1 and open(os.path.join(out, got[0]),
                                           "rb").read() == payload,
          "deep-now.now: wrote %r, wanted the one file" % got)
    # The cut path is 255 bytes, which is exactly the folder ABOVE the
    # leaf: shortening makes a file collide with a directory, and the
    # policy numbers it rather than losing it. So the written path is the
    # cap plus `~1`, and what has to hold is the filesystem's limit —
    # every component fits one directory entry.
    check(problems, got and max(len(c.encode("utf-8"))
                                for c in got[0].split("/")) <= 255,
          "deep-now.now: wrote a component longer than a directory entry")
    check(problems, len(noted(err)) == 2,
          "deep-now.now: the notice listed %d name(s), wanted the folder and "
          "the file under it" % len(noted(err)))
    check(problems, rc == 0, "deep-now.now: exit was %d" % rc)
    check(problems, full in err,
          "deep-now.now: the notice does not carry the whole %d-byte path; "
          "it says %r" % (len(full), noted(err)))
    check(problems, "cut before it reached us" not in err,
          "deep-now.now: the path is in the headers the walk is holding, so "
          "it is not one the engine can only report the length of")
    return 1


def dd_tree_cases(macextract, tmp, problems):
    """DiskDoubler's two directory walks, which no fixture exercises: the
    four real `DDAR` archives are flat and the five real `DDA2` ones hold
    one folder at one level, so `DDAR`'s isdir/enddir records and
    `DDA2`'s dirlevel counter were read from the reference and never run
    against a tree (OPEN_ITEMS.md, closed 2026-08-28).

    Two archives per walk. A TREE — folders inside folders, a file after
    a folder closes, a file at the root after that, a resource fork, and
    `DDAR`'s stored-in-the-record shape — which says the walk descends
    and pops where the reference does. And a DEEP chain of the longest
    component each format has, 63 bytes for `DDAR` and 31 for `DDA2`,
    which is the only way these formats reach the engine's 255-byte cap:
    every name in them is ordinary and it is the PATH that is too long.

    Written by tools/synth_dd.py and graded by `unar`, the implementation
    fmt_dd.c was transcribed from (second_reader() below)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import synth_dd                                           # noqa: E402

    ran = 0
    payload = b"deep in a DiskDoubler tree\n"
    tree = [
        synth_dd.folder("Alpha", [
            synth_dd.file("one.txt", data=b"one\n"),
            synth_dd.folder("Beta", [
                synth_dd.file("two.txt", data=b"two\n", stored=True),
                synth_dd.file("forked", data=b"data\n", rsrc=b"rsrc\n"),
            ]),
            synth_dd.file("three.txt", data=b"three\n"),
        ]),
        synth_dd.file("root.txt", data=b"root\n"),
        synth_dd.folder("Gamma", [
            synth_dd.file("four.txt", data=b"four\n", stored=True),
        ]),
    ]

    for kind, comp, depth in (("ddar", "f" * 63, 4), ("dda2", "g" * 31, 8)):
        p, want = synth_dd.write_one(tmp, "tree-dd-" + kind, tree, kind)
        out = os.path.join(tmp, "treeout-" + kind)
        os.mkdir(out)
        names, _, lrc = ours(macextract, ["l", p])
        _, err, rc = ours(macextract, ["x", "-o", out, p])
        check(problems, rc == 0 and lrc == 0,
              "tree-dd-%s: exit was %d listing, %d extracting"
              % (kind, lrc, rc))
        check(problems, sorted(names) == sorted(want),
              "tree-dd-%s: listed %r, wanted %r"
              % (kind, sorted(names), sorted(want)))
        for path, forks in sorted(want.items()):
            here = os.path.join(out, path)
            if forks is None:
                check(problems, os.path.isdir(here),
                      "tree-dd-%s: %s is not a directory" % (kind, path))
                continue
            data, rsrc = forks
            check(problems, os.path.exists(here)
                  and open(here, "rb").read() == data,
                  "tree-dd-%s: %s is not the data fork that went in"
                  % (kind, path))
            if rsrc:
                check(problems, os.path.exists(here + ".rsrc")
                      and open(here + ".rsrc", "rb").read() == rsrc,
                      "tree-dd-%s: %s has no resource fork" % (kind, path))
        ran += 1

        # The deep chain. `depth` components of `comp` sum to exactly the
        # cap, so the folder above the leaf is the longest path that fits
        # and the leaf under it is the first that does not — the same
        # place the Now Compress tree lands, reached through a different
        # header walk.
        node = synth_dd.file("leaf.txt", data=payload)
        for _ in range(depth):
            node = synth_dd.folder(comp, [node])
        p, want = synth_dd.write_one(tmp, "deep-dd-" + kind, [node], kind)
        full = [n for n in want if want[n] is not None][0]
        if not check(problems, len(full) > CAP,
                     "deep-dd-%s: the generated path is only %d bytes"
                     % (kind, len(full))):
            ran += 1
            continue
        out = os.path.join(tmp, "deepout-" + kind)
        os.mkdir(out)
        _, err, rc = ours(macextract, ["x", "-o", out, p])
        got = written(out)
        check(problems, len(got) == 1 and open(os.path.join(out, got[0]),
                                               "rb").read() == payload,
              "deep-dd-%s: wrote %r, wanted the one file" % (kind, got))
        check(problems, got and max(len(c.encode("utf-8"))
                                    for c in got[0].split("/")) <= 255,
              "deep-dd-%s: wrote a component longer than a directory entry"
              % kind)
        # The chain sums to EXACTLY the cap at the folder above the
        # leaf, so the folder is the longest path that still fits and
        # only the leaf is cut — and cutting it lands it on the folder's
        # own path, so what makes the file survive at all is the
        # numbering.
        check(problems, len(noted(err)) == 1,
              "deep-dd-%s: the notice listed %d name(s), wanted the leaf"
              % (kind, len(noted(err))))
        check(problems, got and got[0].endswith("~1"),
              "deep-dd-%s: the leaf collided with the folder it is in and "
              "was not numbered: %r" % (kind, got))
        check(problems, "numbered" in err,
              "deep-dd-%s: the notice does not say a name was numbered"
              % kind)
        check(problems, rc == 0, "deep-dd-%s: exit was %d" % (kind, rc))
        check(problems, full in err,
              "deep-dd-%s: the notice does not carry the whole %d-byte "
              "path; it says %r" % (kind, len(full), noted(err)))
        check(problems, "cut before it reached us" not in err,
              "deep-dd-%s: the path is in the headers the walk is holding, "
              "so it is not one the engine can only report the length of"
              % kind)
        ran += 1
    return ran


def applesingle_case(macextract, tmp, problems):
    """A name the ENGINE carries whole and the FILESYSTEM cannot: 200
    bytes of MacRoman are 400 bytes of UTF-8, and one directory entry
    takes 255. Hand-built, because nothing writes these any more.
    Source for the layout: AppleSingle/AppleDouble Developer's Note, the
    same header fmt_applesingle.c reads."""
    p = os.path.join(tmp, "longmac.as")
    name = bytes([0x8E]) * 200                  # MacRoman 'e acute'
    data = b"applesingle payload\n"
    entries = [(3, name), (1, data)]
    hdr = struct.pack(">II16xH", 0x00051600, 0x00020000, len(entries))
    off = len(hdr) + 12 * len(entries)
    descs = b""
    body = b""
    for eid, blob in entries:
        descs += struct.pack(">III", eid, off + len(body), len(blob))
        body += blob
    open(p, "wb").write(hdr + descs + body)

    out = os.path.join(tmp, "macout")
    os.mkdir(out)
    _, err, rc = ours(macextract, ["x", "-o", out, p])
    got = written(out)
    check(problems, len(got) == 1, "longmac.as: wrote %r" % got)
    if got:
        n = len(got[0].encode("utf-8"))
        check(problems, n <= 255,
              "longmac.as: wrote a %d-byte component; the filesystem takes "
              "255" % n)
        check(problems, open(os.path.join(out, got[0]), "rb").read() == data,
              "longmac.as: the extracted bytes are not the archive's")
    check(problems, "needs 400 bytes" in err,
          "longmac.as: the notice does not say what the name needed: %r"
          % noted(err))
    # The engine carried this one whole; only the filesystem could not
    # take it, so the notice has every character of it.
    check(problems, ("\u00e9" * 200) in err,
          "longmac.as: the notice does not carry the whole name as text")
    check(problems, rc == 0, "longmac.as: exit was %d" % rc)
    return 1


def streamed_directory_case(macextract, tmp, problems):
    """Where the whole name is NOT recoverable: a zip whose central
    directory does not fit the allocator's budget is read a record at a
    time, and the name is gone with the record. The notice must then
    give the LENGTH and say the text was lost before it reached us —
    never imply the shortened name is the archive's."""
    p = os.path.join(tmp, "bigdir.zip")
    long_name = "s" * 400 + ".txt"
    with zipfile.ZipFile(p, "w") as z:
        for i in range(500):                 # ~230 KB of central directory
            z.writestr("%03d/%s" % (i, long_name), b"x")
    out = os.path.join(tmp, "bigdirout")
    os.mkdir(out)
    _, err, rc = ours(macextract, ["x", "--budget", "65536", "-o", out, p])
    check(problems, len(written(out)) == 500,
          "bigdir.zip: wrote %d file(s) of 500" % len(written(out)))
    check(problems, rc == 0, "bigdir.zip: exit was %d" % rc)
    check(problems, "cut before it reached us" in err,
          "bigdir.zip: the notice does not say the name text was lost")
    check(problems, long_name not in err,
          "bigdir.zip: the notice claims a name the engine never had")
    return 1


def outdir_cases(macextract, tmp, problems):
    """The one limit that IS a refusal: no shortening of a name makes a
    path shorter than the directory it goes in, so a path past
    _PC_PATH_MAX is the filesystem's answer and not ours.

    Both sides: a deep output directory that still fits must extract
    normally, and one past PATH_MAX must be refused. The second has to
    be built by walking into it — the kernel will not take a path that
    long in one mkdir either, which is the whole point."""
    p = os.path.join(tmp, "plain.zip")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("short.txt", b"ok\n")

    deep = tmp
    for _ in range(5):                       # ~1 KB: legal, and used to
        deep = os.path.join(deep, "d" * 200)  # be refused by our own buffer
    os.makedirs(deep, exist_ok=True)
    _, err, rc = ours(macextract, ["x", "-o", deep, p])
    check(problems, os.path.exists(os.path.join(deep, "short.txt")),
          "outdir: a legal 1 KB output path was not written to")
    check(problems, rc == 0, "outdir: a legal deep path exited %d" % rc)

    here = os.getcwd()
    try:
        os.chdir(tmp)
        parts = [tmp]
        for _ in range(24):                  # past PATH_MAX (4096)
            os.mkdir("e" * 200)
            os.chdir("e" * 200)
            parts.append("e" * 200)
        toolong = "/".join(parts)
    finally:
        os.chdir(here)
    if check(problems, len(toolong) > 4096,
             "outdir: the over-long path is only %d bytes" % len(toolong)):
        _, err, rc = ours(macextract, ["x", "-o", toolong, p])
        check(problems, "longer than this filesystem takes" in err,
              "outdir: an over-long output path was not reported")
        check(problems, rc != 0, "outdir: an output path that does not fit "
                                 "exited 0")
    return 2


def second_reader(tmp, problems):
    """The subjects say what we think they say, according to something
    that is not this project. Skips politely where a tool is missing."""
    p = os.path.join(tmp, "long.zip")
    if shutil.which("unzip"):
        r = subprocess.run(["unzip", "-l", p], capture_output=True)
        out = r.stdout.decode("utf-8", "replace")
        check(problems, "y" * 200 in out,
              "long.zip: unzip does not see the long name we wrote")
    p = os.path.join(tmp, "long.tar")
    if shutil.which("tar"):
        r = subprocess.run(["tar", "tf", p], capture_output=True)
        out = r.stdout.decode("utf-8", "replace")
        check(problems, "p" * 155 in out,
              "long.tar: tar does not see the long name we wrote")
    # The nested path, from the implementation fmt_now.c was transcribed
    # from: XADMaster has no 255-byte cap, so what `lsar` lists is the
    # whole path our notice must carry.
    p = os.path.join(tmp, "deep-now.now")
    if shutil.which("lsar") and os.path.exists(p):
        r = subprocess.run(["lsar", p], capture_output=True)
        out = r.stdout.decode("utf-8", "replace")
        check(problems, ("f" * 31 + "/") * 9 + "leaf.txt" in out,
              "deep-now.now: lsar does not see the nested path we wrote")
    # Both DiskDoubler walks, from the same implementation fmt_dd.c was
    # transcribed from: it lists the tree it descended and the whole deep
    # path, and a disagreement about either is a disagreement between two
    # implementations rather than with the generator.
    for kind, comp, depth in (("ddar", "f" * 63, 4), ("dda2", "g" * 31, 8)):
        p = os.path.join(tmp, "tree-dd-%s.dd" % kind)
        if not shutil.which("lsar") or not os.path.exists(p):
            continue
        out = subprocess.run(["lsar", p],
                             capture_output=True).stdout.decode("utf-8",
                                                                "replace")
        listed = [ln.rstrip("/") for ln in out.splitlines()[1:]]
        # A resource fork is a second entry of the same name to `unar`
        # and one entry with two forks here, so the comparison is by set.
        want = {"Alpha", "Alpha/one.txt", "Alpha/Beta", "Alpha/Beta/two.txt",
                "Alpha/Beta/forked", "Alpha/three.txt", "root.txt",
                "Gamma", "Gamma/four.txt"}
        check(problems, set(listed) == want,
              "tree-dd-%s: lsar walked %r" % (kind, sorted(set(listed))))
        p = os.path.join(tmp, "deep-dd-%s.dd" % kind)
        out = subprocess.run(["lsar", p],
                             capture_output=True).stdout.decode("utf-8",
                                                                "replace")
        check(problems, (comp + "/") * depth + "leaf.txt" in out,
              "deep-dd-%s: lsar does not see the nested path we wrote"
              % kind)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract", default="build/macextract")
    args = ap.parse_args()

    problems = []
    ran = 0
    tmp = tempfile.mkdtemp()
    try:
        ran += zip_cases(args.macextract, tmp, problems)
        ran += tar_case(args.macextract, tmp, problems)
        ran += uu_case(args.macextract, tmp, problems)
        ran += nested_folder_case(args.macextract, tmp, problems)
        ran += dd_tree_cases(args.macextract, tmp, problems)
        ran += applesingle_case(args.macextract, tmp, problems)
        ran += streamed_directory_case(args.macextract, tmp, problems)
        ran += outdir_cases(args.macextract, tmp, problems)
        second_reader(tmp, problems)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("NAMES FAIL " + p)
    print("names: %d case(s) checked, %d problem(s)" % (ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
