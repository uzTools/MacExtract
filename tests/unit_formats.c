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
    /* The archive's own comment, and how many times it was delivered:
     * an archive without one must not call back at all. Sized for what
     * these tests hand in rather than for UNC_COMMENT_MAX, which is
     * zip's 64 KB ceiling; cap_comment refuses anything longer, so a
     * test that outgrows it fails loudly instead of truncating. */
    uint8_t comment[2048];
    uint16_t comment_len;
    int comments;
    /* Each entry's Get Info comment, copied in begin_entry: the engine's
     * bytes are only valid until that entry's end_entry returns. */
    uint8_t ecomment[8][256];
} CapSink;

static int cap_begin(void *ctx, const UncEntryInfo *info)
{
    CapSink *s = (CapSink *)ctx;
    if (s->count >= 8) return -1;
    s->info[s->count] = *info;
    s->dlen[s->count] = s->rlen[s->count] = 0;
    if (info->comment_len > sizeof s->ecomment[0]) return -1;
    if (info->comment_len)
        memcpy(s->ecomment[s->count], info->comment, info->comment_len);
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

static int cap_comment(void *ctx, const uint8_t *buf, uint16_t len)
{
    CapSink *s = (CapSink *)ctx;
    if (len > sizeof s->comment) return -1;
    memcpy(s->comment, buf, len);
    s->comment_len = len;
    s->comments++;
    /* The comment must arrive BEFORE the first entry, and this is where
     * that is checked: by the time any entry has been seen, it is late. */
    if (s->count) return -1;
    return 0;
}

static void cap_make(UncSink *sk, CapSink *s)
{
    memset(s, 0, sizeof *s);
    sk->ctx = s;
    sk->begin_entry = cap_begin;
    sk->write = cap_write;
    sk->end_entry = cap_end;
    sk->comment = cap_comment;
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

    /* THE 0xA001 FALLBACK, pinned here because nothing else reaches it.
     * fmt_macbinary.c accepts a header whose CRC was computed with the
     * reflected 0xA001 table instead of CRC-16/XMODEM — XADMaster's
     * tolerance, supported by no standard. Measured 2026-09-28: it
     * fires ZERO times across 933 fixtures and 9,330 robustness
     * variants, and removing it changes nothing any suite grades. So
     * it was uncited AND unexercised, which is the pair OPEN_ITEMS
     * calls the `unc_lzah.c` shape. This case does not make it right —
     * only noticed, so a change to it cannot pass silently. */
    {
        uint16_t a = 0xFFFF;
        uint32_t i, j;
        for (i = 0; i < 124; i++) {
            a ^= arc[i];
            for (j = 0; j < 8; j++)
                a = (a & 1) ? (uint16_t)((a >> 1) ^ 0xA001)
                            : (uint16_t)(a >> 1);
        }
        a ^= 0xFFFF;
        arc[124] = (uint8_t)(a >> 8); arc[125] = (uint8_t)a;
        test_make_memio(&io, &m, arc, len);
        CHECK(unc_sniff(&io) == UNC_FORMAT_MACBINARY);
    }
}

/* The rest of the Finder info a MacBinary header holds, the lock and the
 * Get Info comment (DECISIONS.md 2026-10-17, *the envelopes' own Finder
 * info*). The header is mb_synth's, edited and re-checksummed. */
static void mb_recrc(uint8_t *b)
{
    uint16_t crc = unc_crc16_xmodem(0, b, 124);
    b[124] = (uint8_t)(crc >> 8); b[125] = (uint8_t)crc;
}

static void test_macbinary_meta(void)
{
    static const char cmt[] = "A comment after the resource fork.";
    uint8_t arc[1024];
    uint32_t len, cl = (uint32_t)sizeof cmt - 1;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    UncOptions opt;
    const UncEntryInfo *e = &cap.info[0];

    test_make_alloc(&al);

    /* II: location, folder, Protected, and a comment. */
    len = mb_synth(arc, "placed", "hello, fork", 11, "RSRC", 4);
    arc[73] = 0x01; arc[101] = 0x20;
    arc[75] = 0x00; arc[76] = 0x50; arc[77] = 0x00; arc[78] = 0x64;
    arc[79] = 0x00; arc[80] = 0x07;
    arc[81] = 0x01;
    arc[99] = 0; arc[100] = (uint8_t)cl;
    mb_recrc(arc);
    memcpy(arc + len, cmt, cl);
    test_make_memio(&io, &m, arc, len + cl);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_MACBINARY, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(e->meta == UNC_META_FINFO);
    CHECK(memcmp(e->finder_info, "TEXTttxt\x01\x20\x00\x50\x00\x64\x00\x07", 16) == 0);
    CHECK(e->locked == UNC_LOCK_YES);
    CHECK(e->comment_len == cl && memcmp(cap.ecomment[0], cmt, cl) == 0);
    CHECK(cap.dlen[0] == 11 && cap.rlen[0] == 4);

    /* The same in list mode: the comment is read without the copy buffer. */
    memset(&opt, 0, sizeof opt);
    opt.list_only = 1;
    test_make_memio(&io, &m, arc, len + cl);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_MACBINARY, &io, &sk, &al, NULL, &opt) == UNC_OK);
    CHECK(e->comment_len == cl && memcmp(cap.ecomment[0], cmt, cl) == 0);

    /* Cut inside the comment: the forks are whole, the comment is dropped
     * and the entry is not an error (fmt_macbinary.c says why). */
    test_make_memio(&io, &m, arc, len + cl - 1);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_MACBINARY, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK && e->comment_len == 0);

    /* III: fdScript and fdXFlags, and 73's bit 7 is isAlias, not a lock. */
    len = mb_synth(arc, "alias", "hello, fork", 11, "RSRC", 4);
    arc[73] = 0x80;
    memcpy(arc + 102, "mBIN", 4);
    arc[106] = 0x81; arc[107] = 0x02;
    mb_recrc(arc);
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_MACBINARY, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(e->meta == (UNC_META_FINFO | UNC_META_FXINFO));
    CHECK(e->finder_info[24] == 0x81 && e->finder_info[25] == 0x02);
    CHECK(e->finder_info[16] == 0 && e->finder_info[31] == 0);
    CHECK(e->locked == UNC_LOCK_NO && e->comment_len == 0);
    CHECK((e->finder_flags & 0x8000) && (e->finder_info[8] & 0x80));

    /* I: no CRC, and 73's bit 7, "Locked", is the lock. */
    len = mb_synth(arc, "old", "hello, fork", 11, "RSRC", 4);
    arc[73] = 0x80;
    arc[122] = arc[123] = arc[124] = arc[125] = 0;
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_MACBINARY);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_MACBINARY, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(e->locked == UNC_LOCK_YES && e->meta == UNC_META_FINFO);
    /* ...and only the lock: left in the flags it is System 7's isAlias. */
    CHECK((e->finder_flags & 0x8000) && (e->finder_info[8] & 0x80) == 0);
    arc[73] = 0x00;
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_MACBINARY, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(e->locked == UNC_LOCK_NO);
}

/* ------------------------------------------------------------------ */
/* M1: AppleSingle/AppleDouble                                        */
/* ------------------------------------------------------------------ */

static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
}

/* Mac OS X's sidecars (src/unc_sidecar.c): the names, and the capture fed
 * a byte at a time and all at once to the same answer. */
static void test_sidecar(void)
{
    static const uint8_t ad[] = {
        0x00,0x05,0x16,0x07, 0x00,0x02,0x00,0x00,
        'M','a','c',' ','O','S',' ','X',' ',' ',' ',' ',' ',' ',' ',' ',
        0x00,0x02,
        0,0,0,9, 0,0,0,50, 0,0,0,32,
        0,0,0,2, 0,0,0,82, 0,0,0,3,
        'T','E','X','T','t','t','x','t', 0x01,0x20, 0,0x50, 0,0x64, 0,0,
        0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        'r','e','s' };
    static const uint8_t zero[82 + 3] = { 0x00,0x05,0x16,0x07, 0x00,0x02,0x00,0x00 };
    UncAdCap a;
    UncEntryInfo e;
    uint32_t i;

    CHECK(unc_side_kind((const uint8_t *)"__MACOSX", 8, 1) == UNC_SIDE_DIR);
    CHECK(unc_side_kind((const uint8_t *)"__MACOSX/a", 10, 1) == UNC_SIDE_DIR);
    CHECK(unc_side_kind((const uint8_t *)"__MACOSXa", 9, 1) == UNC_SIDE_NO);
    CHECK(unc_side_kind((const uint8_t *)"a/._b", 5, 0) == UNC_SIDE_FILE);
    CHECK(unc_side_kind((const uint8_t *)"a/._", 4, 0) == UNC_SIDE_NO);
    CHECK(unc_side_kind((const uint8_t *)"a/._b", 5, 1) == UNC_SIDE_NO);
    CHECK(unc_side_of((const uint8_t *)"__MACOSX/d/e/._f", 16,
                      (const uint8_t *)"d/e/f", 5));
    CHECK(unc_side_of((const uint8_t *)"__MACOSX/._f", 12,
                      (const uint8_t *)"f", 1));
    CHECK(unc_side_of((const uint8_t *)"d/._f", 5, (const uint8_t *)"d/f", 3));
    CHECK(!unc_side_of((const uint8_t *)"d/._f", 5, (const uint8_t *)"e/f", 3));
    CHECK(!unc_side_of((const uint8_t *)"d/._f", 5, (const uint8_t *)"d/ff", 4));
    CHECK(!unc_side_of((const uint8_t *)"__MACOSX/._f", 12,
                       (const uint8_t *)"x/f", 3));

    unc_ad_init(&a, sizeof ad);
    for (i = 0; i < sizeof ad && !unc_ad_feed(&a, ad + i, 1); i++) {}
    CHECK(a.state == UNC_AD_YES && a.roff == 82 && a.rlen == 3);
    unc_entry_clear(&e);
    unc_ad_apply(&a, &e);
    CHECK(e.type == 0x54455854u && e.finder_flags == 0x0120);
    CHECK((e.meta & (UNC_META_FINFO | UNC_META_FXINFO)) ==
          (UNC_META_FINFO | UNC_META_FXINFO));
    CHECK(e.finder_info[11] == 0x50 && e.finder_info[13] == 0x64);

    unc_ad_init(&a, sizeof ad);
    CHECK(unc_ad_feed(&a, ad, sizeof ad) == 1 && a.state == UNC_AD_YES);
    /* A resource fork past the end: not a sidecar. */
    unc_ad_init(&a, sizeof ad - 1);
    (void)unc_ad_feed(&a, ad, sizeof ad - 1);
    unc_ad_end(&a);
    CHECK(a.state == UNC_AD_NOT);
    /* Cut inside the table: not a sidecar either. */
    unc_ad_init(&a, sizeof ad);
    (void)unc_ad_feed(&a, ad, 40);
    unc_ad_end(&a);
    CHECK(a.state == UNC_AD_NOT);
    /* No entry 2 or 9: copyfile always has both; this is not one. */
    unc_ad_init(&a, sizeof zero);
    CHECK(unc_ad_feed(&a, zero, sizeof zero) == 1 && a.state == UNC_AD_NOT);
    /* 32 zero bytes of Finder info state nothing. */
    {
        uint8_t z[sizeof ad];
        memcpy(z, ad, sizeof ad);
        memset(z + 50, 0, 32);
        unc_ad_init(&a, sizeof z);
        (void)unc_ad_feed(&a, z, sizeof z);
        unc_entry_clear(&e);
        unc_ad_apply(&a, &e);
        CHECK(a.state == UNC_AD_YES && e.meta == 0 && e.type == 0);
    }
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

    /* RFC 1740's "unknown" date, 0x80000000, is left unknown in all
     * three places it can be (it came out as 1931-12-13 before
     * 2026-10-17), and a 16-byte entry 9 states its FInfo alone. */
    {
        unc_entry_clear(&cap.info[1]);
        memset(arc, 0, 16);
        put32(arc, 0x80000000u); put32(arc + 4, 0x00000010u);
        put32(arc + 8, 0x80000000u);
        unc_as_record(&cap.info[1], 8, arc, 16);
        CHECK(cap.info[1].create_date == 0);
        CHECK(cap.info[1].mod_date == 0x10u + 0xB492F400u);
        CHECK(!(cap.info[1].meta & UNC_META_BACKUP));
        /* The one date stated is GMT, so marked an instant; the two
         * unknown ones carry no mark (DECISIONS.md 2026-10-17, *dates in
         * the Macintosh's own zone*). */
        CHECK(cap.info[1].meta == UNC_META_MD_UTC);
        memcpy(arc, "APPLausT\x01\x00\x00\x10\x00\x20\x00\x00", 16);
        unc_as_record(&cap.info[1], 9, arc, 16);
        CHECK(cap.info[1].meta == (UNC_META_FINFO | UNC_META_MD_UTC));
        CHECK(cap.info[1].finder_info[11] == 0x10);
        CHECK(cap.info[1].finder_flags == 0x0100);
    }
}

/* An AppleDouble sidecar with NO "real name" entry — the shape Netatalk
 * writes, and the shape every `._X` beside an `X` on a Mac volume has.
 * The name is then the host's, as it is for every other name-less
 * format here; before 2026-08-21 the sink got an empty name and wrote a
 * file called "_". */
static void test_appledouble_noname(void)
{
    uint8_t arc[256];
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    UncOptions opt;
    static const uint8_t hint[] = "Foo";
    uint32_t off = 26 + 12;

    memset(arc, 0, sizeof arc);
    put32(arc, 0x00051607u);                    /* AppleDouble */
    put32(arc + 4, 0x00020000u);
    memcpy(arc + 8, "Netatalk        ", 16);
    arc[24] = 0; arc[25] = 1;
    put32(arc + 26, 2); put32(arc + 30, off); put32(arc + 34, 6);
    memcpy(arc + off, "RSRC!!", 6); off += 6;

    memset(&opt, 0, sizeof opt);
    opt.name_hint = hint;
    opt.name_hint_len = (uint16_t)(sizeof hint - 1);
    test_make_alloc(&al);
    test_make_memio(&io, &m, arc, off);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_APPLESINGLE, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.info[0].name_len == 3 &&
          memcmp(cap.info[0].name, "Foo", 3) == 0);
    CHECK(cap.rlen[0] == 6 && memcmp(cap.rsrc[0], "RSRC!!", 6) == 0);
    CHECK(cap.dlen[0] == 0);

    /* No hint, no name: the entry still extracts, and the host names it.
     * This is the case the CLI cannot reach — it always has a filename —
     * and a caller that passes none must not get a truncated read. */
    test_make_memio(&io, &m, arc, off);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_APPLESINGLE, &io, &sk, &al, NULL,
                         NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.info[0].name_len == 0);
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

    /* ONE symbol, written with a length of 1 -> Kraft 0.5, the most
     * incomplete a code can be. Now Compress writes exactly this: a
     * block matched entirely out of the member before it codes one
     * match symbol and no literal at all (docs/formats/now-compress.md,
     * *The main table*). No fixture comes near it — the smallest main
     * alphabet in the two real Now archives is 47 symbols, measured by
     * tools/derive_now.py over both — so the two bytes here are what
     * covers the shape. Enough of them to fill the fast table's ten
     * bits, because that is the path at risk: half of
     * fastlen[] names the symbol and the other half must fall through
     * to the walk and be refused. */
    lens[0] = 0; lens[1] = 0; lens[2] = 1; lens[3] = 0;
    CHECK(unc_canon_build(&cn, lens, 4) == UNC_OK);
    buf[0] = 0x40; buf[1] = 0x00;   /* bits 0, then 1: the code, then not */
    test_make_memio(&io, &m, buf, 2);
    unc_bufin_init(&in, &io, NULL, storage, sizeof storage);
    unc_bitin_init(&bi, &in);
    CHECK(unc_canon_decode(&cn, &bi) == 2);
    CHECK(unc_canon_decode(&cn, &bi) == -1);

    /* Over-subscribed code -> rejected at build time. */
    lens[0] = 1; lens[1] = 1; lens[2] = 1;
    CHECK(unc_canon_build(&cn, lens, 3) == UNC_ERR_CORRUPT);

    /* The deepest length the type allows. UNC_CANON_MAX_BITS is 31, so
     * the code space reaches 1 << 31 here — which is not an int32_t, and
     * carrying it signed the way puff.c does at 15 bits is undefined
     * behaviour the sanitizer build catches. Two symbols at 31 bits are
     * a legal (very incomplete) code; 1 << 31 of them would not be, and
     * nothing can declare that many, so the check being made BEFORE the
     * subtraction is what keeps the arithmetic in range. */
    {
        uint8_t deep[2];
        deep[0] = UNC_CANON_MAX_BITS; deep[1] = UNC_CANON_MAX_BITS;
        CHECK(unc_canon_build(&cn, deep, 2) == UNC_OK);
        CHECK(cn.maxlen == UNC_CANON_MAX_BITS);
        /* One length past it is refused rather than truncated. */
        deep[0] = UNC_CANON_MAX_BITS + 1;
        CHECK(unc_canon_build(&cn, deep, 2) == UNC_ERR_CORRUPT);
    }
}

/* Build a one-entry RLE-only Compact Pro archive around `comp`, with
 * the archive comment `cmt` (NULL for none — what most archives have). */
static uint32_t cpt_synth(uint8_t *out, const uint8_t *comp, uint32_t clen,
                          const uint8_t *plain, uint32_t plen,
                          const uint8_t *cmt, uint32_t cmtlen)
{
    uint32_t off = 8 + clen, crc;
    uint8_t *ix = out + off;
    uint8_t *e;

    out[0] = 1; out[1] = 1; out[2] = out[3] = 0;
    put32(out + 4, off);
    memcpy(out + 8, comp, clen);

    /* index: u32 crc, u16 nentries, u8 commentlen, comment, one file entry */
    ix[4] = 0; ix[5] = 1;          /* nentries = 1 */
    ix[6] = (uint8_t)cmtlen;
    if (cmtlen) memcpy(ix + 7, cmt, cmtlen);
    e = ix + 7 + cmtlen;
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
    crc = unc_crc32(0xFFFFFFFFu, ix + 4, (int32_t)(3 + cmtlen + 50));
    put32(ix, crc);                /* index CRC */
    return off + 7 + cmtlen + 50;
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
    uint32_t len = cpt_synth(arc, comp, sizeof comp, plain, sizeof plain,
                             NULL, 0);
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

    /* This archive has no comment, so the sink must not be told about
     * one. An empty comment and no comment are the same thing here. */
    CHECK(cap.comments == 0);
}

/* The archive's own comment: Compact Pro is the only format that has
 * one, and until 2026-08-23 the engine read it, folded it into the
 * index CRC and dropped it. */
