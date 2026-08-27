#!/usr/bin/env python3
"""run_names.py — names longer than the engine can carry.

`UncEntryInfo.name` is UNC_NAME_MAX (255) bytes plus a terminator, and
the struct goes on a 68000 stack with a 4 KB budget, so a longer name
cannot be carried. Until 2026-08-27 it was CUT and nothing said so: a
457-byte path listed and extracted as 255 bytes, exit 0, under a name
that was not the archive's. The engine now sets `name_truncated` and the
CLI treats it as a per-entry failure — the entry is not written, the
others are, and the run exits non-zero.

The subjects are generated, because **the longest name in 932 fixtures
is 120 bytes** — less than half the cap, so the differential suite and
its 9,320 variants could not have failed on this.

Graded by readers that have no such limit: CPython's `zipfile` and
`tarfile`, which wrote the archives and give the names that were meant,
and `unzip -l` / `tar tf` where they are installed.

There is a fifth case for the CLI's own cap — `outdir/name` in a
1024-byte buffer — because a host that cuts the path it writes to is the
same defect one layer up.

Three carriers, because the cap is applied in three different places:
zip clamps the name as it reads the central directory, tar builds
`prefix + '/' + name` and hands the result to the shared path funnel
(155 + 1 + 100 = 256 is one byte over, which the FORMAT can express and
this engine cannot), and uuencode's "begin" line goes through the other
funnel, `unc_entry_set_name`.

uuencode also shows that UNC_NAME_MAX is not the only cap a name can
meet: its "begin" line is read through a 96-byte line buffer, so a long
name is cut there first. That is reported the same way — which is the
point, since a host cannot tell the two apart and does not need to.

What this CANNOT see: the Macintosh formats' own path builders
(StuffIt, Compact Pro, DiskDoubler, SuperDisk!, Now), which reach the
cap only by nesting folders deep enough to sum past 255 bytes. Nothing
here synthesises one of those containers; their builders set the same
flag, and the code path is shared with tar's from `unc_entry_set_path`
down. The Mac application does not consume the flag at all — names
there are shortened to 31 characters per component by policy
(OPEN_ITEMS.md).
"""
import argparse
import os
import shutil
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


def refused(stderr, name):
    """Did the CLI name this entry as one it would not write?"""
    for line in stderr.splitlines():
        if "longer than" in line and line.split(": ")[1].startswith(name[:60]):
            return True
    return False


def check(problems, cond, msg):
    if not cond:
        problems.append(msg)
    return cond


def zip_cases(macextract, tmp, problems):
    ran = 0

    # 1. One entry the engine cannot name, one it can. The second is the
    #    point: a refusal must not cost the entries around it.
    p = os.path.join(tmp, "long.zip")
    long_name = "d/" + "x" * 250 + "/" + "y" * 200 + ".txt"
    payload = b"the entry that can be named\n"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(long_name, b"the entry that cannot\n")
        z.writestr("short.txt", payload)
    if check(problems, len(zipfile.ZipFile(p).namelist()) == 2,
             "long.zip: the generator did not write two entries"):
        names, err, rc = ours(macextract, ["l", p])
        check(problems, len(names) == 2,
              "long.zip: listing showed %d entries, wanted 2" % len(names))
        check(problems, refused(err, "d/" + "x" * 20),
              "long.zip: listing did not say the name was too long")
        check(problems, rc != 0, "long.zip: listing a name it cannot carry "
                                 "exited 0")
        out = os.path.join(tmp, "longout")
        os.mkdir(out)
        _, err, rc = ours(macextract, ["x", "-o", out, p])
        got = []
        for root, _, files in os.walk(out):
            for f in files:
                got.append(os.path.relpath(os.path.join(root, f), out))
        check(problems, got == ["short.txt"],
              "long.zip: extracted %r, wanted only short.txt" % got)
        check(problems, rc != 0, "long.zip: extraction exited 0")
        if got == ["short.txt"]:
            check(problems,
                  open(os.path.join(out, "short.txt"), "rb").read() == payload,
                  "long.zip: the entry that survived is not byte-exact")
    ran += 1

    # 2. The boundary, both sides, in one archive: 255 bytes is carried
    #    whole, 256 is one byte too many.
    p = os.path.join(tmp, "edge.zip")
    at_cap = "a" * (CAP - 4) + ".txt"          # exactly 255
    over = "b" * (CAP - 3) + ".txt"            # exactly 256
    body = b"edge\n"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(at_cap, body)
        z.writestr(over, body)
    if check(problems, len(at_cap) == CAP and len(over) == CAP + 1,
             "edge.zip: the subject does not straddle the cap"):
        out = os.path.join(tmp, "edgeout")
        os.mkdir(out)
        _, err, rc = ours(macextract, ["x", "-o", out, p])
        check(problems, os.path.exists(os.path.join(out, at_cap)),
              "edge.zip: a name of exactly %d bytes was not written" % CAP)
        check(problems, not refused(err, at_cap),
              "edge.zip: a name of exactly %d bytes was refused" % CAP)
        check(problems, refused(err, over),
              "edge.zip: a name of %d bytes was not refused" % (CAP + 1))
        check(problems, rc != 0, "edge.zip: extraction exited 0")
    ran += 1
    return ran


