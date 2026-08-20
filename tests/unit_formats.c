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

/* LZH/LHA is DETECT-ONLY: unc_sniff must name it so a UI can say what the
 * file is, and extraction must refuse cleanly. The corpus holds one real
 * LZH archive (aminet-lha_68k.lha, an Amiga -lh5- set — Macintosh software
 * was essentially never distributed this way, which is why the format is
 * detect-only at all), and run_diff.py grades that one on its NAME. This
 * covers what one file cannot: every method byte the reference accepts,
 * and every guard that must reject.
 *
 * Source: reference/XADMaster/XADLZHParser.m +recognizeFileWithHandle:,
 * which matches bytes[2..6] as "-lh?-" with ? in 0-7 or 'd', and "-lz?-"
 * with ? in 0, 4 or 5. Bytes 0 and 1 are the header size and its checksum
 * and are not part of the recognition. */
static void test_lzh(void)
{
    uint8_t h[32];
    UncIO io;
    MemIO m;
    int i;
    static const char *ok_lh = "01234567d";
    static const char *ok_lz = "045";
    static const char *no_lh = "89abcex-";
    static const char *no_lz = "1236789";

    for (i = 0; i < (int)sizeof h; i++) h[i] = 0;
    h[0] = 0x20;                       /* header size, not checked */
    h[1] = 0x00;                       /* header checksum, not checked */
    h[2] = '-'; h[6] = '-';

    h[3] = 'l'; h[4] = 'h';
    for (i = 0; ok_lh[i]; i++) {
        h[5] = (uint8_t)ok_lh[i];
        test_make_memio(&io, &m, h, sizeof h);
        CHECK(unc_sniff(&io) == UNC_FORMAT_LZH);
    }
    for (i = 0; no_lh[i]; i++) {
        h[5] = (uint8_t)no_lh[i];
        test_make_memio(&io, &m, h, sizeof h);
        CHECK(unc_sniff(&io) != UNC_FORMAT_LZH);
    }

    h[4] = 'z';                        /* LArc */
    for (i = 0; ok_lz[i]; i++) {
        h[5] = (uint8_t)ok_lz[i];
        test_make_memio(&io, &m, h, sizeof h);
        CHECK(unc_sniff(&io) == UNC_FORMAT_LZH);
    }
    for (i = 0; no_lz[i]; i++) {
        h[5] = (uint8_t)no_lz[i];
        test_make_memio(&io, &m, h, sizeof h);
        CHECK(unc_sniff(&io) != UNC_FORMAT_LZH);
    }

    /* Both dashes are required, and so is the length. */
    h[4] = 'h'; h[5] = '5';
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) == UNC_FORMAT_LZH);
    h[2] = '+';
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) != UNC_FORMAT_LZH);
    h[2] = '-';
    h[6] = '+';
    test_make_memio(&io, &m, h, sizeof h);
    CHECK(unc_sniff(&io) != UNC_FORMAT_LZH);
    h[6] = '-';
    test_make_memio(&io, &m, h, 6);            /* one byte short of a decision */
    CHECK(unc_sniff(&io) != UNC_FORMAT_LZH);

    /* Detect-only: named, and refused without pretending. */
    {
        UncAlloc al;
        UncSink sk;
        CapSink cap;
        test_make_memio(&io, &m, h, sizeof h);
        test_make_alloc(&al);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_LZH, &io, &sk, &al, NULL, NULL)
              == UNC_ERR_UNSUPPORTED);
        CHECK(cap.count == 0);
    }
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
        memset(&vs, 0, sizeof vs);   /* optional members are NULL ones */
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

/* ------------------------------------------------------------------ */
/* M11: spanned ("split") zip                                         */
/*                                                                    */
/* Everything here is hand-built, because the properties that matter   */
/* are ones no generated fixture reaches: an end-of-central-directory  */
/* record pushed away from the end of the file by a comment (and, at   */
/* one specific length, straddling the backwards scanner's window      */
/* boundary), and a set whose declared part count disagrees with what  */
/* the host assembled. tools/run_segments.py covers real `zip -s`      */
/* output against the oracle.                                         */
/* ------------------------------------------------------------------ */

static void put16le(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v & 0xFF);
    p[1] = (uint8_t)((v >> 8) & 0xFF);
}

/* One stored entry called "f", its data at `dataoff` within part
 * `startdisk`, plus a central directory and an EOCD claiming `ndisks`
 * disks and a comment of `commentlen` bytes. Returns the total length.
 * `cdat` receives where the central directory was put. */
static uint32_t zs_build_tail(uint8_t *buf, uint32_t crc, uint32_t n,
                              uint32_t startdisk, uint32_t dataoff,
                              uint32_t ndisks, uint32_t cddisk,
                              uint32_t cdrel, uint32_t commentlen)
{
    uint32_t cd = 0, eocd;

    memcpy(buf + cd, "PK\x01\x02", 4);
    put32le(buf + cd + 16, crc);
    put32le(buf + cd + 20, n);
    put32le(buf + cd + 24, n);
    buf[cd + 28] = 1;                            /* name length */
    put16le(buf + cd + 34, startdisk);           /* "disk number start" */
    put32le(buf + cd + 42, dataoff);             /* relative to that disk */
    buf[cd + 46] = 'f';
    eocd = cd + 47;

    memcpy(buf + eocd, "PK\x05\x06", 4);
    put16le(buf + eocd + 4, ndisks - 1);         /* "number of this disk" */
    put16le(buf + eocd + 6, cddisk);
    buf[eocd + 8] = 1; buf[eocd + 10] = 1;       /* entry counts */
    put32le(buf + eocd + 12, eocd - cd);         /* cd size */
    put32le(buf + eocd + 16, cdrel);             /* cd offset in cddisk */
    put16le(buf + eocd + 20, commentlen);
    return eocd + 22 + commentlen;
}

