#!/usr/bin/env python3
"""run_abk.py — Apple Backup (src/fmt_abk.c), graded by two other readers.

    run_abk.py [--macextract BIN]

`unar`, macunpack and deark have never heard of the format. What grades
the engine instead, both fetched by tools/fetch_references.sh into
reference/applebackup/ and neither written here:

  unbak.py       Sidney S.M.'s reader (a gist, 2013), a whole independent
                 extraction: every fork the engine writes must be the one
                 it writes, byte for byte, and every file it writes that
                 the engine does not must be one the engine reported as
                 failed. Run from a copy with three edits, all to where it
                 WRITES and none to how it reads (UNBAK_EDITS below).
  Kaitai         Em Adespoton's description, compiled for Python by
                 Kaitai Struct (MIT): FInfo, FXInfo, both dates and the
                 lock of every item the engine lists (`l --meta`). Run
                 from a copy that decodes names as MacRoman instead of
                 ASCII and drops a version check that wants setuptools.

Over the six real disks of two backups (fixtures/SOURCES.md, abk-*),
which are partial sets: disks 1, 5, 6 of six and 1, 4, 7 of seven. Then:

  - a set made here, three disks with ONE file across all of them, so
    the middle disk holds nothing but a continuation — a shape neither
    real set has. Graded by unbak.py too, not by what made it;
  - the real disks cut and bit-flipped, each variant alone in a directory
    of its own (the CLI joins any file beside an input whose header
    matches), where `t` must end, under the sanitizers, in time;
  - controls that must fail: a fork changed by one byte, a date changed
    in the expectation, and a set's two disks swapped in their numbers.

Neither reader is run on this machine as it stands: each is run inside
tools/sandbox.py's box (no network, no home, no repository; the disks
read-only and one output directory), whose own self-test runs first and
must pass, and what comes out is read as data.

What it CANNOT see: anything both other readers get wrong the same way
— they were written from one article — and the Finder flags the
Macintosh shell then clears or sets (on-desk, inited), which only the
emulator run shows. A disk this machine has no copy of is not graded.
"""
import argparse, filecmp, json, os, re, shutil, struct, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sandbox                                               # noqa: E402

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
FIX = os.path.join(ROOT, "fixtures")
REF = os.path.join(ROOT, "reference", "applebackup")
SETS = {"perfA": (1, 5, 6), "perfB": (1, 4, 7)}

# unbak.py writes a resource fork to NAME/..namedfork/rsrc, which only
# macOS has; makes folders only for nested paths; and lets pathlib split
# a Mac name holding '/'. Each edit changes a destination, not a reading.
UNBAK_EDITS = [
    ("    nix_path = pathlib.Path(*full_path.decode('macroman').split(':'))",
     "    nix_path = pathlib.Path(*[c.replace('/', ':') for c in "
     "full_path.decode('macroman').split(':')])"),
    ("    if len(nix_path.parts) > 1:\n"
     "        os.makedirs(nix_path if is_folder else nix_path.parent, "
     "exist_ok=True)",
     "    os.makedirs(nix_path if is_folder else (nix_path.parent if "
     "len(nix_path.parts) > 1 else '.'), exist_ok=True)"),
    ("        with open(nix_path.joinpath('..namedfork', 'rsrc'), "
     "open_flags) as of:",
     "        with open(str(nix_path) + '.rsrc', open_flags) as of:"),
]
KAITAI_EDITS = [
    ("from pkg_resources import parse_version\n", ""),
    ("if parse_version(ks_version) < parse_version('0.7'):",
     "if False:"),
    ('.decode(u"ascii")', '.decode(u"mac_roman")'),
]


def patched(src, edits, dest):
    s = open(src, encoding="utf-8").read()
    for a, b in edits:
        n = s.count(a)
        if n == 0:
            raise SystemExit(f"run_abk: {os.path.basename(src)} no longer "
                             f"holds {a[:50]!r}; re-read the edits")
        s = s.replace(a, b)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(s)


def disk_no(path):
    with open(path, "rb") as f:
        return struct.unpack(">H", f.read(8)[6:8])[0]


