# unclassic

An open-source universal unarchiver for Classic Mac OS formats
(System 6 → Mac OS 9): StuffIt (classic & 5), Compact Pro, PackIt,
BinHex 4, MacBinary, AppleSingle/Double, plus zip/gzip/tar/compress.

- **`libunclassic`** — portable, dependency-free C99 engine.
  All I/O, allocation and progress via caller callbacks; re-entrant;
  32-bit arithmetic; no recursion; 68000-safe (no unaligned access).
- **`unclassic`** — Linux CLI: `unclassic l|x|t <file>`.

Extraction only (no compression). Validated by differential testing
against The Unarchiver (`unar`) — see TESTING.md.

## Build

    make            # or ./ci.sh for the full test matrix

## Status

Work in progress — see PROGRESS.md for the milestone matrix and
FORMATS.md for per-format coverage.

## License

LGPL-2.1-or-later. Decoders are transcribed from XADMaster
(The Unarchiver, Dag Ågren/MacPaw) and documented specs — see NOTICE.
