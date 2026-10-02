#!/usr/bin/env python3
"""run_sitopt.py — the optimized archives, graded by the program that wrote them.

StuffIt Deluxe 2.0 could hand a fork to an Optimizer before compressing
it, and this engine's whole reading of where an archive records that is
six header bytes taken out of the application's own code (FORMATS.md,
*Where an archive names the module*). Until 2026-09-28 nothing graded
that reading against an archive, because none existed here.

`tools/vmac/sitopt.py` made nine, over four boots, and this
replays them:

  Plain.sit       the control — no Optimizer, the same subject
  Optimized.sit   `Text 1`, method 2
  OptBetter.sit   `Text 1`, method 5
  unstuffed.bin   what 2.0.1's OWN unstuffer gives back for Optimized.sit
  PlainPaint.sit  the control for the other kind of Optimizer
  OptPaint.sit    `MacPaint 1` over a document MacPaint 2.0 itself drew
  Painting.bin    that document, as MacPaint wrote it
  unapp3/Painting.bin  what 2.0.1's own unstuffer gives back for OptPaint
  OptSound.sit    `Sound 1`, over a Sound Designer II file
  OptPhoto.sit    `Photoshop 1`, over a Photoshop document
  OptJpeg.sit     `Photoshop/JPEG Lossy`, over the same document —
                  the subject that module could NOT encode
  psdoc/PSDoc.bin a document Photoshop 1.0.7 itself wrote
  ps-jpeg1/       `JPEG Lossy` over THAT, and what 2.0.1 restored from it

**The oracle is the writer.** An optimized entry's right answer is not
the file that went in — `Text 1` turns leading spaces into tabs, strips
trailing ones and deletes the resource fork, and none of it is undone
— so "correct" can only mean *what StuffIt Deluxe 2.0.1 itself
produces*, which is why `unstuffed.bin` is in the set. Grading this
against the original subject would fail a correct engine, and grading
it against our own output would pass a broken one.

Seven things are asserted, and each one has failed a version of this
engine at some point:

  1. the control extracts to the subject, both forks, byte for byte;
  2. both optimized entries extract to **2.0.1's own unstuffed bytes**;
  3. neither writes a resource fork — `Text 1` deleted it, the header
     says `rlen` 0, and an engine that invents one is wrong;
  4. the header bytes are what the reading says: `0x40` set on both
     method bytes, 106 and 108 both 255, and 46/47/107/109 zero;
  5. **every module's id is its own.** All four Optimizers that carry
     a 'DCMP' write their resource id into byte 106 — `Sound 1` 1,
     `Photoshop 1` 2, `Photoshop/JPEG Lossy` 3, `MacPaint 1` 4 —
     and `Text 1`, the one with no 'DCMP', is the only 255. **JPEG
     Lossy is the case that could have broken the rule and does not**:
     it is lossy, and 255 is what the application's Get Info pane
     prints as " lossy", but it writes 3;
  6. **the declared lengths**, which are what makes the rule a rule
     rather than a convention — see 4b in the code; and
  7. **what this engine undoes, and how far.** All four reversible
     Optimizers are undone here, each module's own 'DCMP' having been
     disassembled:

       `Sound 1` and `Photoshop 1` delta-code a fork and change
       nothing else, so the subject comes back BYTE FOR BYTE, both
       forks, and the entry's own CRC-16 — which is the original
       file's — has to agree or the engine fails it. Nothing is said
       to the user about those, and the silence is asserted too.

       `MacPaint 1` throws a painting's 512-byte header and its whole
       resource fork away, so the artwork must be byte-identical to
       MacPaint's own file AND to 2.0.1's own unstuffed output, the
       resource fork must be ABSENT, the header this engine writes
       must be zeros — the module writes its caller's stack there and
       nothing can reproduce that — and the run must SAY it is not
       the original file.

       `JPEG Lossy` stores C-Cube's JPEG in a TIFF and is decoded
       by `src/sit_ccube.c`, which carries that codec's own integer
       IDCT rather than a better one. So the bar is BYTE-EXACTNESS
       against 2.0.1's own restored file — being more accurate than the
       module would miss — while the resource fork is graded against
       the ORIGINAL document, which this engine reproduces and 2.0.1
       does not. The run must say it is not the original file, and the
       data fork must NOT equal the original: a lossy module cannot
       give back what it threw away. The entry whose subject the module
       could not encode (OptJpeg.sit) must still be refused.

What this CANNOT see:

- **whether a 'DCMP' agrees with this engine on anything but these
  nine archives.** What each module does was read out of its own code
  and then run on an emulated Mac (tools/vmac/dcmptest), but only over
  the documents here.
- **whether a real Sound Designer II document behaves the same.** That
  subject is 8 KB of generated samples, and the `Photoshop 1` one is
  part synthetic too — a genuine PSD data fork (ImageMagick wrote it,
  deark reads it back) behind a resource fork built to the module's own
  acceptance test. So they show what a module does once it accepts a
  file, not that a real document looks like this. The `JPEG Lossy`
  subject is the exception: Photoshop 1.0.7 itself drew and saved it on
  an emulated Mac Plus, which is why that one is graded byte for byte.
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
# The `JPEG Lossy` round trip: a document Photoshop 1.0.7 itself
# wrote, the archive 2.0.1 made of it with that Optimizer enabled,
# and the file 2.0.1 then restored (tools/vmac/sitopt.py --psdoc,
# --psjpeg).
PSJ = os.path.join(SPECIMENS, "ps-jpeg1")
PSDOC = os.path.join(SPECIMENS, "psdoc", "PSDoc.bin")
# And the SECOND subject, a dense grid rather than five strokes
# (`sitopt.py --psdoc --drawing grid --psname PSDoc2`). It is here for
# the arithmetic: it reaches the output stage's negative branch 9,645
# times against the first subject's 709, which is what withdrew the
# round-toward-zero reading of CCOD+0x3826 (BLOCKERS.md). A decoder that
# regains that correction passes section 6 and fails this one.
PSJ2 = os.path.join(SPECIMENS, "ps-jpeg2")
PSDOC2 = os.path.join(SPECIMENS, "psdoc2", "PSDoc2.bin")
# The same document at Q=50 instead of the module's default 25
# (`sitopt.py --psjpeg --quality 50`). Its quantisation tables are
# Annex K unscaled where the default's are half of it, so this is the
# only specimen that can fail a decoder which ASSUMES the tables
# instead of reading tag 33606.
PSJ3 = os.path.join(SPECIMENS, "ps-jpeg3")
# What 2.0.1's OWN unstuffer gave back for OptPaint.sit — the only
# thing "correct" can mean for an entry `MacPaint 1` optimized,
# because the module does not restore the original either.
UNAPP = os.path.join(SPECIMENS, "unapp3", "Painting.bin")

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
            # `MacPaint 1` drops a painting's 512-byte header and its
            # whole resource fork, and this engine puts back a header of
            # ZEROS — as reproducible as the module's own is not, since
            # a 'DCMP' writes 512 bytes of its caller's stack there
            # (FORMATS.md, *What the data path does*). So the artwork
            # must be exact and the header must not be graded against
            # anything: what is graded is that the entry comes out at
            # the declared length, with no resource fork, with the
            # painting byte-identical to MacPaint's own file AND to
            # 2.0.1's own unstuffed output, and that the user is TOLD.
            out = os.path.join(work, "optpaint")
            rc, msg = extract(args.macextract,
                              os.path.join(PAINT, "OptPaint.sit.bin"), out)
            q = os.path.join(out, "Painting")
            if rc != 0 or not os.path.exists(q):
                problems.append("OptPaint.sit did not extract: %s"
                                % msg.strip())
            else:
                got = open(q, "rb").read()
                if len(got) != len(pd):
                    problems.append("OptPaint: the painting is %d bytes and "
                                    "the header declares %d"
                                    % (len(got), len(pd)))
                elif got[512:] != pd[512:]:
                    problems.append("OptPaint: the artwork is not "
                                    "MacPaint's own from offset 512 on")
                if got[:512] != bytes(512):
                    problems.append("OptPaint: the 512-byte header this "
                                    "engine writes is not zeros")
                if os.path.exists(q + ".rsrc"):
                    problems.append("OptPaint: a resource fork was written; "
                                    "`MacPaint 1` deletes it and 2.0.1's "
                                    "own unstuffer gives back none")
                if "MacPaint 1" not in msg or "NOT the original" not in msg:
                    problems.append("OptPaint extracted without saying it "
                                    "is not the original file: %s"
                                    % msg.strip())
                if os.path.exists(UNAPP):
                    ud, ur = forks(UNAPP)
                    if got[512:] != ud[512:]:
                        problems.append("OptPaint: the artwork differs from "
                                        "what 2.0.1's own unstuffer gave "
                                        "back")
                    if ur:
                        problems.append("the unapp3 specimen has a resource "
                                        "fork; 2.0.1 gave back none")
                else:
                    print("run_sitopt: no unapp3 specimen — the DCMP's own "
                          "output is not compared (sitopt.py --unstuffapp)")
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
                out = os.path.join(work, fn)
                rc, msg = extract(args.macextract, arc, out)
                if mid == 3:
                    # This subject is the one `JPEG Lossy` could not
                    # take: a modern 8BPS PSD wearing Photoshop 1.0's
                    # type code, so the module wrote an empty header and
                    # 2.0.1 refuses its own archive (FORMATS.md). The
                    # engine must refuse it too rather than invent a
                    # picture — the real round trip is graded below.
                    if rc == 0:
                        problems.append("%s extracted; that entry holds "
                                        "an 80-byte header and no image"
                                        % fn)
                    continue
                # `Sound 1` and `Photoshop 1` delta-code the fork and
                # change nothing else, so undoing it is EXACT — graded
                # against the subject itself, both forks, and the
                # entry's own CRC-16 had to agree or the engine would
                # have failed it. Nothing is said to the user about
                # these, and that silence is part of the assertion.
                sd, sr = forks(os.path.join(MODS, entry + ".bin"))
                q = os.path.join(out, entry)
                if rc != 0 or not os.path.exists(q):
                    problems.append("%s did not extract: %s"
                                    % (fn, msg.strip()))
                    continue
                if open(q, "rb").read() != sd:
                    problems.append("%s: the data fork is not the subject "
                                    "`%s` byte for byte" % (fn, entry))
                if sr and (not os.path.exists(q + ".rsrc")
                           or open(q + ".rsrc", "rb").read() != sr):
                    problems.append("%s: the resource fork is not the "
                                    "subject's" % fn)
                if "NOT the original" in msg:
                    problems.append("%s: `%s` is exactly reversible and the "
                                    "run warned about it anyway: %s"
                                    % (fn, name, msg.strip()))
        else:
            print("run_sitopt: no Sound/Photoshop specimens — three "
                  "modules are not graded (sitopt.py --makemods)")

        # 6. `JPEG Lossy`, over a document Photoshop 1.0.7 itself wrote.
        #
        # The bar here is BYTE-EXACTNESS against 2.0.1's own restored
        # file, which is attainable because `src/sit_ccube.c` carries
        # C-Cube's own IDCT rather than a better one — being more
        # accurate than the module would miss (FORMATS.md, *What an
        # Optimizer did to the fork*). The resource fork is graded
        # against the ORIGINAL, which this engine reproduces and 2.0.1
        # itself does not.
        jarc = os.path.join(PSJ, "JpegPS.sit.bin")
        jref = os.path.join(PSJ, "PSDoc.bin")
        if os.path.exists(jarc) and os.path.exists(jref) \
                and os.path.exists(PSDOC):
            out = os.path.join(work, "psjpeg")
            rc, msg = extract(args.macextract, jarc, out)
            q = os.path.join(out, "PSDoc")
            rd, rr = forks(jref)
            od, orr = forks(PSDOC)
            if rc != 0 or not os.path.exists(q):
                problems.append("JpegPS.sit did not extract: %s"
                                % msg.strip())
            else:
                got = open(q, "rb").read()
                if got != rd:
                    n = sum(1 for i in range(min(len(got), len(rd)))
                            if got[i] != rd[i])
                    problems.append("JpegPS: the data fork is not 2.0.1's "
                                    "own restored bytes (%d B against %d, "
                                    "%d differing)" % (len(got), len(rd), n))
                if (not os.path.exists(q + ".rsrc")
                        or open(q + ".rsrc", "rb").read() != orr):
                    problems.append("JpegPS: the resource fork is not the "
                                    "document's own")
                if "NOT the original" not in msg:
                    problems.append("JpegPS extracted without saying it is "
                                    "not the original file: %s" % msg.strip())
                if got == od:
                    problems.append("JpegPS: the data fork equals the "
                                    "ORIGINAL, which a lossy Optimizer "
                                    "cannot give back")
        else:
            print("run_sitopt: no ps-jpeg1 specimens — `JPEG Lossy` is not "
                  "graded (sitopt.py --psdoc, --psjpeg)")

        # 7. the same, over the subject that exercises the rounding.
        jarc = os.path.join(PSJ2, "JpegPS.sit.bin")
        jref = os.path.join(PSJ2, "PSDoc2.bin")
        jctl = os.path.join(PSJ2, "PlainPS.sit.bin")
        if os.path.exists(jarc) and os.path.exists(jref) \
                and os.path.exists(PSDOC2):
            out = os.path.join(work, "psjpeg2")
            rc, msg = extract(args.macextract, jarc, out)
            q = os.path.join(out, "PSDoc2")
            rd, _ = forks(jref)
            od, orr = forks(PSDOC2)
            if rc != 0 or not os.path.exists(q):
                problems.append("the grid JpegPS.sit did not extract: %s"
                                % msg.strip())
            else:
                got = open(q, "rb").read()
                if got != rd:
                    n = sum(1 for i in range(min(len(got), len(rd)))
                            if got[i] != rd[i])
                    problems.append("JpegPS(grid): the data fork is not "
                                    "2.0.1's own restored bytes (%d B "
                                    "against %d, %d differing)"
                                    % (len(got), len(rd), n))
                if (not os.path.exists(q + ".rsrc")
                        or open(q + ".rsrc", "rb").read() != orr):
                    problems.append("JpegPS(grid): the resource fork is not "
                                    "the document's own")
                if got == od:
                    problems.append("JpegPS(grid): the data fork equals the "
                                    "ORIGINAL, which a lossy Optimizer "
                                    "cannot give back")
            # and its control, which says the subject itself round-trips
            if os.path.exists(jctl):
                out = os.path.join(work, "psplain2")
                rc, msg = extract(args.macextract, jctl, out)
                q = os.path.join(out, "PSDoc2")
                if rc != 0 or not os.path.exists(q):
                    problems.append("the grid control did not extract: %s"
                                    % msg.strip())
                elif open(q, "rb").read() != od:
                    problems.append("the grid control's data fork is not "
                                    "the subject")
        else:
            print("run_sitopt: no ps-jpeg2 specimens — the second `JPEG "
                  "Lossy` subject is not graded (sitopt.py --psdoc "
                  "--drawing grid --psname PSDoc2, --psjpeg)")

        # 8. the same subject at a quality the module did not default to.
        jarc = os.path.join(PSJ3, "JpegPS.sit.bin")
        jref = os.path.join(PSJ3, "PSDoc2.bin")
        if os.path.exists(jarc) and os.path.exists(jref) \
                and os.path.exists(PSDOC2):
            out = os.path.join(work, "psjpeg3")
            rc, msg = extract(args.macextract, jarc, out)
            q = os.path.join(out, "PSDoc2")
            rd, _ = forks(jref)
            od, orr = forks(PSDOC2)
            if rc != 0 or not os.path.exists(q):
                problems.append("the Q=50 JpegPS.sit did not extract: %s"
                                % msg.strip())
            else:
                got = open(q, "rb").read()
                if got != rd:
                    n = sum(1 for i in range(min(len(got), len(rd)))
                            if got[i] != rd[i])
                    problems.append("JpegPS(Q=50): the data fork is not "
                                    "2.0.1's own restored bytes (%d B "
                                    "against %d, %d differing)"
                                    % (len(got), len(rd), n))
                if (not os.path.exists(q + ".rsrc")
                        or open(q + ".rsrc", "rb").read() != orr):
                    problems.append("JpegPS(Q=50): the resource fork is not "
                                    "the document's own")
                if got == od:
                    problems.append("JpegPS(Q=50): the data fork equals the "
                                    "ORIGINAL, which a lossy Optimizer "
                                    "cannot give back")
            # and the archive is a DIFFERENT one: a decoder that ignored
            # the file's own tables could still pass section 7.
            a2 = os.path.join(PSJ2, "JpegPS.sit.bin")
            if os.path.exists(a2) and \
                    open(a2, "rb").read() == open(jarc, "rb").read():
                problems.append("the Q=50 archive is byte-identical to the "
                                "Q=25 one; the quality did not take")
        else:
            print("run_sitopt: no ps-jpeg3 specimens — the second QUALITY "
                  "is not graded (sitopt.py --psjpeg --quality 50)")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for p in problems:
        print("run_sitopt: %s" % p)
    print("run_sitopt: 13 archive(s) StuffIt Deluxe 2.0.1 wrote — all five "
          "Optimizers — graded against its own unstuffer and its own "
          "Engine, %d problem(s)" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