def tar_cases(macextract, tmp, problems):
    """ustar splits a path into a 155-byte prefix and a 100-byte name, so
    it can state 256 bytes — one more than this engine carries."""
    ran = 0
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
              "long.tar: the 255-byte member was not written")
        check(problems, refused(err, over[:60]),
              "long.tar: the 256-byte member was not refused")
        check(problems, rc != 0, "long.tar: extraction exited 0")
    ran += 1
    return ran


def outdir_case(macextract, tmp, problems):
    """The CLI's own cap: `outdir/name` goes into a 1024-byte buffer, and
    a path that does not fit used to be cut — writing one file under
    another's name, the same failure the engine's cap had."""
    deep = tmp
    for _ in range(5):
        deep = os.path.join(deep, "d" * 200)
    os.makedirs(deep, exist_ok=True)
    p = os.path.join(tmp, "plain.zip")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("short.txt", b"ok\n")
    _, err, rc = ours(macextract, ["x", "-o", deep, p])
    check(problems, "too long" in err,
          "outdir: an output path over 1024 bytes was not reported")
    check(problems, rc != 0, "outdir: an output path that does not fit "
                             "exited 0")
    check(problems, not os.path.exists(os.path.join(deep, "short.txt")),
          "outdir: a file was written under a path that did not fit")
    return 1


def uu_cases(macextract, tmp, problems):
    """uuencode's name is one line of text, and it reaches the OTHER
    funnel — unc_entry_set_name, which every Mac format uses."""
    ran = 0
    p = os.path.join(tmp, "long.uu")
    name = "u" * 300 + ".bin"
    with open(p, "w") as f:
        f.write("begin 644 %s\n" % name)
        f.write("$86)C\n")            # "abc", one 3-byte line
        f.write("`\nend\n")
    names, err, rc = ours(macextract, ["l", p])
    check(problems, len(names) == 1,
          "long.uu: listed %d entries, wanted 1" % len(names))
    # uuencode's cap is reached before UNC_NAME_MAX is: the "begin" line
    # goes through a 96-byte line buffer, so the name is cut there. What
    # matters is that a cut name is REPORTED, whichever cap cut it.
    check(problems, names and 0 < len(names[0]) < len(name),
          "long.uu: the listed name is %d bytes, wanted a cut one under %d"
          % (len(names[0]) if names else -1, len(name)))
    check(problems, refused(err, "u" * 60),
          "long.uu: the cut name was not reported")
    check(problems, rc != 0, "long.uu: exited 0 on a name it cut")
    ran += 1
    return ran


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract", default="build/macextract")
    args = ap.parse_args()

    problems = []
    ran = 0
    tmp = tempfile.mkdtemp()
    try:
        ran += zip_cases(args.macextract, tmp, problems)
        ran += tar_cases(args.macextract, tmp, problems)
        ran += uu_cases(args.macextract, tmp, problems)
        ran += outdir_case(args.macextract, tmp, problems)
        second_reader(tmp, problems)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("NAMES FAIL " + p)
    print("names: %d case(s) checked, %d problem(s)" % (ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
