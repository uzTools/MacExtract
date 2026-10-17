#!/usr/bin/env python3
"""run_meta.py — the engine's Finder metadata beyond type, creator and flags.

    tools/run_meta.py [--cli build/macextract] [--corpus] [--expander]

`macextract l --meta` prints, per entry, the FInfo/DInfo and FXInfo/DXInfo
bytes, the backup date, the lock and the Get Info comment the engine
delivers (cli/main.c, print_meta). This holds those rows to something
other than the engine:

  synth-as-meta.as, synth-as-dosro.as   `lsar` (XADMaster's AppleSingle
      parser) for the 32 bytes of Finder info, the comment and the backup
      date; tools/synth_as.py --describe for the lock, which XADMaster has
      no key for, and for the one place this engine and XADMaster differ
      by design: a backup date of 0x80000000 is the RFC's "unknown"
      (reference/notes/rfc1740.txt), which XADMaster reports as 2068.
  synth-sqp-meta.pkg                    tools/synth_sqp.py's own items —
      `lsar` does not read AppleLink packages at all.
  DiskDoubler 3.7's own file            the catalog record the subject had
      before 3.7 compressed it (tools/vmac/ddmeta.py --writer's result;
      skipped, and said so, where it is absent).
  --corpus                              every fixture: wherever the engine
      states a field and `lsar` reports the same field, they must agree.
  the envelopes (envelope_expectations, envelope_corpus)
      MacBinary, uuencode, base64 and MIME multipart/appledouble, generated
      by tools/synth_envelopes.py and swept over the corpus, against deark,
      macunpack, hexbin, Python's email and zipfile, and lsar. There, a
      field the oracle states and the engine prints `-` FAILS.
  --expander                            StuffIt classic, against StuffIt
      Expander 4.0.2's OWN output: the catalog records tools/vmac/sitmeta.py
      read back off the disk Expander wrote, for every corpus archive and
      sentinel archive it ran (its results directory; skipped, and said so,
      where that is absent). Per entry, a file's FInfo, FXInfo, backup date
      and lock and a folder's DInfo, DXInfo and backup date must be what
      Expander wrote, field for field. A field the engine leaves unstated
      (`-`) counts as what a host writes on a new file: zero, unlocked.
      An archive Expander did not extract whole is left out, by name, as
      sitmeta.py's model check leaves it out.

Then a CONTROL per field: the engine's row is tampered with, one field at
a time, and the comparison must fail — or it was comparing nothing.

**What it cannot see.** With --expander: the dates (not in `l --meta`),
what the SHELL then writes (tools/vmac/sitgrade.py runs the application),
and any StuffIt reader but Expander 4.0.2. Outside the envelope tables,
anything the engine does not deliver: an entry whose archive stores a
field this engine does not read yet prints `-` and passes (the inventory
of those is OPEN_ITEMS.md's). Inside them, MacLHA's payloads, and a
MacBinary comment or FXInfo on a real file (none exists here: generator
only). The lock, against any
reader but the synthesizer. Whether a host WRITES any of it: that is
tests/mac_sink_test.c --meta, and on an emulated Mac tools/vmac/hfscat.py.
"""
import argparse
import calendar
import json
import os
import struct
import shutil
import subprocess
import tempfile
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guard                        # noqa: E402,F401  tempfile -> .tmp/
MAC_EPOCH = 2082844800                       # 1904-01-01 to 1970-01-01


def meta_rows(cli, path):
    r = subprocess.run([cli, "l", "--meta", path], capture_output=True)
    out = {}
    for line in r.stdout.decode("utf-8", "surrogateescape").splitlines():
        if not line.startswith("m "):
            continue
        f = line.split(" ", 6)
        out[f[6]] = dict(finfo=f[1], fxinfo=f[2], backup=f[3], lock=f[4],
                         comment=f[5])
    return out


def lsar_rows(path):
    r = subprocess.run(["lsar", "-j", path], capture_output=True)
    try:
        d = json.loads(r.stdout)
    except ValueError:
        return {}
    out = {}
    for e in d.get("lsarContents", []):
        if e.get("XADIsResourceFork") and e["XADFileName"] in out:
            continue                   # the data fork's row already holds it
        o = {}
        fi = e.get("XADFinderInfo")
        if fi is not None:
            b = fi.encode("latin-1")
            if len(b) >= 16:
                o["finfo"] = b[:16].hex()
            if len(b) >= 32:
                o["fxinfo"] = b[16:32].hex()
        if "XADComment" in e:
            o["comment"] = e["XADComment"].encode("mac-roman").hex()
        if "XADLastBackupDate" in e:
            t = calendar.timegm(time.strptime(e["XADLastBackupDate"][:19],
                                              "%Y-%m-%d %H:%M:%S"))
            o["backup"] = "%08x" % ((t + MAC_EPOCH) & 0xFFFFFFFF)
        out[e["XADFileName"]] = o
    return out


def compare(name, got, want, fields):
    bad = []
    for k in fields:
        if k in want and got.get(k) != want[k]:
            bad.append("%s: %s %s, wanted %s" % (name, k, got.get(k), want[k]))
    return bad


