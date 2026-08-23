#!/usr/bin/env python3
"""Regenerate the constants the cipher unit tests assert.

The point of the exercise is that none of them comes from this project:
DES from `openssl enc -des-ecb` (the legacy provider), MD5 from
hashlib, RC4 from the twenty lines below, which are the algorithm and
not a transcription of src/unc_crypt.c. Run it and compare with
tests/unit_formats.c (test_des, test_md5, test_rc4).
"""
import hashlib
import subprocess


def des_ecb_encrypt(key, block):
    out = subprocess.run(
        ["openssl", "enc", "-des-ecb", "-K", key.hex(), "-nopad",
         "-provider", "legacy", "-provider", "default"],
        input=block, capture_output=True, check=True).stdout
    return out[:8]


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


key = bytes.fromhex("0123456789abcdef")
print("DES  key=%s  'Now is t' -> %s"
      % (key.hex(), des_ecb_encrypt(key, b"Now is t").hex()))

msg = bytes(ord("a") + (i % 26) for i in range(80))
for label, m in (("''", b""), ("'abc'", b"abc"),
                 ("64 bytes", msg[:64]), ("80 bytes", msg)):
    print("MD5  %-10s -> %s" % (label, hashlib.md5(m).hexdigest()))

print("RC4  key='Key' 'Plaintext' -> %s" % rc4(b"Key", b"Plaintext").hex())
