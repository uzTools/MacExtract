/*
 * fmt_arc.c — ARC archives (.arc), the SEA/PKARC family, plus the
 * ArcMac container that wraps each entry in Macintosh metadata.
 *
 * Sources (transcribed, never guessed):
 *   docs/formats/arc-container-and-coders.md — this project's own
 *       description, derived 2026-09-20 from archives ARC 5.21q
 *       wrote here (tools/derive_arc.py): the member HEADER, the
 *       RLE90 filter, method 4's node-pair Huffman tree, method 8's
 *       leading width byte and LZW, and method 9's LZW without
 *       either. Methods 1, 2, 3, 4, 8 and 9 of the corpus fixture
 *       are read back by that note's rules alone.
 *   reference/XADMaster/XADARCParser.m       — the method numbers
 *       this file names, which methods chain RLE90, and the CRC-16
 *       contract (IBM CRC-16 over the DECODED bytes, unconditioned);
 *       the header walk itself is the note above since 2026-09-20.
 *   reference/XADMaster/XADRLE90Handle.m     — the 0x90 run filter,
 *       superseded by the note above, which derives the same rule.
 *   reference/XADMaster/XADSqueezeHandle.m   — method 4's Huffman
 *       tree, likewise superseded.
 *   reference/XADMaster/XADARCCrunchHandle.m — methods 5/6/7, an LZW
 *       whose table is addressed by hash rather than by sequence.
 *   reference/XADMaster/XADARCCrushHandle.m + LZW.c — method 0x0a, the
 *       only implementation of Crushed anywhere.
 *   reference/deark/src/fmtutil-lzh.c        — method 0x0b, the
 *       "PAK/ARC Distilled" section, which is a SECOND reading of that
 *       method and the one this file follows.
 *   reference/XADMaster/XADARCDistillHandle.m — the first reading of
 *       0x0b, which agrees with deark everywhere except the window.
 *   reference/macutils/macunpack/arc.h       — the ArcMac header, and
 *       the note that its second size field is a copy of the first
 *       ("this is wrong for Arc!"), which is why the uncompressed
 *       length of an ArcMac entry comes from the fork lengths.
 *   reference/macutils/README                — "ArcMac: nearly PC-Arc
 *       compatible", and the method list this file implements.
 *   reference/notes/ArcMac.DOC               — ArcMac's own specification,
 *       section "ArcMac File Structure": the header as a Pascal record,
 *       and the only statement anywhere of the fork lengths' byte order
 *       ("stored in archive using Intel 80xxx byte sex").
 *
 * What no document states is which fork an ArcMac payload starts with.
 * That was MEASURED — ArcMac 1.3c archiving a two-fork file under an
 * emulated Mac Plus, tools/vmac/arcmac.py — and it is the data fork.
 *
 * Methods 8, 9 and 0x7f are Unix compress with the parameters the
 * method fixes, so they run through unc_lzw.c unchanged.
 *
 * Methods 0x0a (Crushed) and 0x0b (Distilled) belong to PAK, from
 * NoGate Consulting — NOT to PKARC/PKPAK, which this project believed
 * for a year (BLOCKERS.md). Two things about them are not in
 * XADMaster:
 *
 *   - Distilled's 8 KB window starts full of SPACES, as LZHUF.C's
 *     does. XADMaster starts it at zero and so decodes any match that
 *     reaches back past the start of the data to the wrong bytes —
 *     6 of the 10 members of a real archive (DECISIONS.md).
 *   - Method 0x0a is AMBIGUOUS: ARC 7.x ("ARC Plus") uses the same
 *     number for Trimmed, a different algorithm. This file decodes
 *     0x0a as Crushed, which is what PAK wrote; a Trimmed member is
 *     caught by its CRC rather than by its header (OPEN_ITEMS.md).
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* Methods. Source: XADARCParser.m and macutils' arc.h, which agree. */
#define ARC_M_STORED_OLD  0x01
#define ARC_M_STORED      0x02
#define ARC_M_PACKED      0x03
#define ARC_M_SQUEEZED    0x04
#define ARC_M_CRUNCH5     0x05
#define ARC_M_CRUNCH6     0x06
#define ARC_M_CRUNCH7     0x07
#define ARC_M_CRUNCH8     0x08
#define ARC_M_SQUASHED    0x09
#define ARC_M_CRUSHED     0x0a
#define ARC_M_DISTILLED   0x0b
#define ARC_M_INFO        0x14   /* archive info      (ARC 7.x)      */
#define ARC_M_FILEINFO    0x15   /* extended file info                */
#define ARC_M_OSINFO      0x16   /* OS-specific info                  */
#define ARC_M_DIR         0x1e
#define ARC_M_DIREND      0x1f
#define ARC_M_COMPRESSED  0x7f

/* Informational items, not members: an ordinary header whose payload
 * is metadata. ARC 7.x writes 0x14 first in every archive it makes,
 * which is why an ARC+Plus file was not recognised as ARC at all until
 * these were walked (neither `unar` nor deark-less tooling reads one).
 * They are skipped: what they carry is a version string and per-file
 * notes this extractor has nothing to do with. */
#define arc_is_item(m) ((m) == ARC_M_INFO || (m) == ARC_M_FILEINFO || \
                        (m) == ARC_M_OSINFO)

/* Carried in the `method` int above the byte a header holds: this
 * archive's 0x0a is ARC 7.x's Trimmed, not PAK's Crushed. The two
 * share a method number and are different algorithms, so the decision
 * is the ARCHIVE's, taken once by arc_dialect() and then travelling
 * with the entry — including through the password path, which decodes
 * the same entry up to four times. */
#define ARC_F_TRIMMED     0x1000

#define ARC_HDR_MIN       0x1d   /* 0x1a, method, 13 name, 4+2+2+2, 4 */
#define ARC_NAME_LEN      13

/* ArcMac field offsets. Source: reference/macutils/macunpack/arc.h. */
#define AM_MAGIC1      0
#define AM_KIND        1
#define AM_FNAME       2      /* 31 bytes, NUL-padded */
#define AM_FTYPE      34
#define AM_FAUTH      38
#define AM_FINFO      42
#define AM_FDATA      50      /* data fork length   */
#define AM_FRSRC      54      /* rsrc fork length   */
#define AM_MAGIC2     59      /* the PC ARC header starts here */
#define AM_HDRBYTES   88

/* Crunch: a 4096-entry table, addressed by hash. */
#define ARC_CRUNCH_SIZE  4096
#define ARC_STACK_SIZE   4096

/* Squeeze: at most 257 leaves, so 257 node pairs. */
#define ARC_SQ_MAXNODES  (257 * 2)

/* Crushed: AllocLZW(8192,1) — 8192 symbols, one reserved for the EOF
 * code, and a 500-symbol window that decides how codes are framed. */
#define ARC_CRUSH_SIZE     8192
#define ARC_CRUSH_FIRST    257        /* 256 literals + the EOF code   */
#define ARC_CRUSH_RING     500
#define ARC_CRUSH_STRINGS  375        /* strings in the window above
                                       * which the literal bit goes    */
#define ARC_CRUSH_MAXBITS  13

/* Distilled: an 8 KB window, at most 628 tree nodes (314 internal for
 * 315 codes), and a fixed 64-entry prefix code for the offsets. */
#define ARC_DIST_WIN       8192
#define ARC_DIST_MAXNODES  628
#define ARC_DIST_MAXSYM    314        /* 256 literals + stop + lengths */
#define ARC_DIST_OFFSYMS   64
#define ARC_DIST_OFFNODES  64

/* ------------------------------------------------------------------ */
/* Decoder state                                                      */
/* ------------------------------------------------------------------ */

