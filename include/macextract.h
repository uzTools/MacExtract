/*
 * macextract.h — public API of libmacextract.
 *
 * A portable, dependency-free C99 decompression engine for classic
 * Macintosh archive and encoding formats (System 6 → Mac OS 9 era).
 *
 * Engine discipline (see CLAUDE.md / DECISIONS.md):
 *   - No libc I/O or allocation: everything goes through caller callbacks.
 *   - No global mutable state; fully re-entrant.
 *   - 32-bit arithmetic only in hot paths (HFS caps files at 2 GB).
 *   - No recursion; bounded stack (< 4 KB call-chain depth).
 *   - All multi-byte reads via byte-wise big-endian helpers.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef MACEXTRACT_H
#define MACEXTRACT_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* The version, and the ONE place it is written. It sat at "0.4.0" through
 * four releases because nothing read it — `macextract --version` and
 * tools/make_dist.sh do now, and tools/check_docs.py fails the build if
 * this, README.md and dist/README.txt disagree. A constant nobody reads
 * is a constant that is wrong. */
#define UNC_VERSION "0.34.0"

/* ------------------------------------------------------------------ */
/* Formats                                                            */
/* ------------------------------------------------------------------ */

typedef enum UncFormat {
    UNC_FORMAT_UNKNOWN = 0,

    /* Extractable (v1) */
    UNC_FORMAT_MACBINARY,     /* .bin — MacBinary I/II/III            */
    UNC_FORMAT_APPLESINGLE,   /* AppleSingle                          */
    UNC_FORMAT_APPLEDOUBLE,   /* AppleDouble header file (._foo)      */
    UNC_FORMAT_BINHEX,        /* .hqx — BinHex 4.0                    */
    UNC_FORMAT_PACKIT,        /* .pit — PackIt                        */
    UNC_FORMAT_COMPACTPRO,    /* .cpt — Compact Pro                   */
    UNC_FORMAT_SIT,           /* .sit — StuffIt classic (1.5–4.x)     */
    UNC_FORMAT_SIT5,          /* .sit — StuffIt 5+                    */
    UNC_FORMAT_ZIP,           /* .zip                                 */
    UNC_FORMAT_GZIP,          /* .gz                                  */
    UNC_FORMAT_COMPRESS_Z,    /* .Z — Unix compress (16-bit LZW)      */
    UNC_FORMAT_TAR,           /* .tar                                 */

    /* Detect-only (named so a UI can tell the user what the file is) */
    UNC_FORMAT_SITX,          /* .sitx — StuffIt X (unsupported v1)   */
    UNC_FORMAT_DISKDOUBLER,   /* DiskDoubler (unsupported v1)         */
    /* RETIRED 2026-08-27 (attic/), and kept as a reserved slot so that
     * no enumerator after it changes value: it shipped in every
     * release up to v0.23.0. unc_sniff never returns it now.       */
    UNC_FORMAT_DISKCOPY_RETIRED,
    UNC_FORMAT_NOWCOMPRESS,   /* Now Compress archive                 */
    UNC_FORMAT_LZH,           /* .lzh/.lha                            */

    /* Extractable, but assembled from several files. Appended here
     * rather than beside the other extractable formats so that no
     * existing enumerator changes value. */
    UNC_FORMAT_SITSEG,        /* one part of a StuffIt segmented set   */
    UNC_FORMAT_ZIPSEG,        /* one part of a spanned (split) zip set */
    UNC_FORMAT_SPLIT,         /* one part of a plain NAME.001 split    */
    UNC_FORMAT_CPTSEG,        /* one segment of a Compact Pro set      */

    /* Brought in scope 2026-08-15 with the rest of what StuffIt
     * Expander 4.0.2 expands; appended for the same ABI reason. */
    UNC_FORMAT_UU,            /* uuencoded file, incl. UUTool's shape  */
    UNC_FORMAT_ARC,           /* .arc — ARC / ArcMac                   */

    /* Brought in scope 2026-08-20; appended for the same ABI reason. */
    UNC_FORMAT_SUPERDISK,     /* Alysis SuperDisk! auto-expanding file  */

    /* Brought in scope 2026-08-21; appended for the same ABI reason. */
    UNC_FORMAT_DDSEG,         /* one part of a DiskDoubler `SPLT` set   */

    /* Brought in scope 2026-08-22; appended for the same ABI reason. */
    UNC_FORMAT_SPACESAVER,    /* StuffIt SpaceSaver compressed file     */

    /* Named, not extracted, since 2026-08-23. */

    /* Brought in scope 2026-08-23; appended for the same ABI reason. */
    UNC_FORMAT_BTOA,          /* btoa/atob ASCII armour                 */

    /* Brought in scope 2026-08-26; appended for the same ABI reason. */
    UNC_FORMAT_BASE64,        /* base64, bare or "begin-base64"         */
    UNC_FORMAT_MIME,          /* a MIME message, incl. appledouble      */

    /* Named, not extracted, since 2026-08-27 (src/fmt_foreign.c). None
     * of these is a Macintosh format and none is in scope to extract;
     * what naming them buys is a user who came here with an archive
     * being told which one it is, instead of "not recognized".      */
    UNC_FORMAT_RAR,           /* .rar — RAR 1.3/1.4 and 1.5-4.x         */
    UNC_FORMAT_RAR5,          /* .rar — RAR 5                           */
    UNC_FORMAT_7Z,            /* .7z                                    */
    UNC_FORMAT_XZ,            /* .xz                                    */
    UNC_FORMAT_BZIP2,         /* .bz2                                   */
    UNC_FORMAT_CAB,           /* .cab — Microsoft Cabinet               */
    UNC_FORMAT_ZOO,           /* .zoo                                   */
    UNC_FORMAT_AR,            /* ar / .deb                              */
    UNC_FORMAT_CPIO,          /* .cpio, and the payload of a .cpgz      */
    UNC_FORMAT_ARJ,           /* .arj                                   */
    UNC_FORMAT_ZSTD,          /* .zst — Zstandard                       */
    UNC_FORMAT_LZIP,          /* .lz                                    */
    UNC_FORMAT_LRZIP,         /* .lrz                                   */
    UNC_FORMAT_WIM,           /* .wim — Windows Imaging                 */
    UNC_FORMAT_AAR,           /* .aar/.yaa — Apple Archive              */

    /* One part of a message/partial set — a message split across
     * several FILES. Joined, never extracted on its own. */
    UNC_FORMAT_MIMESEG,

    UNC_FORMAT__COUNT
} UncFormat;

