#!/usr/bin/env python3
"""Generate src/crypt_tables.h — the constant tables the ciphers need.

Every table below is read out of a named source, never from memory:

  * The standard-DES tables (IP, IP^-1, PC-1, PC-2, the shift schedule,
    the S boxes and P) are read out of the STANDARD, reference/notes/
    fips46-3.pdf, rather than out of anyone's implementation of it.  Each
    is re-segmented under its own permutation constraint, because PDF
    text loses kerning and splits some entries; see below.  They were
    taken from reference/XADMaster/Crypto/des.c until 2026-09-23, and
    the swap left src/crypt_tables.h byte for byte identical
    (DECISIONS.md 2026-09-23, *the tables that were the standard's*).

  * The MD5 tables are the per-step constants, rotation counts and
    message-word indices of RFC 1321 (reference/notes/rfc1321.txt), read
    out of the 64 round calls of the RFC's own reference implementation
    so the loop here can be a loop.  The RFC states its constants twice —
    as literals and as the integer part of 4294967296*abs(sin(i)) — and
    both are used, the second asserted to reproduce the first.  They came
    from reference/XADMaster/Crypto/md5.c until 2026-09-23, which is now
    read only to agree (DECISIONS.md 2026-09-23, *the third statement of
    the same constants*).

  * `unc_aes_sbox` is the AES substitution box, BUILT here the way
    FIPS-197 defines it (inverse in GF(2^8), then the affine map) and
    checked against reference/XADMaster/Crypto/aestab.c's `sb_data`,
    which it had been taken from until 2026-09-23.  Emitting the
    construction rather than the extraction changes no byte and leaves
    the check exactly where it was.

  * `unc_cpt_crc64` is the byte table of the 64-bit CRC Compact Pro
    keys its cipher with. There is no reference implementation and no
    published description of that cipher: it was read out of Compact
    Pro 1.51's own `CODE` 3, where the routine at 0x408e builds this
    table with the polynomial 0xEDB88320EDB88320 — CRC-32's reflected
    polynomial in both halves — and the routine at 0x40fe seeds the
    state with 0x0123456789ABCDEF. DECISIONS.md 2026-08-23.

  * There is no StuffIt table any more. DES_SPtrans from
    reference/XADMaster/XADStuffItDESHandle.m is the standard table
    relabelled, so the StuffIt variant reads the standard one; the
    relation is asserted below and proved in full by
    tools/fit_sitdes.py.

Run: python3 tools/gen_crypt_tables.py > src/crypt_tables.h
"""
import math
import re

SITREF = "reference/XADMaster/XADStuffItDESHandle.m"


# ---- standard DES, from the published FIPS 46-3 -------------------------
# reference/notes/fips46-3.pdf, the 1999-10-25 reaffirmation.  Its text
# streams are Flate; PDF text carries no inter-glyph kerning, so some
# multi-digit entries arrive split ("43" -> "4 3").  Every table below is
# a permutation of a known set over a known span — the whole table for the
# permutations, each row of sixteen for the S boxes — so the split is
# repaired by re-segmenting under that constraint, and the reading is
# asserted UNIQUE.  The shift schedule is the one table that is not a
# permutation; it is read as pairs, below.
FIPS = "reference/notes/fips46-3.pdf"


def fips_text(path):
    import zlib
    lits = []
    for s in re.findall(rb"stream\r?\n(.*?)endstream", open(path, "rb").read(),
                        re.S):
        try:
            u = zlib.decompress(s)
        except Exception:
            continue
        lits += [l[1:-1] for l in re.findall(rb"\((?:[^()\\]|\\.)*\)", u)]
    return b" ".join(lits).decode("latin-1")


FIPSTXT = fips_text(FIPS)


def fips_tokens(anchor, start=0):
    """The digit run following `anchor`, one token per printed group."""
    toks = []
    for m in re.finditer(r"\S+", FIPSTXT[FIPSTXT.index(anchor, start) +
                                         len(anchor):]):
        if m.group().isdigit():
            toks.append(m.group())
        elif toks:
            break
    return toks


def fips_table(anchor, n, values, span=0, start=0):
    """`n` numbers from `values`, distinct within each `span` of them."""
    toks, sols, span = fips_tokens(anchor, start), [], span or n

    def rec(k, acc, used):
        if len(acc) == n:
            sols.append((acc, k))
            return
        if k >= len(toks) or len(sols) > 1:
            return
        if len(acc) % span == 0:
            used = set()
        s = ""
        for j in range(k, min(k + 2, len(toks))):
            s += toks[j]
            if len(s) > 2:
                break
            v = int(s)
            if v in values and v not in used:
                rec(j + 1, acc + [v], used | {v})

    rec(0, [], set())
    assert len(sols) == 1, ("not a unique reading of " + anchor, len(sols))
    # What the table does not use must not look like an entry of it: the
    # runs carry the odd page number (S4's is 18), never a stray value.
    assert not [t for t in toks[sols[0][1]:] if int(t) in values], anchor
    return sols[0][0]


IP = fips_table("called the initial permutation  IP : IP", 64, range(1, 65))
FP_PUB = fips_table("inverse of the initial permutation: IP -1", 64,
                    range(1, 65))
PC1 = fips_table("Permuted choice 1 is determined by the following table: "
                 "PC -1", 56, range(1, 65))
PC1_C, PC1_D = PC1[:28], PC1[28:]
PC2 = fips_table("Permuted choice 2 is determined by the following table: "
                 "PC -2", 48, range(1, 57))
P = fips_table("defined by the following table: P", 32, range(1, 33))

# Appendix 1, eight selection functions of four rows each.
S, _at = [], FIPSTXT.index("S 1 14 4 13")
for _b in range(8):
    _at = FIPSTXT.index("S %d " % (_b + 1), _at)
    S.append(fips_table("S %d " % (_b + 1), 64, range(0, 16), span=16,
                        start=_at))
    _at += 4

