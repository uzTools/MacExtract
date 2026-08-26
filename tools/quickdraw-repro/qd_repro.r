/*
 * qd_repro.r — one dialog, so probe 6 can exercise the Dialog Manager route
 * the shipped application actually takes (GetNewDialog + DrawDialog), not
 * just a bare NewWindow. Deliberately the same geometry and item list as
 * macextract's own progress dialog (mac/macextract.r), moved down the screen
 * so it cannot cover the framebuffer log.
 */
#include "Dialogs.r"

resource 'DLOG' (128, purgeable) {
    { 240, 80, 320, 400 },
    dBoxProc, visible, noGoAway, 0, 128, "", noAutoCenter
};

resource 'DITL' (128, purgeable) {
    {
        { 48, 220, 68, 300 }, Button { enabled, "Cancel" };
        { 12, 16, 28, 300 }, StaticText { disabled, "Probe 6: GetNewDialog" };
    }
};
