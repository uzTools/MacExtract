/*
 * traptest — the minimal reproduction for "a 64K ROM cannot run this".
 *
 * MacExtract itself bombs on a true Macintosh 512K with ID = 03 the moment it
 * is launched, which does not say WHICH call did it. This does: it paints a
 * mark, makes one call, paints the next mark. A missing mark names the call
 * that follows the last one painted.
 *
 * Launch it as the boot shell (mkmfs.py --shell TrapTest) so that no Finder
 * is in the frame, and never return: when the shell quits, the System
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
#include <string.h>

QDGlobals qd;

static void mark(short n)
{
    Rect r;
    SetRect(&r, (short)(20 + n * 120), 40, (short)(120 + n * 120), 100);
    PaintRect(&r);
}

int main(void)
{
    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();

    mark(0);                    /* alive, and QuickDraw works */

    /* _GetToolBoxTrapAddress (A346). The 128K ROM introduced it; a 64K ROM
     * has only _GetTrapAddress (A046). TrapAvailable() in
     * mac/macextract_mac.c calls this twice before anything else happens. */
    (void)NGetTrapAddress(_WaitNextEvent, kToolboxTrapType);
    (void)NGetTrapAddress(_Unimplemented, kToolboxTrapType);

    mark(1);                    /* survived both */

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

    mark(2);                    /* survived an HFS parameter block */

    {
        CInfoPBRec cpb;
        memset(&cpb, 0, sizeof cpb);
        cpb.hFileInfo.ioVRefNum = 0;
        cpb.hFileInfo.ioFDirIndex = 1;
        (void)PBGetCatInfoSync(&cpb);
    }

    mark(3);                    /* survived PBGetCatInfo */

    for (;;)
        ;                       /* hold the screen; see the header */
}
