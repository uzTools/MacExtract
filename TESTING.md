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
4. **Progress-callback coverage** (`tools/tick_probe.c` +
   `tools/run_ticks.py`): the one engine property the byte comparisons
   cannot see. A decoder that never yields to its caller produces
   perfectly correct output and freezes the Mac's progress dialog for the
   whole extraction, with both Cancel routes out of reach. Every fixture
   the engine extracts must call back at least once, and no gap between
   calls may exceed 32 KB. **What it cannot see:** how long a gap TAKES —
   it counts input bytes, not time, so a decoder that spends a minute on
   8 KB passes. The Mac OS 9 tier is where that would show
   (`os9.py --cancel`).
5. **The Mac shell's sink, allocator and I/O through a mock Toolbox**
   (`tests/run_mac_sink.sh` + `tests/mac_sink_test.c`): the shell's own
   code from `mac/macextract_mac.c`, compiled on the host under
   ASan+UBSan and again big-endian under qemu-m68k, driven by the real
   engine over a spread of fixtures and compared byte-for-byte, both
   forks, against the oracle manifests. **What it cannot see:**
   `RunExtract`, `ExtractOne`, the dialogs and the Toolbox glue, which
   the mock never calls — it builds its own `UncOptions` and hands the
   engine the sink directly. And a read of state nobody set: ASan reports
   writes past a block, not a load from uninitialised stack, so the
   `UncOptions` field the shell left unassigned for eight days
   (DECISIONS.md 2026-09-04, *the field nobody assigned*) was invisible
   to this layer by construction, and would have been even had the mock
   run `RunExtract`. Nor does valgrind see it: over the pre-fix unit
   tests, whose DiskDoubler and SuperDisk! walks read the unset field 20
   times (gdb), it reported nothing, because stack bytes an earlier call
   had written count as initialised. That class needs MemorySanitizer
   over the real call chain, and no host-side build here has it.
0. **Documentation invariants** (`tools/check_docs.py`): DECISIONS.md's
   Contents index must list every `## ` entry in file order, no
   document may cite another by line number, the version agrees in the
   three places it is written, and every `synthetic:` fixture in
   SOURCES.md regenerates the bytes recorded there. **Two figures about
   the documents themselves joined on 2026-09-26**, both of which had
   gone stale three times between them: the five sizes CLAUDE.md
   advertises as the session-start reading, at four characters per token
   and a tolerance of 25 % or half a thousand, and the number of smells
   BLOCKERS.md claims — counted from the list, in both files that quote
   it. Needs no build, so
   `ci.sh` runs it first; `--fix` regenerates the index. **What it cannot
   see:**
   whether an entry is in the right file, whether a citation points at a
   section that still exists, or whether a paragraph re-narrates one that
   lives elsewhere — that last one is the failure mode these documents
   actually have (CLAUDE.md, *Writing things down*).

   **A third figure joined on 2026-10-02: the ones DERIVED from
   `tools/run_tiers.py`'s model.** `OVL_SAVED` is quoted in FORMATS.md in
   three different sentences and every per-format budget in *What each
   format is granted* is computed from it; the constant had moved twice
   and the prose neither time. A search for the literal could not find it
   because the prose figure was never the literal — 117,328 against a
   constant of 117,664, a related-but-different quantity, which is how one
   goes stale while still looking plausible. So the three sentences and the
   bundle's own three terms (images + index = bundle) are held against the
   constants, and the run refuses to report a pass unless bending two of
   them is caught. That selftest bends the figures the same code reads, so
   it was also failed from OUTSIDE once on 2026-10-02 — one of the four
   `123,776`s changed by hand to `123,777`, which named the sentence, the
   constant and the function to re-derive from. **What it cannot see:** the
   twelve per-format rows themselves — those are `run_tiers.gain()` of a set
   of images and nothing recomputes them, so re-take them from that function
   rather than by hand.

0b. **Tuple truth** (`tools/check_tuple_truth.py`, in `ci.sh` since
   2026-09-25): a Python function whose every `return` carries a tuple of
   two or more must never be tested for truthiness, because a tuple is
   never falsy and the test therefore cannot fail. Needs no build and takes
   about a second, so it runs beside check 0. `--selftest` alone runs the
   case it was written for; the full run does that first and refuses to
   report a pass it could not have failed. Pass a directory to check some
   other checkout. **What it cannot see:** a function returning a tuple on
   some paths and a scalar or `None` on others — truthiness may be intended
   there, so it is not flagged, and neither is the legitimate
   `if x: return a, b` / `else: return c, d` shape, which the "body ends in
   a return" test drops along with the unsafe ones; any call it cannot
   resolve to a module-level `def` in this tree (through a variable, a
   dict, `getattr`, a method, a decorator); and truthiness reached
   indirectly, as `x = f()` and a later `if x:` — only a call written
   directly in the boolean position is examined.

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
lsar -j -nr -e <enc> <fixture>         # format name + metadata (JSON)
unar -nr -D -f -q -k hidden -e <enc> -o <tmpdir> <fixture>
```

- `-nr`: no recursion — each manifest describes exactly one container
  layer (see DECISIONS.md; nesting is tested by chaining layers).
- `-e <enc>`: pin filename decoding rather than leaving it to
  auto-detection, so manifests are deterministic. **`macintosh` for
  every format but StuffIt 5, whose names are the archive's own UTF-8**
  and which gets `utf-8` (`make_manifests.py`, `ORACLE_ENCODING`). One
  encoding for every format was the same assumption this engine made,
  so the corpus agreed with the oracle about 27 mojibake names and
  proved nothing (DECISIONS.md 2026-09-22, *a name an HFS volume can
  hold*). The format decides the encoding and the encoding decides the
  names, so the first `lsar` is trusted only for the FORMAT, which no
  encoding changes; a format with its own encoding costs one more.
  Each manifest records the invocation it was built with, in `oracle`.
- `-D`: no wrapper directory.

### Manifest format

`fixtures/manifests/<fixture>.json`: fixture sha256/size, lsar format
name, and per entry: name (UTF-8, NFC-normalized), data fork
sha256+size, resource fork sha256+size, type/creator and `finder_flags`
when the oracle exposes them, and `oracle_methods` — the compression method(s) `lsar`
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

And, for a fixture that needs one, `ungraded`: the fields no oracle on
this machine can adjudicate, with the reason beside each. One fixture
has one (*The Finder metadata, and the one field no oracle settles*,
below).

### The Finder metadata, and the one field no oracle settles

`run_diff.py` lists with `macextract l --finder`, which prints type,
creator and Finder flags as hex. **The pretty columns could not be read
back:** `%4s/%-4s` of a code holding a space (`PDF `) or a NUL moves the
name by a field, so the suite looked that entry up under a mangled name,
found no manifest entry, and compared nothing — silently. **200 of the
corpus's 5,539 type/creator codes hold a space** (measured 2026-10-04).
All 937 fixtures pass with the hex form, so what the silence hid was
agreement; the hole was in what COULD have been seen, which is the point
(DECISIONS.md 2026-10-04, *the column that moved the name*).

The flags are graded wherever the ORACLE recorded them — AppleDouble's
`fdFlags` where `unar` wrote a sidecar, `lsar`'s `XADFinderFlags`
otherwise, and the two agree on all 423 entries where both are present.
**A manifest built before 2026-10-04 carries no such key and grades
nothing here**, so `run_diff.py` prints the number of entries it did
compare rather than letting a silent zero read as coverage. Across the
corpus 3,195 entries would be gradeable and the engine agrees with
`lsar` on every one (measured 2026-10-04); backfilling them means
rebuilding manifests, which is its own change.

**The dates are graded nowhere, and for zip's `0x334d` nothing can grade
them:** XADMaster adds `CrGMTOffs`, deark subtracts it, and both label
the result UTC (FORMATS.md, *Zip's Macintosh extra fields*). So the
fixture that carries the field DECLARES the exclusion rather than
inheriting it from the manifest schema's silence:

```json
"ungraded": { "dates": "XADMaster adds CrGMTOffs and deark subtracts it ..." }
```

`run_diff.py` refuses any other key under `ungraded` — a fixture cannot
declare away a field the suite does compare — requires a non-empty
reason, and prints every declaration on each run.
`make_manifests.py` carries the key across a `--force` rebuild, which is
what keeps the one tolerance from being dropped by a command that looks
like a refresh.

**What this cannot see:** whether the dates are right — nothing on this
machine can say; the flags of any entry whose manifest predates the
field; and anything the oracle does not report at all, since an absent
value is never compared and never excused.

**What the fixture costs, measured before it was taken** (2026-10-04,
the sanitizer build):

| | cost |
|---|---|
| `run_diff.py`, this fixture alone | **0.51 s**, median of 5 — against 0.03 s for `derived-MUSFMT10.ZIP`. `ci.sh` runs the diff suite in five build variants, so **~2.6 s** a run |
| `run_robustness.py`, its ten variants | **2.8 s**, median of 3, in three variants: **~8.4 s** a run. The four truncations cost nothing at all — a zip is read from its end, so a cut one is refused before anything inflates |
| the slowest single variant | **0.51 s**, against the suite's 30 s timeout: 59× of headroom, which is the figure that matters for a fixture ten times larger than any other |
| `fixtures/` on disk | **+31,167,318 B** on 72 MB, +41 %, and 10.5× the previous largest fixture |

**The suite-level wall clock cannot see any of this, and that is worth
recording so it is not re-measured that way.** Eleven suites timed with
the fixture and again without it came to 489 s against 511 s — the run
WITHOUT it was 22 s slower, and the diff suite alone moved 24.7 → 38.4 s
between two runs of identical work. Run-to-run variance on this machine
is larger than the whole quantity. **Time the fixture, not the suite.**

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

**`make_manifests.py --force` erases what other tools wrote.** Three
tools put adjudications into manifests that `unar` cannot produce —
`tools/run_ddforks.py --write` (the DDn off-by-one), `tools/vmac/
diskdoubler.py --adjudicate --write-manifest` (an emulated Mac) and
`tools/run_ddtf.py --register` — and a forced rebuild replaces them
with `unadjudicated`. The `--register` ones are safe: the loop keeps
any manifest whose `oracle` is not `unar`. **The other two are not**,
because their fixtures' manifests ARE unar's; a forced rebuild of the
whole corpus silently cost 11 adjudicated forks across
`derived-LHA_Expander_1.0.3.sea` and `derived-Terrainman_2.0__.sea` on
2026-09-22. Worse, they cannot simply be re-run in either order:
`run_ddforks.py` pairs a manifest entry to a file header **by the data
fork's hash**, and on those two fixtures the data fork is one the
emulator graded — so the emulator has to go first, or the pairing
finds nothing and writes nothing. Rebuild the whole corpus and those
two manifests are the thing to check, and `git checkout` is the cheap
answer when nothing about them has changed.

### A third oracle (`tools/build_deark.sh`)

Since 2026-08-25 the forks `unar` AND `macunpack` leave open are offered to
**deark**, recorded the same way (`"data_oracle": "deark (Deark version:
…)"`). It arrived for one method and one reason: `unar` decodes ARC/PAK
method 0x0b (Distilled) **wrong** — right length, wrong bytes, on 6 of the
10 members of `derived-INTRECHO.pak` — because XADMaster starts the 8 KB
window at zero where PAK fills it with spaces (BLOCKERS.md). Those entries
arrive as checksum failures, which is correct of `unar` and useless as
ground truth; deark implements the method independently and agrees with the
CRC PAK stored. `sh tools/build_deark.sh` copies `reference/deark` to
`build/deark/` and builds it; nothing is patched and it needs only a C
compiler.

**Since 2026-09-21 it does two jobs, and the second is the one that was
missing.** It is also offered the **23 forks macunpack alone had graded**,
which nothing was open in, and it agrees with every one. That matters
because macunpack is where this project's StuffIt method-6 decoder was
transcribed from: those forks were a transcription checked against its own
source. Such a fork now records both — `"macunpack (…) + deark (…)"` — and
a DISAGREEMENT is printed and nothing is rewritten, because two
implementations differing is a finding and not a manifest edit.

**It reads both forks**, which this section asserted the opposite of until
that day: deark writes an AppleDouble `.adf` sidecar beside any member with
a resource fork, and the corpus's only real method-6 entry is one whose
data fork is EMPTY and whose resource fork is 34,818 bytes — so the fork
the claim excluded was the only one that method occurs in. It also reads
**Zip**, which the same paragraph denied; it decodes the Implode entries
`unar` fails on.

Matching is **by the name deark WRITES**, with a name two entries share
refused outright, the same rule the `macunpack` path uses. It was by
position and name until 2026-09-21, and the position is deark's
OUTPUT-FILE counter rather than a member ordinal — which is the same
number only while no member has two forks, i.e. only for the one format
the third oracle was ever asked about. And it was by the RAW name until
2026-09-22: deark writes each member to a real file, so a member inside
a folder arrives with its path separators mangled to `_`, and matching
raw names skipped **every entry in a folder** — 500 of them across the
corpus. `deark_name()` models deark's own sanitiser
(`de_char_to_valid_fn_char` in `reference/deark/src/deark-util.c`), and
the mapping being many-to-one is why a mangled name two entries share is
refused.