static void test_cpt_comment(void)
{
    static const uint8_t comp[] = { 0x41 };
    static const uint8_t plain[] = { 0x41 };
    /* A comment as a Mac writes one: two lines separated by CR, and an
     * 8-bit MacRoman byte (0xA5, bullet) that no ASCII reading gets
     * right. Neither is rewritten on the way out. */
    static const uint8_t cmt[] = { 'R', 'e', 'a', 'd', ' ', 0xA5, '\r',
                                   'm', 'e' };
    /* 255 is what COMPACT PRO can express — its length is one byte —
     * and no longer what the sink's contract allows. */
    uint8_t arc[512], big[512], full[255];
    uint32_t len, i;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    test_make_alloc(&al);

    len = cpt_synth(arc, comp, sizeof comp, plain, sizeof plain,
                    cmt, sizeof cmt);
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_COMPACTPRO);
    cap_make(&sk, &cap);
    /* cap_comment refuses a comment that arrives after an entry, which
     * would fail this call: reaching UNC_OK is the ordering check. */
    CHECK(unc_extract_as(UNC_FORMAT_COMPACTPRO, &io, &sk, &al, NULL, NULL)
          == UNC_OK);
    CHECK(cap.comments == 1);
    CHECK(cap.comment_len == sizeof cmt);
    CHECK(memcmp(cap.comment, cmt, sizeof cmt) == 0);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);

    /* The longest one the format can express: the length is a byte. */
    for (i = 0; i < sizeof full; i++) full[i] = (uint8_t)('a' + i % 26);
    len = cpt_synth(big, comp, sizeof comp, plain, sizeof plain,
                    full, sizeof full);
    test_make_memio(&io, &m, big, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_COMPACTPRO, &io, &sk, &al, NULL, NULL)
          == UNC_OK);
    CHECK(cap.comments == 1 && cap.comment_len == sizeof full);
    CHECK(memcmp(cap.comment, full, sizeof full) == 0);

    /* A sink with no comment callback is not a broken sink: it is every
     * host that has no use for one, and the archive must extract as it
     * always did. */
    test_make_memio(&io, &m, arc, (uint32_t)(len = cpt_synth(
        arc, comp, sizeof comp, plain, sizeof plain, cmt, sizeof cmt)));
    cap_make(&sk, &cap);
    sk.comment = NULL;
    CHECK(unc_extract_as(UNC_FORMAT_COMPACTPRO, &io, &sk, &al, NULL, NULL)
          == UNC_OK);
    CHECK(cap.comments == 0);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == sizeof plain);
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

    /* An Optimizer, a Compressor and an Encryptor module, each named.
     *
     * WHAT THIS CANNOT SEE: no archive written by StuffIt 2.x is in
     * hand, so these entries are built to the layout read out of
     * StuffIt Deluxe 2.0.1's own application (src/fmt_sit.c) rather
     * than measured. What it does check is the thing that matters
     * either way — that a fork the archive says went through a module
     * is REFUSED. The first case decodes perfectly as method 1 and its
     * CRC agrees, so with the flag ignored it comes back UNC_OK with
     * the optimized bytes under the original's name; the control below
     * is the same archive with bit 0x40 cleared and it must extract,
     * which is what makes the refusal a discrimination and not a
     * blanket. */
    {
        uint8_t mod[256];
        uint32_t mlen;
        uint16_t crc;
        int i;
        /* flag/nibble to set, the id byte's offset, its value, and what
         * the entry should then report. The NAME a host prints for an id
         * is not graded here and cannot be: the table is the CLI's
         * (cli/main.c, module_name), because on the 68000 target it
         * would be resident A5 for every extraction. */
        static const struct {
            uint8_t meth; int off; uint8_t id; unsigned kind;
        } cases[] = {
            { 0x41, 106,  5, UNC_MODULE_OPTIMIZER  },
            { 0x41, 106, 99, UNC_MODULE_OPTIMIZER  },
            { 0x07,  46,  1, UNC_MODULE_COMPRESSOR },
        };
        /* 255 is NOT one of them: it is the id StuffIt Deluxe 2.0.1
         * writes for an Optimizer nothing can undo, and such an entry
         * decodes. The ids above are the refused case, and it is not a
         * guess either — `MacPaint 1` carries a 'DCMP' and writes its
         * real id of 4, which Aladdin's own Engine refuses to unstuff.
         * tools/run_sitopt.py grades both against five archives 2.0.1
         * wrote. */

        for (i = 0; i < (int)(sizeof cases / sizeof cases[0]); i++) {
            mlen = sit_synth(mod, "opt", 1, comp, sizeof comp,
                             plain, sizeof plain);
            mod[22 + 1] = cases[i].meth;
            mod[22 + cases[i].off] = cases[i].id;
            crc = unc_crc16_arc(0, mod + 22, 110);
            mod[22 + 110] = (uint8_t)(crc >> 8);
            mod[22 + 111] = (uint8_t)crc;
            test_make_memio(&io, &m, mod, mlen);
            cap_make(&sk, &cap);
            CHECK(unc_extract_as(UNC_FORMAT_SIT, &io, &sk, &al, NULL, NULL)
                  == UNC_OK);
            CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_MODULE);
            CHECK(cap.info[0].module_kind == cases[i].kind);
            CHECK(cap.info[0].module_id == cases[i].id);
            CHECK(cap.dlen[0] == 0);       /* nothing was written */
        }

        /* The control: bit 0x40 cleared, everything else identical. */
        mlen = sit_synth(mod, "opt", 1, comp, sizeof comp, plain, sizeof plain);
        mod[22 + 106] = 5;
        crc = unc_crc16_arc(0, mod + 22, 110);
        mod[22 + 110] = (uint8_t)(crc >> 8);
        mod[22 + 111] = (uint8_t)crc;
        test_make_memio(&io, &m, mod, mlen);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_SIT, &io, &sk, &al, NULL, NULL) == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
        CHECK(cap.info[0].module_kind == UNC_MODULE_NONE);
        CHECK(cap.dlen[0] == sizeof plain);

        /* Optimizer id 255: decoded, not refused, and the fields still
         * say what happened so a host can report it. */
        mlen = sit_synth(mod, "lossy", 1, comp, sizeof comp,
                         plain, sizeof plain);
        mod[22 + 1] = 0x41;
        mod[22 + 106] = 255;
        crc = unc_crc16_arc(0, mod + 22, 110);
        mod[22 + 110] = (uint8_t)(crc >> 8);
        mod[22 + 111] = (uint8_t)crc;
        test_make_memio(&io, &m, mod, mlen);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_SIT, &io, &sk, &al, NULL, NULL) == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
        CHECK(cap.info[0].module_kind == UNC_MODULE_OPTIMIZER);
        CHECK(cap.info[0].module_id == 255);
        CHECK(cap.dlen[0] == sizeof plain);
        CHECK(memcmp(cap.data[0], plain, sizeof plain) == 0);

        /* An encrypted fork names its encryptor too, and still fails as
         * encrypted — that code says something this one does not. The
         * id is 4, which is what StuffIt Deluxe 3.5.1 wrote for the
         * built-in scheme on the three archives it made here. */
        mlen = sit_synth(mod, "enc", 1, comp, sizeof comp, plain, sizeof plain);
        mod[22 + 1] = 0x81;
        mod[22 + 107] = 4;
        crc = unc_crc16_arc(0, mod + 22, 110);
        mod[22 + 110] = (uint8_t)(crc >> 8);
        mod[22 + 111] = (uint8_t)crc;
        test_make_memio(&io, &m, mod, mlen);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_SIT, &io, &sk, &al, NULL, NULL) == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_ENCRYPTED);
        CHECK(cap.info[0].module_kind == UNC_MODULE_ENCRYPTOR);
        CHECK(cap.info[0].module_id == 4);
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

static void put16le(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v & 0xFF);
    p[1] = (uint8_t)((v >> 8) & 0xFF);
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

    /* Concatenated members (RFC 1952): one entry whose data is the
     * concatenation of every member, each member's own trailer verified. */
    {
        uint8_t two[256];
        memcpy(two, arc, len);              /* member 1 */
        memcpy(two + len, arc, len);        /* member 2, identical */
        test_make_memio(&io, &m, two, len * 2u);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_GZIP, &io, &sk, &al, NULL, NULL)
              == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
        CHECK(cap.dlen[0] == 2u * n &&
              memcmp(cap.data[0], payload, n) == 0 &&
              memcmp(cap.data[0] + n, payload, n) == 0);
    }
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

    /* A member past the 32-bit reach is a PER-ENTRY refusal: the first
     * member still extracts, the big one is reported as an entry, and
     * the walk ends without declaring the archive corrupt. That the
     * member AFTER it is still read cannot be shown here — it lies
     * gigabytes away — and is what tools/run_sizelimits.py grades
     * against GNU tar. */
    memcpy(arc + 1024, arc, 512);
    memcpy(arc + 1024, "huge.bin\0\0\0\0\0", 13);
    snprintf((char *)arc + 1024 + 124, 12, "%011o", 0x80000000u);
    memset(arc + 1024 + 148, ' ', 8);
    sum = 0;
    for (i = 0; i < 512; i++) sum += arc[1024 + i];
    snprintf((char *)arc + 1024 + 148, 8, "%06o", sum);
    arc[1024 + 155] = ' ';

    test_make_memio(&io, &m, arc, sizeof arc);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_TAR, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 2);
    CHECK(cap.status[0] == UNC_OK && cap.dlen[0] == n);
    CHECK(cap.status[1] == UNC_ERR_TOOLARGE);
    CHECK(cap.info[1].data_size == UNC_SIZE_UNKNOWN);
    memset(arc + 1024, 0, 512);
}

/* One stored entry: LFH + data + central dir + EOCD, followed by
 * `cmtlen` bytes of ARCHIVE comment. `cdp` and `eop` come back with the
 * offsets of the central directory and of the EOCD, for a caller that
 * wants to spoil a field of either. `out` needs 256 bytes plus the
 * comment. */
#define ZIP_SYNTH_PAYLOAD "zip stored data"

static uint32_t zip_synth(uint8_t *out, const uint8_t *cmt, uint32_t cmtlen,
                          uint32_t *cdp, uint32_t *eop)
{
    static const char *payload = ZIP_SYNTH_PAYLOAD;
    static const char *name = "f.txt";
    uint32_t n = (uint32_t)strlen(payload), nl = (uint32_t)strlen(name);
    uint32_t crc, lfh = 0, cd, eocd;

    memset(out, 0, 256 + cmtlen);
    crc = unc_crc32(0xFFFFFFFFu, (const uint8_t *)payload, (int32_t)n)
          ^ 0xFFFFFFFFu;

    /* local file header */
    memcpy(out, "PK\x03\x04", 4);
    out[4] = 20;
    put32le(out + 14, crc);
    put32le(out + 18, n);
    put32le(out + 22, n);
    out[26] = (uint8_t)nl;
    memcpy(out + 30, name, nl);
    memcpy(out + 30 + nl, payload, n);
    cd = 30 + nl + n;

    memcpy(out + cd, "PK\x01\x02", 4);
    put32le(out + cd + 16, crc);
    put32le(out + cd + 20, n);
    put32le(out + cd + 24, n);
    out[cd + 28] = (uint8_t)nl;
    put32le(out + cd + 42, lfh);
    memcpy(out + cd + 46, name, nl);
    eocd = cd + 46 + nl;

    memcpy(out + eocd, "PK\x05\x06", 4);
    out[eocd + 8] = 1; out[eocd + 10] = 1;       /* entry counts */
    put32le(out + eocd + 12, eocd - cd);         /* cd size */
    put32le(out + eocd + 16, cd);                /* cd offset */
    put16le(out + eocd + 20, (uint16_t)cmtlen);  /* .ZIP file comment */
    if (cmtlen) memcpy(out + eocd + 22, cmt, cmtlen);

    if (cdp) *cdp = cd;
    if (eop) *eop = eocd;
    return eocd + 22 + cmtlen;
}

static void test_zip(void)
{
    static const char *payload = ZIP_SYNTH_PAYLOAD;
    static const char *name = "f.txt";
    uint8_t arc[256];
    uint32_t n = (uint32_t)strlen(payload), nl = (uint32_t)strlen(name);
    uint32_t cd, eocd, len;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    len = zip_synth(arc, NULL, 0, &cd, &eocd);
    (void)eocd;

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

/* A zip's end-of-central-directory comment, which the engine read past
 * and dropped until 2026-08-26. It leaves by the same sink callback
 * Compact Pro's does, and it is the reason that callback's length is no
 * longer bounded by 255: zip states it in two bytes, and the one corpus
 * archive that has one has 495 (FORMATS.md, *The archive comment*). */
static void test_zip_comment(void)
{
    uint8_t arc[256 + 512];
    uint8_t cmt[400];
    uint32_t i, cd, eocd, len;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    test_make_alloc(&al);

    /* Longer than a Compact Pro comment can be, with an 8-bit MacRoman
     * byte in it that no ASCII reading gets right, and a CR: neither is
     * rewritten on the way out. */
    for (i = 0; i < sizeof cmt; i++) cmt[i] = (uint8_t)('a' + i % 26);
    cmt[3] = 0xA5;
    cmt[7] = '\r';

    len = zip_synth(arc, cmt, sizeof cmt, &cd, &eocd);
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_ZIP);
    cap_make(&sk, &cap);
    /* cap_comment refuses a comment that arrives after an entry, so
     * reaching UNC_OK is the ordering check as well. */
    CHECK(unc_extract_as(UNC_FORMAT_ZIP, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.comments == 1);
    CHECK(cap.comment_len == sizeof cmt);
    CHECK(memcmp(cap.comment, cmt, sizeof cmt) == 0);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);

    /* A length that runs off the end of the file describes bytes that
     * are not there: no comment, and no failure either — the entries
     * are all still readable. (This grades the OUTCOME. The length
     * check in fmt_exo.c bounds the allocation rather than the result,
     * so removing it leaves this passing.) */
    put16le(arc + eocd + 20, 0xFFFFu);
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_ZIP, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.comments == 0);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);

    /* No comment at all: the sink must not be told about one. */
    len = zip_synth(arc, NULL, 0, &cd, &eocd);
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_ZIP, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.comments == 0);

    /* And a host with no comment callback is not a broken host: the
     * archive extracts exactly as it did before 2026-08-26. */
    len = zip_synth(arc, cmt, sizeof cmt, &cd, &eocd);
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    sk.comment = NULL;
    CHECK(unc_extract_as(UNC_FORMAT_ZIP, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.comments == 0);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == strlen(ZIP_SYNTH_PAYLOAD));
}

/* A zip BEHIND something else — a self-extracting archive, whose first
 * bytes are executable code. Nothing in the corpus is one and nothing
 * here can be: the five specimens ZipIt wrote are not committable
 * (fixtures/SOURCES.md), and `tools/run_zipit.py` grades those. What is
 * pinned here is the probe's reasoning, which no whole archive isolates:
 * the claim rests on the end-of-central-directory record alone, and each
 * of the five things that record has to agree with is bent in turn.
 *
 * The stub is a PEF container's first bytes — "Joy!peff" — because that
 * is what all five of those specimens begin with, measured 2026-10-05.
 * Its content is irrelevant to the engine, which never looks at it; what
 * matters is that the archive's offsets count from the start of the FILE
 * and not from the start of the zip, which is what Info-ZIP's `zip -A`
 * and ZipIt both write (FORMATS.md, *What the zip pair claims, and what
 * it costs*). */
#define ZIP_STUB_LEN 200u

static uint32_t zip_synth_behind_stub(uint8_t *out, uint32_t *cdp,
                                      uint32_t *eop)
{
    uint32_t cd, eocd, len;

    memset(out, 0, ZIP_STUB_LEN);
    memcpy(out, "Joy!peffpwpc", 12);
    len = zip_synth(out + ZIP_STUB_LEN, NULL, 0, &cd, &eocd);
    cd += ZIP_STUB_LEN;
    eocd += ZIP_STUB_LEN;
    /* The two offsets a stub displaces: "relative offset of local
     * header" (APPNOTE.TXT 4.4.16) and "offset of start of central
     * directory" (4.4.24). Both are from the start of the file. */
    put32le(out + cd + 42, 0 + ZIP_STUB_LEN);
    put32le(out + eocd + 16, cd);
    if (cdp) *cdp = cd;
    if (eop) *eop = eocd;
    return ZIP_STUB_LEN + len;
}

static void test_zip_behind_a_stub(void)
{
    static const char *payload = ZIP_SYNTH_PAYLOAD;
    uint8_t arc[256 + ZIP_STUB_LEN];
    uint32_t n = (uint32_t)strlen(payload);
    uint32_t cd, eocd, len;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    test_make_alloc(&al);
    len = zip_synth_behind_stub(arc, &cd, &eocd);

    /* Recognised with nothing forced, and extracted from the directory
     * the record points at. This is the whole of the 2026-10-05 change:
     * before it, the sniff of this buffer was UNC_FORMAT_UNKNOWN. */
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_ZIP);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_ZIP, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == n && memcmp(cap.data[0], payload, n) == 0);

    /* --- the five tests, one bend each ----------------------------- *
     * Each must take the claim away. A corroboration nothing can fail
     * is not one (CLAUDE.md), and four bytes of `PK\5\6` on their own
     * claimed five files of 8,364 that are not archives at all. */

    /* 1. the central file header is not where the record says. This is
     *    a stub glued in front of an archive whose offsets were never
     *    adjusted — the file cannot be read as a zip, and must not be
     *    claimed as one. */
    put32le(arc + eocd + 16, cd - ZIP_STUB_LEN);
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
    put32le(arc + eocd + 16, cd);

    /* 2. no entries: nothing to extract, and the count every walk is
     *    bounded by. */
    put16le(arc + eocd + 10, 0);
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
    put16le(arc + eocd + 10, 1);

    /* 3. more entries on this disk than in the whole directory. */
    put16le(arc + eocd + 8, 2);
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
    put16le(arc + eocd + 8, 1);

    /* 4. a directory too small to hold the entries it declares: a
     *    central file header is 46 bytes before its name (4.3.12). */
    put32le(arc + eocd + 12, 45);
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);

    /* 5. ...and one that does not fit in front of the record pointing
     *    at it. 0xFFFFFFFF is Zip64's escape (4.4.23), so this is also
     *    the test that the arithmetic cannot wrap. */
    put32le(arc + eocd + 12, 0xFFFFFFFFu);
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
    put32le(arc + eocd + 12, eocd - cd);

    /* Restored, it is claimed again — so the five checks above were
     * measuring the bend and not something they broke on the way. */
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_ZIP);

    /* --- a signature by chance, which is what the five files had ---- *
     * `PK\5\6` in a buffer that is not an archive, with the fields that
     * follow it being whatever was there. It must be claimed as neither
     * zip NOR zip segment: the segment half took exactly this on the
     * strength of a nonzero disk number until 2026-10-05 (BLOCKERS.md,
     * *Withdrawn claims*). Four shapes, because a chance record's disk
     * number is as likely to be nonzero as zero. */
    {
        static const uint16_t disk[4] = { 0, 1, 626, 0xFFFFu };
        unsigned k;
        for (k = 0; k < 4; k++) {
            uint8_t junk[600];
            uint32_t at = 400;
            unsigned j;
            for (j = 0; j < sizeof junk; j++)
                junk[j] = (uint8_t)(j * 37u + 11u);     /* not an archive */
            memcpy(junk + at, "PK\x05\x06", 4);
            put16le(junk + at + 4, disk[k]);
            test_make_memio(&io, &m, junk, sizeof junk);
            CHECK(unc_sniff(&io) != UNC_FORMAT_ZIP);
            CHECK(unc_sniff(&io) != UNC_FORMAT_ZIPSEG);
        }
    }
}

