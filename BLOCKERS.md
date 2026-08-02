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

### Mac OS 9 — the boot volume is HFS+, and offline writes are not possible here

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

**Attempted 2026-08-02 across four boots and NOT achieved.** What is now
established, and what is not:

- **Mac OS 9.2 boots to the Finder** under `qemu-system-ppc -M mac99,via=pmu`
  on this host — seen directly, repeatedly. (The image is 9.2, not the 9.0.4
  the task named.) It takes 20-45 minutes here, not the four minutes the old
  note claimed, and the time varies a lot with host load.
- **The transfer volume mounts.** Both `untitled` (boot) and `unclassic`
  (transfer, carrying the application and an archive) appear on the desktop.
- **The desktop icon coordinates are measured and correct**: `unclassic` sits
  at (974, 117) on the 1024x768 screen; `XFER_VOLUME_ICON` is (974, 120).
- **The volume will not open, so the application has never been launched.**
  The click lands — the Finder comes to the front — but no window opens.

**ROOT CAUSE FOUND 2026-08-02, and it was neither of the things the first two
fixes chased.** `info mice` on the running guest reports:

    * Mouse #2: QEMU HID Mouse

`mac99`'s default pointer is an **ADB mouse, which is RELATIVE**. The
monitor's `mouse_move X Y` applies X and Y as a *delta*, so the 0..32767
absolute coordinates this harness computes slam the pointer into a screen
corner — and every click lands on bare desktop. That is why the Finder came
forward but nothing ever opened, and why the failure looked exactly like a
mis-measured icon or a mistimed double-click.

The fix is two parts, and the second is easy to miss: add `-device usb-tablet`
**and select it**, because QEMU leaves the relative mouse active. Verified
directly against `info mice`, without waiting for an OS 9 boot:

    before   * Mouse #2: QEMU HID Mouse
    after      Mouse #2: QEMU HID Mouse
             * Mouse #3: QEMU HID Tablet (absolute)

`Qemu.use_absolute_pointer()` does this at start-up, parses the index rather
than assuming it, and refuses to continue if the active pointer is still
relative — so this class of failure reports itself instead of looking like a
coordinate problem.

**What is verified: the pointer mechanism. What is NOT: that the volume opens
and the application launches — a fifth boot with the absolute pointer active
still ended with nothing open.**

So there is at least one more cause. The fifth run's screenshot shows what the
earlier ones did not: **the Mac OS Setup Assistant is frontmost.** It launches
itself shortly AFTER the desktop settles — on every boot, because this harness
correctly boots a pristine copy each time and the assistant is therefore never
marked done — and it takes the foreground. In classic Mac OS **the first click
in an inactive application only activates it**; the click is not passed
through. A double-click aimed at a desktop icon while another application is
frontmost is therefore spent activating the Finder, leaving a single click on
the icon, which selects rather than opens. That matches every observation:
the Finder comes forward, the icon does not open.

`os9.py` now clicks empty desktop first and then double-clicks. **This is a
hypothesis and is labelled as one in the code.** It is the THIRD explanation
for this single symptom; the first two — a double-click spanning 0.9 s, and a
relative pointer receiving absolute coordinates — were both real defects, both
fixed, and neither was sufficient. Do not treat the next one as settled
either until a screenshot shows a window.

A cheaper route exists and is worth trying first: get rid of the Setup
Assistant instead of working around it, by clicking its close box, or by
finding whether the image can be made to skip it.

The earlier click investigation, kept because the reasoning is sound even
though it was chasing the wrong thing:

- Originally `click(double=True)` sent four `mouse_button` commands as four
  separate `mon()` calls. `mon()` sleeps 0.3 s before sending so the monitor
  banner can arrive, which put roughly **0.9 s between the two clicks** — past
  the Mac's ~0.5 s double-click threshold, so the Finder saw two single
  clicks.
- Sending all four events in one write fixed that and broke the other end:
  they arrive microseconds apart and the guest samples the mouse once per VBL
  (60 Hz), so the transitions can be missed entirely. Same symptom.
- It now sends them on one connection with deliberate 60 ms down/up gaps and
  180 ms between clicks — inside the threshold, above one frame. **That
  version has not been run**; a verification boot costs ~50 minutes here and
  was not started.

So the next attempt is ONE run, not three. Everything ahead of the click is
known-good and measured.

Two harness weaknesses were fixed along the way:

- **The fixed sleep is gone.** `Qemu.settle()` screenshots until the screen
  stops changing, the same approach `interactive.py` uses, so the boot is
  waited for rather than predicted. Default bound raised to 1800 s.
