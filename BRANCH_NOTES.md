# Branch `overlay-eager` — one disk read at launch, then throw most of it away

**Branched from `selective-loading`**, and it carries all fifteen of that
branch's images. Same images, opposite lifetime: `selective-loading` reads the
one it needs when it needs it; this reads **all fifteen as a single resource
while the boot disk is certainly still in**, and releases everything the
archive cannot want as soon as the sniff says what the archive is.

**Status, 2026-09-24: measured on an emulated Mac Plus at 1 MB.** A bare
StuffIt 5 archive is granted **734,656 B** with the bundle released and only
the ciphers kept; an LZH gets **752,898 B**, keeping only its own decoder,
against 650,692 B with no overlays at all. 71/71 fixtures extract byte-exact
at 4 MB and at 1 MB, and 69/71 on a 512 KB machine (*Merged main*, below).
**71/71 on System 7.0.1 at 4 MB and 22/22 on Mac OS 9.2, 2026-09-25** — the
first runs of this configuration anywhere above System 6, and both equal to
what a resident build scores (*Both tiers above System 6*, below).

## Both tiers above System 6 — 2026-09-25

**Claim: the two tiers OPEN_ITEMS.md said had never seen this configuration
have now seen it, and neither distinguishes it from a resident build.**

| tier | overlays | resident |
|---|---|---|
| System 7.0.1, 4 MB, `run.py --system Sys7.img` | **71/71** | 71/71 (FORMATS.md, *System 7 tier*) |
| Mac OS 9.2, `os9.py --autotest` | **22/22**, one sweep | 22/22 (FORMATS.md, *Mac OS 9 tier*, via `--launch`) |

**Mac OS 9.2 goes through `--autotest`, not `--launch`**, because `-D` is a
build switch for the autotest application and the harness refuses it
otherwise — correctly, since the alternative is silently driving the resident
build.

**That route scored three healthy fixtures as failures, and it took a control
plus a second look to see it was the harness.** The first sweep read 19/22:
`.Z` and `.gz` came back as `archive` against Linux's `synth-exo-Z` with the
data byte-exact, and a detect-only `.rar`'s correct `ret=-6` counted as a
failure. The same three failed identically with NO overlays — which says only
that the defect was in neither build, and was read at first as "19/22 is this
route's score". Both halves were harness defects and both are fixed
(`tools/vmac/README.md`, *`--autotest` scored three healthy fixtures*;
BLOCKERS.md for the withdrawn figure). **An A/B that agrees locates a
difference, never a correctness.**


## The instruction cache that nothing flushed — 2026-09-25

**Claim: both fixup sites write executable bytes as data and then execute
them, and neither flushed the instruction cache, which Inside Macintosh
requires.** `ovl_bundle_fixup` rewrites longs inside the bundle at preload;
`ovl_keep` copies an image with `BlockMoveData` and fixes it up again at the
copy's address.

**The rule is documented rather than inferred.** Inside Macintosh: Memory,
chapter 4, *Stale Instructions*: "you must flush the instruction cache every
time you modify executable instructions in memory", naming modified jump-table
entries and patches installed by copying code. `_BlockMove`, `_Read`,
`_LoadSeg` and `_UnloadSeg` flush on the application's behalf.
**`BlockMoveData` is not among them** — it is the variant trap, 0xA22E against
`_BlockMove`'s 0xA02E — so `ovl_keep`'s copy is exactly the case the chapter
is about.

**Two traps, and the toolchain uses the older one.** Retro68's own relocator
flushes at these same two moments — after `Retro68ApplyRelocations` and after
patching each jump-table entry (`libretro/relocate.c`,
`libretro/MultiSegApp.c`) — by calling `FlushCodeCache` (0xA0BD). Inside
Macintosh documents `FlushInstructionCache` as `_HWPriv` (0xA198) selector 1,
which on a processor with a copy-back data cache flushes the DATA cache first,
"to ensure that any instructions subsequently copied to the instruction cache
are not copied from stale RAM" — the 68040 case, and precisely what a
`BlockMoveData` copy creates. `ovl_flush_code()` therefore prefers `_HWPriv`
and falls back to 0xA0BD, each behind a trap-availability probe, because a 64K
ROM has neither.

| | before | after |
|---|---|---|
| overlay build, resident `CODE` | 53,780 B | **53,920 B** |
| overlay build, A5 | 19,148 B | **19,136 B** |
| `MacExtract.bin` | 214,528 B | **214,656 B** |

The default build is untouched: none of it compiles into one.

### What no tier here can show, and what one of them did

**Neither emulator has a cache to go stale.** Mini vMac is a 68000, and Apple
documents that the 68LC040 Emulator — how the Mac OS 9 tier runs this
application — **ignores** requests to invalidate the 68040 instruction cache,
while telling developers to keep issuing them for 680x0 machines (Inside
Macintosh: PowerPC System Software, *The 68LC040 Emulator*). So no sweep
available here can fail for want of the flush, and a green one is not evidence
that it works.

`fc` — which route the machine offers, 0 none, 1 `_HWPriv`, 2
`FlushCodeCache` — and `fn`, calls made, therefore ride the
`-D UNC_AT_BUDGET` completion alert. `derived-BootTime.cpt` through
`interactive.py`, same fixture both times:

| tier | | |
|---|---|---|
| System 6.0.8, 4 MB | `fc=0 fn=0` | neither trap is live on the Plus's ROM |
| System 7.0.1, 4 MB | **`fc=1 fn=3`** | `_HWPriv` is patched in, and fires |

Three is the right number: one for the bundle fixup at preload, one for each
of the two images an unencrypted Compact Pro keeps. Both runs extracted
completely at `pk=23889`, so **the call executes in the right places and costs
nothing on a machine with no cache** — which is as far as this environment can
take it. Real 68020-and-up silicon is MANUAL_TESTS.md §2's.

### The alarm that fired on a healthy archive

**Claim: `wa` — an image wanted after the release, which this file calls a
thing that must never happen — fires on every unencrypted Compact Pro.**
Measured 2026-09-25: `derived-BootTime.cpt` reported `wa=128` with `e1=0` and
the extraction complete.

**Why.** `fmt_cpt.c`, `fmt_sit.c` and `fmt_packit.c` call `unc_crypt_free` at
cleanup unconditionally, encrypted or not, and the resident `unc_crypt_free`
is a no-op on a NULL table. A Compact Pro whose directory let the release drop
the ciphers arrives there with nothing to free and no image to do it with.
Nothing leaks: `cr->tab` is non-NULL only if a key setup ran, which would have
kept the image.

**Consequence: the free path asks quietly** — `ovl_image_q(OVL_ID_CRYPT, 1)`,
every other caller unchanged — and the same run then reads `wa=0` with the
same output and the same peak. **An alarm that fires when nothing is wrong
cannot be read when something is**, and `wa` is the field that found the
preload bug (*Withdrawn: "one disk read at launch"*).


## The build could go stale, and every image was — 2026-09-25

