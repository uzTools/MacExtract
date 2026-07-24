#!/usr/bin/env python3
"""vmac_check.py <manifest.json> <macscreen.png>

Verify one Mini vMac autotest run. Decodes the on-screen result grid
(tools/decode_grid.py) and compares its aggregate to what the oracle says the
extraction should produce:

  nfiles         count of non-directory entries
  ret == 0       (UNC_OK) and errors == 0
  sumDataCRC     sum mod 2^32 of each data fork's CRC-32
  totalDataLen   sum of data-fork lengths
  sumRsrcCRC     sum of each resource fork's CRC-32, reserved header (bytes
                 16..127) masked to 0 — the OS stamps that region per session
  totalRsrcLen   sum of resource-fork lengths

Prints PASS/FAIL and the engine's on-Mac peak heap use. Exit 0 iff PASS.
"""
import sys, os, zlib, json, subprocess, tempfile, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_grid import decode

# The reference is the SAME engine's Linux CLI, single-level (`-nr`): the Mac
# shell calls unc_extract once (no auto-unwrap loop), so `-nr` reproduces its
# exact output. The CLI output is itself verified byte-exact against the
# committed oracle manifests by the main differential suite.
CLI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "build", "rel", "unclassic")


def crc(b):
    return zlib.crc32(b) & 0xFFFFFFFF


def mask_reserved(rsrc):
    b = bytearray(rsrc)
    for i in range(16, min(128, len(b))):
        b[i] = 0
    return bytes(b)


def expected_aggregate(manifest_path):
    man = json.load(open(manifest_path))
    fixture = os.path.join(os.path.dirname(manifest_path), "..", man["fixture"])
    tmp = tempfile.mkdtemp()
    try:
        subprocess.run([CLI, "x", "-nr", fixture, "-o", tmp],
                       capture_output=True, timeout=180)
        nfiles = sdc = sdl = src = srl = 0
        for root, _d, files in os.walk(tmp):
            for f in files:
                if f.endswith(".rsrc"):
                    continue
                p = os.path.join(root, f)
                data = open(p, "rb").read()
                nfiles += 1
                sdc = (sdc + crc(data)) & 0xFFFFFFFF
                sdl += len(data)
                rp = p + ".rsrc"
                rsrc = open(rp, "rb").read() if os.path.exists(rp) else b""
                src = (src + crc(mask_reserved(rsrc))) & 0xFFFFFFFF
                srl += len(rsrc)
        return nfiles, sdc, sdl, src, srl
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    manifest, png = sys.argv[1], sys.argv[2]
    got = decode(png)
    if got is None:
        print("FAIL: no valid result grid on screen (app bombed or miscalibrated)")
        return 1
    nfiles, ret, errors, sdc, sdl, src, srl, peak = got
    enf, esdc, esdl, esrc, esrl = expected_aggregate(manifest)

    checks = [
        ("nfiles", nfiles, enf),
        ("ret==0", ret, 0),
        ("errors==0", errors, 0),
        ("sumDataCRC", sdc, esdc),
        ("totalDataLen", sdl, esdl),
        ("sumRsrcCRC", src, esrc),
        ("totalRsrcLen", srl, esrl),
    ]
    ok = True
    for name, g, e in checks:
        good = (g == e)
        ok = ok and good
        if not good:
            print(f"  {name:14s} got {g} (0x{g:08X}) want {e} (0x{e:08X})  MISMATCH")
    tag = "PASS" if ok else "FAIL"
    print(f"{tag}: {nfiles} file(s), peak heap {peak} B "
          f"({peak/1024.0:.1f} KB), data {sdl} B, rsrc {srl} B")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
