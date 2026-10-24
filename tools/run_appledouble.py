#!/usr/bin/env python3
"""run_appledouble.py — a loose AppleDouble header joined to its data file.

An AppleDouble header carries a file's Finder info, resource fork and the
rest, and leaves the data fork in a second file beside it (RFC 1740). The
CLI looks for that file by the header's own name — "._NAME", "%NAME" and
"NAME.ad" all point at NAME (unc_appledouble_data_name) — hands it to the
engine as `UncOptions.data_fork`, and names the entry after it where the
header has no real-name entry. This grades that, against bytes the suite
itself put in: the headers are generated here, from RFC 1740's layout.

    run_appledouble.py --macextract build/san/macextract

Each case states what it would mean if it failed. The inputs are hashed
before and after every run: whatever the CLI writes, it must not touch
them, and one case extracts into the header's own folder to make it try:
the CLI refuses there rather than overwrite, as it does for any name.

What this CANNOT see: the Macintosh application, whose half is its own
shell code (tools/vmac/as703.py --set adext, by hand on Mac OS 9.2);
and a data file the host failed to find for a reason this filesystem
does not have, such as a name longer than HFS's 31 characters.
"""
import argparse, hashlib, os, shutil, struct, subprocess, sys, tempfile

RSRC = b"\x00\x00\x01\x00" + b"resource fork of the header" + bytes(9)
DATA = b"the data fork, from the file beside the header\n"
FINFO = b"TEXTttxt" + bytes(24)


def header(name=None, data=None):
    """An AppleDouble header (or AppleSingle, with `data`)."""
    ents = [(9, FINFO), (2, RSRC)]
    if name:
        ents.append((3, name))
    if data is not None:
        ents.append((1, data))
    magic = 0x00051600 if data is not None else 0x00051607
    head = struct.pack(">II16sH", magic, 0x00020000, bytes(16), len(ents))
    off = len(head) + 12 * len(ents)
    table, body = b"", b""
    for eid, b in ents:
        table += struct.pack(">III", eid, off + len(body), len(b))
        body += b
    return head + table + body


def tree(d):
    return {os.path.relpath(os.path.join(r, f), d):
            hashlib.sha256(open(os.path.join(r, f), "rb").read()).hexdigest()
            for r, _, fs in os.walk(d) for f in fs}


def run_case(cli, work, case):
    name, files, outdir_is_src, want = case
    src = os.path.join(work, name, "in")
    os.makedirs(src)
    for fn, blob in files:
        p = os.path.join(src, fn)
        if blob is None:
            os.makedirs(p)
        else:
            open(p, "wb").write(blob)
    before = tree(src)
    out = src if outdir_is_src else os.path.join(work, name, "out")
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([cli, "x", "--forks", "hidden", "-o", out,
                        os.path.join(src, files[0][0])],
                       capture_output=True, text=True)
    problems = []
    if want is None:
        # The CLI does not overwrite: a joined file that would land on
        # an existing one is refused, and says so.
        if r.returncode == 0:
            problems.append("wrote over an existing name without refusing")
        want = {}
    elif r.returncode != 0:
        problems.append("exit %d: %s" % (r.returncode, r.stderr.strip()[:160]))
    after = tree(src)
    for k, h in before.items():
        if after.get(k) != h:
            problems.append("input %s was changed" % k)
    got = tree(out)
    if outdir_is_src:
        got = {k: v for k, v in got.items() if k not in before}
    for fn, blob in want.items():
        h = hashlib.sha256(blob).hexdigest()
        if got.get(fn) != h:
            problems.append("%s: %s" % (fn, "missing" if fn not in got
                                        else "wrong bytes"))
    extra = set(got) - set(want)
    if extra:
        problems.append("unexpected output %s" % sorted(extra))
    return problems


def cases():
    bare = header()
    named = header(b"Kept Whole")
    joined = {"Note": DATA, "._Note": RSRC}
    return [
        ("dotunderscore", [("._Note", bare), ("Note", DATA)], False, joined),
        ("percent", [("%Note", bare), ("Note", DATA)], False, joined),
        ("dot-ad", [("Note.ad", bare), ("Note", DATA)], False, joined),
        # A real-name entry outranks the data file's name.
        ("real-name", [("._Note", named), ("Note", DATA)], False,
         {"Kept Whole": DATA, "._Kept Whole": RSRC}),
        # Nothing beside it: today's behaviour, the header alone.
        ("alone", [("._Note", bare)], False,
         {"._Note": b"", "._._Note": RSRC}),
        # A FOLDER of that name is not a data file.
        ("folder", [("._Note", bare), ("Note", None)], False,
         {"._Note": b"", "._._Note": RSRC}),
        # AppleSingle holds its own data fork; the file beside is not it.
        ("applesingle", [("._Note", header(data=b"own")), ("Note", DATA)],
         False, {"._Note": b"own", "._._Note": RSRC}),
        # Into the header's own folder, where the data file already is:
        # the joined file would land on it, and the CLI refuses rather
        # than overwrite. The inputs must come through untouched.
        ("same-folder", [("._Note", bare), ("Note", DATA)], True, None),
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--macextract", default="build/dev/macextract")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    work = tempfile.mkdtemp(prefix="appledouble-")
    fails = 0
    try:
        for case in cases():
            problems = run_case(a.macextract, work, case)
            for p in problems:
                print("FAIL %s: %s" % (case[0], p))
            fails += bool(problems)
    finally:
        if a.keep:
            print("kept: %s" % work)
        else:
            shutil.rmtree(work, ignore_errors=True)
    print("appledouble: %d case(s) checked, %d problem(s)"
          % (len(cases()), fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
