#!/usr/bin/env python3
"""run_diff.py — differential acceptance tests.

For every manifest in fixtures/manifests/ whose fixture is present:
  1. `macextract x` into a temp dir
  2. compare every entry byte-for-byte against the oracle manifest:
     data fork sha256+size, resource fork sha256+size, and type/creator
     when recorded (via `macextract l`).

Formats the engine does not implement yet are skipped (reported), not
failed: milestones land one format at a time. A manifest whose format
IS implemented must pass completely.
"""
import argparse, hashlib, json, os, re, subprocess, sys, tempfile
from concurrent import futures
import unicodedata

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIXDIR = os.path.join(ROOT, "fixtures")

# lsar format name -> our format name; grown as milestones land.
# Only fixtures whose format appears here are asserted on.
IMPLEMENTED = {
    "MacBinary": "MacBinary",              # M1
    "AppleSingle": "AppleSingle",          # M1
    "AppleDouble": "AppleDouble",          # M1
    "BinHex": "BinHex 4",                  # M2
    "PackIt": "PackIt",                    # M3
    "Compact Pro": "Compact Pro",          # M4
    "StuffIt": "StuffIt",                  # M5/M6
    "StuffIt 5": "StuffIt 5",              # M7
    "Zip": "Zip",                          # M8
    # A zip behind a code stub. `lsar` names the STUB and this engine
    # names the archive, which is the one case in this table where the
    # two differ about a format both read — recognised here since
    # 2026-10-05, and the fixture is PKZIP 1.01's own distribution
    # self-extractor (FORMATS.md, *What the zip pair claims*, *Implode*).
    "Self-extracting Zip": "Zip",
    "Gzip": "Gzip",
    "Tar": "Tar",
    "Compress": "Unix compress",
    "DiskDoubler": "DiskDoubler",          # M12
    "Now Compress": "Now Compress",        # M12
    "ARC": "ARC",                          # M13
    # `unar` cannot read uuencode at all, so a manifest for one is not
    # built from the oracle: its ground truth is the bytes
    # tools/synth_uu.py encoded, with macutils' hexbin agreeing on the
    # same content in tools/run_uu.py. The manifest says so in its
    # "oracle" field (TESTING.md, "ARC and uuencode").
    "uuencode": "uuencode",                # M13
    "LZH": "LZH",                          # M28
    # Nothing but Aladdin's own translator reads an AppleLink package —
    # `unar`, deark and macunpack have never heard of the format — so
    # these manifests are the bytes tools/synth_sqp.py compressed, with
    # gzip reading every LZW fork through a .Z header in
    # tools/run_sqp.py. The manifest says so in its "oracle" field
    # (TESTING.md, *AppleLink packages: SqueezePlay*).
    "SqueezePlay": "AppleLink package",    # M56
    # Nor `.hex` and `.hcx`, BinHex before 4.0: these manifests are
    # hexbin's reading, and four of them were written by BinHex 2.0 from
    # a subject whose bytes are known (tools/run_hecx.py).
    "BinHex hex/hcx": "BinHex hex/hcx",
}

# Formats v1 names but does not extract. Until 2026-08-14 a fixture of one
# of these was simply skipped — counted as "formats pending" and asserted
# on in no way at all — which left the whole detect-only claim untested:
# `unc_sniff` names them "so a UI can tell the user what the file is"
# (CLAUDE.md) and nothing checked that it does. They are now graded on
# the two things the claim actually promises: the NAME agrees with the
# oracle's, and extraction refuses without writing anything.
DETECT_ONLY = {
    "StuffIt X": "StuffIt X",
    "DiskCopy": "Disk Copy 4.2",
}


