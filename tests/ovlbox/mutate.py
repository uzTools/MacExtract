#!/usr/bin/env python3
"""mutate.py <file> <old> <new> — break one line, on purpose, and prove it.

tests/run_overlay_host.sh --mutate uses this to answer "can this suite fail?"
for the overlay loader: each break must be caught by the loader test. Written
as a tool rather than as sed because a sed that matches NOTHING exits 0, and
the first version of that lane reported a mutation as uncaught when what had
actually happened was that it was never applied.

Replaces the FIRST occurrence only, and exits 1 if there is none.
"""
import io
import sys


def main():
    if len(sys.argv) != 4:
        print(__doc__.strip().split("\n")[0], file=sys.stderr)
        return 2
    path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
    text = io.open(path, encoding="utf-8").read()
    if old not in text:
        print("mutate: %r is not in %s — the mutation would be a no-op, which "
              "is not the same as an uncaught defect" % (old, path),
              file=sys.stderr)
        return 1
    io.open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