/* A Shrink entry that is nothing but partial clears ticks once per
 * clear — the zip peek's decode too, which until 2026-10-09 had no
 * progress state at all — and a Cancel inside the peek ends the archive
 * before the entry is begun. Each clear walks the table twice for 18
 * bits of input, so a crafted 100 KB stream is ~3 hours of a Mac Plus;
 * before this its only ticks were the reader's, ~17 minutes apart
 * (FORMATS.md, *Shrink*). 373 bytes here, which the reader alone never
 * ticks for: the counts below are 0 without the per-clear tick. */
#define SHR_TICK_OUT 131u
static long shr_ticks, shr_cancel_at;
static uint32_t shr_overrun;    /* the most `done` ever exceeded `total` */
static int shr_tick(void *ctx, uint32_t done, uint32_t total)
{
    (void)ctx;
    if (done > total && done - total > shr_overrun)
        shr_overrun = done - total;
    return ++shr_ticks != shr_cancel_at;
}

static uint32_t zip_shrink_clears(uint8_t *out, int zipit)
{
    static const char *name = "c";
    uint8_t *d = out + 31;                  /* past the local header */
    uint32_t acc = 0, bits = 0, n = 0, crc, cd, eocd, ex = zipit ? 18 : 0;
    uint8_t plain[SHR_TICK_OUT];
    int i;

    for (i = 0; i < 331; i++) {
        /* 'A', then 100 escapes of code 2 (partial clear), then 130
         * more 'A's: 131 bytes, because the peek skips an entry
         * shorter than a MacBinary header. Codes are 9 bits, LSB
         * first. */
        uint32_t code = i == 0 || i > 200 ? 65u : (i & 1) ? 256u : 2u;
        acc |= code << bits;
        bits += 9;
        while (bits >= 8) { d[n++] = (uint8_t)acc; acc >>= 8; bits -= 8; }
    }
    if (bits) d[n++] = (uint8_t)acc;
    memset(plain, 'A', sizeof plain);
    crc = unc_crc32(0xFFFFFFFFu, plain, SHR_TICK_OUT) ^ 0xFFFFFFFFu;

    memset(out, 0, 31);
    memcpy(out, "PK\x03\x04", 4);
    out[4] = 10;
    out[8] = 1;                             /* method 1, Shrink */
    put32le(out + 14, crc);
    put32le(out + 18, n);
    put32le(out + 22, SHR_TICK_OUT);
    out[26] = 1;
    out[30] = (uint8_t)name[0];

    cd = 31 + n;
    memset(out + cd, 0, 47 + ex + 22);
    memcpy(out + cd, "PK\x01\x02", 4);
    out[cd + 10] = 1;
    put32le(out + cd + 16, crc);
    put32le(out + cd + 20, n);
    put32le(out + cd + 24, SHR_TICK_OUT);
    out[cd + 28] = 1;
    out[cd + 30] = (uint8_t)ex;
    out[cd + 46] = (uint8_t)name[0];
    if (zipit) {
        /* APPNOTE.TXT 4.6.4: 'ZPIT', FnLen, FileName, fdType,
         * fdCreator. The entry is not MacBinary, so the peek decodes
         * it and says no — which is the decode being measured. */
        uint8_t *x = out + cd + 47;
        put16le(x, 0x2605);
        put16le(x + 2, 14);
        memcpy(x + 4, "ZPIT\x01" "cTEXTttxt", 14);
    }
    eocd = cd + 47 + ex;
    memcpy(out + eocd, "PK\x05\x06", 4);
    out[eocd + 8] = 1; out[eocd + 10] = 1;
    put32le(out + eocd + 12, eocd - cd);
    put32le(out + eocd + 16, cd);
    return eocd + 22;
}

static void test_zip_shrink_ticks(void)
{
    uint8_t arc[512], plain[SHR_TICK_OUT];
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    UncProgress pg;
    uint32_t len;
    int zipit;

    test_make_alloc(&al);
    memset(plain, 'A', sizeof plain);
    memset(&pg, 0, sizeof pg);
    pg.tick = shr_tick;
    for (zipit = 0; zipit < 2; zipit++) {
        len = zip_shrink_clears(arc, zipit);
        test_make_memio(&io, &m, arc, len);
        cap_make(&sk, &cap);
        shr_ticks = 0;
        shr_cancel_at = -1;
        shr_overrun = 0;
        CHECK(unc_extract_as(UNC_FORMAT_ZIP, &io, &sk, &al, &pg, NULL)
              == UNC_OK);
        /* The peek reads the entry once and the decode again; only one
         * of them may count toward the bar, or a ZipIt archive reads
         * 100 % halfway through (152 % here until 2026-10-09). */
        CHECK(shr_overrun == 0);
        CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
        CHECK(cap.dlen[0] == SHR_TICK_OUT &&
              memcmp(cap.data[0], plain, SHR_TICK_OUT) == 0);
        CHECK(shr_ticks >= (zipit ? 200 : 100));
    }
    /* Cancelled at the first tick, which is the peek's. */
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    shr_ticks = 0;
    shr_cancel_at = 1;
    CHECK(unc_extract_as(UNC_FORMAT_ZIP, &io, &sk, &al, &pg, NULL)
          == UNC_ERR_ABORTED);
    CHECK(cap.count == 0 && shr_ticks == 1);
}

/* Zip's Reduce (src/unc_reduce.c), on hand-built streams: every follower
 * set empty (256 six-bit zeros, 192 bytes), so each byte after them is
 * an 8-bit literal of stage 1, and stage 2 is what is tested. The wild
 * fixtures pin the zero window and the literal 144; a copy longer than
 * its distance and an index past a set's count are in no CRC-good entry,
 * so only these can fail on them (FORMATS.md, *Reduce*). */
static int red_out_len;
static uint8_t red_out[64];
static int red_put(void *ctx, const uint8_t *p, uint32_t n)
{
    (void)ctx;
    if (red_out_len + (int)n > (int)sizeof red_out) return UNC_ERR_CORRUPT;
    memcpy(red_out + red_out_len, p, n);
    red_out_len += (int)n;
    return UNC_OK;
}

static int red_run(const uint8_t *tail, uint32_t ntail, uint32_t usize)
{
    static uint8_t s[192 + 16], obuf[4096];
    UncBufIn in;
    UncAlloc al;
    uint32_t crc = UNC_CRC32_INIT;

    memset(s, 0, 192);
    memcpy(s + 192, tail, ntail);
    test_make_alloc(&al);
    unc_bufin_init_mem(&in, s, 192 + ntail);
    red_out_len = 0;
    return unc_reduce_decode(&al, &in, 1, usize, &crc, obuf, sizeof obuf,
                             red_put, NULL);
}

/* LSB-first bit writer for the follower-set streams below. */
static uint32_t red_bw_put(uint8_t *buf, uint32_t at, uint32_t v, int n)
{
    int k;
    for (k = 0; k < n; k++, at++)
        if ((v >> k) & 1u) buf[at >> 3] |= (uint8_t)(1u << (at & 7u));
    return at;
}

/* Set 0 (the one the first byte is coded against) holds 'x', 'y', 'z':
 * N = 3, so B(N) = 2 and an index of 3 can be SENT and names nothing. */
static int red_run_index(uint32_t index, uint8_t *got)
{
    static uint8_t s[256], obuf[4096];
    UncBufIn in;
    UncAlloc al;
    uint32_t at = 255u * 6u, crc = UNC_CRC32_INIT;   /* 255 empty sets */
    int r;

    memset(s, 0, sizeof s);
    at = red_bw_put(s, at, 3, 6);
    at = red_bw_put(s, at, 'x', 8);
    at = red_bw_put(s, at, 'y', 8);
    at = red_bw_put(s, at, 'z', 8);
    at = red_bw_put(s, at, 0, 1);                    /* "from the set" */
    at = red_bw_put(s, at, index, 2);
    test_make_alloc(&al);
    unc_bufin_init_mem(&in, s, (at + 7u) / 8u);
    red_out_len = 0;
    r = unc_reduce_decode(&al, &in, 1, 1, &crc, obuf, sizeof obuf,
                          red_put, NULL);
    *got = red_out_len ? red_out[0] : 0;
    return r;
}

static void test_zip_reduce_rules(void)
{
    /* Factor 1: V = 0x05 is length 5 + 3, and D = 7 a distance of 8,
     * which reaches 7 bytes before the start: zeros. */
    static const uint8_t back[] = { 'A', 144, 0x05, 7 };
    static const uint8_t lit[] = { 144, 0, 'B' };
    /* The same copy at distance 1: longer than its distance, so it
     * repeats the one byte before it (APPNOTE.TXT 5.2.5). */
    static const uint8_t over[] = { 'A', 144, 0x05, 0 };
    static const uint8_t run[] = { 'A', 'A', 'A', 'A', 'A', 'A', 'A', 'A', 'A' };
    static const uint8_t want[] = { 'A', 0, 0, 0, 0, 0, 0, 0, 'A' };

    CHECK(red_run(back, sizeof back, 9) == UNC_OK);
    CHECK(red_out_len == 9 && memcmp(red_out, want, 9) == 0);
    CHECK(red_run(lit, sizeof lit, 2) == UNC_OK);
    CHECK(red_out_len == 2 && red_out[0] == 144 && red_out[1] == 'B');
    CHECK(red_run(over, sizeof over, 9) == UNC_OK);
    CHECK(red_out_len == 9 && memcmp(red_out, run, 9) == 0);
    /* A stream that ends before `usize` is truncated, not padded. */
    CHECK(red_run(lit, sizeof lit, 3) == UNC_ERR_TRUNCATED);
    /* Index 2 is the set's third byte; index 3 is past its count, which
     * `ozur` turns into a 0 and this refuses. */
    {
        uint8_t got = 0;
        CHECK(red_run_index(2, &got) == UNC_OK && got == 'z');
        CHECK(red_run_index(3, &got) == UNC_ERR_CORRUPT);
    }
}

/* LZH/LHA, in scope since 2026-08-23. The corpus and lhasa's collection
 * cover the decoders (tools/run_lzh.py, fixtures/manifests); what a
 * whole archive cannot isolate is covered here: every method byte the
 * probe must accept and reject, the three header levels a hand-built
 * archive can carry, the per-entry CRC failure, and MacLHA's MacBinary
 * payload with a resource fork in it.
 *
 * Source: reference/XADMaster/XADLZHParser.m +recognizeFileWithHandle:,
 * which matches bytes[2..6] as "-lh?-" with ? in 0-7 or 'd', and "-lz?-"
 * with ? in 0, 4 or 5 — plus "-lzs-", which that recogniser omits and
 * its own parser can decode (fmt_lzh.c). Bytes 0 and 1 are the header
 * size and its checksum and are not part of the recognition. */
static void test_lzh_probe(void)
{
    uint8_t h[32];
    UncIO io;
    MemIO m;
    int i;
    static const char *ok_lh = "01234567d";
    static const char *ok_lz = "045s";
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
}

/* Build a level 0 or level 1 "-lh0-" (stored) entry into `out`, and
 * return its length. Level 1 adds the OS byte and an empty extended
 * header chain; both are what LHa itself writes. */
static uint32_t lzh_make_entry(uint8_t *out, int level, const char *name,
                               int os, const uint8_t *body, uint32_t blen)
{
    uint32_t nl = (uint32_t)strlen(name), i, at;
    uint32_t base = 22 + nl + 2 + (level == 1 ? 3u : 0u);
    uint16_t crc = unc_crc16_arc(0, body, (int32_t)blen);
    uint32_t sum = 0;

    for (i = 0; i < base; i++) out[i] = 0;
    out[0] = (uint8_t)(base - 2);
    out[2] = '-'; out[3] = 'l'; out[4] = 'h'; out[5] = '0'; out[6] = '-';
    out[7]  = (uint8_t)blen; out[8]  = (uint8_t)(blen >> 8);
    out[9]  = (uint8_t)(blen >> 16); out[10] = (uint8_t)(blen >> 24);
    out[11] = out[7]; out[12] = out[8]; out[13] = out[9]; out[14] = out[10];
    out[20] = (uint8_t)level;
    out[21] = (uint8_t)nl;
    for (i = 0; i < nl; i++) out[22 + i] = (uint8_t)name[i];
    out[22 + nl] = (uint8_t)crc;
    out[23 + nl] = (uint8_t)(crc >> 8);
    if (level == 1) out[24 + nl] = (uint8_t)os;   /* then a zero ext size */
    /* The checksum byte: every header byte from 2 on. Nothing in this
     * reader looks at it, which is exactly why the test sets it — a
     * future version that starts checking must not fail here. */
    for (i = 2; i < base; i++) sum += out[i];
    out[1] = (uint8_t)sum;
    at = base;
    for (i = 0; i < blen; i++) out[at + i] = body[i];
    return at + blen;
}

