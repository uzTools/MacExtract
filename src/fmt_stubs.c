/*
 * fmt_stubs.c — detect-only probes: formats v1 names in unc_sniff but
 * does not extract, so a UI can tell the user what the file is.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* StuffIt X: 8-byte magic "StuffIt!" or "StuffIt?".
 * Source: reference/deark/modules/unsupported.c, which recognises the
 * same seven characters and the same two eighth ones (MIT, see NOTICE)
 * — a second reading of a magic number Aladdin never published, and
 * the reason this probe owes XADMaster nothing. */
UncFormat unc_sitx_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    if (len < 8) return UNC_FORMAT_UNKNOWN;
    return (head[0] == 'S' && head[1] == 't' && head[2] == 'u' &&
           head[3] == 'f' && head[4] == 'f' && head[5] == 'I' &&
           head[6] == 't' && (head[7] == '!' || head[7] == '?'))
           ? UNC_FORMAT_SITX : UNC_FORMAT_UNKNOWN;
}

/* Now Compress: 00 02 magic, plausible file count, Pascal name, and a
 * byte-sum checksum over bytes 24..129 stored at 130 — which is the
 * first ENTRY RECORD's own checksum, the record being 110 bytes from
 * 24 with a u32 at +106 summing the 106 before it.
 *
 * Source: docs/formats/now-compress.md, *The archive layer* — this
 * project's own description, where every field this tests is measured:
 * the 24-byte file header (0x0002, a version word, the entry count as
 * a u32 at +8), the record layout, and that checksum, which nine
 * archives here agree on. Until 2026-09-21 this cited
 * XADNowCompressParser.m, the only account of the format that existed;
 * `src/fmt_now.c` still does, for the code. */
UncFormat unc_nowcompress_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    uint32_t nfiles, sum;
    int32_t i;
    if (len < 134) return UNC_FORMAT_UNKNOWN;
    if (head[0] != 0x00 || head[1] != 0x02) return UNC_FORMAT_UNKNOWN;
    nfiles = unc_get_u32be(head + 8);
    if (nfiles == 0 || nfiles > 0xFFFF) return UNC_FORMAT_UNKNOWN;
    if (head[24] == 0 || head[24] > 31) return UNC_FORMAT_UNKNOWN;
    for (i = 0; i < head[24]; i++)
        if (head[25 + i] < 32) return UNC_FORMAT_UNKNOWN;
    sum = 0;
    for (i = 24; i < 130; i++) sum += head[i];
    return (sum == unc_get_u32be(head + 130))
           ? UNC_FORMAT_NOWCOMPRESS : UNC_FORMAT_UNKNOWN;
}

/* DiskDoubler: 0xABCD0054 magic + XMODEM CRC of the 82-byte header
 * (or 0 in very old files), 0xABCD0030 for the 1990 shape, or the
 * 'DDAR' archive variant.
 *
 * **That long is a word and a length**, measured 2026-09-22 by running
 * DiskDoubler ß05 (1990), which writes 48 where every one of the 195
 * headers in the corpus writes 84 (docs/formats/diskdoubler-container.md,
 * "The header size, and the 1990 header"). A short header ends before
 * `C_HDRCRC 82`, so there is no header CRC to check — and none of its
 * fill is one either: 0x00 through all six bytes at +42, where the two
 * forks' own sums are 0xd766 and 0x116a. So the second shape is matched
 * as a whole 32-bit constant exactly as the first is, and the size makes
 * the magic MORE specific rather than less. Only two values have a
 * specimen; that version's validator accepts any size from 48 up, which
 * is why the field is read as a size at all, but nothing here guesses
 * what a third would put where. Both references know only the 84-byte
 * shape — macutils states `MAGIC2 "\253\315\000\124"` as four bytes
 * and XADMaster compares `0xabcd0054` as a long — so the first path
 * below is byte-for-byte what it was and no corpus file reaches the new
 * one.
 *
 * Source for the first two: reference/macutils/macunpack/dd.h, which
 * states both magics and both header shapes — MAGIC2 "\253\315\000\124"
 * is the same four bytes, C_HDRCRC 82 in an 84-byte compressed-file
 * header, ARCHHDRCRC 76 in a 78-byte archive header. XADMaster's
 * XADDiskDoublerParser.m agrees and is where the CRC came from; its
 * reversed-table formulation equals plain CRC-16/XMODEM, see
 * DECISIONS.md M0.
 *
 * 'DDA2' is in neither: it is DiskDoubler Pro's, read off the CC0
 * specimens NOTICE credits, as the SPLT container in fmt_ddseg.c was. */
UncFormat unc_diskdoubler_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    if (len >= 84 && unc_get_u32be(head) == 0xABCD0054u) {
        uint16_t crc = unc_get_u16be(head + 82);
        if (crc == 0 || crc == unc_crc16_xmodem(0, head, 82)) return UNC_FORMAT_DISKDOUBLER;
    }
    if (len >= 48 && unc_get_u32be(head) == 0xABCD0030u)
        return UNC_FORMAT_DISKDOUBLER;
    if (len >= 78 && unc_get_u32be(head) == 0x44444152u &&    /* 'DDAR' */
        unc_get_u16be(head + 76) == unc_crc16_xmodem(0, head, 76)) return UNC_FORMAT_DISKDOUBLER;
    if (len >= 62 && unc_get_u32be(head) == 0x44444132u &&    /* 'DDA2' */
        unc_get_u16be(head + 60) == unc_crc16_xmodem(0, head, 60)) return UNC_FORMAT_DISKDOUBLER;
    return UNC_FORMAT_UNKNOWN;
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
/*   which is Aladdin's whole test. No byte signature is invented here.*/
/*                                                                     */
/* That transcription stands; what it does NOT do is name a real       */
/* package. Two arrived on 2026-09-26 and both are BINARY containers   */
/* this test rejects — one of them sniffs as a Compact Pro segment     */
/* instead (FORMATS.md, *AppleLink packages*; BLOCKERS.md). Kept and   */
/* not deleted, because it IS the translator's own recogniser; whether */
/* that routine is reached for a second shape of input is a boot       */
/* nobody has spent (OPEN_ITEMS.md).                                   */
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

UncFormat unc_applelink_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    char tok[32];
    int32_t at;

    if (len < 12) return UNC_FORMAT_UNKNOWN;
    at = al_token(head, len, 0, tok, (int32_t)sizeof tok);
    if (at < 0 || !al_is(tok, "decode")) return UNC_FORMAT_UNKNOWN;
    /* token 2 is what to decode, and may be anything at all */
    at = al_token(head, len, at, tok, (int32_t)sizeof tok);
    if (at < 0 || tok[0] == 0) return UNC_FORMAT_UNKNOWN;
    at = al_token(head, len, at, tok, (int32_t)sizeof tok);
    if (at < 0) return UNC_FORMAT_UNKNOWN;
    return (al_is(tok, "to") || al_is(tok, "into"))
           ? UNC_FORMAT_APPLELINK : UNC_FORMAT_UNKNOWN;
}
