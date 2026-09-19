#!/usr/bin/env python3
"""Why StuffItDES is standard DES, and where it is not.

XADStuffItDESHandle.m calls it "a modified DES that ROLs the input, does
the DES rounds without IP, then RORs the result. It also uses its own key
schedule", and carries a second S-box table, DES_SPtrans, in a different
bit order from the standard one. Until 2026-09-19 src/unc_crypt.c had all
of that: a second 2 KB table, a second round function, and revbits.

This tool establishes the three facts that let the round go, and the one
that keeps the key schedule. Run it from the repository root; it needs
reference/XADMaster (tools/fetch_references.sh) for step 2 only.

  1. The KEY SCHEDULE is not standard. sitdes_setkey reads all 64 key
     bits; PC-1 drops eight. No permutation of the key can turn one
     schedule into the other, so the nibble schedule stays as the format
     knowledge it is.
  2. The TABLE is a relabelling. DES_SPtrans[b][v] is the standard
     SP[b][rev6(v)] with its output word bit-reversed and rotated left
     three — checked against XADMaster's verbatim table, entry for entry.
  3. Given 2, the subkeys fall out of the nibble schedule as plain
     six-bit groups, with no bit reversal at all.
  4. So the two formulations agree, on 20,000 random key/block pairs and
     on every single-bit key and block.

DECISIONS.md 2026-09-19, *the DES that was only wearing a disguise*.
"""
import random
import re
import sys

H = open("src/crypt_tables.h").read()
M = 0xFFFFFFFF


def tab(name, n):
    i = H.index("unc_" + name + "[")
    j = H.index("{", i)
    k = H.index("};", j)
    v = [int(x) for x in re.findall(r"\d+", H[j:k])]
    assert len(v) == n, (name, len(v))
    return v


PC1C, PC1D = tab("des_pc1c", 28), tab("des_pc1d", 28)
PC2, SHIFTS = tab("des_pc2", 48), tab("des_shifts", 16)
S, PINV = tab("des_s", 512), tab("des_pinv", 32)


def rotl(v, n):
    return v if n == 0 else ((v << n) | (v >> (32 - n))) & M


def revbits(v):
    r = 0
    for _ in range(32):
        r = (r << 1) | (v & 1)
        v >>= 1
    return r


def rev6(v):
    return sum(((v >> i) & 1) << (5 - i) for i in range(6))


def nib(key, n):
    """Nibble n of the key, high nibble of byte 0 first."""
    return (key[(n & 0x0F) >> 1] >> (((n ^ 1) & 1) << 2)) & 0x0F


# --------------------------------------------------------------- the tables
def sp_entry(box, v, sit):
    if sit:
        e = [(v >> i) & 1 for i in range(6)]
        row = (e[0] << 1) | e[5]
        col = (e[1] << 3) | (e[2] << 2) | (e[3] << 1) | e[4]
    else:
        row, col = ((v & 0x20) >> 4) | (v & 1), (v >> 1) & 0xF
    out = S[box * 64 + row * 16 + col]
    w = 0
    for b in range(4):
        if out & (8 >> b):
            dest = PINV[box * 4 + b]
            w |= (1 << ((dest + 2) % 32)) if sit else (1 << (32 - dest))
    return w


SP = [[sp_entry(b, v, False) for v in range(64)] for b in range(8)]
SPSIT = [[sp_entry(b, v, True) for v in range(64)] for b in range(8)]

# ------------------------------------------------- 1. the key schedule is not
def sitdes_setkey_old(key):
    """The formulation this engine carried until 2026-09-19."""
    ks = []
    for i in range(16):
        s1 = (nib(key, i) >> 2) | (nib(key, i + 13) << 2)
        s1 |= ((nib(key, i + 11) >> 2) | (nib(key, i + 6) << 2)) << 8
        s1 |= ((nib(key, i + 3) >> 2) | (nib(key, i + 10) << 2)) << 16
        s1 |= ((nib(key, i + 8) >> 2) | (nib(key, i + 1) << 2)) << 24
        s0 = (nib(key, i + 9) | (nib(key, i) << 4)) & 0x3F
        s0 |= ((nib(key, i + 2) | (nib(key, i + 11) << 4)) & 0x3F) << 8
        s0 |= ((nib(key, i + 14) | (nib(key, i + 3) << 4)) & 0x3F) << 16
        s0 |= ((nib(key, i + 5) | (nib(key, i + 8) << 4)) & 0x3F) << 24
        ks.append((revbits(s1), revbits(s0)))
    return ks


def std_setkey(key):
    """16 x 48 subkey bits, slot j being PC-2 output j."""
    def bit(n):
        return (key[(n - 1) >> 3] >> (7 - ((n - 1) & 7))) & 1

    c = d = 0
    for i in range(28):
        c, d = (c << 1) | bit(PC1C[i]), (d << 1) | bit(PC1D[i])
    out = []
    for r in range(16):
        s = SHIFTS[r]
        c = ((c << s) | (c >> (28 - s))) & 0x0FFFFFFF
        d = ((d << s) | (d >> (28 - s))) & 0x0FFFFFFF
        out.append([(c >> (28 - b)) & 1 if b <= 28 else (d >> (56 - b)) & 1
                    for b in PC2])
    return out


def key_bits_used(setkey, slots=None):
    n = 0
    for p in range(64):
        key = [0] * 8
        key[p >> 3] = 1 << (7 - (p & 7))
        m = setkey(key)
        if slots:
            m = slots(m)
        if any(any(row) for row in m):
            n += 1
    return n