typedef struct ArcDec {
    int        method;       /* method & 0x7f */
    UncBufIn  *in;
    UncAlloc  *al;
    uint8_t   *mem;          /* single allocation for the tables */

    uint32_t   left;         /* stored: input bytes still to copy    */

    /* RLE90 filter state (XADRLE90Handle). */
    int        rle;          /* filter enabled                        */
    UncRle90   rle90;

    /* Squeeze (XADSqueezeHandle). */
    UncBitIn   bit;
    int16_t   *nodes;
    uint16_t  *sq_fast;   /* first-bits table over `nodes`   */
    int32_t    numnodes;
    int        sq_eof;

    /* Crunch (XADARCCrunchHandle). */
    int16_t   *parent;       /* [4096], -1 = root                     */
    uint8_t   *cbyte;        /* [4096]                                */
    uint16_t  *next;         /* [4096]                                */
    uint8_t   *used;         /* [4096]                                */
    uint8_t   *stack;        /* [4096]                                */
    int32_t    sp;
    int32_t    numfree;
    int32_t    lastcode;
    int        lastbyte;
    int        fast;         /* method 7's hash                       */
    int        started;

    /* Crushed (method 0x0a). The LZW tree is XADMaster's LZW.c: a
     * parent link and one byte per symbol, walked leaf to root. */
    int16_t   *cr_parent;    /* [8192], -1 = root                      */
    uint8_t   *cr_chr;       /* [8192]                                 */
    uint8_t   *cr_usage;     /* [8192], the replacement policy's counts */
    uint8_t   *cr_out;       /* [8192], one symbol's string, leaf first */
    uint8_t   *cr_ring;      /* [500], string-or-literal window        */
    int32_t    cr_numsym, cr_prev;
    int32_t    cr_symsize, cr_bump;
    int32_t    cr_recent, cr_ringidx, cr_usageidx;
    int32_t    cr_outlen;
    int        cr_litbit;

    /* Distilled (method 0x0b). */
    uint16_t  *di_nodes;     /* [628], the stored decode tree          */
    int16_t   *di_off;       /* [64*2], the fixed offset code as a tree */
    uint16_t  *di_fast;      /* first-bits table over di_nodes          */
    uint16_t  *di_offfast;   /* and over di_off                         */
    uint8_t   *di_win;       /* [8192], starts full of spaces          */
    int32_t    di_numnodes;
    int32_t    di_wpos;      /* next window write position             */
    uint32_t   di_written;   /* bytes produced — the offset ladder     */
    int32_t    di_msrc, di_mlen;   /* the match being copied out       */

    /* Unix compress (methods 8, 9, 0x7f). */
    UncLzw     lzw;
    int        lzw_open;
    uint8_t    lzwbuf[64];
    int32_t    lzwlen, lzwpos;
} ArcDec;

/* ------------------------------------------------------------------ */
/* Squeeze                                                            */
/* ------------------------------------------------------------------ */

/* ------------------------------------------------------------------ */
/* First-bits tables over the node trees                              */
/*                                                                    */
/* Squeeze and Distilled both store an explicit tree of node pairs and */
/* walked it a bit at a time. Measured on derived-INTRECHO.pak: 7.0    */
/* bits a symbol over 295,185 symbols, and the tree read TEN times for */
/* all of them — so a table over the first bits is built once per      */
/* entry and paid back thousands of times. 98.2 % of that fixture's    */
/* symbols are ten bits or fewer.                                     */
/*                                                                    */
/* An entry is the code length in the top four bits and the symbol in  */
/* the low twelve; 0 means "longer than the table, walk it". The       */
/* window is indexed RAW: these readers are LSB-first, so the bit that */
/* leaves the stream first is bit 0 of both the window and the index   */
/* and nothing has to be turned round — unlike unc_canon_decode, whose */
/* codes are assembled MSB-first (DECISIONS.md 2026-08-27).            */
/*                                                                    */
/* The table is filled by RUNNING the walk, through the same step      */
/* functions the decoders use, over every window value. A thousand     */
/* short walks per tree is nothing against the two million steps it    */
/* saves, and a builder that CANNOT disagree with the walk is worth    */
/* more here than a clever one.                                       */
/* ------------------------------------------------------------------ */

#define ARC_TREE_LEAF  (-1)
#define ARC_TREE_BAD   (-2)

#define ARC_FAST_BITS  10
#define ARC_FAST_SIZE  (1u << ARC_FAST_BITS)
#define ARC_FAST_MASK  (ARC_FAST_SIZE - 1u)
#define ARC_OFF_BITS    8
#define ARC_OFF_SIZE   (1u << ARC_OFF_BITS)
#define ARC_OFF_MASK   (ARC_OFF_SIZE - 1u)

enum { ARC_T_SQ, ARC_T_DIST, ARC_T_OFF };

/* Defined once all three step functions are, below. */
static void arc_tree_table(const ArcDec *d, int which, int32_t root,
                           uint16_t *tab, int bits);

static int arc_squeeze_init(ArcDec *d)
{
    int32_t i;
    int lo, hi, pairs;

    lo = unc_bufin_next(d->in);
    hi = unc_bufin_next(d->in);
    if (lo < 0 || hi < 0) return UNC_ERR_TRUNCATED;
    pairs = lo | (hi << 8);
    d->numnodes = (int32_t)pairs * 2;
    if (d->numnodes >= ARC_SQ_MAXNODES || d->numnodes < 2) return UNC_ERR_CORRUPT;

    for (i = 0; i < d->numnodes; i++) {
        int a = unc_bufin_next(d->in), b = unc_bufin_next(d->in);
        if (a < 0 || b < 0) return UNC_ERR_TRUNCATED;
        d->nodes[i] = (int16_t)(uint16_t)(a | (b << 8));
    }
    unc_bitin_init_le(&d->bit, d->in);
    d->sq_eof = 0;
    arc_tree_table(d, ARC_T_SQ, 0, d->sq_fast, ARC_FAST_BITS);
    return UNC_OK;
}

/* -1 = end of stream, -2 = corrupt/short. */
/* One step down the tree: the child of `node` on `bit`, ARC_TREE_LEAF
 * with *sym set, or ARC_TREE_BAD. The table builder below walks with
 * this same function, so a table can never disagree with the walk. */
static int32_t arc_squeeze_step(const ArcDec *d, int32_t node, int bit,
                                int32_t *sym)
{
    int32_t v;
    if (2 * node + bit >= d->numnodes) return ARC_TREE_BAD;
    v = d->nodes[2 * node + bit];
    if (v < 0) { *sym = -(v + 1); return ARC_TREE_LEAF; }
    return v;
}

static int arc_squeeze_byte(ArcDec *d)
{
    int32_t node = 0, sym = 0;
    int depth = 0;

    if (d->sq_eof) return -1;

    if (unc_bitin_fill(&d->bit, ARC_FAST_BITS)) {
        unsigned e = d->sq_fast[d->bit.bitbuf & ARC_FAST_MASK];
        if (e) {
            d->bit.nbits -= (int32_t)(e >> 12);
            d->bit.bitbuf >>= (e >> 12);
            sym = (int32_t)(e & 0xFFFu);
            if (sym == 256) { d->sq_eof = 1; return -1; }
            if (sym > 255) return -2;
            return (int)sym;
        }
    }

    for (;;) {
        int bit = unc_bitin_bit(&d->bit);
        if (bit < 0) return -1;                 /* input ran out */
        node = arc_squeeze_step(d, node, bit, &sym);
        if (node == ARC_TREE_LEAF) {
            if (sym == 256) { d->sq_eof = 1; return -1; }
            if (sym < 0 || sym > 255) return -2;
            return (int)sym;
        }
        if (node == ARC_TREE_BAD) return -2;
        if (++depth > 64) return -2;            /* cyclic tree */
    }
}

/* ------------------------------------------------------------------ */
/* Crunch (methods 5, 6, 7)                                           */
/* ------------------------------------------------------------------ */

static void arc_crunch_update(ArcDec *d, int32_t parentcode, int byte)
{
    uint32_t index;

    if (d->fast) {
        index = (((uint32_t)(parentcode + byte) & 0xffffu) * 15073u) & 0xfffu;
    } else {
        index = ((uint32_t)(parentcode + byte) | 0x0800u) & 0xffffu;
        index = ((index * index) >> 6) & 0xfffu;
    }

    if (d->used[index]) {
        uint32_t nx;
        while (d->next[index]) index = d->next[index];
        nx = (index + 101u) & 0xfffu;
        while (d->used[nx]) nx = (nx + 1u) & 0xfffu;
        d->next[index] = (uint16_t)nx;
        index = nx;
    }

    d->used[index]   = 1;
    d->next[index]   = 0;
    d->parent[index] = (int16_t)parentcode;
    d->cbyte[index]  = (uint8_t)byte;
}

static int arc_crunch_start(ArcDec *d)
{
    int32_t i, code;

    for (i = 0; i < ARC_CRUNCH_SIZE; i++) {
        d->used[i] = 0;
        d->next[i] = 0;
        d->parent[i] = -1;
        d->cbyte[i] = 0;
    }
    d->sp = 0;
    d->numfree = ARC_CRUNCH_SIZE - 256;
    for (i = 0; i < 256; i++) arc_crunch_update(d, -1, (int)i);

    /* MSB-first: XADARCCrunchHandle reads CSInputNextBitString, and it
     * is the LE-suffixed variant that means LSB-first (CSInputBuffer.h).
     * Reading these 12-bit codes the other way round decodes to
     * plausible-looking garbage that still satisfies our own CRC, so
     * the mistake only surfaced against `unar`. */
    unc_bitin_init(&d->bit, d->in);
    code = unc_bitin_bits(&d->bit, 12);
    if (code < 0) return UNC_ERR_TRUNCATED;
    d->lastcode = code;
    d->lastbyte = d->cbyte[code];
    d->stack[d->sp++] = (uint8_t)d->lastbyte;
    d->started = 1;
    return UNC_OK;
}

