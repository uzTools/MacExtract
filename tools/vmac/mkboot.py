#!/usr/bin/env python3
"""mkboot.py — build the pristine System 6.0.8 boot image the autotest runs on.

Takes the stock image fetched by setup.sh and produces a boot volume that

  1. contains ONLY System + Finder in its System Folder (every INIT, cdev and
     leftover application is deleted), so nothing but the OS competes for RAM
     — this matters on the 1 MB floor-target machine, where a handful of INITs
     is the difference between a result and a dead machine, and it is what
     makes the peak-heap numbers comparable between runs; and
  2. launches the unclassic autotest application AT BOOT instead of the
     Finder, by rewriting the boot blocks' shell name (offset 0x1A: a Str15
     naming the application the ROM hands control to, normally "Finder").
     No mouse automation, no double-click, no Finder — the machine boots
     straight into the test.

Usage:
    mkboot.py <stock.hfv> <unclassic.bin> <out.hfv>

<unclassic.bin> is the MacBinary produced by the UNC_MAC_AUTOTEST build
(tools/vmac/run.py builds it); its resource fork is what makes it an
application, so it is copied in MacBinary mode.
"""
import os, re, shutil, subprocess, sys, tempfile

# "Feb 16  1994" (older than a year) or "Jul 18 17:20" (recent) — both exactly
# 12 characters, always followed by one space and then the item's name.
LISTING_DATE = re.compile(r"[A-Z][a-z]{2} [ \d]\d (?: \d{4}|\d\d:\d\d) (.+)$")

APP_NAME = "unclassic"          # must match the boot-block shell name below
SYS_FOLDER = "System Folder"
KEEP = {"System", "Finder"}     # everything else in the System Folder goes

# Boot block layout (Inside Macintosh II-83, "The Boot Blocks"): a chain of
# Str15 fields naming the files the ROM loads. Only the shell is touched.
BB_SHELL_LEN = 0x1A             # Pascal length byte of bbShellName
BB_SHELL_STR = 0x1B             # its 15 bytes of text
BB_FIELD_MAX = 15


class HFS:
    """hfsutils wrapper. hmount/hcd/hcopy keep their state in $HOME/.hcwd, so
    each instance points HOME at a private temp dir — otherwise two concurrent
    runs (or a stale .hcwd from an earlier one) silently operate on the wrong
    volume."""

    def __init__(self, image):
        self.home = tempfile.mkdtemp(prefix="hfs-")
        self.env = dict(os.environ, HOME=self.home)
        out = self.run("hmount", image).stdout
        m = re.search(r'Volume name is "(.*)"', out)
        if not m:
            raise SystemExit(f"mkboot: cannot read the volume name of {image}")
        self.vol = m.group(1)

    def run(self, *argv, check=True):
        # HFS names are MacRoman bytes, not UTF-8. surrogateescape carries the
        # undecodable ones through unchanged and back out again when a name is
        # handed to the next hfsutils command as an argument.
        return subprocess.run(argv, env=self.env, check=check,
                              capture_output=True, text=True,
                              errors="surrogateescape")

    def path(self, *parts):
        """An ABSOLUTE HFS path. In classic Mac syntax a leading colon means
        *relative to the current directory*, so ":a:b" silently resolves
        against wherever the last hcd left us — prefixing the volume name is
        the only way to be positional."""
        return self.vol + ":" + ":".join(parts)

    def ls(self, path):
        """Names in <path> (absolute), plus a flag for directory-ness."""
        self.run("hcd", path)
        out = self.run("hdir").stdout
        items = []
        for line in out.splitlines():
            if not line or line[0] not in "fd":
                continue
            # "f  TYPE/CREA  dlen  rlen  Mon dd  yyyy  name"
            # "d  n items               Mon dd hh:mm  name"
            # Cutting at fixed columns is fragile and splitting on runs of
            # spaces breaks on names that contain them, so anchor on the
            # 12-character date that always immediately precedes the name.
            m = LISTING_DATE.search(line)
            if m:
                items.append((line[0] == "d", m.group(1)))
        return items

    def close(self):
        self.run("humount", check=False)
        shutil.rmtree(self.home, ignore_errors=True)


def strip_system_folder(hfs):
    """Delete every root-level item except the System Folder, and everything
    inside the System Folder except System and Finder."""
    for isdir, name in hfs.ls(hfs.path()):
        if name == SYS_FOLDER:
            continue
        if isdir:
            rmtree(hfs, hfs.path(name))
        else:
            hfs.run("hdel", hfs.path(name))
    for isdir, name in hfs.ls(hfs.path(SYS_FOLDER)):
        if name in KEEP:
            continue
        if isdir:
            rmtree(hfs, hfs.path(SYS_FOLDER, name))
        else:
            hfs.run("hdel", hfs.path(SYS_FOLDER, name))


def rmtree(hfs, path):
    """Delete a directory and its contents. Iterative (an HFS tree can nest
    arbitrarily and this runs next to an engine that bans recursion)."""
    stack, dirs = [path], []
    while stack:
        d = stack.pop()
        dirs.append(d)
        for isdir, name in hfs.ls(d):
            child = d + ":" + name
            if isdir:
                stack.append(child)
            else:
                hfs.run("hdel", child)
    hfs.run("hcd", hfs.path())           # hrmdir refuses to delete our own cwd
    for d in reversed(dirs):             # deepest first
        # Best-effort: this stock image has at least one directory whose
        # valence disagrees with what hdir enumerates ("8 items", 7 listed),
        # so hrmdir reports "directory not empty" on a directory nothing can
        # list the contents of. An empty-looking leftover folder costs
        # nothing at boot — only files IN THE SYSTEM FOLDER load — and
        # verify_stripped() below checks the property that actually matters.
        hfs.run("hrmdir", d, check=False)


def verify_stripped(hfs):
    """The property that decides how much RAM the boot costs: System 6 loads
    INITs, cdevs and drivers from the FILES sitting directly in the System
    Folder. Assert that only the OS and our application remain there."""
    files = {name for isdir, name in hfs.ls(hfs.path(SYS_FOLDER)) if not isdir}
    want = KEEP | {APP_NAME}
    if files != want:
        raise SystemExit(f"mkboot: System Folder holds {sorted(files)}, "
                         f"expected {sorted(want)}")


def patch_boot_blocks(image, shell_name):
    """Point the boot blocks' shell field at our application."""
    name = shell_name.encode("macroman")
    if len(name) > BB_FIELD_MAX:
        raise SystemExit(f"mkboot: shell name {shell_name!r} exceeds 15 bytes")
    with open(image, "r+b") as f:
        bb = bytearray(f.read(1024))
        if bb[0:2] != b"LK":
            raise SystemExit("mkboot: not a bootable Mac image (no 'LK' signature)")
        bb[BB_SHELL_LEN] = len(name)
        bb[BB_SHELL_STR:BB_SHELL_STR + BB_FIELD_MAX] = name.ljust(BB_FIELD_MAX, b"\0")
        f.seek(0)
        f.write(bb)


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    stock, appbin, out = sys.argv[1:4]
    shutil.copyfile(stock, out)
    hfs = HFS(out)
    try:
        strip_system_folder(hfs)
        # The shell application is looked up in the blessed (System) folder.
        hfs.run("hcopy", "-m", appbin, hfs.path(SYS_FOLDER, APP_NAME))
        verify_stripped(hfs)
    finally:
        hfs.close()
    patch_boot_blocks(out, APP_NAME)
    print(f"mkboot: {out} boots straight into {APP_NAME}")


if __name__ == "__main__":
    main()
