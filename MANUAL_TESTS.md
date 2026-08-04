# MANUAL_TESTS.md — Macintosh application checklist

NOTE (2026-07-25): the shell runs under Mini vMac (System 6.0.8, Mac
Plus, a true 68000) and **extracts correctly — single-fork, two-fork,
and multi-file — with both forks verified byte-exact ON THE MAC ITSELF**
(44/44 sampled fixtures at 4 MB across all twelve formats, 41/44 at
1 MB). Data forks match exactly;
resource forks match except the 112-byte "reserved for system use" area
of the resource file header (offsets 16–127), which is masked identically
on both sides — see DECISIONS.md. For the 1 MB Mac Plus results, see the
per-fixture table in FORMATS.md.

The earlier claim that this was caused by a **broken Retro68 `HOpen`
glue** has been **withdrawn** — a standalone minimal reproduction
(`tools/retro68-hopen-repro/`) disproved it. See BLOCKERS.md.

### Why an entry is refused, 2026-08-04 — `-D UNC_AT_BUDGET`

The result grid carries what the engine **used** and never what it was
**allowed**, so a budget refusal and a genuine shortage are indistinguishable
on screen — and `mal_alloc` returns NULL for two unrelated reasons with
opposite fixes. `-D UNC_AT_BUDGET` overwrites four grid slots to show both:

    tools/vmac/run.py --mem 1M -D UNC_AT_BUDGET fixtures/<fixture>

| grid slot | carries |
|---|---|
| `errors` | `MaxBlock()` at the first refusal |
| `sumDataCRC` | size of the first refused allocation |
| `totalDataLen` | `FreeMem()` before the reserve |
| `sumRsrcCRC` | 1 = over budget, 2 = `NewPtr` returned NULL |
| `totalRsrcLen` | the budget the engine was given |

It reports FAIL by construction — the overwritten slots no longer match the
oracle. Read the numbers, not the verdict. This is what showed the last three
1 MB refusals are a contiguity failure rather than a shortage (OPEN_ITEMS.md
section 5).

**A `-D` the CMakeLists does not know is silently ignored.** The first run of
this probe "worked" and changed nothing, because a new switch must also be
registered in `mac/CMakeLists.txt`; `run.py` passes it through the environment
and CMake drops what it has no rule for. Check that a probe's numbers actually
moved before believing what they say.

### The LZW table bound, 2026-08-03 — three builds, because one proves nothing

`unc_lzw_init` sizes its table from the input rather than from `maxbits`
(DECISIONS.md, FORMATS.md footnote §). The safety net that catches an
under-estimated bound never runs in normal operation, so it is only ever
exercised deliberately. Re-run all three — the third is what makes the other
two mean anything:

    # 1. the bound never under-estimates: hard-disable growth
    #    (make lzw_grow return UNC_ERR_MEM as its first statement)
    UNCLASSIC=build/never/unclassic sh tests/run_diff.sh      # expect 769/769

    # 2. the safety net is correct: force it to run on every stream
    make BUILD=build/tiny CFLAGS="-O1 -g \
        -fsanitize=address,undefined,alignment -fno-sanitize-recover=all \
        -DUNC_LZW_TINY_TABLE" all
    UNCLASSIC=build/tiny/unclassic sh tests/run_diff.sh       # expect 769/769

    # 3. these fixtures CAN fail on this code: starve the table AND
    #    skip the add instead of growing
    UNCLASSIC=build/probe/unclassic sh tests/run_diff.sh      # expect 675/769

`UNC_LZW_TINY_TABLE` is committed and forces the initial capacity to 258.
Steps 1 and 3 are one-line local edits and are deliberately NOT build flags:
each makes the engine wrong on purpose, and a flag that ships wrong behaviour
is a flag somebody eventually sets. **Step 3 is the point.** Steps 1 and 2 both
report 769/769 — the same number a build that ignored the input entirely would
report — so without a demonstrated failure they distinguish nothing. 94 of the
769 fixtures reach the LZW path (4 `.Z`, the rest StuffIt classic method 2).

### System 7.0.1, 2026-08-01 — a second system tier, corpus only

Every on-Mac result before this one came from System 6.0.8. This is the first
time the binary has been run anywhere else in the System 6 → Mac OS 9 range
the project claims.

