/*
 * macextract.r — resources for the macextract Macintosh shell.
 * Compiled with Retro68's Rez. License: LGPL-2.1-or-later.
 */
#include "Dialogs.r"
#include "Processes.r"

/* Progress dialog. Four items, and the order is the item numbering the
 * code uses (kCancelItem..kDetailItem in macextract_mac.c):
 *
 *   1  Cancel button          also reachable as Cmd-.
 *   2  status   "Extracting <name>"
 *   3  userItem the progress bar; drawn by BarUserItem, not by the Dialog
 *      Manager, so it repaints on update events as well as on every tick
 *   4  detail   "45%   about 2 minutes left"
 *
 * 110 points tall rather than 80: the bar and the detail line are new.
 *
 * A titled window, not dBoxProc: the one System 7 has been seen switching
 * away from (dBoxProc, with the menu bar, was not tried). It cannot be
 * dragged — that was 32 B. noGrowDocProc is in every System from 3.0 on,
 * so there is one window everywhere (DECISIONS.md 2026-10-12, *the
 * application nobody could leave*).
 *
 * EVERY dialog, alert and 'dlgx' here is `preload` as well as purgeable
 * (2026-10-14): read once at launch, while the application's disk is
 * certainly in, instead of when each first appears. Otherwise a one-drive
 * Mac whose archive is on another floppy asked for the application's disk
 * back for the progress window and again for "Extraction complete."
 * Purgeable still, so the budget, taken with PurgeSpace, is the same
 * (DECISIONS.md 2026-10-14, *the disk the dialogs were on*). */
resource 'DLOG' (128, purgeable, preload) {
    { 80, 80, 190, 400 },
    noGrowDocProc, visible, noGoAway, 0, 128, "MacExtract", noAutoCenter
};

/* Mac OS 8 and later: the progress window takes the theme's background
 * rather than white, as alerts already do; 'dlgx' 132 does the same for
 * the password dialog. No code reads either; Systems before Appearance
 * 1.0 ignore the type. Standard File's dialogs stay white: a 'dlgx' is
 * read only from its DLOG's own file, and theirs are the System's.
 * Source: flag bit — Mac OS 8 Toolbox Reference, Dialog Manager, *Dialog
 * Feature Flag Constants* (kDialogFlagsUseThemeBackground = 1 << 0).
 * Layout — measured on 100 of Apple's own 'dlgx' resources on the
 * Mac OS 9.2 disk: 6 bytes, version word 0 then a 32-bit flags word. */
data 'dlgx' (128, purgeable, preload) {
    $"0000 0000 0001"
};

resource 'DITL' (128, purgeable, preload) {
    {
        { 78, 220, 98, 300 }, Button     { enabled,  "Cancel" };
        { 10,  16, 26, 300 }, StaticText { disabled, "Extracting" };
        { 34,  16, 50, 300 }, UserItem   { enabled };
        { 56,  16, 72, 300 }, StaticText { disabled, "" };
    }
};

resource 'ALRT' (129, purgeable, preload) {
    { 90, 100, 190, 412 }, 129, {
        OK, visible, silent, OK, visible, silent,
        OK, visible, silent, OK, visible, silent
    }, noAutoCenter
};

resource 'DITL' (129, purgeable, preload) {
    {
        { 68, 232, 88, 292 }, Button { enabled, "OK" };
        { 12, 64, 60, 300 }, StaticText { disabled, "^0" };
    }
};

resource 'ALRT' (130, purgeable, preload) {
    { 90, 100, 190, 412 }, 130, {
        OK, visible, sound1, OK, visible, sound1,
        OK, visible, sound1, OK, visible, sound1
    }, noAutoCenter
};

resource 'DITL' (130, purgeable, preload) {
    {
        { 68, 232, 88, 292 }, Button { enabled, "OK" };
        { 12, 64, 60, 300 }, StaticText { disabled, "^0" };
    }
};

