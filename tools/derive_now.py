#!/usr/bin/env python3
"""derive_now.py — one of Now Compress's stream shapes, derived from
the application's own output, and a tool that re-runs the reading.

Now Compress is the last format in this project's inventory with **no
published description of any kind** — no wiki page, no specification,
no second implementation: `XADNowCompressHandle.m` is the only account
of it that exists (OPEN_ITEMS.md). So this one could not be fetched;
it had to be measured.

What it was measured from is the application itself.
`tools/vmac/nowcompress.py` drives Now Compress under the emulator and
compresses files chosen here, keeping the inputs beside the outputs in
`$UNC_VMAC_HOME/specimens/now/`. This tool reads those pairs back with
a decoder written from nothing but the bytes.

    tools/derive_now.py

**One shape of five, and the simplest.** It reads the two specimens
the harness made in each of two modes, and it does NOT read the
corpus's real Now Compress files or the harness's larger ones, which
use shapes this has not derived. That is stated rather than glossed:
`src/fmt_now.c` still cites XADMaster for everything, and will until
all of them are described.

Not in `ci.sh`: it needs the emulator's specimen directory.
"""
import argparse
import os
import sys

HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
SPECIMENS = os.path.join(HOME, "specimens", "now")

# Every stream this reads puts its payload here. Four specimens, two
# modes, two very different files — so it is a fixed header and not a
# coincidence, but 164 is an observation and not a field anybody has
# read out of the header.
PAYLOAD_AT = 164


def decode(d, p, nout):
    """The shape.

    A flag byte, then eight tokens, its bits taken most significant
    first: a 1 is a literal byte, a 0 is a match.

    A match is two bytes — `length - 2`, then the distance — EXCEPT
    that a length byte of zero is an escape, and then the token is
    three bytes: zero, the distance, and `length - 2`. So a match
    reaches 2..257 bytes back at most 255 bytes, which is why this
    shape only ever appears on small forks: the encoder picks another
    when a file needs a longer reach.

    Nothing in the stream says when to stop. The caller's byte count
    does — the same as StuffIt method 8 and ARC's squeeze.
    """
    out = bytearray()
    while len(out) < nout:
        if p >= len(d):
            raise EOFError
        flags = d[p]
        p += 1
        for bit in range(8):
            if len(out) >= nout:
                break
            if flags & (0x80 >> bit):
                out.append(d[p])
                p += 1
            else:
                n = d[p]
                if n == 0:
                    dist, ln = d[p + 1], d[p + 2] + 2
                    p += 3
                else:
                    ln, dist = n + 2, d[p + 1]
                    p += 2
                if dist == 0 or dist > len(out):
                    raise ValueError("distance %d" % dist)
                for _ in range(ln):
                    out.append(out[-dist])
    return bytes(out[:nout]), p


def main():
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter
                            ).parse_args()
    if not os.path.isdir(SPECIMENS):
        print("derive-now: no specimens — tools/vmac/nowcompress.py --case all "
              "makes them (skipped)")
        return 0
    ok = stored = other = 0
    for mode in sorted(os.listdir(SPECIMENS)):
        mdir = os.path.join(SPECIMENS, mode)
        if not os.path.isdir(mdir):
            continue
        for f in sorted(os.listdir(mdir)):
            if not f.endswith(".dat"):
                continue
            base = f[:-4]
            inp = os.path.join(mdir, "in-" + base)
            if not os.path.exists(inp):
                continue
            d = open(os.path.join(mdir, f), "rb").read()
            want = open(inp, "rb").read()
            try:
                out, end = decode(d, PAYLOAD_AT, len(want))
            except Exception:
                out, end = None, None
            if out == want:
                print(f"ok  {mode:8s} {base:10s} {len(want):6d} B from "
                      f"{len(d):6d}  payload {PAYLOAD_AT}..{end}, "
                      f"trailer {d[end:].hex(' ')}")
                ok += 1
            elif d == want:
                # `archive` mode stores the member and compresses the
                # .sea around it: the fork IS the file, byte for byte.
                print(f"ok  {mode:8s} {base:10s} {len(want):6d} B from "
                      f"{len(d):6d}  stored, not compressed at all")
                stored += 1
            else:
                print(f"--  {mode:8s} {base:10s} {len(want):6d} B from "
                      f"{len(d):6d}  another shape")
                other += 1
    print(f"derive-now: {ok} specimen(s) read by this shape, {stored} "
          f"stored, {other} by shapes not derived here")
    return 0


if __name__ == "__main__":
    sys.exit(main())