**A fork deark DECLINED is not a fork it read as empty**, and this
section's "an empty fork is an assertion of absence" rests on telling
them apart. It could not until 2026-09-22: given a StuffIt method-8
entry deark writes the resource fork's sidecar, prints `Unsupported
compression method: 8 (MW)` for the data fork, and writes no data file
— which read as a 0-byte data fork. `deark_forks` now parses the errors
deark attaches to a fork and returns **None** for those; an error it
cannot attach to a fork makes every absent fork of that archive unknown
rather than empty, which is over-cautious on purpose. No manifest ever
recorded a false empty: the gap-filling path had not been offered such
a fork (DECISIONS.md 2026-09-22, *the oracle asked about everything
else*).

Two things about those errors were wrong the same day, and both are
fixed in `deark_forks` so that the manifest builder and the sweep see
one answer:

- **A member deark declined EVERY fork of writes no output file**, and
  was therefore absent from `deark_forks` entirely — so it read as a
  member deark could not name. It is carried now, with the forks the
  errors name as declined and the forks they do not as **unknown**, not
  as empty: a member deark gave up on may have been given up on before
  the second fork was ever considered. 2,324 forks across the corpus.
- **The name in an error is not the member's raw name.** deark prints
  it MAKE_PRINTABLE, so `Icon\r` — the commonest filename on a Mac
  volume — arrives as `Icon<\r>`, which our sanitiser model turns into
  `Icon__r_` where the file on disk is `Icon_`. `deark_err_name()`
  reverses deark's escapes first (`reference/deark/src/deark-ucstring.c`,
  `ucstring_to_sz`). **382 declined forks across 35 fixtures were
  mis-keyed**, and none of them was live: in every one deark had written
  no file for that member, so nothing consulted the wrong key. What it
  would have cost with one live is the exact defect the rule above
  exists to prevent — a declined fork recorded as an empty one.

**And it does not fail on a damaged file — it PADS.** `sitdoc.sit` is a
MacBinary declaring a 286-byte resource fork in a file that ends 52 bytes
short: this engine writes the 234 bytes that are there and reports the file
truncated, `unar` says *"Attempted to read more data than was available"*,
and deark writes **286 bytes whose last 52 are zeros it made up**. An
oracle that always produces something is not ground truth about a file that
does not contain it. So deark fills a gap only where it cannot invent one —
when the fork is **empty**, which is an assertion of absence, or when the
entry's methods are all ones deark is the designated oracle for
(`DEARK_METHODS`, currently Distilled). Everything else it is offered is a
cross-check against a fork another implementation already graded. Lifting
that guard for one run put 52 invented zeros into a manifest and then
failed seven fixtures against them, which is how the padding was found.

**What this still cannot see:** deark credits macunpack **as
documentation** for method 6 and uses none of its code
(`reference/deark/modules/stuffit.c`), so on that method the two are
independent implementations but not independent readings — a transcription
error in either shows up, a misreading of the format shared with macunpack
does not. (The same caveat applies to `unar`, which is the primary
reference for everything else.) It does not read DiskDoubler, and it
fails whole-archive far more often than `unar` does, which is why it is the
third oracle and not the first. It DOES read Gzip, Compress and tar, which
this paragraph denied until 2026-09-22 — the sweep compares 164 forks of the
three tar fixtures alone — and given a `.gz` or a `.Z` it carries on into
whatever it finds inside.

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
- Do not read "unadjudicated: 8 forks" as 8 defects. It is **8 forks
  across 4 fixtures**, measured 2026-09-22, where two implementations
  cannot be compared: 4 in the PKZIP 1.x zips and `arcplus712.zip`,
  where unar failed the entry and Implode is outside v1 scope for us,
  so **both sides decline**; and 4 in the 1995 Now Compress archive,
  which the archive's own extractor has graded under emulation instead
  (`nowcompress.py --adjudicate`). It was **23 across 12** until deark
  was offered resource forks and the 6 empty ones of
  `derived-INTRECHO.pak` closed, **15 across 11** until the 8 in damaged
  MacBinary were graded from the container itself (*The container's own
  arithmetic*, below) — which took it to 7, and the eighth came back the
  same day when deark stopped asserting a resource fork is empty on an
  entry it reported a CRC failure for (*A third oracle*). Three files had recorded three
  different values for this tally — 16/10, 23/11 and the suite's own
  23/12 — which is the cross-file contradiction BLOCKERS.md names as the
  cheapest smell there is; the number `run_diff.py` prints is the one
  that is measured.

### Asking the third oracle about everything (`tools/sweep_deark.py`)

**`make_manifests.py` offers deark only what the others left open.** A
check positioned where nothing can contradict it cannot contradict
anything, and that is precisely how deark sat here for four weeks
without being asked about StuffIt method 6. This sweep asks it about
**every fixture that has a manifest**, and compares everything it
produces against every hash the manifest holds, from whatever oracle
put it there. It writes nothing: a disagreement is a finding to look
at, not a manifest edit.

    sh tools/build_deark.sh        # ./ci.sh's `make clean` deletes it
    tools/sweep_deark.py [--fixture NAME ...] [-v]

**2026-09-22: 4,556 graded forks across 728 of the 932 fixtures, 2,151
agree, 0 disagree.** The other 2,405 are three shapes that are not
disagreements, each of which the sweep names rather than counting as
agreement:

| verdict | what it is |
|---|---|
| `padded` | deark does not fail on a damaged file, it pads. A fork longer than the graded one, whose prefix hashes to it and whose tail is all zeros, is padding (`DEARK_METHODS`, above). **6** — and they are worth more than the label suggests: they are the six resource forks graded from the container's own arithmetic, so a second implementation reads the same bytes at the same offsets, stops where the file stops, and only then invents a tail. The arithmetic and deark agree byte for byte about what is present |
| `wrapped` | deark does not unwrap MacLHA's MacBinary payload: it writes the 128-byte header and both padded forks as one file where `unar` and this engine split them. Reported only after the container's own data fork is checked byte for byte against the graded one. **3** |
| `declined` | deark said it could not read this fork. **2,396**, nearly all of them StuffIt method 13 and StuffIt 5's Arsenic, which deark does not implement; 8 are the blanket for an error deark named a member but not a fork in (`synth-arc-mixed.arc`) |

That `declined` number was **18** until 2026-09-22 and the difference is
not a change of behaviour: 2,324 of those forks were being counted as
entries deark could not NAME. A member deark declines every fork of
writes no output file, `deark_forks` was built from output files alone,
so a member it named in an error and nowhere else was invisible — and
"invisible" was reported as the sweep's blind spot rather than as the
oracle saying *I do not implement this method*. Fixed where it belongs,
in `deark_forks`, so `make_manifests.py` sees the same thing (*A third
oracle*). It went up another **54** later the same day, for the same
reason one layer further out: the 27 StuffIt 5 entries below could not
be MATCHED at all while the manifests held a mojibake name, and once
the oracle was asked in the encoding those names are in, every one of
their forks turned out to be a decline too (DECISIONS.md 2026-09-22,
*a name an HFS volume can hold*).

**What it cannot see, and it prints this every run.** **10** entries
deark neither named nor declined are not compared at all, and each of
the four shapes is named:

| | |
|---|---|
| **7** Gzip and Compress | deark goes one layer FURTHER than the manifest describes: it decompresses the `.gz`/`.Z` and reads the tar inside it, so it writes `manual.txt` where the manifest — built with `unar -nr`, one container layer — records `synth-exo-gz-named` |
| **1** StuffIt 5 | `.typeAttributes.dict` in `derived-PuzzleGetter_0.8.sit`, whose forks are BOTH empty. deark names it and writes no file for it — `do_pre_decompress_fork` in `reference/deark/modules/stuffit.c` leaves both `fork_exists` clear when a fork's compressed and uncompressed lengths are zero — and `deark_forks` is built from output files. The only entry of that shape in the corpus |
| **1** uuencode | `synth-uu-mac.uu` stores its name with the quotes around it; `unar` strips them and deark keeps them, where its own sanitiser turns each into `_` |
| **1** ARC | `synth-arc-mixed.arc`'s method 7, declined in an error that names the member and not a fork — the over-cautious blanket, which costs 8 more forks in the same file on purpose |

**It was 49 higher until the Tar entries were looked at**, and what they
are is not what this file said. deark writes no AppleDouble sidecar
there: a tar member is stored as `./NAME`, `unar` reports it without the
`./`, deark keeps it, and deark's own sanitiser turns that slash into
`_` — so `./READ_ME` reaches the disk as `._READ_ME`, which looks
exactly like a Netatalk sidecar and is not one. None of the 49 files
deark writes for `derived-PCCTS.tar` carries the AppleDouble magic, and
each holds its own member's data. Matching the alternative name recovers
all 49 entries and **98 forks, every one of which agrees**. That alias
belongs to this sweep and not to `make_manifests.py`: the manifest
builder offers deark a fork only to FILL a gap, and tar has none —
`unar` grades every one of those entries.

**That 10 was 37 until the oracle was asked in the right encoding**, and
27 of the 28 StuffIt 5 entries counted here were a disagreement about
the NAME and not about any fork: those names are UTF-8 and the oracle
was pinned to MacRoman for every format alike (*Exact oracle
invocation*; DECISIONS.md 2026-09-22, *a name an HFS volume can hold*).
The 28th is the empty-fork entry above and was never about encoding —
a count attached to the wrong cause is what a shape-by-shape table is
for.

**A sweep is worth what its denominator is**, so the denominator is
printed per format, along with the entries whose mangled name another
entry claims — **0** today, and counted rather than silently skipped,
because a category that leaves no trace is a denominator nobody can
check. **4** forks nobody has graded are printed beside it: entries the
oracle failed on that no second implementation filled.

Not in `ci.sh`: it needs the fixtures, and it is an audit rather than a
test. It skips cleanly without them.

### The container's own arithmetic — not an oracle, the file itself

**A fourth adjudicator, and it is not an implementation.** Eight forks
in seven damaged MacBinary fixtures had nothing to be wrong against:
`unar` declines them, deark pads them, and our own output cannot grade
our own output. A MacBinary is a 128-byte header, the data fork padded
to a multiple of 128, then the resource fork, all of it stored — so
where a fork starts is arithmetic and what is in it is the file's own
bytes, and a file that ends early holds exactly as much as is
physically there.

`make_manifests.py`'s `adjudicate_from_macbinary` runs **last**, after
all three oracles, and records those forks as
`"MacBinary container arithmetic"`.

**It refuses to grade anything unless the arithmetic is confirmed on
the file it is applied to**, because the engine reads the same header
and would be wrong the same way. One of two confirmations is required:
the header's own **CRC-16/CCITT** over its first 124 bytes matching the
value at +124 (MacBinary II, so the lengths are checksummed — this is
`guysmaccontacts.sea`, where neither fork had an oracle), or the
entry's **other fork already adjudicated** and reproduced byte for byte
by the same arithmetic (the six MacBinary I fixtures). Where an oracle
and the arithmetic disagree on a file it grades nothing there and says
so.

**What this cannot see.** It says how much of a fork is present and
what those bytes are; it says nothing about the bytes that are missing,
and nothing at all about a compressed fork — every MacBinary fork is
stored, which is the whole reason this works and the reason it
generalises to no other format here. The layout itself is not assumed:
the same arithmetic reproduces both forks of **174 undamaged MacBinary
fixtures** with no mismatch. DECISIONS.md 2026-09-22, *the container is
the oracle*.

### When our engine declines an entry

A per-entry error from `macextract` is tolerated in exactly two cases, and
**both are the oracle's word, never ours**:

- the oracle failed that same entry (it is `unadjudicated`), or
- the oracle names the entry's compression method as one v1 does not
  implement — `oracle_methods` against `run_diff.py`'s
  `ORACLE_OUT_OF_SCOPE`, which today holds `Implode` and nothing else.

**One decline is deliberately NOT eligible, and must never be made so.**
An entry whose method byte says a StuffIt 2.x Optimizer ran fails
`UNC_ERR_MODULE` here, and the message ends differently on purpose:
`unar` 1.10.8 has no notion of that flag, decodes the method, writes the
PREPROCESSED bytes under the original's name and **reports success**
(measured 2026-09-28 on a synthetic three-entry archive — it declines only
the external-Compressor method, as *"File is not fully supported"*). So on
such a fixture the oracle and this engine would disagree and **this engine
would be right**; an excuse anchored to the oracle would excuse the wrong
answer. No corpus fixture produces one — nothing in 1,256 entries sets the
flag (FORMATS.md, *Where an archive names the module*) — so nothing rests
on this yet, which is the cheap time to write it down.

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

**A suite run by hand needs a `make` first, and `ci.sh` is why.** Its second
step is `make clean`, which is `rm -rf $(BUILD)` with `BUILD ?= build`; every
build after it is redirected to `build/san`, `build/ars`, `build/rel`,
`build/m32`, `build/off32` or cmake's `build/mac`, and **nothing ever rebuilds
the default target**. So a green `ci.sh` leaves no `build/macextract`, and the
next `tools/run_*.py --macextract build/macextract` has nothing to run.

Most suites say so — `no CLI at <path>`, exit 1 — and the ones that do not
raise `FileNotFoundError` before a single check, which looks nothing like a
suite that failed. That is what happened on 2026-09-01, in the two suites that
lacked the guard; both have it now, and it was briefly blamed on
`make_dist.sh` before either half was measured. **If a suite dies with a
traceback rather than a message, check for the binary before believing
anything about the suite.**

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
5b. **Application size** (`tools/check_app_size.py`, in `ci.sh` since
   2026-09-23): fails when the linked `MacExtract.code.bin` moves more
   than 2,048 B from a committed figure. Every byte is resident on the
   target, so a byte of code is a byte of heap a Macintosh does not have.
   **What it cannot see**: whether the move MATTERS. It compares one
   number and knows nothing about tiers — only `tools/run_tiers.py` can
   say whether a fixture flipped, which is why the failure message sends
   you there before raising the figure. It also cannot see A5 growth, or
   growth in a build without the Retro68 toolchain, where it skips.

6. **Fuzzing** (`tools/fuzz.py`): seeded, reproducible
   mutation/splice/magic-garbage cases through `macextract t` under the
   sanitizer build, plus three generators that exist because those
   three reach nothing on their own — a fourth (**2026-09-23**) that
   flips one to four bits in an encrypted archive
   `tools/synth_crypt.py` wrote and runs `macextract x -p` on it, a
   fifth (**2026-09-27**) that repairs the checksum it breaks in a Now
   Compress block, and a sixth (**2026-10-05**) that mutates a NAMED
   seed inside the ranges its generator calls compressed. Nonzero exits
   are fine, signals/sanitizer aborts/hangs fail. 4,000 cases at M9;
   every CI run does a 150-case smoke, a quarter of it the ciphers, in
   ~3 s.

   **One seed per cipher since 2026-09-26, and every one of the eight is
   reached.** `synth_crypt.py` writes nine shapes — StuffIt classic's
   DES, StuffIt 5's RC4, PackIt's XOR and DES, Compact Pro's, ARC's
   garble, PKWARE's zip cipher, and WinZip AES at 256 and at 128 bits,
   which is two shapes for one cipher because the key schedules differ —
   all of them in Python, with nothing installed. `zip -P`, `7z` and
   Debian's `arc` write three of them for real and are the ORACLES for
   those in `run_crypt.py`, but none can be the fuzzer's encoder: one
   seeds its encryption header from the clock, another picks a random
   salt, and the third is not installed here at all. A seed either of the
   first two wrote would make a quarter of a reproducible fuzzer
   unreproducible and its coverage conditional on what the machine has.
   Every shape goes straight back out to somebody else's reader — `unar`,
   `7z t`, or the application itself — which is what says they are
   archives and not plausible bytes (*Decryption*, below), and writing
   the ARC one found a defect in the engine's garble retry
   (DECISIONS.md 2026-09-26).

   Two things about how the cases are drawn. The seeds are taken **round
   robin**, not at random: a quarter of 150 is 37 cases over nine shapes,
   and drawing them would leave one shape untouched about a fifth of the
   time. And half the flips land anywhere in the seed while half
   land inside the bytes the reader hands to a cipher, which
   `synth_crypt.py --ranges` reports per shape — the container of an
   encrypted archive is worth fuzzing too, but a flip anywhere has to
   survive everything the container checks on the way in, and targeting
   the ciphertext raises every figure in the table below.

   **What it reaches** — `tools/fuzz_reach.py`, which plants an
   out-of-bounds store in one cipher's key setup, rebuilds, checks on the
   UNMUTATED seed that the fault actually fires, and counts the mutants
   that trip the sanitizer. Two cheaper instruments lied about this in
   2026-09-23: `macextract`'s exit code says nothing — a `t` run over an
   encrypted archive exits 0 having decrypted nothing, so "exit 0 or the
   word password in stderr" scored `sit-des` 31/40 when the truth was
   **0** — and `t` never descends into the MacBinary a StuffIt archive
   arrives in, which is why the crypt cases EXTRACT. 30 mutants a shape,
   seed 11, 2026-09-26:

   | shape | the site that is reaching it | flips anywhere | as shipped |
   |---|---|---|---|
   | `sit-des` | `unc_crypt_sit` | 19 | **26** |
   | `sit5-rc4` | `unc_crypt_rc4` | 21 | **27** |
   | `packit-xor` | `unc_crypt_packit_xor` | 17 | **21** |
   | `packit-des` | `unc_crypt_packit_des` | 17 | **21** |
   | `cpt` | `unc_crypt_cpt` | 20 | **29** |
   | `arc-garble` | `unc_crypt_xor` | 28 | **29** |
   | `zip-crypt` | `unc_crypt_zip` | 27 | **29** |
   | `zip-aes` | `unc_crypt_winzip_aes` | 27 | **30** |
   | `zip-aes128` | `unc_crypt_winzip_aes` | 23 | **29** |
   | `zip-aes` | `aes_encrypt_block` | 26 | **29** |

   The first column of figures is `--untargeted`, which mutates the way
   this did before the ranges existed; it is kept so that the before and
   the after come from one instrument. It also reproduces 2026-09-23's
   `sit-des` 19 and `sit5-rc4` 21 to the case — and **contradicts that
   run's PackIt 0**, which is withdrawn with what it cost (BLOCKERS.md,
   *Withdrawn claims*). The last row is a second site for the same seed:
   `unc_crypt_winzip_aes` runs before the password verifier is checked,
   so reaching it does not prove the cipher ran, and `aes_encrypt_block`
   is only on the far side of that check.

   **3,000 crypt-only cases and 2,000 mixed ones, clean** (seeds 101 and
   202, 2026-09-26, all nine shapes). Four of these ciphers had never been
   fuzzed at all and no mutant found anything in any of them — the one
   defect this work turned up came from WRITING a seed, not from mutating
   one (DECISIONS.md 2026-09-26).

   **And the same question for the DECODERS, answered 2026-09-27.**
   `tools/fuzz_reach.py` covers the ciphers a fault at a time;
   `tools/fuzz_cover.py` covers every decoder at once, because for a
   decoder "was this entered" is what gcov reports. 3,000 cases, seed
   11, engine sources only:

   | family | functions | never entered |
   |---|---|---|
   | StuffIt classic, StuffIt 5, PackIt, LZH `-lh1-`/method 5 | 23, 4, 6, 6 | **0** |
   | Compact Pro | 13 | 1 — `cpt_has_encrypted` |
   | Arsenic | 19 | 3 — `ars_index_*` |
   | ARC | 33 | 4 — `arc_crush_*` |
   | LZH container | 21 | 3 — `lzh_larc`, `lzh_preload`, `lzh_put_run` |
   | DiskDoubler | 24 | 4 — `dd_rle` (method 3), `dd_huffman` (4), `dd_stac*` (7) |
   | Now Compress | 13 | 6 — the coders and the block table |
   | **LZH `-lh2-`/`-lh3-`** | 16 | **16 — the whole file, never fuzzed**; **11 after the seed below** |

   **Every one of those is a method with no specimen in the corpus**,
   and the cause is structural rather than bad luck: three of the four
   generators mutate a corpus fixture, so **the fuzzer's reach is the
   corpus's coverage.** A method this project grades by GENERATING a
   file — `-lh2-`/`-lh3-` (`run_lzh.py`), DiskDoubler 3/4/7
   (`ddencode.py`), ARC's Crush — is graded for CORRECTNESS and fuzzed
   not at all. It is the cipher finding of 2026-09-23 again, in the
   other half of the engine, and it has the same remedy: a seed per
   method, the way `synth_crypt.py` seeds the ciphers.

   Now Compress is the one with a second cause worth naming: its
   archives ARE in the corpus, and its coders were unreached anyway,
   because the block table is gated by a 32-bit sum that a random
   mutation destroys (`now_tables`). **That is the gate that hid the
   one heap overflow this project has found in a decoder** — a length
   checked against `incap` where the buffer is `blkcap`, found by a
   crafted archive under ASan and never by a mutant.

   **A fifth generator answers that one, since 2026-09-27**, because
   more cases cannot get past a checksum and repairing it can: flip
   bits inside a block's PAYLOAD, then recompute that block's 32-bit
   trailer with `tools/mutate_now.py`'s own `fix_trailer` — the routine
   that tool uses to make changes a correct reader cannot notice. It
   takes a twentieth of the ordinary cases when the corpus holds a file
   for it (two do, under `corpus()`'s size filter). **Now Compress goes
   from 6 functions never entered to 1**, `now_find_delta`, reproduced
   at seeds 11 and 12 — and to **0 since 2026-10-05**, below.

   **That last one needed a seed, not more cases.** `now_find_delta`
   recovers a block table whose stored offsets are all off the real
   ones by a constant *while its checksum agrees with them*, and no
   mutation can grow that shape; neither corpus archive carries one.
   So `now_seeds()` writes three that do, with
   `synth_now.build_archive` — `synth-now-delta`, whose offsets are
   relative to their own table, `synth-now-delta-small`, short by 8,
   and `synth-now-delta-neg`, off by -64. The first two are the two
   routes a reader takes into that search: an offset that cannot be
   right at all, and one that has to fail a checksum first.

   Pure Python, like the `-lh3-` seeds, so the coverage is the same
   wherever this runs, and all three are archives `run_now.py` grades
   three ways against `unar` on every `ci.sh` run. **Now Compress: 13
   functions, 0 never entered, at seeds 11 and 12 over 3,000 cases** —
   the first family here with nothing left.

   `ci.sh`'s 150-case fuzz smoke grades the reader half as well: a seed
   with no blocks for the repair generator is a failure and not a skip,
   so deleting `derive_now.table_delta` turns `ci.sh` red — measured,
   not assumed.

   What that does NOT say: a mutant is graded by nothing, here as
   everywhere in this file. What is graded is the seed.

   **A sixth generator since 2026-10-05: a NAMED seed, mutated inside
   the ranges its own generator calls compressed.** StuffIt 5's method
   14 is the shape that wanted it. Its only specimen here is
   `synth_sit14.py`'s 1,859 B among ~950 fixtures, so what generators 1
   and 2 reach it with is a draw — none in 1,500 cases (DECISIONS.md
   2026-10-03), two or three in 3,000, which enter ten of the decoder's
   eleven functions and leave the nested-tree reader at zero at both
   seeds. `synth_sit14.py --ranges` reports its four streams, 1,345 B of
   the file against 514 B of banner and entry headers, and the generator
   keeps every edit inside them. 3,000 cases:

   | | seed 11 | seed 12 |
   |---|---|---|
   | of 11 functions, never entered, before → after | 1 → **0** | 1 → **0** |
   | `sit14_lengths_coded` (the nested tree) | 0 → **100 %** | 0 → **100 %** |
   | `sit14_tree` | 50 → **100 %** | 50 → **100 %** |
   | `unc_sit14_decode` | 92.5 → **95.5 %** | 89.5 → **95.5 %** |

   **Naming the seed is most of it; targeting is the rest.** Measured
   over 120 `--stream-only` cases, which is what a 3,000-case run
   spends on this seed anyway: `--stream-untargeted` — the seed named
   and mutated anywhere, i.e. what generator 1 does when it draws the
   file — reaches all eleven functions and 95.5 % of the entry
   function's lines, and targeting reaches **98.5 %** and takes
   `sit14_tree` from 94.4 to 100. Both flags stay, so the before and
   the after come from one instrument, the way `--crypt-untargeted`
   does.

   **It can fail, checked the way this repository checks.** The defect
   the ad-hoc targeted run found on 2026-10-03 — `sit14_build`'s code
   counter made signed, so a corrupt tree shifts it past 32 bits — was
   planted again and the whole instrument asked whether it would have
   caught it. **400 `--stream-only` cases: 11 failures. The old
   instrument at 3,000 cases and the same seed: none**, though it
   enters the decoder there. A mixed 3,000-case run finds it twice,
   which is the ~120 stream cases at the same hit rate. **`ci.sh`'s
   150-case smoke does NOT** — its 11 stream cases at that hit rate
   find a defect of this shape about a quarter of the time, and seed 7
   is one of the three quarters. The smoke is a regression guard; the
   figures here come from runs nobody does on every commit.

   **What the targeted mode cannot see** is now a branch and a line:
   the window-wrap half of `sit14_flush`, which needs a fork past 256
   KB where this seed's largest is 17,799 B, and the `goto out` on a
   failed flush, which is a sink write error and nothing a mutant can
   cause. Both are reached only by the two real payloads, which no
   committed suite can touch (FORMATS.md, *StuffIt 5's method 14*).
   The seed also arrives in ONE container, a bare `.sit`: method 14
   inside MacBinary or BinHex is fuzzed by nothing. And a mutant is
   graded by nothing — what is graded is the seed, which `run_diff`
   adjudicates against `unar`.

   **The twelve seeds `method_seeds()` already wrote had the same
   problem, and it was invisible**: they are in the POOL rather than
   named in the draw, so each is 1 of ~958 and drawn about 2.3 times in
   3,000 cases, which puts a tenth of the weight on never being drawn
   at all. That tail landed — `-lh2-`'s `lzd_*` set read 2 functions
   never entered at seed 12 and **16 of 16, the whole file, one
   reshuffle later**, the seed having been committed on 2026-09-27
   precisely to take that family off zero. Generators 1 and 2 now draw
   a named seed on **one case in 32** (`--named-share`; `--no-weight`
   is the old behaviour, and reproduces its runs to the case): each is
   drawn about six times, the corpus keeps 97 % of the draws, and
   `-lh2-` reads 1 — `lzd_reconst`, which wants 32,768 codes — at
   seeds 11, 12 and 13 alike.

   1/16 was measured too and buys nothing: the same families at the
   same counts at those three seeds, with a HIGHER total never-entered
   at all three (174/163/156 against 147/137/150). What none of these
   runs can say is whether the 3 % costs a corpus family anything —
   ARC reads 7, 11 and 18 functions never entered at 1/32 against 15,
   15 and 13 at 1/16, so its worst run is the cheaper share's and what
   moves ARC is the draw.

   **Two rows of the table above could not report, found while
   splitting it.** `^sit\d*_` put method 14's eleven functions inside
   "StuffIt classic", and a family of 34 cannot read as wholly at zero
   — which is the one signal this instrument calls reliable. So method
   14's state was unreadable here from the day it landed, at 1,500
   cases where the decoder was entirely unfuzzed and at 3,000 where one
   function of eleven is; the figures above come from a "StuffIt method
   14" row of its own. The BinHex row's regex named `hqx_`/`binhex_` where
   the functions are `bh_`: it matched nothing and printed no line at
   all, so twelve functions read as absent rather than as unmeasured
   for as long as the tool has existed. Both claims are withdrawn in
   BLOCKERS.md with what they cost. `fuzz_cover.py` now says how many
   engine functions fall in NO family — 381 of 581, the containers and
   envelopes it was never a claim about — so the next prefix nobody
   adds a row for is visible instead of silent.

   **How much of this table to believe.** The per-family counts are
   noisy: seeds 11 and 12 over an identical build differ by up to
   **thirteen** functions in a family — ARC 0 against 13 and StuffIt
   classic 8 against 1, measured 2026-10-05, where the same comparison
   on 2026-09-27 gave five at most (StuffIt classic 6 against 1, ARC 6
   against 10, Compact Pro 4 against 1). Those StuffIt figures were
   first recorded as 9 against 2, which was the row before method 14
   was split out of it; the eleventh function was at zero at BOTH
   seeds, so one of each nine and two was structure and not noise. **A single-run delta in a
   family is not a finding**, and one was briefly read as one here: a
   first cut gave the repair generator a sixth of the cases, the totals
   moved, and
   that was written up as starvation before a second seed showed the
   same swings with the weight unchanged (BLOCKERS.md, *Withdrawn
   claims*). What survives repetition is the whole-family signal —
   `-lh2-`'s `lzd_*` set is at zero at every seed, and Now Compress's
   6 → 1 holds at both.

   **`-lh3-` has a seed since 2026-09-27**, and it is the decoder half
   of what `synth_crypt.py` does for the ciphers: `fuzz.py`'s
   `method_seeds()` builds a six-entry `-lh3-` archive with
   `run_lzh.py`'s pure-Python encoder — deterministic, no binary, so
   the coverage is the same wherever this runs — and adds it to the
   pool the mutation and splice generators draw from. Re-measured, same
   3,000 cases and seed:

   | function | before | after |
   |---|---|---|
   | `unc_lzst0_decode` (the `-lh3-` entry) | 0 | **69.7 % of lines** |
   | `lzs_ready_made`, `lzs_block_head`, `lzs_decode_c`, `lzs_read_tree_c` | 0 | **100 / 85 / 73 / 72 %** |
   | `lzs_decode_p`, `lzs_read_tree_p` | 0 | **still 0** |
   | `unc_lzdyn_decode` and the `lzd_*` set (`-lh2-`) | 0 | **still 0** |

   **The rest of `-lh3-` followed on 2026-09-27, and getting there
   found a hole in the CORRECTNESS suite rather than the fuzzer.**
   `lzs_decode_p` was at zero on the UNMUTATED seed as well, which
   means no `-lh3-` stream this project has ever written contains a
   match: `lh3_stream()` Huffman-codes the 256 byte values and emits
   nothing above 255. The six graded cases are the only `-lh3-` files
   anywhere here, so **the decoder's whole LZSS half — `lzs_decode_p`
   and the copy loop — was graded by nothing** (BLOCKERS.md).

   `lh3_lz_stream()` writes matches, and LHa adjudicates it: `lh3()`
   extracts with LHa before it asks this engine, so a stream LHa reads
   back wrong is the encoder's fault. Four match cases joined the
   graded set, `-lh3-` entries going 6 to 10, and two seeds joined the
   fuzzer. With the seeds split one archive per case — a mutant of a
   ten-entry archive breaks an earlier entry and the walk stops, which
   is why a combined seed left `lzs_decode_p` at zero — every `-lh3-`
   function is now reached:

   | function | before | after |
   |---|---|---|
   | `unc_lzst0_decode` | 0 | **100 %** |
   | `lzs_decode_p` | 0 | **88.9 %** |
   | `lzs_read_tree_p` | 0 | **64.3 %** |

   **`-lh2-` is a COMMITTED seed since 2026-09-27**, `tools/seeds/
   lh2.lzh`, 4,896 B. It cannot be generated per run the way `-lh3-` is:
   only the patched LHa this repo builds on demand writes the method,
   and a reproducible fuzzer cannot depend on a binary that may not be
   built — so the bytes are in the tree and every machine gets the same
   seed. It is this project's own output, not a corpus fixture. To
   remake it: `sh tools/build_lha_lh2.sh`, then compress a
   repetitive text and 6,000 bytes over a 64-symbol alphabet with
   `lha ao2q10`, which gives two `-lh2-` entries, one match-heavy and
   one literal-heavy; LHa's own `t` verifies it and so does this engine.

   With it, **`src/unc_lzdyn.c` goes from 16 of 16 functions never
   entered to 1**: only `lzd_reconst`, which wants 32,768 codes — too
   large to sit in a fuzz seed, and already covered by the graded suite
   above. (`lzd_flush` shows coverage because the `-lh3-` decoder calls
   it too.)

   **DiskDoubler 3, 4 and 5 are committed seeds too**, the same day and
   for the same reason: `tools/seeds/dd-Rle2.dd`, `dd-HuffDeep.dd` and
   `dd-Splay128.dd`, written by `tools/vmac/ddencode.py --build`, which
   needs no emulator. No corpus fixture used any of those methods. They
   are round-tripped by this engine and, for the vendor's verdict, read
   by Salient's own 1991 expander (`ddencode.py --expand`).

   **Method 7 went a different way, and the difference is the point.**
   Those three seeds are files this project WRITES, so committing them
   is free. Method 7 is the Sigma Designs card's compression and
   nothing here can write it — but 24 specimens already existed, two on
   the 3.7 disk and 22 on the 3.1.2, and they are Salient's, which
   fixtures never are. So it became a FIXTURE rather than a seed:
   `dd37-IACUtilities-A4.lib.dd`, restored by a fourth `derived:`
   scheme in `harvest.py` — `derived:hfsvol:<image>:<mode>:<HFS path>`,
   which lifts one file out of an emulator disk image with hfsutils.
   Nothing copyrighted is committed; `SOURCES.md` carries the hash and
   the recipe, exactly as it does for the other 944.

   Two details that cost a run each. The mode letter matters: a
   DiskDoubler file must come off as the DATA fork alone (`r`), because
   MacBinary-wrapping it makes `unar` stop at the wrapper and report a
   1,356-byte `DD01` file — the manifest would then describe the
   container and never the contents. And the HFS path needs its leading
   separator restored after the recipe's fields are split, or hfsutils
   reads it as relative.

   With it, **DiskDoubler is at 0 functions never entered**, and the
   fixture is graded like any other: `unar` names its method `Stac LZS`
   and agrees with this engine on the 2,226-byte resource fork.

   **Its graded suite was asked the same question, and one path failed
   it.** Run under the coverage build, `run_lzh.py`'s `-lh2-` entries
   reach `unc_lzdyn_decode` and `lzd_decode_p` at 100 % — so unlike
   `-lh3-`, the match path was always exercised, the encoder being a
   real one. But **`lzd_reconst` was at zero**: the adaptive tree
   halves every frequency and rebuilds when the root's count reaches
   0x8000, which is 32,768 codes, and every subject was far short of
   it. A subject that crosses it is now in the set (`-lh2-` entries 15
   → 18) and `lzd_reconst` and `lzd_update_c` are at 100 %.

   **Two obvious shapes failed first, and both are worth knowing.** 48
   KB of incompressible bytes added no `-lh2-` entry at all — LHa
   stores what it cannot shrink as `-lh0-`. 80 KB of digits compressed
   and stayed `-lh2-`, but ten symbols make a three-byte match
   available almost everywhere, so the codes ran at roughly a quarter
   of the bytes and still missed the threshold. A 64-symbol alphabet
   does both at once: six bits of entropy a byte, so Huffman alone
   shrinks it, while a three-byte repeat is rare enough that the code
   count tracks the length. `lzd_update_p` stays partial — its own
   branch wants 32,768 MATCHES, which no subject here reaches.

   A 400-case run had far more at zero and most of it was sampling; the
   difference between 400 and 3,000 is how the two were told apart, and
   `fuzz_cover.py` says so rather than reporting one run as structure.

   **A constant the corpus never reads, found the same way**, 2026-09-28
   and recorded here because the method is the point rather than the
   format: `unc_lzah.c`'s window preload for `-lh1-` and StuffIt method
   5 was bent five ways and the whole differential suite run on each.
   The pattern and an all-spaces fill both give **933/933**; zeros,
   `0xAA`, and the pattern with only its trailing-spaces step bent all
   give 932/933, failing the one fixture that touches it at all
   (`derived-BitMap11.sit`, 29 method-5 entries). So the suite proves
   the window is not zero-filled and cannot distinguish XADMaster's
   pattern from lhasa's spaces — they agree exactly where anything
   reads. **Bending a constant and seeing whether anything notices is
   the only way to tell a load-bearing one from a decorative one**, and
   it costs a build each (DECISIONS.md 2026-09-28, *the preload nothing
   reaches*).

   **What none of this can see.** The reach figures are about EXECUTION,
   not about what the mutants explore once inside: one seed per cipher,
   none over 2.2 KB, so no keystream here runs long and no cipher's
   buffer handling is exercised at size. Each cipher is reached through
   ONE container — AES inside a spanned zip, or StuffIt's DES inside a
   BinHex envelope, is not covered. The instrument's only signal is a
   sanitizer abort, so a cipher that silently decrypts to the wrong bytes
   is invisible to it; that is `run_crypt.py`'s job, against `unar`, 7-Zip
   and Aladdin's and Compact Pro's own applications. And
   `fuzz_reach.py` is not in `ci.sh` — it rebuilds the engine once per
   site and takes minutes. What `ci.sh` carries is the result, which is
   this table.

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

**Nor can any fixture have the 1990 header**, added 2026-09-22: the low
word of the magic is the header's own SIZE, 48 rather than 84, and the
only specimen in existence here is the one `diskdoubler.py --beta` made
under Mini vMac — fixture archives are not committed, and `unar` cannot
open one to write a manifest from. So the differential suite does not
cover it at all. `ci.sh` carries the CONTAINER, in `test_diskdoubler`:
a 48-byte header over stored forks, so no codec is involved, plus two
negative controls — size 47, below the floor DiskDoubler ß05's own
validator enforces, and size 60, a size it WOULD accept and for which
nothing here knows the layout. Both must sniff UNKNOWN. What grades the
BYTES is `diskdoubler.py --beta-verify`, against what DiskDoubler was
given. **Established that it can fail**: those checks fail 7 ways
against the engine of the day before.

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

## The optimized StuffIt archives (`tools/run_sitopt.py`, in `ci.sh`)

**The writer is the oracle.** StuffIt Deluxe 2.0 could run an *Optimizer*
over a fork before compressing it, and for `Text 1` — leading spaces to
tabs, trailing ones stripped, the resource fork deleted — **nothing undoes
it**. So the right answer for such an entry is not the file that went in;
it is what StuffIt Deluxe 2.0.1 itself gives back, which is why the suite's
reference is `unstuffed.bin`, the output of that application unstuffing its
own archive under Mini vMac (`tools/vmac/sitopt.py --unstuff`).

Ten assertions over twenty-eight archives 2.0.1 wrote, in fourteen runs
— which between them are **everything that application writes with what
was in its box**: every Optimizer, every cipher, every compression
word, a 1.5.1-compatible archive, a folder, and a self-extracting
archive:

1. the control — same subject, no Optimizer — extracts to the subject,
   both forks, byte for byte;
2. the two optimized entries extract to **2.0.1's own unstuffed bytes**;
3. neither writes a resource fork, because `Text 1` deleted it and the
   header says `rlen` 0;
4. the header bytes are what `src/fmt_sit.c` reads: `0x40` set on both
   method bytes, 106 and 108 both 255, 46/47/107/109 zero;
5. **the declared lengths**, which are checkable without running
   anything: the `Text 1` entry declares the lengths of the fork it
   REWROTE, every module with an id left its control's lengths in the
   header;
6. **the other kind of Optimizer** — `MacPaint 1`, over a document
   MacPaint 2.0 itself drew — records its own module id, 4, and comes
   out at the declared length with the artwork byte-identical to
   MacPaint's own file AND to 2.0.1's unstuffed output, a header of 512
   zeros, no resource fork, and the user TOLD; its control extracts byte
   for byte. `Sound 1` (id 1) and `Photoshop 1` (2) come back byte for
   byte against the subject, both forks, and the run says nothing about
   them, which is asserted too; the synthetic `JPEG Lossy` (3) entry is
   the one the module could not encode, and must be refused rather than
   invented;
7. **`JPEG Lossy` over two documents Photoshop 1.0.7 itself wrote**
   comes out **byte-identical to 2.0.1's own restored file**, with the
   resource fork identical to the ORIGINAL document's — which 2.0.1's
   output is not — and the user told. It must NOT equal the original
   data fork: that would mean a lossy module had given back what it
   threw away. The second document is a dense grid and is graded for
   one reason: it puts the output stage's negative branch on 9,645
   bytes against the first one's 2,127, so a decoder that regains
   `CCOD`+0x3826's round-toward-zero correction fails it four times as
   loudly (BLOCKERS.md, *Withdrawn claims*). Measured 2026-10-02 by
   putting that correction back: 2,127 and 9,645 wrong, both sections
   failing. A THIRD archive is the same subject at **Q=50** rather than
   the module's default 25, whose quantisation tables are Annex K
   unscaled where the default's are half of it — the only specimen that
   can fail a decoder which assumes the tables instead of reading tag
   33606, and it is asserted to differ from the Q=25 archive so that a
   quality which silently did not take is a failure too.
8. **Every cipher StuffIt 2.x has.** `DES` and `DESex` (standard DES
   in CBC), `NewDE™` and `NewDEx` (StuffItDES in CBC) and `PassLock`
   (no cipher at all) each stuffed over one `Subject`, with a plain
   archive of the same subject from the same boots — so the control IS
   the plaintext and the suite grades BYTES, not the absence of an
   error. A wrong password must still be refused by the four real ones
   and must not be asked for by `PassLock`. Swapping the two primitives
   in `unc_crypt.c`, or the two modules' ids in `fmt_sit.c`, makes four
   and two assertions fail respectively — measured 2026-10-02.
   `PassLock` in particular: an entry it protected must extract
   **without a password**, come out byte-exact, and the run must say
   **nothing** about the password — the protection is nominal, there is
   nothing a user can act on, and the suite asserts the silence as well
   as the bytes. Two archives: one that is ALSO `JPEG Lossy`-optimized,
   where the Optimizer's loss must still be reported because that is
   about the bytes, and a text file stuffed twice in one boot,
   protected and plain, whose extractions must be identical. Removing
   the pass-through makes the first fail with *"wrong password, or none
   given"*, with a password *"archive structure is corrupt"*, and the
   text pair refuse — measured 2026-10-02, which is how this one is
   known to be testing something.

**Where the split came from.** Aladdin's own Engine, asked to unstuff
both, decoded the `Text 1` archive and refused the `MacPaint 1` one —
*"Items that were encrypted or compressed with an optimizer or
compressor will be skipped… Please use StuffIt Deluxe instead."* That is
graded here as a fact about the Engine; this engine refuses neither, and
says instead which entries are not the file that was archived.

**What it cannot see.** Whether a `DCMP` and this engine agree on
anything but these nine archives. All four reversible Optimizers are
undone in `src/fmt_sit.c` and this suite grades the RESULT — byte for
byte against the subject for `Sound 1` and `Photoshop 1`, and against
2.0.1's own unstuffed output for `MacPaint 1` and `JPEG Lossy` — but
only over the SETTINGS this project asked 2.0.1 for — which since
2026-10-02 is two subjects, two qualities, every compression method the
script language has, and both with and without `PassLock`. What is left
unseen is `Custom Compression…`, the one method with no script word,
and the two encryptor modules this machine does not have (`NewDE™`,
`DES`). The archives
themselves are not synthetic — 2.0.1 wrote every one of them — so what
is unseen is coverage of its options rather than authenticity of its
output. Two SUBJECTS are part synthetic, which is a
different gap: `Sound 1` wants a Sound Designer II file and got generated
samples, and `Photoshop 1`'s resource fork was built to the acceptance
test in the module's own `COMP` — so those two show what a module does
once it accepts a file rather than that a real document looks like that.
`JPEG Lossy`'s subject is a real Photoshop 1.0.7 document and is the one
exception. And it says nothing on a fresh clone: the specimens are emulator output and are
not committed, like `sitcrypt.py`'s, so the suite skips cleanly when they
are absent.

## StuffIt method 14 (`tools/synth_sit14.py`, in `ci.sh` via `run_diff`)

**The format had no fixture and no suite could ask for it.** Method 14
appears in no corpus archive: the two that settled the decoder are
Aladdin's own installer payloads, 6.6 MB and 12.4 MB, neither committable
nor restorable by `harvest.py` (FORMATS.md, *StuffIt 5's method 14*). So
`tools/synth_sit14.py` writes the shape instead — an ENCODER for the
format, from the same reading of libxad's `SIT_14` — and
`fixtures/synth-sit14.sit` (1,859 B) is graded against `unar` by
`run_diff` like every other fixture, on four entries chosen one per
shape: literals across two blocks, the shortest match the ladder can
state at the overlapping distance 1, extra bits on both ladders plus the
**longest match the format can code** (16,387 B), and a **nested tree**
— the code lengths themselves Huffman-coded, which is what 524 of the
7.0.3 payload's 1,132 tree reads do.

**Three implementations agree on those bytes**: the Python encoder, this
engine's decoder, and `unar`. That is what makes the fixture evidence
rather than a round trip through our own reading — and the agreement
caught the encoder's first version, which wrote a repeat count without
the escape value in front of it.

**It can fail**, checked the way this repository checks: bending the
match-length base by one byte in `src/sit14.c` fails this fixture and
only this fixture, 31/32 (2026-10-03). Which also says that **no other
fixture covers method 14** — if one did, the bend would have failed two.

**Robustness.** `run_robustness.py` takes the fixture with everything
else, so ten truncated and bit-flipped variants of it run under
ASan+UBSan on every `ci.sh` run. **What that cannot see:** most variants
of THIS fixture never reach the decoder — the 80-byte StuffIt 5 banner is
4 % of a 1,859-byte file, so a whole-file mutation usually lands in it
and the archive is refused as unrecognised, and a mutated length field
is refused on the allocation budget.

**In `fuzz.py` since 2026-10-05**, as the stream generator: the same
archive rebuilt as a NAMED seed and mutated only inside the four spans
`synth_sit14.py --ranges` calls compressed, which is about 110 cases of
a 3,000-case run. It reaches every function of the decoder and every
line of it but the window wrap and a sink-write failure, at seeds 11 and
12 alike (*Fuzzing*, above, for the figures and for what it still cannot
see). The 2,000-mutant run that measured this first is what found the
decoder's one real defect — a signed left shift in the canonical code
assignment, UB on a corrupt tree (DECISIONS.md 2026-10-03) — and a
pre-existing leak in the CLI's own name-cut notice.

**Big-endian, and on the machine.** `tests/run_mac_sink.sh` carries the
fixture since 2026-10-03, so the decoder also runs under qemu-m68k
through the Mac shell's own sink on every `ci.sh` run — the target it
was written for, and the only lane that runs it big-endian. That one can
fail too: the same bent base fails `mac-sink` on this fixture and on no
other. The application itself ran it on four emulated tiers the same
day (FORMATS.md, *Run on a Macintosh*).

**What none of it sees:** the two real payloads, which no committed
suite can reach. They are re-run by hand, and the figures and what
adjudicates them are in FORMATS.md, *StuffIt 5's method 14*.

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
- **It only covers encodings our encoder emits** — which since 2026-08-29 is
  most of the space, because that was the thing to fix. `--expand` now writes
  twelve forks rather than five: method 5 at all four counts its own validator
  allows, a method 4 tree with a leaf at depth 1 and leaves at depth 10, and
  method 3 at run length 2. All byte-exact through the 1991 expander
  (FORMATS.md, *What the 1991 expander accepts*). A method 4 stream whose
  Huffman root is a LEAF still has no case — `enc_huffman` adds a second
  symbol rather than emit one — and is checked by hand only.
- **`ESC 1` is the one the two references disagree about, and the vendor
  broke the tie.** `XADRLE90Handle` calls it an error, macutils emits no
  repeat, and this engine followed macutils until 2026-08-29 — alone among
  its six RLE90 call sites. Salient's own 1991 expander refuses such a fork,
  at offset 0 and mid-stream; `dd_rle` now passes `strict = 1` like the other
  five, and all 91 DiskDoubler fixtures are unchanged (BLOCKERS.md). A fork
  opening with `ESC`, which no compressor can legitimately emit, yields zeros
  from a deterministic `last = 0` rather than macutils' uninitialised read.
- **A fork whose compressed size exceeds its original is refused by the 1991
  expander**, measured with a control that uses no token an accepted fork does
  not (`RleGrow`). It is why the first `ESC 2` run read as a codec
  disagreement and was not one.

**Only `--emit` runs in `ci.sh`, and the rest of the file rotted behind it.**
`build()` and the verification half of `expand()` call `header`, `cli` and
`describe` from `diskdoubler.py`; a later refactor moved that import into a
deferred helper and dropped the three, so both modes had raised `NameError`
from their first line since — with the emulator results they had already
produced still standing in FORMATS.md. Repaired 2026-08-28. A harness nobody
can run is a claim nobody can re-check, and the mode `ci.sh` exercises is not
the mode that grades anything.

**Five subjects since 2026-08-28, and one of them passes by being refused.**
`Splay128` is method 5 with a tree-count byte of 128, which Salient's own 1991
expander turned back into the subject byte-exact; `Splay16` carries a count of
16, which that expander's validator rejects before decoding a bit, so a
refusal is what this case asserts. Which values are legal — 32, 64, 128, 256 —
was read out of the expander itself rather than guessed (FORMATS.md, the
method table; DECISIONS.md 2026-08-28, the tree count).

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

The Arsenic decoder picks between a 3-bytes-per-byte transform table and a
sampled occurrence index **by trying to allocate the table and failing**
(DECISIONS.md). Nothing an unconstrained run does reaches the fallback, so
CI forces it three ways:

- `-DUNC_ARS_FORCE_SAMPLED` compiles the fast path out. The whole
  933-fixture diff suite and all 9,320 robustness variants run through the
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

## The LZW string length — a build at `UNC_LZW_LEN_MAX=4`

Since 2026-09-19 `unc_lzw.c` stores each symbol's string length in one
byte, saturating at 255, and `lzw_strlen` walks up the parents to
recover the exact figure when it has. **Nothing in the corpus reaches
that walk**: the longest string anywhere, over all 113 fixtures that use
the decoder, is 223 bytes (measured with an instrumented build). So
`ci.sh` builds a variant with the saturation point at 4, where nearly
every string takes it, and requires it byte-exact:

    make BUILD=build/lzwlen CFLAGS="... -DUNC_LZW_LEN_MAX=4" all

**It was shown to test something.** Breaking the resolving walk by one
token (`n += len[s]` to `n += 1`) leaves the default build byte-exact on
all 113 fixtures and makes the `LEN_MAX=4` build differ on 112 of them.
Without that demonstration the variant would be a minute of CI proving
that a path nothing enters still does not.

What it cannot see: the corpus has one ARC fixture that reaches LZW, so
the re-walk that hands a long string over in pieces — ARC reads through
a 64-byte buffer — is graded on 46 splits in `synth-arc-mixed.arc` and
on whatever `tools/run_arc.py` generates, not on a real archive with
long strings.

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

**Chained documents** since 2026-08-27, uuencode having become an
envelope: a plain document and a UUTool document each holding a
MacBinary file must yield the file inside it and no wrapper, `-nr` must
stop at the wrapper, and a file of TWO documents must not chain at all —
that last is the guard the newsgroup shape rests on, so it is asserted
rather than assumed. All four were run against a build with uuencode
taken back out of `env_is_envelope`: the two chained cases fail there,
and the `-nr` and two-document cases are controls that pass either way.

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

And since 2026-08-27 the **chain**, which is the shape a real one has:
the reference encodes a MacBinary file, the CLI has to write what was
inside the wrapper and delete the wrapper, in both framings, and `-nr`
has to stop at the wrapper. Three cases; the two chained ones fail against a
build with btoa taken back out of `env_is_envelope`, and the `-nr` one
is the control that has to pass either way (DECISIONS.md 2026-08-27).

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

65 cases. The base64 half: four lengths around a group boundary (the
last group padded with none, one or two `=`), every byte value, a
one-byte file, two documents in one file, and the same document with
CR, LF and CRLF line endings. The MIME half: a single base64
attachment, a multipart with a note and two attachments, a
quoted-printable part, an unencoded part, a part with no filename at
all (`part1`, which is what munpack calls it), an LF-only message —
and **multipart/appledouble**, both forks, the type and creator, the
resource-only case with no data part, and one nested inside a
`multipart/mixed`.

**A document pasted into a part** (2026-08-29) is six of those cases:
a multipart holding a uuencoded part AND a base64 attachment, where
munpack is the oracle for the attachment the uu part used to hide; the
same message with `Content-Transfer-Encoding: x-uuencode`, which
neither implementation knows; a multipart whose only part is uuencoded,
which decoded before the sniff order changed and says the change cost
nothing; a pasted BinHex document, kept undecoded and recognised as
BinHex when handed back; a note that merely begins with the word
"begin"; and a uuencoded POSTING, which has no boundary and still
sniffs as uuencode. Each of the first three and the BinHex one was run
against a build with `unc_mime_probe_multipart` removed from
`unc_sniff` first, and fails there — an established failure, not a
green tick.

**`message/partial`** (2026-08-29) is nine more, and the only ones
where BOTH ends are somebody else's: `mpack -m 4000` writes the
multi-file set and munpack reassembles it, so what is graded is that
this engine joins the same parts into the same bytes. The set is joined
from part 1, from a middle part and from the last; a set missing a
middle part is refused with nothing written; two sets in one directory
do not mix, because the parts are placed by the `id` they repeat and
never by filename; a `multipart/appledouble` split across files comes
out with both forks; and a set that carries `total` only on its LAST
part — which is all RFC 2046 requires — still joins. Six of the nine
were run against a build with `unc_mimeseg_probe` removed from
`unc_sniff` and fail there.

Two things about munpack as an oracle for this, both of which cost a
run: it reassembles through a FIXED directory, `/usr/tmp/m-prts-$USER`,
which it does not create; and it creates that directory's `CT` file
with `O_EXCL`, so a part after the first dies with *"CT: File exists"*
unless it is removed in between — mpack failing to round-trip with its
own twin (DECISIONS.md 2026-08-29). The harness does both, and where
there is no writable `/usr/tmp` it says the comparison was skipped and
still grades this engine against itself.

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
| `unar` | XADMaster, which `src/fmt_lzh.c`'s HEADER WALK is transcribed from — but not its decoders, which have been lhasa's since 2026-09-19 | on the walk, a transcription error and nothing else; on `-lh4-` .. `-lh7-` and LArc, a wrong reading that lhasa shares |
| `lhasa` | an independent implementation, compiled out of `reference/lhasa` — and, since 2026-09-19, the source the decoders are written from | on the walk, a wrong reading that XADMaster shares; on the decoders, a transcription error and nothing else |
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

Added 2026-08-25, extended 2026-08-27. A zip counts its entries in 16 bits;
past 65,535 the count lives in a Zip64 record. A reader that trusts the 16-bit field does not fail
on such an archive — it walks 65,535 entries and reports success, which is how
a 70,000-entry zip lost 4,465 files silently until that date (FORMATS.md,
*Size limits*).

The corpus cannot reach this: **the largest zip in 937 fixtures has 29
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

Four more cases were added 2026-08-27, for the OTHER Zip64 structure — the
per-entry escape, which arrives at 2 GB rather than 4 (FORMATS.md, *Size
limits*). `offsets.zip` is a single **sparse** subject holding one entry just
under 0x80000000 and three past it, so it costs a few kilobytes of disk; the
generator asserts that it straddles the boundary, and CPython's `zipfile`
grades the construction — the names, the payload behind the hole, and that the
entries past the boundary carry a Zip64 field while the one under it does not.
Every entry must then verify under `t`. The remaining three are synthetic and
cost nothing: an escape whose value is small and honest must extract as if it
were not escaped, and an escaped position or size whose high half is set must
refuse **that entry alone** and leave the walk and its neighbours intact.

**Established that it can fail**: against the previous commit's `fmt_exo.c`,
six of the nine cases fail — the 65,536 count, the past-4-GB locator, and all
four of the per-entry cases, three of them as `UNC_ERR_CORRUPT`.

**What it cannot see.** No subject here is over 4 GB, and the only large one
is 2 GB of hole: the read path over a multi-gigabyte entry is not exercised,
and the over-4-GB refusals are reached by writing a high half rather than by
building an archive that has one. Sizes are the next suite's subject. Skips
the offset cases politely where the filesystem has no sparse files.

## Size limits (`tools/run_sizelimits.py`, in `ci.sh`)

Added 2026-08-27. Two boundaries live here and they are not the same
boundary: a MEMBER over 2 GB cannot be extracted, and a POSITION past
`unc_off_t` cannot be addressed at all. Until that date the first behaved
like the second — one oversized tar member ended the whole walk, losing every
member behind it (FORMATS.md, *Size limits*).

**Since 2026-08-28 the second boundary depends on the build**, so the suite
asks the binary rather than assuming: `--version` reports the width derived
from `sizeof(unc_off_t)`, and the over-4-GB case expects a truncated walk at
32 bits and a complete one at 64. Being TOLD the expectation by `ci.sh` would
have been weaker — the binary is the thing that knows. That case caught the
first `UNC_OFF64` build precisely because it had been written against the
32-bit ceiling.

The subjects are generated, because nothing in the corpus is remotely this
large, and **sparse**: an oversized member is a hole, so a 4.5 GB archive
costs a few kilobytes of disk and no time. They are graded by **GNU tar**,
which has none of these limits and therefore states the member list each
subject is supposed to have.

Four cases: an oversized member between two ordinary ones (all three listed,
the big one refused per entry, both small ones out byte-exact and the archive
exiting non-zero); the boundary from both sides, 2 GiB − 1024 listing a size
and 2 GiB (0x80000000) listing `?`; and — so the two limits are not confused
— a member whose POSITION passes 4 GB, which still ends the walk with
`UNC_ERR_CORRUPT`.

**Established that it can fail**: against the previous commit's `fmt_exo.c`,
three of the four cases fail.

**What it cannot see.** The holes are never read, so the read path over a
multi-gigabyte entry is still unexercised — on the Mac target it is
unreachable anyway, since HFS caps a fork at 2 GB. Skips politely where there
is no `tar` or no sparse files.

## Both offset widths (`ci.sh` variant 5, added 2026-08-28)

`unc_off_t` is 64-bit in the host build and 32-bit in the Macintosh one, so
there are two engines and they cannot share one grading. Variant 5 builds the
**32-bit** configuration — `make OFFDEFS=` — under the same sanitizers as
variant 1 and runs the unit tests, all 933 fixtures against the oracle, the
9,320 robustness variants and the size limits through it. The lanes above it
cover the 64-bit default.

Width is a compile-time choice and not an architecture, which is the whole
reason this is possible: the configuration that ships to a 68000 builds and
grades on Linux. Without this lane the shipped Macintosh width would be the
one nothing runs, and two widths would not be defensible (DECISIONS.md
2026-08-28, *what a width costs*).

**Established that it can fail**: the lane asserts `--version` reports
`offsets: 32-bit` before running anything, because `make` tracks timestamps
and not flags — a stale `build/off32` would otherwise re-grade the default
width and pass for the wrong reason.

**What it cannot see.** Only the two widths that exist; nothing checks that a
third would work. And it grades the 32-bit ENGINE on x86-64, not on a 68000 —
that is the Mini vMac tier's job, where both widths ran 69/69.

## Over-long names (`tools/run_names.py`, in `ci.sh`)

Added 2026-08-27. Two caps meet a name — the engine's `UNC_NAME_MAX`
(255) and the filesystem's `pathconf` answers — and until that date the
first cut names with nothing said, so a 457-byte path extracted under a
name that was not the archive's (FORMATS.md, *Name limits*).

The subjects are generated because **the longest name in 937 fixtures is
120 bytes** — under half the engine's cap, so neither the differential
suite nor its variants could reach either limit. They are graded by
CPython's `zipfile` and `tarfile`, which wrote them and have no such
limit, and by `unzip -l` and `tar tf` where those exist.

Fifteen cases over seven carriers, the allocator's budget and the output
directory: a zip whose long
entry is extracted under the shortened name while the entry beside it is
untouched; two zip entries that differ only past the cut, which must both
come out with the second numbered `~1`; the engine's cap from both sides,
255 written whole and 256 shortened; a tar whose ustar `prefix + '/' +
name` states 256 bytes; a uuencode `begin` line, cut by a 96-byte line
buffer before the cap is reached; an AppleSingle whose 200 MacRoman bytes
are 400 of UTF-8, which the engine carries whole and one directory entry
cannot take; and the output path from both sides — a legal 1 KB directory
that must be written to, and one past `PATH_MAX` that must be refused.
That last subject is built by walking into it, because the kernel will
not take a path that long in one `mkdir` either.

Each case also asserts what the NOTICE says: the archive's own name in
full where the format still held it — `collide.zip`'s two names differ
only past the cut, so the notice is the only place they can be told
apart at all. A ninth case reaches the other side of that: a zip whose
central directory does not fit a 64 KB budget is read a record at a
time, the name really is gone, and the notice must give the length and
say so rather than present the shortened name as the archive's.

The fifth carrier is the Macintosh shape of the same defect, added the
same day: a path that reaches the cap by SUMMING rather than by holding
one long name. `tools/synth_now.py` writes a nine-deep tree of 31-byte
components — 296 bytes, and no name in it remarkable — and the notice
must carry every byte of it. `lsar`, which has no such cap, is asked for
the same path. What this grades for Now Compress is `unc_path_leaf`,
which DiskDoubler and SuperDisk! also run.

**SuperDisk! reaches that helper through its own walk since 2026-09-01,
and it is the case here with no oracle on this machine.** `tools/synth_sd.py`
writes a ten-deep stream — declared paths 43 to 331 bytes — out of a corpus
archive's own folder and file records and its own method-7 blocks, so the
only thing in it this project invented is the nesting. Nothing off the
Macintosh reads the container, so the verdict it replays was taken on the
emulator: the format's OWN self-extracting application, given a data fork
built by that script (`tools/vmac/superdisk.py --nest`). That machine makes
each component through the File Manager and never assembles a path, so what
it built IS the uncut path, and it agreed on all eleven files. The case is
skipped, not failed, where the fixture is absent.

The sixth is DiskDoubler, added 2026-08-28, and it is there for the
header walks rather than for the helper: the four real `DDAR` archives
are flat and the five real `DDA2` ones hold one folder at one level, so
`DDAR`'s isdir/enddir records and `DDA2`'s dirlevel counter had never
descended anything. `tools/synth_dd.py` writes both containers — the
archive-header CRC-16/XModem included, without which `unar` does not
recognise the file at all — and each walk gets two archives. A TREE
(folders inside folders, a file after a folder closes, one at the root
after that, a resource fork, and `DDAR`'s stored-in-the-record shape),
whose every path and every fork must come back, and which `lsar` is
asked to walk as well. And a DEEP chain of the longest component the
format has, 63 bytes for `DDAR` and 31 for `DDA2`, sized so the folder
above the leaf lands on EXACTLY 255: the folder is then the longest path
that fits, the leaf under it is cut onto the folder's own path, and what
saves the file is the `~1` numbering.

**And what these archives were NOT, until 2026-09-22.** A `DDAR`
record's `+74` is the entry's whole span — the field a walk steps by —
and `synth_dd.py` was writing the uncompressed data fork's length
there, with the resource fork's length at `+78` where DiskDoubler
writes 0. Nothing read either, because the walk stepped by the file
header's own arithmetic instead, so both were free to be wrong. What
found it was an archive **DiskDoubler's own Combine command** wrote
(`tools/vmac/diskdoubler.py --combine`), and what proved it mattered
was this suite: the engine changed to step by the span and these
eighteen assertions failed at once. They say what the encoder says
now.

**Established that it can fail**: against the engine and CLI of two
commits earlier, nineteen assertions fail; the nested-path case fails
three ways against the commit before it, including a reported length of
287 bytes for a 296-byte path. The DiskDoubler cases were failed the
same way, by breaking the generator rather than the engine: dropping
every `DDAR` enddir record fails five assertions, squashing the `DDA2`
dirlevels fails five, and both mismatches are seen by `lsar` too.
Shifting every `DDA2` dirlevel by one fails NOTHING, and correctly —
the walks compare levels only with each other, so a uniform shift is
the same tree in both implementations.

**What it cannot see.** Whether DiskDoubler itself writes the trees the
generator writes: both readers agree on what the records mean, and only
a deep archive written by DiskDoubler would say the records are what it
would have written. SuperDisk!'s header walk still never reaches the cap
here — no fixture nests that deep, and nothing off the Macintosh reads
that container to grade a generated one (OPEN_ITEMS.md). The Mac
application consumes none of it and says nothing on screen; what it does
instead is graded in the next section.

## The tiers a budget predicts (`tools/run_tiers.py`, in `ci.sh`)

**A small Macintosh's memory result, measured on Linux in five seconds.**
The Mac shell's allocator is a running total against a cap and refuses
per entry; `macextract --budget N` is the same rule, so the whole
71-fixture sample can be swept at a tier's measured budget without an
emulator, a ROM or an X server.

    tools/run_tiers.py --check                 # what ci.sh runs: both lanes
    tools/run_tiers.py --tier sys3-512K        # one tier, with shortfalls
    tools/run_tiers.py --tier sys3-512K --shipped     # the 'OVLY' build
    tools/run_tiers.py --budget 102328         # any cap

Not to be confused with `tools/run_budget.py`, the older half of the
pair: that one sweeps the whole CORPUS at a single cap and reports per
format (layer 5 above). This one sweeps the Mac SAMPLE at each tier's
own budget and asserts the tallies.

**Two lanes, and `--check` runs both.** The RESIDENT lane sweeps one
budget per tier, which is what the control build (`UNC_OVL_RESIDENT=1`)
has; the SHIPPED lane sweeps one budget per tier PER FORMAT, which is
what the `'OVLY'` build has, and per LAYER, because the shell re-takes a
budget for every envelope layer. Neither replaces the other: the first
grades the engine's allocation behaviour against a fixed ceiling, and
the second predicts what a user's Macintosh refuses.

The resident lane asserts every tally Mini vMac agreed with for that
build, which since 2026-09-22 is all three: **71/71 at the 1 MB floor
target** (653,532 B), **67/71 on a 512 KB Macintosh under System 3.0**
(224,644 B) and **64/71 on the same machine under System 6.0.8**
(129,244 B) — the same four and seven fixtures, by name, that the
machines refuse. All three budgets were re-taken twice on 2026-09-27 — +4,746 B
and then +536 B, the three moving together each time — and no tally moved
(FORMATS.md, *Budget*). The fourth arrived 2026-09-22 with
`derived-Cool_Tools__.sit`, which needs 242,464 B; the third tier became
assertable the same day, when its budget was re-taken. A tally that moves is
a memory regression or a memory win; either way the number in `EXPECT`
is meant to be changed deliberately.

The shipped lane asserts all three tiers a machine has run — **71/71 at
the floor target, 69/71 at System 3.0 / 512 KB and 66/71 at System 6.0.8
/ 512 KB** — and it asserts the REFUSED FIXTURES BY NAME rather than a
tally, because a tier that refuses two different fixtures and still
counts 69 is exactly what a count cannot fail on. The third joined
2026-09-27, and it is the one this lane PREDICTED before any machine ran
it (FORMATS.md, *512 KB machines*). Its budgets are not constants: the
keep set is parsed out of `mac/ovl_load_eager.c`, the format names and
envelope flags out of the engine's table, the image sizes are checked
against `build/mac/` whenever Retro68 is installed, and since 2026-09-27
`OVL_SAVED` is checked against `build/mac` and `build/mac-resident` the
same way — `--check-saved`, which `ci.sh` runs after the control build,
because that constant had gone 32 B stale with FORMATS.md corrected and
`run_tiers.py` not (FORMATS.md, *What each format is granted*;
DECISIONS.md 2026-09-26, *a budget per format, and one per layer*).

**What it cannot see** (and why the emulator tiers stay):

- **The budget's own currency, which is the limit that has actually
  bitten.** Each figure is `FreeMem() - 20,480` measured on the machine
  (FORMATS.md, *Budget*), so it moves when the application's size does,
  and this file cannot notice. **All three were stale on 2026-09-22** —
  the two 512 KB constants by 21,666 B each — and re-taking them is what
  made this file reproduce every tier. The shipped lane inherits every
  one of them, since a per-format budget is one of these plus what the
  release gives back.
- **Whether a Compact Pro or zip archive holds an encrypted entry.** The
  shell asks `unc_archive_encrypted` and drops the ciphers on a definite
  NO; that walk is not reachable from the CLI, so the shipped lane keeps
  them for those two formats always and grants 9,808 B less than the
  machine does. It decides nothing: the narrowest margin on any Compact
  Pro or zip layer in the sample is 147,262 B, re-measured 2026-09-27.
- **Fragmentation.** A budget is one number; the Memory Manager also has
  to find one PIECE that big, which the shell reports separately
  ("Memory is too broken up"). Nothing here models it. **No disagreement
  currently rests on it.** The System 6.0.8 / 512 KB gap that was filed
  here as "the likeliest reason" — 59/69 against the machine's 58, then
  61/71 against 63 — was the stale budget above, entirely: with the
  budget re-taken this file puts that tier at 64/71 and names the same
  seven fixtures the machine refuses. The hypothesis that replaced it —
  *this tier's constant predates the stack cut* — was the right one, and
  one `-D UNC_AT_BUDGET` boot settled it.
- **68000 struct sizes.** `derived-a2basic.dmg.sit` holds 37,356 B
  before its block here and 37,372 B there. Tens of bytes — but a
  fixture that missed by twenty would not be decided by this.
- **Everything that is not memory**: names, CRCs, the File Manager, the
  interface. Those are `tools/vmac/run.py`'s, and no budget sweep
  replaces them.
- **What a shortfall means.** It is the FIRST refused request's, not the
  entry's demand, which is why both front ends say *"at least"*.
  `synth-dd-m5.dd` reports 928 B at the 512 KB budget and wants
  203,680 (FORMATS.md, *512 KB machines*).

`UNC_TRACE_ALLOC=1` in the environment makes the CLI print every
allocation and every refusal with the live total, which is how those
figures are read.

## Selective extraction (`tools/run_only.py`, in `ci.sh`)

Added 2026-08-28, with `--only`. There is no oracle for a subset:
`unar` has no per-file selection, so nothing else on this machine can be
asked what extracting two entries out of forty should produce.

What stands in for one is the engine's own FULL extraction of the same
archive, which the differential suite grades against `unar` — so a
selected entry being byte-identical to that same entry from the full run
is transitive to the oracle rather than circular. Every fork is
compared, sidecar included.

**The assertion that can fail is the strict subset.** An `--only` that
did nothing at all — every entry extracted, every time — satisfies every
byte comparison above it, because a superset contains each file it is
held against. Requiring strictly fewer files is what catches that, and
it was checked by disabling the filter: 362 failures, all three
generated formats and every swept fixture.

Five generated cases and a sampled corpus sweep. The generated ones are
a zip (exact names, a folder selector that takes what is in it, two
selectors at once, a name that matches nothing, one hit beside one miss,
and `l`/`t` taking the same option), a zip with a COMMENT, then
DiskDoubler in both its containers and Now Compress — the last three
chosen because each holds a FOLDER, which is the entry both hosts have
always skipped and the one those two formats reported the end of anyway
until the same day.

**An archive's own comment is not an entry**, so `--only` neither
filters it nor can be pointed at it: it belongs to the archive and is
written beside the selection as `<archive>.comment.txt` whatever was
asked for, and `--no-comment` is how a caller declines it (cli/main.c,
`sink_comment`). The comment case added 2026-09-20 asserts all three
halves of that. The sweep has to permit the file, and it does not guess
the NAME — a nested archive's comment is named after the archive inside
the envelope, not after the fixture — it asks: what a `--no-comment` run
of the same archive does not write is the comment, by definition.

**What it cannot see.** Whether a skip SAVED anything: a format that
seeks past a skipped entry and one that must decode and discard it —
PackIt, whose compressed entries state no end — pass identically, and
nothing here times either. A defect that corrupts the full extraction
and the selective one alike is invisible by construction; the diff suite
is what grades that side. The sweep passes over any fixture whose names
the filesystem shortened, because the path on disk is then not the name
`--only` matches against. Encrypted entries and segmented sets are not
reached. Neither is the Mac application, which has no selection UI.

**The sweep is every sixteenth fixture by name**, so what it covers is a
function of what the corpus is CALLED. Two fixtures added on 2026-09-20
sorted early, moved the stride by two, and the new sample immediately
found an archive with a comment — a case the suite had never met in
three weeks. A sweep sampled this way cannot be said to cover a
property; it can only be said to have met one.

## The three walks agree (`tools/walk_probe.c`, `tools/run_walk.py`, in `ci.sh`)

Added 2026-08-28. Every other suite here compares the OUTPUT of one
walk. Three exist, and nothing had ever held them against each other:
`list_only`, an ordinary extraction, and one that SKIPS every second
entry — the shape a selection has, and one no host produced before
`--only`.

The rule is that all three offer `begin_entry` the same entries, with
the same name, `is_dir`, type, creator and both fork sizes, in the same
order. The probe measures and `run_walk.py` applies it, as with the
progress callback.

**Envelopes are peeled on the way in.** A fixture named `Archive.sit.bin`
is a one-entry MacBinary wrapper, and probing it says nothing about the
StuffIt walk inside; the descent is by result rather than by a list of
formats — a layer yielding exactly one file that is itself a recognised
archive is an envelope, whatever it is called. 937 fixtures become
**1,354 archives walked three ways**, 419 of them behind a wrapper. The
whole sweep costs about 10 s, because what makes the differential suite
slow is running `unar` and comparing files rather than our own decode.

Both assertions were made to fail first, separately: a listing that
reports `data_size + 1` gives 461 failures across the corpus, and a
PackIt skip that does not consume the entry's bytes — the one format
whose compressed entries state no end, so a skip there must decode and
discard — desynchronises the walk on all four `.pit` archives and ends
it with `UNC_ERR_CORRUPT`.

**What it cannot see.** Whether the entries are RIGHT: it holds three of
our own walks against each other, and their agreeing on a wrong name is
the differential suite's subject, not this one's. Nor the decoded bytes
— `run_only.py` is what compares a selection against a full extraction.
Segmented sets agree trivially, ending with `UNC_ERR_SEGMENTED` and no
entries, because the probe builds no volume source. And the skip pattern
is positional, so a walk that lost its place in a way that repeated
every two entries would pass.

**A different kind of walk, in the same layer since 2026-09-22.**
`tools/vmac/walkprobe.py --check` grades the twelve HOST-side listers that
read a Macintosh volume back — whether each can see an invisible file, an
invisible folder, a locked file, and anything below the root. All twelve
see all three since 2026-09-23, so two of the four `EXPECT_*` sets are
EMPTY and kept: they fail in the other direction, which is the only
direction left. **Four more functions in `tools/` list a volume without
returning an entry set**, so nothing grades them; all four pass `-a` as
well, and `tools/vmac/README.md` carries the one-command `ast` re-survey
that says so. Four columns, no emulator and no ROM, seconds, and it
skips cleanly where hfsutils is absent. What it measures and what it cannot see:
`tools/vmac/README.md`, *What every walk can see*.

## The Macintosh shell's names (`tools/run_macnames.py`, in `ci.sh`)

Added 2026-08-28. The section above grades the CLI's answer to a name
that does not fit; this one grades the Macintosh shell's, which is
different code and had no test at all. `mac/macextract_mac.c` cuts every
path component to 31 characters — HFS's limit, so this happens to
ordinary long Mac names and not only to remarkable ones — and resolves
the collision that cutting creates in `BumpName`, off the File Manager's
`dupFNErr` rather than off the engine's flag.

The code under test is the shell itself, through the mock Toolbox of
`tests/mac_sink_test.c`; the subjects are DiskDoubler archives from
`tools/synth_dd.py`, because both caps have to be reached in one archive
shape to see which one acted — with one exception noted below. Twelve
cases: two files whose names are the same for 31 characters, which must
both come out with the second
numbered; two FOLDERS in the same position, which since 2026-09-03 are
two folders on the disk with the second numbered rather than one holding
both their files; four 63-byte folders summing to exactly the
engine's 255-byte cap, where the leaf's cut path lands on its own folder
and the numbering is the only reason the file survives; the edges of
the cut — 31 characters written whole, 40 cut to 31, and a nameless entry
written as `_`; and four added 2026-08-29 with the end-of-run report:

- **the extension is kept and the stem is cut** — `...ForTheBoard.rtf`
  keeps its `.rtf` and loses a character of name, and a numbered name
  takes the `~1` before the suffix rather than after it;
- **the report's lines**, which are what the Macintosh box lists: a
  renamed file and a renamed folder each name themselves twice, and an
  entry whose name was writable is not mentioned at all;
- **a per-entry failure**, from an archive whose one damaged entry is
  named in the report while the sound one still comes out;
- **more alike names than the numbering has digits for** — 102 of them,
  and one file after them whose survival is the assertion.

Four more since 2026-09-03, when folders started being numbered like
files (DECISIONS.md, *a folder is a name too*):

- **the same two folders in a ZIP**, the one case here whose subject is
  not a DiskDoubler archive, and deliberately: a zip declares no folders,
  so they exist only inside the paths of the files in them — the shape
  most archives a user downloads have, and the shape that used to merge
  in silence;
- **the same archive extracted TWICE into one destination**, where the
  folder must be descended into and the FILES numbered. It is what stops
  a numbering rule from spraying `~1` over the last run's work, and it
  fails on the one-line change that treats a directory this run did not
  make as somebody else's;
- **101 folders whose names shorten alike**, where the numbering runs out
  at `~99` and the hundred-and-first merges, is reported as *combined
  with*, and keeps its file;
- **250 folders against a 200-row memo**, where what is asserted is not
  the numbering but that no folder is SPLIT — the failure that would
  make numbering worse than merging, and the reason the table never
  evicts.

Two more since 2026-09-22, when StuffIt 5's UTF-8 names started being
folded into the MacRoman bytes an HFS name holds (DECISIONS.md,
*a name an HFS volume can hold*). The first is generated, because
nothing in this tree writes a StuffIt 5 file; the second is an archive
and lives in `tests/run_mac_sink.sh`'s own fixture list rather than
here, graded by `tools/check_mac_sink.py` (*And a warning for whoever
adds a fixture*, below):

- **a UTF-8 name**, driven straight through `sink_begin` by
  `mac_sink_test.c --utf8` rather than out of an archive — nothing in
  this tree writes a StuffIt 5 file, and the subject is the SHELL.
  Seven names: one that folds and loses nothing, one with no MacRoman
  spelling at all, a folder that loses characters holding a file that
  does not (one report line, about the folder), a 32-byte UTF-8 name
  that is 16 MacRoman characters and must therefore NOT be cut, two
  different unwritable names that fold to one disk name and must be
  numbered apart, and the same bytes with the flag clear, which are not
  folded at all. The ENGINE's half — that `fmt_sit5.c` sets the flag —
  is graded by `run_diff.py` over the corpus instead. **This one case
  also runs on big-endian m68k under qemu** (`--sink "qemu-m68k
  build/mac_sink_m68k" --case utf8`), because a 16-bit table and a
  shift-and-or decode are exactly the shape that reads differently on
  the target; the other twelve are file-system work qemu only makes
  slower.