/* The decoders could not be read again for the next archive the Finder
 * handed over (ovl_reload). Its own alert with the text written in, rather
 * than ShowNote and a string: a string literal is A5, and A5 comes off every
 * extraction's budget one for one, for a message almost nobody will see
 * (DECISIONS.md 2026-10-12, *the reload that the list needs*). */
resource 'ALRT' (135, purgeable, preload) {
    { 90, 100, 190, 412 }, 135, {
        OK, visible, sound1, OK, visible, sound1,
        OK, visible, sound1, OK, visible, sound1
    }, noAutoCenter
};

resource 'DITL' (135, purgeable, preload) {
    {
        { 68, 232, 88, 292 }, Button { enabled, "OK" };
        { 12, 64, 60, 300 }, StaticText { disabled,
          "There is not enough memory to open the next archive. "
          "Open it again." };
    }
};

/* "Locate part N" alert, for a segmented archive whose next part was not
 * found beside the one that was opened. Three buttons, in the order the
 * code tests them (kSegFindItem..kSegCancelItem in macextract_mac.c):
 *
 *   1  Find...   opens Standard File so the user can point at it, on any
 *                mounted volume — including a disk inserted just now
 *   2  Skip      give up on this part; what was decoded so far is kept
 *   3  Cancel    stop the extraction
 *
 * The wording says "locate", not "insert the next disk": the parts of a
 * set are not assumed to be on separate floppies, or to be named alike,
 * or to be anywhere in particular. ALRT 136 is the same alert after the
 * disk the previous part came from was ejected (SegEjectPrevious), when
 * putting the next one in IS the likely answer.
 *
 * ^0 is `Part 2 of "Name"`, ^1 is ` About 33K still to read.` or empty.
 * The sentences are here rather than in the code because a purgeable
 * resource costs nothing until it is shown, and a string costs A5. */
resource 'ALRT' (131, purgeable, preload) {
    { 90, 80, 214, 452 }, 131, {
        OK, visible, sound1, OK, visible, sound1,
        OK, visible, sound1, OK, visible, sound1
    }, noAutoCenter
};

resource 'DITL' (131, purgeable, preload) {
    {
        { 92, 282, 112, 352 }, Button { enabled, "Find..." };
        { 92, 196, 112, 266 }, Button { enabled, "Skip" };
        { 92, 110, 112, 180 }, Button { enabled, "Cancel" };
        { 10, 16, 84, 356 }, StaticText { disabled,
            "^0 has not been found.^1 Locate it, skip it, or cancel." };
    }
};

resource 'ALRT' (136, purgeable, preload) {
    { 90, 80, 214, 452 }, 136, {
        OK, visible, sound1, OK, visible, sound1,
        OK, visible, sound1, OK, visible, sound1
    }, noAutoCenter
};

resource 'DITL' (136, purgeable, preload) {
    {
        { 92, 282, 112, 352 }, Button { enabled, "Find..." };
        { 92, 196, 112, 266 }, Button { enabled, "Skip" };
        { 92, 110, 112, 180 }, Button { enabled, "Cancel" };
        { 10, 16, 84, 356 }, StaticText { disabled,
            "^0 is not on that disk, so it was ejected. Insert the disk "
            "it is on.^1 Or locate it, skip it, or cancel." };
    }
};

/* Password dialog, for an encrypted entry. Four items, in the order the
 * code tests them (kPassOKItem..kPassMsgItem in macextract_mac.c):
 *
 *   1  OK       the default button, so Return takes it
 *   2  Cancel   "do without this entry"; the walk goes on
 *   3  editText the field. What is TYPED goes into the code's own
 *               buffer and the field only ever shows bullets — the
 *               filter in PassFilter swaps the character on its way in,
 *               which is how a Mac hid a password before there was a
 *               password field to ask for
 *   4  the message, which names the archive and, on a second ask, says
 *      the last one was refused
 */
