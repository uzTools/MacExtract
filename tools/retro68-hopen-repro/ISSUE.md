# Ready-to-post upstream issue (github.com/autc04/Retro68)

Not filed from this environment: there is no `gh` CLI and no GitHub credentials
here. Post it manually if you want it upstream. Reproduction code:
`tools/retro68-hopen-repro/`.

Scope note: this is a *small* issue. The much larger claim this investigation
started from — "`HOpen` returns `noErr` without writing the refNum on System 6"
— was tested across ten cases and **does not reproduce**; it has been withdrawn
(see `DECISIONS.md`). Please do not file that part.

---

**Title:** `HOpenDF` unusable on System 6 (returns paramErr); non-hierarchical
`OpenDF` already has the fallback

**Body:**

`multiversal/custom/glue.c` defines both `OpenDF` and `HOpenDF`. The
non-hierarchical one already knows that the `_OpenDF` trap does not exist
before System 7 and falls back:

```c
    {
        // OpenDF not implemented, so use regular Open.
        err = PBOpenSync(&pb);
    }
```

The hierarchical one has no such fallback:

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

so on System 6 every `HOpenDF` call fails with `paramErr` (-50). Suggested fix
is the same shape as `OpenDF`: fall back to `PBHOpenSync` when `PBHOpenDFSync`
returns `paramErr`.

Second, smaller point in the same three functions: `HOpen`, `HOpenRF` and
`HOpenDF` declare `HParamBlockRec pb;` as an uninitialised stack local and fill
in only `ioVRefNum`, `ioDirID`, `ioNamePtr` and `ioPermssn`. `ioMisc` is left as
stack garbage, and for `_Open`/`PBHOpen` `ioMisc` is an *input* — a pointer to
an optional access path buffer, or NULL to use the volume buffer (Inside
Macintosh: Files, `PBHOpen`). `OpenDF()` and `OpenRF()` in the same file do set
`pb.ioParam.ioMisc = NULL`; the H-variants do not.

In practice System 6.0.8 tolerates the garbage — I deliberately poisoned
`ioMisc` with `0xA3A3A3A2` and the open still succeeded and read correctly — so
this is a latent inconsistency rather than an observed failure. Still worth
zeroing for the same reason the non-H versions do.

**Environment:** System 6.0.8, Mac Plus (68000), Mini vMac 36.04, Retro68 at
`335fa54f6d`, `-mcpu=68000 -Os`.

**Reproduction:** `hopen_repro.c` (attached / linked). It creates its own
512-byte test file next to the application, then runs ten open cases and prints
`err`, `refNum`, `GetEOF` and a 4-byte `FSRead` for each. Case 8 is `HOpenDF`;
cases 1 and 4 are the `ioMisc` probes. Full result table in the README.
