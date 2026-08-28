/* walk_probe.c — do the three walks over one archive offer the same
 * entries, in the same order?
 *
 * Everything in this repository that compares bytes compares the output
 * of ONE walk. Three exist, and nothing had ever held them against each
 * other:
 *
 *   list   `UncOptions.list_only` — the containers are parsed and no
 *          data is decoded. What a listing shows.
 *   full   an ordinary extraction. What the files on disk come from.
 *   alt    an extraction that SKIPS every second entry, which is the
 *          shape a selection has (`begin_entry` returning >0 for some
 *          entries and 0 for others while writing).
 *
 * The property under test is that all three offer `begin_entry` the
 * same entries, with the same identity, in the same order. Three things
 * rest on it, in rising order of how badly they break:
 *
 *   a listing that disagreed with the extraction is a bug no diff suite
 *   could see — already written down for MacLHA, whose MacBinary peek
 *   has to run in listing too or the entry's very name is wrong
 *   (DECISIONS.md, *MacLHA is the Macintosh half*);
 *
 *   `--only NAME` matches a name the listing printed against an entry
 *   the extraction offers, so the two walks agreeing is its premise;
 *
 *   a selection UI that keys by walk ORDINAL — which is what a Mac
 *   list window would do, names being neither unique nor always
 *   representable — is wrong the moment a skip perturbs the sequence.
 *   `alt` is that question asked directly.
 *
 * This only MEASURES: it prints one line per file and
 * `tools/run_walk.py` applies the rule.
 *
 *   <path> ret=<list>,<full>,<alt> n=<list>,<full>,<alt>
 *          lf=<prefix|->:<what> af=<prefix|->:<what>
 *
 * `lf` compares list against full, `af` alt against full. Each is `-`
 * when the sequences are identical, or the index of the first entry
 * that differs and which field differed. A walk that ended early leaves
 * the shorter count in `n`, which is a difference in its own right and
 * is reported as `short`.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
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

static void *p_alloc(void *ctx, uint32_t n) { (void)ctx; return malloc(n); }
static void  p_free(void *ctx, void *ptr)   { (void)ctx; free(ptr); }

/* One entry as a listing shows it: what it is called and what it is.
 * Not the decoded bytes — those are the diff suite's subject, and they
 * are not what an ordinal or a name is matched against. */
typedef struct {
    uint8_t  name[UNC_NAME_MAX + 1];
    uint16_t name_len;
    uint8_t  is_dir;
    uint32_t type, creator, data_size, rsrc_size;
} Rec;

typedef struct {
    Rec   *rec;
    size_t n, cap;
    int    oom;        /* the probe's own allocation failed, not the engine's */
    int    skip_odd;   /* the `alt` walk: skip every second entry offered */
} Seq;

static void seq_free(Seq *s) { free(s->rec); s->rec = NULL; s->n = s->cap = 0; }

static int w_begin(void *ctx, const UncEntryInfo *info)
{
    Seq *s = (Seq *)ctx;
    Rec *r;

    if (s->n == s->cap) {
        size_t cap = s->cap ? s->cap * 2 : 64;
        Rec *grown = (Rec *)realloc(s->rec, cap * sizeof *grown);
        if (!grown) { s->oom = 1; return -1; }
        s->rec = grown;
        s->cap = cap;
    }
    r = &s->rec[s->n++];
    memset(r, 0, sizeof *r);
    r->name_len = (uint16_t)(info->name_len > UNC_NAME_MAX
                             ? UNC_NAME_MAX : info->name_len);
    memcpy(r->name, info->name, r->name_len);
    r->is_dir    = info->is_dir;
    r->type      = info->type;
    r->creator   = info->creator;
    r->data_size = info->data_size;
    r->rsrc_size = info->rsrc_size;

    /* The skip is decided by POSITION, so it does not depend on
     * anything the archive says and every format meets the same
     * pattern. Entry 0 is kept, so a one-entry archive is still a
     * walk that wrote something. */
    if (s->skip_odd && (s->n - 1) % 2 == 1) return 1;
    return 0;
}

static int w_write(void *ctx, UncFork fork, const void *buf, int32_t len)
{ (void)ctx; (void)fork; (void)buf; (void)len; return 0; }
static int w_end(void *ctx, int status) { (void)ctx; (void)status; return 0; }

static int walk(const char *path, Seq *seq, int list_only, int skip_odd)
{
    ProbeIO pio;
    UncIO io;
    UncSink sink;
    UncAlloc al;
    UncOptions opt;
    long len;
    int ret;

    memset(seq, 0, sizeof *seq);
    seq->skip_odd = skip_odd;

    pio.f = fopen(path, "rb");
    if (!pio.f) { perror(path); return UNC_ERR_IO; }
    if (fseek(pio.f, 0, SEEK_END) != 0) { fclose(pio.f); return UNC_ERR_IO; }
    len = ftell(pio.f);
    rewind(pio.f);
    pio.size = (uint32_t)len;

    io.ctx = &pio; io.read = p_read; io.seek = p_seek;
    io.tell = p_tell; io.size = p_size;
    sink.ctx = seq; sink.begin_entry = w_begin; sink.write = w_write;
    sink.end_entry = w_end; sink.comment = NULL;
    al.ctx = NULL; al.alloc = p_alloc; al.free = p_free;

    memset(&opt, 0, sizeof opt);
    opt.list_only = (uint8_t)(list_only ? 1 : 0);

    ret = unc_extract(&io, &sink, &al, NULL, &opt);
    fclose(pio.f);
    return ret;
}

/* The first entry the two sequences disagree about, and what about it.
 * Writes "-" when they are identical. */
static void diff(const Seq *a, const Seq *b, char *out, size_t outsz)
{
    size_t i, n = a->n < b->n ? a->n : b->n;

    for (i = 0; i < n; i++) {
        const Rec *x = &a->rec[i], *y = &b->rec[i];
        const char *what = NULL;
        if (x->name_len != y->name_len ||
            memcmp(x->name, y->name, x->name_len) != 0) what = "name";
        else if (x->is_dir != y->is_dir)         what = "is_dir";
        else if (x->type != y->type)             what = "type";
        else if (x->creator != y->creator)       what = "creator";
        else if (x->data_size != y->data_size)   what = "data_size";
        else if (x->rsrc_size != y->rsrc_size)   what = "rsrc_size";
        if (what) {
            snprintf(out, outsz, "%lu:%s", (unsigned long)i, what);
            return;
        }
    }
    if (a->n != b->n) {
        snprintf(out, outsz, "%lu:short", (unsigned long)n);
        return;
    }
    snprintf(out, outsz, "-");
}

int main(int argc, char **argv)
{
    int i;

    for (i = 1; i < argc; i++) {
        Seq list, full, alt;
        char lf[64], af[64];
        int rl, rf, ra;

        rl = walk(argv[i], &list, 1, 0);
        rf = walk(argv[i], &full, 0, 0);
        ra = walk(argv[i], &alt,  0, 1);

        if (list.oom || full.oom || alt.oom) {
            printf("%s oom\n", argv[i]);
            seq_free(&list); seq_free(&full); seq_free(&alt);
            continue;
        }
        diff(&list, &full, lf, sizeof lf);
        diff(&alt, &full, af, sizeof af);
        printf("%s ret=%d,%d,%d n=%lu,%lu,%lu lf=%s af=%s\n",
               argv[i], rl, rf, ra,
               (unsigned long)list.n, (unsigned long)full.n,
               (unsigned long)alt.n, lf, af);
        seq_free(&list); seq_free(&full); seq_free(&alt);
    }
    return 0;
}
