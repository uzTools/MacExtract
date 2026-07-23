#!/usr/bin/env python3
"""analyze_forks.py <manifest.json> <macbin_output>

Compare a Mini vMac extraction (a MacBinary produced by `hcopy -m`) against
the oracle manifest, and REPORT WHERE forks differ — specifically whether
differences fall only in the resource fork's 'reserved for system use'
header area (offsets 16..127), which a real Mac's Resource Manager may
stamp and the Linux oracle cannot replicate.
"""
import sys, struct, hashlib, json


def forks(path):
    d = open(path, "rb").read()
    dl = struct.unpack(">I", d[0x53:0x57])[0]
    rl = struct.unpack(">I", d[0x57:0x5B])[0]
    do = 128
    ro = 128 + ((dl + 127) & ~127)
    return d[do:do + dl], d[ro:ro + rl]


def diffspans(a, b):
    spans, i, n = [], 0, min(len(a), len(b))
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            spans.append((i, j))
            i = j
        else:
            i += 1
    if len(a) != len(b):
        spans.append(("len", len(a), len(b)))
    return spans


def main():
    man = json.load(open(sys.argv[1]))
    mac = sys.argv[2]
    md, mr = forks(mac)
    e = man["entries"][0]
    # data fork
    if e["data_size"]:
        exp = e["data_sha256"]
        got = hashlib.sha256(md).hexdigest()
        print(f"DATA {len(md)}B got={got[:10]} want={exp[:10]} "
              f"{'OK' if got == exp else 'DIFF'}")
    if e["rsrc_size"]:
        exp = e["rsrc_sha256"]
        got = hashlib.sha256(mr).hexdigest()
        ok = got == exp
        print(f"RSRC {len(mr)}B got={got[:10]} want={exp[:10]} "
              f"{'OK' if ok else 'DIFF'}")
        if not ok:
            # need expected bytes to localize — reconstruct from fixture
            import os
            fx = os.path.join(os.path.dirname(sys.argv[1]), "..", e_fixture(man))
            if os.path.exists(fx):
                _, er = forks(fx)
                sp = diffspans(er, mr)
                print("  rsrc diff spans:", sp)
                reserved = all(isinstance(s[0], int) and s[0] >= 16 and s[1] <= 128
                               for s in sp)
                print("  confined to reserved header (16..127)?",
                      reserved and len(sp) > 0)


def e_fixture(man):
    return man["fixture"]


if __name__ == "__main__":
    sys.exit(main())
