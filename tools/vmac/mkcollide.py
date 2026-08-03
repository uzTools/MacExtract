#!/usr/bin/env python3
"""mkcollide.py — build a tar whose entries COLLIDE once the Mac renames them.

`BumpName()` in mac/unclassic_mac.c appends `~1`..`~9` when a sanitized name
already exists on the output volume. It is real code on a real path — it is
what produced `archive.sit~1` when the gzip/.Z fallback name collided with the
archive itself — but nothing has ever verified it, and nothing in the corpus
can: across all 769 manifests, **no two entries collide** under the Mac's
rules (case-insensitive HFS, 31-character components, ':' <-> '/'). Checked,
not assumed.

So the only way to exercise it is to build an archive for the purpose. Two
independent ways of colliding, because they reach BumpName through different
parts of ComponentToStr63:

  * **case** — HFS is case-insensitive, so `README` and `readme` are the same
    name on the Mac and two different files on Linux;
  * **truncation** — two names identical in their first 31 characters are the
    same name on the Mac, whatever follows.

Three entries share the truncating prefix, so `~1` and `~2` both have to
happen, and the 29-character clamp inside BumpName (it truncates to 29 before
appending two characters) is exercised by construction.

Every payload is distinct and self-identifying, so the check is not merely
"five files exist" but "the right bytes are in the file with the right name".

    tools/vmac/mkcollide.py /tmp/collide.tar
"""
import io, os, subprocess, sys, tarfile, tempfile

# Exactly 31 characters, so the three names below differ only past the cap.
PREFIX = "collide-me-when-truncated-to-31"
assert len(PREFIX) == 31, len(PREFIX)

# name -> payload. The payload names itself so a mix-up is visible rather than
# just a length mismatch.
ENTRIES = [
    ("README", b"payload of README, upper case\n"),
    ("readme", b"payload of readme, lower case\n"),
    (PREFIX + "-alpha", b"payload of alpha\n"),
    (PREFIX + "-beta", b"payload of beta\n"),
    (PREFIX + "-gamma", b"payload of gamma\n"),
]


# What the Mac is expected to write, MEASURED on a real System 6.0.8 Mac Plus
# on 2026-08-02 and then held as the assertion. The rule it follows is
# ComponentToStr63 (cap at 31) plus BumpName (clamp to 29, append ~N):
#
#   README          first arrival keeps the name
#   readme~1        collides case-insensitively with README
#   collide-...-31  first of the three long names, truncated to 31
#   collide-...-~1  second: truncated to 29, then "~1" -> 31 characters
#   collide-...-~2  third
#
# Archive order decides who keeps the plain name, which is why the payloads
# are distinct: a check that only counted files would pass even if the bytes
# had gone into the wrong ones.
EXPECTED = [
    ("README",                          b"payload of README, upper case\n"),
    ("readme~1",                        b"payload of readme, lower case\n"),
    ("collide-me-when-truncated-to-31", b"payload of alpha\n"),
    ("collide-me-when-truncated-to-~1", b"payload of beta\n"),
    ("collide-me-when-truncated-to-~2", b"payload of gamma\n"),
]


def verify(outdsk):
    """Check an Out volume against EXPECTED. Returns (ok, [lines])."""
    home = tempfile.mkdtemp(prefix="collide-")
    env = dict(os.environ, HOME=home)
    run = lambda *a: subprocess.run(a, capture_output=True, env=env)
    if run("hmount", outdsk).returncode != 0:
        return False, [f"cannot mount {outdsk}"]
    got = [l.decode("mac_roman") for l in
           run("hls", "-a", "-1").stdout.split(b"\n") if l.strip()]
    lines, ok = [], True
    want_names = [n for n, _ in EXPECTED]
    if sorted(got) != sorted(want_names):
        ok = False
        lines.append(f"NAMES differ: Mac {sorted(got)}")
        lines.append(f"    expected {sorted(want_names)}")
    for name, payload in EXPECTED:
        if name not in got:
            continue
        tmp = os.path.join(home, "f")
        if run("hcopy", "-r", name.encode("mac_roman"), tmp.encode()).returncode != 0:
            ok = False
            lines.append(f"{name}: cannot copy off the volume")
            continue
        data = open(tmp, "rb").read()
        if data != payload:
            ok = False
            lines.append(f"{name}: WRONG PAYLOAD {data!r}, expected {payload!r}")
        else:
            lines.append(f"{name}: {len(data)} B, correct payload")
    run("humount")
    return ok, lines


def build(path):
    with tarfile.open(path, "w", format=tarfile.USTAR_FORMAT) as tf:
        for name, payload in ENTRIES:
            ti = tarfile.TarInfo(name)
            ti.size = len(payload)
            ti.mtime = 0            # deterministic: same bytes every build
            ti.mode = 0o644
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            tf.addfile(ti, io.BytesIO(payload))
    return path


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--verify":
        good, report = verify(sys.argv[2])
        for l in report:
            print("  " + l)
        print("PASS — BumpName renames collisions and keeps the payloads with "
              "the right names" if good else "FAIL")
        sys.exit(0 if good else 1)
    out = sys.argv[1] if len(sys.argv) > 1 else "collide.tar"
    print(build(out))