**Claim: an image rule depended on its own `.c` files and on almost none of
the headers those files include, so a header edit rebuilt the resident
application and left the images as they were.** Counted with `gcc -MM` over
each rule's own sources against its `DEPENDS`: the fifteen rules between them
name **none** of the 26 headers their sources actually include, and
`touch tools/overlay/overlay.h` regenerated **7 of 15** images — that header
was listed by seven rules and omitted by eight, which is what a list copied
fifteen times does.

**Why this is worse than a stale object file.** `overlay.h` is where the
`OVL_*` entry-point ids live and `include/macextract.h` is where
`UncEntryInfo` lives, and an image compiles against both — a decoder overlay
compiles the decoder. Neither disagreement is a link error: the host calls an
id the image numbers differently, or hands it a struct the image lays out
differently, and the first symptom is on the Macintosh.

**The fix is one list, and headers by glob.** `OVL_DEPS` holds what every
image is built from — `overlay.ld`, `mkoverlay.sh`, `mkreloctrailer.py`,
`ovl_rt.c` — and `file(GLOB OVL_HDRS CONFIGURE_DEPENDS ...)` adds every header
under `src/`, `include/`, `third_party/zlib/` and `tools/overlay/`. Names are
what drifted, so the fix uses no names, and `CONFIGURE_DEPENDS` re-globs at
build time so a header added tomorrow is covered by itself. **`touch
src/unc_internal.h` now rebuilds 15 of 15 images, in 9.4 s for the whole
build**, and a no-op rebuild still regenerates nothing.

### The runtime net: the compiler emits calls that appear in no source file

**Neither `-fno-builtin` nor `-fno-tree-loop-distribute-patterns` stops gcc
calling libc from an image.** With both, at exactly the flags `mkoverlay.sh`
uses, a 400-byte struct assignment still emits a call to `memcpy` (measured
2026-09-25). The flag added on 2026-09-19 covers the one idiom that bit then —
the zeroing loop main's fused Compact Pro stages arrived with — and the
optimiser has more idioms than this build has flags.

`tools/overlay/ovl_rt.c` defines `memcpy`, `memmove`, `memset` and `memcmp`,
is compiled into every image, and `--gc-sections` drops every one nothing
calls. **Cost: 0 bytes, measured rather than argued** — 14 of the 15 images
are byte-identical to what they were before the object joined the link, and
`MacExtract.bin` is the same 214,528 B. What moved is `ovl_exo.r`, whose
hand-written `memcpy` for zlib this replaces (same 27,252 B), the bundle that
carries it, and the application that carries the bundle. The DEFAULT build is
byte-identical too, checked on the shipped payload rather than on
`MacExtract.code.bin`, whose last 4 bytes differ between two clean builds of
the same source.

**It can fail, which was checked before it was trusted**: emptying
`ovl_rt.c` fails the link with `undefined reference to memcpy` from zlib's
`inflate`. `malloc` and `free` deliberately stay in `ovl_exo.c` — a stub that
answers NULL is right for zlib and wrong as a default for whatever reaches for
malloc next, and a link failure is how that gets noticed.

**What the net cannot see:** these are byte-wise, and resident code calls
Retro68's libc, so an image that pulls one onto a decoder's hot path is slower
than the same code resident, with nothing failing to say so. `mkoverlay.sh`
now prints `runtime: memcpy` beside the image that took one — today only
`ovl_exo.r`.


### The resource ids were written three times, and nothing compared them

**Claim: the id an image answers to lived in `overlay.h`, `mac/CMakeLists.txt` and the bundle's own argument
list — and two of them disagreeing
is not a build error.** The shim asks `GetResource('OVLY', OVL_ID_LZH)`; the
resource is numbered by whatever the build passed as `OVL_ID=131`. Renumber
one and not the other and the build is green and the image is simply not
found, which reaches the user as a per-entry memory error.

**Every id now comes from `overlay.h`, by name** — `tools/overlay/ovlid.py`,
called by `mkoverlay.sh` and by `mkbundle.py`, and the bundle's own `OVLY` id with it. A NUMBER is refused rather
than passed through, because accepting one is how the second copy of the table
comes back. Renaming `OVL_ID_LZH` in `overlay.h` now fails the build with
*"ovlid: overlay.h defines no OVL_ID_LZH"*, which was run. **Every image is
byte-identical across the change**, which is what says no id moved while the
table was being removed.

## Merged main — 2026-09-24

**126 commits of main, and three of them crossed the overlay boundary.** The
default build is unchanged in shape; the overlay build needed five files
changed, and `ci.sh`'s variant 4b is what caught all three, which is what it
was added for.

| resident | 2026-09-09 | after the merge |
|---|---|---|
| default build, `CODE` | 150,296 B | **153,804 B** |
| default build, A5 | 44,264 B | **37,956 B** |
| overlay build, resident `CODE` | 53,004 B | **53,780 B** |
| overlay build, resident A5 | 18,804 B | **19,148 B** |

The A5 world FELL 6,308 B, and that is main's doing rather than this
branch's: the DES SP tables and Compact Pro's CRC-64 table stopped being
const data and are built at key setup instead (DECISIONS.md 2026-09-19, the
transient tables). It is also what made the merge work rather than compile —
those three key setups now take an allocator and can fail, so `OvlArgs`
carries a `void *al`, `unc_crypt_cpt` and `unc_crypt_packit_des` return what
they used to discard, and `unc_crypt_free` is entry point `OVL_CRYPT_FREE`
and a forward. Freeing goes through the image because the block is
`unc_crypt.c`'s own; it is always reachable when there is anything to free,
since `cr->tab` is non-NULL only if a key setup ran and
`ovl_release_if_unwanted` runs once after the sniff and never during an
extraction.

**An overlay links no libc, and `-fno-builtin` does not stop gcc calling
it.** Main's fused Compact Pro LZH and RLE stages zero a window with a plain
`for` loop, and the loop-distribution pass rewrote that into a call to
`memset` — undefined in an image, so `ovl_cptdd.r` would not link.
`mkoverlay.sh` now compiles with `-fno-tree-loop-distribute-patterns`; the
loop is emitted as written and runs once per fork. `unc_fork_write`, which
main's LZH rewrite added, is a forward.

**Re-run on the machine, 2026-09-24**, because `ci.sh` variant 4b only
COMPILES this configuration and the Linux suites do not exercise the overlay
mechanism at all. All with `-D UNC_AT_OVERLAY` over `tools/vmac/sample.txt`:

| tier | | |
|---|---|---|
| `run.py --emu mv-4M` | **71/71** | |
| `run.py --mem 1M` | **71/71** | |
| `sys30.py --emu mv-512Ke` | **69/71** | `synth-dd-m5.dd` and `derived-Library_ISBN_Barcoder.sit`, both per entry |

The two that do not pass are the two FORMATS.md (*512 KB machines*) says
cannot: the Barcoder writes 33 of its 34 entries with one errored, and
`synth-dd-m5.dd` is a single-entry archive whose 405,520 B block is refused.
`derived-a2basic.dmg.sit` and `derived-Cool_Tools__.sit` both PASS, which
`main` does not manage on this tier — and `Cool_Tools` peaks at 300,834 B
here against `selective-loading`'s 315,317 B, which is this branch's release
doing what it is for.

