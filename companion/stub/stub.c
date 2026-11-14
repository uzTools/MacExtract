/*
 * The companion's stub. The Finder launches it for a double-clicked
 * archive whose creator it claims, with that archive in the application's
 * Finder information (AppParmHandle); it finds MacExtract and launches it,
 * leaving that information alone, so MacExtract opens the archive exactly
 * as it opens one dropped on its icon. MacExtract itself is not changed.
 *
 * TRIAGE. A creator is not a format: StuffIt Expander's `SITx` and
 * StuffIt's `SIT!` are also on StuffIt X archives (type `SITX`, declared
 * by Expander 7.0.3's bundle), which MacExtract does not open. So the
 * documents' types, from the Finder's list, are checked against the types
 * MacExtract's own bundle claims, read out of MacExtract at run time so
 * the two cannot drift, and the types this helper's own bundle claims,
 * every one a type MacExtract opens (companion/helpers.tsv): DiskDoubler's
 * icon types are claimed by the `DDAP` helper alone (DECISIONS.md
 * 2026-11-13, *the icon types only the helper claims*). All claimed:
 * MacExtract. Any one not: the whole list goes to the creator's own
 * application, found as MacExtract is (below) and launched the same way
 * (DECISIONS.md 2026-10-31, *the stub that sorts*).
 *
 * RECLAIM. On Mac OS 9 the Finder gives a creator's documents to the
 * application registered LAST in the volume's desktop database (Apple's
 * Information Alley, May 1995; measured, DECISIONS.md 2026-10-31, *the
 * stub that sorts*), so installing StuffIt after MacExtract hands `SITx`
 * and `SIT!` back to it. A stub opened with NO document therefore removes
 * its own entry and adds it again (PBDTRemoveAPPL, PBDTAddAPPL, PBDTFlush;
 * Inside Macintosh: More Macintosh Toolbox, Desktop Manager), which makes
 * it the last registered, and says so. A volume without a Desktop Manager
 * (System 6 and older) has nothing to reclaim; there the stub says that.
 *
 * Its icons: registered by the stub itself where the Finder would not
 * (Icons, below).
 *
 * Where MacExtract is: wherever the Finder has seen it, on any mounted
 * volume — the application of creator MExt in the volume's desktop
 * database, or in its Desktop file where that lists none (FindApp, below). No
 * folder is assumed (the maintainer, 2026-11-03; DECISIONS.md 2026-11-03,
 * *the helper that asks the desktop*).
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
#include <Gestalt.h>
#include <Traps.h>
#include <AppleEvents.h>

/* No globals: the image is position-independent (-mpcrel) and runs
 * unrelocated, so nothing may live in .data or .bss, which no start-up code
 * here sets up. QuickDraw's globals sit in stub_main's frame, which lasts
 * the whole run; InitGraf records where through A5. */
typedef struct { QDGlobals qd; char done; } Tb;

enum { kNotFoundAlert = 128, kLaunchAlert = 129, kNoOwnerAlert = 130,
       kReclaimedAlert = 131, kNoReclaimAlert = 132 };

static void Toolbox(Tb *t)
{
    if (t->done) return;
    t->done = 1;
    InitGraf(&t->qd.thePort);
    InitFonts();
    InitWindows();
    InitMenus();
    TEInit();
    InitDialogs(NULL);
    InitCursor();
}

/* The stub's own volume, folder and name, to tell it apart from the
 * creator's real application. */
static OSErr HomeFolder(short *vol, Str255 name, long *self)
{
    short ref;
    Handle parms;
    FCBPBRec fcb;
    OSErr err;

    GetAppParms(name, &ref, &parms);
    fcb.ioCompletion = NULL;
    fcb.ioNamePtr = name;
    fcb.ioVRefNum = 0;
    fcb.ioRefNum = ref;
    fcb.ioFCBIndx = 0;
    err = PBGetFCBInfoSync(&fcb);
    if (err) return err;
    *vol = fcb.ioFCBVRefNum;
    *self = fcb.ioFCBParID;
    return noErr;
}

/* The stub's own creator: make_stub.py writes one per stub. */
static OSType OwnCreator(short vol, long self, Str255 me)
{
    CInfoPBRec c;
    c.hFileInfo.ioCompletion = NULL;
    c.hFileInfo.ioNamePtr = me;
    c.hFileInfo.ioVRefNum = vol;
    c.hFileInfo.ioFDirIndex = 0;
    c.hFileInfo.ioDirID = self;
    if (PBGetCatInfoSync(&c)) return 0;
    return c.hFileInfo.ioFlFndrInfo.fdCreator;
}

