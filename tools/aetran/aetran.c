/* aetran.c — ask StuffIt Deluxe 3.5.1 to run one of its translators, by
 * Apple event, on a Macintosh that has no scripting language on it.
 *
 * WHY THIS EXISTS. The btoa decoder in src/fmt_btoa.c is graded against
 * streams that all come out of one encoder, btoa 5.2.1 on Linux
 * (TESTING.md, *btoa*). The independent encoder within reach is Aladdin's
 * own `btoa/atob Translator`, and the only route to it anybody here had
 * tried is StuffIt Deluxe's Translate menu — whose items are a submenu,
 * and submenu items cannot be selected under Mini vMac at all
 * (tools/vmac/README.md, *sitcrypt.py*).
 *
 * They do not have to be. StuffIt Deluxe 3.5.1's 'aete' declares a
 * `translate` event — 'SIT!'/'TRAN', direct object an alias, 'trnm' the
 * translator's name, 'encd' encode-or-decode, 'dest' where to put the
 * result — and its 'SIZE' -1 is 0xd8e8, isHighLevelEventAware and
 * localAndRemoteHLEvents both set. Aladdin's own `Translate Sample`
 * script sends exactly that event. So the translator is reachable
 * without touching the menu bar, and the Apple Event Manager is in
 * System 7.0.1 whether or not AppleScript is installed — which on this
 * image it is not.
 *
 * WHAT IT DOES. Launches the application if it is not already running,
 * sends it the event, waits for the reply, and writes what came back to
 * a text file beside itself. The file is the result; the window is only
 * so a screenshot of a run that hangs says where it stopped.
 *
 * This is a HARNESS tool, not part of the shipping application: it is
 * System 7 only (Apple events, the Alias Manager, FSSpecs) and it is
 * never built by ci.sh. The 68000 discipline the engine follows does not
 * apply to it beyond compiling for -mcpu=68000, which it does.
 *
 * Everything it needs is in the folder it is launched from: the subject
 * file, and the application. No file names are typed at it and no
 * coordinate is clicked, so there is nothing here for the Finder to
 * catch if a step fails — which is how the last attempt at this went
 * wrong, renaming the subject to `Subject.ascii` and producing a
 * specimen that was the plain subject (tools/vmac/README.md).
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

/* The names are compiled in rather than typed in: this runs with no
 * dialog and no keyboard. MacRoman 0xAA is the trademark sign, which is
 * part of the application's real file name. */
static const unsigned char kAppName[]  = "\017StuffIt Deluxe\xAA";
static const unsigned char kSubject[]  = "\007Subject";
/* What the translator calls its output, measured: it MacBinary-wraps the
 * file first and btoa's that, so `Subject` becomes `Subject.MBin.ascii`
 * (its STR# 130 holds both suffixes). Deleted before the run, so a stale
 * one cannot be read back as this run's specimen. */
static const unsigned char kOutName[]  = "\022Subject.MBin.ascii";
static const unsigned char kLogName[]  = "\011AEResult";
static const char kTranslator[] = "btoa/atob";   /* the translator's own
                                                  * 'Name' resource, read
                                                  * off the disk image */

/* Three constants Retro68's headers do not carry. Source: Inside
 * Macintosh — Processes (launchNoFileFlags, the bit that says the
 * launchFileFlags field is not to be used) and Interapplication
 * Communication (gestaltAppleEventsPresent, bit 0 of 'evnt'). */
#define launchNoFileFlags 0x0800
#define gestaltAppleEventsPresent 0

#define kSITCreator  'SIT!'
#define kTranslateID 'TRAN'
#define keyUsing     'trnm'
#define keyEncoding  'encd'
#define keyDest      'dest'
#define keyErrNumber 'errn'

static WindowPtr gWin;
static short gLine;
static char gLog[1024];
static short gLogLen;

/* ---------------------------------------------------------------- */
/* Saying what happened, on the screen and in a file                 */
/* ---------------------------------------------------------------- */

