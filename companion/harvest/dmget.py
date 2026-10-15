"""dmget.py QUERY OUTDIR [N] — up to N "MacOS Executable" originals whose
name contains QUERY, from Discmaster's search, into OUTDIR as k.bin (the
originals arrive as MacBinary), with their Discmaster paths in sources.txt.
Paced: one request every 3 seconds; exits 3 on the first refusal."""
import html, os, re, subprocess, sys, time, urllib.parse

UA = "Mozilla/5.0 (X11; Linux x86_64)"
BASE = "https://discmaster.textfiles.com"


def get(url, out):
    time.sleep(3.0)
    r = subprocess.run(["curl", "-sL", "-A", UA, "--max-time", "120", "-o", out,
                        "-w", "%{http_code}", url], capture_output=True, text=True)
    return r.stdout.strip()


def main():
    q, outdir = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    os.makedirs(outdir, exist_ok=True)
    page = os.path.join(outdir, ".search.html")
    if get(BASE + "/search?q=" + urllib.parse.quote(q) + "&pageNum=0", page) != "200":
        print(f"dmget: {q!r}: the search was refused; stopping"); sys.exit(3)
    s = open(page, encoding="utf-8", errors="replace").read()
    i = s.find('<a name="executable">')
    if i < 0:
        print(f"dmget: {q!r}: no executables"); return
    sect = s[i:s.find('<a name="', i + 10) if s.find('<a name="', i + 10) > 0 else len(s)]
    rows = re.findall(r'<td><a href="(/(?:browse|view)/[^"]+)">([^<]+)</a>\s*<td nowrap>([^<]+)<', sect)
    got, seen_names = 0, set()
    ql = q.lower()
    with open(os.path.join(outdir, "sources.txt"), "a") as src:
        for href, name, fmt in rows:
            name = html.unescape(name).strip()
            if not fmt.strip().startswith("MacOS") or ("Executable" not in fmt and "Application" not in fmt):
                continue
            if ql not in name.lower():
                continue
            href = html.unescape(href)
            fileurl = BASE + "/file/" + href.split("/", 2)[2]
            out = os.path.join(outdir, f"{got}.bin")
            code = get(urllib.parse.quote(fileurl, safe=":/%()&=?+,'!~*"), out)
            if code != "200":
                print(f"dmget: {q!r}: download refused ({code}); stopping"); sys.exit(3)
            ok = os.path.getsize(out) > 128
            src.write(f"{got}.bin\t{code}\t{name}\t{href}\n")
            print(f"dmget: {q!r}: {name!r} [{fmt}] -> {code} {os.path.getsize(out) if os.path.exists(out) else 0} B  {href[:90]}")
            if ok:
                got += 1
            if got >= n:
                break
    if got == 0:
        print(f"dmget: {q!r}: nothing downloaded ({len(rows)} rows)")


if __name__ == "__main__":
    main()
