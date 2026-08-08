/*
 * unclassic CLI — Linux frontend for libunclassic.
 *
 * Commands:
 *   unclassic l <file>            list entries
 *   unclassic x <file>            extract
 *   unclassic t <file>            test (decode + CRC check, no output)
 * Options:
 *   -o <dir>       output directory (default .)
 *   --budget <N>   allocation cap in bytes (simulate a small Mac)
 *   --raw-names    emit raw MacRoman bytes instead of UTF-8 names
 *   --forks <visible|hidden>  resource-fork sidecar naming
 *   --overwrite    write over existing output files (default: refuse)
 *   -f <format>    force format (name from `unclassic formats`)
 *
 * The CLI is the only place libc I/O and malloc are used; the engine
 * sees callbacks only.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unclassic.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/stat.h>
#include <sys/types.h>

/* ------------------------------------------------------------------ */
/* File-backed UncIO                                                  */
/* ------------------------------------------------------------------ */

typedef struct {
    FILE    *f;
    uint32_t size;
} FileIO;

static int32_t fio_read(void *ctx, void *buf, int32_t len)
{
    FileIO *io = (FileIO *)ctx;
    size_t r = fread(buf, 1, (size_t)len, io->f);
    if (r == 0 && ferror(io->f)) return -1;
    return (int32_t)r;
}

static int fio_seek(void *ctx, uint32_t pos)
{
    FileIO *io = (FileIO *)ctx;
    return fseek(io->f, (long)pos, SEEK_SET) == 0 ? 0 : -1;
}

static uint32_t fio_tell(void *ctx)
{
    FileIO *io = (FileIO *)ctx;
    return (uint32_t)ftell(io->f);
}

static uint32_t fio_size(void *ctx)
{
    FileIO *io = (FileIO *)ctx;
    return io->size;
}

/* ------------------------------------------------------------------ */
/* Budgeted allocator with high-water tracking                        */
/* Each block is prefixed with its size so free() can account.        */
/* ------------------------------------------------------------------ */

typedef struct {
    uint32_t budget;     /* 0 = unlimited */
    uint32_t used;
    uint32_t high_water;
    uint32_t failed;     /* count of refused allocations */
} BudgetAlloc;

#define BA_HDR 16  /* keep payload 16-byte aligned */

static void *ba_alloc(void *ctx, uint32_t size)
{
    BudgetAlloc *ba = (BudgetAlloc *)ctx;
    uint8_t *p;
    if (size == 0 || size > 0x7FFFFFFFu - BA_HDR) return NULL;
    if (ba->budget && ba->used + size > ba->budget) {
        ba->failed++;
        return NULL;
    }
    p = (uint8_t *)malloc(size + BA_HDR);
    if (!p) return NULL;
    memcpy(p, &size, sizeof size);
    ba->used += size;
    if (ba->used > ba->high_water) ba->high_water = ba->used;
    return p + BA_HDR;
}

static void ba_free(void *ctx, void *ptr)
{
    BudgetAlloc *ba = (BudgetAlloc *)ctx;
    uint8_t *p = (uint8_t *)ptr - BA_HDR;
    uint32_t size;
    memcpy(&size, p, sizeof size);
    ba->used -= size;
    free(p);
}

/* ------------------------------------------------------------------ */
/* MacRoman → UTF-8 (CLI-side nicety; the engine speaks raw bytes).   */
/* Table: Unicode mappings for 0x80–0xFF from the standard Apple      */
/* MacRoman layout (as used by Python's mac_roman codec / XADMaster   */
/* XADStringCFString). Verified round-trip in tests.                  */
/* ------------------------------------------------------------------ */

