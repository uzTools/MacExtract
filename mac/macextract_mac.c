/*
 * macextract_mac.c — minimal Macintosh Toolbox shell around
 * libmacextract. Compile-only target (M10): built with Retro68 for
 * plain 68000, floor System 6.0.x on a 1 MB Mac Plus; the same binary
 * runs unchanged through Mac OS 9.
 *
 * Design (see CLAUDE.md M10):
 *   - SFGetFile to pick an archive, then SFPutFile to pick where the
 *     output goes — opening in the archive's own folder, so Return
 *     means "beside it"; loop back to SFGetFile until Cancel.
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

#ifdef UNC_SINK_TEST
#include "mac_mocks.h"      /* Linux-backed Toolbox mocks (test build) */
#else
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
#endif

#include "macextract.h"

#define kProgressDLOG   128
#define kDoneALRT       129
#define kErrorALRT      130
#define kCancelItem     1
#define kStatusItem     2
#define kBarItem        3
#define kDetailItem     4

#define kStackBump      (24L * 1024)   /* extra stack over the 8 KB default */
/* Heap kept back from the engine for the Toolbox and File Manager.
 *
 * A QUARTER of what is free, between a 32 KB floor and the 80 KB this was
 * a flat constant of until 2026-08-24, because the two configurations this
 * application runs in are four and a half times apart and one constant
 * cannot suit both. On a 1 MB Mac Plus with the machine to itself
 * FreeMem() is ~681 KB and a quarter is over 80 KB, so the cap holds and
 * nothing changes there — every verified figure on that tier stays exactly
 * as measured. Under MultiFinder at the 400 KB minimum partition
 * `macextract.r` declares, FreeMem() is 212,056 B, and a flat 80 KB is
 * 38 % of the heap held back from a machine that has none to spare.
 *
 * What it is worth keeping back was measured rather than assumed: with a
 * probe recording the lowest FreeMem() seen during writes across all 67
 * fixtures of the 1 MB sample, the tightest moment left **121 KB** free,
 * and the Toolbox and File Manager together took **under 1 KB** while the
 * engine was at its peak. So even the floor is generous by that evidence.
 *
 * WHAT THAT EVIDENCE CANNOT SEE, and why the floor is 32 KB rather than
 * the kilobyte measured: a stripped System Folder with no INITs, a
 * RAM-backed emulated disk, and no fragmentation pressure. A real Plus
 * with a Chooser extension, a floppy's File Manager buffers or an
 * AppleShare volume all cost more, and the reserve also has to cover a
 * dialog or an alert drawn while the engine holds its peak. MANUAL_TESTS.md
 * carries this as something only real hardware can settle. */
#define kMemReserveMax  (80L * 1024)
#define kMemReserveMin  (32L * 1024)

#ifndef ioDirMask
#define ioDirMask 0x10   /* ioFlAttrib bit 4 = "is a directory"
                          * (Inside Macintosh: Files, CInfoPBRec) */
#endif

/* ------------------------------------------------------------------ */
/* Runtime environment checks                                         */
/* ------------------------------------------------------------------ */

#ifndef UNC_SINK_TEST
static Boolean gHasWNE;

static Boolean TrapAvailable(short trap)
{
    /* Multiversal names: kToolboxTrapType/kOSTrapType. */
    TrapType tt = (trap & 0x0800) ? kToolboxTrapType : kOSTrapType;
    return NGetTrapAddress((uint16_t)trap, tt) !=
           NGetTrapAddress(_Unimplemented, kToolboxTrapType);
}
#endif

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

static int mio_seek(void *ctx, unc_off_t pos)
{
    MacIO *io = (MacIO *)ctx;
    OSErr err = SetFPos(io->refNum, fsFromStart, (long)pos);
    /* SetFPos past EOF returns eofErr but still positions at EOF; a
     * following read then returns 0 and the engine treats it as
     * truncation. Treating eofErr as a hard error made valid seeks to
     * end-of-file fail with a spurious I/O error. */
    return (err == noErr || err == eofErr) ? 0 : -1;
}

static unc_off_t mio_tell(void *ctx)
{
    MacIO *io = (MacIO *)ctx;
    long pos = 0;
    GetFPos(io->refNum, &pos);
    return (uint32_t)pos;
}

static unc_off_t mio_size(void *ctx)
{
    MacIO *io = (MacIO *)ctx;
    return (uint32_t)io->size;
}

/* ------------------------------------------------------------------ */
/* UncIO over a RAM buffer                                            */
/*                                                                    */
/* The whole archive is slurped into RAM up front and decoded from    */
/* there. This is deliberate, not just an optimization: on a real Mac */
/* the extractor otherwise reads the input file while the sink is      */
/* creating output files on the SAME volume, and interleaving File     */
/* Manager reads with catalog-changing operations on one volume        */
/* corrupts the reader's file mark (the input reads start returning    */
/* zeros). Reading everything before any output file exists sidesteps  */
/* that entirely — and archives targeted here are small.               */
/* ------------------------------------------------------------------ */

typedef struct {
    const uint8_t *data;
    uint32_t       size;
    uint32_t       pos;
} MemIO;

static int32_t xio_read(void *ctx, void *buf, int32_t len)
{
    MemIO *m = (MemIO *)ctx;
    const uint8_t *src = m->data + m->pos;
    uint8_t *dst = (uint8_t *)buf;
    uint32_t avail = m->size - m->pos;
    uint32_t n = (len <= 0) ? 0
               : ((uint32_t)len < avail ? (uint32_t)len : avail);
    uint32_t i;
    for (i = 0; i < n; i++) dst[i] = src[i];
    m->pos += n;
    return (int32_t)n;
}
static int xio_seek(void *ctx, unc_off_t pos)
{
    MemIO *m = (MemIO *)ctx;
    m->pos = (pos > m->size) ? m->size : pos;   /* clamp, like SetFPos@EOF */
    return 0;
}
static unc_off_t xio_tell(void *ctx) { return ((MemIO *)ctx)->pos; }
static unc_off_t xio_size(void *ctx) { return ((MemIO *)ctx)->size; }

/* ------------------------------------------------------------------ */
/* UncIO straight off the input file — the default                     */
/*                                                                    */
/* The archive used to be slurped whole into a NewPtr block first, on  */
/* the grounds that reading the input while output files are created   */
/* on the same volume makes the reads return zeros. That claim came    */
/* from the confounded period (BLOCKERS.md) and does NOT reproduce:    */
/* UNC_AT_INTERLEAVE reads a 278 KB file three ways on one volume —    */
/* undisturbed, and twice more with 67 file creations interleaved,     */
/* sequentially and seeking before every read — and gets the same      */
/* CRC-32 every time, at 4 MB and at 1 MB. The bullet directly after   */
/* it in DECISIONS.md ("deep writes corrupt the volume") was already   */
/* withdrawn for the same reason.                                     */
/*                                                                    */
/* It matters on the floor target: the buffer was subtracted from the */
/* engine's budget before extraction began, so on a 1 MB Mac Plus a    */
/* 278 KB archive cost the engine 278 KB it could otherwise have used. */
/*                                                                    */
/* Every read positions explicitly with SetFPos rather than trusting   */
/* the file mark, which is the exact shape the reproduction exercised. */
/* Build with UNC_MAC_SLURP_ARCHIVE to get the old path back.          */
/* ------------------------------------------------------------------ */

typedef struct {
    short    refNum;
    uint32_t size;
    uint32_t pos;
} FileIO;

static int32_t fio_read(void *ctx, void *buf, int32_t len)
{
    FileIO *f = (FileIO *)ctx;
    uint32_t avail = f->size - f->pos;
    uint32_t n = (len <= 0) ? 0
               : ((uint32_t)len < avail ? (uint32_t)len : avail);
    long cnt;
    OSErr err;

    if (n == 0) return 0;
    if (SetFPos(f->refNum, fsFromStart, (long)f->pos) != noErr) return 0;
    cnt = (long)n;
    err = FSRead(f->refNum, &cnt, buf);
    if (cnt < 0) cnt = 0;
    f->pos += (uint32_t)cnt;
    /* eofErr with bytes delivered is a normal short read, not a failure. */
    if (err != noErr && err != eofErr) return (int32_t)cnt;
    return (int32_t)cnt;
}
static int fio_seek(void *ctx, unc_off_t pos)
{
    FileIO *f = (FileIO *)ctx;
    f->pos = (pos > f->size) ? f->size : pos;   /* clamp, like SetFPos@EOF */
    return 0;
}
static unc_off_t fio_tell(void *ctx) { return ((FileIO *)ctx)->pos; }
static unc_off_t fio_size(void *ctx) { return ((FileIO *)ctx)->size; }

/* ------------------------------------------------------------------ */
/* UncAlloc over NewPtr with a budget                                 */
/* ------------------------------------------------------------------ */
/* What a memory refusal COST, kept so the alert at the end can say it.
 *
 * "Out of memory" on its own leaves the user guessing at the Get Info box.
 * The allocator is the one place that knows the number, and it knows it at
 * the moment of refusal rather than by predicting anything — so this is
 * measured, not estimated, and cannot disagree with what actually happened.
 *
 * The two refusals have OPPOSITE fixes and are kept apart: over budget
 * means the partition is too small, and a NewPtr that fails while the
 * budget still had room means the heap has no piece big enough, which a
 * bigger partition may not cure and quitting something else will.
 *
 * NOT inside UNC_AT_BUDGET: that build is a diagnostic and these two are
 * the shipped message. */
static long gShortBy;      /* largest budget shortfall, in bytes; 0 = none */
static int  gShortPiece;   /* NewPtr failed though the budget allowed it   */
/* Entries whose METHOD this build cannot read, for the alert that asks
 * for the file rather than blaming the machine. Run-level like the two
 * above, and reset by RunExtract. */
static int  gUnsupported;

#ifdef UNC_AT_BUDGET
/* The result grid reports what the engine USED and never what it was
 * ALLOWED, so a budget refusal and a genuine shortage look identical on
 * screen. Worse, mal_alloc returns NULL for two unrelated reasons — the
 * budget said no, or NewPtr itself failed — and those have opposite
 * fixes ("the reserve is too big" vs "the heap is fragmented"). These
 * make both visible. See tools/vmac/README.md. */
static long gFreeAtStart;   /* FreeMem() before the reserve is taken off */
static long gBudget;        /* what the engine was actually given        */
static long gRefusedSize;   /* size of the FIRST refused allocation      */
static long gRefusedWhy;    /* 1 = over budget, 2 = NewPtr returned NULL */
static long gRefusedMaxBlk; /* MaxBlock() at that moment: contiguity vs total */
static long gRefusedFree;   /* FreeMem() at the SAME moment. FreeMem-MaxBlock
                             * is the fragmentation; without both, the gap has
                             * to be inferred from the start-of-run figure. */
static long gRefusedHeld;   /* bytes the engine held when it was refused */
/* Live-block table: the addresses are what a MaxBlock figure cannot give.
 * The heap is fragmented somewhere between the Arsenic block and the
 * transform request (OPEN_ITEMS.md section 5); knowing WHERE each live
 * block sits, against the zone's own bounds, says which one splits it. */
#define kLiveMax 8
static Ptr  gLiveAddr[kLiveMax];
static long gLiveSize[kLiveMax];
static int  gLiveN;
static Ptr  gSnapAddr[4];
static long gZoneLo, gZoneHi;

static void live_add(Ptr p, long n)
{
    if (gLiveN < kLiveMax) { gLiveAddr[gLiveN] = p; gLiveSize[gLiveN] = n;
                             gLiveN++; }
}

static void live_del(Ptr p)
{
    int i;
    for (i = 0; i < gLiveN; i++)
        if (gLiveAddr[i] == p) {
            gLiveN--;
            gLiveAddr[i] = gLiveAddr[gLiveN];
            gLiveSize[i] = gLiveSize[gLiveN];
            return;
        }
}

/* Snapshot the four LARGEST live blocks, biggest first — the small ones
 * cannot account for a 125 KB split. */
static void live_snapshot(void)
{
    int i, k;
    long best;
    int taken[kLiveMax], bi;
    for (i = 0; i < gLiveN; i++) taken[i] = 0;
    for (k = 0; k < 4; k++) {
        best = -1; bi = -1;
        for (i = 0; i < gLiveN; i++)
            if (!taken[i] && gLiveSize[i] > best) { best = gLiveSize[i]; bi = i; }
        if (bi < 0) break;
        taken[bi] = 1;
        gSnapAddr[k] = gLiveAddr[bi];
    }
    gZoneLo = (long)(Ptr)ApplicationZone();
    gZoneHi = (long)LMGetApplLimit();
}

#ifdef UNC_AT_HANDLES
/* Does MoveHHi move anything at all here? Measured around the call for the
 * first allocation big enough to matter, in the real heap state rather than
 * a synthetic one. Equal values mean MoveHHi is a no-op and the reverted
 * relocatable-blocks remedy never had a chance. */
static long gMoveBefore, gMoveAfter;   /* the block's ADDRESS, not MaxBlock:
                                        * MaxBlock is blind to where in a
                                        * free run a block sits, so it can
                                        * never fail. See tools/vmac/README.md. */
#endif
#endif
/* ------------------------------------------------------------------ */

typedef struct {
    long budget;    /* remaining bytes the engine may hold */
    long initial;   /* starting budget (set at init) */
    long lowmark;   /* lowest budget ever seen => peak = initial - lowmark */
} MacAlloc;

static void *mal_alloc(void *ctx, uint32_t size)
{
    MacAlloc *a = (MacAlloc *)ctx;
    Ptr p;
    if ((long)size + 16 > a->budget) {
        /* How much more the budget would have had to be, at this moment.
         * The engine already holds initial - budget, so this is exactly
         * what the application's memory size is short by. Keep the
         * LARGEST: it is the one that has to be covered. */
        long shortby = (long)size + 16 - a->budget;
        if (shortby > gShortBy) gShortBy = shortby;
#ifdef UNC_AT_BUDGET
        if (gRefusedWhy == 0) { gRefusedSize = (long)size; gRefusedWhy = 1; }
#endif
        return NULL;
    }
#ifdef UNC_AT_HANDLES
    {
        Handle h = NewHandle((long)size + 16);
        p = NULL;
        if (h != NULL) {
            if (gMoveBefore == 0 && size >= 65536L) gMoveBefore = (long)*h;
            MoveHHi(h);
            if (gMoveAfter == 0 && size >= 65536L) gMoveAfter = (long)*h;
            HLock(h);
            p = *h;
            *(Handle *)(p + 8) = h;
        }
    }
#else
    p = NewPtr((long)size + 16);
#endif
    if (p == NULL) {
        gShortPiece = 1;
#ifdef UNC_AT_BUDGET
        if (gRefusedWhy == 0) { gRefusedSize = (long)size; gRefusedWhy = 2;
                                gRefusedMaxBlk = MaxBlock();
                                gRefusedFree = FreeMem();
                                gRefusedHeld = a->initial - a->budget;
                                live_snapshot(); }
#endif
        return NULL;
    }
    *(long *)p = (long)size;
    a->budget -= (long)size + 16;
    if (a->budget < a->lowmark) a->lowmark = a->budget;  /* track peak usage */
#ifdef UNC_AT_BUDGET
    live_add(p, (long)size);
#endif
    return p + 16;
}

static void mal_free(void *ctx, void *ptr)
{
    MacAlloc *a = (MacAlloc *)ctx;
    Ptr p = (Ptr)ptr - 16;
    a->budget += *(long *)p + 16;
#ifdef UNC_AT_BUDGET
    live_del(p);
#endif
#ifdef UNC_AT_HANDLES
    { Handle h = *(Handle *)(p + 8); HUnlock(h); DisposeHandle(h); }
#else
    DisposePtr(p);
#endif
}

/* ------------------------------------------------------------------ */
/* Progress dialog                                                    */
/* ------------------------------------------------------------------ */

typedef struct {
    DialogPtr dlg;
    Boolean   cancelled;
    long      lastTicks;    /* TickCount of the last pump, for the 10 Hz gate */
    long      startTicks;   /* TickCount when extraction began, for the ETA */
    short     shownPct;     /* what the bar and the text currently say, so an */
    long      shownRem;     /* unchanged reading costs no redraw and no flicker */
} Progress;

#ifndef UNC_SINK_TEST
/* ---- progress bar -------------------------------------------------
 * The bar is a DITL userItem. The Dialog Manager will not draw it, so
 * BarUserItem is installed as its draw proc: that is what repaints it on
 * an update event, and prog_tick calls BarDraw directly in between. The
 * percentage lives in a file static because a userItem proc is handed
 * nothing but the dialog and the item number. (The no-global-state rule
 * is an ENGINE rule; the shell already keeps gHasWNE and friends.) */
static short gBarPct = 0;

static void BarDraw(const Rect *box)
{
    Rect r = *box, fill;
    short w;

    PenNormal();
    FrameRect(&r);
    r.left++; r.top++; r.right--; r.bottom--;   /* inside the frame */
    w = (short)((long)(r.right - r.left) * gBarPct / 100);
    fill = r;
    fill.right = (short)(r.left + w);
    if (fill.right > fill.left) PaintRect(&fill);
    fill.left = fill.right;
    fill.right = r.right;
    if (fill.right > fill.left) EraseRect(&fill);
}

static pascal void BarUserItem(WindowPtr w, short item)
{
    short kind;
    Handle h;
    Rect box;
    GetDialogItem((DialogPtr)w, item, &kind, &h, &box);
    BarDraw(&box);
}

/* Pascal-string builders. NumToString is the only number formatter the
 * Toolbox offers and it writes a whole Str255, so appending needs these. */
static void PStrCat(Str255 d, const char *s)
{
    while (*s && d[0] < 255) d[++d[0]] = (unsigned char)*s++;
}

static void PStrCatNum(Str255 d, long n)
{
    Str255 t;
    short i;
    NumToString(n, t);
    for (i = 1; i <= (short)t[0] && d[0] < 255; i++) d[++d[0]] = t[i];
}

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
    short pct;
    long elapsed, rem;
    Handle h;
    short kind;
    Rect box;

    if (now - pr->lastTicks < 6) return pr->cancelled ? 0 : 1;   /* ~10 Hz */
    pr->lastTicks = now;
    ProgressPump(pr);
    if (pr->cancelled) return 0;
    if (total == UNC_SIZE_UNKNOWN || total == 0 || !pr->dlg)
        return 1;

    /* /128 first: done*100 overflows a 32-bit long past 42 MB, and this
     * runs on a 68000 where 64-bit division is a library call. */
    pct = (short)((done / 128) * 100 / (total / 128 + 1));
    if (pct > 100) pct = 100;
    if (pct < 0) pct = 0;

    /* Time left, in whole seconds, from the rate so far. Held back for the
     * first two seconds and below 1%, where the estimate is meaningless and
     * would show a wild number that then collapses. -1 means "no estimate".
     * elapsed*(100-pct) is at most 216,000*100, which fits. */
    elapsed = now - pr->startTicks;
    rem = -1;
    if (pct > 0 && elapsed > 120) rem = elapsed * (100 - pct) / pct / 60;

    /* Redraw nothing if the reading has not changed: SetDialogItemText
     * redraws the item, and at 10 Hz that flickers. */
    if (pct == pr->shownPct && rem == pr->shownRem) return 1;
    pr->shownPct = pct;
    pr->shownRem = rem;

    gBarPct = pct;
    GetDialogItem(pr->dlg, kBarItem, &kind, &h, &box);
    BarDraw(&box);

    {
        Str255 s;
        s[0] = 0;
        PStrCatNum(s, pct);
        PStrCat(s, "%");
        if (rem < 0) {
            PStrCat(s, "   estimating time left");
        } else if (rem < 60) {
            PStrCat(s, "   about ");
            PStrCatNum(s, rem < 5 ? 5 : rem);
            PStrCat(s, " seconds left");
        } else {
            long mins = (rem + 30) / 60;
            PStrCat(s, "   about ");
            PStrCatNum(s, mins);
            PStrCat(s, mins == 1 ? " minute left" : " minutes left");
        }
        GetDialogItem(pr->dlg, kDetailItem, &kind, &h, &box);
        if (h) SetDialogItemText(h, s);
    }
    return 1;
}
#endif

#ifdef UNC_MAC_AUTOTEST
/* Autotest-only: the sink records each extracted file (folder id + leaf
 * name) so main() can CRC its forks back through the File Manager after
 * extraction. */
#define AT_MAXREC 128
static struct { long dir; Str63 name; } gATrec[AT_MAXREC];
static int   gATnrec;
static short gATrecVol;   /* main sets this; sink records only for it */
static void unc_at_record(short vol, long dir, ConstStr255Param name)
{
    int i;
    if (vol != gATrecVol || gATnrec >= AT_MAXREC) return;
    gATrec[gATnrec].dir = dir;
    for (i = 0; i <= name[0]; i++) gATrec[gATnrec].name[i] = name[i];
    gATnrec++;
}
#endif

/* ------------------------------------------------------------------ */
/* Disk sink: HFS files, both forks, then catalog info                */
/* ------------------------------------------------------------------ */

typedef struct {
    short        vRefNum;      /* destination volume */
    long         rootDirID;    /* destination folder */
    long         curDirID;     /* directory of the current entry */
    Str63        curName;      /* sanitized current file name */
    UncEntryInfo cur;
    int          entries, errors, unsupported;
    /* The shape of what was written, for the envelope unwrap in
     * ExtractOne: one file and no folders is what an envelope layer
     * looks like, and lastName/lastDir say where it landed. */
    int          fileCount, dirCount;
    Str63        lastName;
    long         lastDir;
    Progress    *pr;
#ifndef UNC_MAC_STAGE_WRITES
    /* Streaming write path: each chunk goes straight to disk as the engine
     * delivers it, so the shell never holds a whole fork in RAM. Exactly one
     * fork is open at a time; switching forks closes and flushes the open one
     * first, and the byte position of each is remembered so a fork can be
     * reopened if the engine comes back to it. */
    short        openRef;            /* refNum of the open fork, 0 if none  */
    int          openIsRsrc;         /* which fork openRef refers to        */
    uint32_t     dataPos, rsrcPos;   /* bytes written to each fork so far   */
    int          dataSized, rsrcSized; /* SetEOF already done for this fork */
    int          wrErr;              /* a write failed; fail the entry      */
    OSErr        wrOSErr;            /* the FIRST write error of this entry */
#else
    /* Staging write path: forks are accumulated in RAM and written in
     * sink_end at shallow depth. Costs the shell one whole fork of RAM,
     * which is what bounds the file size a 1 MB machine can extract. */
    Ptr          dataBuf, rsrcBuf;   /* whole-fork RAM staging */
    uint32_t     dataLen, dataCap, rsrcLen, rsrcCap;
    int          bufErr;
    int          dropData, dropRsrc; /* fork dropped (unknown-size fallback) */
    int          sharedBuf;          /* dataBuf+rsrcBuf are ONE NewPtr block */
#endif
} MacSink;

