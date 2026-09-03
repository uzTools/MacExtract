# Branch `selective-loading` — load only the decoder the archive needs

**Status: thirteen overlays, four tiers run, and one archive recovered.**
69/69 at 4 MB, 69/69 at 1 MB, 69/69 on System 3.0 at 1 MB, and **67/69 at
512 KB against `main`'s 66/69** — `derived-a2basic.dmg.sit` extracts on a
Macintosh 512Ke for the first time.
Resident code is 50,932 B against 147,772 B, the A5 world 18,828 B against
44,116 B, and the largest single `CODE` resource — the thing a small machine
has to find room for in one piece — is **45,480 B** against 142,152 B. The decoders for SpaceSaver, Compact Pro, DiskDoubler, LZH, ARC
and Now Compress are loaded only when an archive turns out to be one, and the
ciphers as before. Resident code 147,772 → 105,640 B, A5 world 44,116 →
27,128 B, and a StuffIt archive is granted **58,304 B more budget**.

The hard part — getting code that is not resident to run on a 68000 and call
back into the application — has worked since 2026-08-30; what was missing was
the belief that a decoder could go in one, and that came from a wrong comment
(*What the prize is NOT*, below).

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

## What the engine is left with, against the other two methods

**Measured 2026-09-02, 1 MB, System 6.0.8, all three built and run in one
session.** The full three-way table — and what the eager lifetime costs — is
in `BRANCH_NOTES.md` on **`overlay-eager`**, which is where the comparison
belongs because it is the branch the trade is against. The rows for this
branch:

| archive | no overlays | this branch |
|---|---|---|
| StuffIt 5, bare | 650,548 B | **708,916 B** |
| LZH, bare | 650,548 B | **702,104 B** |
| Compact Pro, bare | 650,548 B | **694,172 B** |
| MacBinary → StuffIt, driven through the real UI | 647,114 B | **705,780 B** |

The first column does not move with the archive, which is the point of it:
with every decoder resident the engine gets the same heap whatever it is
decoding.

**The last row needed a new instrument.** `run.py` drives the autotest build,
whose `main()` extracts ONE layer; envelope chaining lives in `ExtractOne`,
which only the interactive `main()` calls. `-D UNC_AT_BUDGET` now prepends
`bg=` and `pk=` to the completion alert, so `interactive.py` can be asked the
same question the grid answers — which is how the envelope row was measured
rather than assumed.

## The tiers, 2026-09-03 — and one archive that could not be opened before

| tier | this branch | `main` |
|---|---|---|
| 4 MB, System 6.0.8 | **69/69** | 69/69 |
| 1 MB, System 6.0.8 | **69/69** | 69/69 |
| System 3.0, 1 MB | **69/69** | 69/69 |
| System 3.0, **512 KB** (Macintosh 512Ke) | **67/69** | 66/69 |

**The 512 KB tier gained a fixture, which is the point of all of this.**
`derived-a2basic.dmg.sit` extracts there now, holding **305,507 B** of peak
heap — an archive whose one entry needs 246,734 B against a budget that was
163,656 B, and which had been refused per entry since the tier existed
(FORMATS.md, *512 KB machines*, on `main`). **A machine that could not open
that archive now opens it.**

The two that still fail are the other two of the documented three, and they
fail for the reason the design says they must: `synth-dd-m5.dd` asks for one
405,520 B block on every tier, and `derived-Library_ISBN_Barcoder.sit` for
393,869 B — both more, in a single allocation, than a 512 KB machine has for
the whole job. No amount of code moved out of the heap reaches those; what
would is a smaller archive.

**And the tiers are what found the relocation defect below.** 67/69 at 1 MB on
the first run, where seven hand-picked fixtures had said 7/7.

## The check that could not fail, and the defect it hid

**`-mpcrel` makes an overlay's CODE position-independent. It does nothing for
a POINTER STORED IN DATA, and for a year this branch believed otherwise.**