/* Human-readable name for a format ("StuffIt 5", "MacBinary", ...). */
const char *unc_format_name(UncFormat f);

/* Nonzero if the engine can extract this format (vs. detect-only). */
int unc_format_extractable(UncFormat f);

/* Nonzero if this format holds exactly one file and is worth looking
 * inside: what a host unwraps to reach the archive underneath
 * (.sit.hqx, .cpt.bin, .tar.Z). Not every format that yields one file —
 * see the table in src/unc_engine.c for which and why. */
int unc_format_is_envelope(UncFormat f);

/* ------------------------------------------------------------------ */
/* Error codes (negative; 0 = success)                                */
/* ------------------------------------------------------------------ */

enum {
    UNC_OK              =  0,
    UNC_ERR_FORMAT      = -1,   /* not a recognized/valid archive       */
    UNC_ERR_IO          = -2,   /* read/seek failure from UncIO         */
    UNC_ERR_MEM         = -3,   /* allocation failed / over budget      */
    UNC_ERR_CRC         = -4,   /* checksum mismatch (per entry)        */
    UNC_ERR_TRUNCATED   = -5,   /* file ends before the data does       */
    UNC_ERR_UNSUPPORTED = -6,   /* recognized but not extractable       */
    UNC_ERR_ENCRYPTED   = -7,   /* encrypted by a scheme we cannot read */
    UNC_ERR_ABORTED     = -8,   /* progress callback requested stop     */
    UNC_ERR_SINK        = -9,   /* sink callback reported failure       */
    UNC_ERR_CORRUPT     = -10,  /* internal structure inconsistency     */
    UNC_ERR_SEGMENTED   = -11,  /* multi-segment archive, parts missing */
    UNC_ERR_PASSWORD    = -12,  /* encrypted, and no usable password      */
    UNC_ERR_TOOLARGE    = -13   /* entry past this engine's 32-bit reach  */
    /* -14 was UNC_ERR_NOTCOMPRESSED, for a DART that was already
     * uncompressed. DART left the engine on 2026-09-25 (DECISIONS.md,
     * *the disk images that found another home*); the number is not
     * reused, so a caller built against an older header cannot read a
     * new code as that one.                                            */
};

/* Human-readable message for an error code. */
const char *unc_strerror(int err);

/* ------------------------------------------------------------------ */
/* I/O abstraction                                                    */
/* ------------------------------------------------------------------ */

/* Three ceilings, named because they are three different ideas that
 * currently share two numbers. Naming them is what makes every place
 * with an opinion about a limit greppable, and what a host uses to
 * state the same limit without repeating a literal.
 *
 * UNC_OFF_MAX and UNC_SIZE_UNKNOWN are the SAME VALUE today: a size
 * field of all-ones reads both as "unknown" and as "the largest
 * offset this engine can address". Nothing depends on the
 * coincidence, and they are separate names because the day the
 * offset type widens they stop being the same number.
 */

