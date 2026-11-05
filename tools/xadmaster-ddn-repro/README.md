# `tools/xadmaster-ddn-repro/` — four DiskDoubler DDn (method 10) bugs in `unar`

`unar` refuses 11 of the 33 DiskDoubler DDn forks in
`derived-LHA_Expander_1.0.3.sea` and `derived-Terrainman_2.0__.sea` with
*Attempted to read more data than was available*, on archives that are not
damaged (`make_repro.py`). Three more gaps in the same handle, found by
reading the reference rather than from any fixture
(`make_repro_unchecked.py`): one crashes `unar`, one leaks heap memory
into the extracted file with no error, one just decodes the wrong bytes.
`ISSUE.md` is the write-up for all four.

    make_repro.py -o /tmp/repro.dd              # unar fails on both forks
    make_repro.py --slack 1 -o /tmp/ok.dd       # unar succeeds

    make_repro_unchecked.py -o /tmp/ddn         # writes case_a/b/c/d/e.dd
    unar -f /tmp/ddn/case_d.dd                  # segfault
    unar -f /tmp/ddn/case_e.dd                  # OK, exit 0 -- but leaks heap

The fixture `make_repro.py` slices is not committed (`fixtures/SOURCES.md`
says how to fetch it), so it generates rather than stores; the five
`make_repro_unchecked.py` cases are synthetic and need no fixture.

**This is not a workaround kept for its own sake.** `tools/run_ddforks.py`
uses the same one-byte slack to make `unar` an oracle for forks it would
otherwise refuse, which is what adjudicated the 8 resource forks that had
no off-Mac second implementation (DECISIONS.md 2026-08-22).
