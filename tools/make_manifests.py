#!/usr/bin/env python3
"""make_manifests.py — build oracle manifests for every fixture.

For each file in fixtures/ (non-recursive, excluding manifests/ etc.),
run the oracle (unar, The Unarchiver's CLI) and record per entry:

  - data-fork SHA-256 + size
  - resource-fork SHA-256 + size (parsed out of the AppleDouble "._"
    files that `unar -k hidden` produces)
  - Mac type/creator codes when the oracle exposes them (from the
    AppleDouble Finder-info entry, falling back to `lsar -j`)

Manifests land in fixtures/manifests/<fixture>.json and are committed;
the fixtures themselves are not. See TESTING.md for the exact procedure.

Forks are taken from `-k hidden` ("._NAME") rather than `-k visible`
("NAME.rsrc") because the suffix convention is ambiguous whenever an
archive holds both "X" and "X.rsrc" — a THINK C project is exactly that
shape — while the prefix namespace is disjoint from real archive names.
The manifest itself records neither convention: entry name plus per-fork
hashes. DECISIONS.md, 2026-08-08.

When the oracle fails on individual ENTRIES but still walks the
container, the manifest is built from what it did produce and the forks
it failed on are recorded per entry as "unadjudicated" (fork -> the
oracle's own error text) with their hashes omitted. Nothing else is
lost: an archive where unar dies on one fork used to yield no manifest
at all, discarding every other fork it adjudicated perfectly well.
Discovery is by condition, never by fixture name. DECISIONS.md,
2026-08-08.

Forks unar cannot adjudicate are offered to a SECOND oracle, macutils'
macunpack, and the ones it decodes are recorded with per-fork provenance
("data_oracle" / "rsrc_oracle"); the rest stay "unadjudicated". unar not
implementing a method is a fact about unar, not about the format —
StuffIt method 6 is one macunpack has decoded since 1991. Build the
second oracle with tools/build_macunpack.sh. TESTING.md, "A second
oracle"; DECISIONS.md, 2026-08-08.

Oracle invocation (see TESTING.md for rationale):
    lsar -j -nr -e <enc> <fixture>              # format + metadata
    unar -nr -D -f -q -k hidden -e <enc> -o <tmp> <fixture>
    macunpack -f <fixture>                      # second oracle, in <tmp>

<enc> is "macintosh" for every format but StuffIt 5, whose names are
the archive's own UTF-8 (ORACLE_ENCODING, below); the manifest records
the invocation it was built with.
"""
import argparse, hashlib, json, os, plistlib, re, struct, subprocess, sys
import tempfile, unicodedata

FIXDIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
ROOT = os.path.join(os.path.dirname(__file__), "..")
MACUNPACK = os.path.join(ROOT, "build", "macunpack", "macunpack", "macunpack")
MACUNPACK_ID = "macunpack (macutils 2.0b3, -m32)"
# Fixtures whose unadjudicated forks were never offered to the second
# oracle because it was not built. Reported at the end, loudly.
MISSING_ORACLE = set()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_appledouble(path):
    """Return (rsrc_bytes, type4cc, creator4cc, finder_flags) from an
    AppleDouble file.

    AppleDouble layout (per RFC 1740 / the files unar emits):
      u32 magic 0x00051607, u32 version, 16 bytes filler, u16 nentries,
      then nentries * (u32 id, u32 offset, u32 length).
      id 2 = resource fork, id 9 = Finder info (type + creator + flags).

    The flags are bytes 8..9 of the Finder info, `fdFlags`. They agree
    with lsar's XADFinderFlags wherever both are present (423 entries
    checked 2026-10-04), so either source is the oracle's word; this
    takes them from the same place it takes type and creator.
    """
    with open(path, "rb") as f:
        blob = f.read()
    if len(blob) < 26 or struct.unpack(">I", blob[:4])[0] != 0x00051607:
        return None, None, None, None
    nent = struct.unpack(">H", blob[24:26])[0]
    rsrc, typ, creator, flags = b"", None, None, None
    for i in range(nent):
        off = 26 + 12 * i
        if off + 12 > len(blob):
            break
        eid, eoff, elen = struct.unpack(">III", blob[off:off + 12])
        if eoff + elen > len(blob):
            continue
        if eid == 2:
            rsrc = blob[eoff:eoff + elen]
        elif eid == 9 and elen >= 8:
            typ = blob[eoff:eoff + 4].decode("mac_roman")
            creator = blob[eoff + 4:eoff + 8].decode("mac_roman")
            if elen >= 10:
                flags = struct.unpack(">H", blob[eoff + 8:eoff + 10])[0]
    return rsrc, typ, creator, flags


def norm(name):
    return unicodedata.normalize("NFC", name)


def matchkey(name):
    """Key for matching the oracle's own report against extracted paths.

    A classic Mac name may contain '/', which unar writes as '_' on
    disk while its progress report still prints it — so "F/G" on disk
    is ambiguous between a folder and a name. Flattening both
    separators to '_' removes the ambiguity for MATCHING only; manifest
    entry names are recorded exactly as walked.
    """
    return norm(name).replace(":", "_").replace("/", "_")


# `unar` has no machine-readable extraction report, so per-entry
# failures are read off its progress output. Both templates are literal
# strings in the reference tree: unar.m builds "  " + info line +
# "... Failed! (" + reason + ")" and the trailer at unar.m:307, and
# CommandLineCommon.m::MediumInfoLineForEntryWithDictionary joins the
# tags as "  (" + ", " + ")".
#
# The tag list can also carry "dir", "link" and "corrupted", which this
# pattern deliberately does NOT match: an unmatched failure line makes
# the parsed count disagree with the trailer, which refuses the whole
# manifest. Failing safe beats guessing at a shape never seen here.
# /* Source: reference/XADMaster/unar.m, CommandLineCommon.m */
FAIL_RE = re.compile(r"^  (.*)  \((\d+) B(, rsrc)?\)\.\.\. Failed! \((.*)\)$")
TRAILER_RE = re.compile(
    r"^Extraction to directory .* failed \((\d+) files? failed\.\)$")