static int arc_crunch_byte(ArcDec *d)
{
    if (!d->started) {
        if (arc_crunch_start(d) != UNC_OK) return -1;
    }
    if (!d->sp) {
        int32_t code = unc_bitin_bits(&d->bit, 12);
        int32_t entry;
        int byte;

        if (code < 0) return -1;                 /* end of input */
        entry = code;
        if (!d->used[entry]) {
            entry = d->lastcode;
            if (d->sp >= ARC_STACK_SIZE) return -2;
            d->stack[d->sp++] = (uint8_t)d->lastbyte;
        }
        while (d->parent[entry] != -1) {
            if (d->sp >= ARC_STACK_SIZE - 1) return -2;
            d->stack[d->sp++] = d->cbyte[entry];
            entry = d->parent[entry];
        }
        byte = d->cbyte[entry];
        d->stack[d->sp++] = (uint8_t)byte;

        if (d->numfree != 0) {
            arc_crunch_update(d, d->lastcode, byte);
            d->numfree--;
        }
        d->lastcode = code;
        d->lastbyte = byte;
    }
    return d->stack[--d->sp];
}

/* ------------------------------------------------------------------ */
/* Crushed (method 0x0a, PAK)                                         */
/*                                                                    */
/* LZW over 8192 symbols, with two features ordinary LZW has not.     */
/*                                                                    */
/* Codes are framed one of two ways, and the stream switches between  */
/* them without saying so: a 500-symbol window counts how many recent */
/* symbols were strings rather than literals, and while literals are  */
/* common every code carries a leading bit that says which it is.     */
/* Once strings dominate, both share one code length — and literals   */
/* then arrive with their bits INVERTED, which XADMaster attributes   */
/* to an optimisation in the original decruncher.                     */
/*                                                                    */
/* When the table fills it is not cleared. Each symbol carries a      */
/* usage count, and a rotating scan decrements counts until it finds  */
/* one that reaches zero; that symbol is overwritten.                 */
/*                                                                    */
/* Source: XADARCCrushHandle.m, with the tree from LZW.c.             */
/* ------------------------------------------------------------------ */

/* The first byte of a symbol's string, i.e. the root's byte.
 * Guarded because replacement can point a parent at a descendant and
 * make a cycle, which no amount of valid input does but corrupt input
 * does readily. Source: FindFirstByte(), LZW.c. */
static int arc_crush_firstbyte(ArcDec *d, int32_t sym)
{
    int32_t guard = 0;
    while (d->cr_parent[sym] >= 0) {
        sym = d->cr_parent[sym];
        if (++guard > ARC_CRUSH_SIZE) return -1;
    }
    return d->cr_chr[sym];
}

/* One symbol, framed as the current mode says. -1 = input ran out. */
static int32_t arc_crush_readsym(ArcDec *d)
{
    int32_t v;

    if (d->cr_litbit) {
        int b = unc_bitin_bit(&d->bit);
        if (b < 0) return -1;
        if (b) {
            v = unc_bitin_bits_le(&d->bit, (int)d->cr_symsize);
            if (v < 0) return -1;
            return v + 256;
        }
        v = unc_bitin_bits_le(&d->bit, 8);
        if (v < 0) return -1;
        return v;
    }

    v = unc_bitin_bits_le(&d->bit, (int)d->cr_symsize);
    if (v < 0) return -1;
    if (v < 0x100) v ^= 0xff;
    return v;
}

/* Decode one symbol into cr_out. 0 = ok, -1 = end, -2 = corrupt. */
static int arc_crush_step(ArcDec *d)
{
    int32_t symbol, s, n, guard;
    int manyliterals;

    symbol = arc_crush_readsym(d);
    if (symbol < 0) return -1;
    if (symbol == 0x100) return -1;              /* the EOF code */
    if (symbol >= ARC_CRUSH_SIZE) return -2;

    /* This string and every parent count as freshly used. */
    s = symbol;
    guard = 0;
    while (s >= 0) {
        d->cr_usage[s] = 4;
        s = d->cr_parent[s];
        if (++guard > ARC_CRUSH_SIZE) return -2;
    }

    /* Move the string-versus-literal window on by one. */
    if (d->cr_ring[d->cr_ringidx]) d->cr_recent--;
    if (symbol < 0x100) {
        d->cr_ring[d->cr_ringidx] = 0;
    } else {
        d->cr_ring[d->cr_ringidx] = 1;
        d->cr_recent++;
    }
    if (++d->cr_ringidx == ARC_CRUSH_RING) d->cr_ringidx = 0;

    manyliterals = (d->cr_recent < ARC_CRUSH_STRINGS);
    if (manyliterals != d->cr_litbit) {
        d->cr_litbit = manyliterals;
        d->cr_bump = (int32_t)1 << d->cr_symsize;
        if (!d->cr_litbit) d->cr_bump -= 0x100;
    }

    if (d->cr_numsym != ARC_CRUSH_SIZE) {
        /* Room left: add a symbol. Source: NextLZWSymbol(). */
        if (d->cr_prev < 0) {
            if (symbol >= d->cr_numsym) return -2;
            d->cr_prev = symbol;
        } else {
            int post;
            if (symbol < d->cr_numsym)       post = arc_crush_firstbyte(d, symbol);
            else if (symbol == d->cr_numsym) post = arc_crush_firstbyte(d, d->cr_prev);
            else return -2;
            if (post < 0) return -2;
            d->cr_parent[d->cr_numsym] = (int16_t)d->cr_prev;
            d->cr_chr[d->cr_numsym]    = (uint8_t)post;
            d->cr_prev = symbol;
            d->cr_numsym++;
        }
        d->cr_usage[d->cr_numsym - 1] = 2;
    } else {
        /* Full: overwrite the least-used symbol the scan reaches.
         * Source: XADARCCrushHandle.m, and the counts are bytes there
         * too, so a count of zero wraps to 255 exactly as it does
         * upstream rather than ending the scan. */
        int32_t minindex = 0, minusage = 0x7fffffff;
        int32_t index = d->cr_usageidx;
        int post;

        for (;;) {
            index++;
            if (index == ARC_CRUSH_SIZE) index = ARC_CRUSH_FIRST;
            if ((int32_t)d->cr_usage[index] < minusage) {
                minindex = index;
                minusage = (int32_t)d->cr_usage[index];
            }
            d->cr_usage[index]--;
            if (d->cr_usage[index] == 0) break;
            if (index == d->cr_usageidx) break;
        }
        d->cr_usageidx = index;

        if (symbol >= d->cr_numsym) return -2;
        /* The parent link is written BEFORE the first byte is looked
         * up, as ReplaceLZWSymbol() does — the lookup can walk through
         * the symbol just overwritten, and does. */
        d->cr_parent[minindex] = (int16_t)d->cr_prev;
        post = arc_crush_firstbyte(d, symbol);
        if (post < 0) return -2;
        d->cr_chr[minindex] = (uint8_t)post;
        d->cr_prev = symbol;
        d->cr_usage[minindex] = 2;
    }

    /* The string, leaf first; it comes back out root first below. */
    n = 0;
    s = d->cr_prev;
    while (s >= 0) {
        if (n >= ARC_CRUSH_SIZE) return -2;
        d->cr_out[n++] = d->cr_chr[s];
        s = d->cr_parent[s];
    }
    d->cr_outlen = n;

    if (d->cr_numsym - ARC_CRUSH_FIRST >= d->cr_bump) {
        d->cr_symsize++;
        if (d->cr_symsize > ARC_CRUSH_MAXBITS) return -2;
        d->cr_bump = (int32_t)1 << d->cr_symsize;
        if (!d->cr_litbit) d->cr_bump -= 0x100;
    }
    return 0;
}

static int arc_crush_byte(ArcDec *d)
{
    while (d->cr_outlen == 0) {
        int r = arc_crush_step(d);
        if (r != 0) return r;                    /* -1 end, -2 corrupt */
    }
    return d->cr_out[--d->cr_outlen];
}