def run_unbak(unbak, disks, out):
    """unbak.py over each disk in turn, in the box: the disks and the
    script read-only, `out` the one directory it may write."""
    os.makedirs(out)
    setdir = os.path.dirname(os.path.abspath(disks[0]))
    for d in sorted(disks, key=disk_no):
        r = sandbox.run(["python3", "-I", "/ref/" + os.path.basename(unbak),
                         "/in/" + os.path.basename(d)],
                        ro=[(os.path.dirname(unbak), "/ref"), (setdir, "/in")],
                        rw=(out, "/out"), cwd="/out", timeout=300,
                        capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"run_abk: unbak.py failed on {d}:\n"
                             f"{r.stderr[-400:]}")


def tree(root):
    out = {}
    for dp, _, fn in os.walk(root):
        for x in fn:
            p = os.path.join(dp, x)
            out[os.path.relpath(p, root)] = p
    return out


def failed_entries(stderr):
    """The entries the CLI reported as failed, by the name it printed."""
    got = set()
    for line in stderr.splitlines():
        m = re.match(r"macextract: (.*): (multi-segment archive|"
                     r"truncated|internal structure|file ends)", line)
        if m:
            got.add(m.group(1))
    return got


def grade_bytes(mx, setdir, work, tag):
    """0 failures, or the count; prints what it found."""
    disks = [os.path.join(setdir, f) for f in os.listdir(setdir)]
    ref, out = os.path.join(work, "unbak"), os.path.join(work, "mx")
    run_unbak(UNBAK, disks, ref)
    r = subprocess.run([mx, "x", "-o", out, disks[0]],
                       capture_output=True, text=True)
    failed = failed_entries(r.stderr)
    R, M = tree(ref), tree(out) if os.path.isdir(out) else {}
    bad, same = 0, 0
    for k, p in sorted(M.items()):
        q = R.get(k)
        if q is None:
            print(f"  {tag}: {k} written by the engine, not by unbak.py")
            bad += 1
        elif not filecmp.cmp(p, q, shallow=False):
            print(f"  {tag}: {k} differs ({os.path.getsize(p)} B against "
                  f"{os.path.getsize(q)} B)")
            bad += 1
        else:
            same += 1
    for k in sorted(set(R) - set(M)):
        base = k[:-5] if k.endswith(".rsrc") else k
        if base not in failed:
            print(f"  {tag}: {k} written by unbak.py, and the engine "
                  f"neither wrote it nor reported it failed")
            bad += 1
    return same, len(failed), bad, r


# Run in the box beside Kaitai's parser: one JSON line per item whose
# first part is on the disk. This driver is ours; what it imports is not.
KAITAI_DRIVER = """
import json, sys
sys.path.insert(0, "/k")
import apple_backup_k as kab
ab = kab.AppleBackup.from_file(sys.argv[1])
for it in ab.file_data.file_data_contents:
    if it.file_part != 1:
        continue
    if it.folder_flags == 0:
        fi, fx = it._raw_finfo_data, it._raw_fxinfo_data
    else:
        fi, fx = it._raw_dinfo_data, it._raw_dxinfo_data
    print(json.dumps([it.full_file_path, fi.hex(), fx.hex(),
                      it.creation_date, it.modification_date,
                      it.file_attributes, it.validity_flag,
                      it.folder_flags]))
"""


def kaitai_items(disk):
    """(path, raw FInfo, raw FXInfo, created, modified, attr, valid,
    flags) of every item whose first part is on this disk, as Kaitai's
    parser reads them, in the box. Its output is data, checked for shape."""
    r = sandbox.run(["python3", "-I", "/k/driver.py",
                     "/in/" + os.path.basename(disk)],
                    ro=[(KDIR, "/k"), (os.path.dirname(os.path.abspath(disk)),
                                       "/in")],
                    timeout=300, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"run_abk: Kaitai's parser failed on {disk}:\n"
                         f"{r.stderr[-400:]}")
    rows = []
    for line in r.stdout.splitlines():
        p, fi, fx, cr, md, attr, valid, flags = json.loads(line)
        if not (isinstance(p, str) and all(isinstance(v, int) for v in
                                           (cr, md, attr, valid, flags))):
            raise SystemExit("run_abk: Kaitai's output is not what was asked")
        rows.append((p, bytes.fromhex(fi), bytes.fromhex(fx), cr, md, attr,
                     valid, flags))
    return rows