def parse_oracle_failures(text):
    """Return (failures, trailer_count) from unar's output.

    failures: [(name, "data"|"rsrc", error text)]; trailer_count is the
    total unar itself reports, or None if it never said.
    """
    failures, trailer = [], None
    for line in text.splitlines():
        m = FAIL_RE.match(line)
        if m:
            failures.append((m.group(1), "rsrc" if m.group(3) else "data",
                             m.group(4)))
            continue
        t = TRAILER_RE.match(line)
        if t:
            trailer = int(t.group(1))
    return failures, trailer


# --- which encoding to ask the oracle for --------------------------
# `-e macintosh` forces MacRoman on every format, which is right for
# every Mac archive family here EXCEPT StuffIt 5: its names are the
# archive's own UTF-8, and forcing MacRoman makes the oracle produce
# exactly the mojibake this engine used to produce, so the manifests
# recorded it as ground truth and the diff suite was byte-exact against
# a shared mistake (DECISIONS.md 2026-09-22, *the name that was never a
# fork*). Keyed on lsar's own format name, because that is what a
# fixture is identified by before anything else is read.
ORACLE_ENCODING = {"StuffIt 5": "utf-8"}
ORACLE_ENCODING_DEFAULT = "macintosh"


def oracle_encoding(fmt):
    return ORACLE_ENCODING.get(fmt, ORACLE_ENCODING_DEFAULT)


def lsar_metadata(fixture, encoding=ORACLE_ENCODING_DEFAULT):
    """Return (formatname, {name: (type, creator, finder_flags)},
    {name: [method, ...]}, archive comment or None).

    The method names are the ORACLE's own (`XADCompressionName`), one set
    per entry name because a two-fork entry is two lsar records and the
    forks may use different methods. They are recorded so that a harness
    can ask what an entry is compressed with WITHOUT asking our engine —
    see run_diff.py, which excuses "recognized but unsupported" only for
    methods named here (TESTING.md, "When our engine declines an entry").
    """
    try:
        out = subprocess.run(
            ["lsar", "-j", "-nr", "-e", encoding, fixture],
            capture_output=True, timeout=60)
        # strict=False: lsar's JSON may contain raw control characters
        # (e.g. binary XADNextSolidEntry keys in PackIt archives).
        data = json.loads(out.stdout.decode("utf-8", "replace"), strict=False)
    except Exception:
        return None, {}, {}, None
    fmt = data.get("lsarFormatName")
    # The archive's OWN comment, which belongs to no entry. XADMaster
    # reports it as a parser property; it is the ground truth for what
    # this engine now writes out beside the extracted items.
    comment = data.get("lsarProperties", {}).get("XADComment")
    meta, methods = {}, {}
    for e in data.get("lsarContents", []):
        name = norm(e.get("XADFileName", ""))
        t, c = e.get("XADFileType"), e.get("XADFileCreator")
        ff = e.get("XADFinderFlags")
        to4 = lambda v: struct.pack(">I", v).decode("mac_roman") if v else None
        meta[name] = (to4(t), to4(c), None if ff is None else ff & 0xffff)
        m = e.get("XADCompressionName")
        if m:
            methods.setdefault(name, set()).add(m)
    return fmt, meta, {k: sorted(v) for k, v in methods.items()}, comment


# --- second oracle: macunpack ----------------------------------------
# macunpack names its output files after a Mac name run through
# util/transname.c: a 256-entry table that maps every unprintable byte,
# every 8-bit byte without an unaccented Latin equivalent, space and '/'
# to '_', plus a leading dot, because tools/build_macunpack.sh builds with
# -DNODOT. The table is parsed out of the reference rather than retyped,
# and the mapping is MANY-TO-ONE, so a name is only usable when no other
# entry maps onto it.

def _transname_table():
    src = os.path.join(ROOT, "reference", "macutils", "util", "transname.c")
    try:
        text = open(src).read()
    except OSError:
        return None
    m = re.search(r"static char char_mapping\[\] = \{(.*?)\};", text, re.S)
    if not m:
        return None
    body = re.sub(r"#else /\* LATIN1 \*/.*?#endif /\* LATIN1 \*/", "",
                  m.group(1), flags=re.S).replace("#ifndef LATIN1", "")
    vals = []
    for ch, octal in re.findall(r"'(\\.|[^'])'|(0[0-7]+)", body):
        vals.append(int(octal, 8) if octal
                    else ord({"\\\\": "\\", "\\'": "'"}.get(ch, ch)))
    return bytes(vals) if len(vals) == 256 else None


def transname(name, table):
    """The path macunpack writes for one entry, or None if the name is not
    MacRoman (in which case macunpack never saw these bytes either). Each
    path component is mapped separately, and the leading-dot rule applied to
    each: the separators in a manifest name are real directories, and
    macunpack calls transname once per Mac name as it descends. Measured
    against the built oracle, 2026-08-08: ".dotname" -> "_dotname"."""
    try:
        comps = [c.encode("mac_roman") for c in name.split("/")]
    except UnicodeEncodeError:
        return None
    out = []
    for c in comps:
        t = "".join(chr(table[b]) for b in c)
        out.append("_" + t[1:] if t.startswith(".") else t)   # -DNODOT
    return "/".join(out)


def macunpack_forks(fixture_path):
    """Extract with the second oracle and return {output path: bytes} for the
    files it wrote, or None if it failed. The ".info" files are kept as well
    as the forks: macunpack writes one per entry it extracted, and it is the
    only witness that a MISSING ".data" means an empty fork rather than a
    name we failed to predict."""
    if not os.path.exists(MACUNPACK):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([os.path.abspath(MACUNPACK), "-f",
                            os.path.abspath(fixture_path)],
                           cwd=tmp, capture_output=True, timeout=300)
        if r.returncode != 0:
            return None
        out = {}
        for root, dirs, files in os.walk(tmp):
            for f in files:
                if not f.endswith((".data", ".rsrc", ".info")):
                    continue
                rel = os.path.relpath(os.path.join(root, f), tmp)
                out[rel] = open(os.path.join(root, f), "rb").read()
        return out


