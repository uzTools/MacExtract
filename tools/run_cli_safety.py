#!/usr/bin/env python3
"""run_cli_safety.py — the Linux CLI must never destroy what it did not write.

Every case here is one way `macextract x` could lose a file the user
already had, or report success with the data nowhere: the input archive
opened for writing under --overwrite, an unwrap's cleanup removing a file
this run never wrote, a write error that only fclose() reported, a link
planted in the output folder, a selector ignored on the last layer. Each
builds its own input — a MacBinary II header with its CRC-16/XMODEM at
124 and a tarfile ustar payload is enough for most — and each was made to
fail against the code before its fix (DECISIONS.md 2026-11-07, *what the
CLI may delete*).

What it CANNOT see: anything outside the cases listed in CASES. It is a
regression suite for named defects, not a search for new ones; a remove()
or rename() added later on a path built from a name is caught only if it
lands on one of these shapes.

Usage: run_cli_safety.py [--macextract PATH] [CASE ...]
"""
import argparse, binascii, io, os, struct, subprocess, sys, tarfile, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard  # noqa: E402,F401  (points tempfile at .tmp/)

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MACEXTRACT = os.path.join(ROOT, "build", "san", "macextract")


# ---- inputs ---------------------------------------------------------------

def macbinary(name, data=b"", rsrc=b"", typ=b"????", creator=b"????"):
    """A MacBinary II file. Header offsets as tools/mar_unix.py writes
    them (after mac-utils' macbinary.c); CRC-16/XMODEM over bytes 0..123
    at 124 (poly 0x1021, init 0 — binascii.crc_hqx)."""
    hd = bytearray(128)
    hd[1] = len(name)
    hd[2:2 + len(name)] = name
    hd[65:69], hd[69:73] = typ, creator
    struct.pack_into(">II", hd, 83, len(data), len(rsrc))
    hd[122], hd[123] = 129, 129
    struct.pack_into(">H", hd, 124, binascii.crc_hqx(bytes(hd[:124]), 0))
    pad = lambda b: b + bytes((128 - len(b) % 128) % 128)
    return bytes(hd) + pad(data) + pad(rsrc)