`static const uint8_t *const sit13_firstlengths[5]` — StuffIt method 13's
preset code tables — is an array of pointers. In an overlay those five words
hold LINK-TIME addresses, and the blob runs wherever the Memory Manager put
it, so they point at nothing. The same shape is in zlib's `z_errmsg`, in
MIME's keyword tables, and in Compact Pro's.

**The build could not see it.** `mkoverlay.sh` ran `objdump -r` on the FULLY
LINKED image and required zero relocations — and a fully linked image has
none, because the linker has already resolved them into the data. The check
passed because it was asking a question with only one possible answer.

**What it looked like on the machine**: `UNC_ERR_CORRUPT` from StuffIt method
13, for exactly the entries small enough to use the PRESET tables — large ones
take the dynamic path and never touch them. Four entries of one archive, one
archive in sixty-nine. **The 1 MB tier found it; seven fixtures had not.**

**The fix is to stop pretending.** `mkoverlay.sh` links with `-q`, which keeps
the relocations, and appends the absolute ones to the image as a trailer
(`mkreloctrailer.py`): the offsets, then the count, big-endian, at the end
where the handle's own size finds them. `ovl_fixup()` in the shim adds the
load address to each, once, after `HLock`. Every image carries a trailer, a
clean one with a count of 0, so the loader needs no flag.

| overlay | relocations |
|---|---|
| StuffIt | 15 |
| Compact Pro + DiskDoubler, MIME + text, exo, codecs | non-zero, and silently wrong before this |
| crypt, LZH, ARC, Now, SpaceSaver, PackIt, SuperDisk! | 0 |

**Two wrong versions of the fix, both instructive.** The first fed the loader
every `R_68K_32` `readelf` prints — including `.rela.debug_line`,
`.rela.debug_info` and `.rela.debug_aranges`, whose offsets are offsets into
sections `objcopy` never emits. Patching those wrote arbitrary words of the
image: the application hung instead of extracting, which is a worse failure
than the one being fixed. The second used `strtonum()` in `awk`, which this
platform's `awk` does not have, and reported **0 relocations for an image with
41** — a silent empty list, the same shape of failure as the check it was
replacing.

**After it: 69/69 at 1 MB**, where the same tier was 67/69 before.

## Thirteen overlays, and a blob that other blobs can call

**2026-09-02, third pass.** `fmt_exo` moved after all, `unc_lzdyn` with it,
and then the thing that looked impossible: the shared codec machinery is an
overlay too.

| resident, default build | plain | six | ten | **thirteen** |
|---|---|---|---|---|
| `CODE` | 147,772 B | 105,640 B | 73,052 B | **50,932 B** |
| A5 world | 44,116 B | 27,128 B | 22,036 B | **18,828 B** |
| static total | 191,888 B | 132,768 B | 95,088 B | **69,760 B** |
| largest single `CODE` resource | 142,152 B | 100,188 B | 67,600 B | **45,480 B** |

**On the machine, 7/7 at 1 MB on System 6.0.8** — a `.sit`, a `.cpt`, a
`.lzh`, an `.arc`, a SpaceSaver method-4 stream, a deflated zip and
`derived-Domino_v1.4.sit`, all byte-exact. Domino is granted **747,638 B**,
against 650,548 B with everything resident.

### One blob calling another, which the mechanism forbids

The bit reader, the Huffman and canonical coders, LZW and LZAH are called by
six decoders between them. That is why they were resident: an overlay carries
no relocations and reaches outside itself only through the host vector, whose
entries the application fills with addresses of RESIDENT functions. Blob B's
address is not known when blob A is linked, and there is nothing left to patch
it with afterwards.

**The way through is that the vector is only a struct of pointers, and nothing
says a pointer in it has to point at resident code.** `ovl_codecs.c` is loaded
before any decoder that needs it and, on `OVL_CODEC_EXPORTS`, writes the
addresses of its own fifteen functions into the application's copy of the
vector. Every decoder overlay then calls them exactly as before — through
`g_ovl_fns` — and never learns that the target moved.

**Taking those addresses in CODE is what makes it legal.** Under `-mpcrel` a
function's address is PC-relative and costs no relocation; the same fifteen
pointers in a static table would need one each, and `mkoverlay.sh` refuses
any. The mechanism is three lines of generated macro.

