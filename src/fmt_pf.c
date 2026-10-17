/* fmt_pf.c — Aladdin Private File (`.pf`), a password-encrypted single file.
 *
 * One Macintosh file, both forks and its Finder information, under RC4.
 * The layout, all big-endian:
 *
 *     0   18  header, in clear:  'CSIT', u16 version (2), u16 key
 *             derivation (1 = MD5 of the password), u16 cipher (1 =
 *             RC4), u16 key length in bytes, s16 (0), u32 (0)
 *    18  308  file record, encrypted: 'CSIT', Str255 name, FInfo (16),
 *             FXInfo (16), u32 data length, u32 resource length, u32
 *             created, u32 modified
 *   326   ..  data fork then resource fork, encrypted as ONE stream
 *   ...   12  footer, in clear: 'CSIT', u32 CRC-32 of the data fork, u32
 *             CRC-32 of the resource fork
 *
 * The key is the first `key length` bytes of MD5(password), the password
 * being its bytes with no length and no terminator. The file record and
 * the forks are two SEPARATE RC4 streams under that same key, each
 * started fresh. A wrong password is known by the decrypted record not
 * beginning 'CSIT' — there is no other verifier. Each CRC-32 is the
 * reflected 0xEDB88320 one, but started at 0 and never inverted, which
 * is exactly what unc_crc32 computes on its own.
 *
 * Source: Aladdin Private File 2.0's `PF Encrypt™`, `CODE` 4 "ACL/Crypto",
 * whose MacsBug names survive: CCrypt::MakeHeader, MakeFileInfo and
 * MakeFooter fill the three records, and CCrypt::Encrypt writes them in
 * the order above, keys both RC4s from MD5::GetDigest and runs the data
 * fork then the resource fork through the same one; RC4::SetKey and
 * RC4::Crypt are the textbook cipher, ACLCRC32's constructor zeroes and
 * its Update has no final XOR. The key length is GetEncryptionKeySize:
 * resource 'KSiz' 128 if present, otherwise 5 — and the export build
 * Aladdin shipped has no 'KSiz', so it writes 5. What the READER accepts
 * is StuffIt Engine 5.1's PFEngine (`Eng ` 10009, the decrypt path): the
 * header magic, version exactly 2, derivation and cipher each at most 1,
 * the s16 at most 0 — anything else is "encrypted with a method that this
 * software does not handle" — and a record that does not decrypt to
 * 'CSIT' is "an incorrect password". DECISIONS.md 2026-10-08 has how it
 * was read and what graded it.
 *
 * NOT SUPPORTED, by decision rather than by accident: derivation 0 (the
 * password's own bytes as key) and cipher 0. PFEngine has paths for both
 * and no writer here produces either, so they are named and refused per
 * entry — the reading of them would be a guess.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"
#include "fmt_pf_priv.h"

/* One fork: read, CRC the plaintext, write. The stream is the caller's
 * and runs on from the data fork into the resource fork. */
static int pf_fork(UncCtx *c, UncCrypt *cr, UncFork fork, uint32_t size,
                   uint8_t *buf, uint32_t cap, uint32_t *crc)
{
    while (size > 0) {
        int32_t want = (int32_t)(size < cap ? size : cap);
        int32_t r = c->io->read(c->io->ctx, buf, want);
        int e;
        if (r < 0) return UNC_ERR_IO;
        if (r == 0) return UNC_ERR_TRUNCATED;
        unc_crypt_apply(cr, buf, (uint32_t)r, 0);
        *crc = unc_crc32(*crc, buf, r);
        if (!c->opt.test_only &&
            c->sink->write(c->sink->ctx, fork, buf, r) < 0)
            return UNC_ERR_SINK;
        size -= (uint32_t)r;
        e = unc_progress_add(&c->ps, (uint32_t)r);
        if (e != UNC_OK) return e;
    }
    return UNC_OK;
}

/* The record is decrypted in place, and read again from the file for
 * each password tried: a second copy kept encrypted would be 308 B of
 * heap for every extraction, to save one read per WRONG password. */
typedef struct PfWork {
    UncCrypt cr;
    uint8_t  rec[PF_REC];       /* the file record, under the password tried */
    uint8_t  buf[UNC_IOBUF];
} PfWork;

