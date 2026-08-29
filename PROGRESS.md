# PROGRESS.md — milestone status

Every milestone is **DONE** and nothing is in flight. One line each: what it
delivered, and where the detail lives. Numbers are in FORMATS.md, reasoning in
DECISIONS.md, how a suite runs in TESTING.md, what is still missing in
OPEN_ITEMS.md. This file repeats none of them, and a row that starts
explaining itself belongs in DECISIONS.md instead.

| Milestone | Delivered | Detail |
|---|---|---|
| M0 scaffold | Build matrix (ASan/UBSan/alignment, `-m32`, release `-Werror`), the unit, differential and robustness harnesses, corpus and manifest tooling | TESTING.md |
| M1 MacBinary, AppleSingle/Double | Data fork, resource fork, type and creator | FORMATS.md |
| M2 BinHex 4 | Header and per-fork CRCs enforced, mail-wrapped banners, several documents in one file and one document posted in several parts | FORMATS.md, DECISIONS.md 2026-08-15 |
| M3 PackIt | Stored and Huffman; encrypted PMa5/PMa6 reported and resynced | DECISIONS.md M3 |
| M4 Compact Pro | RLE, LZH+RLE, nested folders, index-CRC probe | FORMATS.md |
| M5/M6 StuffIt classic | Methods 0/1/2/3/5/6/8/13, per-fork CRC-16 | FORMATS.md, BLOCKERS.md |
| M7 StuffIt 5 + Arsenic | BWT+MTF+RLE+arithmetic with an internal CRC-32, and the sampled inverse BWT that puts StuffIt 5 inside the 1 MB floor | FORMATS.md, DECISIONS.md 2026-08-07 |
| M8 zip, gzip, tar, `.Z` | zlib 1.3.1 vendored, inflate only; PKZIP 1.x declined per entry | FORMATS.md |
| M9 CLI polish | Envelope auto-unwrap and `-nr`, budget sweep, 4,000-case fuzz, detect-only probes, `--forks hidden`, refusal to overwrite an existing output file | TESTING.md |
| M10 Retro68 Mac app | The application, extracting byte-exact on System 6.0.8, System 7.0.1 and Mac OS 9.2, with the interactive UI driven end to end on System 6 | BLOCKERS.md, `tools/vmac/README.md` |
| M11 Multi-segment | Four join schemes — StuffIt and Compact Pro segments, spanned zip, `.NNN` splits — plus parts inside per-part envelopes, on both hosts | DECISIONS.md 2026-08-09→14, FORMATS.md |
| M12 DiskDoubler + Now Compress | DiskDoubler's three containers and methods 0/6/8/9/10; Now Compress's five stream shapes | FORMATS.md, DECISIONS.md 2026-08-15 |
| M13 ARC + uuencode | ARC methods 1–9 and ArcMac's two-fork payload; uuencode plain, UUTool's two-fork shape, and multipart postings | FORMATS.md, DECISIONS.md M13 |
| M14 Alysis SuperDisk! | Container, block chain and methods 1–9 and 11, read out of the archives' own self-extractors | FORMATS.md, DECISIONS.md (*SuperDisk!, read out of SuperDisk!*) |
| M15 DiskDoubler 1 + 7 | Methods 1 (Unix compress) and 7 (Stac LZS), graded against forks DiskDoubler itself wrote | FORMATS.md, DECISIONS.md 2026-08-20 |
| M16 DiskDoubler Pro | The headerless `DDA2` entry, and `SPLT` — the fifth segmented scheme; 456 forks graded against a CC0 corpus's published originals | DECISIONS.md 2026-08-21, FORMATS.md |
| M17 The DiskDoubler corpus in `ci.sh` | That corpus becomes 115 fixtures with a pinned URL and a manifest each, so `run_diff.py` grades all of it | DECISIONS.md 2026-08-21, TESTING.md |
| M18 The Symantec release | DiskDoubler 4.0 and Norton DiskDoubler Pro 1.1 run; what selects the headerless record, and the two date fields, measured | DECISIONS.md 2026-08-21 (the Symantec release), FORMATS.md |
| M19 DiskDoubler method 2 | Salient's own 3.1.2 floppy: the only method 2 fork found anywhere, and method 7 forks longer than one chunk | DECISIONS.md 2026-08-21 (the Salient disk), FORMATS.md |
| M20 The last three methods | DiskDoubler methods 3, 4 and 5 — every method the format has — graded by writing forks Salient's own expander reads back | DECISIONS.md 2026-08-21 (methods 3, 4 and 5), FORMATS.md |
| M21 The forks nobody could grade | The 8 resource forks carried as "not ground truth" since M12, adjudicated; XADMaster's DDn off-by-one reduced to a 1,166-byte repro | DECISIONS.md 2026-08-22, `tools/xadmaster-ddn-repro/` |
| M22 SuperDisk!'s other container | The single-file container, derived by making five specimens with Alysis's own 1991 control panel | DECISIONS.md 2026-08-22 (later still), FORMATS.md |
| M23 The settings sweep | The same bytes compressed once per control-panel setting, which found method 6 broken | DECISIONS.md 2026-08-22 (last), FORMATS.md |
| M24 StuffIt SpaceSaver | The 84-byte container and methods 0 and 4, read out of Aladdin's own engine; the 9,679-byte preset dictionary ships | DECISIONS.md 2026-08-22 (the layout), FORMATS.md |
| M25 Decryption | Seven ciphers across five formats as one filter on the shared reader; the Mac application asks when an entry turns out to need a password | FORMATS.md (*Encryption*), DECISIONS.md 2026-08-23 (decryption) |
| M26 btoa/atob | Both framings, graded against btoa 5.2.1 itself as encoder and reference | FORMATS.md (*btoa*), TESTING.md |
| M27 Compact Pro comments | The archive Note saved rather than dropped, on both hosts | DECISIONS.md 2026-08-23 (Compact Pro comments), FORMATS.md |
| M28 LZH / LHA | Every method the format has except PMarc, all four header levels, and MacLHA's MacBinary payload split back into two forks | FORMATS.md (*LZH / LHA*), DECISIONS.md 2026-08-23 (LZH) |
| M29 The performance pass | Seven measured optimisations, two proposals killed by the measurement; 1,898 s → 1,384 s on a 7 MHz Mac Plus | DECISIONS.md 2026-08-24, FORMATS.md (*Decode cost*) |
| M30 The rest of the performance plan | Five more, three further claims killed; `PLANNED_WORK.md` closed and deleted | DECISIONS.md 2026-08-24 (PLANNED_WORK.md, closed), FORMATS.md |
| M31 An icon | The whole icon family generated, bound, and photographed drawn by a real Finder | DECISIONS.md 2026-08-24 (the icon), `tools/icon/` |
| M32 A second implementation for SuperDisk! | Disk Expander's `Cmpr` Add-In Modules run under `qemu-m68k`, giving every method a second reader; method 10 implemented on the strength of it | DECISIONS.md 2026-08-25, `tools/sdmodule/` |
| M33 ARC 0x0a and 0x0b | Crushed and Distilled — PAK's, not PKARC's — graded by PAK 2.51 under DOSBox; deark replaces `unar` as the oracle for Distilled | DECISIONS.md 2026-08-25 (ARC 0x0a and 0x0b), FORMATS.md (*ARC*) |
| M34 ARC 7.x's Trimmed | The other method 0x0a, and the ARC 7 container read at all for the first time | DECISIONS.md 2026-08-25 (ARC 7.x Trimmed), FORMATS.md (*ARC*) |
| M35 SpaceSaver's codecs | The `CMod` modules' compressors run under `qemu-m68k`, and all three declined methods land: every method the format has now decodes | DECISIONS.md 2026-08-25 (SpaceSaver's codecs), `tools/ssmodule/` |
| M36 base64 and MIME | `multipart/appledouble` as one file with both forks, plus bare base64, sharutils' framing, nested multiparts and quoted-printable | FORMATS.md (*base64 and MIME*), DECISIONS.md 2026-08-26 |
| M37 Disk images, named | Volume-shaped probes (HFS, HFS+/HFSX, Apple Partition Map, ISO 9660) replacing seven extensions the sniffer answered UNKNOWN for — retired the same day by M38 | DECISIONS.md 2026-08-26 (disk images), `attic/` |
| M38 Named archives, retired disk images | Nine PC-side formats named by `unc_sniff` and never extracted, with the Mac shell finally saying the name; the disk-image probes retired to `attic/` whole | DECISIONS.md 2026-08-26 (a name is only worth something…), FORMATS.md (*Archives named but not extracted*) |
| M39 Selective extraction (CLI) | `--only NAME`, repeatable, on `l`, `x` and `t` alike: the entries the user named, matched on the name `l` prints, a folder taking what is in it, a name that matches nothing an error. The listing, extracting and SKIPPING walks are held against each other over the whole corpus for the first time | TESTING.md (*Selective extraction*, *The three walks agree*), DECISIONS.md 2026-08-28 (`--only`) |
| M40 The yardstick | StuffIt Expander 4.0.2 booted on the same emulated Mac Plus as this application, over the same archives, timed by one instrument — the first external speed comparison this project has, and the first time the free tool was RUN here rather than read | FORMATS.md (*Timed on the same Mac Plus*), DECISIONS.md 2026-08-29, `tools/vmac/README.md` |
| M41 The end-of-run report | The Macintosh application lists what it renamed and what failed, with the outcome under the list and a **Save as Text** button, instead of one sentence that said neither. A name too long for HFS loses its extension before its stem; collisions number to `~99` and a name that still cannot be placed fails its own entry rather than the archive | FORMATS.md (*Name limits*), DECISIONS.md 2026-08-29 (the end-of-run report), TESTING.md (*The Macintosh shell's names*) |
| M42 A cut archive is not a complete one | DiskDoubler and StuffIt reported SUCCESS on a truncated archive, handing over the entries before the cut: the walks now tell "the archive ended" from "the bytes ran out", and `run_truncation.py` grades that against `unar` for every format | BLOCKERS.md (*9,320 robustness variants clean*), DECISIONS.md 2026-08-29 (a cut archive), TESTING.md (*A cut archive is NOTICED*) |
| M43 The two MIME gaps | Both items whose oracle was already on this machine: a multipart's uuencoded part no longer hides the rest of the message, and `message/partial` — a message split across several FILES — becomes the sixth join scheme, graded against munpack over sets mpack writes | FORMATS.md (*base64 and MIME*, *Segmented archives*), DECISIONS.md 2026-08-29 (a part that hid its message; a message in several files) |

**The suite is 932 fixtures**, byte-exact against `unar` and, where `unar`
fails, `macunpack`; 9,320 robustness variants clean. The Mac shell replays a
69-fixture sample byte-exact at 4 MB and at the 1 MB floor on System 6.0.8,
and on System 7.0.1 — all three re-run twice on 2026-08-26, for M37 and again
for M38, and those were the first sweeps to cover the whole sample
(BLOCKERS.md, the tier table). The **Mac OS 9.2 tier is 20/20** since
2026-08-27, its first run since M12 and its first over every format.
Current figures and per-tier tables: FORMATS.md.
