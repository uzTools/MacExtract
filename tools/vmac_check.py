#!/usr/bin/env python3
"""vmac_check.py <manifest.json> <macscreen.png>
   vmac_check.py --fixture <archive> <macscreen.png>

Verify one Mini vMac autotest run. Decodes the on-screen result grid
(tools/decode_grid.py) and compares its aggregate to what the oracle says the
extraction should produce:

  nfiles         count of non-directory entries
  ret == 0       (UNC_OK) and errors == 0
  sumDataCRC     sum mod 2^32 of each data fork's CRC-32
  totalDataLen   sum of data-fork lengths
  sumRsrcCRC     sum of each resource fork's CRC-32 with bytes 16..127 — the
                 112-byte "reserved for system use" area of the resource file
                 header — masked to 0; see mask_reserved() below for why that
                 is safe and what is deliberately NOT masked
  totalRsrcLen   sum of resource-fork lengths

Prints PASS/FAIL and the engine's on-Mac peak heap use. Exit 0 iff PASS.
"""
import sys, os, zlib, json, struct, subprocess, tempfile, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_grid import decode

# The reference is the SAME engine's Linux CLI, single-level (`-nr`): the
# AUTOTEST build calls RunExtract once and has no auto-unwrap loop, so `-nr`
# reproduces its exact output. The shipped application does unwrap chains, and
# nothing here can see that — `interactive.py --chain` is what tests it. The CLI output is itself verified byte-exact against the
# committed oracle manifests by the main differential suite.
CLI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "build", "rel", "macextract")


def crc(b):
    return zlib.crc32(b) & 0xFFFFFFFF


# ---- the resource-fork reserved-header mask ------------------------------
#
# A resource fork begins with a 256-byte resource FILE header (Inside
# Macintosh: More Macintosh Toolbox, Resource Manager, "Resource file
# format"), laid out as:
#
#     offset  size  content
#     0       4     offset from start of fork to the resource DATA
#     4       4     offset from start of fork to the resource MAP
#     8       4     length of the resource data
#     12      4     length of the resource map
#     16      112   reserved for SYSTEM use      <-- masked
#     128     128   reserved for APPLICATION use
#
# Only the 112-byte system area is masked. The System 6 Resource Manager
# stamps that region with machine/session scratch when it touches the file,
# and nothing off-Mac reproduces it, so an unmasked CRC would make every
# resource fork mismatch spuriously. Nothing in the fork ever points into it:
# resources are reached exclusively through the four offsets in bytes 0..15
# and the map, so zeroing it cannot hide a difference in any actual resource.
#
# The 128-byte application area at 128..255 is deliberately NOT masked — it
# carries real content (e.g. THINK C writes its copyright notice there) and
# must still compare byte-exact.
RSRC_SYS_RESERVED = (16, 128)          # [start, end) — 112 bytes


def mask_reserved(rsrc):
    """Zero the resource fork's system-reserved header bytes 16..127.

    Refuses to mask anything that is not provably header padding: if the
    fork's own dataOffset/mapOffset say a resource starts inside the range
    we are about to zero, the layout is not the standard one and masking
    could hide a real mismatch, so the fork is returned untouched and the
    comparison is left to fail loudly.
    """
    lo, hi = RSRC_SYS_RESERVED
    if len(rsrc) < 16:
        return rsrc                      # too short to have a header at all
    data_off, map_off = struct.unpack(">II", rsrc[:8])
    # Both regions must start at or after the end of the masked range for the
    # mask to be pure padding. A standard fork has data_off == 256.
    if data_off < hi or map_off < hi:
        return rsrc
    b = bytearray(rsrc)
    for i in range(lo, min(hi, len(b))):
        b[i] = 0
    return bytes(b)


# ---- the name a Macintosh writes, given the name the CLI wrote -----------
#
# Three harnesses compare a NAME off a Mac volume against the CLI's output
# (vmac/checkdisk.py, vmac/interactive.py, vmac/os9.py) and all three need
# the same mapping, so it lives here with the other arithmetic the tiers
# have to agree on. Two things happen to a name between the two hosts, both
# in mac/macextract_mac.c:
#
#   Utf8ToMacRoman      a StuffIt 5 name is UTF-8 (UncEntryInfo.name_utf8)
#                       and an HFS name is MacRoman bytes, so the shell
#                       folds the whole path once, at the door of
#                       sink_begin, and a code point MacRoman has no byte
#                       for becomes '_'. Every other format states MacRoman
#                       already and is not folded at all — which is why
#                       this is not applied unconditionally: a zip name
#                       holding a character MacRoman lacks reaches the disk
#                       as its own bytes, and folding it here would invent
#                       an agreement.
#   ComponentToStr63    each component is then fitted to HFS's 31
#                       characters WITH ITS EXTENSION KEPT, and an empty
#                       one becomes '_'.
#
# Until 2026-09-22 the three sites did `c.replace(":", "/")[:31]`, which is
# neither of those: it cut the extension off and knew nothing of the fold.


