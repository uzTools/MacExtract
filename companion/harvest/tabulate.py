"""tabulate.py DLDIR > app-bundles.tsv — one row per bundle of every
application in every copy dmget.py fetched: DLDIR/<query>/<k>.bin with
DLDIR/<query>/sources.txt beside it. Each copy is analysed on its own, so
copies from different discs can be seen to agree, or not.

Run with python3 -I from outside the download directories: they hold
untrusted data."""
import hashlib, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A                                           # noqa: E402

def s(b): return A.s(b)


def unescape(name):
    """The CLI writes a name's non-ASCII bytes as \\xNN; put them back."""
    return re.sub(r"(?:\\x[0-9a-fA-F]{2})+",
                  lambda m: bytes.fromhex(m.group(0).replace("\\x", "")).decode("utf-8", "replace"),
                  name)

def main():
    top = sys.argv[1]
    print("# query\tapplication\tcreator\tbundle_owner\tdeclared_types\tsource\tsha256")
    for q in sorted(os.listdir(top)):
        d = os.path.join(top, q)
        src = os.path.join(d, "sources.txt")
        if not os.path.isfile(src):
            continue
        for line in open(src, encoding="utf-8", errors="replace"):
            f = line.rstrip("\n").split("\t")
            if len(f) < 4 or f[1] != "200":
                continue
            path = os.path.join(d, f[0])
            if not os.path.isfile(path):
                continue
            sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
            apps, docs = [], []
            A.unpack(path, f[0], apps, docs)
            where = "discmaster:" + f[3]
            if not apps:
                print(f"{q}\t{f[2]}\t\t\t(no application found)\t{where}\t{sha}")
            for origin, name, typ, cre, bs in apps:
                name = unescape(name)
                if not bs:
                    print(f"{q}\t{name}\t{cre}\t\t(no BNDL)\t{where}\t{sha}")
                for o, fr in bs:
                    print(f"{q}\t{name}\t{cre}\t{s(o)}\t{' '.join(s(x) for x in fr)}\t{where}\t{sha}")

if __name__ == "__main__":
    main()