**The cipher path was driven separately**, because `run.py` has no password
and `crypt-04.hqx` never reaches a key setup:
`interactive.py --password -D UNC_AT_OVERLAY` extracts a StuffIt classic DES
archive, refusing one password and taking the next — so `unc_crypt_sit`
through the new `OvlArgs.al`, the DES table built on the heap, `MKey` out of
the resource fork and `unc_crypt_free` through `OVL_CRYPT_FREE` all ran on
the machine, with the crypt image still resident at free time. That last
part was the hypothesis this entry started with; it is now measured.

## DART, overlaid — 2026-09-09

`main` gained DART (M52) and it came in **resident**. It is now
`OVL_ID_DART` in the bundle, built by `tools/overlay/ovl_dart.c`.

**Merging it in had already broken this branch's own configuration, and
every check passed anyway.** A resident `unc_dart_extract` calls
`unc_lzah_decode` — DART's "best" method is LZHUF — and that lives in the
codecs image, so `UNC_AT_OVERLAY=1` would not LINK. `ci.sh` never built
that configuration. It does now, as variant 4b: **a branch whose feature
is a build configuration has to build it.**

### The split

DART has **no signature**, so its probe reads the whole block-length table
and checks it against the file's size — and the decoder needs the same
reader. `src/fmt_dart_probe.c` holds `dart_parse`, `dart_kind` and
`dart_chunk_bytes`, and is **resident AND compiled into the image**, which
is what `ovl_spacesaver.c` already does. ~400 B duplicated beats calling
back into the host for a header reader, or loading a decoder to decide a
file is not a DART.

### What the release decision gains, which is this branch's own question

`ovl_release_if_unwanted` had no case for DART, so it fell to `default` —
keep the whole bundle, the answer that cannot be wrong. It now keeps
`OVL_ID_DART` and releases the rest, with `crypt = 0`: DART carries no
encryption of any kind, the format has no flag for one and no reference
describes one.

| | bytes |
|---|---|
| the fifteen images in the bundle | 148,770 |
| a DART keeps: its own 2,632 + codecs 6,224 | **8,856** |
| released for a DART archive | **139,914** |

Codecs is kept unconditionally and has to be: LZHUF is there.

| | before | after |
|---|---|---|
| default build, `CODE` | 150,220 B | **150,296 B** (+76) |
| default build, A5 | 44,244 B | **44,264 B** (+20) |
| overlay build, resident `CODE` | *would not link* | **53,004 B** |
| overlay build, resident A5 | *would not link* | **18,804 B** |

### Proven on the machine

`tools/vmac/run.py --emu mv-4M --expect -D UNC_AT_OVERLAY` over
`test1-best` (LZHUF, so it reaches the codecs image from inside another
image) and `Studio8_Program.dart` (RLE): **2/2 byte-exact**, 838,484 B
each. **The negative was run**: the shim pointed at a nonexistent id gives
0 files, and there is no resident decoder to fall back on.


## Fifteen images: BinHex and btoa stop travelling with MIME

**Opening a `.hqx` used to load 15,864 B of decoder. It now loads 2,148 B.**

The text group existed because MIME decodes base64 and uuencoded parts and
calls straight into both, and an overlay cannot call another overlay. But
`nm` over the objects says only MIME does that: **BinHex and btoa call
nothing and nothing calls them.** They were in the group by association, not
by need.

| image | was | now |
|---|---|---|
| MIME + uu + base64 | 15,864 B | **11,450 B** |
| BinHex | — | **2,148 B** |
| btoa | — | **2,756 B** |

BinHex is the envelope a Macintosh user meets most — a `.hqx` is how nearly
every Macintosh file crossed the internet — so it is the one image worth
having alone. Nothing else changes: same formats, same behaviour, 254 B more
in the download, and `main` cannot be affected because `main` has no images.

**69/69 at 1 MB with the new grouping**, and a `.hqx`, a `.uu`, a `.btoa` and
a `.sit` all extract byte-exact.

**The rule this makes explicit: group by the CALL GRAPH and nothing else.**
Measured with `nm`, not assumed — the first grouping put five formats
together because they are all "text", which is a category in a reader's head
rather than in the code.


## Parity with `selective-loading`, 2026-09-03

The four tiers and the segmented sweep, run on both:

| | this branch | `selective-loading` | `main` |
|---|---|---|---|
| 4 MB, System 6.0.8 | **69/69** | 69/69 | 69/69 |
| 1 MB, System 6.0.8 | **69/69** | 69/69 | 69/69 |
| System 3.0, 1 MB | **69/69** | 69/69 | 69/69 |
| System 3.0, 512 KB | **67/69** | 67/69 | 66/69 |
| `segcheck.py` | 6/9 | 6/9 | 6/9 |

Identical, including which three `segcheck` cases fail — the ones staged by
`interactive.py`, which fail on `main` too and are written up there.

**So the lifetimes cost nothing against each other any more.** What was a
one-archive gap at 512 KB closed with `MoveHHi`, and what is left between the
two branches is one disk read at launch against one read per format, with the
same formats extracting either way.

## Segmented sets, with MoveHHi and thirteen overlays

**Asked because the segments path is separate code and `MoveHHi` changes where
things land in the heap it shares.** Measured 2026-09-03:

| | |
|---|---|
| four-part Compact Pro set, 1 MB | **PASS**, 9 files byte-exact, budget **728,270 B** |
| the same set on a **Macintosh 512Ke** | **PASS**, 9 files byte-exact |
| `segcheck.py`, the six cases `run.py` can stage | **6/6** — `sit-scattered`, `cpt-middle`, `cpt-truncated`, `chain`, `mimeseg`, `ddseg-real` |

**A segmented set on a 512 KB machine had never been run before**, on any
branch. It works.

The budget is up from 670,836 B — the segments release site, twelve more
images out of the resident set, and `MoveHHi`, which between them took a
multi-part set from **worse than having no overlays at all** to 78 KB better
than `main`.

`segcheck.py`'s other three cases — `zip-named`, `split-named`, `wrapped` —
fail here, and fail identically on `main` and without overlays. They are the
three staged by `interactive.py` rather than `run.py`; the fault is on that
side and is written up on `main` in OPEN_ITEMS.md, because it is not this
branch's.

## Open, and reduced but not explained: two bytes in UncEntryInfo

**Adding a field to `UncEntryInfo` makes two fixtures roughly twenty times
slower on the Macintosh, and nothing else changes.** Found while trying to let
this branch ask an archive whether it is encrypted; the feature turned out to
be unnecessary (see below), but the effect is real and is written down here
because it will bite whoever adds a field next.

**The reproduction**, on this branch or `selective-loading`:

1. add `uint8_t encrypted;` to `UncEntryInfo` in `include/macextract.h` —
   anywhere in the struct, and set by nobody;
2. `rm -rf build/mac-autotest`
3. `tools/vmac/run.py fixtures/derived-LHA_Expander_1.0.3.sea --mem 1M`

