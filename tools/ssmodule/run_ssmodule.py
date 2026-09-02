#!/usr/bin/env python3
"""run_ssmodule.py — run SpaceSaver's own codecs, off the Macintosh.

StuffIt SpaceSaver has been the one format here graded by nothing but
itself: no oracle, no fixture and no specimen, because no run of the
application under Mini vMac has ever made it compress anything
(OPEN_ITEMS.md). Methods 1, 2 and 3 were declined per entry for exactly
that reason — nothing reachable WRITES one, so an implementation could
not be graded.

**Aladdin's codecs run on Linux.** Each is a `CMod` resource holding
position-independent 68k with a compressor at +0x08 and an expander at
+0x10, and `ssmod_run.c` calls either under `qemu-m68k` — the
arrangement `tools/sdmodule/` already uses for SuperDisk!'s Add-In
Modules. That makes the modules both the specimen generator and the
second implementation, for every method the format has:

    tools/ssmodule/run_ssmodule.py --macextract build/macextract

Four phases, and the first two are what make the third mean anything:

  1. **round trip through Aladdin's code alone** — each module
     compresses a subject and the matching expander decodes it, which
     establishes that the parameter block, the callbacks and the work
     buffer are right before this engine is asked to agree with
     anything. Two things the modules themselves do are counted rather
     than treated as this harness's failures, and both are named below;
  2. **negative controls** — a corrupted stream, and method 4 decoded
     without the preset dictionary. Both must come back wrong, because
     a comparison that has never failed is not evidence;
  2b. **corrupted specimens through this engine**, which must refuse
     rather than crash or hang — the corpus has no SpaceSaver fixture,
     so `run_robustness.py` never sees these codecs;
  3. **this engine against the module**, for the methods it implements
     (0 and 4): the module writes, `macextract` reads, and the result
     must be the subject byte for byte;
  4. **what the module writes for 1, 2 and 3 is kept**, as `.ss` files
     beside the emulator's other state, so that an implementation of
     those methods has specimens the day it is written.

Two properties of the "Original" modules, measured here on 2026-08-25:

  - **Their `store this block verbatim` path is an F-line word.** Both
    compressors reach `0xFFFF` — not a 68000 instruction — at `CMod 3`
    @0x5e4 and `CMod 4` @0x6ba, on the branch that gives up on a block
    (`CMod 3` @0x34c reaches it when the output would pass its limit).
    About a third of the subjects here take it. Nothing is emulated for
    it, because what it stands for cannot be read off the code; the run
    is counted, and every OTHER kind of fault is a failure. The path it
    would have written is still covered — `phase_stored` builds a
    stored block by hand and requires the expander to return it, which
    is how its layout is known: flag byte 1 at +0, a big-endian payload
    length at +4, payload at +8.
  - **Method 1's expander does not terminate on a corrupted stream.**
    `CMod 3` spins rather than refusing, so every module call here has a
    timeout and a timeout is a fired negative control, not a hang.

What this CANNOT see:

  - **Agreement is not correctness for the CONTAINER.** The modules
     know nothing about the 84-byte header; a fork's stream is exactly
     what the module wrote, so this grades codecs and not the file.
  - **A module is not the application.** SpaceSaver chooses a method by
     CPU, rounds a file's length to 256 bytes, and writes the header;
     none of that is exercised here, and a file SpaceSaver itself wrote
     would still settle it (OPEN_ITEMS.md).
  - **The subjects are ours.** A codec that mishandles input no test
     here builds is not visible — the same limit `run_spacesaver.py`'s
     synthetic pass has.

Nothing here fails when the prerequisites are absent: no cross
compiler, no `qemu-m68k` or no installed SpaceSaver image prints what
was skipped and returns 0, so a fresh clone stays green.

License: LGPL-2.1-or-later. See LICENSE and NOTICE.
"""
import argparse
import os
import random
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "tools", "vmac"))

HOME = os.environ.get("UNC_VMAC_HOME",
                      os.path.expanduser("~/.cache/macextract/vmac"))
SPECIMENS = os.path.join(HOME, "specimens", "spacesaver")

# Which module writes each method, and which one reads it back. The
# decompress-only builds (11, 21) are the second reader for the two
# methods that have one, and they are the modules any Mac can run
# (FORMATS.md, "StuffIt SpaceSaver").
METHODS = {
    0: ("Default Compressor",       1,  [1]),
    1: ("Original Fast Compressor", 3,  [3]),
    2: ("Original Slow Compressor", 4,  [4]),
    3: ("Alg 3",                    10, [10, 11]),
    4: ("Alg 4",                    20, [20, 21]),
}

