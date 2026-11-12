/*
 * unc_engine.c — the format table and the dispatch. The sniffer is
 * unc_sniff.c's since 2026-10-21.
 * SPDX-License-Identifier: 0BSD
 */
#include "unc_internal.h"

/* ------------------------------------------------------------------ */
/* Format metadata                                                    */
/* ------------------------------------------------------------------ */

/* One row a format: F(format, name, envelope, extractor) for a format
 * read as a file, S(format, name) for one read only as a SET, which
 * unc_extract_as refuses (see UNC_FORMAT_SPLIT's comment below). Every
 * row but UNC_FORMAT_UNKNOWN's is a format this engine extracts; since
 * 2026-10-18 it names none it does not (DECISIONS.md 2026-10-18, *the
 * formats it only named*).
 *
 * One list, expanded twice: into the table below everywhere but in a
 * Macintosh build with images, and there into three bitmaps, because
 * that build reads no name and dispatches every extractor by format
 * (DECISIONS.md 2026-11-12, *the format table that became three
 * bitmaps*). */
#define UNC_FORMAT_ROWS(F, S) \
    S(UNC_FORMAT_UNKNOWN, "unknown") \
    F(UNC_FORMAT_MACBINARY, "MacBinary", 1, unc_macbinary_extract) \
    F(UNC_FORMAT_APPLESINGLE, "AppleSingle", 1, unc_appledouble_extract) \
    F(UNC_FORMAT_APPLEDOUBLE, "AppleDouble", 1, unc_appledouble_extract) \
    F(UNC_FORMAT_BINHEX, "BinHex 4", 1, unc_binhex_extract) \
    /* .hex and .hcx, both written by BinHex 2.0 (src/fmt_hecx.c). An
     * envelope on the same terms as BinHex 4: it carries its own forks.
     * Reached through unc_binhex_extract, which looks at UncCtx.fmt. */ \
    F(UNC_FORMAT_BINHEX_OLD, "BinHex hex/hcx", 1, unc_binhex_extract) \
    /* .dl, SUMacC's, older than both: a resource fork alone. The same
     * decoder, entered the same way. */ \
    F(UNC_FORMAT_DL, "SUMacC dl", 1, unc_binhex_extract) \
    F(UNC_FORMAT_PACKIT, "PackIt", 0, unc_packit_extract) \
    F(UNC_FORMAT_COMPACTPRO, "Compact Pro", 0, unc_cpt_extract) \
    F(UNC_FORMAT_SIT, "StuffIt", 0, unc_sit_extract) \
    F(UNC_FORMAT_SIT5, "StuffIt 5", 0, unc_sit5_extract) \
    F(UNC_FORMAT_ZIP, "Zip", 0, unc_zip_extract) \
    F(UNC_FORMAT_GZIP, "Gzip", 1, unc_gzip_extract) \
    F(UNC_FORMAT_COMPRESS_Z, "Unix compress", 1, unc_compressz_extract) \
    /* One stream in a frame, as `.Z`: mar 0.2.0's other compressed form
     * of a MAR (src/fmt_lz4.c). */ \
    F(UNC_FORMAT_LZ4, "LZ4", 1, unc_lz4_extract) \
    F(UNC_FORMAT_TAR, "Tar", 0, unc_tar_extract) \
    /* Not an envelope even as a `.mac`, which holds one file: the
     * format is the same when it holds a folder (fmt_mar.c). */ \
    F(UNC_FORMAT_MAR, "MAR", 0, unc_mar_extract) \
    F(UNC_FORMAT_TOME, "Installer Tome", 0, unc_tome_extract) \
    F(UNC_FORMAT_DISKDOUBLER, "DiskDoubler", 0, unc_dd_extract) \
    F(UNC_FORMAT_NOWCOMPRESS, "Now Compress", 0, unc_now_extract) \
    F(UNC_FORMAT_LZH, "LZH", 0, unc_lzh_extract) \
    F(UNC_FORMAT_SITSEG, "StuffIt segment", 0, unc_sitseg_extract) \
    F(UNC_FORMAT_ZIPSEG, "Zip segment", 0, unc_zipseg_extract) \
    /* Extractable, but only as a SET: unc_extract_as has no case for it,
     * because one part of a plain split is an anonymous slice of bytes
     * and there is no header to read it as. The host decides by name
     * and calls unc_extract_segments. */ \
    S(UNC_FORMAT_SPLIT, "Split file") \
    S(UNC_FORMAT_CPTSEG, "Compact Pro segment") \
    /* Extractable only as a SET, like the two rows above: one part of a
     * message/partial set is half a message, and unc_extract_as has no
     * case for it. */ \
    S(UNC_FORMAT_MIMESEG, "message/partial part") \
    /* One disk of a set, like the rows above: read only as a set, a set
     * of one included, because only the joiner can hand the reader the
     * next disk (fmt_abk.c). */ \
    S(UNC_FORMAT_ABK, "Apple Backup") \
    F(UNC_FORMAT_UU, "uuencode", 1, unc_uu_extract) \
    F(UNC_FORMAT_ARC, "ARC", 0, unc_arc_extract) \
    F(UNC_FORMAT_SUPERDISK, "SuperDisk!", 0, unc_superdisk_extract) \
    F(UNC_FORMAT_DDSEG, "DiskDoubler split", 0, unc_ddseg_extract) \
    F(UNC_FORMAT_SPACESAVER, "StuffIt SpaceSaver", 0, unc_spacesaver_extract) \
    F(UNC_FORMAT_BTOA, "btoa", 1, unc_btoa_extract) \
    F(UNC_FORMAT_BASE64, "base64", 1, unc_b64_extract) \
    F(UNC_FORMAT_MIME, "MIME message", 0, unc_mime_extract) \
    F(UNC_FORMAT_SQP, "AppleLink package", 0, unc_sqp_extract) \
    /* An envelope: one file in, one file out — and the file PF Encrypt
     * puts in is always a StuffIt archive it made first (fmt_pf.c). */ \
    F(UNC_FORMAT_PRIVATEFILE, "Private File", 1, unc_pf_extract)

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

