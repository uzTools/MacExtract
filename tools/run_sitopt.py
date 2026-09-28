#!/usr/bin/env python3
"""run_sitopt.py — the optimized archives, graded by the program that wrote them.

StuffIt Deluxe 2.0 could hand a fork to an Optimizer before compressing
it, and this engine's whole reading of where an archive records that is
six header bytes taken out of the application's own code (FORMATS.md,
*Where an archive names the module*). Until 2026-09-28 nothing graded
that reading against an archive, because none existed here.

`tools/vmac/sitopt.py` made four, and this replays them:

  Plain.sit       the control — no Optimizer, the same subject
  Optimized.sit   `Text 1`, method 2
  OptBetter.sit   `Text 1`, method 5
  unstuffed.bin   what 2.0.1's OWN unstuffer gives back for Optimized.sit

**The oracle is the writer.** An optimized entry's right answer is not
the file that went in — `Text 1` turns leading spaces into tabs, strips
trailing ones and deletes the resource fork, and none of it is undone
— so "correct" can only mean *what StuffIt Deluxe 2.0.1 itself
produces*, which is why `unstuffed.bin` is in the set. Grading this
against the original subject would fail a correct engine, and grading
it against our own output would pass a broken one.

Four things are asserted, and each one has failed a version of this
engine at some point today:

  1. the control extracts to the subject, both forks, byte for byte;
  2. both optimized entries extract to **2.0.1's own unstuffed bytes**;
  3. neither writes a resource fork — `Text 1` deleted it, the header
     says `rlen` 0, and an engine that invents one is wrong;
  4. the header bytes are what the reading says: `0x40` set on both
     method bytes, 106 and 108 both 255, and 46/47/107/109 zero.

What this CANNOT see:

- **an Optimizer that CAN be undone.** Every specimen here is `Text 1`,
  which has no 'DCMP' and writes the id 255; the rule that a
  non-255 id is refused instead is graded only by
  `tests/unit_formats.c`, on entries built to the reading. A MacPaint,
  Sound or Photoshop specimen would close that (MANUAL_TESTS.md §8).
- **anything at all on a fresh clone.** The specimens are not
  committed — they are an emulator's output, like `sitcrypt.py`'s — so
  this skips cleanly and says nothing when they are absent.

    tools/run_sitopt.py --macextract build/macextract
"""
import argparse
import os
import subprocess
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "vmac"))
import run as R                                          # noqa: E402

SPECIMENS = os.path.join(R.VMAC_HOME, "specimens", "sitopt")
MADE = os.path.join(SPECIMENS, "make2")
UNSTUFFED = os.path.join(SPECIMENS, "unstuff1", "unstuffed.bin")

# The subject `sitopt.py` stuffed, repeated here rather than imported so
# that this suite still grades if that harness is edited: what the
# control must come back as is a property of the specimens, not of the
# generator as it stands today.
SUBJECT_DATA = (b"    indented four spaces   \r"
                b"        indented eight   \r"
                b"no indent, trailing tab\t\r"
                b"    mixed \t indent and trailing spaces    \r") * 6


def forks(path):
    d = open(path, "rb").read()
    dl = int.from_bytes(d[83:87], "big")
    rl = int.from_bytes(d[87:91], "big")
    off = 128 + ((dl + 127) // 128) * 128
    return d[128:128 + dl], d[off:off + rl]


def header(path):
    data, _r = forks(path)
    if data[:4] != b"SIT!":
        return None
    return data[22:22 + 112]


def extract(cli, arc, out):
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([cli, "x", "-o", out, arc], capture_output=True,
                       text=True)
    return r.returncode, r.stdout + r.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract",
                    default=os.path.join(REPO, "build", "macextract"))
    args = ap.parse_args()

    need = [os.path.join(MADE, n + ".sit.bin")
            for n in ("Plain", "Optimized", "OptBetter")] + [UNSTUFFED]
    missing = [p for p in need if not os.path.exists(p)]
    if missing:
        print("run_sitopt: no specimens (%s) — skipped; "
              "tools/vmac/sitopt.py makes them"
              % os.path.basename(missing[0]))
        return 0

    ref_data, ref_rsrc = forks(UNSTUFFED)
    problems = []
    work = tempfile.mkdtemp(prefix="sitopt-grade-")
    try:
        # 1. the control
        rc, msg = extract(args.macextract,
                          os.path.join(MADE, "Plain.sit.bin"),
                          os.path.join(work, "plain"))
        p = os.path.join(work, "plain", "Subject")
        if rc != 0:
            problems.append("the control did not extract: %s" % msg.strip())
        elif open(p, "rb").read() != SUBJECT_DATA:
            problems.append("the control's data fork is not the subject")
        elif not os.path.exists(p + ".rsrc"):
            problems.append("the control lost its resource fork")

        # 2, 3. the optimized pair, against 2.0.1's own unstuffer
        for name in ("Optimized", "OptBetter"):
            out = os.path.join(work, name)
            rc, msg = extract(args.macextract,
                              os.path.join(MADE, name + ".sit.bin"), out)
            p = os.path.join(out, "Subject")
            if rc != 0 or not os.path.exists(p):
                problems.append("%s did not extract: %s" % (name,
                                                            msg.strip()))
                continue
            got = open(p, "rb").read()
            if got != ref_data:
                problems.append("%s: %d B, and StuffIt Deluxe 2.0.1 "
                                "unstuffs it to %d B" % (name, len(got),
                                                         len(ref_data)))
            if os.path.exists(p + ".rsrc"):
                problems.append("%s: a resource fork was written and "
                                "`Text 1` deleted it" % name)

        # 4. the header bytes the reading names
        for name in ("Optimized", "OptBetter"):
            h = header(os.path.join(MADE, name + ".sit.bin"))
            if h is None:
                problems.append("%s: not a StuffIt archive" % name)
                continue
            if not (h[0] & 0x40) or not (h[1] & 0x40):
                problems.append("%s: 0x40 is not set on both method bytes "
                                "(%02x %02x)" % (name, h[0], h[1]))
            if h[106] != 255 or h[108] != 255:
                problems.append("%s: optimizer bytes are %d/%d, not 255/255"
                                % (name, h[106], h[108]))
            if h[46] or h[47] or h[107] or h[109]:
                problems.append("%s: a module byte that should be zero is "
                                "not (46=%d 47=%d 107=%d 109=%d)"
                                % (name, h[46], h[47], h[107], h[109]))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for p in problems:
        print("run_sitopt: %s" % p)
    print("run_sitopt: 3 archive(s) StuffIt Deluxe 2.0.1 wrote, graded "
          "against its own unstuffer, %d problem(s)" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
