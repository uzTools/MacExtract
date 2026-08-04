# BLOCKERS.md

## Status

**No open blockers.** The engine and Linux CLI (M0–M9) were never affected by
anything in this file. The Retro68 Mac shell runs and extracts byte-exact on
every system the project claims:

| tier | result |
|---|---|
| System 6.0.8, 4 MB Mac Plus (Mini vMac, a true 68000) | 44/44 sampled fixtures |
| System 6.0.8, **1 MB** — the floor target | 41/44; the three are StuffIt 5 budget refusals, each missing one entry |
| System 7.0.1, 4 MB | 44/44 |
| Mac OS 9.2 (QEMU PowerPC, 68LC040 emulation) | 13/13, plus HFS+ and the `SIZE` partition |

Per-fixture tables are in FORMATS.md, re-run instructions in
`tools/vmac/README.md`, and the on-demand experiments in MANUAL_TESTS.md.

**Nine claims this file used to assert have been withdrawn, and one
confirmed.** (This count read "seven" while the table held eight; corrected
2026-08-03.) They are collected at the end, under *Withdrawn claims*, and kept
on purpose, because two mechanisms keep finding the next one:

- **A live claim sitting next to an already-withdrawn one.** Twice, worth
  39/44 → 40/44 at the floor target once.
- **Two files disagreeing.** Once, and it is how the 512 KB block claim below
  fell — the disproof was already written down elsewhere in this repository.

Nothing above this line depends on them.

---

## What is true, and load-bearing

### How the Mac shell is verified

The autotest build (`-DUNC_MAC_AUTOTEST`) CRC-32s BOTH forks after reading them
back through the real File Manager and paints the aggregate to the framebuffer;
the host decodes a screenshot and compares against the same engine's Linux
output (`tools/vmac_check.py`). Extracted metadata (type/creator, inited-flag
cleared) is confirmed on-Mac, so an extracted `APPL` launches by double-click.

Since 2026-08-02 the Out volume can also be read directly
(`run.py --keep-disks` + `tools/vmac/checkdisk.py`), which adds the one thing
the grid cannot carry: **names**. 44/44 with names and folder structure
included. The grid is kept — it needs nothing of the volume and reports
liveness and setup failures a disk cannot.

The off-Mac blind spot is real: the qemu-m68k mock (`tests/run_mac_sink.sh`)
calls the sink directly and never touches the Toolbox glue, so only Mini vMac
exercises that layer.

### The fix that unblocked M10 — and what is still unknown about it

Driving the File Manager through explicit HFS param blocks — `PBHOpenSync` /
`PBHOpenRFSync` / `PBHCreateSync` / `PBHDeleteSync` via `MyOpenFork` /
`MyHCreate` / `MyHDelete`, each zeroing the whole `HParamBlockRec` first —
unblocked everything at once and is what ships.

**Why it worked is not established.** The original attribution (a broken
Retro68 `HOpen`) was disproved; see *Withdrawn claims*. The likeliest remaining
explanation is that the helpers zero the entire param block where the pre-fix
code passed partly-uninitialised state, but that has never been reduced to a
reproduction either, so it is written here as a guess and not as a finding.
It is not being chased: the app is verified byte-exact as it stands.

The one upstream finding that survived: **both `OpenDF` and `HOpenDF` return
`paramErr` on System 6**, because the `_OpenDF` trap is System 7 and neither
has a fallback — `FSOpen`, in the same glue file, does. Written up in
`tools/retro68-hopen-repro/ISSUE.md`, **deliberately not filed**; the
maintainer will post it from his own account.

### Replacing the Finder means nothing mounts disks

The autotest application is installed as the boot **shell** (boot blocks offset
0x1A, `Finder` → `unclassic`), so it is the only thing running, and a disk
inserted after startup never mounts: the disk-inserted event is posted, but
volumes are mounted when somebody asks, and normally that somebody is the
Finder. Measured — the volume walk saw exactly one volume after 30 s, with both
images present and both mounting fine when the Finder was left as shell.