**What was run:** the committed 44-fixture sample, on a stripped System 7.0.1
boot volume, 4 MB Mac Plus, same on-Mac CRC-32 read-back of both forks.

    tools/vmac/run.py --system Sys7.img --list tools/vmac/sample.txt

**Result: 44/44 byte-exact**, with engine peak heap identical to System 6.0.8
on every fixture. **1 MB: the system does not boot** — a probe painted nothing
in 180 s, which is System 7 needing 2 MB, not a fault in the application.

7.0.1 rather than 7.1 because 7.1 survives on the mirrors only as floppy sets
and a beta ISO. Both are System 7; what the tier is for is the two things
System 6 cannot reach — a working-directory `SFReply.vRefNum`, and a Process
Manager that honours the `SIZE` partition.

**NOT run on System 7, and therefore not claimed:**

- **The interactive UI — and it is not going to be.** System 6 is the UI's
  target (decided 2026-08-02); only the headless autotest build is replayed
  above it, and the Finder-driven path (`--e2e`) runs on 6.0.8 only. What that
  leaves unexercised, stated so it is not mistaken for tested: `ProgressPump()`
  branches on `gHasWNE`, and the cancel routes inside it — Cmd-., the Cancel
  button via `DialogSelect`, the dialog repainting — have only ever run on the
  `GetNextEvent` side. Mac OS 9 runs the `WaitNextEvent` side, but only where
  nothing is cancelled.
- **`SFReply` working-directory semantics: now TESTED, and passing.** See the
  section below — `run.py -D UNC_AT_WD` settles it without a Finder.
- **The `SIZE` partition under the Process Manager.** Still never exercised.

### The 'SIZE' partition, 2026-08-02 — first time it has ever done anything

4 MB preferred / 400 KB minimum has been in `mac/unclassic.r` since M10 and had
never governed a launch: System 6 without MultiFinder ignores `SIZE` outright,
and every on-Mac run until now was on System 6. System 7 always runs the
Process Manager, so the System 7 tier finally makes the question askable.

**The experiment.** Rebuild with a deliberately small preferred partition —
enough to launch, not enough for a 512 KB Arsenic block plus its transform
vector — and run a fixture that needs more than that and is known to pass at
4 MB. `derived-KeyGraphics.sit` needs ~656 KB and passes on both systems with
the stock partition.

    sed -i 's/4096 \* 1024, 400 \* 1024/600 * 1024, 400 * 1024/' mac/unclassic.r
    tools/vmac/run.py --system Sys7.img fixtures/derived-KeyGraphics.sit
    tools/vmac/run.py               fixtures/derived-KeyGraphics.sit
    tools/vmac/os9.py fixtures/derived-KeyGraphics.sit \
                      -o <dir> --hfsplus --expect-refusal
    git checkout mac/unclassic.r        # the edit is temporary, on purpose

**Result — same binary, same fixture:**

| System | Outcome | Engine peak heap |
|---|---|---|
| System 7.0.1 (4 MB) | **1 entry refused, 0 files** | 35.5 KB |
| Mac OS 9.2 (512 MB) | **1 entry refused, 0 files** | 35.5 KB |
| System 6.0.8 (4 MB) | 1 file, byte-exact | 656.8 KB |

Mac OS 9 added 2026-08-02, and the figure it produced is **the same 35.5 KB**
System 7 did — on a machine with 512 MB of RAM, which is the point: the
partition governs, not the hardware. `--expect-refusal` states the expectation
so the run is self-checking rather than a number to be interpreted by eye; it
passes only when the Linux engine DOES extract the fixture, the Mac writes
nothing, the archive itself returns `UNC_OK`, and an entry is counted as
refused. Without that first condition a negative test would pass just as
happily on an empty archive.

So **the Process Manager honours `SIZE` and System 6 ignores it**, exactly as
the resource's comment always claimed and nothing had ever shown. The 35.5 KB
peak is the diagnostic: it is parser state alone, meaning the budget rejected
the 512 KB block *at request time* and the buffer was never allocated — the
documented per-entry refusal, reached through a route that had never been
exercised. No crash, no hang; the application declines the entry and stops.

The 656.8 KB on System 6 is the same figure the 44/44 sweep records for that
fixture, which is the control: nothing about the binary changed but the
partition it was given.

