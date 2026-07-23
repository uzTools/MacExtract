/*
 * unclassic_mac.c — minimal Macintosh Toolbox shell around
 * libunclassic. Compile-only target (M10): built with Retro68 for
 * plain 68000, floor System 6.0.x on a 1 MB Mac Plus; the same binary
 * runs unchanged through Mac OS 9.
 *
 * Design (see CLAUDE.md M10):
 *   - SFGetFile to pick an archive; extraction lands in the archive's
 *     folder; loop back to SFGetFile until Cancel.
 *   - Event loop on GetNextEvent + SystemTask; WaitNextEvent is used
 *     only after a runtime trap check.
 *   - Modal progress dialog with a Cancel button (and Cmd-.).
 *   - Streaming writes to the data fork and resource fork (HOpenRF),
 *     then PBSetCatInfo for type/creator/Finder flags/dates.
 *   - 31-character, colon-free name sanitization with collision
 *     suffixes; the engine's reversible '/'->':' swap is undone here
 *     (':' in an engine component was '/' in the original Mac name).
 *   - SetApplLimit stack bump before MaxApplZone.
 *   - Engine memory goes through NewPtr with a FreeMem()-derived
 *     budget: allocation failures surface as clean per-entry errors.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */

#include <Dialogs.h>
#include <Devices.h>
#include <Events.h>
#include <Files.h>
#include <Fonts.h>
#include <Memory.h>
#include <Menus.h>
#include <OSUtils.h>
#include <Quickdraw.h>
#include <StandardFile.h>
#include <TextUtils.h>
#include <ToolUtils.h>
#include <Traps.h>
#include <Windows.h>

#include "unclassic.h"

#define kProgressDLOG   128
#define kDoneALRT       129
#define kErrorALRT      130
#define kCancelItem     1
#define kStatusItem     2

#define kStackBump      (24L * 1024)   /* extra stack over the 8 KB default */
#define kMemReserve     (80L * 1024)   /* heap headroom kept from the engine */

#ifndef ioDirMask
#define ioDirMask 0x10   /* ioFlAttrib bit 4 = "is a directory"
                          * (Inside Macintosh: Files, CInfoPBRec) */
#endif

/* ------------------------------------------------------------------ */
/* Runtime environment checks                                         */
/* ------------------------------------------------------------------ */

static Boolean gHasWNE;

static Boolean TrapAvailable(short trap)
{
    /* Multiversal names: kToolboxTrapType/kOSTrapType. */
    TrapType tt = (trap & 0x0800) ? kToolboxTrapType : kOSTrapType;
    return NGetTrapAddress((uint16_t)trap, tt) !=
           NGetTrapAddress(_Unimplemented, kToolboxTrapType);
}

/* ------------------------------------------------------------------ */
/* UncIO over the File Manager                                        */
/* ------------------------------------------------------------------ */

typedef struct {
    short  refNum;
    long   size;
} MacIO;

static int32_t mio_read(void *ctx, void *buf, int32_t len)
{
    MacIO *io = (MacIO *)ctx;
    long count = len;
    OSErr err = FSRead(io->refNum, &count, buf);
    if (err != noErr && err != eofErr) return -1;
    return (int32_t)count;
}

static int mio_seek(void *ctx, uint32_t pos)
{
    MacIO *io = (MacIO *)ctx;
    return SetFPos(io->refNum, fsFromStart, (long)pos) == noErr ? 0 : -1;
}

static uint32_t mio_tell(void *ctx)
{
    MacIO *io = (MacIO *)ctx;
    long pos = 0;
    GetFPos(io->refNum, &pos);
    return (uint32_t)pos;
}

static uint32_t mio_size(void *ctx)
{
    MacIO *io = (MacIO *)ctx;
    return (uint32_t)io->size;
}

/* ------------------------------------------------------------------ */
/* UncAlloc over NewPtr with a budget                                 */
/* ------------------------------------------------------------------ */

typedef struct {
    long budget;    /* remaining bytes the engine may hold */
} MacAlloc;

static void *mal_alloc(void *ctx, uint32_t size)
{
    MacAlloc *a = (MacAlloc *)ctx;
    Ptr p;
    if ((long)size + 16 > a->budget) return NULL;
    p = NewPtr((long)size + 16);
    if (p == NULL) return NULL;
    *(long *)p = (long)size;
    a->budget -= (long)size + 16;
    return p + 16;
}

