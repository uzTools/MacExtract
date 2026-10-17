#!/usr/bin/env python3
"""run_meta.py — the engine's Finder metadata beyond type, creator and flags.

    tools/run_meta.py [--cli build/macextract] [--corpus]

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
  --corpus                              every fixture: wherever the engine
      states a field and `lsar` reports the same field, they must agree.
  the envelopes (envelope_expectations, envelope_corpus)
      MacBinary, uuencode, base64 and MIME multipart/appledouble, generated
      by tools/synth_envelopes.py and swept over the corpus, against deark,
      macunpack, hexbin, Python's email and zipfile, and lsar. There, a
      field the oracle states and the engine prints `-` FAILS.

Then a CONTROL per field: the engine's row is tampered with, one field at
a time, and the comparison must fail — or it was comparing nothing.

**What it cannot see.** Outside the envelope tables, anything the engine
does not deliver: an entry whose archive stores a field this engine does
not read yet prints `-` and passes (the inventory of those is
OPEN_ITEMS.md's). Inside them, MacLHA's payloads, and a MacBinary comment
or FXInfo on a real file (none exists here: generator only). The lock, against any
reader but the synthesizer. Whether a host WRITES any of it: that is
tests/mac_sink_test.c --meta, and on an emulated Mac tools/vmac/hfscat.py.
"""
import argparse
import calendar
import json
import os
import struct
import subprocess
import sys
import tempfile
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
    return out


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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cli", default=os.path.join(REPO, "build", "macextract"))
    ap.add_argument("--corpus", action="store_true")
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

    for f in fails:
        print("run_meta: FAIL %s" % f)
    print("run_meta: %s" % ("OK" if not fails else "%d FAILED" % len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
