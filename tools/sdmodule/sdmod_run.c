/*
 * sdmod_run.c — run Alysis "SuperDisk! Add-In Modules" as subroutines.
 *
 * The modules are 68k code with no Toolbox in them: an entry that reads a
 * selector out of a parameter block, decodes a block, and writes the length
 * back. That makes them runnable OFF the Macintosh — built for m68k-linux and
 * executed under `qemu-m68k`, the same way the cipher vectors already run
 * (tests/run_mac_sink.sh). No emulator, no boot, no screenshot.
 *
 *   Source: the caller is `INIT 32` of the Disk Expander 1.2 extension —
 *   the expand path at 0x5054..0x50a6 fills the block, and the dispatcher at
 *   0x50c8 picks a module by method. The fields below are the ones it sets.
 *
 *     +0  (4) source: the block's length word, its method word, then the body
 *     +4  (4) destination buffer — and, AFTER the call, where the output
 *             actually is: "Tighter" ping-pongs between the two buffers and
 *             leaves its result in the one it was given as SOURCE. The
 *             extension reads the pointer back (`moveal %a0@(4),%a0` at
 *             INIT 32 @0x50b8) rather than assuming, and so does this
 *     +12 (4) the context table
 *     +16 (4) its size — 0x2000 narrow, 0x10000 wide
 *     +20 (4) the length being worked on
 *     +24 (4) OUT: bytes produced
 *     +28 (4) a CALLBACK: "decode the region I have just pointed you at"
 *     +36 (2) selector: 1 = "can you?", 3 = expand (2 = compress)
 *     +38 (2) OUT: status, 0 = ok, negative = refused
 *     +40 (2) the method number — which the callback dispatches on
 *     +52 (4) a serial the extension increments per call
 *     +60 (4) OUT: where a sub-decode left its cursor
 *
 * **The callback is not optional.** "Tighter" decodes methods 2, 3, 4, 6, 7
 * and 8, and for the Huffman-coded flag bitmap it points the parameter block
 * at the region, writes 9 into +40 and JSRs through +28 — so without a
 * dispatcher on the other end it jumps to address zero. `sd_callback` below
 * is that dispatcher, and it maps methods the way INIT 32 @0x50c8 does.
 *
 * A module is position-independent (it takes its own base with `lea
 * %pc@(0),%a4`), so it runs wherever it is put.
 *
 * Usage:  sdmod_run <manifest> <src> <out> [selector] [method] [cap] [prefix]
 *
 * The manifest is one `<method> <entry> <path>` per line; the first line is
 * the module called directly and the rest are reachable through the callback.
 * `prefix` is the fork decoded SO FAR: these decoders reach backwards into
 * what they have already produced, and the extension decodes a fork into one
 * buffer block after block, so the second block of a fork is only decodable
 * with the first one in front of it.
 *
 * One line of key=value goes to stdout, and the whole parameter block with
 * it, so the caller can read fields this program does not name.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#include <signal.h>
#include <sys/mman.h>

#define PB_SIZE    64
#define MAX_MODS   16
#define SLACK      (64u * 1024u)   /* room past the declared output: these
                                    * decoders over-produce on purpose */

static jmp_buf  g_escape;
static volatile int g_signal;

static struct { unsigned method; unsigned char *code; } g_mods[MAX_MODS];
static int g_nmods;

static void on_signal(int sig)
{
    g_signal = sig;
    longjmp(g_escape, 1);
}

static unsigned char *slurp(const char *path, size_t *len)
{
    FILE *f = fopen(path, "rb");
    unsigned char *b;
    long n;
    if (!f) { perror(path); exit(2); }
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    b = malloc((size_t)n + 1);
    if (!b || fread(b, 1, (size_t)n, f) != (size_t)n) { perror(path); exit(2); }
    fclose(f);
    *len = (size_t)n;
    return b;
}

/* Call a module with A0 pointing at the parameter block. Everything is
 * callee-saved by the module itself (it opens with MOVEM.L D0-A6,-(SP)),
 * but the clobber list says so anyway. */