Result: `TIMEOUT — app alive but still extracting after 300s`, against **5.1 s**
without the field. `derived-Terrainman_2.0__.sea` does the same. Both are
DiskDoubler self-extracting archives; every other fixture in the 69 is
unaffected, at 1 MB and at 4 MB alike.

**What it is not.** Not the overlays — the default build does it too. Not the
stack: `UNC_STACK_BUMP_KB=48` changes nothing. Not layout — the field at the
END of the struct behaves the same. Not the engine: the Linux CLI, the
native ASan/UBSan Mac-sink build and the **big-endian m68k** build under
`qemu-m68k` all extract it correctly and quickly.

**The one clue is the size.** `uint8_t` and `uint16_t` both grow the struct by
2 bytes after padding, and both hang. `uint32_t` grows it by 4, and **passes**.
So the sensitivity is to the struct's total size in a way that 4 satisfies and
2 does not, which points at the Macintosh Memory Manager's block placement
rather than at anything in this repository's code — a shifted allocation
landing somewhere that makes every later one compact the heap would look
exactly like this. *Hypothesis, not measured.*

**Nothing is built on it.** The `encrypted` field was reverted. A 4-byte field
"works" and is exactly the kind of unexplained workaround this repository does
not ship — an unreduced root cause is a hypothesis, and building on one is
building on sand.

## MoveHHi: the eager trade cost nothing after all

**One line, and this branch matches `selective-loading` at 512 KB.**

| tier | `selective-loading` | this branch | `main` |
|---|---|---|---|
| 1 MB, System 6.0.8 | 69/69 | **69/69** | 69/69 |
| System 3.0, **512 KB** | 67/69 | **67/69** | 66/69 |

`derived-a2basic.dmg.sit` extracts here now, as it does on the other branch.

**The blocker was never the ciphers; it was fragmentation.** The kept images
are locked for the rest of the run, and `NewHandle` puts them wherever it
likes — in the middle of the heap the released bundle just vacated. Measured
on a Macintosh 512Ke: the engine was granted **317,838 B** and the entry still
failed, with `gRefusedWhy` = 2 — `NewPtr` returning NULL for a 205 KB block
against a largest free block of **169,298 B**. The memory was there, in two
pieces. `MoveHHi` before the `HLock` puts them at the top where a locked block
belongs, and the hole below stays whole.

**What that cost to find: a day chasing the wrong cause.** The gap had been
measured at 15,748 B and attributed to the ciphers this branch must keep for a
format that MAY encrypt, which was true and irrelevant — releasing them
raised the budget to 317,838 B and the archive still failed. **A number that
explains a gap is not the same as a cause**, and the budget said so all along:
`gRefusedWhy` = 2 means the heap could not do what the budget said it could,
which is fragmentation and not shortage. That distinction is in the shell's
own comments, written by somebody who knew, and it took an afternoon to read
it.

## The tiers, 2026-09-03: the trade costs exactly one archive

| tier | `selective-loading` | **this branch** | `main` |
|---|---|---|---|
| 1 MB, System 6.0.8 | 69/69 | **69/69** | 69/69 |
| System 3.0, **512 KB** | 67/69 | **66/69** | 66/69 |

**Superseded 2026-09-03 by the section above: `MoveHHi` closed this.** What
follows is what the tier said before that, kept because the reasoning is what
sent the next day's work in the wrong direction.

**`derived-a2basic.dmg.sit` extracts on a Macintosh 512Ke under
`selective-loading` and does not under this branch.** That is the whole of the
difference, and it is the 15,748 B this file has been calling "the ciphers"
since 2026-09-02, now expressed as a capability rather than a number: a `.sit`
may carry an encrypted entry, so loading eagerly means keeping the cipher
image whatever the archive turns out to hold, and that archive needs
246,734 B in one allocation against a machine that has barely more.

So the trade is priced on both sides at last. **One disk read at launch and no
access afterwards, against one archive in sixty-nine on the smallest machine
this application runs on.** Which of those a user would rather have is a real
question, and not one this repository can answer for them.

## The three methods, and what each leaves the decoder

**Re-taken 2026-09-24 at 1 MB on System 6.0.8, all three built and run in one
session, same fixtures, same instrument.** The number is what the engine is
GRANTED — `mal_take_budget` at its first allocation, so every overlay the run
is going to load has already loaded. The 2026-09-02 figures this replaces are
in the column beside each one; nothing had re-taken them across four more
overlays and two merges from `main`.

| the archive | A: no overlays | B: `selective-loading` | C: this branch |
|---|---|---|---|
| StuffIt 5, bare | 650,692 B *(650,548)* | **745,358 B** *(708,916)* | 734,656 B *(693,168)* |
| LZH, bare | 650,692 B *(650,548)* | **753,792 B** *(702,104)* | 752,898 B *(701,688)* |
| Compact Pro, bare | 650,692 B *(650,548)* | **747,576 B** *(694,172)* | 746,682 B *(692,988)* |
| MacBinary → StuffIt, through the real UI | *not re-taken* | *(705,780)* | *(689,108)* |
| disk access after the archive is chosen | none | **one, per format** | **none** |

**Column A does not move with the archive**, and that is the control: with
every decoder resident the engine gets the same heap whatever it decodes. It
also barely moved in three weeks — 650,548 to 650,692 B — which is what says
the 36–54 KB the other two columns gained is THEIRS and not something `main`
handed the whole application. Both overlay methods now beat A by 84–103 KB,
against 44–58 KB when this was first measured.

The last row was driven through the real UI by `interactive.py` and is **not
re-taken here**; the three above it are `run.py --mem 1M -D UNC_AT_OVERLAY
-D UNC_AT_BUDGET`. Two different StuffIt 5 fixtures were run as a control and
report the same budget to the byte, which is what says the figure is a
property of the FORMAT — of which images are kept — and not of the file.

**Where B and C differ is the ciphers.** A format that MAY carry an encrypted
entry forces this branch to keep the cipher image, because it must decide what
to throw away before it knows whether any entry is encrypted;
`selective-loading` never loads the ciphers unless an entry asks. That was
15,748 B and is now **10,702 B** (2026-09-24), because the cipher image
itself shrank from 15,324 B to **9,800 B** when `main` stopped carrying the
two DES SP tables and Compact Pro's CRC-64 as const data and built them at
key setup instead (DECISIONS.md 2026-09-19, the transient tables). Both
figures are measured — `mkoverlay.sh` prints the image size. And **two of
the five formats no longer pay it**: Compact Pro and
zip keep a per-entry flag in a directory that can be walked before anything is
decoded, so `unc_archive_encrypted()` answers for the whole archive and the
ciphers are kept only when one is actually encrypted. The Compact Pro row is
within **894 B** of B, which is the query's own code, and LZH — which never
keeps the ciphers — is the same 894 B, so that is the floor of the method
rather than anything about either format. StuffIt,
StuffIt 5, PackIt and ARC still pay: the first three flag encryption per entry
with no directory to consult, and ARC does not flag it at all.

