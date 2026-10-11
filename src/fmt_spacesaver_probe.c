/* fmt_spacesaver_probe.c — SpaceSaver's probe, kept resident.
 *
 * Split out of fmt_spacesaver.c on 2026-09-02 so the decoder can be an
 * overlay. `unc_sniff` calls this for every file it is given; if it lived in
 * the overlay, sniffing anything at all would load 16 KB of decoder and the
 * on-demand loading would buy nothing. The rest of the format —
 * unc_spacesaver_extract and everything under it — is what moves.
 *
 * Source: unchanged from fmt_spacesaver.c, whose provenance comment stands.
 *
 * License: LGPL-2.1-or-later. See LICENSE and NOTICE.
 */
#include "fmt_spacesaver_priv.h"

void ss_parse(const uint8_t *h, SsHead *o)
{
    o->version = unc_get_u32be(h + 8);
    o->flags   = unc_get_u32be(h + 16);
    if (o->version >= 3) {
        int i;
        for (i = 0; i < 2; i++) {
            const uint8_t *r = h + (i ? 36 : 20);
            o->fork[i].clen   = unc_get_u32be(r);
            o->fork[i].ulen   = unc_get_u32be(r + 4);
            o->fork[i].off    = unc_get_u32be(r + 8);
            o->fork[i].pset   = r[12];
            o->fork[i].method = r[13];
        }
        o->type         = unc_get_u32be(h + 52);
        o->creator      = unc_get_u32be(h + 56);
        o->finder_flags = unc_get_u16be(h + 60);
        return;
    }
    o->fork[0].clen   = unc_get_u32be(h + 24);
    o->fork[0].ulen   = unc_get_u32be(h + 32);
    o->fork[0].off    = SS_HDRLEN;
    o->fork[0].pset   = 0;
    o->fork[0].method = h[21];
    o->fork[1].clen   = unc_get_u32be(h + 28);
    o->fork[1].ulen   = unc_get_u32be(h + 36);
    o->fork[1].off    = SS_HDRLEN + o->fork[0].clen;
    o->fork[1].pset   = 0;
    o->fork[1].method = h[21];
    o->type         = unc_get_u32be(h + 40);
    o->creator      = unc_get_u32be(h + 44);
    o->finder_flags = unc_get_u16be(h + 48);
}

int ss_head_ok(const SsHead *o)
{
    int i;
    if (o->version == 0 || o->version > 3) return 0;
    for (i = 0; i < 2; i++) {
        const SsFork *f = &o->fork[i];
        if (f->clen > UNC_MAC_MAX || f->ulen > UNC_MAC_MAX) return 0;
        if (f->ulen == 0) {
            /* SetupAFork @0x53d4 clears the method and the parameter
             * set with the length; a fork that claims neither bytes nor
             * a method is simply absent. */
            if (f->clen != 0) return 0;
            continue;
        }
        if (f->clen == 0) return 0;
        if (f->off < SS_HDRLEN || f->off > UNC_MAC_MAX) return 0;
        if (f->off + f->clen < f->off) return 0;
        /* The compressor byte is deliberately NOT checked. A file whose
         * method this engine does not know is still a SpaceSaver file
         * and is worth NAMING — the user gets the format instead of
         * *unknown*, and the entry fails on its own (CLAUDE.md; the
         * same bargain StuffIt X gets). The two magics are eight
         * bytes. */
    }
    return 1;
}

UncFormat unc_spacesaver_probe(const uint8_t *head, int32_t len, UncIO *io)
{
    (void)io;
    SsHead o;
    if (len < (int32_t)SS_HDRLEN) return UNC_FORMAT_UNKNOWN;
    if (unc_get_u32be(head) != SS_MAGIC1) return UNC_FORMAT_UNKNOWN;
    if (unc_get_u32be(head + 4) != SS_MAGIC2) return UNC_FORMAT_UNKNOWN;
    /* Version 3 states its own header length and it is always 84;
     * ReadSSHeader reads exactly that many bytes before looking. */
    if (unc_get_u32be(head + 8) >= 3 && unc_get_u32be(head + 12) != SS_HDRLEN)
        return UNC_FORMAT_UNKNOWN;
    ss_parse(head, &o);
    return (ss_head_ok(&o))
           ? UNC_FORMAT_SPACESAVER : UNC_FORMAT_UNKNOWN;
}
