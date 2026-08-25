#!/usr/bin/env python3
"""run_sdmodule.py — grade the SuperDisk! decoder against Alysis's own.

SuperDisk! has no second implementation: `unar` and `macunpack` stop at the
envelope, and until now the only oracle was the archives' own self-extractors
run on an emulated Mac (`tools/vmac/superdisk.py --adjudicate`), which costs a
boot and can only decode the two forks those archives happen to contain.

**The Add-In Modules are that second implementation, and they are in the
corpus.** Disk Expander 1.2 — which `fixtures/alysis-disk-expander-12.hqx`
carries and this engine extracts — has one `Cmpr` resource per codec, each a
self-contained 68k decoder with no Toolbox in it. `sdmod_run.c` calls one
under `qemu-m68k`; this drives it.

    tools/sdmodule/run_sdmodule.py --unclassic build/unclassic

Four things happen, and the first three are what make the last trustworthy:

  1. **the modules are lifted out of the corpus** (methods 1, 2, 9, 10, 11,
     13 and 20 — the last three are codecs this engine does not implement);
  2. **every real block in both corpus archives** whose method has a module
     is decoded by that module and compared with what this engine wrote —
     and one block is deliberately corrupted, because a comparison that has
     never failed is not evidence;
  3. **the specimens Alysis's own 1991 compressor wrote**, when they are in
     the emulator cache (`tools/vmac/sdcompress.py`): methods 1 and 6, the
     only SuperDisk! data in reach that a COMPRESSOR produced;
  4. **synthetic blocks** are built for the methods no archive here uses, and
     put through both implementations.

The one thing to know before reading the code: "Tighter" decodes methods 2,
3, 4, 6, 7 and 8 and hands its Huffman regions back to its CALLER — a `jsr`
through a field of the parameter block — so `sdmod_run.c` has to be a
dispatcher as well as a loader.

What it CANNOT see, and each of these is a real gap:

  - **Methods 10, 13 and 20 have a module and nothing to feed it.** Their
    codecs are here and this engine does not implement them, so all this
    harness can say about those three is that the modules load.
  - **A synthetic block only exercises what this engine's reading can
    build.** The Huffman regions are written with a flat 8-bit table (an
    identity code), so tree shapes a real encoder would emit are untested —
    what is graded is the FRAMING, the flag bitmap and the context
    predictor, not the code assignment.
  - **Agreement is not correctness where both sides came from one reading.**
    The module is an independent implementation of the format, so a framing
    error shows up; a misunderstanding of what the ORIGINAL COMPRESSOR emits
    does not.

License: LGPL-2.1-or-later. See LICENSE and NOTICE.
"""
import argparse
import glob
import os
import random
import struct
import subprocess
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SIG = b"SuperDisk! Add-In Module"

# The fixture that carries Disk Expander 1.2, and the file inside it whose
# resource fork holds the codecs.
MODULE_FIXTURE = "alysis-disk-expander-12.hqx"
MODULE_FILE = "Disk Expander /Disk Expander.rsrc"

# Both SuperDisk! containers in the corpus, as the payload inside the BinHex.
CORPUS = ["alysis-disk-expander-12.hqx", "super-disk-utility.hqx"]


