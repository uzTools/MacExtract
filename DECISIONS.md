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
  With lazy sizing the corpus measures: min 0.63 MB, median 0.97 MB,
  mean 1.23 MB, max 2.53 MB (fixtures that genuinely fill their
  blocks). A 1 MB Mac Plus can therefore expand small Arsenic archives
  but will cleanly refuse large ones per entry (UNC_ERR_MEM) — by
  design.
  **RE-CONFIRMED 2026-08-01, against a later entry that contradicted
  it.** The M10 entry below ("Arsenic block sizes are 128 KB
  (dominant) / 256 KB / 512 KB, not 'always 512 KB'") was the wrong one
  of the pair: instrumenting the point where `sit_arsenic.c` reads the
  block-size field shows all 484 Arsenic streams across the 31-fixture
  corpus — one per compressed fork — declaring 512 KB, without exception. This entry stands; only
  the precision of its figures has been sharpened.
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
  **[SUPERSEDED 2026-07-25 — the DiskCopy 4.2 half only.]** A reference
  was later obtained (`reference/notes/DiskCopy42.md`, from the
  DiscFerret wiki) and the probe is now real: `unc_diskcopy_probe`
  (`src/fmt_stubs.c:76`) matches a synthetic 800K GCR image and a real
  one, with 0 false positives across 803 fixtures. Still detect-only —
  disk images remain out of scope for v1. The rest of this entry stands.
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
  **[SUPERSEDED — true when written, false since the M10 runtime
  sections below.]** The application runs on a real System 6.0.8 Mac
  Plus under Mini vMac and extracts byte-exact (44/44 sampled fixtures
  at 4 MB, 39/44 at 1 MB), and its interactive UI has been driven end to
  end (`tools/vmac/interactive.py`, MANUAL_TESTS.md). Of the three
  known-risk items listed here, only the System 7+ `SFReply`
  working-directory semantics remain untested — see OPEN_ITEMS.md.
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

- **[SUPERSEDED — the whole of this bisection was confounded. See BLOCKERS.md
  "Earlier 'root causes' that turned out to be confounded": every File Manager
  open was silently failing throughout, so the observations below are real but
  the conclusions drawn from them are not. The write path works and is verified
  byte-exact on-Mac.]**
  Known bug — the disk-write path: enabling actual fork writes
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
  **[SUPERSEDED — the shell is fully working and verified byte-exact
  on-Mac; see the M10 sections below.]**

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
- **[SUPERSEDED — "environmental" was as far as this reasoning could get, and
  it was wrong: the cause was in unclassic's own File Manager calls, and the
  param-block rewrite fixed it. See the M10 sections below.]**
  The write crash is environmental, not a code-logic bug. With both
  the engine and the sink C proven byte-exact on BE 68000, and every
  Linux tool clean, the remaining cause is the real classic Mac OS
  runtime (Toolbox/Memory Manager) interaction, which needs MacsBug to
  finish. See BLOCKERS.md for the full bisection and next steps.
- Streaming (not staging) sink kept: it is more memory-efficient for
  the 1 MB Mac Plus floor, and is equally proven-correct off-Mac.

## M10 write path — resolved (single-fork) + characterized (two-fork)

The earlier "disk-write crash" was NOT one bug but a stack of them; the
Mac app now extracts single-fork files correctly under Mini vMac. See
BLOCKERS.md for the full write-up. Key decisions:

- **`mio_seek` tolerates `eofErr`.** A `SetFPos` to/past EOF returns
  `eofErr` on a real Mac while still positioning at EOF; treating that as
  a hard error made valid end-of-file seeks fail with a spurious
  `UNC_ERR_IO`. The mock's `SetFPos` was updated to reproduce this so the
  test suite catches the class of bug.
- **[SUPERSEDED 2026-08-02 — the archive is now read straight off the file;
  see "The archive is no longer slurped into RAM" at the end of this file.
  The interleaving claim below is from the confounded period and does NOT
  reproduce: `UNC_AT_INTERLEAVE` reads a file three ways on one volume with
  67 file creations in between and gets the same CRC every time.]**
  ~~**Slurp the whole archive into RAM, decode from memory** (`MemIO` /
  `xio_*`). On a real Mac, interleaving File Manager reads of the input
  with writes to output files on the same volume makes the input reads
  return zeros. Reading everything before any output exists removes the
  interleave.~~ Also keeps all output writes shallow (in `sink_end`) —
  deep writes from the decode callback corrupt the HFS volume. The
  `xio_*` path is now exercised off-Mac too (mock `ram` mode, ASan +
  qemu-m68k). Archives are small, so a full-file RAM buffer is fine.
- **[SUPERSEDED — streaming is the shipped sink; see "The Mac sink writes each
  chunk straight to the File Manager" at the end of this file. The volume
  corruption reported here dates from the confounded period (BLOCKERS.md) and
  did not survive re-testing.]**
  Staging (not streaming) is the shipped sink. A streaming
  write-as-you-decode variant (open fork, write each chunk, switch
  forks) does deep File Manager writes and corrupts the volume worse
  than staging. Reverted the note above: staging + shallow writes wins on
  the real Mac. (Both are byte-exact off-Mac.)
- **[SUPERSEDED — "three blocks bomb the Memory Manager" is FALSE; re-tested
  with `UNC_AT_SEPARATE_BLOCKS` once the opens were fixed, and a two-fork file
  extracts byte-exact with three blocks (BLOCKERS.md). The shared block is
  still what the staging path does — it is harmless and marginally more
  heap-friendly — but the justification below is not why.]**
  Two-fork files: stage both forks in ONE shared block (Mac build).
  Staging the two forks in two *separate* `NewPtr` blocks — a third
  non-relocatable block beside the archive buffer — corrupts System 6's
  Memory Manager and bombs the app (byte-exact off-Mac; crashes only on
  the real Memory Manager). It's the block *count*, not memory: a 63 KB
  resource-only file in two blocks works; a 43 KB two-fork file in three
  crashes. Fix: one contiguous block holding the data region then the
  resource region, so block count stays at two like the single-fork case
  (`sharedBuf` in `mac/unclassic_mac.c`). Confirmed on real Mini vMac
  (app idles, no bomb) and proven byte-exact for both forks off-Mac via
  `UNC_MAC_FORCE_SHAREBUF` in `tests/run_mac_sink.sh` (ASan + qemu-m68k).
  Guarded `#ifndef UNC_SINK_TEST`; a rare unknown-fork-size two-fork entry
  falls back to keeping the larger fork (avoids a two-block allocation).
  (Superseded an earlier stopgap that always dropped the smaller fork.)
- **Reserved-header diff is expected, not a defect.** Resource forks come
  out byte-exact except offsets 16–127 ("reserved for system use"),
  which a real Mac's Resource Manager stamps per machine/session. The
  Mini vMac autotest treats an all-in-16..127 diff as a pass.

## M10 (real Mini vMac) — the decisions that actually made it run

- **[WITHDRAWN 2026-07-25 — see "The 'broken Retro68 HOpen glue' root cause is
  WITHDRAWN" at the end of this section. The fix below is kept and still ships;
  only the explanation is retracted.]**
  ~~The Mac never ran because Retro68's HOpen glue is broken on System 6.~~
  `HOpen()` returns `noErr` but never writes back the file refNum, so
  `GetEOF`/`FSRead` then operate on garbage: the archive slurps as 0 bytes and
  the whole extraction fails as `UNC_ERR_FORMAT`, silently. `HOpenDF` returns
  `paramErr`. This was invisible off-Mac — the qemu mock calls the sink
  directly and never touches the glue. **Fix:** drive the File Manager through
  explicit HFS param blocks (`PBHOpenSync`/`PBHOpenRFSync`/`PBHCreateSync`/
  `PBHDeleteSync`) via `MyOpenFork`/`MyHCreate`/`MyHDelete`, reading back
  `pb.ioParam.ioRefNum` ourselves. This unblocked EVERYTHING; the earlier
  "two-fork crash" investigation was all confounded by it (see BLOCKERS.md).
- **On-screen result channel, not disk.** [The justification below is
  WITHDRAWN 2026-08-02 — it does not reproduce; see "the Out volume can be read
  after all" at the end of this file. The channel itself is kept and still
  ships.] ~~Mini vMac's write-back of a mounted image to its host file is lazy
  and PARTIAL (commits one fork but not the other), so the autotest can't be
  read off the Out volume.~~ The app
  CRC-32s both forks on-Mac (resource fork with the OS-stamped reserved header
  16..127 masked) and paints an 8-value aggregate straight to the framebuffer
  (`qd.screenBits`, `at_report`); the host decodes a screenshot
  (`tools/decode_grid.py` + `tools/vmac_check.py`, referenced against
  `unclassic x -nr`). ~~QuickDraw (NewWindow/EraseRect) bombs after any File
  Manager activity, so the framebuffer poke is deliberate~~ — **that
  justification is WITHDRAWN 2026-08-01: it does not reproduce
  (`tools/quickdraw-repro/`, twelve configurations, every QuickDraw call clean
  with `MemError()==0`).** The framebuffer poke is kept for the reason that
  does hold: it needs no allocation, cannot fail, and is the only channel that
  still reports when the machine is in a state where the Toolbox cannot be
  trusted. `HideCursor()` first so the cursor's saved background can't stamp
  the desktop over the grid.
- **[WITHDRAWN 2026-08-01 — this entry is wrong. See the M7 entry it tried to
  correct.]** ~~Arsenic block sizes are 128 KB (dominant) / 256 KB / 512 KB, not
  "always 512 KB". Measured via `unclassic x --stats` across the 31-fixture SIT5
  corpus: 14 use 128 KB, 9 use 256 KB, 8 use 512 KB; peak heap ≈ 5× block =
  0.64–2.6 MB.~~ All 484 Arsenic streams in the corpus declare **512 KB**; the
  M7 entry was right all along. The mistake was the method: `--stats` reports
  peak heap, and peak is `~35 KB parser state + 512 KB block + 4 × actual block
  fill`, not `5 × block`, because the transform vector is lazily sized (which is
  what the M7 entry says). Dividing a peak by five therefore reads every
  small payload as a small block — 0.64 MB is a 512 KB block holding ~24 KB,
  not a 128 KB block. Peak heap cannot recover the declared block size at all;
  the field has to be read where `sit_arsenic.c` reads it, which is what was
  done to settle this. What survives: every Arsenic entry exceeds 400 KB, so
  Arsenic is a ≥4 MB-machine tier — works on a 4 MB 68000, mostly refuses
  cleanly on a 1 MB Plus, and there the boundary is the *archive's* size (it is
  slurped into RAM before the engine gets its budget), not the block size.
