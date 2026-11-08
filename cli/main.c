/*
 * macextract CLI — Linux frontend for libmacextract.
 *
 * Commands:
 *   macextract l <file>            list entries
 *   macextract x <file>            extract
 *   macextract t <file>            test (decode + CRC check, no output)
 * Options:
 *   -o <dir>       output directory (default .)
 *   --budget <N>   allocation cap in bytes, K/M/G allowed (simulate a small Mac)
 *   --raw-names    emit raw MacRoman bytes instead of UTF-8 names
 *   --forks <visible|hidden>  resource-fork sidecar naming
 *   --overwrite    write over existing output files (default: refuse)
 *   --only <name>  restrict the command to these entries (repeatable)
 *   --no-comment   do not save the archive's own comment
 *   --preset <f>   SpaceSaver's preset dictionary ('PrAm' -4048)
 *   -f <format>    force format (the name `sniff` prints)
 *
 * UNC_TRACE_ALLOC=1 in the environment prints every allocation and every
 * budget refusal with the live total, which is how a tier's peak is read
 * apart into its pieces (TESTING.md, *The tiers a budget predicts*).
 * UNC_SHORT_READ=<n> caps every read at n bytes (TESTING.md, *Short
 * reads*).
 *
 * The CLI is the only place libc I/O and malloc are used; the engine
 * sees callbacks only.
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */
/* lstat, fdopen, O_NOFOLLOW and mkdtemp are POSIX.1-2008, which
 * -std=c99 -pedantic does not expose by itself. */
#define _POSIX_C_SOURCE 200809L

#include "macextract.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

/* ------------------------------------------------------------------ */
/* File-backed UncIO                                                  */
/* ------------------------------------------------------------------ */

typedef struct {
    FILE      *f;
    unc_off_t  size;
} FileIO;

/* `UncIO` addresses a file with unc_off_t, which is 32 bits unless the
 * build defines UNC_OFF64. Narrowing st_size to it WRAPS a larger file
 * into a plausible small one — a 4.5 GB zip looked like 237 MB of
 * nonsense and was reported as "not a recognized archive", a true
 * refusal with a false reason. Say what is actually wrong, and hand the
 * engine the largest size it can state rather than a wrapped one: a tar
 * still lists the members under the ceiling, which is worth more than a
 * clean refusal of the whole file. At 64 bits the branch cannot be
 * reached by any file a filesystem can hold. */
static unc_off_t file_size_off(const struct stat *st, const char *path)
{
    if ((uint64_t)st->st_size > (uint64_t)UNC_OFF_MAX) {
        fprintf(stderr, "macextract: %s: file is larger than 4 GB; this engine "
                        "addresses the first 4 GB of it\n", path);
        return UNC_OFF_MAX;
    }
    return (unc_off_t)st->st_size;
}

/* UNC_SHORT_READ=<n> caps every read at n bytes. `UncIO` allows a short
 * read before EOF, and a file-backed host never returns one, so without
 * this no suite exercises the engine's half of that contract
 * (TESTING.md, *Short reads*). Set once in main(). */
static int32_t fio_read_cap;

static int32_t fio_read(void *ctx, void *buf, int32_t len)
{
    FileIO *io = (FileIO *)ctx;
    size_t r;
    if (fio_read_cap > 0 && len > fio_read_cap) len = fio_read_cap;
    r = fread(buf, 1, (size_t)len, io->f);
    if (r == 0 && ferror(io->f)) return -1;
    return (int32_t)r;
}

static int fio_seek(void *ctx, unc_off_t pos)
{
    FileIO *io = (FileIO *)ctx;
    return fseek(io->f, (long)pos, SEEK_SET) == 0 ? 0 : -1;
}

static unc_off_t fio_tell(void *ctx)
{
    FileIO *io = (FileIO *)ctx;
    return (uint32_t)ftell(io->f);
}

static unc_off_t fio_size(void *ctx)
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
        if (getenv("UNC_TRACE_ALLOC"))
            fprintf(stderr, "REFUSED %10u  live %10u\n", size, ba->used);
        return NULL;
    }
    p = (uint8_t *)malloc(size + BA_HDR);
    if (!p) return NULL;
    memcpy(p, &size, sizeof size);
    ba->used += size;
    if (ba->used > ba->high_water) ba->high_water = ba->used;
    if (getenv("UNC_TRACE_ALLOC"))
        fprintf(stderr, "alloc %10u  live %10u\n", size, ba->used);
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

/* Is this entry's name MacRoman, and so ours to decode? A Mac format's
 * names are — except StuffIt 5's, which are the archive's own UTF-8 and
 * already the encoding this side writes (macextract.h, name_utf8). The
 * engine says which per ENTRY rather than per format, because the
 * format the CLI sniffed is not always the one that read the name: a
 * segmented set is sniffed as a split and walked by whatever the joined
 * stream turns out to be. */
#define NAME_IS_MACROMAN(s, i) ((s)->mac_encoding && !(i)->name_utf8)

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

/* Files by device and inode: no spelling, link or hard link of one is
 * ever opened for writing (sink_is_reading). Room for one layer's own
 * input and parts, and as many again carried from earlier layers. */
#define READ_MAX (2 * (UNC_SEG_MAX_PARTS + 1))
typedef struct {
    struct { dev_t dev; ino_t ino; } id[READ_MAX];
    int n;
} ReadList;

typedef struct {
    const char *outdir;
    int         list_only;
    int         test_only;
    int         raw_names;
    int         hidden_forks;   /* "._NAME" sidecars, not "NAME.rsrc" */
    int         overwrite;      /* write over existing output files    */
    int         clobber;        /* last open refused: path existed     */
    int         write_err;      /* this entry's write error was said   */
    int         said;           /* this entry's failure was explained,
                                 * so "NAME: output error" adds nothing */
    const char *unwrap_src;     /* envelope being unwrapped, or NULL   */
    const char *unwrap_rsrc;    /* ITS sidecar, only if the layer before
                                 * wrote one; "" or NULL otherwise      */
    int         deferred[2];    /* a write landed beside unwrap_src [0]
                                 * or unwrap_rsrc [1], whichever PATH it
                                 * matched, and is renamed onto it once
                                 * that is deleted                     */
    /* Every file this layer READS — the layer itself and, for a
     * segmented set, each part located — and every file an earlier layer
     * read that this run did not write, the archive named on the command
     * line first (DECISIONS.md 2026-11-08, *the original on every layer*). */
    ReadList    reading;
    /* --only: the entries the user named, and one flag each recording
     * whether anything matched. NULL/0 means "every entry", which is
     * what every run did before 2026-08-28. */
    const char *const *only;
    unsigned char *only_hit;
    int         nonly;
    /* --only on a layer written whole because it may unwrap (st_only_now). An
     * entry the selectors do not name is written ASIDE, to a new file
     * beside its path, so nothing already there is replaced for it: moved
     * into place if the chain goes on through it (sink_aside_settle),
     * removed if this layer is the last (sink_late_final). The hits are
     * kept apart until then: an envelope's entry is not the user's.
     * DECISIONS.md 2026-11-08, *the file an excluded entry replaced*. */
    int         only_late;
    const char *const *late_sel;
    int         late_nsel;
    unsigned char late_hit[ONLY_MAX];
    int         cur_aside;          /* this entry is written aside      */
    char        aside[2][PATHBUF];  /* where its data [0] and resource
                                     * [1] fork went; "" if not opened  */
    struct LateFile { char *path[2], *at[2]; } *late;  /* final, aside */
    int         nlate, latecap;
    mode_t      file_mode;      /* 0666 less the umask, for the asides */
    int         mac_encoding;   /* names are MacRoman */
    int         verbose;
    int         show_finder;    /* --finder: the Finder metadata as hex
                                 * — type, creator, flags — in place of
                                 * the four-character columns. Off by
                                 * default: the hex is for a parser, not
                                 * a reader. The pretty columns cannot be
                                 * read back, which is why this exists: a
                                 * code holding a space ("PDF ") or a NUL
                                 * moves the name, and the suite then
                                 * compares nothing at all (TESTING.md,
                                 * *The Finder metadata, and the one
                                 * field no oracle settles*) */
    int         show_meta;      /* --meta: with l, one row per entry of
                                 * what the Finder keeps beyond type,
                                 * creator and flags (print_meta) */
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
    int         inexact;        /* entries an Optimizer left INEXACT   */
    int         unsupported;    /* entries whose METHOD this build lacks */
    int         unsup_method;   /* the first such method, for the message */
    /* For envelope auto-unwrap: shape of what was extracted. */
    int         file_count, dir_count;
    char        last_ok_path[PATHBUF];
    char        last_ok_at[PATHBUF];    /* where its bytes are: the path,
                                         * or its aside */
    char        last_ok_rsrc[PATHBUF];  /* its sidecar, if this run wrote
                                         * one; "" otherwise */
    uint32_t    last_ok_type;  /* its Mac type, 0 if none */
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

/* Create `path` for writing and never write through a link: an existing
 * path is an error, or with `overwrite` is unlinked first — a link is
 * replaced, not followed, and a hard link no longer shares what is
 * written. O_NOFOLLOW|O_EXCL is what makes a link planted there between
 * the check and the open fail rather than be followed. DECISIONS.md
 * 2026-11-07, *the links in the output folder*. */
static FILE *create_file(const char *path, int overwrite)
{
    struct stat st;
    FILE *f;
    int fd;
    if (lstat(path, &st) == 0) {
        if (!overwrite) { errno = EEXIST; return NULL; }
        if (S_ISDIR(st.st_mode)) { errno = EISDIR; return NULL; }
        if (unlink(path) != 0) return NULL;
    }
    fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0666);
    if (fd < 0) return NULL;
    f = fdopen(fd, "wb");
    if (!f) close(fd);
    return f;
}

/* Make the folders of s->cur_path below outdir: all of it when `whole`,
 * else all but the leaf. A FILE in a folder's place is not touched: the
 * folder is numbered past it, `X~1`, the first such name that is free or
 * already a folder, so every entry of that folder finds the same one.
 * That is a layer this run unwrapped (`Foo.hqx` holding `Foo` holding
 * `Foo/`), an archive extracted beside itself, or an archive holding
 * both `X` and `X/` (DECISIONS.md 2026-11-07, *the folder numbered past
 * a file*). A LINK there is never followed: it fails the entry, or with
 * --overwrite is replaced by a real folder, and a link where a numbered
 * name would go is passed over like a file (DECISIONS.md 2026-11-07, *the
 * links in the output folder*). Returns 0, or -1 when a folder could not
 * be made. */
static int sink_make_dirs(DiskSink *s, int whole)
{
    size_t base = strlen(s->outdir);
    size_t i;
    struct stat st;

    for (i = base + 1;; i++) {
        char c = s->cur_path[i];
        if (c != '/' && !(c == 0 && whole)) {
            if (c == 0) return 0;
            continue;
        }
        s->cur_path[i] = 0;
        if (lstat(s->cur_path, &st) == 0 && S_ISLNK(st.st_mode)) {
            if (!s->overwrite) {
                fprintf(stderr, "macextract: %s: is a symbolic link, which is "
                        "not followed (--overwrite replaces it)\n",
                        s->cur_path);
                s->cur_path[i] = c;
                return -1;
            }
            if (unlink(s->cur_path) != 0) { s->cur_path[i] = c; return -1; }
        }
        if (mkdir(s->cur_path, 0777) != 0 &&
            (lstat(s->cur_path, &st) != 0 || !S_ISDIR(st.st_mode))) {
            char rest[PATHBUF], was[PATHBUF];
            int n;
            if (lstat(s->cur_path, &st) != 0) { s->cur_path[i] = c; return -1; }
            snprintf(rest, sizeof rest, "%s", c ? s->cur_path + i + 1 : "");
            snprintf(was, sizeof was, "%s", s->cur_path + base + 1);
            for (n = 1; n <= 99; n++) {
                int k = snprintf(s->cur_path + i, PATHBUF - i, "~%d", n);
                if (k < 0 || (size_t)k >= PATHBUF - i) return -1;
                if (lstat(s->cur_path, &st) != 0) {
                    if (mkdir(s->cur_path, 0777) != 0) return -1;
                    fprintf(stderr, "macextract: %s: a file has this name; "
                                    "the folder is %s\n",
                            was, s->cur_path + base + 1);
                    break;
                }
                if (S_ISDIR(st.st_mode)) break;
                s->cur_path[i] = 0;
            }
            if (n > 99) { s->cur_path[i] = c; return -1; }
            i = strlen(s->cur_path);
            if (c && (size_t)snprintf(s->cur_path + i, PATHBUF - i, "/%s",
                                      rest) >= PATHBUF - i)
                return -1;
        }
        s->cur_path[i] = c;
        if (c == 0) return 0;
    }
}

static char *seg_dup(const char *s);

/* Both are defined below, next to the conventions they implement. */
static int rsrc_path(const char *path, int hidden, char *out, size_t outsz);
static int sink_unwrap_exempt(DiskSink *s, const char *path);

/* Is this path (or its resource-fork sidecar) already on disk? The
 * envelope being unwrapped does not count — it is deleted moments
 * later and an inner entry may legitimately carry its name. */
static int path_taken(DiskSink *s, const char *path)
{
    struct stat st;
    char rp[PATHBUF];
    if (lstat(path, &st) == 0 && !sink_unwrap_exempt(s, path)) return 1;
    if (rsrc_path(path, s->hidden_forks, rp, sizeof rp) != 0) return 1;
    return lstat(rp, &st) == 0 && !sink_unwrap_exempt(s, rp);
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
                        NAME_IS_MACROMAN(s, info), s->raw_names);
}

/* --only: did the user name this entry? It matches a selector exactly,
 * or lies under one — naming a folder takes what is in it — and the
 * comparison is against the name `l` prints, so a row copied out of a
 * listing is a selector.
 *
 * Every match is recorded rather than the first, because the flags are
 * what let the run report a selector that matched NOTHING: a mistyped
 * name would otherwise extract nothing and say nothing, and exit 0. */