def expectations(cli):
    """[(fixture, {entry: {field: value}}, fields)]"""
    import synth_as
    import synth_sqp
    out = []
    for case in ("meta", "dosro"):
        fx = os.path.join(REPO, "fixtures", "synth-as-%s.as" % case)
        d = synth_as.describe(case)
        want = lsar_rows(fx)
        w = want.setdefault(d["name"], {})
        w["lock"] = d["locked"]
        # The design difference, stated once: the RFC's unknown.
        if d["backup"] is None:
            w["backup"] = "-"
        out.append((fx, want, ("finfo", "fxinfo", "comment", "backup",
                               "lock")))
    fx = os.path.join(REPO, "fixtures", "synth-sqp-meta.pkg")
    items, version = synth_sqp.case_meta()
    want = {}
    for path, it in synth_sqp.paths(items, version):
        rec = synth_sqp._record(it, 0, 0, 0, 0, 0)
        want[path] = {"finfo": rec[20:36].hex()}
    out.append((fx, want, ("finfo",)))
    # DiskDoubler 3.7's own compressed file (tools/vmac/ddmeta.py --writer),
    # against the catalog record it was compressed FROM: the FInfo whole,
    # the location 3.7's own Expand does not put back included.
    w = os.path.join(os.path.dirname(VMAC_HOME()), "sitmeta", "dd",
                     "writer.json")
    if os.path.exists(w):
        d = json.load(open(w))
        fx = os.path.join(REPO, ".tmp", "run_meta", "dd37-writer.dd")
        os.makedirs(os.path.dirname(fx), exist_ok=True)
        open(fx, "wb").write(bytes.fromhex(d["data"]))
        out.append((fx, {"dd37-writer": {
            "finfo": bytes.fromhex(d["before"])[4:20].hex()}}, ("finfo",)))
    else:
        print("run_meta: DiskDoubler 3.7's specimen SKIPPED: no %s" % w)
    return out


def VMAC_HOME():
    sys.path.insert(0, os.path.join(HERE, "vmac"))
    import run as R
    return R.VMAC_HOME


def corpus(cli):
    """Every fixture where the engine states a field lsar also reports."""
    bad, compared = [], 0
    fdir = os.path.join(REPO, "fixtures")
    for fn in sorted(os.listdir(fdir)):
        p = os.path.join(fdir, fn)
        if not os.path.isfile(p):
            continue
        rows = meta_rows(cli, p)
        stated = {n: {k: v for k, v in r.items() if v != "-"}
                  for n, r in rows.items()}
        if not any(stated.values()):
            continue
        oracle = lsar_rows(p)
        for n, r in stated.items():
            o = oracle.get(n)
            if o is None and len(oracle) == 1 and len(rows) == 1:
                # One entry each, named apart: a name-less AppleDouble
                # takes the host's file name, less `.ad`, here, and lsar
                # keeps it whole.
                o = next(iter(oracle.values()))
            if o is None:
                continue
            for k in ("finfo", "fxinfo", "comment", "backup"):
                if k in r and k in o:
                    compared += 1
                    if r[k] != o[k]:
                        bad.append("%s: %s: %s %s, lsar %s"
                                   % (fn, n, k, r[k], o[k]))
    return bad, compared


# --------------------------------------------------------------------
# The envelopes: MacBinary (itself, and inside ZipIt and MacGzip),
# uuencode, base64 and MIME multipart/appledouble (DECISIONS.md
# 2026-10-17, *the envelopes' own Finder info*). Kept to these functions
# and this table so that another format's additions merge beside them.
#
# Unlike corpus() above, a field the oracle states and the engine prints
# as `-` FAILS here: these are the formats whose readers deliver every
# field they hold, so a `-` is a field dropped.
# --------------------------------------------------------------------

ENV_ORACLES = {
    # name: (build script, binary under the repository, reference tree)
    "deark": ("build_deark.sh", "build/deark/deark", "reference/deark"),
    "macunpack": ("build_macunpack.sh",
                  "build/macunpack/macunpack/macunpack", "reference/macutils"),
    "hexbin": ("build_macunpack.sh", "build/macunpack/hexbin/hexbin",
               "reference/macutils"),
}


def env_oracle(name, problems):
    """An oracle binary, built if its reference tree is here. A tree that
    is here and will not build is a failure, not a skip (run_mime.build)."""
    import run_mime
    script, binary, tree = ENV_ORACLES[name]
    path, why = run_mime.build(script, binary, os.path.join(REPO, tree))
    if why:
        problems.append("%s will not build: %s" % (name, why.splitlines()[-1]))
    return path


def env_rows(cli, path):
    """(format the engine sniffed, meta_rows) in one run."""
    r = subprocess.run([cli, "l", "--meta", path], capture_output=True)
    lines = r.stdout.decode("utf-8", "surrogateescape").splitlines()
    fmt = ""
    for line in r.stderr.decode("utf-8", "surrogateescape").splitlines():
        if line.startswith(path + ": "):        # the sniffed format
            fmt = line[len(path) + 2:]
            break
    out = {}
    for line in lines:
        if line.startswith("m "):
            f = line.split(" ", 6)
            out[f[6]] = dict(finfo=f[1], fxinfo=f[2], backup=f[3], lock=f[4],
                             comment=f[5])
    return fmt, out


