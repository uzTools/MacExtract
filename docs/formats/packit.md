# PackIt's container

**The inventory said PackIt's container could come only from macutils'
`macunpack/pit.c`**, on the grounds that "PackIt's own format is
trivial; the app is not here". Both halves were beside the point. The
format is published, in a 1986 freeware manual that describes it field
by field, and `tools/fetch_references.sh` fetches it since 2026-09-21:

    reference/notes/packit_unpackit.txt

That is R. Scott McGinnis's `UNPACKIT.DOC`, appendices B and C — the
documentation of a DOS extractor, written by somebody who was neither
Harry Chesley nor one of the Unix implementers. **What named it was
`reference/notes/PackIt.md`**, a page this project had fetched with
the very first batch of references and never read past the first
screen; its *Specifications* section lists that document, and
macutils' own `doc/README.unpit`, which describes the same layout and
which was sitting in `reference/macutils/` all along.

`tools/derive_packit.py` is a reader written from the appendices and
from this project's own `docs/formats/serialized-huffman-tree.md`, and
it reads **all 38 forks of the corpus's four PackIt archives** byte
for byte against the sha256 an independent oracle recorded.

## What the appendices give

**Appendix B — the file.** A concatenated series of subfiles, each
opening with a four-byte type word, ending with `PEnd`:

| word | means |
|---|---|
| `PMag` | stored |
| `PMa4` | Huffman-coded |
| `PMa5` | Huffman-coded and simply encrypted |
| `PEnd` | end of file |

**Appendix C — the subfile.** A header, the data fork, the resource
fork, and a two-byte CRC over the forks. The header is 94 bytes:

| at | size | field |
|---|---|---|
| 0 | 1 | length of the name, 1..63 |
| 1 | 63 | the name |
| 64 | 4 | type |
| 68 | 4 | creator |
| 72 | 1 | Finder flags |
| 73 | 1 | filler, for word alignment |
| 74 | 2 | locked if nonzero |
| 76 | 4 | data fork length |
| 80 | 4 | resource fork length |
| 84 | 4 | created, seconds since 1 January 1904 |
| 88 | 4 | modified |
| 92 | 2 | CRC of the header |

and appendix C states the fact this project had to measure on
2026-09-20 to believe: **for a compressed subfile the header is coded
along with the forks**, "therefore the entire subfile must be
uncompressed in order to get to the next subfile".

## The corrections

**1. The name field is fixed, not counted.** The appendix gives
"NameLen 1, Name 63" and lists no padding, which reads as a
variable-length name. It is 63 bytes whatever the length byte says;
a reader that advances by the count walks off by the difference on
every entry.

**2. There is no MacBinary header.** Appendix B says a PackIt file
begins with one — appendix A even lays it out. That is how a `.pit`
crossed a modem in 1986, not part of the format: four of the corpus's
five specimens begin at the first type word, and the one that does
carry an envelope is named `.bin` here for exactly that reason.

**3. The type table lists `PMa5` twice**, for simple encryption and
for DES. One of them is presumably `PMa6`. Neither appears in the
corpus, so nothing here can say which — and the reader refuses both.

**4. The compression is named and not described.** "huffman encoded"
is the whole of it. The tree is
`docs/formats/serialized-huffman-tree.md`, this project's own
description, derived from the output of the three formats that write
one.

## What this does NOT cover

- **Either encrypted form.** No specimen, and the document describes
  neither.
- **The CRCs.** The appendix names both — one over the header, one
  over the forks — and says nothing about the polynomial. The reader
  does not check them, so nothing here confirms which CRC it is.
- **PackIt I.** The document says unPACKIT is "compatible with PACKIT
  I and II", and PackIt I "simply stored files together". Whether
  that older file differs in any way the corpus cannot say: every
  specimen here is `PMag` or `PMa4`.
