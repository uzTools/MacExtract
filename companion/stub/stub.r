/* Resources of the companion's stub. Its bundle is NOT here:
   companion/make_stub.py writes the BNDL, the FREFs, the signature and the
   icons for the creator each stub claims. */
#include "Multiverse.r"

/* MacExtract was not found beside this helper's folder. */
resource 'ALRT' (128, purgeable) {
    { 90, 100, 200, 412 }, 128, {
        OK, visible, sound1, OK, visible, sound1,
        OK, visible, sound1, OK, visible, sound1
    }, noAutoCenter
};

resource 'DITL' (128, purgeable) {
    {
        { 78, 232, 98, 292 }, Button { enabled, "OK" };
        { 12, 64, 70, 300 }, StaticText { disabled,
          "MacExtract could not be found. Keep this helper in a folder "
          "beside MacExtract." };
    }
};

/* Launching MacExtract failed: ^0 is the error number. */
resource 'ALRT' (129, purgeable) {
    { 90, 100, 200, 412 }, 129, {
        OK, visible, sound1, OK, visible, sound1,
        OK, visible, sound1, OK, visible, sound1
    }, noAutoCenter
};

resource 'DITL' (129, purgeable) {
    {
        { 78, 232, 98, 292 }, Button { enabled, "OK" };
        { 12, 64, 70, 300 }, StaticText { disabled,
          "MacExtract could not be started (error ^0)." };
    }
};

/* Small, and not aware of high-level events: the Finder then hands it the
   document the way it hands one to MacExtract, in the application's Finder
   information, which is what the stub passes on. */
resource 'SIZE' (-1) {
    reserved, ignoreSuspendResumeEvents, reserved,
    cannotBackground, needsActivateOnFGSwitch, backgroundAndForeground,
    dontGetFrontClicks, ignoreChildDiedEvents, not32BitCompatible,
    notHighLevelEventAware, onlyLocalHLEvents, notStationeryAware,
    dontUseTextEditServices, reserved, reserved, reserved,
    64 * 1024, 48 * 1024
};
