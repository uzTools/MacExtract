/*
 * macextract_progress.r — the progress window, in a file of its own so
 * that UNC_POC_COLORBAR, whose window 146 replaces it, can leave it out:
 * Retro68's Rez rule takes no -D. License: LGPL-2.1-or-later.
 */
#include "Dialogs.r"
#include "macextract_strings.h"

resource 'DLOG' (128, purgeable, preload) {
    { 80, 80, 190, 400 },
    noGrowDocProc, visible, noGoAway, 0, 128, S_PROGRESS_TITLE, noAutoCenter
};

/* Mac OS 8 and later: the progress window takes the theme's background
 * rather than white, as alerts already do; 'dlgx' 132 does the same for
 * the password dialog. No code reads either; Systems before Appearance
 * 1.0 ignore the type. Standard File's dialogs stay white: a 'dlgx' is
 * read only from its DLOG's own file, and theirs are the System's.
 * Source: flag bit — Mac OS 8 Toolbox Reference, Dialog Manager, *Dialog
 * Feature Flag Constants* (kDialogFlagsUseThemeBackground = 1 << 0).
 * Layout — measured on 100 of Apple's own 'dlgx' resources on the
 * Mac OS 9.2 disk: 6 bytes, version word 0 then a 32-bit flags word. */
data 'dlgx' (128, purgeable, preload) {
    $"0000 0000 0001"
};

resource 'DITL' (128, purgeable, preload) {
    {
        { 78, 220, 98, 300 }, Button     { enabled,  S_BTN_CANCEL };
        { 10,  16, 26, 300 }, StaticText { disabled, S_PROGRESS_STATUS };
        { 34,  16, 50, 300 }, UserItem   { enabled };
        { 56,  16, 72, 300 }, StaticText { disabled, "" };
    }
};

