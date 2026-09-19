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

echo "references ready"
