# PROGRESS.md — milestone status

Every milestone is **DONE**. This table says what each one delivered and
where the detail lives; it does not repeat it. Numbers live in FORMATS.md,
reasoning in DECISIONS.md, how a suite runs in TESTING.md, what is still
missing in OPEN_ITEMS.md.

| Milestone | Delivered | Detail |
|---|---|---|
| M0 scaffold | Build matrix (ASan/UBSan/alignment, `-m32`, release `-Werror`), unit + diff + robustness harnesses, corpus and manifest tooling | TESTING.md |
| M1 MacBinary, AppleSingle/Double | 195 fixtures byte-exact, data + resource + type/creator | FORMATS.md |
| M2 BinHex 4 | 179 fixtures; header and per-fork CRCs enforced; mail-wrapped banners; **several documents in one file, and one document posted in several parts** (2026-08-15), both graded by `hexbin` because `unar` shares the blind spot | FORMATS.md ††, DECISIONS.md |
| M3 PackIt | Stored + Huffman; encrypted PMa5/6 reported and resynced; a CRC byte-order conflict between references arbitrated | DECISIONS.md |
| M4 Compact Pro | 108 fixtures byte-exact (RLE, LZH+RLE, nested folders, index-CRC probe) | FORMATS.md |
| M5/M6 StuffIt classic | 227 fixtures; methods 0/1/2/3/5/6/8/13; per-fork CRC-16. Method 6 was implemented only on 2026-08-08, when a second oracle turned up in `reference/` | FORMATS.md ‡, BLOCKERS.md |
| M7 StuffIt 5 + Arsenic | 31 fixtures; BWT+MTF+RLE+arithmetic with an internal CRC-32; a sampled inverse BWT takes over under memory pressure, which is what put StuffIt 5 inside the 1 MB floor | FORMATS.md, DECISIONS.md |
| M8 zip, gzip, tar, .Z | 11 fixtures; zlib 1.3.1 vendored, inflate only; 2 PKZIP 1.x zips declined per entry and graded on names | FORMATS.md |
| M9 CLI polish | Envelope auto-unwrap and `-nr`, budget sweep, 4,000-case fuzz, detect-only probes, `--forks hidden`, refusal to overwrite an existing output file | TESTING.md |
| M10 Retro68 Mac app | Runs and extracts byte-exact on System 6.0.8, System 7.0.1 and Mac OS 9.2; the interactive UI is driven end to end on System 6; the emulator harness is committed under `tools/vmac/` | FORMATS.md, BLOCKERS.md, `tools/vmac/README.md` |
| M11 Multi-segment | Four schemes — StuffIt and Compact Pro segments (identified by header), spanned zip and `.NNN` splits (placed by name, adjudicated after assembly) — plus parts inside per-part envelopes. All four join on Linux **and** in the Macintosh application | DECISIONS.md 2026-08-09→14 (the rule that ordered them: **a part must be identifiable from its own bytes** — a ranking rule, not a gate); FORMATS.md for the tables |
| M12 DiskDoubler + Now Compress | DiskDoubler: three containers, methods 0/6/8/9/10, 6 fixtures. Now Compress: 2 real fixtures, 13 generated archives, and **specimens from the original encoder** under emulation (2026-08-16) | FORMATS.md ✦ ✧, DECISIONS.md, `tools/vmac/nowcompress.py` |
| M13 ARC + uuencode | ARC methods 1–9 and ArcMac, both forks — the payload's fork order measured by running ArcMac itself under emulation (2026-08-16); uuencode plain and UUTool's two-fork shape, multipart included. Neither format occurs in the corpus, so both suites generate and hand off to a second implementation | FORMATS.md ★ ★★★, DECISIONS.md, `tools/vmac/arcmac.py` |

| M14 Alysis SuperDisk! | The format nothing here could name, read out of the corpus itself: both archives are self-extracting, so each ships the decoder it should be graded by. Container, block chain and methods 1-9 from the self-extractor's `CODE 2`; method 11 from the Add-In Module in the second archive's own data fork; the method table from the Disk Expander extension that method 11 unpacks. 5 forks across 2 archives adjudicated by running those self-extractors under emulation (2026-08-20); methods 10, 13 and 20 declined per entry | FORMATS.md ✧✧, DECISIONS.md, BLOCKERS.md, `tools/vmac/superdisk.py` |
| M15 DiskDoubler 1 + 7 | The two methods "nothing reachable writes", written by DiskDoubler itself: method 1 (Unix compress, an 0x5a XOR over the DECODED bytes) is what its own "Method A" produces under Mini vMac, and method 7 (Stac LZS, stream and output both complemented) came off the 3.7 distribution disk, which Salient built on a machine with the Sigma card fitted. Graded by the bytes that went in, by the forks' own checksums, and by `unar`; methods 2-5 stay declined for want of a specimen | FORMATS.md ✦, DECISIONS.md, BLOCKERS.md, `tools/vmac/diskdoubler.py` |
| M16 DiskDoubler Pro | The `DDA2` entry that has no header of its own — what DiskDoubler Pro writes for a file it could not shrink — read for the first time by anything: XADMaster raises on it, so `unar` calls five of nine real DiskDoubler Pro archives corrupt and still does. Found and graded with `ssokolow/diskdoubler-test-files`, a CC0 corpus that publishes the ORIGINALS beside the archives: 456 forks byte-exact against the bytes that went in, across 63 single-file containers, 9 archives and 20 self-extractors. Plus `SPLT`, DiskDoubler's split container, implemented as the fifth segmented scheme — derived from four specimens, verified by reassembling both sets byte-exact, and the only one of the five no reference reads | BLOCKERS.md, DECISIONS.md 2026-08-21, FORMATS.md ✦, `tools/run_ddtf.py`, `src/fmt_ddseg.c` |

**The suite is 809 fixtures**, byte-exact against `unar` and, where `unar`
fails, `macunpack`; 8,090 robustness variants clean. The Mac shell replays a
63-fixture sample byte-exact at 4 MB and at the 1 MB floor. Current figures
and per-tier tables: FORMATS.md.
