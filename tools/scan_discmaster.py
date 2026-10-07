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
       has the Optimizer bit `0x40`, the encrypted bit `0x80` or the
       `NewDE` bit `0x10`
       (reference/notes/sit_format_theunarchiver.md, the file-header
       table, for the layout; `src/fmt_sit.c` for the flag bits, which
       that page does not have — **0x10 is `NewDE` and not a folder**,
       measured 2026-10-02, and a folder is the masked value 0x20/0x21).
       It names the MODULE, per fork: the Optimizer id at 106/108 and
       the Encryptor id at 107/109, read only where that fork's own
       method byte carries the flag and its length is nonzero.
       `--walk` follows the entry chain; once the window-Range control
       passes it costs 112 bytes per entry rather than the whole
       prefix, so a whole archive can be walked.
  dd   a DiskDoubler compressed file, reported with both forks' method
       bytes and lengths (docs/formats/diskdoubler-container.md, *A
       compressed file*).  `--method` keeps only the forks that use one.
  pit  a PackIt archive, reported only when a block is `PMa5` or
       `PMa6` — the two encrypted forms, which no corpus here has.
       Added 2026-10-05.  It fetches the WHOLE file, because an
       encrypted block is almost never the first one and a `PMa4`
       block can only be stepped over by decoding it.

**A third key, and it is about an archive's CONTENTS**: the listing
hands over `meta.fileMeta`, the index's own record of the Mac file type
and creator of every file INSIDE an archive, for free with every row.
`--meta-type` keeps only the archives carrying a member of a type named
on the command line, which is the key the Optimizers need — each module's
`COMP` accepts exactly one type (`member_types()`, below). Discmaster
does not index inside a `.sit`, so no query can ask this; the listing can.

