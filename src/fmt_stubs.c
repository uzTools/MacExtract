/*
 * fmt_stubs.c — placeholder probes/extractors for formats whose
 * milestone hasn't been reached yet. Each is replaced by a real
 * fmt_*.c implementation as milestones land; the stub is then removed
 * from this file. A stub probe never matches; a stub extractor
 * reports UNC_ERR_UNSUPPORTED.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

#define UNC_STUB_PROBE(fn) \
    int fn(const uint8_t *head, int32_t len) \
    { (void)head; (void)len; return 0; }

#define UNC_STUB_EXTRACT(fn) \
    int fn(UncCtx *c) { (void)c; return UNC_ERR_UNSUPPORTED; }

/* M1 */
int unc_macbinary_probe(const uint8_t *h, int32_t l, UncIO *io)
{ (void)h; (void)l; (void)io; return 0; }
UNC_STUB_EXTRACT(unc_macbinary_extract)
int unc_applesingle_probe(const uint8_t *h, int32_t l, UncFormat *out)
{ (void)h; (void)l; (void)out; return 0; }
int unc_appledouble_extract(UncCtx *c, UncFormat which)
{ (void)c; (void)which; return UNC_ERR_UNSUPPORTED; }

/* M2 */
UNC_STUB_PROBE(unc_binhex_probe)
UNC_STUB_EXTRACT(unc_binhex_extract)

/* M3 */
UNC_STUB_PROBE(unc_packit_probe)
UNC_STUB_EXTRACT(unc_packit_extract)

/* M4 */
int unc_cpt_probe(const uint8_t *h, int32_t l, UncIO *io)
{ (void)h; (void)l; (void)io; return 0; }
UNC_STUB_EXTRACT(unc_cpt_extract)

/* M5/M6 */
UNC_STUB_PROBE(unc_sit_probe)
UNC_STUB_EXTRACT(unc_sit_extract)

/* M7 */
UNC_STUB_PROBE(unc_sit5_probe)
UNC_STUB_EXTRACT(unc_sit5_extract)

/* M8 */
UNC_STUB_PROBE(unc_zip_probe)
UNC_STUB_EXTRACT(unc_zip_extract)
UNC_STUB_PROBE(unc_gzip_probe)
UNC_STUB_EXTRACT(unc_gzip_extract)
UNC_STUB_PROBE(unc_compressz_probe)
UNC_STUB_EXTRACT(unc_compressz_extract)
UNC_STUB_PROBE(unc_tar_probe)
UNC_STUB_EXTRACT(unc_tar_extract)

/* Detect-only */
UNC_STUB_PROBE(unc_sitx_probe)
int unc_diskcopy_probe(const uint8_t *h, int32_t l, UncIO *io)
{ (void)h; (void)l; (void)io; return 0; }
UNC_STUB_PROBE(unc_nowcompress_probe)
UNC_STUB_PROBE(unc_lzh_probe)