static void test_lzh_extract(void)
{
    static const uint8_t body[] = "hello, LHarc";
    uint8_t arc[1024];
    uint32_t n;
    UncIO io;
    MemIO m;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    /* Level 0, one stored entry. */
    n = lzh_make_entry(arc, 0, "hello.txt", 0, body, sizeof body - 1);
    arc[n++] = 0;                                  /* end-of-archive */
    test_make_memio(&io, &m, arc, n);
    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract(&io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1);
    CHECK(cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == sizeof body - 1);
    CHECK(memcmp(cap.data[0], body, sizeof body - 1) == 0);
    CHECK(strcmp((char *)cap.info[0].name, "hello.txt") == 0);

    /* A wrong CRC is a per-entry error and not a dead archive. */
    n = lzh_make_entry(arc, 0, "hello.txt", 0, body, sizeof body - 1);
    arc[22 + 9] ^= 0xFF;
    arc[n++] = 0;
    test_make_memio(&io, &m, arc, n);
    cap_make(&sk, &cap);
    CHECK(unc_extract(&io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1);
    CHECK(cap.status[0] == UNC_ERR_CRC);

    /* Level 1: the same entry, with an OS byte and an empty extended
     * header chain the walk has to step over to find the data. */
    n = lzh_make_entry(arc, 1, "hello.txt", 'U', body, sizeof body - 1);
    arc[n++] = 0;
    test_make_memio(&io, &m, arc, n);
    cap_make(&sk, &cap);
    CHECK(unc_extract(&io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1);
    CHECK(cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == sizeof body - 1);
    CHECK(memcmp(cap.data[0], body, sizeof body - 1) == 0);

    /* MacLHA: OS byte 'm' and a MacBinary stream as the payload, so the
     * entry's forks, name, type and creator come from the Mac header
     * and not from the LZH one. The resource fork is the half no
     * `.lzh` fixture in the corpus carries. */
    {
        static const uint8_t dfork[] = "data fork bytes";
        static const uint8_t rfork[] = "RSRC";
        uint8_t mb[128 + 128 + 128];
        uint32_t dlen = sizeof dfork - 1, rlen = sizeof rfork - 1, i;
        uint16_t hcrc;

        for (i = 0; i < sizeof mb; i++) mb[i] = 0;
        mb[1] = 6;
        memcpy(mb + 2, "Mac It", 6);
        memcpy(mb + 65, "TEXTttxt", 8);
        mb[83 + 3] = (uint8_t)dlen;
        mb[87 + 3] = (uint8_t)rlen;
        unc_put_u32be(mb + 91, 0x11223344u);       /* creation date */
        unc_put_u32be(mb + 95, 0x55667788u);       /* modification   */
        hcrc = unc_crc16_xmodem(0, mb, 124);
        mb[124] = (uint8_t)(hcrc >> 8);
        mb[125] = (uint8_t)hcrc;
        memcpy(mb + 128, dfork, dlen);
        memcpy(mb + 256, rfork, rlen);

        n = lzh_make_entry(arc, 1, "macfile", 'm', mb, sizeof mb);
        arc[n++] = 0;
        test_make_memio(&io, &m, arc, n);
        cap_make(&sk, &cap);
        CHECK(unc_extract(&io, &sk, &al, NULL, NULL) == UNC_OK);
        CHECK(cap.count == 1);
        CHECK(cap.status[0] == UNC_OK);
        CHECK(cap.info[0].type == 0x54455854u);    /* 'TEXT' */
        CHECK(cap.info[0].creator == 0x74747874u); /* 'ttxt' */
        CHECK(cap.info[0].create_date == 0x11223344u);
        CHECK(cap.info[0].mod_date == 0x55667788u);
        CHECK(cap.dlen[0] == dlen);
        CHECK(cap.rlen[0] == rlen);
        CHECK(memcmp(cap.data[0], dfork, dlen) == 0);
        CHECK(memcmp(cap.rsrc[0], rfork, rlen) == 0);
        /* The name stays the LZH one: MacLHA writes the same name into
         * both headers, and the oracle reports the archive's. */
        CHECK(strcmp((char *)cap.info[0].name, "macfile") == 0);

        /* MacLHA 2.00's shape: a MacBinary I header with BOTH DATES
         * ZERO, which XADMaster's probe refuses (it requires them
         * non-zero) and lhasa refuses too (it wants the modification
         * date to match the LZH header's). The fallback accepts it on
         * arithmetic instead — the name matches the entry's, and the
         * two padded fork lengths plus the header come to exactly the
         * uncompressed size. Measured on an archive MacLHA 2.00 wrote
         * under Mini vMac (tools/vmac/maclha.py). */
        {
            uint8_t old124 = mb[124], old125 = mb[125];
            unc_put_u32be(mb + 91, 0);
            unc_put_u32be(mb + 95, 0);
            mb[124] = mb[125] = 0;                 /* no MacBinary II CRC */
            CHECK(unc_macbinary_probe(mb, 128, 0) == 0);   /* both refuse */
            n = lzh_make_entry(arc, 1, "Mac It", 'm', mb, sizeof mb);
            arc[n++] = 0;
            test_make_memio(&io, &m, arc, n);
            cap_make(&sk, &cap);
            CHECK(unc_extract(&io, &sk, &al, NULL, NULL) == UNC_OK);
            CHECK(cap.count == 1);
            CHECK(cap.dlen[0] == dlen);
            CHECK(cap.rlen[0] == rlen);
            CHECK(memcmp(cap.rsrc[0], rfork, rlen) == 0);

            /* The name has to be the entry's, or it is not this shape:
             * the same bytes under a different entry name are one
             * file again. */
            n = lzh_make_entry(arc, 1, "Other", 'm', mb, sizeof mb);
            arc[n++] = 0;
            test_make_memio(&io, &m, arc, n);
            cap_make(&sk, &cap);
            CHECK(unc_extract(&io, &sk, &al, NULL, NULL) == UNC_OK);
            CHECK(cap.dlen[0] == sizeof mb);
            CHECK(cap.rlen[0] == 0);

            /* And so does the arithmetic: one byte more of payload and
             * the lengths no longer add up. */
            n = lzh_make_entry(arc, 1, "Mac It", 'm', mb, sizeof mb - 1);
            arc[n++] = 0;
            test_make_memio(&io, &m, arc, n);
            cap_make(&sk, &cap);
            CHECK(unc_extract(&io, &sk, &al, NULL, NULL) == UNC_OK);
            CHECK(cap.dlen[0] == sizeof mb - 1);
            CHECK(cap.rlen[0] == 0);

            mb[124] = old124;
            mb[125] = old125;
            unc_put_u32be(mb + 91, 0x11223344u);
            unc_put_u32be(mb + 95, 0x55667788u);
        }

        /* The same bytes under any other OS byte are NOT unwrapped —
         * one file, MacBinary header and padding included, which is
         * what `unar` does with MacLHA's own level 0 archives. */
        n = lzh_make_entry(arc, 1, "macfile", 'U', mb, sizeof mb);
        arc[n++] = 0;
        test_make_memio(&io, &m, arc, n);
        cap_make(&sk, &cap);
        CHECK(unc_extract(&io, &sk, &al, NULL, NULL) == UNC_OK);
        CHECK(cap.count == 1);
        CHECK(cap.dlen[0] == sizeof mb);
        CHECK(cap.rlen[0] == 0);
        CHECK(cap.info[0].type == 0);
    }

    /* A method with no decoder is a per-entry refusal, not a broken
     * archive. This asked about -lh2- until 2026-08-25 and then -lh3-,
     * and both landed the same day, each time failing this check —
     * correctly, because its premise had changed.
     *
     * It now uses -lz0-, and the choice is deliberate: a method that does
     * not exist at all (-lh9-) is rejected by the PROBE, so the archive
     * stops being an archive and the per-entry contract is never reached.
     * -lz0- is what the probe accepts and nothing decodes — XADMaster's
     * recogniser takes it while its own parser has no case for it, and
     * this probe copies that recogniser deliberately
     * (unc_lzh_probe's comment). */
    n = lzh_make_entry(arc, 0, "old.txt", 0, body, sizeof body - 1);
    arc[4] = 'z';
    arc[5] = '0';
    arc[n++] = 0;
    test_make_memio(&io, &m, arc, n);
    cap_make(&sk, &cap);
    CHECK(unc_extract(&io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1);
    CHECK(cap.status[0] == UNC_ERR_UNSUPPORTED);
    CHECK(cap.dlen[0] == 0);
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

/* Big-endian, for the resource fork below. */
static void put16be(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 8);
    p[1] = (uint8_t)v;
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
        CHECK(unc_sitseg_probe(other, UNC_SEG_HEAD, NULL) == 0);

        /* What StuffIt itself writes (2026-10-24): the first two bytes
         * a per-set value, not XADMaster's B0 56 — 41 A7 is what StuffIt
         * Lite 3.0.5 and InstallerMaker 2.0 wrote — and the running CRC
         * at 98.
         * Refused until then; every B0 56 part here was our own. */
        seg_head(other, 2, "Thing.sit", 100, 200, 0x11223344u);
        other[0] = 0x41; other[1] = 0xA7;
        other[94] = 0x03; other[95] = 0x62;     /* varies by part */
        other[98] = 0x19; other[99] = 0x40;     /* the running CRC */
        CHECK(unc_sitseg_probe(other, UNC_SEG_HEAD, NULL) == UNC_FORMAT_SITSEG);
        CHECK(unc_segment_match(&desc, other, UNC_SEG_HEAD) == 2);
        /* ...and what stands in for the two bytes: 96 and 97 zero, ... */
        other[96] = 0x01;
        CHECK(unc_sitseg_probe(other, UNC_SEG_HEAD, NULL) == 0);
        other[96] = 0x00; other[97] = 0x01;
        CHECK(unc_sitseg_probe(other, UNC_SEG_HEAD, NULL) == 0);
        other[97] = 0x00;
        /* ...byte 2 zero, ... */
        other[2] = 0x01;
        CHECK(unc_sitseg_probe(other, UNC_SEG_HEAD, NULL) == 0);
        other[2] = 0x00;
        /* ...and forks that are sizes: none at all, or past 2 GB. */
        seg_head(other, 2, "Thing.sit", 0, 0, 0x11223344u);
        CHECK(unc_sitseg_probe(other, UNC_SEG_HEAD, NULL) == 0);
        seg_head(other, 2, "Thing.sit", 0x80000000u, 200, 0x11223344u);
        CHECK(unc_sitseg_probe(other, UNC_SEG_HEAD, NULL) == 0);
    }

    /* --- a part whose payload outgrows the whole it is part of ------ */
    {
        uint8_t big[UNC_SEG_HEAD + 400];
        MemIO bm;
        UncIO bio;
        memset(big, 0x5A, sizeof big);
        seg_head(big, 1, "Thing.sit", 100, 200, 0x11223344u);
        test_make_memio(&bio, &bm, big, sizeof big);     /* 400 > 300 */
        CHECK(unc_sitseg_probe(big, UNC_SEG_HEAD, &bio) == 0);
        test_make_memio(&bio, &bm, big, UNC_SEG_HEAD + 300);  /* exact */
        CHECK(unc_sitseg_probe(big, UNC_SEG_HEAD, &bio) == UNC_FORMAT_SITSEG);
    }

    /* --- a fat installer's part 1: its resource fork's 'endD' ------- */
    /* A fork of two types, 'ICN#' then 'endD', each with one ID-0
     * reference; the data area holds an 8-byte icon stand-in and the
     * four-byte 'endD' (Inside Macintosh: More Macintosh Toolbox,
     * "Resource File Format"). */
    {
        uint8_t rf[16 + 20 + 28 + 2 + 16 + 24];
        MemIO rm;
        UncIO rio;
        UncSegmentDesc other = desc;
        const uint32_t mapoff = 16 + 20, tl = mapoff + 28;
        memset(rf, 0, sizeof rf);
        unc_put_u32be(rf + 0, 16);                    /* data area */
        unc_put_u32be(rf + 4, mapoff);
        unc_put_u32be(rf + 8, 20);
        unc_put_u32be(rf + 12, (uint32_t)sizeof rf - mapoff);
        unc_put_u32be(rf + 16, 8);                    /* 'ICN#' 0, 8 B */
        unc_put_u32be(rf + 28, 4);                    /* 'endD' 0, 4 B */
        unc_put_u32be(rf + 32, 1132983);
        put16be(rf + mapoff + 24, 28);                /* type list */
        put16be(rf + tl, 1);                          /* two types */
        memcpy(rf + tl + 2, "ICN#", 4);
        put16be(rf + tl + 8, 18);                     /* refs at tl+18 */
        memcpy(rf + tl + 10, "endD", 4);
        put16be(rf + tl + 16, 30);                    /* refs at tl+30 */
        unc_put_u32be(rf + tl + 18 + 4, 0);           /* ICN# at data+0 */
        unc_put_u32be(rf + tl + 30 + 4, 12);          /* endD at data+12 */
        test_make_memio(&rio, &rm, rf, sizeof rf);
        CHECK(unc_segment_first_end(&desc, &rio, 1189189) == 1132983);
        /* No fork, a fork without it, or a value that is not inside
         * the data fork: the fork's own length. */
        CHECK(unc_segment_first_end(&desc, NULL, 1189189) == 1189189);
        CHECK(unc_segment_first_end(&desc, &rio, 1132983) == 1132983);
        CHECK(unc_segment_first_end(&desc, &rio, 1000) == 1000);
        memcpy(rf + tl + 10, "endd", 4);
        test_make_memio(&rio, &rm, rf, sizeof rf);
        CHECK(unc_segment_first_end(&desc, &rio, 1189189) == 1189189);
        memcpy(rf + tl + 10, "endD", 4);
        unc_put_u32be(rf + 28, 5);                    /* not four bytes */
        test_make_memio(&rio, &rm, rf, sizeof rf);
        CHECK(unc_segment_first_end(&desc, &rio, 1189189) == 1189189);
        unc_put_u32be(rf + 28, 4);
        unc_put_u32be(rf + 32, UNC_SEG_HEAD);         /* no payload */
        test_make_memio(&rio, &rm, rf, sizeof rf);
        CHECK(unc_segment_first_end(&desc, &rio, 1189189) == 1189189);
        unc_put_u32be(rf + 32, 1132983);
        put16be(rf + tl + 30, 1);                     /* ID 1, not 0 */
        test_make_memio(&rio, &rm, rf, sizeof rf);
        CHECK(unc_segment_first_end(&desc, &rio, 1189189) == 1189189);
        put16be(rf + tl + 30, 0);
        /* A truncated fork, and another scheme's set. */
        test_make_memio(&rio, &rm, rf, (uint32_t)sizeof rf - 12);
        CHECK(unc_segment_first_end(&desc, &rio, 1189189) == 1189189);
        other.scheme = UNC_FORMAT_SPLIT;
        test_make_memio(&rio, &rm, rf, sizeof rf);
        CHECK(unc_segment_first_end(&other, &rio, 1189189) == 1189189);
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
    /* Both entry counts, both bytes each. They were a single byte apiece
     * until 2026-10-05 and read as 1 only because two of the three
     * callers hand this a zeroed buffer; the third fills with 0xAA and
     * was declaring 43,521 entries in a 47-byte directory. */
    put16le(buf + eocd + 8, 1);                  /* entries on this disk */
    put16le(buf + eocd + 10, 1);                 /* entries altogether   */
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
     * Multi-chunk forks are real — the 3.1.2 distribution disk has forks
     * of up to EIGHT chunks and 97,906 bytes, and they decode as one
     * continuous bit stream (DECISIONS.md 2026-08-21, the Salient disk). */
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

    memset(&opt, 0, sizeof opt);   /* the whole struct: a field this list
                                     * does not name is stack garbage otherwise
                                     * (DECISIONS.md 2026-09-04) */
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


/* ------------------------------------------------------------------ */
/* Method 2: splay-tree Huffman with one tree per preceding byte.      */
/* The only specimen reachable is 564 bytes on Salient's 3.1.2 disk    */
/* (tools/vmac/ndd.py --specimens), so what the fixtures cannot see is */
/* written by hand here: several contexts, and enough repetition that  */
/* the splay step actually shortens a code. The encoder below is OURS, */
/* so this grades the transcription against the reference rather than  */
/* against the format; the specimen is what grades it against the      */
/* format.                                                             */
/* ------------------------------------------------------------------ */

typedef struct M2Tree {
    uint16_t left[256], right[256];
    uint8_t  parent[512];
} M2Tree;

static void m2_init(M2Tree *t)
{
    int j;
    for (j = 0; j < 256; j++) {
        t->left[j]  = (uint16_t)(j * 2);
        t->right[j] = (uint16_t)(j * 2 + 1);
        t->parent[j * 2] = (uint8_t)j;
        t->parent[j * 2 + 1] = (uint8_t)j;
    }
}

/* The same rotation the decoder performs, so encoder and decoder stay
 * in step; if they did not, nothing would come back. */
static void m2_splay(M2Tree *t, int byte)
{
    int node = byte + 0x100;
    for (;;) {
        int parent = t->parent[node], grand, uncle;
        if (parent == 1) break;
        grand = t->parent[parent];
        uncle = t->left[grand];
        if (uncle == parent) { uncle = t->right[grand]; t->right[grand] = (uint16_t)node; }
        else                 { t->left[grand] = (uint16_t)node; }
        if (t->left[parent] != node) t->right[parent] = (uint16_t)uncle;
        else                         t->left[parent]  = (uint16_t)uncle;
        t->parent[node] = (uint8_t)grand;
        t->parent[uncle] = (uint8_t)parent;
        node = grand;
        if (node == 1) break;
    }
}

typedef struct M2Bits { uint8_t *p; uint32_t len; int nbits; uint32_t acc; } M2Bits;

static void m2_put(M2Bits *b, uint32_t v, int n)
{
    b->acc = (b->acc << n) | (v & ((1u << n) - 1u));
    b->nbits += n;
    while (b->nbits >= 8) {
        b->nbits -= 8;
        b->p[b->len++] = (uint8_t)(b->acc >> b->nbits);
    }
}

static void m2_flush(M2Bits *b)
{
    if (b->nbits) m2_put(b, 0, 8 - b->nbits);
}

/* Walk leaf -> root recording each step, then emit root -> leaf. */
static void m2_emit(M2Bits *b, M2Tree *t, int byte)
{
    uint8_t dir[32];
    int node = byte + 0x100, n = 0, i;
    while (node != 1) {
        int parent = t->parent[node];
        dir[n++] = (uint8_t)(t->right[parent] == node ? 1 : 0);
        node = parent;
    }
    for (i = n - 1; i >= 0; i--) m2_put(b, dir[i], 1);
}

static void test_dd_method2(void)
{
    /* Repeats so that a context is revisited after its tree has moved,
     * and distinct enough that several trees exist at once. */
    static const char text[] =
        "abracadabra abracadabra abracadabra banana bandana bandanna "
        "abracadabra abracadabra banana banana banana";
    const uint32_t NTEXT = (uint32_t)(sizeof text - 1);
    uint8_t one[4096], want[256];
    M2Tree *trees;
    M2Bits b;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    UncOptions opt;
    uint32_t n, i, sum = 0;
    int ctx = 0;
    static const uint8_t hint[] = "M2";

    CHECK(NTEXT <= sizeof want);
    /* info1 >= 0x2a with info2's high bit clear, so the DECODED bytes
     * are XORed with 0x5a — the same condition method 1 uses. */
    for (i = 0; i < NTEXT; i++) {
        want[i] = (uint8_t)(text[i] ^ 0x5A);
        sum = (sum + want[i]) & 0xFFFFu;
    }

    trees = (M2Tree *)malloc(256 * sizeof *trees);
    CHECK(trees != NULL);
    for (i = 0; i < 256; i++) m2_init(&trees[i]);

    for (n = 0; n < 84; n++) one[n] = 0;
    one[0] = 0xAB; one[1] = 0xCD; one[2] = 0x00; one[3] = 0x54;
    put32(one + 4, NTEXT);                     /* datasize */
    one[20] = 2; one[21] = 0;                  /* data method 2, no rsrc */
    one[22] = 0x2A;                            /* info1: the XOR applies */
    memcpy(one + 32, "TEXT", 4);
    memcpy(one + 36, "ttxt", 4);
    one[48] = (uint8_t)(sum >> 8); one[49] = (uint8_t)sum;
    one[52] = 0;                               /* info2 */

    b.p = one + 84; b.len = 0; b.nbits = 0; b.acc = 0;
    for (i = 0; i < NTEXT; i++) {
        int byte = (int)(uint8_t)text[i];      /* pre-XOR: what is coded */
        m2_emit(&b, &trees[ctx], byte);
        m2_splay(&trees[ctx], byte);
        ctx = byte;
    }
    m2_flush(&b);
    n = 84 + b.len;
    put32(one + 8, b.len);                     /* datacomp */
    free(trees);

    memset(&opt, 0, sizeof opt);   /* the whole struct: a field this list
                                     * does not name is stack garbage otherwise
                                     * (DECISIONS.md 2026-09-04) */
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
    CHECK(cap.dlen[0] == NTEXT);
    CHECK(memcmp(cap.data[0], want, NTEXT) == 0);

    /* It can fail: one bit of the stored sum must reject the fork. */
    one[49] ^= 0x01;
    test_make_memio(&io, &m, one, n);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_DISKDOUBLER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_CRC);
    one[49] ^= 0x01;
}


/* ------------------------------------------------------------------ */
/* Methods 3, 4 and 5. No specimen of any of them exists; what grades  */
/* them against the FORMAT is Salient's own 1991 expander, which turned */
/* streams from these same encoders back into the bytes that went in    */
/* (tools/vmac/ddencode.py --expand; DECISIONS.md, methods 3, 4 and 5). */
/* These vectors are that encoder's output, frozen, so the C decoder    */
/* has a regression test the emulator does not have to be booted for.   */
/* ------------------------------------------------------------------ */

static const uint8_t m345_subject[] = {
    0x61, 0x61, 0x61, 0x61, 0x61, 0x61, 0x61, 0x61, 0x61, 0x61, 0x90, 0x90,
    0x62, 0x63, 0x64, 0x62, 0x63, 0x64, 0x62, 0x63, 0x64, 0x7A, 0x7A, 0x7A,
    0x7A, 0x7A, 0x7A, 0x7A, 0x7A, 0x7A, 0x7A, 0x7A, 0x7A, 0x7A, 0x7A, 0x7A,
    0x7A, 0x7A, 0x7A, 0x7A, 0x7A, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06,
    0x07, 0x65, 0x6E, 0x64, 0x2E
};

/* RLE90 on 0x90: a run of ten, an escaped literal 0x90 twice, a run of
 * twenty, and bytes that must pass through untouched. No 0x5a XOR. */
static const uint8_t m3_stream[] = {
    0x61, 0x90, 0x0A, 0x90, 0x00, 0x90, 0x00, 0x62, 0x63, 0x64, 0x62, 0x63,
    0x64, 0x62, 0x63, 0x64, 0x7A, 0x90, 0x14, 0x00, 0x01, 0x02, 0x03, 0x04,
    0x05, 0x06, 0x07, 0x65, 0x6E, 0x64, 0x2E
};

/* StuffIt's bit-serialized Huffman tree, then the codes. No 0x5a XOR. */
static const uint8_t m4_stream[] = {
    0x5E, 0x85, 0x8A, 0xC6, 0x20, 0x50, 0x34, 0x12, 0x0A, 0x41, 0xA0, 0xE9,
    0x75, 0x94, 0xB2, 0x32, 0x0B, 0x72, 0x01, 0x01, 0xB0, 0xFF, 0xFF, 0xFF,
    0xFF, 0xAD, 0x44, 0xE4, 0x4E, 0x44, 0xE0, 0x00, 0x00, 0x6E, 0xDF, 0x45,
    0x35, 0x57, 0x65, 0xB7, 0xED, 0x97, 0x00
};

/* A leading tree count of 0, meaning 256 — the only value either
 * expander accepted — then method 2's splay stream. The 0x5a XOR DOES
 * apply here, which is the difference from 3 and 4 that cost a run to
 * find. */
static const uint8_t m5_stream[] = {
    0x00, 0x3B, 0x3B, 0x87, 0xF4, 0x95, 0x95, 0xB8, 0x39, 0x3E, 0x38, 0x98,
    0x95, 0xC0, 0x41, 0x67, 0xFF, 0xF8, 0xB4, 0xB6, 0xB0, 0xB2, 0xBC, 0xBE,
    0xB8, 0xBA, 0x7E, 0x68, 0x7D, 0xBA, 0x00
};

static void dd_one_method(int method, const uint8_t *stream, uint32_t slen)
{
    uint8_t one[256];
    uint32_t n, i, sum = 0;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    UncOptions opt;
    static const uint8_t hint[] = "M345";

    for (i = 0; i < sizeof m345_subject; i++)
        sum = (sum + m345_subject[i]) & 0xFFFFu;

    for (n = 0; n < 84; n++) one[n] = 0;
    one[0] = 0xAB; one[1] = 0xCD; one[2] = 0x00; one[3] = 0x54;
    put32(one + 4, (uint32_t)sizeof m345_subject);
    put32(one + 8, slen);
    one[20] = (uint8_t)method; one[21] = 0;
    one[22] = 0x2A;                            /* info1: the XOR rule fires */
    memcpy(one + 32, "TEXT", 4);
    memcpy(one + 36, "ttxt", 4);
    one[48] = (uint8_t)(sum >> 8); one[49] = (uint8_t)sum;
    memcpy(one + 84, stream, slen);
    n = 84 + slen;

    memset(&opt, 0, sizeof opt);   /* the whole struct: a field this list
                                     * does not name is stack garbage otherwise
                                     * (DECISIONS.md 2026-09-04) */
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
    CHECK(cap.dlen[0] == sizeof m345_subject);
    CHECK(memcmp(cap.data[0], m345_subject, sizeof m345_subject) == 0);

    /* It can fail: one bit of the stored sum must reject the fork. */
    one[49] ^= 0x01;
    test_make_memio(&io, &m, one, n);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_DISKDOUBLER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_CRC);
}

static void test_dd_methods345(void)
{
    dd_one_method(3, m3_stream, (uint32_t)sizeof m3_stream);
    dd_one_method(4, m4_stream, (uint32_t)sizeof m4_stream);
    dd_one_method(5, m5_stream, (uint32_t)sizeof m5_stream);
}


/* ------------------------------------------------------------------ */
/* The 'DDA2' archive walk: a folder, a file with its own 0xABCD0054   */
/* header, and one stored in the archive with none — which is what     */
/* DiskDoubler Pro writes for a file it could not shrink, and what the */
/* reference raises on. Derived from ssokolow/diskdoubler-test-files   */
/* (DECISIONS.md 2026-08-21).                                          */
/* ------------------------------------------------------------------ */

/* The first 46 bytes of a record, common to all three kinds. */
static void dda2_rec(uint8_t *p, uint32_t reclen, uint16_t type,
                     const char *name, uint32_t dirlevel, uint32_t totalsize)
{
    uint32_t nl = (uint32_t)strlen(name), i;
    for (i = 0; i < reclen; i++) p[i] = 0;
    memcpy(p, "DDA2", 4);
    p[4] = (uint8_t)(type >> 8); p[5] = (uint8_t)type;
    p[6] = (uint8_t)nl;
    memcpy(p + 7, name, nl);
    put32(p + 38, dirlevel + 2u);
    put32(p + 42, totalsize);
}

static void test_dd_archive2(void)
{
    uint8_t arc[1024];
    uint32_t len, i, folder, stored;
    uint16_t crc;
    uint8_t dx = 0, rx = 0;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    static const char dat[] = "plain";
    static const char rsc[] = "RSC";

    for (i = 0; i < 5; i++) dx ^= (uint8_t)dat[i];
    for (i = 0; i < 3; i++) rx ^= (uint8_t)rsc[i];

    /* Archive header: 'DDA2' + 58 bytes, CRC-16/XMODEM over the first 60. */
    for (i = 0; i < 62; i++) arc[i] = 0;
    memcpy(arc, "DDA2", 4);
    crc = unc_crc16_xmodem(0, arc, 60);
    arc[60] = (uint8_t)(crc >> 8); arc[61] = (uint8_t)crc;
    len = 62;

    /* A folder at level 0, whose dates live at +54 and +58 — past the 46
     * bytes the walk reads first, so a walk that does not read them again
     * reports whatever was in its buffer. */
    folder = len;
    dda2_rec(arc + len, 88, 0x9000, "folder", 0, 88);
    put32(arc + len + 54, 0xE01AF53Eu);   /* creation     */
    put32(arc + len + 58, 0xE01AF54Eu);   /* modification */
    len += 88;

    /* A file at level 1 stored in the archive: 90-byte record header,
     * then the two raw forks. */
    stored = len;
    dda2_rec(arc + len, 90, 0x1000, "raw.bin", 1, 90 + 5 + 3);
    put32(arc + len + 62, 0x4A504547u);   /* 'JPEG' */
    put32(arc + len + 66, 0x474B4F4Eu);   /* 'GKON' */
    arc[len + 70] = 0x01;                 /* finder flags 0x0100 */
    put32(arc + len + 78, 5);             /* datasize */
    put32(arc + len + 82, 3);             /* rsrcsize */
    arc[len + 86] = dx;
    arc[len + 87] = rx;
    len += 90;
    memcpy(arc + len, dat, 5); len += 5;
    memcpy(arc + len, rsc, 3); len += 3;

    /* A file at level 1 with a header of its own at +56. */
    dda2_rec(arc + len, 56, 0x5000, "own.txt", 1, 56 + 84 + 5 + 3);
    len += 56;
    for (i = 0; i < 84; i++) arc[len + i] = 0;
    arc[len] = 0xAB; arc[len + 1] = 0xCD; arc[len + 2] = 0x00; arc[len + 3] = 0x54;
    put32(arc + len + 4, 5);              /* datasize */
    put32(arc + len + 8, 5);              /* datacomp */
    put32(arc + len + 12, 3);             /* rsrcsize */
    put32(arc + len + 16, 3);             /* rsrccomp */
    memcpy(arc + len + 32, "TEXT", 4);
    memcpy(arc + len + 36, "ttxt", 4);
    len += 84;
    memcpy(arc + len, dat, 5); len += 5;
    memcpy(arc + len, rsc, 3); len += 3;

    /* End of archive. */
    dda2_rec(arc + len, 46, 0xBBBB, "", 1, 46);
    len += 46;

    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DISKDOUBLER);

    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_DISKDOUBLER, &io, &sk, &al, NULL, NULL)
          == UNC_OK);
    CHECK(cap.count == 3);
    CHECK(cap.info[0].is_dir == 1);
    CHECK(cap.info[0].name_len == 6 && memcmp(cap.info[0].name, "folder", 6) == 0);
    CHECK(cap.info[0].create_date == 0xE01AF53Eu);
    CHECK(cap.info[0].mod_date == 0xE01AF54Eu);

    CHECK(cap.info[1].name_len == 14 &&
          memcmp(cap.info[1].name, "folder/raw.bin", 14) == 0);
    CHECK(cap.status[1] == UNC_OK);
    CHECK(cap.info[1].type == 0x4A504547u);
    CHECK(cap.info[1].creator == 0x474B4F4Eu);
    CHECK(cap.info[1].finder_flags == 0x0100);
    CHECK(cap.dlen[1] == 5 && memcmp(cap.data[1], dat, 5) == 0);
    CHECK(cap.rlen[1] == 3 && memcmp(cap.rsrc[1], rsc, 3) == 0);

    CHECK(cap.info[2].name_len == 14 &&
          memcmp(cap.info[2].name, "folder/own.txt", 14) == 0);
    CHECK(cap.status[2] == UNC_OK);
    CHECK(cap.info[2].type == 0x54455854u);   /* 'TEXT' */
    CHECK(cap.dlen[2] == 5 && memcmp(cap.data[2], dat, 5) == 0);

    /* The stored record's XOR of each fork is checked, and can fail:
     * one wrong bit in the data fork's is a per-entry CRC error, and the
     * entries around it still come out. */
    arc[stored + 86] ^= 0x01;
    test_make_memio(&io, &m, arc, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_DISKDOUBLER, &io, &sk, &al, NULL, NULL)
          == UNC_OK);
    CHECK(cap.count == 3);
    CHECK(cap.status[1] == UNC_ERR_CRC);
    CHECK(cap.status[2] == UNC_OK);
    arc[stored + 86] ^= 0x01;
    (void)folder;
}


