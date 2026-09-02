#!/usr/bin/env python3
"""mkforwards.py — generate the overlay's host vector and its forwards.

An overlay compiles engine source UNMODIFIED, so every engine helper that
source calls has to resolve inside the blob. Each one is therefore defined in
the overlay as a one-line forward through a table of pointers the application
fills. With one decoder that was twelve functions written by hand; with six it
is forty-odd, and hand-writing them is how a wrong argument list gets across
the boundary silently.

So they are generated from the engine's own prototypes. Three files:

    ovl_host_gen.h        the OverlayHostFns struct   (both sides)
    ovl_host_init_gen.h   its initialiser             (application side)
    ovl_forwards_gen.c    one forward per symbol      (overlay side)

**Real engine types, not opaque ones.** overlay.h keeps engine types out of
OverlayHost deliberately, so that a blob cannot depend on their layout. That
argument does not reach here: a decoder overlay compiles the decoder, so it
already depends on every one of those layouts. What the opacity would buy is
casts on both sides — and a cast is exactly what turns a signature mismatch
from a compile error into a wrong call at run time.

    tools/overlay/mkforwards.py <outdir>

The symbol list is below, in this file, because it IS the interface: adding a
decoder to an overlay means adding whatever it calls here, and the build fails
loudly (undefined reference) if something is missing.
"""
import os
import re
import sys

# The union over every decoder that has an overlay. Sorted, one per line, so a
# diff shows exactly what a new decoder brought with it.
SYMBOLS = """
unc_bitin_align unc_bitin_bits unc_bitin_bits_le unc_bitin_bytepos
unc_bitin_init unc_bitin_init_le unc_bufin_init unc_bufin_init_mem
unc_bufin_next_slow unc_bufin_skip_to unc_bufin_tell unc_canon_build
unc_canon_build_ext unc_canon_decode unc_crc32 unc_crypt_cpt unc_crypt_xor
unc_entry_clear unc_entry_path_append unc_entry_set_name unc_entry_set_path
unc_fork_flush unc_fork_out unc_fork_split unc_huff_decode unc_huff_read_tree
unc_io_size32 unc_lzah_decode unc_lzdyn_decode unc_lzst0_decode unc_lzw_free
unc_lzw_init unc_lzw_read unc_macbinary_probe unc_password unc_path_init
unc_path_leaf unc_path_pop unc_path_push unc_progress_add unc_read_at
unc_read_full unc_crc16_arc unc_crc16_xmodem unc_progress_at
unc_readline unc_crypt_packit_des unc_crypt_packit_xor unc_crypt_rc4
unc_crypt_sit unc_crypt_sit5_key
""".split()

HEADERS = ("src/unc_internal.h", "include/macextract.h")


def split_params(args):
    """Split an argument list on TOP-LEVEL commas only."""
    out, depth, cur = [], 0, ""
    for ch in args:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


PP = ("define", "include", "ifdef", "ifndef", "endif", "if", "else", "elif",
      "pragma", "undef", "enum", "typedef")


def return_type(before):
    """The type tokens immediately before the name, and nothing else."""
    toks = before.replace("*", " * ").split()
    got = []
    while toks:
        t = toks.pop()
        if t == "*" or re.match(r"^[A-Za-z_]\w*$", t):
            if t.lower() in PP or t.isdigit():
                break
            got.insert(0, t)
            if t in ("void", "int", "char", "long", "short") or \
               re.match(r"^(u?int\d+_t|Unc\w+|size_t)$", t):
                # a complete type unless a qualifier precedes it
                if toks and toks[-1] in ("const", "unsigned", "signed",
                                         "struct"):
                    got.insert(0, toks.pop())
                break
            if len(got) >= 3:
                break
        else:
            break
    if not got:
        return None
    return " ".join(got).replace(" *", " *")


