/*
 * dd_run.c — run Salient's own DiskDoubler decoders for methods 2, 5 and 7
 * as subroutines, under qemu-m68k.
 *
 * `DiskDoubler™ App` 3.1.2 (Salient Software, 1991; the file on the
 * distribution floppy, not compressed) carries both software decoders in
 * `CODE` 11, a THINK C segment whose globals are off A5:
 *
 *   CODE 11 @0x221e  the splay-tree decoder, methods 2 and 5:
 *                    (in, out, unused, long outlen, short sum) -> OSErr
 *           @0x1e5c  set the "tree count in the stream" flag (method 5)
 *   CODE 11 @0x34e2  the Stac LZS decoder, method 7:
 *                    (in, out, unused, long outlen, short xor) -> OSErr
 *   CODE 7  @0x0070  the CRC-16 the Stac decoder checks its chunk table
 *                    with, called through the jump table
 *
 * Everything those routines reach outside the two segments goes through
 * the A5 jump table, and this file puts its own stubs there: the byte
 * stream (get a byte, read n, put a byte, flush; a stream is a record whose
 * +0 is the next byte and +8 the last one, which the decoders also read
 * inline), the progress callback (answers 100, "go on"), and the Memory
 * Manager calls the Stac decoder makes for its chunk table (NewHandle,
 * DisposeHandle, GetHandleSize, SetHandleSize, HLock, HUnlock, Pascal
 * glue). The decoders' input is all in memory, so the get-a-byte stub is
 * reached only at the end of the input, where it answers eofErr. The
 * splay trees are handed over allocated (A5-1014, A5-1002 = 256), so the
 * allocation routine at 0x242e takes its early exit. The Stac decoder reads
 * MemErr at 0x220, so low memory is mapped (qemu-m68k -B gives the guest a
 * page 0). Every offset is a file offset into the resource's data, checked
 * by tools/ddcode/run_ddcode.py against the bytes it was read from.
 *
 * Usage:  dd_run <code11> <code7>, then one command per line on stdin:
 *
 *   S <flag5> <xor> <outlen> <sum> <hex input>   methods 2 (flag5 0) / 5
 *   L <outlen> <xor> <hex input>                 method 7
 *
 * Answer: "<OSErr> <hex output>".
 *
 * SPDX-License-Identifier: 0BSD
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#include <signal.h>
#include <sys/mman.h>

#define BELOW 1852            /* CODE 0: the application's globals */
#define ABOVE 2808            /* CODE 0: above A5, jump table at +32 */

static jmp_buf g_escape;
static volatile int g_signal;

unsigned char g_args[32];
long g_nargs;
void *g_fn;
unsigned char *g_a5;
long g_ret;

static void call(void)
{
    __asm__ __volatile__(
        "movem.l %%d2-%%d7/%%a2-%%a6,-(%%sp)\n\t"
        "move.l g_nargs,%%d0\n\t"
        "suba.l %%d0,%%sp\n\t"
        "lea g_args,%%a0\n\t"
        "movea.l %%sp,%%a1\n\t"
        "1: tst.l %%d0\n\t"
        "beq.s 2f\n\t"
        "move.b (%%a0)+,(%%a1)+\n\t"
        "subq.l #1,%%d0\n\t"
        "bra.s 1b\n\t"
        "2: movea.l g_a5,%%a5\n\t"
        "movea.l g_fn,%%a0\n\t"
        "jsr (%%a0)\n\t"
        "adda.l g_nargs,%%sp\n\t"
        "move.l %%d0,g_ret\n\t"
        "movem.l (%%sp)+,%%d2-%%d7/%%a2-%%a6"
        : : : "d0", "d1", "a0", "a1", "memory", "cc");
}

/* ---- the stream ---------------------------------------------------- */

typedef struct Stream { unsigned char *cur, *pad, *end; } Stream;

long c_getbyte(Stream *s)
{
    if (s->cur > s->end) return -39;             /* eofErr */
    return *s->cur++;
}

long c_read(Stream *s, unsigned char *dst, long n)
{
    while (n-- > 0) {
        if (s->cur > s->end) return -39;
        *dst++ = *s->cur++;
    }
    return 0;
}

long c_putbyte(Stream *s, long b)
{
    if (s->cur > s->end) return -34;             /* dskFulErr */
    *s->cur++ = (unsigned char)b;
    return 0;
}

long c_zero(void) { return 0; }
long c_go_on(void) { return 100; }

