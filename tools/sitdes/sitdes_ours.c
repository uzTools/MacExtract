/*
 * sitdes_ours.c — this engine's StuffIt classic key code behind the same
 * command protocol as sitdes_run.c, so tools/sitdes/run_sitdes.py can put
 * one line to both and compare the answers. It includes the engine's
 * src/unc_crypt.c (path given with -DUNC_CRYPT_C) to reach its static
 * routines; the commands and their answers are sitdes_run.c's.
 *
 * `S` answers in StuffIt Engine 3.5.2's own schedule layout (CCOD -2013
 * @0x1820): round r's eight bytes at 8r, mode 1 storing round 15 - r
 * there; within a round the four subkeys for S-boxes 1, 3, 5, 7 come
 * first and those for 2, 4, 6, 8 after, each six-bit value shifted left
 * two over a tag of 1, 2, 3, 0 (docs/formats/stuffit-des-key.md).
 *
 * SPDX-License-Identifier: 0BSD
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include UNC_CRYPT_C

static void *h_alloc(void *ctx, uint32_t n) { (void)ctx; return malloc(n); }
static void h_free(void *ctx, void *p) { (void)ctx; free(p); }

static int unhex(const char *s, unsigned char *out, int cap)
{
    int n = 0;
    while (s && s[0] && s[1] && n < cap) {
        char b[3]; b[0] = s[0]; b[1] = s[1]; b[2] = 0;
        out[n++] = (unsigned char)strtoul(b, NULL, 16);
        s += 2;
    }
    return n;
}

static void hex(const unsigned char *p, int n)
{
    int i;
    for (i = 0; i < n; i++) printf("%02x", p[i]);
}

int main(void)
{
    UncAlloc al = { NULL, h_alloc, h_free };
    UncCrypt cr;
    char line[4096], *tok[8];
    uint8_t key[8], blk[8], mk[8], ek[16], ks[16][8];
    static uint8_t buf[2048], pw[600];

    memset(&cr, 0, sizeof cr);
    if (crypt_table(&cr, &al, CRYPT_TAB_DES) != UNC_OK) return 2;
    while (fgets(line, sizeof line, stdin)) {
        int nt = 0, r, k, mode;
        char *p = strtok(line, " \t\r\n");
        while (p && nt < 8) { tok[nt++] = p; p = strtok(NULL, " \t\r\n"); }
        if (nt == 0) continue;
        switch (tok[0][0]) {
        case 'S':
            unhex(tok[2], key, 8);
            mode = atoi(tok[3]);
            sitdes_setkey(key, ks);
            for (r = 0; r < 16; r++) {
                const uint8_t *s = ks[mode ? 15 - r : r];
                uint8_t o[8];
                for (k = 0; k < 4; k++) {
                    o[k] = (uint8_t)((s[2 * k] << 2) | ((k + 1) & 3));
                    o[4 + k] = (uint8_t)((s[2 * k + 1] << 2) | ((k + 1) & 3));
                }
                hex(o, 8);
            }
            break;
        case 'B':
            unhex(tok[2], key, 8);
            unhex(tok[4], blk, 8);
            sitdes_setkey(key, ks);
            sitdes_crypt(blk, ks, atoi(tok[3]) == 0, cr.tab);
            hex(blk, 8);
            break;
        case 'P': {
            /* Through the engine's own entry point, as fmt_sit.c calls
             * it: the password, the 'MKey' and the entry's sixteen
             * bytes in; the file key and IV it leaves in the cipher
             * state out, or 1 for a refusal. */
            int n = unhex(tok[1], pw, (int)sizeof pw);
            unhex(tok[2], mk, 8);
            unhex(tok[3], ek, 16);
            if (unc_crypt_sit(&cr, &al, pw, (uint16_t)n, ek, mk,
                              UNC_SIT_SCHEME_FEEDBACK) != UNC_OK) {
                printf("1");
                break;
            }
            {
                uint8_t o[16];
                unc_put_u32be(o, cr.a); unc_put_u32be(o + 4, cr.b);
                unc_put_u32be(o + 8, cr.c); unc_put_u32be(o + 12, cr.d);
                printf("0 "); hex(o, 8); printf(" "); hex(o + 8, 8);
            }
            break;
        }
        case 'X': {
            int n;
            uint8_t iv[8];
            unhex(tok[2], key, 8);
            unhex(tok[3], iv, 8);
            n = unhex(tok[4], buf, (int)sizeof buf) & ~7;
            cr.kind = UNC_CRYPT_SIT_DES; cr.blocksize = 8;
            cr.a = unc_get_u32be(key); cr.b = unc_get_u32be(key + 4);
            cr.c = unc_get_u32be(iv); cr.d = unc_get_u32be(iv + 4);
            unc_crypt_apply(&cr, buf, (uint32_t)n, 0);
            hex(buf, n);
            break;
        }
        default:
            printf("?");
        }
        printf("\n");
    }
    return 0;
}
