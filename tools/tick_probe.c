/* tick_probe.c — how often does the engine call the progress callback?
 *
 * The one property of the engine that NOTHING else here measures. Every
 * other suite grades bytes: the diff harness compares output against an
 * oracle, the robustness one checks that corrupt input is refused, and
 * both are perfectly happy with a decoder that runs to completion
 * without ever letting its caller breathe. On Linux that costs nothing.
 * On a classic Mac it is the whole user interface: `UncProgress.tick` is
 * where the application pumps events, so a format that never calls it
 * freezes the progress dialog and puts BOTH Cancel routes out of reach
 * for as long as the extraction takes.
 *
 * Which is what Now Compress did, from the day it was written until
 * 2026-08-28, and it was found on an emulated Mac rather than here:
 * three Cmd-. in twenty seconds did nothing to a 9.9 MB entry
 * (DECISIONS.md 2026-08-28). This probe is what that finding cost —
 * one number per fixture, and a suite that can fail on it.
 *
 * Prints one line per file:
 *   <path> ret=<n> ticks=<n> max_gap=<bytes> overrun=<bytes> size=<bytes>
 *
 * `max_gap` is the largest jump in `bytes_done` between consecutive
 * ticks — the interval the contract in include/macextract.h bounds.
 * `overrun` is how far `bytes_done` ever passed a known total.
 * tools/run_ticks.py applies the rule; this only measures.
 */
#include <stdio.h>
#include <stdlib.h>
#include "macextract.h"

typedef struct { FILE *f; uint32_t size; } ProbeIO;

static int32_t p_read(void *ctx, void *buf, int32_t len)
{
    ProbeIO *s = (ProbeIO *)ctx;
    return (int32_t)fread(buf, 1, (size_t)len, s->f);
}
static int p_seek(void *ctx, unc_off_t pos)
{
    ProbeIO *s = (ProbeIO *)ctx;
    return fseek(s->f, (long)pos, SEEK_SET);
}
static unc_off_t p_tell(void *ctx)
{
    ProbeIO *s = (ProbeIO *)ctx;
    return (uint32_t)ftell(s->f);
}
static unc_off_t p_size(void *ctx) { return ((ProbeIO *)ctx)->size; }

/* A sink that keeps nothing: this measures the callback, not the bytes. */
static int p_begin(void *ctx, const UncEntryInfo *info)
{ (void)ctx; (void)info; return 0; }
static int p_write(void *ctx, UncFork fork, const void *buf, int32_t len)
{ (void)ctx; (void)fork; (void)buf; (void)len; return 0; }
static int p_end(void *ctx, int status) { (void)ctx; (void)status; return 0; }

static void *p_alloc(void *ctx, uint32_t n) { (void)ctx; return malloc(n); }
static void  p_free(void *ctx, void *ptr)   { (void)ctx; free(ptr); }

static uint32_t ticks, last_done, max_gap, overrun;

static int p_tick(void *ctx, uint32_t done, uint32_t total)
{
    (void)ctx;
    /* How far `done` ever ran past `total`: a pass that reads input the
     * decode proper reads again must not count it twice, or the bar
     * fills early and sits at 100 % (DECISIONS.md 2026-10-09, *the bar
     * that counted the peek*). */
    if (total != UNC_SIZE_UNKNOWN && done > total && done - total > overrun)
        overrun = done - total;
    if (ticks) {
        uint32_t gap = done > last_done ? done - last_done : 0;
        if (gap > max_gap) max_gap = gap;
    }
    ticks++;
    last_done = done;
    return 1;                                    /* never abort */
}

int main(int argc, char **argv)
{
    int i;
    for (i = 1; i < argc; i++) {
        ProbeIO pio;
        UncIO io;
        UncSink sink;
        UncAlloc al;
        UncProgress prog;
        long len;
        int ret;

        pio.f = fopen(argv[i], "rb");
        if (!pio.f) { perror(argv[i]); return 2; }
        if (fseek(pio.f, 0, SEEK_END) != 0) { fclose(pio.f); return 2; }
        len = ftell(pio.f);
        rewind(pio.f);
        pio.size = (uint32_t)len;

        io.ctx = &pio; io.read = p_read; io.seek = p_seek;
        io.tell = p_tell; io.size = p_size;
        sink.ctx = NULL; sink.begin_entry = p_begin; sink.write = p_write;
        sink.end_entry = p_end; sink.comment = NULL;
        al.ctx = NULL; al.alloc = p_alloc; al.free = p_free;
        prog.ctx = NULL; prog.tick = p_tick;

        ticks = 0; last_done = 0; max_gap = 0; overrun = 0;
        ret = unc_extract(&io, &sink, &al, &prog, NULL);
        printf("%s ret=%d ticks=%lu max_gap=%lu overrun=%lu size=%ld\n",
               argv[i], ret, (unsigned long)ticks, (unsigned long)max_gap,
               (unsigned long)overrun, len);
        fclose(pio.f);
    }
    return 0;
}