**Established that it can fail**: against five one-line breakages of the
shell — the cap raised to 63 fails five assertions, the numbering removed
fails six (and loses a file, and stops the run), the empty-name
fallback removed fails one, the extension cut the other way fails four
(which is how it was written for a few hours), and
the numbering restored to its `~9` limit fails four, one of which is the
file that never came out. A sixth since 2026-09-03: treating a directory
this run did not make as another folder's — one line in `EnsureDir` —
fails the twice-extracted case with a `~1` folder beside the first run's.

**The mock's directory calls had to be made honest first.**
`PBDirCreateSync` tolerated `EEXIST` and minted a fresh directory id, and
`PBGetCatInfoSync` returned `noErr` over an untouched param block — so
`EnsureDir`'s dupFNErr branch, the one the real File Manager takes
whenever a folder is already there, ran against stack garbage in the
mock and was never exercised at all. Both are real enough to answer now
(2026-08-29).

**What it cannot see.** A name holding a '/', which HFS takes and which
reaches the shell as ':' for it to swap back: the mock builds a Linux path
out of the leaf, so the create fails there for a reason the real File
Manager does not have. Nor the BOX those lines are drawn in: whether it
is legible, scrolls and saves is `interactive.py --report` on an emulated
Mac (`tools/vmac/README.md`) — and, for the fold's own line,
`--report-utf8`, which drives `derived-800saywhat301j.sit` there and reads
the saved document back: three *"was named in characters this Macintosh
cannot write"* lines under *"Extraction complete."*. A control run
expecting the COMPOSED spelling's twelve `_` fails it, which is the defect
an NFC fold would have.

