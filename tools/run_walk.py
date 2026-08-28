#!/usr/bin/env python3
"""run_walk.py — the listing walk, the extracting walk and a skipping one
must offer the same entries, in the same order.

Every other suite here compares the OUTPUT of one walk. Three walks
exist and nothing had ever held them against each other:

  list   `UncOptions.list_only`: containers parsed, nothing decoded.
  full   an ordinary extraction.
  alt    an extraction that skips every second entry — the shape a
         selection has, and the one no host had ever produced until
         `--only` (DECISIONS.md 2026-08-28).

The rule is that all three offer `begin_entry` the same entries with the
same identity — name, is_dir, type, creator and both fork sizes — in the
same order. `tools/walk_probe.c` measures; this applies the rule.

Why it is worth a suite of its own:

  * a listing that disagreed with the extraction is a bug no diff suite
    can see, because a diff suite never looks at the listing. It is
    already on record for MacLHA, whose MacBinary peek has to run in
    listing or the entry's very NAME is wrong (DECISIONS.md, *MacLHA is
    the Macintosh half*);
  * `--only NAME` matches a name the listing printed against an entry
    the extraction offers, so list == full is its premise;
  * a selection keyed by walk ORDINAL — what a Mac list window would do,
    names being neither unique nor always printable — is wrong the
    moment a skip perturbs the sequence. `alt` asks that directly, and
    it is the assertion with no other home: every format's skip branch
    is now exercised on every archive in the corpus.

Envelopes are unwrapped on the way in, because a fixture like
`Archive.sit.bin` is a ONE-entry MacBinary wrapper and probing it says
nothing about the StuffIt walk inside. Each layer is probed, and the
descent stops where a layer yields something other than exactly one
recognised archive.

What this CANNOT see:

  * whether the entries are RIGHT. It compares three of our walks with
    each other; that they agree on a wrong name is invisible here and
    is the differential suite's subject.
  * the decoded bytes. `alt` skips half the entries, so this says
    nothing about what a skipped entry would have produced — that is
    `tools/run_only.py`, which compares a selection against a full
    extraction byte for byte.
  * segmented sets. A part on its own ends the walk with
    UNC_ERR_SEGMENTED and no entries, which agrees trivially; joining a
    set needs a volume source the probe does not build.
  * a walk that is wrong in the same way three times. The skip pattern
    is positional (every second entry), so a format that lost track of
    its position in a way that happens to repeat every two entries
    would pass.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

MAX_DEPTH = 8


def sniff(mac, path):
    """The format name, or None when nothing is recognised."""
    r = subprocess.run([mac, "sniff", path], capture_output=True, text=True)
    name = r.stdout.strip()
    return name if r.returncode == 0 and name and name != "unknown" else None


def layers(mac, path, tmp):
    """`path` and every archive found by peeling envelopes off it.

    The descent is by RESULT, not by a list of envelope formats: a layer
    that yields exactly one file which is itself a recognised archive is
    an envelope, whatever it is called. -nr stops the CLI doing the same
    thing itself, one layer at a time, so each is probed."""
    out = [path]
    cur = path
    for depth in range(MAX_DEPTH):
        if sniff(mac, cur) is None:
            break
        into = os.path.join(tmp, "peel%d" % depth)
        os.mkdir(into)
        subprocess.run([mac, "x", "-nr", cur, "-o", into],
                       capture_output=True)
        got = []
        for root, _, files in os.walk(into):
            got += [os.path.join(root, f) for f in files]
        # Exactly one file, and it is an archive: an envelope. A
        # resource-fork sidecar is part of the same one file.
        got = [g for g in got if not g.endswith(".rsrc")]
        if len(got) != 1 or sniff(mac, got[0]) is None:
            break
        cur = got[0]
        out.append(cur)
    return out


def probe(binary, paths):
    """{path: (rets, counts, lf, af)} for a batch of archives."""
    rows = {}
    for i in range(0, len(paths), 32):
        batch = paths[i:i + 32]
        r = subprocess.run([binary] + batch, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit("run_walk: probe failed on %s: %s"
                             % (batch[0], r.stderr.strip()))
        for line in r.stdout.splitlines():
            if line.endswith(" oom"):
                rows[line[:-4]] = None
                continue
            # The path may contain spaces; the four fields never do.
            parts = line.rsplit(" ", 4)
            if len(parts) != 5:
                raise SystemExit("run_walk: unparsable line: " + line)
            vals = dict(kv.split("=", 1) for kv in parts[1:])
            rows[parts[0]] = (vals["ret"], vals["n"], vals["lf"], vals["af"])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", default=os.path.join(REPO, "build/walk_probe"))
    ap.add_argument("--macextract",
                    default=os.path.join(REPO, "build/macextract"))
    ap.add_argument("--fixtures", default=os.path.join(REPO, "fixtures"))
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N fixtures (0 = all of them)")
    args = ap.parse_args()

    if not os.path.isfile(args.probe):
        print("run_walk: no %s — skipping" % args.probe)
        return 0
    if not os.path.isdir(args.fixtures):
        print("run_walk: no fixtures — skipping")
        return 0

    names = sorted(n for n in os.listdir(args.fixtures)
                   if not n.endswith(".md")
                   and os.path.isfile(os.path.join(args.fixtures, n)))
    if args.limit:
        names = names[:args.limit]
    if not names:
        print("run_walk: no fixtures — skipping")
        return 0

    problems = []
    walked = empty = peeled = 0
    tmp = tempfile.mkdtemp()
    try:
        for n in names:
            path = os.path.join(args.fixtures, n)
            work = os.path.join(tmp, "w")
            os.mkdir(work)
            try:
                chain = layers(args.macextract, path, work)
                peeled += len(chain) - 1
                for p, row in probe(args.probe, chain).items():
                    shown = n if p == path else n + " -> " + os.path.basename(p)
                    if row is None:
                        problems.append("%s: the probe ran out of memory"
                                        % shown)
                        continue
                    rets, counts, lf, af = row
                    if counts == "0,0,0":
                        empty += 1
                        continue
                    walked += 1
                    if lf != "-":
                        problems.append(
                            "%s: the listing walk and the extracting walk "
                            "differ at entry %s (n=%s, ret=%s)"
                            % (shown, lf, counts, rets))
                    if af != "-":
                        problems.append(
                            "%s: skipping every second entry changed the "
                            "walk at entry %s (n=%s, ret=%s)"
                            % (shown, af, counts, rets))
            finally:
                shutil.rmtree(work, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("WALK FAIL " + p)
    print("walk: %d archive(s) walked three ways, %d envelope layer(s) "
          "peeled, %d with no entries, %d problem(s)"
          % (walked, peeled, empty, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
