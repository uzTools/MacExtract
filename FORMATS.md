# FORMATS.md — format support matrix

Status after M0–M9. "Oracle coverage" = fixtures with byte-exact
differential manifests (built from The Unarchiver's `unar`; see
TESTING.md); every one passes, plus 10 corruption variants each in the
robustness suite. "Peak RAM" = allocator high-water mark across the
whole corpus for that format (engine allocations only, via
`unclassic t --stats`).

| Format | Status | Methods | Oracle coverage | Peak RAM | 400 KB budget |
|---|---|---|---|---|---|
| MacBinary I/II/III | extract | — | 233 fixtures | 8 KB | full |
| AppleSingle/Double | extract | — | (unit tests + envelopes) | 8 KB | full |
| BinHex 4 (.hqx) | extract | RLE90; several documents in one file, and one document posted in several parts†† | 179 fixtures | 8 KB | full |
| PackIt (.pit) | extract | store, Huffman; encrypted detected | 4 fixtures (1 real + 3 synthetic PMa4) | 9 KB | full |
| Compact Pro (.cpt) | extract | RLE, LZH+RLE | 108 fixtures | 19 KB | full |
| StuffIt classic (.sit) | extract | 0 store, 1 RLE90*, 2 LZW, 3 Huffman, 5 LZAH, 6 fixed Huffman‡, 8 MW, 13 LZSS+Huffman; encrypted detected | 227 fixtures‡‡ | 8–76 KB‖ | full |
| StuffIt 5 (.sit) | extract | 0, 13, 15 Arsenic; encrypted detected | 31 fixtures | 0.15–2.53 MB† | 23 of 31 fixtures extract FULLY; the rest refuse per entry |
| Zip | extract | store, deflate; others & encrypted per-entry errors | 5 fixtures (2 of them PKZIP 1.x, graded on names and entry counts only — Implode is out of v1 scope, and `unar` adjudicates 5 of their 7 entries) | 12–54 KB¶ | full |
| Gzip | extract | deflate | 3 fixtures | 51 KB | full |
| Unix compress (.Z) | extract | LZW ≤16 bit | 4 fixtures | 219 KB§ | full |
| Tar (ustar/v7) | extract | — (links reported unsupported) | 3 fixtures (2 real 1990 v7 tars) + unit tests | 8 KB | full |
| StuffIt segment (multi-part) | extract | — (join only; the joined file is the next layer) | 7 synthetic sets, oracle-adjudicated, + 3 with each part in its own envelope (CLI only) | 8 KB | full |
| Zip segment (spanned, .z01…/.zip) | extract | store, deflate — the zip reader, over the joined parts | 5 generated sets, adjudicated 4 ways (source tree, `unar`, us split, us unsplit) | 12–13 KB¶ | full |
| Compact Pro segment (multi-part) | extract | RLE / LZH+RLE — the Compact Pro reader, over the segments | 2 generated sets + 2 cut by Compact Pro 1.51 itself | 20 KB | full |
| Split file (plain .001/.002) | extract | — (join only; the joined file is the next layer) | 3 generated sets, adjudicated against the bytes that were cut, `unar` where it can join, and our unsplit read | 8 KB | full |
| StuffIt X (.sitx) | detect only | — | — (no fixture) | — | — |
| DiskDoubler (DD, DDAR, DDA2) | extract | 0 store, 6/9 AD LZSS, 8 Compact Pro, 10 DDn; 1/2/3/4/5/7 declined per entry✦ | 6 fixtures | 16–108 KB✦ | full |
| Now Compress | extract | stored, LZSS, Huffman, Huffman+LZSS, "new" LZSS✧ | 2 real fixtures + 13 generated archives (all five shapes, adjudicated by `unar`); `synth-now-mixed.now` also has an `unar` manifest and is in the differential suite | 128 KB✧ | full |
| ARC / ArcMac (.arc) | extract | 1/2 store, 3 RLE90, 4 squeeze+RLE90, 5/6/7 crunch, 8 12-bit LZW+RLE90, 9 13-bit LZW, 0x7f compress; ArcMac's two-fork payload since 2026-08-16★★★; 0x0a/0x0b (PKARC) declined per entry★ | 10 generated archives (methods 1-9, adjudicated by `unar`) + 3 written by Debian's `arc` 5.21q; `synth-arc-mixed.arc` also has an `unar` manifest and is in the differential suite | 4–32 KB★ | full |
| uuencode (.uu, incl. UUTool) | extract | — (plain uu, UUTool's two-fork "MU" shape, and documents posted in several parts★★) | 7 generated cases, the two-fork ones adjudicated by macutils' `hexbin`; `synth-uu-mac.uu` is in the differential suite | 4 KB | full |
| LZH/LHA (-lh?-, -lz?-) | detect only | — | 1 real `-lh5-` archive, named + refused; unit test over every method byte | — | — |
| DiskCopy 4.2 (.image) | detect only | — | synthetic 800K GCR + real 800K image; 0 false positives in 807 fixtures (re-measured 2026-08-15) | — | — |

✦ **DiskDoubler, in scope since 2026-08-15** (M12), where every status file
here used to call it detect-only. Three containers — a single compressed file
(`0xABCD0054`), `DDAR`, `DDA2` — and four methods, which is every method the
corpus uses: 0 stored, 6/9 (an 8 KB-block LZSS), 8 (Compact Pro compression in
a DiskDoubler container: the same two stages as `.cpt`, at a 0xfff0 Huffman
block instead of 0x1fff0), 10 (DDn: a 64 KB-window LZSS whose literals, offsets
and lengths are three separately Huffman-coded streams laid out back to back).
Delta-1 preprocessing is applied where the header asks for it, outside the
checksum, which is where the reference puts it.

Peak heap 16–108 KB on Linux and the same on a Mac Plus at 4 MB and 1 MB (`unclassic t --stats`; FORMATS.md, "DiskDoubler and Now Compress on the Mac"): the 100 KB end is DDn,
whose window is sized from the entry up to the format's 64 KB, plus a
literal/offset buffer sized from each block's own header. All six extract
fully under a 400 KB budget and under the 678,392 B a 1 MB Mac Plus leaves the
engine — measured on Linux; no on-Mac run has extracted one (OPEN_ITEMS.md).

Methods 1, 2, 3, 4, 5 and 7 are **declined per entry**: no corpus fixture uses
one, and the reference marks 3 and 4 unimplemented and 5 untested, so anything
written for them could not be graded. **11 forks across 2 fixtures are
adjudicated by neither oracle** — `unar` fails on them and `macunpack` (built
with its DiskDoubler support on) fails too; our output for those is ungraded,
and `run_diff.py` prints the count on every run. DECISIONS.md 2026-08-15.

✧ **Now Compress, in scope since 2026-08-15** (M12). The archive is a flat
entry table nested by a per-directory entry count, then one compressed stream
per file; each stream is a table of blocks, each up to 32 KB of output against
a 32 KB sliding history, in one of five shapes (stored, LZSS, Huffman,
Huffman then LZSS, and a second "new" LZSS with its own length/offset tables).
Peak heap is a flat **128 KB** — history, block and staging buffers, all fixed
by the format — and it extracts fully under a 400 KB budget. Byte-exact on a
real emulated Mac Plus at 4 MB and at the 1 MB floor (2026-08-15).

The reference treats the whole archive as ONE solid stream and cuts entries
out of it by offset; this reader does not, because each file's stream holds
exactly that file's resource fork followed by its data fork. That is what
keeps it to fixed memory (DECISIONS.md 2026-08-15).

**What the two real fixtures reach, measured** by instrumenting the block
loop. `derived-Expand_Now_1.0.1.sea`: three blocks, "new" LZSS twice and
Huffman-only once, zero padding, no offset delta, no stream restart, no length
past a nibble, deepest code 12. `derived-SyntheticReferences2.0.sea`
(1995, found 2026-08-16): a folder, a two-fork file and a 9,949,696-byte
FileMaker database out of 2.9 MB, in two streams of 306 blocks — all "new"
LZSS, and **two stream-restart records**, the dictionary-cache reload no other
real archive here uses. Peak heap on that extraction is 131,072 B, so the flat
128 KB is measured on a 9.9 MB output.

Everything else — the other three shapes, a 17-bit code and both routes into
the offset-delta search — is covered since 2026-08-15 by 13 generated archives
adjudicated by `unar` (TESTING.md), byte-exact there and under qemu-m68k.

**`unar` cannot read the 1995 archive at all**, so four of its forks are
adjudicated by nobody: 129 of its 306 blocks end within 7 bits of their
buffer, and XADMaster's bit reader raises end-of-buffer there (DECISIONS.md
2026-08-16). The spare-bit count is spread almost uniformly over 0..15, which
is what a real encoder writes. Those four forks were adjudicated on
2026-08-16 by the decoder inside the archive — it is self-extracting —
which agrees with us on every one (DECISIONS.md, "The archive that carries its
own oracle").

**The block shapes come from the encoder itself since 2026-08-16.**
`tools/vmac/nowcompress.py` installs Now QuickFiler 5.0.1 under System 7 on an
emulated Mac Plus and drives its Compress and Archive commands, the way
`cptsegment.py` derives a segmented Compact Pro set. What it writes:

| what | block flags | shape |
|---|---|---|
| Compress ▸ Faster | 0x10 | LZSS only |
| Compress ▸ Smaller, text | 0x1f | LZSS only |
| Compress ▸ Smaller, mixed content | 0x3f | Huffman then LZSS |
| Compress ▸ Smaller, incompressible | 0x00 | stored |
| Archive ▸ Smaller (a `.sea`) | 0x100 / 0x140 | stored / new LZSS |

Seven specimens, every one byte-exact through this decoder and through `unar`.
With the 1993 fixture's Huffman-only block that is all five shapes on real
bytes. Two things only the encoder could say: it REFUSES a wholly
incompressible file rather than storing it, so a stored block appears only
inside a file that compresses somewhere else; and a stored block may carry
flag bit 0x100, which no decoder here or in XADMaster examines
(DECISIONS.md 2026-08-16).

†† **Multipart, in both directions, since 2026-08-15.** A `.hqx` file may hold
more than one document, and a single document may have been posted in several
parts — each part carrying its own mail header, so that joining them puts that
header in the MIDDLE of the stream. The second case was added later the same
day, after the first was: `unclassic x posted.hqx.001` used to report the entry
truncated, because the `:` in `From:` is BinHex's terminator. The rule that
fixes it is `reference/macutils/hexbin/hqx.c`'s — judge each LINE and skip one
holding "intermediate garbage" — and it works because the BinHex alphabet omits
`n`, `o`, `s`, `t`, `u` and the space, so ordinary prose disqualifies itself
within a few characters. Half of hexbin's rule is deliberately left out (the
equal-length test, which can discard a legitimate short final line — hexbin
ships `-c` to disable it); what that half would have caught, a junk line built
only of alphabet characters, the per-fork CRC catches instead, as a per-entry
error rather than as silence. Both halves are asserted in
`tools/run_multihqx.py`, and both fail against a build with the rule removed.