**And a warning for whoever adds a fixture.** Since the fold, the Mac
shell and the Linux CLI deliberately write DIFFERENT names for a StuffIt
5 entry MacRoman cannot spell — a row of `_` against the characters the
archive asked for — so a harness that grades Mac output NAMES against
the oracle reads a correct fold as a defect until it is taught the fold.
Three did, and all three were taught on 2026-09-22
(`tools/vmac_check.py`, `mac_component`):
`tools/vmac/checkdisk.py` when the Mac sample gained two such fixtures;
`tools/check_mac_sink.py`, when `tests/run_mac_sink.sh`'s list gained
`derived-800saywhat301j.sit` — the layer in `ci.sh`, which is also what
runs the fold **big-endian under `qemu-m68k` over a real archive**
rather than through `sink_begin`; and `tools/vmac/os9.py`, whose
`mac_leaf` had the fold and ran it on the NFC spelling, which is
`checkdisk.py`'s own bug and was labelled as latent in its docstring
until `os9sample.txt` gained a fixture that bites it. **`tools/vmac/run.py` is not
one of them and this paragraph named it until that day**: its verdict is
the on-screen grid, which is a file count and two summed CRCs, and a
summed CRC cannot carry a name — so a fold that went entirely wrong
would pass it, which is the same blind spot that let the gzip/.Z
fallback name survive (*Checking a run off the disk*, `tools/vmac/README.md`).
A name that MacRoman CAN spell needs no teaching anywhere: both sides
end up with the same character, which is why
`derived-Cool_Tools__.sit` cannot fail `checkdisk.py` with the fold
disabled, and `derived-800saywhat301j.sit` fails it with three names
missing and three unexpected.

