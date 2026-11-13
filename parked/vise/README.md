# Installer VISE, parked

MindVision's installers, 1992 to VISE X: the 'VISE' archive before 3.5
(`src/fmt_viseold.c`) and Installer VISE 3.5 to X, floppy sets included
(`src/fmt_vise.c`). Both extracted byte-exact until they were taken off on
2026-11-12, on the maintainer's word ("I'm still not convinced we should
support it"; DECISIONS.md 2026-11-12, *VISE parked*). Why they read the way
they do is DECISIONS.md 2026-11-11, *the installer that was an archive*, and
2026-11-12, *the VISE before VISE*.

**Nothing in `parked/` is built, run or counted.** The Makefile and the
Macintosh build compile `src/` only, `ci.sh` runs `tests/harness/` only, and
`check_docs` counts `fixtures/manifests/` only. It costs the application
nothing; what VISE costs when it is in is below.

## What is here

| here | goes to |
|---|---|
| `src/` — the readers, the probe, the set's identity | `src/` |
| `tools/overlay/ovl_vise.c` — its image's entry | `tools/overlay/` |
| `tests/harness/run_vise.py`, `run_viseold.py` | `tests/harness/` |
| `fixtures/manifests/` — 25 manifests | `fixtures/manifests/` |
| `fixtures/SOURCES.md.part` — their rows | into `fixtures/SOURCES.md` |
| `tools/vmac/vise-sample.txt` — the emulator sample | `tools/vmac/` |
| `register.patch` — every line VISE has in a shared file | `git apply` |
| `reference-*.patch` — its docs, the emulator harness's VISE mode and the sink lane's fixture, as they were removed | by hand |

The 29 fixtures themselves are copyrighted and live in
`~/.cache/macextract/specimens/vise/fixtures` (never committed; the URLs are
in `SOURCES.md.part`). `reference/installer-vise` and
`reference/notes/scummvm_vise.cpp` come from `tools/fetch_references.sh`
once `register.patch` is in.

## Bringing it back

1. Copy each file above to where the table says, the fixtures into
   `fixtures/`.
2. `git apply parked/vise/register.patch`. It is the registration on the
   one-list layout (DECISIONS.md 2026-11-13, *one registration per format*),
   and it touches only these, so if it no longer applies the same lines go
   in by hand:
   - `include/macextract.h`: `UNC_FORMAT_VISE`, reserved now, described again;
   - `src/unc_formats.h`: its `FORMAT` row after Apple Backup's (the join
     rows' order is the Macintosh's `seg_schemes` bytes), its `PROBE` after
     the Tome's, its `SEGID` after Apple Backup's, its `DECODER`;
   - `src/unc_internal.h`: `unc_vise_match`, the one declaration the lists
     cannot make;
   - `tools/overlay/overlay.h`: `OVL_ID_VISE` 147 and `OVL_VISE_EXTRACT` 70;
   - `mac/CMakeLists.txt`: the `ovl_vise` rule, two `EXCLUDE` lines, and
     `fmt_vise_probe.c` and `fmt_viseset.c` in the sniffer's rule (twice
     each, sources and dependencies);
   - `tests/unit_formats.c`: `test_vise` and `test_viseold`, and their calls;
   - `tools/fetch_references.sh`, `tools/harvest.py` (`macbin-data+`),
     `tools/run_diff.py` (its oracle entry), `tools/run_foreign.py` (the
     later parts that must sniff as unknown).
3. `python3 tools/retake_budgets.py`, then `tools/run_tiers.py --check` and
   `sh tools/make_dist.sh`.
4. The docs, from `reference-docs.patch`, rewritten against the docs as they
   are then; the corpus counts `check_docs` holds move by 25 manifests and
   29 fixtures.
5. `./ci.sh`, and the emulator sample (`tools/vmac/vise-sample.txt`).

## Measured, 2026-11-13, on main at e09fcc72 with steps 1–3 done

- Builds: host, and all three Macintosh configurations. The shipped build's
  CODE and A5 do not move (37,296 / 15,696 B): VISE's rows land in padding.
  The control is +12,404 B of code and +524 of A5.
- `retake_budgets.py` puts every figure back where it was before the
  parking: the bundle 223,308 B (`ovl_vise` 12,198, `ovl_sniff` +1,296),
  `OVL_SAVED` 195,136, `TIERS_CONTROL` 248,128.
- Unit tests 2,447 checks (2,371 without); `run_vise.py` and
  `run_viseold.py` OK; `run_diff` 1,018/1,018 fixtures; `run_foreign` OK;
  `check_ovl_rows --selftest`, `images.py` (18 images) and
  `check_harnesses` (27) pass. Not run: `ci.sh` whole, the emulator.
