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


def run(*args, cwd=None, fsize=None):
    """`fsize`: RLIMIT_FSIZE for the child, with SIGXFSZ ignored, so a
    write past it fails with EFBIG — the one write error this machine can
    raise in an unprivileged process without a link, a preload or a seam."""
    def limit():
        import resource, signal
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
    r = subprocess.run([MACEXTRACT] + list(args), capture_output=True,
                       timeout=120, cwd=cwd,
                       preexec_fn=limit if fsize is not None else None)
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


def case_deferred_by_path(tmp):
    """Item 2B: the write deferred beside the envelope was keyed by which
    FORK was written, not which path matched, so an inner DATA fork named
    like the envelope's sidecar went to Foo.tar.rsrc.unwrap~ and was
    never renamed back. MacBinary "Foo.tar" WITH a resource fork, holding
    a tar whose one member carries the sidecar's name."""
    probs = []
    for forks, side in (("visible", "Foo.tar.rsrc"), ("hidden", "._Foo.tar")):
        d = os.path.join(tmp, forks)
        os.makedirs(os.path.join(d, "o"))
        body = b"the inner entry\n" * 100
        write(os.path.join(d, "Foo.bin"),
              macbinary(b"Foo.tar", tar_of([(side, body)]), rsrc=b"R" * 300))
        rc, err = run("x", "Foo.bin", "-o", "o", "--forks", forks, cwd=d)
        left = sorted(os.listdir(os.path.join(d, "o")))
        p = os.path.join(d, "o", side)
        if rc != 0 or left != [side] or read(p) != body:
            probs.append(f"{forks}: wanted only {side} holding the entry, "
                         f"got {left} exit {rc} {err.strip()[:120]!r}")
    return probs


def long_dir(base, total):
    """A directory under `base` whose path is exactly `total` bytes, in
    components short enough for any filesystem."""
    p = base
    while len(p) < total:
        room = total - len(p) - 1
        if room < 1:
            raise ValueError("cannot pad to that length")
        n = min(200, room) if room - min(200, room) != 1 else 199
        p = os.path.join(p, "d" * n)
    os.makedirs(p)
    assert len(p) == total
    return p


def case_long_paths(tmp):
    """Item 2C: fixed buffers (rp[1100], tmp[1200]) cut a long sidecar or
    deferral path, and remove()/rename() then acted on a DIFFERENT file.
    (a) the review's shape: -o 1,207 bytes long, MacBinary "Foo.tar" with
    no resource fork; the 1,099-byte cut of OUT/Foo.tar.rsrc lands inside
    the output path, where a sibling file is planted. (b) the deferral
    rename: two nameless gzip layers in "Same", -o 1,190 bytes, so
    OUT/Same.unwrap~ cut to 1,199 is OUT/Same.unw, a planted sibling."""
    import gzip
    probs = []
    mine = b"a sibling the user owns\n"
    # (a)
    out = long_dir(os.path.join(tmp, "a"), 1207)
    cut = (out + "/Foo.tar.rsrc")[:1099]
    write(cut, mine)
    src = os.path.join(tmp, "Foo.bin")
    write(src, macbinary(b"Foo.tar", tar_of([("inner.txt", b"in\n" * 300)])))
    rc, err = run("x", src, "-o", out)
    if not os.path.exists(cut) or read(cut) != mine:
        probs.append(f"(a) the sibling at the 1,099-byte cut was removed "
                     f"(exit {rc})")
    elif rc != 0 or not os.path.exists(os.path.join(out, "inner.txt")):
        probs.append(f"(a) wanted a clean unwrap, exit {rc} "
                     f"{err.strip()[-160:]!r}")
    # (b)
    out = long_dir(os.path.join(tmp, "b"), 1190)
    cut = (out + "/Same.unwrap~")[:1199]
    write(cut, mine)
    payload = b"two nameless layers\n" * 50
    src = os.path.join(tmp, "Same")
    write(src, gzip.compress(gzip.compress(payload, mtime=0), mtime=0))
    rc, err = run("x", src, "-o", out)
    left = sorted(os.listdir(out))
    if not os.path.exists(cut) or read(cut) != mine:
        probs.append(f"(b) the sibling {os.path.basename(cut)} was renamed "
                     f"onto the output (left {left}, exit {rc})")
    elif rc != 0 or read(os.path.join(out, "Same")) != payload or \
            len(left) != 2:
        probs.append(f"(b) wanted Same holding the payload beside the "
                     f"sibling, got {left} exit {rc} {err.strip()[-160:]!r}")
    return probs


