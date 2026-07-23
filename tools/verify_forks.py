#!/usr/bin/env python3
"""verify_forks.py <manifest.json> <outdir>

Compare MacBinary files (produced by `hcopy -m` from the Mini vMac test
volume) against an oracle manifest, hashing both forks. Used by the
Mini vMac autotest harness (scratchpad/vmac/verify.sh).
"""
import sys, json, hashlib, os, struct, unicodedata


def sha(b):
    return hashlib.sha256(b).hexdigest()


def norm(s):
    return unicodedata.normalize("NFC", s).replace(":", "_").replace("/", "_")


def parse_macbin(path):
    with open(path, "rb") as f:
        d = f.read()
    if len(d) < 128:
        return None
    namelen = d[1]
    name = d[2:2 + namelen].decode("mac_roman", "replace")
    dlen = struct.unpack(">I", d[0x53:0x57])[0]
    rlen = struct.unpack(">I", d[0x57:0x5B])[0]
    doff = 128
    roff = 128 + ((dlen + 127) & ~127)
    return name, d[doff:doff + dlen], d[roff:roff + rlen]


def main():
    man = json.load(open(sys.argv[1]))
    outdir = sys.argv[2]
    produced = {}
    for fn in sorted(os.listdir(outdir)):
        if not fn.endswith(".bin"):
            continue
        r = parse_macbin(os.path.join(outdir, fn))
        if r:
            produced[norm(r[0])] = (r[1], r[2])
    bad = checked = 0
    for e in man["entries"]:
        if e.get("is_dir"):
            continue
        nm = norm(e["name"].split("/")[-1])
        p = produced.get(nm)
        if p is None:
            print(f"  MISSING {e['name']!r}  (produced: {sorted(produced)})")
            bad += 1
            continue
        data, rsrc = p
        checked += 1
        if e["data_size"] and sha(data) != e["data_sha256"]:
            print(f"  DATA MISMATCH {e['name']!r} got {len(data)}B/{sha(data)[:12]} "
                  f"want {e['data_size']}B/{e['data_sha256'][:12]}")
            bad += 1
        if e["rsrc_size"] and sha(rsrc) != e["rsrc_sha256"]:
            print(f"  RSRC MISMATCH {e['name']!r} got {len(rsrc)}B/{sha(rsrc)[:12]} "
                  f"want {e['rsrc_size']}B/{e['rsrc_sha256'][:12]}")
            bad += 1
    if checked == 0:
        print("  NO ENTRIES CHECKED")
        return 1
    if bad == 0:
        print(f"  ALL {checked} ENTRIES MATCH ✓")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