- **'SIZE' resource: 4 MB preferred / 400 KB minimum.** The engine budget is
  already derived at runtime from `FreeMem()`, so one binary adapts from a
  1 MB Plus (small files only) to a G3. On System 6 without MultiFinder the
  SIZE is ignored and the app gets all free RAM anyway.
- **Cancel/error removes the partial file.** An entry creates its file in
  `sink_begin` before decoding; on a Cmd-. cancel or per-entry failure
  `sink_end` now `MyHDelete`s it, so no empty/incomplete output is left behind.
- **DiskCopy 4.2 stays detect-not-implemented.** No reference is available
  offline (XADMaster has no DiskCopy parser, reference/notes has no page, the
  network is refused), and rule #3 forbids inventing the magic/header from
  memory. The `UNC_FORMAT_DISKCOPY` name exists; the probe never matches.
  **[SUPERSEDED 2026-07-25 — the probe is now real.]** A reference did become
  available (`reference/notes/DiskCopy42.md`, from the DiscFerret wiki), so the
  rule stopped biting: `unc_diskcopy_probe` (`src/fmt_stubs.c:76`) matches a
  synthetic 800K GCR image and a real one, 0 false positives across 803
  fixtures. Still detect-only, because disk images are out of scope for v1.
  See BLOCKERS.md "Detect-only gap — RESOLVED".
