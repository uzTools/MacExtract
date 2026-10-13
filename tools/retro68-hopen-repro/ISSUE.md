# Ready-to-post upstream issue (github.com/autc04/Retro68)

**Not filed, and not to be filed from here.** The maintainer posts this from
his own account (MANUAL_TESTS.md §7, CLAUDE.md Rules). Reproduction:
`iomisc_repro.c` in this directory.

Re-verified 2026-10-13 against Retro68 master `d8b891a` (2026-10-09): its
pinned multiversal `d124fa6` and multiversal master `28eac84` carry a
`custom/glue.c` byte-identical to the one measured here.

**What is NOT in this issue, and why.** The 2026-08 draft led with "`OpenDF`
and `HOpenDF` return `paramErr` on System 6 and do not fall back". That is
Apple's documented contract, not a bug: Technote FL 1041 tells the caller to
retry with `HOpen` on `paramErr`, and Retro68 already settled exactly this in
issue #53 (2018) by doing so in `libretro/syscalls.c`. Withdrawn (BLOCKERS.md).

---

**Title:** `HOpen`/`HOpenRF`/`HOpenDF` glue leaves `ioMisc` uninitialised; the
File Manager writes an access path buffer through it

**Body:**

In `multiversal/custom/glue.c`, `HOpen`, `HOpenRF` and `HOpenDF` declare
`HParamBlockRec pb;` on the stack and set only `ioVRefNum`, `ioDirID`,
`ioNamePtr` and `ioPermssn`. `ioMisc` keeps whatever the stack held.

For `_HOpen`, `ioMisc` is an input: a pointer to the caller's own access path
buffer, or NULL to use the volume buffer. Technote FL 1041 (*Inside Macintosh:
Files* errata, "Parameter blocks missing ioMisc field"):

> ioMisc must be initialized to zero before calling PBHOpenDF, PBHOpenRF, or
> PBHOpen. Failure to initialize ioMisc to zero on some Macintosh models will
> cause the system to crash.

The File Manager does use it. When `HOpen` is called with a valid RAM address
left on the stack, it opens the file successfully and then writes into
memory the caller never passed:

```
                                   System 6.0.8   System 7.0.1
1  PBHOpenSync, ioMisc = NULL        0 changed      0 changed
2  PBHOpenSync, ioMisc = &decoy    131 changed      3 changed
3  HOpen, &decoy left on stack     131 changed      3 changed
```

(longs of a 1 KB `decoy` array changed by open + a 4-byte `FSRead` + `FSClose`;
131 longs = 524 bytes, one access path buffer. Every open returns `noErr`.)

Case 1 is the control. Case 2 shows the File Manager writes through `ioMisc`.
Case 3 is the glue: the stack garbage becomes a buffer pointer. With an
arbitrary stale pointer this is silent heap or stack corruption. The
non-hierarchical `FSOpen`, `OpenDF` and `OpenRF` in the same file already set
`pb.ioParam.ioMisc = NULL`, so the fix is to do the same in the three
H-variants (TN1041 also asks for `ioFVersNum` = 0, which they also leave unset).

This is not hypothetical. An application of ours (an archive extractor) opened
its files through `HOpen`/`HOpenRF` and, on System 6.0.8, hung or wrote zero
files. Rebuilt with a verbatim copy of the glue it still fails on 4 of 4
archives; the same copy with only `pb.ioParam.ioMisc = NULL;` added passes
4 of 4. The symptom changes with the stack layout (a hang, empty output, an
application that never draws), because it depends on what the stale pointer
addresses.

**Reproduction:** `iomisc_repro.c`, attached (~130 lines, Toolbox only). Build
it as an application, boot or launch it on System 6, and read the three
"decoy longs changed" lines. It creates its own 512-byte file `T`.

**Environment:** Mini vMac 36.04 emulating a Mac Plus (68000, 4 MB); System
6.0.8 and System 7.0.1; Retro68 `335fa54f6d`, `-mcpu=68000 -Os`.
