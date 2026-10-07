#!/usr/bin/env python3
"""checkdisk.py — verify a Mini vMac run by READING ITS OUT VOLUME.

BLOCKERS.md has said since M10 that this cannot be done:

    Mini vMac's disk write-back to the host image is lazy and PARTIAL — it
    can commit one fork of a file but not the other — so results cannot be
    read off the Out volume. Verification is done ON-SCREEN instead.

That claim dates from the confounded period and had no reproduction. It
matters because of what the on-screen channel cannot do: the grid carries a
file COUNT, two summed CRC-32s and two summed lengths, and a summed CRC
cannot carry a name. So the System 6 and 7 tiers have never compared an
output NAME and cannot be made to fail on one — which is exactly how a real
defect in the gzip/.Z fallback name survived in the corpus for weeks until
the Mac OS 9 harness, which reads its volume, caught it on its first sweep.

    tools/vmac/run.py --keep-disks --list tools/vmac/sample.txt
    tools/vmac/checkdisk.py /tmp/vmacrun-*/

Each directory must hold the `out.dsk` of a finished run. The fixture is
identified from the `in.dsk` beside it, so no bookkeeping is needed.

Compares, per file, against `macextract x -nr`: both forks byte for byte
(resource forks through the same reserved-header mask vmac_check.py uses),
the type/creator, and — the point — the set of NAMES, recursively.
"""
import os, subprocess, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import os9                                                   # noqa: E402
from vmac_check import (mask_reserved, aggregate_dir,         # noqa: E402
                        mac_component, names_are_utf8)

CLI = os.path.join(REPO, "build", "rel", "macextract")


def hfs(env, *argv):
    return subprocess.run(argv, capture_output=True, env=env)


class TooDeep(Exception):
    """The volume walk went deeper than the engine can write."""


def walk(env, mac_dir=(), depth=0, dirs=False):
    """Every file on the mounted volume, as tuples of MacRoman components.

    With `dirs`, every FOLDER too. Off by default, because the comparison
    this file makes is against a Linux extraction's files; a caller that
    needs to assert a folder was NOT created has to ask for them, and one
    that forgets gets a set no folder can ever be in — which is an
    assertion that cannot fail (CLAUDE.md).

    Components, not a joined string: '/' is a legal character in an HFS
    filename (`mw/68k•unshar π` in derived-unshar_1.11_folder.sit) and ':'
    is the separator, so joining on either loses the difference between a
    name and a path. Found on 2026-08-08, when that fixture joined the
    sample and two of its entries could not be copied off the volume.
    """
    # The engine carries UNC_PATH_MAXDEPTH (24) levels of folder and refuses
    # to descend past them (src/unc_internal.h), so no volume this
    # application wrote can nest deeper than 25 components. This guard is
    # here to stop a CYCLE, not to bound a tree, so exceeding it raises
    # rather than returning what it has: it was `depth > 8: return []` until
    # 2026-10-07, which reported a correct 24-deep volume as 32 files
    # MISSING ON THE MAC — a harness limit that reads exactly like an
    # application defect, and silent because nothing in the sample nests
    # past 6 (BLOCKERS.md, FORMATS.md *How deep anything actually nests*).
    if depth > 26:
        raise TooDeep("the volume nests past %d components, which the engine "
                      "cannot write — a loop, or a harness bug" % depth)
    out = []
    # -a because hfsutils hides a file whose Finder INVISIBLE bit is set —
    # NOT, as this comment said until 2026-09-22, names beginning with a dot.
    # Measured as a 2x2 (`walkprobe.py`): a dotted name with the bit clear is
    # listed without -a and one with the bit set is hidden, dot or no dot.
    # `.DS_Store` needed the flag because a Macintosh writes it invisible.
    # The wrong reason mattered: four later walks whose subjects had no
    # dotfiles skipped the flag and looked safe (OPEN_ITEMS.md).
    # The path goes out as MacRoman bytes because
    # that is what the names on the volume are — passing a Python str makes
    # subprocess encode UTF-8 and any 8-bit name (`spinning brain ƒ`) becomes
    # a directory that does not exist.
    arg = [mac_path(mac_dir, True).encode("mac_roman", "replace")] \
        if mac_dir else []
    listing = hfs(env, "hls", "-a", "-F", "-1", *arg)
    for raw in listing.stdout.split(b"\n"):
        # NOT rstrip(): a carriage return is a legal HFS filename character
        # and `Icon\r` is what every custom folder icon on a Mac is called,
        # so stripping trailing whitespace renamed it to `Icon` and the
        # comparison then failed on a file that was present and correct.
        # `hls -1` terminates each line with \n and adds nothing else, so
        # splitting on \n has already removed everything that is not name.
        entry = raw.decode("mac_roman")
        if not entry:
            continue
        isdir = entry.endswith(":")
        name = entry[:-1] if isdir or entry.endswith("*") else entry
        rel = mac_dir + (unicodedata.normalize("NFC", name),)
        if isdir:
            if dirs:
                out.append(rel)
            out += walk(env, rel, depth + 1, dirs)
        else:
            out.append(rel)
    return out


