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
