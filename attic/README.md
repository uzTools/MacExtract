# attic — code that was finished, and then taken out of scope

Nothing in this directory is built. `src/` is what the Makefile globs and
`tools/` is what `ci.sh` runs; these files sit outside both on purpose.

This is not a graveyard for broken things. Everything here worked, was
graded against another implementation, and left the tree because the
answer to *"should this be in the product?"* changed — which is a
different event from a bug, and the code is worth keeping in a form that
can be read and put back.

## What is here

**The disk-image probes** (added and retired on 2026-08-26 and, for
Disk Copy 4.2, M9):

| file | was |
|---|---|
| `fmt_diskimage.c` | `unc_diskcopy_probe` and `unc_diskimage_probe`, part of `src/fmt_stubs.c` |
| `unit_diskimage.c` | `test_diskcopy` and `test_diskimage`, part of `tests/unit_formats.c`, called from `test_all` |
| `run_diskimage.py` | `tools/run_diskimage.py`, a suite in `ci.sh` |

They named a **disk image** — Disk Copy 4.2, HFS, HFS+/HFSX, an Apple
Partition Map, ISO 9660 in all four CD sector layouts — at 135 real
images named and 0 false positives across 940 fixtures.

**Why they left:** a disk image is not an archive. Somebody who opens an
unarchiver is telling you they believe they have an archive, and naming
something outside that frame changes nothing they can do: the file is
still not extracted and the next move is still not this program. Naming
an archive this engine declines is the opposite case, and that is what
took their place (`src/fmt_foreign.c`). DECISIONS.md 2026-08-26 has the
argument; OPEN_ITEMS.md part 1 records disk images as out of scope in
both directions now, extraction and naming.

## Putting them back

Nothing was deleted or rewritten, so it is a move rather than a port:

1. `fmt_diskimage.c` → `src/`, or paste its two functions back into
   `src/fmt_stubs.c`. It already `#include "unc_internal.h"` and needs
   nothing else.
2. Declare both probes in `src/unc_internal.h` and call them from
   `unc_sniff` in `src/unc_engine.c`, in this order and immediately after
   `unc_arc_probe`: Disk Copy first, then the volume probe. Both belong
   ahead of the text probes (BinHex, uuencode, btoa, MIME, base64),
   whose tests are scans rather than fixed offsets.
3. `include/macextract.h` still carries `UNC_FORMAT_DISKCOPY_RETIRED`, a
   reserved slot kept so that no enumerator after it changed value when
   the probe went. Rename it and append a new enumerator for the volume
   probe — appending is the rule, so nothing shifts.
4. Add both to the table in `unc_engine.c` with `extractable` 0.
5. `unit_diskimage.c` → `tests/unit_formats.c`, and call the two
   functions from `test_all` in `tests/unit_main.c`.
6. `run_diskimage.py` → `tools/`, and a line in `ci.sh`. It needs
   `reference/pycdlib` (a pure-Python ISO writer, which
   `tools/fetch_references.sh` fetched until 2026-08-26 — the entry is in
   that file's history), `hformat` from hfsutils, and `deark`. It skips
   each part by name when its tool is missing.

## What graded them, if it has to be re-graded

- **deark** identified every case the probe claimed: `hfs`, `apm`,
  `iso9660` and `cd_raw` modules, all four still in `reference/deark`.
  The probe was transcribed from those modules' `identify` functions.
- **pycdlib** wrote the ISO; `lsar` confirmed it independently.
- **The real images are still on this machine** and cost nothing to
  re-run: Retro68's 800K `.dsk` volumes under `/opt/Retro68-build`, the
  emulator tiers' disks under `~/.cache/macextract` (up to the 2 GB
  `qemu-ppc/MacOS9.img`), and `vmac/spacesaver/STUFFIT_DLX_SS_501.ISO`, a
  224 MB Toast hybrid CD that is Apple-partitioned rather than ISO 9660.
- **The negative tests were mutation-tested**, one corroborating field at
  a time, and the APM one only became real when it was rewritten to spoil
  the block the probe is entered from rather than the one it checks
  second. If these are restored, keep that: it is the case that failed a
  mutant.