/* Whether MacExtract's bundle or this helper's claims every document's
 * type. The list is AppParmHandle as MacExtract reads it
 * (mac/macextract_mac.c, *Documents handed over by the Finder*): message,
 * count, then per document vRefNum, fType at +2, versNum, the name at +8,
 * the record padded to even. The types are the 'FREF's of this helper (the
 * current resource file) and then of MacExtract, the first four bytes of
 * each, less the ones that name no document format. The default directory
 * must already be MacExtract's folder. An empty list, or Print, is
 * MacExtract's. */
static Boolean AllOpenable(Str255 mx)
{
    enum { kMaxTypes = 128 };
    OSType types[kMaxTypes];
    short nt = 0, i, j, n, ref = 0, saved = CurResFile();
    Handle h = LMGetAppParmHandle(), r;
    const unsigned char *q;
    long off = 4;

    if (!h || !*h) return true;
    q = (const unsigned char *)*h;
    n = (short)((q[2] << 8) | q[3]);
    if (q[0] || q[1] || n <= 0) return true;

    for (;;) {
        for (i = 1; nt < kMaxTypes; i++) {
            OSType t;
            r = Get1IndResource('FREF', i);
            if (!r) break;
            t = *(OSType *)*r;
            if (t != '****' && t != 'APPL' && t != 'fold' && t != 'disk')
                types[nt++] = t;
        }
        if (ref) break;
        ref = OpenResFile(mx);
        if (ref == -1) return true;      /* cannot tell: MacExtract decides */
    }
    CloseResFile(ref);
    UseResFile(saved);

    for (i = 0; i < n; i++) {
        OSType t;
        q = (const unsigned char *)*h + off;
        t = ((OSType)q[2] << 24) | ((OSType)q[3] << 16)
            | ((OSType)q[4] << 8) | q[5];
        for (j = 0; j < nt && types[j] != t; j++) ;
        if (j == nt) return false;
        off += (8 + 1 + q[8] + 1) & ~1;
    }
    return true;
}

/* Whether the Finder handed over any document at all. */
static Boolean HasDocuments(void)
{
    Handle h = LMGetAppParmHandle();
    const unsigned char *q;
    if (!h || !*h) return false;
    q = (const unsigned char *)*h;
    return !q[0] && !q[1] && ((q[2] << 8) | q[3]) > 0;
}

/* Remove the stub's own entry from its volume's desktop database and add
 * it again, so it is the last registered for its creator. */
static OSErr Reclaim(short vol, long self, Str255 me, OSType creator)
{
    DTPBRec dt;
    OSErr err;

    dt.ioCompletion = NULL;
    dt.ioNamePtr = NULL;
    dt.ioVRefNum = vol;
    err = PBDTGetPath(&dt);
    if (err) return err;
    dt.ioNamePtr = me;
    dt.ioDirID = self;
    dt.ioFileCreator = creator;
    dt.ioTagInfo = 0;
    PBDTRemoveAPPLSync(&dt);              /* absent is not an error here */
    dt.ioNamePtr = me;
    dt.ioDirID = self;
    dt.ioFileCreator = creator;
    dt.ioTagInfo = 0;
    err = PBDTAddAPPLSync(&dt);
    if (!err) err = PBDTFlushSync(&dt);
    return err;
}

/* Whether `name` in `dir` is an application of `creator` that is not
 * this stub: an entry may outlive its file, or name a renamed one. One of
 * the stub's own creator in the stub's own folder is the stub. */
static Boolean IsApp(OSType creator, short vol, long dir, Str255 name,
                     short selfVol, long selfDir)
{
    CInfoPBRec c;

    if (vol == selfVol && dir == selfDir)
        return false;
    c.hFileInfo.ioCompletion = NULL;
    c.hFileInfo.ioNamePtr = name;
    c.hFileInfo.ioVRefNum = vol;
    c.hFileInfo.ioFDirIndex = 0;
    c.hFileInfo.ioDirID = dir;
    return !PBGetCatInfoSync(&c) && c.hFileInfo.ioFlFndrInfo.fdCreator == creator;
}

