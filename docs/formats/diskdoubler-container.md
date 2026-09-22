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

| offset | size | field | how it is pinned |
|---|---|---|---|
| 0 | 4 | magic `0xABCD0054` | the sniffer's, and 66 files begin with it |
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
| 40 | 2 | Finder flags | not pinned — no manifest records them |
| 48 | 2 | data fork checksum | the decoders check it: `src/fmt_dd.c` fails an entry whose sum disagrees, over the whole corpus |
| 50 | 2 | resource fork checksum | as +48 |
| 52 | 1 | `info2` | the XOR garbling, below |
| 54 | 2 | data fork delta distance | **held against the coder**, below |
| 56 | 2 | resource fork delta distance | as +54 |
| 84 | | the data fork's bytes, then the resource fork's | |

**The compressed file carries no name.** It is the host's file that has
one — DiskDoubler appended `.dd` to it — so nothing in this document
says what an entry is called, and `derive_ddc.py` grades a compressed
file on everything else.

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
has reached `0x2a` and `info2`'s high bit is clear. **Every specimen
here reads `info1 == 0x2a` exactly**, so the `>=` is a rule no fixture
distinguishes from `==`, and this document says so rather than
choosing.

## `DDAR` — DiskDoubler 3.x and 4.x

`DDAR`, 74 more bytes of archive header this reader does not
interpret, then one **124-byte record per entry**, each with its own
`DDAR` magic.

**The body begins at 78.** Pinned: in all 7 archives the first `DDAR`
past byte 4 is at exactly that offset.

| offset | size | field | how it is pinned |
|---|---|---|---|
| 0 | 4 | `DDAR` | every record has it, and the walk lands on one every time |
| 8 | 64 | the name, a Str63 | **pinned**: one offset agrees over 36 entries — the length byte at +8, the bytes at +9 |
| 72 | 1 | starts a folder | **no specimen** — see below |
| 73 | 1 | ends a folder | **no specimen** |
| 74 | 4 | data fork length | **no specimen**: only a record that carries the forks itself states them, and no `DDAR` fixture here does |
| 78 | 4 | resource fork length | **no specimen** |
| 82 | 4 | creation date | no manifest records a date |
| 86 | 4 | modification date | as +82 |
| 90 | 4 | type | **not the entry's** — see below |
| 94 | 2 | Finder flags, whose `0x20` says the forks follow raw | **no specimen** |
| 118 | 2 | data fork checksum | **no specimen** |
| 120 | 2 | resource fork checksum | **no specimen** |
| 124 | | a compressed file header, or the raw forks | |

**The type at +90 is not the entry's type.** In
`derived-MAZv143.sea` the record reads `DDF1`/`DDAP` where the oracle
says the entry is a `cdev` by `NaOH` — so what the record carries is
the *compressed* file's type and creator, and the entry's own come from
the file header at +124. That is why the `--grid` search pins type and
creator inside the file header and finds nothing for them in the
record.

**An archive ends where the FILE ends.** There is no end marker. Five
of the seven archives here end with a stray compressed-file header
belonging to no entry, 84 bytes long; stepping over it is the only
reading under which those five end exactly at their last byte, which is
what `derive_ddc.py` asserts.

**What no `DDAR` fixture here reaches, and whose statement those rows
are.** All 36 entries in the 7 archives are files with a full file
header. **None is a folder, and none has the `0x20` flag** that says
the forks follow the record raw. So the folder pair at +72 and +73, the
record's own fork lengths at +74 and +78, its checksums at +118 and
+120 and the `0x20` flag itself are read by **no specimen in this
corpus**, and nothing in this document measures them.

They are not one program's opinion either, which is worth separating
from being measured: **two independent readings state them and agree**
— XADMaster's `XADDiskDoublerParser.m`, which `src/fmt_dd.c` is
transcribed from, and macutils' `macunpack/dd.h`, whose `D_ISDIR 72`,
`D_ENDDIR 73`, `D_DATALENGTH 74`, `D_RSRCLENGTH 78`, `D_FNDRFLAGS 98`,
`D_DATACRC 118` and `D_RSRCCRC 120` are the same offsets under their
own names. Agreement between two readers is evidence about the
readers; it is not a specimen, and this document does not present it as
one.

**What would close it:** an archive with a folder in it, and one
holding a file the application refuses to compress. DiskDoubler 3.7
runs here — `tools/vmac/diskdoubler.py` drives it — and its Combine
command is what writes a `DDAR`; two specimens would turn these six
rows into measured ones the same afternoon.

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
- **The `DDAR` folder records and its raw-fork records**, for want of a
  specimen: see the table above.
- **Methods 2, 3, 4 and 5's own headers.** `src/fmt_dd.c` decodes 3, 4
  and 5 against forks DiskDoubler's own expander reads back
  (DECISIONS.md 2026-08-21) and the three specimens here are this
  project's; the container work above treats them like any other
  method byte.