def grade_meta(mx, disk, tamper=False):
    """Failures in `l --meta` against Kaitai, for the items on one disk."""
    r = subprocess.run([mx, "l", "--meta", disk], capture_output=True)
    meta, dates = {}, {}
    # Not splitlines(): a Mac name may hold a CR ("Icon\r", a folder's
    # custom icon), which `l` prints as it is.
    for line in r.stdout.decode("utf-8").split("\n"):
        # m FInfo FXInfo backup lock comment NAME (cli/main.c, print_meta)
        f = line.split(" ", 6)
        if line.startswith("m ") and len(f) == 7:
            meta[f[6]] = f
        elif line.startswith("t "):
            g = line.split(" ", 3)
            dates[g[3]] = g
    bad = n = 0
    for path, fi, fx, cr, md, attr, valid, flags in kaitai_items(disk):
        name = "/".join(c.replace("/", ":") for c in path.split(":"))
        if tamper:
            md ^= 1
        n += 1
        m, t = meta.get(name), dates.get(name)
        if not m or not t:
            if not tamper:
                print(f"  meta: {name} not listed")
            bad += 1
            continue
        want_fi = fi.hex() if valid & 1 else "-"
        want_fx = fx.hex() if valid & 1 else "-"
        want_lock = ("L" if attr & 1 else "n") if (valid & 1 and
                                                    not flags & 0x80) else "-"
        want_t = [f"{cr:08x}" if valid & 1 and cr else "-",
                  f"{md:08x}" if valid & 1 and md else "-"]
        got = (m[1], m[2], m[4], t[1], t[2])
        want = (want_fi, want_fx, want_lock, want_t[0], want_t[1])
        if got != want:
            if not tamper:
                print(f"  meta: {name}: listed {got}, Kaitai reads {want}")
            bad += 1
    return n, bad


# ---- a set made here ---------------------------------------------------

def synth_set(dest, stamp=0xA1B2C3D4, drive=b"Synth HD"):
    """Three disks; one file's resource fork runs across all three, and
    the second holds nothing else. Layout as src/fmt_abk.c states it."""
    DISK = 0x161800

    def disk_hdr(n, used):
        h = bytearray(0x600)
        struct.pack_into(">H4sHHII", h, 0, 0x0103, b"CMWL", n, 3, stamp, stamp)
        h[0x12] = len(drive)
        h[0x13:0x13 + len(drive)] = drive
        struct.pack_into(">II", h, 0x32, DISK, used)
        return h

    def item(start, off, path, part, folder, dl, rl, dh, rh, ftype=b"TEXT"):
        h = bytearray(0x70)
        name = path.split(b":")[-1]
        struct.pack_into(">H4sHII", h, 0, 0x0103, b"RLDW", start, stamp, off)
        h[0x10] = len(name)
        h[0x11:0x11 + len(name)] = name
        struct.pack_into(">HBB", h, 0x30, part, 0x80 if folder else 0, 1)
        if not folder:
            h[0x34:0x3C] = ftype + b"ttxt"
            struct.pack_into(">H", h, 0x3C, 0x0100)
        h[0x54] = 0x10 if folder else 0x01           # a locked file
        struct.pack_into(">IIIIIIH", h, 0x56, 0xA0000000 + part,
                         0xA1000000 + part, dl, rl, dh, rh, len(path))
        return bytes(h) + path

    big_d = bytes((i * 7) & 0xFF for i in range(5000))
    big_r = bytes((i * 13 + 5) & 0xFF for i in range(2 * DISK + 70000))
    disks = []
    # disk 1: a folder, a small file, the big file's data fork and the
    # first of its resource fork.
    body = bytearray()
    def put(b):
        nonlocal body
        body += b
        body += b"\0" * (-len(body) % 0x200)
    put(item(1, 0x600, b"Folder", 1, True, 0, 0, 0, 0))
    put(item(1, 0x800, b"Folder:small", 1, False, 3, 0, 3, 0) + b"abc")
    path = b"Folder:big"
    r1 = DISK - 0xA00 - 0x70 - len(path) - len(big_d)
    hdr = item(1, 0xA00, path, 1, False, len(big_d), len(big_r),
               len(big_d), r1)
    body += hdr + big_d + big_r[:r1]
    disks.append(disk_hdr(1, DISK) + body)
    # disk 2: nothing but more of it.
    r2 = DISK - 0x600 - 0x70 - len(path)
    hdr = item(1, 0x600, path, 2, False, len(big_d), len(big_r), 0, r2)
    disks.append(disk_hdr(2, DISK) + hdr + big_r[r1:r1 + r2])
    # disk 3: the rest, and one more file after it.
    hdr = item(1, 0x600, b"Folder:big", 3, False, len(big_d), len(big_r), 0,
               len(big_r) - r1 - r2)
    body = bytearray(hdr + big_r[r1 + r2:])
    body += b"\0" * (-(0x600 + len(body)) % 0x200)
    off = 0x600 + len(body)
    body += item(3, off, b"last", 1, False, 2, 0, 2, 0) + b"zz"
    used = 0x600 + len(body)
    body += b"\0" * (-used % 0x200)
    used = 0x600 + len(body)
    tail = b"\xf6" * (DISK - used)
    disks.append(disk_hdr(3, used) + body + tail)
    os.makedirs(dest)
    for i, d in enumerate(disks, 1):
        assert len(d) == DISK, (i, len(d))
        with open(os.path.join(dest, f"Apple Backup Data {i}"), "wb") as f:
            f.write(d)