- **QEMU is started with `start_new_session=True`**, so when the driver is
  killed by a timeout the emulator survives as an orphan. One was left running
  and had to be killed by hand. Not fixed — the flag is deliberate (a stray
  signal to the process group must not take the emulator down mid-write) — but
  it is now written down, and `run.py` has the same property.

What that leaves for getting the application launched on Mac OS 9:

- Finder automation through QEMU screendumps — the original plan, and still
  the only one available in this container. `mkapmdisk.py` already builds a
  transfer volume (HFS, so writable with hfsutils) that mounts on the OS 9
  desktop; what is missing is opening it and double-clicking, which needs the
  screenshot-look-adjust loop.
- Or installing HFS+ tooling, which would reopen the Startup Items route and
  remove GUI automation from the problem entirely.

One thing does improve: because the volume really is **HFS+**, the "HFS+ long
filenames, and names HFS+ permits that HFS does not" row in MANUAL_TESTS.md is
genuinely reachable on this image once the application can be run there. It is
blocked on the same thing, not on a different one.

### Timing on a 7 MHz Mac Plus — NOT MEASURED, and why

**No timing numbers were produced, and none are published.** This is the one
claim the project makes loudest ("runs on a Mac Plus") and the one it has
never quantified; an attempt on 2026-08-01 failed, and the failure is worth
recording so the next attempt does not repeat it.

What works and is committed:

- `mv-4M-1x`, the authentic 7 MHz build, already existed.
- `run.py --emu` now selects it, and `run.py` **splits boot from extraction**:
  the application paints its `kAtRunning` grid before touching a disk, so the
  gap between the first decodable grid and the final one is the extraction
  alone. Proven on a small fixture: `derived-Export.sit` (1615 B StuffIt)
  came out as **boot 10 s + extract 2 s**.
- `tools/vmac/timing.txt` is the representative set — one fixture per format,
  chosen large, plus a small one for the other end.

What failed: **`macburger-helper.hqx` (306 KB BinHex) did not finish in over
fifteen minutes of wall clock at 1x, on two separate attempts.** On a real
Mac Plus that decode should be a minute or two.

Two explanations were possible, and one is now **ruled out**:

1. The host is not sustaining 1x — a single contended core also running the
   screenshot loop, with the first attempt polling every 3 s through a
   pure-Python decoder over 175k pixels. **This is the surviving
   explanation.**
2. ~~The on-Mac path really is that slow for large inputs~~ — **disproved
   2026-08-01.** Decode cost was measured on Linux, where the engine is the
   same code and the clock is trustworthy: `macburger-helper.hqx` takes
   **2.9 ms** for 299 KB, one of the *cheapest* fixtures per byte and about
   3x cheaper than `derived-EmpireBuilderDemo.sit` (9.0 ms) — which DID
   complete at 1x, in ~134 s. A fixture three times cheaper than one that
   finishes in 134 s cannot honestly take more than 900 s on the same
   machine; the two figures disagree by a factor of roughly twenty. The
   non-completion is an artifact of that run, not a property of the code.

~~So there is no lurking usability defect, and the remaining problem is purely
one of environment: this host cannot be trusted to run Mini vMac at a faithful
1x while also screenshotting it.~~ **HALF WITHDRAWN 2026-08-02.**

Blaming host contention does not survive the obvious test. With the machine
idle — load average 0.4, no CI, no second emulator — `macburger-helper.hqx`
STILL did not finish in fifteen minutes, while eight other fixtures across
eight formats measured cleanly at 1x in the same session (8/8; boot ~10 s,
every extraction under 5 s; table in FORMATS.md). Contention was real and did
wreck the first attempt, but it was never the reason this one fixture hangs.

So the part that stands is that the harness and 1x are fine; the part that
falls is the diagnosis. **`macburger-helper.hqx` is a genuine outlier, not an
artifact** — and since it is the cheapest fixture per byte on Linux while
`kermitut9test.bin` at 304 KB extracts fine, neither size nor format explains
it. It is the single best piece of evidence that something in the on-Mac path
scales badly. Chase it with the progress callback instrumented; this write-up
has now guessed twice and been wrong twice.

What can be said with evidence today: the engine's relative cost per format,
an absolute 1x table of eight fixtures, and the
`derived-EmpireBuilderDemo.sit` anchor (278 KB in, 417 KB out, ~134 s, machine
booting in ~10-16 s). All in FORMATS.md, summarised in the README.

**Until it is, no number goes in the README.** A fabricated or
contention-inflated figure would be worse than the current honest absence, and
this repository has enough retracted numbers already.

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