### The archive RAM slurp, 2026-08-02 — the claim behind it does not reproduce

`RunExtract()` used to read the whole archive into one `NewPtr` block before
the engine got a budget, because DECISIONS.md had claimed since M10 that
reading the input while output files are created on the same volume makes the
reads return zeros. It had no reproduction, and the bullet directly after it in
the same list had already been withdrawn as an artefact of the confounded
period.

    tools/vmac/run.py -D UNC_AT_INTERLEAVE fixtures/derived-EmpireBuilderDemo.sit
    tools/vmac/run.py -D UNC_AT_INTERLEAVE --mem 1M fixtures/derived-EmpireBuilderDemo.sit
    tools/vmac/run.py -D UNC_AT_INTERLEAVE fixtures/derived-PCCTS.tar

Reads one file three ways on ONE volume and compares CRC-32s: undisturbed; in
4 KB chunks with a fresh file created and written on that same volume between
every chunk; and again seeking explicitly with `SetFPos` before each read,
which is the shape a file-backed reader has.

| run | bytes | CRC | rounds |
|---|---|---|---|
| `derived-EmpireBuilderDemo.sit`, 4 MB | 278,294 | 05746998 | 67 |
| `derived-EmpireBuilderDemo.sit`, 1 MB | 278,294 | 05746998 | 67 |
| `derived-PCCTS.tar`, 4 MB | 286,720 | 8f448a65 | 70 |

Identical all three ways in every run. The claim is withdrawn and the archive
is now read from the file as the engine asks, which hands the engine back the
archive's own size on the floor target — 39/44 to 40/44 at 1 MB, and three of
the four remaining failures went from refusing everything to extracting most
of it. `UNC_MAC_SLURP_ARCHIVE` rebuilds the old path.

**And the same-volume case is now covered, which it never was.** Every
autotest run in this project's history used a separate `In` and `Out` volume,
while the interactive application writes next to the archive — one volume,
which is exactly where the withdrawn claim lived:

    tools/vmac/run.py -D UNC_AT_SAMEVOL --list tools/vmac/sample.txt

**44/44 byte-exact at 4 MB**, output landing on the volume being read from,
with the usual on-Mac read-back CRC of both forks.

### Name collisions, 2026-08-02 — BumpName verified for the first time

`BumpName()` appends `~1`..`~9` when a sanitized name already exists. It is
live code — it is what produced `archive.sit~1` when the gzip/.Z fallback name
collided with the archive itself — and nothing had ever checked it. Nothing in
the corpus can: across all 769 manifests **no two entries collide** under the
Mac's rules (case-insensitive HFS, 31-character components, `:` <-> `/`),
which was measured, not assumed. So the archive has to be built for it.

    tools/vmac/mkcollide.py /tmp/collide.tar
    tools/vmac/run.py --keep-disks /tmp/collide.tar
    tools/vmac/mkcollide.py --verify <that run's out.dsk>

Five entries collide two different ways: `README` vs `readme` (case), and
three names sharing their first 31 characters (truncation). Every payload is
distinct and self-identifying, so the check is "the right bytes are in the
file with the right name", not "five files exist".

| archive entry | on the Mac | payload |
|---|---|---|
| `README` | `README` | upper case |
| `readme` | `readme~1` | lower case |
| `collide-me-when-truncated-to-31-alpha` | `collide-me-when-truncated-to-31` | alpha |
| `collide-me-when-truncated-to-31-beta` | `collide-me-when-truncated-to-~1` | beta |
| `collide-me-when-truncated-to-31-gamma` | `collide-me-when-truncated-to-~2` | gamma |

All five arrive, none overwrites another, and each holds its own payload. The
29-character clamp is visible in the result: `collide-me-when-truncated-to-` is
29 characters, then `~1` makes 31. Archive order decides who keeps the plain
name. **No silent data loss**, which is what a broken BumpName would cause.

### The harness-lesson audit, 2026-08-02

The remaining unreproduced claims in BLOCKERS.md's *test-harness lessons* list
were tested. One survived, one did not; details there.

    tools/vmac/run.py -D UNC_AT_NOHIDECURSOR fixtures/derived-DDT.sit
    UNC_VMAC_PARK=344,279 tools/vmac/run.py ...      # park the pointer anywhere

