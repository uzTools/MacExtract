#!/usr/bin/env python3
"""Generate src/crypt_tables.h — the constant tables the ciphers need.

Both are transcriptions, not derivations from memory:

  * The standard-DES tables (PC-1, PC-2, the shift schedule, the S boxes
    and P) are the ones in reference/XADMaster/Crypto/des.c, which builds
    equivalent lookup tables at RUNTIME into file-scope arrays.  This
    engine may not have global mutable state, so the same tables are
    precomputed here and emitted as const data.  The initial and final
    permutations are the ones that file's comment spells out in prose
    ("L = I7,1 I6,1 I5,1 ... I0,1  I7,3 ...") rather than tabulates;
    that formula is reproduced below and checked against the published
    IP by the DES known-answer test in tests/unit_formats.c.

  * The MD5 tables are the per-step constants, rotation counts and
    message-word indices of reference/XADMaster/Crypto/md5.c, pulled out
    of its unrolled STEP() list so the loop here can be a loop.

  * `unc_cpt_crc64` is the byte table of the 64-bit CRC Compact Pro
    keys its cipher with. There is no reference implementation and no
    published description of that cipher: it was read out of Compact
    Pro 1.51's own `CODE` 3, where the routine at 0x408e builds this
    table with the polynomial 0xEDB88320EDB88320 — CRC-32's reflected
    polynomial in both halves — and the routine at 0x40fe seeds the
    state with 0x0123456789ABCDEF. DECISIONS.md 2026-08-23.

  * `unc_sitdes_sp` is DES_SPtrans from
    reference/XADMaster/XADStuffItDESHandle.m, copied verbatim: the
    StuffIt variant is a little-endian DES formulation and needs that
    table's bit order, not the natural one.

Run: python3 tools/gen_crypt_tables.py > src/crypt_tables.h
"""
import re
import sys

REF = "reference/XADMaster/Crypto/des.c"
SITREF = "reference/XADMaster/XADStuffItDESHandle.m"


def grab_table(path, name, count):
    """Pull `static ... name[...] = { ... };` out of a C file."""
    src = open(path).read()
    i = src.index(name)
    j = src.index("{", i)
    k = src.index("};", j)
    nums = [int(x) for x in re.findall(r"\d+", src[j + 1:k])]
    assert len(nums) == count, (name, len(nums), count)
    return nums


# ---- standard DES, from reference/XADMaster/Crypto/des.c ----------------
PC1_C = grab_table(REF, "bK_C[28]", 28)      # permuted choice 1, C half
PC1_D = grab_table(REF, "bK_D[28]", 28)      # ... and D half
SHIFTS = grab_table(REF, "preshift[16]", 16)
PC2 = grab_table(REF, "bCD_KS[48]", 48)      # permuted choice 2
P = grab_table(REF, "uint8_t P[32]", 32)
S = grab_table(REF, "uint8_t S[8][64]", 8 * 64)
S = [S[i * 64:(i + 1) * 64] for i in range(8)]

# The initial permutation, from that file's own description of it:
#   L = I7,1 I6,1 ... I0,1  I7,3 ... I0,3  I7,5 ... I0,5  I7,7 ... I0,7
#   R = I7,0 I6,0 ... I0,0  I7,2 ... I0,2  I7,4 ... I0,4  I7,6 ... I0,6
# where Ii,j is bit j (0 = most significant) of input byte i, i.e. the
# 1-based DES bit number 8*i + j + 1.
IP = []
for j in (1, 3, 5, 7):
    for i in range(7, -1, -1):
        IP.append(8 * i + j + 1)
for j in (0, 2, 4, 6):
    for i in range(7, -1, -1):
        IP.append(8 * i + j + 1)
assert sorted(IP) == list(range(1, 65))

FP = [0] * 64
for k, src_bit in enumerate(IP):
    FP[src_bit - 1] = k + 1

# S merged with P, indexed by the raw 6-bit E-expansion value, so the
# round function is eight lookups and seven XORs. Bit 1 of the 32-bit
# result is the most significant bit, matching the rest of this engine.
SP = []
for box in range(8):
    col = []
    for v in range(64):
        row = ((v & 0x20) >> 4) | (v & 1)
        column = (v >> 1) & 0xF
        out = S[box][row * 16 + column]
        word = 0
        for b in range(4):                    # bit b of the 4-bit output
            if out & (8 >> b):
                pos = box * 4 + b + 1         # position in the pre-P word
                dest = P.index(pos) + 1       # where P sends it
                word |= 1 << (32 - dest)
        col.append(word)
    SP.append(col)


def sit_sptrans():
    src = open(SITREF).read()
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
    assert len(nums) == 8 * 64, len(nums)
    return [nums[i * 64:(i + 1) * 64] for i in range(8)]


SITSP = sit_sptrans()

