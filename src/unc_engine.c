/*
 * unc_engine.c — format sniffing and dispatch.
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* ------------------------------------------------------------------ */
/* Format metadata                                                    */
/* ------------------------------------------------------------------ */

typedef struct UncFormatDesc {
    UncFormat   fmt;
    const char *name;
    int         extractable;
} UncFormatDesc;

static const UncFormatDesc unc_formats[] = {
    { UNC_FORMAT_UNKNOWN,     "unknown",         0 },
    { UNC_FORMAT_MACBINARY,   "MacBinary",       1 },
    { UNC_FORMAT_APPLESINGLE, "AppleSingle",     1 },
    { UNC_FORMAT_APPLEDOUBLE, "AppleDouble",     1 },
    { UNC_FORMAT_BINHEX,      "BinHex 4",        1 },
    { UNC_FORMAT_PACKIT,      "PackIt",          1 },
    { UNC_FORMAT_COMPACTPRO,  "Compact Pro",     1 },
    { UNC_FORMAT_SIT,         "StuffIt",         1 },
    { UNC_FORMAT_SIT5,        "StuffIt 5",       1 },
    { UNC_FORMAT_ZIP,         "Zip",             1 },
    { UNC_FORMAT_GZIP,        "Gzip",            1 },
    { UNC_FORMAT_COMPRESS_Z,  "Unix compress",   1 },
    { UNC_FORMAT_TAR,         "Tar",             1 },
    { UNC_FORMAT_SITX,        "StuffIt X",       0 },
    { UNC_FORMAT_DISKDOUBLER, "DiskDoubler",     1 },
    { UNC_FORMAT_DISKCOPY,    "DiskCopy image",  0 },
    { UNC_FORMAT_NOWCOMPRESS, "Now Compress",    1 },
    { UNC_FORMAT_LZH,         "LZH",             0 },
    { UNC_FORMAT_SITSEG,      "StuffIt segment", 1 },
    { UNC_FORMAT_ZIPSEG,      "Zip segment",     1 },
    /* Extractable, but only as a SET: unc_extract_as has no case for it,
     * because one part of a plain split is an anonymous slice of bytes
     * and there is no header to read it as. The host decides by name
     * and calls unc_extract_segments. */
    { UNC_FORMAT_SPLIT,       "Split file",      1 },
    { UNC_FORMAT_CPTSEG,      "Compact Pro segment", 1 },
};

const char *unc_format_name(UncFormat f)
{
    unsigned i;
    for (i = 0; i < sizeof unc_formats / sizeof unc_formats[0]; i++)
        if (unc_formats[i].fmt == f) return unc_formats[i].name;
    return "unknown";
}

int unc_format_extractable(UncFormat f)
{
    unsigned i;
    for (i = 0; i < sizeof unc_formats / sizeof unc_formats[0]; i++)
        if (unc_formats[i].fmt == f) return unc_formats[i].extractable;
    return 0;
}

const char *unc_strerror(int err)
{
    switch (err) {
    case UNC_OK:              return "ok";
    case UNC_ERR_FORMAT:      return "not a recognized archive";
    case UNC_ERR_IO:          return "I/O error";
    case UNC_ERR_MEM:         return "out of memory (budget exceeded)";
    case UNC_ERR_CRC:         return "checksum mismatch";
    case UNC_ERR_TRUNCATED:   return "file is truncated";
    case UNC_ERR_UNSUPPORTED: return "recognized but unsupported";
    case UNC_ERR_ENCRYPTED:   return "encrypted (unsupported)";
    case UNC_ERR_ABORTED:     return "aborted";
    case UNC_ERR_SINK:        return "output error";
    case UNC_ERR_CORRUPT:     return "archive structure is corrupt";
    case UNC_ERR_SEGMENTED:   return "multi-segment archive (missing segments)";
    default:                  return "unknown error";
    }
}

/* ------------------------------------------------------------------ */
/* Sniffing                                                           */
/*                                                                    */
/* Content only, never extensions. We read the first UNC_SNIFF_HEAD   */
/* bytes and hand them to cheap per-format probes, strongest magic    */
/* first. Probes that need more context (MacBinary CRC, tar at 257,   */
/* Compact Pro trailer) get the io handle too.                        */
/* ------------------------------------------------------------------ */

#define UNC_SNIFF_HEAD 512