`HideCursor()` is **confirmed necessary**: without it, dragging the host
pointer through the grid's cell centres flips a bit in the decoded result
(`ret = 0x04000000`), while the stock build survives the same drag. Note the
emulator window sits at (144,129) on the 800x600 Xvfb, so "grid coordinates"
must have that added — two earlier attempts parked the pointer outside the
window and proved nothing.

The `pkill -9` claim is **withdrawn**: 6 boot+kill cycles re-using one
boot-shell image leave it byte-identical (that configuration never writes to
its boot volume), and 5 cycles of a `--finder` image change its hash every
time and still boot to a healthy desktop. A fresh image per run is kept for
reproducibility — the image drifts — not for corruption.

### Working directories, 2026-08-01 (System 6.0.8 AND System 7.0.1, 4 MB)

`tools/vmac/run.py -D UNC_AT_WD` with `derived-EmpireBuilderDemo.sit`.

The application takes `SFReply.vRefNum` from Standard File and hands it to the
File Manager with `dirID` 0. On System 7 and later that refNum is a **working
directory**, not a volume — untested code since M10, and untestable by any
harness here until now, because they all extracted into a volume ROOT where
the working directory and the root are the same directory.

This build makes a real working directory over a real subfolder with
`PBOpenWD`, extracts through it exactly as `ExtractOne()` does, and counts
what landed where. No Finder, no Standard File, no screen coordinates.

| system | wdRefNum | entries | in the folder | in the root |
|---|---|---|---|---|
| System 6.0.8 | -32717 | 3 | 3 | 0 |
| System 7.0.1 | -32701 | 3 | 3 | 0 |

The refNums are negative and outside the volume range, i.e. genuine working
directory references rather than volume refNums that happened to work. The
root column is the one that matters: nothing leaked out of the folder.

### End to end from the Finder, 2026-08-01 (System 6.0.8, 4 MB, 1x)

`tools/vmac/interactive.py --e2e` with `derived-ScrollbarPattern.sit`. Unlike
every other on-Mac run here, this one leaves the **Finder** in place instead of
installing the application as the boot shell — which is the only way to launch
the application the way a person does, and the only way to launch what it
extracted. A second volume is mounted so Standard File's Drive button has
somewhere to go. Confirmed from the screenshots, in one session:

- **Launched by double-clicking it in the Finder.** SFGetFile comes up on the
  boot volume, listing `archive.sit`, `unclassic` and the System Folder.
- **Volume navigation works.** Drive switches the listing to the second volume
  (`Second`, showing only its Desktop file) and back to `Macintosh`, with the
  archive re-selected.
- **Result alert**: "Extraction complete." after ~11 s of emulated Mac Plus
  time for this small archive.
- **Quits cleanly to the Finder on Cmd-.** in SFGetFile, and the volume window
  then shows six items — the four it started with plus the archive's two
  entries.
- **The extracted application has an application icon** in the Finder, so
  type/creator and the Finder inited flag were applied.