/* ------------------------------------------------------------------ */
/* Distilled (method 0x0b, PAK)                                       */
/*                                                                    */
/* LZ77 with a stored prefix code for literals and match lengths, a   */
/* fixed one for the offsets, and no adaptive coding — Deflate's      */
/* general shape, simpler. The distinctive part is that the number of */
/* extra offset bits grows with how much has been decoded so far, so  */
/* early matches spend fewer bits on a distance that cannot be large  */
/* yet.                                                               */
/*                                                                    */
/* The window starts full of spaces and PAK's compressor emits        */
/* matches into it, so a decoder that starts it at zero returns the   */
/* wrong bytes near the head of text files and the right length —     */
/* which is what XADMaster does (DECISIONS.md).                       */
/*                                                                    */
/* Source: deark src/fmtutil-lzh.c, "PAK/ARC Distilled".              */
/* ------------------------------------------------------------------ */

/* The fixed offset code, as bit lengths and low-bit-first codes.
 * Source: XADARCDistillHandle.m's offsetlengths/offsetcodes, which are
 * LZHUF.C's p_len/p_code and agree bit for bit with deark's table. */
static const uint8_t arc_dist_offlen[ARC_DIST_OFFSYMS] = {
    3,4,4,4, 5,5,5,5, 5,5,5,5, 6,6,6,6,
    6,6,6,6, 6,6,6,6, 7,7,7,7, 7,7,7,7,
    7,7,7,7, 7,7,7,7, 7,7,7,7, 7,7,7,7,
    8,8,8,8, 8,8,8,8, 8,8,8,8, 8,8,8,8
};
static const uint8_t arc_dist_offcode[ARC_DIST_OFFSYMS] = {
    0x00,0x02,0x04,0x0c,0x01,0x06,0x0a,0x0e,
    0x11,0x16,0x1a,0x1e,0x05,0x09,0x0d,0x15,
    0x19,0x1d,0x25,0x29,0x2d,0x35,0x39,0x3d,
    0x03,0x07,0x0b,0x13,0x17,0x1b,0x23,0x27,
    0x2b,0x33,0x37,0x3b,0x43,0x47,0x4b,0x53,
    0x57,0x5b,0x63,0x67,0x6b,0x73,0x77,0x7b,
    0x0f,0x1f,0x2f,0x3f,0x4f,0x5f,0x6f,0x7f,
    0x8f,0x9f,0xaf,0xbf,0xcf,0xdf,0xef,0xff
};

/* Build the offset code as a binary tree: slot 0 = unused, positive =
 * an internal node, negative = -(symbol + 1). 64 complete codes need
 * 63 internal nodes, so ARC_DIST_OFFNODES is a ceiling, not a guess. */
static int arc_dist_offtree(ArcDec *d)
{
    int32_t next = 1;
    int n, i;

    for (i = 0; i < ARC_DIST_OFFNODES * 2; i++) d->di_off[i] = 0;

    for (n = 0; n < ARC_DIST_OFFSYMS; n++) {
        int len = (int)arc_dist_offlen[n];
        int32_t node = 0;
        for (i = 0; i < len; i++) {
            int bit = (arc_dist_offcode[n] >> i) & 1;
            int32_t at = node * 2 + bit;
            if (i == len - 1) {
                if (d->di_off[at] != 0) return UNC_ERR_CORRUPT;
                d->di_off[at] = (int16_t)(-(n + 1));
            } else {
                if (d->di_off[at] == 0) {
                    if (next >= ARC_DIST_OFFNODES) return UNC_ERR_CORRUPT;
                    d->di_off[at] = (int16_t)next++;
                }
                if (d->di_off[at] < 0) return UNC_ERR_CORRUPT;
                node = d->di_off[at];
            }
        }
    }
    return UNC_OK;
}

static int arc_distill_init(ArcDec *d)
{
    int32_t i, lo, hi, codelen;

    unc_bitin_init_le(&d->bit, d->in);

    lo = unc_bitin_bits_le(&d->bit, 8);
    hi = unc_bitin_bits_le(&d->bit, 8);
    codelen = unc_bitin_bits_le(&d->bit, 8);
    if (lo < 0 || hi < 0 || codelen < 0) return UNC_ERR_TRUNCATED;

    d->di_numnodes = lo | (hi << 8);
    if (d->di_numnodes < 2 || d->di_numnodes > ARC_DIST_MAXNODES ||
        (d->di_numnodes & 1)) return UNC_ERR_CORRUPT;
    if (codelen < 1 || codelen > 16) return UNC_ERR_CORRUPT;

    for (i = 0; i < d->di_numnodes; i++) {
        int32_t v = unc_bitin_bits_le(&d->bit, (int)codelen);
        if (v < 0) return UNC_ERR_TRUNCATED;
        d->di_nodes[i] = (uint16_t)v;
    }

    for (i = 0; i < ARC_DIST_WIN; i++) d->di_win[i] = ' ';
    d->di_wpos = 0;
    d->di_written = 0;
    d->di_msrc = d->di_mlen = 0;

    arc_tree_table(d, ARC_T_DIST, d->di_numnodes - 2, d->di_fast,
                   ARC_FAST_BITS);
    if (arc_dist_offtree(d) != UNC_OK) return UNC_ERR_CORRUPT;
    arc_tree_table(d, ARC_T_OFF, 0, d->di_offfast, ARC_OFF_BITS);
    return UNC_OK;
}

/* How many extra bits the offset carries, from how much has been
 * decoded. Source: distilled_get_num_extra_bits(), deark. */
/* The Distilled main tree: a value past the end of the table is a leaf.
 * Shared by the walk and the table builder — see the block above. */
static int32_t arc_dist_step(const ArcDec *d, int32_t node, int bit,
                             int32_t *sym)
{
    int32_t v;
    if (node < 0 || node + bit >= d->di_numnodes) return ARC_TREE_BAD;
    v = (int32_t)d->di_nodes[node + bit];
    if (v >= d->di_numnodes) { *sym = v - d->di_numnodes; return ARC_TREE_LEAF; }
    return v;
}

/* The fixed offset tree: negative is a leaf, and 0 is not a child
 * because node 0 is the root. */
static int32_t arc_off_step(const ArcDec *d, int32_t node, int bit,
                            int32_t *sym)
{
    int32_t v = d->di_off[node * 2 + bit];
    if (v < 0) { *sym = -(v + 1); return ARC_TREE_LEAF; }
    if (v == 0) return ARC_TREE_BAD;
    return v;
}

static int32_t arc_tree_step(const ArcDec *d, int which, int32_t node,
                             int bit, int32_t *sym)
{
    if (which == ARC_T_SQ)   return arc_squeeze_step(d, node, bit, sym);
    if (which == ARC_T_DIST) return arc_dist_step(d, node, bit, sym);
    return arc_off_step(d, node, bit, sym);
}

static void arc_tree_table(const ArcDec *d, int which, int32_t root,
                           uint16_t *tab, int bits)
{
    uint32_t n = 1u << bits, w;

    for (w = 0; w < n; w++) {
        int32_t node = root, sym = 0;
        int i;
        tab[w] = 0;
        for (i = 0; i < bits; i++) {
            node = arc_tree_step(d, which, node, (int)((w >> i) & 1u), &sym);
            if (node == ARC_TREE_LEAF) {
                /* A symbol the walk would refuse is left out, so the
                 * walk runs and refuses it exactly as it always did. */
                if (sym >= 0 && sym < 4096)
                    tab[w] = (uint16_t)(((uint32_t)(i + 1) << 12)
                                        | (uint32_t)sym);
                break;
            }
            if (node == ARC_TREE_BAD) break;
        }
    }
}

static int arc_dist_extrabits(uint32_t written)
{
    uint32_t n = written + 60;
    int x;
    for (x = 12; x >= 6; x--)
        if (n >= (uint32_t)1 << x) return x - 5;
    return 0;
}

static int arc_dist_put(ArcDec *d, int b)
{
    d->di_win[d->di_wpos] = (uint8_t)b;
    d->di_wpos = (d->di_wpos + 1) & (ARC_DIST_WIN - 1);
    d->di_written++;
    return b;
}

