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

Plain NAME.001 splits (tools/synth_split.py) are adjudicated by what
they were cut from, since nothing in the parts says anything:

  * the original file, byte for byte  (we did the cutting, so this is
    exact ground truth rather than an opinion)
  * `unar`, on the payloads it can join at all — a plain data file, but
    not an archive, whose first part its content parsers claim first.
    That asymmetry is the reason our discovery decides by NAME, so it
    is re-measured here on every run instead of quoted from a document
  * our own extraction of the unsplit archive, for the archive payload

and by what they CANNOT catch, which is asserted just as hard: see
split_behaviours().

Parts inside envelopes (tools/synth_wrapped.py) are the shape a real
download has — Archive.sit.1.hqx, Archive.sit.2.hqx — and are the same
StuffIt sets with a BinHex or MacBinary layer around each part. The
oracle contributes what it DOES rather than ground truth: it unwraps
the one part it was given and exits 0. See wrapped_case_run().

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
import argparse, glob, json, os, re, shutil, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIXDIR = os.path.join(os.path.dirname(HERE), "fixtures")
sys.path.insert(0, HERE)
import synth_sitsplit as synth
import synth_zipsplit as zsynth
import synth_split as ssynth
import synth_wrapped as wsynth
import synth_cptsplit as csynth
import synth_ddsplit as dsynth
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
    # nothing compared it against anything (DECISIONS.md 2026-08-10).
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


# --- plain NAME.001 splits -----------------------------------------------


def joined_file(dest, whole):
    """The one entry a split yields: the parts' name minus ".NNN"."""
    p = os.path.join(dest, os.path.basename(whole))
    return open(p, "rb").read() if os.path.exists(p) else None


def ours_join(unclassic, part_path, dest, extra=()):
    """Extract with -nr, which stops at the joined file itself."""
    return ours_extract(unclassic, os.path.abspath(part_path), dest, extra)


def run_full(unclassic, path, dest):
    """Extract WITHOUT -nr: a joined archive is unwrapped in place, the
    way a user gets it."""
    os.makedirs(dest, exist_ok=True)
    r = run([unclassic, "x", "--forks", "hidden", "-o", dest,
             os.path.abspath(path)])
    return r.returncode, r.stdout.decode("utf-8", "replace")


def split_case_run(unclassic, case, workroot, fails):
    d = os.path.join(workroot, case)
    os.makedirs(d)
    kind, whole, parts, src = ssynth.CASES[case](d)
    original = open(whole, "rb").read()
    if not fails.check(len(parts) > 1, "%s: no parts were generated" % case):
        return

    # Ours, from part 1. The comparison is against the bytes that were
    # cut up, so this case needs no oracle to be adjudicated at all.
    rc, out = ours_join(unclassic, parts[0], os.path.join(d, "_ours"))
    fails.check(rc == 0, "%s: unclassic failed: %s" % (case, out.strip()))
    fails.check(joined_file(os.path.join(d, "_ours"), whole) == original,
                "%s: the join is not the file that was cut up" % case)

    # The oracle, and which half of it applies is the whole point.
    rc, out = oracle_extract(parts[0], os.path.join(d, "_oracle"))
    got = joined_file(os.path.join(d, "_oracle"), whole)
    if kind == "blob":
        fails.check(rc == 0, "%s: oracle failed: %s" % (case, out.strip()))
        fails.check(got == original,
                    "%s: the oracle's join disagrees with the original"
                    % case)
    else:
        # MEASURED, not assumed: XADSplitFileParser is tried after the
        # content parsers, so part 1 of a split archive is read as the
        # truncated archive it is a slice of. If this ever starts
        # passing, deciding by name before the sniff is no longer a
        # capability the reference lacks and the CLI's rule wants
        # revisiting (cli/main.c, UNC_FORMAT_SPLIT).
        fails.check(got != original,
                    "%s: the oracle joined an archive-payload split after "
                    "all; the premise for deciding by name is wrong" % case)

    # An archive payload can be checked all the way through, against an
    # opinion that owes nothing to the joiner: our own unsplit read.
    if src is not None:
        rc, out = run_full(unclassic, parts[0], os.path.join(d, "_full"))
        fails.check(rc == 0, "%s: joined archive did not extract: %s"
                    % (case, out.strip()))
        rc, out = run_full(unclassic, whole, os.path.join(d, "_unsplit"))
        fails.check(rc == 0, "%s: unsplit archive did not extract: %s"
                    % (case, out.strip()))
        stem = os.path.basename(src)
        want = dict(("%s/%s" % (stem, k), v) for k, v in read_tree(src).items())
        got_full = read_tree(os.path.join(d, "_full"))
        # The joined archive is left behind by the unwrap only if it
        # failed; where it succeeded the layer is removed, so the trees
        # compare directly.
        fails.check(got_full == want,
                    "%s: the joined archive extracted to something else: "
                    "%s vs %s" % (case, sorted(got_full), sorted(want)))
        fails.check(got_full == read_tree(os.path.join(d, "_unsplit")),
                    "%s: joined and unsplit reads disagree" % case)
    return d, kind, whole, parts, original


