/*
 * unc_sidecar.c — Mac OS X's AppleDouble sidecars, put back on the file
 * they describe.
 *
 * Where Mac OS X puts a file somewhere that cannot hold a resource fork
 * or Finder info, it writes them into a second file, "._" + the name: an
 * AppleDouble header file. Two writers put those into archives:
 *
 *   zip, the Finder's Compress (ditto): `dir/name` and, under a top
 *        folder of its own, `__MACOSX/dir/._name`. Measured on a
 *        Finder-made zip of 2006 (fixtures/SOURCES.md, `macosx-*`): each
 *        sidecar follows its file, after the `__MACOSX/...` folder
 *        records it needs.
 *   tar, bsdtar: `dir/._name`, inline, as the member BEFORE `dir/name`.
 *        Source: reference/notes/libarchive_write_set_format_pax.c,
 *        archive_write_pax_header — "._" spliced in front of the last
 *        component, written and finished before the entry itself.
 *
 * What the sidecar holds is the writer's: entry 9 (32 bytes of Finder
 * info, then on Mac OS X the extended attributes) at 50 and entry 2 (the
 * resource fork) after it. Source: reference/notes/copyfile.c,
 * copyfile_pack and `apple_double_header_t`. Entries 4, 8, 10 and 12
 * are read too, because other writers of the same file (RFC 1740) carry
 * them; what each one means is fmt_applesingle.c's (unc_as_record).
 *
 * Which names are sidecars, and which folders are not emitted, is
 * XADMaster's rule. Source: reference/XADMaster/XADMacArchiveParser.m,
 * -parseAppleDoubleWithDictionary: (the last component starts "._",
 * an optional first component "__MACOSX" is dropped, the rest is the
 * file's path) and -addEntryWithDictionary: (a DIRECTORY whose first
 * component is "__MACOSX" is discarded). What makes a file a sidecar
 * rather than a file whose name starts "._" is XADAppleDouble.m's test:
 * magic 0x00051607, version 0x00020000, and entry 2 or entry 9 present;
 * and "Add FinderInfo ... only if it is not empty": 32 zero bytes are
 * how copyfile says it had none.
 *
 * Where the two disagree, this follows neither: XADMaster pairs a zip
 * sidecar only with an ADJACENT file, and libarchive pairs it by name
 * anywhere in the directory but loses one whose file is absent
 * (reference/notes/libarchive_read_support_format_zip.c, the `tree_rsrc`
 * that only a lookup reads). Here a sidecar pairs with its file wherever
 * the directory puts either, and one that pairs with nothing comes out
 * as itself (DECISIONS.md 2026-10-17, *the sidecars Mac OS X left
 * beside the file*).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define SIDE_NONE UNC_SIZE_UNKNOWN

/* ------------------------------------------------------------------ */
/* The AppleDouble header, captured out of a stream                   */
/* ------------------------------------------------------------------ */

/* The first UNC_AD_WIN bytes of the sidecar are kept, and the entries
 * read out of them: copyfile's Finder info ends at 82 (copyfile.c,
 * `apple_double_header_t`), and an RFC 1740 writer that puts every entry
 * the engine reads in front of the forks needs a few hundred. An entry
 * that is not wholly inside the window is not read; the forks are spans,
 * and are not limited by it. */
void unc_ad_init(UncAdCap *a, uint32_t size)
{
    a->got = 0;
    a->size = size;
    a->state = UNC_AD_READING;
}

int unc_ad_feed(UncAdCap *a, const uint8_t *p, uint32_t n)
{
    while (n-- && a->got < UNC_AD_WIN) a->win[a->got++] = *p++;
    if (a->got < UNC_AD_WIN && a->got < a->size) return 0;
    unc_ad_end(a);
    return 1;
}

/* The header and its table, from what was captured. Source:
 * reference/notes/rfc1740.txt, appendix A — u32 magic, u32 version, 16
 * bytes of filler, u16 count, then count × {u32 id, u32 offset, u32
 * length}. A sidecar is XADAppleDouble.m's: magic 0x00051607, version
 * 0x00020000, an entry 2 or 9; and a resource fork that fits the file. */
void unc_ad_end(UncAdCap *a)
{
    uint32_t i, n, have = 0;
    if (a->state != UNC_AD_READING) return;
    a->state = UNC_AD_NOT;
    a->rlen = 0;
    if (a->got < 26 || unc_get_u32be(a->win) != 0x00051607u ||
        unc_get_u32be(a->win + 4) != 0x00020000u)
        return;
    n = unc_get_u16be(a->win + 24);
    if (26 + 12 * n > a->got) return;
    for (i = 0; i < n; i++) {
        const uint8_t *t = a->win + 26 + 12 * i;
        uint32_t id = unc_get_u32be(t), off = unc_get_u32be(t + 4);
        uint32_t len = unc_get_u32be(t + 8);
        if (id == 2) {
            if (off > a->size || len > a->size - off) return;
            a->roff = off;
            a->rlen = len;
        }
        if (id == 2 || id == 9) have = 1;
    }
    if (have) a->state = UNC_AD_YES;
}