Fixed by `PBMountVol` on each drive number before looking for the volume
(`MountAllDrives`). Autotest build only; the interactive application uses
Standard File, which does its own disk handling.

### `HideCursor()` before drawing the grid — CONFIRMED, with a reproduction

The only claim in the old *test-harness lessons* list to survive its audit.
Built without it (`UNC_AT_NOHIDECURSOR`) and with the host pointer dragged
through the grid's cell CENTRES, the decoded result comes back
`ret = 0x04000000` — one flipped bit, i.e. one cell stamped over by the
cursor's saved background. The stock build survives the same drag. Reproduced
twice.

Two things had to be right before the test meant anything, and neither was at
first: the pointer must be inside the emulator window, which sits at (144,129)
on the 800x600 Xvfb, and the drag must cross cell centres, because a path
between rows disturbs nothing. Both early attempts "passed" while testing
nothing. `UNC_VMAC_PARK` overrides the parking position, which is how this was
measured; the harness's own parking is belt-and-braces given `HideCursor()`,
and costs one `xdotool` call, so it stays.

### Mac OS 9: the boot volume is HFS+ inside an HFS wrapper

    wrapper MDB signature   0x4244 'BD'
    drEmbedSigWord          0x482B 'H+'
    embedded volume header  'H+' at byte 966656 of the partition

hfsutils mounts the WRAPPER, whose root holds exactly one file,
`Where_have_all_my_files_gone?` — Apple's placeholder. This environment has no
HFS+ writer at all (no hfsprogs, no kernel module), so the application cannot
be placed in `System Folder:Startup Items:` offline and the Finder has to be
automated. That constraint still stands.

It also gives a free, unambiguous test: after extracting onto that volume, if
the output were on plain HFS it would be visible in the wrapper. It is not —
which is how the HFS+ runs prove where their output landed, rather than
inferring it from a signature word the classic File Manager reports as `'BD'`
for compatibility anyway.

### Mac OS 9 is driven by the keyboard, because the pointer does not work

`tools/vmac/os9probe.py` measured eleven input primitives in one boot: all five
mouse probes changed **exactly 0.0000** of the watched rectangle, and locating
the cursor by diffing screenshots found it only ever at (0,0) and (1023,767) —
never at any of three requested positions. All five keyboard probes worked.

So `launch_by_keyboard()` types to select and Cmd-Downs to open: no
coordinates, no double-click threshold. It worked first try, all the way to an
extraction. The mechanism behind the failure is *not* established — the natural
reading is that OS 9 treats the tablet's absolute reports as relative deltas,
but that has no reproduction and is written here as a guess.

Getting there took five boots and three published explanations, all of them
about *clicking*: a 0.9 s double click, a relative ADB pointer fed absolute
coordinates, and the Setup Assistant holding the foreground. Each was a real
defect, each was fixed, none was the answer — because clicking was never going
to work. **Measure the primitive before theorising about the compound.**

### The Mac OS 9 harness was damaging its own disk image

Two defects in `os9.py`, the second hiding the first: it booted the MASTER
image in place (OS 9 writes to its boot volume as a matter of course, and a
killed QEMU leaves it dirty), and it never hashed the image, so the drift was
invisible. Confirmed, not assumed: the local copy did not match archive.org's
published SHA-1, and the volume read back hardware-locked with the
unmounted-cleanly bit clear.

Fixed: the published SHA-1 is verified before every run, the master is copied
to a throwaway before booting, and `--setup --force` re-fetches. The same
lesson had been in this file for Mini vMac since M10 and was simply never
carried across.

### Timing on a 7 MHz Mac Plus — measured

Absolute 1x timings exist for every format sampled (FORMATS.md).
`run.py --emu mv-4M-1x` separates boot from extraction, because the app paints
its "alive" grid before touching a disk. Small archives extract in under 5 s on
a machine that takes ~10 s to boot; `derived-EmpireBuilderDemo.sit` (278 KB in,
417 KB out) takes ~134 s, and `macburger-helper.hqx` 150 s.