/* The type a container offset is carried in, and the widest value it
 * holds. 32 bits by default — the 68000 target, where a file cannot
 * exceed 2 GB anyway — and 64 bits when the host builds with
 * UNC_OFF64, which is what lets it address a container past 4 GiB.
 *
 * Only CONTAINER addressing widens. An entry's own size stays 32-bit
 * (UncEntryInfo.data_size), because a fork past 4 GiB is a separate
 * question and no target here can write one. */
#ifdef UNC_OFF64
typedef uint64_t unc_off_t;
#define UNC_OFF_MAX      0xFFFFFFFFFFFFFFFFull
#else
typedef uint32_t unc_off_t;
#define UNC_OFF_MAX      0xFFFFFFFFu
#endif

/* The largest value a 32-bit field holds. Used where a span, a budget
 * or a saturating sum is 32-bit by DEFINITION and does not follow
 * unc_off_t: a fork's extent, a read budget, the sum of two fork
 * sizes. These do not widen when container addressing does. */
#define UNC_U32_MAX      0xFFFFFFFFu

/* A container whose size the host cannot state. Distinct from
 * UNC_SIZE_UNKNOWN, which is an ENTRY's; the two are the same number
 * at 32 bits and different numbers at 64, which is exactly why they
 * are two names. */
#define UNC_OFF_UNKNOWN  UNC_OFF_MAX

/* The 2 GB ceiling every classic Macintosh file lives under: HFS caps
 * a fork there, and the File Manager's own position parameter is a
 * signed 32-bit long. A declared fork size, a declared entry size or
 * an offset inside a Macintosh container past this is not a file any
 * target could hold, and is refused where it is read. */
#define UNC_MAC_MAX      0x7FFFFFFFu

/* A size field that states nothing: a streamed entry whose length is
 * not known until it ends. */
#define UNC_SIZE_UNKNOWN 0xFFFFFFFFu

typedef struct UncIO {
    void *ctx;
    /* Read up to len bytes into buf. Returns bytes read (0 on EOF),
     * or <0 on error. Short reads before EOF are allowed. */
    int32_t (*read)(void *ctx, void *buf, int32_t len);
    /* Absolute seek. Returns 0 on success, <0 on error. */
    int (*seek)(void *ctx, unc_off_t pos);
    /* Current position. */
    unc_off_t (*tell)(void *ctx);
    /* Total stream size, or UNC_OFF_UNKNOWN. */
    unc_off_t (*size)(void *ctx);
} UncIO;

/* ------------------------------------------------------------------ */
/* Allocator                                                          */
/* ------------------------------------------------------------------ */

typedef struct UncAlloc {
    void *ctx;
    /* Returns NULL on failure (including budget exhaustion). */
    void *(*alloc)(void *ctx, uint32_t size);
    void  (*free)(void *ctx, void *ptr);
} UncAlloc;

/* ------------------------------------------------------------------ */
/* Entry metadata                                                     */
/* ------------------------------------------------------------------ */

#define UNC_NAME_MAX 255   /* raw bytes; Mac names are <=31, zip/tar longer */

typedef enum UncFork { UNC_FORK_DATA = 0, UNC_FORK_RSRC = 1 } UncFork;

typedef struct UncEntryInfo {
    /* Filename: a '/'-separated path of raw name components, in the
     * ARCHIVE's own encoding (MacRoman for most Mac formats; see
     * name_utf8), NUL-terminated. '/' is ALWAYS a path separator:
     * in Mac-format components the engine applies the classic
     * reversible '/'->':' swap (':' cannot occur in an HFS name, '/'
     * can), so a raw '/' never leaks into a component. zip/tar paths
     * pass through unchanged ('/' is genuinely their separator). */
    uint8_t  name[UNC_NAME_MAX + 1];
    uint16_t name_len;

    uint32_t type;          /* Mac type code, 0 if unknown    */
    uint32_t creator;       /* Mac creator code, 0 if unknown */
    uint16_t finder_flags;  /* Finder flags, 0 if unknown     */
    uint32_t create_date;   /* Mac epoch (1904) secs, 0 if unknown */
    uint32_t mod_date;      /* Mac epoch (1904) secs, 0 if unknown */

    uint32_t data_size;     /* uncompressed data fork size, or UNC_SIZE_UNKNOWN */
    uint32_t rsrc_size;     /* uncompressed rsrc fork size, or UNC_SIZE_UNKNOWN */
    uint32_t comp_data_size;/* compressed sizes (informational), or UNKNOWN */
    uint32_t comp_rsrc_size;

    uint8_t  is_dir;        /* directory entry (no forks)     */
    /* The name bytes above are UTF-8, not the 8-bit encoding the rest
     * of that format's family uses. StuffIt 5 is the one format here
     * that sets it: its names are UTF-8 where StuffIt classic's are
     * MacRoman (reference/deark/modules/stuffit.c picks the encoding
     * on `file_fmt`, and `lsar -nr` unforced agrees). The engine does
     * not convert — a host decides what its filesystem wants; the
     * Linux CLI passes UTF-8 through and the Macintosh shell folds it
     * into MacRoman, which is what an HFS name holds. */
    uint8_t  name_utf8;
    uint8_t  method_data;   /* format-specific method id (informational) */
    uint8_t  method_rsrc;
    /* Set when the archive's name for this entry was LONGER than
     * UNC_NAME_MAX and `name` holds only the first UNC_NAME_MAX bytes
     * of it. The engine cannot carry more (the buffer is part of this
     * struct, which a 68000 host puts on a 4 KB stack), and it does not
     * decide what that means: a host writing to a filesystem with room
     * for the whole name should treat it as a per-entry failure rather
     * than write a file under a name nobody asked for, while a host
     * that shortens every name to fit its own filesystem — the classic
     * Mac one does, at 31 characters — has already made that choice.
     * Before 2026-08-27 the truncation happened with nothing said. */
    uint8_t  name_truncated;   /* 0 = whole; 1 = cut; 2 = cut, and the
                                * WHOLE name is in UncOptions.long_name */
    /* How long the name was BEFORE it was cut, saturating at 65,535, or
     * 0 where the format cannot say — a name cut by a line buffer took
     * its own length with it. The bytes themselves are gone: they are
     * never held anywhere, which is the point of the cap. */
    uint16_t name_full_len;
} UncEntryInfo;

