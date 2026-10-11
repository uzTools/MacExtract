/* sit_akscan.c — slide an 8-byte window over files and print every offset
 * whose bytes verify, against a StuffIt classic 'MKey', as the ARCHIVE KEY.
 *
 * The compiled half of tools/sit_mkey_oracle.py --scan, which in Python is
 * ~1 ms a window — hours for one 12 MB memory image of Mini vMac. The check
 * is the one `unc_crypt_sit` makes once the password is folded: decrypt the
 * MKey under the key to the archive IV, then encrypt the IV's first four
 * bytes with 00 00 00 04 behind them and compare the last four. Source:
 * `unc_crypt_sit` in src/unc_crypt.c, which cites XADStuffItDESHandle.m
 * keyForPasswordData:entryKey:MKey:. That file is INCLUDED, not copied, so
 * the DES here is the engine's own; a four-byte check passes by chance once
 * in 2^32 windows, so a hit is confirmed with `--ak` before it is believed.
 *
 *     sit_akscan MKEYHEX FILE...     prints "AKEY <file> off=<n> <key hex>"
 *
 * Built on demand by tools/sit_mkey_oracle.py, whose self-test grades it
 * against the Python verifier; nothing links it into the CLI.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "../src/unc_crypt.c"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int hexval(int c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int verify_ak(const uint8_t ak[8], const uint8_t mkey[8],
                     const uint32_t *sp)
{
    uint8_t ks[16][8], iv[8], vb[8] = { 0, 0, 0, 0, 0, 0, 0, 4 };
    int i;

    sitdes_setkey(ak, ks);
    for (i = 0; i < 8; i++) iv[i] = mkey[i];
    sitdes_crypt(iv, ks, 0, sp);
    for (i = 0; i < 4; i++) vb[i] = iv[i];
    sitdes_crypt(vb, ks, 1, sp);
    for (i = 4; i < 8; i++)
        if (vb[i] != iv[i]) return 0;
    return 1;
}

int main(int argc, char **argv)
{
    static uint32_t sp[UNC_CRYPT_TAB_WORDS];
    uint8_t mkey[8];
    int i, a;

    if (argc < 3 || strlen(argv[1]) != 16) {
        fprintf(stderr, "usage: sit_akscan MKEYHEX FILE...\n");
        return 2;
    }
    for (i = 0; i < 8; i++) {
        int h = hexval(argv[1][2 * i]), l = hexval(argv[1][2 * i + 1]);
        if (h < 0 || l < 0) {
            fprintf(stderr, "sit_akscan: MKEYHEX is not hex\n");
            return 2;
        }
        mkey[i] = (uint8_t)(h << 4 | l);
    }
    crypt_build(sp, CRYPT_TAB_DES);

    for (a = 2; a < argc; a++) {
        FILE *f = fopen(argv[a], "rb");
        uint8_t *buf;
        long sz, off;

        if (!f || fseek(f, 0, SEEK_END) != 0 || (sz = ftell(f)) < 0) {
            fprintf(stderr, "sit_akscan: cannot read %s\n", argv[a]);
            return 1;
        }
        rewind(f);
        buf = (uint8_t *)malloc(sz ? (size_t)sz : 1u);
        if (!buf || fread(buf, 1, (size_t)sz, f) != (size_t)sz) {
            fprintf(stderr, "sit_akscan: cannot read %s\n", argv[a]);
            return 1;
        }
        fclose(f);
        for (off = 0; off + 8 <= sz; off++)
            if (verify_ak(buf + off, mkey, sp)) {
                printf("AKEY %s off=%ld ", argv[a], off);
                for (i = 0; i < 8; i++) printf("%02x", buf[off + i]);
                printf("\n");
            }
        free(buf);
    }
    return 0;
}
