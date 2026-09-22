#!/usr/bin/env python3
"""sweep_deark.py — ask the third oracle about the forks nobody ever
asked it about.

`make_manifests.py` offers deark only what the other implementations
left OPEN, plus the forks macunpack alone had graded. **A check
positioned where nothing can contradict it cannot contradict
anything**, and that is exactly how deark sat in `reference/` for four
weeks without ever being put to StuffIt method 6 (BLOCKERS.md,
DECISIONS.md 2026-09-21, *the oracle that was never asked*). The same
mechanism still hides it from the ~900 fixtures `unar` grades on its
own.

This runs deark over **every** fixture that has a manifest and
compares everything it produces against every hash the manifest holds.
Nothing is written: a disagreement is a finding to look at, not a
manifest edit. Offline, no emulator; deark reads StuffIt, PackIt, ARC,
Compact Pro, MacBinary and Zip, and simply produces nothing for the
rest.

    sh tools/build_deark.sh        # ./ci.sh's `make clean` deletes it
    tools/sweep_deark.py [--fixture NAME ...] [-v]

**An entry deark DECLINED is not an entry deark could not name.** This
counted both as "not compared" until 2026-09-22, because
`deark_forks` was built from deark's output FILES and a member it
declined every fork of writes none. deark names those members perfectly
well — in its errors — and 225 of the 283 entries this sweep said it
could not compare were StuffIt method 13 or StuffIt 5's Arsenic, methods
deark does not implement. They are `declined` now, and the number left
is the naming gap this line was always supposed to be reporting — 10,
since the oracle stopped being asked about StuffIt 5 in MacRoman
(TESTING.md, *Exact oracle invocation*).

**Two guards, and both are agreements that do not look like one.**

deark does not fail on a damaged file, it pads:
`sitdoc.sit` declares a 286-byte resource fork in a file that ends 52
bytes short and deark writes 286 bytes whose last 52 are zeros it made
up. So a fork that is LONGER than the graded one, whose first bytes
hash to the graded one and whose tail is all zeros, is reported as
padding and not as a disagreement — which is the same rule
`make_manifests.py` states as DEARK_METHODS, applied from the other
side.

And deark does not unwrap **MacLHA's MacBinary payload**: where `unar`
and this engine split an entry into two forks, deark writes the
128-byte header and the padded forks as one file. A fork whose graded
bytes are exactly what that container holds is reported as `wrapped`,
which is agreement one layer down.

Not in `ci.sh`: it needs the fixtures, which are copyrighted and not
committed, and it is an audit rather than a test. It skips cleanly
without them.
"""
import argparse
import glob
import hashlib
import importlib.util
import collections
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def load_make_manifests():
    """Reuse `deark_forks`/`deark_id` rather than copying them, so this
    sweep and the manifest builder can never drift into disagreeing
    about what deark produced."""
    spec = importlib.util.spec_from_file_location(
        "mm", os.path.join(ROOT, "tools", "make_manifests.py"))
    mm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mm)
    return mm


def sha(b):
    return hashlib.sha256(b).hexdigest()


def classify(blob, size, want, wrapped=None):
    """'agree' | 'padded' | 'wrapped' | 'differ' — for one fork deark
    produced against one the manifest records.

    A blob of None is a fork deark reported it could not read, which
    is not a disagreement about anything.

    `wrapped` is what this fork would be if deark's DATA output were a
    MacBinary container that it did not unwrap, which is what MacLHA
    entries come out as: deark writes the 128-byte header and the
    padded forks as one file where `unar` and this engine split them.
    Agreement one layer down is agreement.
    """
    if blob is None:
        return "declined"
    if size == len(blob) and sha(blob) == want:
        return "agree"
    if len(blob) > size and sha(blob[:size]) == want \
            and not any(blob[size:]):
        return "padded"
    if wrapped is not None and len(wrapped) == size and sha(wrapped) == want:
        return "wrapped"
    return "differ"


def keys(mm, name):
    """Every mangled name deark might have written this entry under.

    Two, and the second is `unar`'s doing rather than deark's: a tar
    member is normally stored as `./NAME`, `unar` reports it without
    the `./` and deark keeps it — where its own sanitiser turns the
    slash into `_`, so `./READ_ME` reaches the disk as `._READ_ME`.
    That looks exactly like an AppleDouble sidecar and is not one:
    none of the 49 files deark writes for `derived-PCCTS.tar` begins
    with the AppleDouble magic, and each holds its member's own data
    (measured 2026-09-22). It was read as the sidecar convention and
    filed as "a merge rule" for a day.
    """
    out = [mm.deark_name(name)]
    alt = mm.deark_name("./" + name)
    if alt != out[0]:
        out.append(alt)
    return out