def sit_slots(ks):
    """The old formulation's subkey words, in standard slot numbering.

    sitdes_round indexed box 2g with bits 8g+2..8g+7 of subkey[0] and box
    2g+1 with the same bits of subkey[1]; index bit i is the standard
    group's bit b(i+1), i.e. PC-2 slot 6*box + i.
    """
    out = []
    for r in range(16):
        row = [0] * 48
        for g in range(4):
            for i in range(6):
                sh = 8 * g + 2 + i
                row[6 * (2 * g) + i] = (ks[r][0] >> sh) & 1
                row[6 * (2 * g + 1) + i] = (ks[r][1] >> sh) & 1
        out.append(row)
    return out


sit_used = key_bits_used(sitdes_setkey_old, sit_slots)
std_used = key_bits_used(std_setkey)
print("1. key bits read: StuffIt %d, standard DES %d" % (sit_used, std_used))
assert sit_used == 64 and std_used == 56
print("   so no permutation of the key makes one schedule the other: the")
print("   nibble schedule is format knowledge and stays.")

# ------------------------------------------------ 2. the table is a relabelling
try:
    src = open("reference/XADMaster/XADStuffItDESHandle.m").read()
except IOError:
    print("2. SKIPPED — no reference/XADMaster (tools/fetch_references.sh)")
    src = None
if src:
    i = src.index("DES_SPtrans[8][64]=")
    j, depth, k = src.index("{", i), 0, src.index("{", i)
    while True:
        depth += (src[k] == "{") - (src[k] == "}")
        if depth == 0:
            break
        k += 1
    nums = [int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{8})", src[j:k])]
    assert len(nums) == 512, len(nums)
    XAD = [nums[b * 64:(b + 1) * 64] for b in range(8)]
    assert XAD == SPSIT, "the derivation of DES_SPtrans no longer matches"
    assert all(XAD[b][v] == rotl(revbits(SP[b][rev6(v)]), 3)
               for b in range(8) for v in range(64)), \
        "DES_SPtrans is not the standard table relabelled"
    print("2. DES_SPtrans[b][v] == ROL(REV(SP[b][rev6(v)]), 3): 512 entries")

# ----------------------------------- 3 and 4. the two formulations, A/B'd
def sitdes_setkey_new(key):
    """What src/unc_crypt.c does now: standard six-bit groups.

    Group 2g is s1's lane 3-g and group 2g+1 is s0's — which is what the
    bit reversal in the old formulation was undoing.
    """
    return [[(nib(key, i + 8) >> 2) | (nib(key, i + 1) << 2),
             (nib(key, i + 5) | (nib(key, i + 8) << 4)) & 0x3F,
             (nib(key, i + 3) >> 2) | (nib(key, i + 10) << 2),
             (nib(key, i + 14) | (nib(key, i + 3) << 4)) & 0x3F,
             (nib(key, i + 11) >> 2) | (nib(key, i + 6) << 2),
             (nib(key, i + 2) | (nib(key, i + 11) << 4)) & 0x3F,
             (nib(key, i) >> 2) | (nib(key, i + 13) << 2),
             (nib(key, i + 9) | (nib(key, i) << 4)) & 0x3F] for i in range(16)]


def old_crypt(data, key, enc):
    def rnd(left, right, sk):
        u, t = right ^ sk[0], rotl(right, 28) ^ sk[1]
        return left ^ (
            SPSIT[0][(u >> 2) & 0x3F] ^ SPSIT[2][(u >> 10) & 0x3F] ^
            SPSIT[4][(u >> 18) & 0x3F] ^ SPSIT[6][(u >> 26) & 0x3F] ^
            SPSIT[1][(t >> 2) & 0x3F] ^ SPSIT[3][(t >> 10) & 0x3F] ^
            SPSIT[5][(t >> 18) & 0x3F] ^ SPSIT[7][(t >> 26) & 0x3F])

    ks = sitdes_setkey_old(key)
    left = rotl(revbits(int.from_bytes(data[0:4], "big")), 3)
    right = rotl(revbits(int.from_bytes(data[4:8], "big")), 3)
    order = range(0, 16, 2) if enc else range(15, 0, -2)
    step = 1 if enc else -1
    for i in order:
        left = rnd(left, right, ks[i])
        right = rnd(right, left, ks[i + step])
    left, right = rotl(left, 29), rotl(right, 29)
    return revbits(right).to_bytes(4, "big") + revbits(left).to_bytes(4, "big")


def new_crypt(data, key, enc):
    """DES's own round function, no IP, no FP."""
    ks = sitdes_setkey_new(key)
    l, r = int.from_bytes(data[0:4], "big"), int.from_bytes(data[4:8], "big")
    for rd in range(16):
        sk = ks[rd if enc else 15 - rd]
        f = 0
        for g in range(8):
            f ^= SP[g][((rotl(r, (4 * g + 31) & 31) >> 26) & 0x3F) ^ sk[g]]
        l, r = r, l ^ f
    return r.to_bytes(4, "big") + l.to_bytes(4, "big")


random.seed(1)
bad = 0
for n in range(20000):
    key = bytes(random.randrange(256) for _ in range(8))
    blk = bytes(random.randrange(256) for _ in range(8))
    enc = random.randrange(2)
    if old_crypt(blk, key, enc) != new_crypt(blk, key, enc):
        bad += 1
print("3. random key/block pairs: %d, disagreements: %d" % (n + 1, bad))

edges = [bytes(8), bytes([0xFF] * 8)] + \
        [bytes(1 << (7 - (p & 7)) if q == p >> 3 else 0 for q in range(8))
         for p in range(64)]
for key in edges:
    for blk in edges:
        for enc in (0, 1):
            if old_crypt(blk, key, enc) != new_crypt(blk, key, enc):
                bad += 1
print("4. every single-bit key x single-bit block, both directions: %s"
      % ("all agree" if bad == 0 else "%d DISAGREE" % bad))
sys.exit(1 if bad else 0)