static const uint16_t macroman_high[128] = {
    0x00C4,0x00C5,0x00C7,0x00C9,0x00D1,0x00D6,0x00DC,0x00E1,
    0x00E0,0x00E2,0x00E4,0x00E3,0x00E5,0x00E7,0x00E9,0x00E8,
    0x00EA,0x00EB,0x00ED,0x00EC,0x00EE,0x00EF,0x00F1,0x00F3,
    0x00F2,0x00F4,0x00F6,0x00F5,0x00FA,0x00F9,0x00FB,0x00FC,
    0x2020,0x00B0,0x00A2,0x00A3,0x00A7,0x2022,0x00B6,0x00DF,
    0x00AE,0x00A9,0x2122,0x00B4,0x00A8,0x2260,0x00C6,0x00D8,
    0x221E,0x00B1,0x2264,0x2265,0x00A5,0x00B5,0x2202,0x2211,
    0x220F,0x03C0,0x222B,0x00AA,0x00BA,0x03A9,0x00E6,0x00F8,
    0x00BF,0x00A1,0x00AC,0x221A,0x0192,0x2248,0x2206,0x00AB,
    0x00BB,0x2026,0x00A0,0x00C0,0x00C3,0x00D5,0x0152,0x0153,
    0x2013,0x2014,0x201C,0x201D,0x2018,0x2019,0x00F7,0x25CA,
    0x00FF,0x0178,0x2044,0x20AC,0x2039,0x203A,0xFB01,0xFB02,
    0x2021,0x00B7,0x201A,0x201E,0x2030,0x00C2,0x00CA,0x00C1,
    0x00CB,0x00C8,0x00CD,0x00CE,0x00CF,0x00CC,0x00D3,0x00D4,
    0xF8FF,0x00D2,0x00DA,0x00DB,0x00D9,0x0131,0x02C6,0x02DC,
    0x00AF,0x02D8,0x02D9,0x02DA,0x00B8,0x02DD,0x02DB,0x02C7,
};

/* Encode one Unicode code point as UTF-8 into out (max 3 bytes here). */
static int utf8_put(char *out, unsigned cp)
{
    if (cp < 0x80) { out[0] = (char)cp; return 1; }
    if (cp < 0x800) {
        out[0] = (char)(0xC0 | (cp >> 6));
        out[1] = (char)(0x80 | (cp & 0x3F));
        return 2;
    }
    out[0] = (char)(0xE0 | (cp >> 12));
    out[1] = (char)(0x80 | ((cp >> 6) & 0x3F));
    out[2] = (char)(0x80 | (cp & 0x3F));
    return 3;
}

/* Convert an engine entry path to a filesystem path in out.
 * The engine guarantees '/' is always a path separator (Mac name
 * components already carry the classic '/'->':' swap, and ':' is
 * POSIX-legal in a filename). mac_encoding: nonzero → components are
 * MacRoman, else pass through. "." and ".." components are defused. */
static void name_to_fs(const uint8_t *name, uint32_t len, int mac_encoding,
                       int raw, char *out, size_t outsz)
{
    size_t o = 0, comp = 0;    /* comp = start of current component */
    uint32_t i;
    for (i = 0; i <= len && o + 5 < outsz; i++) {
        uint8_t b = i < len ? name[i] : (uint8_t)'/'; /* virtual final sep */
        if (b == '/') {
            size_t cl = o - comp;
            /* Defuse ".", ".." and empty components. */
            if (cl == 0 && i < len) continue;
            if ((cl == 1 && out[comp] == '.') ||
                (cl == 2 && out[comp] == '.' && out[comp + 1] == '.'))
                out[o++] = '_';
            if (i < len) { out[o++] = '/'; comp = o; }
            continue;
        }
        if (b < 0x80 || raw || !mac_encoding) { out[o++] = (char)b; continue; }
        o += (size_t)utf8_put(out + o, macroman_high[b - 0x80]);
    }
    if (o == 0) { out[o++] = '_'; }
    out[o] = 0;
}

/* ------------------------------------------------------------------ */
/* Disk sink                                                          */
/* ------------------------------------------------------------------ */

typedef struct {
    const char *outdir;
    int         list_only;
    int         test_only;
    int         raw_names;
    int         hidden_forks;   /* "._NAME" sidecars, not "NAME.rsrc" */
    int         overwrite;      /* write over existing output files    */
    int         clobber;        /* last open refused: path existed     */
    const char *unwrap_src;     /* envelope being unwrapped, or NULL   */
    int         mac_encoding;   /* names are MacRoman */
    int         verbose;
    FILE       *data_f, *rsrc_f;
    char        cur_path[1024];
    UncEntryInfo cur;
    uint32_t    data_written, rsrc_written;
    int         entries, errors;
    /* For envelope auto-unwrap: shape of what was extracted. */
    int         file_count, dir_count;
    char        last_ok_path[1024];
} DiskSink;

/* Render a type/creator code for the listing. High bytes are MacRoman
 * (decoded to UTF-8 like filenames); whitespace-class bytes become '?'
 * so the listing stays column-parseable. out must hold >= 13 bytes. */
