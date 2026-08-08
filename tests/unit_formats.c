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

/* ------------------------------------------------------------------ */
/* M3: bit reader, serialized Huffman trees, PackIt                   */
/* ------------------------------------------------------------------ */

static void test_bitin(void)
{
    /* 0xB6 0x01 = bits 1,0,1,1,0,1,1,0, 0,0,0,0,0,0,0,1 (MSB first) */
    static const uint8_t bytes[2] = { 0xB6, 0x01 };
    MemIO m;
    UncIO io;
    uint8_t storage[8];
    UncBufIn in;
    UncBitIn bi;

    test_make_memio(&io, &m, bytes, 2);
    unc_bufin_init(&in, &io, NULL, storage, sizeof storage);
    unc_bitin_init(&bi, &in);
    CHECK(unc_bitin_bit(&bi) == 1);
    CHECK(unc_bitin_bits(&bi, 3) == 3);        /* 011 */
    CHECK(unc_bitin_bits(&bi, 4) == 6);        /* 0110 */
    CHECK(unc_bitin_bits(&bi, 8) == 1);
    CHECK(unc_bitin_bit(&bi) == -1);           /* EOF */
    CHECK(bi.err == UNC_ERR_TRUNCATED);
}

static void test_huffman_tree(void)
{
    /* Serialized tree (XADStuffItHuffmanHandle parseTree order):
     *   0                       internal root
     *     1 'A'                 leaf on the 0-branch
     *     0                     internal on the 1-branch
     *       1 'B'  1 'C'        leaves
     * Codes: A=0, B=10, C=11.
     * Then payload bits: 0 10 11 -> "ABC". */
    uint8_t buf[8];
    MemIO m;
    UncIO io;
    uint8_t storage[8];
    UncBufIn in;
    UncBitIn bi;
    UncHuff h;
    uint32_t acc = 0;
    int nb = 0, i;
    uint8_t bits[] = { 0, 1, 0,1,0,0,0,0,0,1, 0, 1, 0,1,0,0,0,0,1,0,
                       1, 0,1,0,0,0,0,1,1,
                       0, 1,0, 1,1 };
    uint32_t len = 0;

    for (i = 0; i < (int)(sizeof bits); i++) {
        acc = (acc << 1) | bits[i];
        if (++nb == 8) { buf[len++] = (uint8_t)acc; acc = 0; nb = 0; }
    }
    if (nb) buf[len++] = (uint8_t)(acc << (8 - nb));

    test_make_memio(&io, &m, buf, len);
    unc_bufin_init(&in, &io, NULL, storage, sizeof storage);
    unc_bitin_init(&bi, &in);
    CHECK(unc_huff_read_tree(&h, &bi) == UNC_OK);
    CHECK(unc_huff_decode(&h, &bi) == 'A');
    CHECK(unc_huff_decode(&h, &bi) == 'B');
    CHECK(unc_huff_decode(&h, &bi) == 'C');

    /* Degenerate tree: root is a single leaf. Decoding then consumes
     * zero bits per symbol (PackIt one-symbol files rely on this). */
    buf[0] = 0xA1; buf[1] = 0x80;   /* 1 01000011 -> leaf 'C' + pad */
    test_make_memio(&io, &m, buf, 2);
    unc_bufin_init(&in, &io, NULL, storage, sizeof storage);
    unc_bitin_init(&bi, &in);
    CHECK(unc_huff_read_tree(&h, &bi) == UNC_OK);
    CHECK(unc_huff_decode(&h, &bi) == 'C');
    CHECK(unc_huff_decode(&h, &bi) == 'C');

    /* Truncated serialization -> clean error. */
    buf[0] = 0x00;                  /* internal node, then EOF */
    test_make_memio(&io, &m, buf, 1);
    unc_bufin_init(&in, &io, NULL, storage, sizeof storage);
    unc_bitin_init(&bi, &in);
    CHECK(unc_huff_read_tree(&h, &bi) != UNC_OK);
}

