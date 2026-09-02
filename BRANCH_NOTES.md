# Branch `overlay-eager` — load the overlay at launch, release what cannot be wanted

**Branched from `selective-loading`.** Same overlay mechanism, different
LIFETIME, for one reason: a lazy `GetResource` touches the application's own
disk AFTER the archive has been chosen, and on a Mac Plus with one floppy
drive — which "cannot mount two" (DECISIONS.md 2026-08-24) — that disk may
have been swapped by then. Loading at launch confines the only disk access to
a moment when the boot disk is certainly in.

**Verified 2026-08-31 at 1 MB:** encryption still works with the overlay HELD
(`--password`: *"every entry decrypted"*), and a releasable format, an
envelope-free terminal one and a held one all extract — LZH, tar and Compact
Pro, 3/3.

## What it can and cannot give back

**5,988 B, and only for six formats.** Two things disqualify a format from
release: it may carry an encrypted entry, or it is an ENVELOPE whose contents
are not yet known.

| | release? |
|---|---|
| SIT, SIT5, Compact Pro, PackIt, Zip, ARC | no — may carry encrypted entries |
| BinHex, MacBinary, AppleSingle, gzip, `.Z`, MIME, uu, btoa, base64 | no — envelopes; a `.sit.hqx` sniffs as BinHex |
| LZH, DiskDoubler, Now Compress, SpaceSaver, SuperDisk!, tar | **yes** |

**So it does not pay for StuffIt**, which is the common case and the reason
this project exists.

## The release is per ARCHIVE; the application's life is per SESSION

**A bug this branch shipped for one commit, and the reason it matters more
than the fix.** The release ran after each archive's sniff, but the "already
tried" flag was global, so `ovl_entry` never reloaded. Extract an LZH, then an
encrypted `.sit` in the same session, and the ciphers were gone — the cipher
kind cleared, the entry failing, **a capability disappearing because of what
was opened before it.** Not a prompt, not a delay: a silent loss. Fixed by
allowing the reload; encryption re-verified at 1 MB afterwards.

**And the fix concedes the branch's own argument.** A reload is exactly the
mid-run disk access this lifetime was chosen to avoid, so `overlay-eager` does
not escape the trade — it defers it to the second archive, where it is less
predictable. A user who opens several archives in a session meets the same
prompt, later.

**Neither overlay branch avoids the disk dependency. They move it.**

## The conflict is inherent, not an implementation gap

Freeing the cipher memory and guaranteeing no mid-run disk access are in
direct opposition unless you know BEFORE extracting whether an entry is
encrypted. For StuffIt you cannot: encryption is per entry and discovered as
the entry is read. The engine exposes no per-entry encryption flag; the only
signal is `UNC_ERR_PASSWORD`, which arrives after the memory would have
mattered.

Three ways to know, and what each costs:

1. **From the format** — what this branch does. Free, covers six formats.
2. **From the archive's directory before extracting** — zip's central
   directory carries an encryption bit per entry, Compact Pro and StuffIt 5
   have entry tables, and StuffIt classic's archive key announces itself as
   `MKey` in the resource fork, which the shell already reads. Needs a small
   PUBLIC API addition and does not work for streamed formats with no
   directory.
3. **Lazily, paying one disk access when a password is actually needed** —
   release before the big allocations, reload if `unc_password` is reached.
   Unencrypted archives get the memory back with no disk access; encrypted
   ones pay a read at the moment they are already interrupting the user with
   a dialog.

**And weigh all of it against the prize, which is 6 KB — about ONE archive.**
The corpus headroom study puts the density near the line at roughly one
archive per 6–7 KB of budget (FORMATS.md), so 6 KB is one file in 922, and
not `derived-EasyFind.dmg.sit`, whose margin is no longer unmeasured: it is
short by **2,031,101 B** (FORMATS.md, *Budget*), which is nearly two megabytes
past what a 1 MB Macintosh has at all, so that fixture is decoder-shaped and
out of reach of any amount of shedding resident code. Against that: a dispatch, a shim, a loader, a build step, a
new resource type, three branches, and a class of bug that does not exist when
the code is simply linked in. Re-pricing one constant
in the memory reserve, the same week, was worth **49 KB**, and three such
re-pricings have since been worth **81,936 B** together (FORMATS.md,
*Budget*). Extending a public API for six kilobytes is not obviously right.

## The three positions, so the choice is on the table

| | ciphers cost | mid-run disk access |
|---|---|---|
| `main` | 6 KB, always | none |
| `selective-loading` | nothing until needed | **yes, after the archive is chosen** |
| `overlay-eager` (here) | nothing for six formats, 6 KB otherwise | none |

---

# Branch `selective-loading` — load only the decoder the archive needs

**Status: the loading mechanism is BUILT and PROVEN ON THE MACHINE. The
decoders are not ported yet.** The hard part — getting code that is not
resident to run on a 68000 and call back into the application — works. What
remains is a registration refactor and porting decoders in behind it.

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
at no commit on this branch — 141,216 B at `7a35327`, 141,252 B at the tip,
never 141,100 B. Taking both sides from the same build at the same commit
gives **−5,988 B**, or −5,720 B if both sides are autotest builds
(141,928 → 136,208). Every version of it rounds to "about 6 KB", which is
why it survived unquestioned.

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