UncFormat unc_sniff(UncIO *io)
{
    uint8_t head[UNC_SNIFF_HEAD];
    int32_t len = 0;

    if (io->seek(io->ctx, 0) < 0) return UNC_FORMAT_UNKNOWN;
    /* Tolerate short files: read as much as available. */
    while (len < UNC_SNIFF_HEAD) {
        int32_t r = io->read(io->ctx, head + len, UNC_SNIFF_HEAD - len);
        if (r <= 0) break;
        len += r;
    }
    if (len <= 0) return UNC_FORMAT_UNKNOWN;

    /* Strong magic numbers first. */
    if (unc_sit5_probe(head, len))      return UNC_FORMAT_SIT5;
    if (unc_sit_probe(head, len))       return UNC_FORMAT_SIT;
    if (unc_sitseg_probe(head, len))    return UNC_FORMAT_SITSEG;
    if (unc_sitx_probe(head, len))      return UNC_FORMAT_SITX;
    if (unc_packit_probe(head, len))    return UNC_FORMAT_PACKIT;
    if (unc_gzip_probe(head, len))      return UNC_FORMAT_GZIP;
    if (unc_compressz_probe(head, len)) return UNC_FORMAT_COMPRESS_Z;
    /* Before the plain zip probe, and not after: the two parts of a
     * spanned set that are recognizable at all both look enough like a
     * zip for that probe to claim them, and it would then be reported
     * as an archive that happens to be broken rather than as a piece of
     * one. This costs every file that reaches here a bounded backwards
     * scan for an end-of-central-directory record; a whole zip has one
     * in its last 512 bytes, so it pays a single read. */
    if (unc_zipseg_probe(head, len, io)) return UNC_FORMAT_ZIPSEG;
    if (unc_zip_probe(head, len))       return UNC_FORMAT_ZIP;
    if (unc_lzh_probe(head, len))       return UNC_FORMAT_LZH;
    if (unc_nowcompress_probe(head, len)) return UNC_FORMAT_NOWCOMPRESS;
    if (unc_diskdoubler_probe(head, len)) return UNC_FORMAT_DISKDOUBLER;

    {
        UncFormat asd = UNC_FORMAT_UNKNOWN;
        if (unc_applesingle_probe(head, len, &asd)) return asd;
    }

    /* Weaker/structural probes. */
    /* Before the plain Compact Pro probe, and for the same reason the
     * spanned-zip probe precedes the zip one: the FINAL segment of a set
     * carries a valid index and would be claimed as a whole archive,
     * which would then read every entry at an offset belonging to some
     * other volume. What separates them is the volume byte and the index
     * offset, and only this probe looks at those. */
    if (unc_cptseg_probe(head, len, io)) return UNC_FORMAT_CPTSEG;
    if (unc_cpt_probe(head, len, io))   return UNC_FORMAT_COMPACTPRO;
    if (unc_tar_probe(head, len))       return UNC_FORMAT_TAR;
    if (unc_diskcopy_probe(head, len, io)) return UNC_FORMAT_DISKCOPY;
    if (unc_macbinary_probe(head, len, io)) return UNC_FORMAT_MACBINARY;

    /* BinHex last: it scans for a banner amid mail garbage. */
    if (unc_binhex_probe(head, len, io)) return UNC_FORMAT_BINHEX;

    return UNC_FORMAT_UNKNOWN;
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
    c.ps.total = io->size(io->ctx);
    c.ps.done = 0;
    c.ps.since_tick = 0;
    c.ps.hold = 0;
    if (opt) c.opt = *opt;
    else { c.opt.list_only = 0; c.opt.test_only = 0;
           c.opt.name_hint = 0; c.opt.name_hint_len = 0; }

    if (io->seek(io->ctx, 0) < 0) return UNC_ERR_IO;

    switch (f) {
    case UNC_FORMAT_MACBINARY:   return unc_macbinary_extract(&c);
    case UNC_FORMAT_APPLESINGLE: return unc_appledouble_extract(&c, UNC_FORMAT_APPLESINGLE);
    case UNC_FORMAT_APPLEDOUBLE: return unc_appledouble_extract(&c, UNC_FORMAT_APPLEDOUBLE);
    case UNC_FORMAT_BINHEX:      return unc_binhex_extract(&c);
    case UNC_FORMAT_PACKIT:      return unc_packit_extract(&c);
    case UNC_FORMAT_COMPACTPRO:  return unc_cpt_extract(&c);
    case UNC_FORMAT_SIT:         return unc_sit_extract(&c);
    case UNC_FORMAT_SIT5:        return unc_sit5_extract(&c);
    case UNC_FORMAT_ZIP:         return unc_zip_extract(&c);
    case UNC_FORMAT_GZIP:        return unc_gzip_extract(&c);
    case UNC_FORMAT_COMPRESS_Z:  return unc_compressz_extract(&c);
    case UNC_FORMAT_TAR:         return unc_tar_extract(&c);
    case UNC_FORMAT_DISKDOUBLER: return unc_dd_extract(&c);
    case UNC_FORMAT_NOWCOMPRESS: return unc_now_extract(&c);
    case UNC_FORMAT_SITSEG:      return unc_sitseg_extract(&c);
    case UNC_FORMAT_ZIPSEG:      return unc_zipseg_extract(&c);
    case UNC_FORMAT_UNKNOWN:     return UNC_ERR_FORMAT;
    default:                     return UNC_ERR_UNSUPPORTED;
    }
}

int unc_extract(UncIO *io, UncSink *sink, UncAlloc *al,
                UncProgress *prog, const UncOptions *opt)
{
    UncFormat f = unc_sniff(io);
    return unc_extract_as(f, io, sink, al, prog, opt);
}
