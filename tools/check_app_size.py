#!/usr/bin/env python3
"""check_app_size.py — fail when the application's size moves unremarked.

The Segment Loader reads one MacExtract.code.bin at launch and the A5
world is allocated once and never purged (FORMATS.md, *Resident
memory*), so every byte of THAT comes off the heap a Macintosh has left,
one for one, and a tier's budget is FreeMem() minus it
(tools/run_tiers.py).

"Every byte of this application is resident" was true until 2026-09-25
and is not any more: the decoders ship as fifteen 'OVLY' images, read at
launch as one bundle and mostly released as soon as the sniff says what
the archive is (mac/ovl_load_eager.c). The bundle is 143,072 B and none
of it is resident while an archive is being extracted — which is the
whole point of the build — so it is NOT what this file watches. What it
watches is the code that cannot go away.

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

Raising EXPECT is the acknowledgement. Re-run tools/run_tiers.py when
you do: what matters is not the number here but whether a tier's tally
moved with it.
"""
import os
import sys

# The linked CODE resource of the SHIPPED build — overlays, eager — in
# bytes. Bump DELIBERATELY, in the commit that grows it, and say what was
# bought. It was 65,792 B earlier on 2026-09-25 and fell 896 B when DART
# left the engine; 185,472 B was the figure for the resident build until
# overlays became the default the same day; the same build still exists as the
# control (UNC_OVL_RESIDENT=1) and has its own ceiling in
# tools/build_mac.sh, which is where a per-configuration limit belongs.
# LOWERED 2026-09-27 from 64,896 to 64,384, at the size on the day: the
# AppleLink `.pkg` probe left with the routine it was transcribed from
# (DECISIONS.md 2026-09-27, *the recogniser that was a command line*).
# RE-TAKEN 2026-09-28 from 64,384 to 64,512: the StuffIt add-on module
# fields (FORMATS.md, *Where an archive names the module*), which cost 112 B
# of resident code + A5 and put 208 B into the StuffIt 'OVLY' image. Re-taken
# rather than absorbed into the tolerance, on the same terms as
# tools/build_mac.sh's six ratchets, which moved in the same commit; and
# `run_tiers.py --check` moves no tally in either lane.
# RE-TAKEN 2026-10-05 from 64,512 to 65,536: AppleLink packages, and
# this is the first format since the overlays landed whose resident cost
# is not nothing. 666 B of the 1,024 is `src/fmt_sqp_probe.c`, which is
# resident because the sniffer calls it for every file it is handed; the
# rest is the release switch's new case, `mac/ovl_shim.c`'s dispatch and
# the engine's table row. (This read 65,536 for an hour on the day,
# estimated from the resident `CODE` figure instead of read off the
# file; the tolerance reported the 128 B rather than failing, which is
# what it is for, and the number here is `stat` on build/mac now.) The decoder is 1,474 B and is in the new
# `ovl_sqp` image. What was bought is a `.pkg` recognised by its
# CONTENT, which Aladdin's own reader never did (FORMATS.md, *AppleLink
# packages: SqueezePlay*). `run_tiers.py --check` moves no tally in
# either lane.
EXPECT = 65664
TOLERANCE = 2048
TAKEN = "2026-10-05"

