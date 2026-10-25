# DiskDoubler's three containers — a compressed file, `DDAR`, `DDA2`

**The coders are published; the containers never were.** The
Unarchiver's format wiki has a page for DiskDoubler's AD and DD
algorithms — `tools/derive_dd.py` reads them from it — and its
`DiskDoublerSpecs` page lists three more pages by name:

> * DiskDoublerSingleFormat
> * DiskDoublerArchiveFormat1
> * DiskDoublerArchiveFormat2
>
> (See … XADDiskDoublerParser.m for now.)

**Those three pages do not exist.** That wiki's own index,
`.../theunarchiver/wikis.json`, lists 40 pages and none of them is
one; fetched and read 2026-09-22, the same way `StuffIt5Format` was
found to exist on 2026-09-22. So the sentence is not a pointer to a
description, it is the absence of one — which leaves this container
where Now Compress's was: it has to be measured.

**What it is measured against.** 91 DiskDoubler fixtures — 66
compressed files, 18 `DDA2` archives, 7 `DDAR` archives, 244 entries —
each with an oracle manifest recording every entry's path, both fork
lengths, and the type and creator wherever `unar` reported them.
`tools/derive_ddc.py` is a reader written from this document and from
nothing else, and it makes **643 assertions against those manifests
with 0 disagreements**.

**And the layout is derived, not asserted.** `tools/derive_ddc.py
--grid` throws away the offsets below and searches for them: for each
field, every offset whose value agrees with the oracle in *every*
fixture that states one. Each field's row says what that search
returned, and a field the search cannot pin says so rather than being
presented as measured. Nothing locates a record except something the
format itself supplies — a compressed file's header is at zero and its
magic says so, an archive's first record is the first occurrence of the
archive magic past byte 4, and a file header inside an archive is where
the walk that those 643 assertions already grade put it.

## A compressed file

`0xABCD0054`, then 80 more bytes, then the data fork's compressed bytes
and the resource fork's, in that order.

**That long is not one magic number.** It is the word `0xABCD` and then
a 16-bit HEADER SIZE, measured 2026-09-22 — see *The header size, and
the 1990 header* below. Every specimen in this corpus states 84, so
everything in the table is offsets into an 84-byte header; a file
DiskDoubler ß05 wrote states 48 and stops after +47.

| offset | size | field | how it is pinned |
|---|---|---|---|
| 0 | 2 | magic `0xABCD` | the sniffer's, and 66 files begin with it |
| 2 | 2 | **the header's own size**, 84 here | **measured 2026-09-22**: the 1990 build writes 48 and lays the 48 bytes out identically, and its own expander accepts any value ≥ 48. `src/fmt_dd.c` reads both |
| 4 | 4 | data fork length | **pinned**: one offset survives over 66 compressed files, and one over all 195 file headers wherever they sit — 66 files, 36 inside `DDAR`, 93 inside `DDA2` |
| 8 | 4 | data fork compressed length | the walk: the resource fork's bytes begin here past the header, in every archive that has a next entry to arrive at |
| 12 | 4 | resource fork length | **pinned**, same two searches |
| 16 | 4 | resource fork compressed length | the walk, as +8 |
| 20 | 1 | data fork method | the census below, and the oracle's own method names on 26 forks |
| 21 | 1 | resource fork method | as +20 |
| 22 | 1 | `info1` | the XOR garbling, below |
| 24 | 4 | modification date | **not pinned here** — no manifest records a date, and the evidence for the pair is `tools/vmac/ndd.py --dates` on `DDA2`'s records (DECISIONS.md 2026-08-21) |
| 28 | 4 | creation date | as +24 |
| 32 | 4 | type | **pinned**: one offset agrees over 87 entries whose type the oracle recorded |
| 36 | 4 | creator | **pinned**, same 87 |
| 40 | 2 | Finder flags | **measured 2026-10-17**: DiskDoubler 3.7 copies the catalog's `fdFlags` here (`tools/vmac/ddmeta.py --writer`) |
| 42 | 4 | `fdLocation` | **measured 2026-10-17**: 3.7 writes the catalog's position here; its in-place Expand does not restore it (FORMATS.md, *Finder info in the archive*) |
| 48 | 2 | data fork checksum | the decoders check it: `src/fmt_dd.c` fails an entry whose sum disagrees, over the whole corpus |
| 50 | 2 | resource fork checksum | as +48 |
| 52 | 1 | `info2` | the XOR garbling, below |
| 54 | 2 | data fork delta distance | **held against the coder**, below |
| 56 | 2 | resource fork delta distance | as +54 |
| 82 | 2 | **CRC-16/XMODEM of bytes 0..81** | **measured 2026-10-17**: 70 headers of 70; 3.7 refuses one that disagrees (`ddmeta.py --reader`). 91 of 91 on 2026-10-23, over the fixtures and every specimen, and none stores the zero XADMaster accepts |
| 84 | | the data fork's bytes, then the resource fork's | |
| 84 + both | 84 | a byte-identical COPY of the header above | **63 of the corpus's 66 compressed files**, and the three without it are this project's own (below) |

