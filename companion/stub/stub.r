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

/* Launching MacExtract, or the creator's own application, failed: ^0 is
   the error number. */
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
          "The application could not be started (error ^0)." };
    }
};

/* A document MacExtract's bundle does not claim, and no other application
   of this helper's creator is known to the Desktop Manager. */
resource 'ALRT' (130, purgeable) {
    { 90, 100, 200, 412 }, 130, {
        OK, visible, sound1, OK, visible, sound1,
        OK, visible, sound1, OK, visible, sound1
    }, noAutoCenter
};

resource 'DITL' (130, purgeable) {
    {
        { 78, 232, 98, 292 }, Button { enabled, "OK" };
        { 12, 64, 70, 300 }, StaticText { disabled,
          "MacExtract cannot open this document, and the application "
          "that made it could not be found." };
    }
};

/* Opened with no document: this helper is again the application the
   Finder gives its creator's archives to. */
resource 'ALRT' (131, purgeable) {
    { 90, 100, 200, 412 }, 131, {
        OK, visible, sound1, OK, visible, sound1,
        OK, visible, sound1, OK, visible, sound1
    }, noAutoCenter
};

resource 'DITL' (131, purgeable) {
    {
        { 78, 232, 98, 292 }, Button { enabled, "OK" };
        { 12, 64, 70, 300 }, StaticText { disabled,
          "Archives this helper claims open in MacExtract again." };
    }
};

/* The reclaim failed: ^0 is the error (System 6 has no desktop database
   to write to). */
resource 'ALRT' (132, purgeable) {
    { 90, 100, 200, 412 }, 132, {
        OK, visible, sound1, OK, visible, sound1,
        OK, visible, sound1, OK, visible, sound1
    }, noAutoCenter
};

resource 'DITL' (132, purgeable) {
    {
        { 78, 232, 98, 292 }, Button { enabled, "OK" };
        { 12, 64, 70, 300 }, StaticText { disabled,
          "This helper could not register itself (error ^0)." };
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