/* Where the Finder keeps no desktop database (System 6 and older, and a
 * 7.0.1 floppy): the 'APPL' resource 0 of its Desktop file, the Finder's list of
 * the applications it has seen, opened read-only (OpenRFPerm, Inside
 * Macintosh IV, The Resource Manager) so a Finder holding it open is not
 * disturbed. The resource's layout is MEASURED, not documented: entries
 * of creator, folder ID and name, each padded to even, newest first, read
 * off the System 3.0 and 6.0.8 Finders' Desktop files (tools/vmac/
 * deskclaim.py, *appl_parse*). Every entry starts on an even offset of
 * the handle, so its creator and folder are read as longs. */
static Boolean DesktopFile(OSType creator, short vol, long *dir, Str255 name,
                           short selfVol, long selfDir)
{
    short saved = CurResFile(), ref;
    Handle h;
    unsigned char *e, *end;
    Boolean found = false;

    ref = OpenRFPerm((ConstStr255Param)"\pDesktop", vol, fsRdPerm);
    if (ref == -1) return false;
    h = Get1Resource('APPL', 0);
    if (h) {
        HLock(h);
        e = (unsigned char *)*h;
        end = e + GetHandleSize(h);
        for (; e + 9 <= end && e + 9 + e[8] <= end && !found;
             e += (9 + e[8] + 1) & ~1) {
            if (*(OSType *)e != creator) continue;
            BlockMoveData(e + 8, name, e[8] + 1);
            *dir = *(long *)(e + 4);
            found = IsApp(creator, vol, *dir, name, selfVol, selfDir);
        }
    }
    CloseResFile(ref);
    UseResFile(saved);
    return found;
}

/* ICONS. The 7.0.1 Finder registers no bundle short of a desktop
 * rebuild, so a helper and its archives draw generic icons there until
 * one (measured; DECISIONS.md 2026-11-03, *the helper that asks the
 * desktop*). The stub registers its own, as StuffIt Expander 4.0.2 and
 * MacExtract do (mac/macextract_mac.c, DTBundle; DECISIONS.md 2026-10-18,
 * *the icon Expander registers*): per 'FREF', the six members of the one
 * icon family, ID 128, through PBDTAddIcon as icon types 1 to 6 (Inside
 * Macintosh: More Macintosh Toolbox, Desktop Manager). Every 'FREF' is on
 * local icon 0, which is that family (companion/make_stub.py; checked by
 * tools/check_helpers.py), so the 'BNDL' is not read. Unless `force`,
 * only when the database has no large icon for the first 'FREF' under
 * this creator yet, so a double-click does not rewrite it each time. A
 * volume without a Desktop Manager is the Finder's to fill. */
static void Icons(short vol, OSType creator, Boolean force)
{
    static const OSType kIcon[6] =
        { 'ICN#', 'icl4', 'icl8', 'ics#', 'ics4', 'ics8' };
    DTPBRec d;
    Handle f, h;
    char probe[256];
    short i, n;

    d.ioCompletion = NULL;
    d.ioNamePtr = NULL;
    d.ioVRefNum = vol;
    if (PBDTGetPath(&d)) return;
    d.ioFileCreator = creator;
    for (i = 1; (f = Get1IndResource('FREF', i)) != NULL; i++) {
        d.ioFileType = *(OSType *)*f;
        if (i == 1 && !force) {
            d.ioTagInfo = 0;
            d.ioDTBuffer = probe;
            d.ioDTReqCount = sizeof probe;
            d.ioIconType = 1;
            if (!PBDTGetIconSync(&d)) return;
        }
        for (n = 0; n < 6; n++) {
            h = Get1Resource(kIcon[n], 128);
            if (!h) continue;
            HLock(h);
            d.ioTagInfo = 0;
            d.ioDTBuffer = *h;
            d.ioDTReqCount = GetHandleSize(h);
            d.ioIconType = (SignedByte)(n + 1);
            PBDTAddIconSync(&d);
            HUnlock(h);
        }
    }
    PBDTFlushSync(&d);
}

/* The first application of `creator` the Finder has seen, on any mounted
 * volume, that is not this stub: by PBDTGetAPPL from the volume's desktop
 * database (Source: Inside Macintosh: More Macintosh Toolbox, Desktop
 * Manager — PBDTGetPath, then PBDTGetAPPL by creator and index, which
 * answers the name and the parent folder, ioAPPLParID), then from its
 * Desktop file. Both, on every volume: PBDTGetPath refuses on System 3.0,
 * 6.0.8 and a 7.0.1 floppy (mac/macextract_mac.c, PBDTGetPath's comment),
 * but a database that answers need not be the Finder's. PBDTGetPath opens
 * one, "If the desktop database is not open" (the same chapter), and under
 * AppleShare's `Desktop Mgr` INIT on System 6.0.8 it creates one on every
 * volume, empty, while that Finder keeps the Desktop file: PBDTGetAPPL
 * then answers -5012 and only the Desktop file lists MacExtract (measured;
 * DECISIONS.md 2026-11-13, *the database that lists nothing*). */
