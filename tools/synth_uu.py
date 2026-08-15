#!/usr/bin/env python3
"""synth_uu.py — uuencoded fixtures, in both shapes the decoder reads.

The corpus holds no `.uu` (measured 2026-08-15 by innermost format over
all 805 fixtures), so these are generated. Each shape has its own
independent adjudicator, which is the point:

    plain     `binascii.b2a_uu` writes it (CPython, not our code) and
              the ground truth is the bytes that went in.
    UUTool    macutils' `hexbin` decodes it — the implementation
              fmt_uu.c was transcribed from (hexbin/mu.c), so an
              agreement is between two implementations rather than
              between a generator and its mirror image.

Layout of the UUTool shape, from reference/macutils/hexbin/mu.c:

    begin 644 "<mac name>"     <- data fork
    <uu lines>
    `                          <- zero-length line
    end
    begin 644  .rsrc           <- optional resource fork
    ...
    begin 644  .finfo          <- 16 bytes of Finder info
    <one uu line>
    `
    end

mu.c compares the section tag at a FIXED offset (line+10), which is why
the prefix is exactly "begin 644 " and the tag itself starts with a
space.

Usage:  synth_uu.py <outdir>
"""
import binascii, os, sys


def uu_lines(data):
    out = []
    for i in range(0, len(data), 45):
        out.append(binascii.b2a_uu(data[i:i + 45]).decode('ascii').rstrip('\n'))
    return out


def plain(name, data, mode="644"):
    lines = ["begin %s %s" % (mode, name)]
    lines += uu_lines(data)
    lines.append("`")
    lines.append("end")
    return "\n".join(lines) + "\n"


def uutool(macname, datafork, rsrcfork, ftype, creator, flags=0):
    def section(tag, payload):
        lines = ["begin 644 " + tag]
        lines += uu_lines(payload)
        lines.append("`")
        lines.append("end")
        return lines

    info = ftype + creator + bytes([flags >> 8, flags & 0xFF]) + bytes(6)
    lines = section('"%s"' % macname, datafork)
    if rsrcfork:
        lines += section(" .rsrc", rsrcfork)
    lines += section(" .finfo", info)
    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: synth_uu.py <outdir>")
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)

    data = b"the quick brown fox jumps over the lazy dog.\n" * 30
    rsrc = bytes(range(256)) * 3
    made = []

    p = os.path.join(out, "synth-uu-plain.uu")
    open(p, "w").write(plain("hello.txt", data))
    made.append(p)

    # A mail banner in front of it, which is how these travelled.
    p = os.path.join(out, "synth-uu-banner.uu")
    open(p, "w").write("From: someone\nSubject: here you go\n\n"
                       "Cut here\n" + plain("hello.txt", data))
    made.append(p)

    # Several documents in one file, the comp.binaries.mac shape.
    p = os.path.join(out, "synth-uu-multi.uu")
    open(p, "w").write(plain("first.txt", b"first file\n") +
                       "\n---- part two ----\n\n" +
                       plain("second.bin", bytes(range(200))))
    made.append(p)

    p = os.path.join(out, "synth-uu-mac.uu")
    open(p, "w").write(uutool("Mac File", data, rsrc, b"TEXT", b"ttxt"))
    made.append(p)

    p = os.path.join(out, "synth-uu-mac-nrsrc.uu")
    open(p, "w").write(uutool("Data Only", data, b"", b"TEXT", b"ttxt"))
    made.append(p)

    for m in made:
        print(m)


if __name__ == "__main__":
    main()
