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

  * `unc_aes_sbox` is the AES substitution box, taken from
    reference/XADMaster/Crypto/aestab.c's `sb_data` — the same 256
    bytes FIPS-197 tabulates, and the generator checks them against the
    standard construction (inverse in GF(2^8), then the affine map)
    rather than trusting the extraction.

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

# Since 2026-09-19 neither SP table is EMITTED: both are built at key setup,
# into a 2 KB heap block that lives only while an encrypted entry is
# decoded, from the S boxes and the inverse of P below (src/unc_crypt.c,
# crypt_build). What this generator still does is PROVE the run-time
# derivation against the references, because the StuffIt table's bit
# convention was fitted rather than transcribed: DES bit k of the round
# output sits at word bit (k - 1 + 3) mod 32 — the same rotate-by-3 the
# handle undoes at the end of a block — and the six-bit index takes the
# E-expansion bits in order, bit 0 first. Both derivations are asserted
# equal to the tables XADMaster carries, entry for entry.
PINV = [P.index(pos) + 1 for pos in range(1, 33)]   # pre-P bit -> after P


def sp_entry(box, v, sit):
    if sit:
        e = [(v >> i) & 1 for i in range(6)]
        row = (e[0] << 1) | e[5]
        col = (e[1] << 3) | (e[2] << 2) | (e[3] << 1) | e[4]
    else:
        row = ((v & 0x20) >> 4) | (v & 1)
        col = (v >> 1) & 0xF
    out = S[box][row * 16 + col]
    word = 0
    for b in range(4):
        if out & (8 >> b):
            dest = PINV[box * 4 + b]
            word |= 1 << ((dest + 2) % 32) if sit else 1 << (32 - dest)
    return word


assert all(sp_entry(b, v, False) == SP[b][v] for b in range(8) for v in range(64))
assert all(sp_entry(b, v, True) == SITSP[b][v] for b in range(8) for v in range(64)), \
    "the run-time derivation of DES_SPtrans does not match XADMaster's table"

# ---- AES, from reference/XADMaster/Crypto/aestab.c ---------------------
def aes_sbox():
    src = open("reference/XADMaster/Crypto/aestab.c").read()
    i = src.index("#define sb_data(w) {")
    nums = [int(x, 16)
            for x in re.findall(r"w\(0x([0-9a-f]{2})\)", src[i:i + 6000])]
    box = nums[:256]
    assert len(box) == 256 and len(set(box)) == 256

    # The same table, built the way FIPS-197 defines it: the
    # multiplicative inverse in GF(2^8) modulo x^8+x^4+x^3+x+1, then the
    # affine transform. Extraction and construction have to agree.
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
    built = []
    for x in range(256):
        v = inv[x] if x else 0
        r = v
        for _ in range(4):
            v = ((v << 1) | (v >> 7)) & 0xFF
            r ^= v
        built.append(r ^ 0x63)
    assert built == box, "the AES S box does not match its own definition"
    return box


AES_SBOX = aes_sbox()

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
# Not emitted either since 2026-09-19: src/unc_crypt.c builds it at key
# setup with the same eight-step loop, in two 32-bit halves.

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
    print(" * (DES_SPtrans, which the generator checks its derivation against)")
    print(" * and Crypto/md5.c (the STEP list).")
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
    print("/* The eight S boxes, box-major, 64 entries each indexed row*16+col;")
    print(" * and the P permutation INVERTED: for pre-P bit 1..32, where P")
    print(" * sends it. The two SP tables a round actually reads are built from")
    print(" * these at key setup (unc_crypt.c, crypt_build): 544 B resident")
    print(" * against 4,096 for the tables themselves. */")
    emit_u8("unc_des_s", [v for box in S for v in box], 16)
    emit_u8("unc_des_pinv", PINV, 8)
    print("/* AES: the substitution box. Only the FORWARD cipher is here —")
    print(" * WinZip's AES runs in counter mode, which encrypts to decrypt,")
    print(" * so the inverse box and inverse mix-columns are never used. */")
    emit_u8("unc_aes_sbox", AES_SBOX, 16)
    print("/* MD5: per-step message-word index, rotation and constant. */")
    emit_u8("unc_md5_x", MD5_X, 16)
    emit_u8("unc_md5_s", MD5_S, 16)
    emit_u32("unc_md5_t", MD5_T)
    print("#endif /* UNC_CRYPT_TABLES_H */")


main()
