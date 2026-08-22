# `tools/xadmaster-ddn-repro/` — one byte, 1,166 bytes to show it

`unar` refuses 11 of the 33 DiskDoubler DDn forks in
`derived-LHA_Expander_1.0.3.sea` and `derived-Terrainman_2.0__.sea` with
*Attempted to read more data than was available*. `ISSUE.md` is the
write-up; `make_repro.py` builds the smallest case.

    make_repro.py -o /tmp/repro.dd              # unar fails on both forks
    make_repro.py --slack 1 -o /tmp/ok.dd       # unar succeeds

The fixture it slices is not committed (`fixtures/SOURCES.md` says how to
fetch it), so this generates rather than stores.

**This is not a workaround kept for its own sake.** `tools/run_ddforks.py`
uses the same one-byte slack to make `unar` an oracle for forks it would
otherwise refuse, which is what adjudicated the 8 resource forks that had no
off-Mac second implementation (DECISIONS.md 2026-08-22).
