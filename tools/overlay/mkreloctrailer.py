#!/usr/bin/env python3
"""mkreloctrailer.py <image> [offset ...] — append an overlay's relocations.

-mpcrel makes an overlay's CODE position-independent, and for a year that was
taken to mean the whole image was. It is not: an array of POINTERS in constant
data — `sit13_firstlengths`, zlib's `z_errmsg`, MIME's keyword tables — holds
LINK-TIME addresses, and a blob loaded at an arbitrary heap address then
dereferences them into nowhere. The build could not see it, because it asked a
fully linked image for its relocations and a fully linked image has none.

So the loader gets a list. Appended, big-endian, so the handle's own size
finds it:

    [ image bytes ][ u32 offset ] * n [ u32 n ]

Every image gets the trailer, with n = 0 where there is nothing to do, so the
loader needs no flag to tell the two apart. The offsets are image offsets
because the overlay links at base 0.
"""
import struct
import sys


def main():
    path = sys.argv[1]
    # Hex, as `readelf -r` prints it — the awk in mkoverlay.sh does not
    # convert, because this platform's awk has no strtonum() and an
    # empty list from a silently failing one is how the first version of
    # this reported '0 relocations' for an image that had 41.
    offs = sorted(int(x, 16) for x in sys.argv[2:])
    with open(path, "rb") as f:
        img = f.read()
    for o in offs:
        if o + 4 > len(img):
            print("mkreloctrailer: offset %d is past the image" % o,
                  file=sys.stderr)
            return 1
    trailer = b"".join(struct.pack(">I", o) for o in offs)
    with open(path, "wb") as f:
        f.write(img + trailer + struct.pack(">I", len(offs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
