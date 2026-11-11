/*
 * release_plan.inc.c — what the eager release keeps, decided in an image.
 *
 * mac/ovl_load_eager.c gives back the images an archive cannot want once its
 * format is known, and keeps the rest. Which ones it keeps is decided here:
 * by format, by the envelope peek's answer under an envelope, and by the
 * archive's own directory where it says no entry is encrypted. Included by
 * tools/overlay/ovl_segsetup.c, so that the decision is in the bundle while
 * the bundle is whole — which is the only time it runs — and goes back with
 * it; the resident loader keeps only the list it is handed (DECISIONS.md
 * 2026-11-11, *the release decided in the bundle*). tests/ovlbox compiles
 * it natively, as the host lane's stand-in for the image.
 *
 * Its includer provides peek_alloc and peek_free, the plain NewPtr and
 * DisposePtr the peek runs on: the engine's budget is not taken until after
 * the release.
 *
 * SPDX-License-Identifier: 0BSD
 */

/* What each format keeps (DECISIONS.md 2026-10-23, *the shims that were
 * one function*), by format: its decoder's image as an offset from 128,
 * plus one so that 0 can mean "not here", and KEEP_CRYPT if an entry might
 * be encrypted. That flag is the eligibility rule the mechanism has always
 * had: a format that MAY carry an encrypted entry keeps the ciphers, because
 * encryption is discovered per entry and the release must decide before it
 * knows. KEEP_ZIPOLD is zip's Shrink, Reduce and Implode, which nothing else
 * calls.
 *
 * An ENVELOPE, KEEP_PEEK, keeps its own reader and what the format under it
 * keeps, when the first bytes of its payload say what that is
 * (unc_envelope_peek; DECISIONS.md 2026-11-03, *the envelope that said what
 * it held*); when they do not, or say another envelope, it keeps the whole
 * bundle, as every envelope did before.
 *
 * A format that is NOT here keeps the whole bundle, which costs memory and
 * loses nothing: MIME, whose parts can be anything; the segment schemes
 * that join to a FILE (StuffIt's, DiskDoubler's, plain NAME.001, MIME's
 * partial), because what they join is unknown until it is joined; Private
 * File, whose reader is in the StuffIt image and its key setup in the
 * ciphers', and which always decrypts to a StuffIt archive unwrapped next;
 * and any format nobody has added here yet, which is the answer that cannot
 * be wrong. */
#define KEEP_CRYPT  0x80
#define KEEP_PEEK   0x40
#define KEEP_ZIPOLD 0x20
#define KEEP(id, flags) ((unsigned char)(((id) - OVL_ID_CRYPT + 1) | (flags)))
static const unsigned char gKeepSet[UNC_FORMAT__COUNT] = {
    [UNC_FORMAT_SPACESAVER]  = KEEP(OVL_ID_SPACESAVER, 0),
    [UNC_FORMAT_COMPACTPRO]  = KEEP(OVL_ID_CPTDD,      KEEP_CRYPT),
    [UNC_FORMAT_DISKDOUBLER] = KEEP(OVL_ID_CPTDD,      0),
    [UNC_FORMAT_LZH]         = KEEP(OVL_ID_LZH,        0),
    [UNC_FORMAT_ARC]         = KEEP(OVL_ID_ARC,        KEEP_CRYPT),
    [UNC_FORMAT_NOWCOMPRESS] = KEEP(OVL_ID_NOW,        0),
    [UNC_FORMAT_SUPERDISK]   = KEEP(OVL_ID_SUPERDISK,  0),
    [UNC_FORMAT_PACKIT]      = KEEP(OVL_ID_PACKIT,     KEEP_CRYPT),
    /* An AppleLink package cannot be encrypted: the format has no password
     * anywhere in it, and its own expander never asks for one. */
    [UNC_FORMAT_SQP]         = KEEP(OVL_ID_SQP,        0),
    [UNC_FORMAT_SIT]         = KEEP(OVL_ID_STUFFIT,    KEEP_CRYPT),
    [UNC_FORMAT_SIT5]        = KEEP(OVL_ID_STUFFIT,    KEEP_CRYPT),
    [UNC_FORMAT_ZIP]         = KEEP(OVL_ID_EXO,        KEEP_CRYPT | KEEP_ZIPOLD),
    [UNC_FORMAT_TAR]         = KEEP(OVL_ID_ZIPOLD,     0),
    /* No password anywhere in the format. */
    [UNC_FORMAT_MAR]         = KEEP(OVL_ID_ZIPOLD,     0),
    [UNC_FORMAT_TOME]        = KEEP(OVL_ID_ZIPOLD,     0),
    /* Segment SCHEMES, from the other release site: a Compact Pro or spanned
     * zip set is read by that format's own reader over the joined parts. */
    [UNC_FORMAT_CPTSEG]      = KEEP(OVL_ID_CPTDD,      KEEP_CRYPT),
    [UNC_FORMAT_ZIPSEG]      = KEEP(OVL_ID_EXO,        KEEP_CRYPT | KEEP_ZIPOLD),
    /* An Apple Backup set: its reader and its match, no password. */
    [UNC_FORMAT_ABK]         = KEEP(OVL_ID_ZIPOLD,     0),
    /* Envelopes, by the image their reader is in. */
    [UNC_FORMAT_BINHEX]      = KEEP(OVL_ID_BINHEX,     KEEP_PEEK),
    [UNC_FORMAT_BINHEX_OLD]  = KEEP(OVL_ID_BINHEX,     KEEP_PEEK),
    [UNC_FORMAT_DL]          = KEEP(OVL_ID_BINHEX,     KEEP_PEEK),
    [UNC_FORMAT_MACBINARY]   = KEEP(OVL_ID_BINHEX,     KEEP_PEEK),
    [UNC_FORMAT_APPLESINGLE] = KEEP(OVL_ID_BINHEX,     KEEP_PEEK),
    [UNC_FORMAT_APPLEDOUBLE] = KEEP(OVL_ID_BINHEX,     KEEP_PEEK),
    [UNC_FORMAT_GZIP]        = KEEP(OVL_ID_EXO,        KEEP_PEEK),
    [UNC_FORMAT_COMPRESS_Z]  = KEEP(OVL_ID_EXO,        KEEP_PEEK),
    [UNC_FORMAT_LZ4]         = KEEP(OVL_ID_ZIPOLD,     KEEP_PEEK),
    [UNC_FORMAT_UU]          = KEEP(OVL_ID_TEXT,       KEEP_PEEK),
    [UNC_FORMAT_BASE64]      = KEEP(OVL_ID_TEXT,       KEEP_PEEK),
    [UNC_FORMAT_BTOA]        = KEEP(OVL_ID_BTOA,       KEEP_PEEK),
};