### The header is written twice

**A file DiskDoubler compressed ends with a byte-for-byte copy of its
own 84-byte header.** True of 3.x and 4.x, and **not of the format** —
the 1990 build writes no trailer at all (*The header size, and the 1990
header*). 63 of the 66 compressed files here carry one, and
the three that do not are `synth-dd-m3.dd`, `synth-dd-m4.dd` and
`synth-dd-m5.dd` — written by `tools/vmac/ddencode.py`, in this tree,
rather than by DiskDoubler. So every real specimen has it and no
synthetic one does, which is the shape of a fact about the FORMAT and
also the shape of a thing our own fixtures would never have taught us.

It matters because it is what a `DDAR` record's span is measured in:
an entry whose file was compressed BEFORE it was archived carries the
whole `.dd` file, trailer and all, and one Combine compressed itself
carries no trailer. 31 entries of the corpus's `DDAR` archives have it
and 5 do not. Reading the trailer as a stray header of its own — which
is what it looks like from a walk that steps by the fork lengths —
happens to work, and is not what the archive says.

**The compressed file carries no name.** It is the host's file that has
one — DiskDoubler appended `.dd` to it — so nothing in this document
says what an entry is called, and `derive_ddc.py` grades a compressed
file on everything else.

### The header size, and the 1990 header

**Measured 2026-09-22 by running the oldest DiskDoubler there is.**
`DiskDoubler ß05, Copyright 1990 Salient` is an INIT with no
application: it adds a `DD` menu to the Finder reading
`Compress Selection;Expand Selection`, and nothing else. It is four
versions older than the 3.1.2 this project had been calling the oldest
(DECISIONS.md 2026-09-22, *the version that could not have written it*),
and `tools/vmac/diskdoubler.py --beta` installs it under System 6.0.8
and drives that menu.

What it writes, over a subject with an 11,428-byte data fork and a
340-byte resource fork:

    ab cd 00 30  00 00 2c a4  00 00 06 a1  00 00 01 54
    00 00 00 61  01 01 1f 00  00 00 00 00  00 00 00 00
    54 45 58 54  74 74 78 74  00 00 00 00  00 00 00 00

Field for field that is the table above: `0xABCD`, then **48** where
every corpus file says 84, then 11,428 → 1,697 and 340 → 97, methods
1/1, `info1` `0x1f`, the ORIGINAL file's `TEXT`/`ttxt` at +32 and +36,
and Finder flags 0. The header then **stops**: there is no room for the
checksums at +48, `info2` at +52 or the delta distances at +54, and the
file is `48 + 1697 + 97 = 1842` bytes exactly.

Three things follow, and each was an open question this document asked:

- **The magic long is a magic word and a length.** `0xABCD0054` is
  `0xABCD` and 84. The 1990 expander's own validator, read out of its
  `CCOD` resource, refuses a word other than `0xABCD` and then requires
  the size at +2 to be **≥ 48** — a forward-compatible test, which is
  what a version that expected the header to grow would write.
- **The header trailer is 3.x's, not the format's.** Nothing follows
  the two forks: the 1990 file has no copy of its own header. So the
  63-of-66 count above is a fact about the generation this corpus is
  made of.
- **The file is stamped `ZIVM`/`LZIV`.** Not `DD01`, which is what a
  search for the meaning of that type code would have hoped for; `DD01`
  and `DD02` stay unexplained, and the 1990 INIT's own `BNDL` declares
  no file types at all beyond its own `INIT`.

