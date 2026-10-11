#!/usr/bin/env python3
"""check_app_size.py — fail when the application's size moves unremarked.

The Segment Loader reads one MacExtract.code.bin at launch and the A5
world is allocated once and never purged (FORMATS.md, *Resident
memory*), so every byte of THAT comes off the heap a Macintosh has left,
one for one, and a tier's budget is FreeMem() minus it
(tools/run_tiers.py).

"Every byte of this application is resident" was true until 2026-09-25
and is not any more: the decoders ship as sixteen 'OVLY' images, read at
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
# RE-TAKEN 2026-10-05 again, 65,664 -> 66,048, for the zip behind a
# stub: `zs_cd_is_there` in src/fmt_zipseg.c, which corroborates the
# end-of-central-directory record the probe was already scanning for and
# claims the archive behind a self-extractor's code. Resident `CODE`
# moved +316 and A5 +4 in all three configurations — none of it in an
# 'OVLY' image, because the sniffer calls that probe for every file it is
# handed. Re-taken rather than absorbed into the tolerance, on the same
# terms as tools/build_mac.sh's six ratchets, which moved in the same
# commit. `run_tiers.py --check` moves no tally in either lane.
# RE-TAKEN 2026-10-07, 66,048 -> 66,176 for the folder-depth rule and then
# -> 65,920 the same day when the depth LIMIT went: popping a path
# component re-scans for the separator now instead of reading a stored
# length, which is what let `UncPath`'s two fixed arrays go and with them
# UNC_PATH_MAXDEPTH, a limit of 24 against a destination that takes 250
# (FORMATS.md, *What the DESTINATION actually allows*). It is SMALLER
# than before any of this: -68 B of CODE against +4 of A5, because the
# walker stopped keeping the path twice (tools/build_mac.sh's eager pair
# has the whole arithmetic, including the +376 it read for an hour). Re-taken rather than
# absorbed into the tolerance, on the same terms as the entry above and
# as tools/build_mac.sh's six ratchets. `run_tiers.py --check` moves no tally in either lane.
# RE-TAKEN 2026-10-09, 65,920 -> 66,432, for Aladdin Private File
# (`.pf`). Resident `CODE` +368 and A5 +32 in the shipped build: the probe
# (186 B — the sniffer calls it for every file), the shim that keys the
# cipher in the crypt image (80 B), the one that dispatches the reader
# (46 B), and the engine's table row and name. The reader itself is in
# `ovl_stuffit`, beside the StuffIt archive a Private File always
# decrypts to. Re-taken rather than absorbed into the tolerance, on the
# same terms as tools/build_mac.sh's six ratchets, which moved in the
# same commit. `run_tiers.py --check` moves no tally in either lane.
EXPECT = 66432
TOLERANCE = 2048
TAKEN = "2026-10-09"

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
# RE-TAKEN 2026-10-06, 155,672 -> 155,920: `ovl_text` 11,450 -> 11,502
# for the two alphabets UUTool actually writes with and `ovl_binhex`
# 2,392 -> 2,590 for the part separator DeHQX documents, plus 2 B of
# bundle index because one more image is now 2 mod 4. The SHIPPED
# build's resident `CODE` moved +8 and its A5 −8, so EXPECT above is
# untouched and nothing comes off an extraction's budget. What was
# bought is every file UUTool writes by default — which this engine
# refused outright — and a posting cut at the separator Peter Lewis's
# own decoder resumes at (FORMATS.md, *uuencode: three alphabets*).
# `run_tiers.py --check` moves no tally in either lane.
# RE-TAKEN 2026-10-06, 155,920 -> 155,916: `ovl_stuffit` 26,278 ->
# 26,274, the method-14 sort fix of the same day. Resident `CODE` and A5
# did not move (FORMATS.md, *StuffIt 5's method 14*; TESTING.md, *The
# sort that dropped what it could not hold*). `run_tiers.py --check`
# moves no tally in either lane.
# RE-TAKEN 2026-10-07, 155,916 -> 156,136 for the folder-depth rule and
# then -> 156,068 when the depth limit went: four of the five images are
# smaller than that morning, the per-entry refusal each carried having
# gone with the limit, and Now Compress's is bigger because its per-level
# counts must survive a level the path string could not hold. The cost of removing it is resident
# and in the walker (tools/build_mac.sh's eager pair). `run_tiers.py --check` moves no
# tally in either lane.
# RE-TAKEN 2026-10-08, 156,068 -> 158,600, and it is TWO changes rather
# than one because the first was MISSED: `ovl_exo` 29,252 -> 31,176 for
# zip method 6 on 2026-10-07 raised the bundle 1,924 B and this constant
# was left where it was, while FORMATS.md's *Overlays* and its launch-read
# sum were both corrected the same day. So this check spent a day
# reporting a growth it should have been holding — it WARNS on the bundle
# rather than failing, 1,924 B being inside TOLERANCE_BUNDLE, which is
# exactly the shape of "a test that passes may not be testing anything".
# The second 608 B is `ovl_exo` 31,176 -> 31,784 for PKZIP 1.01/1.02's
# minimum match length (FORMATS.md, *Implode*). Resident `CODE` and A5
# do not move for either, in either shipped configuration, and
# `run_tiers.py --check` moves no tally in either lane.
# RE-TAKEN 2026-10-08 again, 158,752 -> 159,968, for zip method 1
# (Shrink): `ovl_codecs` 6,404 -> 7,520 and `ovl_exo` 31,936 -> 32,036.
# The decoder is in the codecs image because `ovl_exo` would not link
# past 32 KB (FORMATS.md, *Shrink*). Resident `CODE` and A5 do not move
# in either shipped configuration, and `run_tiers.py --check` moves no
# tally in either lane.
# RE-TAKEN 2026-10-09, 159,968 -> 161,752, for Private File: `ovl_stuffit`
# 26,274 -> 27,950 (the reader, and its probe again for the reader's own
# check) and `ovl_crypt` 10,140 -> 10,248 (`unc_crypt_pf`, MD5 then RC4).
# What it costs the engine's budget is in EXPECT above. -> 161,736 the
# same day: `ovl_stuffit` -12 (the reader keeps its record once) and
# `ovl_crypt` -4 (RC4's indices in registers). -> 161,712 the same day:
# `ovl_stuffit` -24, the Private File footer read through unc_read_full.
# -> 161,840 the same day: `ovl_codecs` +108 and `ovl_exo` +20, a tick per
# Shrink partial clear and a Cancel the zip peek returns. -> 161,868:
# `ovl_exo` +28, zip's dry passes putting the progress count back.
# -> 162,040: `ovl_cptdd` +144, `ovl_lzh` +18, `ovl_text` +8, the
# progress count put right in DiskDoubler, MacLHA and uuencode.
# -> 162,064: `ovl_stuffit` +24, a method-13 fork's encryptor id unread.
# -> 163,596 2026-10-11: zip Reduce, `ovl_exo` +76 and a sixteenth image,
# `ovl_zipold` (2,666 B), with Shrink gone from `ovl_codecs` (-1,224).
# -> 163,588 the same evening: `ovl_zipold` -8, both decoders faster.
EXPECT_BUNDLE = 163588
TOLERANCE_BUNDLE = 2048
TAKEN_BUNDLE = "2026-10-09"


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
