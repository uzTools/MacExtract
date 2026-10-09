#!/usr/bin/env python3
"""Recover the key of an encrypted classic-StuffIt archive from its 'MKey'.

Every encrypted StuffIt classic archive carries an eight-byte `'MKey'`
resource in its resource fork that VERIFIES a password: the reader decrypts
the MKey under the password-derived ARCHIVE KEY to an IV, then checks that
encrypting the IV's first four bytes (with a trailing 00 00 00 04) reproduces
its last four (`unc_crypt_sit`, `src/unc_crypt.c`; FORMATS.md, *Encryption*).

That check is an ORACLE, and it is independent of the fork cipher — the three
schemes (built-in feedback, `DES`, `NewDE`) share the archive key and the MKey
verifier and differ only in the fork transform. So the MKey alone decides
whether a candidate password, OR a raw eight-byte archive key, is the one.

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
                        decrypt time, so the dump must be taken while the
                        installer is extracting — a dump from its splash or its
                        destination dialog does NOT contain it
                        (DECISIONS.md 2026-10-09, *the key is folded at decrypt
                        time, not at launch*). The C translation in that entry
                        is the one to use on a multi-megabyte dump; this scan is
                        for small blobs.

The MKey is given with `--mkey HEX16`; `tools/sit_mkey_oracle.py --mkey ... x`
reads it off an archive's resource fork with `macextract`'s own loader if you
prefer, but the eight bytes are easiest lifted straight from the fork.

Run with no arguments for the self-test, which builds an MKey for a known
password with `tools/synth_crypt.py` and recovers it three ways.
"""
import argparse
import os
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


def scan(blob, mkey):
    """Every offset in `blob` whose next 8 bytes are the archive key."""
    hits = []
    for i in range(len(blob) - 7):
        if verify_archive_key(blob[i:i + 8], mkey):
            hits.append((i, blob[i:i + 8]))
    return hits


def _selftest():
    pw = b"swordfish"
    mkey, ak, _iv = sit_mkey_and_iv(pw)
    assert verify_password(pw, mkey), "password check failed"
    assert not verify_password(b"wrong", mkey), "false positive on bad password"
    assert verify_archive_key(ak, mkey), "archive-key check failed"
    blob = b"....." + ak + b"garbage"
    hits = scan(blob, mkey)
    assert hits and hits[0][0] == 5, f"scan failed: {hits}"
    print("self-test OK: password, archive key and scan all recover",
          f"mkey={mkey.hex()}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mkey", help="archive 'MKey' resource, 16 hex chars")
    ap.add_argument("--pw", help="password string to test")
    ap.add_argument("--ak", help="raw 8-byte archive key, 16 hex chars")
    ap.add_argument("--scan", help="file to slide an 8-byte window over")
    args = ap.parse_args()

    if not (args.pw or args.ak or args.scan):
        _selftest()
        return

    if not args.mkey:
        sys.exit("--mkey is required with --pw/--ak/--scan")
    mkey = bytes.fromhex(args.mkey)
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
    main()
