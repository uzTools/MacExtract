#!/usr/bin/env python3
"""synth_deep.py — archives nested PAST `UNC_PATH_MAXDEPTH`.

`unc_path_push` refuses to descend at depth 24. Nothing on this disk
reaches it: the deepest folder nesting any archive here has is 4, in
`Sys 7 for MA 2.0.1.pkg` (FORMATS.md, *How deep anything actually
nests*), so what the five walk sites do at the limit was read from the
code and never run. This writes the archives that run it.

The tree is the same for every format, and it is shaped to tell three
failures apart rather than just to go deep:

    D01/f01.txt                     a file at every level, so the
    D01/D02/f02.txt                 reported depth of the deepest one
    ...                             says where descending stopped
    D01/../D30/f30.txt
    D01/../D30/t30.txt              a TRAILER at every level, emitted
    D01/../D29/t29.txt              after that level's subtree closes
    ...
    D01/t01.txt
    after.txt                       a sentinel at the ROOT, emitted last

Folder names are three characters, so a 30-deep path is 119 bytes and
stays inside `UNC_NAME_MAX`: depth is then the only thing being varied,
and a cut NAME cannot be mistaken for a refused push (that question is
`tools/run_names.py`'s, on `synth_sd.nest()`'s 31-character names).

What each part catches:

  * `fNN` past 24 report the engine's answer to a path it cannot
    represent — the subject of the rule.
  * `tNN` catch an UNBALANCED POP. Four of the five walks pop by a
    COUNT (a marker record, or a level counter), so a push that was
    refused and a pop that still happens leave the walk shallower than
    it should be, and every trailer after it is reported inside a real
    folder it is not in. A trailer in the wrong folder is silent: the
    path is plausible and nothing about it looks truncated.
  * `after.txt` catches the same thing where the arithmetic happens to
    cancel. `unc_path_pop` clamps at depth 0, so a walk that over-pops
    by fewer levels than it has left still lands the root sentinel at
    the root; the trailers are what sees it, and this says whether the
    clamp was doing the hiding.

What this CANNOT see:

  * whether any real archive is ever this deep. It is a generator; the
    corpus measurement is `tools/measure_depth.py` and the answer there
    is no.
  * whether these record shapes are what each application would write.
    They are the shapes the existing `tools/synth_*.py` builders write,
    with their own provenance; nesting them deeper invents no field.
    For SuperDisk! there is no second reader off the Macintosh at all
    (`tools/synth_sd.py`).
  * anything about `unc_entry_path_append`, which is how StuffIt and
    Compact Pro carry a path. They have no `UNC_PATH_MAXDEPTH`.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MAXDEPTH = 24                 # UNC_PATH_MAXDEPTH, src/unc_internal.h
DEFAULT_DEPTH = 30            # past it, with room for the overshoot to show


def _payload(d, tag):
    return ("%s at level %d\n" % (tag, d)).encode("ascii")


def plan(depth):
    """(folders, files) the archive declares, as the paths a reader that
    could represent them would report. Folders first at each level, then
    that level's file, then the subtree, then the trailer."""
    folders, files = [], []
    for d in range(1, depth + 1):
        here = "/".join("D%02d" % i for i in range(1, d + 1))
        folders.append(here)
        files.append(here + "/f%02d.txt" % d)
    for d in range(depth, 0, -1):
        here = "/".join("D%02d" % i for i in range(1, d + 1))
        files.append(here + "/t%02d.txt" % d)
    files.append("after.txt")
    return folders, files


# ------------------------------------------------------------------
# DiskDoubler, both containers: a tree for tools/synth_dd.py
# ------------------------------------------------------------------

def dd_tree(depth, mod):
    """`mod` is the synth_dd or synth_now module — both take the same
    {folder,file} tree."""
    def level(d):
        kids = [mod.file("f%02d.txt" % d, data=_payload(d, "file"))]
        if d < depth:
            kids.append(level(d + 1))
        kids.append(mod.file("t%02d.txt" % d, data=_payload(d, "trailer")))
        return mod.folder("D%02d" % d, kids)
    return [level(1), mod.file("after.txt", data=b"at the root\n")]