static void test_zipseg(void)
{
    static const char *payload = "spanned zip payload, split across parts";
    uint8_t p1[64], p2[1600], solo[1700];
    uint32_t n = (uint32_t)strlen(payload);
    uint32_t crc, p1len, p2len;
    UncSegmentDesc desc;
    UncIO io;
    MemIO m;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    uint32_t comment;

    crc = unc_crc32(0xFFFFFFFFu, (const uint8_t *)payload, (int32_t)n)
          ^ 0xFFFFFFFFu;
    test_make_alloc(&al);

    /* --- part 1: marker, local header, and the first 10 payload bytes.
     * The entry's data deliberately runs off the end of the part. --- */
    memset(p1, 0, sizeof p1);
    memcpy(p1, "PK\x07\x08", 4);                 /* what `zip -s` writes */
    memcpy(p1 + 4, "PK\x03\x04", 4);
    put32le(p1 + 4 + 14, crc);
    put32le(p1 + 4 + 18, n);
    put32le(p1 + 4 + 22, n);
    p1[4 + 26] = 1;                              /* name length */
    p1[4 + 30] = 'f';
    memcpy(p1 + 4 + 31, payload, 10);
    p1len = 4 + 31 + 10;

    /* --- part 2: the rest of the payload, then the directory ------- */
    memset(p2, 0, sizeof p2);
    memcpy(p2, payload + 10, n - 10);
    p2len = (n - 10) +
            zs_build_tail(p2 + (n - 10), crc, n, 0, 4, 2, 1, n - 10, 0);

    /* --- what each part says about itself -------------------------- */
    test_make_memio(&io, &m, p1, p1len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_ZIPSEG);   /* local header at 4 */
    CHECK(unc_segment_describe(&io, &desc) == UNC_ERR_FORMAT);  /* no EOCD */

    test_make_memio(&io, &m, p2, p2len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_ZIPSEG);
    CHECK(unc_segment_describe(&io, &desc) == UNC_OK);
    CHECK(desc.scheme == UNC_FORMAT_ZIPSEG);
    CHECK(desc.nparts == 2 && desc.part == 2);
    CHECK(desc.head_len == 0);                    /* the parts concatenate */
    CHECK(desc.total == UNC_SIZE_UNKNOWN);        /* measured, not declared */
    CHECK(desc.name_len == 0);                    /* the format stores none */

    /* A scheme that fingerprints nothing cannot answer this, and 0 here
     * means "cannot be asked" rather than "does not belong". */
    CHECK(unc_segment_match(&desc, p1, (int32_t)p1len) == 0);

    /* --- the last part alone is not the archive -------------------- */
    cap_make(&sk, &cap);
    test_make_memio(&io, &m, p2, p2len);
    CHECK(unc_extract_as(UNC_FORMAT_ZIPSEG, &io, &sk, &al, NULL, NULL)
          == UNC_ERR_SEGMENTED);
    CHECK(cap.count == 0);

    /* --- joined ---------------------------------------------------- */
    {
        SegParts sp;
        UncVolumeSource vs;
        void *scratch;
        uint32_t opens = 0, back = 0;

        memset(&sp, 0, sizeof sp);
        sp.part[0] = p1; sp.len[0] = p1len;
        sp.part[1] = p2; sp.len[1] = p2len;
        sp.nparts = 2;
        memset(&vs, 0, sizeof vs);   /* optional members are NULL ones */
        vs.ctx = &sp; vs.need = segsrc_need; vs.release = NULL;

        scratch = malloc(unc_segment_scratch_size());
        CHECK(scratch != NULL);

        cap_make(&sk, &cap);
        CHECK(unc_extract_segments(&desc, &vs, scratch, &sk, &al, NULL, NULL)
              == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
        CHECK(cap.dlen[0] == n && memcmp(cap.data[0], payload, n) == 0);
        /* The floor, and it is exact rather than a bound: part 2 for the
         * directory, part 1 for the entry's data, then part 2 again
         * because this entry deliberately spans the cut. One backward
         * crossing is what the layout costs and all it costs — a reader
         * that opened every part to measure it first reports 5 here
         * (DECISIONS.md 2026-08-09). */
        unc_segment_stats(scratch, &opens, &back);
        CHECK(opens == 3);
        CHECK(back == 1);

        /* A part the host cannot produce. The entry fails, and the
         * archive's verdict outranks it. */
        sp.missing = 1;
        cap_make(&sk, &cap);
        CHECK(unc_extract_segments(&desc, &vs, scratch, &sk, &al, NULL, NULL)
              == UNC_ERR_SEGMENTED);
        sp.missing = 0;

        /* The set assembled must be the set the archive describes. The
         * host ordered these by filename, so this is the only thing
         * standing between a wrong guess and a wrong extraction. Two
         * shapes of wrong, and they fail differently:
         *
         * a count that disagrees with the record — the real last part
         * is where it should be, but the set claims one more... */
        desc.nparts = 3;
        sp.nparts = 3;
        sp.part[2] = p2; sp.len[2] = p2len;
        cap_make(&sk, &cap);
        CHECK(unc_extract_segments(&desc, &vs, scratch, &sk, &al, NULL, NULL)
              == UNC_ERR_CORRUPT);
        CHECK(cap.count == 0);

        /* ...and a last part that is not one, which is caught earlier
         * still, when no directory is found where the format puts it. */
        sp.part[2] = p1; sp.len[2] = p1len;
        cap_make(&sk, &cap);
        CHECK(unc_extract_segments(&desc, &vs, scratch, &sk, &al, NULL, NULL)
              == UNC_ERR_FORMAT);
        CHECK(cap.count == 0);
        desc.nparts = 2;
        sp.nparts = 2;
        free(scratch);
    }

    /* --- a whole archive that merely LOOKS split ------------------- *
     * `zip -s` writes its marker even when the result fits in one file
     * (MEASURED). Such a file says "disk 0", needs no joining, and must
     * read as an ordinary zip rather than be refused as a fragment. */
    memset(solo, 0, sizeof solo);
    memcpy(solo, "PK\x07\x08", 4);
    memcpy(solo + 4, "PK\x03\x04", 4);
    put32le(solo + 4 + 14, crc);
    put32le(solo + 4 + 18, n);
    put32le(solo + 4 + 22, n);
    solo[4 + 26] = 1;
    solo[4 + 30] = 'f';
    memcpy(solo + 4 + 31, payload, n);
    {
        uint32_t cdat = 4 + 31 + n;
        uint32_t len = cdat + zs_build_tail(solo + cdat, crc, n, 0, 4,
                                            1, 0, cdat, 0);
        test_make_memio(&io, &m, solo, len);
        CHECK(unc_sniff(&io) == UNC_FORMAT_ZIP);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_ZIP, &io, &sk, &al, NULL, NULL)
              == UNC_OK);
        CHECK(cap.count == 1 && cap.dlen[0] == n);
        CHECK(memcmp(cap.data[0], payload, n) == 0);
    }

    /* --- the EOCD pushed away from the end by a comment ------------ *
     * The scanner walks backwards in 512-byte windows, so the lengths
     * that matter are the ones putting the signature 513, 514 and 515
     * bytes from the end: its four bytes then straddle a window edge
     * and a scanner that forgot to carry them would miss it entirely.
     * A whole spanned set would be needed to notice this any other way. */
    for (comment = 0; comment <= 1000; comment++) {
        uint32_t cdat = 0;
        uint32_t len;
        int interesting = (comment + 22 >= 511 && comment + 22 <= 517) ||
                          comment == 0 || comment == 1000;
        if (!interesting) continue;
        memset(p2, 0xAA, sizeof p2);   /* noise, not zeros, in the comment */
        len = cdat + zs_build_tail(p2 + cdat, crc, n, 0, 4, 4, 3, 0, comment);
        CHECK(len <= sizeof p2);
        test_make_memio(&io, &m, p2, len);
        CHECK(unc_sniff(&io) == UNC_FORMAT_ZIPSEG);
        CHECK(unc_segment_describe(&io, &desc) == UNC_OK);
        CHECK(desc.nparts == 4);
    }
}

/* ------------------------------------------------------------------ */
/* M11: a plain NAME.001 split                                        */
/*                                                                    */
/* Nothing to parse — the parts are anonymous slices and the whole     */
/* descriptor is the host's word. What is worth pinning is therefore   */
/* the contract, not a layout: where the joined LENGTH may come from,  */
/* and what happens when it can come from nowhere.                    */
/* ------------------------------------------------------------------ */

static uint32_t segsrc_size(void *ctx, const UncSegmentDesc *desc, int part)
{
    SegParts *p = (SegParts *)ctx;
    (void)desc;
    if (part < 1 || part > p->nparts) return UNC_SIZE_UNKNOWN;
    return p->len[part - 1];
}

static void split_desc(UncSegmentDesc *d, int nparts, uint32_t total)
{
    memset(d, 0, sizeof *d);
    d->scheme = UNC_FORMAT_SPLIT;
    d->part = 1;
    d->head_len = 0;
    d->nparts = (uint16_t)nparts;
    d->total = total;
    memcpy(d->name, "Thing.sit", 9);
    d->name_len = 9;
}

