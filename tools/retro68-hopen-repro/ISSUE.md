# Ready-to-post upstream issue (github.com/autc04/Retro68)

**Not filed, and not to be filed from here.** The maintainer posts this from
his own account (MANUAL_TESTS.md §7, CLAUDE.md Rules) — no session working in
this repository should submit it. It is also not possible from here: there is
no `gh` CLI and no GitHub credentials (an unauthenticated POST to the issues
API returns 401). Reproduction code: `tools/retro68-hopen-repro/`.

Scope note: this is a *small* issue. The much larger claim this investigation
started from — "`HOpen` returns `noErr` without writing the refNum on System 6"
— was tested across ten cases and **does not reproduce**; it has been withdrawn
(see `DECISIONS.md`). Please do not file that part.

**Corrected 2026-08-01, before filing.** The first draft of this write-up said
the bug was that `HOpenDF` lacks a fallback "unlike the non-hierarchical
`OpenDF` in the same file, which already has it". That is wrong, and it was
wrong in the direction that would have understated the bug: the fallback is in
**`FSOpen`**, and `OpenDF` calls `PBOpenDFSync` bare exactly as `HOpenDF` does.
Case 11 was added to the reproduction to settle it on the machine rather than
by reading, and plain `OpenDF` returns `paramErr` too. So this is two broken
functions, not one. Reading `glue.c` carelessly is how this project got the
first, withdrawn claim wrong as well.

---

**Title:** `OpenDF` and `HOpenDF` are unusable on System 6 (return paramErr);
`FSOpen` has the fallback they need

**Body:**

`multiversal/custom/glue.c` has three entry points that reach the `_OpenDF`
trap. Only one of them copes with that trap not existing before System 7.

`FSOpen` does it correctly:

```c
    // Try newer OpenDF first, because it does not open drivers
    err = PBOpenDFSync(&pb);
    if(err == paramErr)
    {
        // OpenDF not implemented, so use regular Open.
        err = PBOpenSync(&pb);
    }
```

`OpenDF` does not:

```c
pascal OSErr OpenDF(ConstStr255Param fileName, short vRefNum, short *refNum)
{
    ...
    err = PBOpenDFSync(&pb);

    *refNum = pb.ioParam.ioRefNum;
    return err;
}
```

and neither does `HOpenDF`:

```c
pascal OSErr HOpenDF(INTEGER vref, LONGINT dirid, ConstStringPtr name,
                     SignedByte perm, INTEGER *refp)
{
    HParamBlockRec pb;
    pb.fileParam.ioVRefNum = vref;
    pb.fileParam.ioDirID   = dirid;
    pb.fileParam.ioNamePtr = (StringPtr)name;
    pb.ioParam.ioPermssn   = perm;
    OSErr err = PBHOpenDFSync(&pb);
    *refp = pb.ioParam.ioRefNum;
    return err;
}
```

so on System 6 **every `OpenDF` and `HOpenDF` call fails with `paramErr`
(-50)**, measured, on a file that `HOpen` and a hand-filled `PBHOpenSync` open
successfully in the same run:

```
1  HOpen   dirty stack   err=0   ref=378  eof=512  got=4     ok
4  PB      ioMisc=junk   err=0   ref=378  eof=512  got=4     ok
8  HOpenDF vref, rd      err=-50                             BUG
11 OpenDF  (plain)       err=-50                             BUG
```

Case 11 opens the same file, on the same default volume, that cases 1-4 open
without trouble, so this is the trap being absent rather than the file being
missing — and `paramErr` is exactly what `FSOpen`'s own fallback tests for.

Suggested fix is the shape `FSOpen` already uses: fall back to `PBOpenSync` /
`PBHOpenSync` when the DF call returns `paramErr`.

Second, smaller point, in the hierarchical functions: `HOpen`, `HOpenRF` and
`HOpenDF` declare `HParamBlockRec pb;` as an uninitialised stack local and fill
in only `ioVRefNum`, `ioDirID`, `ioNamePtr` and `ioPermssn`. `ioMisc` is left as
stack garbage, and for `_Open`/`PBHOpen` `ioMisc` is an *input* — a pointer to
an optional access path buffer, or NULL to use the volume buffer (Inside
Macintosh: Files, `PBHOpen`). `FSOpen()`, `OpenDF()` and `OpenRF()` in the same
file all set `pb.ioParam.ioMisc = NULL`; the three H-variants do not.

In practice System 6.0.8 tolerates the garbage — I deliberately poisoned
`ioMisc` with `0xA3A3A3A2` and the open still succeeded and read correctly
(case 4 above) — so this is a latent inconsistency rather than an observed
failure. Still worth zeroing for the same reason the non-H versions do.

**Environment:** System 6.0.8, Mac Plus (68000), Mini vMac 36.04, Retro68 at
`335fa54f6d` ("update multiversal", 2026-06-06), `-mcpu=68000 -Os`.

**Reproduction:** `hopen_repro.c` (attached / linked). It creates its own
512-byte test file next to the application, then runs eleven open cases and
prints `err`, `refNum`, `GetEOF` and a 4-byte `FSRead` for each. Cases 8 and 11
are the two `paramErr` bugs; cases 1 and 4 are the `ioMisc` probes. Full result
table in the README.
