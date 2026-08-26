/*
 * fmt_stubs.c — detect-only probes: formats v1 names in unc_sniff but
 * does not extract, so a UI can tell the user what the file is.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* StuffIt X: 8-byte magic "StuffIt!" or "StuffIt?".
 * Source: reference/XADMaster/XADStuffItXParser.m. */
int unc_sitx_probe(const uint8_t *head, int32_t len)
{
    if (len < 8) return 0;
    return head[0] == 'S' && head[1] == 't' && head[2] == 'u' &&
           head[3] == 'f' && head[4] == 'f' && head[5] == 'I' &&
           head[6] == 't' && (head[7] == '!' || head[7] == '?');
}

/* Now Compress: 00 02 magic, plausible file count, Pascal name, and a
 * byte-sum checksum over bytes 24..129 stored at 130.
 * Source: reference/XADMaster/XADNowCompressParser.m. */
int unc_nowcompress_probe(const uint8_t *head, int32_t len)
{
    uint32_t nfiles, sum;
    int32_t i;
    if (len < 134) return 0;
    if (head[0] != 0x00 || head[1] != 0x02) return 0;
    nfiles = unc_get_u32be(head + 8);
    if (nfiles == 0 || nfiles > 0xFFFF) return 0;
    if (head[24] == 0 || head[24] > 31) return 0;
    for (i = 0; i < head[24]; i++)
        if (head[25 + i] < 32) return 0;
    sum = 0;
    for (i = 24; i < 130; i++) sum += head[i];
    return sum == unc_get_u32be(head + 130);
}

/* DiskDoubler: 0xABCD0054 magic + XMODEM CRC of the 82-byte header
 * (or 0 in very old files), or the 'DDAR' archive variant.
 * Source: reference/XADMaster/XADDiskDoublerParser.m — its
 * reversed-table CRC formulation equals plain CRC-16/XMODEM, see
 * DECISIONS.md M0. */
int unc_diskdoubler_probe(const uint8_t *head, int32_t len)
{
    if (len >= 84 && unc_get_u32be(head) == 0xABCD0054u) {
        uint16_t crc = unc_get_u16be(head + 82);
        if (crc == 0 || crc == unc_crc16_xmodem(0, head, 82)) return 1;
    }
    if (len >= 78 && unc_get_u32be(head) == 0x44444152u &&    /* 'DDAR' */
        unc_get_u16be(head + 76) == unc_crc16_xmodem(0, head, 76)) return 1;
    if (len >= 62 && unc_get_u32be(head) == 0x44444132u &&    /* 'DDA2' */
        unc_get_u16be(head + 60) == unc_crc16_xmodem(0, head, 60)) return 1;
    return 0;
}

/* DiskCopy 4.2 disk image — DETECT ONLY (disk images are out of scope for
 * v1; naming the format lets a UI tell the user what the file is).
 *
 * Header is 84 bytes, big-endian:
 *   0x00  1   Pascal length of the image name (<= 63)
 *   0x01  63  image name, NUL-padded
 *   0x40  4   data size, bytes, of the block at 0x54
 *   0x44  4   tag size, bytes, of the block after the data
 *   0x48  4   data checksum        0x4C  4  tag checksum
 *   0x50  1   disk encoding        0x51  1  format byte
 *   0x52  2   magic "private word", always 0x0100
 *
 * Source: reference/notes/DiskCopy42.md (transcribed from
 * discferret.com/wiki/Apple_DiskCopy_4.2; XADMaster has no DiskCopy parser).
 *
 * The magic word alone is only 16 bits and would false-positive freely, so
 * the probe also requires a sane name length and an encoding byte whose
 * disk type matches the declared data size. The format byte at 0x51 is NOT
 * checked: 0x22 is shared by 800K GCR, 720K MFM and 1440K MFM, so it
 * discriminates nothing. */
int unc_diskcopy_probe(const uint8_t *h, int32_t l, UncIO *io)
{
    uint32_t data_size, tag_size;
    uint8_t encoding;

    (void)io;
    if (l < 84) return 0;
    if (unc_get_u16be(h + 0x52) != 0x0100) return 0;
    if (h[0] > 63) return 0;                     /* Pascal name length */

    data_size = unc_get_u32be(h + 0x40);
    tag_size  = unc_get_u32be(h + 0x44);
    encoding  = h[0x50];

    /* Data size must be the one this encoding implies. */
    switch (encoding) {
        case 0x00: if (data_size !=  409600u) return 0; break;  /* 400K GCR  */
        case 0x01: if (data_size !=  819200u) return 0; break;  /* 800K GCR  */
        case 0x02: if (data_size !=  737280u) return 0; break;  /* 720K MFM  */
        case 0x03: if (data_size != 1474560u) return 0; break;  /* 1440K MFM */
        default:   return 0;
    }

    /* Tags: 12 bytes per 512-byte sector on the GCR formats, or absent. The
     * MFM formats can never carry them — a PC 720K/1.44M sector has no room
     * beyond its 512 bytes — so there tag_size must be 0. */
    if (encoding <= 0x01) {
        if (tag_size != 0 && tag_size != (data_size / 512u) * 12u) return 0;
    } else {
        if (tag_size != 0) return 0;
    }
    return 1;
}