- **The "broken Retro68 `HOpen` glue" root cause is WITHDRAWN.** M10's write-up
  (BLOCKERS.md, commit 22e806b) blamed Retro68: "`HOpen` returns `noErr` but
  never writes back the refNum on System 6". Building the standalone minimal
  reproduction that was supposed to go upstream (`tools/retro68-hopen-repro/`)
  disproved it. On the same System 6.0.8 / Mac Plus / Mini vMac / Retro68
  `335fa54f6d` setup, ten cases all pass: `HOpen` writes the refNum every time
  and matches a hand-filled `PBHOpenSync` exactly — with a poisoned stack, with
  a real vRefNum and non-zero dirID, with `fsWrPerm`, with `HOpenRF`, and
  across volumes (the app's own pattern). A theory that the glue's
  uninitialised `ioMisc` was to blame was also tested and disproved: poisoning
  `ioMisc` with `0xA3A3A3A2` still opens and reads correctly.
  Consequence: the param-block rewrite (`MyOpenFork`/`MyHCreate`) is kept
  because it demonstrably works, but its justification is now "it zeroes the
  whole param block", not "the glue is broken". **The true root cause of the
  original failure is unestablished and is deliberately not being chased
  further** — the shell is verified byte-exact on-Mac as it stands, and a
  wrong explanation in the docs is worse than an admitted gap. Rule: a
  root cause that has never been reduced to a minimal reproduction is a
  hypothesis, not a finding.
- **No upstream issue was filed.** Two things blocked it. (a) The headline
  finding is false, per the entry above, and filing it would have sent a wrong
  bug report to a third-party project. (b) This environment has no `gh` CLI and
  no GitHub credentials, so it could not post one regardless. What survives is
  small but real — **both `OpenDF` and `HOpenDF`** return `paramErr` on
  System 6, because the `_OpenDF` trap is System 7 and neither falls back the
  way `FSOpen` in the same file does; plus the latent uninitialised-`ioMisc`
  inconsistency in the three H-variants. Written up ready to post in
  `tools/retro68-hopen-repro/ISSUE.md`. **Corrected 2026-08-01**: that
  write-up named only `HOpenDF`, and said `OpenDF` "already has the fallback".
  It does not — `FSOpen` does. Settled by running it (case 11), not by reading
  `glue.c` again, which is how the first version of this went wrong.
- **The on-Mac resource-fork mask is bytes 16..127 and it is header padding,
  not a fudge.** The autotest compares resource forks by CRC, and the System 6
  Resource Manager stamps session scratch into part of the header, so a raw CRC
  would mismatch every time. The masked range is exactly the 112-byte "reserved
  for system use" area of the 256-byte resource FILE header (Inside Macintosh:
  More Macintosh Toolbox, Resource Manager) — verified on a real fixture: `AT
  View.rsrc` has dataOffset=256, mapOffset=16805, do+dl==mo and mo+ml==filesize,
  so bytes 16..255 are pure padding, split 112 system / 128 application.
  Note this is the resource *file* header, not the resource *map* header (whose
  own reserved area is the 22 bytes at mapOffset, per
  reference/XADMaster/XADResourceFork.m).
  Two deliberate limits keep the mask honest: (a) bytes 128..255, the
  application-reserved area, are NOT masked — they carry real content (THINK C
  writes its copyright notice there) and must still match byte-exact; (b)
  `mask_reserved()` refuses to mask at all unless the fork's own dataOffset and
  mapOffset are both >= 128, so a non-standard layout fails loudly instead of
  being silently papered over. Swept across the corpus: 1545/1545 resource
  forks have the standard layout, 0 non-standard.
- **The on-Mac harness is committed and fetches its copyrighted inputs, rather
  than shipping them.** Every "runs on real System 6" claim in this repository
  used to rest on a working directory that was never checked in and no longer
  exists, so nothing could be re-run, disputed or debugged — and two of the
  three open items in BLOCKERS.md were unreproducible for exactly that reason.
  `tools/vmac/` now scripts the whole thing. It follows the `fixtures/` rule for
  the two Apple-copyrighted inputs it needs (a Mac Plus ROM and a System 6.0.8
  image): fetch by URL, verify by SHA-256, never commit. The 44-fixture sample
  it replays is committed as a plain list (`tools/vmac/sample.txt`) so that a
  4 MB run and a 1 MB run months apart compare like for like.
- **The emulator runs "all out", so the harness measures correctness only.**
  Mini vMac's speed is a compile-time option; building it at 1x would make each
  fixture take Mac Plus time and the sweep impractical, and correctness is
  speed-independent. The cost is that no timing claim about a 7 MHz 68000 can
  come from this harness — the previously recorded "185 s for XferIt" has been
  struck rather than restated, since the 1x setup that produced it is gone.
- **The autotest application always reports what it is doing, even when it has
  nothing to report.** It paints a grid with `ret = -1000` before starting work
  and `-1001`/`-1002` when the In/Out volume is missing. Without that, a
  screenshot with no grid was ambiguous between "never launched", "bombed" and
  "still decoding", and the harness could only report a timeout — which is
  precisely how a broken disk set once looked like a slow decoder. The codes
  sit far outside the engine's `UNC_ERR_*` range so they cannot be confused
  with a result.
- **The Mac sink writes each chunk straight to the File Manager; it no longer
  stages whole forks in RAM.** Staging cost the shell `archive + engine peak +
  largest output fork`, which is what stopped a 1 MB Mac Plus extracting the
  two largest-output fixtures in the sample — a limit on *output size*, which
  is a strange thing for a floor-target machine to have. The comment that
  justified staging said writes from the deep decode callback corrupt HFS, but
  that dates from the period BLOCKERS.md records as confounded, so it was
  re-tested rather than trusted: streaming is byte-exact through the mock
  (native ASan/UBSan and big-endian qemu-m68k) and on a real System 6.0.8 Mac
  Plus, 44/44 at 4 MB and 39/44 at 1 MB, where the only remaining failures are
  StuffIt 5 memory-budget refusals. Deep writes are safe here for a concrete
  reason: the archive is slurped into RAM first, so no File Manager READ is
  ever interleaved with the writes on the same volume. The staging path stays
  buildable as `UNC_MAC_STAGE_WRITES` and CI proves both byte-exact.