#define UNC_ROW_F(f, n, e, x) { f, n, e, x },
#define UNC_ROW_S(f, n)       { f, n, 0, NULL },
static const UncFormatDesc unc_formats[] = {
    UNC_FORMAT_ROWS(UNC_ROW_F, UNC_ROW_S)
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

#define UNC_BIT(f)              | (1ULL << (f))
#define UNC_ROW_F(f, n, e, x)   UNC_BIT(f)
#define UNC_ROW_S(f, n)         UNC_BIT(f)
#define UNC_FILE_F(f, n, e, x)  UNC_BIT(f)
#define UNC_FILE_S(f, n)
#define UNC_ENV_F(f, n, e, x)   | ((e) ? 1ULL << (f) : 0ULL)
#define UNC_ENV_S(f, n)
#define UNC_MAP(m) \
    (uint8_t)(m),         (uint8_t)((m) >> 8),  (uint8_t)((m) >> 16), \
    (uint8_t)((m) >> 24), (uint8_t)((m) >> 32), (uint8_t)((m) >> 40), \
    (uint8_t)((m) >> 48), (uint8_t)((m) >> 56)

enum { UNC_MAP_ROW = 0, UNC_MAP_FILE = 8, UNC_MAP_ENV = 16 };
static const uint8_t unc_maps[24] = {
    UNC_MAP(0ULL UNC_FORMAT_ROWS(UNC_ROW_F, UNC_ROW_S)),
    UNC_MAP(0ULL UNC_FORMAT_ROWS(UNC_FILE_F, UNC_FILE_S)),
    UNC_MAP(0ULL UNC_FORMAT_ROWS(UNC_ENV_F, UNC_ENV_S))
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