static void mal_free(void *ctx, void *ptr)
{
    MacAlloc *a = (MacAlloc *)ctx;
    Ptr p = (Ptr)ptr - 16;
    a->budget += *(long *)p + 16;
    DisposePtr(p);
}

/* ------------------------------------------------------------------ */
/* Progress dialog                                                    */
/* ------------------------------------------------------------------ */

typedef struct {
    DialogPtr dlg;
    Boolean   cancelled;
    long      lastTicks;
} Progress;

static void ProgressPump(Progress *pr)
{
    EventRecord ev;
    Boolean got;

    if (gHasWNE) got = WaitNextEvent(everyEvent, &ev, 1, NULL);
    else {
        SystemTask();
        got = GetNextEvent(everyEvent, &ev);
    }
    if (got) {
        if (ev.what == keyDown &&
            (ev.modifiers & cmdKey) &&
            (char)(ev.message & charCodeMask) == '.') {
            pr->cancelled = true;
            return;
        }
        if (IsDialogEvent(&ev)) {
            DialogPtr hit;
            short item;
            if (DialogSelect(&ev, &hit, &item) &&
                hit == pr->dlg && item == kCancelItem)
                pr->cancelled = true;
        }
    }
}

static int prog_tick(void *ctx, uint32_t done, uint32_t total)
{
    Progress *pr = (Progress *)ctx;
    long now = TickCount();
    if (now - pr->lastTicks >= 6) {      /* ~10 Hz */
        pr->lastTicks = now;
        ProgressPump(pr);
        if (total != UNC_SIZE_UNKNOWN && total != 0 && pr->dlg) {
            Str255 s;
            long pct = (long)((done / 128) * 100 / (total / 128 + 1));
            Handle h;
            short kind;
            Rect box;
            NumToString(pct, s);
            s[++s[0]] = '%';
            GetDialogItem(pr->dlg, kStatusItem, &kind, &h, &box);
            if (h) SetDialogItemText(h, s);
        }
    }
    return pr->cancelled ? 0 : 1;
}

/* ------------------------------------------------------------------ */
/* Disk sink: HFS files, both forks, then catalog info                */
/* ------------------------------------------------------------------ */

typedef struct {
    short        vRefNum;      /* destination volume */
    long         rootDirID;    /* destination folder */
    long         curDirID;     /* directory of the current entry */
    Str63        curName;      /* sanitized current file name */
    short        dataRef, rsrcRef;
    UncEntryInfo cur;
    int          entries, errors;
    Progress    *pr;
} MacSink;

/* One engine path component -> Pascal Str63: undo the '/'->':' swap,
 * strip any stray ':' (illegal in an HFS name), cap at 31 chars. */
static void ComponentToStr63(const uint8_t *comp, int len, Str63 out)
{
    int i, o = 0;
    for (i = 0; i < len && o < 31; i++) {
        unsigned char b = comp[i];
        if (b == ':') b = '/';           /* reversible swap undone */
        out[++o] = b;
    }
    if (o == 0) out[++o] = '_';
    out[0] = (unsigned char)o;
}

/* Append a collision suffix "~1".."~9" within 31 chars. */
static void BumpName(Str63 name, int attempt)
{
    int len = name[0];
    if (len > 29) len = 29;
    name[len + 1] = '~';
    name[len + 2] = (unsigned char)('0' + attempt);
    name[0] = (unsigned char)(len + 2);
}

/* DirCreate via the parameter-block call (the Multiversal interfaces
 * expose PBDirCreateSync only; HFileParam.ioDirID carries the parent
 * in and the new directory id out). */
static OSErr MyDirCreate(short vRefNum, long parent, StringPtr name,
                         long *created)
{
    HParamBlockRec pb;
    OSErr err;
    pb.fileParam.ioCompletion = NULL;
    pb.fileParam.ioNamePtr = name;
    pb.fileParam.ioVRefNum = vRefNum;
    pb.fileParam.ioDirID = parent;
    err = PBDirCreateSync(&pb);
    *created = pb.fileParam.ioDirID;
    return err;
}

