# OPEN_ITEMS.md — what is missing, as of 2026-08-09

A standing audit of the gaps: things not done, things done but not verified,
and things this repository asserts more confidently than the evidence supports.

**Not** BLOCKERS.md, which records investigations that went wrong and the
claims withdrawn from them. Nothing here stops the engine or the CLI, which are
byte-exact against the oracle across 797 fixtures in `./ci.sh`.

Each item says what would close it. Detail lives in one place per finding —
status in BLOCKERS.md, reasoning in DECISIONS.md, how to re-run in TESTING.md
or `tools/vmac/README.md`, what needs real hardware in MANUAL_TESTS.md,
results in FORMATS.md — and is cross-referenced from here rather than
repeated.

**Filing something here is a decision to stop looking at it, so it had better
be true.** Section 1 in particular: it held "eight fixtures are excluded as
oracle-undecidable or oracle-buggy" until 2026-08-08, when the item turned out
to be nine fixtures, closeable in an hour, and nothing to do with this
environment (section 4).

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
| The LZW table sized from `maxbits` rather than the input | 2026-08-03 | growth-on-demand and one-shot sizing look interchangeable and are not: copy-based growth has an `old + new` transient, so **where the buffer IS the allocation it can lose to doing nothing** (measured, 274,432 → 405,504 B). Bound it from the input instead. DECISIONS.md |
| StuffIt 5 / Arsenic incomplete at the 1 MB floor (42/44) | 2026-08-07 | the last four gains were all "allocate less of what the data does not use"; this one had to **reduce the requirement** instead, and the tell was that no placement or reserve tuning could close a 410 KB shortfall on a 760 KB machine. Also: **estimate the thing you are changing.** The prediction here was within 200 B on one fixture and 3.6% on the other because it estimated a single allocation inside one entry; the method 13 estimate a day earlier missed badly because it estimated an aggregate over a distribution. DECISIONS.md |
| "peak heap under a budget" read as a requirement | 2026-08-07 | a decoder with a time-for-memory dial spends whatever the cap allows, so its peak tracks the CAP, not its needs. Comparing such a peak against a predicted requirement compares two different quantities — **bisect the cap** for the requirement. This nearly made the sampled BWT look 2.3x worse than predicted when it was in fact accurate |
| The Mac-side checkers read `<X>.rsrc` sidecars, so nine fixtures could not be replayed on the Mac | 2026-08-08 | the sidecar heuristic ("`X.rsrc` is a sidecar only when `X` exists beside it") cannot describe an archive where both are real. All host-side readers now extract with `--forks hidden` and pair `._X`, including the mock File Manager — on HFS the fork is inside the file, so the suffix made the mock *less* faithful than the prefix. Sample 44 → 53 fixtures, **53/53 at 4 MB, at the 1 MB floor, on System 7, and read back off the volumes with names**. Adding one fixture of a new SHAPE exposed three harness defects that were unfailable rather than passing, including `/` inside an HFS filename. DECISIONS.md |
| `unclassic x` clobbered its own output on a THINK C archive | 2026-08-08 | entry `X`'s sidecar and entry `X.rsrc`'s data fork are one path, and the sink opened it `"wb"`: a 7,048 B resource fork became a 0-byte file with a zero exit status. Every open now refuses an existing path as a per-entry error naming both ways out. **Fixing a harness can hide the defect it was hiding** — `run_diff.py` had just been moved to `--forks hidden`, so nothing exercised the shipped default any more; `tests/run_collide.sh` extracts with the default on purpose. DECISIONS.md |
| StuffIt method 1 (RLE90) had no oracle coverage | 2026-08-08 | the premise was false in the same way twice over. `unar` decodes the method-1 fork perfectly — it fails on a *different entry's* fork compressed with method *3* — and `make_manifests.py` was discarding nine adjudicated forks to avoid recording the one bad one. **A harness that throws evidence away is indistinguishable from one that never had it**, because `oracle FAILED on X` scrolls past on every rebuild and reads as a fact about the fixture. Per-entry manifests took the suite 778 → 793 across 19 fixtures that had contributed nothing. Also: what a failed extraction leaves behind is not one thing (0-byte, 114 KB partial, or a sidecar padded to the declared length with garbage), so "the failed fork will be empty" is not a usable cross-check. DECISIONS.md |
| Nine fixtures with no oracle manifest ("undecidable" or "oracle-buggy") | 2026-08-08 | both reasons were the fork-naming flag, not the archives: `unar -k visible` writes `NAME.rsrc`, which collides with a real entry called `X.rsrc` and which GNUstep refuses to build for a leading `~`. `-k hidden` (`._NAME`) decides all nine, and all 774 existing manifests rebuild identically. **A limitation and its remedy sat one paragraph apart in TESTING.md**; the remedy was a documented flag of a tool already in use. DECISIONS.md, BLOCKERS.md |
| StuffIt method 6 unimplemented, "no oracle to check it against" | 2026-08-08 | the oracle existed and was already in `reference/`: macunpack has decoded fixed Huffman since 1991, and only XADMaster — the implementation we happened to be reading — refuses it. **"No oracle exists" was a statement about one tool.** The second fixture the item also said was missing was a generator, not a search: `tools/synth_sit6.py` covers the branches the one real fork cannot reach. Building that oracle also adjudicated 22 forks of OTHER methods that unar fails on, taking the suite 793 → 795. DECISIONS.md, TESTING.md |
| The Mac "locate part N" alert had never been on screen | 2026-08-09 | the emulator runs that proved the join used the autotest build, which does not compile `SegAskUser` at all — so "verified on a Mac" covered the join and covered none of the dialog. Closed by `tools/vmac/interactive.py --segments`, which forces the alert by leaving part 1 alone on the boot volume. **Both bugs it found were in the harness, and both looked like application bugs**: Standard File opens on the LAST-INSERTED volume, so the first walk opened part 2 and the app's perfectly correct "part 1 has not been found" read as a defect; and the read-back opened the pristine boot image rather than `Mac()`'s private copy, reporting "not found" for a run that had worked. **A UI harness asserts on a screenshot, so its own mistakes are indistinguishable from the failures it is looking for** — which is why this phase ends on a byte comparison instead. DECISIONS.md |
| Output could only go beside the archive | 2026-08-09 | wrong for the case the segment work exists for: the volume holding the output is the volume that has to be ejected. There is no folder picker before System 7, so the System 6 idiom is `SFPutFile` with the name ignored — and because Standard File keeps ONE current folder across it and `SFGetFile`, the dialog opens beside the archive and Return is the old behaviour. Closed by `interactive.py --dest`, which asserts on BOTH volumes because "Extraction complete." looks the same wherever the bytes went. **The prompt is a fixed-width resource, not a sentence**: "Extract the files into this folder:" rendered as "Extract the files into this". DECISIONS.md |
| `Mac.settle` could not tell "finished" from "slow" | 2026-08-09 | it waited for two consecutive identical frames, and the progress dialog repaints once per engine callback (8–16 KB of input), so on a slow decode both polls land in one gap. It returned at 33% and `--dest` reported the application had written to the wrong volume. Now every settle that waits on an extraction asks for SECONDS of stillness (`quiet=EXTRACT_QUIET`) rather than two polls. **The unsound wait had been in every interactive phase since M10 and never failed, because none of them could**: they extract to a hard disk and are judged by eye. It took an assertion to expose it. DECISIONS.md |
| Two harness excuses that could not fail | 2026-08-08 | found by asking what EVIDENCE each tolerance rested on. One rested on our own error message — a fixture was skipped whole when every entry our binary called "recognized but unsupported", so the thing being graded decided whether it was graded; it was discarding 10 adjudicated forks of the two PKZIP 1.x zips, and a regression on a supported method would have become a skip. The other excused a whole ENTRY where the oracle had failed one of its forks, so an adjudicated fork beside an unadjudicated one was never required to exist. Both now anchor on the oracle (`oracle_methods` from lsar), both were demonstrated failing with stub binaries first, and no engine result moved: 795 → 797 graded. **An excuse must be anchored outside the thing it excuses.** DECISIONS.md, TESTING.md |

