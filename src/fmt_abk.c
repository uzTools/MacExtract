/*
 * fmt_abk.c — Apple Backup, the Performa's backup to floppy disks.
 *
 * A backup is a set of disks, each holding one file, "Apple Backup Data"
 * (type 'OBDa', creator 'OBBa', no resource fork), 0x161800 bytes long
 * on a 1.44 MB disk. Nothing is compressed. Each file is:
 *
 *   +0x000  the disk header, 0x200 bytes:
 *             +0x00 u16 version (0x0103 on every disk here)
 *             +0x02 u32 'CMWL'
 *             +0x06 u16 this disk's number, 1-based
 *             +0x08 u16 how many disks the backup has
 *             +0x0A u32 when the backup began (Macintosh date), and the
 *                       same again at +0x0E
 *             +0x12 Str31 the name of the drive backed up
 *             +0x32 u32 the file's length, +0x36 u32 how much of it is
 *                       used: what follows that is not the backup's
 *   +0x200  boot blocks, 0x400 bytes, which a restore does not need
 *   +0x600  items, each starting on a multiple of 0x200:
 *             +0x00 u16 version, +0x02 u32 'RLDW'
 *             +0x06 u16 the disk this item's first part is on
 *             +0x08 u32 the backup's date again
 *             +0x0C u32 this header's own offset in the file
 *             +0x10 Str31 the item's name
 *             +0x30 u16 which part of the item this is, 1-based
 *             +0x32 u8  bit 7 a folder; bit 0 the System Folder to bless
 *             +0x33 u8  bit 0: what follows is valid (a folder whose
 *                       properties could not be read has it clear)
 *             +0x34 16  FInfo or DInfo, +0x44 16 FXInfo or DXInfo
 *             +0x54 u8  ioFlAttrib, bit 0 locked
 *             +0x56 u32 created, +0x5A u32 modified
 *             +0x5E u32 the data fork's whole length, +0x62 the
 *                       resource fork's
 *             +0x66 u32 the data fork's bytes on this disk, +0x6A the
 *                       resource fork's
 *             +0x6E u16 the length of the path after the header
 *           then the path from the drive's root, ':' between names,
 *           then this disk's data fork bytes and its resource fork
 *           bytes, then zeros to the next 0x200.
 *
 * An item that does not fit is cut where the disk ends and continued at
 * 0x600 of the next disk, under a repeat of its header with the part
 * number one higher and this disk's byte counts. Measured on the twelve
 * cut items in six real disks of two backups: the data fork is always
 * finished before any of the resource fork is written, so each fork
 * arrives in order.
 *
 * Source: Doug Brown, "Legacy Apple Backup file format on floppy disks"
 * (2013, reference/applebackup/downtowndougbrown-2013.txt), for every
 * offset above; checked against the two readers written from it,
 * siddhartha77's Apple Backup Extractor 1.0b1 (reference/applebackup/
 * abe-AppleBackupSpec.[ch], no licence stated, read for facts only) for
 * the validity bit, ioFlAttrib and the item's start disk, and Em
 * Adespoton's Kaitai description (reference/applebackup/
 * kaitai-applebackup.ksy, MIT); and against six real disks from two backups
 * (fixtures/SOURCES.md), where the header offset, the date and the
 * padding hold on every one of 124 items and every walk ends exactly
 * at the used length.
 *
 * Not restored: the System Folder's blessing (bit 0 of +0x32), which no
 * host here has a way to write; and the backup date, which this format
 * does not store per item — Apple Backup Extractor writes the backup's
 * start into each file's, the format says nothing of what Apple's own
 * restore did.
 *
 * Every disk says which disk it is and how many there are, so a set is
 * read in ADDRESSED mode (unc_segment.c): this reader opens disk after
 * disk through UncSegMap, in order, and never reads past a disk's used
 * length. A disk the host cannot produce is skipped: what started
 * before it ends as a missing part, and what continues after it is
 * reported once and passed over. The rest of the set still comes out.
 *
 * SPDX-License-Identifier: 0BSD
 */