static void call_module(void *code, void *pb)
{
    __asm__ __volatile__(
        "movea.l %0,%%a0\n\t"
        "movea.l %1,%%a1\n\t"
        "jsr (%%a1)"
        :
        : "r"(pb), "r"(code)
        : "d0", "d1", "d2", "a0", "a1", "memory", "cc");
}

static unsigned get16(const unsigned char *p) { return (unsigned)((p[0] << 8) | p[1]); }

static unsigned char *pick(unsigned method, unsigned selector)
{
    /* INIT 32 @0x50c8: on expand, methods 1 and 5 go to "Faster", anything
     * else below 9 to "Tighter", and 9 and up to the module that names that
     * method. The narrow/wide pair share a module and tell themselves apart
     * from the method byte in the block. */
    unsigned want = method;
    int i;
    if (selector == 3 && method < 9)
        want = (method == 1 || method == 5) ? 1u : 2u;
    for (i = 0; i < g_nmods; i++)
        if (g_mods[i].method == want) return g_mods[i].code;
    return NULL;
}

/* The other end of +28. Called from the shim below with the module's own
 * parameter block, which already says what it wants decoded. */
void sd_dispatch(unsigned char *pb);
void sd_dispatch(unsigned char *pb)
{
    unsigned method = get16(pb + 40);
    unsigned selector = get16(pb + 36);
    unsigned char *code = pick(method, selector);
    if (!code) {                         /* "no module for that" */
        pb[38] = 0xFF; pb[39] = 0xFF;
        return;
    }
    call_module(code, pb);
}

/* A0 is the parameter block and there is no way to say that in C, so the
 * shim is written out. Everything is preserved: the caller is in the middle
 * of a decode and expects its registers back. */
__asm__(
    "       .globl sd_callback\n"
    "sd_callback:\n"
    "       movem.l %d0-%d7/%a0-%a6,-(%sp)\n"
    "       move.l  %a0,-(%sp)\n"
    "       jsr     sd_dispatch\n"
    "       addq.l  #4,%sp\n"
    "       movem.l (%sp)+,%d0-%d7/%a0-%a6\n"
    "       rts\n");
extern void sd_callback(void);

static void put32(unsigned char *p, unsigned long v)
{
    p[0] = (unsigned char)(v >> 24); p[1] = (unsigned char)(v >> 16);
    p[2] = (unsigned char)(v >> 8);  p[3] = (unsigned char)v;
}

static void put16(unsigned char *p, unsigned v)
{
    p[0] = (unsigned char)(v >> 8); p[1] = (unsigned char)v;
}

static unsigned long get32(const unsigned char *p)
{
    return ((unsigned long)p[0] << 24) | ((unsigned long)p[1] << 16) |
           ((unsigned long)p[2] << 8) | p[3];
}

static int get16s(const unsigned char *p)
{
    int v = (int)get16(p);
    return v >= 0x8000 ? v - 0x10000 : v;
}

/* Load every module the manifest names; the first one is the entry point. */
static unsigned char *load_manifest(const char *path)
{
    char line[1024];
    unsigned char *first = NULL;
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); exit(2); }
    while (fgets(line, sizeof line, f)) {
        unsigned method, entry;
        char file[900];
        unsigned char *code, *blob;
        size_t len;
        if (sscanf(line, "%u %u %899s", &method, &entry, file) != 3) continue;
        if (g_nmods >= MAX_MODS) break;
        blob = slurp(file, &len);
        code = mmap(NULL, (len + 4095) & ~4095u,
                    PROT_READ | PROT_WRITE | PROT_EXEC,
                    MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (code == MAP_FAILED) { perror("mmap"); exit(2); }
        memcpy(code, blob, len);
        free(blob);
        g_mods[g_nmods].method = method;
        g_mods[g_nmods].code = code + entry;
        if (!first) first = code + entry;
        g_nmods++;
    }
    fclose(f);
    if (!first) { fprintf(stderr, "sdmod_run: no modules in %s\n", path); exit(2); }
    return first;
}