# Methods 3 and 4 read the preset dictionary out of the parameter block
# and 1 and 2 never touch it (`CMod 3`/`CMod 4` reference no field past
# +52, measured). Passing it anyway would hide a codec that started to.
NEEDS_PRESET = (3, 4)

IMPLEMENTED = (0, 1, 2, 3, 4)      # what src/fmt_spacesaver.c decodes


def subjects(n_random, seed):
    """Inputs a codec has to survive, not just compress well."""
    rng = random.Random(seed)
    out = [("readme", open(os.path.join(REPO, "README.md"), "rb").read()),
           ("zeroes", b"\x00" * 40000),
           ("ones", b"\xff" * 5000),
           ("short", b"x"),
           ("empty", b""),
           ("runs", b"".join(bytes([i]) * 300 for i in range(256))),
           ("random", bytes(rng.randrange(256) for _ in range(20000)))]
    words = [b"the quick brown fox ", b"SpaceSaver ", b"\x00" * 40,
             b"Macintosh System 7 ", b"abcdefghijklmnop"]
    for i in range(n_random):
        body = bytearray()
        while len(body) < rng.randrange(1000, 120000):
            body += rng.choice(words)
        out.append(("mixed%d" % i, bytes(body)))
    return out


def build_runner():
    exe = os.path.join(REPO, "build", "ssmod_run")
    src = os.path.join(HERE, "ssmod_run.c")
    if os.path.exists(exe) and os.path.getmtime(exe) > os.path.getmtime(src):
        return exe
    os.makedirs(os.path.dirname(exe), exist_ok=True)
    r = subprocess.run(["m68k-linux-gnu-gcc", "-O1", "-static", "-o", exe, src],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("ssmodule: building ssmod_run failed:\n" + r.stderr)
    return exe


def modules(workdir):
    """Lift every `CMod` and the preset out of the installed control panel.

    No emulator: `hcopy` reads the image and the resource map is parsed
    here, the same way `spacesaver.py --layout` reads the layout.
    """
    import spacesaver as S
    from superdisk import read_forks
    if not os.path.exists(S.INSTALLED):
        return None, None
    got, preset = {}, None
    for path, (_ftype, creator, _data, rsrc) in read_forks(S.INSTALLED).items():
        if creator != "SMKR":
            continue
        res = S.resources(rsrc)
        for rid, (name, code) in res.get("CMod", {}).items():
            p = os.path.join(workdir, "CMod%d.bin" % rid)
            with open(p, "wb") as f:
                f.write(code)
            got[rid] = (name, p, len(code))
        for rid, (_name, data) in res.get("PrAm", {}).items():
            if rid == -4048:
                preset = os.path.join(workdir, "PrAm-4048.bin")
                with open(preset, "wb") as f:
                    f.write(data)
        break
    return got, preset


def run_module(exe, module, what, src, dst, preset, ulen, cpu, timeout=60):
    cmd = ["qemu-m68k"]
    if cpu:
        cmd += ["-cpu", cpu]
    cmd += [exe, module, what, src, dst, preset or "", str(ulen)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # `CMod 3` loops rather than refusing a stream it cannot parse.
        return {"status": "timeout", "rc": -1, "stderr": ""}
    fields = {}
    for tok in (r.stdout.split() if r.stdout else []):
        if "=" in tok:
            k, v = tok.split("=", 1)
            fields[k] = v
    fields["rc"] = r.returncode
    fields["stderr"] = r.stderr.strip()
    return fields


# Where each "Original" compressor gives up on a block and executes the
# F-line word 0xFFFF instead of storing it. A fault at exactly these
# offsets is the known path; anywhere else is a failure of this harness.
FLINE = {3: 1508, 4: 1722}          # CMod 3 @0x5e4, CMod 4 @0x6ba


def phase_roundtrip(exe, mods, preset, subs, cpu, verbose):
    """Aladdin's compressor and Aladdin's expander, and nothing else."""
    bad = ok = gaveup = 0
    tmp = tempfile.mkdtemp(prefix="ssmod-rt-")
    written = {}
    try:
        for method, (name, writer, readers) in sorted(METHODS.items()):
            if writer not in mods:
                print("ssmodule: no CMod for method %d — skipped" % method)
                continue
            use = preset if method in NEEDS_PRESET else None
            for label, data in subs:
                sp = os.path.join(tmp, "in")
                cp = os.path.join(tmp, "c")
                with open(sp, "wb") as f:
                    f.write(data)
                c = run_module(exe, mods[writer][1], "compress", sp, cp,
                               use, len(data), cpu)
                if c.get("status") != "0":
                    known = (c.get("op") == "ffff"
                             and c.get("pc") == str(FLINE.get(writer)))
                    if known:
                        gaveup += 1
                        if verbose:
                            print("ssmodule: method %d %-8s reached the "
                                  "F-line store path" % (method, label))
                    else:
                        print("ssmodule: method %d (%s) refused %s: %s"
                              % (method, name, label, c))
                        bad += 1
                    continue
                clen = os.path.getsize(cp)
                for reader in readers:
                    if reader not in mods:
                        continue
                    xp = os.path.join(tmp, "x")
                    x = run_module(exe, mods[reader][1], "expand", cp, xp,
                                   use, len(data), cpu)
                    got = open(xp, "rb").read() if os.path.exists(xp) else b""
                    if x.get("status") != "0" or got != data:
                        print("ssmodule: MISMATCH method %d %s via CMod %d: "
                              "%d B in, %d B out, %s"
                              % (method, label, reader, len(data), len(got), x))
                        bad += 1
                    else:
                        ok += 1
                        if verbose:
                            print("ssmodule: method %d %-8s %6d -> %6d B, "
                                  "CMod %d agrees" % (method, label, len(data),
                                                      clen, reader))
                written.setdefault(method, []).append(
                    (label, data, open(cp, "rb").read()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ssmodule: round trip through Aladdin's own code: %d agreements, "
          "%d inputs the Original compressors would have STORED (their F-line "
          "path, not run here), %d failures" % (ok, gaveup, bad))
    return bad == 0 and ok > 0, written


def phase_controls(exe, mods, preset, cpu):
    """Three ways the comparison above must be able to fail.

    The SUBJECT is the control here, and picking it out of the sweep by
    a heuristic got this wrong twice: the largest stream is the random
    one, which is all literals and so decodes the same with no
    dictionary at all, and the best-compressing one is 40,000 zeroes,
    which decodes to zeroes however it is damaged. Both made a control
    that could not fire. This uses one deliberate subject — ordinary
    prose, compressible, no long runs — and requires it to have
    compressed before it trusts either check.
    """
    data = open(os.path.join(REPO, "README.md"), "rb").read()
    bad = 0
    tmp = tempfile.mkdtemp(prefix="ssmod-neg-")
    try:
        sp = os.path.join(tmp, "in")
        with open(sp, "wb") as f:
            f.write(data)
        for method in sorted(METHODS):
            if method == 0:
                continue                       # stored: nothing to corrupt
            writer, reader = METHODS[method][1], METHODS[method][2][-1]
            if writer not in mods or reader not in mods:
                continue
            use = preset if method in NEEDS_PRESET else None
            cp = os.path.join(tmp, "c")
            c = run_module(exe, mods[writer][1], "compress", sp, cp, use,
                           len(data), cpu)
            if c.get("status") != "0" or os.path.getsize(cp) >= len(data):
                print("ssmodule: method %d did not compress the control "
                      "subject (%s) — the checks below would be vacuous"
                      % (method, c.get("status")))
                bad += 1
                continue
            stream = open(cp, "rb").read()

            hurt = bytearray(stream)
            hurt[len(hurt) // 2] ^= 0xFF
            bp = os.path.join(tmp, "b")
            with open(bp, "wb") as f:
                f.write(bytes(hurt))
            xp = os.path.join(tmp, "x")
            if os.path.exists(xp):
                os.remove(xp)
            run_module(exe, mods[reader][1], "expand", bp, xp, use,
                       len(data), cpu)
            got = open(xp, "rb").read() if os.path.exists(xp) else b""
            if got == data:
                print("ssmodule: THE COMPARISON CANNOT FAIL — method %d "
                      "decoded a corrupted stream to the subject" % method)
                bad += 1

            # The dictionary is not decoration: without it the stream has
            # to come back wrong rather than right (DECISIONS.md
            # 2026-08-22, the codecs).
            if method in NEEDS_PRESET:
                if os.path.exists(xp):
                    os.remove(xp)
                run_module(exe, mods[reader][1], "expand", cp, xp, None,
                           len(data), cpu)
                got = open(xp, "rb").read() if os.path.exists(xp) else b""
                if got == data:
                    print("ssmodule: method %d decoded WITHOUT the preset "
                          "dictionary — the window is not preloaded" % method)
                    bad += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ssmodule: negative controls: %s"
          % ("all fired" if bad == 0 else "%d did not fire" % bad))
    return bad == 0


def phase_stored(exe, mods, cpu):
    """The block the Original compressors will not write here.

    Their store path is an F-line word this harness does not emulate,
    so the shape of a stored block is established from the other side:
    built by hand and handed to Aladdin's own expander, which must
    return the payload verbatim. `CMod 3` @0x184 reads an 8-byte header
    and then `a2@(4)` bytes, and @0x1b6 skips the decoder when the
    header's first byte is 1.
    """
    payload = b"A stored block, verbatim. " * 40
    blk = bytearray(8)
    blk[0] = 1
    blk[4:8] = len(payload).to_bytes(4, "big")
    bad = 0
    tmp = tempfile.mkdtemp(prefix="ssmod-stored-")
    try:
        sp = os.path.join(tmp, "s")
        with open(sp, "wb") as f:
            f.write(bytes(blk) + payload)
        for method in (1, 2):
            reader = METHODS[method][2][-1]
            if reader not in mods:
                continue
            xp = os.path.join(tmp, "x")
            r = run_module(exe, mods[reader][1], "expand", sp, xp, None,
                           len(payload), cpu)
            got = open(xp, "rb").read() if os.path.exists(xp) else b""
            if r.get("status") != "0" or got != payload:
                print("ssmodule: method %d did NOT return a hand-built "
                      "stored block: %s, %d B" % (method, r.get("status"),
                                                  len(got)))
                bad += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ssmodule: stored blocks: %s"
          % ("methods 1 and 2 return one verbatim" if bad == 0
             else "%d wrong" % bad))
    return bad == 0


def phase_engine(exe_unc, written, preset, verbose):
    """What the module wrote, read by this engine.

    Methods 0 and 4 must decode byte for byte. Methods 1, 2 and 3 are
    declined per entry, and that is asserted rather than assumed: the
    file is still recognised and the ENTRY is what fails.
    """
    from run_spacesaver import container
    bad = ok = declined = 0
    tmp = tempfile.mkdtemp(prefix="ssmod-eng-")
    try:
        for method, cases in sorted(written.items()):
            for label, data, stream in cases:
                if not data:
                    # A fork of zero bytes is an ABSENT fork by the
                    # format's own rule (`SetupAFork` @0x53d4 clears the
                    # method with the length), so the container cannot
                    # carry "method 1, nothing in it" and this phase has
                    # nothing to grade.
                    continue
                p = os.path.join(tmp, "t.ss")
                with open(p, "wb") as f:
                    f.write(container(stream, len(data), method=method))
                out = os.path.join(tmp, "out")
                shutil.rmtree(out, ignore_errors=True)
                os.makedirs(out)
                cmd = [exe_unc, "x", "-o", out, p]
                if preset and method in NEEDS_PRESET:
                    cmd = [exe_unc, "x", "--preset", preset, "-o", out, p]
                r = subprocess.run(cmd, capture_output=True, text=True)
                got = None
                q = os.path.join(out, "t.ss")
                if os.path.exists(q):
                    got = open(q, "rb").read()
                if method in IMPLEMENTED:
                    if r.returncode != 0 or got != data:
                        print("ssmodule: MISMATCH engine vs CMod, method %d "
                              "%s: rc=%d %s" % (method, label, r.returncode,
                                                (r.stderr or "").strip()))
                        bad += 1
                    else:
                        ok += 1
                        if verbose:
                            print("ssmodule: method %d %-8s engine agrees "
                                  "with the module, %d B" % (method, label,
                                                             len(data)))
                else:
                    if r.returncode == 0 and got == data:
                        print("ssmodule: method %d decoded, but this engine "
                              "declares it unsupported — one of the two is "
                              "wrong" % method)
                        bad += 1
                    else:
                        declined += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ssmodule: this engine against the module: %d entries byte-exact, "
          "%d declined as documented, %d wrong" % (ok, declined, bad))
    return bad == 0 and ok > 0


def phase_fuzz(exe_unc, written, preset, cases, seed):
    """Corrupt what the module wrote and require a clean refusal.

    The engine's own robustness suite has no SpaceSaver fixture to work
    on (there is none in the corpus), so the specimens this harness
    makes are the only place these three codecs meet damaged input.
    What is checked is what `run_robustness.py` checks everywhere else:
    the process exits, and it exits as itself rather than as a signal.
    """
    rng = random.Random(seed)
    bad = ran = 0
    tmp = tempfile.mkdtemp(prefix="ssmod-fuzz-")
    try:
        out = os.path.join(tmp, "out")
        os.makedirs(out)
        for method, cases_ in sorted(written.items()):
            if method == 0:
                continue
            label, data, stream = max(cases_, key=lambda c: len(c[2]))
            if not data:
                continue
            from run_spacesaver import container
            base = container(stream, len(data), method=method)
            for _ in range(cases):
                b = bytearray(base)
                for _ in range(rng.randrange(1, 5)):
                    b[rng.randrange(84, len(b))] ^= 1 << rng.randrange(8)
                p = os.path.join(tmp, "f.ss")
                with open(p, "wb") as f:
                    f.write(bytes(b))
                cmd = [exe_unc, "x", "-o", out, "--overwrite"]
                if preset and method in NEEDS_PRESET:
                    cmd += ["--preset", preset]
                cmd.append(p)
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True,
                                       timeout=60)
                except subprocess.TimeoutExpired:
                    print("ssmodule: method %d: a corrupted stream did not "
                          "terminate" % method)
                    bad += 1
                    continue
                ran += 1
                if r.returncode not in (0, 1):
                    print("ssmodule: method %d: corrupted stream exited %d\n%s"
                          % (method, r.returncode, (r.stderr or "")[-400:]))
                    bad += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ssmodule: %d corrupted variant(s), %d bad" % (ran, bad))
    return bad == 0


