# BLOCKERS.md

## M10 Mac shell — RESOLVED (extraction verified byte-exact on real System 6)

**Status:** RESOLVED, no open blockers. The Retro68 Mac shell runs on a
real System 6.0.8 / 4 MB Mac Plus under Mini vMac (a true 68000) and
extracts real Classic-Mac files correctly — single-fork, two-fork, and
multi-file — with both forks **verified byte-exact ON THE MAC ITSELF**. The
engine and Linux CLI (M0–M9) were never affected.

### The fix (and a WITHDRAWN root cause)

**Fix that worked:** drive the File Manager through explicit HFS param
blocks — `PBHOpenSync` / `PBHOpenRFSync` / `PBHCreateSync` /
`PBHDeleteSync` via the helpers `MyOpenFork` / `MyHCreate` / `MyHDelete`,
each zeroing the whole `HParamBlockRec` before filling it in. This
unblocked everything at once and is what ships.

**WITHDRAWN 2026-07-25 — "Retro68's `HOpen` glue is broken on System 6:
returns `noErr` but never writes back the refNum."** This was recorded here
and in the commit message for 22e806b as the root cause. It is **wrong**.
A standalone minimal reproduction (`tools/retro68-hopen-repro/`) was built
to hand upstream and, run on the same System 6.0.8 / Mac Plus / Mini vMac
setup against the same Retro68 build, it does not reproduce: across ten
cases `HOpen` writes the refNum every time and agrees exactly with a
hand-filled `PBHOpenSync` — including with a real vRefNum, a non-zero
dirID, write permission, a deliberately poisoned stack, and a cross-volume
open (the shape this app actually uses). See that directory's README for
the result table.

So switching to explicit param blocks fixed the app for some *other*
reason — most likely that `MyOpenFork`/`MyHCreate` zero the entire param
block, whereas the surrounding pre-fix code passed partly-uninitialised
state. **The true root cause is not established.** It is not being chased
further: the app is verified byte-exact on-Mac as it stands, and the honest
statement is "the param-block rewrite fixed it; we do not know precisely
which field mattered."

The only real (and minor) upstream finding that survived is that **both
`OpenDF` and `HOpenDF` return `paramErr` on System 6**, because the `_OpenDF`
trap is System 7 and neither has a fallback. `FSOpen`, in the same glue file,
does have one. Written up in `tools/retro68-hopen-repro/ISSUE.md`; not filed
(no GitHub credentials in this environment — an unauthenticated POST to the
issues API returns 401).

That write-up said, until 2026-08-01, that `HOpenDF` was the odd one out
"unlike the non-hierarchical `OpenDF` beside it". **Wrong**: the fallback is in
`FSOpen`, and `OpenDF` is broken in exactly the same way. Case 11 was added to
the reproduction to settle it on the machine instead of by reading the file,
and plain `OpenDF` returns `paramErr` too. Twice now, a claim about this one
source file has been wrong because it was read rather than run.

The off-Mac blind spot is still real: the qemu-m68k mock
(`tests/run_mac_sink.sh`) calls the sink directly and never touches the
Toolbox glue, so only Mini vMac exercises that layer at all.

### How it's verified (on the Mac, not just off it)

The autotest build (`-DUNC_MAC_AUTOTEST`) CRC-32s BOTH forks after reading
them back through the real File Manager and paints the aggregate straight
to the framebuffer; the host decodes a screenshot and cross-checks against
the same engine's Linux output (`tools/vmac_check.py`). Result: **44/44
sampled fixtures byte-exact across all twelve formats at 4 MB, 39/44 at
1 MB**; the extracted metadata (type/creator, inited-flag cleared) is
confirmed on-Mac so an extracted `APPL` launches by double-click. The whole
harness is committed in `tools/vmac/` — see FORMATS.md for the tables and
`tools/vmac/README.md` for how to re-run it.

### Earlier "root causes" that turned out to be confounded

Every open silently failed for the whole of the "two-fork crash"
investigation, so it drew wrong conclusions. (The cause of those failures is
the withdrawn attribution above; what is certain is that they happened.)
Corrected here:

- **"THREE non-relocatable staging blocks bomb the Memory Manager" — FALSE.**
  Re-tested with the glue fixed (`UNC_AT_SEPARATE_BLOCKS` forces two
  separate `NewPtr` staging blocks + the archive buffer = three blocks):
  a two-fork file extracts **byte-exact, no crash**. The block count was
  never the problem. The staging code stages both forks in one shared
  block anyway — retained as harmless and marginally more heap-friendly —
  but its "avoids the 3-block bomb" justification was wrong.
- **The `mio_seek` eofErr fix and the RAM-slurp of the archive** are kept
  (both are correct and the mock exercises them) but were not the blocker;
  the real Mac app uses the RAM-slurp `xio_*` path regardless.
- The dramatic "all-black screen crash" seen while chasing a supposed
  large-resource-fork bug was a **test-harness artifact** — a launcher that
  backgrounded the emulator and exited took the emulator down with it
  (SIGHUP), and a dead X window reads as pure black. Booting the emulator
  as a child of the long-running batch fixed it; the fixture extracts fine.

### Replacing the Finder has a consequence: nothing mounts disks

The autotest application is installed as the boot **shell** (the boot
blocks' shell name, offset 0x1A, is rewritten from `Finder`), so it is the
only thing running. A disk inserted after startup then never mounts: the
disk-inserted event is posted, but the volume is only mounted when somebody
asks, and normally that somebody is the Finder. Measured, not assumed — the
volume walk saw exactly one volume (the boot disk) after 30 seconds of
waiting, with the emulator's In and Out images both present and the same
images mounting fine when the Finder was left as shell.

Fixed by calling `PBMountVol` on each drive number before looking for the
volume (`MountAllDrives`). This affects only the autotest build; the
interactive application relies on Standard File, which does its own disk
handling.

### Real test-harness lessons (not app bugs)

- **Mini vMac's disk write-back to the host image is lazy and PARTIAL** —
  it can commit one fork of a file but not the other — so results cannot be
  read off the Out volume. Verification is done ON-SCREEN instead (the app
  paints results to the framebuffer, read from a screenshot).
- ~~**QuickDraw drawing (NewWindow/EraseRect) bombs "out of memory" when
  called after any File Manager activity**, despite megabytes free — so the
  result grid is written by poking `qd.screenBits` directly.~~ **WITHDRAWN
  2026-08-01 — does not reproduce; see the section immediately below.** It
  was never a harness lesson either: it was filed as one, which is how a
  claim that would have meant the shipped interactive build was broken sat
  here unexamined.
- **`HideCursor()` before drawing**, or the cursor's saved background
  stamps the desktop pattern back over the grid; park the host pointer off
  the grid before the app draws.
- `pkill -9` never lets the emulator flush; use a fresh pristine boot image
  per run (repeated boot+kill cycles corrupt System 6's writes to it).

### "QuickDraw bombs after File Manager activity" — WITHDRAWN 2026-08-01

**It does not reproduce, in any of twelve configurations.** The minimal
reproduction is `tools/quickdraw-repro/` — a standalone Retro68 application
that runs `NewWindow` + `EraseRect` + `DrawString` before File Manager work
and again immediately after it, on the same System 6.0.8 / Mac Plus / Mini
vMac setup, and writes its log by poking the framebuffer through its own 5x7
font so that the report cannot depend on the thing being tested. Every
QuickDraw call succeeded with `MemError() == 0`, including `GetNewDialog` (the
route the shipped application actually takes), `EraseRect` on the Window
Manager port (named in the claim), eight interleaved rounds, and the same
while holding a 200 KB non-relocatable `NewPtr`. The table is in that
directory's README.

Both proposed explanations are also disproved:

- **Master-pointer heap fragmentation.** `MaxApplZone` and 12x `MoreMasters`
  were already in the application when the claim was made (`a707db3`), so
  their absence cannot explain it — and *removing* them does not produce the
  failure either. With no `MaxApplZone` the heap is ungrown and `FreeMem()`
  reports **2 KB**, and QuickDraw still allocates every window cleanly,
  because the Memory Manager grows the zone on demand.
- **Running as the boot shell in place of the Finder.** The same repro
  binary, double-clicked from a normal Finder desktop (`mkboot.py --finder`),
  behaves identically. On System 6 without MultiFinder, launching an
  application unloads the Finder anyway, so the heap it inherits is nearly the
  same — the two arrangements' `FreeMem()` figures agree.

Independently: the shipped application itself has now been driven end to end
from a real Finder desktop (`tools/vmac/interactive.py --e2e`, MANUAL_TESTS.md)
— SFGetFile, a progress dialog and two alerts, all after the File Manager has
opened, read and written files — with no sign of the reported failure.

Where the claim came from cannot be established: it entered in commit
`22e806b`, during the period this file records as confounded (every File
Manager open was silently failing), and that working directory is gone. The
lesson is the one already in CLAUDE.md — a root cause that has never been
reduced to a minimal reproduction is a hypothesis, not a finding — with a
corollary: **filing a hypothesis under "test-harness lessons" hides it.** This
one implied the shipped interactive build was broken (SFGetFile, then a
progress dialog, then an alert, is File Manager followed by QuickDraw) and
nobody noticed, because it was written down as a note about the harness.

`at_report()` still pokes the framebuffer and still should — it needs no
allocation, cannot fail, and is the only channel that survives a bomb — but
that is now its stated reason.

### The Mac OS 9 harness was damaging its own disk image

Found 2026-08-02, while looking for a way to launch the application on OS 9
without driving the Finder. Two defects in `tools/vmac/os9.py`, and the second
hid the first:

- **It booted the MASTER image in place** (`Qemu([DISK, xfer], ...)`). Mac OS 9
  writes to its boot volume as a matter of course — Desktop DB, temporary
  items, the "unmounted cleanly" flag — and a QEMU process that is killed
  rather than shut down leaves the volume dirty. So every run quietly altered
  the one artifact the harness depends on.
- **It never hashed the image.** `setup.sh` fetches everything by URL *and
  verifies by SHA-256*; `os9.py` only checked that the file existed. With no
  hash, the drift was invisible.

This lesson was already in this file for Mini vMac — "use a fresh pristine boot
image per run (repeated boot+kill cycles corrupt System 6's writes to it)" —
and `tools/vmac/run.py` has copied its boot image since M10. It was simply
never carried across to the OS 9 harness.

Confirmed rather than assumed: archive.org publishes a SHA-1 per file, and the
local image did not match it (`2eb3f07c…` against the published `a6e39e04…`).
The volume also reads back flagged hardware-locked with the
"unmounted-cleanly" bit CLEAR, which is what an interrupted boot leaves behind.
Some of that drift is mine — an `hmount` during the same investigation opened
it read-write — and the rest predates this session; the point is that nothing
could tell the two apart, which is the actual defect.

**Fixed:** `os9.py` now records the published SHA-1, verifies before every run,
copies the master to a throwaway before booting, and `--setup --force`
re-fetches. The damaged image was re-downloaded and re-verified.

### Mac OS 9 — RESOLVED: the application runs there, driven by the keyboard

(The boot volume is HFS+ and offline writes to it are impossible here, which is
why the Finder had to be automated at all. That part still stands.)

**This section replaces one written earlier the same day that said the volume
was "plain HFS, signature BD, not HFS+" and proposed dropping the application
into `System Folder:Startup Items:` with hfsutils to avoid Finder automation.
That was wrong**, and wrong in the way this repository keeps being wrong: a
signature was read at a fixed offset and the conclusion drawn without checking
the field that qualifies it.

The volume is **HFS+ inside an HFS wrapper**:

    wrapper MDB signature   0x4244 'BD'      <- what the earlier claim read
    drEmbedSigWord          0x482B 'H+'      <- what it failed to read
    embedded volume header  'H+' at byte 966656 of the partition

The tell was in plain sight: the wrapper's root directory contains exactly one
file, `Where_have_all_my_files_gone?`, which is the placeholder Apple puts in
an HFS wrapper. hfsutils mounts the WRAPPER and reports an almost empty disk;
the actual System Folder is in the embedded HFS+ volume, which hfsutils cannot
read or write at all.

**And there is no HFS+ writer in this environment**: no `hfsplus`/`hfsprogs`
tools, no `mount.hfsplus`, and the kernel has no hfsplus module
(`/proc/filesystems` has no entry, `modprobe hfsplus` fails). So the Startup
Items idea is not merely unproven — **it cannot be done here at all**, by any
route that writes the boot volume offline.

**ACHIEVED 2026-08-02, on the sixth boot — the application runs on Mac OS 9.2
and its output is byte-exact.** It is driven from the KEYBOARD. Five earlier
boots were spent trying to make the mouse work, and the mouse cannot work
here at all.

What runs, and what checks it:

    tools/vmac/os9.py fixtures/derived-DDT.sit -o <dir> --launch
    tools/vmac/os9.py --list tools/vmac/os9sample.txt -o <dir> --launch

`launch_by_keyboard()` quits the Setup Assistant with Cmd-Q, selects the
transfer volume by typing `unc`, opens it with Cmd-Down, selects and launches
the application the same way, presses Return in SFGetFile (which opens with
`archive.sit` already selected) and Return again on the result alert. No
coordinates, no double-click timing, no pointer. It worked first try.

`verify_output()` then does something the System 6 harness cannot: the
transfer volume is a plain file on the host, so after the emulator is gone the
extracted forks are lifted straight out of it with hfsutils (`hcopy -m`, both
forks in one MacBinary) and compared **byte for byte** against the same
engine's Linux output. That is a stronger check than the framebuffer CRC grid
Mini vMac needs, it needs no pixel decoding, and it doubles as the check on
whether the guest flushed — an unflushed volume fails to mount or comes up
short, rather than passing silently.

**13/13 on `tools/vmac/os9sample.txt`**: 32 files, 712,481 data bytes and
309,358 resource-fork bytes, all byte-exact, names and folder structure
included. The table is in FORMATS.md. Two entries in it are not extractions:
`derived-DandStoQIF2.sea` sniffs as DiskDoubler, which is detect-only by the
brief, and passes because the Mac declines it cleanly ("This file could not be
extracted") and the Linux engine declines it too — agreement on nothing being
written is a result, not an absence of one.

### The new harness found a real bug on its first sweep — FIXED

`synth-exo-Z.Z` and `synth-exo-gz.gz` failed: the Mac wrote `archive.sit~1`
where Linux wrote `archive`, same 2200 bytes either way. Both fixtures are in
`tools/vmac/sample.txt` and both had been passing under Mini vMac.

They passed there because **the Mini vMac check cannot see names.** It compares
`nfiles`, summed CRC-32s and summed lengths off the screen; a name does not
survive being summed. The OS 9 check reads the volume, so it compares names
without anyone deciding it should.

The bug was in the Mac shell. `unclassic.h` defines `name_hint` — the fallback
name for the formats that store none, gzip and .Z — as *the archive filename
minus its last extension*, which is what `cli/main.c` passes and what unar
does. `RunExtract()` passed the whole name. So opening `foo.gz` on a Mac wrote
`foo.gz`, colliding with the archive beside it, hence `foo.gz~1` — on every
system, not just OS 9. Fixed in `mac/unclassic_mac.c` with the CLI's rule, a
leading dot not counting as an extension.

**An aggregate check cannot fail on a property it never aggregates**, and
nothing recorded that on-Mac names were unverified, because the harness looked
exhaustive: twelve formats, both forks, byte-exact. It was exhaustive about
bytes.

### The pointer does not work in this guest — measured, not inferred

`tools/vmac/os9probe.py` exists because four boots had been spent inferring
causes from a single non-observation: "the volume did not open". That is the
`macburger-helper.hqx` mistake in another costume — an outcome that did not
happen tells you nothing about which link in the chain broke. So the probe
measures the primitive instead, on targets whose response is unambiguous, and
runs the whole ladder in one boot. Results:

| # | probe | changed | verdict |
|---|---|---|---|
| 0 | pointer moves at all (whole screen) | 64 px | yes |
| 1 | held press pulls a menu bar title down | 0.0000 | **no** |
| 2 | release rolls it back up | 0.0000 | — |
| 3 | click on bare desktop changes the app menu | 0.0000 | **no** |
| 4 | single click highlights the volume icon | 0.0000 | **no** |
| 5 | double click opens the volume | 0.0000 | **no** |
| 6 | Cmd-Q changes the front application | 0.2662 | yes |
| 7 | typing `unc` highlights the volume icon | 0.1553 | yes |
| 8 | Cmd-Down opens the volume window | 0.1284 | yes |
| 9 | the application launches | 0.0677 | yes |
| 10 | extraction runs and reports | 0.0954 | yes |

Every mouse probe is **exactly** zero and every keyboard probe works. Probe 0
is the one that explains it: the 64 pixels it changed are the arrow cursor
itself, and enumerating them locates the two clusters at (0..8, 0..13) and
(1022..1023, 766..767) — the cursor bitmap in one screen corner and then the
other. It appears **only in the extreme corners**. The pointer was then parked
at three positions on bare desktop in turn — (200,600), (800,600), (500,400) —
and both consecutive diffs are uniformly black, mean 0 and maximum 0, not one
pixel: the cursor did not move between any of them. So `mouse_move` does not
position the cursor in this guest, and clicks land wherever it is pinned.

Probe 4 is the one every earlier attempt skipped. A single click that only
SELECTS separates "the coordinate is wrong" from "the double-click is wrong",
and those two had been conflated in every write-up. It is zero as well, which
rules out both.

**What is NOT established** is the mechanism. The natural reading is that Mac
OS 9 binds QEMU's `usb-tablet` but treats its absolute reports as relative
deltas, which would saturate at the corners exactly as observed — but that is
a hypothesis, it has no minimal reproduction, and nothing in this project may
be written down as a finding without one. What is a finding is the behaviour:
the pointer cannot be positioned, so nothing here uses it.

### Three explanations for one symptom, and why all three were the wrong shape

Superseded, kept because the pattern is the point:

1. **The double click was too slow.** True and real: `click(double=True)` sent
   four `mouse_button` commands as four `mon()` calls, each sleeping 0.3 s
   first, putting ~0.9 s between clicks against the Mac's ~0.5 s threshold.
   Fixed. Not sufficient.
2. **The pointer was relative.** True and real: `mac99`'s default is an ADB
   mouse, `info mice` says so, and absolute coordinates fed to it are applied
   as deltas. `-device usb-tablet` plus `mouse_set` was added, and
   `use_absolute_pointer()` verifies against `info mice` rather than assuming.
   Not sufficient — and now known not to help at all, because the guest does
   not use the tablet either.
3. **The Setup Assistant holds the foreground.** True, and confirmed by
   screenshot: it launches on every boot (the harness correctly starts from a
   pristine copy, so it is never marked done) and takes the front. Quitting it
   is a real and necessary step, which `launch_by_keyboard()` does first. Not
   sufficient either.

Three consecutive real defects, each fixed, none of them the answer. All three
were about *clicking* — and clicking was never going to work. The probe that
asked "does a press land at all?" cost one boot and answered it. **Measure the
primitive before theorising about the compound.**

### And the boot time was host load written down as a guest property

This section said 20-45 minutes, having earlier said four. On an idle host the
desktop settles in **~110 s**, measured twice in the same afternoon. Both
earlier figures were real measurements of a loaded machine and a lucky one,
recorded as facts about Mac OS 9. `settle()` waits for the screen to stop
changing and for the Finder's menu bar to be present, so no figure is needed;
`--boot-wait` only bounds the wait.

`settle()` gained that menu-bar check after it announced a settled desktop 43 s
into a boot. The cause was `shot()` returning its path unconditionally once the
PPM existed, so a failed `convert` still read as success: a caller passed a
directory instead of a file, every screenshot silently failed, and two empty
buffers compared equal. Two fixes: `shot()` now verifies the converted file
exists and is non-empty, and a screenshot that did not happen resets stability
rather than counting towards it. "Nothing changed for a while" is a proxy for
"ready", and a proxy is not the thing.

### What is still open on Mac OS 9

- **HFS+.** The transfer volume is HFS, so long names, the 31-character
  truncation rule and the collision-suffix logic still have not met an HFS+
  volume. The boot volume *is* HFS+, so this is reachable now — extract onto
  it rather than onto the transfer volume — but it has not been done.
- **The `SIZE` partition under OS 9's Process Manager.** The application
  launches, so the partition is honoured enough to run; it has not been tested
  against a fixture large enough to make the refusal bite, which is what the
  System 6/7 comparison did with `derived-KeyGraphics.sit`.
- **Real PowerPC hardware**, like real 68k hardware, remains untouched.

### Timing on a 7 MHz Mac Plus — MEASURED, after three wrong write-ups

Absolute 1x timings now exist for every format sampled (FORMATS.md). Getting
there took four attempts, and the three failed ones are kept because the
mistake behind all of them was identical.

`run.py --emu mv-4M-1x` separates boot from extraction: the application paints
its "alive" grid before touching a disk, so the gap between the first
decodable grid and the last is the archive alone. Small archives extract in
under 5 s on a machine that takes ~10 s to boot; `derived-EmpireBuilderDemo.sit`
(278 KB in, 417 KB out) takes ~134 s.

**`macburger-helper.hqx` was written up three times as an anomaly and is not
one.** It extracts in **150 s** (boot 30 s), one file, 259,379 bytes out,
byte-exact. The published explanations, in order, were:

1. **host contention** — the first attempt ran alongside CI and a second
   emulator, and polled every 3 s through a pure-Python decoder over a
   175k-pixel grid. Real, and it did wreck that run. Disproved as *the* cause
   by an idle host, where it still did not finish.
2. **the on-Mac path scales badly** — the strongest claim, and wrong.
3. **the autotest's CRC read-back** — disproved with `-D UNC_AT_NOCRC`, and
   irrelevant once (2) fell.

What actually settled it was `UNC_AT_PROGRESS`, which paints the engine's byte
counter into the result grid as it runs, so a run that has *not* finished can
still be interrogated — screenshot it and read where it got to:

    t+~7 min     49,152 / 306,651   (16%)
    t+~9 min     98,304 / 306,651   (32%)
    t+11 min    303,104 / 306,651   (99%)   <- 205 KB in the last 100 s

The rate is wildly non-uniform: slow through the first third, then most of the
archive in under two minutes. Every fixed timeout I chose expired during the
slow phase and looked exactly like a hang.

**The lesson, and it cost three write-ups: a timeout expiring is not a
measurement.** It reports that something did not finish inside a number I
picked, and nothing at all about why — yet each time I read a cause into it and
published one. The instrument that answered it in a single run was twenty
lines, and the data it needed was already flowing through a callback the
engine has had since M0.


### Open items from the on-Mac corpus replay — both CLOSED 2026-07-25

Both were re-run on a rebuilt, and this time **committed**, Mini vMac
harness (`tools/vmac/`; the original was never checked in and its working
directory is gone).

- **`derived-RWAsm_Folder.sit` "fails on a 4 MB Mac Plus" — DOES NOT
  REPRODUCE.** It extracts all 38 entries byte-exact, at the same 643.2 KB
  peak the failing run reported. The whole 44-fixture sample is now 44/44 at
  4 MB, which also clears the four fixtures previously recorded as timing
  out. What differed cannot be established, because the harness that
  produced the old numbers does not exist any more. Closed as
  not-reproducible, not as fixed.
- **`popper-1.7.tar.Z` and `PCCTS.tar.gz` at 1 MB — ROOT-CAUSED AND
  FIXED.** Both reproduced, and the cause was not File Manager or HFS cache
  headroom: the Mac sink accumulated each whole fork in a `NewPtr` block
  before writing it, so the shell needed `archive + engine peak + largest
  output fork`, and these two have the sample's largest output forks (174 KB
  and 287 KB). The sink now writes each chunk straight through as the engine
  produces it, and the shell's RAM use no longer depends on output size at
  all. Both fixtures are byte-exact at 1 MB; the sweep went 37/44 -> 39/44,
  with only StuffIt 5 budget refusals left. The old path stays buildable as
  `UNC_MAC_STAGE_WRITES` and both are byte-exact through the qemu-m68k mock
  in CI.

### Detect-only gap — RESOLVED

DiskCopy 4.2 was long named in `unc_sniff` but never detected, because no
reference was available offline (XADMaster has no DiskCopy parser) and
rule #3 forbids inventing a format from memory. A reference was since
obtained (`reference/notes/DiskCopy42.md`, from the DiscFerret wiki) and the
probe is now real: it matches a synthetic 800K GCR image and a real one,
with 0 false positives across 803 fixtures. Still detect-only — disk images
remain out of scope for v1, and extraction returns cleanly unsupported.
