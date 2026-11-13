#!/usr/bin/env python3
"""retake_budgets.py — re-take every size this tree asserts about its builds.

A change that moves the application's resident code, its A5 world or an
overlay image moves a dozen figures at once: the ratchets tools/build_mac.sh
holds each configuration to, what tools/run_tiers.py computes every budget
from, what tools/check_app_size.py watches, and every grant in FORMATS.md's
*What each format is granted*. They used to be moved by hand, in four files,
a paragraph of history each; adding or removing a format meant all of them.

This builds the three configurations (or reads the builds already there),
measures them, and rewrites:

  * tools/budgets.txt, the MEASURED figures only — the machine's
    (TIERS_MACHINE_*, OVL_RESIDUE) are the emulator's to re-take, and a
    ceiling with headroom (UNC_MAC_A5_LAZY) moves only if a build passes it;
  * FORMATS.md: every `<!-- gain: ... -->` figure, the sentences
    tools/check_docs.py holds to OVL_SAVED and BUNDLE, and the bundle's
    images-and-index sentence.

It prints what moved, for the commit message, which must say what the bytes
bought: running this IS the acknowledgement the ratchets exist to force.
Then run tools/run_tiers.py --check, which says whether a tier's tally moved.

    tools/retake_budgets.py             # build all three, then re-take
    tools/retake_budgets.py --no-build  # re-take from build/mac* as they are
    tools/retake_budgets.py --dry-run   # say what would move, write nothing

WHAT IT CANNOT SEE: a tier's budget on the machine. TIERS is derived from
TIERS_MACHINE less TIERS_CONTROL, as it has been since 2026-10-09 between
re-takes; when a change moves resident bytes OUTSIDE the CODE + A5 unit
(resource map entries, the jump table), only the emulator measures it
(tools/vmac/README.md, the budget probe).
"""

import argparse
import glob
import importlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import budgets  # noqa: E402

BUILDS = {
    # name: (build dir, environment)
    "eager": ("build/mac", {"UNC_AT_OVERLAY": "1"}),
    "lazy": ("build/mac-lazy", {"UNC_AT_OVERLAY": "1", "UNC_OVL_LAZY": "1"}),
    "resident": ("build/mac-resident",
                 {"UNC_AT_OVERLAY": "1", "UNC_OVL_RESIDENT": "1"}),
}
TOOLCHAIN = os.environ.get("RETRO68", "/opt/Retro68-build/toolchain")


def die(msg):
    raise SystemExit("retake_budgets: " + msg)


def build(name):
    d, env = BUILDS[name]
    e = dict(os.environ, UNC_MAC_BUILD_DIR=d,
             # no ceiling: this is the step that re-takes them
             UNC_MAC_MAX_CODE="999999999", UNC_MAC_MAX_A5="999999999", **env)
    r = subprocess.run(["sh", "tools/build_mac.sh"], cwd=ROOT, env=e,
                       capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stdout[-3000:] + r.stderr[-3000:])
        die("the %s build failed" % name)


def code_a5(builddir):
    """CODE and A5 the way tools/build_mac.sh reads them: `size`'s text less
    the stripped MacsBug names, and data + bss."""
    size = os.path.join(TOOLCHAIN, "bin", "m68k-apple-macos-size")
    gdb = os.path.join(ROOT, builddir, "MacExtract.code.bin.gdb")
    if not os.access(size, os.X_OK):
        die("no %s (Retro68)" % size)
    if not os.path.exists(gdb):
        die("no %s — build it, or drop --no-build" % gdb)
    row = subprocess.run([size, gdb], capture_output=True,
                         text=True).stdout.splitlines()[1].split()
    names = 0
    for line in subprocess.run([size, "-A", gdb], capture_output=True,
                               text=True).stdout.splitlines():
        c = line.split()
        if c and c[0] == ".strippedmacsbugnames":
            names = int(c[1])
    return int(row[0]) - names, int(row[1]) + int(row[2])


