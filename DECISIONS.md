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
