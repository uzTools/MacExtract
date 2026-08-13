#!/bin/sh
# fetch_references.sh — repopulate the read-only reference/ directory.
# reference/ is never committed; this script documents its provenance.
set -e
cd "$(dirname "$0")/.."
mkdir -p reference/notes

[ -d reference/XADMaster ] || \
    git clone --depth 1 https://github.com/MacPaw/XADMaster reference/XADMaster

if [ ! -d reference/macutils ]; then
    mkdir -p reference/macutils
    curl -sL -o /tmp/macutils.tar.gz \
        "http://deb.debian.org/debian/pool/main/m/macutils/macutils_2.0b3.orig.tar.gz"
    tar xzf /tmp/macutils.tar.gz -C reference/macutils --strip-components=1
    rm /tmp/macutils.tar.gz
fi

cd reference/notes
for p in StuffIt Compact_Pro PackIt BinHex MacBinary; do
    [ -f "$p.md" ] || curl -sL "http://fileformats.archiveteam.org/wiki/$p?action=raw" -o "$p.md"
done
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
