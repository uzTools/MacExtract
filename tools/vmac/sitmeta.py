#!/usr/bin/env python3
"""sitmeta.py — which StuffIt classic header bytes does StuffIt Expander restore?

No reference says where a classic StuffIt archive keeps a file's icon
position or a folder's window, yet Expander puts them back. This hands
Expander 4.0.2 archives on an emulated Mac Plus, reads every file's
FInfo/FXInfo and every folder's DInfo/DXInfo back off the disk
(`hfscat.py`), and lines each catalog field up against every byte of the
header the entry came from.

    sitmeta.py --list FIXTURE...       writer class and entries; no emulator
    sitmeta.py --plan                  the corpus cut into boot-sized batches
    sitmeta.py --synth                 write the sentinel archives (below)
    sitmeta.py --run [--tag T] ARCHIVE...   one boot over these archives
    sitmeta.py --batch N               --run over batch N of --plan
    sitmeta.py --report [--tag T]      line every result up, per writer class

Results are JSON in $UNC_VMAC_HOME/../sitmeta/ (`RESULTS`), one file per
boot, holding each header and the catalog record it became; screenshots
and the image go in `.tmp/` through tools/guard.py.

**Two kinds of evidence, and they answer different questions.**

- **The corpus** says what real writers put in those bytes and what
  Expander makes of it: per field, over how many entries, with every
  exception listed by fixture and entry.
- **The sentinel archives** (`--synth`) say which bytes Expander READS. Every
  byte no reference defines is filled with a value that names its own
  offset, so a field that comes back holding 0x01 0x27 can only have come
  from @38. Variants switch one suspected gate at a time: the version byte,
  the 0x0986 word at @36, the link fields, and the bytes @104..109.

How a run is driven: Expander is the boot shell (`mkboot.py`), the
archives are at the volume root under short names, and each is opened by
⌘E, its name typed into Standard File (type-select), and the Expand button
pressed at expander.py's measured coordinate. Return is pressed after each,
which dismisses an alert if one is up. ⌘Q at the end is what commits
Expander's writes (tools/vmac/README.md, *The yardstick*); the catalog is
then polled on the host until it stops changing.

What this CANNOT see:

- **Get Info comments.** They live in the Finder's Desktop file, which
  Expander may or may not touch and `hfscat.py` does not read.
- **Anything Expander 4.0.2 does differently from other Aladdin expanders.**
  One reader. The writers are many — whatever wrote the corpus — but what
  this measures is what THIS expander restores.
- **An entry whose name is changed on the way out** (a collision Expander
  renamed): it is reported unmatched, never guessed at.
- **Encrypted archives**, which stop at a password dialog: `--plan` leaves
  them out, and an Optimizer module's archives with them.
"""
import argparse
import glob
import hashlib
import json
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import guard                                                 # noqa: E402
import run as R                                              # noqa: E402
import hfscat                                                # noqa: E402

RESULTS = os.path.join(os.path.dirname(R.VMAC_HOME), "sitmeta")
SYNTH = os.path.join(RESULTS, "synth")


def _fixtures():
    """This checkout's fixtures, or — in a git worktree, where the
    uncommitted archives are absent — the main checkout's."""
    import subprocess
    here = os.path.join(REPO, "fixtures")
    if glob.glob(os.path.join(here, "*.sit")):
        return here
    common = subprocess.run(["git", "-C", REPO, "rev-parse",
                             "--git-common-dir"], capture_output=True,
                            text=True).stdout.strip()
    return os.path.join(os.path.dirname(os.path.abspath(
        os.path.join(REPO, common))), "fixtures")


FIXTURES = os.environ.get("UNC_FIXTURES") or _fixtures()
HDR = 112

# Source: reference/XADMaster/XADStuffItParser.m (StuffItStartFolder,
# StuffItEndFolder, StuffItFolderMask, StuffItEncryptedFlag).
START, END, FOLDER_MASK, ENCRYPTED = 0x20, 0x21, 0x6F, 0x80
# Source: src/fmt_sit.c — SIT_NEWDE and SIT_OPTIMIZED, read out of
# StuffIt Deluxe 2.0.1 (FORMATS.md, *Where an archive names the module*).
NEWDE, OPTIMIZED = 0x10, 0x40


def crc16_arc(data, c=0):
    """CRC-16/ARC (reflected 0xA001, init 0): the header CRC
    (XADStuffItParser.m, XADCRCTable_a001) and — measured 2026-10-16 on
    derived-AsciiConverter.sit, four headers — the @34 word over bytes
    2..33, the name's length byte and its 31-byte field."""
    for x in data:
        c ^= x
        for _ in range(8):
            c = (c >> 1) ^ 0xA001 if c & 1 else c >> 1
    return c


# ------------------------------------------------------------------
# Reading an archive
# ------------------------------------------------------------------

def _sit5_name(raw):
    """A StuffIt 5 name as HFS will hold it: MacRoman. The engine treats
    them as UTF-8 (src/fmt_sit5.c, name_utf8); a name that is not valid
    UTF-8 is taken as already MacRoman."""
    try:
        return raw.decode("utf-8").encode("mac-roman")[:31]
    except (UnicodeDecodeError, UnicodeEncodeError):
        return raw[:31]


