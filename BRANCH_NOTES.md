# Branch `overlay-eager` — one disk read at launch, then throw most of it away

**Branched from `selective-loading`**, and it carries all six of that branch's
overlays. Same images, opposite lifetime: `selective-loading` reads the one it
needs when it needs it; this reads **all six as a single resource while the
boot disk is certainly still in**, and releases everything the archive cannot
want as soon as the sniff says what the archive is.

**Status, 2026-09-02: measured on an emulated Mac Plus at 1 MB.** A bare
StuffIt 5 archive is granted **693,168 B** with the bundle released and only
the ciphers kept; an LZH gets **701,688 B**, keeping only its own decoder.
4/4 fixtures extract byte-exact across the formats that keep one image, two
images, and none.

## The three methods, and what each leaves the decoder

**Measured 2026-09-02 at 1 MB on System 6.0.8, all three built and run in one
session, same fixtures, same instrument.** The number is what the engine is
GRANTED — `mal_take_budget` at its first allocation, so every overlay the run
is going to load has already loaded.

| the archive | A: no overlays | B: `selective-loading` | C: this branch |
|---|---|---|---|
| StuffIt 5, bare | 650,548 B | **708,916 B** | 693,168 B |
| LZH, bare | 650,548 B | **702,104 B** | 701,688 B |
| Compact Pro, bare | 650,548 B | 694,172 B | **693,212 B** |
| MacBinary → StuffIt, through the real UI | 647,114 B | **705,780 B** | 689,108 B |
| disk access after the archive is chosen | none | **one, per format** | **none** |

**Column A does not move with the archive**, and that is the control: with
every decoder resident the engine gets the same heap whatever it decodes.
Both overlay methods beat it by 44–58 KB.

**Where B and C differ is the ciphers.** A format that MAY carry an encrypted
entry forces this branch to keep the cipher image, because it must decide what
to throw away before it knows whether any entry is encrypted;
`selective-loading` never loads the ciphers unless an entry asks. That is
15,748 B, and **two of the five formats no longer pay it**: Compact Pro and
zip keep a per-entry flag in a directory that can be walked before anything is
decoded, so `unc_archive_encrypted()` answers for the whole archive and the
ciphers are kept only when one is actually encrypted. The Compact Pro row
closed to within **960 B** of B, which is the query's own code. StuffIt,
StuffIt 5, PackIt and ARC still pay: the first three flag encryption per entry
with no directory to consult, and ARC does not flag it at all.

**What C buys for what remains is the disk.** `selective-loading` reads an
overlay after the archive has been chosen, and on a Mac Plus with one drive
the application's floppy may have been ejected by then. This branch reads
once, at launch, while the boot disk is certainly in. **That is the trade,
priced: about 16 KB of budget against a disk access at an unpredictable
moment.**

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
