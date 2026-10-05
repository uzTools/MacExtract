#!/usr/bin/env python3
"""scan_discmaster.py — find specimens by reading their bytes, not their names.

Not in `ci.sh`: it needs the network, and what it produces is a list of
URLs rather than a verdict.  It is here so a sweep can be re-run and
widened rather than re-invented, which is the whole reason
`tools/scan_discmaster_zips.py` exists for the one it was written for
(DECISIONS.md 2026-10-04, *the archive that carried its own extractor*).

**Two indexes, and the second one is the point.**  Discmaster indexes
about 1.74 billion files out of archived CD-ROMs and disk images, and
two of its search fields answer questions about CONTENT rather than
about names:

  * `detection=` is full-text over what each identifier printed AND —
    documented on its own `searchHelp.html` — over the **first 16 bytes
    of every file**, as ASCII or as hex, with `*` at either end of the
    token and `?` for any single character.  So `detection=abcd0054*`
    is every DiskDoubler compressed file in the index whatever it is
    called, and `detection=53495421????????????724c617502??` is every
    classic StuffIt archive whose version byte is 2.
  * `Range` requests on the file itself, which is the cheap form of
    searching by content when nobody has indexed the content: one
    request per candidate, reading the one header that settles it.

So: list the candidates with a query that names the bytes, fetch a few
hundred bytes of each, and decide in this process.  Four probes, each
written from this project's own reading of the format it names:

  pkg  an AppleLink package — SqueezePlay (FORMATS.md, *AppleLink
       packages*).  A package's first 16 bytes are the item count, the
       version, eight zero bytes and the first SQP record's leading
       zero long, so a version-1 package IS a hex token:
       `??01` + 28 zeros.  The probe then validates the whole
       directory against the file's own size.
  sit  a classic StuffIt archive, reported when an entry's method byte
       has the Optimizer bit `0x40` or the encrypted bit `0x80`
       (reference/notes/sit_format_theunarchiver.md, the file-header
       table, for the layout; `src/fmt_sit.c` for the flag bits, which
       that page does not have — **0x10 is `NewDE` and not a folder**,
       measured 2026-10-02, and a folder is the masked value 0x20/0x21).
       `--walk` follows the entry chain with one request per entry.
  dd   a DiskDoubler compressed file, reported with both forks' method
       bytes and lengths (docs/formats/diskdoubler-container.md, *A
       compressed file*).  `--method` keeps only the forks that use one.
  pit  a PackIt archive, reported only when a block is `PMa5` or
       `PMa6` — the two encrypted forms, which no corpus here has.
       Added 2026-10-05.  It fetches the WHOLE file, because an
       encrypted block is almost never the first one and a `PMa4`
       block can only be stepped over by decoding it.

Examples — each sweep this tool has actually run is in TESTING.md
(*Searching somebody else's index by content*):

    tools/scan_discmaster.py --probe pkg --query 'extension=.pkg&family=unknown'
    tools/scan_discmaster.py --probe dd  --query 'detection=abcd0054*' \
        --sort size --desc --method 8
    tools/scan_discmaster.py --probe sit --query 'format=sit' --walk 24
    tools/scan_discmaster.py --probe pit --query 'detection=504d61*'

Progress is written to `--state` after every chunk and re-read on the
next run, so a sweep survives a timeout: run it again and it picks up
where it stopped.  `--budget` is the seconds it spends fetching per
run.  Run it in the FOREGROUND — a backgrounded process on this machine
loses network access and stalls with no error (CLAUDE.md).

Two things this tool CANNOT see, and both are about the index rather
than about the formats:

  * **a file whose first 16 bytes the index did not record** — the hex
    token is only as good as that field, and nothing here checks it is
    populated for every file.  Every `detection=` sweep below is
    therefore paired with a sweep by extension or format, which is
    reached a different way.
  * **anything past Elasticsearch's result window.**  A query with more
    hits than `--pages` × `limit` returns the first page's worth and
    says so; shard it with `sizeMin`/`sizeMax` rather than widening the
    page count, because the window is a server-side cap.
"""
import argparse
import http.client
import json
import os
import re
import struct
import sys
import time
import urllib.parse
import urllib.request

HOST = "discmaster.textfiles.com"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def u16(b, o):
    return struct.unpack(">H", b[o:o + 2])[0]


def u32(b, o):
    return struct.unpack(">I", b[o:o + 4])[0]


# ---- the probes -----------------------------------------------------
#
# Each takes the first bytes of a file and its size as the index
# reports it, and returns None (not one) or a dict describing what it
# found. `need` is how many bytes it wants; a probe may return the
# string "more" to ask for the rest of the file up to `limit`.