def adjudicate_with_macunpack(fixture_path, entries):
    """Fill in forks the primary oracle left unadjudicated. Returns the
    number of forks adjudicated."""
    if not any("unadjudicated" in e for e in entries):
        return 0
    # Doing without the second oracle is deliberate (a machine with no
    # 32-bit toolchain must still build every manifest) but it must never
    # be SILENT: a rebuild with it missing writes weaker manifests than
    # the committed ones and looks like success. `./ci.sh` runs
    # `make clean`, which deletes it — measured the hard way, 2026-08-08,
    # by rebuilding the corpus straight after a CI run and reverting 23
    # adjudicated forks to "unadjudicated".
    if not os.path.exists(MACUNPACK):
        MISSING_ORACLE.add(os.path.basename(fixture_path))
        return 0
    table = _transname_table()
    if table is None:
        return 0
    produced = macunpack_forks(fixture_path)
    if not produced:
        return 0

    # transname is many-to-one: refuse any name two entries share, since
    # there is then no telling whose output a file is.
    mapped, clash = {}, set()
    for e in entries:
        if e.get("is_dir"):
            continue
        t = transname(e["name"], table)
        if t is None:
            continue
        if t in mapped:
            clash.add(t)
        mapped[t] = e
    filled = 0
    for t, e in mapped.items():
        un = e.get("unadjudicated")
        if not un or t in clash:
            continue
        # Without the ".info" macunpack writes for every entry it extracted,
        # a predicted name that is simply WRONG looks exactly like an entry
        # with two empty forks, and would be recorded as ground truth saying
        # so. Adjudicate only where the entry is known to have been written.
        if t + ".info" not in produced:
            continue
        for fork in ("data", "rsrc"):
            if fork not in un:
                continue
            # No file means macunpack decoded the fork as empty: it writes
            # nothing for one — the same convention unar uses.
            blob = produced.get(t + "." + fork, b"")
            e[fork + "_size"] = len(blob)
            e[fork + "_sha256"] = hashlib.sha256(blob).hexdigest()
            e[fork + "_oracle"] = MACUNPACK_ID
            del un[fork]
            filled += 1
        if not un:
            del e["unadjudicated"]
    return filled


# --- third oracle: deark -----------------------------------------------
# The primary oracle is not merely SILENT about ARC/PAK method 0x0b, it
# is WRONG: `unar` starts Distilled's 8 KB window at zero where PAK
# fills it with spaces, so it returns the right length and the wrong
# bytes, and reports the entry as a checksum failure (BLOCKERS.md).
# Those entries arrive here unadjudicated, which is correct and useless.
# deark implements that method independently and agrees with the CRC PAK
# itself stored, so it is offered the forks the others left open.
#
# **It reads BOTH forks**, which this file asserted the opposite of until
# 2026-09-21: deark writes an AppleDouble `.adf` sidecar beside each
# member that has a resource fork, and the corpus's only real StuffIt
# method-6 entry is one whose data fork is EMPTY and whose resource fork
# is 34,818 bytes. A premise that the third oracle could not see a
# resource fork is why it was never offered one (BLOCKERS.md).
DEARK = os.path.join(ROOT, "build", "deark", "deark")
DEARK_ID = "deark"

# **deark does not fail on a damaged file — it PADS.** Measured
# 2026-09-21 on `sitdoc.sit`, a MacBinary whose header declares a
# 286-byte resource fork and which physically ends 52 bytes short:
# this engine writes the 234 bytes that are there and reports the file
# truncated, `unar` says "Attempted to read more data than was
# available", and deark writes 286 bytes whose last 52 are zeros it
# made up. An oracle that always produces something is not ground
# truth about a file that does not contain it.
#
# So deark fills a fork the others left open only where it cannot
# invent one: when the fork is EMPTY — an assertion of absence — or
# when the entry's methods are all ones deark is the designated oracle
# for. Everything else it is offered is a CROSS-CHECK against a fork
# another implementation already graded, where agreement is the whole
# point and disagreement is reported rather than written down.
# Implode joined on 2026-10-07, when the scope decision brought PKZIP
# 1.x's method 6 in (DECISIONS.md 2026-10-07, *the oracle that was one
# line away*). deark decodes all 7 Implode entries of the two PKZIP 1.x
# fixtures and every one matches the CRC-32 PKZIP ITSELF stored — a
# check no decoder here can influence, and one that CAN fail: bending a
# byte of `4acalc.zip` makes deark print "CRC check failed" for that
# entry and write the bytes anyway. `unar` adjudicates 5 of the 7; the
# other 2 are the forks it fails with "Attempted to read more data than
# was available", and they are what this adds.
DEARK_METHODS = {"Distilled", "Implode"}


def deark_id():
    """The oracle string, with the version deark reports."""
    try:
        r = subprocess.run([DEARK, "-version"], capture_output=True, timeout=30)
        v = r.stdout.decode("utf-8", "replace").strip().splitlines()[0]
        return f"deark ({v})"
    except Exception:
        return DEARK_ID


# deark writes every member to a real file, so a member's name reaches
# the disk only after deark's own sanitiser has been over it: a path
# separator, a Windows-reserved character or anything below U+00A0
# becomes "_". Matching raw names misses every entry inside a folder.
#
# Source: reference/deark/src/deark-util.c — `de_char_to_valid_fn_char`
# (32..126 minus / \ : * ? " < > |, or >= 160, else "_"),
# `de_finfo_set_name_internal` (strip trailing spaces) and
# `sanitize_filename1` ("." and ".."). `allow_subdirs` is off because
# `deark_forks` passes no `-allowsubdirs`, so "/" is mangled too.
# The mapping is many-to-one, so every caller refuses a mangled name
# two entries share.
_DEARK_BAD = set('/\\:*?"<>|')