static int only_match(const char *const *only, unsigned char *hit, int nonly,
                      const char *name)
{
    int i, want = 0;

    for (i = 0; i < nonly; i++) {
        size_t n = strlen(only[i]);
        if (strcmp(name, only[i]) == 0 ||
            (strncmp(name, only[i], n) == 0 && name[n] == '/')) {
            hit[i] = 1;
            want = 1;
        }
    }
    return want;
}

static int only_wanted(DiskSink *s, const char *name)
{
    if (!s->nonly) return 1;
    return only_match(s->only, s->only_hit, s->nonly, name);
}

/* `l --meta`: what the Finder keeps beyond type, creator and flags, one
 * row per entry, every field hex so that it reads back whatever it holds:
 *
 *   m <FInfo|DInfo 32 hex> <FXInfo|DXInfo 32 hex> <backup 8 hex>
 *     <lock> <comment hex> NAME
 *   t <created 8 hex> <modified 8 hex> NAME
 *
 * `-` is a field the archive did not state; lock is `-`, `n` (stated, not
 * locked) or `L`. A date the engine marks as an instant, in UTC
 * (UNC_META_*_UTC), has a `Z` after its hex; one without is a wall clock
 * (include/macextract.h). A comment the engine marks as UTF-8
 * (UNC_META_CMT_UTF8) has a `U` after its hex. This is the CLI's whole share of the metadata: it writes
 * none of it to a Linux disk, where nothing would hold it — the `._NAME`
 * sidecar is the resource fork alone, the form `unar -k hidden` writes and
 * the differential suite compares (DECISIONS.md 2026-10-17). */
static void print_hex(const uint8_t *p, unsigned n)
{
    unsigned i;
    for (i = 0; i < n; i++) printf("%02x", p[i]);
}

static void print_meta(const UncEntryInfo *e, const char *name)
{
    printf("m ");
    if (e->meta & UNC_META_FINFO) print_hex(e->finder_info, 16);
    else printf("-");
    printf(" ");
    if (e->meta & UNC_META_FXINFO) print_hex(e->finder_info + 16, 16);
    else printf("-");
    if (e->meta & UNC_META_BACKUP)
        printf(" %08lx%s", (unsigned long)e->backup_date,
               (e->meta & UNC_META_BK_UTC) ? "Z" : "");
    else printf(" -");
    printf(" %s ", e->locked == UNC_LOCK_YES ? "L"
                 : e->locked == UNC_LOCK_NO ? "n" : "-");
    if (e->comment && e->comment_len) {
        print_hex(e->comment, e->comment_len);
        if (e->meta & UNC_META_CMT_UTF8) printf("U");
    } else printf("-");
    printf(" %s\n", name);
    /* And the two dates every entry has, which no other listing shows:
     * a 't' row, created then modified, '-' where the engine says 0
     * ("not stated", macextract.h). */
    printf("t ");
    if (e->create_date)
        printf("%08lx%s", (unsigned long)e->create_date,
               (e->meta & UNC_META_CR_UTC) ? "Z" : "");
    else printf("-");
    if (e->mod_date)
        printf(" %08lx%s", (unsigned long)e->mod_date,
               (e->meta & UNC_META_MD_UTC) ? "Z" : "");
    else printf(" -");
    printf(" %s\n", name);
}

