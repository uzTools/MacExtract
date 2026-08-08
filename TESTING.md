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

## The oracle

The oracle is The Unarchiver's CLI (`unar`/`lsar` 1.10.8, Debian
package `unar`), whose XADMaster engine is also our primary reference.
`macunpack` (macutils) is a secondary cross-check for old formats.

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
sha256+size, resource fork sha256+size, and type/creator when the
oracle exposes them.

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

## The sampled inverse BWT (`ci.sh` variant 1b, added 2026-08-07)

The Arsenic decoder picks between a 4-bytes-per-byte transform table and a
sampled occurrence index **by trying to allocate the table and failing**
(DECISIONS.md). Nothing an unconstrained run does reaches the fallback, so
CI forces it three ways:

- `-DUNC_ARS_FORCE_SAMPLED` compiles the fast path out. The whole
  778-fixture diff suite and all 7,780 robustness variants run through the
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
    UNCLASSIC=build/never/unclassic sh tests/run_diff.sh      # expect 778/778

    # 2. the safety net is correct: force it to run on every stream
    make BUILD=build/tiny CFLAGS="-O1 -g \
        -fsanitize=address,undefined,alignment -fno-sanitize-recover=all \
        -DUNC_LZW_TINY_TABLE" all
    UNCLASSIC=build/tiny/unclassic sh tests/run_diff.sh       # expect 778/778

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

Step 2 was re-measured at **778/778** on 2026-08-08. Step 3's figure is from
2026-08-03 and was **675/769** — 94 failures — against the 769-fixture suite of
that date; re-running it needs the hand edit above, and what matters is that it
fails at all, not the count. The LZW-path figure is from the same day.

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