def phase_keep(written, preset):
    """Keep one specimen per method, where the suite already looks.

    They are what Aladdin's compressor made of a subject, so they live
    beside the emulator's other state rather than in the repository —
    the rule the `.ss` specimens and the dictionary already follow. They
    go in a SUBDIRECTORY, because `run_spacesaver.py` grades every
    `.ss` beside it and three of these five use a method this engine
    does not implement, which would fail that suite by design.
    """
    from run_spacesaver import container
    out = os.path.join(SPECIMENS, "modules")
    os.makedirs(out, exist_ok=True)
    kept = []
    for method, cases in sorted(written.items()):
        label, data, stream = max(cases, key=lambda c: len(c[1]))
        p = os.path.join(out, "m%d.ss" % method)
        with open(p, "wb") as f:
            f.write(container(stream, len(data), method=method))
        with open(p + ".orig", "wb") as f:
            f.write(data)
        kept.append("m%d (%s, %d -> %d B)"
                    % (method, label, len(data), len(stream)))
    print("ssmodule: specimens written to %s: %s" % (out, ", ".join(kept)))
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--macextract",
                    default=os.path.join(REPO, "build", "macextract"))
    ap.add_argument("--cases", type=int, default=4,
                    help="mixed subjects per method (default 4)")
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--fuzz", type=int, default=40,
                    help="corrupted variants per method (default 40)")
    ap.add_argument("--cpu", default="m68030",
                    help="the CPU qemu emulates; Alg 3 is a 68030 codec")
    ap.add_argument("--keep", action="store_true",
                    help="write one specimen per method into the cache")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.macextract):
        print("ssmodule: no CLI at %s" % args.macextract)
        return 1

    if not shutil.which("qemu-m68k") or not shutil.which("m68k-linux-gnu-gcc"):
        print("ssmodule: needs qemu-m68k and the m68k cross-compiler — "
              "skipping")
        return 0
    workdir = tempfile.mkdtemp(prefix="ssmodule-")
    try:
        mods, preset = modules(workdir)
        if not mods:
            print("ssmodule: no installed SpaceSaver image (%s) — skipping"
                  % HOME)
            return 0
        print("ssmodule: modules: " + ", ".join(
            "%d %s (%d B)" % (rid, mods[rid][0], mods[rid][2])
            for rid in sorted(mods)))
        exe = build_runner()
        subs = subjects(args.cases, args.seed)
        a, written = phase_roundtrip(exe, mods, preset, subs, args.cpu,
                                     args.verbose)
        b = phase_controls(exe, mods, preset, args.cpu)
        s_ = phase_stored(exe, mods, args.cpu)
        c = phase_engine(args.macextract, written, preset, args.verbose)
        z = phase_fuzz(args.macextract, written, preset, args.fuzz, args.seed)
        d = phase_keep(written, preset) if args.keep else True
        return 0 if (a and b and s_ and c and z and d) else 1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