def deark_macbinary(deark, path):
    """deark's own reading of a MacBinary header (modules/macbinary.c, its
    debug lines): the 16 bytes of FInfo rebuilt from the fields it names,
    and its "protected" byte. None where deark does not read it as one."""
    r = subprocess.run([deark, "-l", "-d", "-m", "macbinary", path],
                       capture_output=True)
    f = {}
    for line in r.stdout.decode("latin-1").splitlines():
        line = line.replace("DEBUG:", "").strip()
        k, _, v = line.partition(": ")
        f.setdefault(k, v)
    if "type" not in f or "position in window" not in f:
        return None
    if "finder flags" in f:                      # MacBinary I: 73..74
        flags = int(f["finder flags"], 16)
        v23 = False
    else:
        flags = (int(f["finder flags (high byte)"].replace("_", ""), 16) << 8 |
                 int(f.get("finder flags (low byte)", "0x__00")
                     .replace("_", ""), 16))
        v23 = True
    h, v = (int(x) for x in f["position in window"].split(","))
    def code(v):
        # deark prints a byte it will not show as <XX> (de_bytes_to_printable)
        import re
        return re.sub(rb"<([0-9A-F]{2})>", lambda m: bytes([int(m.group(1), 16)]),
                      v[1:-1].encode("latin-1"))
    # MacBinary I's bit 7 is the lock, not System 7's isAlias, so this
    # engine keeps it out of the flags where deark prints the header as it
    # stands (DECISIONS.md 2026-10-17, *the envelopes' own Finder info*, at
    # the merge). The lock below still reads it from deark's own flags.
    shown = flags if v23 else flags & 0x7FFF
    fi = (code(f["type"]) + code(f["creator"]) +
          struct.pack(">HhhH", shown, v, h, int(f["window/folder id"])))
    prot = int(f["protected"], 16) & 1
    # The lock: "Protected" in every version, and 73's bit 7 in MacBinary
    # I, where both standards call it "Locked" (fmt_macbinary.c).
    lock = "L" if prot or (not v23 and flags & 0x8000) else "n"
    return dict(finfo=fi.hex(), lock=lock, protected=prot)


def macunpack_protected(macunpack, path, work):
    """macutils' reading of offset 81, which it names I_LOCKOFF
    (fileio/machdr.h): macunpack copies a plain file's header through, so
    the bit it writes back is the bit it read."""
    d = tempfile.mkdtemp(dir=work)
    subprocess.run([macunpack, os.path.abspath(path)], cwd=d,
                   capture_output=True)
    best = None
    for fn in os.listdir(d):
        b = open(os.path.join(d, fn), "rb").read(128)
        if len(b) == 128 and b[1] and (best is None or fn != ".bin"):
            best = b
    return None if best is None else best[81] & 1


def hexbin_finfo(hexbin, path, work):
    """hexbin's reading of a UUTool .finfo (hexbin/mu.c copies it into its
    MacBinary header at 65): 16 bytes, of which it clears inited and
    zeroes the flags' low byte, so only 0..7 and 10..15 are its."""
    d = tempfile.mkdtemp(dir=work)
    subprocess.run([hexbin, os.path.abspath(path)], cwd=d,
                   capture_output=True)
    for fn in sorted(os.listdir(d)):
        b = open(os.path.join(d, fn), "rb").read(128)
        if len(b) == 128 and b[1]:
            return b[65:81]
    return None


def begin_mode_lock(line):
    """The lock a "begin <mode>" line states: deark's reading of the mode
    (modules/xfer.c, octal after one space), and no owner write (0200,
    posix_ustar.txt) is locked. Written here rather than called, so the
    engine's own parse is not its grader."""
    parts = line.split()
    if len(parts) < 2 or not parts[1] or any(ch not in "01234567"
                                             for ch in parts[1]):
        return "-"
    return "n" if int(parts[1], 8) & 0o200 else "L"


def mime_applefiles(path):
    """Every application/applefile part, decoded by Python's own email
    package — an independent MIME reader — as (bytes, the data part's
    name or None)."""
    import email
    import email.policy
    msg = email.message_from_bytes(open(path, "rb").read(),
                                   policy=email.policy.compat32)
    out = []
    for part in msg.walk():
        if part.get_content_type() == "application/applefile":
            out.append(part.get_payload(decode=True))
    return out


def envelope_expectations(cli, work, problems):
    """[(file, {entry: {field: value}}, fields)] for the generated cases,
    each field held to a second reader where one reads it and to
    tools/synth_envelopes.py's field values where none does."""
    import synth_envelopes as se
    deark = env_oracle("deark", problems)
    macunpack = env_oracle("macunpack", problems)
    hexbin = env_oracle("hexbin", problems)
    out = []
    for case in sorted(se.CASES):
        fx = os.path.join(work, case + se.SUFFIX[case])
        open(fx, "wb").write(se.build(case))
        want = se.describe(case)
        name = next(iter(want))
        w = want[name]
        if case in se.MB:
            fields = ("finfo", "fxinfo", "comment", "backup", "lock")
            o = deark_macbinary(deark, fx) if deark else None
            if deark and o is None:
                problems.append("%s: deark does not read it as MacBinary"
                                % case)
            if o:
                w["finfo"] = o["finfo"]
                w["lock"] = o["lock"]
            if macunpack:
                p = macunpack_protected(macunpack, fx, work)
                if p is None:
                    problems.append("%s: macunpack wrote no header" % case)
                elif o and p != o["protected"]:
                    problems.append("%s: macunpack and deark disagree on "
                                    "offset 81" % case)
        elif case == "uu-mu":
            fields = ("finfo", "lock")
            b = hexbin_finfo(hexbin, fx, work) if hexbin else None
            if hexbin and b is None:
                problems.append("uu-mu: hexbin wrote no header")
            if b:
                spec = bytes.fromhex(w["finfo"])
                w["finfo"] = (b[:8] + spec[8:10] + b[10:16]).hex()
        elif case == "mime-ad":
            fields = ("finfo", "fxinfo", "comment", "backup", "lock")
            parts = mime_applefiles(fx)
            ad = os.path.join(work, "mime-ad.applefile")
            open(ad, "wb").write(parts[0] if parts else b"")
            o = lsar_rows(ad).get(name)
            if o is None:
                problems.append("mime-ad: lsar reads no applefile part")
            else:
                w.update(o)
        else:
            fields = tuple(w)
            text = se.build(case).decode("latin-1").splitlines()
            begin = next(x for x in text if x.startswith("begin"))
            w["lock"] = begin_mode_lock(begin)
        out.append((fx, want, fields))
    return out


