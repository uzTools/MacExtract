#!/usr/bin/env python3
"""run_hecx.py — BinHex before 4.0 (`.hex`, `.hcx`) and SUMacC's `.dl`,
adjudicated by hexbin.

`unar` cannot read either encoding, so the reader graded against is
macutils' `hexbin` (hecx.c), which is also what src/fmt_hecx.c is
transcribed from. That is one implementation agreeing with its own
transcription, and it is not all that is here: the four `derived-bh2-*`
fixtures were WRITTEN by BinHex 2.0 itself on an emulated Mac from a
two-fork subject whose bytes are known (tools/vmac/binhex2.py), so their
forks are also checked against that subject — the writer, not a reader,
is the ground truth for them.

    run_hecx.py [--macextract BIN]     grade, and the variants below
    run_hecx.py --manifests            (re)write the eight manifests

Graded per fixture: both forks, type and creator, against hexbin. Two of
the three 1985 files have no banner and hexbin will not read them as they
are (fmt_hecx.c says why); hexbin is handed a copy with one added.

Then variants of a fixture, each with what must happen. Where hexbin can
be asked, it is asked, and must agree; where this reader departs from it
on purpose, the departure is asserted rather than hidden:

  lf / crlf endings          same forks                 hexbin agrees
  trailing spaces stripped   same forks (.hcx puts back the "lost spaces";
                             hexbin cannot when a line is cut to one
                             character, which fmt_hecx.c says why)
  mail headers in front      same forks                 hexbin agrees
  forks in the other order   same forks (.hex only: the .hcx CRC rotates,
                             so it fixes the order)  hexbin agrees
  banner removed             same forks                 hexbin CANNOT read it
  a body byte changed        refused (sum or CRC)       hexbin refuses
  the sum line changed       refused                    hexbin refuses
  no sum line                refused                    hexbin refuses
  cut inside a fork          refused, never exit 0
  lower-case hex digits      refused                    hexbin refuses
  the same fork twice        refused                    hexbin appends them,
                                                        and its CRC refuses
  a '#..$hhhh' line + prose  not recognised as this format

`.dl` (src/fmt_hecx.c, dl_walk) is graded by hexbin AND by SUMacC's
own tools, built from reference/sumacc: tohex, the writer, and fromhex,
its UNIX reader. The wild file must be tohex's output for its fork:

  tohex's output, 6 sizes    same fork                  hexbin, fromhex agree
  lf / crlf / cr endings     same fork                  hexbin, fromhex agree
  mail headers in front      same fork                  hexbin agrees
  rewrapped at 64            same fork                  hexbin, fromhex agree
  a line break in the sum    same fork, as hexbin       fromhex refuses
  the sum's high 16 bits     refused, as fromhex        hexbin reads it
  a body character changed   refused                    both refuse
  the sum changed            refused                    both refuse
  no '|', or cut in the sum  refused                    both refuse
  cut inside the fork        refused, never exit 0
  a first byte that is not 0 not this format            both read it
  base64 of a run of zeros   base64, not `.dl`

What it cannot see: only BinHex 2.0 has been run as a writer; for `.dl`,
SUMacC's tohex is compiled on this machine, not run as it ran on a VAX,
and the one wild file is all the output of theirs there is. BinHex 1.0
and the BASIC BinHexes before it wrote `.hex` too (reference/notes/
BinHex.md), and none of their output has been found to grade against.
"""
import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FIXDIR = os.path.join(ROOT, "fixtures")
SUBJECT = os.path.expanduser(os.path.join(
    os.environ.get("UNC_VMAC_HOME", "~/.cache/macextract/vmac"),
    "specimens", "binhex2"))

FIXTURES = ["hcx-wild-simpleto.hcx", "hcx-wild-xlisp.hcx",
            "hcx-wild-xlisptin.hcx", "derived-bh2-XF.hcx",
            "derived-bh2-XF.hex", "derived-bh2-XFlf.hex",
            "derived-bh2-YN.hex", "dl-wild-xlispold.dl"]