**And the query refuses to answer for a PART of a multi-part set**, which is
the case that would have broken it. A zip keeps its directory at the END, so
the first part — the one a user is told to open, and the only one they can be
expected to open — has no directory at all; a Compact Pro set puts its index
in the last segment and a first part's index offset is zero. The segment
probes claim such files before the plain ones do, so those paths should be
unreachable, and they are guarded anyway: the cost of being wrong is not a
disk access but a capability, since there is no reload. `tools/run_crypt.py`
checks nine cases including **every part of a spanned encrypted set with the
format forced**, because sniffing alone can never reach the guard. Removing
the guard makes that suite fail, which was checked before it was trusted.

**What C buys for what remains is the disk.** `selective-loading` reads an
overlay after the archive has been chosen, and on a Mac Plus with one drive
the application's floppy may have been ejected by then. This branch reads
once, at launch, while the boot disk is certainly in. **That is the trade,
priced: about 10.7 KB of budget against a disk access at an unpredictable
moment** for a format that must keep the ciphers, and 894 B for one that need
not. It was about 16 KB when this was written; the cipher image shrinking is
what moved it.

## The second release site: multi-part sets

**A segmented set used to pay for the bundle and get nothing back**, because
`ovl_release_if_unwanted` was called only from the sniff-and-dispatch path and
a set goes down `unc_extract_segments`. Measured on a four-part Compact Pro
set (`segcheck.py`'s `cut_cpt`, opened at the first part), 1 MB:

| | budget |
|---|---|
| no overlays | 650,548 B |
| the bundle held all run — before 2026-09-02 | 631,300 B |
| **the release called from the segments path too** | **670,836 B** |

It was **worse than not having the mechanism at all**, by 19,248 B, for that
one shape of input. It now beats it by 20,288 B, and the set still extracts
byte-exact — 9 files.

**The SCHEME is not the format inside, and the release has to know the
difference.** A Compact Pro or spanned-zip set is read by that format's own
reader over the joined parts, so the first keeps the Compact Pro decoder and
the second keeps nothing (the zip reader is resident). A StuffIt set, a
DiskDoubler `SPLT`, a plain `.NNN` split and a `message/partial` set all join
to a FILE that a LATER layer sniffs — what that turns out to be is unknown
here, so they keep the whole bundle, exactly as an envelope does.

**Neither set can be asked whether it is encrypted**, because a set's
directory lives in its LAST part and `unc_archive_encrypted` refuses on a
part. So both keep the ciphers, which is why 670,836 B is short of the
692,988 B the same archive gets whole: two images kept instead of one.

## Withdrawn: "one disk read at launch"

**It was not true in the build a user runs, for as long as this branch has had
a bundle.** `ovl_preload()` was called from the AUTOTEST `main()` and not from
the interactive one, so the shipping application never preloaded at all: the
shim fetched the bundle lazily on first use — a disk access *after* the
archive has been chosen, which is the precise thing this branch exists to
avoid, and the thing it was measured as avoiding.

**How it surfaced.** Not by review: by forbidding the reload. Once
`ovl_image()` refused to re-read the resource fork, an encrypted StuffIt
archive stopped decrypting, and the diagnostic said `wa=128` — the ciphers
were wanted after the release. Three probe fields (`wa`, `kf`, `rf`) took two
runs to say that the keep had succeeded, the release had run on the right
format, and the bundle had nonetheless never been there.

**Cost: every C-column figure taken through `interactive.py` before
2026-09-02 was measured on a build that loaded nothing at launch**, which
flattered it — the envelope row read 705,352 B and is **689,108 B** once the
preload actually happens. The autotest columns were never wrong, because the
autotest is the `main()` that had the call.

**The lesson is the repository's own, one level along.** A ballast referenced
from only one `main()` had already cost three measurements
(FORMATS.md, *What the application costs the engine*). This target has two
`main()`s and **"which `main()`?" is worth asking of every launch-time call**,
not only of ballast.

## The bundle

`tools/overlay/mkbundle.py` writes the six images into ONE `OVLY` resource,
69,700 B, with a twelve-byte directory entry each: id, offset, length, all
big-endian and read byte-wise. Six resources would be six disk reads, and
paying the disk once is the entire argument for loading eagerly.

`ovl_preload()` reads it from **both** `main()`s — see the withdrawn claim
above for what happened when it was in only one. `ovl_release_if_unwanted()` then copies
out the one or two images the sniffed format can want — the decoder, and the
ciphers where an entry might be encrypted — and releases the bundle.

| what the archive is | kept | released |
|---|---|---|
| LZH, DiskDoubler, Now Compress, SpaceSaver | that decoder | everything else |
| Compact Pro, ARC | that decoder + ciphers | the rest |
| StuffIt, StuffIt 5, zip, tar, … | ciphers only | all six decoders |
| an ENVELOPE — BinHex, MacBinary, gzip, MIME … | the whole bundle | nothing |

**An envelope keeps everything, and that is not laziness.** A `.sit.hqx`
sniffs as BinHex: what is under it is unknown until it has been unwrapped, so
releasing on the outer format would strand the archive inside. The shipping
application then opens the unwrapped file as a NEW layer with its own sniff
and its own release, so the second layer gets the memory back.

**Measured, after being a hypothesis for one commit.** `run.py` drives the
autotest build, whose `main()` extracts ONE layer, and the envelope chaining
lives in `ExtractOne`, which only the interactive `main()` calls — so the
autotest reports 638,696 B for a MacBinary-wrapped archive, the bundle still
held, and that figure is the harness rather than the application.
`-D UNC_AT_BUDGET` now prepends `bg=` and `pk=` to the completion alert, and
`interactive.py` driving the real UI on the same archive reports
**705,352 B**: the second layer releases the bundle, exactly as argued. **An
instrument that cannot reach the path is not evidence about the path**, and
the difference between the two numbers is 66,656 B of nothing but harness.

**And nothing needs crediting back.** The release runs immediately after the
sniff, and the budget is taken at the engine's FIRST ALLOCATION
(`mal_take_budget`), which is later — so freed heap is simply part of what the
engine is measured against. A `mal_credit()` path was written, measured to
change nothing, and removed: code no run executes is worse than no code.

## The mechanism, proven 2026-08-30

`tools/overlay/` builds a flat, position-independent image, carried as an
`OVLY` resource and loaded only when wanted. Run on an emulated Mac Plus with
`-D UNC_AT_OVERLAY`, the grid came back:

| slot | value | meaning |
|---|---|---|
| `nfiles` | **20299** = `0x4F4B` | the blob read its own PC-relative table |
| `errors` | **66** | `GetHandleSize`, matching the built blob exactly |
| `ret` | **2541233361** | a callback through the host vector table, byte-identical to what `unc_crc32` returns for the same bytes on Linux |

So all five links hold: a `-mpcrel` image with **zero** relocations; stored as
a resource; `GetResource`d on demand; jumped to at the start of a **locked**
handle; reading its own data; and calling back into the application through a
vector table.

**Why -mpcrel is the whole trick.** It turns internal references into
PC-relative ones the *linker* resolves, so nothing is left to patch at run
time — no relocation format, no loader beyond `GetResource` + `HLock`. The
price is the ±32 KB that PC-relative addressing reaches, which bounds an
overlay and is checked by `mkoverlay.sh`.

**What the build refuses**, because each would fail silently on the Mac
otherwise: any surviving relocation, any `.data` or `.bss` (an overlay has no
A5 world of its own), and any image over 32 KB.

**The shipping application carries no overlay.** `OVERLAY_R` is empty unless
`UNC_AT_OVERLAY` is set. The code ceiling is 147,700 B, raised from 147,588
for the budget fix below; it was 147,268 B when this branch was cut.

## Why the idea came back

Only CODE costs the engine anything on a Macintosh (FORMATS.md, *What the
application costs the engine*): `CODE` resources are handles inside the heap
`FreeMem()` reports, and the A5 global world is outside it. So the one lever
that buys budget is **having less code resident**, which is what selective
loading is.

Two cheaper levers were taken first and are already on `main`: compiler size
flags (780 B, +0.82 % slower) and re-pricing the reserve (32 KB, free). The
reserve alone delivered forty times what the flags did, which is why this is
worth pricing properly rather than assuming.

## What it would be worth — measured

Per-object code in the shipping Mac build, `m68k-apple-macos-size`, 2026-08-30:

| | code |
|---|---|
| all objects | 178,239 B |
| what a StuffIt-family decoder needs | 74,862 B |
| **could be absent** | **103,377 B** |
| absent if encryption is loaded on demand too | 118,051 B |

"Needs" keeps the shell, `fmt_sit`, `fmt_sit5`, `sit_arsenic`, `fmt_sitseg`,
the engine core, the shared codecs, and the envelope readers (`fmt_binhex`,
`fmt_macbinary`, `fmt_applesingle`) — because a `.sit.hqx` must be unwrapped
before anyone knows it is a StuffIt archive.

**~103 KB of budget** is the prize, against **648,100 B** today (main,
2026-08-31; it was 598,932 B when this was measured, and the re-pricings that
moved it are FORMATS.md, *Budget*). That is three times what this author
estimated before measuring.

**Withdrawn: "the only lever large enough to reach `derived-EasyFind.dmg.sit`".**
Written here before that fixture's refusal was priced. It is short by
**2,031,101 B** — the largest single request it makes, nearly two megabytes
past what a 1 MB Macintosh has at all, so it is DECODER-shaped and no amount
of shedding resident code reaches it (FORMATS.md, *Budget*). The prize is
still ~103 KB; what it buys is more of the corpus near the line, not the
fixtures that are out.

## Six overlays, one per format family — 2026-09-02

**The most expensive archive now decodes with 42,044 B less code and 17,040 B
less A5 world resident**, because the five decoders it does not need are not
in memory at all.

| resident, default build | plain | six overlays |
|---|---|---|
| `CODE` | 147,772 B | **105,640 B** |
| A5 world (`.data` + `.bss`) | 44,116 B | **27,128 B** |
| static total | 191,888 B | **132,768 B** |

| the blobs | |
|---|---|
| `OVLY` 128 crypt | 15,324 B |
| `OVLY` 129 SpaceSaver | 17,624 B |
| `OVLY` 130 Compact Pro + DiskDoubler | 14,736 B |
| `OVLY` 131 LZH | 6,804 B |
| `OVLY` 132 ARC | 9,168 B |
| `OVLY` 133 Now Compress | 5,968 B |

Each is loaded only when an archive turns out to be that format. Compact Pro
and DiskDoubler share one because `fmt_dd` calls `fmt_cpt`'s RLE and LZH fork
readers, and an overlay calling into another overlay is a load order nobody
has needed yet.

**On the machine, at 1 MB on System 6.0.8** — every overlay exercised, `5/5`:
a `.cpt`, a `.lzh`, an `.arc`, a SpaceSaver method-4 stream and a `.sit` that
loads none of them. The two heaviest archives pass too: `derived-Domino_v1.4.sit`
at **699,167 B** of peak heap and `derived-Library_ISBN_Barcoder.sit` at
650,786 B.

**What a StuffIt archive is granted: 650,612 → 708,916 B, +58,304 B.** That is
the number this work was for — the budget while the most expensive format
decodes, with every other decoder absent. Domino demonstrably spends it: its
peak went 640,799 → 699,167 B on the same archive and the same output.

### How it is put together

- **`tools/overlay/mkforwards.py` generates the host vector and the forwards.**
  A decoder overlay compiles engine source unmodified, so every helper that
  source calls must resolve inside the blob; each is defined there as a
  one-line forward through a table the application fills. Twelve by hand was
  fine, forty-two is not — a wrong argument list crossing that boundary would
  be silent. The list of symbols in that script IS the interface, and a
  missing one fails the link loudly.
- **Real engine types in the generated vector, not opaque ones.** `overlay.h`
  keeps engine types out of `OverlayHost` so a blob cannot depend on their
  layout; that argument does not reach a DECODER overlay, which compiles the
  decoder and so depends on all of them already. What opacity would buy here
  is casts on both sides, and a cast turns a signature mismatch from a compile
  error into a wrong call.
- **Probes stay resident, always.** `fmt_lzh_probe.c`, `fmt_cpt_probe.c`,
  `fmt_arc_probe.c` and `fmt_spacesaver_probe.c` were split out;
  Now Compress and DiskDoubler needed no split because their probes already
  live in `fmt_stubs.c`. ARC's split also moved its constants into
  `fmt_arc_priv.h` rather than copying them, because duplicating magic numbers
  is what rule #1 forbids.
- **The splits cost the DEFAULT build 72 B of code and 20 B of A5**, which is
  a function prologue and an include per split. Both ratchets fired on it and
  were raised deliberately, which is what they are for.

## A DECODER in an overlay — done, and it runs on the Macintosh

**2026-09-02: SpaceSaver's decoder is an overlay, and the emulated Mac Plus
extracts with it.** This is what the `.data` correction unlocked; nothing else
about the mechanism had to change.

**Why SpaceSaver, measured rather than chosen:** of the eight candidate
decoders it has the most to give (6,560 B of resident `CODE` and 9,701 B of A5
world — `ss_dict0` is the largest single table in the binary) and the fewest
external references (12). All eight compile `-mpcrel` with **zero** absolute
relocations, so the ceiling was never the mechanism.

| | plain build | both overlays | delta |
|---|---|---|---|
| `CODE` | 147,684 B | 135,792 B | **−11,892** |
| A5 world (`.data`) | 32,656 B | 15,964 B | **−16,692** |
| static total | 191,792 B | 163,216 B | **−28,576** |

**On the machine, at 1 MB on System 6.0.8**: the three SpaceSaver specimens
Aladdin's own compressors wrote (`tools/ssmodule/`) extract byte-exact through
the overlay — **3/3**, including method 4, whose preset dictionary now lives
inside the blob rather than in the A5 world. `adobenumbers.sit`,
`3d-terrain-modeling-017.hqx` and `derived-Domino_v1.4.sit` are unchanged,
3/3, so the crypt overlay and the ordinary paths still work beside it.

**The budget, both autotest builds, one session:** 650,612 → **678,766 B**,
**+28,154 B**. That is more than the code that left, and the reason is the
next section.

### The probe stays resident, and that is the general rule

`src/fmt_spacesaver.c` was split: `unc_spacesaver_probe`, `ss_parse` and
`ss_head_ok` moved to `src/fmt_spacesaver_probe.c`, which is never in the
blob. `unc_sniff` calls that probe for every file it is handed, so a probe
inside an overlay would load 16 KB of decoder in order to decide that the file
is not a SpaceSaver document. **Separating what DECIDES from what DECODES is
what makes on-demand loading pay**, and it is the same conclusion the
three-dispatch-tables section reached and the retired segment experiment
proved by failing to do it.

### And the A5 world is not free after all

**`main` says only `CODE` costs the engine and that data, globals and
resources are free** (FORMATS.md, *What the application costs the engine*,
ballast, 2026-08-30). Measured here on 2026-09-02, ballast **verified present
with `nm`** and read from both `main()`s through a volatile so
`--gc-sections` could not drop it:

| | budget |
|---|---|
| both overlays | 678,766 B |
| the same build + 16,384 B of `.data` | 662,350 B |

**16,384 B of `.data` cost 16,416 B of budget** — 1:1, not free. It is the
mechanism you would expect: the A5 world sits above `ApplLimit`, so growing it
lowers the heap's ceiling. That also explains why the budget here rose by
28,154 B when only 11,648 B of code left the build.

**This is a contradiction with a load-bearing claim on `main`**, not just a
branch curiosity: the code ceiling exists because code was believed to be the
only thing that costs, and *"put material in resources and tables, not in C"*
follows from the same belief. One run on `main` with this ballast settles
whether the 2026-08-30 measurement or this one is wrong. **Until then neither
number should be quoted as settled.**

## What the prize is NOT — measured 2026-09-01, on a retired experiment

**The ~103 KB above is what could be ABSENT, not what a naive split delivers.**
A third mechanism was built and retired to find this out: a Retro68 segment
map (`--mac-segments`) splitting the whole application into six `CODE`
resources, which is the same idea as this branch with the OS doing the
loading. Measured at 1 MB on System 6.0.8, both sides built and run in one
session:

| budget the engine is granted | |
|---|---|
| unsegmented, as `main` ships | 647,802 B |
| split, budget taken before the sniff | 726,122 B |
| **split, budget taken at the first allocation** | **650,880 B** |

**So a naive split is worth 3,078 B, not 78 KB and not 103 KB**, and the two
reasons are both things this branch has to solve rather than avoid:

1. **The probes travel with the decoders.** `unc_sniff` walks its order
   calling each probe, and a probe of tens of bytes lives in the same object
   as an extractor of thousands — so by the engine's first allocation almost
   everything has been dragged in. This is the same finding as *three dispatch
   tables* below, seen from the memory side: **the code that DECIDES has to be
   separated from the code that DECODES, or nothing stays unloaded.**
2. **Loaded code is locked.** `PurgeSpace` recovers 2,844 B of a 103,120 B
   split, so what is resident stays resident. An overlay this branch RELEASES
   is therefore worth more per byte than a segment that merely loads late.

**And the budget must be taken after the on-demand code arrives.** That
experiment granted its budget before the loader ran and an archive extracted
to within about 5 KB of a `NewPtr` failure — `gRefusedWhy` = 2, the refusal
that means the heap could not do what the budget said it could. **This branch
has the same shape of bug**: the ciphers load mid-extraction, after the budget
was computed. `mal_take_budget` now runs at the engine's first allocation and
reads `PurgeSpace`, which also counts a released overlay because a released
overlay is purgeable. +116 B of code, ratchet raised to 147,700 deliberately.

**`.data` is allowed in an overlay, and this file said it was not.**
`mkoverlay.sh`'s header refused `.data` while its code twenty lines down
allowed it and explained why. That mattered more than a stale comment usually
does: every decoder has tables, tables are `.data`, so "an overlay cannot
carry `.data`" ruled the entire decoder set out on paper and left the ciphers
as the only candidate — which is how a 5,988 B prize came to look like the
ceiling. **A decoder in an overlay has never been tried, and the reason it was
never tried was wrong.** It would also take its tables OUT OF THE A5 WORLD,
which no segment can do and which is the wall on the smallest machines
(FORMATS.md, *A Macintosh 128K*).

## What stands in the way — found by trying it

An afternoon spent making a `UNC_SUBSET_SIT` build link produced no build and
three facts worth more than the attempt:

1. **There are three dispatch tables, not one.** The format table
   (`unc_engine.c`), the sniffer's probe table beside it, and the segment
   handler table in `unc_segment.c`. Excluding a format means editing all
   three; missing one gives an undefined reference at link time, which is at
   least loud.

2. **The decoders are not leaves.** `unc_sit_decode_fork` calls
   `unc_lzah_decode` — the LZAH coder is shared between StuffIt and LZH.
   `unc_util`, `unc_huffman`, `unc_lzw` and the bufin/sink plumbing are shared
   across most formats. A naive per-format split either duplicates them into
   every decoder or cross-calls constantly.

3. **`#ifdef` at line level does not survive contact.** The tables hold
   multi-line struct initialisers; guarding by matching lines corrupts them.
   This needs a registration mechanism — one translation unit per format,
   registering itself — not conditional compilation sprinkled through shared
   files.

## Two architectures, and which to build

**A. A launcher plus per-format applications, chained by `_Launch`.**
Needs no new machinery: single-tasking Mac OS unloads the current application
when another launches, so the launcher's memory is fully reclaimed — measured
at 12 bytes of difference (FORMATS.md, *512 KB machines*). The launcher
sniffs and hands off.

*Costs:* several binaries instead of the one download the README leans on; a
floppy re-read per handoff on the machines that need this most; envelope
chains like `.sit.hqx` need intermediates written to disk; and the shell's
continuity — the end-of-run report, the multi-file loop, the locate-part
dialog for segmented sets — spans a process boundary.

**B. Decoders as loadable code resources**, `GetResource`d and called through
a pointer. This is how StuffIt itself worked, and it keeps one binary and one
session.

*Costs:* Retro68 emits a single flat code image and has no code-resource
target (`add_application` is the only one it exposes), so this means writing a
relocatable-blob format and its loader. Plus the shared-codec problem above:
the boundary has to fall where the sharing does not.

**Recommendation: B, scoped to the shared boundary rather than per format.**
Not one blob per format, but a small number of overlays along the seams the
code already has — `unc_crypt` (14,674 B, only for encrypted archives) and
zlib + inflate (~10,263 B, only zip and gzip) are genuinely independent and
would prove the mechanism on ~25 KB before anything harder is attempted. If
the loader works, the format decoders follow behind a registration refactor.

## The cipher overlay, WORKING on the machine — 2026-08-31

`src/unc_crypt.c` is out of the link. `mac/ovl_shim.c` provides the thirteen
symbols the engine calls, loads an `OVLY` resource on first use and dispatches
into it; `tools/overlay/ovl_crypt.c` is the other side. **The engine is
unmodified.**

**Verified where it counts:** `interactive.py --password --emu mv-1M -D
UNC_AT_OVERLAY` — *"password dialog WORKS — every entry decrypted"*, with the
phase's byte-for-byte read-back off the volume. That one run crosses the
boundary for `unc_password` (prompt and retry), `unc_resfork_find` (`MKey` out
of the archive's resource fork), `unc_crypt_sit` (key schedule) and
`unc_crypt_apply` (every buffer refill). Ordinary archives never load it:
5/5 on a mixed set at 1 MB.

**What it is worth, measured on the shipping build:**

| | code | data | budget |
|---|---|---|---|
| ciphers linked in | 147,240 B | 32,492 B | 560,860 |
| ciphers as an overlay | **141,252 B** | 25,476 B | **567,000** |

**−5,988 B of code**, so ~6 KB of budget — and the download GROWS by 2,304 B.

**Two figures corrected here, both re-measured 2026-08-31.**

*The delta was published as −6,140 B, from a pair that did not match.* The
resident row is `tools/build_mac.sh`'s plain build; the overlay row reproduces
at no commit on either overlay branch — 141,216 B before the release fix,
141,252 B after it, never 141,100 B. Taking both sides from the same build at
the same commit gives **−5,988 B**, or −5,720 B if both sides are autotest
builds (141,928 → 136,208). Every version of it rounds to "about 6 KB", which
is why it survived unquestioned.

*"7,016 B off the download" is backwards.* The `OVLY` resource ships inside
the application, so shedding 5,988 B of code and adding a 14,996 B blob makes
`MacExtract.bin` **191,104 B against 188,800 B** — 2,304 B BIGGER. The overlay
buys resident heap, and it costs disk.

**The merge from main moves neither.** Post-merge the same plain pair is
147,404 → 141,416 B, −5,988 B to the byte. Code comes off the budget one byte
for one byte, so the prize is independent of the budget itself — which is what
makes it comparable across the re-pricings that DID move: the budget column
above is pre-merge, and FORMATS.md, *Budget*, now says 648,100 B.

**That is far less than `unc_crypt.c`'s 14,674 B, and the gap is the lesson.**
`--gc-sections` was already collecting every cipher entry point nothing
reachable calls, so the module's RESIDENT cost was never its object size.
**Every estimate in this file built from object sizes — including the ~103 KB
for a full per-format split — is therefore optimistic by a factor nobody has
measured.** Treat them as upper bounds, not forecasts.

**For scale, on the same machine and the same day:** re-pricing one constant
in the memory reserve was worth **49 KB**, and three such re-pricings together
have since been worth **81,936 B** (FORMATS.md, *Budget*); this overlay, with a
dispatch, a shim, a loader and a build step, is worth **6 KB**.

**Failure to load is handled, not ignored.** Where a signature allows it the
shim returns `UNC_ERR_MEM`; where it does not, it clears the cipher kind so
the entry decodes undecrypted and fails its CRC — a per-entry error, which is
what this engine does with every allocation failure. What it must never do is
return with a cipher half-initialised.

## The first overlay, built 2026-08-30

`tools/overlay/ovl_crypt.c` compiles `src/unc_crypt.c` **unmodified** into a
**14,996 B** blob: 0 relocations, entry at offset 0, inside the 32 KB reach.
libgcc's `__divsi3`/`__modsi3`/`__mulsi3`/`__umodsi3` link into the image and
`unc_crc32` — the only call back into the application — goes through the host
vector.

**It is BUILT, not INTEGRATED.** The application still links `unc_crypt`, so
nothing has got smaller yet. Integration needs a 19-entry dispatch:
`unc_crypt.c` exports 19 symbols and 7 engine files call them, including
`unc_bufin_next_slow` on the buffer-refill path.

**What building it taught, at the cost of one failed build:** an overlay's
mutable state must be INITIALISED. An uninitialised static lands in `.bss`,
which `objcopy` leaves out of the image — the blob would write past its own
end and into the heap. An initialised one lands in `.data`, inside the image,
which is a locked `Handle` and therefore writable. `mkoverlay.sh` now refuses
`.bss` and allows `.data` for exactly that reason; the rule it had before
("an overlay has no A5 world") was written from theory and was wrong in a way
that would have corrupted memory silently on the Mac.

## What a sibling branch found, which bears on this one

`overlay-eager` loads the same overlay at launch instead of on demand, to
avoid touching the application's floppy after an archive has been chosen — on
a Mac Plus with one drive, which "cannot mount two", that disk may have been
swapped. It also releases the overlay for the six formats that provably cannot
want it.

**Two things it established that apply here too.**

**The disk dependency cannot be removed, only moved.** Releasing per archive
while the application lives per session means a later archive must reload —
which is the same mid-run disk access, later and less predictably. THIS branch
pays it on the first encrypted archive; that one pays it on the second.

**And the prize is about ONE archive.** 5,988 B of code, against a corpus
density of roughly one archive per 6–7 KB of budget near the line
(FORMATS.md). Neither branch reaches `derived-EasyFind.dmg.sit`.

**Recommendation: merge neither for the 6 KB.** Keep both as a proven
mechanism with its traps written down — `-mpcrel`, the `.bss`-versus-`.data`
distinction, the three dispatch tables, the gc-sections correction — so that
if something later needs tens of kilobytes, the loader exists and nobody has
to rediscover any of it.

## What is left

- **`unc_crypt` as the first real overlay.** It has only five external
  references — `__divsi3`, `__modsi3`, `__mulsi3`, `__umodsi3` and
  `unc_crc32`. The libgcc four link into the blob (`mkoverlay.sh` already
  passes `-print-libgcc-file-name`); `unc_crc32` goes through the host
  vector. 14,674 B of code, and nothing else in the engine calls into it.
- **zlib + inflate second**, ~10,263 B, whose externals are `inflate`,
  `inflateEnd`, `inflateInit2_`, `unc_bufin_next_slow` and `unc_crc32` —
  the first three live inside the same overlay, so the vector needs two
  entries.
- **Then the registration refactor**, which is what the three dispatch tables
  make necessary before format decoders can follow.

## What would have to be true before going further

- A registration mechanism replacing the three tables, so a format is one
  translation unit that registers itself and can simply be absent.
- A relocatable-blob format and loader for Retro68 output, proven on one
  overlay, on the machine, with the CRC read-back — not under a Linux budget
  cap, which under-reads the Mac by 16–33 KB (FORMATS.md, *The Linux budget
  check under-reads the Mac*).
- A decision about the download: one application with overlays inside it
  keeps `dist/` a single file, which is the property the README sells.

## What is NOT claimed

That 103 KB would all come back. It is the code that *could* be absent for one
archive of one family; the loader, the registration table and the overlay
headers all cost something, and the envelope readers must stay resident
because they run before the format is known.
