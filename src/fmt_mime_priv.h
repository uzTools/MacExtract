/* fmt_mime_priv.h — what MIME's probes and its decoder both need.
 *
 * The probes stay resident and the decoder can be an overlay, so the struct a
 * probe fills and the constants it reads live here rather than in either.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#ifndef UNC_FMT_MIME_PRIV_H
#define UNC_FMT_MIME_PRIV_H

#include "unc_internal.h"

#define MIME_MAX_DEPTH   4
#define MIME_BND_MAX     70      /* RFC 2046; reference/mpack/part.h    */
#define MIME_LINE_MAX    1000    /* RFC 5322 caps a line at 998         */
#define MIME_HDR_MAX     512     /* one header, continuation lines and all */
#define MIME_CTYPE_MAX   63
#define MIME_IOBUF       4096
#define MIME_AF_PREFIX   512     /* of an applefile part, decoded       */
#define MIME_AF_ENTRIES  16
#define MIME_SCAN_MAX    16384u  /* how far the probe looks for a header */
#define MIME_NEST_SCAN   4096u   /* how far into a body part the test for a
                                  * pasted document looks */

typedef struct MimeSigns {
    int ctype;                   /* a Content-Type at all      */
    int signal;                  /* something to extract       */
    int bnd;                     /* a multipart WITH a boundary */
} MimeSigns;



int mime_is_space(int c);
int mime_is_header(const uint8_t *s, int32_t len);
int32_t mime_ci_prefix(const uint8_t *s, int32_t len, const char *pfx);
uint32_t mime_param(const uint8_t *h, int32_t hlen, const char *key, uint8_t *out, uint32_t cap, int *trunc);
int mime_cte_of(const uint8_t *h, int32_t hlen);

enum { MIME_CTE_NONE = 0, MIME_CTE_QP, MIME_CTE_B64, MIME_CTE_UU };

int mime_lower(int c);
int32_t mime_strlen(const char *s);

void mime_ctype_of(const uint8_t *h, int32_t hlen, uint8_t *out);

#endif