**The alternative was duplication** — compiling the machinery into each of the
six overlays that call it, about 17 KB of extra download to save the same
8.5 KB of RAM. This costs the mechanism and nothing else.

**Failure is handled where it can be**: fifteen vector entries start NULL,
because their implementations are not in the application at all, so every
decoder shim calls `ovl_codecs_ready()` before dispatching and returns
`UNC_ERR_MEM` if the overlay cannot be had. A decoder that ran with NULL codec
pointers would not fail — it would jump to zero.

### `--gc-sections`, and zlib's three libc calls

The exo overlay carries zlib, which reaches for `memcpy`, `malloc` and `free`
— and an overlay links no libc. `mkoverlay.sh` now links with `--gc-sections`
and `--entry=ovl_main`, which drops what nothing calls (`inflateCopy`, and
`zcalloc`/`zcfree`, whose work `src/unc_inflate.c` does with the engine's own
allocator) and shrank every other image as well: SpaceSaver 17,904 → 16,718 B.
`memcpy` survives because inflate really does copy its window with it, so the
overlay carries a real one; `malloc` returns NULL and `free` does nothing,
with the reason written where they are.

## Ten overlays: every decoder that can move has moved

**2026-09-02, second pass.** The first pass moved six because six had clean
seams; the rest needed their probes split out, which is the work rather than
the idea. All of them now are, except `fmt_exo`.

| resident, default build | plain | six overlays | **ten overlays** |
|---|---|---|---|
| `CODE` | 147,772 B | 105,640 B | **73,052 B** |
| A5 world | 44,116 B | 27,128 B | **22,036 B** |
| static total | 191,888 B | 132,768 B | **95,088 B** |
| largest single `CODE` resource | 142,152 B | 100,188 B | **67,600 B** |

| the images | |
|---|---|
| 128 crypt 15,324 · 129 SpaceSaver 17,904 · 130 Compact Pro + DiskDoubler 14,736 | |
| 131 LZH 6,804 · 132 ARC 9,168 · 133 Now Compress 6,248 | |
| 134 SuperDisk! 8,592 · 135 PackIt 4,460 · **136 MIME + text envelopes 19,596** · 137 StuffIt 18,668 | |

**MIME travels with uuencode, btoa, base64 and BinHex** because a MIME part
may be base64 or uuencoded and the decoder calls straight into both — and an
overlay cannot call another overlay. Grouping is decided by the call graph,
not by taste.

**On the machine, 6/6 at 1 MB on System 6.0.8**: a `.sit`, a `.hqx`, a `.cpt`,
a `.lzh`, a SpaceSaver method-4 stream and `derived-Domino_v1.4.sit`, all
byte-exact. The budget a StuffIt 5 archive is granted is **727,802 B** and an
LZH **739,386 B**, against 650,548 B with no overlays — and Domino's own peak
rose to 725,324 B, so the engine spends what it is given.

### What the probe splits cost, and what they taught

Ten formats needed one: `fmt_sit`, `fmt_sit5`, `fmt_packit`, `fmt_btoa`,
`fmt_binhex`, `fmt_superdisk`, `fmt_uu`, `fmt_b64`, `fmt_mime` and (earlier)
`fmt_lzh`, `fmt_cpt`, `fmt_arc`, `fmt_spacesaver`. Five needed a private
header as well, because a probe and its decoder share constants, a struct or
a helper — and copying those instead would be the duplication rule #1 forbids.

**The instructive one is `fmt_mimeseg`, which STAYS resident and calls four
MIME helpers.** A `message/partial` set is recognised and joined before
anything knows there is a message under it, so those four helpers had to move
to the resident probe file rather than into the overlay with the decoder.
**What is resident is decided by who calls it, not by what it belongs to.**

### `fmt_exo` is the one that did not move

7,666 B — zip, gzip, Unix compress and tar in one file with four probes and
its own tar helpers. It is the largest decoder left resident and the reason
`CODE` 2 is 67,600 B rather than about 60,000. Nothing about it is harder in
kind; it is four splits instead of one.

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