static void test_split(void)
{
    uint8_t p1[120], p2[100], p3[80];
    uint8_t payload[300];
    UncSegmentDesc desc;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    SegParts sp;
    UncVolumeSource vs;
    void *scratch;
    uint32_t opens = 0, back = 0;
    int i;

    for (i = 0; i < 300; i++) payload[i] = (uint8_t)(i * 11 + 3);
    memcpy(p1, payload, 120);
    memcpy(p2, payload + 120, 100);
    memcpy(p3, payload + 220, 80);

    test_make_alloc(&al);
    memset(&sp, 0, sizeof sp);
    sp.part[0] = p1; sp.len[0] = sizeof p1;
    sp.part[1] = p2; sp.len[1] = sizeof p2;
    sp.part[2] = p3; sp.len[2] = sizeof p3;
    sp.nparts = 3;
    memset(&vs, 0, sizeof vs);
    vs.ctx = &sp; vs.need = segsrc_need; vs.release = NULL;

    scratch = malloc(unc_segment_scratch_size());
    CHECK(scratch != NULL);

    /* --- the host counted the parts; the engine sums their lengths -- */
    split_desc(&desc, 3, UNC_SIZE_UNKNOWN);
    vs.size = segsrc_size;
    cap_make(&sk, &cap);
    CHECK(unc_extract_segments(&desc, &vs, scratch, &sk, &al, NULL, NULL)
          == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.info[0].name_len == 9 &&
          memcmp(cap.info[0].name, "Thing.sit", 9) == 0);
    CHECK(cap.rlen[0] == 0);                 /* a split file has one fork */
    CHECK(cap.dlen[0] == 300 && memcmp(cap.data[0], payload, 300) == 0);
    CHECK(sp.opens == 3);
    unc_segment_stats(scratch, &opens, &back);
    CHECK(opens == 3 && back == 0);          /* read strictly forward */

    /* --- no length, from anywhere: refused rather than guessed ------ */
    split_desc(&desc, 3, UNC_SIZE_UNKNOWN);
    vs.size = NULL;
    sp.opens = 0;
    cap_make(&sk, &cap);
    CHECK(unc_extract_segments(&desc, &vs, scratch, &sk, &al, NULL, NULL)
          == UNC_ERR_CORRUPT);
    CHECK(cap.count == 0);
    CHECK(sp.opens == 0);                    /* nothing was even opened */

    /* --- a host that knows the total needs no size callback -------- */
    split_desc(&desc, 3, 300);
    cap_make(&sk, &cap);
    CHECK(unc_extract_segments(&desc, &vs, scratch, &sk, &al, NULL, NULL)
          == UNC_OK);
    CHECK(cap.count == 1 && cap.dlen[0] == 300);

    /* --- a part the host cannot produce, with the total already
     * known: the same verdict the other schemes give, and the only
     * shape in which this one can give it at all. */
    split_desc(&desc, 3, 300);
    sp.missing = 2;
    cap_make(&sk, &cap);
    CHECK(unc_extract_segments(&desc, &vs, scratch, &sk, &al, NULL, NULL)
          == UNC_ERR_SEGMENTED);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_TRUNCATED);
    CHECK(cap.dlen[0] == 120);               /* what part 1 held is kept */
    sp.missing = 0;

    /* --- no count either: nobody could tell where the set ends ----- */
    split_desc(&desc, 0, UNC_SIZE_UNKNOWN);
    cap_make(&sk, &cap);
    CHECK(unc_extract_segments(&desc, &vs, scratch, &sk, &al, NULL, NULL)
          == UNC_ERR_CORRUPT);
    CHECK(cap.count == 0);

    /* --- one part is a whole set, and a legitimate one -------------- */
    split_desc(&desc, 1, UNC_SIZE_UNKNOWN);
    vs.size = segsrc_size;
    sp.nparts = 1;
    cap_make(&sk, &cap);
    CHECK(unc_extract_segments(&desc, &vs, scratch, &sk, &al, NULL, NULL)
          == UNC_OK);
    CHECK(cap.count == 1 && cap.dlen[0] == 120);
    CHECK(memcmp(cap.data[0], payload, 120) == 0);

    free(scratch);
}

/* ------------------------------------------------------------------ */
/* M2 follow-up: several BinHex documents in one file                 */
/* ------------------------------------------------------------------ */

/* Source: reference/XADMaster/XADBinHexParser.m (alphabet, header
 * layout, CRC-16/XMODEM per fork, 0x90 escape where count 0 means a
 * literal 0x90). This is the encoder side of fmt_binhex.c, so that the
 * multi-document loop is covered on a machine with no fixtures. */
static const char bh_alpha[65] =
    "!\"#$%&'()*+,-012345689@ABCDEFGHIJKLMNPQRSTUVXYZ[`abcdefhijklmpqr";

static const char bh_line[] = "(This file must be converted with BinHex 4.0)\n\n:";

/* Append one complete BinHex document; returns bytes written. */
static uint32_t bh_synth(uint8_t *out, const char *name,
                         const uint8_t *data, uint32_t dlen,
                         const uint8_t *rsrc, uint32_t rlen)
{
    uint8_t raw[1024], esc[1200];
    uint32_t n = 0, e = 0, i, off, bitbuf = 0, nbits = 0, col = 0;
    uint32_t nl = (uint32_t)strlen(name);
    uint16_t crc;

    raw[n++] = (uint8_t)nl;
    memcpy(raw + n, name, nl); n += nl;
    raw[n++] = 0;                                  /* version */
    memcpy(raw + n, "TEXT", 4); n += 4;
    memcpy(raw + n, "ttxt", 4); n += 4;
    raw[n++] = 0; raw[n++] = 0;                    /* finder flags */
    put32(raw + n, dlen); n += 4;
    put32(raw + n, rlen); n += 4;
    crc = unc_crc16_xmodem(0, raw, (int32_t)n);    /* header CRC */
    raw[n++] = (uint8_t)(crc >> 8); raw[n++] = (uint8_t)crc;
    memcpy(raw + n, data, dlen); n += dlen;
    crc = unc_crc16_xmodem(0, data, (int32_t)dlen);
    raw[n++] = (uint8_t)(crc >> 8); raw[n++] = (uint8_t)crc;
    memcpy(raw + n, rsrc, rlen); n += rlen;
    crc = unc_crc16_xmodem(0, rsrc, (int32_t)rlen);
    raw[n++] = (uint8_t)(crc >> 8); raw[n++] = (uint8_t)crc;

    /* RLE layer: escape 0x90, emit no runs. */
    for (i = 0; i < n; i++) {
        esc[e++] = raw[i];
        if (raw[i] == 0x90) esc[e++] = 0;
    }

    off = (uint32_t)strlen(bh_line);
    memcpy(out, bh_line, off);
    for (i = 0; i < e; i++) {
        bitbuf = (bitbuf << 8) | esc[i];
        nbits += 8;
        while (nbits >= 6) {
            nbits -= 6;
            out[off++] = (uint8_t)bh_alpha[(bitbuf >> nbits) & 0x3F];
            if (++col == 64) { out[off++] = '\n'; col = 0; }
        }
    }
    if (nbits) out[off++] = (uint8_t)bh_alpha[(bitbuf << (6 - nbits)) & 0x3F];
    out[off++] = ':';
    out[off++] = '\n';
    return off;
}