def deark_name(name):
    out = []
    for ch in name:
        o = ord(ch)
        if 32 <= o <= 126 and ch not in _DEARK_BAD:
            out.append(ch)
        elif o >= 160:
            out.append(ch)
        else:
            out.append("_")
    t = "".join(out).rstrip(" ")
    if t == ".":
        t = "_"
    elif t == "..":
        t = "_."
    return norm(t or "_")


# deark names the fork in most of the errors it reports per fork.
#   Error: NAME[data fork]: Unsupported compression method: 8 (MW)
#   Error: Decompression failed for file NAME[resource fork]: ...
#   Error: CRC check failed for file NAME[data fork]
# Source: reference/deark/modules/stuffit.c, and "data"/"resource" are
# its two `forkname` strings.
_DEARK_ERR = re.compile(r"^Error: (?:.*? for file )?(.*)"
                        r"\[(data|resource) fork\]")

# **That NAME is not the member's raw name**, which this file asserted
# until 2026-09-22: deark prints it MAKE_PRINTABLE, so every character
# it will not send to a terminal arrives as an escape — `Icon\r`, the
# commonest filename on a Macintosh volume, reads `Icon<\r>`. Running
# that through `deark_name` gives `Icon__r_` where the file on disk is
# `Icon_`, so the decline was recorded against a member that does not
# exist and the fork it names looked like one deark never mentioned.
# **382 declined forks across 35 fixtures are mis-keyed this way**, and
# on 2026-09-22 none of them was live: in every one, deark wrote no
# file for that member at all, so nothing read the wrong key. What it
# would cost when one IS live is the bug this rule exists to stop —
# a fork deark declined recorded as a fork deark read as EMPTY.
#
# Source: reference/deark/src/deark-ucstring.c,
# `ucstring_to_sz` under DE_CONVFLAG_MAKE_PRINTABLE: 0x0a/0x0d/0x09/0x00
# become \n \r \t \0, a byte deark could not decode becomes its two hex
# digits, anything else unprintable becomes U+XXXX, each wrapped in
# `<`...`>`. A raw byte is `DE_CODEPOINT_BYTE00 + b` = 0x10000000 + b
# (deark-private.h), which is past the 0x10ffff that
# `de_char_to_valid_fn_char` keeps — so in a FILENAME it is "_", which
# is what this maps it to directly.
_DEARK_ESC = re.compile(r"<(\\[rnt0]|U\+[0-9A-Fa-f]{4}|[0-9A-Fa-f]{2})>")
_DEARK_ESC_C = {"\\r": "\r", "\\n": "\n", "\\t": "\t", "\\0": "\0"}


def deark_err_name(raw):
    """The key a member named in one of deark's ERRORS writes its file
    under. Ambiguous by construction — a member really called `Icon<\\r>`
    is indistinguishable from one called `Icon\r` — and that is safe in
    the direction it errs: the worst it can do is mark a fork DECLINED
    that deark could have read, which costs coverage and never records
    a fork's contents."""
    def sub(m):
        t = m.group(1)
        if t in _DEARK_ESC_C:
            return _DEARK_ESC_C[t]
        if t.startswith("U+"):
            return chr(int(t[2:], 16))
        return "_"                      # a raw byte: past 0x10ffff, so "_"
    return deark_name(_DEARK_ESC.sub(sub, raw))


# A fixture deark identifies as something OTHER than the archive it
# holds, and the module to name for it. One entry, and it is the
# self-extracting zip: given `pkz101.exe` deark runs its `exe` module,
# recognises a DOS EXE and writes the embedded zip out as ONE file —
# which adjudicates nothing, because the forks wanted are the zip's
# members. `-m zip` reaches them, and `deark -m zip` on that file
# extracts all 13 (FORMATS.md, *Implode*).
#
# **Not a default and not a fallback.** Naming the module per fixture is
# what keeps this from becoming "if the first run matched nothing, try
# again differently", which would quietly re-identify any fixture whose
# names failed to match for some other reason — and matching is the one
# thing in this function that has been wrong before (the folder-separator
# mangling, 2026-09-22).
DEARK_MODULE = {"pkz101.exe": "zip"}


def deark_forks(fixture_path, tmp):
    """member name -> {"data": bytes, "rsrc": bytes}, as deark reads it.

    deark names its output `<prefix>.<index>.<member name>`, and a
    member with a resource fork gets a second file with `.adf` on the
    end — an AppleDouble sidecar. **The index counts output FILES, not
    members**, so it is not a member ordinal as soon as any member has
    two forks: this matched on it until 2026-09-21, which worked only
    because the one format the third oracle was ever asked about has no
    resource forks at all. Matching is by name, and a name that appears
    twice in an archive is refused by the caller.
    """
    cmd = [DEARK, "-od", tmp, "-o", "m"]
    mod = DEARK_MODULE.get(os.path.basename(fixture_path))
    if mod:
        cmd += ["-m", mod]
    try:
        r = subprocess.run(cmd + [os.path.abspath(fixture_path)],
                           capture_output=True, timeout=600)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    # **A fork deark DECLINED looks exactly like a fork it read as
    # empty**, and this file used to assert the opposite ("a member
    # deark wrote at all has both forks"). It does not: given a
    # StuffIt method-8 entry it writes the resource fork's sidecar,
    # reports `Unsupported compression method: 8 (MW)` for the data
    # fork, and writes no data file — so treating the absence as an
    # empty fork would record "this fork is 0 bytes" as ground truth
    # about a fork deark never read. Found 2026-09-22 by
    # `tools/sweep_deark.py` on `derived-BitMap11.sit`. A declined
    # fork is None here, and every caller must tell that from b"".
    declined, unattributed = set(), False
    for line in (r.stdout + r.stderr).decode("utf-8", "replace").splitlines():
        if not line.startswith("Error: "):
            continue
        m = _DEARK_ERR.match(line)
        if m:
            declined.add((deark_err_name(m.group(1)),
                          "data" if m.group(2) == "data" else "rsrc"))
        else:
            # An error deark did not attach to a fork — a whole-member
            # or whole-archive one — makes every absent fork of this
            # archive UNKNOWN rather than empty. Deliberately
            # over-cautious: it costs coverage (9 forks of
            # `synth-arc-mixed.arc` and `arcplus712.zip`, where the
            # error names a member and no fork) and it cannot turn an
            # error into an assertion of absence.
            unattributed = True
    out = {}
    for fn in os.listdir(tmp):
        parts = fn.split(".", 2)
        if len(parts) < 3:
            continue
        rest, path = parts[2], os.path.join(tmp, fn)
        if rest.endswith(".adf"):
            rsrc = parse_appledouble(path)[0]
            if rsrc is not None:
                out.setdefault(rest[:-4], {})["rsrc"] = rsrc
        else:
            with open(path, "rb") as fh:
                out.setdefault(rest, {})["data"] = fh.read()
    # A member deark wrote NO file for is still a member deark SAW —
    # its errors name it. Until 2026-09-22 such a member was simply
    # absent here, so every caller counted it as one deark could not
    # NAME, which is the opposite of what happened: deark named it and
    # declined it. That is 225 of the 283 entries `sweep_deark.py`
    # reported it could not compare, all of them StuffIt method 13 or
    # StuffIt 5's Arsenic, neither of which deark implements.
    from_file = set(out)
    for name, _fork in declined:
        out.setdefault(name, {})
    # A fork with no file is empty — an assertion of absence — UNLESS
    # deark said it could not read it, or said something about this
    # archive it did not attach to a fork, in which case nothing is
    # known about it and it is None. For a member with no file at all
    # NOTHING is asserted about the fork deark did not mention either:
    # it may have given up on the member before reaching it.
    for name, v in out.items():
        for fork in ("data", "rsrc"):
            if fork in v:
                continue
            v[fork] = None if (unattributed or name not in from_file
                               or (name, fork) in declined) else b""
    return out


