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
#define UNC_AT_OVERLAY 1     /* as the application: the shell finds the reader */
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
#include "unc_internal.h"
#include "../../mac/macextract_strings.h"
#include "../../mac/seg_types.h"

/* In .data, not .bss (mkoverlay.sh): set on every entry. */
static const SegRunFns *gR = (const SegRunFns *)1;

/* The joiner (src/unc_segment.c) is this image's too: only a set reaches it,
 * after the release plan has kept this image. What it calls in the engine
 * is a SegRunFns entry, and the sniffer's three hooks go through one. Its
 * statics that share a name with the set code's are renamed for the
 * length of the include. */
#define unc_run                 (gR->unc_run)
#define unc_read_at             (gR->unc_read_at)
#define unc_io_size32           (gR->unc_io_size32)
/* In the joiner's table of hooks, which a constant initialiser fills. */
static uint16_t jn_crc_arc(uint16_t crc, const uint8_t *b, int32_t n)
{
    return gR->unc_crc16_arc(crc, b, n);
}
static uint16_t jn_crc_xmodem(uint16_t crc, const uint8_t *b, int32_t n)
{
    return gR->unc_crc16_xmodem(crc, b, n);
}
#define unc_crc16_arc           jn_crc_arc
#define unc_crc16_xmodem        jn_crc_xmodem
int unc_sitseg_emit(UncCtx *c, const UncSegmentDesc *desc, uint32_t base,
                    int data_first, const int *ioerr)
{
    OvlArgs g;
    g.obj = c; g.in = desc; g.len = base; g.pos = (uint32_t)data_first;
    g.out = (void *)ioerr;
    return (int)gR->ovl_seg_hook(OVL_SITSEG_EMIT, &g);
}
int unc_ddseg_payload(const UncSegmentDesc *desc, const uint8_t *head,
                      int32_t len, int part, uint32_t size, uint32_t *payload)
{
    OvlArgs g;
    g.obj = (void *)desc; g.in = head; g.len = (uint32_t)len;
    g.pos = (uint32_t)part; g.extra = size; g.off_out = payload;
    return (int)gR->ovl_seg_hook(OVL_DDSEG_PAYLOAD, &g);
}
int unc_mimeseg_head(const UncSegmentDesc *d, UncIO *io, int part,
                     uint32_t size, uint32_t *out)
{
    OvlArgs g;
    g.obj = (void *)d; g.in = io; g.pos = (uint32_t)part; g.extra = size;
    g.off_out = out;
    return (int)gR->ovl_seg_hook(OVL_MIMESEG_HEAD, &g);
}
#define seg_release  join_release
#define seg_part_size join_part_size
#include "../../src/unc_segment.c"
#undef seg_release
#undef seg_part_size

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
    seg_need, seg_part_size, seg_release, SegPeelClean,
    unc_extract_segments
};

int32_t ovl_main(const OverlayHost *host, int32_t which, void *a, void *b)
{
    (void)host; (void)a;
    if (which != OVL_SEGRUN_INIT) return 0;
    gR = (const SegRunFns *)b;
    return (int32_t)(long)&gX;
}