/* Create (or descend into) one directory level. */
static OSErr EnsureDir(short vRefNum, long parent, Str63 name, long *dirID)
{
    long created;
    OSErr err = MyDirCreate(vRefNum, parent, name, &created);
    if (err == noErr) {
        *dirID = created;
        return noErr;
    }
    if (err == dupFNErr) {
        /* Exists: file or folder? Look it up. */
        CInfoPBRec pb;
        Str63 tmp;
        BlockMoveData(name, tmp, name[0] + 1);
        pb.dirInfo.ioNamePtr = tmp;
        pb.dirInfo.ioVRefNum = vRefNum;
        pb.dirInfo.ioDrDirID = parent;
        pb.dirInfo.ioFDirIndex = 0;
        if (PBGetCatInfoSync(&pb) == noErr &&
            (pb.dirInfo.ioFlAttrib & ioDirMask)) {
            *dirID = pb.dirInfo.ioDrDirID;
            return noErr;
        }
    }
    return err;
}

static int sink_begin(void *ctx, const UncEntryInfo *info)
{
    MacSink *s = (MacSink *)ctx;
    long dir = s->rootDirID;
    int start = 0, i, attempt;
    OSErr err;

    s->cur = *info;
    s->entries++;
    s->dataRef = s->rsrcRef = 0;

    /* Walk the '/'-separated engine path, creating directories. */
    for (i = 0; i <= info->name_len; i++) {
        if (i == info->name_len || info->name[i] == '/') {
            Str63 comp;
            ComponentToStr63(info->name + start, i - start, comp);
            if (i == info->name_len && !info->is_dir) {
                BlockMoveData(comp, s->curName, comp[0] + 1);
                s->curDirID = dir;
            } else {
                if (EnsureDir(s->vRefNum, dir, comp, &dir) != noErr)
                    return -1;
                if (i == info->name_len) return 1;   /* dir entry done */
            }
            start = i + 1;
        }
    }

    /* Create the file, bumping the name on collisions ("name~1"...). */
    {
        Str63 base;
        BlockMoveData(s->curName, base, s->curName[0] + 1);
        for (attempt = 0; ; attempt++) {
            err = HCreate(s->vRefNum, s->curDirID, s->curName,
                          0x3F3F3F3FL, 0x3F3F3F3FL);   /* '????' */
            if (err == noErr) break;
            if (err != dupFNErr || attempt >= 9) return -1;
            BlockMoveData(base, s->curName, base[0] + 1);
            BumpName(s->curName, attempt + 1);
        }
    }
    return 0;
}

static int sink_write(void *ctx, UncFork fork, const void *buf, int32_t len)
{
    MacSink *s = (MacSink *)ctx;
    long count = len;
    OSErr err;
    short *ref = fork == UNC_FORK_DATA ? &s->dataRef : &s->rsrcRef;

    if (*ref == 0) {
        err = fork == UNC_FORK_DATA
            ? HOpen(s->vRefNum, s->curDirID, s->curName, fsWrPerm, ref)
            : HOpenRF(s->vRefNum, s->curDirID, s->curName, fsWrPerm, ref);
        if (err != noErr) return -1;
    }
    if (len == 0) return 0;
    err = FSWrite(*ref, &count, (Ptr)buf);
    return err == noErr && count == len ? 0 : -1;
}

static int sink_end(void *ctx, int status)
{
    MacSink *s = (MacSink *)ctx;

    if (s->dataRef) { FSClose(s->dataRef); s->dataRef = 0; }
    if (s->rsrcRef) { FSClose(s->rsrcRef); s->rsrcRef = 0; }

    if (status == UNC_OK && !s->cur.is_dir) {
        /* Set type/creator, Finder flags and dates. */
        CInfoPBRec pb;
        Str63 name;
        BlockMoveData(s->curName, name, s->curName[0] + 1);
        pb.hFileInfo.ioNamePtr = name;
        pb.hFileInfo.ioVRefNum = s->vRefNum;
        pb.hFileInfo.ioDirID = s->curDirID;
        pb.hFileInfo.ioFDirIndex = 0;
        if (PBGetCatInfoSync(&pb) == noErr) {
            if (s->cur.type)    pb.hFileInfo.ioFlFndrInfo.fdType = s->cur.type;
            if (s->cur.creator) pb.hFileInfo.ioFlFndrInfo.fdCreator = s->cur.creator;
            pb.hFileInfo.ioFlFndrInfo.fdFlags =
                s->cur.finder_flags & ~0x0100;   /* clear inited bit */
            if (s->cur.create_date) pb.hFileInfo.ioFlCrDat = s->cur.create_date;
            if (s->cur.mod_date)    pb.hFileInfo.ioFlMdDat = s->cur.mod_date;
            pb.hFileInfo.ioDirID = s->curDirID;  /* PBGetCatInfo clobbers it */
            PBSetCatInfoSync(&pb);
        }
    }
    if (status != UNC_OK) s->errors++;
    return 0;
}