def tar_of(members):
    """A ustar archive: members is [(name, bytes)]."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as t:
        for name, data in members:
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            ti.mtime = 0
            t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def read(path):
    with open(path, "rb") as f:
        return f.read()


def run(*args, cwd=None):
    r = subprocess.run([MACEXTRACT] + list(args), capture_output=True,
                       timeout=120, cwd=cwd)
    return r.returncode, r.stderr.decode("utf-8", "replace")


# ---- cases ----------------------------------------------------------------
# Each returns a list of problems; empty is a pass.

def case_overwrite_self(tmp):
    """Item 1: a MacBinary whose stored name is its own filename, holding a
    tar. With --overwrite the first layer's only entry IS the input file:
    it was opened "wb" while the engine read it. Small payload: exit 0 and
    only the tar's member left. 1 MB payload: the read is cut short."""
    probs = []
    for label, size in (("small", 600), ("1MB", 1 << 20)):
        d = os.path.join(tmp, label)
        os.mkdir(d)
        inner = b"inner %s\n" % label.encode() * (size // 10)
        arc = macbinary(b"Self.bin", tar_of([("inner.txt", inner)]))
        src = os.path.join(d, "Self.bin")
        write(src, arc)
        rc, err = run("x", "Self.bin", "--overwrite", cwd=d)
        if not os.path.exists(src) or read(src) != arc:
            probs.append(f"{label}: Self.bin was destroyed (exit {rc}, "
                         f"{err.strip()[:160]!r})")
        elif rc != 1 or "is the archive being read" not in err:
            probs.append(f"{label}: wanted a per-entry refusal, exit 1; got "
                         f"exit {rc}, {err.strip()[:160]!r}")
    d = os.path.join(tmp, "link")
    os.mkdir(d)
    arc = macbinary(b"Other.bin", tar_of([("inner.txt", b"x" * 900)]))
    write(os.path.join(d, "Real.bin"), arc)
    os.link(os.path.join(d, "Real.bin"), os.path.join(d, "Other.bin"))
    os.mkdir(os.path.join(d, "o"))
    # The stored name lands at o/Other.bin, which is not the input; put the
    # input there as a hard link so only an inode comparison sees it.
    os.link(os.path.join(d, "Real.bin"), os.path.join(d, "o", "Other.bin"))
    rc, err = run("x", "Real.bin", "-o", "o", "--overwrite", cwd=d)
    if read(os.path.join(d, "Real.bin")) != arc:
        probs.append(f"hard link: Real.bin was destroyed through "
                     f"o/Other.bin (exit {rc}, {err.strip()[:160]!r})")
    elif rc != 1:
        probs.append(f"hard link: wanted exit 1, got {rc}")
    return probs


def case_sidecar_not_ours(tmp):
    """Item 2A: the envelope's sidecar (NAME.rsrc, ._NAME) was removed at
    the end of an unwrap whether or not this run wrote it, and was exempt
    from the no-overwrite rule. MacBinary "Foo.tar" with NO resource fork,
    holding a tar; the user's own o/Foo.tar.rsrc (or o/._Foo.tar) beside
    it must survive, and an inner entry of that name must be refused."""
    probs = []
    for forks, side in (("visible", "Foo.tar.rsrc"), ("hidden", "._Foo.tar")):
        mine = b"the user's own file\n"
        # (a) the unwrap's cleanup alone
        d = os.path.join(tmp, forks + "-a")
        os.makedirs(os.path.join(d, "o"))
        write(os.path.join(d, "Foo.bin"),
              macbinary(b"Foo.tar", tar_of([("inner.txt", b"in\n" * 300)])))
        write(os.path.join(d, "o", side), mine)
        rc, err = run("x", "Foo.bin", "-o", "o", "--forks", forks, cwd=d)
        got = os.path.join(d, "o", side)
        if not os.path.exists(got) or read(got) != mine:
            probs.append(f"{forks} cleanup: the user's {side} was removed "
                         f"(exit {rc})")
        if rc != 0 or not os.path.exists(os.path.join(d, "o", "inner.txt")):
            probs.append(f"{forks} cleanup: wanted a clean unwrap, exit {rc} "
                         f"{err.strip()[:160]!r}")
        # (b) an inner entry carrying the sidecar's name, no --overwrite
        d = os.path.join(tmp, forks + "-b")
        os.makedirs(os.path.join(d, "o"))
        write(os.path.join(d, "Foo.bin"),
              macbinary(b"Foo.tar", tar_of([(side, b"inner\n" * 200)])))
        write(os.path.join(d, "o", side), mine)
        rc, err = run("x", "Foo.bin", "-o", "o", "--forks", forks, cwd=d)
        if not os.path.exists(got.replace(forks + "-a", forks + "-b")) or \
           read(os.path.join(d, "o", side)) != mine:
            probs.append(f"{forks} entry: an inner {side} replaced the "
                         f"user's without --overwrite (exit {rc})")
        elif rc != 1 or "already exists" not in err:
            probs.append(f"{forks} entry: wanted the clobber refusal, exit 1;"
                         f" got exit {rc} {err.strip()[:160]!r}")
        # (c) the control: a sidecar this run DID write still goes
        d = os.path.join(tmp, forks + "-c")
        os.makedirs(os.path.join(d, "o"))
        write(os.path.join(d, "Foo.bin"),
              macbinary(b"Foo.tar", tar_of([("inner.txt", b"in\n" * 300)]),
                        rsrc=b"R" * 300))
        rc, err = run("x", "Foo.bin", "-o", "o", "--forks", forks, cwd=d)
        left = sorted(os.listdir(os.path.join(d, "o")))
        if rc != 0 or left != ["inner.txt"]:
            probs.append(f"{forks} control: wanted only inner.txt, got "
                         f"{left} exit {rc}")
    return probs


CASES = {
    "overwrite-self": case_overwrite_self,
    "sidecar-not-ours": case_sidecar_not_ours,
}


def main():
    global MACEXTRACT
    ap = argparse.ArgumentParser()
    ap.add_argument("--macextract", default=MACEXTRACT)
    ap.add_argument("cases", nargs="*")
    a = ap.parse_args()
    MACEXTRACT = os.path.abspath(a.macextract)
    names = a.cases or list(CASES)
    bad = 0
    for n in names:
        with tempfile.TemporaryDirectory() as tmp:
            probs = CASES[n](tmp)
        print(f"cli-safety: {n}: {'ok' if not probs else 'FAILED'}")
        for p in probs:
            print(f"cli-safety:   {p}")
        bad += bool(probs)
    print(f"cli-safety: {len(names) - bad}/{len(names)} cases passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