void unc_ad_apply(const UncAdCap *a, UncEntryInfo *e)
{
    uint32_t i, n, k;
    if (a->state != UNC_AD_YES) return;
    n = unc_get_u16be(a->win + 24);
    for (i = 0; i < n; i++) {
        const uint8_t *t = a->win + 26 + 12 * i;
        uint32_t id = unc_get_u32be(t), off = unc_get_u32be(t + 4);
        uint32_t len = unc_get_u32be(t + 8);
        const uint8_t *b = a->win + off;
        /* The lengths unc_as_record reads; the comment at the engine's
         * ceiling. */
        uint32_t take = id == 4 ? UNC_ENTRY_COMMENT_MAX : 32;
        if (len < take) take = len;
        if (off > a->got || take > a->got - off) continue;
        if (id == 4) {
            if (take) { e->comment = b; e->comment_len = (uint16_t)take; }
        } else if (id >= 8 && id <= 12) {
            /* 32 zero bytes of Finder info are copyfile's "none". */
            for (k = 0; id == 9 && k < take && !b[k]; k++) {}
            if (id != 9 || k < take) unc_as_record(e, id, b, take);
        }
    }
}

/* ------------------------------------------------------------------ */
/* Names                                                              */
/* ------------------------------------------------------------------ */

static int side_eq(const uint8_t *a, const uint8_t *b, uint32_t n)
{
    while (n--) if (*a++ != *b++) return 0;
    return 1;
}

static const uint8_t k_macosx[] = "__MACOSX/";

/* A sidecar's name, split into the folder and the leaf of the file it
 * describes: p[*d .. *d + *dl) and p[*l .. n). 1 if it is a sidecar's. */
static int side_split(const uint8_t *p, uint32_t n, uint32_t *d,
                      uint32_t *dl, uint32_t *l)
{
    uint32_t s = n >= 9 && side_eq(p, k_macosx, 9) ? 9u : 0u, k = n;
    while (k > s && p[k - 1] != '/') k--;
    if (n - k < 3 || p[k] != '.' || p[k + 1] != '_') return 0;
    *d = s;
    *dl = k > s ? k - s - 1 : 0;
    *l = k + 2;
    return 1;
}

int unc_side_kind(const uint8_t *p, uint32_t n, int isdir)
{
    uint32_t d, dl, l;
    if (isdir)
        return n >= 8 && side_eq(p, k_macosx, 8) && (n == 8 || p[8] == '/')
             ? UNC_SIDE_DIR : UNC_SIDE_NO;
    return side_split(p, n, &d, &dl, &l) ? UNC_SIDE_FILE : UNC_SIDE_NO;
}

int unc_side_of(const uint8_t *s, uint32_t sn, const uint8_t *p, uint32_t pn)
{
    uint32_t d, dl, l, ll;
    if (!side_split(s, sn, &d, &dl, &l)) return 0;
    ll = sn - l;
    if (pn != (dl ? dl + 1 : 0) + ll) return 0;
    if (dl && (!side_eq(p, s + d, dl) || p[dl] != '/')) return 0;
    return side_eq(p + pn - ll, s + l, ll);
}

/* ------------------------------------------------------------------ */
/* zip: pairing over the central directory                            */
/* ------------------------------------------------------------------ */

/* The name of the record at `r`, its trailing '/' gone, and where the
 * next record starts — or SIDE_NONE if no record is there. Source:
 * reference/notes/zip_appnote.txt 4.3.12 — 46 fixed bytes, the name's
 * length at +28, the extra field's at +30, the comment's at +32. */
static uint32_t side_rec_at(const uint8_t *cd, uint32_t cdsize, uint32_t r,
                            const uint8_t **p, uint32_t *n, int *dir)
{
    const uint8_t *c = cd + r;
    uint32_t nl;
    if (r > cdsize || cdsize - r < 46 ||
        c[0] != 'P' || c[1] != 'K' || c[2] != 1 || c[3] != 2)
        return SIDE_NONE;
    nl = unc_get_u16le(c + 28);
    if (cdsize - r - 46 < nl) return SIDE_NONE;
    *p = c + 46;
    *dir = nl > 0 && c[46 + nl - 1] == '/';
    while (nl > 0 && c[46 + nl - 1] == '/') nl--;
    *n = nl;
    return r + 46 + unc_get_u16le(c + 28) + unc_get_u16le(c + 30) +
           unc_get_u16le(c + 32);
}
#define side_rec(z, r, p, n, d) side_rec_at((z)->cd, (z)->cdsize, r, p, n, d)

/* A 1,024-bit filter over the leaves, so that a file nothing names a
 * sidecar for costs one test rather than a walk of the directory. A
 * sidecar's key is the leaf it names, less "._". */
static uint32_t side_hash(const uint8_t *p, uint32_t n, uint32_t skip)
{
    uint32_t h = 0, k = n;
    while (k > 0 && p[k - 1] != '/') k--;
    for (k += skip; k < n; k++) h = h * 31u + p[k];
    return h & 1023u;
}

