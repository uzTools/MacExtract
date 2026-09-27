# The LZH/LHA header, from the format's own document

**The inventory row for `fmt_lzh.c` said its header walk came from
`XADLZHParser.m`.** The decoders left for lhasa on 2026-09-19; the walk
is described by the format's own publication, and that document has
been in this tree since the first reference fetch:

    reference/lha/header.doc.euc

Masaru Oki's `header.doc`, dated 2 March 1992 and shipped with LHa for
UNIX, in EUC-JP. It gives levels 0, 1 and 2 field by field, the
extended-header types, the OS IDs and the method IDs; its section B is
credited to Haruyasu Yoshizaki's `lhx.doc`, and a later section by
Nobutaka Watazaki adds the UNIX-dependent extended headers.

`tools/derive_lzh.py` is a reader written from that document and from
lhasa for the four things it does not cover. It walks **156 archives
and 191 entries** — this project's 7 `.lzh` fixtures, lhasa's own test
collection from 20 writers, and LHa for UNIX's — with **0
disagreements** against lhasa's listing of the same files, and it
refuses the one file lhasa's suite ships truncated.

## The base header (section A)

The document gives the three levels as a column of field widths. Read
as offsets from the start of the header:

| at | level 0 | level 1 | level 2 |
|---|---|---|---|
| 0 | 1 header size | 1 header size | 2 total header size |
| 1 | 1 header sum | 1 header sum | — |
| 2 | 5 method ID | 5 method ID | 5 method ID |
| 7 | 4 packed size | 4 **skip size** | 4 packed size |
| 11 | 4 original size | 4 original size | 4 original size |
| 15 | 2 time + 2 date | 2 time + 2 date | 4 time (UNIX) |
| 19 | 1 attribute | 1 `0x20` | 1 reserved |
| 20 | 1 level `0x00` | 1 level `0x01` | 1 level `0x02` |
| 21 | 1 name length | 1 name length | 2 file CRC |
| 22 | ? pathname | ? filename | — |
| 22+n | 2 file CRC | 2 file CRC | 1 OS ID |
| 24+n | (extended area) | 1 OS ID | 2 next-header size |
| 25+n | — | 2 next-header size | — |

Everything this engine reads is in that table. `header size` is the
size **minus two** at level 0/1 — the document's total of "24 + ?"
for a zero-length name is that byte plus 2 — and the whole header at
level 2.

**"Skip size" is the level-1 quirk, and the document names it.** A
level 1 header's size field at offset 7 counts its extended headers as
well as the compressed data, so each extended header read moves the
data start along and shortens the stream by its own length. lhasa
makes the same subtraction (`read_l1_extended_headers`); the word in
the table is the published statement of it.

**The header sum** (level 0/1, offset 1) is the low byte of the sum of
everything from offset 2 to the end of the header. lhasa checks it
(`check_l0_checksum`); `fmt_lzh.c` does not, because nothing follows
from it — every entry carries a CRC-16 over its decoded bytes and that
is enforced per entry. `derive_lzh.py` computes it on every level 0/1
header here and reports a mismatch: **0 across 140 of them.**

## The extended headers (section B)

Each is `1 ext-type`, its payload, then `2 next-header size` — so the
size word read at a chain position is of the header that follows, and
a zero ends the chain. The document lists:

| type | what |
|---|---|
| `0x00` | common (header CRC) |
| `0x01` | filename |
| `0x02` | dirname |
| `0x3f` | comment |
| `0x50`–`0x54` | UNIX permission, GID/UID, group name, user name, mtime |

This engine wants two of them, `0x01` and `0x02`, and steps over the
rest. **A dirname's components are separated by `0xff`**, which the
document does not say and lhasa does (`ext_header_path_decoder`).

Level 2 and 3 keep the whole chain INSIDE the header, so it moves
neither the data offset nor the size; level 1 keeps it outside, which
is what "skip size" is about.

## The four things the document does not cover

Each is lhasa's (ISC), and each is marked **BEYOND THE DOCUMENT** in
`derive_lzh.py` at the line that needs it.

1. **Level 3.** A word-size field at offset 0 that is always 4, a
   32-bit total header size at offset 24, the chain from offset 28
   with 32-bit sizes. `lha_file_header.c`, `decode_level3_header`.
   7 entries here.
2. **LHA for OS-9/68k 2.01 writes its level 2 header size two bytes
   short** — it stores the length of the REST of the header. The OS ID
   `'K'` identifies those archives. `decode_level2_header`.
   XADMaster does not compensate, which is why `unar` fails all three
   of lhasa's `lha_osk_201` level 2 archives.
3. **`-lhd-` is a directory**, which section A.b's list of method IDs
   does not mention. 34 entries here.
4. **LHArk 0.4d writes `-lh7-` over an algorithm of its own** and
   marks itself with a space as the OS ID; lhasa calls it `-lk7-` and
   decodes it separately. `fmt_lzh.c` refuses that combination rather
   than decoding it into rubbish. `lha_reader.c`, `LHA_OS_TYPE_LHARK`.

## What lhasa does that is not the header's

The derivation counts these rather than adopting them, because they
are presentation and safety choices rather than readings of a field —
`unar` makes none of them, and neither does this engine, which
extracts the archive's own bytes.

- **`fix_msdos_allcaps`** lower-cases a name with no lower-case
  character in it at all. **41 names here.**
- **`collapse_path`** removes `.` and `..` components, so
  `regression/dotdot.lzh`'s `foo/../../evil2.txt` lists as
  `evil2.txt`.
- **The listing replaces a byte it will not send to a terminal**
  (`regression/badterm.lzh` is an archive whose entry name is an xterm
  title-setting escape sequence).
- **An entry with no filename is dropped from the listing.** LHa for
  UNIX 1.14i writes level 0 directory entries whose name length is 0,
  and lhasa's `-l` reports `h0_subdir.lzh` — two of those and one real
  file — as "0 files". `unar` lists three entries there, this engine
  lists the file. 2 archives here.

## The NUL in a level 0/1 name, which both readers stop at

`fmt_lzh.c` ends a level 0/1 name at the first NUL inside the name
field and drops what follows. **Both references yield that same name**,
which this section denied until 2026-09-27 by saying lhasa "takes the
whole field":

- **XADMaster** stops there explicitly and keeps the remainder as
  `XADCommentKey` (`XADLZHParser.m`).
- **lhasa** stops there implicitly. `process_level0_path()` copies the
  whole field and NUL-terminates it — that `memcpy` is what the old
  reading was taken from — but every consumer then handles it as a C
  string: `strrchr` in `split_header_filename`, `strdup`, and
  `strlen`/`sprintf` in `lha_file_header_full_path`. Anything past an
  embedded NUL is unreachable.

They differ only in whether the trailing bytes surface as a COMMENT,
and this engine has nowhere to put one. The document states no comment
in that field, and lhasa's level-0 comment support is in the extended
AREA (`process_level0_extended_area`, for PMarc).

**It has no specimen either way: 0 of the 140 level 0/1 name fields in
the 156 archives here contains a NUL**, so nothing forces the question
— which is why the disagreement went five days without being checked
against what either reader actually yields (BLOCKERS.md, *Withdrawn
claims*).
