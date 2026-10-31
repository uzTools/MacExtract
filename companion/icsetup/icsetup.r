/* icsetup's alerts and 'SIZE'. */
#include "Types.r"
#include "Processes.r"

resource 'ALRT' (128) { {60, 40, 210, 460}, 128, {OK, visible, sound1, OK, visible, sound1, OK, visible, sound1, OK, visible, sound1}, alertPositionMainScreen };
resource 'DITL' (128) { {
    {118, 300, 138, 410}, Button { enabled, "Use MacExtract" };
    {118, 200, 138, 280}, Button { enabled, "Cancel" };
    {10, 70, 108, 410}, StaticText { disabled,
        "Internet Config can hand downloaded archives to MacExtract. "
        "^0 file types will open in MacExtract after a download "
        "(^1 already do). The file map is saved first, so this can be undone." };
} };

resource 'ALRT' (129) { {60, 40, 190, 460}, 129, {OK, visible, sound1, OK, visible, sound1, OK, visible, sound1, OK, visible, sound1}, alertPositionMainScreen };
resource 'DITL' (129) { {
    {98, 300, 118, 410}, Button { enabled, "Keep" };
    {98, 200, 118, 280}, Button { enabled, "Cancel" };
    {98, 70, 118, 180}, Button { enabled, "Restore" };
    {10, 70, 88, 410}, StaticText { disabled,
        "All ^0 archive file types already open in MacExtract after a "
        "download. Restore puts back the file map as it was." };
} };

resource 'ALRT' (130) { {60, 40, 150, 460}, 130, {OK, visible, sound1, OK, visible, sound1, OK, visible, sound1, OK, visible, sound1}, alertPositionMainScreen };
resource 'DITL' (130) { {
    {58, 330, 78, 410}, Button { enabled, "OK" };
    {10, 70, 50, 410}, StaticText { disabled, "^0^1" };
} };

resource 'ALRT' (131) { {60, 40, 150, 460}, 131, {OK, visible, sound1, OK, visible, sound1, OK, visible, sound1, OK, visible, sound1}, alertPositionMainScreen };
resource 'DITL' (131) { {
    {58, 330, 78, 410}, Button { enabled, "OK" };
    {10, 70, 50, 410}, StaticText { disabled, "Nothing was changed: ^0 failed (^1)." };
} };

resource 'ALRT' (132) { {60, 40, 150, 460}, 132, {OK, visible, sound1, OK, visible, sound1, OK, visible, sound1, OK, visible, sound1}, alertPositionMainScreen };
resource 'DITL' (132) { {
    {58, 330, 78, 410}, Button { enabled, "OK" };
    {10, 70, 50, 410}, StaticText { disabled, "Internet Config is not installed on this Macintosh, so there is nothing to set up." };
} };

resource 'ALRT' (133) { {60, 40, 150, 460}, 133, {OK, visible, sound1, OK, visible, sound1, OK, visible, sound1, OK, visible, sound1}, alertPositionMainScreen };
resource 'DITL' (133) { {
    {58, 330, 78, 410}, Button { enabled, "OK" };
    {10, 70, 50, 410}, StaticText { disabled, "Internet Config's file map has no archive types in it, so there is nothing to set up." };
} };

resource 'SIZE' (-1) {
    reserved, acceptSuspendResumeEvents, reserved,
    canBackground, doesActivateOnFGSwitch, backgroundAndForeground,
    dontGetFrontClicks, ignoreChildDiedEvents, is32BitCompatible,
    notHighLevelEventAware, onlyLocalHLEvents, notStationeryAware,
    dontUseTextEditServices, reserved, reserved, reserved,
    192 * 1024, 128 * 1024
};
