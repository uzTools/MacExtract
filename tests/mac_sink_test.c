/*
 * mac_sink_test.c — run the ACTUAL Mac sink/allocator/io code
 * (mac/macextract_mac.c) against the real engine on Linux, using a
 * Linux-backed mock Toolbox. Purpose: catch memory bugs in the Mac
 * glue deterministically, especially on big-endian m68k (qemu-m68k),
 * which the real Linux CLI sink never exercises.
 *
 * Build (native ASan): see tests/run_mac_sink.sh
 * Build (big-endian m68k): m68k-linux-gnu-gcc ... then qemu-m68k
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define _GNU_SOURCE 1
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <errno.h>

#include "../mac/mac_mocks.h"
#include "macextract.h"

#ifdef UNC_AT_OVERLAY
/* The overlay lane, tests/run_overlay_host.sh. The decoders are not linked in
 * this build: they are the m68k 'OVLY' images the Retro68 build ships, built
 * here by the same script with the m68k-linux toolchain, loaded by the REAL
 * loader through the mock Resource Manager in tests/ovlbox/ovlbox.c, and
 * CALLED. Everything below is unchanged, so the same fixtures and the same
 * oracle manifests grade both configurations (OPEN_ITEMS.md, *The overlay
 * loader*). */
#include "ovlbox.h"
extern void ovl_preload(void);
extern void ovl_release_if_unwanted(UncFormat fmt, UncIO *io);
#endif

/* ------------------------------------------------------------------ */
/* Mock Toolbox: a tiny open-file table backed by Linux fds.          */
/* ------------------------------------------------------------------ */

#define MAX_OPEN 32
static struct { int fd; int used; } gFiles[MAX_OPEN];
static char gOutDir[512];

/* Directory id -> path map (id 0 = gOutDir; PBDirCreateSync adds more)
 * so the mock reproduces the archive's folder tree on disk. */
#define MAX_DIRS 512
static char gDirs[MAX_DIRS][700];
static int  gNumDirs = 1;   /* [0] filled in main() */

/* Sanitize a Pascal Str63 into a C name (': ' path handling not needed
 * — sink already produced a leaf component). */
static void pstr(ConstStr255Param p, char *out, size_t cap)
{
    size_t n = p[0], i;
    if (n >= cap) n = cap - 1;
    for (i = 0; i < n; i++) out[i] = (char)p[1 + i];
    out[n] = 0;
}

static int alloc_slot(int fd)
{
    int i;
    for (i = 2; i < MAX_OPEN; i++)   /* refNums start at 2 */
        if (!gFiles[i].used) { gFiles[i].used = 1; gFiles[i].fd = fd; return i; }
    return -1;
}

Ptr NewPtr(Size n)      { return (Ptr)malloc((size_t)n); }
Ptr NewPtrClear(Size n) { return (Ptr)calloc(1, (size_t)n); }
void DisposePtr(Ptr p)  { free(p); }
long FreeMem(void)       { return 3800L * 1024; }   /* pretend 3.8 MB */
/* Nothing purgeable in the mock heap, so PurgeSpace agrees with FreeMem —
 * which is what it does on a single-segment build anyway. */
void PurgeSpace(Size *total, Size *contig)
{ if (total) *total = FreeMem(); if (contig) *contig = FreeMem(); }
void BlockMoveData(const void *s, void *d, Size n) { memmove(d, s, (size_t)n); }
void NumToString(long v, StringPtr s)
{
    char b[24]; int n; snprintf(b, sizeof b, "%ld", v); n = (int)strlen(b);
    s[0] = (unsigned char)n; memcpy(s + 1, b, (size_t)n);
}

/* The mock stands in for HFS, where a resource fork is part of the file and
 * two entries named "X" and "X.rsrc" have nothing to do with each other. A
 * ".rsrc" SUFFIX encoding invents a collision the File Manager does not have,
 * so the sidecar is written as a "._" PREFIX — the same convention the host
 * comparison uses. DECISIONS.md, 2026-08-08. */
static void full_path(long dir, ConstStr255Param name, int rsrc,
                      char *out, size_t cap)
{
    char leaf[64];
    const char *base = (dir >= 0 && dir < gNumDirs) ? gDirs[dir] : gOutDir;
    pstr(name, leaf, sizeof leaf);
    snprintf(out, cap, "%s/%s%s", base, rsrc ? "._" : "", leaf);
}

OSErr HCreate(short vref, long dir, ConstStr255Param name, OSType cr, OSType ty)
{
    char path[800]; int fd;
    (void)vref; (void)cr; (void)ty;
    full_path(dir, name, 0, path, sizeof path);
    fd = open(path, O_CREAT | O_EXCL | O_WRONLY, 0644);
    if (fd < 0) return dupFNErr;
    close(fd);
    return noErr;
}

static OSErr do_open(long dir, ConstStr255Param name, int rsrc, short *ref)
{
    char path[800]; int fd, slot;
    full_path(dir, name, rsrc, path, sizeof path);
    fd = open(path, O_CREAT | O_RDWR, 0644);
    if (fd < 0) return fnfErr;
    slot = alloc_slot(fd);
    if (slot < 0) { close(fd); return -1; }
    *ref = (short)slot;
    return noErr;
}
OSErr HOpen(short v, long d, ConstStr255Param n, SignedByte p, short *ref)
{ (void)v; (void)p; return do_open(d, n, 0, ref); }
OSErr HOpenRF(short v, long d, ConstStr255Param n, SignedByte p, short *ref)
{ (void)v; (void)p; return do_open(d, n, 1, ref); }

