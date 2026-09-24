#!/usr/bin/env python3
"""check_app_size.py — fail when the application's size moves unremarked.

Every byte of this application is RESIDENT on the target: the Segment
Loader reads one MacExtract.code.bin at launch and the A5 world is
allocated once and never purged (FORMATS.md, *Resident memory*). So the
binary's size comes off the heap a Macintosh has left, one for one, and
a tier's budget is FreeMem() minus it (tools/run_tiers.py).

Nothing watched that until 2026-09-23, and it showed: the engine grew
10,112 B between 2026-08-28 and 2026-09-23 without a line of any status
file moving, and FORMATS.md's size table spent four days describing
tables that had stopped being emitted.

The threshold is not a taste: at the System 6.0.8 / 512 KB tier the
narrowest PASSING fixture (derived-LHA_Expander_1.0.3.sea) has 6,952 B
of headroom, bisected 2026-09-23. A 2,048 B step is therefore three
deliberate acknowledgements before a tier loses a fixture, and each one
is a commit that has to say so.

    tools/check_app_size.py build/mac/MacExtract.code.bin

Raising EXPECT is the acknowledgement. Re-run tools/run_tiers.py when
you do: what matters is not the number here but whether a tier's tally
moved with it.
"""
import os
import sys

# The linked CODE resource, bytes. Bump DELIBERATELY, in the commit that
# grows it, and say what was bought.
EXPECT = 185472
TOLERANCE = 2048
TAKEN = "2026-09-23"


def main():
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    path = sys.argv[1]
    if not os.path.exists(path):
        print("check_app_size: no %s — skipped (no Retro68 toolchain?)" % path)
        return 0

    size = os.path.getsize(path)
    delta = size - EXPECT
    if abs(delta) <= TOLERANCE:
        print("app size: %d B, %+d from %s's %d (within %d)"
              % (size, delta, TAKEN, EXPECT, TOLERANCE))
        return 0

    what = "GREW" if delta > 0 else "SHRANK"
    print("check_app_size: the application %s by %d B (%d, was %d on %s).\n"
          "  Every byte is resident, so this is heap a Macintosh no longer\n"
          "  has. If it is deliberate: re-run tools/run_tiers.py --check,\n"
          "  then raise EXPECT in this file in the SAME commit and say what\n"
          "  the bytes bought. At the sys6-512K tier the narrowest passing\n"
          "  fixture had 6,952 B of headroom when this was written."
          % (what, abs(delta), size, EXPECT, TAKEN), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
