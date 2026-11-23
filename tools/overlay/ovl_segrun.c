/*
 * ovl_segrun.c — a segmented set's run-time shell code as an image of its
 * own: kept by a set when the bundle is given back (mac/release_plan.inc.c)
 * and given back with it by anything else. The code is mac/seg_run.inc.c,
 * which the lazy and resident instruments compile into the application
 * (mac/macextract_mac.c, UNC_SHELL_IMAGES); here every resident name it
 * uses is the SegRunFns entry the application passes as `b`.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "overlay.h"
#include <Files.h>
#include "../../mac/fm_inline.h"
#include <Memory.h>
#include <Dialogs.h>
#include <Devices.h>
#include <Events.h>
#include <OSUtils.h>
#include <StandardFile.h>
#include <TextUtils.h>
#include <ToolUtils.h>
#include <Windows.h>
#include <LowMem.h>
#include "macextract.h"
#include "../../mac/macextract_strings.h"
#include "../../mac/seg_types.h"

/* In .data, not .bss (mkoverlay.sh): set on every entry. */
static const SegRunFns *gR = (const SegRunFns *)1;

#define MyHCreate               (gR->MyHCreate)
#define MyHDelete               (gR->MyHDelete)
#define MyOpenFork              (gR->MyOpenFork)
#define PStrCat                 (gR->PStrCat)
#define PStrCatNum              (gR->PStrCatNum)
#define ShowNote                (gR->ShowNote)
#define WaitForFront            (gR->WaitForFront)
#define HideInvisible           (gR->HideInvisible)
#define unc_segment_describe_as (gR->unc_segment_describe_as)
#define unc_segment_first_end   (gR->unc_segment_first_end)
#define unc_segment_match       (gR->unc_segment_match)
#define unc_segment_name_part   (gR->unc_segment_name_part)
#define fio_read                (gR->fio_read)
#define fio_seek                (gR->fio_seek)
#define fio_tell                (gR->fio_tell)
#define fio_size                (gR->fio_size)
#define StackSample() ((void)(gR->StackSample ? gR->StackSample(), 0 : 0))
#define gSegShort               (*gR->pSegShort)
#define gBackground             (*gR->pBackground)

#define SEG_DATA __attribute__((section(".data")))
#include "../../mac/seg_run.inc.c"

static const SegRunExports gX = {
    SegTmpOpen, SegRemember, SegScanDir, SegScanFamily, SegPartLength,
    SegPartOf,
#ifdef UNC_MAC_AUTOTEST
    NULL,
#else
    SegAskUser,
#endif
    seg_need, seg_part_size, seg_release, SegPeelClean
};

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    (void)host; (void)a;
    if (which != OVL_SEGRUN_INIT) return 0;
    gR = (const SegRunFns *)b;
    return (int32_t)(long)&gX;
}