## A cut archive is NOTICED (`tools/run_truncation.py`, in `ci.sh`)

Added 2026-08-29, and it exists because the suite next to it cannot ask
this question. `run_robustness.py` truncates every fixture at 25, 50, 75
and 98 % and requires the program to "terminate quickly with a normal
exit code" — **and exit 0 is a normal exit code**. So a walk that reads
the entries before the cut, hands them over and reports success passes
it, 9,320 variants clean, while the user is told a run is complete that
is missing half its files. Two formats did exactly that (BLOCKERS.md).

The question here is a disagreement: when `unar` calls a cut archive
broken, do we? The most-entried two fixtures of each format are cut to
25, 50 and 75 % — 87 archives across 15 formats — and a fixture where
`lsar` reports a parse failure and `macextract t` exits 0 is a failure
of this suite.

**Established that it can fail** against both defects it was written
for: putting the DiskDoubler walk's clean-end rule back fails it on
`ddtf-*.dd`, and removing StuffIt's clamp report fails it four times on
two `.sit` fixtures.

**It was passing for the wrong reason first.** The fixtures were the
first two of each format alphabetically, which for DiskDoubler is two
SINGLE-FILE `.dd` archives — no walk to cut, no way to fail, and the
check went green against a build with the defect deliberately restored.
The fixtures are chosen by entry count now.

