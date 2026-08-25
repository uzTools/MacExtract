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
| PackIt (.pit) | extract | store, Huffman; **PMa5 and PMa6 decrypted** (an XOR keyed by DES's PC-1, and DES) | 4 fixtures (1 real + 3 synthetic PMa4) | 9 KB | full |
| Compact Pro (.cpt) | extract | RLE, LZH+RLE; **encrypted entries decrypted**, from a reading of the application that the application then graded, both directions (*Compact Pro's cipher*, below); the archive **comment** is saved rather than dropped | 108 fixtures | 24 KB | full |
| StuffIt classic (.sit) | extract | 0 store, 1 RLE90*, 2 LZW, 3 Huffman, 5 LZAH, 6 fixed Huffman‡, 8 MW, 13 LZSS+Huffman; **encrypted forks decrypted** (StuffItDES, and the 'MKey' resource — *Encryption*, below) | 227 fixtures‡‡ | 8–76 KB‖ | full |
| StuffIt 5 (.sit) | extract | 0, 13, 15 Arsenic; **encrypted forks decrypted** (RC4 under MD5(password)) | 31 fixtures | 0.15–2.53 MB† | 23 of 31 fixtures extract FULLY; the rest refuse per entry |
| Zip | extract | store, deflate, **PKWARE's cipher and WinZip's AES** (128/192/256); other methods and PKWARE strong encryption are per-entry errors | 5 fixtures (2 of them PKZIP 1.x, graded on names and entry counts only — Implode is out of v1 scope, and `unar` adjudicates 5 of their 7 entries) | 12–54 KB¶ | full |
| Gzip | extract | deflate | 3 fixtures | 51 KB | full |
| Unix compress (.Z) | extract | LZW ≤16 bit | 4 fixtures | 219 KB§ | full |
| Tar (ustar/v7) | extract | — (links reported unsupported) | 3 fixtures (2 real 1990 v7 tars) + unit tests | 8 KB | full |
| StuffIt segment (multi-part) | extract | — (join only; the joined file is the next layer) | 7 synthetic sets, oracle-adjudicated, + 3 with each part in its own envelope (CLI only) | 8 KB | full |
| Zip segment (spanned, .z01…/.zip) | extract | store, deflate — the zip reader, over the joined parts | 5 generated sets, adjudicated 4 ways (source tree, `unar`, us split, us unsplit) | 12–13 KB¶ | full |
| Compact Pro segment (multi-part) | extract | RLE / LZH+RLE — the Compact Pro reader, over the segments | 2 generated sets + 2 cut by Compact Pro 1.51 itself | 20 KB | full |
| DiskDoubler split (`SPLT`) | extract | — (join only; the joined file is the next layer) | 6 real parts (3 sets, cut by DiskDoubler itself, in `fixtures/`) + 8 generated sets, adjudicated against the published files they were cut from — no oracle exists | 8 KB | full |
| Split file (plain .001/.002) | extract | — (join only; the joined file is the next layer) | 3 generated sets, adjudicated against the bytes that were cut, `unar` where it can join, and our unsplit read | 8 KB | full |
| StuffIt X (.sitx) | detect only | — | — (no fixture) | — | — |
| DiskDoubler (DD, DDAR, DDA2) | extract | **all eleven**: 0 store, 1 Unix compress, 2/5 splay Huffman, 3 RLE90, 4 StuffIt Huffman, 6/9 AD LZSS, 7 Stac LZS, 8 Compact Pro, 10 DDn✦ | 88 fixtures (6 harvested + 82 CC0 files graded against their own originals, in `ci.sh` since 2026-08-21) + 19 BinHexed copies of those + 28 specimens (2 written by DiskDoubler 3.7 under Mini vMac, 2 off its distribution disk, 24 off Salient's 3.1.2 disk)✦ | 8–392 KB✦ | full |
| Now Compress | extract | stored, LZSS, Huffman, Huffman+LZSS, "new" LZSS✧ | 2 real fixtures + 13 generated archives (all five shapes, adjudicated by `unar`); `synth-now-mixed.now` also has an `unar` manifest and is in the differential suite | 134 KB✧ | full |
| ARC / ArcMac (.arc) | extract | 1/2 store, 3 RLE90, 4 squeeze+RLE90, 5/6/7 crunch, 8 12-bit LZW+RLE90, 9 13-bit LZW, 0x7f compress; ArcMac's two-fork payload since 2026-08-16★★★; 0x0a/0x0b (PKARC) declined per entry★; **garbled (password-XORed) members decrypted** | 10 generated archives (methods 1-9, adjudicated by `unar`) + 3 written by Debian's `arc` 5.21q; `synth-arc-mixed.arc` also has an `unar` manifest and is in the differential suite | 4–32 KB★ | full |
| btoa (`xbtoa`/`.ascii`) | extract | — (base-85 ASCII armour; both the `xbtoa5` and the older `xbtoa Begin` framings)◆ | no corpus file and no second reader: graded against **btoa 5.2.1 itself**, which encodes the subjects `tools/run_btoa.py` decodes | 12 KB | full |
| uuencode (.uu, incl. UUTool) | extract | — (plain uu, UUTool's two-fork "MU" shape, and documents posted in several parts★★) | 7 generated cases, the two-fork ones adjudicated by macutils' `hexbin`; `synth-uu-mac.uu` is in the differential suite | 4 KB | full |
| Alysis SuperDisk! (.X, .x) | extract | **both containers** (record-stream archive and single file); methods 1-4 and 5-8 (a finite-context predictor over a 13- or 16-bit context, with the flag bitmap and/or the literals Huffman-coded), 9 Huffman, 10 SlowFastA and 11 SlowFastB (LZSS); 13 declined per entry, and 20 is an encoder for 11 rather than a method of its own✧✧ | 2 fixtures, 5 forks, adjudicated by the archives' OWN self-extractors on an emulated Mac, + 11 single-file specimens written by Alysis's own control panel (methods 1 and 6) and graded against their inputs, + every method 1..9 through Alysis's own Add-In Modules under qemu-m68k (`tools/sdmodule/`) | 72–84 KB✧✧ | full |
| StuffIt SpaceSaver (`SPSV`) | extract | 0 stored, 4 "Alg 4" — an LZSS whose window starts loaded with a preset dictionary that ships inside SpaceSaver; 1, 2 and 3 declined per entry✦✦ | no oracle and no specimen — but **Aladdin's own encoder agrees with this decoder field for field** (`CMod 20`, 2026-08-23), which is what grades it, plus a synthetic round-trip and unit tests✦✦ | 4 KB stored, **36 KB** for what SpaceSaver writes (measured on a Mac Plus); 68 KB is the ceiling the width byte allows. The dictionary is 9.7 KB of static data, not heap | full |
| LZH / LHA (.lzh, .lha) | extract | -lh0- store, -lh1- (LHarc's adaptive Huffman, shared with StuffIt method 5), **-lh2- (both codes adaptive, the position tree growing with the output)**, **-lh3- (static, rebuilt per block)**, -lh4-/-lh5-/-lh6-/-lh7- (static Huffman over a 4/8/32/64 KB window), -lhd- directories, LArc's -lz4-/-lz5-/-lzs-; header levels 0, 1, 2 and 3; **MacLHA's MacBinary payload unwrapped into two forks**; every method the format has except PMarc✵ | 8 fixtures (1 real Amiga archive + 7 of lhasa's) + **182 archives from fourteen writers**, each graded against `unar` and against lhasa, + 12 sets written by LHa 1.14i itself, + 15 -lh2- and 6 -lh3- entries generated for the purpose✵ | 4–74 KB✵ | full |
| AppleLink package (.pkg) | detect only | — | no specimen anywhere: the probe is Aladdin's own recogniser, at 0 false positives across 928 fixtures (*AppleLink packages*, below) | — | — |
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

Peak heap 8 KB–392 KB on Linux and the same on a Mac Plus at 4 MB and 1 MB
(`unclassic t --stats`; FORMATS.md, "DiskDoubler and Now Compress on the
Mac"): the 8 KB end is method 3, which is two buffers and no state at all;
method 7 is 10 KB, whose whole state is a 2 KB window; method 1 is 17 KB on
an 11 KB fork, sized from the input like every other `unc_lzw` caller; DDn is
~100 KB, its window sized from the entry up to the format's 64 KB plus a
literal/offset buffer sized from each block's own header; and the 392 KB end
is methods 2 and 5, which pay 1,536 B per distinct context byte (below).
**Measured on the Mac, 2026-08-22:** `synth-dd-m5.dd` touches all 256
contexts and peaks at **405,520 B (396 KB)** on a 68000 — and passes at 4 MB,
at the **1 MB floor**, and on System 7, which is the largest single
allocation this engine has ever asked a Mac Plus for. Methods 3 and 4 are
8,208 B and 9,508 B there, the cheapest in the format. The **400 KB budget**
column is about the corpus and stays true of it: that one fork is the only
thing in this format that would not fit that budget.

**Methods 1 and 7 joined them on 2026-08-20**, when running DiskDoubler
itself showed that both are reachable after all (BLOCKERS.md, *Withdrawn
claims*):

| method | what writes it | specimens | how graded |
|---|---|---|---|
| 1, Unix compress | DiskDoubler 3.7, "Method A (fastest)" | `subject-A.dd`, both forks; one more on the 3.1.2 disk | the bytes that went IN, on the emulated Mac; `unar` agrees |
| 7, Stac LZS | the Sigma Designs card DiskDoubler 3.x drove | the two THINK C libraries on the 3.7 disk, 2,226 B each, **and 22 forks on the 3.1.2 disk, up to 97,906 B in 8 chunks** | the fork's own XOR checksum; `unar` agrees byte for byte |
| 2, splay Huffman | DiskDoubler 1.x-3.1.x | **one**: `XCMD.h` on the 3.1.2 disk, 564 → 386 B (2026-08-21) | the fork's own 16-bit sum, and the output is legible 1990 Salient C |
| 3, RLE90 | DiskDoubler 1.x-2.x | **none** | Salient's 1991 expander, on a fork this project encoded (below) |
| 4, StuffIt Huffman | DiskDoubler 1.x-2.x | **none** | the same |
| 5, splay Huffman, tree count in the stream | DiskDoubler 1.x-2.x | **none** | the same, and DiskDoubler 4.1.1 agrees |

**Methods 3, 4 and 5 joined on 2026-08-21, graded without a specimen.**
`tools/vmac/ddencode.py` writes a fork with our own encoder and hands it to
**Salient's own 1991 DiskDoubler** under Mini vMac; all three come back
byte-exact, and 4.1.1 confirms method 5 a second time. What that grades and
what it does not: DECISIONS.md (methods 3, 4 and 5). Three things it
measured that neither reference states —

- **the 0x5a XOR applies to methods 1, 2 and 5 but NOT to 3 and 4**, on
  headers carrying `info1 = 0x2a`, which is the value every real file of that
  era carries. macutils agrees by construction; **XADMaster's case 4 does
  not**, and is marked untested by its author;
- **DiskDoubler 4.1.1 has dropped methods 3 and 4** — it answers *Unknown
  compression method. The file was probably created by a more recent version
  of DiskDoubler* on a 1990 format;
- **only a tree-count byte of 0 (meaning 256) is confirmed for method 5.**
  Both expanders reject a count of 16 with *Checksum failed* (OPEN_ITEMS.md).

**Method 2 joined on 2026-08-21**, when Salient's own 3.1.2 distribution
floppy turned up on WinWorld — older than any DiskDoubler this project had
(BLOCKERS.md). It is an order-1 adaptive code: 256 splay trees, the one in
use chosen by the byte just produced, each starting as the complete binary
tree over 256 leaves and rotating the leaf it just emitted toward the root.
The 0x5a XOR over decoded bytes is method 1's, under the same `info1`/`info2`
condition; the checksum needs no adjustment because the stream carries no
header of its own. DECISIONS.md 2026-08-21 (the Salient disk).

**Methods 2 and 5 peak on the number of distinct context bytes, not a
constant.** A tree is 1,536 B and is built only when its context first
occurs: the method 2 specimen — 60 contexts in 564 bytes — measures
**101,888 B**, and a synthetic method 5 fork touching all 256 measures
**401,408 B** (`unclassic t --stats`), which still fits the 597,036 B a 1 MB
Mac Plus leaves the engine (*Resident memory, stack and launch*, `Budget`). Methods 3 and 4 are the cheapest in the format at
**8,192 B** and **9,476 B**, being two buffers and, for 4, one Huffman
table.

Method 1 is `unc_lzw` behind three bytes of its own, with an 0x5a XOR over the
DECODED bytes and the header bytes — not over the code stream — and a sum
adjusted by those three bytes. Method 7 is a 2 KB-window LZSS whose bit stream
AND output are stored complemented, with match lengths unbounded by the
window. Both: DECISIONS.md 2026-08-20.

No DiskDoubler method is declined any more. What is still missing for 3, 4
and 5 is a real specimen — every fork of them this project has seen, it
wrote itself (OPEN_ITEMS.md). **11 forks across 2 fixtures were adjudicated
by neither oracle** — `unar` failed on them and `macunpack` has no DDn at all
— and **all 33 forks of both archives are now byte-exact against two other
implementations.** DiskDoubler's own expander agrees under System 7 outside
the resource header's OS-stamped bytes 16..127
(`tools/vmac/diskdoubler.py --adjudicate`, 2026-08-21), and `unar` agrees
everywhere including that window once handed one fork at a time with the
declared compressed length one byte larger — the off-by-one its DDn reads
past (`tools/run_ddforks.py`, 2026-08-22). Every hash is in the manifests and
checked by `ci.sh`; `oracle-unadjudicated` fell from 24 forks across 12
fixtures to **16 across 10**, and neither DiskDoubler fixture is on that list
any more. DECISIONS.md 2026-08-15, 2026-08-21, 2026-08-22.

**That masking window has independent evidence since 2026-08-21.**
`DiskTester™` 3.7.7 ships DiskDoubler-compressed on the Norton DiskDoubler
Pro 1.1 floppy and UNCOMPRESSED in the Fifth Generation 4.0 StuffIt archive —
same build, two publishers. Our decode of the compressed copy equals the
other over all 36,104 bytes except 46, every one of them inside 16..127
(`tools/vmac/ndd.py --grade`). Until then the window was masked on the
argument that the Mac rewrites it; this is a fork graded against a copy no
DiskDoubler ever touched.

**A `DDA2` entry of type `0x1000` carries no `0xABCD0054` header of its own.**
DiskDoubler Pro writes it **exactly when the data fork is stored AND the file
has no resource fork** — measured across all four cells of compressible x
forked in one archive on 2026-08-21 (`tools/vmac/ndd.py --stored`;
DECISIONS.md, the Symantec release). Size is not a factor: 40 B and 20,000 B
both take the form. A file with a resource fork gets a full header even when
its data fork is stored, which is 45 of the records in the CC0 corpus against
30 of the headerless kind. Consequences: **no `0x1000` record can carry a
resource fork**, so `+87` never describes one; `+86` is the data fork's
checksum (corrupting one payload byte trips it); and `+54` and `+58` are the
creation and modification dates, measured 2026-08-21 by archiving subjects
stamped 1990 and 1995, not assigned.

Read since 2026-08-21; before that, five of the nine DiskDoubler Pro
4.1.1 archives in `ssokolow/diskdoubler-test-files` stopped at their third
entry, and **`unar` 1.10.8 still stops there** (MEASURED): `lsar` fails on
all five with *Archive parsing failed! (Data is corrupted.)*, and reads all
four DiskDoubler 3.7.7 archives fine.

That corpus is CC0 and publishes the **originals** beside the archives, so it
grades against source bytes rather than against another decoder. Extracted
here and compared (`tools/run_ddtf.py`):

| what | count | result |
|---|---|---|
| single-file `0xABCD0054` containers (7 files × 9 methods) | 63 | byte-exact |
| `DDAR` / `DDA2` archives (methods 1, 6, 8, 9, 10 and stored) | 9 | byte-exact |
| self-extractors, plain and prompt-for-folder, and the same BinHexed | 20 | byte-exact |
| **forks compared against the published originals, in all** | **456** | **exact** |

The TIFF in each set has no published original — it was made on the Mac — and
comes out identical from all nine independent compressions, forks included.
None of these is in `fixtures/` (OPEN_ITEMS.md); what `ci.sh` covers instead
is in TESTING.md.

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

✧✧ **Alysis SuperDisk!, in scope since 2026-08-20**, where every status file
here used to call it the one format the corpus holds that nothing can name.
An archive is eight bytes nobody reads, an optional chain of 68k decompressor
modules, then a record stream: `0x29` opens a folder, `0x2a` closes one,
`0x28` is a file and `0x27` ends the archive. A file's forks follow its own
record inline — **data fork first**, then resource — each a chain of blocks of
at most 32 KB of output, each block's length counting itself, with bit 15
marking a stored block.

| method | name | shape |
|---|---|---|
| 1 | " Faster" | context predictor, bitmap and literals stored |
| 2 | " Tighter" | bitmap Huffman-coded, literals stored |
| 3 | — | bitmap stored, literals Huffman-coded |
| 4 | — | both Huffman-coded |
| 5-8 | — | 1-4 again, over a 16-bit context instead of a 13-bit one |
| 9 | "30% Solution" | Huffman alone, its region starting at the block's LENGTH word✦ |
| 10 | "SlowFastA" | LZSS: a 32-bit control word per 32 items, matches of `nibble + 2` bytes at `out - offset + 1`, 12-bit offsets with a 16-bit escape✧ |
| 11 | "SlowFastB" | LZSS, lengths 2-282, offsets 1-49120 |
| 13 | "SlowFastC" | **declined per entry** — its module only COMPRESSES✧✧✧ |
| 20 | "Tennessee" | **not a block method**: its module is an ENCODER, and what it writes declares method 11✧✧✧ |

✦ **And the method is the low BYTE of that word, not the word.** Method 9
keeps its Huffman `startbits` in the high byte, so a 16-bit read of a real
method 9 block gives 0x0809 and this engine refused it as unsupported until
2026-08-25 (BLOCKERS.md). Both halves come from the reference dispatching on
`a2@(3)` — CODE 2 @0x6ba — and calling the Huffman routine with `a2`
unchanged for method 9 (@0x712) where the 1..4 family advances past four
bytes first (@0x812).

**Every method 1..9 now has a second implementation, and it runs on Linux.**
Disk Expander 1.2's `Cmpr` resources are one Add-In Module per codec — 68k
with no Toolbox in them — and `tools/sdmodule/` lifts them out of the corpus
fixture and calls them under `qemu-m68k`. Results, in `./ci.sh`:

| what | through both readers |
|---|---|
| corpus blocks (method 11) | 4, byte-exact |
| specimens Alysis's own compressor wrote (methods 1 and 6) | 18, byte-exact |
| synthetic blocks, methods 1-9 | byte-exact, except the refill boundary below |
| method 10, against its module and the bytes behind it | equal three ways |
| method 11 blocks written by Alysis's own encoder (module 20) | 5, byte-exact |

The one disagreement is where a Huffman region's neighbour begins when the
coded flag bitmap ends **exactly** on a 32-bit refill: this engine follows the
1991 self-extractor (cursor + 2) and the 1992 module has already fetched the
next long (cursor + 6). Measured at ulen 64 and absent at ulen 300.
**Only the harness's own encoder reaches it** — its flat 8-bit code ties the
bit length to the byte count, where a real block's flags are coded one bit
each and the length is data-dependent. Four subjects were compressed by
Alysis's own 1991 panel on purpose to look for it (`sdcompress.py
--boundary`, 2026-08-25) and all four came back byte-exact under both
readers, as do all 18. Which reading is right where they differ is **open**
and costs nothing so far (OPEN_ITEMS.md).

**The single-file container joined on 2026-08-22.** SuperDisk! writes two
shapes and this engine now reads both: the record-stream archive, and what
its control panel's "Make File" produces — a 30-byte header, the name as a
Pascal string padded to an even offset, then the same block chains, data fork
first. It stands to the archive as DiskDoubler's `0xABCD0054` does to `DDAR`,
and the payload needed no new codec. Derived from five specimens written by
Alysis's own 1991 control panel under Mini vMac, chosen to separate the
fields — one with a resource fork, one stamped 1990/1995, one with a
20-character name, one over 32 KB — and **all five decode byte-exact against
the bytes that went in**, dates, type, creator and Finder flags included
(`tools/vmac/sdcompress.py --specimens`, then `--verify`; DECISIONS.md
2026-08-22, later still).

✧ **Method 10 landed 2026-08-25, and nothing in reach writes one.** It was
transcribed from its own module — `Cmpr` 21 of Disk Expander 1.2, inside a
corpus fixture — and graded by running that module under `qemu-m68k` over the
same streams: 20 cases equal three ways (the bytes a test encoder started
from, this engine's decode, and Alysis's). Two things only the module could
have said: the match length is `nibble + 2`, not `2*(nibble+1)` — the DBF's
target is the second MOVEB — and the wide-offset escape shifts its marker
nibble OUT (`ASL.W #8`), so the far form is sixteen bits, not twenty. The
first reading of both agreed with this engine's own test encoder and with
nothing else.

✧✧✧ **Measured 2026-08-25, and it dissolved half of an open item.** Module
20 answers `badCommandError` to the decompress command and compresses on
command 2; every block it writes declares **method 11**, and this engine
decodes all of them back to the bytes that went in (five inputs, from 4 KB of
zeros to 30 KB of text; it declines random data with
`inadequateCompressionError`, which is the published code for it). So there
is no method 20 bitstream to implement — and a block that did carry 20 could
not be read by Alysis's own expander either, whose dispatcher would hand it to
this same module and be refused. What it gives instead is a **compressor for
method 11**, which nothing else here has: `tools/sdmodule/` now grades the
SlowFastB decoder against blocks Alysis's own encoder wrote, where before it
had the corpus's four.

Module 13 is the same shape — command 2 only, `_Debugger` on anything else —
and it writes its own eight-byte header (`length+8`, the word 13, then a
32-bit uncompressed length) which is not the six-byte block header this
container uses. So a method 13 block, if one exists, is not shaped like the
ones here. It runs now: it wanted a 64 KB working buffer (it compares
`workingBufferSize` against 65536 and DEBUGGERs below it) and one Toolbox
trap, `_BlockMove`, which the runner answers.

The corpus's two archives use 7 and 11. The method table is not guesswork:
decoding method 11 yields Disk Expander 1.2's own resource fork, whose `Cmpr`
resources are one module per method, each stating its number and its name
(DECISIONS.md, "SuperDisk!, read out of SuperDisk!"). 13 and 20 are declined
because no fixture uses them and neither module can be run end to end here:
13's traps on an A-line instruction under the runner, and 20's is a
COMPRESSOR — it answers `badCommandError` to the decompress command, and no
expander for it exists in any Alysis product in reach. Their modules are in
hand and named by `tools/sdmodule/run_sdmodule.py --list`.

**There is no oracle but the archives themselves.** `unar` and `macunpack`
both stop at the BinHex envelope, so `fixtures/manifests/` describes the
payload and says nothing about its contents. Both archives are
self-extracting applications, so `tools/vmac/superdisk.py --adjudicate` runs
each one under System 7 on an emulated Mac Plus and reads back what it wrote:
**5 forks across the 2 archives, every one identical** (2026-08-20; resource
forks with bytes 16..127 masked, the `vmac_check.py` convention).
`tools/run_superdisk.py` replays that verdict offline by content and adds 116
corrupted variants, which nothing else covers — `t` does not unwrap envelopes,
so the corpus-driven robustness and fuzz suites only ever reach the BinHex
layer.

Peak heap **74,220 B** for `SD! Utilities.x` and **85,943 B** for
`Disk Expander .X` (`unclassic t --stats`); both extract fully under a 400 KB
budget. Neither peak is a ceiling anybody declared: the 64 KB step is the wide
context table, allocated only for methods 5-8, and SlowFastB's window is
allocated only when a method-11 block turns up.

**`Disk Expander .X` was 117,294 B until 2026-08-24**, when that window
stopped being a flat 98,304 B and started being sized from the fork. It is
history carried across blocks plus the block in hand, so one block's `ulen`
does not bound it — but the fork does, because the history is the bytes
produced so far and is capped at `SD_WINDOW`. The visible effect is not the
31 KB: it is that `Read Me` now extracts under a 50,000 B budget where it
used to be refused, which is also why `run_superdisk.py`'s budget probe had
to be re-aimed from 50,000 to 20,000 (TESTING.md is not the place — the
docstring in that file says it).

✦✦ **StuffIt SpaceSaver, in scope since 2026-08-22**, where every status
file here used to say nobody has published how it is laid out. The header, the
fork records, the module table and what each method is: *StuffIt SpaceSaver*,
below. **It is the only format here graded by nothing but itself**: no oracle,
no fixture, and — so far — no specimen, because SpaceSaver has not been made
to compress anything on this machine (OPEN_ITEMS.md). What stands in for one
is an encoder written from the same disassembly as the decoder, which is a
consistency check and not an oracle (TESTING.md).

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

## StuffIt SpaceSaver

**In scope since 2026-08-22**, read out of Aladdin's own engine rather than
from a specimen — there is no specimen of any kind, and the layout came
anyway. `tools/vmac/spacesaver.py --layout` prints every figure below out
of the installed software's own bytes, with nine witnesses that fail if a
different build is ever put in front of it; DECISIONS.md (2026-08-22, the
layout / the codecs) is how it was read.

The writer is `SSEn 1` in `StuffIt Engine™`, not the control panel: the
panel's `ACMP 1` only reads eight bytes and compares the two magics. A
compressed file carries type `SPSV`, creator `SIT!`, an EMPTY resource fork,
and a data fork whose length is rounded up to a multiple of 256 — which is the
screen the system extension applies before it opens anything.

| off | size | field |
|---|---|---|
| +0 | 4 | `'SIT!'` |
| +4 | 4 | `'DFD3'` |
| +8 | 4 | version, 3; 1 and 2 are converted in place on read |
| +12 | 4 | header length, 84 |
| +16 | 4 | flags; `0x00000041` in everything this engine writes |
| +20 | 16 | fork record — data fork |
| +36 | 16 | fork record — resource fork |
| +52 | 4 | the file's `fdType` before compression |
| +56 | 4 | its `fdCreator` |
| +60 | 2 | its `fdFlags`; six bits are cleared on compress and restored from here |
| +62 | 2 | zero |
| +64 | 20 | reserved, zeroed on every write |

| off | size | fork record field |
|---|---|---|
| +0 | 4 | compressed length |
| +4 | 4 | original length; 0 = fork absent, and the two bytes below are 0 |
| +8 | 4 | offset of the stream from the start of the data fork |
| +12 | 1 | parameter set — indexes the engine's `PrAm` resources; always 0 here |
| +13 | 1 | compressor index, bit 7 = the PowerPC module |
| +14 | 2 | zero |

**The records are fixed and the streams are not.** Record 1 is always the data
fork and record 2 the resource fork, but the LARGER fork's stream is written
first, at offset 84, and the other follows it — read each at its own offset.

| idx | modules (`CMod`) | runs on | status |
|---|---|---|---|
| 0 | 1 "Default Compressor" | any | stored, implemented |
| 1 | 3 "Original Fast Compressor" | any | declined per entry |
| 2 | 4 "Original Slow Compressor" | any | declined per entry |
| 3 | 10 "Alg 3", 11 decompress-only, 15 PowerPC | 68030 and up / any / PowerPC | declined per entry |
| 4 | 20 "Alg 4", 21 decompress-only | 68000-68020 / any | implemented |

A file whose compressor byte is none of these is still recognised and named —
the entry fails, the file does not. The index is the module's own byte at
+0x20, not its resource id; the low byte there is a revision and the higher
one wins; +0x24 is a CPU mask, bit 31 − Gestalt `cput`. **The default is the CPU's**: index 4 below a 68030,
index 3 from a 68030 up, and the decompress-only modules accept every CPU so
any Mac can read any file. That is also why 1, 2 and 3 are declined — no
machine reachable here writes them, so an implementation could not be graded,
the bargain LZH's `-lh2-`/`-lh3-` and DiskDoubler's declined methods
already make.

**Method 4 is an LZSS with a preset dictionary.** Three bytes of stream header
(block count as a 16-bit little-endian value, then the window's width in
bits), then that many blocks of a 6-byte header — compressed length including
those six bytes but not the three above them, then uncompressed length, both
24-bit little-endian — and a bit stream read LSB-first: `1` and eight bits is
a literal, `0` and five bits of length plus *wbits* of distance is a copy of
4 + length bytes. The window slides across the whole fork.

**Every one of those fields is confirmed by Aladdin's ENCODER as well as its
decoder** — `CMod 20`'s compressor, a different routine in a different module
(DECISIONS.md 2026-08-23, the encoder agrees). Two figures come from it: the
encoder always writes **15** as the width, so a real file's window is 32,768
bytes, and a block covers **65,536 bytes of output** (`ceil(ulen / 65536)` of
them). The decoder reads the width byte rather than assuming either.

**It starts loaded with 9,679 bytes of Aladdin's `PrAm` -4048**, placed
immediately before the first output byte, so the first matches in every fork
read that table rather than anything in the file. **Those bytes ship here**,
in `src/ss_dict.h` — they are Aladdin's, `NOTICE` says so, and DECISIONS.md
2026-08-23 records whose decision it was and why. Without exactly them a file
decodes to output of the right length that is silently wrong, so there is no
approximating it and no generating an equivalent.

The record's byte at +12 chooses: 0 is -4048 and 1 is `PrAm` -4047, four
spaces, which nothing this engine writes selects. Both are built in; anything
else is refused per entry. `unclassic --preset FILE` overrides the choice, for
a table this build does not carry. The resource is byte-identical in the
control panel and in `StuffIt Engine™`, so either file will do as a source for
`tools/gen_ss_dict.py`.

**Both methods run on a 68000**, which is the part no Linux test can show.
`tools/run_spacesaver.py --emit` writes three files and `tools/vmac/run.py
--expect` replays them on an emulated Mac Plus under System 6.0.8: a stored
one (**1,040 B data + 512 B resource, peak 4,112 B**), a method 4 one at the
window width SpaceSaver writes (**14,524 B out, peak 36,896 B** — the 32 KB
window plus the 4 KB input buffer), and one whose stream reaches into the
dictionary, which the application expands with the built-in table
(**7,000 B out, peak 36,896 B**). All three agree with the Linux CLI byte for
byte, **at 4 MB and at the 1 MB floor target alike** (re-measured 2026-08-23,
after the width was corrected from the ceiling and again after the dictionary
was built in).

**So a lone floppy is enough.** A SpaceSaver file that has travelled without
the machine that made it needs nothing else — not a copy of SpaceSaver, not a
flag — on Linux or on the Macintosh application, which cannot be handed a
dictionary at all. That is the case this format turns up in: the file looks
normal, its own application reads 84 bytes of header where the document
should be, and nothing else on the disk says why.

## LZH / LHA

✵ **In scope since 2026-08-23** (M28), and detect-only until then
because nothing here could grade a decoder: the
Macintosh corpus contains no `.lzh` at all (measured; DECISIONS.md
2026-08-14). What changed is the specimens. `reference/lhasa` ships
**182 archives written by fourteen different LHA implementations** —
MacLHA 2.24, LHa for Amiga/OS-2/OS-9/OSK/X68000, LHarc 1.13, LArc 3.33,
LHMelt, LHArk, UNLHA32 — and `reference/lha` is LHa for UNIX 1.14i,
the original, which this project can compile and run as an ENCODER.

**Three graders, and they are not interchangeable** (TESTING.md):
`unar` is XADMaster, which this decoder is transcribed from, so
agreement with it establishes only that the copy was faithful; lhasa is
an independent reading; LHa 1.14i writes archives whose plain text is
already known. 137 archives are graded against `unar`, 142 against
lhasa, 12 generated sets against their own input.

**What the independent graders were worth**, in the first afternoon:

| what | `unar` | lhasa | settled by |
|---|---|---|---|
| the 18 bytes of an -lz5- window the preload does not cover | zeros | (rotated: zeros) | LArc 3.33's own `initial.lzs`, an archive whose CONTENTS are the initial window — zeros. LHa 1.14i's `decode()` space-fills a dictionary its `decode_start_lz5` never touches |
| an -lzs- window before anything is written | zeros | spaces | the stored CRC: **spaces**. Zero-filling fails `lzs.lzs` and passes `long.lzs`, which is what a difference that only shows on some files looks like |
| LHa for OS-9/68k's level 2 header, two bytes short | fails all three of its archives | compensates by OS byte | lhasa, followed here |
| a 1.2 MB -lh7- file | "Attempted to read more data than was available" | decodes | lhasa, byte-identical to this engine |
| LHArk 0.4d's "-lh7-", which is a different algorithm | fails | decodes it as `-lk7-` | refused per entry here: LHArk marks itself with a space as the OS byte |
| `-lzs-` at all | **cannot open one** — its recogniser omits `-lzs-` while its own parser has a decoder for it | reads it | this probe accepts `-lzs-`; the divergence from the oracle is deliberate and measured |

**MacLHA writes a MacBinary stream and compresses that**, so a Macintosh
entry's decoded bytes are a 128-byte header, the data fork padded to
128, then the resource fork — and the entry's name, type, creator and
dates are the Mac header's, not the LZH header's. The unwrap happens
for OS byte `'m'` and no other: a level 0 header has no OS byte at all,
and `unar` reads MacLHA's own level 0 archives as one 18,304-byte file
where the level 1 copy of the same file is 18,092 plus metadata. Both
readings are reproduced here. lhasa infers the same trigger from the
same byte and then throws the resource fork away; this engine keeps it.

**And MacLHA 2.00 needed one more rule than either reference has.**
None of the sixteen MacLHA archives in lhasa's collection holds a file
with a resource fork, so the split had never met a byte MacLHA wrote —
until `tools/vmac/maclha.py` ran **MacLHA 2.00 itself** under Mini vMac
and archived a two-fork file. Its MacBinary header has **both dates
zero**, which XADMaster's MacBinary-I heuristic refuses (it requires
them non-zero) and lhasa refuses too (it wants the modification date to
match the LZH header's), so `unar` and lhasa both hand back the whole
2,304-byte stream with the resource fork buried in it. This engine
accepts it on arithmetic instead: the name in the Mac header must be
the entry's, and the two fork lengths padded to 128 plus the header must
come to exactly the uncompressed size. Both forks then come back
byte-exact — 1,760 B and 333 B, graded against the bytes that went into
the emulator (`tools/run_lzh.py`, which skips the check where no
specimen has been made). The rule fires on nothing else: all 182
archives and all 8 fixtures are unchanged.

**Dates are not converted.** Levels 0 and 1 carry an MS-DOS timestamp
and levels 2 and 3 a Unix one; neither is a Mac date, and this engine
does what zip's reader does and reports none. A MacBinary payload's
dates ARE used, because those are already Mac dates.

**Symbolic links are reported, not created.** LHA stores one as a single
entry named `link|target`; classic Mac OS has no symbolic links, so the
entry is named and refused per entry — the answer tar's reader gives a
link.

**Peak heap 4–74 KB**, measured with `unclassic t --stats`: 4 KB for a
stored entry, 8 KB for LArc, 16–18 KB for -lh5- and -lh1-, 41 KB for
-lh6-, and **74,128 B** for a -lh7- entry big enough to need the whole
64 KB window (`lh7_long.lzh`, 1.2 MB). The window is sized from the
entry rather than from the method, the way StuffIt method 13's is, so
the -lh7- fixtures in the corpus cost 41 KB rather than 74.

**`-lh2-` reads since 2026-08-25, and the encoder for it is this
project's.** Both codes are adaptive there — the literal/length tree
`-lh1-` also uses, plus a position tree that GROWS with the output, one
leaf per 64 bytes, so an offset only becomes expressible once enough has
been produced. Transcribed from `XADLZHOldHandles.m`
(`LHAdecode_start_dyn`, `_c_dyn`, `_p_dyn` and the tree they share),
cross-read against LHa's own `dhuf.c`, in `src/unc_lzdyn.c`.

Nothing writes one, which is what kept it out: lhasa has no decoder,
the LHa in `reference/` carries the coder without selecting it, and even
the maintained fork — which decodes it properly — cannot write one. So
`tools/build_lha_lh2.sh` teaches that fork to, and the archives it makes
are verified by its own decoder before this engine sees them. **15
`-lh2-` entries across three header levels in `ci.sh`**, byte-exact,
with the run failing if fewer than three entries of an archive really
used the method (TESTING.md).

**`-lh3-` reads since 2026-08-25 too**, and it needed no patch to LHa:
its code is STATIC, rebuilt per block, so `tools/run_lzh.py` writes the
streams itself and LHa's own decoder vets each archive before this engine
sees one. A block is a 16-bit symbol count, a literal/length tree sent as
one 4-bit length per symbol, then either a position tree in the same shape
or the fixed one the format keeps; two escapes carry a block that holds a
single symbol and a position tree sent explicitly, and both are exercised.
Six entries per run.

PMarc (`-pm0-`/`-pm1-`/`-pm2-`), `-lhx-` and the self-extracting archives
remain out of scope (OPEN_ITEMS.md, part 1).

**On the Mac** (2026-08-23), five `.lzh` fixtures byte-exact on System
6.0.8 at 4 MB, at the **1 MB floor** and on System 7.0.1: peak heap
4,112 B for the smallest, 41,364 B for the -lh7- one, 16,788 B for the
five-entry Amiga archive — the Linux figures plus the shell's constant
32 B, at every memory size.

## btoa, the other ASCII armour

**In scope since 2026-08-23**, and it came out of a menu: StuffIt Deluxe
3.5.1's Translate menu is built from the files in
`System Folder:Extensions:Aladdin:Translators`, and there are fourteen
of them. Thirteen are formats this project already reads —
`AppleSingle`, `BinHex4`, `CompactPro`, `DeArc` (ARC), `MacBinary`,
`Text`, `UUCode`, `UnPack` (PackIt: its own `STR#` 129 holds `.pit`),
`UnZip`, `Unix Compress`, `tar`, and Segmenting and PKG below. The
fourteenth was `btoa/atob`, and nothing here had heard of it.

Paul Rutter's btoa is uuencode's rival from the Unix side: four bytes
become five printable characters in base 85, which is 25% overhead
against uuencode's 33%. A Mac met it the same way it met uuencode —
over the wire from a Unix host — and Aladdin shipped a translator for
it, which is what puts it inside this project's brief ("everything
StuffIt Expander 4.0.2 expands", DECISIONS.md 2026-08-15).

◆ **Two framings, and they differ in more than the header.** `xbtoa5`
lines carry a checksum character of their own and the three
whole-stream checksums cover the ENCODED characters; the older `xbtoa
Begin` has neither the per-line check nor the same coverage — its
checksums are over the DECODED bytes. Both are read. `z` stands for
four zero bytes and, in version 5 only, `y` for four spaces. The
declared length is what ends the file: the encoder always writes whole
five-character groups, so `(len - 1) & 3` says how many bytes of the
last group are real.

**CR, LF and CRLF all end a line.** The Unix encoder writes LF, but the
machine this decoder is for writes CR and nothing else, so a file that
reached a Mac and was saved there comes back CR-terminated; for CRLF the
LF that follows reads as a blank line, which the format allows anywhere.
Skipping CR instead — which is what the code did until 2026-08-23 — turns
such a file into a single line that no header matches (*BLOCKERS.md*,
withdrawn claims).

**No corpus file, and no second reader.** `xbtoa` appears in none of
the 903 fixtures, `unar` does not recognise the format and macutils
never had it — so the grading is the original implementation itself.
`tools/fetch_references.sh` fetches btoa 5.2.1 (Paul Rutter, Joe Orost
and Stefan Parmark, 1996, from `archive.debian.org`), `src/fmt_btoa.c`
is transcribed from its `atob.c`, and `tools/run_btoa.py` compiles the
same source as an ENCODER and requires our decoder to reproduce what it
writes — eight subjects across both framings, plus a mail-wrapped one,
a flipped character, a truncated archive and prose that merely contains
the word.

One thing it inherits from the Unix side: the checksum called `R` is a
32-bit rotate that the reference computes in a `long`, so a 64-bit host
prints sixteen hex digits where a Mac prints eight. The low 32 bits are
the same either way — the rotate tests bit 31 in both — and that is
what is compared.

## Encryption

**In scope since 2026-08-23.** Seven ciphers across five formats, and one
thing to know before the table: **nothing in the corpus is encrypted.**
Measured, not assumed — `lsar -j` over all 903 fixtures reports
`XADIsEncrypted` 0 for every entry — so every archive that exercises
any of this is generated by `tools/synth_crypt.py`,
`tools/synth_cpt.py`, `zip -P` or `arc g<password>`, and graded by
`unar -p` where a second implementation exists. TESTING.md, *the
decryption suite*.

| format | cipher | key from the password | verified before decoding? | graded by |
|---|---|---|---|---|
| StuffIt classic | an eight-byte feedback XOR, keyed through **StuffItDES** (a DES with its own key schedule and no initial permutation) | iterated DES over the password — **ceil(len/8) folds, measured** (below) — then the archive's `'MKey'` resource, then sixteen bytes stored at the end of each fork | **yes** — the 'MKey' block checks against itself | **StuffIt Deluxe 3.5.1 itself**, on three archives it wrote; `unar -p` on the generated ones |
| StuffIt 5 | **RC4** | MD5(password) cut to five bytes, then the fork's own five | **yes** — MD5 of that key against a hash in the archive header | `unar -p` |
| PackIt `PMa5` | XOR, key applied **modulo seven** over eight bytes | DES's PC-1 permutation of the first eight password bytes | in effect — the entry header is inside the ciphertext and carries a CRC | `unar -p` |
| PackIt `PMa6` | **DES**, ECB; the operation that DECODES is DES's decrypt | the first eight password bytes | the same | `unar -p` |
| zip | **PKWARE's** three CRC-32-driven keys | the password bytes, folded in | **yes** — a check byte in the twelve-byte header | Info-ZIP wrote the fixture; `unar -p` reads it |
| zip, WinZip **AES** | **AES** in counter mode, 128/192/256, with HMAC-SHA1 over the ciphertext | PBKDF2-HMAC-SHA1, 1000 rounds over a salt in the entry | **yes** — a two-byte verifier the derivation also produces | 7-Zip wrote the fixtures and verifies them; `unar` 1.10.8 cannot open one at all |
| ARC | a repeating XOR of the password over the compressed bytes | the password itself, and `arc` 5.21q upper-cases it first (measured) | **no** — the format has no encryption flag at all | Debian's `arc` wrote the fixture; `unar -p` reads it |
| Compact Pro | a **64-bit CRC** register; keystream is its second byte, stepped on each plaintext byte. The stream opens with **eight bytes that are decrypted and discarded** — a salt, so two entries with one password differ | nine bytes: a length capped at eight, and the password ADDED into eight accumulators in rotation | **no** — its own message says so | **Compact Pro itself**, both directions. See below |

**The formats NOT in that table have no encryption to read**, and that
is measured rather than assumed: a string sweep over the distribution
images this project already keeps — DiskDoubler 3.1.2, 3.7 and Norton
DiskDoubler Pro, Now Utilities 5.0.1, the Alysis control panel and
StuffIt Deluxe's engine — finds no password feature in any of
DiskDoubler, Now Compress, SuperDisk! or SpaceSaver. (The hits on two
of those volumes are System 7's own File Sharing and Chooser.) BinHex,
MacBinary, AppleSingle/Double, uuencode, tar, gzip and `.Z` have
nowhere to put one.

Three properties are worth stating because a user meets them:

- **An encrypted StuffIt classic archive that lost its resource fork
  cannot be decrypted by anything.** `'MKey'` 0 is half the key
  material and it is not in the stream. The entry reports "encrypted"
  rather than asking for a password it could not use.
- **A wrong password is reported, never decoded to rubbish.** Where the
  format verifies, that is immediate; where it does not (ARC, Compact
  Pro), the entry is decoded once writing nothing to find the key and
  again to write it, so a wrong key never reaches the output.
- **A WinZip AES entry is graded by its authentication code, not its
  CRC.** AE-2 stores no CRC at all, so the ten bytes of HMAC-SHA1 after
  the data are the only check — and they are checked. AE-1's CRC is
  checked as well. The 1000-round key derivation is the slow part on a
  68000: seconds, once per entry, before any output appears.
- **An encrypted entry does not stop the walk.** The entries around it
  come out; PackIt, whose encrypted entries do not say where they end,
  resyncs on the next block magic as it always did.

### StuffIt classic's archive key: ceil(len/8), and neither reference has it

The password is folded into the archive key eight bytes at a time, and
**how many times** is the one thing the two references disagree about.
It is now measured, on three archives **StuffIt Deluxe 3.5.1 wrote
itself** under Mini vMac (`tools/vmac/sitcrypt.py`):

| password | characters | folds | XADMaster master | `unar` 1.10.8 |
|---|---|---|---|---|
| `password` | 8 | **1** | 2 (the second all zeros) ✗ | 1 ✓ |
| `swordfish` | 9 | **2** | 2 ✓ | 1 ✗ |
| `abcdefghijklmnopq` | 17 | **3** | 2 ✗ | 1 ✗ |

So the rule is `ceil(len / 8)`, and **neither implementation has it**:
XADMaster's loop folds an extra all-zero block at exactly eight and
never more than two blocks however long the password is; `unar` 1.10.8
folds one, whatever the length. Each opens archives the other cannot,
which is exactly what the disagreement looked like from here while
every encrypted `.sit` in the project was one this project had
generated — a generator built from a reading agrees with that reading
at every length.

Under eight characters all three agree, which is why this went
unnoticed: it is the length a person picks when testing.

### Compact Pro's cipher: read out of the application, and graded by it

This is the one format here whose encryption no second implementation
reads — The Unarchiver's format notes say "the algorithm for this is
unknown", CptExpand's manual says it "will not extract encrypted
files", and StuffIt's own Compact Pro translator answers "the file is
password protected". So it was read out of Compact Pro 1.51's `CODE` 3
in both directions (DECISIONS.md 2026-08-23, *decryption*), and
`tools/vmac/cptcrypt.py` had the application grade that reading, the
way Salient's expander graded DiskDoubler methods 3-5.

**Both directions agree** (2026-08-23, `tools/vmac/cptcrypt.py`):

| what | result |
|---|---|
| three archives **Compact Pro encrypted** (RLE-only, data forks of 96, 100 and 103 bytes) | every byte back, through our reader |
| one **Compact Pro encrypted, LZH-compressed, two-fork** archive (196 B resource + 312 B data) | both forks byte-exact — which is also the check that the register runs across the two forks without resetting |
| an archive **we encrypted**, handed to Compact Pro | it extracted all three entries, and its own CRC-32 over both decrypted forks passed |

Encryption is gated behind **registration** — an unregistered copy
answers Extract with *"This version of Compact Pro cannot validate or
extract encrypted files"*, and the Add dialog's Encrypt checkbox sits
at a negative rect until a registration moves it into view. Macintosh
Garden publishes one for 1.51, and with it the gate opens.

The eight-byte preamble is the part no reading of the decrypt loop
alone would have caught: an encrypted entry's stream opens with eight
bytes that the reader decrypts and **discards** (`CODE` 3 @0x1f5e moves
the read cursor past them), and their length is counted in the
compressed size of the first fork that has any bytes — a 400-byte
resource fork is stored as 408. It is a salt: the register steps on
them, so the same password over the same bytes encrypts differently in
two entries. What found it was arithmetic on three archives the
application wrote — 96→104, 100→108, 103→111, a constant +8 and
therefore not a block cipher's padding.

### The archive comment, which Compact Pro calls a Note

One length byte and up to 255 MacRoman bytes at the top of the index,
belonging to the archive rather than to any entry. **Saved since
2026-08-23** rather than read, CRC'd and dropped: the CLI writes
`<archive>.comment.txt` beside the extracted items and prints it on `l`
and `t`, the Mac shell writes a `TEXT`/`ttxt` document called
`Comments` into the destination folder (DECISIONS.md 2026-08-23).

Graded twice, in both directions:

| what | result |
|---|---|
| the **six** corpus archives that carry one — `derived-DigSim_RAM_Circuit.cpt` (*"Hi there."*, 1990) and the five Compact Pro Package installers, whose notes run to 250 bytes over several CR-separated lines, one of them Shift-JIS mislabelled as MacRoman | the saved file and the printed line equal `lsar`'s `XADComment`, in `ci.sh` |
| a **two-line note typed into Compact Pro 1.51** under Mini vMac (`cptcrypt.py --make --plain --note`) | 61 bytes back byte-exact, the line break stored as a **CR** exactly where Return was pressed, `lsar` agreeing |

The CR is why the two hosts differ in one place and only one: the saved
file keeps it, and the line the CLI PRINTS turns it into a newline,
because a CR sent to a terminal overwrites the line just printed.

## AppleLink packages, and why they are named but not opened

**Named since 2026-08-23.** Every status file here used to say `.pkg` had no
reference implementation anywhere reachable and could not even be sniffed
without inventing a magic number. The first half was withdrawn on 2026-08-22
(BLOCKERS.md) — installing StuffIt Deluxe 3.5.1 to chase SpaceSaver put
`Extensions:Aladdin:Translators:PKG Expand Translator` on the disk — and this
is the second half.

**A package is TEXT.** The translator's recogniser (`Othe` 0 @0x2952) pulls
whitespace-delimited tokens out of the file — @0xf18, which skips space, tab
and CR, honours double quotes and treats backslash as an escape inside them —
and accepts the file when the first token is `Decode` and the third is `to` or
`into`, compared with `_CmpString` and so case-insensitive. `STR# 129` is the
rest of the vocabulary: `Decode`, `to`, `into`, `convert`, `noConvert`,
` Folder`, `.pkg`, and the errors *"Destination not found: "* and *"No items
matching: "*.

`unclassic sniff` implements that test and nothing more, so it is exactly as
strong as Aladdin's: a text file that happens to begin *"Decode this to that"*
is a package as far as either program can tell. Measured against the corpus —
**928 fixtures, 0 false positives**.

**It may not be an archive at all.** Three measured things point that way:
the identify path resolves its operand with `PBGetCatInfo` (`_HFSDispatch`
selector 9), the errors in `STR# 129` are *"No items matching: "* and
*"Destination not found: "*, and the translator carries recognisers for eight
other formats by extension and type. **Hypothesis:** a package is a transfer
manifest naming files that sit beside it, which would make naming it the whole
capability. DECISIONS.md 2026-08-23 has the evidence and what would settle it.

**Two more things the bytes say.** A package expands into a folder named
after itself — `.pkg` stripped, `" Folder"` appended, so `Report.pkg` becomes
`Report Folder` (@0x2e5c) — and the expansion itself is not in the translator
at all: it opens the file and then calls `GetResource('Eng ', 2)` in
`StuffIt Engine™` and jumps into it (@0x334c). The translator is a driver.

**Detect only, and the reason is a specimen.** What a `Decode` line refers to
has not been read out of the expander, and no `.pkg` file has ever reached
this project, so there is nothing to grade a reading against. `tools/vmac/
spacesaver.py --pkg` re-derives everything above out of the translator on the
installed image, with four witnesses that fail if a different build is ever
put in front of it.


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

One logical file cut across several, one per floppy. **Five schemes
are implemented**: StuffIt segments, Compact Pro segments, spanned
("split") zip, plain `.NNN` splits and DiskDoubler's `SPLT`. They differ
in how much a part can prove about itself, and everything else follows
from that (DECISIONS.md 2026-08-08, 2026-08-09, 2026-08-10, 2026-08-14
and 2026-08-21).

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

**M11's four schemes join on the Mac** as of 2026-08-14, and so does a set
whose parts are still inside envelopes — the StuffIt scheme only, which is the
one whose identity survives a wrapper. **The fifth, DiskDoubler `SPLT`, joined
there on 2026-08-21** and is in the table. The StuffIt table below is from
2026-08-08; the others are:

| scheme | how it was driven | result |
|---|---|---|
| Compact Pro, 4 MB and **1 MB** | `run.py`, opened at a MIDDLE segment, the others named `One`, `Three`, `Last` | 9 files byte-exact against the Linux oracle, peak heap 19,915 B |
| Compact Pro, last segment withheld | same | 0 files, refused — the negative control |
| Spanned zip, 4 MB and **1 MB** | `interactive.py --named zip`, opened at part 1 of 5 through Standard File | joined file **byte-exact**, 278,294 B |
| `.NNN` split, 4 MB and **1 MB** | `interactive.py --named split`, opened at part 1 of 3 | joined file **byte-exact** |
| Parts inside envelopes, 4 MB and **1 MB** | `interactive.py --wrapped`: part 1 as `Apart.sit.1.hqx`, part 2 as `zzz-download.bin`, part 3 as `Other.9.hqx` | same contents as the Linux CLI on the same three files, and no decoded parts left on the volume |
| A chained file (`.sit.hqx`), 4 MB and **1 MB** | `interactive.py --chain` | every layer comes off and the intermediate is removed — which this application did NOT do before 2026-08-14 (BLOCKERS.md) |
| DiskDoubler `SPLT`, 4 MB | `segcheck.py --case ddseg-real`: two parts **cut by DiskDoubler Pro 4.1.1 itself**, part 2 on the volume as `zzz-piece2` | the joined file off the Out volume equals the file the corpus publishes — 15,918 B data + 342 B resource fork, the latter with the OS-stamped header bytes masked — and the grid agrees, peak heap 8,208 B |

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

### DiskDoubler `SPLT`

DiskDoubler's own Split command, in scope since 2026-08-21.
`src/fmt_ddseg.c` has the layout, derived from the six specimens in
`ssokolow/diskdoubler-test-files` (four when it was derived — BLOCKERS.md); why each field is read the way it is,
and the rule that a `SPLT` header beats a `.NNN` filename, are
DECISIONS.md 2026-08-21.

A 94-byte header per part, carrying more than any other scheme's: the
set's 26-byte identity, the part INDEX, the part COUNT, both fork
lengths of the original file, and that part's own payload length. So it
is the only scheme here where a part is matched by content AND the set's
size is known — a missing tail is detectable, which the plain `.NNN`
split cannot manage either way — and the only one where bytes appended
to a part never reach the join. It stores no NAME; the joined file takes
the opened part's, minus the `.N`. The payload is the DATA fork then the
resource fork, the opposite of StuffIt's split.

**No reference reads it** (MEASURED, 2026-08-21): `unar` 1.10.8
recognizes neither a part nor the parts concatenated. All three specimen
sets reassemble byte-exact, forks included, against the files they were
cut from — including the 14,128-byte resource fork of the
self-extractor, the largest fork any of them carries.

**And the loop closes without an oracle at all**: DiskDoubler Pro 4.1
splitting a 1,024,000-byte file under Mini vMac
(`tools/vmac/ddpro.py --experiments`) produced a two-part set that this
engine joins back to the bytes that went in, byte for byte — cut on a
Mac, joined here, compared with the input, which is the same bargain the
method 1 specimens make.

Part opens are one per part, 0 backward. Peak heap is the 8 KB streaming
buffer. The CRC-16/XMODEM at offset 48 is exact on all six specimen
parts and is **checked while a part is read straight through**, which is
what joining a set does (DECISIONS.md 2026-08-21).

**The 4 bytes at offset 4 are the Mac's `TickCount` when the file was
split** (MEASURED 2026-08-21, `tools/vmac/ddpro.py --experiments`):
DiskDoubler Pro splitting three files 72 s apart wrote 7,581, 11,905 and
16,235 — differences of 4,324 and 4,330, which is 60.06 and 60.14 per
second against the Mac's 60.15 Hz tick. Two of the three files were
byte-identical with different names, so it is neither a checksum nor a
hash of the name. It is written once per SET, which is exactly why it is
equal across a set's parts and different between sets; the joiner needs
no more than that, and matches on all 26 identity bytes anyway.

## Hardening

- Differential: 927 fixtures byte-exact against `unar` manifests
  (both forks + type/creator), `./ci.sh` — 107 of them since 2026-08-21,
  the DiskDoubler corpus, whose manifests are built from the files it was
  made from rather than from a decoder (TESTING.md). `run_diff.py` prints
  the number it actually ran, plus two figures that must be read with it:
  **16 forks across 10 fixtures are oracle-unadjudicated** — both
  implementations decline every one of them, so the engine's own CRC-16
  is the only byte-exact check; 8 more were compared
  with DiskDoubler's own expander on an emulated Mac and agree with the
  resource header's OS-stamped bytes masked, which `run_diff.py` reports
  as its own line — and **7 entries are compressed with a method the
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

## Resident memory, stack and launch (Mac target)

Everything here is measured on the Retro68 target's own flags
(`-mcpu=68000 -Os -ffunction-sections`), summed per object, on 2026-08-24.

| | code | rodata |
|---|---|---|
| engine (`src/*.c`) | 92,580 | 25,437 |
| zlib | 11,682 | 4,369 |
| Mac shell | 11,784 | 732 |
| **total** | **116,046** | **30,538** |

The application ships as 154,240 B of MacBinary (`dist/unclassic.bin`). Both
halves are resident for the whole session: the link line produces a single
`unclassic.code.bin` that the Segment Loader reads at launch, and
`Elf2Mac/LdScript.cc` emits `*(.rodata*)` inside the `.data` output section —
the A5 global world, allocated once and never purgeable.

The five largest objects are `unc_crypt.c` (7,654 + 7,032),
`unclassic_mac.c` (11,784 + 732), `fmt_spacesaver.c` (2,528 + 9,694, almost
all of it `ss_dict.h`), `inflate.c` (7,824 + 2,675) and `fmt_dd.c`
(10,194 + 12).

### Launch

**A kilobyte of code is not a kilobyte of launch time; a RELOCATION is.**
Measured by ballast — a block of resident data compiled in behind a temporary
define and referenced from the startup path so `-gc-sections` keeps it — three
runs each on `mv-4M-1x` (authentic 7 MHz), System 6.0.8, booting straight into
the application:

| build | app | relocations | boot |
|---|---|---|---|
| shipping | 150,144 B | 2,376 | **8.9 s** |
| + 64 KB of `const unsigned char[]` | 215,680 B | 2,376 | **8.9 s** |
| + 64 KB as 16,384 pointers | 232,064 B | 18,682 | **10.0 s** |

64 KB that carries no relocations is **below the harness's 0.1 s resolution**;
64 KB that carries 16,306 more is 1.1 s, about **67 µs per relocation**. The
whole application has **2,376**, so everything it pays at launch for its own
size is ≈ **0.16 s of an 8.9 s boot** — the rest is System 6 booting.

That is why the CODE resource is not segmented (BLOCKERS.md, *Withdrawn
claims*), and why moving `ss_dict.h` or the StuffIt tables out of the A5 world
would buy nothing at launch: they are data, so they carry no relocations.

### Budget

**What a 1 MB Mac Plus actually leaves the engine is 597,036 B** — measured
2026-08-24 with `run.py --mem 1M -D UNC_AT_BUDGET`, which reports
`FreeMem()` at **678,956 B** and the shell's `kMemReserve` at 80 KB. This is
the number `ci.sh` caps the StuffIt 5 run at and the number every `--budget`
figure in this file is drawn from.

**It was 678,392 B everywhere until then, and that was 91 KB too generous.**
Two fixtures now agree with the Mac to 48 bytes at 597,036 (*Floor target
verification*); at 678,392 the ISBN fixture was out by 90,981. The old figure
was not obviously wrong when it was taken — it reproduced the machine's peak
then, to 54 bytes — and it went stale silently because the budget is
`FreeMem()` at the moment extraction begins, so it falls every time the
application or its dialogs get bigger. Nothing re-measured it for seventeen
days.

**What hid it for those seventeen days is the shape of the dial**, and it is
the reusable part: `target` halves, so a budget error smaller than the gap
between two rungs changes nothing observable. It became visible only when the
index got 25 % smaller and moved the ISBN fixture onto a different rung on
Linux but not on the Mac. **A cross-validation that agrees is not evidence
that its input is right when the thing it drives is quantised.**

**And 597,036 B is the System 6 whole-machine case, which is the ROOMY
one.** Under MultiFinder and on System 7 and later the application gets a
PARTITION, and `unclassic.r` declares a 400 KB minimum — a user who accepts
that in Get Info, or a machine that cannot spare the 4 MB preferred size,
gets it. Measured 2026-08-24 on System 7.0.1 with the preferred size built
down to 400 KB, `-D UNC_AT_BUDGET`: **`FreeMem()` 212,056 B, budget
130,136 B.** The partition also holds the application's own ~150 KB of code
and its 32 KB stack, which is where the rest of the 400 KB goes.

**So there are two budgets, four and a half times apart**, and a figure
measured on the roomy one says nothing about the tight one:

| | free | reserve | budget |
|---|---|---|---|
| System 6.0.8, 1 MB, no MultiFinder (whole machine) | 678,956 B | 80 KB (cap) | **597,036 B** |
| System 7 / MultiFinder at the declared 400 KB minimum | 211,960 B | 53,014 B | **158,970 B** |

Both are `FreeMem()` less the reserve, taken when extraction begins.

**The reserve is a QUARTER of free, clamped to [32 KB, 80 KB]** — it was a
flat 80 KB until 2026-08-24. On the roomy tier a quarter exceeds the cap, so
that tier is unchanged and every figure measured on it stands. In the
minimum partition a flat 80 KB was **38 % of the whole heap** held back from
a machine with none to spare; the quarter rule makes it 53,014 B and the
budget 130,136 → **158,970 B**, which is what takes Now Compress from
opening none of its fixtures there to opening all three (*Budget sweep*).

**What the reserve is worth was measured, for the first time.** A probe
recording the lowest `FreeMem()` seen during writes, over all 67 fixtures of
the 1 MB sample: the tightest moment left **121,124 B** free, and the
Toolbox and File Manager together took **under 1 KB** while the engine sat
at its peak. By that evidence even the 32 KB floor is generous.

**What that evidence cannot see**, which is why the floor is 32 KB and not
the kilobyte measured: a stripped System Folder with no INITs, a RAM-backed
emulated disk, and no fragmentation pressure. A real Plus with a Chooser
extension, a floppy's File Manager buffers or an AppleShare volume all cost
more, and the reserve also covers a dialog or an alert drawn while the
engine holds its peak. MANUAL_TESTS.md carries it.

**`kMemReserve` cannot be traded for speed** (derived from the above, and it
closes PLANNED_WORK.md's proposal to try): the next `target` rung for the
slowest fixture needs a 650,222 B peak, so the reserve would have to fall
from 80 KB to under 28 KB to reach it. That is headroom the Toolbox and File
Manager use during output writes, on the one machine nothing here can test on
real hardware. Whatever the reserve is worth, it is not a rung.

### How low it goes

Two different floors, both binary-searched with `tools/run_budget.py` over
the whole corpus (2026-08-24). A sweep is two seconds, so these are searched
rather than sampled:

| | budget | partition |
|---|---|---|
| every archive at least OPENS — entries named, folders made, each failure per entry | **27,596 B** | ~252 KB |
| every fixture EXTRACTS FULLY — nothing budget-limited at all | **566,009 B** | **~826 KB** |

The partition column is `budget + reserve + 197,640 B`, and that overhead —
the application's own code, its 32 KB stack and the A5 world — is measured,
not modelled: 409,600 − 211,960 at a 400 KB partition and 870,400 − 672,760
at an 850 KB one, **197,640 both times**.

**So: give it about 850 KB in Get Info and everything in the corpus comes
out whole.** At the declared 400 KB minimum every archive still opens and
lists; 16 of 31 StuffIt 5 fixtures and two others fail per entry, with a
message naming each.

**The opens-floor was 137,264 B until 2026-08-24** — Now Compress's block
buffers, the engine's only per-ARCHIVE allocation, which returned
UNC_ERR_MEM and refused the whole archive: no listing, no entry names,
nothing. Against a 158,970 B budget at the minimum partition that left
**21,706 B of headroom**, on an application that grew twenty-four kilobytes
in two versions. It fails per entry now, like everything else, and the floor
is five times lower.

### Budget sweep: the corpus at both budgets

`tools/run_budget.py` runs the whole corpus under a cap. Run it at the
figure that matters — and **the figure that matters is the MultiFinder one**
(*Budget*), because that is the one a user can choose:

| format | fixtures | limited at 158,970 B | peak |
|---|---|---|---|
| BinHex | 204 | 0 | 8,192 B |
| Compact Pro | 108 | 0 | 31,111 B |
| StuffIt | 227 | 0 | 81,212 B |
| LZH | 8 | 0 | 44,624 B |
| Gzip | 3 | 0 | 52,216 B |
| **Now Compress** | 3 | **0** | 137,264 B |
| DiskDoubler | 91 | 1 | 158,720 B |
| Unix compress | 4 | 1 | 120,880 B |
| StuffIt 5 | 31 | **16** | 158,165 B |

Before the two 2026-08-24 changes — Now Compress sized from the fork, and
the adaptive reserve — the same sweep at the then-budget of 130,136 B had
Now Compress at **2 limited of 3 with a peak of zero** (refused whole,
before an entry was read) and StuffIt 5 at 21 limited.

At the roomy System 6 budget of 597,036 B only StuffIt 5 refuses anything
(8 of 31), which is why it is the only format with a memory-for-time path.
**At 130,136 B that picture is quite different**, and it is the reason the
fixed-size windows are worth sizing from the entry after all:

- **Now Compress allocated 131,072 B per ARCHIVE, before an entry was
  read**, and at 130,136 B that failed — so it opened NONE of its three
  fixtures, refused with a high-water of zero. Sized from the largest fork
  (2026-08-24) the small one is 84,248 B, and with the adaptive reserve
  all three open. A per-archive allocation failure is also the one shape
  the engine's contract does not allow: failure is supposed to be per
  ENTRY. Listing now skips the allocation entirely, so `l` works in any
  partition.
- **SuperDisk's window** was a flat 98,304 B and is now bounded by the
  fork: 117,294 → 85,943 B, and `Read Me` in `alysis-disk-expander-12`
  extracts under a 50,000 B budget where it used to be refused.
- **zip's inflate window** was deflate's full 32 KB per entry;
  `synth-exo-zip-deflate.zip` fell 53,515 → 24,843 B. gzip's cannot be
  done at all — its ISIZE is in the trailer, so `fmt_exo.c` passes
  `UNC_SIZE_UNKNOWN`.

**ARC (33,732 B) and SpaceSaver (36 KB measured, 68 KB ceiling) still fit
at 130,136 B**, so they stay on their ceilings — but note that this is a
measurement about today's corpus and today's minimum partition, not a
property of those decoders. ARC's is the awkward one if it is ever needed:
its tables are indexed by a 12-bit code read straight from the stream, so a
smaller allocation changes what a damaged file does, and it needs
`unc_lzw.c`'s two-number treatment.

There is still nothing for a generic adaptive mechanism to work on, and one
could not be graded against this corpus. It becomes real the day a format
with a megabyte-class window arrives, and the Arsenic answer will not simply
port to it — DECISIONS.md (2026-08-03, the LZW table) is the recorded case
of that same fix failing on the second problem. LZH is not that format:
64 KB of window worst case, and it halves.

### Per-file `-O2`

**Tried and rejected, 2026-08-24.** Everything builds at `-Os`;
`sit_arsenic.c` is the one file where that looks like the wrong trade,
because it is 4 KB of code that runs for twenty minutes while every other
decoder runs for seconds. Building that one file at `-O2`:

| | app | ISBN at 1 MB, 1x |
|---|---|---|
| `-Os` | 154,240 B | **1,284 s** |
| `-O2` on `sit_arsenic.c` | 155,776 B | **1,304 s** |

**1,536 B for an effect that is at or below the harness's resolution and not
in the right direction.** The two runs are exactly one poll interval apart at
`--poll 20`, which is the finest poll these runs tolerate, so the honest
reading is "≤ 20 s, sign unknown" — and that does not buy 1.5 KB. Do not
re-try without a harness that resolves better on a 22-minute run.

### Stack

**Measure it; do not assume it.** One command gives every function's frame:

    m68k-apple-macos-gcc -mcpu=68000 -Os -std=c99 -Iinclude -Isrc \
        -fstack-usage -c src/FILE.c -o /dev/null

and the call graph comes from the relocations in the linked objects
(`m68k-apple-macos-objdump -dr`), so the worst path is a sum over the two.

| | before 2026-08-24 | now |
|---|---|---|
| deepest chain in the engine | 6,664 B (`unc_dd_extract` → `dd_fork` → `dd_ddn`) | **3,290 B** |
| Now Compress chain | 5,632 B | ~1,400 B |
| largest single frame | 3,740 B (`dd_fork`) | **2,352 B** (`ars_index_build`) |

The 6,664 B chain **exceeded CLAUDE.md's 4 KB call-depth rule by 66 %**, for
months, in code that ships and passes on a real 1 MB Mac Plus. It never came
near the machine: `mac/unclassic_mac.c` runs
`SetApplLimit(LMGetApplLimit() - kStackBump)` with `kStackBump` = 24 KB, so
the shell has **32 KB of stack**, not the 8 KB default. The rule is what keeps
the engine portable to a host that did not ask for more.

What fixed it: DiskDoubler's three `UncCanon` and Now Compress's two moved to
the heap (~3.9 KB each, per fork and per archive respectively), and the zip
end-of-central-directory scan window stopped at 1 KB rather than the 4 KB that
would have made it the deepest frame in the engine on its own.

## Decode cost, before and after the 2026-08-24 pass (Linux, callgrind `Ir`)

Instruction counts, not cycles, and immune to what else is running on the box —
which wall clock here is not. Use them as ratios between builds of the same
engine, never as predicted runtime; the Mac Plus figures two sections down are
the ones a user waits through.

| Fixture | What it exercises | before | after | |
|---|---|---|---|---|
| `ACInfo_Comm.sit.bin` | opening a MacBinary envelope | 757,559 | 163,776 | **−78.4 %** |
| `alpha401.cpt` | the same, Compact Pro inside | 761,290 | 167,655 | **−78.0 %** |
| `xmasbeeps.sit` | the same, StuffIt inside | 789,219 | 195,059 | **−75.3 %** |
| `derived-Library_ISBN_Barcoder.sit` (`--budget 597036`) | StuffIt 5, sampled index | 2,346,708,561 | 697,304,583 | **−70.3 %** |
| `derived-SyntheticReferences2.0.sea` | Now Compress | 791,938,983 | 419,972,116 | **−47.0 %** |
| `derived-Terrainman_2.0__.sea` | DiskDoubler DDn | 52,194,820 | 32,424,007 | **−37.9 %** |
| `derived-EmpireBuilderDemo.sit` | StuffIt, serialized-tree Huffman | 48,971,940 | 31,422,881 | **−35.8 %** |
| `derived-a2basic.dmg.sit` (`--budget 597036`) | StuffIt 5, sampled index | 487,403,395 | 315,159,205 | **−35.3 %** |
| `derived-XferIt_1.5b4.sea` | Compact Pro | 114,726,855 | 77,335,095 | **−32.6 %** |
| `PCCTS.tar.gz` | gzip (zlib inflate + our CRC-32) | 6,342,819 | 5,411,475 | **−14.7 %** |
| `derived-MUSFMT10.ZIP` | zip (deflate) | 13,728,964 | 12,068,337 | **−12.1 %** |
| `derived-xmasbeeps.sit` | StuffIt classic method 2 (LZW) | 34,270,500 | 30,635,054 | **−10.6 %** |
| `a2ps.V4.3.tar.Z` | Unix compress (LZW) | 4,648,124 | 4,212,836 | **−9.4 %** |
| `macburger-helper.hqx` | BinHex | 26,385,143 | 24,054,217 | **−8.8 %** |
| `4acalc.zip` | a real zip, 8 KB | 151,835 | 151,784 | −0.0 % |

**Read the two StuffIt 5 rows with `Budget` in mind.** Both builds are capped
at 597,036 B, the figure the machine actually gives the engine — but the older
build falls to `target` 256 there where the newer one holds 512, so part of
that −70.2 % is a whole rung of the memory-for-time dial rather than cheaper
instructions. The number a user waits through is the Mac Plus wall clock two
sections down: 1,898 s → 1,384 s.

**The three envelope rows are the same change and it is not a decoder at all:**
`unc_macbinary_probe` moved ahead of the 64 KB backwards scan that
`unc_zipseg_probe` runs on every file, and the scan itself became a pointer
walk. MacBinary is 234 of the 929 fixtures.

**A real zip is unchanged**, which is the control: `4acalc.zip` is 8 KB, it
finds its end-of-central-directory record in the first window and always
did, and nothing in it is hot enough to move.

**The three CRC functions are four bytes per loop test, walked with a
pointer.** They are the most shared loop in the engine — every format's fork
CRC comes through one of them — and `unc_crc32` alone was **40.7 %** of a
gzip extraction, where zlib does the inflating and this does everything
else. That is what moves gzip and zip off the flat line they sat on through
every earlier change, and it is 4 % on the Huffman formats besides. **Not**
slicing-by-4, which is the usual next step: that wants aligned 32-bit reads
of the input, which the 68000 discipline forbids, and a table four times the
size. Same bytes in, same table, same answer, 384 B of code.

**Both Huffman decoders now peek eight bits and look the code up**, and they
are separate decoders: `unc_canon_decode` reads canonical code lengths
(Compact Pro, DiskDoubler DDn, Now Compress, StuffIt 13, LZH) and
`unc_huff_decode` walks a serialized TREE (StuffIt method 3, DiskDoubler
method 4, PackIt). The second was found by re-profiling after the first
landed — it was 48 % of `derived-EmpireBuilderDemo.sit` and the original
plan had not named it. Its table stores the symbol, because an arbitrary
tree has no arithmetic that recovers one; the canonical table does not need
to.

`unc_bitin_bits` takes its n bits in one masked shift when the window holds
them, instead of n calls to the single-bit reader. That is another 6 to 10
points on DiskDoubler and Now Compress on top of the table.

**Both tables are TEN bits wide, and that was measured rather than
assumed.** Eight is the textbook figure and covers every code of eight bits
or fewer, which for a 256-symbol alphabet is most of the symbols decoded.
Now Compress codes 0x122 symbols and DiskDoubler DDn 257, and there the
tail past eight bits was where the time still was: 8 → 10 is a further
**17.0 %** of a Now Compress run, 8.0 % of DiskDoubler, 7.8 % of Compact
Pro and 8.7 % of the tree decoder's StuffIt fixture. 11 adds 2.7 % more and
12 a further 0.7 %, for two and four times the table, so 10 is the knee.
The cost is 1 KB (canonical) or 2 KB (tree) per table and `1 << K` writes
per build; archives of many small entries were checked for that build cost
and `derived-keyAhead.cpt` got *faster*.

### What is still hot, measured on the same runs

`ars_next_symbol`'s linear symbol search averages **10.4 iterations per
decoded symbol** (471,500 symbol decodes on the ISBN fixture; the loop's two
lines are 4.52 % + 5.37 % of the run against 0.72 % for both divisions). That
kills the obvious idea of replacing `code / renorm` with a multiply per
iteration — ten `__mulsi3` calls would cost a 68000 more than one
`__udivsi3`. The divisions are now unsigned, which deletes `__divsi3`'s sign
wrapper; gcc had **already** merged the third one the plan expected to find.

**BinHex is the one left with an obvious shape and no obvious fix.**
`bh_get_bits` is still 38 % of a large `.hqx` — 600,000 calls at about
sixteen instructions each, over half of them call overhead — and giving it
an inline fast path with the rare cases behind a call measured **worse**
(−5.5 % against −6.6 % without it), for the same reason the bit reader did:
the opaque call forces the cursor fields back to memory. What is left is
decoding four groups to three bytes in a batch, which changes what a stream
truncated mid-triple does, and that is graded by 9,270 robustness variants
rather than argued.

`-flto` is not available: it crashes Retro68's gcc 16.1.0 with an internal
compiler error (`write_symbol, at lto-streamer-out.cc:3097`, during IPA pass
`modref`) on `mac/unclassic_mac.c`. Tried 2026-08-24, clear pass/fail, do not
re-try without a newer toolchain.

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
| `derived-a2basic.dmg.sit` | 205,019 B | **587 s** (peak 1,031,525 B) | **762 s** (peak 482,345 B) | 1.30x |
| `derived-Library_ISBN_Barcoder.sit` | 641,115 B | **768 s** (peak 1,682,142 B) | **1,284 s** (peak 559,805 B) | 1.67x |

**The fallback costs 1.30x to 1.67x, and Arsenic is still the slow one.**
Ten minutes for a 205 KB output is what the *fast* path costs a 7 MHz 68000;
before 2026-08-07 a 1 MB machine could not extract either entry at all. The
ratio widens with block fill, and neither the x86 ratio nor one fixture scaled
by output size predicts these — DECISIONS.md 2026-08-07 for both.

**The 1 MB column is the 2026-08-24 performance pass.** It was 966 s (peak
560,589 B) and 1,898 s (peak 614,134 B) before, which is where the "1.65x to
2.47x" this section used to state came from. What changed: a sentinel byte
removed the bound test from the scan that was 77 % of the second run, and the
index's sample positions went from four bytes to three. Both are byte-exact by
construction; DECISIONS.md 2026-08-24 has the reasoning and BLOCKERS.md the
proposal the same measurement killed.

**The 4 MB column did NOT change and was not re-measured**: those runs take
the transform vector and never touch the sampled index or its scan.

Both 1 MB figures were re-run on the build that first carried them, and
everything landed since moves the ISBN fixture by **0.2 % on Linux** —
below this harness's 20 s resolution on a 22-minute run, so they stand
rather than being re-measured for a change that could not show. Two of the
smaller changes have their own measurements: the unsigned divisions are worth
**20 s of 1,404** on the ISBN fixture (1.4 %) and nothing measurable on
`derived-a2basic.dmg.sit`, and replacing the per-output-byte binary search
over `cum[]` with a 512-byte coarse table is worth **100 s of 1,384** (7.2 %)
for 512 bytes of heap and no code at all.

**Poll no faster than 20 s on these runs.** `--poll 5` and below report a
bogus FAIL after about five seconds, with a nonsense value in the grid's `ret`
slot — four times out of four here, against five clean runs at `--poll 20`.
The alive-grid-read-mid-paint explanation is a **hypothesis**; the pattern is
measured. The short 4 MB runs in the table above are a different regime and
`--poll 3` is fine for them.

**Three bytes per sample buys 25 % more density at the same budget**, and on
Linux that moves `derived-Library_ISBN_Barcoder.sit` from `target` 512 to 1024
— if the budget is big enough. **The real 1 MB Mac stayed at 512**, taking the
saving as 55 KB of headroom instead of as density. That disagreement is what
found the budget error in *Budget* below: the machine's is 597,036 B, not the
678,392 B every simulation here was using.

All four figures were measured with one emulator running at a time. The 4 MB
pair supersedes an earlier one (537 s / 927 s) taken before the progress
rewrite; DECISIONS.md 2026-08-07 records the ~40 s between those two sets as
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

The engine's *relative* cost is a property of the code and transfers to any CPU
as a ratio. (Absolute Mac Plus figures are two sections up; this table is the
shape, not the clock.) Measured with `unclassic t`, best of three, on the
release build:

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

The Retro68 Mac shell was replayed against a 67-fixture sample spanning all
seventeen formats on a **real System 6.0.8 / 4 MB Mac Plus** under Mini vMac
(a true 68000). Every extraction is verified ON THE MAC ITSELF: the app
CRC-32s both forks after reading them back through the File Manager and the
result — painted to the framebuffer, read from a screenshot — is
cross-checked against the same engine's Linux output (`tools/vmac_check.py`,
`tools/decode_grid.py`).

**67/67 byte-exact PASS** (**2026-08-23**, with M28's LZH in and five
`.lzh` fixtures added to the sample — MacLHA's MacBinary payload, `-lh7-`'s
64 KB window, LArc's `-lz5-`, a five-entry Amiga archive and the smallest
archive in the corpus; 62/62 earlier the same day, re-run against the
decryption build, which is 20 KB larger; 2026-08-22 with M15–M23's codecs in and
three fixtures added for them — DiskDoubler methods 3, 4 and 5, which nothing
in the sample had exercised; 59/59 on 2026-08-15, re-run after the BinHex line rule
changed — every `.hqx` in the sample goes through it; 57/57 earlier the same
day, before M13 added ARC and uuencode; 55/55 on 2026-08-08, before M12 added
two names to the sample) — data forks exact, resource forks exact bar the
OS-stamped reserved header (bytes 16–127). Those runs were 63, 61 and 55
files long: four names were listed twice until 2026-08-21 and every sweep ran
them twice (BLOCKERS.md). The verdicts are unchanged — a duplicate that
passes twice passes — and the COUNT is what was wrong.

**The archive comment is written on the Mac too** (2026-08-23,
`run.py` then `checkdisk.py`): `derived-DigSim_RAM_Circuit.cpt`
extracts as 11 files rather than 10, the extra being a `TEXT`/`ttxt`
document called `Comments` holding the nine bytes *"Hi there."*,
byte-exact against the CLI's own comment file when read back off the
Out volume. Verified on its own rather than added to the sample, which
would restate every tier's figure.

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
| Compact Pro | 24 KB |
| Zip | 12–53 KB (re-measured 2026-08-09, was 12–65: see ¶) |
| Gzip | 51 KB |
| StuffIt classic | 19–72 KB‖ |
| Unix compress (.Z) | 15–219 KB§ |
| StuffIt 5 (Arsenic) | 0.63–2.53 MB (block *fill* dependent — see †) |
| LZH / LHA | 4–41 KB over the sample (4,112 B stored, 41,364 B for `-lh7-`); 74 KB is the format's ceiling, for an entry that fills a 64 KB window |
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

**67/67 byte-exact PASS at 4 MB** (**2026-08-23**, with M28's five `.lzh`
fixtures in and every codec since M15 — this tier's first run since
2026-08-22; 62/62 then, 59/59 on 2026-08-21, 55/55 on 2026-08-08 and 44/44
before the sample grew) — the same committed sample, the same on-Mac CRC-32
read-back. The 2026-08-21 run is the first on this tier since M12, M13 and M14,
so it is the first that includes DiskDoubler, Now Compress, ARC and uuencode
here; every one passed, 5.1 s a fixture, one boot each:

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
the shell's constant 16 B. **Peaks re-measured 2026-08-24**, when the two
Huffman decoders gained lookup tables and DiskDoubler DDn's and Now
Compress's code tables moved off the stack; the previous column is in
brackets:

| Fixture | Format / method | Files | Peak heap on the Mac | Data | Rsrc |
|---|---|---|---|---|---|
| `derived-DandStoQIF2.sea` | DiskDoubler AD1 (9) | 3 | 16,400 B | 20,918 B | 24,562 B |
| `derived-MAZv143.sea` | DiskDoubler Compact Pro (8) | 2 | 22,594 B (was 19,318) | 57,078 B | 40,079 B |
| `derived-MacPass390.sea` | DiskDoubler Compact Pro (8) | 3 | 22,594 B (was 19,318) | 0 B | 351,825 B |
| `derived-DD_Expand.sea` | DiskDoubler DDn (10) | 1 | 108,610 B (was 102,432) | 0 B | 270,362 B |
| `derived-LHA_Expander_1.0.3.sea` | DiskDoubler DDn, folders | 5 | 116,802 B (was 110,624) | 69,776 B | 82,778 B |
| `derived-Terrainman_2.0__.sea` | DiskDoubler DDn + delta-1 | 12 | 112,706 B (was 106,528) | 95,860 B | 245,265 B |
| `derived-Expand_Now_1.0.1.sea` | Now Compress | 1 | 137,250 B (was 131,088) | 0 B | 88,942 B |

**The 3–6 KB each row gained is the lookup tables**, and it is bought back
many times over: those same fixtures decode 30–47 % fewer instructions
(*Decode cost*). `derived-DandStoQIF2.sea` is unchanged because AD LZSS has
no Huffman stage at all.

`derived-DandStoQIF2.sea` was in the sample before M12 as a REFUSAL case —
the only one there has ever been — and is now an extraction.

**Multi-document BinHex was checked here too**, on a file the corpus does not
contain: `export-hc.hqx`, a mail separator, and `mac-rot13.hqx` concatenated.
2 files byte-exact at 4 MB and at 1 MB, 8,208 B peak. It is not in
`sample.txt` because it is not a corpus fixture; regenerate it by
concatenating those two with any text between them, which is what
`tools/run_multihqx.py` does on Linux.

### SuperDisk! on the Mac (2026-08-20)

Not in `sample.txt`, because neither archive is a fixture: both are PAYLOADS
inside envelopes, and `run.py` graded only against an oracle manifest, which
for this format describes the envelope. Since 2026-08-21 one command replays
both — `tools/vmac/superdisk.py --on-mac`, which unwraps each payload and
grades it with `run.py --expect` against this engine's own Linux output
(both PASS at 4 MB, re-run 2026-08-21). **Identical numbers at 4 MB and at
1 MB**, and identical to the Linux aggregate for the same payload, `ret` 0
with 0 entry errors on every run:

| Payload | Files | Peak heap on the Mac | Data | Rsrc |
|---|---|---|---|---|
| `SD! Utilities.x` (method 7) | 3 | 74,252 B | 9,916 B | 14,389 B |
| `Disk Expander .X` (method 11) | 2 | 117,326 B | 1,748 B | 66,953 B |

The 117,326 B is the 96 KB SlowFastB window plus one block, and the Mac
granted it at the floor target without a refusal. Both exceed the Linux figures by exactly 32 B, which is
the shell's 16 B allocation header on each of the TWO blocks live at the peak
— the block buffer and either the window or the context table. The
DiskDoubler rows above differ by 16 B for the same reason: one block.

## Floor target verification (Mini vMac — System 6.0.8, **1 MB** Mac Plus, 68000)

The same 67-fixture sample was replayed on a Mini vMac built for **1 MB of
RAM** — the project's floor target — one boot per fixture, same on-Mac
CRC-32 verification (`tools/vmac/run.py --mem 1M --list tools/vmac/sample.txt`).
The engine budget is derived from `FreeMem` at startup.

**67/67 byte-exact PASS** (**2026-08-23**, with M28's five `.lzh` fixtures
in — the heaviest of them 41,364 B, so nothing here moved; 62/62 earlier the
same day, re-run twice against the
decryption build — 20 KB more code is 20 KB less heap on this machine, and
the three heaviest allocations are unchanged at 533 KB, 471 KB and 405 KB;
2026-08-22 with M19–M23's three; 59/59 on
2026-08-15 with M13's two; 57/57 before them;
55/55 on 2026-08-08 and 44/44 on 2026-08-07, before the recovered fixtures,
the method-6 pair and M12's two joined the sample; the sample carried four
duplicate lines until 2026-08-21, so those runs were 63, 61 and 55 files
long — BLOCKERS.md). There are no memory-budget refusals
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

**The CLI's `--budget` simulation is cross-validated against the real Mac
allocator**, and was re-validated on 2026-08-24 after the budget itself turned
out to have drifted. `unclassic --budget 597036` predicts 482,297 B and
559,241 B for those two; the Mac measures 482,345 B and 559,289 B — **48 bytes
apart in both cases**. That is worth stating because every budget figure
elsewhere in this file is a Linux number. The superseded pair (560,535 /
614,080 against 560,589 / 614,134, at `--budget 678392`) agreed just as well
when it was taken; see *Budget* for why that stopped being true.

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
| envelope over a non-archive | 34 | ✅ | ✅ ✧✧✧ |
| StuffIt 5 / Arsenic | 62 | ❌ postdates it | ✅ |
| zip, gzip, `.Z`, tar | 16 | ⚠️ paid add-on, System 7 only | ✅ |
| PackIt | 5 | ❌ not in its list | ✅ |
| DiskDoubler, Now Compress | 14 | ❌ | ✅ since 2026-08-15 |
| Alysis SuperDisk! | 2 | ❌ not in its list | ✅ since 2026-08-20 |
| LZH, StuffIt X | 2 | ❌ | LZH ✅ since 2026-08-23; StuffIt X detect-only, named |
| **total** | **805** | **704 alone, 720 with the add-on** | **804 extract, 1 named** |

✧✧✧ The 34 break down as 31 envelopes whose payload is a resource-only file,
and 3 whose payload is a document: two HyperCard `STAK`s and one damaged
Compact Pro archive whose index offset points past its own end (`unar`
declines it too). The row held 36 until 2026-08-20, when the two Alysis
SuperDisk! payloads stopped being payloads and became the archives they always
were, and moved to their own row above. The Expander column's total was
corrected at the same time: it had read 708 since the row went from 38 to 36
and nobody re-added the column.

The 62 StuffIt 5 fixtures are the largest single difference, and it is a date
rather than a capability: 4.0.2 shipped two years before the format. Handed
one it answers *"You may need a newer version of the StuffIt Engine to work
with this archive."*

### Capability by capability

| | StuffIt Expander 4.0.2 | unclassic 0.15 |
|---|---|---|
| Floor system | System 6.0.5 (its Read Me) | System 6.0.8, measured on a 1 MB Mac Plus |
| Everything beyond `.sit`/`.cpt`/`.hqx`/`.bin` | needs DropStuff with Expander Enhancer, *"a **System 7-only** shareware product"* | in the same free application, on System 6 |
| Installed pieces | application + StuffIt Engine extension + the add-on | one 149 KB application, no extension, no installer |
| StuffIt segmented sets | with the add-on, so System 7 only | yes, System 6 and up |
| Compact Pro segmented sets | *"StuffIt Expander cannot expand encrypted or segmented Zip or Compact Pro files"* | yes |
| Spanned zip sets | same sentence — no | yes |
| Plain `.001`/`.002` splits | not claimed | yes |
| Parts still inside per-part envelopes | not claimed | yes, StuffIt sets |
| How a part is identified | not stated | by its header, never by its filename (zip and `.NNN` sets excepted — see "Segmented archives") |
| Segment joining, known defect | *"if the `Delete segments after joining` preference is selected, and you run out of disk space during a join operation, the first segment will be deleted even though the joining is not complete"* | parts are never deleted; the Mac shell removes only what it wrote |
| Encrypted archives | yes — it prompts, and knows *"You have entered an incorrect password"* | yes, since 2026-08-23: StuffIt, StuffIt 5, PackIt, zip (PKWARE and WinZip AES), ARC — and **Compact Pro, which Expander cannot** (*"StuffIt Expander cannot expand encrypted or segmented Zip or Compact Pro files"*) |
| btoa (`.ascii`) | with the add-on: a `btoa/atob Translator` ships in `Extensions:Aladdin:Translators` | yes, both framings (*btoa*, above) |
| Multipart BinHex | *"Multipart BinHex files, such as those appearing in Internet newsgroup postings (e.g. comp.binaries.mac), are fully supported"* — multiple documents in one text file, and one file broken into several pieces | several documents in one file since 2026-08-15 (††, above); a document broken across FILES joins where the parts are named `.001`, `.002` … |
| Compact Pro comments | written out beside the extracted items | **saved since 2026-08-23**: the Mac shell writes a `TEXT` document called `Comments` into the destination folder, the CLI writes `<archive>.comment.txt` and prints it on `l` and `t` |
| `.lzh` / `.lha` (LZH / LHA) | not named anywhere in its documentation, and no translator for it ships in `Extensions:Aladdin:Translators` — a Macintosh user reached for a separate application, and the corpus holds one (`LHA Expander 1.0.3`) | **yes since 2026-08-23**, every method, all four header levels, and MacLHA's MacBinary payload split back into two forks (*LZH / LHA*, above) |
| `.arc` (ARC / ArcMac) | with the add-on | **yes since 2026-08-15**, methods 1-9; ArcMac's two-fork payload since 2026-08-16 (★★★ above) |
| uuencode (`.uu`) | with the add-on | **yes since 2026-08-15**, plain and UUTool's two-fork shape |
| AppleLink `.pkg` | with the add-on | **named since 2026-08-23**, not expanded: the probe is Aladdin's own recogniser, read out of the `PKG Expand Translator` that StuffIt Deluxe 3.5.1 ships (*AppleLink packages*, above). What is missing is a specimen |
| StuffIt SpaceSaver | with the add-on | **yes since 2026-08-22**, methods 0 and 4 (what a 68000 writes), with SpaceSaver's own dictionary built in since 2026-08-23 so nothing else is needed; 1, 2 and 3 declined per entry (*StuffIt SpaceSaver*, above) |
| Chained expansion (`.sit.hqx`) | yes, and can be turned off | yes, `-nr` turns it off |
| System 7 conveniences | drag-and-drop of files, folders and whole disks; watch folders; background expansion; Apple events | none; Standard File, one archive at a time |
| Verification | none published | 927 fixtures byte-exact against `unar`/`macunpack` — bar the one uuencode fixture, which `unar` cannot read at all and whose ground truth is its generator's input, with `hexbin` agreeing |
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
