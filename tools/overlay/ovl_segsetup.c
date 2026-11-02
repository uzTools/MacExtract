/*
 * ovl_segsetup.c — a segmented set's setup as an image of its own,
 * bundled so that it is read at launch and given back with the bundle
 * before the engine takes its budget. The code is mac/seg_setup.inc.c,
 * which the lazy and resident instruments compile into the application
 * (mac/macextract_mac.c, UNC_SHELL_IMAGES); here every resident call goes
 * through the SegSetupFns the application passes as `b`.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "overlay.h"
#include <Files.h>
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

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    (void)host;
    if (which != OVL_SEGSETUP_RUN) return UNC_ERR_IO;
    gF = (const SegSetupFns *)b;
    return SegSetup((const SegSetupArgs *)a);
}
