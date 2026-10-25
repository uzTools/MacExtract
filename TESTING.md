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
   `tools/run_ticks.py`): every fixture the engine extracts must call
   back at least once, and no gap between calls may exceed 32 KB (a
   decoder that never yields freezes the Mac's progress dialog with both
   Cancel routes out of reach). **What it cannot see:** how long a gap
   TAKES — it counts input bytes, not time, so a decoder that spends a
   minute on 8 KB passes. The Mac OS 9 tier is where that would show
   (`os9.py --cancel`).
5. **The Mac shell's sink, allocator and I/O through a mock Toolbox**
   (`tests/run_mac_sink.sh` + `tests/mac_sink_test.c`, `ci.sh` variant
   3b): the shell's own code from `mac/macextract_mac.c`, compiled on the
   host under ASan+UBSan and again big-endian under qemu-m68k, driven by
   the real engine over a spread of fixtures and compared byte-for-byte,
   both forks, against the oracle manifests. **What it cannot see:**
   `RunExtract`, `ExtractOne`, the dialogs and the Toolbox glue, which
   the mock never calls — it builds its own `UncOptions`. Nor a read of
   state nobody set: ASan reports writes past a block, not a load from
   uninitialised stack, and valgrind missed the same field (read 20 times
   per gdb) because stack bytes an earlier call wrote count as
   initialised (DECISIONS.md 2026-09-04, *the field nobody assigned*).
   That class needs MemorySanitizer over the real call chain, and no
   host-side build here has it.
0. **Documentation invariants** (`tools/check_docs.py`, run first by
   `ci.sh`; needs no build; `--fix` regenerates the index). It checks:
   DECISIONS.md's Contents index lists every `## ` entry in file order;
   no document cites another by line number; the version agrees in the
   three places it is written; every `synthetic:` fixture in SOURCES.md
   regenerates the bytes recorded there; the five session-start sizes
   CLAUDE.md advertises (four characters per token, tolerance 25 % or
   half a thousand); the number of smells BLOCKERS.md claims, counted
   from the list; and:

   - **Figures derived from `tools/run_tiers.py`'s model** (since
     2026-10-02): FORMATS.md's three `OVL_SAVED` sentences and the
     bundle's own three terms (images + index = bundle) are held against
     the constants, and the run refuses to pass unless bending two of
     them is caught. It was also failed from outside once (one `123,776`
     changed by hand to `123,777`). **Cannot see:** the twelve
     per-format rows of *What each format is granted* — those are
     `run_tiers.gain()` of a set of images; re-take them from that
     function rather than by hand.
   - **Figures derived from the corpus** (since 2026-10-06): the
     differential suite's size (the manifests), the robustness suite's
     (`run_robustness.variants`, ten per manifest whose format is
     implemented and whose fixture is present — four truncations and six
     bit-flips), and the sniff sweeps' population (every non-`.md` file in
     `fixtures/`). Seven named sentences are held — two had said
     *"9,490 robustness variants"* and three *"955 corpus files"* — and,
     since 2026-10-07, the same three counts are scanned as a CLASS:
     any figure in a per-kind window next to "fixtures", "robustness
     variants" or "corpus files", in the five files a session reads as
     current, must be today's count or be DECLARED historical in
     `CORPUS_HISTORICAL` (DECISIONS.md 2026-10-07, *the seven sentences
     that were not the class*). `fixtures` is scanned in 900..1,200, so a
     year or one format's count is not matched. Bending each count, and a
     planted near-miss sentence, must report. **Cannot see:** a figure
     outside the window, a corpus-size claim phrased without those three
     words, or BLOCKERS.md, excluded on purpose (its rows quote the corpus
     a withdrawn claim was measured against). A reworded named sentence
     reports *"this check has stopped checking"*.
   - **DECISIONS.md's entry dates** (since 2026-10-07): non-decreasing in
     file order and none in the future (22 references across ten files
     had been written a day ahead). Bending one date each way must be
     caught. **Cannot see:** a date that is wrong but neither in the
     future nor out of order; and it takes the machine's clock as the
     authority.

   **What it cannot see overall:** whether an entry is in the right
   file, whether a citation points at a section that still exists, or
   whether a paragraph re-narrates one that lives elsewhere — the failure
   mode these documents actually have (CLAUDE.md, *Writing things down*).

0b. **Tuple truth** (`tools/check_tuple_truth.py`, in `ci.sh` since
   2026-09-25, beside check 0; no build, about a second): a Python
   function whose every `return` carries a tuple of two or more must
   never be tested for truthiness, because a tuple is never falsy.
   `--selftest` alone runs the case it was written for; the full run does
   that first and refuses to report a pass it could not have failed. Pass
   a directory to check another checkout. **What it cannot see:** a
   function returning a tuple on some paths and a scalar or `None` on
   others (not flagged, nor the `if x: return a, b` / `else: return c, d`
   shape); any call it cannot resolve to a module-level `def` in this tree
   (a variable, a dict, `getattr`, a method, a decorator); and truthiness
   reached indirectly (`x = f()` then `if x:`) — only a call written
   directly in the boolean position is examined.

## The oracle

The oracle is The Unarchiver's CLI (`unar`/`lsar` 1.10.8, Debian
package `unar`), whose XADMaster engine is also our primary reference.
`macunpack` (macutils 2.0b3) is a **second oracle** for the forks `unar`
cannot read — see "A second oracle" below.

### Resource forks on Linux

`unar --help` documents `-forks (-k) <visible|hidden|skip>`. Both
non-skip modes write an **AppleDouble container** beside the data fork;
manifests are built from `-k hidden` (`._<file>`) rather than the default
`-k visible` (`<file>.rsrc`), because the suffix form is ambiguous (an
archive holding both `X` and `X.rsrc` — every THINK C project — cannot be
represented) and hits a GNUstep bug on a leading `~` that writes the
container into the data-fork filename (DECISIONS.md 2026-08-08, *the
undecidability was the oracle's fork convention, not the archives*).

Manifest building parses the AppleDouble (magic `0x00051607`; entry
id 2 = raw resource fork, id 9 = Finder info with type/creator) —
`tools/make_manifests.py::parse_appledouble`. The manifest records
neither convention, only entry names and per-fork hashes.

**A resource-only entry produces only a `._X` file**, because unar
writes nothing for a 0-byte data fork: an empty data fork, not a lost one
(confirmed against `lsar`'s `XADIsResourceFork` and the container's entry
ids).

`macextract` writes `<file>.rsrc` by default and `._<file>` under
`--forks hidden`; the differential harnesses pass that flag. The default
convention is covered by `tests/run_collide.sh` (in `ci.sh`): with
default forks `derived-Unzip101.sit` must fail the one entry whose data
fork lands on another entry's sidecar and keep the fork already written,
with `--forks hidden` it must extract whole, and `--overwrite` must
restore write-over-anything. It fails against the pre-fix binary.

### Exact oracle invocation

```
lsar -j -nr -e <enc> <fixture>         # format name + metadata (JSON)
unar -nr -D -f -q -k hidden -e <enc> -o <tmpdir> <fixture>
```

- `-nr`: no recursion — each manifest describes exactly one container
  layer (nesting is tested by chaining layers).
- `-e <enc>`: pin filename decoding so manifests are deterministic.
  **`macintosh` for every format but StuffIt 5, whose names are the
  archive's own UTF-8** and which gets `utf-8` (`make_manifests.py`,
  `ORACLE_ENCODING`; DECISIONS.md 2026-09-22, *a name an HFS volume can
  hold*). The first `lsar` is trusted only for the FORMAT; a format with
  its own encoding costs one more call. Each manifest records the
  invocation it was built with, in `oracle`.
- `-D`: no wrapper directory.

### Manifest format

`fixtures/manifests/<fixture>.json`: fixture sha256/size, lsar format
name, and per entry: name (UTF-8, NFC-normalized), data fork
sha256+size, resource fork sha256+size, type/creator and `finder_flags`
when the oracle exposes them, and `oracle_methods` — the compression
method(s) `lsar` names for that entry (`XADCompressionName`, a list).
Nothing in the engine reads it.

