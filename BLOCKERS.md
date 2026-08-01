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

The only real (and minor) upstream finding that survived is that
`HOpenDF` returns `paramErr` on System 6, because `PBHOpenDFSync` issues a
System 7 trap and — unlike the non-hierarchical `OpenDF` in the same glue
file — has no fallback. Written up in
`tools/retro68-hopen-repro/ISSUE.md`; not filed (no GitHub credentials in
this environment).

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
