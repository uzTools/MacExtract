# tools/glue_inline — multiversal's File Manager glue, inline, for measuring

`glue_inline.h` turns ten of multiversal's hand-written File Manager glue
routines (`HOpen`, `HOpenRF`, `HDelete`; `FSRead`, `FSWrite`, `SetFPos`,
`GetEOF`, `SetEOF`, `FlushVol`, `FSClose`) into the `gnu_inline` definitions
multiversal pull request 20 generates for traps with register outputs, so the
shell can be sized as if multiversal generated them inline. It does not touch
the toolchain and nothing builds it by default. `shell.patch` is the shell
side, a no-op until defined (byte-identical `.text` and `.data`): `USE_GLUE`
switches `MyOpenFork`/`MyHDelete` to the glue, `GLUE_INLINE_HDR` with
`GLUE_INLINE_HFS` and/or `GLUE_INLINE_IO` includes the header (pass these in
`CFLAGS` to `tools/build_mac.sh` in a fresh build directory),
`MYOPEN_NOINLINE` keeps `MyOpenFork` out of line, and `GLUE_IN_IMAGE`,
defined at the top of `mac/seg_types.h` because `mkoverlay.sh` takes no
`CFLAGS`, takes `FSClose`/`GetEOF`/`FSWrite`/`FlushVol` out of `SegSetupFns`
so that the setup image expands them itself. Apply it in a scratch worktree,
never on `main`. The figures and the method are DECISIONS.md 2026-11-09,
*the glue that was measured inline*.
