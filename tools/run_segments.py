#!/usr/bin/env python3
"""run_segments.py — differential tests for segmented (multi-part) archives.

Two schemes, generated into a temp directory and then extracted several
ways that have to agree byte for byte.

StuffIt segments (tools/synth_sitsplit.py), three ways:

  * what the generator wrote      (what the set is supposed to contain)
  * what `unar` extracts          (the oracle, XADStuffItSplitParser)
  * what our CLI extracts         (the thing under test)

The generator alone would be a closed loop — it is our own code stating
what our own code should produce — so the oracle is what makes a case
adjudicated. The generator is kept as a third opinion because it can
catch the case where we and unar are wrong in the same way.

Spanned zip (tools/synth_zipsplit.py), four ways, because the generator
is Info-ZIP rather than us and that buys an extra one:

  * the source tree that was zipped   (ground truth, ours only in the
    sense that we chose the bytes)
  * `unar` on the set                 (the oracle, XADZipParser)
  * our CLI on the set, from the LAST part and from the FIRST
  * our CLI on the same content zipped WITHOUT splitting — an opinion
    that owes nothing to any of the segment code, so a joiner that is
    subtly wrong disagrees with our own engine and not merely with unar

ORACLE TRAP, measured 2026-08-08: `unar Part.1` joins NOTHING and
extracts part 1 alone, exit status 0-ish, while `unar ./Part.1` and
`unar /abs/Part.1` join the whole set. The cause is in the reference
source: +volumesForHandle: takes [name stringByDeletingLastPathComponent],
which is @"" for a bare relative name, and the `if(!dirname) dirname=@"."`
guard does not fire for an empty string, so the volume scan reads the
wrong directory. Ground truth built that way is silently truncated.
Every oracle call here therefore passes an ABSOLUTE path.

Usage: run_segments.py [--unclassic build/dev/unclassic] [--case NAME]
"""
import argparse, os, re, shutil, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import synth_sitsplit as synth
import synth_zipsplit as zsynth
from make_manifests import parse_appledouble


def read_tree(d, appledouble=False):
    """{relative path: bytes} for every regular file under d.

    `unar` writes a resource fork as a real AppleDouble container while
    our CLI writes the raw fork bytes, so the oracle's "._X" sidecars
    are unwrapped here (parse_appledouble is make_manifests'; one home
    per finding). Zero-length files are dropped from both sides: the
    two extractors disagree about whether an EMPTY data fork is written
    at all — ours always writes one (cli/main.c sink_end), unar does
    not — and that is a file-creation policy, not bytes. Which means
    this comparison cannot see such a disagreement; the generator
    comparison, which encodes our policy, is what covers it.
    """
    out = {}
    for root, _dirs, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, d)
            if appledouble and f.startswith("._"):
                rsrc, _t, _c = parse_appledouble(p)
                blob = rsrc if rsrc is not None else open(p, "rb").read()
            else:
                blob = open(p, "rb").read()
            if blob:
                out[rel] = blob
    return out


def run(cmd, **kw):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          **kw)


def py_parts(d, name, fp):
    """{part number: path} for the files under d belonging to a set,
    decided in Python from the generator's own name and fingerprint.

    A second, independent implementation of the match rule: if the C
    matcher in src/fmt_sitseg.c grows too strict or too lax, the two
    disagree and the case fails. It is also what selects the files the
    oracle is allowed to see, so the oracle's input never depends on
    the binary under test.
    """
    found = {}
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if not os.path.isfile(p):
            continue
        with open(p, "rb") as fh:
            h = fh.read(synth.HEAD)
        if len(h) < synth.HEAD or h[:3] != synth.MAGIC:
            continue
        nl = h[4]
        if h[5:5 + nl] != name or h[68:94] != fp:
            continue
        found.setdefault(h[3], p)
    return found


def oracle_extract_renamed(parts, dest, workroot, tag):
    """Run the oracle on a copy of the set whose filenames follow the
    convention its volume scan requires.

    unar matches parts by content — but only among files whose name
    starts with the opened part's basename (XADStuffItSplitParser
    +volumesForHandle:, `[filename hasPrefix:basename]`). A set whose
    parts are not named alike is therefore invisible to it, however
    valid the headers are. Renaming keeps the BYTES identical and
    changes only what the oracle is able to find, so the payload stays
    adjudicated while our discovery is what the case tests.
    """
    stage = os.path.join(workroot, "_renamed-" + tag)
    os.makedirs(stage, exist_ok=True)
    for part, path in sorted(parts.items()):
        shutil.copyfile(path, os.path.join(stage, "Set.%03d" % part))
    return oracle_extract(os.path.join(stage, "Set.001"), dest)


