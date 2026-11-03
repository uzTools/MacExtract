#!/usr/bin/env python3
"""run_mar.py — MAR (src/fmt_mar.c), graded against what wrote it.

    run_mar.py [--macextract BIN]     grade, and the variants below
    run_mar.py --manifests            (re)write the four MAR manifests

Nothing else reads MAR here: `unar`, deark and macutils have never heard
of it, and the author's own READERS are GPL-2.0-only and are not run
(NOTICE). What grades the engine instead:

  mar-wild-mar020.mar,    hampa's own two archives (mar 0.2.0 and its
  mar-wild-mar020src.mar  source). Every block and header carries his
                          writer's CRC-32, which walk() below checks
                          independently of the engine — a wrong reading of
                          the layout cannot pass 288 of them. And hampa
                          published the same two folders as StuffIt
                          archives (mar-twin-*.sit, graded against `unar`
                          by run_diff.py): every fork the engine takes out
                          of a .mar must be the one it takes out of the
                          twin, except bytes 16..255 of a resource fork —
                          the header's reserved area, where the two
                          copies were made at different times and differ
                          by up to 9 bytes. Those bytes are vouched for by
                          the CRC alone, and the count of forks relying on
                          that is printed.
  synth-mar-single.mac,   tools/synth_mar.py's items, field for field:
  synth-mar-tree.mar      names, both forks, the 16 bytes of Finder info
                          (inited and on-desk cleared on the first item, as
                          mar 0.2.0's expander does), a folder's scroll, the
                          lock, the comment cut at 255 bytes and both dates
                          (`l --meta`).

Then variants, each with what must happen:

  a header byte changed          refused: not MAR at offset 0, corrupt later
  a fork byte changed            that entry fails its CRC, the rest come out
  a comment byte changed         that entry fails, the rest come out
  a fork's CRC changed           that entry fails
  cut at every record and mid-   never exit 0
    block
  bytes after the archive's end  ignored: the same forks, exit 0
  '----' as the first record     not MAR
  2,000 empty files in a folder  the progress callback every 8 KB at most
    (build/*/tick_probe beside   — headers are all there is to count
    the CLI)
  LZW-wrapped, 9, 12 and 16 bits the same forks, through the .Z envelope;
    (mar 0.2.0's encoder,        gzip -dc gives back the archive byte for
    synth_mar.py --lzw)          byte

And the author's own writers, where their output is in the specimen
cache (skipped, and said so, where it is not):

  ~/.cache/macextract/vmac/specimens/mar/unix/   `mar -c` from mac-utils
      (tools/mar_unix.py): every field of each subject — both forks, type,
      creator, Finder flags (inited cleared on the first item), location,
      a folder's view, the lock, both dates.
  ~/.cache/macextract/vmac/specimens/mar/mac/    mar 0.2.0 on System 6.0.8
      (tools/vmac/marenc.py): Encode and Compress, a folder and a file;
      both forks of every subject file, and the Finder type each archive
      was given (written.json). Its Finder fields are what the Finder had
      set on the volume, so they are not graded.

And a CONTROL for each comparison: an expectation changed in one field,
or an LZW stream padded after a clear, must fail, or the comparison was
comparing nothing.

**What it cannot see.** The writer of the synthetic cases is this
repository's reading of the format, so for them the engine is graded
against that reading; the wild archives grade the reading, but they have
no lock, no comment, no empty folder and no single-file `.mac`. A real
LZW-compressed archive (Command-key encode) has not been seen; the encoder
is a port. An LZ4-wrapped archive, which mar 0.2.0 also reads, is not
read here (OPEN_ITEMS.md). What the Macintosh shell writes from these
rows: tests/mac_sink_test.c and the emulator (tools/vmac/README.md).
"""
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import synth_mar  # noqa: E402

FIX = os.path.join(ROOT, "fixtures")
MAN = os.path.join(FIX, "manifests")
WILD = {"mar-wild-mar020.mar": "mar-twin-mar020.sit",
        "mar-wild-mar020src.mar": "mar-twin-mar020src.sit"}
SYNTH = {"synth-mar-single.mac": "single", "synth-mar-tree.mar": "tree"}

FAILS = []


def fail(msg):
    FAILS.append(msg)
    print("  FAIL", msg)