/* ------------------------------------------------------------------ */
/* The run report                                                     */
/*                                                                    */
/* What the user is told at the end of a run, above the one-line      */
/* outcome: every name this shell had to change, and every entry that */
/* failed without stopping the archive. Both are collected AS THEY    */
/* HAPPEN, because neither can be recovered afterwards — the engine's */
/* name for an entry is gone by the time the walk moves on, and a     */
/* failed entry's file has been deleted by then.                      */
/*                                                                    */
/* Names go in WHOLE. The list exists to say which file became which, */
/* and eighteen photographs whose names differ at character 34 are    */
/* one line repeated eighteen times if the names are cut to fit a     */
/* row (2026-08-29). So the text is packed end to end in one pool     */
/* and the box wraps it; what a line costs is what its names are,     */
/* not a per-line ceiling every short line pays for.                  */
/*                                                                    */
/* A fixed pool rather than the heap: the engine's budget is derived  */
/* from FreeMem() once, at the start of the run, so anything          */
/* allocated during it is taken out of the reserve the Toolbox and    */
/* File Manager are holding. When either the lines or the bytes run   */
/* out the rest are COUNTED and the count is shown, so the report     */
/* never presents itself as complete when it is not.                  */
/* ------------------------------------------------------------------ */

#define kRepMax    64          /* lines */
#define kRepPool   6144        /* bytes of text, packed end to end */
/* The last lines and the last bytes are FAILURES' to take. An archive
 * with more long names than the pool holds is ordinary — the crowd of
 * renames would otherwise fill it and push out the one line the user
 * has to act on, which is what happened the first time this ran against
 * 100 alike names. */
#define kRepKeep   16          /* lines held back */
#define kRepKeepB  1024        /* bytes held back */

static unsigned char gRepBuf[kRepPool];
static short gRepStart[kRepMax];    /* first byte of line i, in gRepBuf */
static short gRepLen[kRepMax];
/* Where the line would rather be broken if it has to be: after the
 * archive's own name, so a wrapped line reads as the name on one row
 * and what became of it on the next. 0 = anywhere. */
static short gRepBreak[kRepMax];
static short gRepN;                 /* lines kept */
static short gRepUsed;              /* bytes of the pool in use */
static short gRepCur;               /* the line being appended to, or -1 */
static long  gRepMore;              /* lines there was no room for */

/* Folders this run created, so a folder that turns up ALREADY there can
 * be told from one this walk made a moment ago. Only the archive's own
 * name is remembered, and only its first 63 bytes: two names that agree
 * that far shorten alike, so they would be indistinguishable on disk
 * anyway. */
#define kDirMemo 24

static struct { long dir; unsigned char name[64]; } gDirMemo[kDirMemo];
static short gDirMemoN;

static void RepReset(void)
{
    gRepN = 0;
    gRepUsed = 0;
    gRepCur = -1;
    gRepMore = 0;
    gDirMemoN = 0;
}

/* Start a line. `urgent` is a failure, which may take from the reserve. */
static int RepNew(int urgent)
{
    gRepCur = -1;
    if (gRepN >= (urgent ? kRepMax : kRepMax - kRepKeep) ||
        gRepUsed >= (urgent ? kRepPool - 16 : kRepPool - kRepKeepB)) {
        gRepMore++;
        return 0;
    }
    gRepStart[gRepN] = gRepUsed;
    gRepLen[gRepN] = 0;
    gRepBreak[gRepN] = 0;
    gRepCur = gRepN++;
    return 1;
}

static void RepPut(unsigned char c)
{
    if (gRepCur < 0 || gRepUsed >= kRepPool) return;
    gRepBuf[gRepUsed++] = c;
    gRepLen[gRepCur]++;
}

static void RepCat(const char *s)
{
    while (*s) RepPut((unsigned char)*s++);
}

/* A Pascal name, whole. */
static void RepCatP(const unsigned char *p)
{
    short i;
    for (i = 1; i <= (short)p[0]; i++) RepPut(p[i]);
}

/* Raw engine bytes: one path component, MacRoman, with the engine's
 * reversible '/'->':' swap undone so the line shows the name the archive
 * meant rather than the one the engine carries. */
/* Mark the end of the name: where this line prefers to wrap. */
static void RepMarkBreak(void)
{
    if (gRepCur >= 0) gRepBreak[gRepCur] = gRepLen[gRepCur];
}

static void RepCatBytes(const uint8_t *b, int len)
{
    int i;
    if (len == 0) {                  /* an entry the archive did not name */
        RepCat("An unnamed entry");
        return;
    }
    for (i = 0; i < len; i++) RepPut(b[i] == ':' ? '/' : b[i]);
}

/* "<archive's name> renamed to <what is on the disk>" — the line this
 * whole report exists for. `what` prefixes it for a folder. */
static void RepRenamed(const char *what, const uint8_t *orig, int olen,
                       const unsigned char *now, const char *verb)
{
    if (!RepNew(0)) return;
    RepCat(what);
    RepCatBytes(orig, olen);
    RepMarkBreak();
    RepCat(verb);
    RepCatP(now);
}

static void RepDirMemo(long dir, const uint8_t *orig, int olen)
{
    short i, n = (short)olen;
    if (gDirMemoN >= kDirMemo) return;      /* full: it says nothing, ever */
    if (n > 63) n = 63;
    gDirMemo[gDirMemoN].dir = dir;
    gDirMemo[gDirMemoN].name[0] = (unsigned char)n;
    for (i = 0; i < n; i++)
        gDirMemo[gDirMemoN].name[i + 1] = orig[i] == ':' ? '/' : orig[i];
    gDirMemoN++;
}

/* Did this run create `dir` for a DIFFERENT archive name than this one?
 * That — and only that — is a merge: two folders whose names shorten
 * alike become one, and everything they hold ends up together.
 *
 * WHAT THIS CANNOT SEE: a folder that no entry of its own declares.
 * Where a format carries no directory entries the folders are made
 * along the way by the paths of the files in them, and two such folders
 * merging is indistinguishable from one folder visited twice. */
static int RepDirMerged(long dir, const uint8_t *orig, int olen)
{
    short i, j, n = (short)olen;
    if (n > 63) n = 63;
    for (i = 0; i < gDirMemoN; i++) {
        if (gDirMemo[i].dir != dir) continue;
        if ((short)gDirMemo[i].name[0] != n) return 1;
        for (j = 0; j < n; j++) {
            unsigned char c = orig[j] == ':' ? '/' : orig[j];
            if (gDirMemo[i].name[j + 1] != c) return 1;
        }
        return 0;                            /* the same folder again */
    }
    return 0;                                /* not ours: say nothing */
}

/* An entry that failed on its own without stopping the archive, named
 * as the ARCHIVE names it — the file this shell would have written is
 * not on the disk to be looked for, because a failed entry's partial
 * output is deleted. */
static void RepEntryFailed(const uint8_t *orig, int olen, const char *why)
{
    if (!RepNew(1)) return;
    RepCatBytes(orig, olen);
    RepMarkBreak();
    RepCat(why);
}

/* The same, for the failure the engine reports once the entry has been
 * accepted. The reason is what the user can act on, so each says what is
 * wrong rather than naming the error. */
static void RepFailed(const uint8_t *orig, int olen, int status)
{
    if (!RepNew(1)) return;
    RepCatBytes(orig, olen);
    RepMarkBreak();
    switch (status) {
    case UNC_ERR_TOOLARGE:
        RepCat(" is too large for this version and was not extracted");
        break;
    case UNC_ERR_MEM:
        RepCat(" needs more memory than was free");
        break;
    case UNC_ERR_UNSUPPORTED:
        RepCat(" uses a method this version cannot read");
        break;
    case UNC_ERR_CRC:
        RepCat(" is damaged: its checksum does not match");
        break;
    case UNC_ERR_TRUNCATED:
        RepCat(" ends early: the archive is incomplete");
        break;
    case UNC_ERR_ENCRYPTED:
    case UNC_ERR_PASSWORD:
        RepCat(" is encrypted and was skipped");
        break;
    case UNC_ERR_SINK:
        RepCat(" could not be written to the disk");
        break;
    case UNC_ERR_IO:
        RepCat(" could not be read from the archive");
        break;
    default:
        RepCat(" could not be extracted");
        break;
    }
}

/* The last '.' of a name, when what follows it is a 1..4 character
 * alphanumeric extension: its offset, or -1 for a name that has none. */
static int ExtStart(const unsigned char *b, int len)
{
    int i, j, tail;
    for (i = len - 1; i > 0; i--) {
        if (b[i] != '.') continue;
        tail = len - i - 1;
        if (tail < 1 || tail > 4) return -1;
        for (j = i + 1; j < len; j++) {
            unsigned char c = b[j];
            if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') ||
                  (c >= 'a' && c <= 'z')))
                return -1;
        }
        return i;
    }
    return -1;
}

/* One engine path component -> Pascal Str63: undo the '/'->':' swap,
 * strip any stray ':' (illegal in an HFS name), fit it into 31 chars.
 *
 * THE EXTENSION IS KEPT and the stem is what gets cut, so
 * `LongDocumentName.txt` becomes `LongDocumen.txt` and never
 * `LongDocumentName.tx`. A Macintosh file is opened by the type and
 * creator sink_end stamps on it — but a file that arrived WITH a suffix
 * generally came off a machine that has neither, and carries no fork
 * and no Finder types for this shell to stamp, so the suffix is the
 * only thing that says what opens it (2026-08-29, at the maintainer's
 * ask; it was the first thing cut for a few hours, which was backwards).
 *
 * Returns nonzero when the result is NOT the archive's own name, which
 * is what puts a line in the report. */
static int ComponentToStr63(const uint8_t *comp, int len, Str63 out)
{
    int i, o = 0, stem = len, ext = -1;

    if (len > 31) {
        ext = ExtStart(comp, len);
        /* 31 minus the suffix has to leave a stem to cut down to. */
        if (ext > 0 && 31 - (len - ext) >= 1) stem = 31 - (len - ext);
        else ext = -1;
    }
    for (i = 0; i < stem && o < 31; i++) {
        unsigned char b = comp[i];
        if (b == ':') b = '/';           /* reversible swap undone */
        out[++o] = b;
    }
    if (ext > 0)
        for (i = ext; i < len && o < 31; i++) {
            unsigned char b = comp[i];
            if (b == ':') b = '/';
            out[++o] = b;
        }
    if (o == 0) out[++o] = '_';
    out[0] = (unsigned char)o;
    return o != len;
}

/* Insert a collision suffix "~1".."~99" BEFORE the extension, within 31
 * chars: `bababibibo.txt` numbers to `bababibibo~1.txt`, and a name with
 * no room left for the whole stem loses stem rather than suffix. The
 * extension survives here for the same reason it survives the cut above.
 *
 * TWO digits since 2026-08-29, because one is not enough: names that are
 * alike for 31 characters differ after it, and an archive holding
 * eighteen photographs called "Photograph Of The Summer Of 1994 noNN"
 * ran out at "~9" — measured on a Mac Plus, where it then took the whole
 * extraction down with it (BLOCKERS.md). */
