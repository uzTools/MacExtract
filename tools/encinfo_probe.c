/* encinfo_probe.c — ask unc_archive_encrypted() about a file, from a script.
 *
 * The answer decides whether the Macintosh shell may release the cipher
 * overlay for an archive (BRANCH_NOTES.md on `overlay-eager`), and a wrong
 * NO costs a capability rather than a disk access: there is no reload. So it
 * wants a regression test that runs where the other encryption tests run,
 * and it has no CLI surface of its own.
 *
 * Prints one line per file: "<yes|no|unknown> <path>". With -f zip or
 * -f cpt it FORCES the format instead of sniffing, which is how the
 * multi-part guards are exercised — a part of a spanned set is claimed by
 * the segment probe long before the plain one, so sniffing alone can never
 * reach the code those guards protect.
 *
 * Built on demand by tools/run_crypt.py; nothing links it into the CLI.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "../src/unc_internal.h"
#include <stdio.h>
#include <string.h>

typedef struct { FILE *f; long size; } FIO;

static int32_t p_read(void *c, void *b, int32_t n)
{ return (int32_t)fread(b, 1, (size_t)n, ((FIO *)c)->f); }
static int p_seek(void *c, unc_off_t p)
{ return fseek(((FIO *)c)->f, (long)p, SEEK_SET); }
static unc_off_t p_tell(void *c) { return ftell(((FIO *)c)->f); }
static unc_off_t p_size(void *c) { return ((FIO *)c)->size; }

int main(int argc, char **argv)
{
    int i, force = 0;
    for (i = 1; i < argc; i++) {
        FIO fio;
        UncIO io;
        UncFormat fmt;
        int e;
        if (!strcmp(argv[i], "-f") && i + 1 < argc) {
            i++;
            force = !strcmp(argv[i], "zip") ? UNC_FORMAT_ZIP
                  : !strcmp(argv[i], "cpt") ? UNC_FORMAT_COMPACTPRO : 0;
            continue;
        }
        fio.f = fopen(argv[i], "rb");
        if (!fio.f) { printf("unknown %s\n", argv[i]); continue; }
        fseek(fio.f, 0, SEEK_END);
        fio.size = ftell(fio.f);
        fseek(fio.f, 0, SEEK_SET);
        io.ctx = &fio; io.read = p_read; io.seek = p_seek;
        io.tell = p_tell; io.size = p_size;
        fmt = force ? (UncFormat)force : unc_sniff(&io);
        e = unc_archive_encrypted(fmt, &io);
        printf("%s %s\n",
               e == UNC_ENC_YES ? "yes" : e == UNC_ENC_NO ? "no" : "unknown",
               argv[i]);
        fclose(fio.f);
    }
    return 0;
}
