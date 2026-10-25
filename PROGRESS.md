# PROGRESS.md — milestone status

Every milestone is **DONE** and nothing is in flight; the current release is
v0.44.0. One line each: what it delivered, and where the detail lives. Numbers
are in FORMATS.md, reasoning in DECISIONS.md, how a suite runs in TESTING.md,
what is still missing in OPEN_ITEMS.md. A row is one sentence and a citation.

**The suite is 980 fixtures**, byte-exact against `unar` and, where `unar`
fails, `macunpack`; 9,800 robustness variants clean. The Macintosh tiers and
their tallies are BLOCKERS.md's (*Status*); per-tier tables are FORMATS.md's.

| Milestone | Delivered | Detail |
|---|---|---|
| M0 scaffold | Build matrix (ASan/UBSan/alignment, `-m32`, release `-Werror`), the unit, differential and robustness harnesses, corpus and manifest tooling | TESTING.md |
| M1 MacBinary, AppleSingle/Double | Data fork, resource fork, type and creator | FORMATS.md |
| M2 BinHex 4 | Per-fork CRCs enforced, mail-wrapped banners, several documents per file and one document in several parts | DECISIONS.md 2026-08-15 |
| M3 PackIt | Stored and Huffman; encrypted PMa5/PMa6 reported and resynced | DECISIONS.md M3 |
| M4 Compact Pro | RLE, LZH+RLE, nested folders, index-CRC probe | FORMATS.md |
| M5/M6 StuffIt classic | Methods 0/1/2/3/5/6/8/13, per-fork CRC-16 | FORMATS.md |
| M7 StuffIt 5 + Arsenic | BWT+MTF+RLE+arithmetic, with the sampled inverse BWT that fits the 1 MB floor | DECISIONS.md 2026-08-07 |
| M8 zip, gzip, tar, `.Z` | zlib 1.3.1 vendored, inflate only | FORMATS.md |
| M9 CLI polish | Envelope auto-unwrap, budget sweep, 4,000-case fuzz, detect-only probes, `--forks hidden`, no overwriting an existing file | TESTING.md |
| M10 Retro68 Mac app | The application, byte-exact on System 6.0.8, 7.0.1 and Mac OS 9.2, UI driven end to end on System 6 | BLOCKERS.md, `tools/vmac/README.md` |
| M11 Multi-segment | StuffIt and Compact Pro segments, spanned zip, `.NNN` splits, parts inside per-part envelopes | DECISIONS.md 2026-08-09→14 |
| M12 DiskDoubler + Now Compress | DiskDoubler's three containers and methods 0/6/8/9/10; Now Compress's five stream shapes | DECISIONS.md 2026-08-15 |
| M13 ARC + uuencode | ARC methods 1–9 and ArcMac's two forks; uuencode plain, UUTool's two-fork shape, multipart postings | DECISIONS.md M13 |
| M14 Alysis SuperDisk! | Container, block chain, methods 1–9 and 11, read out of its own self-extractors | DECISIONS.md (*SuperDisk!, read out of SuperDisk!*) |
| M15 DiskDoubler 1 + 7 | Methods 1 (Unix compress) and 7 (Stac LZS), graded against DiskDoubler's own forks | DECISIONS.md 2026-08-20 |
| M16 DiskDoubler Pro | The headerless `DDA2` entry and `SPLT` segments; 456 forks graded against a CC0 corpus | DECISIONS.md 2026-08-21 |
| M17 The DiskDoubler corpus in `ci.sh` | 115 fixtures with pinned URLs and manifests | DECISIONS.md 2026-08-21, TESTING.md |
| M18 The Symantec release | DiskDoubler 4.0 and Norton DiskDoubler Pro 1.1 run; the headerless record and both date fields measured | DECISIONS.md 2026-08-21 (the Symantec release) |
| M19 DiskDoubler method 2 | The only method 2 fork found, on Salient's own 3.1.2 floppy | DECISIONS.md 2026-08-21 (the Salient disk) |
| M20 The last three methods | DiskDoubler methods 3, 4 and 5, graded by Salient's own expander | DECISIONS.md 2026-08-21 (methods 3, 4 and 5) |
| M21 The forks nobody could grade | 8 ungraded resource forks adjudicated; XADMaster's DDn off-by-one reduced to a 1,166-byte repro | DECISIONS.md 2026-08-22, `tools/xadmaster-ddn-repro/` |
| M22 SuperDisk!'s other container | The single-file container, from five specimens made with Alysis's 1991 control panel | DECISIONS.md 2026-08-22 (later still) |
| M23 The settings sweep | One input compressed per control-panel setting; found method 6 broken | DECISIONS.md 2026-08-22 (last) |
| M24 StuffIt SpaceSaver | The 84-byte container and methods 0 and 4, from Aladdin's own engine | DECISIONS.md 2026-08-22 (the layout) |
| M25 Decryption | Eight ciphers across six formats as one filter; the Mac application asks for a password | FORMATS.md (*Encryption*), DECISIONS.md 2026-08-23 (decryption) |
| M26 btoa/atob | Both framings, graded against btoa 5.2.1 | FORMATS.md (*btoa*) |
| M27 Compact Pro comments | The archive Note saved, on both hosts | DECISIONS.md 2026-08-23 (Compact Pro comments) |
| M28 LZH / LHA | Every method but PMarc, all four header levels, MacLHA's two forks | FORMATS.md (*LZH / LHA*) |
| M29 The performance pass | Seven optimisations, two killed by measurement; 1,898 s → 1,384 s on a 7 MHz Mac Plus | DECISIONS.md 2026-08-24, FORMATS.md (*Decode cost*) |
| M30 The rest of the performance plan | Five more, three claims killed | DECISIONS.md 2026-08-24 (PLANNED_WORK.md, closed) |
| M31 An icon | The icon family, bound and drawn by a real Finder | DECISIONS.md 2026-08-24 (the icon), `tools/icon/` |
| M32 A second SuperDisk! reader | Disk Expander's `Cmpr` modules under `qemu-m68k`; method 10 implemented on it | DECISIONS.md 2026-08-25, `tools/sdmodule/` |
| M33 ARC 0x0a and 0x0b | PAK's Crushed and Distilled, graded by PAK 2.51 under DOSBox | DECISIONS.md 2026-08-25 (ARC 0x0a and 0x0b) |
| M34 ARC 7.x's Trimmed | The other method 0x0a and the ARC 7 container | DECISIONS.md 2026-08-25 (ARC 7.x Trimmed) |
| M35 SpaceSaver's codecs | The `CMod` compressors under `qemu-m68k`; every method decodes | DECISIONS.md 2026-08-25 (SpaceSaver's codecs), `tools/ssmodule/` |
| M36 base64 and MIME | `multipart/appledouble`, bare base64, sharutils, nested multiparts, quoted-printable | FORMATS.md (*base64 and MIME*) |
| M37 Disk images, named | Volume probes, retired the same day by M38 | DECISIONS.md 2026-08-26 (disk images), `attic/` |
| M38 Named archives | Nine PC-side formats named and never extracted (withdrawn by M71); disk-image probes to `attic/` | DECISIONS.md 2026-10-18 (*the formats it only named*) |
| M39 Selective extraction (CLI) | `--only NAME` on `l`, `x` and `t`, the three walks held against each other | TESTING.md (*Selective extraction*) |
| M40 The yardstick | StuffIt Expander 4.0.2 timed on the same emulated Mac Plus | FORMATS.md (*Timed on the same Mac Plus*), DECISIONS.md 2026-08-29 |
| M41 The end-of-run report | Renamed and failed entries listed, with **Save as Text** | FORMATS.md (*Name limits*), DECISIONS.md 2026-08-29 (the end-of-run report) |
| M42 A cut archive is not a complete one | Every walk tells "the archive ended" from "the bytes ran out" | DECISIONS.md 2026-08-29 (a cut archive), TESTING.md (*A cut archive is NOTICED*) |
| M43 The two MIME gaps | A multipart's uuencoded part no longer hides the rest; `message/partial` joins | FORMATS.md (*Segmented archives*) |
| M44 Level with the yardstick | Six functions at `-O3`: 70.4 s → 52.6 s for +1,024 B | FORMATS.md (*What -O3 is worth, and where*) |
| M45 System 3.0 tier | The same binary on System 3.0 at 4 MB and 1 MB; 512 KB measured | FORMATS.md (*System 3.0 tier*, *512 KB machines*), `tools/vmac/sys30.py` |
| M46 Two constants | The stack priced (5,200 B), 44 KB back to every 1 MB extraction | FORMATS.md (*Stack*, *Budget*), DECISIONS.md 2026-08-31 (two constants) |
| M47 The medium, not the machine | A Macintosh 512K boots System 3.0 off MFS; the application needs HFS | FORMATS.md (*A true Macintosh 512K*) |
| M48 Two byte reads | Starts on a 64K-ROM Macintosh; on `main` since 2026-10-16 as `GrowApplZone` | DECISIONS.md 2026-10-15 (the purge MaxApplZone never did), MANUAL_TESTS.md §6 |
| M49 The machine that is too small | A Macintosh 128K bombs `ID = 03`; `tools/vmac/memtest` names the heap wall | FORMATS.md (*A Macintosh 128K*) |
| M50 A folder is a name too | Folders agreeing for 31 characters become two, the second `~1` | DECISIONS.md 2026-09-03 (a folder is a name too) |
| M51 The field nobody assigned | The Mac OS 9 bomb was an unassigned `UncOptions` field; Mac OS 9.2 21/21 | DECISIONS.md 2026-09-04 (the field nobody assigned) |
| M52 DART | **Removed 2026-09-25**, out of scope (OPEN_ITEMS.md, *Out by the brief*) | DECISIONS.md 2026-09-25 (*the disk images that found another home*) |
| M53 The overlays become the build | Decoders ship as `'OVLY'` images: resident `CODE` 151,588 → 53,332 B | FORMATS.md (*Overlays*), DECISIONS.md 2026-09-25 (two branches that were one file apart) |
| M54 The specimens that were downloadable | 48 SpaceSaver files and two AppleLink packages, found in an index of file magic | DECISIONS.md 2026-09-26 (*the magic in somebody else's index*) |
| M55 StuffIt 5's method 14 | All 258 entries of StuffIt 7.0.3's installer; `tools/synth_sit14.py` encodes | DECISIONS.md 2026-10-03 (method 14) |
| M56 AppleLink `.pkg` | SqueezePlay through the unchanged `src/unc_lzw.c`; run on an emulated Mac Plus | FORMATS.md (*AppleLink packages: SqueezePlay*) |
| M57 The scan already paid for | A zip behind a self-extractor recognised at +0 reads on non-archives | DECISIONS.md 2026-10-05 (*the scan that was already being paid for*) |
| M58 The specimens filed as unobtainable | Four "no specimen" claims re-tested, three withdrawn | DECISIONS.md 2026-10-06, `tools/scan_discmaster.py` |
| M59 The reference that was the payload | PackIt's ciphers graded against Packit III 1.3 under `qemu-m68k` | DECISIONS.md 2026-10-05 (*the reference implementation was the fixture's payload*) |
| M60 The encoder that was the reference | The MU layout cited to UUTool; its default alphabet read | DECISIONS.md 2026-10-06 (*the alphabet nothing here had seen*) |
| M61 The decoder's author's definition | BinHex's second-document scan cited to DeHQX 2.0.1 | DECISIONS.md 2026-10-06 (*the separator that was in the alphabet*) |
| M62 The last rule that was somebody else's | `src/fmt_binhex.c` owes macutils nothing; no behaviour changed | DECISIONS.md 2026-10-07 (*the engine four layers down*) |
| M63 Implode | Zip method 6 and ZipIt's `0x2605`; `tools/synth_implode.py` encodes; +0 shipped | FORMATS.md (*Implode*) |
| M64 PKZIP 1.01's reading | PKZIP 1.01/1.02's Implode entries, decided per archive; +0 shipped | DECISIONS.md 2026-10-08 (*the second attempt that had nowhere to go*) |
| M65 Shrink | Zip method 1, transcribed from deark; +0 shipped | FORMATS.md (*Shrink*) |
| M66 Private File | Graded on three files PF Encrypt wrote under Mini vMac; +368 B resident | FORMATS.md (*Private File*) |
| M67 Reduce comes in | Zip methods 2–5; 2,371 of 2,379 wild entries match, deark fails the other 8; +80 B resident | FORMATS.md (*Reduce*), DECISIONS.md 2026-10-11 (*Reduce comes in*) |
| M68 The BinHex before 4.0 | `.hex` and `.hcx`, graded on files BinHex 2.0 wrote; +352 B resident | DECISIONS.md 2026-10-14 (*the BinHex before 4.0*) |
| M69 The metadata, carried to the disk | Finder info, backup date, lock and comment written to disk; 18/18 on Systems 3.0 and 6.0.8, 17/18 on 7.0.1; +864 B resident | DECISIONS.md 2026-10-17 (*the metadata, carried to the disk*) |
| M70 Every reader's own Finder info | Each reader delivers what its format holds, StuffIt classic and DiskDoubler what their expanders restore; graded by `tools/run_meta.py`; +1,008 B resident | FORMATS.md (*Finder info in the archive*), DECISIONS.md 2026-10-17 (*the archives' own Finder info*) |
| M71 Nothing named that is not extracted | Formats only named become `UNC_FORMAT_UNKNOWN`; `tools/run_foreign.py` holds 26 specimens to it; −2,032 B resident | DECISIONS.md 2026-10-18 (*the formats it only named*) |
| M72 The format before BinHex | SUMacC's `.dl`, byte-exact against hexbin and SUMacC's `fromhex`; +32 B resident | DECISIONS.md 2026-10-24 (*the format before BinHex*) |