def adjudicate_with_deark(fixture_path, entries):
    """Fill what the others left open, and CHECK what only macunpack saw.

    Two jobs, and the second is the one that was missing. `macunpack`
    is where this project's StuffIt method-6 decoder was transcribed
    from, so a fork it alone grades is a transcription checked against
    its own source. deark implements that method independently — it
    credits macunpack as DOCUMENTATION and uses none of its code — so
    offering it those forks is worth doing even though nothing is open.
    **A third oracle asked only where the others are silent can never
    contradict them**, which is why this one sat in `reference/`,
    compiled by `ci.sh` and running for another format, without ever
    being put to the 23 forks macunpack alone had graded (BLOCKERS.md).

    On agreement the fork records both oracles. On DISAGREEMENT nothing
    is rewritten: two implementations differing is a finding, and it is
    reported rather than resolved here.
    """
    wanted = [e for e in entries
              if "unadjudicated" in e
              or any("macunpack" in (e.get(k) or "")
                     for k in ("data_oracle", "rsrc_oracle"))]
    if not wanted:
        return 0
    if not os.path.exists(DEARK):
        MISSING_ORACLE.add(os.path.basename(fixture_path))
        return 0

    # Match on the name deark WRITES, not the name the archive holds:
    # a member inside a folder reaches the disk with its separators
    # mangled, so matching raw names silently skipped every one of
    # them — 500 entries across the corpus, found 2026-09-22 by
    # `tools/sweep_deark.py`. Many-to-one, so a mangled name two
    # entries share is refused, the same rule as everywhere else here.
    seen = {}
    for e in entries:
        k = deark_name(e["name"])
        seen[k] = seen.get(k, 0) + 1

    with tempfile.TemporaryDirectory() as tmp:
        got = deark_forks(fixture_path, tmp)
        if not got:
            return 0
        filled = 0
        for e in wanted:
            key = deark_name(e["name"])
            if seen.get(key, 0) != 1 or key not in got:
                continue
            for fork in ("data", "rsrc"):
                blob = got[key][fork]
                if blob is None:
                    continue            # deark declined this fork
                un = e.get("unadjudicated") or {}
                if fork in un:
                    m = e.get("oracle_methods")
                    if blob and not (m and all(x in DEARK_METHODS for x in m)):
                        continue        # it may be padding — see DEARK_METHODS
                    e[fork + "_size"] = len(blob)
                    e[fork + "_sha256"] = hashlib.sha256(blob).hexdigest()
                    e[fork + "_oracle"] = deark_id()
                    del un[fork]
                    if not un:
                        e.pop("unadjudicated", None)
                    filled += 1
                    continue
                who = e.get(fork + "_oracle") or ""
                if "macunpack" not in who or DEARK_ID in who:
                    continue
                if (hashlib.sha256(blob).hexdigest() == e.get(fork + "_sha256")
                        and len(blob) == e.get(fork + "_size")):
                    e[fork + "_oracle"] = "%s + %s" % (who, deark_id())
                    filled += 1
                else:
                    print("  DEARK DISAGREES with macunpack on %s %s of %s "
                          "(deark %d B) — two implementations differ, which "
                          "is a finding, not a manifest edit"
                          % (e["name"], fork, os.path.basename(fixture_path),
                             len(blob)), file=sys.stderr)
        return filled


# --- the container's own arithmetic ------------------------------------
# **Not an oracle: the file itself.** Eight forks in seven damaged
# MacBinary fixtures had no second implementation to be wrong against —
# `unar` declines them, deark PADS them (DEARK_METHODS, above), and our
# own output cannot grade our own output. It does not need one. A
# MacBinary is a 128-byte header, the data fork padded to a multiple of
# 128, then the resource fork, all of it STORED; so where a fork starts
# is arithmetic and what is in it is the file's own bytes. A file that
# ends early holds exactly as much of a fork as is physically there,
# and that number is forced rather than decoded.
#
# **This is only ground truth where the arithmetic is confirmed on the
# file it is applied to**, never on the strength of the layout in
# general, because the engine reads the same header and would be wrong
# the same way. Two confirmations exist and one of them is required:
#
#   - the header's own CRC-16/CCITT over its first 124 bytes matches
#     the value at +124, i.e. it is MacBinary II and its LENGTHS are
#     checksummed (guysmaccontacts.sea, whose data fork overruns the
#     file by 36,045 B and whose resource fork is therefore not present
#     at all); or
#   - the entry's OTHER fork is already adjudicated by an oracle and
#     the same arithmetic reproduces it byte for byte, which pins both
#     offsets on that file (the six MacBinary I fixtures, where the
#     data fork is unar's and the resource fork is the remainder).
#
# The layout itself is not assumed either: it reproduces both forks of
# **174 undamaged MacBinary fixtures**, every one in the corpus with a
# single entry and two adjudicated forks, with no mismatch.
MACBINARY_ID = "MacBinary container arithmetic"