/* Build a stored (PMag) PackIt archive with one entry. */
static uint32_t pit_synth(uint8_t *out, const char *name,
                          const char *data, uint32_t dlen,
                          const char *rsrc, uint32_t rlen)
{
    uint8_t *h = out + 4;
    uint32_t n = (uint32_t)strlen(name);
    uint16_t crc;

    memcpy(out, "PMag", 4);
    memset(h, 0, 94);
    h[0] = (uint8_t)n;
    memcpy(h + 1, name, n);
    memcpy(h + 64, "TEXTttxt", 8);                /* type + creator */
    put32(h + 76, dlen);
    put32(h + 80, rlen);
    crc = unc_crc16_xmodem(0, h, 92);
    h[92] = (uint8_t)(crc >> 8); h[93] = (uint8_t)crc;
    memcpy(out + 98, data, dlen);
    memcpy(out + 98 + dlen, rsrc, rlen);
    crc = unc_crc16_xmodem(0, out + 98, (int32_t)(dlen + rlen));
    out[98 + dlen + rlen] = (uint8_t)(crc >> 8);
    out[99 + dlen + rlen] = (uint8_t)crc;
    memcpy(out + 100 + dlen + rlen, "PEnd", 4);
    return 104 + dlen + rlen;
}

static void test_packit(void)
{
    uint8_t arc[512];
    uint32_t len = pit_synth(arc, "pit test", "data-fork!", 10, "RSRC", 4);
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_PACKIT);

    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_PACKIT, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.info[0].name_len == 8);
    CHECK(memcmp(cap.info[0].name, "pit test", 8) == 0);
    CHECK(cap.info[0].type == 0x54455854u);     /* 'TEXT' */
    CHECK(cap.dlen[0] == 10 && memcmp(cap.data[0], "data-fork!", 10) == 0);
    CHECK(cap.rlen[0] == 4 && memcmp(cap.rsrc[0], "RSRC", 4) == 0);

    /* Flip a payload bit -> per-entry CRC error, archive still OK. */
    arc[100] ^= 0x01;
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_PACKIT, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_CRC);
    arc[100] ^= 0x01;

    /* Corrupt header CRC -> archive-level corrupt error. */
    arc[10] ^= 0xFF;
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_PACKIT, &io, &sk, &al, NULL, NULL)
          == UNC_ERR_CORRUPT);
    arc[10] ^= 0xFF;

    /* Truncated mid-fork -> clean stop. */
    test_make_memio(&io, &m, arc, 105);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_PACKIT, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_TRUNCATED);
}

/* ------------------------------------------------------------------ */
/* M4: canonical Huffman + Compact Pro                                */
/* ------------------------------------------------------------------ */

static void test_canon(void)
{
    /* Lengths: A=1, B=2, C=3, D=3 -> codes 0, 10, 110, 111. */
    uint8_t lens[4] = { 1, 2, 3, 3 };
    UncCanon cn;
    uint8_t buf[4];
    MemIO m;
    UncIO io;
    uint8_t storage[8];
    UncBufIn in;
    UncBitIn bi;

    CHECK(unc_canon_build(&cn, lens, 4) == UNC_OK);
    /* Bits: 0 10 110 111 -> 0101 1011 1... = 0x5B 0x80 */
    buf[0] = 0x5B; buf[1] = 0x80;
    test_make_memio(&io, &m, buf, 2);
    unc_bufin_init(&in, &io, NULL, storage, sizeof storage);
    unc_bitin_init(&bi, &in);
    CHECK(unc_canon_decode(&cn, &bi) == 0);
    CHECK(unc_canon_decode(&cn, &bi) == 1);
    CHECK(unc_canon_decode(&cn, &bi) == 2);
    CHECK(unc_canon_decode(&cn, &bi) == 3);

    /* Incomplete code (Compact Pro allows it): A=1, B=2; '11' invalid. */
    lens[0] = 1; lens[1] = 2; lens[2] = 0; lens[3] = 0;
    CHECK(unc_canon_build(&cn, lens, 4) == UNC_OK);
    buf[0] = 0xC0;   /* bits 11... */
    test_make_memio(&io, &m, buf, 1);
    unc_bufin_init(&in, &io, NULL, storage, sizeof storage);
    unc_bitin_init(&bi, &in);
    CHECK(unc_canon_decode(&cn, &bi) == -1);

    /* Over-subscribed code -> rejected at build time. */
    lens[0] = 1; lens[1] = 1; lens[2] = 1;
    CHECK(unc_canon_build(&cn, lens, 3) == UNC_ERR_CORRUPT);
}

