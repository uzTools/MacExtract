#!/usr/bin/env python3
"""run_peek.py — unc_envelope_peek against the whole unwrap, over the corpus.

The Macintosh shell keeps an envelope's reader and what the format under it
needs, and gives the rest of the overlay bundle back, when the first bytes of
the envelope's payload name that format (`src/unc_peek.c`; DECISIONS.md
2026-11-03, *the envelope that said what it held*). A release cannot be
undone mid-run, so a WRONG name would leave the layer under it without its
reader: the layer fails for memory where it worked before.

So for every fixture that sniffs as an envelope this unwraps the layer whole
(`macextract x -nr`), sniffs what came out, and asks the peek through
`tools/encinfo_probe.c --peek`:

  * a peek that names a format other than the whole payload's FAILS;
  * a peek that names nothing is counted, not failed: that envelope keeps the
    whole bundle, as every envelope did before;
  * the peek's own peak allocation is reported, since the shell runs it
    before the release, while the whole bundle is still in memory.

It also fails if fewer envelopes are named than the floor below, so a peek
that quietly stopped naming anything — which no disagreement would show —
does not pass.

Then every fixture that is NOT an envelope, and the Private File specimens
in the cache when it has them, is wrapped here in MacBinary, BinHex and gzip
(tools/synth_wrapped.py's encoders; Python's gzip), and the peek's answer
over each is held to the same rule against the file's own sniff: the corpus
has 466 envelopes, and only those payloads were graded until 2026-11-05.

And one CONTROL that must disagree, or the run fails: a tar header with a
zip appended behind it, the zip's offsets absolute as a self-extractor's
are. Its first 512 bytes sniff as tar; the whole file is a zip, found by
its end record, a probe that runs before tar's and reads past the head
(DECISIONS.md 2026-11-05, *the head that was not the file*). A disagreement
there is what this script exists to see, so not seeing it means it cannot.

WHAT IT CANNOT SEE: a payload the corpus does not hold; whether the peek's
allocations FIT on a Macintosh (`run_tiers.py` charges the peak against the
heap the bundle leaves; fragmentation is the emulator's to find); and the
shell's use of the answer (`mac/ovl_load_eager.c`), which only the emulator
tiers run.
"""
import argparse
import glob
import gzip
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import run_tiers  # noqa: E402
import synth_wrapped  # noqa: E402

# Measured 2026-11-04: 301 of 466 envelope fixtures named, 0 wrong; a 256 B
# window names 4, which this floor fails.
NAMED_FLOOR = 290
# Measured 2026-11-05: 1,620 wrapped payloads, 1,128 named, 0 wrong.
WRAPPED_FLOOR = 1100

SPECIMENS = os.path.expanduser(
    "~/.cache/macextract/vmac/specimens/privatefile/*/*.pf.bin")

WRAPS = (
    ("MacBinary", lambda d: synth_wrapped.macbinary("x", d)),
    ("BinHex", lambda d: synth_wrapped.binhex("x", d)),
    ("gzip", lambda d: gzip.compress(d, mtime=0)),
)