def envelope_corpus(cli, work, problems):
    """Every fixture the engine reads as MacBinary, uuencode, base64 or
    MIME, against the second reader for each field it states, with the
    payloads of the ZipIt and MacGzip specimens in the cache. A field
    the oracle states and the engine leaves `-` fails."""
    deark = env_oracle("deark", problems)
    bad, n, rows = [], 0, []
    fdir = os.path.join(REPO, "fixtures")
    subjects = [os.path.join(fdir, f) for f in sorted(os.listdir(fdir))]
    spec = os.path.join(os.path.expanduser("~"), ".cache", "macextract",
                        "vmac", "specimens")
    for sub, pat in (("macgzip", ".gz"), ("zipit", "")):
        d = os.path.join(spec, sub)
        if os.path.isdir(d):
            subjects += [os.path.join(d, f) for f in sorted(os.listdir(d))
                         if f.endswith(pat)]
    for p in subjects:
        if not os.path.isfile(p):
            continue
        fmt, got = env_rows(cli, p)
        label = os.path.basename(p)
        if fmt == "Gzip":
            import gzip
            try:
                inner = gzip.open(p).read()
            except (OSError, EOFError):
                continue
            q = os.path.join(work, label + ".inner")
            open(q, "wb").write(inner)
            fmt, got = env_rows(cli, q)
            p = q
        if fmt == "MacBinary" and deark and len(got) == 1:
            o = deark_macbinary(deark, p)
            if o:
                rows.append((label, next(iter(got.values())),
                             {"finfo": o["finfo"], "lock": o["lock"]}))
        elif fmt == "Zip" and deark:
            rows += env_zip_payloads(cli, deark, p, label, got, work)
        elif fmt in ("uuencode", "base64"):
            lines = open(p, "rb").read().decode("latin-1").splitlines()
            begins = [x for x in lines if x.startswith("begin")]
            tags = (" .rsrc", " .finfo")
            docs = [x for x in begins if x[10:16] not in tags and
                    x[10:17] not in tags]
            mu = any(x[10:17] == " .finfo" for x in begins)
            if len(got) == 1 and len(docs) == 1:
                want = {"lock": "-" if mu else begin_mode_lock(docs[0])}
                rows.append((label, next(iter(got.values())), want))
        elif fmt == "MIME message":
            for ad in mime_applefiles(p):
                q = os.path.join(work, label + ".applefile")
                open(q, "wb").write(ad)
                for name, o in lsar_rows(q).items():
                    if name in got and o:
                        rows.append((label + ": " + name, got[name], o))
    for label, g, w in rows:
        for k, v in w.items():
            n += 1
            if g.get(k) != v:
                bad.append("%s: %s %s, oracle %s" % (label, k, g.get(k), v))
    # The control: the same rows with one stated field dropped each, as a
    # reader that stopped reading it would print them.
    caught = tried = 0
    for label, g, w in rows:
        for k in w:
            if w[k] == "-":
                continue
            h = dict(g)
            h[k] = "-"
            tried += 1
            caught += h.get(k) != w[k]
    print("run_meta: envelopes, %d field(s) of %d entries held to a second "
          "reader; %d of %d dropped-field controls caught"
          % (n, len(rows), caught, tried))
    if not rows or caught != tried:
        bad.append("envelopes: the corpus comparison is not comparing")
    return bad, n


def env_zip_payloads(cli, deark, path, label, got, work):
    """ZipIt's MacBinary payloads, taken out by Python's zipfile — an
    independent zip reader — and read by deark."""
    import zipfile
    rows = []
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        return rows
    for i in z.infolist():
        if i.filename not in got or i.is_dir():
            continue
        try:
            b = z.open(i).read()
        except Exception:                        # noqa: BLE001
            continue
        q = os.path.join(work, "zipit-payload.bin")
        open(q, "wb").write(b)
        fmt, _ = env_rows(cli, q)
        o = deark_macbinary(deark, q) if fmt == "MacBinary" else None
        if o:
            rows.append(("%s: %s" % (label, i.filename), got[i.filename],
                         {"finfo": o["finfo"], "lock": o["lock"]}))
    return rows
# ------------------------------------------------------------------
# The archive formats (branch meta-archives): PackIt, StuffIt 5, Now
# Compress, SuperDisk!, Private File, ArcMac and ARC, zip, tar, gzip, LZH.
# Their own rows, functions and controls, beside the ones above.
# ------------------------------------------------------------------

ARCHIVE_FIELDS = ("finfo", "fxinfo", "backup", "lock", "comment", "ctime",
                  "mtime")
# The formats whose dates are MS-DOS or Unix ones, which this lane holds
# against lsar; a Macintosh format's dates pass through unconverted and
# were never this branch's.
DATED = ("Zip", "Tar", "Gzip", "LZH", "ARC")


def archive_rows(cli, path, extra=()):
    """`l --meta`'s 'm' and 't' rows, both, keyed by name; and the
    format the listing names."""
    r = subprocess.run([cli, "l", "--meta"] + list(extra) + [path],
                       capture_output=True)
    out, fmt = {}, None
    for line in r.stderr.decode("utf-8", "surrogateescape").split("\n"):
        if fmt is None and line.startswith(path + ": "):
            fmt = line[len(path) + 2:]
    # "\n" and not splitlines(): a Macintosh name can hold a CR ("Icon\r").
    for line in r.stdout.decode("utf-8", "surrogateescape").split("\n"):
        if line.startswith("m "):
            f = line.split(" ", 6)
            out.setdefault(f[6], {}).update(
                finfo=f[1], fxinfo=f[2], backup=f[3], lock=f[4], comment=f[5])
        elif line.startswith("t "):
            f = line.split(" ", 3)
            out.setdefault(f[3], {}).update(ctime=f[1], mtime=f[2])
    return out, fmt


