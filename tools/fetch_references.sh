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

# pycdlib 1.14.0 (Chris Lalancette) — a pure-Python ISO 9660 WRITER, and
# the only one this machine can run: there is no genisoimage, xorriso or
# pip here. tools/run_diskimage.py uses it as the encoder for the CD half
# of the disk-image probe, the way run_btoa.py uses btoa itself.
if [ ! -d reference/pycdlib ]; then
    mkdir -p reference/pycdlib
    curl -sL -o /tmp/pycdlib.tar.gz \
        "https://files.pythonhosted.org/packages/source/p/pycdlib/pycdlib-1.14.0.tar.gz"
    tar xzf /tmp/pycdlib.tar.gz -C reference/pycdlib --strip-components=1
    rm -f /tmp/pycdlib.tar.gz
fi

if [ ! -d reference/macutils ]; then
    mkdir -p reference/macutils
    curl -sL -o /tmp/macutils.tar.gz \
        "http://deb.debian.org/debian/pool/main/m/macutils/macutils_2.0b3.orig.tar.gz"
    tar xzf /tmp/macutils.tar.gz -C reference/macutils --strip-components=1
    rm /tmp/macutils.tar.gz
fi

cd reference/notes
for p in StuffIt Compact_Pro PackIt BinHex MacBinary ArcMac; do
    [ -f "$p.md" ] || curl -sL "http://fileformats.archiveteam.org/wiki/$p?action=raw" -o "$p.md"
done
# ArcMac's own specification: the "ArcMac File Structure" section of the
# ARCMAC.DOC that ships with every ArcMac distribution. It is the only place
# that states the byte order of the two fork lengths ("Intel 80xxx byte sex");
# macutils' arc.h gives the offsets and not the order. Text, CR line endings.
if [ ! -f ArcMac.DOC ]; then
    curl -sL "https://www.sac.sk/download/pack/macarc.zip" -o /tmp/macarc.zip
    # 1988 zip, PKWARE-imploded: python3's zipfile cannot read it, unzip can.
    unzip -p /tmp/macarc.zip ARCMAC.DOC | tr '\r' '\n' > ArcMac.DOC
    rm -f /tmp/macarc.zip
fi

# Matthew Russotto's Arsenic (StuffIt method 15) spec; russotto.net may be
# unreachable — fall back to the Wayback Machine and strip the HTML.
if [ ! -f arsenic_russotto.md ]; then
    curl -sL "https://web.archive.org/web/2023/http://www.russotto.net/arseniccomp.html" \
        -o /tmp/arsenic.html
    python3 -c "
import html, re
raw = open('/tmp/arsenic.html').read()
raw = re.sub(r'<script.*?</script>|<style.*?</style>|<!--.*?-->', '', raw, flags=re.S)
text = html.unescape(re.sub(r'<[^>]+>', '', raw))
open('arsenic_russotto.md', 'w').write(re.sub(r'\n{3,}', '\n\n', text))
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
[ -f cpt_specs_theunarchiver.md ] || \
    curl -sL -o cpt_specs_theunarchiver.md \
    "https://storage.googleapis.com/google-code-archive/v2/code.google.com/theunarchiver/wiki/CompactProSpecs.wiki"

if [ ! -f cpt_users_guide.txt ]; then
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
open('cpt_users_guide.txt', 'w').write(re.sub(r'\n{3,}', '\n\n', ''.join(out)))
"
    rm -f /tmp/cpt_guide.pdf
fi
echo "references ready"