/* Build a one-entry RLE-only Compact Pro archive around `comp`. */
static uint32_t cpt_synth(uint8_t *out, const uint8_t *comp, uint32_t clen,
                          const uint8_t *plain, uint32_t plen)
{
    uint32_t off = 8 + clen, crc;
    uint8_t *ix = out + off;
    uint8_t *e;

    out[0] = 1; out[1] = 1; out[2] = out[3] = 0;
    put32(out + 4, off);
    memcpy(out + 8, comp, clen);

    /* index: u32 crc, u16 nentries, u8 commentlen, one file entry */
    ix[4] = 0; ix[5] = 1;          /* nentries = 1 */
    ix[6] = 0;                     /* no comment */
    e = ix + 7;
    e[0] = 4; memcpy(e + 1, "test", 4);
    memset(e + 5, 0, 45);
    e[5] = 1;                      /* volume */
    put32(e + 6, 8);               /* fileoffs */
    memcpy(e + 10, "TEXTttxt", 8); /* type + creator */
    crc = unc_crc32(0xFFFFFFFFu, plain, (int32_t)plen);
    put32(e + 28, crc);            /* fileCRC (rsrc empty + data) */
    /* flags 0 (@32), rsrclen 0 (@34), datalen (@38), rcomp 0, dcomp */
    put32(e + 38, plen);
    put32(e + 46, clen);
    crc = unc_crc32(0xFFFFFFFFu, ix + 4, 3 + 50);
    put32(ix, crc);                /* index CRC */
    return off + 7 + 50;
}

static void test_cpt(void)
{
    /* RLE stream exercising the escape corners:
     *   A B <81 82 05>=4xB C <81 82 00>=lit 81 82 <81>D=lit 81 D */
    static const uint8_t comp[] = { 0x41, 0x42, 0x81, 0x82, 0x05, 0x43,
                                    0x81, 0x82, 0x00, 0x81, 0x44 };
    static const uint8_t plain[] = { 0x41, 0x42, 0x42, 0x42, 0x42, 0x42,
                                     0x43, 0x81, 0x82, 0x81, 0x44 };
    uint8_t arc[256];
    uint32_t len = cpt_synth(arc, comp, sizeof comp, plain, sizeof plain);
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_COMPACTPRO);

    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_COMPACTPRO, &io, &sk, &al, NULL, NULL)
          == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.info[0].name_len == 4 && memcmp(cap.info[0].name, "test", 4) == 0);
    CHECK(cap.info[0].type == 0x54455854u);
    CHECK(cap.dlen[0] == sizeof plain);
    CHECK(memcmp(cap.data[0], plain, sizeof plain) == 0);
    CHECK(cap.rlen[0] == 0);

    /* Flip a payload byte -> per-entry CRC error, archive still walks. */
    arc[9] ^= 0x01;
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_COMPACTPRO, &io, &sk, &al, NULL, NULL)
          == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_CRC);
    arc[9] ^= 0x01;

    /* Payload corruption must also de-recognize the file? No: the
     * index CRC does not cover file data, so sniff still matches. But
     * an index bit flip must fail the probe. */
    arc[len - 3] ^= 0xFF;
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
    arc[len - 3] ^= 0xFF;

    /* Truncated inside the file data -> engine must not produce a
     * silently-OK entry. */
    test_make_memio(&io, &m, arc, 12);   /* cut inside file data */
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_COMPACTPRO, &io, &sk, &al, NULL, NULL)
          != UNC_OK || cap.count == 0 || cap.status[0] != UNC_OK);
}

/* ------------------------------------------------------------------ */
/* M5: StuffIt classic container + RLE90. Method 1 is NOT absent from  */
/* the corpus, as this comment claimed until 2026-08-08: one resource  */
/* fork in derived-New_Python.sit, oracle-adjudicated since the        */
/* manifest builder learned to record per-entry oracle failures, plus  */
/* the edge cases in synth-sit-rle90.sit. These stay as the fast check.*/
/* ------------------------------------------------------------------ */

static uint16_t crc16arc_ref(const uint8_t *p, uint32_t n)
{
    /* Independent bitwise CRC-16/ARC for cross-checking the table. */
    uint16_t crc = 0;
    uint32_t i;
    int j;
    for (i = 0; i < n; i++) {
        crc ^= p[i];
        for (j = 0; j < 8; j++)
            crc = (crc & 1) ? (uint16_t)((crc >> 1) ^ 0xA001) : (uint16_t)(crc >> 1);
    }
    return crc;
}

/* One-entry StuffIt archive; data fork uses `method` with `comp`
 * given; rsrc fork empty (method 0). */
