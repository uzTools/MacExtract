# `tools/longname-repro/` — the field nobody assigned

The reproduction behind the Mac OS 9 DiskDoubler bomb (DECISIONS.md
2026-09-04, *the field nobody assigned*; BLOCKERS.md, *Withdrawn claims*).

The Mac shell filled `UncOptions` field by field and never assigned
`long_name` or `long_name_cap`, which joined the struct on 2026-08-27. The
engine's folder-path walker (`unc_path_push` → `path_full_add` in
`src/unc_util.c`) writes **every** component through that pointer whenever
it is non-NULL and the cap is at least 2 — the buffer is where the uncut
name accumulates, so it is written whether or not anything is ever cut.
Exactly three formats walk a tree with it: DiskDoubler, SuperDisk! and Now
Compress. Every other format never touches the buffer.

`repro.c` hands the engine the shape stack garbage takes when it looks
valid — a pointer to four bytes the host owns and a cap of a megabyte — and
lists an archive, writing nothing. `run.sh` builds it under ASan and runs
one fixture per family, each twice:

    sh tools/longname-repro/run.sh

Measured 2026-09-04:

| fixture | garbage-shaped `long_name` | `--null` |
|---|---|---|
| `derived-DandStoQIF2.sea` (DiskDoubler) | **heap-buffer-overflow WRITE** in `path_full_add` | clean |
| `derived-SD__Utilities.x` (SuperDisk!) | **heap-buffer-overflow WRITE** | clean |
| `synth-now-mixed.now` (Now Compress) | **heap-buffer-overflow WRITE** | clean |
| `derived-XferIt_1.5b4.sea` (Compact Pro) | clean, buffer untouched | clean |
| `derived-Export.sit` (StuffIt) | clean, buffer untouched | clean |

The Mac half is `git grep long_name mac/` returning nothing before the fix,
and the fixed build extracting the same fixtures byte-exact on Mac OS 9.2
(FORMATS.md, *Mac OS 9.2*). The fix zeroes the whole struct before the
fields are set (`RunExtract`, `mac/macextract_mac.c`), which is what
`unc_extract_as` already did for a NULL `opt` after the same class of
mistake bit the unit tests on 2026-08-27.
