#!/usr/bin/env python3
"""synth_crypt.py — deterministic synthetic ENCRYPTED fixtures.

Nothing in the 903-file corpus is encrypted (measured 2026-08-23 with
`lsar -j` over every fixture: XADIsEncrypted is 0 everywhere), and the
applications that could write one — StuffIt Deluxe, PackIt — either do
not run here or do not exist here. So the fixtures for the four
password schemes this engine reads are generated: a StuffIt classic
archive under StuffItDES, a StuffIt 5 archive under RC4, and PackIt's
two, the PC-1 XOR and DES.

**These files grade nothing on their own.** Every byte of them comes
out of the same reading of the format as the decoder they would test,
so agreement between the two says only that the reading is
self-consistent. What grades them is `unar`, which is a different
implementation of all four: tools/run_crypt.py generates each file,
hands it to `unar -p`, and only then to us. A file `unar` cannot
decrypt is a bug HERE and the suite says so.

For StuffIt classic that means the archive has to arrive as MacBinary:
its password verifier is the 'MKey' resource, which lives in the
archive's resource fork, and a bare data fork has nowhere to put one.

Deterministic: no randomness, no timestamps.

Usage: synth_crypt.py --kind sit-des -o out.sit.bin --password swordfish
"""
import argparse
import hashlib
import os
import re
import struct
import subprocess
import sys

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
    """The password, iterated into the archive key. Mirrors
    keyForPasswordData:entryKey:MKey: exactly, including its loop."""
    ak = bytearray(b"\x01\x23\x45\x67\x89\xab\xcd\xef")
    ks = sitdes_setkey(bytes(ak))
    length = len(password)
    x = 0
    while True:
        block = bytearray(8)
        off = x << 3
        n = 8 if (off <= length and length - off >= 8) else max(0, length - off)
        block[:n] = password[off:off + n]
        for i in range(8):
            ak[i] ^= block[i] & 0x7F
        ak[:] = sitdes_crypt(bytes(ak), ks, True)
        x += 1
        if not ((((x * (length >> 3)) << 3) <= length) and length >= 8):
            break
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
        body += bytes(h) + bytes(forks)
    out = bytearray(22)
    out[0:4] = b"SIT!"
    struct.pack_into(">H", out, 4, len(SIT_CASES))
    struct.pack_into(">I", out, 6, 22 + len(body))
    out[10:14] = b"rLau"
    struct.pack_into(">I", out, 16, 22)
    sit = bytes(out) + bytes(body)
    return sit, resource_fork([(b"MKey", 0, mkey)])


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
        if rsrc:
            e += rc4(archivekey + rkey, rsrc)
        e += rc4(archivekey + dkey, data)
        body += e

    struct.pack_into(">I", head, 84, firstoffs + len(body))
    return bytes(head) + bytes(body)


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
    # One entry in the clear first, so the fixture also proves that a
    # reader gets back onto the rails after an encrypted block.
    parts.append(PIT.stored_entry("Read Me", b"not a secret\n", b""))
    for name, data, rsrc in PIT_CASES:
        stream = PIT.huffman_entry(name, data, rsrc)[4:]   # drop 'PMa4'
        stream += b"\x00" * ((-len(stream)) % 8)
        if des:
            key = (password + b"\x00" * 8)[:8]
            parts.append(b"PMa6" + des_ecb(stream, key, False))
        else:
            key = packit_xor_key(password)
            parts.append(b"PMa5" + bytes(b ^ key[i % 7]
                                         for i, b in enumerate(stream)))
    parts.append(PIT.stored_entry("Trailer", b"after the secret\n", b""))
    return b"".join(parts) + b"PEnd"


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True,
                    choices=["sit-des", "sit5-rc4", "packit-xor",
                             "packit-des"])
    ap.add_argument("--password", default="swordfish")
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()
    pw = args.password.encode("mac_roman")

    if args.kind == "sit-des":
        sit, rsrc = build_sit_des(pw)
        if args.output.endswith(".bin"):
            open(args.output, "wb").write(
                W.macbinary("Secret.sit", sit, rsrc, b"SIT!", b"SIT!"))
        else:
            open(args.output, "wb").write(sit)
            open(args.output + ".rsrc", "wb").write(rsrc)
    elif args.kind == "sit5-rc4":
        open(args.output, "wb").write(build_sit5_rc4(pw))
    else:
        open(args.output, "wb").write(
            build_packit(pw, args.kind == "packit-des"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