/* ------------------------------------------------------------------ */
/* DiskDoubler `SPLT`: the part header, and the set of one            */
/*                                                                    */
/* The joined sets live in tools/run_segments.py and the real          */
/* specimens in tools/run_ddtf.py. What is here is what neither can    */
/* reach cheaply: the four ways a header is refused, and the lone-part */
/* path, which is the only one that runs without a volume source.      */
/* ------------------------------------------------------------------ */

static uint32_t ddseg_head(uint8_t *p, uint32_t datalen, uint32_t rsrclen,
                           int index, int nparts, uint32_t paylen)
{
    uint32_t i;
    for (i = 0; i < UNC_DDSEG_HEAD; i++) p[i] = 0;
    memcpy(p, "SPLT", 4);
    put32(p + 4, 0x0009BE6u);              /* set identity */
    put32(p + 8, datalen);
    put32(p + 12, rsrclen);
    memcpy(p + 16, "DDA2", 4);
    memcpy(p + 20, "DDAP", 4);
    p[24] = 0x01;                          /* finder flags 0x0100 */
    put32(p + 32, 0xE0364FA6u);            /* modification */
    put32(p + 36, 0xE0364F79u);            /* creation     */
    p[41] = (uint8_t)nparts;
    p[43] = (uint8_t)index;
    put32(p + 44, paylen);
    memcpy(p + 90, "SPLT", 4);
    return UNC_DDSEG_HEAD;
}

static void test_ddseg(void)
{
    uint8_t part[512];
    uint32_t len;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    static const char dat[] = "the data fork";
    static const char rsc[] = "RSRC!";

    len = ddseg_head(part, 13, 5, 0, 1, 18);
    memcpy(part + len, dat, 13); len += 13;
    memcpy(part + len, rsc, 5);  len += 5;

    test_make_memio(&io, &m, part, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DDSEG);

    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_DDSEG, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    /* The data fork comes FIRST in the stream, which is the opposite of
     * a StuffIt split and the one thing a set of one still proves. */
    CHECK(cap.dlen[0] == 13 && memcmp(cap.data[0], dat, 13) == 0);
    CHECK(cap.rlen[0] == 5 && memcmp(cap.rsrc[0], rsc, 5) == 0);
    CHECK(cap.info[0].type == 0x44444132u);      /* 'DDA2' */
    CHECK(cap.info[0].creator == 0x44444150u);   /* 'DDAP' */
    CHECK(cap.info[0].finder_flags == 0x0100);
    CHECK(cap.info[0].mod_date == 0xE0364FA6u);
    CHECK(cap.info[0].create_date == 0xE0364F79u);
    /* No name is stored anywhere in the format; with no hint from the
     * host there is nothing to call it but something. */
    CHECK(cap.info[0].name_len == 5 &&
          memcmp(cap.info[0].name, "split", 5) == 0);

    /* Part 1 of TWO is not a file: the count is in the header, so this
     * is the one case in the engine that answers UNC_ERR_SEGMENTED. */
    ddseg_head(part, 13, 5, 0, 2, 18);
    test_make_memio(&io, &m, part, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_DDSEG, &io, &sk, &al, NULL, NULL)
          == UNC_ERR_SEGMENTED);
    CHECK(cap.count == 0);

    /* Four refusals. 'SPLT' at offset 0 is four bytes any file could
     * open with; what makes the header a shape is the second copy at
     * 90 and the three fields that have to agree with each other. */
    ddseg_head(part, 13, 5, 0, 1, 18);
    part[92] ^= 0xFF;                      /* the second mark */
    test_make_memio(&io, &m, part, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);

    ddseg_head(part, 13, 5, 0, 0, 18);     /* a set of no parts */
    test_make_memio(&io, &m, part, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);

    ddseg_head(part, 13, 5, 2, 2, 18);     /* part 3 of 2 */
    test_make_memio(&io, &m, part, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);

    ddseg_head(part, 13, 5, 0, 1, 99);     /* one part, holding more than
                                            * the whole file has forks */
    test_make_memio(&io, &m, part, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);

    /* A header that is legal and a FILE that is short: the refusal has
     * to come from the size, which is the only one of the five that
     * cannot be seen in the header alone. */
    ddseg_head(part, 13, 5, 0, 1, 18);
    test_make_memio(&io, &m, part, UNC_DDSEG_HEAD + 10);
    CHECK(unc_sniff(&io) == UNC_FORMAT_DDSEG);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_DDSEG, &io, &sk, &al, NULL, NULL)
          == UNC_ERR_SEGMENTED);
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
        memset(&opt, 0, sizeof opt);   /* the whole struct: a field this list
                                         * does not name is stack garbage otherwise
                                         * (DECISIONS.md 2026-09-04) */
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

    /* The same file with the 1990 header: **48**, not 84. That long is
     * the magic word 0xABCD and the header's own SIZE, so a header can
     * be shorter than the one every corpus file has — it ends before
     * the checksums at +48 — and the forks begin where it says they do.
     * Stored forks, so this tests the container and no codec; what
     * grades the BYTES is a file DiskDoubler ß05 wrote under emulation,
     * against the bytes it was given (`diskdoubler.py --beta-verify`).
     * Source: docs/formats/diskdoubler-container.md, "The header size,
     * and the 1990 header". */
    {
        UncOptions opt;
        static const uint8_t hint[] = "Subject";
        uint8_t one[512];
        uint32_t n;
        for (n = 0; n < 48; n++) one[n] = 0;
        one[0] = 0xAB; one[1] = 0xCD; one[2] = 0x00; one[3] = 0x30;
        put32(one + 4, 5);           /* datasize   */
        put32(one + 8, 5);           /* datacomp   */
        put32(one + 12, 3);          /* rsrcsize   */
        put32(one + 16, 3);          /* rsrccomp   */
        one[20] = 0; one[21] = 0;    /* both methods: stored */
        one[22] = 0x1F;              /* info1, the 1990 version byte */
        memcpy(one + 32, "TEXT", 4);
        memcpy(one + 36, "ttxt", 4);
        n = 48;
        memcpy(one + n, "plain", 5); n += 5;
        memcpy(one + n, "RSC", 3);   n += 3;
        memset(&opt, 0, sizeof opt);
        opt.name_hint = hint;
        opt.name_hint_len = (uint16_t)(sizeof hint - 1);
        test_make_memio(&io, &m, one, n);
        /* There is no header CRC below +82 to check, so the sniffer's
         * test is the two length pairs — the rule ß05's own validator
         * applies. A fork claiming to compress to more than it started
         * as is not one of these files. */
        CHECK(unc_sniff(&io) == UNC_FORMAT_DISKDOUBLER);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_DISKDOUBLER, &io, &sk, &al, NULL,
                             &opt) == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
        /* No ".dd" to strip: that version compresses in place. */
        CHECK(cap.info[0].name_len == 7 &&
              memcmp(cap.info[0].name, "Subject", 7) == 0);
        CHECK(cap.dlen[0] == 5 && memcmp(cap.data[0], "plain", 5) == 0);
        CHECK(cap.rlen[0] == 3 && memcmp(cap.rsrc[0], "RSC", 3) == 0);
        CHECK(cap.info[0].type == 0x54455854u);   /* 'TEXT' */

        /* Two values, not a range, and these are the controls that say
         * so. 47 is below the floor that version's own validator
         * enforces; 60 is a size it WOULD accept and for which no
         * specimen exists, so nothing here guesses what would sit in
         * the twelve bytes between. Both are UNKNOWN. */
        one[3] = 0x2F;
        test_make_memio(&io, &m, one, n);
        CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
        one[3] = 0x3C;
        test_make_memio(&io, &m, one, n);
        CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
        one[3] = 0x30;
    }

    /* A corrupt header CRC is not a DiskDoubler archive at all. */
    arc[76] ^= 0xFF;
    test_make_memio(&io, &m, arc, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
    arc[76] ^= 0xFF;

    test_dd_stac();
    test_dd_method2();
    test_dd_methods345();
    test_dd_archive2();
    test_ddseg();
}


/* ------------------------------------------------------------------ */
/* SuperDisk!'s SINGLE-FILE container: no record stream, a fixed header */
/* and then the same block chains, data fork first. Built here with     */
/* STORED blocks so the header, the fork split and the metadata are     */
/* tested without a codec; the five specimens Alysis's own control      */
/* panel wrote are what grade the codec (DECISIONS.md 2026-08-22).      */
/* ------------------------------------------------------------------ */

static void test_superdisk_single(void)
{
    static const uint8_t want_d[20] = {
        'a','u','t','o','-','e','x','p','a','n','d','i','n','g',' ',
        'f','i','l','e','.'
    };
    static const uint8_t want_r[8] = { 1, 2, 3, 4, 250, 251, 252, 253 };
    uint8_t one[128];
    uint32_t n;
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    UncOptions opt;
    static const uint8_t hint[] = "SD";

    for (n = 0; n < sizeof one; n++) one[n] = 0;
    put32(one + 0, 28);                        /* total = data + rsrc */
    put32(one + 4, 20);
    put32(one + 8, 8);
    memcpy(one + 12, "TEXT", 4);
    memcpy(one + 16, "ttxt", 4);
    one[20] = 0x12; one[21] = 0x34;            /* Finder flags */
    put32(one + 22, 0xA1C2FC80u);              /* creation */
    put32(one + 26, 0xABEACA80u);              /* modification */
    one[30] = 4;
    memcpy(one + 31, "Test", 4);
    one[35] = 0xAA;                            /* the pad to an even body */
    n = 36;
    /* A stored block: bit 15, and the low bits are the block's whole
     * length including these two, so ulen is that minus two. */
    one[n++] = 0x80; one[n++] = 20 + 2;
    memcpy(one + n, want_d, 20); n += 20;
    one[n++] = 0x80; one[n++] = 8 + 2;
    memcpy(one + n, want_r, 8); n += 8;

    memset(&opt, 0, sizeof opt);   /* the whole struct: a field this list
                                     * does not name is stack garbage otherwise
                                     * (DECISIONS.md 2026-09-04) */
    opt.list_only = 0; opt.test_only = 0;
    opt.name_hint = hint;
    opt.name_hint_len = (uint16_t)(sizeof hint - 1);
    test_make_alloc(&al);
    test_make_memio(&io, &m, one, n);
    CHECK(unc_sniff(&io) == UNC_FORMAT_SUPERDISK);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SUPERDISK, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == 20);
    CHECK(memcmp(cap.data[0], want_d, 20) == 0);
    CHECK(cap.rlen[0] == 8);
    CHECK(memcmp(cap.rsrc[0], want_r, 8) == 0);

    /* `total == data + rsrc` is what tells this container from an
     * archive whose first eight bytes nobody reads. Break it and the
     * sniffer must not claim the file. */
    put32(one + 0, 29);
    test_make_memio(&io, &m, one, n);
    CHECK(unc_sniff(&io) != UNC_FORMAT_SUPERDISK);
    put32(one + 0, 28);
}



/* ------------------------------------------------------------------ */
/* StuffIt SpaceSaver — the container, the stream ORDER, Alg 4 and     */
/* the preset dictionary.                                              */
/*                                                                     */
/* Built here rather than from a fixture: SpaceSaver has never been    */
/* made to compress anything on this machine, so there is no specimen  */
/* of any kind (OPEN_ITEMS.md). These test what the header says and    */
/* what the bit stream means; they cannot say that a real SpaceSaver   */
/* file is laid out this way. What they DO grade honestly is the       */
/* refusal: a stream that reaches into the preset dictionary without   */
/* one must fail rather than decode to something wrong.                */
/* ------------------------------------------------------------------ */

static void ss_head3(uint8_t *h, uint32_t dclen, uint32_t dulen,
                     uint32_t doff, uint8_t dmethod,
                     uint32_t rclen, uint32_t rulen,
                     uint32_t roff, uint8_t rmethod)
{
    memset(h, 0, 84);
    memcpy(h + 0, "SIT!", 4);
    memcpy(h + 4, "DFD3", 4);
    put32(h + 8, 3);
    put32(h + 12, 84);
    put32(h + 16, 0x41);
    put32(h + 20, dclen); put32(h + 24, dulen); put32(h + 28, doff);
    h[32] = 0; h[33] = dmethod;
    put32(h + 36, rclen); put32(h + 40, rulen); put32(h + 44, roff);
    h[48] = 0; h[49] = rmethod;
    memcpy(h + 52, "TEXT", 4);
    memcpy(h + 56, "ttxt", 4);
    h[60] = 0x40; h[61] = 0x00;              /* isInvisible, restored */
}

/* ------------------------------------------------------------------ */
/* SpaceSaver                                                          */
/* ------------------------------------------------------------------ */

