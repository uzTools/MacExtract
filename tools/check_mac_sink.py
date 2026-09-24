#!/usr/bin/env python3
"""check_mac_sink.py <manifest.json> <outdir> [fixture]

Compare the Mac-sink test's output tree against an oracle manifest,
byte-for-byte (data fork + "._" sidecar). Used by tests/run_mac_sink.sh.

The mock File Manager writes resource forks as "._<name>" beside the data
file, because on HFS a fork belongs to the file and an archive holding both
"X" and "X.rsrc" has two unrelated files — a ".rsrc" suffix would invent a
collision the Mac does not have. DECISIONS.md, 2026-08-08.

`fixture` is what the shell was given, and it is needed for one thing: to
ask the engine whether this format states its names in UTF-8, so that the
manifest's name can be put through the same fold the shell applied
(vmac_check.names_are_utf8, which asks the ENGINE rather than keeping a
list of formats that could drift from it). Omitting it predicts no fold,
which is right for every format but StuffIt 5 and reports three names
MISSING for that one — so run_mac_sink.sh always passes it.
"""
import hashlib, json, os, sys, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vmac_check import mac_component, names_are_utf8      # noqa: E402


def norm(p):
    n = unicodedata.normalize("NFC", p)
    return n.replace(":", "_").replace("/", "_")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


def normpath(p):
    return "/".join(norm(c) for c in p.split("/"))


def macpath(p, utf8):
    """The manifest's name, as the Mac shell writes it.

    vmac_check.mac_component() is the same arithmetic the three emulator
    harnesses use: Utf8ToMacRoman where the engine set `name_utf8`, then
    ComponentToStr63's 31-character cut with the extension kept.

    **The fold runs on the DECOMPOSED spelling**, because the shell folds
    the archive's own bytes and this manifest holds the oracle's: `unar -e
    utf-8` composes. Measured over all 31 StuffIt 5 fixtures on
    2026-09-22 — 27 non-ASCII entry names, and both of the two where NFC
    and NFD differ are stored decomposed, so decomposing recovers what
    the archive states. A composed non-ASCII name would fail here rather
    than pass quietly, which is the point: `ユーザーライセンスの購入.rtf`
    is 13 code points in the archive and 12 in the manifest, so the
    Macintosh writes one more '_' than a composed fold predicts
    (DECISIONS.md 2026-09-22, *the fold, on a Macintosh*).
    """
    if utf8:
        p = unicodedata.normalize("NFD", p)
    return "/".join(norm(mac_component(c, utf8)) for c in p.split("/"))


def resolve_cli():
    """A CLI to ask about the format. `build/rel` does not exist when
    ci.sh reaches this suite — `make clean` took it and the release
    build comes later — so the sanitizer build is what is normally
    found."""
    if os.environ.get("MACEXTRACT"):
        return os.environ["MACEXTRACT"]
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for b in ("san", "rel", ""):
        p = os.path.join(repo, "build", b, "macextract")
        if os.path.exists(p):
            return p
    return None


def main():
    man = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    fixture = sys.argv[3] if len(sys.argv) > 3 else None
    utf8 = False
    if fixture:
        cli = resolve_cli()
        if not cli:
            print("  no macextract build to ask about the name encoding; "
                  "build one (make) before running this")
            return 1
        utf8 = names_are_utf8(fixture, cli)
    # The mock reproduces the folder tree; index produced files by
    # normalized relative path (matching the manifest entry names).
    # The names on disk are the engine's RAW MacRoman bytes, which is what
    # a Mac writes; the manifest's are UTF-8. Decoding here is what lets an
    # 8-bit name (`UnZip.π`) be compared at all — until 2026-08-08 every
    # fixture in this harness's list was pure ASCII, so nothing said so.
    produced = {}
    for root, _dirs, files in os.walk(out):
        # Folder names are MacRoman on disk too ("BootTime ƒ"), so the whole
        # relative path is decoded, not just the leaf.
        rel = os.fsencode(os.path.relpath(root, out)).decode("mac_roman")
        for f in files:
            leaf = os.fsencode(f).decode("mac_roman")
            p = normpath(os.path.normpath(os.path.join(rel, leaf)))
            produced[p] = os.path.join(root, f)
    bad = 0
    # The archive's own comment: the Mac shell writes it beside the
    # extracted items as a "Comments" document, so the oracle's
    # XADComment is compared against that file's bytes — which are
    # MacRoman, because that is what a Mac writes.
    want = man.get("comment")
    if want is not None:
        p = produced.pop("Comments", None)
        if not p:
            print("  MISSING archive comment file 'Comments'")
            bad += 1
        else:
            got = open(p, "rb").read()
            if got != want.encode("mac_roman"):
                print(f"  MISMATCH archive comment {got!r}")
                bad += 1
    for e in man["entries"]:
        if e.get("is_dir"):
            continue
        name = macpath(e["name"], utf8)
        p = produced.get(name)
        # An entry with an empty data fork still gets a file, so presence is
        # checked whatever the size: a missing empty file is a real defect
        # and a size-gated check cannot see it.
        if not p:
            print(f"  MISSING {name!r}")
            bad += 1
        elif e["data_size"] and sha(p) != e["data_sha256"]:
            print(f"  MISMATCH data {name!r}")
            bad += 1
        if e["rsrc_size"]:
            head, _, tail = name.rpartition("/")
            p = produced.get(f"{head}/._{tail}" if head else f"._{tail}")
            if not p or sha(p) != e["rsrc_sha256"]:
                print(f"  MISMATCH rsrc {name!r}")
                bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
