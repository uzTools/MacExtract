/* UNC_POC_COLORBAR's resources: the progress window laid out as the
 * System 7 Finder's "Copy" window, measured on its frames (System 7.5.5,
 * Mac II): inside 286 x 82; the bar 188 x 11 at (13, 58); the button
 * 59 x 20 at (214, 54), on the bar's line; two lines of text above.
 * The first says the archive's name alone, as the title already says
 * MacExtract. A window of its own (146) rather than a change to 128, so
 * the switch leaves the shipped one alone. */
#include "Dialogs.r"
#include "macextract_strings.h"

resource 'DLOG' (146, purgeable, preload) {
    { 80, 80, 156, 360 },
    movableDBoxProc, visible, noGoAway, 0, 146, S_PROGRESS_TITLE, noAutoCenter
};

resource 'DITL' (146, purgeable, preload) {
    {
        { 51, 211, 71, 270 }, Button     { enabled,  S_BTN_CANCEL };
        {  7,  10, 23, 270 }, StaticText { disabled, "" };
        { 55,  10, 66, 198 }, UserItem   { enabled };
        { 29,  10, 45, 270 }, StaticText { disabled, "" };
    }
};

/* A colour window, so the bar can be painted in the Finder's colours.
 * Source for the bytes: System 7.0.1's System file, whose 'dctb' -6043,
 * -6042 and -6046 are these 8 bytes exactly: seed 0, flags 0, count -1,
 * no entries, default colours. Ignored where there is no Color QuickDraw. */
data 'dctb' (146, purgeable, preload) {
    $"0000 0000 0000 FFFF"
};

/* Mac OS 8 and later: the theme's background, as 'dlgx' 128 gives the
 * progress window it replaces (macextract.r has the source). */
data 'dlgx' (146, purgeable, preload) {
    $"0000 0000 0001"
};
