# Branch `eta-backstep` — the time left that went back up

**Status: ready to merge after the release; not seen on a Macintosh.** The
arithmetic is tested on Linux and on qemu-m68k through the real function
(`tests/mac_sink_test.c --eta`); no emulator or hardware run has watched
the dialog. The reasoning is DECISIONS.md 2026-10-16, *the estimate that
went back up*.

## What the branch changes

- `ProgressReading` in `mac/macextract_mac.c`: the time left from `done`
  and `total` scaled to 16 bits, in place of `elapsed * (100 - pct) / pct`.
- `startTicks` is reset before each layer of a chain (`X.sit.hqx`), not once
  per file.
- `mac_sink_test --eta`, run by `tests/run_mac_sink.sh` natively and on
  qemu-m68k.

## What is measured (2026-10-16, against `main` at 73652b2)

| | `main` | this branch |
|---|---|---|
| time left on a steady run, 3 MB, one hour | up 211 times, by up to 16 min | no rise over 2 s |
| the same, 4 hours | by up to 65 min | no rise over 2 s |
| `--eta`, 16 cases to 400 MB and 4 hours | fails 12 | passes, x86-64 and m68k |
| shipped CODE / A5 | 55,820 / 18,532 B | 55,840 / 18,544 B (A5 is padding) |
| resident control CODE + A5 | 212,928 B | 212,928 B |

## Merging

`dist/` here is rebuilt from this branch under `main`'s version number. It
is not a release, and should not be handed out as one. Merge after the
release, rebuild `dist/` on `main`, and bump `UNC_VERSION` with the next
release.