static uint32_t sit_synth(uint8_t *out, const char *name, int method,
                          const uint8_t *comp, uint32_t clen,
                          const uint8_t *plain, uint32_t plen)
{
    uint8_t *h = out + 22;
    uint32_t n = (uint32_t)strlen(name);
    uint32_t total = 22 + 112 + clen;
    uint16_t crc;

    memset(out, 0, total);
    memcpy(out, "SIT!", 4);
    out[5] = 1;                        /* numfiles */
    put32(out + 6, total);
    memcpy(out + 10, "rLau", 4);

    h[0] = 0;                          /* rsrc: method 0 */
    h[1] = (uint8_t)method;            /* data method */
    h[2] = (uint8_t)n;
    memcpy(h + 3, name, n);
    memcpy(h + 66, "TEXTttxt", 8);
    put32(h + 84, 0);                  /* rsrclen */
    put32(h + 88, plen);               /* datalen */
    put32(h + 92, 0);                  /* rsrc comp len */
    put32(h + 96, clen);               /* data comp len */
    /* fork CRCs: rsrc over nothing (0), data over decoded bytes */
    crc = unc_crc16_arc(0, plain, (int32_t)plen);
    h[102] = (uint8_t)(crc >> 8); h[103] = (uint8_t)crc;
    crc = unc_crc16_arc(0, h, 110);
    h[110] = (uint8_t)(crc >> 8); h[111] = (uint8_t)crc;
    memcpy(h + 112, comp, clen);
    return total;
}

static void test_sit(void)
{
    /* RLE90: "A"x6 -> 'A' 0x90 0x06; literal 0x90 -> 0x90 0x00. */
    static const uint8_t comp[] = { 'A', 0x90, 0x06, 'B', 'C', 0x90, 0x00, 'D' };
    static const uint8_t plain[] = { 'A','A','A','A','A','A','B','C',0x90,'D' };
    uint8_t arc[256];
    uint32_t len;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    /* Table vs independent bitwise CRC-16/ARC + check value. */
    CHECK(unc_crc16_arc(0, (const uint8_t *)"123456789", 9) == 0xBB3D);
    CHECK(crc16arc_ref((const uint8_t *)"123456789", 9) == 0xBB3D);

    len = sit_synth(arc, "rle test", 1, comp, sizeof comp,
                    plain, sizeof plain);
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_SIT);

    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SIT, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.info[0].method_data == 1);
    CHECK(cap.dlen[0] == sizeof plain);
    CHECK(memcmp(cap.data[0], plain, sizeof plain) == 0);

    /* Flip a data byte -> per-entry CRC error. */
    arc[22 + 112 + 3] ^= 0x01;
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SIT, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_CRC);
    arc[22 + 112 + 3] ^= 0x01;

    /* Corrupt entry header -> walk stops with a corrupt error. */
    arc[25] ^= 0xFF;
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SIT, &io, &sk, &al, NULL, NULL)
          == UNC_ERR_CORRUPT);
    arc[25] ^= 0xFF;

    /* Method 6, "fixed Huffman": one STORED segment followed by one
     * Huffman-coded segment, both expanding to the same PackBits stream
     * (three literals then a five-byte run). The bytes come from
     * tools/synth_sit6.py, whose code tree is generated from
     * reference/macutils/macunpack/sit.c; the corpus has a single
     * method-6 fork and it uses neither the stored branch nor a run this
     * short, so without this the fixtureless build tests neither. */
    {
        static const uint8_t m6[] = {
            /* stored: size -(6+4), then the PackBits bytes */
            0xFF, 0xFF, 0xFF, 0xF6, 0x02, 'A', 'B', 'C', 0xFC, 0x2A,
            /* Huffman: size 21, expanded 6, 6 codes, alphabet, bitstream */
            0x00, 0x00, 0x00, 0x15, 0x00, 0x00, 0x00, 0x06, 0x00, 0x06,
            0x02, 0x2A, 'A', 'B', 'C', 0xFC, 0x06, 0x3A, 0x12, 0x5F, 0xFE
        };
        static const uint8_t m6plain[] = {
            'A','B','C',0x2A,0x2A,0x2A,0x2A,0x2A,
            'A','B','C',0x2A,0x2A,0x2A,0x2A,0x2A
        };
        uint8_t six[256];
        uint32_t slen = sit_synth(six, "fixhuf", 6, m6, sizeof m6,
                                  m6plain, sizeof m6plain);
        test_make_memio(&io, &m, six, slen);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_SIT, &io, &sk, &al, NULL, NULL) == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
        CHECK(cap.info[0].method_data == 6);
        CHECK(cap.dlen[0] == sizeof m6plain);
        CHECK(memcmp(cap.data[0], m6plain, sizeof m6plain) == 0);

        /* A segment claiming more expanded bytes than any segment can
         * hold is a per-entry error, not a big allocation. */
        six[22 + 112 + 10 + 4] = 0x7F;      /* explen high byte */
        test_make_memio(&io, &m, six, slen);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_SIT, &io, &sk, &al, NULL, NULL) == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] != UNC_OK);
    }

    /* Encrypted method flag -> reported, not decoded. */
    {
        uint8_t enc[256];
        uint32_t elen = sit_synth(enc, "enc", 1, comp, sizeof comp,
                                  plain, sizeof plain);
        uint16_t crc;
        enc[22 + 1] |= 0x80;   /* data method: encrypted */
        crc = unc_crc16_arc(0, enc + 22, 110);
        enc[22 + 110] = (uint8_t)(crc >> 8);
        enc[22 + 111] = (uint8_t)crc;
        test_make_memio(&io, &m, enc, elen);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_SIT, &io, &sk, &al, NULL, NULL) == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_ENCRYPTED);
    }
}

