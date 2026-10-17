/*
 * fmt_applesingle.c — AppleSingle / AppleDouble decoder.
 *
 * Source: reference/notes/rfc1740.txt, appendices A and B — the whole
 * header, the predefined entry ids, and the epoch entry 8's dates are
 * counted from.
 *
 *   u32 magic     0x00051600 = AppleSingle, 0x00051607 = AppleDouble
 *   u32 version   0x00020000
 *   16 bytes filler (RFC: "all zeros")
 *   u16 count
 *   count × { u32 id, u32 offset, u32 length }
 *
 * Entry ids used: 1 = data fork, 2 = resource fork, 3 = real name,
 * 4 = comment ("Standard Macintosh comment"), 8 = dates ("the number of
 * seconds before or after 12:00 a.m. (midnight), January 1, 2000
 * Greenwich Mean Time", create/modify/backup/access, "Any unknown
 * entries are set to 0x80000000"), 9 = Finder info (FInfo then FXInfo,
 * 16 bytes each: type 4, creator 4, flags 2, ...), 10 = Macintosh file
 * info (three filler bytes, then ioFlAttrib, whose 0x01 is AS_LOCKED),
 * 12 = MS-DOS file info (a filler byte, then the attribute, whose 0x01
 * is AS_DOS_READONLY). Read-only on DOS is how HFS spells locked, so
 * either bit locks the file.
 *
 * ONE tolerance here is not the RFC's, and cannot be, because the RFC
 * forbids what it tolerates: "byte ordering in the file fields follows
 * MC68000 conventions, most significant byte first". The byte-swapped
 * magics 0x00160500 / 0x07160500 and version 0x00000200 below accept a
 * header written the other way round, and read the entry table to
 * match. XADMaster is the sole source of that — LGPL, see NOTICE.
 * Source: reference/XADMaster/XADAppleSingleParser.m. It stops at the table:
 * the CONTENTS of entries 8 and 9 are read big-endian whatever the
 * header said, because the RFC defines them as Macintosh structures
 * rather than as header fields.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define AS_MAGIC_SINGLE     0x00051600u
#define AS_MAGIC_DOUBLE     0x00051607u
#define AS_MAGIC_SINGLE_LE  0x00160500u
#define AS_MAGIC_DOUBLE_LE  0x07160500u
#define AS_VERSION          0x00020000u
#define AS_VERSION_LE       0x00000200u

/* Seconds between the Mac epoch (1904-01-01) and the AppleSingle
 * dates epoch (2000-01-01): 96 years of 365 days + 24 leap days =
 * 35064 days = 3029529600 s = 0xB492F400 (naive time, no leap secs). */
#define AS_EPOCH_2000_AS_MAC 0xB492F400u

UncFormat unc_applesingle_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t magic, version;
    (void)io;
    if (len < 8) return UNC_FORMAT_UNKNOWN;
    magic = unc_get_u32be(head);
    version = unc_get_u32be(head + 4);
    if (magic != AS_MAGIC_SINGLE && magic != AS_MAGIC_DOUBLE &&
        magic != AS_MAGIC_SINGLE_LE && magic != AS_MAGIC_DOUBLE_LE)
        return UNC_FORMAT_UNKNOWN;
    if (version != AS_VERSION && version != AS_VERSION_LE)
        return UNC_FORMAT_UNKNOWN;
    return (magic == AS_MAGIC_SINGLE || magic == AS_MAGIC_SINGLE_LE)
         ? UNC_FORMAT_APPLESINGLE : UNC_FORMAT_APPLEDOUBLE;
}

/* Cap on the entry table: real files have <10 entries; 64 is generous
 * and keeps the on-stack table small (64 * 12 = 768 bytes). */
#define AS_MAX_ENTRIES 64

static uint32_t as_get_u32(const uint8_t *p, int be)
{
    return be ? unc_get_u32be(p) : unc_get_u32le(p);
}

static int as_stream_fork(UncCtx *c, UncFork fork, uint32_t offs,
                          uint32_t size, uint8_t *buf, uint32_t bufsz)
{
    if (c->io->seek(c->io->ctx, offs) < 0) return UNC_ERR_IO;
    return unc_copy_fork(c, fork, size, buf, bufsz);
}

