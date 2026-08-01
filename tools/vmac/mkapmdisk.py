#!/usr/bin/env python3
"""mkapmdisk.py — build a hard-disk image Mac OS on PowerPC will actually mount.

Mini vMac mounts a bare HFS volume, so the System 6 harness never needed a
partition map. Mac OS 9 does: its ATA driver enumerates an Apple Partition
Map, and a driverless image is either ignored or offered up as "this disk is
unreadable". This builds the disk that carries the application and a test
archive into Mac OS 9.

    mkapmdisk.py <donor.img> <out.img> <size-MB> <volume-name>
                 [--data FILE:MACNAME]... [--macbinary FILE:MACNAME]...

**The map and the drivers are cloned verbatim from <donor.img>**, a disk the
target system already mounts (in practice the Mac OS 9 boot image itself).
Only the Apple_HFS entry is repointed, at a freshly hformat'd HFS volume
appended after the cloned head.

That is not laziness, it is the second attempt. The first built a map by hand
from the format documentation — driver descriptor record, an
Apple_partition_map entry, an Apple_HFS entry with the status word copied off
a real disk — and Mac OS 9 silently ignored the result: no volume on the
desktop, no error, nothing to debug. Cloning a head that is known to work and
changing one entry mounts first time. What in the driver partitions the OS
insists on is still unknown, and this tool does not need to know.

Requires the donor's HFS partition to start no earlier than the new volume's
start block, which for any real Apple-partitioned disk it does.
"""
import os, struct, subprocess, sys, tempfile, shutil

BLK = 512


def clone_head(donor, out_blocks, volname, hfs_start, hfs_blocks):
    """Everything before the donor's HFS partition, with the map repointed."""
    head = bytearray(open(donor, "rb").read(hfs_start * BLK))
    if head[0:2] != b"ER":
        raise SystemExit(f"mkapmdisk: {donor} has no driver descriptor record")
    struct.pack_into(">I", head, 4, out_blocks)          # sbBlkCount
    seen_hfs = False
    for i in range(1, 64):
        off = BLK * i
        if head[off:off + 2] != b"PM":
            break
        ptype = bytes(head[off + 48:off + 80]).split(b"\0")[0].decode("ascii")
        if ptype == "Apple_HFS":
            struct.pack_into(">II", head, off + 8, hfs_start, hfs_blocks)
            head[off + 16:off + 48] = volname.encode("mac_roman").ljust(32, b"\0")
            struct.pack_into(">I", head, off + 84, hfs_blocks)   # pmDataCnt
            seen_hfs = True
        elif ptype == "Apple_Free":
            # Its blocks are past the end of the new, smaller disk.
            head[off:off + BLK] = b"\0" * BLK
    if not seen_hfs:
        raise SystemExit(f"mkapmdisk: {donor} has no Apple_HFS partition to clone")
    return bytes(head)


def find_hfs_start(donor):
    d = open(donor, "rb").read(BLK * 64)
    for i in range(1, 64):
        off = BLK * i
        if d[off:off + 2] != b"PM":
            break
        if d[off + 48:off + 80].split(b"\0")[0] == b"Apple_HFS":
            return struct.unpack(">I", d[off + 8:off + 12])[0]
    raise SystemExit(f"mkapmdisk: no Apple_HFS partition in {donor}")


def main():
    argv = sys.argv[1:]
    files = []
    for flag, macbin in (("--data", False), ("--macbinary", True)):
        while flag in argv:
            i = argv.index(flag)
            host, _, macname = argv[i + 1].partition(":")
            if not macname:
                raise SystemExit(f"mkapmdisk: {flag} wants FILE:MACNAME")
            files.append((host, macname, macbin))
            del argv[i:i + 2]
    if len(argv) != 4:
        raise SystemExit(__doc__)
    donor, out, size_mb, volname = argv[0], argv[1], int(argv[2]), argv[3]

    hfs_start = find_hfs_start(donor)
    hfs_blocks = size_mb * 1024 * 1024 // BLK
    total = hfs_start + hfs_blocks

    tmp = tempfile.mkdtemp(prefix="apm-")
    try:
        vol = os.path.join(tmp, "vol.hfs")
        with open(vol, "wb") as f:
            f.truncate(hfs_blocks * BLK)
        env = dict(os.environ, HOME=tmp)
        run = lambda *a: subprocess.run(a, check=True, capture_output=True, env=env)
        run("hformat", "-l", volname, vol)
        if files:
            run("hmount", vol)
            for host, macname, macbin in files:
                run("hcopy", "-m" if macbin else "-r", host, f"{volname}:{macname}")
            run("humount", vol)
        with open(out, "wb") as f:
            f.write(clone_head(donor, total, volname, hfs_start, hfs_blocks))
            with open(vol, "rb") as v:
                shutil.copyfileobj(v, f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"mkapmdisk: {out} — {size_mb} MB, Apple_HFS volume {volname!r} at "
          f"block {hfs_start}, {len(files)} file(s); map cloned from {donor}")


if __name__ == "__main__":
    main()
