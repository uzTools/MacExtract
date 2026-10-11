/* Memory.h — the Memory Manager calls the overlay loaders make, and no more.
 *
 * A STUB, for tests/run_overlay_host.sh only: it lets mac/ovl_load_eager.c,
 * mac/ovl_load_lazy.c and mac/ovl_shim.c compile UNMODIFIED off the
 * Macintosh, which is the whole point — a host-side copy of a loader would
 * grade itself. Implemented in tests/ovlbox/ovlbox.c.
 *
 * The shared types and the Ptr-level calls are mac/mac_mocks.h's, which the
 * sink test has used since 2026-08 for exactly this reason.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef OVLBOX_MEMORY_H
#define OVLBOX_MEMORY_H

#include "mac_mocks.h"

Handle NewHandle(Size n);
void   DisposeHandle(Handle h);
Size   GetHandleSize(Handle h);
void   HLock(Handle h);
void   HUnlock(Handle h);
void   HNoPurge(Handle h);
void   MoveHHi(Handle h);
OSErr  MemError(void);

#endif /* OVLBOX_MEMORY_H */