def control():
    """A tar header, then a zip whose offsets count from the start of the
    whole file: tar by its head, zip by its end. Python's zipfile writes
    absolute offsets when it appends to a file that is not a zip."""
    import tarfile
    import zipfile
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode="w", format=tarfile.USTAR_FORMAT) as t:
        ti = tarfile.TarInfo("readme")
        ti.size, ti.mtime = 100, 0
        t.addfile(ti, io.BytesIO(b"x" * 100))
    b.seek(0, 2)
    with zipfile.ZipFile(b, "a", zipfile.ZIP_STORED) as z:
        z.writestr("inner.txt", b"hello zip\n" * 50)
    return b.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract",
                    default=os.path.join(REPO, "build", "rel", "macextract"))
    args = ap.parse_args()

    envelopes = {n for n, env in run_tiers.formats().values() if env}
    tmp = tempfile.mkdtemp(prefix="run_peek-", dir=os.path.join(REPO, ".tmp"))
    try:
        ask = run_tiers.encinfo_probe(tmp)

        def sniff(path):
            r = subprocess.run([args.macextract, "sniff", path],
                               capture_output=True, text=True)
            return r.stdout.strip().split(": ", 1)[-1] \
                if r.returncode == 0 else None

        problems, named, silent, peak, peakof = [], 0, 0, 0, ""
        for path in sorted(glob.glob(os.path.join(REPO, "fixtures", "*"))):
            if not os.path.isfile(path) or path.endswith((".md", ".json")):
                continue
            if sniff(path) not in envelopes:
                continue
            name, _enc, pk = ask(path, peek=True)
            if pk > peak:
                peak, peakof = pk, os.path.basename(path)
            if name is None:
                silent += 1
                continue
            out = os.path.join(tmp, "x")
            shutil.rmtree(out, ignore_errors=True)
            os.mkdir(out)
            subprocess.run([args.macextract, "x", "-nr", "--forks", "hidden",
                            "-o", out, path], capture_output=True)
            files = [os.path.join(r, f) for r, _, fs in os.walk(out)
                     for f in fs if not f.startswith("._")]
            whole = sniff(files[0]) if len(files) == 1 else None
            if whole != name:
                problems.append("%s: the peek says %s, the whole payload %s"
                                % (os.path.basename(path), name, whole))
            else:
                named += 1

        # Payloads wrapped here, held to the file's own sniff.
        wnamed = wsilent = wtotal = 0
        payloads = []
        for path in sorted(glob.glob(os.path.join(REPO, "fixtures", "*"))):
            if not os.path.isfile(path) or path.endswith((".md", ".json")):
                continue
            whole = sniff(path)
            if whole is None or whole in envelopes:
                continue
            payloads.append((path, whole))
        # The specimens are MacBinary, as they came off the Macintosh: the
        # Private File inside is the payload.
        for i, path in enumerate(sorted(glob.glob(SPECIMENS))):
            out = os.path.join(tmp, "pf%d" % i)
            os.mkdir(out)
            subprocess.run([args.macextract, "x", "-nr", "--forks", "hidden",
                            "-o", out, path], capture_output=True)
            files = [os.path.join(out, f) for f in os.listdir(out)
                     if not f.startswith("._")]
            if len(files) == 1 and sniff(files[0]) == "Private File":
                payloads.append((files[0], "Private File"))
        wrapped = os.path.join(tmp, "w")
        for path, whole in payloads:
            with open(path, "rb") as f:
                data = f.read()
            for env, wrap in WRAPS:
                with open(wrapped, "wb") as f:
                    f.write(wrap(data))
                wtotal += 1
                name, _enc, pk = ask(wrapped, peek=True)
                if pk > peak:
                    peak, peakof = pk, os.path.basename(path) + " in " + env
                if name is None:
                    wsilent += 1
                elif name != whole:
                    problems.append("%s in %s: the peek says %s, the whole "
                                    "payload %s" % (os.path.basename(path),
                                                    env, name, whole))
                else:
                    wnamed += 1

        # The control: every envelope of it must be seen to disagree.
        cdata = control()
        with open(wrapped, "wb") as f:
            f.write(cdata)
        cwhole = sniff(wrapped)
        seen = []
        for env, wrap in WRAPS:
            with open(wrapped, "wb") as f:
                f.write(wrap(cdata))
            name, _enc, _pk = ask(wrapped, peek=True)
            if name is not None and name != cwhole:
                seen.append(env)
        if cwhole != "Zip" or len(seen) != len(WRAPS):
            problems.append("the control (a zip behind a tar header, %s "
                            "whole) disagreed in %s of %d envelopes: this "
                            "cannot see a wrong peek"
                            % (cwhole, len(seen), len(WRAPS)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if named < NAMED_FLOOR:
        problems.append("only %d envelopes named, fewer than %d"
                        % (named, NAMED_FLOOR))
    if wnamed < WRAPPED_FLOOR:
        problems.append("only %d wrapped payloads named, fewer than %d"
                        % (wnamed, WRAPPED_FLOOR))
    print("run_peek: %d envelopes named, %d not; %d of %d wrapped here "
          "named, %d not; peak %d B (%s)"
          % (named, silent, wnamed, wtotal, wsilent, peak, peakof))
    print("run_peek: the control disagreed in %s, as it must"
          % (", ".join(seen) or "NO envelope"))
    for p in problems:
        print("run_peek: FAIL " + p)
    print("run_peek: %d problem(s)" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
