/*
 * pit_run.c — run PackIt III 1.3's own two ciphers as subroutines.
 *
 * PackIt III is the generation that wrote every `PMa5` and `PMa6` block
 * there has ever been, and 1.3 (6/14/87) is the copy that is reachable:
 * it ships inside `PackIt.pit`, which is a corpus fixture, and an
 * application is all resource fork. Its `CODE` 1 carries both ciphers
 * and its `CODE` 256 is nothing but DES's tables. So the cipher does
 * not have to be read out of somebody's reimplementation, nor out of
 * this disassembly alone: the original code can be EXECUTED, built for
 * m68k-linux and run under `qemu-m68k`, the same way the SuperDisk!
 * modules are (tools/sdmodule/). No emulator, no boot, no screenshot.
 *
 * Source: PackIt III 1.3's own `CODE` 1 and `CODE` 256, read with
 * m68k-linux-gnu-objdump. Every address below is a file offset into the
 * resource's data and is checked at that offset by
 * tools/derive_pitcrypt.py --witness, which fails if the input is not
 * the binary this was read from.
 *
 *   CODE 256, data start      DES's tables, as 16-bit words, in this
 *                             order: IP at +0, IP-inverse at +128, the
 *                             L/R swap at +256, PC-1 at +384, PC-2 at
 *                             +496, E at +592, P at +688, the eight S
 *                             boxes at +752 and the 16 shift counts at
 *                             +1776. The runtime reads the resource
 *                             into A5-19150 (CODE 1 @0x3cca), which is
 *                             why PC-1 is addressed as A5-18766 =
 *                             -19150+384.
 *   CODE 1 @0x334a            SetKey: the eight password bytes at
 *                             A5-2191 become 64 bits, PC-1 permutes
 *                             them to 56, and those pack into the
 *                             SEVEN-byte key at A5-22. The running
 *                             pointer A5-14 and counter A5-10 are reset
 *                             to that key and to 7 (@0x337e).
 *   CODE 1 @0x3390            Cipher(ptr, count) in the direction
 *                             PackIt WRITES with: mode 1 XORs each byte
 *                             with the next of the seven, wrapping
 *                             (@0x33a6); mode 2 runs the eight-byte
 *                             block routine @0x33fc, which is DES with
 *                             the rounds ascending — standard
 *                             ENCRYPTION.
 *   CODE 1 @0x3518            The same dispatcher in the direction it
 *                             READS with: the same XOR, and the block
 *                             routine @0x3584, whose rounds descend —
 *                             standard DECRYPTION.
 *   CODE 1 @0x1942            and the reason a `PMa5`/`PMa6` stream is
 *                             always a whole number of eight-byte
 *                             blocks: the writer rounds the flush
 *                             length up with `addq.l #7` / `and.l #-8`
 *                             whenever the mode is nonzero.
 *
 * Usage:  pit_run <code1> <code256> <mode 1|2> <keyhex> <pack|unpack>
 *                 <in> <out>
 *
 * `mode` is PackIt's own encryption word: 1 = Simple, 2 = DES. `pack`
 * is the direction the application writes with, `unpack` the one it
 * reads with. One line of key=value goes to stdout.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#include <signal.h>
#include <sys/mman.h>
#include <ucontext.h>

/* Where in CODE 1 each routine sits, and where in the A5 world each
 * global does. Both sets are the binary's, not this file's. */
#define OFF_SETKEY   0x334aL
#define OFF_PACK     0x3390L
#define OFF_UNPACK   0x3518L

#define A5_KEY       (-22)       /* the seven-byte XOR key           */
#define A5_KEYPTR    (-14)       /* the running pointer into it      */
#define A5_KEYLEFT   (-10)       /* and how many of the seven are left */
#define A5_PASSWORD  (-2192)     /* a Str255: length byte, then eight */
#define A5_MODE      (-2180)     /* 0 none, 1 simple, 2 DES          */
#define A5_TABLES    (-19150)    /* CODE 256, read in whole          */

#define WORLD_LOW    24576u      /* room below A5 for all of the above */
#define WORLD_HIGH   4096u       /* and the jump table's side of it    */

static jmp_buf g_escape;
static volatile int g_signal;
static unsigned char *g_code;
static size_t g_codelen;
static volatile long g_where = -1;

/* What the harness passes in. Globals rather than asm operands so that
 * no register allocation can collide with A5, which the call needs. */
void *g_fn;
unsigned char *g_a5;
void *g_ptr;
long g_count;

/*
 * The one Toolbox trap in the call graph. The DES block routine saves
 * its 64 bits with `_BlockMove` (A02E) at CODE 1 @0x3f84 — A0 source,
 * A1 destination, D0 count, per Inside Macintosh: Memory. A user-mode
 * process has no Toolbox, so the A-line word raises SIGILL; answering
 * it here is four lines, and it is the same four tools/sdmodule's
 * harness needs for the same trap. Anything else A-line still faults,
 * and is reported with its offset inside CODE 1 so it can be read.
 */
static int serve_trap(void *uc)
{
    ucontext_t *u = (ucontext_t *)uc;
    greg_t *g;
    unsigned short op;
    if (!u) return 0;
    g = u->uc_mcontext.gregs;
    op = *(unsigned short *)(size_t)g[R_PC];
    if (op != 0xA02Eu) return 0;
    memmove((void *)(size_t)g[R_A1], (void *)(size_t)g[R_A0],
            (size_t)(unsigned long)g[R_D0]);
    g[R_PC] += 2;
    return 1;
}