/* A catalog of what the shell set, per path: the mock stands in for the
 * File Manager's catalog, so a test can ask what a file or folder came out
 * with. Creating or deleting an item stamps its folder's modification date
 * with "now", which is what the File Manager does and what the shell has
 * to undo for folders whose date the archive states. */
#define MAX_CAT 1024
typedef struct {
    char     path[800];
    int      used;
    uint8_t  finfo[16], fxinfo[16];
    uint32_t cr, md, bk;
    int      locked;
    uint8_t  comment[256];
    int      clen;
} CatRec;
static CatRec gCat[MAX_CAT];
static uint32_t gNow = 0xD0000000u;    /* the mock's clock, one per change */
/* Controls: a set bit makes the mock DROP that write, so a check that
 * still passes under it was not testing the write. */
#define DROP_FINFO   0x01
#define DROP_FXINFO  0x02
#define DROP_BACKUP  0x04
#define DROP_LOCK    0x08
#define DROP_COMMENT 0x10
#define DROP_DIRMD   0x20
static int gDrop;
static int gHasDT = 1;                 /* the volume has a Desktop Manager */
static int gDTSetCalls;

static CatRec *cat_rec(const char *path, int make)
{
    int i, fr = -1;
    for (i = 0; i < MAX_CAT; i++) {
        if (gCat[i].used && strcmp(gCat[i].path, path) == 0) return &gCat[i];
        if (!gCat[i].used && fr < 0) fr = i;
    }
    if (!make || fr < 0) return NULL;
    memset(&gCat[fr], 0, sizeof gCat[fr]);
    gCat[fr].used = 1;
    snprintf(gCat[fr].path, sizeof gCat[fr].path, "%s", path);
    return &gCat[fr];
}

static void cat_touch_dir(long dir)
{
    const char *dp = (dir >= 0 && dir < gNumDirs) ? gDirs[dir] : gOutDir;
    CatRec *r = cat_rec(dp, 1);
    r->md = gNow++;
}

/* Param-block File Manager calls — the real Mac shell uses these (the H-glue
 * is broken on System 6); the mock exercises the same code path. */
OSErr PBHOpenSync(HParamBlockRec *pb)
{
    short ref = 0;
    OSErr e = do_open(pb->fileParam.ioDirID, pb->ioParam.ioNamePtr, 0, &ref);
    pb->ioParam.ioRefNum = ref;
    return e;
}
OSErr PBHOpenRFSync(HParamBlockRec *pb)
{
    short ref = 0;
    OSErr e = do_open(pb->fileParam.ioDirID, pb->ioParam.ioNamePtr, 1, &ref);
    pb->ioParam.ioRefNum = ref;
    return e;
}
OSErr PBHCreateSync(HParamBlockRec *pb)
{
    char path[800]; int fd;
    full_path(pb->fileParam.ioDirID, pb->ioParam.ioNamePtr, 0, path,
              sizeof path);
    fd = open(path, O_CREAT | O_EXCL | O_WRONLY, 0644);
    if (fd < 0) return dupFNErr;
    close(fd);
    { CatRec *r = cat_rec(path, 1); memset(r->finfo, 0, 16); r->cr = r->md = gNow; }
    cat_touch_dir(pb->fileParam.ioDirID);
    return noErr;
}
OSErr PBHDeleteSync(HParamBlockRec *pb)
{
    char path[800], rpath[820];
    CatRec *r;
    full_path(pb->fileParam.ioDirID, pb->ioParam.ioNamePtr, 0, path,
              sizeof path);
    full_path(pb->fileParam.ioDirID, pb->ioParam.ioNamePtr, 1, rpath,
              sizeof rpath);
    r = cat_rec(path, 0);
    if (r && r->locked) return fLckdErr;   /* as the File Manager does */
    unlink(rpath);                     /* resource-fork sidecar, if any */
    if (unlink(path) != 0) return fnfErr;
    if (r) r->used = 0;
    cat_touch_dir(pb->fileParam.ioDirID);
    return noErr;
}
static OSErr set_lock(HParamBlockRec *pb, int lock)
{
    char path[800];
    CatRec *r;
    full_path(pb->fileParam.ioDirID, pb->ioParam.ioNamePtr, 0, path,
              sizeof path);
    r = cat_rec(path, 0);
    if (!r) return fnfErr;
    if (!(lock && (gDrop & DROP_LOCK))) r->locked = lock;
    return noErr;
}
OSErr PBHSetFLockSync(HParamBlockRec *pb) { return set_lock(pb, 1); }
OSErr PBHRstFLockSync(HParamBlockRec *pb) { return set_lock(pb, 0); }
/* PBHGetVolParms: vMVersion, then vMAttrib, big-endian, with bit 12
 * (bHasDesktopMgr) set when the mock volume has a Desktop Manager. */
OSErr PBHGetVolParmsSync(HParamBlockRec *pb)
{
    uint8_t *b = (uint8_t *)pb->ioParam.ioBuffer;
    if (pb->ioParam.ioReqCount < 6) return paramErr;
    memset(b, 0, 6);
    b[1] = 2;
    if (gHasDT) b[4] = 0x10;
    return noErr;
}
OSErr PBDTGetPath(DTPBRec *pb)
{
    if (!gHasDT) return paramErr;
    pb->ioDTRefNum = 99;
    return noErr;
}
OSErr PBDTSetCommentSync(DTPBRec *pb)
{
    char path[800];
    CatRec *r;
    gDTSetCalls++;
    if (pb->ioDTRefNum != 99) return paramErr;
    full_path(pb->ioDirID, pb->ioNamePtr, 0, path, sizeof path);
    r = cat_rec(path, 0);
    if (!r) return fnfErr;
    if (gDrop & DROP_COMMENT) return noErr;
    r->clen = pb->ioDTReqCount > 255 ? 255 : (int)pb->ioDTReqCount;
    memcpy(r->comment, pb->ioDTBuffer, (size_t)r->clen);
    return noErr;
}
OSErr PBDTFlushSync(DTPBRec *pb) { (void)pb; return noErr; }

