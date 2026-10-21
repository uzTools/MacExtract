#!/usr/bin/env python3
"""code_map.py — where the Macintosh application's CODE actually is.

CODE is the only part of this application that costs the engine anything
(FORMATS.md, *What the application costs the engine*), so "why is it 147 KB"
is a question with a budget attached. This answers it from the LINKER MAP,
which is the only instrument that gets it right:

  - summing `size` over the .obj files overstates the linked total by ~17 %,
    because --gc-sections drops what nothing calls;
  - counting every .text/.rodata input section overstates it too, because
    Retro68 places .rodata in the A5 world, not in a CODE resource — which
    is the linker-level reason tables are free and code is not.

So it counts only the input sections the map places under a `.code*` OUTPUT
section, and reports the rest separately.

    cmake -B /tmp/macmap -S mac \\
          -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake \\
          -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXE_LINKER_FLAGS="-Wl,-Map=/tmp/mac.map"
    cmake --build /tmp/macmap -- -j"$(nproc)"
    tools/code_map.py /tmp/mac.map

Pass `--expect` the text column of `m68k-apple-macos-size` and it prints
nothing at all unless the two agree to within 512 B: a table published under
a warning is a table published, and the warning goes to stderr where a
pipeline drops it.
"""
import argparse
import collections
import re
import sys

# One group per line of the report. A file not named here is a format decoder,
# which is the point of the report: the decoders are the bulk and no single
# one of them is.
GROUPS = [
    ("Macintosh shell (UI, File Manager, memory)", ["macextract_mac"]),
    ("shared codec machinery (Huffman/LZW/LZ/BWT)",
     ["unc_huffman", "unc_lzw", "unc_lzdyn", "unc_lzah", "crc32", "sit_arsenic"]),
    ("deflate (zip + gzip)",
     ["inflate", "inftrees", "inffast", "adler32", "unc_inflate", "zutil"]),
    ("engine core, util, segment joining",
     ["unc_engine", "unc_util", "unc_segment"]),
    ("encryption: ciphers and key schedules", ["unc_crypt"]),
]


def objname(path):
    if "(" in path:                      # an archive member: libfoo.a(bar.o)
        return path.split("(")[-1].rstrip(")").replace(".o", "") + "[lib]"
    return path.split("/")[-1].replace(".c.obj", "").replace(".o", "")


def parse(path):
    """(code per object, rodata-outside-CODE per object). GNU ld wraps a long
    input-section name onto its own line, so both shapes are matched."""
    text = open(path, errors="replace").read().split("\n")
    try:
        start = next(i for i, l in enumerate(text)
                     if l.startswith("Linker script and memory map")) + 1
    except StopIteration:
        raise SystemExit("code_map: no linker map in %s" % path)
    code, rodata = collections.Counter(), collections.Counter()
    out = None
    i = start
    while i < len(text):
        line = text[i]
        head = re.match(r"^(\.\S+)", line)          # output section, column 0
        if head:
            out = head.group(1)
            i += 1
            continue
        sec = size = obj = None
        wrapped = re.match(r"^ (\.[\w.$]+)\s*$", line)
        if wrapped and i + 1 < len(text):
            m = re.match(r"^\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+(\S+)", text[i + 1])
            if m:
                sec, size, obj = wrapped.group(1), int(m.group(2), 16), m.group(3)
                i += 1
        if sec is None:
            m = re.match(r"^ (\.[\w.$]+)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+(\S+)", line)
            if m:
                sec, size, obj = m.group(1), int(m.group(3), 16), m.group(4)
        if sec and out:
            if out.startswith(".code"):
                code[objname(obj)] += size
            elif sec.startswith(".rodata"):
                rodata[objname(obj)] += size
        i += 1
    return code, rodata


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map", nargs="?", default="/tmp/mac.map")
    ap.add_argument("--expect", type=int,
                    help="the text column of m68k-apple-macos-size, to check "
                         "this attribution against")
    args = ap.parse_args()

    code, rodata = parse(args.map)
    if not code:
        raise SystemExit("code_map: no .code output sections in that map")
    total = sum(code.values())

    # Checked BEFORE anything is printed, and fatal. A tool that prints a
    # table and then says not to quote it has published the table: stdout is
    # what gets pasted into a document, and the warning was on stderr.
    if args.expect is not None and abs(args.expect - total) > 512:
        print("code_map: attributed %d B against size(1)'s %d B, a gap of "
              "%d B. The map's layout has changed and this attribution is "
              "wrong; no table printed."
              % (total, args.expect, args.expect - total), file=sys.stderr)
        return 1
    named = {n for _, names in GROUPS for n in names}
    named |= {n for n in code if n.endswith("[lib]")}
    decoders = sorted(((s, n) for n, s in code.items() if n not in named),
                      reverse=True)

    def row(label, value):
        print("%-46s%7d  %5.1f%%" % (label, value, 100.0 * value / total))

    row(GROUPS[0][0], sum(code[n] for n in GROUPS[0][1]))
    row("format decoders (%d files)" % len(decoders), sum(s for s, _ in decoders))
    for label, names in GROUPS[1:]:
        row(label, sum(code[n] for n in names))
    row("Retro68 runtime + libc glue",
        sum(s for n, s in code.items() if n.endswith("[lib]")))
    print("%-46s%7d" % ("total", total))

    print("\nformat decoders, biggest first:")
    for s, n in decoders[:12]:
        print("   %-22s%7d" % (n, s))
    if len(decoders) > 12:
        print("   ... %d more totalling %d"
              % (len(decoders) - 12, sum(s for s, _ in decoders[12:])))

    print("\nread-only tables placed in the A5 world, outside CODE: %d"
          % sum(rodata.values()))

    if args.expect is not None:
        print("\nagainst size(1)'s text column: %d B of link fill"
              % (args.expect - total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