static int arc_distill_byte(ArcDec *d)
{
    int32_t cur, sym, depth, osym, extra, dist, mlen;
    int bit;

    if (d->di_mlen > 0) {
        int b = d->di_win[d->di_msrc];
        d->di_msrc = (d->di_msrc + 1) & (ARC_DIST_WIN - 1);
        d->di_mlen--;
        return arc_dist_put(d, b);
    }

    /* One symbol from the stored tree: node pairs, walked by bit,
     * a value past the end of the table being a leaf. */
    sym = -1;
    if (unc_bitin_fill(&d->bit, ARC_FAST_BITS)) {
        unsigned e = d->di_fast[d->bit.bitbuf & ARC_FAST_MASK];
        if (e) {
            d->bit.nbits -= (int32_t)(e >> 12);
            d->bit.bitbuf >>= (e >> 12);
            sym = (int32_t)(e & 0xFFFu);
        }
    }
    if (sym < 0) {
        cur = d->di_numnodes - 2;
        depth = 0;
        for (;;) {
            bit = unc_bitin_bit(&d->bit);
            if (bit < 0) return -1;
            cur = arc_dist_step(d, cur, bit, &sym);
            if (cur == ARC_TREE_LEAF) break;
            if (cur == ARC_TREE_BAD) return -2;
            if (++depth > 64) return -2;
        }
    }

    if (sym > ARC_DIST_MAXSYM) return -2;
    if (sym < 256) return arc_dist_put(d, (int)sym);
    if (sym == 256) return -1;                   /* the stop code */

    mlen = sym - 254;

    osym = -1;
    if (unc_bitin_fill(&d->bit, ARC_OFF_BITS)) {
        unsigned e = d->di_offfast[d->bit.bitbuf & ARC_OFF_MASK];
        if (e) {
            d->bit.nbits -= (int32_t)(e >> 12);
            d->bit.bitbuf >>= (e >> 12);
            osym = (int32_t)(e & 0xFFFu);
        }
    }
    if (osym < 0) {
        cur = 0;
        depth = 0;
        for (;;) {
            bit = unc_bitin_bit(&d->bit);
            if (bit < 0) return -1;
            cur = arc_off_step(d, cur, bit, &osym);
            if (cur == ARC_TREE_LEAF) break;
            if (cur == ARC_TREE_BAD) return -2;
            if (++depth > 8) return -2;
        }
    }

    extra = arc_dist_extrabits(d->di_written);
    if (extra > 0) {
        int32_t e = unc_bitin_bits_le(&d->bit, extra);
        if (e < 0) return -1;
        dist = (osym << extra) | e;
    } else {
        dist = osym;
    }

    /* Unsigned, because wpos-1-dist is negative for any match that
     * reaches back past the start and the wrap has to be defined. */
    d->di_msrc = (int32_t)((((uint32_t)d->di_wpos - 1u) - (uint32_t)dist)
                           & (uint32_t)(ARC_DIST_WIN - 1));
    d->di_mlen = mlen;

    {
        int b = d->di_win[d->di_msrc];
        d->di_msrc = (d->di_msrc + 1) & (ARC_DIST_WIN - 1);
        d->di_mlen--;
        return arc_dist_put(d, b);
    }
}

/* ------------------------------------------------------------------ */
/* Producer: one pre-RLE byte                                         */
/* ------------------------------------------------------------------ */

static int arc_raw_byte(ArcDec *d)
{
    switch (d->method) {
    case ARC_M_STORED_OLD:
    case ARC_M_STORED:
    case ARC_M_PACKED:
        if (d->left == 0) return -1;
        {
            int b = unc_bufin_next(d->in);
            if (b < 0) return -1;
            d->left--;
            return b;
        }
    case ARC_M_SQUEEZED:
        return arc_squeeze_byte(d);
    case ARC_M_CRUNCH5:
    case ARC_M_CRUNCH6:
    case ARC_M_CRUNCH7:
        return arc_crunch_byte(d);
    case ARC_M_CRUSHED:
        return arc_crush_byte(d);
    case ARC_M_DISTILLED:
        return arc_distill_byte(d);
    default:                                     /* LZW family */
        if (d->lzwpos >= d->lzwlen) {
            int32_t n = unc_lzw_read(&d->lzw, d->lzwbuf, (int32_t)sizeof d->lzwbuf);
            if (n <= 0) return n == 0 ? -1 : -2;
            d->lzwlen = n;
            d->lzwpos = 0;
        }
        return d->lzwbuf[d->lzwpos++];
    }
}

/* One output byte, through the RLE90 filter where the method uses it.
 * Source: XADRLE90Handle.m. */
static int arc_byte(ArcDec *d)
{
    if (!d->rle) return arc_raw_byte(d);
    for (;;) {
        int b, v = unc_rle90_take(&d->rle90);
        if (v >= 0) return v;
        b = arc_raw_byte(d);
        if (b < 0) return b;
        v = unc_rle90_feed(&d->rle90, b);
        /* A byte, or UNC_ERR_CORRUPT, which this caller reads as < -1. */
        if (v != UNC_RLE90_MORE) return v;
    }
}

/* ------------------------------------------------------------------ */
/* Per-entry setup                                                    */
/* ------------------------------------------------------------------ */

static int arc_dec_init(ArcDec *d, UncCtx *c, UncBufIn *in, int method,
                        uint32_t compsize)
{
    int err = UNC_OK;

    d->in = in;
    d->al = c->al;
    d->mem = 0;
    d->method = method & 0x7f;
    d->left = compsize;
    d->rle = 0;
    unc_rle90_init(&d->rle90, 1);
    d->sq_eof = 0;
    d->started = 0;
    d->lzw_open = 0;
    d->lzwlen = d->lzwpos = 0;
    d->fast = (d->method == ARC_M_CRUNCH7);

    switch (d->method) {
    case ARC_M_STORED_OLD:
    case ARC_M_STORED:
        break;
    case ARC_M_PACKED:
        d->rle = 1;
        break;
    case ARC_M_SQUEEZED:
        d->mem = (uint8_t *)unc_alloc(c->al,
                     ARC_SQ_MAXNODES * 2u + ARC_FAST_SIZE * 2u);
        if (!d->mem) return UNC_ERR_MEM;
        d->nodes   = (int16_t *)(void *)d->mem;
        d->sq_fast = (uint16_t *)(void *)(d->mem + ARC_SQ_MAXNODES * 2u);
        d->rle = 1;
        err = arc_squeeze_init(d);
        break;
    case ARC_M_CRUNCH5:
    case ARC_M_CRUNCH6:
    case ARC_M_CRUNCH7:
        /* parent[4096] u16 | next[4096] u16 | cbyte[4096] | used[4096]
         * | stack[4096] — one block, 2-aligned first for the u16s. */
        d->mem = (uint8_t *)unc_alloc(c->al, ARC_CRUNCH_SIZE * 6u + ARC_STACK_SIZE);
        if (!d->mem) return UNC_ERR_MEM;
        d->parent = (int16_t *)(void *)d->mem;
        d->next   = (uint16_t *)(void *)(d->mem + ARC_CRUNCH_SIZE * 2u);
        d->cbyte  = d->mem + ARC_CRUNCH_SIZE * 4u;
        d->used   = d->mem + ARC_CRUNCH_SIZE * 5u;
        d->stack  = d->mem + ARC_CRUNCH_SIZE * 6u;
        d->rle = (d->method != ARC_M_CRUNCH5);
        break;
    case ARC_M_CRUSHED:
        /* parent[8192] u16 | chr | usage | out | ring[500].
         * The u16 array goes first so the block's own alignment is the
         * only one that matters. */
        d->mem = (uint8_t *)unc_alloc(c->al, ARC_CRUSH_SIZE * 5u + ARC_CRUSH_RING);
        if (!d->mem) return UNC_ERR_MEM;
        d->cr_parent = (int16_t *)(void *)d->mem;
        d->cr_chr    = d->mem + ARC_CRUSH_SIZE * 2u;
        d->cr_usage  = d->mem + ARC_CRUSH_SIZE * 3u;
        d->cr_out    = d->mem + ARC_CRUSH_SIZE * 4u;
        d->cr_ring   = d->mem + ARC_CRUSH_SIZE * 5u;
        {
            int32_t i;
            for (i = 0; i < ARC_CRUSH_SIZE; i++) {
                d->cr_parent[i] = -1;
                d->cr_chr[i]    = 0;
                d->cr_usage[i]  = 0;
            }
            for (i = 0; i < 256; i++) d->cr_chr[i] = (uint8_t)i;
            for (i = 0; i < ARC_CRUSH_RING; i++) d->cr_ring[i] = 0;
        }
        d->cr_numsym   = ARC_CRUSH_FIRST;
        d->cr_prev     = -1;
        d->cr_symsize  = 1;
        d->cr_bump     = 2;
        d->cr_litbit   = 1;
        d->cr_recent   = 0;
        d->cr_ringidx  = 0;
        d->cr_usageidx = ARC_CRUSH_FIRST;
        d->cr_outlen   = 0;
        unc_bitin_init_le(&d->bit, in);
        d->rle = 1;                    /* XADARCParser chains RLE90 */
        break;
    case ARC_M_DISTILLED:
        /* nodes[628] u16 | offtree[64*2] i16 | win[8192] */
        d->mem = (uint8_t *)unc_alloc(c->al,
                     ARC_DIST_MAXNODES * 2u + ARC_DIST_OFFNODES * 4u
                     + ARC_FAST_SIZE * 2u + ARC_OFF_SIZE * 2u
                     + ARC_DIST_WIN);
        if (!d->mem) return UNC_ERR_MEM;
        d->di_nodes   = (uint16_t *)(void *)d->mem;
        d->di_off     = (int16_t *)(void *)(d->mem + ARC_DIST_MAXNODES * 2u);
        d->di_fast    = (uint16_t *)(void *)(d->mem + ARC_DIST_MAXNODES * 2u
                                             + ARC_DIST_OFFNODES * 4u);
        d->di_offfast = d->di_fast + ARC_FAST_SIZE;
        d->di_win     = d->mem + ARC_DIST_MAXNODES * 2u
                        + ARC_DIST_OFFNODES * 4u
                        + ARC_FAST_SIZE * 2u + ARC_OFF_SIZE * 2u;
        err = arc_distill_init(d);
        break;
    case ARC_M_CRUNCH8:
        /* A leading maxbits byte, which the format fixes at 12. */
        {
            int b = unc_bufin_next(in);
            if (b < 0) return UNC_ERR_TRUNCATED;
            if (b != 0x0c) return UNC_ERR_CORRUPT;
        }
        err = unc_lzw_init(&d->lzw, c->al, in, 12, 1, compsize);
        if (err == UNC_OK) d->lzw_open = 1;
        d->rle = 1;
        break;
    case ARC_M_SQUASHED:
        err = unc_lzw_init(&d->lzw, c->al, in, 13, 1, compsize);
        if (err == UNC_OK) d->lzw_open = 1;
        break;
    case ARC_M_COMPRESSED:
        {
            int b = unc_bufin_next(in);
            if (b < 0) return UNC_ERR_TRUNCATED;
            err = unc_lzw_init(&d->lzw, c->al, in, b & 0x1f, 1, compsize);
            if (err == UNC_OK) d->lzw_open = 1;
        }
        break;
    default:
        return UNC_ERR_UNSUPPORTED;
    }
    return err;
}