/* ------------------------------------------------------------------ */
/* Sink — receives decoded output                                     */
/* ------------------------------------------------------------------ */

/* The largest an archive comment can be: zip writes its length in two
 * bytes, Compact Pro in one. A host must not size a fixed buffer by
 * this — the engine hands over its own. */
#define UNC_COMMENT_MAX 65535u

typedef struct UncSink {
    void *ctx;
    /* Called once per entry before any writes. Return 0 to accept,
     * >0 to skip this entry (its data is not decoded and end_entry is
     * not called for it), <0 to abort the archive. */
    int (*begin_entry)(void *ctx, const UncEntryInfo *info);
    /* Decoded bytes for one fork. Return 0 on success, <0 on failure. */
    int (*write)(void *ctx, UncFork fork, const void *buf, int32_t len);
    /* Entry finished; status is UNC_OK or a per-entry error (e.g.
     * UNC_ERR_CRC). Return 0 to continue with next entry, <0 to abort. */
    int (*end_entry)(void *ctx, int status);
    /* The archive's OWN comment — text that belongs to the archive
     * rather than to any entry. Called once, before the first
     * begin_entry, and only when the archive carries a non-empty one.
     * `buf` holds `len` raw bytes (MacRoman for the Mac formats), not
     * NUL-terminated, 1..UNC_COMMENT_MAX; it is the engine's and is
     * not valid after the call returns. Return 0 to continue, <0 to
     * abort the archive (UNC_ERR_SINK).
     * MAY BE NULL: nothing else then happens to the comment (Compact
     * Pro's is still read and checksummed as part of the index, zip's
     * is not read at all), which is what every host did before
     * 2026-08-23.
     * Compact Pro and zip are the v1 formats that carry one.
     * A comment the engine cannot buffer or read is DROPPED, not
     * turned into an error: it is worth less than the entries. */
    int (*comment)(void *ctx, const uint8_t *buf, uint16_t len);
} UncSink;

/* ------------------------------------------------------------------ */
/* Progress / cooperative yield                                       */
/* ------------------------------------------------------------------ */

typedef struct UncProgress {
    void *ctx;
    /* Invoked at bounded intervals: every <=16 KB of input consumed
     * through the shared reader, and for a format that pulls a whole
     * compressed BLOCK at a time, once per block — Now Compress's is at
     * most 32 KB, the largest interval any format here has. Return
     * nonzero to continue, 0 to abort cleanly (UNC_ERR_ABORTED).
     * On classic Mac OS this is where the event loop breathes, so a
     * decoder that never calls it freezes the progress dialog and puts
     * both Cancel routes out of reach — which Now Compress did until
     * 2026-08-28, measured on Mac OS 9 rather than deduced. */
    int (*tick)(void *ctx, uint32_t bytes_done, uint32_t bytes_total);
} UncProgress;

