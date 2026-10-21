/*
 * unc_sniff.c — format sniffing: the probe order, and the walk over it.
 *
 * Split from unc_engine.c on 2026-10-21 so that the Macintosh application
 * can carry it, with every probe, in an 'OVLY' image of its own, run from
 * the bundle before the release and given back with it (DECISIONS.md
 * 2026-10-21, *the probes that left with the bundle*). Nothing here
 * changed in the move; the resident control build links it as before.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

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
    /* 'SIT!' again, but with 'DFD3' behind it: SpaceSaver's header, and
     * the StuffIt probe above would never claim it (its second long is
     * 'rLau'). */
    unc_spacesaver_probe,
    unc_packit_probe,
    unc_gzip_probe,
    unc_compressz_probe,
    /* 'CSIT' and a version word, confirmed by a second 'CSIT' twelve
     * bytes from the end. Neither StuffIt probe above can take one: their
     * magics are 'SIT!' and the StuffIt 5 banner (fmt_pf.c). */
    unc_pf_probe,
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
     * in its last 512 bytes, so it pays a single read.
     *
     * It is also where a zip is recognised BEHIND something else — a
     * self-extracting archive, whose first bytes are code. The record
     * this probe already has in hand says where the central directory
     * is, absolutely, so the decoder needs nothing extra and neither
     * does the sniff: one four-byte read confirms the directory is
     * there. Nothing below is reached by such a file today, and nothing
     * above can be taken from it — every probe ahead of this one has a
     * magic number at a fixed offset, and 8,364 files that are not
     * archives were swept for the claim (FORMATS.md, *What the zip pair
     * claims, and what it costs*). */
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