---

## 5. Deliberate gaps, and remedies ruled out by measurement

- **Out of scope by the brief, and still out:** compression, StuffIt X
  (`.sitx`), encrypted archives, disk-image extraction, Now Compress, and
  LZH *extraction* — LZH was the optional half of M8 and is detect-only
  (the LZH/LHA row of FORMATS.md). **Multi-segment archives are IN scope
  since 2026-08-08** and one scheme is implemented; the rest are the
  section below.

---

## 6. Multi-segment: what the proof of concept deliberately left

StuffIt segments extract end to end (M11). These are the parts that were
scoped out on purpose, ranked by what they would cost.

- **Other segment schemes.** Spanned Zip (`.z01…/.zip`, oracle: `unar`)
  and plain `.NNN` splits are next and cheap; note a `.NNN` split can
  only ever be identified by NAME, so it cannot meet the "parts may be
  named anything" bar the StuffIt scheme meets. **Compact Pro segmented
  archives are the interesting one and the expensive one**: the format
  documents a volume byte per archive and per entry, no reference
  implementation extracts them (`unar` and `macunpack` both read the
  byte and ignore it), and there is no sample in the corpus — so it
  needs a genuine segmented `.cpt` before a line of parser is written.
  Compact Pro itself is in the corpus and splits archives across
  floppies, so generating one under Mini vMac is a route; the oracle
  would then be differential (same files, segmented vs not).
- **Reacting to a disk being inserted.** The Mac shell finds parts by
  scanning a folder and by asking the user, and does nothing when a new
  volume appears — so after a disk swap the user must point at the part
  even though it is now sitting on the desktop. `diskEvt` already
  arrives in `ProgressPump` and is dropped; the rescan it would trigger
  is the same routine the folder scan uses. **Held until the UI is
  reworked, deliberately**, so that the shipped code has no path that
  nothing exercises. It is **testable under emulation** — Mini vMac
  mounts an image mid-run — and does not belong in MANUAL_TESTS.md.
- **Parts that are individually wrapped.** A real download is
  `Archive.sit.1.hqx`: each part BinHex- or MacBinary-encoded on its
  own, so the envelope has to come off before the join. Today the
  envelope recursion runs *after* the join, which is the other order.
- **A part count in the alert.** The format stores none, so "part 2 of
  3" cannot be stated. The remaining byte count can be (`total` minus
  what has been read), and is not shown yet.

- **Do not retry, on Mac heap pressure.** Both were measured while StuffIt 5 /
  Arsenic was still short of the 1 MB floor, and both are dead ends:
  `MaxMem()` before a retry (compaction may not move a `NewPtr`), and
  relocatable blocks moved high with `MoveHHi` (it demonstrably works,
  205,828 → 803,634, and changed `MaxBlock` at the refusal by under 500 B —
  the stranded heap was never about where the live blocks sat). Cited from
  `src/sit_arsenic.c` and `mac/unclassic_mac.c`.