static void fourcc_str(uint32_t v, char *out)
{
    int i;
    size_t o = 0;
    for (i = 0; i < 4; i++) {
        uint8_t b = (uint8_t)(v >> (24 - 8 * i));
        if (b >= 0x80) { o += (size_t)utf8_put(out + o, macroman_high[b - 0x80]); }
        else if (b == '\t' || b == '\n' || b == '\v' || b == '\f' || b == '\r')
            out[o++] = '?';
        else out[o++] = (char)b;
    }
    out[o] = 0;
}

/* mkdir -p for the directory part of path (below outdir). */
static void mkdirs_for(char *path)
{
    char *p;
    for (p = path + 1; *p; p++) {
        if (*p == '/') {
            *p = 0;
            mkdir(path, 0777);
            *p = '/';
        }
    }
}

static int sink_begin(void *ctx, const UncEntryInfo *info)
{
    DiskSink *s = (DiskSink *)ctx;
    char name[512];

    s->cur = *info;
    s->data_written = s->rsrc_written = 0;
    s->entries++;

    name_to_fs(info->name, info->name_len, s->mac_encoding, s->raw_names,
               name, sizeof name);

    if (s->list_only) {
        char t[13], c[13];
        fourcc_str(info->type, t);
        fourcc_str(info->creator, c);
        if (info->is_dir)
            printf("d %10s %10s %-9s %s\n", "-", "-", "-", name);
        else {
            char dsz[16], rsz[16];
            if (info->data_size == UNC_SIZE_UNKNOWN) snprintf(dsz, sizeof dsz, "?");
            else snprintf(dsz, sizeof dsz, "%u", info->data_size);
            if (info->rsrc_size == UNC_SIZE_UNKNOWN) snprintf(rsz, sizeof rsz, "?");
            else snprintf(rsz, sizeof rsz, "%u", info->rsrc_size);
            printf("f %10s %10s %4s/%-4s %s\n", dsz, rsz, t, c, name);
        }
        return 1; /* skip data */
    }

    if (s->test_only) return 0;

    snprintf(s->cur_path, sizeof s->cur_path, "%s/%s", s->outdir, name);
    if (info->is_dir) {
        mkdirs_for(s->cur_path);
        mkdir(s->cur_path, 0777);
        return 1;
    }
    mkdirs_for(s->cur_path);
    return 0;
}

/* Resource-fork sidecar path for a data path, under the convention the
 * caller chose: "NAME.rsrc" (default, and what unar -k visible writes)
 * or "._NAME" (unar -k hidden). The suffix form is ambiguous whenever
 * an archive holds both "X" and "X.rsrc" — a THINK C project is that
 * shape — so the differential harness uses the prefix form, whose
 * namespace is disjoint from real archive names.
 * DECISIONS.md, 2026-08-08. */
static void rsrc_path(const char *path, int hidden, char *out, size_t outsz)
{
    const char *slash;
    if (!hidden) {
        snprintf(out, outsz, "%s.rsrc", path);
        return;
    }
    slash = strrchr(path, '/');
    if (slash)
        snprintf(out, outsz, "%.*s._%s", (int)(slash - path + 1), path,
                 slash + 1);
    else
        snprintf(out, outsz, "._%s", path);
}

/* The envelope currently being unwrapped is exempt from the clobber
 * check: it is deleted moments after the inner layer succeeds, and an
 * inner entry may legitimately carry its name. */
static int sink_unwrap_exempt(DiskSink *s, const char *path)
{
    char rp[1100];
    if (!s->unwrap_src || !s->unwrap_src[0]) return 0;
    if (strcmp(path, s->unwrap_src) == 0) return 1;
    rsrc_path(s->unwrap_src, s->hidden_forks, rp, sizeof rp);
    return strcmp(path, rp) == 0;
}

/* Never write over a file that is already there. Two entries can want
 * the same path — an archive holding both "X" and "X.rsrc" puts the
 * second one on the first one's sidecar — and letting the last writer
 * win destroys a fork that was extracted correctly, without saying so.
 * Refusing makes it a per-entry error like a CRC failure, and names the
 * two ways out. --overwrite restores the old behaviour, which is what
 * re-extracting into a used directory wants. */