/* ------------------------------------------------------------------ */
/* Passwords                                                          */
/*                                                                    */
/* Five of the formats here can encrypt an entry, and each of them    */
/* derives its key from a password the archive does not contain:      */
/* StuffIt classic (DES), StuffIt 5 (RC4), PackIt (an XOR whose key   */
/* is the DES key permutation, or DES), zip (PKWARE's stream cipher   */
/* or WinZip's AES), and ARC (a plain repeating XOR).                 */
/*                                                                    */
/* A host supplies one of two ways: `password`, set before the call,  */
/* or `ask`, called the first time an entry actually needs one — the  */
/* second exists because on a Mac the natural moment to put up a      */
/* dialog is when the archive turns out to need it, not before. Where */
/* the format can TELL a wrong password from a right one (all but     */
/* ARC), `ask` is called again with a rising `attempt` until it       */
/* either verifies or the host gives up.                              */
/* ------------------------------------------------------------------ */

#define UNC_PASSWORD_MAX 64   /* raw bytes; no format here uses more   */

typedef struct UncPasswordSource {
    void *ctx;
    /* Write up to `cap` raw password bytes into buf and set *len.
     * Return 1 if a password was supplied, 0 if the user declined —
     * the entry then fails with UNC_ERR_PASSWORD and the walk goes on.
     * `attempt` is 0 the first time and rises each time a password
     * this callback supplied was REJECTED by the archive, so a host
     * can say "wrong password, try again" rather than repeating
     * itself. The bytes are the password's own encoding: MacRoman for
     * the Mac formats, which is what a Mac dialog produces anyway. */
    int (*ask)(void *ctx, uint8_t *buf, uint16_t cap, uint16_t *len,
               int attempt);
} UncPasswordSource;

/* ------------------------------------------------------------------ */
/* Options                                                            */
/* ------------------------------------------------------------------ */

typedef struct UncOptions {
    /* If nonzero: parse containers and report entries via
     * begin_entry/end_entry, but decode/write no data.
     * (Listing is streaming extract minus the writes — see DECISIONS.md.) */
    uint8_t list_only;
    /* If nonzero: verify CRCs by decoding but discard output. */
    uint8_t test_only;
    /* Fallback entry name for formats that store none (gzip, .Z):
     * conventionally the archive filename minus its last extension
     * (what unar does). May be NULL; the engine then emits an empty
     * name. Raw bytes, not necessarily NUL-terminated. */
    const uint8_t *name_hint;
    uint16_t       name_hint_len;
    /* SpaceSaver's LZSS starts with its window loaded from a preset
     * dictionary that ships inside SpaceSaver itself ('PrAm' -4048,
     * 9,679 bytes) — see FORMATS.md, "StuffIt SpaceSaver's container".
     * That table is Aladdin's and is not in this repository, so a
     * caller that has a copy passes it here. Without it, an entry whose
     * stream reaches back into the dictionary fails as corrupt rather
     * than decoding to something wrong. May be NULL. */
    const uint8_t *preset;
    uint32_t       preset_len;
    /* Password for encrypted entries, raw bytes; NULL if the host has
     * none to offer up front. Not NUL-terminated, so an empty password
     * (which zip permits) is a non-NULL pointer with password_len 0. */
    const uint8_t *password;
    uint16_t       password_len;
    /* Asked when an entry needs a password and none has verified yet.
     * May be NULL, in which case `password` is the only one tried. */
    const UncPasswordSource *ask;
    /* Where to put a name that does not fit `UncEntryInfo.name`. A host
     * with room — one whose display is text rather than a filesystem —
     * passes a buffer here, and the engine writes the WHOLE name into
     * it (raw bytes, NUL-terminated, cut only at `long_name_cap`)
     * wherever the format still holds it when the cut is made;
     * `name_truncated` is then 2 rather than 1. NULL, and the classic
     * Mac shell passes NULL, costs nothing and loses only the text: the
     * length is still reported in `name_full_len`.
     * A NON-NULL pointer is WRITTEN in the formats that walk folders
     * (DiskDoubler, SuperDisk!, Now Compress) for every path component,
     * cut or not — the uncut path accumulates here. So a host that has
     * no buffer must pass NULL, not leave the field unset: the Mac shell
     * left it unset from the day it was added until 2026-09-04, and
     * three formats bombed on Mac OS 9 through whatever its stack held
     * (DECISIONS.md 2026-09-04, *the field nobody assigned*).
     * A format that has already dropped the bytes by then — uuencode's
     * 96-byte line buffer, MIME's 512-byte header — cannot fill this,
     * and says so by leaving `name_truncated` at 1. */
    uint8_t *long_name;
    uint32_t long_name_cap;
    /* StuffIt classic keeps the block that VERIFIES a password, and
     * half of the material the file keys are built from, in the
     * ARCHIVE's own resource fork — 'MKey' 0, eight bytes. It is
     * therefore not in the bytes UncIO reads, and an encrypted .sit
     * whose resource fork was lost cannot be decrypted by anything,
     * this engine included. A host that has the fork passes those
     * eight bytes here (unc_resfork_find will locate them in a raw
     * fork; a Mac may as well ask the Resource Manager). NULL if the
     * host has no resource fork for the archive. */
    const uint8_t *mkey;
} UncOptions;