BANNER = b"(This file must be converted with BinHex.Hex)\r"


def read(p):
    return open(p, "rb").read() if os.path.exists(p) else None


def hexbin(blob, add_banner=False):
    """(exit, data, rsrc, type, creator) as hexbin reads `blob`."""
    if add_banner and not blob.startswith(b"(This file") \
            and not blob.startswith(b"@"):
        blob = BANNER + blob
    w = tempfile.mkdtemp()
    try:
        open(os.path.join(w, "in"), "wb").write(blob)
        r = subprocess.run(["hexbin", "-3", "in"], cwd=w, capture_output=True)
        info = read(os.path.join(w, "in.info")) or bytes(128)
        return (r.returncode, read(os.path.join(w, "in.data")),
                read(os.path.join(w, "in.rsrc")) or b"",
                info[65:69], info[69:73])
    finally:
        shutil.rmtree(w, ignore_errors=True)


def ours(cli, blob, name="t.hex"):
    """(exit, data, rsrc, type, creator) as our CLI reads `blob`."""
    w = tempfile.mkdtemp()
    try:
        src = os.path.join(w, name)
        open(src, "wb").write(blob)
        out = os.path.join(w, "o")
        os.mkdir(out)
        r = subprocess.run([cli, "x", "-nr", "--forks", "hidden", "-o", out,
                            src], capture_output=True)
        files = sorted(f for f in os.listdir(out) if not f.startswith("._"))
        data = read(os.path.join(out, files[0])) if files else None
        rsrc = (read(os.path.join(out, "._" + files[0])) or b"") if files \
            else b""
        tc = (b"", b"")
        l = subprocess.run([cli, "l", "--finder", src], capture_output=True)
        m = re.search(rb"\s([0-9a-f]{8})/([0-9a-f]{8})\s", l.stdout)
        if m:
            tc = (bytes.fromhex(m.group(1).decode()),
                  bytes.fromhex(m.group(2).decode()))
        return (r.returncode, data, rsrc, tc[0], tc[1])
    finally:
        shutil.rmtree(w, ignore_errors=True)


def sniff(cli, blob):
    w = tempfile.mkdtemp()
    try:
        p = os.path.join(w, "t")
        open(p, "wb").write(blob)
        return subprocess.run([cli, "sniff", p],
                              capture_output=True).stdout.decode().strip()
    finally:
        shutil.rmtree(w, ignore_errors=True)


def norm(code):
    """hexbin leaves a missing creator as four NULs, and so does this."""
    return code.replace(b"\0", b" ")


def grade_fixture(cli, name, problems):
    blob = read(os.path.join(FIXDIR, name))
    hb = hexbin(blob, add_banner=True)
    us = ours(cli, blob, name)
    if hb[0] != 0:
        problems.append("%s: hexbin cannot read it (exit %d)" % (name, hb[0]))
        return
    if us[0] != 0:
        problems.append("%s: exit %d" % (name, us[0]))
        return
    if us[1] != hb[1] or us[2] != hb[2]:
        problems.append("%s: forks differ from hexbin's" % name)
    if norm(us[3]) != norm(hb[3]) or norm(us[4]) != norm(hb[4]):
        problems.append("%s: type/creator %r/%r, hexbin %r/%r"
                        % (name, us[3], us[4], hb[3], hb[4]))
    # The BinHex 2.0 specimens: the subject that went in.
    if name.startswith("derived-bh2-") and name != "derived-bh2-YN.hex":
        want_d = read(os.path.join(SUBJECT, "in-data"))
        want_r = read(os.path.join(SUBJECT, "in-rsrc"))
        if want_d is None:
            problems.append("%s: no subject in %s (binhex2.py --make)"
                            % (name, SUBJECT))
        elif us[1] != want_d or us[2] != want_r or us[3] != b"Junk" \
                or us[4] != b"Test":
            problems.append("%s: not the subject BinHex 2.0 was given"
                            % name)


