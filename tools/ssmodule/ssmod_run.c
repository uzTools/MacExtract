/*
 * ssmod_run.c — run Aladdin's SpaceSaver `CMod` compressor modules as
 * subroutines, off the Macintosh.
 *
 * SpaceSaver's five codecs each ship as a `CMod` resource: position-
 * independent 68k with no Toolbox in it beyond three Memory Manager traps.
 * Methods 0 and 4 are implemented in `src/fmt_spacesaver.c`; methods 1, 2
 * and 3 are not, and the reason has always been that nothing reachable
 * WRITES them (OPEN_ITEMS.md). Their modules compress as well as expand, so
 * running one under `qemu-m68k` is both the specimen generator and the
 * second implementation — the arrangement `tools/sdmodule/` already uses for
 * SuperDisk!'s Add-In Modules.
 *
 *   Source: the modules themselves, and their caller. `ExpandFork` @0x5ee6
 *   in `SSEn 1` (StuffIt Engine 3.5.1) builds the parameter block at its
 *   fp@(-146) and calls the module's +0x10 vector; every field below is
 *   read either from that routine or from the wrapper thunks at the head of
 *   `CMod 20`/`CMod 21` (@0x2e, @0x4a, @0x68, @0x82, @0xa0, @0xb6, @0xd0),
 *   each of which calls `pb->[n]` with `pb->[28]` as its first argument.
 *   The seven slots are NAMED by the engine's own MacsBug symbols, which is
 *   what fixes them beyond doubt: the routines ExpandFork installs at +0..+24
 *   are `cReadSource` @0x6186, `cWriteDest` @0x620e, `cGetSourceFPos`
 *   @0x6296, `cSetSourceFPos` @0x62e8, `cGetSourceEOF` @0x6386, `cProgress`
 *   @0x63ec and `cDebug` @0x6434.
 *
 *   `CMod 3` and `CMod 4` ("Original Fast"/"Original Slow") have no thunks
 *   and call through the same fields directly (`%a3@`, `%a3@(4)`,
 *   `%a3@(28)`, `%a3@(52)`), which is how the two eras are known to share
 *   one interface.
 *
 *     +0  (4) read(refcon, void *buf, long *count) -> OSErr
 *     +4  (4) write(refcon, void *buf, long count) -> OSErr — the
 *             count comes BY VALUE here and by reference on +0
 *             (`CMod 20` @0xe68 pushes D3 itself; `CMod 21` @0x1aa
 *             pushes `pea %fp@(-4)` to read)
 *     +8  (4) cGetSourceFPos(refcon, long *pos)
 *     +12 (4) cSetSourceFPos(refcon, long pos, short mode)
 *     +16 (4) cGetSourceEOF(refcon) -> Boolean in the low byte of D0
 *             (`CMod 20` @0x2de and @0x42e take the byte and widen it)
 *     +20 (4) cProgress(refcon, long sofar) -> OSErr
 *     +24 (4) cDebug(refcon, char *buf) — a 256-byte buffer, cleared first
 *     +28 (4) refcon: the engine's own context, opaque to the module
 *     +32 (4) compressed length — IN for expand, OUT for compress
 *             (`CMod 3` @0x12e writes it; `CMod 21` @0x190 refuses 0)
 *     +36 (4) uncompressed length — IN for both; `CMod 3` @0x230 stops when
 *             it has produced this many bytes
 *     +40 (4) cleared by ExpandFork and read by no module here
 *     +44 (4) preset dictionary, a `PrAm` master pointer
 *     +48 (4) its size (ExpandFork's glue @0x3e4 is GetHandleSize)
 *     +52 (4) work buffer — every module carves its own buffers out of this
 *     +56 (4) its size, which each module checks before it starts
 *
 * Every vector takes TWO arguments: the parameter block, and the private
 * block this module's own init returned — `LoadCompressors` @0x11a0 keeps
 * one per module at its table's +28+4i and `mExpandFile` @0x57e6 pushes it
 * as the second argument. `CMod 10` ("Alg 3") is the module that needs it:
 * its compress vector @0x3616 immediately reads five fields out of it, so
 * called with one argument it dereferences whatever follows on the stack.
 *
 * The +0x00 vector is `init(void **priv, long *workSize)`: it says how much
 * work buffer this module needs (`CMod 3` @0x2e answers a constant 164,360;
 * `CMod 21` @0x68c computes 212,992 + 98,304) and hands back a private
 * block. +0x08 compresses, +0x10 expands, +0x18 disposes. All four take the
 * parameter block as one stack argument in the ordinary C way, so they are
 * called from C directly.
 *
 * Three A-line traps have to be answered, exactly as `sdmod_run.c` answers
 * `_BlockMove`: `_NewPtr` (A11E), `_DisposPtr` (A01F) and `_DebugStr`
 * (ABFF) — `CMod 3`'s compressor announces its own name through the last of
 * these at @0x5e, which on a Mac with no debugger installed is a no-op and
 * here would otherwise be a SIGILL.
 *
 * Usage: ssmod_run <module.bin> <compress|expand> <in> <out>
 *                  [preset] [ulen] [--] 
 *
 * `ulen` is required for expand (the fork's original length, from its
 * record); for compress it is the input's own length. One line of key=value
 * goes to stdout.
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

#define PB_SIZE   64
#define SLACK     (256u * 1024u)

static jmp_buf g_escape;
static volatile int g_signal;
static void *g_code;
static size_t g_codelen;
static volatile long g_where = -1;      /* fault address inside the module */
static volatile long g_pc = -1;         /* and where it was executing */
static volatile unsigned long g_pcabs, g_addr, g_a0, g_sp;
static volatile unsigned g_op;          /* the word it died on */

