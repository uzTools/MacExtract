/*
 * macextract CLI — Linux frontend for libmacextract.
 *
 * Commands:
 *   macextract l <file>            list entries
 *   macextract x <file>            extract
 *   macextract t <file>            test (decode + CRC check, no output)
 * Options:
 *   -o <dir>       output directory (default .)
 *   --budget <N>   allocation cap in bytes (simulate a small Mac)
 *   --raw-names    emit raw MacRoman bytes instead of UTF-8 names
 *   --forks <visible|hidden>  resource-fork sidecar naming
 *   --overwrite    write over existing output files (default: refuse)
 *   --only <name>  restrict the command to these entries (repeatable)
 *   --no-comment   do not save the archive's own comment
 *   --preset <f>   SpaceSaver's preset dictionary ('PrAm' -4048)
 *   -f <format>    force format (the name `sniff` prints)
 *
 * The CLI is the only place libc I/O and malloc are used; the engine
 * sees callbacks only.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "macextract.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <dirent.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

/* ------------------------------------------------------------------ */
/* File-backed UncIO                                                  */
/* ------------------------------------------------------------------ */

typedef struct {
    FILE    *f;
    uint32_t size;
} FileIO;

/* `UncIO` addresses a file with a uint32 by decision (FORMATS.md, *Size
 * limits*), and (uint32_t)st_size WRAPS a larger one into a plausible
 * small file — a 4.5 GB zip looked like 237 MB of nonsense and was
 * reported as "not a recognized archive", a true refusal with a false
 * reason. Say what is actually wrong, and hand the engine the largest
 * size it can state rather than a wrapped one: a tar still lists the
 * members that live under 4 GB, which is worth more than a clean
 * refusal of the whole file. */
static uint32_t file_size32(const struct stat *st, const char *path)
{
    if ((uint64_t)st->st_size > (uint64_t)UNC_OFF_MAX) {
        fprintf(stderr, "macextract: %s: file is larger than 4 GB; this engine "
                        "addresses the first 4 GB of it\n", path);
        return UNC_OFF_MAX;
    }
    return (uint32_t)st->st_size;
}

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
    /* The largest shortfall, so a refusal can say HOW MUCH more was
     * wanted rather than only that there was not enough. Measured at the
     * moment of refusal, so it cannot disagree with what happened. */
    uint32_t shortby;
} BudgetAlloc;

#define BA_HDR 16  /* keep payload 16-byte aligned */