def parse_sit5(blob):
    """StuffIt 5's entries, walked as src/fmt_sit5.c walks them (that
    file cites XADStuffIt5Parser.m and docs/formats/stuffit5-container.md
    for every offset). `hdr` is the whole entry header, first block to
    the start of the data; `b2` is where its second block starts."""
    if blob[82] != 5:
        raise ValueError("not a version 5 StuffIt archive")
    n = struct.unpack(">H", blob[92:94])[0]
    pos = struct.unpack(">I", blob[94:98])[0]
    dirs, out, i = {}, [], 0
    while i < n and pos + 48 <= len(blob):
        h = blob[pos:pos + 48]
        if h[:4] != b"\xa5\xa5\xa5\xa5":
            raise ValueError("no entry at %d" % pos)
        ver, hsize, flags = h[4], struct.unpack(">H", h[6:8])[0], h[9]
        diroffs, namelen = struct.unpack(">IH", h[26:32])
        dlen, dcomp = struct.unpack(">II", h[34:42])
        hp = pos + 46
        isdir = flags & 0x40
        if isdir:
            nfiles = struct.unpack(">H", blob[hp:hp + 2])[0]
            hp += 2
            if dlen == 0xFFFFFFFF:                 # the marker entry
                i += 1
                pos += hsize
                continue
        else:
            hp += 2 + blob[hp + 1]
        name = _sit5_name(blob[hp:hp + namelen])
        hp += namelen
        if hp < pos + hsize:
            hp += 4 + struct.unpack(">H", blob[hp:hp + 2])[0]
        b2 = hp - pos
        flags2 = struct.unpack(">H", blob[hp:hp + 2])[0]
        hp += 14 + (22 if ver == 1 else 18)
        rcomp = 0
        if flags2 & 1:
            rcomp = struct.unpack(">I", blob[hp + 4:hp + 8])[0]
            hp += 14 + blob[hp + 13]
        path = dirs.get(diroffs, ()) + (name,)
        e = dict(kind="dir" if isdir else "file", off=pos, path=path,
                 hdr=blob[pos:hp], b2=b2, crypted=bool(flags & 0x20),
                 ver=ver)
        out.append(e)
        i += 1
        if isdir:
            dirs[pos] = path
            n += nfiles
            pos = hp
        else:
            pos = hp + rcomp + dcomp
    return out


def parse(blob):
    """The archive's entries: kind ('file', 'dir', 'end'), offset, path
    (a tuple of names as bytes, each cut to 31 like an HFS name) and the
    112 header bytes. Stops at the first header whose CRC fails."""
    # Source: reference/notes/sit_format_theunarchiver.md, *Archive
    # header* and *File headers*.
    if blob[:16] == b"StuffIt (c)1997-":
        return parse_sit5(blob)
    if blob[10:14] != b"rLau":
        raise ValueError("not a StuffIt classic archive")
    total = min(struct.unpack(">I", blob[6:10])[0], len(blob))
    pos, stack, out = 22, [], []
    while pos + HDR <= total:
        h = blob[pos:pos + HDR]
        if crc16_arc(h[:110]) != struct.unpack(">H", h[110:112])[0]:
            break
        name = h[3:3 + min(h[2], 63)][:31]
        rm, dm = h[0] & FOLDER_MASK, h[1] & FOLDER_MASK
        if rm == START or dm == START:
            stack.append(name)
            out.append(dict(kind="dir", off=pos, path=tuple(stack), hdr=h))
            pos += HDR
        elif rm == END or dm == END:
            out.append(dict(kind="end", off=pos, path=tuple(stack), hdr=h))
            if stack:
                stack.pop()
            pos += HDR
        else:
            out.append(dict(kind="file", off=pos, path=tuple(stack + [name]),
                            hdr=h))
            pos += HDR + struct.unpack(">I", h[92:96])[0] \
                + struct.unpack(">I", h[96:100])[0]
    return out


def writer(blob, entries):
    """A writer class: the version byte (archive @14) and whether any
    header carries 0x0986 at @36. These two separate the corpus into
    groups whose unknown bytes look alike (DECISIONS.md 2026-10-17,
    *the window StuffIt kept in the name*)."""
    if blob[:8] == b"StuffIt ":
        return "sit5/v%s" % "".join(sorted({str(e["ver"]) for e in entries}))
    mark = any(e["hdr"][36:38] == b"\x09\x86" for e in entries)
    return "v%d%s" % (blob[14], "/0986" if mark else "")


def refusals(entries):
    """Why Expander could not run unattended on this archive, or None."""
    for e in entries:
        if e["kind"] != "file":
            continue
        if "b2" in e:
            if e["crypted"]:
                return "encrypted"
            continue
        for m in e["hdr"][0:2]:
            if m & (ENCRYPTED | NEWDE | OPTIMIZED):
                return "encrypted or optimized"
            if m & 0x0F not in (0, 1, 2, 3, 5, 6, 8, 13):
                return "method %d" % (m & 0x0F)
    return None


def cmd_list(paths):
    for p in paths:
        blob = open(p, "rb").read()
        ents = parse(blob)
        print("%s  %s  %d entries  %s" % (os.path.basename(p),
              writer(blob, ents), len(ents), refusals(ents) or "ok"))
        for e in ents:
            h = e["hdr"]
            print("  %-4s %-40s 34:%s 100:%s" % (
                e["kind"], b"/".join(e["path"]).decode("mac-roman")[-40:],
                h[34:66].hex(), h[100:110].hex()))


# ------------------------------------------------------------------
# Batches
# ------------------------------------------------------------------

def corpus(family="classic"):
    """Every raw StuffIt classic fixture a real writer made: (path, blob,
    entries). `synth-*` are this project's own and say nothing about one."""
    out = []
    for p in sorted(glob.glob(os.path.join(FIXTURES, "*"))):
        if not os.path.isfile(p) or os.path.basename(p).startswith("synth-"):
            continue
        blob = open(p, "rb").read()
        if family == "classic" and (len(blob) < 22
                                    or blob[10:14] != b"rLau"):
            continue
        if family == "sit5" and blob[:16] != b"StuffIt (c)1997-":
            continue
        try:
            out.append((p, blob, parse(blob)))
        except ValueError:
            pass
    return out


def plan(max_bytes=4 << 20, max_n=8, family="classic"):
    """Batches whose top-level names are disjoint from each other's, so a
    name on the volume can belong to one archive only; each under
    max_bytes of archive (the volume is 24 MB and the output is larger
    than the input)."""
    todo, skipped = [], []
    for p, blob, ents in corpus(family):
        why = refusals(ents)
        if why or not ents:
            skipped.append((os.path.basename(p), why or "no entries"))
        else:
            tops = {e["path"][0] for e in ents}
            todo.append((p, len(blob), tops))
    batches = []
    for p, size, tops in todo:
        for b in batches:
            if (len(b["fixtures"]) < max_n and b["bytes"] + size <= max_bytes
                    and not (b["tops"] & tops)):
                b["fixtures"].append(p)
                b["bytes"] += size
                b["tops"] |= tops
                break
        else:
            batches.append(dict(fixtures=[p], bytes=size, tops=set(tops)))
    return [b["fixtures"] for b in batches], skipped