/* The refcon: what the engine would pass, reduced to two buffers. */
typedef struct {
    unsigned char *in;
    long           inlen, inpos;
    unsigned char *out;
    long           outcap, outlen;
    long           reads, writes, eofs, progress, debugs, unknown;
} Ref;

static Ref g_ref;

/* --- the callbacks, in the module's own calling convention ------------- */

static short cb_read(Ref *r, void *buf, long *count)
{
    long want = *count, have = r->inlen - r->inpos;
    if (want < 0) return -50;                       /* paramErr */
    if (have < 0) have = 0;
    if (want > have) want = have;
    memcpy(buf, r->in + r->inpos, (size_t)want);
    r->inpos += want;
    r->reads++;
    /* FSRead's contract: the count comes back as what was actually read,
     * and a short read is eofErr rather than an error the module stops on
     * (`CMod 21` @0x1c4 tolerates exactly -39). */
    if (want < *count) { *count = want; return -39; }
    *count = want;
    return 0;
}

static short cb_write(Ref *r, void *buf, long want)
{
    if (want < 0) return -50;
    if (r->outlen + want > r->outcap) return -34;   /* dskFulErr */
    memcpy(r->out + r->outlen, buf, (size_t)want);
    r->outlen += want;
    r->writes++;
    return 0;
}

static short cb_eof(Ref *r)
{
    r->eofs++;
    return (short)(r->inpos >= r->inlen);
}

static short cb_progress(Ref *r, long sofar)
{
    (void)sofar; r->progress++;
    return 0;
}

static short cb_debug(Ref *r, char *buf)
{
    r->debugs++;
    if (buf) buf[0] = 0;
    return 0;
}

/* +8 and +12 are called by none of the six modules in hand. A stub that
 * returned 0 would let a module that DOES call one carry on with an
 * invented answer, so these count themselves and the count is printed. */
static short cb_unknown1(Ref *r, long a) { (void)a; r->unknown++; return -50; }
static short cb_unknown2(Ref *r, long a, long b)
{ (void)a; (void)b; r->unknown++; return -50; }

/* --- the three traps --------------------------------------------------- */

static char g_lastdebug[256];