def measure():
    m = {}
    for name in BUILDS:
        m[name] = code_a5(BUILDS[name][0])
    ship = os.path.join(ROOT, BUILDS["eager"][0])
    images = {}
    for p in sorted(glob.glob(os.path.join(ship, "ovl_*.bin"))):
        n = os.path.basename(p)[len("ovl_"):-len(".bin")]
        if n.startswith("bundle"):
            continue
        images[n.upper()] = os.path.getsize(p)
    new = {
        "UNC_MAC_CODE_DEFAULT": m["resident"][0],
        "UNC_MAC_A5_DEFAULT": m["resident"][1],
        "UNC_MAC_CODE_EAGER": m["eager"][0],
        "UNC_MAC_A5_EAGER": m["eager"][1],
        "UNC_MAC_CODE_LAZY": m["lazy"][0],
        "TIERS_CONTROL": sum(m["resident"]),
        "OVL_SAVED": sum(m["resident"]) - sum(m["eager"]),
        "BUNDLE": os.path.getsize(os.path.join(ship, "ovl_bundle.bin")),
        "APP_CODE_FILE": os.path.getsize(os.path.join(ship,
                                                      "MacExtract.code.bin")),
        "APP_BUNDLE_FILE": os.path.getsize(os.path.join(ship,
                                                        "ovl_bundle.bin")),
    }
    for n, v in images.items():
        new["IMAGE_" + n] = v
    return new, m["lazy"][1]


def rewrite_budgets(new, lazy_a5, old, dry):
    """budgets.txt with the measured figures replaced in place; an image the
    build no longer has is removed, a new one added after the last."""
    text = open(budgets.PATH, encoding="utf-8").read().split("\n")
    out, seen, last_image = [], set(), None
    for line in text:
        m = budgets.ROW.match(line)
        if m:
            k = m.group(1)
            if k.startswith("IMAGE_") and k not in new:
                continue                          # an image that left
            if k == "UNC_MAC_A5_LAZY" and lazy_a5 > old[k]:
                new[k] = lazy_a5                   # a ceiling passed
            if k in new:
                line = re.sub(r"=-?\d+", "=%d" % new[k], line, count=1)
                seen.add(k)
            if k.startswith("IMAGE_"):
                last_image = len(out)
        out.append(line)
    added = [k for k in new if k not in seen]
    for k in added:
        if not k.startswith("IMAGE_") or last_image is None:
            die("%s is measured and tools/budgets.txt has no line for it" % k)
        last_image += 1
        out.insert(last_image, "%s=%d" % (k, new[k]))
    if not dry:
        open(budgets.PATH, "w", encoding="utf-8").write("\n".join(out))


WORDS = ("zero one two three four five six seven eight nine ten eleven "
         "twelve thirteen fourteen fifteen sixteen seventeen eighteen "
         "nineteen twenty").split()