static FILE *sink_open_fork(DiskSink *s, UncFork fork)
{
    char path[1100];
    struct stat st;
    if (fork == UNC_FORK_DATA)
        snprintf(path, sizeof path, "%s", s->cur_path);
    else
        rsrc_path(s->cur_path, s->hidden_forks, path, sizeof path);
    s->clobber = 0;
    if (!s->overwrite && stat(path, &st) == 0 &&
        !sink_unwrap_exempt(s, path)) {
        s->clobber = 1;
        fprintf(stderr, "unclassic: %s: output path already exists; re-run "
                "with --forks hidden to keep both forks, or --overwrite\n",
                path);
        return NULL;
    }
    return fopen(path, "wb");
}

static int sink_write(void *ctx, UncFork fork, const void *buf, int32_t len)
{
    DiskSink *s = (DiskSink *)ctx;
    FILE **fp;
    if (s->test_only) {
        if (fork == UNC_FORK_DATA) s->data_written += (uint32_t)len;
        else s->rsrc_written += (uint32_t)len;
        return 0;
    }
    fp = (fork == UNC_FORK_DATA) ? &s->data_f : &s->rsrc_f;
    if (!*fp) {
        *fp = sink_open_fork(s, fork);
        if (!*fp) {
            if (!s->clobber)   /* sink_open_fork already explained that one */
                fprintf(stderr, "unclassic: cannot create output for %s: %s\n",
                        s->cur_path, strerror(errno));
            return -1;
        }
    }
    if (len > 0 && fwrite(buf, 1, (size_t)len, *fp) != (size_t)len) return -1;
    if (fork == UNC_FORK_DATA) s->data_written += (uint32_t)len;
    else s->rsrc_written += (uint32_t)len;
    return 0;
}

static int sink_end(void *ctx, int status)
{
    DiskSink *s = (DiskSink *)ctx;
    char name[512];

    if (!s->test_only && !s->list_only) {
        /* An entry with a data fork of size 0 still gets an empty file.
         * That open can hit the clobber check too — a resource-only
         * entry named "X" collides with the sidecar of an earlier "X"
         * under the hidden convention — so it becomes a per-entry
         * error the same way a write would have. */
        if (!s->cur.is_dir && !s->data_f && s->cur_path[0] && status == UNC_OK) {
            FILE *f = sink_open_fork(s, UNC_FORK_DATA);
            if (f) s->data_f = f;
            else if (s->clobber) status = UNC_ERR_SINK;
        }
        if (s->data_f) { fclose(s->data_f); s->data_f = NULL; }
        if (s->rsrc_f) { fclose(s->rsrc_f); s->rsrc_f = NULL; }
    }

    name_to_fs(s->cur.name, s->cur.name_len, s->mac_encoding, s->raw_names,
               name, sizeof name);

    if (status != UNC_OK) {
        s->errors++;
        fprintf(stderr, "unclassic: %s: %s\n", name, unc_strerror(status));
    } else if (s->verbose && !s->list_only) {
        printf("  %s (%u data, %u rsrc)\n", name, s->data_written, s->rsrc_written);
    }
    if (s->cur.is_dir) s->dir_count++;
    else {
        s->file_count++;
        if (status == UNC_OK && s->cur_path[0])
            snprintf(s->last_ok_path, sizeof s->last_ok_path, "%s",
                     s->cur_path);
    }
    s->cur_path[0] = 0;
    return 0;
}

/* ------------------------------------------------------------------ */
/* Progress                                                           */
/* ------------------------------------------------------------------ */

static int prog_tick(void *ctx, uint32_t done, uint32_t total)
{
    (void)ctx; (void)done; (void)total;
    return 1;
}

/* ------------------------------------------------------------------ */
/* main                                                               */
/* ------------------------------------------------------------------ */

static UncFormat format_by_name(const char *s)
{
    UncFormat f;
    for (f = (UncFormat)1; f < UNC_FORMAT__COUNT; f++)
        if (strcmp(unc_format_name(f), s) == 0) return f;
    return UNC_FORMAT_UNKNOWN;
}

static void usage(void)
{
    fprintf(stderr,
        "usage: unclassic <l|x|t|sniff> [options] <file>\n"
        "  l      list archive contents\n"
        "  x      extract\n"
        "  t      test integrity (decode, verify CRCs, discard output)\n"
        "  sniff  print the detected format\n"
        "options:\n"
        "  -o <dir>       output directory (default .)\n"
        "  --budget <N>   allocation cap in bytes\n"
        "  --raw-names    keep raw MacRoman bytes in filenames\n"
        "  --forks <visible|hidden>  resource forks as NAME.rsrc "
        "(default) or ._NAME\n"
        "  --overwrite    write over existing output files "
        "(default: per-entry error)\n"
        "  -nr            do not auto-unwrap envelope layers (.sit.hqx, ...)\n"
        "  --stats        print allocator statistics\n"
        "  -f <format>    force format\n"
        "  -v             verbose\n");
}

