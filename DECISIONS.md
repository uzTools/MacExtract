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

## M7

- **SIT5 entry-header CRC is not verified** (XADStuffIt5Parser reads
  and ignores it; per-entry sync is re-checked by the 0xA5A5A5A5 id on
  every header, and fork CRCs still guard the data). Russotto's doc
  describes the CRC but the oracle never enforces it.
- **Second-block prefix is 14 bytes** (u16 flags, u16 ?, u32 type,
  u32 creator, u16 finderflags) followed by a 22-byte (entry v1) or
  18-byte (v2+) skip — found the hard way after assuming 16.
- **SIT5's "mystery entries"** (datalen 0xFFFFFFFF after every
  directory) are skipped without consuming an entry slot, exactly as
  XADStuffIt5Parser does; directory parentage is tracked by header
  offset, not nesting order (bounded map, 256 dirs / 16 KB of path
  pool — overflowing dirs degrade to root-relative paths rather than
  failing).
- **Arsenic transform vector is sized to the actual block fill**, not
  the declared block size. Every real SIT5 fixture declares 512 KB
  blocks (blockbits 19) even for 3 KB payloads; allocating
  4 x blocksize up front would pin every extraction at ~2.6 MB.
  With lazy sizing the corpus measures: min 0.64 MB, median 1.0 MB,
  max 2.6 MB (fixtures that genuinely fill their blocks). A 1 MB
  Mac Plus can therefore expand small Arsenic archives but will
  cleanly refuse large ones per entry (UNC_ERR_MEM) — by design.
