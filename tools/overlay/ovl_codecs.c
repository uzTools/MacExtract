/* ovl_codecs.c — the shared codec machinery, in an overlay that patches
 * itself into the host vector.
 *
 * The bit reader, the Huffman and canonical coders, LZW and LZAH are called
 * by six decoders between them, which is why they were resident: an overlay
 * has no relocations and reaches outside itself only through the host vector,
 * whose entries the application fills with addresses of resident functions,
 * so one blob cannot call another.
 *
 * The way out is that the vector is just a struct of pointers, and nothing
 * requires a pointer in it to point at resident code. This overlay is loaded
 * before any decoder that needs it, and OVL_CODEC_EXPORTS writes the
 * addresses of its own functions into the application's copy of the vector.
 * Every decoder overlay then calls them exactly as it always did — through
 * `g_ovl_fns` — and never learns that the target moved.
 *
 * Assigning those addresses HERE rather than in a static table is the whole
 * trick: under -mpcrel taking a function's address in code is PC-relative and
 * costs no relocation, while a table of the same pointers in .data would need
 * one for each, and mkoverlay.sh refuses any.
 *
 * The alternative was duplicating this code into each of the decoder images
 * that call it — about 17 KB of extra download to save the same 8.5 KB of
 * RAM, measured when there were six images rather than fourteen. This costs
 * nothing but the mechanism.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "overlay.h"
#include "ovl_host_gen.h"
#include "ovl_codec_exports_gen.h"

const OverlayHostFns *g_ovl_fns = (const OverlayHostFns *)-1;

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b);
int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    (void)b;
    g_ovl_fns = (const OverlayHostFns *)host->fns;
    switch (which) {
    case OVL_SELFTEST:
        return 0x4F4B;
    case OVL_CODEC_EXPORTS:
        OVL_CODEC_EXPORTS_FILL((OverlayHostFns *)a);
        return 0;
    default:
        return -1;
    }
}