def lines(blob):
    return re.split(rb"(\r\n|\r|\n)", blob)


def relines(blob, eol):
    return eol.join(re.split(rb"\r\n|\r|\n", blob))


def swap_forks(blob):
    """Move the RESOURCE section after the DATA one."""
    parts = re.split(rb"(?=\*\*\*(?:RESOURCE|DATA))", blob)
    head, secs = parts[0], parts[1:]
    tail_at = secs[-1].find(b"***CRC") if b"***CRC" in secs[-1] \
        else secs[-1].find(b"***CHECKSUM")
    tail = secs[-1][tail_at:]
    secs[-1] = secs[-1][:tail_at]
    return head + b"".join(reversed(secs)) + tail


def first_body_line(blob):
    """Offset of the first character of the first fork's first line."""
    i = blob.find(b"FORK")
    return blob.index(b"\r", i) + 1


def variants(cli, base, problems):
    """`base` is a fixture's bytes; returns how many cases ran."""
    ran = 0
    base = relines(base, b"\r")       # the 1985 files are LF; BinHex wrote CR
    want = ours(cli, base)
    if want[0] != 0:
        problems.append("variants: the base does not extract")
        return 0
    compressed = b"***COMPRESSED" in base

    def same(label, blob, hb_too=True):
        got = ours(cli, blob)
        if got[0] != 0 or got[1:3] != want[1:3]:
            problems.append("%s: exit %d, forks %s" % (
                label, got[0], "same" if got[1:3] == want[1:3] else "differ"))
        if hb_too:
            hb = hexbin(blob)
            if hb[0] != 0 or hb[1:3] != want[1:3]:
                problems.append("%s: hexbin does not agree" % label)

    def refused(label, blob, hb_refuses=True):
        got = ours(cli, blob)
        if got[0] == 0:
            problems.append("%s: exit 0 — should be refused" % label)
        if hb_refuses is not None:
            hb = hexbin(blob)
            if (hb[0] != 0) != hb_refuses:
                problems.append("%s: hexbin %s it" % (
                    label, "reads" if hb[0] == 0 else "refuses"))

    same("LF endings", relines(base, b"\n")); ran += 1
    same("CRLF endings", relines(base, b"\r\n")); ran += 1
    if compressed:
        cut = b"\r".join(l.rstrip(b" ") for l in base.split(b"\r"))
        same("trailing spaces stripped", cut, hb_too=False)
        ran += 1
    same("mail in front", b"From: someone\rSubject: a file\r\r" + base)
    ran += 1
    if not compressed:
        same("forks in the other order", swap_forks(base)); ran += 1
    nob = base[base.index(b"\r") + 1:]
    same("banner removed", nob, hb_too=False); ran += 1
    if hexbin(nob)[0] == 0:
        problems.append("banner removed: hexbin reads it — the departure "
                        "documented in fmt_hecx.c is not one")

    i = first_body_line(base) + 8
    flip = bytearray(base)
    if compressed:
        flip[i] = ord("!") if flip[i] != ord("!") else ord("#")
    else:
        flip[i] = ord("0") if flip[i] != ord("0") else ord("1")
    refused("a body byte changed", bytes(flip)); ran += 1
    m = re.search(rb"\*\*\*(CRC|CHECKSUM):([0-9A-Fa-f]+)", base)
    v = int(m.group(2), 16) ^ 1
    bad = base[:m.start(2)] + (b"%X" % v).rjust(len(m.group(2)), b"0") \
        + base[m.end(2):]
    refused("the sum changed", bad); ran += 1
    refused("no sum line", base[:m.start()]); ran += 1
    for frac in (0.3, 0.6, 0.9):
        cut = base[:int(m.start() * frac)]
        refused("cut at %d%%" % int(frac * 100), cut, hb_refuses=None)
        ran += 1
    if not compressed:
        j = first_body_line(base)
        e = base.index(b"\r", j)
        low = base[:j] + base[j:e].lower() + base[e:]
        if low != base:
            refused("lower-case hex digits", low); ran += 1
    k = base.index(b"***END")
    k = base.index(b"\r", k) + 1
    first = base[base.index(b"***", base.index(b"#")):k]
    if not compressed or b"***COMPRESSED" not in first:
        dup = base[:k] + first + base[k:]
    else:
        sec = first[first.index(b"***", 4):]
        dup = base[:k] + sec + base[k:]
    refused("the same fork twice", dup); ran += 1

    prose = (b"#JunkTest$0000 was a heading once\r#Junk$1234\r"
             b"Not a marker: the next line is prose.\r" * 3)
    if sniff(cli, prose) not in ("unknown", ""):
        problems.append("a '#..$hhhh' line and prose: sniffed %r"
                        % sniff(cli, prose))
    ran += 1
    return ran


