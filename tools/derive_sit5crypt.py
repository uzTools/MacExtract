#!/usr/bin/env python3
"""derive_sit5crypt.py — grade StuffIt 5's archive flag byte against the
archives Aladdin's own software wrote.

`src/fmt_sit5.c` reads header byte 83 as a set of optional blocks, and
every part of that reading is checked here with no engine and no
reference in the loop — just the bytes Aladdin wrote and the hashlib in
the standard library:

  * **bit 7** means encrypted: three DropStuff 5.0.1 archives set it;
  * **bit 4** adds a 14-byte block, so the password hash sits 14 bytes
    later — load-bearing, because at the unshifted offset the length
    byte reads 13 and not the key length;
  * **the hash is MD5(MD5(password)[:5])[:5]**, at 4, 9 and 17
    characters;
  * **bit 5 marks an archive COMMENT** and adds a four-byte block of two
    lengths, the comment's and its style scrap's. The archive that says
    so is the `Sample Archive.sit` StuffIt Deluxe 5.5 ships inside its
    own installer, where 100 + 14 + 4 + 204 + 22 is exactly the offset
    its header gives for the first entry — and a block of 0, 2, 6 or 8
    bytes is checked separately and must NOT close the same sum;
  * **the hash comes after that block**, graded on the two archives
    StuffIt Deluxe 7.0.3 wrote by Apple event on Mac OS 9.2
    (`tools/vmac/sitcomment.py --specimen`), which are the only ones here
    that set bits 5 and 7 together. The check that makes it mean
    anything is the one on the UNSHIFTED offset, which reads 0;
  * **the key is MD5(password)[:5]**, then the fork's own five bytes,
    with `--macextract BIN`: every fork of the four single-entry
    archives is decrypted by THIS file's RC4 under the rule and handed to
    the engine re-encrypted under its own key, so its cipher cancels and
    it is only the Arsenic decoder and the CRC check. Aladdin's CRC must
    verify under the rule and under none of four others (`check_key`).

    tools/derive_sit5crypt.py [-v] [--macextract build/rel/macextract]

Not in `ci.sh`: the specimens live in the cache, not the repository
(fixtures/SOURCES.md's rule about copyrighted archives). It skips cleanly
without them. What it cannot see: the key on an archive of more than one
entry, whose fork offsets this file does not walk. FORMATS.md, *StuffIt 5's RC4* and *StuffIt 5's archive flag
byte, and what bit 5 is*, hold the numbers.
"""

import hashlib
import os
import subprocess
import sys

CACHE = os.environ.get("UNC_SIT5_HOME",
                       os.path.expanduser("~/.cache/macextract/sit5"))
SPECIMENS = os.path.join(CACHE, "specimens")

# FORMATS.md, *StuffIt 5's RC4* — the passwords DropStuff was given, and
# (the last two) the two archives StuffIt Deluxe 7.0.3 wrote by Apple
# event, which are the only ones here that set bits 5 and 7 together.
CASES = [("enc-pass.sit", "pass"),
         ("enc-swordfish.sit", "swordfish"),
         ("enc-twofork.sit", "abcdefghijklmnopq"),
         ("enc-comment-added.sit", "swordfish"),
         ("enc-comment-stuffed.sit", "swordfish")]

KEYLEN = 5
ARCH_CRYPTED = 0x80
ARCH_14BYTES = 0x10
ARCH_20 = 0x20
BASE = 100


# The archive StuffIt Deluxe 5.5 ships in its own `Tutorial Files`, which
# is the only one on this machine that sets bit 5. Lifted out of the
# installer payload by `tools/vmac/sitzip.py --payload 55`.
COMMENTED = "comment-sample.sit"
ARCH_14LEN = 14
ARCH_20LEN = 4
STYLE_ELEM = 20                 # ScrpSTElement; Inside Macintosh — Text


