#!/usr/bin/env python3
"""synth_crypt.py — deterministic synthetic ENCRYPTED fixtures.

Nothing in the 903-file corpus is encrypted (measured 2026-08-23 with
`lsar -j` over every fixture: XADIsEncrypted is 0 everywhere), and the
applications that could write one — StuffIt Deluxe, PackIt — either do
not run here or do not exist here. So the fixtures for the password
schemes this engine reads are generated: a StuffIt classic archive under
StuffItDES, a StuffIt 5 archive under RC4, PackIt's two — the PC-1 XOR
and DES — Compact Pro's, ARC's garble, and zip's two, PKWARE's stream
cipher and WinZip's AES at 128 and 256 bits. Nine shapes for the eight
ciphers, which is what it takes for tools/fuzz.py to reach every one of
them; AES is two of the nine because 128 and 256 take different paths
through the key schedule.

**These files grade nothing on their own.** Every byte of them comes
out of the same reading of the format as the decoder they would test,
so agreement between the two says only that the reading is
self-consistent. What grades them is somebody else's implementation:
tools/run_crypt.py generates each file, hands it to `unar -p` — a
different reading of five of the eight schemes — and only then to us. A
file `unar` cannot decrypt is a bug HERE and the suite says so. Three of
the eight shapes it cannot read at all — WinZip AES at either key length,
and Compact Pro's — and each of those has its own outside reader: AES
goes to `7z t`, which verifies the authentication code, and Compact Pro's
to Compact Pro 1.51 itself under Mini vMac (tools/vmac/cptcrypt.py),
because no other implementation of that cipher exists anywhere.

For StuffIt classic that means the archive has to arrive as MacBinary:
its password verifier is the 'MKey' resource, which lives in the
archive's resource fork, and a bare data fork has nowhere to put one.

Deterministic: no randomness, no timestamps.

Usage: synth_crypt.py --kind sit-des -o out.sit.bin --password swordfish
       synth_crypt.py --kind zip-aes -o out.zip --ranges out.json
"""
import argparse
import hashlib
import hmac
import os
import re
import struct
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import synth_pit as PIT                                       # noqa: E402
import synth_wrapped as W                                     # noqa: E402

REPO = os.path.dirname(HERE)
SITDES_REF = os.path.join(REPO, "reference", "XADMaster",
                          "XADStuffItDESHandle.m")


def crc16_arc(data, crc=0):
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


# ---------------------------------------------------------------------------
# StuffItDES — the same modified DES src/unc_crypt.c transcribes, in the
# same little-endian formulation, from the same file. Key management
# only; the fork cipher below is separate.
# ---------------------------------------------------------------------------

def _sptrans():
    src = open(SITDES_REF).read()
    i = src.index("DES_SPtrans[8][64]=")
    j = src.index("{", i)
    depth, k = 0, j
    while True:
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    nums = [int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{8})", src[j:k])]
    assert len(nums) == 512
    return [nums[n * 64:(n + 1) * 64] for n in range(8)]


SP = _sptrans()
M32 = 0xFFFFFFFF


def rotr(v, n):
    return ((v >> n) | (v << (32 - n))) & M32


def revbits(v):
    r = 0
    for _ in range(32):
        r = (r << 1) | (v & 1)
        v >>= 1
    return r & M32


def _nibble(key, n):
    return (key[(n & 0x0F) >> 1] >> (((n ^ 1) & 1) << 2)) & 0x0F


def sitdes_setkey(key):
    ks = []
    for i in range(16):
        s1 = (_nibble(key, i) >> 2) | (_nibble(key, i + 13) << 2)
        s1 |= ((_nibble(key, i + 11) >> 2) | (_nibble(key, i + 6) << 2)) << 8
        s1 |= ((_nibble(key, i + 3) >> 2) | (_nibble(key, i + 10) << 2)) << 16
        s1 |= ((_nibble(key, i + 8) >> 2) | (_nibble(key, i + 1) << 2)) << 24
        s0 = (_nibble(key, i + 9) | (_nibble(key, i) << 4)) & 0x3F
        s0 |= ((_nibble(key, i + 2) | (_nibble(key, i + 11) << 4)) & 0x3F) << 8
        s0 |= ((_nibble(key, i + 14) | (_nibble(key, i + 3) << 4)) & 0x3F) << 16
        s0 |= ((_nibble(key, i + 5) | (_nibble(key, i + 8) << 4)) & 0x3F) << 24
        ks.append((revbits(s1), revbits(s0)))
    return ks