**A `.hqx` file may hold more than one document, and since 2026-08-15 all
of them are extracted** — the shape comp.binaries.mac produced, several files
posted in one message. Each document is banner, ':', stream, ':'; the decoder
looks for the next banner after each one, as
`reference/macutils/hexbin/hexbin.c` does. A banner with nothing usable after
it is an error rather than a quiet stop. Graded by `hexbin` and by the same
fixtures decoded one at a time (TESTING.md, "Several BinHex documents in one
file"); the differential suite cannot see this case, because `unar` takes the
first document too. The 179 fixtures are single-document files and are
unaffected — all still byte-exact.

\* **Method 1 occurs once and IS oracle-adjudicated** (since 2026-08-08).
It is the 470-byte resource fork of `I Want To Buy Some Cheese` in
`derived-New_Python.sit` (470 → 389), and `unar` decodes it byte-identically
to us — `unar` fails elsewhere in that archive, on a method-3 fork, which is
why per-entry manifests were needed to see this one at all (TESTING.md, "When
the oracle fails on an entry"). Edge cases the one real fork cannot reach — runs of `0x90`, the 255-byte
maximum token, output ending inside a run — are covered by
`synth-sit-rle90.sit` (`tools/synth_sit1.py`), also oracle-adjudicated.

‡ **Method 6, "Fixed Huffman", is implemented and oracle-adjudicated**
(since 2026-08-08). It occurs once in the corpus: the 34,818-byte resource
fork of `INITLoader` in `derived-INITLoader.sit`, two Huffman-coded segments,
which we decode byte-exact. Every segment is coded with a tree whose SHAPE is
a constant of the format, so it is generated once from the reference by
`tools/gen_sit6_tables.py` into `src/sit6_tables.h` rather than rebuilt per
fork on a 68000; only the byte each leaf stands for is declared per segment.
Peak heap 39,998 B on that fixture — the segment buffer is sized from the
segment (31,806 B here), capped at 64 KB.

The branches one real fork cannot reach — a *stored* segment, PackBits fillers,
the longest and shortest runs, a one-byte alphabet, twelve segments in a fork —
are covered by `synth-sit-fixhuf.sit` (`tools/synth_sit6.py`), also
oracle-adjudicated, 10 forks over 5 entries.

**The oracle for both is `macunpack`, not `unar`:** XADMaster recognizes the
method and refuses it (`//case 6: fixed huffman`,
`reference/XADMaster/XADStuffItParser.m`), which is where the name comes from;
macunpack has decoded it since 1991 and is the reference the decoder is
transcribed from. TESTING.md, "A second oracle", for what that does and does
not prove; BLOCKERS.md for the claim that no oracle existed.

‡‡ **Per-entry method coverage across the 227 StuffIt-classic fixtures**,
counted from the manifests: LZ+Huffman (13) 970 entries in 115 fixtures,
Compress (2) 330/90, Huffman (3) 38/24, None (0) 13/7, Fixed Huffman (6) 6/2,
LZAH (5) 1/1, MW (8) 3/1. Method 1 (RLE90) has no oracle coverage but does
occur — `synth-sit-rle90.sit` and one real fork carry it.

† **Every real Arsenic block is 512 KB.** The block size is `1 << (v+9)`
with `v` read from the stream, so other sizes are legal, but across the
31-fixture StuffIt 5 corpus **all 484 Arsenic streams — one per compressed
fork — declare 512 KB** (`v` = 10, blockbits 19). Measured directly by
instrumenting the point where `sit_arsenic.c` reads `v`, not inferred.

Peak heap is modelled by

    peak  =  ~35 KB parser state  +  block capacity  +  4 × actual block fill

because only the *block* is allocated at its declared size; the inverse-BWT
transform vector is sized to how much of the block the entry actually fills
(`transform = numbytes * 4`, in `ars_bwt_prepare`). Peak heap therefore cannot
recover the declared block size — the earlier "128 KB (14 fixtures) / 256 KB
(9) / 512 KB (8)" figures were inferred by dividing peak by five and are
withdrawn (BLOCKERS.md, *Withdrawn claims*).

Measured peak heap over the corpus (`unclassic t --stats`): **min
0.15 MB / median 0.59 MB / mean 0.92 MB / max 2.53 MB**, the maximum
being the entries that genuinely fill a 512 KB block (35 KB + 512 KB +
2048 KB) — **exactly two fixtures reach 524,257 B of fill**, which is the
number that got applied to three fixtures it did not describe (BLOCKERS.md,
*Withdrawn claims*). A true figure about the worst case is not a figure about
the case in front of you. Those are the peaks with memory to spare, where the decoder takes
the fast inverse BWT; under a cap it takes a cheaper one and the numbers
below apply instead.

**Under a cap, since 2026-08-07: 23 of the 31 fixtures extract completely
and byte-exact under a 400 KB budget (was 11), and all 31 fit the ~700 KB a
1 MB Mac Plus has free (was 18).** The transform vector is no longer built
at all when it does not fit; a sampled occurrence index answers the same
query for a fraction of the memory and more time (DECISIONS.md 2026-08-07).
**Peak heap under a budget is not the requirement** — the decoder spends
whatever the cap allows, so the honest figure is the minimum at which a
fixture still extracts fully, bisected:

| fixture | needed before | minimum now |
|---|---|---|
| `derived-RWAsm_Folder.sit` | 160,704 | 71,996 |
| `derived-Troi-ClipSave-Plug-in1.1.sit` | 660,200 | 167,455 |
| `derived-a2basic.dmg.sit` | 1,031,463 | 245,897 |
| `derived-Library_ISBN_Barcoder.sit` | 1,682,080 | 393,028 |
| `derived-Domino_v1.4.sit` | 2,657,700 | 565,062 |
| `derived-EasyFind.dmg.sit` | 2,657,700 | 565,062 |

Those figures are what the corpus costs today. **Arsenic reached the 1 MB floor
in four steps, and the per-fixture outcomes are the two Mini vMac sections
below:** 2026-08-02 the shell stopped slurping the archive, 2026-08-03 the
block stopped being allocated at its declared 512 KB, 2026-08-06 its first
allocation was sized from the entry, 2026-08-07 the transform vector became
optional. Before the first, peak was min 0.63 / median 0.97 / mean 1.23 MB with
**every** entry over a 400 KB budget; nothing about the format or the decoder
changed, only what is allocated to hold it. One DECISIONS.md entry per step,
same dates.

§ **The `.Z` peak used to be a flat 274,432 B for every input, and is now
sized from the input.** MEASURED 2026-08-03. `compress(1)` writes `maxbits=16`
whatever it compressed, so a 488-byte `.Z` declared a 65,536-entry table it
filled a few hundred entries of; the table is now bounded from the input by
`symbols <= 256 + reserved + insize * 8 / 9` (DECISIONS.md 2026-08-03):

| fixture | in | was | now |
|---|---|---|---|
| `synth-exo-Z.Z` | 488 B | 274,432 B | 15,044 B |
| `synth-exo-tar-Z.tar.Z` | 5,465 B | 274,432 B | 32,740 B |
| `a2ps.V4.3.tar.Z` | 30,255 B | 274,432 B | 120,880 B |
| `popper-1.7.tar.Z` | 59,323 B | 274,432 B | 224,232 B |

StuffIt classic method 2 is bounded the same way from the entry's compressed
size; 50 fixtures improved corpus-wide, none regressed, and the sampled
StuffIt classic peaks are unchanged because none of them is method-2 bound.
On-Mac figures agree with Linux to a constant 32 B of shell overhead. See
DECISIONS.md for why the table is sized once rather than grown.

¶ **The zip peak lost its 66,000 B floor on 2026-08-09.** Every zip used
to allocate the whole span an end-of-central-directory record could
occupy and scan it in memory; it is now scanned backwards through a
515-byte window on the stack, which is what a segmented set needed
anyway — a 66,000-byte read from the end of one spans two parts and
costs a disk swap to satisfy. The peak is now the 12,288 B decode
buffer, plus a deflate window where there is one, plus the central
directory, which is read once so that walking it does not interleave
with reading entry data:

| fixture | was | now |
|---|---|---|
| `4acalc.zip` | 12,288 | 12,493 |
| `4alnch11.zip` | 41,702 | 12,554 |
| `derived-MUSFMT10.ZIP` | 53,892 | 53,892 |
| `synth-exo-zip-deflate.zip` | 52,216 | 52,551 |
| `synth-exo-zip-store.zip` | 12,288 | 12,623 |

A large directory can therefore cost more than it used to on a small
archive — a few hundred bytes here, and unbounded in principle at 46
bytes plus a name per entry. That is why the directory buffer is
optional: when the allocation fails, the reader goes back to fetching
one record at a time and produces the same bytes more slowly, which
`ci.sh` checks by aiming a budget one byte under the run's own peak
(TESTING.md). The bound is the caller's budget, never a constant chosen
in the decoder.

‖ **Method 13's LZSS window is sized from the entry, not from the format's
64 KB.** MEASURED 2026-08-06; an instrumented run over the whole corpus counted
**0 back-references past produced output**, which is what licenses it
(DECISIONS.md 2026-08-06). 34 fixtures improved, none regressed; the corpus
maximum is unchanged at 76,944 B because some forks genuinely exceed 64 KB, so
the gain is at the small end — `derived-MacGzip.sit` 76,944 → 13,456 B, and
on-Mac `derived-Export.sit` 76,984 → 19,640 B.


★★ **A uu document posted in several parts** joins the same way, and the test
is stronger than BinHex's: a uu line's first character DECLARES how many bytes
it encodes, so a line whose length disagrees cannot be data and is stepped
over. What uuencode cannot do is notice a part that never arrived — it carries
no length and no checksum anywhere, so a set missing its MIDDLE part decodes to
a short file with nothing to object to (a missing LAST part is still caught:
the terminator and `end` live there). That limitation is asserted rather than
described, in `tools/run_uu.py`; OPEN_ITEMS.md.

★ **ARC and uuencode, in scope since 2026-08-15** (M13), when the brief
became "everything StuffIt Expander 4.0.2 expands". Neither occurs in this
corpus, so every archive under test is generated and handed to a second
implementation to grade — `unar` for ARC, `hexbin` for the UUTool shape
(TESTING.md). The methods: 1/2 stored, 3 RLE90, 4 squeeze (a Huffman tree of
int16LE node pairs, then RLE90), 5/6/7 crunch (12-bit LZW whose table is
addressed **by hash rather than by sequence**), 8 (12-bit compress LZW +
RLE90) and 9 (13-bit compress LZW), the last two over the shared `unc_lzw.c`;
CRC-16 per entry. 0x0a/0x0b are PKARC's and nothing reachable writes them. Peak heap, measured per method: stored and RLE90 4,096 B,
squeeze 5,124 B, the compress methods 6,660–6,664 B, and crunch **32,768 B**,
which is the whole spread — a 4096-entry table at 6 B an entry plus a 4 KB
stack. uuencode is a flat 4,096 B, whatever the file holds, because it
decodes a line at a time.

**Byte-exact on a real emulated Mac Plus at 4 MB and at the 1 MB floor**
(2026-08-15): `synth-arc-mixed.arc`, all nine methods in one archive, 9 files
at 32,800 B peak; `synth-uu-mac.uu`, both forks and its type, 1 file at
4,112 B — the same numbers at both memory sizes, and the same as Linux plus
the shell's constant 32 B. Both are in `tools/vmac/sample.txt`, which is 63
fixtures since M13.

**What is declined, and why it is declined rather than written:** ARC's
methods 0x0a (Crushed) and 0x0b (Distilled) are PKARC's, and nothing
reachable from here writes them, so an implementation could not be graded.

★★★ **ArcMac** — the Macintosh container, `0x1b` then the ordinary ARC header
59 bytes in — **extracts both forks since 2026-08-16**. One compressed stream
holds them, **data fork first**, with the CRC over the concatenation; the
header's two fork lengths are **little-endian**, as ARCMAC.DOC's *ArcMac File
Structure* states and both real archives confirm. Neither fact is in `arc.h`,
which is what this decoder was transcribed from, and the order is in no
document at all — it was measured by having ArcMac 1.3c archive a two-fork
file under Mini vMac (`tools/vmac/arcmac.py`; DECISIONS.md). Two archives in
the wild now read end to end: `ARCMACRC.BIN` (6 entries, methods 8 and 9, 1988)
and `ArcPop.Arc`. Splitting the stream across two forks allocates nothing, so
peak heap stays the underlying method's: `Packed.ARC` (method 8, 4,230 + 333)
extracts **byte-exact on a real emulated Mac Plus at 4 MB**, 1 file, 0 errors,
**8,000 B peak**, both fork CRCs equal to the bytes that went into ArcMac —
encoded on an emulated Mac, decoded on one. `unar` reads none of these: it
cannot recognise the format at all, which is why the encoder had to be the
oracle.

## Envelope auto-unwrap

`unclassic x` unwraps chained envelopes by content sniffing
(never by extension): MacBinary, BinHex, AppleSingle/Double, gzip and
.Z layers that yield exactly one file are recursively extracted and
the intermediate deleted (`-nr` disables; depth ≤ 8). Verified chains:
`.sit.bin`, `.sit.hqx`, `.tar.Z` (tools/run_unwrap.py, in CI).

A **StuffIt segment** is an envelope too, and joins that list: the
parts are joined, the file inside comes out, and if that file is an
archive the same recursion continues into it.

## Segmented archives (multi-part sets)

One logical file cut across several, one per floppy. **Three schemes
are implemented**: StuffIt segments, spanned ("split") zip and plain
`.NNN` splits. They differ in how much a part can prove about itself,
and everything else follows from that (DECISIONS.md 2026-08-08,
2026-08-09 and 2026-08-10).

### StuffIt segments

XADMaster's "StuffIt split file":
a 100-byte header on each part: `B0 56 00`, part number, the original
file's name, and 26 fingerprint bytes at offset 68 (type, creator,
Finder flags, both dates, both fork lengths). Concatenating the parts'
payloads in order gives the original file — resource fork, then data
fork. `src/fmt_sitseg.c` has the layout and its source.

Two properties of that header decide the design, and DECISIONS.md 2026-08-08
has why they decided it: **identity is content, not name** (a part belongs to a
set if its name bytes and those 26 bytes agree — the `misnamed` case in the
suite joins correctly and `unar` cannot read it), and **the set is
self-terminating** (`rsrclen + datalen` is the exact payload total, so no part
count is stored anywhere and none is needed).

**The join is read strictly forward: 0 backward crossings**, measured
over the 3-part and 12-part cases (`unclassic x --stats` reports part
opens and how many were backward). That is what decides the cost on
removable media — a backward crossing is a disk the user has to put
back — so it is measured rather than assumed.

Peak heap for the join is 8 KB: one buffer, no part table beyond the
caller's ~1.1 KB scratch struct, one part open at a time.

**Parts inside envelopes** — `Archive.sit.1.hqx`, which is how a set
was actually distributed — join on the Linux CLI since 2026-08-13. The
envelope comes off each part before the join rather than after it, and
the search is rationed: envelopes beside the archive are opened only
while the set is short of a part, at `UNC_SEG_HEAD` decoded bytes each,
and a part is decoded whole only once its fingerprint places it. Mixed
envelopes, wrapper names that say nothing, and parts in three
directories all join byte-exact; `unar` handed part 1 of such a set
unwraps that part alone and exits 0. **In the Mac shell too since
2026-08-14**, where a decoded part lands on the output volume as
`unclassic part N` and is deleted when the join is over. Not for the two
name-placed schemes, on Linux or Mac: a wrapped part's filename is the
wrapper's, and no reference says what that should look like
(DECISIONS.md 2026-08-13).

### Compact Pro segments

The one scheme whose layout is derived rather than transcribed: nothing
documents it, so it was measured on sets cut by Compact Pro 1.51 itself
(`tools/vmac/cptsegment.py`, DECISIONS.md 2026-08-14). Every segment
carries the same 8-byte header an ordinary archive has — signature,
volume, a 16-bit set identity shared by the whole set, and an index
offset that is 0 in all but the LAST segment. `src/fmt_cptseg.c` has the
layout and what would falsify it.

**Identity is content, not name** (the author's manual: "the names of the
files are not important"), so discovery matches headers exactly as it
does for StuffIt, and **any** segment opens the set — the application
itself requires the final one. An entry is addressed as (volume, offset
within that volume's file), so this reads in the same addressed mode as
a spanned zip.

Part opens (backward), measured, beside the floor each archive's own
directory permits — `run_segments.py` derives that floor independently:

| case | segments | measured = floor | without the index buffer |
|---|---|---|---|
| `cpt4` (9 files, folders) | 4 | 5 opens, 1 backward | 19 opens, 8 backward |
| `cpt5` (one entry) | 5 | 6, 1 | 6, 1 |

The last column is the fallback when the index allocation is refused:
same bytes, more crossings (DECISIONS.md 2026-08-14). Peak heap ~20 KB,
the ordinary Compact Pro reader's 16 KB of buffers plus the index.

`unar` cannot read one: given the final segment it calls it a whole
archive and writes garbage with exit 0 (MEASURED, and asserted by the
suite).

### Spanned ("split") zip — `NAME.z01` … `NAME.zip`

The parts concatenate with nothing to strip, and the archive addresses
itself as (part, offset within that part): "disk number start" at
offset 34 of each central-directory entry, and the two disk numbers in
the end-of-central-directory record. `src/fmt_zipseg.c` has the layout
and its sources.

Only the FIRST part (a local file header at offset 4) and the LAST (the
EOCD, the only place the part COUNT appears) identify themselves; the
parts between are undistinguished data, and `unar` refuses one too. So
the host orders parts by filename and the engine adjudicates the result
structurally — part count, central-directory position, every entry's
local header, every CRC-32. A deliberately lax reader (CRC and
signature checks removed) fails exactly the suite's *wrong order* and
*foreign part* cases, so those checks are load-bearing.

`zip -s` writes its `50 4B 07 08` marker even when the archive did not
need splitting. Such a file says "disk 0", needs no joining, and reads
as an ordinary zip — it sniffed as *unknown* before 2026-08-09.

The join is **not** read forward — the directory is at the end — but it
costs exactly one backward crossing, which is the floor the format
allows. Part opens (backward), measured, beside the floor each
archive's own directory permits; `run_segments.py` computes that floor
independently and requires the two to be equal, so this cannot drift
(DECISIONS.md 2026-08-09):

| case | parts | measured = floor |
|---|---|---|
| `zstored` | 5 | 6 opens, 1 backward |
| `zdeflate` | 4 | 5, 1 |
| `znested` | 3 | 4, 1 |
| `zmany` | 12 | 14, 2 |

`zmany` needs two because its central directory begins on part 11 and
crosses into part 12; where the directory sits is part of the floor.

Peak heap **12.4–13.0 KB** across those cases: the 12,288 B decode
buffer plus the central directory, which is read once into memory.
When that allocation does not fit the budget the reader falls back to
fetching one directory record at a time — same bytes out, at 16 opens
instead of 6 — so the bound is the allocator's rather than a constant
chosen here. Both paths are exercised in `ci.sh`.

### Segmented sets on a real emulated Mac Plus (System 6.0.8)

**All four schemes join on the Mac** as of 2026-08-14, and so does a set
whose parts are still inside envelopes — the StuffIt scheme only, which is the
one whose identity survives a wrapper. The StuffIt table below is from
2026-08-08; the other three are:

| scheme | how it was driven | result |
|---|---|---|
| Compact Pro, 4 MB and **1 MB** | `run.py`, opened at a MIDDLE segment, the others named `One`, `Three`, `Last` | 9 files byte-exact against the Linux oracle, peak heap 19,915 B |
| Compact Pro, last segment withheld | same | 0 files, refused — the negative control |
| Spanned zip, 4 MB and **1 MB** | `interactive.py --named zip`, opened at part 1 of 5 through Standard File | joined file **byte-exact**, 278,294 B |
| `.NNN` split, 4 MB and **1 MB** | `interactive.py --named split`, opened at part 1 of 3 | joined file **byte-exact** |
| Parts inside envelopes, 4 MB and **1 MB** | `interactive.py --wrapped`: part 1 as `Apart.sit.1.hqx`, part 2 as `zzz-download.bin`, part 3 as `Other.9.hqx` | same contents as the Linux CLI on the same three files, and no decoded parts left on the volume |
| A chained file (`.sit.hqx`), 4 MB and **1 MB** | `interactive.py --chain` | every layer comes off and the intermediate is removed — which this application did NOT do before 2026-08-14 (BLOCKERS.md) |

The two name-placed schemes go through the real UI rather than the
autotest, because the autotest opens a file called `archive.sit` and a
scheme decided by filename cannot be driven that way (DECISIONS.md
2026-08-14). All of it replays with `tools/vmac/segcheck.py`, one
command, which is what keeps this table re-runnable rather than
historical.

`derived-Cal.sit` (50,205 B) cut into three parts and put on one
floppy, the parts named `archive.sit`, `part-two` and `zzz` — names
that resemble neither each other nor the file inside:

| tier | result |
|---|---|
| Mini vMac, 4 MB | joined and written as `Cal.sit`, **byte-identical** to the original, type/creator `SIT!/SIT!` off the header |
| Mini vMac, **1 MB** (floor target) | same, byte-identical |
| 4 MB, part 2 removed | `ret = -11` (`UNC_ERR_SEGMENTED`), 1 entry error, the 20,000 B that part 1 held left on the volume; peak heap **8,208 B** |

Read back off the Out volume with hfsutils and compared to the source
file on the host, which is layer 9 of TESTING.md — not the on-screen
grid, which cannot see a filename. Re-run with:

```
python3 tools/vmac/run.py PART1 --extra-file HOST:MACNAME ... --keep-disks
```

The parts being found at all is the point of the middle column: the app
reads every file in the folder and asks the engine, so the names are
free.

### The "locate part N" dialog, driven on the same machine (2026-08-09)

Those runs use the autotest build, which has no user and does not
compile the dialog at all. The interactive application was driven
separately, with part 1 alone on the boot volume and parts 2 and 3 on a
second floppy so the folder scan has to fail:

```
python3 tools/vmac/interactive.py fixtures/derived-Cal.sit --segments -o DIR
```

| step | what the Mac showed |
|---|---|
| open part 1 | *Part 2 of "derived-Cal.sit" has not been found. Locate it, skip it, or cancel.* — Cancel / Skip / **Find...** |
| Find..., switch to the other floppy, offer part **3** | *That is part 3 of the same archive. Part 2 is the one needed.* |
| Find... again, offer part 2 | extraction resumes with no further prompt: locating one part rescans its folder, which picks up part 3 beside it |
| finish | *Extraction complete.* |

**It ends on a byte comparison, not on the screenshot**: the joined file
is read back off the volume the Mac wrote to and compared to the
fixture — 50,205 B, byte-exact. A screenshot of "Extraction complete."
is not evidence that the bytes are right, and this phase found two
harness bugs that each produced a plausible-looking wrong screenshot
(DECISIONS.md).

A part arriving on a disk inserted mid-run is driven by
`interactive.py --diskswap`; what no emulator here can settle about it — Mini
vMac gives every insertion a NEW drive — is MANUAL_TESTS.md, "A disk swap in
ONE drive".


### Plain `.NNN` splits

No header, no marker, no part count: the scheme is the naming
convention (`reference/XADMaster/XADSplitFileParser.m`). The host
builds the descriptor, the engine joins the consecutive run `.001` …
`.NNN` flat, and one entry comes out — the joined file, named without
the extension — for the caller's next layer, as for a StuffIt segment.
The joined LENGTH is the sum of the parts', which is the only place it
exists, so every part is located before extraction starts.

Part opens are one per part, 0 backward, on every case (`--stats`,
required to equal that floor in `ci.sh`). Peak heap is the 8 KB
streaming buffer; nothing else is allocated.

**What adjudicates such a set is the file it joins into**, and only
that. Measured, both directions: a swap of two parts of a split zip is
refused by the payload's own offsets and CRCs, unless the swap involves
part 1 — after which the join no longer sniffs as an archive and
nothing objects. A set missing its tail is undetectable in every case.
DECISIONS.md 2026-08-10.

## Hardening

- Differential: 809 fixtures byte-exact against `unar` manifests
  (both forks + type/creator), `./ci.sh`. `run_diff.py` prints the
  number it actually ran, plus two figures that must be read with it:
  **23 forks across 11 fixtures are oracle-unadjudicated** (both
  implementations decline every one of them, so the engine's own CRC-16
  is the only check), and **7 entries are compressed with a method the
  ORACLE names as outside v1 scope** and are graded on their names and
  entry counts alone. No fixture is skipped for anything our own engine
  says about it (TESTING.md, "When our engine declines an entry"). It was
  769 until 2026-08-08 and reached 797 that day in four steps, every one of
  them the measuring apparatus rather than new archives (BLOCKERS.md,
  DECISIONS.md).
- Robustness: 10 truncation/bit-flip variants per fixture — no
  crashes, hangs, or sanitizer trips under
  ASan+UBSan+`-fsanitize=alignment` (`-fno-sanitize-recover=all`).
- Fuzz: seeded mutation/splice/garbage fuzzing (tools/fuzz.py);
  4,000 cases clean at M9, 150-case smoke in every CI run.
- 32-bit `-m32` build runs the full suite (68000 discipline: no
  unaligned access, no recursion, 32-bit arithmetic in hot paths).

## Measured on a 7 MHz Mac Plus (Mini vMac 1x, System 6.0.8, 4 MB)

The first absolute timings this project has ever had. `run.py --emu mv-4M-1x`
separates boot from extraction — the application paints its "alive" grid
before touching a disk — so the extract column is the archive alone. Poll
interval 5 s, so that column is quantised to 5 s; it is an upper bound at this
resolution, not a stopwatch.

| Fixture | Format | In | Boot | Extract |
|---|---|---|---|---|
| derived-Export.sit | StuffIt | 1.6 KB | 10 s | 5 s |
| synth-packit-2.pit | PackIt | 3.4 KB | 10 s | 5 s |
| derived-keyAhead.cpt | Compact Pro | 0.9 KB | 10 s | <5 s |
| export-hc.hqx | BinHex | 3.1 KB | 10 s | 5 s |
| stuffit151mstr.bin | MacBinary | 0.5 KB | 10 s | <5 s |
| synth-exo-zip-store.zip | Zip | 8.4 KB | 10 s | 5 s |
| synth-exo-tar.tar | Tar | 20 KB | 10 s | 5 s |
| synth-exo-gz.gz | Gzip | 0.1 KB | 10 s | <5 s |
| macburger-helper.hqx | BinHex | 306 KB | 30 s | **150 s** |

**StuffIt 5 / Arsenic at 1x — and it is in a class of its own.** The list
above samples StuffIt 5 with a 4,611 B fixture, far too small to reach the
sampled inverse BWT, so the fallback's cost on real hardware went unmeasured
until 2026-08-07. Both Arsenic fixtures in the 1 MB sample, both paths,
extract time only, on a purpose-built 1 MB 1x emulator (`build_mv mv-1M-1x
1M z`; `setup.sh` had no such build until then):

| Fixture | Output | 4 MB — transform table | 1 MB — sampled index | ratio |
|---|---|---|---|---|
| `derived-a2basic.dmg.sit` | 205,019 B | **587 s** (peak 1,031,525 B) | **966 s** (peak 560,589 B) | 1.65x |
| `derived-Library_ISBN_Barcoder.sit` | 641,115 B | **768 s** (peak 1,682,142 B) | **1,898 s** (peak 614,134 B) | 2.47x |

**The fallback costs 1.65x to 2.47x, and Arsenic was already the slow one.**
Ten minutes for a 205 KB output is what the *fast* path costs a 7 MHz 68000;
before 2026-08-07 a 1 MB machine could not extract either entry at all. The
ratio widens with block fill, and neither the x86 ratio nor one fixture scaled
by output size predicts these — DECISIONS.md 2026-08-07 for both.

All four figures were measured on one build, with one emulator running at a
time. They supersede an earlier pair (537 s / 927 s) taken before the progress
rewrite; DECISIONS.md 2026-08-07 records the ~40 s between the two sets as
unexplained.

**8/8, and the shape is the useful part: for small archives the BOOT dominates
and extraction is seconds.** A stripped System 6.0.8 reaches the application in
about 10 s; everything in this table then extracts in under five. The one
larger 1x measurement that exists — `derived-EmpireBuilderDemo.sit`, 278 KB in
and 417 KB out — took **~134 s**. So a few kilobytes is instant, a quarter of a
megabyte is a couple of minutes.

**The large BinHex is not an anomaly.** `macburger-helper.hqx` simply takes
150 s; the rate is very non-uniform (16% of the input in the first seven
minutes, the last 205 KB in a hundred seconds), which is what made the
timeouts chosen for it mislead three times. BLOCKERS.md.

## Relative decode cost per format (Linux, same engine)

Absolute Mac Plus timings are still missing (BLOCKERS.md says why), but the
engine's *relative* cost is a property of the code and transfers to any CPU as
a ratio. Measured with `unclassic t`, best of three, on the release build:

| Fixture | Format | In KB | Out KB | ms | in KB/s |
|---|---|---|---|---|---|
| kermitut9test.bin | MacBinary | 297 | 296 | 0.6 | 485,802 |
| derived-PCCTS.tar | Tar | 280 | 231 | 0.6 | 439,603 |
| derived-PackIt.pit | PackIt (stored) | 60 | 60 | 0.7 | 85,110 |
| macburger-helper.hqx | BinHex | 299 | 253 | 2.9 | 102,708 |
| derived-MUSFMT10.ZIP | Zip (deflate) | 168 | 498 | 3.9 | 42,704 |
| popper-1.7.tar.Z | Compress | 58 | — | 2.0 | 29,526 |
| PCCTS.tar.gz | Gzip | 62 | — | 2.0 | 31,162 |
| derived-EmpireBuilderDemo.sit | StuffIt (13) | 272 | 407 | 9.0 | 30,204 |
| derived-XferIt_1.5b4.sea | Compact Pro | 279 | 926 | 18.2 | 15,351 |
| derived-KeyGraphics.sit | StuffIt 5 (Arsenic) | 5 | 33 | 1.6 | 2,859 |

The ordering is the useful part: envelope formats (MacBinary, tar) are
essentially a copy; BinHex costs a few times that; the real compressors —
StuffIt 13 and Compact Pro's LZH — are 15-30x the cost of a copy per input
byte; and Arsenic is in a class of its own, two orders of magnitude off the
top of the table, which is consistent with its memory profile.

**This is not a Mac Plus timing.** It says a Compact Pro archive costs roughly
six times what a BinHex of the same size costs, on any CPU. The one authentic
1x measurement that exists — `derived-EmpireBuilderDemo.sit`, ~134 s for
278 KB — is in the StuffIt-13 row, so the ratios can be used to reason about
the others, cautiously and from a single anchor.

## Real-hardware verification (Mini vMac — System 6.0.8, 4 MB Mac Plus, 68000)

The Retro68 Mac shell was replayed against a 63-fixture sample spanning all
sixteen formats on a **real System 6.0.8 / 4 MB Mac Plus** under Mini vMac
(a true 68000). Every extraction is verified ON THE MAC ITSELF: the app
CRC-32s both forks after reading them back through the File Manager and the
result — painted to the framebuffer, read from a screenshot — is
cross-checked against the same engine's Linux output (`tools/vmac_check.py`,
`tools/decode_grid.py`).

**63/63 byte-exact PASS** (2026-08-15, re-run after the BinHex line rule changed — every `.hqx` in the sample goes through it; 61/61 earlier the same day, before M13 added ARC and uuencode; 55/55 on 2026-08-08, before M12 added
six DiskDoubler fixtures and one Now Compress fixture to the sample) — data
forks exact, resource forks exact bar the OS-stamped reserved header
(bytes 16–127).

**The sample was 44 fixtures until 2026-08-08**, when nine that had never had
an oracle manifest gained one and were added: seven THINK C projects holding
both `X` and a real `X.rsrc`, and two with a leading-`~` name. Two more joined
the same day for the same reason once method 6 had an oracle —
`derived-INITLoader.sit` and `synth-sit-fixhuf.sit`, measured on all three
Mini vMac tiers that day and byte-exact on each. Every `n/44`
figure elsewhere in this file refers to the smaller sample and is left as it
was measured. The nine are the only fixtures here whose shape can distinguish
a fork-naming mistake from a correct extraction, which is why the host-side
readers had to stop guessing at `<X>.rsrc` sidecars first (DECISIONS.md,
2026-08-08).

The sample is `tools/vmac/sample.txt`; reproduce with

    tools/vmac/setup.sh                              # once
    tools/vmac/run.py --list tools/vmac/sample.txt   # 4 MB

An `EMUDIED` verdict (the emulator process exits before the application paints)
is a harness event, not a Mac-side failure — `tools/vmac/README.md`. An earlier
39/44 record of this run does not survive the rebuilt harness (BLOCKERS.md,
*Withdrawn claims*).

Note that the emulator now runs **all out** rather than at Mac Plus speed,
so this harness measures correctness only — **no timing claim about a 7 MHz
68000 can be drawn from it**, including the previously recorded "185 s".

On-Mac engine peak heap (high-water mark) by format, matching the Linux
`--stats` figures:

| Format | on-Mac peak heap |
|---|---|
| MacBinary / BinHex / Tar | 8 KB |
| PackIt | 9 KB |
| Compact Pro | 19 KB |
| Zip | 12–53 KB (re-measured 2026-08-09, was 12–65: see ¶) |
| Gzip | 51 KB |
| StuffIt classic | 19–72 KB‖ |
| Unix compress (.Z) | 15–219 KB§ |
| StuffIt 5 (Arsenic) | 0.63–2.53 MB (block *fill* dependent — see †) |
| DiskDoubler / Now Compress | extracted and byte-exact on both Mini vMac tiers since 2026-08-15 (see above); the Mac OS 9 rows below still predate M12 |

## System 7 tier (Mini vMac — System 7.0.1, 4 MB Mac Plus, 68000)

Until 2026-08-01 every on-Mac result in this repository came from one point of
the System 6 → Mac OS 9 range the project claims: System 6.0.8. This is the
second point.

**System 7.0.1, not 7.1.** 7.1 survives on the mirrors only as floppy disk
sets and a beta ISO, and installing from emulated floppies is hours of GUI
automation for a system that differs in nothing this project exercises. What
matters is that it is System 7 rather than 6, because two things only exist
above System 6: Standard File returns a **working-directory** reference in
`SFReply.vRefNum` rather than a plain volume refNum, and the Process Manager
is always running, so the `SIZE` partition governs the launch. Mini vMac's
Mac Plus supports up to 7.5.5, so this is the same 68000 as every other row.

**55/55 byte-exact PASS at 4 MB** (2026-08-08; 44/44 before the sample grew) —
the same committed sample, the same on-Mac CRC-32 read-back, the same twelve
formats:

    tools/vmac/run.py --system Sys7.img --list tools/vmac/sample.txt

Engine peak heap is **identical to System 6.0.8 at the same memory size on
every fixture**, which is the expected result — the engine allocates through
the same callback and never asks the system for anything — but it had never
been shown. Re-measured with the final build on 2026-08-07:
`derived-RWAsm_Folder.sit` 160,766 B, `derived-KeyGraphics.sit` 181,774 B,
`derived-Troi-ClipSave-Plug-in1.1.sit` 660,262 B. (The figures this paragraph
carried before — 643.2 KB, 1810.8 KB, 710.6 KB — predate the 2026-08-03 block
sizing and were never refreshed.)

**Where this tier and the 1 MB tier disagree is the whole point of the
adaptive inverse BWT, and it is visible in one number.** Same binary, same
fixtures:

| fixture | System 7, 4 MB | System 6, 1 MB |
|---|---|---|
| `derived-a2basic.dmg.sit` | 1,031,525 B (transform table) | 560,589 B (sampled index) |
| `derived-Library_ISBN_Barcoder.sit` | 1,682,142 B (transform table) | 614,134 B (sampled index) |

Given room, the decoder takes the fast table and spends 1.0 and 1.6 MB on it.
Given a 1 MB machine, the table's allocation fails and it takes the sampled
index instead. Nothing selects this but the allocator saying no, and both
columns are byte-exact.

**This tier is 4 MB.** **The 1 MB floor target is System 6, and only
System 6**, and it is demonstrated by the 55/55 run below.

### DiskDoubler and Now Compress on the Mac (2026-08-15)

The seven fixtures M12 added, replayed on both tiers the day the formats
landed. **Identical numbers at 4 MB and at 1 MB** — nothing in either decoder
varies with the machine, and the on-Mac peak agrees with the Linux figure to
the shell's constant 16 B:

| Fixture | Format / method | Files | Peak heap on the Mac | Data | Rsrc |
|---|---|---|---|---|---|
| `derived-DandStoQIF2.sea` | DiskDoubler AD1 (9) | 3 | 16,400 B | 20,918 B | 24,562 B |
| `derived-MAZv143.sea` | DiskDoubler Compact Pro (8) | 2 | 19,318 B | 57,078 B | 40,079 B |
| `derived-MacPass390.sea` | DiskDoubler Compact Pro (8) | 3 | 19,318 B | 0 B | 351,825 B |
| `derived-DD_Expand.sea` | DiskDoubler DDn (10) | 1 | 102,432 B | 0 B | 270,362 B |
| `derived-LHA_Expander_1.0.3.sea` | DiskDoubler DDn, folders | 5 | 110,624 B | 69,776 B | 82,778 B |
| `derived-Terrainman_2.0__.sea` | DiskDoubler DDn + delta-1 | 12 | 106,528 B | 95,860 B | 245,265 B |
| `derived-Expand_Now_1.0.1.sea` | Now Compress | 1 | 131,088 B | 0 B | 88,942 B |

`derived-DandStoQIF2.sea` was in the sample before M12 as a REFUSAL case —
the only one there has ever been — and is now an extraction.

**Multi-document BinHex was checked here too**, on a file the corpus does not
contain: `export-hc.hqx`, a mail separator, and `mac-rot13.hqx` concatenated.
2 files byte-exact at 4 MB and at 1 MB, 8,208 B peak. It is not in
`sample.txt` because it is not a corpus fixture; regenerate it by
concatenating those two with any text between them, which is what
`tools/run_multihqx.py` does on Linux.

## Floor target verification (Mini vMac — System 6.0.8, **1 MB** Mac Plus, 68000)

The same 63-fixture sample was replayed on a Mini vMac built for **1 MB of
RAM** — the project's floor target — one boot per fixture, same on-Mac
CRC-32 verification (`tools/vmac/run.py --mem 1M --list tools/vmac/sample.txt`).
The engine budget is derived from `FreeMem` at startup.

**63/63 byte-exact PASS** (2026-08-15, with M13's two; 61/61 before them; 55/55 on 2026-08-08 and 44/44 on
2026-08-07, before the recovered fixtures, the method-6 pair and M12's seven
joined the sample). There are no memory-budget refusals
left at the floor target: every fixture in the sample, in every format,
extracts byte-exact on a 1 MB Mac Plus. The six StuffIt 5 rows, which were the
last to arrive, with peak heap as the Mac itself reports it:

| Fixture | Format | Outcome at 1 MB | Peak heap |
|---|---|---|---|
| derived-RWAsm_Folder.sit | StuffIt 5 | **all 38 entries byte-exact** | 160,766 B |
| derived-KeyGraphics.sit | StuffIt 5 | all 1 entry byte-exact | 181,774 B |
| derived-PuzzleGetter_0.8.sit | StuffIt 5 | **all 26 entries byte-exact** | 269,084 B |
| derived-a2basic.dmg.sit | StuffIt 5 | **all 1 entry byte-exact** | 560,589 B |
| derived-Library_ISBN_Barcoder.sit | StuffIt 5 | **all 34 entries byte-exact** | 614,134 B |
| derived-Troi-ClipSave-Plug-in1.1.sit | StuffIt 5 | **all 13 entries byte-exact** | 660,262 B |

The last two rows are the ones that moved on 2026-08-07: `a2basic` was a clean
per-entry refusal of its only entry, and `Library_ISBN` delivered 33 of 34.
Both now need a *sampled* inverse BWT rather than the 4-bytes-per-byte table,
chosen automatically because the table's allocation fails first.

**What those three entries actually hold**, measured 2026-08-03 by
instrumenting `numbytes` where `sit_arsenic.c` sizes the transform vector.
The figures matter because a false one — "each fills a 512 KB block" — closed
this tier as needing a redesign for a day (BLOCKERS.md, *Withdrawn claims*):

| fixture | largest block fill | capacity by doubling | peak |
|---|---|---|---|
| `derived-Library_ISBN_Barcoder.sit` | 323,384 B | 512 KB | 1,854,208 B |
| `derived-a2basic.dmg.sit` | 197,515 B | 256 KB | 1,088,588 B |
| `derived-Troi-ClipSave-Plug-in1.1.sit` | **124,637 B** | 128 KB | 666,004 B |

The peak model `~35 KB parser + capacity + 4 × fill` reproduces all three to
within a rounding step, so the fills are confirmed by two independent routes —
and the 4× transform vector (487 KB, 772 KB and 1,263 KB respectively) is
visibly the dominant term, which is what the sampled inverse BWT went after.

**The CLI's `--budget` simulation is now cross-validated against the real Mac
allocator.** `unclassic --budget 678392` on Linux predicted 560,535 B and
614,080 B for those two; the Mac measured 560,589 B and 614,134 B — 54 bytes
apart in both cases. That is worth stating because every budget figure
elsewhere in this file is a Linux number.

**This tier moved four times in six days, 39/44 → 44/44**, one DECISIONS.md
entry per step and none of them a decoder change until the last:

| date | what changed | tier |
|---|---|---|
| 2026-08-02 | the shell stopped reading the whole archive into RAM | 39/44 → 40/44 |
| 2026-08-03 | the Arsenic block stopped being allocated at its declared 512 KB | 40/44 → 41/44 |
| 2026-08-06 | the block's first allocation sized from the entry, so growth strands no heap | 41/44 → 42/44 |
| 2026-08-07 | the transform vector is not built when it does not fit | 42/44 → 44/44 |

`derived-RWAsm_Folder.sit` went 595.7 KB → **160,766 B** across the first two,
for the same 38 byte-exact entries.

The three entries that were refused before the last step peaked at 1,854,208 B
(`Library_ISBN`), 1,088,588 B (`a2basic`) and 666,004 B (`Troi-ClipSave`) on the
fast path — `~35 KB parser + capacity + 4 × fill` reproduces all three. Under
the sampled index the same entries extract fully from **245,897 B**, **393,028 B**
and **167,455 B**, bisected minima rather than peaks under a cap. (This is where
the withdrawn "each fills a 512 KB block" claim lived; BLOCKERS.md has it and
what it cost.) The per-entry refusal machinery is unchanged and still correct;
nothing in the sample reaches it any more.

**`popper-1.7.tar.Z` and `PCCTS.tar.gz` used to fail here and no longer do** —
the Mac sink stopped accumulating whole output forks, so the shell's RAM use no
longer depends on output size at all, and these two have the sample's largest
output forks (174 KB and 287 KB). Both byte-exact at 1 MB, engine peak heap
unchanged; the old path stays buildable as `UNC_MAC_STAGE_WRITES` and both are
byte-exact through the qemu-m68k mock in CI. BLOCKERS.md, *Corrected figures*,
and DECISIONS.md for the HFS param-block rewrite that unblocked it — and for the
`HOpen` attribution that was withdrawn.

## Mac OS 9 tier (QEMU PowerPC — Mac OS 9.2, `mac99`, 512 MB, 68LC040 emulation)

The third and last point of the System 6 → Mac OS 9 range the project claims,
and the only one where the 68k binary does not run on a 68k CPU: Mac OS 9.2 on
emulated PowerPC executes it through the **68LC040 emulator** built into the
system. Nothing above System 7 had ever run it.

**13/13 byte-exact** — `tools/vmac/os9sample.txt`, one fixture per format,
each in its own boot from a pristine copy of the master image:

    tools/vmac/os9.py --setup                                   # once
    tools/vmac/os9.py --list tools/vmac/os9sample.txt -o <dir> --launch

| fixture | format | files | data bytes | rsrc bytes | result |
|---|---|---|---|---|---|
| `export-hc.hqx` | BinHex | 1 | 1,615 | 0 | ✅ byte-exact |
| `derived-keyAhead.cpt` | Compact Pro | 1 | 0 | 1,233 | ✅ byte-exact |
| `synth-exo-Z.Z` | compress | 1 | 2,200 | 0 | ✅ byte-exact |
| `synth-exo-gz.gz` | gzip | 1 | 2,200 | 0 | ✅ byte-exact |
| `stuffit151mstr.bin` | MacBinary | 1 | 0 | 365 | ✅ byte-exact |
| `synth-packit-2.pit` | PackIt | 5 | 3,050 | 2,020 | ✅ byte-exact |
| `derived-Export.sit` | StuffIt | 1 | 6,944 | 0 | ✅ byte-exact |
| `derived-DDT.sit` | StuffIt with a resource fork | 2 | 1,473 | 3,504 | ✅ byte-exact |
| `derived-KeyGraphics.sit` | StuffIt 5 / Arsenic | 1 | 0 | 33,484 | ✅ byte-exact |
| `derived-XferIt_1.5b4.sea` | Compact Pro self-extracting | 10 | 679,423 | 268,752 | ✅ byte-exact |
| `derived-DandStoQIF2.sea` | DiskDoubler: must REFUSE | 0 | — | — | ✅ declined, as Linux did **then** — pre-M12, not re-run |
| `synth-exo-tar.tar` | tar | 4 | 7,788 | 0 | ✅ byte-exact |
| `synth-exo-zip-deflate.zip` | zip | 4 | 7,788 | 0 | ✅ byte-exact |

**13/13**, 32 files, 712,481 data bytes and 309,358 resource-fork bytes compared.

This tier reads its result **off the disk rather than the screen** — both forks
of every extracted file lifted out with hfsutils and compared byte for byte
against `unclassic x -nr` — so unlike the Mini vMac tiers it compares **names,
folder structure and 8-bit characters** too, which is how it caught the gzip/.Z
fallback-name defect on its first sweep (TESTING.md for what each layer can and
cannot see). `derived-XferIt_1.5b4.sea` alone lands 10 files three folders deep,
and PackIt's `Appé` is a MacRoman name that has to survive the round trip.

**The sample is small on purpose:** each fixture costs a whole boot (~110 s plus
a 2 GB image copy) against Mini vMac's ~5 s, so this tier samples for breadth of
format, and the memory-budget spread `sample.txt` exercises is a 1 MB question
on a 512 MB machine.

**The Finder is driven from the keyboard.** The pointer does not work in this
guest at all — five mouse primitives measured at exactly zero effect, cursor
pinned to screen corners. See BLOCKERS.md, and `tools/vmac/os9probe.py` for
the measurement.

### Onto HFS+ (the same machine, the boot volume instead of the transfer disk)

Everything above extracts onto the transfer volume, which is HFS. The OS 9
boot volume is HFS+, so `--hfsplus` renames it to `Out` from the keyboard and
runs the **autotest** build against it: the extraction lands on HFS+, and the
application CRC-32s both forks after reading them back through the File
Manager, exactly as the Mini vMac tiers do.

    tools/vmac/os9.py fixtures/derived-Berkeley_Packet_Monitor.sit \
                      -o <dir> --hfsplus

| fixture | files | data | rsrc | peak heap | result |
|---|---|---|---|---|---|
| `derived-Berkeley_Packet_Monitor.sit` | 31 | 372,301 B | — | 779.1 KB | ✅ CRC + length identical to Linux |
| `derived-XferIt_1.5b4.sea` | 10 | 679,423 B | 268,752 B | 18.8 KB | ✅ CRC + length identical to Linux |

Both report `ret=0` with zero per-entry errors, and every output **name** on
HFS+ is exactly what the 31-character rule predicts — including the one entry
in the Berkeley fixture whose name is 34 characters and must be truncated. A
68k application reaching HFS+ through the classic File Manager is capped at 31
characters just as it is on HFS, so HFS+ changes nothing here; that is the
result, and it was worth measuring rather than assuming.

Two things make this tier trustworthy:

- **The answer comes back as a file, not off the screen** — `at_report_file()`
  on the plain-HFS input volume, because the framebuffer channel that works on
  a Mac Plus is invisible on OS 9's 32-bit screen. The output volume was never
  the obstacle; the reporting channel was (DECISIONS.md 2026-08-02).
- **That the output really landed on HFS+ is measured.** hfsutils sees only the
  HFS wrapper, and after the run it still contains exactly one file,
  `Where_have_all_my_files_gone?` — so none of those 41 files went to plain HFS.
  A signature word proves nothing here (BLOCKERS.md).

One corroboration falls out of it: the Mac's **unmasked** resource-fork CRC
equals Linux's **masked** one, so Mac OS 9 leaves the 112-byte reserved header
area alone where System 6 stamps it — the same thing the byte-level comparison
found on the HFS tier.

### The `SIZE` partition under OS 9's Process Manager

Built with a 600 KB preferred partition and run against
`derived-KeyGraphics.sit`, which needs ~656 KB: **1 entry refused, 0 files,
`ret == UNC_OK`, peak heap 35.5 KB** — the same figure System 7.0.1 gives, on
a machine with 512 MB of RAM. The partition governs, not the hardware, and
35.5 KB is parser state alone: the 512 KB Arsenic block was declined at
request time, never allocated.

Same binary, same fixture, three systems — the partition governs and System 6
without MultiFinder ignores `SIZE` outright, exactly as the resource's comment
always claimed and nothing had ever shown:

| System | Outcome | Engine peak heap |
|---|---|---|
| System 7.0.1 (4 MB) | **1 entry refused, 0 files** | 35.5 KB |
| Mac OS 9.2 (512 MB) | **1 entry refused, 0 files** | 35.5 KB |
| System 6.0.8 (4 MB) | 1 file, byte-exact | 656.8 KB |

The 656.8 KB row is the control — the same figure the 4 MB sweep records for
that fixture, with nothing changed but the partition. Method and commands in
`tools/vmac/README.md` ("The `SIZE` partition").

**Still not covered here:** names HFS+ permits that HFS does not — probably
unreachable through the classic File Manager at all, since it caps at 31
characters on either filesystem, but that is unproven either way. Real PowerPC
silicon, like real 68k silicon, remains untouched.

## Compared with StuffIt Expander 4.0.2 (Aladdin, April 1996)

The free tool a user would otherwise run on the machine itself, and the only
external yardstick this project has (why it was worth applying: DECISIONS.md
2026-08-15). **This is its documentation against our measurements: Expander
has never been RUN here**, and no row below is a head-to-head observation of
its behaviour.

**Where the Expander column comes from.** Its own distribution,
`stuffit_expander_4.0.2.sea_.bin` from Macintosh Garden: MacBinary around a
StuffIt self-extracting archive around a 400K HFS image. `unclassic x` walked
the chain and produced an image byte-identical to `unar`'s (410,624 B, md5
`888c0ca0b93f6ee0ff67e89926e20f83`), and every quotation below is a string
read out of that image — the shipped Read Me, the "What's new" file and the
application's own alert strings. Web sources are used for dates and for what
later versions did, never for what 4.0.2 does.

### Coverage over this corpus

805 files in `fixtures/` — the corpus as it stood before M13 added two
generated ones — classified by INNERMOST format — envelopes unwrapped
with `x -nr` first, then `unclassic sniff` — because both tools decode BinHex
and MacBinary and then continue into what was inside (measured 2026-08-15,
re-measured the same day after M12: the total read 807 and the corpus is 805,
which moved the non-archive row and nothing else):

| Innermost format | files | Expander 4.0.2 | unclassic 0.10 |
|---|---|---|---|
| StuffIt classic, incl. `.sea` | 454 | ✅ | ✅ |
| Compact Pro, incl. `.sea` | 216 | ✅ | ✅ |
| envelope over a non-archive | 36 | ✅ | ✅ ✧✧ |
| StuffIt 5 / Arsenic | 62 | ❌ postdates it | ✅ |
| zip, gzip, `.Z`, tar | 16 | ⚠️ paid add-on, System 7 only | ✅ |
| PackIt | 5 | ❌ not in its list | ✅ |
| DiskDoubler, Now Compress | 14 | ❌ | ✅ since 2026-08-15 |
| LZH, StuffIt X | 2 | ❌ | detect-only, named |
| **total** | **805** | **708 alone, 724 with the add-on** | **803 extract, 2 named** |

✧✧ The 36 break down as 31 envelopes whose payload is a resource-only file,
and 5 whose payload is a document: two HyperCard `STAK`s, one damaged Compact
Pro archive whose index offset points past its own end (`unar` declines it
too), and **two Alysis SuperDisk! files** (`Disk Expander .X`,
`SD! Utilities.x` — the header carries the string `SuperDisk! Add-In Module`).
SuperDisk! is the one format the corpus actually holds that nothing here
names: a user gets *unknown*, and `unar` reads no further than the envelope
either. OPEN_ITEMS.md, *Out of scope for v1*.

The 62 StuffIt 5 fixtures are the largest single difference, and it is a date
rather than a capability: 4.0.2 shipped two years before the format. Handed
one it answers *"You may need a newer version of the StuffIt Engine to work
with this archive."*

### Capability by capability

| | StuffIt Expander 4.0.2 | unclassic 0.10 |
|---|---|---|
| Floor system | System 6.0.5 (its Read Me) | System 6.0.8, measured on a 1 MB Mac Plus |
| Everything beyond `.sit`/`.cpt`/`.hqx`/`.bin` | needs DropStuff with Expander Enhancer, *"a **System 7-only** shareware product"* | in the same free application, on System 6 |
| Installed pieces | application + StuffIt Engine extension + the add-on | one 85 KB application, no extension, no installer |
| StuffIt segmented sets | with the add-on, so System 7 only | yes, System 6 and up |
| Compact Pro segmented sets | *"StuffIt Expander cannot expand encrypted or segmented Zip or Compact Pro files"* | yes |
| Spanned zip sets | same sentence — no | yes |
| Plain `.001`/`.002` splits | not claimed | yes |
| Parts still inside per-part envelopes | not claimed | yes, StuffIt sets |
| How a part is identified | not stated | by its header, never by its filename (zip and `.NNN` sets excepted — see "Segmented archives") |
| Segment joining, known defect | *"if the `Delete segments after joining` preference is selected, and you run out of disk space during a join operation, the first segment will be deleted even though the joining is not complete"* | parts are never deleted; the Mac shell removes only what it wrote |
| Encrypted archives | yes — it prompts, and knows *"You have entered an incorrect password"* | detected and refused, out of scope |
| Multipart BinHex | *"Multipart BinHex files, such as those appearing in Internet newsgroup postings (e.g. comp.binaries.mac), are fully supported"* — multiple documents in one text file, and one file broken into several pieces | several documents in one file since 2026-08-15 (††, above); a document broken across FILES joins where the parts are named `.001`, `.002` … |
| Compact Pro comments | written out beside the extracted items | read and CRC'd, never surfaced |
| `.arc` (ARC / ArcMac) | with the add-on | **yes since 2026-08-15**, methods 1-9; ArcMac's two-fork payload since 2026-08-16 (★★★ above) |
| uuencode (`.uu`) | with the add-on | **yes since 2026-08-15**, plain and UUTool's two-fork shape |
| AppleLink `.pkg`, StuffIt SpaceSaver | with the add-on | no, and not sniffed either. Not a decision about scope any more — a decision about evidence: neither has a reference implementation or a published layout anywhere reachable, so rule #1 forbids writing one. OPEN_ITEMS.md, *Out of scope for v1*, records what was searched |
| Chained expansion (`.sit.hqx`) | yes, and can be turned off | yes, `-nr` turns it off |
| System 7 conveniences | drag-and-drop of files, folders and whole disks; watch folders; background expansion; Apple events | none; Standard File, one archive at a time |
| Verification | none published | 809 fixtures byte-exact against `unar`/`macunpack` — bar the one uuencode fixture, which `unar` cannot read at all and whose ground truth is its generator's input, with `hexbin` agreeing |
| Licence | free, closed | free, LGPL-2.1-or-later |
| Memory partition | **not measured** — reading the app's `SIZE` resource needs an HFS reader this machine does not have | engine peak heap per format in the matrix above |

### Sources

- The application itself, extracted as described above: `Read Me`, `What's new
  in Expander`, and the alert strings in `StuffIt Expander 4.0.2`.
- [Gryphel Project — Stuffit Expander](https://www.gryphel.com/c/sw/archive/stuffexp/),
  for which versions run under Mini vMac and on which systems.
- [Macintosh Garden — StuffIt Expander 4.0.2](https://macintoshgarden.org/apps/stuffit-expander-402),
  the distribution used here.
- [ATPM 5.05 — review of StuffIt Deluxe 5.1.2](https://atpm.com/5.05/stuffit.shtml),
  for StuffIt 5 archives being unreadable by 4.x.
- [Wikipedia — StuffIt Expander](https://en.wikipedia.org/wiki/StuffIt_Expander),
  for freeware status and version history.
