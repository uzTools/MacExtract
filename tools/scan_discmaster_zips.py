#!/usr/bin/env python3
"""scan_discmaster_zips.py — find Macintosh zips by reading their bytes.

Not in `ci.sh`: it needs the network, and what it produces is a list of
URLs rather than a verdict. It is here so the 2026-10-04 sweep can be
re-run and widened rather than re-invented (DECISIONS.md 2026-10-04,
*the archive that carried its own extractor*).

**The problem it solves.** A zip written by a Macintosh archiver is a
plain `.zip` with one extra field in each entry — Info-ZIP's `0x334d` or
ZipIt's `0x2605`/`0x2705`/`0x2805`. Nothing indexes that: Discmaster's
`detection` search is full-text over what each identifier PRINTED, and
no identifier prints an extra-field id. So a search by name finds
nothing and a search by content has no content to search.

**What it does instead.** The field is in the FIRST local file header,
within the first few dozen bytes of the archive, and Discmaster serves
`Range` requests. So: list every zip on the items you name, fetch 512
bytes of each, and parse. The 2026-10-04 run covered the 40 items
`fetch_specimens.py` cites — **3,029 zips for 1.5 MB of traffic**,
against 7.3 GB to download them — and found seven files carrying a
ZipIt field, four of them distinct archives, all four now specimens.

    tools/scan_discmaster_zips.py --items 11927 11960 11869 14746
    tools/scan_discmaster_zips.py --items-from tools/specimens/zipit.tsv

Progress is written to `--state` after every chunk and re-read on the
next run, so the sweep survives a timeout: run it again and it picks up
where it stopped. Run it in the FOREGROUND — a backgrounded process on
this machine loses network access and stalls with no error (CLAUDE.md).
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
# The Macintosh extra fields, and nothing else: an id this engine reads
# is the whole reason to look (src/fmt_exo.c, zip_extra_scan).
MAC_IDS = {0x2605: "ZipIt long", 0x2705: "ZipIt file",
           0x2805: "ZipIt dir", 0x334d: "Info-ZIP M3"}


def items_from(path):
    """Discmaster item ids cited by a specimen table (or any file of
    `.../file/<id>/...` URLs)."""
    text = open(path, encoding="utf-8").read()
    return sorted(set(int(m) for m in re.findall(r"/file/(\d+)/", text)))


def zips_on(item, pages=4, limit=1000):
    """Every file Discmaster identifies as a zip on one item."""
    out, seen = [], set()
    # `pageNum` is 0-based: the form's "next" link for page two reads
    # pageNum=1, and pageNum=1 on a one-page result returns an EMPTY
    # array rather than an error — which is how a sweep can look
    # complete and have fetched nothing.
    for page in range(pages):
        url = ("https://%s/search?format=zip&itemid=%d&limit=%d&pageNum=%d"
               "&outputAs=json" % (HOST, item, limit, page))
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=180) as r:
            rows = json.loads(r.read().decode("utf-8", "replace"))
        fresh = [x for x in rows if x["fileid"] not in seen]
        seen.update(x["fileid"] for x in fresh)
        out += fresh
        if len(rows) < limit:
            break
    return out


def mac_fields(head):
    """Macintosh extra-field ids in the first local header of `head`,
    or None if `head` does not start one."""
    if head[:4] != b"PK\x03\x04" or len(head) < 30:
        return None
    nlen, elen = struct.unpack("<HH", head[26:30])
    ex = head[30 + nlen:30 + nlen + elen]
    out, q = [], 0
    while q + 4 <= len(ex):
        hid, hsz = struct.unpack("<HH", ex[q:q + 4])
        if hid in MAC_IDS:
            out.append((hid, hsz, ex[q + 4:q + 4 + hsz].hex()))
        q += 4 + hsz
    return head[30:30 + nlen].decode("mac_roman", "replace"), out


class Head:
    """One keep-alive connection, re-made when the server drops it."""

    def __init__(self):
        self.conn = None

    def get(self, path, nbytes=512):
        for attempt in (0, 1):
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPSConnection(HOST, timeout=30)
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


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", type=int, nargs="+", default=[])
    ap.add_argument("--items-from", action="append", default=[],
                    help="a file holding /file/<id>/ URLs, e.g. a specimen "
                         "table or fixtures/SOURCES.md")
    ap.add_argument("--state", default="/tmp/discmaster-zips.json",
                    help="where the sweep's progress is kept between runs")
    ap.add_argument("--budget", type=float, default=600.0,
                    help="seconds to spend fetching headers this run")
    a = ap.parse_args()

    items = list(a.items)
    for path in a.items_from:
        items += items_from(path)
    items = sorted(set(items))
    if not items:
        ap.error("name at least one item (--items or --items-from)")

    state = {"zips": {}, "heads": {}}
    if os.path.exists(a.state):
        state = json.load(open(a.state))
    for item in items:
        if str(item) in state["zips"]:
            continue
        rows = zips_on(item)
        state["zips"][str(item)] = [(r["fileid"], r["size"]) for r in rows]
        print("item %d: %d zip(s)" % (item, len(rows)))
        json.dump(state, open(a.state, "w"))

    todo = [(int(i), f, sz) for i, rows in state["zips"].items()
            for f, sz in rows if f not in state["heads"]]
    total = sum(len(v) for v in state["zips"].values())
    head = Head()
    t0, done = time.time(), 0
    for item, fileid, size in todo:
        if time.time() - t0 > a.budget:
            break
        blob = head.get("/file/%d/%s" % (item, urllib.parse.quote(fileid)))
        if not blob:
            state["heads"][fileid] = {"err": "no bytes"}
        else:
            got = mac_fields(blob)
            state["heads"][fileid] = (
                {"notzip": blob[:4].hex()} if got is None
                else {"item": item, "size": size, "first": got[0],
                      "mac": [list(f) for f in got[1]]})
        done += 1
    json.dump(state, open(a.state, "w"))

    hits = {k: v for k, v in state["heads"].items() if v.get("mac")}
    print("%d header(s) this run, %d/%d read, %d carrying a Macintosh field"
          % (done, len(state["heads"]), total, len(hits)))
    for k in sorted(hits):
        v = hits[k]
        print("  https://%s/file/%d/%s" % (HOST, v["item"],
                                           urllib.parse.quote(k)))
        print("    %d B, first entry %r, %s"
              % (v["size"], v["first"],
                 ", ".join("%s 0x%04x/%d" % (MAC_IDS[i], i, s)
                           for i, s, _ in v["mac"])))
    if len(state["heads"]) < total:
        print("not finished — run again to continue (%s)" % a.state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
