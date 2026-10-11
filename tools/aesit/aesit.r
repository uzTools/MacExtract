/* aesit's 'SIZE'. Two flags matter and the rest are the usual ones:
 * isHighLevelEventAware, because an application that is not gets no
 * reply to an AESend, and canBackground, because StuffIt Deluxe comes to
 * the front when it is launched and this one has to keep running behind
 * it. 400 KB is generous for what it does and leaves 7.0.3 its declared
 * 5,120 KB with room to spare on the 512 MB guest. */
#include "Processes.r"

resource 'SIZE' (-1) {
    reserved, acceptSuspendResumeEvents, reserved,
    canBackground, doesActivateOnFGSwitch, backgroundAndForeground,
    dontGetFrontClicks, ignoreChildDiedEvents, not32BitCompatible,
    isHighLevelEventAware, onlyLocalHLEvents, notStationeryAware,
    dontUseTextEditServices, reserved, reserved, reserved,
    400 * 1024, 300 * 1024
};
