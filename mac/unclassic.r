/*
 * unclassic.r — resources for the unclassic Macintosh shell.
 * Compiled with Retro68's Rez. License: LGPL-2.1-or-later.
 */
#include "Dialogs.r"
#include "Processes.r"

resource 'DLOG' (128, purgeable) {
    { 80, 80, 160, 400 },
    dBoxProc, visible, noGoAway, 0, 128, "", noAutoCenter
};

resource 'DITL' (128, purgeable) {
    {
        { 48, 220, 68, 300 }, Button { enabled, "Cancel" };
        { 12, 16, 28, 300 }, StaticText { disabled, "Extracting" };
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
 * same entry with 656.8 KB. See MANUAL_TESTS.md. */
resource 'SIZE' (-1) {
    reserved, acceptSuspendResumeEvents, reserved,
    canBackground, doesActivateOnFGSwitch, backgroundAndForeground,
    dontGetFrontClicks, ignoreChildDiedEvents, not32BitCompatible,
    notHighLevelEventAware, onlyLocalHLEvents, notStationeryAware,
    dontUseTextEditServices, reserved, reserved, reserved,
    4096 * 1024, 400 * 1024
};