static uint32_t bh_text(uint8_t *out, const char *s)
{
    uint32_t n = (uint32_t)strlen(s);
    memcpy(out, s, n);
    return n;
}

static void test_binhex_multi(void)
{
    /* 0x90 in both payloads: the escape has to survive the round trip,
     * and it is the one byte that can desynchronise a document. */
    static const uint8_t d1[] = { 'h','i',0x90,0x90,'!' };
    static const uint8_t r1[] = { 'R','S','R','C' };
    static const uint8_t d2[] = { 's','e','c','o','n','d' };
    uint8_t arc[8192];
    uint32_t len, one;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    test_make_alloc(&al);

    /* --- one document: unchanged behaviour ------------------------- */
    one = bh_synth(arc, "first.txt", d1, sizeof d1, r1, sizeof r1);
    test_make_memio(&io, &m, arc, one);
    CHECK(unc_sniff(&io) == UNC_FORMAT_BINHEX);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_BINHEX, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == sizeof d1 && memcmp(cap.data[0], d1, sizeof d1) == 0);
    CHECK(cap.rlen[0] == sizeof r1 && memcmp(cap.rsrc[0], r1, sizeof r1) == 0);

    /* --- two documents, with a posting's worth of text between ----- */
    len = one;
    len += bh_text(arc + len, "\n--- next part of the digest ---\n"
                              "Content-Type: application/mac-binhex40\n\n");
    len += bh_synth(arc + len, "second.txt", d2, sizeof d2, r1, 0);
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_BINHEX, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 2);
    CHECK(cap.status[0] == UNC_OK && cap.status[1] == UNC_OK);
    CHECK(cap.info[0].name_len == 9 && memcmp(cap.info[0].name, "first.txt", 9) == 0);
    CHECK(cap.info[1].name_len == 10 && memcmp(cap.info[1].name, "second.txt", 10) == 0);
    CHECK(cap.dlen[0] == sizeof d1 && memcmp(cap.data[0], d1, sizeof d1) == 0);
    CHECK(cap.dlen[1] == sizeof d2 && memcmp(cap.data[1], d2, sizeof d2) == 0);
    CHECK(cap.rlen[1] == 0);

    /* --- the second document is truncated: per-entry error, and the
     *     first one still arrives ---------------------------------- */
    test_make_memio(&io, &m, arc, len - 12);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_BINHEX, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 2);
    CHECK(cap.status[0] == UNC_OK && cap.status[1] == UNC_ERR_TRUNCATED);

    /* --- a banner with no document after it is reported, not
     *     swallowed: taking the first document and exiting 0 is the
     *     defect this loop exists to fix -------------------------- */
    len = one;
    len += bh_text(arc + len, "\n(This file must be converted with BinHex 4.0)\n"
                              "and then the posting was cut off\n");
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_BINHEX, &io, &sk, &al, NULL, NULL)
          == UNC_ERR_FORMAT);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);

    /* --- ONE document posted in several parts: the mail header of the
     *     second posting lands in the middle of the stream, and the
     *     line has to be stepped over. Source for the rule:
     *     reference/macutils/hexbin/hqx.c. Note "From:" — its colon is
     *     the terminator, which is exactly how this used to end the
     *     document early and report it truncated ------------------- */
    {
        uint32_t cut = one / 2, tail;
        uint8_t split[8192];
        uint32_t sl = 0;
        /* Cut the document at a line boundary. */
        while (cut < one && arc[cut] != '\n') cut++;
        cut++;
        memcpy(split, arc, cut);
        sl = cut;
        sl += bh_text(split + sl, "\nFrom: someone\n"
                                  "Subject: first.txt (2/2)\n\n"
                                  "[ append this to part 1 ]\n\n");
        tail = one - cut;
        memcpy(split + sl, arc + cut, tail);
        sl += tail;

        test_make_memio(&io, &m, split, sl);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_BINHEX, &io, &sk, &al, NULL, NULL)
              == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
        CHECK(cap.dlen[0] == sizeof d1 && memcmp(cap.data[0], d1, sizeof d1) == 0);
        CHECK(cap.rlen[0] == sizeof r1 && memcmp(cap.rsrc[0], r1, sizeof r1) == 0);
    }
}


/* ------------------------------------------------------------------ */
/* M12: DiskDoubler containers                                        */
/* ------------------------------------------------------------------ */

/* One 'DDAR' entry header, 124 bytes; the payload follows it.
 * Source: reference/XADMaster/XADDiskDoublerParser.m parseArchive. */
static uint32_t ddar_entry(uint8_t *p, const char *name, int isdir, int enddir,
                           uint32_t dlen, uint32_t rlen, int inlineflag)
{
    uint32_t nl = (uint32_t)strlen(name), i;
    for (i = 0; i < 124; i++) p[i] = 0;
    memcpy(p, "DDAR", 4);
    p[8] = (uint8_t)nl;
    memcpy(p + 9, name, nl);
    p[72] = (uint8_t)isdir;
    p[73] = (uint8_t)enddir;
    put32(p + 74, dlen);
    put32(p + 78, rlen);
    memcpy(p + 90, "TEXT", 4);
    memcpy(p + 94, "ttxt", 4);
    p[99] = (uint8_t)(inlineflag ? 0x20 : 0x00);   /* finder flags */
    return 124;
}

/* ------------------------------------------------------------------ */
/* Method 7 (Stac LZS): a written stream, because the two specimens in  */
/* the wild reach neither of the two things worth checking — a match    */
/* longer than the 2048-byte window, and a fork of ODD length, whose    */
/* checksum is NOT complemented.                                        */
/* ------------------------------------------------------------------ */

typedef struct StacBits {
    uint8_t *p;
    uint32_t len;
    int      nbits;
    uint32_t acc;
} StacBits;

/* The stream is stored complemented, so each finished byte is inverted
 * on the way out. Source: XADDiskDoublerParser.m, case 7. */
static void stac_put(StacBits *b, uint32_t v, int n)
{
    int i;
    for (i = n - 1; i >= 0; i--) {
        b->acc = (b->acc << 1) | ((v >> i) & 1u);
        if (++b->nbits == 8) {
            b->p[b->len++] = (uint8_t)(~b->acc & 0xFFu);
            b->nbits = 0;
            b->acc = 0;
        }
    }
}

static void stac_flush(StacBits *b)
{
    while (b->nbits) stac_put(b, 0, 1);
}

/* A match of `length` at `dist`, with the 7-bit distance form and the
 * 4-bit length extension the codec uses past 8. */
static void stac_match(StacBits *b, uint32_t dist, uint32_t length)
{
    uint32_t extra;
    stac_put(b, 1, 1);
    stac_put(b, 1, 1);
    stac_put(b, dist, 7);
    if (length <= 4) {
        stac_put(b, length - 2u, 2);
        return;
    }
    stac_put(b, 3, 2);
    if (length <= 7) {
        stac_put(b, length - 5u, 2);
        return;
    }
    stac_put(b, 3, 2);
    extra = length - 8u;
    while (extra >= 15u) { stac_put(b, 15, 4); extra -= 15u; }
    stac_put(b, extra, 4);
}