static Boolean FindApp(OSType creator, short selfVol, long selfDir,
                       short *vol, long *dir, Str255 name)
{
    HParamBlockRec v;
    DTPBRec dt;
    short vi, k;

    for (vi = 1; ; vi++) {
        v.volumeParam.ioCompletion = NULL;
        v.volumeParam.ioNamePtr = NULL;
        v.volumeParam.ioVRefNum = 0;
        v.volumeParam.ioVolIndex = vi;
        if (PBHGetVInfoSync(&v)) return false;
        *vol = v.volumeParam.ioVRefNum;
        dt.ioCompletion = NULL;
        dt.ioNamePtr = NULL;
        dt.ioVRefNum = *vol;
        if (!PBDTGetPath(&dt))
            for (k = 1; k < 32; k++) {
                dt.ioNamePtr = name;
                dt.ioIndex = k;
                dt.ioFileCreator = creator;
                if (PBDTGetAPPLSync(&dt)) break;
                *dir = dt.ioAPPLParID;
                if (IsApp(creator, *vol, *dir, name, selfVol, selfDir))
                    return true;
            }
        if (DesktopFile(creator, *vol, dir, name, selfVol, selfDir))
            return true;
    }
}

/* _Launch `name` in `dir`, which becomes the default directory. Returns
 * only if the launch failed. */
static OSErr LaunchIn(short vol, long dir, Str255 name)
{
    WDPBRec wd;
    LaunchParamBlockRec lp;
    OSErr err;

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
        err = LaunchApplication(&lp);
    }
    return err;
}

/* MULTIFINDER. Under System 6's MultiFinder a _Launch of an application
 * already running only brings it forward, and the documents are lost.
 * The Finder instead hands a running application its documents as a
 * "puppet string" (Technical Note OV17), through MultiFinder's private
 * _OSDispatch calls, read out of the System 6.0.8 Finder (6.1.8, CODE 4)
 * and MultiFinder (CODE 2, 'Puppet'); the stub makes the same two calls
 * (DECISIONS.md 2026-11-01, *the Open item MultiFinder looks for*).
 * Selector 1 lists the processes, 10 bytes each: number, creator, and
 * four bytes the stub does not read (0 on 6.0.8 and 7.0.1, measured).
 * Selector 0 queues the string: the process number, a handle, a long 0
 * and a word 0. The handle: a long offset to the next event (6), a word
 * count, that many 16-byte EventRecords, then the Finder's document list
 * copied whole; one record per document, `what` 15 and `message` $0C in
 * the high byte with the document's offset in the handle below it, and a
 * last record of `what` $2000. MultiFinder disposes of it once played,
 * so it goes in the system heap: the stub's own heap is gone when it
 * quits. System 6 only, where there is no Apple Event Manager; under
 * System 7 and Mac OS 9 the stub posts an odoc instead (Odoc, below):
 * 7.0.1 plays this string too, but Mac OS 9.2 answers MacExtract's dialog
 * from somewhere other than the document records, and MacExtract cannot
 * open what it is given (measured; DECISIONS.md 2026-11-01, *the Open
 * item MultiFinder looks for*). */
pascal short MFProcesses(void *list, short max) M68K_INLINE(0x3F3C, 0x0001, 0xA88F);
pascal void MFPuppet(short process, Handle s, long z1, short z2) M68K_INLINE(0x3F3C, 0x0000, 0xA88F);

