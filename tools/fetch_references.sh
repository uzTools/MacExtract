#!/bin/sh
# fetch_references.sh — repopulate the read-only reference/ directory.
# reference/ is never committed; this script documents its provenance.
set -e
cd "$(dirname "$0")/.."
mkdir -p reference/notes

[ -d reference/XADMaster ] || \
    git clone --depth 1 https://github.com/MacPaw/XADMaster reference/XADMaster

# btoa 5.2.1 (Paul Rutter, Joe Orost & Stefan Parmark, 1996) — the only
# implementation of the format there is, and the one `atob.c` this
# project's src/fmt_btoa.c is transcribed from. Debian carried it in
# non-free until woody; archive.debian.org still has the tarball.
if [ ! -d reference/btoa ]; then
    mkdir -p reference/btoa
    curl -sL -o /tmp/btoa.tar.gz \
        "http://archive.debian.org/debian/pool/non-free/b/btoa/btoa_5.2.1.orig.tar.gz"
    tar xzf /tmp/btoa.tar.gz -C reference/btoa --strip-components=1
    rm -f /tmp/btoa.tar.gz
fi

# LHa for UNIX 1.14i (Yoshizaki/Oki/Watazaki/Okamoto) — the ORIGINAL
# LHA implementation, and the only encoder for the format this project
# can reach. Debian carried it in non-free until sarge.
if [ ! -d reference/lha ]; then
    mkdir -p reference/lha
    curl -sL -o /tmp/lha.tar.gz \
        "http://archive.debian.org/debian/pool/non-free/l/lha/lha_1.14i.orig.tar.gz"
    tar xzf /tmp/lha.tar.gz -C reference/lha --strip-components=1
    rm -f /tmp/lha.tar.gz
fi

# lhasa 0.4.0 (Simon Howard) — an INDEPENDENT reading of LZH/LHA, and
# more importantly ~160 test archives written by fourteen different LHA
# implementations, MacLHA 2.24 among them. Those specimens are what
# moved LZH from detect-only into scope (DECISIONS.md 2026-08-23);
# seven of them are fixtures (fixtures/SOURCES.md) and the rest are
# swept by tools/run_lzh.py.
if [ ! -d reference/lhasa ]; then
    mkdir -p reference/lhasa
    curl -sL -o /tmp/lhasa.tar.xz \
        "http://deb.debian.org/debian/pool/main/l/lhasa/lhasa_0.4.0.orig.tar.xz"
    tar xJf /tmp/lhasa.tar.xz -C reference/lhasa --strip-components=1
    rm -f /tmp/lhasa.tar.xz
fi

# deark (Jason Summers) — the SECOND implementation of ARC/PAK method
# 0x0b (Distilled), independent of XADMaster and the only one that gets
# it right: its window starts full of spaces, XADMaster's starts at zero
# (DECISIONS.md). Also the reading src/fmt_arc.c follows for that method.
[ -d reference/deark ] || \
    git clone --depth 1 https://github.com/jsummers/deark reference/deark

# mpack/munpack 1.6 (John G. Myers, Carnegie Mellon University) — the
# reference for MIME (src/fmt_mime.c) and, built by tools/build_mpack.sh,
# the second implementation that suite grades against. Its tree carries
# the MACINTOSH port as well (macfile.c, macos.c, README.mac), which is
# where multipart/appledouble came from in the first place: the CMU
# licence is permissive, so unlike btoa this one may be transcribed.
# ftp.andrew.cmu.edu is long gone; Debian still ships the same tarball.
if [ ! -d reference/mpack ]; then
    mkdir -p reference/mpack
    curl -sL -o /tmp/mpack.tar.gz \
        "http://deb.debian.org/debian/pool/main/m/mpack/mpack_1.6.orig.tar.gz"
    tar xzf /tmp/mpack.tar.gz -C reference/mpack --strip-components=1
    rm -f /tmp/mpack.tar.gz
fi

if [ ! -d reference/macutils ]; then
    mkdir -p reference/macutils
    curl -sL -o /tmp/macutils.tar.gz \
        "http://deb.debian.org/debian/pool/main/m/macutils/macutils_2.0b3.orig.tar.gz"
    tar xzf /tmp/macutils.tar.gz -C reference/macutils --strip-components=1
    rm /tmp/macutils.tar.gz
fi

