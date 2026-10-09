#!/usr/bin/env python3
"""run_shortread.py — the engine under reads that come back short.

`UncIO` allows a read to return fewer bytes than asked before EOF
(include/macextract.h, *I/O*), and every host this project has — a
`FILE *` in the CLI, `FSRead` on a Macintosh — returns the whole request,
so no other suite sends the engine a short read at all. The CLI's
`UNC_SHORT_READ=<n>` caps every read at n bytes; this extracts every
present fixture with the cap and without it and requires the same exit
status, the same messages, and the same names and bytes written. Then it
runs the two suites that hold what the corpus does not — encryption
(`run_crypt.py`) and Private File (`run_privatefile.py`) — whole, under
the same cap, since a fixture that needs a password fails identically
both ways here and proves nothing.

    tools/run_shortread.py --macextract build/macextract [--cap 1]

It has failed once on a real defect: Private File's footer was read with
one bare call, so a valid file came out in full and was then reported
truncated (DECISIONS.md 2026-10-09, *the read nothing sent short*).

What it CANNOT see: a decoder that is right under any cap but slow under
a small one — the cap multiplies calls, and nothing here times them —
and anything the Macintosh host does differently, since only the CLI
honours the variable.
"""
import argparse
import concurrent.futures
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXDIR = os.path.join(REPO, "fixtures")


def tree(root):
    out = []
    for d, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            h = hashlib.sha256(open(p, "rb").read()).hexdigest()
            out.append((os.path.relpath(p, root), h))
    return sorted(out)


def extract(mx, path, out, cap):
    env = dict(os.environ)
    env.pop("UNC_SHORT_READ", None)
    if cap:
        env["UNC_SHORT_READ"] = str(cap)
    r = subprocess.run([mx, "x", "-o", out, path], capture_output=True,
                       stdin=subprocess.DEVNULL, env=env, timeout=900)
    msg = (r.stdout + r.stderr).decode("utf-8", "replace").replace(out, "OUT")
    if cap:
        # The CLI announces the cap. A binary that does not is one built
        # before the hook, and would pass every comparison by ignoring it.
        said = "macextract: every read capped at %d B\n" % cap
        if said not in msg:
            raise SystemExit("shortread: %s does not honour UNC_SHORT_READ"
                             % mx)
        msg = msg.replace(said, "", 1)
    return r.returncode, msg, tree(out)


def compare(mx, path, cap):
    tmp = tempfile.mkdtemp(prefix="shortread-")
    try:
        a = extract(mx, path, os.path.join(tmp, "a"), 0)
        b = extract(mx, path, os.path.join(tmp, "b"), cap)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if a == b:
        return None
    if a[0] != b[0]:
        why = "exit %d, %d under the cap" % (a[0], b[0])
    elif a[1] != b[1]:
        why = "messages differ: %r" % b[1].strip().splitlines()[-1:]
    else:
        why = "%d file(s) written, %d under the cap, or bytes differ" % (
            len(a[2]), len(b[2]))
    return "%s: %s" % (os.path.basename(path), why)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--macextract", default=os.path.join(REPO, "build",
                                                         "macextract"))
    ap.add_argument("--cap", type=int, default=1)
    ap.add_argument("-j", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()
    mx = os.path.abspath(a.macextract)

    fixtures = []
    for m in sorted(os.listdir(os.path.join(FIXDIR, "manifests"))):
        p = os.path.join(FIXDIR, m[:-len(".json")])
        if m.endswith(".json") and os.path.isfile(p):
            fixtures.append(p)
    with concurrent.futures.ThreadPoolExecutor(a.j) as ex:
        bad = [r for r in ex.map(lambda p: compare(mx, p, a.cap), fixtures)
               if r]
    for b in bad:
        print("shortread: FAIL %s" % b)

    env = dict(os.environ, UNC_SHORT_READ=str(a.cap))
    for suite in ("run_crypt.py", "run_privatefile.py"):
        r = subprocess.run([sys.executable, os.path.join(REPO, "tools", suite),
                            "--macextract", mx], capture_output=True, env=env)
        if r.returncode != 0:
            print("shortread: FAIL %s under the cap:\n%s" % (
                suite, r.stdout.decode(errors="replace")[-2000:]))
            bad.append(suite)

    if bad:
        print("shortread: %d failure(s)" % len(bad))
        return 1
    print("shortread: %d fixture(s) extract identically with every read "
          "capped at %d B, and run_crypt.py and run_privatefile.py pass "
          "under the same cap" % (len(fixtures), a.cap))
    return 0


if __name__ == "__main__":
    sys.exit(main())