#define SIDE_SET(m, h)  ((m)[(h) >> 3] |= (uint8_t)(1u << ((h) & 7u)))
#define SIDE_HAS(m, h)  ((m)[(h) >> 3] & (1u << ((h) & 7u)))

/* Two walks of the directory: the first only asks whether any record is
 * named as a sidecar, so that a zip with none allocates nothing — not
 * even for a moment, which would move its peak (tools/run_segments.py's
 * un-buffered walk is aimed at that peak, and caught it). */
UncSideZip *unc_side_zip_open(UncAlloc *al, const uint8_t *cd,
                              uint32_t cdsize, uint32_t n)
{
    UncSideZip *z = NULL;
    uint32_t r, k, pass, found = 0;
    for (pass = 0; pass < 2; pass++) {
        for (r = 0, k = 0; k < n; k++) {
            const uint8_t *p;
            uint32_t len;
            int dir, kind;
            uint32_t nx = side_rec_at(cd, cdsize, r, &p, &len, &dir);
            if (nx == SIDE_NONE) break;
            kind = unc_side_kind(p, len, dir);
            if (kind == UNC_SIDE_FILE) {
                found = 1;
                if (!z) break;
                SIDE_SET(z->sides, side_hash(p, len, 2));
            } else if (kind == UNC_SIDE_NO && z) {
                SIDE_SET(z->files, side_hash(p, len, 0));
            }
            r = nx;
        }
        if (!z) {
            if (!found) return NULL;
            z = (UncSideZip *)unc_alloc(al, (uint32_t)sizeof *z);
            if (!z) return NULL;
            z->cd = cd;
            z->cdsize = cdsize;
            z->n = n;
            z->caprel = z->lastfile = SIDE_NONE;
            for (k = 0; k < 128; k++) z->files[k] = z->sides[k] = 0;
        }
    }
    return z;
}

/* The first record after `from`, going round the directory, that is the
 * sidecar of `key` (want == 0) or the file the sidecar `key` names
 * (want == 1). Starting from the record itself rather than from wherever
 * the walk is makes the answer the record's own, whoever asks: a file and
 * its sidecar each ask the other's question, and must agree, or a
 * sidecar would be skipped that no file took. */
static uint32_t side_scan(const UncSideZip *z, uint32_t from,
                          const uint8_t *key, uint32_t kn, int want)
{
    const uint8_t *p;
    uint32_t n, k;
    int dir;
    uint32_t r = side_rec(z, from, &p, &n, &dir);
    for (k = 0; k <= z->n && r != SIDE_NONE; k++) {
        uint32_t nx = side_rec(z, r, &p, &n, &dir);
        if (nx == SIDE_NONE) {          /* the end: round to the start */
            if (r == 0) break;
            r = 0;
            continue;
        }
        if (r == from) break;
        if (want ? unc_side_kind(p, n, dir) == UNC_SIDE_NO &&
                   unc_side_of(key, kn, p, n)
                 : !dir && unc_side_of(p, n, key, kn))
            return r;
        r = nx;
    }
    return SIDE_NONE;
}

/* A file's sidecar is the first one naming it after it, round the
 * directory: in the Finder's order that is a few records on, past the
 * folder records under __MACOSX. A sidecar pairs with the file it names
 * only if that file's own search finds it, so of two sidecars for one
 * file, the other comes out as itself (DECISIONS.md 2026-10-17, *the
 * sidecars Mac OS X left beside the file*). */
uint32_t unc_side_zip_pair(UncSideZip *z, uint32_t rel, int *isside)
{
    const uint8_t *p, *tp;
    uint32_t n, tn, t;
    int dir, tdir, kind;

    *isside = 0;
    if (side_rec(z, rel, &p, &n, &dir) == SIDE_NONE) return SIDE_NONE;
    kind = unc_side_kind(p, n, dir);
    if (kind == UNC_SIDE_DIR) return SIDE_NONE;
    if (kind == UNC_SIDE_NO) {
        z->lastfile = rel;
        if (!SIDE_HAS(z->sides, side_hash(p, n, 0))) return SIDE_NONE;
        return side_scan(z, rel, p, n, 0);
    }
    *isside = 1;
    if (!SIDE_HAS(z->files, side_hash(p, n, 2))) return SIDE_NONE;
    /* Its file is most often the last one walked (the Finder's order),
     * which is one comparison; otherwise the directory is searched. */
    t = z->lastfile;
    if (t == SIDE_NONE || side_rec(z, t, &tp, &tn, &tdir) == SIDE_NONE ||
        !unc_side_of(p, n, tp, tn))
        t = side_scan(z, rel, p, n, 1);
    if (t == SIDE_NONE) return SIDE_NONE;
    (void)side_rec(z, t, &tp, &tn, &tdir);
    return side_scan(z, t, tp, tn, 0) == rel ? t : SIDE_NONE;
}