def check_comment(verbose):
    """Grade bit 5 against an archive that sets it.

    The reading under test is `fmt_sit5.c`'s: bit 5 introduces a FOUR-byte
    block, so the password hash in an encrypted archive sits four bytes
    later. The block is a comment's two lengths, and the comment itself
    follows every other optional block.

    The check is arithmetic and it closes or it does not: the header's own
    `firstoffs` says where the first entry starts, and 100 + 14 + 4 +
    commentsize + stylesize has to land exactly there. A block of any
    other size misses, which is what makes this falsifiable — the same
    thing the 14-byte shift is checked for above."""
    p = os.path.join(SPECIMENS, COMMENTED)
    if not os.path.exists(p):
        print("derive-sit5crypt: no %s — sitzip.py --payload 55 lifts it "
              "out of StuffIt Deluxe 5.5's Tutorial Files" % COMMENTED)
        return 0, []
    b = open(p, "rb").read()
    flags = b[83]
    bad = []
    if not flags & ARCH_20:
        return 0, ["%s: bit 5 clear — this is not the commented archive"
                   % COMMENTED]

    firstoffs = int.from_bytes(b[94:98], "big")
    at = BASE + (ARCH_14LEN if flags & ARCH_14BYTES else 0)
    csize = int.from_bytes(b[at:at + 2], "big")
    ssize = int.from_bytes(b[at + 2:at + 4], "big")
    text = at + ARCH_20LEN
    end = text + csize + ssize

    if end != firstoffs:
        bad.append("%s: 100 + %d + %d + %d + %d = %d, but the first entry "
                   "is at %d" % (COMMENTED, at - BASE, ARCH_20LEN, csize,
                                 ssize, end, firstoffs))
    # The alternative readings this specimen rules out, stated so that a
    # pass cannot be a coincidence: no block at all, and a block of any
    # other plausible width.
    for width in (0, 2, 6, 8):
        if text - ARCH_20LEN + width + csize + ssize == firstoffs:
            bad.append("%s: a %d-byte block would close the arithmetic too, "
                       "so this specimen does not grade the width"
                       % (COMMENTED, width))
    # length_b is a TextEdit style scrap: a count and that many
    # 20-byte elements. Source: Inside Macintosh — Text, TEStyleScrap.
    nelem = int.from_bytes(b[text + csize:text + csize + 2], "big")
    if ssize != 2 + nelem * STYLE_ELEM:
        bad.append("%s: the second length is %d, which is not 2 + %d x %d"
                   % (COMMENTED, ssize, nelem, STYLE_ELEM))
    comment = b[text:text + csize]
    if not comment or any(c < 9 for c in comment):
        bad.append("%s: the %d bytes at %d do not read as text"
                   % (COMMENTED, csize, text))
    if verbose and not bad:
        print("  %-18s flags 0x%02x  comment %d B at %d, style %d B "
              "(%d run), first entry %d"
              % (COMMENTED, flags, csize, text, ssize, nelem, firstoffs))
        print("     %s" % comment.decode("mac_roman")[:70])
    return (0 if bad else 1), bad