/* ---- handles ------------------------------------------------------- */

typedef struct Master { unsigned char *p; long size; } Master;

long c_newhandle(long size)
{
    Master *m = calloc(1, sizeof *m);
    m->p = calloc(1, (size_t)size + 1);
    m->size = size;
    return (long)m;
}

void c_dispose(Master *m) { free(m->p); free(m); }
long c_gethsize(Master *m) { return m->size; }
void c_sethsize(Master *m, long size)
{
    m->p = realloc(m->p, (size_t)size + 1);
    m->size = size;
}

/* THINK C's own calls: arguments on the stack, the answer in D0, the
 * caller pops. A word argument is a word. */
__asm__(
    ".globl s_getbyte\n s_getbyte:\n"
    "  move.l 4(%sp),-(%sp)\n jsr c_getbyte\n addq.l #4,%sp\n rts\n"
    ".globl s_read\n s_read:\n"
    "  move.l 12(%sp),-(%sp)\n move.l 12(%sp),-(%sp)\n move.l 12(%sp),-(%sp)\n"
    "  jsr c_read\n lea 12(%sp),%sp\n rts\n"
    ".globl s_putbyte\n s_putbyte:\n"
    "  moveq #0,%d0\n move.w 8(%sp),%d0\n move.l %d0,-(%sp)\n"
    "  move.l 8(%sp),-(%sp)\n jsr c_putbyte\n addq.l #8,%sp\n rts\n"
    ".globl s_zero\n s_zero:\n moveq #0,%d0\n rts\n"
    ".globl s_go_on\n s_go_on:\n moveq #100,%d0\n rts\n"
/* The Toolbox's Pascal glue: the callee pops, a function's answer goes in
 * the space the caller left under the arguments. */
    ".globl s_newhandle\n s_newhandle:\n"               /* (size) : Handle */
    "  move.l 4(%sp),-(%sp)\n jsr c_newhandle\n addq.l #4,%sp\n"
    "  movea.l (%sp)+,%a1\n addq.l #4,%sp\n move.l %d0,(%sp)\n jmp (%a1)\n"
    ".globl s_dispose\n s_dispose:\n"                   /* (h) */
    "  move.l 4(%sp),-(%sp)\n jsr c_dispose\n addq.l #4,%sp\n"
    "  movea.l (%sp)+,%a1\n addq.l #4,%sp\n jmp (%a1)\n"
    ".globl s_gethsize\n s_gethsize:\n"                 /* (h) : long */
    "  move.l 4(%sp),-(%sp)\n jsr c_gethsize\n addq.l #4,%sp\n"
    "  movea.l (%sp)+,%a1\n addq.l #4,%sp\n move.l %d0,(%sp)\n jmp (%a1)\n"
    ".globl s_sethsize\n s_sethsize:\n"                 /* (h, size) */
    "  move.l 4(%sp),-(%sp)\n move.l 12(%sp),-(%sp)\n jsr c_sethsize\n"
    "  addq.l #8,%sp\n movea.l (%sp)+,%a1\n addq.l #8,%sp\n jmp (%a1)\n"
    ".globl s_hlock\n s_hlock:\n"                       /* (h), HLock/HUnlock */
    "  movea.l (%sp)+,%a1\n addq.l #4,%sp\n jmp (%a1)\n"
);

extern char s_getbyte[], s_read[], s_putbyte[], s_zero[], s_go_on[],
            s_newhandle[], s_dispose[], s_gethsize[], s_sethsize[], s_hlock[];

/* ---- the world ----------------------------------------------------- */