# ------------------------------------------------------------------
# Sentinel archives
# ------------------------------------------------------------------

def sentinel(o, page, byteoff):
    """The byte at header offset `o`. With byteoff, the byte IS the offset;
    otherwise words read as `page`:offset+1 — 0x0127 at @38 — values small
    enough to be a plausible coordinate, so Expander has no reason to
    reject them."""
    if byteoff:
        return o
    return page if o % 2 == 0 else o


def synth_archive(version=2, mark=True, byteoff=False, links=True,
                  tail=False, namecrc=True, garbage=False, top=b"S1",
                  override=None, crc_any_version=False):
    """A folder `top` holding a file, and a folder holding another file.

    Every byte nothing defines is a sentinel (page 0x01 in a start header,
    0x02 in an end header, 0x03 in a file header). What IS defined is
    written as a writer would: methods, name, type and creator, dates,
    lengths, fork CRCs, the header CRC; and with `links`, the child count
    and the prev/next/parent/first-child offsets (XADStuffItParser.m,
    SITFH_CHILDCOUNT..SITFH_CHILDOFFS), so Expander can walk it however it
    walks a real one.
    """
    data1 = b"sentinel file one\r" * 3
    data2 = b"sentinel file two\r" * 5
    plan_ = [("dir", top), ("file", top + b"f1", data1), ("dir", top + b"in"),
             ("file", top + b"f2", data2), ("end", top + b"in"),
             ("end", top)]
    hdrs, offs = [], []
    pos = 22
    for item in plan_:
        offs.append(pos)
        pos += HDR + (len(item[2]) if item[0] == "file" else 0)
    total = pos
    # parents and children, for the link fields
    parent, first_child, nchild, stack = {}, {}, {}, []
    for i, item in enumerate(plan_):
        if item[0] == "end":
            stack.pop()
            continue
        parent[i] = offs[stack[-1]] if stack else 0
        if stack:
            first_child.setdefault(stack[-1], offs[i])
            nchild[stack[-1]] = nchild.get(stack[-1], 0) + 1
        if item[0] == "dir":
            stack.append(i)
    date = 0xA1000000 + (version << 16) + (mark << 12)
    for i, item in enumerate(plan_):
        kind, name = item[0], item[1]
        page = {"dir": 1, "end": 2, "file": 3}[kind]
        h = bytearray(sentinel(o, page, byteoff) for o in range(HDR))
        h[0] = h[1] = {"dir": START, "end": END, "file": 0}[kind]
        h[2] = len(name)
        h[3:3 + len(name)] = name
        if (version >= 2 or crc_any_version) and namecrc:
            struct.pack_into(">H", h, 34, crc16_arc(bytes(h[2:34])))
        h[36:38] = b"\x09\x86" if mark else b"\x00\x00"
        if links and kind != "end":
            struct.pack_into(">H", h, 48, nchild.get(i, 0))
            struct.pack_into(">I", h, 50, offs[i - 1] if i else 0)
            struct.pack_into(">I", h, 54, offs[i + 1] if i + 1 < len(offs)
                             else 0)
            struct.pack_into(">I", h, 58, parent[i])
            if kind == "dir":
                struct.pack_into(">I", h, 62, first_child.get(i, 0))
        if kind == "file":
            h[66:70], h[70:74] = b"TEXT", b"ttxt"
            struct.pack_into(">H", h, 74, 0x0420)
            d = item[2]
            struct.pack_into(">IIIIIIHH", h, 76, date + i * 0x100,
                             date + i * 0x100 + 1, 0, len(d), 0, len(d),
                             0, crc16_arc(d))
            if not tail:
                h[104:110] = bytes(6)
        else:
            struct.pack_into(">II", h, 76, date + i * 0x100,
                             date + i * 0x100 + 1)
            struct.pack_into(">IIII", h, 84, 0, 0, 0, 0)
        if garbage and kind != "end":
            # implausible values where the corpus measurement puts the
            # Finder fields: a location far off any screen, a rectangle
            # whose bottom is above its top, every frFlags bit
            if kind == "file":
                h[62:66] = b"\x7f\xff\x80\x00"
            else:
                h[38:46] = struct.pack(">hhhh", 300, 400, 10, 20)
                h[70:74] = b"\x80\x00\x7f\xff"
                h[74:76] = b"\xff\xff"
                h[100:104] = b"\x7f\x00\x80\x01"
        for o, v in ((override or {}).get(kind) or {}).items():
            h[o:o + len(v)] = v
        struct.pack_into(">H", h, 110, crc16_arc(bytes(h[:110])))
        hdrs.append(bytes(h))
    body = b""
    for item, h in zip(plan_, hdrs):
        body += h + (item[2] if item[0] == "file" else b"")
    arch = bytearray(22)
    arch[0:4] = b"SIT!"
    struct.pack_into(">HI", arch, 4, 1, total)
    arch[10:14] = b"rLau"
    arch[14] = version
    if version >= 2:
        # the bytes 15..21 26 v2 fixtures carry: 00, headersize 0x16, 0000
        arch[15:22] = bytes.fromhex("00000000160000")
    return bytes(arch) + body


SYNTH_SET = [
    # name   keyword arguments                    what it isolates
    ("S1", dict(version=2, mark=True), "an Aladdin 0x0986 writer, plausible sentinels"),
    ("S2", dict(version=2, mark=False), "the same with 0000 at @36"),
    ("S3", dict(version=1, mark=False), "the same under version byte 1"),
    ("S4", dict(version=2, mark=True, byteoff=True), "every byte its own offset"),
    ("S5", dict(version=2, mark=True, links=False), "link fields left as sentinels"),
    ("S6", dict(version=2, mark=True, tail=True), "files' @104..109 as sentinels too"),
    ("S7", dict(version=2, mark=True, garbage=True), "implausible values at the measured offsets"),
    ("S8", dict(version=2, mark=True, namecrc=False), "a wrong name CRC at @34"),
]