def check_detect_only(macextract, fx, ourname):
    """A format v1 names but does not extract. Two promises, both checked:
    `sniff` agrees with the oracle about WHAT it is, and `x` refuses
    without writing anything. Returns a list of problems."""
    bad = []
    r = subprocess.run([macextract, "sniff", fx], capture_output=True,
                       timeout=120)
    got = r.stdout.decode("utf-8", "replace").strip()
    if got != ourname:
        bad.append(f"sniff says {got!r}, the oracle says {ourname!r}")
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([macextract, "x", "-o", tmp, fx],
                           capture_output=True, timeout=300)
        files, dirs = collect_outputs(tmp)
        if r.returncode == 0:
            bad.append("extraction exited 0 for a format v1 cannot extract")
        if files or dirs:
            bad.append(f"extraction wrote {len(files)} file(s) and "
                       f"{len(dirs)} folder(s); it must write nothing")
    return bad


def norm(name):
    # NFC-normalize, and neutralize path-separator sanitization
    # differences: classic Mac names may contain '/', which unar writes
    # as '_' and macextract as ':' — map all three to '_' on both sides.
    n = unicodedata.normalize("NFC", name)
    return n.replace(":", "_").replace("/", "_")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def normpath(path):
    """norm() each path component, preserving directory separators."""
    return "/".join(norm(c) for c in path.split("/"))


def sidecar(path):
    """Resource-fork sidecar path for an entry: "dir/file" -> "dir/._file".

    Both sides of the diff use the "._" prefix (`macextract --forks
    hidden`, `unar -k hidden`) rather than a ".rsrc" suffix, because
    the suffix collides with real entries in archives that hold both
    "X" and "X.rsrc". DECISIONS.md, 2026-08-08.
    """
    head, _, tail = path.rpartition("/")
    return f"{head}/._{tail}" if head else f"._{tail}"


def collect_outputs(tmp):
    """Map normalized relative path -> full path for files and dirs."""
    files, dirs = {}, set()
    for root, ds, fs in os.walk(tmp):
        rel = os.path.relpath(root, tmp)
        for d in ds:
            dirs.add(normpath(os.path.normpath(os.path.join(rel, d))))
        for f in fs:
            p = normpath(os.path.normpath(os.path.join(rel, f)))
            files[p] = os.path.join(root, f)
    return files, dirs


# `macextract l --finder`: the Finder metadata as hex, which is the only
# form that can be read back. The pretty columns cannot be: `%4s/%-4s`
# of a code holding a SPACE ("PDF ") or a NUL moves the name by a field,
# and 200 of the corpus's 5,539 type/creator codes hold a space
# (measured 2026-10-04). The old parser took those rows' names apart
# wrongly, found no manifest entry under the mangled name, and compared
# nothing — silently (DECISIONS.md 2026-10-04).
LISTING_ROW = re.compile(
    r"^([fd]) +(?:\S+) +(?:\S+) +([0-9a-f]{8})/([0-9a-f]{8}) "
    r"([0-9a-f]{4}) (.*)$")


def parse_listing(out):
    """Parse `macextract l --finder` output ->
    ({name: (type, creator, finder_flags)}, unparsed_row_count).

    Every listed entry is recorded, not only those with type/creator: the
    listing is how an entry the engine cannot extract is checked to be
    SEEN at all, and a zip entry has no Finder metadata at all (every
    field is zero). Directories are recorded too: a folder has Finder
    flags of its own and the oracle reports them.

    Type and creator come back as the 32-bit values they are, so a
    comparison is exact for all four bytes including NUL and the high
    half of MacRoman.
    """
    meta, unparsed = {}, 0
    for line in out.splitlines():
        if not (line.startswith("f ") or line.startswith("d ")):
            continue
        m = LISTING_ROW.match(line)
        if not m:
            # Never shrugged off: a row the suite cannot read is a row
            # it grades nothing about, which is the hole this parser
            # was rewritten to close.
            unparsed += 1
            continue
        meta[normpath(m.group(5))] = (int(m.group(2), 16),
                                      int(m.group(3), 16),
                                      int(m.group(4), 16))
    return meta, unparsed