int main(int argc, char **argv)
{
    const char *cmd, *file = NULL, *outdir = ".", *force = NULL;
    int raw_names = 0, verbose = 0, stats = 0, hidden_forks = 0, overwrite = 0;
    uint32_t budget = 0;
    int i;

    FileIO fio;
    BudgetAlloc ba;
    DiskSink sink;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    UncProgress prog;
    UncOptions opt;
    UncFormat fmt;
    int ret;
    int no_recurse = 0, depth = 0;
    char curfile[1024], delfile[1024];
    struct stat st;

    if (argc < 3) { usage(); return 2; }
    cmd = argv[1];

    for (i = 2; i < argc; i++) {
        if (strcmp(argv[i], "-o") == 0 && i + 1 < argc) outdir = argv[++i];
        else if (strcmp(argv[i], "--budget") == 0 && i + 1 < argc)
            budget = (uint32_t)strtoul(argv[++i], NULL, 0);
        else if (strcmp(argv[i], "--raw-names") == 0) raw_names = 1;
        else if (strcmp(argv[i], "--forks") == 0 && i + 1 < argc) {
            const char *k = argv[++i];
            if (strcmp(k, "hidden") == 0) hidden_forks = 1;
            else if (strcmp(k, "visible") == 0) hidden_forks = 0;
            else { usage(); return 2; }
        }
        else if (strcmp(argv[i], "--overwrite") == 0) overwrite = 1;
        else if (strcmp(argv[i], "-nr") == 0) no_recurse = 1;
        else if (strcmp(argv[i], "--stats") == 0) stats = 1;
        else if (strcmp(argv[i], "-f") == 0 && i + 1 < argc) force = argv[++i];
        else if (strcmp(argv[i], "-v") == 0) verbose = 1;
        else if (argv[i][0] == '-') { usage(); return 2; }
        else file = argv[i];
    }
    if (!file) { usage(); return 2; }
    snprintf(curfile, sizeof curfile, "%s", file);
    delfile[0] = 0;

nextlayer:
    file = curfile;
    memset(&fio, 0, sizeof fio);
    fio.f = fopen(file, "rb");
    if (!fio.f) {
        fprintf(stderr, "unclassic: %s: %s\n", file, strerror(errno));
        return 1;
    }
    if (stat(file, &st) == 0) fio.size = (uint32_t)st.st_size;
    else fio.size = UNC_SIZE_UNKNOWN;

    io.ctx = &fio;
    io.read = fio_read;
    io.seek = fio_seek;
    io.tell = fio_tell;
    io.size = fio_size;

    memset(&ba, 0, sizeof ba);
    ba.budget = budget;
    al.ctx = &ba;
    al.alloc = ba_alloc;
    al.free = ba_free;

    memset(&sink, 0, sizeof sink);
    sink.outdir = outdir;
    sink.raw_names = raw_names;
    sink.hidden_forks = hidden_forks;
    sink.overwrite = overwrite;
    sink.unwrap_src = delfile;   /* "" until a layer is being unwrapped */
    sink.verbose = verbose;

    sk.ctx = &sink;
    sk.begin_entry = sink_begin;
    sk.write = sink_write;
    sk.end_entry = sink_end;

    prog.ctx = NULL;
    prog.tick = prog_tick;

    memset(&opt, 0, sizeof opt);

    if (force) {
        fmt = format_by_name(force);
        if (fmt == UNC_FORMAT_UNKNOWN) {
            fprintf(stderr, "unclassic: unknown format '%s'\n", force);
            return 2;
        }
    } else {
        fmt = unc_sniff(&io);
    }

    /* Mac formats carry MacRoman names; zip/tar/gzip do not. */
    switch (fmt) {
    case UNC_FORMAT_ZIP: case UNC_FORMAT_TAR:
    case UNC_FORMAT_GZIP: case UNC_FORMAT_COMPRESS_Z:
        sink.mac_encoding = 0; break;
    default:
        sink.mac_encoding = 1; break;
    }

    if (strcmp(cmd, "sniff") == 0) {
        printf("%s\n", unc_format_name(fmt));
        fclose(fio.f);
        return fmt == UNC_FORMAT_UNKNOWN ? 1 : 0;
    }

    if (fmt == UNC_FORMAT_UNKNOWN) {
        fprintf(stderr, "unclassic: %s: format not recognized\n", file);
        fclose(fio.f);
        return 1;
    }
    if (!unc_format_extractable(fmt)) {
        fprintf(stderr, "unclassic: %s: recognized as %s, which v1 cannot extract\n",
                file, unc_format_name(fmt));
        fclose(fio.f);
        return 1;
    }

    /* Name hint for name-less formats (gzip, .Z): archive basename
     * minus its last extension, unar-style. */
    {
        const char *base = strrchr(file, '/');
        const char *dot;
        base = base ? base + 1 : file;
        dot = strrchr(base, '.');
        opt.name_hint = (const uint8_t *)base;
        opt.name_hint_len = (uint16_t)(dot && dot != base ? (size_t)(dot - base)
                                                          : strlen(base));
    }

    if (strcmp(cmd, "l") == 0) {
        opt.list_only = 1;
        sink.list_only = 1;
    } else if (strcmp(cmd, "t") == 0) {
        opt.test_only = 1;
        sink.test_only = 1;
    } else if (strcmp(cmd, "x") == 0) {
        mkdir(outdir, 0777);
    } else {
        usage();
        fclose(fio.f);
        return 2;
    }

    if (verbose || strcmp(cmd, "l") == 0)
        fprintf(stderr, "%s: %s\n", file, unc_format_name(fmt));

    ret = unc_extract_as(fmt, &io, &sk, &al, &prog, &opt);
    fclose(fio.f);

    if (stats)
        fprintf(stderr, "alloc: high-water %u bytes, %u refused\n",
                ba.high_water, ba.failed);

    if (ret != UNC_OK) {
        fprintf(stderr, "unclassic: %s: %s\n", file, unc_strerror(ret));
        return 1;
    }
    if (sink.errors) {
        fprintf(stderr, "unclassic: %d of %d entries failed\n",
                sink.errors, sink.entries);
        return 1;
    }

    /* This layer extracted cleanly: the previous layer's envelope file
     * (if any) is no longer needed. */
    if (delfile[0]) {
        char rp[1100];
        remove(delfile);
        rsrc_path(delfile, hidden_forks, rp, sizeof rp);
        remove(rp);
        delfile[0] = 0;
    }

    /* Envelope auto-unwrap (real-world files are chained: .sit.hqx,
     * .cpt.bin, .tar.Z ...): when an envelope format yielded exactly
     * one file, sniff it and extract in place. -nr disables. */
    if (strcmp(cmd, "x") == 0 && !no_recurse && depth < 8 &&
        (fmt == UNC_FORMAT_MACBINARY || fmt == UNC_FORMAT_BINHEX ||
         fmt == UNC_FORMAT_APPLESINGLE || fmt == UNC_FORMAT_APPLEDOUBLE ||
         fmt == UNC_FORMAT_GZIP || fmt == UNC_FORMAT_COMPRESS_Z) &&
        sink.file_count == 1 && sink.dir_count == 0 &&
        sink.last_ok_path[0]) {
        FILE *pf = fopen(sink.last_ok_path, "rb");
        if (pf) {
            FileIO pio_f;
            UncIO pio;
            UncFormat pfmt;
            struct stat pst;
            memset(&pio_f, 0, sizeof pio_f);
            pio_f.f = pf;
            pio_f.size = stat(sink.last_ok_path, &pst) == 0
                         ? (uint32_t)pst.st_size : UNC_SIZE_UNKNOWN;
            pio.ctx = &pio_f;
            pio.read = fio_read;
            pio.seek = fio_seek;
            pio.tell = fio_tell;
            pio.size = fio_size;
            pfmt = unc_sniff(&pio);
            fclose(pf);
            if (pfmt != UNC_FORMAT_UNKNOWN && unc_format_extractable(pfmt)) {
                if (verbose)
                    fprintf(stderr, "unwrapping: %s (%s)\n",
                            sink.last_ok_path, unc_format_name(pfmt));
                snprintf(delfile, sizeof delfile, "%s", sink.last_ok_path);
                snprintf(curfile, sizeof curfile, "%s", sink.last_ok_path);
                depth++;
                force = NULL;
                sink.file_count = sink.dir_count = 0;
                sink.last_ok_path[0] = 0;
                sink.entries = sink.errors = 0;
                goto nextlayer;
            }
        }
    }
    return 0;
}