# The second boot: each gate the first one confounded, alone.
G = b"\x5a\x5a\x5a\x5a"
SYNTH_SET2 = [
    ("T1", dict(version=1, mark=False, crc_any_version=True), "version 1 WITH a valid name CRC"),
    ("T2", dict(version=0, mark=False, crc_any_version=True), "version 0 with a valid name CRC"),
    ("T3", dict(override={"dir": {48: G[:2]}, "file": {48: G[:2]}}), "garbage child count @48"),
    ("T4", dict(override={"dir": {50: G}, "file": {50: G}}), "garbage previous @50"),
    ("T5", dict(override={"dir": {54: G}, "file": {54: G}}), "garbage next @54"),
    ("T6", dict(override={"dir": {58: G}, "file": {58: G}}), "garbage parent @58"),
    ("T7", dict(override={"dir": {62: G}}), "garbage first child @62, folders"),
    ("T8", dict(override={"file": {48: b"\x80\x01"}}), "files' @48 = 0x8001, as some real files carry"),
]


# The third boot: bit 15 of @36, which three corpus files carry and come
# back LOCKED with (the model check's only exceptions, 2026-10-17).
SYNTH_SET3 = [
    ("U1", dict(mark=False, override={"file": {36: b"\x80\x00"},
                                      "dir": {36: b"\x80\x00"}}),
     "@36 = 0x8000, valid name CRC"),
    ("U2", dict(mark=True, override={"file": {36: b"\x89\x86"}}),
     "@36 = 0x8986: the bit beside the 0x0986 mark"),
    ("U3", dict(version=1, mark=False, crc_any_version=True,
                override={"file": {36: b"\x80\x00"}}),
     "version 1, valid CRC, @36 = 0x8000"),
    ("U4", dict(mark=False, namecrc=False,
                override={"file": {36: b"\x80\x00"}}),
     "@36 = 0x8000 with a WRONG name CRC"),
    ("U5", dict(mark=False, override={"file": {36: b"\x7f\xff"},
                                      "dir": {36: b"\x7f\xff"}}),
     "@36 = 0x7fff: every other bit"),
]


def cmd_synth():
    os.makedirs(SYNTH, exist_ok=True)
    out = []
    for name, kw, what in SYNTH_SET + SYNTH_SET2 + SYNTH_SET3:
        p = os.path.join(SYNTH, "synth-%s.sit" % name)
        with open(p, "wb") as f:
            f.write(synth_archive(top=name.encode(), **kw))
        out.append(p)
        print("sitmeta: %s  %s" % (p, what))
    return out


# ------------------------------------------------------------------
# One boot
# ------------------------------------------------------------------

def run_boot(archives, tag, emu, system, quiet):
    import subprocess
    from arcmac import macbinary
    from interactive import Mac
    import expander as X

    if not os.path.exists(X.APPBIN):
        raise SystemExit("sitmeta: no Expander.bin — expander.py --fetch")
    work = guard.run_dir("sitmeta")
    shots = os.path.join(work, "shots")
    os.makedirs(shots, exist_ok=True)
    names, argv = [], []
    for i, a in enumerate(archives):
        # Short, unique, and sorting after anything else at the root, so
        # that typing it into Standard File can select nothing else.
        mac = "zq%02d.sit" % i
        names.append(mac)
        mb = os.path.join(work, mac + ".bin")
        with open(mb, "wb") as f:
            f.write(macbinary(mac, "SIT!", "SIT!", data=open(a, "rb").read()))
        argv += ["--macbin", "%s:%s" % (mb, mac)]
    boot = os.path.join(work, "boot-in.hfv")
    R.sh(sys.executable, os.path.join(HERE, "mkboot.py"),
         os.path.join(R.VMAC_HOME, system), X.APPBIN, boot,
         "--app-name", X.APP_NAME, *argv)
    pre = {(r["path"], r["kind"]) for r in
           hfscat.records(open(boot, "rb").read())}

    m = Mac(boot, emu, work)
    live = os.path.join(work, "boot.hfv")
    n = [0]

    def shot(t):
        n[0] += 1
        m.shot(os.path.join(shots, "%03d-%s.png" % (n[0], t)))

    def new_records():
        try:
            recs = hfscat.records(open(live, "rb").read())
        except (ValueError, struct.error, IndexError):
            return None
        return [r for r in recs if (r["path"], r["kind"]) not in pre]

    try:
        scratch = os.path.join(work, "s.png")
        if m.settle(scratch, interval=4.0, timeout=300.0) is None:
            raise SystemExit("sitmeta: the machine never booted")
        shot("booted")
        m.origin(cached=False)
        for mac in names:
            m.command_key("e")
            time.sleep(2.5)
            m._xdo("type", "--delay", "80", mac[:4])
            time.sleep(1.0)
            shot(mac + "-selected")
            m.click(*X.EXPAND_BUTTON)
            X.last_change(m, scratch, 1.5, quiet, 900.0)
            shot(mac + "-done")
            m.key("Return")
            time.sleep(1.5)
        m.command_key("q")
        # The writes land at the quit; wait until the catalog stops
        # changing (two equal reads 5 s apart), at most three minutes.
        t0, last = time.time(), None
        while time.time() - t0 < 180:
            time.sleep(5)
            cur = new_records()
            key = None if cur is None else sorted(
                (r["path"], r["rec"]) for r in cur)
            if cur and key == last:
                break
            last = key
        time.sleep(5)
        shot("quit")
    finally:
        m.close()
    post = new_records() or []
    result = dict(tag=tag, emu=emu, system=system,
                  when=time.strftime("%Y-%m-%d %H:%M:%S"),
                  shots=shots, archives=[],
                  new=[dict(path=[x.hex() for x in r["path"]],
                            kind=r["kind"], rec=r["rec"].hex())
                       for r in post])
    for a, mac in zip(archives, names):
        blob = open(a, "rb").read()
        ents = parse(blob)
        rows = []
        for e in ents:
            row = dict(kind=e["kind"], off=e["off"],
                       path=[x.hex() for x in e["path"]], hdr=e["hdr"].hex())
            if e["kind"] != "end":
                want = hfscat.DIR if e["kind"] == "dir" else hfscat.FILE
                cands = [r for r in post if r["kind"] == want
                         and r["path"][-len(e["path"]):] == e["path"]]
                row["candidates"] = len(cands)
                if len(cands) == 1:
                    row["match"] = dict(path=[x.hex() for x in
                                              cands[0]["path"]],
                                        rec=cands[0]["rec"].hex())
            rows.append(row)
        result["archives"].append(dict(
            fixture=os.path.basename(a), macname=mac,
            sha256=hashlib.sha256(blob).hexdigest(),
            writer=writer(blob, ents), arch=blob[:22].hex(), entries=rows))
        got = sum("match" in r for r in rows)
        want = sum(r["kind"] != "end" for r in rows)
        print("sitmeta: %-40s %-8s %3d/%3d entries matched on the volume"
              % (os.path.basename(a), writer(blob, ents), got, want))
    os.makedirs(RESULTS, exist_ok=True)
    out = os.path.join(RESULTS, "%s-%s.json" % (
        tag, time.strftime("%Y%m%d-%H%M%S")))
    json.dump(result, open(out, "w"), indent=0)
    print("sitmeta: %d new catalog records; results in %s" % (len(post), out))
    return out