def check_order(verbose):
    """Grade the ORDER of the password hash and the comment block.

    This is the last thing `fmt_sit5.c` took from XADStuffIt5Parser.m
    without a specimen: inside the encrypted branch it adds bit 4's
    fourteen bytes AND bit 5's four before reading the hash, so a
    commented encrypted archive puts the hash four bytes further along
    than an uncommented one. Only an archive that sets both bits can say,
    and the check that makes it mean something is the one that reads the
    UNSHIFTED offset and requires it NOT to look like a hash."""
    ok, bad = 0, []
    for fn, pw in CASES:
        p = os.path.join(SPECIMENS, fn)
        if not os.path.exists(p):
            continue
        b = open(p, "rb").read()
        flags = b[83]
        if (flags & (ARCH_20 | ARCH_CRYPTED)) != (ARCH_20 | ARCH_CRYPTED):
            continue
        shifted = BASE + (ARCH_14LEN if flags & ARCH_14BYTES else 0) \
                       + ARCH_20LEN
        unshifted = shifted - ARCH_20LEN
        if b[shifted] != KEYLEN:
            bad.append("%s: with the comment block counted, the length byte "
                       "at %d is %d, not %d" % (fn, shifted, b[shifted],
                                                KEYLEN))
            continue
        if b[unshifted] == KEYLEN:
            bad.append("%s: the offset WITHOUT the comment block also reads "
                       "%d, so this archive cannot grade the order"
                       % (fn, KEYLEN))
            continue
        want = hashlib.md5(hashlib.md5(pw.encode()).digest()[:KEYLEN]
                           ).digest()[:KEYLEN]
        if b[shifted + 1:shifted + 1 + KEYLEN] != want:
            bad.append("%s: the hash at %d is not MD5(MD5(pw)[:5])[:5]"
                       % (fn, shifted))
            continue
        # And the comment still has to land where the header says.
        csize = int.from_bytes(b[unshifted:unshifted + 2], "big")
        ssize = int.from_bytes(b[unshifted + 2:unshifted + 4], "big")
        end = shifted + 1 + KEYLEN + csize + ssize
        firstoffs = int.from_bytes(b[94:98], "big")
        if end != firstoffs:
            bad.append("%s: hash, then %d + %d of comment, ends at %d, but "
                       "the first entry is at %d"
                       % (fn, csize, ssize, end, firstoffs))
            continue
        ok += 1
        if verbose:
            print("  %-24s flags 0x%02x  hash at %d (%d reads %d), comment "
                  "%d B at %d, first entry %d"
                  % (fn, flags, shifted, unshifted, b[unshifted], csize,
                     shifted + 1 + KEYLEN, firstoffs))
    return ok, bad


# The KEY, as opposed to the hash: the archive key is MD5(password)[:5]
# and each fork is RC4 under that key followed by the fork's own five
# bytes. The hash above only proves that MD5(MD5(pw)[:5])[:5] is stored;
# this proves the first MD5's five bytes are what Aladdin keyed RC4 with.
# Only the single-entry archives, whose forks run to the archive's end.
KEY_CASES = CASES[:4]

# Rules that must NOT decode, or the check cannot fail: the other ten
# bytes of the digest, the password itself, and the password upper-cased
# (ARC's habit).
def _md5(pw):
    return hashlib.md5(pw).digest()


KEY_RULES = [("MD5(pw)[:5]", lambda pw: _md5(pw)[:5], True),
             ("MD5(pw)[5:10]", lambda pw: _md5(pw)[5:10], False),
             ("MD5(pw)[11:16]", lambda pw: _md5(pw)[11:16], False),
             ("pw[:5]", lambda pw: (pw * 5)[:5], False),
             ("MD5(PW)[:5]", lambda pw: _md5(pw.upper())[:5], False)]


def _rc4(key, data):
    """RC4, draft-kaukonen-cipher-arcfour-03 section 3."""
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xFF
        s[i], s[j] = s[j], s[i]
    out = bytearray(data)
    i = j = 0
    for n in range(len(out)):
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        out[n] ^= s[(s[i] + s[j]) & 0xFF]
    return bytes(out)


def _forks(b):
    """[(offset, length, forkkey)] of the encrypted forks of a
    single-entry archive. The layout is fmt_sit5.c's: rsrc fork, then
    data fork, right after the entry's second block."""
    p = int.from_bytes(b[94:98], "big")
    hs = int.from_bytes(b[p + 6:p + 8], "big")
    dcomp = int.from_bytes(b[p + 38:p + 42], "big")
    if b[p + 47] != KEYLEN:
        return None
    dkey = b[p + 48:p + 48 + KEYLEN]
    q = p + hs
    flags2 = int.from_bytes(b[q:q + 2], "big")
    q += 14 + (22 if b[p + 4] == 1 else 18)
    out = []
    if flags2 & 1:
        rcomp = int.from_bytes(b[q + 4:q + 8], "big")
        if b[q + 13] != KEYLEN:
            return None
        rkey = b[q + 14:q + 14 + KEYLEN]
        q += 14 + KEYLEN
        out.append((q, rcomp, rkey))
        q += rcomp
    out.append((q, dcomp, dkey))
    if q + dcomp != len(b):
        return None
    return out


