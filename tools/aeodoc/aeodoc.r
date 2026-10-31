/* aeodoc's 'SIZE': isHighLevelEventAware (an application that is not
 * cannot send and be answered) and canBackground, because MacExtract
 * comes to the front when it is launched and this one keeps running. */
#include "Processes.r"

resource 'SIZE' (-1) {
    reserved, acceptSuspendResumeEvents, reserved,
    canBackground, doesActivateOnFGSwitch, backgroundAndForeground,
    dontGetFrontClicks, ignoreChildDiedEvents, not32BitCompatible,
    isHighLevelEventAware, onlyLocalHLEvents, notStationeryAware,
    dontUseTextEditServices, reserved, reserved, reserved,
    200 * 1024, 150 * 1024
};
