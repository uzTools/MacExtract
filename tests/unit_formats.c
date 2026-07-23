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

void run_format_tests(void)
{
    test_macbinary();
    test_applesingle();
    test_bitin();
    test_huffman_tree();
    test_packit();
    test_canon();
    test_cpt();
}
