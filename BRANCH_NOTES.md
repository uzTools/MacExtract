# Branch `rom64k` — the application on a 64K-ROM Macintosh

**Status: it STARTS and its interface works; it cannot extract.** On an
emulated Macintosh 512K — 64 KB of ROM — under Apple's 400K MFS System 3.0,
the build in `dist/` opens Standard File, lists the volume, and refuses a
non-archive with its own alert. Extracting a real archive bombs `ID = 12` on
an HFS call, because that machine has no HFS. **`dist/` on this branch is the
binary to hand to anyone with the hardware** (MANUAL_TESTS.md §7); `main`'s
`dist/` bombs on arrival there.

## What the branch changes

One guard, in `mac/macextract_mac.c`:

```c
static Boolean Has128KROM(void)
{
    const unsigned char *rom = (const unsigned char *)LMGetROMBase();
    return (Boolean)!(rom[8] == 0 && rom[9] < 0x75);
}
```

and `MaxApplZone()` called only when it is true, at both `main()`s. That is
the whole diff against `main` apart from `dist/` and the documentation.

`MaxApplZone` is `[Not in ROM]` on a 64K ROM (Inside Macintosh II-30) and
Retro68 emits it as an inline trap, so it bombs before the application draws
anything. The version word at `ROMBase+8` is Inside Macintosh II's `Environs`
note; `>= 117 ($75)` is Inside Macintosh IV's preface. `TrapAvailable` cannot
be used — it reports that trap as PRESENT on a 64K ROM.

## What is measured

| | result |
|---|---|
| Macintosh 512K, 64K ROM, MFS System 3.0 | Standard File opens; a non-archive is refused with the application's alert; **extraction bombs `ID = 12`** |
| System 6.0.8, 1 MB Mac Plus | 69/69, unchanged |
| System 3.0, 512 KB (512Ke) | 66/69, unchanged, same three memory refusals |
| code size | **0 B** over `main` — the guard fits under `UNC_MAC_MAX_CODE` |

## What would finish it, and why this machine cannot

HFS. Those machines have it only with an Apple **Hard Disk 20**, whose driver
ships as a file named `Hard Disk 20` on Apple's *HD 20 Startup* disk. Under
Mini vMac that file hangs the 64K-ROM machine at an empty dialog frame that
nothing dismisses — Apple's own disk and a disk built here with only that file
added behave identically, so it is the DRIVER, not the disk layout, and the
likely reason is that Mini vMac provides no HD20 hardware for it to find.

So the remaining question is one somebody with a real 512K **and an
HD20** can answer in an afternoon, and nobody here can answer at all. That is
MANUAL_TESTS.md §6, and it is askable only because this branch's `dist/`
starts.

## Why it is not on `main`

Because nothing has ever run it on the machine it is for. The guard is
provably neutral on every tier the project claims, but a capability nobody has
exercised does not belong in the download that people are told works. Merge it
when a real machine says yes.