static void BumpName(Str63 name, int attempt)
{
    Str63 tmp;
    int len = name[0];
    int ext = ExtStart(name + 1, len);
    int extlen = ext > 0 ? len - ext : 0;
    int sufflen = attempt > 9 ? 3 : 2;
    int stem = ext > 0 ? ext : len;
    int o = 0, i;

    if (31 - extlen - sufflen < 1) { extlen = 0; ext = -1; }  /* no room */
    if (stem > 31 - extlen - sufflen) stem = 31 - extlen - sufflen;
    for (i = 0; i < stem; i++) tmp[++o] = name[i + 1];
    tmp[++o] = '~';
    if (sufflen == 3) tmp[++o] = (unsigned char)('0' + attempt / 10);
    tmp[++o] = (unsigned char)('0' + attempt % 10);
    for (i = 0; i < extlen; i++) tmp[++o] = name[ext + i + 1];
    tmp[0] = (unsigned char)o;
    BlockMoveData(tmp, name, o + 1);
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

/* Create (or descend into) one directory level. `*isNew` says which of
 * the two happened, which is how a folder MERGED into one that is
 * already there is told from one this walk just made. */
static OSErr EnsureDir(short vRefNum, long parent, Str63 name, long *dirID,
                       int *isNew)
{
    long created;
    OSErr err = MyDirCreate(vRefNum, parent, name, &created);
    *isNew = 0;
    if (err == noErr) {
        *dirID = created;
        *isNew = 1;
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

/* ------------------------------------------------------------------ */
/* File Manager via explicit HFS param blocks                         */
/* ------------------------------------------------------------------ */
/* Drive the traps through param blocks we fill in ourselves, zeroing the whole
 * block first. This is what made the Mac shell work at all, after a long
 * period in which every open silently failed.
 *
 * It was attributed to Retro68's high-level HOpen/HOpenRF glue ("returns noErr
 * but never writes back the refNum on System 6"). That attribution is
 * WITHDRAWN: tools/retro68-hopen-repro/ tests exactly that against a
 * hand-filled PBHOpenSync on the same setup and they agree in all ten cases.
 * The honest statement is that zeroing the whole param block fixed it and we
 * do not know which field mattered; the one real glue finding that survives is
 * that HOpenDF returns paramErr on System 6 (PBHOpenDFSync issues a System 7
 * trap with no fallback), which is why nothing here calls it.
 *
 * Field layout: Multiversal CIncludes HParamBlockRec. */
static OSErr MyOpenFork(short vol, long dir, ConstStr255Param name,
                        SignedByte perm, int rsrc, short *refOut)
{
    HParamBlockRec pb;
    long z;
    OSErr err;
    *refOut = 0;
    for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
    pb.ioParam.ioNamePtr = (StringPtr)name;
    pb.ioParam.ioVRefNum = vol;
    pb.ioParam.ioPermssn = perm;
    pb.fileParam.ioDirID = dir;
    err = rsrc ? PBHOpenRFSync(&pb) : PBHOpenSync(&pb);
    *refOut = pb.ioParam.ioRefNum;
    return err;
}

/* Create a file (type/creator are stamped later by sink_end). */
static OSErr MyHCreate(short vol, long dir, ConstStr255Param name)
{
    HParamBlockRec pb;
    long z;
    for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
    pb.ioParam.ioNamePtr = (StringPtr)name;
    pb.ioParam.ioVRefNum = vol;
    pb.fileParam.ioDirID = dir;
    return PBHCreateSync(&pb);
}

/* Delete a file — used to remove the partial output of an entry that was
 * cancelled or failed (the file was created in sink_begin before decoding). */
static OSErr MyHDelete(short vol, long dir, ConstStr255Param name)
{
    HParamBlockRec pb;
    long z;
    for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
    pb.ioParam.ioNamePtr = (StringPtr)name;
    pb.ioParam.ioVRefNum = vol;
    pb.fileParam.ioDirID = dir;
    return PBHDeleteSync(&pb);
}

static int sink_begin(void *ctx, const UncEntryInfo *info)
{
    MacSink *s = (MacSink *)ctx;
    long dir = s->rootDirID;
    int start = 0, i, attempt;
    int leafStart = 0, leafLen = 0, leafChanged = 0;
    OSErr err;

    s->cur = *info;
    s->entries++;
#ifndef UNC_MAC_STAGE_WRITES
    s->openRef = 0;
    s->openIsRsrc = 0;
    s->dataPos = s->rsrcPos = 0;
    s->dataSized = s->rsrcSized = 0;
    s->wrErr = 0;
#else
    s->dataBuf = s->rsrcBuf = NULL;
    s->dataLen = s->dataCap = s->rsrcLen = s->rsrcCap = 0;
    s->bufErr = 0;
#endif

    /* Walk the '/'-separated engine path, creating directories. */
    for (i = 0; i <= info->name_len; i++) {
        if (i == info->name_len || info->name[i] == '/') {
            Str63 comp;
            int changed = ComponentToStr63(info->name + start, i - start, comp);
            if (i == info->name_len && !info->is_dir) {
                BlockMoveData(comp, s->curName, comp[0] + 1);
                s->curDirID = dir;
                leafStart = start;
                leafLen = i - start;
                leafChanged = changed;
            } else {
                int isNew = 0;
                OSErr derr = EnsureDir(s->vRefNum, dir, comp, &dir, &isNew);
                if (derr != noErr) {
                    if (derr == dskFulErr) return -1;   /* the run is over */
                    RepEntryFailed(info->name + start, i - start,
                                   " could not be made on the disk");
                    s->errors++;
                    return 1;                           /* this entry only */
                }
                /* A folder is reported once, where it is made: at the
                 * moment of creation for a name that had to change, and
                 * — for a folder the archive declares as an entry of its
                 * own — where the name it shortened to was already
                 * taken by another folder of this same run. */
                if (isNew) {
                    if (changed)
                        RepRenamed("Folder ", info->name + start, i - start,
                                   comp, " renamed to ");
                    RepDirMemo(dir, info->name + start, i - start);
                } else if (changed && info->is_dir && i == info->name_len &&
                           RepDirMerged(dir, info->name + start, i - start)) {
                    RepRenamed("Folder ", info->name + start, i - start,
                               comp, " combined with ");
                }
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
            err = MyHCreate(s->vRefNum, s->curDirID, s->curName);
            if (err == noErr) break;
            if (err == dskFulErr) return -1;     /* nothing else will fit */
            if (err != dupFNErr || attempt >= 99) {
                /* One entry's name, not the archive's run: until
                 * 2026-08-29 this returned -1, which the engine reads as
                 * "abort", so the eleventh file whose name shortened
                 * alike ended the extraction and everything after it was
                 * never written (BLOCKERS.md). */
                RepEntryFailed(info->name + leafStart, leafLen,
                               err == dupFNErr
                               ? " could not be given a name of its own"
                               : " could not be created on the disk");
                s->errors++;
                return 1;
            }
            BlockMoveData(base, s->curName, base[0] + 1);
            BumpName(s->curName, attempt + 1);
            leafChanged = 1;
        }
    }

    /* The line the user reads at the end. `name_truncated` is the
     * ENGINE's own cut — a path that summed past its 255-byte cap — and
     * it is reported even where this shell then left the leaf alone,
     * because the file is not where the archive said it was. */
    if (leafChanged)
        RepRenamed("", info->name + leafStart, leafLen, s->curName,
                   " renamed to ");
    else if (info->name_truncated && RepNew(0)) {
        RepCatP(s->curName);
        RepCat(" is in a folder whose path had to be shortened");
    }
#ifndef UNC_MAC_STAGE_WRITES
    return 0;                        /* nothing to pre-allocate: we stream */
#else
    s->dropData = s->dropRsrc = 0;
    s->sharedBuf = 0;
    {
        int dgood = (info->data_size != UNC_SIZE_UNKNOWN && info->data_size);
        int rgood = (info->rsrc_size != UNC_SIZE_UNKNOWN && info->rsrc_size);
        /* The single-shared-block path is the real Mac path; UNC_SINK_TEST
         * normally uses per-fork blocks, but UNC_MAC_FORCE_SHAREBUF forces
         * the shared path so the mock can prove it byte-exact too. */
#if (!defined(UNC_SINK_TEST) || defined(UNC_MAC_FORCE_SHAREBUF)) && !defined(UNC_AT_SEPARATE_BLOCKS)
        /* Stage both forks of one file in ONE contiguous block (data region
         * then resource region). This is retained as marginally more
         * heap-friendly (one fewer non-relocatable block beside the archive
         * buffer), NOT because separate blocks fail: the old belief that two
         * separate NewPtr staging blocks bomb System 6's Memory Manager was a
         * confound of the period when every open silently failed (see
         * BLOCKERS.md). With that fixed, UNC_AT_SEPARATE_BLOCKS forces two
         * separate blocks and a two-fork file still extracts byte-exact on a
         * real Mac. Mock/Linux builds use per-fork blocks. */
        if (dgood && rgood) {
            long total = (long)info->data_size + (long)info->rsrc_size;
            Ptr block = NewPtr(total);
            if (!block) return -1;
            s->dataBuf = block;
            s->dataCap = info->data_size;
            s->rsrcBuf = block + info->data_size;
            s->rsrcCap = info->rsrc_size;
            s->sharedBuf = 1;
            return 0;
        }
        if (dgood && info->rsrc_size == UNC_SIZE_UNKNOWN) s->dropRsrc = 1;
        if (rgood && info->data_size == UNC_SIZE_UNKNOWN) s->dropData = 1;
#endif
        /* Pre-size each fork's staging buffer to its known size (avoids
         * grow-and-copy during decode). Failure fails the entry cleanly. */
        if (dgood && !s->dropData) {
            s->dataBuf = NewPtr((long)info->data_size);
            if (!s->dataBuf) return -1;
            s->dataCap = info->data_size;
        }
        if (rgood && !s->dropRsrc) {
            s->rsrcBuf = NewPtr((long)info->rsrc_size);
            if (!s->rsrcBuf) return -1;
            s->rsrcCap = info->rsrc_size;
        }
    }
    return 0;
#endif  /* !UNC_MAC_STAGE_WRITES */
}

/* Trap-free byte copy for the deep decode-callback depth. */
static void ByteCopy(const uint8_t *src, uint8_t *dst, uint32_t n)
{
    while (n--) *dst++ = *src++;
}

#ifndef UNC_MAC_STAGE_WRITES

/* Close the fork currently open, if any, and commit it. */
static OSErr StreamClose(MacSink *s)
{
    OSErr err = noErr;
    if (s->openRef) {
        err = FSClose(s->openRef);
        s->openRef = 0;
        FlushVol(NULL, s->vRefNum);   /* commit before anything else opens */
    }
    return err;
}

/* Make <fork> the open one, positioned where its last write left off.
 *
 * Only one fork is ever open at a time. That is deliberate rather than
 * incidental: it keeps the File Manager's per-file state simple and matches
 * the way the staging path wrote its forks, one after the other. Remembering
 * each fork's position means the engine may interleave forks freely — the
 * fork is simply reopened and repositioned.
 *
 * Deep File Manager writes are safe here for a specific reason: the whole
 * archive has already been slurped into RAM (see the MemIO comment above),
 * so no File Manager READ is ever interleaved with these writes on the same
 * volume. Verified on a real 68000 Mac Plus under System 6.0.8 — the
 * 44-fixture sample is byte-exact at 4 MB and only the Arsenic
 * memory-budget refusals fail at 1 MB (tools/vmac/run.py). */
static OSErr StreamSelect(MacSink *s, int isRsrc)
{
    OSErr err;
    uint32_t pos;
    if (s->openRef && s->openIsRsrc == isRsrc) return noErr;
    err = StreamClose(s);
    if (err != noErr) return err;
    err = MyOpenFork(s->vRefNum, s->curDirID, s->curName, fsWrPerm,
                     isRsrc, &s->openRef);
    if (err != noErr) { s->openRef = 0; return err; }
    s->openIsRsrc = isRsrc;

    /* Ask for the whole fork at once, the first time it is opened.
     *
     * Two things fall out of one call. HFS allocates the extent (or as few
     * as the volume's fragmentation allows) ONCE, instead of extending the
     * fork and rewriting the extent record every 8 KB — this is a streaming
     * writer, so without it a 300 KB fork is 37 separate extensions.
     *
     * And a volume that cannot hold the fork says so HERE, before the entry
     * is decoded, rather than at some FSWrite twenty minutes in. That is the
     * difference between "this entry will not fit" and a hundred identical
     * unexplained failures, one per remaining entry.
     *
     * Only when the size is known: UNC_SIZE_UNKNOWN is a real case (a
     * streamed gzip has no length until it ends), and those forks keep the
     * old grow-as-you-go behaviour. sink_end trims back to what was actually
     * written, so a short or failed entry leaves exactly the file it left
     * before. */
    {
        int *sized = isRsrc ? &s->rsrcSized : &s->dataSized;
        uint32_t want = isRsrc ? s->cur.rsrc_size : s->cur.data_size;
        if (!*sized) {
            *sized = 1;
            if (want != UNC_SIZE_UNKNOWN && want > 0) {
                err = SetEOF(s->openRef, (long)want);
                if (err != noErr) return err;   /* dskFulErr lands here */
            }
        }
    }

    pos = isRsrc ? s->rsrcPos : s->dataPos;
    return SetFPos(s->openRef, fsFromStart, (long)pos);
}

/* The first write error of the RUN, not of the entry.
 *
 * Every extractor treats a sink failure as the end of the archive, so a
 * full destination volume already stops the run — what was missing is
 * that the OSErr was dropped at the `!= noErr` test, leaving "the disk is
 * full" indistinguishable from a media error. This carries it out to the
 * alert. File-scope because the sink is local to RunExtract and the alert
 * is in ExtractOne, and threading an out-parameter through five call
 * sites to move one OSErr is the worse trade. */
static OSErr gLastWriteErr = noErr;

/* Trim a fork back to what was actually written.
 *
 * StreamSelect asks for the whole declared size at first open. A correct
 * archive then delivers exactly that, and this does nothing; a damaged one
 * can deliver less, and without this the file would keep the difference as
 * whatever HFS left in the blocks it had just allocated. Only reopens when
 * there is something to trim, which on the 67-fixture sample is never. */
static void StreamTrim(MacSink *s, int isRsrc)
{
    short ref;
    uint32_t pos  = isRsrc ? s->rsrcPos : s->dataPos;
    uint32_t want = isRsrc ? s->cur.rsrc_size : s->cur.data_size;
    int sized     = isRsrc ? s->rsrcSized : s->dataSized;

    if (!sized || want == UNC_SIZE_UNKNOWN || pos >= want) return;
    if (MyOpenFork(s->vRefNum, s->curDirID, s->curName, fsWrPerm,
                   isRsrc, &ref) != noErr) return;
    (void)SetEOF(ref, (long)pos);
    (void)FSClose(ref);
    FlushVol(NULL, s->vRefNum);
}

#endif  /* !UNC_MAC_STAGE_WRITES */

/* Deep decode callback: writes straight through to the File Manager. With
 * UNC_MAC_STAGE_WRITES it instead only copies into RAM (a plain memcpy, no
 * Toolbox call) and sink_end does the writing at shallow depth. */
static int sink_write(void *ctx, UncFork fork, const void *buf, int32_t len)
{
    MacSink *s = (MacSink *)ctx;
#ifndef UNC_MAC_STAGE_WRITES
    uint32_t *pos = fork == UNC_FORK_DATA ? &s->dataPos : &s->rsrcPos;
    uint32_t off = 0, todo = (uint32_t)len;

    if (len <= 0) return 0;
    if (s->wrErr) return -1;
    {
        OSErr serr = StreamSelect(s, fork == UNC_FORK_RSRC);
        if (serr != noErr) {
            s->wrErr = 1;
            if (s->wrOSErr == noErr) s->wrOSErr = serr;
            gLastWriteErr = s->wrOSErr;
            return -1;
        }
    }
    /* Write in bounded pieces: FSWrite takes a byte count, and keeping it
     * small bounds how much the File Manager does per call in this deep,
     * cooperative context. */
    while (todo > 0) {
        long count = (long)(todo < 8192u ? todo : 8192u);
        long want = count;
        OSErr werr = FSWrite(s->openRef, &count,
                             (Ptr)((const char *)buf + off));
        if (werr != noErr || count != want) {
            s->wrErr = 1;
            /* Keep the FIRST OSErr. The grid and the alert could not tell
             * dskFulErr from a media error before, so a full disk read as a
             * hundred unexplained entry failures. */
            if (s->wrOSErr == noErr) s->wrOSErr = (werr != noErr ? werr : ioErr);
            gLastWriteErr = s->wrOSErr;
            return -1;
        }
        off += (uint32_t)want;
        todo -= (uint32_t)want;
        *pos += (uint32_t)want;
    }
    return 0;
#else
    Ptr *fb      = fork == UNC_FORK_DATA ? &s->dataBuf : &s->rsrcBuf;
    uint32_t *fl = fork == UNC_FORK_DATA ? &s->dataLen : &s->rsrcLen;
    uint32_t *fc = fork == UNC_FORK_DATA ? &s->dataCap : &s->rsrcCap;

    if (len <= 0) return 0;
    if ((fork == UNC_FORK_DATA && s->dropData) ||
        (fork == UNC_FORK_RSRC && s->dropRsrc))
        return 0;                    /* fork dropped on this Mac */
    if (s->bufErr) return -1;
    if (*fl + (uint32_t)len > *fc) {
        /* A shared block is fixed-size (both fork regions are packed into
         * it) and must not grow (it would break the other region); a
         * known-size fork should never overrun, but fail cleanly if so. */
        uint32_t ncap = *fc ? *fc : 8192;
        Ptr nb;
        if (s->sharedBuf) { s->bufErr = 1; return -1; }
        /* Unknown-size fork (nothing pre-allocated): grow it. */
        while (ncap < *fl + (uint32_t)len) ncap *= 2;
        nb = NewPtr((long)ncap);
        if (!nb) { s->bufErr = 1; return -1; }
        if (*fb) { ByteCopy((uint8_t *)*fb, (uint8_t *)nb, *fl);
                   DisposePtr(*fb); }
        *fb = nb; *fc = ncap;
    }
    ByteCopy((const uint8_t *)buf, (uint8_t *)(*fb + *fl), (uint32_t)len);
    *fl += (uint32_t)len;
    return 0;
#endif  /* !UNC_MAC_STAGE_WRITES */
}

#ifdef UNC_MAC_STAGE_WRITES
/* Write one staged fork to disk (shallow depth, in sink_end). Resource
 * fork opens via HOpenRF; both open one at a time. */
static OSErr StageFlush(MacSink *s, UncFork fork)
{
    Ptr fb      = fork == UNC_FORK_DATA ? s->dataBuf : s->rsrcBuf;
    uint32_t fl = fork == UNC_FORK_DATA ? s->dataLen : s->rsrcLen;
    short ref = 0;
    long count;
    OSErr err;

    if (fl == 0) return noErr;
    err = MyOpenFork(s->vRefNum, s->curDirID, s->curName, fsWrPerm,
                     fork == UNC_FORK_RSRC, &ref);
    if (err != noErr) return err;
    SetEOF(ref, (long)fl);
    SetFPos(ref, fsFromStart, 0);
    {
        uint32_t off = 0;
        err = noErr;
        while (off < fl && err == noErr) {
            uint32_t n = fl - off < 8192u ? fl - off : 8192u;
            count = (long)n;
            err = FSWrite(ref, &count, fb + off);
            if (err == noErr && (uint32_t)count != n) err = ioErr;
            off += n;
        }
    }
    FSClose(ref);
    FlushVol(NULL, s->vRefNum);   /* commit this fork before the next opens */
    return err;
}
#endif  /* !UNC_MAC_STAGE_WRITES */

static int sink_end(void *ctx, int status)
{
    MacSink *s = (MacSink *)ctx;

#ifndef UNC_MAC_STAGE_WRITES
    /* Everything is already on disk; just close the fork left open. The
     * close must happen even on failure, or the refNum leaks and the next
     * entry's open can fail for want of file-control blocks. */
    if (StreamClose(s) != noErr && status == UNC_OK) status = UNC_ERR_SINK;
    if (s->wrErr && status == UNC_OK) status = UNC_ERR_SINK;
    if (status == UNC_OK && !s->cur.is_dir) {
        StreamTrim(s, 0);
        StreamTrim(s, 1);
    }
#else
    if (s->bufErr && status == UNC_OK) status = UNC_ERR_MEM;

    /* Flush the staged forks to disk, at shallow depth, one fork open at a
     * time (data fork, then resource fork). At most one fork is ever staged
     * for a two-fork file — see sink_begin. */
    if (status == UNC_OK && !s->cur.is_dir) {
        if (StageFlush(s, UNC_FORK_DATA) != noErr ||
            StageFlush(s, UNC_FORK_RSRC) != noErr)
            status = UNC_ERR_SINK;
        /* A dropped fork means the file came out incomplete: report it. */
        if (status == UNC_OK && (s->dropData || s->dropRsrc))
            status = UNC_ERR_SINK;
    }
    /* When sharedBuf is set, rsrcBuf points inside dataBuf's single block;
     * dispose that one block exactly once. */
    if (s->sharedBuf) {
        if (s->dataBuf) DisposePtr(s->dataBuf);
        s->dataBuf = s->rsrcBuf = NULL;
    } else {
        if (s->dataBuf) { DisposePtr(s->dataBuf); s->dataBuf = NULL; }
        if (s->rsrcBuf) { DisposePtr(s->rsrcBuf); s->rsrcBuf = NULL; }
    }
#endif

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
#ifdef UNC_MAC_AUTOTEST
        unc_at_record(s->vRefNum, s->curDirID, s->curName);   /* success only */
#endif
        if (!s->cur.is_dir) {
            BlockMoveData(s->curName, s->lastName, s->curName[0] + 1);
            s->lastDir = s->curDirID;
        }
    } else if (!s->cur.is_dir) {
        /* Cancelled or failed: remove the empty/partial file this entry
         * created in sink_begin, so no incomplete output is left behind. */
        MyHDelete(s->vRefNum, s->curDirID, s->curName);
    }
    if (status != UNC_OK) s->errors++;
    /* Every failure that does not stop the archive goes in the report,
     * named: "some entries could not be extracted" is what the user was
     * told before 2026-08-29, and it names neither the entry nor the
     * one thing to do about it. UNC_ERR_ABORTED is the user's own
     * Cancel and is the outcome line's business, not a failure. */
    if (status != UNC_OK && status != UNC_ERR_ABORTED) {
        int b = 0, k;
        for (k = 0; k < (int)s->cur.name_len; k++)
            if (s->cur.name[k] == '/') b = k + 1;
        RepFailed(s->cur.name + b, (int)s->cur.name_len - b, status);
    }
    /* Kept apart from the rest: an entry this build cannot read YET is
     * the one failure whose answer is the file itself, and the alert
     * says so rather than "some entries could not be extracted". */
    if (status == UNC_ERR_UNSUPPORTED) s->unsupported++;
    if (s->cur.is_dir) s->dirCount++;
    else s->fileCount++;
    return 0;
}

/* The archive's OWN comment (Compact Pro's Note, or a zip's
 * end-of-central-directory comment). It belongs to no entry, so it
 * cannot arrive as one: it is written beside the extracted items — a
 * TeachText document named "Comments" in the destination folder,
 * holding the comment's bytes, which are already MacRoman and already
 * CR-separated because a Mac wrote them.
 *
 * Called before the first entry, so an archive that ALSO holds a file
 * called "Comments" takes the collision suffix sink_begin already
 * applies to it ("Comments~1"); the comment keeps the plain name.
 *
 * Never fails the archive: a comment that could not be written is worth
 * less than the files that can be, so every error returns 0 and the
 * walk goes on. It is not counted in fileCount either — that count is
 * what ExtractOne reads to decide whether a layer was an envelope. */
/* The archive's own note is not an entry, so nothing counted it and
 * nothing said so when it could not be written: it was dropped in
 * silence, which is the one thing this report exists to stop. It still
 * does not fail the archive — it is worth less than the files — but it
 * is now something that did not come out, and it is listed and counted
 * like anything else that did not (2026-08-29). */
static void RepCommentLost(MacSink *s)
{
    if (RepNew(1))
        RepCat("The note this archive carries could not be written "
               "to the disk");
    s->errors++;
}

static int sink_comment(void *ctx, const uint8_t *buf, uint16_t len)
{
    MacSink *s = (MacSink *)ctx;
    static const char kName[] = "Comments";
    Str63 name, base;
    short ref = 0;
    long count = (long)len;
    int i, attempt;
    OSErr err;

    for (i = 0; kName[i]; i++) name[i + 1] = (unsigned char)kName[i];
    name[0] = (unsigned char)i;
    BlockMoveData(name, base, name[0] + 1);

    for (attempt = 0; ; attempt++) {
        err = MyHCreate(s->vRefNum, s->rootDirID, name);
        if (err == noErr) break;
        if (err != dupFNErr || attempt >= 9) {
            RepCommentLost(s);
            return 0;
        }
        BlockMoveData(base, name, base[0] + 1);
        BumpName(name, attempt + 1);
        if (attempt == 0)
            RepRenamed("The archive's comment: ", (const uint8_t *)kName,
                       (int)sizeof kName - 1, name, " written as ");
    }

    if (MyOpenFork(s->vRefNum, s->rootDirID, name, fsWrPerm, 0,
                   &ref) != noErr) {
        MyHDelete(s->vRefNum, s->rootDirID, name);
        RepCommentLost(s);
        return 0;
    }
    if (len && (FSWrite(ref, &count, (Ptr)buf) != noErr ||
                count != (long)len)) {
        FSClose(ref);
        MyHDelete(s->vRefNum, s->rootDirID, name);
        RepCommentLost(s);
        return 0;
    }
    FSClose(ref);
    FlushVol(NULL, s->vRefNum);

    /* 'TEXT'/'ttxt': a document TeachText and SimpleText open, on every
     * system this application runs on. Spelled numerically because the
     * mock build compiles as C99, where a multi-character constant is
     * implementation-defined. */
    {
        CInfoPBRec pb;
        Str63 nm;
        BlockMoveData(name, nm, name[0] + 1);
        pb.hFileInfo.ioNamePtr = nm;
        pb.hFileInfo.ioVRefNum = s->vRefNum;
        pb.hFileInfo.ioDirID = s->rootDirID;
        pb.hFileInfo.ioFDirIndex = 0;
        if (PBGetCatInfoSync(&pb) == noErr) {
            pb.hFileInfo.ioFlFndrInfo.fdType = 0x54455854L;      /* TEXT */
            pb.hFileInfo.ioFlFndrInfo.fdCreator = 0x74747874L;   /* ttxt */
            pb.hFileInfo.ioDirID = s->rootDirID;   /* PBGetCatInfo clobbers */
            PBSetCatInfoSync(&pb);
        }
    }
#ifdef UNC_MAC_AUTOTEST
    unc_at_record(s->vRefNum, s->rootDirID, name);
#endif
    return 0;
}

/* ------------------------------------------------------------------ */
/* Extraction driver                                                  */
/* ------------------------------------------------------------------ */

#ifndef UNC_SINK_TEST
/* ------------------------------------------------------------------ */
/* Segmented archives: finding the parts                              */
/*                                                                    */
/* A part is recognized by its header, never by its name, so the       */
/* search is the same wherever the file came from: read the first 100  */
/* bytes and ask the engine whether they belong to this set.           */
/*                                                                    */
/* Order of attack, cheapest first:                                    */
/*   1. the folder the opened part is in — the usual case, silent;     */
/*   2. the "locate part N" alert, which offers Standard File. Its     */
/*      Drive/Eject buttons reach any mounted volume, so a part on     */
/*      another disk is found the same way as one in another folder.   */
/*                                                                    */
/* One part is open at a time (seg_release before the next seg_need),  */
/* because a Mac Plus with one floppy drive cannot mount two and       */
/* System 6 counts its FCBs.                                           */
/* ------------------------------------------------------------------ */

#define kSegMaxKnown 64      /* parts we can remember where to find */

static void ShowNote(short alrtID, const unsigned char *msg);

typedef struct {
    short vRefNum;
    long  dirID;
    Str63 name;
} SegLoc;

typedef struct {
    UncSegmentDesc desc;
    SegLoc  loc[kSegMaxKnown + 1];   /* loc[p].name[0] == 0 => unknown */
    /* Payload bytes of each part actually opened, so that "how much is
     * left" is a sum over what has been SEEN rather than a running
     * total. Indexed by part, so a part opened twice counts once. */
    uint32_t psize[kSegMaxKnown + 1];
    FileIO  fio;                     /* the one open part */
    short   refNum;                  /* 0 = nothing open */
    DialogPtr hide;                  /* progress dialog to hide while asking */
    int     asked;                   /* nonzero once the user was involved */
    int     cancelled;               /* user chose Cancel in the alert */
    /* Name-placed schemes only: the stem the family shares, and the
     * highest member number seen — which is how a set missing a part in
     * the middle is told from one that simply ends there. */
    unsigned char stem[64];
    short   stemlen;
    int     highest;
    /* Where a part that arrived inside an envelope is decoded to, and
     * whether any was. */
    short   tmpVol;
    long    tmpDir;
    int     peeled;
} SegHost;

/* Read a candidate file's header and return its part number, or 0. */
static int SegPartOf(SegHost *h, short vol, long dir, ConstStr255Param name)
{
    short ref;
    long count;
    uint8_t head[UNC_SEG_HEAD];
    OSErr err;
    int part;

    if (MyOpenFork(vol, dir, name, fsRdPerm, 0, &ref) != noErr) return 0;
    count = (long)sizeof head;
    err = FSRead(ref, &count, head);
    FSClose(ref);
    if (err != noErr && err != eofErr) return 0;
    if (count < (long)sizeof head) return 0;
    part = unc_segment_match(&h->desc, head, (int32_t)count);
    return part;
}

/* ------------------------------------------------------------------ */
/* The schemes that are placed by NAME                                 */
/*                                                                    */
/* A spanned zip part and a plain .NNN split part carry nothing that   */
/* says which set they belong to — only the FIRST and LAST parts of a  */
/* spanned zip are recognizable at all, and a split part is not even   */
/* that. So the family is decided by filename, exactly as the Linux    */
/* CLI decides it, and what keeps a wrong file out is not this scan    */
/* but the check the engine makes on the ASSEMBLED set (macextract.h,  */
/* unc_extract_segments). Names propose; content disposes.            */
/*                                                                    */
/* Filenames here are Str63 — a length byte and MacRoman bytes — so    */
/* the comparisons are written out rather than borrowed from a libc    */
/* this application does not link.                                     */
/* ------------------------------------------------------------------ */

#define kZipFamLast (-1)          /* the ".zip" member, whose number is N */

static void SegRemember(SegHost *h, int part, short vol, long dir,
                        ConstStr255Param name);

static short PLowerByte(short c)
{
    return (c >= 'A' && c <= 'Z') ? (short)(c - 'A' + 'a') : c;
}

/* Length of `nm` up to its LAST '.', or 0 if it has none. That is the
 * stem a family shares: "Archive.zip" and "Archive.z01" share
 * "Archive", and "Set.001" and "Set.002" share "Set". */
static short PStemLen(ConstStr255Param nm)
{
    short i, dot = 0;
    for (i = 1; i <= (short)nm[0]; i++)
        if (nm[i] == '.') dot = i;
    return dot ? (short)(dot - 1) : 0;
}

static int PStemMatches(const unsigned char *stem, short stemlen,
                        ConstStr255Param nm)
{
    short i;
    if ((short)nm[0] < stemlen + 2) return 0;      /* stem + '.' + one */
    if (nm[stemlen + 1] != '.') return 0;
    for (i = 0; i < stemlen; i++)
        if (PLowerByte(stem[i]) != PLowerByte(nm[i + 1])) return 0;
    return 1;
}

/* Which member of the zip family `nm` is: NN for ".zNN", kZipFamLast
 * for ".zip", 0 for anything else. Source for the naming: the volume
 * regex in reference/XADMaster/XADZipParser.m, ^NAME\.(zip|z[0-9]{2})$,
 * matched case-insensitively. */
static int ZipFamPartOf(const unsigned char *stem, short stemlen,
                        ConstStr255Param nm)
{
    short ext = stemlen + 2;                       /* first byte after '.' */
    if (!PStemMatches(stem, stemlen, nm)) return 0;
    if ((short)nm[0] == ext + 2 &&
        PLowerByte(nm[ext]) == 'z' && PLowerByte(nm[ext + 1]) == 'i' &&
        PLowerByte(nm[ext + 2]) == 'p')
        return kZipFamLast;
    /* ext is the INDEX of the first extension byte, so a three-byte
     * extension ends at ext+2 and the name is ext+2 long — the same
     * arithmetic the ".zip" test above uses. Written ext+1 here at
     * first, which matched nothing: the .zip member was found, the
     * numbered parts were not, and the set failed as damaged rather
     * than as incomplete. The .NNN scheme was right, so a passing
     * split case said nothing about this one. */
    if ((short)nm[0] == ext + 2 && PLowerByte(nm[ext]) == 'z' &&
        nm[ext + 1] >= '0' && nm[ext + 1] <= '9' &&
        nm[ext + 2] >= '0' && nm[ext + 2] <= '9') {
        int n = (nm[ext + 1] - '0') * 10 + (nm[ext + 2] - '0');
        return n >= 1 ? n : 0;                     /* there is no part zero */
    }
    return 0;
}

/* Which member of a .NNN split `nm` is, or 0. Three digits exactly, and
 * ".000" is not one: reference/XADMaster/XADSplitFileParser.m. */
static int SplitPartOf(const unsigned char *stem, short stemlen,
                       ConstStr255Param nm)
{
    short ext = stemlen + 2;
    short i;
    int n = 0;
    if (!PStemMatches(stem, stemlen, nm)) return 0;
    if ((short)nm[0] != ext + 2) return 0;
    for (i = 0; i < 3; i++) {
        if (nm[ext + i] < '0' || nm[ext + i] > '9') return 0;
        n = n * 10 + (nm[ext + i] - '0');
    }
    return n >= 1 ? n : 0;
}

/* Walk one folder and record every member of the family, by name. The
 * zip family's ".zip" member is the LAST part, and its number is only
 * known once that part has been read, so it is reported separately. */
static void SegScanFamily(SegHost *h, short vol, long dir, int split,
                          Str63 lastName)
{
    CInfoPBRec pb;
    Str63 nm;
    short idx;
    long z;

    lastName[0] = 0;
    for (idx = 1; idx < 32767; idx++) {
        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        nm[0] = 0;
        pb.hFileInfo.ioNamePtr = nm;
        pb.hFileInfo.ioVRefNum = vol;
        pb.hFileInfo.ioDirID = dir;
        pb.hFileInfo.ioFDirIndex = idx;
        if (PBGetCatInfoSync(&pb) != noErr) break;
        if (pb.hFileInfo.ioFlAttrib & 0x10) continue;         /* a folder */
        {
            int part = split ? SplitPartOf(h->stem, h->stemlen, nm)
                             : ZipFamPartOf(h->stem, h->stemlen, nm);
            if (part == kZipFamLast) {
                for (z = 0; z <= (long)nm[0]; z++) lastName[z] = nm[z];
                continue;
            }
            if (part >= 1) {
                SegRemember(h, part, vol, dir, nm);
                if (part > h->highest) h->highest = part;
                h->psize[part <= kSegMaxKnown ? part : 0] = 0;
            }
        }
    }
}

/* The length of a part, without opening it: a directory lookup, which
 * on a hard disk is free and on a floppy costs nothing the user can
 * see. A plain split needs every one of them before extraction starts,
 * because the sum IS the joined length and nothing else states it
 * (DECISIONS.md 2026-08-10). */
static uint32_t SegPartLength(SegHost *h, int part)
{
    CInfoPBRec pb;
    Str63 nm;
    long z;
    short i;

    if (part < 1 || part > kSegMaxKnown || !h->loc[part].name[0])
        return UNC_SIZE_UNKNOWN;
    for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
    for (i = 0; i <= (short)h->loc[part].name[0]; i++)
        nm[i] = h->loc[part].name[i];
    pb.hFileInfo.ioNamePtr = nm;
    pb.hFileInfo.ioVRefNum = h->loc[part].vRefNum;
    pb.hFileInfo.ioDirID = h->loc[part].dirID;
    pb.hFileInfo.ioFDirIndex = 0;
    if (PBGetCatInfoSync(&pb) != noErr) return UNC_SIZE_UNKNOWN;
    return (uint32_t)pb.hFileInfo.ioFlLgLen;
}

/* Read the part count out of the one file that has it — the ".zip"
 * member of a spanned set. Returns nonzero on success, having filled in
 * the descriptor and recorded that file as the last part. */
static int SegDescribeLast(SegHost *h, short vol, long dir,
                           ConstStr255Param nm)
{
    UncSegmentDesc cand;
    FileIO probe;
    UncIO pio;
    short ref;
    long eof = 0;
    int ok;

    if (MyOpenFork(vol, dir, nm, fsRdPerm, 0, &ref) != noErr) return 0;
    GetEOF(ref, &eof);
    probe.refNum = ref;
    probe.size = (uint32_t)eof;
    probe.pos = 0;
    pio.ctx = &probe;
    pio.read = fio_read;
    pio.seek = fio_seek;
    pio.tell = fio_tell;
    pio.size = fio_size;
    ok = unc_segment_describe(&pio, &cand) == UNC_OK && cand.nparts;
    FSClose(ref);
    if (!ok) return 0;
    h->desc = cand;
    SegRemember(h, (int)cand.nparts, vol, dir, nm);
    if ((int)cand.nparts > h->highest) h->highest = (int)cand.nparts;
    return 1;
}

/* ------------------------------------------------------------------ */
/* Parts that arrived inside an envelope                               */
/*                                                                    */
/* A real download is per-part wrapped — Archive.sit.1.hqx — so the    */
/* envelope has to come off each part BEFORE the join. On this side    */
/* that means writing the decoded part somewhere, which is the whole   */
/* difference from the Linux CLI: it peeks ~100 bytes and decodes to a */
/* file, and so does this, but here the file lands on the output       */
/* volume and is deleted when the join is over.                        */
/*                                                                    */
/* StuffIt only, for the reason the CLI gives: its header is IN the    */
/* payload, so unwrapping is all that stands between a wrapped part    */
/* and the fingerprint check every other part gets. A spanned zip or a */
/* .NNN part is placed by FILENAME, and the filename of a wrapped part */
/* is the wrapper's.                                                   */
/* ------------------------------------------------------------------ */

typedef struct {
    short    outRef;         /* PEEL: fork being written, 0 in peek mode */
    uint8_t *head;           /* PEEK: where the first bytes go           */
    int32_t  cap, len;
    int      entries;
    int      err;
} EnvSink;

static int env_begin(void *ctx, const UncEntryInfo *info)
{
    EnvSink *e = (EnvSink *)ctx;
    if (info->is_dir) { e->entries++; return 1; }
    return e->entries++ ? 1 : 0;         /* the first file is the payload */
}

static int env_write(void *ctx, UncFork fork, const void *buf, int32_t len)
{
    EnvSink *e = (EnvSink *)ctx;

    if (fork != UNC_FORK_DATA || len <= 0) return 0;
    if (e->outRef) {
        long count = (long)len;
        if (FSWrite(e->outRef, &count, (const void *)buf) != noErr ||
            count != (long)len) { e->err = 1; return -1; }
        return 0;
    }
    if (e->len < e->cap) {
        int32_t n = e->cap - e->len, i;
        const uint8_t *sp = (const uint8_t *)buf;
        if (n > len) n = len;
        for (i = 0; i < n; i++) e->head[e->len + i] = sp[i];
        e->len += n;
    }
    /* Enough to decide on; the abort is reported as a per-entry failure,
     * which is why a peek is judged by what it collected. */
    return e->len >= e->cap ? -1 : 0;
}

static int env_end(void *ctx, int status)
{
    EnvSink *e = (EnvSink *)ctx;
    if (e->outRef && status != UNC_OK) e->err = 1;
    return 0;
}

/* Run one envelope layer of a file into `es`. 0 if it is not one. */
static int EnvRun(short vol, long dir, ConstStr255Param nm, EnvSink *es,
                  UncAlloc *al)
{
    FileIO fio;
    UncIO eio;
    UncSink sk;
    UncProgress prog;
    UncFormat fmt;
    short ref;
    long eof = 0;
    int rc;

    if (MyOpenFork(vol, dir, nm, fsRdPerm, 0, &ref) != noErr) return 0;
    GetEOF(ref, &eof);
    fio.refNum = ref;
    fio.size = (uint32_t)eof;
    fio.pos = 0;
    eio.ctx = &fio;
    eio.read = fio_read;
    eio.seek = fio_seek;
    eio.tell = fio_tell;
    eio.size = fio_size;

    fmt = unc_sniff(&eio);
    if (!unc_format_is_envelope(fmt)) {
        FSClose(ref);
        return 0;
    }
    sk.ctx = es;
    sk.begin_entry = env_begin;
    sk.write = env_write;
    sk.end_entry = env_end;
    sk.comment = NULL;    /* an envelope layer carries none */
    prog.ctx = NULL;
    prog.tick = NULL;
    rc = unc_extract_as(fmt, &eio, &sk, al, NULL, NULL);
    FSClose(ref);
    if (es->outRef && rc != UNC_OK) es->err = 1;
    return 1;
}

/* Do the parts found so far account for the whole set? StuffIt states
 * the payload total in every part, so this is the same sum that ends the
 * joiner's walk — and it is the only question that decides whether
 * opening envelopes is worth anything. */
static int SegHaveAll(SegHost *h)
{
    uint32_t sum = 0;
    int p;

    if (h->desc.total == UNC_SIZE_UNKNOWN) return 0;
    for (p = 1; p <= kSegMaxKnown && h->loc[p].name[0]; p++) {
        uint32_t len = SegPartLength(h, p);
        if (len == UNC_SIZE_UNKNOWN || len <= h->desc.head_len) return 0;
        sum += len - h->desc.head_len;
        if (sum >= h->desc.total) return 1;
    }
    return 0;
}

/* Is this file an envelope holding a part of the set? If so it is
 * decoded whole, next to the output, and recorded. */
static int SegWrappedPartOf(SegHost *h, short vol, long dir,
                            ConstStr255Param nm, UncAlloc *al)
{
    uint8_t head[UNC_SEG_HEAD];
    EnvSink es;
    Str255 tmp;              /* PStrCat's contract is Str255, not Str63 */
    int part;
    short ref;
    long z;

    for (z = 0; z < (long)sizeof es; z++) ((char *)&es)[z] = 0;
    es.head = head;
    es.cap = (int32_t)sizeof head;
    if (!EnvRun(vol, dir, nm, &es, al)) return 0;
    part = es.len > 0 ? unc_segment_match(&h->desc, head, es.len) : 0;
    if (part < 1) return 0;
    if (h->loc[part].name[0]) return part;      /* already have that one */

    /* "MacExtract part N" — on the output volume, which is the one place
     * this application knows it may write. */
    tmp[0] = 0;
    PStrCat(tmp, "MacExtract part ");
    PStrCatNum(tmp, (long)part);
    MyHDelete(h->tmpVol, h->tmpDir, tmp);        /* a stale one, if any */
    if (MyHCreate(h->tmpVol, h->tmpDir, tmp) != noErr) return 0;
    if (MyOpenFork(h->tmpVol, h->tmpDir, tmp, fsWrPerm, 0, &ref) != noErr) {
        MyHDelete(h->tmpVol, h->tmpDir, tmp);
        return 0;
    }
    for (z = 0; z < (long)sizeof es; z++) ((char *)&es)[z] = 0;
    es.outRef = ref;
    if (!EnvRun(vol, dir, nm, &es, al) || es.err) {
        FSClose(ref);
        MyHDelete(h->tmpVol, h->tmpDir, tmp);
        return 0;
    }
    FSClose(ref);
    FlushVol(NULL, h->tmpVol);
    SegRemember(h, part, h->tmpVol, h->tmpDir, tmp);
    h->peeled = 1;
    return part;
}

/* Walk a folder looking INSIDE envelopes. Only ever called when the set
 * is short of a part: a complete one opens nothing. */
static void SegScanWrapped(SegHost *h, short vol, long dir, UncAlloc *al)
{
    CInfoPBRec pb;
    Str63 nm;
    short idx;
    long z;

    for (idx = 1; idx < 32767; idx++) {
        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        nm[0] = 0;
        pb.hFileInfo.ioNamePtr = nm;
        pb.hFileInfo.ioVRefNum = vol;
        pb.hFileInfo.ioDirID = dir;
        pb.hFileInfo.ioFDirIndex = idx;
        if (PBGetCatInfoSync(&pb) != noErr) break;
        if (pb.hFileInfo.ioFlAttrib & 0x10) continue;          /* a folder */
        if (SegPartOf(h, vol, dir, nm)) continue;      /* a part in its own right */
        SegWrappedPartOf(h, vol, dir, nm, al);
        if (SegHaveAll(h)) break;
    }
}

/* Remove the decoded parts: this application's own litter, and a join
 * that failed is when a user is least helped by finding pieces of one. */
static void SegPeelClean(SegHost *h)
{
    int p;
    if (!h->peeled) return;
    for (p = 1; p <= kSegMaxKnown; p++) {
        Str255 tmp;
        tmp[0] = 0;
        PStrCat(tmp, "MacExtract part ");
        PStrCatNum(tmp, (long)p);
        MyHDelete(h->tmpVol, h->tmpDir, tmp);
    }
    FlushVol(NULL, h->tmpVol);
    h->peeled = 0;
}

/* Compact Pro: which of these is the LAST segment?
 *
 * Only the last one carries the index, and only the index says how many
 * segments there are — so a set opened at any other segment has no
 * count, and neither the joiner nor the "part N of M" arithmetic can
 * start. Every segment identifies itself (a 16-bit set identity in its
 * header), so the answer is here on the disk; it just has to be asked
 * for, one 8-byte header at a time. The CLI does exactly this.
 *
 * Leaves h->desc alone if no part answers, and the caller then reports
 * the set as incomplete, which it is: without the final segment there
 * is no directory anywhere. */
static void SegFindLast(SegHost *h)
{
    int p;

    for (p = 1; p <= kSegMaxKnown; p++) {
        UncSegmentDesc cand;
        FileIO probe;
        UncIO pio;
        short ref;
        long eof = 0;

        if (!h->loc[p].name[0]) continue;
        if (MyOpenFork(h->loc[p].vRefNum, h->loc[p].dirID, h->loc[p].name,
                       fsRdPerm, 0, &ref) != noErr) continue;
        GetEOF(ref, &eof);
        probe.refNum = ref;
        probe.size = (uint32_t)eof;
        probe.pos = 0;
        pio.ctx = &probe;
        pio.read = fio_read;
        pio.seek = fio_seek;
        pio.tell = fio_tell;
        pio.size = fio_size;
        if (unc_segment_describe(&pio, &cand) == UNC_OK && cand.nparts) {
            h->desc = cand;
            FSClose(ref);
            return;
        }
        FSClose(ref);
    }
}

static void SegRemember(SegHost *h, int part, short vol, long dir,
                        ConstStr255Param name)
{
    short i;
    if (part < 1 || part > kSegMaxKnown) return;
    if (h->loc[part].name[0]) return;         /* first match wins */
    h->loc[part].vRefNum = vol;
    h->loc[part].dirID = dir;
    for (i = 0; i <= (short)name[0]; i++) h->loc[part].name[i] = name[i];
}

/* Walk one folder, recording every part of this set that it holds. */
static void SegScanDir(SegHost *h, short vol, long dir)
{
    CInfoPBRec pb;
    Str63 nm;
    short idx;
    long z;

    for (idx = 1; idx < 512; idx++) {
        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        pb.hFileInfo.ioNamePtr = nm;
        pb.hFileInfo.ioVRefNum = vol;
        pb.hFileInfo.ioDirID = dir;
        pb.hFileInfo.ioFDirIndex = idx;
        if (PBGetCatInfoSync(&pb) != noErr) return;    /* past the last item */
        if (pb.hFileInfo.ioFlAttrib & ioDirMask) continue;
        {
            int part = SegPartOf(h, vol, dir, nm);
            if (part) SegRemember(h, part, vol, dir, nm);
        }
    }
}

#ifndef UNC_MAC_AUTOTEST
#define kSegALRT        131
#define kSegFindItem    1
#define kSegSkipItem    2
#define kSegCancelItem  3
#define kSegDiskItem    4    /* NOT in the DITL — see SegDiskFilter */

#define kSegRootDirID   2L   /* fsRtDirID; the headers here do not define it */

/* An alert filter takes no context, so these say which part the alert
 * currently on screen is waiting for. The shell already keeps state this
 * way (gHasWNE); the no-global rule is the engine's. */
static SegHost *gSegAsking = NULL;
static int gSegWantPart = 0;
static long gSegNextPoll = 0;    /* TickCount: throttles SegDiskFilter */

/* Record every part of this set that is on the volume in `drive`.
 * PBHGetVInfo reports a volume's drive in ioVDrvInfo, so the disk just
 * put in is found by number rather than by walking every volume
 * mounted — a hard disk's root is not worth scanning again. */
static void SegScanDrive(SegHost *h, short drive)
{
    HParamBlockRec pb;
    Str63 nm;
    short idx;
    long z;

    for (idx = 1; idx < 64; idx++) {
        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        pb.volumeParam.ioNamePtr = nm;
        pb.volumeParam.ioVolIndex = idx;
        if (PBHGetVInfoSync(&pb) != noErr) return;   /* past the last volume */
        if (pb.volumeParam.ioVDrvInfo != drive) continue;
        SegScanDir(h, pb.volumeParam.ioVRefNum, kSegRootDirID);
        return;
    }
}

/* Notice a disk going in while the alert is asking for a part.
 *
 * This is the whole feature: the user is told "part 2 has not been
 * found", puts the disk in, and the extraction carries on rather than
 * making them answer an alert about a disk already in the machine.
 *
 * Two things about it are not obvious, and both cost a run to find.
 *
 * The event handed to a filter is never the one wanted. `ModalDialog`
 * "calls the Event Manager function GetNextEvent with a mask that
 * excludes disk-inserted events" (Inside Macintosh: Toolbox Essentials,
 * ModalDialog), so a diskEvt is never delivered — a build that dismissed
 * the alert on ANY diskEvt reaching this filter sat through two
 * insertions unmoved. The queue has to be asked directly, which is done
 * here on every event including the null ones, and that is what makes it
 * work with nobody touching the mouse.
 *
 * And fetching the event is not merely how we hear about the disk, it is
 * what gets the disk MOUNTED: a version that left the queue alone and
 * instead polled the volume list twice a second never saw a new volume
 * at all. The mount result is what the event's high word carries, so
 * nothing has mounted until somebody fetches it. */
static pascal Boolean SegDiskFilter(DialogPtr dlg, EventRecord *evt,
                                    INTEGER *itemHit)
{
    EventRecord de;

    (void)dlg;
    if (gSegAsking == NULL) return false;

    /* Return and Enter press the default button — and doing that here is
     * not a courtesy, it is replacing what was lost. An alert with no
     * filter gets a standard one that maps them to item 1; supplying our
     * own takes that away, and the symptom is not subtle in hindsight:
     * the alert simply ignored its own default button, and every later
     * step of --segments clicked into a dialog that should have closed.
     * Handled on every pass, unthrottled, because a keystroke is not
     * something to poll for. */
    if (evt->what == keyDown || evt->what == autoKey) {
        char c = (char)(evt->message & charCodeMask);
        if (c == '\r' || c == 0x03) {
            *itemHit = kSegFindItem;
            return true;
        }
    }

    /* THROTTLED, and that is not an optimisation. Calling GetNextEvent
     * on every pass takes events out from under the modal loop that
     * owns them: with it unthrottled the alert stopped acting on its
     * own buttons — Return was still sitting on an undismissed alert
     * three seconds later, and every later step of --segments then
     * clicked into a dialog that should have been gone. Twice a second
     * is far quicker than anyone swaps a floppy. */
    if (TickCount() < gSegNextPoll) return false;
    gSegNextPoll = TickCount() + 30;

    if (!GetNextEvent(diskMask, &de)) return false;

    /* Nonzero result: no HFS volume mounted. This shell has nothing to
     * offer for that — it is not the Finder, and formatting somebody's
     * disk is not its business — so the alert simply stays up. */
    if ((short)((de.message >> 16) & 0xFFFFL) != noErr) return false;

    SegScanDrive(gSegAsking, (short)(de.message & 0xFFFFL));

    if (gSegWantPart >= 1 && gSegWantPart <= kSegMaxKnown
        && gSegAsking->loc[gSegWantPart].name[0]) {
        *itemHit = kSegDiskItem;
        return true;               /* the disk had it: take the alert down */
    }
    return false;                  /* some other disk: keep asking */
}

/* Payload bytes of this set not yet read, or 0 if that cannot be said.
 *
 * "Part 2 of 3" is what a person wants and the format does not store a
 * part count, so it cannot be said at all — but how much is left CAN
 * be: the header carries the total payload of the whole set, and the
 * parts already opened account for the rest. It answers roughly the
 * same question, "how many more floppies is this", without inventing a
 * number the file does not contain. */
static uint32_t SegRemaining(SegHost *h)
{
    uint32_t seen = 0;
    short p;

    if (h->desc.total == 0) return 0;
    for (p = 1; p <= kSegMaxKnown; p++) seen += h->psize[p];
    return seen < h->desc.total ? h->desc.total - seen : 0;
}

/* Append "About 33K still to read." for a size worth mentioning. */
static void SegCatRemaining(Str255 msg, uint32_t left)
{
    if (left == 0) return;
    PStrCat(msg, " About ");
    if (left >= 1024) {
        PStrCatNum(msg, (long)((left + 512) / 1024));
        PStrCat(msg, "K");
    } else {
        PStrCatNum(msg, (long)left);
        PStrCat(msg, " bytes");
    }
    PStrCat(msg, " still to read.");
}

/* Ask the user to point at part `part`. Returns nonzero once it has been
 * located. The autotest build has no user, so this is not compiled there
 * and a part that was not found beside the archive is simply missing. */
static int SegAskUser(SegHost *h, int part)
{
    Str255 msg;
    SFReply reply;
    Point where;
    short hit;
    short savedMask;

    for (;;) {
        msg[0] = 0;
        PStrCat(msg, "Part ");
        PStrCatNum(msg, (long)part);
        PStrCat(msg, " of \"");
        { short i; for (i = 0; i < (short)h->desc.name_len && msg[0] < 200; i++)
                       msg[++msg[0]] = h->desc.name[i]; }
        PStrCat(msg, "\" has not been found.");
        SegCatRemaining(msg, SegRemaining(h));
        PStrCat(msg, " Locate it, skip it, or cancel.");
        ParamText(msg, "\p", "\p", "\p");

        if (h->hide) HideWindow((WindowPtr)h->hide);
        gSegAsking = h;
        gSegWantPart = part;
        /* Disk-inserted events reach the queue only if the system event
         * mask lets them; saved and put back rather than restored to an
         * assumed default, because the default is not ours to know. */
        savedMask = LMGetSysEvtMask();
        LMSetSysEvtMask(savedMask | diskMask);
        gSegNextPoll = 0;
        hit = CautionAlert(kSegALRT, NewModalFilterUPP(SegDiskFilter));
        LMSetSysEvtMask(savedMask);
        gSegAsking = NULL;
        h->asked = 1;

        /* The filter found it on a disk that was put in while the alert
         * was up; nothing was clicked. */
        if (hit == kSegDiskItem) {
            if (h->hide) ShowWindow((WindowPtr)h->hide);
            return 1;
        }

        if (hit == kSegFindItem) {
            SetPt(&where, 90, 90);
            reply.good = false;
            SFGetFile(where, "\p", NULL, -1, NULL, NULL, &reply);
            if (reply.good) {
                int got;
                /* A spanned zip part and a split part cannot prove
                 * which part they are, so an offer of one is taken at
                 * face value and the engine's check on the assembled
                 * set is what catches a wrong file. Said out loud,
                 * because everywhere else here a part is verified
                 * before it is used. */
                if (h->desc.scheme == UNC_FORMAT_ZIPSEG ||
                    h->desc.scheme == UNC_FORMAT_SPLIT)
                    got = part;
                else
                    got = SegPartOf(h, reply.vRefNum, 0, reply.fName);
                if (got == part) {
                    SegRemember(h, part, reply.vRefNum, 0, reply.fName);
                    /* The rest of the set is often beside it. */
                    SegScanDir(h, reply.vRefNum, 0);
                    if (h->hide) ShowWindow((WindowPtr)h->hide);
                    return 1;
                }
                if (got) {
                    Str255 s;
                    s[0] = 0;
                    PStrCat(s, "That is part ");
                    PStrCatNum(s, (long)got);
                    PStrCat(s, " of the same archive. Part ");
                    PStrCatNum(s, (long)part);
                    PStrCat(s, " is the one needed.");
                    ShowNote(kErrorALRT, s);
                    /* Keep it: a later part will want it. */
                    SegRemember(h, got, reply.vRefNum, 0, reply.fName);
                } else {
                    ShowNote(kErrorALRT,
                             "\pThat file is not part of this archive.");
                }
            }
            continue;             /* ask again */
        }

        if (hit == kSegCancelItem) h->cancelled = 1;
        if (h->hide) ShowWindow((WindowPtr)h->hide);
        return 0;                 /* Skip or Cancel */
    }
}
#endif  /* !UNC_MAC_AUTOTEST */

static int seg_need(void *ctx, const UncSegmentDesc *desc, int part, UncIO *io)
{
    SegHost *h = (SegHost *)ctx;
    long eof;

    (void)desc;
    if (part < 1 || part > kSegMaxKnown) return UNC_ERR_SEGMENTED;
#ifndef UNC_MAC_AUTOTEST
    if (!h->loc[part].name[0] && !h->cancelled) SegAskUser(h, part);
    if (h->cancelled) return UNC_ERR_ABORTED;
#endif
    if (!h->loc[part].name[0]) return UNC_ERR_SEGMENTED;

    if (MyOpenFork(h->loc[part].vRefNum, h->loc[part].dirID,
                   h->loc[part].name, fsRdPerm, 0, &h->refNum) != noErr)
        return UNC_ERR_SEGMENTED;
    eof = 0;
    GetEOF(h->refNum, &eof);
    if (eof <= 0) { FSClose(h->refNum); h->refNum = 0; return UNC_ERR_SEGMENTED; }

    /* What this part contributes to the whole, for the "still to read"
     * line in the alert. Every part carries the same header, which is
     * not payload. */
    if (part <= kSegMaxKnown)
        h->psize[part] = (uint32_t)eof > h->desc.head_len
                       ? (uint32_t)eof - h->desc.head_len : 0;

    h->fio.refNum = h->refNum;
    h->fio.size = (uint32_t)eof;
    h->fio.pos = 0;
    io->ctx = &h->fio;
    io->read = fio_read;
    io->seek = fio_seek;
    io->tell = fio_tell;
    io->size = fio_size;
    return UNC_OK;
}

static void seg_release(void *ctx, UncIO *io)
{
    SegHost *h = (SegHost *)ctx;
    (void)io;
    if (h->refNum) { FSClose(h->refNum); h->refNum = 0; }
}

static long gPeakUsage;   /* engine heap high-water mark from the last RunExtract */
#ifdef UNC_AT_BUDGET
/* The result grid reports what the engine USED and never what it was
 * ALLOWED, so a budget refusal and a genuine shortage look identical on
 * screen. These two make the difference visible. See tools/vmac/README.md. */
#endif

/* Core extraction: open the archive at (inVol,inDir,name) and extract into
 * (outVol,outDir). The interactive app passes the same volume/folder for
 * both (extract next to the archive); the autotest uses a separate output
 * volume. Returns the unc_extract status; fills *entries and *errors from the
 * sink, and gPeakUsage with the engine's peak heap use. prog may be NULL.
 * Shared by the interactive app and the on-Mac autotest. */
/* `out` is filled with where a single-file extraction landed, so the
 * caller can take the next envelope off it; pass NULL not to care. */
typedef struct {
    int       fileCount, dirCount;
    Str63     name;
    long      dirID;
    UncFormat fmt;        /* what this layer turned out to be */
} ExtractShape;

/* ------------------------------------------------------------------ */
/* Asking for a password                                              */
/*                                                                    */
/* The engine calls this when an entry turns out to need one, and     */
/* again — with a rising `attempt` — when the archive refuses what it */
/* was given. Asking at that moment rather than up front is the whole */
/* reason the engine takes a callback: most archives never need one,  */
/* and the ones that do only say so partway through.                  */
/*                                                                    */
/* What is typed goes into gPassBuf and the field shows bullets. That */
/* is done by swapping the character inside the filter, on its way to */
/* the Dialog Manager — the same trick every Mac application used     */
/* before there was a password field to ask for. A click in the field */
/* or an arrow key would let the two diverge, so both are swallowed:  */
/* the caret stays at the end and the buffer stays the truth.         */
/* ------------------------------------------------------------------ */

#ifndef UNC_MAC_AUTOTEST

#define kPassDLOG       132
#define kPassOKItem     1
#define kPassCancelItem 2
#define kPassTextItem   3
#define kPassMsgItem    4
#define kPassBullet     0xA5   /* MacRoman bullet */

static Str63 gPassBuf;         /* what was actually typed */

static pascal Boolean PassFilter(DialogPtr dlg, EventRecord *ev, short *item)
{
    char ch;
    (void)dlg;
    if (ev->what == mouseDown) {
        /* Inside the field is the one click that could move the caret
         * away from the end; everything else (the buttons) goes on. */
        Point p = ev->where;
        GrafPtr save;
        short kind;
        Handle h;
        Rect box;
        GetPort(&save);
        SetPort((GrafPtr)dlg);
        GlobalToLocal(&p);
        SetPort(save);
        GetDialogItem(dlg, kPassTextItem, &kind, &h, &box);
        if (PtInRect(p, &box)) return true;      /* swallowed */
        return false;
    }
    if (ev->what != keyDown && ev->what != autoKey) return false;
    ch = (char)(ev->message & charCodeMask);
    if ((ev->modifiers & cmdKey) != 0) return false;
    if (ch == '\r' || ch == 3) { *item = kPassOKItem; return true; }
    if (ch == 27) { *item = kPassCancelItem; return true; }
    if (ch == 8) {                                /* backspace */
        if (gPassBuf[0] > 0) gPassBuf[0]--;
        return false;                             /* let the field shrink */
    }
    if (ch == 28 || ch == 29 || ch == 30 || ch == 31) return true; /* arrows */
    if ((unsigned char)ch < 32) return false;
    if (gPassBuf[0] >= UNC_PASSWORD_MAX) return true;   /* full: ignore */
    gPassBuf[++gPassBuf[0]] = (unsigned char)ch;
    /* Show a bullet instead of what was typed. */
    ev->message = (ev->message & ~(long)charCodeMask) | kPassBullet;
    return false;
}

typedef struct {
    Str63       name;      /* the archive, for the message */
    WindowPtr   hide;      /* the progress dialog, out of the way */
} PassHost;

static int MacAskPassword(void *ctx, uint8_t *buf, uint16_t cap,
                          uint16_t *len, int attempt)
{
    PassHost *ph = (PassHost *)ctx;
    DialogPtr dlg;
    Str255 msg;
    short hit, kind, i;
    Handle h;
    Rect box;
    ModalFilterUPP filter;

    msg[0] = 0;
    if (attempt > 0)
        PStrCat(msg, "That password was refused. ");
    PStrCat(msg, "\"");
    for (i = 0; i < (short)ph->name[0] && msg[0] < 180; i++)
        msg[++msg[0]] = ph->name[i + 1];
    PStrCat(msg, "\" is encrypted. Type its password, or click Cancel to "
                 "skip the entries that need one.");
    ParamText(msg, "\p", "\p", "\p");

    if (ph->hide) HideWindow(ph->hide);
    dlg = GetNewDialog(kPassDLOG, NULL, (WindowPtr)-1);
    if (!dlg) {
        if (ph->hide) ShowWindow(ph->hide);
        return 0;
    }
    gPassBuf[0] = 0;
    GetDialogItem(dlg, kPassTextItem, &kind, &h, &box);
    SelectDialogItemText(dlg, kPassTextItem, 0, 0);
    /* The OK button is the default one; draw its ring. */
    GetDialogItem(dlg, kPassOKItem, &kind, &h, &box);
    InsetRect(&box, -4, -4);
    SetPort((GrafPtr)dlg);
    PenSize(3, 3);
    FrameRoundRect(&box, 16, 16);
    PenSize(1, 1);

    filter = NewModalFilterUPP(PassFilter);
    do {
        ModalDialog(filter, &hit);
    } while (hit != kPassOKItem && hit != kPassCancelItem);
    DisposeDialog(dlg);
    if (ph->hide) ShowWindow(ph->hide);

    if (hit != kPassOKItem || gPassBuf[0] == 0) {
        gPassBuf[0] = 0;
        return 0;
    }
    *len = gPassBuf[0] > cap ? cap : gPassBuf[0];
    for (i = 0; i < (short)*len; i++) buf[i] = gPassBuf[i + 1];
    gPassBuf[0] = 0;               /* do not leave it in the data segment */
    return 1;
}

/* StuffIt classic keeps the block that verifies a password in the
 * ARCHIVE's resource fork ('MKey' 0). Read it here, as plain bytes
 * rather than through the Resource Manager: this is somebody else's
 * file and its map may be anything, and unc_resfork_find bounds-checks
 * every field it follows. A fork bigger than the cap is not read at
 * all — that is a self-extracting archive, and an encrypted one of
 * those is a thing Compact Pro cannot even create. Returns 1 if eight
 * bytes were found. */
#define kMKeyForkMax 32768L

static int LoadMKey(short vol, long dir, ConstStr255Param name,
                    uint8_t out[8])
{
    short refNum;
    long size = 0, got;
    Ptr buf;
    uint32_t off = 0, len = 0;
    int ok = 0;

    if (MyOpenFork(vol, dir, name, fsRdPerm, 1, &refNum) != noErr) return 0;
    GetEOF(refNum, &size);
    if (size <= 0 || size > kMKeyForkMax) { FSClose(refNum); return 0; }
    buf = NewPtr(size);
    if (!buf) { FSClose(refNum); return 0; }
    got = size;
    if (FSRead(refNum, &got, buf) == noErr && got == size &&
        unc_resfork_find((const uint8_t *)buf, (uint32_t)size,
                         0x4D4B6579UL /* 'MKey' */, 0, &off, &len) == UNC_OK &&
        len == 8) {
        long i;
        for (i = 0; i < 8; i++) out[i] = ((unsigned char *)buf)[off + i];
        ok = 1;
    }
    DisposePtr(buf);
    FSClose(refNum);
    return ok;
}

#endif /* !UNC_MAC_AUTOTEST */

/* `origVol`/`origDir` is the folder the USER's file came from, which is
 * not where this layer's file is once an envelope has been taken off —
 * and it is where the other parts of a wrapped set are still sitting.
 * Pass the same as inVol/inDir when there is no chain. */
static int RunExtract(short inVol, long inDir, ConstStr255Param name,
                      short outVol, long outDir,
                      short origVol, long origDir,
                      UncProgress *prog, int *entries, int *errors,
                      ExtractShape *shape)
{
    UncIO io;
    MemIO mem;
    FileIO fio;
    MacAlloc ma;
    UncAlloc al;
    MacSink sink;
    UncSink sk;
    UncOptions opt;
    short refNum;
    long fileSize;
    Ptr archiveBuf;
    OSErr err;
    int ret;
    SegHost *sh = NULL;         /* non-NULL: this file is one part of a set */
    Ptr segScratch = NULL;
    unsigned char famStem[64];
    short famStemLen = 0;
    int famSplit = 0, famZip = 0;
    UncFormat extractedAs = UNC_FORMAT_UNKNOWN;
#ifndef UNC_MAC_AUTOTEST
    UncPasswordSource passSrc;
    PassHost passHost;
    uint8_t mkeyBuf[8];
#endif

    *entries = *errors = 0;

    /* --- Open the archive and read from it as the engine asks. The file
     *     stays open for the whole extraction, including while output files
     *     are created on the same volume; UNC_AT_INTERLEAVE established that
     *     this is safe (see FileIO above). --- */
    err = MyOpenFork(inVol, inDir, name, fsRdPerm, 0, &refNum);
    if (err != noErr) return UNC_ERR_IO;
    fileSize = 0;
    GetEOF(refNum, &fileSize);
    if (fileSize <= 0) { FSClose(refNum); return UNC_ERR_FORMAT; }

    /* --- Is this one part of a segmented set? Decided from the header,
     *     before any of the whole-archive machinery below, because a
     *     segmented archive is not read through `io` at all: the parts
     *     are opened one at a time by the volume source. --- */
    {
        FileIO probe;
        UncIO pio;
        UncSegmentDesc desc;
        int segOK;
        probe.refNum = refNum;
        probe.size = (uint32_t)fileSize;
        probe.pos = 0;
        pio.ctx = &probe;
        pio.read = fio_read;
        pio.seek = fio_seek;
        pio.tell = fio_tell;
        pio.size = fio_size;
        /* unc_segment_describe, not unc_sniff: this runs on EVERY archive
         * the app opens, and a full sniff would re-walk a Compact Pro
         * index CRC that unc_extract is about to walk again — twice the
         * work on a 7 MHz machine, for a question one header answers. */
        {
            /* Decided by NAME first, and deliberately before the header
             * has a say: part 1 of a split .sit begins with "SIT!" and
             * would be read as the truncated archive it is a slice of.
             * The Linux CLI makes the same choice for the same reason
             * (DECISIONS.md 2026-08-10). A family of one is not a set,
             * so a lone Archive.001 falls through to the ordinary
             * reader. */
            short stemlen = PStemLen(name);
            if (stemlen > 0 && stemlen <= 63) {
                short i;
                for (i = 0; i < stemlen; i++) famStem[i] = name[i + 1];
                famStemLen = stemlen;
                famSplit = SplitPartOf(famStem, stemlen, name) >= 1;
                famZip = !famSplit &&
                         ZipFamPartOf(famStem, stemlen, name) != 0;
            }
        }
        segOK = unc_segment_describe(&pio, &desc) == UNC_OK;
        /* ...unless the file proves otherwise. A DiskDoubler `SPLT`
         * part carries its own index, count and identity, so a set
         * named Archive.dd.001 is joined as the scheme it declares:
         * the name rule above is for parts that declare nothing, and
         * folding 94-byte headers into a file would be silent and
         * wrong. The Linux CLI makes the same choice. */
        if (segOK && desc.scheme == UNC_FORMAT_DDSEG) {
            famSplit = 0;
            famZip = 0;
        }
        if (famSplit || famZip || segOK) {
            sh = (SegHost *)NewPtr((Size)sizeof(SegHost));
            segScratch = NewPtr((Size)unc_segment_scratch_size());
            if (sh == NULL || segScratch == NULL) {
                if (sh) DisposePtr((Ptr)sh);
                if (segScratch) DisposePtr(segScratch);
                FSClose(refNum);
                return UNC_ERR_MEM;
            }
            { long z; for (z = 0; z < (long)sizeof(SegHost); z++)
                          ((char *)sh)[z] = 0; }
            if (famSplit || famZip) {
                short i;
                Str63 lastName;
                for (i = 0; i < famStemLen; i++) sh->stem[i] = famStem[i];
                sh->stemlen = famStemLen;
                SegScanFamily(sh, inVol, inDir, famSplit, lastName);
                if (famZip) {
                    /* Only the ".zip" member carries the part count, so
                     * it has to be read before anything else can be. */
                    if (!lastName[0] ||
                        !SegDescribeLast(sh, inVol, inDir, lastName)) {
                        DisposePtr((Ptr)sh);
                        DisposePtr(segScratch);
                        FSClose(refNum);
                        return UNC_ERR_SEGMENTED;
                    }
                } else {
                    /* Nothing in a split says anything, so the whole
                     * descriptor is built here: the set is the
                     * consecutive run of NAME.NNN, the joined file is
                     * called NAME, and its length is the sum of the
                     * parts' — which is why every one is measured now
                     * rather than disk by disk. */
                    int p, run = 0;
                    uint32_t total = 0;
                    long z;
                    for (z = 0; z < (long)sizeof sh->desc; z++)
                        ((char *)&sh->desc)[z] = 0;
                    sh->desc.scheme = UNC_FORMAT_SPLIT;
                    sh->desc.part = 1;
                    sh->desc.head_len = 0;
                    for (i = 0; i < famStemLen && i < UNC_NAME_MAX; i++)
                        sh->desc.name[i] = famStem[i];
                    sh->desc.name[i] = 0;
                    sh->desc.name_len = (uint16_t)i;
                    while (run < kSegMaxKnown && sh->loc[run + 1].name[0])
                        run++;
                    if (run < 1 || run < sh->highest) {
                        /* A member numbered past the end of the run says
                         * the gap is a missing part, not the end. */
                        DisposePtr((Ptr)sh);
                        DisposePtr(segScratch);
                        FSClose(refNum);
                        return UNC_ERR_SEGMENTED;
                    }
                    for (p = 1; p <= run; p++) {
                        uint32_t len = SegPartLength(sh, p);
                        if (len == UNC_SIZE_UNKNOWN) { total = UNC_SIZE_UNKNOWN; break; }
                        total += len;
                    }
                    if (total == UNC_SIZE_UNKNOWN) {
                        DisposePtr((Ptr)sh);
                        DisposePtr(segScratch);
                        FSClose(refNum);
                        return UNC_ERR_SEGMENTED;
                    }
                    sh->desc.nparts = (uint16_t)run;
                    sh->desc.total = total;
                    sh->desc.data_size = total;
                }
            } else {
            sh->desc = desc;
            /* A `SPLT` set stores no name for the file it joins into.
             * The opened part's is all there is, minus the ".N" that
             * numbers it — for the output file, never for matching:
             * the parts are found by content like a StuffIt set's. */
            if (desc.scheme == UNC_FORMAT_DDSEG) {
                short n = name[0], d, i;
                if (n > UNC_NAME_MAX) n = UNC_NAME_MAX;
                d = n;
                while (d >= 1 && name[d] >= '0' && name[d] <= '9') d--;
                if (d < n && d >= 2 && name[d] == '.') n = (short)(d - 1);
                for (i = 0; i < n; i++) sh->desc.name[i] = name[i + 1];
                sh->desc.name[n] = 0;
                sh->desc.name_len = (uint16_t)n;
            }
            sh->tmpVol = outVol;
            sh->tmpDir = outDir;
            /* The file we were opened on is a part, at the number its
             * own header states — so opening part 3 of a set works. */
            SegRemember(sh, (int)sh->desc.part, inVol, inDir, name);
            SegScanDir(sh, inVol, inDir);
            /* A part that arrived wrapped was unwrapped into the OUTPUT
             * folder, so the rest of the set is not there: it is still
             * where the user left it. */
            if (origVol != inVol || origDir != inDir)
                SegScanDir(sh, origVol, origDir);
            /* Only now, and only if something is still missing, is it
             * worth taking envelopes off to look — which is how a real
             * download arrives, and also how a half-unstuffed one does.
             * A complete set opens nothing beside it. */
            if (sh->desc.scheme == UNC_FORMAT_SITSEG && !SegHaveAll(sh)) {
                if (origVol != inVol || origDir != inDir)
                    SegScanWrapped(sh, origVol, origDir, &al);
                SegScanWrapped(sh, inVol, inDir, &al);
            }
            /* A Compact Pro set opened anywhere but its last segment
             * does not yet know how many segments it has. */
            if (sh->desc.nparts == 0 &&
                sh->desc.scheme == UNC_FORMAT_CPTSEG) {
                SegFindLast(sh);
                if (sh->desc.nparts) {
                    /* With a count in hand the match rule is stricter —
                     * a middle segment must not carry an index and the
                     * last one must — so everything found under the
                     * looser one is looked at again. Two bytes of
                     * identity is not much to let a file in on. */
                    long z;
                    for (z = 0; z < (long)sizeof sh->loc; z++)
                        ((char *)sh->loc)[z] = 0;
                    SegScanDir(sh, inVol, inDir);
                }
            }
            }
        }
    }

#ifdef UNC_MAC_SLURP_ARCHIVE
    archiveBuf = NewPtr(fileSize);
    if (archiveBuf == NULL) { FSClose(refNum); return UNC_ERR_MEM; }

    SetFPos(refNum, fsFromStart, 0);
    {
        long remaining = fileSize;
        Ptr p = archiveBuf;
        OSErr rerr = noErr;
        while (remaining > 0) {
            long chunk = remaining;
            rerr = FSRead(refNum, &chunk, p);
            if (chunk > 0) { p += chunk; remaining -= chunk; }
            if (rerr != noErr) break;      /* eofErr or a real error */
        }
        FSClose(refNum);
        if (remaining != 0) { DisposePtr(archiveBuf); return UNC_ERR_IO; }
    }

    mem.data = (const uint8_t *)archiveBuf;
    mem.size = (uint32_t)fileSize;
    mem.pos = 0;
    io.ctx = &mem;
    io.read = xio_read;
    io.seek = xio_seek;
    io.tell = xio_tell;
    io.size = xio_size;
#else
    archiveBuf = NULL;
    fio.refNum = refNum;
    fio.size = (uint32_t)fileSize;
    fio.pos = 0;
    io.ctx = &fio;
    io.read = fio_read;
    io.seek = fio_seek;
    io.tell = fio_tell;
    io.size = fio_size;
#endif

    /* Budget the engine against the free heap. With the archive read straight
     * off disk there is no buffer to subtract first, so on the floor target
     * the engine now gets the archive's size back — which is what decided
     * which StuffIt 5 entries it could afford. */
    {
        long freenow = FreeMem();
        long reserve = freenow / 4;
        if (reserve > kMemReserveMax) reserve = kMemReserveMax;
        if (reserve < kMemReserveMin) reserve = kMemReserveMin;
#ifdef UNC_AT_BUDGET
        gFreeAtStart = freenow;
#endif
        ma.budget = freenow - reserve;
    }
    if (ma.budget < 32L * 1024) ma.budget = 32L * 1024;
    ma.initial = ma.budget;      /* for peak-usage = initial - lowmark */
#ifdef UNC_AT_BUDGET
    gBudget = ma.initial;
#endif
    ma.lowmark = ma.budget;
    al.ctx = &ma;
    al.alloc = mal_alloc;
    al.free = mal_free;

    sink.vRefNum = outVol;
    sink.rootDirID = outDir;
    sink.entries = sink.errors = sink.unsupported = 0;
    gUnsupported = 0;
    sink.fileCount = sink.dirCount = 0;
    sink.lastName[0] = 0;
    sink.lastDir = 0;
    sink.pr = NULL;
    sink.wrOSErr = noErr;
    /* gLastWriteErr, gShortBy and gShortPiece are NOT reset here. They
     * describe the whole operation the user asked for, and ExtractOne
     * calls this once per ENVELOPE LAYER — so a reset here would let the
     * last layer wipe what an earlier one recorded. ExtractOne clears
     * them once, before its loop. */
    sk.ctx = &sink;
    sk.begin_entry = sink_begin;
    sk.write = sink_write;
    sk.end_entry = sink_end;
    sk.comment = sink_comment;

    opt.list_only = 0;
    opt.test_only = 0;
    /* SpaceSaver's preset dictionary is Aladdin's and this application
     * does not carry one, so entries whose stream reaches into it fail
     * cleanly rather than decoding to something wrong (OPEN_ITEMS.md).
     * Set explicitly: this struct is filled field by field, so a field
     * nobody assigns is stack garbage. */
    opt.preset = NULL;
    opt.preset_len = 0;
    /* Encrypted entries. The password is asked for when one turns up,
     * not before — see MacAskPassword — and the 'MKey' resource is the
     * key material a StuffIt classic archive keeps outside its stream. */
    opt.password = NULL;
    opt.password_len = 0;
    opt.ask = NULL;
    opt.mkey = NULL;
#ifndef UNC_MAC_AUTOTEST
    {
        short i;
        passHost.hide = prog ? (WindowPtr)((Progress *)prog->ctx)->dlg : NULL;
        passHost.name[0] = name[0] > 63 ? 63 : name[0];
        for (i = 0; i < (short)passHost.name[0]; i++)
            passHost.name[i + 1] = name[i + 1];
        passSrc.ctx = &passHost;
        passSrc.ask = MacAskPassword;
        opt.ask = &passSrc;
        if (LoadMKey(inVol, inDir, name, mkeyBuf)) opt.mkey = mkeyBuf;
    }
#endif
    /* Fallback name for formats that store none (gzip, .Z). The contract in
     * macextract.h is "the archive filename minus its LAST extension", which
     * is what unar does and what cli/main.c passes; this used to pass the
     * whole name, so opening `foo.gz` on a Mac wrote a file called `foo.gz`
     * — colliding with the archive itself, hence `foo.gz~1` — where every
     * other implementation writes `foo`. Found 2026-08-02 by the Mac OS 9
     * harness, which compares output NAMES; the Mini vMac harness compares
     * CRCs and counts and so could not see it.
     *
     * A leading dot is not an extension (`.foo` stays `.foo`), matching the
     * `dot != base` test in the CLI. */
    opt.name_hint = name + 1;            /* Pascal string body */
    opt.name_hint_len = name[0];
    {
        int i;
        for (i = (int)name[0]; i > 1; i--) {
            if (name[i] == '.') { opt.name_hint_len = (uint16_t)(i - 1); break; }
        }
    }

    if (sh) {
        UncVolumeSource vs;
        /* Nothing else may hold the archive open: the parts are opened
         * one at a time, and this file is one of them. */
#ifdef UNC_MAC_SLURP_ARCHIVE
        DisposePtr(archiveBuf);
        archiveBuf = NULL;
#else
        FSClose(refNum);
#endif
        refNum = 0;
#ifndef UNC_MAC_AUTOTEST
        /* Only the interactive app puts a Progress behind prog->ctx; the
         * autotest's tick carries something else entirely. */
        sh->hide = prog ? ((Progress *)prog->ctx)->dlg : NULL;
#endif
        /* Optional members are the NULL ones, so this must start
         * zeroed (macextract.h). `size` stays NULL deliberately: this
         * host reads floppies, and answering it would mean sending the
         * user after disks to put a denominator on a progress bar. */
        {
            long z;
            for (z = 0; z < (long)sizeof vs; z++) ((char *)&vs)[z] = 0;
        }
        vs.ctx = sh;
        vs.need = seg_need;
        vs.release = seg_release;
        ret = unc_extract_segments(&sh->desc, &vs, segScratch, &sk, &al,
                                   prog, &opt);
        seg_release(sh, NULL);
        SegPeelClean(sh);
        DisposePtr((Ptr)sh);
        DisposePtr(segScratch);
    } else {
        /* Sniff and dispatch rather than calling unc_extract, which does
         * exactly this internally: same work, and the caller learns what
         * the layer was — which is what decides whether there is another
         * one under it. */
        extractedAs = unc_sniff(&io);
        /* SpaceSaver is the exception to the strip above: it compresses a
         * file IN PLACE and adds no extension, so the whole name is the
         * name and stripping one eats a real ".txt". cli/main.c has said
         * so since SpaceSaver went in; this shell had the unconditional
         * strip until 2026-08-28, when the Mac OS 9 tier was pointed at a
         * SpaceSaver specimen for the first time. The sniff has to come
         * first, which is why this is here rather than beside the strip. */
        if (extractedAs == UNC_FORMAT_SPACESAVER)
            opt.name_hint_len = name[0];
        ret = unc_extract_as(extractedAs, &io, &sk, &al, prog, &opt);
    }
    gPeakUsage = ma.initial - ma.lowmark;   /* engine heap high-water mark */

#ifdef UNC_MAC_SLURP_ARCHIVE
    if (archiveBuf) DisposePtr(archiveBuf);
#else
    if (refNum) FSClose(refNum);   /* held open for the whole extraction */
#endif
    FlushVol(NULL, outVol);    /* persist all output before returning */
    FlushVol(NULL, outVol);
    *entries = sink.entries;
    *errors = sink.errors;
    gUnsupported = sink.unsupported;
    if (shape) {
        shape->fileCount = sink.fileCount;
        shape->dirCount = sink.dirCount;
        shape->dirID = sink.lastDir;
        shape->fmt = sh ? sh->desc.scheme : extractedAs;
        BlockMoveData(sink.lastName, shape->name, sink.lastName[0] + 1);
    }
    return ret;
}
#endif

/* ================================================================== */
/* On-Mac autotest driver: no SFGetFile, no alerts. Finds the "Test"  */
/* floppy, extracts archive.sit into its root, and records the        */
/* outcome in a RESULT text file. The Linux harness then mounts the   */
/* image and diffs the extracted forks against the oracle manifest —  */
/* deterministic, no screenshots. Build with -DUNC_MAC_AUTOTEST.      */
/* ================================================================== */
#if !defined(UNC_SINK_TEST) && defined(UNC_MAC_AUTOTEST)

#define fsRtDirID 2L
#define nsvErr    (-35)

/* How many volumes the last FindVol walk saw. Reported in the failure grid:
 * "1" means only the boot disk ever mounted, which is a harness problem
 * (disk set, insertion), whereas "3" would mean the disks are all there and
 * the names are wrong. Without it the two look identical from the host. */
static int gATnvols;

/* Locate a mounted volume by name; return its real vRefNum. */
static OSErr FindVol(ConstStr255Param want, short *vref)
{
    HParamBlockRec pb;
    Str63 nm;
    short idx;
    for (idx = 1; idx < 128; idx++) {
        pb.volumeParam.ioCompletion = NULL;
        pb.volumeParam.ioNamePtr = nm;
        pb.volumeParam.ioVRefNum = 0;
        pb.volumeParam.ioVolIndex = idx;
        if (PBHGetVInfoSync(&pb) != noErr) { gATnvols = idx - 1; return nsvErr; }
        if (EqualString(nm, want, false, false)) {
            *vref = pb.volumeParam.ioVRefNum;
            return noErr;
        }
    }
    gATnvols = idx - 1;
    return nsvErr;
}

/* Mount whatever is sitting in the floppy drives.
 *
 * This application replaces the Finder as the boot shell, and that turns out
 * to matter: a disk inserted after startup is announced with a disk-inserted
 * event, but the volume is only mounted when SOMEBODY asks, and normally that
 * somebody is the Finder. With the Finder gone, the emulator's In and Out
 * images stay unmounted forever — measured, not assumed: the volume walk saw
 * exactly one volume (the boot disk) after 30 seconds of waiting.
 *
 * So ask, by drive number. Errors are ignored on purpose: an empty drive
 * answers nsDrvErr and an already-mounted one volOnLinErr, and neither is a
 * problem. */
static void MountAllDrives(void)
{
    ParamBlockRec pb;
    short drv;
    long z;
    for (drv = 1; drv <= 8; drv++) {
        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        pb.volumeParam.ioVRefNum = drv;      /* drive number, not a vRefNum */
        (void)PBMountVol(&pb);
    }
}

/* As FindVol, but mounts the drives first and waits for the volume to turn up.
 *
 * The wait is still needed on top of the mount: the application is the boot
 * shell, so it starts the instant the System is up, which can be before the
 * emulator has finished inserting all its images. */
#define kVolWaitTicks 1800L   /* 30 s of Mac time, i.e. many boots' worth */

static OSErr FindVolWait(ConstStr255Param want, short *vref)
{
    long deadline = TickCount() + kVolWaitTicks;
    for (;;) {
        MountAllDrives();
        if (FindVol(want, vref) == noErr) return noErr;
        if ((long)(TickCount() - deadline) >= 0) return nsvErr;
        SystemTask();
    }
}

/* CRC-32 (IEEE, reflected — the zlib/PNG polynomial), computed on the Mac
 * by reading a fork back through the File Manager. Comparing this against a
 * host-side CRC of the same fork tells whether a mismatch is the decoder
 * writing wrong bytes (on-Mac CRC already wrong) or the harness ferrying
 * them wrong (on-Mac CRC right, host CRC wrong). */
static uint32_t at_crc32_update(uint32_t crc, const uint8_t *p, long n)
{
    long i; int k;
    crc = ~crc;
    for (i = 0; i < n; i++) {
        crc ^= p[i];
        for (k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(crc & 1)));
    }
    return ~crc;
}

/* CRC-32 one fork of a file, reading it back through the File Manager.
 *
 * For the resource fork, bytes 16..127 are ZEROED before CRCing. That range
 * is the 112-byte "reserved for system use" area of the 256-byte resource
 * FILE header (Inside Macintosh: More Macintosh Toolbox, Resource Manager):
 *
 *     0..3     offset to resource data      12..15   length of resource map
 *     4..7     offset to resource map       16..127  reserved, SYSTEM     <-- masked
 *     8..11    length of resource data      128..255 reserved, APPLICATION
 *
 * The System 6 Resource Manager stamps session scratch into the system area
 * and no off-Mac tool reproduces it, so an unmasked CRC would make every
 * resource fork mismatch spuriously. Masking is safe because nothing points
 * into that range — resources are reached only via the offsets in bytes
 * 0..15 and the map. The application area at 128..255 is NOT masked: it
 * holds real content (THINK C's copyright notice, for one) and must still
 * match byte-exact. tools/vmac_check.py masks exactly the same range on the
 * host side. Returns 0 and sets *crc/*len; -1 on open failure. */
#define kRsrcSysReservedBeg  16    /* first byte of the system-reserved area */
#define kRsrcSysReservedEnd  128   /* one past its last byte (112 bytes)     */

static int at_fork_crc(short vol, long dir, ConstStr255Param name,
                       int rsrc, uint32_t *crc, long *len)
{
    short ref;
    OSErr err;
    static char buf[4096];
    uint32_t c = 0;
    long total = 0;

    err = MyOpenFork(vol, dir, name, fsRdPerm, rsrc, &ref);
    if (err != noErr) return -1;
    SetFPos(ref, fsFromStart, 0);
    for (;;) {
        long cnt = (long)sizeof buf;
        OSErr rerr = FSRead(ref, &cnt, buf);
        if (cnt > 0) {
            if (rsrc && total < kRsrcSysReservedEnd) {
                long i;
                for (i = 0; i < cnt; i++) {
                    long off = total + i;
                    if (off >= kRsrcSysReservedBeg && off < kRsrcSysReservedEnd)
                        buf[i] = 0;
                }
            }
            c = at_crc32_update(c, (const uint8_t *)buf, cnt);
            total += cnt;
        }
        if (rerr != noErr || cnt <= 0) break;   /* eofErr ends it */
    }
    FSClose(ref);
    *crc = c;
    *len = total;
    return 0;
}

/* ---- On-screen result channel -------------------------------------------
 * Mini vMac's write-back of a mounted disk image to its host backing file is
 * lazy and PARTIAL — it reliably commits neither both forks of a file nor
 * small trailing files, so the host cannot read results off the Out volume.
 * The screen, being the framebuffer, is captured EXACTLY by a screenshot.
 * So the app paints its results as a black/white bit grid the host decodes.
 * Three solid calibration squares at known screen positions let the host map
 * Mac-screen coords to screenshot pixels regardless of the emulator window
 * offset/scale. Bit order: 16-bit sync 0xA55A (MSB first), then each 32-bit
 * value MSB first, row-major across AT_GRID_COLS columns. */
#define AT_GRID_COLS  16
#define AT_CELL_X0    96     /* Mac-screen px of the grid's first cell */
#define AT_CELL_Y0    72
#define AT_CELL_PITCH 14
#define AT_CELL_FILL  10

/* Fill a screen rect black(1) or white(0) by poking the framebuffer bits
 * directly. Mac 1bpp bitmap: bit set = black. No QuickDraw, no allocation. */
static void at_fill(Ptr base, long rb, int x0, int y0, int x1, int y1, int black)
{
    int x, y;
    for (y = y0; y < y1; y++) {
        unsigned char *row = (unsigned char *)base + (long)y * rb;
        for (x = x0; x < x1; x++) {
            unsigned char m = (unsigned char)(0x80 >> (x & 7));
            if (black) row[x >> 3] |= m;
            else       row[x >> 3] &= (unsigned char)~m;
        }
    }
}

static void at_cell(Ptr base, long rb, int idx, int bit)
{
    int col = idx % AT_GRID_COLS, row = idx / AT_GRID_COLS;
    int x = AT_CELL_X0 + col * AT_CELL_PITCH;
    int y = AT_CELL_Y0 + row * AT_CELL_PITCH;
    if (bit) at_fill(base, rb, x, y, x + AT_CELL_FILL, y + AT_CELL_FILL, 1);
}

static void at_report(const uint32_t *vals, int nvals)
{
    /* Write STRAIGHT to the screen framebuffer: it needs zero allocation,
     * cannot fail, and keeps reporting when the machine is in a state where
     * the Toolbox cannot be trusted — which is exactly when the harness most
     * needs an answer.
     *
     * This used to say QuickDraw "reliably bombs when called after the File
     * Manager has run". That was never reduced to a reproduction, and it is
     * WRONG: tools/quickdraw-repro/ runs NewWindow/EraseRect/DrawString,
     * GetNewDialog and an EraseRect on the WMgr port immediately after 64 KB
     * of File Manager writes, on System 6.0.8 / Mac Plus, in twelve
     * configurations, and every call succeeds with MemError() == 0. */
    Ptr base = qd.screenBits.baseAddr;
    long rb = (long)(qd.screenBits.rowBytes & 0x3FFF);
    long h = qd.screenBits.bounds.bottom - qd.screenBits.bounds.top;
    long k, n;
    int i, b, idx = 0;

#ifndef UNC_AT_NOHIDECURSOR
    HideCursor();      /* stop the cursor's save/restore from stamping its old
                          (desktop-pattern) background back over the grid.
                          UNC_AT_NOHIDECURSOR builds without it so the claim
                          can be tested instead of inherited. */
#endif
    n = h * rb;                                 /* erase whole screen to white */
    for (k = 0; k < n; k++) ((unsigned char *)base)[k] = 0;

    at_fill(base, rb, 24, 32, 48, 56, 1);       /* calibration TL (36,44)  */
    at_fill(base, rb, 464, 32, 488, 56, 1);     /* calibration TR (476,44) */
    at_fill(base, rb, 24, 288, 48, 312, 1);     /* calibration BL (36,300) */

    /* Values first, sync word LAST — same layout, deliberate order.
     *
     * The sync word is the only thing that tells the host a grid is
     * complete, and painting it first meant a HALF-painted grid decoded
     * cleanly: the screen is erased to white above, so cells not yet
     * reached read as zero, and the host saw a valid sync, a plausible
     * ret and a truncated tail. That is the false FAIL of 2026-08-28 —
     * derived-PackIt.pit reported totalRsrcLen 0x00008000 where the
     * truth is 0x0000DB05, which is exactly that value with painting
     * stopped after its 17th bit, and peakBytes 0 because painting
     * never reached it.
     *
     * Painted last, the sync is a completion certificate: a screenshot
     * taken mid-paint has no sync, decode_grid.py rejects it, and the
     * host simply looks again. */
    idx = 16;
    for (i = 0; i < nvals; i++)
        for (b = 31; b >= 0; b--)
            at_cell(base, rb, idx++, (int)((vals[i] >> b) & 1u));
    idx = 0;
    for (b = 15; b >= 0; b--) at_cell(base, rb, idx++, (0xA55A >> b) & 1);
}

/* Idle so the host can screenshot the framebuffer, then kill the emulator. */
static void at_idle(void)
{
    for (;;) {
        EventRecord ev;
        if (gHasWNE) WaitNextEvent(everyEvent, &ev, 60, NULL);
        else SystemTask();
    }
}

/* Statuses that are NOT engine results, reported in vals[1] where a finished
 * run reports the engine's return code. They sit far outside the engine's
 * UNC_ERR_* range — a handful of small negatives — so the host can never
 * mistake one for the other.
 *
 * kAtRunning is painted before any work starts, and matters more than it
 * looks: without it a host screenshot showing no grid is ambiguous between
 * "the application never launched", "it bombed" and "it is still decoding",
 * and the harness can only report a timeout and leave the reader guessing.
 * With it, a decodable grid means the app is alive. */
#define kAtRunning   (-1000)   /* alive, extraction not finished yet */
#define kAtNoInVol   (-1001)   /* no volume named "In" is mounted    */
#define kAtNoOutVol  (-1002)   /* no volume named "Out" is mounted   */

/* ---- the same report, as a FILE ------------------------------------
 *
 * at_report() paints 1bpp pixels straight at the framebuffer. On a Mac Plus
 * that is the best channel there is — no allocation, cannot fail, works when
 * the Toolbox cannot be trusted. On Mac OS 9 it is useless: the screen is
 * 32-bit colour, so the bits land as noise and the host has nothing to
 * decode. That is the reason HFS+ stayed untested long after the application
 * itself ran there — the output volume can be anything, but the ANSWER had to
 * come back through a screen the host could read.
 *
 * So the same values also go to a file, on a volume chosen by the caller —
 * in practice the plain-HFS input volume, which the host can read with
 * hfsutils however exotic the OUTPUT volume is.
 *
 * The file carries the output NAMES as well as the aggregate, because the
 * aggregate is exactly what cannot answer a question about names, and names
 * are most of what changes on HFS+ (see TESTING.md on what each layer is
 * blind to).
 *
 * Format — big-endian, written and read byte-wise, nothing aligned:
 *
 *     0   4   'UNCR'
 *     4   4   version, 1
 *     8   4   nvals
 *     12  4*n the values at_report would paint
 *     ..  4   number of recorded output files
 *     ..      per file: 4 dirID, 1 name length, that many MacRoman bytes
 */
static short gATreportVol;         /* 0 = no file report wanted */

static void at_put32(unsigned char *p, uint32_t v)
{
    p[0] = (unsigned char)(v >> 24);
    p[1] = (unsigned char)(v >> 16);
    p[2] = (unsigned char)(v >> 8);
    p[3] = (unsigned char)v;
}

static void at_wr(short refNum, const void *p, long n)
{
    long count = n;
    (void)FSWrite(refNum, &count, p);
}

static void at_report_file(const uint32_t *vals, int nvals)
{
    unsigned char w[4];
    short refNum;
    int i;

    if (gATreportVol == 0) return;
    /* Written in small pieces rather than built in one buffer: 128 records of
     * a Str63 is over 8 KB, and this application runs inside a 4 KB call-depth
     * budget — see kStackBump, which raises the stack to 32 KB, and
     * FORMATS.md's `Stack` for what the engine actually reaches. */
    (void)MyHDelete(gATreportVol, fsRtDirID, "\preport");
    if (MyHCreate(gATreportVol, fsRtDirID, "\preport") != noErr) return;
    if (MyOpenFork(gATreportVol, fsRtDirID, "\preport", fsWrPerm, 0,
                   &refNum) != noErr) return;

    at_put32(w, 0x554E4352UL); at_wr(refNum, w, 4);       /* 'UNCR' */
    at_put32(w, 1UL);          at_wr(refNum, w, 4);
    at_put32(w, (uint32_t)nvals); at_wr(refNum, w, 4);
    for (i = 0; i < nvals; i++) {
        at_put32(w, vals[i]);
        at_wr(refNum, w, 4);
    }
    at_put32(w, (uint32_t)gATnrec);
    at_wr(refNum, w, 4);
    for (i = 0; i < gATnrec; i++) {
        at_put32(w, (uint32_t)gATrec[i].dir);
        at_wr(refNum, w, 4);
        at_wr(refNum, gATrec[i].name, (long)gATrec[i].name[0] + 1);
    }
    FSClose(refNum);
    FlushVol(NULL, gATreportVol);      /* the host reads this off the image */
}

static void at_status(int code)
{
    uint32_t vals[8];
    int i;
    for (i = 0; i < 8; i++) vals[i] = 0;
    vals[1] = (uint32_t)code;
    at_report(vals, 8);
}

#ifdef UNC_AT_CANCEL
/* Abort as soon as ONE entry has completed, so the cancel lands inside a
 * later entry — the case that matters now that writes stream straight to
 * disk, because the in-flight file already exists and already has bytes in
 * it. (Aborting before any data arrives was the only shape the old
 * stage-then-write path could produce, and it proves much less.) */
static int at_cancel_tick(void *ctx, uint32_t done, uint32_t total)
{
    (void)ctx; (void)done; (void)total;
    return gATnrec >= 1 ? 0 : 1;      /* 0 = stop */
}

#endif  /* UNC_AT_CANCEL */

#if defined(UNC_AT_CANCEL) || defined(UNC_AT_WD)
/* Count the items directly in one directory. `dirs` matters as a guard: this
 * walks one level only, so a non-zero directory count means the file count is
 * partial and the host must not draw conclusions from it. */
static void at_count_dir(short vol, long dir, int *files, int *dirs)
{
    CInfoPBRec pb;
    Str63 nm;
    short idx;
    long z;
    *files = *dirs = 0;
    for (idx = 1; idx < 512; idx++) {
        for (z = 0; z < (long)sizeof pb; z++) ((char *)&pb)[z] = 0;
        pb.hFileInfo.ioNamePtr = nm;
        pb.hFileInfo.ioVRefNum = vol;
        pb.hFileInfo.ioDirID = dir;
        pb.hFileInfo.ioFDirIndex = idx;
        if (PBGetCatInfoSync(&pb) != noErr) return;   /* past the last item */
        if (pb.hFileInfo.ioFlAttrib & ioDirMask) (*dirs)++;
        else                                     (*files)++;
    }
}
#endif

#ifdef UNC_AT_PROGRESS
/* Paint the engine's progress into the result grid as it goes, so a run that
 * never finishes can still be interrogated: screenshot it at intervals and
 * see whether `done` is advancing, crawling, or stopped, and at what byte.
 *
 * This exists for one fixture. macburger-helper.hqx (306 KB BinHex) has never
 * completed at 1x, on an idle host, with the CRC read-back disabled — while a
 * 304 KB MacBinary and a 278 KB StuffIt both extract fine, and the same
 * archive is among the CHEAPEST fixtures per byte off-Mac. Two confident
 * explanations for it have already been wrong (host contention, then the
 * read-back), so this measures instead of guessing: the callback already fires
 * every 8-16 KB of input, which is all the resolution needed to tell "slow"
 * from "stuck". */
/* THE INSTRUMENT MUST NOT PERTURB THE MEASUREMENT. at_report erases the whole
 * 21,888-byte framebuffer a byte at a time and repaints 272 cells, which costs
 * about 57 ms on a 7 MHz 68000. That was invisible while the engine ticked
 * every 8 KB of INPUT — `derived-a2basic.dmg.sit` reported 41 times in a whole
 * run. On 2026-08-07 Arsenic started reporting every 256 bytes of OUTPUT so
 * the Mac's progress bar and Cancel button would work, which took the same run
 * to 801 reports and made this harness 8.6% slower: the 4 MB 1x figure went
 * 537 s -> 583 s with no change to the decoder at all.
 *
 * So the autotest grid is rate-limited here rather than at the source. Five
 * seconds is far finer than run.py's 5 s poll needs and keeps the overhead
 * near 1%. The engine's own tick rate is left alone: it is what makes the
 * shipped UI responsive, and the shipped UI redraws a small bar, not this. */
#define kAtReportTicks 300      /* 60ths of a second */

static long gATlastReport;      /* TickCount of the last progress grid */

static int at_prog_tick(void *ctx, uint32_t done, uint32_t total)
{
    uint32_t vals[8];
    int i;
    long now = TickCount();
    (void)ctx;
    if (gATlastReport != 0 && now - gATlastReport < kAtReportTicks) return 1;
    gATlastReport = now;
    for (i = 0; i < 8; i++) vals[i] = 0;
    vals[0] = done;                      /* input bytes consumed so far   */
    vals[1] = (uint32_t)kAtRunning;      /* still working — not a result  */
    vals[2] = total;                     /* input bytes expected          */
    vals[7] = (uint32_t)gPeakUsage;
    at_report(vals, 8);
    return 1;                            /* keep going */
}
#endif

static void at_fail(int code)
{
    uint32_t vals[8];
    int i;
    for (i = 0; i < 8; i++) vals[i] = 0;
    vals[0] = (uint32_t)gATnvols;    /* how many volumes were actually mounted */
    vals[1] = (uint32_t)code;
    at_report(vals, 8);
    at_report_file(vals, 8);
    at_idle();
}

int main(void)
{
    short inVol, outVol;
    int ret, entries, errors;

    SetApplLimit((Ptr)((long)LMGetApplLimit() - kStackBump));
    MaxApplZone();
    { int i; for (i = 0; i < 12; i++) MoreMasters(); }

    InitGraf(&qd.thePort);
    InitFonts();
    InitWindows();
    InitMenus();
    TEInit();
    InitDialogs(NULL);
    InitCursor();
    FlushEvents(everyEvent, 0);
    gHasWNE = TrapAvailable(_WaitNextEvent);

    at_status(kAtRunning);   /* "I am alive" — see the kAt* codes above */

    /* Input archive is on the "In" volume; extract onto a SEPARATE "Out"
     * volume. A missing volume used to spin here forever, which on the host
     * side is indistinguishable from a slow extraction or a bombed app — the
     * harness would just time out and blame the engine. Report it instead:
     * the grid is the only channel off this machine, so a setup failure has
     * to travel down it too. */
    if (FindVolWait("\pIn", &inVol) != noErr)   at_fail(kAtNoInVol);

    /* The file report goes to the INPUT volume, deliberately. It is the one
     * the harness built, so the harness knows it can read it; the output
     * volume is whatever is under test, and on the Mac OS 9 HFS+ run that is
     * a volume no tool on the host can open. Set before "Out" is looked up,
     * so a missing output volume reports itself down this channel too. */
    gATreportVol = inVol;

    if (FindVolWait("\pOut", &outVol) != noErr) at_fail(kAtNoOutVol);

#ifdef UNC_AT_SAMEVOL
    /* Extract onto the volume the archive is ON, which is what the
     * interactive application actually does — it writes next to the archive —
     * and what no autotest run has ever done, because this harness has always
     * had a separate "Out" volume. That difference is exactly where the
     * withdrawn "interleaving reads with writes on ONE volume corrupts the
     * read" claim lived, so with the archive now read from the file rather
     * than slurped into RAM, the same-volume case has to be shown byte-exact
     * rather than assumed. Everything else — the read-back CRC of both forks,
     * the grid — is unchanged. */
    outVol = inVol;
#endif

    gATrecVol = outVol;   /* sink records each output file here (see below) */

#ifdef UNC_AT_CANCEL
    /* Cancel-cleanup mode: abort the extraction and check that the entry that
     * was in flight left NOTHING behind on the volume. See at_cancel_tick. */
    {
        UncProgress prog;
        int files = 0, dirs = 0;
        uint32_t vals[8];
        int i;
        prog.ctx = NULL;
        prog.tick = at_cancel_tick;
        ret = RunExtract(inVol, fsRtDirID, "\parchive.sit",
                         outVol, fsRtDirID, inVol, fsRtDirID,
                         &prog, &entries, &errors, NULL);
        at_count_dir(outVol, fsRtDirID, &files, &dirs);
        for (i = 0; i < 8; i++) vals[i] = 0;
        vals[0] = (uint32_t)gATnrec;   /* entries that completed successfully */
        vals[1] = (uint32_t)ret;       /* expect UNC_ERR_ABORTED (-8)         */
        vals[2] = (uint32_t)files;     /* files actually on the Out volume    */
        vals[3] = (uint32_t)dirs;      /* must be 0, or the count is partial  */
        vals[7] = (uint32_t)gPeakUsage;
        at_report(vals, 8);
        at_report_file(vals, 8);
        at_idle();
    }
#endif

#ifdef UNC_AT_INTERLEAVE
    /* Does reading a file while CREATING files on the same volume corrupt the
     * read?
     *
     * DECISIONS.md has claimed since M10 that it does — "interleaving File
     * Manager reads of the input with writes to output files on the same
     * volume makes the input reads return zeros" — and that claim is why
     * RunExtract() slurps the entire archive into RAM with one NewPtr before
     * the engine is given any budget at all. On the 1 MB floor target that
     * buffer is subtracted from the engine's budget first, which is why which
     * StuffIt 5 fixtures fail there depends on how big the ARCHIVE is rather
     * than on what it contains.
     *
     * It has never been reduced to a reproduction, and it is suspect for a
     * specific reason: the bullet immediately after it in the same list —
     * "deep writes from the decode callback corrupt the HFS volume" — comes
     * from the same investigation and has already been WITHDRAWN, because it
     * dates from the period when every File Manager open was silently failing
     * (BLOCKERS.md) and did not survive re-testing. "Reads start returning
     * zeros" is exactly what that confound looks like.
     *
     * So: read the same file twice on the same volume and compare.
     *
     *   pass A   read it end to end, nothing else happening   -> crcA
     *   pass B   read it in chunks, creating and writing a NEW
     *            file on that same volume between every chunk  -> crcB
     *
     * crcA == crcB and the same byte count means the interleave is harmless
     * and the RAM slurp is buying nothing. Different means the claim is real
     * and finally has a repro. Either way it stops being a hypothesis. */
    {
        static char rbuf[4096];
        uint32_t crcA = 0, crcB = 0, crcC = 0;
        long lenA = 0, lenB = 0, lenC = 0;
        int rounds = 0;
        OSErr rerrA = noErr, rerrB = noErr, werr = noErr;
        short ref;
        uint32_t vals[8];
        int i;

        for (i = 0; i < 8; i++) vals[i] = 0;

        /* Pass A: the control. Nothing touches the volume while it runs. */
        if (MyOpenFork(inVol, fsRtDirID, "\parchive.sit", fsRdPerm, 0,
                       &ref) == noErr) {
            for (;;) {
                long cnt = (long)sizeof rbuf;
                rerrA = FSRead(ref, &cnt, rbuf);
                if (cnt > 0) {
                    crcA = at_crc32_update(crcA, (const uint8_t *)rbuf, cnt);
                    lenA += cnt;
                }
                if (rerrA != noErr || cnt <= 0) break;
            }
            FSClose(ref);
        }

        /* Pass B: the same read, with catalog-changing writes in between.
         * A fresh file every round, on the volume being read from — the
         * shape an extraction has when output lands beside the archive. */
        if (MyOpenFork(inVol, fsRtDirID, "\parchive.sit", fsRdPerm, 0,
                       &ref) == noErr) {
            for (;;) {
                long cnt = (long)sizeof rbuf;
                Str63 nm;
                short oref;
                rerrB = FSRead(ref, &cnt, rbuf);
                if (cnt > 0) {
                    crcB = at_crc32_update(crcB, (const uint8_t *)rbuf, cnt);
                    lenB += cnt;
                }
                if (rerrB != noErr || cnt <= 0) break;

                nm[0] = 5;
                nm[1] = 'i'; nm[2] = 'l';
                nm[3] = (unsigned char)('0' + (rounds / 100) % 10);
                nm[4] = (unsigned char)('0' + (rounds / 10) % 10);
                nm[5] = (unsigned char)('0' + rounds % 10);
                (void)MyHDelete(inVol, fsRtDirID, nm);
                if (MyHCreate(inVol, fsRtDirID, nm) == noErr &&
                    MyOpenFork(inVol, fsRtDirID, nm, fsWrPerm, 0,
                               &oref) == noErr) {
                    long wn = 512;
                    OSErr e2 = FSWrite(oref, &wn, rbuf);
                    if (e2 != noErr && werr == noErr) werr = e2;
                    FSClose(oref);
                } else if (werr == noErr) {
                    werr = ioErr;
                }
                rounds++;
            }
            FSClose(ref);
        }

        /* Pass C: the shape a replacement would actually have. A file-backed
         * UncIO does not read sequentially — it seeks, because the engine
         * walks indexes and forks in whatever order the container demands. So
         * position explicitly with SetFPos before every read, still creating
         * files on the same volume in between. If a "file mark" were what the
         * interleave disturbs, this is the case that would either suffer from
         * it or be immune to it, and either answer is worth having before
         * writing the replacement. */
        if (MyOpenFork(inVol, fsRtDirID, "\parchive.sit", fsRdPerm, 0,
                       &ref) == noErr) {
            long pos = 0;
            for (;;) {
                long cnt = (long)sizeof rbuf;
                Str63 nm;
                short oref;
                if (SetFPos(ref, fsFromStart, pos) != noErr) break;
                if (FSRead(ref, &cnt, rbuf) != noErr && cnt <= 0) break;
                if (cnt <= 0) break;
                crcC = at_crc32_update(crcC, (const uint8_t *)rbuf, cnt);
                lenC += cnt;
                pos += cnt;

                nm[0] = 5;
                nm[1] = 's'; nm[2] = 'k';
                nm[3] = (unsigned char)('0' + (lenC / 40960) % 10);
                nm[4] = (unsigned char)('0' + (lenC / 4096) % 10);
                nm[5] = (unsigned char)('0' + (lenC / 409) % 10);
                (void)MyHDelete(inVol, fsRtDirID, nm);
                if (MyHCreate(inVol, fsRtDirID, nm) == noErr &&
                    MyOpenFork(inVol, fsRtDirID, nm, fsWrPerm, 0,
                               &oref) == noErr) {
                    long wn = 512;
                    (void)FSWrite(oref, &wn, rbuf);
                    FSClose(oref);
                }
            }
            FSClose(ref);
        }

        vals[0] = (uint32_t)lenA;        /* bytes read with nothing else going on */
        vals[1] = 0;                     /* not an engine run; keep out of AT_* range */
        vals[2] = (uint32_t)lenB;        /* bytes read while writing the same volume */
        vals[3] = crcA;
        vals[4] = crcB;
        vals[5] = (uint32_t)(((uint32_t)(uint16_t)werr << 16) |
                             (uint32_t)(rounds & 0xFFFF));
        vals[6] = crcC;                  /* same, but seeking before every read */
        vals[7] = (uint32_t)lenC;
        (void)rerrA; (void)rerrB;
        at_report(vals, 8);
        at_report_file(vals, 8);
        at_idle();
    }
#endif

#ifdef UNC_AT_WD
    /* Where does the output land when the caller passes a WORKING DIRECTORY?
     *
     * This is the shape the interactive application actually uses: SFGetFile
     * hands back `SFReply.vRefNum`, which on System 7 and later is a working
     * directory reference rather than a plain volume refNum, and the app
     * passes it to the File Manager with dirID 0. OPEN_ITEMS.md has carried
     * that as untested code since M10, and it could not be tested by any
     * earlier harness here: every one of them extracted into a volume ROOT,
     * where the working directory and the root are the same directory and a
     * mistake has nowhere to show itself.
     *
     * So make a real working directory over a real subfolder with PBOpenWD —
     * no Finder, no Standard File, no screen coordinates — extract through it,
     * and count what landed where. The files belong in the folder; the root
     * must hold nothing but the folder itself. */
    {
        WDPBRec wpb;
        Str63 folder;
        long z, dirID = 0;
        short wdRef = 0;
        OSErr derr, werr;
        int rootFiles = 0, rootDirs = 0, subFiles = 0, subDirs = 0;
        uint32_t vals[8];
        int i;

        for (i = 0; i < 8; i++) vals[i] = 0;
        folder[0] = 6;
        folder[1] = 'W'; folder[2] = 'D'; folder[3] = 'T';
        folder[4] = 'e'; folder[5] = 's'; folder[6] = 't';
        derr = MyDirCreate(outVol, fsRtDirID, folder, &dirID);

        for (z = 0; z < (long)sizeof wpb; z++) ((char *)&wpb)[z] = 0;
        wpb.ioNamePtr  = NULL;
        wpb.ioVRefNum  = outVol;
        wpb.ioWDDirID  = dirID;
        wpb.ioWDProcID = 0x756E6331L;         /* 'unc1', any distinct signature */
        werr = PBOpenWDSync(&wpb);
        wdRef = wpb.ioVRefNum;                /* the WD refNum, as SFGetFile returns */

        /* dirID 0 with a working-directory refNum: exactly ExtractOne(). */
        ret = RunExtract(inVol, fsRtDirID, "\parchive.sit",
                         wdRef, 0, inVol, fsRtDirID,
                         NULL, &entries, &errors, NULL);

        at_count_dir(outVol, fsRtDirID, &rootFiles, &rootDirs);
        at_count_dir(outVol, dirID, &subFiles, &subDirs);

        vals[0] = (uint32_t)entries;      /* entries the sink reported      */
        vals[1] = (uint32_t)ret;
        vals[2] = (uint32_t)errors;
        vals[3] = (uint32_t)rootFiles;    /* MUST be 0 — output is not here */
        vals[4] = (uint32_t)subFiles;     /* MUST equal entries             */
        vals[5] = (uint32_t)(short)wdRef;
        vals[6] = (uint32_t)((derr << 16) | (werr & 0xFFFF));
        vals[7] = (uint32_t)gPeakUsage;
        at_report(vals, 8);
        at_report_file(vals, 8);
        at_idle();
    }
#endif

#ifdef UNC_AT_PROGRESS
    {
        UncProgress prog;
        prog.ctx = NULL;
        prog.tick = at_prog_tick;
        ret = RunExtract(inVol, fsRtDirID, "\parchive.sit",
                         outVol, fsRtDirID, inVol, fsRtDirID,
                         &prog, &entries, &errors, NULL);
    }
#else
    ret = RunExtract(inVol, fsRtDirID, "\parchive.sit",
                     outVol, fsRtDirID, inVol, fsRtDirID,
                     NULL, &entries, &errors, NULL);
#endif

    /* Read every extracted file's forks back through the real File Manager,
     * CRC-32 each, and aggregate into an ORDER-INDEPENDENT summary: file
     * count, summed data-fork CRC + total bytes, summed resource-fork CRC
     * (reserved header masked) + total bytes, and the engine's peak heap.
     * The host recomputes the same eight numbers from the oracle and
     * compares. Summing per-file CRCs scales to any file count within one
     * fixed-size on-screen grid; a single file makes the sums its own CRCs. */
    {
        uint32_t sumDataCRC = 0, sumRsrcCRC = 0;
        long totalDataLen = 0, totalRsrcLen = 0;
        uint32_t vals[8];
        int e;
        for (e = 0; e < gATnrec; e++) {
            uint32_t dc = 0, rc = 0; long dl = 0, rl = 0;
#ifndef UNC_AT_NOCRC   /* skip the read-back to isolate write vs read crashes */
            at_fork_crc(outVol, gATrec[e].dir, gATrec[e].name, 0, &dc, &dl);
            at_fork_crc(outVol, gATrec[e].dir, gATrec[e].name, 1, &rc, &rl);
#endif
            sumDataCRC += dc; totalDataLen += dl;
            sumRsrcCRC += rc; totalRsrcLen += rl;
        }
        vals[0] = (uint32_t)gATnrec;
        vals[1] = (uint32_t)ret;
        vals[2] = (uint32_t)errors;
        vals[3] = sumDataCRC;
        vals[4] = (uint32_t)totalDataLen;
        vals[5] = sumRsrcCRC;
        vals[6] = (uint32_t)totalRsrcLen;
        vals[7] = (uint32_t)gPeakUsage;
#ifdef UNC_AT_BUDGET
        /* Overwrite the two length slots — same trick UNC_AT_META uses.
         * vals[7] still carries peak, so the three numbers that decide a
         * refusal (free, allowed, used) are on screen together. */
        vals[0] = (uint32_t)gSnapAddr[0];  /* largest live block, by address */
        vals[1] = (uint32_t)gSnapAddr[1];
        vals[3] = (uint32_t)gSnapAddr[2];
        vals[4] = (uint32_t)gFreeAtStart;
        vals[2] = (uint32_t)gRefusedMaxBlk;
        vals[5] = (uint32_t)gRefusedWhy;
        vals[6] = (uint32_t)gBudget;
        vals[4] = (uint32_t)gZoneLo;       /* application zone bottom */
        vals[6] = (uint32_t)gZoneHi;       /* ApplLimit                */
        vals[7] = (uint32_t)gSnapAddr[3];
#ifdef UNC_AT_HANDLES
        vals[4] = (uint32_t)gMoveBefore;   /* MaxBlock before MoveHHi */
        vals[6] = (uint32_t)gMoveAfter;    /* MaxBlock after  MoveHHi */
#endif
#endif
#ifdef UNC_AT_META
        /* E2E "launches by double-click" check: overwrite errors/CRC slots with
         * the first file's on-Mac Finder info — should be the archive's
         * type/creator with the inited bit (0x0100) CLEARED, which is exactly
         * what makes the Finder treat an extracted APPL as launchable.
         * "First" is the first file the sink WROTE, so for an archive that
         * carries a comment that is the 'TEXT'/'ttxt' Comments document and
         * not an entry at all. No fixture used with UNC_AT_META has one; if
         * one ever does, this reads the wrong file rather than failing. */
        if (gATnrec > 0) {
            CInfoPBRec pb; Str63 nm;
            BlockMoveData(gATrec[0].name, nm, gATrec[0].name[0] + 1);
            pb.hFileInfo.ioNamePtr = nm;
            pb.hFileInfo.ioVRefNum = outVol;
            pb.hFileInfo.ioDirID = gATrec[0].dir;
            pb.hFileInfo.ioFDirIndex = 0;
            if (PBGetCatInfoSync(&pb) == noErr) {
                vals[2] = (uint32_t)pb.hFileInfo.ioFlFndrInfo.fdType;
                vals[3] = (uint32_t)pb.hFileInfo.ioFlFndrInfo.fdCreator;
                vals[4] = (uint32_t)(uint16_t)pb.hFileInfo.ioFlFndrInfo.fdFlags;
            }
        }
#endif
        at_report(vals, 8);
        at_report_file(vals, 8);
    }
    (void)entries;

    /* Idle forever. The host reads the result off the SCREEN (a screenshot),
     * not the disk — no write-back needed, so the emulator can just be
     * killed once the grid has been captured. */
    at_idle();
    return 0;
}

#endif /* UNC_MAC_AUTOTEST */

/* ================================================================== */
/* Interactive app: SFGetFile loop + progress dialog + result alerts. */
/* ================================================================== */
#if !defined(UNC_SINK_TEST) && !defined(UNC_MAC_AUTOTEST)

static void ShowNote(short alrtID, const unsigned char *msg)
{
    ParamText(msg, "\p", "\p", "\p");
    NoteAlert(alrtID, NULL);
}

/* ------------------------------------------------------------------ */
/* The end-of-run report                                              */
/*                                                                    */
/* A run that had something to say about individual entries ends in   */
/* this box instead of the one-line alert: the names that changed and */
/* the entries that failed, one line each, and the outcome LAST — so  */
/* "Extraction complete" still has the last word, with what it cost   */
/* above it rather than lost.                                         */
/*                                                                    */
/* A run with nothing to report still ends in the alert. A list box   */
/* holding one line, behind a button the user must find before the    */
/* familiar one, would be a worse answer to the common case.          */
/*                                                                    */
/* The list is drawn rather than built out of TextEdit: the lines are */
/* already Pascal strings in a fixed pool, nothing here is editable   */
/* or selectable, and a TERec would put a second copy of the text in  */
/* a heap the engine has just finished stretching.                    */
/* ------------------------------------------------------------------ */

#define kReportDLOG   133
#define kRepOKItem    1
#define kRepSaveItem  2
#define kRepListItem  3
#define kRepRingItem  4
#define kRepBarWidth  16        /* one scroll bar, drawn beside the list */

#define kRepLineH     11        /* Geneva 9 on 11: 20 rows in the box */
#define kRepVisible   20
/* The last two rows are the blank and the outcome, held there whenever
 * the list is longer than the box. */
#define kRepScroll    (kRepVisible - 2)
#define kRepIndent    14        /* a wrapped line's continuation rows */

/* A name goes into the report whole, so a line is as long as the two
 * names in it and the box wraps it over as many rows as that takes.
 * The rows are worked out once, when the box opens, because measuring
 * text is a Toolbox call and scrolling must not pay for it. */
#define kRepRowMax    320

static short gRowLine[kRepRowMax];   /* which report line the row is from */
static short gRowOff[kRepRowMax];    /* its first byte within that line */
static short gRowLen[kRepRowMax];
static short gRowN;

static Str255        gRepOutcome;   /* the run's result: the last line */
static short         gRepTop;       /* index of the first row shown */
static ControlHandle gRepBar;
static DialogPtr     gRepDlg;       /* the scroll action proc's only route */

/* Rows, not lines: the "and N more" line is one of them. */
static short RepRows(void)
{
    return (short)(gRowN + (gRepMore ? 1 : 0));
}

static void RepMoreLine(Str255 out)
{
    out[0] = 0;
    PStrCat(out, "and ");
    PStrCatNum(out, gRepMore);
    PStrCat(out, " more, which this list had no room for");
}

/* How many of `len` bytes fit in `width`, broken at a space where there
 * is one to break at. The first guess is proportional, so the loops
 * that follow it run a few times rather than once per character — this
 * is a 68000 and TextWidth is a trap. */
static short RepFit(const unsigned char *p, short len, short width)
{
    short n, w, sp;
    if (len <= 0) return 0;
    w = TextWidth((Ptr)p, 0, len);
    if (w <= width) return len;
    n = (short)((long)len * width / (w > 0 ? w : 1));
    if (n < 1) n = 1;
    if (n > len) n = len;
    while (n > 1 && TextWidth((Ptr)p, 0, n) > width) n--;
    while (n < len && TextWidth((Ptr)p, 0, (short)(n + 1)) <= width) n++;
    for (sp = n; sp > n / 2; sp--)
        if (p[sp - 1] == ' ') return sp;
    return n;
}

/* Wrap every line into rows. The port's font must already be the list's
 * (TextWidth measures in it), so this is called from ShowReport after
 * the dialog is up. */
static void RepBuildRows(short width)
{
    short i;
    gRowN = 0;
    for (i = 0; i < gRepN && gRowN < kRepRowMax; i++) {
        const unsigned char *p = gRepBuf + gRepStart[i];
        short len = gRepLen[i], off = 0;
        do {
            short avail = (short)(off ? width - kRepIndent : width);
            short fit = RepFit(p + off, (short)(len - off), avail);
            if (fit <= 0) fit = 1;
            /* A line that has to wrap wraps after the name, when the
             * name itself fits a row: "<what the archive calls it>" and
             * then "renamed to <what is on the disk>". */
            if (off == 0 && fit < len && gRepBreak[i] > 0 &&
                gRepBreak[i] <= fit)
                fit = gRepBreak[i];
            gRowLine[gRowN] = i;
            gRowOff[gRowN] = off;
            gRowLen[gRowN] = fit;
            gRowN++;
            off = (short)(off + fit);
            while (off < len && p[off] == ' ') off++;   /* the break ate it */
        } while (off < len && gRowN < kRepRowMax);
    }
}

static void RepListDraw(DialogPtr dlg)
{
    Rect box, clip;
    short kind, i, rows, total, fits;
    Handle h;
    GrafPtr save;
    RgnHandle saveClip;

    GetPort(&save);
    SetPort((GrafPtr)dlg);
    GetDialogItem(dlg, kRepListItem, &kind, &h, &box);
    EraseRect(&box);
    FrameRect(&box);
    clip = box;
    InsetRect(&clip, 1, 1);
    saveClip = NewRgn();
    if (saveClip) GetClip(saveClip);
    ClipRect(&clip);
    /* Geneva 9: this is a list of names, not a message. Chicago 12 fits
     * about 60 characters across the box and a rename line wants 80. */
    TextFont(3);
    TextSize(9);
    total = RepRows();
    /* Everything fits: the outcome follows the last row and a blank one,
     * where a reader ends up anyway. It does not: the rows scroll under
     * a blank row and the outcome, which stay on the bottom two — the
     * one thing here that must not be somewhere the reader has to go
     * and find. */
    fits = (short)(total + 2 <= kRepVisible);
    rows = fits ? total : (short)kRepScroll;
    for (i = 0; i < rows && gRepTop + i < total; i++) {
        short r = (short)(gRepTop + i), line;
        MoveTo(box.left + 5, box.top + 2 + (i + 1) * kRepLineH);
        if (r >= gRowN) {                      /* the "and N more" row */
            Str255 more;
            RepMoreLine(more);
            DrawString(more);
            continue;
        }
        line = gRowLine[r];
        if (gRowOff[r]) Move(kRepIndent, 0);   /* a wrapped continuation */
        DrawText((Ptr)gRepBuf, (short)(gRepStart[line] + gRowOff[r]),
                 gRowLen[r]);
    }
    TextFace(bold);              /* the verdict, in the document's font */
    MoveTo(box.left + 5,
           box.top + 2 + (short)((fits ? total + 2 : kRepVisible) * kRepLineH));
    DrawString(gRepOutcome);
    TextFace(normal);
    TextFont(0);
    TextSize(12);
    if (saveClip) { SetClip(saveClip); DisposeRgn(saveClip); }
    /* The bar is not a dialog item (macextract.r), so nothing else
     * repaints it when the list under it is redrawn. */
    if (gRepBar) Draw1Control(gRepBar);
    SetPort(save);
}

static pascal void RepListItemProc(WindowPtr w, short item)
{
    (void)item;
    RepListDraw((DialogPtr)w);
}

/* The default button's ring, as an item of its own so that it is redrawn
 * with everything else after Standard File has been over the box. */
static pascal void RepRingItemProc(WindowPtr w, short item)
{
    short kind;
    Handle h;
    Rect box;
    GetDialogItem((DialogPtr)w, kRepOKItem, &kind, &h, &box);
    InsetRect(&box, -4, -4);
    PenSize(3, 3);
    FrameRoundRect(&box, 16, 16);
    PenSize(1, 1);
}

static void RepSetTop(short top)
{
    short max = (short)(RepRows() - kRepScroll);
    if (max < 0) max = 0;
    if (top > max) top = max;
    if (top < 0) top = 0;
    if (top == gRepTop) return;
    gRepTop = top;
    if (gRepBar) SetControlValue(gRepBar, top);
    if (gRepDlg) RepListDraw(gRepDlg);
}

/* Live tracking for the arrows and the page regions. TrackControl calls
 * this repeatedly while the button is held, which is the whole reason
 * the scroll bar is not left to ModalDialog. */
static pascal void RepScrollAction(ControlHandle c, short part)
{
    if (c != gRepBar) return;
    switch (part) {
    case inUpButton:   RepSetTop((short)(gRepTop - 1)); break;
    case inDownButton: RepSetTop((short)(gRepTop + 1)); break;
    case inPageUp:     RepSetTop((short)(gRepTop - kRepScroll)); break;
    case inPageDown:   RepSetTop((short)(gRepTop + kRepScroll)); break;
    default: break;
    }
}

static ControlActionUPP gRepActionUPP;

/* The same lines, as a document: whole, unwrapped, and ending in the
 * outcome. A Macintosh screen has no scrollback and this list can be
 * long, so the run that is worth acting on later can be filed —
 * TEXT/ttxt, CR-separated, opened by TeachText and SimpleText on every
 * system this application runs on. */
static void RepSaveAsText(void)
{
    Point where;
    SFReply reply;
    short ref = 0, i;
    char cr = '\r';

    where.h = 100;
    where.v = 100;
    SFPutFile(where, "\pSave the report as:", "\pExtraction Report",
              NULL, &reply);
    if (!reply.good) return;

    /* Standard File has already asked about replacing it. */
    MyHDelete(reply.vRefNum, 0, reply.fName);
    if (MyHCreate(reply.vRefNum, 0, reply.fName) != noErr) return;
    if (MyOpenFork(reply.vRefNum, 0, reply.fName, fsWrPerm, 0,
                   &ref) != noErr) {
        MyHDelete(reply.vRefNum, 0, reply.fName);
        return;
    }
    for (i = 0; i < gRepN + (gRepMore ? 1 : 0) + 2; i++) {
        Str255 line;
        const unsigned char *p;
        long count;
        if (i < gRepN) {
            p = gRepBuf + gRepStart[i];
            count = gRepLen[i];
        } else if (i == gRepN && gRepMore) {
            RepMoreLine(line);
            p = line + 1;
            count = line[0];
        } else if (i == gRepN + (gRepMore ? 1 : 0)) {
            p = line;                     /* the blank line */
            count = 0;
        } else {
            p = gRepOutcome + 1;
            count = gRepOutcome[0];
        }
        if (count && FSWrite(ref, &count, (Ptr)p) != noErr) break;
        count = 1;
        if (FSWrite(ref, &count, (Ptr)&cr) != noErr) break;
    }
    FSClose(ref);
    FlushVol(NULL, reply.vRefNum);
    {
        CInfoPBRec pb;
        Str63 nm;
        BlockMoveData(reply.fName, nm, reply.fName[0] + 1);
        pb.hFileInfo.ioNamePtr = nm;
        pb.hFileInfo.ioVRefNum = reply.vRefNum;
        pb.hFileInfo.ioDirID = 0;
        pb.hFileInfo.ioFDirIndex = 0;
        if (PBGetCatInfoSync(&pb) == noErr) {
            pb.hFileInfo.ioFlFndrInfo.fdType = 0x54455854L;      /* TEXT */
            pb.hFileInfo.ioFlFndrInfo.fdCreator = 0x74747874L;   /* ttxt */
            pb.hFileInfo.ioDirID = 0;    /* PBGetCatInfo clobbers it */
            PBSetCatInfoSync(&pb);
        }
    }
}

static pascal Boolean RepFilter(DialogPtr dlg, EventRecord *ev, short *item)
{
    char ch;

    if (ev->what == mouseDown) {
        Point p = ev->where;
        ControlHandle c = NULL;
        short part;
        GrafPtr save;
        if (!gRepBar) return false;
        GetPort(&save);
        SetPort((GrafPtr)dlg);
        GlobalToLocal(&p);
        SetPort(save);
        part = FindControl(p, (WindowPtr)dlg, &c);
        if (c != gRepBar || part == 0) return false;   /* a button: go on */
        if (part == inThumb) {
            if (TrackControl(c, p, NULL))
                RepSetTop(GetControlValue(c));
        } else {
            TrackControl(c, p, gRepActionUPP);
        }
        return true;
    }
    if (ev->what != keyDown && ev->what != autoKey) return false;
    ch = (char)(ev->message & charCodeMask);
    if ((ev->modifiers & cmdKey) != 0) return false;
    if (ch == '\r' || ch == 3) { *item = kRepOKItem; return true; }
    switch (ch) {
    case 30: RepSetTop((short)(gRepTop - 1)); return true;             /* up */
    case 31: RepSetTop((short)(gRepTop + 1)); return true;           /* down */
    case 11: RepSetTop((short)(gRepTop - kRepScroll)); return true;  /* PgUp */
    case 12: RepSetTop((short)(gRepTop + kRepScroll)); return true;  /* PgDn */
    case 1:  RepSetTop(0); return true;                              /* Home */
    case 4:  RepSetTop(RepRows()); return true;                       /* End */
    default: break;
    }
    return false;
}

/* `outcome` is the line the alert would have carried on its own. */
static void ShowReport(const unsigned char *outcome)
{
    DialogPtr dlg;
    short hit, kind, max;
    Handle h;
    Rect box;
    ModalFilterUPP filter;

    BlockMoveData(outcome, gRepOutcome, outcome[0] + 1);
    dlg = GetNewDialog(kReportDLOG, NULL, (WindowPtr)-1);
    if (!dlg) {                       /* no room for it: the line still gets said */
        ShowNote(kDoneALRT, outcome);
        return;
    }
    gRepDlg = dlg;
    gRepTop = 0;
    SetPort((GrafPtr)dlg);

    GetDialogItem(dlg, kRepListItem, &kind, &h, &box);
    SetDialogItem(dlg, kRepListItem, kind,
                  (Handle)NewUserItemUPP(RepListItemProc), &box);
    /* Wrap the lines to the box, in the font they are drawn in. */
    TextFont(3);
    TextSize(9);
    RepBuildRows((short)(box.right - box.left - 12));
    TextFont(0);
    TextSize(12);
    max = (short)(RepRows() - kRepScroll);
    if (max < 0) max = 0;
    {
        Rect bar;
        bar.top = box.top;
        bar.bottom = box.bottom;
        bar.left = box.right;
        bar.right = (short)(box.right + kRepBarWidth);
        gRepBar = NewControl((WindowPtr)dlg, &bar, "\p", true, 0, 0, max,
                             scrollBarProc, 0);
        if (gRepBar && max == 0)
            HiliteControl(gRepBar, 255);             /* nothing to scroll */
    }
    if (!gRepActionUPP) gRepActionUPP = NewControlActionUPP(RepScrollAction);

    GetDialogItem(dlg, kRepRingItem, &kind, &h, &box);
    SetDialogItem(dlg, kRepRingItem, kind,
                  (Handle)NewUserItemUPP(RepRingItemProc), &box);
    DrawDialog(dlg);

    filter = NewModalFilterUPP(RepFilter);
    do {
        ModalDialog(filter, &hit);
        if (hit == kRepSaveItem) RepSaveAsText();
    } while (hit != kRepOKItem);
    DisposeDialog(dlg);
    gRepBar = NULL;
    gRepDlg = NULL;
}

static void ExtractOne(short vRefNum, long dirID, ConstStr255Param name,
                       short outVol, long outDir)
{
    Progress pr;
    UncProgress prog;
    int ret, entries, errors;
    UncFormat topFmt = UNC_FORMAT_UNKNOWN;
    Str255 outcome;
    short alrt;

    RepReset();          /* this file's report, not the last one's */
    pr.dlg = GetNewDialog(kProgressDLOG, NULL, (WindowPtr)-1);
    pr.cancelled = false;
    pr.lastTicks = 0;
    pr.startTicks = TickCount();
    pr.shownPct = -1;      /* forces the first tick to draw */
    pr.shownRem = -2;
    gBarPct = 0;
    if (pr.dlg) {
        Str255 s;
        Handle h;
        short kind;
        Rect box;

        /* The bar is a userItem, so nothing draws it until it has a proc. */
        GetDialogItem(pr.dlg, kBarItem, &kind, &h, &box);
        SetDialogItem(pr.dlg, kBarItem, kind,
                      (Handle)NewUserItemUPP(BarUserItem), &box);

        s[0] = 0;
        PStrCat(s, "Extracting ");
        { short i; for (i = 1; i <= (short)name[0] && s[0] < 255; i++)
                       s[++s[0]] = name[i]; }
        GetDialogItem(pr.dlg, kStatusItem, &kind, &h, &box);
        if (h) SetDialogItemText(h, s);

        GetDialogItem(pr.dlg, kDetailItem, &kind, &h, &box);
        if (h) SetDialogItemText(h, "\p0%   estimating time left");

        SetPort((GrafPtr)pr.dlg);
        DrawDialog(pr.dlg);
    }
    prog.ctx = &pr;
    prog.tick = prog_tick;

    /* The archive is read from where it was opened; output goes wherever
     * the destination dialog left us, which defaults to that same folder.
     *
     * Then the envelope layers come off, one at a time. A real download
     * is chained — Archive.sit.hqx, Archive.cpt.bin, Archive.tar.Z —
     * and until 2026-08-14 this application took exactly ONE layer off
     * and stopped, leaving the user to open the result again by hand.
     * README.md has promised the other behaviour since it was written;
     * the Linux CLI has always done it. The autotest keeps the
     * single-layer semantics, because every manifest it is graded
     * against describes one layer (tools/vmac_check.py).
     *
     * The test is the same one the CLI uses: exactly one file and no
     * folders is what an envelope yields, and the file is then sniffed
     * rather than trusted by name. */
    {
        ExtractShape shape;
        short curVol = vRefNum;
        long curDir = dirID;
        Str63 curName;
        short delVol = 0;
        long delDir = 0;
        Str63 delName;
        int depth;

        BlockMoveData(name, curName, name[0] + 1);
        delName[0] = 0;
        /* What the FIRST layer turned out to be, kept for the alert: a
         * file this engine names but cannot open is the one failure whose
         * answer is a different program, and the name is the answer. */
        shape.fmt = UNC_FORMAT_UNKNOWN;

        /* Once per operation, not once per layer: these three are what
         * the alert at the end is built from, and an envelope chain runs
         * the loop below several times. Not measured against a chained
         * fixture that runs out of memory mid-chain — no such specimen
         * here — but the single-layer wording is verified on screen
         * (BLOCKERS.md, tier results). */
        gLastWriteErr = noErr;
        gShortBy = 0;
        gShortPiece = 0;

        for (depth = 0; depth < 8; depth++) {
            ret = RunExtract(curVol, curDir, curName, outVol, outDir,
                             vRefNum, dirID,
                             &prog, &entries, &errors, &shape);
            if (depth == 0) topFmt = shape.fmt;
            /* This layer worked, so the envelope it came out of is
             * litter now. Removed before the next layer runs, so a
             * chain does not leave a trail of intermediates. */
            if (ret == UNC_OK && !errors && delName[0]) {
                MyHDelete(delVol, delDir, delName);
                delName[0] = 0;
                /* RunExtract flushed the volume before it returned, so
                 * this delete is on the far side of the last flush and
                 * would sit in the cache until something else forced
                 * it. The harness kills the emulator where a user would
                 * quit, and the intermediate survived on the volume for
                 * exactly that reason. */
                FlushVol(NULL, delVol);
            }
            if (ret != UNC_OK || errors || pr.cancelled) break;
            if (shape.fileCount != 1 || shape.dirCount != 0 ||
                !shape.name[0]) break;
            /* Only an envelope — or a segmented set, which yields the
             * file it was cut from — has another layer under it. */
            if (!unc_format_is_envelope(shape.fmt) &&
                shape.fmt != UNC_FORMAT_SITSEG &&
                shape.fmt != UNC_FORMAT_DDSEG &&
                shape.fmt != UNC_FORMAT_SPLIT) break;
            {
                short ref;
                FileIO fio2;
                UncIO io2;
                long eof = 0;
                UncFormat inner;

                if (MyOpenFork(outVol, shape.dirID, shape.name, fsRdPerm,
                               0, &ref) != noErr) break;
                GetEOF(ref, &eof);
                fio2.refNum = ref;
                fio2.size = (uint32_t)eof;
                fio2.pos = 0;
                io2.ctx = &fio2;
                io2.read = fio_read;
                io2.seek = fio_seek;
                io2.tell = fio_tell;
                io2.size = fio_size;
                inner = unc_sniff(&io2);
                FSClose(ref);
                if (!unc_format_extractable(inner)) break;
            }
            /* Go round on what was just written, and remember it as the
             * layer to delete once the next one succeeds. */
            delVol = outVol;
            delDir = shape.dirID;
            BlockMoveData(shape.name, delName, shape.name[0] + 1);
            curVol = outVol;
            curDir = shape.dirID;
            BlockMoveData(shape.name, curName, shape.name[0] + 1);
        }
    }

    if (pr.dlg) DisposeDialog(pr.dlg);

    /* One line says how the run ENDED. Where entries have something of
     * their own to report — a name that had to change, a failure that
     * did not stop the archive — that line is the last of a list rather
     * than an alert of its own (ShowReport). The wording is the same
     * either way, and so is the order these are tested in: the most
     * specific answer wins, because it is the one the user can act on. */
    outcome[0] = 0;
    alrt = kErrorALRT;
    if (gLastWriteErr == dskFulErr)
        /* The engine has already stopped the run — every extractor treats a
         * sink failure as the end of the archive — so all that was missing
         * was being able to say WHICH failure. Before this the OSErr was
         * dropped at the `!= noErr` test and a full disk read as "this file
         * could not be extracted". */
        PStrCat(outcome, "The disk is full. Free up some space "
                         "and try again.");
    else if (pr.cancelled || ret == UNC_ERR_ABORTED) {
        PStrCat(outcome, "Extraction cancelled.");
        alrt = kDoneALRT;
    }
    else if (ret == UNC_ERR_SEGMENTED)
        /* A part of a segmented set was never located. Whatever the parts
         * on hand did decode has been written and is worth saying so. */
        PStrCat(outcome, "This archive has more parts. "
                         "Find them and try again.");
    else if (ret == UNC_ERR_IO && entries == 0)
        PStrCat(outcome, "Could not open the archive.");
    else if (gShortBy > 0) {
        /* Ahead of the two generic messages, and covering both of them: a
         * memory shortfall is the same answer whether one entry failed or
         * the whole archive did, and it is the only failure here the user
         * can actually do something about. The number is what turns "it
         * did not work" into one thing to go and do — it is exactly what
         * the memory size in Get Info has to grow by. Rounded UP to the
         * next 8K, so it is round enough to type and never short. */
        PStrCat(outcome, "Needs ");
        PStrCatNum(outcome, (gShortBy + 8191L) / 8192L * 8L);
        PStrCat(outcome, "K more memory. Give MacExtract more in Get Info.");
    }
    else if (gShortPiece)
        /* The budget had room and the Memory Manager still could not find
         * one piece that big, so a bigger memory size need not help. */
        PStrCat(outcome, "Memory is too broken up. "
                         "Quit other programs and try again.");
    else if (ret == UNC_ERR_UNSUPPORTED && entries == 0 &&
             topFmt != UNC_FORMAT_UNKNOWN && !unc_format_extractable(topFmt)) {
        /* Ahead of the generic message, and the reason detect-only exists
         * at all: this file is not damaged and re-downloading it will not
         * help — it is a format somebody else's program opens. Naming it
         * is the whole of what this program can contribute to a file it
         * will never extract (DECISIONS.md 2026-08-27). Kept short: the
         * alert wraps between 32 and 36 characters, and the longest name
         * in the table makes 46. */
        PStrCat(outcome, "MacExtract cannot open ");
        PStrCat(outcome, unc_format_name(topFmt));
        PStrCat(outcome, " files.");
    }
    else if (ret != UNC_OK && entries > 0)
        /* The archive stopped being readable part way down, and what
         * was read is on the disk: "this file could not be extracted"
         * is what the user was told until 2026-08-29, about a file that
         * had just given them entries. What is NOT listed here is
         * whatever lay beyond the point where the walk stopped — the
         * engine never saw those entries either, so nothing can name
         * them (FORMATS.md, *Name limits*). */
        PStrCat(outcome, "Extraction stopped part way through this "
                         "archive.");
    else if (ret != UNC_OK)
        PStrCat(outcome, "This file could not be extracted.");
    /* A run that finished with something behind it. WHERE THE LIST IS
     * BEING SHOWN the verdict says only that — every entry that failed
     * is named a row above it, with what is wrong with it, and a
     * sentence that repeats the list in the vaguest possible terms is
     * worth less than the word that distinguishes this from a clean
     * run. Without the list those sentences are all the user gets, so
     * they stay: two lines, because the alert wraps between 32 and 36
     * characters and a third sits level with the OK button
     * (tools/vmac/README.md). */
    else if (gUnsupported)
        PStrCat(outcome, gRepN ? "Extraction finished."
                               : "Some entries use a method this version "
                                 "cannot read yet.");
    else if (errors)
        PStrCat(outcome, gRepN ? "Extraction finished."
                               : "Some entries could not be extracted.");
    else {
        PStrCat(outcome, "Extraction complete.");
        alrt = kDoneALRT;
    }

    if (gRepN) ShowReport(outcome);
    else ShowNote(alrt, outcome);
}

int main(void)
{
    Point where, dwhere;

    /* LMGetApplLimit: the GetApplLimit glue is absent from the
     * Multiversal import libraries; the low-memory accessor is the
     * documented equivalent (ApplLimit at 0x0130). */
    SetApplLimit((Ptr)((long)LMGetApplLimit() - kStackBump));
    MaxApplZone();
    /* Pre-allocate plenty of master pointers up front. If the File
     * Manager / Dialog Manager exhaust them mid-write, the Memory
     * Manager allocates a new master-pointer block on demand, which
     * fragments a heap already holding the engine's big non-relocatable
     * NewPtr blocks and can corrupt it. 12 blocks = 768 handles. */
    {
        int i;
        for (i = 0; i < 12; i++) MoreMasters();
    }

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

    /* The destination dialog is placed 30 points down and right of the
     * file-open one, so that it visibly MOVES when it replaces it. The
     * two are otherwise near-identical Standard File boxes at the same
     * spot — same list, same Eject and Drive, differing in a prompt
     * line, a name box, and Save where Open was — and a reader who is
     * not looking for those reads the second as the first redrawn.
     * Both dialogs are Apple's; their size and internal layout are not
     * ours to change (that would need SFPPutFile and our own DLOG), so
     * position is the cue available. Measured: the open dialog is
     * 366x216 and the destination one 322x200, so at +30 both still sit
     * whole on a 512x342 Mac Plus screen. */
    dwhere.h = where.h + 30;
    dwhere.v = where.v + 30;

    for (;;) {
        SFReply reply, dest;
        /* The prompt stays empty because SFGetFile ignores it.
         * Source: Inside Macintosh: Files, Standard File Package —
         * the `prompt` parameter of SFGetFile and SFPGetFile is
         * documented "Ignored". Confirmed on System 6.0.8 before that
         * was found: passing "Open an archive:" produced a frame
         * pixel-for-pixel identical to this one. DITL -4000 does carry
         * an empty statText (item 10), but parked at t=1044, a
         * thousand points below a 348x200 dialog, and reaching it needs
         * a customized dialog template. Only SFPutFile's dialog has a
         * usable prompt item, which is why the two are told apart by
         * POSITION below. DECISIONS.md, 2026-08-09. */
        SFGetFile(where, "\p", NULL, -1, NULL, NULL, &reply);
        if (!reply.good) break;

        /* Where should the files go? Standard File keeps ONE current
         * folder across SFGetFile and SFPutFile, so this opens in the
         * folder the archive was just chosen from: pressing Return
         * extracts beside the archive, which is what this application
         * did before it asked at all. Navigating elsewhere is the
         * point — a set of floppies cannot write its output to the
         * disk it is about to ask you to eject.
         *
         * SFPutFile is the classic way to pick a FOLDER (there is no
         * folder picker before System 7's CustomGetFile hooks, and
         * this binary must run on System 6). Only the location of the
         * reply is used; the name in the box is inert.
         *
         * THE DEFAULT NAME MUST NOT NAME A FILE THAT IS THERE. It was
         * `reply.fName` for a day, which is the archive's own name in
         * the archive's own folder, so Save always hit Standard File's
         * "Replace existing "archive.sit"?" — on the DEFAULT path, the
         * one that means "beside the archive". Nothing is written under
         * this name whichever button is pressed, but the alert asks the
         * user to overwrite the file they just opened. A constant is
         * used instead: the box is inert, so it may as well say what
         * the button does.
         *
         * KEEP THE PROMPT SHORT. Standard File's prompt is a single
         * static text item about 200 points wide and it does not wrap:
         * "Extract the files into this folder:" was photographed on
         * System 6 rendering as "Extract the files into this", with
         * the word that carried the meaning cut off. */
        SFPutFile(dwhere, "\pExtract into this folder:",
                  "\pExtract here", NULL, &dest);
        if (!dest.good) continue;      /* changed their mind: pick again */

        /* Both refNums are working directories on System 7 and later
         * and plain volume refNums on System 6; dirID 0 is correct for
         * either (FORMATS.md, the working-directory row). */
        ExtractOne(reply.vRefNum, 0, reply.fName, dest.vRefNum, 0);
    }
    return 0;
}

#endif /* interactive app */
