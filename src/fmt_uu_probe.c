/* fmt_uu_probe.c — uuencode's probe(s), kept resident.
 *
 * Split out so the decoder can live in an overlay: `unc_sniff` calls a probe
 * for every file it is handed, and a probe inside a blob would mean loading
 * the decoder to decide the file is not one (BRANCH_NOTES.md).
 *
 * The helpers below come with it and are used by the decoder as well, so this
 * file is compiled into that overlay TOO — one definition, two places.
 *
 * Source: unchanged from fmt_uu.c, whose provenance comments stand.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_uu_priv.h"
/* Used by the probe AND by the decoder, so it lives with the probe —
 * which the uu overlay compiles as well.
 *
 * Returns 0 when the line cannot be a data line, else the mask of the
 * alphabets it fits: UU_TBL_PC, UU_TBL_UNIX, or both. A document is
 * written with ONE of them, so a caller walking a document ANDs these
 * masks as it goes and a line that does not fit what the document has
 * used so far is mail. A line that fits NEITHER is not data at all,
 * and that is what the probe rests on: an English sentence after a
 * "begin" line declares 45 bytes and is short enough to be a data
 * line, and what rejects it is having a space AND lower case.
 *
 * Source: UUTool's own two encode tables, `HEXA` 128 "PC" and `HEXA`
 * 129 "UNIX", read out of the application (tools/derive_mu.py
 * --tables). "PC" is the standard alphabet, 0x20..0x5f. "UNIX" moves
 * the low values up past it so that NO value encodes to a space —
 * 2.0.4 moves 30 of them, to 0x60..0x7d, and 2.3.2 moves 27, to
 * 0x60..0x7a ("changed UNIX encoding table to ignore {,}", its own
 * revision log) — and it is the table UUTool uses unless "use
 * original coding" is set, so its DEFAULT output is not in the
 * standard alphabet at all.
 *
 * And 0x60, which is in the UNIX range as a value of its own, is also
 * the standard alphabet's OTHER spelling of zero: Unix `uuencode`
 * writes the value 0 as '`' rather than as a space, so a mailer
 * stripping trailing whitespace cannot eat it (UU_PC_MAX in
 * fmt_uu_priv.h carries the citation). It narrows nothing, and the
 * mask is therefore the union of
 * three spellings rather than two tables. Requiring 0x20..0x5f of the
 * "PC" half instead, between 2026-10-06 and 2026-10-07, made every file
 * BSD and GNU uuencode write unreadable: a line carrying a zero AND a
 * value under 27 fits neither half, so it was skipped as mail and the
 * document decoded to nothing, with no checksum anywhere to object
 * (BLOCKERS.md; DECISIONS.md 2026-10-07).
 *
 * What matters for telling data from mail survives that: the UNIX half
 * excludes 0x20..0x3a and the PC half excludes 0x61..0x7d, so prose
 * needs only a space and one lower-case letter to fit neither.
 * UU_SIXB decodes every table, the & 0x3f doing the work. */
int unc_uu_line_is_data(const uint8_t *p, int32_t len)
{
    int32_t outcount, incount, i;
    int mask = UU_TBL_ANY;

    if (len < 1) return 0;
    outcount = UU_SIXB(p[0]);
    if (outcount == 0 || outcount > 45) return 0;
    incount = ((outcount / 3) + 1) * 4;
    /* Trailing spaces may have been stripped; the line may be short,
     * never long. */
    if (len > incount + 1) return 0;
    /* One unsigned subtraction decides all three questions: the two
     * alphabets are contiguous ranges inside 0x20..0x7d, so a
     * character is out of range, above "PC"'s top, or below "UNIX"'s
     * bottom, and the last two are disjoint. The count character is
     * judged with the rest — it comes from the same table, and below
     * 27 the two tables spell it differently. */
    for (i = 0; i < len; i++) {
        uint8_t c = (uint8_t)(p[i] - UU_CH_MIN);
        if (c > (uint8_t)(UU_CH_MAX - UU_CH_MIN)) return 0;
        if (c > (uint8_t)(UU_PC_MAX - UU_CH_MIN)) mask &= ~UU_TBL_PC;
        else if (c < (uint8_t)(UU_UNIX_MIN - UU_CH_MIN))
            mask &= ~UU_TBL_UNIX;
    }
    return mask;
}

UncFormat unc_uu_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    int32_t i = 0;

    while (i < len) {
        int32_t ls = i, le;
        while (i < len && head[i] != '\n' && head[i] != '\r') i++;
        le = i;
        while (i < len && (head[i] == '\n' || head[i] == '\r')) i++;

        if (le - ls >= 6 && head[ls] == 'b' && head[ls + 1] == 'e' &&
            head[ls + 2] == 'g' && head[ls + 3] == 'i' &&
            head[ls + 4] == 'n' && head[ls + 5] == ' ') {
            /* Next non-empty line must be a uu data line. */
            while (i < len) {
                int32_t ns = i, ne;
                while (i < len && head[i] != '\n' && head[i] != '\r') i++;
                ne = i;
                while (i < len && (head[i] == '\n' || head[i] == '\r')) i++;
                if (ne == ns) continue;                 /* blank */
                return (unc_uu_line_is_data(head + ns, ne - ns))
           ? UNC_FORMAT_UU : UNC_FORMAT_UNKNOWN;
            }
            return UNC_FORMAT_UNKNOWN;   /* begin line, but the file ends there */
        }
    }
    return UNC_FORMAT_UNKNOWN;
}
