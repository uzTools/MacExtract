# `tests/ovlbox/` — the overlay loader, off the Macintosh

The application's fourteen `'OVLY'` images were reached by no automated test
until 2026-09-26: they exist only in a Retro68 build, so the 932-fixture
corpus, the robustness variants and the sanitiser builds all exercise the
decoders as ordinary linked code, and whether an image is FOUND, RELOCATED,
KEPT, RELEASED or RE-READ was answered only by emulator tiers, by hand
(OPEN_ITEMS.md, *The overlay loader*). Three defects lived in that gap.

This box closes the Linux-side half of it. `mac/ovl_load_eager.c`,
`mac/ovl_load_lazy.c`, `mac/ovl_reloc.c` and `mac/ovl_shim.c` are compiled
**unmodified** against the stub Toolbox headers here, the images are built from
the same sources with the same flags by `tools/overlay/mkoverlay.sh`, and the
result runs natively under ASan and big-endian under `qemu-m68k`.

What the mock does that a Macintosh does not, on purpose:

- **Every relocatable block moves on every allocation.** A real Memory
  Manager only compacts when it must, so a loader that depends on an
  unlocked handle staying put works there most of the time. Here it never
  does.
- **Each handle is its own allocation**, so a relocation or a `BlockMoveData`
  that runs past the image end is an ASan report rather than a corrupted heap.
- **The flush route is live and counted.** `gFlushHas`/`gFlushCalls` are
  readable only on the completion alert of a probe build on a real machine;
  here the counts are assertions.

What it CANNOT see: `tests/ovlbox/ovlbox.c`'s header says, and TESTING.md
(*The overlay loader, off the Macintosh*) repeats it — no CPU cache, no
Resource Manager, no fragmentation, and not the Retro68 toolchain's codegen.
