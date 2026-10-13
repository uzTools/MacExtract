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

**Title:** `HOpen`/`HOpenRF`/`HOpenDF` don't initialise `ioMisc`, and the File Manager writes through it

**Body:**

Hi! `HOpen`, `HOpenRF` and `HOpenDF` in `multiversal/custom/glue.c` never set `ioMisc`, so it holds whatever was on the stack. But for `_HOpen` it's an input (a pointer to an access path buffer, or NULL), and Technote FL 1041 says:

> ioMisc must be initialized to zero before calling PBHOpenDF, PBHOpenRF, or PBHOpen. Failure to initialize ioMisc to zero on some Macintosh models will cause the system to crash.

The File Manager really does write through it. With the address of a 1 KB array left on the stack, `HOpen` succeeds and the array gets overwritten (524 bytes on System 6.0.8, 12 on 7.0.1). That's how my application ended up hanging or writing nothing on System 6: with a copy of the glue it fails, and adding just `pb.ioParam.ioMisc = NULL;` fixes it.

`FSOpen`, `OpenDF` and `OpenRF` in the same file already set it to NULL, so the H-variants just need the same line.

Repro: [`iomisc_repro.c`](https://github.com/jarreboum/MacExtract/blob/main/tools/retro68-hopen-repro/iomisc_repro.c) (Mini vMac Mac Plus, System 6.0.8 and 7.0.1, Retro68 `335fa54f6d`; master still has the same `glue.c`).

Thanks for Retro68!