def walk(blob):
    """The archive's items, every CRC checked: the layout as src/fmt_mar.c
    states it, read by a second hand. Raises on any CRC that fails."""
    items, stack, pos = [], [], 0
    while True:
        h = blob[pos:pos + 128]
        if len(h) < 128 or h[:4] != b"MAR\x80":
            raise ValueError("no record at %d" % pos)
        if synth_mar.crc32(h[:124]) != struct.unpack(">I", h[124:])[0]:
            raise ValueError("header CRC at %d" % pos)
        kind = h[4:8]
        pos += 128
        if kind == b"----":
            stack.pop()
            if not stack:
                return items, pos
            continue
        name = h[9:9 + min(h[8], 63)].replace(b"/", b":").decode("mac_roman")
        path = "/".join(stack + [name])
        dl, rl, cl, fl, ct, mt = struct.unpack(">IIIIII", h[72:96])
        fi = bytearray(h[96:112])
        if not items:
            fi[8] &= 0xFE
            fi[9] &= 0xFE
        row = {"name": path, "finder_flags": struct.unpack(">H", h[104:106])[0],
               "finfo": fi.hex(), "ctime": ct, "mtime": mt}
        if kind == b"fold":
            row.update(is_dir=True, fxinfo=h[112:116].hex() + "00" * 12)
            items.append(row)
            stack.append(name)
            continue
        if kind != b"file":
            raise ValueError("record %r at %d" % (kind, pos - 128))
        forks = []
        for n in (dl, rl, cl):
            d = blob[pos:pos + n]
            if n:
                want = struct.unpack(">I", blob[pos + n:pos + n + 4])[0]
                if len(d) < n or synth_mar.crc32(d) != want:
                    raise ValueError("block CRC at %d" % pos)
                pos += (n + 4 + 127) & ~127
            forks.append(d)
        row.update(type=h[96:100].decode("mac_roman"),
                   creator=h[100:104].decode("mac_roman"),
                   data=forks[0].hex(), rsrc=forks[1].hex(),
                   comment=forks[2][:255].hex(), locked=bool(fl & 1))
        items.append(row)
        if not stack:
            return items, pos


def run(cli, *args):
    return subprocess.run([cli] + list(args), capture_output=True)


def meta(cli, path):
    """`l --meta`, keyed by name: the m row's fields and the t row's
    two dates."""
    r = run(cli, "l", "--meta", path)
    rows = {}
    for line in r.stdout.decode("utf-8", "surrogateescape").splitlines():
        p = line.split(" ", 6)
        if p[0] == "m" and len(p) == 7:
            rows.setdefault(p[6], {}).update(fi=p[1], fx=p[2], lock=p[4],
                                             cmt=p[5])
        elif p[0] == "t":
            q = line.split(" ", 3)
            rows.setdefault(q[3], {}).update(ct=q[1], mt=q[2])
    return r.returncode, rows


def extract(cli, path, out, extra=()):
    r = run(cli, "x", "--forks", "hidden", "-o", out, *extra, path)
    forks = {}
    for dp, _, fn in os.walk(out):
        for f in fn:
            rel = os.path.relpath(os.path.join(dp, f), out)
            side = os.path.basename(rel).startswith("._")
            key = os.path.join(os.path.dirname(rel),
                               os.path.basename(rel)[2:]) if side else rel
            forks.setdefault(key, [b"", b""])[1 if side else 0] = \
                open(os.path.join(dp, f), "rb").read()
    return r.returncode, forks


def compare_items(label, items, rows, forks):
    """Every field of every item; returns the number of problems."""
    bad = 0

    def miss(msg):
        nonlocal bad
        bad += 1
        return msg
    for it in items:
        n = it["name"]
        m = rows.get(n)
        if m is None:
            yield miss(f"{label}: {n!r} not listed")
            continue
        if m.get("fi") != it["finfo"]:
            yield miss(f"{label}: {n!r} Finder info {m.get('fi')} != {it['finfo']}")
        want_fx = it.get("fxinfo", "-")
        if m.get("fx") != want_fx:
            yield miss(f"{label}: {n!r} FXInfo {m.get('fx')} != {want_fx}")
        for k, v in (("ct", it["ctime"]), ("mt", it["mtime"])):
            want = "%08x" % v if v else "-"
            if m.get(k) != want:
                yield miss(f"{label}: {n!r} {k} {m.get(k)} != {want}")
        if it.get("is_dir"):
            continue
        lock = "L" if it["locked"] else "n"
        if m.get("lock") != lock:
            yield miss(f"{label}: {n!r} lock {m.get('lock')} != {lock}")
        cmt = it["comment"] or "-"
        if m.get("cmt") != cmt:
            yield miss(f"{label}: {n!r} comment differs")
        if forks is not None:
            got = forks.get(n.replace(":", ":"))
            if got is None:
                yield miss(f"{label}: {n!r} not extracted")
            elif got[0].hex() != it["data"] or got[1].hex() != it["rsrc"]:
                yield miss(f"{label}: {n!r} forks differ")