static void logs(const char *s)
{
    unsigned char p[256];
    short n = 0;
    while (s[n] && n < 200) {
        p[n + 1] = (unsigned char)s[n];
        if (gLogLen < (short)sizeof(gLog) - 2)
            gLog[gLogLen++] = s[n];
        n++;
    }
    p[0] = (unsigned char)n;
    if (gLogLen < (short)sizeof(gLog) - 2)
        gLog[gLogLen++] = '\r';
    if (gWin) {
        SetPort(gWin);
        gLine += 12;
        MoveTo(6, gLine);
        DrawString(p);
    }
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

/* The log file is the result of the run. The screen is not: a window can
 * be photographed showing a step that later failed, and the harness reads
 * the volume, not the picture. */
static void writelog(FSSpec *dir)
{
    FSSpec spec;
    short ref;
    long count = gLogLen;
    spec = *dir;
    BlockMoveData(kLogName, spec.name, kLogName[0] + 1);
    FSpDelete(&spec);
    if (FSpCreate(&spec, 'ttxt', 'TEXT', smSystemScript) != noErr) return;
    if (FSpOpenDF(&spec, fsWrPerm, &ref) != noErr) return;
    FSWrite(ref, &count, gLog);
    SetEOF(ref, gLogLen);
    FSClose(ref);
}

/* ---------------------------------------------------------------- */
/* Waiting                                                           */
/* ---------------------------------------------------------------- */

static pascal Boolean AEIdle(EventRecord *ev, long *sleep, RgnHandle *rgn)
{
    (void)ev;
    *sleep = 6;
    *rgn = NULL;
    return false;                       /* keep waiting for the reply */
}

static void spin(long ticks)
{
    EventRecord ev;
    long stop = TickCount() + ticks;
    while (TickCount() < stop)
        WaitNextEvent(everyEvent, &ev, 6, NULL);
}

/* ---------------------------------------------------------------- */
/* Finding, and if need be starting, StuffIt Deluxe                  */
/* ---------------------------------------------------------------- */

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
        if (info.processSignature == creator) {
            *psn = p;
            return true;
        }
    }
    return false;
}

/* The application is launched from here rather than by the harness,
 * because the harness would have to bring the Finder back to the front
 * afterwards to start this one — and clicking a partly covered desktop
 * is exactly the kind of coordinate that fails into the wrong window. */
static OSErr launchApp(FSSpec *app, ProcessSerialNumber *psn)
{
    LaunchParamBlockRec pb;
    OSErr err;
    short tries;
    pb.reserved1 = 0;
    pb.reserved2 = 0;
    pb.launchBlockID = extendedBlock;
    pb.launchEPBLength = extendedBlockLen;
    pb.launchFileFlags = 0;
    pb.launchControlFlags = launchContinue | launchNoFileFlags;
    pb.launchAppSpec = app;
    pb.launchAppParameters = NULL;
    err = LaunchApplication(&pb);
    if (err != noErr) return err;
    *psn = pb.launchProcessSN;
    /* It is launched, not ready: the reply would come back with
     * errAEEventNotHandled if the event arrived before its handlers were
     * installed. Give it time, and check it is still there. */
    for (tries = 0; tries < 40; tries++) {
        spin(30);
        if (findProcess(kSITCreator, psn)) return noErr;
    }
    return procNotFound;
}

/* ---------------------------------------------------------------- */
/* The event                                                         */
/* ---------------------------------------------------------------- */

/* An alias descriptor for one file — or, with wantList, a one-item list
 * holding it, which is the shape AppleScript actually sends for a
 * parameter an 'aete' declares as a single alias (Aladdin's own Scripting
 * Addenda writes `unstuff into {alias "HD:Downloads:"}` for an 'into' the
 * dictionary calls `fss `). */
static OSErr fileDesc(FSSpec *spec, Boolean wantList, AEDesc *out)
{
    AliasHandle alias = NULL;
    AEDesc one;
    OSErr err = NewAlias(NULL, spec, &alias);
    if (err != noErr) return err;
    HLock((Handle)alias);
    err = AECreateDesc(typeAlias, *alias, GetHandleSize((Handle)alias), &one);
    HUnlock((Handle)alias);
    DisposeHandle((Handle)alias);
    if (err != noErr || !wantList) {
        *out = one;
        return err;
    }
    err = AECreateList(NULL, 0, false, out);
    if (err == noErr) err = AEPutDesc(out, 1, &one);
    AEDisposeDesc(&one);
    return err;
}

/* One shape of the translate event. The parameters an application will
 * accept are not in its 'aete' — that says what the terms MEAN, not what
 * its handler coerces — so each shape is sent and the reply's 'errn' is
 * what says whether it was right. -1700 (errAECoercionFail) is a
 * parameter of the wrong type; -1701 (errAEDescNotFound) a missing one.
 */
typedef struct {
    const char *what;
    Boolean list;               /* direct object wrapped in a list */
    Boolean encoding;           /* send 'encd' at all */
    short dest;                 /* 0 none, 1 the output file as 'fss ',
                                 * 2 the folder as an alias */
} Shape;

