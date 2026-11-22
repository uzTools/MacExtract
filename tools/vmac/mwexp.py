#!/usr/bin/env python3
"""mwexp.py — StuffIt Expander 4.0.2 fed method-8 streams that reach the rules
no writer here reaches.

StuffIt method 8's table restart is measured off a fork StuffIt Deluxe 2.0.1
wrote (docs/formats/stuffit-method-8-mw.md, *A writer's restart*). Two rules of
`src/fmt_sit.c` are still libxad's: a code greater than the next free one ENDS
the stream, and the dictionary's ceiling (the width goes to 15 bits at 16,384
entries; past 16,385 the fork is corrupt). Deluxe 2.0.1 restarts its table at
about 2,000 entries and wrote no end code, so its output cannot show either.
Aladdin's own reader can be asked instead: this builds one classic StuffIt
archive per variant, each a single data fork coded to a stated rule, has
Expander 4.0.2 expand it on the System 6.0.8 Mac Plus (`sitexp.py`'s flow),
and reports what Expander wrote.

Every variant but `endcode` is LITERAL codes only — each byte its own code —
so the table's contents never matter and the code WIDTH is the only thing a
reader can disagree about:

  w14      16,000 bytes: the table reaches 16,255 entries, codes 9..14 bits.
           Expander right = the width rule holds to 14 bits.
  grow15   17,000 bytes, the width going to 15 at 16,384 entries (libxad).
  stay14   the same bytes, the width staying 14 past 16,384.
  reset    the same bytes, the table restarting by itself at 16,384 entries
           with no restart code.
  fullrestart  16,129 literals fill the table to 16,384 entries, then the
           restart code 16,384 at 15 bits, then 871 literals from 9 bits.
           Right = the width is 15 at 16,384 entries and a full table
           restarts like any other.
  endcode  4,000 bytes, then a code greater than the next free one, then
           100 more literal bytes; the header declares 4,100.

Two controls, for the container rather than the rule: `lit300` (300
literal bytes, 9-bit codes only) and `dlx` (StuffIt Deluxe 2.0.1's own
MwText fork, sitopt.py --mw, which Deluxe wrote and this engine decodes).

What it CANNOT see: whether Expander keeps ADDING entries past 16,384 in
`grow15`/`stay14` (literals never reference one), and anything an alert says
except in the screenshots (-o). An Expander that writes nothing on a CRC
mismatch reports "no file", which is not the same as "it decoded something
else".

    tools/vmac/mwexp.py -o <shotdir> [variant ...]
"""
import argparse
import os
import shutil
import struct
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import run as R                                              # noqa: E402
from interactive import Mac                                 # noqa: E402
from arcmac import macbinary                                # noqa: E402
from expander import APP_NAME, EXPAND_BUTTON, names_on, select_by_name  # noqa: E402
from cptexp import pull                                     # noqa: E402


def crc16_arc(data, crc=0):
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def subject(n, seed):
    out, x = bytearray(), seed
    while len(out) < n:
        x = (x * 1103515245 + 12345) & 0x7fffffff
        out.append((x >> 16) & 255)
    return bytes(out)


def literal_codes(data, policy):
    """(code, width) for each byte of `data` as a literal, under `policy` at
    the ceiling: 'grow15', 'stay14' or 'reset'. Below 16,384 entries all three
    are the rule docs/formats/stuffit-method-8-mw.md states."""
    out = []
    nxt, width, first = 256, 9, True
    for b in data:
        out.append((b, width))
        if first:
            first = False
            continue
        nxt += 1
        if nxt == 16384 and policy == "reset":
            nxt, width, first = 256, 9, True
        elif nxt == 1 << width and not (policy == "stay14" and width == 14):
            width += 1
    return out


def pack(codes):
    """LSB-first, straight through the bytes, zero bits to the end."""
    acc = nb = 0
    out = bytearray()
    for c, w in codes:
        assert 0 <= c < (1 << w)
        acc |= c << nb
        nb += w
        while nb >= 8:
            out.append(acc & 255)
            acc >>= 8
            nb -= 8
    if nb:
        out.append(acc & 255)
    return bytes(out)


def variant(name):
    """(declared data, compressed stream, what a reader following the
    variant's rule would write)."""
    if name == "w14":
        d = subject(16000, 7)
        return d, pack(literal_codes(d, "grow15")), d
    if name in ("grow15", "stay14", "reset"):
        d = subject(17000, 11)
        return d, pack(literal_codes(d, name)), d
    if name == "fullrestart":
        # 16,129 literals fill the table to 16,384; then the restart code,
        # 16,384, at 15 bits (read at 14 it is a literal 0); then 871 more
        # literals from a fresh table, 9 bits up.
        a, b = subject(16129, 23), subject(871, 29)
        ca = literal_codes(a, "grow15")
        return a + b, pack(ca + [(16384, 15)] + literal_codes(b, "grow15")), a + b
    if name == "lit300":
        d = subject(300, 19)
        return d, pack(literal_codes(d, "grow15")), d
    if name == "dlx":
        # Deluxe 2.0.1's own MwText fork (sitopt.py --mw), in this container
        mb = open(os.path.join(R.VMAC_HOME, "specimens", "sitopt", "mw-1",
                               "Mw.sit.bin"), "rb").read()
        blob = mb[128:128 + struct.unpack(">I", mb[83:87])[0]]
        h = blob[22:134]
        rc, dc = struct.unpack(">II", h[92:100])
        dl = struct.unpack(">I", h[88:92])[0]
        src = open(os.path.join(R.VMAC_HOME, "specimens", "sitopt", "mw-1",
                                "MwText.in.bin"), "rb").read()[128:128 + dl]
        return src, blob[134 + rc:134 + rc + dc], src
    if name == "endcode":
        a, b = subject(4000, 13), subject(100, 17)
        codes = literal_codes(a, "grow15")
        nxt = 256 + len(a) - 1
        width = codes[-1][1]
        if nxt == 1 << width:
            width += 1
        codes.append((nxt + 5, width))          # greater than the next free
        codes += [(x, width) for x in b]        # what follows, same width
        return a + b, pack(codes), a
    raise SystemExit("mwexp: no variant %r" % name)