/* 1 if a running MacExtract was handed the documents. */
static int Puppet(void)
{
    unsigned char list[32 * 10], *p;
    Handle ap = LMGetAppParmHandle(), h;
    ProcPtr none = NGetTrapAddress(_Unimplemented, kToolboxTrapType);
    short n, i, process = 0;
    long cnt, size, off, ae;

    if (!ap || NGetTrapAddress(0xA88F, kToolboxTrapType) == none)
        return 0;                                   /* no MultiFinder */
    if (NGetTrapAddress(0xA1AD, kOSTrapType) != none
        && !Gestalt(gestaltAppleEventsAttr, &ae) && (ae & 1))
        return 0;                                   /* System 7 or later */
    n = MFProcesses(list, 32);
    for (i = 0; i < n && i < 32; i++) {
        p = list + i * 10;
        if (p[2] == 'M' && p[3] == 'E' && p[4] == 'x' && p[5] == 't')
            process = (short)(p[0] << 8 | p[1]);
    }
    if (!process) return 0;

    size = GetHandleSize(ap);
    cnt = (*(unsigned char **)ap)[2] << 8 | (*(unsigned char **)ap)[3];
    off = 6 + (cnt + 1) * 16;
    h = NewHandleSysClear(off + size);
    if (!h) return 0;
    p = *(unsigned char **)h;
    p[3] = 6;
    p[4] = (unsigned char)((cnt + 1) >> 8);
    p[5] = (unsigned char)(cnt + 1);
    BlockMoveData(*ap, p + off, size);
    off += 4;                                       /* message and count */
    for (i = 0; i < cnt; i++) {
        unsigned char *e = p + 6 + i * 16;
        e[1] = 15;
        e[2] = 0x0C;
        e[3] = (unsigned char)(off >> 16);
        e[4] = (unsigned char)(off >> 8);
        e[5] = (unsigned char)off;
        off += (p[off + 8] + 10) & ~1;
    }
    p[6 + cnt * 16] = 0x20;                         /* `what` $2000: the end */
    MFPuppet(process, h, 0, 0);
    return 1;
}

/* SYSTEM 7. The 7.0.1 Finder hands a running application its documents
 * by PostHighLevelEvent of an odoc to its process serial number, after
 * SetFrontProcess (Finder 7.0.1 CODE 160 $644, $8D4; CODE 10 $46A). For a
 * process with no high-level event port, as MacExtract, the Process
 * Manager turns the event into a puppet string itself (scod -16462 $1802
 * picks that path, -16464 $5BC builds it), on two conditions read there
 * and measured: no process switch in progress (else protocolErr, -603;
 * a helper just launched is in one, so it lets its own switch finish in
 * WaitNextEvent first and asks again on -603), and every document an
 * alias ('alis'; anything else is paramErr, and nothing arrives); and
 * the stub stays running after posting until the string has played,
 * which is MacExtract's next event call (one that quits at once hands
 * nothing on; measured). Mac OS 9.2 takes the same event. The
 * event goes out as its Process Manager form, the AppParameters block an
 * odoc coerces to: the EventRecord at +0, refcon +16, length +20, the
 * message at +24 (the Finder's own call reads the same offsets). AESend
 * would not do: a sender that is not high-level-event aware may not use
 * it (noPortErr, -903), and the stub stays unaware so that the Finder
 * keeps handing it the documents in the Finder information
 * (DECISIONS.md 2026-11-01, *the Open item MultiFinder looks for*). */
#define typeAppParameters 'appa'
/* Retro68's headers lack these. Source: Inside Macintosh — Interapplication
 * Communication, PostHighLevelEvent's posting options (receiverIDisPSN
 * $8000, which the 7.0.1 Finder passes) and Processes (protocolErr -603,
 * which the 7.0.1 Process Manager returns at scod -16464 $5E6). */
#define receiverIDisPSN 0x8000
#define protocolErr (-603)

static void Settle(long ticks)
{
    EventRecord ev;
    long until = TickCount() + ticks;

    while (TickCount() < until)
        WaitNextEvent(everyEvent, &ev, 10, NULL);
}