/* ------------------------------------------------------------------ */
/* M8: gzip / tar / zip (deflate "stored block" built by hand from    */
/* RFC 1951/1952 and the PKWARE APPNOTE / POSIX ustar specs).         */
/* ------------------------------------------------------------------ */

static void put32le(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

static void test_gzip(void)
{
    /* gzip header + one stored deflate block + CRC/ISIZE trailer. */
    static const char *payload = "hello, gzip world";
    uint8_t arc[128];
    uint32_t n = (uint32_t)strlen(payload), len, crc;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    memset(arc, 0, sizeof arc);
    arc[0] = 0x1F; arc[1] = 0x8B; arc[2] = 8;   /* magic + deflate */
    /* flg=0, mtime=0, xfl=0, os=255 */
    arc[9] = 255;
    arc[10] = 0x01;                              /* final stored block */
    arc[11] = (uint8_t)n; arc[12] = (uint8_t)(n >> 8);
    arc[13] = (uint8_t)~n; arc[14] = (uint8_t)(~n >> 8);
    memcpy(arc + 15, payload, n);
    crc = unc_crc32(0xFFFFFFFFu, (const uint8_t *)payload, (int32_t)n)
          ^ 0xFFFFFFFFu;
    put32le(arc + 15 + n, crc);
    put32le(arc + 19 + n, n);
    len = 23 + n;

    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_GZIP);
    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_GZIP, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == n && memcmp(cap.data[0], payload, n) == 0);

    /* Flip a payload bit -> CRC error. */
    arc[16] ^= 1;
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_GZIP, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_CRC);
    arc[16] ^= 1;
}

static void test_tar(void)
{
    uint8_t arc[512 * 4];
    static const char *payload = "tar file contents\n";
    uint32_t n = (uint32_t)strlen(payload), sum = 0;
    int i;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    memset(arc, 0, sizeof arc);
    memcpy(arc, "dir1/file.txt", 13);
    memcpy(arc + 100, "0000644", 7);
    memcpy(arc + 108, "0000000", 7);
    memcpy(arc + 116, "0000000", 7);
    snprintf((char *)arc + 124, 12, "%011o", n);
    memcpy(arc + 136, "00000000000", 11);
    arc[156] = '0';
    memcpy(arc + 257, "ustar", 5);
    arc[263] = '0'; arc[264] = '0';
    memset(arc + 148, ' ', 8);
    for (i = 0; i < 512; i++) sum += arc[i];
    snprintf((char *)arc + 148, 8, "%06o", sum);
    arc[155] = ' ';
    memcpy(arc + 512, payload, n);
    /* two zero blocks already present (arc is zeroed) */

    test_make_memio(&io, &m, arc, sizeof arc);
    CHECK(unc_sniff(&io) == UNC_FORMAT_TAR);
    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_TAR, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.info[0].name_len == 13);
    CHECK(memcmp(cap.info[0].name, "dir1/file.txt", 13) == 0);
    CHECK(cap.dlen[0] == n && memcmp(cap.data[0], payload, n) == 0);

    /* Corrupt checksum -> no longer recognized / clean error. */
    arc[148] ^= 1;
    test_make_memio(&io, &m, arc, sizeof arc);
    CHECK(unc_sniff(&io) != UNC_FORMAT_TAR);
    arc[148] ^= 1;
}

