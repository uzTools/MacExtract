# TESTING.md — how unclassic is validated

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
   Contents index must list every `## ` entry in file order, and no
   document may cite another by line number. Needs no build, so `ci.sh`
   runs it first; `--fix` regenerates the index. **What it cannot see:**
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

`unclassic` writes `<file>.rsrc` by default like unar, and `._<file>`
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
- Do not read "unadjudicated: 12 forks" as 12 defects. It is 12 forks
  across 9 fixtures where two implementations cannot be compared, and
  **both sides decline on every one of them**: 8 in damaged nested archives
  where the engine says "file is truncated" and unar says "Error on
  decrunching", and 4 in the two PKZIP 1.x zips, where unar failed the entry
  and Implode is outside v1 scope for us. Every fork the engine extracts is
  adjudicated by somebody. (The count was 8 across 7 until those two zips
  stopped being skipped whole, which is the point: a skipped fixture's
  unadjudicated forks were not counted anywhere.) Out of the diff run's
  scope, 11 more forks stay unadjudicated in DiskDoubler fixtures.

### When our engine declines an entry

A per-entry error from `unclassic` is tolerated in exactly two cases, and
**both are the oracle's word, never ours**:

- the oracle failed that same entry (it is `unadjudicated`), or
- the oracle names the entry's compression method as one v1 does not
  implement — `oracle_methods` against `run_diff.py`'s
  `ORACLE_OUT_OF_SCOPE`, which today holds `Implode` and nothing else.

Anything else fails the fixture, including a non-zero exit with no
per-entry report at all, and including every whole-archive error (those
name the FIXTURE path, which can never match an entry name).

**Why it is anchored outside our own output.** Until 2026-08-08 a fixture
was skipped whole when every entry our binary reported failed with
"recognized but unsupported". Two consequences, both measured on
2026-08-08:

- it discarded ground truth. `4acalc.zip` and `4alnch11.zip` carry
  adjudicated hashes for 5 of their 7 entries — `unar` implements Implode
  and we do not — and none of the 10 forks, nor the names, nor the entry
  counts were compared. **"even unar fails on them" was true at M8 and
  false since per-entry manifests landed**, and the disproof was sitting
  in the manifests themselves.
- it could not fail. A regression that made a *supported* method report
  "recognized but unsupported" for a whole archive converted a failure
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
`unclassic l` output. Dates are recorded loosely but not compared (v1;
see DECISIONS.md).

## Corpus

`fixtures/` is gitignored (copyrighted historical software); committed
are only `fixtures/SOURCES.md` (name, sha256, size, URL per fixture)
and `fixtures/manifests/`. `tools/harvest.py --restore` re-downloads
the corpus; `--probe URL` adds a candidate, accepting it only if lsar
can read it.

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
   mutation/splice/magic-garbage cases through `unclassic t` under the
   sanitizer build; nonzero exits are fine, signals/sanitizer
   aborts/hangs fail. 4,000 cases at M9; every CI run does a 150-case
   smoke.

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
  797-fixture diff suite and all 7,970 robustness variants run through the
  fallback under ASan+UBSan, and must be byte-exact.
- `--budget 678392` (what a 1 MB Mac Plus leaves the engine) on the 31
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
    UNCLASSIC=build/never/unclassic sh tests/run_diff.sh      # expect 797/797

    # 2. the safety net is correct: force it to run on every stream
    make BUILD=build/tiny CFLAGS="-O1 -g \
        -fsanitize=address,undefined,alignment -fno-sanitize-recover=all \
        -DUNC_LZW_TINY_TABLE" all
    UNCLASSIC=build/tiny/unclassic sh tests/run_diff.sh       # expect 797/797

    # 3. these fixtures CAN fail on this code: starve the table AND
    #    skip the add instead of growing
    UNCLASSIC=build/probe/unclassic sh tests/run_diff.sh      # expect ~90 FAILURES

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

## Segmented archives (`tools/run_segments.py`, in `ci.sh`)

No segmented archive exists in the corpus — measured over all 806
fixtures: no `B0 56 00` header anywhere, every Compact Pro archive is
volume 1 with all 273 of its file entries pointing at volume 1, no
disk-spanning zip marker, no part-like filename, and no part-like entry
name in the 804 manifests. So these fixtures are generated by
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
only, and the shell's discovery matches headers with no envelope step
in it (OPEN_ITEMS.md section 4). Nor can it see the other two schemes,
which are placed by filename and are deliberately not looked for inside
envelopes at all (DECISIONS.md, 2026-08-13).

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
   byte** against `unclassic x -nr`.

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
