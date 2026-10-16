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
import hashlib
import json
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
FIXTURES = os.path.join(REPO, "fixtures")
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
# An entry that is BOTH optimized and encrypted, which no script can
# write: `PassLock` is armed from Options ▸ Custom Encryption… and the
# stuffing is the application's own (`sitopt.py --psencgui`). It is the
# first archive here from any of 2.x's three encryptor modules.
PSENC = os.path.join(SPECIMENS, "psenc3", "EncG.sit.bin")
PSJ2REF = os.path.join(PSJ2, "PSDoc2.bin")
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


def extract(cli, arc, out, extra=()):
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([cli, "x", "-o", out, arc] + list(extra),
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


# ---------------------------------------------------------------------
# The two wild archives carrying a REVERSIBLE Optimizer.
#
# Everything the lanes below grade is StuffIt Deluxe 2.0.1's own output
# under Mini vMac: authentic bytes, but one subject per module, chosen
# here. These two are fixtures off a 1993 CD-ROM collection, found
# 2026-10-07 by asking the index what each archive CONTAINS rather than
# what it is called — an Optimizer accepts exactly one Mac file type, so
# an archive with no member of that type cannot carry that module's bit
# (TESTING.md, *Searching somebody else's index by content*).
#
# **Both optimized forks defeat both oracles**, so their manifests
# record those two forks as unadjudicated and `run_diff.py` grades
# everything else: `unar` fails `DNANAL Key Commands` with *"Attempted
# to read more data than was available"* and `Phantom` with **"Wrong
# checksum"** — the archive's own CRC-16 catching the oracle, because
# that field is over the RESTORED bytes — and `macunpack` skips both
# (*"Unknown stuffit flags: 0 65"*, *"5 45"*). What grades the two
# forks themselves is below, and none of it is this engine's own
# output.
WILD_PHANTOM = "sitopt-wild-Phantom.sit"
WILD_DNA = "sitopt-wild-DNAnalyze.sit"
DEARK = os.path.join(REPO, "build", "deark", "deark")


def crc16_arc(data, crc=0):
    """CRC-16/ARC, the one a StuffIt entry header carries at 100/102 and
    at 110 (reference/notes/StuffIt.md; `unc_crc16_arc`)."""
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def find_entry(blob, name):
    """One file header out of a raw classic StuffIt archive, by name."""
    at = 22
    while at + 112 <= len(blob):
        nl = min(blob[at + 2], 63)
        if blob[at + 3:at + 3 + nl].decode("mac-roman") == name:
            return at, blob[at:at + 112]
        # **A folder marker carries no fork**, and its length fields
        # hold whatever the writer left there — stepping by them walks
        # into the middle of the first file's data (`src/fmt_sit.c`,
        # SIT_FOLDER_MASK).
        if (blob[at] & 0x6F) in (0x20, 0x21) or \
                (blob[at + 1] & 0x6F) in (0x20, 0x21):
            at += 112
            continue
        at += 112 + int.from_bytes(blob[at + 92:at + 96], "big") \
            + int.from_bytes(blob[at + 96:at + 100], "big")
    return None, None


def pntg_rows(data):
    """How many rows of exactly 72 bytes a MacPaint document's PackBits
    stream decodes to, and whether it is consumed exactly.

    Source: MacPaint's published layout — 576x720 one bit deep, so 72
    bytes per row and 720 rows, each row PackBits-compressed; the same
    `MACPAINT_WIDTH`/`MACPAINT_HEIGHT` as
    `reference/deark/modules/macpaint.c`. It is an INDEPENDENT check on
    a rebuild nothing else here can grade: 720 rows that each close at
    exactly 72 bytes, with no byte left over, is a property of the
    artwork being intact, not of the engine having written something.
    """
    p, rows = 512, 0
    while p < len(data) and rows < 10000:
        row = 0
        while row < 72 and p < len(data):
            n = data[p]
            p += 1
            if n < 128:
                row += n + 1
                p += n + 1
            else:
                row += 257 - n
                p += 1
        if row != 72:
            return rows, len(data) - p, "row %d closed at %d bytes" % (rows,
                                                                       row)
        rows += 1
    return rows, len(data) - p, None


def deark_warnings(path, out):
    """What `deark` says about a MacPaint document, or None if it is not
    built. A warning line is the signal: on a correct rebuild it emits
    none, and on the same artwork with its 512-byte header removed or
    filled with noise it reports an unrecognised version and an image
    that decompressed short of 720 x 72."""
    if not os.path.exists(DEARK):
        return None
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([DEARK, "-od", out, "-m", "macpaint", path],
                       capture_output=True, text=True, timeout=300)
    return [l for l in (r.stdout + r.stderr).splitlines()
            if l.startswith("Warning:")]


def wild_reversible(cli, work):
    """Grade the two wild archives. Returns (problems, graded)."""
    bad, graded = [], 0
    unar = shutil.which("unar")

    # ---- `Sound 1`, id 1, on an archive nobody here wrote -----------
    path = os.path.join(FIXTURES, WILD_PHANTOM)
    if os.path.exists(path):
        graded += 1
        blob = open(path, "rb").read()
        at, hdr = find_entry(blob, "Phantom")
        if hdr is None:
            bad.append("%s: no entry called 'Phantom'" % WILD_PHANTOM)
        else:
            dm = hdr[1]
            dcrc = int.from_bytes(hdr[102:104], "big")
            if not (dm & 0x40) or (dm & 0x0F) != 5:
                bad.append("Phantom: data method byte 0x%02x, and the "
                           "Optimizer bit over method 5 is what this "
                           "fixture is for" % dm)
            if hdr[106] != 1 or hdr[108] != 0:
                bad.append("Phantom: optimizer ids %d/%d, and `Sound 1` "
                           "is 1 on the data fork alone"
                           % (hdr[106], hdr[108]))
            if int.from_bytes(hdr[88:92], "big") != 366189:
                bad.append("Phantom: the data fork is not the declared "
                           "366,189 B")
            if int.from_bytes(hdr[84:88], "big") != 470:
                bad.append("Phantom: `Sound 1` keeps the resource fork "
                           "and this one declares %d B"
                           % int.from_bytes(hdr[84:88], "big"))
            if dcrc == 0xFFFF:
                bad.append("Phantom: the data CRC is 0xffff, and an "
                           "exactly reversible module leaves the "
                           "ORIGINAL file's")

            # The archive's own CRC-16 is the oracle: it is taken over
            # the RESTORED bytes, so `t` passing is the format itself
            # saying the delta came out right.
            r = subprocess.run([cli, "t", path], capture_output=True,
                               text=True, timeout=600)
            if r.returncode != 0:
                bad.append("Phantom: `t` failed, so the archive's own "
                           "CRC-16 rejects the restored bytes: %s"
                           % (r.stdout + r.stderr).strip()[:120])

            # **And that test can fail.** Clear the Optimizer bit and
            # the id, repair the header's own CRC-16 at 110 so the
            # entry is still well formed, and the same `t` must report a
            # checksum mismatch — which is what makes the line above
            # evidence about the filter rather than about the decoder.
            off = at
            f = bytearray(blob)
            f[off + 1] &= ~0x40
            f[off + 106] = 0
            f[off + 110:off + 112] = crc16_arc(
                bytes(f[off:off + 110])).to_bytes(2, "big")
            fpath = os.path.join(work, "phantom-nofilter.sit")
            open(fpath, "wb").write(bytes(f))
            r = subprocess.run([cli, "t", fpath], capture_output=True,
                               text=True, timeout=600)
            if r.returncode == 0 or "checksum" not in (r.stdout + r.stderr):
                bad.append("Phantom: with the `Sound 1` filter switched "
                           "off the archive still passes `t`, so `t` "
                           "passing says nothing about the filter")

            out = os.path.join(work, "wild-phantom")
            rc, msg = extract(cli, path, out)
            got = os.path.join(out, "Phantom")
            if rc != 0 or not os.path.exists(got):
                bad.append("%s did not extract: %s"
                           % (WILD_PHANTOM, msg.strip()[:120]))
            elif unar:
                # A SECOND implementation, and it is the module's
                # OUTPUT: `unar` decodes method 5 and hands back what
                # `Sound 1` left, because it does not know the module.
                # The running sum over those bytes is the whole of what
                # the 'DCMP' does (src/unc_internal.h, UncForkOut.delta),
                # and it must land on the same file this engine wrote.
                u = os.path.join(work, "wild-phantom-unar")
                os.makedirs(u, exist_ok=True)
                r = subprocess.run([unar, "-nr", "-D", "-f", "-k",
                                    "hidden", "-e", "macintosh", "-o", u,
                                    path], capture_output=True, timeout=600)
                said = (r.stdout + r.stderr).decode("utf-8", "replace")
                # **The archive's CRC-16 catches the oracle**, which is
                # the clearest statement there is that the restored
                # bytes are the file: `unar` decodes method 5 correctly
                # and fails the entry on the checksum, because the
                # field is over what the module was given rather than
                # what it left.
                if "Wrong checksum" not in said:
                    bad.append("Phantom: `unar` no longer fails on the "
                               "checksum — it used to, which is the "
                               "format telling the oracle it is wrong: %s"
                               % said.strip()[-160:])
                up = os.path.join(u, "Phantom")
                ours = open(got, "rb").read()
                if not os.path.exists(up):
                    bad.append("Phantom: `unar` wrote no data fork")
                else:
                    opt = open(up, "rb").read()
                    acc, want = 0, bytearray(len(opt))
                    for i, b in enumerate(opt):
                        acc = (acc + b) & 0xFF
                        want[i] = acc
                    if opt == ours:
                        bad.append("Phantom: `unar`'s bytes and ours are "
                                   "the same, so nothing undid the delta")
                    if bytes(want) != ours:
                        bad.append("Phantom: the running sum over "
                                   "`unar`'s bytes is not what this "
                                   "engine wrote")
                    if crc16_arc(ours) != dcrc:
                        bad.append("Phantom: the archive's CRC-16 is not "
                                   "the CRC of the restored bytes")
                    if crc16_arc(opt) == dcrc:
                        bad.append("Phantom: the archive's CRC-16 also "
                                   "matches the OPTIMIZED bytes, so it "
                                   "cannot tell the two apart")

    # ---- `MacPaint 1`, id 4, beside a `Text 1` in one archive -------
    path = os.path.join(FIXTURES, WILD_DNA)
    if os.path.exists(path):
        graded += 1
        blob = open(path, "rb").read()
        # Two kinds of optimized entry in one archive, which nothing
        # this project made has: one the module can undo and one that
        # is the sentinel 255.
        for name, meth, oid, crcff in (("DNANAL Key Commands", 5, 4, True),
                                       ("TC.DNA", 3, 255, False)):
            _at, hdr = find_entry(blob, name)
            if hdr is None:
                bad.append("%s: no entry called %r" % (WILD_DNA, name))
                continue
            dm = hdr[1]
            dcrc = int.from_bytes(hdr[102:104], "big")
            if not (dm & 0x40) or (dm & 0x0F) != meth:
                bad.append("%s: data method byte 0x%02x, wanted the "
                           "Optimizer bit over method %d" % (name, dm, meth))
            if hdr[106] != oid or hdr[108] != 0:
                bad.append("%s: optimizer ids %d/%d, wanted %d/0"
                           % (name, hdr[106], hdr[108], oid))
            # **The CRC field says which kind an entry is**, and here it
            # says so on an archive nobody here wrote: 0xffff where the
            # module cannot be undone exactly, the original file's CRC
            # where the bytes in the archive ARE the file.
            if crcff and dcrc != 0xFFFF:
                bad.append("%s: the data CRC is 0x%04x, and an entry "
                           "`MacPaint 1` optimized carries no checksum"
                           % (name, dcrc))
            if not crcff and dcrc == 0xFFFF:
                bad.append("%s: the data CRC is 0xffff, and a `Text 1` "
                           "entry's bytes ARE the file" % name)
        _at, hdr = find_entry(blob, "DNANAL Key Commands")
        if hdr is not None and int.from_bytes(hdr[84:88], "big") != 0:
            bad.append("DNANAL Key Commands: a resource fork is declared "
                       "and `MacPaint 1` deletes it")

        out = os.path.join(work, "wild-dna")
        rc, msg = extract(cli, path, out)
        got = os.path.join(out, "DNAnalyze", "DNANAL Key Commands")
        if rc != 0 or not os.path.exists(got):
            bad.append("%s did not extract: %s"
                       % (WILD_DNA, msg.strip()[:160]))
        else:
            if "MacPaint 1" not in msg or "NOT the original file" not in msg:
                bad.append("DNANAL Key Commands: the user was not told "
                           "the entry is a rebuild: %s" % msg.strip()[:160])
            if os.path.exists(got + ".rsrc"):
                bad.append("DNANAL Key Commands: a resource fork was "
                           "written and `MacPaint 1` deletes it")
            d = open(got, "rb").read()
            if len(d) != 12992:
                bad.append("DNANAL Key Commands: %d B, and the header "
                           "declares 12,992" % len(d))
            elif d[:512] != b"\0" * 512:
                bad.append("DNANAL Key Commands: the 512 bytes this "
                           "engine writes in place of the header are not "
                           "zero")
            rows, left, why = pntg_rows(d)
            if why or rows != 720 or left != 0:
                bad.append("DNANAL Key Commands: the rebuild is not a "
                           "MacPaint document — %d rows, %d bytes over "
                           "(%s)" % (rows, left, why))
            # deark, an independent reader, must have NOTHING to say
            # about it — and must complain about the same artwork with
            # its header removed, or the silence means nothing.
            w = deark_warnings(got, os.path.join(work, "dk-ok"))
            if w is None:
                print("run_sitopt: build/deark/deark absent — the "
                      "MacPaint rebuild is not read back by a second "
                      "implementation (tools/build_deark.sh)")
            else:
                if w:
                    bad.append("DNANAL Key Commands: deark warns about "
                               "the rebuild: %s" % "; ".join(w)[:160])
                nohdr = os.path.join(work, "nohdr.pntg")
                open(nohdr, "wb").write(d[512:])
                if not deark_warnings(nohdr, os.path.join(work, "dk-bad")):
                    bad.append("deark says nothing about the artwork "
                               "WITHOUT its header either, so its "
                               "silence about the rebuild is not "
                               "evidence")
            if unar:
                # **The oracle appears for what it cannot do.** `unar`
                # FAILS this entry — the manifest records the fork as
                # unadjudicated for that reason — while reading every
                # other entry in the archive perfectly well. The
                # manifest is static, so the live check is here: if
                # `unar` ever learns the module, this is where it is
                # noticed.
                u = os.path.join(work, "wild-dna-unar")
                os.makedirs(u, exist_ok=True)
                r = subprocess.run([unar, "-nr", "-D", "-f", "-k",
                                    "hidden", "-e", "macintosh", "-o", u,
                                    path], capture_output=True, timeout=600)
                said = (r.stdout + r.stderr).decode("utf-8", "replace")
                if "Attempted to read more data than was available" \
                        not in said:
                    bad.append("`unar` no longer fails on the MacPaint "
                               "entry — it used to, so this fixture may "
                               "now have an oracle: %s"
                               % said.strip()[-160:])
                for rel in ("DNANALYZE Docs", "Schwindinger 1987",
                            "TC.DNA"):
                    a = os.path.join(out, "DNAnalyze", rel)
                    b = os.path.join(u, "DNAnalyze", rel)
                    if not (os.path.exists(a) and os.path.exists(b)):
                        bad.append("%s: missing from one of the two "
                                   "extractions" % rel)
                    elif open(a, "rb").read() != open(b, "rb").read():
                        bad.append("%s: this engine and `unar` disagree "
                                   "on an entry no module touched" % rel)
    return bad, graded


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract",
                    default=os.path.join(REPO, "build", "macextract"))
    args = ap.parse_args()

    # The wild fixtures need no specimens, so they are graded BEFORE
    # the gate below: a fresh clone that has restored `fixtures/` and
    # has never booted an emulator still grades them.
    wild_work = tempfile.mkdtemp(prefix="sitopt-wild-")
    try:
        wild_bad, wild_graded = wild_reversible(args.macextract, wild_work)
    finally:
        shutil.rmtree(wild_work, ignore_errors=True)
    if wild_graded < 2:
        print("run_sitopt: %d of 2 wild reversible-Optimizer fixtures "
              "present — the rest is not graded (fixtures/SOURCES.md)"
              % wild_graded)

    need = [os.path.join(MADE, n + ".sit.bin")
            for n in ("Plain", "Optimized", "OptBetter")] + [UNSTUFFED]
    paint = [os.path.join(PAINT, n) for n in ("PlainPaint.sit.bin",
                                              "OptPaint.sit.bin",
                                              "Painting.bin")]
    missing = [p for p in need if not os.path.exists(p)]
    if missing:
        print("run_sitopt: no specimens (%s) — 2.0.1's own archives are "
              "skipped; tools/vmac/sitopt.py makes them"
              % os.path.basename(missing[0]))
        for p in wild_bad:
            print("run_sitopt: %s" % p)
        print("run_sitopt: %d wild archive(s) carrying a reversible "
              "Optimizer graded, %d problem(s)"
              % (wild_graded, len(wild_bad)))
        return 1 if wild_bad else 0

    ref_data, ref_rsrc = forks(UNSTUFFED)
    problems = list(wild_bad)
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

        # 9. optimized AND password-protected by `PassLock`.
        #
        # `PassLock` enciphers nothing — measured four ways: both forks
        # of two subjects against the unprotected archives of the same
        # ones, the entry's own CRC over what comes out, and the
        # module's own `COMP` and `DCMP`, whose data paths never
        # dereference the buffer they are handed (FORMATS.md,
        # *Encryption*). So the entry comes out WITHOUT a password and
        # the run says NOTHING about the protection: there is nothing
        # for a user to do about it, and an unarchiver that editorialises
        # on every entry is one people stop reading. What it must still
        # report is the Optimizer's loss, which is about the bytes.
        if os.path.exists(PSENC) and os.path.exists(PSJ2REF):
            rd, _ = forks(PSJ2REF)
            od, orr = forks(PSDOC2)
            for label, extra in (("no password", []),
                                 ("a password", ["-p", "swordfish"])):
                out = os.path.join(work, "psenc-" + label.replace(" ", ""))
                rc, msg = extract(args.macextract, PSENC, out, extra)
                q = os.path.join(out, "PSDoc2")
                if rc != 0 or not os.path.exists(q):
                    problems.append("the PassLock archive did not extract "
                                    "with %s: %s" % (label, msg.strip()[:120]))
                    continue
                if open(q, "rb").read() != rd:
                    problems.append("the PassLock archive's data fork is not "
                                    "2.0.1's own restored bytes (%s)" % label)
                if (not os.path.exists(q + ".rsrc")
                        or open(q + ".rsrc", "rb").read() != orr):
                    problems.append("the PassLock archive's resource fork is "
                                    "not the document's own (%s)" % label)
                if "PassLock" in msg or "password" in msg:
                    problems.append("the PassLock archive, with %s, said "
                                    "something about the password: %s"
                                    % (label, msg.strip()[:120]))
                if "NOT the original" not in msg:
                    problems.append("the PassLock archive, with %s, did not "
                                    "say the Optimizer's output is not the "
                                    "original file" % label)
        else:
            print("run_sitopt: no psenc3 specimen — `PassLock` is not graded "
                  "(sitopt.py --psencgui)")

        # 10. the control for that claim, on a subject with no Optimizer
        # anywhere near it: the same text file, LZW-compressed, stuffed
        # twice in one boot — once with `PassLock` armed through the
        # application's own Stuff and once from a script, which cannot
        # encrypt. Both must extract to the same bytes.
        enc = os.path.join(SPECIMENS, "enctext1", "EncT.sit.bin")
        plain = os.path.join(SPECIMENS, "enctext1", "PlainT.sit.bin")
        if os.path.exists(enc) and os.path.exists(plain):
            oe = os.path.join(work, "enct")
            op = os.path.join(work, "plaint")
            rce, msge = extract(args.macextract, enc, oe)
            rcp, _ = extract(args.macextract, plain, op)
            if rce != 0 or rcp != 0:
                problems.append("the PassLock text pair did not both "
                                "extract: %s" % msge.strip()[:120])
            else:
                for fn in ("Subject", "Subject.rsrc"):
                    a = os.path.join(oe, fn)
                    b = os.path.join(op, fn)
                    if not os.path.exists(a) or not os.path.exists(b):
                        problems.append("the PassLock text pair is missing %s"
                                        % fn)
                    elif open(a, "rb").read() != open(b, "rb").read():
                        problems.append("%s differs between the protected "
                                        "archive and the plain one" % fn)
                if msge.strip():
                    problems.append("the protected text archive was not "
                                    "silent: %s" % msge.strip()[:120])
        else:
            print("run_sitopt: no enctext1 pair — the `PassLock` control is "
                  "not graded (sitopt.py --enctext)")

        # 11. the two ciphers that are real, built in, and DECRYPTED.
        #
        # `DES` says so with 0x80 and encryptor id 1, `NewDE` with a bit
        # of its own (0x10) and no id — the folder flag's value, which
        # is what it was read as until 2026-10-02. Both share 3.5's key
        # derivation exactly, down to the 'MKey' verifier, and differ
        # only in the fork transform: standard DES in CBC for one,
        # StuffItDES in CBC for the other (FORMATS.md, *The three ways
        # 2.0.1 encrypts*).
        #
        # The control stuffed in the same boot IS the plaintext, so this
        # grades the decryption against bytes rather than against an
        # absence of errors — and a wrong password must still be
        # refused, which is what says the key check is doing its job.
        des = os.path.join(SPECIMENS, "psdes1")
        if os.path.exists(os.path.join(des, "NoneT.sit.bin")):
            out = os.path.join(work, "noneT")
            rc, msg = extract(args.macextract, os.path.join(des,
                                                            "NoneT.sit.bin"),
                              out)
            if rc != 0 or not os.path.exists(os.path.join(out, "Subject")):
                problems.append("the psdes control did not extract: %s"
                                % msg.strip()[:120])
            for arc, what in (("DesT.sit.bin", "DES"),
                              ("NewdeT.sit.bin", "NewDE")):
                p2 = os.path.join(des, arc)
                if not os.path.exists(p2):
                    continue
                o = os.path.join(work, what + "ok")
                rc, msg = extract(args.macextract, p2, o, ["-p", "swordfish"])
                if rc != 0:
                    problems.append("%s did not decrypt: %s"
                                    % (what, msg.strip()[:120]))
                for fn in ("Subject", "Subject.rsrc"):
                    a = os.path.join(o, fn)
                    b = os.path.join(out, fn)
                    if not os.path.exists(a):
                        problems.append("%s did not write %s" % (what, fn))
                    elif open(a, "rb").read() != open(b, "rb").read():
                        problems.append("%s's %s is not the plain control's "
                                        "bytes" % (what, fn))
                # and the key check has to be able to say no
                o2 = os.path.join(work, what + "bad")
                rc, msg = extract(args.macextract, p2, o2, ["-p", "hunter2"])
                if rc == 0:
                    problems.append("%s accepted the wrong password" % what)
                if "wrong password" not in msg:
                    problems.append("%s, with a wrong password, did not say "
                                    "so: %s" % (what, msg.strip()[:120]))
                if os.path.exists(os.path.join(o2, "Subject")):
                    problems.append("%s wrote Subject with a wrong password"
                                    % what)
        else:
            print("run_sitopt: no psdes1 specimens — `DES` and `NewDE` are "
                  "not graded (sitopt.py --psdes)")

        # 12. the two ENCRYPTOR MODULES off the optional disk, and
        # `PassLock` beside them on the same subject.
        #
        # `NewDEx` (id 3) and `DESex` (id 64) turn out to be the two
        # built-in ciphers packaged as plug-ins — StuffItDES in CBC and
        # standard DES in CBC — measured against the same plaintext
        # (FORMATS.md, *The three ways 2.0.1 encrypts*). The control is
        # psdes1's plain archive of the same `Subject`, so this grades
        # bytes and not the absence of an error.
        ex = os.path.join(SPECIMENS, "psex2")
        ctl = os.path.join(SPECIMENS, "psdes1", "NoneT.sit.bin")
        if os.path.exists(os.path.join(ex, "EncC.sit.bin")) \
                and os.path.exists(ctl):
            base = os.path.join(work, "exctl")
            rc, msg = extract(args.macextract, ctl, base)
            if rc != 0:
                problems.append("the psex control did not extract: %s"
                                % msg.strip()[:120])
            for arc, who in (("EncA.sit.bin", "PassLock"),
                             ("EncB.sit.bin", "NewDEx"),
                             ("EncC.sit.bin", "DESex")):
                p3 = os.path.join(ex, arc)
                if not os.path.exists(p3):
                    continue
                o = os.path.join(work, who)
                rc, msg = extract(args.macextract, p3, o, ["-p", "swordfish"])
                if rc != 0:
                    problems.append("%s did not decode: %s"
                                    % (who, msg.strip()[:120]))
                    continue
                for fn in ("Subject", "Subject.rsrc"):
                    a2 = os.path.join(o, fn)
                    b2 = os.path.join(base, fn)
                    if not os.path.exists(a2):
                        problems.append("%s did not write %s" % (who, fn))
                    elif open(a2, "rb").read() != open(b2, "rb").read():
                        problems.append("%s's %s is not the plain control's "
                                        "bytes" % (who, fn))
                # `PassLock` needs no password and must not ask; the two
                # real ciphers must refuse a wrong one.
                o2 = os.path.join(work, who + "-bad")
                rc, msg = extract(args.macextract, p3, o2, ["-p", "hunter2"])
                if who == "PassLock":
                    if rc != 0:
                        problems.append("PassLock refused a wrong password; "
                                        "it enciphers nothing")
                elif rc == 0 or "wrong password" not in msg:
                    problems.append("%s accepted or mis-reported a wrong "
                                    "password: %s" % (who, msg.strip()[:120]))
        else:
            print("run_sitopt: no psex2 specimens — `NewDEx` and `DESex` are "
                  "not graded (sitopt.py --psex)")

        # 13. the rest of what 2.0.1 writes by default: `guess` and
        # `none`, a 1.5.1-compatible archive, and a FOLDER. The first
        # three must come out as the plain control's bytes; the folder
        # must come out as a folder with both its files, one of which
        # has a resource fork (sitopt.py --psrest, --psfold).
        rest = os.path.join(SPECIMENS, "psrest1")
        if os.path.exists(os.path.join(rest, "RGuess.sit.bin")):
            base = os.path.join(work, "restctl")
            extract(args.macextract, ctl, base)
            for arc in ("RGuess", "RNone", "R151", "RSea"):
                p4 = os.path.join(rest, arc + ".sit.bin")
                if not os.path.exists(p4):
                    continue
                o = os.path.join(work, arc)
                rc, msg = extract(args.macextract, p4, o)
                if rc != 0:
                    problems.append("%s did not extract: %s"
                                    % (arc, msg.strip()[:120]))
                    continue
                for fn in ("Subject", "Subject.rsrc"):
                    a3 = os.path.join(o, fn)
                    if not os.path.exists(a3) or open(a3, "rb").read() != \
                            open(os.path.join(base, fn), "rb").read():
                        problems.append("%s's %s is not the control's bytes"
                                        % (arc, fn))
        else:
            print("run_sitopt: no psrest1 specimens — `guess`, `none` and "
                  "the 1.5.1 archive are not graded (sitopt.py --psrest)")

        # 14. a SELF-EXTRACTING archive 2.0.1 wrote. The stub is about
        # 19 KB of code in front of the same archive — its entry header
        # is byte-identical to the plain one's — and it must come out as
        # the control's bytes (sitopt.py --pssea).
        sea = os.path.join(SPECIMENS, "pssea9", "RSea3.sea.bin")
        if os.path.exists(sea):
            base = os.path.join(work, "seactl")
            extract(args.macextract, ctl, base)
            # The MacBinary leaves the self-extractor, an application,
            # where a chain of layers stops (DECISIONS.md 2026-10-16, *the
            # installer that was a layer*); it is then opened directly.
            app = os.path.join(work, "seaapp")
            rc, msg = extract(args.macextract, sea, app)
            apps = [f for f in os.listdir(app) if not f.endswith(".rsrc")]
            o = os.path.join(work, "sea")
            if rc == 0 and len(apps) == 1:
                rc, msg = extract(args.macextract,
                                  os.path.join(app, apps[0]), o)
            elif rc == 0:
                rc, msg = 1, "the MacBinary left %r" % sorted(apps)
            if rc != 0:
                problems.append("the self-extracting archive did not "
                                "extract: %s" % msg.strip()[:120])
            else:
                for fn in ("Subject", "Subject.rsrc"):
                    a4 = os.path.join(o, fn)
                    if not os.path.exists(a4) or open(a4, "rb").read() != \
                            open(os.path.join(base, fn), "rb").read():
                        problems.append("the self-extractor's %s is not the "
                                        "control's bytes" % fn)
        else:
            print("run_sitopt: no pssea9 specimen — a 2.0.1 self-extractor "
                  "is not graded (sitopt.py --pssea)")

        fold = os.path.join(SPECIMENS, "psfold1", "RFold.sit.bin")
        if os.path.exists(fold):
            o = os.path.join(work, "fold")
            rc, msg = extract(args.macextract, fold, o)
            if rc != 0:
                problems.append("the folder archive did not extract: %s"
                                % msg.strip()[:120])
            else:
                for rel in ("Papers/First", "Papers/First.rsrc",
                            "Papers/Second"):
                    if not os.path.exists(os.path.join(o, rel)):
                        problems.append("the folder archive did not write %s"
                                        % rel)
        else:
            print("run_sitopt: no psfold1 specimen — a FOLDER 2.0.1 stuffed "
                  "is not graded (sitopt.py --psfold)")
        # 15. THE ONLY OPTIMIZED ARCHIVES NOBODY HERE MADE.
        #
        # Everything above is 2.0.1's own output under Mini vMac, which
        # is authentic but one subject per module, chosen here. These
        # two are FIXTURES — Giga-ROM CD icon collections from 1992,
        # found on 2026-10-06 by walking 7,929 wild classic StuffIt
        # archives' entry chains over HTTP `Range`
        # (DECISIONS.md 2026-10-06, *the Optimizer that was in somebody
        # else's corpus*) — so `run_diff.py` already grades their bytes
        # against `unar` manifests. What it does not grade is the six
        # header bytes this engine's whole reading of the Optimizer
        # rests on, which is what this lane is for.
        #
        # Both carry `Text 1`: the id 255 that means CANNOT BE UNDONE,
        # and the resource fork it deletes. The method under the bit is
        # the point — 8 in one, **3** in the other, where this
        # project's own archives only ever reached 0, 2, 5, 6 and 8 —
        # so a reader that masked the nibble wrongly would fail on an
        # archive it had never seen.
        wild = [("derived-QK_2.1_icon_family.sit", "QK 2.1 icon info", 8),
                ("derived-SoundEdit_icon_family.sit",
                 "SoundEdit\u2122 icon info", 3)]
        seen = 0
        for fx, entry, method in wild:
            path = os.path.join(FIXTURES, fx)
            man = os.path.join(FIXTURES, "manifests", fx + ".json")
            if not os.path.exists(path) or not os.path.exists(man):
                continue
            seen += 1
            blob = open(path, "rb").read()
            # The optimized entry is the last header the walk reaches;
            # find it by name rather than by position.
            at, hdr = 22, None
            while at + 112 <= len(blob):
                nl = min(blob[at + 2], 63)
                if blob[at + 3:at + 3 + nl].decode("mac-roman") == entry:
                    hdr = blob[at:at + 112]
                    break
                at += 112 + int.from_bytes(blob[at + 92:at + 96], "big") \
                    + int.from_bytes(blob[at + 96:at + 100], "big")
            if hdr is None:
                problems.append("%s: no entry called %r" % (fx, entry))
                continue
            rm, dm = hdr[0], hdr[1]
            if not (dm & 0x40):
                problems.append("%s: %r's data method byte is 0x%02x and "
                                "carries no Optimizer bit" % (fx, entry, dm))
            if (dm & 0x0F) != method:
                problems.append("%s: %r is method %d under the bit, not %d"
                                % (fx, entry, dm & 0x0F, method))
            if hdr[106] != 255 or hdr[108] != 0:
                problems.append("%s: %r's optimizer bytes are %d/%d, and "
                                "`Text 1` writes 255 with no resource fork"
                                % (fx, entry, hdr[106], hdr[108]))
            if int.from_bytes(hdr[84:88], "big") != 0:
                problems.append("%s: %r declares a resource fork, and "
                                "`Text 1` deletes it" % (fx, entry))
            # 255 must be DECODED, not refused: those are the only
            # bytes that exist (src/fmt_sit.c).
            o = os.path.join(work, "wild-" + fx)
            rc, msg = extract(args.macextract, path, o)
            want = [e for e in json.load(open(man))["entries"]
                    if e["name"] == entry]
            got = os.path.join(o, entry)
            if rc != 0 or not os.path.exists(got):
                problems.append("%s did not extract: %s"
                                % (fx, msg.strip()[:120]))
            elif want and hashlib.sha256(
                    open(got, "rb").read()).hexdigest() != \
                    want[0]["data_sha256"]:
                problems.append("%s: %r is not the oracle's bytes"
                                % (fx, entry))
            if os.path.exists(got + ".rsrc"):
                problems.append("%s: a resource fork was written for %r"
                                % (fx, entry))
        if seen != len(wild):
            print("run_sitopt: %d of %d wild optimized fixtures present — "
                  "the rest is not graded (fixtures/SOURCES.md)"
                  % (seen, len(wild)))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for p in problems:
        print("run_sitopt: %s" % p)
    print("run_sitopt: 28 archive(s) StuffIt Deluxe 2.0.1 wrote — all five "
          "Optimizers — graded against its own unstuffer and its own "
          "Engine, plus 4 optimized archives nobody here made, %d of them "
          "carrying a module this engine UNDOES, %d problem(s)"
          % (wild_graded, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