# ------------------------------------------------------------------
# The writer side: StuffIt Deluxe 2.0.1 stuffs a folder whose catalog
# records carry sentinels
# ------------------------------------------------------------------

# Sentinels planted in the catalog records before boot (hfscat.py's
# layouts). Each value names the field it was put in. Wf2 is LOCKED.
W_TREE = [  # (path under the volume, kind)
    (("Wfold",), "dir"), (("Wfold", "Wf1"), "file"),
    (("Wfold", "Win"), "dir"), (("Wfold", "Win", "Wf2"), "file")]
W_DIR = {"frRect": (22, b"\x00\x31\x00\x42\x01\x53\x01\x64"),
         "frFlags": (30, b"\x04\x00"),
         "frLocation": (32, b"\x00\x75\x00\x86"),
         "frView": (36, b"\x02\x00"),
         "frScroll": (38, b"\x00\x11\x00\x22"),
         "DXInfo rest": (42, bytes(range(0x51, 0x5d))),
         "dirBkDat": (18, b"\xa5\xa6\xa7\xa8")}
W_FILE = {"fdFlags": (12, b"\x01\x20"),
          "fdLocation": (14, b"\x01\x23\x01\x45"),
          "FXInfo": (56, bytes(range(0x61, 0x71))),
          "filBkDat": (52, b"\xb5\xb6\xb7\xb8")}
W_SCRIPT = "\r".join([
    "; written by tools/vmac/sitmeta.py --writer201",
    'Write Status To "{Startup}MetaStatus.out"',
    "Continue On Error",
    'New Archive "{Startup}Meta.sit"',
    'Stuff "{Startup}Wfold" with fast',
    "Close",
    "Quit", ""])


def writer201(emu):
    import subprocess
    import tempfile
    import sitopt as O
    from arcmac import macbinary
    if not os.path.exists(O.BOOT):
        raise SystemExit("sitmeta: no %s — sitopt.py --personalize" % O.BOOT)
    work = guard.run_dir("sitmeta-w201")
    img = os.path.join(work, "w201.hfv")
    shutil_copy(O.BOOT, img)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    vol = O.VOL
    run = lambda *a: subprocess.run(a, env=env, capture_output=True,  # noqa
                                    check=True)
    run("hmount", img)
    for path, kind in W_TREE:
        mac = ":".join((vol,) + path)
        if kind == "dir":
            run("hmkdir", mac)
        else:
            src = os.path.join(work, path[-1])
            open(src, "wb").write(("subject %s\r" % path[-1]).encode() * 40)
            run("hcopy", "-r", src, mac)
            run("hattrib", "-t", "TEXT", "-c", "ttxt", mac)
    sc = os.path.join(work, "script.bin")
    open(sc, "wb").write(macbinary("Zmeta", "TEXT", "SIT!",
                                   W_SCRIPT.encode("mac-roman")))
    run("hcopy", "-m", sc, vol + ":")
    run("humount")
    for path, kind in W_TREE:
        full = (vol.encode(),) + tuple(x.encode() for x in path)
        for _f, (off, v) in (W_DIR if kind == "dir" else W_FILE).items():
            hfscat.patch(img, full, off, v)
        if path[-1] == "Wf2":
            hfscat.patch(img, full, 2, b"\x01")            # locked
    s = O.Session(img, [], os.path.join(work, "shots"), mem=emu)
    try:
        args = argparse.Namespace(launch_wait=40.0)
        O.launch(s, args)
        s.menu(O.EDIT_X, O.EDIT_SWITCH_Y, "edit-switch")
        s.shot("expert", wait=3.0)
        s.mac.command_key("e")
        s.shot("script-picker", wait=8.0)
        s.mac._xdo("type", "--delay", "120", "Zmeta")
        s.shot("script-selected", wait=2.0)
        s.mac.key("Return")
        s.shot("script-running", wait=60.0)
        s.shot("script-done", wait=20.0)
        s.menu(O.SPECIAL_X, O.SHUT_DOWN_Y, "special-menu")
        s.shot("off", wait=35.0)
        written = os.path.join(s.work, "boot.hfv")
        run("hmount", written)
        for n in ("Meta.sit", "MetaStatus.out"):
            subprocess.run(["hcopy", "-m", vol + ":" + n,
                            os.path.join(work, n + ".bin")],
                           env=env, capture_output=True)
        run("humount")
        after = hfscat.records(open(written, "rb").read())
    finally:
        time.sleep(4)
        s.close()
    st = os.path.join(work, "MetaStatus.out.bin")
    if os.path.exists(st):
        print(open(st, "rb").read()[128:].split(b"\0")[0]
              .decode("mac-roman", "replace").replace("\r", "\n"))
    mb = os.path.join(work, "Meta.sit.bin")
    if not os.path.exists(mb):
        raise SystemExit("sitmeta: no Meta.sit came back — %s" % work)
    b = open(mb, "rb").read()
    dlen = struct.unpack(">I", b[83:87])[0]
    blob = b[128:128 + dlen]
    os.makedirs(RESULTS, exist_ok=True)
    keep = os.path.join(RESULTS, "writer201-Meta.sit")
    open(keep, "wb").write(blob)
    # what the source records held at the moment of stuffing
    before = {r["path"][1:]: r for r in after
              if r["path"][:2] == (vol.encode(), b"Wfold")}
    ents = parse(blob)
    print("sitmeta: Meta.sit, %s, %d entries; kept as %s"
          % (writer(blob, ents), len(ents), keep))
    for e in ents:
        if e["kind"] == "end":
            continue
        h = e["hdr"]
        fields_ = W_DIR if e["kind"] == "dir" else W_FILE
        print("  %s %s" % (e["kind"], b"/".join(e["path"]).decode()))
        src = before.get(tuple(e["path"]))
        for f, (off, v) in fields_.items():
            # the planted value, and the record as it stood after the
            # run if the Finder changed it since
            cur = src["rec"][off:off + len(v)] if src else v
            at = where(v, h, None)
            print("     %-11s planted %-26s header %s" % (
                f, v.hex(), ", ".join(at) or "NOWHERE"))
            if cur != v:
                print("     %-11s now     %-26s header %s" % (
                    "", cur.hex(), ", ".join(where(cur, h, None))
                    if any(cur) else "-"))
        if src and e["kind"] == "file":
            print("     %-11s catalog %-26s header bytes 104..109 %s" % (
                "locked", "%02x" % src["rec"][2], h[104:110].hex()))
    return 0


