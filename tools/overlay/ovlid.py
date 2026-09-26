#!/usr/bin/env python3
"""ovlid.py — resolve an OVL_ID_* name to the number overlay.h gives it.

The resource id of an image was written in three places: overlay.h, which is
what the shim asks GetResource for; mac/CMakeLists.txt, which is what the
resource is NUMBERED; and (in the eager lifetime) the bundle's directory. Three
copies of one table, and a disagreement between them is not a build error —
it is a GetResource that answers NULL at run time, or an image answering to
an id that means something else. The build says nothing either way.

So the build takes the number from overlay.h by NAME, here, and nowhere else
writes one down.

    ovlid.py OVL_ID_LZH         -> 131

A number is refused rather than passed through: accepting one is how the
second copy of the table would come back.
"""
import os
import re
import sys

HDR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "overlay.h")


def resolve(name):
    if not name.startswith("OVL_ID_"):
        raise SystemExit("ovlid: %r is not an OVL_ID_* name — overlay.h is "
                         "where the number lives" % name)
    with open(HDR) as f:
        m = re.search(r"^#define\s+%s\s+(\d+)" % re.escape(name), f.read(), re.M)
    if not m:
        raise SystemExit("ovlid: overlay.h defines no %s" % name)
    return int(m.group(1))


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__.strip().split("\n")[-3].strip())
    print(resolve(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