def sh(*cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return r


# ---------------------------------------------------------------- resources

def resource_data(fork):
    """Every resource in a resource fork, as {type: [(id, name, bytes)]}."""
    do, ro, dl, rl = struct.unpack(">IIII", fork[:16])
    m = fork[ro:ro + rl]
    tlo, nlo = struct.unpack(">HH", m[24:28])
    out = {}
    ntypes = struct.unpack(">h", m[tlo:tlo + 2])[0] + 1
    for i in range(ntypes):
        off = tlo + 2 + i * 8
        typ = m[off:off + 4].decode("mac_roman")
        n = struct.unpack(">H", m[off + 4:off + 6])[0] + 1
        rlo = struct.unpack(">H", m[off + 6:off + 8])[0]
        items = []
        for j in range(n):
            e = tlo + rlo + j * 12
            rid = struct.unpack(">h", m[e:e + 2])[0]
            noff = struct.unpack(">h", m[e + 2:e + 4])[0]
            doff = struct.unpack(">I", m[e + 4:e + 8])[0] & 0xFFFFFF
            name = ""
            if noff != -1:
                p = nlo + noff
                name = m[p + 1:p + 1 + m[p]].decode("mac_roman")
            dlen = struct.unpack(">I", fork[do + doff:do + doff + 4])[0]
            items.append((rid, name, fork[do + doff + 4:do + doff + 4 + dlen]))
        out[typ] = items
    return out


def module_entry(blob):
    """Where a module's code starts.

    Most begin with a BRA.W over their own header; Tennessee does not, and
    its header's first long is zero. The reliable landmark in both is the
    selector fetch — MOVEW A0@(36),D0 — with the MOVEM prologue eight bytes
    before it when there is one.
    """
    if blob[:2] == b"\x60\x00":
        return 2 + struct.unpack(">h", blob[2:4])[0]
    i = blob.find(b"\x30\x28\x00\x24")
    if i < 0:
        return None
    if blob[i - 8:i - 6] == b"\x48\xe7":
        return i - 8
    return i


def modules(unclassic, workdir):
    """Lift every Add-In Module out of the corpus fixture.

    They are not one per resource: `Cmpr` 22 holds SlowFastB and Tennessee
    end to end, so the signature is searched for rather than assumed.
    """
    out = os.path.join(workdir, "dexp")
    os.makedirs(out, exist_ok=True)
    r = sh(unclassic, "x", "-o", out, os.path.join(REPO, "fixtures", MODULE_FIXTURE))
    if r.returncode != 0:
        raise SystemExit(f"sdmodule: extracting {MODULE_FIXTURE} failed:\n{r.stderr}")
    fork = open(os.path.join(out, MODULE_FILE), "rb").read()
    res = resource_data(fork)
    found = {}
    for rid, name, blob in res.get("Cmpr", []):
        at = 0
        while True:
            i = blob.find(SIG, at)
            if i < 0:
                break
            m = i - 4
            method = struct.unpack(">H", blob[m + 0x1C:m + 0x1E])[0]
            length = struct.unpack(">I", blob[m + 0x26:m + 0x2A])[0]
            n = blob[m + 0x3C]
            mname = blob[m + 0x3D:m + 0x3D + n].decode("mac_roman").strip()
            at = i + 4
            if not (0 < method < 100) or not (0 < length <= len(blob) - m):
                continue
            body = blob[m:m + length]
            entry = module_entry(body)
            if entry is None:
                continue
            # One module per method is enough; the first is the one the
            # extension's own dispatcher reaches first.
            found.setdefault(method, (mname, body, entry, rid))
    return found


# ---------------------------------------------------------------- container

def block_head(d, p):
    """clen, ulen, method, stored — the six bytes at the head of a block."""
    n = struct.unpack(">H", d[p:p + 2])[0]
    if n & 0x8000:
        if n == 0x8002:
            return 0x8002, 0x8000, 0, True
        n &= 0x7FFF
        return n, n - 2, 0, True
    return n, struct.unpack(">H", d[p + 2:p + 4])[0], \
        struct.unpack(">H", d[p + 4:p + 6])[0], False


def walk(d):
    """Every fork in a SuperDisk! archive, as (path, fork, [blocks])."""
    at = 8
    if d[8] in (0x28, 0x29) and d[9:16] == b"\0" * 7:
        start = 8
    else:
        ln = struct.unpack(">I", d[8:12])[0]
        at = 12
        while ln:
            if d[at + 4:at + 28] != SIG:
                raise SystemExit("sdmodule: module chain does not parse")
            at += ln
            ln = struct.unpack(">I", d[at:at + 4])[0]
            at += 4
        start = at

    def fork_blocks(p, want):
        done, out = 0, []
        while done < want:
            clen, ulen, meth, stored = block_head(d, p)
            if ulen > want - done:
                ulen = want - done
            out.append((p, clen, ulen, meth, stored))
            done += ulen
            p += clen
        return out, p

    at, path, forks = start, [], []
    while d[at] != 0x27:
        tag = d[at]
        if tag == 0x2A:
            path.pop()
            at += 8
            continue
        nlen = d[at + 8]
        name = d[at + 9:at + 9 + nlen].decode("mac_roman")
        p = at + 9 + nlen
        if p & 1:
            p += 1
        if tag == 0x29:
            path.append(name)
            at = p + 20
            continue
        dlen, rlen = struct.unpack(">II", d[p:p + 8])
        at2 = p + 30
        full = "/".join(path + [name])
        end = at2
        if dlen:
            blocks, end = fork_blocks(at2, dlen)
            forks.append((full, "data", dlen, blocks))
        if rlen:
            blocks, end = fork_blocks(end, rlen)
            forks.append((full, "rsrc", rlen, blocks))
        at = end
    return forks


# ------------------------------------------------------------------ running

def run_module(mods, method, src, cap, prefix=None, selector=3):
    """Decode `src` with the module for `method`.

    Every module goes into the manifest, not just the one being called:
    "Tighter" hands its flag bitmap back through the callback for method 9
    to decode, so a run with one module in it dies at address zero.
    """
    tmp = tempfile.mkdtemp(prefix="sdmod-")
    try:
        want = method
        if selector == 3 and method < 9:
            want = 1 if method in (1, 5) else 2
        if want not in mods:
            return None, f"no module for method {method}"
        lines = []
        for m in [want] + [k for k in sorted(mods) if k != want]:
            name, blob, entry, _rid = mods[m]
            mp = os.path.join(tmp, f"mod{m}.bin")
            open(mp, "wb").write(blob)
            lines.append(f"{m} {entry} {mp}")
        mf = os.path.join(tmp, "manifest")
        open(mf, "w").write("\n".join(lines) + "\n")
        sp = os.path.join(tmp, "src.bin")
        op = os.path.join(tmp, "out.bin")
        open(sp, "wb").write(src)
        cmd = ["qemu-m68k", os.path.join(REPO, "build", "sdmod_run"), mf, sp, op,
               str(selector), str(method), str(cap)]
        if prefix is not None:
            pp = os.path.join(tmp, "pre.bin")
            open(pp, "wb").write(prefix)
            cmd.append(pp)
        r = sh(*cmd)
        if r.returncode != 0:
            return None, r.stdout.strip() or f"exit {r.returncode}"
        status = int(r.stdout.split("status=")[1].split()[0])
        return open(op, "rb").read(), status
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_runner():
    """The m68k runner, built into build/ rather than beside its source: it
    is an artifact, and `make clean` taking it away costs a second."""
    exe = os.path.join(REPO, "build", "sdmod_run")
    src = os.path.join(HERE, "sdmod_run.c")
    os.makedirs(os.path.join(REPO, "build"), exist_ok=True)
    if os.path.exists(exe) and os.path.getmtime(exe) > os.path.getmtime(src):
        return exe
    r = sh("m68k-linux-gnu-gcc", "-std=gnu99", "-O2", "-static",
           "-fomit-frame-pointer", "-o", exe, src)
    if r.returncode != 0:
        raise SystemExit(f"sdmodule: building sdmod_run failed:\n{r.stderr}")
    return exe


# ------------------------------------------------------- our side, per block

def single_container(block, ulen, name=b"T"):
    """A SuperDisk! single-file container holding one block.

    The layout is FORMATS.md's, and it is what lets one block be handed to
    the shipping CLI without a per-block entry point into the engine.
    """
    hdr = struct.pack(">IIIII", ulen, ulen, 0, 0x54455854, 0x74747874)
    hdr += struct.pack(">H", 0) + struct.pack(">II", 0, 0)
    hdr += bytes([len(name)]) + name
    if len(hdr) % 2:
        hdr += b"\0"
    return hdr + block


def ours(unclassic, block, ulen, workdir):
    """What this engine makes of one block, or None if it refuses it."""
    p = os.path.join(workdir, "one.x")
    out = os.path.join(workdir, "one")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    open(p, "wb").write(single_container(block, ulen))
    r = sh(unclassic, "x", "-o", out, p)
    f = os.path.join(out, "T")
    if r.returncode != 0 or not os.path.exists(f):
        return None
    return open(f, "rb").read()


# --------------------------------------------------------- synthetic blocks

def huff_identity(payload):
    """A Huffman region whose code is a flat 8 bits — the identity map.

    Header, then a 256-byte symbol table, then the limit table, then the
    bitstream. `startbits` 8 with a first limit of 256 means every 8-bit
    code is its own symbol, so the bitstream IS the payload. What this
    grades is the region's framing and where the next region starts, not
    the code assignment.
    """
    sym = bytes(range(256))
    limits = struct.pack(">HH", 0x0100, 0xFFFF)
    ct_rel = 8 + len(sym) - 10          # ct = at + 10 + ct_rel
    bits = payload + b"\0" * ((-len(payload)) % 4)
    bitpos = 8 + len(sym) + len(limits)
    head = struct.pack(">HBBHH", len(payload), 8, 0, bitpos, ct_rel)
    return head + sym + limits + bits, bitpos + len(bits)


def synth_block(method, payload, flagbits):
    """One coded block for a method in the 1..9 family.

    `flagbits` is one bit per output byte after the first two: 1 says "the
    byte this context predicted", 0 says "the next literal". Building both
    forms from this engine's reading is the point — the module is what says
    whether the reading is right.
    """
    ulen = len(payload)
    fsize = ((ulen >> 3) + 4) & ~1
    nflags = min((ulen + 7) >> 3, fsize)
    flags = bytearray(fsize)
    lits = bytearray()
    ctx = 0
    tbl = bytearray(0x10000)
    wide = 5 <= method <= 8
    shift = 6 if wide else 5
    mask = 0xFFFF if wide else 0x1FFF
    for i, b in enumerate(payload):
        if i < 2:
            lits.append(b)
            continue
        j = i - 2
        predict = flagbits[j] and tbl[ctx] == b
        if predict:
            flags[j >> 3] |= 0x80 >> (j & 7)
        else:
            lits.append(b)
            tbl[ctx] = b
        ctx = (ctx << shift) & 0xFFFF
        ctx = (ctx & 0xFF00) | ((ctx | b) & 0x00FF)
        ctx &= mask
    base = method - 4 if wide else method
    if base in (1, 3):
        body = bytes(flags[:fsize])
    else:
        # Two bytes of slack after a Huffman region: the next one starts at
        # the bit reader's cursor PLUS TWO (sd_huff_end, from CODE 2 @0x84a),
        # and the cursor is a whole number of 32-bit refills.
        region, _ = huff_identity(bytes(flags[:nflags]))
        body = region + b"\0\0"
    if base in (3, 4):
        region, _ = huff_identity(bytes(lits))
        body += region
    else:
        body += bytes(lits)
    return struct.pack(">HHH", 6 + len(body), ulen, method) + body


def synth_block9(payload):
    """Method 9 is the Huffman region on its own — and it starts at the
    block's LENGTH word, so the region's `left` IS `ulen` and its
    `startbits` is the byte the method word shares with the method. That
    is not how this engine read it until 2026-08-25 (BLOCKERS.md), and the
    module is what said so."""
    sym = bytes(range(256))
    limits = struct.pack(">HH", 0x0100, 0xFFFF)
    bits = payload + b"\0" * ((-len(payload)) % 4)
    bitpos = 8 + len(sym) + len(limits)
    ct_rel = 8 + len(sym) - 10
    region = (struct.pack(">HBBHH", len(payload), 8, 9, bitpos, ct_rel)
              + sym + limits + bits)
    return struct.pack(">H", 2 + len(region)) + region


# ------------------------------------------------------------------- phases

def phase_corpus(unclassic, mods, workdir, verbose=False):
    """Every real block whose method has a module, both ways.

    The reference is what this engine extracts, read back per fork; the
    module decodes the same block and the two are compared byte for byte.
    A run also corrupts one block on purpose: if that still matches, the
    comparison is not comparing anything.
    """
    ok = bad = skipped = 0
    for fixture in CORPUS:
        payload = os.path.join(workdir, "payload")
        shutil.rmtree(payload, ignore_errors=True)
        os.makedirs(payload)
        r = sh(unclassic, "x", "-nr", "-o", payload,
               os.path.join(REPO, "fixtures", fixture))
        if r.returncode != 0:
            raise SystemExit(f"sdmodule: unwrapping {fixture} failed:\n{r.stderr}")
        xs = [f for f in os.listdir(payload)
              if f.lower().endswith(".x")]
        if not xs:
            raise SystemExit(f"sdmodule: no .X payload inside {fixture}")
        container = open(os.path.join(payload, xs[0]), "rb").read()

        full = os.path.join(workdir, "full")
        shutil.rmtree(full, ignore_errors=True)
        os.makedirs(full)
        r = sh(unclassic, "x", "-o", full, os.path.join(REPO, "fixtures", fixture))
        if r.returncode != 0:
            raise SystemExit(f"sdmodule: extracting {fixture} failed:\n{r.stderr}")

        for path, which, flen, blocks in walk(container):
            ref = os.path.join(full, path + (".rsrc" if which == "rsrc" else ""))
            if not os.path.exists(ref):
                continue
            want = open(ref, "rb").read()
            done = 0
            for (p, clen, ulen, meth, stored) in blocks:
                if stored or meth not in mods:
                    skipped += 1
                    done += ulen
                    continue
                name = mods[meth][0]
                got, status = run_module(mods, meth,
                                         container[p + 2:p + clen],
                                         max(ulen, 0x8000),
                                         prefix=want[:done])
                if got is None or got[:ulen] != want[done:done + ulen]:
                    bad += 1
                    print(f"sdmodule: MISMATCH {fixture} {path} {which} "
                          f"block @{p:x} method {meth} ({name}): "
                          f"{'refused: ' + str(status) if got is None else 'bytes differ'}")
                else:
                    ok += 1
                    if verbose:
                        print(f"sdmodule: ok {path} {which} @{p:x} "
                              f"method {meth} {ulen} B")
                done += ulen

            # ...and the same comparison against a block that has been
            # tampered with, which must NOT match. Against the bytes THAT
            # block is responsible for: comparing a later block's output
            # with the fork's first bytes would "fail to match" for a
            # reason that has nothing to do with the tampering.
            at = 0
            for (p, clen, ulen, meth, stored) in blocks:
                if stored or meth not in mods or clen < 40:
                    at += ulen
                    continue
                src = bytearray(container[p + 2:p + clen])
                src[20] ^= 0x01
                got, _status = run_module(mods, meth, bytes(src),
                                          max(ulen, 0x8000),
                                          prefix=want[:at])
                if got is not None and got[:ulen] == want[at:at + ulen]:
                    print("sdmodule: THE COMPARISON CANNOT FAIL — a corrupted "
                          f"block still matched ({fixture} {path} @{p:x})")
                    bad += 1
                break
    print(f"sdmodule: corpus blocks: {ok} byte-exact against the module, "
          f"{bad} wrong, {skipped} skipped (stored, or no module for the method)")
    return bad == 0 and ok > 0


def phase_synth(unclassic, mods, workdir, cases, seed, verbose=False):
    """Blocks this engine builds, through both implementations.

    Every method here is one no archive in reach uses, so there is nothing
    to replay: the block is built from this engine's reading of the format
    and the module is asked whether that reading decodes.
    """
    rnd = random.Random(seed)
    results = {}
    for method in (1, 2, 3, 4, 5, 6, 7, 8, 9):
        want = 1 if method in (1, 5) else (2 if method < 9 else method)
        if want not in mods:
            continue
        name = mods[want][0]
        agree = differ = refused = ourfail = boundary = 0
        for _ in range(cases):
            ulen = rnd.choice([16, 64, 300, 1200, 5000])
            if rnd.random() < 0.5:
                payload = bytes(rnd.getrandbits(8) for _ in range(ulen))
            else:                       # repetitive: the predictor's own case
                alphabet = bytes(rnd.getrandbits(8) for _ in range(rnd.choice([2, 5, 17])))
                payload = bytes(alphabet[rnd.randrange(len(alphabet))]
                                for _ in range(ulen))
            flagbits = [rnd.random() < 0.9 for _ in range(ulen)]
            block = (synth_block9(payload) if method == 9
                     else synth_block(method, payload, flagbits))
            a = ours(unclassic, block, ulen, workdir)
            b, status = run_module(mods, method, block[2:],
                                   max(ulen, 0x8000))
            if a is None:
                ourfail += 1
                continue
            # The boundary check comes first: where the literals are Huffman
            # coded too (4 and 8), landing four bytes out does not decode to
            # something wrong, it runs the module off the end and it dies.
            # Same cause, and counting it as a refusal would hide that.
            if on_the_refill_boundary(method, ulen):
                boundary += 1
                continue
            if b is None:
                refused += 1
                continue
            if a == payload and b[:ulen] == payload:
                agree += 1
            else:
                differ += 1
                if differ <= 2:
                    print(f"sdmodule: method {method} ({name}) DIFFERS at "
                          f"ulen {ulen}: ours {'==' if a == payload else '!='} "
                          f"payload, module "
                          f"{'==' if b[:ulen] == payload else '!='} payload "
                          f"(status {status})")
        results[method] = (agree, differ, refused, ourfail)
        print(f"sdmodule: method {method:2d} ({name}): {agree} agreed, "
              f"{differ} differed, {refused} refused by the module, "
              f"{ourfail} refused by this engine"
              + (f", {boundary} on the refill boundary" if boundary else ""))
    return all(r[1] == 0 and r[0] > 0 for r in results.values()) and bool(results)


def on_the_refill_boundary(method, ulen):
    """The one case where the two references disagree with each other.

    A Huffman region's next neighbour starts at the bit reader's cursor plus
    two, and the cursor moves in 32-bit refills. When the coded flag bitmap
    ends EXACTLY on a refill — the reader's bit budget hits zero and nothing
    asks for more — the 1991 self-extractor this engine follows leaves the
    cursor there and the 1992 module has already fetched the next long, so
    they part company by four bytes over where the literals begin. Measured
    both ways: at ulen 64 (8 flag bytes, 64 bits) this engine reads a block
    with two bytes of slack and the module wants six; at ulen 300 (38 bytes,
    304 bits) they agree.

    **This is reachable only through the harness's own encoder.** The flat
    8-bit code it writes makes the bit length a fixed multiple of the byte
    count; a real block's flags are coded (the 1991 compressor writes a
    ONE-bit code for them), so its bit length is data-dependent and the
    predicate below does not describe it. All 18 real blocks in reach —
    both corpus archives and 18 blocks from Alysis's own compressor,
    including four subjects sized on purpose for this — decode identically
    under both readers.

    So which reading is right where they differ is **open**, and it is not
    known to cost anything. What would settle it is a real block whose coded
    flag bitstream is a multiple of 32 bits, which has to be found by
    MEASURING what the compressor writes rather than by choosing a subject
    size.
    """
    if method not in (2, 4, 6, 8):
        return False
    fsize = ((ulen >> 3) + 4) & ~1
    nflags = min((ulen + 7) >> 3, fsize)
    return nflags % 4 == 0


def phase_specimens(unclassic, mods, workdir, verbose=False):
    """The blocks Alysis's own 1991 control panel wrote, through its own
    1992 module.

    `tools/vmac/sdcompress.py` made these under Mini vMac and they are the
    only SuperDisk! data in reach that a COMPRESSOR produced rather than an
    archive: methods 1 and 6, single-file containers. They live in the
    emulator cache rather than the repository — fixtures are not committed —
    so this phase is skipped when they are not there.
    """
    home = os.environ.get("UNC_VMAC_HOME",
                          os.path.expanduser("~/.cache/unclassic/vmac"))
    root = os.path.join(home, "specimens", "sdcompress")
    paths = sorted(glob.glob(os.path.join(root, "*", "*.x")))
    if not paths:
        print("sdmodule: no sdcompress specimens under "
              f"{root} — skipping (tools/vmac/sdcompress.py makes them)")
        return True
    ok = bad = 0
    for path in paths:
        d = open(path, "rb").read()
        if len(d) < 40:
            continue
        dlen, rlen = struct.unpack(">II", d[4:12])
        nlen = d[30]
        body = 31 + nlen
        if body & 1:
            body += 1
        name = d[31:31 + nlen].decode("mac_roman")
        out = os.path.join(workdir, "spec")
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        if sh(unclassic, "x", "-o", out, path).returncode != 0:
            continue
        p = body
        for want in (dlen, rlen):
            ref = os.path.join(out, name + ("" if want == dlen else ".rsrc"))
            if not want or not os.path.exists(ref):
                continue
            data = open(ref, "rb").read()
            done = 0
            while done < want:
                clen, ulen, meth, stored = block_head(d, p)
                if ulen > want - done:
                    ulen = want - done
                if not stored and meth in (1, 2, 3, 4, 5, 6, 7, 8) or meth in mods:
                    got, status = run_module(mods, meth, d[p + 2:p + clen],
                                             max(ulen, 0x8000),
                                             prefix=data[:done])
                    if got is None or got[:ulen] != data[done:done + ulen]:
                        bad += 1
                        print(f"sdmodule: MISMATCH {os.path.basename(path)} "
                              f"block @{p:x} method {meth}: "
                              f"{status if got is None else 'bytes differ'}")
                    else:
                        ok += 1
                done += ulen
                p += clen
    print(f"sdmodule: compressor specimens: {ok} byte-exact against the "
          f"module, {bad} wrong")
    return bad == 0


def encode_method10(rnd, nitems):
    """A method 10 stream, and the bytes it must decode to.

    Written from this engine's reading — which is exactly why the module
    grades it: a decoder that agrees only with its own encoder agrees with
    nothing. The first run of this pair disagreed with Alysis's module on
    every match, because the length was read as 2*(nibble+1) where the
    reference copies nibble+2 (the DBF's target is the second MOVEB, not
    the pair).
    """
    out = bytearray()
    items = []
    for _ in range(8):                       # something to point back at
        b = rnd.randrange(256)
        items.append((True, bytes([b])))
        out.append(b)
    for _ in range(nitems):
        if len(out) < 4 or rnd.random() < 0.45:
            b = rnd.randrange(256)
            items.append((True, bytes([b])))
            out.append(b)
            continue
        nib = rnd.randrange(0, 16)
        n = nib + 2
        back = rnd.randrange(1, min(len(out), 60000) + 1)
        off = back + 1                       # the reference reads out-off+1
        if off < 2 or off > 0xFFFF:
            continue
        wide = off >= 0xF00 or rnd.random() < 0.25
        if wide:                             # the escape: marker nibble 0xF
            payload = bytes([(nib << 4) | 0x0F, (off >> 8) & 0xFF, off & 0xFF])
        else:
            payload = bytes([(nib << 4) | ((off >> 8) & 0x0F), off & 0xFF])
        src = len(out) - back
        for i in range(n):
            out.append(out[src + i])
        items.append((False, payload))
    items.append((False, b"\x00\x00"))      # offset zero ends the block
    body = bytearray()
    i = 0
    while i < len(items):
        chunk = items[i:i + 32]
        ctrl = 0
        for j, (lit, _) in enumerate(chunk):
            if lit:
                ctrl |= 1 << (31 - j)
        body += struct.pack(">I", ctrl)
        for _, payload in chunk:
            body += payload
        i += 32
    return bytes(body), bytes(out)


def phase_method10(unclassic, mods, workdir, cases, seed, verbose=False):
    """Method 10, three ways: the bytes, this engine, and Alysis's module.

    Nothing in reach writes a method 10 block — both corpus archives use 7
    and 11, and the 1991 control panel writes 1 or 6 — so the stream is
    built here and the module is what says the reading is right. Every case
    has to come out equal three ways.

    What it cannot see: one block per case, so the history carried BETWEEN
    blocks is exercised only by the shape of the code it shares with
    SlowFastB; and a real compressor's choice of matches is not modelled,
    only the format's grammar.
    """
    if 10 not in mods:
        print("sdmodule: no method 10 module — skipping")
        return True
    rnd = random.Random(seed)
    agree = bad = 0
    for _ in range(cases):
        body, want = encode_method10(rnd, rnd.choice([40, 150, 400]))
        block = struct.pack(">HHH", 6 + len(body), len(want), 10) + body
        a = ours(unclassic, block, len(want), workdir)
        b, status = run_module(mods, 10, block[2:], max(len(want), 0x8000))
        oka = a == want
        okb = b is not None and b[:len(want)] == want
        if oka and okb:
            agree += 1
        else:
            bad += 1
            if bad <= 2:
                print(f"sdmodule: method 10 DISAGREES at ulen {len(want)}: "
                      f"this engine {'==' if oka else '!='} the bytes, module "
                      f"{'==' if okb else '!='} them (status {status})")
    print(f"sdmodule: method 10 (SlowFastA): {agree} case(s) equal three ways, "
          f"{bad} wrong")
    return bad == 0 and agree > 0


def phase_tennessee(unclassic, mods, workdir, verbose=False):
    """What method 20 turns out to be, and five blocks it writes for free.

    Module 20 ("Tennessee") answers `badCommandError` to the decompress
    command and compresses on command 2 — and what it emits is a block
    whose own header declares **method 11**. So method 20 is a codec ID
    for an ENCODER, not a block method: there is no method 20 bitstream
    to implement, and a block that did carry 20 could not be decoded by
    Alysis's own expander either, whose dispatcher would hand it to this
    module (INIT 32 @0x50c8) and be refused.

    The useful consequence is that it writes SlowFastB blocks on demand,
    which is a compressor for method 11 that nothing else here has: the
    corpus's method 11 blocks are four, and these are as many as anybody
    wants. Each is decoded by this engine and required to come back equal
    to what went in.

    Inputs it declines with `inadequateCompressionError` (-2) — random
    bytes, or anything too short to pay for itself — are not failures.
    """
    if 20 not in mods:
        print("sdmodule: no method 20 module — skipping")
        return True
    rnd = random.Random(3)
    cases = [
        ("zeros", b"\x00" * 4096),
        ("text", b"the quick brown fox. " * 300),
        ("counting", bytes(range(256)) * 16),
        ("runs", b"".join(bytes([rnd.randrange(256)]) * rnd.randrange(1, 40)
                          for _ in range(300))),
        ("big", (b"SuperDisk method 20 probe. " * 1200)[:30000]),
    ]
    ok = bad = declined = 0
    for name, data in cases:
        out, status = run_module(mods, 20, data, len(data), selector=2)
        if out is None or len(out) < 4:
            if status == -2:
                declined += 1
                continue
            bad += 1
            print(f"sdmodule: Tennessee failed on {name}: {status}")
            continue
        ulen, method = struct.unpack(">HH", out[:4])
        block = struct.pack(">H", 2 + len(out)) + out
        back = ours(unclassic, block, ulen, workdir)
        if method != 11:
            bad += 1
            print(f"sdmodule: Tennessee wrote method {method} for {name}, "
                  f"not 11 — method 20 may be a block method after all")
        elif back != data:
            bad += 1
            print(f"sdmodule: this engine does not read back Tennessee's "
                  f"{name} block ({len(data)} B in)")
        else:
            ok += 1
            if verbose:
                print(f"sdmodule: Tennessee {name}: {len(data)} -> "
                      f"{len(out)} B, method 11, byte-exact")
    print(f"sdmodule: method 20 (Tennessee) is an ENCODER: {ok} block(s) it "
          f"wrote declare method 11 and decode byte-exact here, "
          f"{declined} input(s) it declined as incompressible, {bad} wrong")
    return bad == 0 and ok > 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--unclassic", default=os.path.join(REPO, "build", "unclassic"))
    ap.add_argument("--cases", type=int, default=12,
                    help="synthetic blocks per method (default 12)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--list", action="store_true",
                    help="list the modules found and stop")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if not shutil.which("qemu-m68k") or not shutil.which("m68k-linux-gnu-gcc"):
        print("sdmodule: needs qemu-m68k and the m68k cross-compiler — skipping")
        return 0
    if not os.path.exists(os.path.join(REPO, "fixtures", MODULE_FIXTURE)):
        print(f"sdmodule: no fixtures/{MODULE_FIXTURE} — skipping")
        return 0
    build_runner()

    workdir = tempfile.mkdtemp(prefix="sdmodule-")
    try:
        mods = modules(args.unclassic, workdir)
        print("sdmodule: modules in the corpus: "
              + ", ".join(f"{m} ({mods[m][0]}, {len(mods[m][1])} B)"
                          for m in sorted(mods)))
        if args.list:
            return 0
        a = phase_corpus(args.unclassic, mods, workdir, args.verbose)
        b = phase_specimens(args.unclassic, mods, workdir, args.verbose)
        c = phase_synth(args.unclassic, mods, workdir, args.cases, args.seed,
                        args.verbose)
        e = phase_method10(args.unclassic, mods, workdir, args.cases,
                           args.seed, args.verbose)
        f = phase_tennessee(args.unclassic, mods, workdir, args.verbose)
        return 0 if (a and b and c and e and f) else 1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
