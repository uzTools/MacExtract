/* sniff_io_probe.c — what does identifying a file COST in reads?
 *
 * Every other instrument here measures extraction. This one measures
 * `unc_sniff` alone, and it measures the axis a Linux wall clock cannot
 * see: the number of times the engine calls `UncIO.read`, and how many
 * bytes it asks for. On a Macintosh those calls are SetFPos + FSRead
 * pairs on a floppy, which is why fmt_zipseg.c sizes its backwards
 * window by the READ count rather than by the instructions
 * (`unc_zip_scan_eocd`'s comment), and why the sniff order was rearranged
 * twice to keep files away from that scan (src/unc_engine.c).
 *
 * Prints one line per file:
 *   <path> fmt=<name> reads=<n> bytes=<n> seeks=<n> size=<n>
 *
 * tools/run_sniffio.py applies the rules; this only measures. Nothing
 * here extracts anything: the sink is never reached.
 */
#include <stdio.h>
#include <stdlib.h>
#include "macextract.h"

typedef struct {
    FILE    *f;
    uint32_t size;
    unsigned long reads, bytes, seeks;
} ProbeIO;

static int32_t p_read(void *ctx, void *buf, int32_t len)
{
    ProbeIO *s = (ProbeIO *)ctx;
    int32_t got = (int32_t)fread(buf, 1, (size_t)len, s->f);
    s->reads++;
    if (got > 0) s->bytes += (unsigned long)got;
    return got;
}
static int p_seek(void *ctx, unc_off_t pos)
{
    ProbeIO *s = (ProbeIO *)ctx;
    s->seeks++;
    return fseek(s->f, (long)pos, SEEK_SET);
}
static unc_off_t p_tell(void *ctx)
{
    ProbeIO *s = (ProbeIO *)ctx;
    return (uint32_t)ftell(s->f);
}
static unc_off_t p_size(void *ctx) { return ((ProbeIO *)ctx)->size; }

int main(int argc, char **argv)
{
    int i;
    for (i = 1; i < argc; i++) {
        ProbeIO pio;
        UncIO io;
        long len;
        UncFormat f;

        pio.f = fopen(argv[i], "rb");
        if (!pio.f) { perror(argv[i]); return 2; }
        if (fseek(pio.f, 0, SEEK_END) != 0) { fclose(pio.f); return 2; }
        len = ftell(pio.f);
        rewind(pio.f);
        pio.size = (uint32_t)len;
        pio.reads = pio.bytes = pio.seeks = 0;

        io.ctx = &pio; io.read = p_read; io.seek = p_seek;
        io.tell = p_tell; io.size = p_size;

        f = unc_sniff(&io);
        printf("%s fmt=%s reads=%lu bytes=%lu seeks=%lu size=%ld\n",
               argv[i], unc_format_name(f), pio.reads, pio.bytes,
               pio.seeks, len);
        fclose(pio.f);
    }
    return 0;
}