static void test_spacesaver(void)
{
    static const uint8_t want_d[12] = "data fork!!";
    static const uint8_t want_r[6]  = { 9, 8, 7, 6, 5, 4 };
    static const uint8_t hint[] = "Report.txt";
    uint8_t f[128];
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    UncOptions opt;

    /* mCompressFile @0x5538 gives offset 84 to the LARGER fork, so the
     * records stay data-then-resource while the streams do not. Here
     * the resource stream comes first, which only the offsets say. */
    memset(f, 0, sizeof f);
    ss_head3(f, 11, 11, 84 + 6, 0, 6, 6, 84, 0);
    memcpy(f + 84, want_r, 6);
    memcpy(f + 84 + 6, want_d, 11);

    memset(&opt, 0, sizeof opt);
    opt.name_hint = hint;
    opt.name_hint_len = (uint16_t)(sizeof hint - 1);
    test_make_alloc(&al);
    test_make_memio(&io, &m, f, 84 + 17);
    CHECK(unc_sniff(&io) == UNC_FORMAT_SPACESAVER);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SPACESAVER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == 11 && memcmp(cap.data[0], want_d, 11) == 0);
    CHECK(cap.rlen[0] == 6 && memcmp(cap.rsrc[0], want_r, 6) == 0);
    CHECK(cap.info[0].type == 0x54455854u);          /* 'TEXT' */
    CHECK(cap.info[0].creator == 0x74747874u);       /* 'ttxt' */
    CHECK(cap.info[0].finder_flags == 0x4000);
    /* The name is the host's, whole: SpaceSaver adds no extension, so
     * ".txt" is part of it. */
    CHECK(cap.info[0].name_len == 10);
    CHECK(memcmp(cap.info[0].name, "Report.txt", 10) == 0);

    /* Version 1 and 2 put the same things elsewhere; UpdateSSHeader
     * @0x6520 is the map, and the data fork's stream came first. */
    memset(f, 0, sizeof f);
    memcpy(f + 0, "SIT!", 4);
    memcpy(f + 4, "DFD3", 4);
    put32(f + 8, 2);
    put32(f + 16, 0x41);
    f[21] = 0;                                   /* the method, both forks */
    put32(f + 24, 11); put32(f + 32, 11);        /* data: clen, ulen */
    put32(f + 28, 6);  put32(f + 36, 6);         /* rsrc: clen, ulen */
    memcpy(f + 40, "TEXT", 4);
    memcpy(f + 44, "ttxt", 4);
    f[48] = 0x40;
    memcpy(f + 84, want_d, 11);
    memcpy(f + 84 + 11, want_r, 6);
    test_make_memio(&io, &m, f, 84 + 17);
    CHECK(unc_sniff(&io) == UNC_FORMAT_SPACESAVER);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SPACESAVER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == 11 && memcmp(cap.data[0], want_d, 11) == 0);
    CHECK(cap.rlen[0] == 6 && memcmp(cap.rsrc[0], want_r, 6) == 0);
    CHECK(cap.info[0].finder_flags == 0x4000);

    /* 'SIT!' alone is StuffIt's magic; it is the second long that makes
     * this format, and neither probe may claim the other's file. */
    memcpy(f + 4, "rLau", 4);
    test_make_memio(&io, &m, f, 84 + 17);
    CHECK(unc_sniff(&io) != UNC_FORMAT_SPACESAVER);
    memcpy(f + 4, "DFD3", 4);
}

/* One block, wbits 8: three literals, a match of 6 at distance 3, then
 * three more literals — "abcabcabcXYZ". Assembled bit by bit against
 * `CMod 21` @0x462: flag bit first, LSB of each byte first, a match's
 * length field biased by four. */
static const uint8_t ss_alg4_vec[] = {
    0x01, 0x00, 0x08,                    /* one block, 256-byte window */
    0x0f, 0x00, 0x00,                    /* clen, header included      */
    0x0c, 0x00, 0x00,                    /* ulen                       */
    0xc3, 0x8a, 0x1d, 0x23, 0x06, 0x62, 0xcd, 0xaa, 0x05
};

static void test_spacesaver_alg4(void)
{
    static const uint8_t want[12] = "abcabcabcXYZ";
    static const uint8_t hint[] = "Squeezed";
    uint8_t f[160];
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    UncOptions opt;
    uint32_t n = (uint32_t)sizeof ss_alg4_vec;

    memset(f, 0, sizeof f);
    ss_head3(f, n, 12, 84, 4, 0, 0, 0, 0);
    memcpy(f + 84, ss_alg4_vec, n);

    memset(&opt, 0, sizeof opt);
    opt.name_hint = hint;
    opt.name_hint_len = (uint16_t)(sizeof hint - 1);
    test_make_alloc(&al);
    test_make_memio(&io, &m, f, 84 + n);
    CHECK(unc_sniff(&io) == UNC_FORMAT_SPACESAVER);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SPACESAVER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == 12 && memcmp(cap.data[0], want, 12) == 0);

    /* bit 7 of the method byte only says WHICH BUILD of the module
     * wrote the stream (@0x578e masks it off); the bits are the same. */
    f[33] = 0x84;
    test_make_memio(&io, &m, f, 84 + n);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SPACESAVER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == 12 && memcmp(cap.data[0], want, 12) == 0);
    f[33] = 4;

    /* A method this engine has never heard of must still SNIFF as
     * SpaceSaver — naming the format is what saves the user from
     * *unknown* — and fail on the entry rather than on the file. */
    f[33] = 9;
    test_make_memio(&io, &m, f, 84 + n);
    CHECK(unc_sniff(&io) == UNC_FORMAT_SPACESAVER);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SPACESAVER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_UNSUPPORTED);
    CHECK(cap.dlen[0] == 0);

    /* A method no version of SpaceSaver ever wrote is declined per
     * ENTRY, not per archive: the entry is still named and its sizes
     * still reported. Methods 0..4 all decode as of 2026-08-25
     * (FORMATS.md), so this is method 5 — reserved, and refused. */
    f[33] = 5;
    test_make_memio(&io, &m, f, 84 + n);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SPACESAVER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_UNSUPPORTED);
    CHECK(cap.info[0].data_size == 12);
    f[33] = 4;
}

/* The preset dictionary: which one, and who chooses it. @0x280 loads the
 * window from a 'PrAm' resource before the first output byte, and the
 * fork record's byte at +12 says which. Both tables are built in
 * (ss_dict.h), and a caller may override the choice.
 *
 * The stream here is one token: a match of 10 at distance 10, entirely
 * inside the dictionary, so its output IS the dictionary's last ten
 * bytes and nothing of the file's own. */
static void test_spacesaver_preset(void)
{
    static const uint8_t preset[10] = "0123456789";
    static const uint8_t hint[] = "Squeezed";
    static const uint8_t vec[] = {
        0x01, 0x00, 0x08,
        0x08, 0x00, 0x00,
        0x0a, 0x00, 0x00,
        0x8c, 0x02
    };
    uint8_t f[160], builtin[10];
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    UncOptions opt;
    uint32_t n = (uint32_t)sizeof vec;

    memset(f, 0, sizeof f);
    ss_head3(f, n, 10, 84, 4, 0, 0, 0, 0);
    memcpy(f + 84, vec, n);

    memset(&opt, 0, sizeof opt);
    opt.name_hint = hint;
    opt.name_hint_len = (uint16_t)(sizeof hint - 1);
    test_make_alloc(&al);

    /* No caller table: the built-in one is used, and the ten bytes are
     * ITS tail — whatever they are, they are not the file's. */
    test_make_memio(&io, &m, f, 84 + n);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SPACESAVER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == 10);
    memcpy(builtin, cap.data[0], 10);

    /* A caller's table overrides it, and the same stream then decodes to
     * the caller's bytes instead. Both cannot be true of one decoder
     * that ignores one of them. */
    opt.preset = preset;
    opt.preset_len = (uint32_t)sizeof preset;
    test_make_memio(&io, &m, f, 84 + n);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SPACESAVER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == 10 && memcmp(cap.data[0], preset, 10) == 0);
    CHECK(memcmp(builtin, preset, 10) != 0);
    opt.preset = NULL;
    opt.preset_len = 0;

    /* Record byte +12 selects the table. Index 1 is the other 'PrAm'
     * and is four spaces, so the same stream cannot decode at all — it
     * reaches ten bytes back into a four-byte history. */
    f[32] = 1;
    test_make_memio(&io, &m, f, 84 + n);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SPACESAVER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] != UNC_OK);
    CHECK(cap.dlen[0] == 0);

    /* And a table this build does not have is refused rather than
     * decoded with the wrong one. */
    f[32] = 7;
    test_make_memio(&io, &m, f, 84 + n);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SPACESAVER, &io, &sk, &al, NULL,
                         &opt) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_UNSUPPORTED);
    CHECK(cap.dlen[0] == 0);
    f[32] = 0;
}

/* ------------------------------------------------------------------ */
/* Compact Pro segments: the one field an indexless segment can be    */
/* held to (src/fmt_cptseg.c)                                          */
/*                                                                     */
/* A middle segment is a chunk of compressed data with an 8-byte hat,  */
/* so the probe is deliberately weak. It was weak enough to claim a    */
/* file from another format: `Read First.PKG`, a real AppleLink        */
/* package, is 01 01 00 00 with a zero index and sniffed as a first    */
/* segment until 2026-09-26. The header below is that file's, byte for */
/* byte; the specimen is fetched, not committed.                       */
/* ------------------------------------------------------------------ */
static void test_cptseg_probe(void)
{
    uint8_t seg[64];
    MemIO m;
    UncIO io;
    UncSegmentDesc desc;
    int i;

    /* A first segment as Compact Pro writes one: volume 1, no index,
     * and the identity edu3's real four-part set carries. */
    for (i = 0; i < (int)sizeof seg; i++) seg[i] = (uint8_t)(i * 7 + 3);
    seg[0] = 0x01; seg[1] = 0x01; seg[2] = 0xab; seg[3] = 0x78;
    seg[4] = seg[5] = seg[6] = seg[7] = 0x00;
    test_make_memio(&io, &m, seg, sizeof seg);
    CHECK(unc_cptseg_probe(seg, sizeof seg, &io) == UNC_FORMAT_CPTSEG);

    /* A middle segment of the same set. */
    seg[1] = 0x03;
    test_make_memio(&io, &m, seg, sizeof seg);
    CHECK(unc_cptseg_probe(seg, sizeof seg, &io) == UNC_FORMAT_CPTSEG);

    /* The AppleLink package. Zero identity and zero index: there is no
     * Compact Pro fact anywhere in the file, and the probe must not
     * invent one. */
    seg[1] = 0x01; seg[2] = 0x00; seg[3] = 0x00;
    test_make_memio(&io, &m, seg, sizeof seg);
    CHECK(unc_cptseg_probe(seg, sizeof seg, &io) == UNC_FORMAT_UNKNOWN);
    test_make_memio(&io, &m, seg, sizeof seg);
    CHECK(unc_cptseg_describe(&io, &desc) == UNC_ERR_FORMAT);

    /* Volume 0 does not exist, identity or no identity. */
    seg[1] = 0x00; seg[2] = 0xab; seg[3] = 0x78;
    test_make_memio(&io, &m, seg, sizeof seg);
    CHECK(unc_cptseg_probe(seg, sizeof seg, &io) == UNC_FORMAT_UNKNOWN);

    /* The describe walk agrees with the probe on the file it accepts,
     * and reports the identity as the set fingerprint. */
    seg[1] = 0x02;
    test_make_memio(&io, &m, seg, sizeof seg);
    CHECK(unc_cptseg_describe(&io, &desc) == UNC_OK);
    CHECK(desc.fp[0] == 0xab && desc.fp[1] == 0x78);
    CHECK(desc.part == 2 && desc.nparts == 0);
}

/* ------------------------------------------------------------------ */
/* AppleLink package (`.pkg`) — NOT recognised, deliberately          */
/*                                                                    */
/* `unc_applelink_probe` shipped from 2026-08-23 to 2026-09-27 and    */
/* tested three tokens — `Decode <thing> to|into <place>` — read out  */
/* of `PKG Expand Translator`. That routine is the StuffIt translator */
/* COMMAND parser and not a file test: the CompactPro, UnZip, UUCode, */
/* BinHex4 and Unix Compress translators each carry the same routine  */
/* with the same `STR# 129` verbs, so a line it accepts is equally    */
/* every one of their commands and none of their formats. Removed;    */
/* these assert that it stays removed (FORMATS.md, *AppleLink         */
/* packages*; DECISIONS.md 2026-09-27).                               */
/* ------------------------------------------------------------------ */

static void ss_sniff_is(const char *text, UncFormat want)
{
    MemIO m;
    UncIO io;
    uint32_t n = 0;
    while (text[n]) n++;
    test_make_memio(&io, &m, (const uint8_t *)text, n);
    CHECK(unc_sniff(&io) == want);
}