def declarations(root):
    """symbol -> (return type, [(type, name)], raw) from the engine headers."""
    text = ""
    for h in HEADERS:
        with open(os.path.join(root, h)) as f:
            text += f.read() + "\n"
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)      # comments out
    out = {}
    for chunk in text.split(";"):
        chunk = " ".join(chunk.split())
        # Anchored at the END, not the start: a chunk is everything since the
        # last semicolon, so it can carry a #define or an enum with it, and
        # anchoring at the start silently skipped four prototypes that were
        # preceded by one.
        m = re.search(r"(unc_\w+)\s*\((.*)\)$", chunk)
        if not m:
            continue
        name, args = m.group(1), m.group(2)
        if name not in SYMBOLS or name in out:
            continue
        ret = return_type(chunk[:m.start()])
        if ret is None:
            return None, "cannot find a return type for %s in %r" % (
                name, chunk[-90:])
        params = []
        for a in split_params(args):
            a = a.strip()
            if a in ("void", ""):
                continue
            # A function-pointer parameter — int (*put)(void *, uint8_t) —
            # carries its name inside the first parenthesis, and splitting on
            # commas without counting depth tears it in half. That is what the
            # first version of this script did, and unc_lzdyn_decode caught it.
            fp = re.match(r"^(.*)\(\s*\*\s*(\w+)\s*\)\s*\((.*)\)$", a)
            if fp:
                params.append((None, fp.group(2),
                               "%s(*%%s)(%s)" % (fp.group(1), fp.group(3))))
                continue
            # An ARRAY parameter — const uint8_t hash[UNC_SIT5_KEYLEN] —
            # keeps its brackets after the name, which the plain pattern below
            # cannot see. It decays to a pointer either way; what matters is
            # that the forward's signature matches the engine's exactly.
            ar = re.match(r"^(.*?[ *])(\w+)\s*(\[[^\]]*\])$", a)
            if ar:
                params.append((None, ar.group(2),
                               "%s%%s%s" % (ar.group(1), ar.group(3))))
                continue
            pm = re.match(r"^(.*?[ *])(\w+)$", a)
            if not pm:
                return None, "cannot parse parameter %r of %s" % (a, name)
            params.append((pm.group(1).strip(), pm.group(2), None))
        out[name] = (ret.strip(), params)
    missing = [s for s in SYMBOLS if s not in out]
    if missing:
        return None, "no prototype found for: " + ", ".join(missing)
    return out, None


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "."
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    root = os.path.join(root, "unclassic") if not os.path.exists(
        os.path.join(root, "src")) else root
    decls, err = declarations(root)
    if err:
        print("mkforwards: " + err, file=sys.stderr)
        return 1

    def sig(name, ptr):
        ret, params = decls[name]
        parts = []
        for t, n, tmpl in params:
            parts.append(tmpl % n if tmpl else "%s %s" % (t, n))
        args = ", ".join(parts) or "void"
        return "%s (%s)(%s)" % (ret, ptr, args) if ptr.startswith("*") \
            else "%s %s(%s)" % (ret, ptr, args)

    with open(os.path.join(outdir, "ovl_host_gen.h"), "w") as f:
        f.write("/* GENERATED by tools/overlay/mkforwards.py — do not edit. */\n"
                "#ifndef UNC_OVL_HOST_GEN_H\n#define UNC_OVL_HOST_GEN_H\n"
                '#include "unc_internal.h"\n\ntypedef struct OverlayHostFns {\n')
        for s in SYMBOLS:
            f.write("    %s;\n" % sig(s, "*" + s[4:]))
        f.write("} OverlayHostFns;\n\n#endif\n")

    with open(os.path.join(outdir, "ovl_host_init_gen.h"), "w") as f:
        f.write("/* GENERATED by tools/overlay/mkforwards.py — do not edit. */\n")
        f.write("#define OVL_HOST_FNS_INIT { \\\n")
        f.write(", \\\n".join("    %s" % s for s in SYMBOLS))
        f.write(" \\\n}\n")

    with open(os.path.join(outdir, "ovl_forwards_gen.c"), "w") as f:
        f.write("/* GENERATED by tools/overlay/mkforwards.py — do not edit.\n"
                " *\n"
                " * Compiled into every decoder overlay. Each definition\n"
                " * satisfies the reference the decoder makes and forwards it\n"
                " * to the application through the host vector.\n */\n"
                '#include "ovl_host_gen.h"\n'
                '#include "overlay.h"\n\n'
                "extern const OverlayHostFns *g_ovl_fns;\n\n")
        for s in SYMBOLS:
            ret, params = decls[s]
            call = ", ".join(n for _, n, _t in params)
            body = "%sg_ovl_fns->%s(%s);" % (
                "" if ret == "void" else "return ", s[4:], call)
            f.write("%s\n{ %s }\n\n" % (sig(s, s), body))
    print("mkforwards: %d symbol(s)" % len(SYMBOLS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