static int serve_trap(void *uc)
{
    ucontext_t *u = (ucontext_t *)uc;
    greg_t *g;
    unsigned short op;
    if (!u) return 0;
    g = u->uc_mcontext.gregs;
    op = *(unsigned short *)(size_t)g[R_PC];
    switch (op) {
    case 0xA11Eu: {                                  /* _NewPtr */
        void *p = calloc(1, (size_t)(unsigned long)g[R_D0] + 16);
        g[R_A0] = (greg_t)(size_t)p;
        g[R_D0] = p ? 0 : -108;                      /* memFullErr */
        break;
    }
    case 0xA01Fu:                                    /* _DisposPtr */
        free((void *)(size_t)g[R_A0]);
        g[R_D0] = 0;
        break;
    case 0xABFFu: {                                  /* _DebugStr */
        unsigned char *s = *(unsigned char **)(size_t)g[R_SP];
        if (s) {
            size_t n = s[0] < sizeof g_lastdebug - 1 ? s[0]
                                                     : sizeof g_lastdebug - 1;
            memcpy(g_lastdebug, s + 1, n);
            g_lastdebug[n] = 0;
        }
        g[R_SP] += 4;                                /* Pascal: it pops */
        break;
    }
    default:
        return 0;
    }
    g[R_PC] += 2;
    return 1;
}