ENTRY_ERR = re.compile(r"^macextract: (.*): (.*)$")
TALLY = re.compile(r"^macextract: (\d+) of (\d+) entries failed$")


def parse_entry_errors(stderr):
    """Return {normalized entry name: reason}.

    `macextract` reports a failed entry as "macextract: NAME: reason"; the
    whole-archive errors it prints instead name the FIXTURE path, and are
    left in the dict deliberately — they must never be excused as
    per-entry.
    """
    errs = {}
    for line in stderr.splitlines():
        if TALLY.match(line):
            continue
        m = ENTRY_ERR.match(line)
        if m:
            errs[normpath(m.group(1))] = m.group(2)
    return errs


def said_unsupported(msg):
    """True when our binary declined an entry for UNC_ERR_UNSUPPORTED.

    Two shapes since 2026-08-25 — the generic one and the one that names
    the method, which is what makes a bug report about it actionable —
    and both end the same way. Matching the ENDING rather than the whole
    sentence keeps this from breaking every time the wording is improved,
    which is what it did the day the wording was improved.

    The excuse itself is still anchored to the ORACLE (see below): this
    only says which of our errors is eligible for one."""
    return msg.endswith("is not supported yet")

# Compression methods v1 does not implement, NAMED AS THE ORACLE NAMES
# THEM (`XADCompressionName`, recorded per entry in the manifest). An
# entry our engine declines as unsupported (said_unsupported) is excused
# only if the oracle says its method is one of these — so the excuse is
# anchored to lsar, and a regression that made a SUPPORTED method report
# "unsupported" cannot buy itself an excuse. FORMATS.md is the scope.
#
# Deliberately only the methods the corpus actually contains: a method
# named here that lsar spells differently would excuse nothing, silently,
# whereas an unlisted one fails the suite loudly and gets added. Tar
# links belong here the day a fixture has one.
#
# **EMPTY as of 2026-10-07**, and kept because it was not: `Implode`
# left when zip method 6 was implemented, which turned the 7 entries of
# `4acalc.zip` and `4alnch11.zip` from "graded on their names" into 7
# forks compared byte for byte — 5 against `unar` and 2 against deark,
# the two `unar` fails (DECISIONS.md 2026-10-07, *the method that was
# out for a premise with no halves left*). An empty set is not a dead
# mechanism: `out_of_scope` below still runs on every entry. Shrink and
# Reduce did not need it: the entries `unar` fails went to deark through
# DEARK_METHODS (2026-10-08 and 2026-10-11).
ORACLE_OUT_OF_SCOPE = set()


def out_of_scope(entry):
    """True when the ORACLE says every method of this entry is outside v1
    scope. An entry with no recorded method is never out of scope: an
    absent field must not become an excuse."""
    m = entry.get("oracle_methods")
    return bool(m) and all(x in ORACLE_OUT_OF_SCOPE for x in m)


def said_truncated(msg):
    """True when our binary declined an entry because the file ran out.

    Same rule as `said_unsupported`: match the ENDING, not the whole
    sentence."""
    return msg.endswith("file is truncated")


# A fork the manifest grades from the container rather than from an
# implementation. `make_manifests.py` writes this only for a MacBinary
# whose file ends before its own header says it should, and only where
# the arithmetic is confirmed on that very file — so the string is an
# assertion that the fixture IS truncated (TESTING.md, *The container's
# own arithmetic*).
MACBINARY_ARITHMETIC = "MacBinary container arithmetic"


def graded_from_container(entry):
    return any(entry.get(f + "_oracle") == MACBINARY_ARITHMETIC
               for f in ("data", "rsrc"))


