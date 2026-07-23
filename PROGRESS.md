# PROGRESS.md — milestone status

| Milestone | Status | Notes |
|---|---|---|
| M0 scaffold | **DONE** | build matrix (ASan/UBSan/alignment, -m32, release -Werror), unit harness, diff/robustness harnesses, corpus+manifest tooling, empty engine sniffs gracefully |
| M1 MacBinary + AppleSingle/Double | **DONE** | 195 oracle fixtures byte-exact (data+rsrc+type/creator); 1950 corrupt variants clean; found & excluded a GNUstep oracle bug on `~`-prefixed names |
| M2 BinHex 4 | **DONE** | 179 fixtures byte-exact incl. mail-wrapped banners at >512 B offsets; header+fork CRCs enforced; 3740 corrupt variants clean |
| M3 PackIt | **DONE** | stored + Huffman; 1 real stored fixture (4 entries) + 3 synthetic PMa4 archives byte-exact; encrypted PMa5/6 reported+resynced; CRC byte-order conflict in references arbitrated (see DECISIONS.md) |
| M4 Compact Pro | **DONE** | 106 fixtures byte-exact (RLE + LZH+RLE, nested folders, index-CRC probe); 2 fixtures excluded as oracle-undecidable (.rsrc name collisions); full-corpus diff 514/514, robustness 5140/5140 |
| M5 StuffIt classic 0–3 | **DONE** | committed with M6 (corpus interleaves methods; see DECISIONS.md); container walk + folder tree, per-fork CRC-16/ARC; method 1 pinned by unit tests (absent from corpus) |
| M6 StuffIt method 13 (+corpus methods) | **DONE** | 211 StuffIt fixtures byte-exact. Per-entry method coverage: LZ+Huffman(13) 970 entries/115 fixtures, Compress(2) 330/90, Huffman(3) 38/24, None(0) 13/7, LZAH(5) 1/1, MW(8) 3/1; method 1 unit-only; 6 fixtures excluded as oracle-undecidable/buggy |
| M7 SIT5 + Arsenic | **DONE** | 31 SIT5 fixtures byte-exact (methods 0/13/15); Arsenic BWT+MTF+RLE+arithmetic coder with internal CRC-32; all real archives use 512 KB blocks; peak mem min 0.64 MB / median 1.0 MB / max 2.6 MB (lazy transform sizing) |
| M8 zip/gzip/tar/.Z | **DONE** | 11 fixtures byte-exact (3 zip / 3 gz / 1 tar / 4 .Z incl. real-world tar.gz+tar.Z); zlib 1.3.1 vendored (inflate only); 2 PKZIP-1.x zips corpus-only (unar cannot read them either); unit tests hand-build stored-deflate gzip, ustar, stored zip |
| M9 CLI polish & hardening | **DONE** | envelope auto-unwrap (+`-nr`), unwrap chain tests in CI, 400 KB budget sweep (only Arsenic refuses, per-entry), 4,000-case fuzz clean + CI smoke, detect-only probes (SITX/DiskDoubler/NowCompress/LZH), FORMATS.md matrix, README |
| M10 Retro68 Mac app (stretch) | **PARTIAL** | Built on-box m68k toolchain; ran on real Mini vMac/System 6.0.8/Mac Plus 4 MB. VERIFIED on hardware: launch, full Toolbox UI, format sniffing, and the **engine decode** (test-only: decode + in-engine CRC → "Extraction complete"), plus file creation + PBSetCatInfo metadata. OPEN BUG: disk-write path hits a layout-sensitive heap corruption (see BLOCKERS.md) — needs MacsBug. Engine (the product) verified correct on 68000; shell write glue defective. |