static void test_zip(void)
{
    /* One stored entry: LFH + data + central dir + EOCD. */
    static const char *payload = "zip stored data";
    static const char *name = "f.txt";
    uint8_t arc[256];
    uint32_t n = (uint32_t)strlen(payload), nl = (uint32_t)strlen(name);
    uint32_t crc, lfh = 0, cd, eocd, len;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    memset(arc, 0, sizeof arc);
    crc = unc_crc32(0xFFFFFFFFu, (const uint8_t *)payload, (int32_t)n)
          ^ 0xFFFFFFFFu;

    /* local file header */
    memcpy(arc, "PK\x03\x04", 4);
    arc[4] = 20;
    put32le(arc + 14, crc);
    put32le(arc + 18, n);
    put32le(arc + 22, n);
    arc[26] = (uint8_t)nl;
    memcpy(arc + 30, name, nl);
    memcpy(arc + 30 + nl, payload, n);
    cd = 30 + nl + n;

    memcpy(arc + cd, "PK\x01\x02", 4);
    put32le(arc + cd + 16, crc);
    put32le(arc + cd + 20, n);
    put32le(arc + cd + 24, n);
    arc[cd + 28] = (uint8_t)nl;
    put32le(arc + cd + 42, lfh);
    memcpy(arc + cd + 46, name, nl);
    eocd = cd + 46 + nl;

    memcpy(arc + eocd, "PK\x05\x06", 4);
    arc[eocd + 8] = 1; arc[eocd + 10] = 1;       /* entry counts */
    put32le(arc + eocd + 12, eocd - cd);         /* cd size */
    put32le(arc + eocd + 16, cd);                /* cd offset */
    len = eocd + 22;

    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_ZIP);
    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_ZIP, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.info[0].name_len == nl);
    CHECK(cap.dlen[0] == n && memcmp(cap.data[0], payload, n) == 0);

    /* Unknown method -> clean per-entry unsupported. */
    arc[cd + 10] = 99;
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_ZIP, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_UNSUPPORTED);
    arc[cd + 10] = 0;
}

/* DiskCopy 4.2 is DETECT-ONLY: unc_sniff must name it, and extraction must
 * refuse cleanly rather than pretend. The probe is deliberately strict (the
 * magic word is only 16 bits), so also check that each guard rejects. */
static void test_diskcopy(void)
{
    uint8_t h[128];
    UncIO io;
    MemIO m;
    int i;

    /* Minimal valid 800K GCR header: name, dataSize 819200, tags 19200. */
    for (i = 0; i < (int)sizeof h; i++) h[i] = 0;
    h[0] = 4;                                    /* Pascal name length */
    h[1] = 'D'; h[2] = 'i'; h[3] = 's'; h[4] = 'k';
    h[0x40] = 0x00; h[0x41] = 0x0C; h[0x42] = 0x80; h[0x43] = 0x00;  /* 819200 */
    h[0x44] = 0x00; h[0x45] = 0x00; h[0x46] = 0x4B; h[0x47] = 0x00;  /*  19200 */
    h[0x50] = 0x01;                              /* GCR CLV dsdd (800K) */
    h[0x51] = 0x22;                              /* format byte, not checked */
    h[0x52] = 0x01; h[0x53] = 0x00;              /* magic "private word" */

    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKCOPY);

    /* A tagless GCR image is equally valid. */
    h[0x44] = h[0x45] = h[0x46] = h[0x47] = 0;
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKCOPY);

    /* 1440K MFM, which can never carry tags. */
    h[0x40] = 0x00; h[0x41] = 0x16; h[0x42] = 0x80; h[0x43] = 0x00;  /* 1474560 */
    h[0x50] = 0x03;
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKCOPY);
    h[0x47] = 0x0C;                              /* ...so any tag size is wrong */
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKCOPY);
    h[0x47] = 0x00;

    /* Encoding must agree with the declared data size. */
    h[0x50] = 0x01;                              /* says 800K, size says 1440K */
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKCOPY);
    h[0x50] = 0x03;

    /* Unknown encoding, over-long Pascal name, wrong magic: all rejected. */
    h[0x50] = 0x07;
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKCOPY);
    h[0x50] = 0x03;

    h[0] = 64;
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKCOPY);
    h[0] = 4;

    h[0x53] = 0x01;
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) != UNC_FORMAT_DISKCOPY);
    h[0x53] = 0x00;

    /* Detect-only: it is named, but extracting it is refused cleanly. */
    {
        UncAlloc al;
        UncSink sk;
        CapSink cap;
        test_make_memio(&io, &m, h, sizeof h);
        test_make_alloc(&al);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_DISKCOPY, &io, &sk, &al, NULL, NULL)
              == UNC_ERR_UNSUPPORTED);
        CHECK(cap.count == 0);
    }
}