Plus `comment`, for an archive that carries one
(`lsarProperties.XADComment`); absent means "no comment", never "not
looked for". `tools/run_diff.py` requires `<fixture>.comment.txt` to hold
exactly those bytes in MacRoman and `macextract l` to print the line; an
archive with no `comment` key may write no such file (the "unexpected
output" check, which found five of the seven). **Seven fixtures in the
corpus carry a comment** (measured by sweeping all 928 with `lsar`): six
Compact Pro archives (`derived-DigSim_RAM_Circuit.cpt` and the five
Compact Pro Package installers) and `derived-MUSFMT10.ZIP`'s 495-byte
end-of-central-directory comment. All seven are graded.

And `ungraded`, for a fixture that needs one: the fields no oracle on
this machine can adjudicate, with the reason beside each (next section).

### The Finder metadata, and the one field no oracle settles

`run_diff.py` lists with `macextract l --finder`, which prints type,
creator and Finder flags as hex; the padded columns misplace the name
when a code holds a space or NUL, and **200 of the corpus's 5,539
type/creator codes hold a space** (measured 2026-10-04; DECISIONS.md
2026-10-04, *the column that moved the name*).

The flags are graded wherever the ORACLE recorded them — AppleDouble's
`fdFlags` where `unar` wrote a sidecar, `lsar`'s `XADFinderFlags`
otherwise (they agree on all 423 entries where both are present). **A
manifest built before 2026-10-04 carries no such key and grades nothing
here**, so `run_diff.py` prints the number of entries it compared. Across
the corpus 3,195 entries would be gradeable and the engine agrees with
`lsar` on every one (measured 2026-10-04); backfilling means rebuilding
manifests.

**The dates are graded nowhere, and for zip's `0x334d` nothing can grade
them:** XADMaster adds `CrGMTOffs`, deark subtracts it, and both label
the result UTC (FORMATS.md, *Zip's Macintosh extra fields*). The fixture
that carries the field DECLARES the exclusion:

```json
"ungraded": { "dates": "XADMaster adds CrGMTOffs and deark subtracts it ..." }
```

`run_diff.py` refuses any other key under `ungraded`, requires a
non-empty reason, and prints every declaration on each run;
`make_manifests.py` carries the key across a `--force` rebuild.

**What this cannot see:** whether the dates are right; the flags of any
entry whose manifest predates the field; and anything the oracle does
not report at all (an absent value is never compared and never excused).

**What the fixture costs** (2026-10-04, the sanitizer build):

| | cost |
|---|---|
| `run_diff.py`, this fixture alone | **0.51 s**, median of 5 (0.03 s for `derived-MUSFMT10.ZIP`); five diff variants, so **~2.6 s** a run |
| `run_robustness.py`, its ten variants | **2.8 s**, median of 3, in three variants: **~8.4 s** a run; the truncations cost nothing (a zip is read from its end) |
| the slowest single variant | **0.51 s** against the suite's 30 s timeout: 59× of headroom |
| `fixtures/` on disk | **+31,167,318 B** on 72 MB, +41 %, and 10.5× the previous largest fixture |

**Time the fixture, not the suite:** suite wall clock on this machine
varies by more than the whole quantity (eleven suites took 489 s with the
fixture and 511 s without it).

### When the oracle fails on an entry

`unar` sometimes fails on individual entries while walking the rest
fine. `make_manifests.py` records what the oracle produced and marks the
forks it failed on, per entry:

```json
"unadjudicated": { "data": "Attempted to read more data than was available" }
```

with that fork's size and hash **omitted**. The classification is by
condition, never by fixture name: exit non-zero plus a per-entry failure
report, and two cross-checks — the parsed failure count equals the total
unar prints, and every name it reports is an entry `lsar` lists — or the
manifest is refused (DECISIONS.md 2026-08-08, *"the oracle cannot read
it" was the harness throwing evidence away*).

`run_diff.py` skips those forks, requires the entry to exist anyway,
prints the running total on every run, and fails a manifest where a hash
and a reason sit beside each other, or where neither does.

### A second oracle

Every fork `unar` leaves unadjudicated is offered to **macutils'
`macunpack`**, and the ones it decodes are recorded with per-fork
provenance:

```json
"data_oracle": "macunpack (macutils 2.0b3, -m32)"
```

Build it with `sh tools/build_macunpack.sh`, which copies the read-only
`reference/macutils` tree to `build/macunpack/` and patches the copy (two
C99/makefile fixes, neither changing behaviour). `make_manifests.py` uses
it if present and silently does without; `./ci.sh`'s `make clean` deletes
it, and re-running the script is a no-op when the binary exists.

**`-m32` is load-bearing:** `get4()` returns `unsigned long` into a
`long`, so the sign test that selects a *stored* method-6 segment is only
reachable with a 32-bit `long`; built LP64, `macunpack` dies with
"Premature EOF" on the branch `tools/synth_sit6.py` exists to adjudicate
(measured 2026-08-08).

Matching an entry to the files `macunpack` wrote is a prediction, and
the builder refuses rather than guesses: names go through the
`transname.c` table parsed out of the reference (plus the leading-dot
rule, because the build passes `-DNODOT`), a name two entries share is
refused, and a missing `.data` counts as an empty fork **only** when the
entry's `.info` file is present.

**`make_manifests.py --force` erases what other tools wrote.**
`tools/run_ddforks.py --write`, `tools/vmac/diskdoubler.py --adjudicate
--write-manifest` and `tools/run_ddtf.py --register` put adjudications
into manifests. The `--register` ones survive (the loop keeps any
manifest whose `oracle` is not `unar`); **the other two do not**, because
their manifests ARE unar's — a forced whole-corpus rebuild silently cost
11 adjudicated forks across `derived-LHA_Expander_1.0.3.sea` and
`derived-Terrainman_2.0__.sea` on 2026-09-22. Re-running them is
order-dependent: `run_ddforks.py` pairs entries **by the data fork's
hash**, and on those two fixtures the data fork is one the emulator
graded, so the emulator goes first. After a whole-corpus rebuild check
those two manifests; `git checkout` is the cheap answer when nothing about
them changed.

### A third oracle (`tools/build_deark.sh`)

Forks `unar` AND `macunpack` leave open are offered to **deark**,
recorded the same way (`"data_oracle": "deark (Deark version: …)"`). It
was brought in because `unar` decodes ARC/PAK method 0x0b (Distilled)
**wrong** on 6 of the 10 members of `derived-INTRECHO.pak` (BLOCKERS.md).
`sh tools/build_deark.sh` copies `reference/deark` to `build/deark/` and
builds it; nothing is patched and it needs only a C compiler.

**It also cross-checks the 23 forks macunpack alone had graded**
(since 2026-09-21) and agrees with every one; such a fork records both
(`"macunpack (…) + deark (…)"`), and a DISAGREEMENT is printed and
nothing is rewritten. It reads both forks (via its AppleDouble `.adf`
sidecar), Zip (including Implode entries `unar` fails), Gzip, Compress and
tar — and given a `.gz` or `.Z` it carries on into what it finds inside.

Rules in `make_manifests.py`'s deark path, all in `deark_forks`
(DECISIONS.md 2026-09-22, *the oracle asked about everything else*):

- **Matching is by the name deark WRITES**: `deark_name()` models its
  sanitiser (`de_char_to_valid_fn_char`,
  `reference/deark/src/deark-util.c`), which mangles folder separators to
  `_`; a mangled name two entries share is refused.
- **A fork deark DECLINED is not a fork it read as empty.** The errors
  deark attaches to a fork make it **None**; an error it cannot attach to
  a fork makes every absent fork of that archive unknown (over-cautious
  on purpose). A member whose every fork was declined writes no file and
  is still carried, its unnamed forks **unknown** (2,324 forks across the
  corpus). Error names are MAKE_PRINTABLE (`Icon<\r>`), so
  `deark_err_name()` reverses the escapes first
  (`reference/deark/src/deark-ucstring.c`, `ucstring_to_sz`); 382
  declined forks across 35 fixtures had been mis-keyed, none of them live.
- **It does not fail on a damaged file — it PADS** (`sitdoc.sit`: 286
  bytes whose last 52 are invented zeros, where the file ends 52 short).
  So deark fills a gap only when the fork is **empty**, or when the
  entry's methods are all ones deark is the designated oracle for
  (`DEARK_METHODS`, currently Distilled). Everything else it is offered is
  a cross-check.

**What this still cannot see:** deark credits macunpack **as
documentation** for method 6 (`reference/deark/modules/stuffit.c`), so on
that method they are independent implementations but not independent
readings — a misreading shared with macunpack does not show (the same
caveat applies to `unar`). It does not read DiskDoubler, and fails
whole-archive far more often than `unar`.

**What this layer cannot see:**

- **An unadjudicated fork is checked only by the archive's own CRC-16**,
  written by the same compressor; a decoder bug that reproduced the CRC
  would pass. (The `derived-New_Python.sit` fork — 23,987 bytes — has
  since been agreed by the second oracle.)
- **An entry the oracle names as out of v1 scope is graded on its name and
  on anything the engine did write — not on its forks.** That tolerance
  is **unused as of 2026-10-07**: `ORACLE_OUT_OF_SCOPE` held only
  `Implode`, now implemented; Shrink and Reduce went to deark through
  `DEARK_METHODS` instead. The mechanism stays.
- Do not read "unadjudicated: 9 forks" as 9 defects. It is **9
  forks across 4 fixtures**, measured 2026-10-07, where two
  implementations cannot be compared: 2 in `arcplus712.zip`, a stored
  entry whose checksum unar calls wrong, so **both sides decline**; 4 in
  the 1995 Now Compress archive, graded under emulation by the archive's
  own extractor (`nowcompress.py --adjudicate`); and 3 across the two wild
  StuffIt Optimizer fixtures, where both oracles fail and
  `tools/run_sitopt.py` grades them three other ways. The number
  `run_diff.py` prints is the measured one.

### Asking the third oracle about everything (`tools/sweep_deark.py`)

`make_manifests.py` offers deark only what the others left open. This
sweep asks it about **every fixture that has a manifest** and compares
everything it produces against every hash the manifest holds, from
whatever oracle. It writes nothing: a disagreement is a finding, not a
manifest edit. Not in `ci.sh` (an audit, and it needs the fixtures; it
skips cleanly without them).

    sh tools/build_deark.sh        # ./ci.sh's `make clean` deletes it
    tools/sweep_deark.py [--fixture NAME ...] [-v]

**2026-09-22: 4,556 graded forks across 728 of the 932 fixtures, 2,151
agree, 0 disagree.** The other 2,405 are named, not counted as agreement:

| verdict | what it is |
|---|---|
| `padded` | longer than the graded fork, prefix hashes to it, tail all zeros. **6** — the six resource forks graded from the container's own arithmetic, so deark agrees byte for byte on what is present |
| `wrapped` | deark does not unwrap MacLHA's MacBinary payload; reported only after the container's data fork is checked against the graded one. **3** |
| `declined` | deark said it could not read this fork. **2,396**, nearly all StuffIt method 13 and StuffIt 5's Arsenic; 8 are the blanket for an error naming a member but not a fork (`synth-arc-mixed.arc`) |

**What it cannot see, and it prints this every run:** **10** entries
deark neither named nor declined:

| | |
|---|---|
| **7** Gzip and Compress | deark goes one layer FURTHER than the manifest (`unar -nr`) describes and writes the tar inside |
| **1** StuffIt 5 | `.typeAttributes.dict` in `derived-PuzzleGetter_0.8.sit`, both forks empty; deark writes no file for it (`do_pre_decompress_fork`, `reference/deark/modules/stuffit.c`). The only entry of that shape |
| **1** uuencode | `synth-uu-mac.uu` stores its name in quotes; `unar` strips them, deark keeps them |
| **1** ARC | `synth-arc-mixed.arc`'s method 7, declined in an error naming the member and not a fork — the blanket costs 8 more forks there on purpose |

Tar members are stored as `./NAME`, which deark writes as `._NAME` —
not an AppleDouble sidecar; the sweep matches that alias (98 forks in
`derived-PCCTS.tar`, all agree). The denominator is printed per format,
with entries whose mangled name another entry claims (**0** today), and
**4** forks nobody has graded (the oracle failed and no second
implementation filled them).

### The container's own arithmetic — not an oracle, the file itself

A MacBinary is a 128-byte header, the data fork padded to a multiple of
128, then the resource fork, all stored — so for a damaged MacBinary that
`unar` declines and deark pads, what is present is the file's own bytes.
`make_manifests.py`'s `adjudicate_from_macbinary` runs **last**, after
all three oracles, and records such forks as `"MacBinary container
arithmetic"` (eight forks in seven fixtures).

**It refuses to grade unless the arithmetic is confirmed on that file**:
the header's **CRC-16/CCITT** over its first 124 bytes matches the value
at +124 (MacBinary II — `guysmaccontacts.sea`), or the entry's **other
fork is already adjudicated** and reproduced byte for byte by the same
arithmetic (the six MacBinary I fixtures). Where an oracle and the
arithmetic disagree it grades nothing there and says so.

**What this cannot see:** the bytes that are missing, and any compressed
fork — every MacBinary fork is stored, which is why this generalises to
no other format. The layout itself reproduces both forks of **174
undamaged MacBinary fixtures** with no mismatch. DECISIONS.md 2026-09-22,
*the container is the oracle*.

### When our engine declines an entry

A per-entry error from `macextract` is tolerated in exactly two cases, and
**both are the oracle's word, never ours**:

- the oracle failed that same entry (it is `unadjudicated`), or
- the oracle names the entry's compression method as one v1 does not
  implement — `oracle_methods` against `run_diff.py`'s
  `ORACLE_OUT_OF_SCOPE`, **which is EMPTY since 2026-10-07**;
  `out_of_scope()` still runs on every entry.

**One decline is deliberately NOT eligible, and must never be made so:**
an entry whose method byte says a StuffIt 2.x Optimizer ran fails
`UNC_ERR_MODULE` here, while `unar` 1.10.8 writes the PREPROCESSED bytes
and **reports success** (measured 2026-09-28) — so an excuse anchored to
the oracle would excuse the wrong answer. No corpus fixture sets the flag
(FORMATS.md, *Where an archive names the module*).

Which of OUR errors is eligible is `said_unsupported()`, which matches
the END of the message (the line names the method where the format
states one). **The excuse is still the oracle's**; this only decides
eligibility.

Anything else fails the fixture, including a non-zero exit with no
per-entry report and every whole-archive error. An adjudicated fork is
compared or missing — absence is excused only for out-of-scope entries.
Anchoring the excuse in our own output had discarded ground truth and
could not fail (a stub binary passed `derived-Export.sit` as a skip; it
fails now) — DECISIONS.md 2026-08-08, *an excuse must be anchored
outside our own output*.

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

**Synthetic fixtures are restored by running their generator**:
`synthetic:<script>` in SOURCES.md, which harvest.py calls with `-o
<path>`. `--restore` needs a network and never runs in `ci.sh`, so
`check_docs.py` regenerates every synthetic line and compares the sha256
— the only part of the restore path that can be checked offline.

## Running everything

```
./ci.sh          # full matrix; must be green before every commit
```

**A full run is ~20 minutes** on two cores (measured 2026-10-06, v0.33.0
corpus): the three robustness lanes **342 s**, the eight native builds
**136 s**, the five diff lanes **120 s**, the mac sink **103 s**, the overlay
host lanes **93 s**, and no other single suite over 55 s. `run_robustness.py`,
`run_diff.py`, `run_walk.py` and `run_ticks.py` take **`-j/--jobs`**, default
one per CPU; `ci.sh` exports `MAKEFLAGS=-j$(nproc)`, and
`tests/run_mac_sink.sh` starts its six whole-program compiles together.
**Nothing about the output depends on `--jobs`** (checked byte-for-byte
against the serial run, each suite made to fail under a pool); `-j` above
the core count loses time (DECISIONS.md 2026-10-06, *the twenty-four
minutes*).

**A suite run by hand needs a `make` first.** `ci.sh`'s second step is
`make clean` (`rm -rf $(BUILD)`, `BUILD ?= build`), and every later build
goes to its own directory (`build/san`, `build/ars`, `build/ars1`,
`build/lzwlen`, `build/sit14stack`, `build/m32`, `build/rel`,
`build/off32`, and cmake's `build/mac`, `build/mac-lazy`,
`build/mac-resident`) — so a green `ci.sh` leaves no `build/macextract`.
Most suites then say `no CLI at <path>`, exit 1; **if a suite dies with a
traceback rather than a message, check for the binary before believing
anything about the suite.**
## M9 additions

4. **Envelope unwrap tests** (`tools/run_unwrap.py`, in CI): chained
   fixtures (.sit.bin, .sit.hqx, .tar.Z) extracted with auto-unwrap
   must match the inner layer's manifest exactly, with the
   intermediate file removed. The single-layer diff harness passes
   `-nr` to disable unwrapping. It also builds two nameless gzip layers
   in a file called `Same`, whose inner entry has the envelope's own path
   (DECISIONS.md 2026-10-14, *the layer that had its envelope's name*).
5. **Budget sweep** (`tools/run_budget.py`, not in `ci.sh`): the whole
   corpus under `--budget 409600` (a small Mac). Everything verifies
   fully except part of StuffIt 5/Arsenic — **25 of 32** fixtures (2026-10-25), the
   rest giving a clean per-entry "out of memory". Results in FORMATS.md.
5b. **Application size** (`tools/check_app_size.py`, in `ci.sh` since
   2026-09-23): fails when the linked `MacExtract.code.bin` moves more
   than 2,048 B from a committed figure (every byte is resident heap on
   the target). **What it cannot see**: whether the move MATTERS — only
   `tools/run_tiers.py` can say whether a fixture flipped, which is why
   the failure message sends you there. Nor A5 growth, nor anything in a
   build without the Retro68 toolchain, where it skips.

6. **Fuzzing** (`tools/fuzz.py`): seeded, reproducible
   mutation/splice/magic-garbage cases through `macextract t` under the
   sanitizer build, plus three generators for what those reach nothing
   of: a fourth that flips one to four bits in an encrypted archive
   `tools/synth_crypt.py` wrote and runs `macextract x -p` on it, a fifth
   that repairs the checksum it breaks in a Now Compress block, and a
   sixth that mutates a NAMED seed inside the ranges its generator calls
   compressed. Nonzero exits are fine, signals/sanitizer aborts/hangs
   fail. Every CI run does a 150-case smoke (`-n 150 --seed 7`), a
   quarter of it the ciphers, in ~3 s. A failing case is moved to
   `--keep-dir` with `shutil.move` (an `os.replace` across filesystems
   once swallowed the FUZZ FAIL line; DECISIONS.md 2026-10-06, *the sort
   that dropped what it could not hold*). **A mutant is graded by
   nothing**, here as everywhere in this file; what is graded is the seed.

   **Ciphers: one seed per shape, every one reached.** `synth_crypt.py`
   writes ten shapes in pure Python — StuffIt classic's DES, StuffIt 5's
   RC4, PackIt's XOR and DES, Compact Pro's, ARC's garble, PKWARE's zip
   cipher, WinZip AES at 256 and 128 bits, and Private File's MD5-keyed
   RC4 (`tools/synth_pf.py`). `zip -P`, `7z` and `arc` cannot be the
   encoder (clock-seeded headers, random salts, not installed). Every
   shape is checked by somebody else's reader (*Decryption*, below;
   DECISIONS.md 2026-09-26). Seeds are taken **round robin**, and half
   the flips land inside the bytes the reader hands to a cipher
   (`synth_crypt.py --ranges`).

   **What it reaches** — `tools/fuzz_reach.py` (not in `ci.sh`: it
   rebuilds the engine once per site and takes minutes) plants an
   out-of-bounds store in one cipher's key setup, checks on the UNMUTATED
   seed that the fault fires, and counts the mutants that trip the
   sanitizer. Neither the exit code (a `t` run exits 0 having decrypted
   nothing) nor `t` (it never descends into a MacBinary) can measure
   this, which is why the crypt cases EXTRACT. 30 mutants a shape, seed
   11, 2026-09-26 (the `pf` row 2026-10-09):

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
   | `pf` | `unc_crypt_pf` | 27 | **29** |

   "Flips anywhere" is `fuzz_reach.py --untargeted`. The last `zip-aes`
   row is the site past the password verifier, which `unc_crypt_winzip_aes`
   is not. The 2026-09-23 PackIt 0 is withdrawn (BLOCKERS.md, *Withdrawn
   claims*). **3,000 crypt-only cases and 2,000 mixed ones, clean** (seeds
   101 and 202, 2026-09-26, all nine shapes).

   **Decoders: `tools/fuzz_cover.py`** (gcov, every decoder at once).
   3,000 cases, seed 11, engine sources only, 2026-09-27:

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

   **The fuzzer's reach is the corpus's coverage**: three of the four
   generators mutate a corpus fixture, so a method graded only by
   GENERATING a file is fuzzed not at all until it has a seed. Seeds
   since added, and what they did:

   - **Now Compress** — the fifth generator flips bits inside a block's
     payload and recomputes its 32-bit trailer with `tools/mutate_now.py`'s
     `fix_trailer` (the sum that hid this project's one decoder heap
     overflow from every mutant); then `now_seeds()` writes
     `synth-now-delta`, `-delta-small` and `-delta-neg` for
     `now_find_delta`. **Now Compress: 13 functions, 0 never entered, at
     seeds 11 and 12 over 3,000 cases.** `ci.sh`'s smoke treats a seed
     with no blocks for the repair generator as a failure, not a skip —
     deleting `derive_now.table_delta` turns `ci.sh` red (measured).
   - **StuffIt method 14** — the sixth generator (`--stream-only`,
     `--stream-shape`; `synth_sit14.py --ranges` reports its streams).
     3,000 cases, when the seed was four streams of 1,859 B:

     | | seed 11 | seed 12 |
     |---|---|---|
     | of 11 functions, never entered, before → after | 1 → **0** | 1 → **0** |
     | `sit14_lengths_coded` (the nested tree) | 0 → **100 %** | 0 → **100 %** |
     | `sit14_tree` | 50 → **100 %** | 50 → **100 %** |
     | `unc_sit14_decode` | 92.5 → **95.5 %** | 89.5 → **95.5 %** |

     `--stream-untargeted` (named, mutated anywhere) reaches 95.5 % of
     the entry function; targeting reaches **98.5 %**. **It can fail**:
     the 2026-10-03 signed-counter defect, planted again — **400
     `--stream-only` cases: 11 failures**; the old instrument at 3,000:
     none. **`ci.sh`'s 150-case smoke does NOT** reliably catch that
     shape (about a quarter of the time; seed 7 misses) — it is a
     regression guard.
   - **The method-14 window wrap** — `synth_sit14.py --wrap` adds an
     entry whose fork is 278,896 B (BLOCKERS.md, *Withdrawn claims*, for
     the figure that hid it). 3,000 mixed cases, `--stream-shape sit14`
     for the before:

     | | seed 11 | seed 12 | seed 13 |
     |---|---|---|---|
     | `sit14_flush`, before → after | 55.6 → **100 %** | 55.6 → **100 %** | 55.6 → **100 %** |
     | every other method-14 function | unchanged | unchanged | unchanged |

     Only `--detail` can see this change (the family reads 0 of 11 either
     way). Over 400 `--stream-shape sit14-wrap` cases the wrap branch runs
     **210, 205 and 202 times** at seeds 11, 12 and 13 (executions, not
     cases; the unmutated seed wraps once in 15 flushes).
   - **Zip Implode** — `tools/synth_implode.py` is an encoder (nothing
     here writes Implode); its seed carries all four flag-word
     combinations. 3,000 cases, `fuzz_cover.py`'s `Zip Implode` family:

     | | seed 11 | seed 12 |
     |---|---|---|
     | of 5 functions, never entered | **0** | **0** |
     | `imp_build`, `imp_flush`, `imp_read_lengths` | — | **100 % of lines** |
     | `imp_decode` | — | **88.9 %** |
     | `zip_implode` | — | **93.8 %** |

     The lines left are allocation-failure returns and two corrupt-tree
     exits. `tools/run_implode.py` bends the same streams on every
     `ci.sh` run (*Implode*, below).
   - **Zip Reduce** — `tools/synth_reduce.py`, one entry per factor;
     deark reads all four byte-exact. 3,000 cases, `--stream-only
     --stream-shape reduce`, seed 11: **0 failures under ASan+UBSan**, and
     `unc_reduce_decode` at **100 % of lines** (FORMATS.md, *Reduce*).
   - **`-lh3-`** — `method_seeds()` builds archives with `run_lzh.py`'s
     pure-Python encoder, one archive per case, including
     `lh3_lz_stream()`'s match cases that LHa adjudicates first (no
     `-lh3-` stream written before had a match; BLOCKERS.md):

     | function | before | after |
     |---|---|---|
     | `unc_lzst0_decode` | 0 | **100 %** |
     | `lzs_decode_p` | 0 | **88.9 %** |
     | `lzs_read_tree_p` | 0 | **64.3 %** |

   - **`-lh2-`** — a COMMITTED seed, `tools/seeds/lh2.lzh`, 4,896 B,
     because only the patched LHa writes the method. To remake it: `sh
     tools/build_lha_lh2.sh`, then compress a repetitive text and 6,000
     bytes over a 64-symbol alphabet with `lha ao2q10`. **`src/unc_lzdyn.c`
     goes from 16 of 16 functions never entered to 1**: `lzd_reconst`,
     which wants 32,768 codes and is covered by `run_lzh.py`'s graded
     set instead (`lzd_update_p` stays partial: 32,768 MATCHES).
   - **DiskDoubler 3, 4 and 5** — committed seeds `tools/seeds/dd-Rle2.dd`,
     `dd-HuffDeep.dd` and `dd-Splay128.dd`, written by
     `tools/vmac/ddencode.py --build` (no emulator), round-tripped here and
     read by Salient's 1991 expander (`ddencode.py --expand`). **Method
     7** became a FIXTURE instead, `dd37-IACUtilities-A4.lib.dd`, lifted
     from Salient's disk by `harvest.py`'s
     `derived:hfsvol:<image>:<mode>:<HFS path>` scheme (mode `r`, the
     data fork alone; the HFS path keeps its leading separator). `unar`
     names it `Stac LZS` and agrees on the 2,226-byte resource fork.
     **DiskDoubler is at 0 functions never entered.**

   **Named seeds are drawn on one case in 32** (`--named-share`;
   `--no-weight` is the old pool behaviour and reproduces its runs), so
   each is drawn about six times in 3,000 cases and the corpus keeps
   97 % of the draws; `-lh2-` then reads 1 never entered at seeds 11, 12
   and 13 alike. 1/16 bought nothing (total never-entered 174/163/156
   against 147/137/150).

   `fuzz_cover.py` reports how many engine functions fall in NO family —
   **385 of 586**, re-read 2026-10-06 — so a prefix nobody adds a row for
   is visible. Two family regexes that could not report (method 14 inside
   "StuffIt classic"; BinHex's `bh_`) are withdrawn in BLOCKERS.md.

   **How much of this table to believe.** Per-family counts are noisy:
   seeds 11 and 12 over an identical build differ by up to **thirteen**
   functions in a family (ARC 0 against 13, measured 2026-10-05). **A
   single-run delta in a family is not a finding** (BLOCKERS.md,
   *Withdrawn claims*); what survives repetition is the whole-family
   signal. A 400-case run is mostly sampling noise.

   **Bending a constant** is the way to tell a load-bearing one from a
   decorative one: `unc_lzah.c`'s window preload bent five ways — the
   pattern and an all-spaces fill both give **933/933**; zeros, `0xAA`
   and a bent pattern give 932/933, failing `derived-BitMap11.sit`
   (DECISIONS.md 2026-09-28, *the preload nothing reaches*).

   **What none of this can see.** The reach figures are about EXECUTION,
   not what mutants explore inside: one seed per cipher, none over
   2.2 KB, so no cipher's buffer handling is exercised at size. Each
   cipher and each method-14 seed is reached through ONE container (a
   bare `.sit` for method 14; AES in a spanned zip, DES in BinHex,
   method 14 in MacBinary or BinHex are fuzzed by nothing). The only
   signal is a sanitizer abort, so a cipher that decrypts to wrong bytes
   is invisible — that is `run_crypt.py`'s job. Method 14's `goto out`
   after a failed flush is a sink write error no mutant can cause
   (FORMATS.md, *StuffIt 5's method 14*). The wrap seed is not a
   fixture and runs on no Macintosh and under no qemu-m68k (peak heap
   294,528 B), so the wrap is a host-only, little-endian measurement;
   the seeds themselves are graded by `run_diff` against `unar` and by
   `tools/run_sit14wrap.py` (*StuffIt method 14*).

## DiskDoubler and Now Compress joined the graded set (2026-08-15)

Both are in `run_diff.py`'s `IMPLEMENTED` and graded entry-for-entry
against `unar`.

**Now Compress has two real archives**, and the first reaches only two of
the five block shapes; the rest is covered by generated archives (*Now
Compress: the archives the corpus does not have*, below) and by
`test_nowcompress` (a fork-order mutation fails it while the fixture
passes). `unar` cannot decode a byte of the second (DECISIONS.md).

**DiskDoubler forks neither oracle can decode** (11 forks across 2
self-extracting fixtures) are graded by the archive's own expander under
System 7: `tools/vmac/diskdoubler.py --adjudicate --write-manifest` — 33
forks compared, all identical, 3 data forks graded by `ci.sh` on every
run and 8 resource forks still `unadjudicated` because the Mac's copy of
one is never byte-exact (DECISIONS.md 2026-08-21). `run_diff.py` counts
the two kinds separately. The single-file `.dd` container has no fixture;
`test_diskdoubler` covers it and the inline-stored path (DECISIONS.md
2026-08-15).

**The 1990 header** (size 48 rather than 84) cannot have a fixture: the
specimens are made under Mini vMac (`diskdoubler.py --beta`, and
`maccompress.py --make` — MacCompress 3.2, same header) and `unar` cannot
open one. `ci.sh` carries the CONTAINER in `test_diskdoubler` — a 48-byte
header over stored forks, plus negative controls at 47 and 60, both of
which must sniff UNKNOWN. The BYTES are graded on demand by
`diskdoubler.py --beta-verify` and `maccompress.py --check` against what
each application was given; those checks fail 7 ways against the engine
of the day before.

### Method 1 is graded outside `ci.sh`, method 7 inside it since it became a fixture (2026-08-20)

Neither has a URL-fetchable specimen: method 1's are written by
DiskDoubler 3.7 under Mini vMac, method 7's live inside its distribution
disk image. `tools/vmac/diskdoubler.py --wild | --make | --verify`
produces and grades both (`tools/vmac/README.md`). Method 7 has since
gained a fixture (`dd37-IACUtilities-A4.lib.dd`, *M9 additions*).

**`ci.sh` sees method 1 only through `test_dd_stac` and the method 1 half
of `test_diskdoubler`** — unit tests on streams this project wrote. They
grade the transcription against the reference, not against the format;
a regression that agreed with our own encoder would survive them.

### The CC0 corpus, graded against its own originals (`tools/run_ddtf.py`, 2026-08-21)

`ssokolow/diskdoubler-test-files` publishes nine sets of the same seven
files — DiskDoubler 3.7.7 and DiskDoubler Pro 4.1.1, every method their
menus offer — **beside the source files they were made from**, so the
grading is against the bytes that went in:

    tools/run_ddtf.py --fetch          # 564 forks, 0 mismatched (2026-08-21)

63 single-file containers, 9 archives and the same 9 BinHexed, 10
self-extractors and the same 10 BinHexed.

**In `ci.sh` by a different route:** `run_ddtf.py --register` copies the
corpus into `fixtures/` (a `SOURCES.md` row per file, pinned to the
corpus commit) and writes manifests from the published originals, so
`run_diff.py` grades all 107 fixtures on every run (DECISIONS.md
2026-08-21). `run_ddtf.py` itself is how to re-derive that from a fresh
clone — the only thing that can notice the corpus changing. It handles
`Icon` + CR names (DECISIONS.md, *`Icon\r`*).

**What it cannot see**, beyond the docstring's list: it compares forks,
so a regression in dates, type/creator or Finder flags passes (the
sidecars' Finder info was rewritten by the Mac that copied them). It
skips the six `SPLT` parts — `run_segments.py` has the sets.

**It can fail**: 25 mismatches against the build before the `DDA2`
`0x1000` fix.
## The optimized StuffIt archives (`tools/run_sitopt.py`, in `ci.sh`)

**The writer is the oracle.** StuffIt Deluxe 2.0's *Optimizers* rewrite a
fork before compressing it, and `Text 1`'s rewrite cannot be undone, so
the reference for such an entry is `unstuffed.bin` — StuffIt Deluxe 2.0.1
unstuffing its own archive under Mini vMac (`tools/vmac/sitopt.py
--unstuff`).

**Lane 15 is the only one whose subject nobody here made**: two Giga-ROM
CD archives (1992-93) carry a `Text 1`-optimized entry; `run_diff.py`
grades their bytes against `unar`, and this lane grades the six header
bytes a manifest does not record (FORMATS.md, *Two optimized archives
nobody here made*). Changing the 255 to a 1 makes it fail twice
(measured 2026-10-06). How they were found: *Searching somebody else's
index by content*, below.

**A lane for the two wild archives whose module this engine UNDOES** —
`sitopt-wild-Phantom.sit` (`Sound 1`) and `sitopt-wild-DNAnalyze.sit`
(`MacPaint 1`) — runs BEFORE the specimen gate, so a fresh clone with
`fixtures/` restored grades them. Both optimized forks defeat both
oracles (unadjudicated in the manifests; the rest is graded by
`run_diff.py`). It asserts three things none of which is this engine's
output (measurements in FORMATS.md, *Two more, and these the engine
UNDOES*):

* `Sound 1`: the archive's own CRC-16 over the RESTORED bytes; the
  running sum over what `unar` hands back; and **the same `t` failing**
  once the Optimizer bit and id are cleared and the header CRC at 110
  repaired.
* `MacPaint 1`: 12,992 B as declared, a 512-byte header of zeros,
  **720 PackBits rows of exactly 72 bytes with nothing left over**, and
  `deark` reading it with no warning — while it DOES warn about the same
  artwork with its header removed.
* both: `unar`'s own failure text, asserted LIVE, so the day the oracle
  learns the modules is noticed.

**Measured able to fail**: with `sit_opt_decodable` returning
`SIT_OPTDEC_ASIS` for both modules, the lane reports both fixtures and
the rest of the suite reports `OptPaint`, `OptPhoto` and `OptSound`.

Ten assertions over twenty-eight archives 2.0.1 wrote, in fourteen runs —
**everything that application writes with what was in its box**: every
Optimizer, every cipher, every compression word, a 1.5.1-compatible
archive, a folder, and a self-extracting archive:

1. the control — same subject, no Optimizer — extracts to the subject,
   both forks, byte for byte;
2. the two optimized entries extract to **2.0.1's own unstuffed bytes**;
3. neither writes a resource fork (`Text 1` deleted it; `rlen` 0);
4. the header bytes are what `src/fmt_sit.c` reads: `0x40` set on both
   method bytes, 106 and 108 both 255, 46/47/107/109 zero;
5. **the declared lengths**: the `Text 1` entry declares the fork it
   REWROTE; every module with an id left its control's lengths;
6. **`MacPaint 1`**, over a document MacPaint 2.0 drew, records id 4 and
   comes out at the declared length, artwork byte-identical to MacPaint's
   file AND 2.0.1's output, 512 zeros, no resource fork, the user TOLD;
   `Sound 1` (id 1) and `Photoshop 1` (2) come back byte for byte, both
   forks, with silence asserted; the synthetic `JPEG Lossy` (3) entry the
   module could not encode must be refused;
7. **`JPEG Lossy` over two documents Photoshop 1.0.7 wrote** comes out
   **byte-identical to 2.0.1's own restored file**, resource fork
   identical to the ORIGINAL document's, the user told, and must NOT
   equal the original data fork. The dense second document puts the
   output stage's negative branch on 9,645 bytes against 2,127
   (BLOCKERS.md, *Withdrawn claims*; putting `CCOD`+0x3826's correction
   back failed both, 2026-10-02). A third archive at **Q=50** (Annex K
   unscaled) can fail a decoder that assumes the tables instead of
   reading tag 33606, and must differ from the Q=25 one;
8. **Every cipher StuffIt 2.x has**: `DES`, `DESex`, `NewDE™`, `NewDEx`
   and `PassLock`, each over one `Subject` beside a plain archive from the
   same boots, so the BYTES are graded. A wrong password must be refused
   by the four real ones; `PassLock` must extract **without a password**,
   byte-exact, with **nothing** said about a password — also when ALSO
   `JPEG Lossy`-optimized (the loss is still reported) and for a text
   file stuffed protected and plain in one boot. Swapping the two
   primitives in `unc_crypt.c`, or the two modules' ids in `fmt_sit.c`,
   fails four and two assertions; removing the pass-through fails the
   `PassLock` cases (measured 2026-10-02).

Aladdin's own Engine decoded the `Text 1` archive and refused the
`MacPaint 1` one (*"Please use StuffIt Deluxe instead"*); that is graded
as a fact about the Engine.

**What it cannot see.** Whether a `DCMP` and this engine agree on
anything but these archives, over the SETTINGS this project asked 2.0.1
for (two subjects, two qualities, every scriptable compression method,
with and without `PassLock`). Unseen: `Custom Compression…`, the one
method with no script word, and the two encryptor modules this machine
does not have (`NewDE™`, `DES`). The archives are authentic; two SUBJECTS
are part synthetic (`Sound 1`'s generated samples, `Photoshop 1`'s
resource fork built to the module's `COMP` acceptance test). And nothing
on a fresh clone beyond the wild lanes: the specimens are emulator output,
not committed, and the suite skips cleanly without them.

## Every combination 2.0.1 will write (`tools/run_sitcombo.py`, in `ci.sh`)

**Same oracle as above, every parameter varied.** `tools/vmac/sitcombo.py`
asked StuffIt Deluxe 2.0.1 for what one subject per module at the
defaults never could (FORMATS.md, *Every other document 2.0.1 will
optimize*), and each set unstuffed its own archives in the same boot.
This replays 121 of them, 245 checks:

| lane | graded against |
|---|---|
| `JPEG Lossy`, 37 entries: widths 1 to 512, grey, CMYK, HSL, HSB, multichannel, indexed, bitmap, colour, Q=5 and 255, under `DES` and `NewDE` | 2.0.1's own restore, byte for byte; the resource fork against the document, which 2.0.1 rewrites; each must say *"rebuilt"* |
| `Photoshop 1`, 20 entries: two drawn documents under every method and a 1.5.1 archive, and the twelve `--psnew` documents | the document, both forks |
| four Optimizers at once over a folder; `Text 1` under Best Guess and in a 1.5.1 archive | 2.0.1's restore of the folder; `run_sitopt.py`'s own graded controls |
| `MacPaint 1` over a second painting, every method | 2.0.1's restore from byte 512; zeros before it |
| every Optimizer under each built-in cipher; the three plug-ins over optimized entries; empty, resource-only, eight-block and 40 KB forks, a folder and 11 entries per archive | the same entry unencrypted, or the subject regenerated from `sitcombo.py`'s own generator; each encrypted one must refuse with no password |
| two of those archives without their resource fork | the refusal names the missing fork, and never *"does not implement"* |

**Measured able to fail**: the engine before the `JPEG Lossy` rewrite
reports **59 problems** here, 31 of them byte mismatches against 2.0.1's
restores and one the forkless message.

What this CANNOT see:

- **anything on a fresh clone** — the specimens are emulator output in
  `~/.cache/macextract/vmac/specimens/sitcombo/` and are not committed;
  it skips and says so.
- **a coloured document Photoshop drew.** `cdocs/` are built by
  `sitcombo.py --cdocs` in Photoshop 1.0's own layout; what is graded is
  2.0.1's archive and restore, both authentic.
- **a real Sound Designer II file**, which nothing here can make; the
  wild `Phantom` archive grades `Sound 1` (above).
- **widths over 512, heights over 300**, or a quality the module's
  dialog refuses (1..3).

## StuffIt method 14 (`tools/synth_sit14.py`, in `ci.sh` via `run_diff`)

Method 14 appears in no corpus archive; the two real payloads are
Aladdin's installers, neither committable nor restorable (FORMATS.md,
*StuffIt 5's method 14*). `tools/synth_sit14.py` is an ENCODER (from
libxad's `SIT_14`), and `fixtures/synth-sit14.sit` (2,149 B) is graded
against `unar` by `run_diff`, five entries one per shape: literals across
two blocks, the shortest match at distance 1, extra bits on both ladders
plus the **longest match the format can code** (16,387 B), a **nested
tree**, and **a tree whose code lengths ASCEND over the alphabet** (next
section). **Three implementations agree on those bytes** — encoder,
engine, `unar` — which is what makes it evidence rather than a round
trip.

### The sort that dropped what it could not hold

The fifth entry (112 bytes, a complete code with ascending lengths)
failed on the engine the day it was written: `sit14_build`'s transcribed
sort deferred the SMALLER half of each partition onto a 16-deep stack and
silently dropped what did not fit. Fixed by deferring the LARGER half —
**7 at the format's largest, 308, against 16 available**, measured over
4,000 random length vectors and every shaped one (DECISIONS.md
2026-10-06, *the sort that dropped what it could not hold*). **-4 B of
`ovl_stuffit`, and every stack frame unchanged** — `sit14_build` 172 B
before and after.

**A full stack is now an error**, which `ci.sh`'s variant 1d exercises:
a build at `-DSIT14_SORTSTACK=4` must REFUSE the fixture — measured, 5 of
5 entries, exit 1 — where the default build passes. The only lane that
reaches the guard.

**The fuzzer barely sees this shape**: on the PRE-FIX engine, 1 of 500
`--stream-only` cases at seed 12 and 0 of 500 at seed 11; `ci.sh`'s smoke
would catch it about once in 200 runs. The fixture entry is the guard.

**What none of this says** is whether the two real payloads were ever
affected: they are byte-exact against `unar` on every fork (FORMATS.md,
*The two subjects*, measured 2026-10-03 on the defective engine) — a fact
about two files, not the format.

**It can fail**: bending the match-length base by one byte in
`src/sit14.c` fails this fixture and only this fixture, 31/32
(2026-10-03) — so **no other fixture covers method 14**.

**Robustness.** `run_robustness.py` runs ten variants of it under
ASan+UBSan on every `ci.sh` run. **What that cannot see:** most variants
never reach the decoder — the 80-byte banner is 4 % of the file, and a
mutated length field is refused on the allocation budget.

**In `fuzz.py`** as the stream generator (*Fuzzing*, above, for figures
and limits): it reaches every function and every line but a sink-write
failure, at seeds 11, 12 and 13, and found the decoder's one real defect
(a signed left shift, DECISIONS.md 2026-10-03).

### The fork that wraps the window (`tools/run_sit14wrap.py`, in `ci.sh`)

The window is sized to the fork, so `sit14_flush`'s second half is
reached by nothing under 0x40000 B of output. `synth_sit14.py --wrap`
writes an entry of **278,896 B of fork for 458 B of stream**, one wrap on
an in-loop flush and 16 KB decoded after it. It is **not** in
`fixtures/synth-sit14.sit`: its peak heap is **294,528 B** against the
fixture's 65,152 B, which one of the two 512 KB tiers refuses (FORMATS.md,
*What each format is granted*). So it is generated in `ci.sh` and graded
THREE ways: the encoder's input, `unar`'s output, and this CLI's. All five
entries agree byte for byte.

**It can fail, three ways, each checked** (18 checks): `win - a` bent to
`win - a - 1` in `src/sit14.c` fails only the `window-wrap` entry (first
wrong byte at 262,143), while the committed fixture extracts identically;
shortening the case to ten matches, or growing `SIT14_WINDOW` to
0x80000, makes the suite say the entry no longer wraps.

**What it cannot see.** The flush SCHEDULE is mirrored in Python
(`flush_points`), taking `SIT14_WINDOW` and `SIT14_WINMIN` from
`src/sit14.c`; a change to the threshold (`pos - flushed >= win >> 2`) or
to where the flush is called leaves the mirror saying "wraps" while the
branch goes uncovered — re-read `sit14_flush`'s line percentage with
`tools/fuzz_cover.py --detail "StuffIt method 14"`. It is correctness on
ONE archive, and nothing in this lane runs on the Macintosh or
big-endian.

**Big-endian:** `tests/run_mac_sink.sh` carries the 2,149 B fixture, so
the decoder runs under qemu-m68k through the Mac shell's sink on every
`ci.sh` run; the same bent base fails `mac-sink` on this fixture alone.
The application ran it on four emulated tiers (FORMATS.md, *Run on a
Macintosh*).

**What none of it sees:** the two real payloads, re-run by hand
(FORMATS.md, *StuffIt 5's method 14*).

## The forks `unar` refuses (`tools/run_ddforks.py`, on demand)

`unar` 1.10.8 fails on 11 of the 33 DiskDoubler DDn forks in
`derived-LHA_Expander_1.0.3.sea` and `derived-Terrainman_2.0__.sea` with
*Attempted to read more data than was available*: its DDn reads one byte
past the fork's declared compressed length; the codec is correct
(DECISIONS.md 2026-08-22, and `tools/xadmaster-ddn-repro/` for the
1,166-byte case).

    tools/run_ddforks.py fixtures/derived-LHA_Expander_1.0.3.sea
    tools/run_ddforks.py --write FIXTURE...     # record it in the manifests

For each fork it builds a one-fork `0xABCD0054` container holding **the
fixture's own compressed bytes, unmodified**, with the declared length one
larger and one pad byte after it, and compares `unar`'s output with ours.
That adjudicated the 8 resource forks no off-Mac implementation could
read.

**What it cannot see:**

- **It is not in `ci.sh`** — it needs `unar` and rebuilds every fork
  twice. `ci.sh` checks the *result*: the hashes are in the manifests and
  `run_diff.py` enforces them.
- **The pad byte's value**, so every fork is decoded with 0x00 and 0xFF
  and both must agree.
- It pairs manifest entries to headers **by the data fork's hash**; a
  header that does not pair uniquely is an error, not a guess.

## DiskDoubler methods 3, 4 and 5 (`tools/vmac/ddencode.py --emit`, in `ci.sh`)

Three `synthetic:` fixtures — `synth-dd-m3.dd`, `synth-dd-m4.dd`,
`synth-dd-m5.dd` — regenerated by `check_docs.py` on every run and graded
against the bytes that went into them, because those methods have **no
specimen** (DECISIONS.md, methods 3, 4 and 5). Registering them also puts
the three codecs in `run_robustness.py`, so 30 corrupted variants per
fixture run under ASan, UBSan and the alignment sanitizer every run.

**What this suite cannot see**:

- **It cannot grade the format.** Encoder and decoder are both ours. What
  grades the format is `ddencode.py --expand`, which hands the same
  encodings to Salient's own 1991 DiskDoubler under Mini vMac — not in
  `ci.sh`, needs an emulator, and is the only check of `build()` and the
  verification half of `expand()` (only `--emit` runs in `ci.sh`; the
  other modes once raised `NameError` unnoticed, repaired 2026-08-28).
- **It only covers encodings our encoder emits.** `--expand` writes
  twelve forks: method 5 at all four counts its validator allows, a
  method 4 tree with leaves at depth 1 and 10, and method 3 at run length
  2, all byte-exact through the 1991 expander (FORMATS.md, *What the 1991
  expander accepts*). A method 4 stream whose Huffman root is a LEAF has
  no case and is checked by hand only.
- **`ESC 1`**: the vendor's expander refuses such a fork, so `dd_rle`
  passes `strict = 1` like the other five RLE90 sites (BLOCKERS.md). A
  fork opening with `ESC` yields zeros from a deterministic `last = 0`.
- **A fork whose compressed size exceeds its original is refused by the
  1991 expander** (control: `RleGrow`).

Five subjects; `Splay128` (tree count 128) must round-trip byte-exact
through the expander and `Splay16` must be REFUSED by its validator. The
legal counts — 32, 64, 128, 256 — were read out of the expander
(FORMATS.md, the method table; DECISIONS.md 2026-08-28, the tree count).

## Several BinHex documents in one file (`tools/run_multihqx.py`, in `ci.sh`)

Real corpus `.hqx` fixtures are concatenated with text between them — 2
documents and 3 — and each set is graded against the same fixtures
extracted ONE AT A TIME with `-nr`, against macutils' `hexbin`, and on the
two ways it must fail (a truncated last document is a per-entry error with
the earlier documents intact; a banner with nothing usable after it is
reported). All four assertions fail against a single-document build.
`hexbin` is the oracle because `unar` decodes the first document and stops
(`reference/macutils/hexbin/hexbin.c`, the `again = 1; goto nexttry`
loop).

**What this cannot see:** entry NAMES — it compares fork hashes, because
`hexbin` mangles names; `test_binhex_multi` in the unit tests covers
names, and the whole case without fixtures. Nor one document cut across
several postings with their own headers (what this engine joins is the
`.001`, `.002` plain-split scheme).

## The sampled inverse BWT (`ci.sh` variant 1b, added 2026-08-07)

The Arsenic decoder picks between a 3-bytes-per-byte transform table and a
sampled occurrence index **by trying to allocate the table and failing**
(DECISIONS.md). CI forces the fallback three ways:

- `-DUNC_ARS_FORCE_SAMPLED` compiles the fast path out; the whole diff
  suite (the 933-fixture suite when this was written up) and the
  robustness variants (9,320 then) run through the fallback under
  ASan+UBSan and must be byte-exact.
- `--budget 615348` on the StuffIt 5 fixtures with the normal adaptive
  build (the figure `ci.sh` passes; it was written up as `597036`, the
  1 MB Mac Plus budget of its day). The only step that exercises
  *choosing*, and the halving of `target`.
- `-DARS_INDEX_TARGET=1` forces the deep end of the dial; byte-exactness
  is checked on StuffIt 5 fixtures up to 100 KB (`--max-size`), without
  sanitizers, because the walk is quadratic there (8.4 minutes for the
  full set against ~25 s for the subset).

**What these cannot see.** (a) *Time on a 68000*: both Arsenic fixtures
have been timed at 1x on both paths (`a2basic` 587 s fast / 966 s sampled,
`Library_ISBN` 768 s / 1,898 s — FORMATS.md), but CI cannot produce those
figures. (b) *The progress and Cancel path under the sampled walk*
(`unc_progress_poll`), Mac-side and unobserved by any Linux harness. (c)
*The middle of the dial*: only `target=1024` (forced) and `target=1` are
pinned.

## The LZW string length — a build at `UNC_LZW_LEN_MAX=4`

`unc_lzw.c` stores each symbol's string length in one byte, saturating at
255, and `lzw_strlen` walks up the parents to recover the exact figure.
**Nothing in the corpus reaches that walk** (longest string over all 113
fixtures that use the decoder: 223 bytes, measured). So `ci.sh` (variant
1c) builds the saturation point at 4 and requires the diff suite
byte-exact:

    make BUILD=build/lzwlen CFLAGS="... -DUNC_LZW_LEN_MAX=4" all

**Shown to test something:** breaking the walk (`n += len[s]` to `n +=
1`) leaves the default build byte-exact on all 113 fixtures and makes
the `LEN_MAX=4` build differ on 112.

What it cannot see: one ARC fixture reaches LZW, so the re-walk through
ARC's 64-byte buffer is graded on 46 splits in `synth-arc-mixed.arc` and
on what `tools/run_arc.py` generates, not on a real archive with long
strings.

## The LZW table bound — three builds, because one proves nothing

`unc_lzw_init` sizes its table from the input rather than from `maxbits`
(DECISIONS.md, FORMATS.md footnote §). The safety net that catches an
under-estimated bound never runs normally, so it is exercised by hand
(not in `ci.sh`):

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
Steps 1 and 3 are one-line local edits, deliberately NOT build flags (each
makes the engine wrong on purpose). **Step 3 is the point**: steps 1 and 2
report a full pass, which alone distinguishes nothing. "Expect" counts
are the suite of their day: step 2 was **778/778** on 2026-08-08; step 3
was **675/769** — 94 failures — on 2026-08-03, when 94 fixtures reached
the LZW path (4 `.Z`, the rest StuffIt classic method 2). What matters is
that step 3 fails at all.

## BinHex before 4.0 and `.dl` (`tools/run_hecx.py`, in `ci.sh`)

`unar` reads neither `.hex` nor `.hcx`, so the seven manifests are
macutils' `hexbin`; four of the seven fixtures were written by BinHex 2.0
itself (`tools/vmac/binhex2.py`) and are also checked against the subject
that went in. Each fixture is graded fork for fork and type/creator
against hexbin; then forty variants of three of them (endings, mail in
front, the banner removed, fork order, a byte or the sum changed, cut,
lower-case digits, the same fork twice), each with what must happen and
hexbin asked where it can be — a deliberate departure from it is asserted,
not skipped. Shown to fail: a build that ignores the sum fails six checks;
one that does not restore the space a one-character `.hcx` line lost fails
the stripped-spaces variant.

`.dl`: graded by hexbin and by SUMacC's own `tohex` (the writer) and
`fromhex` (its reader), built from `reference/sumacc` at run time. The
wild file must be what `tohex` writes for its fork; then 24 cases on
`tohex`'s output and that file, each with what hexbin and `fromhex` must
say. Shown to fail: the build before `.dl` fails 14 checks, and the 16-bit
sum of 2026-10-24 fails the high-half case.

**What it cannot see.** Only BinHex 2.0 has written anything here; a
`.hex` from BinHex 1.0 or the BASIC BinHexes would be graded by hexbin
alone; `tohex` is compiled here, not run on the VAX it was written for,
and one wild file is all its output there is. CLI only; the application's
runs (System 6.0.8 and System 3.0, 1 MB) are `tools/vmac/run.py` and
`sys30.py`, not `ci.sh`.

## ARC and uuencode (`tools/run_arc.py`, `tools/run_uu.py`, in `ci.sh`)

Neither format occurred in the corpus when these were written (measured
2026-08-15), so both suites write their own archives and hand them to a
second implementation, because a generator this repository wrote cannot
grade a decoder this repository wrote.

**ARC.** `tools/synth_arc.py` builds one archive per method (1-9) plus one
holding all nine; each must agree three ways: the bytes that went in,
`unar`'s output, and ours. `unar` is the load-bearing one: two
encoder/decoder pairs shared a misreading and the CRC-16 agreed too,
because it covers the DECODED bytes (DECISIONS.md 2026-08-15). When
`tools/get_arc.sh` has fetched Debian's `arc` 5.21q, three archives from
a real encoder are checked too; its absence is printed. Also asserted: a
flipped payload byte is a per-entry CRC error and the next entry still
extracts.

**uuencode.** `tools/synth_uu.py` writes the plain shape (encoded by
CPython's `binascii`) and UUTool's two-fork shape, which macutils'
`hexbin` decodes. Also covered: a mail banner in front, several documents
in one file, CR line endings, and the two ways it must fail (prose
containing "begin" is not an archive — including `prose2.txt`, a capital-`M`
sentence that fits NEITHER table; a truncated document is an error).

- **All three UUTool alphabets**: `TABLE_UNIX20` and `TABLE_UNIX23`
  generated and adjudicated by `hexbin` (its `SIXB` mask reads every
  table), plus two WILD specimens, `uu-wild-dictcol.uu` and
  `uu-wild-terrainman.uu`, in the differential suite and replayed by
  `tools/derive_mu.py --grade` (DECISIONS.md 2026-10-06, *the alphabet
  nothing here had seen*; FORMATS.md, *uuencode: three alphabets*).
- **The backquote spelling of zero** (Unix `uuencode`):
  `synth-uu-plain-classic.uu` (`TABLE_PC_BQ`), a binary payload with a
  line holding a zero AND a value under 27, which `run_uu.py` asserts is
  present; graded against its input and by CPython's `binascii.a2b_uu`.
  It fails against the build before (BLOCKERS.md). *What this case cannot
  see:* whether any WILD document uses the spelling — the claim graded is
  that the reader admits it.
- **The alphabet separates data from mail**: one standard-alphabet line
  inserted into two documents is data in one (the fork grows 45 bytes)
  and mail in the UNIX-table one. Taking the alphabets' union fails it,
  and `posted.uu` and `split.uu.001`.
- **Chained documents**: a plain and a UUTool document each holding a
  MacBinary file must yield the file inside, `-nr` must stop at the
  wrapper, and a file of TWO documents must not chain. With uuencode
  taken out of `env_is_envelope` the two chained cases fail; the others
  are controls.

**Multipart postings**: `run_uu.py` joins two postings (headers and all),
runs the same set through the `.001`/`.002` split scheme, and asserts that
a missing MIDDLE part decodes short and silent — the one thing uuencode
cannot detect. `run_multihqx.py` does the BinHex half, plus a junk line of
alphabet characters only, which must come back as a CRC error. **Both fail
against a build with the line rules removed** (DECISIONS.md, "Multipart
postings").

**Cut at DeHQX's separator**: `run_multihqx.py` builds a posting cut at
`---` and asserts it reads exactly what the single file gives (it failed
on the build before — `checksum mismatch`); `--- part 2 ---` and `-----`
are cases too (DECISIONS.md 2026-10-06, *the line that had to be the whole
line*). The control: a bare `---` with no `--- end of part` before it is
still data and must still fail the CRC. `tools/derive_dehqx.py` checks the
sentence and consults `hexbin`; `tools/derive_hqxgarbage.py` grades all
three resume shapes against the second implementation. **What neither can
see is a wild posting cut that way**: none of the 204 `.hqx` fixtures
carries the separator (measured).
### `tools/derive_hqxgarbage.py` — fourteen readers, and the one that says yes

Not in `ci.sh` (it needs fixtures and cached specimens). Eleven sections,
each skipping cleanly when its specimen is absent (the docstring lists
all eleven, including `--tables`, `--code` and `--absent`):

    python3 tools/derive_hqxgarbage.py              all eleven
    python3 tools/derive_hqxgarbage.py --engine     StuffIt's HQXEngine: THE RULE
    python3 tools/derive_hqxgarbage.py --siblings   Aladdin's other four 5.x decoders
    python3 tools/derive_hqxgarbage.py --definition the Definition's own sentences
    python3 tools/derive_hqxgarbage.py --author     BinHex 5.0
    python3 tools/derive_hqxgarbage.py --lewis      DeHQX 2.0.1's binary
    python3 tools/derive_hqxgarbage.py --others     five more readers
    python3 tools/derive_hqxgarbage.py --length     the length half and the trim
    python3 tools/derive_hqxgarbage.py --grade      the subject, every reader here

`--engine` is the one `src/fmt_binhex.c` cites. It opens four layers with
this project's own CLI (`sdk512.hqx` → a `.sit` → an Installer whose DATA
FORK is a `.sit` → `Individual Engines/HQXEngine.rsrc`), checks 29
witnesses in `Eng ` 10000 (including the instruction that sets the
resource's A4, so the two table displacements are derived), and SIMULATES
the predicate's branch chain over all 256 character values — the set is
not the alphabet.

`--siblings` is the control on that citation: Aladdin's other four 5.x
BinHex decoders, all the same code (the PowerPC two checked by their
compares and two loop branches, without a disassembler). It also carries
**the roll-call of `StuffIt Engine™ PowerPlug`'s fourteen PEF
containers**, each matched by code-section sha256 against the SDK's named
`.shlb` files — this project's only external inventory of Macintosh
archive formats, which found Private File missing (DECISIONS.md
2026-10-07, *the engine list as a checklist*). It asserts the container
COUNT, so a fifteenth fails.

**193 checks, nearly every one a BYTE at the offset it is claimed to sit
at.** Proven able to fail ten ways (a witness moved two bytes, one of
HQXEngine's the same, one simulated branch bent, a table-class count
loosened, the corpus norm forced to 1, and in the sibling section a PPC
branch target and a PPC compare moved by four, the byte-identity test
negated, a PowerPlug container moved by four, the container count bent).
`--grade`'s instrument is bracketed: `hexbin` skips the junk line and
`deark` errors on it.

`--length` measures this project's corpus: **0 of 204 `.hqx` fixtures
carry a line that the length half would skip and the alphabet half would
keep** (beside the Definition's own refusal of that half, asserted
verbatim by `--definition`), and **one fixture carries a trailing space on
all 2,600 of its data lines** (`country-song-generator-101.hqx`), so the
trim is load-bearing; HQXEngine does not trim. The scan carries its own
control — an injected line of twenty hyphens.

**What it cannot see.**

- **what a PowerPC build does between its compares** — no PowerPC
  disassembler here; same source, not proven otherwise identical.
- **frequency**: the 204 fixtures are Info-Mac single postings.
- **run-time behaviour from a static reading**: every Macintosh answer
  here is read out of code; the one reader that was RUN is StuffIt
  Expander 4.0.2 (`tools/vmac/README.md`).
- **the engine**: the corpus scan reads raw fixture text, not through
  `bh_refill_line`; `tools/run_multihqx.py` grades the engine on the same
  shapes.

**(ARC and uuencode suites) What these cannot see.** Neither reads a real
ArcMac archive: `ci.sh` covers the two-fork split with one synthetic
stored entry in `tests/unit_formats.c` — a regression guard, not evidence
about the format (it once encoded the fork lengths big-endian exactly as
the buggy decoder read them). The order is measured by
`tools/vmac/arcmac.py`, which reads the wild archives too; not in
`ci.sh`.

## ARC's PAK methods (`tools/run_pak.py`, `tools/pak.py`, in `ci.sh`)

Methods **0x0a (Crushed)** and **0x0b (Distilled)** are PAK's and no Linux
program writes them, so the archives come from **PAK 2.51 itself (NoGate
Consulting, 1990), run headless under DOSBox**, or from the two real
specimens.

    python3 tools/pak.py --setup              # DOSBox + PAK 2.51, needs network
    python3 tools/pak.py --make DIR           # write the corpus
    python3 tools/pak.py --list ARCHIVE       # methods, sizes and CRCs
    python3 tools/run_pak.py --macextract build/rel/macextract

`--setup` needs **no root** (`apt-get download`s DOSBox and its
dependencies into `$UNC_PAK_HOME`, default `~/.cache/macextract/pak/`) and
no X server (`SDL_VIDEODRIVER=dummy`). `run_pak.py` skips politely when
neither the corpus nor a `.pak` fixture is present.

**Four graders:**

1. the **CRC-16 PAK stored** per member, over the decoded bytes — no
   decoder can influence it, and it caught the oracle;
2. the input bytes, for the seven generated archives;
3. **deark for 0x0b and `unar` for 0x0a**, byte for byte — not
   interchangeable (deark lacks Crushed, `unar` gets Distilled wrong);
4. PAK 2.51 extracting under DOSBox — by hand, not in `ci.sh`; it verified
   the nine members of the PAK distribution.

**Reach:** `pak-crushed-big.pak` fills the 8,192-symbol table and fires
the replacement scan 49,751 times and the inverted-literal framing 13,009
times; `REPEAT.TXT` makes matches reach into the space-filled window.
Truncations and bit flips run over every archive under 120 KB: a damaged
archive may refuse, but must not exit outside 0..2 or die by signal.

**What this cannot see.** Anything PAK 2.51 never emits at one setting
each, and every archive written by PAK 1.x. Method 0x0a's dialect is
decided by `arc_dialect()` (next section).

## ARC 7.x's Trimmed (`tools/run_arcplus.py`, `tools/arcplus.py`, in `ci.sh`)

**Method 0x0a is two methods**: PAK's Crushed and ARC 7.x's Trimmed.

    python3 tools/arcplus.py --setup            # ARC+Plus 7.12, needs network
    python3 tools/arcplus.py --make DIR
    python3 tools/run_arcplus.py --macextract build/rel/macextract
    python3 tools/run_arcplus.py --register     # the real fixture's manifest

`--setup` carves the archive out of the DOS self-extractor structurally
(`--carve`) and copies the STORED `ARCDOS.ARC`; only lifting `ARC.EXE` out
of it uses our decoder — **a bootstrap, not a grading**.

**Graders:** the CRC-16 ARC+Plus stored; the input bytes, for the three
generated archives; **deark**; and `XARC.EXE`, Trimmed in the
distribution and uncompressed in another CD's `XARC.ZIP`, byte-identical.
`unar` does not recognise ARC 7 (BLOCKERS.md), so
`fixtures/manifests/derived-ARCDOS.arc.json` is REGISTERED by this tool;
`make_manifests.py` refuses to overwrite a manifest whose oracle is not
`unar`.

**The discriminator has its own test**: `arc7-text.arc` and
`pak-crushed-text.pak` hold the same inputs under the same method number
from the two programs; forcing Crushed fails the ARC 7 side, forcing
Trimmed the PAK side.

**What this cannot see.** ARC 7 has no switch to force Trimmed, so
coverage is what its inputs persuade it to do; ARC 6.x has no specimen.
An archive with items and no PAK trailer is read as Trimmed, so a
hypothetical ARC 6 archive using 0x0a would fail its CRC rather than pass
quietly.

## btoa (`tools/run_btoa.py`, in `ci.sh`)

No corpus file (`xbtoa` appears in none of the 903) and no second READER
(`unar` and macutils lack it), so the original implementation is the
ENCODER: the suite compiles `reference/btoa` (5.2.1, from
`tools/fetch_references.sh`) and requires our decoder to reproduce what it
writes, byte for byte.

Eight subjects chosen for what they make the encoder do: runs of zeros
and spaces (`z`, and version 5's `y`), lengths 101-104 around the padded
last group, every byte value, a one-byte file — all in **both framings**
(`xbtoa5` checksums the encoded characters, `xbtoa Begin` the decoded
bytes). Also asserted: version 5's header names the entry, version 4
falls back to the host's hint; a mail header is stepped over; a flipped
character and a truncation are errors; prose containing `xbtoa` is not an
archive; LF, CR and CRLF decode identically (25 cases; BLOCKERS.md,
withdrawn claims); the End line's `R` field in the **32-bit** width a
Macintosh writes (FORMATS.md, *btoa*; four cases); and the **chain**: a
MacBinary inside must come out unwrapped in both framings and `-nr` must
stop at the wrapper — the chained cases fail with btoa out of
`env_is_envelope` (DECISIONS.md 2026-08-27).

**What it cannot see.** It skips, loudly, without `reference/btoa`, so a
fresh clone runs only the two hand-built streams in
`tests/unit_formats.c`. Every stream in `ci.sh` comes from ONE encoder.
The independent specimen (`tools/vmac/sitcrypt.py --btoa-send`, Aladdin's
`btoa/atob Translator`) decodes byte-exact (FORMATS.md, *btoa*) but is
made on demand under an emulator; nothing in `ci.sh` replays it.

## base64 and MIME (`tools/run_mime.py`, in `ci.sh`)

The differential suite has neither: re-measured 2026-10-11 over all 983
corpus files, exactly one sniffs as a MIME message and none as base64,
and that one — `synth-os9-mime.mim` — has no manifest. So every case is
generated and graded by two other implementations:

- **munpack 1.6** (CMU), which `src/fmt_mime.c` is transcribed from,
  built from `reference/mpack` by `tools/build_mpack.sh`. **Its `md5.h`
  is edited in the copy** (`UINT4` to `unsigned int`; LP64 computes
  something that is not MD5), and the script rebuilds any mpack whose
  digest of `abc` is not RFC 1321's (DECISIONS.md 2026-10-11, *the digest
  our own oracle could not compute*).
- **deark**, an independent base64 implementation (`tools/build_deark.sh`).

65 cases. base64: four lengths around a group boundary, every byte value,
a one-byte file, two documents in one file, CR/LF/CRLF. MIME: a single
attachment, a multipart with a note and two attachments, quoted-printable,
an unencoded part, a nameless part (`part1`), an LF-only message, and
**multipart/appledouble** (both forks, type and creator, resource-only,
nested in `multipart/mixed`). Plus:

- **A document pasted into a part** (six cases: uuencoded beside base64,
  `x-uuencode`, a uu-only multipart, a pasted BinHex document kept
  undecoded, a note beginning "begin", and a uuencoded POSTING). Four fail
  with `unc_mime_probe_multipart` removed from `unc_sniff`.
- **`message/partial`** (nine cases, BOTH ends somebody else's: `mpack -m
  4000` writes the set, munpack reassembles it): joined from the first,
  a middle and the last part; a missing middle part refused with nothing
  written; two sets in one directory placed by `id`, never filename; a
  split `multipart/appledouble`; `total` only on the LAST part. Six fail
  with `unc_mimeseg_probe` removed. munpack reassembles through
  `/usr/tmp/m-prts-$USER`, which it does not create, and its `CT` file
  needs removing between parts (DECISIONS.md 2026-08-29); without a
  writable `/usr/tmp` the comparison is reported skipped.
- **Progress** (three cases, `tick_probe` beside the CLI): a 400 KB
  message must report nothing past its size and end within 16 KB of it;
  the build before the fix fails by 836 KB and 639 KB (DECISIONS.md
  2026-10-13, *the mail that counted itself three times*). Cancel inside a
  message was checked once by a scratch harness, and is not here.

**The three places the oracle is wrong** (reproductions in DECISIONS.md
2026-08-26): munpack ignores a `Content-Disposition` filename, cannot read
CRLF, and drops a decoded `=0D`. So munpack gets the LF form, BYTES are
compared rather than names, and the `=0D` case is graded against its
subject only.

**What it cannot see.** Neither grader knows a resource fork, so
**nothing here adjudicates the fork JOIN except this project's own
AppleDouble decoder** (graded against `unar` by the corpus; the suite
feeds it the same applefile part alone to say so). base64 carries no
length or checksum, so a truncated message decodes short and silently —
asserted as such. It skips, loudly, without `reference/mpack`.

## LZH / LHA (`tools/run_lzh.py`, in `ci.sh`)

The corpus holds one `.lzh` (Amiga software); what grades the format is
`reference/lhasa/test/archives` — **182 archives written by fourteen
different LHA implementations**, MacLHA 2.24 among them (seven are also
fixtures with oracle manifests).

**Three graders, deliberately not interchangeable.**

| grader | what it is | what it can catch |
|---|---|---|
| `unar` | XADMaster, which `src/fmt_lzh.c`'s HEADER WALK is transcribed from — but not its decoders, which have been lhasa's since 2026-09-19 | on the walk, a transcription error and nothing else; on `-lh4-` .. `-lh7-` and LArc, a wrong reading that lhasa shares |
| `lhasa` | an independent implementation, compiled out of `reference/lhasa` — and, since 2026-09-19, the source the decoders are written from | on the walk, a wrong reading that XADMaster shares; on the decoders, a transcription error and nothing else |
| LHa for UNIX 1.14i | the ORIGINAL program, compiled out of `reference/lha` and used as an **encoder** | a decoder that agrees with both readers and still cannot read what the format's own writer emits |

The run reports how many archives each grader adjudicated (137 and 142
of 182 when written up) plus 12 generated sets — `-lh0-`, `-lh5-`,
`-lh6-`, `-lh7-` at three header levels over five subjects (long runs,
text, incompressible bytes, one byte, none).

**What it cannot see**, all named in the file itself:

- The `SKIP` set — PMarc, `-lhx-`, LHArk's private `-lh7-`, the
  self-extracting ones — is checked to be REFUSED and nothing more.
- `-lh2-` and `-lh3-` have their own section (*LZH's -lh2-*, below); no
  wild archive uses either.
- **The resource fork of a MacLHA entry, unless this machine has made
  one.** lhasa discards it and all sixteen MacLHA archives in its
  collection are data-fork-only. `tools/vmac/maclha.py --make` runs
  **MacLHA 2.00** under Mini vMac on a file with a real resource fork and
  this suite grades both forks against the input; a fresh clone skips
  that and says so. Off-Mac, a hand-built MacBinary payload in
  `tests/unit_formats.c` covers the branch.
- Dates: the engine converts neither MS-DOS nor Unix timestamps
  (FORMATS.md), so there is nothing to compare.

Three archives are excused by name, each with its measurement: `unar`
mis-reads one OS-9/68k level 2 archive, and lhasa reads two level 0
archives as empty (a zero-length `-lhd-` name first). A grader is excused
on a named file, never a format.

## Implode, zip method 6 (`tools/run_implode.py`, in `ci.sh`)

**`tools/synth_implode.py` is an ENCODER**, because nothing here writes
method 6; it is written from APPNOTE.TXT 5.3, the same section
`src/fmt_exo.c` is transcribed from — a circularity the graders answer.

**Four graders per entry, two of them outside this project.**

| grader | what it settles |
|---|---|
| the writer's own `--plain` output | the bytes it CODED, not a decode of what it wrote |
| `unar` | an independent implementation of the method |
| deark | a second one, and the file `src/fmt_exo.c` was read beside (`reference/deark/src/fmtutil-lzh.c`) |
| the CRC-32 the writer stored | the same check a real PKZIP file is graded by, through `macextract t` |

All four flag-word combinations (4 K / 8 K dictionary × two / three
Shannon-Fano trees) are written; `--only` names one. **One entry is a
committed fixture**, `synth-exo-zip-implode.zip`, so `run_diff.py` grades
Implode with no oracle at run time — and it holds the two combinations
where PKZIP 1.01's minimum-match-length bug is observable (a build with
the wrong reading had passed the whole corpus; FORMATS.md, *Implode*).

The lanes:

1. **the four conforming shapes**, graded as above;
2. **240 mutants** on a fixed seed, edits confined to `--ranges`, each
   required to exit cleanly with no signal and no sanitizer report — and
   **all 240 refuse at least one entry, asserted**, so the lane is known
   to bend something;
3. **the two shapes PKZIP 1.01 and 1.02 would have written**
   (`8k-2trees-mmlbug`, `4k-3trees-mmlbug`): **deark is not optional**
   (the only other implementation of the rule `ci.sh` can run; PKUNZIP
   1.01 and 1.02 read both under DOSBox by hand, *Their programs, run*),
   and **`unar` must REFUSE both** as the negative control. One archive
   per shape, because both readers settle the question per ARCHIVE from
   the first bug-capable entry. `synth_implode.py --selftest` requires each
   bug shape to come out WRONG or not at all under 5.3.4's reading;
4. **one archive carrying BOTH readings** (`synth_implode.py --mixed`,
   three entries): the settling entry comes out; the next is refused AS A
   CHECKSUM failure, not a truncation; the third comes out. The oracle is
   each entry's stored CRC-32 (deark settles per archive too). No writer
   is known to make one — none of the 1,537 swept on 2026-10-08 mixes
   (DECISIONS.md 2026-10-08, *the writer a zip is allowed to have twice*);
5. **how many times each entry is DECODED**, counted from
   `UNC_TRACE_ALLOC` (zip_implode's state then its window), against
   Python's `zipfile` as denominator. Extra passes asserted exactly: **0**
   on the two unambiguous generated shapes and on `4acalc.zip` and
   `4alnch11.zip`, **1** on the four conforming shapes, **2** on
   `pkz101.exe`, **4** on the mixed archive; each subject's exit status
   too (1 on the mixed archive, 0 elsewhere). Absent fixtures are skipped
   with a message.

**Made to fail**, each a separate rule: the minimum match length from the
dictionary size, the window filled with spaces, the length-63 escape
dropped, the distance bias off by one, Shannon-Fano codes assigned
shortest-first — each fails. For the rule choosing between the two
minimum match lengths: keyed on tree count, the probe ignoring the
CRC-32, the probe adopting 1.01/1.02 where 5.3.4 matched, and the
predicate narrowed to nothing are caught on the bytes; the predicate
WIDENED and the probe ORDER inverted are caught only by lane 5
(FORMATS.md, *What the suites cannot see*).

**What it cannot see.**

- **Whether a MIXED archive exists anywhere**: 0 of 1,537, not 0 in the
  world.
- **Which half of the 1.01/1.02 rule is authentic**: all three authentic
  bug entries are 4 K with three trees (`pkz101.exe`); **8 K with two
  trees is this project's own encoder alone**, with deark as its second
  reader (FORMATS.md, *Which half is graded by a real file*).
- **Which reading a decode pass used, or what it costs**: lane 5 counts
  passes; lanes 3 and 4 catch a wrong reading on the bytes; cost is
  callgrind `Ir` and `strace` in FORMATS.md (*The minimum match length
  PKZIP 1.01 and 1.02 used*).
- **No Finder metadata and no fork split** — `tools/run_zipit.py` grades
  that shape.
- **No mutant is graded by anything**; a bent stream must come out
  cleanly, never right.
- **No Macintosh**: the decoder reaches it through `ovl_exo`, checked by
  `run_tiers.py --check-images` and the tier sweeps.

## Large zips (`tools/run_ziplarge.py`, in `ci.sh`)

A zip counts its entries in 16 bits; past 65,535 the count lives in a
Zip64 record, and a reader that trusts the 16-bit field walks 65,535
entries and reports success (FORMATS.md, *Size limits*). **The largest
zip in 943 fixtures has 29 entries**, so the subjects are generated and
graded by CPython's `zipfile` (which wrote them), `lsar` (skipped if
absent), and the boundary itself: 65,535 (no Zip64 record) and 65,536
(one) are both built.

Also asserted: a locator whose record sits past 4 GB is REFUSED; a
locator pointing at non-Zip64 bytes falls back to the 16-bit count
(XADMaster's behaviour, which `fmt_exo.c` follows). And the **per-entry
escape**, which arrives at 2 GB: `offsets.zip` is a **sparse** subject
with one entry just under 0x80000000 and three past it (`zipfile` grades
the construction; every entry must verify under `t`), plus three
synthetic cases — a small honest escape extracts normally, and an
escaped position or size with its high half set refuses **that entry
alone**.

**Established that it can fail**: against the previous commit's
`fmt_exo.c`, six of the nine cases fail.

**What it cannot see.** No subject is over 4 GB and the large one is
2 GB of hole: the read path over a multi-gigabyte entry is not exercised,
and the over-4-GB refusals are reached by writing a high half. Skips the
offset cases where the filesystem has no sparse files.

## Size limits (`tools/run_sizelimits.py`, in `ci.sh`)

Two boundaries: a MEMBER over 2 GB cannot be extracted (refused per
entry), and a POSITION past `unc_off_t` cannot be addressed (ends the
walk) — FORMATS.md, *Size limits*. The second depends on the build, so
the suite reads the width from `--version` (derived from
`sizeof(unc_off_t)`) and expects a truncated walk at 32 bits and a
complete one at 64; `ci.sh` runs it on the default build and on variant
5's.

Subjects are generated and **sparse** (a 4.5 GB archive costs a few
kilobytes), graded by **GNU tar**, which has none of these limits. Four
cases: an oversized member between two ordinary ones (all three listed,
the big one refused, both small ones byte-exact, non-zero exit); 2 GiB −
1024 listing a size and 2 GiB (0x80000000) listing `?`; and a member
whose POSITION passes 4 GB, which ends the walk with `UNC_ERR_CORRUPT`.

**Established that it can fail**: three of the four cases fail against
the previous commit's `fmt_exo.c`.

**What it cannot see.** The holes are never read, so the read path over a
multi-gigabyte entry is unexercised (unreachable on the Mac anyway: HFS
caps a fork at 2 GB). Skips where there is no `tar` or no sparse files.

## Both offset widths (`ci.sh` variant 5, added 2026-08-28)

`unc_off_t` is 64-bit in the host build and 32-bit in the Macintosh one.
Variant 5 builds the **32-bit** configuration — `make OFFDEFS=` — under the
same sanitizers as variant 1 and runs the unit tests, the whole diff suite
(all 933 fixtures when written up), the robustness variants (9,320 then)
and the size limits through it (DECISIONS.md 2026-08-28, *what a width
costs*).

**Established that it can fail**: the lane asserts `--version` reports
`offsets: 32-bit` first, because `make` tracks timestamps and not flags.

**What it cannot see.** Only the two widths that exist. And it grades the
32-bit ENGINE on x86-64, not on a 68000 — that is the Mini vMac tier's job,
where both widths ran 69/69.

## Over-long names (`tools/run_names.py`, in `ci.sh`)

Two caps meet a name — the engine's `UNC_NAME_MAX` (255) and the
filesystem's `pathconf` answers; a name over either is shortened and
numbered, never refused, and the notice says so (FORMATS.md, *Name
limits*). **The longest name in 943 fixtures is 120 bytes**, so the
subjects are generated, graded by CPython's `zipfile` and `tarfile` and by
`unzip -l` and `tar tf` where present.

Fifteen cases over seven carriers, the allocator's budget and the output
directory: a long zip entry shortened while its neighbour is untouched;
two entries differing only past the cut (the second numbered `~1`); 255
written whole and 256 shortened; a ustar `prefix + '/' + name` of 256
bytes; a uuencode `begin` line cut by its 96-byte buffer; an AppleSingle
whose 200 MacRoman bytes are 400 of UTF-8; a legal 1 KB output directory,
and one past `PATH_MAX` that must be refused. Each case asserts the
NOTICE carries the archive's own name in full where the format held it;
a zip whose central directory exceeds a 64 KB budget must give the length
and say the name is gone.

- **Now Compress** (`tools/synth_now.py`): a nine-deep tree of 31-byte
  components, 296 bytes; `lsar` is asked for the same path. This grades
  `unc_path_leaf`, which DiskDoubler and SuperDisk! also run.
- **SuperDisk!** (`tools/synth_sd.py`): a ten-deep stream (paths 43 to 331
  bytes) built from a corpus archive's own records and blocks; no
  off-Mac oracle, so the verdict replayed is the format's own
  self-extractor on the emulator (`tools/vmac/superdisk.py --nest`),
  which agreed on all eleven files. Skipped, not failed, without the
  fixture.
- **DiskDoubler** (`tools/synth_dd.py`, both containers, archive-header
  CRC-16/XModem included): a TREE per walk (nested folders, a file after a
  folder closes, a resource fork, `DDAR`'s stored-in-the-record shape),
  also walked by `lsar`; and a DEEP chain (63-byte components for `DDAR`,
  31 for `DDA2`) whose leaf's folder lands on EXACTLY 255, so `~1`
  numbering is what saves the file. The generator's `DDAR` `+74` span and
  `+78` are what DiskDoubler's own Combine command writes
  (`tools/vmac/diskdoubler.py --combine`, 2026-09-22).

**Established that it can fail**: nineteen assertions fail against the
engine and CLI of two commits earlier; the nested-path case fails three
ways against the commit before it (reporting 287 bytes for a 296-byte
path); dropping every `DDAR` enddir record fails five, squashing the
`DDA2` dirlevels fails five, both also seen by `lsar`. A uniform dirlevel
shift fails nothing, correctly.

**What it cannot see.** Whether DiskDoubler itself writes the trees the
generator writes. SuperDisk!'s header walk never reaches the cap — no
fixture nests that deep (OPEN_ITEMS.md). The Mac application's handling
is graded in the next section.

## The tiers a budget predicts (`tools/run_tiers.py`, in `ci.sh`)

**A small Macintosh's memory result, measured on Linux in five seconds.**
The Mac shell's allocator is a running total against a cap and refuses
per entry; `macextract --budget N` is the same rule, so the 74-fixture
sample (`tools/vmac/sample.txt`) can be swept at a tier's measured budget
without an emulator, a ROM or an X server.

    tools/run_tiers.py --check                 # what ci.sh runs: both lanes
    tools/run_tiers.py --tier sys3-512K        # one tier, with shortfalls
    tools/run_tiers.py --tier sys3-512K --shipped     # the 'OVLY' build
    tools/run_tiers.py --budget 102328         # any cap

`tools/run_budget.py` is the other half: the whole CORPUS at one cap, per
format (layer 5 above). `ci.sh` also runs `--check-images` after the
eager overlay build and `--check-saved` after the resident control build.

**Two lanes, and `--check` runs both.** The RESIDENT lane sweeps one
budget per tier (the control build, `UNC_OVL_RESIDENT=1`) and grades the
engine against a fixed ceiling; the SHIPPED lane sweeps one budget per
tier PER FORMAT and per envelope LAYER (the `'OVLY'` build) and predicts
what a user's Macintosh refuses (DECISIONS.md 2026-09-26, *a budget per
format, and one per layer*). Both assert the refused fixtures **BY NAME**
(`EXPECT`, `EXPECT_SHIPPED`), because a count cannot fail on two
different refusals:

- resident, from `EXPECT`: **74/74** at the 1 MB floor target, **70/74**
  at System 3.0 / 512 KB, **64/74** at System 6.0.8 / 512 KB. The resident
  build last ran on all three machines on 2026-10-09 (72/72, 68/72 and
  63/72); every change since is DERIVED and recorded in `run_tiers.py`
  beside the name.
- shipped: **74/74, 72/74 and 68/74**. The System 6.0.8 tier is the one
  this lane PREDICTED before any machine ran it (FORMATS.md, *512 KB
  machines*).

The budgets are `TIERS` (627,832, 198,926 and 103,544 B as of
2026-10-25, derived from the 2026-10-22 machine re-take); `TIERS_MACHINE`
holds each plus the control it was read against. The keep set is parsed
from `mac/ovl_load_eager.c`, format names and envelope flags from the
engine's table, image sizes checked against `build/mac/`
(`--check-images`), and `OVL_SAVED` against `build/mac` and
`build/mac-resident` (`--check-saved`; FORMATS.md, *What each format is
granted*). A tally that moves is a memory regression or a memory win;
either way the names are changed deliberately.

**What it cannot see** (and why the emulator tiers stay):

- **The budget's own currency, which is the limit that has actually
  bitten.** Each figure is `FreeMem() - 20,480` on the machine
  (FORMATS.md, *Budget*), so it moves when the application's size does;
  stale budgets have twice cost a wrong prediction (BLOCKERS.md,
  *Withdrawn claims*). `--check-saved` fails when the control build's
  `CODE` + A5 leaves `TIERS_CONTROL`, and when `TIERS` + `TIERS_CONTROL`
  leaves `TIERS_MACHINE`; asked for by name, it fails rather than skips
  when the builds are missing. It cannot see a change the size does not
  show — a different System, emulator or ROM, growth that lands in slack,
  or resident bytes outside the `CODE` + A5 unit (the autotest harness;
  `run_tiers.py` notes each).
- **Whether a Compact Pro or zip archive holds an encrypted entry.** The
  shell drops the ciphers on a definite NO from `unc_archive_encrypted`,
  which the CLI cannot reach, so the shipped lane grants those formats
  10,252 B less than the machine does (measured 2026-10-09). It decides
  nothing: the narrowest margin on any Compact Pro or zip layer in the
  sample is 138,989 B, re-measured 2026-10-09.
- **Fragmentation.** The Memory Manager also needs one PIECE that big
  ("Memory is too broken up"); nothing here models it. No disagreement
  currently rests on it.
- **68000 struct sizes.** `derived-a2basic.dmg.sit` holds 37,356 B before
  its block here and 37,372 B there — tens of bytes.
- **Everything that is not memory**: names, CRCs, the File Manager, the
  interface — `tools/vmac/run.py`'s.
- **What a shortfall means.** It is the FIRST refused request's, not the
  entry's demand, which is why both front ends say *"at least"*.
  `synth-dd-m5.dd` reports 928 B at the 512 KB budget and wants 203,680
  (FORMATS.md, *512 KB machines*).

`UNC_TRACE_ALLOC=1` in the environment makes the CLI print every
allocation and every refusal with the live total.

## Selective extraction (`tools/run_only.py`, in `ci.sh`)

`unar` has no per-file selection, so the reference for `--only` is the
engine's own FULL extraction of the same archive, which the differential
suite grades against `unar` — transitive to the oracle, not circular.
Every fork is compared, sidecar included.

**The assertion that can fail is the strict subset**: an `--only` that
did nothing satisfies every byte comparison. Disabling the filter gives
362 failures.

Five generated cases — a zip (exact names, a folder selector, two
selectors, a name matching nothing, one hit beside one miss, `l`/`t`
taking the option), a zip with a COMMENT, DiskDoubler in both containers
and Now Compress (each holding a FOLDER) — and a sampled corpus sweep.

**An archive's own comment is not an entry**: it is written beside the
selection as `<archive>.comment.txt` whatever was asked for, and
`--no-comment` declines it (cli/main.c, `sink_comment`); the comment case
asserts all three. The sweep identifies the comment file as what a
`--no-comment` run does not write. **An envelope layer kept because the
layer inside it failed** is allowed the same way (DECISIONS.md
2026-10-18, *the comment Spotlight kept*).

**What it cannot see.** Whether a skip SAVED anything (seeking past an
entry and decoding-and-discarding it — PackIt — pass identically; nothing
times either). A defect that corrupts full and selective extraction alike
(the diff suite grades that side). Fixtures whose names the filesystem
shortened are passed over. Encrypted entries and segmented sets are not
reached, nor the Mac application, which has no selection UI. **The sweep
is every sixteenth fixture by name**, so what it covers is a function of
what the corpus is CALLED: it can be said to have met a property, never
to cover one.
## Folder nesting, and the limit that was deleted (`tools/synth_deep.py`, `tools/run_depth.py`, in `ci.sh`)

`UNC_PATH_MAXDEPTH` (24) is gone: a push is refused only when the path
STRING has no room left (`UNC_NAME_MAX`), the same five walks reaching the
same refusal by a different route, so every case still grades what it
graded. **Nothing on this disk nests deeper than 4** (FORMATS.md, *How deep
anything actually nests*, measured with `tools/measure_depth.py`); three
of the five walks had been misfiling entries (BLOCKERS.md, *what ignoring
a refused push cost*).

The rule: an entry the walk could not descend to is still OFFERED, with
the path it could represent, carrying `path_too_deep` and failing per
entry with `UNC_ERR_TOODEEP`, and nothing is written for it; an entry the
walk COULD represent is reported at exactly its own path.

Subjects are generated, one per walk — DDAR, DDA2, Now Compress, AppleLink
package, SuperDisk! — by nesting 30 deep through the existing
`tools/synth_*.py` builders, with three-character folder names so depth is
the only variable (cut NAMES are `run_names.py`'s). **The tree's shape is
the finding**: a file at every level on the way down, a **trailer at every
level on the way back up** (four of the five walks pop by a count, so an
uncounted refusal misfiles everything after it), and a sentinel at the
root. **An assertion built on the sentinel alone passes on all five broken
walks** (`unc_path_pop` clamps at 0).

Six assertions per format: every declared entry offered; every
representable path reported as its own; no path past 24 levels reported;
the root sentinel at the root; extraction failing exactly the entries it
cannot place and writing exactly the ones it can; and the engine saying so
in words.

### Both limits at once

`deep-dd-long.dd` is the same tree with 31-character folder names, so a
path passes `UNC_NAME_MAX` around the eighth level and an entry past 24 is
name-cut AND unplaceable — where the engine claimed a whole name it did
not have (BLOCKERS.md). **Its assertion is `test_path_depth` in
`tests/unit_formats.c`**, because at the CLI every deep entry reports the
same 255-byte string and no note can be attributed; this suite only checks
the subject still reaches both limits. (The unit test's first version
passed with the fix reverted and was rewritten.)

### And on a Macintosh — run 2026-10-07

The Macintosh shell declines such an entry at `begin_entry`. Driven on an
emulated Mac Plus at 4 MB under System 6.0.8: `run.py --keep-disks` then
`checkdisk.py --fixture` on a 30-level `deep-sqp.pkg` — **61 files, 61
forks byte-exact off the Out volume, names included**, in 30 folders whose
deepest entry is `D01/../D30/f30.txt`. **The control is the same archive
through the two builds before it** (one misfiled five folders, the other
wrote 49 files and 25 folders and refused 17 entries); `checkdisk.py`
fails both by name. `checkdisk.py --fixture` is what lets a generated
subject be checked at all; its volume walk's old depth caps are withdrawn
(BLOCKERS.md).

Run against a build of the previous commit: **28 problems across the five
formats**, discriminating all three old behaviours.

What this CANNOT see:

  * whether 24 is the right limit, or whether any real archive reaches
    it — this grades a RULE, not a corpus; `tools/measure_depth.py` is what
    would notice a deeper specimen.
  * the decoded bytes of a deep entry (nothing is written for one); the
    representable part is compared by path and length, not byte for byte.
  * whether these record shapes are what each application would write;
    for SuperDisk! there is no second reader off the Macintosh at all
    (`tools/synth_sd.py`).
  * StuffIt and Compact Pro, which build paths through
    `unc_entry_path_append` without this walker; nothing here tests what
    they do instead.
  * anything about a tier: these runs are at 4 MB on System 6.0.8, and no
    tier sample holds a 25-level tree.

## The three walks agree (`tools/walk_probe.c`, `tools/run_walk.py`, in `ci.sh`)

Three walks exist — `list_only`, an ordinary extraction, and one that SKIPS
every second entry — and all three must offer `begin_entry` the same
entries, with the same name, `is_dir`, type, creator and both fork sizes,
in the same order. The probe measures; `run_walk.py` applies the rule.

**Envelopes are peeled on the way in** (by result: a layer yielding exactly
one recognised archive is an envelope). 943 fixtures become **1,360
archives walked three ways**, 419 of them behind a wrapper; about 10 s.

Both assertions were made to fail: a listing reporting `data_size + 1`
gives 461 failures, and a PackIt skip that does not consume the entry's
bytes desynchronises all four `.pit` archives (`UNC_ERR_CORRUPT`).

**What it cannot see.** Whether the entries are RIGHT (three of our own
walks agreeing on a wrong name is the differential suite's subject); the
decoded bytes (`run_only.py`); segmented sets, which agree trivially with
`UNC_ERR_SEGMENTED` and no entries; and a walk that lost its place in a
way that repeats every two entries.

**A different kind of walk, in the same layer.** `tools/vmac/walkprobe.py
--check` (in `ci.sh`) grades the twelve HOST-side listers that read a
Macintosh volume back — whether each sees an invisible file, an invisible
folder, a locked file, and anything below the root. All twelve see all
three, so two of the four `EXPECT_*` sets are EMPTY and kept (they fail in
the other direction). **Four more functions in `tools/` list a volume
without returning an entry set**, so nothing grades them; all four pass
`-a`, and `tools/vmac/README.md` has the one-command `ast` re-survey. No
emulator, no ROM, seconds; skips cleanly without hfsutils. Details and
limits: `tools/vmac/README.md`, *What every walk can see*.

## The Macintosh shell's names (`tools/run_macnames.py`, in `ci.sh`)

`mac/macextract_mac.c` cuts every path component to 31 characters (HFS's
limit) and resolves the collisions in `BumpName`, off the File Manager's
`dupFNErr`. The code under test is the shell itself through the mock
Toolbox of `tests/mac_sink_test.c`; subjects are DiskDoubler archives from
`tools/synth_dd.py` (both caps reachable in one shape), except where
noted. Cases:

- two files alike for 31 characters (the second numbered); two FOLDERS in
  the same position (two folders, the second numbered — DECISIONS.md, *a
  folder is a name too*); four 63-byte folders summing to 255, where
  numbering is the only reason the leaf survives; 31 characters written
  whole, 40 cut to 31, a nameless entry written as `_`;
- **the extension is kept and the stem cut** (`...ForTheBoard.rtf`), the
  `~1` before the suffix;
- **the report's lines**: a renamed file and folder each name themselves
  twice; a writable name is not mentioned;
- **a per-entry failure** named in the report while the sound entry comes
  out;
- **102 alike names**, and one file after them whose survival is the
  assertion;
- **the same two folders in a ZIP** (folders existing only inside file
  paths — the shape that used to merge in silence);
- **the same archive extracted TWICE into one destination**: the existing
  top-level folder's twin is numbered `~1` (the maintainer's rule since
  2026-10-11);
- **101 folders whose names shorten alike**: numbering runs out at `~99`
  and the hundred-and-first merges, reported as *combined with*;
- **250 folders against a 200-row memo**: no folder is SPLIT;
- **a UTF-8 name**, driven straight through `sink_begin` by
  `mac_sink_test.c --utf8` (DECISIONS.md, *a name an HFS volume can
  hold*): seven names — folds losslessly; no MacRoman spelling; a lossy
  folder holding a lossless file (one report line); 32 UTF-8 bytes that
  are 16 MacRoman characters and must NOT be cut; two unwritable names
  folding to one disk name, numbered apart; the same bytes with the flag
  clear, not folded. The ENGINE's half is `run_diff.py`'s. **This case
  also runs big-endian under qemu** (`--sink "qemu-m68k
  build/mac_sink_m68k" --case utf8`). A second UTF-8 subject, an archive,
  is in `tests/run_mac_sink.sh`'s own list, graded by
  `tools/check_mac_sink.py`.

**Established that it can fail**: the cap raised to 63 fails five
assertions, the numbering removed fails six (and loses a file), the
empty-name fallback removed fails one, the extension cut the other way
fails four, the numbering restored to its `~9` limit fails four; treating
a directory this run did not make as another folder's (one line in
`EnsureDir`) fails the twice-extracted case. The mock's `PBDirCreateSync`
and `PBGetCatInfoSync` were made honest first (2026-08-29), so
`EnsureDir`'s `dupFNErr` branch is exercised.

**What it cannot see.** A name holding a '/' (the mock builds a Linux
path). Nor the BOX those lines are drawn in: legibility, scrolling and
saving are `interactive.py --report` on an emulated Mac
(`tools/vmac/README.md`), and the fold's own line is `--report-utf8`
(`derived-800saywhat301j.sit`, three *"was named in characters this
Macintosh cannot write"* lines; a control expecting the COMPOSED
spelling's twelve `_` fails).

**And a warning for whoever adds a fixture.** The Mac shell and the Linux
CLI deliberately write DIFFERENT names for a StuffIt 5 entry MacRoman
cannot spell, so a harness grading Mac output NAMES against the oracle
must be taught the fold (`tools/vmac_check.py`, `mac_component`).
Taught: `tools/vmac/checkdisk.py`, `tools/check_mac_sink.py` (the `ci.sh`
layer, which also runs the fold **big-endian under `qemu-m68k` over a
real archive**), and `tools/vmac/os9.py`. **`tools/vmac/run.py` cannot be**:
its verdict is a file count and two summed CRCs, which carry no name
(*Checking a run off the disk*, `tools/vmac/README.md`). A name MacRoman
CAN spell needs no teaching: `derived-Cool_Tools__.sit` cannot fail
`checkdisk.py` with the fold disabled, while `derived-800saywhat301j.sit`
fails it with three names missing and three unexpected.

## The Finder metadata beyond type, creator and flags (`tools/run_meta.py`, `mac_sink_test --meta`, in `ci.sh`)

Two halves, because two parties can get it wrong (DECISIONS.md, *the
metadata, carried to the disk*). `ci.sh` runs `run_meta.py --corpus
--expander`.

**The engine's half: `tools/run_meta.py`.** `macextract l --meta` prints
one `m` row per entry, every field hex: the 32 bytes of FInfo/DInfo and
FXInfo/DXInfo, the backup date, the lock, the comment, `-` where the
archive is silent. Graded against:

| subject | oracle |
|---|---|
| `synth-as-meta.as`, `synth-as-dosro.as` | `lsar` for Finder info, comment and backup date; `tools/synth_as.py --describe` for the lock (no XADMaster key) and backup date 0x80000000 (RFC 1740's unknown, which XADMaster reports as 2068) |
| `synth-sqp-meta.pkg` | `tools/synth_sqp.py`'s own items: nothing else reads the container |
| `--corpus` | every fixture where the engine and `lsar` both state a field: 8 fields on 2026-10-17 |
| the envelopes, generated per run into `.tmp/` by `tools/synth_envelopes.py`: MacBinary I, II and III, uuencode, UUTool with a `.finfo`, base64, `multipart/appledouble` | MacBinary: deark's debug reading (`modules/macbinary.c`) and macunpack's copy of offset 81 (`I_LOCKOFF`), which must agree; UUTool: hexbin's header (`hexbin/mu.c`); MIME: the applefile part via Python's `email`, read by `lsar`; the begin-line mode, a reading in the suite; MacBinary's comment and FXInfo: the generator alone |
| the archive formats (`archive_check`), generated by `tools/synth_archmeta.py`: zip (MacZip `0x334d`, comments, backup date, foreign permissions), pax tar, gzip (MTIME, FCOMMENT), Private File, ArcMac, Now QuickFiler's and SuperDisk!'s sentinel archives, StuffIt 5's sentinel `derived-FloatingNotes.sit` (and spoiled-CRC copies, which must state nothing) | the writing side of each layout, field by field; the sentinels re-read by the measurement tools' walkers; `rexnebular_1_0_0.zip`'s `0x334d` and lock as Info-ZIP's Macintosh UnZip decodes them (`DecodeMac3ExtraField`, `mapattr`); PackIt's lock word as `macunpack -3` copies it |
| `--corpus`, archives (`archive_corpus`) | every zip, tar, gzip, LZH, ARC and StuffIt 5 fixture and every lhasa test archive against `lsar` in UTC, and for LZH lhasa's own header dumps (`test/output/*-hdr.txt`; DECISIONS.md 2026-10-17, *the archives' own Finder info*): 655 fields on 2026-10-17; plus StuffIt 5's archive comment on `Sample Archive.sit` in the cache |
| Mac OS X's sidecars (`sidecar_expectations`): `synth-macosx.zip`, `.tar` and the `-edge` pair (`tools/synth_macosx.py`) | the generator's values, including names that must NOT be listed, and each `-edge` resource fork byte for byte; every zip with a `__MACOSX` member against **libarchive 3.7.4 through ctypes** (`zip:mac-ext`). DECISIONS.md, *the sidecars Mac OS X left beside the file*; controls: apply step removed fails 417 fields, pairing removed fails 15 |
| the Spotlight comment: the `-spot` pair (13 entries) | the generator's values; libarchive, a second attribute reader in the suite (`spot_comment`) and **plistlib**; **`lsar`** per case (`spot_lsar`): 9 compared, `Both` and `Huge` out by design; the `U` mark too. DECISIONS.md 2026-10-18, *the comment Spotlight kept*; controls fail 28, 17 and 4 rows, and every `U` toggled alone |
| `--corpus`, envelopes (`envelope_corpus`) | every fixture sniffed as MacBinary (deark), uuencode or base64 (the begin line), MIME (`email`, then `lsar`), each ZipIt payload (`zipfile`, then deark), and the MacGzip and ZipIt specimens when present: 507 fields of 255 entries on 2026-10-17 |
| DiskDoubler 3.7's own compressed file | the catalog record the subject had before 3.7 compressed it (`tools/vmac/ddmeta.py --writer`'s result; skipped where absent) |
| `--expander` | **StuffIt classic against StuffIt Expander 4.0.2's own output** (`tools/vmac/sitmeta.py`: 225 corpus, 21 sentinel archives), field for field: 241 archives, 6,627 fields, 0 disagreements on 2026-10-17; 5 archives Expander did not extract whole are left out by name. Skipped, and said so, without the results |

**Controls.** Each field tampered with in the engine's row must fail: 37
of 37, and 228 of 228 in the archive tables (1,511 and 361 on 2026-10-18).
Seven scratch engines with one rule undone (StuffIt 5's CRC gate, zip's
host rule, LZH's POSIX mode, the DOS leap day, the pax mtime, one byte of
`0x334d`'s FXInfo order, PackIt's lock word) each fail. **In the envelope
tables a field the oracle states and the engine prints as `-` FAILS**
(505 of 505 caught). `--expander` has seven controls of its own; each of
the eight rules removed from `sit_finder` disagrees on 11 to 500 fields
(DECISIONS.md 2026-10-17, *the window Expander puts back*).

**The shell's half: `mac_sink_test --meta`** (`tests/run_mac_sink.sh`). A
folder and two files go through the real `sink_begin`/`sink_end` against a
mock catalog that stamps a folder with "now" on create/delete, as the File
Manager does. Checked: DInfo/FInfo, DXInfo/FXInfo with the comment id
cleared, three dates each, the lock, the comment through the mock Desktop
Manager, the folder's modification date after two creates; no comment and
no report line without a Desktop Manager; a `UNC_META_CMT_UTF8` comment
folded into MacRoman and the same bytes unmarked passed raw. Six controls
drop one write each and each fails exactly its own check.

**Dates and their zone** (DECISIONS.md, *dates in the Macintosh's own
zone*). `l --meta` prints a `Z` after a date the engine marks as an
instant; `run_meta.py` grades the mark wherever it grades a date (LZH
levels 0 and 1 by `lzh_instants`): 119 marked and 245 wall-clock dates on
2026-10-17, 3 ungraded, 69 controls. **`mac_sink_test --zone`** holds the
shell's half (marked dates moved by a mocked offset, unmarked not), with
two controls. It cannot see what ReadLocation answers;
`tools/vmac/tzrun.py` reads that off emulated disks (tools/vmac/README.md,
*Dates in the Macintosh's zone*).

**`mac_sink_test --dirdates`** holds the one-entry folder-date cache to
three orders — a subfolder between a folder's files, a folder entry after
its files, a failed entry's delete — with three controls (DECISIONS.md
2026-10-17, *the date held once per folder*).

**What neither can see.** A field the engine does not read yet, outside
the envelope tables: it prints `-` and passes. Generated archive cases
grade arithmetic against the documented layout, not what a real writer
puts there: Private File, ArcMac and the pax comment have no second reader,
and no corpus file carries a zip Finder comment, a gzip comment, a pax
header or a zip backup date. MacLHA's payloads; a MacBinary comment or
FXInfo on any real file (generator only). With `--expander`: the dates
(`metarun.py --expander` reads them off the disk), and any StuffIt reader
but Expander 4.0.2. Of the sidecars: entries 4, 8, 10 and 12 on a real
file (copyfile writes only 2 and 9); a Spotlight comment on a real file
(none found, DECISIONS.md 2026-10-18); the window rule, which
`spot_comment` states rather than derives; any other extended attribute.
The real File Manager and Desktop Manager (`tools/vmac/metarun.py`,
`tools/vmac/README.md`), and what the Finder then does with any of it.

## A cut archive is NOTICED (`tools/run_truncation.py`, in `ci.sh`)

`run_robustness.py` accepts exit 0 on a truncated archive, so a walk that
hands over the entries before the cut and reports success passes it,
9,320 variants clean (BLOCKERS.md). This asks the oracle: the most-entried
two fixtures of each format (`--per-format 2`) are cut to 25, 50 and 75 % —
**111 archives across 19 formats** on 2026-10-17's `ci.sh` — and a
fixture where `lsar` reports a parse failure and `macextract t` exits 0 is
a failure. AppleSingle joined by failing it (DECISIONS.md 2026-10-17, *the
metadata, carried to the disk*).

**Established that it can fail**: the DiskDoubler walk's clean-end rule
put back fails it on `ddtf-*.dd`; removing StuffIt's clamp report fails it
four times on two `.sit` fixtures. Fixtures are chosen by entry count, not
alphabetically (alphabetical picked single-file `.dd` archives, which
cannot fail).

**The default sample does not reach every fixture**: `synth-exo-zip-implode.zip`
is not cut on an ordinary run. Swept at `--per-format 20` on 2026-10-07:
**504 cut archives across 16 formats, 0 silent**; a wider default would
cut the 29.7 MB `rexnebular_1_0_0.zip` three more times every run.

**What it cannot see.** A format that CANNOT notice (a cut tar is a short
tar; `unar` accepts it too). A DDA2 cut that lands where a valid archive
may end without its 0xBBBB marker (`ddtf-ddpro411dd3.dd` cut to a fifth;
DECISIONS.md 2026-08-29, *a cut archive*). A format `unar` cannot read at
all (SuperDisk!, Now Compress, SpaceSaver, AppleLink packages); for
AppleLink, `tools/run_sqp.py`'s lane 4 asserts the engine's own answer.
And WHERE the cut falls — three fractions per fixture. A wider sweep, not
in `ci.sh`: all 932 fixtures at the same three fractions, 2,796 cut
archives, none silent (2026-08-29).

## The progress callback (`tools/run_ticks.py`, in `ci.sh`)

`UncProgress.tick` is the engine's only cooperative yield; on classic Mac
OS a format that does not call it freezes the progress dialog and disables
Cmd-. and Cancel (Now Compress never called it until 2026-08-28;
DECISIONS.md 2026-08-28).

`tick_probe.c` extracts with a counting callback and a sink that keeps
nothing, printing `ret`, the call count, the widest gap in `bytes_done`,
and how far it ran past the total (`overrun=`). `run_ticks.py` sweeps the
corpus (envelopes peeled by `tools/envelopes.py`, shared with the walk
suite: **1,363 archives**) and applies three rules: an archive over 64 KB
that extracts must tick at least once; no gap may exceed 32 KB
(`NOW_INBLOCK`, the largest block any format reads whole; widest gap
30,634 B); and `bytes_done` must not pass the total — any overrun not in
`KNOWN_OVERRUN` fails, and `KNOWN_OVERRUN` is empty (DECISIONS.md
2026-10-09, *the bar that counted the peek* and *DiskDoubler read every
block six times*).

**It can fail**: reverting the one-line fix in `src/fmt_now.c` fails it on
`derived-SyntheticReferences2.0.sea`; reverting zip's dry-pass fix fails
`NPWritersKit.zip` and the Implode fixture; reverting the uuencode fix
fails both `uu-wild-*` rows (measured).

**What it cannot see:** how long a gap takes. It counts input bytes, so a
decoder that spends a minute inside one 8 KB step passes — Arsenic is that
shape (`unc_progress_at`), and passed while a Mac Plus went 254 s without a
callback (DECISIONS.md 2026-10-12, *the block nobody could cancel*). The
gap in TIME is `-D UNC_AT_TICKGAP` on the emulator (tools/vmac/README.md),
not in `ci.sh`. **Nor a bar that goes backwards, or one that sits below
100 % with no work left**: only the excess over the total is graded
(uuencode's writing pass restarts from the `begin` line by design).

## Decryption (`tools/run_crypt.py`, in `ci.sh`)

**Every archive this suite DECRYPTS, it also writes** — or has somebody
else's program write — so that no decoder is graded against a generator
sharing its reading. The corpus has exactly one encrypted entry, and
`lsar -j` reports `XADIsEncrypted` 0 for every fixture including it
(FORMATS.md, *Encryption*).

**That one is wild, and what it grades is a refusal** (no password is
published). `sitcrypt-wild-F7Menus.sit.bin` asserts: method byte `0x12`
with a 5,944-byte resource fork (no folder has one); an `MKey` in the
archive's resource fork; through the envelope, *"wrong password, or none
given"* with no and a wrong password and no fork written; **forkless,
"encrypted by a scheme we cannot read"**; and `unar` failing *"Error on
decrunching"* with `lsar` setting no flag, so an oracle that learns the
bit is noticed. **Measured able to fail**: without the `SIT_NEWDE` term
the lane reports three problems.

**Who grades each cipher:**

- **PKWARE's zip cipher and ARC's garble**: `zip -P` (stored and deflated)
  and `arc g<password>` write fixtures that owe nothing to this project.
- **StuffIt classic's StuffItDES, StuffIt 5's RC4**: `tools/synth_crypt.py`
  writes them and **`unar -p` adjudicates**. StuffIt classic's fixture is
  MacBinary (the `'MKey'` verifier is in the resource fork); our CLI gets
  the bare `.sit` and reads its own sidecar.
- **StuffIt classic by StuffIt Deluxe 3.5.1**, when the emulator has been
  run: `tools/vmac/sitcrypt.py` has its Magic Menu encrypt a known file;
  three kept, passwords of 8, 9 and 17 characters (the lengths that showed
  the fold count is ceil(len/8)).
- **3.5.1's own cipher words** (`tools/vmac/sitenc351.py --script`: `des`,
  `newde`, `encrypt`, and `encrypt` after `Set encryptor "NewDEx"`, with
  2.0's three Encryptor modules installed, plus a control). `check_sit351`
  decrypts each to both forks, refuses a wrong password through `x` (`t`
  and `l` act on the MacBinary envelope alone), and **asserts the header**:
  method 13 on both forks and encryptor id 4 at 107/109 (FORMATS.md,
  *Where an archive names the module*). Byte 109 set to 1 gives one
  problem; a wrong password in `made.json` three. **It cannot see** any
  other 3.x build.
- **One wild StuffIt classic archive, graded by the installer that
  carries it**: Aladdin's *Shortcut 1.5.3 Update*, password read off its
  own memory. `check_installermaker` hashes six files against what the
  installer wrote to an emulated disk (resource fork bytes 16..127
  masked), expects exactly one failure (the Addendum's CRC), and checks
  the two forks with stray bytes at 109 still carry 3 and 5. The engine
  before `sit_enc_id` gives three problems.
- **The archive-key oracle**: `tools/sit_mkey_oracle.py`'s self-test (in
  `ci.sh`) grades it on the four MKeys Aladdin's software wrote, and
  `tools/sit_akscan.c` against the Python verifier; five scanner mutations
  and one of `unfold()` each fail it (re-measured 2026-10-10). **It cannot
  see** a fault shared by both scanners.
- **PackIt's XOR and DES, by PackIt III 1.3** (`unar` IS XADMaster, where
  both were transcribed from, so it could not fail on a shared mistake —
  DECISIONS.md 2026-10-05, *the reference implementation was the
  fixture's payload*). Its `CODE` 1, inside the fixture `packit.pit_.bin`,
  is run under `qemu-m68k` by `tools/pitcrypt/pit_run.c`, and
  `tools/derive_pitcrypt.py --make` has it encrypt three archives into
  `$UNC_VMAC_HOME/specimens/pitcrypt/`; `run_crypt.py` replays them (eight
  cases) and says loudly when there are none. The third carries a false
  `'PMag'` off PackIt's eight-byte grid — **the only part that can fail
  on the byte-wise resync**. `tools/derive_pitcrypt.py` with no arguments
  checks the reading itself (32 byte patterns in `CODE` 1, `CODE` 256's
  nine tables against FIPS 46-3 via `gen_crypt_tables.py`); not in
  `ci.sh` (needs the fixture, the m68k cross-compiler and `qemu-m68k`), so
  **nothing in a `ci.sh` run compiles `pit_run.c` or re-checks a witness**
  — `tools/derive_sqp.py`'s position too.
- **WinZip AES**: no second reader here (`unar` 1.10.8 cannot open one),
  so **7-Zip** writes four cases (256, 192, 128, and one stored), verifies
  them itself, and our output must equal the input; each also has a
  ciphertext byte flipped, because AE-2 stores no CRC and the ten-byte
  authentication code must catch it.
- **The fuzzer's seeds**: `synth_crypt.py` also writes PKWARE, AES 256 and
  128, and a garbled ARC archive (*Fuzzing*, above); each is extracted
  here and handed back out — `unar -p` for the traditional and ARC ones,
  `7z t` for AES — and all four must return the input. One flipped bit per
  zip shape fails `unar`, `7z` and our CLI alike (2026-09-26).

**ARC's garble on every run is the synthetic shape**: `arc` lives in
`build/arc`, which `ci.sh`'s `make clean` deletes and nothing re-fetches,
so the three real-encoder cases skip (printed) unless `tools/get_arc.sh`
is run between runs. The synthetic shape garbles three of `synth_arc.py`'s
methods and failed against the engine of 2026-09-26 (DECISIONS.md
2026-09-26, *the guard that was on the other side*); it also asserts that
no password fails every entry rather than handing over garbled bytes.

**StuffItDES's construction** (the 2026-09-19 fold onto standard DES) is
proved outside `ci.sh` by `python3 tools/fit_sitdes.py` (XADMaster's
`DES_SPtrans` against the relabelled standard table, 20,000 random pairs
and every single-bit case) and by `tools/gen_crypt_tables.py`, which also
asserts its readings of FIPS 46-3's tables
(`reference/notes/fips46-3.pdf`) and RFC 1321's constants. Regenerating
`src/crypt_tables.h` needs `reference/`, which is why `ci.sh` cannot check
the header against its generator (DECISIONS.md 2026-09-19, *the DES that
was only wearing a disguise*).

**Big-endian**: `tests/run_mac_sink.sh` runs the unit tests under
`qemu-m68k` (`m68k-linux-gnu-gcc -mcpu=68000`), so every cipher vector —
DES, StuffItDES, MD5, RC4, the zip and Compact Pro keystreams, SHA-1,
HMAC-SHA1, PBKDF2, AES — is checked in the target's word order. Nothing
else does: no Mac-sample fixture is encrypted.

Also asserted: a **wrong** password is reported per entry with no output
(checked with `t`); **no** password leaves the archive walkable (PackIt's
clear entries either side still come out); a StuffIt classic archive
**without** its resource fork reports "encrypted", not "wrong password";
ARC opens under the password as typed and upper-cased (`arc` 5.21q keys on
capitals).

**What this cannot see.**

- **StuffIt 5's suite cases are generated files**, adjudicated by `unar`
  — one reading, not two. Three archives **DropStuff 5.0.1 wrote** on Mac
  OS 9.2 settle the cipher (FORMATS.md, *StuffIt 5's RC4*), at passwords of
  4, 9 and 17 characters; not committed, re-made with
  `tools/vmac/os9mouse.py` (`tools/vmac/README.md`, *Mac OS 9 with the
  pointer*) and checked by hand:

      macextract x -p swordfish -o /tmp/out ~/.cache/macextract/sit5/specimens/enc-swordfish.sit
- **Compact Pro is graded by Compact Pro** only when the emulator has run
  `tools/vmac/cptcrypt.py --make --probe`; on a fresh clone the case
  skips, loudly. A round trip through our own cipher is deliberately NOT
  substituted.
- The **`arc` cases skip** when `build/arc/` is empty (after `make clean`);
  run `tools/get_arc.sh` first. The skip is printed.
## Now Compress: the archives the corpus does not have (`tools/run_now.py`, in `ci.sh`)

The corpus's first real fixture reaches two block shapes; the rest had no
archive. `tools/synth_now.py` writes them and `unar` grades them three ways
— the bytes that went in, the oracle's output, ours — as the ARC and
uuencode suites do.

Fourteen archives: one per block shape (prose, run-length content, noise),
one stream cycling all five shapes with non-zero `padding`, a nested folder
tree, an empty folder, a two-fork file, a resource-only file, a code 17
bits deep, three whose table offsets are off by a constant (one obviously,
one only after a checksum fails, one by **-64** — forcing the search's
answer positive refuses that one alone, 1 of 4), and one whose first block
reaches into the previous stream's dictionary cache. Type and creator are
checked separately (ours from `l -v`, the oracle's from its AppleDouble
sidecar).

**`synth-now-mixed.now` is also a committed fixture** with an `unar`
manifest, so `run_diff.py` grades those paths with no `unar` present; it is
restored from `tools/synth_now.py -o` (*Corpus*).

**The same trees are built a second way**, `build_archive(lead=True,
word=True, trailer=True)` — the shape the encoder writes — and required to
be **word-aligned**, to carry a well-formed **16-byte archive trailer** and
the **fork-boundary record**, and to be read by `derive_now.py` and this
CLI; the `unar`-graded ones stay unaligned because `unar` refuses a region
leaving it fewer than four spare bits. **One more archive is built the way
Now Compress builds one** (those plus 32,768-byte blocks) and graded all
three ways — the rung Now Compress itself extracted (*The rungs*).

**One archive is graded ONE way**, because the reference is wrong: a
zero-length file anywhere but last makes `unar` decode the next file from a
stale block. Our extraction must be byte-exact AND the oracle must still
fail, so a fixed `unar` reports itself (DECISIONS.md, "Now Compress: an
empty file in the middle").

**Two mutations are built in**: a flipped byte inside a stored block must
change the output (no block checksum), and one inside a block table must be
refused by both implementations. Twelve mutations of `fmt_now.c` all fail
the suite (DECISIONS.md, "Now Compress: writing the archives the corpus
never had").

**The READER half of the offset-delta search**: `ci.sh` rebases a generated
archive by 100 with `tools/mutate_now.py --delta` (recomputing the table's
32-bit sum) and requires `tools/derive_now.py` to decode the same blocks,
15 of 15; deleting `derive_now`'s `table_delta` turns it red. It cannot see
whether a real encoder's delta has this shape — no file Now Compress wrote
here needs the search (FORMATS.md, *Now Compress*).

**The corpus's second real archive**, `derived-SyntheticReferences2.0.sea`
(1995), defeats `unar` on every fork. `run_now.py` asserts **the resource
fork we produce is a resource fork** (its first 16 bytes account for its
length) plus per-fork hashes; mutating the decoder's fork order fails both.
Skipped with a message when not fetched. The hashes are the archive's own
decoder's: `tools/vmac/nowcompress.py --adjudicate` runs it under the
emulator and it agrees on all four forks — 9,949,696 bytes, the resource
fork identical with bytes 16..127 masked (DECISIONS.md, "The archive that
carries its own oracle").

**Archives from the ENCODER**, when they exist: `tools/vmac/nowcompress.py`
drives Now QuickFiler 5.0.1 under Mini vMac, and `run_now.py` requires each
specimen to decode back to its input; skipped (as in CI) when absent. Seven
specimens cover stored, LZSS-only, Huffman-then-LZSS and new LZSS
(FORMATS.md ✧); `--case probe`'s four members built to RESEMBLE each other
found a decoder defect (DECISIONS.md 2026-09-21, *the window that stopped
at the fork*).

**What this cannot see.** XADMaster is the only other implementation, and
`fmt_now.c` was transcribed from it — so a shape with no encoder specimen
proves the transcription, not the format (true today for nothing the four
encoder cases reach, and for anything they do not). The generator leaves a
whole spare byte at every stream end, because `unar` refuses a stream ending
within 7 bits of its buffer. And these archives have run on Linux and under
qemu-m68k, not on a Mac: the Mac sample's Now Compress entry is the real
fixture, so the shapes only these archives reach have never been decoded on
a 68000 with a real File Manager; adding `synth-now-mixed.now` to
`tools/vmac/sample.txt` would need the sample's FORMATS.md counts
re-measured.

## LZH's -lh2- (`tools/run_lzh.py`, in `ci.sh`)

No corpus archive uses `-lh2-`, `lhasa` has no decoder for it, and the LHa
in `reference/` never selects it; the maintained LHa fork decodes it and
cannot write one. So `sh tools/build_lha_lh2.sh` fetches that fork at a
pinned commit into `reference/` (unmodified), and `run_lzh.py` builds it on
demand with `tools/lha-lh2/lh2-encoder.patch` (the mirror of its
`decode_p_dyn`). The source lives in `reference/` because `ci.sh`'s `make
clean` once deleted a `build/`-only encoder and the grading went quiet.
**The data is the reference implementation's**, and each archive is
verified by that program's own decoder before this engine sees it.

Nine subjects at three header levels, **15 `-lh2-` entries** per run.
Against vacuous passes: **the method of every entry is read out of the
headers** and fewer than three `-lh2-` entries in an archive fails the run
(LHa falls back to `-lh0-`); and **the encoder's own decoder runs first**.
Demonstrated failing: inverting the tree walk's bit sense gives `-lh2-
level 2: text.txt missing` and `zeros.bin differs`.

**What it cannot see.** The window preload (spaces): zeroing it changes no
result, because LHa never emits a match reaching before the output's start.
And the patch is conservative (a match whose position symbol has no node
yet goes out as literals), so a real 1990 encoder may have used offsets at a
boundary these specimens never reach.

### `-lh3-`, which needed no patch at all

`-lh3-` is a STATIC code rebuilt per block; the encoder is in `run_lzh.py`,
whose only job is streams **LHa accepts**, and LHa extracts every archive
before this engine is handed it. Six entries per run (plus the match cases,
*M9 additions*), including the "this block is one symbol" form and an
explicitly sent position tree. Breaking the block's symbol count by one
fails it: `one.bin missing`, `single.bin differs`, `ptree.txt differs`.

**A difference recorded rather than tested:** LHa refuses an INCOMPLETE
code table ("Bad table (case b)") and this engine's canonical builder
accepts one, so a corrupt `-lh3-` table is a per-entry error in LHa and
garbage output here. The suite feeds only complete tables.

## When a suite skips, and when it must not (2026-09-09)

Suites that build their oracle out of `reference/` — munpack and deark for
`run_mime.py`, btoa for `run_btoa.py`, lhasa and LHa for `run_lzh.py` —
answer "is the oracle here?" with three values:

| state | verdict | why |
|---|---|---|
| the binary is built | run | — |
| `reference/X` is **absent** | **skip, exit 0** | a fresh clone has no `reference/`, and `ci.sh` must still run end to end |
| `reference/X` is **present** and will not build | **exit 1** | somebody fetched it; the differential coverage it pays for has gone, and nothing in that suite is graded against a second implementation any more |

The message prints what the build said and ends "fix the build, or delete
`reference/X` to make this a skip" (DECISIONS.md 2026-09-09, *the oracle
that built two times in three*). Both failure paths were made to fire
(`reference/btoa/atob.c` moved aside; `build_mpack.sh`'s old `cp -r`
restored).

**What this does NOT cover.** A suite can pass with the oracle built and
doing nothing — an assertion that never runs, a sweep over zero files.
Every suite prints its case count for that reason, and a count that drops
is the only signal.

## dist/ is compared with the build (`ci.sh` variant 4, added 2026-09-22)

`dist/` is a committed binary and the only download. After variant 4
builds `build/mac/MacExtract.bin`, `ci.sh` compares the SHA-256 of
everything from offset 128 on — the resource fork; the data fork is 0
bytes — with `dist/MacExtract.bin`'s. The first 128 bytes (MacBinary,
carrying dates) are not compared. The failure names the fix — `sh
tools/make_dist.sh`, in the same commit as the change to `mac/` or `src/`.
(Before the check, `0aa9101` had shipped a download 591 B of resource fork
behind its tree.)

## The three Macintosh configurations (`ci.sh` variants 4, 4b, 4c, 4d)

The application is three builds from one tree, and `ci.sh` compiles all
three, because a configuration nothing builds rots (DECISIONS.md
2026-09-25, *two branches that were one file apart*; the control joined
2026-09-26 after drifting 4 B over its ratchet unbuilt — DECISIONS.md
2026-09-26, *the numbers DART left behind*).

| variant | build | what it is |
|---|---|---|
| 4 | `build/mac` | the SHIPPED application — seventeen images, **eager**: one bundle read at launch, everything the sniffed format cannot want released before the engine takes its budget. `dist/` is compared against this one |
| 4c | `build/mac-lazy` | `UNC_OVL_LAZY=1` — the same images, one resource each, read when a format turns out to want one. Not shipped |
| 4d | `build/mac-resident` | `UNC_OVL_RESIDENT=1` — every decoder linked in. The CONTROL for budget measurements (FORMATS.md, *Overlays*), with its own ceiling in `tools/build_mac.sh` |

Variant 4b (`UNC_AT_OVERLAY=1 sh tools/build_mac.sh`) rebuilds the eager
configuration with the variable set explicitly — it has been the default
since 2026-09-25 (`mac/CMakeLists.txt`) — and is followed by `run_tiers.py
--check-images`; 4d is followed by `--check-saved`. All of them skip
without a Retro68 toolchain.

**What these variants CANNOT see.** They compile; what the loader does
with an image is variant 3c's (next section). What stays the emulator
tiers' alone is Retro68's code generation, the real Resource Manager,
fragmentation, and any machine with an instruction cache.

**Made to fail before it was believed.** `unc_strerror`'s `"ok"` changed
to `"oK"` fails the `dist/` check on a `build/mac/MacExtract.bin` of
**exactly the same 187,776 bytes** as the shipped one; three builds of one
source produced the same payload hash.

**What it cannot see:**

- **`dist/MacExtract.dsk` and `dist/MacExtract-1440K.img`.** `make_dist.sh`
  writes all three and round-trips each image's application against the
  `.bin`; the images are HFS volumes with their own dates and are not
  compared byte for byte.
- **Anything, without a Retro68 toolchain.**
- **A docs-only change**, which does not run `ci.sh` (CLAUDE.md, Rules).
  `dist/README.txt` — the release notes verbatim — is `tools/check_docs.py`'s
  check 7: it re-renders `make_dist.sh`'s heredoc with the current
  `UNC_VERSION` and reports the first line that differs (made to fail three
  ways). Prose edited in the script reaches the download only when somebody
  re-runs it.
- **Whether the application is CORRECT** — that is everything above.

## The overlay loader, off the Macintosh (`tests/run_overlay_host.sh`, `ci.sh` variant 3c)

The `'OVLY'` images exist only in a Retro68 build, so every other lane runs
the decoders as linked code. Nothing in the mechanism is Retro68's,
though: the images are flat `-mpcrel` m68k blobs with a relocation trailer,
so `mkoverlay.sh` takes a toolchain PREFIX (`OVL_TOOL`) and builds the same
sources for `m68k-linux-gnu`; stub Toolbox headers in `tests/ovlbox/toolbox/`
let `mac/ovl_load_eager.c`, `mac/ovl_load_lazy.c`, `mac/ovl_reloc.c` and
`mac/ovl_shim.c` compile **unmodified**; `qemu-m68k` runs the result
(DECISIONS.md 2026-09-26, *the overlay images were never Retro68's to
hold*).

Four lanes, in one script, ~65 s, plus `--shipped-only` as variant 3d:

| lane | what it grades |
|---|---|
| the images | seventeen of them, from `tools/overlay/images.py`'s inventory — PARSED out of `mac/CMakeLists.txt`, so an image cannot exist in the build and be missing here; the asserted count has to be raised with each new image (`ovl_sniff` was the seventeenth; DECISIONS.md, *the probes that left with the bundle*) |
| the loader | both lifetimes, natively under ASan+UBSan and big-endian under `qemu-m68k`: read counts, keep and release per format (including that a StuffIt release gives `ovl_zipold` back), the `wa`/`kf`/`rf`/`fc`/`fn` probe fields, and **every relocation in every image checked against the raw file's own trailer at the address the image runs at** — including a kept copy, relocated by the difference of two addresses |
| extraction | the sink suite's fixture list, extracted THROUGH the images under `qemu-m68k` and compared with the oracle manifests by `tools/check_mac_sink.py`: **20 fixtures, byte-exact, in both lifetimes**, including `synth-exo-zip-implode.zip` (the only run zip method 6 gets through its own image). **The only check that zip KEEPS `ovl_zipold`**: with that keep removed, the eager lane fails on `derived-MUSFMT10.ZIP` (bent by hand once; not a `--mutate` break) |
| one per image | twenty fixtures reaching sixteen of the seventeen images (every one runs the sniffer's, released before the decoder's is called; `shrink-wild-BBA.zip` and `reduce-wild-fractlan.zip` for `ovl_zipold`), each compared with the RESIDENT build of the same engine — the only oracle for an image no manifest covers (SuperDisk!, btoa, MIME, AppleLink). Exit status is compared too |
| the SHIPPED images (`--shipped-only`, `ci.sh` variant 3d) | the same loader against the images **Retro68** just built — the bytes `dist/` ships — in both lifetimes: found, relocated, kept, released. The only check on the bundle's own directory and on **30 relocations across six images** (the m68k-linux build emits 15 in one). They cannot be CALLED: a Retro68 image entered from an m68k-linux host binary segfaults (measured) |

**The mock is harsher than a Macintosh, deliberately**
(`tests/ovlbox/ovlbox.c`): every unlocked block moves on every allocation;
every block's last byte abuts a guard page; a released resource is really
gone, the next `GetResource` counted as a fresh read.

**Made to fail, every run.** `--mutate` breaks the loader six ways and
requires each to be caught: the delta dropped, the trailer's table
mislocated, a kept copy relocated by its own address, the bundle fixup not
flushing, the lazy loader not locking, the codecs image not kept.
`tests/ovlbox/mutate.py` FAILS when its pattern is absent (a `sed` version
had reported unapplied mutations as uncaught defects).

**What it CANNOT see** (the list is `tests/ovlbox/ovlbox.c`'s header; the
emulator tiers cover these):

- **No instruction cache.** The flush is counted, never needed; whether it
  WORKS is 68020-and-up silicon's answer (BLOCKERS.md, *Status*: the LC
  475, round 2).
- **Not Retro68's code generation, where an image is EXECUTED** (variant 3d
  loads the shipped images but cannot run them).
- **No Resource Manager**: no resource map, no purging, no file.
- **No fragmentation** — `tools/run_tiers.py`'s blind spot too.
- **Nothing about the interface**, and no budget: `UNC_AT_BUDGET` is
  defined for the loader lane only.
- **The control lane's oracle is this project's own output**, so it cannot
  notice a decoder wrong in both configurations; that is the differential
  suite's job. This lane grades only that the mechanism is transparent.

## Alysis SuperDisk! (`tools/run_superdisk.py`, in `ci.sh`)

`unar` and `macunpack` stop at the BinHex envelope, so the manifests of the
corpus's two SuperDisk! archives describe only the payload file. Both are
self-extracting, so the grading was done by the archives themselves —
`tools/vmac/superdisk.py --adjudicate`, under System 7 on an emulated Mac
Plus, 5 forks, all identical — and this suite replays that verdict offline:
per-fork size and SHA-256, the sniff, and the file count from `l`.

**It runs on the PAYLOAD** (unwrapped with `x -nr` first): to
`run_robustness.sh` and `fuzz.py` these fixtures are BinHex files, and all
9,320 of the suite's variants exercise the BinHex layer. So **116 corrupted
variants** — ten truncations and forty-eight bit-flips per archive — live
here, FORCED with `-f "SuperDisk!"` (a truncated archive loses the trailing
`0x27` record and sniffs as *unknown*). **A budget run per archive** checks
the per-entry contract: `--budget 50000` refuses every method-11 fork of
`alysis-disk-expander-12`, and the run must still NAME every entry.

**What this cannot see.** The hashes were produced by this reader before
the emulator confirmed them: a regression fence, not an oracle
(re-confirm with `--adjudicate`). It grades methods 7 and 11 only, and
**all seven blocks across both fixtures are coded**, so `sd_block_head`'s
stored branch is graded on the emulator instead (`tools/vmac/superdisk.py
--stored`, byte-exact 2026-09-01; FORMATS.md, *Alysis SuperDisk!*). The
unit test carries a two-fork file (fork order) and an undecodable method
BETWEEN two decodable entries. **Every other method is graded by the
suite below.**

## SuperDisk!'s second implementation (`tools/sdmodule/`, in `ci.sh`)

No Macintosh needed. Disk Expander 1.2 (`fixtures/alysis-disk-expander-12.hqx`)
holds one `Cmpr` resource per codec, 68k code with no Toolbox in it.
`sdmod_run.c` is built for m68k-linux and calls one under `qemu-m68k` with
the parameter block INIT 32 fills in; the driver lifts the modules out of the
fixture. Skips cleanly without qemu-m68k or the cross-compiler.

    tools/sdmodule/run_sdmodule.py --macextract build/macextract
    tools/sdmodule/run_sdmodule.py --list        # the seven modules

1. **Every real block in both corpus archives** whose method has a module,
   against this engine's output — then one block CORRUPTED, which must not
   match.
2. **The specimens Alysis's own 1991 control panel wrote**
   (`tools/vmac/sdcompress.py`), when cached: 22 blocks of methods 1 and 6,
   byte-exact both ways, eight sized to the refill boundary (`--boundary`;
   `tools/sdhuff.py`; DECISIONS.md, the refill boundary).
3. **Synthetic blocks for methods 1..9**, through both readers, no case
   excused: every method agrees 12/12.
4. **Method 10 three ways**: a stream this harness encodes, decoded by this
   engine and by SlowFastA's module — its only grading (it caught a
   match-length misreading on the first run).
5. **Tennessee**, method 20's module, is an ENCODER: five blocks it writes
   must declare method 11 and decode back to their input — the only
   method-11 compressor in reach.
6. **Method 13**, the other compressor: four streams must declare method 13
   and carry the input length in a 32-bit field, its decompress command
   must break into the debugger, and **no method this engine knows may read
   the payload** (passes today by finding nothing; module 20 handed in under
   13's number fires three of four checks).

**The callback**: "Tighter" (methods 2, 3, 4, 6, 7, 8) hands its Huffman
regions back to its CALLER via `jsr` through the parameter block, so the
runner is a dispatcher too.

`tools/vmac/rescomp.py` (Alysis Resource Compressor 2.0; `--modules` lists
its codec library without an emulator) settled a negative: it compresses
into Apple's resource container, not a `Cmpr` stream, so it is not method
10's writer (OPEN_ITEMS.md).

**What it cannot see.** Synthetic Huffman regions use a flat 8-bit table,
so no real tree shape is exercised. Method 10's cases are one block each,
so history BETWEEN blocks is exercised only via code shared with
SlowFastB. **Method 13's output cannot be checked by anything** — no
decoder for it exists in reach. Where both sides came from one reading,
a misreading of what the original COMPRESSOR emits does not show. The one
disagreement between the two references is counted and printed
(FORMATS.md, the method table).

## SpaceSaver's own codecs (`tools/ssmodule/`, in `ci.sh`)

Each SpaceSaver method is a `CMod` resource holding a **compressor at +0x08
and an expander at +0x10**, so the modules are both specimen generator and
second implementation. `ssmod_run.c` builds the parameter block
`ExpandFork` builds and calls a vector under `qemu-m68k`; the driver lifts
the modules and the preset dictionary out of the installed control panel,
no emulator, about 3 seconds.

    tools/ssmodule/run_ssmodule.py --macextract build/macextract
    tools/ssmodule/run_ssmodule.py --keep        # leave one .ss per method

1. **Round trip through Aladdin's code alone**, both decompress-only builds
   included — what says the parameter block and callbacks are right.
2. **Negative controls**: a corrupted stream, and methods 3 and 4 without
   the preset dictionary, must come back wrong.
3. **A hand-built stored block** both Original expanders must return
   verbatim (flag byte 1 at +0, big-endian length at +4, payload at +8).
4. **This engine against the module** for every method, byte-exact, 44
   forks; `IMPLEMENTED` in the driver must match `src/fmt_spacesaver.c` from
   either side.
5. **Corrupted specimens through this engine**, 40 per method — the only
   damaged input these codecs meet (no SpaceSaver fixture). Each must exit
   as itself, and at all; every module call has a timeout (`CMod 3` does
   not terminate on a corrupted stream).
6. `--keep` writes one specimen per method into
   `specimens/spacesaver/modules/` (a subdirectory, so `run_spacesaver.py`
   does not adopt them) — **what the Macintosh tier replays for methods 1,
   2 and 3**: `tools/vmac/run.py --expect .../modules/m1.ss ...`, 3/3 at 4 MB
   and 3/3 at the 1 MB floor (FORMATS.md, *StuffIt SpaceSaver*).

**What it cannot see.** The modules know nothing of the 84-byte header, so
this grades codecs, not files (*StuffIt SpaceSaver*, below, grades files
the application wrote). The subjects are ours. And the Original
compressors execute an F-line `0xFFFF` on the store-verbatim branch, which
is counted rather than emulated (DECISIONS.md 2026-08-25, SpaceSaver's
codecs).
## AppleLink packages: SqueezePlay (`tools/run_sqp.py`, in `ci.sh`)

Nothing but Aladdin's own translator reads the container (`unar`, deark and
macunpack have zero hits for "applelink" or "squeezeplay", checked
2026-10-05), so five lanes grade different things:

```sh
python3 tools/run_sqp.py --macextract build/san/macextract
python3 tools/run_sqp.py --register        # rewrite the six manifests
python3 tools/derive_sqp.py                # grade the READING, not the engine
python3 tools/derive_sqp.py --witness      # and grade it against the binary
```

| lane | subject | oracle |
|---|---|---|
| 1 | the **eight real packages** — **67 forks**, every path the format has | three at once, because a package carries no checksum: **`tools/derive_sqp.py`'s** independent reading of `AppleLink Package Translator` 3.0.3, **each record's own declared expanded length**, and for 4 of the 67 the sha256 that script recorded on 2026-10-05 (IMPORTED, not copied). Skips cleanly without `tools/fetch_specimens.py --only applelink` |
| 1 | `Iconf Display`'s two members that want one output file | the engine must REFUSE the second entry under `-nr` and name it, and `--forks hidden` must write all six (FORMATS.md, *Two members of one package that want one file*) |
| 2 | **six synthesised packages** | the bytes `tools/synth_sqp.py` compressed |
| 3 | every **LZW fork** of all fourteen — 59 real, 18 synthesised | **`gzip -dc`**, over the fork's own bytes with three bytes of `.Z` header in front. Skips cleanly without gzip |
| 4 | **ten bent packages** and **two files of zeros**, then **two packages of one empty file**, then one cut package | the sniffer must answer `unknown` for the twelve, `AppleLink package` for the two (whose one empty file must also extract), and the cut one must be reported truncated |
| 5 | **300 mutants** of the six fixtures, a fixed seed | no sanitizer report and no abnormal exit from the ones that still sniff as a package — 270 of 300 do |

**Lane 3**: a SqueezePlay fork is a Unix `compress` stream (13 bits, block
mode), so `1f 9d 8d` in front makes a `.Z` file; gzip reads all 59 real and 18
synthesised LZW forks byte-identically, so the codec's oracle — **clear code** and **13-bit
width** included — is somebody else's program (FORMATS.md, *What is graded
by what, and what is not*).

**Lane 1 can fail** (measured 2026-10-06): one byte flipped in `Read
First.PKG`'s stream gives four complaints (one byte long against its
record, the entry refused, the member missing, gzip disagreeing).

**Lane 4**: the sniffer tests a version byte, eight zero bytes, two item
counts, every record's name length and level, and that the forks tile the
file; each is bent in turn. **Ten** of the bends, the file of zeros and the
empty-member package are also in `tests/unit_formats.c` (`test_sqp`), under
the sanitizers on every pass. The four non-package inputs exist because a
bend can only ask whether a test FIRES, never find a missing one
(DECISIONS.md 2026-10-06, *the directory of empty records*); both cases
failed on the build of the day before, and `sum > 0` passes the first pair
and fails the second.

**Lane 5** exists because `tools/fuzz.py` cannot reach this decoder: at 400
cases `unc_sqp_extract` and `sqp_fork` were at **zero lines** while
`unc_sqp_probe` reached **83.9 %**. The 270 is what says it tests the WALK.

**Six fixtures, in the differential suite too**:
`synth-sqp-{plain,forks,stored,clear,v0,folder}.pkg`, `synthetic:` in
`fixtures/SOURCES.md`, manifests whose `oracle` names the generator (so
`make_manifests.py` leaves them alone). `run_diff.py` grades them (**22
forks, 17 Finder-flag rows**), `run_robustness.sh` and `run_truncation.py`
cover them, and `synth-sqp-forks.pkg` runs through its `'OVLY'` image in
`tests/run_overlay_host.sh`.

**On a Macintosh** (not in `ci.sh`, not in `sample.txt`): **all fourteen
packages** through `tools/vmac/run.py` at the 1 MB floor, plus 3/3 on
System 3.0 with `sys30.py`; the real ones need `--expect` (no committed
manifest), which `sys30.py` cannot take (FORMATS.md, *Run on a Macintosh*).
Re-run from `tools/vmac/README.md`.

**What this cannot see.**

- **Whether Aladdin's expander would read what the generator writes.** The
  paths no real package reaches (resource fork, stored mode, version 0,
  folders) are graded against a generator from the same reading as the
  decoder — and a shared mistake did happen (a folder's type and creator
  are its window rectangle). **No package written here has ever been
  handed to Aladdin's own expander** (OPEN_ITEMS.md).
- **A subtly wrong CONTAINER reading**: what says a fork decoded is that its
  stream ended exactly at the declared length and the directory tiled the
  file; beyond that, `gzip` on the codec and the real members reading as
  coherent text. (`derive_sqp.py` asserts the stream's natural end, not a
  ceiling it was given: a flipped byte reports 1,960 against 1,954 —
  DECISIONS.md 2026-10-05, *the sample that was read as the table*.)
- **Lane 4's files of zeros are two of a family** (`10 + 86n` for version
  0; four planted bytes for version 1); that the rest are refused is an
  argument from the probe's source, not a measurement.
- **No real package has a member with BOTH forks empty** — 39 files and 14
  folders across all 8, 17 declaring one fork of length zero and none
  two (measured 2026-10-06). That such a package is writable is a
  **hypothesis**, and the lane's two positive controls rest on it; if
  disproved, `sum > 0` becomes the narrower test at 2 B more.
- **The old probe's pin stays**: `test_applelink` asserts five translator
  COMMAND lines name nothing (BLOCKERS.md, the "0 of 928 fixtures said
  AppleLink" sweep); with six packages in the corpus that sweep can now
  fail both ways.

**Twenty-nine witnesses** (`derive_sqp.py --witness`) are byte patterns in
`'Othe' 1` of the translator, each checked AT its claimed offset: the
86-byte SQP record, the 4+86 of an HFS one, the HFS directory at 86 ×
count + 22, the version test, the folder level, the 9-bit start, the 257th
first code, the 256 clear code, the 8192 ceiling, the two fork lengths,
both stored bits and the 50-item cap. `tools/vmac/README.md` (*The
AppleLink package expander*) rebuilds the resource from the 3.0.7
installer, which is not committed; `--witness` skips cleanly without it.

## Archives this engine does not have (`tools/run_foreign.py`, in `ci.sh`)

**A negative test** (DECISIONS.md 2026-10-18, *the formats it only
named*): such a file is not an archive.

```sh
python3 tools/run_foreign.py --macextract build/macextract
```

**The contract, per specimen:** `sniff` prints `unknown`, and `x` exits
non-zero, says *"format not recognized"* and leaves its output directory
empty. **The specimens must be real first**: bzip2, xz, 7z, WIM, cpio (three
header shapes) and ar are written by their own tools and must be **opened by
p7zip**; four Apple Archives are written and read back by libNeoAppleArchive
(`tools/build_neoaa.sh`, `tools/neoaa_write.c`); StuffIt X, RAR 1.3, 1.5–4
and 5, Cabinet, Zoo, ARJ and lzip are hand-built headers that **deark** must
identify as that format, or the case fails. Zstandard (a frame and two
skippable frames) and lrzip rest on their published magics alone.
`tests/unit_formats.c`'s `test_foreign` asks the same of every magic the old
probes accepted, in a buffer of zeros and one of 0xFF, without tools.

**The corpus is swept**: every fixture with a manifest must sniff as its
oracle's format (`run_diff.py`'s `IMPLEMENTED`), every other fixture as
something, and `synth-os9-rar.rar` (the Mac OS 9 tier's refusal sample)
must meet the specimens' contract.

**It can fail, measured 2026-10-18**: `origin/main`'s CLI, which still
named them, fails 52 of 97 checks (all 26 specimens); a probe claiming
`MSCF` as a zip with no LZH probe fails 3.

**What this cannot see.** A reader that claims a real archive of one of
these families whose head differs from every specimen — a self-extracting
`.exe`, a RAR with a comment block first, a multi-volume part, a shape only
Apple's `aa` writes. Zoo, ARJ, Cabinet, RAR, StuffIt X and lzip are
headers deark identifies, not files an archiver wrote. On the Macintosh,
only the Mac OS 9 tier's single RAR (`tools/vmac/README.md`,
*Photographing the refusal alert*).

## StuffIt SpaceSaver (`tools/run_spacesaver.py`, in `ci.sh`)

SpaceSaver has no oracle but itself (`unar` and `macunpack` do not know
it). **48 specimens**, downloaded: files SpaceSaver compressed on the
machines that mastered Apple Developer, MacTech, Apprentice, Info-Mac and
HyperLib CD-ROMs, **46 of them with the uncompressed original** from an
earlier pressing; both header versions, methods 0, 1, 2, 3 and 4, all 46
pairs byte-exact (DECISIONS.md 2026-09-26, *the magic in somebody else's
index*).

    tools/fetch_specimens.py --only spacesaver

fetches them (table: `tools/specimens/spacesaver.tsv`) and checks every
sha256; they live outside the repository:

    ~/.cache/macextract/vmac/specimens/spacesaver/NAME.ss        the file
    ~/.cache/macextract/vmac/specimens/spacesaver/NAME.ss.orig   its input
    ~/.cache/macextract/vmac/specimens/spacesaver/PrAm-4048.bin  the preset

`--layout` writes the preset out of the installed control panel;
`tools/vmac/spacesaver.py --idlespec` would make a pair on the Macintosh
and never has (BLOCKERS.md). **With none present the suite prints what it
skipped and returns 0.** A specimen without an `.orig` is decoded and
required to succeed (the CLI keeps the whole basename; SpaceSaver adds no
extension).

**The synthetic pass**: an Alg 4 ENCODER written from the same disassembly
round-trips 200,000 bytes through a wrapping window and a dozen blocks, the
widest window, and a preset-dictionary start — a consistency check, not an
oracle. **Aladdin's own encoder** (`CMod 20`'s compressor, a different
routine in a different module) **agrees field for field** on the reading
(DECISIONS.md 2026-08-23, the encoder agrees).

**The dictionary is checked for drift**: `src/ss_dict.h` is generated by
`tools/gen_ss_dict.py` from the `PrAm` resources AND committed, so whenever
the resource is present the suite compares the two byte for byte (it fails
on one byte changed). The unit tests carry the table contract: built-in
when none is supplied, a caller's overrides it, the byte at +12 selects
between the two built-ins, an unknown table is refused.

**58 corrupted variants per specimen** (ten truncations, forty-eight
bit-flips), FORCED with `-f "StuffIt SpaceSaver"`, because no SpaceSaver
file is in `fixtures/`; `fuzz.py` also carries the header's magic.

**The Macintosh side is three files**: `tools/run_spacesaver.py --emit DIR`
writes them and `tools/vmac/run.py --expect DIR/*.ss` replays them (stored,
method 4 without a dictionary, method 4 with one) against this engine's
Linux output — same bytes on a 68000, not proof either is right. 3/3 at
4 MB and 3/3 at the 1 MB floor (2026-08-22; FORMATS.md).

**What this cannot see.** **No resource fork is graded** (the originals come
from ISO 9660 pressings; the decoded fork is only checked as a valid
resource map of the declared length). **Method 4 is not graded either** —
its two specimens have no published original and are only required to
decode. Methods 1, 2 and 3 are also graded against the modules that write
them (*SpaceSaver's own codecs*, above). The unit tests carry the per-ENTRY
refusal (method 5, which no SpaceSaver wrote) and a resource fork whose
stream precedes the data fork's.

## PKZIP's own distributions (`tools/specimens/implode.tsv`, one of three in `ci.sh`)

Three self-extractors, fetched and hash-checked like every other specimen
set:

    tools/fetch_specimens.py --only implode
    tools/fetch_specimens.py --only implode --check

    ~/.cache/macextract/vmac/specimens/implode/

**`PKZ101.EXE` is the fixture `pkz101.exe`**, so `run_diff.py` grades all
thirteen of its entries on every `ci.sh` run — including the three that
need PKZIP 1.01's minimum match length, the only file here that carries
that rule (FORMATS.md, *The fixture that carries the bug*; DECISIONS.md
2026-10-08, *the second attempt that had nowhere to go*). Its manifest
needs **deark told `-m zip`** (`make_manifests.py`'s `DEARK_MODULE`, its
only entry, deliberately not a fallback) and **`IMPLEMENTED`'s
`"Self-extracting Zip": "Zip"`** (`lsar` names the stub).

`PKZ102.EXE` and `PKZ110.EXE` stay specimens, as negative controls: 1.02
writes no bug-capable entry and 1.10 is where *version made by* turns from
ZIP spec 1.0 into 1.1 (DECISIONS.md 2026-10-08, *the stub is the writer's
signature*).

**What this set cannot see:** nothing in `ci.sh` reads the two specimens;
`tools/scan_discmaster.py --probe implode` grades them against their stored
CRC-32, by hand.

**Their programs, run (`tools/pkzip_writers.py`, by hand):**

    tools/pak.py --setup                    # DOSBox, no root
    tools/fetch_specimens.py --only implode
    tools/pkzip_writers.py --macextract build/rel/macextract

It runs `PKZIP.EXE` and `PKUNZIP.EXE` from all three distributions headless
under DOSBox (about 20 s) and **exits 1 if any answer differs from the one
DECISIONS.md records** (`FAILS`, and the stamps and counts in steps 1–2); a
log holding neither *OK* nor *fails CRC* fails too. Four checks:

1. the Implode combinations each writer chooses over 51 inputs, its matches
   at distance operand 0, and its literal trees equal to
   `synth_implode.PKZIP_LITERAL_TREE`;
2. every record's *version made by* after one version updates another's
   archive (`-a`, `-u`, `-f`, both directions, and `PKZ101.EXE` itself);
3. what each PKUNZIP makes of `PKZ101.EXE`, of 1.10's output, and of the six
   generated shapes — so **PKUNZIP 1.01 and 1.02 grade both `-mmlbug`
   shapes**, with 1.10 the negative control;
4. what each PKUNZIP makes of the minimal cases it reads differently from
   APPNOTE 5.3, each beside a control.

Positive control: `PKZ101.EXE`'s three bug entries print `DISAGREE`.
**What it cannot see:** writers other than these three binaries
(including whatever wrote `PKZ101.EXE`'s entries); step 3 reports a CRC
per archive, not which token failed, and grades the minimum match length
only because step 4's features are absent from the generator's streams —
asserted by `synth_implode.py --selftest` on every `ci.sh` run. Those
features stay under test in the ENGINE through `QUIRKSHAPES`' one shape in
`run_implode.py`. A generator change is not graded by a PKUNZIP until this
is run. Results: DECISIONS.md 2026-10-08, *the key that survives and has
nothing to separate*, and 2026-10-09, *the run PKZIP never codes at
distance one*.

## ZipIt's own archives (`tools/run_zipit.py`, in `ci.sh`)

**Nine archives ZipIt itself wrote** grade its three Macintosh extra fields
(DECISIONS.md 2026-10-04, *the archive that carried its own extractor*;
figures in FORMATS.md, *ZipIt's own archives*).

    tools/fetch_specimens.py --only zipit
    python3 tools/run_zipit.py --macextract build/macextract

    ~/.cache/macextract/vmac/specimens/zipit/

(`tools/specimens/zipit.tsv` is the table.) Four were found by
`tools/scan_discmaster_zips.py`, which reads 512 bytes of every zip on the
named Discmaster items over HTTP `Range`; not in `ci.sh` (network, URLs not
a verdict), resumable via `--state`:

    tools/scan_discmaster_zips.py \
        --items-from tools/specimens/spacesaver.tsv \
        --items-from tools/specimens/applelink.tsv

is the 2026-10-04 run: **3,029 zips, seven hits**.

**Two of the nine are also corpus fixtures** (`MrTs_Paint_Folder.zip`:
`0x2705`, `0x2805`; `NPWritersKit.zip`: a `0x2605` entry, 150,016 B data and
323 B resource fork), graded by `run_diff.py` with no oracle at run time;
this suite checks the fields a manifest does not record.

Six checks, the last over the corpus zips as well:

1. **The format, read independently**: every field parsed in Python; the
   central copy equals the local one; each size is what `'ZPIT'` plus its
   members needs.
2. **`0x2605` against the bytes**: the entry's first 128 bytes probed as
   MacBinary (the `zip_mb_peek` test), both directions.
3. **`l --finder` against `lsar`**: name, type, creator, Finder flags, both
   fork lengths.
4. **`x` against `unar`**: every fork byte for byte, `unar`'s AppleDouble
   sidecar unwrapped.
5. **`x` on the whole file against `x` on its data fork**, for the four
   that arrived MacBinary-wrapped (a ZipIt `.sea` is a PEF container with
   the zip behind it).
6. **The name coupling**: **every `0x2605` FileName, divergent or not, must
   be the leaf this engine LISTS the entry under** (`src/fmt_exo.c`
   substitutes it). One `l` per archive carrying a field; a wrapped
   specimen is listed through its data fork. **23 fields, 3 divergent, 23
   names held against the listing**, counts printed. `selftest_coupling`
   runs five one-entry zips (from `tools/synth_crypt.py`'s writer) against
   the real binary, which must pass, and against a stub answering with the
   zip's own leaf, which must fail on the 3 differing cases (DECISIONS.md
   2026-10-06, *the gate that had never fired*).

**Per-specimen tallies are asserted** (`EXPECT`: entries, a count per field
id, MacBinary payloads), so a parse that stopped parsing cannot pass with
zeros (CLAUDE.md, *A test that passes may not be testing anything*):
rewriting every `0x2605` id to `0x2805` in one specimen gives 4 failures,
moving the `0x2705` flag read by two bytes in `src/fmt_exo.c` gives 66.

**What it cannot see.**

- **The probe's own reasoning.** All nine are *required* to sniff as `Zip`
  with nothing forced, but all carry a well-formed end-of-central-directory
  record, so a corroboration that stopped corroborating cannot fail here;
  `test_zip_behind_a_stub` in `tests/unit_formats.c` bends each of the five
  tests (FORMATS.md, *What the zip pair claims, and what it costs*).
- **No fork of an entry whose method is out of scope** — `UNGRADED` names
  every one with the reason, and **is EMPTY since 2026-10-07** (the fork
  tally is **119 of 119**). The declaration carries the NUMBER, so a
  refusal anywhere fails.
- **No date**: `lsar`'s MS-DOS stamp and the MacBinary header's Macintosh
  dates are different fields.
- **ONE name `unar` spells differently**, allowed only while ZipIt's own
  `0x2605` FileName is one of the two spellings: ZipIt 2.2.2's `Drop files
  here to zip (OS X)`, where XADMaster takes the MacBinary HEADER's name
  (DECISIONS.md 2026-10-05, *a leaf is not a path, and a version is not a
  preference*).
- **Check 6 reads `fixtures/*.zip` and the nine specimens only**; a ZipIt
  archive inside a `.hqx` or `.sea` is not seen. The number swept is
  printed.

## Private File (`tools/run_privatefile.py`, in `ci.sh`)

Nothing else reads a Private File, so **the writer is the grader**: files
Aladdin Private File 2.0's `PF Encrypt™` encrypted under Mini vMac from
subjects whose bytes and passwords are fixed in `tools/vmac/privatefile.py`
(FORMATS.md, *Private File*).

    tools/vmac/privatefile.py --make NAME        an emulator run, ~6 min
    python3 tools/run_privatefile.py --macextract build/macextract

    ~/.cache/macextract/vmac/specimens/privatefile/NAME/SUBJECT.pf.bin

1. **Every specimen, graded**: `x -p` through every layer (MacBinary,
   Private File, then the StuffIt archive PF Encrypt makes first), both
   forks against the subject; the file unwrapped once by hand must refuse
   a wrong password and list under its record's name.
2. **Refusals**, from `tools/synth_pf.py` (this project's reading, used for
   nothing else): a wrong password and none (*wrong password*), a flipped
   data byte (*checksum mismatch*), a header naming a derivation nothing
   writes (*encrypted by a scheme we cannot read*), a file one byte short
   (not claimed). A positive control runs first.

**Made to fail**: the key length forced to 16 fails all three specimens and
both decrypting synthetic cases.

**What it cannot see**: a 16-byte key (the one writer here is the export
build, which keys with five), and derivations or ciphers other than MD5 and
RC4. With no specimens it says so and runs the refusals alone; **a partial
set fails**, and so does a specimen with no subject.

**The Macintosh side is `tools/vmac/interactive.py --privatefile`**, not in
`ci.sh`: the shipped application extracts the `Forked` specimen on System
6.0.8, answering its password dialog wrongly once, and both forks are read
back off the volume.

## MacGzip's own output (`tools/run_macgzip.py`, in `ci.sh`)

Eleven files **MacGzip 1.1.3 68K** wrote on emulated Mac OS 8.1 from one
two-fork subject (TEXT/ttxt, 292 + 391 B): MacBinary mode at levels 1–9,
Binary mode and ASCII mode (the docstring has how they were made).

    python3 tools/run_macgzip.py --macextract build/macextract

    ~/.cache/macextract/vmac/specimens/macgzip/{lvl1..9,binary,ascii}.gz
    ~/.cache/macextract/vmac/specimens/macgzip/source-A_Document.macbinary.bin

Each must sniff as Gzip and extract to: both forks under the subject's
MacBinary name (MacBinary mode, two envelopes deep); its data fork
(Binary); its data fork with CR→LF (ASCII). The subject's forks are read by
the script from the MacBinary II header, not by the engine; the MacBinary
layer taken off with `-nr` must list the subject's type, creator and fork
lengths.

**Made to fail** (measured 2026-10-14): a flipped deflate byte (1 failed),
one resource byte changed in the subject (9 failed), a missing specimen
(*incomplete*), a CLI forced to `-nr` (9 failed).

**What it cannot see**: stored deflate blocks (MacGzip cannot write one),
any other MacGzip, the gzip header's name (ignored, as `unar` does), and the
Macintosh host. With no specimen directory it skips and returns 0; a
partial set fails.

## Short reads (`tools/run_shortread.py`, in `ci.sh`)

`UncIO` lets a read return fewer bytes than asked before EOF, and neither
host here ever does. The CLI's `UNC_SHORT_READ=<n>` caps every read at n
bytes and says so on stderr; this extracts every present fixture capped at
**1 B** and uncapped and requires the same exit status, messages, names and
bytes, then runs `run_crypt.py` and `run_privatefile.py` whole under the
cap.

    python3 tools/run_shortread.py --macextract build/macextract [--cap 1]

It found Private File's bare footer `io->read` (DECISIONS.md 2026-10-09,
*the read nothing sent short*). **Made to fail**, three ways: that fix
reverted, `unc_read_full` bent to give up on a short read (953 of 959
fixtures failed, 2026-10-09), and a binary built before the hook (refused:
the CLI's announcement is what tells a binary that honours the cap from one
that ignores it). 971 fixtures at 1 B, 3 and 7 all agreed with uncapped on
the fixed build.

**What it cannot see**: a decoder right under any cap and slow under a
small one, and the Macintosh host, which never honours the variable.
## Searching somebody else's index by content (`tools/scan_discmaster.py`, not in `ci.sh`)

Not in `ci.sh`: it needs the network, and it produces URLs rather than a
verdict. It is here so a sweep can be re-run and widened
(`tools/scan_discmaster_zips.py` is the narrower zip sweep).

**Two content indexes.** Discmaster's `detection=` field is full-text over
what each identifier printed AND — per its `searchHelp.html` — over the
**first 16 bytes of every file**, as ASCII or hex, with `*` at either end and
`?` for any single character. The other is an HTTP `Range` request on the
file itself.

    # a version-1 AppleLink package IS a hex token: ?? 01 and 14 zeros
    tools/scan_discmaster.py --probe pkg \
        --query 'detection=01010000000000000000000000000000&dedup=dedup'
    tools/scan_discmaster.py --probe pkg \
        --query 'extension=.pkg&family=unknown&dedup=dedup'

The probes are written from this project's own reading of each format and
checked against the corpus before being pointed at a stranger's disk:

| probe | what it accepts | established before the sweep |
|---|---|---|
| `pkg` | an AppleLink package: item count, version, eight zero bytes, then the whole directory validated against the file's size and tiling | **exactly the 6 synthesised `.pkg` fixtures out of 956 files in `fixtures/`**, and both real packages — fails in both directions |
| `sit` | a classic StuffIt archive, reported when a fork's method byte carries the Optimizer bit `0x40`, the encrypted bit `0x80` or the `NewDE` bit `0x10`, NAMING the module (Optimizer id at 106/108, Encryptor id at 107/109, read only for a fork that carries the flag and has a length). A walk records WHY it stopped; `--resync` searches the unread bytes for a header whose own CRC checks | the **340** `rLau` archives out of 1,915 files in `fixtures/`, **1,710 file headers**, of which it flags exactly **4** (the two wild optimized archives in both forms); over StuffIt Deluxe 2.0.1's specimens it names all five ciphers and all five Optimizer ids, each on the right archive |
| `dd` | a DiskDoubler compressed file, with both forks' methods and lengths | the 67 DiskDoubler headers in `fixtures/`, reproducing FORMATS.md's *the biggest method-8 fork in reach is 44,549 B and compresses to 1,230* |
| `implode` | a zip's Implode entries, each decoded BOTH ways (5.3.4's minimum match length and 1.01/1.02's) and graded by the stored CRC-32; reported only when an entry needs the 1.01/1.02 rule. Wants the whole file; the decoder is `tools/synth_implode.py`'s. Reads a zip BEHIND CODE (`zip_start()`); `--vermade` filters by the central directory's writer version over two `Range`s first (`central_vermade()`), `--host` adds the host byte; every decoded archive records the local headers it walked | the 10 wild Implode entries on this disk: **7 where the two rules COINCIDE** (CRC-OK either way), and the 3 bug-capable ones in the ZipIt specimen (CRC-OK under 5.3.4 only); the three `tools/specimens/implode.tsv` self-extractors: **3 flagged in `PKZ101.EXE` and 0 in `PKZ102.EXE` and `PKZ110.EXE`**; `central_vermade()` checked against those files' own directories |
| `pit` | a PackIt archive walked to the end of its block chain, reported only when a block is `PMa5` or `PMa6`. Wants the WHOLE file (a `PMa4` block can only be stepped over by decoding it, with `tools/derive_packit.py`'s decoder) | **exactly the 5 PackIt archives out of 962 files in `fixtures/`**, each walking to `PEnd`, and all 3 encrypted specimens in `specimens/pitcrypt/`, each stopping at its encrypted block |

**The sweeps that have been run, by key:**

| date | key | listed | hits |
|---|---|---|---|
| 2026-10-06 | `detection=<n>01` + 14 zero bytes, n = 1…50 except 7, deduplicated | 1,443 | **36** AppleLink packages |
| 2026-10-06 | `extension=.pkg&family=unknown`, deduplicated | 2,641 | 13 more, **49** in all, 7 of them version 0 |
| 2026-10-06 | `detection=abcd0054*&sizeMin=40000`, deduplicated | 2,046 | all DiskDoubler compressed files, **612 method-8 forks** up to 6,212,378 B of coder output; two became fixtures (FORMATS.md, *Method 8's Huffman block*) |
| 2026-10-07 | `format=sit` AND `format=sea`, deduplicated, **sharded by size under the result window** (`--shard-under`) | **196,139** | from `meta.fileMeta`: **21** hold an `8BIM` member, **521** an `FSSD`, **423** a `PNTG`; **10,452** carry no member metadata |
| 2026-10-07 | those **954** archives, walked over window `Range`s (`--bytes 32768 --walk 400`) | 954 | **927** classic StuffIt archives, **16,413 file headers**, 4,283 folder markers; **`Sound 1` and `MacPaint 1`** Optimizer bits, one archive each, both now fixtures (FORMATS.md, *Two more, and these the engine UNDOES*); **0** encrypted forks |
| 2026-10-09 | the **10,452** with NO member metadata (`--no-meta`), walked to the end (`--bytes 32768 --walk 100000`) | 10,452 | **6,432** classic StuffIt archives, **166,970 file headers**, 101,443 folder markers; **112 walks stop short** (next row). **0 `Photoshop 1` or `JPEG Lossy` bits, 0 `NewDE`, `DES`, `DESex` or `PassLock` forks**; 2 `Text 1` bits; 6,911 encrypted forks in 143 archives, **2 read as `NewDEx` and 2 as id 5**, all in one InstallerMaker 1.0.3 updater (FORMATS.md, *Where an archive names the module*). Controls: 2.0.1's specimens; the 911 previously walked archives reproduce |
| 2026-10-10 | those **112** again (`--keys`, `--resync`; `hcrc_ok()` is `src/fmt_sit.c`'s per-entry test) | 112 | **88 at a header `plausible()` rejects, 24 past the FILE's own end** (38 MB declared beyond what the index holds); of the 88, **61 resume and land on the declared end exactly**, 2 run off a truncated file, 25 never resume. **12,255 CRC-valid headers in the unread bytes, 0 carrying the Optimizer, encrypted or `NewDE` bit** (2,571 "flagged" without the CRC test — compressed data). Controls: all **2,835** headers in `fixtures/` and 2.0.1's specimens pass the CRC test; a spliced-junk case recovers; it reproduces the 2026-10-09 readings. States under `~/.cache/macextract/discmaster/rewalk/` |
| 2026-10-06 | `format=sit`, deduplicated, ordered by hash — a uniform sample | 10,000 | 8,798 classic StuffIt archives, **8,746 entry headers**, **0 Optimizer bits** |
| 2026-10-06 | the same, `tsMax=19921231`, at `--bytes 8192` | 8,000 | 7,929 archives, **12,987 entry headers**, **5 Optimizer bits** in 3 archives, all `Text 1`, two now fixtures (FORMATS.md, *Two optimized archives nobody here made*); with the in-step tests the pair's 21,767 headers became **21,733** |
| 2026-10-06 | `detection=626567696e2030*`, `...2036*`, `...2037*` — a uuencode `begin` line, then each candidate's TAIL read for ` .finfo` | 939 | **1** UUTool MU-layout posting, `uu-wild-dictcol.uu`, now a fixture (a second, `uu-wild-terrainman.uu`, came off the same key by eye) |
| 2026-10-07 | `detection=504b0304????02000600*` and `...04000600*` — a zip whose FIRST local header is Implode at a disagreeing combination | **800** probed of 8,943 named (of 1,125,083 zips whose first entry is method 6, and 6,805,790 zips) | **19,107 bug-capable Implode entries: 19,105 follow APPNOTE.TXT 5.3.4, 0 need the 1.01/1.02 rule, 2 decode under neither** (a truncated `synchro.zip`) (FORMATS.md, *Implode*) |
| 2026-10-08 | `detection=4d5a98001f000b002000c10affff0a0e*` — **the PKSFX 1.01/1.02 stub's own DOS EXE header** | **1,323** probed of 5,576 named | **12 bug-capable entries, every one written by the bug**, in the 4 copies of `PKZ101.EXE` (FORMATS.md, *The specimen that carries the bug*) |
| 2026-10-08 | the two flag tokens, deduplicated to 3,821, every central directory read (`--vermade 10`), spec-1.0 writers fetched whole | 3,821 read, **1,537** decoded | **29,799 bug-capable entries: 29,795 by 5.3.4, 0 by the bug, 4 by neither**; only **10 of 3,821** say MS-DOS + spec 1.0 (FORMATS.md, *Implode*) |
| 2026-10-08 | the same tokens with `tsMin=1989&tsMax=1990` | 975 | **3,543 bug-capable entries, 3,543 by 5.3.4, 0 by the bug.** A date is not a writer |
| 2026-10-08 | `detection=504b0304????????MM00*` for MM = 01…05 (Shrink, Reduce 1–4), listed with `size_shards` and classified by `idMeta` and path | **109,207** (96,193 Shrink; 117 / 143 / 43 / 12,711 Reduce 1–4) | **146 distinct in a Macintosh context, 1 written on one** (`BBA.zip`, now a fixture); 2,246 entries decoded, all CRC-correct under deark, 270 failed by `unar` (FORMATS.md, *Shrink*). Kept under `~/.cache/macextract/discmaster/shrink/2026-10-08/` |
| 2026-10-09 | the same five keys THROUGH `scan_discmaster.py`: `--probe keep --mac-context --dedup`, and `--probe keep --dedup --max-size 409600 --exclude-state mac.json --sample 200 --seed 20261009`. **`--probe keep` writes each file under `--keep-dir` by SHA-256**; `manifest.tsv` joins the two states | **109,046** listed; 146 + 200 kept | `mac_context()` reproduces the census — **141 Shrink, 5 Reduce** — with the disc's NAME dropped as a key; 1,965 Shrink entries graded both ways (FORMATS.md, *Shrink*, *What grades it*) |
| 2026-10-09 | `detection=504b03040a00????MM00??????YY*`, MM = 06, 00, 01 and YY = 12, 13 (version needed 1.0, a 1989 DOS date), then `--vermade 10 --host 0` — PKZIP 1.0x's own output, which the flag tokens excluded (**8,462 of 22,063 directories say MS-DOS/1.0**) | **22,063**, every directory read | **8,452 archives decoded, 99,951 local headers walked, 68,855 Implode entries — every one at 0x0000 or 0x0006, 0 bug-capable** |
| 2026-10-09 | the same key with YY = 10, 11 (1988) | **26,885** | **10,826 archives decoded, 124,380 local headers, 83,069 Implode entries, 0 bug-capable.** Together: **151,924 Implode entries in 19,278 MS-DOS/1.0 archives, none at 0x0002 or 0x0004.** YY = 14, 15 (1990) is not run |
| 2026-10-09 | by NAME, `q=pkz100`, `q=pkz101`, `q=pkz090` | 16 | the four `PKZ101.EXE` copies again, and **PKZIP 1.01 for OS/2 (`PKZ101_2.ZIP` ×5, `PKZ101-S.EXE`), written at 0x0000 and 0x0006 only** (DECISIONS.md 2026-10-09, *the writer's own output was the population the flags excluded*); and `pkz100.txt` (1989-05-29) quoting *"PKZIP 1.0 Alpha"* |
| 2026-10-05 | `detection=504d6135*` and `504d6136*` — an archive that BEGINS with an encrypted block | 0 | **0**, which is why the chain has to be walked |
| 2026-10-05 | `detection=504d61*` — first bytes `PMa`, complete | 2,573 | **182** PackIt archives, 1,107 blocks (696 `PMa4`, 411 `PMag`), **0 encrypted** |
| 2026-10-05 | `extension=.pit`, 3,324 of 22,558 probed (resumable) | 22,558 | 6 more archives, 27 blocks, **0 encrypted** |
| 2026-10-11 | `detection=504b0304????????MM00*` for MM = 02, 03, 04, `--probe keep --dedup` into `~/.cache/macextract/discmaster/reduce/files`; MM = 05 with `--dedup --max-size 400000 --sample 150 --seed 20261011` into `files5` | 117 / 143 / 42 / 12,603 listed; 105 + 92 + 13 + 150 kept | **2,379 Reduce entries**, graded against the stored CRC-32 (FORMATS.md, *Reduce*) |

**Controls the sweeps earned:**

- **A suffix `Range` is not honoured here, and it answers `206`**:
  `bytes=-2048` returns 2,049 bytes **of the head**, so the first uu pass
  over 939 files reported 0. Use `bytes=<size-2048>-<size-1>`, and before
  any probe reads anything but the head, fetch a tail whose last bytes are
  known and compare.
- **A window `Range` is honoured** (0..511 then 256..511 must agree), so a
  walk costs 112 bytes per entry — 16,413 headers out of 954 archives,
  against 924 for a prefix-fetching walk.
- **The probe must be shown to have RUN**: the stub key's first run decoded
  nothing (30 bytes of an `MZ` file contain no local header, so "not a
  zip" 1,323 times).
- **Three tests keep a `sit` walk IN STEP**, each measured against the 1,710
  known-good headers in `fixtures/` with 0 false positives: name length
  1..31, no NUL in the name, entry and forks inside the declared total. The
  obvious fourth (no control byte) rejects 44 real headers and was dropped.
  The three reject exactly the known-bogus walks (two `cursors.sit` copies,
  the 2026-10-06 false `NewDE` bit, `SternSounds3.sit`'s 3.1 GB fork).
- **The flag bits are this repository's measurement, not the published
  table's**: `0x10` is `NewDE` (measured 2026-10-02), the encrypted bit is
  `0x80` (`src/fmt_sit.c`); an id byte belongs to a fork, read only where
  that fork carries the flag and has a length, and the method BIT beats a
  stale id (2.0.1's `NewdeT.sit.bin`).
- **`--bytes` costs nothing**: the `sit` probe walks the chain inside the
  bytes already fetched, so 8 KB reads several entries for one request
  (first-entry-only: 8,798 archives, 0 hits; 8 KB: 12,998 headers in 7,929
  archives, 7).

**The member-type key** (`meta.fileMeta`): **Discmaster does not index
inside a `.sit`** (`detection=PNTG/MPNT` returns no `fileid` with `.sit/`,
measured 2026-10-07), but the listing reports each archive's member types
free. An Optimizer accepts exactly one type out of its own `COMP` — `FSSD`
for `Sound 1`, `8BIM` for `Photoshop 1` and `JPEG Lossy`, `PNTG` for
`MacPaint 1`, `TEXT` for `Text 1` (FORMATS.md, *The module ABI*) — so 954
of 196,139 archives were worth a request. Positive control: all three wild
`Text 1` archives contain a `TEXT` member. `format=sea` (17,798) and
`format=sit` (175,810) are both in the 196,139, and **those three figures
are not meant to add up** (`dedup` is per query; 48,824 rows share a name
and size with another).

**Both AppleLink keys were needed**: the hex token cannot see version 0
(all 7 version-0 packages came from the extension key), and **20 of the
49** are not called `.pkg`. `n = 7` is excluded because `0701` + zeros is
612,514 files.

**The listings are kept** in `~/.cache/macextract/discmaster/` (60 MB;
re-listing the StuffIt corpus is about 25 minutes); `--state` points there
and the tool resumes.

**What it cannot see.**

- **The Implode sweep**: a bug-capable entry that is not the FIRST in its
  archive (a `format=zip` sweep would reach those and is not done; the
  2026-10-09 keys reach them only behind a version-1.0 first header with a
  1988 or 1989 date).
- **The PackIt sweep**: a MacBinary-wrapped archive (`packit.pit_.bin`
  itself); the `.pit` extension sweep is the other way in (6 in 3,324).
- **The member-type key**: archives whose members the index did not record
  (**10,452 of 196,139, 5.3 %**, swept by `--no-meta`), and an Optimizer
  over a file whose type the index read differently.
- **The tool**: a file whose first 16 bytes the index did not record — why
  every `detection=` sweep is paired with one reached another way — and
  anything past Elasticsearch's result window, which `sizeMin`/`sizeMax`
  shards around.

## Segmented archives (`tools/run_segments.py`, in `ci.sh`)

When this suite was written no segmented archive was in the corpus
(re-measured 2026-08-15 over all 805 fixtures; the `B0 56 00` search was
for the wrong bytes — BLOCKERS.md, *Withdrawn claims*, 2026-10-24); the
three DiskDoubler `SPLT` sets have since been registered as fixtures (*DiskDoubler
`SPLT`*, below). So the StuffIt sets are generated by
`tools/synth_sitsplit.py` into a temp directory per run, each case
required to agree three ways: the generator, `unar`, and our CLI.

Seven cases: three parts with cuts inside both forks, a set of one, a cut
exactly on the fork boundary, data-only, resource-only, twelve parts (one
carrying no payload), and a set whose filenames contradict the part order
with a name-alike intruder beside it. Plus behaviours: opening a part other
than the first, a missing part, `--ask` accepting and refusing files,
`--no-parts`, and the part-open counters.

**Twelve real sets** (`REAL_SITSEG`), which `unar` refuses, in
`$UNC_VMAC_HOME/specimens/sitseg-real/` (skipped loudly where missing):
seven StuffIt cut (Deluxe 2.0.1 at 75K with every part typed `SegM`, Lite
3.0.5 at 24K and 8K, Deluxe 5.0 at 24K and by Save As onto two floppies,
DropSegment 5.0's self-extracting set, an InstallerMaker 2.0 installer);
Now Utilities 6.0's two installer disks (1996), a fat installer whose
`.rsrc` carries the `'endD'` that says where the segment stops; and four
from `tools/vmac/sitopt.py --segment small` and `big` over files WITH a
resource fork (DECISIONS.md, *the two bytes the writer drew*). Each is
graded by the SHA-256 of what it must join to and by its running
CRC-16/ARC at 96, part by part.

**Shown to fail**: the binary before the fix refuses the seven and joins the
eighth wrong; a set with a `.rsrc` beside a part, run without it, must fail;
the fat set inside a MacBinary-then-BinHex envelope opened through part 2
(DECISIONS.md, *the fork the peel dropped*); `basic3`'s part 2 with a payload
byte or a stored-CRC byte flipped must fail as a *checksum mismatch* after
two part opens (DECISIONS.md, *the sum each part carries*); and with a bit of
the header's own CRC at 94 flipped, or a byte it alone covers, part 2 must
be refused as missing and part 1 must sniff as *unknown* (DECISIONS.md, *the
check the header carries*). The application's reading of `'endD'` is
`segcheck.py --case sit-fat`'s, on an emulator (`tools/vmac/README.md`).

**What they cannot see**: any writer other than these, and a part read
under `--no-parts`, which no joiner holds to its CRC.

### Spanned zip (`tools/synth_zipsplit.py`, same runner)

Here the generator is **Info-ZIP**: `zip -s 64k` builds each case split,
and the same input unsplit, so each is adjudicated four ways — the source
tree, `unar`, our CLI on the set, and our CLI on the unsplit archive (no
joiner on that path). Skipped with a notice without `zip`.

Six cases: stored entries straddling part boundaries; a deflated stream
straddling one; nested folders with an 8-bit name and an empty file; twelve
parts (`.z09` → `.z10`); a `zip -s` archive that did not need splitting (must
extract even under `--no-parts`); and **`zspancd`**: 1,200 entries at 64 KB
per part, so `zip -s` SPLITS the central directory — disk 7 of 8, the
directory starting on **disk 6**, 132,048 bytes declared, 238 of the 1,201
entries in the 26,312-byte last file. The other five passed a
`zs_cd_is_there` (`src/fmt_zipseg.c`) that refused this; re-do the size if
you touch that function (DECISIONS.md 2026-10-05, *the scan that was
already being paid for*).

**The two mutations hold the scheme up** (parts are placed by FILENAME):
two parts swapped, and one replaced by random bytes of the same length;
both must fail, and a lax reader (no CRC comparison, no local-header
signature check) fails those two and only those two — re-do that before
trusting a change to `zip_at` or the part-count check in
`unc_zip_extract`. Opening a MIDDLE part must fail, and `unar` is asserted
to fail on it too.

**`--stats` is asserted against a floor**: `zip_floor()` derives from each
archive's OWN central directory the fewest part opens the format permits,
and the measured count must equal it exactly.

### Compact Pro segments (`tools/synth_cptsplit.py`, same runner)

Two cases cut from archives the differential suite ALREADY grades against
`unar` and `macunpack`: `cpt4` (folders and entries either side of a cut)
and `cpt5` (one entry crossing every boundary). `unar` is asserted to
mishandle both ends (the final segment read as a whole archive, garbage
and exit 0; the first segment "Couldn't recognize the archive format",
exit 0), so the day it learns the scheme is noticed.

Beyond byte-exactness: **any** segment opens the set (Compact Pro itself
requires the final one); a segment of ANOTHER set in place of the missing
one is refused by its identity; a missing segment fails; `--no-parts`
refuses. **Part opens against a floor** derived in Python from the
archive's own directory: 5 opens with 1 backward crossing on `cpt4`, 6/1 on
`cpt5`. **One byte under its own high-water mark** (landing on the index
buffer), the walk reads each record where it lies: `cpt4` goes 5/1 →
**19/8** with a byte-identical tree; both halves are asserted.

**What this layer cannot see:** the Mac shell, and how Compact Pro actually
writes a set — covered by `tools/vmac/cptsegment.py --verify`, which
requires the generator to reproduce two real sets cut by Compact Pro 1.51
under Mini vMac byte for byte, and by the suite extracting those real sets
when present.

### Parts inside envelopes (`tools/synth_wrapped.py`, same runner)

Three cases: the StuffIt sets with a BinHex or MacBinary layer around each
part (`Archive.sit.1.hqx`), one per envelope, plus a mixed one named
`zzz-download.bin` and `Other.sit.9.hqx`. Adjudicated by the generator, by
our own read of the same set UNWRAPPED, and by `unar`'s asserted behaviour
(handed part 1 it unwraps that part and exits 0).

Behaviours: a wrapped part of a DIFFERENT set, named exactly like the
missing one, must be refused; parts scattered across three directories in
two envelopes under three names must join; nothing of ours may be left in
the output directory, on failure or success. **The ration**: a COMPLETE set
must open no envelope beside it, a set missing one must open them and join
— asserted on the decode itself (`looked inside X` under `-v`). All four
assertions fail when the code they guard is mutated (search disabled,
ration removed, cleanup removed, the decoy replaced by the genuine part).

**What this layer cannot see:** the Mac shell (`cli/main.c` only; the shell's
envelope step is driven by `interactive.py`, PROGRESS.md, M11), and the
other two schemes, which are placed by filename and deliberately not looked
for inside envelopes (DECISIONS.md, 2026-08-13).

### DiskDoubler `SPLT` (`tools/synth_ddsplit.py`, same runner)

**No oracle**: a case requires `unar` to fail on a part, so the day it has a
second implementation this says so. Adjudication is against the bytes that
were cut up and, for a zip payload, our own read of the unsplit archive.

Eight cases, each joined from the first part and from the last: two parts
cut inside the data fork, three with a cut inside the RESOURCE fork, a set
of ONE, twelve parts, 64 bytes appended after each payload, parts named
nothing alike, parts named `.001` … `.003`, and a zip payload. Behaviours:
`--no-parts` fails on a set of more than one and SUCCEEDS on a set of one
(`unc_ddseg_extract`, no volume source); a foreign set's part is ignored; a
missing part fails and says so; a part declaring more payload than it holds
is refused; a flipped PAYLOAD byte and a flipped STORED CRC byte each fail
with a checksum error, and the set still joins afterwards. Mutations confirm
three cases are load-bearing: the header-declared payload length (`tail`),
the fork order (every resource-fork case), and a `SPLT` header beating a
`.NNN` filename (`numbered`; DECISIONS.md 2026-08-21).

**What it cannot see:** the layout — these parts are written from
`src/fmt_ddseg.c`. **What says that** is the three sets DiskDoubler itself
cut, registered as fixtures (`run_ddtf.py --register`) and joined here
from the first and the last part, each compared with the published file
(both forks) and then extracted to what the unsplit one gives; one flipped
byte in a COPY of a real part must fail on DiskDoubler's own CRC. Outside
`ci.sh`, `tools/vmac/ddpro.py --experiments` has DiskDoubler Pro 4.1 split
a known file under emulation, and the parts join back to its bytes.

### Plain `.NNN` splits (`tools/synth_split.py`, same runner)

Three cases; the generator CUTS a file, so the join must equal the bytes
that were cut. Two payloads: a plain data file, which `unar` can also join
(so the join is adjudicated against the oracle), and a zip, which `unar`
CANNOT (it claims part 1 as a truncated archive — re-measured every run);
the zip payload must extract to the source tree and to what our engine gets
from it unsplit.

**The scheme's limit is asserted as well as its strength**: a set missing
its TAIL joins cleanly into a short file and NOTHING notices; a swap
involving part 1 makes the join a plain file nothing objects to (asserted,
with a message to find out what caught it before believing a pass). Beside
them: the consecutive-run rule (a member numbered past the run is a missing
part, where the reference appends it silently — the stray is numbered so it
cannot trip the 256-part ceiling instead), the 256-part ceiling, `--ask`
across a gap, `--no-parts`, opening any part, and part opens against a
floor of one per part with no backward crossing.

**Floors (here and in the zip cases above) are computed in Python**, never
asked of the engine, like `py_parts()`'s StuffIt match rule. Both directions
are demonstrated: the record-at-a-time directory walk gives 16/6 against a
floor of 6/1, a measure-every-part-first pass 10/1, and both fail. **A floor
that is too low reads as a defect in the thing being measured** (the model
once accused `zmany` of two opens the format requires). The last case also
runs one byte below its own high-water mark, on all-STORED cases only,
forcing the fallback walk: identical bytes, strictly more opens.

**Two ways the oracle is wrong for the StuffIt sets, both measured on
2026-08-08:**

- `unar Part.1` joins **nothing** (a bare relative name gives an empty
  `stringByDeletingLastPathComponent`, and the `dirname=@"."` guard does not
  fire), while `unar ./Part.1` joins the set. **Every oracle call passes an
  absolute path.**
- `unar` finds parts only among files whose name starts with the opened
  part's basename (`[filename hasPrefix:basename]`), so the `misnamed` case
  is adjudicated on a **renamed copy of the same bytes**.

The oracle runs `-nr` (it would otherwise extract a joined `.sit`/`.sea`
too); our side stops at the same layer.

**What this cannot see.** Zero-length files are dropped on both sides (our
CLI writes an empty data fork as an empty file, `unar` writes nothing), so
a disagreement of that shape is covered only by the generator comparison.
Nothing about the Mac: `tools/vmac/run.py --extra-file` puts the other
parts on the In floppy, and `tools/vmac/interactive.py --segments` drives
the dialog (layer 10 below); the CLI's `--ask` uses the same engine
callback, which is the most it can claim.

**Demonstrated failing**: a matcher that ignores the fingerprint (4
failures — the name-alike intruder gets used) and a joiner that drops one
byte per part boundary (27 failures).
## The derivation tools (`tools/derive_*.py`, not in `ci.sh`)

**These are not tests. They are the evidence that a format's facts come
from somewhere other than somebody's program**: each is a reader for one
format, written from a description and nothing else, which decodes whole
forks and compares them against the sha256 an independent oracle recorded
in `fixtures/manifests/`.

| tool | reads | against |
|---|---|---|
| `derive_huffman_tree.py` | the bit-serialized tree of StuffIt 3, DiskDoubler 4 and PackIt | 13 forks; `--grid` re-derives the rule from a 16-way search |
| `derive_stuffit8.py` | StuffIt method 8 (Miller-Wegman) | all 4 method-8 forks in the corpus; `--grid` re-searches the parameters |
| `derive_arc.py` | ARC's member header, RLE90, and methods 4, 8 and 9 | 6 members; `--grid` derives them from archives a real ARC 5.21q writes to order |
| `derive_cpt.py` | Compact Pro, container and both coders | 536 forks of 68 archives |
| `derive_sqp.py` | AppleLink `.pkg` — SqueezePlay's two directories, folder levels and 13-bit LZW, out of Aladdin's own expander | **4 of 4** members of the two real packages, to their declared length and a recorded sha256, plus **29 witnesses checked at the offsets they are claimed to sit at**. It grades the READING; `tools/run_sqp.py` grades the engine. Cannot see whether Aladdin's expander reads what `tools/synth_sqp.py` writes |
| `derive_sit13.py` | StuffIt's container and method 13 | 897 forks of 103 archives, all six code selectors |
| `derive_sit6.py` | StuffIt method 6: framing, fixed code book, PackBits tail | all 11 method-6 forks in the corpus — 27 blocks, 13 Huffman and 14 stored; parses the 26 bytes out of deark's source rather than holding a copy; measures whether the stop code follows the declared length (13 of 13) |
| `derive_dd.py` | DiskDoubler's DD (10) and AD (6, 9) coders | 39 of 39 forks, two in method 10's delta form, NAMED so the list can be held against `derive_ddc.py`'s |
| `derive_sit5crypt.py` | StuffIt 5's archive flag byte, against archives Aladdin's own software wrote | **5 of 5** encrypted: bit 7 = encrypted, bit 4 = the password hash sits 14 bytes later (shift checked LOAD-BEARING: 5 against 13), hash MD5(MD5(password)[:5])[:5] at passwords of 4, 9 and 17 characters — only Aladdin's bytes and `hashlib`. **Bit 5** against `Sample Archive.sit` (StuffIt Deluxe 5.5's `Tutorial Files`, via `tools/vmac/sitzip.py --payload 55`): 100 + 14 + 4 + 204 + 22 is exactly `firstoffs`, blocks of 0, 2, 6 and 8 required NOT to close it. The **order** of hash and block on two StuffIt Deluxe 7.0.3 archives (`tools/vmac/sitcomment.py --specimen`). Cannot see **bit 6**, which nothing here sets. Specimens in the cache |
| `derive_dd8.py` | DiskDoubler method 8 — whether it IS Compact Pro's stages, and at what Huffman block | **9 of 9 method-8 forks, byte for byte**, with `derive_cpt.py`'s reader (from Compact Pro's three published wiki pages), graded against the manifests AND each fork's own CRC-16/ARC; of eleven block sizes **0xfff0 is the only one that reads all 9** (FORMATS.md, *Method 8's Huffman block*); the two adjudicators must agree fork for fork. Cannot see whether some OTHER pair of stages would also reproduce them |
| `derive_ddc.py` | DiskDoubler's three containers: a compressed file, `DDAR`, `DDA2` | **all 91 DiskDoubler fixtures, 244 entries — 643 assertions, 0 disagreements**: path, both fork lengths, type and creator where recorded. `--grid` reports for each field every offset that agrees EVERYWHERE, and which fields the corpus cannot pin (`DDA2`'s stored-record resource-fork length: 27 offsets survive, the value being 0 in all 30). `tools/vmac/diskdoubler.py --combine` / `--verify-combine` grade DiskDoubler 3.7's own Combine output: **7 entries, 0 disagreements** |
| `derive_packit.py` | PackIt's container, stored and Huffman-coded | 38 forks of 4 archives; it checks no CRC, so nothing here confirms the polynomial |
| `derive_sit5.py` | the StuffIt 5 container: archive header, both entry headers, the second file header and the tree | **all 31 StuffIt 5 fixtures, 525 entries** — every PATH (built from the parent-offset chain) and both fork lengths, 0 disagreements |
| `derive_lzh.py` | the LZH/LHA header, all four levels and the extended-header chain | **156 archives and 191 entries** (this project's 7 fixtures, lhasa's collection from 20 writers, LHa for UNIX's own), **0 disagreements** against lhasa's listing. Structural: an entry's data must end where the next header begins. lhasa's three name rewrites are counted (41 names), not adopted. Refuses `regression/truncated.lzh` |
| `derive_now.py` | Now Compress: all four coders, the block table, and the shared container | `nowcompress.py`'s specimens, byte for byte — 139 archive blocks of 139 and 144 specimens across sixteen cases — and **both corpus archives** via `--expect DIR` (`--forks visible`): the 1993 one's 3 blocks of 3, the 1995 one's 306 of 306. **Nothing is searched for**; three checksums (block, table, member record) are checked as it goes. `--prefixes` censuses LZSS stream openings. **Cannot see any version not installed** (5.0.1's and 6.0's, `nowcompress.py --setup6 --case6`) |

Each writes its corrections into `docs/formats/`, which the engine cites;
the descriptions are fetched into `reference/notes/` by
`tools/fetch_references.sh`.

**One asks the other direction.** `tools/mutate_now.py` changes one field
of a Now Compress file, recomputes every checksum, and
`tools/vmac/nowcompress.py --expand` / `--adjudicate` hands it back to Now
Compress itself. It cannot see beyond the ONE implementation that exists
(5.0.1, and the decoder a 1995 `.sea` carries), and a failing mutation
proves only that something changed — which is why the byte in front of a
Huffman stream needed a POSITIVE specimen (docs/formats/now-compress.md,
*A code length past 15*).

**Not in `ci.sh`**: they need the fixtures, `derive_arc.py --grid` needs the
encoder `get_arc.sh` downloads, and the whole set takes the better part of
an hour. All skip cleanly with a message when what they need is absent.

**What they CANNOT see:**

- **Whether the shipped C is independent of XADMaster.** They prove a
  description is sufficient to read the format, nothing about how `src/`
  was written.
- **Anything about a fork no fixture has.** StuffIt method 8's table
  restart, end-of-stream code and 14-bit ceiling are unreached, so
  `fmt_sit.c` still cites XADMaster for those three rules. Every tool
  prints how many forks it decoded.
- **Whether the oracle is independent.** `unar` IS XADMaster; where a second
  lineage exists it is used instead (`derive_arc.py --grid` against a real
  ARC's input; the DiskDoubler method-4 specimen read back by Salient's
  expander).
- **What this project's own Now Compress fixtures are not.** The 13
  synthetic archives `tools/synth_now.py` writes are not what the encoder
  writes: zero block trailers and file-header checksum, mode words
  `0x0001`/`0x0021` against `0x0010`/`0x003f`, padding 2, LZSS streams
  opening `00 00` against `00 03`, **no fork-boundary record**
  (docs/formats/now-compress.md, *A member's blocks*), and **blocks not
  word-aligned**, where all 479 of the encoder's are (*Every block is an
  even number of bytes*). 25 of their 37 shape-3 blocks are odd, so they
  state their stream start two ways (`src/fmt_now.c` rounds up,
  `derive_now.py` believes byte 1); they stay that way because `unar`
  refuses a region leaving it fewer than four spare bits (measured
  2026-08-15). `--ladder`'s `word` rung is the aligned build; `build_fork`
  carries the record, because Decompress refuses a file without it.

### The rungs

  `synth_now.py --ladder` builds a control and a rung per difference, and
  `tools/mutate_now.py`'s `splice` puts each in a real self-extractor's
  data fork for Now Compress's own decoder (`nowcompress.py --adjudicate`,
  about six minutes a boot). The **control** is `probe`'s 3,830-byte
  archive inside `tree`'s self-extractor:

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

  **Three things are needed and the fourth is not**: the archive trailer,
  32,768-byte blocks and word alignment (docs/formats/now-compress.md,
  *The archive layer*, *A fork is a sequence of blocks*, *Every block is an
  even number of bytes*). An archive can be ACCEPTED and still be wrong
  (`no-word`), so the fork comparison grades a rung, not the verdict line.
  None of the three was on any list of differences; they came from diffing
  an encoder-written archive field by field. `derive_now.py` reads 4 of
  `synth-now-mixed.now`'s 15 blocks and every block of every archive Now
  Compress wrote (docs/formats/now-compress.md).

- **A rule fitted to the blocks in front of it.** "16 minus header byte 4"
  for a shape-3 stream start was exact on 75 blocks and wrong on 20 of the
  1995 archive's 306 (the correction is `mod 16`); it was caught only
  because the header states the number twice (docs/formats/now-compress.md,
  *The header*).
- **A degenerate match.** A single-leaf Huffman tree decodes copies of one
  byte from nine bits found in almost any file; `derive_huffman_tree.py`
  refuses such matches (one was reported as a confirmation on 2026-09-20).

## What a SNIFF costs in reads (`tools/sniff_io_probe.c`, not in `ci.sh`)

Measures `unc_sniff` alone, by wrapping `UncIO` with counters; one line per
file:

    gcc -std=c99 -O2 -DUNC_OFF64 -Iinclude tools/sniff_io_probe.c \
        build/rel/*.o -o build/rel/sniff_io_probe
    find fixtures -maxdepth 1 -type f ! -name '*.md' | sort \
        | xargs build/rel/sniff_io_probe

    fixtures/4acalc.zip fmt=Zip reads=4 bytes=1562 seeks=4 size=10422

**Reads, not bytes, are what it is for**: on a Macintosh each call is a
`SetFPos` + `FSRead` pair, a head move on a floppy; `unc_zip_scan_eocd` is
sized by that count (`src/unc_engine.c`). It established that the zip
end-of-central-directory scan is **50.0 % of every read a sniff of the
corpus makes** (FORMATS.md, *What the zip pair claims, and what it costs*).
To attribute a share to one probe, build a second binary with that probe
short-circuited and subtract — the instrument sees only the total.

**What it cannot see.**

- **Correctness** — that is `run_diff.py`'s and every other suite's.
- **Cycles, or time.** A read of 4 bytes and of 1,027 count one each. For
  instructions use `tools/m68kprof.py`; for real cost, the tick probe on an
  emulated Mac.
- **The Macintosh's own I/O** (stdio is not the File Manager).
- **Any file it is not handed**: the corpus is 996 files, and the
  population that matters for REJECTION cost is non-archives —
  `reference/`, this repository's trees, the specimen cache; 8,364 were
  swept on 2026-10-05 (BLOCKERS.md, *Withdrawn claims*).
- **A regression**, because it asserts nothing; the claims it settled are
  pinned by `test_zip_behind_a_stub` in `tests/unit_formats.c` and
  `tools/run_zipit.py`'s nine-of-nine sniff count.

## The 68000 profile (`tools/m68kprof.py`, not in `ci.sh`)

**It ranks; it does not price.** The tick probe on an emulated Mac Plus
(`tools/vmac/README.md`, `UNC_AT_TIMING`) prices a change; this says WHERE
to look. It reads a `qemu-m68k -d exec,nochain,in_asm` log: per-function
instruction counts, then the hottest basic blocks with `file:line` through
`addr2line`.

    m68k-linux-gnu-gcc -static -std=c99 -g -Os -mcpu=68000 \
      -fno-tree-loop-distribute-patterns \
      -freorder-blocks-algorithm=simple -fipa-icf \
      -Iinclude -Ithird_party/zlib -DZ_TESTW=0 -DNO_GZIP \
      cli/main.c src/*.c third_party/zlib/*.c -o /tmp/me68k
    mkfifo /tmp/q.fifo
    python3 tools/m68kprof.py /tmp/q.fifo /tmp/me68k > /tmp/prof.txt &
    qemu-m68k -d exec,nochain,in_asm -D /tmp/q.fifo /tmp/me68k t fixtures/<f>

`-Os` and `-mcpu=68000` are what ships; the other three flags suppress
transformations the Mac build does not get. `nochain` makes the log
complete; the FIFO keeps a multi-gigabyte log off the disk.

**Read the BLOCKS, not just the functions**: the function ranking
attributes an inlined callee to its caller (on `macburger-helper.hqx`, 25
of `bh_get_bits`' 41 % were `bh_refill_line` inlined into it —
DECISIONS.md, *the character that was touched three times*).

**What it cannot see:**

- **Cycles.** It counts instructions; a `mulu`, `divu` or libgcc helper
  (`__mulsi3`, `__udivsi3`) costs far more than its count. Changes within a
  few percent are not ranked by this — settle them on the tick probe.
- **The inliner's choices on the target** (a different GCC from
  Retro68's); the `.obj` and the CODE ratchet check that.
- **Anything in the Mac shell** — 1.5 % of an extraction, measured once
  (FORMATS.md, *What -O3 is worth, and where*).
- **Whether the change is worth anything.** −23.0 % of Linux `Ir` was
  −9.4 % of Mac Plus ticks on one rewrite and −35.8 % of 68000 instructions
  was −36.7 % of ticks on the next: closer, still not the answer.

## On-Mac layers (not in `ci.sh` — they need an emulator)

7. **Mini vMac replay** (`tools/vmac/run.py`, System 6.0.8 and 7.0.1 on a
   Mac Plus; `tools/vmac/sys30.py` for System 3.0, which reads no
   boot-block shell name): the autotest build CRC-32s both forks after
   reading them back through the real File Manager and paints an aggregate
   to the framebuffer; the host decodes the screenshot and compares against
   the same engine's Linux output (`tools/vmac_check.py`).
8. **Mac OS 9 replay** (`tools/vmac/os9.py --launch`, QEMU PowerPC): the
   application is launched from the Finder by keyboard; afterwards the
   transfer volume is mounted with hfsutils and **both forks of every output
   file are compared byte for byte** against `macextract x` with auto-unwrap
   ON (the INTERACTIVE build takes envelopes off; `tools/vmac/README.md`).
   **21/21 on the committed sample**, 2026-09-04 (BLOCKERS.md, *Withdrawn
   claims*; DECISIONS.md 2026-09-04, *the field nobody assigned*). The run
   goes to the END of the interaction (alert dismissed, SFGetFile repaint
   checked, Cmd-. quits); `--cancel` interrupts the extraction (pass: a
   strict non-empty subset of the entries); `--cancel-click` does it through
   the Cancel BUTTON, with `--click-at` as the control (FORMATS.md,
   *Cancelling, and an 8-bit name*); `--encrypted` covers the password
   dialog on a generated archive, a wrong password first (FORMATS.md, *An
   encrypted archive, through the dialog*). SpaceSaver runs by PATH out of
   the emulator cache, reconciling `archive.sit~1` against `archive.sit`
   (FORMATS.md, *SpaceSaver on Mac OS 9*). **What it cannot see**: a name
   the Mac cut at 31 characters (both sides are in the Mac's spelling;
   `run_names.py`), and whether an extraction finished or paused at 0 % —
   the completion wait is the screen going still; when that misfires the
   disk comparison still decides.

9. **Reading the Mini vMac Out volume** (`tools/vmac/run.py --keep-disks`
   then `tools/vmac/checkdisk.py /tmp/vmacrun-*/`): layer 8's comparison
   on the System 6/7 tier — both forks byte for byte, plus names and folder
   structure, read off the floppy image. **73/73 on 2026-09-22** (the
   71-fixture sample of that day and two run alone). It grades the UTF-8
   fold's NAMES (`tools/vmac_check.py`, `mac_component`): with the fold
   disabled `derived-800saywhat301j.sit` fails it with three names missing
   and three unexpected.

10. **Driving the real UI** (`tools/vmac/interactive.py`): the interactive
    application, clicked the way a person clicks it.

    - `--segments` covers the "locate part N" alert (the autotest build
      does not compile `SegAskUser`): part 1 on the boot volume, the others
      on a second floppy, the WRONG part offered first, and it **ends on a
      byte comparison** of the joined file read off the volume — a
      screenshot fails identically whether the application or the harness
      is wrong (DECISIONS.md, 2026-08-09).
    - `--dest`: the DESTINATION dialog switched to an empty floppy; every
      output name must be on it and none on the archive's volume.
    - `--diskswap`: the harness **inserts the disk while the alert is up**
      (`tools/vmac/xdnd_insert.c`), a decoy disk first that must not dismiss
      anything; ends on the joined bytes, so its fixture must not be an
      archive (`tools/vmac/README.md`).
    - `--diskeject`: part 1 on a floppy of its own, which must be ejected
      before the alert asks while the application's disk is not, and on
      System 7 no dimmed Floppy A left on the desktop. **Neither can see a
      one-drive Mac** (MANUAL_TESTS.md §4) — except `onedrive.py`'s, on a
      one-floppy Mini vMac build, which counts the disks the System asks
      for after Save.
    - `--wd`: the archive inside a folder, Return accepts the default
      destination; every output must be under that folder, none at the
      root.
    - **The default phase runs on both Mini vMac tiers**, `--system
      Sys7.img` included: `ProgressPump()`'s `WaitNextEvent` side, Cancel
      through `DialogSelect`, Cmd-., the SFGetFile repaint, and 8-bit names
      photographed — the one thing the byte comparisons cannot see. Mac OS
      9 covers all of those through `os9.py` (`--cancel`, `19-names.png`,
      `--cancel-click` via `os9mouse.Pointer`).

**What each layer can see is not the same.** Layer 7 compares a count, two
summed CRC-32s and two summed lengths, so it has never checked an output
NAME and cannot fail on one; layer 8 compares names by reading a directory,
and on its first sweep failed two fixtures layer 7 had passed for weeks
(the gzip/.Z fallback name; BLOCKERS.md, DECISIONS.md). **An aggregate check
cannot fail on a property it never aggregates. When adding a harness, write
down what it is blind to.** Layer 9 exists because the claim that Mini
vMac's write-back could not be read off the Out volume did not reproduce
and is withdrawn (BLOCKERS.md).
