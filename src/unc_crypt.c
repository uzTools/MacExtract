/*
 * unc_crypt.c — the ciphers the encrypting formats use, and the layer
 * that puts one underneath a decoder.
 *
 * Seven schemes across the five formats that can encrypt an entry:
 *
 *   ARC          a plain repeating XOR of the password over the
 *                compressed bytes (XADXORHandle).
 *   PackIt PMa5  an XOR too, but the key is the password run through
 *                DES's PC-1 permutation and then applied modulo SEVEN
 *                over an eight-byte key (XADPackItXORHandle — the
 *                modulus is the original's and is kept).
 *   PackIt PMa6  DES in ECB, decrypting eight bytes at a time.
 *   StuffIt      a two-stage thing: standard DES with no IP/FP and its
 *   classic      own key schedule ("StuffItDES") derives a per-file key
 *                from the password, the archive's 'MKey' resource and a
 *                per-entry key stored after the fork; the fork itself is
 *                then decrypted by an eight-byte feedback XOR built from
 *                that key.
 *   StuffIt 5    RC4, keyed by MD5(password) truncated to five bytes
 *                followed by the entry's own five key bytes.
 *   zip          PKWARE's stream cipher, three CRC-32-driven keys
 *                updated from each plaintext byte.
 *   zip, AES     WinZip's: PBKDF2-HMAC-SHA1 over a salt in the entry,
 *                AES in counter mode (which encrypts to decrypt, so
 *                only the forward cipher is here), and ten bytes of
 *                HMAC-SHA1 over the ciphertext, which is the only
 *                check an AE-2 entry carries.
 *   Compact Pro  a 64-bit CRC register, seeded 0x0123456789ABCDEF,
 *                folded over the password and then over each PLAINTEXT
 *                byte; the keystream is the register's second byte.
 *                No reference implementation of this exists and no
 *                description has ever been published — The
 *                Unarchiver's own format notes say "the algorithm for
 *                this is unknown". It was read out of Compact Pro
 *                1.51's `CODE` 3: the key at 0x1892, the table at
 *                0x408e, the seed at 0x40fe, the encrypt loop at
 *                0x1152 and the decrypt loop at 0x1f08 — and then
 *                graded by that application, both ways (FORMATS.md,
 *                *Compact Pro's cipher*). The eight-byte preamble an
 *                encrypted entry opens with is fmt_cpt.c's business,
 *                not this file's. DECISIONS.md 2026-08-23.
 *
 * Sources: FIPS 46-3 for DES itself, which is now the whole of both DES
 * ciphers here — StuffIt's variant is that round function and no other
 * (see *StuffItDES* below); reference/XADMaster/XADStuffItDESHandle.m
 * for what remains format knowledge, the nibble key schedule and the
 * derivation the three real archives grade; XADStuffIt5Parser.m +
 * XADRC4Handle.m, XADPackItParser.m (both PackIt handles), XADZipCryptHandle.m,
 * XADXORHandle.m, and reference/XADMaster/Crypto/des.c + md5.c for the
 * standard DES and MD5 tables, which src/crypt_tables.h carries
 * precomputed (this engine may not have global mutable state, and that
 * DES builds its tables at runtime). LGPL — see NOTICE.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"
#include "crypt_tables.h"

/* ------------------------------------------------------------------ */
/* Standard DES (PackIt PMa6, and nothing else)                        */
/*                                                                    */
/* Bit numbering is DES's own: bit 1 is the most significant bit of    */
/* the first byte. The S boxes come merged with the P permutation, so  */
/* a round is eight lookups; the two outer permutations are done bit   */
/* by bit, which costs 128 steps a block and is why this is not the    */
/* cipher anything large is encrypted with. PMa6 archives are floppy   */
/* sized and rare.                                                    */
/* ------------------------------------------------------------------ */

static uint32_t rotl32(uint32_t v, int n)
{
    return n == 0 ? v : ((v << n) | (v >> (32 - n)));
}

static uint32_t rotr32(uint32_t v, int n)
{
    return n == 0 ? v : ((v >> n) | (v << (32 - n)));
}

/* Bit `n` (1-based) of an 8-byte block. */
static uint32_t bit_at(const uint8_t *b, int n)
{
    return (uint32_t)((b[(n - 1) >> 3] >> (7 - ((n - 1) & 7))) & 1);
}

/* ------------------------------------------------------------------ */
/* The tables a round reads, built when a key is set                   */
/*                                                                    */
/* DES reads the S boxes merged with P as eight 64-entry words, and     */
/* Compact Pro's cipher reads a 256-entry table of 64-bit CRC steps.    */
/* That is 2 KB each, and as const data it sat in the A5 world — which  */
/* costs the engine its budget one for one, on every extraction, for   */
/* entries the corpus does not have one of. So they are built HERE,    */
/* into a 2 KB heap block that lives as long as the entry's other      */
/* buffers, from the 512 B of S boxes and 32 B of inverted P that      */
/* crypt_tables.h keeps.                                              */
/*                                                                    */
/* There is ONE DES table, not two. Until 2026-09-19 StuffItDES had a  */
/* second one in a different bit order; tools/fit_sitdes.py shows that */
/* order is a relabelling rather than a cipher, so the variant reads   */
/* this table (see *StuffItDES* below). DECISIONS.md 2026-09-19.       */
/* ------------------------------------------------------------------ */

#define UNC_CRYPT_TAB_WORDS 512u

enum { CRYPT_TAB_NONE = 0, CRYPT_TAB_DES, CRYPT_TAB_CRC64 };

static uint32_t des_sp_entry(int box, int v)
{
    int row = ((v & 0x20) >> 4) | (v & 1);
    int col = (v >> 1) & 0xF;
    int out = unc_des_s[box * 64 + row * 16 + col];
    uint32_t w = 0;
    int b;

    for (b = 0; b < 4; b++) {
        if (out & (8 >> b)) {
            int dest = unc_des_pinv[box * 4 + b];        /* 1..32 */
            w |= 1u << (32 - dest);
        }
    }
    return w;
}