def grade(cli, label, path, items):
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, ".tmp")) as t:
        rc, rows = meta(cli, path)
        xrc, forks = extract(cli, path, os.path.join(t, "x"))
        # The CLI writes a ':' in a name as itself; the engine's swap of
        # '/' is what `l` shows, and the file on disk carries the same.
        probs = list(compare_items(label, items, rows, forks))
        if rc or xrc:
            probs.append(f"{label}: exit {rc}/{xrc}")
        nfiles = sum(1 for i in items if not i.get("is_dir"))
        if len(forks) != nfiles:
            probs.append(f"{label}: {len(forks)} files written, {nfiles} items")
        return probs, rows, forks


def manifests(cli):
    for fx in list(WILD) + list(SYNTH):
        path = os.path.join(FIX, fx)
        items, _ = walk(open(path, "rb").read())
        ents = []
        for it in items:
            if it.get("is_dir"):
                ents.append({"is_dir": True, "name": it["name"]})
                continue
            d, r = bytes.fromhex(it["data"]), bytes.fromhex(it["rsrc"])
            ents.append({"creator": it["creator"],
                         "data_sha256": hashlib.sha256(d).hexdigest(),
                         "data_size": len(d),
                         "finder_flags": it["finder_flags"],
                         "name": it["name"],
                         "rsrc_sha256": hashlib.sha256(r).hexdigest(),
                         "rsrc_size": len(r), "type": it["type"]})
        blob = open(path, "rb").read()
        oracle = ("every block's CRC-32 as hampa's writer stored it "
                  "(tools/run_mar.py walk), and the forks of its StuffIt "
                  "twin " + WILD[fx]) if fx in WILD else \
            ("tools/synth_mar.py --case " + SYNTH[fx] +
             "'s items, every CRC checked by tools/run_mar.py walk")
        man = {"entries": ents, "fixture": fx, "format": "MAR",
               "oracle": oracle,
               "sha256": hashlib.sha256(blob).hexdigest(), "size": len(blob)}
        with open(os.path.join(MAN, fx + ".json"), "w") as f:
            json.dump(man, f, indent=1, sort_keys=True)
            f.write("\n")
        print("wrote", fx + ".json", len(ents), "entries")


