#!/usr/bin/env python3
"""make_seeds.py — seed every harness in tools/fuzz/ from the corpus.

A harness's input is a decoder's RAW stream behind fz_common.h's six-byte
header, and nothing in the corpus is in that shape: the streams are inside
containers. So this copies the engine to a scratch tree, inserts one line
at the top of each decoder entry point that writes the stream it is about
to decode (outlen, param and the bytes, exactly as the harness reads them),
builds the CLI from that tree, and runs `t` over every fixture, unwrapping
envelopes (SpaceSaver and SuperDisk! reach this corpus only inside one).

    tools/fuzz/make_seeds.py [--out .tmp/fuzz/seeds] [--max 64]

The scratch tree is .tmp/fuzz/seedsrc; nothing under src/ is touched.
A stream that is encrypted (a reader with a cipher) is not written: its
bytes are ciphertext. At most --max seeds per target, smallest first, so a
run starts from many short streams rather than a few long ones.

SpaceSaver is in no fixture, so its seeds come from the files SpaceSaver
itself wrote where tools/fetch_specimens.py has fetched them (all four
methods), and always from what tools/run_spacesaver.py --emit writes
(methods 0 and 4 only).

WHAT IT CANNOT SEE: a decoder reached by no fixture gets no seed (it then
starts from the header alone; SpaceSaver's methods 1-3 without the fetched
specimens), and the harness's `param` is reconstructed
from what the caller passed, so a decoder parameter the harness does not
model (DiskDoubler's xorval beyond 0, SpaceSaver's preset) is dropped.
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

SEED_H = r'''
#ifndef FZ_SEED_H
#define FZ_SEED_H
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned long fz_seed_n;
static void fz_seed_write(const char *tag, uint32_t outlen, unsigned param,
                          const uint8_t *p, uint32_t n)
{
    const char *dir = getenv("FZ_SEED_DIR");
    char path[1024];
    FILE *f;
    uint8_t h[6];
    if (!dir || n == 0 || n > (1u << 20)) return;
    snprintf(path, sizeof path, "%s/%s.%ld.%lu", dir, tag, (long)getpid(),
             fz_seed_n++);
    f = fopen(path, "wb");
    if (!f) return;
    h[0] = (uint8_t)(outlen >> 24); h[1] = (uint8_t)(outlen >> 16);
    h[2] = (uint8_t)(outlen >> 8);  h[3] = (uint8_t)outlen;
    h[4] = (uint8_t)param; h[5] = 0;
    fwrite(h, 1, 6, f);
    fwrite(p, 1, n, f);
    fclose(f);
}
/* `len` bytes of `io` from `at`, the reader left where it was. */
static void fz_seed_io(const char *tag, UncIO *io, uint32_t at, uint32_t len,
                       uint32_t outlen, unsigned param)
{
    unc_off_t was = io->tell(io->ctx);
    uint8_t *b;
    int32_t got;
    if (len > (1u << 20)) len = 1u << 20;
    b = (uint8_t *)malloc(len ? len : 1);
    if (!b) return;
    if (io->seek(io->ctx, at) == 0) {
        got = io->read(io->ctx, b, (int32_t)len);
        if (got > 0) fz_seed_write(tag, outlen, param, b, (uint32_t)got);
    }
    io->seek(io->ctx, was);
    free(b);
}
/* What is left of a buffered reader: its buffer, then the io up to limit. */
static void fz_seed_in(const char *tag, UncBufIn *in, uint32_t outlen,
                       unsigned param)
{
    uint32_t have = in->len - in->pos, more, n;
    unc_off_t was;
    uint8_t *b;
    int32_t got = 0;
    if (in->crypt) return;
    more = in->limit == ~0u ? (1u << 20) : in->limit - in->lenfed;
    if (more > (1u << 20)) more = 1u << 20;
    b = (uint8_t *)malloc(have + more + 1);
    if (!b) return;
    memcpy(b, in->buf + in->pos, have);
    was = in->io->tell(in->io->ctx);
    if (more) got = in->io->read(in->io->ctx, b + have, (int32_t)more);
    in->io->seek(in->io->ctx, was);
    n = have + (got > 0 ? (uint32_t)got : 0);
    fz_seed_write(tag, outlen, param, b, n);
    free(b);
}
#endif
'''

SIT_METHODS = [0, 1, 2, 3, 5, 6, 8, 13, 14, 15]
LZH_STATIC = ['-lh4-', '-lh5-', '-lh6-', '-lh7-']
LZH_DYN = ['-lh1-', '-lh2-', '-lh3-', '-lz5-', '-lzs-']

# A chain of layers stops at an application (DECISIONS.md 2026-10-16, *the
# installer that was a layer*), and SuperDisk!'s blocks are inside one:
# these are extracted, and what comes out is tested as a second step, as
# tools/sdmodule/run_sdmodule.py does.
CHAINS = ["alysis-disk-expander-12.hqx", "super-disk-utility.hqx"]

# (file, function, hook). Each hook is C inserted as the function body's
# first statement; it names the parameters as the function declares them.
HOOKS = [
    ("fmt_sit.c", "unc_sit_decode_fork", r'''
    if (!cr) {
        static const int fzm[10] = { 0, 1, 2, 3, 5, 6, 8, 13, 14, 15 };
        int fzi, fzk = method & 0x0f;
        const char *fzt = fzk == 13 ? "sit13" : fzk == 14 ? "sit14"
                        : fzk == 15 ? "arsenic" : "sit";
        for (fzi = 0; fzi < 10 && fzm[fzi] != fzk; fzi++) ;
        if (fzi < 10 && optdec <= 1)  /* REFUSE (StuffIt 5 passes it) or ASIS */
            fz_seed_io(fzt, c->io, at, complen, outlen, (unsigned)fzi);
    }'''),
    ("fmt_dd.c", "dd_fork", r'''
    if ((method & 0x7F) <= 10)
        fz_seed_io((method & 0x7F) == 10 ? "ddn" : "dd", c->io, at, complen,
                   uncomplen, (unsigned)(method & 0x7F));'''),
    ("fmt_lzh.c", "lzh_decode", r'''
    {
        static const char *const fzs[4] = { "-lh4-", "-lh5-", "-lh6-", "-lh7-" };
        static const char *const fzd[5] = { "-lh1-", "-lh2-", "-lh3-",
                                            "-lz5-", "-lzs-" };
        unsigned fzi;
        for (fzi = 0; fzi < 4; fzi++)
            if (!memcmp(e->method, fzs[fzi], 5))
                fz_seed_io("lzh_static", c->io, e->dataoff, e->compsize,
                           e->origsize, fzi);
        for (fzi = 0; fzi < 5; fzi++)
            if (!memcmp(e->method, fzd[fzi], 5))
                fz_seed_io("lzh_dyn", c->io, e->dataoff, e->compsize,
                           e->origsize, fzi);
    }'''),
    ("fmt_now.c", "now_huffman", r'''
    if (nsyms == 0x100) fz_seed_write("now", dstcap, 0, src, srclen);'''),
    ("fmt_now.c", "now_lzss", r'''
    fz_seed_write("now", dstcap, 1, src, srclen);'''),
    ("fmt_now.c", "now_newlzss", r'''
    fz_seed_write("now", dstcap, 2, src, srclen);'''),
    ("fmt_spacesaver.c", "ss_one_fork", r'''
    fz_seed_io("spacesaver", s->out.c->io, f->off, f->clen, f->ulen,
               (unsigned)(f->method & 0x87));'''),
    ("fmt_superdisk.c", "sd_fork", r'''
    fz_seed_io("superdisk", s->out.c->io, at, 1u << 20, want, 0);'''),
    ("unc_implode.c", "unc_implode_decode", r'''
    fz_seed_in("implode", in, usize, (unsigned)((flags & 6u) | (mmlbug & 1u)));'''),
    ("unc_shrink.c", "unc_shrink_decode", r'''
    fz_seed_in("shrink", in, usize, 0);'''),
    ("unc_reduce.c", "unc_reduce_decode", r'''
    fz_seed_in("reduce", in, usize, (unsigned)(factor - 1u));'''),
]


def patch(tree):
    for fname, func, hook in HOOKS:
        path = os.path.join(tree, "src", fname)
        text = open(path).read()
        m = re.search(r"^(?:static )?(?:int|int32_t) " + re.escape(func)
                      + r"\([^)]*\)\s*\{", text, re.M)
        if not m:
            raise SystemExit("make_seeds: no definition of %s in %s"
                             % (func, fname))
        text = text[:m.end()] + hook + "\n" + text[m.end():]
        if '#include "fz_seed.h"' not in text:
            text = text.replace('#include "unc_internal.h"',
                                '#include "unc_internal.h"\n#include <unistd.h>\n'
                                '#include "fz_seed.h"', 1)
            if '#include "fz_seed.h"' not in text:
                raise SystemExit("make_seeds: %s does not include "
                                 "unc_internal.h directly" % fname)
        open(path, "w").write(text)


SS_HOME = os.environ.get("UNC_VMAC_HOME",
                         os.path.expanduser("~/.cache/macextract/vmac"))
SS_SPECIMENS = os.path.join(SS_HOME, "specimens", "spacesaver")
SS_PRESET = os.path.join(SS_SPECIMENS, "PrAm-4048.bin")


def spacesaver_inputs(cli):
    """Every SpaceSaver file this machine has: the fetched specimens (the
    same glob and magic test tools/run_spacesaver.py grades), then what
    `run_spacesaver.py --emit` writes into .tmp/fuzz/ssemit."""
    out = []
    if os.path.isdir(SS_SPECIMENS):
        for n in sorted(os.listdir(SS_SPECIMENS)):
            p = os.path.join(SS_SPECIMENS, n)
            if n.endswith(".ss") and open(p, "rb").read(8) == b"SIT!DFD3":
                out.append(p)
    emit = os.path.join(REPO, ".tmp", "fuzz", "ssemit")
    shutil.rmtree(emit, ignore_errors=True)
    subprocess.run([sys.executable, os.path.join(REPO, "tools",
                                                 "run_spacesaver.py"),
                    "--macextract", cli, "--emit", emit],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=600)
    if os.path.isdir(emit):
        out += [os.path.join(emit, n) for n in sorted(os.listdir(emit))
                if n.endswith(".ss")]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO, ".tmp", "fuzz", "seeds"))
    ap.add_argument("--max", type=int, default=64)
    ap.add_argument("--fixtures", default=os.path.join(REPO, "fixtures"))
    a = ap.parse_args()

    tree = os.path.join(REPO, ".tmp", "fuzz", "seedsrc")
    shutil.rmtree(tree, ignore_errors=True)
    os.makedirs(tree)
    for d in ("src", "include", "cli", "third_party", "tools"):
        shutil.copytree(os.path.join(REPO, d), os.path.join(tree, d),
                        symlinks=True)
    shutil.copy(os.path.join(REPO, "Makefile"), tree)
    open(os.path.join(tree, "src", "fz_seed.h"), "w").write(SEED_H)
    patch(tree)
    r = subprocess.run(["make", "-C", tree, "BUILD=build", "CFLAGS=-O1",
                        "build/macextract"], capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-4000:] + r.stderr[-4000:])
        raise SystemExit("make_seeds: the patched CLI did not build")
    cli = os.path.join(tree, "build", "macextract")

    raw = os.path.join(REPO, ".tmp", "fuzz", "seedraw")
    shutil.rmtree(raw, ignore_errors=True)
    os.makedirs(raw)
    env = dict(os.environ, FZ_SEED_DIR=raw)
    names = sorted(n[:-5] for n in os.listdir(os.path.join(a.fixtures,
                                                           "manifests"))
                   if n.endswith(".json"))
    for n in names:
        p = os.path.join(a.fixtures, n)
        if os.path.exists(p):
            subprocess.run([cli, "t", p], env=env,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=600)

    # SpaceSaver is in no fixture (its files may not be committed, and no
    # tool here reads them, so there are no manifests). Two sources exist
    # anyway: the files SpaceSaver itself wrote, which
    # tools/fetch_specimens.py --only spacesaver puts outside the
    # repository, and the method-0 and method-4 files
    # tools/run_spacesaver.py --emit writes from nothing.
    for p in spacesaver_inputs(cli):
        args = [cli, "t"]
        if os.path.exists(SS_PRESET):
            args += ["--preset", SS_PRESET]
        subprocess.run(args + [p], env=env, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=600)

    for n in CHAINS:
        p = os.path.join(a.fixtures, n)
        if not os.path.exists(p):
            continue
        out = os.path.join(REPO, ".tmp", "fuzz", "chain", n)
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        subprocess.run([cli, "x", "-o", out, p], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=600)
        for dirpath, _, files in os.walk(out):
            for f in files:
                subprocess.run([cli, "t", os.path.join(dirpath, f)], env=env,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=600)

    # Dedupe by content, keep the smallest --max per target, and give the
    # three StuffIt targets that fix their method the `sit` seeds' streams.
    by = {}
    for f in os.listdir(raw):
        tag = f.split(".", 1)[0]
        b = open(os.path.join(raw, f), "rb").read()
        by.setdefault(tag, {})[hashlib.sha1(b).hexdigest()] = b
    shutil.rmtree(a.out, ignore_errors=True)
    for tag, seeds in sorted(by.items()):
        d = os.path.join(a.out, tag)
        os.makedirs(d)
        keep = sorted(seeds.items(), key=lambda kv: len(kv[1]))[:a.max]
        for h, b in keep:
            open(os.path.join(d, h), "wb").write(b)
        print("make_seeds: %-11s %4d distinct streams, %d kept"
              % (tag, len(seeds), len(keep)))
    shutil.rmtree(raw, ignore_errors=True)


if __name__ == "__main__":
    main()