class PkgProbe:
    """An AppleLink package, off FORMATS.md's container table.

    The table is read out of `AppleLink Package Translator` 3.0.3's own
    reader, so this is this project's reading rather than a spec — the
    same reading `src/fmt_sqp_probe.c` ships.
    """
    need = 512
    # 10 + 86*50 + 12 + 90*50, the largest directory the format has:
    # the item count is capped at 50 (DoSqForward @0xc46).
    limit = 10 + 86 * 50 + 12 + 90 * 50

    def __call__(self, head, size):
        if len(head) < 16:
            return None
        n, ver = head[0], head[1]
        if n == 0 or n > 50 or ver > 1 or head[2:10] != b"\0" * 8:
            return None
        sqp_end = 10 + 86 * n
        if ver == 0:
            dirend, items, recs = sqp_end, n, 10
        else:
            if len(head) < sqp_end + 12:
                return "more"
            m = u32(head, sqp_end)
            if m == 0 or m > 4096 or head[sqp_end + 4:sqp_end + 12] != b"\0" * 8:
                return None
            dirend, items, recs = sqp_end + 12 + 90 * m, m, sqp_end + 12
        if dirend > size:
            return None
        if len(head) < dirend:
            return "more"
        out, span, bad = [], 0, False
        for i in range(items):
            at = recs + (90 if ver else 86) * i
            lvl, isdir = (u16(head, at), u16(head, at + 2)) if ver else (1, 0)
            r = at + (4 if ver else 0)
            rlen, dlen = u32(head, r + 4), u32(head, r + 8)
            doff, roff = u32(head, r + 12), u32(head, r + 16)
            nlen = head[r + 36]
            name = head[r + 37:r + 37 + min(nlen, 31)].decode("mac_roman",
                                                              "replace")
            flags = head[r + 84]
            if nlen > 31:
                bad = True
            e = {"name": name, "level": lvl, "folder": bool(isdir),
                 "rlen": rlen, "dlen": dlen, "flags": flags,
                 "stored_data": bool(flags & 2), "stored_rsrc": bool(flags & 4),
                 "dexp": u32(head, r + 80), "rexp": u32(head, r + 76)}
            out.append(e)
            if not isdir:
                span += rlen + dlen
                for off, ln in ((doff, dlen), (roff, rlen)):
                    if ln and not (dirend <= off <= size - ln):
                        bad = True
        if bad:
            return None
        return {"n": n, "ver": ver, "items": items, "dirend": dirend,
                "span": span, "tiles": dirend + span == size,
                "members": out}


class SitProbe:
    """A classic StuffIt archive, and what its entries' method bytes say.

    Source: reference/notes/sit_format_theunarchiver.md — the archive
    header (magic 2 'rLau' at 10, version at 14) and the file header
    (method bytes at 0 and 1, the lengths at 84..99).  The Optimizer
    bit and bytes 106/108 are this project's reading of StuffIt Deluxe
    2.0.1 (FORMATS.md, *Where an archive names the module*).
    """
    need = 512
    limit = 512

    def head_at(self, head):
        """Where the archive header starts: at 0, or past a MacBinary one."""
        for off in (0, 128):
            if len(head) >= off + 22 and head[off + 10:off + 14] == b"rLau":
                return off
        return None

    def __call__(self, head, size):
        off = self.head_at(head)
        if off is None:
            return None
        if len(head) < off + 22 + 112:
            return "more"
        # Walk as far as the bytes already fetched allow, which is free
        # and matters: **a folder marker carries no fork**, so an
        # archive that opens with one — 1,081 of the first 1,946 swept
        # on 2026-10-06 — puts its first FILE header inside the same
        # 512 bytes. One entry per probe would have seen no method byte
        # at all in over half the corpus.
        total = u32(head, off + 6)
        # **The walk stops where the ARCHIVE says it does**, not where
        # the fetched bytes run out: the header's total size at +6 is
        # the end, and a walk that passes it reads compressed data as
        # though it were a file header. Measured 2026-10-06, after a
        # deep sweep reported four Optimizer entries whose names were
        # English prose out of the middle of a fork.
        end = min(len(head), off + total) if total >= 22 else len(head)
        ents, at = [], off + 22
        while at + 112 <= end:
            e = entry(head, at)
            ents.append(e)
            at += 112 + e.get("rclen", 0) + e.get("dclen", 0)
        return {"base": off, "ver": head[off + 14],
                "files": u16(head, off + 4), "total": total,
                "next": at, "entries": ents}