static void arc_dec_free(ArcDec *d)
{
    if (d->lzw_open) unc_lzw_free(&d->lzw, d->al);
    if (d->mem) unc_free(d->al, d->mem);
    d->mem = 0;
    d->lzw_open = 0;
}

/* ------------------------------------------------------------------ */
/* Header walk                                                        */
/* ------------------------------------------------------------------ */

static int arc_name_ok(const uint8_t *p)
{
    int i;
    if (p[0] == 0) return 0;
    for (i = 0; i < ARC_NAME_LEN && p[i] != 0; i++)
        if (p[i] < 32) return 0;
    return 1;
}

/* Trim as XADARCParser does: to the NUL, then one trailing space, then
 * one trailing dot. */
static uint32_t arc_name_len(const uint8_t *p)
{
    uint32_t n = 0;
    while (n < ARC_NAME_LEN - 1 && p[n] != 0) n++;
    if (n > 1 && p[n - 1] == ' ') n--;
    if (n > 1 && p[n - 1] == '.') n--;
    return n;
}

UncFormat unc_arc_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    uint32_t compsize, uncompsize, nextoff;
    int method;
    uint8_t nb[1];

    if (len < ARC_HDR_MIN) return UNC_FORMAT_UNKNOWN;

    /* ArcMac: the Mac header, then the PC one 59 bytes in. */
    if (head[AM_MAGIC1] == 0x1b && len >= AM_HDRBYTES &&
        head[AM_MAGIC2] == 0x1a && head[AM_KIND] != 0 &&
        head[AM_KIND] == head[AM_MAGIC2 + 1])
        return UNC_FORMAT_ARC;

    if (head[0] != 0x1a) return UNC_FORMAT_UNKNOWN;
    method = head[1];
    if (method == 0) return UNC_FORMAT_UNKNOWN;
    if (method != ARC_M_DIR && method != ARC_M_DIREND && !arc_is_item(method) &&
        (method & 0x7f) > ARC_M_DISTILLED && (method & 0x7f) != ARC_M_COMPRESSED)
        return UNC_FORMAT_UNKNOWN;
    /* An informational item's name field is empty and its uncompressed
     * length is 0 while its payload is not, so neither the name check
     * nor the size relation below applies to one. */
    if (!arc_is_item(method) && !arc_name_ok(head + 2)) return UNC_FORMAT_UNKNOWN;

    compsize = unc_get_u32le(head + 0x0f);
    if (method == ARC_M_STORED_OLD) {
        if (compsize > 0x1000000u) return UNC_FORMAT_UNKNOWN;
        nextoff = 0x19u + compsize;
    } else {
        if (len < 0x1d) return UNC_FORMAT_UNKNOWN;
        uncompsize = unc_get_u32le(head + 0x19);
        if (compsize > 0x1000000u) return UNC_FORMAT_UNKNOWN;
        if (uncompsize > 0x1000000u) return UNC_FORMAT_UNKNOWN;
        if (!arc_is_item(method) && compsize > uncompsize) return UNC_FORMAT_UNKNOWN;
        nextoff = 0x1du + compsize;
        if (method & 0x80) nextoff += 12u;
    }

    /* The strongest thing an ARC file says about itself: the next
     * header, or the end marker, sits exactly where the size puts it. */
    if ((int32_t)nextoff < len) return (head[nextoff] == 0x1a)
           ? UNC_FORMAT_ARC : UNC_FORMAT_UNKNOWN;
    if (!io) return UNC_FORMAT_UNKNOWN;
    if (unc_read_at(io, nextoff, nb, 1) != UNC_OK) return UNC_FORMAT_UNKNOWN;
    return (nb[0] == 0x1a)
           ? UNC_FORMAT_ARC : UNC_FORMAT_UNKNOWN;
}

/* Write one run of decoded bytes, splitting it across the two forks.
 *
 * `at` is the offset of buf[0] within the entry's single stream and
 * `dsplit` how much of that stream is the data fork — the whole of it for
 * plain ARC, the header's data-fork length for ArcMac. A run can straddle
 * the boundary, so it is written in at most two pieces.
 * Source: the fork order is measured, tools/vmac/arcmac.py. */

/* ------------------------------------------------------------------ */
/* Trimmed (method 0x0a, ARC 7.x) — the OTHER 0x0a                    */
/*                                                                    */
/* -lh1-'s adaptive-Huffman LZSS with a stop code, one shorter match  */
/* range and a window of zeros (unc_lzah.c), then RLE90. It shares a  */
/* method number with PAK's Crushed and is a different algorithm, so  */
/* which one an archive means is decided by arc_dialect() below.      */
/*                                                                    */
/* This is the one method here that PUSHES. Everything else is pulled */
/* a byte at a time by arc_byte(), but unc_lzah.c drives its own loop */
/* and is shared with StuffIt method 5 and LZH, so the RLE90 filter   */
/* is written a second time in push form rather than inverting a      */
/* decoder three formats depend on.                                   */
/*                                                                    */
/* Source: reference/deark/modules/arc.c, decompressor_trimmed.       */
/* ------------------------------------------------------------------ */

/* Returned by the sink callback when the declared length is reached,
 * so a stream that would run on stops at once. Any non-zero return
 * aborts unc_lzah_decode; this one is mapped back to success. */
#define ARC_TRIM_DONE  (-999)

typedef struct ArcTrim {
    UncForkOut out;
    uint8_t    buf[UNC_STAGE];
    uint32_t   outsize;
    UncRle90   rle;              /* the filter, driven from the push side */
} ArcTrim;

/* One byte of the FINAL output, until the entry's declared length is
 * reached; the LZH layer above has no idea where that is. */
static int arc_trim_emit(ArcTrim *t, int b)
{
    if (t->outsize != UNC_SIZE_UNKNOWN &&
        unc_fork_pos(&t->out) >= t->outsize)
        return ARC_TRIM_DONE;
    return unc_fork_put(&t->out, (uint8_t)b);
}

/* A run out of the LZH layer, through RLE90 — the same filter the pull
 * side above runs, driven from the other end. The run count is
 * inclusive of the byte already emitted, as arc_byte() reads it. */
static int arc_trim_put(void *ctx, const uint8_t *p, uint32_t n)
{
    ArcTrim *t = (ArcTrim *)ctx;

    while (n-- > 0) {
        int v = unc_rle90_feed(&t->rle, *p++);
        int err;

        if (v == UNC_RLE90_MORE) continue;
        if (v < 0) return v;
        err = arc_trim_emit(t, v);
        while (err == UNC_OK) {
            v = unc_rle90_take(&t->rle);
            if (v == UNC_RLE90_MORE) break;
            err = arc_trim_emit(t, v);
        }
        if (err != UNC_OK) return err;
    }
    return UNC_OK;
}