int main(int argc, char **argv)
{
    unsigned char *src, *dst, *table, *arena, *pre = NULL, pb[PB_SIZE];
    unsigned char *entry, *outp;
    size_t srclen, prelen = 0, srcroom, dstroom;
    unsigned long cap, tablesize;
    unsigned selector, method;
    int i;
    FILE *out;

    if (argc < 4) {
        fprintf(stderr, "usage: %s <manifest> <src> <out> "
                        "[selector] [method] [cap] [prefix]\n", argv[0]);
        return 2;
    }
    entry = load_manifest(argv[1]);
    src = slurp(argv[2], &srclen);
    selector = argc > 4 ? (unsigned)strtoul(argv[4], NULL, 0) : 3u;
    method   = argc > 5 ? (unsigned)strtoul(argv[5], NULL, 0) : 0u;
    cap      = argc > 6 ? strtoul(argv[6], NULL, 0) : 0x8000u;
    if (argc > 7) pre = slurp(argv[7], &prelen);

    /* The wide methods index a 64K table, the narrow ones 8K; the module
     * refuses a wide block if +16 says the table is too small. */
    tablesize = (method >= 5 && method <= 8) ? 0x10000u : 0x2000u;

    /* Source and destination live in ONE mapping, because the modules hand
     * each other buffers and the output can come back in either. The source
     * gets slack of its own: a module that decodes into its input needs the
     * room the extension's scratch buffer had. */
    srcroom = srclen + cap + SLACK;
    dstroom = prelen + cap + SLACK;
    arena = mmap(NULL, srcroom + dstroom, PROT_READ | PROT_WRITE,
                 MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    table = mmap(NULL, 0x20000, PROT_READ | PROT_WRITE,
                 MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (arena == MAP_FAILED || table == MAP_FAILED) { perror("mmap"); return 2; }
    memset(arena, 0, srcroom + dstroom);
    memset(table, 0, 0x20000);
    memcpy(arena, src, srclen);
    dst = arena + srcroom;
    if (prelen) { memcpy(dst, pre, prelen); dst += prelen; }

    memset(pb, 0, sizeof pb);
    put32(pb + 0,  (unsigned long)(size_t)arena);
    put32(pb + 4,  (unsigned long)(size_t)dst);
    put32(pb + 12, (unsigned long)(size_t)table);
    put32(pb + 16, tablesize);
    put32(pb + 20, cap);
    put32(pb + 28, (unsigned long)(size_t)sd_callback);
    put16(pb + 36, selector);
    put16(pb + 40, method);

    signal(SIGSEGV, on_signal);
    signal(SIGBUS,  on_signal);
    signal(SIGILL,  on_signal);
    signal(SIGFPE,  on_signal);
    if (setjmp(g_escape) == 0) {
        call_module(entry, pb);
    } else {
        printf("signal=%d\n", g_signal);
        return 3;
    }

    printf("status=%d len=%lu pb=", get16s(pb + 38), get32(pb + 24));
    for (i = 0; i < PB_SIZE; i++) printf("%02x", pb[i]);
    printf("\n");

    out = fopen(argv[3], "wb");
    if (!out) { perror(argv[3]); return 2; }
    {
        unsigned long n = get32(pb + 24);
        outp = (unsigned char *)(size_t)get32(pb + 4);
        if (outp < arena || outp >= arena + srcroom + dstroom)
            outp = dst;                       /* not ours: fall back */
        if (n > (unsigned long)(arena + srcroom + dstroom - outp))
            n = (unsigned long)(arena + srcroom + dstroom - outp);
        /* SDMOD_FULL dumps everything from there instead of what the module
         * says it produced — for working out where a module actually put
         * its output. */
        if (getenv("SDMOD_FULL"))
            n = (unsigned long)(arena + srcroom + dstroom - outp);
        fwrite(outp, 1, n, out);
    }
    fclose(out);
    return 0;
}
