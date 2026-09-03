/*
 * fmt_sit5.c — StuffIt 5+ container (.sit).
 *
 * Source: reference/XADMaster/XADStuffIt5Parser.m — LGPL, see NOTICE.
 * Also documented in Matthew T. Russotto's SIT5 write-up
 * (reference/notes/arsenic_russotto.md).
 *
 * Archive header: an 80-byte banner ("StuffIt (c)1997-....") with 4
 * wildcard bytes, then u8 version (= 5), u8 flags, u32 total size,
 * u32 ?, u16 top-level entry count, u32 offset of the first entry,
 * u16 crc, plus flag-dependent extras we skip via the entry offset.
 *
 * Entry header, at each entry offset:
 *    0 u32 id 0xA5A5A5A5 | 4 u8 version | 5 skip | 6 u16 header size |
 *    8 skip | 9 u8 flags | 10 u32 createdate | 14 u32 moddate |
 *   18 u32 prevoffs | 22 u32 nextoffs | 26 u32 diroffs (parent) |
 *   30 u16 namelen | 32 u16 headercrc |
 *   34 u32 datalen | 38 u32 datacomplen | 42 u16 datacrc | 44 skip2 |
 *   directory (flags & 0x40): u16 numfiles
 *   file: 46 u8 datamethod | 47 u8 passlen | key[passlen]
 *   name[namelen], then if header space remains: u16 commentlen,
 *   skip2, comment. Then a second block: u16 flags2 (bit 0 = has
 *   rsrc), skip2, u32 type, u32 creator, u16 finderflags, then skip
 *   22 (entry version 1) or 18 bytes, and when flags2 & 1:
 *   u32 rsrclen, u32 rsrccomplen, u16 rsrccrc, skip2, u8 rsrcmethod,
 *   u8 passlen, key[passlen].
 * Fork data follows the header: rsrc fork first, then data fork.
 *
 * Quirk (from the reference): after every directory entry an extra
 * entry with datalen == SIT5_DATALEN_NONE appears; it is skipped and does
 * not count against the entry total. Directory entries add their
 * (recursive) child count to the total. Parent chains are tracked by
 * header offset (diroffs), not by nesting order.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"
#include "fmt_sit5_priv.h"

/* The datalen of the extra entry that follows every directory entry —
 * the format's own marker, not a ceiling. */
#define SIT5_DATALEN_NONE 0xFFFFFFFFu

#define SIT5_ID          0xA5A5A5A5u
#define SIT5_DIRECTORY   0x40
#define SIT5_CRYPTED     0x20
/* Archive-level flags (header byte 83). */
#define SIT5_ARCH_14BYTES 0x10
#define SIT5_ARCH_20      0x20
#define SIT5_ARCH_CRYPTED 0x80

/* The banner match string; \xFF bytes match anything (the four
 * digits of the second year vary). XADStuffIt5Parser.m. */


/* Map from directory entry offset -> its path, for parent lookup.
 * Bounded pool; archives with more directories than fit fail cleanly
 * per entry (parent falls back to the root). */
#define SIT5_MAX_DIRS 256

typedef struct Sit5Dirs {
    uint32_t offs[SIT5_MAX_DIRS];
    uint16_t start[SIT5_MAX_DIRS];   /* offset into pool */
    uint16_t len[SIT5_MAX_DIRS];
    int32_t  count;
    uint32_t pool_used;
    uint8_t  pool[16384];
} Sit5Dirs;

static const uint8_t *sit5_dir_lookup(const Sit5Dirs *d, uint32_t offs,
                                      uint32_t *lenout)
{
    int32_t i;
    for (i = 0; i < d->count; i++) {
        if (d->offs[i] == offs) {
            *lenout = d->len[i];
            return d->pool + d->start[i];
        }
    }
    *lenout = 0;
    return NULL;
}

static void sit5_dir_add(Sit5Dirs *d, uint32_t offs,
                         const uint8_t *path, uint32_t len)
{
    if (d->count >= SIT5_MAX_DIRS || d->pool_used + len > sizeof d->pool)
        return;   /* children of an overflowed dir land at the root */
    d->offs[d->count] = offs;
    d->start[d->count] = (uint16_t)d->pool_used;
    d->len[d->count] = (uint16_t)len;
    {
        uint32_t i;
        for (i = 0; i < len; i++) d->pool[d->pool_used + i] = path[i];
    }
    d->pool_used += len;
    d->count++;
}

