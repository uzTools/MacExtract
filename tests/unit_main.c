/*
 * unit_main.c — unit tests for libunclassic internals.
 * Uses libc freely (test code runs on Linux only).
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unclassic.h"
#include "unc_internal.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures = 0;
static int checks = 0;

#define CHECK(cond) do { \
    checks++; \
    if (!(cond)) { \
        failures++; \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
    } \
} while (0)

/* ------------------------------------------------------------------ */
/* Memory-backed UncIO for tests                                      */
/* ------------------------------------------------------------------ */

typedef struct {
    const uint8_t *data;
    uint32_t size, pos;
} MemIO;

static int32_t mio_read(void *ctx, void *buf, int32_t len)
{
    MemIO *m = (MemIO *)ctx;
    uint32_t left = m->size - m->pos;
    uint32_t n = (uint32_t)len < left ? (uint32_t)len : left;
    memcpy(buf, m->data + m->pos, n);
    m->pos += n;
    return (int32_t)n;
}

static int mio_seek(void *ctx, uint32_t pos)
{
    MemIO *m = (MemIO *)ctx;
    if (pos > m->size) return -1;
    m->pos = pos;
    return 0;
}

static uint32_t mio_tell(void *ctx) { return ((MemIO *)ctx)->pos; }
static uint32_t mio_size(void *ctx) { return ((MemIO *)ctx)->size; }

void test_make_memio(UncIO *io, MemIO *m, const uint8_t *data, uint32_t size)
{
    m->data = data; m->size = size; m->pos = 0;
    io->ctx = m;
    io->read = mio_read; io->seek = mio_seek;
    io->tell = mio_tell; io->size = mio_size;
}

/* Plain malloc allocator for tests. */
static void *ta_alloc(void *ctx, uint32_t size) { (void)ctx; return malloc(size); }
static void ta_free(void *ctx, void *p) { (void)ctx; free(p); }
void test_make_alloc(UncAlloc *al)
{
    al->ctx = NULL; al->alloc = ta_alloc; al->free = ta_free;
}

/* ------------------------------------------------------------------ */
/* Tests                                                              */
/* ------------------------------------------------------------------ */

static void test_be_readers(void)
{
    const uint8_t b[] = { 0x12, 0x34, 0x56, 0x78 };
    CHECK(unc_get_u16be(b) == 0x1234);
    CHECK(unc_get_u32be(b) == 0x12345678u);
    CHECK(unc_get_u16le(b) == 0x3412);
    CHECK(unc_get_u32le(b) == 0x78563412u);
}

static void test_crc(void)
{
    /* Standard check values for the two polynomials. */
    const uint8_t s[] = "123456789";
    CHECK(unc_crc16_xmodem(0, s, 9) == 0x31C3);
    CHECK((unc_crc32(0xFFFFFFFFu, s, 9) ^ 0xFFFFFFFFu) == 0xCBF43926u);
    /* Incremental == one-shot. */
    {
        uint16_t a = unc_crc16_xmodem(0, s, 4);
        a = unc_crc16_xmodem(a, s + 4, 5);
        CHECK(a == 0x31C3);
    }
}

static void test_sniff_unknown(void)
{
    const uint8_t garbage[600] = { 0x55, 0xAA, 0x00 };
    MemIO m;
    UncIO io;
    test_make_memio(&io, &m, garbage, sizeof garbage);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
    /* Empty input must not crash. */
    test_make_memio(&io, &m, garbage, 0);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
}

static void test_progress_abort(void)
{
    UncProgressState ps;
    memset(&ps, 0, sizeof ps);
    ps.total = 100000;
    CHECK(unc_progress_add(&ps, 4096) == UNC_OK);  /* no prog: never aborts */
    CHECK(unc_progress_add(&ps, 8192) == UNC_OK);
    CHECK(ps.done == 4096 + 8192);
}

static void test_strerror(void)
{
    CHECK(strcmp(unc_strerror(UNC_OK), "ok") == 0);
    CHECK(unc_strerror(UNC_ERR_CRC) != NULL);
    CHECK(unc_strerror(-999) != NULL);
}

/* Per-milestone test entry points (defined in unit_fmt_*.c include'd
 * below as they land). */
void run_format_tests(void);

int main(void)
{
    test_be_readers();
    test_crc();
    test_sniff_unknown();
    test_progress_abort();
    test_strerror();
    run_format_tests();

    if (failures) {
        fprintf(stderr, "%d/%d checks FAILED\n", failures, checks);
        return 1;
    }
    printf("all %d checks passed\n", checks);
    return 0;
}

/* Format-specific unit tests are appended per milestone: */
#include "unit_formats.c"
