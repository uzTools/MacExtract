/*
 * repro.c — the engine writes through UncOptions.long_name for every
 * folder-path component, in the three formats that walk a tree.
 *
 * This is the host half of the reproduction of the Mac OS 9 bomb
 * (DECISIONS.md 2026-09-04, *the field nobody assigned*). The Mac shell
 * filled UncOptions field by field and never assigned `long_name` or
 * `long_name_cap`, so the engine saw whatever the stack held there. This
 * program hands it the shape that garbage takes when it looks valid — a
 * pointer to 4 bytes the host owns, and a cap that says a megabyte — and
 * lists an archive with no writes at all (list_only). Under ASan the
 * formats that use the path walker (unc_path_push: DiskDoubler,
 * SuperDisk!, Now Compress) overflow the 4 bytes on their first
 * component; every other format never touches the buffer.
 *
 *   repro FIXTURE          long_name = 4-byte heap block, cap = 1 MB
 *   repro --null FIXTURE   long_name = NULL, cap = 0 (what a host must
 *                          pass when it has no buffer — the fix)
 *
 * Build and run: run.sh.
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "macextract.h"

typedef struct { FILE *f; unc_off_t size; } FileCtx;

static int32_t r_read(void *ctx, void *buf, int32_t len)
{
    FileCtx *c = (FileCtx *)ctx;
    size_t n = fread(buf, 1, (size_t)len, c->f);
    if (n == 0 && ferror(c->f)) return -1;
    return (int32_t)n;
}
static int r_seek(void *ctx, unc_off_t pos)
{
    return fseek(((FileCtx *)ctx)->f, (long)pos, SEEK_SET) == 0 ? 0 : -1;
}
static unc_off_t r_tell(void *ctx) { return (unc_off_t)ftell(((FileCtx *)ctx)->f); }
static unc_off_t r_size(void *ctx) { return ((FileCtx *)ctx)->size; }

static void *a_alloc(void *ctx, uint32_t size) { (void)ctx; return malloc(size); }
static void  a_free(void *ctx, void *p) { (void)ctx; free(p); }

static int entries;
static int s_begin(void *ctx, const UncEntryInfo *info)
{
    (void)ctx; (void)info;
    entries++;
    return 0;
}
static int s_write(void *ctx, UncFork fork, const void *buf, int32_t len)
{ (void)ctx; (void)fork; (void)buf; (void)len; return 0; }
static int s_end(void *ctx, int status) { (void)ctx; (void)status; return 0; }

int main(int argc, char **argv)
{
    FileCtx fc;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    UncOptions opt;
    uint8_t *tiny = NULL;
    int null_mode = 0, ret;
    const char *path;

    if (argc == 3 && strcmp(argv[1], "--null") == 0) { null_mode = 1; path = argv[2]; }
    else if (argc == 2) path = argv[1];
    else { fprintf(stderr, "usage: repro [--null] FIXTURE\n"); return 2; }

    fc.f = fopen(path, "rb");
    if (!fc.f) { perror(path); return 2; }
    fseek(fc.f, 0, SEEK_END);
    fc.size = (unc_off_t)ftell(fc.f);
    fseek(fc.f, 0, SEEK_SET);

    io.ctx = &fc; io.read = r_read; io.seek = r_seek; io.tell = r_tell; io.size = r_size;
    al.ctx = NULL; al.alloc = a_alloc; al.free = a_free;
    memset(&sk, 0, sizeof sk);
    sk.begin_entry = s_begin; sk.write = s_write; sk.end_entry = s_end;

    memset(&opt, 0, sizeof opt);
    opt.list_only = 1;
    if (!null_mode) {
        tiny = (uint8_t *)malloc(4);
        opt.long_name = tiny;
        opt.long_name_cap = 1u << 20;
    }

    ret = unc_extract(&io, &sk, &al, NULL, &opt);
    printf("%s: %s, %d entries, %s (%d), long_name %s\n", path,
           unc_format_name(unc_sniff(&io)), entries, unc_strerror(ret), ret,
           null_mode ? "NULL" : "4-byte block, cap 1 MB");
    free(tiny);
    fclose(fc.f);
    return ret == UNC_OK ? 0 : 1;
}
