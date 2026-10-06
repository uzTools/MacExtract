#!/usr/bin/env python3
"""run_sit14wrap.py — the method-14 fork that wraps the window, graded.

`fixtures/synth-sit14.sit` covers four shapes and none of them reaches
the second half of `sit14_flush`: the window is sized to the fork
(`sit14_winsize`), so a flush straddles the end of it only once the
output has passed 0x40000 B, and the four fixture entries decode to
18,389 B all told. `tools/synth_sit14.py --wrap` adds a fifth entry
whose fork is 278,896 B for 458 B of stream — seventeen maximum matches
— and this is what adjudicates it.

Why it is not a fifth entry in the fixture: a 256 KB window is a
peak-RAM figure (FORMATS.md), a budget-sweep row and a Macintosh tier,
and none of those should move to cover a branch (DECISIONS.md
2026-10-06). So the archive is generated here, the way run_now.py
generates the Now Compress shapes the corpus lacks, and graded THREE
ways: the bytes that went into the encoder, what `unar` extracts
(XADMaster's SIT_14 being what sit14.c was transcribed from), and what
this CLI extracts.

It also asks whether the archive still WRAPS, which no byte comparison
can see: an encoder change that shortened the fork, or a window constant
that grew, would leave every byte agreeing and cover nothing. The
straddle is recomputed here from `SIT14_WINDOW`/`SIT14_WINMIN` as they
are spelled in `src/sit14.c`, so a change to either fails this suite
instead of silently costing the branch.

WHAT IT CANNOT SEE:

  * The flush SCHEDULE is mirrored in Python, not read from the engine:
    `flush_points` below is a transcription of sit14.c's `pos - flushed
    >= win >> 2`. It reads the two window constants out of the source,
    so those cannot drift, but a change to the THRESHOLD or to where
    the flush is called would make this check stale — and a stale check
    here says "wraps" while the branch goes uncovered. What actually
    measures the branch is `tools/fuzz_cover.py --detail "StuffIt method
    14"`, and `sit14_flush`'s line percentage is the number to re-read
    (TESTING.md, *StuffIt method 14*).
  * Correctness only, on ONE archive. It is not a fuzz run: mutants of
    this seed are `fuzz.py`'s stream generator, shape `sit14-wrap`.
  * Nothing here runs on the Macintosh. `tests/run_mac_sink.sh` carries
    the 1,859 B fixture, not this archive — a 256 KB window is more than
    the 1 MB tier has to spare (OPEN_ITEMS.md).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth_sit14                                   # noqa: E402


def window_constants():
    """SIT14_WINDOW and SIT14_WINMIN as src/sit14.c spells them."""
    src = open(os.path.join(ROOT, "src", "sit14.c")).read()
    out = {}
    for name in ("SIT14_WINDOW", "SIT14_WINMIN"):
        m = re.search(r"#define\s+%s\s+(0x[0-9a-fA-F]+|\d+)u?" % name, src)
        if not m:
            return None, "src/sit14.c no longer defines %s" % name
        out[name] = int(m.group(1), 0)
    return out, None


def flush_points(script, window, winmin):
    """Every (from, to) sit14.c hands to sit14_flush for `script`, and
    whether it straddles the end of the window. A transcription of the
    decoder's loop: the window doubles from SIT14_WINMIN to the fork
    length and is capped at SIT14_WINDOW, the threshold is a quarter of
    it, and the flush happens before each symbol."""
    outlen = sum(1 if it[0] == "lit" else it[1] for it in script)
    win = winmin
    while win < outlen and win < window:
        win <<= 1
    thresh = win >> 2
    pos, flushed, out = 0, 0, []
    for it in script:
        if pos - flushed >= thresh:
            out.append((flushed, pos))
            flushed = pos
        pos += 1 if it[0] == "lit" else it[1]
    out.append((flushed, pos))
    return win, [(f, t, (f & (win - 1)) + (t - f) > win)
                 for f, t in out if t > f]


def forks(root, path, who):
    """What one extractor wrote for `path`. Neither implementation
    writes a data file for an entry with an empty data fork, and none of
    these entries has a resource fork at all."""
    full = os.path.join(root, path)
    return open(full, "rb").read() if os.path.isfile(full) else b""


def command(who, macextract, archive, out):
    if who == "unar":
        return ["unar", "-q", "-f", "-nr", "-D", "-k", "hidden", "-o", out,
                archive]
    return [macextract, "x", "-o", out, archive]


def check_wraps(problems):
    """The archive's fifth entry must still straddle the window end, and
    the four fixture shapes must still NOT — if they did, the fixture
    would cover the branch and this suite would be dead weight."""
    consts, err = window_constants()
    if err:
        problems.append(err)
        return 0
    window, winmin = consts["SIT14_WINDOW"], consts["SIT14_WINMIN"]
    ran = 0
    for name, blocks in synth_sit14.cases(wrap=True):
        script = [it for b, _nested in blocks for it in b]
        win, points = flush_points(script, window, winmin)
        wraps = [p for p in points if p[2]]
        ran += 1
        if name == "window-wrap":
            if not wraps:
                problems.append(
                    "the window-wrap entry no longer wraps: window %d, "
                    "%d flush(es) %s — sit14_flush's second half is "
                    "covered by nothing"
                    % (win, len(points), [p[:2] for p in points]))
            elif len(wraps) < 1 or wraps[0][1] >= sum(
                    1 if it[0] == "lit" else it[1] for it in script):
                problems.append(
                    "the window-wrap entry wraps only on the LAST flush "
                    "(%s): nothing decodes past the wrap" % (wraps,))
        elif wraps:
            problems.append("%s wraps the window (%s) — it is a fixture "
                            "entry and a 256 KB window is a tier"
                            % (name, wraps))
    return ran


def main():
    macextract = os.path.join(ROOT, "build", "macextract")
    args = sys.argv[1:]
    if "--macextract" in args:
        macextract = args[args.index("--macextract") + 1]
    if not os.path.exists(macextract):
        print("run_sit14wrap: no CLI at %s" % macextract)
        return 1

    problems = []
    ran = check_wraps(problems)

    blob, _ranges = synth_sit14.build(wrap=True)
    want = {}
    for name, blocks in synth_sit14.cases(wrap=True):
        _stream, data = synth_sit14.encode(blocks)
        want[name] = data

    whos = ["us"]
    if shutil.which("unar") is None:
        print("run_sit14wrap: no `unar` — the oracle half is SKIPPED, the "
              "encoder half is not")
    else:
        whos.insert(0, "unar")

    tmp = tempfile.mkdtemp()
    try:
        archive = os.path.join(tmp, "synth-sit14-wrap.sit")
        with open(archive, "wb") as fh:
            fh.write(blob)
        for who in whos:
            out = os.path.join(tmp, "out-" + who)
            os.mkdir(out)
            r = subprocess.run(command(who, macextract, archive, out),
                               capture_output=True)
            if r.returncode != 0:
                problems.append("%s exited %d (%s)"
                                % (who, r.returncode,
                                   r.stdout.decode("utf-8", "replace")
                                   .strip().replace("\n", " | ")[-160:]))
            for name in sorted(want):
                got = forks(out, name, who)
                ran += 1
                if got == want[name]:
                    continue
                if len(got) != len(want[name]):
                    problems.append("%s wrote %d bytes for %r, wanted %d"
                                    % (who, len(got), name, len(want[name])))
                else:
                    at = next(i for i, (a, b)
                              in enumerate(zip(got, want[name])) if a != b)
                    problems.append("%s wrote the right length and the wrong "
                                    "bytes for %r, first at %d"
                                    % (who, name, at))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("  FAIL " + p)
    print("run_sit14wrap: %d check(s), %d problem(s)" % (ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