def lsar_date(s):
    try:
        t = calendar.timegm(time.strptime(s[:19], "%Y-%m-%d %H:%M:%S"))
    except ValueError:            # a year past 9999: no Mac date either
        return "-"
    return "%08x" % ((t + MAC_EPOCH) & 0xFFFFFFFF)


def archive_lsar(path):
    """lsar -j, run in UTC so that an MS-DOS time — which XADMaster
    turns into an instant in the HOST's zone — prints as the wall clock
    it was (DECISIONS.md 2026-10-17, *the archives' own Finder info*). Per
    entry: mtime, ctime, comment, lock, and whether XADMaster saw a
    Macintosh source for it (a type code, a MacBinary payload), where
    its dates are not the archive's foreign ones."""
    r = subprocess.run(["lsar", "-j", path], capture_output=True,
                       env=dict(os.environ, TZ="UTC"))
    try:
        d = json.loads(r.stdout)
    except ValueError:
        return {}, None
    props = d.get("lsarProperties") or {}
    out = {}
    for e in d.get("lsarContents", []):
        if e.get("XADIsResourceFork") and e["XADFileName"] in out:
            continue
        o = {}
        if "XADLastModificationDate" in e:
            o["mtime"] = lsar_date(e["XADLastModificationDate"])
        if "XADCreationDate" in e:
            o["ctime"] = lsar_date(e["XADCreationDate"])
        if "XADComment" in e:
            o["comment"] = e["XADComment"].encode("mac-roman", "replace").hex()
        if "XADPosixPermissions" in e:
            o["lock"] = "n" if e["XADPosixPermissions"] & 0o200 else "L"
        elif "XADDOSFileAttributes" in e:
            o["lock"] = "L" if e["XADDOSFileAttributes"] & 1 else "n"
        o["mac"] = any(k in e for k in ("XADFileType", "XADIsMacBinary",
                                        "XADMightBeMacBinary"))
        out[e["XADFileName"]] = o
    return out, props.get("XADComment")


def macunpack_locks(path, work):
    """PackIt's lock word as macunpack copies it: to byte 81..82 of each
    `.info` header it writes with -3 (reference/macutils/macunpack/pit.c,
    H_LOCKOFF). Name from the header's own byte 1 and 2..."""
    d = os.path.join(work, "mu-" + os.path.basename(path))
    os.makedirs(d, exist_ok=True)
    with open(path, "rb") as f:
        subprocess.run(["macunpack", "-3"], stdin=f, cwd=d,
                       capture_output=True)
    out = {}
    for fn in os.listdir(d):
        if fn.endswith(".info"):
            b = open(os.path.join(d, fn), "rb").read()
            if len(b) >= 83:
                out[b[2:2 + b[1]].decode("mac-roman")] = \
                    "L" if b[81] or b[82] else "n"
    return out


def maczip_want(path):
    import struct
    import zipfile
    import zlib
    want = {}
    raw = open(path, "rb").read()
    for zi in zipfile.ZipFile(path).infolist():
        o = zi.header_offset
        nl, el = struct.unpack("<HH", raw[o + 26:o + 30])
        ex, q = raw[o + 30 + nl:o + 30 + nl + el], 0
        w = {"lock": "L" if zi.external_attr & 1 else "n"}
        while q + 4 <= len(ex):
            fid, sz = struct.unpack("<HH", ex[q:q + 4])
            d = ex[q + 4:q + 4 + sz]
            if fid == 0x334d:
                fl = struct.unpack("<H", d[4:6])[0]
                rec = d[14:] if fl & 4 else zlib.decompress(d[20:], -15)
                fdflags, v, hh, fldr = struct.unpack("<HhhH", rec[:8])
                fx = struct.unpack("<HHHHBBHI", rec[8:24])
                w["finfo"] = (d[6:14] + struct.pack(">HhhH", fdflags, v, hh,
                                                    fldr)).hex()
                w["fxinfo"] = struct.pack(">HHHHBBHI", *fx).hex()
            q += 4 + sz
        want[zi.filename.rstrip("/")] = w
    return want


def archive_expectations(cli, work, problems):
    """[(label, path, want, extra args)] — generated cases, and the corpus
    rows whose oracle is a second reader rather than lsar."""
    import synth_archmeta as S
    out = []

    def gen(label, blob_want, ext, extra=()):
        blob, want = blob_want
        p = os.path.join(work, label + ext)
        open(p, "wb").write(blob)
        out.append((label, p, want, extra))

    gen("am-zip", S.zip_meta(), ".zip")
    gen("am-tar", S.tar_meta(), ".tar")
    gen("member", S.gzip_meta(), ".gz")
    gen("am-pf", S.pf_meta(), ".pf", ("-p", "swordfish"))
    gen("am-arcmac", S.arcmac_meta(), ".arc")
    gen("am-now", S.now_meta(), ".now")
    fx = os.path.join(REPO, "fixtures")
    sd = os.path.join(fx, "derived-SD__Utilities.x")
    s5 = os.path.join(fx, "derived-FloatingNotes.sit")
    for p in (sd, s5):
        if not os.path.exists(p):
            problems.append("%s is missing (fixtures/SOURCES.md)"
                            % os.path.basename(p))
            return out
    gen("am-sd", S.sd_meta(sd), ".sd")
    gen("am-sit5", S.sit5_meta(s5), ".sit")
    gen("am-sit5-badcrc", S.sit5_meta(s5, break_crc=True), ".sit")
    # A real MacZip archive: its 0x334d records decoded here as
    # Info-ZIP's own Macintosh UnZip decodes them (DecodeMac3ExtraField),
    # and the lock as its mapattr takes it, the MS-DOS read-only bit.
    rex = os.path.join(fx, "rexnebular_1_0_0.zip")
    if os.path.exists(rex):
        out.append(("rexnebular_1_0_0.zip", rex, maczip_want(rex), ()))
    # PackIt's lock word, against macunpack.
    for fn in ("derived-PackIt.pit", "synth-packit-1.pit"):
        p = os.path.join(fx, fn)
        want = {n: {"lock": v} for n, v in macunpack_locks(p, work).items()}
        if not want:
            problems.append("%s: macunpack wrote nothing" % fn)
        out.append((fn, p, want, ()))
    return out


