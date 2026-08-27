#!/usr/bin/env python3
"""synth_os9.py — the specimens the Mac OS 9 tier needs and nothing else
leaves behind.

Every other format in `tools/vmac/os9sample.txt` names a fixture the
corpus already holds. Three do not: base64/MIME, btoa and the archives
this engine NAMES and never extracts each generate their subjects into a
temporary directory inside their own suite, so a sweep that boots one
fixture per format had nothing to boot. This writes one of each, once,
into `fixtures/`.

    tools/synth_os9.py --kind mime -o fixtures/synth-os9-mime.mim
    tools/synth_os9.py --kind rar  -o fixtures/synth-os9-rar.rar
    tools/synth_os9.py --kind btoa -o fixtures/synth-os9-btoa.btoa

Deterministic, because `fixtures/SOURCES.md` records the SHA-256 and
`tools/check_docs.py` regenerates every `synthetic:` row in `ci.sh`.
The MIME and RAR shapes come from the suites that grade them —
`run_mime.py` writes the AppleDouble header the way
reference/mpack's `encode_applefile()` does, and `run_foreign.py` fixes
what a RAR signature is — so this file states no format detail of its
own. btoa is encoded by reference/btoa 5.2.1 itself; without
`reference/` there is nothing to encode with, and this exits 3, the
convention `get_lhasa_fixture.py` set for a generator that cannot run on
a fresh offline clone.

Provenance in SOURCES.md: synthetic:tools/synth_os9.py --kind K
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Fixed bytes, so the file is the same on every machine. Text rather than
# random data: what a Mac OS 9 run reads back is compared fork by fork
# against the Linux engine, and a failure is easier to look at.
DATA = b"MacExtract on Mac OS 9: the data fork.\r\n" * 8
RSRC = b"MacExtract on Mac OS 9: the resource fork.\r\n" * 4
BTOA_SUBJECT = b"btoa reached the Macintosh on 2026-08-27.\n" * 12


def kind_mime():
    """multipart/appledouble: one file, both forks, type and creator.

    The shape that only a Macintosh cares about, and the reason MIME is
    in scope at all."""
    import run_mime
    af = run_mime.applefile(b"MacExtract MIME", RSRC)
    return run_mime.message(
        [(b'Content-Type: application/applefile; name="MacExtract MIME"\r\n'
          b"Content-Transfer-Encoding: base64\r\n", run_mime.b64(af)),
         (b'Content-Type: application/octet-stream; name="MacExtract MIME"\r\n'
          b"Content-Transfer-Encoding: base64\r\n", run_mime.b64(DATA))],
        ctype=b'multipart/appledouble; name="MacExtract MIME"')


def kind_rar():
    """A RAR, which the engine names and refuses per the brief. The
    signature is all there is to it — `run_foreign.py` grades that
    reading, including the neighbouring bytes that must NOT be claimed —
    and a refusal is what this fixture exists to photograph on Mac OS 9:
    the alert reading "MacExtract cannot open RAR files." (M38)."""
    return b"Rar!\x1a\x07\x00" + bytes(64)


def kind_btoa():
    """btoa 5.2.1's own output. Version 5 framing (`xbtoa Begin`), which
    is the one with the `z` and `y` shorthands in it."""
    import run_btoa
    if not run_btoa.build():
        print("synth_os9: no reference/btoa (tools/fetch_references.sh)",
              file=sys.stderr)
        raise SystemExit(3)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "btoa-subject.txt")
        with open(src, "wb") as f:
            f.write(BTOA_SUBJECT)
        r = subprocess.run([run_btoa.BIN, src], capture_output=True)
        if r.returncode != 0 or not r.stdout:
            raise SystemExit("synth_os9: the reference would not encode")
        return r.stdout


KINDS = {"mime": kind_mime, "rar": kind_rar, "btoa": kind_btoa}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=sorted(KINDS))
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    blob = KINDS[args.kind]()
    with open(args.out, "wb") as f:
        f.write(blob)
    return 0


if __name__ == "__main__":
    sys.exit(main())