def main():
    args = sys.argv[1:]
    cli = os.path.join(ROOT, "build", "macextract")
    if "--macextract" in args:
        cli = args[args.index("--macextract") + 1]
    if "--manifests" in args:
        manifests(cli)
        return 0
    os.makedirs(os.path.join(ROOT, ".tmp"), exist_ok=True)
    work = tempfile.mkdtemp(dir=os.path.join(ROOT, ".tmp"), prefix="run_mar.")
    try:
        return lanes(cli, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


SPEC = os.path.join(os.environ.get("UNC_VMAC_HOME", os.path.expanduser(
    "~/.cache/macextract/vmac")), "specimens", "mar")


def writers(cli, work):
    """The author's two writers' output, against their subjects."""
    import mar_unix as U
    n = 0
    unix = os.path.join(SPEC, "unix")
    for name in ("tree.mar", "single.mac"):
        p = os.path.join(unix, name)
        jp = os.path.splitext(p)[0] + ".json"
        if not (os.path.exists(p) and os.path.exists(jp)):
            print(f"run_mar: no {p} — mac-utils' writer not graded "
                  f"(tools/mar_unix.py makes it)")
            continue
        want = json.load(open(jp))
        rc, rows = meta(cli, p)
        xrc, forks = extract(cli, p, os.path.join(work, "u-" + name))
        if rc or xrc:
            fail(f"unix {name}: exit {rc}/{xrc}")
        top = min(want, key=len)
        for path, w in want.items():
            m = rows.get(path)
            if m is None:
                fail(f"unix {name}: {path!r} not listed")
                continue
            fi = bytes.fromhex(m["fi"])
            fl = fi[8] << 8 | fi[9]
            if "flags" in w:
                wf = w["flags"] & (0xFEFE if path == top else 0xFFFF)
                if fl != wf:
                    fail(f"unix {name}: {path!r} flags {fl:#06x} != {wf:#06x}")
                v, h = int.from_bytes(fi[10:12], "big", signed=True), \
                    int.from_bytes(fi[12:14], "big", signed=True)
                if (v, h) != (w["v"], w["h"]):
                    fail(f"unix {name}: {path!r} location {(v, h)}")
            for k in ("ctime", "mtime"):
                if k in w and m.get("ct" if k == "ctime" else "mt") != "%08x" % w[k]:
                    fail(f"unix {name}: {path!r} {k}")
            if "unix_mtime" in w and m.get("mt") != "%08x" % (
                    w["unix_mtime"] + 2082844800):
                fail(f"unix {name}: {path!r} the Unix date")
            if w.get("is_dir"):
                if "view" in w and int.from_bytes(fi[14:16], "big") != w["view"]:
                    fail(f"unix {name}: {path!r} view")
                continue
            if "type" in w and fi[:8].decode("mac_roman") != w["type"] + w["creator"]:
                fail(f"unix {name}: {path!r} type/creator")
            if "locked" in w and m.get("lock") != ("L" if w["locked"] else "n"):
                fail(f"unix {name}: {path!r} lock {m.get('lock')}")
            got = forks.get(path)
            if got is None or got[0].hex() != w["data"] or got[1].hex() != w["rsrc"]:
                fail(f"unix {name}: {path!r} forks differ")
            n += 1
        print(f"run_mar: mac-utils' writer, {name}: {len(want)} items, every field")
    mac = os.path.join(SPEC, "mac")
    wj = os.path.join(mac, "written.json")
    if not os.path.exists(wj):
        print(f"run_mar: no {wj} — mar 0.2.0's own archives not graded "
              f"(tools/vmac/marenc.py --make writes them)")
        return n
    written = json.load(open(wj))
    want_type = {"Subject.mar": "MARd", "Subject.mar.Z": "ZIVU",
                 "Two Forks.mac": "MARf", "Two Forks.mac.Z": "ZIVU"}
    files = {"Subject/Locked": (U.FILES["locked"]["data"], b""),
             "Subject/Inner/Rsrc Only": (b"", U.FILES["rsrconly"]["rsrc"]),
             "Two Forks": (U.FILES["both"]["data"], U.FILES["both"]["rsrc"])}
    for name, typ in want_type.items():
        p = os.path.join(mac, name)
        if name not in written or not os.path.exists(p):
            fail(f"mar 0.2.0: {name} missing — a partial set")
            continue
        if (written[name]["type"], written[name]["creator"]) != (typ, "MARc"):
            fail(f"mar 0.2.0: {name} typed {written[name]}")
        rc, forks = extract(cli, p, os.path.join(work, "m-" + name))
        mine = {k: v for k, v in files.items()
                if k.split("/")[0] == name.split(".")[0]}
        if rc or {k: tuple(forks.get(k, [None, None])) for k in mine} != mine \
                or len(forks) != len(mine):
            fail(f"mar 0.2.0: {name}: exit {rc}, forks differ")
        n += len(mine)
    print(f"run_mar: mar 0.2.0's own archives: {len(want_type)} "
          f"(MARd, MARf, two ZIVU), every fork, every type")
    return n


def lanes(cli, work):
    graded = 0

    # 1. The synthetic cases against their generator, and the committed
    #    fixture against a fresh generation.
    for fx, case in SYNTH.items():
        want = synth_mar.describe(synth_mar.CASES[case])
        p = os.path.join(work, fx)
        with open(p, "wb") as f:
            f.write(synth_mar.write(synth_mar.CASES[case]))
        fixp = os.path.join(FIX, fx)
        if os.path.exists(fixp) and open(fixp, "rb").read() != open(p, "rb").read():
            fail(f"{fx}: the fixture is not what synth_mar.py --case {case} writes")
        walked, _ = walk(open(p, "rb").read())
        if walked != want:
            fail(f"{fx}: walk() and the generator disagree")
        probs, rows, forks = grade(cli, fx, p, want)
        for m in probs:
            fail(m)
        graded += len(want)
        # Control: one field of the expectation changed must be noticed.
        for field in ("finfo", "comment", "locked", "rsrc", "mtime"):
            bent = json.loads(json.dumps(want))
            tgt = next(i for i in bent if not i.get("is_dir"))
            tgt[field] = {"finfo": "00" * 16, "comment": "41",
                          "locked": not tgt["locked"], "rsrc": "41",
                          "mtime": 12345}[field]
            if not list(compare_items("control", bent, rows, forks)):
                fail(f"{fx}: control on {field} was not noticed")
    print(f"run_mar: synthetic: {graded} items field for field, 10 controls")

    # 2. The wild archives: every CRC, then the twins.
    allowance = 0
    for fx, twin in WILD.items():
        p, tp = os.path.join(FIX, fx), os.path.join(FIX, twin)
        if not os.path.exists(p):
            print(f"run_mar: {fx} absent — skipped, and that is a gap")
            continue
        blob = open(p, "rb").read()
        items, end = walk(blob)
        if end != len(blob):
            fail(f"{fx}: the archive ends at {end} of {len(blob)}")
        probs, _, forks = grade(cli, fx, p, items)
        for m in probs:
            fail(m)
        if not os.path.exists(tp):
            fail(f"{fx}: its twin {twin} is absent")
            continue
        _, tw = extract(cli, tp, os.path.join(work, twin))
        # The twin's folder may sit one level down (a StuffIt archive of
        # the folder's contents rather than of the folder).
        top = items[0]["name"]
        tw = {(k if k.startswith(top + "/") or k == top else top + "/" + k): v
              for k, v in tw.items()}
        for k, (d, r) in forks.items():
            if k not in tw:
                fail(f"{fx}: {k!r} has no twin")
                continue
            td, tr = tw[k]
            if d != td:
                fail(f"{fx}: {k!r} data fork differs from the twin's")
            if r != tr:
                diff = [i for i in range(max(len(r), len(tr)))
                        if i >= len(r) or i >= len(tr) or r[i] != tr[i]]
                if len(r) == len(tr) and all(16 <= i < 256 for i in diff):
                    allowance += 1
                else:
                    fail(f"{fx}: {k!r} resource fork differs from the twin's "
                         f"outside its reserved header")
        if set(tw) - set(forks):
            fail(f"{fx}: the twin has {sorted(set(tw) - set(forks))[:3]}")
        graded += len(items)
        print(f"run_mar: {fx}: {len(items)} items, every CRC, "
              f"{len(forks)} files against {twin}")
    print(f"run_mar: {allowance} resource forks equal the twin's only outside "
          f"bytes 16..255, which the CRC alone vouches for")

    # 3. Variants of the tree case.
    base = synth_mar.write(synth_mar.CASES["tree"])
    want = synth_mar.describe(synth_mar.CASES["tree"])
    nfiles = sum(1 for i in want if not i.get("is_dir"))

    def variant(name, blob):
        p = os.path.join(work, name)
        with open(p, "wb") as f:
            f.write(blob)
        return p

    def xrun(p):
        out = os.path.join(work, "v")
        shutil.rmtree(out, ignore_errors=True)
        rc, forks = extract(cli, p, out)
        return rc, forks

    # Offsets out of walk's own reading of the tree.
    recs, pos = [], 0
    while pos < len(base):
        h = base[pos:pos + 128]
        recs.append((pos, h[4:8]))
        dl, rl, cl = struct.unpack(">III", h[72:84])
        pos += 128 + sum((n + 4 + 127) & ~127 for n in (dl, rl, cl) if n)
    both = next(p for p, k in recs if base[p + 9:p + 19] == b"Both Forks")

    cases = 0
    rc, _ = xrun(variant("hdr0", base[:5] + bytes([base[5] ^ 1]) + base[6:]))
    sn = run(cli, "sniff", os.path.join(work, "hdr0")).stdout.decode()
    if "MAR" in sn or rc == 0:
        fail("first header changed: still MAR, or exit 0")
    cases += 1
    b = bytearray(base)
    b[both + 20] ^= 1
    rc, f = xrun(variant("hdr1", bytes(b)))
    if rc == 0:
        fail("a later header changed: exit 0")
    cases += 1
    for what, off in (("data", both + 128 + 7), ("crc", both + 128 + 5000),
                      ("rsrc", both + 128 + 5120 + 3)):
        b = bytearray(base)
        b[off] ^= 0x10
        rc, f = xrun(variant("fork-" + what, bytes(b)))
        if rc == 0 or len(f) != nfiles:
            fail(f"a {what} byte changed: exit {rc}, {len(f)} of {nfiles} files")
        cases += 1
    cmt_at = next(p for p, k in recs if base[p + 9:p + 18] == b"A/B slash")
    b = bytearray(base)
    b[cmt_at + 128 + 256 + 9] ^= 1     # the comment, after a 129-byte fork
    rc, f = xrun(variant("cmt", bytes(b)))
    if rc == 0 or len(f) != nfiles:
        fail(f"a comment byte changed: exit {rc}, {len(f)} of {nfiles} files")
    cases += 1
    cuts = sorted({p for p, _ in recs[1:]} | {p + 77 for p, _ in recs} |
                  {len(base) - 1, len(base) - 128})
    for c in cuts:
        rc, _ = xrun(variant("cut", base[:c]))
        if rc == 0:
            fail(f"cut at {c} of {len(base)}: exit 0")
        cases += 1
    rc, f = xrun(variant("tail", base + b"trailing bytes" * 20))
    if rc or {k: v for k, v in f.items()} != {
            i["name"]: [bytes.fromhex(i["data"]), bytes.fromhex(i["rsrc"])]
            for i in want if not i.get("is_dir")}:
        fail(f"bytes after the end: exit {rc} or different forks")
    cases += 1
    endrec = synth_mar.header(b"----", b"")
    sn = run(cli, "sniff", variant("endfirst", endrec + base)).stdout.decode()
    if "MAR" in sn:
        fail("'----' first: sniffed as MAR")
    cases += 1
    print(f"run_mar: {cases} damaged, cut and padded variants of the tree")

    # An archive that is nothing but headers must still call back
    # (CLAUDE.md: every 8-16 KB). tick_probe is built beside the CLI.
    probe = os.path.join(os.path.dirname(os.path.abspath(cli)), "tick_probe")
    if os.path.exists(probe):
        empties = [("fold", b"F", dict(flags=0x10, finfo=bytes(16)),
                    [("file", b"e%04d" % i, dict(finfo=bytes(16)))
                     for i in range(2000)])]
        p = variant("empties.mar", synth_mar.write(empties))
        r = subprocess.run([probe, p], capture_output=True, text=True)
        f = dict(kv.split("=") for kv in r.stdout.split()[1:] if "=" in kv)
        if f.get("ret") != "0" or int(f.get("ticks", 0)) < 1 or \
                int(f.get("max_gap", 1 << 30)) > 16384:
            fail(f"2,000 empty files: {r.stdout.strip()}")
        print(f"run_mar: 2,000 empty files tick {f.get('ticks')} times, "
              f"gap at most {f.get('max_gap')} B")
    else:
        print(f"run_mar: no {probe} — the progress check is skipped")

    # 4. LZW-wrapped, as mar 0.2.0's Command-key encode writes.
    lz = 0
    gz = shutil.which("gzip")
    for src in [("tree", base)] + [
            (fx, open(os.path.join(FIX, fx), "rb").read())
            for fx in ("mar-wild-mar020.mar",)
            if os.path.exists(os.path.join(FIX, fx))]:
        plain_rc, plain = xrun(variant("plain.mar", src[1]))
        for bits in (9, 12, 16):
            z = synth_mar.lzw(src[1], bits)
            rc, f = xrun(variant("lzw.mar", z))
            if rc or f != plain:
                fail(f"{src[0]} LZW {bits}: exit {rc}, forks differ")
            if gz:
                g = subprocess.run([gz, "-dc"], input=z, capture_output=True)
                if g.stdout != src[1]:
                    fail(f"{src[0]} LZW {bits}: gzip -dc disagrees")
            lz += 1
    # Control: a byte of padding after the first clear, which mar 0.2.0's
    # encoder does not write; read as if it did, the stream must not come
    # out the same.
    ctl = synth_mar.lzw(src[1], 9, pad_after_clear=True)
    rc, f = xrun(variant("lzw-ctl.mar", ctl))
    if rc == 0 and f == plain:
        fail("LZW control (padding after a clear) was not noticed")
    print(f"run_mar: {lz} LZW-wrapped archives, gzip agreeing; control fails")

    graded += writers(cli, work)

    print(f"run_mar: {'FAIL' if FAILS else 'OK'} — {graded} items graded, "
          f"{len(FAILS)} problems")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
