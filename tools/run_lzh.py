#!/usr/bin/env python3
"""run_lzh.py — LZH/LHA extraction, graded by two other implementations.

The Macintosh corpus holds exactly one `.lzh` (an Amiga one, on purpose:
fixtures/SOURCES.md), which is why the format was out of scope until
2026-08-23. What put it in reach is somebody else's test corpus:
`reference/lhasa/test/archives` is 160-odd archives written by fourteen
different LHA implementations — MacLHA 2.24, LHa for Amiga, OS/2, OS-9,
X68000, Atari, LHArk, LHMelt, LArc 3.33 — covering every method this
engine implements and all four header levels.

Three graders, and they are NOT interchangeable:

Since 2026-09-19 the first two swap roles depending on the method:
fmt_lzh.c's HEADER WALK is XADMaster's, its DECODERS for -lh4- .. -lh7-
and LArc's -lz5-/-lzs- are lhasa's (DECISIONS.md, the match that was
walked twice). So:

  1. `unar` — XADMaster. On the header walk it catches a transcription
     error and nothing else; on the static and LArc methods it is now
     the independent reader, and can disagree with our source.
  2. `lhasa` (built from reference/lhasa) — Simon Howard's reading of
     the format, from the specifications rather than from XADMaster.
     On the header walk it is the independent one; on the decoders it
     is what they were written from, so agreement there says the
     reading was faithful and no more.
  3. LHa for UNIX 1.14i (built from reference/lha) — the original
     program, used here as an ENCODER: it writes archives whose plain
     text we already know, which is the only check in this file that
     depends on no reader but itself.

Grader 2 has earned its place twice already: `unar` cannot read LHA for
OS-9/68k's level 2 headers (they are two bytes short and lhasa
compensates), and it fails on a 1.2 MB -lh7- file that lhasa and this
engine both decode. Both are archives where agreeing with the oracle
would have been the wrong answer.

What this suite CANNOT see:

  * Anything about PMarc (-pm0-/-pm1-/-pm2-), LHArk's -lh7-, -lhx- or
    the self-extracting archives: they are named in SKIP below as out
    of scope, and a change that made one of them extract would be
    reported as an unexpected pass rather than caught as a bug.
  * -lh2- and -lh3-, which no archive in reach uses (OPEN_ITEMS.md).
  * Whether our TYPE and CREATOR codes are right for a Mac entry
    beyond what `unar` reports: lhasa throws the resource fork and the
    Finder info away, so on MacLHA archives it grades the data fork
    only. The differential suite (fixtures/manifests) is what holds
    those to the oracle.
  * File modification dates. This engine converts neither MS-DOS nor
    Unix timestamps (FORMATS.md), so there is nothing to compare.
"""
import hashlib
import struct
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
LHASA_SRC = os.path.abspath(os.path.join(ROOT, "reference", "lhasa"))
LHA_SRC = os.path.abspath(os.path.join(ROOT, "reference", "lha"))
ARCHIVES = os.path.join(LHASA_SRC, "test", "archives")
LHASA_BIN = os.path.abspath(os.path.join(ROOT, "build", "lhasa", "lhasa"))
VMAC_HOME = os.environ.get("UNC_VMAC_HOME",
                           os.path.expanduser("~/.cache/macextract/vmac"))
MACLHA = os.path.join(VMAC_HOME, "specimens", "maclha")
LHA_BIN = os.path.abspath(os.path.join(ROOT, "build", "lha", "lha"))

