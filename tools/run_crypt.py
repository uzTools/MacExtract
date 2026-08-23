#!/usr/bin/env python3
"""run_crypt.py — decryption, adjudicated by `unar` and by Info-ZIP.

Five formats here can encrypt an entry and nothing in the corpus does:
`lsar -j` over all 903 fixtures reports XADIsEncrypted 0 for every one
(2026-08-23). So every archive in this suite is generated, and every one
is required to agree THREE ways, exactly as the ARC suite is:

  1. the bytes that went into the generator;
  2. what `unar -p` (or `unzip -P`) extracts — a different
     implementation of the same cipher, which is the check a shared
     misreading cannot survive;
  3. what our CLI extracts.

Where the encoder is somebody else's, it is used: `zip -P` writes the
PKWARE-cipher fixtures and `arc g<password>` the garbled ARC ones, so
those two owe nothing at all to this project's reading. StuffIt
classic, StuffIt 5 and PackIt have no encoder available on this
machine, so tools/synth_crypt.py writes them and point 2 is what makes
them worth having.

Also checked here, because they are the behaviours a user actually
meets: a wrong password is REPORTED (never decoded to rubbish), no
password at all leaves the archive walkable, and the retry callback is
asked again after a refusal.

One divergence is deliberate and is asserted rather than worked around:
for StuffIt classic, Debian's `unar` 1.10.8 and the XADMaster master
this engine transcribes derive the archive key differently once the
password reaches EIGHT bytes (BLOCKERS.md). The oracle-graded fixtures
therefore use a seven-byte password, and the long-password case is
checked against our own round trip only, and says so.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth_crypt as SC                              # noqa: E402

ARC_BIN = os.path.abspath(os.path.join(ROOT, "build", "arc", "usr", "bin",
                                       "arc"))
SHORT_PW = "hushnow"          # seven bytes: see the note above
LONG_PW = "swordfish-and-more"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **kw)


def forkbytes(path):
    """The bytes of a resource fork as written by either extractor.
    Ours writes the fork raw; `unar` wraps it in AppleDouble, so unwrap
    that (magic 0x00051607, then a count and id/offset/length triples;
    entry id 2 is the resource fork)."""
    b = open(path, "rb").read()
    if len(b) < 26 or b[:4] != b"\x00\x05\x16\x07":
        return b
    n = int.from_bytes(b[24:26], "big")
    for i in range(n):
        e = 26 + i * 12
        if len(b) < e + 12:
            break
        eid = int.from_bytes(b[e:e + 4], "big")
        off = int.from_bytes(b[e + 4:e + 8], "big")
        ln = int.from_bytes(b[e + 8:e + 12], "big")
        if eid == 2:
            return b[off:off + ln]
    return b


def extracted(outdir, name):
    """unar drops multi-entry archives into a subdirectory of its own."""
    direct = os.path.join(outdir, name)
    if os.path.exists(direct):
        return forkbytes(direct)
    for sub in sorted(os.listdir(outdir)):
        p = os.path.join(outdir, sub, name)
        if os.path.exists(p):
            return forkbytes(p)
    return None


def check_one(label, archive, want, password, unclassic, problems,
              oracle=True):
    """`want` maps output name -> bytes. Names ending in .rsrc are
    resource forks, which both extractors write under that name."""
    cmds = [("us", [unclassic, "x", "-o", None, "-p", password, archive])]
    if oracle:
        cmds.insert(0, ("unar", ["unar", "-q", "-f", "-p", password,
                                 "-o", None, archive]))
    for who, cmd in cmds:
        out = tempfile.mkdtemp()
        try:
            r = run([c if c is not None else out for c in cmd])
            if r.returncode != 0:
                problems.append("%s: %s exited %d (%s)"
                                % (label, who, r.returncode,
                                   r.stderr.decode("utf-8", "replace")
                                   .strip()[:120]))
            for name, content in want.items():
                got = extracted(out, name)
                if got is None:
                    problems.append("%s: %s did not write %s"
                                    % (label, who, name))
                elif got != content:
                    problems.append("%s: %s wrote %d bytes for %s, wanted %d"
                                    % (label, who, len(got), name,
                                       len(content)))
        finally:
            shutil.rmtree(out, ignore_errors=True)


def check_refusal(label, archive, unclassic, problems, args=(),
                  expect="wrong password"):
    """A wrong or missing password must be reported per entry, and must
    never produce output. `t` decodes and discards, so a success here
    would mean the CRC passed on rubbish."""
    r = run([unclassic, "t", archive] + list(args))
    if r.returncode == 0:
        problems.append("%s: %s was accepted" % (label, expect))
    msg = r.stderr.decode("utf-8", "replace")
    if expect not in msg:
        problems.append("%s: expected %r, got %r"
                        % (label, expect, msg.strip()[:160]))


def synth(kind, path, password):
    run([sys.executable, os.path.join(ROOT, "tools", "synth_crypt.py"),
         "--kind", kind, "-o", path, "--password", password], check=True)


def main():
    unclassic = os.path.join(ROOT, "build", "unclassic")
    args = sys.argv[1:]
    if "--unclassic" in args:
        unclassic = args[args.index("--unclassic") + 1]
    if not os.path.exists(unclassic):
        print("run_crypt: no CLI at %s" % unclassic)
        return 1
    if shutil.which("unar") is None:
        print("run_crypt: SKIPPED — no `unar` to adjudicate with")
        return 0

    problems = []
    ran = 0
    tmp = tempfile.mkdtemp()
    try:
        # ---- StuffIt classic (StuffItDES) -----------------------------
        # The password verifier is the archive's 'MKey' resource, so the
        # oracle needs the resource fork and therefore the MacBinary
        # form; our CLI reads the same resource out of the sidecar file
        # it writes itself, so it gets the bare .sit and its .rsrc.
        want = {}
        for name, data, rsrc in SC.SIT_CASES:
            if data or not rsrc:
                want[name] = data
            if rsrc:
                want[name + ".rsrc"] = rsrc
        p = os.path.join(tmp, "sit-des.sit")
        synth("sit-des", p, SHORT_PW)
        synth("sit-des", p + ".bin", SHORT_PW)
        check_one("sit-des (unar, MacBinary)", p + ".bin", want, SHORT_PW,
                  unclassic, problems)
        check_one("sit-des (us, sidecar fork)", p, want, SHORT_PW, unclassic,
                  problems, oracle=False)
        check_refusal("sit-des wrong password", p, unclassic, problems,
                      ["-p", "nothush"])
        # Without the resource fork there is no verifier and no key: the
        # entry must say "encrypted", not "wrong password".
        bare = os.path.join(tmp, "nokey.sit")
        shutil.copyfile(p, bare)
        check_refusal("sit-des without 'MKey'", bare, unclassic, problems,
                      ["-p", SHORT_PW], expect="encrypted")
        ran += 4

        # The long-password case: our own round trip only, because the
        # oracle here predates the iteration XADMaster now uses.
        pl = os.path.join(tmp, "sit-des-long.sit")
        synth("sit-des", pl, LONG_PW)
        check_one("sit-des (long password, no oracle)", pl, want, LONG_PW,
                  unclassic, problems, oracle=False)
        ran += 1

        # ---- StuffIt 5 (RC4) ------------------------------------------
        want = {}
        for name, data, rsrc in SC.SIT5_CASES:
            want[name] = data
            if rsrc:
                want[name + ".rsrc"] = rsrc
        p = os.path.join(tmp, "sit5-rc4.sit")
        synth("sit5-rc4", p, LONG_PW)
        check_one("sit5-rc4", p, want, LONG_PW, unclassic, problems)
        check_refusal("sit5 wrong password", p, unclassic, problems,
                      ["-p", "wrong"])
        check_refusal("sit5 no password", p, unclassic, problems)
        ran += 3

        # ---- PackIt PMa5 (XOR) and PMa6 (DES) -------------------------
        want = {"Read Me": b"not a secret\n",
                "Trailer": b"after the secret\n"}
        for name, data, rsrc in SC.PIT_CASES:
            want[name] = data
            if rsrc:
                want[name + ".rsrc"] = rsrc
        for kind in ("packit-xor", "packit-des"):
            p = os.path.join(tmp, kind + ".pit")
            synth(kind, p, LONG_PW)
            check_one(kind, p, want, LONG_PW, unclassic, problems)
            # A wrong password must not stop the walk: the two clear
            # entries either side of the encrypted ones still come out.
            out = tempfile.mkdtemp()
            r = run([unclassic, "x", "-o", out, "-p", "wrong", p])
            if r.returncode == 0:
                problems.append("%s: a wrong password was accepted" % kind)
            for n in ("Read Me", "Trailer"):
                if extracted(out, n) != want[n]:
                    problems.append("%s: %s was lost when the password was "
                                    "wrong" % (kind, n))
            shutil.rmtree(out, ignore_errors=True)
            ran += 2

        # ---- zip, from Info-ZIP itself --------------------------------
        if shutil.which("zip"):
            src = tempfile.mkdtemp()
            payload = {"deflated.txt": b"the same line, over and over\n" * 40,
                       "random.bin": bytes((i * 37 + 11) & 0xFF
                                           for i in range(5000)),
                       "tiny.txt": b"x"}
            for n, b in payload.items():
                open(os.path.join(src, n), "wb").write(b)
            for label, zargs in (("zip-deflate", []), ("zip-store", ["-0"])):
                z = os.path.join(tmp, label + ".zip")
                run(["zip", "-q", "-j", "-P", LONG_PW] + zargs +
                    [z] + [os.path.join(src, n) for n in payload])
                check_one(label, z, payload, LONG_PW, unclassic, problems)
                check_refusal("%s wrong password" % label, z, unclassic,
                              problems, ["-p", "nope"])
                check_refusal("%s no password" % label, z, unclassic,
                              problems)
                ran += 3
            shutil.rmtree(src, ignore_errors=True)
        else:
            print("run_crypt: no `zip`, PKWARE-cipher fixtures skipped")

        # ---- ARC, from Debian's `arc` if it is here -------------------
        if os.path.exists(ARC_BIN):
            src = tempfile.mkdtemp()
            payload = {"crunched.txt": b"quick brown fox " * 30,
                       "stored.bin": bytes((i * 91 + 7) & 0xFF
                                           for i in range(3000))}
            for n, b in payload.items():
                open(os.path.join(src, n), "wb").write(b)
            garbled = os.path.join(tmp, "garbled.arc")
            run([ARC_BIN, "ag" + LONG_PW, garbled] + list(payload), cwd=src)
            # `arc` upper-cases the password before garbling with it,
            # so the archive is keyed on the CAPITALS: the oracle only
            # opens it with those, and we must open it with either.
            check_one("arc garble (as `arc` keyed it)", garbled, payload,
                      LONG_PW.upper(), unclassic, problems)
            check_one("arc garble (as the user typed it)", garbled, payload,
                      LONG_PW, unclassic, problems, oracle=False)
            ran += 2
            # And with no password at all it must fail, not emit rubbish.
            # Garbled input reaches the decoder as nonsense, so which of
            # the two failures comes out depends on the method.
            r = run([unclassic, "t", garbled])
            if r.returncode == 0:
                problems.append("arc garble: opened without a password")
            ran += 1
            shutil.rmtree(src, ignore_errors=True)
        else:
            print("run_crypt: no `arc` at %s, garbled ARC skipped" % ARC_BIN)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for p in problems:
        print("run_crypt: " + p)
    print("crypt: %d case(s) checked, %d problem(s)" % (ran, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
