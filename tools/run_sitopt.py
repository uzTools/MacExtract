#!/usr/bin/env python3
"""run_sitopt.py — the optimized archives, graded by the program that wrote them.

StuffIt Deluxe 2.0 could hand a fork to an Optimizer before compressing
it, and this engine's whole reading of where an archive records that is
six header bytes taken out of the application's own code (FORMATS.md,
*Where an archive names the module*). Until 2026-09-28 nothing graded
that reading against an archive, because none existed here.

`tools/vmac/sitopt.py` made eight, over three boots, and this
replays them:

  Plain.sit       the control — no Optimizer, the same subject
  Optimized.sit   `Text 1`, method 2
  OptBetter.sit   `Text 1`, method 5
  unstuffed.bin   what 2.0.1's OWN unstuffer gives back for Optimized.sit
  PlainPaint.sit  the control for the other kind of Optimizer
  OptPaint.sit    `MacPaint 1` over a document MacPaint 2.0 itself drew
  Painting.bin    that document, as MacPaint wrote it
  OptSound.sit    `Sound 1`, over a Sound Designer II file
  OptPhoto.sit    `Photoshop 1`, over a Photoshop document
  OptJpeg.sit     `Photoshop/JPEG Lossy`, over the same document

**The oracle is the writer.** An optimized entry's right answer is not
the file that went in — `Text 1` turns leading spaces into tabs, strips
trailing ones and deletes the resource fork, and none of it is undone
— so "correct" can only mean *what StuffIt Deluxe 2.0.1 itself
produces*, which is why `unstuffed.bin` is in the set. Grading this
against the original subject would fail a correct engine, and grading
it against our own output would pass a broken one.

Six things are asserted, and each one has failed a version of this
engine at some point today:

  1. the control extracts to the subject, both forks, byte for byte;
  2. both optimized entries extract to **2.0.1's own unstuffed bytes**;
  3. neither writes a resource fork — `Text 1` deleted it, the header
     says `rlen` 0, and an engine that invents one is wrong;
  4. the header bytes are what the reading says: `0x40` set on both
     method bytes, 106 and 108 both 255, and 46/47/107/109 zero;
  5. **every module's id is its own.** All four Optimizers that carry
     a 'DCMP' write their resource id into byte 106 — `Sound 1` 1,
     `Photoshop 1` 2, `Photoshop/JPEG Lossy` 3, `MacPaint 1` 4 — and
     each entry is refused with that module NAMED. `Text 1`, the one
     with no 'DCMP', is the only 255. **JPEG Lossy is the case that
     could have broken the rule and does not**: it is lossy, and 255
     is what the application's Get Info pane prints as " lossy", but
     it writes 3;
  6. **the declared lengths**, which are what makes the rule a rule
     rather than a convention — see 4b in the code; and
  7. **the other kind of Optimizer.** `MacPaint 1` carries a 'DCMP', so
     something CAN undo it: it writes its own module id, 4, and the
     entry is refused by name. Aladdin's Engine refuses it too —
     *"Items that were encrypted or compressed with an optimizer or
     compressor will be skipped. The Engine does not currently support
     this. Please use StuffIt Deluxe instead."* — and decoded the
     `Text 1` one without a murmur, so this engine's rule is the
     Engine's rule. Its control must still extract byte for byte.

What this CANNOT see:

- **whether the module would restore the original.** Refusing is graded
  as agreement with Aladdin's Engine, not by running a 'DCMP'; nothing
  here has ever run one (OPEN_ITEMS.md).
- **whether a real Photoshop or Sound Designer II document behaves the
  same.** Those two subjects are part synthetic: the data fork of the
  Photoshop one is a genuine PSD (ImageMagick wrote it, deark reads it
  back), but its resource fork is built to the module's own acceptance
  test, and the Sound Designer II file is 8 KB of generated samples. So
  they show what a module does once it accepts a file, not that a real
  document looks like this.
- **anything at all on a fresh clone.** The specimens are not
  committed — they are an emulator's output, like `sitcrypt.py`'s — so
  this skips cleanly and says nothing when they are absent.

    tools/run_sitopt.py --macextract build/macextract
"""
import argparse
import os
import subprocess
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "vmac"))
import run as R                                          # noqa: E402