static int arc_entry_trimmed(UncCtx *c, UncBufIn *in, uint32_t outsize,
                             uint16_t crc16, int write, uint32_t dsplit)
{
    ArcTrim t;
    UncBitIn bi;
    uint32_t cap;
    int err;

    unc_fork_out(&t.out, c, UNC_FORK_DATA, write, UNC_CK_CRC16_ARC,
                 t.buf, UNC_STAGE);
    unc_fork_split(&t.out, 0, dsplit, dsplit, UNC_U32_MAX);
    t.outsize = outsize;
    unc_rle90_init(&t.rle, 1);

    /* The LZH layer's own output is what RLE90 consumes, and RLE90
     * both expands (a run) and contracts (a literal 0x90, which costs
     * two bytes to say), so the cap is twice the declared length. */
    cap = (outsize == UNC_SIZE_UNKNOWN || outsize > 0x7fffffffu)
              ? 0xffffffffu : outsize * 2u + 2u;

    unc_bitin_init(&bi, in);          /* MSB-first, as -lh1- is */
    err = unc_lzah_decode(c->al, &bi, cap, UNC_LZAH_TRIMMED, arc_trim_put, &t);
    if (err == ARC_TRIM_DONE) err = UNC_OK;
    if (err == UNC_OK) err = unc_fork_flush(&t.out);
    else (void)unc_fork_flush(&t.out);

    if (err != UNC_OK) return err;
    if (outsize != UNC_SIZE_UNKNOWN && unc_fork_pos(&t.out) != outsize)
        return UNC_ERR_TRUNCATED;
    if (t.out.crc16 != crc16) return UNC_ERR_CRC;
    return UNC_OK;
}

/* Decode one entry's stream into the sink, checking the CRC.         */
static int arc_entry_data(UncCtx *c, UncBufIn *in, int method,
                          uint32_t compsize, uint32_t outsize, uint16_t crc16,
                          int write, uint32_t dsplit)
{
    ArcDec d;
    UncForkOut o;
    uint8_t out[UNC_STAGE];
    int err;

    /* 0x0a is two methods. Which one this archive means was decided
     * once, by arc_dialect(), and rides in the method int. */
    if ((method & 0x7f) == ARC_M_CRUSHED && (method & ARC_F_TRIMMED))
        return arc_entry_trimmed(c, in, outsize, crc16, write, dsplit);

    err = arc_dec_init(&d, c, in, method, compsize);
    if (err != UNC_OK) { arc_dec_free(&d); return err; }

    unc_fork_out(&o, c, UNC_FORK_DATA, write, UNC_CK_CRC16_ARC,
                 out, UNC_STAGE);
    unc_fork_split(&o, 0, dsplit, dsplit, UNC_U32_MAX);

    for (;;) {
        int b;
        if (outsize != UNC_SIZE_UNKNOWN && unc_fork_pos(&o) >= outsize) break;
        b = arc_byte(&d);
        if (b == -1) break;
        if (b < -1) { err = UNC_ERR_CORRUPT; break; }
        if ((err = unc_fork_put(&o, (uint8_t)b)) != UNC_OK) break;
    }
    if (err == UNC_OK) err = unc_fork_flush(&o);
    arc_dec_free(&d);

    if (err != UNC_OK) return err;
    if (outsize != UNC_SIZE_UNKNOWN && unc_fork_pos(&o) != outsize)
        return UNC_ERR_TRUNCATED;
    if (o.crc16 != crc16) return UNC_ERR_CRC;
    return UNC_OK;
}

/* ARC's "garble": the password is XORed over the COMPRESSED bytes,
 * repeating, and nothing in the file says it was done — SEA's format
 * has no encryption flag and XADMaster says so in as many words ("we
 * should somehow figure out if an ARC file is actually encrypted;
 * however, there seems to be no way to do this"). The only evidence is
 * the entry's own CRC, which means a candidate key can only be graded
 * by decoding the whole entry.
 *
 * So where a password is available at all, the entry is decoded once
 * WITHOUT writing to find the key that checks out, and then again to
 * write it. Deciding as it wrote would mean handing the sink the output
 * of a wrong key and then appending the output of the right one to it —
 * which is exactly what the first version of this did.
 *
 * Source: XADARCParser.m + XADXORHandle.m. */
static int arc_run(UncCtx *c, UncCrypt *cr, uint8_t *iobuf, uint32_t iocap,
                   uint32_t at, int method, uint32_t compsize,
                   uint32_t outsize, uint16_t crc16, int write,
                   uint32_t dsplit, const uint8_t *pw, uint16_t pwlen)
{
    UncBufIn in;
    if (c->io->seek(c->io->ctx, at) < 0) return UNC_ERR_IO;
    unc_bufin_init(&in, c->io, &c->ps, iobuf, iocap);
    in.limit = compsize;
    if (pw) {
        unc_crypt_xor(cr, pw, pwlen);
        in.crypt = cr;
    }
    return arc_entry_data(c, &in, method, compsize, outsize, crc16, write,
                          dsplit);
}

static int arc_entry_data_pw(UncCtx *c, UncCrypt *cr, uint8_t *iobuf,
                             uint32_t iocap, uint32_t at, int method,
                             uint32_t compsize, uint32_t outsize,
                             uint16_t crc16, int write, uint32_t dsplit)
{
    int est, attempt = 0;

    if (!c->opt.password && !c->opt.ask)
        return arc_run(c, cr, iobuf, iocap, at, method, compsize, outsize,
                       crc16, write, dsplit, NULL, 0);

    /* Not garbled at all is the usual case, and the one to establish
     * first: a password given for an archive that does not need one
     * must not break it. */
    est = arc_run(c, cr, iobuf, iocap, at, method, compsize, outsize, crc16,
                  0, dsplit, NULL, 0);
    if (est == UNC_OK)
        return write ? arc_run(c, cr, iobuf, iocap, at, method, compsize,
                               outsize, crc16, write, dsplit, NULL, 0)
                     : UNC_OK;
    if (est != UNC_ERR_CRC && est != UNC_ERR_CORRUPT) return est;

    for (;;) {
        uint8_t pw[UNC_PASSWORD_MAX];
        uint16_t i, n;
        int upper;

        est = unc_password(c, attempt > 0);
        if (est != UNC_OK) return attempt ? UNC_ERR_PASSWORD : UNC_ERR_CRC;

        /* Twice per password: as typed, then upper-cased. `arc` 5.21q
         * upper-cases the password before garbling with it (measured: a
         * stored entry's ciphertext XOR its plaintext is the password in
         * capitals), which is the DOS lineage's habit; XADMaster uses
         * the bytes as given. Neither is wrong, so try both — the format
         * carries nothing that could tell them apart. */
        for (upper = 0; upper < 2; upper++) {
            int same = 1;
            n = c->pwlen;
            for (i = 0; i < n; i++) {
                uint8_t b = c->pw[i];
                pw[i] = (upper && b >= 'a' && b <= 'z') ? (uint8_t)(b - 32) : b;
                if (pw[i] != c->pw[i]) same = 0;
            }
            if (upper && same) break;
            est = arc_run(c, cr, iobuf, iocap, at, method, compsize, outsize,
                          crc16, 0, dsplit, pw, n);
            if (est == UNC_OK)
                return write ? arc_run(c, cr, iobuf, iocap, at, method,
                                       compsize, outsize, crc16, write,
                                       dsplit, pw, n)
                             : UNC_OK;
            if (est != UNC_ERR_CRC && est != UNC_ERR_CORRUPT) return est;
        }
        if (!c->opt.ask) return UNC_ERR_PASSWORD;
        attempt++;
    }
}

/* Which dialect's 0x0a this archive holds, decided once for the whole
 * file. Two signals, and they are the ones deark uses
 * (reference/deark/modules/arc.c: member_cb_for_prescan sets
 * has_arc_extensions, do_pak_trailer sets has_pak_trailer):
 *
 *   - an informational item (0x14, 0x15) or a subdirectory (0x1e) is
 *     something ARC 6/7 writes and PAK does not;
 *   - extended records after the end-of-archive marker — 0xfe then a
 *     byte no greater than 4 — are PAK's, from v1.5 on.
 *
 * Trimmed only when the first is present and the second is not, which
 * is deark's rule. Where neither appears the answer is Crushed:
 * PAK 1.0 wrote neither and its archives are the ones in this corpus,
 * and a wrong answer costs the entry its CRC rather than passing
 * quietly. */
