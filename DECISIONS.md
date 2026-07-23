# DECISIONS.md — engineering decision log

Non-obvious decisions, most recent last.

## M0

- **License LGPL-2.1-or-later** — forced by transcribing XADMaster
  (LGPL) algorithms; see NOTICE.
- **`reference/` is gitignored**, repopulated by
  `tools/fetch_references.sh`. It contains a full LGPL repo clone plus
  fetched wiki text of unclear licensing; committing it would bloat the
  repo and muddy provenance. The fetch script *is* the provenance record.
- **Listing = extraction minus writes.** No separate `unc_list`
  allocation API: `UncOptions.list_only` drives the same streaming walk
  and reports entries via `begin_entry`/`end_entry`. One code path to
  test, no arrays to size, and the Mac app gets progress-capable
  listing for free. (`begin_entry` returning >0 means "skip data",
  which is also how listing is implemented.)
- **CRC tables are compile-time constants** generated from the
  documented polynomials (0x1021 XMODEM for MacBinary II/BinHex,
  reflected 0xEDB88320 for Arsenic/zip/gzip) with check values
  asserted in unit tests. XADMaster computes the XMODEM CRC through a
  reflected table + bit-unreverse dance (`XADCRCReverseTable_1021` +
  `XADUnReverseCRC16`); the plain MSB-first formulation is
  mathematically identical and simpler; equivalence is pinned by the
  standard check value 0x31C3 and by every MacBinary/BinHex fixture.
- **Engine emits raw archive-encoding names** (MacRoman for Mac
  formats); MacRoman→UTF-8 conversion is CLI-side (`--raw-names`
  opts out). Encoding choice is per-format at the frontend: Mac
  containers → MacRoman, zip/tar/gzip → pass-through.
- **Oracle manifests are built with `unar -nr` (no recursion)** so each
  manifest describes exactly one container layer. Nesting is tested by
  chaining layers, not by replicating unar's name-based recursion
  heuristics (XADMacArchiveParser recurses into MacBinary members only
  when the *name* matches /\.(sea|sit|cpt)$/ — a quirk, not a spec).
- **Manifest dates are not compared** (v1). Mac timestamps pass through
  XADMaster's timezone interpretation in the oracle; chasing an exact
  epoch match adds risk without validating any decompression code. The
  engine still surfaces raw 1904-epoch seconds; correctness of the
  *fields* is covered by the type/creator checks that ride the same
  header parses.
- **Allocator budget lives in the frontend callback**, not the engine:
  the engine just sees NULL and must fail per-entry. This keeps the
  budget policy (CLI `--budget`, Mac `FreeMem()`-driven) out of the
  engine and makes over-budget behavior mechanically testable.
- **`unc_skip` rejects offset wraparound** (`pos + len < pos`) as
  corrupt: all offsets are 32-bit by design (HFS caps files at 2 GB).

## M1

