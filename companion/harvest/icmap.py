"""icmap.py MACBINARY — the Internet Config 'Mapping' entries of an Internet Preferences file.
Layout read off Mac OS 9.2's own file, not a header: 4 bytes, then entries of
total length, fixed length (0x16), version, type, creator, post-processor creator,
flags, and five Pascal strings (extension, application, post-processor, MIME type,
name). The walk must land exactly on the resource's end. DECISIONS.md 2026-10-31."""
import os, sys, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools", "vmac"))
import deskclaim as D
b = open(sys.argv[1], "rb").read()
dl, rl = struct.unpack(">II", b[83:91])
r = b[128 + ((dl + 127) // 128) * 128:][:rl]
res, _ = D.rsrc_read(r)
m = [dd for t, i, a, n, dd in res if n == b"Mapping"][0]
q = 4; out = []  # 4 bytes precede the first entry (read off the data)
while q < len(m):
    tot, fix, ver = struct.unpack(">HHH", m[q:q+6])
    ty, cr, pc = m[q+6:q+10], m[q+10:q+14], m[q+14:q+18]
    fl = struct.unpack(">I", m[q+18:q+22])[0]
    p = q + fix; ss = []
    for _ in range(5):
        L = m[p]; ss.append(m[p+1:p+1+L].decode("mac_roman")); p += 1 + L
    out.append((ss[0], ty.decode("mac_roman"), cr.decode("mac_roman"), pc.decode("mac_roman"), "%08x" % fl, ss[1], ss[2], ss[3], ss[4]))
    assert tot > 0; q += tot
assert q == len(m), (q, len(m))
for e in out: print("\t".join(e))
print("#entries", len(out), file=sys.stderr)