def ext_start(name):
    """Offset of the last '.' introducing a 1..4 character alphanumeric
    extension, or -1. ExtStart() in mac/macextract_mac.c."""
    for i in range(len(name) - 1, 0, -1):
        if name[i] != ".":
            continue
        tail = name[i + 1:]
        if not 1 <= len(tail) <= 4:
            return -1
        return i if all(c.isascii() and c.isalnum() for c in tail) else -1
    return -1


def fold_macroman(s):
    """UTF-8 -> the characters a MacRoman byte can spell, '_' for the rest.

    Python's `mac_roman` codec is Apple's table and agrees with the shell's
    kMacRomanHigh[] at all 128 high bytes (checked).

    **Operate on the name BEFORE any Unicode normalization**, because the
    shell folds the archive's own bytes and those are DECOMPOSED. Measured
    2026-09-22 on `derived-800saywhat301j.sit`, whose
    `ユーザーライセンスの購入.rtf` is 13 code points and not 12: `ザ` is
    stored as `サ` + U+3099, both of which MacRoman lacks, so the Macintosh
    writes 13 '_' and an NFC fold would predict 12. The oracle manifests
    hold NFC — `lsar` composes — which is invisible to `run_diff.py`
    because it normalizes both sides, and was invisible here until a
    fixture with such a name reached a Mac.
    """
    out = []
    for ch in s:
        try:
            ch.encode("mac_roman")
        except UnicodeEncodeError:
            out.append("_")
        else:
            out.append(ch)
    return "".join(out)


def mac_component(c, utf8=False):
    """One CLI path component as the Macintosh shell writes it.

    `utf8` says the format states its names in UTF-8 — i.e. the engine set
    `name_utf8` and the shell folded. `names_are_utf8()` below answers it
    for a fixture.
    """
    if utf8:
        c = fold_macroman(c)
    c = c.replace(":", "/")             # the engine's reversible swap, undone
    if len(c) > 31:
        ext = ext_start(c)
        if ext > 0 and 31 - (len(c) - ext) >= 1:
            c = c[:31 - (len(c) - ext)] + c[ext:]
        else:
            c = c[:31]
    return c or "_"


def names_are_utf8(fixture, cli=None):
    """Does this fixture's format state its names in UTF-8?

    Asked of the engine rather than kept as a list here, so the two cannot
    drift: `fmt_sit5.c` is the only file that sets the flag. The format is
    the OUTER one, which is what the autotest build walks — it calls
    RunExtract once and unwraps no envelope. A segmented StuffIt 5 set
    sniffs as a split and is not covered; none is in any Mac list.
    """
    cli = cli or CLI
    r = subprocess.run([cli, "sniff", fixture], capture_output=True, text=True)
    return r.stdout.strip() == "StuffIt 5"


def aggregate_dir(root_dir, names=None):
    """(nfiles, sumDataCRC, totalDataLen, sumRsrcCRC, totalRsrcLen) for a tree
    of CLI output, extracted with `--forks hidden`.

    Split out of expected_aggregate() so the Mac OS 9 harness can use the same
    arithmetic on its own reference directory — the two tiers must agree on
    what "the expected aggregate" means, and having it in one place is the only
    way that stays true. `names`, if given, is a list the leaf filenames are
    appended to, for harnesses that also compare names.

    The "._<X>" sidecar namespace is disjoint from archive names, so a file
    either IS a sidecar or is not, with nothing to infer. This used to read
    "<X>.rsrc" sidecars and guess: a "<X>.rsrc" was a sidecar only when <X>
    existed beside it, otherwise a real entry of that name. That guess is
    wrong for the archives where BOTH are real — the THINK C projects
    recovered on 2026-08-08 — which is why every caller now passes
    `--forks hidden`. On a Mac there is no ambiguity to begin with: HFS
    forks are part of the file, so this only ever described how the HOST
    stages a comparison. DECISIONS.md, 2026-08-08."""
    nfiles = sdc = sdl = src = srl = 0
    for root, _d, files in os.walk(root_dir):
        for f in files:
            if f.startswith("._"):
                continue                 # sidecar; counted with its data file
            p = os.path.join(root, f)
            data = open(p, "rb").read()
            nfiles += 1
            if names is not None:
                names.append(f)
            sdc = (sdc + crc(data)) & 0xFFFFFFFF
            sdl += len(data)
            rp = os.path.join(root, "._" + f)
            rsrc = open(rp, "rb").read() if os.path.exists(rp) else b""
            src = (src + crc(mask_reserved(rsrc))) & 0xFFFFFFFF
            srl += len(rsrc)
    return nfiles, sdc, sdl, src, srl