- **Arsenic CRC-32 is internal to the stream** (read from the final
  block's end marker, compared against ~crc of the output); the SIT5
  header CRC-16 field is meaningless for method 15 and is skipped,
  as in XADMaster.
- **No synthetic Arsenic unit fixture:** producing one would require
  writing an arithmetic *encoder*; coverage comes from 31 real SIT5
  fixtures plus their 310 corruption variants.

## M8

- **zlib 1.3.1 vendored unmodified** (inflate subset only) into
  third_party/zlib; allocation is routed through UncAlloc via
  z_stream zalloc/zfree, so the engine's no-libc rule holds. Raw mode
  (-15): gzip/zip framing, CRCs and trailers are our own code.
- **Synthetic exogenous fixtures are encoded by independent reference
  implementations** — Info-ZIP zip, GNU gzip, GNU tar, ncompress —
  which is stronger ground truth than hand-built streams
  (tools/synth_exo.py; deterministic via TZ=UTC, fixed mtimes,
  gzip -n, tar --sort/--owner/--group/--mtime, zip -X). Plus
  real-world era files: PCCTS.tar.gz, popper-1.7.tar.Z,
  a2ps.V4.3.tar.Z from funet.
- **4acalc.zip / 4alnch11.zip (PKZIP 1.x, method Implode) stay
  corpus-only:** even unar fails on them, so there is no oracle
  manifest; they exercise our clean per-entry
  "unsupported method" path and the robustness harness.
- **gzip/.Z carry no entry name; unar derives it from the archive
  filename (minus extension), ignoring even an embedded FNAME.** The
  engine gained UncOptions.name_hint so frontends can supply the same
  convention; content-only sniffing is unaffected.
- **Zip is parsed from the central directory** (EOCD scanned in the
  last 66,000 bytes), with per-entry data offsets taken from each
  local header (their name/extra sizes can differ from the CD's).
  Methods other than store/deflate and encrypted entries are clean
  per-entry errors. zip64 is out of scope (HFS-era corpus).
- **tar acceptance requires a valid header checksum** (unsigned, or
  signed for old GNU tars); link/device/GNU-extension entries are
  reported per-entry as unsupported rather than silently skipped.

## M9

- **Auto-unwrap lives in the CLI, not the engine.** The engine stays a
  one-container-at-a-time streaming machine; the CLI re-sniffs the
  single extracted file of an envelope format (MacBinary, BinHex,
  AppleSingle/Double, gzip, .Z), extracts in place (depth ≤ 8) and
  deletes the intermediate (+ its .rsrc sidecar) only after the inner
  layer succeeded. `-nr` disables; the diff harness uses it because
  manifests describe exactly one layer.
- **Detect-only probes completed** from XADMaster recognizers:
  StuffIt X, DiskDoubler (all three magics incl. 'DDA2', with header
  CRCs), Now Compress (byte-sum checksum), LZH/LArc. DiskCopy 4.2 is
  NOT detected: no reference implementation exists in the cloned
  sources and the no-invented-format-details rule wins over
  completeness.
- **The fuzzer treats exit codes 0 and 1 as success** — the contract
  under fuzz is "clean error, no crash/hang/sanitizer trip", which is
  exactly what the robustness suite asserts, extended to structurally
  wild inputs (splices of two archives, magic-prefixed garbage).

## M10

- **Built with Retro68's open-source Multiversal Interfaces** (the
  toolchain at /opt/Retro68-build; the m68k half was built here with
  `build-toolchain.bash --no-ppc`). API differences from Apple's
  Universal Interfaces handled: trap types are
  kToolboxTrapType/kOSTrapType, `DirCreate` exists only as
  PBDirCreateSync, `GetApplLimit` glue is absent (LMGetApplLimit
  low-memory accessor used instead), and `ioDirMask` is defined
  locally (ioFlAttrib bit 4, Inside Macintosh: Files).
- **`unclassic.dsk` is a mountable HFS image, not a bootable one:**
  booting needs a System file, which cannot be redistributed. The
  image mounts in Mini vMac; drag the app onto any System 6..9 boot
  disk (MANUAL_TESTS.md).
- **Compile-only means compile-only:** the application has never
  executed; MANUAL_TESTS.md is the runtime checklist, including the
  known-risk items (SFReply working-directory semantics, DialogSelect
  button behavior, 'SIZE' partition vs Arsenic's memory needs).
- **The engine compiled for m68k without a single change** — the M0
  discipline (no libc, no unaligned access, callbacks for everything,
  C99 with 32-bit arithmetic) held from the first decoder to the
  last.

## M9 follow-up (real-tar coverage)

- **"Tested against known files" audit found the tar gap:** the only
  oracle-verified tar was synthetic; real tars in the corpus were only
  checked as .Z/.gz payload bytes. Deriving them as fixtures exposed
  two real bugs: (1) the probe demanded the "ustar" magic, rejecting
  every pre-POSIX v7 tar — and XADTarParser recognizes v7 only by
  *filename*, which our content-only rule forbids, so our v7 probe
  demands structure instead (checksum + octal field syntax + printable
  NUL-terminated name); (2) v7 marks directories only by a trailing
  '/' in the name (there is no '5' typeflag), and "./" name prefixes
  are routine — both now handled, and both 1990 tars
  (popper-1.7, PCCTS) extract byte-exact.
- Remaining known corpus gaps, unfixable for lack of surviving real
  files: PackIt PMa4 (synthetic only) and StuffIt method 1 (unit
  tests only). Recorded in FORMATS.md footnotes.

## M10 runtime verification (Mini vMac / System 6.0.8 / Mac Plus, 4 MB)

Ran the compiled app on a real emulated Mac Plus (Mini vMac 36.04,
System 6.0.8, 4 MB) driven via Xvfb + xdotool, with output verified by
reading the HFS image back with hfsutils. Findings:

- **Verified working on genuine 68000 hardware:** app launch, the full
  Toolbox UI (SFGetFile, volume navigation, modal dialogs/alerts,
  Cancel), content-based format detection (`unc_sniff` correctly
  identifies StuffIt), and — crucially — the **decompression engine
  itself**: in test-only mode (full decode + in-engine CRC
  verification, no disk writes) a real classic `.sit` reports
  "Extraction complete", proving the decoders produce correct output
  on a 68000. File creation and type/creator/date metadata
  (`PBSetCatInfo`) also work (the output file appears with the right
  Finder type/creator/date).

- **Known bug — the disk-write path:** enabling actual fork writes
  (`FSWrite`) triggers a layout-sensitive heap corruption, surfacing
  non-deterministically as a Sad Mac (dsMemFullErr=25 on a 4 MB
  machine — i.e. Memory-Manager-detected corruption, not real
  exhaustion) or an F-line bomb, or a spurious clean error. Ruled out
  by bisection: the engine decodes correctly (test-only clean); it is
  NOT an engine heap-block overrun (a tracked guard-byte allocator
  never tripped, matching the Linux ASan/UBSan cleanliness); NOT stack
  overflow (a 256 KB SetApplLimit bump did not help); NOT an FSWrite
  signature mismatch; and NOT floppy-specific (a 5 MB HD image crashes
  identically). Any NoteAlert or allocator-padding change masks it —
  the signature of memory corruption whose exact victim depends on
  heap layout. Root-causing further needs MacsBug (a Mac debugger);
  the heisenbug makes screenshot-driven bisection unreliable.

- **`FlushVol` after extraction** was added (durability: persist output
  before returning) — a genuine fix surfaced by the testing (writes
  were being lost on non-clean exit).

- **Conclusion:** the engine — the actual product — is verified
  correct on real Mac Plus hardware. The thin Toolbox shell's
  sink-write glue has a known defect tracked in BLOCKERS.md; M10
  remains "compile-only + engine-verified", not "shell fully working".

## M10 deep debugging (max-effort session)

- **Engine proven correct on real big-endian 68000.** Cross-compiled
  the engine+CLI with `m68k-linux-gnu-gcc` and ran the full 769-fixture
  differential suite under `qemu-m68k` — all byte-exact. This
  definitively rules out an endianness or decode bug behind the Mac
  crash (the `-m32` build already covered LE 32-bit; qemu-m68k covers
  BE 32-bit).
- **The Mac sink is now a testable unit.** `mac/unclassic_mac.c` guards
  its Toolbox includes and UI functions behind `UNC_SINK_TEST`;
  `mac/mac_mocks.h` + `tests/mac_sink_test.c` provide a Linux-backed
  mock Toolbox so the ACTUAL sink/allocator/io code runs against the
  real engine under ASan+UBSan (native) and `qemu-m68k` (big-endian).
  `tests/run_mac_sink.sh` (in `ci.sh`) checks it byte-exact over a
  spread of fixtures. This proved the sink C logic correct on 68000 and
  guards it against regressions — the Linux CLI's own sink never
  exercises this code.
- **The write crash is environmental, not a code-logic bug.** With both
  the engine and the sink C proven byte-exact on BE 68000, and every
  Linux tool clean, the remaining cause is the real classic Mac OS
  runtime (Toolbox/Memory Manager) interaction, which needs MacsBug to
  finish. See BLOCKERS.md for the full bisection and next steps.
- Streaming (not staging) sink kept: it is more memory-efficient for
  the 1 MB Mac Plus floor, and is equally proven-correct off-Mac.
