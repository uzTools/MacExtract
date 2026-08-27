/*
 * fmt_applesingle.c — AppleSingle / AppleDouble decoder.
 *
 * Layout transcribed from:
 *   Source: reference/XADMaster/XADAppleSingleParser.m — LGPL, see NOTICE.
 *
 *   u32 magic     0x00051600 = AppleSingle, 0x00051607 = AppleDouble
 *                 (byte-swapped variants 0x00160500 / 0x07160500 are
 *                 accepted as little-endian files, as XADMaster does)
 *   u32 version   0x00020000 (or LE-swapped)
 *   16 bytes filler
 *   u16 count
 *   count × { u32 id, u32 offset, u32 length }
 *
 * Entry ids used: 1 = data fork, 2 = resource fork, 3 = real name,
 * 8 = dates (always big-endian, epoch 2000-01-01), 9 = Finder info
 * (type 4, creator 4, flags 2, ...).
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


    err = unc_read_at(c->io, 0, hdr, 26);
    if (err != UNC_OK) return err;

    magic = unc_get_u32be(hdr);
    if (magic == AS_MAGIC_SINGLE || magic == AS_MAGIC_DOUBLE) be = 1;
    else if (magic == AS_MAGIC_SINGLE_LE || magic == AS_MAGIC_DOUBLE_LE) be = 0;
    else return UNC_ERR_FORMAT;

    filesize = c->io->size(c->io->ctx);

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

        /* Sanity-cap every offset/length against the file size. */
        if (filesize != UNC_SIZE_UNKNOWN &&
            (offs > filesize || elen > filesize - offs))
            continue;   /* skip corrupt entry, keep the rest */

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
        case 8: /* dates: always big-endian, epoch 2000 (see ref) */
            if (elen >= 8 && unc_read_at(c->io, offs, tmp, 8) == UNC_OK) {
                e.create_date = unc_get_u32be(tmp) + AS_EPOCH_2000_AS_MAC;
                e.mod_date    = unc_get_u32be(tmp + 4) + AS_EPOCH_2000_AS_MAC;
            }
            break;
        case 9: /* Finder info: type, creator, flags */
            if (elen >= 10 && unc_read_at(c->io, offs, tmp, 10) == UNC_OK) {
                e.type         = unc_get_u32be(tmp);
                e.creator      = unc_get_u32be(tmp + 4);
                e.finder_flags = unc_get_u16be(tmp + 8);
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
    }

    if (c->sink->end_entry(c->sink->ctx, err) < 0) return UNC_ERR_SINK;
    if (unc_fatal(err))
        return err;
    return UNC_OK;
}
