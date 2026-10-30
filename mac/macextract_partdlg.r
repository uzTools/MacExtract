/*
 * macextract_partdlg.r — PoC (UNC_POC_PARTDLG): the part of a segmented set
 * that was not found is asked for in ONE dialog, Standard File's Open with
 * a prompt, instead of an alert whose Find... opened it. Built only with
 * UNC_POC_PARTDLG set (mac/CMakeLists.txt). License: LGPL-2.1-or-later.
 *
 * Items 1-10 are Apple's own Open dialog, DITL -4000, as read out of System
 * 3.0's and 6.0.8's System files (identical in both), numbered as Standard
 * File numbers them; item 10, the prompt SFGetFile ignores, stays parked
 * where Apple parks it. Item 11 is the prompt, below the list in a band
 * the dialog grows by; ^0 and ^1 are ParamText's (SegAskUser).
 */
#include "Dialogs.r"
#include "macextract_strings.h"

resource 'DLOG' (142, purgeable, preload) {
    { 0, 0, 236, 348 },
    dBoxProc, invisible, noGoAway, 0, 142, "", noAutoCenter
};

resource 'DITL' (142, purgeable, preload) {
    {
        { 138, 256, 156, 336 }, Button     { enabled,  "Open" };
        {1152,  59,1232,  77 }, Button     { enabled,  "" };
        { 163, 256, 181, 336 }, Button     { enabled,  S_BTN_CANCEL };
        {  39, 232,  59, 347 }, UserItem   { disabled };
        {  68, 256,  86, 336 }, Button     { enabled,  S_DEST_EJECT };
        {  93, 256, 111, 336 }, Button     { enabled,  S_DEST_DRIVE };
        {  39,  12, 185, 230 }, UserItem   { enabled };
        {  39, 229, 185, 246 }, UserItem   { enabled };
        { 124, 252, 125, 340 }, UserItem   { disabled };
        {1044,  20,1145, 116 }, StaticText { disabled, "" };
        { 194,  12, 230, 340 }, StaticText { disabled, S_SEG_MISSING };
    }
};

resource 'DLOG' (143, purgeable, preload) {
    { 0, 0, 236, 348 },
    dBoxProc, invisible, noGoAway, 0, 143, "", noAutoCenter
};

resource 'DITL' (143, purgeable, preload) {
    {
        { 138, 256, 156, 336 }, Button     { enabled,  "Open" };
        {1152,  59,1232,  77 }, Button     { enabled,  "" };
        { 163, 256, 181, 336 }, Button     { enabled,  S_BTN_CANCEL };
        {  39, 232,  59, 347 }, UserItem   { disabled };
        {  68, 256,  86, 336 }, Button     { enabled,  S_DEST_EJECT };
        {  93, 256, 111, 336 }, Button     { enabled,  S_DEST_DRIVE };
        {  39,  12, 185, 230 }, UserItem   { enabled };
        {  39, 229, 185, 246 }, UserItem   { enabled };
        { 124, 252, 125, 340 }, UserItem   { disabled };
        {1044,  20,1145, 116 }, StaticText { disabled, "" };
        { 194,  12, 230, 340 }, StaticText { disabled, S_SEG_INSERT };
    }
};
