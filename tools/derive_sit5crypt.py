#!/usr/bin/env python3
"""derive_sit5crypt.py — grade StuffIt 5's encrypted-archive header
against the archives Aladdin's own software wrote.

`src/fmt_sit5.c` cited `XADStuffIt5Parser.m` for two things, and said
of the first that it *"has no specimen either — all 31 corpus archives
read 0x10 here and none is encrypted, so the only archives that
exercise it are the ones tools/run_crypt.py synthesises, which cannot
grade it."*  That was false.  Three encrypted StuffIt 5 archives
written by **DropStuff 5.0.1** under Mac OS 9.2 have been in the cache
since 2026-08-26 (FORMATS.md, *StuffIt 5's RC4*), and they exercise it.

What this checks, with no engine and no reference involved — just the
bytes Aladdin wrote and the hashlib in the standard library:

  * **the flag byte's bit 7** means encrypted: all three set it;
  * **bit 4 moves the password hash by 14 bytes**: with the shift the
    length byte at the computed offset reads 5, the key length; at the
    unshifted offset it reads 13, which is not;
  * **the hash is MD5(MD5(password)[:5])[:5]**, at password lengths of
    4, 9 and 17.

What it CANNOT see: **bit 5**, which none of the three sets.  That
part of the reading is still XADStuffIt5Parser.m's and still has no
specimen — an archive carrying a comment would be one.

    tools/derive_sit5crypt.py [-v]

Not in `ci.sh`: the specimens live in the cache, not the repository.
It skips cleanly without them.
"""

import hashlib
import os
import sys

CACHE = os.environ.get("UNC_SIT5_HOME",
                       os.path.expanduser("~/.cache/macextract/sit5"))
SPECIMENS = os.path.join(CACHE, "specimens")

# FORMATS.md, *StuffIt 5's RC4* — the passwords DropStuff was given.
CASES = [("enc-pass.sit", "pass"),
         ("enc-swordfish.sit", "swordfish"),
         ("enc-twofork.sit", "abcdefghijklmnopq")]

KEYLEN = 5
ARCH_CRYPTED = 0x80
ARCH_14BYTES = 0x10
ARCH_20 = 0x20
BASE = 100


def main():
    verbose = "-v" in sys.argv
    if not os.path.isdir(SPECIMENS):
        print("derive-sit5crypt: no specimens in %s — skipped" % SPECIMENS)
        return 0

    ok = 0
    bad = []
    saw_bit5 = False

    for fn, pw in CASES:
        p = os.path.join(SPECIMENS, fn)
        if not os.path.exists(p):
            continue
        b = open(p, "rb").read()
        flags = b[83]

        if not (flags & ARCH_CRYPTED):
            bad.append("%s: bit 7 clear, but DropStuff was given a password"
                       % fn)
            continue

        at = BASE + (14 if flags & ARCH_14BYTES else 0) \
                  + (4 if flags & ARCH_20 else 0)
        if flags & ARCH_20:
            saw_bit5 = True

        if b[at] != KEYLEN:
            bad.append("%s: length byte at %d is %d, want %d"
                       % (fn, at, b[at], KEYLEN))
            continue

        stored = b[at + 1:at + 1 + KEYLEN]
        want = hashlib.md5(hashlib.md5(pw.encode()).digest()[:KEYLEN]
                           ).digest()[:KEYLEN]
        if stored != want:
            bad.append("%s: hash %s, but MD5(MD5(pw)[:5])[:5] is %s"
                       % (fn, stored.hex(), want.hex()))
            continue

        # The shift has to matter, or "bit 4 adds 14" is unfalsifiable
        # here the way the block size was for DiskDoubler method 8.
        if flags & ARCH_14BYTES and b[BASE] == KEYLEN:
            bad.append("%s: the unshifted offset ALSO reads a length of %d, "
                       "so this specimen cannot grade the 14-byte shift"
                       % (fn, KEYLEN))
            continue

        ok += 1
        if verbose:
            print("  %-18s pw %2d chars  flags 0x%02x  hash at %d  %s"
                  % (fn, len(pw), flags, at, stored.hex()))

    if not ok and not bad:
        print("derive-sit5crypt: no specimens matched — skipped")
        return 0

    print("derive-sit5crypt: %d of %d archive(s) DropStuff 5.0.1 wrote"
          % (ok, len(CASES)))
    if bad:
        for b_ in bad:
            print("derive-sit5crypt: FAIL: " + b_)
        return 1

    print("            bit 7 = encrypted, bit 4 = the hash sits 14 bytes "
          "later, and the hash is MD5(MD5(password)[:5])[:5] — measured at "
          "4, 9 and 17 characters, against Aladdin's own output.")
    print("            NOT graded: bit 5, which none of the three sets. "
          "That reading is still XADStuffIt5Parser.m's; an archive with a "
          "comment would be the specimen."
          if not saw_bit5 else
          "            bit 5 seen — update this tool, it is now gradeable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