/* ------------------------------------------------------------------ */
/* Every OTHER disk image — DETECT ONLY, and for the same reason as     */
/* DiskCopy 4.2 above: extraction means a filesystem rather than a      */
/* codec and stays out by the brief, but a file this engine cannot      */
/* name reads to a user as a corrupt archive.                           */
/*                                                                      */
/* Nothing here looks at an extension. What `.iso`, `.cdr`, `.toast`,   */
/* `.img` and an uncompressed `.dmg` have in common is the volume       */
/* INSIDE them, so the probe reads that instead, in four shapes:        */
/*                                                                      */
/*   HFS master directory block  "BD" at 1024, allocation block size a  */
/*                               nonzero multiple of 512                */
/*   HFS+ / HFSX volume header   "H+" or "HX" at 1024                   */
/*   Apple Partition Map         "PM\0\0" at 512 AND at 1024            */
/*   ISO 9660 / High Sierra      a volume descriptor at sector 16 and   */
/*                               at sector 17, in any of the four       */
/*                               sector layouts a CD image uses         */
/*                                                                      */
/* Source: reference/deark/modules/hfs.c (de_identify_hfs),             */
/* reference/deark/modules/apm.c (de_identify_apm, and the HFS+/HFSX    */
/* signatures it reads at partition+1024), and                          */
/* reference/deark/modules/iso9660.c (cdsig_at, de_identify_iso9660,    */
/* cdraw_detect_params). XADMaster's XADISO9660Parser.m scans for the   */
/* same descriptor pair.                                                */
/*                                                                      */
/* All of it sits past the 512-byte sniff window, so this probe reads   */
/* through io and `head` is unused.                                     */
/* ------------------------------------------------------------------ */

/* One ISO 9660 / High Sierra / CD-I volume descriptor at `pos`.
 * Source: cdsig_at() in reference/deark/modules/iso9660.c. */
static int cd_desc_at(UncIO *io, uint32_t pos)
{
    uint8_t b[14];
    uint8_t ty;

    if (unc_read_at(io, pos, b, 14) != UNC_OK) return 0;
    if (b[1] == 'C' && b[2] == 'D' && b[3] == '0' && b[4] == '0' &&
        b[5] == '1') ty = b[0];                              /* ISO 9660  */
    else if (b[1] == 'C' && b[2] == 'D' && b[3] == '-' && b[4] == 'I' &&
             b[5] == ' ') ty = b[0];                         /* CD-I      */
    else if (b[9] == 'C' && b[10] == 'D' && b[11] == 'R' && b[12] == 'O' &&
             b[13] == 'M') ty = b[8];                        /* High Sierra */
    else return 0;
    return ty <= 3 || ty == 255;
}

/* The four sector layouts, as `cdraw_detect_params` reads them: 2048-byte
 * logical sectors, then the raw ones (2336 with an 8-byte subheader, 2352
 * with a 16-byte header, 2352 with both). Sector 16 carries the primary
 * descriptor and sector 17 the next one, and requiring BOTH is what keeps
 * a five-character string from claiming a file on its own. */
static int cd_image(UncIO *io)
{
    static const uint32_t sector[4] = { 2048u, 2336u, 2352u, 2352u };
    static const uint32_t skip[4]   = {    0u,    8u,   16u,   24u };
    int i;

    for (i = 0; i < 4; i++) {
        uint32_t at = sector[i] * 16u + skip[i];
        if (cd_desc_at(io, at) && cd_desc_at(io, at + sector[i])) return 1;
    }
    return 0;
}