Examples — each sweep this tool has actually run is in TESTING.md
(*Searching somebody else's index by content*):

    tools/scan_discmaster.py --probe pkg --query 'extension=.pkg&family=unknown'
    tools/scan_discmaster.py --probe dd  --query 'detection=abcd0054*' \
        --sort size --desc --method 8
    tools/scan_discmaster.py --probe sit --query 'format=sit' --walk 24
    tools/scan_discmaster.py --probe pit --query 'detection=504d61*'
    # how many a query matches, which the JSON output does not carry
    tools/scan_discmaster.py --probe sit --count --query 'format=sit&dedup=dedup'
    # the whole corpus, in shards under the result window, probed only
    # where a member's type is one an Optimizer accepts
    tools/scan_discmaster.py --probe sit --shard-under 9000 --sort b3sum \
        --query 'format=sit&dedup=dedup' --query 'format=sea&dedup=dedup' \
        --meta-type PNTG --meta-type 8BIM --meta-type FSSD \
        --bytes 32768 --walk 400

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
  * **the END of a file, unless the range is explicit.** A suffix range
    — `Range: bytes=-2048` — is answered here with `206 Partial
    Content` and the bytes of the HEAD, so a probe that reads a tail
    must ask for `bytes=<size-2048>-<size-1>` and must be given a
    positive control first: one file whose last bytes are already
    known. A sweep of 939 files reported 0 hits that way and the
    specimen was in it (TESTING.md, *Searching somebody else's index by
    content*).

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
        aend = off + total if total >= 22 else None
        # Two different bounds, and conflating them rejects the last
        # entry of every archive: `end` is where the FETCHED bytes run
        # out, `aend` is where the archive says it ends. An entry's
        # forks legitimately extend past the bytes in hand.
        end = min(len(head), aend) if aend else len(head)
        ents, at = [], off + 22
        while at + 112 <= end:
            e = entry(head, at)
            if not plausible(e, aend):
                break
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


def plausible(e, end=None):
    """Whether a walk has arrived at a FILE HEADER or at the middle of
    a fork.

    **The declared total at +6 bounds the walk but does not keep it in
    step**: one wrong length and every entry after it is read out of
    compressed data. Three tests, each with a measured false-positive
    rate over the **1,216 file headers in `fixtures/`**, which are
    known good:

      * the name-length byte is **1..31**, 31 being the longest name
        HFS has and what `src/fmt_sit.c` itself clamps to. 0 of 1,710.
      * the name holds **no NUL**. 0 of 1,710 — and note that a weaker
        test does not survive this corpus: *"no control byte"* rejects
        **44** real headers, names made of tabs and `\x01`, so the
        obvious tightening would have silently dropped them.
      * the entry and both its forks **fit inside the declared total**.
        0 of 1,710.

    Of the headers the 2026-10-06 sweep's archives yield, exactly the
    already-known-bogus ones fail: the two `cursors.sit` copies `unar`
    also refuses, the entry that made that sweep report a `NewDE` bit,
    and `SternSounds3.sit`, whose second "entry" asks for a 3.1 GB fork
    out of a 206 KB archive. Every real `Text 1`, `MacPaint 1` and
    `Sound 1` entry passes.
    """
    # `len(name)` is the fallback for a state file written before the
    # raw length byte was kept; mac_roman is one character per byte, so
    # it is exact up to the 63 the name is clamped at.
    nl = e.get("nl", len(e["name"]))
    if nl > 31 or nl == 0 or "\x00" in e["name"]:
        return False
    if end is not None:
        nxt = e["at"] + 112 + e.get("rclen", 0) + e.get("dclen", 0)
        if nxt > end or nxt <= e["at"]:
            return False
    return True


def entry(b, at):
    """One file header, as `src/fmt_sit.c` reads it."""
    rm, dm = b[at], b[at + 1]
    nl = b[at + 2]
    e = {"at": at, "rmeth": rm, "dmeth": dm, "nl": nl,
         "name": b[at + 3:at + 3 + min(nl, 63)].decode("mac_roman",
                                                       "replace")}
    if (rm & FOLDER_MASK) in (0x20, 0x21):
        e["folder"] = "start" if (rm & FOLDER_MASK) == 0x20 else "end"
        return e
    e.update(rlen=u32(b, at + 84), dlen=u32(b, at + 88),
             rclen=u32(b, at + 92), dclen=u32(b, at + 96),
             b106=b[at + 106], b108=b[at + 108],
             b107=b[at + 107], b109=b[at + 109],
             opt=bool((rm | dm) & 0x40), enc=bool((rm | dm) & 0x80),
             newde=bool((rm | dm) & 0x10))
    # **An id byte belongs to a FORK, and is read only where that
    # fork's own method byte carries the flag.** Bytes 106/107 are the
    # data fork's Optimizer and Encryptor ids, 108/109 the resource
    # fork's (FORMATS.md, *Where an archive names the module*). The
    # first tally here keyed a cipher on 107 OR 109 whichever was
    # nonzero and reported four `DES` entries off byte 107 of archives
    # whose DATA fork is absent — `dlen` 0, `dmeth` 0 — and whose
    # encrypted resource fork says 0. A 1.x writer left whatever was in
    # the buffer at those offsets, which is the same reason the reading
    # of 46/47 is anchored to the nibble rather than to the bytes being
    # zero.
    # **And a fork of length zero went through nothing, whatever its
    # method byte says** — which is `src/fmt_sit.c`'s own rule (`&&
    # rlen`, `&& dlen` at the encryption branch) and the other half of
    # the same mistake: all four spurious `DES` readings were byte 107
    # of an entry with `dlen` 0.
    e["forks"] = [f for f in (
        {"fork": "data", "meth": dm, "len": e["dlen"], "clen": e["dclen"],
         "opt_id": e["b106"], "enc_id": e["b107"]},
        {"fork": "rsrc", "meth": rm, "len": e["rlen"], "clen": e["rclen"],
         "opt_id": e["b108"], "enc_id": e["b109"]})
        if f["len"] and (f["meth"] & 0xD0)]
    e["opt"] = any(f["meth"] & 0x40 for f in e["forks"])
    e["enc"] = any(f["meth"] & 0x90 for f in e["forks"])
    e["newde"] = any(f["meth"] & 0x10 for f in e["forks"])
    return e


# The ENCRYPTOR id, as `src/fmt_sit.c` reads it: the module's resource
# id is `512 + id` (FORMATS.md, *Where an archive names the module*).
# Without it an encrypted hit says only THAT it is encrypted, which is
# all the first sweep could report; with it the hit says WHICH of the
# five ciphers wrote the fork, and that is the whole question the row
# asks.
ENCRYPTORS = {0: "unset", 1: "DES", 2: "PassLock", 3: "NewDEx",
              4: "StuffItDES (built-in)", 64: "DESex"}


def encname(f):
    """Which cipher a flagged fork is under, by `sit_scheme()`'s rule.

    **The method BIT wins over the id byte**, which is not a detail:
    `0x10` is `NewDE` built in (measured 2026-10-02, where the
    published table calls it a folder marker), and the one archive here
    that carries it — `sitopt/psdes1/NewdeT.sit.bin`, 2.0.1's own
    output — ALSO carries a stale `1` in the id byte. Reading the id
    first names that fork `DES`, and a wild `NewDE` fork would have
    been reported as the one cipher this project has no file for.
    """
    if f["meth"] & 0x10:
        return "NewDE (built in)"
    return ENCRYPTORS.get(f["enc_id"], "id %d" % f["enc_id"])


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
        rows = json.loads(fetch(url).decode("utf-8", "replace"))
        fresh = [x for x in rows if (x["itemid"], x["fileid"]) not in seen]
        seen.update((x["itemid"], x["fileid"]) for x in fresh)
        out += fresh
        print("    page %d: %d row(s), %d total" % (page, len(rows), len(out)),
              flush=True)
        if len(rows) < limit:
            break
    return out


def member_types(row):
    """The Mac file TYPES of the files INSIDE an archive, off the index's
    own `meta.fileMeta` — which the listing hands over for free.

    This is the second content key for an archive, and the only one
    there is for its CONTENTS: Discmaster does not index inside a
    `.sit` (measured 2026-10-07 — `detection=PNTG/MPNT` returns 20,000
    MacPaint documents and not one fileid with `.sit/` in it), so no
    query can ask for a member.  The listing can, locally.

    It is the key the Optimizers need, because **an Optimizer is a
    per-file-type preprocessor** and each module's own `COMP` says
    which type it accepts: `FSSD` for `Sound 1`, `8BIM` for
    `Photoshop 1` and `JPEG Lossy`, `PNTG` for `MacPaint 1`, `TEXT`
    for `Text 1` (FORMATS.md, *The module ABI*, read out of the
    modules).  An archive with no member of an accepted type cannot
    carry that module's bit.
    """
    fm = (row.get("meta") or {}).get("fileMeta") or {}
    return sorted({v.get("macFileType") for v in fm.values()
                   if v.get("macFileType")})


def save(state, path):
    """Write the state atomically.

    **A `SIGTERM` in the middle of `json.dump` leaves a truncated file**,
    which is how 70,869 listed rows were lost on 2026-10-07: a run inside
    a shell timeout was killed mid-write and the next run could not parse
    what it had saved. The temp-file-and-rename costs nothing and a long
    listing cannot be re-done cheaply.
    """
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, path)