def oracle_extract(part_path, dest):
    os.makedirs(dest, exist_ok=True)
    # Absolute path: see the ORACLE TRAP note above.
    # -nr: the parser marks the joined file as an archive when its name
    # ends in .sit/.sea, and unar would then extract THAT too. We stop at
    # the same layer (our CLI runs -nr here as well), so the two outputs
    # describe the same thing.
    r = run(["unar", "-q", "-nr", "-k", "hidden", "-o", dest,
             os.path.abspath(part_path)])
    return r.returncode, r.stdout.decode("utf-8", "replace")


def ours_extract(unclassic, part_path, dest, extra=()):
    os.makedirs(dest, exist_ok=True)
    r = run([unclassic, "x", "-nr", "--forks", "hidden", "-o", dest]
            + list(extra) + [part_path])
    return r.returncode, r.stdout.decode("utf-8", "replace")


class Failures(list):
    def check(self, cond, msg):
        if not cond:
            self.append(msg)
        return cond


def expected_tree(name, payload, rsrclen):
    """What the set is supposed to decode to, per the generator.

    Empty forks are omitted: read_tree drops zero-length files on both
    sides, so this is the same view.
    """
    t = {}
    rsrc, data = payload[:rsrclen], payload[rsrclen:]
    if rsrc:
        t["._" + name] = rsrc
    if data:
        t[name] = data
    return t


def case_run(unclassic, case, workroot, fails):
    d = os.path.join(workroot, case)
    os.makedirs(d)
    rawname, payload, rsrclen, datalen = synth.CASES[case](d)
    name = rawname.decode("ascii")
    fp = struct.pack(">4s4sHIIII", synth.TYPE, synth.CREATOR, synth.FFLAGS,
                     synth.CREATED, synth.MODIFIED, rsrclen, datalen)

    parts = py_parts(d, rawname, fp)
    if not fails.check(1 in parts, "%s: no part 1 was generated" % case):
        return
    first = parts[1]
    want = expected_tree(name, payload, rsrclen)

    # `misnamed` deliberately breaks the naming the oracle's volume scan
    # needs, so it is adjudicated on a renamed copy of the same bytes.
    if case == "misnamed":
        rc, out = oracle_extract_renamed(parts, os.path.join(d, "_oracle"),
                                         workroot, case)
    else:
        rc, out = oracle_extract(first, os.path.join(d, "_oracle"))
    fails.check(rc == 0, "%s: oracle failed: %s" % (case, out.strip()))
    got_oracle = read_tree(os.path.join(d, "_oracle"), appledouble=True)

    rc, out = ours_extract(unclassic, first, os.path.join(d, "_ours"))
    fails.check(rc == 0, "%s: unclassic failed: %s" % (case, out.strip()))
    got_ours = read_tree(os.path.join(d, "_ours"))

    fails.check(got_oracle == want,
                "%s: oracle disagrees with the generator: %s vs %s"
                % (case, sorted(got_oracle), sorted(want)))
    fails.check(got_ours == want,
                "%s: ours disagrees with the generator: %s vs %s"
                % (case, sorted(got_ours), sorted(want)))
    fails.check(got_ours == got_oracle, "%s: ours disagrees with the oracle" % case)
    return d, first, name, want


# --- spanned zip ---------------------------------------------------------


def zip_stats(unclassic, part_path, dest):
    """Extract with --stats and return (rc, output, the segments line)."""
    os.makedirs(dest, exist_ok=True)
    r = run([unclassic, "x", "-nr", "--stats", "-o", dest,
             os.path.abspath(part_path)])
    out = r.stdout.decode("utf-8", "replace")
    line = "".join(l for l in out.splitlines() if l.startswith("segments:"))
    return r.returncode, out, line