What settled it was `UNC_AT_PROGRESS`, which paints the engine's byte counter
into the grid as it runs, so a run that has *not* finished can still be
interrogated:

    t+~7 min     49,152 / 306,651   (16%)
    t+~9 min     98,304 / 306,651   (32%)
    t+11 min    303,104 / 306,651   (99%)   <- 205 KB in the last 100 s

The rate is wildly non-uniform, so every fixed timeout expired during the slow
phase and looked exactly like a hang. **A timeout expiring is not a
measurement** — it reports that something did not finish inside a number
somebody picked, and nothing about why. That cost three wrong write-ups; the
instrument that answered it was twenty lines over a callback the engine has had
since M0.

### Detect-only gap — RESOLVED

DiskCopy 4.2 was named in `unc_sniff` but never detected, because no reference
was available offline and rule #3 forbids inventing a format from memory. A
reference was obtained (`reference/notes/DiskCopy42.md`, DiscFerret wiki) and
the probe is real: it matches a synthetic 800K GCR image and a real one, 0
false positives across 803 fixtures. Still detect-only — disk images are out of
scope for v1.

---

## Withdrawn claims

Kept deliberately. Twice now a live claim has been re-tested *because* it sat
beside an already-withdrawn one in the same list — the archive RAM slurp was
found that way, and it was worth 39/44 → 40/44 at the floor target. Deleting
these would remove the smell that finds the next one.

Each entry is: what was claimed, what disproved it, and what it cost.

| claim | disproved by | withdrawn |
|---|---|---|
| Retro68's `HOpen` glue is broken on System 6 | `tools/retro68-hopen-repro/`, 10 cases | 2026-07-25 |
| Three non-relocatable staging blocks bomb the Memory Manager | `UNC_AT_SEPARATE_BLOCKS` | 2026-07-25 |
| QuickDraw bombs after File Manager activity | `tools/quickdraw-repro/`, 12 configurations | 2026-08-01 |
| `derived-RWAsm_Folder.sit` fails on a 4 MB Mac Plus | committed harness re-run | 2026-07-25 |
| The OS 9 boot volume is plain HFS | `drEmbedSigWord` = `'H+'` | 2026-08-02 |
| Interleaved reads and writes on one volume return zeros | `UNC_AT_INTERLEAVE`, 3 read shapes | 2026-08-02 |
| Mini vMac's write-back is lazy and partial | `checkdisk.py`, 44/44 off the disk | 2026-08-02 |
| `pkill -9` never flushes; boot+kill corrupts the image | 11 boot+kill cycles | 2026-08-02 |
| The three 1 MB StuffIt 5 refusals each fill a 512 KB block | instrumenting `numbytes` where the transform vector is allocated | 2026-08-03 |

**Retro68's `HOpen` glue.** Claimed to return `noErr` without writing back the
refNum, and recorded as M10's root cause in commit `22e806b`. A standalone
reproduction run against the same Retro68 build on the same System 6.0.8 Mac
Plus does not reproduce it: across ten cases `HOpen` writes the refNum every
time and agrees exactly with a hand-filled `PBHOpenSync` — with a real vRefNum,
a non-zero dirID, write permission, a poisoned stack, and a cross-volume open.
**Cost:** the true cause of the M10 saga is still unknown, and every conclusion
drawn during that period had to be re-tested (the next three entries).

*A second error inside the same write-up*: it said `HOpenDF` was the odd one out
"unlike the non-hierarchical `OpenDF` beside it". Wrong — the fallback is in
`FSOpen` and `OpenDF` is broken identically, settled by adding case 11 to the
reproduction. Twice, a claim about this one source file was wrong because the
file was read rather than run.

**Three non-relocatable staging blocks bomb the Memory Manager.** Re-tested with
the glue fixed: `UNC_AT_SEPARATE_BLOCKS` forces two separate `NewPtr` staging
blocks plus the archive buffer, and a two-fork file extracts byte-exact with no
crash. The shared-block staging is retained as harmless and marginally more
heap-friendly, but its stated justification was wrong. **Cost:** none beyond
the write-up.

