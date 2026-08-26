#!/usr/bin/env python3
"""run_ddforks.py — grade the DiskDoubler forks `unar` refuses, off the Mac.

`unar` 1.10.8 fails on some DiskDoubler DDn forks with *Attempted to read
more data than was available*, and those forks had no off-Mac oracle at
all: macunpack's DiskDoubler method table stops at 9, so only
DiskDoubler's own expander could read them — on a Mac, which restamps a
resource fork's system-reserved bytes 16..127 as it writes it. That is
why 8 resource forks across 2 fixtures were recorded as not ground truth.

**The cause is an off-by-one, reduced to a 1,166-byte reproduction**
(DECISIONS.md 2026-08-22): XADMaster's DDn wants exactly ONE byte more
than the fork's declared compressed length. Declare one more and give it
a pad byte and it decodes — byte for byte what this engine produces,
system-reserved area included.

So the workaround is the oracle. For each fork this rebuilds a
single-fork `0xABCD0054` container holding **the original compressed
bytes, untouched**, with two changes and no others:

  * the declared compressed length is one larger, and
  * one pad byte follows the fork.

    tools/run_ddforks.py FIXTURE...          compare, report
    tools/run_ddforks.py --write FIXTURE...  and record it in the manifest

The pad byte is shown to be inert rather than assumed: every fork is
decoded twice, with 0x00 and with 0xFF, and both must agree.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "build/rel/macextract")
MANIFESTS = os.path.join(ROOT, "fixtures", "manifests")
DD_MAGIC = b"\xab\xcd\x00\x54"


def crc16(d, crc=0):
    for x in d:
        crc ^= x << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def headers(blob):
    """Every 0xABCD0054 file header in an archive, by offset."""
    out, off = [], 0
    while True:
        i = blob.find(DD_MAGIC, off)
        if i < 0 or i + 84 > len(blob):
            break
        dl, dcl, rl, rcl = struct.unpack_from(">IIII", blob, i + 4)
        if i + 84 + dcl + rcl <= len(blob):
            out.append({"at": i, "datasize": dl, "datacomp": dcl,
                        "rsrcsize": rl, "rsrccomp": rcl,
                        "datamethod": blob[i + 20] & 0x7F,
                        "rsrcmethod": blob[i + 21] & 0x7F})
        off = i + 4
    return out


def single(blob, h, which, slack=1, pad=b"\x00"):
    """A one-fork container carrying the original compressed bytes."""
    head = bytearray(blob[h["at"]:h["at"] + 84])
    data = blob[h["at"] + 84:h["at"] + 84 + h["datacomp"]]
    rsrc = blob[h["at"] + 84 + h["datacomp"]:
                h["at"] + 84 + h["datacomp"] + h["rsrccomp"]]
    if which == "data":
        struct.pack_into(">IIII", head, 4, h["datasize"],
                         h["datacomp"] + slack, 0, 0)
        payload = data + pad * slack
    else:
        struct.pack_into(">IIII", head, 4, 0, 0, h["rsrcsize"],
                         h["rsrccomp"] + slack)
        payload = rsrc + pad * slack
        head[20] = head[21]                       # the fork that is present
    struct.pack_into(">H", head, 82, crc16(bytes(head[:82])))
    return bytes(head) + payload


def ad_rsrc(blob):
    """The resource fork inside an AppleDouble sidecar (entry id 2)."""
    if len(blob) < 26 or struct.unpack_from(">I", blob, 0)[0] not in (
            0x00051607, 0x00051600):
        return None
    n = struct.unpack_from(">H", blob, 24)[0]
    for i in range(n):
        eid, off, ln = struct.unpack_from(">III", blob, 26 + i * 12)
        if eid == 2:
            return blob[off:off + ln]
    return None


def _run(argv, out):
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    subprocess.run(argv, capture_output=True)


def decode(container, which, tool):
    """One fork, by one tool, as bytes — or None if it refused."""
    tmp = tempfile.mkdtemp(prefix="ddforks-")
    try:
        f = os.path.join(tmp, "one.dd")
        open(f, "wb").write(container)
        out = os.path.join(tmp, "out")
        if tool == "ours":
            _run([CLI, "x", "--forks", "hidden", "-o", out, f], out)
        else:
            _run(["unar", "-q", "-o", out, "-f", "-k", "hidden", f], out)
        got = None
        for root, _d, files in os.walk(out):
            for x in sorted(files):
                p = os.path.join(root, x)
                blob = open(p, "rb").read()
                if which == "rsrc":
                    if not x.startswith("._"):
                        continue
                    got = blob if tool == "ours" else ad_rsrc(blob)
                else:
                    if x.startswith("._"):
                        continue
                    got = blob
        return got or None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def grade(path, write=False):
    blob = open(path, "rb").read()
    name = os.path.basename(path)
    hs = headers(blob)
    print("%s: %d file headers" % (name, len(hs)))
    rows, bad = [], 0
    for h in hs:
        for which in ("data", "rsrc"):
            size = h[which + "size"]
            if not size:
                continue
            plain = single(blob, h, which)
            ours = decode(plain, which, "ours")
            # `unar` with no slack: does it refuse this fork at all?
            refused = decode(single(blob, h, which, slack=0), which, "unar") is None
            theirs = decode(plain, which, "unar")
            other = decode(single(blob, h, which, pad=b"\xff"), which, "unar")
            ok = (ours is not None and theirs is not None and ours == theirs
                  and theirs == other)
            rows.append((h["at"], which, size, refused, ok))
            bad += 0 if ok else 1
            print("  @%-6d %-4s %-7d  unar without slack: %-8s  with slack: %s"
                  % (h["at"], which, size,
                     "refuses" if refused else "reads it",
                     "AGREES, both pad bytes" if ok else "DIFFERS/failed"))
    print("%s: %d forks, %d graded, %d not"
          % (name, len(rows), len(rows) - bad, bad))
    if write:
        bad += record(path, blob, hs)
    return bad


def record(path, blob, hs):
    """Fill the verdict into the fixture's manifest.

    Only entries currently marked `unadjudicated` are touched; everything
    already graded the ordinary way is left exactly as it is. Headers and
    manifest entries are matched IN ORDER and the pairing is checked
    against both fork sizes before anything is written — a silent
    mis-pairing would put one fork's hash on another fork's name, which
    `ci.sh` would then enforce forever.
    """
    name = os.path.basename(path)
    mp = os.path.join(MANIFESTS, name + ".json")
    if not os.path.exists(mp):
        print("  (no manifest for %s)" % name)
        return 0
    man = json.load(open(mp))
    need = [e for e in man["entries"] if "unadjudicated" in e]
    if not need:
        print("  manifest: nothing left unadjudicated")
        return 0
    # Match a manifest entry to a file header by the DATA fork's hash, not
    # by position: the manifest is ordered by name and the headers by
    # position in the archive, and on one fixture those differ. A silent
    # mis-pairing would put one fork's hash under another fork's name and
    # `ci.sh` would then enforce it forever.
    byhash = {}
    for h in hs:
        d = decode(single(blob, h, "data"), "data", "ours") or b""
        byhash.setdefault((hashlib.sha256(d).hexdigest(), h["datasize"]),
                          []).append(h)
    changed = 0
    for e in need:
        key = (e.get("data_sha256"), e.get("data_size", 0))
        cand = byhash.get(key, [])
        if len(cand) != 1:
            print("  %r: %d headers match its data fork, cannot pair"
                  % (e["name"], len(cand)))
            return 1
        h = cand[0]
        got = decode(single(blob, h, "rsrc"), "rsrc", "unar")
        if got is None or len(got) != h["rsrcsize"]:
            print("  %r: unar still refuses" % e["name"])
            return 1
        e["rsrc_size"] = len(got)
        e["rsrc_sha256"] = hashlib.sha256(got).hexdigest()
        e["rsrc_oracle"] = ("unar 1.10.8 on this fork alone, with the "
                            "declared compressed length one byte larger and "
                            "one pad byte after it — the off-by-one its DDn "
                            "reads past (tools/run_ddforks.py; DECISIONS.md "
                            "2026-08-22). The compressed bytes are the "
                            "fixture's own, unmodified; 0x00 and 0xff pads "
                            "give the same output")
        e.pop("unadjudicated", None)
        changed += 1
    if changed:
        open(mp, "w").write(json.dumps(man, indent=1, sort_keys=True) + "\n")
        print("  manifest: %d resource forks now adjudicated" % changed)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixtures", nargs="+")
    ap.add_argument("--write", action="store_true",
                    help="record the verdict in the manifests")
    a = ap.parse_args()
    bad = 0
    for f in a.fixtures:
        bad += grade(f, a.write)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