def zip_floor(parts):
    """Fewest part opens (and backward crossings) the set can be read in,
    derived from the archive's OWN central directory.

    Computed here in Python rather than taken from the engine, for the
    same reason py_parts() re-implements the StuffIt match rule: a floor
    the engine calculates is a floor the engine cannot fail to meet.

    The model is what the format allows: open the last part for the
    end-of-central-directory record, read the directory from wherever
    that record says it starts, then visit each entry in the order the
    directory lists them, opening the part it starts on and rolling
    forward while its data spills into the next.

    The directory's own placement is part of the model and was left out
    of the first version of it, which then accused the engine of two
    extra opens on `zmany` — where the directory genuinely begins on
    part 11 and crosses into part 12. A floor that is too low is not a
    safe error: it reads as a defect in the thing being measured.
    """
    sizes = [os.path.getsize(p) for p in parts]
    data = b"".join(open(p, "rb").read() for p in parts)
    e = data.rfind(b"PK\x05\x06")
    if e < 0:
        return None
    cddisk, _nd, nent, cdsize, cdoff = struct.unpack_from("<HHHII", data, e + 6)
    base = lambda k: sum(sizes[:k])

    def part_of(logical):
        k = 0
        while k + 1 < len(sizes) and base(k + 1) <= logical:
            k += 1
        return k

    state = {"cur": len(parts) - 1, "opens": 1, "back": 0}

    def visit(first, last):
        for k in range(first, last + 1):
            if k != state["cur"]:
                if k < state["cur"]:
                    state["back"] += 1
                state["cur"] = k
                state["opens"] += 1

    # the directory, which need not start on the last part
    cdstart = base(cddisk) + cdoff
    visit(cddisk, part_of(cdstart + cdsize - 1))

    p = cdstart
    ents = []
    for _ in range(nent):
        if data[p:p + 4] != b"PK\x01\x02":
            return None
        csize = struct.unpack_from("<I", data, p + 20)[0]
        nl, el, cl, sd = struct.unpack_from("<HHHH", data, p + 28)
        lho = struct.unpack_from("<I", data, p + 42)[0]
        ents.append((sd, lho, csize))
        p += 46 + nl + el + cl

    for sd, lho, csize in ents:
        # 30 = the local header, whose name and extra add more; using the
        # minimum keeps the floor a floor.
        visit(sd, part_of(base(sd) + lho + 30 + csize))
    return state["opens"], state["back"]


def zip_case_run(unclassic, case, workroot, fails):
    d = os.path.join(workroot, case)
    os.makedirs(d)
    src, parts, whole = zsynth.CASES[case](d)

    # The archives were built by zipping the directory, so every stored
    # path carries its name; the tree read off disk does not.
    stem = os.path.basename(src)
    want = dict(("%s/%s" % (stem, k), v) for k, v in read_tree(src).items())
    if not fails.check(bool(parts), "%s: no parts were generated" % case):
        return
    last, first = parts[-1], parts[0]

    # The oracle. Absolute path: see the ORACLE TRAP note above, which
    # is a property of XADMaster's volume scan and so applies here too.
    rc, out = oracle_extract(last, os.path.join(d, "_oracle"))
    fails.check(rc == 0, "%s: oracle failed: %s" % (case, out.strip()))
    got_oracle = read_tree(os.path.join(d, "_oracle"))

    # Ours, from the last part and from the first. A user has whichever
    # one they double-clicked, so both have to reach the same set.
    rc, out = ours_extract(unclassic, os.path.abspath(last),
                           os.path.join(d, "_last"))
    fails.check(rc == 0, "%s: unclassic failed on the last part: %s"
                % (case, out.strip()))
    got_last = read_tree(os.path.join(d, "_last"))

    rc, out = ours_extract(unclassic, os.path.abspath(first),
                           os.path.join(d, "_first"))
    fails.check(rc == 0, "%s: unclassic failed on the first part: %s"
                % (case, out.strip()))
    got_first = read_tree(os.path.join(d, "_first"))

    # The same content, not split: no joiner, no address translation.
    rc, out = ours_extract(unclassic, whole, os.path.join(d, "_whole"))
    fails.check(rc == 0, "%s: unclassic failed on the unsplit archive: %s"
                % (case, out.strip()))
    got_whole = read_tree(os.path.join(d, "_whole"))

    fails.check(got_oracle == want,
                "%s: oracle disagrees with the source tree: %s vs %s"
                % (case, sorted(got_oracle), sorted(want)))
    fails.check(got_whole == want,
                "%s: our unsplit read disagrees with the source tree"
                % case)
    fails.check(got_last == want, "%s: ours (from the last part) disagrees "
                "with the source tree: %s vs %s"
                % (case, sorted(got_last), sorted(want)))
    fails.check(got_first == got_last,
                "%s: opening the first part gave different bytes" % case)
    return d, src, parts, whole, want