And one that was not asked. **`info1` is a version byte and the XOR
garbling is gated on it.** The 1990 file reads `0x1f` and its data fork
begins `1f 9d 90` — `compress(1)`'s own magic, in clear. The same
subject through DiskDoubler 3.7 reads `info1 == 0x2a` and begins
`45 c7 ca`, which is those three bytes XORed with `0x5a`. Until now
every specimen here read `0x2a`, so the un-garbled branch of the rule in
*The XOR garbling* had never been seen at all.

**Graded against the bytes DiskDoubler was given**, which is the oracle
`--verify-combine` and `nowcompress.py` use, because `unar` answers
"format not recognized" for one of these and no other reader exists.
`diskdoubler.py --beta-verify` decodes the specimen twice:

- **as it is.** Since 2026-09-22 `src/fmt_dd.c` reads the size word, so
  a 48-byte header is a shape this engine knows and the file goes in
  untouched — sniffed, listed as `TEXT`/`ttxt` with both fork lengths,
  and both forks byte-exact.
- **rewritten with an 84-byte header**, the two forks' checksums written
  where an 84-byte header keeps them. This is what established the claim
  before any of it was implemented, and it is the stronger statement:
  the forks come back byte-exact THROUGH a checksum this file did not
  compute — the sums are taken from the INPUT, and `0xd766` and `0x116a`
  are the two DiskDoubler 3.7 itself stored for the same forks.

The two compressors also agree on length to the byte, 1,697 and 97 from
the same input, which is the LZW behaving identically either side of the
XOR.

**What this engine accepts is the two sizes that have a specimen**, 48
and 84, each as a whole 32-bit constant. ß05's validator accepts any
size from 48 up, which is the evidence that the field IS a size; a
reader that acted on the whole range would be guessing what a third
value puts in the bytes between, and there is nothing to guess from.
Cost on a 1 MB Mac Plus: **64 B**, 48 of code and 16 of A5
(DECISIONS.md 2026-09-22, *the header that was a length*).

### Which forks use method 10's second form, and how that is known

**The container says, and the coder agrees without being told.** A
method 10 fork is sometimes a stream of increments rather than of
bytes: what the coder emits has to be integrated, byte by byte, against
the byte `distance` back (`docs/formats/diskdoubler-dd.md`, *The second
form*). Which forks those are is not in the stream — it is the two
fields at +54 and +56.

`tools/derive_ddc.py` reads those fields and names two forks:

    derived-Terrainman_2.0__.sea :: Terrainman 2.0 ƒ/Pictures to try/Bloop! data
    derived-Terrainman_2.0__.sea :: Terrainman 2.0 ƒ/Pictures to try/Gnarly cove data

`tools/derive_dd.py` has no container parser at all — it finds blocks
by the checksum a DD block header carries — so it tries both forms and
reports which one reproduced the oracle's sha256. It names **the same
two forks and no others**, out of 39.

That is the one thing the inventory said this container was needed for,
measured from both sides: a field read without decoding, and a decoding
done without reading the field.

### The XOR garbling

Methods 1 to 5 may be written with every byte XORed by `0x5a` — the
three header bytes at +20, +21 and +22 included. It is on when `info1`
has reached `0x2a` and `info2`'s high bit is clear.

**Both branches now have a specimen, since 2026-09-22.** Every file in
this corpus reads `info1 == 0x2a` and is garbled; the one DiskDoubler
ß05 wrote reads `0x1f` and is not, and its data fork begins with
`compress(1)`'s `1f 9d 90` in clear where 3.7's begins `45 c7 ca`
(*The header size, and the 1990 header*). So `info1` is a version byte
that varies, which is what the threshold is testing. The `>=` is still
a rule no fixture distinguishes from `==` — 0x1f fails both — and this
document says so rather than choosing.

## `DDAR` — DiskDoubler 3.x and 4.x

`DDAR`, 74 more bytes of archive header this reader does not
interpret, then one **124-byte record per entry**, each with its own
`DDAR` magic.

**The body begins at 78.** Pinned: in all 7 archives the first `DDAR`
past byte 4 is at exactly that offset. **The archive header's last two
bytes, +76, are a CRC-16/XMODEM of its first 76**, measured 2026-10-23:
7 archives of 7, which is what the sniffer tests.

