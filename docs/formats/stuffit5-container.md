# The StuffIt 5 container

**The inventory row for `fmt_sit5.c` said the container parser was
XADMaster's, and that "Russotto's write-up describes the SIT5 container
too".** It does not. `reference/notes/arsenic_russotto.md` is method 15
from start to finish — the arithmetic coder, the models, the block
sort — and the only "header" in it is the Arsenic stream's own.

The description that does exist was one page away from a file this
project already had. `reference/notes/StuffIt.md`, the wiki page method
13 was read out of, lists it under *Sources*; it lives on the same wiki
as the eight pages `tools/fetch_references.sh` already fetches, and it
is fetched now:

    reference/notes/sit5_specs_theunarchiver.md      (StuffIt5Format)

`tools/derive_sit5.py` is a reader written from that page alone. It
reads **all 31 StuffIt 5 fixtures — 525 entries** — and agrees with the
oracle manifests on every entry's PATH and on both forks' lengths, with
**0 disagreements**. The path is the part worth saying: nothing in the
container stores one, so a path is the tree the parent-offset chain
makes, and comparing it against `unar`'s is what tests the tree rather
than the record.

## What the page gives

**The archive header**: an 80-byte banner whose four year digits vary,
then a version byte that is 5, a flags byte, the archive's total size,
the number of entries in the root, and the offset of the first entry.

**The entry header**, at every entry offset: the identifier
`0xa5a5a5a5`, an entry version, the header size, a flags byte, two Mac
OS dates, the offsets of the previous, next and parent entries, the
name length and a header CRC. Then, for a file, both data-fork lengths,
its CRC and its method, a password-data length and that much password
data, the name, and a comment. For a folder, the same head followed by
the offset of its first entry, the size of the directory and the number
of files.

**The second file header**, which follows a file's header: a flags word
whose bit 0 says a resource fork is present, the type and creator, the
Finder flags, and then — only if that bit is set — the resource fork's
two lengths, its CRC and its method. **One four-byte field in the
middle of it is "not included in version 3, included in version 1"**,
which is why the page gives two columns of offsets and why the reader
branches on the entry version.

**The flag bits** (5 encrypted, 6 folder), **the folder marker** (a
folder entry whose data-fork length field is `0xffffffff` is ignored),
**the fork order** (resource first, then data) and **the CRC**
(CCITT 0x1021, no pre- or post-conditioning).

## The correction it needs

**The archive-header table gives offset 84 twice** — once for "Total
size of archive" and once for "Offset of first entry header" — and then
jumps to 86. Two fields cannot share an offset, and following the
second of them lands the walk inside the banner's own trailer. The
entry count is a `u16` at **92** and the first entry's offset a `u32`
at **94**; that reads all 31 archives here, and Maconv's copy of the
same table (linked from the same *Sources* list) gives 092 and 094.

**And one thing it does not say**: a file's comment fields are inside
the header, so a header that ends at its own `header size` has no
comment. Without that, a folder's "Unknown data until next entry" is
read as a comment length.

## What is still nobody else's

**The ENCRYPTED archive, both halves.** When bit 7 of the archive flags
byte is set, a five-byte hash — the thing that says whether a password
is the right one — sits after the fixed header, behind two optional
blocks whose presence is flagged by bits 4 and 5 of the same byte; and
the archive key is MD5 of the password cut to five bytes, with the
header holding MD5 of THAT, also cut to five. The page says only
"Encrypted (algorithm used is unknown)".

**All of that is measured** — bit 7, bit 4's fourteen bytes, bit 5's
four, the MD5-of-MD5 hash, and the ORDER of the hash and the comment
block — against three archives DropStuff 5.0.1 wrote, one StuffIt Deluxe
5.5 ships inside its own installer, and two StuffIt Deluxe 7.0.3 wrote
by Apple event, with no engine and no reference in the loop
(`tools/derive_sit5crypt.py`; FORMATS.md, *StuffIt 5's RC4* and *StuffIt
5's archive flag byte, and what bit 5 is*). Bit 6 is still
`XADStuffIt5Parser.m`'s alone: nothing here sets it.