static void test_dd_stac(void)
{
    static const char lit[] = "unclassic";
    static const uint32_t NLIT = 9, MATCH = 2100;   /* 2109: odd, > window */
    uint8_t one[4096], want[2109];
    uint8_t sum = 0;
    uint32_t n, i;
    StacBits b;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    UncOptions opt;
    static const uint8_t hint[] = "Stac";

    for (i = 0; i < NLIT; i++) want[i] = (uint8_t)(~(uint8_t)lit[i]);
    for (i = NLIT; i < NLIT + MATCH; i++) want[i] = want[i - NLIT];
    for (i = 0; i < NLIT + MATCH; i++) sum ^= want[i];

    for (n = 0; n < 84; n++) one[n] = 0;
    one[0] = 0xAB; one[1] = 0xCD; one[2] = 0x00; one[3] = 0x54;
    put32(one + 4, NLIT + MATCH);              /* datasize  */
    one[20] = 7; one[21] = 0;                  /* data method 7, no rsrc */
    memcpy(one + 32, "TEXT", 4);
    memcpy(one + 36, "ttxt", 4);
    /* The fork is 2109 bytes — odd, so the stored checksum is the plain
     * XOR rather than its complement. */
    one[48] = 0; one[49] = sum;

    /* Six bytes, a chunk count of TWO, eight bytes, then one 16-bit
     * length per chunk: eighteen plus four bytes the codec steps over.
     * No specimen has more than one chunk. */
    n = 84;
    for (i = 0; i < 6; i++) one[n++] = 0x11;
    put32(one + n, 2); n += 4;
    for (i = 0; i < 8; i++) one[n++] = 0x22;
    for (i = 0; i < 4; i++) one[n++] = 0x33;

    b.p = one + n; b.len = 0; b.nbits = 0; b.acc = 0;
    for (i = 0; i < NLIT; i++) {
        stac_put(&b, 0, 1);
        stac_put(&b, (uint8_t)lit[i], 8);
    }
    stac_match(&b, NLIT, MATCH);
    stac_put(&b, 1, 1); stac_put(&b, 0, 1); stac_put(&b, 0, 7);  /* end */
    stac_flush(&b);
    n += b.len;
    put32(one + 8, n - 84u);                   /* datacomp */

    opt.list_only = 0; opt.test_only = 0;
    opt.name_hint = hint;
    opt.name_hint_len = (uint16_t)(sizeof hint - 1);
    test_make_alloc(&al);
    test_make_memio(&io, &m, one, n);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKDOUBLER);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_DISKDOUBLER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == NLIT + MATCH);
    CHECK(memcmp(cap.data[0], want, NLIT + MATCH) == 0);

    /* The checksum is checked, and this is what proves it: one bit of it
     * changed must fail the fork rather than pass it. */
    one[49] ^= 0x01;
    test_make_memio(&io, &m, one, n);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_DISKDOUBLER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_CRC);
    one[49] ^= 0x01;
}

static void test_diskdoubler(void)
{
    uint8_t arc[1024];
    uint32_t len = 0, i;
    uint16_t crc;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    /* Archive header: 'DDAR' + 74 bytes, CRC-16/XMODEM over the first 76. */
    for (i = 0; i < 78; i++) arc[i] = 0;
    memcpy(arc, "DDAR", 4);
    crc = unc_crc16_xmodem(0, arc, 76);
    arc[76] = (uint8_t)(crc >> 8); arc[77] = (uint8_t)crc;
    len = 78;

    /* A folder, a file stored inline inside it, then the folder's end. */
    len += ddar_entry(arc + len, "folder", 1, 0, 0, 0, 0);
    len += ddar_entry(arc + len, "hello.txt", 0, 0, 11, 4, 1);
    memcpy(arc + len, "hello, fork", 11); len += 11;
    memcpy(arc + len, "RSRC", 4); len += 4;
    len += ddar_entry(arc + len, "", 0, 1, 0, 0, 0);

    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKDOUBLER);

    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_DISKDOUBLER, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 2);
    CHECK(cap.info[0].is_dir == 1);
    CHECK(cap.info[0].name_len == 6 && memcmp(cap.info[0].name, "folder", 6) == 0);
    /* The path is the folder's, joined — the walk tracks depth by the
     * end-of-directory marker, not by re-reading names. */
    CHECK(cap.info[1].name_len == 16 &&
          memcmp(cap.info[1].name, "folder/hello.txt", 16) == 0);
    CHECK(cap.status[1] == UNC_OK);
    CHECK(cap.dlen[1] == 11 && memcmp(cap.data[1], "hello, fork", 11) == 0);
    CHECK(cap.rlen[1] == 4 && memcmp(cap.rsrc[1], "RSRC", 4) == 0);
    CHECK(cap.info[1].type == 0x54455854u);   /* 'TEXT' */

    /* A single compressed file: magic, an 80-byte header, then the forks.
     * It carries no name of its own, so the host's supplies one and the
     * ".dd" suffix comes off. Source: XADDiskDoublerParser.m parse. */
    {
        UncOptions opt;
        static const uint8_t hint[] = "Report.txt.dd";
        uint8_t one[512];
        uint32_t n;
        for (n = 0; n < 84; n++) one[n] = 0;
        one[0] = 0xAB; one[1] = 0xCD; one[2] = 0x00; one[3] = 0x54;
        put32(one + 4, 5);           /* datasize   */
        put32(one + 8, 5);           /* datacomp   */
        put32(one + 12, 3);          /* rsrcsize   */
        put32(one + 16, 3);          /* rsrccomp   */
        one[20] = 0; one[21] = 0;    /* both methods: stored */
        memcpy(one + 32, "TEXT", 4);
        memcpy(one + 36, "ttxt", 4);
        n = 84;
        memcpy(one + n, "plain", 5); n += 5;
        memcpy(one + n, "RSC", 3);   n += 3;
        /* The probe accepts a zero CRC ("really old files"), which keeps
         * this synthetic file honest rather than needing one computed. */
        opt.list_only = 0; opt.test_only = 0;
        opt.name_hint = hint;
        opt.name_hint_len = (uint16_t)(sizeof hint - 1);
        test_make_memio(&io, &m, one, n);
        CHECK(unc_sniff(&io) == UNC_FORMAT_DISKDOUBLER);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_DISKDOUBLER, &io, &sk, &al, NULL,
                             &opt) == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
        CHECK(cap.info[0].name_len == 10 &&
              memcmp(cap.info[0].name, "Report.txt", 10) == 0);
        CHECK(cap.dlen[0] == 5 && memcmp(cap.data[0], "plain", 5) == 0);
        CHECK(cap.rlen[0] == 3 && memcmp(cap.rsrc[0], "RSC", 3) == 0);
    }

    /* A corrupt header CRC is not a DiskDoubler archive at all. */
    arc[76] ^= 0xFF;
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
    arc[76] ^= 0xFF;

    test_dd_stac();
}


/* ------------------------------------------------------------------ */
/* M12: Now Compress — the container, which the one fixture cannot     */
/* reach (it holds a single file, one fork, no folders)                */
/* ------------------------------------------------------------------ */

/* One 110-byte entry. Its last 4 bytes are a sum of the first 106,
 * which is what unc_sniff checks on the first entry.
 * Source: reference/XADMaster/XADNowCompressParser.m. */
static void now_entry(uint8_t *p, const char *name, int isdir,
                      uint32_t numdir, uint32_t dlen, uint32_t rlen,
                      uint32_t datastart)
{
    uint32_t nl = (uint32_t)strlen(name), i, sum = 0;
    for (i = 0; i < 110; i++) p[i] = 0;
    p[0] = (uint8_t)nl;
    memcpy(p + 1, name, nl);
    p[37] = (uint8_t)(isdir ? 0x10 : 0x00);
    memcpy(p + 38, "TEXT", 4);
    memcpy(p + 42, "ttxt", 4);
    p[82] = (uint8_t)(numdir >> 8); p[83] = (uint8_t)numdir;
    put32(p + 86, dlen);
    put32(p + 90, rlen);
    put32(p + 98, datastart);
    for (i = 0; i < 106; i++) sum += p[i];
    put32(p + 106, sum);
}

