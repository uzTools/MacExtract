# OPEN_ITEMS.md — what is missing, as of 2026-08-03

A standing audit of the gaps: things not done, things done but not verified,
and things this repository asserts more confidently than the evidence supports.

**Not** BLOCKERS.md, which records investigations that went wrong and the
claims withdrawn from them. Nothing here stops the engine or the CLI, which are
byte-exact against the oracle across 769 fixtures in `./ci.sh`.

Each item says what would close it. Detail lives in one place per finding —
status in BLOCKERS.md, reasoning in DECISIONS.md, how to re-run in
MANUAL_TESTS.md, results in FORMATS.md — and is cross-referenced from here
rather than repeated.

---

## 1. Cannot be closed in this environment

- **Real 68k hardware: never run.** No genuine floppy I/O, no real media errors
  mid-write, no real 8 KB stack underneath a real ROM's own usage. The
  per-entry I/O error path has never seen an actual I/O failure. The 1 MB
  figures come from an emulated 1 MB machine with a stripped System Folder; a
  real Plus with a Chooser extension or two has less free heap than any number
  recorded here.
- **Real PowerPC hardware: never run.** Mac OS 9 is verified under QEMU only.
- **The Retro68 `OpenDF`/`HOpenDF` report is not filed.** The `_OpenDF` trap is
  System 7 and neither falls back to a plain open on `paramErr`, so both are
  unusable on System 6; `FSOpen` in the same file does fall back. Measured,
  cases 8 and 11 of `tools/retro68-hopen-repro/`, written up in that
  directory's `ISSUE.md`. **Deliberately not submitted, and no future session
  should submit it** — the maintainer will post it from his own account. (It is
  also not possible from here: an unauthenticated POST to the issues API
  returns 401.)
- **Eight fixtures are excluded as oracle-undecidable or oracle-buggy**
  (six StuffIt, two Compact Pro; see the M4 and M6 rows of PROGRESS.md). Not known
  failures — the oracle cannot adjudicate them.

---

## 2. Known unknowns, not being chased

- **Why the pointer does not work under QEMU on Mac OS 9.** Measured to
  0.0000 effect across five mouse primitives; the mechanism behind that has no
  reproduction and is labelled a guess. The keyboard route works, so this costs
  nothing.
- **Names HFS+ permits that HFS does not.** Probably unreachable from this
  binary at all — the classic File Manager caps components at 31 characters on
  either filesystem — but that is unproven either way.

---

## 3. Untested code, named so it is not mistaken for tested

- **The interactive UI above System 6 is deliberate scope**, not a gap
  (2026-08-02). System 6 is the UI's target and it is driven end to end there.
  What that leaves unexercised: `ProgressPump()` branches on `gHasWNE`, and the
  cancel routes inside it — Cmd-., the Cancel button via `DialogSelect`, the
  dialog repainting — have only ever run on the `GetNextEvent` side. Mac OS 9
  runs the `WaitNextEvent` side, but only where nothing is cancelled. The
  engine and sink semantics of a cancel are covered separately: unit tests,
  both write paths through the qemu-m68k mock in `ci.sh`, and `UNC_AT_CANCEL`
  on-Mac at 4 MB and 1 MB.
- **Files larger than the HFS 2 GB cap**, and the engine's 32-bit-only
  arithmetic against them.
- **MacRoman filename display and 8-bit characters above System 6.** The bytes
  are checked everywhere; how they *look* on 7 and 9 is not.

---

## 4. Closed, kept only for the method

| was open | closed | why it is worth remembering |
|---|---|---|
| Cancel with partial output under streaming writes | 2026-08-01 | the mock's `--cancel` never called `sink_write`, so it tested only the "no fork was ever opened" path; now aborts mid-fork on both write paths |
| The `v0.1` tag was 10 commits behind | 2026-08-01 | **a tag freezes the documentation's errors along with its code**, and this repository's errors have all been in the documentation |
| Orphan emulators after a killed run | 2026-08-02 | `start_new_session=True` is deliberate, so a signal must be turned into a normal unwind; demonstrated by interrupting a live run, not assumed |
| "DECISIONS.md is truncated" | 2026-08-02 | it was not; the natural response — "restoring" the section — would have destroyed correct history. `git diff HEAD` answers it in seconds |
| A hypothesis filed under *harness lessons* | 2026-08-01 | filing a hypothesis as a lesson hides it: this one implied the shipped UI was broken and nobody looked. **This file is the place to look for others of the same shape** |

---

## 5. Capability gaps that are deliberate, but still gaps