/* ------------------------------------------------------------------ */
/* Formats this engine does not have: not an archive                  */
/*                                                                     */
/* Until 2026-10-18 sixteen PC-side and modern formats were NAMED      */
/* here and never extracted (DECISIONS.md 2026-10-18, *the formats it  */
/* only named*). Their probes ran ahead of MacBinary's CRC and every   */
/* weaker test, so nothing else was ever asked about one. Now nothing  */
/* claims them, and that has to be shown rather than assumed: each     */
/* magic the old probes accepted, in a file that is otherwise zeros    */
/* and in one that is otherwise 0xFF, sniffs as UNKNOWN                */
/* and extracts as UNC_ERR_FORMAT with nothing written.                */
/* tools/run_foreign.py puts real archives through the same question. */
/* ------------------------------------------------------------------ */
static void fgn_none(const uint8_t *data, int32_t len)
{
    UncIO io;
    MemIO m;
    UncAlloc al;
    UncSink sk;
    CapSink cap;
    test_make_memio(&io, &m, data, (uint32_t)len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
    test_make_memio(&io, &m, data, (uint32_t)len);
    test_make_alloc(&al);
    cap_make(&sk, &cap);
    CHECK(unc_extract(&io, &sk, &al, NULL, NULL) == UNC_ERR_FORMAT);
    CHECK(cap.count == 0);
}

/* The signature at `off`, then filler to 128 bytes: zeros, which are
 * what MacBinary's constraints want, and then 0xFF, so that a test
 * wanting zeros is not the only thing that refuses it. */
static void fgn_sig_at(const char *sig, int32_t siglen, int32_t off)
{
    uint8_t buf[128];
    int32_t i, fill;
    for (fill = 0; fill < 2; fill++) {
        for (i = 0; i < (int32_t)sizeof buf; i++)
            buf[i] = fill ? 0xFF : 0;
        for (i = 0; i < siglen; i++) buf[off + i] = (uint8_t)sig[i];
        fgn_none(buf, (int32_t)sizeof buf);
    }
}

static void fgn_sig(const char *sig, int32_t siglen)
{
    fgn_sig_at(sig, siglen, 0);
}

static void test_foreign(void)
{
    uint8_t buf[128];
    int32_t i;

    /* The enumerators either side of the two retired gaps keep the
     * values they shipped with (include/macextract.h). */
    CHECK(UNC_FORMAT_TAR == 12);
    CHECK(UNC_FORMAT_SITX_RETIRED == 13);
    CHECK(UNC_FORMAT_DISKDOUBLER == 14);
    CHECK(UNC_FORMAT_MIME == 29);
    CHECK(UNC_FORMAT_MIMESEG == 45);
    CHECK(UNC_FORMAT_BINHEX_OLD == 48);
    CHECK(!unc_format_extractable(UNC_FORMAT_SITX_RETIRED));
    for (i = 30; i <= 44; i++)
        CHECK(!unc_format_extractable((UncFormat)i));
    CHECK(unc_format_extractable(UNC_FORMAT_MIMESEG));

    /* StuffIt X. Source: reference/deark/modules/unsupported.c. */
    fgn_sig("StuffIt!", 8);
    fgn_sig("StuffIt?", 8);
    /* RAR, three generations. Source: reference/deark/modules/rar.c. */
    fgn_sig("Rar!\x1a\x07\x00", 7);
    fgn_sig("Rar!\x1a\x07\x01\x00", 8);
    fgn_sig("RE~^", 4);
    /* 7-Zip, xz, bzip2 (both stream magics). Source: deark's
     * unsupported.c. "\xfd7..." would eat the 7 as a hex digit. */
    fgn_sig("7z\xbc\xaf\x27\x1c\x00", 7);
    fgn_sig("\xfd" "7zXZ\x00", 6);
    fgn_sig("BZh9\x31\x41\x59\x26\x53\x59", 10);
    fgn_sig("BZh1\x17\x72\x45\x38\x50\x90", 10);
    /* Cabinet, ar, cpio's five shapes. Source: deark's cab.c, ar.c,
     * cpio.c. */
    fgn_sig("MSCF", 4);
    fgn_sig("!<arch>\x0a", 8);
    fgn_sig("070707", 6);
    fgn_sig("070701", 6);
    fgn_sig("070702", 6);
    fgn_sig("\xc7\x71", 2);
    fgn_sig("\x71\xc7", 2);
    /* Zoo, at 0x14. Source: deark's zoo.c. */
    fgn_sig_at("\xdc\xa7\xc4\xfd", 4, 0x14);
    /* Zstandard and its skippable frames. Source:
     * reference/notes/zstd_rfc8878.txt, 3.1.1 and 3.1.2. */
    fgn_sig("\x28\xb5\x2f\xfd", 4);
    fgn_sig("\x50\x2a\x4d\x18", 4);
    fgn_sig("\x5f\x2a\x4d\x18", 4);
    /* lzip, lrzip, WIM. Sources: deark's unsupported.c,
     * reference/lrzip/lrzip.c, reference/wimlib's header.h. */
    fgn_sig("LZIP", 4);
    fgn_sig("LRZI\x00\x06", 6);
    fgn_sig("MSWIM\0\0\0\xd0\0\0\0", 12);
    /* Apple Archive, raw and compressed. Source:
     * reference/libNeoAppleArchive; the lzma and lz4 letters from
     * reference/notes/Apple_Archive.md. */
    fgn_sig("AA01\x06\x00", 6);
    fgn_sig("YAA1\x06\x00", 6);
    fgn_sig("AA01\x0a\x00TYP1", 10);
    fgn_sig("pbze", 4);
    fgn_sig("pbzz", 4);
    fgn_sig("pbzb", 4);
    fgn_sig("pbzx", 4);
    fgn_sig("pbz4", 4);

    /* ARJ: its magic and a basic header whose CRC-32 checks out, which
     * is the whole of what the old probe asked. Source:
     * reference/deark/modules/arj.c. */
    {
        uint32_t crc;
        int32_t hlen = 34;
        for (i = 0; i < (int32_t)sizeof buf; i++) buf[i] = 0;
        buf[0] = 0x60; buf[1] = 0xea;
        buf[2] = (uint8_t)hlen; buf[3] = 0;          /* little-endian */
        buf[4] = 34; buf[5] = 11; buf[6] = 1; buf[7] = 1; buf[8] = 2;
        crc = ~unc_crc32(0xFFFFFFFFu, buf + 4, hlen);
        buf[4 + hlen + 0] = (uint8_t)crc;
        buf[4 + hlen + 1] = (uint8_t)(crc >> 8);
        buf[4 + hlen + 2] = (uint8_t)(crc >> 16);
        buf[4 + hlen + 3] = (uint8_t)(crc >> 24);
        fgn_none(buf, (int32_t)sizeof buf);
    }
}

static void test_applelink(void)
{
    /* A translator command line names nothing. Every one of these was
     * sniffed as "AppleLink package" until 2026-09-27, and the first is
     * also, word for word, what the CompactPro translator's own
     * recogniser accepts. The probe that replaced it on 2026-10-05 is a
     * file test and these stay here as the pin on the old one. */
    ss_sniff_is("Decode \"My File\" to \"Some Folder\"\r", UNC_FORMAT_UNKNOWN);
    ss_sniff_is("Decode Thing into Folder\r", UNC_FORMAT_UNKNOWN);
    ss_sniff_is("DECODE thing TO folder\r", UNC_FORMAT_UNKNOWN);
    ss_sniff_is("\r\n   Decode thing to folder\r", UNC_FORMAT_UNKNOWN);
    ss_sniff_is("Decode the message by hand, then send it to Bob.\r",
                UNC_FORMAT_UNKNOWN);
}

/* ------------------------------------------------------------------ */
/* AppleLink packages: SqueezePlay (src/fmt_sqp.c), M56               */
/*                                                                    */
/* The codec and the container are graded on real and synthesised      */
/* packages by tools/run_sqp.py and the diff suite; what is here is    */
/* the version-1 container at its smallest, so that every test the     */
/* SNIFFER makes can be bent one at a time in a few bytes. The record  */
/* below is a STORED fork, because the probe does not decode and this  */
/* keeps the subject readable.                                        */
/* ------------------------------------------------------------------ */

/* One item, stored, four bytes of data fork. Returns the total length.
 * Source: as fmt_sqp.c. */
static uint32_t sqp_synth(uint8_t *buf)
{
    uint32_t i, start = 86u + 22u + 90u;   /* 198 */
    uint8_t *rec;

    for (i = 0; i < start + 4u; i++) buf[i] = 0;
    buf[0] = 1;                            /* one SQP record  */
    buf[1] = 1;                            /* version         */
    buf[10 + 86 + 3] = 1;                  /* one HFS record  */

    /* The HFS record: level 1, not a folder, then the same 86 bytes the
     * SQP directory carries. */
    rec = buf + 10 + 86 + 12;
    rec[1] = 1;                            /* level           */
    rec = rec + 4;
    unc_put_u32be(rec + 8, 4);             /* data, compressed */
    unc_put_u32be(rec + 12, start);        /* data, at         */
    memcpy(rec + 20, "TEXTttxt", 8);
    rec[36] = 1;
    rec[37] = 'T';
    unc_put_u32be(rec + 80, 4);            /* data, expanded   */
    rec[84] = (uint8_t)(0x80 | 0x02);      /* InitSqp's bit, and stored */
    memcpy(buf + 10, rec, 86);             /* the SQP copy of it */
    memcpy(buf + start, "ABCD", 4);
    return start + 4u;
}

static void test_sqp(void)
{
    uint8_t pkg[256], bent[256];
    uint32_t len = sqp_synth(pkg);
    uint32_t recat = 10u + 86u + 12u;      /* the HFS record   */
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    test_make_memio(&io, &m, pkg, len);
    CHECK(unc_sniff(&io) == UNC_FORMAT_SQP);

    test_make_alloc(&al);
    cap_make(&sk, &cap);
    test_make_memio(&io, &m, pkg, len);
    CHECK(unc_extract_as(UNC_FORMAT_SQP, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.info[0].name_len == 1 && cap.info[0].name[0] == 'T');
    CHECK(cap.info[0].type == 0x54455854u);     /* 'TEXT' */
    CHECK(cap.dlen[0] == 4 && memcmp(cap.data[0], "ABCD", 4) == 0);
    CHECK(cap.rlen[0] == 0);

    /* Every test the probe makes, bent one at a time. A probe with no
     * magic number is worth exactly what its negative controls are. */
#define SQP_BENT(what, at, to) do {                                      \
        memcpy(bent, pkg, len);                                          \
        bent[at] = (uint8_t)(to);                                        \
        test_make_memio(&io, &m, bent, len);                             \
        CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);                     \
    } while (0)
    SQP_BENT("the version byte", 1, 2);
    SQP_BENT("one of the eight zero bytes", 5, 1);
    SQP_BENT("the SQP count, which locates the HFS directory", 0, 2);
    SQP_BENT("the item count", 10 + 86 + 3, 2);
    SQP_BENT("the second header's zero bytes", 10 + 86 + 4, 1);
    SQP_BENT("the level", recat + 1, 2);
    SQP_BENT("the name length, past what a Str31 holds", recat + 4 + 36, 32);
    SQP_BENT("the name length, to zero, which no HFS name has",
             recat + 4 + 36, 0);
    SQP_BENT("the compressed length, so the members no longer tile",
             recat + 4 + 11, 5);
    SQP_BENT("the fork's offset", recat + 4 + 15, 199);
#undef SQP_BENT

    /* A file of ZEROS whose length is 10 + 86n for the n in its first
     * byte. Every length in it is 0, so the tiling test cannot fail on
     * it — `lo` stays at EOF, `hi` at the directory's end and the sum at
     * 0 == fsize - start — and the name's lower bound is the only test
     * left standing. This was sniffed as a package, and listed as one
     * 0-byte entry, until 2026-10-06 (DECISIONS.md, *the directory of
     * empty records*). */
    memset(bent, 0, sizeof bent);
    bent[0] = 1;                                /* one version-0 record */
    test_make_memio(&io, &m, bent, 96);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);
    /* The same 96 bytes with a NAME in the record is a package — one
     * member, an empty file — and the pair is what says the probe
     * refuses a nameless record rather than a forkless one. */
    bent[10 + 36] = 1;
    bent[10 + 37] = 'E';
    test_make_memio(&io, &m, bent, 96);
    CHECK(unc_sniff(&io) == UNC_FORMAT_SQP);
    cap_make(&sk, &cap);
    test_make_memio(&io, &m, bent, 96);
    CHECK(unc_extract_as(UNC_FORMAT_SQP, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.info[0].name_len == 1 && cap.info[0].name[0] == 'E');
    CHECK(cap.dlen[0] == 0 && cap.rlen[0] == 0);

    /* And one byte short of tiling, from the other end. */
    test_make_memio(&io, &m, pkg, len - 1);
    CHECK(unc_sniff(&io) == UNC_FORMAT_UNKNOWN);

    /* A version-0 package is the SQP directory alone, with every item
     * at level 1 (ReadFileAndBuildLinkedList @0x31be). */
    memcpy(bent, pkg, len);
    bent[1] = 0;
    unc_put_u32be(bent + 10 + 12, 96);     /* the member moves to 10+86 */
    unc_put_u32be(bent + 10 + 8, 4);
    memcpy(bent + 96, "WXYZ", 4);
    test_make_memio(&io, &m, bent, 100);
    CHECK(unc_sniff(&io) == UNC_FORMAT_SQP);
    cap_make(&sk, &cap);
    test_make_memio(&io, &m, bent, 100);
    CHECK(unc_extract_as(UNC_FORMAT_SQP, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == 4 && memcmp(cap.data[0], "WXYZ", 4) == 0);

    /* A folder, whose own record carries no forks and must not be
     * asked for any: DoItemsReverse @0x1ecc never calls DoWork for one,
     * and the lengths in that record are the Finder's rather than the
     * format's. */
    memcpy(bent, pkg, len);
    bent[recat + 2] = 0;
    bent[recat + 3] = 1;                        /* it is a folder */
    unc_put_u32be(bent + recat + 4 + 8, 0);     /* no fork lengths */
    unc_put_u32be(bent + recat + 4 + 80, 0);
    test_make_memio(&io, &m, bent, 198);        /* nothing after it */
    CHECK(unc_sniff(&io) == UNC_FORMAT_SQP);
    cap_make(&sk, &cap);
    test_make_memio(&io, &m, bent, 198);
    CHECK(unc_extract_as(UNC_FORMAT_SQP, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.info[0].is_dir == 1);
    CHECK(cap.dlen[0] == 0 && cap.rlen[0] == 0);

    /* The version the reference implementation refuses, and it refuses
     * the whole file rather than one entry. */
    memcpy(bent, pkg, len);
    bent[1] = 2;
    test_make_memio(&io, &m, bent, len);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_SQP, &io, &sk, &al, NULL, NULL)
          == UNC_ERR_UNSUPPORTED);
    CHECK(cap.count == 0);
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
    /* Method 13 (SlowFastC), which is declined per entry. This was
     * method 10 until 2026-08-25, when SlowFastA was implemented — the
     * test wants a method NOTHING here can read, so it has to move when
     * one lands. 13 and 20 are what is left (OPEN_ITEMS.md). */
    arc[at + 4] = 0; arc[at + 5] = 13;
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


/* ------------------------------------------------------------------ */
/* Ciphers                                                            */
/*                                                                    */
/* The primitives are graded against implementations that are not     */
/* this one: the DES vectors below come from `openssl enc -des-ecb`   */
/* and the MD5 ones from python3's hashlib, both re-runnable —        */
/* tools/check_crypt.py regenerates every constant in this function.  */
/* ------------------------------------------------------------------ */

static void test_des(void)
{
    UncCrypt cr;
    UncAlloc al;
    /* Key 0123456789abcdef over "Now is t": the FIPS example, and what
     * `openssl enc -des-ecb -K 0123456789abcdef -nopad` produces. */
    static const uint8_t key[8] = { 0x01,0x23,0x45,0x67,0x89,0xab,0xcd,0xef };
    static const uint8_t plain[8] = { 'N','o','w',' ','i','s',' ','t' };
    static const uint8_t cipher[8] = { 0x3f,0xa4,0x0e,0x8a,0x98,0x4d,0x48,0x15 };
    uint8_t buf[8];
    int i;

    /* PackIt decodes by DES-DECRYPTING, which is the operation
     * unc_crypt_apply performs, so the ciphertext must come back as
     * the plaintext of the same key pair. */
    test_make_alloc(&al);
    unc_crypt_init(&cr);
    CHECK(unc_crypt_packit_des(&cr, &al, key, 8) == UNC_OK);
    memcpy(buf, cipher, 8);
    unc_crypt_apply(&cr, buf, 8, 0);
    CHECK(memcmp(buf, plain, 8) == 0);

    /* And a second block runs on the same schedule (ECB: no state). */
    CHECK(unc_crypt_packit_des(&cr, &al, key, 8) == UNC_OK);
    for (i = 0; i < 8; i++) buf[i] = cipher[i];
    unc_crypt_apply(&cr, buf, 8, 0);
    CHECK(memcmp(buf, plain, 8) == 0);
    unc_crypt_free(&cr, &al);
}

static void test_md5(void)
{
    static const uint8_t empty[16] = {
        0xd4,0x1d,0x8c,0xd9,0x8f,0x00,0xb2,0x04,
        0xe9,0x80,0x09,0x98,0xec,0xf8,0x42,0x7e };
    static const uint8_t abc[16] = {
        0x90,0x01,0x50,0x98,0x3c,0xd2,0x4f,0xb0,
        0xd6,0x96,0x3f,0x7d,0x28,0xe1,0x7f,0x72 };
    uint8_t out[16], msg[80];
    int i;

    unc_md5((const uint8_t *)"", 0, out);
    CHECK(memcmp(out, empty, 16) == 0);
    unc_md5((const uint8_t *)"abc", 3, out);
    CHECK(memcmp(out, abc, 16) == 0);
    /* "abcdefghij..." — 64 bytes is exactly one block, so the padding
     * needs a second one, and 80 exercises the ordinary tail. */
    for (i = 0; i < 80; i++) msg[i] = (uint8_t)('a' + (i % 26));
    unc_md5(msg, 64, out);
    CHECK(out[0] == 0xa2 && out[15] == 0x2b);
    unc_md5(msg, 80, out);
    CHECK(out[0] == 0xe2 && out[15] == 0x9e);
}

static void test_rc4(void)
{
    /* RC4 test vector: key "Key", plaintext "Plaintext" ->
     * BBF316E8D940AF0AD3 (RFC 6229 era, reproduced by python's
     * ARC4 in tools/check_crypt.py). */
    static const uint8_t want[9] = {
        0xBB,0xF3,0x16,0xE8,0xD9,0x40,0xAF,0x0A,0xD3 };
    UncCrypt cr;
    uint8_t buf[9];
    memcpy(buf, "Plaintext", 9);
    unc_crypt_rc4(&cr, (const uint8_t *)"Key", 3);
    unc_crypt_apply(&cr, buf, 9, 0);
    CHECK(memcmp(buf, want, 9) == 0);
    /* Symmetric, and the state carries across calls. */
    unc_crypt_rc4(&cr, (const uint8_t *)"Key", 3);
    unc_crypt_apply(&cr, buf, 4, 0);
    unc_crypt_apply(&cr, buf + 4, 5, 4);
    CHECK(memcmp(buf, "Plaintext", 9) == 0);
}

/* Compact Pro's cipher. These are NOT evidence about the format — no
 * second implementation of it exists to produce them, and the numbers
 * come from the same reading src/unc_crypt.c does (tools/synth_cpt.py,
 * which is what feeds tools/vmac/cptcrypt.py). They are a regression
 * guard: the day somebody changes a shift here, this says so. What
 * would make them evidence is in OPEN_ITEMS.md. */
static void test_cpt_cipher(void)
{
    static const uint8_t want[16] = {
        0xd8,0x79,0x03,0x74,0xb7,0x1e,0xa9,0xcb,
        0xc1,0x3d,0xc4,0x33,0x19,0x2f,0xee,0x3f };
    /* A password over eight characters folds by ADDITION into eight
     * accumulators, which is the one part of the key derivation a
     * shorter password cannot exercise. */
    static const uint8_t wantlong[8] = {
        0x67,0xe9,0x32,0x46,0xc6,0x8f,0x59,0x6a };
    UncCrypt cr;
    UncAlloc al;
    uint8_t buf[16];
    int i;

    test_make_alloc(&al);
    unc_crypt_init(&cr);
    for (i = 0; i < 16; i++) buf[i] = 0;
    CHECK(unc_crypt_cpt(&cr, &al, (const uint8_t *)"ohsecret", 8) == UNC_OK);
    unc_crypt_apply(&cr, buf, 16, 0);
    CHECK(memcmp(buf, want, 16) == 0);

    /* The state carries across calls: decrypting in two pieces gives
     * the same answer as decrypting in one. (It is not an involution —
     * the register steps on the PLAINTEXT byte, so encrypting and
     * decrypting are different walks; tools/synth_cpt.py has both.) */
    for (i = 0; i < 16; i++) buf[i] = 0;
    CHECK(unc_crypt_cpt(&cr, &al, (const uint8_t *)"ohsecret", 8) == UNC_OK);
    unc_crypt_apply(&cr, buf, 5, 0);
    unc_crypt_apply(&cr, buf + 5, 11, 5);
    CHECK(memcmp(buf, want, 16) == 0);

    for (i = 0; i < 8; i++) buf[i] = 0;
    CHECK(unc_crypt_cpt(&cr, &al, (const uint8_t *)"a-very-long-password-indeed", 27) == UNC_OK);
    unc_crypt_apply(&cr, buf, 8, 0);
    CHECK(memcmp(buf, wantlong, 8) == 0);
    unc_crypt_free(&cr, &al);
}

/* SHA-1, HMAC-SHA1, PBKDF2 and AES: the four WinZip's AES is built
 * from, each against something that is not this project — hashlib,
 * hmac, hashlib.pbkdf2_hmac and `openssl enc -aes-*-ecb`. Regenerate
 * with tools/check_crypt.py. */
static void test_winzip_aes_pieces(void)
{
    UncCrypt cr;
    UncHmac m;
    uint8_t out[20], buf[16];
    int i;

    /* SHA-1 is reached through HMAC here, which is how the engine uses
     * it; an all-zero key of 64 bytes makes the inner block a known
     * constant, so a broken SHA-1 cannot hide behind a broken HMAC. */
    unc_hmac_init_test(&m, (const uint8_t *)"key", 3);
    unc_hmac_update(&m, (const uint8_t *)
                    "The quick brown fox jumps over the lazy dog", 43);
    unc_hmac_final(&m, out);
    CHECK(out[0] == 0xde && out[1] == 0x7c && out[19] == 0xd9);

    /* AES-256 and AES-128, forward direction, FIPS-197 shape. */
    for (i = 0; i < 16; i++) buf[i] = (uint8_t)i;
    {
        uint8_t key[32];
        static const uint8_t want256[16] = {
            0x5a,0x6e,0x04,0x57,0x08,0xfb,0x71,0x96,
            0xf0,0x2e,0x55,0x3d,0x02,0xc3,0xa6,0x92 };
        static const uint8_t want128[16] = {
            0x0a,0x94,0x0b,0xb5,0x41,0x6e,0xf0,0x45,
            0xf1,0xc3,0x94,0x58,0xc6,0x53,0xea,0x5a };
        for (i = 0; i < 32; i++) key[i] = (uint8_t)i;
        unc_aes_encrypt_test(&cr, key, 32, buf);
        CHECK(memcmp(buf, want256, 16) == 0);
        for (i = 0; i < 16; i++) buf[i] = (uint8_t)i;
        unc_aes_encrypt_test(&cr, key, 16, buf);
        CHECK(memcmp(buf, want128, 16) == 0);
    }

    /* PBKDF2 with the iteration count WinZip uses, at the length an
     * AES-256 entry needs (two 32-byte keys and the verifier). */
    {
        uint8_t derived[66];
        unc_pbkdf2_test((const uint8_t *)"password", 8,
                        (const uint8_t *)"salt", 4, 1000, derived, 66);
        CHECK(derived[0] == 0x6e && derived[1] == 0x88 &&
              derived[64] == 0xa3 && derived[65] == 0x0b);
    }
}

/* btoa: both framings, on streams the reference encoder produced for
 * "Mac\n" (tools/run_btoa.py grades the real thing against the real
 * encoder; these two are here so `ci.sh` covers the format on a clone
 * with no reference/ directory). The version 4 and version 5 lines
 * differ in more than the header: v5 carries a per-line checksum
 * character and sums the ENCODED characters, v4 sums the decoded
 * bytes, so the two End lines disagree on a four-byte file. */
static void test_btoa(void)
{
    static const char v5[] =
        "xbtoa5 78 small.txt Begin\n"
        "9jqN=q\n"
        "xbtoa End N 4 4 E 51 S 1a4 R 97d\n";
    static const char v4[] =
        "xbtoa Begin\n"
        "9jqN=\n"
        "xbtoa End N 4 4 E 45 S 11f R 4bc\n";
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    test_make_alloc(&al);

    test_make_memio(&io, &m, (const uint8_t *)v5, (uint32_t)sizeof v5 - 1);
    CHECK(unc_sniff(&io) == UNC_FORMAT_BTOA);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_BTOA, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == 4 && memcmp(cap.data[0], "Mac\n", 4) == 0);
    /* Version 5 names the file; the entry takes that name. */
    CHECK(cap.info[0].name_len == 9 &&
          memcmp(cap.info[0].name, "small.txt", 9) == 0);

    test_make_memio(&io, &m, (const uint8_t *)v4, (uint32_t)sizeof v4 - 1);
    CHECK(unc_sniff(&io) == UNC_FORMAT_BTOA);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_BTOA, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == 4 && memcmp(cap.data[0], "Mac\n", 4) == 0);

    /* A flipped body character must be a per-entry error. Establish
     * that this test CAN fail: the same stream with one character
     * changed has to come back wrong. */
    {
        char bad[sizeof v5];
        memcpy(bad, v5, sizeof v5);
        bad[27] = bad[27] == '!' ? '#' : '!';
        test_make_memio(&io, &m, (const uint8_t *)bad, (uint32_t)sizeof v5 - 1);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_BTOA, &io, &sk, &al, NULL, NULL)
              == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] != UNC_OK);
    }

    /* Prose that merely contains the word is not an archive. */
    {
        static const char prose[] =
            "I used xbtoa Begin once, years ago, and it worked.\n";
        test_make_memio(&io, &m, (const uint8_t *)prose,
                        (uint32_t)sizeof prose - 1);
        CHECK(unc_sniff(&io) != UNC_FORMAT_BTOA);
    }

    /* A ten-field End line (one short of eleven) must be refused, not
     * read its eleventh field (the rot checksum) from off[10]/flen[10],
     * which `btoa_fields` leaves uninitialised. */
    {
        static const char short_end[] =
            "xbtoa Begin\n"
            "9jqN=\n"
            "xbtoa End N 4 4 E 45 S 11f R\n";
        test_make_memio(&io, &m, (const uint8_t *)short_end,
                        (uint32_t)sizeof short_end - 1);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_BTOA, &io, &sk, &al, NULL, NULL)
              == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_CORRUPT);
    }
}