def split_behaviours(unclassic, case, d, kind, whole, parts, original,
                     workroot, fails):
    """What byte-exactness cannot see — including, deliberately, the two
    things this scheme cannot promise."""
    n = len(parts)

    # Any part reaches the same set: the numbering is a total order and
    # the run is walked from .001 whichever member was opened.
    for i in (1, n - 1):
        dest = os.path.join(d, "_from%d" % (i + 1))
        rc, out = ours_join(unclassic, parts[i], dest)
        fails.check(rc == 0 and joined_file(dest, whole) == original,
                    "%s: opening part %d gave a different join" % (case, i + 1))

    # A flat join is read strictly forward, so the floor is one open per
    # part and no backward crossing. Unlike a spanned zip there is no
    # directory at the end to reach first.
    r = run([unclassic, "x", "-nr", "--stats", "-o", os.path.join(d, "_stats"),
             os.path.abspath(parts[0])])
    out = r.stdout.decode("utf-8", "replace")
    line = "".join(l for l in out.splitlines() if l.startswith("segments:"))
    if fails.check(bool(line), "%s: --stats printed no segment line" % case):
        got = tuple(int(x) for x in re.findall(r"\d+", line))
        print("  %-7s %s  (floor: %d part opens, 0 backward)"
              % (case + ":", line, n))
        fails.check(got == (n, 0), "%s: %d opens / %d backward, floor is "
                    "%d / 0" % ((case,) + got + (n,)))

    # --no-parts hands the file back to the sniff, which sees one slice.
    rc, out = ours_join(unclassic, parts[0], os.path.join(d, "_np"),
                        extra=["--no-parts"])
    fails.check(joined_file(os.path.join(d, "_np"), whole) is None,
                "%s: --no-parts produced the joined file" % case)

    # A member numbered past the end of the run says a part is missing.
    # The reference appends it instead (MEASURED here, both halves).
    #
    # Numbered n+2, deliberately inside the 256-part ceiling: at .900
    # this "passed" against the ceiling check instead, which is a
    # different branch and would have gone on passing with the run
    # rule removed entirely.
    stray = "%s.%03d" % (whole, n + 2)
    open(stray, "wb").write(b"JUNKJUNK")
    rc, out = ours_join(unclassic, parts[0], os.path.join(d, "_stray"))
    fails.check(rc != 0, "%s: a stray numbered member was joined" % case)
    fails.check("part %d" % (n + 1) in out,
                "%s: stray member reported as %r" % (case, out.strip()))
    if kind == "blob":
        rc, oout = oracle_extract(parts[0], os.path.join(d, "_ostray"))
        fails.check(joined_file(os.path.join(d, "_ostray"), whole)
                    == original + b"JUNKJUNK",
                    "%s: the oracle did not append the stray member; the "
                    "departure this rule exists for is gone" % case)
    os.remove(stray)

    # ...and one past the ceiling, which is its own branch and its own
    # message: three digits reach 999 and the joiner stops at 256.
    stray = "%s.900" % whole
    open(stray, "wb").write(b"JUNKJUNK")
    rc, out = ours_join(unclassic, parts[0], os.path.join(d, "_over"))
    fails.check(rc != 0 and "256" in out,
                "%s: a member numbered 900 reported as %r" % (case, out.strip()))
    os.remove(stray)

    # A gap with something beyond it: refused, and named.
    hidden = os.path.join(workroot, "hidden-%s" % case)
    shutil.move(parts[1], hidden)
    rc, out = ours_join(unclassic, parts[0], os.path.join(d, "_gap"))
    fails.check(rc != 0, "%s: a missing middle part must fail" % case)
    fails.check("part 2" in out, "%s: missing part reported as %r"
                % (case, out.strip()))

    # --ask puts it back, over the engine callback the Mac dialog uses.
    dest = os.path.join(d, "_ask")
    os.makedirs(dest, exist_ok=True)
    r = subprocess.run([unclassic, "x", "-nr", "--ask", "-o", dest,
                        os.path.abspath(parts[0])],
                       input=(hidden + "\n").encode(),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    fails.check(r.returncode == 0, "%s: --ask failed: %s"
                % (case, r.stdout.decode("utf-8", "replace").strip()))
    fails.check(joined_file(dest, whole) == original,
                "%s: --ask produced a different join" % case)
    shutil.move(hidden, parts[1])

    # --- the two things this scheme cannot promise --------------------
    # Both are asserted rather than written down, so that "a wrong part
    # cannot pass silently" is never quietly assumed of this scheme the
    # way it is true of a spanned zip.

    # 1. A missing TAIL. No part count exists anywhere, so a set that
    #    stops early looks exactly like a complete one — unless what it
    #    joins into notices, which only an archive does.
    tail = os.path.join(workroot, "tail-%s" % case)
    shutil.move(parts[-1], tail)
    dest = os.path.join(d, "_tail")
    rc, out = ours_join(unclassic, parts[0], dest)
    if kind == "blob":
        got = joined_file(dest, whole)
        fails.check(rc == 0 and got is not None and len(got) < len(original)
                    and got == original[:len(got)],
                    "%s: a set missing its tail did not join into a short "
                    "prefix — nothing in this scheme can detect that, so "
                    "find out what did before believing it" % case)
    else:
        rc2, out2 = run_full(unclassic, parts[0], os.path.join(d, "_tailfull"))
        fails.check(rc2 != 0,
                    "%s: an archive missing its tail extracted cleanly" % case)
    shutil.move(tail, parts[-1])

    # 2. Parts in the wrong ORDER — a user's floppies labelled wrongly,
    #    which here means two parts' CONTENTS swapped. What catches it
    #    is entirely the payload's doing, and the two swaps below are
    #    the two halves of that:
    def swap(i, j):
        pi, pj = parts[i], parts[j]
        bi, bj = open(pi, "rb").read(), open(pj, "rb").read()
        open(pi, "wb").write(bj)
        open(pj, "wb").write(bi)
        return lambda: (open(pi, "wb").write(bi), open(pj, "wb").write(bj))

    #    (a) a swap that leaves part 1 alone. The joined file still
    #        LOOKS like its format, so the reader runs and its own
    #        offsets and checksums throw it out.
    if kind != "blob" and n > 3:
        undo = swap(1, 2)
        rc2, out2 = run_full(unclassic, parts[0], os.path.join(d, "_swapmid"))
        fails.check(rc2 != 0, "%s: parts 2 and 3 swapped extracted cleanly; "
                    "the payload is what adjudicates a split and it did not"
                    % case)
        undo()

    #    (b) a swap involving part 1, which is where the payload's own
    #        header lived. The join no longer sniffs as anything, so it
    #        is emitted as the plain file this scheme is entitled to
    #        produce and NOTHING objects. Asserted so that the limit is
    #        re-measured rather than remembered: a wrong part cannot
    #        pass silently only while what it joins into can still be
    #        recognized (DECISIONS.md 2026-08-10).
    undo = swap(0, 1)
    dest = os.path.join(d, "_swapped")
    rc, out = ours_join(unclassic, parts[0], dest)
    fails.check(rc == 0 and joined_file(dest, whole) != original,
                "%s: a swap across part 1 was caught; nothing in this "
                "scheme can do that, so find out what did before "
                "believing it" % case)
    undo()

    # Back to health, so a mutation that leaked would be caught here.
    dest = os.path.join(d, "_again")
    rc, out = ours_join(unclassic, parts[0], dest)
    fails.check(rc == 0 and joined_file(dest, whole) == original,
                "%s: the set did not survive the mutation tests" % case)


# --- Compact Pro segments -------------------------------------------------


CPT_CASES = {
    "cpt4": ("derived-Education7.1.cpt", 24576,
             "folders, and entries either side of a cut"),
    "cpt5": ("derived-BiPlane__2_Share.cpt", 24576,
             "ONE entry, whose data crosses every boundary"),
}

SPECIMENS = os.path.join(
    os.environ.get("UNC_VMAC_HOME",
                   os.path.expanduser("~/.cache/unclassic/vmac")), "specimens")


def cpt_parts(d):
    return sorted(glob.glob(os.path.join(d, "*.cpt.#*")),
                  key=lambda p: int(p.rsplit("#", 1)[1]))


def cpt_floor(fixture_path, seg_size):
    """The fewest segment opens the format allows, derived in Python from
    the archive's OWN directory rather than asked of the engine.

    The index is in the last segment, so that one is opened first; then
    the entries are visited in directory order, each starting in the
    segment its (volume, offset) names and rolling forward while its
    data spills into the next. Same reasoning as zip_floor(), and for
    the same reason: a floor the engine calculates is a floor the engine
    cannot fail to meet.
    """
    src = open(fixture_path, "rb").read()
    idx, ents, _end = csynth.parse_index(src)
    body = seg_size - csynth.HDR
    payload = len(src) - csynth.HDR
    nseg = max(1, (payload + body - 1) // body)
    def vol_of(flat):
        return min(nseg, flat // body + 1)
    seq = [nseg]
    for kind, _name, _vol, off, at in ents:
        if kind != "f":
            continue
        # rsrc+data run consecutively from the entry's offset
        j = ents.index((kind, _name, _vol, off, at))
        start = off - csynth.HDR
        span = 0
        # lengths live in the 45-byte record; re-read them here
        nl = src[at]
        q = at + 1 + (nl & 0x7f) + 1
        rcl, dcl = struct.unpack(">II", src[q + 36:q + 44])
        span = rcl + dcl
        if span == 0:
            continue
        first, last = vol_of(start), vol_of(start + span - 1)
        seq.extend(range(first, last + 1))
    opens = 1
    back = 0
    for a, b in zip(seq, seq[1:]):
        if b != a:
            opens += 1
            if b < a:
                back += 1
    return opens, back


def cpt_case_run(unclassic, case, workroot, fails):
    """A segmented Compact Pro set, cut in Python the way the application
    cuts one.

    Adjudicated against the archive it was cut FROM — which the
    differential suite already grades against `unar` and `macunpack` —
    so nothing here rests on the segment code being right. The oracle
    appears for what it CANNOT do, which is the reason this scheme
    needed generating in the first place: handed the final segment,
    `unar` calls it a whole Compact Pro archive, reads every entry at an
    offset belonging to another volume, and exits 0 having written
    garbage (MEASURED 2026-08-14).
    """
    fixture, seg_size, _why = CPT_CASES[case]
    src = os.path.join(FIXDIR, fixture)
    if not os.path.exists(src):
        print(f"run_segments: SKIP {case} ({fixture} absent)")
        return None
    d = os.path.join(workroot, case)
    os.makedirs(d)
    setdir = os.path.join(d, "set")
    csynth.write_set(src, setdir, seg_size, base="Source.cpt")
    parts = cpt_parts(setdir)
    if not fails.check(len(parts) > 1, "%s: nothing was segmented" % case):
        return None

    # What the archive holds, by a path with no joiner in it.
    rc, out = run_full(unclassic, src, os.path.join(d, "_whole"))
    fails.check(rc == 0, "%s: the unsegmented archive failed: %s"
                % (case, out.strip()))
    want = read_tree(os.path.join(d, "_whole"))

    rc, out = run_full(unclassic, parts[-1], os.path.join(d, "_ours"))
    fails.check(rc == 0, "%s: the segmented set failed: %s" % (case, out.strip()))
    got = read_tree(os.path.join(d, "_ours"))
    fails.check(got == want,
                "%s: the set does not hold what the archive did: %s vs %s"
                % (case, sorted(got), sorted(want)))

    # The oracle, for what it does. If this ever starts agreeing, unar
    # has learned the scheme and OPEN_ITEMS.md wants revisiting.
    rc, out = oracle_extract(parts[-1], os.path.join(d, "_oracle"))
    got_oracle = read_tree(os.path.join(d, "_oracle"), appledouble=True)
    fails.check(got_oracle != want,
                "%s: the oracle read a segmented set correctly after all"
                % case)
    return d, setdir, parts, want


def cpt_behaviours(unclassic, case, d, setdir, parts, want, workroot, fails):
    fixture, seg_size, _why = CPT_CASES[case]

    # ANY segment reaches the set. The application itself requires the
    # final one ("you must open the FINAL segment"); every part carries
    # the set's identity, so there is no reason a reader should.
    for i in (0, len(parts) // 2):
        dest = os.path.join(d, "_from%d" % (i + 1))
        rc, out = run_full(unclassic, parts[i], dest)
        fails.check(rc == 0 and read_tree(dest) == want,
                    "%s: opening segment %d gave a different result: %s"
                    % (case, i + 1, out.strip()))

    # A segment of ANOTHER set, named exactly like the missing one. The
    # identity is two bytes, so this is the check that has to hold.
    other = os.path.join(d, "_other")
    os.makedirs(other, exist_ok=True)
    alt = os.path.join(FIXDIR, CPT_CASES["cpt5" if case == "cpt4" else "cpt4"][0])
    if os.path.exists(alt):
        csynth.write_set(alt, other, seg_size, base="Other.cpt")
        decoy = os.path.join(d, "_decoy")
        shutil.copytree(setdir, decoy)
        victim = os.path.basename(parts[1])
        os.remove(os.path.join(decoy, victim))
        shutil.copyfile(cpt_parts(other)[1], os.path.join(decoy, victim))
        rc, out = run_full(unclassic, os.path.join(decoy, os.path.basename(parts[-1])),
                           os.path.join(d, "_decoyout"))
        fails.check(rc != 0, "%s: a segment of another set was accepted" % case)
        fails.check("segment" in out.lower(),
                    "%s: foreign segment reported as %r" % (case, out.strip()))

    # A missing middle segment, and --no-parts.
    gap = os.path.join(d, "_gap")
    shutil.copytree(setdir, gap)
    os.remove(os.path.join(gap, os.path.basename(parts[1])))
    rc, out = run_full(unclassic, os.path.join(gap, os.path.basename(parts[-1])),
                       os.path.join(d, "_gapout"))
    fails.check(rc != 0, "%s: a missing segment must fail" % case)
    rc, out = run_full_with(unclassic, parts[-1], os.path.join(d, "_np"),
                            ["--no-parts"])
    fails.check(rc != 0, "%s: --no-parts must not extract a set" % case)

    # The index buffer is an allocation, so it can be refused — and then
    # the walk reads each record where it lies, which costs part opens
    # and changes nothing else. Run one byte under the run's own
    # high-water mark, which lands on exactly that block because it is
    # allocated last (src/fmt_cpt.c).
    r = run([unclassic, "x", "--forks", "hidden", "--stats", "-o",
             os.path.join(d, "_hw"), os.path.abspath(parts[-1])])
    hw = re.search(r"high-water (\d+)", r.stdout.decode("utf-8", "replace"))
    if fails.check(bool(hw), "%s: --stats printed no high-water" % case):
        dest = os.path.join(d, "_tight")
        rc, out = run_full_with(unclassic, parts[-1], dest,
                                ["--stats", "--budget",
                                 str(int(hw.group(1)) - 1)])
        fails.check(rc == 0, "%s: refusing the index buffer broke the read: %s"
                    % (case, out.strip()))
        fails.check(read_tree(dest) == want,
                    "%s: the record-at-a-time walk gave different bytes" % case)
        tight = re.search(r"segments: (\d+) part opens, (\d+)", out)
        if fails.check(bool(tight),
                       "%s: no segment stats under the tight budget" % case):
            print("  %-7s without the index buffer: %s part opens, %s backward"
                  % (case + ":", tight.group(1), tight.group(2)))
            fails.check("1 refused" in out,
                        "%s: the tight budget refused nothing, so the "
                        "fallback was never taken" % case)

    # Part opens against a floor derived from the archive's own directory.
    r = run([unclassic, "x", "--forks", "hidden", "--stats", "-o",
             os.path.join(d, "_stats"), os.path.abspath(parts[-1])])
    out = r.stdout.decode("utf-8", "replace")
    line = [l for l in out.splitlines() if l.startswith("segments:")]
    floor = cpt_floor(os.path.join(FIXDIR, fixture), seg_size)
    if fails.check(bool(line), "%s: --stats printed no segment line" % case):
        got = tuple(int(w) for w in re.findall(r"(\d+) part opens, (\d+)",
                                               line[0])[0])
        print("  %-7s %s  (floor: %d part opens, %d backward)"
              % (case + ":", line[0], floor[0], floor[1]))
        fails.check(got == floor,
                    "%s: %d/%d opens against a floor of %d/%d"
                    % (case, got[0], got[1], floor[0], floor[1]))


def cpt_specimens(unclassic, workroot, fails):
    """The real thing, when it is here: sets cut by Compact Pro 1.51
    itself (tools/vmac/cptsegment.py). The generator above is checked
    against these byte for byte by `cptsegment.py --verify`; this checks
    the READER against them, which is a different question."""
    if not os.path.isdir(SPECIMENS):
        print("run_segments: no Compact Pro specimens (tools/vmac/cptsegment.py)")
        return 0
    ran = 0
    for case in sorted(os.listdir(SPECIMENS)):
        meta_path = os.path.join(SPECIMENS, case, "case.json")
        if not os.path.exists(meta_path):
            continue
        meta = json.load(open(meta_path))
        src = os.path.join(FIXDIR, meta["source_fixture"])
        if not os.path.exists(src):
            continue
        parts = cpt_parts(os.path.join(SPECIMENS, case))
        d = os.path.join(workroot, "specimen-" + case)
        os.makedirs(d)
        rc, out = run_full(unclassic, src, os.path.join(d, "_whole"))
        fails.check(rc == 0, "specimen %s: the archive failed" % case)
        rc, out = run_full(unclassic, parts[-1], os.path.join(d, "_ours"))
        fails.check(rc == 0, "specimen %s: the real set failed: %s"
                    % (case, out.strip()))
        fails.check(read_tree(os.path.join(d, "_ours"))
                    == read_tree(os.path.join(d, "_whole")),
                    "specimen %s: the real set gave something else" % case)
        ran += 1
        print("  specimen %s: %d segments cut by Compact Pro 1.51 — same bytes"
              % (case, len(parts)))
    return ran


# --- parts that arrived inside an envelope --------------------------------


WRAPPED_CASES = {
    # case: {part basename: (envelope, name the wrapper is given)}
    "wrapped-hqx": {},
    "wrapped-bin": {},
    "wrapped-mixed": {
        "Test.sit.2": ("bin", "zzz-download"),
        "Test.sit.3": ("hqx", "Other.sit.9"),
    },
}


def wrapped_layout(case):
    """(default envelope, per-part overrides, per-part renames)."""
    over = WRAPPED_CASES[case]
    default = "bin" if case == "wrapped-bin" else "hqx"
    return (default,
            dict((k, v[0]) for k, v in over.items()),
            dict((k, v[1]) for k, v in over.items()))


def wrapper_name(case, part):
    """What the wrapper around `part` is called on disk. The reader is
    not allowed to care; the harness has to, since it puts the files
    there and takes them away again."""
    default, per_part, rename = wrapped_layout(case)
    env = per_part.get(part, default)
    return rename.get(part, part) + wsynth.ENVELOPES[env][1]


def wrapped_case_run(unclassic, case, workroot, fails):
    """A set whose parts are each in their own envelope — what a real
    download of one looks like: Archive.sit.1.hqx, Archive.sit.2.hqx.

    Adjudicated three ways, none of which is the peel path being tested:

      * the generator, which knows the joined bytes exactly;
      * our own read of the SAME set unwrapped, which reaches the joiner
        by a route that never opens an envelope;
      * `unar`, for what it does rather than for ground truth. MEASURED
        2026-08-13: handed part 1 of a wrapped set it unwraps that one
        part, writes it out and exits 0 — success, with a fragment. If
        that ever changes, the reference has gained a capability this
        program was built because it lacks, and the note in
        OPEN_ITEMS.md wants revisiting.
    """
    d = os.path.join(workroot, case)
    plain = os.path.join(d, "plain")
    os.makedirs(plain)
    rawname, payload, rsrclen, datalen = synth.CASES["basic3"](plain)
    name = rawname.decode("ascii")
    want = expected_tree(name, payload, rsrclen)

    default, per_part, rename = wrapped_layout(case)
    wrapped = os.path.join(d, "wrapped")
    wsynth.wrap_dir(plain, wrapped, default, per_part, rename)
    first = os.path.join(wrapped, wrapper_name(case, "Test.sit.1"))
    if not fails.check(os.path.exists(first),
                       "%s: part 1 was not wrapped" % case):
        return

    # Ours, the way a user gets it: no -nr, because taking the envelope
    # off is the layer under test.
    rc, out = run_full(unclassic, first, os.path.join(d, "_ours"))
    fails.check(rc == 0, "%s: unclassic failed: %s" % (case, out.strip()))
    got = read_tree(os.path.join(d, "_ours"))
    fails.check(got == want,
                "%s: ours disagrees with the generator: %s vs %s"
                % (case, sorted(got), sorted(want)))

    # The same set, unwrapped: an opinion that owes nothing to the peel.
    rc, out = run_full(unclassic, os.path.join(plain, "Test.sit.1"),
                       os.path.join(d, "_plain"))
    fails.check(rc == 0, "%s: the unwrapped set failed: %s" % (case, out.strip()))
    fails.check(got == read_tree(os.path.join(d, "_plain")),
                "%s: wrapped and unwrapped reads disagree" % case)

    # Nothing of ours is left in the output directory.
    fails.check(not os.path.exists(os.path.join(d, "_ours",
                                                ".unclassic-parts")),
                "%s: the decoded parts were left behind" % case)

    rc, out = oracle_extract(first, os.path.join(d, "_oracle"))
    got_oracle = read_tree(os.path.join(d, "_oracle"), appledouble=True)
    fails.check(got_oracle != want,
                "%s: the oracle joined a wrapped set after all" % case)
    return d, plain, wrapped, first, want


def wrapped_behaviours(unclassic, case, d, plain, wrapped, first, want, fails):
    """What byte-exactness cannot see: what gets in, and what does not."""
    # A wrapped part of a DIFFERENT set, named exactly like the one that
    # is missing. The envelope comes off and the fingerprint decides, so
    # the name buys it nothing.
    other = os.path.join(d, "_other")
    os.makedirs(other)
    synth.CASES["many12"](other)
    decoy = os.path.join(d, "decoy")
    shutil.copytree(wrapped, decoy)
    default, per_part, _r = wrapped_layout(case)
    gone = wrapper_name(case, "Test.sit.2")
    os.remove(os.path.join(decoy, gone))
    wsynth.wrap_file(os.path.join(other, sorted(os.listdir(other))[1]),
                     decoy, per_part.get("Test.sit.2", default),
                     dest_name=gone.rsplit(".", 1)[0])
    rc, out = run_full(unclassic,
                       os.path.join(decoy, wrapper_name(case, "Test.sit.1")),
                       os.path.join(d, "_decoy"))
    fails.check(rc != 0, "%s: a foreign wrapped part was accepted" % case)
    fails.check("segment" in out.lower(),
                "%s: foreign wrapped part reported as %r" % (case, out.strip()))
    fails.check(not os.path.exists(os.path.join(d, "_decoy",
                                                ".unclassic-parts")),
                "%s: a failed join left its decoded parts behind" % case)

    # Parts collected from three directories, under three names, in two
    # envelopes: the set is what the headers say it is.
    scat = os.path.join(d, "_scattered")
    for i, sub in ((1, "a"), (2, "b"), (3, "c")):
        os.makedirs(os.path.join(scat, sub))
        wsynth.wrap_file(os.path.join(plain, "Test.sit.%d" % i),
                         os.path.join(scat, sub),
                         "hqx" if i != 2 else "bin",
                         dest_name="disk%d" % i)
    rc, out = run_full_with(unclassic,
                            os.path.join(scat, "a", "disk1.hqx"),
                            os.path.join(d, "_scat"),
                            ["--part", os.path.join(scat, "b", "disk2.bin"),
                             "--part", os.path.join(scat, "c", "disk3.hqx")])
    fails.check(rc == 0, "%s: --part with wrapped parts failed: %s"
                % (case, out.strip()))
    fails.check(read_tree(os.path.join(d, "_scat")) == want,
                "%s: scattered wrapped parts gave different bytes" % case)

    # What the search is rationed by: a set that is COMPLETE opens
    # nothing beside it, however many envelopes are lying there. The
    # "looked inside" line is the decode itself reporting, so this
    # measures the cost and not a consequence of it.
    beside = os.path.join(d, "_beside")
    shutil.copytree(plain, beside)
    wsynth.wrap_file(os.path.join(plain, "Test.sit.2"), beside, "hqx",
                     dest_name="spare")
    r = run([unclassic, "x", "-v", "--forks", "hidden", "-o",
             os.path.join(d, "_beside_out"), os.path.join(beside, "Test.sit.1")])
    out = r.stdout.decode("utf-8", "replace")
    fails.check(r.returncode == 0,
                "%s: the unwrapped set failed beside an envelope: %s"
                % (case, out.strip()))
    fails.check("looked inside" not in out,
                "%s: a complete set opened the envelopes beside it" % case)
    fails.check(read_tree(os.path.join(d, "_beside_out")) == want,
                "%s: the unwrapped set gave different bytes" % case)

    # ...and a set that is SHORT does pay, which is how a half-unstuffed
    # download joins: two parts unwrapped on disk, the third still in
    # its envelope.
    half = os.path.join(d, "_half")
    shutil.copytree(plain, half)
    os.remove(os.path.join(half, "Test.sit.2"))
    wsynth.wrap_file(os.path.join(plain, "Test.sit.2"), half, "hqx",
                     dest_name="whatever-it-was-called")
    r = run([unclassic, "x", "-v", "--forks", "hidden", "-o",
             os.path.join(d, "_half_out"), os.path.join(half, "Test.sit.1")])
    out = r.stdout.decode("utf-8", "replace")
    fails.check(r.returncode == 0, "%s: a half-unstuffed set failed: %s"
                % (case, out.strip()))
    fails.check("looked inside" in out,
                "%s: a set short of a part did not look inside anything"
                % case)
    fails.check(read_tree(os.path.join(d, "_half_out")) == want,
                "%s: the half-unstuffed set gave different bytes" % case)


def run_full_with(unclassic, path, dest, extra):
    os.makedirs(dest, exist_ok=True)
    r = run([unclassic, "x", "--forks", "hidden", "-o", dest]
            + list(extra) + [os.path.abspath(path)])
    return r.returncode, r.stdout.decode("utf-8", "replace")



# --------------------------------------------------------------------
# DiskDoubler `SPLT` sets (tools/synth_ddsplit.py)
#
# The one scheme here with NO oracle at all: `unar` 1.10.8 does not
# recognize a part, and does not recognize the parts concatenated
# either — asserted below rather than quoted, because it is a claim
# about the reference and those go stale. So a case is adjudicated
# against the bytes that were cut up, and, where the payload is an
# archive, against our own read of the unsplit one.
#
# What grades the FORMAT is elsewhere: tools/run_ddtf.py replays the
# four real specimens against the original files they were made from.
# This file grades the READER against the layout in src/fmt_ddseg.c.
# --------------------------------------------------------------------

def ddseg_joined(dest, part_path):
    """The one entry a `SPLT` set yields. The format stores no name, so
    it is the OPENED part's, minus a trailing ".N"."""
    base = os.path.basename(part_path)
    stem, _, ext = base.rpartition(".")
    if stem and ext.isdigit():
        base = stem
    data = os.path.join(dest, base)
    rsrc = os.path.join(dest, "._" + base)
    return (open(data, "rb").read() if os.path.exists(data) else None,
            open(rsrc, "rb").read() if os.path.exists(rsrc) else b"")


def ddseg_case_run(unclassic, case, workroot, fails):
    d = os.path.join(workroot, "ddseg-" + case)
    os.makedirs(d)
    whole, rsrc, parts, src = dsynth.CASES[case](d)
    original = open(whole, "rb").read()

    # From the first part and from the last: the part's own index is in
    # its header, so the set is reachable from any member.
    for which in sorted({0, len(parts) - 1}):
        dest = os.path.join(d, "_ours%d" % which)
        rc, out = ours_join(unclassic, parts[which], dest)
        fails.check(rc == 0, "ddseg/%s: unclassic failed from part %d: %s"
                    % (case, which + 1, out.strip()))
        gotd, gotr = ddseg_joined(dest, parts[which])
        fails.check(gotd == original,
                    "ddseg/%s: the join is not the file that was cut up "
                    "(from part %d)" % (case, which + 1))
        fails.check(gotr == rsrc,
                    "ddseg/%s: the joined resource fork is wrong (from part "
                    "%d): %d bytes vs %d, %s"
                    % (case, which + 1, len(gotr), len(rsrc),
                       "same length, different bytes" if len(gotr) == len(rsrc)
                       else "wrong length"))

    # The oracle cannot join this scheme, and the case says so rather
    # than assuming it: if this ever starts passing, `SPLT` has a second
    # implementation and everything here can be graded against it.
    rc, out = oracle_extract(parts[0], os.path.join(d, "_oracle"))
    fails.check(rc != 0 or not out.strip().startswith("Test.dd"),
                "ddseg/%s: the oracle read a SPLT part after all" % case)

    if src is not None:
        rc, out = run_full(unclassic, parts[0], os.path.join(d, "_full"))
        fails.check(rc == 0, "ddseg/%s: joined archive did not extract: %s"
                    % (case, out.strip()))
        rc, out = run_full(unclassic, whole, os.path.join(d, "_unsplit"))
        fails.check(rc == 0, "ddseg/%s: unsplit archive did not extract: %s"
                    % (case, out.strip()))
        fails.check(read_tree(os.path.join(d, "_full")) ==
                    read_tree(os.path.join(d, "_unsplit")),
                    "ddseg/%s: joined and unsplit reads disagree" % case)
    return d, whole, rsrc, parts, original


def ddseg_behaviours(unclassic, case, d, whole, rsrc, parts, original,
                     workroot, fails):
    """What byte-exactness cannot see: the four ways a set can be wrong,
    and the two properties no other scheme here has."""
    n = len(parts)

    # --no-parts on a set of more than one must FAIL. A `SPLT` part
    # declares the part count, so a reader that quietly emitted the one
    # part it was handed would be discarding a fact it had.
    dest = os.path.join(d, "_alone")
    rc, out = ours_join(unclassic, parts[0], dest, extra=("--no-parts",))
    if n > 1:
        fails.check(rc != 0, "ddseg/%s: --no-parts must fail on a %d-part set"
                    % (case, n))
    else:
        # A set of ONE is a whole file with a 94-byte hat: it extracts
        # with no volume source at all, which is a different code path
        # (unc_ddseg_extract, not the joiner).
        fails.check(rc == 0, "ddseg/%s: --no-parts on a set of one failed: %s"
                    % (case, out.strip()))
        gotd, gotr = ddseg_joined(dest, parts[0])
        fails.check(gotd == original and gotr == rsrc,
                    "ddseg/%s: the lone-part path gave different bytes" % case)

    if n < 2:
        return

    # A part of a DIFFERENT set, sitting in the same directory, must be
    # ignored: parts are matched by the 26 identity bytes, never by name.
    other = os.path.join(d, os.path.basename(parts[1]) + ".other")
    pay = b"\xEE" * 200
    with open(other, "wb") as f:
        f.write(dsynth.part_header(0x1234567, 200, 0, 1, n, pay) + pay)
    dest = os.path.join(d, "_intruder")
    rc, out = ours_join(unclassic, parts[0], dest)
    fails.check(rc == 0, "ddseg/%s: an intruder broke the set: %s"
                % (case, out.strip()))
    fails.check(ddseg_joined(dest, parts[0])[0] == original,
                "ddseg/%s: an intruder changed the join" % case)
    os.remove(other)

    # A missing part must fail, and say what is wrong with it.
    hidden = os.path.join(workroot, "ddseg-hidden-" + case)
    shutil.move(parts[1], hidden)
    rc, out = ours_join(unclassic, parts[0], os.path.join(d, "_gap"))
    fails.check(rc != 0, "ddseg/%s: a missing part must fail" % case)
    fails.check("segment" in out.lower(),
                "ddseg/%s: missing part reported as %r" % (case, out.strip()))
    shutil.move(hidden, parts[1])

    # A part that declares more payload than it holds is truncated, and
    # must be refused rather than read to the end of the file.
    body = open(parts[1], "rb").read()
    pay = body[dsynth.HEAD:]
    lie = dsynth.part_header(0x0009BE6, len(original), len(rsrc), 1, n, pay,
                             paylen=len(pay) + 4096)
    with open(parts[1], "wb") as f:
        f.write(lie + pay)
    rc, out = ours_join(unclassic, parts[0], os.path.join(d, "_short"))
    fails.check(rc != 0,
                "ddseg/%s: a part declaring more payload than it holds must "
                "fail" % case)
    with open(parts[1], "wb") as f:
        f.write(body)

    # And the join still works afterwards, so the two mutations above
    # are testing the mutation rather than the directory.
    rc, out = ours_join(unclassic, parts[0], os.path.join(d, "_again"))
    fails.check(rc == 0 and
                ddseg_joined(os.path.join(d, "_again"), parts[0])[0] == original,
                "ddseg/%s: the set stopped joining after it was restored"
                % case)


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
    wrapcases = [c for c in (selected or sorted(WRAPPED_CASES))
                 if c in WRAPPED_CASES]
    cptcases = [c for c in (selected or sorted(CPT_CASES)) if c in CPT_CASES]
    splitcases = [c for c in (selected or sorted(ssynth.CASES))
                  if c in ssynth.CASES]
    ddsegcases = [c for c in (selected or sorted(dsynth.CASES))
                  if c in dsynth.CASES]
    if ddsegcases and not dsynth.available():
        print("run_segments: `zip` not found; skipping the zip4 SPLT case")
        ddsegcases = [c for c in ddsegcases if c != "zip4"]
    if splitcases and not ssynth.available():
        print("run_segments: `zip` not found; skipping the zip5 split case")
        splitcases = [c for c in splitcases if c != "zip5"]

    nspec = 0
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

        # --- Compact Pro segments ---------------------------------------
        for c in cptcases:
            r = cpt_case_run(unclassic, c, workroot, fails)
            if r:
                d, setdir, parts, want = r
                cpt_behaviours(unclassic, c, d, setdir, parts, want,
                               workroot, fails)
        nspec = cpt_specimens(unclassic, workroot, fails)

        # --- parts inside envelopes -------------------------------------
        for c in wrapcases:
            r = wrapped_case_run(unclassic, c, workroot, fails)
            if r:
                d, plain, wrapped, first, want = r
                wrapped_behaviours(unclassic, c, d, plain, wrapped, first,
                                   want, fails)

        # --- plain NAME.001 splits --------------------------------------
        for c in splitcases:
            r = split_case_run(unclassic, c, workroot, fails)
            if r:
                d, kind, whole, parts, original = r
                split_behaviours(unclassic, c, d, kind, whole, parts,
                                 original, workroot, fails)

        # --- DiskDoubler `SPLT` sets ------------------------------------
        for c in ddsegcases:
            r = ddseg_case_run(unclassic, c, workroot, fails)
            if r:
                d, whole, rsrc, parts, original = r
                ddseg_behaviours(unclassic, c, d, whole, rsrc, parts,
                                 original, workroot, fails)
    finally:
        if a.keep:
            print("kept: %s" % workroot)
        else:
            shutil.rmtree(workroot, ignore_errors=True)

    for f in fails:
        print("FAIL " + f)
    print("segments: %d StuffIt + %d spanned-zip + %d split + %d wrapped + "
          "%d Compact Pro + %d DiskDoubler SPLT cases, %d failures"
          % (len(cases), len(zipcases), len(splitcases), len(wrapcases),
             len(cptcases), len(ddsegcases), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
