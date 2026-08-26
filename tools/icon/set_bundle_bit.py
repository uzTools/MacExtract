#!/usr/bin/env python3
"""set_bundle_bit.py — turn on hasBundle in a built application's Finder info.

The Finder does not look at an application's 'BNDL' unless the file's
hasBundle flag (0x2000) is set, and nothing in the Retro68 chain sets it:
Rez takes `-t` and `-c` for type and creator and has no option for the
Finder flags, so a freshly built application has flags 0x0000.

That failure is silent and complete — every icon resource is present, the
'BNDL' owner matches the creator, and the Finder still draws the generic
application diamond. It was found by booting to a real Finder and looking
(tools/vmac/interactive.py --e2e, e2e-2-volume.png), which is the only way
it could have been found.

Two artifacts need it, because they are produced side by side and travel
separately:

  MacExtract.bin   MacBinary. Flags live at offset 73 (high byte) and 101
                  (low byte), and byte 73 is inside the range the header
                  CRC at 124 covers, so the CRC is recomputed.
  MacExtract.dsk   an HFS image. Rebuilt from the patched MacBinary rather
                  than edited: `hcopy -m` carries the Finder flags across,
                  and hfsutils has no way to set them in place (`hattrib
                  -b` blesses a system folder, which is a different thing
                  entirely). Without hfsutils the image is left alone and
                  this says so rather than failing the build.

Everything downstream inherits from these: mkboot.py copies the MacBinary
onto its boot images with `hcopy -m`, which carries the Finder flags over.
"""
import os
import subprocess
import sys

HAS_BUNDLE = 0x2000


def crc16_xmodem(buf):
    """CRC-16/XMODEM: poly 0x1021, init 0, no reflection, no final xor —
    the same one src/fmt_macbinary.c verifies incoming headers with."""
    crc = 0
    for b in buf:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 \
                else (crc << 1) & 0xFFFF
    return crc


def patch_macbinary(path):
    with open(path, "rb") as f:
        b = bytearray(f.read())
    if len(b) < 128:
        raise SystemExit(f"set_bundle_bit: {path} is not MacBinary")
    before = (b[73] << 8) | b[101]
    if before & HAS_BUNDLE:
        print(f"set_bundle_bit: {os.path.basename(path)} already 0x{before:04X}")
        return
    b[73] |= HAS_BUNDLE >> 8
    crc = crc16_xmodem(bytes(b[:124]))
    b[124] = (crc >> 8) & 0xFF
    b[125] = crc & 0xFF
    with open(path, "wb") as f:
        f.write(bytes(b))
    after = (b[73] << 8) | b[101]
    print(f"set_bundle_bit: {os.path.basename(path)} "
          f"0x{before:04X} -> 0x{after:04X}, CRC 0x{crc:04X}")


def have(tool):
    return any(os.access(os.path.join(d, tool), os.X_OK)
               for d in os.environ.get("PATH", "").split(os.pathsep))


def patch_dsk(path, macbin, volume):
    """Rewrite the floppy image around the already-patched MacBinary."""
    if not (have("hformat") and have("hmount") and have("hcopy")):
        print("set_bundle_bit: no hfsutils — .dsk left alone "
              "(the .bin is what mkboot.py and make_dist.sh copy)")
        return
    size = os.path.getsize(path)
    env = dict(os.environ, HOME=os.path.join(os.path.dirname(path), ".hfs"))
    os.makedirs(env["HOME"], exist_ok=True)
    try:
        with open(path, "wb") as f:
            f.truncate(size)
        subprocess.run(["hformat", "-l", volume, path], check=True,
                       capture_output=True, env=env)
        subprocess.run(["hmount", path], check=True, capture_output=True,
                       env=env)
        subprocess.run(["hcopy", "-m", macbin, ":"], check=True,
                       capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
        print(f"set_bundle_bit: {os.path.basename(path)} rebuilt "
              f"({size} B, volume {volume!r})")
    except subprocess.CalledProcessError as e:
        raise SystemExit("set_bundle_bit: .dsk rebuild failed: "
                         + e.stderr.decode().strip())


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: set_bundle_bit.py <app.bin> "
                         "[<app.dsk> <volume-name>]")
    patch_macbinary(sys.argv[1])
    if len(sys.argv) >= 4:
        patch_dsk(sys.argv[2], sys.argv[1], sys.argv[3])


if __name__ == "__main__":
    main()
