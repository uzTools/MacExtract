#!/usr/bin/env python3
"""synth_uu.py — uuencoded fixtures, in every shape the decoder reads.

The corpus holds no `.uu` (measured 2026-08-15 by innermost format over
all 805 fixtures), so these are generated. Each shape has its own
independent adjudicator, which is the point:

    plain     `binascii.b2a_uu` writes it (CPython, not our code) and
              the ground truth is the bytes that went in.
    UUTool    macutils' `hexbin` decodes it — a second
              implementation, so an agreement is between two
              implementations rather than between a generator and its
              mirror image. What fmt_uu.c CITES is UUTool itself
              (tools/derive_mu.py); hexbin is an oracle here, not a
              source.

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

The section tag is compared at a FIXED offset (line+10), which is why
the prefix is exactly "begin 644 " and the tag itself starts with a
space — UUTool writes "begin 0700 .rsrc" and the mode is four
characters (tools/derive_mu.py).

FOUR SPELLINGS, three of them not the standard alphabet. UUTool
encodes with its `HEXA` 128 "PC" table (the standard 0x20..0x5f) only
when "use original coding" is set; by default it uses `HEXA` 129
"UNIX", which moves the low values up past the standard range so that
no value encodes to a space. It shipped in two generations — 2.0.4's
moves 30 values to 0x60..0x7d, 2.3.2's moves 27 to 0x60..0x7a — and
BOTH are generated here, because a reader that assumes the standard
alphabet reads nothing UUTool writes by default (DECISIONS.md
2026-10-06, *the alphabet nothing here had seen*).

The fourth is not UUTool's at all and is the one Unix `uuencode` has
always written: the standard alphabet with the value ZERO spelled "`"
instead of a space. `binascii.b2a_uu` does not write it, so it was the
one spelling no generated case here held — and narrowing the standard
range to 0x5f for the two tables above made every such file unreadable
for a day (DECISIONS.md 2026-10-07, *the spelling the tables did not
have*).

Usage:  synth_uu.py <outdir>
"""
import binascii, os, sys

# Source: UUTool's own `HEXA` 128 and 129 resources, read out of 2.0.4
# and 2.3.2 by tools/derive_mu.py --tables. `None` is the standard
# alphabet, which is both `HEXA` 128 and what binascii writes.
TABLE_PC = None
TABLE_UNIX20 = 30      # UUTool 2.0.4: values 0..29 -> 0x60..0x7d
TABLE_UNIX23 = 27      # UUTool 2.3.2: values 0..26 -> 0x60..0x7a
# Not a UUTool table: the standard alphabet as Unix `uuencode` writes
# it, where the value ZERO is "`" and not a space, so that a mailer
# stripping trailing whitespace cannot eat it. 4.2BSD's uuencode.c and
# GNU sharutils' both spell it ENC(c) = (c) ? ((c) & 077) + ' ' : '`',
# and mpack's uudecode.c accepts either. `binascii.b2a_uu` writes the
# space, so this is the one shape CPython cannot generate — and the
# shape no fixture had until 2026-10-07 (BLOCKERS.md).
TABLE_PC_BQ = "bq"


def encode_char(v, table):
    """One 6-bit value as the character `table` spells it."""
    if table == TABLE_PC_BQ:
        return 0x60 if v == 0 else 0x20 + v
    if table is None or v >= table:
        return 0x20 + v
    return 0x60 + v


def uu_line(chunk, table):
    """One data line: the count character, then the 4-for-3 groups."""
    if table is None:
        return binascii.b2a_uu(chunk).decode('ascii').rstrip('\n')
    out = [encode_char(len(chunk), table)]
    pad = chunk + bytes(-len(chunk) % 3)
    for i in range(0, len(pad), 3):
        a, b, c = pad[i], pad[i + 1], pad[i + 2]
        for v in (a >> 2, ((a & 3) << 4) | (b >> 4),
                  ((b & 15) << 2) | (c >> 6), c & 0x3f):
            out.append(encode_char(v, table))
    return bytes(out).decode('ascii')


def uu_lines(data, table=TABLE_PC):
    out = []
    for i in range(0, len(data), 45):
        out.append(uu_line(data[i:i + 45], table))
    return out


def plain(name, data, mode="644", table=TABLE_PC):
    lines = ["begin %s %s" % (mode, name)]
    lines += uu_lines(data, table)
    lines.append("`")           # value 0 is "`" in all three tables
    lines.append("end")
    return "\n".join(lines) + "\n"


def uutool(macname, datafork, rsrcfork, ftype, creator, flags=0,
           table=TABLE_PC):
    def section(tag, payload):
        lines = ["begin 644 " + tag]
        lines += uu_lines(payload, table)
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
    data = b"the quick brown fox jumps over the lazy dog.\n" * 30
    rsrc = bytes(range(256)) * 3
    # Binary rather than prose for the classic-spelling case: the point
    # of it is a line that holds a ZERO and a value under 27 at once,
    # which is what fits neither half of the mask when the standard
    # range is narrowed. run_uu.py asserts that such a line is there.
    binary = bytes(range(256)) * 2

    # `-o <file>` writes the one document committed as a fixture, which
    # is the form fixtures/SOURCES.md restores with (harvest.py: "the
    # script must accept -o <path> and be deterministic"). Without it
    # that line could not be restored at all.
    if len(sys.argv) == 3 and sys.argv[1] == "-o":
        open(sys.argv[2], "w").write(
            uutool("Mac File", data, rsrc, b"TEXT", b"ttxt"))
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: synth_uu.py <outdir> | synth_uu.py -o <file>")
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)

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

    # The two alphabets UUTool actually ships with, which is what a
    # wild specimen turned out to be in (FORMATS.md, *uuencode*).
    p = os.path.join(out, "synth-uu-mac-unix20.uu")
    open(p, "w").write(uutool("Unix Table", data, rsrc, b"TEXT", b"ttxt",
                              table=TABLE_UNIX20))
    made.append(p)

    p = os.path.join(out, "synth-uu-mac-unix23.uu")
    open(p, "w").write(uutool("Later Table", data, rsrc, b"TEXT", b"ttxt",
                              table=TABLE_UNIX23))
    made.append(p)

    p = os.path.join(out, "synth-uu-plain-unix20.uu")
    open(p, "w").write(plain("hello.txt", data, table=TABLE_UNIX20))
    made.append(p)

    # What `uuencode` itself writes: the standard alphabet, zero as "`".
    p = os.path.join(out, "synth-uu-plain-classic.uu")
    open(p, "w").write(plain("binary.bin", binary, table=TABLE_PC_BQ))
    made.append(p)

    for m in made:
        print(m)


if __name__ == "__main__":
    main()