# NOT `cd reference/notes`, which is what these blocks used to open with.
# Every block BELOW them names its file from the repository root, so the
# cd made all of those write into reference/notes/reference/notes/ — a
# directory that does not exist, so `set -e` killed the script at the
# zstd fetch and the last six references never arrived on a tree that
# did not already have them. Found 2026-09-09 by running this script on
# a populated tree for the first time in a while; nothing had, because
# every block is guarded by the file it fetches.
for p in StuffIt Compact_Pro PackIt BinHex MacBinary ArcMac; do
    [ -f "reference/notes/$p.md" ] || \
        curl -sL "http://fileformats.archiveteam.org/wiki/$p?action=raw" \
             -o "reference/notes/$p.md"
done
# ArcMac's own specification: the "ArcMac File Structure" section of the
# ARCMAC.DOC that ships with every ArcMac distribution. It is the only place
# that states the byte order of the two fork lengths ("Intel 80xxx byte sex");
# macutils' arc.h gives the offsets and not the order. Text, CR line endings.
if [ ! -f reference/notes/ArcMac.DOC ]; then
    curl -sL "https://www.sac.sk/download/pack/macarc.zip" -o /tmp/macarc.zip
    # 1988 zip, PKWARE-imploded: python3's zipfile cannot read it, unzip can.
    unzip -p /tmp/macarc.zip ARCMAC.DOC | tr '\r' '\n' > reference/notes/ArcMac.DOC
    rm -f /tmp/macarc.zip
fi

# Matthew Russotto's Arsenic (StuffIt method 15) spec; russotto.net may be
# unreachable — fall back to the Wayback Machine and strip the HTML.
if [ ! -f reference/notes/arsenic_russotto.md ]; then
    curl -sL "https://web.archive.org/web/2023/http://www.russotto.net/arseniccomp.html" \
        -o /tmp/arsenic.html
    python3 -c "
import html, re
raw = open('/tmp/arsenic.html').read()
raw = re.sub(r'<script.*?</script>|<style.*?</style>|<!--.*?-->', '', raw, flags=re.S)
text = html.unescape(re.sub(r'<[^>]+>', '', raw))
open('reference/notes/arsenic_russotto.md', 'w').write(re.sub(r'\n{3,}', '\n\n', text))
"
fi

# The two sources for Compact Pro SEGMENTED archives, which nothing in
# reference/ describes: XADMaster reads the three fields involved and
# marks all three "meaning not entirely clear", and macunpack stores one
# of them unused. Neither documents the scheme, so both of these are
# needed before a parser is written (OPEN_ITEMS.md section 4).
#
#   cpt_specs_theunarchiver.md  The Unarchiver's own format wiki, off the
#       Google Code archive the project moved out of. It is the source
#       XADCompactProParser.m was written from, and the place the three
#       unclear fields are named as unclear.
#   cpt_users_guide.txt         Compact Pro User's Guide 1.52 (Bill
#       Goodman, 1998) — the AUTHOR's manual, and the only documentation
#       of what a segmented archive promises: at most 255 segments, names
#       chosen freely because "Compact Pro saves information inside the
#       files to determine their proper ordering", and the FINAL segment
#       is the one you open. https is unusable (the certificate is for
#       another host), so this is fetched over http.
[ -f reference/notes/cpt_specs_theunarchiver.md ] || \
    curl -sL -o reference/notes/cpt_specs_theunarchiver.md \
    "https://storage.googleapis.com/google-code-archive/v2/code.google.com/theunarchiver/wiki/CompactProSpecs.wiki"

# The two pages that page's LAST LINE links to, and which nothing here
# fetched until 2026-09-20 — so the project had a full description of
# Compact Pro's coders one hop away from a file in reference/notes and
# did not have it. Together they document the whole format; what they
# get wrong is written up in docs/formats/compact-pro.md, which is
# what src/fmt_cpt.c cites.
[ -f reference/notes/cpt_lzh_theunarchiver.md ] || \
    curl -sL -o reference/notes/cpt_lzh_theunarchiver.md \
    "https://storage.googleapis.com/google-code-archive/v2/code.google.com/theunarchiver/wiki/CompactProLzhAlgorithm.wiki"
[ -f reference/notes/rle8182_theunarchiver.md ] || \
    curl -sL -o reference/notes/rle8182_theunarchiver.md \
    "https://storage.googleapis.com/google-code-archive/v2/code.google.com/theunarchiver/wiki/Rle8182Algorithm.wiki"