# The flag bits are `src/fmt_sit.c`'s, measured where the published
# table is silent: 0x80 is encrypted, 0x40 says an Optimizer ran on that
# fork, and **0x10 is `NewDE`** — the second cipher built into StuffIt
# Deluxe 2.0.1 — rather than anything to do with folders. A folder is
# the masked value 0x20 (start) or 0x21 (end), under the mask 0x6F.
FOLDER_MASK = 0x6F


def entry(b, at):
    """One file header, as `src/fmt_sit.c` reads it."""
    rm, dm = b[at], b[at + 1]
    nl = min(b[at + 2], 63)
    e = {"at": at, "rmeth": rm, "dmeth": dm,
         "name": b[at + 3:at + 3 + nl].decode("mac_roman", "replace")}
    if (rm & FOLDER_MASK) in (0x20, 0x21):
        e["folder"] = "start" if (rm & FOLDER_MASK) == 0x20 else "end"
        return e
    e.update(rlen=u32(b, at + 84), dlen=u32(b, at + 88),
             rclen=u32(b, at + 92), dclen=u32(b, at + 96),
             b106=b[at + 106], b108=b[at + 108],
             opt=bool((rm | dm) & 0x40), enc=bool((rm | dm) & 0x80),
             newde=bool((rm | dm) & 0x10))
    return e


class DdProbe:
    """A DiskDoubler compressed file's header.

    Source: docs/formats/diskdoubler-container.md, *A compressed file*
    — the magic word and the header size at +2, the four lengths, and
    the two method bytes at +20 and +21.
    """
    need = 512
    limit = 512

    def __call__(self, head, size):
        if len(head) < 24:
            return None
        if u16(head, 0) != 0xABCD:
            return None
        hsize = u16(head, 2)
        if hsize < 48:
            return None
        return {"hsize": hsize, "dlen": u32(head, 4), "dclen": u32(head, 8),
                "rlen": u32(head, 12), "rclen": u32(head, 16),
                "dmeth": head[20], "rmeth": head[21]}


class PitProbe:
    """A PackIt archive, walked to the end of its block chain.

    The question this one answers is whether any archive in the index
    has an ENCRYPTED entry, and it cannot be asked of the first 16
    bytes: a `PMa5` or `PMa6` block is almost never the first one, and
    `detection=504d6135*` and `504d6136*` return **0 rows between
    them** (measured 2026-10-05). Following the chain to find one means
    DECODING every `PMa4` block on the way, because a compressed entry
    is Huffman-coded from its first bit and its own lengths are inside
    the stream — so this probe wants the whole file where `pkg`, `sit`
    and `dd` want 512 bytes.

    The decoder is `tools/derive_packit.py`'s, written from the
    format's published appendices. Its primitives rather than its
    `entries()`: the loop below bounds every length against the bytes
    actually present, which a reader of known-good fixtures does not
    have to do and a reader of 1.74 billion strangers does.
    """
    need = 16
    limit = 4 << 20

    def __call__(self, head, size):
        import derive_packit as DP
        start = 0
        if head[:4] not in (b"PMag", b"PMa4", b"PEnd") and len(head) >= 132:
            start = 128                      # a MacBinary envelope
        if head[start:start + 3] != b"PMa" and head[start:start + 4] != b"PEnd":
            return None
        if len(head) < min(size, self.limit):
            return "more"
        out, at, d, end = [], start, head, "ran out"
        try:
            while at + 4 <= len(d):
                kind = d[at:at + 4]
                if kind == b"PEnd":
                    end = "PEnd"
                    break
                if kind in (b"PMa5", b"PMa6"):
                    out.append({"magic": kind.decode(), "at": at,
                                "encrypted": True})
                    end = "encrypted"
                    break                    # nothing can say where it ends
                if kind == b"PMag":
                    h = d[at + 4:at + 4 + DP.HDR]
                    if len(h) < DP.HDR:
                        break
                    name, dsize, rsize = DP.header(h)
                    if dsize + rsize > len(d) - at:
                        return None
                    out.append({"magic": "PMag", "at": at, "name": name,
                                "dlen": dsize, "rlen": rsize})
                    at += 4 + DP.HDR + dsize + rsize + 2
                    continue
                if kind == b"PMa4":
                    bs = DP.Bits(d, at + 4)
                    tree = DP.read_tree(bs)
                    h = DP.decode(bs, tree, DP.HDR)
                    name, dsize, rsize = DP.header(h)
                    # A compressed entry's DECODED size is normally
                    # larger than the bytes left in the file, so the
                    # bound here is the one the bit stream gives: a
                    # symbol costs at least one bit. (The first draft
                    # bounded it by the file length and rejected every
                    # archive tools/synth_pit.py writes.)
                    if dsize + rsize > 8 * (len(d) - at):
                        return None
                    DP.decode(bs, tree, dsize + rsize + 2)
                    out.append({"magic": "PMa4", "at": at, "name": name,
                                "dlen": dsize, "rlen": rsize})
                    at = (bs.p + 7) // 8
                    continue
                return None                  # not a PackIt block at all
        except Exception:
            # A truncated or damaged archive is not a finding here; what
            # was read before it still is.
            if not out:
                return None
        return {"base": start, "entries": out, "end": end,
                "encrypted": [e for e in out if e.get("encrypted")]}


