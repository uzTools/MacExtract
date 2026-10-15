/* Resources.h — the Resource Manager calls the overlay loaders make.
 *
 * A STUB for tests/run_overlay_host.sh; see tests/ovlbox/toolbox/Memory.h.
 * The resources themselves are registered by the harness from the image
 * files the build just wrote (ovlbox_add_resource), so the loader reads the
 * same bytes a Macintosh does.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef OVLBOX_RESOURCES_H
#define OVLBOX_RESOURCES_H

#include "Memory.h"

typedef unsigned long ResType;

Handle GetResource(ResType type, short id);
void   ReleaseResource(Handle h);
void   DetachResource(Handle h);
short  ResError(void);
void   SetResLoad(Boolean load);
long   GetResourceSizeOnDisk(Handle h);   /* the classic SizeRsrc, A9A5 */

#endif /* OVLBOX_RESOURCES_H */