#include "fmt_abk_priv.h"

#define ABK_BUF (2u * UNC_IOBUF)

/* The item a disk's next part must continue: its first disk and its two
 * whole lengths, which every part's header repeats. */
typedef struct AbkOpen {
    uint16_t start;
    uint16_t part;              /* the part the next one must be, or 0
                                 * for any: the item's earlier parts
                                 * are on a disk that was not read    */
    uint32_t dlen, rlen;
    uint32_t dleft, rleft;      /* still to come                      */
    uint8_t  state;             /* ABK_NONE, ABK_WRITING, ABK_PASSING */
} AbkOpen;

enum { ABK_NONE, ABK_WRITING, ABK_PASSING };

/* `n` bytes of the current disk to `fork`, or past them when `fork` is
 * -1 or nothing is to be written. */
static int abk_copy(UncCtx *c, uint32_t n, int fork, uint8_t *buf)
{
    if (fork < 0 || c->opt.list_only) {
        const UncSegMap *m = c->segmap;
        if (n && m->skip(m->ctx, n) < 0) return UNC_ERR_TRUNCATED;
        return unc_progress_add(&c->ps, n);
    }
    while (n) {
        uint32_t k = n < ABK_BUF ? n : ABK_BUF;
        int err = unc_read_full(c->io, buf, (int32_t)k);
        if (err != UNC_OK) return err;
        err = unc_progress_add(&c->ps, k);
        if (err != UNC_OK) return err;
        if (!c->opt.test_only &&
            c->sink->write(c->sink->ctx, (UncFork)fork, buf, (int32_t)k) < 0)
            return UNC_ERR_SINK;
        n -= k;
    }
    return UNC_OK;
}

/* Stop following the open item. One being written ends with `verdict`;
 * with `orphan`, its later parts are still passed over as they come.
 * UNC_ERR_SINK if the host refuses even that. */
static int abk_drop(UncCtx *c, AbkOpen *o, int verdict, int orphan)
{
    int was = o->state;
    o->state = (orphan && was != ABK_NONE) ? ABK_PASSING : ABK_NONE;
    o->part = 0;
    if (was == ABK_WRITING && c->sink->end_entry(c->sink->ctx, verdict) < 0)
        return UNC_ERR_SINK;
    return UNC_OK;
}

/* The entry an item describes, announced to the sink. `path` is the
 * item's path, ':' between names. 1 if the sink wants its forks, 0 if
 * not, UNC_ERR_SINK if it failed. */
static int abk_begin(UncCtx *c, const uint8_t *h, const uint8_t *path,
                     uint32_t plen, UncPath *walk)
{
    UncEntryInfo e;
    uint32_t i, last = 0;
    int k;

    unc_path_init(walk, c);
    for (i = 0; i < plen; i++)
        if (path[i] == ':') {
            (void)unc_path_push(walk, path + last, i - last);
            last = i + 1;
        }
    unc_entry_clear(&e);
    unc_path_leaf(walk, &e, path + last, plen - last);
    e.is_dir = (h[0x32] & 0x80) != 0;
    /* A folder whose properties could not be read is still a folder,
     * and nothing more is known of it. */
    if (h[0x33] & 1) {
        for (k = 0; k < 32; k++) e.finder_info[k] = h[0x34 + k];
        e.meta = UNC_META_FINFO | UNC_META_FXINFO;
        e.finder_flags = unc_get_u16be(h + 0x3C);
        e.create_date = unc_get_u32be(h + 0x56);
        e.mod_date = unc_get_u32be(h + 0x5A);
        if (!e.is_dir) {
            e.type = unc_get_u32be(h + 0x34);
            e.creator = unc_get_u32be(h + 0x38);
            e.locked = (h[0x54] & 1) ? UNC_LOCK_YES : UNC_LOCK_NO;
        }
    }
    if (!e.is_dir) {
        e.data_size = e.comp_data_size = unc_get_u32be(h + 0x5E);
        e.rsrc_size = e.comp_rsrc_size = unc_get_u32be(h + 0x62);
    }
    k = c->sink->begin_entry(c->sink->ctx, &e);
    if (k < 0) return UNC_ERR_SINK;
    if (k > 0) return 0;
    if (e.is_dir) {
        if (c->sink->end_entry(c->sink->ctx, UNC_OK) < 0) return UNC_ERR_SINK;
        return 0;
    }
    return 1;
}