def archive(entry, data, comp, method=8):
    h = bytearray(112)
    h[0], h[1] = 0, method                      # rsrc stored (empty), data
    nb = entry.encode("mac_roman")
    h[2] = len(nb)
    h[3:3 + len(nb)] = nb
    h[66:74] = b"BINA????"
    struct.pack_into(">IIII", h, 84, 0, len(data), 0, len(comp))
    struct.pack_into(">H", h, 100, crc16_arc(b""))
    struct.pack_into(">H", h, 102, crc16_arc(data))
    struct.pack_into(">H", h, 110, crc16_arc(bytes(h[:110])))
    top = bytearray(22)
    top[0:4] = b"SIT!"
    struct.pack_into(">H", top, 4, 1)
    struct.pack_into(">I", top, 6, 22 + 112 + len(comp))
    top[10:14] = b"rLau"
    top[14] = 2                                 # what the corpus's MW archives say
    struct.pack_into(">I", top, 16, 22)         # header size: 22 in all 220 read
    # Bytes 15 and 20-21 are left zero: 220 corpus archives put 65 values
    # in 15, and 20-21 is no CRC-16/ARC of the bytes before it in any.
    return bytes(top) + bytes(h) + comp


def run_one(name, args):
    data, comp, expect = variant(name)
    entry = "Mw" + name
    expand(name, entry, archive(entry, data, comp), expect, len(data),
           len(comp), args)


def expand(name, entry, arc, expect, declared, streamlen, args):
    """Boot Expander 4.0.2 over `arc`, expand it, and print what it wrote
    for `entry` against `expect` (a bytes, or a dict of label -> bytes)."""
    work = R.work_tmp("mwexp-%s-" % name)
    if getattr(args, "keep_archives", None):
        os.makedirs(args.keep_archives, exist_ok=True)
        open(os.path.join(args.keep_archives, name + ".sit"), "wb").write(arc)
    boot = os.path.join(work, "boot-in.hfv")
    macname = name + ".sit"
    mb = os.path.join(work, macname + ".bin")
    open(mb, "wb").write(macbinary(macname, "SIT!", "SIT!", data=arc))
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"),
         os.path.join(R.VMAC_HOME, "System6.hfv"),
         os.path.join(R.VMAC_HOME, "expander", "Expander.bin"), boot,
         "--macbin", f"{mb}:{macname}", "--app-name", APP_NAME)
    before = set(names_on(boot))
    scratch = os.path.join(work, "scratch.png")
    mac = Mac(boot, args.emu, work)

    def shot(n):
        if args.outdir:
            os.makedirs(args.outdir, exist_ok=True)
            mac.shot(os.path.join(args.outdir, "%s-%s.png" % (name, n)))
    try:
        if mac.settle(scratch, interval=4.0, timeout=300.0) is None:
            raise SystemExit("mwexp: %s: never booted" % name)
        mac.origin(cached=False)
        mac.command_key("e")
        time.sleep(3.0)
        select_by_name(mac, macname)
        mac.click(*EXPAND_BUTTON)
        mac.settle(scratch, interval=3.0, timeout=600.0, quiet=15.0)
        shot("after-expand")
        mac.key("Return")
        mac.settle(scratch, interval=3.0, timeout=300.0, quiet=9.0)
        mac.command_key("q")
        time.sleep(10.0)
        mac.settle(scratch, interval=3.0, timeout=300.0, quiet=9.0)
    finally:
        mac.close()
    img = os.path.join(work, "boot.hfv")
    new = [n for n in names_on(img)
           if n not in before and ":System Folder:" not in n]
    got = pull(img, new, work)
    shutil.rmtree(work, ignore_errors=True)
    files = {k.split(":")[-1]: v[0] for k, v in got.items()}
    out = files.get(entry)
    expects = expect if isinstance(expect, dict) else {"the variant's rule": expect}
    if out is None:
        verdict = "no file (wrote %s)" % sorted(files)
    else:
        parts = []
        for label, e in expects.items():
            if out == e:
                parts.append("WROTE what %s gives (%d bytes)" % (label, len(out)))
                continue
            k = next((i for i in range(min(len(out), len(e)))
                      if out[i] != e[i]), min(len(out), len(e)))
            parts.append("wrote %d bytes, %s gives %d; they agree for the "
                         "first %d" % (len(out), label, len(e), k))
        verdict = "; ".join(parts)
    print("%s: %-8s declared %d, stream %d B: %s"
          % (os.path.basename(sys.argv[0])[:-3], name, declared, streamlen,
             verdict), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("variants", nargs="*",
                   default=["w14", "grow15", "stay14", "reset", "endcode"])
    p.add_argument("-o", "--outdir", default=None, help="screenshots")
    p.add_argument("--emu", default="mv-4M")
    p.add_argument("--keep-archives", default=None,
                   help="also write each archive here")
    a = p.parse_args()
    for v in a.variants:
        run_one(v, a)


if __name__ == "__main__":
    main()
