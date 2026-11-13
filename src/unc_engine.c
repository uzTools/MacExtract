/*
 * unc_engine.c — the format table and the dispatch. The sniffer is
 * unc_sniff.c's since 2026-10-21.
 * SPDX-License-Identifier: 0BSD
 */
#include "unc_internal.h"

/* ------------------------------------------------------------------ */
/* Format metadata                                                    */
/* ------------------------------------------------------------------ */

/* One row a format, in src/unc_formats.h: every row but UNC_FORMAT_UNKNOWN's
 * is a format this engine extracts; since 2026-10-18 it names none it does
 * not (DECISIONS.md 2026-10-18, *the formats it only named*). A PART row is
 * a format read only as a SET, which unc_extract_as refuses (unc_formats.h,
 * UNC_FORMAT_SPLIT's row).
 *
 * Expanded into the table below everywhere but in a Macintosh build with
 * images, and there into three bitmaps, because that build reads no name
 * and dispatches every extractor by format (DECISIONS.md 2026-11-12, *the
 * format table that became three bitmaps*). */
#define UNC_KIND_ENV_FILE        0
#define UNC_KIND_ENV_ENVELOPE    1
#define UNC_KIND_ENV_PART        0
#define UNC_KIND_X_FILE(x)       x
#define UNC_KIND_X_ENVELOPE(x)   x
#define UNC_KIND_X_PART(x)       NULL

#ifndef UNC_AT_OVERLAY

typedef struct UncFormatDesc {
    UncFormat   fmt;
    const char *name;
    /* Holds exactly one file and is worth looking inside: the layers a
     * real download is chained from (.sit.hqx, .cpt.bin, .tar.Z). NOT
     * every format that happens to yield one file — a zip holding a
     * single archive is an ARCHIVE, and going round again would extract
     * something the user did not ask for.
     *
     * It lives here because it is a property of a FORMAT, and it lived
     * in both hosts before that: they disagreed for a day (DECISIONS.md
     * 2026-08-14), which is what a list kept in two places does.
     *
     * base64 and not MIME, though both usually hold an archive: an
     * envelope layer is DELETED once the layer under it comes out, and
     * a MIME part can carry a resource fork that would go with it.
     * base64 has one anonymous stream and no forks at all. btoa and
     * uuencode are in for the same reason with the same guard — a real
     * btoa file off a Mac is MacBinary inside armour, and uuencode's
     * UUTool shape carries its own forks the way BinHex does, so
     * neither can strand a fork on a layer that is deleted
     * (DECISIONS.md 2026-08-26, 2026-08-27). */
    int         envelope;
    /* The extractor: an F() row's, or NULL for an S() row's. */
    UncExtract  extract;
} UncFormatDesc;