def _crc16_ccitt(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 \
                else (crc << 1) & 0xFFFF
    return crc


def macbinary_slices(path):
    """`macbinary_slices_bytes` for a file on disk."""
    try:
        with open(path, "rb") as fh:
            return macbinary_slices_bytes(fh.read())
    except OSError:
        return None


def macbinary_slices_bytes(d):
    """(data_bytes, rsrc_bytes, crc_ok) as the container places them,
    clipped to where the bytes actually end; None if the header is not
    a MacBinary one."""
    if len(d) < 128 or d[0] != 0 or d[74] != 0 or d[82] != 0:
        return None
    if not 1 <= d[1] <= 63:
        return None
    dlen = int.from_bytes(d[83:87], "big")
    rlen = int.from_bytes(d[87:91], "big")
    rstart = 128 + (dlen + 127) // 128 * 128
    crc = int.from_bytes(d[124:126], "big")
    return (d[128:min(len(d), 128 + dlen)],
            d[min(len(d), rstart):min(len(d), rstart + rlen)],
            crc != 0 and crc == _crc16_ccitt(d[0:124]))


def adjudicate_from_macbinary(fixture_path, fmt, entries):
    """Grade a damaged MacBinary's forks against the container itself."""
    if fmt != "MacBinary":
        return 0
    live = [e for e in entries if not e.get("is_dir")]
    if len(live) != 1 or "unadjudicated" not in live[0]:
        return 0
    e = live[0]
    got = macbinary_slices(fixture_path)
    if got is None:
        return 0
    blobs = {"data": got[0], "rsrc": got[1]}
    confirmed = got[2]
    for fork in ("data", "rsrc"):
        want = e.get(fork + "_sha256")
        if want is None:
            continue            # nobody has graded this fork
        if hashlib.sha256(blobs[fork]).hexdigest() == want:
            confirmed = True
        else:
            # The arithmetic disagrees with an oracle on this very file,
            # so it is not describing this file. Say so and grade
            # nothing: a rule that adjudicates where it has just been
            # shown wrong is worse than no rule.
            print("  MACBINARY ARITHMETIC DISAGREES with %s on %s of %s "
                  "— grading nothing from the container here"
                  % (e.get(fork + "_oracle") or "the oracle", fork,
                     os.path.basename(fixture_path)), file=sys.stderr)
            return 0
    if not confirmed:
        return 0
    filled = 0
    un = e["unadjudicated"]
    for fork in ("data", "rsrc"):
        if fork not in un:
            continue
        e[fork + "_size"] = len(blobs[fork])
        e[fork + "_sha256"] = hashlib.sha256(blobs[fork]).hexdigest()
        e[fork + "_oracle"] = MACBINARY_ID
        del un[fork]
        filled += 1
    if not un:
        del e["unadjudicated"]
    return filled


def build_manifest(fixture_path, verbose=False):
    name = os.path.basename(fixture_path)
    fmt, meta, methods, comment = lsar_metadata(fixture_path)
    # The format decides the encoding and the encoding decides the
    # names, so the first call is only ever trusted for the format —
    # which no encoding changes. One extra lsar for the formats that
    # want another one, and none at all for the rest.
    encoding = oracle_encoding(fmt)
    if encoding != ORACLE_ENCODING_DEFAULT:
        fmt, meta, methods, comment = lsar_metadata(fixture_path, encoding)
    # The "._" sidecar namespace is disjoint from real archive names in
    # every fixture harvested so far, which is why forks are taken from
    # `-k hidden` — but an entry literally named "._X" would collide
    # with the sidecar of "X", the one shape this convention cannot
    # represent. Refuse rather than guess; the fixture stays in the
    # corpus for robustness testing.
    for n in meta:
        if os.path.basename(n).startswith("._"):
            print(f"  oracle UNDECIDABLE on {name} "
                  f"(AppleDouble prefix collision: {n!r}), skipping",
                  file=sys.stderr)
            return None
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(
            ["unar", "-nr", "-D", "-f", "-q", "-k", "hidden",
             "-e", encoding, "-o", tmp, fixture_path],
            capture_output=True, timeout=300)
        # A non-zero exit is per-ENTRY failure or container failure, and
        # the difference is worth the whole manifest. Accept it as
        # per-entry only when unar's own report accounts for it exactly:
        # the parsed failures must match the total it prints, and every
        # name it names must be an entry lsar also lists. Otherwise the
        # output is not modelled and is not ground truth.
        failures, failed_names = {}, {}
        if r.returncode != 0:
            parsed, trailer = parse_oracle_failures(
                (r.stdout + r.stderr).decode("utf-8", "replace"))
            if not parsed or trailer is None or len(parsed) != trailer:
                print(f"  oracle FAILED on {name}: {r.stderr.decode()[:200]}",
                      file=sys.stderr)
                return None
            # matchkey is many-to-one (':' and '/' both flatten to '_'),
            # so two DIFFERENT entry names can share a key — and then a
            # failure would be attributed to whichever of them the walk
            # reached, leaving the entry that really failed holding
            # hashes of whatever unar dropped on disk. Refuse instead.
            # No fixture harvested so far collides; this is a condition,
            # not a case.
            bykey = {}
            for n in meta:
                bykey.setdefault(matchkey(n), []).append(n)
            clashing = [v for v in bykey.values() if len(v) > 1]
            if clashing:
                print(f"  oracle UNRELIABLE on {name} (entries {clashing[0]!r} "
                      f"share a failure-report key), skipping", file=sys.stderr)
                return None
            known = set(bykey)
            for ename, fork, err in parsed:
                if matchkey(ename) not in known:
                    print(f"  oracle UNRELIABLE on {name} (reports a failure "
                          f"for {ename!r}, which it does not list)",
                          file=sys.stderr)
                    return None
                failures.setdefault(matchkey(ename), {})[fork] = err
                failed_names[matchkey(ename)] = norm(ename)
            print(f"  oracle PARTIAL on {name}: "
                  f"{len(parsed)} fork(s) unadjudicated", file=sys.stderr)
        # GNUstep's fork-path bug is a `-k visible` bug: it comes from
        # appending ".rsrc" to a name its path code rejects (leading
        # '~'), and it can write the AppleDouble container into the
        # data-fork filename. Prefixing never calls that code, so this
        # warning should not appear here at all — if it does, something
        # is unmodelled and the output is not ground truth.
        if b"cannot append extension" in r.stderr:
            print(f"  oracle UNRELIABLE on {name} (fork path bug), skipping",
                  file=sys.stderr)
            return None
        entries = []
        for root, dirs, files in os.walk(tmp):
            dirs.sort()          # os.walk order is otherwise the
            rel = os.path.relpath(root, tmp)   # filesystem's, not ours
            fs = set(files)
            for d in sorted(dirs):
                p = norm(os.path.normpath(os.path.join(rel, d)))
                ent = {"name": p, "is_dir": True}
                # A folder has Finder flags of its own and the oracle
                # reports them (0x03f0 on a MacZip folder); nothing else
                # about a directory is ground truth here.
                if p in meta and meta[p][2] is not None:
                    ent["finder_flags"] = meta[p][2]
                entries.append(ent)
            # One entry per name, whether it arrived as a data-fork
            # file, a "._" sidecar, or both. A sidecar with no data
            # file beside it is a real entry whose data fork is empty:
            # unar writes nothing for a 0-byte data fork (resource-only
            # entries, e.g. PackIt members and FKEY/cdev files).
            for base in sorted({f[2:] if f.startswith("._") else f
                                for f in fs}):
                p = norm(os.path.normpath(os.path.join(rel, base)))
                ent = {
                    "name": p,
                    "data_size": 0,
                    "data_sha256": hashlib.sha256(b"").hexdigest(),
                    "rsrc_size": 0,
                    "rsrc_sha256": hashlib.sha256(b"").hexdigest(),
                }
                if base in fs:
                    full = os.path.join(root, base)
                    ent["data_size"] = os.path.getsize(full)
                    ent["data_sha256"] = sha256_file(full)
                ad = os.path.join(root, "._" + base)
                if os.path.exists(ad):
                    rsrc, typ, creator, fflags = parse_appledouble(ad)
                    # Every "._" file unar writes is an AppleDouble
                    # container; one that is not means the oracle put
                    # something else there, which is not ground truth.
                    if rsrc is None:
                        print(f"  oracle UNRELIABLE on {name} "
                              f"(sidecar is not AppleDouble: {p!r})",
                              file=sys.stderr)
                        return None
                    ent["rsrc_size"] = len(rsrc)
                    ent["rsrc_sha256"] = hashlib.sha256(rsrc).hexdigest()
                    if typ:
                        ent["type"] = typ
                    if creator:
                        ent["creator"] = creator
                    if fflags is not None:
                        ent["finder_flags"] = fflags
                if "type" not in ent and p in meta and meta[p][0]:
                    ent["type"], ent["creator"] = meta[p][0], meta[p][1]
                # The Finder flags, from whichever of the two the oracle
                # offered. An entry the oracle reports no flags for gets
                # no key: an absent field must never become an excuse,
                # so run_diff grades the ones that are here and says how
                # many that is.
                if "finder_flags" not in ent and p in meta and meta[p][2] is not None:
                    ent["finder_flags"] = meta[p][2]
                if p in methods:
                    ent["oracle_methods"] = methods[p]
                # A fork the oracle failed on is not ground truth,
                # whatever it left on disk — and what it leaves varies:
                # a 0-byte file, a partial one (114,644 B of a failed
                # data fork in guysmaccontacts.sea), or a sidecar padded
                # to the DECLARED length (appledraw51.cpt). Record the
                # oracle's reason and drop the hashes.
                un = failures.pop(matchkey(p), None)
                if un:
                    # "no data-fork file means a 0-byte data fork" holds
                    # only for entries the oracle COMPLETED. On one it
                    # failed, absent output means it never got there, so
                    # the other fork is unadjudicated too rather than
                    # empty (derived-INITLoader.sit: sidecar written,
                    # data fork never attempted).
                    if base not in fs:
                        un.setdefault("data", "oracle wrote no output for "
                                              "this fork")
                    if not os.path.exists(ad):
                        un.setdefault("rsrc", "oracle wrote no output for "
                                              "this fork")
                    ent["unadjudicated"] = un
                    for fork in un:
                        ent.pop(fork + "_size", None)
                        ent.pop(fork + "_sha256", None)
                entries.append(ent)
        # An entry the oracle failed on before writing anything at all
        # is still an entry, and its NAME is still ground truth: record
        # it with both forks unadjudicated so the runner keeps checking
        # that we produce it, rather than silently tolerating one more
        # output file.
        for key, un in failures.items():
            full = dict(un)
            for fork in ("data", "rsrc"):
                full.setdefault(fork, "oracle wrote no output for this entry")
            ent = {"name": failed_names[key], "unadjudicated": full}
            if failed_names[key] in methods:
                ent["oracle_methods"] = methods[failed_names[key]]
            entries.append(ent)
    if not entries:
        print(f"  oracle produced nothing for {name}", file=sys.stderr)
        return None
    filled = adjudicate_with_macunpack(fixture_path, entries)
    if filled:
        print(f"  second oracle adjudicated {filled} fork(s) of {name}",
              file=sys.stderr)
    filled = adjudicate_with_deark(fixture_path, entries)
    if filled:
        print(f"  deark adjudicated {filled} fork(s) of {name}",
              file=sys.stderr)
    # Last, because it is not an oracle and should only see what three
    # implementations could not settle between them.
    filled = adjudicate_from_macbinary(fixture_path, fmt, entries)
    if filled:
        print(f"  the container's own arithmetic adjudicated {filled} "
              f"fork(s) of {name}", file=sys.stderr)
    # The warning about a missing second oracle is about forks that are
    # STILL open. A fixture the third oracle finished is not one of
    # them, and saying so would send the next reader to build a tool
    # that had nothing left to decide — **unless the tool that is
    # missing is macunpack**, which since 2026-09-21 deark can stand in
    # for on the forks macunpack alone used to grade. Discarding the
    # warning there would undo the thing this file was written to
    # prevent: a rebuild without the second oracle writing WEAKER
    # manifests than the committed ones and looking like success. It
    # was measured the hard way on 2026-08-08 and then reproduced on
    # 2026-09-21, one layer up, by the change that let deark close
    # those gaps (BLOCKERS.md).
    if (not any("unadjudicated" in e for e in entries)
            and os.path.exists(MACUNPACK)):
        MISSING_ORACLE.discard(name)
    # Canonical order, so a rebuild on another machine produces the same
    # file. Every consumer looks entries up by name; none depends on the
    # order they were walked in.
    entries.sort(key=lambda e: e["name"])
    man = {
        "fixture": name,
        "sha256": sha256_file(fixture_path),
        "size": os.path.getsize(fixture_path),
        "format": fmt,
        "oracle": "unar -nr -D -f -q -k hidden -e %s (v1.10.8)" % encoding,
        "entries": entries,
    }
    # Absent unless the archive carries one, so a manifest without the
    # key means "no comment" and never "not looked for".
    if comment:
        man["comment"] = comment
    return man


# **Two fixtures are INPUTS, not archives**, and this is where saying so
# has to live: `make_manifests.py` with no arguments builds a manifest
# for any fixture that lacks one, which is how these two — read by
# `unar`, so a manifest gets built — became two failing fixtures on
# 2026-09-22 (OPEN_ITEMS.md had them as an open question until
# DECISIONS.md 2026-09-22, *the sidecar is not an archive*).
#
# They are the AppleDouble sidecars carrying the RESOURCE FORK of the two
# DiskDoubler files that were cut into `.1`/`.2` parts, and
# `run_segments.py`'s DDSEG_SPECIMENS is what reads them: they are what a
# joined set is graded AGAINST, in `ci.sh`, every run. The parts
# themselves get no manifest for the same reason and always did —
# `run_ddtf.py` says so where it registers them.
NOT_ARCHIVES = {
    "ddtf-ddpro411ad1.dd.ad":
        "the resource fork of the file ddtf-ddpro411ad1.dd.[12] joins into",
    "ddtf-ddpro411ad1.sea.ad":
        "the resource fork of the file ddtf-ddpro411ad1.sea.[12] joins into",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="specific fixtures (default: all)")
    ap.add_argument("--force", action="store_true", help="rebuild existing")
    args = ap.parse_args()

    mandir = os.path.join(FIXDIR, "manifests")
    os.makedirs(mandir, exist_ok=True)

    if args.files:
        fixtures = args.files
    else:
        fixtures = [os.path.join(FIXDIR, f) for f in sorted(os.listdir(FIXDIR))
                    if os.path.isfile(os.path.join(FIXDIR, f))
                    and f not in ("SOURCES.md",)]

    made = skipped = failed = 0
    for fx in fixtures:
        base = os.path.basename(fx)
        if base in NOT_ARCHIVES:
            print(f"  input, not an archive: {base} — "
                  f"{NOT_ARCHIVES[base]}", file=sys.stderr)
            skipped += 1
            continue
        out = os.path.join(mandir, base + ".json")
        if os.path.exists(out) and not args.force:
            skipped += 1
            continue
        # Some manifests are not built from unar at all: the DiskDoubler
        # corpus is graded against the files it was made from
        # (tools/run_ddtf.py --register), and unar cannot read half of
        # it. Rebuilding one here would replace ground truth with an
        # opinion, or -- where the oracle fails -- delete it.
        if os.path.exists(out):
            try:
                oracle = json.load(open(out)).get("oracle", "")
            except ValueError:
                oracle = ""
            if not oracle.startswith("unar"):
                print(f"  kept (oracle is not unar): {os.path.basename(fx)}",
                      file=sys.stderr)
                skipped += 1
                continue
        prev = {}
        if os.path.exists(out):
            try:
                prev = json.load(open(out))
            except ValueError:
                prev = {}
        m = build_manifest(fx)
        if m is not None and prev.get("ungraded"):
            # A declaration of what no oracle can grade is the
            # manifest's own word, not the oracle's, so a rebuild has
            # nothing to regenerate it from: carry it across, or the
            # next --force silently drops the one tolerance a fixture
            # rests on (TESTING.md, *The Finder metadata, and the one
            # field no oracle settles*).
            m["ungraded"] = prev["ungraded"]
        if m is None:
            failed += 1
            # A stale manifest for an oracle-unreliable fixture is
            # worse than none: drop it.
            if os.path.exists(out):
                os.unlink(out)
                print(f"  removed stale manifest for {os.path.basename(fx)}",
                      file=sys.stderr)
            continue
        with open(out, "w") as f:
            json.dump(m, f, indent=1, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        made += 1
        print(f"  manifest: {os.path.basename(fx)} "
              f"({m['format']}, {len(m['entries'])} entries)")
    print(f"manifests: {made} built, {skipped} kept, {failed} failed")
    if MISSING_ORACLE:
        print(f"WARNING: the second oracle is not built, so {len(MISSING_ORACLE)}"
              f" fixture(s) kept forks it may be able to adjudicate — the "
              f"manifests just written are WEAKER than committed ones built "
              f"with it. Run `sh tools/build_macunpack.sh` and rebuild them: "
              f"{' '.join(sorted(MISSING_ORACLE))}", file=sys.stderr)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