# Archives this project deliberately does not read, and why. Each is
# checked to be REFUSED rather than skipped silently: an entry here that
# suddenly extracts is reported.
SKIP = {
    "generated/pm1/pm1.pma": "PMarc, out of scope",
    "pmarc124/mtcd.pma": "PMarc, out of scope",
    "pmarc124/pm0.pma": "PMarc, out of scope",
    "pmarc124/pm1.pma": "PMarc, out of scope",
    "pmarc124/pm1_long.pma": "PMarc, out of scope",
    "pmarc2/comment.pma": "PMarc, out of scope",
    "pmarc2/long.pma": "PMarc, out of scope",
    "pmarc2/pm0.pma": "PMarc, out of scope",
    "pmarc2/pm2.pma": "PMarc, out of scope",
    "pmarc2/sfx.com": "PMarc self-extracting, out of scope",
    "larc333/sfx.com": "self-extracting (executable prefix), out of scope",
    "lha213/sfx.exe": "self-extracting, out of scope",
    "lha255e/sfx.exe": "self-extracting, out of scope",
    "lha_amiga_122/sfx.run": "self-extracting, out of scope",
    "lha_x68k_213/sfx.x": "self-extracting, out of scope",
    "lharc113/sfx.com": "self-extracting, out of scope",
    "lharc_atari_313a/sfx.tos": "self-extracting, out of scope",
    "lhmelt_16536/sfx_winsfx32_213.exe": "self-extracting, out of scope",
    "lhmelt_16536/sfx_winsfx32m_250.exe": "self-extracting, out of scope",
    "lhmelt_16536/sfx_winsfx_213.exe": "self-extracting, out of scope",
    "lhmelt_16536/sfx_winsfxm_250.exe": "self-extracting, out of scope",
    "unlha32/h2_lhx.lzh": "-lhx-, out of scope",
    "unlha32/lhx_long.lzh": "-lhx-, out of scope",
    "lhark04d/lh7.lzh": "LHArk's own method behind an -lh7- label",
    "lhark04d/lh7_long.lzh": "LHArk's own method behind an -lh7- label",
}

# Archives whose entries this engine reports but does not create, so a
# comparison of extracted files is not the right check. Symbolic links
# are stored as one entry named "link|target"; classic Mac OS has none,
# and tar's reader gives the same answer (fmt_exo.c).
LINKS = {
    "lha_unix114i/h0_symlink.lzh",
    "lha_unix114i/h1_symlink.lzh",
    "lha_unix114i/h1_symlink2.lzh",
    "lha_unix114i/h2_symlink.lzh",
    "lha_unix114i/h2_symlink2.lzh",
    "lha_unix114i/h2_symlink3.lzh",
    "lha_unix114i/h0_symlink2.lzh",
    "lha_unix114i/h0_symlink3.lzh",
    "lha_unix114i/h1_symlink3.lzh",
    "regression/symlink1.lzh",
    "regression/symlink2.lzh",
    "regression/symlink3.lzh",
}

# Archives that try to escape the extraction directory. The CLI defuses
# "." and ".." into "_" for EVERY format (cli/main.c, name_to_fs) where
# unar renames them "__Parent__", so the two disagree by design; what
# matters is that nothing lands outside the output directory, and that
# is what is checked instead.
ESCAPES = {"regression/dotdot.lzh", "regression/abspath.lzh"}

# Two archives lhasa reads as EMPTY. Both are level 0 sets that begin
# with a `-lhd-` entry whose name is zero bytes long; lhasa stops there
# and lists nothing, where `unar` and this engine both walk on and
# extract the file that follows. Measured, 2026-08-23: `lhasa -l` says
# "Total 0 files" for these two and for no other archive here.
LHASA_DECLINES = {
    "lha_unix114i/h0_subdir.lzh",
    "lha_osk_201/h0_subdir.lzh",
}

# LHA for OS-9/68k's level 2 headers are two bytes short (fmt_lzh.c),
# so `unar` mis-reads them: on this one it stops after the first
# directory instead of failing outright, which is the one case where
# its output is wrong rather than absent. lhasa grades it instead.
UNAR_MISREADS = {"lha_osk_201/h2_subdir.lzh"}

# Truncated on purpose: both readers fail the entry, and comparing what
# each wrote before it noticed is not a property of the format.
TRUNCATED = {"regression/truncated.lzh"}


def unlock(d):
    """Archives carry read-only directory permissions; walk needs +x."""
    for r, ds, _ in os.walk(d):
        for x in ds:
            try:
                os.chmod(os.path.join(r, x), 0o755)
            except OSError:
                pass


