# Branch `rom64k` — the application on a 64K-ROM Macintosh

**Status: it STARTS and its interface works; it cannot extract.** On an
emulated Macintosh 512K — 64 KB of ROM — under Apple's 400K MFS System 3.0,
the build in `dist/` opens Standard File, lists the volume, and refuses a
non-archive with its own alert. Extracting a real archive bombs `ID = 12` on
an HFS call, because that machine has no HFS. **`dist/` on this branch is the
binary to hand to anyone with the hardware** (MANUAL_TESTS.md §6); `main`'s
`dist/` bombs on arrival there.

## What the branch changes

One launch path for every machine, in `mac/macextract_mac.c`: both `main()`s
call `GrowApplZone()` where `main` calls `MaxApplZone()`.

```c
_MaxMem;                          /* D0 largest free block, A0 grow (II-38) */
p = NewPtr(largest + grow);       /* grows the zone to ApplLimit (II-13)   */
if (p != NULL) DisposePtr(p);
```

`MaxApplZone` is `[Not in ROM]` on a 64K ROM (Inside Macintosh II-30) and
Retro68 emits it as an inline trap, so it bombs before the application draws
anything. `_MaxMem`, `_NewPtr` and `_DisposPtr` are in every ROM (II-36,
II-38). `_MaxMem` is issued inline because its two results come back in two
registers, which Multiverse can only declare as Pascal glue (+44 B instead of
+12). Nothing detects the machine, and nothing touches the zone header.

Until 2026-10-15 the branch skipped `MaxApplZone` when the ROM version word
read below `$75` instead (`Has128KROM()`, DECISIONS.md 2026-09-01). That is
gone.

## What is measured (2026-10-15, against `main` at 29e148d)

| | `main` | this branch |
|---|---|---|
| Macintosh 512K, 64K ROM, MFS System 3.0 | **bombs at launch, `ID = 03`** (the control) | Standard File opens; the destination dialog appears; a non-archive is refused with *"This file could not be extracted."* |
| zone end after launch, System 6.0.8, 1 MB | `ApplLimit` exactly | `ApplLimit` exactly; the `NewPtr` succeeds |
| budget, `-D UNC_OVL_RESIDENT -D UNC_AT_BUDGET`: floor-1M / sys6-512K / sys3-512K | 627,684 / 103,396 / 198,786 B | 627,688 / 103,400 / 198,792 B — **+4, +4, +6, not equal** |
| System 3.0: 4 MB / 1 MB / 512Ke | 74/74, 74/74, 72/74 (BLOCKERS.md) | 74/74, 74/74, 72/74, the same two refusals by name |
| System 6.0.8: 4 MB / 1 MB / 512Ke | 74/74, 74/74, 68/74 (BLOCKERS.md) | 74/74, 74/74 (one `EMUDIED`, re-run: PASS), 68/74, the same six by name |
| System 7.0.1, 4 MB | 74/74 | 74/74 |
| Mac OS 9.2, QEMU, `os9.py --launch` | 22/22 | **22/22** byte-exact: 21 in the sweep, and `synth-arc-mixed.arc` on re-run, after the harness drove a desktop still starting up |

The `main` tallies are BLOCKERS.md's, taken 2026-10-10/11; `main` was not
re-swept, because the branch matched them on every tier. The budget figures
are both builds measured the same morning.

**The budget gap is behaviour, not code, measured.** Two hybrids of this
branch, byte-identical in `CODE` and A5, with `_MaxApplZone` in `_MaxMem`'s
place: without the `NewPtr` they read **627,684 and 198,786 B, `main`'s
exactly**; with a `NewPtr` that fails and purges, 627,688 and 198,800 B. On
System 6 the +4 is `_MaxMem`'s purge; on System 3.0 a whole-zone `NewPtr`
leaves +14 B more even with no purge, so the +6 there is not attributed. It
is in the engine's favour, and it is not zero.

**A no-purge version was measured and not taken**: `CompactMem` plus
`ApplLimit − HeapEnd` grows the zone to `ApplLimit` without purging, at +24 B
of `CODE` and −32, −32, −18 B of budget (DECISIONS.md 2026-10-15, *the purge
MaxApplZone never did*).

## The price, against `main`

| axis | cost |
|---|---|
| `CODE` | **+12 B** in every configuration, all of it `main()` (426 → 438 B shipped; `nm`, no other symbol moved) |
| A5 | −12 B shipped, +20 B lazy and control: `.data` padding behind the longer text, no symbol changed size |
| heap | +4 to +6 B of budget on the machine; `TIERS` derived −32 from the control's +32 (`tools/run_tiers.py`) |
| stack | 0: `main()`'s frame is 148 B and the same six registers in both |
| extractions lost | **0** on every tier above, and in `run_tiers.py --check` |

## What would finish it, and why this machine cannot

HFS. Those machines have it only with an Apple **Hard Disk 20**, whose driver
ships as a file named `Hard Disk 20` on Apple's *HD 20 Startup* disk. Under
Mini vMac that file hangs the 64K-ROM machine at an empty dialog frame that
nothing dismisses — Apple's own disk and a disk built here with only that file
added behave identically, so it is the DRIVER, not the disk layout, and the
likely reason (hypothesis) is that Mini vMac provides no HD20 hardware for it
to find.

So the remaining question is one somebody with a real 512K **and an
HD20** can answer in an afternoon, and nobody here can answer at all. That is
MANUAL_TESTS.md §6, and it is askable only because this branch's `dist/`
starts.

## Why it is not on `main`

Because whether it goes there is the maintainer's decision, and nothing has
yet run it on real hardware. Unlike the guard it replaces, it runs the same
code on every machine, so the LC 475 and the Mac OS 9.2.2 PowerPC can test
the path a 512K would take.