def shutil_copy(a, b):
    import shutil
    shutil.copyfile(a, b)


# ------------------------------------------------------------------
# StuffIt 5's second block, read by StuffIt Expander 5.5 (Mac OS 9)
# ------------------------------------------------------------------

def sit5_sentinel(blob, last=36, files_only=False):
    """A copy of a StuffIt 5 archive whose second blocks carry sentinels:
    for a file, bytes +14..35 (after type, creator and flags); for a
    folder, +4..35 (`last`=20 stops at the end of the FInfo/DInfo half).
    Byte k of the block is k at an odd k and the page
    (0x01 file, 0x02 folder) at an even one. The first block, and the CRC
    it carries, are untouched."""
    out = bytearray(blob)
    for e in parse_sit5(blob):
        if e["ver"] != 1:
            raise SystemExit("sitmeta: a version %d entry; only 1 is "
                             "measured" % e["ver"])
        if files_only and e["kind"] == "dir":
            continue
        at = e["off"] + e["b2"]
        page, first = (0x02, 4) if e["kind"] == "dir" else (0x01, 14)
        for k in range(first, last):
            out[at + k] = k if k % 2 else page
        # b+2 is a CRC-16/ARC of the whole second block, to the start of
        # the data, with b+2..3 zeroed — measured 2026-10-17 on all 272
        # entries of the StuffIt 5 corpus. Expander 5.5 refuses an entry
        # whose word disagrees ("a disk related error (-12043)"), which
        # is what four sentinel boots got before this was found.
        end = e["off"] + len(e["hdr"])
        blk = bytearray(out[at:end])
        blk[2:4] = b"\0\0"
        struct.pack_into(">H", out, at + 2, crc16_arc(bytes(blk)))
    return bytes(out)


def sit5_run(archive, outdir, plain=False, last=36, files_only=False):
    """`plain` hands Expander the archive unmodified: the control that
    says whether a refusal is the sentinels' doing."""
    import sitzip as Z
    from arcmac import macbinary as mb
    blob = open(archive, "rb").read()
    if not plain:
        blob = sit5_sentinel(blob, last, files_only)
    sub = os.path.join(outdir, "sentinel5.sit")
    os.makedirs(outdir, exist_ok=True)
    open(sub, "wb").write(blob)
    # sitzip.py's run, with this archive as its subject: named so the
    # 5.5 dialog's `pick` ("r") selects it, typed SIT5/SITx.
    Z.SUBJECT, Z.SUBJECT_NAME = sub, "Rsentinel.sit"
    Z.macbinary = lambda name, t, c, *a, **k: mb(
        name, "SIT5" if name == Z.SUBJECT_NAME else t, c, *a, **k)
    args = argparse.Namespace(boot_wait=600.0, settle_wait=300.0)
    Z.run("55", outdir, args)
    part = os.path.join(outdir, "transfer.hfs")
    recs = hfscat.records(open(part, "rb").read())
    ents = parse_sit5(blob)
    print("\nsitmeta: %d entries; where each catalog word came from, as "
          "second-block offsets (b+N) or first-block ones (@N)" % len(ents))
    for e in ents:
        want = hfscat.DIR if e["kind"] == "dir" else hfscat.FILE
        hit = [r for r in recs if r["kind"] == want
               and r["path"][-len(e["path"]):] == e["path"]]
        name = "/".join(x.decode("mac-roman") for x in e["path"])
        if len(hit) != 1:
            print("  %-4s %-40s %d records" % (e["kind"], name, len(hit)))
            continue
        rec, h, b2 = hit[0]["rec"], e["hdr"], e["b2"]
        spans = ((22, 16), (38, 16)) if want == hfscat.DIR \
            else ((4, 16), (56, 16))
        out = []
        for off, n in spans:
            for k in range(0, n, 2):
                w = rec[off + k:off + k + 2]
                src = [o for o in range(len(h) - 1) if h[o:o + 2] == w] \
                    if any(w) else []
                out.append(w.hex() + ("" if not src else "(%s)" % ",".join(
                    "b+%d" % (o - b2) if o >= b2 else "@%d" % o
                    for o in src[:2])))
        f = hfscat.fields(hit[0])
        print("  %-4s %s\n       info  %s\n       xinfo %s\n       "
              "lock %d bkdat %08x" % (
                  e["kind"], name, " ".join(out[:8]), " ".join(out[8:]),
                  rec[2] & 1 if want == hfscat.FILE else 0, f["bkdat"]))
    return 0


# ------------------------------------------------------------------
# Lining up
# ------------------------------------------------------------------

# (field, offset in the catalog record, size) — hfscat.py's layouts.
FILE_FIELDS = [("fdType", 4, 4), ("fdCreator", 8, 4), ("fdFlags", 12, 2),
               ("fdLocation", 14, 4), ("fdFldr", 18, 2),
               ("fdIconID", 56, 2), ("fdUnused", 58, 6), ("fdScript", 64, 1),
               ("fdXFlags", 65, 1), ("fdComment", 66, 2),
               ("fdPutAway", 68, 4), ("filFlags", 2, 1),
               ("filCrDat", 44, 4), ("filMdDat", 48, 4), ("filBkDat", 52, 4)]
