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

**Title:** `HOpen`/`HOpenRF`/`HOpenDF` don't initialise `ioMisc`, and the File
Manager writes through it

**Body:**

Hi! I think I've run into a small bug in the H-variants of the open glue.

In `multiversal/custom/glue.c`, `HOpen`, `HOpenRF` and `HOpenDF` put an
`HParamBlockRec` on the stack and fill in `ioVRefNum`, `ioDirID`, `ioNamePtr`
and `ioPermssn`, but never `ioMisc`, so it ends up holding whatever was on the
stack.

For `_HOpen`, `ioMisc` is actually an input: it points to the caller's own
access path buffer, or is NULL to use the volume buffer. Apple's Technote FL
1041 (the *Inside Macintosh: Files* errata) is pretty direct about it:

> ioMisc must be initialized to zero before calling PBHOpenDF, PBHOpenRF, or
> PBHOpen. Failure to initialize ioMisc to zero on some Macintosh models will
> cause the system to crash.

And the File Manager really does use it. I wrote a small test that leaves the
address of a 1 KB "decoy" array on the stack, then calls `HOpen`. The open
succeeds, and the File Manager writes into the decoy:

```
                                   System 6.0.8   System 7.0.1
1  PBHOpenSync, ioMisc = NULL        0 changed      0 changed
2  PBHOpenSync, ioMisc = &decoy    131 changed      3 changed
3  HOpen, &decoy left on stack     131 changed      3 changed
```

(Longs of the decoy changed after open + a 4-byte `FSRead` + `FSClose`. 131
longs is 524 bytes, exactly one access path buffer. Every open returns
`noErr`.)

So with whatever pointer happens to be lying on the stack, you get silent
memory corruption.

This is how I found it: my application used `HOpen`/`HOpenRF`, and on
System 6.0.8 it would hang or write zero files, and I couldn't work out why.
Rebuilt with a verbatim copy of the glue, it still fails on 4 out of 4 test
archives. Add just `pb.ioParam.ioMisc = NULL;` to that copy and it passes
4 out of 4. The symptom moves around with the stack layout (a hang, empty
output, an app that never draws), which made it a fun one to chase down.

The fix should be easy: `FSOpen`, `OpenDF` and `OpenRF` in the same file
already set `pb.ioParam.ioMisc = NULL`, so the three H-variants just need the
same line. TN1041 also asks for `ioFVersNum = 0`, which they leave unset too.

Possibly related to #53: the `paramErr` fallback in `syscalls.c` lands in
`HOpen`, so `open()`/`fopen()` on System 6 go through this code as well.

**Repro:** [`iomisc_repro.c`](https://github.com/jarreboum/MacExtract/blob/main/tools/retro68-hopen-repro/iomisc_repro.c),
about 130 lines, Toolbox only. Build it as an app, run it on System 6, and
read the three "decoy longs changed" lines. It creates its own little test
file `T`.

**Setup:** Mini vMac 36.04 as a Mac Plus (68000, 4 MB), System 6.0.8 and
7.0.1, Retro68 `335fa54f6d` with `-mcpu=68000 -Os`. Current master
(`d8b891a`) still has the same `glue.c`.

Thanks for Retro68!
