/* ovl_reloc.c — the two things both overlay lifetimes do to an image.
 *
 * Applying the relocation trailer, and telling the processor that what was
 * just written as data is now instructions. Neither depends on WHEN the
 * image was read, which is the whole of the difference between
 * mac/ovl_load_eager.c and mac/ovl_load_lazy.c.
 */
#include "ovl_load.h"
#include <OSUtils.h>

#ifdef UNC_AT_BUDGET
/* Diagnostics, in the probe build only, and worth keeping: they are what
 * found the preload that was called from one main() and not the other. `wa`
 * is an image wanted AFTER the release — which must never happen, since
 * there is no reload — `kf` says why a keep failed, and `rf` is the format
 * the release decided on. Printed on the completion alert. */
short gWantedAfterRelease, gKeepFail, gRelFmt;
/* `fc` is which flush route this machine offers — 0 none, 1 _HWPriv, 2
 * FlushCodeCache — and `fn` how many times one was called. Without them the
 * flush is a line nobody can watch fail: every tier here is either cacheless
 * or documented to ignore the request, so a green sweep says nothing about
 * whether the call was even reached. These two say which. */
short gFlushHas, gFlushCalls;
#define OVL_DIAG(stmt) do { stmt; } while (0)
#else
#define OVL_DIAG(stmt) ((void)0)
#endif

unsigned long ovl_be32(const unsigned char *p)
{
    return ((unsigned long)p[0] << 24) | ((unsigned long)p[1] << 16) |
           ((unsigned long)p[2] << 8) | (unsigned long)p[3];
}

unsigned short ovl_be16(const unsigned char *p)
{
    return (unsigned short)(((unsigned short)p[0] << 8) | p[1]);
}



void ovl_fixup(unsigned char *base, unsigned long size, long delta)
{
    unsigned long n, i, table;
    if (size < 4) return;
    n = ovl_be32(base + size - 4);
    if (n == 0) return;
    if (n > (size - 4) / 4) return;          /* not ours; leave it alone */
    table = size - 4 - n * 4;
    for (i = 0; i < n; i++) {
        unsigned long off = ovl_be32(base + table + i * 4);
        unsigned long v;
        if (off + 4 > table) continue;       /* outside the image proper */
        v = ovl_be32(base + off) + (unsigned long)delta;
        base[off]     = (unsigned char)(v >> 24);
        base[off + 1] = (unsigned char)(v >> 16);
        base[off + 2] = (unsigned char)(v >> 8);
        base[off + 3] = (unsigned char)v;
    }
}

/* Newly written instruction bytes have to reach the instruction stream, and
 * this is a documented requirement rather than a precaution.
 *
 * Both fixup sites write code AS DATA and then execute it: ovl_bundle_fixup
 * rewrites longs inside the bundle at load, and ovl_keep copies an image with
 * BlockMoveData and fixes it up again at the copy's address.
 *
 * Source: Inside Macintosh: Memory, chapter 4, *Stale Instructions* — "you
 * must flush the instruction cache every time you modify executable
 * instructions in memory", and it names modifying jump-table entries and
 * installing patches by copying code as the cases. _BlockMove, _Read, _LoadSeg
 * and _UnloadSeg flush on the application's behalf; BlockMoveData is the
 * variant trap (0xA22E against _BlockMove's 0xA02E) and is not among them, so
 * ovl_keep's copy is exactly the case the chapter is about. Retro68's own
 * relocator flushes at the same two moments — after Retro68ApplyRelocations
 * and after patching each jump-table entry (libretro/relocate.c,
 * libretro/MultiSegApp.c) — which is where the trap-availability probe below
 * comes from.
 *
 * TWO traps, because the one the toolchain uses is not the documented one.
 * Retro68 calls FlushCodeCache (0xA0BD). Inside Macintosh: Memory documents
 * FlushInstructionCache as _HWPriv (0xA198) selector 1, and says that on a
 * processor with a copy-back data cache it flushes the DATA cache first, "to
 * ensure that any instructions subsequently copied to the instruction cache
 * are not copied from stale RAM" — which is the 68040 case, and the case a
 * BlockMoveData copy creates. So _HWPriv is preferred where it exists and
 * 0xA0BD is the fallback for the older ROMs that have only that.
 *
 * WHAT NO TIER HERE CAN SHOW. Mini vMac emulates a 68000, which has no cache,
 * and Apple documents that the 68LC040 Emulator — how the Mac OS 9 tier runs
 * this application — IGNORES requests to invalidate the 68040 instruction
 * cache, while telling developers to keep issuing them for 680x0 machines
 * (Inside Macintosh: PowerPC System Software, *The 68LC040 Emulator*). So a
 * green sweep on any tier this project can run is not evidence that the call
 * works, and the gFlushHas/gFlushCalls diagnostics below are what a run can
 * actually report: which route was taken, and how many times. Real 68020-and-up
 * silicon is MANUAL_TESTS.md's. */
static int gFlushProbed;
static int gFlushRoute;         /* 0 none, 1 _HWPriv, 2 FlushCodeCache */

static int ovl_trap_live(unsigned short trap)
{
    return GetOSTrapAddress(trap) != GetOSTrapAddress(_Unimplemented);
}

void ovl_flush_code(void)
{
    if (!gFlushProbed) {
        const short *rom85 = (const short *)0x028EL;   /* >0 on a 128K ROM */
        gFlushProbed = 1;
        if (*rom85 > 0) {                    /* a 64K ROM has neither trap */
            if (ovl_trap_live(_HWPriv)) gFlushRoute = 1;
            else if (ovl_trap_live(0xA0BD)) gFlushRoute = 2;
        }
        OVL_DIAG(gFlushHas = (short)gFlushRoute);
    }
    if (gFlushRoute == 1) HWPriv(1, 0);      /* FlushInstructionCache */
    else if (gFlushRoute == 2) FlushCodeCache();
    else return;
    OVL_DIAG(gFlushCalls++);
}
