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

  1. `unar` — XADMaster, which fmt_lzh.c is transcribed from. It catches
     a transcription error and nothing else: where we and it agree we
     have only established that the copy was faithful.
  2. `lhasa` (built from reference/lhasa) — an INDEPENDENT reading of
     the format, by Simon Howard, from the specifications rather than
     from XADMaster. This is the one that can disagree with our source.
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
                           os.path.expanduser("~/.cache/unclassic/vmac"))
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


def us_extract(unclassic, archive, out):
    return subprocess.run([unclassic, "x", "-nr", "--forks", "hidden",
                           "-o", out, archive], capture_output=True,
                          timeout=600)


def sweep(unclassic, problems):
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
            r = us_extract(unclassic, archive, ours)
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


def generated(unclassic, problems):
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
                    us_extract(unclassic, arc, out)
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


def maclha(unclassic, problems):
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
            r = us_extract(unclassic, os.path.join(MACLHA, a), out)
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
    unclassic = os.path.join(ROOT, "build", "unclassic")
    args = sys.argv[1:]
    if "--unclassic" in args:
        unclassic = args[args.index("--unclassic") + 1]
    if not os.path.exists(unclassic):
        print("run_lzh: no CLI at %s" % unclassic)
        return 1
    if not os.path.isdir(ARCHIVES):
        print("run_lzh: SKIPPED — no reference/lhasa "
              "(tools/fetch_references.sh)")
        return 0
    if not build_lhasa():
        print("run_lzh: SKIPPED — reference/lhasa will not compile here")
        return 0

    problems = []
    ran, by_unar, by_lhasa = sweep(unclassic, problems)
    mac = maclha(unclassic, problems)
    gen = 0
    if build_lha():
        gen = generated(unclassic, problems)
    else:
        print("run_lzh: no reference/lha — the generated cases are skipped")

    for p in problems:
        print("run_lzh: FAIL: %s" % p)
    print("run_lzh: %d archive(s) checked (%d against unar, %d against "
          "lhasa), %d generated set(s), %d MacLHA specimen(s)"
          % (ran, by_unar, by_lhasa, gen, mac))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
