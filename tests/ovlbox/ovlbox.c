/* ovlbox.c — a Memory Manager and a Resource Manager the overlay loaders can
 * run against off the Macintosh.
 *
 * WHY THIS EXISTS. The application ships fifteen 'OVLY' images and until
 * 2026-09-26 no automated test reached one: the images exist only in a
 * Retro68 build, so every Linux suite exercises the decoders as ordinary
 * linked code, and whether an image is found, relocated, kept, released or
 * re-read was answered by emulator tiers, by hand, at minutes per fixture
 * (OPEN_ITEMS.md, *The overlay loader*). Three defects have lived there.
 *
 * So the real loaders — mac/ovl_load_eager.c, mac/ovl_load_lazy.c,
 * mac/ovl_reloc.c, mac/ovl_shim.c, unmodified — are compiled against the stub
 * Toolbox headers beside this file and run here.
 *
 * WHAT THIS MOCK DOES THAT A MACINTOSH DOES NOT, deliberately:
 *
 *   - every unlocked block MOVES on every allocation. The Memory Manager
 *     compacts only when it has to, so a loader that dereferences an unlocked
 *     handle works there most of the time and fails on a full heap;
 *   - every block gets a GUARD PAGE immediately after its last byte, so a
 *     relocation offset or a copy past the image end faults at the write
 *     rather than corrupting a neighbour. The trailer's own guard
 *     (`off + 4 > table`) is what this is aimed at;
 *   - a released resource is really gone, and the next GetResource is COUNTED
 *     as a fresh read. That count is how the two lifetimes are told apart.
 *
 * WHAT IT CANNOT SEE, and the reason the emulator tiers stay:
 *
 *   - no instruction cache, on either host. The flush is counted, never
 *     needed. MANUAL_TESTS.md is the only instrument for whether it works;
 *   - no Resource Manager, so a real GetResource's purging, its resource map
 *     and the file it reads from are all absent;
 *   - no FRAGMENTATION model. The mock always finds room; a Macintosh's
 *     "Memory is too broken up" is tools/run_tiers.py's blind spot too;
 *   - not the Retro68 toolchain's code generation. The images here are built
 *     by m68k-linux-gnu-gcc from the same sources with the same flags, which
 *     is the same COMPILER FAMILY and not the same compiler;
 *   - nothing about the interface: no alert, no grid, no report.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/mman.h>

#include "ovlbox.h"
#include "toolbox/OSUtils.h"

long ovlbox_reads, ovlbox_flushes, ovlbox_moves, ovlbox_handles;

static int gShuffle = 1;
static int gFlushRoute = 1;
static short gROM85 = 1;          /* >0: a 128K ROM, so a trap can exist */

#define MAX_BLK   64
#define MAX_RES   32

/* One mapping per block, with the block's last byte flush against a guard
 * page. `cell` is the master pointer; a Handle is its address, which is why
 * these live in a static array and are never moved themselves. */
typedef struct Blk {
    Ptr    cell;
    void  *map;
    size_t maplen;
    Size   size;
    int    inuse, locked;
    short  resid;                 /* -1 if not a resource */
} Blk;

static Blk gBlk[MAX_BLK];
static long gLive, gPeak;

typedef struct Res {
    short  id;
    void  *bytes;
    size_t len;
    Blk   *open;                  /* the handle this resource is loaded in */
    int    used;
} Res;

static Res gRes[MAX_RES];

static size_t pagesize(void)
{
    static size_t ps;
    if (!ps) ps = (size_t)sysconf(_SC_PAGESIZE);
    return ps;
}

/* PROT_EXEC because an image IS code: the m68k lane calls its entry point
 * through the handle, exactly as the application does. */