OSErr FSRead(short ref, long *count, void *buf)
{
    ssize_t r;
    if (ref < 0 || ref >= MAX_OPEN || !gFiles[ref].used) return -1;
    r = read(gFiles[ref].fd, buf, (size_t)*count);
    if (r < 0) return -1;
    if (r == 0) { *count = 0; return eofErr; }
    *count = (long)r;
    return noErr;
}
OSErr FSWrite(short ref, long *count, const void *buf)
{
    ssize_t w;
    if (ref < 0 || ref >= MAX_OPEN || !gFiles[ref].used) return -1;
    w = write(gFiles[ref].fd, buf, (size_t)*count);
    if (w < 0) return -1;
    *count = (long)w;
    return noErr;
}
OSErr FSClose(short ref)
{
    if (ref < 0 || ref >= MAX_OPEN || !gFiles[ref].used) return -1;
    close(gFiles[ref].fd);
    gFiles[ref].used = 0;
    return noErr;
}
OSErr SetFPos(short ref, short mode, long off)
{
    off_t end;
    if (ref < 0 || ref >= MAX_OPEN || !gFiles[ref].used) return -1;
    end = lseek(gFiles[ref].fd, 0, SEEK_END);
    if (mode == fsFromLEOF) {                 /* seek relative to EOF (append) */
        return lseek(gFiles[ref].fd, end + off, SEEK_SET) < 0 ? -1 : noErr;
    }
    /* fsFromStart: replicate the real File Manager — seeking past EOF returns
     * eofErr (but still positions at EOF), exercising the sink's handling. */
    if (off > end) { return eofErr; }
    return lseek(gFiles[ref].fd, off, SEEK_SET) < 0 ? -1 : noErr;
}
OSErr GetFPos(short ref, long *pos)
{
    if (ref < 0 || ref >= MAX_OPEN || !gFiles[ref].used) return -1;
    *pos = (long)lseek(gFiles[ref].fd, 0, SEEK_CUR);
    return noErr;
}
OSErr GetEOF(short ref, long *eof)
{
    off_t cur;
    if (ref < 0 || ref >= MAX_OPEN || !gFiles[ref].used) return -1;
    cur = lseek(gFiles[ref].fd, 0, SEEK_CUR);
    *eof = (long)lseek(gFiles[ref].fd, 0, SEEK_END);
    lseek(gFiles[ref].fd, cur, SEEK_SET);
    return noErr;
}
OSErr SetEOF(short ref, long eof)
{
    if (ref < 0 || ref >= MAX_OPEN || !gFiles[ref].used) return -1;
    return ftruncate(gFiles[ref].fd, eof) < 0 ? -1 : noErr;
}
OSErr FlushVol(ConstStringPtr v, short r) { (void)v; (void)r; return noErr; }
/* The id this mock knows for `path`, registering it if it is new. */
static int dir_id_for(const char *path)
{
    int i;
    for (i = 0; i < gNumDirs; i++)
        if (strcmp(gDirs[i], path) == 0) return i;
    if (gNumDirs >= MAX_DIRS) return 0;
    snprintf(gDirs[gNumDirs], sizeof gDirs[0], "%s", path);
    return gNumDirs++;
}

/* Enough of PBGetCatInfo for what the shell asks it: does this name
 * exist, and is it a FOLDER? EnsureDir asks exactly that, of a name
 * PBDirCreateSync has just refused, and until 2026-08-29 this returned
 * noErr over an untouched param block — so the shell read a dir bit and
 * a directory id out of stack garbage on the one path the real File
 * Manager takes whenever a folder is already there. */