/* Locate one resource in a raw resource fork. Returns UNC_OK and sets
 * `off` and `len` to the resource's data within `fork`, or returns
 * UNC_ERR_FORMAT.
 * Provided because the one piece of key material this engine cannot
 * read out of the archive stream lives in a resource fork, and a host
 * without a Resource Manager would otherwise have to parse one itself.
 * Source: Inside Macintosh: More Macintosh Toolbox, "Resource File
 * Format" (offsets transcribed in src/unc_crypt.c). */
int unc_resfork_find(const uint8_t *fork, uint32_t forklen,
                     uint32_t type, int16_t id,
                     uint32_t *off, uint32_t *len);

/* ------------------------------------------------------------------ */
/* Entry points                                                       */
/* ------------------------------------------------------------------ */

/* Identify the format by content (magic bytes), never by name.
 * Reads from the current position; seeks freely; leaves position
 * undefined. Returns UNC_FORMAT_UNKNOWN if nothing matches. */
UncFormat unc_sniff(UncIO *io);

/* Extract (or list/test, per opt) every entry of the archive at io.
 * Per-entry failures are reported through end_entry(status) and do not
 * abort the archive. Returns UNC_OK if the container was walked to the
 * end, or a fatal error. opt may be NULL (defaults: full extract). */
int unc_extract(UncIO *io, UncSink *sink, UncAlloc *al,
                UncProgress *prog, const UncOptions *opt);

/* Same, but skip sniffing and force a specific format. */
int unc_extract_as(UncFormat f, UncIO *io, UncSink *sink, UncAlloc *al,
                   UncProgress *prog, const UncOptions *opt);

/* ------------------------------------------------------------------ */
/* Multi-segment archives                                             */
/*                                                                    */
/* A segmented archive is one logical stream cut across several        */
/* files, one per floppy. Five schemes are supported, and they differ  */
/* in one respect — how much a part can prove about itself:            */
/*                                                                    */
/*  UNC_FORMAT_SITSEG  Every part carries a header that names the set, */
/*      numbers the part within it, and fingerprints the original      */
/*      file, so a part is identified BY CONTENT: filenames are a hint */
/*      for finding candidates and never evidence that one belongs.    */
/*                                                                    */
/*  UNC_FORMAT_CPTSEG  A Compact Pro segment carries the same 8-byte   */
/*      header an ordinary archive has, holding a 16-bit identity that  */
/*      every segment of the set shares and an index offset that is 0   */
/*      in all but the LAST. So identity is content, as for SITSEG —    */
/*      unc_segment_match answers for it — but the part COUNT lives     */
/*      only in the final segment, and unc_segment_describe answers     */
/*      with nparts == 0 from any other. A host given a middle segment  */
/*      is expected to find the final one (it can: every part           */
/*      identifies itself) and describe that. Entries are addressed as  */
/*      (volume, offset within that volume), so the reader translates   */
/*      rather than flattens. DERIVED from specimens, not transcribed:  */
/*      see src/fmt_cptseg.c.                                           */
/*                                                                    */
/*  UNC_FORMAT_ZIPSEG  A spanned ("split") zip stores nothing of the   */
/*      kind. Only the FIRST part (a local file header at offset 4)    */
/*      and the LAST (the end-of-central-directory record, which is    */
/*      also the only place the part COUNT is written) can be          */
/*      recognized at all; parts in between are undistinguished data.  */
/*      So the host orders them by filename and the engine adjudicates */
/*      the result structurally — see unc_extract_segments. Names      */
/*      propose; content disposes.                                     */
/*                                                                    */
/*  UNC_FORMAT_SPLIT   A plain NAME.001 / NAME.002 split proves        */
/*      nothing at all: no header, no marker, no part count anywhere,  */
/*      and the payload is a byte concatenation. The whole scheme is   */
/*      the naming convention, so the DESCRIPTOR IS BUILT BY THE HOST  */
/*      — unc_segment_describe never returns this scheme, because      */
/*      there is nothing in a part to read it out of. The host fills   */
/*      in scheme, nparts, part and name; the engine joins.            */
/*                                                                    */
/*      What adjudicates such a set is the file it joins back into: a  */
/*      .sit or .cpt or .zip states its own lengths and checksums, and */
/*      one entry is emitted for the caller to hand to that reader     */
/*      (the CLI does it automatically, as for any envelope). Where    */
/*      that file is not an archive, NOTHING checks the join — and a   */
/*      set missing its TAIL is invisible even when it is, because no  */
/*      part count exists to miss. This scheme is the weak one on      */
/*      purpose; see DECISIONS.md 2026-08-09.                          */
/*                                                                    */
/*  UNC_FORMAT_DDSEG   DiskDoubler's own Split command, `SPLT`. The    */
/*      strongest of the five and the only one no reference reads: a   */
/*      94-byte header per part carries the set's identity, the part's */
/*      INDEX, the part COUNT, both fork lengths of the original and   */
/*      this part's own payload length. So a part is identified by     */
/*      content like a StuffIt one, a missing tail is detectable       */
/*      unlike a .NNN split, and the payload is bounded by the header  */
/*      rather than by the file's size. It carries no NAME — that is   */
/*      the host's, as for a plain split — and the joined payload is   */
/*      the DATA fork first, then the resource fork, which is the      */
/*      opposite of StuffIt's. DERIVED from specimens, not             */
/*      transcribed: src/fmt_ddseg.c.                                  */
/*                                                                    */
/*  UNC_FORMAT_MIMESEG A message split across several FILES:           */
/*      message/partial (RFC 2046 5.2.2), which is how a file too big  */
/*      for a mail gateway crossed one. Every part names the set (an   */
/*      `id` parameter that they all repeat) and numbers itself, so a  */
/*      part is identified BY CONTENT like a StuffIt one — but a mail  */
/*      header is longer than the 100 bytes unc_segment_match is       */
/*      given, so that call answers 0 for this scheme and a host       */
/*      identifies a candidate with unc_segment_describe instead.      */
/*      Two things are unlike every other scheme: a part's header is   */
/*      its own mail headers, so each part's is a DIFFERENT length,    */
/*      and the set states a part COUNT but no byte total, so the      */
/*      joiner learns the length when it opens the last part. What is  */
/*      joined is the part BODIES, in number order; part 1's body      */
/*      begins with the enclosed message's own headers, so the joined  */
/*      stream is a message and the MIME walk reads it directly.       */
/*                                                                    */
/* The engine sequences the parts; the host opens them. That keeps     */
/* every file operation on the caller's side (engine discipline) and   */
/* puts the "where is part 2?" question — a directory scan, a dialog,  */
/* a disk swap — where it belongs.                                     */
/* ------------------------------------------------------------------ */