def case_write_error(tmp):
    """Item 3: a write error that stdio reports only at fclose() was
    ignored: the entry counted as OK and the layer above was deleted.
    MacBinary "Foo.gz" holding a gzip of a compressible text, so the
    envelope's own output is small and the inner entry is not; the
    child's RLIMIT_FSIZE sits between them. 1,500 B is buffered whole and
    fails at fclose; 200 KB fails inside fwrite. Either way: exit 1, the
    errno text, and Foo.gz kept."""
    import gzip
    probs = []
    for label, size in (("fclose", 1500), ("fwrite", 200000)):
        d = os.path.join(tmp, label)
        os.makedirs(os.path.join(d, "o"))
        text = (b"compressible line of text\n" * (size // 26 + 1))[:size]
        gz = gzip.compress(text, mtime=0)
        assert len(gz) + 128 < 1000
        write(os.path.join(d, "Foo.bin"), macbinary(b"Foo.gz", gz))
        rc, err = run("x", "Foo.bin", "-o", "o", cwd=d, fsize=1000)
        left = sorted(os.listdir(os.path.join(d, "o")))
        if rc != 1 or "File too large" not in err:
            probs.append(f"{label}: wanted exit 1 naming the error, got exit "
                         f"{rc} {err.strip()[:160]!r}, left {left}")
        if "Foo.gz" not in left:
            probs.append(f"{label}: the layer above, Foo.gz, was deleted "
                         f"(left {left})")
    # And a listing sent to a full device is as lost as a file.
    with open("/dev/full", "wb") as full:
        r = subprocess.run([MACEXTRACT, "l", os.path.join(d, "Foo.bin")],
                           stdout=full, stderr=subprocess.PIPE, timeout=60)
    if r.returncode != 1 or b"No space left" not in r.stderr:
        probs.append(f"l > /dev/full: wanted exit 1, got {r.returncode} "
                     f"{r.stderr.decode()[:120]!r}")
    return probs


def case_planted_links(tmp):
    """Item 4: links already in the output folder were followed: stat,
    mkdir and fopen("wb") went through them, a dangling file link even
    without --overwrite. A tar holding evil.txt and lnk/x.txt, extracted
    into o/ where evil.txt -> ../outside.txt and lnk -> ../outsidedir were
    planted. Nothing outside o/ may change; --overwrite replaces the link
    itself, and without it the entry is refused."""
    probs = []
    tar = tar_of([("evil.txt", b"entry evil\n"), ("lnk/x.txt", b"entry x\n")])
    for ow in (False, True):
        tag = "--overwrite" if ow else "default"
        d = os.path.join(tmp, tag.strip("-"))
        os.makedirs(os.path.join(d, "o"))
        os.mkdir(os.path.join(d, "outsidedir"))
        if ow:      # a link to a file that exists; default: a dangling one
            write(os.path.join(d, "outside.txt"), b"outside\n")
        os.symlink("../outside.txt", os.path.join(d, "o", "evil.txt"))
        os.symlink("../outsidedir", os.path.join(d, "o", "lnk"))
        write(os.path.join(d, "a.tar"), tar)
        args = ["x", "a.tar", "-o", "o"] + (["--overwrite"] if ow else [])
        rc, err = run(*args, cwd=d)
        out_txt = os.path.join(d, "outside.txt")
        if ow and read(out_txt) != b"outside\n":
            probs.append(f"{tag}: outside.txt was written through the link")
        if not ow and os.path.exists(out_txt):
            probs.append(f"{tag}: outside.txt was created through the "
                         f"dangling link")
        if os.listdir(os.path.join(d, "outsidedir")):
            probs.append(f"{tag}: lnk/x.txt landed in outsidedir")
        o = os.path.join(d, "o")
        if ow:
            if rc != 0 or os.path.islink(os.path.join(o, "evil.txt")) or \
               os.path.islink(os.path.join(o, "lnk")) or \
               read(os.path.join(o, "evil.txt")) != b"entry evil\n" or \
               read(os.path.join(o, "lnk", "x.txt")) != b"entry x\n":
                probs.append(f"{tag}: wanted both links replaced by the "
                             f"entries, exit 0; got exit {rc} "
                             f"{err.strip()[:160]!r}")
        else:
            if rc != 1 or not os.path.islink(os.path.join(o, "evil.txt")) \
               or not os.path.islink(os.path.join(o, "lnk")):
                probs.append(f"{tag}: wanted both entries refused and the "
                             f"links left, exit 1; got exit {rc} "
                             f"{err.strip()[:160]!r}")
    return probs


def case_unwrap_temp_not_ours(tmp):
    """Found auditing item 2's fopen("wb") calls: the deferral beside the
    envelope opened NAME.unwrap~ "wb" whatever was there. Two nameless
    gzip layers in "Same", with the user's own o/Same.unwrap~ in place:
    without --overwrite that file must survive (the entry is refused)."""
    import gzip
    mine = b"the user's own .unwrap~ file\n"
    d = os.path.join(tmp, "d")
    os.makedirs(os.path.join(d, "o"))
    payload = b"two nameless layers\n" * 50
    write(os.path.join(d, "Same"),
          gzip.compress(gzip.compress(payload, mtime=0), mtime=0))
    write(os.path.join(d, "o", "Same.unwrap~"), mine)
    rc, err = run("x", "Same", "-o", "o", cwd=d)
    got = os.path.join(d, "o", "Same.unwrap~")
    if not os.path.exists(got) or read(got) != mine:
        return [f"o/Same.unwrap~ was written over (exit {rc}, left "
                f"{sorted(os.listdir(os.path.join(d, 'o')))})"]
    if rc != 1:
        return [f"wanted the entry refused, exit 1; got {rc}"]
    return []


def case_only_last_layer(tmp):
    """Item 5: --only was exempted on every layer that MIGHT unwrap, so on
    an envelope whose payload is not an archive (MacBinary of a text
    file) it was never applied: `x --only nosuchentry` wrote Note.txt and
    exited 0, where `l` with the same arguments exits 1. x must write
    only what was asked for and exit as l does; the control, --only
    naming the payload, must write it, exit 0. And the selector still
    reaches through a layer that DOES unwrap."""
    probs = []
    d = os.path.join(tmp, "d")
    os.makedirs(d)
    note = b"just a note, not an archive\r" * 20
    write(os.path.join(d, "Note.bin"),
          macbinary(b"Note.txt", note, typ=b"TEXT", creator=b"ttxt"))
    for sel, want_rc, want_files in (("nosuchentry", 1, []),
                                     ("Note.txt", 0, ["Note.txt"])):
        o = os.path.join(d, "o-" + sel)
        rcl, _ = run("l", "Note.bin", "--only", sel, cwd=d)
        rc, err = run("x", "Note.bin", "-o", o, "--only", sel, cwd=d)
        left = sorted(os.listdir(o)) if os.path.isdir(o) else []
        if rc != want_rc or rcl != want_rc or left != want_files:
            probs.append(f"--only {sel}: wanted x and l exit {want_rc} and "
                         f"{want_files}; got x {rc}, l {rcl}, {left} "
                         f"{err.strip()[:120]!r}")
    # through a layer that unwraps: Foo.bin -> Foo.tar -> a.txt, b.txt
    write(os.path.join(d, "Foo.bin"), macbinary(
        b"Foo.tar", tar_of([("a.txt", b"a\n"), ("b.txt", b"b\n")])))
    o = os.path.join(d, "o-tar")
    rc, err = run("x", "Foo.bin", "-o", o, "--only", "b.txt", cwd=d)
    left = sorted(os.listdir(o)) if os.path.isdir(o) else []
    if rc != 0 or left != ["b.txt"]:
        probs.append(f"through a tar: wanted only b.txt, exit 0; got {left} "
                     f"exit {rc} {err.strip()[:120]!r}")
    return probs


def wrapped_set(d, name=b"Test.sit"):
    """A three-part StuffIt segmented set, each part in a BinHex envelope
    (tools/synth_sitsplit.py, tools/synth_wrapped.py), so the join has to
    peel parts into its own folder. Returns part 1's wrapper."""
    import synth_sitsplit as ss, synth_wrapped as sw
    plain = os.path.join(d, "plain")
    os.makedirs(plain)
    rsrc, data = ss.blob(9000, 1), ss.blob(21000, 2)
    ss.write_set(plain, ["Test.sit.1", "Test.sit.2", "Test.sit.3"],
                 rsrc + data, len(rsrc), len(data), [11000, 22000], name=name)
    sw.wrap_dir(plain, os.path.join(d, "w"), "hqx")
    return os.path.join(d, "w", "Test.sit.1.hqx")


def case_peel_folder_not_ours(tmp):
    """Item 6: the decoded parts went in OUT/.macextract-parts, whose
    mkdir accepted EEXIST (a link to a folder too), and the cleanup then
    deleted every regular file in it. (a) the user's own folder of that
    name holding a file; (b) a link of that name to a folder elsewhere
    holding a file. Each user file must survive. (The review's third
    shape, a joined file named ".macextract-parts/x", is not reachable:
    name_to_fs writes a Mac name's '/' as ':', and the folder is cleaned
    before any later layer writes — DECISIONS.md 2026-11-07, *the parts
    folder that was not ours*.)"""
    probs = []
    for label in ("own-folder", "link"):
        d = os.path.join(tmp, label)
        first = wrapped_set(d)
        o = os.path.join(d, "o")
        os.makedirs(o)
        keep_dir = os.path.join(o, ".macextract-parts")
        if label == "link":
            keep_dir = os.path.join(d, "elsewhere")
            os.makedirs(keep_dir)
            os.symlink("../elsewhere", os.path.join(o, ".macextract-parts"))
        else:
            os.makedirs(keep_dir)
        write(os.path.join(keep_dir, "keep.txt"), b"mine\n")
        rc, err = run("x", first, "-o", o)
        if not os.path.exists(os.path.join(keep_dir, "keep.txt")):
            probs.append(f"{label}: the user's keep.txt was deleted "
                         f"(exit {rc})")
        if rc != 0 or not os.path.exists(os.path.join(o, "Test.sit")):
            probs.append(f"{label}: wanted the set joined, exit 0; got "
                         f"{rc} {err.strip()[:160]!r}")
        left = [f for f in os.listdir(o) if f.startswith(".macextract-parts-")]
        if left:
            probs.append(f"{label}: the peel folder was left: {left}")
    return probs


def case_mkey_past_256k(tmp):
    """Item 7: load_mkey read the first 256 KB of the archive's sidecar
    and nothing more, and a resource map sits at a fork's END, so a
    larger fork hid its 'MKey'. A StuffIt classic archive encrypted with
    StuffIt's DES scheme (tools/synth_crypt.py, as run_crypt.py builds
    it) beside a sidecar holding a 300 KB resource before the 'MKey':
    it must decrypt. The control, the same 'MKey' in a small sidecar,
    decrypts either way."""
    import synth_crypt as sc
    pw = b"hush"
    probs = []
    sit, small, _ = sc.build_sit_des(pw)
    mkey = sc.sit_mkey_and_iv(pw)[0]
    big = sc.resource_fork([(b"PICT", 128, bytes(300 * 1024)),
                            (b"MKey", 0, mkey)])
    for label, rsrc in (("small", small), ("past 256 KB", big)):
        d = os.path.join(tmp, label.replace(" ", "-"))
        os.makedirs(d)
        write(os.path.join(d, "Secret.sit"), sit)
        write(os.path.join(d, "Secret.sit.rsrc"), rsrc)
        rc, err = run("x", "Secret.sit", "-o", "o", "-p", pw.decode(), cwd=d)
        memo = os.path.join(d, "o", "Secret Memo")
        if rc != 0 or not os.path.exists(memo) or \
           read(memo) != sc.SIT_CASES[0][1]:
            probs.append(f"{label} sidecar ({len(rsrc)} B): wanted a clean "
                         f"decryption, got exit {rc} {err.strip()[:160]!r}")
    return probs


def case_budget_parse(tmp):
    """Item 8: --budget went through strtoul with no end or range check:
    "1M" parsed as 1, "lots" as 0 (no cap at all), and 4G and above
    wrapped through the uint32_t cast. A gzip of 100 KB of text needs its
    32 KB window, so 1K must refuse it and 1M must not; every malformed
    or out-of-range value must be a usage error, exit 2."""
    import gzip
    probs = []
    p = os.path.join(tmp, "t.gz")
    write(p, gzip.compress(b"budget test line\n" * 6000, mtime=0))
    for val, want in (("1M", 0), ("1048576", 0), ("1K", 1), ("1024", 1),
                      ("4095M", 0), ("0", 0)):
        rc, err = run("t", "--budget", val, p)
        if rc != want:
            probs.append(f"--budget {val}: wanted exit {want}, got {rc} "
                         f"{err.strip()[:100]!r}")
    for val in ("lots", "1X", "", "-1", "+5", " 5", "1.5M", "0x10", "4G",
                "4294967296", "99999999999999999999", "5000M", "1MB"):
        rc, err = run("t", "--budget", val, p)
        if rc != 2:
            probs.append(f"--budget {val!r}: wanted a usage error (exit 2), "
                         f"got {rc}")
    return probs


def case_only_late_user_file(tmp):
    """Item 9: a layer that may unwrap is written whole and judged by
    --only afterwards. With --overwrite its entry replaced the user's
    o/Note.txt, and the judge then removed it as not asked for: the
    user's file was gone. Without --overwrite the excluded entry was
    refused as "already exists" and failed the run with two "output
    error" lines for a file nobody asked for. A file the user already
    has, data fork or sidecar, must be left as it was; the excluded
    entry must say nothing but the selector's miss; and the control
    (--only naming it, --overwrite) must still replace it."""
    probs = []
    note = b"just a note, not an archive\r" * 20
    for label, rsrc, hidden in (("data", b"", False), ("rsrc", b"R" * 300, False),
                                ("hidden", b"R" * 300, True)):
        d = os.path.join(tmp, label)
        os.makedirs(os.path.join(d, "o"))
        write(os.path.join(d, "Note.bin"),
              macbinary(b"Note.txt", note, rsrc=rsrc, typ=b"TEXT"))
        side = "._Note.txt" if hidden else "Note.txt.rsrc"
        mine = {"Note.txt": b"USER\n"}
        if rsrc:
            mine[side] = b"USER RSRC\n"
        forks = ["--forks", "hidden"] if hidden else []
        for extra in (["--overwrite"], []):
            for n, b in mine.items():
                write(os.path.join(d, "o", n), b)
            rc, err = run("x", "Note.bin", "-o", "o", *forks, *extra,
                          "--only", "nosuch", cwd=d)
            left = {n: read(os.path.join(d, "o", n))
                    for n in sorted(os.listdir(os.path.join(d, "o")))}
            lines = [l for l in err.strip().splitlines() if l]
            if left != mine:
                probs.append(f"{label} {extra}: the user's files were changed: "
                             f"{sorted(left)} (exit {rc})")
            if rc != 1 or len(lines) != 1 or "nosuch" not in lines[0]:
                probs.append(f"{label} {extra}: wanted only the selector's "
                             f"miss, exit 1; got exit {rc} {lines!r}")
        rc, err = run("x", "Note.bin", "-o", "o", *forks, "--overwrite",
                      "--only", "Note.txt", cwd=d)
        if rc != 0 or read(os.path.join(d, "o", "Note.txt")) != note:
            probs.append(f"{label}: --only Note.txt --overwrite did not "
                         f"replace it (exit {rc}, {err.strip()[:120]!r})")
    # A selected entry that fails is not one "no entry has that name".
    d = os.path.join(tmp, "data")
    write(os.path.join(d, "o", "Note.txt"), b"USER\n")
    rc, err = run("x", "Note.bin", "-o", "o", "--only", "Note.txt", cwd=d)
    if rc != 1 or "already exists" not in err or "no entry" in err:
        probs.append(f"selected but refused: wanted the refusal alone, exit 1;"
                     f" got exit {rc} {err.strip()[:200]!r}")
    return probs


def case_original_every_layer(tmp):
    """Item 10: the file named on the command line was protected only on
    the first layer. A.bin holding B.tar holding a member named A.bin,
    extracted beside itself with --overwrite: layer 2 replaced the user's
    archive with the member and exited 0. Two and three layers deep."""
    probs = []
    inner = tar_of([("A.bin", b"inner\n"), ("c.txt", b"c\n")])
    for label, arc in (("two", macbinary(b"B.tar", inner)),
                       ("three", macbinary(b"B.bin", macbinary(b"C.tar", inner)))):
        d = os.path.join(tmp, label)
        os.makedirs(d)
        write(os.path.join(d, "A.bin"), arc)
        rc, err = run("x", "A.bin", "--overwrite", cwd=d)
        if read(os.path.join(d, "A.bin")) != arc:
            probs.append(f"{label} layers: A.bin was replaced (exit {rc}, "
                         f"{err.strip()[:160]!r})")
        elif rc != 1 or "is the archive being read" not in err:
            probs.append(f"{label} layers: wanted the refusal, exit 1; got "
                         f"exit {rc} {err.strip()[:160]!r}")
    return probs


def case_refusal_said_once(tmp):
    """Item 11: an entry the sink refused (the input itself, a path that
    exists) was said three times: the refusal, then "NAME: output error"
    for the entry, then the layer's own "output error". The entry's line
    added nothing; the refusal and the layer's line stay."""
    probs = []
    d = os.path.join(tmp, "d")
    os.makedirs(d)
    write(os.path.join(d, "Self.bin"),
          macbinary(b"Self.bin", tar_of([("inner.txt", b"x" * 600)])))
    rc, err = run("x", "Self.bin", "--overwrite", cwd=d)
    n = err.count("output error")
    if rc != 1 or "is the archive being read" not in err or n != 1:
        probs.append(f"wanted the refusal and one \"output error\", exit 1; "
                     f"got exit {rc}, {n} of them: {err.strip()[:200]!r}")
    return probs


CASES = {
    "overwrite-self": case_overwrite_self,
    "sidecar-not-ours": case_sidecar_not_ours,
    "deferred-by-path": case_deferred_by_path,
    "long-paths": case_long_paths,
    "write-error": case_write_error,
    "planted-links": case_planted_links,
    "unwrap-temp-not-ours": case_unwrap_temp_not_ours,
    "only-last-layer": case_only_last_layer,
    "peel-folder-not-ours": case_peel_folder_not_ours,
    "mkey-past-256k": case_mkey_past_256k,
    "budget-parse": case_budget_parse,
    "only-late-user-file": case_only_late_user_file,
    "original-every-layer": case_original_every_layer,
    "refusal-said-once": case_refusal_said_once,
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