static void crypt_build(uint32_t *tab, int kind)
{
    int i, j;

    if (kind == CRYPT_TAB_CRC64) {
        /* Compact Pro 1.51 `CODE` 3 @0x408e, as an algorithm: eight
         * reflected steps of a 64-bit CRC with 0xEDB88320 in both
         * halves, in two 32-bit registers (68000 discipline). */
        for (i = 0; i < 256; i++) {
            uint32_t hi = 0, lo = 0, v = (uint32_t)i;
            for (j = 0; j < 8; j++) {
                uint32_t fb = (lo ^ v) & 1u;
                lo = (lo >> 1) | ((hi & 1u) << 31);
                hi >>= 1;
                if (fb) { hi ^= 0xEDB88320u; lo ^= 0xEDB88320u; }
                v >>= 1;
            }
            tab[2 * i] = hi;
            tab[2 * i + 1] = lo;
        }
    } else {
        for (i = 0; i < 8; i++)
            for (j = 0; j < 64; j++)
                tab[i * 64 + j] = des_sp_entry(i, j);
    }
}

/* Make sure cr->tab holds `kind`, allocating it on first use. */
static int crypt_table(UncCrypt *cr, UncAlloc *al, int kind)
{
    if (!cr->tab) {
        cr->tab = (uint32_t *)unc_alloc(al, UNC_CRYPT_TAB_WORDS * 4u);
        if (!cr->tab) return UNC_ERR_MEM;
        cr->tabkind = CRYPT_TAB_NONE;
    }
    if (cr->tabkind != kind) {
        crypt_build(cr->tab, kind);
        cr->tabkind = kind;
    }
    return UNC_OK;
}

void unc_crypt_free(UncCrypt *cr, UncAlloc *al)
{
    unc_free(al, cr->tab);
    cr->tab = NULL;
    cr->tabkind = CRYPT_TAB_NONE;
}

static void des_setkey(uint8_t ks[16][8], const uint8_t key[8])
{
    uint32_t c = 0, d = 0;
    int i, r, j;

    for (i = 0; i < 28; i++) {
        c = (c << 1) | bit_at(key, unc_des_pc1c[i]);
        d = (d << 1) | bit_at(key, unc_des_pc1d[i]);
    }
    for (r = 0; r < 16; r++) {
        int s = unc_des_shifts[r];
        c = ((c << s) | (c >> (28 - s))) & 0x0FFFFFFFu;
        d = ((d << s) | (d >> (28 - s))) & 0x0FFFFFFFu;
        for (j = 0; j < 8; j++) ks[r][j] = 0;
        for (j = 0; j < 48; j++) {
            int b = unc_des_pc2[j];
            uint32_t v = b <= 28 ? (c >> (28 - b)) & 1 : (d >> (56 - b)) & 1;
            ks[r][j / 6] = (uint8_t)(((uint32_t)ks[r][j / 6] << 1) | v);
        }
    }
}

/* The sixteen rounds, and nothing else: standard DES is this between IP
 * and FP, StuffItDES is this alone. On return `*lp` is L16 and `*rp` is
 * R16, so the preoutput a caller writes is R16 then L16. */
static void des_core(uint32_t *lp, uint32_t *rp, uint8_t ks[16][8],
                     int decrypt, const uint32_t *sp)
{
    uint32_t l = *lp, r = *rp;
    int round;

    for (round = 0; round < 16; round++) {
        const uint8_t *sk = ks[decrypt ? 15 - round : round];
        uint32_t f = 0, t;
        int g;
        for (g = 0; g < 8; g++) {
            /* The E expansion picks bits 4g, 4g+1 .. 4g+5 (1-based, and
             * 0 means 32), which is a rotate and a shift. */
            uint32_t e = (rotl32(r, (4 * g + 31) & 31) >> 26) & 0x3Fu;
            f ^= sp[g * 64 + (int)(e ^ sk[g])];
        }
        t = r;
        r = l ^ f;
        l = t;
    }
    *lp = l;
    *rp = r;
}

static void des_crypt(uint8_t ks[16][8], uint8_t block[8], int decrypt,
                      const uint32_t *sp)
{
    uint32_t l = 0, r = 0;
    uint8_t pre[8];
    int i;

    for (i = 0; i < 32; i++) l = (l << 1) | bit_at(block, unc_des_ip[i]);
    for (i = 32; i < 64; i++) r = (r << 1) | bit_at(block, unc_des_ip[i]);

    des_core(&l, &r, ks, decrypt, sp);

    /* Preoutput is R16 L16 — the final swap. */
    pre[0] = (uint8_t)(r >> 24); pre[1] = (uint8_t)(r >> 16);
    pre[2] = (uint8_t)(r >> 8);  pre[3] = (uint8_t)r;
    pre[4] = (uint8_t)(l >> 24); pre[5] = (uint8_t)(l >> 16);
    pre[6] = (uint8_t)(l >> 8);  pre[7] = (uint8_t)l;

    for (i = 0; i < 8; i++) block[i] = 0;
    for (i = 0; i < 64; i++)
        block[i >> 3] = (uint8_t)(block[i >> 3] |
                                  (bit_at(pre, unc_des_fp[i]) << (7 - (i & 7))));
}

/* ------------------------------------------------------------------ */
/* StuffItDES                                                          */
/*                                                                    */
/* "A modified DES that ROLs the input, does the DES rounds without    */
/* IP, then RORs the result. It also uses its own key schedule." —     */
/* XADStuffItDESHandle.m. That description is exact, and since         */
/* 2026-09-19 only its second sentence is code here: the rotate, the   */
/* bit reversal and the second S-box table were one relabelling of     */
/* standard DES's round, applied to the state and undone at the end of */
/* the block, so the rounds ARE des_core above.                        */
/*                                                                    */
/* Two facts carry it, both machine-checked by tools/fit_sitdes.py:    */
/* XADMaster's DES_SPtrans[b][v] equals ROL(REV(SP[b][rev6(v)]), 3)    */
/* entry for entry, and with the state held in the standard layout the */
/* subkeys fall out of the nibble schedule as plain six-bit groups —   */
/* group 2g is s1's lane 3-g, group 2g+1 is s0's, which is why no      */
/* revbits survives. The same tool A/Bs the two formulations over      */
/* 20,000 random key/block pairs and every single-bit case.            */
/*                                                                    */
/* What is NOT standard DES, and is kept as the format knowledge it    */
/* is, is the schedule below — it reads all 64 key bits where PC-1     */
/* drops eight, so no permutation of the key can turn one into the     */
/* other (DECISIONS.md 2026-09-19, *the DES that was only wearing a    */
/* disguise*). Used only to derive keys: a handful of blocks per       */
/* archive.                                                           */
/* ------------------------------------------------------------------ */