- **StuffIt 5 / Arsenic on a 1 MB machine: 3 of 6 sampled fixtures fully, the
  other 3 missing exactly one entry each.** An entry needs its block plus four
  bytes of transform vector per byte the block holds, so an entry whose block
  genuinely fills 512 KB needs ~2.5 MB and a 1 MB machine cannot give it. The
  engine declines that entry and carries on, which is the designed behaviour.

  **Closed as far as it can be** (2026-08-03). Two changes took the sample from
  39/44 to 41/44, both about not paying for memory the data does not use: the
  shell no longer reads the whole archive into RAM before the engine gets a
  budget, and the Arsenic block is grown to what it actually holds rather than
  allocated at its declared 512 KB. `derived-RWAsm_Folder.sit` went from
  595.7 KB to 163.2 KB for the same 38 byte-exact entries.

  What is left is not a bug and not addressable by allocating better: those
  three entries each really do fill a 512 KB block, and 512 KB + 2 MB of
  transform vector does not fit in ~700 KB. Closing them would need a
  fundamentally different inverse BWT — a sampled or blockwise one that trades
  time for memory — which is a real design change, on a 7 MHz machine where the
  time is already the scarce resource.
- **Timing: MEASURED 2026-08-02, and closed.** Eight
  fixtures across eight formats at authentic 1x, 8/8: boot ~10 s, every
  extraction under 5 s, plus the 278 KB StuffIt anchor at ~134 s (FORMATS.md,
  README). The earlier diagnosis that this host "cannot be trusted to run 1x"
  was wrong and is corrected — an idle machine measures fine. What remains is
  nothing outstanding: `macburger-helper.hqx`, written up three times as an
  anomaly, simply takes 150 s, and instrumenting the engine's byte counter
  (`-D UNC_AT_PROGRESS`) showed the rate is very non-uniform so every timeout
  chosen for it expired mid-run. **Timing is closed for every format sampled.**
- **Out of scope by the brief, and still out:** compression, StuffIt X
  (`.sitx`), encrypted archives, multi-segment archives, disk-image extraction,
  Now Compress, and LZH *extraction* — LZH was the optional half of M8 and is
  detect-only (the LZH/LHA row of FORMATS.md).

---

## 6. Specified and ready to do: size the LZW table from the input

**Attempted 2026-08-03, reverted, and worth finishing.** `.Z` is the second
largest peak in the format matrix at a flat **274,432 B**, and it is flat
regardless of input: `compress(1)` writes `maxbits=16` by default whatever it
compressed, so a 488-byte `.Z` allocates 256 KB for a table it fills a few
hundred entries of. `unc_lzw_init` allocates `(1 << maxbits) * 4` — the
DECLARED ceiling, exactly the mistake the Arsenic block had.

**What was tried and why it failed.** Growing the table on demand (doubling,
as `ars_block_reserve` does) measured:

    synth-exo-Z.Z          274,432 -> 18,432 B
    synth-exo-tar-Z.tar.Z  274,432 -> 61,440 B
    a2ps.V4.3.tar.Z        274,432 -> 208,896 B
    popper-1.7.tar.Z       274,432 -> 405,504 B      <- WORSE

The last row is the lesson: a copy-based growth has an unavoidable
`old + new` transient, and where the table IS the whole allocation that
transient becomes the peak. Arsenic escaped this only because its transform
vector (4x the fill) dominates the later peak. **Copy-based growth can never
beat a single allocation for a file that fills most of its table** — that is
arithmetic, not a tuning problem, so do not retry it.

**The design that does work, and was half-implemented when the session ended.**
Size the table ONCE, from the input: every input code defines at most one new
symbol and codes are at least 9 bits wide, so

    symbols <= 256 + reserved + insize * 8 / 9

However large `maxbits` claims. No transient, one allocation, strictly better
than today in every case — `popper-1.7.tar.Z` would be ~211 KB rather than
274 KB, and the 488-byte fixture ~2.8 KB.

Concretely:

- add a `uint32_t insize` parameter to `unc_lzw_init` (0 = unknown, keep
  today's behaviour);
- `fmt_exo.c` passes `c->io->size(c->io->ctx) - 3` (less the 3-byte header);
- `fmt_sit.c:143` (StuffIt method 2, maxbits 14) passes the entry's compressed
  size if it has one, else 0;
- keep a growth path as a **safety net** so an under-estimated bound is still
  correct rather than an overflow — it should never fire with a correct bound.

Verify with `unclassic t --stats` on the four `.Z` fixtures and the two
`.tar.Z` chains, then `./ci.sh`, then the 1 MB sweep. Nothing currently fails
because of this, so it is an efficiency change, not a fix — treat a regression
in any peak as disqualifying, which is what killed the first attempt.

## 7. Loose ends

- **StuffIt method 1 (RLE90): the claim that no corpus fixture uses it was
  WRONG.** Measured 2026-08-01 by instrumenting the method byte:
  `derived-New_Python.sit` has one 470-byte method-1 resource fork, and the
  engine extracts that archive cleanly with every CRC-16 verified. It has no
  ORACLE coverage because `unar` fails on that same archive, so no manifest
  exists. Closing it properly still needs a method-1 archive `unar` can read.
- **StuffIt method 6, "fixed Huffman", is not implemented — and was never
  named.** `derived-INITLoader.sit` carries one 34,818-byte method-6 fork;
  the engine returns a clean per-entry "recognized but unsupported", which is
  correct behaviour, but no document mentioned the method existed. XADMaster
  does not implement it either (`XADStuffItParser.m:319`), so there is no
  oracle to check an implementation against and no second fixture to test one
  on. One fork in 344 StuffIt archives — worth naming, not obviously worth
  implementing.