#define UNC_SEG_HEAD      100  /* bytes of a part the engine inspects   */
#define UNC_SEG_FP_LEN     26  /* fingerprint length, in those bytes    */
#define UNC_SEG_MAX_PARTS 256  /* part numbers are one byte             */
#define UNC_DDSEG_HEAD     94  /* a DiskDoubler `SPLT` part's header    */

/* Identity of a SET, plus which part of it we happened to look at. */
typedef struct UncSegmentDesc {
    UncFormat scheme;        /* SITSEG, CPTSEG, ZIPSEG or SPLIT         */
    uint16_t  part;          /* part number of the inspected file, >= 1 */
    uint32_t  head_len;      /* header bytes to drop from each part      */

    /* Name of the ORIGINAL file (not of any part), raw MacRoman.
     * Empty when the scheme does not store one (ZIPSEG). A host may
     * fill it in for display; nothing in the engine reads it — except
     * under SPLIT, where it is the only name there is and becomes the
     * emitted entry's, so it is host-supplied bytes in the host's own
     * encoding rather than MacRoman. */
    uint8_t   name[UNC_NAME_MAX + 1];
    uint16_t  name_len;

    /* Opaque bytes that must agree across every part of the set.
     * All zero for a scheme that fingerprints nothing (ZIPSEG, SPLIT).
     * CPTSEG spends two bytes on it, in fp[0..1]. */
    uint8_t   fp[UNC_SEG_FP_LEN];

    /* How many parts the set has, or 0 when the scheme does not say
     * and `total` is what ends the walk (SITSEG). Exactly one of the
     * two is always known: a joiner that had neither could not tell a
     * complete set from a truncated one. SPLIT stores neither in the
     * files, so the count is the host's — how many consecutively
     * numbered parts it found — and it is required. */
    uint16_t  nparts;

    /* Decoded from the fingerprint: what the joined stream contains.
     * `total` is UNC_SIZE_UNKNOWN when the scheme does not declare it,
     * in which case the joiner measures it by opening every part. */
    uint32_t  total;         /* payload bytes across all parts          */
    uint32_t  data_size, rsrc_size;
    uint32_t  type, creator;
    uint16_t  finder_flags;
    uint32_t  create_date, mod_date;
} UncSegmentDesc;

/* Describe the set that the file at `io` is a part of.
 * Returns UNC_OK, or UNC_ERR_FORMAT if this is not a segment.
 *
 * SPLIT is never the answer: a part of one carries nothing to read.
 * A host that has decided by name builds the descriptor itself.
 *
 * For ZIPSEG this only ever succeeds on the LAST part, because the
 * end-of-central-directory record is the one place a spanned zip
 * writes its part count. Hand it any other part and it answers
 * UNC_ERR_FORMAT — the host is expected to find the last one, which
 * for that scheme it can only do by name. */