SUMACC = os.path.join(ROOT, "reference", "sumacc", "cmd")


def sumacc_tools(w):
    """SUMacC's writer and its own reader, built from reference/: the
    (tohex, fromhex) paths, or None if either will not build."""
    out = []
    for name in ("tohex", "fromhex"):
        src = os.path.join(SUMACC, name + ".c")
        exe = os.path.join(w, name)
        if not os.path.exists(src) or subprocess.run(
                ["cc", "-std=gnu89", "-w", "-o", exe, src],
                capture_output=True).returncode != 0:
            return None
        out.append(exe)
    return tuple(out)


def tohex(tools, fork):
    return subprocess.run([tools[0]], input=fork,
                          capture_output=True).stdout


def fromhex(tools, blob):
    """(sum good, fork) as SUMacC's own UNIX reader reads `blob`."""
    r = subprocess.run([tools[1]], input=blob, capture_output=True)
    return b"checksum good!" in r.stderr, r.stdout


def dl_encode(fork, width=66, eol=b"\n", sum_add=0):
    """A `.dl` with dl.c's rules, for what tohex cannot be asked to write:
    another width or line ending, a wrong sum. At width 66 and "\n" it is
    tohex's own output, which dl_variants asserts."""
    body = bytes(0x40 | (b >> s & 0xF) for b in fork for s in (4, 0))
    total = (len(fork) + sum(fork) + sum_add) & 0xFFFFFFFF
    tail = b"|" + bytes(0x40 | (total >> s & 0xF)
                        for s in range(28, -4, -4))
    text = body + tail
    return eol.join(text[i:i + width]
                    for i in range(0, len(text), width)) + eol


def dl_variants(cli, problems):
    """`.dl` cases, graded by hexbin and by SUMacC's own writer and reader."""
    w = tempfile.mkdtemp()
    try:
        tools = sumacc_tools(w)
        if tools is None:
            problems.append("dl: SUMacC's tohex/fromhex do not build from "
                            "reference/sumacc (tools/fetch_references.sh)")
            return 0
        return dl_cases(cli, tools, problems)
    finally:
        shutil.rmtree(w, ignore_errors=True)


