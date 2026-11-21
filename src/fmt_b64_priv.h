/* fmt_b64_priv.h — what base64's probe and its decoder both need.
 *
 * Compiled into different places: the probe stays resident, the decoder can
 * be an overlay. One definition, in the probe file, declared here.
 *
 * SPDX-License-Identifier: 0BSD
 */
#ifndef UNC_FMT_B64_PRIV_H
#define UNC_FMT_B64_PRIV_H

#include "unc_internal.h"

#define B64_LINE_MAX   1000       /* a mailer wraps at 76; this is slack */
#define B64_IOBUF      4096
#define B64_SCAN_MAX   8192u      /* how far in a "begin-base64" may sit */
#define B64_MIN_LINES  4
#define B64_MIN_WIDTH  40
#define B64_MAX_WIDTH  76

int b64_val(int c);
/* b64_val, inline, for unc_b64_span's loop alone: a call a character was
 * a fifth of an attachment's decode (2026-11-21). The same ranges. */
static inline int b64_val_inline(int c)
{
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}
int b64_is_begin(const uint8_t *line, int32_t len);
int b64_line_ok(const uint8_t *line, int32_t len);

#endif