/* base64 and MIME. tools/run_mime.py grades both against munpack and
 * deark; these are here so `ci.sh` covers them on a clone with no
 * reference/ directory, and they are hand-built rather than generated:
 * "Mac\n" is `TWFjCg==`, which anyone can check by eye. */
static void test_base64_mime(void)
{
    static const char wrapped[] =
        "begin-base64 644 small.txt\n"
        "TWFjCg==\n"
        "====\n";
    /* An appledouble message: an application/applefile part carrying a
     * real name, the Finder info and a four-byte resource fork, then
     * the data fork. The applefile is 26 + 3*12 = 62 bytes of header
     * and table, then "small.txt", 32 bytes of Finder info, "RSRC". */
    static const char msg[] =
        "From: someone\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: multipart/appledouble; boundary=\"=b=\"\r\n"
        "\r\n"
        "--=b=\r\n"
        "Content-Type: application/applefile\r\n"
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "AAUWBwACAAAAAAAAAAAAAAAAAAAAAAAAAAMAAAADAAAAPgAAAAkAAAAJAAAARwAA\r\n"
        "ACAAAAACAAAAZwAAAARzbWFsbC50eHRURVhUVFRYVAAAAAAAAAAAAAAAAAAAAAAA\r\n"
        "AAAAAAAAAFJTUkM=\r\n"
        "--=b=\r\n"
        "Content-Type: application/octet-stream\r\n"
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "TWFjCg==\r\n"
        "--=b=--\r\n";
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    test_make_alloc(&al);

    /* The named base64 shape, which carries a filename. */
    test_make_memio(&io, &m, (const uint8_t *)wrapped, (uint32_t)sizeof wrapped - 1);
    CHECK(unc_sniff(&io) == UNC_FORMAT_BASE64);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_BASE64, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == 4 && memcmp(cap.data[0], "Mac\n", 4) == 0);
    CHECK(cap.info[0].name_len == 9 &&
          memcmp(cap.info[0].name, "small.txt", 9) == 0);

    /* multipart/appledouble: one entry, both forks, and the type and
     * creator out of the applefile's Finder-info entry. */
    test_make_memio(&io, &m, (const uint8_t *)msg, (uint32_t)sizeof msg - 1);
    CHECK(unc_sniff(&io) == UNC_FORMAT_MIME);
    cap_make(&sk, &cap);
    CHECK(unc_extract_as(UNC_FORMAT_MIME, &io, &sk, &al, NULL, NULL) == UNC_OK);
    CHECK(cap.count == 1 && cap.status[0] == UNC_OK);
    CHECK(cap.dlen[0] == 4 && memcmp(cap.data[0], "Mac\n", 4) == 0);
    CHECK(cap.rlen[0] == 4 && memcmp(cap.rsrc[0], "RSRC", 4) == 0);
    CHECK(cap.info[0].type == 0x54455854u);         /* 'TEXT' */
    CHECK(cap.info[0].creator == 0x54545854u);      /* 'TTXT' */
    CHECK(cap.info[0].name_len == 9 &&
          memcmp(cap.info[0].name, "small.txt", 9) == 0);

    /* Neither probe may claim ordinary text: the message needs
     * something to extract, and a bare base64 body needs the shape of
     * one. Establish that these tests can fail — the two streams above
     * DO get claimed, three lines up each. */
    {
        static const char prose[] =
            "Subject: not a message\n"
            "This is a note about Content-Type: and base64, in prose.\n";
        test_make_memio(&io, &m, (const uint8_t *)prose,
                        (uint32_t)sizeof prose - 1);
        CHECK(unc_sniff(&io) != UNC_FORMAT_MIME);
        CHECK(unc_sniff(&io) != UNC_FORMAT_BASE64);
    }
}

static void test_resfork_find(void)
{
    /* A minimal resource fork holding 'MKey' 0 = eight bytes. */
    uint8_t fork[16 + 12 + 30 + 2 + 8 + 12 + 2];
    uint32_t off = 0, len = 0;
    uint32_t dataoff = 16, mapoff = 16 + 12, i;

    memset(fork, 0, sizeof fork);
    unc_put_u32be(fork + 0, dataoff);
    unc_put_u32be(fork + 4, mapoff);
    unc_put_u32be(fork + 8, 12);                    /* data length      */
    unc_put_u32be(fork + 12, (uint32_t)sizeof fork - mapoff);
    unc_put_u32be(fork + dataoff, 8);               /* resource length  */
    for (i = 0; i < 8; i++) fork[dataoff + 4 + i] = (uint8_t)(0x11 * i);
    fork[mapoff + 24] = 0; fork[mapoff + 25] = 28;  /* type list offset */
    {
        uint8_t *tl = fork + mapoff + 28;
        tl[0] = 0; tl[1] = 0;                       /* one type - 1     */
        memcpy(tl + 2, "MKey", 4);
        tl[6] = 0; tl[7] = 0;                       /* one ref - 1      */
        tl[8] = 0; tl[9] = 10;                      /* ref list offset  */
        tl[10] = 0; tl[11] = 0;                     /* id 0             */
        tl[12] = 0; tl[13] = 0;                     /* name offset -1   */
        tl[14] = 0;                                 /* attributes       */
        tl[15] = 0; tl[16] = 0; tl[17] = 0;         /* data offset 0    */
    }
    CHECK(unc_resfork_find(fork, (uint32_t)sizeof fork, 0x4D4B6579u, 0,
                           &off, &len) == UNC_OK);
    CHECK(len == 8 && off == dataoff + 4);
    CHECK(unc_resfork_find(fork, (uint32_t)sizeof fork, 0x4D4B6579u, 1,
                           &off, &len) == UNC_ERR_FORMAT);
    CHECK(unc_resfork_find(fork, (uint32_t)sizeof fork, 0x76657273u, 0,
                           &off, &len) == UNC_ERR_FORMAT);
    /* Truncation must be refused, not read past. */
    CHECK(unc_resfork_find(fork, 20, 0x4D4B6579u, 0, &off, &len)
          == UNC_ERR_FORMAT);
    /* An offset+length pair that wraps 32-bit must be refused, not let a
     * wild `mapoff` through to the `fork + mapoff + 24` read. */
    {
        uint8_t w[64];
        memset(w, 0, sizeof w);
        unc_put_u32be(w + 4, 0xFFFFFFF0u);      /* mapoff */
        unc_put_u32be(w + 12, 0x20u);           /* maplen: mapoff+maplen wraps */
        CHECK(unc_resfork_find(w, (uint32_t)sizeof w, 0x4D4B6579u, 0,
                               &off, &len) == UNC_ERR_FORMAT);
    }
}

/* ------------------------------------------------------------------ */
/* The path walker, which has no depth limit                          */
/*                                                                    */
/* It had one until 2026-10-07 — UNC_PATH_MAXDEPTH, 24, sized two     */
/* fixed arrays, and was measured against nothing. A Macintosh takes  */
/* 250 levels (FORMATS.md, *What the DESTINATION actually allows*).   */
/* The only limit now is the path STRING, and these assert that.      */
/* ------------------------------------------------------------------ */

static void test_path_depth(void)
{
    UncPath p;
    UncEntryInfo e;
    uint8_t nm[40];
    int i;

    /* 1. Depth far past the old limit, with the path exactly right at
     *    the bottom. One character a level, so 100 levels is 199 bytes
     *    and the string never fills. */
    unc_path_init(&p, NULL);
    for (i = 0; i < 100; i++) {
        nm[0] = (uint8_t)('a' + (i % 26));
        CHECK(unc_path_push(&p, nm, 1) == UNC_OK);
    }
    CHECK(p.depth == 100);
    CHECK(p.len == 199);                      /* 100 names + 99 separators */
    CHECK(p.w == p.buf);                      /* no host buffer offered */
    CHECK(p.lost == 0);
    CHECK(p.truncdepth == 0);
    CHECK(p.buf[0] == 'a' && p.buf[1] == '/' && p.buf[2] == 'b');

    /* 2. Popping back up by SCANNING, which is what replaced the arrays.
     *    Every level has to come back exactly. */
    for (i = 99; i >= 0; i--) {
        unc_path_pop(&p);
        CHECK(p.depth == i);
        CHECK(p.len == (i ? (uint16_t)(2 * i - 1) : 0));
    }
    CHECK(p.len == 0 && p.depth == 0);

    /* 3. A '/' inside a component becomes ':' on the way in, which is
     *    what makes the scan exact rather than a guess: pop must land on
     *    the separator this walker wrote and not on one from a name. */
    unc_path_init(&p, NULL);
    CHECK(unc_path_push(&p, (const uint8_t *)"a", 1) == UNC_OK);
    CHECK(unc_path_push(&p, (const uint8_t *)"x/y", 3) == UNC_OK);
    CHECK(p.len == 5 && p.buf[1] == '/' && p.buf[3] == ':');
    unc_path_pop(&p);
    CHECK(p.len == 1 && p.depth == 1);        /* back to "a", not to "a/x" */

    /* 4. The string filling is the ONE failure, and it is counted so the
     *    pops stay balanced — four of the five walks pop by a count, and
     *    an uncounted omission misfiles every entry after it (BLOCKERS.md). */
    unc_path_init(&p, NULL);
    for (i = 0; i < 40; i++) nm[i] = (uint8_t)'w';
    for (i = 0; i < 8; i++)
        CHECK(unc_path_push(&p, nm, 31) == UNC_OK);
    CHECK(p.len == UNC_NAME_MAX);             /* 8 x 31 + 7 = 255 exactly */
    CHECK(p.truncdepth == 0);                 /* exactly full is not cut */
    CHECK(unc_path_push(&p, nm, 31) == UNC_ERR_TRUNCATED);
    CHECK(p.lost == 1);
    CHECK(p.depth == 8);                      /* the path did not move */
    CHECK(unc_path_askdepth(&p) == 9);        /* but the archive's did */
    CHECK(unc_path_push(&p, nm, 31) == UNC_ERR_TRUNCATED);
    CHECK(p.lost == 2);

    /* 5. With no host buffer the path stopped at UNC_NAME_MAX and what
     *    did not fit was never counted, so the length is 0 — the
     *    documented "the format cannot say" (macextract.h) rather than a
     *    number for a path nothing here holds. A host that offers a
     *    buffer gets the whole thing instead; `run_names.py` grades THAT
     *    on a real archive, through the CLI's 64 KB. */
    unc_entry_clear(&e);
    unc_path_leaf(&p, &e, (const uint8_t *)"leaf.txt", 8);
    CHECK(e.name_truncated == 1);
    CHECK(e.name_full_len == 0);

    /* 6. The omissions unwind before the real levels do. */
    unc_path_pop(&p);
    CHECK(p.lost == 1 && p.depth == 8);
    unc_path_pop(&p);
    CHECK(p.lost == 0 && p.depth == 8);
    unc_path_pop(&p);
    CHECK(p.depth == 7);

    /* 7. A component that PARTLY fits is a cut, not an omission: the
     *    separator is there, so the scan still finds it and the pop is
     *    exact — only the name is short. `truncdepth` marks it and comes
     *    back up with it. */
    unc_path_init(&p, NULL);
    for (i = 0; i < 7; i++)
        CHECK(unc_path_push(&p, nm, 31) == UNC_OK);
    CHECK(p.len == 223 && p.truncdepth == 0);
    CHECK(unc_path_push(&p, nm, 40) == UNC_OK);   /* 31 of 40 fit */
    CHECK(p.len == UNC_NAME_MAX);
    CHECK(p.truncdepth == 8);
    CHECK(p.lost == 0);                           /* cut, not omitted */
    unc_path_pop(&p);
    CHECK(p.depth == 7 && p.len == 223);          /* the scan still works */
    CHECK(p.truncdepth == 0);                     /* and the cut came back */
}

/* ------------------------------------------------------------------ */
/* Crafted-malformed regressions: each input tripped a memory error or  */
/* an infinite loop before the fix beside it (verified under ASan/UBSan */
/* by ci's sanitizer build).                                            */
/* ------------------------------------------------------------------ */
static void test_malformed_regressions(void)
{
    MemIO m;
    UncIO io;
    UncAlloc al;
    UncSink sk;
    CapSink cap;

    test_make_alloc(&al);

    /* MIME multipart/appledouble: an applefile NAME entry whose offset
     * (0xFFFFFFF0) wrapped the `off + elen <= got` bounds check and was
     * read far past the decoded prefix. It must be ignored, not chased.
     * The assertion that matters is that extraction RETURNS — ASan would
     * trap the out-of-bounds read otherwise. */
    {
        static const char msg[] =
            "MIME-Version: 1.0\r\n"
            "Content-Type: multipart/appledouble; boundary=\"=b=\"\r\n"
            "\r\n"
            "--=b=\r\n"
            "Content-Type: application/applefile\r\n"
            "Content-Transfer-Encoding: base64\r\n"
            "\r\n"
            "AAUWBwACAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAD////8AAAACA=\r\n"
            "--=b=\r\n"
            "Content-Type: application/octet-stream\r\n"
            "Content-Transfer-Encoding: base64\r\n"
            "\r\n"
            "TWFjCg==\r\n"
            "--=b=--\r\n";
        test_make_memio(&io, &m, (const uint8_t *)msg, (uint32_t)sizeof msg - 1);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_MIME, &io, &sk, &al, NULL, NULL)
              == UNC_OK);
        CHECK(cap.count == 1);
    }

    /* Compact Pro: a large commentlen with a host that sets no comment
     * callback advanced the index cursor past the cached index, and the
     * wrapped bounds check in cpt_index_read then read off its end. */
    {
        uint8_t cpt[108];
        memset(cpt, 0, sizeof cpt);
        cpt[0] = 1;
        unc_put_u32be(cpt + 4, 8);           /* index offset */
        cpt[13] = 1;                         /* nentries (u16be) */
        cpt[14] = 255;                       /* commentlen */
        test_make_memio(&io, &m, cpt, (uint32_t)sizeof cpt);
        cap_make(&sk, &cap);
        sk.comment = NULL;                   /* the documented no-comment host */
        CHECK(unc_extract_as(UNC_FORMAT_COMPACTPRO, &io, &sk, &al, NULL, NULL)
              != UNC_OK);                    /* an error, not an OOB read */
    }

    /* Compact Pro: an ENCRYPTED entry whose forks fall past EOF must be
     * rejected as corrupt — before, only the plain path checked the extent,
     * so the encrypted one reached the cipher and the password prompt on
     * forks that cannot be in the file. */
    {
        uint8_t cpt[62];
        memset(cpt, 0, sizeof cpt);
        cpt[0] = 1;
        unc_put_u32be(cpt + 4, 8);           /* index offset */
        cpt[13] = 1;                         /* nentries (u16be) */
        /* cpt[14] commentlen = 0 */
        cpt[15] = 0x01;                      /* entry: name length 1, a file */
        cpt[16] = 'A';                       /* name */
        cpt[17] = 1;                         /* meta[0]  filevol */
        /* meta: fileoffs 0, flags bit0 = encrypted, rcomp/dcomp past EOF */
        cpt[17 + 28] = 0x01;                 /* meta[27..28] flags = 1 */
        unc_put_u32be(cpt + 17 + 37, 0x10000000u);  /* meta[37] rcomp */
        unc_put_u32be(cpt + 17 + 41, 0x10000000u);  /* meta[41] dcomp */
        test_make_memio(&io, &m, cpt, (uint32_t)sizeof cpt);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_COMPACTPRO, &io, &sk, &al, NULL, NULL)
              == UNC_OK);
        CHECK(cap.count == 1 && cap.status[0] == UNC_ERR_CORRUPT);
    }

    /* StuffIt 5: a directory marker with a zero header size left `pos`
     * unchanged, so the walk looped forever while numentries grew. (The
     * forced extractor still runs the probe, so the banner is genuine;
     * the four year digits are wildcards.) */
    {
        static const unsigned char banner[] =
            "StuffIt (c)1997-2000 Aladdin Systems, Inc., "
            "http://www.aladdinsys.com/StuffIt/\r\n";
        uint8_t s[184];
        memset(s, 0, sizeof s);
        memcpy(s, banner, 80);
        s[82] = 5;                           /* archive version */
        s[93] = 1;                           /* numfiles (u16be) */
        unc_put_u32be(s + 94, 100);          /* first entry offset */
        unc_put_u32be(s + 100, 0xA5A5A5A5u); /* SIT5_ID */
        s[104] = 1;                          /* entry version */
        /* header size (s+106..107) stays 0 -> marker makes no progress */
        s[109] = 0x40;                       /* SIT5_DIRECTORY */
        unc_put_u32be(s + 134, 0xFFFFFFFFu); /* datalen = marker */
        test_make_memio(&io, &m, s, (uint32_t)sizeof s);
        cap_make(&sk, &cap);
        CHECK(unc_extract_as(UNC_FORMAT_SIT5, &io, &sk, &al, NULL, NULL)
              == UNC_ERR_CORRUPT);
    }
}

void run_format_tests(void)
{
    test_malformed_regressions();
    test_macbinary();
    test_macbinary_meta();
    test_applesingle();
    test_sidecar();
    test_appledouble_noname();
    test_bitin();
    test_huffman_tree();
    test_packit();
    test_canon();
    test_cpt();
    test_cpt_comment();
    test_sit();
    test_gzip();
    test_tar();
    test_zip();
    test_zip_comment();
    test_zip_behind_a_stub();
    test_zip_shrink_ticks();
    test_zip_reduce_rules();
    test_lzh_probe();
    test_cptseg_probe();
    test_lzh_extract();
    test_sitseg();
    test_zipseg();
    test_split();
    test_binhex_multi();
    test_diskdoubler();
    test_nowcompress();
    test_applelink();
    test_sqp();
    test_foreign();
    test_spacesaver();
    test_spacesaver_alg4();
    test_path_depth();
    test_spacesaver_preset();
    test_superdisk();
    test_superdisk_single();
    test_uu();
    test_arc();
    test_des();
    test_md5();
    test_rc4();
    test_cpt_cipher();
    test_winzip_aes_pieces();
    test_btoa();
    test_base64_mime();
    test_resfork_find();
}