def archive_compare(got, want, label):
    bad = []
    for name, w in want.items():
        g = got.get(name)
        if g is None:
            bad.append("%s: %s not listed" % (label, name))
            continue
        for k, v in w.items():
            if g.get(k) != v:
                bad.append("%s: %s: %s %s, wanted %s"
                           % (label, name, k, g.get(k), v))
    return bad


def lhasa_headers(archive):
    """lhasa's own dump of an archive's headers, which its test suite
    keeps beside each archive (reference/lhasa/test/output/*/NAME-hdr.txt,
    written by test/dump-headers.c): mtime from `timestamp` or, where a
    0x41 header gave one, `win_modification_time`; ctime from
    `win_creation_time`; the lock from `unix_perms`. A second reader of
    the LZH headers, and the one that reads level 0's Unix area, which
    XADMaster does not."""
    root = os.path.join(REPO, "reference", "lhasa", "test", "archives")
    rel = os.path.relpath(archive, root)
    if rel.startswith(".."):
        # A corpus fixture that is one of lhasa's archives, by content.
        import hashlib
        want = hashlib.sha256(open(archive, "rb").read()).digest()
        for r, _d, fs in os.walk(root):
            for f in fs:
                q = os.path.join(r, f)
                if hashlib.sha256(open(q, "rb").read()).digest() == want:
                    rel = os.path.relpath(q, root)
    p = os.path.join(REPO, "reference", "lhasa", "test", "output",
                     rel + "-hdr.txt")
    if rel.startswith("..") or not os.path.exists(p):
        return None
    out = {}

    def ft(v):
        t = int(v) // 10000000 - 11644473600
        return "%08x" % (t + MAC_EPOCH)
    for block in open(p, encoding="latin-1").read().split("--\n"):
        kv = dict(l.split(": ", 1) for l in block.splitlines() if ": " in l)
        name = (kv.get("path", "") + kv.get("filename", "")).rstrip("/")
        if not name:
            continue
        o = {}
        # Only an instant: lhasa turns a level 0/1 MS-DOS time into one
        # with mktime() in the zone its test outputs were written in, an
        # hour east of UTC on all of them, so those are lsar's to grade.
        unix = int(kv.get("header_level", "0")) >= 2 or \
            kv.get("os_type", "")[:2] == "85"
        if "win_modification_time" in kv:
            o["mtime"] = ft(kv["win_modification_time"])
        elif unix and int(kv.get("timestamp", "0")):
            o["mtime"] = "%08x" % (int(kv["timestamp"]) + MAC_EPOCH)
        if "win_creation_time" in kv:
            o["ctime"] = ft(kv["win_creation_time"])
        if "unix_perms" in kv and kv.get("os_type", "")[:2] != "75":
            o["lock"] = "n" if int(kv["unix_perms"], 8) & 0o200 else "L"
        out[name] = o
    return out


def archive_corpus(cli):
    """Every DATED fixture, and every lhasa test archive, against lsar:
    mtime and ctime where XADMaster saw no Macintosh source, comment and
    lock wherever both state them. Returns (fails, counts per field)."""
    paths = [os.path.join(REPO, "fixtures", f)
             for f in sorted(os.listdir(os.path.join(REPO, "fixtures")))]
    lh = os.path.join(REPO, "reference", "lhasa", "test", "archives")
    for root, _d, fs in os.walk(lh):
        paths += [os.path.join(root, f) for f in sorted(fs)]
    bad, n = [], {}
    for p in paths:
        if not os.path.isfile(p):
            continue
        rows, fmt = archive_rows(cli, p)
        if fmt not in DATED and fmt != "StuffIt 5":
            continue
        oracle, _ac = archive_lsar(p)
        lha = lhasa_headers(p) if fmt == "LZH" else None
        for name, r in rows.items():
            o = oracle.get(name)
            # lhasa lower-cases a name that is all capitals (fix_msdos_allcaps).
            if lha is not None and name not in lha and name.lower() in lha:
                lha[name] = lha[name.lower()]
            if lha is not None and name in lha:
                # lhasa's dump, where it has one, in place of lsar's
                # dates and POSIX lock: XADMaster reads neither level 0's
                # Unix area nor 0x41 right (it prints a year past 22700
                # for lhmelt's), and takes an OS/2 0xff header's mtime
                # over the base header's, which neither lhasa nor this
                # engine reads (DECISIONS.md 2026-10-17, *the archives'
                # own Finder info*).
                o = dict(o or {"mac": False})
                for k in lha[name]:
                    o.pop(k, None)
                o.update(lha[name])
                o["src"] = "lhasa"
            if o is None:
                continue
            for k in ("mtime", "ctime", "comment", "lock"):
                if k in ("mtime", "ctime") and (o["mac"] or fmt not in DATED):
                    continue
                if k not in o or o[k] == "-" or r.get(k, "-") == "-":
                    continue
                src = o.get("src", "lsar") if k != "comment" else "lsar"
                n[src + " " + k] = n.get(src + " " + k, 0) + 1
                if r[k] != o[k]:
                    bad.append("%s: %s: %s %s, %s %s"
                               % (os.path.relpath(p, REPO), name, k, r[k],
                                  src, o[k]))
    return bad, n