def expected_from_fixture(fixture):
    # The reference build is what `./ci.sh` deletes first (`make clean`),
    # and losing it here used to surface as sixty lines of traceback from
    # subprocess. Say it in one line instead — the answer is always the
    # same, and `tools/vmac/README.md` already warns not to run these
    # alongside CI.
    if not os.path.exists(CLI):
        sys.exit("vmac_check: no reference build at %s — `make` it (and do "
                 "not run this while ./ci.sh is running: its `make clean` "
                 "takes that binary away)" % os.path.normpath(CLI))
    tmp = tempfile.mkdtemp()
    try:
        subprocess.run([CLI, "x", "-nr", "--forks", "hidden", fixture,
                        "-o", tmp],
                       capture_output=True, timeout=180)
        return aggregate_dir(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def expected_aggregate(manifest_path):
    man = json.load(open(manifest_path))
    fixture = os.path.join(os.path.dirname(manifest_path), "..", man["fixture"])
    return expected_from_fixture(fixture)


def main():
    # Two ways to say what to compare against, and they differ in ONE
    # thing: whether a committed oracle manifest exists for the file.
    #
    #   <manifest.json> <png>       the fixture the manifest names
    #   --fixture <path> <png>      any file, graded the same way
    #
    # Both grade the Mac against this engine's own Linux output, which
    # is what the aggregate on screen can be compared with at all — the
    # manifest only ever located the fixture. The difference is what
    # adjudicates the LINUX side: for a fixture with a manifest, the
    # differential suite does, entry by entry; for a file passed with
    # --fixture, whatever suite grades that format does (run_superdisk.py,
    # run_arc.py). Never nothing — and the line printed below says which,
    # so a run cannot look better than it is (TESTING.md).
    argv = sys.argv[1:]
    if len(argv) == 3 and argv[0] == "--fixture":
        manifest, fixture, png = None, argv[1], argv[2]
    elif len(argv) == 2:
        manifest, png = argv[0], argv[1]
        fixture = None
    else:
        print(__doc__.strip())
        return 2
    got = decode(png)
    if got is None:
        print("FAIL: no valid result grid on screen (app bombed or miscalibrated)")
        return 1
    nfiles, ret, errors, sdc, sdl, src, srl, peak = got
    ret_s = ret - (1 << 32) if ret >= (1 << 31) else ret   # signed
    if manifest:
        enf, esdc, esdl, esrc, esrl = expected_aggregate(manifest)
    else:
        enf, esdc, esdl, esrc, esrl = expected_from_fixture(fixture)
        print(f"  reference: this engine's Linux CLI on "
              f"{os.path.basename(fixture)} — no oracle manifest, so the "
              f"Linux side is adjudicated by its own suite, not here")

    # A file the engine does not recognise, or cannot extract, yields 0 files from the
    # SAME engine's Linux CLI. Then the only correct behaviour on the Mac is to
    # also extract nothing — consistent refusal, not a byte match.
    if enf == 0:
        ok = (nfiles == 0)
        tag = "PASS" if ok else "FAIL"
        print(f"{tag} (unsupported by engine): Mac nfiles={nfiles} ret={ret_s}, "
              f"CLI nfiles=0; peak {peak/1024.0:.1f} KB")
        return 0 if ok else 1

    checks = [
        ("nfiles", nfiles, enf),
        ("ret==0", ret, 0),
        ("errors==0", errors, 0),
        ("sumDataCRC", sdc, esdc),
        ("totalDataLen", sdl, esdl),
        ("sumRsrcCRC", src, esrc),
        ("totalRsrcLen", srl, esrl),
    ]
    ok = True
    for name, g, e in checks:
        good = (g == e)
        ok = ok and good
        if not good:
            print(f"  {name:14s} got {g} (0x{g:08X}) want {e} (0x{e:08X})  MISMATCH")
    tag = "PASS" if ok else "FAIL"
    print(f"{tag}: {nfiles} file(s), peak heap {peak} B "
          f"({peak/1024.0:.1f} KB), data {sdl} B, rsrc {srl} B")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