/* ------------------------------------------------------------------ */
/* StuffIt segments (multi-part sets)                                 */
/* ------------------------------------------------------------------ */

/* One part: 100-byte header + payload slice. See src/fmt_sitseg.c for
 * the layout and its source. */
static void seg_head(uint8_t *h, int part, const char *name,
                     uint32_t rsrclen, uint32_t datalen, uint32_t mtime)
{
    size_t nl = strlen(name);
    memset(h, 0, UNC_SEG_HEAD);
    h[0] = 0xB0; h[1] = 0x56; h[2] = 0x00; h[3] = (uint8_t)part;
    h[4] = (uint8_t)nl;
    memcpy(h + 5, name, nl);
    memcpy(h + 68, "SIT!SIT!", 8);                 /* type + creator */
    h[82] = (uint8_t)(mtime >> 24); h[83] = (uint8_t)(mtime >> 16);
    h[84] = (uint8_t)(mtime >> 8);  h[85] = (uint8_t)mtime;
    h[86] = (uint8_t)(rsrclen >> 24); h[87] = (uint8_t)(rsrclen >> 16);
    h[88] = (uint8_t)(rsrclen >> 8);  h[89] = (uint8_t)rsrclen;
    h[90] = (uint8_t)(datalen >> 24); h[91] = (uint8_t)(datalen >> 16);
    h[92] = (uint8_t)(datalen >> 8);  h[93] = (uint8_t)datalen;
}

/* A volume source over in-memory parts, with a hole the test can open
 * and close to check the missing-part path. */
typedef struct {
    const uint8_t *part[5];
    uint32_t       len[5];
    int            nparts;
    int            missing;      /* part number to refuse, 0 = none */
    MemIO          m;
    int            opens;
} SegParts;

static int segsrc_need(void *ctx, const UncSegmentDesc *desc, int part,
                       UncIO *io)
{
    SegParts *p = (SegParts *)ctx;
    (void)desc;
    if (part < 1 || part > p->nparts || part == p->missing)
        return UNC_ERR_SEGMENTED;
    p->opens++;
    test_make_memio(io, &p->m, p->part[part - 1], p->len[part - 1]);
    return UNC_OK;
}