static uint32_t sit_nibble(const uint8_t key[8], int n)
{
    return (uint32_t)((key[(n & 0x0f) >> 1] >> (((n ^ 1) & 1) << 2)) & 0x0f);
}

/* The nibble schedule, straight into standard six-bit subkey groups. */
static void sitdes_setkey(const uint8_t key[8], uint8_t ks[16][8])
{
    int i;
    for (i = 0; i < 16; i++) {
        ks[i][0] = (uint8_t)((sit_nibble(key, i + 8) >> 2) |
                             (sit_nibble(key, i + 1) << 2));
        ks[i][1] = (uint8_t)((sit_nibble(key, i + 5) |
                              (sit_nibble(key, i + 8) << 4)) & 0x3f);
        ks[i][2] = (uint8_t)((sit_nibble(key, i + 3) >> 2) |
                             (sit_nibble(key, i + 10) << 2));
        ks[i][3] = (uint8_t)((sit_nibble(key, i + 14) |
                              (sit_nibble(key, i + 3) << 4)) & 0x3f);
        ks[i][4] = (uint8_t)((sit_nibble(key, i + 11) >> 2) |
                             (sit_nibble(key, i + 6) << 2));
        ks[i][5] = (uint8_t)((sit_nibble(key, i + 2) |
                              (sit_nibble(key, i + 11) << 4)) & 0x3f);
        ks[i][6] = (uint8_t)((sit_nibble(key, i) >> 2) |
                             (sit_nibble(key, i + 13) << 2));
        ks[i][7] = (uint8_t)((sit_nibble(key, i + 9) |
                              (sit_nibble(key, i) << 4)) & 0x3f);
    }
}

/* DES with no IP and no FP: the block IS L0 R0, and the preoutput is
 * the answer. `enc` runs the subkeys forwards, which is what des_core
 * calls NOT decrypting. */
static void sitdes_crypt(uint8_t data[8], uint8_t ks[16][8], int enc,
                         const uint32_t *sp)
{
    uint32_t l = unc_get_u32be(&data[0]);
    uint32_t r = unc_get_u32be(&data[4]);

    des_core(&l, &r, ks, !enc, sp);

    unc_put_u32be(&data[0], r);
    unc_put_u32be(&data[4], l);
}

/* ------------------------------------------------------------------ */
/* MD5 (StuffIt 5's key derivation, and nothing else)                  */
/* Source: reference/XADMaster/Crypto/md5.c — its unrolled STEP list is */
/* src/crypt_tables.h's three tables. Public domain; see NOTICE.        */
/* ------------------------------------------------------------------ */

static void md5_block(uint32_t abcd[4], const uint8_t *p)
{
    uint32_t x[16], a = abcd[0], b = abcd[1], c = abcd[2], d = abcd[3];
    int i;

    for (i = 0; i < 16; i++) x[i] = unc_get_u32le(p + 4 * i);

    for (i = 0; i < 64; i++) {
        uint32_t f, t;
        if (i < 16)      f = (b & c) | (~b & d);
        else if (i < 32) f = (d & b) | (~d & c);
        else if (i < 48) f = b ^ c ^ d;
        else             f = c ^ (b | ~d);
        t = a + f + x[unc_md5_x[i]] + unc_md5_t[i];
        a = d;
        d = c;
        c = b;
        b = b + rotl32(t, unc_md5_s[i]);
    }

    abcd[0] += a;
    abcd[1] += b;
    abcd[2] += c;
    abcd[3] += d;
}

/* One-shot MD5 of a short message (the only kind this engine hashes:
 * a password, then a 5-byte digest). `len` under 56 fits one block
 * with its padding, which is all StuffIt 5 ever needs — a longer
 * password takes the loop below. */
void unc_md5(const uint8_t *msg, uint32_t len, uint8_t out[16])
{
    uint32_t abcd[4];
    uint8_t block[64];
    uint32_t i, done = 0;

    abcd[0] = 0x67452301u; abcd[1] = 0xefcdab89u;
    abcd[2] = 0x98badcfeu; abcd[3] = 0x10325476u;

    while (len - done >= 64) {
        md5_block(abcd, msg + done);
        done += 64;
    }
    for (i = 0; i < 64; i++) block[i] = 0;
    for (i = 0; done + i < len; i++) block[i] = msg[done + i];
    block[i++] = 0x80;
    if (i > 56) {                 /* padding needs a block of its own */
        md5_block(abcd, block);
        for (i = 0; i < 64; i++) block[i] = 0;
    }
    /* Length in BITS, little-endian. 32 bits is the whole range here. */
    block[56] = (uint8_t)(len << 3);
    block[57] = (uint8_t)(len >> 5);
    block[58] = (uint8_t)(len >> 13);
    block[59] = (uint8_t)(len >> 21);
    block[60] = (uint8_t)(len >> 29);
    md5_block(abcd, block);

    for (i = 0; i < 4; i++) {
        out[4 * i + 0] = (uint8_t)abcd[i];
        out[4 * i + 1] = (uint8_t)(abcd[i] >> 8);
        out[4 * i + 2] = (uint8_t)(abcd[i] >> 16);
        out[4 * i + 3] = (uint8_t)(abcd[i] >> 24);
    }
}

static void crypt_clear(UncCrypt *cr, int kind, uint32_t blocksize);

/* ------------------------------------------------------------------ */
/* SHA-1, HMAC-SHA1 and PBKDF2 (WinZip's AES, and nothing else)        */
/* Source: reference/XADMaster/Crypto/sha.c and hmac_sha1.c, and the    */
/* key derivation in XADWinZipAESHandle.m (DeriveKey), which is         */
/* PBKDF2 with 1000 iterations. LGPL / public domain — see NOTICE.      */
/* ------------------------------------------------------------------ */

