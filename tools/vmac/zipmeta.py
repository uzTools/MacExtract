#!/usr/bin/env python3
"""zipmeta.py — does StuffIt restore a MacZip archive's type and creator?

A Macintosh-written zip carries Finder metadata in an extra field, and
`src/fmt_exo.c` reads two writers' worth of them (FORMATS.md, *Zip's
Macintosh extra fields*). This asks what ALADDIN's software does with the
same bytes, on the installation `spacesaver.py` already builds.

The subject is a four-entry cut of `rexnebular_1_0_0.zip` whose local
headers, `0x334d` fields and compressed data are the ORIGINAL bytes; only
the central-directory offsets are rewritten (`--make`). So this grades
StuffIt against a real MacZip archive rather than one written here.

**The discriminator is `MSWD`.** `checksum.md5` is `TEXT/ttxt` in the
archive, which is also what a Mac defaults a text file to, so it decides
nothing on its own. The three `docs/*.txt` entries are `TEXT/MSWD`, which
no default produces. Either those come back MSWD or StuffIt did not read
the field.

**This driver needs System 7 and will silently do nothing on System
6.** It picks every folder and application by typing its name and
pressing Cmd-O, and Finder type-ahead SELECTION arrived with System 7 —
System 6's Finder has no such feature, so a typed name there selects
nothing and Cmd-O opens nothing. The image `spacesaver.py` builds boots
System 7.0.1, which is why this works; `03-opened-stuffit.png` shows the
Label menu and a `System_7_0_1` volume. Anything retargeted at a System
6 volume must drive the Finder some other way (`tools/vmac/README.md`).
The `Escape` before each name is a SECOND and unrelated guard: on
System 7 a later search in the same boot concatenates onto the
type-ahead buffer and matches nothing unless the buffer is cleared.

**What this CANNOT see.** It grades ONE StuffIt — Expander 3.5.2 over
StuffIt Engine 3.5.2 and UnZip Translator 3.5, the installation
`spacesaver.py` builds and the only one here. 3.5.1 is from 1994 and Info-ZIP's `0x334d` carries
"Last Revision 19981005" in its own specification, so a negative result
here is a fact about a version that predates the field and NOT about
StuffIt in general. **`sitzip.py` is where the later boxes are**: 5.5
and 7.0.3 were assembled into a Mac OS 9 System Folder and run on
2026-10-04, and both fail the field too; 6.0.1 is still an uninstalled
installer. It also cannot distinguish "read the
field and ignored it" from "never looked": both leave the same volume.
What it CAN do is name the mechanism, because the translator's own
`E2Ty` resource is a filename-extension table and `--table` prints it
without booting anything.

    tools/vmac/zipmeta.py --make      cut the subject out of the archive
    tools/vmac/zipmeta.py --table     the translator's extension table
    tools/vmac/zipmeta.py --expander  hand it to StuffIt Expander, read back
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arcmac import macbinary                              # noqa: E402
from diskdoubler import Session                            # noqa: E402
from spacesaver import INSTALLED, SPECIMENS, WORK, resources, SIT_FOLDER  # noqa: E402
from spacesaver import SPECIAL_X, SHUT_DOWN_Y              # noqa: E402
from superdisk import read_forks                           # noqa: E402

SUBJECT = os.path.join(WORK, "rex-tiny.zip")
KEEP = [b"checksum.md5", b"docs/rex_codes.txt",
        b"docs/rex_codes_dos.txt", b"docs/rex_bonus_notes.txt"]
# What the archive itself says, off its 0x334d fields; `lsar` agrees on
# all four and so does our own CLI (FORMATS.md).
EXPECT = {
    "checksum.md5":          ("TEXT", "ttxt"),
    "rex_codes.txt":         ("TEXT", "MSWD"),
    "rex_codes_dos.txt":     ("TEXT", "MSWD"),
    "rex_bonus_notes.txt":   ("TEXT", "MSWD"),
}


def make(src):
    """Cut four entries out of the real archive, bytes intact."""
    d = open(src, "rb").read()
    i = d.rfind(b"PK\x05\x06")
    cnt, = struct.unpack_from("<H", d, i + 10)
    cdof, = struct.unpack_from("<I", d, i + 16)
    recs = {}
    p = cdof
    for _ in range(cnt):
        nl, el, kl = struct.unpack_from("<HHH", d, p + 28)
        lh, = struct.unpack_from("<I", d, p + 42)
        csz, = struct.unpack_from("<I", d, p + 20)
        name = d[p + 46:p + 46 + nl]
        lnl, lel = struct.unpack_from("<HH", d, lh + 26)
        if name in KEEP:
            recs[name] = (d[p:p + 46 + nl + el + kl],
                          d[lh:lh + 30 + lnl + lel + csz])
        p += 46 + nl + el + kl
    missing = [n for n in KEEP if n not in recs]
    if missing:
        raise SystemExit("zipmeta: not in %s: %s" % (src, missing))
    out = b""
    cd = b""
    for name in KEEP:
        cdrec, lblob = recs[name]
        off = len(out)
        out += lblob
        r = bytearray(cdrec)
        struct.pack_into("<I", r, 42, off)   # the ONLY byte changed
        cd += bytes(r)
    eocd = struct.pack("<IHHHHIIH", 0x06054b50, 0, 0, len(KEEP), len(KEEP),
                       len(cd), len(out), 0)
    os.makedirs(WORK, exist_ok=True)
    open(SUBJECT, "wb").write(out + cd + eocd)
    print("zipmeta: wrote %s (%d entries, %d B)"
          % (SUBJECT, len(KEEP), len(out + cd + eocd)))


def table():
    """The UnZip Translator's `E2Ty` — no emulator.

    This is the whole answer to HOW it assigns type and creator, and it
    is an extension table with no reference to any extra field.
    """
    if not os.path.exists(INSTALLED):
        raise SystemExit("zipmeta: no installed image — spacesaver.py --keep-installed")
    forks = read_forks(INSTALLED)
    tr = None
    for path, (ftype, creator, _d, rsrc) in forks.items():
        if path[-1] == "UnZip Translator":
            tr = (ftype, creator, rsrc)
    if not tr:
        raise SystemExit("zipmeta: no UnZip Translator on %s" % INSTALLED)
    ftype, creator, rsrc = tr
    res = resources(rsrc)
    nm = bytes(res["Name"][0][1])
    ver = bytes(res["vers"][1][1])
    print("UnZip Translator  %s/%s  %d B" % (ftype, creator, len(rsrc)))
    print("  'Name' 0: %r" % nm[1:1 + nm[0]].decode("mac-roman"))
    print("  'vers' 1: %r" % ver[6:].decode("mac-roman", "replace"))
    e2 = bytes(res["E2Ty"][0][1])
    n, = struct.unpack(">H", e2[:2])
    print("  'E2Ty' 0: %d bytes, count field %d" % (len(e2), n))
    # Sixteen bytes a row: a length byte, the extension in a FIXED
    # four-byte field zero-padded, a pad byte, type, creator, and a
    # two-byte flag. 2 + 19 * 16 = 306, which is the whole resource, so
    # the shape is checked by the arithmetic and not assumed.
    rows = []
    for p in range(2, len(e2) - 15, 16):
        ln = e2[p]
        ext = e2[p + 1:p + 1 + ln].decode("mac-roman")
        rows.append((ext, e2[p + 6:p + 10].decode("mac-roman"),
                     e2[p + 10:p + 14].decode("mac-roman")))
    for ext, t, c in rows:
        print("    %-6s -> %s/%s" % (ext, t, c))
    print("  %d row(s), and 2 + %d * 16 = %d of %d bytes"
          % (len(rows), len(rows), 2 + len(rows) * 16, len(e2)))
    rows = len(rows)
    for sid in (131, 260):
        if sid in res["STR#"]:
            print("  'STR#' %d: %r"
                  % (sid, bytes(res["STR#"][sid][1])[:120]))
    print("\nNO extra-field id appears in this translator: 0x334d x%d, "
          "'ZPIT' x%d, 0x2705 x%d"
          % (rsrc.count(struct.pack(">H", 0x334d)), rsrc.count(b"ZPIT"),
             rsrc.count(struct.pack(">H", 0x2705))))
    return rows


def report(volume, shots):
    """Read the volume back and compare against the archive's own fields."""
    forks = read_forks(volume)
    print("\nzipmeta: reading back %s" % volume)
    seen = {}
    for path, (ftype, creator, data, rsrc) in forks.items():
        leaf = path[-1]
        if leaf in EXPECT:
            seen[leaf] = (ftype, creator, len(data or b""), len(rsrc or b""))
    if not seen:
        print("  NOTHING extracted — the run says nothing about the field.")
        print("  (shots in %s)" % shots)
        return 2
    agree = differ = 0
    print("  %-22s %-11s %-11s" % ("entry", "archive", "on the Mac"))
    for leaf, (et, ec) in EXPECT.items():
        if leaf not in seen:
            print("  %-22s %s/%-6s  (not extracted)" % (leaf, et, ec))
            continue
        ft, cr, dn, rn = seen[leaf]
        ok = (ft, cr) == (et, ec)
        agree += ok
        differ += not ok
        print("  %-22s %s/%-6s %s/%-6s %s  d=%d r=%d"
              % (leaf, et, ec, ft, cr, "agree" if ok else "DIFFERS", dn, rn))
    print("\n  %d agree, %d differ" % (agree, differ))
    if differ and seen.get("rex_codes.txt", ("", ""))[1] == "ttxt":
        print("  The MSWD entries came back ttxt, which is 'E2Ty' row "
              "'.TXT' -> TEXT/ttxt: assigned from the NAME, not read from "
              "the archive (--table).")
    return 0 if differ or agree else 2