| offset | size | field | how it is pinned |
|---|---|---|---|
| 0 | 4 | `DDAR` | every record has it, and the walk lands on one every time |
| 8 | 64 | the name, a Str63 | **pinned**: one offset agrees over 36 entries — the length byte at +8, the bytes at +9 |
| 72 | 1 | starts a folder | **measured 2026-09-22** on an archive DiskDoubler 3.7's Combine command wrote here from a known tree (below) |
| 73 | 1 | ends a folder | as +72. The closing record is a COPY of the record before it with this byte set, name and all, so a reader must test it BEFORE it treats the record as an entry |
| 74 | 4 | **the stored file's data fork length** | **measured**: stepping `record + 124 + this + (+78)` walks all 8 corpus archives and both Combine specimens from the first record to the last byte, exactly. For a file DiskDoubler compressed, the data fork IS the compressed file, so this is 84 + both compressed forks, plus 84 again where that file carries its header trailer |
| 78 | 4 | **the stored file's resource fork length**, its bytes after the data fork's | **measured 2026-10-25**: 6,374 on the one record that is not a compressed file, Symantec's `APPL/DSEA` self-extractor in `im2-DD3.7.7AuxFiles.dd`, whose resource fork DD Expand 3.7.7 writes back (equal with the reserved header masked); 0 on the 43 compressed files, which keep no resource fork (DECISIONS.md 2026-10-25, *the archive Symantec shipped*) |
| 82 | 4 | creation date | **measured 2026-10-25**: what DD Expand 3.7.7 writes, on all eight files of `im2-DD3.7.7AuxFiles.dd` |
| 86 | 4 | modification date | as +82 |
| 90 | 4 | the STORED file's type; a folder's `frRect` | the entry's own only where DiskDoubler did not compress the file — see below. On a folder record +90..105 is the `DInfo` whole (`frRect`, `frFlags`, `frLocation`, `frView`), **measured 2026-10-25** against the catalog DD Expand 3.7.7 wrote |
| 94 | 4 | the stored file's creator | `DDAP` on all 43 compressed files here, so **creator `DDAP` is what is expanded**; a record of any other creator is a file stored as it was, both forks raw at +124 (measured 2026-10-25) |
| 98 | 2 | the stored file's Finder flags; XADMaster and macutils say `0x20` means the forks follow raw | the `0x20` reading has **no specimen**: the self-extractor stored raw has `0x2100` |
| 100 | 4 | a file's `fdLocation` | **measured 2026-10-25**: eight of eight equal to what DD Expand 3.7.7 writes; +104..117 are zero in every record and the Mac writes `fdFldr` zero |
| 106 | 4 | a folder's `frScroll`, the `DXInfo`'s first four bytes | **measured 2026-10-25**; the Mac writes the rest of the `DXInfo` zero |
| 118 | 2 | data fork checksum | **no specimen** |
| 120 | 2 | resource fork checksum | **no specimen** |
| 124 | | a compressed file header, or the raw forks | |

**The type at +90 is the STORED file's.** In
`derived-MAZv143.sea` the record reads `DDF1`/`DDAP` where the oracle
says the entry is a `cdev` by `NaOH` — so what the record carries is
the *compressed* file's type and creator, and the entry's own come from
the file header at +124. The record is the stored file's catalog entry,
and Combine stores a file as it sits on the disk: compressed where
DiskDoubler compressed it, and as it was where it did not. Symantec's own
`DD Expand™.sea`, an `APPL/DSEA` whose data fork happens to begin with a
compressed-file header too, is written back by DD Expand 3.7.7 as that
self-extractor, not expanded (DECISIONS.md 2026-10-25, *the archive Symantec shipped*). That is why the `--grid` search pins type and
creator inside the file header and finds nothing for them in the
record.

**An archive ends where the FILE ends.** There is no end marker. What
looks like a stray 84-byte header before some records is the previous
entry's header trailer, inside its span rather than beside it (*The
header is written twice*); walking by +74 and +78 lands on a record
or on the last byte, and on nothing else, in all ten archives here.
Walking by +74 alone, as this reader and XADMaster both did until
2026-10-25, stops at the stored record's raw resource fork and calls the
archive corrupt (DECISIONS.md 2026-10-25, *the archive Symantec shipped*).

### The folder records, measured

