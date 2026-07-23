/*
 * unc_inflate.c — zlib raw-inflate bridge for zip (method 8) and gzip.
 *
 * The engine's no-libc rule is satisfied by routing zlib's allocator
 * through UncAlloc; input comes from an UncBufIn (which drives the
 * progress pump) and output goes through the caller's chunk callback.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 * zlib itself is vendored unmodified in third_party/zlib (zlib
 * license).
 */
#include "unc_internal.h"

#include "../third_party/zlib/zlib.h"

static voidpf unc_zalloc(voidpf opaque, uInt items, uInt size)
{
    UncAlloc *al = (UncAlloc *)opaque;
    uint32_t total = (uint32_t)items * (uint32_t)size;
    return unc_alloc(al, total);
}

static void unc_zfree(voidpf opaque, voidpf addr)
{
    UncAlloc *al = (UncAlloc *)opaque;
    unc_free(al, addr);
}

int unc_inflate_raw(UncBufIn *in, UncAlloc *al,
                    uint8_t *obuf, uint32_t ocap,
                    uint32_t maxout, uint32_t *produced, uint32_t *crc,
                    int (*emit)(void *ctx, const uint8_t *p, int32_t n),
                    void *ectx)
{
    z_stream zs;
    int zerr, err = UNC_OK;
    uint32_t total = 0;

    zs.zalloc = unc_zalloc;
    zs.zfree = unc_zfree;
    zs.opaque = al;
    zs.next_in = Z_NULL;
    zs.avail_in = 0;
    if (inflateInit2(&zs, -15) != Z_OK) return UNC_ERR_MEM;

    for (;;) {
        if (zs.avail_in == 0) {
            /* Refill from the buffered reader. unc_bufin_next both
             * refills and consumes one byte; hand zlib that byte plus
             * whatever remains in the window. */
            int b = unc_bufin_next(in);
            if (b < 0) {
                err = in->err == UNC_ERR_TRUNCATED ? UNC_ERR_TRUNCATED
                                                   : in->err;
                break;
            }
            zs.next_in = in->buf + in->pos - 1;
            zs.avail_in = in->len - in->pos + 1;
            in->pos = in->len;   /* consumed below by zlib */
        }

        zs.next_out = obuf;
        zs.avail_out = ocap;
        zerr = inflate(&zs, Z_NO_FLUSH);
        if (zerr != Z_OK && zerr != Z_STREAM_END && zerr != Z_BUF_ERROR) {
            err = UNC_ERR_CORRUPT;
            break;
        }

        {
            uint32_t got = ocap - zs.avail_out;
            if (got) {
                if (maxout != UNC_SIZE_UNKNOWN && total + got > maxout) {
                    err = UNC_ERR_CORRUPT;   /* more output than declared */
                    break;
                }
                if (crc) *crc = unc_crc32(*crc, obuf, (int32_t)got);
                if (emit && emit(ectx, obuf, (int32_t)got) != UNC_OK) {
                    err = UNC_ERR_SINK;
                    break;
                }
                total += got;
            }
        }

        if (zerr == Z_STREAM_END) break;
    }

    /* Return unread input bytes to the window so the caller can parse
     * whatever follows the deflate stream (gzip trailer, next member). */
    in->pos = in->len - zs.avail_in;

    inflateEnd(&zs);
    *produced = total;
    return err;
}
