/*
 * fmt_packit.c — PackIt (.pit) decoder.
 *
 * A PackIt archive is a sequence of blocks, each introduced by a
 * 4-byte magic:
 *   'PMag'  uncompressed entry
 *   'PMa4'  Huffman-compressed entry
 *   'PMa5'  XOR-encrypted + Huffman        (reported as encrypted)
 *   'PMa6'  DES-encrypted + Huffman        (reported as encrypted)
 *   'PEnd'  end of archive
 *
 * Entry layout (94 bytes, itself inside the compressed stream for
 * PMa4..6):
 *   u8 namelen (capped at 63), 63 bytes name buffer,
 *   u32 type @64, u32 creator @68, u16 finderflags @72, u16 "lock" @74,
 *   u32 datasize @76, u32 rsrcsize @80, u32 createdate @84,
 *   u32 moddate @88, u16 header CRC @92 (CRC-16/XMODEM over bytes 0..91)
 *   (the layout is appendix C of reference/notes/packit_unpackit.txt)
 * then the data fork, the resource fork, and a u16 CRC-16/XMODEM over
 * both decoded forks. For PMa4 the container resumes at the next byte
 * boundary after the compressed stream.
 *
 * Source: reference/notes/packit_unpackit.txt, appendices B and C —
 * the format's own published description, with the corrections it
 * needs in docs/formats/packit.md, where a reader written from those
 * appendices alone reads all 38 forks of the corpus's four PackIt
 * archives (tools/derive_packit.py). The Huffman tree's serialisation,
 * which that document names and does not describe, is
 * docs/formats/serialized-huffman-tree.md; that a PMa4 entry codes its
 * 94-byte HEADER into the same stream as the two forks was measured
 * here on 2026-09-20 and is appendix C's closing note as well.
 *
 * What is still somebody else's, and says so where it is used:
 * everything about the two encrypted forms. **That the two CRCs are
 * CRC-16/XMODEM stopped being macutils' on 2026-09-27**: the appendix
 * names the fields and not their polynomial, but deark's packit.c
 * (MIT) builds both with DE_CRCOBJ_CRC16_XMODEM and checks the header
 * one exactly as this does — where XADMaster ignores it.
 *
 * PMa5 and PMa6 are decrypted where a password is available; without
 * one the entry is reported and the reader resyncs by scanning for the
 * next magic, which is macutils' strategy (pit.c "trying to sync") and
 * the only thing possible, since an undecodable entry does not say
 * where it ends. XADMaster's two handles are the reference for both
 * ciphers, and for the rule that the next block begins at the next
 * EIGHT-byte boundary after an encrypted one rather than the next
 * byte. Appendix B lists "PMa5" twice, for both ciphers, so the
 * document cannot name the fourth word and XADMaster is where 'PMa6'
 * comes from.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define PIT_HDR 94


/* Decoder for one entry's byte stream: either raw bufin bytes (PMag)
 * or Huffman-decoded (PMa4). */
typedef struct PitStream {
    UncBufIn *in;
    UncBitIn  bits;
    UncHuff  *huff;    /* NULL = stored */
    int       err;
} PitStream;

static int pit_next(PitStream *s)
{
    int b;
    if (s->err != UNC_OK) return -1;
    if (s->huff) {
        b = unc_huff_decode(s->huff, &s->bits);
        if (b < 0) s->err = s->bits.err != UNC_OK ? s->bits.err : UNC_ERR_CORRUPT;
    } else {
        b = unc_bufin_next(s->in);
        if (b < 0) s->err = s->in->err;
    }
    return b;
}

/* Read `n` stream bytes into buf; UNC_OK or error. */
static int pit_read(PitStream *s, uint8_t *buf, uint32_t n)
{
    uint32_t i;
    for (i = 0; i < n; i++) {
        int b = pit_next(s);
        if (b < 0) return s->err != UNC_OK ? s->err : UNC_ERR_TRUNCATED;
        buf[i] = (uint8_t)b;
    }
    return UNC_OK;
}

