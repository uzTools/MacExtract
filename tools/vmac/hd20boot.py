#!/usr/bin/env python3
"""hd20boot.py — a true Macintosh 512K (64K ROM) with HFS, from floppies.

A 64K ROM has no HFS; Apple's `Hard Disk 20` file supplies it, loaded at
startup from the System Folder of an MFS floppy (FORMATS.md, *A true
Macintosh 512K*). Mini vMac does not emulate the HD20 itself, so a large
HFS disk image in the next drive stands in for it. This writes the boot
floppy and, with --hfs, that volume:

    hd20boot.py BOOT.img --hfs HD.img
    $V/mv-512K/minivmac -r $V/Mac512K.ROM BOOT.img HD.img dist/MacExtract-400K.img

The boot floppy is Apple's MFS System 3.0 (`Sys30MFS.img`: its boot blocks
and System) and the `Hard Disk 20` file from Apple's *HD 20 Startup* disk
(`HD20.img`; tools/vmac/setup.sh fetches both), with its third patch left
out. The file holds three `PTCH` resources: 0 `TFS` (the HFS File Manager),
1 `Dispatch Kernel` and 2 `.Sony`, a floppy driver. With all three the
emulated 512K stops at an empty dialog frame; without `.Sony` it boots and
mounts HFS (measured 2026-11-06; DECISIONS.md 2026-11-06, *the two calls a
64K ROM lacks*). The Finder is the stock one unless a file is given as
`PATH:Finder`, which is how tools/vmac/traptest runs here.

What it CANNOT see: Apple's `.Sony` patch, which a real 512K with an HD20
loads; the HD20's own driver and timing; a System other than 3.0.
"""
import argparse, os, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mkmfs as M                                            # noqa: E402

VMAC = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))


def lift(image, name):
    """One file off an MFS image, as mkmfs.MacFile."""
    img = open(image, "rb").read()
    for e in M.entries_of(img):
        if e["name"] == name:
            _f, ds, dl, _dp, rs, rl, _rp = e["nums"]
            return M.MacFile(name, e["type"], e["creator"], e["flags"],
                             M.read_fork(img, ds, dl) if ds else b"",
                             M.read_fork(img, rs, rl) if rs else b"",
                             *e["dates"])
    raise SystemExit(f"hd20boot: {image} has no {name!r}")


def drop_sony(rsrc):
    """The resource fork with PTCH 2 removed from its map. Layout as
    src/unc_crypt.c's unc_resfork_find reads it (Source: Inside Macintosh:
    More Macintosh Toolbox, "Resource File Format"): the type list at the
    offset at map+24, a count-1 word, then per type its code, count-1 and
    reference list offset; 12-byte references. Only the case this file
    has is handled: one type, PTCH, whose LAST reference is ID 2, so
    lowering the count drops it and nothing else moves."""
    r = bytearray(rsrc)
    _do, mo = struct.unpack(">II", r[:8])
    tlo, = struct.unpack(">H", r[mo + 24:mo + 26])
    ntypes = struct.unpack(">H", r[mo + tlo:mo + tlo + 2])[0] + 1
    t, n1, ref = struct.unpack(">4sHH", r[mo + tlo + 2:mo + tlo + 10])
    last = mo + tlo + ref + 12 * n1
    rid, = struct.unpack(">h", r[last:last + 2])
    if ntypes != 1 or t != b"PTCH" or n1 != 2 or rid != 2:
        raise SystemExit("hd20boot: not the Hard Disk 20 file this expects "
                         f"({ntypes} type(s), {t!r}, {n1 + 1} refs, last ID {rid})")
    struct.pack_into(">H", r, mo + tlo + 6, 1)
    return bytes(r)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("boot", help="the boot floppy to write")
    ap.add_argument("files", nargs="*",
                    help="more MacBinary files for it, PATH or PATH:MACNAME")
    ap.add_argument("--hfs", help="also write a blank HFS volume here")
    ap.add_argument("--hfs-mb", type=int, default=10)
    a = ap.parse_args()
    sys30 = os.path.join(VMAC, "Sys30MFS.img")
    hd20 = lift(os.path.join(VMAC, "HD20.img"), "Hard Disk 20")
    hd20.rsrc = drop_sony(hd20.rsrc)
    files = [lift(sys30, "System"), hd20]
    extra = [s.partition(":") for s in a.files]
    if not any(n == "Finder" for _p, _c, n in extra):
        files.append(lift(sys30, "Finder"))
    files += [M.MacFile.from_macbinary(p, n or None) for p, _c, n in extra]
    boot = open(sys30, "rb").read(2 * M.BLOCK)
    open(a.boot, "wb").write(M.build(files, "System Software", boot))
    print(f"hd20boot: wrote {a.boot}")
    if a.hfs:
        with open(a.hfs, "wb") as f:
            f.truncate(a.hfs_mb * 1024 * 1024)
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home)
            subprocess.run(["hformat", "-l", "Hard Disk", a.hfs], env=env,
                           check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["humount"], env=env, stdout=subprocess.DEVNULL)
        print(f"hd20boot: wrote {a.hfs}, {a.hfs_mb} MB HFS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
