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

static int mio_seek(void *ctx, uint32_t pos)
{
    MacIO *io = (MacIO *)ctx;
    OSErr err = SetFPos(io->refNum, fsFromStart, (long)pos);
    /* SetFPos past EOF returns eofErr but still positions at EOF; a
     * following read then returns 0 and the engine treats it as
     * truncation. Treating eofErr as a hard error made valid seeks to
     * end-of-file fail with a spurious I/O error. */
    return (err == noErr || err == eofErr) ? 0 : -1;
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
static int xio_seek(void *ctx, uint32_t pos)
{
    MemIO *m = (MemIO *)ctx;
    m->pos = (pos > m->size) ? m->size : pos;   /* clamp, like SetFPos@EOF */
    return 0;
}
static uint32_t xio_tell(void *ctx) { return ((MemIO *)ctx)->pos; }
static uint32_t xio_size(void *ctx) { return ((MemIO *)ctx)->size; }

/* ------------------------------------------------------------------ */
/* UncAlloc over NewPtr with a budget                                 */
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
    if ((long)size + 16 > a->budget) return NULL;
    p = NewPtr((long)size + 16);
    if (p == NULL) return NULL;
    *(long *)p = (long)size;
    a->budget -= (long)size + 16;
    if (a->budget < a->lowmark) a->lowmark = a->budget;  /* track peak usage */
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

#ifndef UNC_SINK_TEST
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
    int          entries, errors;
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
    int          wrErr;              /* a write failed; fail the entry      */
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
    OSErr err;

    s->cur = *info;
    s->entries++;
#ifndef UNC_MAC_STAGE_WRITES
    s->openRef = 0;
    s->openIsRsrc = 0;
    s->dataPos = s->rsrcPos = 0;
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
            err = MyHCreate(s->vRefNum, s->curDirID, s->curName);
            if (err == noErr) break;
            if (err != dupFNErr || attempt >= 9) return -1;
            BlockMoveData(base, s->curName, base[0] + 1);
            BumpName(s->curName, attempt + 1);
        }
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
    pos = isRsrc ? s->rsrcPos : s->dataPos;
    return SetFPos(s->openRef, fsFromStart, (long)pos);
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
    if (StreamSelect(s, fork == UNC_FORK_RSRC) != noErr) {
        s->wrErr = 1;
        return -1;
    }
    /* Write in bounded pieces: FSWrite takes a byte count, and keeping it
     * small bounds how much the File Manager does per call in this deep,
     * cooperative context. */
    while (todo > 0) {
        long count = (long)(todo < 8192u ? todo : 8192u);
        long want = count;
        if (FSWrite(s->openRef, &count, (Ptr)((const char *)buf + off)) != noErr
            || count != want) {
            s->wrErr = 1;
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
    } else if (!s->cur.is_dir) {
        /* Cancelled or failed: remove the empty/partial file this entry
         * created in sink_begin, so no incomplete output is left behind. */
        MyHDelete(s->vRefNum, s->curDirID, s->curName);
    }
    if (status != UNC_OK) s->errors++;
    return 0;
}

/* ------------------------------------------------------------------ */
/* Extraction driver                                                  */
/* ------------------------------------------------------------------ */

#ifndef UNC_SINK_TEST
static long gPeakUsage;   /* engine heap high-water mark from the last RunExtract */

/* Core extraction: open the archive at (inVol,inDir,name) and extract into
 * (outVol,outDir). The interactive app passes the same volume/folder for
 * both (extract next to the archive); the autotest uses a separate output
 * volume. Returns the unc_extract status; fills *entries and *errors from the
 * sink, and gPeakUsage with the engine's peak heap use. prog may be NULL.
 * Shared by the interactive app and the on-Mac autotest. */