/* A block table for one file: `n` stored blocks of the given lengths,
 * laid out immediately after it. The table is `firstoffset`, then one
 * 8-byte record per block, then four bytes and a 32-bit sum of
 * everything before them.
 * Source: parseAndCheckFileHeaderWithHeaderOffset. */
static uint32_t now_sum32_t(uint32_t v)
{
    return (v >> 24) + ((v >> 16) & 0xff) + ((v >> 8) & 0xff) + (v & 0xff);
}

static void now_table(uint8_t *arc, uint32_t at, const uint32_t *lens, int n)
{
    uint32_t first = at + 4 + 8 * (uint32_t)n + 8;
    uint32_t last = first, sum;
    int k;

    put32(arc + at, first);
    sum = now_sum32_t(first);
    for (k = 0; k < n; k++) {
        uint8_t *rec = arc + at + 4 + 8 * (uint32_t)k;
        uint32_t next = last + lens[k] + 4;      /* padding 0 */
        rec[0] = rec[1] = rec[2] = rec[3] = 0;   /* flags 0 = stored */
        put32(rec + 4, next);
        sum += now_sum32_t(next);
        last = next;
    }
    for (k = 0; k < 4; k++) arc[at + 4 + 8 * (uint32_t)n + (uint32_t)k] = 0;
    put32(arc + at + 4 + 8 * (uint32_t)n + 4, sum);
}

static void test_nowcompress(void)
{
    uint8_t arc[2048];
    uint32_t i, at, f1, f2;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    for (i = 0; i < sizeof arc; i++) arc[i] = 0;
    arc[0] = 0x00; arc[1] = 0x02;
    put32(arc + 8, 3);                    /* three entries */

    /* The two streams live after the three entry records. */
    f1 = 24 + 3 * 110;
    f2 = f1 + 200;

    now_entry(arc + 24,       "folder", 1, 1, 0, 0, 0);
    now_entry(arc + 24 + 110, "inside", 0, 0, 6, 5, f1);
    now_entry(arc + 24 + 220, "beside", 0, 0, 4, 0, f2);

    /* Stream 1: one stored block holding rsrc then data. */
    {
        uint32_t lens[1];
        lens[0] = 11;
        now_table(arc, f1, lens, 1);
        at = f1 + 4 + 8 + 8;
        memcpy(arc + at, "RSRCXdatadd", 11);   /* 5 rsrc + 6 data */
    }
    /* Stream 2: one stored block, data fork only. */
    {
        uint32_t lens[1];
        lens[0] = 4;
        now_table(arc, f2, lens, 1);
        at = f2 + 4 + 8 + 8;
        memcpy(arc + at, "tail", 4);
    }

    test_make_memio(&io, &m, arc, sizeof arc);
    CHECK(unc_sniff(&io) == UNC_FORMAT_NOWCOMPRESS);

    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_NOWCOMPRESS, &io, &sk, &al, NULL, NULL)
          == UNC_OK);
    CHECK(cap.count == 3);
    CHECK(cap.info[0].is_dir == 1);
    CHECK(cap.info[1].name_len == 13 &&
          memcmp(cap.info[1].name, "folder/inside", 13) == 0);
    /* The folder held one entry, so the next one is a sibling again. */
    CHECK(cap.info[2].name_len == 6 &&
          memcmp(cap.info[2].name, "beside", 6) == 0);
    CHECK(cap.status[1] == UNC_OK);
    CHECK(cap.rlen[1] == 5 && memcmp(cap.rsrc[1], "RSRCX", 5) == 0);
    CHECK(cap.dlen[1] == 6 && memcmp(cap.data[1], "datadd", 6) == 0);
    CHECK(cap.status[2] == UNC_OK);
    CHECK(cap.dlen[2] == 4 && memcmp(cap.data[2], "tail", 4) == 0);
}

/* ------------------------------------------------------------------ */
/* Alysis SuperDisk! — the container, and the fork order no fixture    */
/* in the corpus can show (both of them have one fork per file)        */
/* ------------------------------------------------------------------ */

/* An 8-byte record prefix and a Pascal name padded to even.
 * Source: CODE 2 of super-disk-utility.hqx @0x2f6 and @0x336. */
static uint32_t sd_rec(uint8_t *p, uint32_t at, unsigned tag, const char *name)
{
    uint32_t nl = (uint32_t)strlen(name), i;
    for (i = 0; i < 8; i++) p[at + i] = 0;
    p[at] = (uint8_t)tag;
    at += 8;
    p[at++] = (uint8_t)nl;
    memcpy(p + at, name, nl);
    at += nl;
    if (at & 1u) p[at++] = 0;
    return at;
}

/* A stored block: the length word with bit 15 set counts itself and
 * the two bytes of the next block's length. Source: @0x614. */
static uint32_t sd_stored(uint8_t *p, uint32_t at, const char *bytes,
                          uint32_t n)
{
    p[at] = (uint8_t)(0x80 | ((n + 2) >> 8));
    p[at + 1] = (uint8_t)(n + 2);
    memcpy(p + at + 2, bytes, n);
    return at + 2 + n;
}

static void test_superdisk(void)
{
    uint8_t arc[1024];
    uint32_t i, at, len;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    for (i = 0; i < sizeof arc; i++) arc[i] = 0;
    /* The first eight bytes are read and thrown away (@0x110), so what
     * is in them is deliberately not zero here. */
    memcpy(arc, "\xe5\x80\xd0\xad\xf6\x7c\x42\x67", 8);
    at = 8;

    at = sd_rec(arc, at, 0x29, "folder");            /* open a folder */
    at += 20;                                        /* DInfo + scroll */

    at = sd_rec(arc, at, 0x28, "both");              /* a two-fork file */
    put32(arc + at, 6);                              /* data fork  */
    put32(arc + at + 4, 5);                          /* rsrc fork  */
    memcpy(arc + at + 8, "TEXT", 4);
    memcpy(arc + at + 12, "ttxt", 4);
    at += 30;
    at = sd_stored(arc, at, "DATAdd", 6);            /* data comes first */
    at = sd_stored(arc, at, "RSRCX", 5);

    at = sd_rec(arc, at, 0x28, "cannot");            /* an unknown method */
    put32(arc + at, 4);
    put32(arc + at + 4, 0);
    memcpy(arc + at + 8, "TEXT", 4);
    memcpy(arc + at + 12, "ttxt", 4);
    at += 30;
    arc[at] = 0; arc[at + 1] = 12;                   /* clen: 6 + 6 bytes */
    arc[at + 2] = 0; arc[at + 3] = 4;                /* ulen                */
    arc[at + 4] = 0; arc[at + 5] = 10;               /* method 10, SlowFastA */
    at += 12;

    at = sd_rec(arc, at, 0x2a, "");                  /* close the folder */
    at -= 2;                                         /* 0x2a carries no name */

    at = sd_rec(arc, at, 0x28, "after");             /* a sibling again */
    put32(arc + at, 4);
    put32(arc + at + 4, 0);
    memcpy(arc + at + 8, "TEXT", 4);
    memcpy(arc + at + 12, "ttxt", 4);
    at += 30;
    at = sd_stored(arc, at, "tail", 4);

    for (i = 0; i < 8; i++) arc[at + i] = 0;
    arc[at] = 0x27;                                  /* end of archive */
    len = at + 8;

    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_SUPERDISK);

    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SUPERDISK, &io, &sk, &al, NULL, NULL)
          == UNC_OK);
    CHECK(cap.count == 4);
    CHECK(cap.info[0].is_dir == 1);
    CHECK(cap.info[1].name_len == 11 &&
          memcmp(cap.info[1].name, "folder/both", 11) == 0);
    CHECK(cap.status[1] == UNC_OK);
    CHECK(cap.dlen[1] == 6 && memcmp(cap.data[1], "DATAdd", 6) == 0);
    CHECK(cap.rlen[1] == 5 && memcmp(cap.rsrc[1], "RSRCX", 5) == 0);
    /* A method no reference here could be read from is a per-entry
     * error, and the entry after it still arrives: the block chain is
     * walked past it by length. */
    CHECK(cap.status[2] == UNC_ERR_UNSUPPORTED);
    CHECK(cap.info[3].name_len == 5 &&
          memcmp(cap.info[3].name, "after", 5) == 0);
    CHECK(cap.status[3] == UNC_OK);
    CHECK(cap.dlen[3] == 4 && memcmp(cap.data[3], "tail", 4) == 0);

    /* Without the 0x27 record the file is not claimed at all: byte 8
     * looking like a tag is far too weak on its own. */
    arc[len - 8] = 0x28;
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) != UNC_FORMAT_SUPERDISK);
    arc[len - 8] = 0x27;
    arc[8] = 0x11;
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) != UNC_FORMAT_SUPERDISK);
}

