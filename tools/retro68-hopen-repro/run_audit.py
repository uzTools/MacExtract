#!/usr/bin/env python3
"""run_audit.py — boot GlueAudit with a blank HFS and a blank MFS test disk
and photograph what it prints (README.md, *glue_audit*).

    run_audit.py BUILD/GlueAudit.bin --system 6|7|3 [--emu mv-4M] [--wait 60]

System 6.0.8 and 7.0.1 launch it as the startup shell (mkboot.py); System
3.0 ignores the shell name, so there it goes on Apple's MFS boot disk AS the
Finder (tools/vmac/README.md). The screenshot is read by eye.
"""
import argparse, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
VMAC = os.path.join(HERE, "..", "vmac")
sys.path.insert(0, VMAC)
import run as R                                              # noqa: E402
import guard                                                 # noqa: E402
from interactive import Mac                                  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("app")
    ap.add_argument("--system", choices=("3", "6", "7"), default="6")
    ap.add_argument("--emu", default="mv-4M")
    ap.add_argument("--wait", type=int, default=60)
    a = ap.parse_args()

    work = guard.run_dir("glueaudit-sys%s" % a.system)
    mkmfs = os.path.join(VMAC, "mkmfs.py")
    boot = os.path.join(work, "boot.img")
    if a.system == "3":
        sysbin = os.path.join(work, "System30mfs.bin")
        R.sh(sys.executable, mkmfs, "--extract", "System",
             os.path.join(R.VMAC_HOME, "Sys30MFS.img"), sysbin)
        R.sh(sys.executable, mkmfs, boot, "--boot",
             os.path.join(R.VMAC_HOME, "Sys30MFS.img"),
             "--name", "System Software", sysbin, a.app + ":Finder")
    else:
        R.sh(sys.executable, os.path.join(VMAC, "mkboot.py"),
             os.path.join(R.VMAC_HOME,
                          "System6.hfv" if a.system == "6" else "Sys7.img"),
             a.app, boot, "--app-name", "GlueAudit")
    hfs = os.path.join(work, "gluehfs.img")
    with open(hfs, "wb") as f:
        f.truncate(800 * 1024)
    R.sh("hformat", "-l", "GlueHFS", hfs)
    R.sh("humount", hfs)       # hformat leaves it current in ~/.hcwd
    mfs = os.path.join(work, "gluemfs.img")
    R.sh(sys.executable, mkmfs, mfs, "--name", "GlueMFS")

    mac = Mac(boot, a.emu, work, extra=(hfs, mfs))
    try:
        shot = None
        for t in range(10, a.wait + 1, 10):
            time.sleep(10)
            shot = os.path.join(work, "t%03d.png" % t)
            mac.dpy.screenshot(shot)
        print(shot)
    finally:
        guard.reap(mac.proc)
        mac.dpy.close()


if __name__ == "__main__":
    main()