/* ------------------------------------------------------------------ */
/* Extraction driver                                                  */
/* ------------------------------------------------------------------ */

static void ShowNote(short alrtID, const unsigned char *msg)
{
    ParamText(msg, "\p", "\p", "\p");
    NoteAlert(alrtID, NULL);
}

static void ExtractOne(short vRefNum, long dirID, ConstStr255Param name)
{
    MacIO mio;
    UncIO io;
    MacAlloc ma;
    UncAlloc al;
    MacSink sink;
    UncSink sk;
    Progress pr;
    UncProgress prog;
    UncOptions opt;
    OSErr err;
    int ret;

    err = HOpen(vRefNum, dirID, name, fsRdPerm, &mio.refNum);
    if (err != noErr) {
        ShowNote(kErrorALRT, "\pCould not open the archive.");
        return;
    }
    GetEOF(mio.refNum, &mio.size);

    io.ctx = &mio;
    io.read = mio_read;
    io.seek = mio_seek;
    io.tell = mio_tell;
    io.size = mio_size;

    ma.budget = FreeMem() - kMemReserve;
    if (ma.budget < 32L * 1024) ma.budget = 32L * 1024;
    al.ctx = &ma;
    al.alloc = mal_alloc;
    al.free = mal_free;

    pr.dlg = GetNewDialog(kProgressDLOG, NULL, (WindowPtr)-1);
    pr.cancelled = false;
    pr.lastTicks = 0;
    if (pr.dlg) DrawDialog(pr.dlg);
    prog.ctx = &pr;
    prog.tick = prog_tick;

    sink.vRefNum = vRefNum;
    sink.rootDirID = dirID;
    sink.entries = sink.errors = 0;
    sink.pr = &pr;
    sk.ctx = &sink;
    sk.begin_entry = sink_begin;
    sk.write = sink_write;
    sk.end_entry = sink_end;

    opt.list_only = 0;
    opt.test_only = 0;
    opt.name_hint = name + 1;            /* Pascal string body */
    opt.name_hint_len = name[0];

    ret = unc_extract(&io, &sk, &al, &prog, &opt);

    FSClose(mio.refNum);
    if (pr.dlg) DisposeDialog(pr.dlg);

    if (pr.cancelled)
        ShowNote(kDoneALRT, "\pExtraction cancelled.");
    else if (ret != UNC_OK)
        ShowNote(kErrorALRT, "\pThis file could not be extracted.");
    else if (sink.errors)
        ShowNote(kErrorALRT, "\pSome entries could not be extracted.");
    else
        ShowNote(kDoneALRT, "\pExtraction complete.");
}

/* ------------------------------------------------------------------ */
/* main                                                               */
/* ------------------------------------------------------------------ */

int main(void)
{
    Point where;

    /* LMGetApplLimit: the GetApplLimit glue is absent from the
     * Multiversal import libraries; the low-memory accessor is the
     * documented equivalent (ApplLimit at 0x0130). */
    SetApplLimit((Ptr)((long)LMGetApplLimit() - kStackBump));
    MaxApplZone();
    MoreMasters();
    MoreMasters();

    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    InitMenus();
    TEInit();
    InitDialogs(NULL);
    InitCursor();
    FlushEvents(everyEvent, 0);

    gHasWNE = TrapAvailable(_WaitNextEvent);

    where.h = 82;
    where.v = 90;
    for (;;) {
        SFReply reply;
        SFGetFile(where, "\p", NULL, -1, NULL, NULL, &reply);
        if (!reply.good) break;
        {
            /* SFReply.vRefNum is a working directory; extract there. */
            ExtractOne(reply.vRefNum, 0, reply.fName);
        }
    }
    return 0;
}