- **The extracted application launches by double-click** and draws its splash
  screen ("Scrollbar Pattern Editor — a simple little utility by Andrew
  McGeachie"). This is the test that exercises type/creator, the inited flag
  and resource-fork integrity together: the application *is* its resource
  fork, so it could not launch if a single byte were wrong.

### Re-driven on 2026-08-01 against the streaming sink (System 6.0.8, 4 MB, 1x)

`tools/vmac/interactive.py` drives the real application under an emulator
built for authentic 7 MHz timing and photographs every step. Confirmed from
the screenshots:

- **SFGetFile** comes up listing the archive on the boot volume.
- **Progress dialog** repaints live — caught mid-run at 13% and 16%.
- **The Cancel button** stops it: "Extraction cancelled." alert.
- **Cmd-.** does the same, by the other route (the keyDown check in
  ProgressPump rather than Dialog Manager hit-testing).
- **Partial output is removed, still.** After cancelling, SFGetFile lists
  exactly `Demo Manual V1.6` — the one entry that had finished — and no
  trace of `EB Sounds`, the entry that was being written. This is the
  behaviour the streaming rewrite put at risk, seen in the file list rather
  than inferred.
- **Extraction completes**: "Extraction complete." after ~134 s of emulated
  Mac Plus time for `derived-EmpireBuilderDemo.sit` (278 KB in, 417 KB out,
  3 entries); the machine boots in ~16 s.

### Driven end to end on 2026-07-25 (System 6.0.8, Mini vMac)

Done interactively by hand, before the sink was rewritten to stream. Each
step was captured; the items above supersede the cancel-related ones.

- Application launches from the Finder; **SFGetFile** appears and lists
  the archive.
- **Open** → **progress dialog** appears and repaints live (observed
  18% → 51% → completion on a 278 KB StuffIt archive).
- **Result alert**: "Extraction complete." on success, and
  "Extraction cancelled." after a cancel.
- **Cmd-.** during extraction cancels promptly (Mini vMac maps the host
  Alt key to Command).
- **Partial output is removed.** Cancelling part-way through
  `derived-EmpireBuilderDemo.sit` (3 entries) left exactly the one entry
  that had already completed, `Demo Manual V1.6`; the entry being written
  at the time, `EB Sounds`, was deleted rather than left truncated, and
  the third was never started.
- Cancelling SFGetFile quits cleanly back to the Finder.
- **An extracted application actually runs** (re-confirmed 2026-08-01 against
  the streaming sink, scripted — see the section above).
  `derived-ScrollbarPattern.sit`
  was extracted onto an HFS volume; the Finder showed
  `Scrollbar Pattern Editor` with an application icon (so type/creator
  and the inited flag were applied), and double-clicking it **launched
  it** — splash screen, then its working pattern-editor dialog. This is
  the one test that exercises type/creator, the Finder inited flag and
  resource-fork integrity together: the application *is* its resource
  fork, so it could not have launched if a single resource byte were
  wrong.

### Automated regression harness (Linux, no interaction)
- `sh tests/run_mac_sink.sh` (in `ci.sh`): runs the ACTUAL sink through a
  mock Toolbox against the engine, byte-exact vs. the oracle manifests,
  natively (ASan+UBSan) and under `qemu-m68k` — the file-backed IO path,
  the RAM-slurp `xio_*` path, BOTH write paths (streaming, and the older
  whole-fork staging under `UNC_MAC_STAGE_WRITES`, including its
  shared-block variant), AND the Cmd-. cancel cleanup (`--cancel`).
  Authoritative proof of the sink logic on the target word size/endian.
- **`tools/vmac/run.py` — the on-Mac replay, scripted end to end.** It
  boots a stripped System 6.0.8 straight into the `-DUNC_MAC_AUTOTEST`
  build (no Finder, no simulated double-click), which finds the HFS
  volumes "In"/"Out", extracts `In:archive.sit` onto Out, reads both forks
  back through the real File Manager, CRC-32s them, and **paints the
  result to the framebuffer** (Mini vMac's disk write-back is too
  lazy/partial to read off the Out volume). The host decodes a screenshot
  (`tools/decode_grid.py`) and cross-checks against the Linux engine
  (`tools/vmac_check.py`):

      tools/vmac/setup.sh                                       # once
      tools/vmac/run.py --list tools/vmac/sample.txt            # 4 MB
      tools/vmac/run.py --list tools/vmac/sample.txt --mem 1M   # floor target

  `-D UNC_AT_CANCEL` switches it to the cancel-cleanup check: the app aborts
  once one entry has completed — so the cancel lands inside a LATER entry,
  with that file already created and already written to — and then counts
  what the volume actually holds. Files present must equal entries
  completed, i.e. the aborted entry left nothing behind. Confirmed at 4 MB
  and 1 MB on 2026-08-01 with `derived-EmpireBuilderDemo.sit` (a flat
  3-entry archive; the walk is one level deep, and the app reports the
  root's folder count so a non-flat archive cannot be mistaken for a pass).

  It is not part of `ci.sh` (downloads, an X server, minutes per fixture).
  Read `tools/vmac/README.md` before changing it — several of its
  arrangements exist to work around emulator behaviour, not by preference.
  Note that the emulator runs **all out**, so its wall-clock times say
  nothing about a real 7 MHz 68000.

Before calling the interactive app working, run this checklist in each
environment. Do not skip the System 6 / Mac Plus column — that is the
floor target and the most likely place for stack, memory and trap
assumptions to break.

## Environments

1. **Mini vMac** (Mac Plus emulation, System 6.0.8, 1 MB then 4 MB)
2. **A real Mac Plus** (System 6.0.x, 1 MB, if available)
3. **Mac OS 9** (real hardware or SheepShaver/QEMU)

## Still untested — what is NOT known to work

Everything claimed above was observed under **emulation only** — Mini
vMac for System 6 and 7, QEMU for Mac OS 9. Nothing below is a known
failure; it is simply unverified, and should not be described as
working until someone runs it.

Two things, specifically, and neither can be closed from here:

1. **Real 68k hardware** — any physical Mac Plus, SE or Classic.
2. **A real Mac Plus with a real 1 MB of RAM.** The 1 MB figures in
   FORMATS.md come from an emulated 1 MB machine with a stripped System
   Folder; a real one has INITs, a real ROM's own memory use, and less
   free heap than any number recorded here.

(**Mac OS 9 on PowerPC** was the third entry here until 2026-08-02.
`tools/vmac/os9.py --launch` now boots it, launches the application
under the 68LC040 emulator and checks both forks of what it writes; see
below for what that did and did not close. Real PowerPC silicon is
still untouched.)

### Real 68k hardware (Mac Plus / SE / Classic, System 6.0.x)

Never run on physical hardware. Mini vMac emulates a Mac Plus faithfully
enough for the File Manager, Memory Manager and QuickDraw paths used
here, but it is not the same as silicon. Specifically unverified:

- **Real 68000 timing and the floppy-only I/O path.** Every on-Mac test
  so far used emulated disks backed by host files; a real 800K floppy is
  orders of magnitude slower and can return media errors mid-write that
  the emulator never produces. The per-entry error path has never seen a
  genuine I/O failure.
- **Actual free memory on a stock 1 MB Plus.** The 1 MB figures in
  FORMATS.md come from an emulated 1 MB machine with a clean System
  6.0.8 and no INITs. A real machine with a Chooser extension or two has
  less, and the `FreeMem()`-derived budget will land lower than recorded.
- **The `SetApplLimit` stack bump against a real 8 KB stack**, and
  whether the engine's ≤4 KB call-chain bound holds with the real
  ROM's own stack use underneath it.
- **Address-error behaviour.** x86 and the emulator both tolerate some
  unaligned access patterns that a real 68000 traps on. CI's
  `-fsanitize=alignment` and the qemu-m68k mock are the current
  defence; neither is the actual CPU.
- Whether the app's memory use leaves the Finder able to relaunch
  afterwards (`FreeMem()` returning to its starting value is checked
  in-app, not across a real reboot cycle).

### Mac OS 9 on PowerPC

**Run, and passing, since 2026-08-02** — the 68k binary executes under the
68LC040 emulator on Mac OS 9.2. Results in FORMATS.md, the harness in
`tools/vmac/README.md`, the history in BLOCKERS.md.

    tools/vmac/os9.py --setup                                  # once
    tools/vmac/os9.py --list tools/vmac/os9sample.txt \
                      -o <dir> --launch                        # 13/13 byte-exact
    tools/vmac/os9.py fixtures/foo.sit -o <dir> --hfsplus      # onto HFS+

The Finder is driven from the **keyboard**: the pointer does not work in this
guest (measured — five mouse primitives at exactly 0.0000 effect). Results come
back through the disk image, not the screen: `at_report()`'s 1bpp grid is
invisible on a 32-bit screen, so `at_report_file()` writes the values and every
output name to the plain-HFS input volume.

Closed by these runs: the `WaitNextEvent` branch, Standard File and the Toolbox
File Manager layer under a real Process Manager, `SFReply.vRefNum` as a
System 7+ working directory, extraction onto HFS+, and the `SIZE` partition
(a 600 KB partition declines a 656 KB entry at 35.5 KB peak — the same figure
System 7 gives, on a 512 MB machine).

Still unverified on OS 9:

- **Names HFS+ permits that HFS does not.** Through the classic File Manager a
  68k application is capped at 31 characters on either filesystem, so these may
  be unreachable from this binary at all — unproven either way.
- **Files larger than the HFS 2 GB cap**, and the engine's 32-bit arithmetic
  against them.
- **MacRoman filename display and 8-bit characters** above System 6 — the
  bytes are checked, the appearance is not.
- **Real PowerPC silicon.** As with 68k, an emulator is not hardware.


## Setup

- Build: see mac/CMakeLists.txt header. Import `unclassic.dsk` (or the
  .bin) into the target system; copy the application to the boot disk.
- The bootstrap distribution is built by `tools/make_dist.sh`, which builds
  the application rather than picking up an old one, and checks that the
  800K image and the MacBinary carry the same resource fork byte for byte.
  **`dist/unclassic.dsk` mounts on System 6.0.8** — confirmed 2026-08-01 by
  `tools/vmac/mountcheck.py dist/unclassic.dsk`, which boots the stock system
  with the image attached and photographs the desktop; the `unclassic` volume
  appears below the boot disk. hfsutils reading an image is not evidence that
  a Mac will mount it.
- Bring test archives over as MacBinary (.bin) files — ImportFl or
  similar drops the wrapper; unclassic itself can unwrap MacBinary if
  the file arrives with a flattened fork.

## Checklist (every environment)

Launch & UI
- [ ] Application launches; SFGetFile appears immediately.
      (System 6: confirmed 2026-08-01, launched by double-click from a real
      Finder desktop — `tools/vmac/interactive.py --e2e`.)
- [ ] Cancel in SFGetFile quits cleanly to Finder.
      (System 6: confirmed 2026-08-01 by the same run, via Cmd-.)
- [ ] Standard File's Drive button switches volumes and back.
      (System 6: confirmed 2026-08-01 with a second volume mounted.)
- [ ] During extraction the progress dialog shows and repaints when
      covered/uncovered (System 6: by desk accessories).
- [ ] Cancel button stops extraction promptly (< 1 s); already-completed
      entries remain, the entry being written is deleted rather than left
      truncated, and the app returns to SFGetFile without damage.
- [ ] Cmd-. behaves exactly like the Cancel button.
      (Both re-confirmed against the streaming sink on 2026-08-01 by
      `tools/vmac/interactive.py`, at authentic Mac Plus speed — see below.)
- [ ] Under MultiFinder / System 7+ / OS 9: the app yields (other apps
      stay responsive while extracting; WaitNextEvent path).

Extraction correctness (use archives whose contents are known from the
Linux differential suite)
- [ ] A classic .sit (methods 2/13 mix): all files appear, correct
      sizes, type/creator/icons correct in Finder, dates preserved.
- [ ] A .cpt with nested folders: folder tree recreated.
- [ ] A .hqx and a .bin: single file with both forks; ResEdit (or
      Get Info) confirms the resource fork is intact.
- [ ] A file whose name contains '/': appears with '/' in Finder
      (engine ':' undone).
- [ ] Name collision: extracting the same archive twice produces
      "name~1" copies, no overwrite, no crash.
- [ ] An archive with a >31-char member name (zip/tar): truncated to
      31 chars, extraction completes.

Resource limits (Mac Plus / 1 MB, System 6)
- [ ] Small .sit extracts with ~700 KB free heap.
- [ ] A StuffIt 5 (Arsenic) archive fails **per entry** with a clean
      alert — no crash, no hang, no heap corruption on return.
- [ ] Extraction of a large archive (> free memory in output size)
      streams: memory usage stays flat (About This Mac / heap watch).
- [ ] After several consecutive extractions FreeMem() returns to the
      same value (no leaks; MacsBug `hc` clean if available).

Corrupt input
- [ ] A truncated .sit: per-entry error alert, app stays alive.
- [ ] A random file renamed .sit: "could not be extracted" alert.

Mac OS 9 specific
- [ ] Long extraction in the background while another app is frontmost.
- [ ] Filenames with 8-bit MacRoman characters display correctly.

## Known deviations to verify/fix at runtime

- SFReply.vRefNum is a working-directory reference on System 7+; the
  HOpen/HCreate calls pass dirID 0 with it. Verify extraction lands
  next to the archive on both System 6 and 9.
- The progress dialog uses DialogSelect without a filterProc; verify
  the Cancel button highlights on click.
- 'SIZE' partition is 4 MB preferred / 400 KB minimum. Arsenic (StuffIt 5
  method 15) needs 0.64–2.6 MB depending on block size, so on a small
  machine it refuses per entry rather than the app refusing to launch.
  That is the documented tier, not a bug — see FORMATS.md.