static OSErr sendTranslate(ProcessSerialNumber *psn, FSSpec *subject,
                           FSSpec *dest, FSSpec *folder, const Shape *shape)
{
    AEAddressDesc target;
    AppleEvent evt, reply;
    AEDesc obj, destDesc;
    OSErr err, remote = noErr;
    DescType got;
    Size size;
    long code = 0;
    Boolean yes = true;

    err = AECreateDesc(typeProcessSerialNumber, psn, sizeof(*psn), &target);
    if (err != noErr) { lognum("AECreateDesc ", err); return err; }
    err = AECreateAppleEvent(kSITCreator, kTranslateID, &target,
                             kAutoGenerateReturnID, kAnyTransactionID, &evt);
    AEDisposeDesc(&target);
    if (err != noErr) { lognum("AECreateAppleEvent ", err); return err; }

    /* The direct object is an ALIAS, which is what Aladdin's own sample
     * script sends ('alis' in its compiled bytes) and what the 'aete'
     * declares. Whether an FSSpec would also be accepted there is
     * untested — nothing needed it. */
    err = fileDesc(subject, shape->list, &obj);
    if (err != noErr) { lognum("subject desc ", err); return err; }
    err = AEPutParamDesc(&evt, keyDirectObject, &obj);
    AEDisposeDesc(&obj);
    if (err != noErr) { lognum("put direct ", err); return err; }

    err = AEPutParamPtr(&evt, keyUsing, typeChar, kTranslator,
                        (Size)sizeof(kTranslator) - 1);
    if (err != noErr) { lognum("put trnm ", err); return err; }
    if (shape->encoding) {
        err = AEPutParamPtr(&evt, keyEncoding, typeBoolean, &yes, sizeof(yes));
        if (err != noErr) { lognum("put encd ", err); return err; }
    }
    /* A destination is sent because the translator has a "Save ASCII
     * file as:" string in its STR# 128 and a modal box in the other
     * application would block everything after it. The shapes that sent
     * none also answered errn 0 — but that run had Returns typed at the
     * screen throughout, so what a destination-less send does on its own
     * is untested. */
    if (shape->dest == 1) {
        err = AEPutParamPtr(&evt, keyDest, typeFSS, dest, sizeof(*dest));
        if (err != noErr) { lognum("put dest ", err); return err; }
    } else if (shape->dest == 2) {
        err = fileDesc(folder, true, &destDesc);
        if (err == noErr) {
            err = AEPutParamDesc(&evt, keyDest, &destDesc);
            AEDisposeDesc(&destDesc);
        }
        if (err != noErr) { lognum("put dest ", err); return err; }
    }

    logs(shape->what);
    err = AESend(&evt, &reply, kAEWaitReply | kAECanInteract |
                 kAECanSwitchLayer, kAENormalPriority, 60L * 90L,
                 (IdleUPP)AEIdle, NULL);
    if (err != noErr) lognum("  AESend ", err);
    if (err == noErr) {
        if (AEGetParamPtr(&reply, keyErrNumber, typeSInt32, &got,
                          (Ptr)&code, sizeof(code), &size) == noErr)
            remote = (OSErr)code;
        lognum("  errn ", remote);
        AEDisposeDesc(&reply);
    }
    AEDisposeDesc(&evt);
    return err != noErr ? err : remote;
}

static void quitApp(ProcessSerialNumber *psn)
{
    AEAddressDesc target;
    AppleEvent evt, reply;
    if (AECreateDesc(typeProcessSerialNumber, psn, sizeof(*psn),
                     &target) != noErr) return;
    if (AECreateAppleEvent(kCoreEventClass, kAEQuitApplication, &target,
                           kAutoGenerateReturnID, kAnyTransactionID,
                           &evt) == noErr) {
        AESend(&evt, &reply, kAENoReply, kAENormalPriority,
               kAEDefaultTimeout, NULL, NULL);
        AEDisposeDesc(&evt);
    }
    AEDisposeDesc(&target);
}

/* ---------------------------------------------------------------- */

