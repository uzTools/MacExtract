#!/usr/bin/env python3
"""check_app_size.py — fail when the application's size moves unremarked.

The Segment Loader reads one MacExtract.code.bin at launch and the A5
world is allocated once and never purged (FORMATS.md, *Resident
memory*), so every byte of THAT comes off the heap a Macintosh has left,
one for one, and a tier's budget is FreeMem() minus it
(tools/run_tiers.py).

"Every byte of this application is resident" was true until 2026-09-25
and is not any more: the decoders ship as 'OVLY' images, read at
launch as one bundle and mostly released as soon as the sniff says what
the archive is (mac/ovl_load_eager.c). The bundle is EXPECT_BUNDLE below
and none of it is resident while an archive is being extracted — which
is the whole point of the build — so it is NOT what this file watches.
What it watches is the code that cannot go away. (This paragraph read
"143,072 B" until 2026-10-06, a figure correct on 2026-09-26 and
contradicted by this file's own EXPECT_BUNDLE for ten days; it is named
rather than repeated now, so there is one place to change.)

Nothing watched that until 2026-09-23, and it showed: the engine grew
10,112 B between 2026-08-28 and 2026-09-23 without a line of any status
file moving, and FORMATS.md's size table spent four days describing
tables that had stopped being emitted.

The threshold is not a taste: at the System 6.0.8 / 512 KB tier the
narrowest PASSING fixture (derived-LHA_Expander_1.0.3.sea) has 12,460 B
of headroom — it needs 116,784 B against that tier's 129,244, both
re-taken 2026-09-27; it was 6,952 B when this file was written, against a
budget 4,746 B lower. A 2,048 B step is therefore five deliberate
acknowledgements before a tier loses a fixture, and each one is a commit
that has to say so.

    tools/check_app_size.py build/mac/MacExtract.code.bin

Re-taking the figure (tools/retake_budgets.py) is the acknowledgement.
Re-run tools/run_tiers.py when you do: what matters is not the number here
but whether a tier's tally moved with it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import budgets  # noqa: E402

# The linked CODE resource of the SHIPPED build (overlays, eager), and the
# bundle beside it, in bytes: tools/budgets.txt's APP_CODE_FILE and
# APP_BUNDLE_FILE, which tools/retake_budgets.py re-takes. Their history is
# that file's git log and DECISIONS.md; it was kept here until 2026-11-13.
# The control has its own ceiling in tools/build_mac.sh, which is where a
# per-configuration limit belongs.
EXPECT = budgets.get("APP_CODE_FILE")
TOLERANCE = 2048

# The BUNDLE is watched for one reason: FORMATS.md quotes it and nothing
# measured it, so it was wrong by 544 B — the figure in the docs was the
# bundle's Rez'd RESOURCE FORK (`ovl_bundle.r.rsrc.bin`) rather than the
# bundle (DECISIONS.md 2026-09-26, *the fork that was mistaken for its
# contents*). It is NOT resident, so its growth costs the download and the
# launch read rather than the engine's budget — but a figure nothing
# measures is a figure nobody can correct.
EXPECT_BUNDLE = budgets.get("APP_BUNDLE_FILE")
TOLERANCE_BUNDLE = 2048
TAKEN = TAKEN_BUNDLE = "tools/budgets.txt"


def main():
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    path = sys.argv[1]
    if not os.path.exists(path):
        print("check_app_size: no %s — skipped (no Retro68 toolchain?)" % path)
        return 0

    # The bundle sits beside the CODE resource in the same build directory.
    bundle = os.path.join(os.path.dirname(path), "ovl_bundle.bin")
    if os.path.exists(bundle):
        bsize = os.path.getsize(bundle)
        bdelta = bsize - EXPECT_BUNDLE
        if abs(bdelta) <= TOLERANCE_BUNDLE:
            print("bundle:   %d B, %+d from %s' %d (within %d)"
                  % (bsize, bdelta, TAKEN_BUNDLE, EXPECT_BUNDLE,
                     TOLERANCE_BUNDLE))
        else:
            print("check_app_size: the 'OVLY' bundle %s by %d B (%d, was %d "
                  "in %s).\n"
                  "  It is not resident, so this is the DOWNLOAD and the launch\n"
                  "  read rather than the engine's budget — FORMATS.md,\n"
                  "  *Overlays*, quotes all three and they move together. If it\n"
                  "  is deliberate: correct that section and run\n"
                  "  tools/retake_budgets.py in the SAME commit."
                  % ("GREW" if bdelta > 0 else "SHRANK", abs(bdelta), bsize,
                     EXPECT_BUNDLE, TAKEN_BUNDLE), file=sys.stderr)
            return 1

    size = os.path.getsize(path)
    delta = size - EXPECT
    if abs(delta) <= TOLERANCE:
        print("app size: %d B, %+d from %s' %d (within %d)"
              % (size, delta, TAKEN, EXPECT, TOLERANCE))
        return 0

    what = "GREW" if delta > 0 else "SHRANK"
    print("check_app_size: the application %s by %d B (%d, was %d in %s).\n"
          "  This code is resident for the whole run, so it is heap a\n"
          "  Macintosh no longer has (the 'OVLY' images are not, and are\n"
          "  not counted here). If it is deliberate: re-run\n"
          "  tools/run_tiers.py --check,\n"
          "  then tools/retake_budgets.py in the SAME commit and say what\n"
          "  the bytes bought. At the sys6-512K tier the narrowest passing\n"
          "  fixture had 12,460 B of headroom on 2026-09-27."
          % (what, abs(delta), size, EXPECT, TAKEN), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
