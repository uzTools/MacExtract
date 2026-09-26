/* ovlbox.h — what a harness asks of the mock Toolbox under tests/ovlbox/.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef OVLBOX_H
#define OVLBOX_H

#include <stddef.h>
#include "toolbox/Resources.h"

/* Register an 'OVLY' resource. The harness reads the image files the build
 * just wrote and hands the bytes over; GetResource then serves them to the
 * real loader. A copy is kept, so the caller may free its buffer. */
int  ovlbox_add_resource(short id, const void *bytes, size_t len);

/* Register every image a build just wrote, from a manifest of
 * "<decimal resource id> <path>" lines — which is what
 * tests/run_overlay_host.sh writes beside the images. Returns the count, or
 * -1. Both harnesses take the manifest's path from $OVLBOX_IMAGES so a test
 * main needs three lines rather than an argument. */
int  ovlbox_load_manifest(const char *path);

/* The low-memory global ROM85 lives at 0x028E on a Macintosh; off one it is
 * this. mac/ovl_reloc.c is compiled with
 * -DOVL_LOWMEM_ROM85=ovlbox_rom85() so the file itself needs no change. */
const void *ovlbox_rom85(void);

/* Which flush route the mock offers: 1 _HWPriv (the default, the documented
 * one), 2 FlushCodeCache, 0 neither — a 64K ROM, where ovl_flush_code must
 * fall through without calling anything. */
void ovlbox_set_flush_route(int route);

/* Counters. Every one of these is a property no tier here can report:
 * `reads` is what says the eager lifetime reads the bundle ONCE and the lazy
 * one reads per format; `flushes` that the documented flush is reached at
 * both fixup sites; `moves` that the loader survives a heap that compacts. */
extern long ovlbox_reads;        /* GetResource calls that hit the "disk"   */
extern long ovlbox_flushes;      /* HWPriv/FlushCodeCache calls             */
extern long ovlbox_moves;        /* relocatable blocks moved by the mock    */
extern long ovlbox_handles;      /* handles currently allocated             */

/* Every relocatable (unlocked) block moves on every allocation. A real
 * Memory Manager compacts only when it must, so a loader that depends on an
 * unlocked handle staying put works on a Macintosh most of the time; here it
 * never does. Off only to measure what the shuffling itself costs. */
void ovlbox_set_shuffle(int on);

/* Guard pages sit immediately after every block, so a relocation or a
 * BlockMoveData past the image end faults rather than corrupting the heap.
 * This reports the sizes for a harness that wants to print them. */
void ovlbox_stats(long *live_bytes, long *peak_bytes);

#endif /* OVLBOX_H */