static int arc_dialect(UncCtx *c)
{
    uint8_t h[ARC_HDR_MIN], t[2];
    uint32_t pos = 0, compsize;
    int ext = 0, guard = 0;

    for (;;) {
        if (++guard > 8192) return ext;
        if (unc_read_at(c->io, pos, h, ARC_HDR_MIN) != UNC_OK) return ext;
        if (h[0] != 0x1a) return ext;
        if (h[1] == 0) {                          /* end of archive */
            if (unc_read_at(c->io, pos + 2u, t, 2) == UNC_OK &&
                t[0] == 0xfe && t[1] <= 4)
                return 0;                         /* PAK's own trailer */
            return ext;
        }
        if (arc_is_item(h[1]) || h[1] == ARC_M_DIR) ext = 1;
        compsize = unc_get_u32le(h + 0x0f);
        if (compsize > 0x4000000u) return ext;
        if (h[1] == ARC_M_STORED_OLD) {
            pos += 0x19u + compsize;
        } else {
            pos += 0x1du + compsize;
            if (h[1] & 0x80) pos += 12u;
        }
    }
}

int unc_arc_extract(UncCtx *c)
{
    uint8_t hdr[ARC_HDR_MIN + 12];
    uint8_t *iobuf;
    uint32_t iocap = UNC_IOBUF;
    uint32_t pos = 0;
    uint8_t  path[UNC_NAME_MAX + 1];
    uint32_t plen = 0;
    int err = UNC_OK, any = 0, arcmac = 0, trimmed = 0;
    UncCrypt *cr;

    /* ArcMac? Its Mac header precedes the PC one; the whole file is
     * either one shape or the other. */
    {
        uint8_t probe[AM_HDRBYTES];
        if (unc_read_at(c->io, 0, probe, AM_HDRBYTES) == UNC_OK &&
            probe[AM_MAGIC1] == 0x1b && probe[AM_MAGIC2] == 0x1a)
            arcmac = 1;
    }
    /* ArcMac is 1988 Macintosh software and predates both claimants to
     * 0x0a, so the question is only asked of the plain container. */
    if (!arcmac) trimmed = arc_dialect(c) ? ARC_F_TRIMMED : 0;

    iobuf = (uint8_t *)unc_alloc(c->al, iocap + (uint32_t)sizeof *cr);
    if (!iobuf) return UNC_ERR_MEM;
    cr = (UncCrypt *)(void *)(iobuf + iocap);
    unc_crypt_init(cr);

    for (;;) {
        UncEntryInfo e;
        uint8_t macname[32];
        uint32_t compsize, uncompsize, dlen = 0, rlen = 0;
        uint32_t mactype = 0, maccreator = 0;
        uint16_t crc16;
        int method, sret, est;

        if (arcmac) {
            uint8_t mh[AM_HDRBYTES];
            uint32_t i;
            if (unc_read_at(c->io, pos, mh, AM_HDRBYTES) != UNC_OK) break;
            if (mh[AM_MAGIC1] != 0x1b || mh[AM_MAGIC2] != 0x1a) break;
            method = mh[AM_KIND];
            if (method == 0) break;
            for (i = 0; i < 31 && mh[AM_FNAME + i]; i++) macname[i] = mh[AM_FNAME + i];
            macname[i] = 0;
            mactype    = unc_get_u32be(mh + AM_FTYPE);
            maccreator = unc_get_u32be(mh + AM_FAUTH);
            /* Little-endian, like every other sized field in an ARC
             * header. ARCMAC.DOC marks the fork lengths, with size, date,
             * time and crc, as "stored in archive using Intel 80xxx byte
             * sex"; arc.h gives the offsets but not the order, and this
             * read was big-endian until 2026-08-16. Both archives in the
             * wild confirm it: little-endian, the pair sums to the
             * header's own uncompressed size on every entry.
             * Source: reference/notes/ArcMac.DOC, "ArcMac File Structure". */
            dlen = unc_get_u32le(mh + AM_FDATA);
            rlen = unc_get_u32le(mh + AM_FRSRC);
            compsize = unc_get_u32le(mh + AM_MAGIC2 + 0x0f);
            crc16 = unc_get_u16le(mh + AM_MAGIC2 + 0x17);
            uncompsize = dlen + rlen;
            pos += AM_HDRBYTES;

            unc_entry_clear(&e);
            unc_entry_set_name(&e, macname, i);
            e.type = mactype;
            e.creator = maccreator;
            e.data_size = dlen;
            e.rsrc_size = rlen;
            e.comp_data_size = compsize;
            e.method_data = (uint8_t)(method & 0x7f);

            sret = c->sink->begin_entry(c->sink->ctx, &e);
            if (sret < 0) { err = UNC_ERR_SINK; break; }
            if (sret == 0) {
                /* One compressed stream holds both forks, data fork
                 * first. Nothing states the order — macunpack's arc.c,
                 * the only implementation that ever read the payload, is
                 * absent from the distribution — so it was MEASURED, by
                 * having ArcMac 1.3c itself archive a two-fork file under
                 * the emulator: tools/vmac/arcmac.py, and DECISIONS.md.
                 * The CRC covers the concatenation, so it grades the
                 * split as well as the decode. */
                est = UNC_OK;
                if (!c->opt.list_only)
                    est = arc_entry_data_pw(c, cr, iobuf, iocap, pos,
                                            method & 0x7f, compsize,
                                            uncompsize, crc16,
                                            !c->opt.test_only, dlen);
                if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                    err = UNC_ERR_SINK;
                    break;
                }
                /* A sink failure ends the ARCHIVE, not just the entry: the
                 * host could not write this one and will not be able to
                 * write the next either, so carrying on turns a full disk
                 * into one identical error per remaining entry. Every other
                 * format here already did this; ARC was the one that did
                 * not (measured 2026-08-24, filling the destination volume
                 * with `run.py --out-kb`). */
                if (unc_fatal(est)) {
                    err = est;
                    break;
                }
            }
            any = 1;
            pos += compsize;
            continue;
        }

        if (unc_read_at(c->io, pos, hdr, ARC_HDR_MIN) != UNC_OK) break;
        if (hdr[0] != 0x1a) break;
        method = hdr[1];
        if (method == 0) break;                       /* end of archive */

        if (method == ARC_M_DIREND || method == 0x80) {
            /* Leave the current directory. */
            while (plen > 0 && path[plen - 1] != '/') plen--;
            if (plen > 0) plen--;
            pos += 2;
            continue;
        }

        compsize = unc_get_u32le(hdr + 0x0f);
        crc16    = unc_get_u16le(hdr + 0x17);
        if (method == ARC_M_STORED_OLD) {
            uncompsize = compsize;
            pos += 0x19u;
        } else {
            uncompsize = unc_get_u32le(hdr + 0x19);
            pos += 0x1du;
            if (method & 0x80) pos += 12u;            /* Archimedes fields */
        }

        /* Informational items carry no name and are not members. They
         * come before the name check because an empty name is exactly
         * what one has. */
        if (arc_is_item(method)) { pos += compsize; continue; }

        if (!arc_name_ok(hdr + 2)) { err = UNC_ERR_CORRUPT; break; }

        if (method == ARC_M_DIR) {
            uint32_t nl = arc_name_len(hdr + 2), i;
            if (plen > 0 && plen < UNC_NAME_MAX) path[plen++] = '/';
            for (i = 0; i < nl && plen < UNC_NAME_MAX; i++)
                path[plen++] = hdr[2 + i] == '/' ? (uint8_t)':' : hdr[2 + i];
            any = 1;
            pos += compsize;
            continue;
        }

        unc_entry_clear(&e);
        if (plen) {
            unc_entry_set_path(&e, path, plen);
            unc_entry_path_append(&e, hdr + 2, arc_name_len(hdr + 2));
        } else {
            unc_entry_set_name(&e, hdr + 2, arc_name_len(hdr + 2));
        }
        e.data_size = uncompsize;
        e.rsrc_size = 0;
        e.comp_data_size = compsize;
        e.method_data = (uint8_t)(method & 0x7f);

        sret = c->sink->begin_entry(c->sink->ctx, &e);
        if (sret < 0) { err = UNC_ERR_SINK; break; }
        if (sret == 0) {
            est = UNC_OK;
            if (!c->opt.list_only)
                est = arc_entry_data_pw(c, cr, iobuf, iocap, pos,
                                        method | trimmed,
                                        compsize, uncompsize, crc16,
                                        !c->opt.test_only, uncompsize);
            if (c->sink->end_entry(c->sink->ctx, est) < 0) {
                err = UNC_ERR_SINK;
                break;
            }
            if (unc_fatal(est)) {
                err = est;
                break;
            }
        }
        any = 1;
        pos += compsize;
    }

    unc_free(c->al, iobuf);
    if (!any && err == UNC_OK) return UNC_ERR_FORMAT;
    return err;
}
