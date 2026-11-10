#!/usr/bin/env python3
"""arc_bin.py — where Debian's `arc` encoder is, for the suites that use it.

`tools/get_arc.sh` installs it in the machine's cache, outside `build/`,
because `./ci.sh` starts with `make clean`, which is `rm -rf build`: kept
there, the real-encoder cases skipped on every CI run (DECISIONS.md
2026-11-10, *the encoder make clean deleted*). `build/arc` is still read,
for a checkout that fetched it before then.

Run as a script, it prints the path, or nothing when there is no encoder.

SPDX-License-Identifier: 0BSD
"""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HOME = os.environ.get("UNC_ARC_HOME") or os.path.join(
    os.path.expanduser("~"), ".cache", "macextract", "arc")


def arc_bin():
    """Absolute path of an executable `arc`, or None."""
    for base in (HOME, os.path.join(ROOT, "build", "arc")):
        p = os.path.join(base, "usr", "bin", "arc")
        if os.access(p, os.X_OK):
            return os.path.abspath(p)
    return None


if __name__ == "__main__":
    print(arc_bin() or "")