/* 1 if a running MacExtract was handed the documents. */
static int Odoc(Tb *tb)
{
    Handle ap = LMGetAppParmHandle();
    ProcessSerialNumber psn = { 0, kNoProcess };
    ProcessInfoRec pi;
    AEAddressDesc target;
    AppleEvent ev;
    AEDescList docs;
    AEDesc parm;
    AliasHandle al;
    FSSpec fs;
    unsigned char *p, *a;
    long cnt, i, off, ae;
    OSErr err;
    short k;

    if (!ap || NGetTrapAddress(0xA1AD, kOSTrapType)
               == NGetTrapAddress(_Unimplemented, kToolboxTrapType)
        || Gestalt(gestaltAppleEventsAttr, &ae) || !(ae & 1))
        return 0;
    for (;;) {
        if (GetNextProcess(&psn)) return 0;         /* not running */
        pi.processInfoLength = sizeof pi;
        pi.processName = NULL;
        pi.processAppSpec = NULL;
        if (!GetProcessInformation(&psn, &pi) && pi.processSignature == 'MExt')
            break;
    }
    if (AECreateDesc(typeProcessSerialNumber, &psn, sizeof psn, &target)
        || AECreateAppleEvent(kCoreEventClass, kAEOpenDocuments, &target,
                              kAutoGenerateReturnID, kAnyTransactionID, &ev)
        || AECreateList(NULL, 0, false, &docs))
        return 0;
    HLock(ap);
    p = *(unsigned char **)ap;
    cnt = p[2] << 8 | p[3];
    err = 0;
    for (i = 0, off = 4; i < cnt && !err; i++) {
        al = NULL;
        err = FSMakeFSSpec((short)(p[off] << 8 | p[off + 1]), 0, p + off + 8, &fs);
        if (!err) err = NewAlias(NULL, &fs, &al);
        if (!err) {
            HLock((Handle)al);
            err = AEPutPtr(&docs, 0, typeAlias, *al, GetHandleSize((Handle)al));
        }
        off += (p[off + 8] + 10) & ~1;
    }
    HUnlock(ap);
    if (err || AEPutParamDesc(&ev, keyDirectObject, &docs)
        || AECoerceDesc(&ev, typeAppParameters, &parm))
        return 0;
    HLock(parm.dataHandle);
    a = *(unsigned char **)parm.dataHandle;
    Toolbox(tb);
    for (k = 0; k < 10; k++) {
        Settle(k ? 30 : 60);
        err = PostHighLevelEvent((EventRecord *)a, (Ptr)&psn,
                                 *(long *)(a + 16), (Ptr)(a + 24),
                                 *(long *)(a + 20), receiverIDisPSN);
        if (err != protocolErr) break;
    }
    /* Then stay: the WaitNextEvent that blocks returns once MacExtract
     * has made its next event call and the string has played (DECISIONS.md
     * 2026-11-01, *How long the helper must stay*). MacExtract has the
     * front by then, hence canBackground in 'SIZE'. */
    if (!err) Settle(180);
    return !err;
}

static int stub_main(void);
/* The entry point, in place of Retro68's _start: nothing to relocate,
 * no constructors, and out through ExitToShell as Retro68's _exit leaves
 * (mac/mac_start.c does the same for MacExtract, less the relocation). */
void stub_start(void)
{
    stub_main();
    ExitToShell();
}

static int stub_main(void)
{
    Tb t, *tb = &t;
    short vol, mvol, ovol;
    long dir, self, odir;
    Str255 me, name, owner;
    WDPBRec wd;
    OSType creator;
    OSErr err;

    t.done = 0;
    if (HomeFolder(&vol, me, &self)) return 0;
    creator = OwnCreator(vol, self, me);
    if (creator) Icons(vol, creator, !HasDocuments());
    /* No folder is excluded: MacExtract is never this stub, and beside it
     * in one folder it was skipped (DECISIONS.md 2026-11-13, *the helper
     * beside MacExtract*). Folder ID 0 names none. */
    if (!FindApp('MExt', vol, 0, &mvol, &dir, name)) {
        Toolbox(tb);
        StopAlert(kNotFoundAlert, NULL);
        return 0;
    }

    /* Opened by itself: take the creator back, and stop there. */
    if (!HasDocuments()) {
        OSErr r = creator ? Reclaim(vol, self, me, creator) : fnfErr;
        Toolbox(tb);
        if (r) {
            Str255 num;
            NumToString(r, num);
            ParamText(num, NULL, NULL, NULL);
            StopAlert(kNoReclaimAlert, NULL);
        } else {
            NoteAlert(kReclaimedAlert, NULL);
        }
        return 0;
    }

    /* MacExtract's folder as the default directory, for OpenResFile here
     * and for _Launch, which names the application relative to it. */
    wd.ioCompletion = NULL;
    wd.ioNamePtr = NULL;
    wd.ioVRefNum = mvol;
    wd.ioWDProcID = 'MXst';
    wd.ioWDDirID = dir;
    err = PBOpenWDSync(&wd);
    if (!err) err = SetVol(NULL, wd.ioVRefNum);

    if (!err && !AllOpenable(name)) {
        if (creator && FindApp(creator, vol, self, &ovol, &odir, owner))
            err = LaunchIn(ovol, odir, owner);
        else {
            Toolbox(tb);
            StopAlert(kNoOwnerAlert, NULL);
            return 0;
        }
    } else if (!err) {
        if (Puppet() || Odoc(tb)) return 0;
        err = LaunchIn(mvol, dir, name);
    }

    Toolbox(tb);
    {
        Str255 num;
        NumToString(err, num);
        ParamText(num, NULL, NULL, NULL);
    }
    StopAlert(kLaunchAlert, NULL);
    return 0;
}