int unc_pf_extract(UncCtx *c)
{
    uint8_t hdr[PF_HDR], foot[PF_FOOT];
    uint32_t size, dlen = 0, rlen = 0, dcrc = 0, rcrc = 0;
    uint16_t keylen;
    UncEntryInfo e;
    PfWork *w;
    int est = UNC_OK, sret, attempt = 0;

    if (unc_read_at(c->io, 0, hdr, (int32_t)PF_HDR) != UNC_OK)
        return UNC_ERR_FORMAT;
    if (unc_pf_probe(hdr, (int32_t)PF_HDR, c->io) != UNC_FORMAT_PRIVATEFILE)
        return UNC_ERR_FORMAT;
    size = unc_io_size32(c->io);
    keylen = unc_get_u16be(hdr + 10);

    w = (PfWork *)unc_alloc(c->al, (uint32_t)sizeof *w);
    if (!w) return UNC_ERR_MEM;
    unc_crypt_init(&w->cr);

    /* Everything about the entry is inside the encrypted record, its name
     * included. With no password the entry is still reported, under the
     * host's name for the file (the archive's minus `.pf`, as gzip's is),
     * and fails on its own. */
    unc_entry_clear(&e);
    if (c->opt.name_hint && c->opt.name_hint_len)
        unc_entry_set_name(&e, c->opt.name_hint, c->opt.name_hint_len);
    e.data_size = e.rsrc_size = UNC_SIZE_UNKNOWN;
    e.comp_data_size = size - PF_FIXED;
    e.comp_rsrc_size = 0;

    if (unc_get_u16be(hdr + 6) != 1 || unc_get_u16be(hdr + 8) != 1 ||
        keylen == 0 || keylen > 16)
        est = UNC_ERR_ENCRYPTED;
    else for (;;) {
        est = unc_password(c, attempt > 0);
        if (est != UNC_OK) break;
        if (unc_read_at(c->io, PF_HDR, w->rec, (int32_t)PF_REC) != UNC_OK) {
            est = UNC_ERR_TRUNCATED;
            break;
        }
        unc_crypt_pf(&w->cr, c->pw, c->pwlen, keylen);
        /* The Macintosh build keys through an overlay, and one that could
         * not be loaded leaves no cipher: say so, rather than read the
         * record as plaintext and call every password wrong. */
        if (w->cr.kind == UNC_CRYPT_NONE) { est = UNC_ERR_MEM; break; }
        unc_crypt_apply(&w->cr, w->rec, PF_REC, 0);
        if (unc_get_u32be(w->rec) == PF_MAGIC) break;
        attempt++;
    }

    if (est == UNC_OK) {
        const uint8_t *r = w->rec;
        dlen = unc_get_u32be(r + 292);
        rlen = unc_get_u32be(r + 296);
        if (r[4]) unc_entry_set_name(&e, r + 5, r[4]);
        e.type         = unc_get_u32be(r + 260);
        e.creator      = unc_get_u32be(r + 264);
        e.finder_flags = unc_get_u16be(r + 268);
        e.create_date  = unc_get_u32be(r + 300);
        e.mod_date     = unc_get_u32be(r + 304);
        /* The FInfo and FXInfo whole, at 260 and 276 — the record's
         * layout above, from CCrypt::MakeFileInfo, which fills both from
         * the file's catalog entry. */
        {
            int k;
            for (k = 0; k < 32; k++) e.finder_info[k] = r[260 + k];
            e.meta = UNC_META_FINFO | UNC_META_FXINFO;
        }
        e.data_size    = dlen;
        e.rsrc_size    = rlen;
        e.comp_data_size = dlen;
        e.comp_rsrc_size = rlen;
        /* The forks fill the file exactly: the writer sizes it to
         * dlen + 338 + rlen before it writes a byte (PreAllocateFile). */
        if (dlen > UNC_MAC_MAX || rlen > UNC_MAC_MAX ||
            dlen + rlen != size - PF_FIXED)
            est = UNC_ERR_CORRUPT;
    }

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) { unc_free(c->al, w); return UNC_ERR_SINK; }
    if (sret > 0) { unc_free(c->al, w); return UNC_OK; }

    if (c->opt.list_only && est == UNC_ERR_PASSWORD) est = UNC_OK;
    if (est == UNC_OK && !c->opt.list_only) {
        unc_crypt_pf(&w->cr, c->pw, c->pwlen, keylen);
        if (c->io->seek(c->io->ctx, PF_HDR + PF_REC) < 0) est = UNC_ERR_IO;
        if (est == UNC_OK)
            est = pf_fork(c, &w->cr, UNC_FORK_DATA, dlen, w->buf,
                          UNC_IOBUF, &dcrc);
        if (est == UNC_OK)
            est = pf_fork(c, &w->cr, UNC_FORK_RSRC, rlen, w->buf,
                          UNC_IOBUF, &rcrc);
        if (est == UNC_OK)
            est = unc_read_full(c->io, foot, (int32_t)PF_FOOT);
        if (est == UNC_OK &&
            (unc_get_u32be(foot + 4) != dcrc || unc_get_u32be(foot + 8) != rcrc))
            est = UNC_ERR_CRC;
    }
    unc_free(c->al, w);

    if (c->sink->end_entry(c->sink->ctx, est) < 0) return UNC_ERR_SINK;
    return unc_fatal(est) ? est : UNC_OK;
}