def fetch(url, tries=4):
    """One GET, retried — a sweep that lists 200 pages must survive a
    transient DNS failure, which this machine produces (measured
    2026-10-07, mid-listing, `Temporary failure in name resolution`)."""
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except Exception as exc:
            if attempt == tries - 1:
                raise
            print("    retry %d: %s" % (attempt + 1, exc), flush=True)
            time.sleep(5 * (attempt + 1))
    return b""


def count(query):
    """How many files the index says a query matches — one request.

    The JSON output does not carry a total, so this reads the HTML
    form, which prints `N match` next to the page it returned.  It is
    what makes sharding plannable instead of guessed: a query over the
    result window returns its first page and says nothing.
    """
    url = "https://%s/search?%s&limit=1&pageNum=0" % (HOST, query)
    html = fetch(url).decode("utf-8", "replace")
    m = re.search(r"([\d,]+) match", html)
    return int(m.group(1).replace(",", "")) if m else None


def size_shards(query, cap, lo=0, hi=1 << 31):
    """Split a query into `sizeMin`/`sizeMax` shards of at most `cap`
    hits each, so a corpus larger than Elasticsearch's result window
    can be listed in full.

    The window is a server-side cap — 10,000 here — and a query past it
    returns the first page's worth and reports the real total, so the
    shard boundaries come from `count()` rather than from the rows.
    Bisection is GEOMETRIC, because file sizes are heavy-tailed: an
    arithmetic midpoint of 0..2 GB puts every archive in one half.
    """
    q = "%s&sizeMin=%d&sizeMax=%d" % (query, lo, hi)
    n = count(q)
    print("    shard %d..%d: %s" % (lo, hi, n), flush=True)
    if n is None or n == 0:
        return []
    if n <= cap or hi - lo < 2:
        return [q]
    mid = int((max(lo, 1) * hi) ** 0.5) if lo else hi // 64
    mid = min(max(mid, lo + 1), hi - 1)
    return size_shards(query, cap, lo, mid) + size_shards(query, cap,
                                                          mid + 1, hi)