# ------------------------------------------------------------------
# AppleLink package: a flat item list carrying a level per item
# ------------------------------------------------------------------

def sqp_items(depth, mod):
    items = []
    for d in range(1, depth + 1):
        items.append(mod.item("D%02d" % d, folder=True, level=d))
        items.append(mod.item("f%02d.txt" % d, data=_payload(d, "file"),
                              level=d + 1))
    for d in range(depth, 0, -1):
        items.append(mod.item("t%02d.txt" % d, data=_payload(d, "trailer"),
                              level=d + 1))
    items.append(mod.item("after.txt", data=b"at the root\n", level=1))
    return items


# ------------------------------------------------------------------
# SuperDisk!: a record stream, with every unread field borrowed from a
# real archive exactly as tools/synth_sd.py does it
# ------------------------------------------------------------------

def sd_stream(depth, mod, orig):
    dirinfo, finfo, blocks, _dlen = mod.borrow(orig)
    body = b""
    for d in range(1, depth + 1):
        body += mod._tag8(0x29) + mod._pstr(("D%02d" % d).encode()) + dirinfo
        body += (mod._tag8(0x28) + mod._pstr(("f%02d.txt" % d).encode())
                 + finfo + blocks)
    for d in range(depth, 0, -1):
        body += (mod._tag8(0x28) + mod._pstr(("t%02d.txt" % d).encode())
                 + finfo + blocks)
        body += mod._tag8(0x2A)                    # up out of D%02d
    body += (mod._tag8(0x28) + mod._pstr(b"after.txt") + finfo + blocks)
    return orig[:8] + body + mod._tag8(0x27)


# ------------------------------------------------------------------

def write(outdir, depth=DEFAULT_DEPTH, sd_payload=None):
    """Write one archive per walk site. Returns {path: kind}."""
    import synth_dd                                           # noqa: E402
    import synth_now                                          # noqa: E402
    import synth_sqp                                          # noqa: E402

    made = {}
    for kind in ("ddar", "dda2"):
        p = os.path.join(outdir, "deep-dd-%s.dd" % kind)
        with open(p, "wb") as fh:
            fh.write(synth_dd.build_ddar(dd_tree(depth, synth_dd))
                     if kind == "ddar"
                     else synth_dd.build_dda2(dd_tree(depth, synth_dd)))
        made[p] = kind

    p = os.path.join(outdir, "deep-now.now")
    with open(p, "wb") as fh:
        fh.write(synth_now.build_archive(dd_tree(depth, synth_now)))
    made[p] = "now"

    p = os.path.join(outdir, "deep-sqp.pkg")
    with open(p, "wb") as fh:
        fh.write(synth_sqp.build(sqp_items(depth, synth_sqp), version=1))
    made[p] = "sqp"

    if sd_payload:
        import synth_sd                                       # noqa: E402
        orig = open(sd_payload, "rb").read()
        p = os.path.join(outdir, "deep-sd.x")
        with open(p, "wb") as fh:
            fh.write(sd_stream(depth, synth_sd, orig))
        made[p] = "superdisk"
    return made


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir")
    ap.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    ap.add_argument("--sd-payload",
                    help="an unwrapped SuperDisk! archive whose unread "
                         "fields and blocks are borrowed (SD! Utilities.x)")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    folders, files = plan(a.depth)
    made = write(a.outdir, a.depth, a.sd_payload)
    for p, kind in sorted(made.items()):
        print("%-28s %-10s %7d B" % (os.path.basename(p), kind,
                                     os.path.getsize(p)))
    print("declares %d folders, %d files, deepest %d"
          % (len(folders), len(files), a.depth))
    return 0


if __name__ == "__main__":
    sys.exit(main())
