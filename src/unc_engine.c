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
    /* The extractor, or NULL for a format this engine only names.
     * UNC_FORMAT_SPLIT is the one row where `extractable` is set
     * and this is NULL: see its comment in the table. */
    UncExtract  extract;
} UncFormatDesc;

static const UncFormatDesc unc_formats[] = {
    { UNC_FORMAT_UNKNOWN,     "unknown",             0, 0, NULL },
    { UNC_FORMAT_MACBINARY,   "MacBinary",           1, 1, unc_macbinary_extract },
    { UNC_FORMAT_APPLESINGLE, "AppleSingle",         1, 1, unc_appledouble_extract },
    { UNC_FORMAT_APPLEDOUBLE, "AppleDouble",         1, 1, unc_appledouble_extract },
    { UNC_FORMAT_BINHEX,      "BinHex 4",            1, 1, unc_binhex_extract },
    { UNC_FORMAT_PACKIT,      "PackIt",              1, 0, unc_packit_extract },
    { UNC_FORMAT_COMPACTPRO,  "Compact Pro",         1, 0, unc_cpt_extract },
    { UNC_FORMAT_SIT,         "StuffIt",             1, 0, unc_sit_extract },
    { UNC_FORMAT_SIT5,        "StuffIt 5",           1, 0, unc_sit5_extract },
    { UNC_FORMAT_ZIP,         "Zip",                 1, 0, unc_zip_extract },
    { UNC_FORMAT_GZIP,        "Gzip",                1, 1, unc_gzip_extract },
    { UNC_FORMAT_COMPRESS_Z,  "Unix compress",       1, 1, unc_compressz_extract },
    { UNC_FORMAT_TAR,         "Tar",                 1, 0, unc_tar_extract },
    { UNC_FORMAT_SITX,        "StuffIt X",           0, 0, NULL },
    { UNC_FORMAT_DISKDOUBLER, "DiskDoubler",         1, 0, unc_dd_extract },
    { UNC_FORMAT_NOWCOMPRESS, "Now Compress",        1, 0, unc_now_extract },
    { UNC_FORMAT_LZH,         "LZH",                 1, 0, unc_lzh_extract },
    { UNC_FORMAT_SITSEG,      "StuffIt segment",     1, 0, unc_sitseg_extract },
    { UNC_FORMAT_ZIPSEG,      "Zip segment",         1, 0, unc_zipseg_extract },
    /* Extractable, but only as a SET: unc_extract_as has no case for it,
     * because one part of a plain split is an anonymous slice of bytes
     * and there is no header to read it as. The host decides by name
     * and calls unc_extract_segments. */
    { UNC_FORMAT_SPLIT,       "Split file",          1, 0, NULL },
    { UNC_FORMAT_CPTSEG,      "Compact Pro segment", 1, 0, NULL },
    /* Extractable only as a SET, like the two rows above: one part of a
     * message/partial set is half a message, and unc_extract_as has no
     * case for it. */
    { UNC_FORMAT_MIMESEG,     "message/partial part", 1, 0, NULL },
    { UNC_FORMAT_UU,          "uuencode",            1, 1, unc_uu_extract },
    { UNC_FORMAT_ARC,         "ARC",                 1, 0, unc_arc_extract },
    { UNC_FORMAT_SUPERDISK,   "SuperDisk!",          1, 0, unc_superdisk_extract },
    { UNC_FORMAT_DDSEG,       "DiskDoubler split",   1, 0, unc_ddseg_extract },
    { UNC_FORMAT_SPACESAVER,  "StuffIt SpaceSaver",  1, 0, unc_spacesaver_extract },
    { UNC_FORMAT_BTOA,        "btoa",                1, 1, unc_btoa_extract },
    { UNC_FORMAT_BASE64,      "base64",              1, 1, unc_b64_extract },
    { UNC_FORMAT_MIME,        "MIME message",        1, 0, unc_mime_extract },
    { UNC_FORMAT_SQP,         "AppleLink package",   1, 0, unc_sqp_extract },
    /* Named, never extracted (src/fmt_foreign.c). */
    { UNC_FORMAT_RAR,         "RAR",                 0, 0, NULL },
    { UNC_FORMAT_RAR5,        "RAR 5",               0, 0, NULL },
    { UNC_FORMAT_7Z,          "7-Zip",               0, 0, NULL },
    { UNC_FORMAT_XZ,          "xz",                  0, 0, NULL },
    { UNC_FORMAT_BZIP2,       "bzip2",               0, 0, NULL },
    { UNC_FORMAT_CAB,         "Microsoft Cabinet",   0, 0, NULL },
    { UNC_FORMAT_ZOO,         "Zoo",                 0, 0, NULL },
    { UNC_FORMAT_AR,          "ar archive",          0, 0, NULL },
    { UNC_FORMAT_CPIO,        "cpio",                0, 0, NULL },
    { UNC_FORMAT_ARJ,         "ARJ",                 0, 0, NULL },
    { UNC_FORMAT_ZSTD,        "Zstandard",           0, 0, NULL },
    { UNC_FORMAT_LZIP,        "lzip",                0, 0, NULL },
    { UNC_FORMAT_LRZIP,       "lrzip",               0, 0, NULL },
    { UNC_FORMAT_WIM,         "WIM",                 0, 0, NULL },
    { UNC_FORMAT_AAR,         "Apple Archive",       0, 0, NULL },
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

int unc_format_extractable(UncFormat f)
{
    const UncFormatDesc *d = unc_desc(f);
    return d ? d->extractable : 0;
}

int unc_format_is_envelope(UncFormat f)
{
    const UncFormatDesc *d = unc_desc(f);
    return d ? d->envelope : 0;
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
    case UNC_ERR_UNSUPPORTED: return "this compression method is not supported yet";
    case UNC_ERR_ENCRYPTED:   return "encrypted by a scheme we cannot read";
    case UNC_ERR_ABORTED:     return "aborted";
    case UNC_ERR_SINK:        return "output error";
    case UNC_ERR_CORRUPT:     return "archive structure is corrupt";
    case UNC_ERR_SEGMENTED:   return "multi-segment archive (missing segments)";
    case UNC_ERR_PASSWORD:    return "wrong password, or none given";
    case UNC_ERR_TOOLARGE:    return "entry is past this engine's 32-bit reach";
    case UNC_ERR_MODULE:      return "needs a StuffIt add-on module nothing has";
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

/* The order IS the algorithm, and each step of it is argued below.
 * Nothing here is alphabetical or accidental: a probe that cannot be
 * wrong goes before one that can, and a probe for a PART of a set goes
 * before the probe for the whole it resembles. */
static const UncProbe unc_sniff_order[] = {
    /* Strong magic numbers first. */
    unc_sit5_probe,
    unc_sit_probe,
    unc_sitseg_probe,
    /* DiskDoubler's `SPLT`: two copies of its magic, 90 bytes apart. */
    unc_ddseg_probe,
    unc_sitx_probe,
    /* 'SIT!' again, but with 'DFD3' behind it: SpaceSaver's header, and
     * the StuffIt probe above would never claim it (its second long is
     * 'rLau'). */
    unc_spacesaver_probe,
    unc_packit_probe,
    unc_gzip_probe,
    unc_compressz_probe,
    /* The PC-side archives, all of them a constant at a fixed offset, so
     * the whole set costs a handful of byte compares on a buffer already
     * read. They sit with the other magic numbers and ahead of
     * MacBinary's CRC for the same reason MacBinary sits ahead of the
     * zip scan: a test that cannot be wrong should not be paid for
     * twice. Nothing here can take a file from a Mac format — every one
     * is a constant no Mac archive begins with (fmt_foreign.c). */
    unc_foreign_probe,
    /* MacBinary has no magic number, only a header CRC and structural
     * constraints, which is why it used to sit LAST — the weakest test
     * claims a file only when nothing stronger has. It is here instead
     * because of what it costs to leave it there: MacBinary is 234 of
     * the corpus's 932 fixtures, the most common format in it, and every
     * one of them walked a 64 KB backwards scan for a zip's
     * end-of-central-directory record, then twenty more probes, before
     * reaching a test that is a CRC-16 over 124 bytes it has already
     * read. It is placed AFTER the magic numbers, so nothing with a
     * signature can be taken from it, and the constraints it adds to
     * that CRC — byte 0, byte 74, byte 82 and bytes 108..115 all zero,
     * plus a valid Pascal name — reject the head of every format probed
     * below (AppleSingle's 0x00051600 fails the name test; Compact Pro,
     * ARC, tar and Disk Copy all have a non-zero byte 0). 932 fixtures
     * and 9,320 robustness variants are what actually grade that. */
    unc_macbinary_probe,
    /* Four more magic numbers, and the two Compact Pro probes, AHEAD of
     * the zip pair rather than behind it (2026-09-18). The spanned-zip
     * probe below scans the last 64 KB of the file backwards in 1 KB
     * reads, so every file that reached it paid up to 65 reads before
     * its own probe ran — on a Mac Plus reading a floppy, that is the
     * open latency. None of these six can take a zip or a part of one:
     * every zip head starts 'P' 'K', where LZH wants '-' at byte 2,
     * Now Compress 0x00 0x02 at byte 0, DiskDoubler one of three
     * four-byte magics, AppleSingle its own, and both Compact Pro
     * probes a first byte of 1. The reverse — a Compact Pro archive
     * carrying a stored zip part in its last 64 KB — used to be claimed
     * as a zip segment, and is now the archive it is. SuperDisk! stays
     * behind the zip pair, being weak on its own (below). */
    unc_lzh_probe,
    unc_nowcompress_probe,
    unc_diskdoubler_probe,
    /* One probe, two formats: they share a magic and differ in it. */
    unc_applesingle_probe,
    /* Before the plain Compact Pro probe, and for the same reason the
     * spanned-zip probe precedes the zip one: the FINAL segment of a set
     * carries a valid index and would be claimed as a whole archive,
     * which would then read every entry at an offset belonging to some
     * other volume. What separates them is the volume byte and the index
     * offset, and only this probe looks at those. */
    unc_cptseg_probe,
    unc_cpt_probe,
    /* Before the plain zip probe, and not after: the two parts of a
     * spanned set that are recognizable at all both look enough like a
     * zip for that probe to claim them, and it would then be reported
     * as an archive that happens to be broken rather than as a piece of
     * one. This costs every file that reaches here a bounded backwards
     * scan for an end-of-central-directory record; a whole zip has one
     * in its last 512 bytes, so it pays a single read. */
    unc_zipseg_probe,
    unc_zip_probe,
    /* SuperDisk!'s own mark is a module signature or a record tag at
     * byte 8, either way confirmed by the 0x27 record that must end
     * the file — weak on its own, so it sits after the magics. */
    unc_superdisk_probe,
    /* An AppleLink package has no magic number at all, so its probe is
     * the container's own arithmetic — a version byte, eight zero bytes
     * and a directory whose forks tile the file to its last byte. It
     * costs a file that is not one ten bytes already read, which is why
     * it sits here rather than at the end: everything below scans, and a
     * package that reached them would pay for the scan before being
     * recognised (fmt_sqp_probe.c). */
    unc_sqp_probe,

    /* Weaker/structural probes. */
    unc_tar_probe,
    /* ARC's magic is one byte (0x1a), so the probe leans on the whole
     * header: a printable 13-byte name, a known method, and sizes that
     * land on the next header or the end marker. */
    unc_arc_probe,
    /* BinHex last: it scans for a banner amid mail garbage. uuencode
     * and btoa sit beside it — same habitat, same kind of scan — and
     * before it, because BinHex's probe reads on past its own banner
     * and neither of those has one to find. btoa goes first of the
     * three: its marker is a whole word at the start of a line, where
     * uuencode's is a "begin" that prose contains. */
    /* Before those three, and not after: each of them scans for a
     * document ANYWHERE in a file, so a multipart message holding one
     * as a part would be claimed whole on the strength of that part,
     * and every other part dropped — measured, and the reason this
     * entry exists (DECISIONS.md 2026-08-29, a part that hid its
     * message). Only a message declaring a multipart WITH a boundary is
     * claimed here; a posting whose body is one uuencoded or BinHex
     * document has no boundary and still belongs to its own format. */
    /* A part of a SET before the whole it resembles, which is the same
     * rule the spanned-zip and Compact Pro segment probes sit under:
     * part 1 of a message/partial set is a message and would be read
     * as the one it is a slice of. */
    unc_mimeseg_probe,
    unc_mime_probe_multipart,
    unc_btoa_probe,
    unc_uu_probe,
    unc_binhex_probe,
    /* Last of all, and deliberately: base64 has no marker at all in its
     * bare shape, and a MIME message is claimed only when it carries a
     * part to extract. Everything the three probes above read — a
     * BinHex banner, a "begin" line with a length that agrees, btoa's
     * word — is a stronger claim on the same kind of file, and a mail
     * message with a .hqx in its body is a BinHex file that happens to
     * have headers rather than a message with an attachment. */
    unc_mime_probe,
    unc_b64_probe
};

UncFormat unc_sniff(UncIO *io)
{
    uint8_t head[UNC_SNIFF_HEAD];
    int32_t len = 0;
    unsigned i;

    if (io->seek(io->ctx, 0) < 0) return UNC_FORMAT_UNKNOWN;
    /* Tolerate short files: read as much as available. */
    while (len < UNC_SNIFF_HEAD) {
        int32_t r = io->read(io->ctx, head + len, UNC_SNIFF_HEAD - len);
        if (r <= 0) break;
        len += r;
    }
    if (len <= 0) return UNC_FORMAT_UNKNOWN;

    for (i = 0; i < sizeof unc_sniff_order / sizeof unc_sniff_order[0]; i++) {
        UncFormat f = unc_sniff_order[i](head, len, io);
        if (f != UNC_FORMAT_UNKNOWN) return f;
    }
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

    if (io->seek(io->ctx, 0) < 0) return UNC_ERR_IO;

    {
        const UncFormatDesc *d = unc_desc(f);
        if (!d || !d->extract)
            return f == UNC_FORMAT_UNKNOWN ? UNC_ERR_FORMAT
                                           : UNC_ERR_UNSUPPORTED;
        return d->extract(&c);
    }
}

int unc_extract(UncIO *io, UncSink *sink, UncAlloc *al,
                UncProgress *prog, const UncOptions *opt)
{
    UncFormat f = unc_sniff(io);
    return unc_extract_as(f, io, sink, al, prog, opt);
}