static int RunExtract(short inVol, long inDir, ConstStr255Param name,
                      short outVol, long outDir,
                      UncProgress *prog, int *entries, int *errors)
{
    UncIO io;
    MemIO mem;
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

    *entries = *errors = 0;

    /* --- Slurp the whole archive into RAM, then close it. All input
     *     reads happen here, before any output file exists. --- */
    err = MyOpenFork(inVol, inDir, name, fsRdPerm, 0, &refNum);
    if (err != noErr) return UNC_ERR_IO;
    fileSize = 0;
    GetEOF(refNum, &fileSize);
    if (fileSize <= 0) { FSClose(refNum); return UNC_ERR_FORMAT; }

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

    /* Budget the engine against memory remaining AFTER the archive buffer. */
    ma.budget = FreeMem() - kMemReserve;
    if (ma.budget < 32L * 1024) ma.budget = 32L * 1024;
    ma.initial = ma.budget;      /* for peak-usage = initial - lowmark */
    ma.lowmark = ma.budget;
    al.ctx = &ma;
    al.alloc = mal_alloc;
    al.free = mal_free;

    sink.vRefNum = outVol;
    sink.rootDirID = outDir;
    sink.entries = sink.errors = 0;
    sink.pr = NULL;
    sk.ctx = &sink;
    sk.begin_entry = sink_begin;
    sk.write = sink_write;
    sk.end_entry = sink_end;

    opt.list_only = 0;
    opt.test_only = 0;
    opt.name_hint = name + 1;            /* Pascal string body */
    opt.name_hint_len = name[0];

    ret = unc_extract(&io, &sk, &al, prog, &opt);
    gPeakUsage = ma.initial - ma.lowmark;   /* engine heap high-water mark */

    DisposePtr(archiveBuf);
    FlushVol(NULL, outVol);    /* persist all output before returning */
    FlushVol(NULL, outVol);
    *entries = sink.entries;
    *errors = sink.errors;
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

    HideCursor();      /* stop the cursor's save/restore from stamping its old
                          (desktop-pattern) background back over the grid */
    n = h * rb;                                 /* erase whole screen to white */
    for (k = 0; k < n; k++) ((unsigned char *)base)[k] = 0;

    at_fill(base, rb, 24, 32, 48, 56, 1);       /* calibration TL (36,44)  */
    at_fill(base, rb, 464, 32, 488, 56, 1);     /* calibration TR (476,44) */
    at_fill(base, rb, 24, 288, 48, 312, 1);     /* calibration BL (36,300) */

    for (b = 15; b >= 0; b--) at_cell(base, rb, idx++, (0xA55A >> b) & 1);
    for (i = 0; i < nvals; i++)
        for (b = 31; b >= 0; b--)
            at_cell(base, rb, idx++, (int)((vals[i] >> b) & 1u));
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

/* Count the items directly in a volume's root. `dirs` matters as a guard:
 * this walks one level only, so a non-zero directory count means the file
 * count is partial and the host must not draw conclusions from it. */
static void at_count_root(short vol, int *files, int *dirs)
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
        pb.hFileInfo.ioDirID = fsRtDirID;
        pb.hFileInfo.ioFDirIndex = idx;
        if (PBGetCatInfoSync(&pb) != noErr) return;   /* past the last item */
        if (pb.hFileInfo.ioFlAttrib & ioDirMask) (*dirs)++;
        else                                     (*files)++;
    }
}
#endif  /* UNC_AT_CANCEL */

static void at_fail(int code)
{
    uint32_t vals[8];
    int i;
    for (i = 0; i < 8; i++) vals[i] = 0;
    vals[0] = (uint32_t)gATnvols;    /* how many volumes were actually mounted */
    vals[1] = (uint32_t)code;
    at_report(vals, 8);
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
    if (FindVolWait("\pOut", &outVol) != noErr) at_fail(kAtNoOutVol);

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
                         outVol, fsRtDirID, &prog, &entries, &errors);
        at_count_root(outVol, &files, &dirs);
        for (i = 0; i < 8; i++) vals[i] = 0;
        vals[0] = (uint32_t)gATnrec;   /* entries that completed successfully */
        vals[1] = (uint32_t)ret;       /* expect UNC_ERR_ABORTED (-8)         */
        vals[2] = (uint32_t)files;     /* files actually on the Out volume    */
        vals[3] = (uint32_t)dirs;      /* must be 0, or the count is partial  */
        vals[7] = (uint32_t)gPeakUsage;
        at_report(vals, 8);
        at_idle();
    }
#endif

    ret = RunExtract(inVol, fsRtDirID, "\parchive.sit",
                     outVol, fsRtDirID, NULL, &entries, &errors);

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
#ifdef UNC_AT_META
        /* E2E "launches by double-click" check: overwrite errors/CRC slots with
         * the first file's on-Mac Finder info — should be the archive's
         * type/creator with the inited bit (0x0100) CLEARED, which is exactly
         * what makes the Finder treat an extracted APPL as launchable. */
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

static void ExtractOne(short vRefNum, long dirID, ConstStr255Param name)
{
    Progress pr;
    UncProgress prog;
    int ret, entries, errors;

    pr.dlg = GetNewDialog(kProgressDLOG, NULL, (WindowPtr)-1);
    pr.cancelled = false;
    pr.lastTicks = 0;
    if (pr.dlg) DrawDialog(pr.dlg);
    prog.ctx = &pr;
    prog.tick = prog_tick;

    /* Interactive: extract next to the archive (same volume/folder). */
    ret = RunExtract(vRefNum, dirID, name, vRefNum, dirID,
                     &prog, &entries, &errors);

    if (pr.dlg) DisposeDialog(pr.dlg);

    if (pr.cancelled)
        ShowNote(kDoneALRT, "\pExtraction cancelled.");
    else if (ret == UNC_ERR_IO && entries == 0)
        ShowNote(kErrorALRT, "\pCould not open the archive.");
    else if (ret != UNC_OK)
        ShowNote(kErrorALRT, "\pThis file could not be extracted.");
    else if (errors)
        ShowNote(kErrorALRT, "\pSome entries could not be extracted.");
    else
        ShowNote(kDoneALRT, "\pExtraction complete.");
}

int main(void)
{
    Point where;

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

#endif /* interactive app */