def dl_cases(cli, tools, problems):
    ran = 0

    def check(label, blob, fork, hb_reads=True, fh_good=True):
        got = ours(cli, blob, "t.dl")
        if fork is None:
            if got[0] == 0:
                problems.append("dl %s: exit 0 — should be refused" % label)
        elif got[0] != 0 or got[2] != fork or got[1] not in (b"", None):
            problems.append("dl %s: exit %d, fork %s" % (
                label, got[0], "same" if got[2] == fork else "differs"))
        if hb_reads is not None:
            hb = hexbin(blob)
            if (hb[0] == 0) != hb_reads:
                problems.append("dl %s: hexbin %s it" % (
                    label, "reads" if hb[0] == 0 else "refuses"))
            elif hb_reads and fork is not None and hb[2] != fork:
                problems.append("dl %s: hexbin's fork differs" % label)
        if fh_good is not None:
            good, fh = fromhex(tools, blob)
            if good != fh_good:
                problems.append("dl %s: fromhex says the sum is %s" % (
                    label, "good" if good else "bad"))
            elif good and fork is not None and fh != fork:
                problems.append("dl %s: fromhex's fork differs" % label)

    import random
    rnd = random.Random(1985)
    # Written by tohex, SUMacC's writer. From 33 B: tohex breaks its line
    # after every 33rd byte, so a smaller fork is one line holding '|' and
    # the sum, odd in length and no `.dl` to hexbin or here; no resource
    # fork is that small, its header alone being 256 B.
    for size in (32, 33, 4095, 4096, 4097, 70000):
        fork = bytes([0]) + bytes(rnd.randrange(256) for _ in range(size))
        blob = tohex(tools, fork)
        if blob != dl_encode(fork):
            problems.append("dl %d B: dl_encode is not tohex" % len(fork))
        check("tohex, %d B" % len(fork), blob, fork); ran += 1
    zeros = bytes(3000)
    check("tohex, zeros", tohex(tools, zeros), zeros); ran += 1

    wild = read(os.path.join(FIXDIR, "dl-wild-xlispold.dl"))
    if wild is not None:
        fork = hexbin(wild)[2]
        # The wild file is tohex's output and three blank lines.
        out = tohex(tools, fork)
        if not wild.startswith(out) or wild[len(out):].strip(b"\n"):
            problems.append("dl xlispold.dl: not what tohex writes for its "
                            "fork")
        ran += 1
        base = wild
    else:
        fork = bytes([0, 0, 1, 0]) + bytes(rnd.randrange(256)
                                           for _ in range(5000))
        base = tohex(tools, fork)
    for eol in (b"\n", b"\r\n", b"\r"):
        check("endings %r" % eol, relines(base, eol), fork); ran += 1
    # fromhex wants the headers gone (etc/download.doc); hexbin and this
    # skip them.
    check("mail in front",
          b"From: someone\nSubject: a file\n\n" + base, fork,
          fh_good=None); ran += 1
    check("rewrapped at 64", dl_encode(fork, 64), fork); ran += 1
    enc = dl_encode(fork)
    bar = enc.index(b"|")
    # hexbin reads by lines and never sees the break; fromhex takes it for
    # a digit. This follows hexbin.
    check("a line break in the sum", enc[:bar + 4] + b"\n" + enc[bar + 4:],
          fork, fh_good=False); ran += 1
    # The sum is 32 bits, as fromhex reads it (DECISIONS.md 2026-10-25, *the
    # writer that was in 4.3BSD*); hexbin compares 16 and reads this.
    check("the sum's high 16 bits changed", dl_encode(fork, sum_add=1 << 16),
          None, True, False); ran += 1

    i = base.index(b"@", 200)
    flip = bytearray(base)
    flip[i] = ord("A")
    check("a body character changed", bytes(flip), None, False, False)
    ran += 1
    check("the sum changed", dl_encode(fork, sum_add=1), None, False, False)
    ran += 1
    cut = base[:base.index(b"|")]
    check("no '|'", cut, None, False, False); ran += 1
    check("cut in the sum", base[:base.index(b"|") + 5], None, False, False)
    ran += 1
    for frac in (0.3, 0.6, 0.9):
        check("cut at %d%%" % int(frac * 100), cut[:int(len(cut) * frac)],
              None, None, None)
        ran += 1

    # The departure: a first byte that is not 0 cannot be a resource fork's
    # data offset, and the line it opens is not taken for a `.dl` here.
    # hexbin and fromhex both read it.
    odd = bytes([0x10]) + fork[1:]
    blob = tohex(tools, odd)
    if sniff(cli, blob) != "unknown":
        problems.append("dl a first byte of 0x10: sniffed %r" % sniff(cli, blob))
    if hexbin(blob)[0] != 0 or not fromhex(tools, blob)[0]:
        problems.append("dl a first byte of 0x10: hexbin or fromhex refuses "
                        "it — the departure in fmt_hecx.c is not one")
    ran += 1
    # Why: base64 of zeros is a line of 'A', which hexbin's test alone takes.
    import base64
    b64 = base64.encodebytes(bytes(4000))
    if sniff(cli, b64) != "base64":
        problems.append("dl base64 of zeros: sniffed %r" % sniff(cli, b64))
    ran += 1
    return ran