**No corpus fixture has one.** All 36 entries in the corpus's 7 `DDAR`
archives are files, at the top level. So on 2026-09-22 two archives
were made: `tools/vmac/diskdoubler.py --combine` builds a volume with a
known tree on it, drives **DiskDoubler 3.7's own Combine command**
under Mini vMac, and reads the archive back.

    Payload/Nest/One      800 B of text
    Payload/Nest/Two      800 B of text
    Payload/Raw        24,576 B nothing compresses
    Payload/Forked         18 B of data and a 340-byte resource fork
    Payload/Empty           0 B
    Payload/Already.dd   a file DiskDoubler had already compressed

`--verify-combine` then grades what comes back out of this engine
against **the bytes DiskDoubler was given** — the oracle is the
encoder's input, the same bargain `nowcompress.py` and `sdcompress.py`
make: **7 entries, 0 disagreements**, the folder tree and the two-fork
file included. `unar` reads both archives and agrees.

Two things that reading measures beyond the folder pair itself:

- **the closing record is a copy of the one before it**, name and all,
  with +73 set. A reader that looks at the name first sees the previous
  entry twice.
- **Combine expands a file that was already compressed.** `Already.dd`
  went in as an 1,878-byte `.dd`; the record's file header states the
  ORIGINAL's 11,428-byte data fork and 340-byte resource fork, so
  Combine unpacked it and archived what was inside. It is graded on the
  original's bytes for that reason, not on the `.dd`'s.

### The `0x20` flag, which nothing here has ever set

The Finder-flags word at +98 is said — by both readers below — to mean
"the forks follow this record raw, with no file header" when `0x20` is
set. **It reads 0x0000 in all 44 records on this disk**, the corpus's
36 and the eight Combine wrote, and five shapes were offered to
DiskDoubler 3.7 specifically to provoke it: a file nothing compresses,
an empty file, a file with a resource fork, an already-compressed file
and ordinary text. Every one came back with a full compressed-file
header behind its record.

So that rule, and the record's own fork lengths and checksums that only
it would use, are read by **no specimen anywhere here**, and nothing in
this document measures them. They are not one program's opinion either,
which is worth separating from being measured: **two independent
readings state them and agree** — XADMaster's
`XADDiskDoublerParser.m`, which `src/fmt_dd.c` is transcribed from, and
macutils' `macunpack/dd.h`, whose `D_ISDIR 72`, `D_ENDDIR 73`,
`D_DATALENGTH 74`, `D_RSRCLENGTH 78`, `D_FNDRFLAGS 98`, `D_DATACRC 118`
and `D_RSRCCRC 120` are the same offsets under their own names.
Agreement between two readers is evidence about the readers; it is not
a specimen, and this document does not present it as one.

**What would close it:** a `DDAR` archive with the flag set, from any
version that writes one — or a shape of file 3.7 declines that has not
been tried.

**It is not 1.x or 2.x, which is what this said until 2026-09-22.**
A 2.x DiskDoubler cannot have written a `DDAR` record of any flags:
`DDExpand 2.03a`'s `BNDL` declares the DiskDoubler file types it opens
— `DD01`, `DDDA`, `DD02`, `DDTM`, `DDSP` — and `DDAR` is not among
them, nor does the string occur anywhere in its 65,212-byte resource
fork, where DDExpand 3.1 declares those five plus `DDAR`, `DDTD`,
`DDCR` and `DDF0`–`DDF5` and holds the literal nine times. A version's
own expander not knowing the type is the version not writing it. Both
applications are on Macintosh Garden's `apps/disk-doubler` page
(`DiskDoubler2.03.sit`, md5 `6e7f2f7ff30d65d0b94efbb17f5716df`;
`DiskDoublerExpand3.sit`, md5 `e03d87b317f7ee638057c3315f715dea`),
which is also where **DiskDoubler ß05, Copyright 1990 Salient** is —
the oldest DiskDoubler reachable, an INIT whose Finder menu reads
`Compress Selection;Expand Selection;(-;About DiskDoubler`, with no
Combine and no `DDAR` in it either. **It has since been run**
(*The header size, and the 1990 header*): the menu is those three items
on the screen as well as in the resource fork, so it writes single
compressed files and nothing else, and this row cannot be closed by
anything older than the 3.x it already has.

## `DDA2` — DiskDoubler Pro

