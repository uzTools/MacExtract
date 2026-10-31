/* aeodoc.c — hand MacExtract an archive the way a browser hands a
 * download to its Internet Config post-processor: an Open Documents
 * Apple event addressed to creator 'MExt'.
 *
 * WHY THIS EXISTS. A helper that writes MacExtract into Internet Config's
 * map as the post-processor is only worth building if the hand-off
 * arrives. MacExtract's 'SIZE' says notHighLevelEventAware, so whether it
 * receives the event at all is the question (DECISIONS.md 2026-10-31,
 * *the helper list Expander asks for*).
 *
 * WHAT IT DOES, two cases in one run, each logged to `AEResult` beside it:
 *   A. MacExtract not running: the odoc for `Subject A.sit` is coerced to
 *      typeAppParameters and passed to LaunchApplication — Inside
 *      Macintosh: Interapplication Communication's way of launching an
 *      application with an event (and the Process Manager's, for one
 *      that is not high-level-event aware, of turning it into Finder
 *      information; Inside Macintosh: Processes).
 *   B. Then, MacExtract still running: an odoc for `Subject B.sit` by
 *      AESend to its process. Its error is the result.
 * Whether each archive was EXTRACTED is read off the volume, not here.
 *
 * A HARNESS tool, System 7 only, never built by ci.sh; aetran.c's shape.
 */
#include <AppleEvents.h>
#include <Errors.h>
#include <Events.h>
#include <Files.h>
#include <Fonts.h>
#include <Gestalt.h>
#include <Memory.h>
#include <Processes.h>
#include <Quickdraw.h>
#include <TextUtils.h>
#include <Windows.h>

/* Source: Inside Macintosh — Processes (launchNoFileFlags) and
 * Interapplication Communication (gestaltAppleEventsPresent, bit 0). */
#define launchNoFileFlags 0x0800
#define gestaltAppleEventsPresent 0
#define kMExt 'MExt'
/* Retro68's headers lack it. Source: Inside Macintosh —
 * Interapplication Communication, the descriptor-type table
 * (typeAppParameters 'appa', "Process Manager launch parameters"), and
 * Apple's LaunchWithDoc sample, which coerces an odoc to it for
 * LaunchApplication exactly as case A does. */
#ifndef typeAppParameters
#define typeAppParameters 'appa'
#endif

static const unsigned char kAppName[] = "\012MacExtract";
static const unsigned char kSubjA[]   = "\015Subject A.sit";
static const unsigned char kSubjB[]   = "\015Subject B.sit";
static const unsigned char kLogName[] = "\010AEResult";

static WindowPtr gWin;
static short gLine;
static char gLog[1024];
static short gLogLen;

static void logs(const char *s)
{
    unsigned char p[256];
    short n = 0;
    while (s[n] && n < 200) {
        p[n + 1] = (unsigned char)s[n];
        if (gLogLen < (short)sizeof(gLog) - 2) gLog[gLogLen++] = s[n];
        n++;
    }
    p[0] = (unsigned char)n;
    if (gLogLen < (short)sizeof(gLog) - 2) gLog[gLogLen++] = '\r';
    if (gWin) { SetPort(gWin); gLine += 12; MoveTo(6, gLine); DrawString(p); }
}

static void lognum(const char *label, long v)
{
    char buf[64];
    short i = 0, j;
    Str255 num;
    while (label[i] && i < 40) { buf[i] = label[i]; i++; }
    NumToString(v, num);
    for (j = 1; j <= num[0]; j++) buf[i++] = (char)num[j];
    buf[i] = 0;
    logs(buf);
}

static void writelog(FSSpec *dir)
{
    FSSpec spec = *dir;
    short ref;
    long count = gLogLen;
    BlockMoveData(kLogName, spec.name, kLogName[0] + 1);
    FSpDelete(&spec);
    if (FSpCreate(&spec, 'ttxt', 'TEXT', smSystemScript) != noErr) return;
    if (FSpOpenDF(&spec, fsWrPerm, &ref) != noErr) return;
    FSWrite(ref, &count, gLog);
    SetEOF(ref, gLogLen);
    FSClose(ref);
}

static void spin(long ticks)
{
    EventRecord ev;
    long stop = TickCount() + ticks;
    while (TickCount() < stop) WaitNextEvent(everyEvent, &ev, 6, NULL);
}

static Boolean findProcess(OSType creator, ProcessSerialNumber *psn)
{
    ProcessSerialNumber p;
    ProcessInfoRec info;
    Str255 name;
    FSSpec spec;
    p.highLongOfPSN = 0;
    p.lowLongOfPSN = kNoProcess;
    while (GetNextProcess(&p) == noErr) {
        info.processInfoLength = sizeof(info);
        info.processName = name;
        info.processAppSpec = &spec;
        if (GetProcessInformation(&p, &info) != noErr) continue;
        if (info.processSignature == creator) { *psn = p; return true; }
    }
    return false;
}

/* An odoc whose direct object is a one-item list of an alias: the shape
 * the Finder sends. `target` is the address. */
