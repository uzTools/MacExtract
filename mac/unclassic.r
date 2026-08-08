/*
 * unclassic.r — resources for the unclassic Macintosh shell.
 * Compiled with Retro68's Rez. License: LGPL-2.1-or-later.
 */
#include "Dialogs.r"
#include "Processes.r"

/* Progress dialog. Four items, and the order is the item numbering the
 * code uses (kCancelItem..kDetailItem in unclassic_mac.c):
 *
 *   1  Cancel button          also reachable as Cmd-.
 *   2  status   "Extracting <name>"
 *   3  userItem the progress bar; drawn by BarUserItem, not by the Dialog
 *      Manager, so it repaints on update events as well as on every tick
 *   4  detail   "45%   about 2 minutes left"
 *
 * 110 points tall rather than 80: the bar and the detail line are new. */
resource 'DLOG' (128, purgeable) {
    { 80, 80, 190, 400 },
    dBoxProc, visible, noGoAway, 0, 128, "", noAutoCenter
};

resource 'DITL' (128, purgeable) {
    {
        { 78, 220, 98, 300 }, Button     { enabled,  "Cancel" };
        { 10,  16, 26, 300 }, StaticText { disabled, "Extracting" };
        { 34,  16, 50, 300 }, UserItem   { enabled };
        { 56,  16, 72, 300 }, StaticText { disabled, "" };
    }
};

resource 'ALRT' (129, purgeable) {
    { 90, 100, 190, 412 }, 129, {
        OK, visible, silent, OK, visible, silent,
        OK, visible, silent, OK, visible, silent
    }, noAutoCenter
};

resource 'DITL' (129, purgeable) {
    {
        { 68, 232, 88, 292 }, Button { enabled, "OK" };
        { 12, 64, 60, 300 }, StaticText { disabled, "^0" };
    }
};

resource 'ALRT' (130, purgeable) {
    { 90, 100, 190, 412 }, 130, {
        OK, visible, sound1, OK, visible, sound1,
        OK, visible, sound1, OK, visible, sound1
    }, noAutoCenter
};

resource 'DITL' (130, purgeable) {
    {
        { 68, 232, 88, 292 }, Button { enabled, "OK" };
        { 12, 64, 60, 300 }, StaticText { disabled, "^0" };
    }
};

/* "Locate part N" alert, for a segmented archive whose next part was not
 * found beside the one that was opened. Three buttons, in the order the
 * code tests them (kSegFindItem..kSegCancelItem in unclassic_mac.c):
 *
 *   1  Find...   opens Standard File so the user can point at it, on any
 *                mounted volume — including a disk inserted just now
 *   2  Skip      give up on this part; what was decoded so far is kept
 *   3  Cancel    stop the extraction
 *
 * The wording deliberately says "locate", not "insert the next disk": the
 * parts of a set are not assumed to be on separate floppies, or to be
 * named alike, or to be anywhere in particular. */
resource 'ALRT' (131, purgeable) {
    { 90, 80, 214, 452 }, 131, {
        OK, visible, sound1, OK, visible, sound1,
        OK, visible, sound1, OK, visible, sound1
    }, noAutoCenter
};

resource 'DITL' (131, purgeable) {
    {
        { 92, 282, 112, 352 }, Button { enabled, "Find..." };
        { 92, 196, 112, 266 }, Button { enabled, "Skip" };
        { 92, 110, 112, 180 }, Button { enabled, "Cancel" };
        { 10, 16, 84, 356 }, StaticText { disabled, "^0" };
    }
};

/* MultiFinder/System 7 friendliness; System 6 Finder ignores it (there the
 * app just gets all free RAM). Preferred 4 MB lets the engine use a large
 * runtime budget on a roomy machine (Arsenic/SIT5 needs ~2.6 MB); minimum
 * 400 KB still launches on a small Mac, where big blocks fail per-entry
 * ("block too large for memory budget") rather than refusing to run. The
 * actual budget is derived at runtime from FreeMem(), so ONE binary adapts
 * from a 1 MB Plus to a G3.
 *
 * VERIFIED 2026-08-02, both halves of that claim: rebuilt with a 600 KB
 * preferred partition, System 7.0.1's Process Manager honoured it and the
 * engine declined a 656 KB entry cleanly (peak 35.5 KB — the block refused at
 * request time), while System 6.0.8 ignored the partition and extracted the
 * same entry with 656.8 KB. FORMATS.md has the three-system table,
 * tools/vmac/README.md the method. */
resource 'SIZE' (-1) {
    reserved, acceptSuspendResumeEvents, reserved,
    canBackground, doesActivateOnFGSwitch, backgroundAndForeground,
    dontGetFrontClicks, ignoreChildDiedEvents, not32BitCompatible,
    notHighLevelEventAware, onlyLocalHLEvents, notStationeryAware,
    dontUseTextEditServices, reserved, reserved, reserved,
    4096 * 1024, 400 * 1024
};