static void sha1_block(uint32_t h[5], const uint8_t *p)
{
    uint32_t w[80], a, b, c, d, e;
    int i;

    for (i = 0; i < 16; i++) w[i] = unc_get_u32be(p + 4 * i);
    for (i = 16; i < 80; i++)
        w[i] = rotl32(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);

    a = h[0]; b = h[1]; c = h[2]; d = h[3]; e = h[4];
    for (i = 0; i < 80; i++) {
        uint32_t f, k, t;
        if (i < 20)      { f = (b & c) | (~b & d);           k = 0x5a827999u; }
        else if (i < 40) { f = b ^ c ^ d;                    k = 0x6ed9eba1u; }
        else if (i < 60) { f = (b & c) | (b & d) | (c & d);  k = 0x8f1bbcdcu; }
        else             { f = b ^ c ^ d;                    k = 0xca62c1d6u; }
        t = rotl32(a, 5) + f + e + k + w[i];
        e = d; d = c; c = rotl32(b, 30); b = a; a = t;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e;
}

static void sha1_init(UncSha1 *s)
{
    s->h[0] = 0x67452301u; s->h[1] = 0xefcdab89u; s->h[2] = 0x98badcfeu;
    s->h[3] = 0x10325476u; s->h[4] = 0xc3d2e1f0u;
    s->len = 0;
    s->have = 0;
}

static void sha1_update(UncSha1 *s, const uint8_t *p, uint32_t n)
{
    s->len += n;
    while (n > 0) {
        uint32_t k = 64 - s->have;
        uint32_t i;
        if (k > n) k = n;
        for (i = 0; i < k; i++) s->buf[s->have + i] = p[i];
        s->have += k;
        p += k;
        n -= k;
        if (s->have == 64) { sha1_block(s->h, s->buf); s->have = 0; }
    }
}

static void sha1_final(UncSha1 *s, uint8_t out[20])
{
    uint32_t bits = s->len << 3, hi = s->len >> 29;
    uint8_t pad = 0x80;
    int i;
    sha1_update(s, &pad, 1);
    pad = 0;
    while (s->have != 56) sha1_update(s, &pad, 1);
    /* The length field is 64 bits; a fork is under 2 GB, so the top
     * three bits are all that can be set above 32. */
    { uint8_t l[8];
      l[0] = 0; l[1] = 0; l[2] = 0; l[3] = (uint8_t)hi;
      unc_put_u32be(l + 4, bits);
      sha1_update(s, l, 8); }
    for (i = 0; i < 5; i++) unc_put_u32be(out + 4 * i, s->h[i]);
}

/* HMAC-SHA1, kept as two saved states so the outer hash does not have
 * to re-key: exactly what hmac_sha1.c does. */
static void hmac_init(UncHmac *m, const uint8_t *key, uint32_t keylen)
{
    uint8_t block[64], digest[20];
    uint32_t i;

    if (keylen > 64) {
        UncSha1 s;
        sha1_init(&s);
        sha1_update(&s, key, keylen);
        sha1_final(&s, digest);
        key = digest;
        keylen = 20;
    }
    for (i = 0; i < 64; i++) block[i] = i < keylen ? (uint8_t)(key[i] ^ 0x36)
                                                  : 0x36;
    sha1_init(&m->in);
    sha1_update(&m->in, block, 64);
    for (i = 0; i < 64; i++) block[i] = i < keylen ? (uint8_t)(key[i] ^ 0x5c)
                                                  : 0x5c;
    sha1_init(&m->out);
    sha1_update(&m->out, block, 64);
}

void unc_hmac_update(UncHmac *m, const uint8_t *p, uint32_t n)
{
    sha1_update(&m->in, p, n);
}

void unc_hmac_final(UncHmac *m, uint8_t out[20])
{
    uint8_t digest[20];
    sha1_final(&m->in, digest);
    sha1_update(&m->out, digest, 20);
    sha1_final(&m->out, out);
}

/* PBKDF2-HMAC-SHA1, as XADWinZipAESHandle's DeriveKey. */
static void pbkdf2(const uint8_t *pw, uint32_t pwlen,
                   const uint8_t *salt, uint32_t saltlen,
                   uint32_t iterations, uint8_t *out, uint32_t outlen)
{
    uint32_t block, done = 0;

    for (block = 1; done < outlen; block++) {
        UncHmac m;
        uint8_t counter[4], buf[20], acc[20];
        uint32_t j, n;

        counter[0] = (uint8_t)(block >> 24); counter[1] = (uint8_t)(block >> 16);
        counter[2] = (uint8_t)(block >> 8);  counter[3] = (uint8_t)block;
        hmac_init(&m, pw, pwlen);
        unc_hmac_update(&m, salt, saltlen);
        unc_hmac_update(&m, counter, 4);
        unc_hmac_final(&m, buf);
        for (j = 0; j < 20; j++) acc[j] = buf[j];

        for (j = 1; j < iterations; j++) {
            uint32_t k;
            hmac_init(&m, pw, pwlen);
            unc_hmac_update(&m, buf, 20);
            unc_hmac_final(&m, buf);
            for (k = 0; k < 20; k++) acc[k] ^= buf[k];
        }
        n = outlen - done < 20 ? outlen - done : 20;
        for (j = 0; j < n; j++) out[done + j] = acc[j];
        done += n;
    }
}

/* Three hooks for the unit tests, which grade these against hashlib
 * and openssl. Nothing in the engine calls them. */
void unc_hmac_init_test(UncHmac *m, const uint8_t *key, uint32_t keylen)
{
    hmac_init(m, key, keylen);
}

void unc_pbkdf2_test(const uint8_t *pw, uint32_t pwlen,
                     const uint8_t *salt, uint32_t saltlen,
                     uint32_t iterations, uint8_t *out, uint32_t outlen)
{
    pbkdf2(pw, pwlen, salt, saltlen, iterations, out, outlen);
}

/* ------------------------------------------------------------------ */
/* AES, forward direction only                                         */
/*                                                                    */
/* Counter mode encrypts to decrypt, so the inverse cipher is never    */
/* needed and neither are its tables: one 256-byte S box and the       */
/* column mix, which costs speed and saves four kilobytes on a machine */
/* that has one megabyte. Source: FIPS-197 as implemented in           */
/* reference/XADMaster/Crypto/aeskey.c and aescrypt.c.                 */
/* ------------------------------------------------------------------ */

static uint8_t xtime(uint8_t x)
{
    return (uint8_t)((x << 1) ^ ((x & 0x80) ? 0x1b : 0));
}

static void aes_setkey(UncCrypt *cr, const uint8_t *key, int keybytes)
{
    int nk = keybytes / 4;                 /* 4, 6 or 8 words */
    int total = (nk + 7) * 4;              /* (rounds + 1) * 4 words */
    uint8_t rcon = 1;
    int i;

    cr->aesrounds = nk + 6;
    for (i = 0; i < keybytes; i++) cr->rk[i] = key[i];
    for (i = nk; i < total; i++) {
        uint8_t t[4];
        int j;
        for (j = 0; j < 4; j++) t[j] = cr->rk[(i - 1) * 4 + j];
        if (i % nk == 0) {
            uint8_t tmp = t[0];
            t[0] = (uint8_t)(unc_aes_sbox[t[1]] ^ rcon);
            t[1] = unc_aes_sbox[t[2]];
            t[2] = unc_aes_sbox[t[3]];
            t[3] = unc_aes_sbox[tmp];
            rcon = xtime(rcon);
        } else if (nk > 6 && i % nk == 4) {
            for (j = 0; j < 4; j++) t[j] = unc_aes_sbox[t[j]];
        }
        for (j = 0; j < 4; j++)
            cr->rk[i * 4 + j] = (uint8_t)(cr->rk[(i - nk) * 4 + j] ^ t[j]);
    }
}

static void aes_encrypt_block(const UncCrypt *cr, uint8_t st[16])
{
    int round, i;

    for (i = 0; i < 16; i++) st[i] ^= cr->rk[i];
    for (round = 1; round <= cr->aesrounds; round++) {
        uint8_t t[16];
        /* SubBytes + ShiftRows, in the column-major order AES uses:
         * byte (r,c) lives at 4*c + r and row r rotates left by r. */
        for (i = 0; i < 16; i++)
            t[i] = unc_aes_sbox[st[(i + 4 * (i & 3)) & 15]];
        if (round != cr->aesrounds) {
            for (i = 0; i < 16; i += 4) {          /* MixColumns */
                uint8_t a0 = t[i], a1 = t[i + 1], a2 = t[i + 2], a3 = t[i + 3];
                uint8_t x = (uint8_t)(a0 ^ a1 ^ a2 ^ a3);
                st[i]     = (uint8_t)(a0 ^ x ^ xtime((uint8_t)(a0 ^ a1)));
                st[i + 1] = (uint8_t)(a1 ^ x ^ xtime((uint8_t)(a1 ^ a2)));
                st[i + 2] = (uint8_t)(a2 ^ x ^ xtime((uint8_t)(a2 ^ a3)));
                st[i + 3] = (uint8_t)(a3 ^ x ^ xtime((uint8_t)(a3 ^ a0)));
            }
        } else {
            for (i = 0; i < 16; i++) st[i] = t[i];
        }
        for (i = 0; i < 16; i++) st[i] ^= cr->rk[round * 16 + i];
    }
}

void unc_aes_encrypt_test(UncCrypt *cr, const uint8_t *key, int keybytes,
                          uint8_t block[16])
{
    aes_setkey(cr, key, keybytes);
    aes_encrypt_block(cr, block);
}

/* WinZip's AES: PBKDF2 over the salt gives an encryption key, an
 * authentication key and a two-byte verifier, and the data is a counter
 * mode stream with the counter LITTLE-endian and starting at 1.
 * Source: XADWinZipAESHandle.m. `keybytes` is 16, 24 or 32; `salt` is
 * keybytes/2 long. Returns UNC_ERR_PASSWORD if the verifier disagrees. */
int unc_crypt_winzip_aes(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen,
                         const uint8_t *salt, int keybytes,
                         const uint8_t verifier[2])
{
    uint8_t keybuf[2 * 32 + 2];
    int i;

    crypt_clear(cr, UNC_CRYPT_AES, 1);
    pbkdf2(pw, pwlen, salt, (uint32_t)(keybytes / 2), 1000, keybuf,
           (uint32_t)(2 * keybytes + 2));
    if (keybuf[2 * keybytes] != verifier[0] ||
        keybuf[2 * keybytes + 1] != verifier[1])
        return UNC_ERR_PASSWORD;

    aes_setkey(cr, keybuf, keybytes);
    hmac_init(&cr->hmac, keybuf + keybytes, (uint32_t)keybytes);
    for (i = 0; i < 16; i++) cr->ctr[i] = 0;
    cr->ctrpos = 0;
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* Constructors                                                        */
/* ------------------------------------------------------------------ */

static void crypt_clear(UncCrypt *cr, int kind, uint32_t blocksize)
{
    uint8_t *p = (uint8_t *)cr;
    uint32_t *tab = cr->tab;          /* the caller's to free, not ours */
    int tabkind = cr->tabkind;
    uint32_t i;
    for (i = 0; i < sizeof *cr; i++) p[i] = 0;
    cr->kind = kind;
    cr->blocksize = blocksize;
    cr->tab = tab;
    cr->tabkind = tabkind;
}

void unc_crypt_xor(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen)
{
    uint16_t i;
    crypt_clear(cr, UNC_CRYPT_XOR, 1);
    if (pwlen > (uint16_t)sizeof cr->key) pwlen = (uint16_t)sizeof cr->key;
    for (i = 0; i < pwlen; i++) cr->key[i] = pw[i];
    cr->keylen = pwlen;
    if (pwlen == 0) cr->kind = UNC_CRYPT_NONE;
}

/* PackIt PMa5. The key is DES's PC-1 applied to eight password bytes;
 * it is then used modulo SEVEN, which loses key[7] entirely. That is
 * what XADPackItXORHandle does and what the files were written by.
 * Source: XADPackItParser.m (keytr1). */
void unc_crypt_packit_xor(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen)
{
    uint8_t passbuf[8];
    int i;

    crypt_clear(cr, UNC_CRYPT_PIT_XOR, 1);
    for (i = 0; i < 8; i++) passbuf[i] = i < pwlen ? pw[i] : 0;
    for (i = 0; i < 56; i++) {
        /* keytr1 is PC-1: bK_C then bK_D, which is how des.c holds it. */
        int bitindex = (i < 28 ? unc_des_pc1c[i] : unc_des_pc1d[i - 28]) - 1;
        cr->key[i / 8] = (uint8_t)(cr->key[i / 8] |
            (((passbuf[bitindex / 8] << (bitindex % 8)) & 0x80) >> (i % 8)));
    }
    cr->keylen = 7;
}

/* PackIt PMa6: DES, and the operation that DECODES is DES's decrypt. */
int unc_crypt_packit_des(UncCrypt *cr, UncAlloc *al, const uint8_t *pw,
                         uint16_t pwlen)
{
    uint8_t key[8];
    int i, err;
    if ((err = crypt_table(cr, al, CRYPT_TAB_DES)) != UNC_OK) return err;
    crypt_clear(cr, UNC_CRYPT_PIT_DES, 8);
    for (i = 0; i < 8; i++) key[i] = i < pwlen ? pw[i] : 0;
    des_setkey(cr->ks, key);
    return UNC_OK;
}

int unc_crypt_zip(UncCrypt *cr, const uint8_t *pw, uint16_t pwlen)
{
    uint16_t i;
    crypt_clear(cr, UNC_CRYPT_ZIP, 1);
    cr->k0 = 305419896u;
    cr->k1 = 591751049u;
    cr->k2 = 878082192u;
    for (i = 0; i < pwlen; i++) unc_crypt_zip_update(cr, pw[i]);
    return UNC_OK;
}

void unc_crypt_zip_update(UncCrypt *cr, uint8_t b)
{
    cr->k0 = unc_crc32(cr->k0, &b, 1);
    cr->k1 += cr->k0 & 0xff;
    cr->k1 = cr->k1 * 134775813u + 1u;
    {
        uint8_t hi = (uint8_t)(cr->k1 >> 24);
        cr->k2 = unc_crc32(cr->k2, &hi, 1);
    }
}

/* Compact Pro. The password becomes a nine-byte key: a length capped
 * at eight, then the password's bytes ADDED into eight accumulators in
 * rotation, so a password of eight or fewer characters is its own key.
 * Those bytes are then folded into the CRC register one at a time, by
 * the same step the data uses. Source: Compact Pro 1.51 `CODE` 3
 * @0x1892 (the key) and @0x40fe (the seed and the fold). */
int unc_crypt_cpt(UncCrypt *cr, UncAlloc *al, const uint8_t *pw,
                  uint16_t pwlen)
{
    uint8_t key[9];
    int i, n, err;

    if ((err = crypt_table(cr, al, CRYPT_TAB_CRC64)) != UNC_OK) return err;
    crypt_clear(cr, UNC_CRYPT_CPT, 1);
    for (i = 0; i < 9; i++) key[i] = 0;
    for (i = 0; i < (int)pwlen; i++)
        key[(i & 7) + 1] = (uint8_t)(key[(i & 7) + 1] + pw[i]);
    n = pwlen > 8 ? 8 : (int)pwlen;
    key[0] = (uint8_t)n;

    cr->hi = 0x01234567u;
    cr->lo = 0x89abcdefu;
    for (i = 1; i <= n; i++) {
        uint32_t idx = (uint32_t)(key[i] ^ (cr->lo & 0xFF));
        uint32_t lo = ((cr->hi << 24) | (cr->lo >> 8)) ^ cr->tab[2 * idx + 1];
        cr->hi = (cr->hi >> 8) ^ cr->tab[2 * idx];
        cr->lo = lo;
    }
    return UNC_OK;
}

void unc_crypt_rc4(UncCrypt *cr, const uint8_t *key, uint16_t keylen)
{
    int i;
    uint8_t j = 0;
    crypt_clear(cr, UNC_CRYPT_RC4, 1);
    for (i = 0; i < 256; i++) cr->s[i] = (uint8_t)i;
    if (keylen == 0) { cr->kind = UNC_CRYPT_NONE; return; }
    for (i = 0; i < 256; i++) {
        uint8_t t;
        j = (uint8_t)(j + cr->s[i] + key[i % keylen]);
        t = cr->s[i]; cr->s[i] = cr->s[j]; cr->s[j] = t;
    }
    cr->si = cr->sj = 0;
}

/* StuffIt 5: the archive key is the first five bytes of MD5(password),
 * and the archive header carries MD5 of THAT, also truncated to five,
 * so a wrong password is known before anything is decoded.
 * Source: XADStuffIt5Parser.m keyForEntryWithDictionary. */
int unc_crypt_sit5_key(const uint8_t *pw, uint16_t pwlen,
                       const uint8_t hash[UNC_SIT5_KEYLEN],
                       uint8_t out[UNC_SIT5_KEYLEN])
{
    uint8_t digest[16];
    int i;

    unc_md5(pw, pwlen, digest);
    for (i = 0; i < UNC_SIT5_KEYLEN; i++) out[i] = digest[i];
    unc_md5(out, UNC_SIT5_KEYLEN, digest);
    for (i = 0; i < UNC_SIT5_KEYLEN; i++)
        if (digest[i] != hash[i]) return UNC_ERR_PASSWORD;
    return UNC_OK;
}

/* StuffIt classic. Three keys are involved: the ARCHIVE key, iterated
 * out of the password; the archive IV, which is the 'MKey' resource
 * decrypted under it (and which also verifies the password); and the
 * FILE key and IV, derived from the sixteen bytes stored at the end of
 * the entry's own compressed fork. Source: XADStuffItDESHandle.m
 * keyForPasswordData:entryKey:MKey:. */
int unc_crypt_sit(UncCrypt *cr, UncAlloc *al, const uint8_t *pw,
                  uint16_t pwlen, const uint8_t entrykey[16],
                  const uint8_t mkey[8])
{
    uint8_t ks[16][8];
    const uint32_t *sp;
    uint8_t archivekey[8] = { 0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef };
    uint8_t archiveiv[8], verifyblock[8] = { 0, 0, 0, 0, 0, 0, 0, 4 };
    uint8_t filekey[8], fileiv[8];
    uint32_t x, blocks, length = pwlen;
    int i;

    /* One fold per eight-byte block of the password, and the count is
     * ceil(length / 8) — MEASURED, on three archives StuffIt Deluxe
     * 3.5.1 wrote under Mini vMac with passwords of 8, 9 and 17
     * characters, which need 1, 2 and 3 folds (tools/vmac/sitcrypt.py;
     * FORMATS.md, *StuffIt classic's archive key*).
     *
     * NEITHER reference has this. XADMaster's loop —
     *   while ((((x * (length >> 3)) << 3) <= length) && length >= 8)
     * — folds an extra ALL-ZERO block at exactly 8 and stops at two
     * folds however long the password is, so it is wrong at 8 and at
     * 17 and up; Debian's `unar` 1.10.8 folds one block whatever the
     * length, so it is wrong at 9 and up. Each opens archives the other
     * cannot, which is what the divergence looked like from here before
     * an archive existed to ask. */
    blocks = (length + 7u) >> 3;
    {
        int err = crypt_table(cr, al, CRYPT_TAB_DES);
        if (err != UNC_OK) return err;
    }
    sp = cr->tab;
    sitdes_setkey(archivekey, ks);
    for (x = 0; x < blocks; x++) {
        uint8_t passblock[8];
        uint32_t off = x << 3, n = length - off < 8u ? length - off : 8u;

        for (i = 0; i < 8; i++) passblock[i] = 0;
        for (i = 0; i < (int)n; i++) passblock[i] = pw[off + (uint32_t)i];

        for (i = 0; i < 8; i++) archivekey[i] ^= passblock[i] & 0x7f;

        sitdes_crypt(archivekey, ks, 1, sp);
    }

    /* Everything below is keyed by the folded archive key, so the
     * schedule is derived once. (It was derived three more times until
     * 2026-09-19, each from the same unchanged bytes.) */
    sitdes_setkey(archivekey, ks);

    for (i = 0; i < 8; i++) archiveiv[i] = mkey[i];
    sitdes_crypt(archiveiv, ks, 0, sp);

    /* Verify: encrypting the IV's first four bytes (with a trailing 4)
     * must reproduce its last four. */
    for (i = 0; i < 4; i++) verifyblock[i] = archiveiv[i];
    sitdes_crypt(verifyblock, ks, 1, sp);
    for (i = 0; i < 4; i++)
        if (verifyblock[4 + i] != archiveiv[4 + i]) return UNC_ERR_PASSWORD;

    for (i = 0; i < 8; i++) {
        filekey[i] = entrykey[i];
        fileiv[i] = entrykey[8 + i];
    }
    sitdes_crypt(filekey, ks, 0, sp);
    for (i = 0; i < 8; i++) filekey[i] ^= archiveiv[i];
    sitdes_setkey(filekey, ks);
    sitdes_crypt(fileiv, ks, 0, sp);

    crypt_clear(cr, UNC_CRYPT_SIT_DES, 8);
    cr->a = unc_get_u32be(&filekey[0]);
    cr->b = unc_get_u32be(&filekey[4]);
    cr->c = unc_get_u32be(&fileiv[0]);
    cr->d = unc_get_u32be(&fileiv[4]);
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* The transform                                                       */
/*                                                                    */
/* `pos` is the offset of buf[0] within the encrypted stream. The two  */
/* position-keyed ciphers use it; the four stateful ones (both DES     */
/* feedbacks, RC4, zip) require the calls to be sequential and ignore  */
/* it, which is what UncBufIn guarantees — it only ever moves forward, */
/* and a decoder that needs to jump re-initialises the whole reader.   */
/* ------------------------------------------------------------------ */

void unc_crypt_apply(UncCrypt *cr, uint8_t *buf, uint32_t len, uint32_t pos)
{
    uint32_t i;

    switch (cr->kind) {
    case UNC_CRYPT_NONE:
        break;

    case UNC_CRYPT_XOR:
        for (i = 0; i < len; i++) buf[i] ^= cr->key[(pos + i) % cr->keylen];
        break;

    case UNC_CRYPT_PIT_XOR:
        for (i = 0; i < len; i++) buf[i] ^= cr->key[(pos + i) % 7u];
        break;

    case UNC_CRYPT_PIT_DES:
        for (i = 0; i + 8 <= len; i += 8) des_crypt(cr->ks, buf + i, 1, cr->tab);
        break;

    case UNC_CRYPT_SIT_DES:
        /* An eight-byte feedback XOR: the two halves are masked with
         * A^C and B^D, and D then folds in the CIPHERTEXT of the block
         * just consumed. A and B never change. */
        for (i = 0; i + 8 <= len; i += 8) {
            uint32_t left = unc_get_u32be(buf + i);
            uint32_t right = unc_get_u32be(buf + i + 4);
            unc_put_u32be(buf + i, left ^ cr->a ^ cr->c);
            unc_put_u32be(buf + i + 4, right ^ cr->b ^ cr->d);
            cr->c = cr->d;
            cr->d = rotr32(left ^ right ^ cr->a ^ cr->b ^ cr->d, 1);
        }
        break;

    case UNC_CRYPT_RC4:
        for (i = 0; i < len; i++) {
            uint8_t t;
            cr->si = (uint8_t)(cr->si + 1);
            cr->sj = (uint8_t)(cr->sj + cr->s[cr->si]);
            t = cr->s[cr->si];
            cr->s[cr->si] = cr->s[cr->sj];
            cr->s[cr->sj] = t;
            buf[i] ^= cr->s[(uint8_t)(cr->s[cr->si] + cr->s[cr->sj])];
        }
        break;

    case UNC_CRYPT_CPT:
        for (i = 0; i < len; i++) {
            uint32_t idx, lo;
            buf[i] ^= (uint8_t)(cr->lo >> 8);          /* keystream byte */
            idx = (uint32_t)(buf[i] ^ (cr->lo & 0xFF));/* on the PLAINtext */
            lo = ((cr->hi << 24) | (cr->lo >> 8)) ^ cr->tab[2 * idx + 1];
            cr->hi = (cr->hi >> 8) ^ cr->tab[2 * idx];
            cr->lo = lo;
        }
        break;

    case UNC_CRYPT_AES:
        /* Counter mode, and the authentication code is over the
         * CIPHERtext, so it is fed before the XOR. */
        unc_hmac_update(&cr->hmac, buf, len);
        for (i = 0; i < len; i++) {
            if (cr->ctrpos == 0) {
                int k;
                for (k = 0; k < 8; k++) if (++cr->ctr[k] != 0) break;
                for (k = 0; k < 16; k++) cr->ctrbuf[k] = cr->ctr[k];
                aes_encrypt_block(cr, cr->ctrbuf);
            }
            buf[i] ^= cr->ctrbuf[cr->ctrpos];
            cr->ctrpos = (uint8_t)((cr->ctrpos + 1) & 15);
        }
        break;

    case UNC_CRYPT_ZIP:
        for (i = 0; i < len; i++) {
            /* 32-bit: the two 16-bit halves multiply to more than a
             * 16-bit int holds, and on a 32-bit int that is signed
             * overflow rather than the wrap the algorithm wants. */
            uint32_t temp = (cr->k2 | 2u) & 0xFFFFu;
            buf[i] ^= (uint8_t)((temp * (temp ^ 1u)) >> 8);
            unc_crypt_zip_update(cr, buf[i]);
        }
        break;

    default:
        break;
    }
    (void)pos;
}

/* ------------------------------------------------------------------ */
/* Resource forks                                                      */
/*                                                                    */
/* Only because StuffIt classic keeps its password verifier in one.    */
/* Layout (Inside Macintosh: More Macintosh Toolbox, "Resource File    */
/* Format"): a 16-byte header gives the offsets of the data area and   */
/* the map; the map's type list is at map+24 (a u16 offset), each type */
/* entry names a 4-char type, a count-1 and the offset of its          */
/* reference list within the type list; each reference gives an id and */
/* a 24-bit offset into the data area, where the resource is a u32     */
/* length followed by the bytes.                                       */
/* ------------------------------------------------------------------ */

int unc_resfork_find(const uint8_t *fork, uint32_t forklen,
                     uint32_t type, int16_t id,
                     uint32_t *off, uint32_t *len)
{
    uint32_t dataoff, mapoff, datalen, maplen, typelistoff, ntypes, i;

    if (!fork || forklen < 16 + 30) return UNC_ERR_FORMAT;
    dataoff = unc_get_u32be(fork + 0);
    mapoff  = unc_get_u32be(fork + 4);
    datalen = unc_get_u32be(fork + 8);
    maplen  = unc_get_u32be(fork + 12);
    if (mapoff + maplen > forklen || dataoff + datalen > forklen) return UNC_ERR_FORMAT;
    if (maplen < 30) return UNC_ERR_FORMAT;

    typelistoff = mapoff + unc_get_u16be(fork + mapoff + 24);
    if (typelistoff + 2 > forklen) return UNC_ERR_FORMAT;
    ntypes = (uint32_t)unc_get_u16be(fork + typelistoff) + 1u;
    if (ntypes > 4096) return UNC_ERR_FORMAT;

    for (i = 0; i < ntypes; i++) {
        uint32_t te = typelistoff + 2 + i * 8, nrefs, reflist, j;
        if (te + 8 > forklen) return UNC_ERR_FORMAT;
        if (unc_get_u32be(fork + te) != type) continue;
        nrefs = (uint32_t)unc_get_u16be(fork + te + 4) + 1u;
        reflist = typelistoff + unc_get_u16be(fork + te + 6);
        for (j = 0; j < nrefs; j++) {
            uint32_t re = reflist + j * 12, dat;
            if (re + 12 > forklen) return UNC_ERR_FORMAT;
            if ((int16_t)unc_get_u16be(fork + re) != id) continue;
            dat = dataoff + (unc_get_u32be(fork + re + 4) & 0x00FFFFFFu);
            if (dat + 4 > forklen) return UNC_ERR_FORMAT;
            *len = unc_get_u32be(fork + dat);
            *off = dat + 4;
            if (*off + *len > forklen) return UNC_ERR_FORMAT;
            return UNC_OK;
        }
        return UNC_ERR_FORMAT;      /* the type is there, the id is not */
    }
    return UNC_ERR_FORMAT;
}

/* ------------------------------------------------------------------ */
/* Password plumbing                                                   */
/* ------------------------------------------------------------------ */

/* Fetch a password to try. `again` means the last one was rejected, so
 * the host is asked for another. Returns UNC_OK with c->pw/pwlen set,
 * or UNC_ERR_PASSWORD when there is nothing (more) to try. */
int unc_password(UncCtx *c, int again)
{
    uint16_t len = 0;

    if (!again) {
        if (c->pwstate == UNC_PW_STATIC || c->pwstate == UNC_PW_ASKED)
            return UNC_OK;                       /* one is in hand */
        if (c->pwstate != UNC_PW_UNSET) return UNC_ERR_PASSWORD;
    } else {
        if (c->pwstate == UNC_PW_NONE) return UNC_ERR_PASSWORD;
        c->pwattempt++;
        /* A rejected static password is not offered again; the callback
         * (if any) is what can produce a different one. */
        if (c->pwstate == UNC_PW_STATIC) c->pwstate = UNC_PW_TRIED;
    }

    if (c->pwstate == UNC_PW_UNSET && c->opt.password) {
        uint16_t n = c->opt.password_len, i;
        if (n > UNC_PASSWORD_MAX) n = UNC_PASSWORD_MAX;
        for (i = 0; i < n; i++) c->pw[i] = c->opt.password[i];
        c->pwlen = n;
        c->pwstate = UNC_PW_STATIC;
        return UNC_OK;
    }
    if (c->opt.ask && c->opt.ask->ask &&
        c->opt.ask->ask(c->opt.ask->ctx, c->pw, UNC_PASSWORD_MAX, &len,
                        c->pwattempt)) {
        c->pwlen = len > UNC_PASSWORD_MAX ? UNC_PASSWORD_MAX : len;
        c->pwstate = UNC_PW_ASKED;
        return UNC_OK;
    }
    c->pwstate = UNC_PW_NONE;
    return UNC_ERR_PASSWORD;
}