def expander(keep=False):
    """Hand the subject to StuffIt Expander 3.5.2 and read the volume back."""
    import glob
    if not os.path.exists(INSTALLED):
        raise SystemExit("zipmeta: no installed image")
    if not os.path.exists(SUBJECT):
        raise SystemExit("zipmeta: no subject — --make first")
    boot = os.path.join(WORK, "zipmeta.hfv")
    shutil.copyfile(INSTALLED, boot)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="hfs-"))
    tmp = tempfile.mkdtemp(prefix="zipmeta-")
    dest = b":" + SIT_FOLDER + b":Drag & Drop Applications:"
    try:
        subprocess.run(["hmount", boot], check=True, capture_output=True,
                       env=env)
        q = os.path.join(tmp, "subject.bin")
        # 'ZIP '/'SITx' is what Aladdin's own software stamps a zip with;
        # the Expand dialog filters on the NAME ending in .zip ('STR#'
        # 260), so the name is what has to be right.
        open(q, "wb").write(macbinary("Rex.zip", "ZIP ", "SITx",
                                      open(SUBJECT, "rb").read()))
        subprocess.run([b"hcopy", b"-m", q.encode(), dest], check=True,
                       capture_output=True, env=env)
        subprocess.run(["humount"], check=True, capture_output=True, env=env)
    finally:
        shutil.rmtree(env["HOME"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    before = set(glob.glob("/tmp/dd-*/boot.hfv"))
    shots = os.path.join(SPECIMENS, "zipmeta")
    s = Session(boot, [], shots)
    try:
        s.boot()
        s.shot("desktop", wait=14.0)
        s.mac.click(250, 38)
        time.sleep(2.5)
        for _ in range(6):
            s.mac.command_key("w")
            time.sleep(2.0)
        s.mac.click(470, 55, double=True)
        s.shot("bootvol", wait=14.0)
        for pick in ("StuffIt D", "Drag"):
            s.mac.key("Escape")
            time.sleep(0.6)
            s.mac._xdo("type", "--delay", "120", pick)
            time.sleep(1.5)
            s.mac.command_key("o")
            s.shot("opened-" + pick.split()[0].lower(), wait=14.0)
        s.mac.key("Escape")
        time.sleep(0.6)
        s.mac._xdo("type", "--delay", "120", "StuffIt E")
        time.sleep(1.5)
        s.mac.command_key("o")
        s.shot("launched", wait=45.0)
        s.mac.command_key("e")
        s.shot("dialog", wait=10.0)
        s.mac._xdo("type", "--delay", "120", "Rex")
        time.sleep(1.5)
        s.shot("typed", wait=0.5)
        s.mac.key("Return")
        s.shot("started", wait=10.0)
        s.shot("settled", wait=30.0)
        s.mac.key("Return")
        s.shot("after", wait=8.0)
        s.mac.command_key("q")
        s.shot("quit", wait=25.0)
        s.menu(SPECIAL_X, SHUT_DOWN_Y, "special-menu")
        s.shot("shutting-down", wait=30.0)
    finally:
        time.sleep(8)
        s.close()

    cands = [p for p in glob.glob("/tmp/dd-*/boot.hfv") if p not in before]
    if not cands:
        cands = sorted(glob.glob("/tmp/dd-*/boot.hfv"),
                       key=os.path.getmtime)[-1:]
    out = sorted(cands, key=os.path.getmtime)[-1]
    if keep:
        shutil.copyfile(out, os.path.join(WORK, "zipmeta-run.hfv"))
    return report(out, shots)


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--make" in a:
        i = a.index("--make")
        src = a[i + 1] if len(a) > i + 1 and not a[i + 1].startswith("-") \
            else "/tmp/rex/rexnebular_1_0_0.zip"
        make(src)
    elif "--table" in a:
        table()
    elif "--expander" in a:
        sys.exit(expander(keep="--keep" in a))
    else:
        print(__doc__)