int unc_abk_extract(UncCtx *c)
{
    const UncSegMap *m = c->segmap;
    uint8_t dh[ABK_DISK_HDR], h[ABK_ITEM_HDR], stamp[4], *buf;
    UncPath *walk;
    AbkOpen o;
    int p, k, have_stamp = 0, err = UNC_OK, worst = UNC_OK;
    /* Why the items being passed over were lost: a disk that was not
     * to be had, or one that was and could not be read. */
    int gap = UNC_ERR_SEGMENTED;

    /* A disk handed over on its own is one disk of a set: the joiner is
     * what reads one, even a set of one. */
    if (!m) return UNC_ERR_SEGMENTED;
    buf = (uint8_t *)unc_alloc(c->al, ABK_BUF + (uint32_t)sizeof *walk);
    if (!buf) return UNC_ERR_MEM;
    /* The walker in the allocation, not on the stack (fmt_sqp.c says
     * why). */
    walk = (UncPath *)(void *)(buf + ABK_BUF);
    o.state = ABK_NONE;
    o.part = 0;

    for (p = 1; p <= (int)m->nparts && err == UNC_OK; p++) {
        uint32_t off = ABK_FIRST, used, size;
        int bad = UNC_OK;

        if (m->seek_part(m->ctx, p, 0) < 0) {
            /* Not to be had: the joiner has recorded the set's verdict.
             * What this disk would have finished, it cannot. */
            gap = UNC_ERR_SEGMENTED;
            err = abk_drop(c, &o, gap, 1);
            continue;
        }
        size = m->part_size(m->ctx, p);
        if (unc_read_full(c->io, dh, (int32_t)ABK_DISK_HDR) != UNC_OK ||
            !abk_disk_ok(dh) || unc_get_u16be(dh + 6) != p ||
            unc_get_u16be(dh + 8) != m->nparts ||
            (have_stamp && (dh[0x0A] != stamp[0] || dh[0x0B] != stamp[1] ||
                            dh[0x0C] != stamp[2] || dh[0x0D] != stamp[3]))) {
            worst = gap = UNC_ERR_CORRUPT;
            err = abk_drop(c, &o, gap, 1);
            continue;
        }
        for (k = 0; k < 4; k++) stamp[k] = dh[0x0A + k];
        have_stamp = 1;
        used = unc_get_u32be(dh + 0x36);
        /* A disk file cut short — a copy that stopped — ends where it
         * ends, and an item running past that is truncated below. */
        if (size != UNC_SIZE_UNKNOWN && used > size) used = size;
        err = unc_progress_add(&c->ps, ABK_FIRST);

        while (err == UNC_OK && off + ABK_ITEM_HDR <= used) {
            uint32_t plen, dh_, rh_, end, dlen, rlen;
            uint16_t part, start;
            int est = UNC_OK, w;

            if (m->seek_part(m->ctx, p, off) < 0 ||
                unc_read_full(c->io, h, (int32_t)ABK_ITEM_HDR) != UNC_OK) {
                bad = UNC_ERR_TRUNCATED;
                break;
            }
            plen = unc_get_u16be(h + 0x6E);
            dh_ = unc_get_u32be(h + 0x66);
            rh_ = unc_get_u32be(h + 0x6A);
            end = off + ABK_ITEM_HDR + plen;
            /* Each length in turn, so no sum can wrap before it is
             * compared with the disk's end. Nothing after a damaged
             * item can be placed: the next one's offset is this one's
             * lengths. */
            if (unc_get_u32be(h + 2) != ABK_ITEM_MAGIC ||
                unc_get_u32be(h + 0x0C) != off ||
                h[8] != stamp[0] || h[9] != stamp[1] ||
                h[10] != stamp[2] || h[11] != stamp[3] ||
                plen > ABK_BUF || end > used ||
                dh_ > used - end || rh_ > used - end - dh_) {
                bad = UNC_ERR_CORRUPT;
                break;
            }
            if (unc_read_full(c->io, buf, (int32_t)plen) != UNC_OK) {
                bad = UNC_ERR_TRUNCATED;
                break;
            }
            err = unc_progress_add(&c->ps, ABK_ITEM_HDR + plen);
            if (err != UNC_OK) break;
            part = unc_get_u16be(h + 0x30);
            start = unc_get_u16be(h + 6);
            dlen = unc_get_u32be(h + 0x5E);
            rlen = unc_get_u32be(h + 0x62);

            /* Not the part the open item needs next: that item is lost,
             * and this one stands on its own below. */
            if (o.state != ABK_NONE &&
                ((o.part && part != o.part) || start != o.start ||
                 dlen != o.dlen || rlen != o.rlen)) {
                err = abk_drop(c, &o, UNC_ERR_CORRUPT, 0);
                if (err != UNC_OK) break;
            }
            if (o.state == ABK_NONE) {
                o.start = start;
                o.dlen = o.dleft = dlen;
                o.rlen = o.rleft = rlen;
                w = abk_begin(c, h, buf, plen, walk);
                if (w < 0) { err = w; break; }
                if (part == 1) {
                    o.state = w ? ABK_WRITING : ABK_PASSING;
                } else {
                    /* Begun on a disk that was not read: said once,
                     * here, and its later parts passed over. */
                    if (w && c->sink->end_entry(c->sink->ctx, gap) < 0) {
                        err = UNC_ERR_SINK;
                        break;
                    }
                    o.state = ABK_PASSING;
                    o.dleft = o.rleft = UNC_U32_MAX;
                }
                if (h[0x32] & 0x80) o.state = ABK_NONE;     /* a folder */
            }

            /* Each fork in order: no resource fork bytes before the data
             * fork is whole (the file comment). An item whose earlier
             * parts were not read has nothing to count against. */
            if (o.state != ABK_NONE && o.dleft != UNC_U32_MAX) {
                if (dh_ > o.dleft || rh_ > o.rleft ||
                    (rh_ && dh_ != o.dleft)) {
                    est = UNC_ERR_CORRUPT;
                } else {
                    o.dleft -= dh_;
                    o.rleft -= rh_;
                }
            }
            w = o.state == ABK_WRITING && est == UNC_OK;
            if (est == UNC_OK)
                est = abk_copy(c, dh_, w ? UNC_FORK_DATA : -1, buf);
            if (est == UNC_OK)
                est = abk_copy(c, rh_, w ? UNC_FORK_RSRC : -1, buf);
            if (unc_fatal(est)) { err = est; break; }
            if (o.state != ABK_NONE &&
                (est != UNC_OK || (o.dleft == 0 && o.rleft == 0))) {
                err = abk_drop(c, &o, est, 0);
                if (err != UNC_OK) break;
            } else if (o.state != ABK_NONE) {
                o.part = (uint16_t)(part + 1);
            }

            end += dh_ + rh_;
            off = (end + ABK_ALIGN - 1u) & ~(ABK_ALIGN - 1u);
            /* The padding, which the last item's may run past the used
             * length to the 0x200 boundary or stop at. */
            err = unc_progress_add(&c->ps, (off < used ? off : used) - end);
        }
        if (err != UNC_OK) break;
        if (bad != UNC_OK) {
            /* The rest of this disk cannot be placed. */
            worst = gap = bad;
            err = abk_drop(c, &o, bad, 1);
            continue;
        }
        /* What is left of the disk after its used length. */
        if (size != UNC_SIZE_UNKNOWN && size > used)
            err = unc_progress_add(&c->ps, size - used);
    }
    /* An item still waiting for a part past the last disk. */
    if (err == UNC_OK)
        err = abk_drop(c, &o, UNC_ERR_TRUNCATED, 0);

    unc_free(c->al, buf);
    return err != UNC_OK ? err : worst;
}