`DDA2`, 58 more bytes of archive header this reader does not
interpret, then **variable-length records**, each stating its own total
size, ending at a record whose type word is `0xBBBB`.

**The body begins at 62.** Pinned: in all 18 archives the first `DDA2`
past byte 4 is at exactly that offset.

| offset | size | field | how it is pinned |
|---|---|---|---|
| 0 | 4 | `DDA2` | every record, and the walk lands on one every time |
| 4 | 2 | record type: `0x8000` a folder, `0x1000` the forks follow raw, `0xBBBB` the end | the walk over 142 records, and the shapes below |
| 6 | 32 | the name, a Str63 | **pinned**: one offset agrees over 142 entries |
| 38 | 4 | folder depth, plus 2 | the paths: 19 folders and 123 files in 18 archives come out where the oracle puts them, and a depth read anywhere else derails the tree at once |
| 42 | 4 | the record's total size | the walk: it is what says where the next record is, over 142 of them |

**The record is 46 bytes common and then depends on its type**, which
is why the dates below are not in the table above: at +56 a file record
has a compressed file header, and a folder record has a date.

A **file** record: a compressed file header at **+56**, its magic there
in all 93.

A **folder** record: creation at **+54**, modification at **+58**.

A record of type `0x1000` carries the file itself instead of pointing
at a header:

| offset | size | field | how it is pinned |
|---|---|---|---|
| 54 | 4 | creation date | `tools/vmac/ndd.py --dates`, 2026-08-21, which is also what pins the ORDER: two subjects stamped with a 1990 creation and a 1995 modification read 1990 here |
| 58 | 4 | modification date | as +54 |
| 62 | 4 | type | no manifest records one for these 30 |
| 66 | 4 | creator | as +62 |
| 70 | 2 | Finder flags | — |
| 78 | 4 | data fork length | **pinned**: one offset agrees over 30 records |
| 82 | 4 | resource fork length | **not pinned, and the reason is the point**: 27 offsets survive, because this value is **0 in all 30**. DiskDoubler Pro writes this record only for a file whose data fork is stored AND which has no resource fork — measured on the application, 2026-08-21 (DECISIONS.md, *the Symantec release*) — so the corpus cannot tell the field from a constant, and neither can this document |
| 86 | 1 | data fork checksum | the decoders check it |
| 87 | 1 | where a resource fork's checksum would go | 0 in all 30, and never compared, for the reason above |
| 90 | | the two forks, raw | |

**A folder deepens the path but not the level counter.** The depth at
+38 counts files, so a folder's own record states the depth its
CONTENTS will state. Read the other way, the tree inverts on the first
nested folder; the 19 folders here are what says which.

**A depth below zero is the archive's own bookkeeping** and is stepped
over by its stated size. `derive_ddc.py` does that and the paths come
out; treating such a record as an entry puts a name in the listing the
oracle does not have.

**An archive normally says where it ends**, with a `0xBBBB` record.
`derived-DD_Expand.sea` does not: it stops 38 bytes after its last
entry, and `unar` reads it. So a walk that arrives with fewer than 46
bytes left is at the end of an archive, and one sent past the end of
the file is not — which is a distinction this format cannot make
inside one 46-byte window, and `src/fmt_dd.c` says so where it matters
(OPEN_ITEMS.md, *Limits of the formats themselves*).

## What this document does NOT describe

- **The archive headers**, 74 bytes of `DDAR` and 58 of `DDA2`. Nothing
  here reads them and nothing here needs to: the first record's magic
  is what locates the body, and `--grid` pins that.
- **Dates**, beyond which of the pair is which. No manifest records a
  date, so the only evidence for the two offsets is `ndd.py --dates`,
  on `DDA2`.
- **Finder flags**, except `DDAR`'s `0x20`, which no fixture sets.
- **`DDAR`'s `0x20` raw-fork records**, for want of a specimen: see
  above. The folder records are no longer on this list — they were
  measured on 2026-09-22 against an archive DiskDoubler wrote here.
- **Methods 2, 3, 4 and 5's own headers.** `src/fmt_dd.c` decodes 3, 4
  and 5 against forks DiskDoubler's own expander reads back
  (DECISIONS.md 2026-08-21) and the three specimens here are this
  project's; the container work above treats them like any other
  method byte.
