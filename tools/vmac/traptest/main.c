/*
 * traptest — the minimal reproduction for "a 64K ROM cannot run this".
 *
 * MacExtract itself bombs on a true Macintosh 512K with ID = 03 the moment it
 * is launched, which does not say WHICH call did it. This does: it paints a
 * mark, makes one call, paints the next mark. A missing mark names the call
 * that follows the last one painted.
 *
 * The calls are in the ORDER THE APPLICATION MAKES THEM, so where the probe
 * stops is where the application stops. A 64K ROM stops at the first one,
 * SetApplLimit, which hides everything behind it — build with
 * -DTRAPTEST_NO_MEM to drop the two memory calls and reach the rest.
 *
 * Put it on the volume as `Finder` (mkmfs.py app.bin:Finder) so that no real
 * Finder is in the frame, and never return: when the shell quits, the System
 * repaints the desktop and erases the marks, which at emulator speed happens
 * long before a screenshot can be taken.
 *
 * Built by hand, not by ci.sh — see tools/vmac/README.md.
 */
#include <Quickdraw.h>
#include <Fonts.h>
#include <Windows.h>
#include <Traps.h>
#include <OSUtils.h>
#include <Files.h>
#include <Events.h>
#include <LowMem.h>
#include <Memory.h>
#include <string.h>

QDGlobals qd;

/* Marks run left to right, eight to a row, in the top 75 points of the
 * screen. Small and high on purpose: the system error dialog covers the
 * middle of a 512x342 screen, and marks under it cannot be read from the
 * screenshot that shows the bomb — which is the screenshot that matters. */
static void mark(short n)
{
    Rect r;
    short col = (short)(n % 8), row = (short)(n / 8);
    SetRect(&r, (short)(10 + col * 62), (short)(25 + row * 28),
            (short)(58 + col * 62), (short)(45 + row * 28));
    PaintRect(&r);
}

int main(void)
{
    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();

    mark(0);                    /* alive, and QuickDraw works */

#ifndef TRAPTEST_NO_MEM
    /* The application's FIRST Toolbox call, and the one a 64K ROM dies on.
     * Mark 6 says the trap reports as present, which it does on both ROMs —
     * an availability check compares against _Unimplemented, and on a 64K ROM
     * this entry is neither _Unimplemented nor a routine: it is an address in
     * RAM (FORMATS.md, *A true Macintosh 512K*). */
    if ((long)NGetTrapAddress(_SetApplLimit, kOSTrapType) !=
        (long)NGetTrapAddress(_Unimplemented, kToolboxTrapType))
        mark(6);

    SetApplLimit((Ptr)((long)LMGetApplLimit() - 4096L));
    mark(7);                    /* survived SetApplLimit */
    MaxApplZone();
    mark(8);                    /* survived MaxApplZone */
#endif

    /* _GetToolBoxTrapAddress (A346). The 128K ROM introduced it; a 64K ROM
     * has only _GetTrapAddress (A046). TrapAvailable() in
     * mac/macextract_mac.c calls this twice and compares — and the comparison
     * is the point, not the survival: a WRONG answer here has the application
     * call a trap that is not there. Mark 1 is what TrapAvailable would call
     * available, mark 2 what it would call missing; only one can appear. */
    {
        long wne = (long)NGetTrapAddress(_WaitNextEvent, kToolboxTrapType);
        long unimp = (long)NGetTrapAddress(_Unimplemented, kToolboxTrapType);

        if (wne != unimp) {
            EventRecord ev;

            mark(1);            /* TrapAvailable(_WaitNextEvent) == TRUE */
            (void)WaitNextEvent(everyEvent, &ev, 0L, NULL);
            mark(3);            /* ...and calling it came back */
        } else {
            mark(2);            /* TrapAvailable(_WaitNextEvent) == FALSE */
        }
    }

    /* The other half of the attribution: every file operation in
     * mac/macextract_mac.c goes through an HFS parameter block, and HFS
     * arrived with the 128K ROM. PBHGetVInfoSync is the cheapest one that
     * changes nothing. */
    {
        HParamBlockRec pb;
        memset(&pb, 0, sizeof pb);
        pb.volumeParam.ioVolIndex = 1;
        (void)PBHGetVInfoSync(&pb);
    }

    mark(4);                    /* survived an HFS parameter block */

    {
        CInfoPBRec cpb;
        memset(&cpb, 0, sizeof cpb);
        cpb.hFileInfo.ioVRefNum = 0;
        cpb.hFileInfo.ioFDirIndex = 1;
        (void)PBGetCatInfoSync(&cpb);
    }

    mark(5);                    /* survived PBGetCatInfo */

    for (;;)
        ;                       /* hold the screen; see the header */
}