# The schedule prints as sixteen (iteration, shift) pairs, and is the one
# table a permutation cannot check: assert the iteration column instead.
_pairs = [int(t) for t in fips_tokens("Iteration        Number of Number "
                                      "        Left Shifts")[:32]]
assert _pairs[0::2] == list(range(1, 17)), _pairs[0::2]
SHIFTS = _pairs[1::2]
assert set(SHIFTS) == {1, 2}, SHIFTS

assert sorted(IP) == list(range(1, 65))

FP = [0] * 64
for k, src_bit in enumerate(IP):
    FP[src_bit - 1] = k + 1
assert FP == FP_PUB, "the derived IP^-1 is not the published one"

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

# Since 2026-09-19 no SP table is EMITTED: the one that is left is built at
# key setup, into a 2 KB heap block that lives only while an encrypted entry
# is decoded, from the S boxes and the inverse of P below (src/unc_crypt.c,
# crypt_build). What this generator still does is PROVE that derivation
# against the reference, entry for entry.
PINV = [P.index(pos) + 1 for pos in range(1, 33)]   # pre-P bit -> after P


def sp_entry(box, v):
    row = ((v & 0x20) >> 4) | (v & 1)
    col = (v >> 1) & 0xF
    out = S[box][row * 16 + col]
    word = 0
    for b in range(4):
        if out & (8 >> b):
            word |= 1 << (32 - PINV[box * 4 + b])
    return word


assert all(sp_entry(b, v) == SP[b][v] for b in range(8) for v in range(64))

# And that the StuffIt variant needs no table of its own: DES_SPtrans is
# this table with its six-bit index bit-reversed and its output word
# bit-reversed and rotated left three — a relabelling of the round, which
# StuffItDES applies to the state and undoes at the end of the block. That
# is why src/unc_crypt.c has one DES and not two. The A/B of the two
# formulations, and the reason the KEY SCHEDULE is not standard either, are
# tools/fit_sitdes.py; DECISIONS.md 2026-09-19.
def _rev(v, n):
    return sum(((v >> i) & 1) << (n - 1 - i) for i in range(n))


assert all(SITSP[b][v] ==
           ((_rev(SP[b][_rev(v, 6)], 32) << 3) |
            (_rev(SP[b][_rev(v, 6)], 32) >> 29)) & 0xFFFFFFFF
           for b in range(8) for v in range(64)), \
    "DES_SPtrans is not the standard SP table relabelled"

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
    return built


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

# ---- MD5, from RFC 1321 -------------------------------------------------
# reference/notes/rfc1321.txt.  The RFC's own reference implementation
# states each of the 64 steps as FF/GG/HH/II(a, b, c, d, x[k], Sxx, T) —
# message-word index, shift macro and constant — and defines the shift
# macros above them.  Two statements of the constants are in the document
# and both are used: the literals, and section 3.4's "integer part of
# 4294967296 times abs(sin(i))", which is asserted to reproduce them.
MD5REF = "reference/notes/rfc1321.txt"
_rfc = open(MD5REF).read()
_shifts = {m[0]: int(m[1]) for m in re.findall(r"#define (S\d\d) (\d+)", _rfc)}
_calls = re.findall(r"\b(FF|GG|HH|II)\s*\(\s*\w+,\s*\w+,\s*\w+,\s*\w+,"
                    r"\s*x\[\s*(\d+)\s*\],\s*(S\d\d),\s*(0x[0-9a-fA-F]+)\s*\)",
                    _rfc, re.S)
assert len(_shifts) == 16 and len(_calls) == 64, (len(_shifts), len(_calls))
assert [c[0] for c in _calls] == ["FF"] * 16 + ["GG"] * 16 + ["HH"] * 16 + \
    ["II"] * 16
MD5_X = [int(c[1]) for c in _calls]
MD5_S = [_shifts[c[2]] for c in _calls]
MD5_T = [int(c[3], 16) for c in _calls]
assert MD5_T == [int(abs(math.sin(i + 1)) * 2 ** 32) & 0xFFFFFFFF
                 for i in range(64)], "RFC 1321's constants are not its sines"

# And a third statement, from an implementation that is not the RFC's:
# XADMaster's Crypto/md5.c (Solar Designer, public domain), whose unrolled
# STEP list this generator read until 2026-09-23.  Nothing is emitted from
# it; it only has to agree.
_steps = re.findall(
    r"STEP\((\w+), (\w), (\w), (\w), (\w), (?:SET|GET)\((\d+)\), "
    r"(0x[0-9a-f]+), (\d+)\)",
    open("reference/XADMaster/Crypto/md5.c").read())
assert len(_steps) == 64, len(_steps)
assert MD5_X == [int(s[5]) for s in _steps]
assert MD5_S == [int(s[7]) for s in _steps]
assert MD5_T == [int(s[6], 16) for s in _steps]
# The (a,b,c,d) rotation is the same in every step, which is what lets the
# loop in unc_crypt.c replace this list.
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
    print(" * Source: the standards themselves. FIPS 46-3")
    print(" * (reference/notes/fips46-3.pdf) for IP, IP^-1, PC-1, PC-2, the")
    print(" * shift schedule, S and P; RFC 1321 (reference/notes/rfc1321.txt)")
    print(" * for MD5's three; FIPS-197's own definition, constructed here,")
    print(" * for the AES S box. Nothing below is derived from XADMaster:")
    print(" * its XADStuffItDESHandle.m (DES_SPtrans), Crypto/md5.c (the")
    print(" * STEP list) and Crypto/aestab.c (sb_data) are read only to")
    print(" * agree with what the standards give.")
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