SPECIMENS = os.path.join(R.VMAC_HOME, "specimens", "sitopt")
MADE = os.path.join(SPECIMENS, "make2")
UNSTUFFED = os.path.join(SPECIMENS, "unstuff1", "unstuffed.bin")
PAINT = os.path.join(SPECIMENS, "paintmake")
MODS = os.path.join(SPECIMENS, "mods5")

# The subject `sitopt.py` stuffed, repeated here rather than imported so
# that this suite still grades if that harness is edited: what the
# control must come back as is a property of the specimens, not of the
# generator as it stands today.
SUBJECT_DATA = (b"    indented four spaces   \r"
                b"        indented eight   \r"
                b"no indent, trailing tab\t\r"
                b"    mixed \t indent and trailing spaces    \r") * 6


def forks(path):
    d = open(path, "rb").read()
    dl = int.from_bytes(d[83:87], "big")
    rl = int.from_bytes(d[87:91], "big")
    off = 128 + ((dl + 127) // 128) * 128
    return d[128:128 + dl], d[off:off + rl]


def header(path):
    data, _r = forks(path)
    if data[:4] != b"SIT!":
        return None
    return data[22:22 + 112]


def extract(cli, arc, out):
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([cli, "x", "-o", out, arc], capture_output=True,
                       text=True)
    return r.returncode, r.stdout + r.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract",
                    default=os.path.join(REPO, "build", "macextract"))
    args = ap.parse_args()

    need = [os.path.join(MADE, n + ".sit.bin")
            for n in ("Plain", "Optimized", "OptBetter")] + [UNSTUFFED]
    paint = [os.path.join(PAINT, n) for n in ("PlainPaint.sit.bin",
                                              "OptPaint.sit.bin",
                                              "Painting.bin")]
    missing = [p for p in need if not os.path.exists(p)]
    if missing:
        print("run_sitopt: no specimens (%s) — skipped; "
              "tools/vmac/sitopt.py makes them"
              % os.path.basename(missing[0]))
        return 0

    ref_data, ref_rsrc = forks(UNSTUFFED)
    problems = []
    work = tempfile.mkdtemp(prefix="sitopt-grade-")
    try:
        # 1. the control
        rc, msg = extract(args.macextract,
                          os.path.join(MADE, "Plain.sit.bin"),
                          os.path.join(work, "plain"))
        p = os.path.join(work, "plain", "Subject")
        if rc != 0:
            problems.append("the control did not extract: %s" % msg.strip())
        elif open(p, "rb").read() != SUBJECT_DATA:
            problems.append("the control's data fork is not the subject")
        elif not os.path.exists(p + ".rsrc"):
            problems.append("the control lost its resource fork")

        # 2, 3. the optimized pair, against 2.0.1's own unstuffer
        for name in ("Optimized", "OptBetter"):
            out = os.path.join(work, name)
            rc, msg = extract(args.macextract,
                              os.path.join(MADE, name + ".sit.bin"), out)
            p = os.path.join(out, "Subject")
            if rc != 0 or not os.path.exists(p):
                problems.append("%s did not extract: %s" % (name,
                                                            msg.strip()))
                continue
            got = open(p, "rb").read()
            if got != ref_data:
                problems.append("%s: %d B, and StuffIt Deluxe 2.0.1 "
                                "unstuffs it to %d B" % (name, len(got),
                                                         len(ref_data)))
            if os.path.exists(p + ".rsrc"):
                problems.append("%s: a resource fork was written and "
                                "`Text 1` deleted it" % name)

        # 4. the header bytes the reading names
        for name in ("Optimized", "OptBetter"):
            h = header(os.path.join(MADE, name + ".sit.bin"))
            if h is None:
                problems.append("%s: not a StuffIt archive" % name)
                continue
            if not (h[0] & 0x40) or not (h[1] & 0x40):
                problems.append("%s: 0x40 is not set on both method bytes "
                                "(%02x %02x)" % (name, h[0], h[1]))
            if h[106] != 255 or h[108] != 255:
                problems.append("%s: optimizer bytes are %d/%d, not 255/255"
                                % (name, h[106], h[108]))
            if h[46] or h[47] or h[107] or h[109]:
                problems.append("%s: a module byte that should be zero is "
                                "not (46=%d 47=%d 107=%d 109=%d)"
                                % (name, h[46], h[47], h[107], h[109]))
        # 5. the reversible Optimizer
        if all(os.path.exists(q) for q in paint):
            pd, pr = forks(os.path.join(PAINT, "Painting.bin"))
            out = os.path.join(work, "plainpaint")
            rc, msg = extract(args.macextract,
                              os.path.join(PAINT, "PlainPaint.sit.bin"), out)
            q = os.path.join(out, "Painting")
            if rc != 0 or not os.path.exists(q):
                problems.append("the paint control did not extract: %s"
                                % msg.strip())
            else:
                if open(q, "rb").read() != pd:
                    problems.append("the paint control's data fork is not "
                                    "MacPaint's own file")
                if (not os.path.exists(q + ".rsrc")
                        or open(q + ".rsrc", "rb").read() != pr):
                    problems.append("the paint control's resource fork is "
                                    "not MacPaint's own")
            out = os.path.join(work, "optpaint")
            rc, msg = extract(args.macextract,
                              os.path.join(PAINT, "OptPaint.sit.bin"), out)
            if rc == 0:
                problems.append("OptPaint.sit extracted; `MacPaint 1` can "
                                "undo what it did and this engine has no "
                                "'DCMP', so the entry must be refused")
            elif "MacPaint 1" not in msg:
                problems.append("OptPaint.sit was refused without naming "
                                "the module: %s" % msg.strip())
            h = header(os.path.join(PAINT, "OptPaint.sit.bin"))
            if h and (h[106] != 4 or h[108] != 4):
                problems.append("OptPaint: optimizer bytes are %d/%d, and "
                                "`MacPaint 1` is module 4" % (h[106], h[108]))
        else:
            print("run_sitopt: no paint specimens — the reversible "
                  "Optimizer is not graded (tools/vmac/sitopt.py --paint)")

        # 4b. THE DECLARED LENGTHS, which are the whole design.
        #
        # `Text 1` (255) rewrote the fork and StuffIt recorded the NEW
        # lengths — 338/732 became 0/594 — so the header describes what
        # is stored and anything can decode it. Every module with an id
        # left the ORIGINAL lengths in the header (501/2945, 342/8192,
        # unchanged from their controls) and stored a remnant, so
        # nothing without the module can produce a fork of the declared
        # size at all. That is why one decodes and the others are
        # refused, and it is checkable without running anything.
        ph = header(os.path.join(MADE, "Plain.sit.bin"))
        oh = header(os.path.join(MADE, "Optimized.sit.bin"))
        if ph and oh and (ph[84:92] == oh[84:92]):
            problems.append("the 255 entry declares the same lengths as "
                            "its control; it should declare the OPTIMIZED "
                            "ones")
        for ctl, opt in (("PlainPaint.sit.bin", "OptPaint.sit.bin"),):
            a, b = (header(os.path.join(PAINT, ctl)),
                    header(os.path.join(PAINT, opt)))
            if a and b and a[84:92] != b[84:92]:
                problems.append("%s does not declare its control's "
                                "lengths; a module entry should" % opt)

        # 5. the other three modules, each naming itself
        mods = {"OptSound.sit.bin": ("Sound 1", 1, "Sound2"),
                "OptPhoto.sit.bin": ("Photoshop 1", 2, "Photo"),
                "OptJpeg.sit.bin": ("Photoshop:JPEG Lossy", 3, "Photo")}
        if all(os.path.exists(os.path.join(MODS, n)) for n in mods):
            for fn, (name, mid, entry) in sorted(mods.items()):
                arc = os.path.join(MODS, fn)
                h = header(arc)
                if h is None or not (h[1] & 0x40):
                    problems.append("%s: 0x40 is not set on the data "
                                    "fork's method byte" % fn)
                elif h[106] != mid:
                    problems.append("%s: byte 106 is %d and `%s` is module "
                                    "%d" % (fn, h[106], name, mid))
                rc, msg = extract(args.macextract, arc,
                                  os.path.join(work, fn))
                if rc == 0:
                    problems.append("%s extracted; `%s` carries a 'DCMP' "
                                    "and this engine has none" % (fn, name))
                elif name not in msg:
                    problems.append("%s was refused without naming `%s`: %s"
                                    % (fn, name, msg.strip()))
        else:
            print("run_sitopt: no Sound/Photoshop specimens — three "
                  "modules are not graded (sitopt.py --makemods)")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for p in problems:
        print("run_sitopt: %s" % p)
    print("run_sitopt: 8 archive(s) StuffIt Deluxe 2.0.1 wrote — all five "
          "Optimizers — graded against its own unstuffer and its own "
          "Engine, %d problem(s)" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
