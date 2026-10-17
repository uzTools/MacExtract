#!/usr/bin/env python3
"""Documentation invariants that would otherwise go stale silently.

Eleven of them, all cheap enough to run first in ci.sh:

1. DECISIONS.md's and FORMATS.md's Contents indexes list every `## ` entry,
   in order. An index nobody regenerates is worse than no index, because it
   reads as complete. `--fix` rewrites either from the headings. FORMATS.md
   joined on 2026-08-29, when 753 lines of it turned out to carry no heading
   at all and the one pointer into them was in a table row GitHub drops.
2. No document cites another document by line number. Line numbers drift
   without anyone noticing; CLAUDE.md requires citing the section by name.
   Source files (`foo.c:41`) are fine - only `*.md:NN` is checked.
3. The version agrees in all five places it is written: UNC_VERSION in
   include/macextract.h (the source of truth, which `macextract --version`
   prints), the download section of README.md, the first line of
   dist/README.txt, which make_dist.sh generates from the header, and the
   two 'vers' resources in mac/macextract_icons.r, which are what the
   Finder's Get Info shows and which nothing on this machine reads, and
   the About MacExtract alert's text in mac/macextract_strings.h. That
   constant sat at "0.4.0" through four releases because nothing read it
   and nothing checked it; a reader who sees a stale version on the
   release page now knows the publish step did not run, which is the one
   thing about a release this environment cannot check for itself.
4. Every `synthetic:` fixture in fixtures/SOURCES.md regenerates the exact
   bytes recorded there. `harvest.py --restore` rebuilds those by running
   the script with `-o <path>`, and that path needs a network for every
   other fixture, so it never runs in ci.sh: two of the lines had been
   unrestorable since they were written, because their generators took an
   output DIRECTORY and no `-o` at all (2026-08-15).
5. Every "N bytes on the 68000 target" states sizeof(UncEntryInfo) as the
   target compiler reports it. That figure is the whole argument for
   capping a name at UNC_NAME_MAX, and it read 296 for a week while the
   struct was 298: it had been measured hours before the struct's last
   field was added (DECISIONS.md 2026-09-03).
6. No figure is left as an unfilled `@PO@` placeholder.
7. dist/README.txt is what make_dist.sh's heredoc currently writes. It is
   the release notes verbatim and it is generated, so prose edited in the
   script reaches the download page only when somebody re-runs it. The
   BINARY beside it is ci.sh's job, which a docs-only change does not run.
8. The five figures CLAUDE.md advertises for the session-start reading
   are what those documents currently weigh. The total was "7.5k
   tokens" from 2026-08-26 to 2026-09-26 while the files under it
   doubled, and the pass that re-measured it left the next figure in
   the same sentence — BLOCKERS' withdrawn-claims archive, quoted at
   15k while it was ~42k — untouched (BLOCKERS.md, *Withdrawn claims*).
   A reader uses these to decide what to open, so a figure a quarter of
   the truth is worse than none.
9. The number of smells BLOCKERS.md claims, in BLOCKERS.md and in
   CLAUDE.md, is the number of bullets in the list. Three corrections of
   one count is where it becomes a check: ten over a list of thirty
   (2026-09-26), ten in CLAUDE.md before that, and thirty-three over
   thirty-five hours after the second fix. A count written above a list
   is the cheapest claim here to check and the least likely to be
   checked, because the list grows one row at a time and no row is ever
   the one that breaks the number.
10. The figures derived from the CORPUS: how big the differential and
   robustness suites are (CLAUDE.md, PROGRESS.md) and how big a
   population the two sniff sweeps claim 0 false positives over
   (FORMATS.md, TESTING.md). Counted the way the harnesses count — the
   manifests, ten variants of each implemented one, and every non-.md
   file in fixtures/ — because both figures drifted the day two fixtures
   arrived: "9,490 robustness variants" against 9,510, and "955 corpus
   files" against 963. Derived prose with nothing deriving it is the
   same shape as check 8 and check 9, and the third time was 2026-10-06
   (TESTING.md, *Documentation invariants*).
11. DECISIONS.md's entry dates are non-decreasing and none is in the
   future. The date is half of every citation this repository makes, and
   22 references across ten files were written a day ahead once.
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEXED = ("DECISIONS.md", "FORMATS.md")
INDEX_HEAD = "## Contents\n"
MD_LINE_CITE = re.compile(r"\b[A-Za-z_][\w./-]*\.md:\d+")


def entries(text):
    return [l[3:].strip() for l in text.split("\n")
            if l.startswith("## ") and l[3:].strip() != "Contents"]


def indexed(text):
    body = text.split(INDEX_HEAD, 1)[1].split("\n---\n", 1)[0]
    return [l[2:].strip() for l in body.split("\n") if l.startswith("- ")]


def check_one_index(name, fix):
    path = ROOT / name
    text = path.read_text()
    want, have = entries(text), indexed(text)
    if want == have:
        return []
    if fix:
        head, rest = text.split(INDEX_HEAD, 1)
        preamble, tail = rest.split("\n---\n", 1)
        keep = "\n".join(l for l in preamble.split("\n")
                         if l and not l.startswith("- "))
        body = "\n".join(f"- {e}" for e in want)
        path.write_text(f"{head}{INDEX_HEAD}{keep}\n\n{body}\n\n---\n{tail}")
        print(f"check_docs: rewrote {name} index ({len(want)} entries)")
        return []
    missing = [e for e in want if e not in have]
    extra = [e for e in have if e not in want]
    out = [f"{name}: Contents index is out of date "
           "(run tools/check_docs.py --fix)"]
    out += [f"  not indexed: {e}" for e in missing]
    out += [f"  indexed but gone: {e}" for e in extra]
    if not missing and not extra:
        out.append("  same entries, wrong order")
    return out


def check_index(fix):
    return [p for name in INDEXED for p in check_one_index(name, fix)]


VERSION_RE = re.compile(r'#define UNC_VERSION "([0-9][^"]*)"')
VERS_RE = re.compile(r"resource 'vers' \((\d+)[^)]*\)\s*\{(.*?)\};",
                     re.DOTALL)


def check_version():
    """UNC_VERSION, README.md's download section, dist/README.txt's first
    line and the Macintosh 'vers' resources must agree."""
    bad = []
    header = (ROOT / "include" / "macextract.h").read_text()
    m = VERSION_RE.search(header)
    if not m:
        return ["include/macextract.h: no UNC_VERSION"]
    ver = m.group(1)

    readme = (ROOT / "README.md").read_text()
    if f"**v{ver}**" not in readme:
        bad.append(f"README.md does not state the current version (**v{ver}**)")

    dist = ROOT / "dist" / "README.txt"
    if dist.exists():
        first = dist.read_text().splitlines()[0]
        if f"v{ver}" not in first:
            bad.append(f"dist/README.txt says {first!r}, not v{ver} — "
                       f"run tools/make_dist.sh")

    # The 'vers' resources are what the Finder's Get Info shows, and nothing
    # in the application reads them — so a stale one is invisible on this
    # machine and wrong on every Macintosh. Both strings of both resources
    # are held against UNC_VERSION; the numeric bytes are not, because the
    # field cannot express a minor of 29 (mac/macextract_icons.r).
    rez = ROOT / "mac" / "macextract_icons.r"
    found = 0
    for rid, body in VERS_RE.findall(rez.read_text()):
        found += 1
        strs = re.findall(r'"([^"]*)"', body)
        if len(strs) != 2:
            bad.append(f"mac/macextract_icons.r: 'vers' ({rid}) has "
                       f"{len(strs)} strings, expected 2")
            continue
        short, long_ = strs
        if short != ver:
            bad.append(f"mac/macextract_icons.r: 'vers' ({rid}) short string "
                       f"is {short!r}, not {ver!r}")
        if ver not in long_:
            bad.append(f"mac/macextract_icons.r: 'vers' ({rid}) long string "
                       f"is {long_!r}, which does not carry {ver!r}")
        # Byte 2, the minor written as two hex digits that read as the
        # number (the comment above the resources). It sat at 0x31 through
        # v0.34.0 and at 0x35 through v0.37.0, each time with a comment
        # saying it now moves with the strings.
        nums = re.findall(r"0x([0-9A-Fa-f]{2})", body)
        minor = ver.split(".")[1]
        if len(minor) <= 2 and (len(nums) < 2
                                or nums[1].lstrip("0") != minor.lstrip("0")):
            bad.append(f"mac/macextract_icons.r: 'vers' ({rid}) byte 2 is "
                       f"0x{nums[1] if len(nums) > 1 else '??'}, not "
                       f"0x{int(minor):02d}")
    if found != 2:
        bad.append(f"mac/macextract_icons.r: {found} 'vers' resources, "
                   f"expected 2 (ids 1 and 2)")

    # About MacExtract writes the number into its own DITL rather than
    # reading 'vers' 1, which cost 32 B of code and A5 (DECISIONS.md
    # 2026-10-12, *the application nobody could leave*).
    about = re.search(r'"MacExtract ([^"]*)"',
                      (ROOT / "mac" / "macextract_strings.h").read_text())
    if not about or about.group(1) != ver:
        bad.append("mac/macextract_strings.h: the About alert says "
                   f"{about.group(1) if about else 'nothing'!r}, not {ver!r}")
    return bad


def check_citations():
    out = []
    for path in sorted(ROOT.glob("*.md")) + sorted(ROOT.glob("tools/**/*.md")):
        for n, line in enumerate(path.read_text().split("\n"), 1):
            for hit in MD_LINE_CITE.findall(line):
                out.append(f"{path.relative_to(ROOT)}:{n}: cites {hit} by line "
                           "number; cite the section by name")
    return out


PLACEHOLDER = re.compile(r"@[A-Z][A-Z0-9]{1,7}@")


DIST_HEREDOC = re.compile(r"cat > dist/README\.txt <<TXT\n(.*?)\nTXT\n", re.S)


def check_dist_readme():
    """dist/README.txt is the release notes verbatim (CLAUDE.md, *Cutting a
    release*) and is GENERATED, so an edit to the prose inside make_dist.sh
    reaches it only when somebody re-runs the script. The heredoc expands
    exactly one thing, $VERSION, and nothing else — so re-rendering it here
    is the whole check. ci.sh's stale-dist check covers the BINARY and does
    not run on a docs-only change; this one does."""
    dist = ROOT / "dist" / "README.txt"
    if not dist.exists():
        return []
    script = (ROOT / "tools" / "make_dist.sh").read_text()
    m = DIST_HEREDOC.search(script)
    if not m:
        return ["tools/check_docs.py: cannot find make_dist.sh's "
                "dist/README.txt heredoc — this check has stopped checking"]
    ver = VERSION_RE.search((ROOT / "include" / "macextract.h").read_text())
    if not ver:
        return []                       # check_version() reports this
    want = m.group(1).replace("$VERSION", ver.group(1)).split("\n")
    have = dist.read_text().rstrip("\n").split("\n")
    if want == have:
        return []
    for n, (a, b) in enumerate(zip(want, have), 1):
        if a != b:
            return [f"dist/README.txt line {n} is {b!r}, make_dist.sh says "
                    f"{a!r} — run: sh tools/make_dist.sh"]
    return [f"dist/README.txt has {len(have)} lines, make_dist.sh writes "
            f"{len(want)} — run: sh tools/make_dist.sh"]


def check_placeholders():
    """A figure left as `@PO@` reads as a typo and not as a hole, and one
    sat in FORMATS.md's decode-cost list from 2026-09-19 to 2026-09-20
    with the numbers it wanted already written out in DECISIONS.md. Six
    of them in one sentence, and nothing in this file looked."""
    out = []
    for path in sorted(ROOT.glob("*.md")) + sorted(ROOT.glob("tools/**/*.md")):
        for n, line in enumerate(path.read_text().split("\n"), 1):
            for hit in PLACEHOLDER.findall(line):
                out.append(f"{path.relative_to(ROOT)}:{n}: {hit} is an "
                           "unfilled placeholder; write the number or "
                           "delete the claim")
    return out


SYNTH_RE = re.compile(r"^\|\s*(\S+)\s*\|\s*([0-9a-f]{64})\s*\|\s*(\d+)\s*\|"
                      r"\s*synthetic:(.+?)\s*\|")


def check_synthetic():
    """Every `synthetic:` line in fixtures/SOURCES.md must regenerate the
    bytes it records. harvest.py restores those fixtures by running the
    script with `-o <path>`, so a script that does not accept `-o`, or
    one that has since changed what it writes, leaves a corpus entry that
    cannot be rebuilt — and nothing else would say so, because the
    restore path needs a network and never runs in ci.sh."""
    src = ROOT / "fixtures" / "SOURCES.md"
    if not src.exists():
        return []
    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        for line in src.read_text().split("\n"):
            m = SYNTH_RE.match(line)
            if not m:
                continue
            name, want, size, cmd = m.groups()
            out = os.path.join(tmp, name)
            argv = [sys.executable, str(ROOT / cmd.split()[0])] + \
                cmd.split()[1:] + ["-o", out]
            r = subprocess.run(argv, capture_output=True)
            # Exit 3 is the one generator that can be legitimately
            # unable to run: tools/get_lhasa_fixture.py needs either
            # reference/lhasa or a network, and a fresh offline clone
            # has neither. Reported out loud, never silently passed.
            if r.returncode == 3:
                print(f"check_docs: {name}: generator unavailable here "
                      f"({r.stderr.decode().strip()[:80]}) — row not checked")
                continue
            if r.returncode != 0 or not os.path.exists(out):
                bad.append(f"fixtures/SOURCES.md: {name} cannot be restored "
                           f"({cmd} -o ... exited {r.returncode})")
                continue
            blob = open(out, "rb").read()
            got = hashlib.sha256(blob).hexdigest()
            if got != want or len(blob) != int(size):
                bad.append(f"fixtures/SOURCES.md: {name} regenerates as "
                           f"{len(blob)} B / {got[:12]}…, recorded as "
                           f"{size} B / {want[:12]}…")
    return bad


TARGET_SIZE_RE = re.compile(r"(\d+) bytes on the\s+68000 target")
PROBE_C = ('#include "macextract.h"\n'
           "char unc_probe_entryinfo[sizeof(UncEntryInfo)];\n")
PROBE_SIZE_RE = re.compile(r"\.size\s+unc_probe_entryinfo,\s*(\d+)")


def m68k_cc():
    """The Retro68 compiler, located the way tools/build_mac.sh locates
    it, else any m68k gcc. What the number is about is the ABI — 2-byte
    alignment — and the two agree on it, so a machine with only the
    Debian cross-compiler still checks something real."""
    r = os.environ.get("RETRO68")
    for c in ([os.path.join(r, "bin", "m68k-apple-macos-gcc")] if r else []) + \
            ["m68k-apple-macos-gcc",
             "/opt/Retro68-build/toolchain/bin/m68k-apple-macos-gcc",
             "m68k-linux-gnu-gcc"]:
        if os.sep in c:
            if os.path.exists(c):
                return c
        elif shutil.which(c):
            return c
    return None


def check_target_struct():
    """sizeof(UncEntryInfo) on the target, measured rather than
    remembered. The struct is quoted by size in FORMATS.md and in a
    comment in src/fmt_lzh.c, because its inline 256-byte name buffer is
    why a name is capped at UNC_NAME_MAX instead of carrying zip's
    65,535 — and a size is exactly the kind of figure that goes wrong
    when the struct next gains a field."""
    cc = m68k_cc()
    stated = []
    for path in sorted(ROOT.glob("*.md")) + sorted(ROOT.glob("src/*.c")) + \
            sorted(ROOT.glob("cli/*.c")) + sorted(ROOT.glob("mac/*.c")) + \
            sorted(ROOT.glob("include/*.h")):
        # Whitespace-normalised: the sentence is line-wrapped in the docs
        # and in the comment, and both wraps fall inside the phrase.
        text = " ".join(path.read_text().split())
        for hit in TARGET_SIZE_RE.findall(text):
            stated.append((path.relative_to(ROOT), int(hit)))
    if not stated:
        return []
    if cc is None:
        print("check_docs: no m68k compiler here — "
              f"{len(stated)} target-size claims not checked")
        return []
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "probe.c")
        with open(src, "w") as f:
            f.write(PROBE_C)
        r = subprocess.run([cc, "-I", str(ROOT / "include"), "-Os", "-S",
                            "-o", "-", src], capture_output=True)
        m = PROBE_SIZE_RE.search(r.stdout.decode(errors="replace"))
        if r.returncode != 0 or not m:
            return [f"check_docs: {cc} could not size UncEntryInfo "
                    f"(exit {r.returncode})"]
        size = int(m.group(1))
    return [f"{path}: says UncEntryInfo is {n} bytes on the 68000 target; "
            f"{os.path.basename(cc)} says {size}"
            for path, n in stated if n != size]


# ---------------------------------------------------------------- sizes
#
# Tokens are not counted here — no tokenizer is installed and none is
# wanted for this. The proxy is FOUR CHARACTERS PER TOKEN, which is what
# reproduces the 2026-09-26 measurement of the session-start reading
# (54,914 characters, advertised as ~14k), and the figures in CLAUDE.md
# are held to it. The tolerance is generous on purpose: this check exists
# to catch a figure that has DOUBLED, not to make every docs edit an
# arithmetic exercise.
CHARS_PER_TOKEN = 4.0
SIZE_SLACK_K = 0.5          # absolute, for the small rounded figures
SIZE_SLACK_FRAC = 0.25      # relative, for the big ones

WITHDRAWN_HEAD = "## Withdrawn claims\n"

K = r"\**~?([\d.]+)k"

SIZE_CLAIMS = (
    # regex over CLAUDE.md, what it measures, how to say it
    # `K` allows the bolding and the tilde these figures are written with,
    # so that emphasising one does not silently stop it being checked.
    (r"session-start reading is " + K, "total", "the three files together"),
    (r"\bPROGRESS " + K, "PROGRESS.md", "PROGRESS.md"),
    (r"\bOPEN_ITEMS " + K, "OPEN_ITEMS.md", "OPEN_ITEMS.md"),
    (r"BLOCKERS' first two sections " + K, "blockers-head",
     "BLOCKERS.md down to *Withdrawn claims*"),
    (r"withdrawn-claims archive is another " + K, "blockers-archive",
     "BLOCKERS.md's withdrawn-claims archive"),
)


def _measured_sizes():
    """Characters, per the five figures CLAUDE.md quotes."""
    blockers = (ROOT / "BLOCKERS.md").read_text()
    cut = blockers.index(WITHDRAWN_HEAD)
    head, archive = blockers[:cut], blockers[cut:]
    out = {
        "PROGRESS.md": len((ROOT / "PROGRESS.md").read_text()),
        "OPEN_ITEMS.md": len((ROOT / "OPEN_ITEMS.md").read_text()),
        "blockers-head": len(head),
        "blockers-archive": len(archive),
    }
    out["total"] = (out["PROGRESS.md"] + out["OPEN_ITEMS.md"] +
                    out["blockers-head"])
    return out


def check_doc_sizes():
    """What it cannot see: whether the reading is worth its size — only
    what it weighs; and, being a proxy rather than a tokenizer, a drift
    smaller than the slack above. It catches a figure that has doubled,
    which is the only way this one has ever been wrong."""
    text = (ROOT / "CLAUDE.md").read_text()
    have = _measured_sizes()
    out = []
    for pattern, key, shown in SIZE_CLAIMS:
        m = re.search(pattern, text)
        if not m:
            out.append("CLAUDE.md: no figure matching %r — this check has "
                       "stopped checking %s" % (pattern, shown))
            continue
        said = float(m.group(1))
        real = have[key] / CHARS_PER_TOKEN / 1000.0
        if abs(said - real) > max(SIZE_SLACK_K, SIZE_SLACK_FRAC * real):
            out.append("CLAUDE.md: says %s is %gk tokens; %s is %s "
                       "characters, %.1fk at %g per token"
                       % (shown, said, shown, "{:,}".format(have[key]),
                          real, CHARS_PER_TOKEN))
    return out


# ------------------------------------------------- figures derived from one
# What this catches, and why a grep could not: `OVL_SAVED` is quoted in
# FORMATS.md three times in three different sentences, and EVERY per-format
# budget in *What each format is granted* is derived from it. On 2026-10-02
# all of them were stale — the constant had moved twice (117,664 -> 119,680
# in 527bfe0, then -> 123,776 for `src/sit_ccube.c`) and the prose had moved
# neither time. It was invisible to a search for the literal number because
# the prose figure was never the same literal: it read 117,328 against a
# constant of 117,664, a related-but-different quantity, which is exactly how
# one goes stale while still looking plausible.
#
# So this holds the PROSE against the constant the model actually computes
# with. The number nothing measures is the one nobody can correct
# (DECISIONS.md 2026-10-02, *C-Cube's JPEG is in the engine*).
#
# What it cannot see: the twelve per-format rows themselves. They are
# `run_tiers.gain()` of a set of images, and nothing here recomputes them —
# re-take them from that function, which is what produced them.
DERIVED = [
    (r"the ([\d,]+) B of `CODE` and A5 the shipped build does not carry",
     "OVL_SAVED", "what the release leaves, in *What each format is granted*"),
    (r"The shipped pair is \*\*([\d,]+) B\*\*",
     "OVL_SAVED", "the shipped pair, under the probe-build table"),
    (r"([\d,]+) B held against ([\d,]+) B saved",
     "BUNDLE,OVL_SAVED", "the envelope row's own arithmetic"),
]


def _run_tiers_consts():
    text = (ROOT / "tools" / "run_tiers.py").read_text()
    out = {}
    for name in ("OVL_SAVED", "BUNDLE"):
        m = re.search(r"^%s = (-?\d+)" % name, text, re.M)
        if m:
            out[name] = int(m.group(1))
    return out


def _n(s):
    return int(s.replace(",", "").replace("\u202f", ""))


def check_derived_figures(text=None):
    consts = _run_tiers_consts()
    missing = [k for k in ("OVL_SAVED", "BUNDLE") if k not in consts]
    if missing:
        return ["tools/run_tiers.py: no %s — check_docs has stopped "
                "checking the figures derived from it" % ", ".join(missing)]
    if text is None:
        text = (ROOT / "FORMATS.md").read_text()
    out = []
    for pattern, keys, shown in DERIVED:
        m = re.search(pattern, text)
        if not m:
            out.append("FORMATS.md: no sentence matching %r — this check "
                       "has stopped checking %s" % (pattern, shown))
            continue
        for got, key in zip(m.groups(), keys.split(",")):
            if _n(got) != consts[key]:
                out.append("FORMATS.md says %s for %s; tools/run_tiers.py "
                           "computes with %s = %s. Every per-format budget "
                           "in *What each format is granted* is derived from "
                           "it, so correct the table in the same commit "
                           "(from run_tiers.gain(), not by hand)."
                           % (got, shown, key, "{:,}".format(consts[key])))

    # And the bundle's own three terms, which must close: the index is the
    # difference, and it does not depend on how big an image is.
    m = re.search(r"The bundle is \*\*([\d,]+) B\*\* — the \w+ images "
                  r"sum to ([\d,]+) B, so its\nindex costs \*\*([\d,]+) B\*\*",
                  text)
    if not m:
        out.append("FORMATS.md: no bundle/images/index sentence — this "
                   "check has stopped checking the bundle's arithmetic")
    else:
        bundle, images, index = (_n(g) for g in m.groups())
        if bundle != consts["BUNDLE"]:
            out.append("FORMATS.md says the bundle is %s B; "
                       "tools/run_tiers.py computes with BUNDLE = %s"
                       % ("{:,}".format(bundle),
                          "{:,}".format(consts["BUNDLE"])))
        if images + index != bundle:
            out.append("FORMATS.md: the bundle's terms do not close — "
                       "%s B of images plus %s B of index is %s, not %s"
                       % ("{:,}".format(images), "{:,}".format(index),
                          "{:,}".format(images + index),
                          "{:,}".format(bundle)))
    return out


def selftest_derived():
    """Establish that it can fail: perturb each figure and require a report."""
    text = (ROOT / "FORMATS.md").read_text()
    consts = _run_tiers_consts()
    caught = 0
    for name in ("OVL_SAVED", "BUNDLE"):
        bent = text.replace("{:,}".format(consts[name]),
                            "{:,}".format(consts[name] + 64))
        if bent != text and check_derived_figures(bent):
            caught += 1
    return caught


# --------------------------------------------------------------- counts
WORDS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
         "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
         "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
        "seventy": 70, "eighty": 80, "ninety": 90}
UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9}


def _word_number(w):
    w = w.lower()
    if w in WORDS:
        return WORDS[w]
    if w in TENS:
        return TENS[w]
    if "-" in w:
        a, b = w.split("-", 1)
        if a in TENS and b in UNITS:
            return TENS[a] + UNITS[b]
    return None


SMELL_CLAIMS = (
    ("BLOCKERS.md", r"\*\*([A-Za-z-]+)\*\* mechanisms keep finding"),
    ("CLAUDE.md", r"names the ([A-Za-z-]+) smells"),
)


def check_smell_count():
    """The count above the list is the list's length. Counted from the
    list itself: `- ` bullets between the *Withdrawn claims* heading and
    the table of claims that follows it.

    What it cannot see: a mechanism written into the body of another
    bullet, which is a bullet's worth of content and not a bullet; and
    two bullets that describe the same mechanism twice, which would make
    the number right and the list wrong."""
    blockers = (ROOT / "BLOCKERS.md").read_text()
    cut = blockers.index(WITHDRAWN_HEAD)
    table = blockers.index("\n| claim |", cut)
    n = sum(1 for l in blockers[cut:table].split("\n") if l.startswith("- "))
    out = []
    for name, pattern in SMELL_CLAIMS:
        text = (ROOT / name).read_text()
        m = re.search(pattern, text.replace("\n", " "))
        if not m:
            out.append("%s: no smell count matching %r — this check has "
                       "stopped checking" % (name, pattern))
            continue
        said = _word_number(m.group(1))
        if said is None:
            out.append("%s: %r is not a number this check can read"
                       % (name, m.group(1)))
        elif said != n:
            out.append("%s: says %s (%d) smells; BLOCKERS.md's list has %d"
                       % (name, m.group(1), said, n))
    return out


# ------------------------------------------------- the corpus's own figures
# Two figures are DERIVED from the corpus and were written by hand, so both
# went stale the day two fixtures arrived: CLAUDE.md and PROGRESS.md carried
# "9,490 robustness variants" against a suite of 951 (ci.sh prints 9,510),
# and FORMATS.md carried a sniff sweep over "955 corpus files" when there
# were 963. Neither is measurable from the prose, so neither could fail
# until now (BLOCKERS.md; DECISIONS.md 2026-10-06).
#
# Counted the way the harnesses themselves count, not by a rule of thumb:
# the differential suite is the manifests (tools/run_diff.py), the
# robustness suite is ten variants of each manifest whose format is
# implemented and whose fixture is present (tools/run_robustness.py,
# `variants`: four truncations and six bit-flips), and the sniff sweeps
# walk every file in fixtures/ that is not a .md (tools/run_foreign.py).
CORPUS_FIGURES = [
    ("CLAUDE.md", r"a \*\*([\d,]+)-fixture\*\* differential suite", "manifests",
     "the differential suite's size"),
    ("CLAUDE.md", r"plus ([\d,]+) robustness variants", "robust",
     "the robustness suite's size"),
    ("PROGRESS.md", r"\*\*The suite is ([\d,]+) fixtures\*\*", "manifests",
     "the differential suite's size"),
    # Anchored: "9,320 robustness variants clean" is the NAME of a
    # BLOCKERS.md section this file cites, and a withdrawn claim's title
    # is not a figure to correct.
    ("PROGRESS.md", r"`macunpack`; ([\d,]+) robustness variants clean",
     "robust", "the robustness suite's size"),
    ("FORMATS.md", r"0 false positives in ([\d,]+) corpus files", "files",
     "the foreign-format sweep's population"),
    ("FORMATS.md", r"exactly the \d+ of ([\d,]+) corpus files", "files",
     "the AppleLink sweep's population"),
    ("TESTING.md", r"the corpus is ([\d,]+) files", "files",
     "the sniff-I/O probe's population"),
]


# The same three counts, scanned as a CLASS rather than at seven named
# sentences. Naming them was the first design and it missed six: two
# stale denominators, three claims that had stopped being true when the
# Mac OS 9 tier's fixtures landed, and one table cell — none of which
# were among the seven (DECISIONS.md 2026-10-07, *the seven sentences
# that were not the class*).
#
# A window per kind, so that what is matched is a CORPUS-SIZE claim and
# not a year ("the 1993 fixture's Huffman-only block") or a per-format
# count ("115 fixtures" of the DiskDoubler corpus).
CORPUS_WINDOW = {"manifests": (900, 1200), "robust": (9000, 12000),
                 "files": (900, 1200)}
CORPUS_SCAN = ("CLAUDE.md", "PROGRESS.md", "OPEN_ITEMS.md", "FORMATS.md",
               "TESTING.md")
# BLOCKERS.md is deliberately NOT scanned: every row in it is a
# withdrawn claim with the corpus size it was measured against, and a
# withdrawal's figures are the point of the row.
#
# Each entry below is a figure that is HISTORICAL — it states what the
# corpus was when some measurement was taken, and the claim it carries
# is dated with it. Anything in the window that is neither today's count
# nor declared here FAILS, so a new sentence quoting an old count has to
# be looked at.
CORPUS_HISTORICAL = {
    # One entry per (file, kind, figure); it covers every occurrence of
    # that figure in that file. Each was read before it was declared.
    ("FORMATS.md", "files", 983):
        "two sweeps dated in their sentences: btoa's probe over the corpus "
        "on 2026-10-11, and the AppleLink sniffer's 6 of 983, re-measured "
        "2026-10-08",
    ("TESTING.md", "files", 983):
        "MIME's sniff over the corpus, dated 2026-10-11 in the sentence",
    ("TESTING.md", "manifests", 971):
        "the short-read lane's 1 B, 3 and 7 caps on the fixed build of "
        "2026-10-09, an experiment and not the lane's own re-run",
    ("TESTING.md", "manifests", 959):
        "the read-cap lane's bend of 2026-10-09, unc_read_full made to "
        "give up on a short read; an experiment, not a re-run lane",
    ("PROGRESS.md", "robust", 9320):
        "the NAME of a BLOCKERS.md section, cited; a withdrawn claim's "
        "title is not a figure to correct",
    ("OPEN_ITEMS.md", "manifests", 933):
        "the MacBinary 0xA001 fallback, measured 2026-09-28 and dated "
        "in the sentence",
    ("OPEN_ITEMS.md", "robust", 9330):
        "the same 2026-09-28 measurement",
    ("FORMATS.md", "manifests", 903):
        "`lsar -j`'s XADIsEncrypted sweep, 2026-08-23, beside the "
        "2026-10-05 re-run in the same sentence",
    ("FORMATS.md", "manifests", 937):
        "the largest zip in the corpus (2026-08-25) and the suite size "
        "the overlay trade was argued against; both claims are dated",
    ("FORMATS.md", "manifests", 948):
        "the fixtures compared byte-identical against the previous "
        "binary on that day's build",
    ("FORMATS.md", "manifests", 929):
        "the population the MacBinary-probe-first measurement was taken "
        "over, 2026-08-24",
    ("FORMATS.md", "robust", 9320):
        "the truncation work of 2026-08-29, and BLOCKERS.md's section "
        "name twice",
    ("FORMATS.md", "files", 955):
        "the sniff-I/O probe's population, measured 2026-10-05 and "
        "stated as such in the table",
    ("TESTING.md", "robust", 9490):
        "quoted as the figure that WAS wrong, in the write-up of the "
        "check that caught it",
    ("TESTING.md", "files", 955):
        "the same write-up, quoting what three sentences said",
    ("TESTING.md", "robust", 9320):
        "BLOCKERS.md's section name, and the 2026-08-29 run",
    ("TESTING.md", "manifests", 943):
        "four dated statements about earlier runs: the hex form, the "
        "largest zip, the longest name, and the envelope sweep",
    ("TESTING.md", "manifests", 932):
        "the 2026-09-22 fork tally and the truncation suite's own count "
        "on that day",
    ("TESTING.md", "manifests", 950):
        "approximate, '~950 fixtures', in the fuzz-weight arithmetic",
    ("TESTING.md", "manifests", 933):
        "the suite size when variant 1 and the no-fork lane were "
        "written up",
    ("TESTING.md", "manifests", 928):
        "the AppleLink false-positive figure that stood until "
        "2026-09-27, quoted as withdrawn",
}


def _corpus_counts():
    """manifests, robustness variants and corpus files, or None if the
    fixtures are not on this disk (a docs-only checkout)."""
    fixdir = ROOT / "fixtures"
    mandir = fixdir / "manifests"
    if not mandir.is_dir():
        return None
    mans = sorted(mandir.glob("*.json"))
    files = [f for f in fixdir.iterdir()
             if f.is_file() and f.suffix != ".md"]
    if not mans or not files:
        return None
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from run_diff import IMPLEMENTED
    except Exception as exc:                        # pragma: no cover
        return ("no IMPLEMENTED from tools/run_diff.py (%s)" % exc)
    rob = 0
    for mf in mans:
        man = json.loads(mf.read_text())
        if man.get("format") in IMPLEMENTED \
                and (fixdir / man["fixture"]).exists():
            rob += 1
    return {"manifests": len(mans), "robust": rob * 10, "files": len(files)}


def check_corpus_figures(counts=None):
    if counts is None:
        counts = _corpus_counts()
    if counts is None:
        return []                      # no fixtures here: nothing to derive
    if isinstance(counts, str):
        return ["check_docs: %s — the corpus figures are unchecked" % counts]
    out = []
    for name, pattern, key, shown in CORPUS_FIGURES:
        text = (ROOT / name).read_text()
        m = re.search(pattern, text)
        if not m:
            out.append("%s: no sentence matching %r — this check has "
                       "stopped checking %s" % (name, pattern, shown))
            continue
        if _n(m.group(1)) != counts[key]:
            out.append("%s says %s for %s; the corpus has %s. Re-take it "
                       "rather than editing the number: ./ci.sh prints both "
                       "suite sizes, and the sweep populations are every "
                       "file in fixtures/ (CLAUDE.md, *Writing things down*)."
                       % (name, m.group(1), shown,
                          "{:,}".format(counts[key])))
    return out


def selftest_corpus():
    """Establish that it can fail: bend each count and require a report."""
    counts = _corpus_counts()
    if counts is None or isinstance(counts, str):
        return None
    caught = 0
    for key in ("manifests", "robust", "files"):
        bent = dict(counts)
        bent[key] += 1
        if check_corpus_figures(bent):
            caught += 1
    return caught


# --------------------------------------------- DECISIONS.md's dates are keys
# Every citation in this repository names an entry by its DATE and title
# ("DECISIONS.md 2026-10-06, *the sort that dropped what it could not
# hold*"), and the file is oldest-first. So a wrong date is a wrong
# citation, silently: 22 references across ten files were written a day
# AHEAD on 2026-10-06 — two entry headers, their index lines, four source
# comments and a BLOCKERS row — which also put one entry in front of nine
# that preceded it (DECISIONS.md 2026-10-06, *the spelling the tables did
# not have*).
#
# What it cannot see: a date that is wrong but neither in the future nor
# out of order, which is the one shape left. The clock is the authority
# here, so a future date fails loudly rather than being tolerated — if the
# machine's clock is what is wrong, that is worth knowing before a commit
# carries it.
def _decision_dates():
    out = []
    for i, line in enumerate((ROOT / "DECISIONS.md").read_text().split("\n")):
        m = re.match(r"## (\d{4}-\d{2}-\d{2})", line)
        if m:
            out.append((m.group(1), line[:72]))
    return out


def check_corpus_class(counts=None):
    """Every corpus-size claim in the status files, not seven of them."""
    if counts is None:
        counts = _corpus_counts()
    if counts is None or isinstance(counts, str):
        return []
    rx = re.compile(r"([\d,]{3,})[- ](fixtures?|robustness variants|"
                    r"corpus files|corpus fixtures|corpus archives)\b")
    rx2 = re.compile(r"corpus is ([\d,]{3,}) files")
    def kindof(word):
        if word.startswith("fixture"):
            return "manifests"
        if word.startswith("robust"):
            return "robust"
        return "files"
    out = []
    for name in CORPUS_SCAN:
        for lineno, line in enumerate(
                (ROOT / name).read_text().split("\n"), 1):
            hits = [(m.group(1), kindof(m.group(2))) for m in rx.finditer(line)]
            hits += [(m.group(1), "files") for m in rx2.finditer(line)]
            for shown, kind in hits:
                n = _n(shown)
                lo, hi = CORPUS_WINDOW[kind]
                if not (lo <= n <= hi) or n == counts[kind]:
                    continue
                if (name, kind, n) in CORPUS_HISTORICAL:
                    continue
                out.append(
                    "%s:%d says %s for a corpus of %s. Either it is today's "
                    "figure — re-take it, do not edit it — or it is a "
                    "historical one, in which case say WHEN it was measured "
                    "and add it to CORPUS_HISTORICAL in this file with that "
                    "reason. Six were wrong when this check was written as "
                    "seven named sentences instead of a scan."
                    % (name, lineno, shown, "{:,}".format(counts[kind])))
    return out


def selftest_corpus_class():
    """Establish that it can fail: a planted stale figure must report."""
    counts = _corpus_counts()
    if counts is None or isinstance(counts, str):
        return None
    bent = dict(counts)
    for kind in ("manifests", "robust", "files"):
        bent[kind] = counts[kind] + 3      # every live figure now "stale"
    return 1 if check_corpus_class(bent) else 0


def check_decision_dates(dates=None, today=None):
    if dates is None:
        dates = _decision_dates()
    if today is None:
        today = datetime.date.today().isoformat()
    out = []
    if not dates:
        return ["DECISIONS.md: no dated `## ` entry — this check has stopped "
                "checking the dates"]
    for (d, head), (nd, nhead) in zip(dates, dates[1:]):
        if nd < d:
            out.append("DECISIONS.md: %s comes after %s — the file is "
                       "oldest-first and every citation names an entry by its "
                       "date (%s)" % (nd, d, nhead))
    for d, head in dates:
        if d > today:
            out.append("DECISIONS.md: %s is in the FUTURE (today is %s) — a "
                       "date is a citation key, so fix the entry, its Contents "
                       "line and every file that cites it; if the clock is what "
                       "is wrong, fix that first (%s)" % (d, today, head))
    return out


def selftest_dates():
    """Establish that it can fail: one date out of order, one ahead."""
    dates = _decision_dates()
    if len(dates) < 2:
        return None
    caught = 0
    bent = list(dates)
    bent[-1] = ("1999-01-01", bent[-1][1])
    if check_decision_dates(bent):
        caught += 1
    bent = list(dates)
    bent[-1] = ("2999-01-01", bent[-1][1])
    if check_decision_dates(bent):
        caught += 1
    return caught


def main():
    fix = "--fix" in sys.argv[1:]
    problems = (check_index(fix) + check_citations() + check_version() +
                check_synthetic() + check_target_struct() +
                check_placeholders() + check_dist_readme() +
                check_doc_sizes() + check_smell_count() +
                check_derived_figures() + check_corpus_figures() +
                check_corpus_class() + check_decision_dates())
    caught = selftest_derived()
    if caught != 2:
        problems.append("check_docs: the derived-figure selftest bent two "
                        "figures and %d were caught — it cannot fail, so it "
                        "is not checking them" % caught)
    caught = selftest_corpus()
    if caught is not None and caught != 3:
        problems.append("check_docs: the corpus-figure selftest bent three "
                        "counts and %d were caught — it cannot fail, so it "
                        "is not checking them" % caught)
    caught = selftest_corpus_class()
    if caught is not None and caught != 1:
        problems.append("check_docs: the corpus-class selftest moved every "
                        "count and nothing was reported — it cannot fail, so "
                        "it is not scanning anything")
    caught = selftest_dates()
    if caught is not None and caught != 2:
        problems.append("check_docs: the entry-date selftest bent two dates "
                        "and %d were caught — it cannot fail, so it is not "
                        "checking them" % caught)
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        print("check_docs: FAILED", file=sys.stderr)
        return 1
    print("check_docs: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