def mac_path(comps, folder=False):
    """A tuple of components as an absolute Mac path, ':'-separated."""
    return ":" + ":".join(comps) + (":" if folder else "")


def fixture_of(indsk, env, candidates=None):
    """Which fixture was this run? The In volume holds it as `archive.sit`.

    `candidates` are extra paths to match before `fixtures/` — a GENERATED
    subject is in no committed directory, so without them a run over one
    skips, which is what every `tools/synth_*.py` archive did here until
    2026-10-07. The match is still by CONTENT: naming a file that is not
    the one on the disk identifies nothing.
    """
    if hfs(env, "hmount", indsk).returncode != 0:
        return None
    got = hfs(env, "hcopy", "-r", "archive.sit", "/tmp/.checkdisk-archive").returncode
    hfs(env, "humount")
    if got != 0:
        return None
    want = open("/tmp/.checkdisk-archive", "rb").read()
    pool = list(candidates or [])
    fixdir = os.path.join(REPO, "fixtures")
    pool += [os.path.join(fixdir, f) for f in os.listdir(fixdir)]
    for p in pool:
        if os.path.isfile(p) and os.path.getsize(p) == len(want):
            if open(p, "rb").read() == want:
                return p
    return None


def check(rundir, candidates=None):
    workhome = os.path.join(rundir, ".hfshome")
    os.makedirs(workhome, exist_ok=True)
    env = dict(os.environ, HOME=workhome)
    outdsk = os.path.join(rundir, "out.dsk")
    indsk = os.path.join(rundir, "in.dsk")
    if not (os.path.exists(outdsk) and os.path.exists(indsk)):
        return None, f"{rundir}: no out.dsk/in.dsk"

    fixture = fixture_of(indsk, env, candidates)
    if fixture is None:
        return None, f"{rundir}: cannot identify the fixture from in.dsk"
    name = os.path.basename(fixture)

    if hfs(env, "hmount", outdsk).returncode != 0:
        return False, f"{name}: the Out volume will not mount"
    try:
        names = walk(env)
    except TooDeep as e:
        return False, f"{name}: {e}"

    ref = os.path.join(rundir, "linux-out")
    subprocess.run(["rm", "-rf", ref], check=False)
    os.makedirs(ref)
    # Run the reference against a copy named exactly what the Mac saw. gzip
    # and .Z store no name and fall back to the archive filename minus its
    # last extension, and run.py puts every fixture on the In volume as
    # `archive.sit` — so the reference has to be handed the same name or the
    # two sides derive different names for identical bytes.
    asmac = os.path.join(rundir, "as-the-mac-saw-it", "archive.sit")
    os.makedirs(os.path.dirname(asmac), exist_ok=True)
    subprocess.run(["cp", fixture, asmac], check=False)
    subprocess.run([CLI, "x", "-nr", "--forks", "hidden", asmac, "-o", ref],
                   capture_output=True)
    want_names = []
    enf, _sdc, _sdl, _src, _srl = aggregate_dir(ref, want_names)

    # Mac path tuple -> the components the CLI actually wrote on Linux.
    # Three differences make that mapping necessary, and all three live in
    # vmac_check.mac_component(): the CLI writes a Mac name's '/' as ':',
    # the Mac shell caps each component at 31 characters with its extension
    # kept (ComponentToStr63), and a StuffIt 5 name is UTF-8 on this side
    # and MacRoman on that one (Utf8ToMacRoman) — so `Cool Tools ƒ` is one
    # byte there and two here, and a Japanese name is a row of '_'.
    utf8 = names_are_utf8(fixture, CLI)
    expected = {}
    # The two hosts save an archive COMMENT under different names — the
    # CLI derives one from the archive's filename, the Mac shell writes
    # "Comments" into the destination folder — so the mapping says so
    # here rather than the comparison reporting one MISSING and one
    # UNEXPECTED. The bytes are identical on both sides and are compared
    # like any other file's.
    comment_file = os.path.basename(asmac) + ".comment.txt"
    for root, _d, files in os.walk(ref):
        # The reference is extracted with `--forks hidden`, so a sidecar is
        # exactly a "._" file and an archive entry never is. The Mac has no
        # sidecars at all — a resource fork is part of the file there — so
        # only the data-fork names are expected on the volume.
        for f in files:
            if f.startswith("._"):
                continue
            rel = os.path.relpath(os.path.join(root, f), ref)
            # The VALUE is the components as they are on the Linux disk,
            # unnormalized, because that is what has to be opened below.
            # Normalizing them was wrong and survived until a fixture with
            # an NFD name arrived: this engine writes the archive's own
            # bytes, and `ユーザーライセンスの購入.rtf` is DECOMPOSED in
            # every StuffIt 5 archive that has one, where the oracle
            # manifests hold NFC (run_diff.py normalizes both sides). An
            # NFC key opened a file that does not exist and the fork
            # compared against zero bytes.
            comps = rel.split(os.sep)
            if [unicodedata.normalize("NFC", c) for c in comps] == [comment_file]:
                expected[("Comments",)] = comps
                continue
            # The KEY is what the Mac wrote, and the fold reads the
            # archive's own bytes — so it goes before the normalization and
            # not after it. On an NFD name that is the whole difference:
            # the shell folds 13 code points to 13 '_' where NFC would
            # predict 12 (vmac_check.fold_macroman).
            expected[tuple(unicodedata.normalize("NFC", mac_component(c, utf8))
                           for c in comps)] = comps

    problems = []
    names = set(names)
    missing, extra = set(expected) - names, names - set(expected)
    if missing:
        problems.append("MISSING on the Mac: "
                        + ", ".join(sorted(mac_path(m) for m in missing)))
    if extra:
        problems.append("UNEXPECTED on the Mac: "
                        + ", ".join(sorted(mac_path(e) for e in extra)))

    nforks = 0
    for n in sorted(names & set(expected)):
        flat = "_".join(n).replace("/", "_")
        mb = os.path.join(rundir, "f-" + flat + ".macbin")
        c = subprocess.run(["hcopy", "-m",
                            mac_path(n).encode("mac_roman", "replace"),
                            mb.encode()],
                           capture_output=True, env=env)
        if c.returncode != 0:
            problems.append(f"{mac_path(n)}: cannot copy off the volume")
            continue
        _t, _c2, data, rsrc = os9.macbinary_forks(mb)
        comps = expected[n]
        data_ref = os.path.join(ref, *comps)
        rsrc_ref = os.path.join(ref, *comps[:-1], "._" + comps[-1])
        for label, got, path, mask in (("data", data, data_ref, False),
                                       ("rsrc", rsrc, rsrc_ref, True)):
            want = open(path, "rb").read() if os.path.exists(path) else b""
            a, b = (mask_reserved(got), mask_reserved(want)) if mask else (got, want)
            if a != b:
                problems.append(f"{mac_path(n)} {label}: Mac {len(got)} B vs "
                                f"Linux {len(want)} B MISMATCH")
            elif got or want:
                nforks += 1
    hfs(env, "humount")
    if problems:
        return False, f"{name}: " + "; ".join(problems[:4])
    return True, (f"{name}: {len(names)} file(s), {nforks} fork(s) byte-exact "
                  f"off the Out volume, names included")


def main():
    args = sys.argv[1:]
    # --fixture PATH, repeatable: an archive to match the In volume against
    # besides the committed ones. For a generated subject.
    cands, dirs = [], []
    i = 0
    while i < len(args):
        if args[i] == "--fixture" and i + 1 < len(args):
            cands.append(args[i + 1])
            i += 2
        else:
            dirs.append(args[i])
            i += 1
    dirs = dirs or ["."]
    npass = nfail = nskip = 0
    for d in sorted(dirs):
        ok, detail = check(d.rstrip("/"), cands)
        if ok is None:
            nskip += 1
            print(f"SKIP  {detail}")
        elif ok:
            npass += 1
            print(f"PASS  {detail}")
        else:
            nfail += 1
            print(f"FAIL  {detail}")
    print(f"\n{npass} pass, {nfail} fail, {nskip} skipped — read off the disk "
          f"image, not the screen")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