def zip_behaviours(unclassic, case, d, parts, whole, want, workroot, fails):
    """The parts of the scheme that byte-exactness cannot see."""
    last, first = parts[-1], parts[0]
    multi = len(parts) > 1

    # What the join costs in part opens, which on removable media is what
    # a disk swap costs. Required to MATCH the floor the archive's own
    # directory allows, not merely to be reported: this number was 3-4x
    # the floor for a day, written up as the format's doing, because
    # nothing compared it against anything (DECISIONS.md 2026-08-09).
    if multi:
        rc, out, line = zip_stats(unclassic, last, os.path.join(d, "_stats"))
        floor = zip_floor(parts)
        if fails.check(bool(line) and floor is not None,
                       "%s: no segment line or no floor" % case):
            got = tuple(int(x) for x in re.findall(r"\d+", line))
            print("  %-9s %s  (floor: %d part opens, %d backward)"
                  % (case + ":", line, floor[0], floor[1]))
            fails.check(got == floor,
                        "%s: %d opens / %d backward, floor is %d / %d"
                        % ((case,) + got + floor))

    if not multi:
        # `zip -s` that did not split: an ordinary archive with a marker
        # in front of it. It must extract with the part machinery
        # explicitly turned OFF, because nothing is missing.
        rc, out = ours_extract(unclassic, os.path.abspath(last),
                               os.path.join(d, "_np"), extra=["--no-parts"])
        fails.check(rc == 0, "%s: --no-parts refused a one-file archive: %s"
                    % (case, out.strip()))
        fails.check(read_tree(os.path.join(d, "_np")) == want,
                    "%s: --no-parts gave different bytes" % case)
        r = run([unclassic, "sniff", os.path.abspath(last)])
        fails.check(r.stdout.decode().strip() == "Zip",
                    "%s: a set of one sniffed as %r"
                    % (case, r.stdout.decode().strip()))
        return

    # The directory is buffered when it fits and read a record at a time
    # when it does not, and the second path is reachable only under a
    # budget too small to hold it. Squeeze it there and require the SAME
    # BYTES out, at a visibly worse cost in part opens — which is what
    # the buffering buys and the only place the difference shows.
    #
    # Only on the cases that STORE. The budget is aimed one byte under
    # the run's own high-water mark, which lands on the directory buffer
    # exactly when nothing else is competing for the heap; a deflated
    # entry allocates a window on top and the same budget would starve
    # the decoder instead, testing something else entirely.
    if case in zsynth.STORED:
        peak = re.search(r"high-water (\d+)", out)
        if fails.check(peak is not None, "%s: --stats printed no peak" % case):
            lean = os.path.join(d, "_lean")
            os.makedirs(lean, exist_ok=True)
            r = run([unclassic, "x", "-nr", "--budget",
                     str(int(peak.group(1)) - 1), "--stats", "--forks",
                     "hidden", "-o", lean, os.path.abspath(last)])
            lout = r.stdout.decode("utf-8", "replace")
            fails.check(r.returncode == 0,
                        "%s: refused to extract without room for the "
                        "directory: %s" % (case, lout.strip()))
            fails.check(read_tree(lean) == want,
                        "%s: the un-buffered directory walk gave different "
                        "bytes" % case)
            fails.check("1 refused" in lout,
                        "%s: nothing was refused, so the fallback was never "
                        "taken and this case proved nothing" % case)
            lean_line = "".join(l for l in lout.splitlines()
                                if l.startswith("segments:"))
            lean_opens = tuple(int(x) for x in re.findall(r"\d+", lean_line))
            fails.check(lean_opens > floor,
                        "%s: the un-buffered walk cost %s, no more than the "
                        "buffered one — buffering the directory is doing "
                        "nothing" % (case, lean_opens))

    # A middle part identifies itself as nothing, and the oracle refuses
    # one too (MEASURED). Ours must refuse rather than guess.
    if len(parts) > 2:
        mid = parts[1]
        r = run(["unar", "-q", "-o", os.path.join(d, "_omid"),
                 os.path.abspath(mid)])
        fails.check(r.returncode != 0,
                    "%s: the oracle accepted a middle part; the premise "
                    "that it cannot be identified is wrong" % case)
        rc, out = ours_extract(unclassic, os.path.abspath(mid),
                               os.path.join(d, "_mid"))
        fails.check(rc != 0, "%s: a middle part must not extract" % case)

    # --no-parts must refuse, not extract a truncated archive.
    rc, out = ours_extract(unclassic, os.path.abspath(last),
                           os.path.join(d, "_np"), extra=["--no-parts"])
    fails.check(rc != 0, "%s: --no-parts must not extract a spanned set" % case)
    fails.check("segment" in out.lower(),
                "%s: --no-parts reported %r" % (case, out.strip()))

    # A missing part: named as a segment problem, not as a broken zip.
    hidden = os.path.join(workroot, "hidden-" + case)
    shutil.move(first, hidden)
    rc, out = ours_extract(unclassic, os.path.abspath(last),
                           os.path.join(d, "_gap"))
    fails.check(rc != 0, "%s: a missing part must fail" % case)
    fails.check("segment" in out.lower(),
                "%s: missing part reported as %r" % (case, out.strip()))

    # --ask puts it back, over the same engine callback the Mac dialog
    # uses. This is the only way a part outside the folder is reachable.
    r = subprocess.run([unclassic, "x", "-nr", "--ask", "-o",
                        os.path.join(d, "_ask"), os.path.abspath(last)],
                       input=(hidden + "\n").encode(),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    fails.check(r.returncode == 0, "%s: --ask failed: %s"
                % (case, r.stdout.decode("utf-8", "replace").strip()))
    fails.check(read_tree(os.path.join(d, "_ask")) == want,
                "%s: --ask produced different bytes" % case)
    shutil.move(hidden, first)

    # --- the check that carries this whole scheme ---------------------
    # The parts were placed by their filenames, which prove nothing. So
    # swap two of them and require the extraction to FAIL. If it can
    # succeed here, then filenames are the only thing standing between a
    # user and silently wrong output.
    if len(parts) > 2:
        a, b = parts[0], parts[1]
        ba, bb = open(a, "rb").read(), open(b, "rb").read()
        open(a, "wb").write(bb)
        open(b, "wb").write(ba)
        rc, out = ours_extract(unclassic, os.path.abspath(last),
                               os.path.join(d, "_swapped"))
        fails.check(rc != 0,
                    "%s: parts in the wrong order extracted cleanly" % case)
        open(a, "wb").write(ba)
        open(b, "wb").write(bb)

        # And a part replaced by something entirely foreign.
        foreign = os.urandom(os.path.getsize(a))
        open(a, "wb").write(foreign)
        rc, out = ours_extract(unclassic, os.path.abspath(last),
                               os.path.join(d, "_foreign"))
        fails.check(rc != 0, "%s: a foreign part extracted cleanly" % case)
        open(a, "wb").write(ba)

    # Back to health, so a mutation that leaked would be caught here.
    rc, out = ours_extract(unclassic, os.path.abspath(last),
                           os.path.join(d, "_again"))
    fails.check(rc == 0 and read_tree(os.path.join(d, "_again")) == want,
                "%s: the set did not survive the mutation tests" % case)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--unclassic", default="build/dev/unclassic")
    ap.add_argument("--case", action="append")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    unclassic = os.path.abspath(a.unclassic)
    if not os.path.exists(unclassic):
        print("run_segments: no such binary: %s" % unclassic)
        return 2
    if shutil.which("unar") is None:
        print("run_segments: unar not found; skipping (oracle unavailable)")
        return 0

    selected = a.case
    cases = [c for c in (selected or sorted(synth.CASES)) if c in synth.CASES]
    zipcases = [c for c in (selected or sorted(zsynth.CASES))
                if c in zsynth.CASES]
    if zipcases and not zsynth.available():
        print("run_segments: `zip` not found; skipping the spanned-zip cases")
        zipcases = []

    fails = Failures()
    workroot = tempfile.mkdtemp(prefix="unc-seg-")
    try:
        results = {}
        for c in cases:
            r = case_run(unclassic, c, workroot, fails)
            if r:
                results[c] = r

        # --- behaviours beyond byte-exactness ---------------------------
        if "basic3" in results:
            d, first, name, want = results["basic3"]

            # Opening a part other than the first still extracts the set:
            # the part number comes from the header, so discovery walks
            # back to part 1 on its own.
            third = os.path.join(d, "Test.sit.3")
            rc, out = ours_extract(unclassic, third, os.path.join(d, "_from3"))
            fails.check(rc == 0, "basic3: opening part 3 failed: %s" % out.strip())
            fails.check(read_tree(os.path.join(d, "_from3")) == want,
                        "basic3: opening part 3 gave different bytes")

            # A missing part is an error, and names the format's problem
            # rather than dying as a generic I/O failure.
            hidden = os.path.join(workroot, "hidden-part2")
            shutil.move(os.path.join(d, "Test.sit.2"), hidden)
            rc, out = ours_extract(unclassic, first, os.path.join(d, "_gap"))
            fails.check(rc != 0, "basic3: a missing part must fail")
            fails.check("segment" in out.lower(),
                        "basic3: missing part reported as %r" % out.strip())

            # --ask: the CLI stand-in for the Mac dialog. Same engine
            # callback, driven from stdin.
            r = subprocess.run([unclassic, "x", "-nr", "--forks", "hidden",
                                "--ask", "-o", os.path.join(d, "_ask"), first],
                               input=(hidden + "\n").encode(),
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
            fails.check(r.returncode == 0, "basic3: --ask failed: %s"
                        % r.stdout.decode("utf-8", "replace").strip())
            fails.check(read_tree(os.path.join(d, "_ask")) == want,
                        "basic3: --ask produced different bytes")

            # A wrong file offered to --ask is refused by fingerprint,
            # not accepted because it is next in line.
            solo = os.path.join(workroot, "single", "Solo.sit.1")
            if os.path.exists(solo):
                r = subprocess.run([unclassic, "x", "-nr", "--ask", "-o",
                                    os.path.join(d, "_askbad"), first],
                                   input=(solo + "\n\n").encode(),
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
                out = r.stdout.decode("utf-8", "replace")
                fails.check(r.returncode != 0,
                            "basic3: --ask accepted a foreign file")
                fails.check("not part of" in out,
                            "basic3: foreign file rejected as %r" % out.strip())
            shutil.move(hidden, os.path.join(d, "Test.sit.2"))

            # --part, and how many times the joiner moved between parts.
            r = run([unclassic, "x", "-nr", "--forks", "hidden", "--stats",
                     "-o", os.path.join(d, "_stats"), first])
            out = r.stdout.decode("utf-8", "replace")
            line = [l for l in out.splitlines() if l.startswith("segments:")]
            fails.check(bool(line), "basic3: --stats printed no segment line")
            if line:
                print("  " + line[0])
                fails.check("0 of them backward" in line[0],
                            "basic3: the join seeks backwards: %s" % line[0])

        if "single" in results:
            d, first, name, want = results["single"]
            # One part is a whole set: no volume source needed, so even
            # --no-parts extracts it.
            rc, out = ours_extract(unclassic, first, os.path.join(d, "_np"),
                                   extra=["--no-parts"])
            fails.check(rc == 0, "single: --no-parts failed: %s" % out.strip())
            fails.check(read_tree(os.path.join(d, "_np")) == want,
                        "single: --no-parts gave different bytes")

        if "basic3" in results:
            d, first, _n, _w = results["basic3"]
            # ...while a multi-part set under --no-parts must refuse
            # rather than extract a truncated file.
            rc, out = ours_extract(unclassic, first, os.path.join(d, "_np"),
                                   extra=["--no-parts"])
            fails.check(rc != 0, "basic3: --no-parts must not extract")
            fails.check("segment" in out.lower(),
                        "basic3: --no-parts reported %r" % out.strip())

        if "misnamed" in results:
            d, first, name, want = results["misnamed"]
            # The intruder shares the set's name and differs in the
            # fingerprint; picking it up would corrupt the output.
            fails.check(read_tree(os.path.join(d, "_ours")) == want,
                        "misnamed: a name-alike part was used")

        if "many12" in results:
            d, first, _n, _w = results["many12"]
            r = run([unclassic, "x", "-nr", "--stats", "-o",
                     os.path.join(d, "_stats"), first])
            out = r.stdout.decode("utf-8", "replace")
            line = [l for l in out.splitlines() if l.startswith("segments:")]
            if line:
                print("  many12: " + line[0])
                fails.check("12 part opens" in line[0],
                            "many12: unexpected part opens: %s" % line[0])

        # --- spanned zip ------------------------------------------------
        for c in zipcases:
            r = zip_case_run(unclassic, c, workroot, fails)
            if r:
                d, _src, parts, whole, want = r
                zip_behaviours(unclassic, c, d, parts, whole, want,
                               workroot, fails)
    finally:
        if a.keep:
            print("kept: %s" % workroot)
        else:
            shutil.rmtree(workroot, ignore_errors=True)

    for f in fails:
        print("FAIL " + f)
    print("segments: %d StuffIt + %d spanned-zip cases, %d failures"
          % (len(cases), len(zipcases), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