## 2026-08-01 — two claims reduced to reproductions, both disproved

- **"QuickDraw bombs after any File Manager activity" is FALSE**
  (`tools/quickdraw-repro/`). It had been filed in BLOCKERS.md under "real
  test-harness lessons (not app bugs)", which is what let it sit unexamined:
  as stated it meant the shipped interactive build was broken, because that
  build's path is SFGetFile -> a progress dialog -> a result alert, i.e. File
  Manager followed by QuickDraw. A standalone Retro68 application now runs
  `NewWindow`/`EraseRect`/`DrawString`, `GetNewDialog`+`DrawDialog` and an
  `EraseRect` on the Window Manager port immediately after 64 KB of File
  Manager writes, a read-back and a catalogue walk, in twelve configurations
  on the same System 6.0.8 / Mac Plus / Mini vMac setup. **Every call
  succeeded with `MemError() == 0`.** Both suggested causes are disproved
  too: `MaxApplZone` + 12x `MoreMasters` were already present when the claim
  was made, and *removing* them does not produce the failure (with no
  `MaxApplZone` the heap is ungrown, `FreeMem()` reports 2 KB, and QuickDraw
  still allocates cleanly because the Memory Manager grows the zone on
  demand); and launching the same binary from a normal Finder desktop instead
  of installing it as the boot shell behaves identically. `at_report()` keeps
  poking the framebuffer, for the reason that survives: no allocation, cannot
  fail, and it is the only channel that still reports when the Toolbox cannot
  be trusted.
- **The reporting channel cannot be the thing under test.** `qd_repro` writes
  its log to the framebuffer through its own 5x7 font, and carries a row of
  marker squares in the top eight scan lines — where System 6's centred system
  error dialog cannot cover them — so a bomb still says which probe was
  running. `decode_log.py` reads that log back to ASCII by matching each glyph
  against the same table parsed out of the C source, so the sweep is
  self-checking without the screenshots ceasing to be the primary evidence.
- **`mkboot.py --finder`**: leave the boot blocks alone and put the
  application at the volume root, so it has to be double-clicked like any
  other application. Every on-Mac result until now came from the app installed
  as the boot *shell*, which is a materially different environment (nothing
  mounts disks, no other process competes for the heap), and "does this happen
  in a normal application?" could not be asked without it.
- **All 484 Arsenic streams in the corpus declare 512 KB blocks.** See the
  withdrawn M10 entry above: peak heap cannot be divided by five to recover a
  block size, because the transform vector is sized to the actual block fill.
  Measured by instrumenting the read of the block-size field itself.

## 2026-08-01 — what the corpus actually contains, measured rather than recalled

The two "known corpus gaps" were re-examined by instrumenting the format
readers (the method byte in `fmt_sit.c`, the block magic in `fmt_packit.c`)
and scanning all 802 fixtures, instead of trusting the note that recorded
them. One of the two was not a gap at all.