def _round(left, right, sk):
    u = right ^ sk[0]
    t = rotr(right, 4) ^ sk[1]
    left ^= (SP[0][(u >> 2) & 0x3F] ^ SP[2][(u >> 10) & 0x3F] ^
             SP[4][(u >> 18) & 0x3F] ^ SP[6][(u >> 26) & 0x3F] ^
             SP[1][(t >> 2) & 0x3F] ^ SP[3][(t >> 10) & 0x3F] ^
             SP[5][(t >> 18) & 0x3F] ^ SP[7][(t >> 26) & 0x3F])
    return left & M32


def sitdes_crypt(data, ks, enc):
    left = revbits(struct.unpack(">I", data[0:4])[0])
    right = revbits(struct.unpack(">I", data[4:8])[0])
    right = rotr(right, 29)
    left = rotr(left, 29)
    if enc:
        for i in range(0, 16, 2):
            left = _round(left, right, ks[i])
            right = _round(right, left, ks[i + 1])
    else:
        for i in range(15, 0, -2):
            left = _round(left, right, ks[i])
            right = _round(right, left, ks[i - 1])
    left = rotr(left, 3)
    right = rotr(right, 3)
    return struct.pack(">II", revbits(right), revbits(left))


def sit_archive_key(password):
    """The password, iterated into the archive key: one fold per
    eight-byte block, ceil(len/8) of them.

    Measured rather than transcribed — neither XADMaster nor `unar`
    1.10.8 has this right, and three archives StuffIt Deluxe 3.5.1 wrote
    say what it is (tools/vmac/sitcrypt.py).
    """
    ak = bytearray(b"\x01\x23\x45\x67\x89\xab\xcd\xef")
    ks = sitdes_setkey(bytes(ak))
    length = len(password)
    for x in range((length + 7) // 8):
        block = bytearray(8)
        off = x << 3
        n = min(8, length - off)
        block[:n] = password[off:off + n]
        for i in range(8):
            ak[i] ^= block[i] & 0x7F
        ak[:] = sitdes_crypt(bytes(ak), ks, True)
    return bytes(ak)


def sit_mkey_and_iv(password, seed=b"\x11\x22\x33\x44"):
    """Build an 'MKey' resource that VERIFIES for this password.

    Decryption computes iv = SITDES_decrypt(mkey) and then requires
    SITDES_encrypt(iv[0:4] + 00 00 00 04)[4:8] == iv[4:8]. So choose
    iv[0:4], derive iv[4:8] from that rule, and encrypt the result to
    get the resource.
    """
    ak = sit_archive_key(password)
    ks = sitdes_setkey(ak)
    vb = sitdes_crypt(seed + b"\x00\x00\x00\x04", ks, True)
    iv = seed + vb[4:8]
    mkey = sitdes_crypt(iv, ks, True)       # the reader DECRYPTS this
    assert sitdes_crypt(mkey, ks, False) == iv
    return mkey, ak, iv


def sit_entry_key(ak, iv, filekey, fileiv):
    """The sixteen bytes stored at the end of an encrypted fork."""
    ks_a = sitdes_setkey(ak)
    a = sitdes_crypt(bytes(x ^ y for x, y in zip(filekey, iv)), ks_a, True)
    b = sitdes_crypt(fileiv, sitdes_setkey(filekey), True)
    return a + b


def sit_fork_encrypt(plain, filekey, fileiv):
    """The fork cipher, run backwards. Plaintext is zero-padded to a
    multiple of eight; the count of pad bytes goes in the header."""
    pad = (-len(plain)) % 8
    plain = plain + b"\x00" * pad
    A, B = struct.unpack(">II", filekey)
    C, D = struct.unpack(">II", fileiv)
    out = bytearray()
    for i in range(0, len(plain), 8):
        l, r = struct.unpack(">II", plain[i:i + 8])
        left = l ^ A ^ C
        right = r ^ B ^ D
        out += struct.pack(">II", left, right)
        C = D
        D = rotr(left ^ right ^ A ^ B ^ D, 1)
    return bytes(out), pad


# ---------------------------------------------------------------------------
# A resource fork holding one 'MKey'
# ---------------------------------------------------------------------------

def resource_fork(entries):
    """entries: list of (type4, id, data). Minimal but real: the layout
    Inside Macintosh describes and src/unc_crypt.c reads."""
    data = bytearray()
    refs = {}
    for t, rid, blob in entries:
        refs.setdefault(t, []).append((rid, len(data)))
        data += struct.pack(">I", len(blob)) + blob
    typelist = bytearray(struct.pack(">H", len(refs) - 1))
    reflists = bytearray()
    reforigin = 2 + 8 * len(refs)          # within the type list
    for t, rl in refs.items():
        typelist += t + struct.pack(">HH", len(rl) - 1,
                                    reforigin + len(reflists))
        for rid, off in rl:
            # id, name offset (-1 = none), attributes+offset, handle
            reflists += struct.pack(">hhII", rid, -1, off, 0)
    tl = bytes(typelist) + bytes(reflists)
    mapp = bytearray(28)                    # 16 reserved + handle + refs + attrs
    struct.pack_into(">HH", mapp, 24, 28, 28 + len(tl))     # type list, names
    mp = bytes(mapp) + tl
    dataoff = 256
    head = bytearray(dataoff)
    struct.pack_into(">IIII", head, 0, dataoff, dataoff + len(data),
                     len(data), len(mp))
    return bytes(head) + bytes(data) + mp


# ---------------------------------------------------------------------------
# StuffIt classic, encrypted
# ---------------------------------------------------------------------------

SIT_CASES = [
    # name, data fork, resource fork
    ("Secret Memo", b"Meet at the Mac Plus. " * 12, b""),
    ("Both Forks", b"data fork bytes, " * 30, b"RSRC" + bytes(range(256))),
    ("Rsrc only", b"", b"\x00\x01\x02\x03" * 40),
]


def build_sit_des(password):
    mkey, ak, iv = sit_mkey_and_iv(password)
    body = bytearray()
    ranges = []
    for n, (name, data, rsrc) in enumerate(SIT_CASES):
        h = bytearray(112)
        forks = bytearray()
        rcomp = dcomp = 0
        rpad = dpad = 0
        # A distinct file key per fork, derived from the entry index so
        # the file stays deterministic.
        for which, payload in ((0, rsrc), (1, data)):
            if not payload:
                continue
            fk = bytes(((n * 2 + which) * 17 + i * 31) & 0xFF for i in range(8))
            fiv = bytes(((n * 2 + which) * 13 + i * 7) & 0xFF for i in range(8))
            ct, pad = sit_fork_encrypt(payload, fk, fiv)
            ct += sit_entry_key(ak, iv, fk, fiv)
            forks += ct
            if which == 0:
                rcomp, rpad = len(ct), pad
            else:
                dcomp, dpad = len(ct), pad
        h[0] = 0x80 if rsrc else 0          # rsrc: stored + encrypted
        h[1] = 0x80 if data else 0          # data: stored + encrypted
        nb = name.encode("mac_roman")
        h[2] = len(nb)
        h[3:3 + len(nb)] = nb
        h[66:74] = b"TEXTttxt"
        struct.pack_into(">I", h, 84, len(rsrc))
        struct.pack_into(">I", h, 88, len(data))
        struct.pack_into(">I", h, 92, rcomp)
        struct.pack_into(">I", h, 96, dcomp)
        struct.pack_into(">H", h, 100, crc16_arc(rsrc))
        struct.pack_into(">H", h, 102, crc16_arc(data))
        h[104] = rpad                       # SITFH_RSRCPAD
        h[105] = dpad                       # SITFH_DATAPAD
        struct.pack_into(">H", h, 110, crc16_arc(bytes(h[:110])))
        ranges.append((22 + len(body) + len(h),
                       22 + len(body) + len(h) + len(forks)))
        body += bytes(h) + bytes(forks)
    out = bytearray(22)
    out[0:4] = b"SIT!"
    struct.pack_into(">H", out, 4, len(SIT_CASES))
    struct.pack_into(">I", out, 6, 22 + len(body))
    out[10:14] = b"rLau"
    struct.pack_into(">I", out, 16, 22)
    sit = bytes(out) + bytes(body)
    return sit, resource_fork([(b"MKey", 0, mkey)]), ranges


# ---------------------------------------------------------------------------
# StuffIt 5, encrypted (RC4)
# ---------------------------------------------------------------------------

SIT5_BANNER = (b"StuffIt (c)1997-1998 Aladdin Systems, Inc., "
               b"http://www.aladdinsys.com/StuffIt/\r\n")


def rc4(key, data):
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 255
        s[i], s[j] = s[j], s[i]
    i = j = 0
    out = bytearray()
    for b in data:
        i = (i + 1) & 255
        j = (j + s[i]) & 255
        s[i], s[j] = s[j], s[i]
        out.append(b ^ s[(s[i] + s[j]) & 255])
    return bytes(out)


SIT5_CASES = [
    ("Encrypted 5", b"StuffIt 5 keeps its keys in the entry header. " * 8,
     b""),
    ("Two forks 5", b"data" * 100, b"rsrc" * 50),
]


def build_sit5_rc4(password):
    archivekey = hashlib.md5(password).digest()[:5]
    pwhash = hashlib.md5(archivekey).digest()[:5]

    banner = SIT5_BANNER
    # The banner is 80 bytes; the version byte is at 82, so two bytes of
    # whatever sit between them (XADStuffIt5Parser.m skips 82).
    head = bytearray(82)
    head[:len(banner)] = banner[:82]
    head += bytes([5, 0x80])                    # version 5, archive CRYPTED
    head += struct.pack(">I", 0)                # total size (patched below)
    head += struct.pack(">I", 0)
    head += struct.pack(">H", len(SIT5_CASES))
    head += struct.pack(">I", 0)                # first entry offset (patched)
    head += struct.pack(">H", 0)                # crc, unchecked by both readers
    head += bytes([5]) + pwhash                 # the password hash block
    firstoffs = len(head)
    struct.pack_into(">I", head, 94, firstoffs)

    body = bytearray()
    ranges = []
    for n, (name, data, rsrc) in enumerate(SIT5_CASES):
        nb = name.encode("mac_roman")
        dkey = bytes((n * 3 + i) & 0xFF for i in range(5))
        rkey = bytes((n * 5 + i * 2) & 0xFF for i in range(5))
        e = bytearray()
        e += struct.pack(">I", 0xA5A5A5A5)      # 0  id
        e += bytes([1, 0])                      # 4  version, ?
        e += struct.pack(">H", 0)               # 6  header size (patched)
        e += bytes([0, 0x20])                   # 8  ?, flags: CRYPTED
        e += struct.pack(">II", 0xA5000000, 0xA6000000)   # 10 dates
        e += struct.pack(">III", 0, 0, 0)       # 18 prev, next, parent
        e += struct.pack(">H", len(nb))         # 30 name length
        e += struct.pack(">H", 0)               # 32 header crc (unchecked)
        e += struct.pack(">II", len(data), len(data))     # 34 sizes
        e += struct.pack(">H", crc16_arc(data))           # 42 crc
        e += struct.pack(">H", 0)               # 44 ?
        e += bytes([0, 5]) + dkey               # 46 method 0, key len, key
        e += nb
        # "Header size" ends at the name (or at the comment, if there
        # were one): both readers treat anything between the name and
        # that offset as a comment block.
        struct.pack_into(">H", e, 6, len(e))
        e += struct.pack(">H", 1 if rsrc else 0)          # flags2: has rsrc
        e += struct.pack(">H", 0)
        e += b"TEXTttxt"
        e += struct.pack(">H", 0)               # finder flags
        e += bytes(22)                          # version 1: 22 filler bytes
        if rsrc:
            e += struct.pack(">II", len(rsrc), len(rsrc))
            e += struct.pack(">H", crc16_arc(rsrc))
            e += struct.pack(">H", 0)
            e += bytes([0, 5]) + rkey
        encstart = len(e)
        if rsrc:
            e += rc4(archivekey + rkey, rsrc)
        e += rc4(archivekey + dkey, data)
        ranges.append((firstoffs + len(body) + encstart,
                       firstoffs + len(body) + len(e)))
        body += e

    struct.pack_into(">I", head, 84, firstoffs + len(body))
    return bytes(head) + bytes(body), ranges


# ---------------------------------------------------------------------------
# PackIt PMa5 (PC-1 XOR) and PMa6 (DES)
# ---------------------------------------------------------------------------

PC1 = [57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2,
       59, 51, 43, 35, 27, 19, 11, 3, 60, 52, 44, 36,
       63, 55, 47, 39, 31, 23, 15, 7, 62, 54, 46, 38, 30, 22, 14, 6,
       61, 53, 45, 37, 29, 21, 13, 5, 28, 20, 12, 4]


def packit_xor_key(password):
    pw = (password + b"\x00" * 8)[:8]
    key = bytearray(8)
    for i in range(56):
        bit = PC1[i] - 1
        key[i // 8] |= ((pw[bit // 8] << (bit % 8)) & 0x80) >> (i % 8)
    return bytes(key)


def des_ecb(data, key, decrypt):
    """openssl, so that not one byte of the PMa6 fixture is produced by
    this project's own DES."""
    cmd = ["openssl", "enc", "-des-ecb", "-K", key.hex(), "-nopad",
           "-provider", "legacy", "-provider", "default"]
    if decrypt:
        cmd.append("-d")
    return subprocess.run(cmd, input=data, capture_output=True,
                          check=True).stdout


PIT_CASES = [
    ("Encrypted Note", b"PackIt encrypted this in 1987. " * 10, b""),
    ("Both forks", b"data fork" * 40, b"resource fork" * 20),
]


def build_packit(password, des):
    parts = []
    ranges = []

    def at():
        return sum(len(x) for x in parts)

    # One entry in the clear first, so the fixture also proves that a
    # reader gets back onto the rails after an encrypted block.
    parts.append(PIT.stored_entry("Read Me", b"not a secret\n", b""))
    for name, data, rsrc in PIT_CASES:
        stream = PIT.huffman_entry(name, data, rsrc)[4:]   # drop 'PMa4'
        stream += b"\x00" * ((-len(stream)) % 8)
        ranges.append((at() + 4, at() + 4 + len(stream)))
        if des:
            key = (password + b"\x00" * 8)[:8]
            parts.append(b"PMa6" + des_ecb(stream, key, False))
        else:
            key = packit_xor_key(password)
            parts.append(b"PMa5" + bytes(b ^ key[i % 7]
                                         for i, b in enumerate(stream)))
    parts.append(PIT.stored_entry("Trailer", b"after the secret\n", b""))
    return b"".join(parts) + b"PEnd", ranges


# ---------------------------------------------------------------------------
# AES, forward direction only — the keystream WinZip's AE-2 needs, because
# no Python on this machine has one (no `cryptography`, no `pycryptodome`;
# `hashlib` supplies PBKDF2 and HMAC and no cipher).
# ---------------------------------------------------------------------------

def _xtime(x):
    return ((x << 1) ^ 0x1B) & 0xFF if x & 0x80 else (x << 1) & 0xFF


def _aes_sbox():
    """The S box built the way FIPS-197 section 5.1.1 defines it — the
    multiplicative inverse in GF(2^8) modulo x^8+x^4+x^3+x+1, then the
    affine transform. The same construction tools/gen_crypt_tables.py
    checks the engine's table against, and for the same reason: a
    transcribed table is somebody's implementation, a built one is the
    standard's."""
    p = q = 1
    inv = [0] * 256
    while True:
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        inv[p] = q
        if p == 1:
            break
    box = []
    for x in range(256):
        v = inv[x] if x else 0
        r = v
        for _ in range(4):
            v = ((v << 1) | (v >> 7)) & 0xFF
            r ^= v
        box.append(r ^ 0x63)
    assert len(set(box)) == 256
    return box


class Aes:
    """AES-128/192/256, encryption only, which is all counter mode uses.
    Key schedule: FIPS-197 section 5.2; the round: section 5.1, with the
    state held column-major the way the standard numbers it.

    Nothing here grades anything on its own — `tools/run_crypt.py` hands
    the archive this ends up inside to `7z t`, which is a different
    implementation of every part of it (TESTING.md, *Fuzzing*)."""

    SBOX = _aes_sbox()

    def __init__(self, key):
        nk = len(key) // 4
        assert nk in (4, 6, 8), "AES takes 16, 24 or 32 key bytes"
        self.rounds = nk + 6
        rk = list(key)
        rcon = 1
        for i in range(nk, (self.rounds + 1) * 4):
            t = rk[(i - 1) * 4:i * 4]
            if i % nk == 0:
                t = [self.SBOX[t[1]] ^ rcon, self.SBOX[t[2]],
                     self.SBOX[t[3]], self.SBOX[t[0]]]
                rcon = _xtime(rcon)
            elif nk > 6 and i % nk == 4:
                t = [self.SBOX[b] for b in t]
            rk += [rk[(i - nk) * 4 + j] ^ t[j] for j in range(4)]
        self.rk = rk

    def encrypt_block(self, block):
        st = [b ^ k for b, k in zip(block, self.rk[0:16])]
        for rnd in range(1, self.rounds + 1):
            st = [self.SBOX[b] for b in st]
            # ShiftRows, in column-major indexing: byte i is row i%4 of
            # column i//4, and row r moves left by r columns.
            st = [st[(i % 4) + 4 * (((i // 4) + (i % 4)) % 4)]
                  for i in range(16)]
            if rnd != self.rounds:
                mixed = []
                for c in range(4):
                    a = st[c * 4:c * 4 + 4]
                    for r in range(4):
                        mixed.append(_xtime(a[r]) ^
                                     (_xtime(a[(r + 1) % 4]) ^ a[(r + 1) % 4]) ^
                                     a[(r + 2) % 4] ^ a[(r + 3) % 4])
                st = mixed
            k = self.rk[rnd * 16:rnd * 16 + 16]
            st = [b ^ kb for b, kb in zip(st, k)]
        return bytes(st)


# The two known-answer vectors FIPS-197 publishes in appendix C, so a
# wrong round here fails at import rather than inside a fuzz seed.
assert Aes(bytes(range(16))).encrypt_block(
    bytes.fromhex("00112233445566778899aabbccddeeff")) == \
    bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
assert Aes(bytes(range(32))).encrypt_block(
    bytes.fromhex("00112233445566778899aabbccddeeff")) == \
    bytes.fromhex("8ea2b7ca516745bfeafc49904b496089")


# ---------------------------------------------------------------------------
# zip: the traditional PKWARE cipher, and WinZip's AES
#
# Both shapes have an encoder on this machine already — `zip -P` and
# `7z -p`, which is what tools/run_crypt.py grades the decoders against.
# They are written HERE as well because a fuzz seed has one job an
# external encoder cannot do: be the same bytes on every machine and in
# every run. fuzz.py advertises seeded reproducibility, and 7-Zip picks a
# random salt while Info-ZIP's encryption header is seeded from the
# clock, so a seed either tool wrote would make a quarter of the fuzz run
# unreproducible and its coverage conditional on what is installed.
# Written here, all eight ciphers are fuzzed wherever Python runs.
#
# The archives are then handed BACK to those tools by run_crypt.py, which
# is what says these are real archives rather than plausible ones.
# ---------------------------------------------------------------------------

DOS_TIME, DOS_DATE = 0x6000, 0x2A21          # fixed: no clock in a fixture


def _crc_table():
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
        t.append(c)
    return t


CRC_T = _crc_table()


def _crc_step(crc, b):
    """One byte through the same reflected register src/unc_util.c's
    unc_crc32 uses — NOT zlib.crc32, whose running value is complemented
    at both ends."""
    return (crc >> 8) ^ CRC_T[(crc ^ b) & 0xFF]


def _deflate(data):
    z = zlib.compressobj(9, zlib.DEFLATED, -15)
    return z.compress(data) + z.flush()


class ZipCipher:
    """The traditional zip stream cipher. Source:
    reference/notes/zip_appnote.txt section 6.1 — the three key
    constants, update_keys and decrypt_byte are all written out there."""

    def __init__(self, password):
        self.k = [305419896, 591751049, 878082192]
        for b in password:
            self.update(b)

    def update(self, b):
        self.k[0] = _crc_step(self.k[0], b)
        self.k[1] = (self.k[1] + (self.k[0] & 0xFF)) & 0xFFFFFFFF
        self.k[1] = (self.k[1] * 134775813 + 1) & 0xFFFFFFFF
        self.k[2] = _crc_step(self.k[2], (self.k[1] >> 24) & 0xFF)

    def _byte(self):
        t = (self.k[2] | 2) & 0xFFFF
        return ((t * (t ^ 1)) >> 8) & 0xFF

    def encrypt(self, plain):
        out = bytearray()
        for p in plain:
            out.append(p ^ self._byte())
            self.update(p)
        return bytes(out)


def _zip(entries):
    """entries: (name, method, crc, usize, extra, payload). Returns the
    archive and the byte range each payload occupies in it."""
    out = bytearray()
    cd = bytearray()
    ranges = []
    for name, method, crc, usize, extra, payload in entries:
        nb = name.encode("ascii")
        off = len(out)
        out += b"PK\x03\x04" + struct.pack("<HHHHHIIIHH", 20, 1, method,
                                           DOS_TIME, DOS_DATE, crc,
                                           len(payload), usize, len(nb),
                                           len(extra))
        out += nb + extra
        ranges.append((len(out), len(out) + len(payload)))
        out += payload
        cd += b"PK\x01\x02" + struct.pack("<HHHHHHIIIHHHHHII", 20, 20, 1,
                                          method, DOS_TIME, DOS_DATE, crc,
                                          len(payload), usize, len(nb),
                                          len(extra), 0, 0, 0, 0, off)
        cd += nb + extra
    cdoff = len(out)
    out += cd
    out += b"PK\x05\x06" + struct.pack("<HHHHIIH", 0, 0, len(entries),
                                       len(entries), len(cd), cdoff, 0)
    return bytes(out), ranges


ZIP_CASES = [
    # name, method, plaintext
    ("stored.txt", 0, b"stored, and encrypted all the same\n"),
    ("deflated.txt", 8, b"the same line, over and over\n" * 40),
    ("random.bin", 8, bytes((i * 37 + 11) & 0xFF for i in range(3000))),
]


def build_zip_crypt(password):
    """One encryption header of twelve bytes per entry, its last byte the
    top byte of the entry's CRC, then the compressed bytes — all under
    one keystream (zip_appnote.txt section 6.1). Stored and deflated
    entries both, so neither of the reader's two paths is in the clear."""
    entries = []
    for n, (name, method, plain) in enumerate(ZIP_CASES):
        comp = plain if method == 0 else _deflate(plain)
        crc = zlib.crc32(plain) & 0xFFFFFFFF
        hdr = bytes((i * 29 + n * 13 + 7) & 0xFF for i in range(11)) + \
            bytes([(crc >> 24) & 0xFF])
        entries.append((name, method, crc, len(plain), b"",
                        ZipCipher(password).encrypt(hdr + comp)))
    return _zip(entries)


def build_zip_aes(password, keybytes=32):
    """WinZip AE-2. Source: reference/notes/winzip_aes.txt for the
    parameters and the extra field, RFC 2898 for the derivation, RFC 2104
    and RFC 3174 for the authentication code.

    AE-2 stores no CRC, so the ten-byte authentication code over the
    CIPHERtext is the only thing that grades the bytes — which is exactly
    the property the fuzzer wants: a flipped ciphertext byte runs every
    round of AES and every block of HMAC before anything refuses it.

    The ranges reported are the ciphertext and that code, and NOT the
    salt or the two verifier bytes, so a targeted mutant always gets past
    the verifier into the cipher."""
    strength = {16: 1, 24: 2, 32: 3}[keybytes]
    entries = []
    ranges_in = []
    for n, (name, method, plain) in enumerate(ZIP_CASES):
        comp = plain if method == 0 else _deflate(plain)
        salt = bytes((i * 41 + n * 17 + 3) & 0xFF for i in range(keybytes // 2))
        dk = hashlib.pbkdf2_hmac("sha1", password, salt, 1000,
                                 2 * keybytes + 2)
        enckey, mackey = dk[:keybytes], dk[keybytes:2 * keybytes]
        # Counter mode, the counter little-endian from 1 — the engine's
        # own increment is over the low eight bytes of sixteen zeroes.
        ct = bytearray()
        aes = Aes(enckey)
        for i in range(0, len(comp), 16):
            ctr = struct.pack("<QQ", i // 16 + 1, 0)
            ks = aes.encrypt_block(ctr)
            ct += bytes(a ^ b for a, b in zip(comp[i:i + 16], ks))
        auth = hmac.new(mackey, bytes(ct), hashlib.sha1).digest()[:10]
        extra = struct.pack("<HHH2sBH", 0x9901, 7, 2, b"AE", strength,
                            method)
        payload = salt + dk[2 * keybytes:] + bytes(ct) + auth
        ranges_in.append((len(salt) + 2, len(payload)))
        entries.append((name, 99, 0, len(plain), extra, payload))
    blob, ranges = _zip(entries)
    return blob, [(at + lo, at + hi)
                  for (at, _), (lo, hi) in zip(ranges, ranges_in)]


ARC_CASES = [
    # name, method, plaintext. Three coders, so the garble runs over
    # three different compressed streams.
    ("stored.txt", 2, b"garbled, and stored\n" * 3),
    ("runs.bin", 3, b"A" * 200 + b"\x90" * 3 + b"B" * 120),
    ("text.txt", 8, b"the quick brown fox jumps over it. " * 12),
]


def build_arc_garble(password):
    """ARC's "garble": the password XORed over an entry's COMPRESSED
    bytes, repeating from the start of each entry, with nothing in the
    file saying it was done (`src/fmt_arc.c`; XADARCParser.m and
    XADXORHandle.m). So the engine finds it by decoding an entry, failing
    its CRC, and trying the password — which makes this the one shape
    here whose cipher is reached only because the CRC does NOT check out.

    The container and the coders are tools/synth_arc.py's, which `unar`
    already adjudicates method by method; `arc g<password>` writes the
    graded fixtures in run_crypt.py and reaches only its own four
    methods. Three methods here, so the garble is over three different
    compressed streams."""
    import synth_arc as ARC                                   # noqa: E402
    out = bytearray()
    ranges = []
    for name, method, data in ARC_CASES:
        e = ARC.entry(method, name, data)
        # entry() is header + payload, and only the payload is garbled:
        # 29 bytes of header, 25 for method 1, which has no size field.
        hdr = 29 if method != 1 else 25
        payload = bytes(b ^ password[i % len(password)]
                        for i, b in enumerate(e[hdr:]))
        ranges.append((len(out) + hdr, len(out) + len(e)))
        out += e[:hdr] + payload
    out += b"\x1a\x00"
    return bytes(out), ranges


def build_cpt(password):
    """Compact Pro, from tools/synth_cpt.py — the writer that already
    exists because Compact Pro's cipher is the one scheme here no other
    implementation reads, and the archives it writes are what Compact Pro
    1.51 itself graded under Mini vMac (DECISIONS.md 2026-08-23).

    Everything after the eight-byte header is encrypted, and the header's
    own index-offset field says where it ends."""
    import synth_cpt as CPT                                   # noqa: E402
    blob = CPT.build(password)
    return blob, [(8, struct.unpack(">I", blob[4:8])[0])]


# ---------------------------------------------------------------------------

KINDS = ["sit-des", "sit5-rc4", "packit-xor", "packit-des", "cpt",
         "arc-garble", "zip-crypt", "zip-aes", "zip-aes128"]


def build(kind, password):
    """Return (archive bytes, encrypted byte ranges, resource fork or
    None). A range is a half-open (start, end) pair of offsets into the
    archive covering bytes the reader hands to a cipher — what
    tools/fuzz.py mutates when it wants the cipher rather than the
    container (TESTING.md, *Fuzzing*)."""
    if kind == "sit-des":
        sit, rsrc, ranges = build_sit_des(password)
        return sit, ranges, rsrc
    if kind == "sit5-rc4":
        blob, ranges = build_sit5_rc4(password)
    elif kind == "cpt":
        blob, ranges = build_cpt(password)
    elif kind == "arc-garble":
        blob, ranges = build_arc_garble(password)
    elif kind == "zip-crypt":
        blob, ranges = build_zip_crypt(password)
    elif kind == "zip-aes":
        blob, ranges = build_zip_aes(password)
    elif kind == "zip-aes128":
        blob, ranges = build_zip_aes(password, 16)
    else:
        blob, ranges = build_packit(password, kind == "packit-des")
    return blob, ranges, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=KINDS)
    ap.add_argument("--password", default="swordfish")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--ranges",
                    help="write the encrypted byte ranges of the output to "
                         "this file as JSON, for a mutator that wants the "
                         "cipher and not the container")
    args = ap.parse_args()
    pw = args.password.encode("mac_roman")

    blob, ranges, rsrc = build(args.kind, pw)
    if rsrc is not None and args.output.endswith(".bin"):
        # The MacBinary form, which is the only one with somewhere to put
        # the 'MKey' resource: the data fork starts at 128.
        open(args.output, "wb").write(
            W.macbinary("Secret.sit", blob, rsrc, b"SIT!", b"SIT!"))
        ranges = [(lo + 128, hi + 128) for lo, hi in ranges]
    elif rsrc is not None:
        open(args.output, "wb").write(blob)
        open(args.output + ".rsrc", "wb").write(rsrc)
    else:
        open(args.output, "wb").write(blob)
    if args.ranges:
        import json
        json.dump(ranges, open(args.ranges, "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