def rewrite_formats(dry):
    """FORMATS.md's figures from the budgets just written."""
    import run_tiers
    importlib.reload(budgets)
    run_tiers = importlib.reload(run_tiers)
    path = os.path.join(ROOT, "FORMATS.md")
    text = open(path, encoding="utf-8").read()
    moved = []

    def gain_sub(m):
        names, bold, sign, num = m.groups()
        old = int(num.replace(",", "")) * (1 if sign == "+" else -1)
        ids = [] if names.split() == ["bundle"] else \
            ["OVL_ID_" + n.upper() for n in names.split()]
        gone = [i for i in ids if i not in run_tiers.IMAGES]
        if gone:
            die("FORMATS.md grants a figure for {%s}, and the build has no %s: "
                "remove or correct that row of *What each format is granted* "
                "(nothing was written)"
                % (names, ", ".join("ovl_%s" % i[len("OVL_ID_"):].lower()
                                    for i in gone)))
        new = run_tiers.gain(ids)
        if new != old:
            moved.append("grant {%s}: %+d -> %+d" % (names, old, new))
        s = "{:,}".format(abs(new))
        return "<!-- gain: %s -->%s%s%s B" % (
            names, bold, "+" if new >= 0 else "−", s)

    text = re.sub(r"<!-- gain: ([a-z ]+) -->(\**)([+−-])([\d,]+) B",
                  gain_sub, text)

    def grant_sub(m):
        tier, names, bold, num = m.groups()
        ids = [] if names.split() == ["bundle"] else \
            ["OVL_ID_" + n.upper() for n in names.split()]
        gone = [i for i in ids if i not in run_tiers.IMAGES]
        if gone or tier not in run_tiers.TIERS:
            die("FORMATS.md grants a figure at %s for {%s}, which this build "
                "cannot price: correct that sentence (nothing was written)"
                % (tier, names))
        new = run_tiers.TIERS[tier][0] + run_tiers.gain(ids)
        old = int(num.replace(",", ""))
        if new != old:
            moved.append("grant at %s {%s}: %d -> %d" % (tier, names, old,
                                                         new))
        return "<!-- grant: %s %s -->%s%s B" % (tier, names, bold,
                                                "{:,}".format(new))

    text = re.sub(r"<!-- grant: ([A-Za-z0-9-]+) ([a-z ]+) -->(\**)([\d,]+) B",
                  grant_sub, text)
    fig = "{:,}".format
    for pat, val in (
            (r"(the )([\d,]+)( B of `CODE` and A5 the shipped build does not "
             r"carry)", run_tiers.OVL_SAVED),
            (r"(The shipped pair is \*\*)([\d,]+)( B\*\*)",
             run_tiers.OVL_SAVED)):
        text, n = re.subn(pat, lambda m: m.group(1) + fig(val) + m.group(3),
                          text, count=1)
        if not n:
            die("FORMATS.md has no sentence matching %r" % pat)
    text, n = re.subn(r"([\d,]+)( B held against )([\d,]+)( B saved)",
                      lambda m: fig(run_tiers.BUNDLE) + m.group(2)
                      + fig(run_tiers.OVL_SAVED) + m.group(4), text, count=1)
    if not n:
        die("FORMATS.md has no 'held against ... saved' sentence")
    imgs = run_tiers.IMAGES
    total = sum(imgs.values())
    text, n = re.subn(
        r"The bundle is \*\*[\d,]+ B\*\* — the \w+ images sum to [\d,]+ B, "
        r"so its\nindex costs \*\*[\d,]+ B\*\*",
        "The bundle is **%s B** — the %s images sum to %s B, so its\nindex "
        "costs **%s B**" % (fig(run_tiers.BUNDLE),
                           WORDS[len(imgs)] if len(imgs) < len(WORDS)
                           else str(len(imgs)), fig(total),
                           fig(run_tiers.BUNDLE - total)), text, count=1)
    if not n:
        die("FORMATS.md has no bundle/images/index sentence")
    if not dry:
        open(path, "w", encoding="utf-8").write(text)
    return moved


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from", dest="prefix", metavar="PREFIX",
                    help="read PREFIX-eager, PREFIX-lazy and PREFIX-resident "
                         "instead of build/mac* (implies --no-build)")
    a = ap.parse_args()
    if a.prefix:
        a.no_build = True
        for name in BUILDS:
            BUILDS[name] = ("%s-%s" % (a.prefix, name), BUILDS[name][1])
    if not a.no_build:
        for name in BUILDS:
            print("retake_budgets: building %s" % name)
            build(name)
    old = budgets.load()
    old_text = open(budgets.PATH, encoding="utf-8").read()
    new, lazy_a5 = measure()
    rewrite_budgets(new, lazy_a5, old, a.dry_run)
    lines = []
    for k in sorted(set(old) | set(new)):
        if k in new and old.get(k) != new[k]:
            lines.append("%s: %s -> %d (%+d)" % (
                k, old.get(k, "none"), new[k], new[k] - old.get(k, 0)))
        elif k.startswith("IMAGE_") and k not in new:
            lines.append("%s: %d -> gone" % (k, old[k]))
    if a.dry_run:
        for line in lines:
            print("  " + line)
        print("retake_budgets: --dry-run, nothing written")
        return 0
    try:
        moved = rewrite_formats(False)
    except SystemExit:
        # FORMATS.md is written last and only whole; put budgets.txt back so
        # that a failed retake leaves both files as they were.
        open(budgets.PATH, "w", encoding="utf-8").write(old_text)
        raise
    if not lines and not moved:
        print("retake_budgets: every figure agrees with the builds")
        return 0
    if lines:
        print("retake_budgets: tools/budgets.txt")
    for line in lines:
        print("  " + line)
    if moved:
        print("retake_budgets: FORMATS.md, *What each format is granted*")
        for line in moved:
            print("  " + line)
    print("retake_budgets: now tools/run_tiers.py --check, and say in the "
          "commit what the bytes bought")
    return 0


if __name__ == "__main__":
    sys.exit(main())
