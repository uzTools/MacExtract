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
echo "references ready"
