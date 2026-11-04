/* fz_decoders.c — one libFuzzer harness per decoder entry point, chosen at
 * compile time with -DFZ_<TARGET> (tools/fuzz/build.sh builds them all).
 *
 * Each feeds the decoder its raw stream behind fz_common.h's six-byte
 * header and nothing else: no magic, no header CRC, no directory. The
 * decoders whose entry point is static are reached by including their
 * file, and build.sh leaves that file's object out of the link.
 *
 * Targets, and what `param` means to each:
 *   SIT       StuffIt fork decoder, unc_sit_decode_fork: method = param
 *             & 15 from {0,1,2,3,5,6,8,13,14,15} (the classic methods,
 *             13, 14 and Arsenic, as the container hands them a fork)
 *   SIT13 / SIT14 / ARSENIC   the same entry, method fixed
 *   DD        DiskDoubler dd_fork: method = param % 11 (0-10; 8 is the
 *             Compact Pro path), xorval = param >> 7 ? 0x5A : 0
 *   DDN       dd_fork, method 10 (dd_ddn_run)
 *   LZH_STATIC  -lh4- to -lh7- (param & 3), lzh_decode
 *   LZH_DYN   -lh1-, -lh2-, -lh3-, -lz5-, -lzs- (param % 5), lzh_decode
 *   NOW       Now Compress block shapes: param % 4 = Huffman only,
 *             LZSS only, new LZSS (shape 3), Huffman then LZSS
 *   SPACESAVER  ss_one_fork: method = param & 0x87 (0-4, bit 7 kept)
 *   IMPLODE / SHRINK / REDUCE   zip methods 6, 1, 2-5 (Reduce's factor
 *             = 1 + param % 4; Implode's flags = param & 6, mmlbug =
 *             param & 1)
 *   SUPERDISK sd_fork over a sequence of blocks
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fz_common.h"

#if defined(FZ_DD) || defined(FZ_DDN)
#include "../../src/fmt_dd.c"
#endif
#if defined(FZ_LZH_STATIC) || defined(FZ_LZH_DYN)
#include "../../src/fmt_lzh.c"
#endif
#if defined(FZ_NOW)
#include "../../src/fmt_now.c"
#endif
#if defined(FZ_SPACESAVER)
#include "../../src/fmt_spacesaver.c"
#endif
#if defined(FZ_SUPERDISK)
#include "../../src/fmt_superdisk.c"
#endif

/* Exact-size heap blocks, so ASan sees one byte past any of them. */
static uint8_t *fz_buf(uint32_t n) { return (uint8_t *)malloc(n ? n : 1); }

static int fz_emit(void *ctx, const uint8_t *p, uint32_t n)
{
    (void)ctx; (void)p; (void)n;
    return UNC_OK;
}

#if defined(FZ_SIT) || defined(FZ_SIT13) || defined(FZ_SIT14) || defined(FZ_ARSENIC)
static int fz_run(Fz *z)
{
    static const uint8_t methods[10] = { 0, 1, 2, 3, 5, 6, 8, 13, 14, 15 };
    uint8_t *iobuf = fz_buf(UNC_IOBUF), *obuf = fz_buf(UNC_STAGE);
    int m;
#if defined(FZ_SIT13)
    m = 13;
#elif defined(FZ_SIT14)
    m = 14;
#elif defined(FZ_ARSENIC)
    m = 15;
#else
    m = methods[z->param % 10];
#endif
    (void)methods;
    (void)unc_sit_decode_fork(&z->c, UNC_FORK_DATA, 0, z->n, z->outlen, m,
                              0, 0, iobuf, UNC_IOBUF, obuf, UNC_STAGE, NULL);
    free(iobuf);
    free(obuf);
    return 0;
}
#endif

#if defined(FZ_DD) || defined(FZ_DDN)
static int fz_run(Fz *z)
{
#if defined(FZ_DDN)
    int m = 10;
#else
    int m = z->param % 11;
#endif
    (void)dd_fork(&z->c, UNC_FORK_DATA, 0, z->n, z->outlen, m, 0, 0,
                  (z->param & 0x80) ? 0x5A : 0, 0);
    return 0;
}
#endif

#if defined(FZ_LZH_STATIC) || defined(FZ_LZH_DYN)
static int fz_run(Fz *z)
{
#if defined(FZ_LZH_STATIC)
    static const char *const names[4] = { "-lh4-", "-lh5-", "-lh6-", "-lh7-" };
    const char *mname = names[z->param & 3];
#else
    static const char *const names[5] = { "-lh1-", "-lh2-", "-lh3-",
                                          "-lz5-", "-lzs-" };
    const char *mname = names[z->param % 5];
#endif
    LzhEnt e;
    UncForkOut o;
    uint8_t *iobuf = fz_buf(UNC_IOBUF), *stage = fz_buf(UNC_STAGE);
    memset(&e, 0, sizeof e);
    memcpy(e.method, mname, 5);
    e.compsize = z->n;
    e.origsize = z->outlen;
    e.dataoff = 0;
    e.os = -1;
    unc_fork_out(&o, &z->c, UNC_FORK_DATA, 1, UNC_CK_CRC16_ARC, stage,
                 UNC_STAGE);
    (void)lzh_decode(&z->c, &e, &o, iobuf, UNC_IOBUF);
    free(iobuf);
    free(stage);
    return 0;
}
#endif