/* ------------------------------------------------------------------ */
/* M13: uuencode                                                      */
/* ------------------------------------------------------------------ */

/* Encode len bytes as one uu line, into buf. Mirror of mu_convert. */
static uint32_t uu_line(uint8_t *buf, const uint8_t *p, uint32_t len)
{
    uint32_t o = 0, i;
    buf[o++] = (uint8_t)(0x20 + len);
    for (i = 0; i < len; i += 3) {
        uint8_t a = p[i];
        uint8_t b = i + 1 < len ? p[i + 1] : 0;
        uint8_t c = i + 2 < len ? p[i + 2] : 0;
        buf[o++] = (uint8_t)(0x20 + ((a >> 2) & 0x3f));
        buf[o++] = (uint8_t)(0x20 + (((a << 4) | (b >> 4)) & 0x3f));
        buf[o++] = (uint8_t)(0x20 + (((b << 2) | (c >> 6)) & 0x3f));
        buf[o++] = (uint8_t)(0x20 + (c & 0x3f));
    }
    buf[o++] = '\n';
    return o;
}

static uint32_t uu_section_bytes(uint8_t *buf, const char *hdr,
                                 const uint8_t *p, uint32_t len)
{
    uint32_t o = 0, i;
    uint32_t hl = (uint32_t)strlen(hdr);
    memcpy(buf, hdr, hl); o += hl;
    buf[o++] = '\n';
    for (i = 0; i < len; i += 45) {
        uint32_t n = len - i > 45 ? 45 : len - i;
        o += uu_line(buf + o, p + i, n);
    }
    buf[o++] = '`'; buf[o++] = '\n';
    memcpy(buf + o, "end\n", 4); o += 4;
    return o;
}

static void test_uu(void)
{
    uint8_t buf[4096];
    uint8_t payload[300], rsrc[64], info[16];
    uint32_t i, o = 0;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    for (i = 0; i < sizeof payload; i++) payload[i] = (uint8_t)(i * 7 + 1);
    for (i = 0; i < sizeof rsrc; i++) rsrc[i] = (uint8_t)(0xF0 - i);
    memset(info, 0, sizeof info);
    memcpy(info, "APPLxxxx", 8);
    info[3] = 'L'; memcpy(info + 4, "MACS", 4);

    /* A mail banner first: the reason the scan exists at all. */
    memcpy(buf, "From: nobody\nSubject: a file\n\n", 29); o = 29;
    o += uu_section_bytes(buf + o, "begin 644 \"Mac File\"", payload,
                          sizeof payload);
    o += uu_section_bytes(buf + o, "begin 644  .rsrc", rsrc, sizeof rsrc);
    o += uu_section_bytes(buf + o, "begin 644  .finfo", info, sizeof info);

    test_make_memio(&io, &m, buf, o);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UU);

    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_UU, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1);
    CHECK(cap.info[0].name_len == 8 &&
          memcmp(cap.info[0].name, "Mac File", 8) == 0);
    CHECK(cap.dlen[0] == sizeof payload &&
          memcmp(cap.data[0], payload, sizeof payload) == 0);
    CHECK(cap.rlen[0] == sizeof rsrc &&
          memcmp(cap.rsrc[0], rsrc, sizeof rsrc) == 0);
    /* The Finder info is the whole reason a document is read twice. */
    CHECK(cap.info[0].type == 0x4150504Cu);      /* 'APPL' */
    CHECK(cap.info[0].creator == 0x4D414353u);   /* 'MACS' */

    /* Two plain documents in one file, the newsgroup shape. Nothing
     * but the second document's offsets proves the base fix: with
     * relative offsets it decoded as corrupt. */
    o = 0;
    o += uu_section_bytes(buf + o, "begin 644 one.bin", payload, 60);
    memcpy(buf + o, "\n-- next --\n\n", 13); o += 13;
    o += uu_section_bytes(buf + o, "begin 600 two.bin", payload + 60, 120);

    test_make_memio(&io, &m, buf, o);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UU);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_UU, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 2);
    CHECK(cap.info[0].name_len == 7 &&
          memcmp(cap.info[0].name, "one.bin", 7) == 0);
    CHECK(cap.dlen[0] == 60 && memcmp(cap.data[0], payload, 60) == 0);
    CHECK(cap.dlen[1] == 120 && memcmp(cap.data[1], payload + 60, 120) == 0);
    CHECK(cap.rlen[1] == 0);

    /* CR line endings: these files came off Macs. */
    for (i = 0; i < o; i++) if (buf[i] == '\n') buf[i] = '\r';
    test_make_memio(&io, &m, buf, o);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UU);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_UU, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 2 && cap.dlen[1] == 120);

    /* One document posted in two parts: the second posting's header sits
     * between two data lines. A uu line's first character declares how
     * many bytes it encodes, so a line whose length disagrees cannot be
     * data — that is the test, and it is stronger than an alphabet. */
    {
        uint8_t split[4096];
        uint32_t o2 = 0, i2, cut;
        const char *hdr = "\nFrom: someone\nSubject: one.bin (2/2)\n\n"
                          "[ append this to part 1 ]\n\n";
        o2 += uu_section_bytes(split, "begin 644 one.bin", payload, 200);
        /* Re-cut it: header inserted after the third line. */
        cut = 0;
        for (i2 = 0, cut = 0; cut < 3 && i2 < o2; i2++)
            if (split[i2] == '\n') cut++;
        memmove(split + i2 + strlen(hdr), split + i2, o2 - i2);
        memcpy(split + i2, hdr, strlen(hdr));
        o2 += (uint32_t)strlen(hdr);

        test_make_memio(&io, &m, split, o2);
        CHECK(unc_sniff(&io) == UNC_FORMAT_UU);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_UU, &io, &sk, &al, NULL, NULL) == UNC_OK);
        CHECK(cap.count == 1);
        CHECK(cap.dlen[0] == 200 && memcmp(cap.data[0], payload, 200) == 0);
    }

    /* Prose that happens to contain "begin " is not a uu file. */
    {
        const char *prose = "To begin with, we should note\nthat nothing"
                            " here is encoded at all.\n";
        memcpy(buf, prose, strlen(prose));
        test_make_memio(&io, &m, buf, (uint32_t)strlen(prose));
        CHECK(unc_sniff(&io) != UNC_FORMAT_UU);
    }
}

