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
 * the two cannot drift. All claimed: MacExtract. Any one not: the whole
 * list goes to the creator's own application, the first other one the
 * Desktop Manager knows for this stub's creator, launched the same way;
 * a volume without a Desktop Manager (System 6 and older) has none to
 * offer, and the stub says so (DECISIONS.md 2026-10-31, *the stub that
 * sorts*).
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
#include <Traps.h>

QDGlobals qd;

enum { kNotFoundAlert = 128, kLaunchAlert = 129, kNoOwnerAlert = 130,
       kReclaimedAlert = 131, kNoReclaimAlert = 132 };

static void Toolbox(void)
{
    static char done;

    if (done) return;
    done = 1;
    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    InitMenus();
    TEInit();
    InitDialogs(NULL);
    InitCursor();
}

/* The folder MacExtract should be in: the parent of the stub's own.
 * Also the stub's own name and folder, to tell it apart from the
 * creator's real application. */
static OSErr HomeFolder(short *vol, long *dir, Str255 name, long *self)
{
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

/* Whether MacExtract's bundle claims every document's type. The list is
 * AppParmHandle as MacExtract reads it (mac/macextract_mac.c, *Documents
 * handed over by the Finder*): message, count, then per document vRefNum,
 * fType at +2, versNum, the name at +8, the record padded to even. The
 * types are MacExtract's 'FREF's, the first four bytes of each, less the
 * ones that name no document format. The default directory must already
 * be MacExtract's folder. An empty list, or Print, is MacExtract's. */
static Boolean AllOpenable(Str255 mx)
{
    enum { kMaxTypes = 64 };
    OSType types[kMaxTypes];
    short nt = 0, i, j, n, ref, saved = CurResFile();
    Handle h = LMGetAppParmHandle(), r;
    const unsigned char *q;
    long off = 4;

    if (!h || !*h) return true;
    q = (const unsigned char *)*h;
    n = (short)((q[2] << 8) | q[3]);
    if (q[0] || q[1] || n <= 0) return true;

    ref = OpenResFile(mx);
    if (ref == -1) return true;          /* cannot tell: MacExtract decides */
    for (i = 1; nt < kMaxTypes; i++) {
        OSType t;
        r = Get1IndResource('FREF', i);
        if (!r) break;
        t = *(OSType *)*r;
        if (t != '****' && t != 'APPL' && t != 'fold' && t != 'disk')
            types[nt++] = t;
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

/* The first application of `creator` the Desktop Manager knows, on any
 * mounted volume, that is not this stub. Source: Inside Macintosh: Files,
 * Desktop Manager — PBDTGetPath for a volume's desktop database, then
 * PBDTGetAPPL by creator and index, which answers the name and the parent
 * folder (ioAPPLParID); a volume without a Desktop Manager refuses
 * PBDTGetPath (measured on System 3.0, 6.0.8 and a 7.0.1 floppy:
 * mac/macextract_mac.c, PBDTGetPath's comment). */
static Boolean FindOwner(OSType creator, short selfVol, long selfDir,
                         Str255 me, short *vol, long *dir, Str255 name)
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
        dt.ioCompletion = NULL;
        dt.ioNamePtr = NULL;
        dt.ioVRefNum = v.volumeParam.ioVRefNum;
        if (PBDTGetPath(&dt)) continue;
        for (k = 1; k < 32; k++) {
            dt.ioNamePtr = name;
            dt.ioIndex = k;
            dt.ioFileCreator = creator;
            if (PBDTGetAPPLSync(&dt)) break;
            if (v.volumeParam.ioVRefNum == selfVol
                && dt.ioAPPLParID == selfDir
                && EqualString(name, me, false, true)) continue;
            *vol = v.volumeParam.ioVRefNum;
            *dir = dt.ioAPPLParID;
            return true;
        }
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

/* A RUNNING MACEXTRACT. Under MultiFinder or System 7 a _Launch of an
 * application already running only brings it forward, and the documents
 * are lost. The System 6 Finder instead hands a running application its
 * documents as a "puppet string" (Technical Note OV17): MultiFinder picks
 * File > Open... in it and answers the dialog. It does so through
 * MultiFinder's private _OSDispatch calls, read out of the 6.0.8 Finder
 * (6.1.8, CODE 4) and MultiFinder (CODE 2, 'Puppet'); the stub makes the
 * same two, and System 7.0.1's Process Manager answers them too: its own
 * translation of an odoc ends in the same queue (scod -16464 $28A)
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
 * quits. Two conditions, both measured on 7.0.1: the call is made only
 * after the stub's own switch-in has finished (the Process Manager will
 * not start a puppet string while a switch is in progress, scod -16464
 * $5DC), so a second of WaitNextEvent first; and the stub stays a few
 * seconds after, since one that quits at once hands nothing on (that the
 * string goes with its poster is a hypothesis), hence canBackground in
 * 'SIZE'. */
pascal short MFProcesses(void *list, short max) M68K_INLINE(0x3F3C, 0x0001, 0xA88F);
pascal void MFPuppet(short process, Handle s, long z1, short z2) M68K_INLINE(0x3F3C, 0x0000, 0xA88F);

static void Settle(long ticks)
{
    EventRecord ev;
    long until = TickCount() + ticks;

    while (TickCount() < until)
        WaitNextEvent(everyEvent, &ev, 10, NULL);
}

/* 1 if a running MacExtract was handed the documents. */
static int Puppet(void)
{
    unsigned char list[32 * 10], *p;
    Handle ap = LMGetAppParmHandle(), h;
    ProcPtr none = NGetTrapAddress(_Unimplemented, kToolboxTrapType);
    short n, i, process = 0;
    long cnt, size, off;

    if (!ap || NGetTrapAddress(0xA88F, kToolboxTrapType) == none)
        return 0;                                   /* no MultiFinder */
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
    Toolbox();
    Settle(60);                                     /* the switch-in */
    MFPuppet(process, h, 0, 0);
    Settle(180);                                    /* and stay */
    return 1;
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
    short vol, ovol;
    long dir, self, odir;
    Str255 me, name, owner;
    WDPBRec wd;
    OSType creator;
    OSErr err;

    if (HomeFolder(&vol, &dir, me, &self) || FindMacExtract(vol, dir, name)) {
        Toolbox();
        StopAlert(kNotFoundAlert, NULL);
        return 0;
    }
    creator = OwnCreator(vol, self, me);

    /* Opened by itself: take the creator back, and stop there. */
    if (!HasDocuments()) {
        OSErr r = creator ? Reclaim(vol, self, me, creator) : fnfErr;
        Toolbox();
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
    wd.ioVRefNum = vol;
    wd.ioWDProcID = 'MXst';
    wd.ioWDDirID = dir;
    err = PBOpenWDSync(&wd);
    if (!err) err = SetVol(NULL, wd.ioVRefNum);

    if (!err && !AllOpenable(name)) {
        if (creator && FindOwner(creator, vol, self, me, &ovol, &odir, owner))
            err = LaunchIn(ovol, odir, owner);
        else {
            Toolbox();
            StopAlert(kNoOwnerAlert, NULL);
            return 0;
        }
    } else if (!err) {
        if (Puppet()) return 0;
        err = LaunchIn(vol, dir, name);
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