class Head:
    """One keep-alive connection, re-made when the server drops it."""

    def __init__(self):
        self.conn = None
        self.window = None          # None until the control below runs

    def get(self, item, fileid, nbytes, start=0):
        """`nbytes` from `start`.  `start` is only ever nonzero once
        `control()` has established that a mid-file range is honoured."""
        path = "/file/%d/%s" % (item, urllib.parse.quote(fileid))
        rng = "bytes=%d-%d" % (start, start + nbytes - 1)
        for attempt in (0, 1):
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPSConnection(HOST, timeout=60)
                self.conn.request("GET", path, headers={
                    "User-Agent": UA, "Range": rng})
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

    def control(self, item, fileid):
        """**The positive control a non-head range needs**, run once per
        process against a file whose head is already in hand.

        A suffix range is NOT honoured here — `Range: bytes=-2048`
        answers `206` with the bytes of the HEAD, which once made a
        sweep of 939 files report 0 hits (TESTING.md, *Searching
        somebody else's index by content*).  So a window range is not
        believed either until one file says the same bytes twice: read
        0..511, then read 256..511 and require the second to equal the
        tail of the first.  Until that passes, a walk pays for the whole
        prefix of the file it is stepping through."""
        if self.window is not None:
            return self.window
        whole = self.get(item, fileid, 512)
        if len(whole) >= 512:
            part = self.get(item, fileid, 256, start=256)
            self.window = part == whole[256:512]
        else:
            self.window = False
        print("    window Range honoured: %s" % self.window, flush=True)
        return self.window


def url_of(item, fileid):
    return "https://%s/file/%d/%s" % (HOST, item, urllib.parse.quote(fileid))