# Archives that do NOT fit on a 1 MB Mac Plus as the application stands.
#
# Empty, and kept because it was not: on 2026-08-30 three StuffIt 5 archives
# needed 566,009 B against a budget of 565,176 and were refused per entry —
# correct behaviour, but a capability the application had lost by growing.
# 988 B of code came back the same day and they fit again, by 155 B
# (FORMATS.md, *Budget*).
#
# Anything listed here is PINNED, not skipped: a fixture here that passes
# fails this run as STALE, and one not here that fails is a regression. The
# way to empty it is less CODE — data and globals cost the budget nothing.
OVER_BUDGET_1MB = set()      # empty: every corpus archive fits again


# A field a fixture may declare its manifest does NOT grade, with the
# reason in the manifest beside it. Exactly one, and it is not a
# convenience: the three Macintosh dates in zip's 0x334d have no oracle
# at all, because XADMaster adds CrGMTOffs where deark subtracts it and
# both call the result UTC (FORMATS.md, *Zip's Macintosh extra fields*).
# Anything else under the key is REFUSED — a fixture cannot declare away
# a field this suite compares — and a declaration without a reason is
# refused too, because the reason is the whole value of the key.
UNGRADABLE = {"dates"}


def check_ungraded(man, problems):
    """Validate a manifest's `ungraded` declaration. Returns the fields
    declared, for the tally at the end: a tolerance nobody counts is a
    tolerance nobody reads."""
    decl = man.get("ungraded") or {}
    if not isinstance(decl, dict):
        problems.append("the manifest's \"ungraded\" is not an object")
        return []
    for field, why in sorted(decl.items()):
        if field not in UNGRADABLE:
            problems.append(
                f"the manifest declares {field!r} ungraded, and this "
                f"suite grades it; only {sorted(UNGRADABLE)} may be "
                f"declared")
        elif not (isinstance(why, str) and why.strip()):
            problems.append(
                f"the manifest declares {field!r} ungraded with no "
                f"reason; the reason is the point")
    return sorted(decl)


def fourcc(s):
    """A manifest's four-character code -> the 32-bit value the listing
    prints. The manifest holds the oracle's four bytes decoded as
    MacRoman, and MacRoman is a complete 256-character table, so the
    encode back is exact."""
    if s is None:
        return None
    b = s.encode("mac_roman")[:4].ljust(4, b"\0")
    return int.from_bytes(b, "big")


def check_flags(e, name, listing, problems, graded_flags):
    """The Finder flags, where the ORACLE recorded them. A manifest built
    before 2026-10-04 has none and grades nothing here, so the count is
    printed at the end rather than assumed: a column nobody compares is
    the shape this suite has been caught by before (DECISIONS.md
    2026-10-01, *a page comment found what 947 fixtures could not*)."""
    if "finder_flags" not in e:
        return
    if name not in listing:
        problems.append(
            f"{name!r}: the oracle reports Finder flags "
            f"{e['finder_flags']:#06x} and the listing has no row for "
            f"this entry")
        return
    ff = listing[name][2]
    if ff != e["finder_flags"]:
        problems.append(f"{name!r}: Finder flags {ff:#06x} != "
                        f"{e['finder_flags']:#06x}")
    else:
        graded_flags[0] += 1