def check_key(macextract, verbose):
    """Grade the archive key against the CRC Aladdin wrote.

    For each rule, every encrypted fork is decrypted under RC4(rule(pw) +
    the fork's five bytes) — this script's RC4, not the engine's — and
    then re-encrypted under the key the engine derives, so the engine's
    own cipher cancels and what reaches its Arsenic decoder and CRC check
    is exactly what the RULE decrypted. The engine is the decompressor
    and nothing else. Exit 0 from `t` means every fork's CRC-16, which
    DropStuff computed over the bytes it was given, verified. The stated
    rule has to pass on every archive and every other rule has to fail
    on every archive."""
    ok, bad = 0, []
    tmp = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), ".tmp", "sit5key")
    os.makedirs(tmp, exist_ok=True)
    engine_key = KEY_RULES[0][1]
    for fn, pw in KEY_CASES:
        p = os.path.join(SPECIMENS, fn)
        if not os.path.exists(p):
            continue
        b = open(p, "rb").read()
        forks = _forks(b)
        if not forks:
            bad.append("%s: not a single-entry archive whose forks end it" % fn)
            continue
        pwb = pw.encode()
        for name, rule, want in KEY_RULES:
            nb = bytearray(b)
            for off, n, fk in forks:
                plain = _rc4(rule(pwb) + fk, b[off:off + n])
                nb[off:off + n] = _rc4(engine_key(pwb) + fk, plain)
            t = os.path.join(tmp, fn)
            open(t, "wb").write(bytes(nb))
            r = subprocess.run([macextract, "t", "-p", pw, t],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
            got = r.returncode == 0
            if got != want:
                bad.append("%s: key %s %s" % (fn, name,
                           "decodes, but must not" if got else
                           "does not decode"))
            elif verbose:
                print("  %-22s key %-15s %s" % (fn, name,
                      "CRC verifies" if got else "refused"))
        os.remove(os.path.join(tmp, fn))
        ok += 1
    return ok, bad


def main():
    verbose = "-v" in sys.argv
    macextract = None
    if "--macextract" in sys.argv:
        macextract = sys.argv[sys.argv.index("--macextract") + 1]
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

    print("derive-sit5crypt: %d of %d archive(s) Aladdin's own software "
          "wrote" % (ok, len(CASES)))
    if bad:
        for b_ in bad:
            print("derive-sit5crypt: FAIL: " + b_)
        return 1

    print("            bit 7 = encrypted, bit 4 = the hash sits 14 bytes "
          "later, and the hash is MD5(MD5(password)[:5])[:5] — measured at "
          "4, 9 and 17 characters, against Aladdin's own output.")

    cok, cbad = check_comment(verbose)
    ook, obad = check_order(verbose)
    cbad += obad
    if cbad:
        for b_ in cbad:
            print("derive-sit5crypt: FAIL: " + b_)
        return 1
    if cok:
        print("derive-sit5crypt: bit 5 = an archive COMMENT, measured: its "
              "block is the comment's length and its style scrap's length, "
              "4 bytes, and 100 + 14 + 4 + both lengths is exactly where "
              "the archive says its first entry starts.")
    if ook:
        print("derive-sit5crypt: and the hash sits AFTER that block in the "
              "%d archive(s) that set both bits — the length byte reads 5 "
              "at 100+14+4 and 0 at 100+14, so the four-byte shift is "
              "load-bearing." % ook)
    if macextract:
        kok, kbad = check_key(macextract, verbose)
        if kbad:
            for b_ in kbad:
                print("derive-sit5crypt: FAIL: " + b_)
            return 1
        if kok:
            print("derive-sit5crypt: the KEY is MD5(password)[:5], then "
                  "the fork's own five: on %d archive(s) every fork's CRC "
                  "verifies under it, and under none of %d other rules."
                  % (kok, len(KEY_RULES) - 1))
    else:
        print("derive-sit5crypt: the key itself not graded — "
              "--macextract BIN to decompress with")
    return 0


if __name__ == "__main__":
    sys.exit(main())
