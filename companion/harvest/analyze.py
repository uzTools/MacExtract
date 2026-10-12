"""analyze.py SRCDIR — every application in a set of downloads:
its type/creator and each BNDL (owner, FREF types); plus the type/creator
of every other file, for what the programs' own documents carry.

Unpacks with MacExtract's CLI, recursively, and walks HFS images with
hfsutils. Run with python3 -I, from outside the download directories."""
import os, re, struct, subprocess, sys, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools", "vmac"))
import deskclaim as D                                         # noqa: E402

CLI = os.path.join(REPO, "build", "rel", "macextract")
ENC = sys.getfilesystemencoding()


def bundles_from_rsrc(r):
    try:
        res, _ = D.rsrc_read(r)
    except Exception:
        return None
    by = {(t, i): dd for t, i, a, n, dd in res}
    out = []
    for t, i, a, n, dd in res:
        if t != b"BNDL" or len(dd) < 8:
            continue
        owner = dd[:4]
        nt = struct.unpack(">H", dd[6:8])[0] + 1
        q, frefs = 8, []
        try:
            for _ in range(nt):
                ty = dd[q:q + 4]
                c = struct.unpack(">H", dd[q + 4:q + 6])[0] + 1
                q += 6
                m = [struct.unpack(">hh", dd[q + 4 * k:q + 4 * k + 4]) for k in range(c)]
                q += 4 * c
                if ty == b"FREF":
                    frefs = [by.get((b"FREF", g), b"????")[:4] for _l, g in m]
        except struct.error:
            pass
        out.append((owner, frefs))
    return out


def appledouble(path):
    b = open(path, "rb").read()
    if len(b) < 26 or b[:4] != b"\x00\x05\x16\x07":
        return None, None, None
    n = struct.unpack(">H", b[24:26])[0]
    finfo = rsrc = None
    for k in range(n):
        eid, off, ln = struct.unpack(">III", b[26 + 12 * k:38 + 12 * k])
        if eid == 9:
            finfo = b[off:off + 8]
        elif eid == 2:
            rsrc = b[off:off + ln]
    if not finfo:
        return None, None, rsrc
    return finfo[:4], finfo[4:8], rsrc


def s(b):
    return b.decode("mac_roman", "replace") if isinstance(b, bytes) else str(b)


def report(origin, name, typ, cre, rsrc, apps, docs):
    if typ == b"APPL" or (rsrc and typ in (b"APPL", b"appe", b"APPC", b"APPD", b"cdev", b"INIT")):
        bs = bundles_from_rsrc(rsrc) if rsrc else None
        apps.append((origin, name, s(typ), s(cre), bs or []))
    elif typ:
        docs.append((origin, name, s(typ), s(cre)))


def is_hfs(path):
    try:
        with open(path, "rb") as f:
            f.seek(1024)
            if f.read(2) == b"BD":
                return 0
            f.seek(1024 + 84)
            return None
    except OSError:
        return None


def walk_hfs(img, origin, apps, docs):
    home = tempfile.mkdtemp()
    env = dict(os.environ, HOME=home)
    m = subprocess.run(["hmount", img], env=env, capture_output=True)
    vol = re.search(rb'Volume name is "(.*)"', m.stdout or b"")
    if m.returncode or not vol:
        return
    stack = [vol.group(1)]
    while stack:
        path = stack.pop()
        out = subprocess.run([b"hls", b"-la", path + b":"], env=env, capture_output=True).stdout
        for line in out.split(b"\n"):
            if not line or line[:1] not in b"fFd":
                continue
            mm = re.search(rb"(\w{3} [ \d]\d [ \d:]{5}) (.*)$", line)
            if not mm:
                continue
            full = path + b":" + mm.group(2)
            if line[:1] == b"d":
                if full.count(b":") < 8:
                    stack.append(full)
                continue
            tc = line.split()[1]
            typ, cre = tc[:4], tc[5:9]
            name = s(mm.group(2))
            if typ == b"APPL" or True:
                tmp = os.path.join(home, "f.bin")
                if subprocess.run([b"hcopy", b"-m", full, tmp.encode()], env=env, capture_output=True).returncode:
                    continue
                h, d, r = D.macbin_split(open(tmp, "rb").read())
                report(origin + " :: " + s(full), name, h[65:69], h[69:73], r, apps, docs)
                # an archive inside the image: unpack it too
                if typ != b"APPL" and d and len(d) < 64 * 1024 * 1024:
                    dpath = os.path.join(home, "data")
                    open(dpath, "wb").write(d)
                    unpack(dpath, origin + " :: " + s(full), apps, docs, depth=2)
    subprocess.run(["humount"], env=env, capture_output=True)
    shutil.rmtree(home, ignore_errors=True)


def listing(path):
    """{relative path: (type, creator)} from the CLI's listing."""
    out = subprocess.run([CLI, "l", path], capture_output=True).stdout
    m = {}
    for line in out.split(b"\n"):
        f = line.split(None, 4)
        if len(f) == 5 and line[:1] == b"f" and b"/" in f[3]:
            tc = f[3]
            m[f[4].decode(ENC, "surrogateescape")] = (tc[:4], tc[5:9])
    return m


def unpack(path, origin, apps, docs, depth=0):
    if depth > 4:
        return
    if is_hfs(path) == 0:
        walk_hfs(path, origin, apps, docs)
        return
    sn = subprocess.run([CLI, "sniff", path], capture_output=True, text=True, errors="replace")
    if sn.returncode != 0 or "unknown" in sn.stdout.lower() or not sn.stdout.strip():
        return
    tcs = listing(path)
    out = tempfile.mkdtemp(prefix="an-")
    subprocess.run([CLI, "x", "--forks", "hidden", "-o", out, path], capture_output=True)
    for root, dirs, files in os.walk(out):
        for f in files:
            if f.startswith("._"):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, out)
            side = os.path.join(root, "._" + f)
            rsrc = open(side, "rb").read() if os.path.exists(side) else None
            typ, cre = tcs.get(rel, (None, None))
            report(origin + " :: " + rel, f, typ, cre, rsrc, apps, docs)
            if typ != b"APPL" and os.path.getsize(p) > 0:
                unpack(p, origin + " :: " + rel, apps, docs, depth + 1)
    shutil.rmtree(out, ignore_errors=True)


def main():
    src = sys.argv[1]
    apps, docs = [], []
    for root, dirs, files in os.walk(src):
        for f in files:
            if f.startswith("."):
                continue
            p = os.path.join(root, f)
            unpack(p, os.path.relpath(p, src), apps, docs)
    seen = set()
    for origin, name, typ, cre, bs in apps:
        key = (name, cre, tuple((o, tuple(fr)) for o, fr in bs))
        if key in seen:
            continue
        seen.add(key)
        print(f"APP  {cre:4}  {name}   [{origin}]")
        for o, fr in bs:
            print(f"       BNDL owner {s(o)}: {' '.join(s(x) for x in fr)}")
    pairs = {}
    for origin, name, typ, cre in docs:
        pairs.setdefault((typ, cre), (name, origin))
    for (typ, cre), (name, origin) in sorted(pairs.items()):
        if typ in ("TEXT", "ttro") and cre in ("ttxt",):
            continue
        print(f"DOC  {typ:4}/{cre:4}  e.g. {name}")


if __name__ == "__main__":
    main()