DIR_FIELDS = [("frRect", 22, 8), ("frFlags", 30, 2), ("frLocation", 32, 4),
              ("frView", 36, 2), ("frScroll", 38, 4), ("frOpenChain", 42, 4),
              ("frScript", 46, 1), ("frXFlags", 47, 1), ("frComment", 48, 2),
              ("frPutAway", 50, 4), ("dirFlags", 2, 2),
              ("dirCrDat", 10, 4), ("dirMdDat", 14, 4), ("dirBkDat", 18, 4)]


def swap_halves(v):
    """A Point with v and h exchanged; a Rect with each corner's swapped."""
    return b"".join(v[i + 2:i + 4] + v[i:i + 2] for i in range(0, len(v), 4))


def where(v, hdr, end):
    """Every header place `v` occurs: '@38', '@100~' (halves swapped),
    'E@38' (in the folder's END header)."""
    out = []
    n = len(v)
    for label, h in (("", hdr), ("E", end)):
        if h is None:
            continue
        for o in range(0, len(h) - n + 1):
            if h[o:o + n] == v:
                out.append("%s@%d" % (label, o))
            if n >= 4 and n % 4 == 0 and h[o:o + n] == swap_halves(v) \
                    and swap_halves(v) != v:
                out.append("%s@%d~" % (label, o))
    return out


def load(tags):
    rows = []
    for p in sorted(glob.glob(os.path.join(RESULTS, "*.json"))):
        r = json.load(open(p))
        if tags and r["tag"] not in tags:
            continue
        for a in r["archives"]:
            ends = {}
            for e in a["entries"]:
                if e["kind"] == "end":
                    ends[tuple(e["path"])] = bytes.fromhex(e["hdr"])
            for e in a["entries"]:
                if e["kind"] == "end":
                    continue
                rows.append(dict(
                    ver=bytes.fromhex(a["arch"])[14],
                    depth=len(e["path"]),
                    run=r["tag"], fixture=a["fixture"], writer=a["writer"],
                    kind=e["kind"], name=b"/".join(bytes.fromhex(x) for x in
                                                   e["path"]).decode("mac-roman"),
                    hdr=bytes.fromhex(e["hdr"]),
                    end=ends.get(tuple(e["path"])) if e["kind"] == "dir"
                    else None,
                    rec=bytes.fromhex(e["match"]["rec"]) if "match" in e
                    else None, candidates=e.get("candidates")))
    return rows


def align(rows, fields, kind, show=12):
    """Per field: where in the header its nonzero values occur, which
    place explains the most, and every entry that place does not."""
    rows = [r for r in rows if r["kind"] == kind and r["rec"] is not None]
    print("\n== %s: %d entries matched on the volume" % (kind, len(rows)))
    for fname, off, size in fields:
        tally, nz = {}, 0
        zero = 0
        for r in rows:
            v = r["rec"][off:off + size]
            if not any(v):
                zero += 1
                continue
            nz += 1
            for w in set(where(v, r["hdr"], r["end"])):
                tally[w] = tally.get(w, 0) + 1
        best = sorted(tally.items(), key=lambda kv: -kv[1])[:4]
        print("  %-11s nonzero %4d/%-4d  %s" % (
            fname, nz, len(rows),
            ", ".join("%s %d" % kv for kv in best) or "found nowhere"))
        if not best:
            continue
        top = best[0][0]
        swapped = top.endswith("~")
        src_end = top.startswith("E")
        o = int(top.lstrip("E@").rstrip("~"))
        bad = []
        for r in rows:
            v = r["rec"][off:off + size]
            h = r["end"] if src_end else r["hdr"]
            if h is None:
                continue
            hv = h[o:o + size]
            if swapped:
                hv = swap_halves(hv)
            if hv != v:
                bad.append((r, v, hv))
        print("  %11s %s explains %d of %d; %d exceptions" % (
            "", top, len(rows) - len(bad), len(rows), len(bad)))
        for r, v, hv in bad[:show]:
            print("  %11s   %-34s %-8s wrote %s, header %s" % (
                "", (r["fixture"] + ":" + r["name"])[-34:], r["writer"],
                v.hex(), hv.hex()))
        if len(bad) > show:
            print("  %11s   ... and %d more" % ("", len(bad) - show))


def gates(r):
    """The two things the sentinel boots found Expander 4.0.2 checks:
    the archive's version byte, and whether @34 is the CRC-16/ARC of
    bytes 2..33 (DECISIONS.md 2026-10-17)."""
    h = r["hdr"]
    return dict(v2=r["ver"] >= 2,
                crc=struct.unpack(">H", h[34:36])[0] == crc16_arc(h[2:34]))


# --control: the rules with each measured gate and mask removed, so the
# model check is shown able to fail on the corpus it passes on.
CONTROL = False


def predict(r):
    """What the measured rules say Expander writes, field by field, as
    (catalog offset, bytes)."""
    h, g = r["hdr"], gates(r)
    if CONTROL:
        g = dict(v2=True, crc=True)
    z = lambda n: bytes(n)                                  # noqa: E731
    if r["kind"] == "file":
        # HYPOTHESIS under test: a position is restored only when the
        # name CRC holds and it is not (-1,-1); when it is not, the
        # hasBeenInited bit goes too, so the Finder places the icon.
        placed = g["crc"] and (CONTROL or h[62:66] != b"\xff" * 4)
        fl = struct.unpack(">H", h[74:76])[0] & ~(0 if CONTROL else 0x0001)
        if not placed and not CONTROL:
            fl &= ~0x0100
        return {"fdType": (4, h[66:70]), "fdCreator": (8, h[70:74]),
                "fdFlags": (12, struct.pack(">H", fl)),
                "fdLocation": (14, h[62:66] if placed else z(4)),
                "fdFldr": (18, z(2)), "FXInfo": (56, z(16)),
                # locked: bit 15 of @36, read when the name CRC holds
                # (the synth3 boot, U1..U5)
                "filFlags": (2, b"\x01" if (g["crc"] and h[36] & 0x80)
                             else z(1)),
                "filCrDat": (44, h[76:80]),
                "filMdDat": (48, h[80:84]), "filBkDat": (52, z(4))}
    top = r["depth"] == 1
    fl = struct.unpack(">H", h[74:76])[0] & ~(0 if CONTROL
                                              else FLAG_CLEAR_DIR)
    return {"frRect": (22, h[38:46] if g["crc"] else z(8)),
            "frFlags": (30, struct.pack(">H", fl) if g["v2"] else z(2)),
            "frLocation": (32, b"\xff" * 4 if (top and not CONTROL)
                           or not g["crc"]
                           else h[70:74]),
            "frView": (36, h[68:70] if g["v2"] else z(2)),
            "frScroll": (38, swap_halves(h[100:104]) if g["crc"]
                         else z(4)),
            "DXInfo rest": (42, z(12)), "dirFlags": (2, z(2)),
            "dirCrDat": (10, h[76:80]), "dirMdDat": (14, h[80:84]),
            "dirBkDat": (18, z(4))}