**QuickDraw bombs after File Manager activity.** `tools/quickdraw-repro/` runs
`NewWindow`+`EraseRect`+`DrawString` before and immediately after File Manager
work, writing its log by poking the framebuffer so the report cannot depend on
what is being tested. Every call succeeded with `MemError() == 0` across twelve
configurations, including `GetNewDialog`, `EraseRect` on the Window Manager
port, eight interleaved rounds, and while holding a 200 KB non-relocatable
`NewPtr`. Both proposed explanations fail too: `MaxApplZone` and 12x
`MoreMasters` were already present when the claim was made and *removing* them
does not produce the failure; and the same binary double-clicked from a normal
Finder desktop behaves identically. **Cost:** as stated it meant the shipped
interactive build was broken — SFGetFile, then a progress dialog, then an alert
is exactly File Manager followed by QuickDraw — and nobody noticed, because it
was filed under *harness lessons*. **Filing a hypothesis under "lessons" hides
it.**

**`derived-RWAsm_Folder.sit` fails at 4 MB.** Does not reproduce: all 38
entries byte-exact at the same 643.2 KB peak the failing run reported. What
differed cannot be established, because the harness that produced the old
numbers was never committed and its working directory is gone. Closed as
not-reproducible, not as fixed. **Cost:** it is why `tools/vmac/` is now
committed and fetches its copyrighted inputs by URL rather than living in an
untracked directory.

**The OS 9 boot volume is plain HFS.** A signature was read at a fixed offset
(`0x4244 'BD'`) and the conclusion drawn without checking `drEmbedSigWord`,
which says `'H+'`. The proposal built on it — drop the app into Startup Items
with hfsutils and skip Finder automation — is not merely untried but
impossible here, since nothing in this environment can write HFS+. **Cost:** a
day's plan; and the same mistake shape (reading a field at an offset instead of
asking what qualifies it) is why the HFS+ runs now prove their output volume by
mounting the wrapper instead of trusting a signature.

**Interleaved reads and writes on one volume return zeros.** This justified
reading the whole archive into RAM before extracting. `UNC_AT_INTERLEAVE` reads
one file three ways on one volume — undisturbed, in chunks with a fresh file
created and written between every chunk, and again seeking with `SetFPos`
before every read — and gets an identical CRC every time, at 4 MB and 1 MB, on
two fixtures. **Cost:** the archive buffer came out of the engine's budget
before extraction began, so on the 1 MB floor target the archive's own size
decided which StuffIt 5 entries were affordable. Removing it took the sample
from 39/44 to 40/44, and three of the four remaining failures from refusing
every entry to extracting most of them.

**Mini vMac's write-back is lazy and partial** — "it can commit one fork of a
file but not the other", so results could not be read off the Out volume. The
whole sample was replayed with `--keep-disks` and every Out volume read back:
**44/44 byte-exact, both forks, names and folder structure included.**
`derived-RWAsm_Folder.sit` alone is 38 files and **73 forks**, i.e. dozens with
both forks non-empty — exactly the case the claim named as impossible. An
8-bit folder name, a MacRoman `Appé` and a `.DS_Store` survive too. **Cost:**
the highest of any of these. It forced verification through the framebuffer
grid, which carries a count, two summed CRC-32s and two summed lengths — and a
summed CRC cannot carry a name. That is why the System 6 and 7 tiers never
checked an output NAME, and why a real defect in the gzip/.Z fallback name sat
in the corpus for weeks until the Mac OS 9 harness, which reads its volume,
caught it on its first sweep.

**`pkill -9` never flushes; repeated boot+kill corrupts the boot image.**
Neither half survives. *Flushing:* the whole sample was read back off its Out
volumes after exactly that kill, and in the `--finder` configuration the boot
image's SHA-1 changes on every cycle — something is plainly being written.
*Corruption:* 6 boot+kill cycles re-using one boot-shell image leave it
**byte-identical**, because that configuration never writes to its boot volume
at all, so there is nothing to damage; 5 more cycles of a `--finder` image
change the hash every time and still boot to a healthy Finder desktop.
**Cost:** none — and the practice it recommended is kept, for the better reason
the OS 9 master-image incident taught: the image DRIFTS, so reusing it makes
two runs months apart incomparable. That is a reproducibility argument, not a
corruption one.