static void test_sitseg(void)
{
    uint8_t whole[UNC_SEG_HEAD + 300];
    uint8_t p1[UNC_SEG_HEAD + 120], p2[UNC_SEG_HEAD + 100],
            p3[UNC_SEG_HEAD + 80];
    uint8_t payload[300];
    UncSegmentDesc desc;
    UncIO io;
    MemIO m;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    int i;

    for (i = 0; i < 300; i++) payload[i] = (uint8_t)(i * 7 + 1);

    /* --- describe ------------------------------------------------- */
    seg_head(whole, 1, "Thing.sit", 100, 200, 0x11223344u);
    memcpy(whole + UNC_SEG_HEAD, payload, 300);
    test_make_memio(&io, &m, whole, sizeof whole);
    CHECK(unc_sniff(&io) == UNC_FORMAT_SITSEG);
    CHECK(unc_segment_describe(&io, &desc) == UNC_OK);
    CHECK(desc.part == 1);
    CHECK(desc.name_len == 9 && memcmp(desc.name, "Thing.sit", 9) == 0);
    CHECK(desc.rsrc_size == 100 && desc.data_size == 200);
    CHECK(desc.total == 300);
    CHECK(desc.type == 0x53495421u);      /* 'SIT!' */
    CHECK(desc.mod_date == 0x11223344u);

    /* --- match: content decides, never the name of the file ------- */
    {
        uint8_t other[UNC_SEG_HEAD];
        seg_head(other, 3, "Thing.sit", 100, 200, 0x11223344u);
        CHECK(unc_segment_match(&desc, other, UNC_SEG_HEAD) == 3);
        /* Same name, one different fingerprint byte: another set. */
        seg_head(other, 3, "Thing.sit", 100, 200, 0x11223345u);
        CHECK(unc_segment_match(&desc, other, UNC_SEG_HEAD) == 0);
        /* Same fingerprint, different name: another set. */
        seg_head(other, 3, "Other.sit", 100, 200, 0x11223344u);
        CHECK(unc_segment_match(&desc, other, UNC_SEG_HEAD) == 0);
        /* Too short to prove itself. */
        seg_head(other, 2, "Thing.sit", 100, 200, 0x11223344u);
        CHECK(unc_segment_match(&desc, other, UNC_SEG_HEAD - 1) == 0);
        /* Part 0 is not a part. */
        seg_head(other, 0, "Thing.sit", 100, 200, 0x11223344u);
        CHECK(unc_sitseg_probe(other, UNC_SEG_HEAD) == 0);
    }

    /* --- a set of one part needs no volume source ----------------- */
    test_make_memio(&io, &m, whole, sizeof whole);
    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SITSEG, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.rlen[0] == 100 && memcmp(cap.rsrc[0], payload, 100) == 0);
    CHECK(cap.dlen[0] == 200 && memcmp(cap.data[0], payload + 100, 200) == 0);

    /* --- three parts, joined through a volume source -------------- */
    seg_head(p1, 1, "Thing.sit", 100, 200, 0x11223344u);
    seg_head(p2, 2, "Thing.sit", 100, 200, 0x11223344u);
    seg_head(p3, 3, "Thing.sit", 100, 200, 0x11223344u);
    memcpy(p1 + UNC_SEG_HEAD, payload, 120);
    memcpy(p2 + UNC_SEG_HEAD, payload + 120, 100);
    memcpy(p3 + UNC_SEG_HEAD, payload + 220, 80);
    {
        SegParts sp;
        UncVolumeSource vs;
        void *scratch;
        uint32_t opens = 0, back = 0;

        memset(&sp, 0, sizeof sp);
        sp.part[0] = p1; sp.len[0] = sizeof p1;
        sp.part[1] = p2; sp.len[1] = sizeof p2;
        sp.part[2] = p3; sp.len[2] = sizeof p3;
        sp.nparts = 3;
        vs.ctx = &sp; vs.need = segsrc_need; vs.release = NULL;

        scratch = malloc(unc_segment_scratch_size());
        CHECK(scratch != NULL);

        /* The fork boundary is inside part 1 and the parts are uneven,
         * so this fails on any off-by-one at a part edge. */
        cap_make(&sk, &cap);
        CHECK(unc_extract_segments(&desc, &vs, scratch, &sk, &al, NULL, NULL)
              == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
        CHECK(cap.rlen[0] == 100 && memcmp(cap.rsrc[0], payload, 100) == 0);
        CHECK(cap.dlen[0] == 200 && memcmp(cap.data[0], payload + 100, 200) == 0);
        CHECK(sp.opens == 3);
        unc_segment_stats(scratch, &opens, &back);
        CHECK(opens == 3);
        CHECK(back == 0);      /* the join is read strictly forward */

        /* A part the host cannot produce: the archive says so, and the
         * entry is reported truncated rather than silently short. */
        sp.missing = 2;
        sp.opens = 0;
        cap_make(&sk, &cap);
        CHECK(unc_extract_segments(&desc, &vs, scratch, &sk, &al, NULL, NULL)
              == UNC_ERR_SEGMENTED);
        CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_TRUNCATED);
        CHECK(cap.rlen[0] == 100);          /* what part 1 held is kept */
        CHECK(cap.dlen[0] == 20);
        free(scratch);
    }

    /* --- a middle part on its own cannot be extracted alone ------- */
    test_make_memio(&io, &m, p2, sizeof p2);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SITSEG, &io, &sk, &al, NULL, NULL)
          == UNC_ERR_SEGMENTED);
    CHECK(cap.count == 0);
}

void run_format_tests(void)
{
    test_macbinary();
    test_applesingle();
    test_bitin();
    test_huffman_tree();
    test_packit();
    test_canon();
    test_cpt();
    test_sit();
    test_gzip();
    test_tar();
    test_zip();
    test_diskcopy();
    test_sitseg();
}