/* ------------------------------------------------------------------ */
/* M13: ARC                                                           */
/* ------------------------------------------------------------------ */

static uint32_t arc_hdr(uint8_t *b, int method, const char *name,
                        uint32_t comp, uint32_t uncomp, uint16_t crc)
{
    uint32_t o = 0, i;
    b[o++] = 0x1A;
    b[o++] = (uint8_t)method;
    for (i = 0; i < 13; i++) b[o + i] = 0;
    memcpy(b + o, name, strlen(name) > 12 ? 12 : strlen(name));
    o += 13;
    b[o++] = (uint8_t)comp; b[o++] = (uint8_t)(comp >> 8);
    b[o++] = (uint8_t)(comp >> 16); b[o++] = (uint8_t)(comp >> 24);
    b[o++] = 0x21; b[o++] = 0x5B;            /* date */
    b[o++] = 0x00; b[o++] = 0x70;            /* time */
    b[o++] = (uint8_t)crc; b[o++] = (uint8_t)(crc >> 8);
    if (method != 1) {
        b[o++] = (uint8_t)uncomp; b[o++] = (uint8_t)(uncomp >> 8);
        b[o++] = (uint8_t)(uncomp >> 16); b[o++] = (uint8_t)(uncomp >> 24);
    }
    return o;
}

static void test_arc(void)
{
    uint8_t buf[2048];
    const uint8_t body[] = "ARCHIVE CONTENT, stored verbatim.";
    uint32_t blen = (uint32_t)sizeof body - 1;
    uint32_t o = 0;
    uint16_t crc;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    memset(buf, 0, sizeof buf);
    crc = unc_crc16_arc(0, body, (int32_t)blen);

    /* A directory, a stored file inside it, the directory end, then a
     * method-1 file (the older header, with no second size field) at
     * the top level. No fixture in the corpus has any of this. */
    o += arc_hdr(buf + o, 0x1e, "folder", 0, 0, 0);
    o += arc_hdr(buf + o, 0x02, "inside.txt", blen, blen, crc);
    memcpy(buf + o, body, blen); o += blen;
    buf[o++] = 0x1A; buf[o++] = 0x1f;              /* leave the folder */
    o += arc_hdr(buf + o, 0x01, "old.txt", blen, blen, crc);
    memcpy(buf + o, body, blen); o += blen;
    buf[o++] = 0x1A; buf[o++] = 0x00;              /* end of archive */

    test_make_memio(&io, &m, buf, o);
    CHECK(unc_sniff(&io) == UNC_FORMAT_ARC);

    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_ARC, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 2);
    CHECK(cap.info[0].name_len == 17 &&
          memcmp(cap.info[0].name, "folder/inside.txt", 17) == 0);
    CHECK(cap.status[0] == UNC_OK && cap.dlen[0] == blen);
    CHECK(memcmp(cap.data[0], body, blen) == 0);
    /* Out of the folder again: a sibling, not a child. */
    CHECK(cap.info[1].name_len == 7 &&
          memcmp(cap.info[1].name, "old.txt", 7) == 0);
    CHECK(cap.status[1] == UNC_OK && cap.dlen[1] == blen);

    /* A wrong CRC is a per-entry error, and the entry after it still
     * extracts. */
    {
        uint32_t at = 0;
        at += arc_hdr(buf, 0x02, "bad.txt", blen, blen, (uint16_t)(crc ^ 1));
        memcpy(buf + at, body, blen); at += blen;
        at += arc_hdr(buf + at, 0x02, "good.txt", blen, blen, crc);
        memcpy(buf + at, body, blen); at += blen;
        buf[at++] = 0x1A; buf[at++] = 0x00;
        test_make_memio(&io, &m, buf, at);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_ARC, &io, &sk, &al, NULL, NULL)
              == UNC_OK);
        CHECK(cap.count == 2);
        CHECK(cap.status[0] == UNC_ERR_CRC);
        CHECK(cap.status[1] == UNC_OK && cap.dlen[1] == blen);
    }

    /* ArcMac: one stream holds both forks, DATA FORK FIRST, and the fork
     * lengths are little-endian.
     *
     * The order is not asserted here — it is MEASURED, by having ArcMac
     * itself archive a two-fork file under the emulator
     * (tools/vmac/arcmac.py). This builds an entry the measured way and
     * guards the split, which is a different job: a generator that agrees
     * with the decoder is not evidence about the format (DECISIONS.md,
     * M13). Before 2026-08-16 both this test and the decoder read the
     * lengths big-endian, so the test could not see the bug. */
    {
        const uint8_t rsrc[] = "RESOURCE FORK BYTES";
        uint32_t rlen = (uint32_t)sizeof rsrc - 1;
        uint8_t mac[256];
        uint32_t at, total = blen + rlen;
        uint16_t mcrc;

        memset(mac, 0, sizeof mac);
        mac[0] = 0x1B;                 /* Mac magic          */
        mac[1] = 0x02;                 /* kind = stored      */
        memcpy(mac + 2, "Mac Entry", 9);
        memcpy(mac + 34, "TEXT", 4);
        memcpy(mac + 38, "ttxt", 4);
        mac[50] = (uint8_t)blen;       /* data fork length, little-endian */
        mac[54] = (uint8_t)rlen;       /* rsrc fork length, little-endian */
        mac[59] = 0x1A;                /* the PC header      */
        mac[60] = 0x02;
        memcpy(mac + 61, "MACENTRY.TXT", 12);
        mac[74] = (uint8_t)total;      /* compressed size    */
        mac[84] = (uint8_t)total;      /* uncompressed size  */
        at = 88;
        memcpy(mac + at, body, blen); at += blen;
        memcpy(mac + at, rsrc, rlen);  at += rlen;
        mcrc = unc_crc16_arc(0, mac + 88, (int32_t)total);
        mac[82] = (uint8_t)(mcrc & 0xFF);
        mac[83] = (uint8_t)(mcrc >> 8);
        mac[at++] = 0x1B; mac[at++] = 0x00;

        test_make_memio(&io, &m, mac, at);
        CHECK(unc_sniff(&io) == UNC_FORMAT_ARC);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_ARC, &io, &sk, &al, NULL, NULL)
              == UNC_OK);
        CHECK(cap.count == 1);
        CHECK(cap.info[0].name_len == 9 &&
              memcmp(cap.info[0].name, "Mac Entry", 9) == 0);
        CHECK(cap.info[0].type == 0x54455854u);      /* 'TEXT' */
        CHECK(cap.status[0] == UNC_OK);
        CHECK(cap.dlen[0] == blen && memcmp(cap.data[0], body, blen) == 0);
        CHECK(cap.rlen[0] == rlen && memcmp(cap.rsrc[0], rsrc, rlen) == 0);
    }
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
    test_lzh();
    test_sitseg();
    test_zipseg();
    test_split();
    test_binhex_multi();
    test_diskdoubler();
    test_nowcompress();
    test_superdisk();
    test_uu();
    test_arc();
}