def manifests(cli):
    for name in FIXTURES:
        p = os.path.join(FIXDIR, name)
        blob = read(p)
        if blob is None:
            print("run_hecx: %s absent, no manifest" % name)
            continue
        hb = hexbin(blob, add_banner=True)
        if hb[0] != 0:
            raise SystemExit("run_hecx: hexbin cannot read %s" % name)
        stem = name.rsplit(".", 1)[0]
        e = {"name": stem,
             "data_size": len(hb[1]),
             "data_sha256": hashlib.sha256(hb[1]).hexdigest(),
             "rsrc_size": len(hb[2]),
             "rsrc_sha256": hashlib.sha256(hb[2]).hexdigest()}
        if hb[3].strip(b"\0"):
            e["type"] = hb[3].decode("mac-roman")
        if hb[4].strip(b"\0"):
            e["creator"] = hb[4].decode("mac-roman")
        oracle = "macutils' hexbin on both forks (tools/run_hecx.py)"
        if not blob.startswith(b"(This file"):
            oracle += ", handed a copy with the banner it requires"
        if name.startswith("derived-bh2-"):
            oracle += "; written by BinHex 2.0 itself (tools/vmac/binhex2.py)"
        if name.endswith(".dl"):
            oracle = "macutils' hexbin (tools/run_hecx.py), its sum verifying"
        man = {"entries": [e], "fixture": name,
               "format": "SUMacC dl" if name.endswith(".dl")
               else "BinHex hex/hcx",
               "oracle": oracle,
               "sha256": hashlib.sha256(blob).hexdigest(),
               "size": len(blob)}
        out = os.path.join(FIXDIR, "manifests", name + ".json")
        with open(out, "w") as f:
            json.dump(man, f, indent=1, sort_keys=True)
            f.write("\n")
        print("run_hecx: wrote %s" % os.path.relpath(out, ROOT))


def main():
    cli = os.path.join(ROOT, "build", "macextract")
    args = sys.argv[1:]
    if "--macextract" in args:
        cli = args[args.index("--macextract") + 1]
    if not shutil.which("hexbin"):
        print("run_hecx: no hexbin (apt install macutils)")
        return 1
    if "--manifests" in args:
        manifests(cli)
        return 0
    problems, graded, ran = [], 0, 0
    for name in FIXTURES:
        if os.path.exists(os.path.join(FIXDIR, name)):
            grade_fixture(cli, name, problems)
            graded += 1
        else:
            print("run_hecx: SKIP %s (absent)" % name)
    for name in ("derived-bh2-XF.hex", "derived-bh2-XF.hcx",
                 "hcx-wild-simpleto.hcx"):
        blob = read(os.path.join(FIXDIR, name))
        if blob is None:
            continue
        if not blob.startswith(b"(This file"):
            blob = BANNER + blob
        before = len(problems)
        n = variants(cli, blob, problems)
        ran += n
        for p in problems[before:]:
            problems[problems.index(p)] = "%s, %s" % (name, p)
    ran += dl_variants(cli, problems)
    for p in problems:
        print("HECX FAIL " + p)
    print("run_hecx: %d fixtures graded against hexbin, %d variants, %d "
          "problems" % (graded, ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
