# TESTING.md — how MacExtract is validated

## Layers

1. **Unit tests** (`tests/unit_main.c` + `tests/unit_formats.c`):
   CRC check values, big-endian readers, per-format probe/decoder tests
   on synthetic buffers. Run by `make test` and every `ci.sh` variant.
2. **Differential tests** (`tools/run_diff.py`): every fixture is
   extracted by the engine and compared byte-for-byte against a
   committed oracle manifest.
3. **Robustness tests** (`tools/run_robustness.py`): truncated and
   bit-flipped fixture variants must produce clean per-entry errors —
   never a crash, hang, or sanitizer trip. Run under
   ASan+UBSan+`-fsanitize=alignment` with `-fno-sanitize-recover=all`,
   so any violation is fatal and caught.
0. **Documentation invariants** (`tools/check_docs.py`): DECISIONS.md's
   Contents index must list every `## ` entry in file order, no
   document may cite another by line number, the version agrees in the
   three places it is written, and every `synthetic:` fixture in
   SOURCES.md regenerates the bytes recorded there. Needs no build, so
   `ci.sh` runs it first; `--fix` regenerates the index. **What it cannot
   see:**
   whether an entry is in the right file, whether a citation points at a
   section that still exists, or whether a paragraph re-narrates one that
   lives elsewhere — that last one is the failure mode these documents
   actually have (CLAUDE.md, *Writing things down*).

## The oracle

The oracle is The Unarchiver's CLI (`unar`/`lsar` 1.10.8, Debian
package `unar`), whose XADMaster engine is also our primary reference.
`macunpack` (macutils 2.0b3) is a **second oracle** for the forks `unar`
cannot read — see "A second oracle" below.

### Resource forks on Linux

`unar --help` documents `-forks (-k) <visible|hidden|skip>`. Both
non-skip modes write an **AppleDouble container** beside the data
fork; they differ in how it is named, and manifests are built from
`-k hidden` (`._<file>`) rather than the default `-k visible`
(`<file>.rsrc`):

- The suffix form is **ambiguous**: an archive holding both `X` and
  `X.rsrc` — every THINK C project — cannot be represented, because
  one entry's sidecar is another entry's name. The prefix namespace is
  disjoint from real archive names.
- The suffix form also triggers a GNUstep bug: `-k visible` builds the
  name by appending an extension, which its path code refuses for a
  leading `~`, and unar then writes the container into the *data*-fork
  filename. Prefixing never calls that code.

Manifest building parses the AppleDouble (magic `0x00051607`; entry
id 2 = raw resource fork, id 9 = Finder info with type/creator) to
recover raw fork bytes and metadata — see
`tools/make_manifests.py::parse_appledouble`. The manifest records
neither convention, only entry names and per-fork hashes; switching
conventions left all 774 pre-existing manifests byte-identical
(DECISIONS.md, 2026-08-08).

**A resource-only entry produces only a `._X` file**, because unar
writes nothing for a 0-byte data fork. That is an empty data fork, not
a lost one — confirmed against `lsar`'s `XADIsResourceFork` and the
container's entry ids, not assumed.

`macextract` writes `<file>.rsrc` by default like unar, and `._<file>`
under `--forks hidden`; the differential harnesses pass that flag so
both sides of the comparison use the unambiguous form.

Which means the harnesses no longer exercise the default convention.
`tests/run_collide.sh` (in `ci.sh`) covers it directly: with default
forks `derived-Unzip101.sit` must fail the one entry whose data fork
lands on another entry's sidecar and keep the fork already written,
with `--forks hidden` it must extract whole, and `--overwrite` must
restore the old write-over-anything behaviour. It was run against the
pre-fix binary and fails there. DECISIONS.md, 2026-08-08.

### Exact oracle invocation

```
lsar -j -nr -e macintosh <fixture>     # format name + metadata (JSON)
unar -nr -D -f -q -k hidden -e macintosh -o <tmpdir> <fixture>
```

- `-nr`: no recursion — each manifest describes exactly one container
  layer (see DECISIONS.md; nesting is tested by chaining layers).
- `-e macintosh`: pin filename decoding to MacRoman rather than
  auto-detection, so manifests are deterministic.
- `-D`: no wrapper directory.

### Manifest format

`fixtures/manifests/<fixture>.json`: fixture sha256/size, lsar format
name, and per entry: name (UTF-8, NFC-normalized), data fork
sha256+size, resource fork sha256+size, type/creator when the oracle
exposes them, and `oracle_methods` — the compression method(s) `lsar`
names for that entry (`XADCompressionName`; two forks can differ, so it
is a list). Nothing in the engine reads it; it exists so a harness can
ask what an entry is compressed with without asking the engine.

Plus, for an archive that carries one, `comment`: the archive's own
comment as the oracle reports it (`lsarProperties.XADComment`). The key
is absent when there is none, so a manifest without it says "no
comment" and never "not looked for". `tools/run_diff.py` requires the
comment file the CLI writes (`<fixture>.comment.txt`) to hold exactly
those bytes in MacRoman and `macextract l` to print the line; an archive
with no `comment` key may write no such file, which the suite's
"unexpected output" check already enforces — and that half is not
decoration: it is what found five of the seven. **Seven fixtures in the
corpus carry a comment**, measured by sweeping all 928 with `lsar`: six
Compact Pro archives (`derived-DigSim_RAM_Circuit.cpt`, *"Hi there."*,
written in 1990, and the five Compact Pro Package installers), and
`derived-MUSFMT10.ZIP`, whose 495-byte end-of-central-directory comment
has been saved since 2026-08-26. All seven are graded; no format is
excused.

### When the oracle fails on an entry

`unar` sometimes fails on individual entries while walking the rest of
the container fine. Until 2026-08-08 that discarded the whole manifest,
which cost oracle coverage of every *other* entry in those archives —
including the corpus's only StuffIt method 1 fork, which unar decodes
correctly (DECISIONS.md).

`make_manifests.py` now records what the oracle produced and marks the
forks it failed on, per entry:

```json
"unadjudicated": { "data": "Attempted to read more data than was available" }
```

with that fork's size and hash **omitted**. The classification is by
condition, never by fixture name: exit non-zero, plus a per-entry
failure report that accounts for itself. Two cross-checks must pass
before the output is treated as ground truth at all — the parsed
failure count must equal the total unar prints, and every name it
reports must be an entry `lsar` independently lists. Otherwise the
manifest is refused, exactly as before.

`run_diff.py` skips those forks, requires the entry to exist anyway,
and prints the running total on every run. It also fails on a manifest
where a hash and a reason sit beside each other, or where neither does.

### A second oracle

`unar` failing on a fork is a fact about `unar`. Since 2026-08-08 every fork
it leaves unadjudicated is offered to **macutils' `macunpack`**, and the ones
it decodes are recorded with per-fork provenance:

```json
"data_oracle": "macunpack (macutils 2.0b3, -m32)"
```

Build it with `sh tools/build_macunpack.sh`, which copies the read-only
`reference/macutils` tree to `build/macunpack/` and patches the copy (two
C99/makefile fixes, neither changing behaviour). `make_manifests.py` uses it
if it is there and silently does without if it is not, so a machine with no
32-bit toolchain still builds every manifest — those forks just stay
unadjudicated. `./ci.sh` runs `make clean`, which takes `build/` and the
oracle with it; re-running the script rebuilds it and is a no-op when the
binary is already there.

**`-m32` is load-bearing, not a preference.** `util.c`'s `get4()` returns
`unsigned long` and `sit.c` assigns it to a `long`, so the sign test that
selects a *stored* method-6 segment is only reachable while `long` is 32 bits.
Built LP64, `macunpack` reads a stored segment as an enormous Huffman segment
and dies with "Premature EOF" — the oracle silently loses the one branch
`tools/synth_sit6.py` exists to adjudicate. Measured 2026-08-08.

Matching an entry to the files `macunpack` wrote is a prediction, and the
manifest builder refuses rather than guesses: names go through the
`transname.c` table parsed out of the reference (plus the leading-dot rule,
because the build passes `-DNODOT`), a name two entries share is refused
because there is then no telling whose output a file is, and a missing
`.data` counts as an empty fork **only** when the `.info` file `macunpack`
writes for every entry is present. Without that witness a mispredicted name
looks exactly like an entry with two empty forks, and would be written into
the manifest as ground truth saying so.

Result, 2026-08-08: 23 forks across 9 fixtures gained ground truth, the suite
went 793 → 795 fixtures, and the unadjudicated tally went 19 forks/14 fixtures
→ 8/7. Later the same day the suite reached 797 and the tally 12/9, for a
different reason — the two fixtures that were being skipped whole started
being graded, and a skipped fixture's unadjudicated forks had been counted
nowhere. See "When our engine declines an entry", below.

### A third oracle, for one method (`tools/build_deark.sh`)

Since 2026-08-25 the forks `unar` AND `macunpack` leave open are offered to
**deark**, recorded the same way (`"data_oracle": "deark (Deark version:
…)"`). It exists for one method and one reason: `unar` decodes ARC/PAK
method 0x0b (Distilled) **wrong** — right length, wrong bytes, on 6 of the
10 members of `derived-INTRECHO.pak` — because XADMaster starts the 8 KB
window at zero where PAK fills it with spaces (BLOCKERS.md). Those entries
arrive as checksum failures, which is correct of `unar` and useless as
ground truth; deark implements the method independently and agrees with the
CRC PAK stored. `sh tools/build_deark.sh` copies `reference/deark` to
`build/deark/` and builds it; nothing is patched and it needs only a C
compiler.

It is a **data-fork oracle only** — deark has no notion of a resource fork
for these formats — and it is matched to entries by position AND name, with
a name two entries share refused outright, the same rule the `macunpack`
path uses.

**What this cannot see:** `macunpack` is where our method-6 decoder was
transcribed from (`src/fmt_sit.c`, `src/sit6_tables.h`), so on method 6 it
adjudicates a transcription against its source rather than two independent
implementations — a transcription error shows up, a misreading of the format
shared with the reference does not. (The same caveat applies to `unar`, which
is the primary reference for everything else.) It also reads none of Zip,
Gzip, tar or DiskDoubler, and it fails whole-archive far more often than
`unar` does, which is why it is the second oracle and not the first.

**What this layer cannot see:**

- **An unadjudicated fork is checked only by the archive's own CRC-16**,
  written by the same compressor that wrote the fork. That is a strong
  check but it is not byte-exactness against a second implementation, and
  a decoder bug that reproduced the CRC would pass. The `derived-New_Python.sit`
  fork unar failed on is what that argument was made about — it decodes to
  23,987 bytes whose CRC matches — and the second oracle has since agreed on
  all 23,987 of them, so on that one fork the argument no longer has to be
  taken on trust.
- **An entry the oracle names as out of v1 scope is graded on its name and
  on anything the engine did write — not on its forks**, because the engine
  produces none (7 entries, all Implode, in the two PKZIP 1.x zips). The
  day Implode is implemented those 10 forks start being compared with no
  change to the harness. Until 2026-08-08 the whole FIXTURE was skipped
  instead, on the strength of our own error message; see "When our engine
  declines an entry".
- Do not read "unadjudicated: 23 forks" as 23 defects. It is 23 forks
  across 11 fixtures where two implementations cannot be compared: 8 in
  damaged nested archives where the engine says "file is truncated" and
  unar says "Error on decrunching", 4 in the two PKZIP 1.x zips, where
  unar failed the entry and Implode is outside v1 scope for us — **both
  sides decline on every one of those 12** — and 11 in two DiskDoubler
  fixtures, which are the exception worth knowing about: **we extract
  those and nobody grades them** (both oracles fail; see the DiskDoubler
  section below). (The count was 8 across 7 until those two zips
  stopped being skipped whole, which is the point: a skipped fixture's
  unadjudicated forks were not counted anywhere.)