resource 'DLOG' (132, purgeable, preload) {
    { 80, 60, 214, 452 }, dBoxProc, visible, noGoAway, 0, 132, "",
    noAutoCenter
};

data 'dlgx' (132, purgeable, preload) {
    $"0000 0000 0001"
};

resource 'DITL' (132, purgeable, preload) {
    {
        { 102, 302, 122, 372 }, Button     { enabled, "OK" };
        { 102, 216, 122, 286 }, Button     { enabled, "Cancel" };
        {  72,  20,  88, 372 }, EditText   { enabled, "" };
        {  10,  20,  64, 372 }, StaticText { disabled, "^0" };
    }
};

/* The end-of-run report. It replaces the "Extraction complete" alert on
 * any run that has something to say per entry: every name that had to
 * change and every entry that failed on its own, one line each, with
 * the one-line outcome under them — where the alert used to be, and
 * where a reader ends up after reading the list.
 *
 * Five items, in the order the code tests them (kRepOKItem..):
 *
 *   1  OK          dismisses; Return and Enter take it
 *   2  Save as Text  writes the same lines to a TEXT file, for a run
 *                  that is worth acting on later. A screen with no
 *                  scrollback is the whole reason this button exists
 *   3  userItem    the list; drawn by RepListDraw, so it repaints on
 *                  update events as well as on every scroll
 *   4  userItem    the default button's ring. A userItem rather than
 *                  three lines after GetNewDialog, because the Save
 *                  button puts Standard File over this box and the ring
 *                  has to come back with the rest of it
 *
 * The outcome is not an item: it is the LAST LINE of the list, after a
 * blank one, and RepListDraw pins it to the bottom row when the list is
 * long enough to scroll. It reads as one document ending in its verdict
 * — which is what it is — and it cannot be scrolled out of sight, which
 * an ordinary last line can: photographed on a Mac Plus with 26 things
 * to say, "Extraction complete." was nine rows below the fold.
 *
 * The scroll bar is NOT an item: it is made with NewControl beside the
 * list, from the list item's own rectangle, and tracked in RepFilter.
 * Retro68's Rez has no Controls.r and so no 'CNTL' type to declare one
 * with, and a hand-assembled resource would be this project inventing a
 * layout it has no reference for. ModalDialog could not have tracked
 * the arrows and page regions anyway.
 *
 * 300 x 460 at (30,26): the bottom edge lands at 330 and the right at
 * 486, so the whole of it sits on a 512x342 Mac Plus screen with the
 * menu bar above it. Nothing here is ever centered on a bigger screen,
 * which is this application's existing habit (noAutoCenter). */
resource 'DLOG' (133, purgeable, preload) {
    { 30, 26, 330, 486 }, dBoxProc, visible, noGoAway, 0, 133, "",
    noAutoCenter
};

resource 'DITL' (133, purgeable, preload) {
    {
        { 264, 376, 284, 446 }, Button     { enabled, "OK" };
        { 264, 236, 284, 356 }, Button     { enabled, "Save as Text\0xC9" };
        {  12,  12, 246, 428 }, UserItem   { disabled };
        { 260, 372, 288, 450 }, UserItem   { disabled };
    }
};

/* The menu bar. File > Quit stops an extraction, and the application
 * then quits; it has no Command key, to save MenuKey's bytes. The Apple menu is not decoration: System 7.0.1 draws its
 * Help and Application menus only beside one, and without the Application
 * menu nothing can be switched to (DECISIONS.md 2026-10-12, *the
 * application nobody could leave*). */
resource 'MENU' (129) {
    129, textMenuProc, allEnabled, enabled, apple,
    { "About MacExtract\0xC9", noIcon, noKey, noMark, plain }
};

resource 'MENU' (128) {
    128, textMenuProc, allEnabled, enabled, "File",
    { "Quit", noIcon, noKey, noMark, plain }
};

/* About MacExtract. The number is written here rather than read from
 * 'vers' 1 at run time, which cost 32 B of code and A5; check_docs.py
 * holds it to UNC_VERSION like the other copies. */