def archive_check(cli, corpus_too):
    """The archive lanes, their controls, and the corpus; returns fails."""
    work = tempfile.mkdtemp(prefix="meta-arch-")
    fails = []
    exp = archive_expectations(cli, work, fails)
    compared = tried = caught = 0
    for label, p, want, extra in exp:
        got, _fmt = archive_rows(cli, p, extra)
        fails += archive_compare(got, want, label)
        compared += sum(len(w) for w in want.values())
        # Control: each wanted field tampered with in the engine's row.
        for name, w in want.items():
            for k in w:
                if name not in got:
                    continue
                g = {name: dict(got[name])}
                g[name][k] = "-" if g[name].get(k) != "-" else "00"
                tried += 1
                caught += bool(archive_compare(g, {name: {k: w[k]}}, label))
    print("run_meta: archives, %d field(s) compared, %d control(s) caught "
          "of %d" % (compared, caught, tried))
    if caught != tried or not tried:
        fails.append("an archive control passed: the comparison is not "
                     "comparing")
    # The archive comment StuffIt 5 keeps behind bit 5, on the one archive
    # Aladdin wrote with one, where it is in reach.
    sample = os.path.join(os.path.expanduser("~/.cache/macextract"),
                          "sitzip", "55", "files", "Tutorial Files",
                          "Sample Archive.sit")
    if os.path.exists(sample):
        _o, want = archive_lsar(sample)
        r = subprocess.run([cli, "l", sample], capture_output=True)
        line = [x for x in r.stdout.decode("mac-roman").splitlines()
                if x.startswith("comment: ")]
        if not want or line != ["comment: " + want]:
            fails.append("Sample Archive.sit: archive comment %r, lsar %r"
                         % (line, want))
        else:
            print("run_meta: StuffIt 5 archive comment agrees with lsar")
    else:
        print("run_meta: StuffIt 5 archive comment NOT checked (no %s)"
              % sample)
    if corpus_too:
        bad, n = archive_corpus(cli)
        print("run_meta: archives' corpus against lsar: %s"
              % ", ".join("%s %d" % kv for kv in sorted(n.items())))
        fails += bad
    shutil.rmtree(work, ignore_errors=True)
    return fails


def meta_list(cli, path):
    """`l --meta`, in archive order: [(name, row)]."""
    r = subprocess.run([cli, "l", "--meta", path], capture_output=True)
    out = []
    for line in r.stdout.decode("utf-8", "surrogateescape").splitlines():
        if line.startswith("m "):
            f = line.split(" ", 6)
            out.append((f[6], dict(finfo=f[1], fxinfo=f[2], backup=f[3],
                                   lock=f[4])))
    return out


def sitmeta_results():
    """[(tag, archive result)] from tools/vmac/sitmeta.py's results
    directory, corpus and sentinel boots only."""
    import glob
    sys.path.insert(0, os.path.join(HERE, "vmac"))
    import sitmeta
    out = []
    for p in sorted(glob.glob(os.path.join(sitmeta.RESULTS, "*.json"))):
        r = json.load(open(p))
        if r["tag"].startswith(("corpus", "synth")):
            out += [(r["tag"], a) for a in r["archives"]]
    return out


def sit_archive(a):
    """The bytes Expander was given: a corpus fixture, or a sentinel
    archive rebuilt by sitmeta.py's own generator; None unless they hash
    to what the boot recorded."""
    import hashlib
    sys.path.insert(0, os.path.join(HERE, "vmac"))
    import sitmeta
    name = a["fixture"]
    blob = None
    if name.startswith("synth-") and name.endswith(".sit"):
        tag = name[6:-4]
        for n, kw, _w in sitmeta.SYNTH_SET + sitmeta.SYNTH_SET2 + \
                sitmeta.SYNTH_SET3:
            if n == tag:
                blob = sitmeta.synth_archive(top=n.encode(), **kw)
    else:
        p = os.path.join(REPO, "fixtures", name)
        if os.path.exists(p):
            blob = open(p, "rb").read()
    if blob is None or hashlib.sha256(blob).hexdigest() != a["sha256"]:
        return None
    return blob


def expander_want(kind, rec):
    """What Expander wrote, in `l --meta`'s vocabulary (hfscat.py's
    record layouts)."""
    if kind == "file":
        return dict(finfo=rec[4:20].hex(), fxinfo=rec[56:72].hex(),
                    backup="%08x" % int.from_bytes(rec[52:56], "big"),
                    lock="L" if rec[2] & 1 else "n")
    return dict(finfo=rec[22:38].hex(), fxinfo=rec[38:54].hex(),
                backup="%08x" % int.from_bytes(rec[18:22], "big"))


def printable(t):
    return "".join(ch for ch in t if ord(ch) >= 0x20)


def as_written(row):
    """An engine row as a host writes it on a new entry: what is not
    stated stays zero, and a lock not stated is no lock."""
    return dict(finfo="00" * 16 if row["finfo"] == "-" else row["finfo"],
                fxinfo="00" * 16 if row["fxinfo"] == "-" else row["fxinfo"],
                backup="00000000" if row["backup"] == "-" else row["backup"],
                lock="L" if row["lock"] == "L" else "n")