static void on_signal_info(int sig, siginfo_t *si, void *uc)
{
    if (sig == SIGILL && serve_trap(uc)) return;
    g_signal = sig;
    g_where = -1;
    g_pc = -1;
    if (uc) {
        greg_t *gg = ((ucontext_t *)uc)->uc_mcontext.gregs;
        g_pcabs = (unsigned long)gg[R_PC];
        g_a0 = (unsigned long)gg[R_A0];
        g_sp = (unsigned long)gg[R_SP];
        g_op = sig == SIGILL ? *(unsigned short *)(size_t)gg[R_PC] : 0;
    }
    g_addr = si ? (unsigned long)(size_t)si->si_addr : 0;
    if (uc) {
        unsigned char *pc =
            (unsigned char *)(size_t)((ucontext_t *)uc)->uc_mcontext.gregs[R_PC];
        if (g_code && pc >= (unsigned char *)g_code &&
            pc < (unsigned char *)g_code + g_codelen)
            g_pc = (long)(pc - (unsigned char *)g_code);
    }
    if (si && si->si_addr) {
        unsigned char *p = (unsigned char *)si->si_addr;
        if (g_code && p >= (unsigned char *)g_code &&
            p < (unsigned char *)g_code + g_codelen)
            g_where = (long)(p - (unsigned char *)g_code);
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
    if (!b || (n && fread(b, 1, (size_t)n, f) != (size_t)n)) {
        perror(path); exit(2);
    }
    fclose(f);
    *len = (size_t)n;
    return b;
}

static void put32(unsigned char *p, unsigned long v)
{
    p[0] = (unsigned char)(v >> 24); p[1] = (unsigned char)(v >> 16);
    p[2] = (unsigned char)(v >> 8);  p[3] = (unsigned char)v;
}

static unsigned long get32(const unsigned char *p)
{
    return ((unsigned long)p[0] << 24) | ((unsigned long)p[1] << 16) |
           ((unsigned long)p[2] << 8) | p[3];
}

typedef short (*Vector)(void *pb, void *priv);
typedef short (*Init)(void **priv, long *worksize);

int main(int argc, char **argv)
{
    unsigned char *blob, *code, *pb, *work = NULL, *preset = NULL;
    size_t bloblen, inlen, presetlen = 0;
    unsigned long ulen, worksize = 0;
    long wants = 0;
    void *priv = NULL;
    int expand;
    short st;
    FILE *out;

    if (argc < 5) {
        fprintf(stderr, "usage: %s <module.bin> <compress|expand> <in> <out>"
                        " [preset] [ulen]\n", argv[0]);
        return 2;
    }
    expand = strcmp(argv[2], "expand") == 0;
    if (!expand && strcmp(argv[2], "compress") != 0) {
        fprintf(stderr, "ssmod_run: selector must be compress or expand\n");
        return 2;
    }
    blob = slurp(argv[1], &bloblen);
    g_ref.in = slurp(argv[3], &inlen);
    g_ref.inlen = (long)inlen;
    if (argc > 5 && argv[5][0]) preset = slurp(argv[5], &presetlen);
    ulen = argc > 6 ? strtoul(argv[6], NULL, 0)
                    : (expand ? 0u : (unsigned long)inlen);

    code = mmap(NULL, (bloblen + 4095) & ~(size_t)4095,
                PROT_READ | PROT_WRITE | PROT_EXEC,
                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (code == MAP_FAILED) { perror("mmap"); return 2; }
    memcpy(code, blob, bloblen);
    g_code = code; g_codelen = bloblen;

    arm_signals();

    /* What does this module need? Ask it, rather than guessing: the two
     * eras answer with different numbers and both check the size they were
     * given before they start. */
    if (setjmp(g_escape) == 0) {
        st = ((Init)(void *)code)(&priv, &wants);
    } else {
        printf("signal=%d at=%ld pc=%ld phase=init\n",
               g_signal, g_where, g_pc);
        return 3;
    }
    if (st != 0) { printf("status=%d phase=init\n", st); return 4; }
    worksize = (unsigned long)wants;
    work = calloc(1, worksize + SLACK);

    g_ref.outcap = (long)(expand ? (ulen ? ulen : inlen * 64 + SLACK)
                                 : inlen + inlen / 2 + SLACK);
    g_ref.out = calloc(1, (size_t)g_ref.outcap + SLACK);
    if (!work || !g_ref.out) { perror("calloc"); return 2; }

    pb = calloc(1, PB_SIZE);
    put32(pb + 0,  (unsigned long)(size_t)cb_read);
    put32(pb + 4,  (unsigned long)(size_t)cb_write);
    put32(pb + 8,  (unsigned long)(size_t)cb_unknown1);
    put32(pb + 12, (unsigned long)(size_t)cb_unknown2);
    put32(pb + 16, (unsigned long)(size_t)cb_eof);
    put32(pb + 20, (unsigned long)(size_t)cb_progress);
    put32(pb + 24, (unsigned long)(size_t)cb_debug);
    put32(pb + 28, (unsigned long)(size_t)&g_ref);
    put32(pb + 32, expand ? (unsigned long)inlen : 0u);
    put32(pb + 36, ulen);
    put32(pb + 44, (unsigned long)(size_t)preset);
    put32(pb + 48, (unsigned long)presetlen);
    put32(pb + 52, (unsigned long)(size_t)work);
    put32(pb + 56, worksize);

    if (setjmp(g_escape) == 0) {
        Vector v = (Vector)(void *)(code + (expand ? 0x10 : 0x08));
        st = v(pb, priv);
    } else {
        printf("signal=%d op=%04x at=%ld pc=%ld phase=%s work=%lu reads=%ld "
               "writes=%ld out=%ld pcabs=%lx addr=%lx a0=%lx sp=%lx "
               "code=%lx+%lx\n", g_signal, g_op, g_where, g_pc, argv[2],
               worksize,
               g_ref.reads, g_ref.writes, g_ref.outlen,
               g_pcabs, g_addr, g_a0, g_sp,
               (unsigned long)(size_t)code, (unsigned long)bloblen);
        return 3;
    }

    printf("base=%lx status=%d out=%ld clen=%lu ulen=%lu work=%lu reads=%ld "
           "writes=%ld eofs=%ld progress=%ld debugs=%ld unknown=%ld "
           "debugstr=%s\n",
           (unsigned long)(size_t)code, st, g_ref.outlen,
           get32(pb + 32), get32(pb + 36), worksize,
           g_ref.reads, g_ref.writes, g_ref.eofs, g_ref.progress,
           g_ref.debugs, g_ref.unknown,
           g_lastdebug[0] ? g_lastdebug : "-");

    out = fopen(argv[4], "wb");
    if (!out) { perror(argv[4]); return 2; }
    fwrite(g_ref.out, 1, (size_t)g_ref.outlen, out);
    fclose(out);
    return st != 0;
}