static int sink_begin(void *ctx, const UncEntryInfo *info)
{
    DiskSink *s = (DiskSink *)ctx;
    char name[FS_NAME_MAX];

    name_to_fs(info->name, info->name_len, NAME_IS_MACROMAN(s, info),
               s->raw_names, name, sizeof name);

    /* Not asked for: skipped before it counts, so the tallies at the end
     * describe the SELECTION rather than the archive. */
    if (!only_wanted(s, name)) return 1;
    s->cur_aside = s->only_late &&
                   !only_match(s->late_sel, s->late_hit, s->late_nsel, name);
    s->aside[0][0] = s->aside[1][0] = 0;

    s->cur = *info;
    s->data_written = s->rsrc_written = 0;
    s->write_err = 0;
    s->said = 0;
    s->entries++;

    if (s->list_only && s->show_meta) {
        print_meta(info, name);
        return 1;
    }
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
        if (info->is_dir) {
            if (s->show_finder)
                printf("d %10s %10s %08lx/%08lx %04x %s\n", "-", "-",
                       (unsigned long)info->type, (unsigned long)info->creator,
                       (unsigned)info->finder_flags, name);
            else
                printf("d %10s %10s %-9s %s\n", "-", "-", "-", name);
        } else {
            char dsz[16], rsz[16];
            if (info->data_size == UNC_SIZE_UNKNOWN) snprintf(dsz, sizeof dsz, "?");
            else snprintf(dsz, sizeof dsz, "%u", info->data_size);
            if (info->rsrc_size == UNC_SIZE_UNKNOWN) snprintf(rsz, sizeof rsz, "?");
            else snprintf(rsz, sizeof rsz, "%u", info->rsrc_size);
            if (s->show_finder)
                printf("f %10s %10s %08lx/%08lx %04x %s\n", dsz, rsz,
                       (unsigned long)info->type, (unsigned long)info->creator,
                       (unsigned)info->finder_flags, name);
            else
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

    if (sink_make_dirs(s, info->is_dir) != 0) {
        fprintf(stderr, "macextract: %s: a folder of its path could not be "
                        "made\n", name);
        s->cur_path[0] = 0;
        s->errors++;
        return 1;
    }
    if (info->is_dir) return 1;
    /* A folder already has the leaf's name: the file is numbered past it,
     * as past any name taken, rather than refused. */
    {
        struct stat st;
        if (lstat(s->cur_path, &st) == 0 && S_ISDIR(st.st_mode)) {
            size_t reserve = info->rsrc_size == 0 ? 0u
                           : (s->hidden_forks ? 2u : 5u);
            if (!sink_number_path(s, (size_t)s->fs_name_max > reserve
                                     ? (size_t)s->fs_name_max - reserve : 1u))
                return 1;           /* every number taken: open refuses */
            fprintf(stderr, "macextract: %s: a folder has this name; written "
                            "as %s\n", name,
                    s->cur_path + strlen(s->outdir) + 1);
        }
    }
    return 0;
}

/* Resource-fork sidecar path for a data path, under the convention the
 * caller chose: "NAME.rsrc" (default, and what unar -k visible writes)
 * or "._NAME" (unar -k hidden). The suffix form is ambiguous whenever
 * an archive holds both "X" and "X.rsrc" — a THINK C project is that
 * shape — so the differential harness uses the prefix form, whose
 * namespace is disjoint from real archive names.
 * DECISIONS.md, 2026-08-08. */
/* Returns 0, or -1 with `out` emptied where the path does not fit: a
 * cut path names a DIFFERENT file, and remove() on one deleted a
 * sibling (DECISIONS.md 2026-11-07, *the path a buffer cut*). */
static int rsrc_path(const char *path, int hidden, char *out, size_t outsz)
{
    const char *slash;
    int n;
    if (!hidden)
        n = snprintf(out, outsz, "%s.rsrc", path);
    else if ((slash = strrchr(path, '/')) != NULL)
        n = snprintf(out, outsz, "%.*s._%s", (int)(slash - path + 1), path,
                     slash + 1);
    else
        n = snprintf(out, outsz, "._%s", path);
    if (n < 0 || (size_t)n >= outsz) {
        if (outsz) out[0] = 0;
        return -1;
    }
    return 0;
}

/* StuffIt classic keeps the block that verifies a password in the
 * ARCHIVE's resource fork ('MKey' 0), so an encrypted .sit can only be
 * decrypted where that fork survived. On this side of the world it
 * survives as the sidecar file this program itself writes when it takes
 * a MacBinary or BinHex envelope off — so look for it under both
 * spellings, and say nothing if there is none. */
/* A ceiling of ours, not the format's: the largest sidecar read whole
 * looking for an 'MKey'. The fork is read WHOLE because its map is at its
 * end; a fixed 256 KB read hid the 'MKey' of any larger fork
 * (DECISIONS.md 2026-11-07, *the key past 256 KB*). */
#define MKEY_FORK_MAX (32ul * 1024 * 1024)

static int load_mkey(const char *path, int hidden, uint8_t out[8])
{
    char rp[PATHBUF];
    int which;

    for (which = 0; which < 2; which++) {
        FILE *f;
        struct stat st;
        uint8_t *fork;
        size_t n;
        uint32_t off = 0, len = 0;
        int found;
        if (rsrc_path(path, which == 0 ? hidden : !hidden, rp, sizeof rp))
            continue;
        if (stat(rp, &st) != 0 || !S_ISREG(st.st_mode) || st.st_size <= 0)
            continue;
        if ((unsigned long)st.st_size > MKEY_FORK_MAX) {
            fprintf(stderr, "macextract: %s: over %lu MB, not searched for "
                    "the archive's key\n", rp, MKEY_FORK_MAX >> 20);
            continue;
        }
        fork = (uint8_t *)malloc((size_t)st.st_size);
        if (!fork) continue;
        f = fopen(rp, "rb");
        n = f ? fread(fork, 1, (size_t)st.st_size, f) : 0;
        if (f) fclose(f);
        found = unc_resfork_find(fork, (uint32_t)n, 0x4D4B6579u /* 'MKey' */,
                                 0, &off, &len) == UNC_OK && len == 8;
        if (found) memcpy(out, fork + off, 8);
        free(fork);
        if (found) return 1;
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
 * inner entry may legitimately carry its name. Such an entry is written
 * BESIDE it (DEFER_SUFFIX) and renamed onto it after the deletion: written
 * in place, it truncated the envelope while the engine was still reading
 * it, and the deletion then removed the entry instead — exit 0 and
 * nothing on disk, measured 2026-10-14 on a .hcx inside a .hex, where the
 * name hint gives both layers the same name. */
#define DEFER_SUFFIX ".unwrap~"
/* Which of the two exempt paths `path` is: 1 for the envelope, 2 for
 * its sidecar, 0 for neither. */
static int sink_unwrap_exempt(DiskSink *s, const char *path)
{
    if (!s->unwrap_src || !s->unwrap_src[0]) return 0;
    if (strcmp(path, s->unwrap_src) == 0) return 1;
    /* The sidecar only if the layer before WROTE it: a file of that name
     * that this run did not write is the user's, and is neither exempt
     * nor deleted (DECISIONS.md 2026-11-07, *what the CLI may delete*). */
    return s->unwrap_rsrc && s->unwrap_rsrc[0] &&
           strcmp(path, s->unwrap_rsrc) == 0 ? 2 : 0;
}

/* Is `st` one of the files this layer is reading? By inode, not by
 * name: `--overwrite` once opened the input archive itself "wb" when
 * its only entry carried its filename, and a hard link or another
 * spelling of the same file is the same file. DECISIONS.md 2026-11-07,
 * *what the CLI may delete*. */
static int read_has(const ReadList *r, const struct stat *st)
{
    int i;
    for (i = 0; i < r->n; i++)
        if (r->id[i].dev == st->st_dev && r->id[i].ino == st->st_ino)
            return 1;
    return 0;
}

static int sink_is_reading(const DiskSink *s, const struct stat *st)
{
    return read_has(&s->reading, st);
}

/* Remember a file that is read. A path that cannot be stat()ed is not
 * one the engine can be reading. */
static void read_add(ReadList *r, const char *path)
{
    struct stat st;
    if (r->n >= READ_MAX || stat(path, &st) != 0 || read_has(r, &st))
        return;
    r->id[r->n].dev = st.st_dev;
    r->id[r->n].ino = st.st_ino;
    r->n++;
}

static void sink_note_reading(DiskSink *s, const char *path)
{
    read_add(&s->reading, path);
}

/* The new file an entry written aside goes to: beside `path`, in its
 * folder, named by mkstemp so that nothing already there is opened. */
#define ASIDE_NAME ".macextract-aside-XXXXXX"
static FILE *sink_open_aside(DiskSink *s, UncFork fork, const char *path)
{
    char *t = s->aside[fork == UNC_FORK_RSRC];
    const char *slash = strrchr(path, '/');
    size_t dl = slash ? (size_t)(slash - path) : 1u;
    FILE *f;
    int fd;
    if (dl + sizeof "/" ASIDE_NAME > PATHBUF) {
        errno = ENAMETOOLONG;
        return NULL;
    }
    memcpy(t, slash ? path : ".", dl);
    memcpy(t + dl, "/" ASIDE_NAME, sizeof "/" ASIDE_NAME);
    fd = mkstemp(t);
    if (fd < 0) { t[0] = 0; return NULL; }
    (void)fchmod(fd, s->file_mode);
    f = fdopen(fd, "wb");
    if (!f) { close(fd); remove(t); t[0] = 0; }
    return f;
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
    FILE *f;
    int ex;
    s->clobber = 0;
    if (fork == UNC_FORK_DATA)
        snprintf(path, sizeof path, "%s", s->cur_path);
    else if (rsrc_path(s->cur_path, s->hidden_forks, path, sizeof path)) {
        s->clobber = s->said = 1;
        fprintf(stderr, "macextract: %s: the resource fork's path is too "
                "long to write\n", s->cur_path);
        return NULL;
    }
    if (s->cur_aside) return sink_open_aside(s, fork, path);
    /* Keyed by the PATH that matched, not by the fork being written: an
     * inner data fork can carry the envelope's sidecar name, and keyed by
     * fork it was renamed onto the envelope's data path, which was gone —
     * left as NAME.rsrc.unwrap~ with exit 0. A second entry onto the same
     * path is taken like any written path: refused, or with --overwrite
     * written over the deferred copy. */
    if ((ex = sink_unwrap_exempt(s, path)) != 0) {
        size_t n = strlen(path);
        if (n + sizeof DEFER_SUFFIX > sizeof path) return NULL;
        if (s->deferred[ex - 1] && !s->overwrite) {
            s->clobber = s->said = 1;
            fprintf(stderr, "macextract: %s: output path already exists; "
                    "re-run with --forks hidden to keep both forks, or "
                    "--overwrite\n", path);
            return NULL;
        }
        memcpy(path + n, DEFER_SUFFIX, sizeof DEFER_SUFFIX);
        /* A NAME.unwrap~ already there is somebody's file like any
         * other; marked only once created, so the rename can only ever
         * move what this run wrote. */
        f = create_file(path, s->overwrite);
        if (f) s->deferred[ex - 1] = 1;
        return f;
    }
    /* Refused, not deferred, even with --overwrite: on the first layer
     * the file being read is the user's archive, which nothing deletes,
     * so writing beside it and renaming would replace their original with
     * its own contents. */
    if (lstat(path, &st) == 0) {
        if (!S_ISLNK(st.st_mode) && sink_is_reading(s, &st)) {
            s->clobber = s->said = 1;
            fprintf(stderr, "macextract: %s: is the archive being read; not "
                    "written over\n", path);
            return NULL;
        }
        if (!s->overwrite) {
            s->clobber = s->said = 1;
            fprintf(stderr, "macextract: %s: output path already exists; "
                    "re-run with --forks hidden to keep both forks, or "
                    "--overwrite\n", path);
            return NULL;
        }
    }
    return create_file(path, s->overwrite);
}

/* A write that failed, said once per entry with what the system said:
 * "output error" alone does not tell a full disk from a quota. */
static void sink_say_write_error(DiskSink *s, UncFork fork)
{
    char rp[PATHBUF];
    const char *path = s->cur_path;
    int e = errno;
    if (s->write_err) return;
    s->write_err = s->said = 1;
    if (fork == UNC_FORK_RSRC &&
        rsrc_path(s->cur_path, s->hidden_forks, rp, sizeof rp) == 0)
        path = rp;
    fprintf(stderr, "macextract: %s: %s\n", path, strerror(e));
}

/* Close one fork, and fail the entry if the close does: stdio holds a
 * small file whole, so a full disk or a quota is reported HERE and
 * nowhere else. Ignored until 2026-11-07, the entry counted as written
 * and the layer above it was deleted (DECISIONS.md 2026-11-07, *the
 * error only fclose saw*). */
static int sink_close_fork(DiskSink *s, FILE **fp, UncFork fork)
{
    int bad;
    if (!*fp) return 0;
    errno = 0;
    bad = fflush(*fp) != 0 || ferror(*fp);
    if (bad) sink_say_write_error(s, fork);
    if (fclose(*fp) != 0 && !bad) {
        bad = 1;
        sink_say_write_error(s, fork);
    }
    *fp = NULL;
    return bad;
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
            s->said = 1;
            return -1;
        }
    }
    if (len > 0 && fwrite(buf, 1, (size_t)len, *fp) != (size_t)len) {
        sink_say_write_error(s, fork);
        return -1;
    }
    if (fork == UNC_FORK_DATA) s->data_written += (uint32_t)len;
    else s->rsrc_written += (uint32_t)len;
    return 0;
}

/* The StuffIt add-on modules, named, or NULL for a pair this does not
 * know — third-party modules existed and an id prints on its own.
 *
 * Source: StuffIt Deluxe 2.0.1's own two floppies. The Optimizers are
 * the five files in the installer payload's `Optimizers` folder and
 * PassLock is its `Encryptors` one, each named by its 'COMP'/'DCMP'
 * resource id; NewDEx and DESex come off `deluxe-2-optional.sit` the
 * same way. Encryptor 1 is the one module no file here has and the
 * application names in its own code — the switch in its CODE 11 prints
 * "DES" (FORMATS.md, *Where an archive names the module*).
 *
 * Encryptor **4 is deliberately absent**: it is the built-in scheme that
 * replaced the modules, which is the one this engine implements, so it
 * is not an add-on to name and its absence here is what makes the
 * encrypted report below say something only when a password cannot help.
 *
 * Here and not in the engine because on the 68000 target these strings
 * are .rodata in the A5 world, resident for every extraction, and the
 * Macintosh shell has no room to print them. */
static const char *module_name(unsigned kind, unsigned id)
{
    if (kind == UNC_MODULE_OPTIMIZER) {
        switch (id) {
        case 1: return "Sound 1";
        case 2: return "Photoshop 1";
        case 3: return "Photoshop:JPEG Lossy";
        case 4: return "MacPaint 1";
        case 5: return "Text 1";
        default: return NULL;
        }
    }
    if (kind == UNC_MODULE_ENCRYPTOR) {
        switch (id) {
        case 1:  return "DES";
        case 2:  return "PassLock";
        case 3:  return "NewDEx";
        case 64: return "DESex";
        default: return NULL;
        }
    }
    return NULL;
}

/* Remember an entry written aside, or remove what it wrote when it
 * failed: a file nobody asked for is not left half-written either. */
static void sink_note_aside(DiskSink *s, int ok)
{
    char rp[PATHBUF];
    struct LateFile *e;
    int k;
    if (ok && s->nlate == s->latecap) {
        int cap = s->latecap ? s->latecap * 2 : 4;
        struct LateFile *p = (struct LateFile *)realloc(s->late,
                                                       (size_t)cap * sizeof *p);
        if (p) { s->late = p; s->latecap = cap; }
    }
    if (!ok || s->nlate == s->latecap) {
        for (k = 0; k < 2; k++) if (s->aside[k][0]) remove(s->aside[k]);
        return;
    }
    e = &s->late[s->nlate];
    e->path[0] = seg_dup(s->cur_path);
    e->path[1] = s->aside[1][0] &&
                 rsrc_path(s->cur_path, s->hidden_forks, rp, sizeof rp) == 0
               ? seg_dup(rp) : NULL;
    e->at[0] = s->aside[0][0] ? seg_dup(s->aside[0]) : NULL;
    e->at[1] = s->aside[1][0] ? seg_dup(s->aside[1]) : NULL;
    if (e->path[0] && e->at[0] && (!s->aside[1][0] || (e->path[1] && e->at[1]))) {
        s->nlate++;
        return;
    }
    for (k = 0; k < 2; k++) {
        if (s->aside[k][0]) remove(s->aside[k]);
        free(e->path[k]);
        free(e->at[k]);
    }
}

/* Forget the asides, removing them first with `drop`. */
static void sink_late_done(DiskSink *s, int drop)
{
    int i, k;
    for (i = 0; i < s->nlate; i++)
        for (k = 0; k < 2; k++) {
            if (drop && s->late[i].at[k]) remove(s->late[i].at[k]);
            free(s->late[i].path[k]);
            free(s->late[i].at[k]);
        }
    free(s->late);
    s->late = NULL;
    s->nlate = s->latecap = 0;
}

/* The chain goes on through this layer: every aside is moved onto its
 * own path, under the rules sink_open_fork would have applied there —
 * the file being read is never replaced, an existing one only with
 * --overwrite. Called once the envelope's own file is gone, so its path
 * is free. Returns the number refused; a refused aside is removed. */
static int sink_aside_settle(DiskSink *s)
{
    int i, k, bad = 0;
    for (i = 0; i < s->nlate; i++)
        for (k = 0; k < 2; k++) {
            struct LateFile *e = &s->late[i];
            struct stat st;
            const char *why = NULL;
            if (!e->at[k]) continue;
            if (lstat(e->path[k], &st) == 0) {
                if (!S_ISLNK(st.st_mode) && sink_is_reading(s, &st))
                    why = "is the archive being read; not written over";
                else if (!s->overwrite)
                    why = "output path already exists; re-run with --forks "
                          "hidden to keep both forks, or --overwrite";
            }
            if (!why && rename(e->at[k], e->path[k]) != 0)
                why = strerror(errno);
            if (why) {
                fprintf(stderr, "macextract: %s: %s\n", e->path[k], why);
                remove(e->at[k]);
                bad++;
            }
            free(e->at[k]);
            e->at[k] = NULL;
        }
    sink_late_done(s, 0);
    return bad;
}

/* Name each selector that matched nothing; returns how many. */
static int only_report_misses(const char *const *only, const unsigned char *hit,
                              int nonly)
{
    int i, miss = 0;
    for (i = 0; i < nonly; i++)
        if (!hit[i]) {
            fprintf(stderr, "macextract: --only \"%s\": no entry of this "
                    "archive has that name\n", only[i]);
            miss++;
        }
    return miss;
}

/* A layer under `only_late` that is the last one: remove what it wrote
 * aside, count its hits, and report what matched nothing. Returns the
 * number of misses. */
static int sink_late_final(DiskSink *s, const char *const *only,
                           unsigned char *only_hit, int nonly)
{
    int i;
    if (!s->only_late) return 0;
    for (i = 0; i < nonly; i++)
        if (s->late_hit[i]) only_hit[i] = 1;
    sink_late_done(s, 1);
    return only_report_misses(only, only_hit, nonly);
}

static int sink_end(void *ctx, int status)
{
    DiskSink *s = (DiskSink *)ctx;
    char name[FS_NAME_MAX];

    int wrote_rsrc = s->rsrc_f != NULL;

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
        if (sink_close_fork(s, &s->data_f, UNC_FORK_DATA) &&
            status == UNC_OK)
            status = UNC_ERR_SINK;
        if (sink_close_fork(s, &s->rsrc_f, UNC_FORK_RSRC) &&
            status == UNC_OK)
            status = UNC_ERR_SINK;
    }

    name_to_fs(s->cur.name, s->cur.name_len, NAME_IS_MACROMAN(s, &s->cur),
               s->raw_names, name, sizeof name);

    if (status != UNC_OK) {
        s->errors++;
        if (status == UNC_ERR_MODULE) {
            /* Name the module, which is the one thing a user can act
             * on: the file wants a 1990 StuffIt add-on, and no
             * unarchiver since has had one. The id is what the archive
             * records; the name is this host's, not the engine's, so
             * that the Macintosh build does not pay A5 for a table only
             * a terminal prints (macextract.h, UNC_MODULE_*). */
            static const char *const kinds[] = {
                "", "Optimizer", "Compressor", "Encryptor"
            };
            unsigned k = s->cur.module_kind;
            const char *mn = module_name(k, s->cur.module_id);
            if (k > UNC_MODULE_ENCRYPTOR) k = 0;
            if (mn)
                fprintf(stderr, "macextract: %s: needs the \"%s\" StuffIt "
                                "%s, which nothing has\n",
                        name, mn, kinds[k]);
            else
                fprintf(stderr, "macextract: %s: needs StuffIt %s module "
                                "%u, which nothing has\n",
                        name, kinds[k], s->cur.module_id);
        } else if (status == UNC_ERR_UNSUPPORTED) {
            /* Name the method. A report that says "method 13" is one
             * somebody can act on; "unsupported" is not. The id is
             * informational (UncEntryInfo), and 0 means the format did
             * not state one. */
            unsigned m = s->cur.method_data ? s->cur.method_data
                                            : s->cur.method_rsrc;
            if (!s->unsupported) s->unsup_method = (int)m;
            s->unsupported++;
            if (s->cur.module_kind == UNC_MODULE_OPTIMIZER &&
                module_name(UNC_MODULE_OPTIMIZER, s->cur.module_id))
                /* The method byte of an optimized fork carries the
                 * Optimizer bit, so "method 64" named nothing: it is
                 * what a greyscale `JPEG Lossy` entry said until
                 * 2026-10-11. Name the module instead. */
                fprintf(stderr, "macextract: %s: what the \"%s\" StuffIt "
                                "Optimizer stored here is not supported "
                                "yet\n", name,
                        module_name(UNC_MODULE_OPTIMIZER, s->cur.module_id));
            else if (m)
                fprintf(stderr, "macextract: %s: method %u is not "
                                "supported yet\n", name, m);
            else
                fprintf(stderr, "macextract: %s: %s\n", name,
                        unc_strerror(status));
        } else if (status == UNC_ERR_ENCRYPTED &&
                   s->cur.module_kind == UNC_MODULE_ENCRYPTOR &&
                   module_name(UNC_MODULE_ENCRYPTOR, s->cur.module_id)) {
            /* Every encryptor this host can NAME, the engine implements
             * — `DES`, `PassLock`, `NewDEx` and `DESex` (src/fmt_sit.c,
             * sit_enc_known) — so UNC_ERR_ENCRYPTED on one of them
             * means the cipher was never reached: its key is the
             * archive's 'MKey' resource, and this copy has no resource
             * fork. Until 2026-10-11 this said the engine "does not
             * implement" the cipher, which was true of nothing it could
             * fire on; a forkless DES archive is what showed it
             * (tools/run_sitcombo.py). An id with no name is a third
             * party's module and gets the generic refusal below. */
            fprintf(stderr, "macextract: %s: encrypted with StuffIt's "
                            "\"%s\", whose key is in the archive's "
                            "resource fork — which this copy does not "
                            "have\n",
                    name, module_name(UNC_MODULE_ENCRYPTOR,
                                      s->cur.module_id));
        } else if (!(status == UNC_ERR_SINK && s->said)) {
            fprintf(stderr, "macextract: %s: %s\n", name, unc_strerror(status));
        }
    } else {
        /* An Optimizer this engine could only PART undo. The bytes are
         * on the disk under the archive's name and they are not the
         * bytes that went in — `MacPaint 1` throws a painting's
         * 512-byte header and its resource fork away and neither this
         * nor StuffIt Deluxe can put them back — so say so, every
         * time, whether or not anybody asked for -v. An entry restored
         * EXACTLY (module_restored 1) says nothing: its own CRC
         * verified it. README.md, *Compared with what Aladdin sold*. */
        if (s->cur.module_restored == 2 && !s->list_only) {
            const char *mn = module_name(s->cur.module_kind,
                                         s->cur.module_id);
            s->inexact++;
            fprintf(stderr, "macextract: %s: rebuilt from what the \"%s\" "
                            "StuffIt Optimizer left — a valid document, "
                            "NOT the original file\n",
                    name, mn ? mn : "?");
        }
        if (s->verbose && !s->list_only)
            printf("  %s (%u data, %u rsrc)\n", name,
                   s->data_written, s->rsrc_written);
    }
    if (s->cur.is_dir) s->dir_count++;
    else {
        s->file_count++;
        if (s->cur_aside)
            sink_note_aside(s, status == UNC_OK && s->cur_path[0]);
        if (status == UNC_OK && s->cur_path[0])
        {
            snprintf(s->last_ok_path, sizeof s->last_ok_path, "%s",
                     s->cur_path);
            snprintf(s->last_ok_at, sizeof s->last_ok_at, "%s",
                     s->cur_aside ? s->aside[0] : s->cur_path);
            /* Recorded, never inferred from the name: what the next
             * layer may delete is what this one wrote. */
            if (wrote_rsrc)
                (void)rsrc_path(s->cur_path, s->hidden_forks, s->last_ok_rsrc,
                                sizeof s->last_ok_rsrc);  /* "" if cut */
            else
                s->last_ok_rsrc[0] = 0;
            s->last_ok_type = s->cur.type;
        }
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
    char path[PATHBUF];
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
    if (lstat(path, &st) == 0 && !S_ISLNK(st.st_mode) &&
        sink_is_reading(s, &st)) {
        fprintf(stderr, "macextract: %s: is the archive being read; "
                "the archive comment was not written\n", path);
        return 0;
    }
    if (!s->overwrite && lstat(path, &st) == 0) {
        fprintf(stderr, "macextract: %s: output path already exists; "
                "the archive comment was not written (use --overwrite)\n",
                path);
        return 0;
    }
    f = create_file(path, s->overwrite);
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
 * whole data fork to a file, and the resource fork, if the envelope
 * carries one, to the `.rsrc` sidecar beside it (rsrc_path).
 *
 * The join itself concatenates data forks (unc_extract_segments), so
 * the resource fork is nothing the joiner reads. It is kept because of
 * what seg_file_len reads from it: a fat installer's part 1 says where
 * its segment ends in its own resource fork ('endD'; fmt_sitseg_end.c),
 * and a peel that wrote the data fork alone joined Now Utilities 6.0
 * wrong with that fork right there in the envelope (DECISIONS.md,
 * *the fork the peel dropped*). PEEK ignores it: a hundred bytes of
 * data fork is what decides. */
typedef struct {
    FILE    *out;           /* PEEL: where the data fork goes          */
    const char *rsrc_dest;  /* PEEL: the sidecar, opened on first byte */
    FILE    *rout;
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

    if (len <= 0) return 0;
    if (fork == UNC_FORK_RSRC) {
        /* Opened on the first byte, so a part with no resource fork
         * leaves no empty sidecar; an empty fork says nothing either. */
        if (!e->out || !e->rsrc_dest) return 0;
        if (!e->rout) {
            e->rout = create_file(e->rsrc_dest, 0);
            if (!e->rout) { e->err = 1; return -1; }
        }
        if (fwrite(buf, 1, (size_t)len, e->rout) != (size_t)len) {
            e->err = 1;
            return -1;
        }
        return 0;
    }
    if (fork != UNC_FORK_DATA) return 0;
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
    f.size = stat(path, &st) == 0 ? (unc_off_t)st.st_size : UNC_OFF_UNKNOWN;
    eio.ctx = &f;
    eio.read = fio_read;
    eio.seek = fio_seek;
    eio.tell = fio_tell;
    eio.size = fio_size;

    fmt = unc_sniff_envelope(&eio);
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

/* Take one envelope off `path`, writing the payload's data fork to
 * `dest` and its resource fork, if any, to the sidecar `dest.rsrc`, both
 * created new (create_file). Returns 1 on success, setting *wrote_rsrc;
 * on failure removes what it created, and only that. */
static int env_peel(const char *path, const char *dest, int *wrote_rsrc)
{
    EnvSink es;
    char rp[PATHBUF];
    int ok;

    *wrote_rsrc = 0;
    memset(&es, 0, sizeof es);
    if (rsrc_path(dest, 0, rp, sizeof rp)) return 0;
    es.rsrc_dest = rp;
    es.out = create_file(dest, 0);
    if (!es.out) return 0;
    ok = env_run(path, &es);
    if (fclose(es.out) != 0) es.err = 1;
    if (es.rout && fclose(es.rout) != 0) es.err = 1;
    if (ok && !es.err) {
        *wrote_rsrc = es.rout != NULL;
        return 1;
    }
    remove(dest);
    if (es.rout) remove(rp);
    return 0;
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
    /* A split with --ask is open-ended (nparts 0): the highest NAME.NNN
     * seen, which tells a gap (asked for) from the set's end (asked
     * whether there is one). */
    int      highest;
    /* Parts that arrived inside an envelope are decoded to here before
     * the join; see seg_wrapped_part_of. Empty until one has been. */
    const char *outdir;
    char     peeldir[PATHBUF];
    unsigned char peeled[UNC_SEG_MAX_PARTS + 1];  /* 1: part-NNN written
                                                   * there, 3: and its
                                                   * .rsrc sidecar     */
    DiskSink *sink;     /* told of each part as it is located, so that no
                         * entry is written over a part (sink_is_reading) */
} SegHost;

/* How much of part `part`'s file is the part: its size, except that a
 * fat installer's part 1 stops where its resource fork says (under
 * either sidecar spelling, as load_mkey looks; unc_segment_first_end). */
static uint32_t seg_file_len(const SegHost *h, int part)
{
    struct stat st;
    uint32_t len;
    char rp[PATHBUF];
    int which;

    if (stat(h->path[part], &st) != 0) return UNC_SIZE_UNKNOWN;
    len = (uint32_t)st.st_size;
    if (part != 1 || h->desc.scheme != UNC_FORMAT_SITSEG) return len;
    for (which = 0; which < 2; which++) {
        FileIO rf;
        UncIO rio;
        uint32_t end;
        if (rsrc_path(h->path[part], which, rp, sizeof rp)) continue;
        if (stat(rp, &st) != 0 || !S_ISREG(st.st_mode)) continue;
        rf.f = fopen(rp, "rb");
        if (!rf.f) continue;
        rf.size = (unc_off_t)st.st_size;
        rio.ctx = &rf;
        rio.read = fio_read;
        rio.seek = fio_seek;
        rio.tell = fio_tell;
        rio.size = fio_size;
        end = unc_segment_first_end(&h->desc, &rio, len);
        fclose(rf.f);
        if (end != len) return end;
    }
    return len;
}

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
    /* message/partial identifies a part in its mail headers, which are
     * longer than the 100 bytes unc_segment_match is given — so the
     * candidate is DESCRIBED instead, which reads as much of it as it
     * needs. Still identity by content: what is compared is the set's
     * `id`, and the filename decides nothing (macextract.h). */
    if (h->desc.scheme == UNC_FORMAT_MIMESEG) {
        UncSegmentDesc cand;
        FileIO cf;
        UncIO cio;
        int ok;
        memset(&cf, 0, sizeof cf);
        cf.f = f;
        cf.size = (unc_off_t)st.st_size;
        cio.ctx = &cf;
        cio.read = fio_read;
        cio.seek = fio_seek;
        cio.tell = fio_tell;
        cio.size = fio_size;
        ok = unc_segment_describe_as(&cio, UNC_FORMAT_MIMESEG,
                                     &cand) == UNC_OK &&
             memcmp(cand.fp, h->desc.fp, UNC_SEG_FP_LEN) == 0;
        fclose(f);
        return ok ? (int)cand.part : 0;
    }
    got = fread(head, 1, sizeof head, f);
    fclose(f);
    return unc_segment_match(&h->desc, head, (int32_t)got);
}

/* How many parts a message/partial part says its set has, or 0. Only
 * the LAST part is required to carry `total` (RFC 2046 5.2.2), so a
 * set opened anywhere else has to ask around for its count — the same
 * shape a Compact Pro set has, where only the final segment knows. */
static int mimeseg_nparts_of(const char *path)
{
    UncSegmentDesc cand;
    FileIO cf;
    UncIO cio;
    struct stat st;
    FILE *f;
    int n = 0;

    if (stat(path, &st) != 0 || !S_ISREG(st.st_mode)) return 0;
    f = fopen(path, "rb");
    if (!f) return 0;
    memset(&cf, 0, sizeof cf);
    cf.f = f;
    cf.size = (unc_off_t)st.st_size;
    cio.ctx = &cf;
    cio.read = fio_read;
    cio.seek = fio_seek;
    cio.tell = fio_tell;
    cio.size = fio_size;
    if (unc_segment_describe(&cio, &cand) == UNC_OK &&
        cand.scheme == UNC_FORMAT_MIMESEG)
        n = (int)cand.nparts;
    fclose(f);
    return n;
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

#define SEG_PEELDIR ".macextract-parts-XXXXXX"

/* Make the directory decoded parts go in. It is inside the output
 * directory, which the caller has already created and is the one place
 * this program knows it may write — and it is a NEW one, named by
 * mkdtemp: a fixed name accepted one already there, a link to a folder
 * elsewhere included, and the cleanup then emptied it (DECISIONS.md
 * 2026-11-07, *the parts folder that was not ours*). */
static int seg_peel_dir(SegHost *h)
{
    if (h->peeldir[0]) return 1;
    if (!h->outdir) return 0;
    if ((size_t)snprintf(h->peeldir, sizeof h->peeldir, "%s/%s",
                         h->outdir, SEG_PEELDIR) >= sizeof h->peeldir ||
        !mkdtemp(h->peeldir)) {
        h->peeldir[0] = 0;
        return 0;
    }
    return 1;
}

/* Remove the decoded parts and the directory holding them. Called
 * whatever the join did: they are this program's own litter, and an
 * archive that failed to join is exactly when a user is least helped
 * by finding pieces of it lying around. */
/* The files removed are the ones seg_wrapped_part_of recorded writing,
 * and the folder goes with rmdir, which refuses one that is not empty:
 * nothing else in it is this program's to delete. */
static void seg_peel_clean(SegHost *h)
{
    int part;

    if (!h->peeldir[0]) return;
    for (part = 1; part <= UNC_SEG_MAX_PARTS; part++) {
        char p[PATHBUF], rp[PATHBUF];
        if (!h->peeled[part]) continue;
        if ((size_t)snprintf(p, sizeof p, "%s/part-%03d", h->peeldir, part)
            >= sizeof p)
            continue;
        remove(p);
        if ((h->peeled[part] & 2) && rsrc_path(p, 0, rp, sizeof rp) == 0)
            remove(rp);
        h->peeled[part] = 0;
    }
    rmdir(h->peeldir);
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
        uint32_t len = seg_file_len(h, p);
        if (len == UNC_SIZE_UNKNOWN || len <= h->desc.head_len) return 0;
        sum += len - h->desc.head_len;
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
    char dest[PATHBUF];
    struct stat st;
    int32_t got;
    int part, wrote_rsrc;

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
    if (!env_peel(path, dest, &wrote_rsrc)) return 0;
    h->peeled[part] = (unsigned char)(wrote_rsrc ? 3 : 1);

    if (h->verbose)
        fprintf(stderr, "unwrapping part %d: %s\n", part, path);
    seg_record(h, part, dest);
    return part;
}

/* ------------------------------------------------------------------ */
/* A set's folder, and the one walk over it                            */
/*                                                                    */
/* Every way this file finds parts beside the one it was given is the */
/* same walk: the folder that file is in, each entry, a path to it.   */
/* What admits an entry is the only difference. A scheme placed by    */
/* NAME (ZIPSEG, SPLIT) admits a regular file whose name is a member  */
/* of the family, by the engine's unc_segment_name_part — the rule    */
/* the Mac shell uses too. A scheme placed by CONTENT (UNKNOWN here)  */
/* admits every entry and leaves the judging to the visitor.          */
/* ------------------------------------------------------------------ */

typedef struct Family {
    char        dir[PATHBUF];   /* the folder to walk                    */
    const char *stem;           /* NAME of NAME.zNN or NAME.NNN, unterminated */
    size_t      stemlen;
    UncFormat   scheme;         /* ZIPSEG or SPLIT; UNKNOWN: by content  */
} Family;

/* Which member of f's family the file called `name` is, or 0. */
static int family_member(const Family *f, const char *name)
{
    return unc_segment_name_part(f->scheme, (const uint8_t *)f->stem,
                                 (uint32_t)f->stemlen, (const uint8_t *)name,
                                 (uint32_t)strlen(name));
}

/* The part a file's own name makes it, its folder aside: what --part
 * has to go on when a file was given from elsewhere. A member's
 * extension is three bytes in both schemes, so its stem is all of the
 * name but the last four. */
static int own_part(UncFormat scheme, const char *path)
{
    const char *slash = strrchr(path, '/');
    const char *base = slash ? slash + 1 : path;
    size_t n = strlen(base);

    if (n < 5) return 0;                       /* "x.001" is the shortest */
    return unc_segment_name_part(scheme, (const uint8_t *)base,
                                 (uint32_t)(n - 4), (const uint8_t *)base,
                                 (uint32_t)n);
}

/* Fill `f` for the family of `path`: the folder it is in, and for a
 * named scheme the stem it shares. Returns the part `path` itself is
 * (UNC_SEG_NAME_LAST for a zip's .zip), 1 for UNKNOWN, or 0 when its
 * name is no member or its folder does not fit. */
static int family_of(Family *f, const char *path, UncFormat scheme)
{
    const char *slash = strrchr(path, '/');
    const char *base = slash ? slash + 1 : path;
    size_t n = slash ? (size_t)(slash - path) : 0;
    int self = 1;

    f->scheme = scheme;
    f->stem = base;
    f->stemlen = 0;
    if (scheme != UNC_FORMAT_UNKNOWN) {
        self = own_part(scheme, base);
        if (!self) return 0;
        f->stemlen = strlen(base) - 4;
    }
    if (n + 2 >= sizeof f->dir) return 0;     /* "." and "/" take two */
    if (!slash) { f->dir[0] = '.'; f->dir[1] = 0; }
    else if (n == 0) { f->dir[0] = '/'; f->dir[1] = 0; }
    else { memcpy(f->dir, path, n); f->dir[n] = 0; }
    return self;
}

/* Called for each admitted entry with its path and, for a named
 * scheme, its part (0 under UNKNOWN). Nonzero ends the walk. */
typedef int (*FamilyVisit)(void *ctx, int part, const char *path);

static void family_scan(const Family *f, FamilyVisit visit, void *ctx)
{
    char cand[PATHBUF];
    DIR *d = opendir(f->dir);
    struct dirent *de;

    if (!d) return;
    while ((de = readdir(d)) != NULL) {
        int part = 0;
        if (f->scheme == UNC_FORMAT_UNKNOWN) {
            if (strcmp(de->d_name, ".") == 0 || strcmp(de->d_name, "..") == 0)
                continue;
        } else if ((part = family_member(f, de->d_name)) == 0) {
            continue;
        }
        if ((size_t)snprintf(cand, sizeof cand, "%s/%s", f->dir, de->d_name)
            >= sizeof cand)
            continue;
        if (f->scheme != UNC_FORMAT_UNKNOWN) {
            struct stat st;
            if (stat(cand, &st) != 0 || !S_ISREG(st.st_mode)) continue;
        }
        if (visit(ctx, part, cand)) break;
    }
    closedir(d);
}

/* Scan the directory holding `anchor` for parts of the set, by
 * content. With `wrapped`, a candidate that is not a part in its own
 * right is also tried as an envelope holding one. */
typedef struct { SegHost *h; int wrapped; } DirScan;

static int dir_visit(void *ctx, int part, const char *path)
{
    DirScan *s = (DirScan *)ctx;
    part = seg_part_of(s->h, path);
    if (part) seg_record(s->h, part, path);
    else if (s->wrapped) (void)seg_wrapped_part_of(s->h, path);
    return 0;
}

static void seg_scan_dir(SegHost *h, const char *anchor, int wrapped)
{
    Family f;
    DirScan s;

    if (!family_of(&f, anchor, UNC_FORMAT_UNKNOWN)) return;
    s.h = h;
    s.wrapped = wrapped;
    family_scan(&f, dir_visit, &s);
}

/* ------------------------------------------------------------------ */
/* Spanned zip: the same three ways in, decided by NAME                 */
/*                                                                    */
/* A spanned zip fingerprints nothing, so unc_segment_match cannot be  */
/* asked and the parts are ordered the only way the format allows —    */
/* by the extension Info-ZIP gives them, NAME.z01 ... NAME.z99 with    */
/* the last part called NAME.zip (unc_segment_name_part has the rule   */
/* and its source). What keeps a wrong file out is not this scan but   */
/* the structural check the engine makes on the assembled set; see     */
/* unc_extract_segments in macextract.h.                               */
/* ------------------------------------------------------------------ */

/* Walk the family's directory and record every member. `nparts` says
 * which slot the ".zip" member belongs in; pass 0 while that is still
 * unknown, which records every other member and leaves that one out.
 * `lastbuf` receives the ".zip" member's path either way, since it has
 * to be described before the count can be known at all. */
typedef struct { SegHost *h; int nparts; char *lastbuf; size_t lastsz; } ZipScan;

static int zip_visit(void *ctx, int part, const char *path)
{
    ZipScan *s = (ZipScan *)ctx;
    if (part == UNC_SEG_NAME_LAST) {
        if (s->lastbuf && s->lastsz) snprintf(s->lastbuf, s->lastsz, "%s", path);
        part = s->nparts;
        if (part < 1) return 0;          /* count not established yet */
    }
    seg_record(s->h, part, path);
    return 0;
}

static void seg_scan_zip_family(SegHost *h, const char *anchor, int nparts,
                                char *lastbuf, size_t lastsz)
{
    Family f;
    ZipScan s;

    if (lastbuf && lastsz) lastbuf[0] = 0;
    if (!family_of(&f, anchor, UNC_FORMAT_ZIPSEG)) return;
    s.h = h;
    s.nparts = nparts;
    s.lastbuf = lastbuf;
    s.lastsz = lastsz;
    family_scan(&f, zip_visit, &s);
}

/* ------------------------------------------------------------------ */
/* Plain NAME.001 splits: the scheme IS the filename                    */
/*                                                                    */
/* (Source: reference/XADMaster/XADSplitFileParser.m. Its              */
/* +recognizeFileWithHandle: requires the sibling to exist — .001      */
/* looks for .002, any other part looks for .001 — and its             */
/* +volumesForHandle: scans the directory for the family; the name     */
/* rule itself is unc_segment_name_part's.)                            */
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

/* What makes this file a segment rather than a file whose name happens
 * to end in three digits: another member of its family is there.
 *
 * The reference asks for one SPECIFIC sibling (.001 looks for .002, and
 * everything else for .001), which means a set whose .002 is the
 * missing one is not recognized as a set at all and the user is told
 * the format is unknown — with the .003 sitting right beside it. Any
 * other member will do here, so that case reaches the part-numbering
 * checks below and is reported as the missing part it is. */
typedef struct { int self, found; } SplitPresent;

static int present_visit(void *ctx, int part, const char *path)
{
    SplitPresent *s = (SplitPresent *)ctx;
    (void)path;
    if (part == s->self) return 0;
    s->found = 1;
    return 1;
}

static int split_family_present(const char *path)
{
    Family f;
    SplitPresent s;

    s.self = family_of(&f, path, UNC_FORMAT_SPLIT);
    s.found = 0;
    if (s.self < 1) return 0;
    family_scan(&f, present_visit, &s);
    return s.found;
}

/* Was another member of this family handed over with --part? That is
 * the second way a set proves it is one, and the only way when the
 * parts were collected from different directories. */
static int split_part_offered(const char *path, const char *const *args,
                              int n)
{
    Family f;
    int self = family_of(&f, path, UNC_FORMAT_SPLIT), i;

    if (self < 1) return 0;
    for (i = 0; i < n; i++) {
        const char *slash = strrchr(args[i], '/');
        int p = family_member(&f, slash ? slash + 1 : args[i]);
        if (p >= 1 && p != self) return 1;
    }
    return 0;
}

/* Record every member of the family in the anchor's directory.
 * Returns the highest part number SEEN, including numbers too large to
 * record, so the caller can tell a 300-part set from a 256-part one. */
typedef struct { SegHost *h; int highest; } SplitScan;

static int split_visit(void *ctx, int part, const char *path)
{
    SplitScan *s = (SplitScan *)ctx;
    if (part > s->highest) s->highest = part;
    seg_record(s->h, part, path);
    return 0;
}

static int seg_scan_split_family(SegHost *h, const char *anchor)
{
    Family f;
    SplitScan s;

    if (family_of(&f, anchor, UNC_FORMAT_SPLIT) < 1) return 0;
    s.h = h;
    s.highest = 0;
    family_scan(&f, split_visit, &s);
    return s.highest;
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
    char line[PATHBUF];

    for (;;) {
        size_t n;
        int got;
        if (h->desc.scheme == UNC_FORMAT_SPLIT && h->desc.nparts == 0 &&
            part > h->highest)
            fprintf(stderr, "macextract: part %d of \"%s\", if the set has "
                            "one (path, or empty if it ends here): ",
                    part, h->desc.name);
        else
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
    /* An open-ended split (--ask; macextract.h, UNC_SEG_ENDS), as the Mac
     * shell does it: below the highest number seen, a part not found is
     * a gap, asked for like any missing part. Past it, the set may go on
     * after .001, or after a part as long as the one before it (a cutter
     * cuts fixed pieces and the remainder goes last): then it is asked
     * for, and an empty answer says the set ends there. After a shorter
     * part it ends without a question. */
    if (h->desc.scheme == UNC_FORMAT_SPLIT && h->desc.nparts == 0 &&
        !h->path[part]) {
        if (part > h->highest &&
            !(part == 2 || (h->path[part - 1] && h->path[part - 2] &&
                            seg_file_len(h, part - 1) ==
                            seg_file_len(h, part - 2))))
            return UNC_SEG_ENDS;
        if (!seg_ask(h, part))
            return part > h->highest ? UNC_SEG_ENDS : UNC_ERR_SEGMENTED;
        {   int hi = seg_scan_split_family(h, h->path[part]);
            if (part > h->highest) h->highest = part;
            if (hi > h->highest) h->highest = hi; }
    }
    if (!h->path[part] && h->ask && !seg_ask(h, part)) return UNC_ERR_SEGMENTED;
    if (!h->path[part]) return UNC_ERR_SEGMENTED;
    if (h->sink) sink_note_reading(h->sink, h->path[part]);

    f = fopen(h->path[part], "rb");
    if (!f) return UNC_ERR_SEGMENTED;
    h->open_io.f = f;
    h->open_io.size = stat(h->path[part], &st) == 0
                    ? (unc_off_t)seg_file_len(h, part) : UNC_OFF_UNKNOWN;
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

    (void)desc;
    if (part < 1 || part > UNC_SEG_MAX_PARTS || !h->path[part])
        return UNC_SIZE_UNKNOWN;
    return seg_file_len(h, part);
}

/* ------------------------------------------------------------------ */
/* main                                                               */
/* ------------------------------------------------------------------ */

static UncFormat format_by_name(const char *s)
{
    UncFormat f;
    /* Not the retired slots, whose name is "unknown" too. */
    for (f = (UncFormat)1; f < UNC_FORMAT__COUNT; f++)
        if (unc_format_extractable(f) &&
            strcmp(unc_format_name(f), s) == 0) return f;
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

/* --budget: decimal digits, then optionally K, M or G (powers of 1024),
 * and nothing else; the result must fit the allocator's uint32_t. Until
 * 2026-11-07 this was strtoul with no end or range check: "1M" was one
 * byte, "lots" no cap at all, and 4G wrapped to none (DECISIONS.md
 * 2026-11-07, *the budget that took anything*). Returns 0 or -1. */
static int parse_budget(const char *s, uint32_t *out)
{
    unsigned long long v = 0, mul = 1;
    const char *p = s;

    if (*p < '0' || *p > '9') return -1;
    for (; *p >= '0' && *p <= '9'; p++) {
        v = v * 10u + (unsigned)(*p - '0');
        if (v > 0xFFFFFFFFull) return -1;
    }
    if (*p == 'K' || *p == 'k') mul = 1024u;
    else if (*p == 'M' || *p == 'm') mul = 1024u * 1024u;
    else if (*p == 'G' || *p == 'g') mul = 1024u * 1024u * 1024u;
    if (mul != 1) p++;
    if (*p) return -1;
    if (v > 0xFFFFFFFFull / mul) return -1;
    *out = (uint32_t)(v * mul);
    return 0;
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
        "  --budget <N>   allocation cap in bytes; K, M or G multiplies\n"
        "                 by 1024, 1024^2, 1024^3 (under 4G). 0: no cap\n"
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
        "  --finder       with l, the Finder metadata as hex — type,\n"
        "                 creator, flags — in place of the four-character\n"
        "                 columns, which a parser cannot read back when a\n"
        "                 code holds a space or a NUL\n"
        "  --meta         with l, the rest of the Finder metadata as hex —\n"
        "                 FInfo, FXInfo, backup date, lock, comment — one\n"
        "                 'm' row per entry, '-' where the archive is silent;\n"
        "                 then a 't' row: created, modified, in Mac seconds\n"
        "  -v             verbose\n"
        "  --version      print the version and exit\n");
}

/* ------------------------------------------------------------------ */
/* The run: the command line, read once, and one layer at a time       */
/*                                                                    */
/* A file the user names is often an envelope around the archive      */
/* (.sit.hqx, .cpt.bin, .tar.Z), so a run is a chain of layers: each   */
/* extracts its file, and when it yields one file that is itself      */
/* something, the next layer extracts that in place. What one layer   */
/* hands the next is LayerState, and every rule about it is a named   */
/* function below; everything else a layer builds is its own.         */
/* ------------------------------------------------------------------ */

/* The parsed command line. Read-only once parse_args has returned. */
typedef struct {
    const char *cmd;            /* l, x, t or sniff                      */
    const char *file;           /* the file named on the command line    */
    const char *outdir;
    const char *force;          /* -f: the FIRST layer's format          */
    const char *presetfile, *password;
    const char *partargs[UNC_SEG_MAX_PARTS];
    int         nparts;
    const char *only[ONLY_MAX];
    int         nonly;
    uint32_t    budget;
    int raw_names, verbose, stats, hidden_forks, overwrite, show_finder,
        show_meta, no_comment, no_recurse, no_parts, ask;
    mode_t      file_mode;      /* 0666 less the umask, read once */
} CliArgs;

/* What one layer hands the next. */
typedef struct {
    char     curfile[PATHBUF];  /* this layer's input                    */
    char     delfile[PATHBUF];  /* the previous layer's output, "" on
                                 * the first: deleted once this layer
                                 * has extracted cleanly                 */
    char     delrsrc[PATHBUF];  /* its sidecar, only if that layer wrote
                                 * one; "" otherwise                     */
    int      depth;             /* 0 for the command line's file         */
    ReadList kept;              /* files read that this run did not write */
    unsigned char only_hit[ONLY_MAX];   /* --only: judged once, at the end */
    uint8_t *longname;          /* one buffer for every layer; freed at
                                 * exit by the OS                        */
    char     pwbuf[UNC_PASSWORD_MAX + 2];   /* `-p -`, read once per run */
    int      pw_read;
} LayerState;

/* One layer's own plumbing: the engine's callbacks and what they hold. */
typedef struct {
    const char *file;           /* LayerState.curfile */
    FileIO      fio;
    UncIO       io;
    BudgetAlloc ba;
    UncAlloc    al;
    DiskSink    sink;
    UncSink     sk;
    UncProgress prog;
    UncOptions  opt;
    UncPasswordSource pwsrc;
    UncFormat   fmt;
    int         ret;            /* what the engine returned */
} Layer;

/* run_layer's answer when the chain goes on. */
#define LAYER_NEXT (-1)

static void fio_bind(UncIO *io, FileIO *f)
{
    io->ctx = f;
    io->read = fio_read;
    io->seek = fio_seek;
    io->tell = fio_tell;
    io->size = fio_size;
}

/* Parse argv into `a`. Returns LAYER_NEXT to run, or the exit code. */
static int parse_args(int argc, char **argv, CliArgs *a)
{
    int i;
    mode_t m;

    memset(a, 0, sizeof *a);
    a->outdir = ".";
    m = umask(0);
    umask(m);
    a->file_mode = 0666 & ~m;

    if (argc >= 2 && (strcmp(argv[1], "--version") == 0 ||
                      strcmp(argv[1], "-V") == 0)) {
        printf("macextract %s\n", UNC_VERSION);
        /* Derived from the type, not declared: the ceiling a build
         * actually has is the one a test should grade it against. */
        printf("container offsets: %d-bit\n",
               (int)(sizeof(unc_off_t) * 8));
        return 0;
    }
    if (argc < 3) { usage(); return 2; }
    a->cmd = argv[1];

    for (i = 2; i < argc; i++) {
        if (strcmp(argv[i], "-o") == 0 && i + 1 < argc) a->outdir = argv[++i];
        else if (strcmp(argv[i], "--budget") == 0 && i + 1 < argc) {
            if (parse_budget(argv[++i], &a->budget) != 0) {
                fprintf(stderr, "macextract: --budget %s: not a byte count "
                        "(digits, then K, M or G at most, under 4G)\n",
                        argv[i]);
                usage();
                return 2;
            }
        }
        else if (strcmp(argv[i], "--raw-names") == 0) a->raw_names = 1;
        else if (strcmp(argv[i], "--forks") == 0 && i + 1 < argc) {
            const char *k = argv[++i];
            if (strcmp(k, "hidden") == 0) a->hidden_forks = 1;
            else if (strcmp(k, "visible") == 0) a->hidden_forks = 0;
            else { usage(); return 2; }
        }
        else if (strcmp(argv[i], "--overwrite") == 0) a->overwrite = 1;
        else if (strcmp(argv[i], "-nr") == 0) a->no_recurse = 1;
        else if (strcmp(argv[i], "--part") == 0 && i + 1 < argc) {
            if (a->nparts < UNC_SEG_MAX_PARTS) a->partargs[a->nparts++] = argv[++i];
            else { fprintf(stderr, "macextract: too many --part\n"); return 2; }
        }
        else if (strcmp(argv[i], "--only") == 0 && i + 1 < argc) {
            if (a->nonly < ONLY_MAX) a->only[a->nonly++] = argv[++i];
            else { fprintf(stderr, "macextract: too many --only\n"); return 2; }
        }
        else if (strcmp(argv[i], "--no-parts") == 0) a->no_parts = 1;
        else if (strcmp(argv[i], "--ask") == 0) a->ask = 1;
        else if (strcmp(argv[i], "--preset") == 0 && i + 1 < argc)
            a->presetfile = argv[++i];
        else if (strcmp(argv[i], "-p") == 0 && i + 1 < argc) a->password = argv[++i];
        else if (strcmp(argv[i], "--no-comment") == 0) a->no_comment = 1;
        else if (strcmp(argv[i], "--stats") == 0) a->stats = 1;
        else if (strcmp(argv[i], "-f") == 0 && i + 1 < argc) a->force = argv[++i];
        else if (strcmp(argv[i], "--finder") == 0) a->show_finder = 1;
        else if (strcmp(argv[i], "--meta") == 0) a->show_meta = 1;
        else if (strcmp(argv[i], "-v") == 0) a->verbose = 1;
        else if (argv[i][0] == '-') { usage(); return 2; }
        else a->file = argv[i];
    }
    if (!a->file) { usage(); return 2; }
    return LAYER_NEXT;
}

/* ---- the rules one layer hands the next ---------------------------- */

/* The first layer reads the command line's file; the rest start empty. */
static int st_init(LayerState *st, const CliArgs *a)
{
    memset(st, 0, sizeof *st);
    if ((size_t)snprintf(st->curfile, sizeof st->curfile, "%s", a->file)
        >= sizeof st->curfile) {
        fprintf(stderr, "macextract: %s: path too long\n", a->file);
        return 1;
    }
    return 0;
}

/* -f names the first layer's format only: what it holds is sniffed. */
static const char *st_forced(const CliArgs *a, const LayerState *st)
{
    return st->depth == 0 ? a->force : NULL;
}

/* --only filters a layer as it is walked, unless the layer may unwrap:
 * then it is written whole, and its entries judged once it turns out to
 * be the last (DiskSink.only_late). `l` and `t` never unwrap, so for
 * them an envelope's single entry IS the listing. */
static int st_only_now(const CliArgs *a, UncFormat fmt)
{
    return !(strcmp(a->cmd, "x") == 0 && !a->no_recurse && layer_unwraps(fmt));
}

/* What may not be written over: this layer's input, and every file an
 * earlier layer read that this run did not write. The previous layer's
 * own output (delfile) is not one: a write onto it is deferred until it
 * is deleted (sink_open_fork). */
static void st_protect(LayerState *st, DiskSink *s)
{
    s->unwrap_src = st->delfile;   /* "" until a layer is being unwrapped */
    s->unwrap_rsrc = st->delrsrc;
    s->reading = st->kept;
    read_add(&s->reading, st->curfile);
    if (st->depth == 0) read_add(&st->kept, st->curfile);
}

/* A part of a set this layer joins is read, and is the user's unless
 * this run decoded it into the peel folder. */
static void st_protect_part(LayerState *st, DiskSink *s, const char *path,
                            int peeled)
{
    read_add(&s->reading, path);
    if (!peeled) read_add(&st->kept, path);
}

/* What may be deleted: the previous layer's output and the sidecar it
 * wrote, once this layer has extracted cleanly; a write deferred beside
 * either is then renamed onto it. */
static void st_drop_previous(LayerState *st, const DiskSink *s)
{
    char tmp[PATHBUF + sizeof DEFER_SUFFIX];
    const char *was[2];
    int k;
    if (!st->delfile[0]) return;
    was[0] = st->delfile;
    was[1] = st->delrsrc;
    remove(st->delfile);
    if (st->delrsrc[0]) remove(st->delrsrc);
    /* sink_open_fork deferred only a path that fit with the suffix,
     * so a cut here would be a bug; it is skipped rather than renaming
     * a file nobody wrote. */
    for (k = 0; k < 2; k++)
        if (s->deferred[k] &&
            (size_t)snprintf(tmp, sizeof tmp, "%s" DEFER_SUFFIX, was[k])
                < sizeof tmp)
            rename(tmp, was[k]);
    st->delfile[0] = 0;
    st->delrsrc[0] = 0;
}

/* When the chain goes on: `x` without -nr, under the depth cap, on a
 * layer that may unwrap and yielded one file and no folder, not an
 * application, whose bytes sniff as a format. Asked once a deferred
 * write has been renamed into place: before, the path still held the
 * envelope's bytes. Returns the next format, or UNC_FORMAT_UNKNOWN. */
static UncFormat st_next_format(const CliArgs *a, const LayerState *st,
                                UncFormat fmt, const DiskSink *s)
{
    UncFormat next = UNC_FORMAT_UNKNOWN;
    FILE *pf;
    if (strcmp(a->cmd, "x") != 0 || a->no_recurse || st->depth >= 8 ||
        !layer_unwraps(fmt) ||
        s->file_count != 1 || s->dir_count != 0 || !s->last_ok_path[0] ||
        /* An application is where the chain stops, whatever its data
         * fork holds: an installer or a self-extracting archive is run,
         * and what it installs is not what its data fork extracts to
         * (DECISIONS.md 2026-10-16, *the installer that was a layer*).
         * unar stops there too. */
        s->last_ok_type == 0x4150504CUL /* 'APPL' */)
        return next;
    pf = fopen(s->last_ok_at, "rb");
    if (pf) {
        FileIO pio_f;
        UncIO pio;
        struct stat pst;
        memset(&pio_f, 0, sizeof pio_f);
        pio_f.f = pf;
        pio_f.size = stat(s->last_ok_at, &pst) == 0
                     ? (unc_off_t)pst.st_size : UNC_OFF_UNKNOWN;
        fio_bind(&pio, &pio_f);
        next = unc_sniff(&pio);
        fclose(pf);
    }
    return next;
}

/* Hand the next layer its input: the one file this layer wrote, which
 * is also what it may delete once that layer has extracted cleanly. */
static void st_advance(LayerState *st, const DiskSink *s)
{
    snprintf(st->delfile, sizeof st->delfile, "%s", s->last_ok_path);
    snprintf(st->delrsrc, sizeof st->delrsrc, "%s", s->last_ok_rsrc);
    snprintf(st->curfile, sizeof st->curfile, "%s", s->last_ok_path);
    st->depth++;
}

/* ---- one layer ------------------------------------------------------ */

static void layer_sink(const CliArgs *a, LayerState *st, Layer *L)
{
    DiskSink *s = &L->sink;
    memset(s, 0, sizeof *s);
    s->outdir = a->outdir;
    /* What this filesystem takes, asked rather than assumed: ext4 gives
     * 255 and 4096, but eCryptfs gives 143 and a FAT volume less
     * again. The fallbacks are POSIX's minimums where pathconf will not
     * say (it returns -1 with errno unset for "no limit"). */
    s->fs_name_max = pathconf(a->outdir, _PC_NAME_MAX);
    if (s->fs_name_max <= 0 || s->fs_name_max > 255) s->fs_name_max = 255;
    s->fs_path_max = pathconf(a->outdir, _PC_PATH_MAX);
    if (s->fs_path_max <= 0 || s->fs_path_max > PATHBUF - 8)
        s->fs_path_max = PATHBUF - 8;
    s->archive = L->file;
    s->no_comment = a->no_comment;
    s->raw_names = a->raw_names;
    s->hidden_forks = a->hidden_forks;
    s->overwrite = a->overwrite;
    st_protect(st, s);
    s->file_mode = a->file_mode;
    s->verbose = a->verbose;
    s->show_finder = a->show_finder;
    s->show_meta = a->show_meta;

    L->sk.ctx = s;
    L->sk.begin_entry = sink_begin;
    L->sk.write = sink_write;
    L->sk.end_entry = sink_end;
    L->sk.comment = sink_comment;
    L->prog.ctx = NULL;
    L->prog.tick = prog_tick;
}

/* The options that do not depend on the format: the long-name buffer,
 * the password, the archive's 'MKey'. Returns 0, or the exit code. */
static int layer_options(const CliArgs *a, LayerState *st, Layer *L)
{
    static uint8_t mkeybuf[8];
    UncOptions *opt = &L->opt;

    memset(opt, 0, sizeof *opt);
    /* Somewhere for a name the engine cannot carry. It is only ever
     * shown, never written, so the size is the largest a format can
     * state rather than anything the filesystem has to say about it.
     * A run without it loses the text and keeps the length. */
    if (!st->longname) st->longname = (uint8_t *)malloc(UNC_LONGNAME_CAP);
    opt->long_name = st->longname;
    opt->long_name_cap = st->longname ? UNC_LONGNAME_CAP : 0;
    L->sink.long_name = st->longname;

    /* A password given on the command line, or read from stdin once so
     * that it does not sit in the process table. */
    if (a->password) {
        if (strcmp(a->password, "-") == 0) {
            /* Once per run, not per layer: a second read meets end of
             * file, and an archive inside an envelope was then opened
             * with no password at all (DECISIONS.md 2026-11-08, *the
             * password the second layer never got*). */
            size_t n;
            if (!st->pw_read) {
                if (!fgets(st->pwbuf, (int)sizeof st->pwbuf, stdin))
                    st->pwbuf[0] = 0;
                n = strlen(st->pwbuf);
                while (n > 0 && (st->pwbuf[n - 1] == '\n' ||
                                 st->pwbuf[n - 1] == '\r'))
                    st->pwbuf[--n] = 0;
                st->pw_read = 1;
            }
            n = strlen(st->pwbuf);
            opt->password = (const uint8_t *)st->pwbuf;
            opt->password_len = (uint16_t)n;
        } else {
            size_t n = strlen(a->password);
            if (n > UNC_PASSWORD_MAX) {
                /* Truncating it silently would report "wrong password"
                 * for a password the user typed correctly. */
                fprintf(stderr, "macextract: password is longer than %d bytes, "
                                "which no format here uses\n", UNC_PASSWORD_MAX);
                return 1;
            }
            opt->password = (const uint8_t *)a->password;
            opt->password_len = (uint16_t)n;
        }
    } else if (a->ask) {
        L->pwsrc.ctx = NULL;
        L->pwsrc.ask = cli_ask_password;
        opt->ask = &L->pwsrc;
    }

    /* The archive's own resource fork, if this machine has it beside
     * the data fork: the one piece of key material a .sit does not
     * carry in its stream. */
    if (load_mkey(L->file, a->hidden_forks, mkeybuf)) opt->mkey = mkeybuf;
    else opt->mkey = NULL;
    return 0;
}

/* What this layer is: -f, or the sniff and the naming rules. Returns 0,
 * or the exit code. */
static int layer_format(const CliArgs *a, const LayerState *st, Layer *L)
{
    const char *force = st_forced(a, st);
    const char *file = L->file;

    if (force) {
        L->fmt = format_by_name(force);
        if (L->fmt == UNC_FORMAT_UNKNOWN) {
            fprintf(stderr, "macextract: unknown format '%s'\n", force);
            return 2;
        }
        return 0;
    }
    L->fmt = unc_sniff(&L->io);

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
    if (!a->no_parts && L->fmt != UNC_FORMAT_DDSEG &&
        (split_family_present(file) ||
         split_part_offered(file, a->partargs, a->nparts) ||
         /* --ask: a NAME.001 alone is the first of a set whose
          * other parts the user is standing by to produce, as when
          * each part is on a floppy of its own. */
         (a->ask && own_part(UNC_FORMAT_SPLIT, file) == 1)))
        L->fmt = UNC_FORMAT_SPLIT;
    /* A spanned zip's middle part has nothing to recognise it by but
     * its name, NAME.zNN (the first carries the spanning signature,
     * the last the directory). Placed by name, as every other part of
     * the set already is when it is opened from the .zip, and as the
     * Mac shell does: the engine's structural check on the assembled
     * set is what keeps a wrong file out, whichever part was opened. */
    if (!a->no_parts && L->fmt == UNC_FORMAT_UNKNOWN &&
        own_part(UNC_FORMAT_ZIPSEG, file) >= 1)
        L->fmt = UNC_FORMAT_ZIPSEG;
    return 0;
}

/* Name hint for name-less formats (gzip, .Z): archive basename minus
 * its last extension, unar-style. */
static void layer_name_hint(Layer *L)
{
    const char *base = strrchr(L->file, '/');
    const char *dot;
    base = base ? base + 1 : L->file;
    dot = strrchr(base, '.');
    /* SpaceSaver compresses a file in place and adds no extension,
     * so the whole basename is the name — stripping one here would
     * eat a real ".txt". */
    if (L->fmt == UNC_FORMAT_SPACESAVER) dot = NULL;
    L->opt.name_hint = (const uint8_t *)base;
    L->opt.name_hint_len = (uint16_t)(dot && dot != base ? (size_t)(dot - base)
                                                         : strlen(base));
}

/* SpaceSaver's window starts loaded with a dictionary that ships inside
 * SpaceSaver itself; without it, entries fail rather than decode to
 * something wrong. Returns 0, or the exit code. */
static int layer_preset(const CliArgs *a, Layer *L)
{
    /* SpaceSaver's preset dictionary is 9,679 bytes; this is the ceiling
     * on what --preset will read, not a size anybody declared. Static
     * rather than malloc: the engine holds this pointer for the whole
     * layer, and a heap buffer would need freeing on every return —
     * which is how the sanitizer build first met this option. */
    static uint8_t presetbuf[64 * 1024];
    FILE *pf;
    long n;

    if (!a->presetfile) return 0;
    pf = fopen(a->presetfile, "rb");
    if (!pf) {
        fprintf(stderr, "macextract: %s: %s\n", a->presetfile, strerror(errno));
        return 1;
    }
    if (fseek(pf, 0, SEEK_END) != 0 || (n = ftell(pf)) < 0 ||
        fseek(pf, 0, SEEK_SET) != 0) n = -1;
    if (n > 0 && n <= (long)sizeof presetbuf &&
        fread(presetbuf, 1, (size_t)n, pf) == (size_t)n) {
        L->opt.preset = presetbuf;
        L->opt.preset_len = (uint32_t)n;
    } else {
        n = -1;
    }
    fclose(pf);
    if (n <= 0) {
        fprintf(stderr, "macextract: %s: not a usable preset\n", a->presetfile);
        return 1;
    }
    return 0;
}

static int is_segmented(UncFormat f)
{
    return f == UNC_FORMAT_SITSEG || f == UNC_FORMAT_ZIPSEG ||
           f == UNC_FORMAT_SPLIT || f == UNC_FORMAT_CPTSEG ||
           f == UNC_FORMAT_DDSEG || f == UNC_FORMAT_MIMESEG;
}

/* ---- a set of parts: one setup per scheme, each returning 0 or the
 * exit code, with `seg` holding the descriptor and the parts found ---- */

/* A plain split. Nothing in these files says anything, so the
 * descriptor is built here: the set is the consecutive run of NAME.NNN
 * in one directory, and the joined file is called NAME. */
static int seg_setup_split(const CliArgs *a, Layer *L, SegHost *seg)
{
    const char *file = L->file;
    Family fam;
    const char *stem;
    size_t stemlen;
    int i, self, highest, beyond = 0, run;

    self = family_of(&fam, file, UNC_FORMAT_SPLIT);
    stem = fam.stem;
    stemlen = fam.stemlen;
    if (self < 1) {
        fprintf(stderr, "macextract: %s: not a NAME.NNN part\n", file);
        return 1;
    }
    seg->desc.scheme   = UNC_FORMAT_SPLIT;
    seg->desc.part     = (uint16_t)self;
    seg->desc.head_len = 0;
    seg->desc.total    = UNC_SIZE_UNKNOWN;   /* the engine sums it */
    if (stemlen > UNC_NAME_MAX) stemlen = UNC_NAME_MAX;
    memcpy(seg->desc.name, stem, stemlen);
    seg->desc.name[stemlen] = 0;
    seg->desc.name_len = (uint16_t)stemlen;

    highest = seg_scan_split_family(seg, file);
    for (i = 0; i < a->nparts; i++) {
        int p = own_part(UNC_FORMAT_SPLIT, a->partargs[i]);
        if (p >= 1) {
            if (p > highest) highest = p;
            seg_record(seg, p, a->partargs[i]);
        } else {
            fprintf(stderr, "macextract: %s: no .NNN extension to "
                    "place it by, ignored\n", a->partargs[i]);
        }
    }

    run = split_run_length(seg, &beyond);
    if (highest > UNC_SEG_MAX_PARTS) {
        /* Says what was SEEN, not what it means: three digits
         * reach 999 and a member numbered past our ceiling is
         * either a set too big to read or a stray file, and
         * nothing here can tell which. */
        fprintf(stderr, "macextract: \"%s\": a part numbered %d is "
                "beside it, and this reads at most %d parts\n",
                seg->desc.name, highest, UNC_SEG_MAX_PARTS);
        return 1;
    }
    if (run < 1) {
        fprintf(stderr, "macextract: %s: part 1 of \"%s\" is not "
                "beside it\n", file, seg->desc.name);
        return 1;
    }
    /* With --ask the set is OPEN-ENDED, as on the Mac: the joiner
     * asks for each next part as it gets there, and seg_need asks
     * the user whether there is one; a gap is asked for there
     * too. Nothing about the set's end is settled here. */
    if (a->ask) {
        seg->highest = highest;
        seg->desc.nparts = 0;
        return 0;
    }
    /* Something numbered past the end of the run says a part in
     * between is missing. Refused: without --ask nobody is standing
     * by to produce it. */
    if (beyond) {
        fprintf(stderr, "macextract: part %d of \"%s\" is missing "
                "(a later part is there)\n", run + 1, seg->desc.name);
        return 1;
    }

    /* Gaps are resolved HERE rather than one disk at a time,
     * which is what the volume source does for the other two
     * schemes. A split states its length nowhere, so the joined
     * size is the sum of the parts' — and that has to be known
     * before the first byte is written, since it is the size
     * the one emitted entry announces. Without --ask, a gap is
     * an error. */
    for (i = 1; i <= run; i++) {
        if (seg->path[i]) continue;
        fprintf(stderr, "macextract: part %d of \"%s\" is "
                "missing\n", i, seg->desc.name);
        return 1;
    }
    seg->desc.nparts = (uint16_t)run;
    if (a->verbose)
        fprintf(stderr, "%s: %d parts\n", seg->desc.name, run);
    return 0;
}

/* A Compact Pro set. Every segment carries the set's identity, so
 * discovery is by CONTENT exactly as it is for StuffIt — a set whose
 * parts are scattered and named unlike each other works, and the
 * author's manual says as much ("the names of the files are not
 * important"). What is special is that only the FINAL segment says how
 * many there are, by being the one that carries the index. So: identify
 * the set from whatever part we were given, collect the rest, then take
 * the count from the final one. */
static int seg_setup_cpt(const CliArgs *a, Layer *L, SegHost *seg)
{
    const char *file = L->file;
    int i, i2, fin = 0;
    char dirbuf[PATHBUF];
    const char *base;

    if (unc_segment_describe(&L->io, &seg->desc) != UNC_OK) {
        fprintf(stderr, "macextract: %s: not a readable segment "
                "header\n", file);
        return 1;
    }
    seg_record(seg, (int)seg->desc.part, file);
    for (i = 0; i < a->nparts; i++) {
        int p = seg_part_of(seg, a->partargs[i]);
        if (p) seg_record(seg, p, a->partargs[i]);
        else fprintf(stderr, "macextract: %s: not a segment of this "
                     "set, ignored\n", a->partargs[i]);
    }
    seg_scan_dir(seg, file, 0);

    /* Which of them is the last? The one whose header names an
     * index. Asking each is an 8-byte read, and it is the only
     * way round: nothing else in the set states the count. */
    if (seg->desc.nparts == 0) {
        for (i2 = 1; i2 <= UNC_SEG_MAX_PARTS && !fin; i2++) {
            UncSegmentDesc cand;
            FILE *cf;
            FileIO cio_f;
            UncIO cio;
            struct stat cst;
            if (!seg->path[i2]) continue;
            cf = fopen(seg->path[i2], "rb");
            if (!cf) continue;
            memset(&cio_f, 0, sizeof cio_f);
            cio_f.f = cf;
            cio_f.size = stat(seg->path[i2], &cst) == 0
                         ? (unc_off_t)cst.st_size : UNC_OFF_UNKNOWN;
            fio_bind(&cio, &cio_f);
            if (unc_segment_describe(&cio, &cand) == UNC_OK &&
                cand.nparts)
                { seg->desc = cand; fin = i2; }
            fclose(cf);
        }
        if (!fin) {
            fprintf(stderr, "macextract: %s: this is one segment of a "
                    "Compact Pro set; the last segment, the one "
                    "holding the index, is not beside it\n", file);
            return 1;
        }
    }

    /* Now that the count is known, every part is re-checked
     * against the full rule: a middle segment must not carry an
     * index and the last one must, which is more than the
     * identity alone could ask (fmt_cptseg.c). */
    for (i2 = 1; i2 <= UNC_SEG_MAX_PARTS; i2++) {
        if (!seg->path[i2]) continue;
        if (seg_part_of(seg, seg->path[i2]) == i2) continue;
        if (a->verbose)
            fprintf(stderr, "part %d: %s no longer matches the set, "
                    "dropped\n", i2, seg->path[i2]);
        free(seg->path[i2]);
        seg->path[i2] = NULL;
    }

    /* The format stores no name for the original archive, so
     * the prompt borrows the opened file's, for display only. */
    base = strrchr(file, '/');
    base = base ? base + 1 : file;
    snprintf(dirbuf, sizeof dirbuf, "%s", base);
    {
        size_t n = strlen(dirbuf);
        if (n > UNC_NAME_MAX) n = UNC_NAME_MAX;
        memcpy(seg->desc.name, dirbuf, n);
        seg->desc.name[n] = 0;
        seg->desc.name_len = (uint16_t)n;
    }
    return 0;
}

/* A spanned zip. Only the LAST part carries the part count, so it has
 * to be found before anything else can be — and for this scheme
 * "found" means "named .zip in the same folder". */
static int seg_setup_zip(const CliArgs *a, Layer *L, SegHost *seg)
{
    const char *file = L->file;
    char lastpath[PATHBUF];
    Family fam;
    const char *stem;
    size_t stemlen;
    FILE *lf;
    FileIO lio_f;
    UncIO lio;
    struct stat lst;
    int i, derr;

    seg_scan_zip_family(seg, file, 0, lastpath, sizeof lastpath);
    if (!lastpath[0]) {
        fprintf(stderr, "macextract: %s: this is one part of a spanned "
                "zip; the last part (named .zip) is not beside it\n",
                file);
        return 1;
    }
    lf = fopen(lastpath, "rb");
    if (!lf) {
        fprintf(stderr, "macextract: %s: %s\n", lastpath,
                strerror(errno));
        return 1;
    }
    memset(&lio_f, 0, sizeof lio_f);
    lio_f.f = lf;
    lio_f.size = stat(lastpath, &lst) == 0 ? (unc_off_t)lst.st_size
                                           : UNC_OFF_UNKNOWN;
    fio_bind(&lio, &lio_f);
    derr = unc_segment_describe(&lio, &seg->desc);
    fclose(lf);
    if (derr != UNC_OK) {
        fprintf(stderr, "macextract: %s: %s\n", lastpath,
                unc_strerror(derr));
        return 1;
    }
    seg_record(seg, (int)seg->desc.nparts, lastpath);

    /* The engine has no filename to put in a prompt, because the
     * format stores none. Borrow the family's stem for display. */
    if (family_of(&fam, file, UNC_FORMAT_ZIPSEG)) {
        stem = fam.stem;
        stemlen = fam.stemlen;
        if (stemlen > UNC_NAME_MAX) stemlen = UNC_NAME_MAX;
        memcpy(seg->desc.name, stem, stemlen);
        seg->desc.name[stemlen] = 0;
        seg->desc.name_len = (uint16_t)stemlen;
    }

    for (i = 0; i < a->nparts; i++) {
        int p = own_part(UNC_FORMAT_ZIPSEG, a->partargs[i]);
        if (p == UNC_SEG_NAME_LAST) p = (int)seg->desc.nparts;
        if (p) seg_record(seg, p, a->partargs[i]);
        else fprintf(stderr, "macextract: %s: no .zNN or .zip "
                     "extension to place it by, ignored\n",
                     a->partargs[i]);
    }
    return 0;
}

/* A set whose parts identify themselves: StuffIt, DiskDoubler `SPLT`,
 * MIME message/partial. */
static int seg_setup_content(const CliArgs *a, const LayerState *st,
                             Layer *L, SegHost *seg)
{
    const char *file = L->file;
    int i;

    if (unc_segment_describe(&L->io, &seg->desc) != UNC_OK) {
        fprintf(stderr, "macextract: %s: not a readable segment header\n",
                file);
        return 1;
    }

    /* A `SPLT` part carries everything about the set except a
     * name for the file it joins into: DiskDoubler's Split does
     * not store one. The part's own filename is all there is,
     * minus the ".N" that numbers it — and because the parts
     * are matched by CONTENT, that name is for display and for
     * the output file, never evidence. */
    if (L->fmt == UNC_FORMAT_DDSEG || L->fmt == UNC_FORMAT_MIMESEG) {
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
        memcpy(seg->desc.name, base, n);
        seg->desc.name[n] = 0;
        seg->desc.name_len = (uint16_t)n;
    }

    /* The file we were handed is a part, and its own part number
     * comes from its header — so opening part 3 of a set works. */
    seg_record(seg, (int)seg->desc.part, file);
    for (i = 0; i < a->nparts; i++) {
        /* A part named by the user is worth unwrapping whether
         * or not anything else here is wrapped: it is one file,
         * and the user has said what it is. */
        int p = seg_part_of(seg, a->partargs[i]);
        if (p) seg_record(seg, p, a->partargs[i]);
        else if (!seg_wrapped_part_of(seg, a->partargs[i]))
            fprintf(stderr, "macextract: %s: not part of \"%s\", "
                    "ignored\n", a->partargs[i], seg->desc.name);
    }
    seg_scan_dir(seg, file, 0);
    /* A part that arrived wrapped was unwrapped into the OUTPUT
     * directory, so the rest of the set is not there: it is
     * still where the user left it. */
    if (st->depth > 0)
        seg_scan_dir(seg, a->file, 0);

    /* Only now, and only if something is still missing, is it
     * worth taking envelopes off to look — which is how a real
     * download arrives (Archive.sit.1.hqx) and also how a
     * half-unstuffed one does. Rationing it this way means a
     * set that is complete never opens a single file beside it,
     * and one that is short pays a hundred decoded bytes per
     * envelope rather than failing. */
    if (L->fmt == UNC_FORMAT_MIMESEG) {
        /* The count, from whichever part carries it, and then
         * the gap check the joiner would otherwise report as
         * "a part the host could not produce". No envelope
         * scan: nothing wraps one of these, and a wrapped part
         * would be a guess (see seg_wrapped_part_of). */
        int p;
        if (seg->desc.nparts == 0) {
            for (p = 1; p <= UNC_SEG_MAX_PARTS; p++) {
                int n2;
                if (!seg->path[p]) continue;
                n2 = mimeseg_nparts_of(seg->path[p]);
                if (n2 > 0) { seg->desc.nparts = (uint16_t)n2; break; }
            }
        }
        if (seg->desc.nparts == 0) {
            fprintf(stderr, "macextract: %s: no part of this set says "
                    "how many parts it has\n", file);
            return 1;
        }
        for (p = 1; p <= (int)seg->desc.nparts; p++) {
            if (seg->path[p]) continue;
            if (a->ask && seg_ask(seg, p)) continue;
            fprintf(stderr, "macextract: part %d of %d is missing\n",
                    p, (int)seg->desc.nparts);
            return 1;
        }
    } else if (!seg_have_all(seg)) {
        if (st->depth > 0)
            seg_scan_dir(seg, a->file, 1);
        seg_scan_dir(seg, file, 1);
    }
    return 0;
}

/* Join a set of parts and extract what it holds: L->ret is the
 * engine's answer. Returns 0 once the engine ran, or the exit code. */
static int layer_join(const CliArgs *a, LayerState *st, Layer *L)
{
    SegHost seg;
    UncVolumeSource vs;
    void *scratch;
    int i, code;

    memset(&seg, 0, sizeof seg);
    seg.ask = a->ask;
    seg.verbose = a->verbose;
    seg.outdir = a->outdir;
    seg.sink = &L->sink;

    if (L->fmt == UNC_FORMAT_SPLIT) code = seg_setup_split(a, L, &seg);
    else if (L->fmt == UNC_FORMAT_CPTSEG) code = seg_setup_cpt(a, L, &seg);
    else if (L->fmt == UNC_FORMAT_ZIPSEG) code = seg_setup_zip(a, L, &seg);
    else code = seg_setup_content(a, st, L, &seg);

    if (code == 0) {
        /* Every part the joiner may open is as much the input as the
         * file named: none of them may be written over mid-join. */
        for (i = 1; i <= UNC_SEG_MAX_PARTS; i++)
            if (seg.path[i])
                st_protect_part(st, &L->sink, seg.path[i], seg.peeled[i]);

        memset(&vs, 0, sizeof vs);   /* optional members are NULL ones */
        vs.ctx = &seg;
        vs.need = seg_need;
        vs.release = seg_release;
        vs.size = seg_size_of;

        scratch = malloc(unc_segment_scratch_size());
        if (!scratch) {
            fprintf(stderr, "macextract: out of memory\n");
            code = 1;
        } else {
            L->ret = unc_extract_segments(&seg.desc, &vs, scratch, &L->sk,
                                          &L->al, &L->prog, &L->opt);
            if (a->stats) {
                uint32_t sw = 0, back = 0;
                unc_segment_stats(scratch, &sw, &back);
                fprintf(stderr, "segments: %u part opens, %u of them "
                        "backward\n", sw, back);
            }
            free(scratch);
        }
    }
    seg_peel_clean(&seg);
    for (i = 1; i <= UNC_SEG_MAX_PARTS; i++) free(seg.path[i]);
    return code;
}

/* Everything up to and including the engine's run, on an open input.
 * Returns LAYER_NEXT once the engine ran (L->ret), or the exit code. */
static int layer_extract(const CliArgs *a, LayerState *st, Layer *L)
{
    int code;

    fio_bind(&L->io, &L->fio);
    memset(&L->ba, 0, sizeof L->ba);
    L->ba.budget = a->budget;
    L->al.ctx = &L->ba;
    L->al.alloc = ba_alloc;
    L->al.free = ba_free;
    layer_sink(a, st, L);

    if ((code = layer_options(a, st, L)) != 0) return code;
    if ((code = layer_format(a, st, L)) != 0) return code;

    if (a->nonly && st_only_now(a, L->fmt)) {
        L->sink.only     = a->only;
        L->sink.only_hit = st->only_hit;
        L->sink.nonly    = a->nonly;
    } else if (a->nonly) {
        L->sink.only_late = 1;
        L->sink.late_sel  = a->only;
        L->sink.late_nsel = a->nonly;
    }

    /* Mac formats carry MacRoman names; zip/tar/gzip do not — nor does
     * a split, whose entry is named after the host's own file. */
    switch (L->fmt) {
    case UNC_FORMAT_ZIP: case UNC_FORMAT_ZIPSEG: case UNC_FORMAT_TAR:
    case UNC_FORMAT_GZIP: case UNC_FORMAT_COMPRESS_Z: case UNC_FORMAT_SPLIT:
        L->sink.mac_encoding = 0; break;
    default:
        L->sink.mac_encoding = 1; break;
    }

    if (strcmp(a->cmd, "sniff") == 0) {
        printf("%s\n", unc_format_name(L->fmt));
        return L->fmt == UNC_FORMAT_UNKNOWN ? 1 : 0;
    }
    if (L->fmt == UNC_FORMAT_UNKNOWN) {
        fprintf(stderr, "macextract: %s: format not recognized\n", L->file);
        return 1;
    }
    layer_name_hint(L);
    if ((code = layer_preset(a, L)) != 0) return code;

    if (strcmp(a->cmd, "l") == 0) {
        L->opt.list_only = 1;
        L->sink.list_only = 1;
    } else if (strcmp(a->cmd, "t") == 0) {
        L->opt.test_only = 1;
        L->sink.test_only = 1;
    } else if (strcmp(a->cmd, "x") == 0) {
        mkdir(a->outdir, 0777);
    } else {
        usage();
        return 2;
    }

    if (a->verbose || strcmp(a->cmd, "l") == 0)
        fprintf(stderr, "%s: %s\n", L->file, unc_format_name(L->fmt));

    if (is_segmented(L->fmt) && !a->no_parts) {
        if ((code = layer_join(a, st, L)) != 0) return code;
    } else {
        L->ret = unc_extract_as(L->fmt, &L->io, &L->sk, &L->al, &L->prog,
                                &L->opt);
    }
    return LAYER_NEXT;
}

/* What a layer that ran says about its entries. Returns 0 if it
 * extracted cleanly, 1 if not. */
static int layer_verdict(const CliArgs *a, LayerState *st, Layer *L)
{
    DiskSink *s = &L->sink;
    int onlymiss = 0;

    if (L->ret != UNC_OK) {
        fprintf(stderr, "macextract: %s: %s\n", L->file, unc_strerror(L->ret));
        /* The names that were shortened are on the disk whatever the
         * WALK then did, so the notice that says where to find them is
         * owed on this path too — and it is what frees the list, which
         * this path leaked until 2026-10-03 (found by UBSan/ASan on a
         * mutated archive, TESTING.md, *Method 14*). */
        sink_report_cuts(s);
        sink_late_final(s, a->only, st->only_hit, a->nonly);
        return 1;
    }
    if (s->unsupported) {
        /* The one failure a user can do something about that is not
         * about their machine: this build cannot read that method YET,
         * and the file itself is what would fix that. Every method this
         * engine has ever added past the first came from somebody's
         * file — so ask for it, once, with the method named. */
        fprintf(stderr,
                "macextract: %d entr%s use%s a compression method this build "
                "cannot read yet.\n",
                s->unsupported, s->unsupported == 1 ? "y" : "ies",
                s->unsupported == 1 ? "s" : "");
        if (s->unsup_method)
            fprintf(stderr, "macextract: the first is %s method %d.\n",
                    unc_format_name(L->fmt), s->unsup_method);
        /* No URL, on purpose: a link names a host, an account and a
         * project, and all three outlive their spelling badly. Somebody
         * who has this program can find where it came from. */
        fprintf(stderr,
                "macextract: if you can share this file, please open an "
                "issue — a specimen\n"
                "macextract: is exactly what is needed to add support.\n");
    }
    sink_report_cuts(s);
    /* A selector that matched nothing is a typo, and a typo must not
     * extract nothing and exit 0. */
    if (s->nonly) onlymiss = only_report_misses(a->only, st->only_hit, a->nonly);
    /* Said once at the end as well as once per entry: a long run's
     * per-entry lines scroll away, and this is the one thing about the
     * output that a user has to know afterwards. Not an error — the
     * files are there and they open. */
    if (s->inexact)
        fprintf(stderr, "macextract: %d entr%s rebuilt from what a StuffIt "
                        "Optimizer left, and %s NOT the original file%s\n",
                s->inexact, s->inexact == 1 ? "y was" : "ies were",
                s->inexact == 1 ? "is" : "are",
                s->inexact == 1 ? "" : "s");
    if (s->errors) {
        fprintf(stderr, "macextract: %d of %d entries failed\n",
                s->errors, s->entries);
        /* Say by how much, once, on its own line: the per-entry lines are
         * what the harnesses read, so the number goes here rather than
         * into them. Only when a budget was actually set — without one
         * there is nothing to be short OF. */
        /* AT LEAST, because this is one request's shortfall and not the
         * entry's demand. A decoder that allocates incrementally is
         * refused at the FIRST request that crosses the line, which for
         * DiskDoubler method 5 — 1,536 B per distinct context byte, up to
         * 256 of them — is a shortfall of about a kilobyte on an entry
         * that needs another 200. Measured 2026-09-01: `synth-dd-m5.dd`
         * at --budget 197728 reports 928 and wants 203,680 more — its
         * minimum budget, bisected, is 401,408. */
        if (L->ba.shortby)
            fprintf(stderr, "macextract: at least %u bytes more memory "
                            "would have been needed\n", (unsigned)L->ba.shortby);
        sink_late_final(s, a->only, st->only_hit, a->nonly);
        return 1;
    }
    return onlymiss ? 1 : 0;
}

/* One layer of the chain. Returns LAYER_NEXT when the chain goes on
 * (st holds the next layer's input), or the run's exit code. */
static int run_layer(const CliArgs *a, LayerState *st)
{
    Layer L;
    UncFormat next;
    struct stat st_in;
    int code;

    memset(&L, 0, sizeof L);
    L.file = st->curfile;
    L.fio.f = fopen(L.file, "rb");
    if (!L.fio.f) {
        fprintf(stderr, "macextract: %s: %s\n", L.file, strerror(errno));
        return 1;
    }
    if (stat(L.file, &st_in) == 0) L.fio.size = file_size_off(&st_in, L.file);
    else L.fio.size = UNC_SIZE_UNKNOWN;

    code = layer_extract(a, st, &L);
    fclose(L.fio.f);
    if (code != LAYER_NEXT) return code;

    if (a->stats)
        fprintf(stderr, "alloc: high-water %u bytes, %u refused\n",
                L.ba.high_water, L.ba.failed);
    if (layer_verdict(a, st, &L)) return 1;

    st_drop_previous(st, &L.sink);
    next = st_next_format(a, st, L.fmt, &L.sink);
    if (L.sink.only_late) {
        if (next != UNC_FORMAT_UNKNOWN) {
            if (sink_aside_settle(&L.sink)) return 1;
        } else if (sink_late_final(&L.sink, a->only, st->only_hit, a->nonly)) {
            return 1;
        }
    }
    if (next == UNC_FORMAT_UNKNOWN) return 0;

    /* Envelope auto-unwrap (real-world files are chained: .sit.hqx,
     * .cpt.bin, .tar.Z ...): the one file this layer wrote sniffs as
     * something, so it is extracted in place. -nr disables. */
    if (a->verbose)
        fprintf(stderr, "unwrapping: %s (%s)\n",
                L.sink.last_ok_path, unc_format_name(next));
    st_advance(st, &L.sink);
    return LAYER_NEXT;
}

static int cli_main(int argc, char **argv)
{
    CliArgs a;
    static LayerState st;      /* static: ~21 KB of paths and the reading list */
    int ret;

    if (getenv("UNC_SHORT_READ")) {
        fio_read_cap = (int32_t)atol(getenv("UNC_SHORT_READ"));
        /* Said, so a harness can tell a binary that honours the cap from
         * one that predates it and passes every comparison by ignoring it. */
        fprintf(stderr, "macextract: every read capped at %ld B\n",
                (long)fio_read_cap);
    }
    if ((ret = parse_args(argc, argv, &a)) != LAYER_NEXT) return ret;
    if (st_init(&st, &a)) return 1;
    do ret = run_layer(&a, &st); while (ret == LAYER_NEXT);
    return ret;
}

/* A listing is the output of `l`, and one sent to a full disk is as lost
 * as an extracted file: stdout's own write errors fail the run too, for
 * every return of cli_main at once. */
int main(int argc, char **argv)
{
    int ret = cli_main(argc, argv);
    if (fflush(stdout) != 0 || ferror(stdout)) {
        fprintf(stderr, "macextract: standard output: %s\n",
                strerror(errno));
        if (ret == 0) ret = 1;
    }
    return ret;
}