def pick(mm, name, got, seen):
    """The key this entry was actually written under, preferring the
    plain one: an archive that really holds both `X` and `./X` is two
    members, and the ambiguous one is refused by the count in `seen`
    like any other."""
    for k in keys(mm, name):
        if k in got:
            return k
    return keys(mm, name)[0]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixture", action="append", default=[],
                    help="sweep only these (repeatable)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    mm = load_make_manifests()
    if not os.path.exists(mm.DEARK):
        print("sweep-deark: no build/deark — run sh tools/build_deark.sh "
              "(skipped)")
        return 0
    mans = sorted(glob.glob(os.path.join(ROOT, "fixtures", "manifests",
                                         "*.json")))
    if not mans:
        print("sweep-deark: no manifests here (skipped)")
        return 0

    tot = dict(fixtures=0, read=0, forks=0, agree=0, padded=0, wrapped=0,
               declined=0, differ=0, unnamed=0, ungraded=0, ambiguous=0)
    # What this sweep CANNOT see, tallied rather than described: an
    # entry deark gives a name no mangling of ours reproduces is not
    # compared at all, and a format where that is most of the entries
    # is a format this sweep barely covers.
    unnamed_by_fmt = collections.Counter()
    differ = []
    for mp in mans:
        man = json.load(open(mp))
        name = man["fixture"]
        if a.fixture and name not in a.fixture:
            continue
        path = os.path.join(ROOT, "fixtures", name)
        if not os.path.exists(path):
            continue
        tot["fixtures"] += 1
        with tempfile.TemporaryDirectory() as tmp:
            got = mm.deark_forks(path, tmp)
            if not got:
                continue
            tot["read"] += 1
            # The mangling is many-to-one, so an entry whose mangled
            # name another entry also claims is refused outright — the
            # same rule the macunpack and deark paths in
            # `make_manifests.py` already use for their own matching.
            seen = {}
            for e in man["entries"]:
                for k in keys(mm, e["name"]):
                    seen[k] = seen.get(k, 0) + 1
            for e in man["entries"]:
                key = pick(mm, e["name"], got, seen)
                if e.get("is_dir"):
                    continue
                if seen.get(key, 0) != 1:
                    # Counted, not just skipped: a category that leaves
                    # no trace is a denominator nobody can check.
                    tot["ambiguous"] += 1
                    continue
                if key not in got:
                    tot["unnamed"] += 1
                    unnamed_by_fmt[man.get("format") or "?"] += 1
                    continue
                # What deark's data output would be if it were a
                # MacBinary it did not unwrap.
                wrap = mm.macbinary_slices_bytes(got[key]["data"] or b"")
                for i, fork in enumerate(("data", "rsrc")):
                    want = e.get(fork + "_sha256")
                    if want is None:
                        tot["ungraded"] += 1
                        continue
                    tot["forks"] += 1
                    verdict = classify(got[key][fork],
                                       e.get(fork + "_size") or 0, want,
                                       wrap[i] if wrap else None)
                    tot[verdict] += 1
                    if verdict == "differ":
                        differ.append((name, e["name"], fork,
                                       e.get(fork + "_size") or 0,
                                       len(got[key][fork]),
                                       e.get(fork + "_oracle") or man["oracle"]))
                    if a.verbose and verdict != "agree":
                        print(f"  {verdict:7s} {name} :: {e['name']} {fork}")

    print(f"sweep-deark: {tot['read']} of {tot['fixtures']} fixtures read by "
          f"deark; {tot['forks']} graded forks cross-checked")
    print(f"             agree {tot['agree']}, padded {tot['padded']}, "
          f"wrapped {tot['wrapped']}, declined {tot['declined']}, "
          f"DIFFER {tot['differ']}")
    print(f"             {tot['unnamed']} entries deark neither named nor "
          f"declined, {tot['ambiguous']} whose mangled name another entry "
          f"claims, {tot['ungraded']} forks nobody has graded")
    if unnamed_by_fmt:
        print("             not compared, by format — "
              + ", ".join(f"{k} {v}" for k, v in unnamed_by_fmt.most_common()))
    for d in differ:
        print(f"  DIFFER  {d[0]} :: {d[1]} {d[2]}  "
              f"graded {d[3]} B by {d[5]}, deark {d[4]} B")
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main())