### When our engine declines an entry

A per-entry error from `macextract` is tolerated in exactly two cases, and
**both are the oracle's word, never ours**:

- the oracle failed that same entry (it is `unadjudicated`), or
- the oracle names the entry's compression method as one v1 does not
  implement — `oracle_methods` against `run_diff.py`'s
  `ORACLE_OUT_OF_SCOPE`, which today holds `Implode` and nothing else.

Which of OUR errors is eligible for that excuse is `said_unsupported()`,
and it matches the END of the message rather than the whole of it: the
per-entry line names the method when the format states one ("method 6 is
not supported yet"), and a matcher spelled out in full broke the day that
wording improved. **The excuse is still the oracle's**; this only decides
eligibility.

Anything else fails the fixture, including a non-zero exit with no
per-entry report at all, and including every whole-archive error (those
name the FIXTURE path, which can never match an entry name).

**Why it is anchored outside our own output.** Until 2026-08-08 a fixture
was skipped whole when every entry our binary reported failed as
unsupported. Two consequences, both measured on
2026-08-08:

- it discarded ground truth. `4acalc.zip` and `4alnch11.zip` carry
  adjudicated hashes for 5 of their 7 entries — `unar` implements Implode
  and we do not — and none of the 10 forks, nor the names, nor the entry
  counts were compared. **"even unar fails on them" was true at M8 and
  false since per-entry manifests landed**, and the disproof was sitting
  in the manifests themselves.
- it could not fail. A regression that made a *supported* method report
  itself unsupported for a whole archive converted a failure
  into a skip, and the mitigation on record was a printed count for a
  human to notice. Demonstrated with a stub binary: `derived-Export.sit`,
  fully adjudicated, passed as a skip. It fails now.

The same pass tightened a second excuse. An entry the oracle partly
failed used to have its whole absence excused, so a fork WITH ground
truth beside an unadjudicated one was never required to exist: a stub
that wrote nothing for `•Draw 5.1.cpt` passed while the manifest held a
78,123-byte adjudicated data fork. Absence is now excused only for
out-of-scope entries; an adjudicated fork is compared or missing. Six
fixtures sit on that path and all six were byte-exact already, so the
tightening changed no result — it changed what a result means.

### Comparison normalization

The engine emits raw MacRoman filename bytes; the CLI converts to
UTF-8 (table in `cli/main.c`). `run_diff.py` NFC-normalizes both the
manifest names and the engine's output paths before comparing, and
compares forks by SHA-256. Type/creator are compared through
`macextract l` output. Dates are recorded loosely but not compared (v1;
see DECISIONS.md).

## Corpus

`fixtures/` is gitignored (copyrighted historical software); committed
are only `fixtures/SOURCES.md` (name, sha256, size, URL per fixture)
and `fixtures/manifests/`. `tools/harvest.py --restore` re-downloads
the corpus; `--probe URL` adds a candidate, accepting it only if lsar
can read it.

**Synthetic fixtures are restored by running their generator**, not
downloaded: `synthetic:<script>` in SOURCES.md, which harvest.py calls
with `-o <path>`. Two of those lines could not be restored at all until
2026-08-15 — their generators took an output DIRECTORY and had no `-o`
— which nothing noticed because `--restore` needs a network for every
other fixture and so never runs in `ci.sh`. `check_docs.py` now
regenerates every synthetic line and compares the sha256, which is the
only part of the restore path that can be checked offline.

## Running everything

```
./ci.sh          # full matrix; must be green before every commit
```

## M9 additions

4. **Envelope unwrap tests** (`tools/run_unwrap.py`, in CI): chained
   fixtures (.sit.bin, .sit.hqx, .tar.Z) extracted with auto-unwrap
   must match the inner layer's manifest exactly, with the
   intermediate file removed. The single-layer diff harness passes
   `-nr` to disable unwrapping.
5. **Budget sweep** (`tools/run_budget.py`): the whole corpus under
   `--budget 409600` (a small Mac). Everything verifies fully except
   part of StuffIt 5/Arsenic; since the sampled inverse BWT landed
   (2026-08-07) that is **23 of 31** fixtures rather than 11, the rest
   giving a clean per-entry "out of memory". Results in FORMATS.md.
6. **Fuzzing** (`tools/fuzz.py`): seeded, reproducible
   mutation/splice/magic-garbage cases through `macextract t` under the
   sanitizer build; nonzero exits are fine, signals/sanitizer
   aborts/hangs fail. 4,000 cases at M9; every CI run does a 150-case
   smoke.

## DiskDoubler and Now Compress joined the graded set (2026-08-15)

M12 moved both out of `run_diff.py`'s `DETECT_ONLY` and into `IMPLEMENTED`,
which is the whole change on the harness side: 7 fixtures that used to be
graded on "named, and wrote nothing" are now graded entry-for-entry against
`unar`, and the suite went 797 → 804.

**Now Compress is one fixture, and it does not reach most of the code.**
Measured by instrumenting the block loop: three blocks, two of the five
shapes (`0x40` twice, `0x20` once), one file, one fork, no folders, no
padding, no stream restart, no offset delta, no length past a nibble, and a
deepest Huffman code of 12. `test_nowcompress` covers the container on
synthetic bytes, and the proof that it is worth having is a mutation: serve
the two forks in the wrong order and the unit test fails while the fixture
still passes 1/1, because the fixture has no data fork. Everything in that
list of nevers is covered since 2026-08-15 by generated archives — see
"Now Compress: the archives the corpus does not have" below — and a **second
real archive** joined the corpus on 2026-08-16: folders, both forks, two
streams, two stream-restart records, 9.9 MB out of 2.9 MB, and `unar` cannot
decode a byte of it (DECISIONS.md).

**What this could not see until 2026-08-21:** 11 forks across 2 of those
fixtures that neither oracle can decode — `unar` fails and `macunpack` fails,
with its own DiskDoubler support compiled in. Both fixtures are
SELF-EXTRACTING, so `tools/vmac/diskdoubler.py --adjudicate --write-manifest`
runs the archive's own expander under System 7 and writes the verdict into
the manifest: 33 forks compared, all identical, 3 data forks now graded by
`ci.sh` on every run and 8 resource forks still `unadjudicated` because the
Mac's copy of one is never byte-exact (DECISIONS.md 2026-08-21).
`run_diff.py` counts the two kinds separately. Nor does anything here
exercise the
single-file `.dd` container, which no fixture uses — `test_diskdoubler` in
the unit tests covers the containers and the inline-stored path instead,
and found a short header read that the fixtures structurally could not
(DECISIONS.md 2026-08-15).

### Methods 1 and 7 are graded outside `ci.sh` (2026-08-20)

Neither has a corpus fixture, because neither can be fetched by a URL: the
method 1 specimens are written by DiskDoubler 3.7 running under Mini vMac,
and the method 7 ones live two containers deep inside its distribution disk
(a Macintosh Garden zip holding a DiskCopy 4.2 image holding an HFS volume).
`tools/vmac/diskdoubler.py --wild | --make | --verify` produces and grades
both, and `tools/vmac/README.md` says how.

**So `ci.sh` sees these two methods only through `test_dd_stac` and the
method 1 half of `test_diskdoubler`** — unit tests whose streams this project
wrote. They grade the transcription against the reference; they cannot grade
it against the format, and a regression that agreed with our own encoder
would survive them. The specimens are what grade it against the format, and
re-running them is a deliberate, on-demand check like every other emulator
harness here.

### The CC0 corpus, graded against its own originals (`tools/run_ddtf.py`, 2026-08-21)

`ssokolow/diskdoubler-test-files` publishes nine sets of the same seven files
— DiskDoubler 3.7.7 and DiskDoubler Pro 4.1.1, every method their menus offer
— **beside the source files they were made from**. So the grading is against
the bytes that went in, not against another decoder, and there is nothing to
adjudicate:

    tools/run_ddtf.py --fetch          # 564 forks, 0 mismatched (2026-08-21)

63 single-file containers, 9 archives and the same 9 BinHexed, 10
self-extractors and the same 10 BinHexed.

**It is now also in `ci.sh`, by a different route.** `run_ddtf.py --register`
copies the corpus into `fixtures/` — a `SOURCES.md` row per file, with a raw
URL pinned to the corpus commit — and writes a manifest per file built from
the published originals, so `run_diff.py` grades all of it entry by entry on
every run (107 fixtures; DECISIONS.md 2026-08-21 lists what in a manifest
comes from where, and it is never our own output). `run_ddtf.py` itself stays
the way to re-derive that from a fresh clone, which is the only thing that can
notice the corpus changing.

It DOES see a name containing a control character — `Icon` + CR, a custom
folder icon — since 2026-08-24; until then `checkdisk.walk` stripped the CR
and reported the file as missing (DECISIONS.md, *`Icon\r`*).

**What it cannot see**, beyond the docstring's list: it compares forks, so a
regression in dates, type/creator or Finder flags passes it — the corpus's
AppleDouble sidecars carry a Finder info block the Mac rewrote when the files
were copied, so those fields are not oracle-grade here even though the forks
are. It also skips the six `SPLT` parts, which the engine does read: they are
three sets rather than six files, and this harness grades file by file.
`run_segments.py` has the sets, and `fixtures/` has the parts.

**It can fail**: 25 mismatches against the build before the `DDA2` `0x1000`
fix — five archives, ten self-extractors, and the forks under them.

## The forks `unar` refuses (`tools/run_ddforks.py`, on demand)

`unar` 1.10.8 fails on 11 of the 33 DiskDoubler DDn forks in
`derived-LHA_Expander_1.0.3.sea` and `derived-Terrainman_2.0__.sea` with
*Attempted to read more data than was available*. Its DDn reads one byte past
the fork's declared compressed length; the codec behind it is correct
(DECISIONS.md 2026-08-22, and `tools/xadmaster-ddn-repro/` for the 1,166-byte
case).

    tools/run_ddforks.py fixtures/derived-LHA_Expander_1.0.3.sea
    tools/run_ddforks.py --write FIXTURE...     # record it in the manifests

For each fork it builds a one-fork `0xABCD0054` container holding **the
fixture's own compressed bytes, unmodified**, with the declared compressed
length one larger and one pad byte after it, then compares `unar`'s output
with ours. That is what adjudicated the 8 resource forks no off-Mac
implementation could read.

**What it cannot see:**

- **It is not in `ci.sh`** — it needs `unar` on the path and rebuilds every
  fork twice. What `ci.sh` checks is the *result*: the hashes it wrote are in
  the manifests and `run_diff.py` enforces them on every run.
- **It proves nothing about the pad byte's value**, so it does not assume:
  every fork is decoded with 0x00 and with 0xFF and both must agree.
- **It pairs manifest entries to archive headers by the data fork's hash**,
  not by position — the two fixtures order their manifests differently — and
  a header that does not pair uniquely is an error, not a guess.

## DiskDoubler methods 3, 4 and 5 (`tools/vmac/ddencode.py --emit`, in `ci.sh`)

Three `synthetic:` fixtures — `synth-dd-m3.dd`, `synth-dd-m4.dd`,
`synth-dd-m5.dd` — regenerated by `check_docs.py` on every run and graded
against the bytes that went into them. They exist because those three methods
have **no specimen**: nothing in the corpus uses one and no DiskDoubler
release writes one from a menu, so the only file of them this project has, it
wrote (DECISIONS.md, methods 3, 4 and 5).

What makes them worth having in `ci.sh` rather than only in the harness:
registering them puts the three newest codecs in `run_robustness.py` as well,
which is where an untested decoder's real danger lives. A wrong decode
announces itself through the fork's 16-bit sum; a hang or an out-of-bounds
read does not, and 30 corrupted variants per fixture now go through them on
every run under ASan, UBSan and the alignment sanitizer.

**What this suite cannot see**, and it is the important part:

- **It cannot grade the format.** Encoder and decoder are both ours, so a
  shared misreading round-trips perfectly. What grades the format is
  `ddencode.py --expand`, which hands the same encodings to Salient's own
  1991 DiskDoubler under Mini vMac; that is not in `ci.sh` and needs an
  emulator.
- **It only covers encodings our encoder emits.** A real fork may hold
  constructs ours never produces. The known ones have been checked by hand
  and behave: a method 4 stream whose Huffman root is a LEAF (a one-symbol
  fork, zero-bit codes) decodes correctly; a method 3 `ESC 1` emits no repeat,
  which is macutils' reading where `XADRLE90Handle` calls it an error — **the
  two references disagree and this engine follows macutils**; and a fork
  opening with `ESC`, which no compressor can legitimately emit, yields zeros
  from a deterministic `last = 0` rather than macutils' uninitialised read.
- **It says nothing about method 5's tree-count byte above 0** — no fixture
  carries one, and both period expanders reject our construction of it
  (OPEN_ITEMS.md).

## Several BinHex documents in one file (`tools/run_multihqx.py`, in `ci.sh`)

Added 2026-08-15, with the capability it grades. Real corpus `.hqx`
fixtures are concatenated with a posting's worth of text between them —
2 documents and 3 — and each set is graded three ways: against the same
fixtures extracted ONE AT A TIME with `-nr`, against `hexbin`, and on the
two ways it must fail (a truncated last document is a per-entry error
with the earlier documents intact; a banner with nothing usable after it
is reported, not swallowed). Every one of those four assertions was shown
to fail against a single-document build before being believed.

`hexbin` is the third oracle in this project, for the same reason
`macunpack` is the second: **the tool the differential suite uses cannot
do the thing being tested.** `unar` decodes the first document and stops,
exactly as we did, so 179 BinHex fixtures and 3,740 corrupt variants
could never have caught this. macutils has decoded multi-document files
since 1991 (`reference/macutils/hexbin/hexbin.c`, the `again = 1; goto
nexttry` loop).

**What this cannot see:** entry NAMES — it compares the set of fork
hashes, because `hexbin` mangles names on the way out (spaces become
underscores) and pairing on a mangled name would grade our naming against
its transliteration. Names are covered by `test_binhex_multi` in the unit
tests instead, which also carries the whole case on a machine with no
fixtures. It also cannot see the *era's* other multipart shape — one
document cut across several postings, each with its own headers; what
this engine joins is a document cut across files named `.001`, `.002`,
which is the plain-split scheme rather than anything BinHex-specific.

## The sampled inverse BWT (`ci.sh` variant 1b, added 2026-08-07)

The Arsenic decoder picks between a 4-bytes-per-byte transform table and a
sampled occurrence index **by trying to allocate the table and failing**
(DECISIONS.md). Nothing an unconstrained run does reaches the fallback, so
CI forces it three ways:

- `-DUNC_ARS_FORCE_SAMPLED` compiles the fast path out. The whole
  932-fixture diff suite and all 9,320 robustness variants run through the
  fallback under ASan+UBSan, and must be byte-exact.
- `--budget 597036` (what a 1 MB Mac Plus leaves the engine) on the 31
  StuffIt 5 fixtures, with the normal adaptive build. This is the only step
  that exercises *choosing*, and the halving of `target`.
- `-DARS_INDEX_TARGET=1` forces the deep end of the dial, where a query's
  scan spans most of the block. Byte-exactness there is checked on StuffIt 5
  fixtures up to 100 KB (`--max-size`), without sanitizers, because at
  `target=1` the walk is quadratic: 8.4 minutes for the full set against
  ~25 s for the capped subset.

**What these cannot see.** (a) *Time on a 68000.* Every figure above is x86;
the emulator harness runs "all out" and the 1x timing list
(`tools/vmac/timing.txt`) samples StuffIt 5 with a 4,611 B fixture, far too
small to reach the fallback. Both Arsenic fixtures have since been timed at 1x
on both paths (`a2basic` 587 s fast / 966 s sampled, `Library_ISBN` 768 s /
1,898 s — FORMATS.md), but CI cannot produce those figures. (b) *The progress
and Cancel path
under the sampled walk.*
`unc_progress_poll` exists because that walk produces output without reading
input; it is Mac-side and no Linux harness observes it. (c) *The middle of
the dial.* Only `target=1024` (forced) and `target=1` are pinned; the values
in between are reached only incidentally by the budget run.

## The LZW table bound — three builds, because one proves nothing

`unc_lzw_init` sizes its table from the input rather than from `maxbits`
(DECISIONS.md, FORMATS.md footnote §). The safety net that catches an
under-estimated bound never runs in normal operation, so it is only ever
exercised deliberately, by hand:

    # 1. the bound never under-estimates: hard-disable growth
    #    (make lzw_grow return UNC_ERR_MEM as its first statement)
    MACEXTRACT=build/never/macextract sh tests/run_diff.sh      # expect 803/803

    # 2. the safety net is correct: force it to run on every stream
    make BUILD=build/tiny CFLAGS="-O1 -g \
        -fsanitize=address,undefined,alignment -fno-sanitize-recover=all \
        -DUNC_LZW_TINY_TABLE" all
    MACEXTRACT=build/tiny/macextract sh tests/run_diff.sh       # expect 803/803

    # 3. these fixtures CAN fail on this code: starve the table AND
    #    skip the add instead of growing
    MACEXTRACT=build/probe/macextract sh tests/run_diff.sh      # expect ~90 FAILURES

`UNC_LZW_TINY_TABLE` is committed and forces the initial capacity to 258.
Steps 1 and 3 are one-line local edits and are deliberately NOT build flags:
each makes the engine wrong on purpose, and a flag that ships wrong behaviour
is a flag somebody eventually sets. **Step 3 is the point.** Steps 1 and 2 both
report a full pass — the same number a build that ignored the input entirely
would report — so without a demonstrated failure they distinguish nothing.
94 of the fixtures reach the LZW path (4 `.Z`, the rest StuffIt classic
method 2).

Step 2 was re-measured at **778/778** on 2026-08-08, before per-entry
oracle failures, the second oracle and the end of whole-fixture skips took
the suite to 797 later the
same day. Step 3's figure is from
2026-08-03 and was **675/769** — 94 failures — against the 769-fixture suite of
that date; re-running it needs the hand edit above, and what matters is that it
fails at all, not the count. The LZW-path figure is from the same day.


## ARC and uuencode (`tools/run_arc.py`, `tools/run_uu.py`, in `ci.sh`)

Neither format occurs in the corpus — measured 2026-08-15 by innermost
format over all 805 fixtures — so both suites write their own archives
and then get out of the way, because a generator this repository wrote
cannot grade a decoder this repository wrote.

**ARC.** `tools/synth_arc.py` builds one archive per compression method
(1-9) plus one holding all nine, and every one is required to agree three
ways: the bytes that went in, what `unar` extracts, and what our CLI
extracts. `unar` is the load-bearing one. Two encoder/decoder pairs here
shared a misreading and round-tripped perfectly — the crunch codes' bit
order, and the compress table's growth point — and in both cases the
CRC-16 agreed as well, because ARC's checksum covers the DECODED bytes
(DECISIONS.md 2026-08-15). When `tools/get_arc.sh` has fetched Debian's
`arc` 5.21q, three archives written by a real encoder are checked too;
its absence is printed, never silent. Also asserted: a flipped payload
byte is a per-entry CRC error and the entry after it still extracts.

**uuencode.** `tools/synth_uu.py` writes the plain shape (encoded by
CPython's `binascii`, so the encoding side is not ours either) and
UUTool's two-fork shape, which macutils' **`hexbin`** then decodes — the
same arrangement that grades multi-document BinHex, and for the same
reason: it is the implementation `fmt_uu.c` was transcribed from. Also
covered: a mail banner in front, several documents in one file, CR line
endings, and the two ways it must fail (prose containing the word
"begin" is not an archive; a truncated document is an error).

**Multipart postings** are covered in both suites since 2026-08-15:
`run_uu.py` joins two postings (headers and all), runs the same set
through the `.001`/`.002` split scheme so the whole chain is exercised
rather than the decoder alone, and asserts the one thing uuencode cannot
detect — a missing MIDDLE part decodes short and silent.
`run_multihqx.py` does the BinHex half, plus the edge of the rule: a
junk line built only of alphabet characters is indistinguishable from
data, is taken as data, and must come back as a CRC error rather than as
silence. **Both were run against a build with the line rules removed and
both fail there** (DECISIONS.md, "Multipart postings").

**What these cannot see.** Neither suite reads a real ArcMac archive:
`ci.sh` covers the two-fork split with one synthetic stored entry in
`tests/unit_formats.c`, which is a regression guard and no more — the
generator encodes the order the decoder expects, so it cannot be evidence
about the format. The order itself is measured elsewhere, by
`tools/vmac/arcmac.py`, and the archives in the wild are read there too;
neither runs in `ci.sh`. Until 2026-08-16 that unit test also encoded the
fork lengths big-endian, exactly as the decoder read them, so **the suite
agreed with the bug** — the fix was to make the test build the entry the
measured way and check both forks come back.

## ARC's PAK methods (`tools/run_pak.py`, `tools/pak.py`, in `ci.sh`)

Added 2026-08-25 for methods **0x0a (Crushed)** and **0x0b (Distilled)**,
which are PAK's rather than PKARC's and are the one part of ARC no Linux
program writes. So the archives are not generated here at all: they come
from **PAK 2.51 itself (NoGate Consulting, 1990), run headless under
DOSBox**.

    python3 tools/pak.py --setup              # DOSBox + PAK 2.51, needs network
    python3 tools/pak.py --make DIR           # write the corpus
    python3 tools/pak.py --list ARCHIVE       # methods, sizes and CRCs
    python3 tools/run_pak.py --macextract build/rel/macextract

`--setup` needs **no root**: it `apt-get download`s DOSBox and its
dependency closure and unpacks the `.deb`s into `$UNC_PAK_HOME`
(default `~/.cache/macextract/pak/`), then fetches `PAK251.EXE` and lets
it self-extract in the guest. No X server either — `SDL_VIDEODRIVER=dummy`
is enough. `run_pak.py` skips politely when neither the corpus nor a
`.pak` fixture is present, so a fresh clone is unaffected.

**What grades what.** Four graders, because no single one covers the
format:

1. the **CRC-16 PAK stored** per member, over the decoded bytes — the only
   check here that no decoder can influence, and the one that caught the
   oracle;
2. the input bytes, for the seven generated archives;
3. **deark for 0x0b and `unar` for 0x0a**, byte for byte. They are not
   interchangeable: deark does not implement Crushed, and `unar` gets
   Distilled wrong, so consulting the wrong one would fail a correct
   decoder;
4. PAK 2.51 extracting under DOSBox — the writer reading its own archive
   back. Not automated in `ci.sh`; it is what verified the nine members of
   the PAK distribution.

**What the corpus is chosen to reach**, since the two real specimens do
not reach it: `pak-crushed-big.pak` fills the 8,192-symbol table and fires
the replacement scan 49,751 times and the inverted-literal framing 13,009
times; `REPEAT.TXT` exists so that matches reach back into the
space-filled window, which is the case a decoder can get wrong while
looking right. Damage sweeps — truncations and bit flips — run over every
archive under 120 KB, asserting the usual rule: a damaged archive may
refuse, but must not exit outside 0..2 or die by signal.

**What this cannot see.** The generated corpus is one compressor's output
at one setting each, so anything PAK 2.51 never emits is untested — as is
every archive written by PAK 1.x, whose self-extractors interleave
remarks differently. And method 0x0a is decoded as Crushed unconditionally:
an ARC 7.x member, which uses the same number for *Trimmed*, fails its CRC
here rather than extracting (OPEN_ITEMS.md).

## ARC 7.x's Trimmed (`tools/run_arcplus.py`, `tools/arcplus.py`, in `ci.sh`)

Added 2026-08-25, and it exists because **method 0x0a is two methods**: PAK's
Crushed (the suite above) and ARC 7.x's Trimmed, a different algorithm at the
same number.

    python3 tools/arcplus.py --setup            # ARC+Plus 7.12, needs network
    python3 tools/arcplus.py --make DIR
    python3 tools/run_arcplus.py --macextract build/rel/macextract
    python3 tools/run_arcplus.py --register     # the real fixture's manifest

`--setup` needs no third-party tool: the distribution is a DOS
self-extractor, and `--carve` finds the archive inside it structurally — the
offset whose header chain walks cleanly to the end-of-archive marker — then
copies out the nested `ARCDOS.ARC`, which is STORED. Only the last step,
lifting `ARC.EXE` out of that, uses a decoder, and it uses ours. **That is a
bootstrap, not a grading**: what grades the decoder is listed below, and none
of it is ours.

**What grades what.** The CRC-16 ARC+Plus stored; the input bytes, for the
three generated archives; **deark**; and one file with no decoder in it at
all — `XARC.EXE` is Trimmed inside the distribution and uncompressed in
another CD's `XARC.ZIP`, and the two are byte-identical. `unar` is not
consulted and cannot be: it does not recognise an ARC 7 archive at all
(BLOCKERS.md), which is also why `fixtures/manifests/derived-ARCDOS.arc.json`
is REGISTERED by this tool rather than built by `make_manifests.py` — the
same arrangement DiskDoubler has, and `make_manifests.py` refuses to
overwrite a manifest whose oracle is not `unar`.

**The discriminator has its own test**, and it is the one that matters most
here: `arc7-text.arc` and `pak-crushed-text.pak` hold the same input files
under the same method number, written by the two different programs. If
`arc_dialect()` regresses, exactly one of them stops extracting. Both
directions were checked by breaking it on purpose — forcing Crushed fails the
ARC 7 side, forcing Trimmed fails the PAK side.

**What this cannot see.** ARC 7 has no switch to force Trimmed, so what the
corpus covers is what its inputs persuade the compressor to do; and ARC 6.x,
which also writes informational items but never Trimmed, has no specimen here
at all. The dialect rule treats an archive with items and no PAK trailer as
Trimmed, so a hypothetical ARC 6 archive using method 0x0a would be read
wrongly — it would fail its CRC rather than pass quietly.

## btoa (`tools/run_btoa.py`, in `ci.sh`)

Added 2026-08-23. The corpus has no btoa file — `xbtoa` appears in none
of the 903 — and no second READER exists: `unar` does not recognise the
format and macutils never had it. What does exist is the original
implementation, so the suite uses it as the ENCODER: it compiles
`reference/btoa` (5.2.1, fetched by `tools/fetch_references.sh`) and
requires our decoder to reproduce, byte for byte, what that encoder
writes.

Eight subjects, each chosen for what it makes the encoder do rather
than for size: a run of zeros and a run of spaces (the `z` and `y`
escapes, and `y` exists only in version 5), four lengths around a
multiple of four (101, 102, 103, 104 — the last group is padded and
only `(len-1)&3 + 1` of its bytes are real), every byte value, and a
one-byte file. All eight in **both framings**, because `xbtoa5`
checksums the encoded characters and `xbtoa Begin` checksums the
decoded bytes, and a decoder with those the wrong way round passes one
and fails the other.

Also asserted: version 5's header names the file and that name is the
entry's, version 4 has none and the host's hint is used instead; a
mail header in front is stepped over; a flipped character and a
truncated archive are errors; and prose containing the word `xbtoa` is
not claimed as an archive.

And the **line endings**, in both framings, because the encoder is a
Unix program and writes only LF: the same stream re-terminated with CR
and with CRLF has to decode identically. CR alone did not, until
2026-08-23 (*BLOCKERS.md*, withdrawn claims) — 25 cases now, and the
four new ones fail against the code they were written for.

Since 2026-08-26 it also asserts the End line's `R` field in the width
a **32-bit** machine writes it: the reference computes that checksum in
a `long` and prints sixteen hex digits on this host where the Macintosh
writes eight (FORMATS.md, *btoa*). Four cases, two framings; the narrow
form must decode and a wrong narrow form must not.

**What it cannot see.** The suite skips, loudly, without
`reference/btoa` — so a fresh clone runs the two hand-built streams in
`tests/unit_formats.c` and nothing else. And every stream IN `ci.sh`
still comes out of ONE encoder: re-terminating the lines and narrowing
`R` vary properties that encoder was hiding, but not the ones nobody has
thought of. The independent specimen exists as of 2026-08-26 —
`tools/vmac/sitcrypt.py --btoa-send` has Aladdin's own `btoa/atob
Translator` write one, and it decodes byte-exact (FORMATS.md, *btoa*) —
but it is a specimen made on demand under an emulator, not a fixture, so
nothing in `ci.sh` replays it.

## base64 and MIME (`tools/run_mime.py`, in `ci.sh`)

Added 2026-08-26. The corpus has neither: no `.mim`, no `.b64` and no
saved mail message — the sniff sweep claims none of the 940 fixture
files. So every case is generated, and a generated case graded by its
own generator proves nothing (*ARC and uuencode*, DECISIONS.md). Two
other implementations grade instead:

- **munpack 1.6** (CMU), which `src/fmt_mime.c` is transcribed from,
  built out of `reference/mpack` by `tools/build_mpack.sh`. It reads
  the same message and has to produce the same bytes.
- **deark**, an independent base64 implementation, built by
  `tools/build_deark.sh` — already the third oracle for ARC 0x0b.

48 cases. The base64 half: four lengths around a group boundary (the
last group padded with none, one or two `=`), every byte value, a
one-byte file, two documents in one file, and the same document with
CR, LF and CRLF line endings. The MIME half: a single base64
attachment, a multipart with a note and two attachments, a
quoted-printable part, an unencoded part, a part with no filename at
all (`part1`, which is what munpack calls it), an LF-only message —
and **multipart/appledouble**, both forks, the type and creator, the
resource-only case with no data part, and one nested inside a
`multipart/mixed`.

**The three places the oracle is wrong**, each with a reproduction in
DECISIONS.md 2026-08-26: munpack never uses a `Content-Disposition`
filename, cannot read the CRLF form a mailer writes, and drops a
decoded `=0D`. So the comparison gives each implementation the input it
was written for (munpack gets the LF form), compares BYTES rather than
names, and the `=0D` case is asserted against a subject munpack is not
asked to grade. Averaging those away would have hidden all three.

**What it cannot see.** Neither grader knows what a resource fork is:
the Unix munpack writes an `application/applefile` part out whole and
deark has no notion of one, so **nothing here adjudicates the fork
JOIN except this project's own AppleDouble decoder** — which 932 corpus
fixtures grade against `unar`, and which the suite feeds the same
applefile part on its own to say so out loud. And base64 carries no
length and no checksum anywhere, so a truncated message decodes short
and silently; the suite asserts that outcome, so the day the format
turns out to have a check, it says so. It skips, loudly, without
`reference/mpack`.

## LZH / LHA (`tools/run_lzh.py`, in `ci.sh`)

Added 2026-08-23, when LZH came into scope. The corpus contains exactly
one `.lzh` and it is Amiga software; what grades the format is somebody
else's test corpus, `reference/lhasa/test/archives` — **182 archives
written by fourteen different LHA implementations**, MacLHA 2.24 among
them (fetched by `tools/fetch_references.sh`; seven are fixtures too,
with oracle manifests, so the differential suite holds the names, sizes
and Mac type/creator codes).

**Three graders, deliberately not interchangeable.**

| grader | what it is | what it can catch |
|---|---|---|
| `unar` | XADMaster, which `src/fmt_lzh.c` is transcribed FROM | a transcription error, and nothing else — agreement here says the copy was faithful, not that the reading is right |
| `lhasa` | an independent implementation, compiled out of `reference/lhasa` | a wrong reading that XADMaster shares |
| LHa for UNIX 1.14i | the ORIGINAL program, compiled out of `reference/lha` and used as an **encoder** | a decoder that agrees with both readers and still cannot read what the format's own writer emits |

The run reports how many archives each grader adjudicated (137 and 142
of 182 at the time of writing) plus 12 generated sets — four methods
(`-lh0-`, `-lh5-`, `-lh6-`, `-lh7-`) at three header levels, over five
subjects chosen for what they make the encoder do: long runs, text,
incompressible bytes, one byte and none.

**What it cannot see**, all four named in the file itself:

- The archives in its `SKIP` set — PMarc, `-lhx-`, LHArk's private
  `-lh7-`, the self-extracting ones — are checked to be REFUSED and
  nothing more. A change that made one of them extract is reported, not
  caught.
- `-lh2-` and `-lh3-`: nothing here has an archive that uses either
  (OPEN_ITEMS.md).
- **The resource fork of a MacLHA entry, unless this machine has made
  one.** lhasa strips the MacBinary header and throws the resource fork
  away, so on those archives it grades the data fork only — and all
  sixteen MacLHA archives in lhasa's collection hold data-fork-only
  files. What closes it is a specimen made here:
  `tools/vmac/maclha.py --make` runs **MacLHA 2.00** under Mini vMac and
  archives a file with a real resource fork, and this suite grades both
  forks of it against the bytes that went in. It lives beside the
  emulator, so a fresh clone skips that check and says so; the branch is
  also covered off-Mac by a hand-built MacBinary payload in
  `tests/unit_formats.c`.
- Dates: the engine converts neither MS-DOS nor Unix timestamps
  (FORMATS.md), so there is nothing to compare.

Three archives are also excused by name, each with the measurement
behind it: `unar` mis-reads one OS-9/68k level 2 archive (it stops after
the first directory), and lhasa reads two level 0 archives as empty
because both begin with a `-lhd-` entry whose name is zero bytes long.
Excusing a grader on a named file is not the same as excusing a format,
and the file says which is which.

## Large zips (`tools/run_ziplarge.py`, in `ci.sh`)

Added 2026-08-25. A zip counts its entries in 16 bits; past 65,535 the count
lives in a Zip64 record. A reader that trusts the 16-bit field does not fail
on such an archive — it walks 65,535 entries and reports success, which is how
a 70,000-entry zip lost 4,465 files silently until that date (FORMATS.md,
*Size limits*).

The corpus cannot reach this: **the largest zip in 932 fixtures has 29
entries**, and robustness variants perturb a fixture rather than grow one. So
the subjects are generated, and graded by three things that are not our
output — CPython's `zipfile`, which wrote them and whose `namelist()` is the
intended count; `lsar`, an independent reader over the same file, skipped if
absent; and the boundary itself, since 65,535 (no Zip64 record) and 65,536
(one) are both built and a reader that ignores Zip64 passes the first and
fails the second.

Two failure paths are asserted as well, both reached by editing a generated
archive: a locator whose record sits past 4 GB must be REFUSED rather than
truncated to something addressable, and a locator pointing at bytes that are
not a Zip64 record must fall back to the 16-bit count rather than failing the
archive — XADMaster's behaviour, which `fmt_exo.c` follows.

**Established that it can fail**: against the previous commit's `fmt_exo.c`,
two of the five cases fail (the 65,536 count and the past-4-GB refusal).

**What it cannot see.** Every subject here is a few megabytes with a large
entry COUNT. Nothing in `ci.sh` opens an archive that is actually larger than
4 GB, or an entry that is — those limits were measured by hand and live in
FORMATS.md, *Size limits*, not in any suite.

## Decryption (`tools/run_crypt.py`, in `ci.sh`)

Added 2026-08-23, when decryption came into scope. **Nothing in the
corpus is encrypted** — `lsar -j` over all 903 fixtures reports
`XADIsEncrypted` 0 for every entry — so this suite writes every archive
it grades, and the whole design is about not grading a decoder against a
generator that shares its reading.

Two of the seven ciphers need no generator here: **`zip -P`** writes the
PKWARE-cipher fixtures (stored and deflated) and **`arc g<password>`**
the garbled ARC ones, so those owe nothing to this project. The other
four — StuffIt classic's StuffItDES, StuffIt 5's RC4, and PackIt's XOR
and DES — have no encoder on this machine, so `tools/synth_crypt.py`
writes them and **`unar -p` adjudicates**: a different implementation of
each cipher, extracting the same file with the same password, byte for
byte. For StuffIt classic the fixture is MacBinary, because the password
verifier is the archive's `'MKey'` resource and the oracle needs the
resource fork too; our CLI is given the bare `.sit` and finds the same
resource in the sidecar file it writes itself.

**StuffIt classic is graded by StuffIt Deluxe 3.5.1** when the emulator
has been run: `tools/vmac/sitcrypt.py` has the application encrypt a
known file under a chosen password and keeps the archive — as
MacBinary, because the password verifier is in the archive's resource
fork. Three are kept, with passwords of 8, 9 and 17 characters, and
those lengths are not decoration: they are what showed that the fold
count is ceil(len/8) and that neither reference implements it.

**The ciphers run on a big-endian 68000 too.** `tests/run_mac_sink.sh`
cross-compiles the unit tests with `m68k-linux-gnu-gcc -mcpu=68000` and
runs them under `qemu-m68k`, so every cipher vector — DES, StuffItDES,
MD5, RC4, the zip and Compact Pro keystreams, SHA-1, HMAC-SHA1, PBKDF2
and AES — is checked where the word order is the target's. Nothing else
does: no fixture in the Mac sample is encrypted, and the differential
suite is little-endian x86.

**WinZip's AES has no second reader here**, so its four cases are
graded the other way round: **7-Zip** writes them (256, 192, 128, and
one stored), verifies them itself, and our output must equal the bytes
that went in — `unar` 1.10.8 cannot open one at any key length. Each
case also has a ciphertext byte flipped, because an AE-2 entry stores
no CRC and the ten-byte authentication code is the only thing that can
catch it.

Also asserted, because they are what a user meets:

- a **wrong** password is reported per entry and produces no output —
  checked with `t`, which decodes and discards, so a pass there would
  mean a CRC agreed with rubbish;
- **no** password leaves the archive walkable: PackIt's two clear
  entries either side of the encrypted ones still come out;
- an encrypted StuffIt classic archive **without** its resource fork
  reports "encrypted", not "wrong password" — there is no key to try;
- ARC opens under both the password as typed and the password
  upper-cased, because `arc` 5.21q keys on the capitals.

**What this cannot see.** Three things, and the first is the one to
remember:

- **StuffIt 5's suite cases are still generated files**, adjudicated by
  `unar` — which is one reading, not two. What settles the cipher is
  kept outside the suite: three archives **DropStuff 5.0.1 wrote** on
  Mac OS 9.2 (FORMATS.md, *StuffIt 5's RC4*), at passwords of 4, 9 and
  17 characters with one of them two-forked. They are not committed and
  not regenerated automatically; re-make them with
  `tools/vmac/os9mouse.py` (`tools/vmac/README.md`, *Mac OS 9 with the
  pointer*) and check them by hand:

      macextract x -p swordfish -o /tmp/out ~/.cache/macextract/sit5/specimens/enc-swordfish.sit
- **Compact Pro is graded by Compact Pro**, when the emulator has been
  run: `tools/vmac/cptcrypt.py --make --probe` has the application
  itself encrypt three known subjects and keeps the archive beside the
  emulator's other state, and this suite extracts it and compares. On a
  fresh clone there is no such archive and the case skips, loudly. A
  round trip through our own cipher is deliberately NOT substituted for
  it: it would grade nothing.
- The **`arc` cases skip** when `build/arc/` is empty, which is what
  `ci.sh` leaves behind after `make clean`; run `tools/get_arc.sh`
  first to include them. The skip is printed, never silent.

## Now Compress: the archives the corpus does not have (`tools/run_now.py`, in `ci.sh`)

Added 2026-08-15. The corpus's one real fixture reaches two block shapes; the other
three, the offset-delta search, folders, data forks, several files in one
archive and a Huffman code deeper than a nibble had no archive at all. So
`tools/synth_now.py` writes them and `unar` grades them, three ways — the
bytes that went in, what the oracle extracts, what our CLI extracts —
exactly as the ARC and uuencode suites do, and for the same reason.

Thirteen archives: one per block shape (each holding prose, run-length
content and incompressible noise), one stream cycling all five shapes with a
non-zero `padding` between two blocks, a folder tree with a nested folder, an
empty folder, a two-fork file, a resource-only file, a code 17 bits deep, two
whose table offsets are wrong by a constant — one obviously (the reference
does not even try zero), one plausibly (its checksum has to fail first) — and
one where a stream's first block reaches back into the dictionary cache the
previous stream left behind. Type and creator are checked separately, since
comparing forks cannot see them: ours from `l -v`, the oracle's from the
Finder info in its AppleDouble sidecar.

**One of the thirteen is also committed as a fixture.**
`synth-now-mixed.now` — the stream cycling all five shapes — has an `unar`
manifest in `fixtures/manifests/`, so the differential suite grades those
paths byte-for-byte on every run, including on a machine with no `unar` at
all, and any future Mac replay can pick it up. It is restored from
`tools/synth_now.py -o`, like every other synthetic fixture (see *Corpus*).

**A fourteenth archive is graded ONE way**, because the two implementations
genuinely disagree on it and the reference is wrong: a zero-length file
anywhere but last leaves `unar` decoding the files after it from a stale
block, so it fails one entry and writes the NEXT one at the right length
with the wrong bytes. Both halves are asserted — our extraction must be
byte-exact and the oracle must still fail — so a later `unar` that fixes it
reports itself rather than quietly agreeing (DECISIONS.md, "Now Compress: an
empty file in the middle").

**Two mutations are built in**, because a comparison nothing has been shown
to fail is not evidence: a flipped byte inside a stored block must change the
output (nothing in this format checksums a block, so it must come out as
wrong bytes rather than as an error), and a flipped byte inside a block table
must be refused by both implementations, since the table is checksummed.
Twelve mutations of `fmt_now.c` were also run against the whole suite and all
twelve fail it (DECISIONS.md, "Now Compress: writing the archives the corpus
never had") — including one that did NOT fail until the archive that tests it
was rebuilt, which is written up there.

**The corpus's second real archive is checked here too**, because the
differential suite cannot: `derived-SyntheticReferences2.0.sea` (1995) defeats
`unar` on every fork, so its manifest carries names, type and creator and
marks the forks unadjudicated. `run_now.py` extracts it and asserts one thing
that can fail on its own terms — **the resource fork we produce must be a
resource fork**, its own first 16 bytes accounting for exactly its length —
plus per-fork hashes. Mutating the decoder's fork order fails both. The
fixture is skipped with a message when it has not been fetched.

**Those hashes are not merely our own output any more.** The archive is
self-extracting, so the decoder Now Software shipped with it is in its
resource fork: `tools/vmac/nowcompress.py --adjudicate` runs it under the
emulator and compares fork by fork, and it agrees with us on all four —
9,949,696 bytes byte for byte, and the resource fork identical once bytes
16..127 are masked, which is the convention `vmac_check.py` has used since
M10 because the Resource Manager stamps that region (DECISIONS.md, "The
archive that carries its own oracle").

**Archives from the ENCODER are checked too, when they exist.**
`tools/vmac/nowcompress.py` drives Now QuickFiler 5.0.1 under Mini vMac and
leaves its specimens beside the emulator; `run_now.py` decodes each one and
requires the bytes that went in to come back. They are not fixtures — the
application is commercial and is not redistributed — so the check reports
itself as skipped when the specimens are absent, which is what CI sees.
Seven specimens cover stored, LZSS-only, Huffman-then-LZSS and new LZSS
(FORMATS.md ✧).

**What this cannot see.** XADMaster is the only implementation of Now
Compress there is, and `fmt_now.c` was transcribed from it — so where a shape
has no specimen from the encoder, agreement proves the transcription and not
the format. Since 2026-08-16 that is no shape at all, but it becomes true
again for anything the four cases do not reach. The generator also has to stay
inside what the oracle can read: its bit reader refuses a stream that ends
within 7 bits of its buffer, which ours reads perfectly well, so every
generated stream leaves a whole spare byte.

And these archives have run on Linux and under qemu-m68k (big-endian,
32-bit) — not on a Mac. The Mac tiers replay `tools/vmac/sample.txt`, whose
Now Compress entry is the real fixture, so the four shapes only these
archives reach have never been decoded on a 68000 with a real File Manager
under it. `synth-now-mixed.now` is a fixture with a manifest, so adding the
line is all it would take; the sample's counts in FORMATS.md would then need
re-measuring, which is why it is not there already.

## LZH's -lh2- (`tools/run_lzh.py`, in `ci.sh`)

Added 2026-08-25. `-lh2-` is one of the two LZH methods this project could
not grade: no corpus archive uses it, `lhasa` has no decoder for it, and the
LHa in `reference/` carries the coder without ever selecting it. The
maintained fork DOES decode it and — like everything else — cannot write one.

So the encoder was added. `sh tools/build_lha_lh2.sh` fetches that fork's
source at a pinned commit into `reference/`, where it stays exactly as
downloaded; `run_lzh.py` builds it on demand with
`tools/lha-lh2/lh2-encoder.patch` applied — the mirror of its own
`decode_p_dyn`, plus the schedule the position tree grows on. The split
matters: the first arrangement kept the built encoder in `build/` alone,
where `ci.sh`'s `make clean` deleted it, and the whole `-lh2-` grading went
quiet without failing. **The data is then the reference implementation's, not ours**, and each
archive is verified by that program's own decoder before this engine is
handed one.

Nine subjects at three header levels, **15 `-lh2-` entries** per run. Two
things keep it from passing vacuously:

- **The method of every entry is read out of the headers**, and fewer than
  three `-lh2-` entries in an archive fails the run. LHa falls back to
  `-lh0-` for anything it cannot shrink, so comparing bytes alone would have
  graded nothing and said so cheerfully.
- **The encoder's own decoder runs first.** If it refuses an archive, the
  archive is at fault rather than this engine — worth separating when the
  encoder is a patch this project wrote.

Demonstrated failing: inverting the tree walk's bit sense gives
`-lh2- level 2: text.txt missing` and `zeros.bin differs`.

**What it cannot see.** The window preload (spaces) is unobservable: zeroing
it changes no result, because LHa's encoder never emits a match reaching
back past the start of the output. And the patch is deliberately
conservative — a match whose position symbol has no node yet goes out as
literals — so a real 1990 encoder may have used offsets at a boundary these
specimens never reach.

### `-lh3-`, which needed no patch at all

`-lh3-` is a STATIC code rebuilt per block, so teaching LHa to write it
would mean building and transmitting a table rather than mirroring a tree.
The encoder is in `run_lzh.py` instead — a small one whose only job is to
produce streams **LHa accepts** — and the guard is that LHa extracts every
archive before this engine is handed it. Six entries per run, including the
two escapes a real compressor would rarely emit and a decoder must still
read: the "this block is one symbol" form (three code lengths of 1, then
the symbol) and an explicitly sent position tree where the format otherwise
supplies a fixed one.

Breaking the block's symbol count by one fails it: `one.bin missing`,
`single.bin differs`, `ptree.txt differs`.

**And the guard earned itself immediately.** The first encoder wrote a
single-symbol file as a tree with one code of length 1, and a position tree
of 128 eight-bit codes. Both are INCOMPLETE tables; LHa refuses them
("Bad table (case b)") and **this engine decoded them without complaint** —
its canonical builder accepts an incomplete code where LHa will not. So the
suite feeds it only complete ones, and that difference is written here
rather than discovered later: a corrupt `-lh3-` table is a per-entry error
in LHa and garbage output here.

## Alysis SuperDisk! (`tools/run_superdisk.py`, in `ci.sh`)

Added 2026-08-20. The corpus holds two SuperDisk! archives and no oracle
outside them: `unar` and `macunpack` both stop at the BinHex envelope, so
their manifests in `fixtures/manifests/` describe the payload file and say
nothing about its contents. Both archives are self-extracting, so the grading
was done by the archives themselves — `tools/vmac/superdisk.py --adjudicate`,
under System 7 on an emulated Mac Plus, 5 forks, all identical. This suite
replays that verdict offline: per-fork size and SHA-256, the sniff, and the
file count from `l`.

**It runs on the PAYLOAD, not on the fixture.** `l` never recurses through an
envelope — only `x` does — so the suite unwraps with `x -nr` first. That is
also why the corpus-driven suites never reach this parser at all: to
`run_robustness.sh` and `fuzz.py` these two fixtures are BinHex files, and all
9,320 of the suite's variants exercise the BinHex layer.

**116 corrupted variants** — ten truncations and forty-eight bit-flips per
archive — therefore live here. They are FORCED with `-f "SuperDisk!"`: a
truncated archive loses the trailing `0x27` record the probe insists on, so it
sniffs as *unknown* and a run that trusted the sniff would exit clean having
parsed nothing.

**A budget run per archive checks the per-entry contract.** Every fork in
`alysis-disk-expander-12` is method 11, whose 96 KB window is the whole
allocation, so `--budget 50000` refuses all of them — and what is asserted is
that the run still NAMES every entry. Allocation failure is per-entry, never
per-archive (CLAUDE.md, 68000 discipline), and the only symptom of getting
that wrong is entries that are silently never reached.

**What this cannot see.** The hashes were produced by this reader before they
were confirmed on the emulator, so they are a regression fence and not an
oracle; re-confirming them means re-running `--adjudicate`. It also grades
two methods, 7 and 11, because that is what the two archives use. The unit
test carries what no fixture can: a two-fork file, so that fork order is asserted, and an
undecodable method BETWEEN two decodable entries. **Every other method is
graded by the suite below**, which did not exist until 2026-08-25.

## SuperDisk!'s second implementation (`tools/sdmodule/`, in `ci.sh`)

Added 2026-08-25, and it needs no Macintosh. Disk Expander 1.2 — which
`fixtures/alysis-disk-expander-12.hqx` carries and this engine extracts —
holds one `Cmpr` resource per codec: a "SuperDisk! Add-In Module", 68k code
with no Toolbox in it. `sdmod_run.c` is built for m68k-linux and calls one
under `qemu-m68k` with the parameter block INIT 32 fills in; the driver
lifts the modules out of the fixture and runs three phases.

    tools/sdmodule/run_sdmodule.py --macextract build/macextract
    tools/sdmodule/run_sdmodule.py --list        # the seven modules

1. **Every real block in both corpus archives** whose method has a module,
   against what this engine wrote — and then one block CORRUPTED on purpose,
   which must not match. A comparison that has never failed is not evidence.
2. **The specimens Alysis's own 1991 control panel wrote**
   (`tools/vmac/sdcompress.py`), when they are in the emulator cache:
   18 blocks of methods 1 and 6, byte-exact both ways — four of them
   compressed on purpose (`--boundary`) to chase the one disagreement
   below, and they closed off the way it was supposed to be reachable.
3. **Synthetic blocks for methods 1..9**, built from this engine's reading
   and put through both readers.
4. **Method 10 three ways** (added 2026-08-25, when the method was
   implemented): a stream this harness encodes, decoded by this engine and
   by SlowFastA's own module, with all three required equal. Nothing in
   reach writes method 10, so this is the only grading it has — and it
   earned its keep on the first run, where the match length was read as
   `2*(nibble+1)` against the reference's `nibble + 2` and the module said
   so on every match.
5. **Tennessee**, which is method 20's module and turns out to be an
   ENCODER: five blocks it writes must declare method 11 and must decode
   back here to the bytes that went in. That is also the only compressor
   for method 11 in reach — the corpus has four such blocks, and this
   makes as many as wanted.

**The callback is the part to know about.** "Tighter" decodes methods 2, 3,
4, 6, 7 and 8, and it hands its Huffman regions back to its CALLER to decode
— `jsr` through a field of the parameter block — so the runner has to be a
dispatcher as well as a loader. Without one it jumps to address zero.

`tools/vmac/rescomp.py` is the sibling that went looking for data for the
three methods this suite can only load: Alysis Resource Compressor 2.0
(1993) carries the whole codec library, and `--modules` lists it without an
emulator. What it settled is negative and worth keeping — driven under Mini
vMac it compresses into Apple's resource container, not a `Cmpr` stream, so
it is not the writer of methods 10, 13 and 20 either (OPEN_ITEMS.md).

**What it cannot see.** A synthetic Huffman region is written with a flat
8-bit table, so no real tree shape is exercised: what is graded is the
framing, the flag bitmap and the context predictor. Method 10's cases are
one block each, so the history carried BETWEEN blocks is exercised only by
the code it shares with SlowFastB; 13 and 20 have modules that cannot be
run end to end here at all (OPEN_ITEMS.md). And agreement is not correctness
where both sides came from one reading — a framing error shows up, a
misreading of what the original COMPRESSOR emits does not. The one
disagreement the two references have with each other is counted separately
and printed, not hidden (FORMATS.md, the method table).

## SpaceSaver's own codecs (`tools/ssmodule/`, in `ci.sh`)

Added 2026-08-25, and it needs no Macintosh either. Each SpaceSaver method
is a `CMod` resource holding a **compressor at +0x08 and an expander at
+0x10**, so the modules are both the specimen generator and the second
implementation — for the three methods this engine declines as much as for
the two it reads. `ssmod_run.c` builds the parameter block `ExpandFork`
builds and calls a vector under `qemu-m68k`; the driver lifts the modules
and the preset dictionary out of the installed control panel with no
emulator, and runs in about 3 seconds.

    tools/ssmodule/run_ssmodule.py --macextract build/macextract
    tools/ssmodule/run_ssmodule.py --keep        # leave one .ss per method

1. **Round trip through Aladdin's code alone** — each module compresses a
   subject and the matching expander decodes it, both decompress-only
   builds included. This has to pass before any comparison with this engine
   means anything, because it is what says the parameter block and the
   callbacks are right.
2. **Negative controls** — a corrupted stream, and methods 3 and 4 decoded
   without the preset dictionary. Both must come back wrong.
3. **A stored block built by hand**, which both Original expanders must
   return verbatim: flag byte 1 at +0, big-endian payload length at +4,
   payload at +8.
4. **This engine against the module** for every method the format has —
   byte-exact, 44 forks. `IMPLEMENTED` at the top of the driver is the
   list, and it has to match `src/fmt_spacesaver.c`: a method in one and
   not the other fails this phase from either side.
5. **Corrupted specimens through this engine**, 40 per method: the
   corpus has no SpaceSaver fixture, so this is the only place these
   codecs meet damaged input. Each must exit as itself rather than as a
   signal, and must exit at all.
6. `--keep` writes one specimen per method into
   `specimens/spacesaver/modules/` beside the emulator's other state, in a
   subdirectory so that `run_spacesaver.py` — which grades every `.ss`
   next to it against the emulator's own specimens — does not adopt them.
   **They are what the Macintosh tier replays for methods 1, 2 and 3**:
   `tools/vmac/run.py --expect .../modules/m1.ss ...`, 3/3 at 4 MB and 3/3
   at the 1 MB floor (FORMATS.md, *StuffIt SpaceSaver*).

**What it cannot see.** The modules know nothing about the 84-byte header,
so this grades codecs and not files — the method choice, the 256-byte
rounding and the header are the application's, and a file SpaceSaver itself
wrote would still settle things this cannot (OPEN_ITEMS.md). The subjects
are ours, so a codec that mishandles input no test here builds stays
invisible. And two of the modules do not run end to end: the Original
compressors execute an F-line `0xFFFF` on the branch that stores a block
verbatim, which is counted rather than emulated — nothing here invents what
that word meant (DECISIONS.md 2026-08-25, SpaceSaver's codecs).

**Every module call has a timeout, and it is not decoration.** `CMod 3`
does not terminate on a corrupted stream; without the timeout the negative
control hangs the suite, which is how it was found.

## AppleLink packages (unit tests + a corpus sweep)

Added 2026-08-23. `.pkg` is detect-only, so what there is to test is the
probe, and it is tested two ways.

**Eight unit checks** assert the shape of Aladdin's own recogniser rather than
the format: the two accepted third tokens, case-insensitivity, leading
whitespace, and four near-misses — a prefix that is not a token (`Decoder`), a
missing third token, a wrong one, and prose. They fail against a probe that
stops checking the third token.

**The corpus sweep is the part that matters.** A text-shaped probe can only be
trusted by how often it is wrong about files that are not packages, so
`macextract sniff` was run over all **928 fixtures**: 0 said AppleLink. That is
the DiskCopy standard — its probe was graded the same way — and it is the only
evidence available while no `.pkg` file exists here.

**What this cannot see.** Whether a real package would be recognised. The
probe is a transcription of the reference's test, and the reference is the
only thing that says what a package looks like; nothing here closes that loop
(OPEN_ITEMS.md). `tools/vmac/spacesaver.py --pkg` re-derives the test from the
translator and prints four witnesses, which is a check on the transcription,
not on the format.

## Archives named but not extracted (`tools/run_foreign.py`, in `ci.sh`)

Added 2026-08-26, replacing the disk-image suite that came out the same day
(`attic/`). `src/fmt_foreign.c` is signatures and nothing else, so the test is
the signature, its neighbours, and the corpus.

```sh
python3 tools/run_foreign.py --macextract build/dev/macextract
```

**Three grades of case, and the suite says which is which.** bzip2, xz, 7z,
cpio (three header shapes) and ar are written by their own tools here and then
**opened by p7zip** — a specimen that p7zip cannot parse proves nothing about
a probe, so that check is asserted rather than assumed. Zoo, ARJ and Cabinet
are hand-built headers that **deark** must identify as `zoo`, `arj` and `cab`;
if deark does not agree, the case is worthless and fails. RAR and RAR 5 have
neither — no writer here, no deark module, and p7zip refuses to name a stub it
cannot parse — so in `ci.sh` they rest on the constants in
`reference/XADMaster`, with real archives measured once outside it (FORMATS.md,
*Archives named but not extracted*).

**The negatives are the point of a signature file**: the eighth RAR byte, the
7-Zip reserved byte, xz's terminator, bzip2's two stream magics and its level
digit, Zoo's magic at offset 0 instead of 0x14, ARJ with a broken header CRC
and with a size out of bounds, `070703`, `!<arch>!`. Each was mutation-tested
against a probe with that field deleted.

**And the corpus is swept**: not one of the 940 fixtures may come back as a
foreign archive. Naming a Macintosh archive as a PC one is worse than not
naming it, because the user would then be sent to a program that cannot open
it either.

**What this cannot see.** Whether a real Zoo, ARJ or Cabinet archive is named —
those three are graded on headers built here, which deark identifies but which
no archiver wrote. And nothing here tests what a named-but-declined archive
does on the Macintosh: that is one alert, photographed once
(`tools/vmac/README.md`, *Photographing the detect-only alert*).

## StuffIt SpaceSaver (`tools/run_spacesaver.py`, in `ci.sh`)

Added 2026-08-22. SpaceSaver has no oracle but itself — `unar` and
`macunpack` do not know the format, so there is no manifest — and **it has no
specimen yet either**: twelve emulator runs have driven every trigger the
control panel offers and none of them compressed anything (OPEN_ITEMS.md,
DECISIONS.md 2026-08-22, what will not compress). So today this suite runs
its synthetic pass and skips the rest, and what is written below is what it
does when a specimen arrives — and a specimen is worth less than it was,
because the reading it would check has since been cross-read against
Aladdin's encoder (below). Specimens live outside the repository, beside
the emulator's ROM and System image, because a compressed file is what
SpaceSaver made of a subject:

    ~/.cache/macextract/vmac/specimens/spacesaver/NAME.ss        the file
    ~/.cache/macextract/vmac/specimens/spacesaver/NAME.ss.orig   its input
    ~/.cache/macextract/vmac/specimens/spacesaver/PrAm-4048.bin  the preset

`tools/vmac/spacesaver.py --idlespec` makes the first two (an emulator run);
`--layout` writes the third out of the installed control panel. **With none
of them present the suite prints what it skipped and returns 0**, so a fresh
clone stays green and says nothing.

**The synthetic pass, and what now stands behind it.** An Alg 4 ENCODER,
written from the same disassembly as the decoder, round-trips 200,000 bytes
through a window that wraps and a dozen blocks, a case at the widest window
the width byte allows, and one whose first 4 KB are the preset dictionary
itself. **Two implementations of one misreading would agree**, so on its own
this is a consistency check and not an oracle.

What makes it more than that is a second reading: **Aladdin's own encoder**
— `CMod 20`'s compressor, a different routine in a different module from the
decompressor everything was first read out of — **agrees field for field**:
the stream header, the block header, which bytes `clen` counts, the 9-bit
literal, the 21-bit match, the length bias of four, LSB-first packing, and
where the preset dictionary sits (DECISIONS.md 2026-08-23, the encoder
agrees). The synthetic pass checks that this code implements that reading;
the cross-read is what checks the reading.

**The dictionary is checked for drift, because it is generated AND
committed.** `src/ss_dict.h` is written by `tools/gen_ss_dict.py` from the
`PrAm` resources of an installed SpaceSaver, so the build needs neither the
emulator nor a copy of the software — and a generated file that is committed
is a file that can go stale. Whenever the resource is present the suite
compares the two byte for byte, and says so. It fails against a header with
one byte changed.

The unit tests carry the rest of the contract: that the built-in table is
used when a caller supplies none, that a caller's table overrides it (the
same stream decoding to different bytes proves neither is being ignored),
that the record's byte at +12 selects between the two built-in tables, and
that a table this build does not have is refused rather than decoded with the
wrong one.

**58 corrupted variants per specimen** — ten truncations, forty-eight
bit-flips — because `fuzz.py` and `run_robustness.py` both work from
`fixtures/`, where no SpaceSaver file may be committed. They are FORCED with
`-f "StuffIt SpaceSaver"`: a truncated header sniffs as *unknown*, and a run
that trusted the sniff would exit clean having parsed nothing. `fuzz.py` also
carries the header's magic now, so its garbage generator aims at this parser.

**The Macintosh side is three files, not a suite.**
`tools/run_spacesaver.py --emit DIR` writes them and `tools/vmac/run.py
--expect DIR/*.ss` replays them: stored, method 4 without a dictionary, and
method 4 that needs one. `--expect` grades a Mac run against this engine's
own Linux output, the arrangement SuperDisk! and the ArcMac specimens
already use, so what it proves is that the same bytes come out of a 68000 —
not that either side is right. 3/3 at 4 MB and 3/3 at the 1 MB floor
(2026-08-22; figures in FORMATS.md).

**What this cannot see.** It grades methods 0 and 4 because that is what the
machine that made the specimens writes — Gestalt `cput` picks 4 below a
68030 (FORMATS.md). Methods 1, 2 and 3 are graded off the Macintosh instead,
against the modules that write them (*SpaceSaver's own codecs*, below); what
the unit test still asserts is the per-ENTRY refusal, now for method 5, which
no version of SpaceSaver ever wrote. The unit tests also carry what no
specimen here has: a resource fork whose stream is written BEFORE the data
fork's, which is what the header's offsets are for.

## Segmented archives (`tools/run_segments.py`, in `ci.sh`)

No segmented archive exists in the corpus — first measured 2026-08-08 and
**re-measured 2026-08-15 over all 805 fixtures**, after M12 grew it: no
`B0 56 00` header anywhere, all 108 Compact Pro archives are volume 1 with
every file entry in them pointing at volume 1, no disk-spanning zip marker,
no part-like filename, and no part-like entry name in the 805 manifests. So these fixtures are generated by
`tools/synth_sitsplit.py` into a temp directory per run, and each case
is required to agree three ways: what the generator wrote, what `unar`
extracts, and what our CLI extracts. The generator alone would be our
own code grading our own code; `unar` is what adjudicates.

Seven cases: three parts with cuts inside both forks, a set of one, a
cut exactly on the fork boundary, data-only, resource-only, twelve
parts (one carrying no payload), and a set whose filenames contradict
the part order with a name-alike intruder beside it. Plus behaviours:
opening a part other than the first, a missing part, `--ask` accepting
and refusing files, `--no-parts`, and the part-open counters.

### Spanned zip (`tools/synth_zipsplit.py`, same runner)

Five more cases, and here the generator is **Info-ZIP** rather than us:
`zip -s 64k` builds each case split, and the same input again unsplit.
That second archive is the reason this scheme is adjudicated four ways
rather than three — the source tree, `unar`, our CLI on the set, and our
CLI on the unsplit archive, which reaches the same bytes down a path
with no joiner and no address translation in it. Skipped with a notice
if `zip` is absent, the way the whole file is if `unar` is.

The cases: stored entries straddling part boundaries; a deflated stream
straddling one; nested folders with an 8-bit name and an empty file;
twelve parts, so the extension rolls over `.z09` → `.z10`; and a
`zip -s` archive that did not need splitting (one file, the marker
present, "disk 0" — which must extract even under `--no-parts`).

**The two cases that hold the scheme up** are the mutations, because
parts are placed by FILENAME here and a filename proves nothing: two
parts swapped, and one part replaced by random bytes of the same
length. Both must fail. That they are not vacuous was established by
building a lax reader — CRC comparison and local-header signature check
removed — and confirming that those two cases, and only those two, then
fail. Re-do that before trusting a change to `zip_at` or to the part-count
check in `unc_zip_extract`.

Opening a MIDDLE part must fail, and the case asserts that `unar` fails
on it too: the justification for refusing is that such a part identifies
itself as nothing, and that is a claim about the format which the suite
re-checks rather than quotes.

**`--stats` is asserted against a floor, not merely printed.**
`zip_floor()` derives, from each archive's OWN central directory, the
fewest part opens the format permits — read the last part for the
end-of-central-directory record, read the directory from wherever that
record says it starts, then visit each entry in the order listed,
rolling forward while its data spills into the next part — and the
measured count must equal it exactly.

### Compact Pro segments (`tools/synth_cptsplit.py`, same runner)

Two cases, and the adjudication chain is what makes them worth
anything: a set is cut from an archive the differential suite ALREADY
grades against `unar` and `macunpack`, so "the set holds what the
archive held" rests on nothing this scheme wrote. `cpt4` has folders
and entries either side of a cut; `cpt5` holds one entry whose data
crosses every boundary.

**The oracle appears for what it cannot do**, which is why this scheme
needed a specimen at all. Given the final segment `unar` calls the file
a whole Compact Pro archive — `lsar` agrees — reads every entry at an
offset belonging to another volume, fails most of them, writes the rest
as garbage and exits 0. Given the first segment it says "Couldn't
recognize the archive format" and also exits 0. Both are asserted, so
if the reference ever learns the scheme this repository finds out.

Beyond byte-exactness: **any** segment opens the set (the application
itself requires the final one); a segment of ANOTHER set, put in place
of the missing one, is refused by its identity; a missing segment fails;
`--no-parts` refuses.

**Part opens are asserted against a floor**, derived in Python from the
archive's own directory the way `zip_floor()` is — the index is in the
last segment, then entries are visited in directory order, rolling
forward while their data spills. 5 opens with 1 backward crossing on
`cpt4`, 6/1 on `cpt5`.

**And the same case runs one byte under its own high-water mark**, which
lands on the index buffer because that is allocated last. Refused, the
walk reads each record where it lies: `cpt4` goes 5/1 → **19/8** with a
byte-identical tree. Both halves are asserted, so neither the
optimisation nor its fallback can quietly stop working.

**What this layer cannot see:** the Mac shell, and anything about how
Compact Pro actually writes a set. The second is covered by
`tools/vmac/cptsegment.py --verify`, which requires the generator above
to reproduce two real sets — cut by Compact Pro 1.51 under Mini vMac —
byte for byte, and by the suite extracting those real sets when they
are present on the machine.

### Parts inside envelopes (`tools/synth_wrapped.py`, same runner)

Three cases, and they are the same StuffIt sets with a BinHex or
MacBinary layer around each part — `Archive.sit.1.hqx`, which is the
shape a download of one actually has. One case per envelope, plus a
mixed one whose wrappers are named `zzz-download.bin` and
`Other.sit.9.hqx`, so a pass says identity survived the envelope rather
than that the names lined up.

Adjudicated three ways, none of them the code under test: the
generator, which knows the joined bytes exactly; our own read of the
same set UNWRAPPED, which reaches the joiner without opening an
envelope; and `unar` for what it DOES — handed part 1 of a wrapped set
it unwraps that one part and exits 0, success with a fragment, which
the suite asserts rather than remembers.

**What this layer cannot see:** the Mac shell. This is `cli/main.c`
only. The shell has its own envelope step in the interactive path since
2026-08-14 (PROGRESS.md, M11) and it is driven by `interactive.py`, not
here. Nor does this layer see the other two schemes, which are placed by
filename and are deliberately not looked for inside envelopes at all
(DECISIONS.md, 2026-08-13).

The behaviours are where the design is: a wrapped part of a DIFFERENT
set, wrapped and named exactly like the missing one, must be refused —
the envelope comes off and the fingerprint decides; parts scattered
across three directories in two envelopes under three names must join;
and nothing of ours may be left in the output directory, on a failed
join as much as a successful one.

**The ration has a case in each direction, and the first version of it
could not fail.** Envelopes are opened only when the set is still short
of a part, so a COMPLETE set must open nothing beside it however many
envelopes are lying there, and a set missing one must open them and
join. What is asserted is the decode itself — `looked inside X` under
`-v` — because the first attempt asserted a consequence of the search
(whether a wrapped part was USED) and stayed green with the ration
removed: a part already located is skipped before anything is printed.
All four assertions were shown to fail before being believed, by
mutating the code they guard — search disabled, ration removed, cleanup
removed — and the foreign-decoy one by replacing the decoy with the
genuine part.

### DiskDoubler `SPLT` (`tools/synth_ddsplit.py`, same runner)

**No oracle at all**, and the suite asserts that rather than assuming
it: a case requires `unar` to fail on a part, so the day it has a second
implementation, this says so. Adjudication is therefore against the
bytes that were cut up, and, where the payload is a zip, against our own
read of the unsplit archive.

Eight cases: two parts cut inside the data fork (the specimens' shape),
three with a cut inside the RESOURCE fork (which neither specimen
reaches), a set of ONE, twelve parts, parts with 64 bytes appended after
each payload, parts named nothing like each other, parts named `.001`
… `.003`, and a zip payload. Each is joined from the first part and
from the last.

Behaviours: `--no-parts` must fail on a set of more than one and must
SUCCEED on a set of one (a different code path — `unc_ddseg_extract`,
with no volume source); a part of a foreign set in the same directory
is ignored; a missing part fails and says so; a part that declares more
payload than it holds is refused; one flipped PAYLOAD byte and one
flipped byte of the STORED CRC must each fail the join with a checksum
error — both halves, because a reader that ignored the stored CRC and
one that ignored the payload would each pass one of them; and the set
still joins afterwards, so the mutations are testing the mutation and
not the directory.

**Three of the cases are load-bearing, and that was confirmed by
mutating the code they guard.** Removing the header-declared payload
length breaks `tail`; emitting the forks in StuffIt's order breaks every
case with a resource fork; removing the rule that a `SPLT` header beats
a `.NNN` filename breaks `numbered` (DECISIONS.md 2026-08-21 for what
that rule is protecting).

**What it cannot see:** the layout. These parts are written from
`src/fmt_ddseg.c`, so a case passing says the reader matches what was
derived, never that what was derived matches DiskDoubler.

**What says that is in the same runner since 2026-08-21**: the three
sets DiskDoubler itself cut, registered as fixtures (`run_ddtf.py
--register`) and joined here from the first part and from the last. A
fourth kind of evidence is outside `ci.sh` and worth knowing about:
`tools/vmac/ddpro.py --experiments` has DiskDoubler Pro 4.1 split a file
of known content under emulation, and the parts join back to the bytes
that went in — cut on a Mac, joined here, compared with the input. Each
is compared with the file the corpus publishes beside it — both forks,
the resource fork coming from the AppleDouble sidecar that is a fixture
too — and then the joined archive is extracted and required to give what
the unsplit one gives. One flipped byte in a COPY of a real part must
fail the join on the CRC DiskDoubler wrote, which is the same assertion
as above with the generator taken out of it.

### Plain `.NNN` splits (`tools/synth_split.py`, same runner)

Three cases, and the ground truth is exact rather than an opinion: the
generator CUTS a file up, so the join is required to equal the bytes
that were cut, byte for byte. Two payloads, because they answer
different questions. A plain data file is one `unar` can also join, so
the join itself is adjudicated against the oracle. A zip archive is one
it CANNOT — its content parsers claim part 1 as the truncated archive
it is a slice of — and that asymmetry is the whole reason our discovery
decides by name, so the suite re-measures it every run rather than
quoting it. The archive payload is then adjudicated twice more: the
joined archive must extract to the source tree, and to exactly what our
own engine gets from the same archive unsplit.

**The two cases that state the scheme's limit are as load-bearing as
the ones that state its strength**, because a split proves nothing about
itself and inherits whatever proof its payload has. A set missing its
TAIL joins cleanly into a short file and NOTHING notices — asserted. A
swap of two parts is thrown out by the payload... unless the swap
involves part 1, after which the join no longer sniffs as an archive,
is emitted as the plain file this scheme may legitimately produce, and
nothing objects — also asserted, with a message telling the next reader
to find out what caught it before believing a pass. Beside them: the
consecutive-run rule (a member numbered past the end of the run is a
missing part, where the reference appends it silently — both halves
measured), the 256-part ceiling as its own case, `--ask` across a gap,
`--no-parts`, opening any part, and part opens against a floor of one
per part with no backward crossing.

The stray-member case was numbered `NAME.900` at first and **passed for
the wrong reason**: 900 trips the part-count ceiling, a different
branch, so deleting the consecutive-run rule left it green. Mutating
the code a test guards is the only way that shows up.

Computed in Python rather than asked of the engine, for the same reason
`py_parts()` re-implements the StuffIt match rule: a floor the engine
calculates is a floor the engine cannot fail to meet. Both directions
have been demonstrated. Falling back to the record-at-a-time directory
walk gives 16/6 against a floor of 6/1 and fails; adding back a pass
that measures every part first gives 10/1 and fails. And the model
itself was wrong first — it ignored where the directory sits, so it
accused `zmany` of two opens the format requires. **A floor that is too
low reads as a defect in the thing being measured**, so treat a
mismatch as a question about both sides.

The last case also runs under a budget one byte below the run's own
high-water mark, which lands on the directory buffer exactly when
nothing else is competing for the heap — so it is applied only to the
cases the generator recorded as all-STORED. That forces the fallback
walk and requires identical bytes out of it, at a cost in opens that
must be strictly worse; otherwise buffering the directory is doing
nothing and the case would pass while proving that.

**Two ways the oracle can be wrong here, both measured on 2026-08-08:**

- `unar Part.1` joins **nothing** and extracts part 1 alone, while
  `unar ./Part.1` and `unar /abs/Part.1` join the set. In
  `+volumesForHandle:`, `[name stringByDeletingLastPathComponent]` is
  `@""` for a bare relative name and the `if(!dirname) dirname=@"."`
  guard does not fire for an empty string, so the volume scan reads the
  wrong directory. Ground truth built that way is silently truncated
  and looks fine. **Every oracle call passes an absolute path.**
- `unar` finds parts only among files whose name starts with the opened
  part's basename (`[filename hasPrefix:basename]`), even though it
  then matches them by content. A set that is not named alike is
  invisible to it — which is exactly what the `misnamed` case is. That
  case is therefore adjudicated on a **renamed copy of the same bytes**:
  the payload stays oracle-checked while our discovery is what the case
  tests.

The oracle also runs `-nr`, because the parser marks the joined file as
an archive when its name ends in `.sit`/`.sea` and would otherwise
extract that too; our side stops at the same layer.

**What this cannot see.** The comparison drops zero-length files on
both sides, because our CLI writes an empty data fork as an empty file
and `unar` writes nothing at all — a file-creation policy, not bytes.
A disagreement of that shape is invisible to the oracle comparison and
is covered only by the generator comparison, which encodes our policy.
It also says nothing about the Mac: `tools/vmac/run.py --extra-file`
puts the other parts on the In floppy for the join, and
`tools/vmac/interactive.py --segments` drives the dialog (layer 10
below). And it cannot see the *dialog* at all — the CLI's `--ask` uses
the same engine callback, which is the most it can claim.

**It was demonstrated failing before it was called passing**, by
mutation: a matcher that ignores the fingerprint (4 failures — the
name-alike intruder gets used) and a joiner that drops one byte per
part boundary (27 failures). Both were reverted.

## On-Mac layers (not in `ci.sh` — they need an emulator)

7. **Mini vMac replay** (`tools/vmac/run.py`, System 6.0.8 and 7.0.1 on a
   Mac Plus): the autotest build CRC-32s both forks after reading them
   back through the real File Manager and paints an aggregate to the
   framebuffer; the host decodes the screenshot and compares against the
   same engine's Linux output (`tools/vmac_check.py`).
8. **Mac OS 9 replay** (`tools/vmac/os9.py --launch`, QEMU PowerPC): the
   application is launched from the Finder by keyboard, and afterwards
   the transfer volume — a plain file on the host — is mounted with
   hfsutils and **both forks of every output file are compared byte for
   byte** against `macextract x -nr`.

9. **Reading the Mini vMac Out volume** (`tools/vmac/run.py --keep-disks`
   then `tools/vmac/checkdisk.py /tmp/vmacrun-*/`): the same comparison
   layer 8 does, on the System 6/7 tier — both forks byte for byte,
   plus names and folder structure, read off the floppy image after the
   run. **53/53 on the committed sample.**

10. **Driving the real UI** (`tools/vmac/interactive.py`): the
    interactive application, clicked the way a person clicks it. Its
    `--segments` phase covers the "locate part N" alert, which nothing
    else can — the autotest build has no user and does not compile
    `SegAskUser` at all. Part 1 is left alone on the boot volume and the
    others put on a second floppy, the WRONG part is offered first, and
    the phase **ends on a byte comparison** of the joined file read back
    off the volume the Mac wrote to. That last part matters: the other
    interactive phases assert on a screenshot, and a screenshot fails
    identically whether the application is wrong or the harness is aimed
    wrong — which is exactly what happened twice while writing this one
    (DECISIONS.md, 2026-08-09).

    Its `--dest` phase covers the destination dialog the same way. The
    archive is on the boot volume, an empty floppy is mounted beside it,
    the DESTINATION dialog is switched to the floppy, and afterwards the
    host reads **both** volumes: every output name must be on the chosen
    one and none may be on the archive's. That is the assertion, because
    "Extraction complete." looks identical wherever the bytes went.
    Its `--diskswap` phase goes one further and changes the machine
    mid-run: the parts are on a floppy that is NOT in the drive, the
    application asks for one, and the harness **inserts the disk while
    the alert is up** (`tools/vmac/xdnd_insert.c` drops it onto the
    running emulator). A decoy disk holding no part of the set goes in
    first and must not dismiss anything — without that control the
    phase could not tell "reacted to the right disk" from "the alert
    went away". It ends on the joined bytes.

    `--wd` covers the other half and asserts the same way: the archive
    goes inside a folder, Return accepts the default destination, and
    every output name must be under that folder and none at the volume
    root — which is where a working-directory mistake would put them.

    **The default phase runs on both Mini vMac tiers**, and since
    2026-08-25 `--system Sys7.img` is one of them: `ProgressPump()`'s
    `WaitNextEvent` side, the Cancel button through `DialogSelect`,
    Cmd-. through the keyDown check beside it, and the SFGetFile
    repaint afterwards. Its fixture is chosen with 8-bit names, so the
    same run also photographs System 7 drawing MacRoman — the one
    thing the byte comparisons cannot see. What it does NOT cover is
    Mac OS 9, where the application has only ever been driven to
    completion (OPEN_ITEMS.md, section 1).

**What each layer can see is not the same, and that matters.** Layer 7
compares a count, two summed CRC-32s and two summed lengths. A summed
CRC cannot carry a filename, so layer 7 has never checked an output
NAME and cannot be made to fail on one. Layer 8 compares names as a
side effect of reading a directory, and on its first sweep it failed two
fixtures that layer 7 had been passing for weeks — a real defect in the
Mac shell's fallback name for gzip/.Z (BLOCKERS.md, DECISIONS.md).

An aggregate check cannot fail on a property it never aggregates. When
adding a harness, write down what it is blind to.

Layer 9 exists because that blind spot turned out to be self-inflicted.
BLOCKERS.md had said since M10 that Mini vMac's write-back was "lazy and
PARTIAL — it can commit one fork of a file but not the other", so results
"cannot be read off the Out volume". It does not reproduce; the claim is
withdrawn. The screen channel was never wrong, only unnecessarily blind.