def expander(cli):
    """(failures, fields compared, archives graded, left out, pairs)
    where pairs is [(label, got, want)] for the controls."""
    res = sitmeta_results()
    if not res:
        return None
    tmp = os.path.join(REPO, ".tmp", "run_meta")
    os.makedirs(tmp, exist_ok=True)
    bad, n, graded, left, pairs = [], 0, 0, [], []
    for tag, a in res:
        ents = [e for e in a["entries"] if e["kind"] != "end"]
        if any("match" not in e for e in ents):
            left.append("%s (%s): not extracted whole by Expander"
                        % (a["fixture"], tag))
            continue
        blob = sit_archive(a)
        if blob is None:
            left.append("%s (%s): absent here, or not the bytes Expander "
                        "was given" % (a["fixture"], tag))
            continue
        p = os.path.join(tmp, "x-" + a["fixture"])
        open(p, "wb").write(blob)
        rows = meta_list(cli, p)
        os.unlink(p)
        if len(rows) != len(ents):
            bad.append("%s: the engine lists %d entries, Expander wrote %d"
                       % (a["fixture"], len(rows), len(ents)))
            continue
        graded += 1
        for (name, row), e in zip(rows, ents):
            # Order is what pairs them (both walks stop at the same
            # header); the leaf is a sanity check, compared as printable
            # text because the CLI drops control bytes (`Icon\r`).
            leaf = printable(bytes.fromhex(e["path"][-1]).decode("mac-roman"))
            mine = printable(name.split("/")[-1])
            if mine[:31] != leaf[:31] and mine.replace(":", "/")[:31] \
                    != leaf[:31]:
                bad.append("%s: entry order: %r against Expander's %r"
                           % (a["fixture"], name, leaf))
                continue
            want = expander_want(e["kind"], bytes.fromhex(e["match"]["rec"]))
            got = as_written(row)
            label = "%s: %s" % (a["fixture"], name)
            for k in want:
                n += 1
                pairs.append((label, e["kind"] + " " + k, got[k], want[k]))
                if got[k] != want[k]:
                    bad.append("%s: %s %s, Expander wrote %s"
                               % (label, k, got[k], want[k]))
    return bad, n, graded, left, pairs


def expander_controls(pairs):
    """Each field of each kind (a file's four, a folder's three), tampered
    with on the first entry where the engine and Expander agree, must be
    caught: a bit flipped in the bytes, the lock inverted."""
    caught, seen = 0, set()
    for label, k, got, want in pairs:
        if k in seen or got != want:
            continue
        seen.add(k)
        if k.endswith("lock"):
            g = "n" if got == "L" else "L"
        else:
            g = got[:-1] + "%x" % (int(got[-1], 16) ^ 1)
        caught += g != want
    return caught, len(seen)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cli", default=os.path.join(REPO, "build", "macextract"))
    ap.add_argument("--corpus", action="store_true")
    ap.add_argument("--expander", action="store_true")
    a = ap.parse_args()

    fails, n = [], 0
    exp = expectations(a.cli)
    envwork = tempfile.mkdtemp(prefix="meta-env-")
    exp += envelope_expectations(a.cli, envwork, fails)
    for fx, want, fields in exp:
        if not os.path.exists(fx):
            print("run_meta: %s is missing — generate it (fixtures/SOURCES.md)"
                  % os.path.basename(fx))
            return 1
        got = meta_rows(a.cli, fx)
        for name, w in want.items():
            g = got.get(name)
            if g is None:
                fails.append("%s: %s not listed" % (os.path.basename(fx), name))
                continue
            n += sum(1 for k in fields if k in w)
            fails += compare("%s: %s" % (os.path.basename(fx), name), g, w,
                             fields)

    # The controls: each field tampered with in turn must be caught.
    caught = 0
    tried = 0
    for fx, want, fields in exp:
        got = meta_rows(a.cli, fx)
        for name, w in want.items():
            for k in fields:
                if k not in w or name not in got:
                    continue
                g = dict(got[name])
                g[k] = "-" if g[k] != "-" else "00"
                tried += 1
                caught += bool(compare(name, g, w, (k,)))
    print("run_meta: %d field(s) compared, %d control(s) caught of %d"
          % (n, caught, tried))
    if caught != tried or not tried:
        fails.append("a control passed: the comparison is not comparing")

    if a.corpus:
        bad, c = corpus(a.cli)
        print("run_meta: corpus, %d stated field(s) held against lsar" % c)
        fails += bad
        bad, c = envelope_corpus(a.cli, envwork, fails)
        fails += bad

    if a.expander:
        r = expander(a.cli)
        if r is None:
            print("run_meta: --expander SKIPPED: no sitmeta.py results "
                  "(tools/vmac/README.md, *Finder info, read back*)")
        else:
            bad, c, graded, left, pairs = r
            caught, tried = expander_controls(pairs)
            print("run_meta: Expander 4.0.2, %d archive(s), %d field(s) "
                  "held against what it wrote; %d left out; %d control(s) "
                  "caught of %d" % (graded, c, len(left), caught, tried))
            for x in left:
                print("run_meta:   left out: %s" % x)
            if caught != tried or tried != 7:
                bad.append("an Expander control passed, or a field of a "
                           "file or a folder was never compared")
            fails += bad
    fails += archive_check(a.cli, a.corpus)

    for f in fails:
        print("run_meta: FAIL %s" % f)
    print("run_meta: %s" % ("OK" if not fails else "%d FAILED" % len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