- **Oracle output is not blindly trusted:** `unar` (GNUstep build)
  mishandles resource forks when it cannot append `.rsrc` to a name
  (leading `~`, seen with `lipservice.bin` — our extraction was correct,
  the oracle's was not). `make_manifests.py` now refuses to build a
  manifest when unar prints `cannot append extension`; such fixtures
  stay in the corpus for robustness testing only.
- **MacBinary II/III CRC fallback:** XADMaster also accepts a
  CRC-16/USB-style checksum (reflected poly 0xA001, init/xor 0xFFFF)
  from buggy encoders; transcribed as a bitwise loop rather than a
  second table (runs over 124 bytes, speed irrelevant).
- **Envelope fixtures are "derived" corpus entries:** the payload of
  each BinHex/MacBinary fixture is extracted with the oracle and
  registered as its own fixture (`derived-*`, provenance
  `derived:unar-nr:<parent>` in SOURCES.md), giving per-layer ground
  truth for nested chains without replicating unar's name-based
  recursion.

## M2

- **BinHex sniffing reads beyond the 512-byte head:** real Info-Mac
  .hqx files bury the banner after mail headers/digest preambles
  (observed at offset 1270). The probe streams up to 8 KB (the same
  window XADMaster inspects) with a rolling 40-byte comparison.
- **Filename sanitization differences are normalized in the harness,
  not imitated:** for '/' in Mac filenames unar-on-Linux emits '_' while
  unclassic emits ':' (the classic Mac swap). `run_diff.py` maps
  [:/] → '_' on both sides, per path component. The engine still emits
  raw bytes.

## M3

- **PackIt trailing fork CRC is big-endian in both modes.** The
  references disagree for Huffman entries: macutils pit.c reads it
  little-endian (`getihuffbyte() | getihuffbyte() << 8`) while
  XADMaster reads it big-endian through the decode handle. Arbitrated
  with two further sources — unpit 0.3.1 (contemporaneous with PackIt;
  `getcrc()` is `(byte1 << 8) | byte2` for both modes) and the nocash
  PSX-SPX PackIt page — both big-endian. macutils' LE read is its own
  bug; `macunpack` therefore cross-checks only stored entries.
- **PackIt date fields:** creation @84, modification @88 (macutils
  pit.h H_CTIMOFF/H_MTIMOFF + nocash). XADMaster reads them in the
  opposite order (`modification` then `creation`) — presumed swapped
  there; harmless to us since manifests don't compare dates.
- **No real PMa4 fixtures exist** on the surviving mirrors (searched
  Info-Mac/funet/macgdn; every found .pit is stored-mode). Compressed
  coverage comes from `tools/synth_pit.py`: deterministic synthetic
  archives (provenance `synthetic:tools/synth_pit.py --seed N` in
  SOURCES.md, regenerated by `harvest.py --restore`), validated
  against the unar oracle like any harvested fixture.
- **Encrypted PMa5/PMa6 entries are reported and skipped** with the
  macutils resync strategy (byte-scan for the next block magic):
  without the password the entry length is unknowable. XADMaster's
  password-based decryption is out of scope (v1).
- **lsar JSON is parsed with `strict=False`:** its output can embed
  raw control bytes (binary `XADNextSolidEntry` values in PackIt
  archives), which the default Python JSON parser rejects.
- **Manifest builder synthesizes entries for orphan `.rsrc` sidecars**
  (resource-only entries: unar writes nothing for a 0-byte data fork,
  so the data file is absent and only `<name>.rsrc` exists).

## M4

- **Path model settled for hierarchical containers:**
  `UncEntryInfo.name` is a '/'-separated path. Mac name components get
  the classic reversible '/'→':' swap inside the engine (':' cannot
  occur in an HFS name, '/' can — so nothing is lost), and zip/tar
  paths will pass through natively. The CLI now treats '/' strictly as
  a separator and defuses '.'/'..' components; final on-disk names are
  unchanged for the single-entry formats.
- **CPT probe verifies the full index CRC** (as XADMaster's recognizer
  does): the 1-byte magic (0x01) is far too weak alone. The extractor
  then trusts the index and relies on per-file CRCs, avoiding a second
  full pass.
- **Index parsed via per-entry `unc_read_at`, no index preload:** the
  container interleaves index walking with fork decoding; random
  access keeps peak memory at ~17 KB (io + staging + 8 KB window)
  regardless of entry count.
- **LZH block padding transcribed from XADMaster**, not macutils:
  macutils' eager 16-bit refill implicitly skips 2–3 padding bytes at
  each 0x1FFF0-cost block boundary; XADCompactProLZHHandle expresses
  the same thing explicitly (align; skip 3 if odd bytes consumed since
  the previous trees, else 2) which fits our lazy bit reader.
- **RLE quirks preserved bit-for-bit** from macutils cpt_outch: an
  0x81 that would be the final output byte is a literal; 0x81 0x81
  emits a literal 0x81 while staying escaped; 0x81 0x82 0x00 is a
  literal "0x81 0x82". The 106-fixture corpus exercises all of them.
- **Oracle output can be structurally undecidable:** archives holding
  both "X" and "X.rsrc" as real entries (THINK C projects) cannot be
  represented with the ".rsrc"-sidecar convention — one clobbers the
  other, for unar and for us. make_manifests.py detects the collision
  in lsar metadata and refuses (derived-BootTime.cpt,
  derived-GNU_Chess_3.0.cpt stay corpus-only).
- **`UncBufIn.limit`** bounds every compressed fork substream so
  corrupt streams cannot read into unrelated bytes — mirrors
  XADMaster's bounded sub-handles.

## M5+M6 (committed together)

- **M5 and M6 land in one commit:** the corpus interleaves methods —
  almost every classic .sit carries method 13 next to methods 0/2/3 —
  so an M5-only build cannot pass the full StuffIt differential suite,
  and CI must be green at every commit. Methods 0/1/2/3 were still
  built and validated first (211-fixture suite + unit tests), then
  13/5/8 added.
- **CRC-16/ARC** (reflected 0xA001, init 0) added for StuffIt header
  and fork CRCs; pinned against an independent bitwise implementation
  and the 0xBB3D check value in unit tests.
- **LZW lives in unc_lzw.c** (compress(1)-compatible, LSB-first
  codes): StuffIt method 2 is compress with 14-bit codes + block mode
  (XADStuffItParser passes flags 0x8e), and M8's .Z reuses the same
  decoder with header-supplied parameters. Compress quirks preserved:
  width grows at power-of-two table sizes; a clear code discards the
  rest of its 8-code group.
- **Method 13 fixed tables are machine-transcribed**
  (tools/gen_sit13_tables.py -> src/sit13_tables.h) from
  XADStuffIt13Handle.m — 3,270 table entries hand-copying of which
  would certainly have introduced errors. The generated header is
  committed so the build does not require reference/.
- **Method 13 is the one little-endian-bit-order format** in the
  classic Mac family; UncBitIn grew an LE mode instead of a second
  reader type. Found the hard way: UncCanon.first[] must be 32-bit —
  17-bit canonical codes overflow uint16 exactly at the point the
  method-13 "second" code needs them (dynamic codes reach length 17+,
  fixed tables reach 18).
- **Method 5 ("LZAH") transcribed from XADLZHDynamicHandle** — the
  handle the oracle actually runs — including its LHarc-style window
  preload (value runs + ramps + zeros + spaces), not from the disabled
  libxad SIT_lzah in the same file (all-spaces window, different
  offset coding). XADMaster's own TODO doubts the preload; our
  fixtures decode byte-exact against the oracle either way it settles.
- **Method 1 (RLE90) has no corpus fixture**; it is pinned by unit
  tests (including the 0x90 0x01 illegal-count case, per
  XADRLE90Handle).
- **StuffIt entry-header CRC failures abort the walk**
  (UNC_ERR_CORRUPT): headers chain by compressed lengths, so a bad
  header leaves no way to locate the next entry (XADStuffItParser
  raises a checksum exception at the same point).
- **`~`-name oracle bug generalized:** GNUstep unar can silently write
  the AppleDouble container INTO the data-fork filename (no warning
  printed). make_manifests.py now rejects any data fork that begins
  with the AppleDouble magic and has no sidecar (caught
  derived-020_Simulator.sit). Five more fixtures dropped as
  .rsrc-collision undecidable (BitMap11, The_Journal, TogSndVol,
  Unzip101, unshar_1.11).
