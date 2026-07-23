/*
 * unit_formats.c — per-format unit tests, included by unit_main.c.
 * Grows milestone by milestone.
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */

/* Helpers from unit_main.c */
void test_make_memio(UncIO *io, MemIO *m, const uint8_t *data, uint32_t size);
void test_make_alloc(UncAlloc *al);

/* ------------------------------------------------------------------ */
/* Capture sink: collects both forks + metadata into fixed buffers.   */
/* ------------------------------------------------------------------ */

typedef struct {
    UncEntryInfo info[8];
    uint8_t data[8][4096];
    uint8_t rsrc[8][4096];
    uint32_t dlen[8], rlen[8];
    int status[8];
    int count;
} CapSink;

static int cap_begin(void *ctx, const UncEntryInfo *info)
{
    CapSink *s = (CapSink *)ctx;
    if (s->count >= 8) return -1;
    s->info[s->count] = *info;
    s->dlen[s->count] = s->rlen[s->count] = 0;
    return 0;
}

static int cap_write(void *ctx, UncFork fork, const void *buf, int32_t len)
{
    CapSink *s = (CapSink *)ctx;
    uint8_t *dst = fork == UNC_FORK_DATA ? s->data[s->count] : s->rsrc[s->count];
    uint32_t *dl = fork == UNC_FORK_DATA ? &s->dlen[s->count] : &s->rlen[s->count];
    if (*dl + (uint32_t)len > 4096) return -1;
    memcpy(dst + *dl, buf, (size_t)len);
    *dl += (uint32_t)len;
    return 0;
}

static int cap_end(void *ctx, int status)
{
    CapSink *s = (CapSink *)ctx;
    s->status[s->count] = status;
    s->count++;
    return 0;
}

static void cap_make(UncSink *sk, CapSink *s)
{
    memset(s, 0, sizeof *s);
    sk->ctx = s;
    sk->begin_entry = cap_begin;
    sk->write = cap_write;
    sk->end_entry = cap_end;
}

/* ------------------------------------------------------------------ */
/* M1: MacBinary                                                      */
/* ------------------------------------------------------------------ */

/* Build a minimal valid MacBinary II file in buf; returns total len. */
static uint32_t mb_synth(uint8_t *buf, const char *name,
                         const char *data, uint32_t dlen,
                         const char *rsrc, uint32_t rlen)
{
    uint32_t nl = (uint32_t)strlen(name), off = 128, i;
    uint16_t crc;
    memset(buf, 0, 128);
    buf[1] = (uint8_t)nl;
    memcpy(buf + 2, name, nl);
    memcpy(buf + 65, "TEXT", 4);
    memcpy(buf + 69, "ttxt", 4);
    buf[83] = (uint8_t)(dlen >> 24); buf[84] = (uint8_t)(dlen >> 16);
    buf[85] = (uint8_t)(dlen >> 8);  buf[86] = (uint8_t)dlen;
    buf[87] = (uint8_t)(rlen >> 24); buf[88] = (uint8_t)(rlen >> 16);
    buf[89] = (uint8_t)(rlen >> 8);  buf[90] = (uint8_t)rlen;
    /* dates: arbitrary nonzero */
    buf[91] = 0xA0; buf[95] = 0xA1;
    buf[122] = 129; buf[123] = 129;  /* MacBinary II versions */
    crc = unc_crc16_xmodem(0, buf, 124);
    buf[124] = (uint8_t)(crc >> 8); buf[125] = (uint8_t)crc;
    memcpy(buf + off, data, dlen);
    off += dlen;
    for (i = dlen; i % 128; i++) buf[off++] = 0;
    memcpy(buf + off, rsrc, rlen);
    off += rlen;
    for (i = rlen; i % 128; i++) buf[off++] = 0;
    return off;
}

static void test_macbinary(void)
{
    uint8_t arc[1024];
    uint32_t len = mb_synth(arc, "test.txt", "hello, fork", 11, "RSRC", 4);
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_MACBINARY);

    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_MACBINARY, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1);
    CHECK(cap.status[0] == UNC_OK);
    CHECK(cap.info[0].name_len == 8);
    CHECK(memcmp(cap.info[0].name, "test.txt", 8) == 0);
    CHECK(cap.info[0].type == 0x54455854u);    /* 'TEXT' */
    CHECK(cap.info[0].creator == 0x74747874u); /* 'ttxt' */
    CHECK(cap.dlen[0] == 11 && memcmp(cap.data[0], "hello, fork", 11) == 0);
    CHECK(cap.rlen[0] == 4 && memcmp(cap.rsrc[0], "RSRC", 4) == 0);

    /* Truncated: cut mid data fork -> clean per-entry error. */
    test_make_memio(&io, &m, arc, 130);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_MACBINARY, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_TRUNCATED);

    /* Corrupt CRC -> not recognized. */
    arc[124] ^= 0xFF;
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
    arc[124] ^= 0xFF;
}

/* ------------------------------------------------------------------ */
/* M1: AppleSingle/AppleDouble                                        */
/* ------------------------------------------------------------------ */

static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
}

static void test_applesingle(void)
{
    /* AppleSingle with name, Finder info, data + rsrc forks. */
    uint8_t arc[512];
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    uint32_t off = 26 + 4 * 12;

    memset(arc, 0, sizeof arc);
    put32(arc, 0x00051600u);
    put32(arc + 4, 0x00020000u);
    arc[24] = 0; arc[25] = 4;
    /* entry 3: name */
    put32(arc + 26, 3); put32(arc + 30, off); put32(arc + 34, 5);
    memcpy(arc + off, "hello", 5); off += 5;
    /* entry 9: finder info */
    put32(arc + 38, 9); put32(arc + 42, off); put32(arc + 46, 32);
    memcpy(arc + off, "APPLaust", 8);
    arc[off + 8] = 0x01; arc[off + 9] = 0x00;
    off += 32;
    /* entry 1: data fork */
    put32(arc + 50, 1); put32(arc + 54, off); put32(arc + 58, 9);
    memcpy(arc + off, "DATA-FORK", 9); off += 9;
    /* entry 2: rsrc fork */
    put32(arc + 62, 2); put32(arc + 66, off); put32(arc + 70, 6);
    memcpy(arc + off, "RSRC!!", 6); off += 6;

    test_make_memio(&io, &m, arc, off);
    CHECK(unc_sniff(&io) == UNC_FORMAT_APPLESINGLE);

    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_APPLESINGLE, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.info[0].name_len == 5 && memcmp(cap.info[0].name, "hello", 5) == 0);
    CHECK(cap.info[0].type == 0x4150504Cu);     /* 'APPL' */
    CHECK(cap.info[0].creator == 0x61757374u);  /* 'aust' */
    CHECK(cap.info[0].finder_flags == 0x0100);
    CHECK(cap.dlen[0] == 9 && memcmp(cap.data[0], "DATA-FORK", 9) == 0);
    CHECK(cap.rlen[0] == 6 && memcmp(cap.rsrc[0], "RSRC!!", 6) == 0);
}

void run_format_tests(void)
{
    test_macbinary();
    test_applesingle();
}