# ---- Compact Pro's 64-bit CRC table ------------------------------------
# Transcribed as an ALGORITHM from Compact Pro 1.51 `CODE` 3 @0x408e:
#
#   for i in 0..255:  hi = lo = 0; v = i
#     eight times:
#       feedback = (lo ^ v) & 1
#       (hi:lo) >>= 1                      # one 64-bit shift
#       if feedback: hi ^= 0xEDB88320; lo ^= 0xEDB88320
#       v >>= 1
#     table[i] = (hi, lo)
CPT_POLY = 0xEDB88320


def cpt_crc64_table():
    rows = []
    for i in range(256):
        hi = lo = 0
        v = i
        for _ in range(8):
            feedback = (lo ^ v) & 1
            lo = (lo >> 1) | ((hi & 1) << 31)
            hi >>= 1
            if feedback:
                hi ^= CPT_POLY
                lo ^= CPT_POLY
            v >>= 1
        rows.append((hi, lo))
    return rows


CPTCRC = cpt_crc64_table()

# ---- MD5, from reference/XADMaster/Crypto/md5.c ------------------------
MD5REF = "reference/XADMaster/Crypto/md5.c"
_steps = re.findall(
    r"STEP\((\w+), (\w), (\w), (\w), (\w), (?:SET|GET)\((\d+)\), "
    r"(0x[0-9a-f]+), (\d+)\)", open(MD5REF).read())
assert len(_steps) == 64, len(_steps)
MD5_X = [int(s[5]) for s in _steps]
MD5_S = [int(s[7]) for s in _steps]
MD5_T = [int(s[6], 16) for s in _steps]
# The four rounds use F, G, H, I in that order, sixteen steps each, and
# the (a,b,c,d) rotation is the same in every step: assert both, because
# the loop that replaces this list assumes them.
assert [s[0] for s in _steps] == ["F"] * 16 + ["G"] * 16 + ["H"] * 16 + ["I"] * 16
assert all(tuple(_steps[i][1:5]) == ("adcb"[i % 4], "badc"[i % 4],
                                     "cbad"[i % 4], "dcba"[i % 4])
           for i in range(64))


def emit_u8(name, values, per_line=16):
    print("static const uint8_t %s[%d] = {" % (name, len(values)))
    for i in range(0, len(values), per_line):
        print("    " + ", ".join("%2d" % v for v in values[i:i + per_line]) + ",")
    print("};")
    print()


def emit_u32(name, values, per_line=4):
    print("static const uint32_t %s[%d] = {" % (name, len(values)))
    for i in range(0, len(values), per_line):
        print("    " + ", ".join("0x%08xu" % v for v in values[i:i + per_line]) + ",")
    print("};")
    print()


def emit_u32_2d(name, rows, per_line=4):
    print("static const uint32_t %s[%d][%d] = {" % (name, len(rows), len(rows[0])))
    for r in rows:
        print("  {")
        for i in range(0, len(r), per_line):
            print("    " + ", ".join("0x%08xu" % v for v in r[i:i + per_line]) + ",")
        print("  },")
    print("};")
    print()


def main():
    print("/*")
    print(" * crypt_tables.h — GENERATED by tools/gen_crypt_tables.py.")
    print(" * Do not edit.")
    print(" *")
    print(" * Source: reference/XADMaster/Crypto/des.c (PC-1 as bK_C/bK_D, PC-2")
    print(" * as bCD_KS, preshift, S, P, and the prose description of the")
    print(" * initial permutation) and reference/XADMaster/XADStuffItDESHandle.m")
    print(" * (DES_SPtrans, verbatim) and Crypto/md5.c (the STEP list).")
    print(" * LGPL / public domain — see NOTICE.")
    print(" */")
    print("#ifndef UNC_CRYPT_TABLES_H")
    print("#define UNC_CRYPT_TABLES_H")
    print()
    print("/* 1-based DES bit numbers throughout: bit 1 is the most")
    print(" * significant bit of the first byte. */")
    print()
    emit_u8("unc_des_ip", IP, 8)
    emit_u8("unc_des_fp", FP, 8)
    emit_u8("unc_des_pc1c", PC1_C, 7)
    emit_u8("unc_des_pc1d", PC1_D, 7)
    emit_u8("unc_des_pc2", PC2, 6)
    emit_u8("unc_des_shifts", SHIFTS, 16)
    print("/* S boxes merged with the P permutation, indexed by the six-bit")
    print(" * value the E expansion produces. */")
    emit_u32_2d("unc_des_sp", SP)
    print("/* The StuffIt variant's own table: a little-endian DES, so its")
    print(" * bit order is not the one above. Verbatim from XADMaster. */")
    emit_u32_2d("unc_sitdes_sp", SITSP)
    print("/* Compact Pro's cipher: a 64-bit CRC, high half then low. */")
    emit_u32_2d("unc_cpt_crc64", CPTCRC, 2)
    print("/* MD5: per-step message-word index, rotation and constant. */")
    emit_u8("unc_md5_x", MD5_X, 16)
    emit_u8("unc_md5_s", MD5_S, 16)
    emit_u32("unc_md5_t", MD5_T)
    print("#endif /* UNC_CRYPT_TABLES_H */")


main()