static OSErr makeOdoc(AEAddressDesc *target, FSSpec *file, AppleEvent *evt)
{
    AliasHandle alias = NULL;
    AEDesc one, list;
    OSErr err = AECreateAppleEvent(kCoreEventClass, kAEOpenDocuments, target,
                                   kAutoGenerateReturnID, kAnyTransactionID,
                                   evt);
    if (err != noErr) return err;
    err = NewAlias(NULL, file, &alias);
    if (err != noErr) return err;
    HLock((Handle)alias);
    err = AECreateDesc(typeAlias, *alias, GetHandleSize((Handle)alias), &one);
    HUnlock((Handle)alias);
    DisposeHandle((Handle)alias);
    if (err != noErr) return err;
    err = AECreateList(NULL, 0, false, &list);
    if (err == noErr) err = AEPutDesc(&list, 1, &one);
    AEDisposeDesc(&one);
    if (err == noErr) err = AEPutParamDesc(evt, keyDirectObject, &list);
    AEDisposeDesc(&list);
    return err;
}

int main(void)
{
    ProcessSerialNumber me, mx;
    ProcessInfoRec info;
    Str255 myName;
    FSSpec myself, folder, app, a, b;
    AEAddressDesc target;
    AppleEvent evt, reply;
    AEDesc launchDesc;
    LaunchParamBlockRec pb;
    Rect r;
    long attr;
    OSErr err;
    short i;

    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    InitCursor();
    SetRect(&r, 40, 360, 480, 470);
    gWin = NewWindow(NULL, &r, "\paeodoc", true, documentProc,
                     (WindowPtr)-1L, false, 0);
    SetPort(gWin);
    TextFont(kFontIDMonaco);
    TextSize(9);
    gLine = 4;
    logs("aeodoc: odoc to MExt, as a post-processor gets it");

    if (Gestalt(gestaltAppleEventsAttr, &attr) != noErr ||
        !(attr & (1L << gestaltAppleEventsPresent))) {
        logs("no Apple Event Manager"); spin(600); ExitToShell();
    }
    GetCurrentProcess(&me);
    info.processInfoLength = sizeof(info);
    info.processName = myName;
    info.processAppSpec = &myself;
    if (GetProcessInformation(&me, &info) != noErr) ExitToShell();
    folder = myself;
    err = FSMakeFSSpec(folder.vRefNum, folder.parID, kAppName, &app);
    if (err == noErr)
        err = FSMakeFSSpec(folder.vRefNum, folder.parID, kSubjA, &a);
    if (err == noErr)
        err = FSMakeFSSpec(folder.vRefNum, folder.parID, kSubjB, &b);
    if (err != noErr) {
        lognum("missing file ", err); writelog(&folder); spin(600);
        ExitToShell();
    }

    /* A: launch with the event as its parameters. */
    if (findProcess(kMExt, &mx)) {
        logs("A: MacExtract already running; case A not run");
    } else {
        OSType sig = kMExt;
        err = AECreateDesc(typeApplSignature, &sig, sizeof(sig), &target);
        if (err == noErr) err = makeOdoc(&target, &a, &evt);
        AEDisposeDesc(&target);
        if (err == noErr)
            err = AECoerceDesc(&evt, typeAppParameters, &launchDesc);
        if (err != noErr) {
            lognum("A: building the event ", err);
        } else {
            HLock(launchDesc.dataHandle);
            pb.reserved1 = 0;
            pb.reserved2 = 0;
            pb.launchBlockID = extendedBlock;
            pb.launchEPBLength = extendedBlockLen;
            pb.launchFileFlags = 0;
            pb.launchControlFlags = launchContinue | launchNoFileFlags;
            pb.launchAppSpec = &app;
            pb.launchAppParameters = (AppParametersPtr)*launchDesc.dataHandle;
            err = LaunchApplication(&pb);
            HUnlock(launchDesc.dataHandle);
            AEDisposeDesc(&launchDesc);
            AEDisposeDesc(&evt);
            lognum("A: LaunchApplication ", err);
        }
    }

    /* Give A time to start and extract a small archive. */
    spin(60 * 60);

    /* B: an odoc to the running process. */
    if (!findProcess(kMExt, &mx)) {
        logs("B: MacExtract not running after A; case B not run");
    } else {
        err = AECreateDesc(typeProcessSerialNumber, &mx, sizeof(mx), &target);
        if (err == noErr) err = makeOdoc(&target, &b, &evt);
        AEDisposeDesc(&target);
        if (err != noErr) {
            lognum("B: building the event ", err);
        } else {
            err = AESend(&evt, &reply, kAENoReply, kAENormalPriority,
                         kAEDefaultTimeout, NULL, NULL);
            lognum("B: AESend ", err);
            AEDisposeDesc(&evt);
        }
    }
    for (i = 0; i < 6; i++) spin(600);   /* let B, if it went, finish */
    logs(findProcess(kMExt, &mx) ? "end: MacExtract running"
                                 : "end: MacExtract not running");
    logs("done");
    writelog(&folder);
    spin(120);
    ExitToShell();
    return 0;
}
