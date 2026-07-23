#!/usr/bin/env python3
"""check_mac_sink.py <manifest.json> <outdir>

Compare the Mac-sink test's output tree against an oracle manifest,
byte-for-byte (data fork + .rsrc sidecar). Used by tests/run_mac_sink.sh.
"""
import hashlib, json, os, sys, unicodedata


def norm(p):
    n = unicodedata.normalize("NFC", p)
    return n.replace(":", "_").replace("/", "_")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


def normpath(p):
    return "/".join(norm(c) for c in p.split("/"))


def main():
    man = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    # The mock reproduces the folder tree; index produced files by
    # normalized relative path (matching the manifest entry names).
    produced = {}
    for root, _dirs, files in os.walk(out):
        rel = os.path.relpath(root, out)
        for f in files:
            p = normpath(os.path.normpath(os.path.join(rel, f)))
            produced[p] = os.path.join(root, f)
    bad = 0
    for e in man["entries"]:
        if e.get("is_dir"):
            continue
        name = normpath(e["name"])
        if e["data_size"]:
            p = produced.get(name)
            if not p or sha(p) != e["data_sha256"]:
                print(f"  MISMATCH data {name!r}")
                bad += 1
        if e["rsrc_size"]:
            p = produced.get(name + ".rsrc")
            if not p or sha(p) != e["rsrc_sha256"]:
                print(f"  MISMATCH rsrc {name!r}")
                bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
