/* ovl_spacesaver.c — the SpaceSaver decoder as an overlay.
 *
 * The first DECODER overlay, and the reason it took until 2026-09-02 to try
 * one is a comment: mkoverlay.sh's header said the build refuses `.data`,
 * while its code twenty lines down allowed it and explained why. Every
 * decoder has tables, tables are `.data`, so "no `.data`" ruled the whole set
 * out on paper and left the ciphers looking like the only candidate.
 *
 * SpaceSaver is the one to move first, measured rather than chosen: it is the
 * largest decoder in the binary and it has the fewest external references —
 * 6,560 B of resident CODE and 9,701 B of A5 world (`ss_dict0`, the biggest
 * single table this application carries), for a format most sessions never
 * meet. The A5 half is what no CODE-splitting scheme can reach, and the A5
 * world is the wall on the smallest machines (FORMATS.md, *A Macintosh 128K*).
 *
 * `src/fmt_spacesaver.c` is compiled in UNMODIFIED. What makes that possible
 * is below: every engine helper it calls is DEFINED here as a one-line
 * forward through the host vector, so the decoder's own source needs no
 * knowledge that it is in an overlay. `unc_spacesaver_probe` stays resident
 * in `src/fmt_spacesaver_probe.c` — a probe the sniffer runs on every file
 * must never be the reason a 16 KB blob is loaded.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "overlay.h"
#include "unc_internal.h"

/* Initialised to -1 and not to 0, which is the same trick ovl_crypt.c uses
 * and for the same reason: a zero initialiser lands in .bss, which objcopy
 * leaves out of the image, so the blob would write past its own end. This was
 * not remembered — mkoverlay.sh's .bss check caught it on the first build of
 * this overlay, which is the second time that check has paid for itself. */
static const OverlayHost *g_host = (const OverlayHost *)-1;

/* The twelve. Each is the engine symbol the decoder links against, defined
 * here as a forward. Signatures are copied from src/unc_internal.h; a
 * mismatch would be a silent wrong-arguments call across the boundary, so
 * they are checked by the fact that this file includes that header. */
void unc_bitin_align(UncBitIn *b)
{ g_host->bitin_align((struct UncBitIn *)b); }

int32_t unc_bitin_bits_le(UncBitIn *b, int n)
{ return g_host->bitin_bits_le((struct UncBitIn *)b, n); }

void unc_bitin_init_le(UncBitIn *b, UncBufIn *in)
{ g_host->bitin_init_le((struct UncBitIn *)b, (struct UncBufIn *)in); }

void unc_bufin_init(UncBufIn *b, UncIO *io, UncProgressState *ps,
                    uint8_t *storage, uint32_t cap)
{ g_host->bufin_init((struct UncBufIn *)b, (struct UncIO *)io,
                     (struct UncProgressState *)ps, storage, cap); }

int unc_bufin_next_slow(UncBufIn *b)
{ return g_host->bufin_next_slow((struct UncBufIn *)b); }

void unc_entry_clear(UncEntryInfo *e)
{ g_host->entry_clear((struct UncEntryInfo *)e); }

int unc_entry_set_name(UncEntryInfo *e, const uint8_t *name, uint32_t len)
{ return g_host->entry_set_name((struct UncEntryInfo *)e, name, len); }

void unc_entry_set_path(UncEntryInfo *e, const uint8_t *path, uint32_t len)
{ g_host->entry_set_path((struct UncEntryInfo *)e, path, len); }

int unc_fork_flush(UncForkOut *o)
{ return g_host->fork_flush((struct UncForkOut *)o); }

void unc_fork_out(UncForkOut *o, UncCtx *c, UncFork fork, int write,
                  int ck, uint8_t *buf, uint32_t cap)
{ g_host->fork_out((struct UncForkOut *)o, (struct UncCtx *)c, (int)fork,
                   write, ck, buf, cap); }

int unc_progress_add(UncProgressState *ps, uint32_t n)
{ return g_host->progress_add((struct UncProgressState *)ps, n); }

int unc_read_at(UncIO *io, unc_off_t pos, void *buf, int32_t len)
{ return g_host->read_at((struct UncIO *)io, (uint32_t)pos, buf, len); }

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b);
int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    (void)b;
    g_host = host;
    switch (which) {
    case OVL_SELFTEST:
        return 0x4F4B;
    case OVL_SPACESAVER_EXTRACT:
        return (int32_t)unc_spacesaver_extract((UncCtx *)a);
    default:
        return -1;
    }
}