def snapshot(d):
    """{relative path: sha256 or "DIR"} for a whole tree."""
    out = {}
    for r, ds, fs in os.walk(d):
        for f in fs:
            p = os.path.join(r, f)
            rel = os.path.relpath(p, d)
            if os.path.islink(p):
                out[rel] = "LINK:" + os.readlink(p)
            else:
                out[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
        for x in ds:
            out[os.path.relpath(os.path.join(r, x), d) + "/"] = "DIR"
    return out


def build_lhasa():
    """Compile lhasa out of reference/. Its warnings are somebody else's."""
    if os.path.exists(LHASA_BIN):
        return True
    if not os.path.isdir(os.path.join(LHASA_SRC, "lib")):
        return False
    os.makedirs(os.path.dirname(LHASA_BIN), exist_ok=True)
    cfg = os.path.join(os.path.dirname(LHASA_BIN), "config.h")
    with open(cfg, "w") as f:
        f.write('#define PACKAGE_STRING "lhasa"\n'
                '#define PACKAGE_NAME "lhasa"\n'
                '#define PACKAGE_VERSION "0.4.0"\n'
                '#define VERSION "0.4.0"\n')
    # Four of the .c files are #included by others, not compiled.
    included = ("bit_stream_reader.c", "lh_new_decoder.c", "pma_common.c",
                "tree_decode.c", "lha_arch_win32.c")
    src = [os.path.join(LHASA_SRC, "lib", f)
           for f in sorted(os.listdir(os.path.join(LHASA_SRC, "lib")))
           if f.endswith(".c") and f not in included]
    src += [os.path.join(LHASA_SRC, "src", f)
            for f in sorted(os.listdir(os.path.join(LHASA_SRC, "src")))
            if f.endswith(".c")]
    r = subprocess.run(["gcc", "-w", "-O1",
                        "-I", os.path.dirname(LHASA_BIN),
                        "-I", os.path.join(LHASA_SRC, "lib", "public"),
                        "-I", LHASA_SRC, "-o", LHASA_BIN] + src,
                       capture_output=True)
    return r.returncode == 0 and os.path.exists(LHASA_BIN)


def build_lha():
    """Compile LHa for UNIX 1.14i out of reference/. 1989 K&R C."""
    if os.path.exists(LHA_BIN):
        return True
    if not os.path.isdir(os.path.join(LHA_SRC, "src")):
        return False
    os.makedirs(os.path.dirname(LHA_BIN), exist_ok=True)
    # lhdir.c is the BSD directory emulation this platform does not
    # need, and makezero.c carries a second main().
    src = [os.path.join(LHA_SRC, "src", f)
           for f in sorted(os.listdir(os.path.join(LHA_SRC, "src")))
           if f.endswith(".c") and f not in ("lhdir.c", "makezero.c")]
    tmpl = os.path.join(tempfile.gettempdir(), "lhXXXXXX")
    r = subprocess.run(["gcc", "-w", "-O1", "-std=gnu89", "-fcommon",
                        "-DSUPPORT_LH7", "-DMKTIME", "-DSYSV_SYSTEM_DIR",
                        "-DMKSTEMP", "-DSYSTIME_HAS_NO_TM",
                        '-DTMP_FILENAME_TEMPLATE="%s"' % tmpl,
                        "-o", LHA_BIN] + src, capture_output=True)
    return r.returncode == 0 and os.path.exists(LHA_BIN)


def us_extract(macextract, archive, out):
    return subprocess.run([macextract, "x", "-nr", "--forks", "hidden",
                           "-o", out, archive], capture_output=True,
                          timeout=600)


def sweep(macextract, problems):
    """Every archive in lhasa's collection, against unar and lhasa."""
    ran = graded_unar = graded_lhasa = 0
    names = []
    for dp, _, fn in os.walk(ARCHIVES):
        for f in fn:
            if f == "README":
                continue
            names.append(os.path.relpath(os.path.join(dp, f), ARCHIVES))
    for name in sorted(names):
        archive = os.path.join(ARCHIVES, name)
        ours = tempfile.mkdtemp()
        try:
            r = us_extract(macextract, archive, ours)
            if name in SKIP:
                # Refused, and nothing written.
                if r.returncode == 0 or os.listdir(ours):
                    problems.append("%s: %s, but we extracted it"
                                    % (name, SKIP[name]))
                ran += 1
                continue
            if name in ESCAPES:
                for root, _, fs in os.walk(ours):
                    for f in fs:
                        p = os.path.realpath(os.path.join(root, f))
                        if not p.startswith(os.path.realpath(ours)):
                            problems.append("%s: wrote outside the output "
                                            "directory: %s" % (name, p))
                ran += 1
                continue
            if name in TRUNCATED:
                if r.returncode == 0:
                    problems.append("%s: truncated archive extracted cleanly"
                                    % name)
                ran += 1
                continue

            got = snapshot(ours)

            # 1. unar, where it can read the archive at all.
            theirs = tempfile.mkdtemp()
            ur = subprocess.run(["unar", "-q", "-k", "hidden", "-o", theirs,
                                 archive], capture_output=True, timeout=600)
            unlock(theirs)
            if ur.returncode == 0 and name not in LINKS \
                    and name not in UNAR_MISREADS:
                want = snapshot(theirs)
                # unar drops a multi-entry archive into a directory of
                # its own, named after the archive.
                stem = os.path.basename(name).rsplit(".", 1)[0]
                inner = os.path.join(theirs, stem)
                alt = (snapshot(inner)
                       if os.listdir(theirs) == [stem] and os.path.isdir(inner)
                       else None)
                if got != want and (alt is None or got != alt):
                    problems.append("%s: differs from unar: ours=%s theirs=%s"
                                    % (name, sorted(got)[:3],
                                       sorted(alt or want)[:3]))
                else:
                    graded_unar += 1
            shutil.rmtree(theirs, ignore_errors=True)

            # 2. lhasa, the independent reading. It strips MacBinary and
            # keeps the DATA fork only, so on a MacLHA archive the
            # resource forks (our "._name" sidecars) are ours alone.
            theirs = tempfile.mkdtemp()
            lr = subprocess.run([LHASA_BIN, "-eqw=" + theirs, archive],
                                capture_output=True, timeout=600,
                                cwd=theirs)
            unlock(theirs)
            if lr.returncode == 0 and name not in LINKS \
                    and name not in LHASA_DECLINES:
                want = snapshot(theirs)
                mine = {k: v for k, v in got.items()
                        if not os.path.basename(k).startswith("._")}
                # lhasa lower-cases names out of MS-DOS archives unless
                # told not to; compare case-insensitively rather than
                # arguing about it, since `unar` above holds the names.
                mine = {k.lower(): v for k, v in mine.items()}
                want = {k.lower(): v for k, v in want.items()}
                if mine != want:
                    onlyus = sorted(set(mine) - set(want))
                    onlythem = sorted(set(want) - set(mine))
                    differ = sorted(k for k in set(mine) & set(want)
                                    if mine[k] != want[k])
                    problems.append(
                        "%s: differs from lhasa: only-ours=%s only-theirs=%s "
                        "content-differs=%s"
                        % (name, onlyus[:3], onlythem[:3], differ[:3]))
                else:
                    graded_lhasa += 1
            shutil.rmtree(theirs, ignore_errors=True)
            ran += 1
        finally:
            unlock(ours)
            shutil.rmtree(ours, ignore_errors=True)
    return ran, graded_unar, graded_lhasa


# Inputs chosen for what they make the ENCODER do.
def subjects():
    return {
        # Long runs: the match coder's whole point.
        "runs.bin": (b"=" * 300 + b"\0" * 500 + b"ab" * 400),
        # Text, which is what these archives held in 1990.
        "text.txt": (b"LHarc came from Japan in 1988, LHa followed.\n" * 220),
        # Incompressible, so a block's literal code carries everything.
        "random.bin": bytes((i * 37 + (i >> 3) * 101) & 0xFF
                            for i in range(9000)),
        # Empty, and one byte: the ends of the range.
        "empty.bin": b"",
        "one.bin": b"x",
    }


def generated(macextract, problems):
    """LHa 1.14i writes; we read; the bytes must be what went in."""
    ran = 0
    work = tempfile.mkdtemp()
    try:
        data = subjects()
        for name, content in sorted(data.items()):
            open(os.path.join(work, name), "wb").write(content)
        # Every method this encoder can write, at every header level it
        # can write. -lh0- comes from `z`, the rest from `o5`/`o6`/`o7`.
        for method, mflag in (("lh0", "z"), ("lh5", "o5"), ("lh6", "o6"),
                              ("lh7", "o7")):
            for level in (0, 1, 2):
                arc = os.path.join(work, "%s_h%d.lzh" % (method, level))
                r = subprocess.run([LHA_BIN, "a%sq1%d" % (mflag, level), arc]
                                   + sorted(data), cwd=work,
                                   capture_output=True)
                if r.returncode != 0 or not os.path.exists(arc):
                    problems.append("lha would not write %s level %d: %s"
                                    % (method, level,
                                       r.stderr.decode()[:100]))
                    continue
                out = tempfile.mkdtemp()
                try:
                    us_extract(macextract, arc, out)
                    for fname, content in sorted(data.items()):
                        p = os.path.join(out, fname)
                        if not os.path.exists(p):
                            problems.append("%s level %d: %s missing"
                                            % (method, level, fname))
                        elif open(p, "rb").read() != content:
                            problems.append("%s level %d: %s differs"
                                            % (method, level, fname))
                    ran += 1
                finally:
                    shutil.rmtree(out, ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return ran


LH2_BIN = os.path.abspath(os.path.join(ROOT, "build", "lha-lh2", "src", "lha"))
LH2_REV = "16619b066b189ef289bb8b07b37d1c38d550da99"
LH2_TAR = os.path.join(ROOT, "reference", "lha-lh2-%s.tar.gz" % LH2_REV)
LH2_PATCH = os.path.join(ROOT, "tools", "lha-lh2", "lh2-encoder.patch")


def build_lh2():
    """The LHa that can WRITE -lh2-, built from reference/ on demand.

    The source is a pristine pinned tarball (sh tools/build_lha_lh2.sh
    fetches it); the encoder is tools/lha-lh2/lh2-encoder.patch, applied
    HERE rather than in reference/, which stays as it was downloaded.
    Built into build/ like everything else, and rebuilt after a clean —
    the first arrangement kept it only in build/, where `make clean`
    deleted it and the -lh2- grading vanished without a word.
    """
    if os.path.exists(LH2_BIN):
        return True
    if not os.path.exists(LH2_TAR) or not os.path.exists(LH2_PATCH):
        return False
    dest = os.path.join(ROOT, "build", "lha-lh2")
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    if subprocess.run(["tar", "xzf", LH2_TAR, "-C", dest,
                       "--strip-components=1"], capture_output=True).returncode:
        return False
    if subprocess.run(["patch", "-s", "-p1", "-d", dest, "-i", LH2_PATCH],
                      capture_output=True).returncode:
        return False
    # 2020s compiler, 1990s C: implicit int and implicit declarations are
    # errors by default now and this tree is full of both.
    cf = ("-std=gnu89 -Wno-implicit-int -Wno-implicit-function-declaration "
          "-Wno-return-mismatch -O2")
    for cmd in (["autoreconf", "-i"], ["./configure", "CFLAGS=" + cf],
                ["make", "-j2"]):
        if subprocess.run(cmd, cwd=dest, capture_output=True).returncode:
            return False
    return os.path.exists(LH2_BIN)


def archive_methods(path):
    """The method string of every entry, straight out of the headers.

    Read here rather than taken on trust: LHa falls back to -lh0- for
    anything it cannot shrink, so a suite that only compared bytes would
    pass with flying colours having exercised no -lh2- at all.
    """
    d = open(path, "rb").read()
    out, p = [], 0
    while p + 21 < len(d) and d[p]:
        out.append(d[p + 2:p + 7].decode("latin1"))
        level = d[p + 20]
        size = int.from_bytes(d[p + 7:p + 11], "little")
        if level == 0:
            p += d[p] + 2 + size
        elif level == 1:
            # In level 1 the size field covers the extended headers AND
            # the data, measured from the end of the base header — which
            # is why walking the extension chain by hand got this wrong
            # and reported one -lh0- entry for a whole archive.
            p += d[p] + 2 + size
        elif level == 2:
            p += int.from_bytes(d[p:p + 2], "little") + size
        else:
            break
    return out


def lh2(macextract, problems):
    """-lh2-, which nothing in the world writes any more.

    `tools/build_lha_lh2.sh` teaches LHa for UNIX to write it — upstream
    only decodes it — so the data here is the reference implementation's,
    and that program's own decoder verifies each archive before this
    engine is handed one. Returns the number of -lh2- entries graded.
    """
    if not build_lh2():
        print("run_lzh: no -lh2- encoder (sh tools/build_lha_lh2.sh fetches "
              "its source) — the -lh2- cases are skipped")
        return 0
    graded = 0
    work = tempfile.mkdtemp()
    try:
        data = dict(subjects())
        # Two more, for what -lh2- has that -lh1- does not: a position
        # tree that grows with the output, so offsets near the far end of
        # the window only become expressible late.
        data["far.bin"] = (bytes((i * 91 + 7) & 0xFF for i in range(6000))
                           + b"PAD" * 100
                           + bytes((i * 91 + 7) & 0xFF for i in range(6000)))
        data["zeros.bin"] = b"\0" * 40000
        for name, content in sorted(data.items()):
            open(os.path.join(work, name), "wb").write(content)
        for level in (0, 1, 2):
            arc = os.path.join(work, "lh2_h%d.lzh" % level)
            r = subprocess.run([LH2_BIN, "ao2q1%d" % level, arc]
                               + sorted(data), cwd=work, capture_output=True)
            if r.returncode != 0 or not os.path.exists(arc):
                problems.append("the -lh2- encoder would not write level %d: %s"
                                % (level, r.stderr.decode()[:100]))
                continue
            methods = archive_methods(arc)
            n2 = methods.count("-lh2-")
            if n2 < 3:
                problems.append("level %d holds %d -lh2- entries, not enough "
                                "to be grading anything (%s)"
                                % (level, n2, methods))
                continue
            # The encoder's own decoder first: if THAT cannot read it, the
            # archive is the thing at fault and not this engine.
            t = subprocess.run([LH2_BIN, "t", arc], cwd=work,
                               capture_output=True)
            if t.returncode != 0:
                problems.append("the -lh2- encoder wrote a level %d archive "
                                "its own decoder refuses" % level)
                continue
            out = tempfile.mkdtemp()
            try:
                us_extract(macextract, arc, out)
                for fname, content in sorted(data.items()):
                    q = os.path.join(out, fname)
                    if not os.path.exists(q):
                        problems.append("-lh2- level %d: %s missing" % (level, fname))
                    elif open(q, "rb").read() != content:
                        problems.append("-lh2- level %d: %s differs" % (level, fname))
                graded += n2
            finally:
                shutil.rmtree(out, ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return graded


# ---------------------------------------------------------------- -lh3-
#
# LHa DECODES -lh3- and cannot write it, and teaching it to would mean
# building and transmitting a table per block rather than mirroring a
# shared tree, as -lh2-'s patch does. So the encoder is here instead: a
# minimal one, whose only job is to produce streams THE REFERENCE accepts.
# Every archive it makes is extracted by LHa itself before this engine is
# handed one, so the grading is still three-way — the bytes, LHa, and us.

LH3_N1, LH3_NP, LH3_CBIT, LH3_LENFIELD, LH3_BUFBITS = 286, 128, 9, 4, 16


class _Bits:
    def __init__(self):
        self.bits = []

    def put(self, value, n):
        for i in range(n - 1, -1, -1):
            self.bits.append((value >> i) & 1)

    def bytes(self):
        while len(self.bits) % 8:
            self.bits.append(0)
        return bytes(int("".join(str(b) for b in self.bits[i:i + 8]), 2)
                     for i in range(0, len(self.bits), 8))


def _huff_lengths(freqs, limit):
    live = [(f, i) for i, f in enumerate(freqs) if f]
    if not live:
        return [0] * len(freqs)
    if len(live) == 1:
        out = [0] * len(freqs)
        out[live[0][1]] = 1
        return out
    import heapq
    nodes = [(f, [i]) for f, i in live]
    heapq.heapify(nodes)
    out = [0] * len(freqs)
    while len(nodes) > 1:
        f1, s1 = heapq.heappop(nodes)
        f2, s2 = heapq.heappop(nodes)
        for sym in s1 + s2:
            out[sym] += 1
        heapq.heappush(nodes, (f1 + f2, s1 + s2))
    if max(out) > limit:
        return [limit if x else 0 for x in out]
    return out


def _canon(lengths):
    codes, code = {}, 0
    top = max(lengths) if any(lengths) else 0
    for bits in range(1, top + 1):
        for sym, l in enumerate(lengths):
            if l == bits:
                codes[sym] = code
                code += 1
        code <<= 1
    return codes


def lh3_stream(data, single=False, send_p_tree=False):
    """One -lh3- block. `single` uses the format's "this block is one
    symbol" escape — three code lengths of 1 in a row, then the symbol —
    and `send_p_tree` sends a position tree instead of leaving the
    decoder to use the fixed one. Both are paths a decoder can only reach
    if something writes them."""
    out = _Bits()
    out.put(len(data), LH3_BUFBITS)
    # One distinct symbol cannot be sent as a tree: a single code of
    # length 1 is an INCOMPLETE table and LHa refuses it ("Bad table (case
    # b)"), which is what the escape exists for. Found by the guard below,
    # not by reading — this engine's canonical builder accepts such a
    # table and would have decoded it happily forever.
    if len(set(data)) <= 1 and data:
        single = True
    if single:
        for _ in range(3):
            out.put(1, 1)
            out.put(0, LH3_LENFIELD)     # length 1, sent as 1 - 1
        out.put(data[0], LH3_CBIT)
        codes, lens = None, None
    else:
        freqs = [0] * LH3_N1
        for b in data:
            freqs[b] += 1
        lens = _huff_lengths(freqs, 15)
        codes = _canon(lens)
        for i in range(LH3_N1):
            if lens[i]:
                out.put(1, 1)
                out.put(lens[i] - 1, LH3_LENFIELD)
            else:
                out.put(0, 1)
    if send_p_tree:
        out.put(1, 1)
        # Seven bits each over 128 symbols is a COMPLETE code; eight is
        # half a table and LHa says so.
        for _ in range(LH3_NP):
            out.put(7, LH3_LENFIELD)
    else:
        out.put(0, 1)                    # the fixed table
    if not single:
        for b in data:
            out.put(codes[b], lens[b])
    return out.bytes()


def lh3_crc16(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def lh3_archive(entries):
    """A level-0 .lzh of -lh3- entries: [(name, data, kwargs)]."""
    out = b""
    for name, data, kw in entries:
        packed = lh3_stream(data, **kw)
        nb = name.encode("latin1")
        head = (b"-lh3-" + struct.pack("<I", len(packed))
                + struct.pack("<I", len(data))
                + struct.pack("<I", 0x50000000)
                + bytes([0x20, 0x00, len(nb)]) + nb
                + struct.pack("<H", lh3_crc16(data)))
        out += bytes([len(head), sum(head) & 0xFF]) + head + packed
    return out + b"\x00"


def lh3(macextract, problems):
    """-lh3-, three ways: the bytes, LHa's decoder, and this engine."""
    if not build_lh2():          # the same binary; it DECODES -lh3-
        print("run_lzh: no LHa that decodes -lh3- — those cases are skipped")
        return 0
    text = b"LHarc 1.13 wrote -lh3- and almost nothing else ever did.\n" * 40
    cases = [
        ("text.txt", text, {}),
        ("runs.bin", b"=" * 400 + b"\0" * 600 + b"ab" * 300, {}),
        ("random.bin", bytes((i * 37 + (i >> 3) * 101) & 0xFF
                             for i in range(4000)), {}),
        ("one.bin", b"x", {}),               # one symbol: takes the escape
        # The two escapes, which a compressor would rarely emit and a
        # decoder still has to read.
        ("single.bin", b"Q" * 5000, {"single": True}),
        ("ptree.txt", text, {"send_p_tree": True}),
    ]
    graded = 0
    work = tempfile.mkdtemp()
    try:
        arc = os.path.join(work, "lh3.lzh")
        open(arc, "wb").write(lh3_archive(cases))
        # LHa first: if IT cannot read the archive, the archive is wrong.
        out_ref = os.path.join(work, "ref")
        os.makedirs(out_ref)
        r = subprocess.run([LH2_BIN, "x", arc], cwd=out_ref,
                           capture_output=True)
        for name, data, _kw in cases:
            q = os.path.join(out_ref, name)
            if r.returncode != 0 or not os.path.exists(q) \
                    or open(q, "rb").read() != data:
                problems.append("the -lh3- encoder wrote %s that LHa itself "
                                "does not read back" % name)
        out = os.path.join(work, "ours")
        os.makedirs(out)
        us_extract(macextract, arc, out)
        for name, data, _kw in cases:
            q = os.path.join(out, name)
            if not os.path.exists(q):
                problems.append("-lh3-: %s missing" % name)
            elif open(q, "rb").read() != data:
                problems.append("-lh3-: %s differs" % name)
            else:
                graded += 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return graded


def maclha(macextract, problems):
    """The archive MacLHA itself wrote, if this machine has made one.

    `tools/vmac/maclha.py` runs MacLHA 2.00 under Mini vMac and archives
    a file with a real resource fork — the one thing sixteen MacLHA
    archives in lhasa's collection do not have between them. The
    archive and the two forks that went into it live beside the
    emulator, so a fresh clone skips this and says so."""
    arcs = ([f for f in sorted(os.listdir(MACLHA)) if f.endswith(".lzh")]
            if os.path.isdir(MACLHA) else [])
    if not arcs:
        print("run_lzh: no MacLHA specimen in %s, skipped "
              "(tools/vmac/maclha.py --make)" % MACLHA)
        return 0
    want_d = open(os.path.join(MACLHA, "in-data"), "rb").read()
    want_r = open(os.path.join(MACLHA, "in-rsrc"), "rb").read()
    ran = 0
    for a in arcs:
        out = tempfile.mkdtemp()
        try:
            r = us_extract(macextract, os.path.join(MACLHA, a), out)
            got = snapshot(out)
            names = [k for k in got if not os.path.basename(k).startswith("._")]
            if r.returncode != 0 or len(names) != 1:
                problems.append("maclha %s: exit %d, wrote %r"
                                % (a, r.returncode, sorted(got)))
                continue
            name = names[0]
            d = open(os.path.join(out, name), "rb").read()
            head, _, tail = name.rpartition("/")
            rp = os.path.join(out, "%s/._%s" % (head, tail) if head
                              else "._" + tail)
            rs = open(rp, "rb").read() if os.path.exists(rp) else b""
            if d != want_d:
                problems.append("maclha %s: data fork %d B, wanted %d B"
                                % (a, len(d), len(want_d)))
            if rs != want_r:
                problems.append("maclha %s: resource fork %d B, wanted %d B "
                                "— MacLHA's payload was not split"
                                % (a, len(rs), len(want_r)))
            ran += 1
        finally:
            shutil.rmtree(out, ignore_errors=True)
    return ran


def main():
    macextract = os.path.join(ROOT, "build", "macextract")
    args = sys.argv[1:]
    if "--macextract" in args:
        macextract = args[args.index("--macextract") + 1]
    if not os.path.exists(macextract):
        print("run_lzh: no CLI at %s" % macextract)
        return 1
    if not os.path.isdir(ARCHIVES):
        print("run_lzh: SKIPPED — no reference/lhasa "
              "(tools/fetch_references.sh)")
        return 0
    if not build_lhasa():
        # NOT a skip, since 2026-09-09: reference/lhasa is right there —
        # the check above just said so — and without it nothing in the
        # sweep below is graded against an independent reader. A suite
        # that returns 0 with no oracle is a suite that tests nothing,
        # which is how a broken munpack build stayed green (DECISIONS.md
        # 2026-09-09).
        print("run_lzh: reference/lhasa is present and will not compile "
              "here, so nothing below is graded against an independent "
              "reader.")
        print("run_lzh: fix the build, or delete reference/lhasa to make "
              "this a skip.")
        return 1

    problems = []
    ran, by_unar, by_lhasa = sweep(macextract, problems)
    mac = maclha(macextract, problems)
    gen = 0
    if build_lha():
        gen = generated(macextract, problems)
    else:
        print("run_lzh: no reference/lha — the generated cases are skipped")

    old = lh2(macextract, problems)
    old3 = lh3(macextract, problems)

    for p in problems:
        print("run_lzh: FAIL: %s" % p)
    print("run_lzh: %d archive(s) checked (%d against unar, %d against "
          "lhasa), %d generated set(s), %d MacLHA specimen(s), "
          "%d -lh2- and %d -lh3- entr(y/ies)"
          % (ran, by_unar, by_lhasa, gen, mac, old, old3))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