static void on_signal_info(int sig, siginfo_t *si, void *uc)
{
    if (sig == SIGILL && serve_trap(uc)) return;
    g_signal = sig;
    g_where = -1;
    if (si && si->si_addr) {
        unsigned char *p = (unsigned char *)si->si_addr;
        if (g_code && p >= g_code && p < g_code + g_codelen)
            g_where = (long)(p - g_code);
    }
    longjmp(g_escape, 1);
}

static void arm_signals(void)
{
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_signal_info;
    sa.sa_flags = SA_SIGINFO;
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS,  &sa, NULL);
    sigaction(SIGILL,  &sa, NULL);
    sigaction(SIGFPE,  &sa, NULL);
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

/*
 * The call-clobbered set. These routines are 1987 Macintosh code and
 * save only what they feel like: SetKey saves nothing at all and uses
 * A2, and the dispatcher pushes D4/A3 and then writes D2, D3 and A2
 * over the caller's. Naming them all is not caution — without it this
 * harness returned a different exit status on every run, because the
 * cipher had quietly taken the register main's own value was in.
 */
#define CLOBBERS "d0", "d1", "d2", "d3", "d4", "d5", "a0", "a1", "a2", \
                 "a3", "a4", "memory", "cc"

/* SetKey() — no arguments, everything through A5. */
static void call_setkey(void)
{
    __asm__ __volatile__(
        "move.l %%a5,-(%%sp)\n\t"
        "movea.l g_a5,%%a5\n\t"
        "movea.l g_fn,%%a1\n\t"
        "jsr (%%a1)\n\t"
        "movea.l (%%sp)+,%%a5"
        : : : CLOBBERS);
}

/* Cipher(ptr, count) — the C convention CODE 1 was compiled with: the
 * arguments at 8(A6) and 12(A6), pushed right to left, popped here. */
static void call_cipher(void)
{
    __asm__ __volatile__(
        "move.l %%a5,-(%%sp)\n\t"
        "movea.l g_a5,%%a5\n\t"
        "move.l g_count,-(%%sp)\n\t"
        "move.l g_ptr,-(%%sp)\n\t"
        "movea.l g_fn,%%a1\n\t"
        "jsr (%%a1)\n\t"
        "addq.l #8,%%sp\n\t"
        "movea.l (%%sp)+,%%a5"
        : : : CLOBBERS);
}

static int unhex(const char *s, unsigned char *out, int cap)
{
    int n = 0;
    while (s[0] && s[1] && n < cap) {
        char b[3];
        b[0] = s[0]; b[1] = s[1]; b[2] = 0;
        out[n++] = (unsigned char)strtoul(b, NULL, 16);
        s += 2;
    }
    return n;
}

int main(int argc, char **argv)
{
    unsigned char *code, *c256, *world, *a5, *data;
    size_t codelen, c256len, datalen;
    unsigned char key[8];
    int mode, keylen, pack;
    long off;
    FILE *f;

    if (argc != 8) {
        fprintf(stderr, "usage: %s <code1> <code256> <mode> <keyhex> "
                        "<pack|unpack> <in> <out>\n", argv[0]);
        return 2;
    }
    code = slurp(argv[1], &codelen);
    c256 = slurp(argv[2], &c256len);
    mode = atoi(argv[3]);
    memset(key, 0, sizeof key);
    keylen = unhex(argv[4], key, (int)sizeof key);
    pack = strcmp(argv[5], "pack") == 0;
    data = slurp(argv[6], &datalen);

    if (mode != 1 && mode != 2) {
        fprintf(stderr, "pit_run: mode must be 1 (simple) or 2 (DES)\n");
        return 2;
    }
    if (mode == 2 && (datalen % 8) != 0) {
        fprintf(stderr, "pit_run: DES wants a multiple of eight bytes, "
                        "got %lu\n", (unsigned long)datalen);
        return 2;
    }

    /* The code has to be executable where it is put; it is entirely
     * PC-relative inside CODE 1, so anywhere will do. */
    g_code = mmap(NULL, codelen + 16, PROT_READ | PROT_WRITE | PROT_EXEC,
                  MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (g_code == MAP_FAILED) { perror("mmap"); return 2; }
    memcpy(g_code, code, codelen);
    g_codelen = codelen;

    /* The A5 world: the globals the two ciphers read, at the offsets
     * the binary addresses them by. */
    world = calloc(1, WORLD_LOW + WORLD_HIGH);
    if (!world) return 2;
    a5 = world + WORLD_LOW;
    memcpy(a5 + A5_TABLES, c256, c256len);
    a5[A5_PASSWORD] = (unsigned char)keylen;      /* the Str255 length */
    memcpy(a5 + A5_PASSWORD + 1, key, 8);
    a5[A5_MODE] = 0; a5[A5_MODE + 1] = (unsigned char)mode;   /* big-endian */
    g_a5 = a5;

    arm_signals();
    if (setjmp(g_escape)) {
        printf("status=signal signal=%d at=0x%lx\n", g_signal, g_where);
        return 1;
    }

    g_fn = g_code + OFF_SETKEY;
    call_setkey();

    off = pack ? OFF_PACK : OFF_UNPACK;
    g_fn = g_code + off;
    g_ptr = data;
    g_count = (long)datalen;
    call_cipher();

    f = fopen(argv[7], "wb");
    if (!f) { perror(argv[7]); return 2; }
    fwrite(data, 1, datalen, f);
    fclose(f);

    printf("status=ok mode=%d dir=%s bytes=%lu entry=0x%lx key7=", mode,
           pack ? "pack" : "unpack", (unsigned long)datalen, off);
    {
        int i;
        for (i = 0; i < 7; i++)
            printf("%02x", a5[A5_KEY + i]);
    }
    printf(" keyleft=%d\n", (int)((a5[A5_KEYLEFT] << 8) | a5[A5_KEYLEFT + 1]));
    (void)A5_KEYPTR;
    return 0;
}