# The folder flag bit Expander does not carry over, 0x0001 — measured on
# the sentinel boots (0x014b -> 0x014a, 0xffff -> 0xfffe); the model
# check re-tests it on every entry.
FLAG_CLEAR_DIR = 0x0001


def model(rows, show=15):
    """Every entry of every archive Expander extracted WHOLE; an archive
    with an entry missing from the volume is a walk Expander abandoned,
    and its survivors say nothing about the fields."""
    broken = {(r["run"], r["fixture"]) for r in rows if r["rec"] is None}
    if broken:
        print("\n(model: %d archive(s) left out, not extracted whole: %s)"
              % (len(broken), ", ".join(sorted(f for _, f in broken))))
    rows = [r for r in rows if (r["run"], r["fixture"]) not in broken]
    print("\n== the measured rules, held against every matched entry")
    for kind in ("file", "dir"):
        sub = [r for r in rows if r["kind"] == kind]
        if not sub:
            continue
        names = list(predict(sub[0]))
        for f in names:
            bad, informative = [], 0
            for r in sub:
                off, want = predict(r)[f]
                got = r["rec"][off:off + len(want)]
                if any(want) or any(got):
                    informative += 1
                if got != want:
                    bad.append((r, got, want))
            print("  %-4s %-11s %4d agree of %-4d (%4d with a nonzero "
                  "side), %d disagree" % (kind, f, len(sub) - len(bad),
                                           len(sub), informative, len(bad)))
            for r, got, want in bad[:show]:
                g = gates(r)
                print("        %-40s %-8s v2=%d crc=%d wrote %s, rule says %s"
                      % ((r["fixture"] + ":" + r["name"])[-40:], r["writer"],
                         g["v2"], g["crc"], got.hex(), want.hex()))
            if len(bad) > show:
                print("        ... and %d more" % (len(bad) - show))


def cmd_report(tags, by_writer):
    rows = load(tags)
    if not rows:
        raise SystemExit("sitmeta: no results in %s" % RESULTS)
    unmatched = [r for r in rows if r["rec"] is None]
    print("sitmeta: %d entries from %d archives; %d not found on the volume"
          % (len(rows), len({(r["run"], r["fixture"]) for r in rows}),
             len(unmatched)))
    for r in unmatched[:20]:
        print("   unmatched: %s:%s (%s candidates)" % (
            r["fixture"], r["name"], r["candidates"]))
    groups = sorted({r["writer"] for r in rows}) if by_writer else [None]
    for g in groups:
        sub = [r for r in rows if g is None or r["writer"] == g]
        if g:
            print("\n######## writer %s" % g)
        align(sub, FILE_FIELDS, "file")
        align(sub, DIR_FIELDS, "dir")
        model(sub)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("archives", nargs="*")
    p.add_argument("--list", action="store_true")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--synth", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--batch", type=int)
    p.add_argument("--family", default="classic", choices=("classic", "sit5"))
    p.add_argument("--report", action="store_true")
    p.add_argument("--sit5", metavar="ARCHIVE",
                   help="Expander 5.5 on Mac OS 9 over a sentinel copy")
    p.add_argument("--info-only", action="store_true",
                   help="with --sit5: sentinels in the FInfo/DInfo half only "
                        "(the full set is refused, -12043)")
    p.add_argument("--location-only", action="store_true",
                   help="with --sit5: sentinels up to b+17 only, so a "
                        "file's fdFldr at b+18 stays real")
    p.add_argument("--files-only", action="store_true",
                   help="with --sit5: leave the folders' blocks real")
    p.add_argument("--plain", action="store_true",
                   help="with --sit5: the archive unmodified (the control)")
    p.add_argument("--writer201", action="store_true",
                   help="StuffIt Deluxe 2.0.1 stuffs a sentinel folder")
    p.add_argument("--by-writer", action="store_true")
    p.add_argument("--control", action="store_true",
                   help="with --report: the rules less every gate and "
                        "mask, which must disagree")
    p.add_argument("--tag", action="append")
    p.add_argument("--emu", default="mv-4M",
                   help="all-out by default: nothing here is timed")
    p.add_argument("--system", default="System6.hfv")
    p.add_argument("--quiet", type=float, default=8.0,
                   help="seconds the screen must hold still after Expand")
    a = p.parse_args()
    if a.list:
        cmd_list(a.archives)
    elif a.plan:
        batches, skipped = plan(family=a.family)
        for i, b in enumerate(batches):
            print("batch %3d: %s" % (i, " ".join(os.path.basename(x)
                                                 for x in b)))
        print("%d batches; %d archives left out:" % (len(batches),
                                                      len(skipped)))
        for s in skipped:
            print("   %s: %s" % s)
    elif a.synth:
        cmd_synth()
    elif a.sit5:
        return sit5_run(a.sit5, guard.run_dir("sitmeta-sit5"), a.plain,
                        18 if a.location_only else 20 if a.info_only
                        else 36, a.files_only)
    elif a.writer201:
        return writer201(a.emu)
    elif a.run or a.batch is not None:
        archives = a.archives
        tag = (a.tag or ["run"])[0]
        if a.batch is not None:
            archives = plan(family=a.family)[0][a.batch]
            tag = ("corpus%03d" if a.family == "classic"
                   else "sit5c%03d") % a.batch
        run_boot(archives, tag, a.emu, a.system, a.quiet)
    elif a.report:
        global CONTROL
        CONTROL = a.control
        cmd_report(a.tag, a.by_writer)
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
