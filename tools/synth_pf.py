#!/usr/bin/env python3
"""synth_pf.py — write an Aladdin Private File (`.pf`) from this project's reading.

It writes what src/fmt_pf.c reads, and so it can grade NOTHING about the
format: an encoder and a decoder sharing one reading agree with each other
whatever the truth is. What grades the reading is the specimens Private
File 2.0 itself wrote under Mini vMac (tools/vmac/privatefile.py,
tools/run_privatefile.py). This exists for the cases those cannot cover —
a file whose header names a method nothing writes, a flipped byte, a
truncation — where what is checked is the REFUSAL, not a decryption.

Source: fmt_pf.c's header comment, which was read off PF Encrypt™ 2.0's
CODE 4 and graded byte-exact on its output (DECISIONS.md 2026-10-08).
"""
import hashlib
import struct


def rc4(key):
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 255
        s[i], s[j] = s[j], s[i]
    i = j = 0
    while True:
        i = (i + 1) & 255
        j = (j + s[i]) & 255
        s[i], s[j] = s[j], s[i]
        yield s[(s[i] + s[j]) & 255]


def crypt(stream, data):
    return bytes(b ^ next(stream) for b in data)


_T = []
for _n in range(256):
    _c = _n
    for _ in range(8):
        _c = (_c >> 1) ^ 0xEDB88320 if _c & 1 else _c >> 1
    _T.append(_c)


def crc32_raw(data, crc=0):
    """The reflected CRC-32, started at 0 and never inverted."""
    for b in data:
        crc = _T[(crc ^ b) & 255] ^ (crc >> 8)
    return crc


def encode(name, ftype, creator, data, rsrc, password, keylen=5,
           version=2, derivation=1, cipher=1, finfo=None, fxinfo=None):
    """`finfo`/`fxinfo`, 16 bytes each, replace the record's FInfo (type,
    creator, then zeros by default) and FXInfo (zeros) whole."""
    key = hashlib.md5(password).digest()[:keylen]
    hdr = struct.pack(">4s5HI", b"CSIT", version, derivation, cipher,
                      keylen, 0, 0)
    n = name.encode("mac_roman")
    rec = (b"CSIT" + bytes([len(n)]) + n + bytes(255 - len(n)) +
           (finfo if finfo is not None else ftype + creator + bytes(8)) +
           (fxinfo if fxinfo is not None else bytes(16)) +
           struct.pack(">4I", len(data), len(rsrc), 0xB0000000, 0xB0000001))
    assert len(rec) == 308
    forks = rc4(key)
    return (hdr + crypt(rc4(key), rec) + crypt(forks, data) +
            crypt(forks, rsrc) +
            struct.pack(">4sII", b"CSIT", crc32_raw(data), crc32_raw(rsrc)))