/* Stream one fork through the sink, updating crc. */
static int pit_fork(UncCtx *c, PitStream *s, UncFork fork, uint32_t size,
                    uint16_t *crc, uint8_t *obuf, uint32_t ocap)
{
    uint32_t left = size;
    while (left > 0) {
        uint32_t n = left < ocap ? left : ocap;
        int err = pit_read(s, obuf, n);
        if (err != UNC_OK) return err;
        *crc = unc_crc16_xmodem(*crc, obuf, (int32_t)n);
        if (!c->opt.test_only &&
            c->sink->write(c->sink->ctx, fork, obuf, (int32_t)n) < 0)
            return UNC_ERR_SINK;
        left -= n;
    }
    return UNC_OK;
}

/* After an encrypted (undecodable) entry we cannot know where it ends;
 * scan byte-wise for the next 'PMa[g456]' or 'PEnd' magic, macutils
 * style (pit.c "trying to sync"). Returns UNC_OK with the 4-byte magic
 * in out, or an error at EOF. */
static int pit_resync(UncBufIn *in, uint8_t out[4])
{
    uint8_t w[4] = {0, 0, 0, 0};
    uint32_t have = 0;
    for (;;) {
        int b = unc_bufin_next(in);
        if (b < 0) return in->err;
        w[0] = w[1]; w[1] = w[2]; w[2] = w[3]; w[3] = (uint8_t)b;
        if (have < 4) { have++; if (have < 4) continue; }
        if (w[0] == 'P' &&
            ((w[1] == 'M' && w[2] == 'a' &&
              (w[3] == 'g' || w[3] == '4' || w[3] == '5' || w[3] == '6')) ||
             (w[1] == 'E' && w[2] == 'n' && w[3] == 'd'))) {
            out[0] = w[0]; out[1] = w[1]; out[2] = w[2]; out[3] = w[3];
            return UNC_OK;
        }
    }
}

/* Is this failure the kind a different password might fix? A wrong key
 * makes the Huffman tree, and then the header, into nonsense; an I/O
 * error or an abort is nobody's password and must not be retried. */
static int pit_retryable(int err)
{
    return err == UNC_ERR_CORRUPT || err == UNC_ERR_TRUNCATED;
}

/* Re-position the reader at an absolute offset, optionally through a
 * cipher. PackIt reads the whole archive as one stream, so this is only
 * needed where an encrypted entry begins (a cipher has to start at the
 * entry, not at the file) and where one ends. */
static int pit_reopen(UncCtx *c, UncBufIn *in, uint8_t *iobuf, uint32_t iocap,
                      uint32_t abs, UncCrypt *cr)
{
    if (c->io->seek(c->io->ctx, abs) < 0) return UNC_ERR_IO;
    unc_bufin_init(in, c->io, &c->ps, iobuf, iocap);
    in->crypt = cr;
    return UNC_OK;
}