/* The row for `fmt`, or 0. A peek answers in a byte, so the bound is
 * checked here rather than trusted. */
static unsigned keep_row(unsigned fmt)
{
    return fmt < UNC_FORMAT__COUNT ? gKeepSet[fmt] : 0;
}

/* The plan for `fmt`, read from `io` where it has to be, into `out`:
 * out[0] the format a peek named under an envelope (0 if none), out[1] the
 * envelope's own reader, for the layer under it to give back, and from
 * out[2] the images to keep, each as an offset from 128, one per keep — an
 * image kept twice is listed twice. Returns how many, or 0 to keep the
 * whole bundle. `sniff` is the sniffer's image, which answers the peek and
 * the encryption check; without it every answer is UNKNOWN. */
static int release_plan(const OverlayHost *host, OverlayEntry sniff,
                        UncFormat fmt, UncIO *io, unsigned char *out)
{
    unsigned char *k = out + 2;
    unsigned row, want, inner = 0;
    int enc = UNC_ENC_UNKNOWN;
    UncFormat as = fmt;     /* whose rules the ciphers and zipold follow */

    /* The sniffer's image (OVL_ID_SNIFF) is in no keep set, on purpose: it
     * has answered by the time this runs, and every later sniff — the next
     * archive after the reload — finds the bundle whole (DECISIONS.md
     * 2026-10-21, *the probes that left with the bundle*). An envelope that
     * was peeked into keeps it for the layer under it, which is sniffed
     * after this. */
    row = keep_row(fmt);
    if (!row) return 0;
    want = (row & 0x1f) - 1;
    if (row & KEEP_PEEK) {
        UncAlloc pal;
        int32_t r;
        if (!sniff) return 0;
        pal.ctx = NULL;
        pal.alloc = peek_alloc;
        pal.free = peek_free;
        r = sniff(host, OVL_ENVELOPE_PEEK, io, &pal);
        enc = (int)((r >> 8) & 0xff) - 1;
        as = (UncFormat)(r & 0xff);
        row = keep_row(as);
        if (!row || (row & KEEP_PEEK)) return 0;
        inner = (row & 0x1f) - 1;
        /* One image can serve both: an LZ4 frame and the MAR in it are
         * both `ovl_zipold`'s, kept twice and given back once. Kept once
         * and given back with the frame, the MAR layer ran with its image
         * gone, "Archive damaged." (measured 2026-11-03; DECISIONS.md, *the
         * frame mar 0.2.0 reads*). */
    }

    /* Compact Pro and zip keep a per-entry encryption flag in a directory
     * that can be walked before anything is decoded, and StuffIt 5's header
     * says whether its reader can decrypt anything at all, so for those
     * three the ciphers are kept only when an entry can need them
     * (unc_archive_encrypted; under an envelope, the peek's answer over the
     * first bytes, which only StuffIt 5's header can give). Anything else —
     * a format that flags encryption per entry with no directory (StuffIt,
     * PackIt), one that does not flag it at all (ARC), or a header or
     * directory that would not read — answers UNKNOWN, and UNKNOWN is
     * treated as YES.
     *
     * This is the only place the answer may be acted on: there is no reload,
     * so releasing the ciphers on a maybe would lose an entry rather than
     * cost a disk access. */
    if ((row & KEEP_CRYPT) && (as == UNC_FORMAT_COMPACTPRO ||
                               as == UNC_FORMAT_ZIP || as == UNC_FORMAT_SIT5)) {
        if (as == fmt && sniff)
            enc = (int)sniff(host, OVL_ARCHIVE_ENCRYPTED, io,
                             (void *)(long)fmt);
        if (enc == UNC_ENC_NO) row &= ~KEEP_CRYPT;
    }

    out[0] = 0;
    out[1] = (unsigned char)want;
    *k++ = (unsigned char)want;
    if (as != fmt) {
        out[0] = (unsigned char)as;
        *k++ = (unsigned char)inner;
        *k++ = OVL_ID_SNIFF - OVL_ID_CRYPT;
    }
    if (row & KEEP_ZIPOLD) *k++ = OVL_ID_ZIPOLD - OVL_ID_CRYPT;
    if (row & KEEP_CRYPT) *k++ = 0;             /* OVL_ID_CRYPT */
    /* And ALWAYS the codecs, because every decoder calls into them: the bit
     * reader, the Huffman and canonical coders, LZW and LZAH live there and
     * are reached through pointers in the host vector. Releasing the bundle
     * without keeping this image left those pointers aimed at memory that had
     * been given back — which is not a wrong answer but no answer at all:
     * every decoder stub failed at ovl_codecs_ready() and the archive
     * produced nothing. */
    *k++ = OVL_ID_CODECS - OVL_ID_CRYPT;
    return (int)(k - (out + 2));
}