def check_fixture(macextract, man, verbose, budget=0, graded_flags=None):
    fx = os.path.join(FIXDIR, man["fixture"])
    cap = ["--budget", str(budget)] if budget else []
    problems, unadjudicated, masked = [], 0, 0
    graded_flags = graded_flags if graded_flags is not None else [0]
    declared = check_ungraded(man, problems)
    excused = {normpath(e["name"]) for e in man["entries"]
               if e.get("unadjudicated")}
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([macextract, "x", "-nr", "--forks", "hidden",
                            "-o", tmp, fx] + cap,
                           capture_output=True, timeout=300)
        un_errs = parse_entry_errors(r.stderr.decode("utf-8", "replace"))
        # An entry may produce nothing for exactly two reasons, both of
        # them the ORACLE's word rather than ours: it failed that entry
        # too, or it names the entry's compression method as one v1 does
        # not implement. Never because our binary said "unsupported" —
        # that would let a regression in the method dispatch grade itself.
        outofscope = {normpath(e["name"]) for e in man["entries"]
                      if out_of_scope(e)}
        # And a third case, which is an ASSERTION rather than an excuse.
        # An entry whose forks the manifest graded from the container's
        # own arithmetic is one the manifest says is CUT: the hashes are
        # of the bytes physically present. So our engine must report
        # that entry truncated — reporting success on it is the M42
        # defect, and reporting nothing is a missing entry. The excuse
        # is the manifest's word; `said_truncated` only says which of
        # our messages is eligible for it.
        cut = {normpath(e["name"]) for e in man["entries"]
               if graded_from_container(e)}
        for n in sorted(cut):
            if not said_truncated(un_errs.get(n, "")):
                problems.append(
                    f"{n!r}: the container's arithmetic grades this entry "
                    f"as cut and our engine did not report it truncated "
                    f"({un_errs.get(n, 'no per-entry error at all')!r})")
        if r.returncode != 0:
            unexplained = {n: er for n, er in un_errs.items()
                           if n not in excused
                           and not (said_unsupported(er) and n in outofscope)
                           and not (said_truncated(er) and n in cut)}
            if unexplained or not un_errs:
                problems.append(
                    f"exit {r.returncode}: {r.stderr.decode()[:300]}")
        files, dirs = collect_outputs(tmp)

        lr = subprocess.run([macextract, "l", "--finder", fx] + cap,
                            capture_output=True, timeout=60)
        listing, unparsed = parse_listing(lr.stdout.decode("utf-8", "replace"))
        if unparsed:
            problems.append(f"{unparsed} listing row(s) could not be parsed")

        for e in man["entries"]:
            name = normpath(e["name"])
            if e.get("is_dir"):
                if name not in dirs and name not in files:
                    problems.append(f"missing dir: {name!r}")
                check_flags(e, name, listing, problems, graded_flags)
                continue
            # Forks the oracle itself failed on carry no hashes: there
            # is no ground truth to compare against, so they are counted
            # and skipped rather than guessed at. The two halves of that
            # record cross-check each other — a missing hash with no
            # reason beside it, or a reason beside a hash, means the
            # manifest is malformed and the fixture fails.
            un = e.get("unadjudicated") or {}
            for fork in ("data", "rsrc"):
                if (fork + "_sha256" in e) == (fork in un):
                    problems.append(
                        f"{name!r}: malformed manifest, {fork} fork is "
                        f"{'both' if fork in un else 'neither'} adjudicated "
                        f"and unadjudicated")
            unadjudicated += len(un)
            # A fork can be unadjudicated in two different senses, and
            # collapsing them overstates the gap: some have been compared
            # on a Mac with the resource header's OS-stamped bytes masked
            # (tools/vmac/diskdoubler.py --adjudicate), which is not
            # byte-exact ground truth but is not "nobody has looked"
            # either. The reason string says which, and it is the
            # manifest's own words rather than a flag we set.
            masked += sum(1 for r in un.values() if "masked" in r)
            path = files.pop(name, None)
            rp = files.pop(sidecar(name), None)
            if len(un) == 2:
                # Nothing to compare, but the entry must still exist: an
                # unadjudicated fork is not a licence to drop it, and a
                # name is the one thing an aggregate check never fails on.
                if path is None and rp is None and name not in listing:
                    problems.append(f"missing entry: {name!r}")
                continue
            # A fork WITH ground truth is compared, or it is missing.
            # Absence is excused only for an entry whose method the oracle
            # puts outside v1 scope — not merely because the oracle failed
            # the entry's OTHER fork, which used to excuse the whole entry
            # and made 6 fixtures' adjudicated forks unfailable.
            absent_ok = name in un_errs and name in outofscope
            if path is None and not absent_ok:
                problems.append(f"missing file: {name!r}")
                continue
            if absent_ok and path is None and rp is None:
                # Out of scope and nothing written: the name is still
                # ground truth and is the only thing left to check.
                if name not in listing:
                    problems.append(f"missing entry: {name!r}")
                continue
            if "data" not in un:
                sz = os.path.getsize(path) if path else 0
                if sz != e["data_size"]:
                    problems.append(
                        f"{name!r}: data size {sz} != {e['data_size']}")
                elif path and sha256_file(path) != e["data_sha256"]:
                    problems.append(f"{name!r}: data sha mismatch")
            if "rsrc" not in un:
                rsz = os.path.getsize(rp) if rp else 0
                if rsz != e["rsrc_size"]:
                    problems.append(
                        f"{name!r}: rsrc size {rsz} != {e['rsrc_size']}")
                elif rp and sha256_file(rp) != e["rsrc_sha256"]:
                    problems.append(f"{name!r}: rsrc sha mismatch")
            if "type" in e and name in listing:
                t, c, _ = listing[name]
                want_t, want_c = fourcc(e["type"]), fourcc(e.get("creator"))
                if t != want_t or (want_c is not None and c != want_c):
                    problems.append(
                        f"{name!r}: type/creator {t:#010x}/{c:#010x} != "
                        f"{want_t:#010x}/"
                        f"{'-' if want_c is None else format(want_c, '#010x')}")
            check_flags(e, name, listing, problems, graded_flags)
        # The archive's OWN comment. It is not an entry — it has no
        # forks and no name of its own — so it is graded here rather
        # than in the entry loop: the oracle's XADComment (recorded in
        # the manifest by tools/make_manifests.py) against the file the
        # CLI writes beside the extracted items, and against the line
        # `macextract l` prints. A manifest without the key asserts the
        # opposite: nothing may be written, which the "unexpected
        # output" check below already enforces.
        want = man.get("comment")
        cname = normpath(man["fixture"] + ".comment.txt")
        if want:
            # Popped only when one is expected: popping unconditionally
            # would let a comment file written for an archive that has
            # none slip past the "unexpected output" check below, which
            # is the half of this that fails closed.
            cpath = files.pop(cname, None)
            if cpath is None:
                problems.append(f"missing archive comment: {cname!r}")
            else:
                # The file holds the archive's own bytes, which are
                # MacRoman; the oracle reports the same bytes decoded.
                # Encoded STRICTLY: `errors="replace"` would turn a
                # character the oracle read some other way into '?' and
                # compare that, which is a comparison that cannot fail.
                got = open(cpath, "rb").read()
                try:
                    wantb = want.encode("mac_roman")
                except UnicodeEncodeError:
                    wantb = None
                    problems.append(
                        f"manifest comment is not MacRoman: {want!r}")
                if wantb is not None and got != wantb:
                    problems.append(
                        f"archive comment {got!r} != {want!r}")
            # Printed, a CR line break becomes a newline (a raw CR
            # overwrites the terminal line), so the expected text is a
            # block rather than one line.
            listed = "comment: " + want.replace("\r\n", "\n").replace("\r", "\n")
            if listed not in lr.stdout.decode("utf-8", "replace"):
                problems.append(f"listing does not print {listed!r}")
        for leftover in files:
            problems.append(f"unexpected output: {leftover!r}")
    return problems, unadjudicated, masked, declared


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract", default=os.path.join(ROOT, "build/san/macextract"))
    ap.add_argument("--all", action="store_true",
                    help="run even not-yet-implemented formats")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1,
                    help="fixtures extracted at once (default: one per CPU). "
                         "Output does not depend on it: the selection pass, "
                         "the grading pass and every line printed stay in "
                         "manifest order.")
    ap.add_argument("--format", help="only fixtures of this lsar format")
    ap.add_argument("--budget", type=int, default=0,
                    help="run under an allocation cap, in bytes: every "
                         "fixture must still come out byte-exact. 565176 is "
                         "what a 1 MB Mac Plus leaves the engine as of "
                         "2026-08-30: FreeMem() at launch, 647,096 B, LESS "
                         "the shell's 80 KB reserve. Do not use the FreeMem "
                         "figure alone; that mistake sat here for weeks "
                         "(BLOCKERS.md). RE-MEASURE it: it falls as the "
                         "application's CODE grows, which is how it went "
                         "stale twice. And it is NOT SUFFICIENT: the Mac "
                         "needs 16-33 KB more than this cap predicts, by a "
                         "margin that is not constant, so passing here does "
                         "not mean it extracts on the machine (FORMATS.md, "
                         "*The Linux budget check under-reads the Mac*).")
    ap.add_argument("--max-size", type=int, default=0,
                    help="only fixtures at most this many bytes. For build "
                         "variants that are correct but slow, where the point "
                         "is to cover a code path rather than the corpus.")
    args = ap.parse_args()

    if not os.path.exists(args.macextract):
        print("diff: no CLI at %s" % args.macextract)
        return 1

    mandir = os.path.join(FIXDIR, "manifests")
    manifests = sorted(f for f in os.listdir(mandir)
                       if f.endswith(".json")) if os.path.isdir(mandir) else []

    ran = passed = skipped_fmt = skipped_missing = 0
    graded_flags = [0]
    ungraded = []
    detect_ran = detect_bad = 0
    over_budget = 0
    unadj_forks = unadj_fixtures = oos_entries = unadj_masked = 0
    fails = []

    # Three passes where there was one loop: SELECT every fixture this run
    # grades, extract them `--jobs` at a time, then grade the results in
    # manifest order. Each fixture was already independent -- check_fixture
    # owns a temporary directory and prints nothing -- so the only shared
    # state that had to go was the Finder-flag counter, now summed per
    # fixture (DECISIONS.md 2026-10-06, *the twenty-four minutes*).
    work = []
    for mf in manifests:
        with open(os.path.join(mandir, mf)) as f:
            man = json.load(f)
        fxpath = os.path.join(FIXDIR, man["fixture"])
        if not os.path.exists(fxpath):
            skipped_missing += 1
            continue
        fmt = man.get("format")
        if args.format and fmt != args.format:
            continue
        if args.max_size and os.path.getsize(fxpath) > args.max_size:
            continue
        if not args.all and fmt not in IMPLEMENTED:
            if fmt in DETECT_ONLY:
                work.append((man, fmt, "detect"))
                continue
            skipped_fmt += 1
            continue
        work.append((man, fmt, "diff"))

    def run_one(item):
        man, fmt, kind = item
        if kind == "detect":
            return check_detect_only(args.macextract,
                                     os.path.join(FIXDIR, man["fixture"]),
                                     DETECT_ONLY[fmt])
        flags = [0]
        return check_fixture(args.macextract, man, args.verbose,
                             args.budget, flags) + (flags[0],)

    with futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        results = list(ex.map(run_one, work))

    for (man, fmt, kind), result in zip(work, results):
        if kind == "detect":
            detect_ran += 1
            bad = result
            if bad:
                detect_bad += 1
                print(f"DETECT FAIL {man['fixture']}")
                for b in bad:
                    print(f"    {b}")
            elif args.verbose:
                print(f"detect ok: {man['fixture']} ({fmt})")
            continue
        ran += 1
        problems, unadj, masked, declared, flags = result
        graded_flags[0] += flags
        for field in declared:
            ungraded.append((man["fixture"], field))
        unadj_masked += masked
        oos_entries += sum(1 for e in man["entries"] if out_of_scope(e))
        if unadj:
            unadj_forks += unadj
            unadj_fixtures += 1
        pinned = args.budget and man["fixture"] in OVER_BUDGET_1MB
        if pinned:
            # Must fail, and must fail for MEMORY — a wrong byte here would
            # otherwise hide behind an expected failure.
            mem = any("memory" in str(p) or "budget" in str(p) for p in problems)
            if not problems:
                fails.append((man["fixture"], ["pinned as over budget, but it "
                                               "PASSED — the list is stale"]))
                print(f"PIN STALE {man['fixture']} ({fmt}) — now fits; "
                      f"remove it from OVER_BUDGET_1MB")
            elif not mem:
                fails.append((man["fixture"], problems))
                print(f"DIFF FAIL {man['fixture']} ({fmt}) — pinned as over "
                      f"budget, but this is not a memory refusal")
                for p in problems[:8]:
                    print(f"    {p}")
            else:
                over_budget += 1
                if args.verbose:
                    print(f"over budget (expected): {man['fixture']} ({fmt})")
            continue
        if problems:
            fails.append((man["fixture"], problems))
            print(f"DIFF FAIL {man['fixture']} ({fmt})")
            for p in problems[:8]:
                print(f"    {p}")
            if len(problems) > 8:
                print(f"    ... {len(problems) - 8} more")
        else:
            passed += 1
            if args.verbose:
                print(f"diff ok: {man['fixture']} ({fmt})")

    cap = f" under a {args.budget} B budget" if args.budget else ""
    cap += f" (fixtures <= {args.max_size} B)" if args.max_size else ""
    print(f"diff{cap}: {passed}/{ran} fixtures ok "
          f"({skipped_fmt} formats pending, {skipped_missing} fixtures absent)")
    if over_budget:
        print(f"  over budget: {over_budget} archive(s) need more than a 1 MB "
              f"Mac Plus has and are refused per entry, as pinned in "
              f"OVER_BUDGET_1MB (FORMATS.md, *Budget*)")
    if detect_ran:
        print(f"  detect-only: {detect_ran - detect_bad}/{detect_ran} named as "
              f"the oracle names them, and refused cleanly")
    else:
        # Said out loud rather than left as a line that stopped
        # printing. LZH was the only detect-only fixture the corpus
        # ever had, and it extracts since 2026-08-23; the formats left
        # in DETECT_ONLY have no specimen here at all (OPEN_ITEMS.md),
        # so this check has nothing to run on and grades nothing.
        print("  detect-only: NO fixture exercises this path — the "
              "formats still in DETECT_ONLY have no specimen in the "
              "corpus (OPEN_ITEMS.md)")
    # No fixture is ever skipped for what OUR engine says about it; an
    # entry the oracle names as out of v1 scope is graded on its name and
    # on anything the engine did produce, and counted here.
    if oos_entries:
        print(f"  {oos_entries} entr(y/ies) the oracle names as compressed "
              f"with a method outside v1 scope: graded on name only")
    # Said out loud, in both directions: the flags are graded only where
    # a manifest records them, and most manifests predate the field
    # (TESTING.md, *The Finder flags*).
    print(f"  Finder flags: {graded_flags[0]} entr(y/ies) compared against "
          f"the oracle's")
    # Printed every run, named fixture by named fixture. The tolerance a
    # fixture rests on is worth exactly as much as the chance of reading
    # it, and a manifest key nobody prints is not read (TESTING.md, *The
    # Finder metadata, and the one field no oracle settles*).
    for fixture, field in ungraded:
        print(f"  DECLARED UNGRADED: {fixture} — {field}: no oracle "
              f"adjudicates them (the manifest says why)")
    print(f"  oracle-unadjudicated: {unadj_forks} fork(s) across "
          f"{unadj_fixtures} fixture(s) — the oracle failed on these, so "
          f"no second implementation adjudicates them byte for byte "
          f"(TESTING.md)")
    if unadj_masked:
        print(f"    of those, {unadj_masked} fork(s) DO agree with a third "
              f"implementation on an emulated Mac, with the resource "
              f"header's OS-stamped bytes 16..127 masked")
    return 1 if (fails or detect_bad) else 0


if __name__ == "__main__":
    sys.exit(main())
