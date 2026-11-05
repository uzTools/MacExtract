/* Dialogs.h — the Dialog Manager call the eager overlay loader makes.
 *
 * A STUB for tests/run_overlay_host.sh; see tests/ovlbox/toolbox/Memory.h.
 * The loader raises one alert, when the bundle cannot be read again under an
 * envelope whose peek was wrong (mac/ovl_load_eager.c); the mock counts it.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef OVLBOX_DIALOGS_H
#define OVLBOX_DIALOGS_H

short StopAlert(short alertID, void *filterProc);

#endif /* OVLBOX_DIALOGS_H */