def variants(blob, seed):
    import random
    rng = random.Random(seed)
    out = [(f"cut{f}", blob[:int(len(blob) * f / 100)])
           for f in (1, 25, 50, 98)]
    for i in range(6):
        b = bytearray(blob)
        for _ in range(rng.randint(1, 8)):
            # half the flips in the headers, where they change a decision
            pos = rng.randrange(0x700) if i % 2 else rng.randrange(len(b))
            b[pos] ^= 1 << rng.randrange(8)
        out.append((f"flip{i}", bytes(b)))
    return out


def main():
    global UNBAK, KDIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract",
                    default=os.path.join(ROOT, "build", "san", "macextract"))
    args = ap.parse_args()
    mx = os.path.abspath(args.macextract)
    have = [n for n in ("gist-unbak.py", "kaitai-apple_backup.py",
                        "kaitaistruct.py")
            if os.path.exists(os.path.join(REF, n))]
    if len(have) < 3:
        print("run_abk: reference/applebackup is incomplete — "
              "tools/fetch_references.sh fetches it")
        return 1
    os.makedirs(os.path.join(ROOT, ".tmp"), exist_ok=True)
    work = tempfile.mkdtemp(dir=os.path.join(ROOT, ".tmp"), prefix="run_abk.")
    fails = 0
    try:
        os.makedirs(os.path.join(work, "unbak-ref"))
        UNBAK = os.path.join(work, "unbak-ref", "unbak_linux.py")
        patched(os.path.join(REF, "gist-unbak.py"), UNBAK_EDITS, UNBAK)
        KDIR = os.path.join(work, "kaitai")
        os.makedirs(KDIR)
        patched(os.path.join(REF, "kaitai-apple_backup.py"), KAITAI_EDITS,
                os.path.join(KDIR, "apple_backup_k.py"))
        shutil.copy(os.path.join(REF, "kaitaistruct.py"), KDIR)
        with open(os.path.join(KDIR, "driver.py"), "w") as f:
            f.write(KAITAI_DRIVER)
        if sandbox.selftest() != 0:
            print("run_abk: the sandbox does not hold; nothing from "
                  "reference/applebackup is run")
            return 1

        # The real sets, each in a directory of its own.
        for name, nums in SETS.items():
            files = [os.path.join(FIX, f"abk-{name}-disk{n}.data")
                     for n in nums]
            if not all(os.path.exists(f) for f in files):
                print(f"run_abk: {name}: fixtures missing "
                      f"(tools/harvest.py --restore)")
                fails += 1
                continue
            sd = os.path.join(work, name)
            os.makedirs(sd)
            for f in files:
                shutil.copy(f, sd)
            same, nfail, bad, _ = grade_bytes(mx, sd, os.path.join(work,
                                              name + ".x"), name)
            n = mbad = 0
            for f in files:
                k, b = grade_meta(mx, os.path.join(sd, os.path.basename(f)))
                n += k
                mbad += b
            print(f"run_abk: {name}: {same} forks as unbak.py writes them, "
                  f"{nfail} entries reported failed (missing disks), "
                  f"{n} items' Finder info and dates as Kaitai reads them"
                  + (f" — {bad + mbad} FAILURES" if bad + mbad else ""))
            fails += bad + mbad

        # Made here: a file across three disks.
        sd = os.path.join(work, "synth")
        synth_set(sd)
        same, nfail, bad, r = grade_bytes(mx, sd, os.path.join(work,
                                          "synth.x"), "synth")
        if r.returncode != 0 or nfail or same != 4:
            print(f"  synth: exit {r.returncode}, {same} forks, {nfail} "
                  f"failed:\n{r.stderr[-600:]}")
            bad += 1
        print(f"run_abk: synth: a file across three disks, {same} forks "
              f"as unbak.py writes them" + (" — FAILED" if bad else ""))
        fails += bad

        # Controls: each must be caught.
        ctl = 0
        x = os.path.join(work, "synth.x", "mx", "Folder", "small")
        with open(x, "r+b") as f:
            f.write(b"X")
        R = tree(os.path.join(work, "synth.x", "unbak"))
        if filecmp.cmp(x, R["Folder/small"], shallow=False):
            print("  control: a changed fork compared equal")
            ctl += 1
        k, b = grade_meta(mx, os.path.join(work, "perfA",
                                           "abk-perfA-disk1.data"),
                          tamper=True) if os.path.isdir(
            os.path.join(work, "perfA")) else (0, 1)
        if b == 0:
            print("  control: a changed date matched")
            ctl += 1
        sw = os.path.join(work, "swapped")
        shutil.copytree(sd, sw)
        for a, b2 in ((1, 2), (2, 1)):
            p = os.path.join(sw, f"Apple Backup Data {a}")
            with open(p, "r+b") as f:
                f.seek(6)
                f.write(struct.pack(">H", b2))
        r = subprocess.run([mx, "t", os.path.join(sw, "Apple Backup Data 1")],
                           capture_output=True)
        if r.returncode == 0:
            print("  control: two disks swapped in their numbers tested clean")
            ctl += 1
        print(f"run_abk: controls: 3, {3 - ctl} caught")
        fails += ctl

        # Damaged disks, each alone.
        tested = 0
        for name, nums in SETS.items():
            for n in nums:
                src = os.path.join(FIX, f"abk-{name}-disk{n}.data")
                if not os.path.exists(src):
                    continue
                blob = open(src, "rb").read()
                for tag, var in variants(blob, f"{name}{n}"):
                    d = os.path.join(work, "var", f"{name}{n}{tag}")
                    os.makedirs(d)
                    p = os.path.join(d, "Apple Backup Data")
                    with open(p, "wb") as f:
                        f.write(var)
                    tested += 1
                    try:
                        r = subprocess.run([mx, "t", p], capture_output=True,
                                           timeout=60)
                        if r.returncode < 0 or r.returncode > 2:
                            print(f"  {name}{n}[{tag}]: exit {r.returncode}"
                                  f"\n{r.stderr.decode('utf-8', 'replace')[-400:]}")
                            fails += 1
                    except subprocess.TimeoutExpired:
                        print(f"  {name}{n}[{tag}]: HANG")
                        fails += 1
                    shutil.rmtree(d)
        print(f"run_abk: {tested} damaged disks, each alone: every one "
              f"ended in time with a normal exit"
              if not fails else f"run_abk: {tested} damaged disks")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("run_abk: OK" if not fails else f"run_abk: {fails} FAILURES")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