OSErr PBGetCatInfoSync(CInfoPBRec *pb)
{
    char path[800];
    struct stat st;
    CatRec *r;
    if (pb->dirInfo.ioFDirIndex < 0) {
        /* The directory whose ID is ioDrDirID: its name and its parent. */
        long id = pb->dirInfo.ioDrDirID;
        char *slash;
        if (id < 0 || id >= gNumDirs) return fnfErr;
        snprintf(path, sizeof path, "%s", gDirs[id]);
        slash = strrchr(path, '/');
        if (pb->dirInfo.ioNamePtr && slash) {
            size_t n = strlen(slash + 1);
            pb->dirInfo.ioNamePtr[0] = (unsigned char)n;
            memcpy(pb->dirInfo.ioNamePtr + 1, slash + 1, n);
        }
        if (slash) {
            *slash = 0;
            pb->dirInfo.ioDrParID = dir_id_for(path);
            *slash = '/';
        }
    } else {
        full_path(pb->dirInfo.ioDrDirID, pb->dirInfo.ioNamePtr, 0, path,
                  sizeof path);
    }
    if (stat(path, &st) != 0) return fnfErr;
    r = cat_rec(path, 1);
    memcpy(&pb->hFileInfo.ioFlFndrInfo, r->finfo, 16);
    memcpy(&pb->hFileInfo.ioFlXFndrInfo, r->fxinfo, 16);
    pb->hFileInfo.ioFlCrDat = r->cr;
    pb->hFileInfo.ioFlMdDat = r->md;
    pb->hFileInfo.ioFlBkDat = r->bk;
    if (S_ISDIR(st.st_mode)) {
        pb->dirInfo.ioFlAttrib = 0x10;             /* ioDirMask */
        pb->dirInfo.ioDrDirID = dir_id_for(path);
    } else {
        pb->hFileInfo.ioFlAttrib = (SignedByte)(r->locked ? 0x01 : 0);
    }
    return noErr;
}
OSErr PBSetCatInfoSync(CInfoPBRec *pb)
{
    char path[800];
    struct stat st;
    CatRec *r;
    full_path(pb->hFileInfo.ioDirID, pb->hFileInfo.ioNamePtr, 0, path,
              sizeof path);
    if (stat(path, &st) != 0) return fnfErr;
    r = cat_rec(path, 1);
    if (!(gDrop & DROP_FINFO)) memcpy(r->finfo, &pb->hFileInfo.ioFlFndrInfo, 16);
    else memcpy(r->finfo, &pb->hFileInfo.ioFlFndrInfo, 10);  /* type..flags */
    if (!(gDrop & DROP_FXINFO))
        memcpy(r->fxinfo, &pb->hFileInfo.ioFlXFndrInfo, 16);
    r->cr = pb->hFileInfo.ioFlCrDat;
    if (!(S_ISDIR(st.st_mode) && (gDrop & DROP_DIRMD)))
        r->md = pb->hFileInfo.ioFlMdDat;
    if (!(gDrop & DROP_BACKUP)) r->bk = pb->hFileInfo.ioFlBkDat;
    return noErr;
}
OSErr PBDirCreateSync(HParamBlockRec *pb)
{
    char path[800];
    full_path(pb->fileParam.ioDirID, pb->fileParam.ioNamePtr, 0, path,
              sizeof path);
    /* dupFNErr for a name that is already taken, as the File Manager
     * does: that is what tells the shell a folder was MERGED into one
     * that was already there rather than created. */
    if (mkdir(path, 0755) != 0) {
        if (errno == EEXIST) return dupFNErr;
        return ioErr;
    }
    { CatRec *r = cat_rec(path, 1); r->cr = r->md = gNow; }
    cat_touch_dir(pb->fileParam.ioDirID);
    pb->fileParam.ioDirID = dir_id_for(path);      /* the new dir id */
    return noErr;
}

/* Pull in the actual sink/allocator/io code under test. */
#define UNC_SINK_TEST
#include "../mac/macextract_mac.c"

/* ------------------------------------------------------------------ */
/* Drive the engine through the Mac sink on a real archive.           */
/* ------------------------------------------------------------------ */