int unc_appledouble_extract(UncCtx *c)
{
    uint8_t hdr[26];
    uint8_t etab[AS_MAX_ENTRIES * 12];
    /* Big enough for the longest name the engine carries: this
     * was 64 until 2026-08-27, which cut a real-name entry
     * without saying so (DECISIONS.md, the name cap). */
    uint8_t tmp[UNC_NAME_MAX + 1];
    UncEntryInfo e;
    uint32_t magic, filesize;
    int be, i, n, err, sret;
    uint32_t dataoffs = 0, datalen = 0, rsrcoffs = 0, rsrclen = 0;
    int have_data = 0, have_rsrc = 0;
    uint32_t cmtoffs = 0, cmtlen = 0, n32;
    int cut = 0;


    err = unc_read_at(c->io, 0, hdr, 26);
    if (err != UNC_OK) return err;

    magic = unc_get_u32be(hdr);
    if (magic == AS_MAGIC_SINGLE || magic == AS_MAGIC_DOUBLE) be = 1;
    else if (magic == AS_MAGIC_SINGLE_LE || magic == AS_MAGIC_DOUBLE_LE) be = 0;
    else return UNC_ERR_FORMAT;

    filesize = unc_io_size32(c->io);

    n = be ? unc_get_u16be(hdr + 24) : unc_get_u16le(hdr + 24);
    if (n > AS_MAX_ENTRIES) n = AS_MAX_ENTRIES;  /* ignore the excess */
    err = unc_read_full(c->io, etab, n * 12);
    if (err != UNC_OK) return err;

    unc_entry_clear(&e);

    for (i = 0; i < n; i++) {
        const uint8_t *ent = etab + i * 12;
        uint32_t id   = as_get_u32(ent, be);
        uint32_t offs = as_get_u32(ent + 4, be);
        uint32_t elen = as_get_u32(ent + 8, be);

        /* An entry that runs past the end of the file means the file was
         * CUT: the table states every entry's offset and length (RFC 1740,
         * appendix B), so bytes it promises and the file lacks are bytes
         * that went missing. Until 2026-10-17 such an entry was skipped and
         * the file called complete — `unar` calls it broken, and so does
         * every other walk here (tools/run_truncation.py, which found it
         * with the corpus's first AppleSingle fixtures). The forks are
         * still streamed, so what is there comes out and their own read
         * ends the entry as truncated; any other entry is dropped. */
        if (filesize != UNC_SIZE_UNKNOWN &&
            (offs > filesize || elen > filesize - offs)) {
            cut = 1;
            if (id != 1 && id != 2) continue;
        }

        /* Entries 8 to 12 are fixed records of at most 32 bytes: one read
         * for all of them, before the switch. */
        n32 = 0;
        if (id >= 8 && id <= 12) {
            n32 = elen < 32 ? elen : 32;
            if (unc_read_at(c->io, offs, tmp, (int32_t)n32) != UNC_OK)
                continue;
        }

        switch (id) {
        case 1: dataoffs = offs; datalen = elen; have_data = 1; break;
        case 2: rsrcoffs = offs; rsrclen = elen; have_rsrc = 1; break;
        case 3: /* real name */
            if (elen > 0) {
                uint32_t nl = elen < sizeof tmp ? elen : (uint32_t)sizeof tmp;
                if (unc_read_at(c->io, offs, tmp, (int32_t)nl) == UNC_OK) {
                    unc_entry_set_name(&e, tmp, nl);
                    if (elen > nl) {
                        e.name_truncated = 1;
                        e.name_full_len = (uint16_t)(elen > 65535u ? 65535u
                                                                   : elen);
                        /* The entry is still on disk in front of us, so
                         * a host with room can be handed all of it. */
                        if (c->opt.long_name && c->opt.long_name_cap > 1) {
                            uint32_t want = elen < c->opt.long_name_cap - 1u
                                          ? elen : c->opt.long_name_cap - 1u;
                            if (unc_read_at(c->io, offs, c->opt.long_name,
                                            (int32_t)want) == UNC_OK) {
                                c->opt.long_name[want] = 0;
                                e.name_truncated = 2;
                            }
                        }
                    }
                }
            }
            break;
        case 4: /* comment: read once the table is done, into tmp */
            cmtoffs = offs;
            cmtlen = elen;
            break;
        case 8: /* dates: always big-endian, epoch 2000 (file comment) */
            if (n32 >= 8) {
                e.create_date = unc_get_u32be(tmp) + AS_EPOCH_2000_AS_MAC;
                e.mod_date    = unc_get_u32be(tmp + 4) + AS_EPOCH_2000_AS_MAC;
                /* The backup date only: 0x80000000 is the RFC's "unknown",
                 * and is kept unknown. The two dates above are added to
                 * blindly, as before; that is a reader's fix of its own. */
                if (n32 >= 12 && unc_get_u32be(tmp + 8) != 0x80000000u) {
                    e.backup_date = unc_get_u32be(tmp + 8) +
                                    AS_EPOCH_2000_AS_MAC;
                    e.meta |= UNC_META_BACKUP;
                }
            }
            break;
        case 9: /* Finder info: FInfo, then FXInfo */
            if (n32 >= 10) {
                e.type         = unc_get_u32be(tmp);
                e.creator      = unc_get_u32be(tmp + 4);
                e.finder_flags = unc_get_u16be(tmp + 8);
                if (n32 >= 32) {
                    int k;
                    for (k = 0; k < 32; k++) e.finder_info[k] = tmp[k];
                    e.meta |= UNC_META_FINFO | UNC_META_FXINFO;
                }
            }
            break;
        case 10: /* Macintosh file info: ioFlAttrib in the fourth byte */
        case 12: /* MS-DOS file info: the attribute in the second byte */
            {
                uint32_t at = id == 10 ? 3u : 1u;
                if (n32 > at && e.locked != UNC_LOCK_YES)
                    e.locked = (tmp[at] & 0x01) ? UNC_LOCK_YES : UNC_LOCK_NO;
            }
            break;
        default:
            break;
        }
    }

    /* A file with no "real name" entry has no name at all — Netatalk
     * writes AppleDouble sidecars that way, and every `._X` beside an
     * `X` on a Mac volume is one. The host's filename is then the only
     * name there is, which is what every other name-less format here
     * does (gzip, .Z, the DiskDoubler single-file container, `SPLT`,
     * uuencode). Without this the sink is handed an empty name and
     * writes "_". */
    if (e.name_len == 0 && c->opt.name_hint && c->opt.name_hint_len)
        unc_entry_set_name(&e, c->opt.name_hint, c->opt.name_hint_len);

    /* The comment, into tmp now that the name is out of it: tmp lives
     * until this function returns, which is after end_entry. */
    if (cmtlen) {
        uint32_t cl = cmtlen < UNC_ENTRY_COMMENT_MAX ? cmtlen
                                                    : UNC_ENTRY_COMMENT_MAX;
        if (unc_read_at(c->io, cmtoffs, tmp, (int32_t)cl) == UNC_OK) {
            e.comment = tmp;
            e.comment_len = (uint16_t)cl;
        }
    }

    e.data_size = have_data ? datalen : 0;
    e.rsrc_size = have_rsrc ? rsrclen : 0;
    e.comp_data_size = e.data_size;
    e.comp_rsrc_size = e.rsrc_size;

    sret = c->sink->begin_entry(c->sink->ctx, &e);
    if (sret < 0) return UNC_ERR_SINK;
    if (sret > 0) return UNC_OK;

    err = UNC_OK;
    if (!c->opt.list_only) {
        uint32_t bufsz = UNC_PROGRESS_STEP;
        uint8_t *buf = (uint8_t *)unc_alloc(c->al, bufsz);
        if (!buf) err = UNC_ERR_MEM;
        if (err == UNC_OK) {
            if (have_data && datalen > 0)
                err = as_stream_fork(c, UNC_FORK_DATA, dataoffs, datalen,
                                     buf, bufsz);
            if (err == UNC_OK && have_rsrc && rsrclen > 0)
                err = as_stream_fork(c, UNC_FORK_RSRC, rsrcoffs, rsrclen,
                                     buf, bufsz);
            unc_free(c->al, buf);
        }
        if (cut && (err == UNC_OK || err == UNC_ERR_IO))
            err = UNC_ERR_TRUNCATED;
    }

    if (c->sink->end_entry(c->sink->ctx, err) < 0) return UNC_ERR_SINK;
    if (unc_fatal(err))
        return err;
    return UNC_OK;
}
