/*
 * unclassic.h — public API of libunclassic.
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
#ifndef UNCLASSIC_H
#define UNCLASSIC_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define UNC_VERSION "0.1.0"

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
    UNC_FORMAT_DISKCOPY,      /* .image — DiskCopy 4.2 disk image     */
    UNC_FORMAT_NOWCOMPRESS,   /* Now Compress archive                 */
    UNC_FORMAT_LZH,           /* .lzh/.lha                            */

    UNC_FORMAT__COUNT
} UncFormat;

/* Human-readable name for a format ("StuffIt 5", "MacBinary", ...). */
const char *unc_format_name(UncFormat f);

/* Nonzero if the engine can extract this format (vs. detect-only). */
int unc_format_extractable(UncFormat f);

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
    UNC_ERR_ENCRYPTED   = -7,   /* entry/archive is encrypted           */
    UNC_ERR_ABORTED     = -8,   /* progress callback requested stop     */
    UNC_ERR_SINK        = -9,   /* sink callback reported failure       */
    UNC_ERR_CORRUPT     = -10,  /* internal structure inconsistency     */
    UNC_ERR_SEGMENTED   = -11   /* multi-segment archive, parts missing */
};

/* Human-readable message for an error code. */
const char *unc_strerror(int err);

/* ------------------------------------------------------------------ */
/* I/O abstraction                                                    */
/* ------------------------------------------------------------------ */

#define UNC_SIZE_UNKNOWN 0xFFFFFFFFu

typedef struct UncIO {
    void *ctx;
    /* Read up to len bytes into buf. Returns bytes read (0 on EOF),
     * or <0 on error. Short reads before EOF are allowed. */
    int32_t (*read)(void *ctx, void *buf, int32_t len);
    /* Absolute seek. Returns 0 on success, <0 on error. */
    int (*seek)(void *ctx, uint32_t pos);
    /* Current position. */
    uint32_t (*tell)(void *ctx);
    /* Total stream size, or UNC_SIZE_UNKNOWN. */
    uint32_t (*size)(void *ctx);
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
    /* Filename: a '/'-separated path of raw name components (MacRoman
     * for Mac formats), NUL-terminated. '/' is ALWAYS a path separator:
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
    uint8_t  method_data;   /* format-specific method id (informational) */
    uint8_t  method_rsrc;
} UncEntryInfo;

/* ------------------------------------------------------------------ */
/* Sink — receives decoded output                                     */
/* ------------------------------------------------------------------ */

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
} UncSink;

/* ------------------------------------------------------------------ */
/* Progress / cooperative yield                                       */
/* ------------------------------------------------------------------ */

typedef struct UncProgress {
    void *ctx;
    /* Invoked at bounded intervals (every <=16 KB of input consumed).
     * Return nonzero to continue, 0 to abort cleanly (UNC_ERR_ABORTED).
     * On classic Mac OS this is where the event loop breathes. */
    int (*tick)(void *ctx, uint32_t bytes_done, uint32_t bytes_total);
} UncProgress;

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
} UncOptions;

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

#ifdef __cplusplus
}
#endif
#endif /* UNCLASSIC_H */