resource 'ALRT' (134, purgeable, preload) {
    { 90, 100, 190, 412 }, 134, {
        OK, visible, silent, OK, visible, silent,
        OK, visible, silent, OK, visible, silent
    }, noAutoCenter
};

resource 'DITL' (134, purgeable, preload) {
    {
        { 68, 232, 88, 292 }, Button { enabled, "OK" };
        { 12, 64, 60, 300 }, StaticText { disabled, "MacExtract 0.40.0" };
    }
};

/* MultiFinder/System 7 friendliness; System 6 Finder ignores it (there the
 * app just gets all free RAM). The actual budget is derived at runtime from
 * FreeMem(), so ONE binary adapts from a 1 MB Plus to a G3.
 *
 * PREFERRED IS 2 MB, AND IT WAS 4 MB UNTIL 2026-08-31. A partition larger
 * than the free memory does not fail — the Process Manager puts up "MacExtract
 * prefers 4,096K of memory. 3,089K is available. Do you want to open it using
 * the available memory?" and launches with what there is when the user says
 * OK. That alert is on the path a real user takes and on no test's: every
 * harness here installs the application as the BOOT SHELL, which gets all of
 * memory and never sees it. It was photographed for the first time on
 * 2026-08-31, by the first Finder launch this project has ever done on System
 * 7, and a 4 MB Macintosh — a generous one for this application — meets it on
 * every launch.
 *
 * 2 MB clears it on any machine that can run System 7 at all, with about a
 * megabyte of margin, and still holds the heaviest fixture in the sample:
 * `derived-Library_ISBN_Barcoder.sit` replays byte-exact on System 7.0.1 at a
 * peak of 1,683,101 B inside the 2 MB partition (2026-08-31).
 *
 * WHAT IT COSTS CANNOT BE DEMONSTRATED ON ANY MACHINE HERE, and the baseline
 * is why: `derived-EasyFind.dmg.sit` needs 2,658,721 B and is refused per
 * entry at 4 MB preferred as well as at 2 MB, because a 4 MB Macintosh has
 * only ~3 MB free and the partition was never 4 MB. The largest emulator
 * build in tools/vmac is 4 MB. So the price is paid by archives needing
 * between ~1.9 MB and ~3.8 MB on a machine with more than 2 MB free — an
 * 8 MB Macintosh, which nothing here can boot. EasyFind is one of them.
 * Whoever has such a machine can raise the partition back: the application
 * already says "Needs NNNK more memory. Give MacExtract more in Get Info",
 * which is the same box this alert was pointing at.
 *
 * Minimum 400 KB still launches on a small Mac, where big blocks fail
 * per-entry ("block too large for memory budget") rather than refusing to
 * run.
 *
 * VERIFIED 2026-08-02, both halves of that claim: rebuilt with a 600 KB
 * preferred partition, System 7.0.1's Process Manager honoured it and the
 * engine declined a 656 KB entry cleanly (peak 35.5 KB — the block refused at
 * request time), while System 6.0.8 ignored the partition and extracted the
 * same entry with 656.8 KB. FORMATS.md has the three-system table,
 * tools/vmac/README.md the method.
 *
 * acceptSuspendResumeEvents STAYS, though nothing handles those events:
 * with ignoreSuspendResumeEvents System 7.0.1 held a switch out of an
 * extraction until the extraction ended (DECISIONS.md 2026-10-12, *the
 * application nobody could leave*). */
resource 'SIZE' (-1) {
    reserved, acceptSuspendResumeEvents, reserved,
    canBackground, doesActivateOnFGSwitch, backgroundAndForeground,
    dontGetFrontClicks, ignoreChildDiedEvents, not32BitCompatible,
    notHighLevelEventAware, onlyLocalHLEvents, notStationeryAware,
    dontUseTextEditServices, reserved, reserved, reserved,
    2048 * 1024, 400 * 1024
};