/* StuffIt 5's archive key is MD5(password) cut to five bytes, and the
 * header carries MD5 of THAT, also cut to five: a password is graded
 * before anything is decoded. Asks the host until one verifies.
 * Source: XADStuffIt5Parser.m keyForEntryWithDictionary. */
static int sit5_archive_key(UncCtx *c, const uint8_t hash[UNC_SIT5_KEYLEN],
                            uint8_t key[UNC_SIT5_KEYLEN])
{
    int attempt = 0;
    for (;;) {
        int err = unc_password(c, attempt > 0);
        if (err != UNC_OK) return err;
        if (unc_crypt_sit5_key(c->pw, c->pwlen, hash, key) == UNC_OK)
            return UNC_OK;
        attempt++;
    }
}

/* Each fork is RC4 under the archive key followed by the fork's own
 * five bytes, which the entry header carries in clear. */
static void sit5_fork_key(UncCrypt *cr, const uint8_t archivekey[UNC_SIT5_KEYLEN],
                          const uint8_t forkkey[UNC_SIT5_KEYLEN])
{
    uint8_t key[2 * UNC_SIT5_KEYLEN];
    int i;
    for (i = 0; i < UNC_SIT5_KEYLEN; i++) {
        key[i] = archivekey[i];
        key[UNC_SIT5_KEYLEN + i] = forkkey[i];
    }
    unc_crypt_rc4(cr, key, (uint16_t)sizeof key);
}

