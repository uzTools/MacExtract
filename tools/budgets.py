#!/usr/bin/env python3
"""budgets.py — tools/budgets.txt, read.

    import budgets
    budgets.get("OVL_SAVED")     -> 182208
    budgets.load()               -> {name: int}, in the file's order
    budgets.images()             -> {"OVL_ID_ARC": 7924, ...}

A name the file does not have raises SystemExit: a figure that went missing
must not read as zero.
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "budgets.txt")
ROW = re.compile(r"^([A-Z][A-Z0-9_]*)=(-?\d+)\s*(#.*)?$")


def load(path=PATH):
    out = {}
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = ROW.match(line)
        if not m:
            raise SystemExit("budgets.py: %s:%d is not NAME=number: %r"
                             % (path, n, line))
        if m.group(1) in out:
            raise SystemExit("budgets.py: %s is in %s twice"
                             % (m.group(1), path))
        out[m.group(1)] = int(m.group(2))
    return out


def get(name, path=PATH):
    b = load(path)
    if name not in b:
        raise SystemExit("budgets.py: tools/budgets.txt has no %s" % name)
    return b[name]


def images(path=PATH):
    return {"OVL_ID_" + k[len("IMAGE_"):]: v for k, v in load(path).items()
            if k.startswith("IMAGE_")}


if __name__ == "__main__":
    for k, v in load().items():
        print("%s=%d" % (k, v))