#if defined(FZ_NOW)
/* now_next_block's buffers at their caps, each its own block: the input
 * staging (incap), the output after a history (hist + blkcap). The
 * staged-input shapes put their input in `outstart`, as the reader does,
 * which is why a block longer than blkcap is refused there first. */
static int fz_run(Fz *z)
{
    uint32_t hist = NOW_HISTORY, blkcap, incap = NOW_INBLOCK;
    uint32_t len = z->n;
    struct NowCodes *cd = (struct NowCodes *)malloc(sizeof *cd);
    uint8_t *inblock, *outblock, *outstart;
    int32_t out, mid;
    int err = UNC_OK;

    blkcap = z->outlen ? z->outlen : 1;
    if (blkcap > NOW_OUTBLOCK - NOW_HISTORY) blkcap = NOW_OUTBLOCK - NOW_HISTORY;
    inblock = fz_buf(incap);
    outblock = fz_buf(hist + blkcap);
    outstart = outblock + hist;
    memset(outblock, 0, hist);
    memset(cd, 0, sizeof *cd);

    switch (z->param & 3) {
    case 0:                                      /* Huffman only */
        if (len > incap) break;
        memcpy(inblock, z->stream, len);
        out = now_huffman(inblock, len, outstart, blkcap, 0x100, &cd->one,
                          &err);
        break;
    case 1:                                      /* LZSS only */
        if (len > incap) break;
        memcpy(inblock, z->stream, len);
        out = now_lzss(inblock, len, outstart, blkcap, &err);
        break;
    case 2:                                      /* new LZSS */
        if (len > incap) break;
        memcpy(inblock, z->stream, len);
        out = now_newlzss(inblock, len, outstart - hist, outstart, blkcap,
                          cd, &err);
        break;
    default:                                     /* Huffman, then LZSS */
        if (len > blkcap) break;
        memcpy(outstart, z->stream, len);
        mid = now_huffman(outstart, len, inblock, incap, 0x100, &cd->one,
                          &err);
        if (mid < 0) break;
        out = now_lzss(inblock, (uint32_t)mid, outstart, blkcap, &err);
        break;
    }
    (void)out;
    free(inblock);
    free(outblock);
    free(cd);
    return 0;
}
#endif

#if defined(FZ_SPACESAVER)
static int fz_run(Fz *z)
{
    SsState *s = (SsState *)calloc(1, sizeof *s);
    SsFork f;
    uint8_t *iobuf = fz_buf(UNC_IOBUF);
    f.clen = z->n;
    f.ulen = z->outlen;
    f.off = 0;
    f.pset = 0;
    f.method = (uint8_t)(z->param & 0x87);
    unc_fork_out(&s->out, &z->c, UNC_FORK_DATA, 1, UNC_CK_NONE, s->sbuf,
                 UNC_STAGE);
    if (f.ulen) (void)ss_one_fork(s, &f, iobuf, UNC_IOBUF);
    free(iobuf);
    free(s);
    return 0;
}
#endif

#if defined(FZ_SUPERDISK)
static int fz_run(Fz *z)
{
    SdState s;
    memset(&s, 0, sizeof s);
    sd_out_start(&s, &z->c, UNC_FORK_DATA);
    if (z->outlen) (void)sd_fork(&s, 0, z->outlen);
    unc_free(&z->al, s.in.p);
    unc_free(&z->al, s.flags.p);
    unc_free(&z->al, s.table.p);
    unc_free(&z->al, s.win.p);
    return 0;
}
#endif

#if defined(FZ_IMPLODE) || defined(FZ_SHRINK) || defined(FZ_REDUCE)
static int fz_run(Fz *z)
{
    UncBufIn in;
    uint8_t *iobuf = fz_buf(UNC_IOBUF), *obuf = fz_buf(2u * UNC_IOBUF);
    uint32_t crc = 0;
    unc_bufin_init(&in, &z->io, &z->c.ps, iobuf, UNC_IOBUF);
    in.limit = z->n;
#if defined(FZ_IMPLODE)
    (void)unc_implode_decode(&z->al, &in, z->param & 6u, z->outlen, &crc,
                             z->param & 1u, fz_emit, NULL);
#elif defined(FZ_SHRINK)
    (void)unc_shrink_decode(&z->al, &in, z->outlen, &crc, obuf,
                            2u * UNC_IOBUF, fz_emit, NULL);
#else
    (void)unc_reduce_decode(&z->al, &in, 1u + z->param % 4u, z->outlen,
                            &crc, obuf, 2u * UNC_IOBUF, fz_emit, NULL);
#endif
    free(iobuf);
    free(obuf);
    return 0;
}
#endif

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    Fz z;
    if (!fz_init(&z, data, size)) return 0;
    fz_run(&z);
    fz_done(&z);
    return 0;
}
