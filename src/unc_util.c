/*
 * unc_util.c — I/O helpers, progress pump, CRC primitives.
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "unc_internal.h"

/* ------------------------------------------------------------------ */
/* I/O helpers                                                        */
/* ------------------------------------------------------------------ */

int unc_read_full(UncIO *io, void *buf, int32_t len)
{
    uint8_t *p = (uint8_t *)buf;
    int32_t got = 0;
    while (got < len) {
        int32_t r = io->read(io->ctx, p + got, len - got);
        if (r < 0) return UNC_ERR_IO;
        if (r == 0) return UNC_ERR_TRUNCATED;
        got += r;
    }
    return UNC_OK;
}

int unc_read_at(UncIO *io, unc_off_t pos, void *buf, int32_t len)
{
    if (io->seek(io->ctx, pos) < 0) return UNC_ERR_IO;
    return unc_read_full(io, buf, len);
}

uint32_t unc_io_size32(UncIO *io)
{
    unc_off_t n = io->size(io->ctx);
    return n > (unc_off_t)UNC_U32_MAX ? UNC_U32_MAX : (uint32_t)n;
}

int unc_skip(UncIO *io, uint32_t len)
{
    unc_off_t pos = io->tell(io->ctx);
    /* Detect wraparound at whatever width offsets are carried in. */
    if (pos + len < pos) return UNC_ERR_CORRUPT;
    if (io->seek(io->ctx, pos + len) < 0) return UNC_ERR_IO;
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* Progress pump                                                      */
/* ------------------------------------------------------------------ */

int unc_progress_add(UncProgressState *ps, uint32_t n)
{
    ps->done += n;
    ps->since_tick += n;
    if (ps->since_tick >= UNC_PROGRESS_STEP) {
        ps->since_tick = 0;
        if (!ps->hold && ps->prog && ps->prog->tick &&
            !ps->prog->tick(ps->prog->ctx, ps->done, ps->total))
            return UNC_ERR_ABORTED;
    }
    return UNC_OK;
}

int unc_progress_at(UncProgressState *ps, uint32_t done)
{
    if (ps && ps->prog && ps->prog->tick &&
        !ps->prog->tick(ps->prog->ctx, done, ps->total))
        return UNC_ERR_ABORTED;
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* Entry helpers                                                      */
/* ------------------------------------------------------------------ */

void unc_entry_clear(UncEntryInfo *e)
{
    uint8_t *p = (uint8_t *)e;
    uint32_t i;
    for (i = 0; i < sizeof *e; i++) p[i] = 0;
    e->data_size = UNC_SIZE_UNKNOWN;
    e->rsrc_size = UNC_SIZE_UNKNOWN;
    e->comp_data_size = UNC_SIZE_UNKNOWN;
    e->comp_rsrc_size = UNC_SIZE_UNKNOWN;
}

int unc_entry_set_name(UncEntryInfo *e, const uint8_t *name, uint32_t len)
{
    /* Mac name component: apply the classic reversible '/'->':' swap
     * (':' cannot occur in an HFS name, '/' can), so '/' in e->name is
     * always a path separator. zip/tar set e->name directly. */
    uint32_t i;
    if (len > UNC_NAME_MAX) {   /* truncate, keep going, and SAY so */
        e->name_truncated = 1;
        e->name_full_len = (uint16_t)(len > 65535u ? 65535u : len);
        len = UNC_NAME_MAX;
    }
    for (i = 0; i < len; i++)
        e->name[i] = name[i] == '/' ? (uint8_t)':' : name[i];
    e->name[len] = 0;
    e->name_len = (uint16_t)len;
    return UNC_OK;
}

void unc_entry_set_path(UncEntryInfo *e, const uint8_t *path, uint32_t len)
{
    uint32_t i;
    if (len > UNC_NAME_MAX) {
        e->name_truncated = 1;
        e->name_full_len = (uint16_t)(len > 65535u ? 65535u : len);
        len = UNC_NAME_MAX;
    }
    for (i = 0; i < len; i++) e->name[i] = path[i];
    e->name[len] = 0;
    e->name_len = (uint16_t)len;
}

void unc_entry_long_name(UncCtx *c, UncEntryInfo *e, const uint8_t *name,
                         uint32_t len)
{
    uint32_t i, n;
    if (!c->opt.long_name || c->opt.long_name_cap < 2 || !len) return;
    n = len < c->opt.long_name_cap - 1u ? len : c->opt.long_name_cap - 1u;
    for (i = 0; i < n; i++) c->opt.long_name[i] = name[i];
    c->opt.long_name[n] = 0;
    e->name_truncated = 2;      /* 1 says it was cut; 2 says where it is */
}

void unc_entry_path_append(UncEntryInfo *e, const uint8_t *comp, uint32_t len)
{
    uint32_t o = e->name_len;
    uint32_t i;
    if (o > 0 && o < UNC_NAME_MAX) e->name[o++] = '/';
    for (i = 0; i < len && o < UNC_NAME_MAX; i++)
        e->name[o++] = comp[i] == '/' ? (uint8_t)':' : comp[i];
    if (i < len) {                        /* the component did not fit */
        uint32_t want = (uint32_t)e->name_len + (e->name_len ? 1u : 0u) + len;
        e->name_truncated = 1;
        e->name_full_len = (uint16_t)(want > 65535u ? 65535u : want);
    }
    e->name[o] = 0;
    e->name_len = (uint16_t)o;
}

/* ------------------------------------------------------------------ */
/* CRC primitives                                                     */
/*                                                                    */
/* ALL THREE TABLES ARE THEIR POLYNOMIALS, and since 2026-09-27 that  */
/* is checked rather than asserted: tools/check_crc_tables.py rebuilds */
/* each from the polynomial its PUBLISHED description states, compares */
/* all 768 entries, and runs the three standard check values. It has   */
/* a --selftest that bends one entry of each table and confirms all    */
/* three are caught, and ci.sh runs it. The tables were XADMaster's    */
/* CRC.m and macutils' arc_updcrc until that day; the file had said    */
/* "generated mechanically from the polynomials" all along and         */
/* nothing had ever checked it (DECISIONS.md 2026-09-27, *the tables   */
/* that said they were generated*).                                    */
/*                                                                    */
/* CRC-16/XMODEM: poly 0x1021, init 0, MSB-first, no final xor.       */
/*   Source: reference/notes/binhex40_lewis.txt, section "CRCs",      */
/*   which states the bitwise algorithm step by step with its initial */
/*   register. Used by MacBinary II/III (header CRC over bytes        */
/*   0..123), BinHex 4 and PackIt.                                    */
/* CRC-32: poly 0x04C11DB7 reflected (table constant 0xEDB88320),     */
/*   init/final-xor handled by callers. Source:                       */
/*   reference/notes/zip_appnote.txt, which states the polynomial and */
/*   the 0xdebb20e3 residue. Used by Arsenic, gzip, zip, Compact Pro. */
/* CRC-16/ARC: at its own table, below.                               */
/*                                                                    */
/* The standard check values xmodem("123456789")=0x31C3 and           */
/* crc32("123456789")=0xCBF43926 are asserted in tests/unit_main.c    */
/* (test_crc, with an incremental-equals-one-shot case beside them),  */
/* and crc16_arc("123456789")=0xBB3D in tests/unit_formats.c against  */
/* an independent bitwise implementation. This comment named          */
/* tests/unit_util.c until 2026-09-26; no such file ever existed.     */
/* ------------------------------------------------------------------ */

static const uint16_t unc_crc16_table[256] = {
    0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50a5, 0x60c6, 0x70e7,
    0x8108, 0x9129, 0xa14a, 0xb16b, 0xc18c, 0xd1ad, 0xe1ce, 0xf1ef,
    0x1231, 0x0210, 0x3273, 0x2252, 0x52b5, 0x4294, 0x72f7, 0x62d6,
    0x9339, 0x8318, 0xb37b, 0xa35a, 0xd3bd, 0xc39c, 0xf3ff, 0xe3de,
    0x2462, 0x3443, 0x0420, 0x1401, 0x64e6, 0x74c7, 0x44a4, 0x5485,
    0xa56a, 0xb54b, 0x8528, 0x9509, 0xe5ee, 0xf5cf, 0xc5ac, 0xd58d,
    0x3653, 0x2672, 0x1611, 0x0630, 0x76d7, 0x66f6, 0x5695, 0x46b4,
    0xb75b, 0xa77a, 0x9719, 0x8738, 0xf7df, 0xe7fe, 0xd79d, 0xc7bc,
    0x48c4, 0x58e5, 0x6886, 0x78a7, 0x0840, 0x1861, 0x2802, 0x3823,
    0xc9cc, 0xd9ed, 0xe98e, 0xf9af, 0x8948, 0x9969, 0xa90a, 0xb92b,
    0x5af5, 0x4ad4, 0x7ab7, 0x6a96, 0x1a71, 0x0a50, 0x3a33, 0x2a12,
    0xdbfd, 0xcbdc, 0xfbbf, 0xeb9e, 0x9b79, 0x8b58, 0xbb3b, 0xab1a,
    0x6ca6, 0x7c87, 0x4ce4, 0x5cc5, 0x2c22, 0x3c03, 0x0c60, 0x1c41,
    0xedae, 0xfd8f, 0xcdec, 0xddcd, 0xad2a, 0xbd0b, 0x8d68, 0x9d49,
    0x7e97, 0x6eb6, 0x5ed5, 0x4ef4, 0x3e13, 0x2e32, 0x1e51, 0x0e70,
    0xff9f, 0xefbe, 0xdfdd, 0xcffc, 0xbf1b, 0xaf3a, 0x9f59, 0x8f78,
    0x9188, 0x81a9, 0xb1ca, 0xa1eb, 0xd10c, 0xc12d, 0xf14e, 0xe16f,
    0x1080, 0x00a1, 0x30c2, 0x20e3, 0x5004, 0x4025, 0x7046, 0x6067,
    0x83b9, 0x9398, 0xa3fb, 0xb3da, 0xc33d, 0xd31c, 0xe37f, 0xf35e,
    0x02b1, 0x1290, 0x22f3, 0x32d2, 0x4235, 0x5214, 0x6277, 0x7256,
    0xb5ea, 0xa5cb, 0x95a8, 0x8589, 0xf56e, 0xe54f, 0xd52c, 0xc50d,
    0x34e2, 0x24c3, 0x14a0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
    0xa7db, 0xb7fa, 0x8799, 0x97b8, 0xe75f, 0xf77e, 0xc71d, 0xd73c,
    0x26d3, 0x36f2, 0x0691, 0x16b0, 0x6657, 0x7676, 0x4615, 0x5634,
    0xd94c, 0xc96d, 0xf90e, 0xe92f, 0x99c8, 0x89e9, 0xb98a, 0xa9ab,
    0x5844, 0x4865, 0x7806, 0x6827, 0x18c0, 0x08e1, 0x3882, 0x28a3,
    0xcb7d, 0xdb5c, 0xeb3f, 0xfb1e, 0x8bf9, 0x9bd8, 0xabbb, 0xbb9a,
    0x4a75, 0x5a54, 0x6a37, 0x7a16, 0x0af1, 0x1ad0, 0x2ab3, 0x3a92,
    0xfd2e, 0xed0f, 0xdd6c, 0xcd4d, 0xbdaa, 0xad8b, 0x9de8, 0x8dc9,
    0x7c26, 0x6c07, 0x5c64, 0x4c45, 0x3ca2, 0x2c83, 0x1ce0, 0x0cc1,
    0xef1f, 0xff3e, 0xcf5d, 0xdf7c, 0xaf9b, 0xbfba, 0x8fd9, 0x9ff8,
    0x6e17, 0x7e36, 0x4e55, 0x5e74, 0x2e93, 0x3eb2, 0x0ed1, 0x1ef0,
};

static const uint32_t unc_crc32_table[256] = {
    0x00000000, 0x77073096, 0xee0e612c, 0x990951ba, 0x076dc419, 0x706af48f,
    0xe963a535, 0x9e6495a3, 0x0edb8832, 0x79dcb8a4, 0xe0d5e91e, 0x97d2d988,
    0x09b64c2b, 0x7eb17cbd, 0xe7b82d07, 0x90bf1d91, 0x1db71064, 0x6ab020f2,
    0xf3b97148, 0x84be41de, 0x1adad47d, 0x6ddde4eb, 0xf4d4b551, 0x83d385c7,
    0x136c9856, 0x646ba8c0, 0xfd62f97a, 0x8a65c9ec, 0x14015c4f, 0x63066cd9,
    0xfa0f3d63, 0x8d080df5, 0x3b6e20c8, 0x4c69105e, 0xd56041e4, 0xa2677172,
    0x3c03e4d1, 0x4b04d447, 0xd20d85fd, 0xa50ab56b, 0x35b5a8fa, 0x42b2986c,
    0xdbbbc9d6, 0xacbcf940, 0x32d86ce3, 0x45df5c75, 0xdcd60dcf, 0xabd13d59,
    0x26d930ac, 0x51de003a, 0xc8d75180, 0xbfd06116, 0x21b4f4b5, 0x56b3c423,
    0xcfba9599, 0xb8bda50f, 0x2802b89e, 0x5f058808, 0xc60cd9b2, 0xb10be924,
    0x2f6f7c87, 0x58684c11, 0xc1611dab, 0xb6662d3d, 0x76dc4190, 0x01db7106,
    0x98d220bc, 0xefd5102a, 0x71b18589, 0x06b6b51f, 0x9fbfe4a5, 0xe8b8d433,
    0x7807c9a2, 0x0f00f934, 0x9609a88e, 0xe10e9818, 0x7f6a0dbb, 0x086d3d2d,
    0x91646c97, 0xe6635c01, 0x6b6b51f4, 0x1c6c6162, 0x856530d8, 0xf262004e,
    0x6c0695ed, 0x1b01a57b, 0x8208f4c1, 0xf50fc457, 0x65b0d9c6, 0x12b7e950,
    0x8bbeb8ea, 0xfcb9887c, 0x62dd1ddf, 0x15da2d49, 0x8cd37cf3, 0xfbd44c65,
    0x4db26158, 0x3ab551ce, 0xa3bc0074, 0xd4bb30e2, 0x4adfa541, 0x3dd895d7,
    0xa4d1c46d, 0xd3d6f4fb, 0x4369e96a, 0x346ed9fc, 0xad678846, 0xda60b8d0,
    0x44042d73, 0x33031de5, 0xaa0a4c5f, 0xdd0d7cc9, 0x5005713c, 0x270241aa,
    0xbe0b1010, 0xc90c2086, 0x5768b525, 0x206f85b3, 0xb966d409, 0xce61e49f,
    0x5edef90e, 0x29d9c998, 0xb0d09822, 0xc7d7a8b4, 0x59b33d17, 0x2eb40d81,
    0xb7bd5c3b, 0xc0ba6cad, 0xedb88320, 0x9abfb3b6, 0x03b6e20c, 0x74b1d29a,
    0xead54739, 0x9dd277af, 0x04db2615, 0x73dc1683, 0xe3630b12, 0x94643b84,
    0x0d6d6a3e, 0x7a6a5aa8, 0xe40ecf0b, 0x9309ff9d, 0x0a00ae27, 0x7d079eb1,
    0xf00f9344, 0x8708a3d2, 0x1e01f268, 0x6906c2fe, 0xf762575d, 0x806567cb,
    0x196c3671, 0x6e6b06e7, 0xfed41b76, 0x89d32be0, 0x10da7a5a, 0x67dd4acc,
    0xf9b9df6f, 0x8ebeeff9, 0x17b7be43, 0x60b08ed5, 0xd6d6a3e8, 0xa1d1937e,
    0x38d8c2c4, 0x4fdff252, 0xd1bb67f1, 0xa6bc5767, 0x3fb506dd, 0x48b2364b,
    0xd80d2bda, 0xaf0a1b4c, 0x36034af6, 0x41047a60, 0xdf60efc3, 0xa867df55,
    0x316e8eef, 0x4669be79, 0xcb61b38c, 0xbc66831a, 0x256fd2a0, 0x5268e236,
    0xcc0c7795, 0xbb0b4703, 0x220216b9, 0x5505262f, 0xc5ba3bbe, 0xb2bd0b28,
    0x2bb45a92, 0x5cb36a04, 0xc2d7ffa7, 0xb5d0cf31, 0x2cd99e8b, 0x5bdeae1d,
    0x9b64c2b0, 0xec63f226, 0x756aa39c, 0x026d930a, 0x9c0906a9, 0xeb0e363f,
    0x72076785, 0x05005713, 0x95bf4a82, 0xe2b87a14, 0x7bb12bae, 0x0cb61b38,
    0x92d28e9b, 0xe5d5be0d, 0x7cdcefb7, 0x0bdbdf21, 0x86d3d2d4, 0xf1d4e242,
    0x68ddb3f8, 0x1fda836e, 0x81be16cd, 0xf6b9265b, 0x6fb077e1, 0x18b74777,
    0x88085ae6, 0xff0f6a70, 0x66063bca, 0x11010b5c, 0x8f659eff, 0xf862ae69,
    0x616bffd3, 0x166ccf45, 0xa00ae278, 0xd70dd2ee, 0x4e048354, 0x3903b3c2,
    0xa7672661, 0xd06016f7, 0x4969474d, 0x3e6e77db, 0xaed16a4a, 0xd9d65adc,
    0x40df0b66, 0x37d83bf0, 0xa9bcae53, 0xdebb9ec5, 0x47b2cf7f, 0x30b5ffe9,
    0xbdbdf21c, 0xcabac28a, 0x53b39330, 0x24b4a3a6, 0xbad03605, 0xcdd70693,
    0x54de5729, 0x23d967bf, 0xb3667a2e, 0xc4614ab8, 0x5d681b02, 0x2a6f2b94,
    0xb40bbe37, 0xc30c8ea1, 0x5a05df1b, 0x2d02ef8d,
};

/* CRC-16/ARC: poly 0xA001 (reflected), init 0, no final xor.
 * Used by StuffIt classic header and fork CRCs.
 * Source: the polynomial, 0x8005 reflected to 0xA001 — which is what
 * reference/deark (MIT) and reference/lhasa (ISC) each BUILD this
 * table from rather than listing it, and what tools/check_crc_tables.py
 * builds it from here. It was XADMaster's CRC.m (XADCRCTable_a001) and
 * macutils' arc_updcrc until 2026-09-27.
 * Check value: crc16_arc("123456789") = 0xBB3D (tests/unit_formats.c,
 * beside an independent bitwise implementation). */
static const uint16_t unc_crc16_arc_table[256] = {
    0x0000, 0xc0c1, 0xc181, 0x0140, 0xc301, 0x03c0, 0x0280, 0xc241,
    0xc601, 0x06c0, 0x0780, 0xc741, 0x0500, 0xc5c1, 0xc481, 0x0440,
    0xcc01, 0x0cc0, 0x0d80, 0xcd41, 0x0f00, 0xcfc1, 0xce81, 0x0e40,
    0x0a00, 0xcac1, 0xcb81, 0x0b40, 0xc901, 0x09c0, 0x0880, 0xc841,
    0xd801, 0x18c0, 0x1980, 0xd941, 0x1b00, 0xdbc1, 0xda81, 0x1a40,
    0x1e00, 0xdec1, 0xdf81, 0x1f40, 0xdd01, 0x1dc0, 0x1c80, 0xdc41,
    0x1400, 0xd4c1, 0xd581, 0x1540, 0xd701, 0x17c0, 0x1680, 0xd641,
    0xd201, 0x12c0, 0x1380, 0xd341, 0x1100, 0xd1c1, 0xd081, 0x1040,
    0xf001, 0x30c0, 0x3180, 0xf141, 0x3300, 0xf3c1, 0xf281, 0x3240,
    0x3600, 0xf6c1, 0xf781, 0x3740, 0xf501, 0x35c0, 0x3480, 0xf441,
    0x3c00, 0xfcc1, 0xfd81, 0x3d40, 0xff01, 0x3fc0, 0x3e80, 0xfe41,
    0xfa01, 0x3ac0, 0x3b80, 0xfb41, 0x3900, 0xf9c1, 0xf881, 0x3840,
    0x2800, 0xe8c1, 0xe981, 0x2940, 0xeb01, 0x2bc0, 0x2a80, 0xea41,
    0xee01, 0x2ec0, 0x2f80, 0xef41, 0x2d00, 0xedc1, 0xec81, 0x2c40,
    0xe401, 0x24c0, 0x2580, 0xe541, 0x2700, 0xe7c1, 0xe681, 0x2640,
    0x2200, 0xe2c1, 0xe381, 0x2340, 0xe101, 0x21c0, 0x2080, 0xe041,
    0xa001, 0x60c0, 0x6180, 0xa141, 0x6300, 0xa3c1, 0xa281, 0x6240,
    0x6600, 0xa6c1, 0xa781, 0x6740, 0xa501, 0x65c0, 0x6480, 0xa441,
    0x6c00, 0xacc1, 0xad81, 0x6d40, 0xaf01, 0x6fc0, 0x6e80, 0xae41,
    0xaa01, 0x6ac0, 0x6b80, 0xab41, 0x6900, 0xa9c1, 0xa881, 0x6840,
    0x7800, 0xb8c1, 0xb981, 0x7940, 0xbb01, 0x7bc0, 0x7a80, 0xba41,
    0xbe01, 0x7ec0, 0x7f80, 0xbf41, 0x7d00, 0xbdc1, 0xbc81, 0x7c40,
    0xb401, 0x74c0, 0x7580, 0xb541, 0x7700, 0xb7c1, 0xb681, 0x7640,
    0x7200, 0xb2c1, 0xb381, 0x7340, 0xb101, 0x71c0, 0x7080, 0xb041,
    0x5000, 0x90c1, 0x9181, 0x5140, 0x9301, 0x53c0, 0x5280, 0x9241,
    0x9601, 0x56c0, 0x5780, 0x9741, 0x5500, 0x95c1, 0x9481, 0x5440,
    0x9c01, 0x5cc0, 0x5d80, 0x9d41, 0x5f00, 0x9fc1, 0x9e81, 0x5e40,
    0x5a00, 0x9ac1, 0x9b81, 0x5b40, 0x9901, 0x59c0, 0x5880, 0x9841,
    0x8801, 0x48c0, 0x4980, 0x8941, 0x4b00, 0x8bc1, 0x8a81, 0x4a40,
    0x4e00, 0x8ec1, 0x8f81, 0x4f40, 0x8d01, 0x4dc0, 0x4c80, 0x8c41,
    0x4400, 0x84c1, 0x8581, 0x4540, 0x8701, 0x47c0, 0x4680, 0x8641,
    0x8201, 0x42c0, 0x4380, 0x8341, 0x4100, 0x81c1, 0x8081, 0x4040,
};

UNC_HOT uint16_t unc_crc16_arc(uint16_t crc, const uint8_t *buf, int32_t len)
{
    while (len >= 4) {
        crc = (uint16_t)((crc >> 8) ^ unc_crc16_arc_table[(crc ^ *buf++) & 0xFF]);
        crc = (uint16_t)((crc >> 8) ^ unc_crc16_arc_table[(crc ^ *buf++) & 0xFF]);
        crc = (uint16_t)((crc >> 8) ^ unc_crc16_arc_table[(crc ^ *buf++) & 0xFF]);
        crc = (uint16_t)((crc >> 8) ^ unc_crc16_arc_table[(crc ^ *buf++) & 0xFF]);
        len -= 4;
    }
    while (len-- > 0)
        crc = (uint16_t)((crc >> 8) ^ unc_crc16_arc_table[(crc ^ *buf++) & 0xFF]);
    return crc;
}

uint16_t unc_crc16_xmodem(uint16_t crc, const uint8_t *buf, int32_t len)
{
    while (len >= 4) {
        crc = (uint16_t)((crc << 8) ^ unc_crc16_table[((crc >> 8) ^ *buf++) & 0xFF]);
        crc = (uint16_t)((crc << 8) ^ unc_crc16_table[((crc >> 8) ^ *buf++) & 0xFF]);
        crc = (uint16_t)((crc << 8) ^ unc_crc16_table[((crc >> 8) ^ *buf++) & 0xFF]);
        crc = (uint16_t)((crc << 8) ^ unc_crc16_table[((crc >> 8) ^ *buf++) & 0xFF]);
        len -= 4;
    }
    while (len-- > 0)
        crc = (uint16_t)((crc << 8) ^ unc_crc16_table[((crc >> 8) ^ *buf++) & 0xFF]);
    return crc;
}

/* Four bytes per loop test, walked with a pointer.
 *
 * This is the single most shared loop in the engine — every format's fork
 * CRC comes through one of these three — and it was 40.7 % of a gzip
 * extraction, where zlib does the inflating and this does everything else.
 * The body is already minimal; what the unrolling removes is the index
 * arithmetic and three quarters of the loop test.
 *
 * NOT slicing-by-4, which is the usual next step and would want aligned
 * 32-bit reads of the input: the 68000 discipline forbids those, and a
 * table four times the size is 3 KB of A5 world for every build. Bytes in,
 * one table, same answer. */
uint32_t unc_crc32(uint32_t crc, const uint8_t *buf, int32_t len)
{
    while (len >= 4) {
        crc = (crc >> 8) ^ unc_crc32_table[(crc ^ *buf++) & 0xFF];
        crc = (crc >> 8) ^ unc_crc32_table[(crc ^ *buf++) & 0xFF];
        crc = (crc >> 8) ^ unc_crc32_table[(crc ^ *buf++) & 0xFF];
        crc = (crc >> 8) ^ unc_crc32_table[(crc ^ *buf++) & 0xFF];
        len -= 4;
    }
    while (len-- > 0)
        crc = (crc >> 8) ^ unc_crc32_table[(crc ^ *buf++) & 0xFF];
    return crc;
}

/* ------------------------------------------------------------------ */
/* Buffered byte-wise input                                           */
/* ------------------------------------------------------------------ */

void unc_bufin_init(UncBufIn *b, UncIO *io, UncProgressState *ps,
                    uint8_t *storage, uint32_t cap)
{
    b->io = io;
    b->ps = ps;
    b->buf = storage;
    b->cap = cap;
    b->len = b->pos = 0;
    b->lenfed = 0;
    b->limit = UNC_U32_MAX;
    b->crypt = NULL;
    b->err = UNC_OK;
}

/* Absolute stream position: what has been pulled from io, less what is
 * still sitting unread in the buffer. */
uint32_t unc_bufin_tell(const UncBufIn *b)
{
    return b->lenfed - (b->len - b->pos);
}

/* Consume forward to an absolute position. Going backwards is a caller
 * bug (a decoder that needs it must seek the io and re-init instead). */
int unc_bufin_skip_to(UncBufIn *b, uint32_t abs)
{
    uint32_t at = unc_bufin_tell(b);
    if (abs < at) return UNC_ERR_CORRUPT;
    while (at < abs) {
        uint32_t chunk = abs - at;
        if (b->pos < b->len) {
            uint32_t have = b->len - b->pos;
            if (chunk > have) chunk = have;
            b->pos += chunk;
        } else {
            if (unc_bufin_next(b) < 0) return b->err;
            chunk = 1;
        }
        at += chunk;
    }
    return UNC_OK;
}

/* A UncBufIn over bytes already in memory: the same reader, with the
 * buffer pre-filled and its limit set so a read past the end reports
 * truncation instead of reaching for an io that is not there. Now
 * Compress needs it — it decompresses block-to-block inside RAM and
 * still wants the shared bit reader and canonical-Huffman decoder. */
void unc_bufin_init_mem(UncBufIn *b, const uint8_t *mem, uint32_t len)
{
    b->io = NULL;
    b->ps = NULL;
    b->buf = (uint8_t *)mem;
    b->cap = len;
    b->len = len;
    b->pos = 0;
    b->lenfed = len;
    b->limit = len;
    b->crypt = NULL;   /* the bytes are already plain: a caller with a
                        * cipher decrypts them before handing them over */
    b->err = UNC_OK;
}

int unc_bufin_next_slow(UncBufIn *b)
{
    int32_t r;
    uint32_t want = b->cap, at = b->lenfed;
    if (b->err != UNC_OK) return -1;   /* sticky */
    if (b->limit - b->lenfed < want) want = b->limit - b->lenfed;
    if (want == 0) { b->err = UNC_ERR_TRUNCATED; return -1; }
    if (b->crypt && b->crypt->blocksize > 1) {
        /* A block cipher cannot decrypt half a block, and io->read is
         * allowed to come up short, so fill the buffer rather than take
         * what arrives. At a genuine EOF the tail is padded to the block
         * size, and THE PAD VALUE CANNOT BE OBSERVED — measured
         * 2026-09-27, not reasoned: this path executes 3 times over
         * tools/run_crypt.py's 45 cases, and the suite is byte-for-byte
         * green with the pad changed to 0xA5. Zero is kept because it is
         * what the reference handles use (XADPackItDESHandle memsets the
         * block), but nothing depends on it, so the citation is a note
         * and not a source. */
        uint32_t got = 0;
        want -= want % b->crypt->blocksize;
        if (want == 0) want = b->crypt->blocksize;
        if (want > b->cap) want = b->cap;
        while (got < want) {
            int32_t n = b->io->read(b->io->ctx, b->buf + got,
                                    (int32_t)(want - got));
            if (n < 0)  { b->err = UNC_ERR_IO; return -1; }
            if (n == 0) break;
            got += (uint32_t)n;
        }
        if (got == 0) { b->err = UNC_ERR_TRUNCATED; return -1; }
        while (got % b->crypt->blocksize) b->buf[got++] = 0;
        r = (int32_t)got;
    } else {
        r = b->io->read(b->io->ctx, b->buf, (int32_t)want);
        if (r < 0)  { b->err = UNC_ERR_IO; return -1; }
        if (r == 0) { b->err = UNC_ERR_TRUNCATED; return -1; }
    }
    b->len = (uint32_t)r;
    b->pos = 0;
    b->lenfed += (uint32_t)r;
    if (b->crypt) unc_crypt_apply(b->crypt, b->buf, b->len, at);
    if (b->ps) {
        int e = unc_progress_add(b->ps, (uint32_t)r);
        if (e != UNC_OK) { b->err = e; return -1; }
    }
    return b->buf[b->pos++];
}

/* See unc_internal.h for what this reader does that fmt_uu.c's and
 * fmt_btoa.c's do not: it takes CRLF as one terminator. */
int unc_readline(UncBufIn *in, uint8_t *buf, int32_t cap, int32_t *len,
                 int *eof)
{
    int32_t n = 0;

    for (;;) {
        int c = unc_bufin_next(in);
        if (c < 0) {
            if (in->err != UNC_ERR_TRUNCATED) return in->err;
            *eof = 1;
            break;
        }
        if (c == '\r') {
            if (unc_bufin_peek(in) == '\n') (void)unc_bufin_next(in);
            break;
        }
        if (c == '\n') break;
        if (n < cap - 1) buf[n++] = (uint8_t)c;
    }
    buf[n] = 0;
    *len = n;
    if (*eof && n == 0) return UNC_ERR_TRUNCATED;
    return UNC_OK;
}

/* ------------------------------------------------------------------ */
/* Sink helpers                                                       */
/* ------------------------------------------------------------------ */

int unc_copy_fork(UncCtx *c, UncFork fork, uint32_t size,
                  uint8_t *buf, uint32_t bufsz)
{
    uint32_t left = size;
    while (left > 0) {
        int32_t want = (int32_t)(left < bufsz ? left : bufsz);
        int32_t r = c->io->read(c->io->ctx, buf, want);
        int e;
        if (r < 0) return UNC_ERR_IO;
        if (r == 0) return UNC_ERR_TRUNCATED;
        if (!c->opt.test_only &&
            c->sink->write(c->sink->ctx, fork, buf, r) < 0)
            return UNC_ERR_SINK;
        left -= (uint32_t)r;
        e = unc_progress_add(&c->ps, (uint32_t)r);
        if (e != UNC_OK) return e;
    }
    return UNC_OK;
}

void unc_fork_out(UncForkOut *o, UncCtx *c, UncFork fork, int write,
                  int ck, uint8_t *buf, uint32_t cap)
{
    o->c = c;
    o->fork = fork;
    o->buf = buf;
    o->cap = cap;
    o->len = 0;
    o->written = 0;
    o->ck = (uint8_t)ck;
    o->write = (uint8_t)(write != 0);
    o->split = 0;
    o->crc16 = 0;
    o->crc32 = 0;
    o->dstart = o->dend = o->rstart = o->rend = 0;
    o->delta = o->dacc = o->skip = 0;
    o->skipval = 0;
}

void unc_fork_split(UncForkOut *o, uint32_t dstart, uint32_t dend,
                    uint32_t rstart, uint32_t rend)
{
    o->split = 1;
    o->dstart = dstart;
    o->dend = dend;
    o->rstart = rstart;
    o->rend = rend;
}

/* The part of the staged run that falls inside [start, end), to `fork`. */
static int fork_span(UncForkOut *o, UncFork fork, uint32_t start, uint32_t end)
{
    uint32_t from = o->written, to = o->written + o->len;
    if (from < start) from = start;
    if (to > end) to = end;
    if (from >= to) return UNC_OK;
    if (o->c->sink->write(o->c->sink->ctx, fork,
                          o->buf + (from - o->written),
                          (int32_t)(to - from)) != 0)
        return UNC_ERR_SINK;
    return UNC_OK;
}

int unc_fork_write(UncForkOut *o, const uint8_t *p, uint32_t n)
{
    /* The inline put, in a loop: on a 68000 a byte loop is what a copy
     * is anyway, and this is 100 B smaller than chunking into the
     * staging buffer (measured 2026-09-18). */
    while (n-- > 0) {
        int err = unc_fork_put(o, *p++);
        if (err != UNC_OK) return err;
    }
    return UNC_OK;
}

int unc_fork_flush(UncForkOut *o)
{
    int err = UNC_OK;

    if (o->len == 0) return UNC_OK;

    /* An Optimizer's output is turned back into the file here, ahead of
     * the checksum and the sink, so that everything downstream — the
     * CRC, `written`, the split spans — sees the restored bytes and
     * nothing else has to know. Source: the modules' own 'DCMP'
     * resources, disassembled (FORMATS.md, *What an Optimizer did to
     * the fork*). */
    if (o->skip) {
        uint32_t n = o->skip < o->len ? o->skip : o->len, i;
        for (i = 0; i < n; i++)
            o->skipval = (o->skipval << 8) | o->buf[i];
        o->len -= n;
        o->skip = (uint8_t)(o->skip - n);
        for (i = 0; i < o->len; i++) o->buf[i] = o->buf[i + n];
        if (o->len == 0) return UNC_OK;
    }
    if (o->delta) {
        uint32_t i;
        uint8_t a = o->dacc;
        for (i = 0; i < o->len; i++) {
            a = (uint8_t)(a + o->buf[i]);
            o->buf[i] = a;
        }
        o->dacc = a;
    }

    /* The checksum is over what was DECODED, so it is taken whether or
     * not the bytes are written: a test-only run and a password
     * candidate are both graded by it. */
    switch (o->ck) {
    case UNC_CK_CRC16_ARC:
        o->crc16 = unc_crc16_arc(o->crc16, o->buf, (int32_t)o->len);
        break;
    case UNC_CK_CRC32_16:
        o->crc16 = unc_crc16_arc(o->crc16, o->buf, (int32_t)o->len);
        /* fall through */
    case UNC_CK_CRC32:
        o->crc32 = unc_crc32(o->crc32, o->buf, (int32_t)o->len);
        break;
    default:
        break;
    }

    if (o->write) {
        if (o->split) {
            err = fork_span(o, UNC_FORK_DATA, o->dstart, o->dend);
            if (err == UNC_OK)
                err = fork_span(o, UNC_FORK_RSRC, o->rstart, o->rend);
        } else if (o->c->sink->write(o->c->sink->ctx, o->fork, o->buf,
                                     (int32_t)o->len) < 0) {
            err = UNC_ERR_SINK;
        }
    }

    o->written += o->len;
    o->len = 0;
    return err;
}

/* ------------------------------------------------------------------ */
/* A folder path being walked                                         */
/* ------------------------------------------------------------------ */

/* The host's long-name buffer, or NULL when there is none to write to.
 * Two bytes is the smallest one that can hold anything at all. */
static uint8_t *path_longbuf(const UncPath *p, uint32_t *cap)
{
    if (!p->c || !p->c->opt.long_name || p->c->opt.long_name_cap < 2)
        return NULL;
    *cap = p->c->opt.long_name_cap;
    return p->c->opt.long_name;
}

/* Add one component to the uncut path: write what fits at `at` in the
 * host's buffer, and return where the next component would start.
 * Counting continues past the end of that buffer — that is how the
 * caller learns the whole name did not fit — and saturates at 65,535,
 * which is all `name_full_len` can carry. */
static uint32_t path_full_add(const UncPath *p, uint32_t at,
                              const uint8_t *name, uint32_t nlen)
{
    uint32_t cap = 0, i, room;
    uint8_t *out = path_longbuf(p, &cap);
    if (!out) {                              /* nothing to write: count */
        uint32_t want = at + (at ? 1u : 0u) + nlen;
        return want > 65535u ? 65535u : want;
    }
    room = cap - 1u;                         /* keep one for the NUL */
    if (at) {
        if (at < room) out[at] = '/';
        if (at < 65535u) at++;
    }
    for (i = 0; i < nlen; i++) {
        uint8_t ch = name[i] == '/' ? (uint8_t)':' : name[i];
        if (at < room) out[at] = ch;
        if (at >= 65535u) break;
        at++;
    }
    return at;
}

void unc_path_init(UncPath *p, struct UncCtx *c)
{
    p->len = 0;
    p->depth = 0;
    p->truncdepth = 0;
    p->buf[0] = 0;
    p->c = c;
    p->full = 0;
    p->lost = 0;
}

int unc_path_push(UncPath *p, const uint8_t *name, uint32_t nlen)
{
    uint32_t i;
    /* Too deep: leave the path alone and COUNT the refusal, so that the
     * pop this descent will be matched by undoes the refusal instead of
     * a level that was never pushed. `lost` can only become nonzero at
     * the limit, and a pop clears it before `depth` moves, so a refusal
     * while shallower than the limit is impossible — the test is there
     * to keep it that way. */
    if (p->depth >= UNC_PATH_MAXDEPTH || p->lost) {
        p->lost++;
        return UNC_ERR_TOODEEP;
    }
    p->fullstack[p->depth] = p->full;
    p->stack[p->depth++] = p->len;
    if (p->len && p->len < UNC_NAME_MAX) p->buf[p->len++] = '/';
    for (i = 0; i < nlen && p->len < UNC_NAME_MAX; i++) {
        uint8_t ch = name[i];
        p->buf[p->len++] = (uint8_t)(ch == '/' ? ':' : ch);
    }
    if (i < nlen && !p->truncdepth) p->truncdepth = p->depth;
    p->buf[p->len] = 0;
    p->full = (uint16_t)path_full_add(p, p->full, name, nlen);
    return UNC_OK;
}

void unc_path_pop(UncPath *p)
{
    if (p->lost) { p->lost--; return; }      /* undo a refused push */
    if (p->depth > 0) {
        p->full = p->fullstack[p->depth - 1];
        p->len = p->stack[--p->depth];
    }
    if (p->truncdepth > p->depth) p->truncdepth = 0;
    p->buf[p->len] = 0;
}

void unc_path_leaf(const UncPath *p, UncEntryInfo *e,
                   const uint8_t *name, uint32_t nlen)
{
    uint8_t full[UNC_NAME_MAX + 1];
    uint32_t n = p->len, i, want, cap = 0;
    uint8_t *out;
    if (n > UNC_NAME_MAX) n = UNC_NAME_MAX;
    for (i = 0; i < n; i++) full[i] = p->buf[i];
    if (n && n < UNC_NAME_MAX) full[n++] = '/';
    for (i = 0; i < nlen && n < UNC_NAME_MAX; i++) {
        uint8_t ch = name[i];
        full[n++] = (uint8_t)(ch == '/' ? ':' : ch);
    }
    /* The uncut path is assembled whether or not this entry needs it:
     * a folder cut on the way down was cut before anyone knew which
     * leaf would want the length back. */
    want = path_full_add(p, p->full, name, nlen);
    unc_entry_set_path(e, full, n);
    /* The walk could not descend this far, so `full` above is the path
     * with its deepest folders missing — reported here rather than only
     * through end_entry, because a host that declines an entry never
     * hears that (macextract.h, path_too_deep). */
    if (p->lost) e->path_too_deep = 1;
    if (i < nlen || p->truncdepth) {
        e->name_truncated = 1;
        /* `want` and the long buffer describe the path the walk COULD
         * represent. Where it could not descend, that is a path with
         * folders missing from the middle of it, so neither is this
         * entry's name: the length would be a number that describes
         * nothing, and `name_truncated` 2 would promise a host the whole
         * name and hand it a shorter real-looking path. 0 is the
         * documented "the format cannot say" (macextract.h), and the
         * entry is already failing with UNC_ERR_TOODEEP.
         *
         * Measured 2026-10-07 on an archive nested 30 deep whose folder
         * names are 31 characters, so both limits fire: the CLI printed
         * `.../D24.../f30.txt` as "the archive's name" for an entry whose
         * name has six more folders in it. */
        if (p->lost) {
            e->name_full_len = 0;
            return;
        }
        e->name_full_len = (uint16_t)want;
        out = path_longbuf(p, &cap);
        if (out && want < cap) {         /* every byte of it is in there */
            out[want] = 0;
            e->name_truncated = 2;
        }
    }
}