#define UNC_ROW(f, n, k, x, run, keep, join) \
    { f, n, UNC_KIND_ENV_##k, UNC_KIND_X_##k(x) },
static const UncFormatDesc unc_formats[] = {
    UNC_FORMATS(UNC_ROW)
};

static const UncFormatDesc *unc_desc(UncFormat f)
{
    unsigned i;
    for (i = 0; i < sizeof unc_formats / sizeof unc_formats[0]; i++)
        if (unc_formats[i].fmt == f) return &unc_formats[i];
    return NULL;
}

const char *unc_format_name(UncFormat f)
{
    const UncFormatDesc *d = unc_desc(f);
    return d ? d->name : "unknown";
}

/* Every row but UNKNOWN's is extractable since 2026-10-18; what this
 * still refuses is a value with no row at all — the two retired slots
 * in macextract.h, and anything out of range. */
int unc_format_extractable(UncFormat f)
{
    return f != UNC_FORMAT_UNKNOWN && unc_desc(f) != NULL;
}

int unc_format_is_envelope(UncFormat f)
{
    const UncFormatDesc *d = unc_desc(f);
    return d ? d->envelope : 0;
}

#else  /* UNC_AT_OVERLAY */

/* The Macintosh build with images. Nothing there shows a format's name
 * (the report names files, not formats), so unc_format_name is not
 * defined and a caller fails to link; every extractor is one dispatch on
 * UncCtx.fmt (mac/ovl_shim.c, unc_run_file), so only whether a row has
 * one is kept. What is left of a row is a bit in each of three maps,
 * constants the compiler folds: a new format costs nothing here until
 * there are 64. */
typedef char unc_formats_fit_in_64[UNC_FORMAT__COUNT <= 64 ? 1 : -1];

#define UNC_KIND_FILE_FILE       1ULL
#define UNC_KIND_FILE_ENVELOPE   1ULL
#define UNC_KIND_FILE_PART       0ULL
#define UNC_MAP(m) \
    (uint8_t)(m),         (uint8_t)((m) >> 8),  (uint8_t)((m) >> 16), \
    (uint8_t)((m) >> 24), (uint8_t)((m) >> 32), (uint8_t)((m) >> 40), \
    (uint8_t)((m) >> 48), (uint8_t)((m) >> 56)

enum { UNC_MAP_ROW = 0, UNC_MAP_FILE = 8, UNC_MAP_ENV = 16 };
#define UNC_ROW(f, n, k, x, run, keep, join)  | (1ULL << (f))
#define UNC_FILE(f, n, k, x, run, keep, join) | (UNC_KIND_FILE_##k << (f))
#define UNC_ENV(f, n, k, x, run, keep, join) \
    | ((unsigned long long)UNC_KIND_ENV_##k << (f))
static const uint8_t unc_maps[24] = {
    UNC_MAP(0ULL UNC_FORMATS(UNC_ROW)),
    UNC_MAP(0ULL UNC_FORMATS(UNC_FILE)),
    UNC_MAP(0ULL UNC_FORMATS(UNC_ENV))
};

static int unc_has(unsigned map, UncFormat f)
{
    unsigned v = (unsigned)f;
    return v < 64 && (unc_maps[map + (v >> 3)] >> (v & 7)) & 1;
}

int unc_format_extractable(UncFormat f)
{
    return f != UNC_FORMAT_UNKNOWN && unc_has(UNC_MAP_ROW, f);
}

int unc_format_is_envelope(UncFormat f)
{
    return unc_has(UNC_MAP_ENV, f);
}

#endif /* UNC_AT_OVERLAY */

const char *unc_strerror(int err)
{
    switch (err) {
    case UNC_OK:              return "ok";
    case UNC_ERR_FORMAT:      return "not a recognized archive";
    case UNC_ERR_IO:          return "I/O error";
    case UNC_ERR_MEM:         return "out of memory (budget exceeded)";
    case UNC_ERR_CRC:         return "checksum mismatch";
    case UNC_ERR_TRUNCATED:   return "file is truncated";
    case UNC_ERR_UNSUPPORTED: return "this compression method is not supported yet";
    case UNC_ERR_ENCRYPTED:   return "encrypted by a scheme we cannot read";
    case UNC_ERR_ABORTED:     return "aborted";
    case UNC_ERR_SINK:        return "output error";
    case UNC_ERR_CORRUPT:     return "archive structure is corrupt";
    case UNC_ERR_SEGMENTED:   return "multi-segment archive (missing segments)";
    case UNC_ERR_PASSWORD:    return "wrong password, or none given";
    case UNC_ERR_TOOLARGE:    return "entry is past this engine's 32-bit reach";
    case UNC_ERR_MODULE:      return "needs a StuffIt add-on module nothing has";
    case UNC_ERR_NESTED:      return "nested too deep to open";
    default:                  return "unknown error";
    }
}

/* ------------------------------------------------------------------ */
/* Extraction dispatch                                                */
/* ------------------------------------------------------------------ */

int unc_extract_as(UncFormat f, UncIO *io, UncSink *sink, UncAlloc *al,
                   UncProgress *prog, const UncOptions *opt)
{
    UncCtx c;

    if (!io || !sink || !al) return UNC_ERR_IO;

    c.io = io;
    c.sink = sink;
    c.al = al;
    c.segmap = NULL;              /* one file: offsets are already absolute */
    c.ps.prog = prog;
    c.ps.total = unc_io_size32(io);
    c.ps.done = 0;
    c.ps.since_tick = 0;
    c.ps.hold = 0;
    if (opt) {
        c.opt = *opt;
    } else {
        /* Zero the WHOLE struct, not a list of its fields. The list was
         * written when UncOptions had nine members and was never
         * revisited: `long_name` joined it on 2026-08-27 and every
         * caller passing NULL — which the unit tests do — then read a
         * pointer off an uninitialised stack. It segfaulted the first
         * time an entry asked for the buffer. */
        uint8_t *p = (uint8_t *)&c.opt;
        uint32_t i;
        for (i = 0; i < sizeof c.opt; i++) p[i] = 0;
    }
    c.pwlen = 0;
    c.pwstate = UNC_PW_UNSET;
    c.pwattempt = 0;
    c.fmt = (uint8_t)f;

    if (io->seek(io->ctx, 0) < 0) return UNC_ERR_IO;

#ifndef UNC_AT_OVERLAY
    {
        const UncFormatDesc *d = unc_desc(f);
        if (!d || !d->extract)
            return f == UNC_FORMAT_UNKNOWN ? UNC_ERR_FORMAT
                                           : UNC_ERR_UNSUPPORTED;
        return d->extract(&c);
    }
#else
    if (!unc_has(UNC_MAP_FILE, f))
        return f == UNC_FORMAT_UNKNOWN ? UNC_ERR_FORMAT : UNC_ERR_UNSUPPORTED;
    return unc_run_file(&c);
#endif
}

int unc_extract(UncIO *io, UncSink *sink, UncAlloc *al,
                UncProgress *prog, const UncOptions *opt)
{
    UncFormat f = unc_sniff(io);
    return unc_extract_as(f, io, sink, al, prog, opt);
}