/* The shape that is sent. What the others answered was measured on
 * 2026-08-26, in one boot, and is the reason only this one is left:
 *
 *   alias + trnm + encd + dest as an 'fss ' naming the OUTPUT FILE
 *                                          errn -1700, coercion failed
 *   list  + trnm + encd + dest as an alias of the FOLDER   errn 0
 *   alias + trnm        + dest as an alias of the FOLDER   errn 0
 *   alias + trnm + encd                                    errn 0
 *   alias + trnm                                           errn 0
 *   list  + trnm                                           errn 0
 *
 * So the destination is a place, not a name — an FSSpec for a file that
 * does not exist yet cannot be coerced to whatever the handler asks for,
 * and every shape that names an existing folder, or names nothing at
 * all, is accepted. 'encd' decides the DIRECTION: without it the
 * translator decodes, and the run that tried all six left a `Subject.dec`
 * of zero bytes beside the `.ascii` to prove it.
 *
 * Set kAllShapes to try the whole matrix again; the log then carries one
 * line per shape. A specimen run wants exactly one, or nothing says
 * which shape wrote the file that came off the volume. */
#define kAllShapes 0

static const Shape kShapes[] = {
    { "list + trnm + encd + dest folder",  true,  true,  2 },
    { "alias + trnm + encd + dest fss",    false, true,  1 },
    { "alias + trnm + dest folder",        false, false, 2 },
    { "alias + trnm + encd",               false, true,  0 },
    { "alias + trnm",                      false, false, 0 },
    { "list + trnm",                       true,  false, 0 },
};

int main(void)
{
    Rect r;
    ProcessSerialNumber me, sit;
    ProcessInfoRec info;
    Str255 myName;
    FSSpec myself, subject, app, dest, folder, folderSpec;
    OSErr err;
    long attr;
    short i;

    MaxApplZone();
    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    InitMenus();
    TEInit();
    InitDialogs(NULL);
    InitCursor();

    SetRect(&r, 20, 60, 480, 300);
    gWin = NewWindow(NULL, &r, "\006aetran", true, documentProc,
                     (WindowPtr)-1L, false, 0);
    SetPort(gWin);
    TextFont(kFontIDMonaco);
    TextSize(9);
    gLine = 4;
    logs("aetran: StuffIt Deluxe translate, by Apple event");

    if (Gestalt(gestaltAppleEventsAttr, &attr) != noErr ||
        !(attr & (1L << gestaltAppleEventsPresent))) {
        logs("no Apple Event Manager on this System");
        spin(600);
        ExitToShell();
    }

    /* Where this application is, is where everything else is. Taken from
     * the Process Manager rather than from the default directory, which
     * is only the launch folder by convention. */
    GetCurrentProcess(&me);
    info.processInfoLength = sizeof(info);
    info.processName = myName;
    info.processAppSpec = &myself;
    err = GetProcessInformation(&me, &info);
    if (err != noErr) {
        lognum("GetProcessInformation ", err);
        spin(600);
        ExitToShell();
    }
    folder = myself;                    /* vRefNum + parID of our folder */

    subject = folder;
    BlockMoveData(kSubject, subject.name, kSubject[0] + 1);
    app = folder;
    BlockMoveData(kAppName, app.name, kAppName[0] + 1);
    dest = folder;
    BlockMoveData(kOutName, dest.name, kOutName[0] + 1);
    FSpDelete(&dest);                   /* a stale one would be read back
                                         * as this run's specimen */

    err = FSMakeFSSpec(folder.vRefNum, folder.parID, subject.name, &subject);
    if (err != noErr) { lognum("no Subject ", err); writelog(&folder);
                        spin(600); ExitToShell(); }
    err = FSMakeFSSpec(folder.vRefNum, folder.parID, app.name, &app);
    if (err != noErr) { lognum("no application ", err); writelog(&folder);
                        spin(600); ExitToShell(); }
    /* An empty name means the directory itself — the shape 'dest' takes
     * when it is a folder to put the result in rather than a file. */
    err = FSMakeFSSpec(folder.vRefNum, folder.parID, "\p", &folderSpec);
    if (err != noErr) lognum("no folder spec ", err);

    if (findProcess(kSITCreator, &sit)) {
        logs("StuffIt Deluxe already running");
    } else {
        logs("launching StuffIt Deluxe");
        err = launchApp(&app, &sit);
        if (err != noErr) {
            lognum("LaunchApplication ", err);
            writelog(&folder);
            spin(600);
            ExitToShell();
        }
        logs("launched");
    }

    /* One boot is minutes, so when the matrix is being re-measured every
     * shape goes in this one and the log carries what each answered. */
    for (i = 0; i < (short)(kAllShapes ? sizeof(kShapes) / sizeof(kShapes[0])
                                       : 1); i++)
        err = sendTranslate(&sit, &subject, &dest, &folderSpec, &kShapes[i]);
    spin(300);                          /* let it write and close */
    quitApp(&sit);
    spin(300);
    logs("done");
    writelog(&folder);
    spin(180);
    ExitToShell();
    return 0;
}