**What it cannot see.** A format that CANNOT notice: a tar has no
directory and no end marker, so a cut tar is indistinguishable from a
short one — `unar` accepts those too, and the row says nothing about
tar. Nor one CUT POINT that DiskDoubler cannot notice either: a DDA2
archive may legitimately end without its 0xBBBB marker, leaving less
than one record after the last entry (`derived-DD_Expand.sea` does, and
`unar` reads it), so a cut that lands in that same window is
byte-for-byte a valid ending — `ddtf-ddpro411dd3.dd` cut to a fifth is
the measured case (DECISIONS.md 2026-08-29, *a cut archive*). A format `unar` cannot read at all (SuperDisk!, Now Compress,
SpaceSaver): it fails on the whole archive as well, so its failure is
not evidence about the cut one. And WHERE the cut falls — three
fractions per fixture, so a hole that only opens at one offset is not
found by three. A wider sweep is not in `ci.sh` but has been run: all
932 fixtures at the same three fractions, 2,796 cut archives, none
silent (2026-08-29).

## The progress callback (`tools/run_ticks.py`, in `ci.sh`)

`UncProgress.tick` is the engine's only cooperative yield, and on classic
Mac OS it is the whole user interface: the application pumps events there,
so a format that does not call it freezes the progress dialog and disables
Cmd-. and the Cancel button for as long as the extraction takes.

**Now Compress never called it**, from the day the format was written until
2026-08-28. Nothing in `ci.sh` could tell — every other suite grades bytes,
and a decoder that never yields produces perfectly correct bytes. It was
found on an emulated Mac, where three Cmd-. in twenty seconds did nothing
to a 9.9 MB entry (DECISIONS.md 2026-08-28).

`tick_probe.c` extracts a file with a counting callback and a sink that
keeps nothing, printing `ret`, the number of calls and the widest gap in
`bytes_done` between them. `run_ticks.py` sweeps the corpus and applies two
rules: an archive over 64 KB that extracts must tick at least once, and no
gap may exceed 32 KB. Both numbers are measured rather than chosen — the
32 KB is `NOW_INBLOCK`, the largest block any format here reads whole, and
everything else in the corpus comes in at 8,192 B.

**It can fail**: reverting the one-line fix in `src/fmt_now.c` makes it
fail on `derived-SyntheticReferences2.0.sea`, and the corpus's widest gap
drops to 16,172 B.

**Envelopes are peeled on the way in since 2026-08-28**
(`tools/envelopes.py`, shared with the walk suite). Until then this swept
the fixtures as they sit on disk, and 419 of the 932 are a wrapper around
the archive that matters — so for those it asked BinHex or MacBinary
whether it ticks, over and over, and never reached the StuffIt or Compact
Pro walk inside. 944 files became **1,363 archives**. Nothing was hiding
there: no new failure, and the widest gap is unchanged at 30,634 B, which
was already visible on a Now Compress `.sea` that needed no unwrapping.
A blind spot that turns out to be empty is still worth closing — it was
not empty by anybody's evidence, only by nobody having looked.

**What it cannot see:** how long a gap takes. It counts input bytes, so a
decoder that spends a minute inside one 8 KB step passes — Arsenic's
sampled inverse BWT is exactly that shape, and it reports its own
interpolated position for the purpose (`unc_progress_at`).

## Decryption (`tools/run_crypt.py`, in `ci.sh`)

Added 2026-08-23, when decryption came into scope. **Nothing in the
corpus is encrypted** — `lsar -j` over all 903 fixtures reports
`XADIsEncrypted` 0 for every entry — so this suite writes every archive
it grades, and the whole design is about not grading a decoder against a
generator that shares its reading.

Two of the eight ciphers need no generator here: **`zip -P`** writes the
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