int main(int argc, char **argv)
{
    MacIO mio;
    UncIO io;
    MacAlloc ma;
    UncAlloc al;
    MacSink sink;
    UncSink sk;
    UncOptions opt;
    int srcfd, srcslot;
    struct stat st;
    int ret;

    if (argc >= 2 && strcmp(argv[1], "--cancel") == 0) {
        /* Cmd-. / per-entry error cleanup: an entry creates its file in
         * sink_begin (before decoding); on a cancel or failure sink_end must
         * delete it, so no empty or partial output is left behind.
         *
         * Two cases, and the SECOND is the one that matters. Aborting before
         * any data arrives was the only case the default write path could
         * produce back when whole forks were staged in RAM and written in
         * sink_end. Now that writes stream straight through, a cancel
         * normally lands with bytes ALREADY on disk and a fork still open —
         * sink_end has to close it before it can delete the file. Testing
         * only the no-data case would leave that entirely uncovered. */
        static const struct { const char *what; int bytes; } cases[] = {
            { "abort before any data",  0    },
            { "abort mid-write",        4100 },   /* > one 4 KB write chunk */
        };
        char path[900];
        size_t c;
        int ok = 1;
        snprintf(gOutDir, sizeof gOutDir, "%s", argc >= 3 ? argv[2] : "/tmp/cancel_out");
        mkdir(gOutDir, 0755);
        snprintf(gDirs[0], sizeof gDirs[0], "%s", gOutDir);
        for (c = 0; c < sizeof cases / sizeof cases[0]; c++) {
            MacSink s; UncEntryInfo info;
            int made, wrote = 1, gone;
            static char chunk[4100];
            memset(&s, 0, sizeof s); s.vRefNum = 1; s.rootDirID = 0;
            memset(&info, 0, sizeof info);
            memcpy(info.name, "canceltest", 10); info.name_len = 10;
            info.data_size = 100; info.rsrc_size = 0; info.is_dir = 0;
            sink_begin(&s, &info);
            snprintf(path, sizeof path, "%s/canceltest", gOutDir);
            made = (access(path, F_OK) == 0);
            if (cases[c].bytes) {
                memset(chunk, 0xA5, sizeof chunk);
                /* Both forks: the resource fork is opened separately, so a
                 * cancel can find either one of them open. */
                wrote = sink_write(&s, UNC_FORK_DATA, chunk, cases[c].bytes) == 0
                     && sink_write(&s, UNC_FORK_RSRC, chunk, 64) == 0;
            }
            sink_end(&s, UNC_ERR_ABORTED);
            gone = (access(path, F_OK) != 0);
            fprintf(stderr, "cancel-cleanup [%s]: created=%d wrote=%d removed=%d\n",
                    cases[c].what, made, wrote, gone);
            if (!(made && wrote && gone)) ok = 0;
        }
        return ok ? 0 : 1;
    }
    if (argc >= 2 && strcmp(argv[1], "--meta") == 0) {
        /* Every field of UncEntryInfo's metadata, written by the shell and
         * read back off the mock catalog: a folder's DInfo, DXInfo, three
         * dates and comment; a file's FInfo, FXInfo, backup date, comment
         * and lock; and the folder's modification date surviving the two
         * files then created inside it. Then the same run once per DROP_*
         * control, in which the mock throws that one write away: the check
         * for it must FAIL there, or it was not testing the write.
         *
         * Driven through sink_begin/sink_end, as --cancel is: the engine's
         * half (which reader delivers which field) is graded against lsar
         * by tools/run_meta.py. Cannot see: the real File Manager's or
         * Desktop Manager's answers, which tools/vmac/hfs_cat.py reads off
         * an emulated Mac's disk instead. */
        static const uint8_t dinfo[16] = {        /* frRect, frFlags 0x0400,
                                                     frLocation, frView */
            0x00,0x28, 0x00,0x14, 0x01,0x2c, 0x01,0xf4, 0x04,0x00,
            0x00,0x50, 0x00,0x60, 0x01,0x07 };
        static const uint8_t dxinfo[16] = {       /* frScroll, frOpenChain
                                                     0x33, frUnused,
                                                     frComment 0x1234,
                                                     frPutAway 7 */
            0xff,0xfc, 0xff,0xfe, 0,0,0,0x33, 0,0, 0x12,0x34, 0,0,0,7 };
        static const uint8_t finfo[16] = {        /* TEXT ttxt, flags 0x0100
                                                     (inited, KEPT: the
                                                     position is stated),
                                                     location (0x30,0x40),
                                                     fdFldr -3 */
            'T','E','X','T', 't','t','x','t', 0x01,0x00,
            0x00,0x30, 0x00,0x40, 0xff,0xfd };
        static const uint8_t fxinfo[16] = {       /* fdIconID 0x0102,
                                                     fdUnused 0x55 0x66 (kept),
                                                     script 0x81, fdComment
                                                     0x5389, fdPutAway 0x22 */
            0x01,0x02, 0,0,0x55,0x66,0,0x81, 0,0, 0x53,0x89, 0,0,0,0x22 };
        static const uint8_t zero6[6] = { 0 };
        static const char fcmt[] = "a folder's comment";
        static const char cmt[] = "Get Info says: keep this";
        static const struct { int bit; const char *what; } controls[] = {
            { 0,            "none" },
            { DROP_FINFO,   "FInfo/DInfo" },
            { DROP_FXINFO,  "FXInfo/DXInfo" },
            { DROP_BACKUP,  "backup date" },
            { DROP_LOCK,    "lock" },
            { DROP_COMMENT, "comment" },
            { DROP_DIRMD,   "folder date" },
        };
        size_t k;
        int ok = 1;
        const char *base = argc >= 3 ? argv[2] : "/tmp/meta_out";
        for (k = 0; k < sizeof controls / sizeof controls[0]; k++) {
            MacSink sk2; UncEntryInfo info;
            char dir[600], path[900];
            CatRec *rf, *rd, *rp;
            unsigned bad = 0;
            FInfo fi;
            snprintf(dir, sizeof dir, "%s/c%u", base, (unsigned)k);
            mkdir(base, 0755);
            mkdir(dir, 0755);
            snprintf(gOutDir, sizeof gOutDir, "%s", dir);
            snprintf(gDirs[0], sizeof gDirs[0], "%s", gOutDir);
            gNumDirs = 1;
            memset(gCat, 0, sizeof gCat);
            gDrop = controls[k].bit;
            RepReset();
            memset(&sk2, 0, sizeof sk2); sk2.vRefNum = 1; sk2.rootDirID = 0;

            memset(&info, 0, sizeof info);
            memcpy(info.name, "Fold", 4); info.name_len = 4; info.is_dir = 1;
            info.finder_flags = 0x0400;
            info.create_date = 0xA0000001u; info.mod_date = 0xA0000002u;
            info.backup_date = 0xA0000003u;
            memcpy(info.finder_info, dinfo, 16);
            memcpy(info.finder_info + 16, dxinfo, 16);
            info.meta = UNC_META_FINFO | UNC_META_FXINFO | UNC_META_BACKUP;
            info.comment = (const uint8_t *)fcmt;
            info.comment_len = (uint16_t)strlen(fcmt);
            sink_begin(&sk2, &info);

            memset(&info, 0, sizeof info);
            memcpy(info.name, "Fold/Doc", 8); info.name_len = 8;
            info.type = 0x54455854u; info.creator = 0x74747874u;
            info.finder_flags = 0x0100;
            info.create_date = 0xA0000011u; info.mod_date = 0xA0000012u;
            info.backup_date = 0xA0000013u;
            memcpy(info.finder_info, finfo, 16);
            memcpy(info.finder_info + 16, fxinfo, 16);
            info.meta = UNC_META_FINFO | UNC_META_FXINFO | UNC_META_BACKUP;
            info.comment = (const uint8_t *)cmt;
            info.comment_len = (uint16_t)strlen(cmt);
            info.locked = UNC_LOCK_YES;
            info.data_size = 5; info.rsrc_size = 0;
            if (sink_begin(&sk2, &info) == 0) {
                sink_write(&sk2, UNC_FORK_DATA, "hello", 5);
                sink_end(&sk2, UNC_OK);
            }

            /* An application: a bundle (0x2000), whose inited bit is
             * cleared so the Finder registers it (finderpos.py). */
            memset(&info, 0, sizeof info);
            memcpy(info.name, "Fold/App", 8); info.name_len = 8;
            info.type = 0x4150504Cu; info.creator = 0x4D457874u;
            info.finder_flags = 0x2100;
            memcpy(info.finder_info, finfo, 16);
            info.meta = UNC_META_FINFO;
            info.data_size = 0; info.rsrc_size = 0;
            if (sink_begin(&sk2, &info) == 0) sink_end(&sk2, UNC_OK);

            memset(&info, 0, sizeof info);
            memcpy(info.name, "Fold/Plain", 10); info.name_len = 10;
            info.locked = UNC_LOCK_NO;
            info.data_size = 0; info.rsrc_size = 0;
            if (sink_begin(&sk2, &info) == 0) sink_end(&sk2, UNC_OK);

            snprintf(path, sizeof path, "%s/Fold", dir);
            rd = cat_rec(path, 0);
            snprintf(path, sizeof path, "%s/Fold/Doc", dir);
            rf = cat_rec(path, 0);
            snprintf(path, sizeof path, "%s/Fold/Plain", dir);
            rp = cat_rec(path, 0);
            if (!rd || !rf || !rp) {
                fprintf(stderr, "meta [%s]: an entry is missing\n",
                        controls[k].what);
                ok = 0;
                continue;
            }
            memcpy(&fi, rf->finfo, 16);
            /* Each check is one bit of `bad`. */
            if (memcmp(rd->finfo, dinfo, 8) || memcmp(rd->finfo + 10, dinfo + 10, 6))
                bad |= DROP_FINFO;
            if (memcmp(rf->finfo + 10, finfo + 10, 6) ||
                fi.fdType != 0x54455854u || fi.fdCreator != 0x74747874u ||
                fi.fdFlags != 0x0100)
                bad |= DROP_FINFO;
            snprintf(path, sizeof path, "%s/Fold/App", dir);
            {
                CatRec *ra = cat_rec(path, 0);
                FInfo fa;
                if (!ra) bad |= DROP_FINFO;
                else {
                    memcpy(&fa, ra->finfo, 16);
                    if (fa.fdFlags != 0x2000) bad |= DROP_FINFO;
                }
            }
            /* As the shell writes them: the source volume's comment id,
             * put-away folder and (a folder's) open chain cleared, the
             * rest — a file's fdUnused included — as the archive held. */
            if (memcmp(rd->fxinfo, dxinfo, 4) || memcmp(rd->fxinfo + 4, zero6, 4) ||
                memcmp(rd->fxinfo + 8, dxinfo + 8, 2) ||
                memcmp(rd->fxinfo + 10, zero6, 6) ||
                memcmp(rf->fxinfo, fxinfo, 10) ||
                memcmp(rf->fxinfo + 10, zero6, 6))
                bad |= DROP_FXINFO;
            if (rd->bk != 0xA0000003u || rf->bk != 0xA0000013u)
                bad |= DROP_BACKUP;
            if (!rf->locked || rp->locked)
                bad |= DROP_LOCK;
            if (rf->clen != (int)strlen(cmt) || memcmp(rf->comment, cmt, strlen(cmt)) ||
                rd->clen != (int)strlen(fcmt) || memcmp(rd->comment, fcmt, strlen(fcmt)) ||
                rp->clen)
                bad |= DROP_COMMENT;
            if (rd->cr != 0xA0000001u || rd->md != 0xA0000002u ||
                rf->cr != 0xA0000011u || rf->md != 0xA0000012u)
                bad |= DROP_DIRMD;
            fprintf(stderr, "meta [drop %s]: failing checks 0x%02x\n",
                    controls[k].what, bad);
            if (controls[k].bit == 0 ? bad != 0 : !(bad & (unsigned)controls[k].bit)) {
                fprintf(stderr, "meta [drop %s]: %s\n", controls[k].what,
                        controls[k].bit ? "the check PASSED without the write"
                                        : "FAILED");
                ok = 0;
            }
        }
        gDrop = 0;
        /* No Desktop Manager on the volume — a System 6 disk: the comment
         * is not written, nothing else changes, nothing is reported. */
        {
            MacSink sk2; UncEntryInfo info;
            char dir[600];
            snprintf(dir, sizeof dir, "%s/nodt", base);
            mkdir(dir, 0755);
            snprintf(gOutDir, sizeof gOutDir, "%s", dir);
            snprintf(gDirs[0], sizeof gDirs[0], "%s", gOutDir);
            gNumDirs = 1;
            gHasDT = 0; gDTSetCalls = 0;
            RepReset();
            memset(&sk2, 0, sizeof sk2); sk2.vRefNum = 1; sk2.rootDirID = 0;
            memset(&info, 0, sizeof info);
            memcpy(info.name, "Doc", 3); info.name_len = 3;
            info.comment = (const uint8_t *)cmt;
            info.comment_len = (uint16_t)strlen(cmt);
            if (sink_begin(&sk2, &info) == 0) sink_end(&sk2, UNC_OK);
            if (gDTSetCalls || gRepN || sk2.errors) {
                fprintf(stderr, "meta [no Desktop Manager]: %d SetComment "
                        "call(s), %d report line(s), %d error(s)\n",
                        gDTSetCalls, (int)gRepN, sk2.errors);
                ok = 0;
            } else
                fprintf(stderr, "meta [no Desktop Manager]: no comment "
                        "written, nothing reported\n");
            gHasDT = 1;
        }
        fprintf(stderr, "meta: %s\n", ok ? "every field written, every "
                "control caught" : "FAILED");
        return ok ? 0 : 1;
    }
    if (argc >= 2 && strcmp(argv[1], "--utf8") == 0) {
        /* The fold a UTF-8 name goes through before it can be an HFS
         * name (Utf8ToMacRoman in mac/macextract_mac.c).
         *
         * Driven through sink_begin directly, the way --cancel is,
         * because the only format that sets `name_utf8` is StuffIt 5
         * and nothing here writes one: a synthetic archive would have
         * to be invented, and what is under test is the SHELL. That
         * the engine sets the flag at all is what the differential
         * suite grades, over the corpus's own StuffIt 5 archives.
         *
         * Every name is written as escapes so this file stays ASCII.
         * What each one is: see tools/run_macnames.py, which asserts
         * on the files and on the report lines printed below. */
        static const struct { const char *name; int utf8; } cases[] = {
            /* U+0192 'f with hook' — MacRoman 0xC4, the folder mark a
             * Mac user types. Folds, and loses nothing. */
            { "Cool Tools \xc6\x92/Cool Tools doc",              1 },
            /* Three Japanese characters MacRoman has no byte for. */
            { "\xe8\xaa\xad\xe3\x82\x93\xe3\x81\xa7.rtf", 1 },
            /* A folder that loses characters, holding a file that does
             * not: one line, about the folder. */
            { "\xe3\x81\x82\xe3\x81\x84/plain",              1 },
            /* 16 x U+00E9: 32 bytes of UTF-8, 16 of MacRoman, so the
             * 31-character cut must happen AFTER the fold. */
            { "\xc3\xa9\xc3\xa9\xc3\xa9\xc3\xa9\xc3\xa9\xc3\xa9"
              "\xc3\xa9\xc3\xa9\xc3\xa9\xc3\xa9\xc3\xa9\xc3\xa9"
              "\xc3\xa9\xc3\xa9\xc3\xa9\xc3\xa9",          1 },
            /* Another unwritable character: same disk name as case 2's
             * sibling below, so the collision numbering acts. */
            { "\xe3\x81\x82.txt",                               1 },
            { "\xe3\x81\x84.txt",                               1 },
            /* The same bytes with the flag CLEAR — StuffIt classic —
             * pass through untouched. */
            { "\xc6\x92 classic",                                0 }
        };
        size_t c;
        snprintf(gOutDir, sizeof gOutDir, "%s",
                 argc >= 3 ? argv[2] : "/tmp/utf8_out");
        mkdir(gOutDir, 0755);
        snprintf(gDirs[0], sizeof gDirs[0], "%s", gOutDir);
        RepReset();
        for (c = 0; c < sizeof cases / sizeof cases[0]; c++) {
            MacSink s; UncEntryInfo info;
            memset(&s, 0, sizeof s); s.vRefNum = 1; s.rootDirID = 0;
            memset(&info, 0, sizeof info);
            info.name_len = (uint16_t)strlen(cases[c].name);
            memcpy(info.name, cases[c].name, info.name_len);
            info.name_utf8 = (uint8_t)cases[c].utf8;
            info.data_size = 0; info.rsrc_size = 0; info.is_dir = 0;
            if (sink_begin(&s, &info) == 0) sink_end(&s, UNC_OK);
        }
        {
            short i;
            for (i = 0; i < gRepN; i++)
                fprintf(stderr, "report: %.*s\n", (int)gRepLen[i],
                        gRepBuf + gRepStart[i]);
        }
        return 0;
    }
    if (argc >= 2 && strcmp(argv[1], "--shortfall") == 0) {
        /* The number the low-memory alert quotes.
         *
         * mal_alloc records the LARGEST amount by which a request exceeded
         * the remaining budget, and the Mac shell turns that into "Needs
         * NNNK more memory" — the one thing a user can act on. The alert
         * itself is UI and is not compiled here, but the arithmetic behind
         * it is, and it is the half that can silently go wrong.
         *
         * Deliberately exact rather than "greater than zero": a shortfall
         * that is merely non-zero would still pass if the sign, the +16
         * header or the choice of largest-so-far were wrong. */
        MacAlloc a;
        long want = 100000L;
        int ok = 1;
        a.budget = a.initial = 40000L;
        a.lowmark = a.budget;
        a.taken = 1;      /* an imposed budget: see mal_take_budget */
        gShortBy = 0;
        if (mal_alloc(&a, (uint32_t)want) != NULL) {
            fprintf(stderr, "shortfall: the over-budget request was ALLOWED\n");
            ok = 0;
        }
        if (gShortBy != want + 16 - 40000L) {
            fprintf(stderr, "shortfall: got %ld, wanted %ld\n",
                    gShortBy, want + 16 - 40000L);
            ok = 0;
        }
        /* A second, smaller shortfall must not displace the larger one. */
        if (mal_alloc(&a, (uint32_t)50000L) == NULL && gShortBy != want + 16 - 40000L) {
            fprintf(stderr, "shortfall: a smaller refusal overwrote the largest\n");
            ok = 0;
        }
        fprintf(stderr, "shortfall: %ld bytes reported for a %ld request "
                        "against a %ld budget\n", gShortBy, want, 40000L);
        return ok ? 0 : 1;
    }
    if (argc >= 2 && strcmp(argv[1], "--eta") == 0) {
        /* The time left must not go back up on a run whose rate never
         * changes. Replays an extraction exactly linear in time at the
         * engine's real cadence: done moves in 8 KB steps and the dialog
         * reads it at most every 6 ticks. Run on qemu-m68k too, where a
         * long is the target's 32 bits. The percentage-based formula this
         * replaced rose by up to 65 minutes here (DECISIONS.md 2026-10-16,
         * *the estimate that went back up*).
         *
         * 2 s of slack: one tick of elapsed time is (t-d)/d ticks of
         * estimate, 1.65 s at 1%, and that is TickCount's resolution, not
         * the formula's. It can still turn a rounded minute over — once
         * in the 4-hour, 400 MB case. Cannot see a rate that really
         * changes, where a rise is the right answer. */
        static const long mins[] = { 2, 16, 60, 240 };
        static const uint32_t totals[] = { 40000UL, 3000000UL, 40000000UL,
                                           400000000UL };
        int ok = 1;
        unsigned i, j;
        for (i = 0; i < sizeof mins / sizeof mins[0]; i++)
            for (j = 0; j < sizeof totals / sizeof totals[0]; j++) {
                long ticks = mins[i] * 3600L, last = -1, lastNow = -6;
                long rises = 0, worst = 0;
                uint32_t total = totals[j], done;
                for (done = 8192; done <= total; done += 8192) {
                    long now = (long)((long long)ticks * done / total);
                    long rem;
                    if (now - lastNow < 6) continue;
                    lastNow = now;
                    (void)ProgressReading(now, done, total, &rem);
                    if (rem < 0) continue;
                    if (last >= 0 && rem > last + 2) {
                        rises++;
                        if (rem - last > worst) worst = rem - last;
                    }
                    last = rem;
                }
                if (rises) {
                    fprintf(stderr, "eta: %ld min, %lu bytes: the time left "
                            "went up %ld times, by up to %ld s\n", mins[i],
                            (unsigned long)total, rises, worst);
                    ok = 0;
                }
            }
        fprintf(stderr, "eta: %s\n", ok ? "never goes up on a linear run"
                                        : "FAILED");
        return ok ? 0 : 1;
    }
    if (argc < 3) { fprintf(stderr, "usage: %s <archive> <outdir>\n", argv[0]); return 2; }
#ifdef UNC_AT_OVERLAY
    if (ovlbox_load_manifest(getenv("OVLBOX_IMAGES")) <= 0) {
        fprintf(stderr, "overlay lane: no images registered — $OVLBOX_IMAGES "
                        "is %s\n", getenv("OVLBOX_IMAGES") ? getenv("OVLBOX_IMAGES")
                                                           : "unset");
        return 2;
    }
    ovl_preload();
#endif
    snprintf(gOutDir, sizeof gOutDir, "%s", argv[2]);
    mkdir(gOutDir, 0755);
    snprintf(gDirs[0], sizeof gDirs[0], "%s", gOutDir);   /* dir id 0 */

    srcfd = open(argv[1], O_RDONLY);
    if (srcfd < 0) { perror("open source"); return 1; }
    fstat(srcfd, &st);
    srcslot = alloc_slot(srcfd);
    mio.refNum = (short)srcslot;
    mio.size = (long)st.st_size;

    /* Default: file-backed mio_* IO. If argv[3]=="ram", exercise the exact
     * RAM-slurp + xio_* path the real Mac app uses (RunExtract), which the
     * file-backed path never covers. */
    {
        static MemIO mem;   /* static so it stays valid through the call */
        if (argc >= 4 && strcmp(argv[3], "ram") == 0) {
            Ptr abuf = NewPtr((long)st.st_size);
            long remaining = (long)st.st_size, off = 0;
            long c;
            while (remaining > 0) {
                c = remaining;
                if (FSRead(mio.refNum, &c, abuf + off) != noErr && c <= 0) break;
                off += c; remaining -= c;
            }
            mem.data = (const uint8_t *)abuf;
            mem.size = (uint32_t)st.st_size;
            mem.pos = 0;
            io.ctx = &mem; io.read = xio_read; io.seek = xio_seek;
            io.tell = xio_tell; io.size = xio_size;
        } else {
            io.ctx = &mio; io.read = mio_read; io.seek = mio_seek;
            io.tell = mio_tell; io.size = mio_size;
        }
    }

    /* The same rule the shell uses: a quarter of free, clamped. See the
     * kMemReserve comment in mac/macextract_mac.c for why it is not a
     * constant any more. */
    {
        long reserve = FreeMem() / 4;
        if (reserve > kMemReserveMax) reserve = kMemReserveMax;
        if (reserve < kMemReserveMin) reserve = kMemReserveMin;
        ma.budget = FreeMem() - reserve;
        ma.initial = ma.budget;
        ma.lowmark = ma.budget;
        /* This test imposes its own budget, so mal_alloc must not go and take
         * one at the first allocation (mal_take_budget). */
        ma.taken = 1;
    }
    al.ctx = &ma; al.alloc = mal_alloc; al.free = mal_free;

    memset(&sink, 0, sizeof sink);
    sink.vRefNum = 1; sink.rootDirID = 0;
    sk.ctx = &sink; sk.begin_entry = sink_begin;
    sk.write = sink_write; sk.end_entry = sink_end;
    /* The Mac shell's own comment writer, mock Toolbox and all: an
     * archive comment lands as a "Comments" file in the destination
     * folder, and tools/check_mac_sink.py compares it with what the
     * oracle read out of the same archive. */
    sk.comment = sink_comment;

    memset(&opt, 0, sizeof opt);

#ifdef UNC_AT_OVERLAY
    /* The two calls mac/macextract_mac.c makes, in its order: preload while
     * the boot disk is certainly in, then release what the sniffed format
     * cannot want, before the engine's first allocation. An overlay build that
     * skipped the release would pass every byte-exactness test and lose the
     * whole mechanism, which is what happened on the branch for a week
     * (DECISIONS.md 2026-09-25, *the flush nobody wrote*). */
    ovl_release_if_unwanted(unc_sniff(&io), &io);
    fprintf(stderr, "overlay: %ld read(s), %ld flush(es) so far\n",
            ovlbox_reads, ovlbox_flushes);
#endif

    ret = unc_extract(&io, &sk, &al, NULL, &opt);
    fprintf(stderr, "unc_extract -> %d, entries=%d errors=%d\n",
            ret, sink.entries, sink.errors);
    /* The run report, exactly as the Macintosh box would list it: what
     * this shell renamed and what failed per entry. The box itself
     * cannot be tested here — its lines can, and they are the half that
     * says something wrong (tools/run_macnames.py). */
    {
        short i;
        for (i = 0; i < gRepN; i++)
            fprintf(stderr, "report: %.*s\n", (int)gRepLen[i],
                    gRepBuf + gRepStart[i]);
        if (gRepMore)
            fprintf(stderr, "report-more: %ld\n", gRepMore);
    }
    return ret == UNC_OK && sink.errors == 0 ? 0 : 1;
}