static void *ba_alloc(void *ctx, uint32_t size)
{
    BudgetAlloc *ba = (BudgetAlloc *)ctx;
    uint8_t *p;
    if (size == 0 || size > 0x7FFFFFFFu - BA_HDR) return NULL;
    if (ba->budget && ba->used + size > ba->budget) {
        uint32_t need = ba->used + size - ba->budget;
        if (need > ba->shortby) ba->shortby = need;
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
/* Room for any name the engine can hand over: UNC_NAME_MAX bytes of
 * MacRoman, each of which can become three bytes of UTF-8, plus the
 * terminator and the slack name_to_fs keeps. 512 was not enough — a
 * path of accented components could reach 765 and was cut here, after
 * the engine had carried it whole. */
#define FS_NAME_MAX (UNC_NAME_MAX * 3 + 8)

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

/* The archive's own name as text, for the notice at the end of a run.
 * Decoded the way name_to_fs decodes one, but with no cap and no
 * defusing: this goes to a screen, not to a directory entry, and a
 * screen is not the filesystem's to constrain. Control bytes become
 * '?' so a name cannot move the cursor. Returns malloc'd UTF-8. */
static char *name_to_text(const uint8_t *name, size_t len, int mac_encoding,
                          int raw)
{
    char *out = (char *)malloc(len * 3 + 2);
    size_t i, o = 0;
    if (!out) return NULL;
    for (i = 0; i < len; i++) {
        uint8_t b = name[i];
        if (b < 0x20 || b == 0x7F) out[o++] = '?';
        else if (b < 0x80 || raw || !mac_encoding) out[o++] = (char)b;
        else o += (size_t)utf8_put(out + o, macroman_high[b - 0x80]);
    }
    out[o] = 0;
    return out;
}

/* The largest name a format here can state: zip and tar count theirs in
 * 16 bits. Only ever displayed, so this is not a filesystem question. */
#define UNC_LONGNAME_CAP 65536u

/* Room for an output path: the filesystem's own PATH_MAX plus the
 * resource-fork convention and slack. */
#define PATHBUF 4200

/* How many entries one --only run may name. A ceiling of ours, like
 * --part's: nothing in any format says anything about it. */
#define ONLY_MAX 256

/* ---- fitting a name to what the filesystem takes --------------------
 *
 * The engine cuts a name at UNC_NAME_MAX and says so (UncEntryInfo).
 * What fits on the DISK is a second question and the answer is the
 * filesystem's, not ours: `pathconf(_PC_NAME_MAX)` for one directory
 * entry, `_PC_PATH_MAX` for the whole path. A component that does not
 * fit is cut on a UTF-8 character boundary — cutting mid-character
 * would put a byte on disk that is not a name in any encoding — and a
 * file whose shortened name is already taken is numbered ~1, ~2 …, the
 * way an 8.3 filesystem numbered what it had to shorten.
 * DECISIONS.md 2026-08-27, *the name cap*. */

/* The largest k <= max that does not split a UTF-8 character. */
static size_t utf8_fit(const char *str, size_t max)
{
    size_t k = strlen(str);
    if (k <= max) return k;
    k = max;
    while (k > 0 && ((unsigned char)str[k] & 0xC0) == 0x80) k--;
    return k;
}

/* Cut every component of `name` in place to `nmax` bytes; the LAST one
 * also leaves `reserve` free for the resource-fork convention, so both
 * forks of an entry keep the same base. Returns nonzero if it cut. */
static int fs_fit_name(char *name, size_t nmax, size_t reserve)
{
    char *p = name;
    int cut = 0;

    while (*p) {
        char *slash = strchr(p, '/');
        size_t len = slash ? (size_t)(slash - p) : strlen(p);
        size_t max = slash ? nmax : (nmax > reserve ? nmax - reserve : 1);
        if (len > max) {
            size_t keep;
            char c = p[len];
            p[len] = 0;
            keep = utf8_fit(p, max);
            p[len] = c;
            if (keep == 0) { p[0] = '_'; keep = 1; }  /* one huge character */
            memmove(p + keep, p + len, strlen(p + len) + 1);
            cut = 1;
            len = keep;
        }
        if (!p[len]) break;
        p += len + 1;
    }
    return cut;
}

/* ------------------------------------------------------------------ */
/* Disk sink                                                          */
/* ------------------------------------------------------------------ */

/* One name that had to be shortened, for the notice at the end of the
 * run. `full` is how long the archive's own name was, 0 where the
 * format could not say; the name ITSELF is not recoverable — the engine
 * never holds the bytes past its cap. */
typedef struct {
    char    *path;      /* what was written, relative to the output dir */
    char    *orig;      /* the archive's own name in full, or NULL where
                         * the format had already dropped the bytes    */
    unsigned full;      /* the archive's own name length, 0 if unknown  */
    unsigned need;      /* bytes the name wanted on THIS filesystem, or 0 */
    int      numbered;
} CutName;

typedef struct {
    const char *outdir;
    int         list_only;
    int         test_only;
    int         raw_names;
    int         hidden_forks;   /* "._NAME" sidecars, not "NAME.rsrc" */
    int         overwrite;      /* write over existing output files    */
    int         clobber;        /* last open refused: path existed     */
    const char *unwrap_src;     /* envelope being unwrapped, or NULL   */
    /* --only: the entries the user named, and one flag each recording
     * whether anything matched. NULL/0 means "every entry", which is
     * what every run did before 2026-08-28. */
    const char **only;
    unsigned char *only_hit;
    int         nonly;
    int         mac_encoding;   /* names are MacRoman */
    int         verbose;
    const char *archive;        /* the archive's own filename: the
                                 * comment file is named after it       */
    int         no_comment;     /* --no-comment: read it, drop it       */
    FILE       *data_f, *rsrc_f;
    const uint8_t *long_name;   /* UncOptions.long_name: the whole name
                                 * of the entry the engine had to cut */
    long        fs_name_max;    /* pathconf(_PC_NAME_MAX) on outdir */
    long        fs_path_max;    /* pathconf(_PC_PATH_MAX) on outdir */
    CutName    *cuts;           /* names shortened, for the end notice */
    int         ncuts, cutcap;
    char        cur_path[PATHBUF];
    UncEntryInfo cur;
    uint32_t    data_written, rsrc_written;
    int         entries, errors;
    int         unsupported;    /* entries whose METHOD this build lacks */
    int         unsup_method;   /* the first such method, for the message */
    /* For envelope auto-unwrap: shape of what was extracted. */
    int         file_count, dir_count;
    char        last_ok_path[PATHBUF];
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

/* Both are defined below, next to the conventions they implement. */
static void rsrc_path(const char *path, int hidden, char *out, size_t outsz);
static int sink_unwrap_exempt(DiskSink *s, const char *path);

/* Is this path (or its resource-fork sidecar) already on disk? The
 * envelope being unwrapped does not count — it is deleted moments
 * later and an inner entry may legitimately carry its name. */
static int path_taken(DiskSink *s, const char *path)
{
    struct stat st;
    char rp[PATHBUF];
    if (stat(path, &st) == 0 && !sink_unwrap_exempt(s, path)) return 1;
    rsrc_path(path, s->hidden_forks, rp, sizeof rp);
    return stat(rp, &st) == 0 && !sink_unwrap_exempt(s, rp);
}

/* A name we had to shorten can collide with one already written, and
 * two entries that differ only past the cut collide every time. Number
 * the second ~1, the third ~2, rather than refusing it. Returns nonzero
 * if a number was used. Directories are never numbered: two folders
 * that shorten alike merge, which is what the children need. */
static int sink_number_path(DiskSink *s, size_t leafmax)
{
    char base[PATHBUF];
    char *leaf;
    int n;

    leaf = strrchr(s->cur_path, '/');
    leaf = leaf ? leaf + 1 : s->cur_path;
    snprintf(base, sizeof base, "%s", leaf);
    for (n = 1; n <= 999; n++) {
        char suffix[8];
        size_t keep;
        int slen = snprintf(suffix, sizeof suffix, "~%d", n);
        keep = utf8_fit(base, leafmax > (size_t)slen ? leafmax - (size_t)slen
                                                     : 0);
        memcpy(leaf, base, keep);
        memcpy(leaf + keep, suffix, (size_t)slen + 1);
        if (!path_taken(s, s->cur_path)) return 1;
    }
    snprintf(leaf, sizeof base, "%s", base);   /* give up; the clobber
                                                * rule speaks instead */
    return 0;
}

/* Remember a shortened name for the notice at the end of the run. */
static void sink_note_cut(DiskSink *s, const char *path, const char *orig,
                          unsigned full, unsigned need, int numbered)
{
    size_t n;
    char *copy;
    if (s->ncuts == s->cutcap) {
        int cap = s->cutcap ? s->cutcap * 2 : 8;
        CutName *p = (CutName *)realloc(s->cuts, (size_t)cap * sizeof *p);
        if (!p) return;            /* the notice is not worth failing over */
        s->cuts = p;
        s->cutcap = cap;
    }
    n = strlen(path) + 1;
    copy = (char *)malloc(n);
    if (!copy) return;
    memcpy(copy, path, n);
    s->cuts[s->ncuts].path = copy;
    s->cuts[s->ncuts].orig = NULL;
    if (orig) {
        size_t on = strlen(orig) + 1;
        char *oc = (char *)malloc(on);
        if (oc) {
            memcpy(oc, orig, on);
            s->cuts[s->ncuts].orig = oc;
        }
    }
    s->cuts[s->ncuts].full = full;
    s->cuts[s->ncuts].need = need;
    s->cuts[s->ncuts].numbered = numbered;
    s->ncuts++;
}

/* The notice itself: what was shortened, and how long the archive said
 * the name was. Printed once at the end of a layer, then forgotten. */
static void sink_report_cuts(DiskSink *s)
{
    int i;
    if (!s->ncuts) return;
    fprintf(stderr, "macextract: %d name%s did not fit and %s shortened:\n",
            s->ncuts, s->ncuts == 1 ? "" : "s",
            s->ncuts == 1 ? "was" : "were");
    for (i = 0; i < s->ncuts; i++) {
        if (s->cuts[i].orig) {
            /* The archive's name, whole, whatever the disk could take. */
            fprintf(stderr, "macextract:   %s\n", s->cuts[i].orig);
            fprintf(stderr, "macextract:     written as %s", s->cuts[i].path);
        } else {
            fprintf(stderr, "macextract:   %s", s->cuts[i].path);
            if (s->cuts[i].full)
                fprintf(stderr, "  (the archive's name is %u bytes; the rest "
                                "was cut before it reached us)",
                        s->cuts[i].full);
            else if (!s->cuts[i].need)
                fprintf(stderr, "  (the archive's name is longer; the rest "
                                "was cut before it reached us)");
        }
        if (s->cuts[i].need)
            fprintf(stderr, "  (needs %u bytes, this filesystem takes %ld)",
                    s->cuts[i].need, s->fs_name_max);
        if (s->cuts[i].numbered)
            fprintf(stderr, "  (numbered: the shortened name was taken)");
        fprintf(stderr, "\n");
        free(s->cuts[i].path);
        free(s->cuts[i].orig);
    }
    free(s->cuts);
    s->cuts = NULL;
    s->ncuts = s->cutcap = 0;
}

/* The archive's own name for this entry, as text, or NULL where the
 * format had already dropped the bytes before the engine saw them.
 * Caller frees. */
static char *sink_orig_name(DiskSink *s, const UncEntryInfo *info)
{
    if (info->name_truncated != 2 || !s->long_name) return NULL;
    return name_to_text(s->long_name, strlen((const char *)s->long_name),
                        s->mac_encoding, s->raw_names);
}

/* --only: did the user name this entry? It matches a selector exactly,
 * or lies under one — naming a folder takes what is in it — and the
 * comparison is against the name `l` prints, so a row copied out of a
 * listing is a selector.
 *
 * Every match is recorded rather than the first, because the flags are
 * what let the run report a selector that matched NOTHING: a mistyped
 * name would otherwise extract nothing and say nothing, and exit 0. */
static int only_wanted(DiskSink *s, const char *name)
{
    int i, want = 0;

    if (!s->nonly) return 1;
    for (i = 0; i < s->nonly; i++) {
        size_t n = strlen(s->only[i]);
        if (strcmp(name, s->only[i]) == 0 ||
            (strncmp(name, s->only[i], n) == 0 && name[n] == '/')) {
            s->only_hit[i] = 1;
            want = 1;
        }
    }
    return want;
}

static int sink_begin(void *ctx, const UncEntryInfo *info)
{
    DiskSink *s = (DiskSink *)ctx;
    char name[FS_NAME_MAX];

    name_to_fs(info->name, info->name_len, s->mac_encoding, s->raw_names,
               name, sizeof name);

    /* Not asked for: skipped before it counts, so the tallies at the end
     * describe the SELECTION rather than the archive. */
    if (!only_wanted(s, name)) return 1;

    s->cur = *info;
    s->data_written = s->rsrc_written = 0;
    s->entries++;

    if (s->list_only) {
        char t[13], c[13];
        /* Nothing is written, so the filesystem's caps do not apply —
         * but the engine's did, and the row below is then not the
         * archive's name. Say so once, at the end, as extraction does. */
        if (info->name_truncated) {
            char *orig = sink_orig_name(s, info);
            sink_note_cut(s, name, orig, info->name_full_len, 0, 0);
            free(orig);
        }
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

    if (s->test_only) {
        if (info->name_truncated) {
            char *orig = sink_orig_name(s, info);
            sink_note_cut(s, name, orig, info->name_full_len, 0, 0);
            free(orig);
        }
        return 0;
    }

    /* Fit the name to the filesystem, not to a constant of ours: the
     * engine has already cut it at UNC_NAME_MAX if it had to, and what
     * one directory entry takes is pathconf's answer. Both cuts land
     * in the same notice at the end of the run. */
    {
        /* Room for the resource-fork convention, so both forks of an
         * entry keep the same base — but only for an entry that HAS
         * one, or a 255-byte zip name would be shortened to make room
         * for a sidecar that is never written. */
        size_t reserve = info->rsrc_size == 0 ? 0u
                       : (s->hidden_forks ? 2u : 5u);   /* "._" or ".rsrc" */
        size_t leafmax = (size_t)s->fs_name_max > reserve
                       ? (size_t)s->fs_name_max - reserve : 1u;
        char before[FS_NAME_MAX];
        unsigned need = (unsigned)strlen(name);
        int fitted;
        snprintf(before, sizeof before, "%s", name);
        fitted = fs_fit_name(name, (size_t)s->fs_name_max, reserve);
        int cut = info->name_truncated || fitted;
        int numbered = 0;

        if ((size_t)snprintf(s->cur_path, sizeof s->cur_path, "%s/%s",
                             s->outdir, name) >= sizeof s->cur_path ||
            strlen(s->cur_path) >= (size_t)s->fs_path_max) {
            /* This one IS the filesystem's answer: no shortening of a
             * name can make a path shorter than its directory. */
            fprintf(stderr, "macextract: %s: the output path is longer than "
                            "this filesystem takes (%ld bytes); not "
                            "extracted\n", name, s->fs_path_max);
            s->cur_path[0] = 0;
            s->errors++;
            return 1;
        }
        if (cut && !info->is_dir && !s->overwrite &&
            path_taken(s, s->cur_path))
            numbered = sink_number_path(s, leafmax);
        if (cut) {
            const char *shown = s->cur_path + strlen(s->outdir);
            char *orig = sink_orig_name(s, info);
            while (*shown == '/') shown++;
            /* Where the FILESYSTEM was the limit, the engine carried the
             * whole name and `before` still holds it. */
            sink_note_cut(s, shown, orig ? orig : (fitted ? before : NULL),
                          info->name_full_len, fitted ? need : 0u, numbered);
            free(orig);
        }
    }

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

/* StuffIt classic keeps the block that verifies a password in the
 * ARCHIVE's resource fork ('MKey' 0), so an encrypted .sit can only be
 * decrypted where that fork survived. On this side of the world it
 * survives as the sidecar file this program itself writes when it takes
 * a MacBinary or BinHex envelope off — so look for it under both
 * spellings, and say nothing if there is none. */
static int load_mkey(const char *path, int hidden, uint8_t out[8])
{
    static uint8_t fork[256 * 1024];
    char rp[1100];
    int which;

    for (which = 0; which < 2; which++) {
        FILE *f;
        size_t n;
        uint32_t off = 0, len = 0;
        rsrc_path(path, which == 0 ? hidden : !hidden, rp, sizeof rp);
        f = fopen(rp, "rb");
        if (!f) continue;
        n = fread(fork, 1, sizeof fork, f);
        fclose(f);
        if (unc_resfork_find(fork, (uint32_t)n, 0x4D4B6579u /* 'MKey' */, 0,
                             &off, &len) == UNC_OK && len == 8) {
            memcpy(out, fork + off, 8);
            return 1;
        }
    }
    return 0;
}

/* --ask: prompt for a password on the terminal, and again when the
 * archive rejects the one given. Returning 0 (an empty line, or EOF)
 * is how the user says "skip it", and the entry then fails cleanly. */
static int cli_ask_password(void *ctx, uint8_t *buf, uint16_t cap,
                            uint16_t *len, int attempt)
{
    char line[UNC_PASSWORD_MAX + 2];
    size_t n;
    (void)ctx;
    fprintf(stderr, attempt ? "password (wrong, try again, empty to skip): "
                            : "password (empty to skip): ");
    fflush(stderr);
    if (!fgets(line, (int)sizeof line, stdin)) return 0;
    n = strlen(line);
    while (n > 0 && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
    if (n == 0) return 0;
    if (n > cap) n = cap;
    memcpy(buf, line, n);
    *len = (uint16_t)n;
    return 1;
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
    char path[PATHBUF];
    struct stat st;
    if (fork == UNC_FORK_DATA)
        snprintf(path, sizeof path, "%s", s->cur_path);
    else
        rsrc_path(s->cur_path, s->hidden_forks, path, sizeof path);
    s->clobber = 0;
    if (!s->overwrite && stat(path, &st) == 0 &&
        !sink_unwrap_exempt(s, path)) {
        s->clobber = 1;
        fprintf(stderr, "macextract: %s: output path already exists; re-run "
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
                fprintf(stderr, "macextract: cannot create output for %s: %s\n",
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
    char name[FS_NAME_MAX];

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
        if (status == UNC_ERR_UNSUPPORTED) {
            /* Name the method. A report that says "method 13" is one
             * somebody can act on; "unsupported" is not. The id is
             * informational (UncEntryInfo), and 0 means the format did
             * not state one. */
            unsigned m = s->cur.method_data ? s->cur.method_data
                                            : s->cur.method_rsrc;
            if (!s->unsupported) s->unsup_method = (int)m;
            s->unsupported++;
            if (m)
                fprintf(stderr, "macextract: %s: method %u is not supported "
                                "yet\n", name, m);
            else
                fprintf(stderr, "macextract: %s: %s\n", name,
                        unc_strerror(status));
        } else {
            fprintf(stderr, "macextract: %s: %s\n", name, unc_strerror(status));
        }
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

/* An archive comment belongs to the archive, not to any entry, so it
 * cannot be an entry: it is written beside the extracted items as
 * "<archive>.comment.txt" — a name derived from the archive's, so that
 * it cannot collide with one of the archive's own. Listing or testing
 * prints it instead, since neither writes files.
 *
 * PRINTED text is decoded from MacRoman like a filename (--raw-names
 * keeps the raw bytes); the SAVED file is the archive's bytes exactly,
 * MacRoman and CR line endings and all. That split is deliberate:
 * printing is display, where the terminal's encoding wins, but the file
 * is the comment itself, and the Mac shell writes the same bytes into
 * its own "Comments" document — so the two hosts save one thing, and a
 * harness can compare them directly. */
static int sink_comment(void *ctx, const uint8_t *buf, uint16_t len)
{
    DiskSink *s = (DiskSink *)ctx;
    /* Flushed as it fills rather than held whole: a zip states its
     * comment length in two bytes, so UNC_COMMENT_MAX is 64 KB and
     * sizing a buffer by it would put 192 KB on the stack. Three bytes
     * is the most one input byte can produce. */
    char text[384];
    char path[1200];
    const char *base;
    size_t o = 0;
    uint16_t i;
    struct stat st;
    FILE *f;

    if (s->no_comment) return 0;

    if (s->list_only || s->test_only) {
        fputs("comment: ", stdout);
        for (i = 0; i < len; i++) {
            uint8_t b = buf[i];
            if (o + 3 > sizeof text) {
                fwrite(text, 1, o, stdout);
                o = 0;
            }
            /* A Mac ends a line with CR, and a CR sent to a terminal
             * returns the carriage and overwrites what was printed —
             * measured on a two-line note Compact Pro 1.51 wrote. The
             * SAVED file keeps the CR; only the printed copy changes. */
            if (b == '\r') {
                if (i + 1 < len && buf[i + 1] == '\n') i++;
                text[o++] = '\n';
            }
            else if (b < 0x80 || s->raw_names || !s->mac_encoding)
                text[o++] = (char)b;
            else o += (size_t)utf8_put(text + o, macroman_high[b - 0x80]);
        }
        if (o) fwrite(text, 1, o, stdout);
        putchar('\n');
        return 0;
    }

    base = s->archive ? strrchr(s->archive, '/') : NULL;
    base = base ? base + 1 : (s->archive ? s->archive : "archive");
    if ((size_t)snprintf(path, sizeof path, "%s/%s.comment.txt",
                         s->outdir, base) >= sizeof path) {
        fprintf(stderr, "macextract: comment: output path too long\n");
        return 0;
    }
    if (!s->overwrite && stat(path, &st) == 0) {
        fprintf(stderr, "macextract: %s: output path already exists; "
                "the archive comment was not written (use --overwrite)\n",
                path);
        return 0;
    }
    f = fopen(path, "wb");
    if (!f || fwrite(buf, 1, len, f) != len) {
        fprintf(stderr, "macextract: %s: %s\n", path, strerror(errno));
        if (f) fclose(f);
        return 0;    /* a comment is not worth failing the archive over */
    }
    if (fclose(f) != 0) {
        fprintf(stderr, "macextract: %s: %s\n", path, strerror(errno));
        return 0;
    }
    if (s->verbose) printf("  %s (archive comment)\n", path);
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
/* Envelopes                                                          */
/*                                                                    */
/* One file in, one file out: the layers a real download is chained    */
/* from (.sit.hqx, .cpt.bin, .tar.Z). WHICH formats those are is the   */
/* engine's to say — unc_format_is_envelope(), and the table behind it */
/* in src/unc_engine.c has the reasoning. It was a list here and a     */
/* second copy in the Mac shell until 2026-08-27, and the two          */
/* disagreed for a day.                                               */
/* ------------------------------------------------------------------ */


/* Sink for taking one envelope off a file, in either of two modes.
 *
 * PEEK (head != NULL) collects the first `cap` bytes of the data fork
 * and then asks to stop, which is what makes it affordable to look
 * inside every envelope in a directory. PEEL (out != NULL) streams the
 * whole data fork to a file.
 *
 * The resource fork is ignored in both: a part of a segmented set is a
 * run of bytes that happens to have travelled inside a Macintosh file,
 * and every scheme here concatenates data forks (unc_extract_segments).
 * An envelope holding a part with a resource fork would be a file this
 * program has never seen, and inventing a meaning for it here is the
 * one thing rule #1 forbids. */
typedef struct {
    FILE    *out;           /* PEEL: where the data fork goes          */
    uint8_t *head;          /* PEEK: where the first bytes go          */
    int32_t  cap, len;
    int      entries;       /* how many entries the envelope yielded   */
    int      err;
} EnvSink;

static int env_begin(void *ctx, const UncEntryInfo *info)
{
    EnvSink *e = (EnvSink *)ctx;
    if (info->is_dir) { e->entries++; return 1; }
    return e->entries++ ? 1 : 0;      /* the first file is the payload */
}

static int env_write(void *ctx, UncFork fork, const void *buf, int32_t len)
{
    EnvSink *e = (EnvSink *)ctx;

    if (fork != UNC_FORK_DATA || len <= 0) return 0;
    if (e->out) {
        if (fwrite(buf, 1, (size_t)len, e->out) != (size_t)len) {
            e->err = 1;
            return -1;
        }
        return 0;
    }
    if (e->len < e->cap) {
        int32_t n = e->cap - e->len;
        if (n > len) n = len;
        memcpy(e->head + e->len, buf, (size_t)n);
        e->len += n;
    }
    /* Enough to decide on. Stopping here is the difference between
     * reading a hundred bytes of every envelope in a directory and
     * decoding all of them; it is reported as a per-entry failure,
     * which is why a peek is judged by what it collected and never by
     * the status it returns. */
    return e->len >= e->cap ? -1 : 0;
}

static int env_end(void *ctx, int status)
{
    EnvSink *e = (EnvSink *)ctx;
    if (e->out && status != UNC_OK) e->err = 1;
    return 0;
}

/* Run one envelope layer of `path` into `es`. Returns 0 if the file is
 * not an envelope at all. */
static int env_run(const char *path, EnvSink *es)
{
    FileIO f;
    UncIO eio;
    UncSink sk;
    UncAlloc al;
    BudgetAlloc ba;
    UncProgress prog;
    UncFormat fmt;
    struct stat st;
    int rc;

    memset(&f, 0, sizeof f);
    f.f = fopen(path, "rb");
    if (!f.f) return 0;
    f.size = stat(path, &st) == 0 ? (uint32_t)st.st_size : UNC_SIZE_UNKNOWN;
    eio.ctx = &f;
    eio.read = fio_read;
    eio.seek = fio_seek;
    eio.tell = fio_tell;
    eio.size = fio_size;

    fmt = unc_sniff(&eio);
    if (!unc_format_is_envelope(fmt)) { fclose(f.f); return 0; }

    memset(&ba, 0, sizeof ba);          /* budget 0: no cap */
    al.ctx = &ba;
    al.alloc = ba_alloc;
    al.free = ba_free;
    sk.ctx = es;
    sk.begin_entry = env_begin;
    sk.write = env_write;
    sk.end_entry = env_end;
    sk.comment = NULL;    /* an envelope layer carries none */
    prog.ctx = NULL;
    prog.tick = prog_tick;

    rc = unc_extract_as(fmt, &eio, &sk, &al, &prog, NULL);
    fclose(f.f);
    if (es->out && rc != UNC_OK) es->err = 1;
    return 1;
}

/* First `cap` bytes of what one envelope layer of `path` holds.
 * Returns how many were collected; 0 for a file that is not an
 * envelope, or whose payload is shorter than a decision needs. */
static int32_t env_peek(const char *path, uint8_t *head, int32_t cap)
{
    EnvSink es;
    memset(&es, 0, sizeof es);
    es.head = head;
    es.cap = cap;
    if (!env_run(path, &es)) return 0;
    return es.len;
}

/* Take one envelope off `path`, writing the payload to `dest`.
 * Returns 1 on success. */
static int env_peel(const char *path, const char *dest)
{
    EnvSink es;
    int ok;

    memset(&es, 0, sizeof es);
    es.out = fopen(dest, "wb");
    if (!es.out) return 0;
    ok = env_run(path, &es);
    if (fclose(es.out) != 0) es.err = 1;
    return ok && !es.err;
}

/* ------------------------------------------------------------------ */
/* Volume source: where the parts of a segmented archive come from     */
/*                                                                    */
/* Three ways in, all ending at the same fingerprint check, because a  */
/* filename is never evidence that a file belongs to a set:            */
/*   1. --part FILE, stated by the user (checked all the same);        */
/*   2. a scan of the directory the opened part came from;             */
/*   3. --ask, which reads a path from stdin — the CLI's stand-in for  */
/*      the Mac's "locate part N" dialog, so both hosts exercise the   */
/*      same engine callback.                                          */
/* Default is non-interactive: a missing part is an error, never a     */
/* prompt, so no test run can block.                                   */
/* ------------------------------------------------------------------ */

typedef struct {
    UncSegmentDesc desc;
    char    *path[UNC_SEG_MAX_PARTS + 1];  /* NULL = not located yet */
    FileIO   open_io;                      /* one part open at a time */
    int      ask;
    int      verbose;
    /* Parts that arrived inside an envelope are decoded to here before
     * the join; see seg_wrapped_part_of. Empty until one has been. */
    const char *outdir;
    char     peeldir[1024];
} SegHost;

/* Read a candidate's first bytes and return its part number in the
 * set, or 0. Never opens directories or unreadable files. */
static int seg_part_of(const SegHost *h, const char *path)
{
    uint8_t head[UNC_SEG_HEAD];
    size_t got;
    FILE *f;
    struct stat st;

    if (stat(path, &st) != 0 || !S_ISREG(st.st_mode)) return 0;
    f = fopen(path, "rb");
    if (!f) return 0;
    got = fread(head, 1, sizeof head, f);
    fclose(f);
    return unc_segment_match(&h->desc, head, (int32_t)got);
}

/* strdup is POSIX, and this file builds -std=c99 -pedantic. */
static char *seg_dup(const char *s)
{
    size_t n = strlen(s) + 1;
    char *p = (char *)malloc(n);
    if (p) memcpy(p, s, n);
    return p;
}

static void seg_record(SegHost *h, int part, const char *path)
{
    if (part < 1 || part > UNC_SEG_MAX_PARTS) return;
    if (h->path[part]) return;              /* first match wins */
    h->path[part] = seg_dup(path);
    if (h->verbose)
        fprintf(stderr, "part %d: %s\n", part, path);
}

/* ------------------------------------------------------------------ */
/* Parts that arrived inside an envelope                               */
/*                                                                    */
/* A real download is per-part wrapped — Archive.sit.1.hqx,            */
/* Archive.sit.2.hqx — so the envelope has to come off BEFORE the      */
/* join, where this program's ordinary auto-unwrap runs after it. The  */
/* part is decoded to a file beside the output and the joiner is given */
/* that; the decoded parts are deleted as soon as the join is over.    */
/*                                                                    */
/* Only the StuffIt scheme is looked for this way, because it is the   */
/* only one whose parts arrive wrapped in the wild: its header is in   */
/* the payload, so unwrapping is all that stands between the file and  */
/* the same fingerprint check every other part gets. A DiskDoubler     */
/* `SPLT` part could prove itself the same way and nothing looks for   */
/* one, because no wrapped specimen of that shape has been seen. A     */
/* spanned zip or a .NNN split is placed by its FILENAME, and the name */
/* of a wrapped part is the wrapper's — no reference implementation    */
/* says what that name should look like, and guessing one is exactly   */
/* what rule #1 forbids.                                              */
/* ------------------------------------------------------------------ */

#define SEG_PEELDIR ".macextract-parts"

/* Make the directory decoded parts go in. It is inside the output
 * directory, which the caller has already created and is the one place
 * this program knows it may write. */
static int seg_peel_dir(SegHost *h)
{
    if (h->peeldir[0]) return 1;
    if (!h->outdir) return 0;
    if ((size_t)snprintf(h->peeldir, sizeof h->peeldir, "%s/%s",
                         h->outdir, SEG_PEELDIR) >= sizeof h->peeldir) {
        h->peeldir[0] = 0;
        return 0;
    }
    if (mkdir(h->peeldir, 0700) != 0 && errno != EEXIST) {
        h->peeldir[0] = 0;
        return 0;
    }
    return 1;
}

/* Remove the decoded parts and the directory holding them. Called
 * whatever the join did: they are this program's own litter, and an
 * archive that failed to join is exactly when a user is least helped
 * by finding pieces of it lying around. */
static void seg_peel_clean(SegHost *h)
{
    DIR *d;
    struct dirent *de;

    if (!h->peeldir[0]) return;
    d = opendir(h->peeldir);
    if (d) {
        while ((de = readdir(d)) != NULL) {
            char p[1200];
            if (strcmp(de->d_name, ".") == 0 || strcmp(de->d_name, "..") == 0)
                continue;
            if ((size_t)snprintf(p, sizeof p, "%s/%s", h->peeldir, de->d_name)
                < sizeof p)
                remove(p);
        }
        closedir(d);
    }
    remove(h->peeldir);
    h->peeldir[0] = 0;
}

/* Do the parts found so far account for the whole set?
 *
 * A StuffIt part states the original file's two fork lengths, so their
 * sum is the payload the set holds and summing to it is what ends the
 * joiner's walk (fmt_sitseg.c). The same sum answers the only question
 * a host needs here: is there anything still to look for. Parts are
 * read in order, so a gap ends the count whatever sits past it. */
static int seg_have_all(const SegHost *h)
{
    uint32_t sum = 0;
    int p;

    if (h->desc.total == UNC_SIZE_UNKNOWN) return 0;
    for (p = 1; p <= UNC_SEG_MAX_PARTS && h->path[p]; p++) {
        struct stat st;
        if (stat(h->path[p], &st) != 0) return 0;
        if ((uint32_t)st.st_size <= h->desc.head_len) return 0;
        sum += (uint32_t)st.st_size - h->desc.head_len;
        if (sum >= h->desc.total) return 1;
    }
    return 0;
}

/* Is `path` an envelope holding a part of this set? If so the part is
 * decoded whole and recorded, and its number returned.
 *
 * The first UNC_SEG_HEAD bytes are what decides, so an envelope that
 * has nothing to do with this set costs a hundred decoded bytes rather
 * than a whole decode. One layer only: Archive.sit.1.hqx is the shape
 * that exists, and a second would be a guess. */
static int seg_wrapped_part_of(SegHost *h, const char *path)
{
    uint8_t head[UNC_SEG_HEAD];
    char dest[1200];
    struct stat st;
    int32_t got;
    int part;

    /* Same gate seg_part_of applies: directories and unreadable things
     * are not candidates, and fopen() on a directory succeeds here. */
    if (stat(path, &st) != 0 || !S_ISREG(st.st_mode)) return 0;

    got = env_peek(path, head, (int32_t)sizeof head);
    /* Said out loud because it is the cost this search is rationed by:
     * every envelope beside the archive is decoded this far, and only
     * a set that is missing a part pays for it at all. */
    if (h->verbose && got > 0)
        fprintf(stderr, "looked inside %s\n", path);
    part = got > 0 ? unc_segment_match(&h->desc, head, got) : 0;
    if (part < 1) return 0;                    /* not one of ours */
    if (h->path[part]) return part;            /* already have that one */

    if (!seg_peel_dir(h)) return 0;
    if ((size_t)snprintf(dest, sizeof dest, "%s/part-%03d", h->peeldir, part)
        >= sizeof dest)
        return 0;
    if (!env_peel(path, dest)) { remove(dest); return 0; }

    if (h->verbose)
        fprintf(stderr, "unwrapping part %d: %s\n", part, path);
    seg_record(h, part, dest);
    return part;
}

/* Scan the directory holding `anchor` for parts of the set. With
 * `wrapped`, a candidate that is not a part in its own right is also
 * tried as an envelope holding one. */
static void seg_scan_dir(SegHost *h, const char *anchor, int wrapped)
{
    char dir[1024], cand[1200];
    const char *slash = strrchr(anchor, '/');
    DIR *d;
    struct dirent *de;

    if (slash) {
        size_t n = (size_t)(slash - anchor);
        if (n >= sizeof dir) return;
        memcpy(dir, anchor, n);
        dir[n] = 0;
        if (n == 0) { dir[0] = '/'; dir[1] = 0; }
    } else {
        dir[0] = '.'; dir[1] = 0;
    }

    d = opendir(dir);
    if (!d) return;
    while ((de = readdir(d)) != NULL) {
        int part;
        if (strcmp(de->d_name, ".") == 0 || strcmp(de->d_name, "..") == 0)
            continue;
        if ((size_t)snprintf(cand, sizeof cand, "%s/%s", dir, de->d_name)
            >= sizeof cand)
            continue;
        part = seg_part_of(h, cand);
        if (part) { seg_record(h, part, cand); continue; }
        if (wrapped) (void)seg_wrapped_part_of(h, cand);
    }
    closedir(d);
}

/* ------------------------------------------------------------------ */
/* Spanned zip: the same three ways in, decided by NAME                 */
/*                                                                    */
/* A spanned zip fingerprints nothing, so unc_segment_match cannot be  */
/* asked and the parts are ordered the only way the format allows —    */
/* by the extension Info-ZIP gives them, NAME.z01 ... NAME.z99 with    */
/* the last part called NAME.zip. (Source: the volume regex in         */
/* reference/XADMaster/XADZipParser.m +volumesForHandle:,              */
/* `^NAME\.(zip|z[0-9]{2})$`, matched case-insensitively against the   */
/* directory the opened part came from.) What keeps a wrong file out   */
/* is not this scan but the structural check the engine makes on the   */
/* assembled set; see unc_extract_segments in macextract.h.            */
/* ------------------------------------------------------------------ */

static int ascii_lower(int ch)
{
    return (ch >= 'A' && ch <= 'Z') ? ch - 'A' + 'a' : ch;
}

/* Which part of the family `name` is, given the stem the family shares:
 * NN for a ".zNN" extension, ZIPFAM_LAST for ".zip", 0 for no match. */
#define ZIPFAM_LAST (-1)

static int zipfam_part_of(const char *stem, size_t stemlen, const char *name)
{
    size_t i;
    const char *ext;

    for (i = 0; i < stemlen; i++)
        if (ascii_lower((unsigned char)name[i]) !=
            ascii_lower((unsigned char)stem[i]) || name[i] == 0)
            return 0;
    if (name[stemlen] != '.') return 0;
    ext = name + stemlen + 1;

    if (ascii_lower((unsigned char)ext[0]) == 'z' &&
        ascii_lower((unsigned char)ext[1]) == 'i' &&
        ascii_lower((unsigned char)ext[2]) == 'p' && ext[3] == 0)
        return ZIPFAM_LAST;
    if (ascii_lower((unsigned char)ext[0]) == 'z' &&
        ext[1] >= '0' && ext[1] <= '9' &&
        ext[2] >= '0' && ext[2] <= '9' && ext[3] == 0) {
        int n = (ext[1] - '0') * 10 + (ext[2] - '0');
        return n >= 1 ? n : 0;      /* there is no part zero */
    }
    return 0;
}

/* Which part a path's own extension names, independent of any family:
 * what --part has to go on when the file was given from elsewhere. */
static int zip_ext_part(const char *path)
{
    const char *slash = strrchr(path, '/');
    const char *base = slash ? slash + 1 : path;
    const char *dot = strrchr(base, '.');
    if (!dot || dot == base) return 0;
    return zipfam_part_of(base, (size_t)(dot - base), base);
}

/* Split a path into the directory to scan and the stem its family
 * shares. Returns the part the given file itself is, or 0 if its name
 * is not of the family shape at all. */
static int zipfam_split(const char *path, char *dir, size_t dirsz,
                        const char **stem, size_t *stemlen)
{
    const char *slash = strrchr(path, '/');
    const char *base = slash ? slash + 1 : path;
    const char *dot = strrchr(base, '.');
    size_t n;

    if (!dot || dot == base) return 0;
    *stem = base;
    *stemlen = (size_t)(dot - base);

    n = slash ? (size_t)(slash - path) : 0;
    if (n + 2 >= dirsz) return 0;
    if (!slash) { dir[0] = '.'; dir[1] = 0; }
    else if (n == 0) { dir[0] = '/'; dir[1] = 0; }
    else { memcpy(dir, path, n); dir[n] = 0; }

    return zipfam_part_of(*stem, *stemlen, base);
}

/* Walk the family's directory and record every member. `nparts` says
 * which slot the ".zip" member belongs in; pass 0 while that is still
 * unknown, which records every other member and leaves that one out.
 * `lastbuf` receives the ".zip" member's path either way, since it has
 * to be described before the count can be known at all. */
static void seg_scan_zip_family(SegHost *h, const char *anchor, int nparts,
                                char *lastbuf, size_t lastsz)
{
    char dir[1024], cand[1200];
    const char *stem;
    size_t stemlen;
    DIR *d;
    struct dirent *de;

    if (lastbuf && lastsz) lastbuf[0] = 0;
    if (!zipfam_split(anchor, dir, sizeof dir, &stem, &stemlen)) return;

    d = opendir(dir);
    if (!d) return;
    while ((de = readdir(d)) != NULL) {
        struct stat st;
        int part = zipfam_part_of(stem, stemlen, de->d_name);
        if (!part) continue;
        if ((size_t)snprintf(cand, sizeof cand, "%s/%s", dir, de->d_name)
            >= sizeof cand)
            continue;
        if (stat(cand, &st) != 0 || !S_ISREG(st.st_mode)) continue;
        if (part == ZIPFAM_LAST) {
            if (lastbuf && lastsz) snprintf(lastbuf, lastsz, "%s", cand);
            part = nparts;
            if (part < 1) continue;      /* count not established yet */
        }
        seg_record(h, part, cand);
    }
    closedir(d);
}

/* ------------------------------------------------------------------ */
/* Plain NAME.001 splits: the scheme IS the filename                    */
/*                                                                    */
/* (Source: reference/XADMaster/XADSplitFileParser.m. Its              */
/* +recognizeFileWithHandle: matches ^(.*)\.([0-9]{3})$ case-          */
/* insensitively and requires the sibling to exist — .001 looks for    */
/* .002, any other part looks for .001 — and its +volumesForHandle:    */
/* scans the directory for ^STEM\.[0-9]{3}$.)                          */
/*                                                                    */
/* Two departures, both because the reference concatenates whatever    */
/* the scan returns, sorted by name:                                   */
/*   - the run must be CONSECUTIVE from .001. A stray NAME.900 beside  */
/*     a valid 3-part set is appended by the reference silently        */
/*     (measured 2026-08-09: 10,200 -> 10,208 bytes).                  */
/*   - a numbered member sitting BEYOND the run means the gap is a     */
/*     missing part, and that is refused rather than joined. It is the */
/*     only shape in which such a set can report a missing part at     */
/*     all: nothing counts the parts, so a set missing its TAIL looks  */
/*     exactly like a complete one.                                    */
/* ------------------------------------------------------------------ */

/* The part number a NAME.NNN filename ends in, or 0 (which is also
 * what ".000" gives, and there is no part zero). */
static int split_ext_part(const char *name)
{
    size_t n = strlen(name);
    const char *e;

    if (n < 5) return 0;                       /* "x.001" is the shortest */
    e = name + n - 4;
    if (e[0] != '.') return 0;
    if (e[1] < '0' || e[1] > '9' || e[2] < '0' || e[2] > '9' ||
        e[3] < '0' || e[3] > '9') return 0;
    return (e[1] - '0') * 100 + (e[2] - '0') * 10 + (e[3] - '0');
}

/* Does `name` belong to the family sharing `stem`? Part number, or 0. */
static int splitfam_part_of(const char *stem, size_t stemlen, const char *name)
{
    size_t i;

    if (strlen(name) != stemlen + 4) return 0;
    for (i = 0; i < stemlen; i++)
        if (ascii_lower((unsigned char)name[i]) !=
            ascii_lower((unsigned char)stem[i]))
            return 0;
    return split_ext_part(name);
}

/* Split a path into the directory to scan and the stem its family
 * shares (its name without ".NNN"). Returns the part the given file
 * itself is, or 0 when the name is not of the family shape. */
static int splitfam_split(const char *path, char *dir, size_t dirsz,
                          const char **stem, size_t *stemlen)
{
    const char *slash = strrchr(path, '/');
    const char *base = slash ? slash + 1 : path;
    size_t n;
    int part = split_ext_part(base);

    if (part < 1) return 0;
    *stem = base;
    *stemlen = strlen(base) - 4;
    if (*stemlen == 0) return 0;               /* ".001" is all extension */

    n = slash ? (size_t)(slash - path) : 0;
    if (n + 2 >= dirsz) return 0;
    if (!slash) { dir[0] = '.'; dir[1] = 0; }
    else if (n == 0) { dir[0] = '/'; dir[1] = 0; }
    else { memcpy(dir, path, n); dir[n] = 0; }

    return part;
}

/* What makes this file a segment rather than a file whose name happens
 * to end in three digits: another member of its family is there.
 *
 * The reference asks for one SPECIFIC sibling (.001 looks for .002, and
 * everything else for .001), which means a set whose .002 is the
 * missing one is not recognized as a set at all and the user is told
 * the format is unknown — with the .003 sitting right beside it. Any
 * other member will do here, so that case reaches the part-numbering
 * checks below and is reported as the missing part it is. */
static int split_family_present(const char *path)
{
    char dir[1024];
    const char *stem;
    size_t stemlen;
    DIR *d;
    struct dirent *de;
    int self = splitfam_split(path, dir, sizeof dir, &stem, &stemlen);
    int found = 0;

    if (self < 1) return 0;
    d = opendir(dir);
    if (!d) return 0;
    while (!found && (de = readdir(d)) != NULL) {
        char cand[1200];
        struct stat st;
        int p = splitfam_part_of(stem, stemlen, de->d_name);
        if (p < 1 || p == self) continue;
        if ((size_t)snprintf(cand, sizeof cand, "%s/%s", dir, de->d_name)
            >= sizeof cand)
            continue;
        if (stat(cand, &st) == 0 && S_ISREG(st.st_mode)) found = 1;
    }
    closedir(d);
    return found;
}

/* Was another member of this family handed over with --part? That is
 * the second way a set proves it is one, and the only way when the
 * parts were collected from different directories. */
static int split_part_offered(const char *path, const char **args, int n)
{
    char dir[1024];
    const char *stem;
    size_t stemlen;
    int self = splitfam_split(path, dir, sizeof dir, &stem, &stemlen), i;

    if (self < 1) return 0;
    for (i = 0; i < n; i++) {
        const char *slash = strrchr(args[i], '/');
        int p = splitfam_part_of(stem, stemlen, slash ? slash + 1 : args[i]);
        if (p >= 1 && p != self) return 1;
    }
    return 0;
}

/* Record every member of the family in the anchor's directory.
 * Returns the highest part number SEEN, including numbers too large to
 * record, so the caller can tell a 300-part set from a 256-part one. */
static int seg_scan_split_family(SegHost *h, const char *anchor)
{
    char dir[1024], cand[1200];
    const char *stem;
    size_t stemlen;
    DIR *d;
    struct dirent *de;
    int highest = 0;

    if (splitfam_split(anchor, dir, sizeof dir, &stem, &stemlen) < 1)
        return 0;

    d = opendir(dir);
    if (!d) return 0;
    while ((de = readdir(d)) != NULL) {
        struct stat st;
        int part = splitfam_part_of(stem, stemlen, de->d_name);
        if (part < 1) continue;
        if ((size_t)snprintf(cand, sizeof cand, "%s/%s", dir, de->d_name)
            >= sizeof cand)
            continue;
        if (stat(cand, &st) != 0 || !S_ISREG(st.st_mode)) continue;
        if (part > highest) highest = part;
        seg_record(h, part, cand);
    }
    closedir(d);
    return highest;
}

/* Length of the consecutive run .001 .. .N that was found. *beyond is
 * set when a member sits past the end of it, which says the gap is a
 * missing part and not the end of the set. */
static int split_run_length(const SegHost *h, int *beyond)
{
    int run = 0, p;

    while (run < UNC_SEG_MAX_PARTS && h->path[run + 1]) run++;
    *beyond = 0;
    for (p = run + 2; p <= UNC_SEG_MAX_PARTS; p++)
        if (h->path[p]) { *beyond = 1; break; }
    return run;
}

/* Ask stdin for a path to part `part`, until one matches or the user
 * gives up (empty line or EOF). */
static int seg_ask(SegHost *h, int part)
{
    char line[1200];

    for (;;) {
        size_t n;
        int got;
        fprintf(stderr, "macextract: locate part %d of \"%s\" "
                        "(path, or empty to give up): ", part, h->desc.name);
        fflush(stderr);
        if (!fgets(line, sizeof line, stdin)) return 0;
        n = strlen(line);
        while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
        if (n == 0) return 0;

        /* A spanned zip part cannot prove which part it is, so the
         * offer is taken at face value and the engine's structural
         * check on the assembled set is what catches a wrong one. Said
         * out loud, because everywhere else in this program a part is
         * verified before it is used. A plain split is the same, minus
         * even that check: there, only the file it joins back into can
         * object. */
        if (h->desc.scheme == UNC_FORMAT_ZIPSEG ||
            h->desc.scheme == UNC_FORMAT_SPLIT) {
            struct stat st;
            if (stat(line, &st) == 0 && S_ISREG(st.st_mode)) {
                seg_record(h, part, line);
                return 1;
            }
            fprintf(stderr, "macextract: %s: cannot read that file\n", line);
            continue;
        }

        got = seg_part_of(h, line);
        /* The user has named one file, so looking inside an envelope
         * costs a hundred decoded bytes and asks nobody anything. */
        if (!got) got = seg_wrapped_part_of(h, line);
        if (got == part) { seg_record(h, part, line); return 1; }
        if (got)
            fprintf(stderr, "macextract: that is part %d of the same set; "
                            "part %d is what is needed\n", got, part);
        else
            fprintf(stderr, "macextract: that file is not part of \"%s\"\n",
                    h->desc.name);
    }
}

static int seg_need(void *ctx, const UncSegmentDesc *desc, int part, UncIO *io)
{
    SegHost *h = (SegHost *)ctx;
    struct stat st;
    FILE *f;

    (void)desc;
    if (part < 1 || part > UNC_SEG_MAX_PARTS) return UNC_ERR_SEGMENTED;
    if (!h->path[part] && h->ask && !seg_ask(h, part)) return UNC_ERR_SEGMENTED;
    if (!h->path[part]) return UNC_ERR_SEGMENTED;

    f = fopen(h->path[part], "rb");
    if (!f) return UNC_ERR_SEGMENTED;
    h->open_io.f = f;
    h->open_io.size = stat(h->path[part], &st) == 0 ? (uint32_t)st.st_size
                                                    : UNC_SIZE_UNKNOWN;
    io->ctx = &h->open_io;
    io->read = fio_read;
    io->seek = fio_seek;
    io->tell = fio_tell;
    io->size = fio_size;
    return UNC_OK;
}

static void seg_release(void *ctx, UncIO *io)
{
    SegHost *h = (SegHost *)ctx;
    (void)io;
    if (h->open_io.f) { fclose(h->open_io.f); h->open_io.f = NULL; }
}

/* A part's length without opening it. On a filesystem that is a stat,
 * so the engine can put a denominator on the progress callback for
 * free; a host reading floppies would leave this NULL rather than send
 * the user hunting for disks to answer a cosmetic question. */
static uint32_t seg_size_of(void *ctx, const UncSegmentDesc *desc, int part)
{
    SegHost *h = (SegHost *)ctx;
    struct stat st;

    (void)desc;
    if (part < 1 || part > UNC_SEG_MAX_PARTS || !h->path[part])
        return UNC_SIZE_UNKNOWN;
    if (stat(h->path[part], &st) != 0) return UNC_SIZE_UNKNOWN;
    return (uint32_t)st.st_size;
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

/* Does a layer of this format hold ANOTHER archive, rather than the
 * entries the user came for? An envelope does by definition; so do the
 * three segmented schemes that join their parts into one file first.
 * Both the auto-unwrap below and --only's exemption from these layers
 * ask this question, and they must not answer it differently. */
static int layer_unwraps(UncFormat f)
{
    return unc_format_is_envelope(f) || f == UNC_FORMAT_SITSEG ||
           f == UNC_FORMAT_SPLIT || f == UNC_FORMAT_DDSEG;
}

static void usage(void)
{
    fprintf(stderr,
        "usage: macextract <l|x|t|sniff> [options] <file>\n"
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
        "  --only <name>  act on this entry only; repeatable. The name is\n"
        "                 the one `l` prints, and naming a folder takes\n"
        "                 what is in it. Applies to l, x and t alike; a\n"
        "                 name that matches nothing is an error. Envelope\n"
        "                 layers (.hqx, .bin, .gz ...) are always unwrapped\n"
        "                 whole, so --only names entries of the archive\n"
        "                 inside them\n"
        "  -nr            do not auto-unwrap envelope layers (.sit.hqx, ...)\n"
        "  --part <file>  another part of a segmented archive (repeatable);\n"
        "                 parts are also looked for beside the one given.\n"
        "                 A StuffIt part is placed by its header, a spanned\n"
        "                 zip part by its .zNN / .zip extension, a plain\n"
        "                 split by its .NNN one. A StuffIt part still inside\n"
        "                 an envelope (Archive.sit.1.hqx) is unwrapped first\n"
        "  --no-parts     do not look for other parts\n"
        "  --ask          prompt on stdin for parts that were not found\n"
        "  --preset <f>   SpaceSaver's preset dictionary: the 'PrAm' -4048\n"
        "                 resource out of your own copy of SpaceSaver, which\n"
        "                 its LZSS window starts loaded with (FORMATS.md)\n"
        "  -p <pw>        password for encrypted entries; \"-\" reads one\n"
        "                 line from stdin. With --ask and no -p, each\n"
        "                 archive that needs one is asked for, and asked\n"
        "                 again when the password is refused\n"
        "  --no-comment   do not save the archive's own comment. By\n"
        "                 default a Compact Pro or zip archive's comment\n"
        "                 is written beside the extracted items as\n"
        "                 <archive>.comment.txt, and printed by l and t\n"
        "  --stats        print allocator statistics\n"
        "  -f <format>    force format\n"
        "  -v             verbose\n"
        "  --version      print the version and exit\n");
}

int main(int argc, char **argv)
{
    const char *cmd, *file = NULL, *outdir = ".", *force = NULL;
    int raw_names = 0, verbose = 0, stats = 0, hidden_forks = 0, overwrite = 0;
    int no_comment = 0;
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
    static uint8_t *longname;      /* freed at exit by the OS: one buffer
                                    * for every layer of an envelope */
    UncFormat fmt;
    int ret;
    int no_recurse = 0, depth = 0;
    const char *origfile;       /* the file named on the command line */
    char curfile[PATHBUF], delfile[PATHBUF];
    struct stat st;
    SegHost seg;
    const char *partargs[UNC_SEG_MAX_PARTS];
    const char *presetfile = NULL, *password = NULL;
    static char pwbuf[UNC_PASSWORD_MAX + 2];
    static uint8_t mkeybuf[8];
    UncPasswordSource pwsrc;
    /* SpaceSaver's preset dictionary is 9,679 bytes; this is the ceiling
     * on what --preset will read, not a size anybody declared. */
    static uint8_t presetbuf[64 * 1024];
    int nparts = 0, no_parts = 0, ask = 0;
    /* --only. The flags outlive one layer on purpose: the selectors are
     * judged once, at the end of the run. */
    const char *only[ONLY_MAX];
    unsigned char only_hit[ONLY_MAX];
    int nonly = 0, onlymiss = 0;

    memset(only_hit, 0, sizeof only_hit);

    if (argc >= 2 && (strcmp(argv[1], "--version") == 0 ||
                      strcmp(argv[1], "-V") == 0)) {
        printf("macextract %s\n", UNC_VERSION);
        return 0;
    }
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
        else if (strcmp(argv[i], "--part") == 0 && i + 1 < argc) {
            if (nparts < UNC_SEG_MAX_PARTS) partargs[nparts++] = argv[++i];
            else { fprintf(stderr, "macextract: too many --part\n"); return 2; }
        }
        else if (strcmp(argv[i], "--only") == 0 && i + 1 < argc) {
            if (nonly < ONLY_MAX) only[nonly++] = argv[++i];
            else { fprintf(stderr, "macextract: too many --only\n"); return 2; }
        }
        else if (strcmp(argv[i], "--no-parts") == 0) no_parts = 1;
        else if (strcmp(argv[i], "--ask") == 0) ask = 1;
        else if (strcmp(argv[i], "--preset") == 0 && i + 1 < argc)
            presetfile = argv[++i];
        else if (strcmp(argv[i], "-p") == 0 && i + 1 < argc) password = argv[++i];
        else if (strcmp(argv[i], "--no-comment") == 0) no_comment = 1;
        else if (strcmp(argv[i], "--stats") == 0) stats = 1;
        else if (strcmp(argv[i], "-f") == 0 && i + 1 < argc) force = argv[++i];
        else if (strcmp(argv[i], "-v") == 0) verbose = 1;
        else if (argv[i][0] == '-') { usage(); return 2; }
        else file = argv[i];
    }
    if (!file) { usage(); return 2; }
    origfile = file;
    snprintf(curfile, sizeof curfile, "%s", file);
    delfile[0] = 0;

nextlayer:
    file = curfile;
    memset(&fio, 0, sizeof fio);
    fio.f = fopen(file, "rb");
    if (!fio.f) {
        fprintf(stderr, "macextract: %s: %s\n", file, strerror(errno));
        return 1;
    }
    if (stat(file, &st) == 0) fio.size = file_size32(&st, file);
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
    /* What this filesystem takes, asked rather than assumed: ext4 gives
     * 255 and 4096, but eCryptfs gives 143 and a FAT volume less
     * again. The fallbacks are POSIX's minimums where pathconf will not
     * say (it returns -1 with errno unset for "no limit"). */
    sink.fs_name_max = pathconf(outdir, _PC_NAME_MAX);
    if (sink.fs_name_max <= 0 || sink.fs_name_max > 255) sink.fs_name_max = 255;
    sink.fs_path_max = pathconf(outdir, _PC_PATH_MAX);
    if (sink.fs_path_max <= 0 || sink.fs_path_max > PATHBUF - 8)
        sink.fs_path_max = PATHBUF - 8;
    sink.archive = file;
    sink.no_comment = no_comment;
    sink.raw_names = raw_names;
    sink.hidden_forks = hidden_forks;
    sink.overwrite = overwrite;
    sink.unwrap_src = delfile;   /* "" until a layer is being unwrapped */
    sink.verbose = verbose;

    sk.ctx = &sink;
    sk.begin_entry = sink_begin;
    sk.write = sink_write;
    sk.end_entry = sink_end;
    sk.comment = sink_comment;

    prog.ctx = NULL;
    prog.tick = prog_tick;

    memset(&opt, 0, sizeof opt);
    /* Somewhere for a name the engine cannot carry. It is only ever
     * shown, never written, so the size is the largest a format can
     * state rather than anything the filesystem has to say about it.
     * A run without it loses the text and keeps the length. */
    if (!longname) longname = (uint8_t *)malloc(UNC_LONGNAME_CAP);
    opt.long_name = longname;
    opt.long_name_cap = longname ? UNC_LONGNAME_CAP : 0;
    sink.long_name = longname;

    /* A password given on the command line, or read from stdin once so
     * that it does not sit in the process table. */
    if (password) {
        if (strcmp(password, "-") == 0) {
            size_t n;
            if (!fgets(pwbuf, (int)sizeof pwbuf, stdin)) pwbuf[0] = 0;
            n = strlen(pwbuf);
            while (n > 0 && (pwbuf[n - 1] == '\n' || pwbuf[n - 1] == '\r'))
                pwbuf[--n] = 0;
            opt.password = (const uint8_t *)pwbuf;
            opt.password_len = (uint16_t)n;
        } else {
            size_t n = strlen(password);
            if (n > UNC_PASSWORD_MAX) {
                /* Truncating it silently would report "wrong password"
                 * for a password the user typed correctly. */
                fprintf(stderr, "macextract: password is longer than %d bytes, "
                                "which no format here uses\n", UNC_PASSWORD_MAX);
                return 1;
            }
            opt.password = (const uint8_t *)password;
            opt.password_len = (uint16_t)n;
        }
    } else if (ask) {
        pwsrc.ctx = NULL;
        pwsrc.ask = cli_ask_password;
        opt.ask = &pwsrc;
    }

    /* The archive's own resource fork, if this machine has it beside
     * the data fork: the one piece of key material a .sit does not
     * carry in its stream. */
    if (load_mkey(file, hidden_forks, mkeybuf)) opt.mkey = mkeybuf;
    else opt.mkey = NULL;

    if (force) {
        fmt = format_by_name(force);
        if (fmt == UNC_FORMAT_UNKNOWN) {
            fprintf(stderr, "macextract: unknown format '%s'\n", force);
            return 2;
        }
    } else {
        fmt = unc_sniff(&io);

        /* A plain split is decided by NAME, and deliberately BEFORE the
         * sniff has a say: part 1 of a split .sit begins with "SIT!" and
         * sniffs as the archive it is a slice of. The reference tries
         * its content parsers first and so cannot read that shape at all
         * — measured 2026-08-09, `unar derived-Fractional_Widths.sit.001`
         * exits 1 having written one truncated fork. --no-parts puts the
         * sniff back in charge. */
        /* Unless the file proves otherwise. A DiskDoubler `SPLT` part
         * carries its own index, count and identity, so a set named
         * Archive.dd.001 is joined as the scheme it declares — the name
         * rule above exists for parts that declare nothing, and folding
         * 94-byte headers into a file would be silent and wrong. */
        if (!no_parts && fmt != UNC_FORMAT_DDSEG &&
            (split_family_present(file) ||
             split_part_offered(file, partargs, nparts)))
            fmt = UNC_FORMAT_SPLIT;
    }

    /* --only names the entries the user can SEE. A layer this run is
     * about to unwrap is not one of them: it holds one file on the way
     * to the archive, and filtering it would extract nothing at all.
     * The condition is the unwrap gate below, not the format — `l` and
     * `t` never unwrap, so for them an envelope's single entry IS the
     * listing, and exempting it made --only silently do nothing.
     * A layer that filters is a layer that does not recurse, which is
     * what makes the report at the end fire exactly once. */
    if (nonly && !(strcmp(cmd, "x") == 0 && !no_recurse && layer_unwraps(fmt))) {
        sink.only     = only;
        sink.only_hit = only_hit;
        sink.nonly    = nonly;
    }

    /* Mac formats carry MacRoman names; zip/tar/gzip do not — nor does
     * a split, whose entry is named after the host's own file. */
    switch (fmt) {
    case UNC_FORMAT_ZIP: case UNC_FORMAT_ZIPSEG: case UNC_FORMAT_TAR:
    case UNC_FORMAT_GZIP: case UNC_FORMAT_COMPRESS_Z: case UNC_FORMAT_SPLIT:
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
        fprintf(stderr, "macextract: %s: format not recognized\n", file);
        fclose(fio.f);
        return 1;
    }
    if (!unc_format_extractable(fmt)) {
        fprintf(stderr, "macextract: %s: recognized as %s, which v1 cannot extract\n",
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
        /* SpaceSaver compresses a file in place and adds no extension,
         * so the whole basename is the name — stripping one here would
         * eat a real ".txt". */
        if (fmt == UNC_FORMAT_SPACESAVER) dot = NULL;
        opt.name_hint = (const uint8_t *)base;
        opt.name_hint_len = (uint16_t)(dot && dot != base ? (size_t)(dot - base)
                                                          : strlen(base));
    }

    /* SpaceSaver's window starts loaded with a dictionary that ships
     * inside SpaceSaver itself; without it, entries fail rather than
     * decode to something wrong. Read once, freed at exit. */
    if (presetfile && !opt.preset) {
        FILE *pf = fopen(presetfile, "rb");
        long n;
        if (!pf) {
            fprintf(stderr, "macextract: %s: %s\n", presetfile, strerror(errno));
            fclose(fio.f);
            return 1;
        }
        if (fseek(pf, 0, SEEK_END) != 0 || (n = ftell(pf)) < 0 ||
            fseek(pf, 0, SEEK_SET) != 0) n = -1;
        /* Static rather than malloc: `main` returns from a dozen places
         * and the engine holds this pointer for the whole run, so a
         * heap buffer would need freeing on every one of them — which
         * is how the sanitizer build first met this option. */
        if (n > 0 && n <= (long)sizeof presetbuf &&
            fread(presetbuf, 1, (size_t)n, pf) == (size_t)n) {
            opt.preset = presetbuf;
            opt.preset_len = (uint32_t)n;
        } else {
            n = -1;
        }
        fclose(pf);
        if (n <= 0) {
            fprintf(stderr, "macextract: %s: not a usable preset\n", presetfile);
            fclose(fio.f);
            return 1;
        }
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

    if ((fmt == UNC_FORMAT_SITSEG || fmt == UNC_FORMAT_ZIPSEG ||
         fmt == UNC_FORMAT_SPLIT || fmt == UNC_FORMAT_CPTSEG ||
         fmt == UNC_FORMAT_DDSEG) && !no_parts) {
        UncVolumeSource vs;
        void *scratch;

        memset(&seg, 0, sizeof seg);
        seg.ask = ask;
        seg.verbose = verbose;
        seg.outdir = outdir;

        if (fmt == UNC_FORMAT_SPLIT) {
            /* Nothing in these files says anything, so the descriptor is
             * built here: the set is the consecutive run of NAME.NNN in
             * one directory, and the joined file is called NAME. */
            const char *stem;
            size_t stemlen;
            char dirbuf[PATHBUF];
            int self, highest, beyond = 0, run;

            self = splitfam_split(file, dirbuf, sizeof dirbuf, &stem, &stemlen);
            if (self < 1) {
                fprintf(stderr, "macextract: %s: not a NAME.NNN part\n", file);
                fclose(fio.f);
                return 1;
            }
            seg.desc.scheme   = UNC_FORMAT_SPLIT;
            seg.desc.part     = (uint16_t)self;
            seg.desc.head_len = 0;
            seg.desc.total    = UNC_SIZE_UNKNOWN;   /* the engine sums it */
            if (stemlen > UNC_NAME_MAX) stemlen = UNC_NAME_MAX;
            memcpy(seg.desc.name, stem, stemlen);
            seg.desc.name[stemlen] = 0;
            seg.desc.name_len = (uint16_t)stemlen;

            highest = seg_scan_split_family(&seg, file);
            for (i = 0; i < nparts; i++) {
                const char *slash = strrchr(partargs[i], '/');
                int p = split_ext_part(slash ? slash + 1 : partargs[i]);
                if (p >= 1) {
                    if (p > highest) highest = p;
                    seg_record(&seg, p, partargs[i]);
                } else {
                    fprintf(stderr, "macextract: %s: no .NNN extension to "
                            "place it by, ignored\n", partargs[i]);
                }
            }

            run = split_run_length(&seg, &beyond);
            if (highest > UNC_SEG_MAX_PARTS) {
                /* Says what was SEEN, not what it means: three digits
                 * reach 999 and a member numbered past our ceiling is
                 * either a set too big to read or a stray file, and
                 * nothing here can tell which. */
                fprintf(stderr, "macextract: \"%s\": a part numbered %d is "
                        "beside it, and this reads at most %d parts\n",
                        seg.desc.name, highest, UNC_SEG_MAX_PARTS);
                fclose(fio.f);
                return 1;
            }
            if (run < 1) {
                fprintf(stderr, "macextract: %s: part 1 of \"%s\" is not "
                        "beside it\n", file, seg.desc.name);
                fclose(fio.f);
                return 1;
            }
            /* Something numbered past the end of the run says a part in
             * between is missing. Refused, unless --ask means the user
             * is standing by to produce it. */
            if (beyond && !ask) {
                fprintf(stderr, "macextract: part %d of \"%s\" is missing "
                        "(a later part is there)\n", run + 1, seg.desc.name);
                fclose(fio.f);
                return 1;
            }
            if (beyond) run = highest;

            /* Gaps are resolved HERE rather than one disk at a time,
             * which is what the volume source does for the other two
             * schemes. A split states its length nowhere, so the joined
             * size is the sum of the parts' — and that has to be known
             * before the first byte is written, since it is the size
             * the one emitted entry announces. */
            for (i = 1; i <= run; i++) {
                if (seg.path[i]) continue;
                if (!ask || !seg_ask(&seg, i)) {
                    fprintf(stderr, "macextract: part %d of \"%s\" is "
                            "missing\n", i, seg.desc.name);
                    fclose(fio.f);
                    return 1;
                }
            }
            seg.desc.nparts = (uint16_t)run;
            if (verbose)
                fprintf(stderr, "%s: %d parts\n", seg.desc.name, run);
        } else if (fmt == UNC_FORMAT_CPTSEG) {
            /* Every segment carries the set's identity, so discovery is
             * by CONTENT exactly as it is for StuffIt — a set whose
             * parts are scattered and named unlike each other works, and
             * the author's manual says as much ("the names of the files
             * are not important"). What is special is that only the
             * FINAL segment says how many there are, by being the one
             * that carries the index. So: identify the set from whatever
             * part we were given, collect the rest, then take the count
             * from the final one. */
            int i2, fin = 0;
            char dirbuf[PATHBUF];
            const char *base;

            if (unc_segment_describe(&io, &seg.desc) != UNC_OK) {
                fprintf(stderr, "macextract: %s: not a readable segment "
                        "header\n", file);
                fclose(fio.f);
                return 1;
            }
            seg_record(&seg, (int)seg.desc.part, file);
            for (i = 0; i < nparts; i++) {
                int p = seg_part_of(&seg, partargs[i]);
                if (p) seg_record(&seg, p, partargs[i]);
                else fprintf(stderr, "macextract: %s: not a segment of this "
                             "set, ignored\n", partargs[i]);
            }
            seg_scan_dir(&seg, file, 0);

            /* Which of them is the last? The one whose header names an
             * index. Asking each is an 8-byte read, and it is the only
             * way round: nothing else in the set states the count. */
            if (seg.desc.nparts == 0) {
                for (i2 = 1; i2 <= UNC_SEG_MAX_PARTS && !fin; i2++) {
                    UncSegmentDesc cand;
                    FILE *cf;
                    FileIO cio_f;
                    UncIO cio;
                    struct stat cst;
                    if (!seg.path[i2]) continue;
                    cf = fopen(seg.path[i2], "rb");
                    if (!cf) continue;
                    memset(&cio_f, 0, sizeof cio_f);
                    cio_f.f = cf;
                    cio_f.size = stat(seg.path[i2], &cst) == 0
                                 ? (uint32_t)cst.st_size : UNC_SIZE_UNKNOWN;
                    cio.ctx = &cio_f;
                    cio.read = fio_read;
                    cio.seek = fio_seek;
                    cio.tell = fio_tell;
                    cio.size = fio_size;
                    if (unc_segment_describe(&cio, &cand) == UNC_OK &&
                        cand.nparts)
                        { seg.desc = cand; fin = i2; }
                    fclose(cf);
                }
                if (!fin) {
                    fprintf(stderr, "macextract: %s: this is one segment of a "
                            "Compact Pro set; the last segment, the one "
                            "holding the index, is not beside it\n", file);
                    fclose(fio.f);
                    return 1;
                }
            }

            /* Now that the count is known, every part is re-checked
             * against the full rule: a middle segment must not carry an
             * index and the last one must, which is more than the
             * identity alone could ask (fmt_cptseg.c). */
            for (i2 = 1; i2 <= UNC_SEG_MAX_PARTS; i2++) {
                if (!seg.path[i2]) continue;
                if (seg_part_of(&seg, seg.path[i2]) == i2) continue;
                if (verbose)
                    fprintf(stderr, "part %d: %s no longer matches the set, "
                            "dropped\n", i2, seg.path[i2]);
                free(seg.path[i2]);
                seg.path[i2] = NULL;
            }

            /* The format stores no name for the original archive, so
             * the prompt borrows the opened file's, for display only. */
            base = strrchr(file, '/');
            base = base ? base + 1 : file;
            snprintf(dirbuf, sizeof dirbuf, "%s", base);
            {
                size_t n = strlen(dirbuf);
                if (n > UNC_NAME_MAX) n = UNC_NAME_MAX;
                memcpy(seg.desc.name, dirbuf, n);
                seg.desc.name[n] = 0;
                seg.desc.name_len = (uint16_t)n;
            }
        } else if (fmt == UNC_FORMAT_ZIPSEG) {
            /* Only the LAST part carries the part count, so it has to be
             * found before anything else can be — and for this scheme
             * "found" means "named .zip in the same folder". */
            char lastpath[1200];
            const char *stem;
            size_t stemlen;
            char dirbuf[PATHBUF];
            FILE *lf;
            FileIO lio_f;
            UncIO lio;
            struct stat lst;
            int derr;

            seg_scan_zip_family(&seg, file, 0, lastpath, sizeof lastpath);
            if (!lastpath[0]) {
                fprintf(stderr, "macextract: %s: this is one part of a spanned "
                        "zip; the last part (named .zip) is not beside it\n",
                        file);
                fclose(fio.f);
                return 1;
            }
            lf = fopen(lastpath, "rb");
            if (!lf) {
                fprintf(stderr, "macextract: %s: %s\n", lastpath,
                        strerror(errno));
                fclose(fio.f);
                return 1;
            }
            memset(&lio_f, 0, sizeof lio_f);
            lio_f.f = lf;
            lio_f.size = stat(lastpath, &lst) == 0 ? (uint32_t)lst.st_size
                                                   : UNC_SIZE_UNKNOWN;
            lio.ctx = &lio_f;
            lio.read = fio_read;
            lio.seek = fio_seek;
            lio.tell = fio_tell;
            lio.size = fio_size;
            derr = unc_segment_describe(&lio, &seg.desc);
            fclose(lf);
            if (derr != UNC_OK) {
                fprintf(stderr, "macextract: %s: %s\n", lastpath,
                        unc_strerror(derr));
                fclose(fio.f);
                return 1;
            }
            seg_record(&seg, (int)seg.desc.nparts, lastpath);

            /* The engine has no filename to put in a prompt, because the
             * format stores none. Borrow the family's stem for display. */
            if (zipfam_split(file, dirbuf, sizeof dirbuf, &stem, &stemlen)) {
                if (stemlen > UNC_NAME_MAX) stemlen = UNC_NAME_MAX;
                memcpy(seg.desc.name, stem, stemlen);
                seg.desc.name[stemlen] = 0;
                seg.desc.name_len = (uint16_t)stemlen;
            }

            for (i = 0; i < nparts; i++) {
                int p = zip_ext_part(partargs[i]);
                if (p == ZIPFAM_LAST) p = (int)seg.desc.nparts;
                if (p) seg_record(&seg, p, partargs[i]);
                else fprintf(stderr, "macextract: %s: no .zNN or .zip "
                             "extension to place it by, ignored\n",
                             partargs[i]);
            }
        } else {
            if (unc_segment_describe(&io, &seg.desc) != UNC_OK) {
                fprintf(stderr, "macextract: %s: not a readable segment header\n",
                        file);
                fclose(fio.f);
                return 1;
            }

            /* A `SPLT` part carries everything about the set except a
             * name for the file it joins into: DiskDoubler's Split does
             * not store one. The part's own filename is all there is,
             * minus the ".N" that numbers it — and because the parts
             * are matched by CONTENT, that name is for display and for
             * the output file, never evidence. */
            if (fmt == UNC_FORMAT_DDSEG) {
                const char *base = strrchr(file, '/');
                const char *dot;
                size_t n;
                base = base ? base + 1 : file;
                n = strlen(base);
                dot = strrchr(base, '.');
                if (dot && dot != base) {
                    const char *d;
                    for (d = dot + 1; *d; d++)
                        if (*d < '0' || *d > '9') break;
                    if (*d == 0 && d != dot + 1) n = (size_t)(dot - base);
                }
                if (n > UNC_NAME_MAX) n = UNC_NAME_MAX;
                memcpy(seg.desc.name, base, n);
                seg.desc.name[n] = 0;
                seg.desc.name_len = (uint16_t)n;
            }

            /* The file we were handed is a part, and its own part number
             * comes from its header — so opening part 3 of a set works. */
            seg_record(&seg, (int)seg.desc.part, file);
            for (i = 0; i < nparts; i++) {
                /* A part named by the user is worth unwrapping whether
                 * or not anything else here is wrapped: it is one file,
                 * and the user has said what it is. */
                int p = seg_part_of(&seg, partargs[i]);
                if (p) seg_record(&seg, p, partargs[i]);
                else if (!seg_wrapped_part_of(&seg, partargs[i]))
                    fprintf(stderr, "macextract: %s: not part of \"%s\", "
                            "ignored\n", partargs[i], seg.desc.name);
            }
            seg_scan_dir(&seg, file, 0);
            /* A part that arrived wrapped was unwrapped into the OUTPUT
             * directory, so the rest of the set is not there: it is
             * still where the user left it. */
            if (depth > 0)
                seg_scan_dir(&seg, origfile, 0);

            /* Only now, and only if something is still missing, is it
             * worth taking envelopes off to look — which is how a real
             * download arrives (Archive.sit.1.hqx) and also how a
             * half-unstuffed one does. Rationing it this way means a
             * set that is complete never opens a single file beside it,
             * and one that is short pays a hundred decoded bytes per
             * envelope rather than failing. */
            if (!seg_have_all(&seg)) {
                if (depth > 0)
                    seg_scan_dir(&seg, origfile, 1);
                seg_scan_dir(&seg, file, 1);
            }
        }

        memset(&vs, 0, sizeof vs);   /* optional members are NULL ones */
        vs.ctx = &seg;
        vs.need = seg_need;
        vs.release = seg_release;
        vs.size = seg_size_of;

        scratch = malloc(unc_segment_scratch_size());
        if (!scratch) {
            fprintf(stderr, "macextract: out of memory\n");
            fclose(fio.f);
            return 1;
        }
        ret = unc_extract_segments(&seg.desc, &vs, scratch, &sk, &al,
                                   &prog, &opt);
        if (stats) {
            uint32_t sw = 0, back = 0;
            unc_segment_stats(scratch, &sw, &back);
            fprintf(stderr, "segments: %u part opens, %u of them backward\n",
                    sw, back);
        }
        free(scratch);
        seg_peel_clean(&seg);
        for (i = 1; i <= UNC_SEG_MAX_PARTS; i++) free(seg.path[i]);
    } else {
        ret = unc_extract_as(fmt, &io, &sk, &al, &prog, &opt);
    }
    fclose(fio.f);

    if (stats)
        fprintf(stderr, "alloc: high-water %u bytes, %u refused\n",
                ba.high_water, ba.failed);

    if (ret != UNC_OK) {
        fprintf(stderr, "macextract: %s: %s\n", file, unc_strerror(ret));
        return 1;
    }
    if (sink.unsupported) {
        /* The one failure a user can do something about that is not
         * about their machine: this build cannot read that method YET,
         * and the file itself is what would fix that. Every method this
         * engine has ever added past the first came from somebody's
         * file — so ask for it, once, with the method named. */
        fprintf(stderr,
                "macextract: %d entr%s use%s a compression method this build "
                "cannot read yet.\n",
                sink.unsupported, sink.unsupported == 1 ? "y" : "ies",
                sink.unsupported == 1 ? "s" : "");
        if (sink.unsup_method)
            fprintf(stderr, "macextract: the first is %s method %d.\n",
                    unc_format_name(fmt), sink.unsup_method);
        /* No URL, on purpose: a link names a host, an account and a
         * project, and all three outlive their spelling badly. Somebody
         * who has this program can find where it came from. */
        fprintf(stderr,
                "macextract: if you can share this file, please open an "
                "issue — a specimen\n"
                "macextract: is exactly what is needed to add support.\n");
    }
    sink_report_cuts(&sink);
    /* A selector that matched nothing is a typo, and a typo must not
     * extract nothing and exit 0. */
    if (sink.nonly) {
        for (i = 0; i < nonly; i++)
            if (!only_hit[i]) {
                fprintf(stderr, "macextract: --only \"%s\": no entry of this "
                        "archive has that name\n", only[i]);
                onlymiss++;
            }
    }
    if (sink.errors) {
        fprintf(stderr, "macextract: %d of %d entries failed\n",
                sink.errors, sink.entries);
        /* Say by how much, once, on its own line: the per-entry lines are
         * what the harnesses read, so the number goes here rather than
         * into them. Only when a budget was actually set — without one
         * there is nothing to be short OF. */
        if (ba.shortby)
            fprintf(stderr, "macextract: %u bytes more memory would have "
                            "been needed\n", (unsigned)ba.shortby);
        return 1;
    }
    if (onlymiss) return 1;

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
        layer_unwraps(fmt) &&
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