- **StuffIt method 1 is in the corpus.** `derived-New_Python.sit`, one 470-byte
  resource fork. FORMATS.md and PROGRESS.md had said for months that method 1
  "does not occur in the harvested corpus". It does; the engine decodes that
  archive end to end with every CRC-16 passing. What is genuinely missing is
  ORACLE coverage, because `unar` fails on that archive ("Attempted to read
  more data than was available"), so `make_manifests.py` correctly refuses a
  manifest and the differential suite never sees it. The corrected claim is
  narrower and stronger than the one it replaces: method 1 is exercised on a
  real file, just not adjudicated by a second implementation.
- **StuffIt method 6 exists, is unimplemented, and had never been named.**
  `derived-INITLoader.sit`, one 34,818-byte fork. The engine returns
  `UNC_ERR_UNSUPPORTED` per entry, which is the right behaviour, but no
  document in this repository mentioned that method 6 was a thing. It is
  "Fixed Huffman" per `reference/XADMaster/XADStuffItParser.m:284`, and
  XADMaster does not implement it either — `//case 6: fixed huffman` at line
  319 — so there is neither an oracle to validate an implementation against
  nor a second fixture to test one on.
- **The PackIt PMa4 gap stands.** All nine PMa4 blocks in the corpus come from
  the three `synth-packit-*.pit` archives; the only real PackIt fixture,
  `derived-PackIt.pit`, is four stored (`PMag`) blocks. The Huffman path still
  has no real-world file behind it.

The method is worth keeping: a per-entry histogram over the whole corpus costs
one instrumented build and a minute, and it answers "what do we actually
have?" in a way that reading old notes does not. It is the same technique that
overturned the Arsenic block-size claim earlier the same day.

## 2026-08-01 — testing a working directory without a Finder

`SFReply.vRefNum` with `dirID` 0 had been listed as untested since M10, and
two attempts to reach it by driving System 7's Finder produced nothing but
mis-aimed double-clicks. The attempts were the wrong shape.

**`UNC_AT_WD`**: the autotest build makes its own working directory over a
subfolder with `PBOpenWD`, calls `RunExtract` with `(vRefNum = that WD,
dirID = 0)` — byte for byte the call `ExtractOne()` makes with what Standard
File returns — and counts the files in the folder against the files in the
volume root. No Finder, no Standard File, no screen coordinates, five seconds
a run, and it works identically on System 6 and System 7 so the two can be
compared.

Passes on both: 3 entries, 3 files in the folder, 0 in the root, with
wdRefNums of -32717 and -32701 — negative and outside the volume range, so
genuine working directory references and not volume refNums that happened to
work.

The general lesson, and it is the second time this session: **when a UI test
is hard to drive, ask what the UI actually hands the code, and hand it the
same thing directly.** The Finder was never the thing under test; it was
scenery, and expensive scenery — ten minutes a run and a coordinate hunt each
time the desktop layout changed. What mattered fits in forty lines and needs
no screen at all.

The empty-root assertion is the whole test. Every earlier harness here
extracted into a volume ROOT, where the working directory and the root are
the same directory — so none of them could have caught a mistake in this
code, however many times they ran.

## 2026-08-02 — driving the Mac OS 9 Finder with the keyboard, not the mouse

Getting the application to launch on Mac OS 9 took six boots. Five of them
were spent on the mouse.

The symptom never varied: the volume did not open. Three explanations were
published against it, each a real defect, each fixed, none of them the answer
— a double click spanning 0.9 s, an ADB pointer being fed absolute
coordinates, and the Setup Assistant holding the foreground. All three are
explanations of *clicking*, because the symptom was read as "the click was
wrong" rather than "something in the chain broke".

`tools/vmac/os9probe.py` broke the loop by measuring primitives instead of
outcomes, cheapest first, on targets that answer unambiguously: does a held
press pull a menu bar title down? does a single click merely SELECT the icon?
does the cursor go where it is sent? Eleven probes, one boot. Every mouse
probe changed exactly 0.0000 of its watched rectangle; every keyboard probe
worked; and the cursor-locating probe found the pointer only ever in screen
corners, never at any requested position.

So the decision is: **the Finder is driven from the keyboard.** Type to select
by name, Cmd-Down to open, Cmd-Q to quit. No coordinates to measure, no
double-click threshold to hit, nothing to re-measure when the desktop layout
changes. It worked first try and it is what `launch_by_keyboard()` does.

Two lessons, and the second is the one worth carrying:

- **Measure the primitive before theorising about the compound.** An outcome
  that did not happen names no link in the chain. This is the same mistake as
  the `macburger-helper.hqx` timeout, which was written up as an anomaly three
  times before anyone instrumented the byte counter.
- **A fix that is real is not thereby sufficient.** Three consecutive
  confirmed defects were fixed and the thing still did not work. Each fix felt
  like progress and each was published as a root cause. The habit that stops
  this is refusing to call anything a root cause until the symptom is gone.

## 2026-08-02 — checking Mac OS 9 output through the disk image, not the screen

Mini vMac's harness CRC-32s both forks on the Mac and paints the aggregate to
the framebuffer, because getting a floppy back out of Mini vMac mid-run is
awkward. That machinery — `at_report()`, the on-screen grid, `decode_grid.py`
— was the obvious thing to reuse on Mac OS 9, and it would have been the wrong
thing: it exists to work around a constraint OS 9 does not have.

The OS 9 transfer volume is a plain file on the host. So `verify_output()`
waits for the emulator to exit and then reads it: the Apple_HFS partition is
lifted out at the offset `mkapmdisk.py` wrote it at, hfsutils mounts it, and
`hcopy -m` pulls each extracted file off as MacBinary — which is how both
forks come across in one file, since hfsutils cannot copy a resource fork on
its own. The forks are then compared byte for byte with `unclassic x -nr`.

This is strictly stronger than the screen grid: it compares bytes rather than
a CRC of them, it needs no pixel decoding, it reports which file and which
fork differed, and it cannot be defeated by a 1bpp report routine meeting a
32-bit colour screen. It also answers a question nobody had asked — whether
the guest flushed its writes before being killed — because an unflushed volume
fails to mount or comes up a file short instead of passing quietly.

The general form: **when the environment changes, re-ask what the workaround
was working around.** The framebuffer channel was a good answer to Mini vMac's
constraint and a bad answer to QEMU's.

**It found a real bug within one run of being written**, which is the argument
for it. The on-screen grid reports `nfiles`, summed CRCs and summed lengths —
it has never compared a single output NAME, and could not, because a name does
not survive being summed into a CRC total. The first OS 9 sweep failed on
`synth-exo-Z.Z` and `synth-exo-gz.gz`: the Mac wrote `archive.sit~1` where
Linux wrote `archive`. Both fixtures are in `sample.txt` and both had been
passing on Mini vMac for weeks.

The cause was in the Mac shell, not the harness. `unclassic.h` documents
`name_hint` — the fallback name for formats that store none, gzip and .Z — as
"the archive filename minus its last extension"; `cli/main.c` strips the
extension, and `RunExtract()` passed the whole Pascal string. So opening
`foo.gz` on any Mac wrote a file called `foo.gz`, which collided with the
archive sitting beside it and became `foo.gz~1`, where every other
implementation writes `foo`. Fixed in `mac/unclassic_mac.c` with the same
rule the CLI uses, including "a leading dot is not an extension".

The lesson is about what a test is blind to rather than about the bug: **an
aggregate check cannot fail on a property it never aggregates.** Nobody had
written down that on-Mac names were unverified, because the harness looked
thorough — twelve formats, both forks, byte-exact. It was thorough about
bytes.

**And then the new checker's own first verdict was wrong, in the same shape.**
It reported 7/11, and all four failures were its blind spots rather than the
Mac's:

- it listed only the volume ROOT, so `synth-exo-tar.tar` — which extracts to
  `README.txt`, `bin/` and `docs/` — looked like one file of four, with the
  other three "MISSING". The Mac had written all four, correctly, in folders;
- it read HFS names as UTF-8. They are MacRoman, so PackIt's `Appé` compared
  unequal to itself. `run_diff.py` has decoded and NFC-normalized for exactly
  this reason for months;
- it treated "the Mac wrote nothing" as failure. For `derived-DandStoQIF2.sea`
  nothing is the CORRECT answer — the engine sniffs it as DiskDoubler, which
  is detect-only by the brief, and the app duly says "This file could not be
  extracted". Linux writes nothing either. Agreement on nothing is a pass, and
  it verifies the refusal path.

All three are fixed, and re-running the checker over the SAME captured volumes
turned 7/11 into 11/11 without the Mac doing anything differently — its output
never changed, only the reading of it. (Two further fixtures, a StuffIt 5 and
a 285 KB self-extracting archive, were added and run afterwards, for 13/13.)
The near-miss is the point
and is why it is written down: a FAIL from a young harness is a claim about
the harness until it is shown to be a claim about the target. That is the same
error as reading a cause into a timeout, arriving from the opposite direction.

## 2026-08-02 — the reporting channel, not the volume, was what blocked HFS+

"Extraction has never touched an HFS+ volume" sat in MANUAL_TESTS.md from M10
onwards, and it read like a missing capability: no HFS+ writer in this
environment, no way to prepare such a volume. It was not that at all.

The autotest build finds its volumes **by name** — `In` and `Out`. The Mac OS 9
boot volume is HFS+. Renaming it to `Out` in the Finder, from the keyboard,
points the existing binary at HFS+ with no code change whatsoever. The real
obstacle was in the other direction: `at_report()` writes 1bpp pixels straight
at the framebuffer, which is the best possible channel on a Mac Plus and
completely invisible on OS 9's 32-bit screen. The output volume was never the
problem. **The answer channel was**, and nothing had said so, because the row
was filed under what could not be written rather than what could not be read.

So `at_report_file()` writes the same values to a file on the plain-HFS INPUT
volume — the one the harness built, so the one it can always read, whatever
the volume under test happens to be. It carries every output NAME as well as
the aggregate, because an aggregate is precisely what cannot answer a question
about names, and names are most of what HFS+ might have changed.

Two things went the way this project keeps going, and both are worth keeping:

- **Two screen-based completion detectors were written before the artifact
  was.** First "wait for the screen to change", then "wait for it to go black,
  since at_report zeroes the framebuffer". Both ran to their full 240 s
  timeout on a run that had already succeeded — eight minutes of waiting for
  proxies that could not fire, on a run that takes two. Polling the host's
  copy of the transfer image for the report FILE finds it in ~20 s. **Wait for
  the artifact, not for a sign of the artifact.**
- **"It landed on HFS+" was nearly left as an inference.** The obvious check —
  ask the File Manager for the volume's signature — is worthless here: the
  classic API answers `'BD'` for an HFS+ volume for compatibility, so a
  negative proves nothing. The check that does work needs no guest code at
  all: hfsutils can see only the volume's HFS wrapper, so if the output were
  on plain HFS it would be visible there. It is not; the wrapper still holds
  its single placeholder file. A signature read at a fixed offset is exactly
  what produced the withdrawn "the boot volume is plain HFS" claim, so making
  the same read the basis of the fix would have been a poor joke.

## 2026-08-02 — the archive is no longer slurped into RAM

`RunExtract()` used to `NewPtr(fileSize)` and read the whole archive in before
the engine was given any budget. That cost landed entirely on the floor
target: on a 1 MB Mac Plus a 278 KB archive took 278 KB away from the engine
before extraction started, which is why README had to explain that *which*
StuffIt 5 entries fail there follows the size of the archive rather than what
is in it.

The justification, from M10, was that "interleaving File Manager reads of the
input with writes to output files on the same volume makes the input reads
return zeros". It was never reduced to a reproduction, and it was suspect for
a specific reason: **the very next bullet in the same list** — "deep writes
from the decode callback corrupt the HFS volume" — came from the same
investigation and had already been withdrawn, because it dates from the period
when every File Manager open was silently failing and it did not survive
re-testing. "Reads start returning zeros" is exactly what that confound looks
like.

`UNC_AT_INTERLEAVE` settles it. It reads one file three ways on one volume and
compares CRC-32s: undisturbed; in chunks with a fresh file created and written
on that same volume between every chunk; and again seeking explicitly with
`SetFPos` before every read, which is the shape a file-backed reader actually
has. **Identical every time** — 278,294 B / CRC 05746998 over 67 rounds, and
286,720 B / CRC 8f448a65 on a second fixture, at 4 MB and at 1 MB. The claim is
withdrawn.

So the default is now a `FileIO` that seeks and reads as the engine asks, with
the input file held open across the whole extraction. `UNC_MAC_SLURP_ARCHIVE`
keeps the old path buildable, the same way `UNC_MAC_STAGE_WRITES` keeps the
pre-streaming sink.

Measured on a real System 6.0.8 Mac Plus:

| run | before | after |
|---|---|---|
| 44-fixture sample, 4 MB | 44/44 | 44/44 |
| 44-fixture sample, **1 MB** | 39/44 | **40/44** |
| same sample, 4 MB, **output on the archive's own volume** | never run | **44/44** |

The 1 MB gain is one fixture, but the change under it is bigger than the tally
shows: three of the four that still fail went from refusing everything to
extracting most of it — `derived-Library_ISBN_Barcoder.sit` 0 of 34 entries to
**31 of 34**, `derived-Troi-ClipSave-Plug-in1.1.sit` 0 of 13 to **6 of 13**,
`derived-PuzzleGetter_0.8.sit` 11 of 26 to **25 of 26**. Each got back exactly
the budget its own archive had been occupying.

Two things worth keeping:

- **The same-volume case had never been tested at all.** Every autotest run in
  this project's history used a separate `In` and `Out` volume, while the
  interactive application writes next to the archive — one volume. That is
  precisely where the withdrawn claim lived, so the fix could not be trusted
  until it was covered: `UNC_AT_SAMEVOL` points the output at the input's
  volume and the read-back CRC does the rest. 44/44. **A harness can be
  thorough and still have never once assumed the shape the shipped program
  uses.**
- **A claim's neighbours are evidence about it.** This one sat directly beside
  a claim already withdrawn as confounded, in the same bullet list, from the
  same week. That was enough reason to re-test it, and it took one afternoon
  against a cost paid on every 1 MB extraction for months.

## 2026-08-02 — the Out volume can be read after all, so names are checkable

Three claims from the confounded period have now fallen in one day. This is
the third and the one that cost the most, because of what it forced rather
than what it broke.

BLOCKERS.md, under *test-harness lessons*:

> Mini vMac's disk write-back to the host image is lazy and PARTIAL — it can
> commit one fork of a file but not the other — so results cannot be read off
> the Out volume. Verification is done ON-SCREEN instead.

So the System 6 and 7 tiers verify through the framebuffer grid: a file count,
two summed CRC-32s, two summed lengths. That is a fine check of BYTES and
structurally incapable of checking a NAME, because a name does not survive
being summed into a CRC total. Which is exactly how the gzip/.Z fallback-name
defect — `foo.gz` extracting to `foo.gz~1` — sat in the corpus for weeks while
44 fixtures passed twice a day, until the Mac OS 9 harness read a directory
and saw it immediately.

It does not reproduce. `run.py --keep-disks` keeps each run's images and
`tools/vmac/checkdisk.py` reads them: **44/44 byte-exact, both forks, names and
folder structure included.** The decisive fixture is
`derived-RWAsm_Folder.sit` — 38 files and **73 forks**, dozens of them with
both forks non-empty, which is precisely the case the claim named as
impossible. An 8-bit folder name (`spinning brain ƒ`), a MacRoman `Appé` and a
`.DS_Store` all survive too.

The grid is kept. It is proven, it needs nothing of the volume, and it reports
liveness and setup failures that a disk cannot — `checkdisk.py` is an addition,
not a replacement. What changes is that the primary tier is no longer blind to
the one property the OS 9 tier had to catch for it.

**Its first verdict was 38/44, and all six failures were the checker's own.**
`hls` hides names beginning with a dot without `-a`; every hfsutils path
argument must be MacRoman bytes, not the UTF-8 subprocess encodes by default;
and `<X>.rsrc` is a sidecar only when `<X>` exists beside it, which
vmac_check.py documents and which this had to learn again. Fixed, and 44/44 on
the SAME captured images — the Mac's output never changed, only the reading of
it. That is the second time in one day a young harness's FAIL turned out to be
a claim about the harness; it is worth expecting.

The lesson underneath all three withdrawals is the same and is now well
evidenced: **a workaround outlives the claim that justified it, and takes the
capability it displaced with it.** Nobody re-examined the screen channel for
months because it worked. It was not wrong — it was unnecessarily blind, and
nothing recorded that difference until TESTING.md was made to say what each
layer cannot see.

## 2026-08-02 — the claim audit, finished

Every assertion this repository made about Mac or emulator behaviour without a
reproduction has now been tested. The list was short by the end, because most
had already been re-tested during the day:

| claim | outcome |
|---|---|
| QuickDraw bombs after File Manager activity | withdrawn 2026-08-01 |
| deep writes from the decode callback corrupt the volume | withdrawn earlier |
| three non-relocatable staging blocks bomb the Memory Manager | withdrawn earlier |
| interleaved reads/writes on one volume return zeros | withdrawn — `UNC_AT_INTERLEAVE` |
| Mini vMac's write-back is lazy and partial | withdrawn — `checkdisk.py`, 44/44 |
| `HideCursor()` before drawing the grid | **CONFIRMED**, with a reproduction |
| `pkill -9` never flushes; boot+kill corrupts the image | withdrawn — 11 cycles |

Two things are worth keeping out of it.

**Not everything was wrong.** `HideCursor()` is load-bearing, and the audit
gave it the reproduction it never had: built without it, with the pointer
dragged through the grid's cell centres, one cell is stamped over and the
decoded value comes back with a single flipped bit. That is a better outcome
than another withdrawal — the list now separates what is true from what was
merely inherited, which it could not do before.

**The tests kept passing before they meant anything.** The cursor claim
"passed" twice while testing nothing: first with the pointer parked at
coordinates that were outside the emulator window altogether (it sits at
(144,129) on the 800x600 Xvfb), then with the drag following a path *between*
cell rows, which disturbs nothing. Only when the drag was aimed at cell
centres did the bit flip. A green result from a test whose reach has not been
established says nothing at all, and this is the third time today that has
been the actual finding rather than the code under test.

The general form, now evidenced five times over: **an unreproduced claim is a
liability proportional to what it forces.** The write-back claim cost the most
because it displaced a capability (reading names off the volume) rather than
because it was wrong about anything. When one is found, the question worth
asking first is not "is it true?" but "what does it stop us doing?".

## 2026-08-03 — the Arsenic block is grown, not assumed

StuffIt 5 was the one format the "runs on a Mac Plus" claim did not really
cover: 2 of 6 sampled fixtures extracted fully at 1 MB, three partially, one
not at all. Every write-up of it — including several of mine — described the
floor as hard, on the grounds that an Arsenic block is 512 KB and a 1 MB Mac
has about 700 KB of free heap, so there was nothing to win.

That reasoning was wrong in a way worth recording, because it was wrong about
which number mattered. **512 KB is what the block DECLARES, not what it
holds.** `blockbits` comes from the stream and every real Arsenic stream in the
corpus declares 512 KB, but the fill varies enormously: the fixture that peaked
at 643.2 KB on a 1 MB machine was a 512 KB allocation holding **24 KB**. The
transform vector has been sized to the actual fill since M9 for exactly this
reason; the block itself was still allocated at the declared size in
`ars_decode_init`, and nobody had asked why.

So `ars_block_reserve()` grows the block on demand, doubling from 8 KB, capped
at the declared size. Peak becomes `~35 KB parser + capacity + 4x fill`
instead of `~35 KB + 512 KB + 4x fill`. Measured on the corpus:

| fixture | before | after |
|---|---|---|
| `derived-RWAsm_Folder.sit` | 643 KB | **163 KB** |
| `derived-KeyGraphics.sit` | 656 KB | **176 KB** |
| `derived-PuzzleGetter_0.8.sit` | 710 KB | **262 KB** |
| `derived-Troi-ClipSave-Plug-in1.1.sit` | 1034 KB | **650 KB** |
| `derived-a2basic.dmg.sit` | 1319 KB | 1063 KB |
| `derived-Library_ISBN_Barcoder.sit` | 1810 KB | 1810 KB |

The last row is the shape of the result, not a failure of it: that fixture's
blocks really do hold ~316 KB, so doubling lands on 512 KB and nothing is
saved. The win is exactly proportional to how much of the declared block goes
unused, which is what it should be.

Two details that keep it honest:

- **Growing never sets the high-water mark.** During a growth both buffers are
  live, `old + new = 1.5x new`, and the later peak is `capacity + 4x fill`.
  Since 1.5x capacity < 5x fill for any fill worth having, the transient is
  never the peak — so the saving is real rather than moved.
- **The declared size is still enforced.** `blockbits` is 4 bits from the
  stream, so a block can legally declare as little as 512 bytes — smaller than
  the starting capacity — and the reserve clamps to it. The pre-existing
  corruption checks against `blocksize` are untouched; capacity is an
  allocation strategy, never a format bound.

The general form is one this repository keeps meeting from new angles: **a
number that comes from the data is not a number you have to budget for.** The
same mistake in the other direction — treating the archive's size as a cost the
engine must carry — was the RAM slurp removed the day before.

## 2026-08-03 — the LZW table is sized from the input, once

Same shape as the Arsenic block the entry above, found by looking for the same
shape: `unc_lzw_init` allocated `(1 << maxbits) * 4`, the **declared** ceiling.
`compress(1)` writes `maxbits=16` by default whatever it compressed, so `.Z`
cost a flat **274,432 B** for every input — a 488-byte fixture allocated 256 KB
for a table it filled a few hundred entries of. It was the second largest peak
in the format matrix and the only one that did not vary with its input at all,
which is what made it worth suspecting.

**Growth on demand was tried first, and was the wrong answer.** Doubling as
`ars_block_reserve` does measured:

    synth-exo-Z.Z          274,432 -> 18,432 B
    synth-exo-tar-Z.tar.Z  274,432 -> 61,440 B
    a2ps.V4.3.tar.Z        274,432 -> 208,896 B
    popper-1.7.tar.Z       274,432 -> 405,504 B      <- WORSE than doing nothing

That last row is the transferable part. Copy-based growth has an unavoidable
`old + new` transient, and **where the table IS the whole allocation, that
transient becomes the peak**. Arsenic escaped it only because its transform
vector is 4x the fill and dominates the later peak — the note above says as
much ("1.5x capacity < 5x fill"), and the condition simply does not hold here.
So the two cases look identical and are not: *growth pays off only when
something larger than the grown buffer is allocated after it.*

**What works is a bound from the input.** Every input code defines at most one
new symbol and codes are at least 9 bits wide, so

    symbols <= 256 + reserved + insize * 8 / 9

however large `maxbits` claims. One allocation, no transient, strictly smaller
than the ceiling in every case. `fmt_exo.c` passes the stream size less the
3-byte header; StuffIt method 2 passes the entry's compressed length.

The bound is **strict**, which is what lets the decode stay bit-identical:
reaching entry `256 + reserved + k` takes `k + 1` codes, so the table cannot
fill even when every code is the minimum width. That matters because
`maxsymbols` is not just an allocation size — it is where the code width stops
growing and where the table is declared full, both of which the encoder also
decided. Lowering it would silently desync the decoder from the encoder rather
than fail. So `maxsymbols` keeps its declared value and a new `capsymbols`
carries what is allocated; only `capsymbols` was substituted into the
allocation and the chain-buffer bound.

`lzw_grow` widens to the declared ceiling if the bound is ever under-estimated,
so a wrong estimate stays correct rather than overflowing. It is a safety net,
not a strategy, and **it was verified to be both**: with growth hard-disabled
the differential suite is still 769/769, so the bound never under-estimates
anywhere in the corpus; and with `-D UNC_LZW_TINY_TABLE`, which forces the
initial capacity to 258 so growth runs on every stream, it is *also* 769/769
under ASan/UBSan/alignment. Neither number means anything without the third:
starving the table without the safety net gives **675/769**, which is what
establishes that these fixtures can fail on this code at all. 94 of them
exercise it.

Result: zero regressions across the corpus, 50 fixtures improved, `.Z` down
from a flat 268 KB to 15–219 KB, and the 1 MB floor sweep unchanged at 41/44
(this was never what limited it). Numbers in FORMATS.md, footnote §.

## 2026-08-06 — method 13's LZSS window is sized from the entry

Third instance of the same shape, and the first where the ceiling is a genuine
format constant rather than a field read from the stream. `SIT13_WINDOW` is
64 KB because StuffIt method 13 says so, and that is correct — but it is the
size of the window the format PERMITS, not the size any given stream can
REACH. An offset is `pos - moff`, and a well-formed encoder never emits
`moff > pos`, because those bytes have not been produced yet. A fork whose
entire output is 6 KB can address 6 KB of window; the other 58 KB was
allocated, zeroed on every fork, and never read.

So the window is rounded up to a power of two at or above the fork's
uncompressed size, capped at 64 KB. The power of two is what keeps it exact:
with `win >= outlen`, `pos < outlen <= win`, so `pos & (win-1) == pos` and
`from & (win-1) == from` for every reachable offset — the same indices the
64 KB window computes, not merely equivalent ones.

**The assumption was measured, not argued.** `moff > pos` cannot happen in a
valid archive, but "cannot happen" is exactly the kind of claim this
repository has had to withdraw before, so an instrumented run counted them
across the whole corpus: **0**. That is a different check from the
differential suite passing — the suite would also pass if such references
existed and happened to read zeros either way.

Sensitivity was established the same way as the LZW bound: forcing the window
to its 256-byte minimum takes the suite to **654/769**, so 115 fixtures reach
this code and can fail on it. ASan stayed clean at that size too, which is
worth noting — the masking keeps every access in bounds even when the window
is wrong, so a bad bound here corrupts output rather than memory.

Result: 34 fixtures improved, none regressed, `derived-MacGzip.sit`
76,944 → 13,456 B. The corpus maximum is unchanged at 76,944 B because some
forks genuinely exceed 64 KB — this is a gain at the small end only.

**The estimate that motivated it was wrong, and the way it was wrong is the
lesson.** 175 of 225 StuffIt fixtures sat at exactly the 64 KB-window peak and
about two thirds had their largest fork under 64 KB, so ~115 fixtures looked
like they would improve. 34 did. The flaw: peak heap is the MAXIMUM over an
archive, so one fork over 64 KB anywhere pins the whole archive's peak at the
old figure, however many small forks it also has. **A per-archive maximum
cannot be predicted from a per-fork distribution** — the same class of error
as inferring Arsenic block sizes from peak heap (see the † footnote in
FORMATS.md), arrived at from the opposite direction.