# And the BUNDLE, watched from 2026-09-26 for one reason: FORMATS.md quotes it
# in three places and nothing measured it, so it was wrong by 544 B — the
# figure in the docs was the bundle's Rez'd RESOURCE FORK
# (`ovl_bundle.r.rsrc.bin`) rather than the bundle, and that error also
# produced a 512 B residue in the launch-read arithmetic which the docs
# recorded as unexplained (DECISIONS.md 2026-09-26, *the fork that was
# mistaken for its contents*). It is NOT resident, so its growth costs the
# download and the launch read rather than the engine's budget — but a figure
# nothing measures is a figure nobody can correct.
# RE-TAKEN 2026-10-02 from 145,652 to 150,244: `src/sit_ccube.c`, the
# C-Cube JPEG decoder that undoes the `JPEG Lossy` Optimizer (FORMATS.md,
# *What an Optimizer did to the fork*). All 4,592 B of it are in
# `ovl_stuffit.bin`, 18,582 -> 23,174 B, so the SHIPPED build's resident
# `CODE` and A5 did not move at all and EXPECT above is untouched — what
# was bought is the fifth and last Optimizer, byte-exact against StuffIt
# Deluxe 2.0.1's own restored file, for 4,592 B of download and launch
# read and nothing off any extraction's budget. `run_tiers.py --check`
# moves no tally in either lane.
# RE-TAKEN 2026-10-02 again, 150,244 -> 151,080: StuffIt 2.x's five
# ciphers. 856 B of it is the crypt image (9,284 -> 10,140), the rest
# the StuffIt one, and the SHIPPED build's resident code moved by eight
# bytes — the shim passing which cipher an entry wants. What was bought
# is `DES`, `DESex`, `NewDE`, `NewDEx` and `PassLock`, all five graded
# against a known plaintext (FORMATS.md, *The three ways 2.0.1
# encrypts*). `run_tiers.py --check` moves no tally in either lane.
# RE-TAKEN 2026-10-03, 151,080 -> 153,688: StuffIt 5's method 14
# (`src/sit14.c`). All 2,608 B of it are in `ovl_stuffit.bin`,
# 23,670 -> 26,278 B, so the SHIPPED build's resident `CODE` and A5 did
# not move at all and EXPECT above is untouched. What was bought is the
# last StuffIt method this engine could not read: 258 of 258 entries in
# StuffIt Deluxe 7.0.3's own installer where 80 refused, and 184 of 184
# in 5.5's (FORMATS.md, *StuffIt 5's method 14*). `run_tiers.py --check`
# moves no tally in either lane.
# RE-TAKEN 2026-10-05, 153,688 -> 155,672: the fifteenth image,
# `ovl_sqp.bin` at 1,972 B, plus the 12 bytes of bundle directory one
# more image costs. The bundle is not resident, so that part is download
# and launch read; what the AppleLink format costs the engine's budget is
# in EXPECT above.
EXPECT_BUNDLE = 155672
TOLERANCE_BUNDLE = 2048
TAKEN_BUNDLE = "2026-10-05"


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
            print("bundle:   %d B, %+d from %s's %d (within %d)"
                  % (bsize, bdelta, TAKEN_BUNDLE, EXPECT_BUNDLE,
                     TOLERANCE_BUNDLE))
        else:
            print("check_app_size: the 'OVLY' bundle %s by %d B (%d, was %d "
                  "on %s).\n"
                  "  It is not resident, so this is the DOWNLOAD and the launch\n"
                  "  read rather than the engine's budget — FORMATS.md,\n"
                  "  *Overlays*, quotes all three and they move together. If it\n"
                  "  is deliberate: correct that section and raise\n"
                  "  EXPECT_BUNDLE here in the SAME commit."
                  % ("GREW" if bdelta > 0 else "SHRANK", abs(bdelta), bsize,
                     EXPECT_BUNDLE, TAKEN_BUNDLE), file=sys.stderr)
            return 1

    size = os.path.getsize(path)
    delta = size - EXPECT
    if abs(delta) <= TOLERANCE:
        print("app size: %d B, %+d from %s's %d (within %d)"
              % (size, delta, TAKEN, EXPECT, TOLERANCE))
        return 0

    what = "GREW" if delta > 0 else "SHRANK"
    print("check_app_size: the application %s by %d B (%d, was %d on %s).\n"
          "  This code is resident for the whole run, so it is heap a\n"
          "  Macintosh no longer has (the 'OVLY' images are not, and are\n"
          "  not counted here). If it is deliberate: re-run\n"
          "  tools/run_tiers.py --check,\n"
          "  then raise EXPECT in this file in the SAME commit and say what\n"
          "  the bytes bought. At the sys6-512K tier the narrowest passing\n"
          "  fixture had 12,460 B of headroom on 2026-09-27."
          % (what, abs(delta), size, EXPECT, TAKEN), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
