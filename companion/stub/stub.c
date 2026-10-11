/*
 * The companion's stub. The Finder launches it for a double-clicked
 * archive whose creator it claims, with that archive in the application's
 * Finder information (AppParmHandle); it finds MacExtract and launches it,
 * leaving that information alone, so MacExtract opens the archive exactly
 * as it opens one dropped on its icon. MacExtract itself is not changed.
 *
 * Where MacExtract is: the folder ABOVE the stub's own — the stubs live in
 * a folder beside it (DECISIONS.md 2026-10-11, *where the stubs can live*)
 * — found by type APPL and creator MExt, so a renamed MacExtract is still
 * found.
 *
 * HYPOTHESIS, which the stub exists to test: that the Segment Loader keeps
 * the Finder information across a _Launch from one application to the
 * next. Nothing here has read that it does.
 *
 * The launch is the original _Launch form, a pointer to the file name and
 * a configuration word, which Multiverse.h declares as the first two fields
 * of LaunchParamBlockRec (reserved1, reserved2); launchBlockID is left 0,
 * which is not extendedBlock, so the Process Manager reads the short form.
 * The layout is the header's; that reserved1 is the name pointer is from
 * memory of Inside Macintosh II's Segment Loader chapter, and a launch that
 * works is what confirms it.
 */
#include <Quickdraw.h>
#include <Fonts.h>
#include <Windows.h>
#include <Menus.h>
#include <TextEdit.h>
#include <Dialogs.h>
#include <Files.h>
#include <Processes.h>
#include <SegLoad.h>
#include <NumberFormatting.h>

QDGlobals qd;

enum { kNotFoundAlert = 128, kLaunchAlert = 129 };

static void Toolbox(void)
{
    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    InitMenus();
    TEInit();
    InitDialogs(NULL);
    InitCursor();
}

/* The folder MacExtract should be in: the parent of the stub's own. */
static OSErr HomeFolder(short *vol, long *dir)
{
    Str255 name;
    short ref;
    Handle parms;
    FCBPBRec fcb;
    CInfoPBRec c;
    OSErr err;

    GetAppParms(name, &ref, &parms);
    fcb.ioCompletion = NULL;
    fcb.ioNamePtr = name;
    fcb.ioVRefNum = 0;
    fcb.ioRefNum = ref;
    fcb.ioFCBIndx = 0;
    err = PBGetFCBInfoSync(&fcb);
    if (err) return err;

    c.dirInfo.ioCompletion = NULL;
    c.dirInfo.ioNamePtr = NULL;
    c.dirInfo.ioVRefNum = fcb.ioFCBVRefNum;
    c.dirInfo.ioFDirIndex = -1;            /* the folder ioDrDirID names */
    c.dirInfo.ioDrDirID = fcb.ioFCBParID;
    err = PBGetCatInfoSync(&c);
    if (err) return err;
    *vol = fcb.ioFCBVRefNum;
    *dir = c.dirInfo.ioDrParID;
    return noErr;
}

/* An application of creator MExt in that folder, by name. */
static OSErr FindMacExtract(short vol, long dir, Str255 name)
{
    CInfoPBRec c;
    short i;

    for (i = 1; ; i++) {
        c.hFileInfo.ioCompletion = NULL;
        c.hFileInfo.ioNamePtr = name;
        c.hFileInfo.ioVRefNum = vol;
        c.hFileInfo.ioFDirIndex = i;
        c.hFileInfo.ioDirID = dir;
        if (PBGetCatInfoSync(&c)) return fnfErr;
        if (c.hFileInfo.ioFlAttrib & 0x10) continue;          /* a folder */
        if (c.hFileInfo.ioFlFndrInfo.fdType == 'APPL'
            && c.hFileInfo.ioFlFndrInfo.fdCreator == 'MExt')
            return noErr;
    }
}

int main(void)
{
    short vol;
    long dir;
    Str255 name;
    WDPBRec wd;
    LaunchParamBlockRec lp;
    OSErr err;

    if (HomeFolder(&vol, &dir) || FindMacExtract(vol, dir, name)) {
        Toolbox();
        StopAlert(kNotFoundAlert, NULL);
        return 0;
    }

    /* _Launch names the application relative to the default directory, so
     * make MacExtract's folder the default one. */
    wd.ioCompletion = NULL;
    wd.ioNamePtr = NULL;
    wd.ioVRefNum = vol;
    wd.ioWDProcID = 'MXst';
    wd.ioWDDirID = dir;
    err = PBOpenWDSync(&wd);
    if (!err) err = SetVol(NULL, wd.ioVRefNum);
    if (!err) {
        lp.reserved1 = (long)name;
        lp.reserved2 = 0;
        lp.launchBlockID = 0;
        err = LaunchApplication(&lp);   /* returns only if it failed */
    }

    Toolbox();
    {
        Str255 num;
        NumToString(err, num);
        ParamText(num, NULL, NULL, NULL);
    }
    StopAlert(kLaunchAlert, NULL);
    return 0;
}