**What this suite cannot see, and what does.** It grades StuffItDES end
to end and says nothing about how it is written, so the 2026-09-19 fold
onto standard DES's round is proved separately: `python3
tools/fit_sitdes.py` checks XADMaster's `DES_SPtrans` against the
standard table relabelled, A/Bs the old and new formulations over 20,000
random key/block pairs and every single-bit case, and shows why the KEY
schedule could not follow. Neither it nor `tools/gen_crypt_tables.py` —
which asserts the same relabelling whenever `src/crypt_tables.h` is
regenerated, and since 2026-09-23 also asserts that its reading of each
of FIPS 46-3's tables out of `reference/notes/fips46-3.pdf` is the only
one possible, and that RFC 1321's literal constants are the sines it
defines them as — runs in `ci.sh`; both are proofs about how the code
was arrived at, and what `ci.sh` grades is the result. Regenerating the
header therefore needs `reference/`, those two documents included
(`tools/fetch_references.sh`), which is also why `ci.sh` cannot check
that the committed header still matches its generator. DECISIONS.md
2026-09-19, *the DES that was only wearing a disguise*.

**The ciphers run on a big-endian 68000 too.** `tests/run_mac_sink.sh`
cross-compiles the unit tests with `m68k-linux-gnu-gcc -mcpu=68000` and
runs them under `qemu-m68k`, so every cipher vector — DES, StuffItDES,
MD5, RC4, the zip and Compact Pro keystreams, SHA-1, HMAC-SHA1, PBKDF2
and AES — is checked where the word order is the target's. Nothing else
does: no fixture in the Mac sample is encrypted, and the differential
suite is little-endian x86.

**Four shapes are graded here only because the FUZZER needs them.**
`synth_crypt.py` also writes zip's two ciphers itself — PKWARE's and
WinZip's AES at 256 and 128 — and a garbled ARC archive, because
`tools/fuzz.py` needs an encrypted seed per cipher that is the same bytes
on every machine, which `zip`, `7z` and `arc` cannot give it (*Fuzzing*,
above). A seed nobody grades might not be an archive at all, so each one
is extracted here too and handed back out: `unar -p` reads the
traditional-cipher one and the garbled ARC, `7z t` verifies the two AES
ones, and all four must come back as the bytes that went in. Demonstrated
failing 2026-09-26 on one flipped ciphertext bit per zip shape — `unar`,
`7z` and our own CLI each refused the archive.

**And the ARC one is the reason ARC's garble is graded here at all.**
`arc g<password>` needs Debian's `arc`, which is not on this machine, so
those cases have always skipped — every `./ci.sh` says so — and the
cipher's only graded cases had never run here — and `tools/get_arc.sh`
fetched that encoder on the first try when it was finally run, taking
this suite from 45 graded cases to 48.

**Those three go back to skipping on the next run**, and this is worth
knowing before reading a skip as a one-off: `ci.sh` opens with `make
clean`, which is `rm -rf build`, and `build/arc` is where `get_arc.sh`
puts the encoder. `build/deark` and `build/mpack` go the same way and come
back, because the suites that need them rebuild them on demand; nothing
re-fetches `arc`. So the real-encoder cases are graded when somebody
fetches it between runs, and **the synthetic shape is what grades this
cipher on every run**. It garbles three of `synth_arc.py`'s methods, needs
nothing installed, and failed two ways against the engine of 2026-09-26: a garbled entry whose ungarbled stream ran SHORT
was refused without the password being tried, because the retry set was
`{CRC, CORRUPT}` and not `TRUNCATED` (DECISIONS.md 2026-09-26, *the guard
that was on the other side*). It also asserts that no password at all
fails every entry rather than handing over garbled bytes.

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

Fourteen archives: one per block shape (each holding prose, run-length
content and incompressible noise), one stream cycling all five shapes with a
non-zero `padding` between two blocks, a folder tree with a nested folder, an
empty folder, a two-fork file, a resource-only file, a code 17 bits deep,
three whose table offsets are wrong by a constant — one obviously (the
reference does not even try zero), one plausibly (its checksum has to fail
first), and since 2026-10-05 one wrong the OTHER way, off by **-64**, which
is the only one gated on the SIGN of what the search returns: forcing that
answer positive refuses it and leaves the other three extracting, 1 of 4 —
and one where a stream's first block reaches back into the dictionary cache
the previous stream left behind. Type and creator are checked separately,
since comparing forks cannot see them: ours from `l -v`, the oracle's from the
Finder info in its AppleDouble sidecar.

**One of the fourteen is also committed as a fixture.**
`synth-now-mixed.now` — the stream cycling all five shapes — has an `unar`
manifest in `fixtures/manifests/`, so the differential suite grades those
paths byte-for-byte on every run, including on a machine with no `unar` at
all, and any future Mac replay can pick it up. It is restored from
`tools/synth_now.py -o`, like every other synthetic fixture (see *Corpus*).

**And since 2026-09-21 the same trees are built a second way** —
`build_archive(lead=True, word=True, trailer=True)`, the shape the encoder
writes —
and that build is required to be **word-aligned** (no block of an odd
length or at an odd offset, and no shape-3 coded region of an odd length,
which is what makes the two accounts its header gives of where its stream
starts agree), to carry a well-formed **16-byte archive trailer**, and to be
read by `derive_now.py` and by this CLI, and to carry the **fork-boundary
record** every member of every file the encoder wrote has. The archives
graded by `unar` keep the unaligned shape, because `unar` refuses a region
that leaves it fewer than four spare bits; the aligned build is checked
instead of replacing them. The record is the one of those differences that
would cost them nothing — what keeps it out of their default is that
changing it means regenerating `synth-now-mixed.now` and its manifest, and
this build is what makes that a decision about a committed fixture rather
than a gap in what is checked. **One more archive is built the way Now Compress builds one** —
those two plus 32,768-byte blocks — and graded all three ways, because it is
the only one here that all three readers agree on: it is the rung Now
Compress itself extracted (*The rungs*).

**Another archive is graded ONE way**, because the two implementations
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

**The READER half of the offset-delta search is graded beside this, since
2026-10-05**, and not through this engine at all: `ci.sh` rebases a
generated archive by 100 with `tools/mutate_now.py --delta` — which
recomputes the 32-bit sum the table keeps over its own stored offsets, so
the file is internally consistent — and requires `tools/derive_now.py` to
decode the same blocks back out, 15 of 15. Deleting `derive_now`'s
`table_delta` turns it red. What it cannot see: whether a delta a real
encoder writes has this shape at all. No file Now Compress wrote here
needs the search, and what the format's own mechanism is, is not known
(FORMATS.md, *Now Compress*).

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
(FORMATS.md ✧). A fifth case, `--case probe`, archives four members
deliberately made to RESEMBLE each other; it was built to make a code table
legible and it found a decoder defect on its first run, because a match
across a member boundary needs two members with something in common and
nothing else in the corpus has that (DECISIONS.md 2026-09-21, *the window
that stopped at the fork*).

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

## When a suite skips, and when it must not (2026-09-09)

Six suites build their oracle out of `reference/` — munpack and deark for
`run_mime.py`, btoa for `run_btoa.py`, lhasa and LHa for `run_lzh.py`.
Each has to answer "is the oracle here?", and the answer has three
values, not two:

| state | verdict | why |
|---|---|---|
| the binary is built | run | — |
| `reference/X` is **absent** | **skip, exit 0** | a fresh clone has no `reference/`, and `ci.sh` must still run end to end |
| `reference/X` is **present** and will not build | **exit 1** | somebody fetched it; the differential coverage it pays for has gone, and nothing in that suite is graded against a second implementation any more |

The third row used to be the second row, and that is how a real breakage
stayed green: `run_mime.py` reported a failed munpack build as *"no
reference/mpack"* — about a directory that was right there — and returned
0 (DECISIONS.md 2026-09-09, *the oracle that built two times in three*).
The message now prints what the build actually said and ends "fix the
build, or delete `reference/X` to make this a skip", so the escape hatch
is stated.

**Both failure paths were made to fire before this was believed**:
`reference/btoa/atob.c` moved aside, and `build_mpack.sh` reverted to the
`cp -r` that caused the original race. Each printed the compiler's own
words and exited 1.

**What this does NOT cover.** A suite can still pass with the oracle
built and doing nothing useful — an assertion that never runs, a sweep
over zero files. Every suite prints its case count for that reason, and a
count that drops is the only signal there is.

## dist/ is compared with the build (`ci.sh` variant 4, added 2026-09-22)

**`dist/` is a committed binary, it is the only download this project
offers, and until 2026-09-22 nothing compared it with anything.** Measured
at `0aa9101`, which changed `src/` without rebuilding it: the committed
`dist/MacExtract.bin` declared **188,154 B** of resource fork where that
tree's own build writes **187,563 B** — the download was **591 B** of
resource fork behind, and different bytes besides.

`ci.sh` variant 4 already builds `build/mac/MacExtract.bin`, so the
comparison is one command after it: the SHA-256 of everything from offset
128 on, against `dist/MacExtract.bin`'s. That payload IS the resource fork
— the application's data fork is 0 bytes. The first 128 bytes are not
compared because MacBinary stores the file's dates, so they differ between
two runs over identical code and the payload does not — asserted by this
check every run, on top of `make_dist.sh`'s statement of it.

The failure names the fix — `sh tools/make_dist.sh`, in the same commit as
the change to `mac/` or `src/`.

## The three Macintosh configurations (`ci.sh` variants 4, 4b, 4c, 4d)

**The application has been three builds from one tree since 2026-09-25**, and
`ci.sh` compiles all three because a configuration nothing builds is one that
rots — which is not a hypothesis: the two overlay branches each grew their own
copy of the same build-staleness fix, days apart, because neither tree
compiled the other (DECISIONS.md 2026-09-25, *two branches that were one file
apart*).

**It compiled two of the three until 2026-09-26**, while this section said
three, and the one left out was the control: a four-byte predicate in
`src/fmt_arc.c` put it 4 B over its own ratchet with every other variant
green, because that file is in an overlay in both shipped lifetimes. It was
found by building the control by hand to re-measure FORMATS.md's figures, not
by anything that runs. Variant 4d is that build (DECISIONS.md 2026-09-26, *the
numbers DART left behind*).

| variant | build | what it is |
|---|---|---|
| 4 | `build/mac` | the SHIPPED application — fourteen images, **eager**: one bundle read at launch, everything the sniffed format cannot want released before the engine takes its budget. `dist/` is compared against this one |
| 4c | `build/mac-lazy` | `UNC_OVL_LAZY=1` — the same images, one resource each, read when a format turns out to want one. Not shipped |
| 4d | `build/mac-resident` | `UNC_OVL_RESIDENT=1` — every decoder linked in, the application as it was until 2026-09-25. It is the CONTROL for budget measurements (FORMATS.md, *Overlays*), it has its own ceiling in `tools/build_mac.sh`, and it is built by `ci.sh` since 2026-09-26 |

**What these variants CANNOT see.** They compile, and that is all: a variant
that builds says nothing about what the loader does with an image. **Since
2026-09-26 that is no longer the end of the story** — `ci.sh` variant 3c runs
the loader itself off the Macintosh (the next section). What stays the
emulator tiers' alone is the Retro68 toolchain's own code generation, the real
Resource Manager, fragmentation, and any machine with an instruction cache.

**Made to fail before it was believed.** `unc_strerror`'s `"ok"` was
changed to `"oK"` and the Mac app rebuilt: the check fails on a
`build/mac/MacExtract.bin` that is **exactly the same 187,776 bytes** as
the shipped one, so a size or a timestamp comparison would have passed.
Reverted and rebuilt, it passes, and three separate builds of the same
source produced the same payload hash.

**What it cannot see:**

- **`dist/MacExtract.dsk`.** `make_dist.sh` copies both files in one run, so
  a current `.bin` implies a current `.dsk` unless somebody edits one by
  hand. The `.dsk` is an HFS volume carrying its own dates and cannot be
  compared byte for byte without mounting it.
- **Anything, without a Retro68 toolchain.** No `build/mac/MacExtract.bin`,
  no comparison; the whole variant already skips there.
- **A docs-only change**, which does not run `ci.sh` (CLAUDE.md, Rules).
  That is why the other half — `dist/README.txt`, which is generated and
  is the release notes verbatim — is `tools/check_docs.py`'s check 7
  instead: it re-renders `make_dist.sh`'s heredoc with the current
  `UNC_VERSION` and reports the first line that differs. Prose edited in
  the script reaches the download page only when somebody re-runs it. Made
  to fail three ways: a word changed in the heredoc, a line deleted from
  `dist/README.txt`, and the file truncated.
- **Whether the application is CORRECT.** This says the download is the
  tree's own build; that build is graded by everything above it.

## The overlay loader, off the Macintosh (`tests/run_overlay_host.sh`, `ci.sh` variant 3c)

Added 2026-09-26. **The fourteen `'OVLY'` images had no automated test of any
kind**: they exist only in a Retro68 build, so every lane above runs the
decoders as ordinary linked code, and whether an image is found, relocated,
kept, released or re-read was answered by emulator tiers, by hand, at minutes
per fixture. Three defects lived in that gap (OPEN_ITEMS.md, *The overlay
loader*).

**What makes it possible is that nothing in the mechanism is Retro68's.** The
images are flat `-mpcrel` m68k blobs with a relocation trailer; the loader
needs eight Memory Manager calls, two Resource Manager calls and a trap probe.
So `mkoverlay.sh` takes a toolchain PREFIX (`OVL_TOOL`, default Retro68's) and
builds the same sources with the same flags for `m68k-linux-gnu`; the stub
Toolbox headers in `tests/ovlbox/toolbox/` let `mac/ovl_load_eager.c`,
`mac/ovl_load_lazy.c`, `mac/ovl_reloc.c` and `mac/ovl_shim.c` compile
**unmodified**; and `qemu-m68k` runs the result, images and all.

Four lanes, in one script, ~65 s:

| lane | what it grades |
|---|---|
| the images | fourteen of them, from `tools/overlay/images.py`'s inventory — which is PARSED out of `mac/CMakeLists.txt`, so a fifteenth image cannot exist in the build and be missing here |
| the loader | both lifetimes, natively under ASan+UBSan and big-endian under `qemu-m68k`: read counts, keep and release per format, the `wa`/`kf`/`rf`/`fc`/`fn` probe fields, and **every relocation in every image checked against the raw file's own trailer at the address the image runs at** — including a kept copy, which is relocated a second time by the difference of two addresses |
| extraction | the sink suite's own fixture list, extracted THROUGH the images under `qemu-m68k` and compared with the committed oracle manifests by `tools/check_mac_sink.py`: **17 fixtures, byte-exact, in both lifetimes** |
| one per image | seventeen fixtures reaching thirteen of the fourteen images, each compared with the RESIDENT build of the same engine — the only oracle for an image no manifest covers (SuperDisk!, btoa, MIME). Exit status is compared too, and neither build is required to succeed |
| the SHIPPED images (`--shipped-only`, `ci.sh` variant 3d) | the same loader against the images **Retro68** just built — the bytes `dist/` ships — in both lifetimes: found, relocated at the address they run at, kept, released. This is the only check anywhere on the bundle's own directory and on **30 relocations across six images**, which is what Retro68 emits where the m68k-linux build of the same sources emits 15 in one. They cannot be CALLED here: a Retro68 image entered from an m68k-linux host binary segfaults, measured rather than assumed, so that lane stops at the loader |

**The mock is harsher than a Macintosh, deliberately**
(`tests/ovlbox/ovlbox.c`): every unlocked block moves on every allocation,
where the Memory Manager compacts only when it must; every block's last byte
abuts a guard page, so a relocation or a `BlockMoveData` past the image end
faults at the write; and a released resource is really gone, with the next
`GetResource` counted as a fresh read — which is how the two lifetimes are
told apart at all.

**Made to fail before it was believed, and it stays that way.** `--mutate`
breaks the loader six ways and requires each break to be caught: the delta
dropped, the trailer's table mislocated, a kept copy relocated by its own
address instead of the difference, the bundle fixup not flushing, the lazy
loader not locking, and the codecs image not kept. All six are caught, and
`ci.sh` runs them every time. The mutations are applied by
`tests/ovlbox/mutate.py`, which FAILS when its pattern is absent — the first
version used `sed`, which exits 0 having matched nothing, and duly reported an
unapplied mutation as an uncaught defect.

**What it CANNOT see** — the list is `tests/ovlbox/ovlbox.c`'s header, and the
emulator tiers are what cover these:

- **No instruction cache, on either host.** The flush is counted, never
  needed; whether it WORKS is real 68020-and-up silicon's answer
  (MANUAL_TESTS.md §2).
- **Not Retro68's code generation, where an image is EXECUTED.** The two
  toolchains do not even emit the same relocations: `m68k-linux-gnu-gcc`
  produces 15 in one image, Retro68 30 across six. The shipped images are
  loaded and checked by variant 3d above — what no host lane can do is RUN
  them, because a Retro68 image entered from an m68k-linux binary segfaults.
- **No Resource Manager**: no resource map, no purging, no file.
- **No fragmentation.** The mock always finds room; "Memory is too broken up"
  is `tools/run_tiers.py`'s blind spot too.
- **Nothing about the interface**, and no budget: `UNC_AT_BUDGET` is defined
  for the loader lane only, because in `mac/macextract_mac.c` it turns on a
  heap probe built from `ApplicationZone`, `LMGetApplLimit` and `MaxBlock`.
- **The control lane's oracle is this project's own output**, so it cannot
  notice a decoder that is wrong in both configurations. That is what the
  937-fixture differential suite is for; this lane grades only that the
  mechanism is transparent.

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
two methods, 7 and 11, because that is what the two archives use — and it
reaches no STORED block at all: **all seven blocks across both fixtures are
coded**, so `sd_block_head`'s bit-15 branch is not exercised by anything in
the corpus, nor by the 116 variants, which flip bytes inside those coded
blocks. That branch is graded on the emulator instead, by the extractor it
was disassembled out of (`tools/vmac/superdisk.py --stored`, byte-exact
2026-09-01; FORMATS.md, *Alysis SuperDisk!*). The unit
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
   22 blocks of methods 1 and 6, byte-exact both ways — eight of them
   compressed on purpose (`--boundary`), and the four added 2026-08-28
   are the ones that found a decode defect in this engine. They were
   sized from a MEASUREMENT of what the panel writes rather than from a
   rule about what the harness writes (`tools/sdhuff.py`; DECISIONS.md,
   the refill boundary).
3. **Synthetic blocks for methods 1..9**, built from this engine's reading
   and put through both readers. Until 2026-08-28 this phase SKIPPED every
   block whose coded flag bitmap ended on a 32-bit refill, on the grounds
   that the two references read those differently — the one case that could
   have failed was the one case excused, and it was hiding a defect in this
   engine rather than a disagreement between theirs. The skip is gone and
   every method agrees 12/12.
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
6. **Method 13** (added 2026-08-29), which is the other compressor and
   is not the same story: the four streams it writes must declare
   method 13 and carry the input's length in a 32-bit field, its
   decompress command must break into the debugger, and **no method this
   engine knows may read the payload**. That last one is an assertion
   that today passes by finding nothing, and it is the one that matters:
   the day a decoder appears it fails and says so. Falsified on purpose
   by handing the phase module 20 under 13's number — three of its four
   checks fire.

**The callback is the part to know about.** "Tighter" decodes methods 2, 3,
4, 6, 7 and 8, and it hands its Huffman regions back to its CALLER to decode
— `jsr` through a field of the parameter block — so the runner has to be a
dispatcher as well as a loader. Without one it jumps to address zero.

`tools/vmac/rescomp.py` is the sibling that went looking for data for the
three methods this suite can only load: Alysis Resource Compressor 2.0
(1993) carries the whole codec library, and `--modules` lists it without an
emulator. What it settled is negative and worth keeping — driven under Mini
vMac it compresses into Apple's resource container, not a `Cmpr` stream, so
it is not the writer of method 10 either (OPEN_ITEMS.md). For 13 and 20 the
question dissolved: both modules ARE writers, and both now run here.

**What it cannot see.** A synthetic Huffman region is written with a flat
8-bit table, so no real tree shape is exercised: what is graded is the
framing, the flag bitmap and the context predictor. Method 10's cases are
one block each, so the history carried BETWEEN blocks is exercised only by
the code it shares with SlowFastB. **Method 13's output cannot be checked
by anything**, because no decoder for it exists in any software in reach —
the phase can assert its framing and cannot say whether the bytes inside
are well formed. And agreement is not correctness
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

## AppleLink packages: SqueezePlay (`tools/derive_sqp.py`, not in `ci.sh`)

Rewritten 2026-10-05, when the format stopped being guessed at. `.pkg` is
still not recognised by the engine, so there is nothing in `ci.sh` to run;
what there is to test is the READING, and it is tested two ways.

**Thirteen witnesses** (`--witness`) are byte patterns in `'Othe' 1` of
`AppleLink Package Translator` 3.0.3, one per fact the reader relies on:
the 86-byte SQP record, the 90-byte HFS record at 86 × count + 22, the
9-bit start, the 257th first code, the 256 clear code, the 8192 ceiling,
the two fork lengths and the stored bit. A different build of the expander
makes this print MISSING rather than silently confirm.

**The grading is the part that matters.** Both real packages are parsed and
every member expanded: **4 of 4** reach their declared length, and each is
checked against a recorded sha256. The directory is also required to tile
the file — the last member must end at the last byte — which is what
catches an off-by-one in the record stride.

**What this cannot see.**

- **Four paths that no member takes.** Both packages carry `rlen` = 0 and
  neither sets the stored bit, and the LZW streams contain **0 clear
  codes** and never widen past **12** of 13 bits (largest table 2,260 of
  8,192). The script prints that list on every run — an UNEXERCISED line —
  so a green pass cannot be read as covering them (OPEN_ITEMS.md).
- **Whether a subtly wrong decoder is wrong.** A package has no per-member
  checksum, so the only oracle beyond the declared length is the sha256
  this script recorded from its own output on 2026-10-05. That makes it a
  REGRESSION oracle and not an independent one; the independent evidence is
  the declared length, the file tiling, and that all four members read as
  coherent Mac-Roman text saying what their names say.
- **The first version of this script could not fail at all**, and the fix
  is the reason the length check is worth anything: it passed `rec["dlen"]`
  into the decompressor as a ceiling and then asserted the output was that
  long. Removing the ceiling makes the stream's natural end the test, and a
  single flipped byte then reports 1,960 against 1,954 and exits non-zero
  (DECISIONS.md 2026-10-05, *the sample that was read as the table*).

The old unit checks for `unc_applelink_probe` are gone with the probe: what
they asserted was the shape of a translator COMMAND parser, and the
"0 of 928 fixtures said AppleLink" sweep was measured over a corpus holding
neither a package nor a script (BLOCKERS.md).

## Archives named but not extracted (`tools/run_foreign.py`, in `ci.sh`)

Added 2026-08-26, replacing the disk-image suite that came out the same day
(`attic/`). `src/fmt_foreign.c` is signatures and nothing else, so the test is
the signature, its neighbours, and the corpus.

```sh
python3 tools/run_foreign.py --macextract build/dev/macextract
```

**Four grades of case, and the suite says which is which.** bzip2, xz, 7z,
cpio (three header shapes) and ar are written by their own tools here and then
**opened by p7zip** — a specimen that p7zip cannot parse proves nothing about
a probe, so that check is asserted rather than assumed. **Apple Archive is the
same grade with the writer built for it**: `tools/build_neoaa.sh` compiles
libNeoAppleArchive out of `reference/`, and `tools/neoaa_write.c` writes one
archive per shape — raw `AA01`, `pbze`, `pbzz`, `pbzb` — then reads each back
with that same library and exits nonzero if it will not parse, which is what
p7zip does for the others. Zoo, ARJ and Cabinet
are hand-built headers that **deark** must identify as `zoo`, `arj` and `cab`;
if deark does not agree, the case is worthless and fails. RAR and RAR 5 have
neither — no writer here, no deark module, and p7zip refuses to name a stub it
cannot parse — so in `ci.sh` they rest on the constants in
`reference/XADMaster`, with real archives measured once outside it (FORMATS.md,
*Archives named but not extracted*).

**The negatives are the point of a signature file**: the eighth RAR byte, the
7-Zip reserved byte, xz's terminator, bzip2's two stream magics and its level
digit, Zoo's magic at offset 0 instead of 0x14, ARJ with a broken header CRC
and with a size out of bounds, `070703`, `!<arch>!`, an Apple Archive header
smaller than its own six-byte prologue, one whose first field subtype is
outside the closed set, and a `pbz` stream naming a codec that is not one.
Each was mutation-tested against a probe with that field deleted.

**And the corpus is swept**: not one of the fixtures may come back as a
foreign archive. Naming a Macintosh archive as a PC one is worse than not
naming it, because the user would then be sent to a program that cannot open
it either. **One fixture is exempt and graded rather than skipped**:
`synth-os9-rar.rar` is a RAR on purpose — the Mac OS 9 tier boots one file per
format and needed something to raise the refusal alert (2026-08-27) — so the
sweep requires it to sniff as RAR and requires everything else not to.

**What this cannot see.** Whether a real Zoo, ARJ or Cabinet archive is named —
those three are graded on headers built here, which deark identifies but which
no archiver wrote. Nor whether Apple's OWN `aa` writes anything
libNeoAppleArchive does not: every Apple Archive here comes from the one
implementation the probe was also written from, so a shape only Apple emits
would be invisible to both. That needs a macOS, and is MANUAL_TESTS.md's kind
of gap, not this suite's. The `pbzx` and `pbz4` codec letters are untested for
the same reason twice over — libNeoAppleArchive names them and does not yet
write them. And nothing here tests what a named-but-declined archive
does on the Macintosh: that is one alert, photographed once
(`tools/vmac/README.md`, *Photographing the detect-only alert*).

## StuffIt SpaceSaver (`tools/run_spacesaver.py`, in `ci.sh`)

Added 2026-08-22. SpaceSaver has no oracle but itself — `unar` and
`macunpack` do not know the format, so there is no manifest. **48 specimens
arrived on 2026-09-26**, downloaded rather than made: files SpaceSaver
compressed on the machines that mastered Apple Developer, MacTech,
Apprentice, Info-Mac and HyperLib CD-ROMs, **46 of them with the
uncompressed original** on an earlier pressing of the same title. They cover
both header versions and methods 0, 1, 2, 3 and 4, and all 46 pairs decode
byte-exact (DECISIONS.md 2026-09-26, *the magic in somebody else's index*).

    tools/fetch_specimens.py --only spacesaver

fetches them into the directory below and checks every sha256;
`tools/specimens/spacesaver.tsv` is the table it reads. Specimens live
outside the repository, beside the emulator's ROM and System image, because
a compressed file is what SpaceSaver made of a subject and is no more
committable than a fixture:

    ~/.cache/macextract/vmac/specimens/spacesaver/NAME.ss        the file
    ~/.cache/macextract/vmac/specimens/spacesaver/NAME.ss.orig   its input
    ~/.cache/macextract/vmac/specimens/spacesaver/PrAm-4048.bin  the preset

`--layout` writes the preset out of the installed control panel;
`tools/vmac/spacesaver.py --idlespec` would make a pair on the Macintosh and
never has (BLOCKERS.md). **With none of them present the suite prints what it
skipped and returns 0**, so a fresh clone stays green and says nothing —
which is exactly how a grade that could never have passed went unnoticed for
five weeks: it looked for the decoded file under the specimen's name with
`.ss` removed, and this format's CLI keeps the whole basename because
SpaceSaver adds no extension. A specimen without an `.orig` beside it is now
decoded and required to succeed rather than skipped outright.

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

**What this cannot see.** **No resource fork is graded.** The originals come
from ISO 9660 pressings, which dropped the resource fork; the package's copy
of it decodes to a structurally valid resource map of the declared length and
nothing compares its bytes. **Method 4 is not graded either** — its two
specimens are magazine production TIFFs with no published original, so they
are only required to decode (they produce valid LZW TIFFs with a `PICT`
preview in the fork). Methods 1, 2 and 3 are also graded off the Macintosh
against the modules that write them (*SpaceSaver's own codecs*, below); what
the unit test still asserts is the per-ENTRY refusal, now for method 5, which
no version of SpaceSaver ever wrote. The unit tests also carry what no
specimen here has: a resource fork whose stream is written BEFORE the data
fork's, which is what the header's offsets are for.

## ZipIt's own archives (`tools/run_zipit.py`, in `ci.sh`)

Added 2026-10-04. Until that day every subject for ZipIt's three
Macintosh extra fields was generated here, and `0x2605`'s premise — the
field is present when and only when the entry's data is MacBinary — was
APPNOTE.TXT 4.6.4's word (DECISIONS.md 2026-10-04, *the archive that
carried its own extractor*). **Nine archives ZipIt itself wrote** now
grade it; the figures are FORMATS.md, *ZipIt's own archives*.

    tools/fetch_specimens.py --only zipit
    python3 tools/run_zipit.py --macextract build/macextract

`tools/specimens/zipit.tsv` is the table, and the files land beside the
other specimens — outside the repository, like every fixture, because
they are somebody's shareware:

    ~/.cache/macextract/vmac/specimens/zipit/

**How four of them were found is re-runnable.**
`tools/scan_discmaster_zips.py` lists every zip on the Discmaster items
you name and reads 512 bytes of each over HTTP `Range`, which is enough
to see the first entry's extra field. Not in `ci.sh` — it needs the
network and produces URLs rather than a verdict — and widening the
sweep to more items is a one-line change:

    tools/scan_discmaster_zips.py \
        --items-from tools/specimens/spacesaver.tsv \
        --items-from tools/specimens/applelink.tsv

is the 2026-10-04 run: **3,029 zips, seven hits**. It keeps its progress
in `--state` and resumes, because it will not finish inside one
foreground timeout.

**Two of the nine are corpus fixtures as well.** `MrTs_Paint_Folder.zip`
carries `0x2705` and `0x2805`; `NPWritersKit.zip` carries a `0x2605`
entry with 150,016 B of data fork and 323 B of resource fork. Both are
plain zips, so `run_diff.py` grades them against a committed manifest
with **no oracle at run time**, which is stronger than anything this
suite does. They stay in this suite too, because what it checks of them
— the fields themselves — a manifest does not record.

Four things run per specimen:

1. **The format, read independently of the engine.** Every ZipIt field
   is parsed in Python: the central copy must equal the local one, and
   each size must be what `'ZPIT'` plus the members it declares needs.
2. **`0x2605` against the bytes.** The entry is inflated and its first
   128 bytes probed as MacBinary — the same test `zip_mb_peek` makes —
   in both directions: a `0x2605` entry that is not MacBinary fails, and
   so does a `0x2705` entry that is.
3. **`l --finder` against `lsar`**: name, type, creator, Finder flags
   and both fork lengths.
4. **`x` against `unar`**: every data and resource fork byte for byte,
   `unar`'s AppleDouble sidecar unwrapped (this engine writes the fork
   raw).

**Per-specimen tallies are asserted, and that is the part that matters.**
`EXPECT` holds entries, one count per field id, and the number of
MacBinary payloads for each archive. A parse that stopped parsing would
otherwise report zero of everything and pass — the failure mode this
project has hit twice (CLAUDE.md, *A test that passes may not be testing
anything*). It was made to fail two ways before being believed:
rewriting every `0x2605` id to `0x2805` in one specimen gives 4
failures, and moving the `0x2705` flag read by two bytes in
`src/fmt_exo.c` gives 66.

**What it cannot see.**

- **It does not test that a ZipIt SEA is RECOGNISED**, because it is
  not: `unc_zip_probe` reads the head and the head is PowerPC or 68k
  code, so the five self-extractors are passed `-f Zip` (OPEN_ITEMS.md).
  The four plain ones are *required* to sniff as `Zip`, and the count of
  each is printed, so the distinction cannot quietly change.
- **No fork of an entry whose method is out of scope**, and `UNGRADED`
  names every one with the reason. Today that is
  `Psycho!v1.0ß1.zip`'s three Implode entries. The declaration carries
  the NUMBER, so a fourth refusal there — or a refusal anywhere else —
  fails.
- **No date.** `lsar` reports zip's own MS-DOS stamp where a `0x2605`
  entry's MacBinary header carries two Macintosh ones. They are not the
  same field, so agreement between them would mean nothing and
  disagreement would mean nothing either.
- **Four names `unar` spells differently**, each allowed only while
  ZipIt's own `0x2605` FileName is one of the two spellings — which is
  checked, and is what lets the tolerance fail. It is not "ours is
  right": on three of the four it is `unar` that is right
  (OPEN_ITEMS.md).

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

## The derivation tools (`tools/derive_*.py`, not in `ci.sh`)

**These are not tests. They are the evidence that a format's facts
come from somewhere other than somebody's program**, and they exist
because a citation is a claim: `src/*.c` says a file follows a
description, and these re-run the reading that says the description
is right.

Each is a reader for one format, written from a description and from
nothing else, which decodes whole forks and compares them against the
sha256 an independent oracle recorded in `fixtures/manifests/`.

| tool | reads | against |
|---|---|---|
| `derive_huffman_tree.py` | the bit-serialized tree of StuffIt 3, DiskDoubler 4 and PackIt | 13 forks; `--grid` re-derives the rule from a 16-way search |
| `derive_stuffit8.py` | StuffIt method 8 (Miller-Wegman) | all 4 method-8 forks in the corpus; `--grid` re-searches the parameters |
| `derive_arc.py` | ARC's member header, RLE90, and methods 4, 8 and 9 | 6 members; `--grid` derives them from archives a real ARC 5.21q writes to order |
| `derive_cpt.py` | Compact Pro, container and both coders | 536 forks of 68 archives |
| `derive_sqp.py` | AppleLink `.pkg` — SqueezePlay's container and its 13-bit LZW, out of Aladdin's own expander | **4 of 4** members of the two real packages, to their declared length and a recorded sha256, plus 13 witnesses in the expander. What it CANNOT see: the resource fork and the stored mode, which neither package uses (above) |
| `derive_sit13.py` | StuffIt's container and method 13 | 897 forks of 103 archives, all six code selectors |
| `derive_sit6.py` | StuffIt method 6: its framing, its fixed code book and its PackBits tail | all 11 method-6 forks in the corpus — 27 blocks, 13 Huffman and 14 stored. It parses the 26 bytes out of deark's source rather than holding a copy, so it cannot agree with the engine by sharing a typo with it; and it measures the one thing the two references disagree about, whether the stop code follows the declared length (13 of 13) |
| `derive_dd.py` | DiskDoubler's DD (10) and AD (6, 9) coders | 39 of 39 forks, two of them in method 10's delta form; with no container parser it tries both forms and says which read — and since 2026-09-22 it NAMES those two rather than counting them, so the list can be held against the one `derive_ddc.py` reads out of the container |
| `derive_sit5crypt.py` | StuffIt 5's encrypted-archive header, against the three archives DropStuff 5.0.1 wrote | **3 of 3**: bit 7 = encrypted, bit 4 = the password hash sits 14 bytes later, and the hash is MD5(MD5(password)[:5])[:5] at passwords of 4, 9 and 17 characters. No engine and no reference in the loop — the bytes Aladdin wrote and `hashlib`. It checks the 14-byte shift is LOAD-BEARING separately (the shifted offset's length byte is 5, the unshifted one's is 13), because a reading that works is not evidence when the alternative would work too. What it CANNOT see: bit 5, which none of the three sets; an archive carrying a comment would grade it. Not in `ci.sh` — the specimens live in the cache |
| `derive_dd8.py` | DiskDoubler method 8 — whether it IS Compact Pro's stages, and at what Huffman block | **7 of 7 method-8 forks, byte for byte** against the oracle manifests, decoded with `derive_cpt.py`'s reader, which is written from Compact Pro's three published wiki pages alone. Sweeps the block size on a grid that runs DOWN as well as up. What it CANNOT see: the block size. Every size at or above 0x1000 reads every fork and the largest that fails anywhere is 0x400, so no stream in the corpus reaches even that much cost and 0xfff0 is unfalsifiable on it — the tool says so rather than passing quietly. It also cannot see whether some OTHER pair of stages would reproduce these forks; it measures that Compact Pro's suffice |
| `derive_ddc.py` | DiskDoubler's three containers: a compressed file, `DDAR`, `DDA2` | **all 91 DiskDoubler fixtures, 244 entries — 643 assertions, 0 disagreements** against the oracle manifests: every entry's path, both fork lengths, and type and creator wherever the oracle recorded them. `--grid` re-derives the layout instead of assuming it, reporting for each field every offset that agrees with the oracle EVERYWHERE — and saying which fields this corpus cannot pin, of which the most instructive is `DDA2`'s stored-record resource-fork length: 27 offsets survive because the value is 0 in all 30, which is what DiskDoubler Pro only writing that record for a fork-less file looks like from the outside. Nothing locates a record except the format's own magic or the walk the assertions already grade. Two of the shapes it reads are not in the corpus at all: `tools/vmac/diskdoubler.py --combine` drives DiskDoubler 3.7's own Combine command over a known tree, and `--verify-combine` grades what this engine makes of the result against the bytes DiskDoubler was given — **7 entries, 0 disagreements**, a folder tree and a two-fork file included |
| `derive_packit.py` | PackIt's container, stored and Huffman-coded | 38 forks of 4 archives; it checks no CRC, so nothing here confirms the polynomial |
| `derive_sit5.py` | the StuffIt 5 container: the archive header, both entry headers, the second file header and the tree | **all 31 StuffIt 5 fixtures, 525 entries**, against the oracle manifests — every entry's PATH and both forks' lengths, 0 disagreements. The path is the part worth having: nothing in the container stores one, so it is the tree the parent-offset chain makes, and two `.nib` bundles in the corpus hold three identically-named files each, which is what caught the first version keying on leaf names |
| `derive_lzh.py` | the LZH/LHA header, all four levels and the extended-header chain | **156 archives and 191 entries** — this project's 7 fixtures, lhasa's collection from 20 writers, LHa for UNIX's own — with **0 disagreements** against lhasa's listing of the same files. The only derivation here that grades HEADERS rather than forks, so it is also the only one whose check is structural: an entry's data must end exactly where the next header begins, and a field read wrong derails the walk at once. The three things lhasa does to a name that the document does not ask for — lower-casing an all-caps one, collapsing `..`, replacing an unprintable byte — are named and counted (41 names), not adopted; `unar` does none of them and neither does the engine. It refuses `regression/truncated.lzh`, which is truncated |
| `derive_now.py` | Now Compress: all four coders, the block table, and the container a compressed file and an archive share | the specimens `nowcompress.py` makes, byte for byte — 139 archive blocks of 139 and 144 specimens across sixteen cases — plus **both corpus archives**: `--expect DIR` grades an archive against a directory of extracted forks (`--forks visible`, so a member's resource fork is `NAME.rsrc`), and it reads the 1993 one's 3 blocks of 3 and the 1995 one's 306 of 306. **Nothing is searched for**: a block table is one layout at one offset width, a shape-3 block's header says where its stream starts and ends, a shape-2 block's stream starts a fixed distance past its table, and three checksums — per block, per block table and per member record — are checked as it goes. Given an archive and no `--expect`, it decodes every block anyway, the member records' fork lengths saying how long each fork is. **`--prefixes`** censuses the two bytes an LZSS stream opens with — which blocks carry one, how many are a member's first, and, per shape-2 block, the symbols its table codes against the symbols its stream uses. **It cannot see anything about a version of Now Compress that is not installed**: the specimens are 5.0.1's and 6.0's (`nowcompress.py --setup6 --case6`), and a constant over two encoders is a fact about those two |

Each writes its corrections into `docs/formats/`, which is what the
engine cites; the descriptions themselves are fetched into
`reference/notes/` by `tools/fetch_references.sh`.

**One of them asks the other direction.** A reader that ignores a field
cannot tell you whether the FORMAT ignores it, so `tools/mutate_now.py`
changes one field of a Now Compress file, recomputes every checksum
over it, and `tools/vmac/nowcompress.py --expand` / `--adjudicate`
hands the file back to Now Compress itself. What it cannot see: only
the ONE implementation that exists, so "nothing reads this" means
nothing in Now Compress 5.0.1 and in the decoder a 1995 `.sea` carries;
and a mutation that fails proves only that something changed, which is
why the byte in front of a Huffman stream needed a second, POSITIVE
specimen before its meaning could be called measured
(docs/formats/now-compress.md, *A code length past 15*).

**Why they are not in `ci.sh`.** They need the fixtures, which are
copyrighted and not committed, and `derive_arc.py --grid` needs an
encoder `get_arc.sh` downloads. All of them skip cleanly with a
message when what they need is absent, which is what a fresh clone
has. They are also slow: Python decoding half a megabyte of LZSS is
minutes, and the whole set is the better part of an hour.

**What they CANNOT see:**

- **Whether the shipped C is independent of XADMaster.** They prove a
  description is sufficient to read the format. They say nothing
  about how `src/` came to be written, and no note claims otherwise.
- **Anything about a fork no fixture has.** StuffIt method 8's table
  restart, its end-of-stream code and its 14-bit ceiling are all
  unreached by any specimen here, so the derivation is silent on them
  and `fmt_sit.c` still cites XADMaster for those three rules. A tool
  that printed "all forks decode" without saying how many forks there
  are would be hiding exactly this.
- **Whether the oracle is independent.** `unar` IS XADMaster, so a
  fork it and the description agree on has been checked by one
  lineage twice. Where a second lineage exists it is used instead —
  `derive_arc.py --grid` grades against the bytes handed to a real
  ARC, and the DiskDoubler method-4 specimen is one Salient's own
  expander reads back.
- **What this project's own Now Compress fixtures are not.** The 13
  synthetic archives `tools/synth_now.py` writes exercise every block
  shape and both routes into the offset-delta search, and they are not
  what the encoder writes: their block trailers and file-header
  checksum are left **zero**, their mode words are `0x0001`/`0x0021`
  where Now Compress writes `0x0010`/`0x003f`, their block records
  carry a padding of 2, their LZSS streams open `00 00` where the
  encoder writes `00 03`, **no member's table carries the
  fork-boundary record every member of every file the encoder wrote
  has** — including the two-fork member, where that record is what
  separates the forks (docs/formats/now-compress.md, *A member's
  blocks*) — and **their blocks are not word-aligned**, where all 479
  of the encoder's are (*Every block is an even number of bytes*).
  `build_fork`, which writes a compressed FILE for Now
  Compress's own Decompress to read, gained the record on 2026-09-21
  because without it Decompress refuses the file.

  The alignment is the one of those that costs a READING rather than
  only fidelity: a shape-3 header states where its stream starts twice
  over, and the two agree only while the coded region is an even number
  of bytes. 25 of the 37 shape-3 blocks these archives hold are odd, so
  they say two different things about their own stream — `src/fmt_now.c`
  rounds up and `derive_now.py` believes byte 1. They stay that way on
  purpose: `unar` refuses a region that leaves it fewer than four spare
  bits (measured 2026-08-15) and a 16-bit flush does not always leave
  more, and these thirteen archives exist to be graded by `unar`.
  `--ladder`'s `word` rung is the aligned build, and it is what Now
  Compress is asked about.

### The rungs

  **On 2026-09-21 the encoder was finally asked about the ARCHIVES, and
  it answered.** `synth_now.py --ladder` builds a control and a rung
  per difference, and `tools/mutate_now.py`'s `splice` puts each one in
  a real self-extractor's data fork so Now Compress's own decoder reads
  it (`nowcompress.py --adjudicate`, one boot each, about six minutes).
  The **control** is `probe`'s 3,830-byte archive inside `tree`'s
  self-extractor, which was built around an archive half that size: it
  extracts all four members byte-exact, so the route is sound and a
  different length is not the obstacle.

  | rung | over `arch` | Now Compress |
  |---|---|---|
  | `control` | a real archive | all four members byte-exact |
  | `arch` | the header's setting, window and byte sum, every block trailer, the fork-boundary record and the `0x0100` mode vocabulary | **refused** |
  | `word` | + every block word-aligned | **refused** |
  | `chunk` | + 32,768-byte blocks | **refused** |
  | `tail` | + the last record's mode and padding before a table's checksum | **refused** |
  | `trail` | + **the 16-byte archive trailer** | **both members byte-exact** |
  | `only` | `arch` + the trailer alone | **refused** |
  | `no-tail` | `trail` less the table tail | **both members byte-exact** — the minimal set |
  | `no-word` | `trail` less the alignment and the tail | extracts; the member whose block starts at an **odd offset** comes out wrong, the one starting even byte-exact |
  | `no-chunk` | `trail` less the block size and the tail | **refused** |

  **Three things are needed and the fourth is not**: the archive
  trailer, 32,768-byte blocks and word alignment, in
  docs/formats/now-compress.md under *The archive layer*, *A fork is a
  sequence of blocks* and *Every block is an even number of bytes*.
  Two of the three are refusals and the third is a silently wrong
  block, which is the more useful half of the result: an archive can
  be ACCEPTED and still be wrong, so the fork comparison is what
  grades a rung and the verdict line is not.

  **The first guess was the LZSS prefix and it was wrong on its face**:
  every block in these archives is shape 3 or Huffman-only, and only
  shapes 1 and 2 carry the `00 03`. Working from the list of
  differences rather than from the file is what put it there; the
  trailer, the block size and the alignment all came out of diffing an
  archive the encoder wrote against one this project wrote, field by
  field, and **none of the three was on any list**. The engine reads
  these archives because it checks none of it — which is exactly the
  point: **a suite of inputs made by one program can only test what
  that program happens to get right**. `derive_now.py` reads 4 of
  `synth-now-mixed.now`'s 15 blocks — three odd regions, each of which
  stops its member's walk — and every block of every archive Now
  Compress itself wrote (docs/formats/now-compress.md).

- **A rule fitted to the blocks in front of it.** `derive_now.py` read
  where a shape-3 stream starts out of the block header, and that rule
  — "16 minus header byte 4" — was exact on the 75 blocks it was
  derived from and wrong on 20 of the 1995 archive's 306, where that
  byte is zero and the correction is `mod 16`. The tool catches such a
  thing only because the header states the same number twice and it
  checks the two against each other; where a format states something
  once, a rule fitted to what is at hand is worth what the sample is
  worth (docs/formats/now-compress.md, *The header*).
- **A degenerate match.** A single-leaf Huffman tree decodes any
  number of copies of one byte from nine bits that occur in almost
  any file; `derive_huffman_tree.py` refuses such matches, and the
  reason it does is that one of them was reported as a confirmation
  on 2026-09-20 before anybody looked at it.

## The 68000 profile (`tools/m68kprof.py`, not in `ci.sh`)

**It ranks; it does not price.** The tick probe on an emulated Mac Plus
(`tools/vmac/README.md`, `UNC_AT_TIMING`) is what prices a change. This
is what says WHERE to look, and it has found the hot spot for every
decoder rewritten since 2026-09-19 — including three that x86 counts
ranked wrong or not at all.

It reads a `qemu-m68k -d exec,nochain,in_asm` log: per-function
instruction counts, then the hottest basic blocks with `file:line`
through `addr2line`.

    m68k-linux-gnu-gcc -static -std=c99 -g -Os -mcpu=68000 \
      -fno-tree-loop-distribute-patterns \
      -freorder-blocks-algorithm=simple -fipa-icf \
      -Iinclude -Ithird_party/zlib -DZ_TESTW=0 -DNO_GZIP \
      cli/main.c src/*.c third_party/zlib/*.c -o /tmp/me68k
    mkfifo /tmp/q.fifo
    python3 tools/m68kprof.py /tmp/q.fifo /tmp/me68k > /tmp/prof.txt &
    qemu-m68k -d exec,nochain,in_asm -D /tmp/q.fifo /tmp/me68k t fixtures/<f>

The flags are there to make this build resemble the Retro68 one: `-Os`
and `-mcpu=68000` are what ships, and the other three suppress
transformations the Mac build does not get. `nochain` is what makes the
log complete — without it QEMU chains blocks and stops announcing them.
The FIFO keeps a multi-gigabyte log off the disk.

**Read the BLOCKS, not just the functions.** The function ranking
attributes an inlined callee to its caller, so a hot loop can be
invisible in it: on `macburger-helper.hqx` the function list read
`bh_get_bits` 41 %, and the block list showed that 25 points of that
were `bh_refill_line` inlined INTO it — which is where the work
actually was, and where the 2026-09-20 rewrite went (DECISIONS.md, *the
character that was touched three times*).

**What it cannot see:**

- **Cycles.** It counts instructions. A `mulu`, a `divu` or a libgcc
  helper (`__mulsi3`, `__udivsi3`) costs far more than its count says,
  and a memory-heavy addressing mode less. Two changes within a few
  percent of each other are not ranked by this at all — settle them on
  the tick probe.
- **The inliner's actual choices on the target.** This is a static
  Linux binary built by a different GCC from the Retro68 one, so what
  is inlined here need not be inlined there. The `.obj` and the CODE
  ratchet are the check for that.
- **Anything in the Mac shell.** No Toolbox, no File Manager, no
  progress dialog, no allocator pressure — `cli/main.c` drives the
  engine. The shell's share was measured once and is 1.5 % of an
  extraction (FORMATS.md, *What -O3 is worth, and where*), which is why
  this omission is tolerable rather than fatal.
- **Whether the change is worth anything.** −23.0 % of Linux `Ir` was
  −9.4 % of Mac Plus ticks on one rewrite and −35.8 % of 68000
  instructions was −36.7 % of ticks on the next. The 68000 count is
  much the closer of the two, and still not the answer.

## On-Mac layers (not in `ci.sh` — they need an emulator)

7. **Mini vMac replay** (`tools/vmac/run.py`, System 6.0.8 and 7.0.1 on a
   Mac Plus; `tools/vmac/sys30.py` for System 3.0, which needs its own
   driver because that system reads no boot-block shell name): the autotest
   build CRC-32s both forks after reading them back through the real File
   Manager and paints an aggregate to the framebuffer; the host decodes the
   screenshot and compares against the same engine's Linux output
   (`tools/vmac_check.py`).
8. **Mac OS 9 replay** (`tools/vmac/os9.py --launch`, QEMU PowerPC): the
   application is launched from the Finder by keyboard, and afterwards
   the transfer volume — a plain file on the host — is mounted with
   hfsutils and **both forks of every output file are compared byte for
   byte** against `macextract x` — with the auto-unwrap loop ON, because
   this harness launches the INTERACTIVE build, which takes envelopes
   off. (It used `-nr` until 2026-08-27, which is right only for the
   autotest build; `tools/vmac/README.md` has what that cost.)
   **21/21 on the committed sample**, 2026-09-04. It read 18/20 that
   morning, the two failures bombing the application, and the sample
   gained a fixture the same day (BLOCKERS.md, *Withdrawn claims*;
   DECISIONS.md 2026-09-04, *the field nobody assigned*).
   Since 2026-08-28 the
   run also goes to the END of the interaction — the result alert is
   dismissed, SFGetFile is checked to repaint, and Cmd-. quits the
   application — and `--cancel` interrupts the extraction instead of
   waiting it out, with a strict non-empty subset of the entries as the
   pass condition. `--cancel-click` does the same through the Cancel
   BUTTON, with `--click-at` as the control that establishes the test
   can fail (FORMATS.md, *Cancelling, and an 8-bit name*).
   `--encrypted` covers the one path no fixture can reach — the
   password dialog — on an archive it generates, a wrong password
   first (FORMATS.md, *An encrypted archive, through the dialog*).
   SpaceSaver is run by PATH, out of the emulator cache, since its
   specimens cannot be committed; that run reconciles the one name an
   in-place format produces (`archive.sit~1` on the Mac against
   `archive.sit` on Linux) and it found a shell defect on its first
   outing (FORMATS.md, *SpaceSaver on Mac OS 9*).
   **What this layer still cannot see** is a name the Mac cut at 31
   characters, because both sides are compared in the Mac's spelling
   (`run_names.py` is where that lives), and whether an extraction is
   finished or merely paused at 0%: the completion wait is the screen
   going still, which a progress dialog that has not reached 1 % also
   satisfies. Nothing on this tier's sample takes long enough for that
   to fire, and when it does misfire the disk comparison still decides.

9. **Reading the Mini vMac Out volume** (`tools/vmac/run.py --keep-disks`
   then `tools/vmac/checkdisk.py /tmp/vmacrun-*/`): the same comparison
   layer 8 does, on the System 6/7 tier — both forks byte for byte,
   plus names and folder structure, read off the floppy image after the
   run. **73/73 on 2026-09-22**, the 71-fixture sample and two fixtures
   run on their own. It is the layer that grades the UTF-8 fold's
   NAMES: since that day it maps each CLI name through the fold and the
   31-character cut before comparing (`tools/vmac_check.py`,
   `mac_component`), and with the fold disabled
   `derived-800saywhat301j.sit` fails it with three names missing and three
   unexpected.

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
    thing the byte comparisons cannot see. **Mac OS 9 covers all of
    those since 2026-08-28**, through `os9.py` rather than this driver:
    `--cancel` for Cmd-. and the repaint behind it, `19-names.png` for
    the glyphs, and `--cancel-click` for the BUTTON, which needs the
    pointer (`os9mouse.Pointer`) rather than the keyboard route a
    fixture run uses. Nothing on this tier is Mini vMac's alone any
    more.

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
