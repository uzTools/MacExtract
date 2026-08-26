#!/usr/bin/env python3
"""Build the minimal XADMaster DDn reproduction from a corpus fixture.

The repro is 1,166 bytes: one DiskDoubler `0xABCD0054` container holding
one file's two DDn forks, lifted verbatim out of
`fixtures/derived-LHA_Expander_1.0.3.sea` with only the header's own
CRC-16 restamped so it stands alone.

The bytes are not committed — fixtures are copyrighted historical
software and this repro is a slice of one — so it is generated:

    tools/xadmaster-ddn-repro/make_repro.py -o /tmp/repro.dd

Then, with unar 1.10.8:

    unar -f /tmp/repro.dd     ->  Failed! (Attempted to read more data
                                  than was available), both forks
    macextract x /tmp/repro.dd ->  both forks, byte-exact against
                                  DiskDoubler's own expander
"""
import argparse
import os
import struct
import sys

FIXTURE = "fixtures/derived-LHA_Expander_1.0.3.sea"
ENTRY_AT = 294          # the first 0xABCD0054 header: "1.0.3 Release Notes (E)"


def crc16(d, crc=0):
    for x in d:
        crc ^= x << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def main():
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", required=True, help="where to write the repro")
    ap.add_argument("--fixture", default=os.path.join(root, FIXTURE))
    ap.add_argument("--slack", type=int, default=0,
                    help="declare N more compressed bytes and pad; 1 makes "
                         "unar succeed, which is the whole point")
    a = ap.parse_args()
    if not os.path.exists(a.fixture):
        raise SystemExit("need %s — see fixtures/SOURCES.md" % a.fixture)
    blob = open(a.fixture, "rb").read()
    head = bytearray(blob[ENTRY_AT:ENTRY_AT + 84])
    dl, dcl, rl, rcl = struct.unpack_from(">IIII", head, 4)
    payload = blob[ENTRY_AT + 84:ENTRY_AT + 84 + dcl + rcl]
    if a.slack:
        # BOTH forks need their own slack: they are laid out back to back
        # and each carries its own declared compressed length.
        struct.pack_into(">I", head, 8, dcl + a.slack)
        struct.pack_into(">I", head, 16, rcl + a.slack)
        payload = (payload[:dcl] + b"\0" * a.slack +
                   payload[dcl:] + b"\0" * a.slack)
    struct.pack_into(">H", head, 82, crc16(bytes(head[:82])))
    open(a.o, "wb").write(bytes(head) + payload)
    print("wrote %s (%d B): data %d->%d, rsrc %d->%d, both method 10 (DDn)"
          % (a.o, 84 + len(payload), dl, dcl, rl, rcl))
    return 0


if __name__ == "__main__":
    sys.exit(main())