int unc_packit_extract(UncCtx *c)
{
    uint8_t *iobuf, *obuf;
    uint32_t iocap = UNC_IOBUF, ocap = UNC_IOBUF;
    UncHuff *huff;
    UncCrypt *cr;
    UncBufIn in;
    uint8_t magic[4];
    uint32_t base = 0;         /* file offset the reader was opened at */
    int err = UNC_OK;
    int first = 1;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap + (uint32_t)sizeof *cr);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;
    cr = (UncCrypt *)(void *)(obuf + ocap);
    unc_crypt_init(cr);
    huff = (UncHuff *)unc_alloc(c->al, (uint32_t)sizeof *huff);
    if (!huff) { unc_free(c->al, iobuf); return UNC_ERR_MEM; }

    if (c->io->seek(c->io->ctx, 0) < 0) { err = UNC_ERR_IO; goto out; }
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);

    for (;;) {
        PitStream st;
        UncEntryInfo e;
        uint8_t hdr[PIT_HDR];
        uint32_t namelen, datasize, rsrcsize;
        uint16_t crc, storedcrc;
        uint32_t start;
        int comp, encrypted, sret, eerr, attempt;

        /* Read block magic. */
        {
            int i;
            for (i = 0; i < 4; i++) {
                int b = unc_bufin_next(&in);
                if (b < 0) {
                    /* EOF exactly at a block boundary after >=1 block:
                     * tolerate a missing PEnd (truncated trailer). */
                    err = first ? UNC_ERR_FORMAT : UNC_OK;
                    goto out;
                }
                magic[i] = (uint8_t)b;
            }
        }

resynced:
        if (magic[0] == 'P' && magic[1] == 'E' && magic[2] == 'n' &&
            magic[3] == 'd')
            break;
        if (!(magic[0] == 'P' && magic[1] == 'M' && magic[2] == 'a' &&
              (magic[3] == 'g' || magic[3] == '4' || magic[3] == '5' ||
               magic[3] == '6'))) {
            err = first ? UNC_ERR_FORMAT : UNC_ERR_CORRUPT;
            goto out;
        }
        first = 0;

        comp      = magic[3] != 'g';
        encrypted = magic[3] == '5' || magic[3] == '6';
        start = base + unc_bufin_tell(&in);
        attempt = 0;

      attempt_entry:
        if (encrypted) {
            /* The cipher starts at the entry, so the reader has to as
             * well. PMa5 is the XOR, PMa6 is DES. */
            int perr = unc_password(c, attempt > 0);
            /* PMa6's DES builds its table on first use, and that is an
             * allocation: refused, the entry fails like any other. */
            if (perr == UNC_OK && magic[3] != '5')
                perr = unc_crypt_packit_des(cr, c->al, c->pw, c->pwlen);
            if (perr != UNC_OK) {
                /* No password to try, or no room for the cipher. Report
                 * the entry — nameless, because its name is inside the
                 * ciphertext — and resync: nothing here can say where
                 * it ends. */
                if (pit_reopen(c, &in, iobuf, iocap, start, NULL) != UNC_OK) {
                    err = UNC_ERR_IO;
                    goto out;
                }
                base = start;
                unc_entry_clear(&e);
                sret = c->sink->begin_entry(c->sink->ctx, &e);
                if (sret < 0) { err = UNC_ERR_SINK; goto out; }
                if (sret == 0 && c->sink->end_entry(c->sink->ctx, perr) < 0) {
                    err = UNC_ERR_SINK;
                    goto out;
                }
                if (pit_resync(&in, magic) != UNC_OK) {
                    err = UNC_OK;   /* clean EOF while scanning */
                    goto out;
                }
                goto resynced;
            }
            if (magic[3] == '5') unc_crypt_packit_xor(cr, c->pw, c->pwlen);
            if (pit_reopen(c, &in, iobuf, iocap, start, cr) != UNC_OK) {
                err = UNC_ERR_IO;
                goto out;
            }
            base = start;
        }

        st.in = &in;
        st.huff = NULL;
        st.err = UNC_OK;
        unc_bitin_init(&st.bits, &in);
        if (comp) {
            err = unc_huff_read_tree(huff, &st.bits);
            if (err != UNC_OK) {
                if (encrypted && pit_retryable(err)) {
                    err = UNC_OK;
                    attempt++;
                    goto attempt_entry;
                }
                goto out;
            }
            st.huff = huff;
        }

        err = pit_read(&st, hdr, PIT_HDR);
        if (err != UNC_OK) {
            if (encrypted && pit_retryable(err)) {
                err = UNC_OK;
                attempt++;
                goto attempt_entry;
            }
            goto out;
        }

        /* Header CRC over the first 92 bytes. Appendix C names the
         * field; that it is CRC-16/XMODEM, and that a reader checks
         * it, is reference/deark/modules/packit.c (MIT), de_run_packit
         * (crco_hdr) — macutils' pit.c until 2026-09-27.
         * PackIt stores nothing that verifies a password, so for an
         * encrypted entry this IS the verification: a wrong key makes
         * a header that does not check, and the host is asked again. */
        if (unc_crc16_xmodem(0, hdr, PIT_HDR - 2) != unc_get_u16be(hdr + 92)) {
            if (encrypted) { attempt++; goto attempt_entry; }
            err = UNC_ERR_CORRUPT;
            goto out;
        }

        namelen = hdr[0];
        if (namelen > 63) namelen = 63;
        datasize = unc_get_u32be(hdr + 76);   /* H_DLENOFF */
        rsrcsize = unc_get_u32be(hdr + 80);   /* H_RLENOFF */

        unc_entry_clear(&e);
        unc_entry_set_name(&e, hdr + 1, namelen);
        e.type         = unc_get_u32be(hdr + 64);  /* H_TYPEOFF */
        e.creator      = unc_get_u32be(hdr + 68);  /* H_AUTHOFF */
        e.finder_flags = unc_get_u16be(hdr + 72);  /* H_FLAGOFF */
        e.data_size    = datasize;
        e.rsrc_size    = rsrcsize;
        e.create_date  = unc_get_u32be(hdr + 84);  /* H_CTIMOFF */
        e.mod_date     = unc_get_u32be(hdr + 88);  /* H_MTIMOFF */
        e.method_data  = e.method_rsrc = comp ? 4 : 0;

        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; goto out; }

        if (sret > 0 || c->opt.list_only) {
            /* Skip the entry without writing. Stored entries could
             * seek, but decoding keeps one code path (and compressed
             * entries must be decoded to find their end anyway). */
            uint32_t left = datasize + rsrcsize;
            eerr = UNC_OK;
            while (left > 0 && eerr == UNC_OK) {
                uint32_t n = left < ocap ? left : ocap;
                eerr = pit_read(&st, obuf, n);
                left -= n;
            }
            if (eerr == UNC_OK) eerr = pit_read(&st, obuf, 2); /* fork CRC */
            if (sret == 0 &&
                c->sink->end_entry(c->sink->ctx, eerr) < 0) {
                err = UNC_ERR_SINK;
                goto out;
            }
        } else {
            crc = 0;
            eerr = pit_fork(c, &st, UNC_FORK_DATA, datasize, &crc, obuf, ocap);
            if (eerr == UNC_OK)
                eerr = pit_fork(c, &st, UNC_FORK_RSRC, rsrcsize, &crc, obuf, ocap);
            if (eerr == UNC_OK) {
                eerr = pit_read(&st, obuf, 2);
                if (eerr == UNC_OK) {
                    storedcrc = unc_get_u16be(obuf);
                    if (storedcrc != crc) eerr = UNC_ERR_CRC;
                }
            }
            if (c->sink->end_entry(c->sink->ctx, eerr) < 0) {
                err = UNC_ERR_SINK;
                goto out;
            }
        }

        /* Fatal conditions end the archive walk. */
        if (unc_fatal(eerr) || eerr == UNC_ERR_TRUNCATED) {
            err = eerr == UNC_ERR_TRUNCATED ? UNC_OK : eerr;
            goto out;
        }
        /* For compressed entries the next block begins at the next
         * byte boundary; bufin is already positioned there because the
         * bit reader only buffers whole bytes and unc_bitin_align
         * discards the remainder of the current byte. */
        unc_bitin_align(&st.bits);
        if (encrypted) {
            /* ... and after an ENCRYPTED one, at the next eight-byte
             * boundary, the cipher's block size (XADPackItParser.m:
             * end = start + ((offset + 7) & ~7)). The reader is holding
             * decrypted bytes, so it has to be reopened either way. */
            uint32_t end = start + ((unc_bufin_tell(&in) + 7u) & ~7u);
            if (pit_reopen(c, &in, iobuf, iocap, end, NULL) != UNC_OK) {
                err = UNC_ERR_IO;
                goto out;
            }
            base = end;
        }
    }

out:
    unc_free(c->al, huff);
    unc_crypt_free(cr, c->al);
    unc_free(c->al, iobuf);
    return err;
}