# And the rest of that wiki, which turned out to describe most of the
# Macintosh formats this project had recorded as undocumented. Its
# index is a JSON file — 40 pages, listed at
# .../theunarchiver/wikis.json — and reading it on 2026-09-20 is what
# turned "no description exists" into a fetch for StuffIt method 13,
# DiskDoubler's AD and DD, and the rest below. These are FACTS pages,
# not code; what each one gets wrong is written up in docs/formats/
# where this project has held it against the corpus, and a row that
# has not been held against the corpus says so.
for page_name in \
    "StuffItAlgorithm13:sit13" \
    "StuffItAlgorithm3:sit3" \
    "StuffItSpecs:sit_specs" \
    "StuffItFormat:sit_format" \
    "StuffIt5Format:sit5_format" \
    "StuffItArsenicAlgorithm:sit_arsenic" \
    "DiskDoublerSpecs:dd_specs" \
    "DiskDoublerAdAlgorithm:dd_ad" \
    "DiskDoublerDdAlgorithm:dd_dd" \
    "DiskDoublerAlgorithm2:dd_method2" \
    "Rle90Algorithm:rle90" \
    "LzwAlgorithm:lzw" \
    "MacBinarySpecs:macbinary_specs" ; do
    page=${page_name%%:*}
    name=${page_name##*:}
    [ -f "reference/notes/${name}_theunarchiver.md" ] || \
        curl -sL -o "reference/notes/${name}_theunarchiver.md" \
        "https://storage.googleapis.com/google-code-archive/v2/code.google.com/theunarchiver/wiki/${page}.wiki"
done

if [ ! -f reference/notes/cpt_users_guide.txt ]; then
    curl -sL -o /tmp/cpt_guide.pdf \
        "http://www.applefool.com/se30/files/Compact%20Pro%20User's%20Guide.pdf"
    # No poppler here, and the PDF is plain Flate-compressed text: pull the
    # show-string operands out of each stream and decode them as MacRoman,
    # which is what a 1998 Macintosh authoring tool wrote them in.
    python3 -c "
import re, zlib
d = open('/tmp/cpt_guide.pdf', 'rb').read()
out = []
for m in re.finditer(rb'stream\r?\n', d):
    end = d.find(b'endstream', m.end())
    if end < 0:
        continue
    try:
        s = zlib.decompress(d[m.end():end])
    except Exception:
        continue
    for t in re.finditer(rb'\((?:\\\\.|[^()\\\\])*\)', s):
        b = t.group()[1:-1]
        b = re.sub(rb'\\\\([()\\\\])', rb'\1', b)
        b = re.sub(rb'\\\\([0-7]{1,3})',
                   lambda o: bytes([int(o.group(1), 8) & 0xFF]), b)
        out.append(b.decode('mac_roman'))
    out.append('\n')
open('reference/notes/cpt_users_guide.txt', 'w').write(re.sub(r'\n{3,}', '\n\n', ''.join(out)))
"
    rm -f /tmp/cpt_guide.pdf
fi

# zstd — RFC 8878, the Zstandard frame format. The only reference this
# project needs for it: the frame magic (0xFD2FB528, little-endian) and
# the skippable-frame range 0x184D2A50..5F, both in section 3.1.1/3.1.2.
[ -f reference/notes/zstd_rfc8878.txt ] || \
    curl -sL -o reference/notes/zstd_rfc8878.txt \
        "https://www.rfc-editor.org/rfc/rfc8878.txt"

# DEFLATE — RFC 1951. Section 3.2.2 is the definition of a canonical
# code-length Huffman code and the algorithm that assigns the codes, which
# is what src/unc_huffman.c's unc_canon_build_ext follows. Nothing here
# reads a deflate stream with it — zlib does that — it is the SPEC for a
# code shape five of the Macintosh formats happen to use.
[ -f reference/notes/rfc1951.txt ] || \
    curl -sL -o reference/notes/rfc1951.txt \
        "https://www.rfc-editor.org/rfc/rfc1951.txt"

# puff.c (Mark Adler, zlib licence) — the reference deflate decoder that
# ships in zlib's contrib/. construct() and decode() are the counts-and-
# offsets build and the length walk in src/unc_huffman.c, and construct()
# is also where "an incomplete code is legal, not an error" is written
# down as a contract rather than as a remark about one encoder.
[ -f reference/notes/puff.c ] || \
    curl -sL -o reference/notes/puff.c \
        "https://raw.githubusercontent.com/madler/zlib/v1.3.1/contrib/puff/puff.c"

# brotli — RFC 7932, kept for what it does NOT contain. Section 9.1 is the
# whole stream header: 1 to 7 bits of WBITS and nothing else. There is no
# magic number, no signature, no version byte, so a raw brotli stream
# cannot be identified from its contents by anything (OPEN_ITEMS.md,
# part 1). This file is the evidence for that.
[ -f reference/notes/brotli_rfc7932.txt ] || \
    curl -sL -o reference/notes/brotli_rfc7932.txt \
        "https://www.rfc-editor.org/rfc/rfc7932.txt"

# lrzip (Con Kolivas) — `write_magic` and `get_magic` in lrzip.c are the
# format's header: "LRZI", a major and a minor version byte, in a 24-byte
# MAGIC_LEN block.
if [ ! -d reference/lrzip ]; then
    mkdir -p reference/lrzip
    curl -sL -o /tmp/lrzip.tar.gz \
        "http://deb.debian.org/debian/pool/main/l/lrzip/lrzip_0.660.orig.tar.gz"
    tar xzf /tmp/lrzip.tar.gz -C reference/lrzip --strip-components=1
    rm -f /tmp/lrzip.tar.gz
fi

# wimlib (Eric Biggers) — the only complete reading of Microsoft's WIM
# there is; `include/wimlib/header.h` carries WIM_MAGIC ("MSWIM\0\0\0")
# and WIM_HEADER_DISK_SIZE, which is what corroborates it.
if [ ! -d reference/wimlib ]; then
    mkdir -p reference/wimlib
    curl -sL -o /tmp/wimlib.tar.gz \
        "http://deb.debian.org/debian/pool/main/w/wimlib/wimlib_1.14.5.orig.tar.gz"
    tar xzf /tmp/wimlib.tar.gz -C reference/wimlib --strip-components=1
    rm -f /tmp/wimlib.tar.gz
fi

# libNeoAppleArchive (Snoolie K, MIT) — the only open reading of Apple
# Archive there is, and not a reimplementation of Apple's closed
# libAppleArchive but a from-scratch one. `libNeoAppleArchive_internal.h`
# carries the magics (AAR_MAGIC/YAA_MAGIC and the pbz* set) and
# `neo_aa_header.c` the six-byte header prologue and the closed set of
# field subtypes that corroborate it. Naming only: extraction stays out
# by the brief.
[ -d reference/libNeoAppleArchive ] || \
    git clone --depth 1 https://github.com/0xilis/libNeoAppleArchive \
        reference/libNeoAppleArchive

# CiderPress2 (Andy McFadden, Apache-2.0) — the SECOND reading of DART,
# and the only other one there is: DiskArc/Disk/DART.cs and its
# DART-notes.md, plus DiskArc/Comp/LZHufStream.cs, which is the LZHUF
# DART's "best" method is a dialect of. Everything src/fmt_dart.c does
# not take from Apple's own header comes from here — the RLE's word
# orientation, the 0xFFFF per-chunk fallback, the type/size pairs, and
# the 0x00 window fill.
#
# TestData/dart/ is fetched with it and is what tools/run_dart.py grades
# against: two 800K disks compressed by DART 1.5.3 itself under MAME,
# each in both methods, WITH THE SOURCE IMAGES BESIDE THEM. That is the
# encoder-side ground truth this project usually has to go to an
# emulator for (TESTING.md, *DART*).
if [ ! -d reference/ciderpress2 ]; then
    mkdir -p reference/ciderpress2
    for f in DiskArc/Disk/DART.cs DiskArc/Disk/DART-notes.md \
             DiskArc/Comp/LZHufStream.cs DiskArc/Comp/LZHuf-notes.md \
             TestData/dart/README.md; do
        curl -sL -o "reference/ciderpress2/$(basename "$f")" \
            "https://raw.githubusercontent.com/fadden/CiderPress2/HEAD/$f"
    done
    for z in test1 random_t; do
        curl -sL -o "/tmp/cp2-$z.zip" \
            "https://raw.githubusercontent.com/fadden/CiderPress2/HEAD/TestData/dart/$z.zip"
        unzip -oq "/tmp/cp2-$z.zip" -d reference/ciderpress2
        rm -f "/tmp/cp2-$z.zip"
    done
fi

# The wrapper the two A/UX 3.0.1 floppies travel in. They are the only
# DART archives here that Apple's tool wrote over a disk nobody in this
# project chose, and the 1.4 MB one is the only 72-slot archive of any
# kind the corpus holds — the one place a disk's SIZE changes a DART's
# layout. Macintosh Garden's own FTP repository is the only place either
# has ever been found; tools/get_dart_specimen.py takes the members out
# of this with the engine's own CLI and fixtures/SOURCES.md pins both,
# so the archive itself is kept here rather than in the corpus.
# Be sparing with that host: public credentials, one volunteer's bandwidth.
AUX301=APPLE_AUX_3-0-1_RETAIL_FLOPPY_IMAGES_DART.sit
if [ ! -f "reference/macgarden/$AUX301" ]; then
    mkdir -p reference/macgarden
    curl -sSL -f -o "reference/macgarden/$AUX301" \
        "ftp://mirror:mirror@ftp.macintosh.garden/apps/$AUX301"
fi

# Apple's own DartIntf.h, version 1.5.3, Ken McLeod, 1987-1994. DART was
# never an Apple product and its format was never published; this header
# is the whole of the documentation there is, and it says so ("The format
# of a DART file is provided here for READ-ONLY use"). It survives as the
# accepted answer to a Retrocomputing Stack Exchange question, which is
# also where CiderPress2's notes cite it from, so it is fetched through
# the API — the HTML page is behind a challenge this machine cannot pass.
if [ ! -f reference/notes/DartIntf.h ]; then
    curl -sL -o /tmp/dartintf.json \
        "https://api.stackexchange.com/2.3/answers/31134?site=retrocomputing&filter=withbody"
    python3 -c "
import gzip, html, json, re
raw = open('/tmp/dartintf.json','rb').read()
if raw[:2] == b'\x1f\x8b':
    raw = gzip.decompress(raw)
d = json.loads(raw)
body = d['items'][0]['body']
code = '\n'.join(html.unescape(re.sub(r'<[^>]+>', '', m))
                 for m in re.findall(r'<code>(.*?)</code>', body, re.S))
open('reference/notes/DartIntf.h', 'w').write(code)
"
    rm -f /tmp/dartintf.json
fi

# The archiveteam wiki's Apple Archive page, kept for the two codec bytes
# libNeoAppleArchive names but does not yet write: lzma `pbzx` (70627A78)
# and lz4 `pbz4` (70627A34). Its own docs/NeoAAArchiveGeneric.md says
# both belong to the format and are "not yet added", so the wiki is what
# supplies the bytes. https is refused by that host; http works.
[ -f reference/notes/Apple_Archive.md ] || \
    curl -sL "http://fileformats.archiveteam.org/wiki/Apple_Archive?action=raw" \
        -o reference/notes/Apple_Archive.md

# ------------------------------------------------------------------
# The container formats' own specifications.
#
# Everything below documents a CONTAINER — a header, an entry table, a
# directory — rather than a compression method, and every one of them is
# public. They were fetched on 2026-09-19 so that src/fmt_binhex.c,
# fmt_macbinary.c, fmt_applesingle.c, fmt_exo.c, fmt_zipseg.c and
# fmt_sitseg.c could cite the document a fact is written in instead of
# citing XADMaster's reading of it (DECISIONS.md 2026-09-19, *the facts
# that were somebody else's to state*). None of them is a licence
# obligation and none is linked into anything shipped.
# ------------------------------------------------------------------

# An HTML page reduced to its text. Three of the documents below survive
# only as web pages; the rest are plain text and are taken as they are.
html_to_text() {
    python3 -c "
import html, re, sys
s = open(sys.argv[1], encoding='utf-8', errors='replace').read()
s = re.sub(r'(?is)<(script|style).*?</\1>', '', s)
s = re.sub(r'(?is)<br\s*/?>|</(p|div|tr|h[1-6]|pre|li)>', '\n', s)
s = re.sub(r'(?is)<[^>]+>', ' ', s)
s = html.unescape(s)
s = re.sub(r'[ \t]+', ' ', s)
s = re.sub(r'\n[ \t]+', '\n', s)
s = re.sub(r'\n{3,}', '\n\n', s)
open(sys.argv[2], 'w').write(s)
" "$1" "$2"
}

# BinHex 4.0 — RFC 1741 for the MIME type and its Appendix A, and Peter
# N Lewis's "BinHex 4.0 Definition" (Aug 1991) for everything Appendix A
# leaves vague. BOTH are needed and the reason is worth knowing: the
# RFC's rendering of the 64-character alphabet contains a stray space
# and is 65 characters long, so the RFC alone cannot say what the
# alphabet is. Lewis's document has it right, and is also the only one
# that states the CRC (0x1021, initial register zero) and the rule that
# a run count of zero means a literal 0x90.
[ -f reference/notes/rfc1741.txt ] || \
    curl -sL -o reference/notes/rfc1741.txt \
        "https://www.rfc-editor.org/rfc/rfc1741.txt"
[ -f reference/notes/binhex40_lewis.txt ] || \
    curl -sL -o reference/notes/binhex40_lewis.txt \
        "http://files.stairways.com/other/binhex-40-specs-info.txt"

# MacBinary II (the 7/24/87 revision) and MacBinary III (December 1996).
# Between them they give the whole 128-byte header, the 128-byte fork
# padding, the CRC over bytes 0..123, the 'mBIN' signature at 102, and —
# this is the part nothing else writes down — the ORDER a reader is
# meant to decide the version in, along with the stricter tests that
# distinguish a MacBinary I header from noise. MacBinary III survives
# only as an archived web page.
[ -f reference/notes/macbinary_ii.txt ] || \
    curl -sL -o reference/notes/macbinary_ii.txt \
        "http://files.stairways.com/other/macbinaryii-standard-info.txt"
if [ ! -f reference/notes/macbinary_iii.txt ]; then
    curl -sL -o /tmp/mb3.html \
        "https://web.archive.org/web/20050305044255/http://www.lazerware.com:80/formats/macbinary/macbinary_iii.html"
    html_to_text /tmp/mb3.html reference/notes/macbinary_iii.txt
    rm -f /tmp/mb3.html
fi

# AppleSingle / AppleDouble — RFC 1740, appendices A and B. The magic
# numbers, the version, the 16 filler bytes, the entry count and the
# (id, offset, length) descriptors, the predefined entry ids, and the
# 2000-01-01 GMT epoch that entry 8's dates are counted from.
[ -f reference/notes/rfc1740.txt ] || \
    curl -sL -o reference/notes/rfc1740.txt \
        "https://www.rfc-editor.org/rfc/rfc1740.txt"

# gzip — RFC 1952, for the header src/fmt_exo.c walks.
[ -f reference/notes/rfc1952.txt ] || \
    curl -sL -o reference/notes/rfc1952.txt \
        "https://www.rfc-editor.org/rfc/rfc1952.txt"

# zip — PKWARE's APPNOTE.TXT 6.3.10, the format's own specification.
# Sections this engine reads: 4.3.12 and 4.3.16 (central directory and
# end-of-central-directory records), 4.3.14 and 4.3.15 (the Zip64
# records and their signatures), 4.4.4 (the general purpose bit flag),
# 4.5.3 (the Zip64 extra field, whose fields appear only for the
# central-directory values that carry the escape, in a fixed order),
# APPENDIX E (method 99 and the 0x9901 extra field), and section 8
# (splitting and spanning, including the 0x08074b50 marker at the front
# of a first segment).
[ -f reference/notes/zip_appnote.txt ] || \
    curl -sL -o reference/notes/zip_appnote.txt \
        "https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT"

# WinZip's AES specification, which APPENDIX E of APPNOTE.TXT names as
# the published layout of the 0x9901 extra field: the vendor version,
# the two-character vendor ID "AE", the strength byte (1, 2, 3 for 128,
# 192, 256 bits) and the real compression method behind method 99.
if [ ! -f reference/notes/winzip_aes.txt ]; then
    curl -sL -o /tmp/winzip_aes.html "https://www.winzip.com/en/support/aes-encryption/"
    html_to_text /tmp/winzip_aes.html reference/notes/winzip_aes.txt
    rm -f /tmp/winzip_aes.html
fi

# ustar — POSIX.1-2017 (The Open Group Base Specifications Issue 7), the
# pax utility page, whose "ustar Interchange Format" section carries the
# 512-octet header block table src/fmt_exo.c reads, the two zero records
# that end an archive, and the typeflag values.
if [ ! -f reference/notes/posix_ustar.txt ]; then
    curl -sL -o /tmp/pax.html \
        "https://pubs.opengroup.org/onlinepubs/9699919799/utilities/pax.html"
    html_to_text /tmp/pax.html reference/notes/posix_ustar.txt
    rm -f /tmp/pax.html
fi

echo "references ready"