PROBES = {"pkg": PkgProbe, "sit": SitProbe, "dd": DdProbe, "pit": PitProbe}


# ---- the index ------------------------------------------------------

def search(query, pages, limit):
    """Every file one query names, over as many pages as it has.

    `pageNum` is 0-based: the form's "next" link for page two reads
    pageNum=1, and pageNum=1 on a one-page result returns an EMPTY
    array rather than an error — which is how a sweep can look complete
    and have fetched nothing (the trap scan_discmaster_zips.py fell
    into first).
    """
    out, seen = [], set()
    for page in range(pages):
        url = ("https://%s/search?%s&limit=%d&pageNum=%d&outputAs=json"
               % (HOST, query, limit, page))
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=300) as r:
            rows = json.loads(r.read().decode("utf-8", "replace"))
        fresh = [x for x in rows if (x["itemid"], x["fileid"]) not in seen]
        seen.update((x["itemid"], x["fileid"]) for x in fresh)
        out += fresh
        print("    page %d: %d row(s), %d total" % (page, len(rows), len(out)),
              flush=True)
        if len(rows) < limit:
            break
    return out


class Head:
    """One keep-alive connection, re-made when the server drops it."""

    def __init__(self):
        self.conn = None

    def get(self, item, fileid, nbytes):
        path = "/file/%d/%s" % (item, urllib.parse.quote(fileid))
        for attempt in (0, 1):
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPSConnection(HOST, timeout=60)
                self.conn.request("GET", path, headers={
                    "User-Agent": UA, "Range": "bytes=0-%d" % (nbytes - 1)})
                return self.conn.getresponse().read()
            except Exception:
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None
                if attempt:
                    return b""
        return b""


def url_of(item, fileid):
    return "https://%s/file/%d/%s" % (HOST, item, urllib.parse.quote(fileid))


