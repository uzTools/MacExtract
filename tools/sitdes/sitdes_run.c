/*
 * sitdes_run.c — run StuffIt Deluxe 3.5.1's own StuffIt classic cipher
 * routines as subroutines, under qemu-m68k.
 *
 * StuffIt Deluxe 3.5.1 does its stuffing and unstuffing in the `StuffIt
 * Engine` extension, and that file's resource fork carries two `CCOD`
 * code resources with the archive cipher in them: `CCOD` -2013 reads an
 * encrypted archive (its `'MKey'` is fetched with `GetResource` at
 * 0x1d9a, its fork transform at 0x1f58 feeds back from its INPUT XOR the
 * key, i.e. from the ciphertext) and `CCOD` -2045 writes one (it makes the
 * `'MKey'` at 0x1f76 and feeds back from its input, the plaintext, at
 * 0x3cf8). Both are position-independent 68k code with their globals off
 * A4, and the routines below call no trap, so they run here as they ran
 * on the Mac. The facts read off them are docs/formats/stuffit-des-key.md;
 * every offset below is a file offset into the resource's data, checked
 * by tools/sitdes/run_sitdes.py against the bytes it was read from.
 *
 *   CCOD -2013 @0x1820  setkey(key8, mode): sixteen eight-byte round
 *                       keys at A4+31208, in round order for mode 0
 *                       (encrypt) and reversed for mode 1 (decrypt)
 *              @0x0f3e  block(src8, dst8) under that schedule
 *              @0x19a8  fold(cstring password, out8): the archive key
 *              @0x0580  check(ak8, mkey8): 0 when the 'MKey' verifies;
 *                       leaves AK at A4+30050 and the IV at A4+30058
 *              @0x0692  filekey(entry[0..7], entry[8..15]): both
 *                       decrypted in place, the first XOR the IV
 *              @0x1f58  feed(state8, key8, src8, dst8): one block of the
 *                       fork transform, reading
 *   CCOD -2045 @0x2ad0, @0x21ee, @0x2c58: the same three as the reader's
 *                       setkey, block and fold, in the writer
 *              @0x3cf8  feed, writing
 *
 * Usage:  sitdes_run <ccod-2013> <ccod-2045>, then one command per line on
 * stdin, one answer per line on stdout (hex):
 *
 *   S r|w <key>  <mode>            the schedule, 128 bytes
 *   B r|w <key>  <mode> <block>    one block
 *   F r|w <password hex>           the archive key
 *   C <ak> <mkey>                  "<status> <iv>"
 *   K <ak> <mkey> <entry16>        "<status> <filekey> <fileiv>"
 *   X r|w <key> <iv> <data>        the fork transform, 8 bytes at a time
 *
 * SPDX-License-Identifier: 0BSD
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#include <signal.h>
#include <sys/mman.h>

#define WORLD 65536

struct ccod {
    unsigned char *code;
    size_t len;
    long setkey, block, fold, feed, sched;
};

static struct ccod R = { 0, 0, 0x1820, 0x0f3e, 0x19a8, 0x1f58, 31208 };
static struct ccod W = { 0, 0, 0x2ad0, 0x21ee, 0x2c58, 0x3cf8, 23524 };
#define R_CHECK   0x0580
#define R_FILEKEY 0x0692
#define R_AK      30050
#define R_IV      30058

static jmp_buf g_escape;
static volatile int g_signal;

unsigned char g_args[32];
long g_nargs;
void *g_fn;
unsigned char *g_a4;
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
        "2: movea.l g_a4,%%a4\n\t"
        "movea.l g_fn,%%a0\n\t"
        "jsr (%%a0)\n\t"
        "adda.l g_nargs,%%sp\n\t"
        "move.l %%d0,g_ret\n\t"
        "movem.l (%%sp)+,%%d2-%%d7/%%a2-%%a6"
        : : : "d0", "d1", "a0", "a1", "memory", "cc");
}

static void on_signal(int sig) { g_signal = sig; longjmp(g_escape, 1); }

static void load(struct ccod *c, const char *path)
{
    FILE *f = fopen(path, "rb");
    long n;
    if (!f) { perror(path); exit(2); }
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    c->code = mmap(NULL, (size_t)n + 16, PROT_READ | PROT_WRITE | PROT_EXEC,
                   MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (c->code == MAP_FAILED || fread(c->code, 1, (size_t)n, f) != (size_t)n)
        { perror(path); exit(2); }
    c->len = (size_t)n;
    fclose(f);
}

static int unhex(const char *s, unsigned char *out, int cap)
{
    int n = 0;
    while (s && s[0] && s[1] && n < cap) {
        char b[3]; b[0] = s[0]; b[1] = s[1]; b[2] = 0;
        out[n++] = (unsigned char)strtoul(b, NULL, 16);
        s += 2;
    }
    return n;
}

static void hex(const unsigned char *p, int n)
{
    int i;
    for (i = 0; i < n; i++) printf("%02x", p[i]);
}

static void put32(int at, unsigned long v)
{
    g_args[at] = (unsigned char)(v >> 24); g_args[at + 1] = (unsigned char)(v >> 16);
    g_args[at + 2] = (unsigned char)(v >> 8); g_args[at + 3] = (unsigned char)v;
}

static void args_pp(void *a, void *b)
{ put32(0, (unsigned long)a); put32(4, (unsigned long)b); g_nargs = 8; }

static void do_setkey(struct ccod *c, unsigned char *key, int mode)
{
    put32(0, (unsigned long)key);
    g_args[4] = 0; g_args[5] = (unsigned char)mode;
    g_nargs = 6;
    g_fn = c->code + c->setkey;
    call();
}

static void do_block(struct ccod *c, unsigned char *src, unsigned char *dst)
{
    args_pp(src, dst);
    g_fn = c->code + c->block;
    call();
}

int main(int argc, char **argv)
{
    static unsigned char world[WORLD];
    char line[4096], *tok[8];
    unsigned char key[8], blk[8], iv[8], mk[8], ek[16];
    static unsigned char buf[2048], pw[600];

    if (argc != 3) { fprintf(stderr, "usage: %s <ccod-2013> <ccod-2045>\n", argv[0]); return 2; }
    load(&R, argv[1]);
    load(&W, argv[2]);
    g_a4 = world;
    signal(SIGSEGV, on_signal); signal(SIGILL, on_signal);
    signal(SIGBUS, on_signal); signal(SIGFPE, on_signal);
    setvbuf(stdout, NULL, _IOLBF, 0);

    while (fgets(line, sizeof line, stdin)) {
        int nt = 0;
        char *p = strtok(line, " \t\r\n");
        struct ccod *c;
        while (p && nt < 8) { tok[nt++] = p; p = strtok(NULL, " \t\r\n"); }
        if (nt == 0) continue;
        if (setjmp(g_escape)) { printf("signal %d\n", g_signal); continue; }
        c = (nt > 1 && tok[1][0] == 'w') ? &W : &R;
        switch (tok[0][0]) {
        case 'S':
            unhex(tok[2], key, 8);
            do_setkey(c, key, atoi(tok[3]));
            hex(world + c->sched, 128);
            break;
        case 'B':
            unhex(tok[2], key, 8);
            unhex(tok[4], blk, 8);
            do_setkey(c, key, atoi(tok[3]));
            do_block(c, blk, blk);
            hex(blk, 8);
            break;
        case 'F': {
            int n = nt > 2 ? unhex(tok[2], pw, (int)sizeof pw - 1) : 0;
            pw[n] = 0;                       /* a C string, as @0x1e56 makes it */
            memset(blk, 0, 8);
            args_pp(pw, blk);
            g_fn = c->code + c->fold;
            call();
            hex(blk, 8);
            break;
        }
        case 'C':
        case 'K':
            unhex(tok[1], key, 8);
            unhex(tok[2], mk, 8);
            memset(world + R_AK, 0, 16);
            args_pp(key, mk);
            g_fn = R.code + R_CHECK;
            call();
            printf("%ld ", g_ret & 0xffff);
            if (tok[0][0] == 'C') { hex(world + R_IV, 8); break; }
            unhex(tok[3], ek, 16);
            args_pp(ek, ek + 8);
            g_fn = R.code + R_FILEKEY;
            call();
            hex(ek, 8); printf(" "); hex(ek + 8, 8);
            break;
        case 'X': {
            int n, i;
            unhex(tok[2], key, 8);
            unhex(tok[3], iv, 8);
            n = unhex(tok[4], buf, (int)sizeof buf) & ~7;
            for (i = 0; i < n; i += 8) {
                put32(0, (unsigned long)iv); put32(4, (unsigned long)key);
                put32(8, (unsigned long)(buf + i)); put32(12, (unsigned long)(buf + i));
                g_nargs = 16;
                g_fn = c->code + c->feed;
                call();
            }
            hex(buf, n);
            break;
        }
        default:
            printf("?");
        }
        printf("\n");
    }
    return 0;
}