int unc_sit5_extract(UncCtx *c)
{
    uint8_t hdr[128], name[256];
    uint32_t firstoffs, pos, fsize;
    int32_t numentries, i;
    Sit5Dirs *dirs;
    uint8_t *iobuf, *obuf;
    UncCrypt *cr;
    uint8_t pwhash[UNC_SIT5_KEYLEN], archivekey[UNC_SIT5_KEYLEN];
    uint8_t datakey[UNC_SIT5_KEYLEN], rsrckey[UNC_SIT5_KEYLEN];
    int havehash = 0, havekey = 0;
    uint32_t iocap = UNC_IOBUF, ocap = UNC_IOBUF;
    int err = UNC_OK;

    fsize = unc_io_size32(c->io);

    if (unc_read_at(c->io, 0, hdr, 100) != UNC_OK) return UNC_ERR_FORMAT;
    if (!unc_sit5_probe(hdr, 100, NULL)) return UNC_ERR_FORMAT;
    if (hdr[82] != 5) return UNC_ERR_FORMAT;      /* archive version */
    /* 80-byte banner, u8 version, u8 flags, u32 totalsize @84,
     * u32 ? @88, u16 numfiles @92, u32 firstoffs @94, u16 crc @98. */
    numentries = unc_get_u16be(hdr + 92);
    firstoffs = unc_get_u32be(hdr + 94);

    /* Optional blocks follow the fixed header, and one of them is the
     * five-byte hash that says whether a password is the right one.
     * Their order is fixed; only their presence is flagged.
     * Source: XADStuffIt5Parser.m parse. */
    if (hdr[83] & SIT5_ARCH_CRYPTED) {
        uint32_t hp = 100;
        uint8_t hb[8];
        if (hdr[83] & SIT5_ARCH_14BYTES) hp += 14;
        if (hdr[83] & SIT5_ARCH_20) hp += 4;   /* comment size, length_b */
        if (unc_read_at(c->io, hp, hb, 6) != UNC_OK) return UNC_ERR_TRUNCATED;
        if (hb[0] != UNC_SIT5_KEYLEN) return UNC_ERR_UNSUPPORTED;
        for (i = 0; i < UNC_SIT5_KEYLEN; i++) pwhash[i] = hb[1 + i];
        havehash = 1;
    }

    dirs = (Sit5Dirs *)unc_alloc(c->al, (uint32_t)sizeof *dirs);
    if (!dirs) return UNC_ERR_MEM;
    dirs->count = 0;
    dirs->pool_used = 0;
    iobuf = (uint8_t *)unc_alloc(c->al, iocap + ocap + (uint32_t)sizeof *cr);
    if (!iobuf) { unc_free(c->al, dirs); return UNC_ERR_MEM; }
    obuf = iobuf + iocap;
    cr = (UncCrypt *)(void *)(obuf + ocap);

    pos = firstoffs;
    for (i = 0; i < numentries; i++) {
        uint32_t headersize, headerend, diroffs, namelen;
        uint32_t datalen, datacomp, datastart;
        uint32_t rsrclen = 0, rsrccomp = 0;
        uint32_t hpos, flags2;
        uint16_t datacrc, rsrccrc = 0;
        int entryver, flags, datamethod = 0, rsrcmethod = 0;
        int isdir = 0, encrypted;
        int hasdatakey = 0, hasrsrckey = 0;
        uint32_t dirfiles = 0;
        UncEntryInfo e;
        int sret;

        if (unc_read_at(c->io, pos, hdr, 48) != UNC_OK) {
            err = i == 0 ? UNC_ERR_FORMAT : UNC_ERR_TRUNCATED;
            goto out;
        }
        if (unc_get_u32be(hdr) != SIT5_ID) {
            err = UNC_ERR_CORRUPT;
            goto out;
        }
        entryver   = hdr[4];
        headersize = unc_get_u16be(hdr + 6);
        headerend  = pos + headersize;
        flags      = hdr[9];
        diroffs    = unc_get_u32be(hdr + 26);
        namelen    = unc_get_u16be(hdr + 30);
        datalen    = unc_get_u32be(hdr + 34);
        datacomp   = unc_get_u32be(hdr + 38);
        datacrc    = unc_get_u16be(hdr + 42);
        isdir      = flags & SIT5_DIRECTORY;
        encrypted  = flags & SIT5_CRYPTED;
        hpos = pos + 46;

        if (isdir) {
            if (unc_read_at(c->io, hpos, hdr, 2) != UNC_OK) {
                err = UNC_ERR_TRUNCATED;
                goto out;
            }
            dirfiles = unc_get_u16be(hdr);
            hpos += 2;
            if (datalen == SIT5_DATALEN_NONE) {
                /* Mystery entry after each directory: skip, does not
                 * count (XADStuffIt5Parser.m). */
                numentries++;
                pos = headerend;
                continue;
            }
        } else {
            uint8_t fb[2];
            if (unc_read_at(c->io, hpos, fb, 2) != UNC_OK) {
                err = UNC_ERR_TRUNCATED;
                goto out;
            }
            datamethod = fb[0];
            hpos += 2;
            if (fb[1]) {                    /* password key bytes */
                if (!encrypted || !datalen || fb[1] != UNC_SIT5_KEYLEN) {
                    err = UNC_ERR_CORRUPT;
                    goto out;
                }
                if (unc_read_at(c->io, hpos, datakey, UNC_SIT5_KEYLEN)
                    != UNC_OK) { err = UNC_ERR_TRUNCATED; goto out; }
                hasdatakey = 1;
                hpos += fb[1];
            }
        }

        if (namelen > sizeof name) namelen = sizeof name;
        if (namelen &&
            unc_read_at(c->io, hpos, name, (int32_t)namelen) != UNC_OK) {
            err = UNC_ERR_TRUNCATED;
            goto out;
        }
        hpos += unc_get_u16be(hdr + 30);    /* true namelen, uncapped */

        if (hpos < headerend) {
            /* comment block: u16 size, skip 2, comment bytes */
            if (unc_read_at(c->io, hpos, hdr, 2) != UNC_OK) {
                err = UNC_ERR_TRUNCATED;
                goto out;
            }
            hpos += 4 + unc_get_u16be(hdr);
        }

        /* Second block. */
        if (unc_read_at(c->io, hpos, hdr, 16) != UNC_OK) {
            err = UNC_ERR_TRUNCATED;
            goto out;
        }
        flags2 = unc_get_u16be(hdr);
        unc_entry_clear(&e);
        e.type         = unc_get_u32be(hdr + 4);
        e.creator      = unc_get_u32be(hdr + 8);
        e.finder_flags = unc_get_u16be(hdr + 12);
        hpos += 14;   /* u16 flags2, u16 ?, u32 type, u32 creator, u16 flags */
        hpos += entryver == 1 ? 22 : 18;

        if (flags2 & 1) {
            if (unc_read_at(c->io, hpos, hdr, 16) != UNC_OK) {
                err = UNC_ERR_TRUNCATED;
                goto out;
            }
            rsrclen  = unc_get_u32be(hdr);
            rsrccomp = unc_get_u32be(hdr + 4);
            rsrccrc  = unc_get_u16be(hdr + 8);
            rsrcmethod = hdr[12];
            hpos += 14;
            if (hdr[13]) {                  /* rsrc password key */
                if (!encrypted || !rsrclen || hdr[13] != UNC_SIT5_KEYLEN) {
                    err = UNC_ERR_CORRUPT;
                    goto out;
                }
                if (unc_read_at(c->io, hpos, rsrckey, UNC_SIT5_KEYLEN)
                    != UNC_OK) { err = UNC_ERR_TRUNCATED; goto out; }
                hasrsrckey = 1;
                hpos += hdr[13];
            }
        }
        datastart = hpos;

        /* Path: parent from diroffs map, then this component. */
        {
            uint32_t plen;
            const uint8_t *ppath = sit5_dir_lookup(dirs, diroffs, &plen);
            if (ppath) unc_entry_set_path(&e, ppath, plen);
            else       unc_entry_set_path(&e, name, 0);
        }
        unc_entry_path_append(&e, name, namelen);

        {
            uint8_t rd[16];
            if (unc_read_at(c->io, pos + 10, rd, 8) == UNC_OK) {
                e.create_date = unc_get_u32be(rd);
                e.mod_date    = unc_get_u32be(rd + 4);
            }
        }

        if (isdir) {
            e.is_dir = 1;
            e.data_size = e.rsrc_size = 0;
            e.comp_data_size = e.comp_rsrc_size = 0;
            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; goto out; }
            if (sret == 0 && c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) {
                err = UNC_ERR_SINK;
                goto out;
            }
            sit5_dir_add(dirs, pos, e.name, e.name_len);
            numentries += (int32_t)dirfiles;
            pos = datastart;
            continue;
        }

        e.data_size = datalen;
        e.rsrc_size = (flags2 & 1) ? rsrclen : 0;
        e.comp_data_size = datacomp;
        e.comp_rsrc_size = rsrccomp;
        e.method_data = (uint8_t)datamethod;
        e.method_rsrc = (uint8_t)rsrcmethod;

        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; goto out; }

        if (sret == 0) {
            int est = UNC_OK;
            if (!c->opt.list_only) {
                if (encrypted && !havehash) {
                    /* Encrypted, but the archive header carries no hash
                     * to check a password against — nothing here can
                     * derive the key. */
                    est = UNC_ERR_ENCRYPTED;
                } else if (encrypted && !havekey &&
                           (est = sit5_archive_key(c, pwhash, archivekey))
                           != UNC_OK) {
                    /* est is UNC_ERR_PASSWORD: no usable password */
                } else if (datastart + rsrccomp < datastart ||
                           datastart + rsrccomp + datacomp < datastart ||
                           (fsize != UNC_SIZE_UNKNOWN &&
                            datastart + rsrccomp + datacomp > fsize)) {
                    est = UNC_ERR_TRUNCATED;
                } else {
                    if (encrypted) havekey = 1;
                    if (flags2 & 1) {
                        if (hasrsrckey) sit5_fork_key(cr, archivekey, rsrckey);
                        est = unc_sit_decode_fork(c, UNC_FORK_RSRC, datastart,
                                                  rsrccomp, rsrclen, rsrcmethod,
                                                  rsrccrc, iobuf, iocap,
                                                  obuf, ocap,
                                                  hasrsrckey ? cr : NULL);
                    }
                    if (est == UNC_OK) {
                        if (hasdatakey) sit5_fork_key(cr, archivekey, datakey);
                        est = unc_sit_decode_fork(c, UNC_FORK_DATA,
                                                  datastart + rsrccomp,
                                                  datacomp, datalen, datamethod,
                                                  datacrc, iobuf, iocap,
                                                  obuf, ocap,
                                                  hasdatakey ? cr : NULL);
                    }
                }
            }
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                goto out;
            }
            if (unc_fatal(est)) {
                err = est;
                goto out;
            }
        }

        if (datastart + rsrccomp + datacomp < datastart) {
            err = UNC_ERR_CORRUPT;
            goto out;
        }
        pos = datastart + rsrccomp + datacomp;
    }

out:
    unc_free(c->al, iobuf);
    unc_free(c->al, dirs);
    return err;
}
