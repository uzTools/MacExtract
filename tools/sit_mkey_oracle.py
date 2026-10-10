#!/usr/bin/env python3
"""Recover the key of an encrypted classic-StuffIt archive from its 'MKey'.

Every encrypted StuffIt classic archive carries an eight-byte `'MKey'`
resource in its resource fork that VERIFIES a password: the reader decrypts
the MKey under the password-derived ARCHIVE KEY to an IV, then checks that
encrypting the IV's first four bytes (with a trailing 00 00 00 04) reproduces
its last four. Source: `unc_crypt_sit` in `src/unc_crypt.c`, which cites
XADStuffItDESHandle.m keyForPasswordData:entryKey:MKey: and FIPS 46-3, and
is graded on every `ci.sh` run against the three archives StuffIt Deluxe
3.5.1 wrote (`tools/run_crypt.py`); FORMATS.md, *Encryption*.

That check is an ORACLE: the MKey alone decides whether a candidate
password, OR a raw eight-byte archive key, is the one, before any fork is
read. Whether every scheme that names the MKey uses it this way is NOT
established here — the 3.5.1 built-in scheme is what the self-test grades.

Two ways in:

  * `--pw STRING`     — test a password string.
  * `--ak HEX16`      — test a raw 8-byte archive key (the value the writer
                        folds the password into; `0123456789abcdef` xored and
                        StuffItDES-encrypted once per 8 password bytes).
  * `--scan FILE`     — slide an 8-byte window over FILE and report every
                        offset whose bytes verify as the archive key. This is
                        how to read the key off a memory image of a running
                        self-installing archive (InstallerMaker writes one that
                        installs WITHOUT prompting, so the key is a constant in
                        its code): the archive key is computed lazily, at
                        decrypt time, a HYPOTHESIS: 45 dumps from its splash,
                        licence and destination dialog did not contain it
                        (DECISIONS.md 2026-10-09, *the key is folded at decrypt
                        time, not at launch*). In Python this is ~1 ms a
                        window, so a multi-megabyte dump wants a compiled
                        scanner, which is not in the repository.

The MKey is given with `--mkey HEX16`, or read off an archive with
`--from FILE`: a MacBinary file or a bare resource fork, walked to its
`'MKey'` resource (Inside Macintosh: More Macintosh Toolbox, "Resource File
Format" — the layout `unc_resfork_find` in `src/unc_crypt.c` reads).

Run with no arguments for the self-test. It grades `verify_*` against the
three archives StuffIt Deluxe 3.5.1 wrote under Mini vMac
(`tools/vmac/sitcrypt.py`; the specimen cache), whose MKeys came from
Aladdin's DES and not from this project's: the right password must verify,
a password one character off must not, the archive key must verify and one
bit off it must not, and a scan must find it in a blob and find nothing in
a blob without it. Without the specimens it says so and grades only the
synthetic round trip, which shares this project's DES and so cannot catch
a fault in it.
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synth_crypt import (sit_archive_key, sitdes_setkey, sitdes_crypt,  # noqa
                         sit_mkey_and_iv)


def verify_archive_key(ak, mkey):
    """True iff the 8-byte archive key `ak` opens the archive whose verifier
    resource is `mkey`. This is the whole of the password check, with the
    password already folded in."""
    ks = sitdes_setkey(ak)
    iv = sitdes_crypt(mkey, ks, False)
    vb = sitdes_crypt(iv[:4] + b"\x00\x00\x00\x04", ks, True)
    return vb[4:] == iv[4:]


def verify_password(pw, mkey):
    return verify_archive_key(sit_archive_key(pw), mkey)


def mkey_from(path):
    """The 8-byte 'MKey' out of a MacBinary file or a bare resource fork.
    Source: Inside Macintosh: More Macintosh Toolbox, "Resource File Format"
    (header: data and map offsets; map +24: type-list offset; type entry:
    type, count-1, reference-list offset; reference: id, name offset,
    attributes + 24-bit data offset), the layout `unc_resfork_find` reads;
    MacBinary II for the fork lengths at 83 and 87."""
    d = open(path, "rb").read()
    fork = d
    if len(d) >= 128 and d[0] == 0 and 1 <= d[1] <= 63:
        dlen, rlen = struct.unpack(">II", d[83:91])
        at = 128 + ((dlen + 127) & ~127)
        fork = d[at:at + rlen]
    doff, moff = struct.unpack(">II", fork[0:8])
    tl = moff + struct.unpack(">H", fork[moff + 24:moff + 26])[0]
    ntypes = struct.unpack(">H", fork[tl:tl + 2])[0] + 1
    for t in range(ntypes):
        e = tl + 2 + 8 * t
        rtype, n1, rl = struct.unpack(">4sHH", fork[e:e + 8])
        if rtype == b"MKey":
            ref = tl + rl
            off = int.from_bytes(fork[ref + 5:ref + 8], "big")
            ln = struct.unpack(">I", fork[doff + off:doff + off + 4])[0]
            if ln != 8:
                raise ValueError("'MKey' is %d bytes, not 8" % ln)
            return fork[doff + off + 4:doff + off + 12]
    raise ValueError("no 'MKey' resource in %s" % path)


def scan(blob, mkey):
    """Every offset in `blob` whose next 8 bytes are the archive key."""
    hits = []
    for i in range(len(blob) - 7):
        if verify_archive_key(blob[i:i + 8], mkey):
            hits.append((i, blob[i:i + 8]))
    return hits


SPECIMENS = os.path.join(os.environ.get(
    "UNC_VMAC_HOME", os.path.expanduser("~/.cache/macextract/vmac")),
    "specimens", "sitcrypt")


def _grade(label, pw, mkey, bad):
    """The five checks, on one (password, MKey) pair."""
    ak = sit_archive_key(pw)
    near = pw[:-1] + bytes([pw[-1] ^ 1])
    wrongak = bytes([ak[0] ^ 1]) + ak[1:]
    for ok, what in ((verify_password(pw, mkey), "the password verifies"),
                     (not verify_password(near, mkey),
                      "a password one character off does not"),
                     (verify_archive_key(ak, mkey), "the archive key verifies"),
                     (not verify_archive_key(wrongak, mkey),
                      "the archive key one bit off does not"),
                     ([h[0] for h in scan(b"....." + ak + b"garbage", mkey)]
                      == [5], "a scan finds it at its offset"),
                     (scan(b"....." + wrongak + b"garbage" * 4, mkey) == [],
                      "a scan of a blob without it finds nothing")):
        if not ok:
            bad.append("%s: %s — FAILED" % (label, what))


def _selftest():
    bad = []
    real = 0
    for tag in sorted(os.listdir(SPECIMENS)) if os.path.isdir(SPECIMENS) else []:
        meta = os.path.join(SPECIMENS, tag, "made.json")
        arch = os.path.join(SPECIMENS, tag, "Secret.sit.bin")
        if not (os.path.exists(meta) and os.path.exists(arch)):
            continue
        pw = json.load(open(meta))["password"].encode("mac_roman")
        _grade("StuffIt Deluxe 3.5.1, %s" % tag, pw, mkey_from(arch), bad)
        real += 1
    pw = b"swordfish"
    mkey, _ak, _iv = sit_mkey_and_iv(pw)
    _grade("synthetic", pw, mkey, bad)
    for b in bad:
        print("sit_mkey_oracle: " + b)
    if bad:
        return 1
    if real:
        print("self-test OK: %d archive(s) StuffIt Deluxe 3.5.1 wrote, and "
              "the synthetic round trip — six checks each, three of them "
              "negative" % real)
    else:
        print("self-test OK on the synthetic round trip ONLY: no StuffIt "
              "Deluxe specimens in %s, and the synthetic MKey shares this "
              "project's DES, so a fault in it cannot show" % SPECIMENS)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mkey", help="archive 'MKey' resource, 16 hex chars")
    ap.add_argument("--from", dest="src", metavar="FILE",
                    help="read the MKey off a MacBinary file or resource fork")
    ap.add_argument("--pw", help="password string to test")
    ap.add_argument("--ak", help="raw 8-byte archive key, 16 hex chars")
    ap.add_argument("--scan", help="file to slide an 8-byte window over")
    args = ap.parse_args()

    if not (args.pw or args.ak or args.scan):
        return _selftest()

    if args.src:
        mkey = mkey_from(args.src)
        print("MKey", mkey.hex())
    elif args.mkey:
        mkey = bytes.fromhex(args.mkey)
    else:
        sys.exit("--mkey or --from is required with --pw/--ak/--scan")
    if len(mkey) != 8:
        sys.exit("--mkey must be 16 hex chars (8 bytes)")

    if args.pw is not None:
        ok = verify_password(args.pw.encode("mac_roman"), mkey)
        print("MATCH" if ok else "no", repr(args.pw))
    if args.ak is not None:
        ak = bytes.fromhex(args.ak)
        print("MATCH" if verify_archive_key(ak, mkey) else "no", ak.hex())
    if args.scan is not None:
        blob = open(args.scan, "rb").read()
        for off, k in scan(blob, mkey):
            print(f"AKEY off={off} {k.hex()}")


if __name__ == "__main__":
    sys.exit(main())