static unsigned char *load(const char *path)
{
    FILE *f = fopen(path, "rb");
    long n;
    unsigned char *p;
    if (!f) { perror(path); exit(2); }
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    p = mmap(NULL, (size_t)n + 16, PROT_READ | PROT_WRITE | PROT_EXEC,
             MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (p == MAP_FAILED || fread(p, 1, (size_t)n, f) != (size_t)n)
        { perror(path); exit(2); }
    fclose(f);
    return p;
}

static void jt(int n, void *to)           /* `jsr n(A5)` lands on JMP to */
{
    unsigned long a = (unsigned long)to;
    unsigned char *e = g_a5 + n;
    e[0] = 0x4e; e[1] = 0xf9;
    e[2] = (unsigned char)(a >> 24); e[3] = (unsigned char)(a >> 16);
    e[4] = (unsigned char)(a >> 8);  e[5] = (unsigned char)a;
}

static void put32(unsigned char *at, unsigned long v)
{
    at[0] = (unsigned char)(v >> 24); at[1] = (unsigned char)(v >> 16);
    at[2] = (unsigned char)(v >> 8);  at[3] = (unsigned char)v;
}

static void put16(unsigned char *at, unsigned v)
{
    at[0] = (unsigned char)(v >> 8); at[1] = (unsigned char)v;
}

static long unhex(const char *s, unsigned char *out, long cap)
{
    long n = 0;
    while (s && s[0] && s[1] && n < cap) {
        char b[3]; b[0] = s[0]; b[1] = s[1]; b[2] = 0;
        out[n++] = (unsigned char)strtoul(b, NULL, 16);
        s += 2;
    }
    return n;
}

static void on_signal(int sig) { g_signal = sig; longjmp(g_escape, 1); }

#define CAP (4L << 20)

int main(int argc, char **argv)
{
    static char line[2 * CAP / 2 + 256];
    unsigned char *c11, *c7, *world, *trees, *in, *out;
    Stream sin, sout;

    if (argc != 3) { fprintf(stderr, "usage: %s <code11> <code7>\n", argv[0]); return 2; }
    c11 = load(argv[1]);
    c7 = load(argv[2]);
    /* Low memory: MemErr at 0x220 reads 0 (needs qemu-m68k -B). */
    if (mmap((void *)0, 4096, PROT_READ | PROT_WRITE,
             MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0) == MAP_FAILED)
        { perror("page 0"); return 2; }
    /* The jump table is executed, so the world is mapped executable. */
    world = mmap(NULL, BELOW + ABOVE, PROT_READ | PROT_WRITE | PROT_EXEC,
                 MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    g_a5 = world + BELOW;
    trees = malloc(256 * 1536);
    in = malloc(CAP);
    out = malloc(CAP);

    jt(1970, s_getbyte);   jt(2018, s_read);    jt(2106, s_putbyte);
    jt(2002, s_zero);      jt(1042, s_go_on);
    jt(218, s_newhandle);  jt(226, s_dispose);  jt(234, s_gethsize);
    jt(242, s_sethsize);   jt(250, s_hlock);    jt(258, s_hlock);
    jt(2274, c7 + 0x70);

    signal(SIGSEGV, on_signal); signal(SIGILL, on_signal);
    signal(SIGBUS, on_signal); signal(SIGFPE, on_signal);
    setvbuf(stdout, NULL, _IOFBF, 1 << 16);

    while (fgets(line, sizeof line, stdin)) {
        char *tok[8], *p = strtok(line, " \t\r\n");
        int nt = 0;
        long n, outlen, i;
        while (p && nt < 8) { tok[nt++] = p; p = strtok(NULL, " \t\r\n"); }
        if (nt == 0) continue;
        if (setjmp(g_escape)) { printf("signal %d\n", g_signal); fflush(stdout); continue; }
        if (tok[0][0] == 'S' && nt >= 5) {
            outlen = atol(tok[3]);
            n = nt > 5 ? unhex(tok[5], in, CAP) : 0;
            g_a5[-1000] = (unsigned char)atoi(tok[1]);       /* method 5 */
            put16(g_a5 - 1544, (unsigned)atoi(tok[2]));      /* the XOR */
            put32(g_a5 - 1014, (unsigned long)trees);
            put16(g_a5 - 1002, 256);
            put16(g_a5 - 1004, 256);
            g_fn = c11 + 0x221e;
            put16(g_args + 16, (unsigned)atoi(tok[4]));
        } else if (tok[0][0] == 'L' && nt >= 3) {
            outlen = atol(tok[1]);
            n = nt > 3 ? unhex(tok[3], in, CAP) : 0;
            g_fn = c11 + 0x34e2;
            put16(g_args + 16, (unsigned)atoi(tok[2]));
        } else {
            printf("?\n");
            continue;
        }
        sin.cur = in; sin.end = in + n - 1;
        sout.cur = out; sout.end = out + CAP - 1;
        put32(g_args, (unsigned long)&sin);
        put32(g_args + 4, (unsigned long)&sout);
        put32(g_args + 8, 0);
        put32(g_args + 12, (unsigned long)outlen);
        g_nargs = 18;
        call();
        printf("%d ", (short)g_ret);
        for (i = 0; i < sout.cur - out; i++) printf("%02x", out[i]);
        printf("\n");
        fflush(stdout);
    }
    return 0;
}
