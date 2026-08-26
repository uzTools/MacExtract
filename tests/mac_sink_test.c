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

#include "../mac/mac_mocks.h"
#include "macextract.h"

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
    return noErr;
}
OSErr PBHDeleteSync(HParamBlockRec *pb)
{
    char path[800], rpath[820];
    full_path(pb->fileParam.ioDirID, pb->ioParam.ioNamePtr, 0, path,
              sizeof path);
    full_path(pb->fileParam.ioDirID, pb->ioParam.ioNamePtr, 1, rpath,
              sizeof rpath);
    unlink(rpath);                     /* resource-fork sidecar, if any */
    return unlink(path) == 0 ? noErr : fnfErr;
}

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
OSErr PBGetCatInfoSync(CInfoPBRec *pb) { (void)pb; return noErr; }
OSErr PBSetCatInfoSync(CInfoPBRec *pb) { (void)pb; return noErr; }
OSErr PBDirCreateSync(HParamBlockRec *pb)
{
    char path[800];
    full_path(pb->fileParam.ioDirID, pb->fileParam.ioNamePtr, 0, path,
              sizeof path);
    mkdir(path, 0755);                 /* tolerate EEXIST */
    if (gNumDirs >= MAX_DIRS) return noErr;
    snprintf(gDirs[gNumDirs], sizeof gDirs[0], "%s", path);
    pb->fileParam.ioDirID = gNumDirs;  /* hand back the new dir id */
    gNumDirs++;
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
    if (argc < 3) { fprintf(stderr, "usage: %s <archive> <outdir>\n", argv[0]); return 2; }
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

    ret = unc_extract(&io, &sk, &al, NULL, &opt);
    fprintf(stderr, "unc_extract -> %d, entries=%d errors=%d\n",
            ret, sink.entries, sink.errors);
    return ret == UNC_OK && sink.errors == 0 ? 0 : 1;
}