def walk_sit(head, item, fileid, probe, first, maxent):
    """Follow a StuffIt entry chain past the bytes already fetched, one
    request per entry."""
    base = first["base"]
    ents = list(first["entries"])
    end = base + first["total"] if first["total"] >= 22 else None
    at = first["next"]
    while len(ents) < maxent and (end is None or at + 112 <= end):
        blob = head.get(item, fileid, at + 112)
        if len(blob) < at + 112:
            break
        e = entry(blob, at)
        ents.append(e)
        at += 112 + (e.get("rclen", 0) + e.get("dclen", 0))
    return ents


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", required=True, choices=sorted(PROBES))
    ap.add_argument("--query", action="append", default=[],
                    help="a Discmaster /search query string, repeatable; "
                         "shard a query bigger than the result window with "
                         "sizeMin/sizeMax")
    ap.add_argument("--pages", type=int, default=40)
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--sort", default=None, help="sortBy= (e.g. size)")
    ap.add_argument("--desc", action="store_true")
    ap.add_argument("--min-size", type=int, default=0,
                    help="skip a listed file smaller than this, without a "
                         "request")
    ap.add_argument("--method", type=int, default=None,
                    help="dd: report only a fork using this method")
    ap.add_argument("--walk", type=int, default=1,
                    help="sit: entries to follow, one request each")
    ap.add_argument("--bytes", type=int, default=0,
                    help="fetch this many bytes per file instead of the "
                         "probe's own default. For `sit` this is the cheap "
                         "way to see more than the first entry: the walk "
                         "inside the fetched bytes costs no extra request, "
                         "so 8 KB covers several entries of a small archive "
                         "for the same number of round trips")
    ap.add_argument("--state", default=None)
    ap.add_argument("--budget", type=float, default=540.0,
                    help="seconds to spend fetching this run")
    a = ap.parse_args()
    if not a.query:
        ap.error("name at least one --query")
    state_path = a.state or "/tmp/discmaster-%s.json" % a.probe
    probe = PROBES[a.probe]()
    if a.bytes:
        probe.need = probe.limit = a.bytes

    state = {"files": {}, "probed": {}, "queries": {}}
    if os.path.exists(state_path):
        state = json.load(open(state_path))
    for q in a.query:
        full = q + (("&sortBy=%s" % a.sort) if a.sort else "")
        full += "&sortOrderDesc=desc" if a.desc else ""
        if full in state["queries"]:
            continue
        print("query %s" % full, flush=True)
        rows = search(full, a.pages, a.limit)
        for r in rows:
            key = "%s/%s" % (r["itemid"], r["fileid"])
            state["files"][key] = r["size"]
        state["queries"][full] = len(rows)
        json.dump(state, open(state_path, "w"))

    todo = [k for k, sz in state["files"].items()
            if k not in state["probed"] and sz >= a.min_size]
    print("%d file(s) listed, %d probed, %d to go"
          % (len(state["files"]), len(state["probed"]), len(todo)), flush=True)

    head = Head()
    t0, done = time.time(), 0
    for key in todo:
        if time.time() - t0 > a.budget:
            break
        item, fileid = key.split("/", 1)
        item, size = int(item), state["files"][key]
        blob = head.get(item, fileid, min(probe.need, max(size, 16)))
        if not blob:
            state["probed"][key] = {"err": "no bytes"}
            done += 1
            continue
        got = probe(blob, size)
        if got == "more":
            blob = head.get(item, fileid, min(probe.limit, size))
            got = probe(blob, size)
            if got == "more":
                got = None
        if got and a.probe == "sit" and a.walk > 1:
            got["entries"] = walk_sit(head, item, fileid, probe, got, a.walk)
        state["probed"][key] = got or False
        done += 1
        if done % 200 == 0:
            json.dump(state, open(state_path, "w"))
            print("  %d probed, %.0f s" % (done, time.time() - t0), flush=True)
    json.dump(state, open(state_path, "w"))

    hits = {k: v for k, v in state["probed"].items() if v and "err" not in v}
    print("%d probed this run; %d/%d read; %d match the probe"
          % (done, len(state["probed"]), len(state["files"]), len(hits)),
          flush=True)
    for k in sorted(hits):
        v, item_fileid = hits[k], k.split("/", 1)
        item, fileid = int(item_fileid[0]), item_fileid[1]
        if a.probe == "dd":
            forks = [("data", v["dmeth"], v["dlen"], v["dclen"]),
                     ("rsrc", v["rmeth"], v["rlen"], v["rclen"])]
            if a.method is not None:
                forks = [f for f in forks if f[1] == a.method and f[2]]
                if not forks:
                    continue
            print("  %s\n    hdr %d, %s" % (url_of(item, fileid), v["hsize"],
                  ", ".join("%s method %d %d->%d" % (n, m, ln, cl)
                            for n, m, ln, cl in forks)))
        elif a.probe == "sit":
            flagged = [e for e in v["entries"]
                       if e.get("opt") or e.get("enc")]
            if not flagged:
                continue
            print("  %s\n    version %d, %d file(s): %s"
                  % (url_of(item, fileid), v["ver"], v["files"],
                     "; ".join("%r %s%s%s rm %d dm %d ids %d/%d"
                               % (e["name"], "OPT " if e["opt"] else "",
                                  "ENC " if e["enc"] else "",
                                  "NewDE" if e.get("newde") else "",
                                  e["rmeth"], e["dmeth"], e["b106"],
                                  e["b108"])
                               for e in flagged)))
        elif a.probe == "pit":
            if not v["encrypted"]:
                continue
            print("  %s\n    %d block(s), %s"
                  % (url_of(item, fileid), len(v["entries"]),
                     "; ".join("%s%s" % (e["magic"],
                                         "" if e.get("encrypted")
                                         else " %r" % e["name"])
                               for e in v["entries"])))
        else:
            print("  %s\n    version %d, %d item(s), tiles %s: %s"
                  % (url_of(item, fileid), v["ver"], v["items"], v["tiles"],
                     "; ".join("%r%s r%d d%d flags 0x%02x"
                               % (m["name"], " DIR" if m["folder"] else "",
                                  m["rlen"], m["dlen"], m["flags"])
                               for m in v["members"])))
    left = len(state["files"]) - len(state["probed"])
    if left:
        print("not finished — run again to continue, %d left (%s)"
              % (left, state_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