static void *map_block(size_t size, size_t *maplen_out, void **data_out)
{
    size_t ps = pagesize();
    size_t body = ((size + ps - 1) / ps) * ps;
    size_t maplen = body + ps;
    void *m = mmap(NULL, maplen, PROT_READ | PROT_WRITE | PROT_EXEC,
                   MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (m == MAP_FAILED) return NULL;
    if (mprotect((char *)m + body, ps, PROT_NONE) != 0) {
        munmap(m, maplen);
        return NULL;
    }
    *maplen_out = maplen;
    *data_out = (char *)m + body - size;   /* last byte abuts the guard */
    return m;
}

/* Move every unlocked block. Called from each allocation, which is where a
 * Macintosh would compact. */
static void shuffle(void)
{
    int i;
    if (!gShuffle) return;
    for (i = 0; i < MAX_BLK; i++) {
        Blk *b = &gBlk[i];
        void *m, *data;
        size_t maplen;
        if (!b->inuse || b->locked) continue;
        m = map_block((size_t)b->size, &maplen, &data);
        if (m == NULL) continue;          /* out of room: leave it be */
        memcpy(data, b->cell, (size_t)b->size);
        munmap(b->map, b->maplen);
        b->map = m; b->maplen = maplen; b->cell = (Ptr)data;
        ovlbox_moves++;
    }
}

static Blk *blk_new(Size n, short resid)
{
    int i;
    shuffle();
    for (i = 0; i < MAX_BLK; i++) {
        Blk *b = &gBlk[i];
        void *m, *data;
        size_t maplen;
        if (b->inuse) continue;
        m = map_block((size_t)n, &maplen, &data);
        if (m == NULL) return NULL;
        b->map = m; b->maplen = maplen; b->cell = (Ptr)data;
        b->size = n; b->inuse = 1; b->locked = 0; b->resid = resid;
        gLive += (long)n;
        if (gLive > gPeak) gPeak = gLive;
        ovlbox_handles++;
        return b;
    }
    return NULL;
}

static Blk *blk_of(Handle h)
{
    int i;
    for (i = 0; i < MAX_BLK; i++)
        if (gBlk[i].inuse && (Handle)&gBlk[i].cell == h) return &gBlk[i];
    return NULL;
}

static void blk_free(Blk *b)
{
    int i;
    if (b == NULL || !b->inuse) return;
    for (i = 0; i < MAX_RES; i++)
        if (gRes[i].used && gRes[i].open == b) gRes[i].open = NULL;
    munmap(b->map, b->maplen);
    gLive -= (long)b->size;
    ovlbox_handles--;
    memset(b, 0, sizeof *b);
}

/* ---- Memory Manager ------------------------------------------------- */

Handle NewHandle(Size n)
{
    Blk *b = blk_new(n, -1);
    return b ? (Handle)&b->cell : NULL;
}

void DisposeHandle(Handle h) { blk_free(blk_of(h)); }

Size GetHandleSize(Handle h)
{
    Blk *b = blk_of(h);
    return b ? b->size : 0;
}

void HLock(Handle h)   { Blk *b = blk_of(h); if (b) b->locked = 1; }
void HUnlock(Handle h) { Blk *b = blk_of(h); if (b) b->locked = 0; }
void HNoPurge(Handle h) { (void)h; }

/* A Macintosh moves the block as high in the heap as it can; what matters to
 * a loader is that it MOVES, and that it must not be locked when it does.
 * A locked block is left where it is here, exactly as there. */
void MoveHHi(Handle h)
{
    Blk *b = blk_of(h);
    void *m, *data;
    size_t maplen;
    if (b == NULL || b->locked) return;
    m = map_block((size_t)b->size, &maplen, &data);
    if (m == NULL) return;
    memcpy(data, b->cell, (size_t)b->size);
    munmap(b->map, b->maplen);
    b->map = m; b->maplen = maplen; b->cell = (Ptr)data;
    ovlbox_moves++;
}

OSErr MemError(void) { return 0; }

/* ---- Resource Manager ----------------------------------------------- */

int ovlbox_add_resource(short id, const void *bytes, size_t len)
{
    int i;
    for (i = 0; i < MAX_RES; i++) {
        if (gRes[i].used) continue;
        gRes[i].bytes = malloc(len ? len : 1);
        if (gRes[i].bytes == NULL) return 0;
        memcpy(gRes[i].bytes, bytes, len);
        gRes[i].len = len; gRes[i].id = id; gRes[i].used = 1;
        gRes[i].open = NULL;
        return 1;
    }
    return 0;
}

/* The images a build just wrote, by resource id. The manifest is written by
 * the harness from tools/overlay/images.py's inventory, which is read out of
 * mac/CMakeLists.txt — so what is registered here is what the Macintosh
 * loads, and a fifteenth image cannot appear in the build and be missing
 * from this lane without images.py failing first. */
int ovlbox_load_manifest(const char *path)
{
    char line[1024];
    FILE *f;
    int n = 0;
    if (path == NULL || *path == 0) return -1;
    f = fopen(path, "r");
    if (f == NULL) return -1;
    while (fgets(line, sizeof line, f) != NULL) {
        char file[900];
        int id;
        FILE *g;
        long len;
        void *buf;
        if (sscanf(line, "%d %899s", &id, file) != 2) continue;
        g = fopen(file, "rb");
        if (g == NULL) { fclose(f); return -1; }
        fseek(g, 0, SEEK_END);
        len = ftell(g);
        fseek(g, 0, SEEK_SET);
        buf = malloc((size_t)(len ? len : 1));
        if (buf == NULL || fread(buf, 1, (size_t)len, g) != (size_t)len) {
            free(buf); fclose(g); fclose(f); return -1;
        }
        fclose(g);
        if (!ovlbox_add_resource((short)id, buf, (size_t)len)) {
            free(buf); fclose(f); return -1;
        }
        free(buf);
        n++;
    }
    fclose(f);
    return n;
}

Handle GetResource(ResType type, short id)
{
    int i;
    if (type != 0x4F564C59UL /* 'OVLY' */) return NULL;
    for (i = 0; i < MAX_RES; i++) {
        Res *r = &gRes[i];
        Blk *b;
        if (!r->used || r->id != id) continue;
        if (r->open) return (Handle)&r->open->cell;   /* already in memory */
        b = blk_new((Size)r->len, id);
        if (b == NULL) return NULL;
        memcpy(b->cell, r->bytes, r->len);
        r->open = b;
        ovlbox_reads++;               /* the disk access a Mac would pay */
        return (Handle)&b->cell;
    }
    return NULL;
}

void ReleaseResource(Handle h) { blk_free(blk_of(h)); }

void DetachResource(Handle h)
{
    Blk *b = blk_of(h);
    int i;
    if (b == NULL) return;
    for (i = 0; i < MAX_RES; i++)
        if (gRes[i].used && gRes[i].open == b) gRes[i].open = NULL;
    b->resid = -1;
}

short ResError(void) { return 0; }

/* ---- Traps and the low-memory global -------------------------------- */

static long gTrapSlot[3];

void *GetOSTrapAddress(unsigned short trap)
{
    if (trap == _Unimplemented) return &gTrapSlot[0];
    if (trap == _HWPriv)   return gFlushRoute == 1 ? &gTrapSlot[1] : &gTrapSlot[0];
    if (trap == 0xA0BD)    return gFlushRoute == 2 ? &gTrapSlot[2] : &gTrapSlot[0];
    return &gTrapSlot[0];
}

void HWPriv(short selector, long arg)
{
    (void)selector; (void)arg;
    ovlbox_flushes++;
}

void FlushCodeCache(void) { ovlbox_flushes++; }

const void *ovlbox_rom85(void) { return &gROM85; }

void ovlbox_set_flush_route(int route)
{
    gFlushRoute = route;
    gROM85 = route ? 1 : -1;       /* route 0 is a 64K ROM: neither trap */
}

void ovlbox_set_shuffle(int on) { gShuffle = on; }

void ovlbox_stats(long *live, long *peak)
{
    if (live) *live = gLive;
    if (peak) *peak = gPeak;
}
