#!/usr/bin/env python3
"""envelopes.py — reach the archive inside the wrapper.

A probe that opens a corpus fixture usually opens a WRAPPER. Real
Macintosh archives travelled as `Archive.sit.hqx` and `Archive.cpt.bin`,
and 419 of the 932 fixtures here are one envelope or more deep — so a
suite that measures a property of "the fixture" measures BinHex's answer
to it, over and over, and never asks the StuffIt walk inside anything at
all.

That is a blind spot two suites had and neither wrote down: `run_walk.py`
was built with the peeling and `run_ticks.py` was not, which is why this
module exists rather than a second copy of it.

The descent is by RESULT, not by a list of envelope formats: a layer
that yields exactly one file which is itself a recognised archive is an
envelope, whatever it is called. `-nr` stops the CLI doing the same
thing itself, so each layer is handed back separately.
"""
import os
import subprocess

MAX_DEPTH = 8


def sniff(macextract, path):
    """The format name `sniff` prints, or None when nothing is
    recognised."""
    r = subprocess.run([macextract, "sniff", path],
                       capture_output=True, text=True)
    name = r.stdout.strip()
    return name if r.returncode == 0 and name and name != "unknown" else None


def layers(macextract, path, workdir):
    """`path`, then every archive found by peeling envelopes off it.

    `workdir` must exist and is the caller's to remove; the peeled files
    live under it and are only valid until it goes."""
    out = [path]
    cur = path
    for depth in range(MAX_DEPTH):
        if sniff(macextract, cur) is None:
            break
        into = os.path.join(workdir, "peel%d" % depth)
        os.mkdir(into)
        subprocess.run([macextract, "x", "-nr", cur, "-o", into],
                       capture_output=True)
        got = []
        for root, _, files in os.walk(into):
            got += [os.path.join(root, f) for f in files]
        # Exactly one file, and it is an archive: an envelope. A
        # resource-fork sidecar is part of that same one file.
        got = [g for g in got if not g.endswith(".rsrc")]
        if len(got) != 1 or sniff(macextract, got[0]) is None:
            break
        cur = got[0]
        out.append(cur)
    return out
