/*
 * ovl_segsetup.c — a segmented set's setup as an image of its own,
 * bundled so that it is read at launch and given back with the bundle
 * before the engine takes its budget. The code is mac/seg_setup.inc.c,
 * which the lazy and resident instruments compile into the application
 * (mac/macextract_mac.c, UNC_SHELL_IMAGES); here every resident call goes
 * through the SegSetupFns the application passes as `b`.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "overlay.h"
#include <Files.h>
#include "../../mac/fm_inline.h"  /* its own FSClose, GetEOF, FSWrite, FlushVol */
#include <Memory.h>
#include <Dialogs.h>
#include <LowMem.h>
#include "macextract.h"
#include "../../mac/seg_types.h"

/* In .data, not .bss: an image may carry initialised data and no .bss
 * (mkoverlay.sh), so it starts non-zero and is set on every entry. */
static const SegSetupFns *gF = (const SegSetupFns *)1;
#define SS(f) (gF->f)

#include "../../mac/seg_setup.inc.c"

/* NewHandle then MoveHHi, on every ROM, a 64K ROM having no MoveHHi
 * (FORMATS.md, *A true Macintosh 512K*): a handle as high as the heap allows.
 * CompactMem gives the largest free block after compaction and purges
 * nothing; a pointer filling all of it but the handle's room takes its
 * bottom, since NewPtr places a block as low as it can; the handle takes
 * the top, and the filler goes. Failing that, a plain NewHandle. Source:
 * Inside Macintosh II, The Memory Manager (CompactMem, NewPtr, NewHandle).
 * In this image rather than resident, so it is carried only in the bundle
 * given back (mac/ovl_load_eager.c, ovl_keep; DECISIONS.md 2026-11-09,
 * *one way to keep a decoder high*). */
static int32_t high_handle(Size len)
{
    Size room = CompactMem(0x7FFFFFF0L) - len - 1024;
    Ptr fill = room > 0 ? NewPtr(room) : NULL;
    Handle h = NewHandle(len);
    if (fill != NULL) DisposePtr(fill);
    if (h == NULL) h = NewHandle(len);
    return (int32_t)h;
}

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    (void)host;
    if (which == OVL_HIGH_HANDLE) return high_handle((Size)b);
    if (which != OVL_SEGSETUP_RUN) return UNC_ERR_IO;
    gF = (const SegSetupFns *)b;
    return SegSetup((const SegSetupArgs *)a);
}