int unc_diskimage_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint8_t b[24];
    uint32_t size;

    (void)head;
    (void)len;
    if (!io) return 0;
    size = io->size(io->ctx);

    /* The first three all live in the block at 1024, so they share one
     * read. A file shorter than that is not an image of any disk. */
    if (unc_read_at(io, 1024, b, 24) == UNC_OK) {
        uint16_t sig = unc_get_u16be(b);

        /* HFS. The signature is 16 bits, so the allocation block size
         * corroborates it — deark requires exactly this pair. */
        if (sig == 0x4244) {                                   /* "BD" */
            uint32_t alblksiz = unc_get_u32be(b + 20);
            if (alblksiz != 0 && (alblksiz % 512u) == 0) return 1;
        }

        /* HFS+ (Mac OS 8.1 and later) and HFSX. deark reads these two
         * signatures at the same offset, but parses no further, so there
         * is no second field here to check and 16 bits would claim a file
         * of random bytes once in 65,536. What corroborates it is not a
         * format detail but a property of an IMAGE: it is a whole number
         * of 512-byte sectors. */
        if (sig == 0x482Bu || sig == 0x4858u) {                /* "H+", "HX" */
            if (size != UNC_SIZE_UNKNOWN && size >= 1536u &&
                (size % 512u) == 0) return 1;
        }

        /* Apple Partition Map: a map entry in sector 1 and another in
         * sector 2, which is deark's whole test. A partitioned image is
         * how a hard disk, a CD and an uncompressed .dmg all arrive. */
        if (b[0] == 'P' && b[1] == 'M' && b[2] == 0 && b[3] == 0) {
            uint8_t p[4];
            if (unc_read_at(io, 512, p, 4) == UNC_OK &&
                p[0] == 'P' && p[1] == 'M' && p[2] == 0 && p[3] == 0)
                return 1;
        }
    }

    /* ISO 9660 lives at sector 16, which is 32 KB in; skip the reads
     * entirely for anything too small to hold the pair (2048-byte
     * sectors, the tightest of the four layouts, ends its second
     * descriptor at 34,830). The wider layouts fail on a short read. */
    if (size == UNC_SIZE_UNKNOWN || size >= 34830u) {
        if (cd_image(io)) return 1;
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* AppleLink package (`.pkg`) — detect only                            */
/*                                                                     */
/*   Source: Aladdin's own reader, disassembled — `PKG Expand          */
/*   Translator`, `Othe` 0, out of a StuffIt Deluxe 3.5.1 installation */
/*   (DECISIONS.md 2026-08-23). The translator's recognise entry is    */
/*   @0x2952: it pulls WHITESPACE-DELIMITED TOKENS out of the file     */
/*   (@0xf18, which skips space, tab and CR, honours double quotes and */
/*   backslash escapes) and answers yes when                           */
/*                                                                     */
/*     token 1 == "Decode"       @0x2996, _CmpString, case-insensitive */
/*     token 3 == "to" or "into" @0x2a04 and @0x2a24                   */
/*                                                                     */
/*   so a package is TEXT, and this is its whole magic. There is no    */
/*   byte signature to find and none is invented here.                 */
/*                                                                     */
/* Detect only: what a `Decode` line then refers to has not been read  */
/* out of the expander, and no `.pkg` file has ever reached this       */
/* project to check a reading against (OPEN_ITEMS.md).                 */
/* ------------------------------------------------------------------ */

/* One whitespace-delimited token, lowercased, into `out` (NUL-ended).
 * Returns the offset just past it, or -1 at end of input. Quotes and
 * escapes are honoured as @0xf18 does, so `"Decode"` is `Decode`. */
static int32_t al_token(const uint8_t *h, int32_t len, int32_t at,
                        char *out, int32_t outmax)
{
    int32_t n = 0;
    int quoted = 0;

    while (at < len && (h[at] == ' ' || h[at] == '\t' || h[at] == '\r' ||
                        h[at] == '\n'))
        at++;
    if (at >= len) return -1;
    while (at < len) {
        uint8_t c = h[at];
        if (c == '"') { quoted = !quoted; at++; continue; }
        if (quoted && c == '\\' && at + 1 < len) { at++; c = h[at]; }
        else if (!quoted && (c == ' ' || c == '\t' || c == '\r' ||
                             c == '\n')) break;
        if (n < outmax - 1) {
            if (c >= 'A' && c <= 'Z') c = (uint8_t)(c + 32);
            out[n++] = (char)c;
        }
        at++;
    }
    out[n] = 0;
    return at;
}

/* No libc in the engine: a three-line compare instead of strcmp. */
static int al_is(const char *tok, const char *want)
{
    while (*want && *tok == *want) { tok++; want++; }
    return *want == 0 && *tok == 0;
}

int unc_applelink_probe(const uint8_t *head, int32_t len)
{
    char tok[32];
    int32_t at;

    if (len < 12) return 0;
    at = al_token(head, len, 0, tok, (int32_t)sizeof tok);
    if (at < 0 || !al_is(tok, "decode")) return 0;
    /* token 2 is what to decode, and may be anything at all */
    at = al_token(head, len, at, tok, (int32_t)sizeof tok);
    if (at < 0 || tok[0] == 0) return 0;
    at = al_token(head, len, at, tok, (int32_t)sizeof tok);
    if (at < 0) return 0;
    return al_is(tok, "to") || al_is(tok, "into");
}