def walk_sit(head, item, fileid, probe, first, maxent):
    """Follow a StuffIt entry chain past the bytes already fetched, one
    request per entry."""
    base = first["base"]
    ents = list(first["entries"])
    end = base + first["total"] if first["total"] >= 22 else None
    at = first["next"]
    window = head.control(item, fileid)
    while len(ents) < maxent and (end is None or at + 112 <= end):
        if window:
            # 112 bytes, not `at` + 112: a prefix fetch per entry makes
            # a full walk quadratic in the archive's size, which is why
            # the first sweep could only afford the first few entries.
            blob = head.get(item, fileid, 112, start=at)
            if len(blob) < 112:
                break
            e = entry(blob, 0)
            e["at"] = at
        else:
            blob = head.get(item, fileid, at + 112)
            if len(blob) < at + 112:
                break
            e = entry(blob, at)
        if not plausible(e, end):
            break
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
    ap.add_argument("--meta-type", action="append", default=[],
                    help="probe only an archive whose index metadata says "
                         "it CONTAINS a member of this Mac file type "
                         "(e.g. PNTG). Repeatable; the key is "
                         "`member_types()` above")
    ap.add_argument("--shard-under", type=int, default=0,
                    help="split each --query into size shards of at most "
                         "this many hits, so a corpus past the result "
                         "window is listed in full")
    ap.add_argument("--max-report", type=int, default=8,
                    help="sit: flagged entries to print per archive")
    ap.add_argument("--count", action="store_true",
                    help="print what the index says each --query matches, "
                         "and stop")
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

    if a.count:
        for q in a.query:
            print("%s -> %s" % (q, count(q)), flush=True)
        return 0

    state = {"files": {}, "probed": {}, "queries": {}, "types": {},
             "shards": {}}
    if os.path.exists(state_path):
        state = json.load(open(state_path))
        state.setdefault("types", {})
    t_start = time.time()
    queries = []
    for q in a.query:
        if not a.shard_under:
            queries.append(q)
            continue
        # The shard boundaries are cached: they cost a count request
        # each, and a listing long enough to need shards is also long
        # enough to be resumed several times.
        sh = state.setdefault("shards", {})
        if q not in sh:
            sh[q] = size_shards(q, a.shard_under)
            save(state, state_path)
        queries += sh[q]
    for q in queries:
        full = q + (("&sortBy=%s" % a.sort) if a.sort else "")
        full += "&sortOrderDesc=desc" if a.desc else ""
        if full in state["queries"]:
            continue
        if time.time() - t_start > a.budget:
            print("listing not finished — %d/%d queries done, run again"
                  % (len(state["queries"]), len(queries)), flush=True)
            return 0
        print("query %s" % full, flush=True)
        rows = search(full, a.pages, a.limit)
        for r in rows:
            key = "%s/%s" % (r["itemid"], r["fileid"])
            state["files"][key] = r["size"]
            state["types"][key] = member_types(r)
        state["queries"][full] = len(rows)
        save(state, state_path)

    todo = [k for k, sz in state["files"].items()
            if k not in state["probed"] and sz >= a.min_size]
    if a.meta_type:
        want = set(a.meta_type)
        todo = [k for k in todo if want & set(state["types"].get(k) or ())]
        tally = {t: sum(1 for v in state["types"].values() if t in (v or ()))
                 for t in sorted(want)}
        print("member types over the %d listed: %s; %d with no member "
              "metadata at all"
              % (len(state["files"]), tally,
                 sum(1 for v in state["types"].values() if not v)),
              flush=True)
    print("%d file(s) listed, %d probed, %d to go"
          % (len(state["files"]), len(state["probed"]), len(todo)), flush=True)

    head = Head()
    t0, done = t_start, 0
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
            save(state, state_path)
            print("  %d probed, %.0f s" % (done, time.time() - t0), flush=True)
    save(state, state_path)

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
            # An installer payload can carry two hundred encrypted forks
            # of the same scheme; the list is a lead, not a manifest.
            more = len(flagged) - a.max_report
            flagged = flagged[:a.max_report]
            print("  %s\n    version %d, %d file(s): %s"
                  % (url_of(item, fileid), v["ver"], v["files"],
                     "; ".join("%r %s" % (e["name"], " ".join(
                         "%s meth %d%s%s%s" % (
                             f["fork"], f["meth"] & 0x0F,
                             " OPT id %d" % f["opt_id"]
                             if f["meth"] & 0x40 else "",
                             " ENC %s" % encname(f)
                             if f["meth"] & 0x80 else "",
                             " NewDE" if f["meth"] & 0x10 else "")
                         for f in e["forks"]))
                         for e in flagged)
                     + (" … and %d more" % more if more > 0 else "")))
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