int unc_segment_describe(UncIO *io, UncSegmentDesc *desc);

/* Test a candidate file's first bytes against a known set. Returns its
 * part number (>= 1) if it belongs, or 0. `len` under UNC_SEG_HEAD
 * always answers 0: a candidate too short to prove itself is not one.
 *
 * Answers 0 for every candidate of a scheme whose parts carry no
 * identity (ZIPSEG, SPLIT). That is not "this file does not belong" —
 * it is "this scheme cannot be asked", and a host that orders parts by
 * name must not read a 0 here as a refusal. Use unc_sniff to check the
 * two parts of a spanned zip that ARE recognizable. */
int unc_segment_match(const UncSegmentDesc *desc,
                      const uint8_t *head, int32_t len);

/* Supplies parts on demand.
 *
 * ZERO THIS STRUCT BEFORE FILLING IT IN. Optional members are marked by
 * being NULL, so a caller that leaves one holding whatever was on the
 * stack is telling the engine to call it. `size` was added on
 * 2026-08-09 and every existing caller — including two unit tests that
 * went on passing — was doing exactly that. */
typedef struct UncVolumeSource {
    void *ctx;
    /* Open part `part` (1-based) of `desc` and fill *io. Return UNC_OK,
     * UNC_ERR_SEGMENTED if it cannot be produced (missing, or the user
     * declined), or another negative error. The engine may ask for a
     * part it has already read: hosts that can should remember where
     * each part was found rather than asking the user twice. */
    int  (*need)(void *ctx, const UncSegmentDesc *desc, int part, UncIO *io);
    /* Release a stream previously handed over by need(). May be NULL.
     * The engine releases the current part before asking for another,
     * so a host is never required to hold two open at once. */
    void (*release)(void *ctx, UncIO *io);
    /* Length of part `part`, IF that can be answered for nothing — a
     * directory lookup, not a disk swap. May be NULL, and returning
     * UNC_SIZE_UNKNOWN for any part is a normal answer.
     *
     * It is only ever used to give the progress callback a denominator.
     * A host with one drive genuinely cannot know the total until every
     * disk has been seen, and going to look would cost the user the
     * swaps this design exists to avoid, so a NULL here means the
     * progress callback is told UNC_SIZE_UNKNOWN and nothing else
     * changes. Never answer by opening the part. */
    uint32_t (*size)(void *ctx, const UncSegmentDesc *desc, int part);
} UncVolumeSource;

/* Joins the parts of `desc` and extracts the result.
 *
 * SITSEG yields one entry, with the original file's name, type/creator,
 * dates and both forks; whatever that file turns out to be (usually a
 * .sit) is the caller's next layer, exactly as for MacBinary or BinHex.
 * ZIPSEG runs the ordinary zip reader over the joined stream and yields
 * the archive's entries directly — there is no envelope to unwrap.
 * SPLIT yields one entry too — the joined file, under `desc->name`,
 * data fork only — and needs its total length before it can say how
 * big that entry is: either `desc->total`, or the sum of what the
 * volume source's `size` callback answers for every part. With
 * neither it returns UNC_ERR_CORRUPT rather than guess, because the
 * scheme has nothing else that could end the walk.
 *
 * For ZIPSEG this is also where a wrongly assembled set is caught. The
 * host ordered the parts by name, which is evidence of nothing, so the
 * joined stream is required to agree with itself: the part count must
 * match the one the end-of-central-directory record states, the central
 * directory must begin where that record says it does, and every entry's
 * local header must be found at the offset the directory gives for it.
 * A set in the wrong order fails these rather than decoding to rubbish.
 *
 * `scratch` is caller-owned working storage for the joiner, of at
 * least unc_segment_scratch_size() bytes, aligned for uint32_t. It is
 * a caller allocation because on a 1 MB Mac it belongs in the heap
 * rather than on an 8 KB stack. */
uint32_t unc_segment_scratch_size(void);
int unc_extract_segments(const UncSegmentDesc *desc, UncVolumeSource *vs,
                         void *scratch, UncSink *sink, UncAlloc *al,
                         UncProgress *prog, const UncOptions *opt);

/* How the last unc_extract_segments() call on `scratch` moved between
 * parts: how many opens it asked for, and how many of those were a
 * backward seek re-opening a part already read. On removable media the
 * second number is what a disk swap costs, so it is measured rather
 * than assumed. Either pointer may be NULL. */
void unc_segment_stats(const void *scratch, uint32_t *part_switches,
                       uint32_t *backward_crossings);

#ifdef __cplusplus
}
#endif
#endif /* MACEXTRACT_H */
