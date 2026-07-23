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
 *   (offsets per macutils pit.h H_*OFF)
 * then the data fork, the resource fork, and a u16 CRC-16/XMODEM over
 * both decoded forks. For PMa4 the container resumes at the next byte
 * boundary after the compressed stream.
 *
 * Sources: reference/XADMaster/XADPackItParser.m and
 * reference/macutils/macunpack/pit.c — LGPL, see NOTICE.
 * (XADMaster ignores the header CRC; macutils checks it (pit.c
 * pit_filehdr) — we check it.)
 * The encrypted-entry resync (scan forward for the next magic) is
 * macutils' strategy; XADMaster instead decrypts with a password,
 * which is out of scope for v1.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define PIT_HDR 94

int unc_packit_probe(const uint8_t *head, int32_t len)
{
    /* Source: XADPackItParser.m recognizeFileWithHandle. */
    if (len < 4) return 0;
    if (head[0] == 'P' && head[1] == 'M' && head[2] == 'a' &&
        (head[3] == 'g' || head[3] == '4' || head[3] == '5' || head[3] == '6'))
        return 1;
    return 0;
}

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

int unc_packit_extract(UncCtx *c)
{
    uint8_t *iobuf, *obuf;
    uint32_t iocap = 4096, ocap = 4096;
    UncHuff *huff;
    UncBufIn in;
    uint8_t magic[4];
    int err = UNC_OK;
    int first = 1;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap);
    if (!iobuf) return UNC_ERR_MEM;
    obuf = iobuf + iocap;
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
        int comp, encrypted, sret, eerr;

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

        if (encrypted) {
            /* Report a nameless encrypted entry, then resync. */
            unc_entry_clear(&e);
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; goto out; }
            if (sret == 0 &&
                c->sink->end_entry(c->sink->ctx, UNC_ERR_ENCRYPTED) < 0) {
                err = UNC_ERR_SINK;
                goto out;
            }
            if (pit_resync(&in, magic) != UNC_OK) {
                err = UNC_OK;   /* clean EOF while scanning */
                goto out;
            }
            goto resynced;
        }

        st.in = &in;
        st.huff = NULL;
        st.err = UNC_OK;
        unc_bitin_init(&st.bits, &in);
        if (comp) {
            err = unc_huff_read_tree(huff, &st.bits);
            if (err != UNC_OK) goto out;
            st.huff = huff;
        }

        err = pit_read(&st, hdr, PIT_HDR);
        if (err != UNC_OK) goto out;

        /* Header CRC over the first 92 bytes (source: macutils pit.c). */
        if (unc_crc16_xmodem(0, hdr, PIT_HDR - 2) != unc_get_u16be(hdr + 92)) {
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
        if (eerr == UNC_ERR_SINK || eerr == UNC_ERR_ABORTED ||
            eerr == UNC_ERR_IO || eerr == UNC_ERR_TRUNCATED) {
            err = eerr == UNC_ERR_TRUNCATED ? UNC_OK : eerr;
            goto out;
        }
        /* For compressed entries the next block begins at the next
         * byte boundary; bufin is already positioned there because the
         * bit reader only buffers whole bytes and unc_bitin_align
         * discards the remainder of the current byte. */
        unc_bitin_align(&st.bits);
    }

out:
    unc_free(c->al, huff);
    unc_free(c->al, iobuf);
    return err;
}