**The three 1 MB StuffIt 5 refusals each fill a 512 KB block.** OPEN_ITEMS.md
gave this as the reason the last three sampled fixtures cannot pass at the
floor target: "those three entries each really do fill a 512 KB block, and
512 KB + 2 MB of transform vector does not fit in ~700 KB", closing the item as
needing "a fundamentally different inverse BWT". Instrumenting `numbytes` at
the point `sit_arsenic.c` sizes the transform vector says otherwise —
**none of the three fills a 512 KB block, and one holds under a quarter of
it**:

| fixture | largest block fill | capacity by doubling | peak |
|---|---|---|---|
| `derived-Library_ISBN_Barcoder.sit` | 323,384 B | 512 KB | 1,854,208 B |
| `derived-a2basic.dmg.sit` | 197,515 B | 256 KB | 1,088,588 B |
| `derived-Troi-ClipSave-Plug-in1.1.sit` | **124,637 B** | 128 KB | 666,004 B |

MEASURED 2026-08-03. The peak model `~35 KB parser + capacity + 4 x fill`
reproduces all three measured peaks to within a rounding step, so the fills are
confirmed by two independent routes.

**Cost: the largest still outstanding.** The false figure made the remaining
gap look like a 3x shortfall requiring a redesign, when `Troi-ClipSave`'s
refused entry needs about **650 KB against the ~700 KB a 1 MB Mac Plus has
free**. Nobody re-derived it for a day because the item read as closed. Two
consequences follow directly and neither needs a new algorithm: the block
capacity is left at the doubled size and never trimmed to the fill (Library_ISBN
holds 323 KB in a 512 KB allocation, 196 KB of it dead), and the 4x transform
vector — 487 KB, 772 KB and 1,263 KB respectively — is now visibly the only
dominant term left.

**Why it survived is the part worth keeping.** The disproof was already in this
repository. DECISIONS.md, in the Arsenic entry, says that same fixture's blocks
"really do hold ~316 KB" — correct, measured, and sitting one file away from
the claim it contradicts. CLAUDE.md already says that where these files
disagree it is a bug rather than a choice; what was missing was anyone reading
them against each other. **A cross-file contradiction is a disproof nobody has
collected yet.**

Why `Troi-ClipSave` still refuses at 650 KB when ~700 KB is documented as free
is NOT established — it is one run to find out, and it is a different and much
smaller question than the one the withdrawn claim posed.

### Corrected figures and superseded write-ups

- **The OS 9 boot time** was recorded as "about four minutes", then "20-45
  minutes". An idle host settles the desktop in **~110 s**, measured
  repeatedly. Both earlier figures were host load written down as a property of
  the guest. `settle()` now waits for the screen to stop changing *and* for the
  Finder's menu bar, so no figure is needed.
- **`macburger-helper.hqx` was written up three times as an anomaly** — host
  contention, then "the on-Mac path scales badly", then the autotest's CRC
  read-back. It simply takes 150 s; see *Timing* above.
- **`popper-1.7.tar.Z` and `PCCTS.tar.gz` at 1 MB** were root-caused and fixed:
  the sink used to accumulate each whole fork in a `NewPtr` block, so the shell
  needed `archive + engine peak + largest output fork`, and these two have the
  sample's largest output forks. Streaming writes fixed it; the sweep went
  37/44 → 39/44. The old path stays buildable as `UNC_MAC_STAGE_WRITES`.
- **The "all-black screen crash"** chased during the M10 saga was a harness
  artifact: a launcher that backgrounded the emulator and exited took it down
  by SIGHUP, and a dead X window reads as pure black.
- **The `mio_seek` eofErr fix** is correct and kept, but it was not the M10
  blocker either.
