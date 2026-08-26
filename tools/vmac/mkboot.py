#!/usr/bin/env python3
"""mkboot.py — build the pristine System 6.0.8 boot image the autotest runs on.

Takes the stock image fetched by setup.sh and produces a boot volume that

  1. contains ONLY System + Finder in its System Folder (every INIT, cdev and
     leftover application is deleted), so nothing but the OS competes for RAM
     — this matters on the 1 MB floor-target machine, where a handful of INITs
     is the difference between a result and a dead machine, and it is what
     makes the peak-heap numbers comparable between runs; and
  2. launches the macextract autotest application AT BOOT instead of the
     Finder, by rewriting the boot blocks' shell name (offset 0x1A: a Str15
     naming the application the ROM hands control to, normally "Finder").
     No mouse automation, no double-click, no Finder — the machine boots
     straight into the test.

Usage:
    mkboot.py <stock.hfv> <app.bin> <out.hfv> [--data FILE:MACNAME]...
              [--macbin FILE:MACNAME]... [--app-name NAME] [--finder]

<app.bin> is the MacBinary produced by a Retro68 build (tools/vmac/run.py
builds macextract's); its resource fork is what makes it an application, so it
is copied in MacBinary mode.

--data copies a host file into the volume as a plain data fork. MACNAME may
name subfolders ("Archives:archive.sit"), which are created as needed. The
interactive driver uses it to put an archive where SFGetFile will list it: the
interactive application extracts next to the archive, so that volume has to be
writable, and the boot volume is the one SFGetFile opens on by default.

--macbin is the same, for a host file in MacBinary form: both forks and the
type/creator survive. A data-fork copy is enough for anything this project's
own application opens, because it opens what it is given by name — but another
application's Standard File filters on TYPE, so an archive copied with --data
is invisible to it. That is what this is for (tools/vmac/cptsegment.py).

--app-name sets the application's name on the volume (default "MacExtract"),
which is also the boot-block shell name.

--finder leaves the Finder as the boot shell and puts the application at the
volume ROOT, so it has to be launched by double-clicking it like any other
application. Replacing the Finder is a big change to the environment — nothing
mounts disks, no other process competes for the heap — and some questions can
only be answered outside it, so this is the arrangement for those.
"""
import os, re, shutil, subprocess, sys, tempfile

# "Feb 16  1994" (older than a year) or "Jul 18 17:20" (recent) — both exactly
# 12 characters, always followed by one space and then the item's name.
LISTING_DATE = re.compile(r"[A-Z][a-z]{2} [ \d]\d (?: \d{4}|\d\d:\d\d) (.+)$")

DEFAULT_APP = "MacExtract"       # also the boot-block shell name, below
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
    # The Desktop file first, and explicitly, because `ls` cannot see it:
    # `hdir` hides invisible files unless given -a, and the Desktop file is
    # invisible. It is the Finder's cache of which application owns which
    # icon, and a stale one is why an application with a correct 'BNDL',
    # a matching creator and hasBundle set still draws the generic diamond
    # (measured 2026-08-24 — interactive.py --e2e photographed exactly
    # that, twice, before this line existed). The Finder rebuilds it on the
    # next boot, which is what holding Cmd-Option at startup does by hand.
    hfs.run("hdel", hfs.path("Desktop"), check=False)
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


def verify_stripped(hfs, expect):
    """The property that decides how much RAM the boot costs: System 6 loads
    INITs, cdevs and drivers from the FILES sitting directly in the System
    Folder. Assert that only the OS — plus the application, when it is the
    boot shell and so has to live in the blessed folder — remains there."""
    files = {name for isdir, name in hfs.ls(hfs.path(SYS_FOLDER)) if not isdir}
    if files != expect:
        raise SystemExit(f"mkboot: System Folder holds {sorted(files)}, "
                         f"expected {sorted(expect)}")


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
    argv = sys.argv[1:]
    extras = []
    app_name = DEFAULT_APP
    finder = False
    for flag, mode in (("--data", "-r"), ("--macbin", "-m")):
        while flag in argv:
            i = argv.index(flag)
            spec = argv[i + 1]
            host, _, macname = spec.partition(":")
            if not macname:
                raise SystemExit(
                    f"mkboot: {flag} wants FILE:MACNAME, got {spec!r}")
            extras.append((host, macname, mode))
            del argv[i:i + 2]
    if "--app-name" in argv:
        i = argv.index("--app-name")
        app_name = argv[i + 1]
        del argv[i:i + 2]
    if "--finder" in argv:
        finder = True
        argv.remove("--finder")
    if len(argv) != 3:
        raise SystemExit(__doc__)
    stock, appbin, out = argv
    shutil.copyfile(stock, out)
    hfs = HFS(out)
    try:
        strip_system_folder(hfs)
        if finder:
            # At the ROOT, where the Finder's volume window shows it.
            hfs.run("hcopy", "-m", appbin, hfs.path(app_name))
            verify_stripped(hfs, KEEP)
        else:
            # The shell application is looked up in the blessed (System) folder.
            hfs.run("hcopy", "-m", appbin, hfs.path(SYS_FOLDER, app_name))
            verify_stripped(hfs, KEEP | {app_name})
        for host, macname, mode in extras:
            # MACNAME may name subfolders, "Archives:archive.sit". Create them:
            # putting the archive somewhere OTHER than the volume root is the
            # only arrangement in which a mishandled working-directory refNum
            # is visible at all — at the root, "the WD" and "the root" are the
            # same directory and a bug cannot show itself.
            parts = macname.split(":")
            for i in range(1, len(parts)):
                hfs.run("hmkdir", hfs.path(*parts[:i]), check=False)
            hfs.run("hcopy", mode, host, hfs.path(*parts))
    finally:
        hfs.close()
    if finder:
        print(f"mkboot: {out} boots to the Finder; {app_name} is at the root")
    else:
        patch_boot_blocks(out, app_name)
        print(f"mkboot: {out} boots straight into {app_name}")


if __name__ == "__main__":
    main()
