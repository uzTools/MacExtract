/*
 * macextract_destdlg.r — the destination dialog with a New Folder button on
 * every System. A proof of concept, built only with UNC_POC_DESTDLG set
 * (mac/CMakeLists.txt). License: LGPL-2.1-or-later.
 */
#include "Dialogs.r"
#include "macextract_strings.h"

/* PoC (UNC_POC_DESTDLG): the destination dialog. Standard File's Save
 * dialog for SFPPutFile, items 1-8 numbered as Standard File numbers them,
 * each placed where System 7.0.1's own Save dialog puts it (measured on
 * screen: content at 112,120, 344x188). Item 3, the prompt Standard File
 * fills in, and item 7, the name box, are parked off-screen: the prompt is
 * item 11, and Option B has no name box. Item 9 is New, a button with no
 * title; item 10 draws its word and folder and the divider below it
 * (DrawNewButton), as Apple's own button is drawn rather than titled. The
 * 'dctb' makes it a colour window where Color QuickDraw exists, which the
 * colour folder and Mac OS 9's text smoothing need. Source for its bytes:
 * System 7.0.1's System file, whose 'dctb' -6043, -6042 and -6046 (Standard
 * File's own dialogs) are these 8 bytes exactly — seed 0, flags 0, count
 * -1: no entries, default colours. */
resource 'DLOG' (140, purgeable, preload) {
    { 0, 0, 188, 344 },
    dBoxProc, invisible, noGoAway, 0, 140, "", noAutoCenter
};

resource 'DITL' (140, purgeable, preload) {
    {
        { 161, 252, 181, 332 }, Button     { enabled,  S_DEST_EXTRACT };
        { 130, 252, 150, 332 }, Button     { enabled,  S_BTN_CANCEL };
        {1136,  15,1176, 230 }, StaticText { disabled, "" };
        {   8, 232,  28, 340 }, UserItem   { disabled };
        {  32, 252,  52, 332 }, Button     { enabled,  S_DEST_EJECT };
        {  60, 252,  80, 332 }, Button     { enabled,  S_DEST_DRIVE };
        {1157,  17,1173, 194 }, EditText   { enabled,  "" };
        {  29,  12, 127, 230 }, UserItem   { disabled };
        {  88, 252, 108, 332 }, Button     { enabled,  "" };
        {  88, 251, 120, 334 }, UserItem   { disabled };
        { 136,  15, 176, 230 }, StaticText { disabled, S_DEST_PROMPT };
    }
};

data 'dctb' (140, purgeable, preload) {
    $"0000 0000 0000 FFFF"
};

/* The New Folder window. Source: System 7.0.1's System file, DLOG/DITL
 * -6046, Standard File's own, items 1-4 as they are; its item 5, a Balloon
 * Help item (a type System 7 introduced), is left out, and it is placed
 * over the destination dialog rather than at -6046's (40, 40). */
resource 'DLOG' (141, purgeable, preload) {
    { 140, 150, 230, 354 },
    dBoxProc, visible, noGoAway, 0, 141, "", noAutoCenter
};

resource 'DITL' (141, purgeable, preload) {
    {
        { 61, 130, 81, 190 }, Button     { enabled,  S_NF_CREATE };
        { 61,  10, 81,  70 }, Button     { enabled,  S_BTN_CANCEL };
        { 33,  12, 49, 189 }, EditText   { enabled,  S_NF_UNTITLED };
        {  8,  10, 28, 178 }, StaticText { disabled, S_NF_ASK };
        { 57, 126, 85, 194 }, UserItem   { disabled };  /* Create's ring */
    }
};
