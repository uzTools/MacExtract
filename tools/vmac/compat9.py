#!/usr/bin/env python3
"""compat9.py — StuffIt 5.5.1 and 7.0.3 over the subjects README.md's table names.

README.md's comparison table had five cells in the two Deluxe columns that
rested on documentation or on nothing: StuffIt Deluxe 2.0's Optimizers and
ciphers, encrypted Compact Pro, and a `message/partial` set. This asks each
box's own StuffIt Expander, with its own engine and translators, on the Mac
OS 9.2 guest `sitzip.py` assembles them on (FORMATS.md, *Compared with
StuffIt Expander 4.0.2*, has the results):

    compat9.py --assemble 55 -o <dir>     boot + transfer volume; no emulator
    compat9.py --boot -o <dir>            start the guest, detached
    # ... drive it with os9mouse.Mac(attach=True), looking at each frame
    compat9.py --stop -o <dir>            kill the pid --boot recorded
    compat9.py --read -o <dir>            what each subject's folder holds now

**Every subject is in a folder of its own**, because most of them expand
to the same name (`Subject`, `MacROT13.cpt`) and the volume is read once,
at the end. **Every subject's creator is `SITx`**, the signature of both
Expanders, so the Finder's Cmd-Down hands it to the Expander as an `odoc`
— the keyboard route, with no Expand dialog and no pointer.

The run is driven by hand, frame by frame, rather than scripted: what
comes up after each subject (a password prompt, an alert, nothing) is the
measurement, and a scripted Return into the Finder renames whatever is
selected (tools/vmac/README.md, *Four things that each cost a boot*).

What it cannot see
------------------
- **The Deluxe APPLICATION.** It runs each box's Expander, which is what
  the box hands an archive to; 5.5's Deluxe will not start on an assembled
  installation (*What `--probe` measured*).
- **Why a reader refused**, beyond the text it puts on screen.
"""
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import run as R                                              # noqa: E402
import os9                                                   # noqa: E402
import os9mouse                                              # noqa: E402
import sitzip                                                # noqa: E402
from arcmac import macbinary                                 # noqa: E402
from superdisk import read_forks                             # noqa: E402

SPEC = os.path.join(R.VMAC_HOME, "specimens")
SUBJ = os.path.join(os.path.dirname(R.VMAC_HOME), "compat", "subj")


def mb_forks(path):
    import struct
    b = open(path, "rb").read()
    dl, rl = struct.unpack(">II", b[83:91])
    p = 128 + (dl + 127) // 128 * 128
    return b[65:69].decode("mac-roman"), b[128:128 + dl], b[p:p + rl]


# (folder, name on the volume, host file, type, password or None)
def subjects():
    s = []
    for folder, rel, pw in (
            ("c0", "make2/Plain.sit.bin", None),
            ("o1", "make2/Optimized.sit.bin", None),       # Text 1
            ("o2", "paintmake/OptPaint.sit.bin", None),    # MacPaint 1
            ("o3", "mods5/OptSound.sit.bin", None),        # Sound 1
            ("o4", "mods5/OptPhoto.sit.bin", None),        # Photoshop 1
            ("o5", "ps-jpeg1/JpegPS.sit.bin", None),       # JPEG Lossy
            ("e1", "psdes1/DesT.sit.bin", "swordfish"),     # DES
            ("e2", "psdes1/NewdeT.sit.bin", "swordfish"),   # NewDE
            ("e3", "psex2/EncA.sit.bin", "swordfish"),      # PassLock
            ("e4", "psex2/EncB.sit.bin", "swordfish"),      # NewDEx
            ("e5", "psex2/EncC.sit.bin", "swordfish")):     # DESex
        s.append((folder, os.path.basename(rel)[:-4],
                  os.path.join(SPEC, "sitopt", rel), "macbin", pw))
    s.append(("k1", "Made.cpt", os.path.join(SPEC, "cptmade", "Made.cpt"),
              "PACT", "ohsecret"))
    for n in ("rot13.mime.01", "rot13.mime.02", "rot13.mime.03"):
        s.append(("m1", n, os.path.join(SUBJ, n), "TEXT", None))
    s.append(("m2", "single.mime", os.path.join(SUBJ, "rot13-single.mime"),
              "TEXT", None))
    s.append(("h1", "posted.hqx", os.path.join(SUBJ, "rot13-posted.hqx"),
              "TEXT", None))
    return s


def assemble(ver, outdir):
    boot, xfer = sitzip.assemble(ver, outdir)
    v = sitzip.Vol(xfer, partition=1)
    try:
        for folder, name, host, kind, _pw in subjects():
            v.mkdir(folder)
            if kind == "macbin":
                t, d, r = mb_forks(host)
            else:
                t, d, r = kind, open(host, "rb").read(), b""
            v.put(macbinary(name, t, "SITx", d, r), "%s:%s" % (folder, name))
    finally:
        v.close()
    print("compat9: %d subjects on %s" % (len(subjects()), xfer))


def boot(outdir):
    disks = [os.path.join(outdir, "boot.img"),
             os.path.join(outdir, "transfer.img")]
    argv = ["qemu-system-ppc", "-M", "mac99,via=pmu", "-m", "512",
            "-boot", "c", "-g", "1024x768x32", "-display", "none",
            "-device", "usb-mouse",
            "-monitor", "unix:%s,server,nowait" % os9mouse.MON]
    for i, d in enumerate(disks):
        argv += ["-drive", "file=%s,format=raw,media=disk,index=%d" % (d, i)]
    if os.path.exists(os9mouse.MON):
        os.remove(os9mouse.MON)
    log = open(os.path.join(outdir, "qemu.log"), "w")
    p = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                         start_new_session=True)
    open(os.path.join(outdir, "qemu.pid"), "w").write(str(p.pid))
    print("compat9: qemu pid %d" % p.pid)


def stop(outdir):
    pid = int(open(os.path.join(outdir, "qemu.pid")).read())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    print("compat9: sent SIGTERM to %d" % pid)


def read(outdir):
    part = os.path.join(outdir, "transfer.hfs")
    os9.hfs_partition(os.path.join(outdir, "transfer.img"), part)
    got = read_forks(part)
    rows = {}
    for path, (t, c, d, r) in sorted(got.items()):
        d, r = d or b"", r or b""
        rows["/".join(path)] = [t, c, len(d), hashlib.md5(d).hexdigest()[:12],
                                len(r), hashlib.md5(r).hexdigest()[:12]]
        print("  %-40s %s/%s d=%-7d %s r=%-7d %s" % (
            "/".join(path), t, c, len(d), rows["/".join(path)][3], len(r),
            rows["/".join(path)][5]))
    json.dump(rows, open(os.path.join(outdir, "volume.json"), "w"), indent=1)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--assemble", choices=sorted(sitzip.DIST))
    p.add_argument("--boot", action="store_true")
    p.add_argument("--stop", action="store_true")
    p.add_argument("--read", action="store_true")
    p.add_argument("-o", "--out", required=True)
    a = p.parse_args()
    if a.assemble:
        assemble(a.assemble, a.out)
    elif a.boot:
        boot(a.out)
    elif a.stop:
        stop(a.out)
    elif a.read:
        read(a.out)


if __name__ == "__main__":
    main()
