/* OSUtils.h — the two cache-flush traps and the availability probe.
 *
 * A STUB for tests/run_overlay_host.sh; see tests/ovlbox/toolbox/Memory.h.
 * There is no cache on either host this runs on, so what the box can show is
 * that the call is REACHED, which it counts (tests/ovlbox/ovlbox.h). Whether
 * a flush was needed is real 68020-and-up silicon's answer and
 * MANUAL_TESTS.md's.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef OVLBOX_OSUTILS_H
#define OVLBOX_OSUTILS_H

#include "Memory.h"

#define _Unimplemented 0xA89F
#define _HWPriv        0xA198

void *GetOSTrapAddress(unsigned short trap);

/* ROM85 lives at 0x028E on a Macintosh and in a variable here;
 * mac/ovl_reloc.c is compiled with -DOVL_LOWMEM_ROM85=ovlbox_rom85() and is
 * otherwise untouched. Declared here because that file includes this header. */
const void *ovlbox_rom85(void);
void  HWPriv(short selector, long arg);
void  FlushCodeCache(void);

#endif /* OVLBOX_OSUTILS_H */
