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
the same engine's Linux output (`tools/vmac_check.py`). Result: **40/44
corpus fixtures byte-exact across all twelve formats**; the extracted
metadata (type/creator, inited-flag cleared) is confirmed on-Mac so an
extracted `APPL` launches by double-click. The other four are the largest
fixtures (~1 MB output) and extract correctly but slowly on the 7 MHz
68000, overrunning the automated poll (one confirmed complete at 185 s);
their logic is proven byte-exact off-Mac (CI differential + qemu-m68k mock
cover them). See FORMATS.md.

### Earlier "root causes" that were confounded by the glue bug

The `HOpen` glue silently broke every open, so the long "two-fork crash"
investigation drew wrong conclusions. Corrected here:

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

### Real test-harness lessons (not app bugs)

- **Mini vMac's disk write-back to the host image is lazy and PARTIAL** —
  it can commit one fork of a file but not the other — so results cannot be
  read off the Out volume. Verification is done ON-SCREEN instead (the app
  paints results to the framebuffer, read from a screenshot).
- **QuickDraw drawing (NewWindow/EraseRect) bombs "out of memory" when
  called after any File Manager activity**, despite megabytes free — so the
  result grid is written by poking `qd.screenBits` directly.
- **`HideCursor()` before drawing**, or the cursor's saved background
  stamps the desktop pattern back over the grid; park the host pointer off
  the grid before the app draws.
- `pkill -9` never lets the emulator flush; use a fresh pristine boot image
  per run (repeated boot+kill cycles corrupt System 6's writes to it).

### Open items from the on-Mac corpus replay

Both surfaced while recording the 1 MB Mac Plus results (see FORMATS.md).
Neither blocks the engine — both fixtures are byte-exact off-Mac and in CI —
but neither is explained, so neither is claimed as an accepted tier.

- **`derived-RWAsm_Folder.sit` fails on a 4 MB Mac Plus.** All 38 entries
  error out at a 643.2 KB peak. It is not a timeout (the run completed) and
  not a budget refusal (4 MB leaves ample headroom, and sibling Arsenic
  fixtures with larger blocks pass on the same machine). At 1 MB the same
  fixture refuses cleanly on every entry, as expected. Only the 4 MB
  behaviour is anomalous. Not re-run since; needs one.
- **`popper-1.7.tar.Z` and `PCCTS.tar.gz` fail at 1 MB only.** Both are the
  largest-output fixtures of their format (174 KB / 280 KB of tar payload);
  both pass at 4 MB with *identical* peak heap, so the decoder is not over
  budget. `popper-1.7.tar.Z` returns `UNC_ERR_SINK` (-9): the failure is in
  the Mac app's File Manager writes under 1 MB memory pressure, not in the
  engine. The harness is byte-identical between the two runs (same 1440 KB
  output volume, same disk set — only the emulator's RAM differs), so this
  is a real RAM-dependent limit of the *shell*, and the likely suspect is
  File Manager / HFS cache headroom rather than the engine budget.

### Detect-only gap — RESOLVED

DiskCopy 4.2 was long named in `unc_sniff` but never detected, because no
reference was available offline (XADMaster has no DiskCopy parser) and
rule #3 forbids inventing a format from memory. A reference was since
obtained (`reference/notes/DiskCopy42.md`, from the DiscFerret wiki) and the
probe is now real: it matches a synthetic 800K GCR image and a real one,
with 0 false positives across 803 fixtures. Still detect-only — disk images
remain out of scope for v1, and extraction returns cleanly unsupported.
