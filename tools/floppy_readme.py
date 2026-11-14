#!/usr/bin/env python3
"""floppy_readme.py — the floppies' "Read Me", from docs/floppy-read-me.txt.

    python3 tools/floppy_readme.py docs/floppy-read-me.txt --disk HFS -o OUT
    python3 tools/floppy_readme.py docs/floppy-read-me.txt --disk MFS -o OUT

The source is wrapped for reading in the repository; TeachText and
SimpleText wrap a paragraph to their window themselves, so the lines of a
paragraph are joined with a space. A blank line ends a paragraph, and a
line starting "- " starts a line of its own (the formats list). A line
starting {HFS} is kept only on the 800K and 1.44 MB disks, {MFS} only on
the 400K one, the tag removed. The result is Mac Roman with CR line ends,
written for tools/make_dist.sh, which types it 'ttro'/'ttxt'.

It refuses a text over LIMIT bytes (below). dist/README.txt is not this
text and has no such limit: it is the download page.
"""
import argparse, sys

# What the readers open, measured one boot per size (DECISIONS.md
# 2026-11-14, *the floppy that works locked*): TeachText 1.2 on System
# 6.0.8 at 1 MB opens 32,000 bytes and refuses 32,001 ("This document is
# too large to be opened by TeachText."); SimpleText on 7.0.1 at 4 MB opens
# 31,500 and refuses 31,999. The guard sits 1,500 under the lower; the
# Read Me that was refused on a Mac Plus was 32,436.
LIMIT = 30000


def convert(src, disk):
    out, para = [], []

    def flush():
        if para:
            out.append("\r".join(para))
            para.clear()

    for line in src.split("\n"):
        for tag in ("{HFS}", "{MFS}"):
            if line.startswith(tag):
                if tag != "{%s}" % disk:
                    line = None
                else:
                    line = line[len(tag):]
                break
        if line is None:
            continue
        line = line.rstrip()
        if not line:
            flush()
        elif line.startswith("- ") or not para:
            para.append(line)
        else:
            para[-1] += " " + line
    flush()
    return ("\r\r".join(out) + "\r").encode("mac_roman")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("--disk", choices=("HFS", "MFS"), required=True)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    t = convert(open(a.src, encoding="utf-8").read(), a.disk)
    if len(t) > LIMIT:
        sys.exit(f"floppy_readme: {a.src} is {len(t)} B as Mac text, over "
                 f"{LIMIT} (SimpleText refused 31,999, TeachText 32,001)")
    open(a.out, "wb").write(t)


if __name__ == "__main__":
    main()
