#!/usr/bin/env python3
"""check_tuple_truth.py — a function that ALWAYS returns a tuple must never
be tested for truthiness.

A 2-tuple is never falsy, so `if f():` on such a function is always taken and
`if not f():` never is. Python reports nothing: no argument list moved, no
name changed. That is the whole of the failure — see DECISIONS.md 2026-09-25,
*the skip that could not fire, again*, where widening `run_btoa.build()` from
a bool to `(ok, why)` on 2026-09-09 left both of its callers testing the old
shape, one skip that could not fire and one guard that could not stop
anything.

Run it on its own:

    python3 tools/check_tuple_truth.py            # the tree
    python3 tools/check_tuple_truth.py DIR        # some other checkout
    python3 tools/check_tuple_truth.py --selftest # prove it can still fail

`--selftest` is what keeps this honest: it runs the same analysis over the
two call sites as they were written BEFORE the fix and fails if they are not
both flagged. A checker nobody has seen fail is not evidence (CLAUDE.md,
*Traps this environment sets*).

**What it cannot see**, and each of these is deliberate — the whole value of
this check is that a hit is unambiguous, so every doubtful shape is dropped
rather than reported:

  - A function that returns a tuple on SOME paths and a scalar or `None` on
    others. There, truthiness may well be the intended test, so it is not
    flagged. A function is only considered when every `return` in it carries
    a tuple of 2 or more AND its body ends in a `return`/`raise` — that last
    clause is an approximation of "cannot fall off the end into `None`", and
    it drops the legitimate `if x: return a, b` / `else: return c, d` shape
    along with the unsafe ones.
  - Any call it cannot resolve to a definition: a function reached through a
    variable, a dict, `getattr`, a class attribute, a decorator that changes
    the return, or a module this walk did not parse. Only two forms resolve —
    a bare `f()` defined at module level in the same file, and `mod.f()` or
    an imported `f()` where the module is another file in this tree.
  - Truthiness reached indirectly: `x = f()` and then `if x:` later. Only a
    call written directly in the boolean position is examined.
  - Methods. Module-level `def`s only, because `self.f()` cannot be resolved
    to one class without a type.
"""
import ast
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKIP_DIRS = {".git", "build", "build-mac", "reference", "third_party",
             "__pycache__", "dist", "node_modules"}


def parse_tree(root):
    """path -> ast.Module, for every .py under root we can parse."""
    trees = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            try:
                src = open(p, encoding="utf-8", errors="replace").read()
                trees[p] = ast.parse(src)
            except SyntaxError:
                pass                    # not ours to fix; nothing to check
    return trees


def always_tuple(fnode):
    """True when every exit from this function hands back a tuple of >= 2.

    Conservative on both counts: a bare `return`, a `return None`, a scalar
    return or a body that does not END in a return/raise all disqualify it,
    because each leaves a falsy result possible and truthiness legitimate."""
    returns = [n for n in ast.walk(fnode) if isinstance(n, ast.Return)]
    if not returns:
        return False
    for r in returns:
        if r.value is None:
            return False
        if not (isinstance(r.value, ast.Tuple) and len(r.value.elts) >= 2):
            return False
    return isinstance(fnode.body[-1], (ast.Return, ast.Raise))


def index(trees):
    """path -> {name: lineno} for module-level defs that always return one."""
    out = {}
    for p, t in trees.items():
        d = {}
        for node in t.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if always_tuple(node):
                    d[node.name] = node.lineno
        out[p] = d
    return out


def bindings(path, tree, tuple_defs, by_mod):
    """What names in this file reach a tuple-returning def.

    -> (direct{name: (defpath, lineno)}, mods{alias: modpath})"""
    direct = {n: (path, ln) for n, ln in tuple_defs.get(path, {}).items()}
    mods = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                base = a.name.split(".")[-1]
                for cand in by_mod.get(base, []):
                    mods[a.asname or base] = cand
        elif isinstance(node, ast.ImportFrom):
            base = (node.module or "").split(".")[-1]
            for a in node.names:
                for cand in by_mod.get(base, []):      # from mod import f
                    ln = tuple_defs.get(cand, {}).get(a.name)
                    if ln:
                        direct[a.asname or a.name] = (cand, ln)
                for cand in by_mod.get(a.name, []):    # from pkg import mod
                    mods[a.asname or a.name] = cand
    return direct, mods


def scan(trees):
    """-> [(path, lineno, shown_name, defpath, defline)], sorted."""
    tuple_defs = index(trees)
    by_mod = {}
    for p in trees:
        by_mod.setdefault(os.path.splitext(os.path.basename(p))[0],
                          []).append(p)

    hits = []
    for p, t in trees.items():
        direct, mods = bindings(p, t, tuple_defs, by_mod)
        if not direct and not mods:
            continue

        def resolved(node):
            if not isinstance(node, ast.Call):
                return None
            f = node.func
            if isinstance(f, ast.Name) and f.id in direct:
                return f.id, direct[f.id]
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                mp = mods.get(f.value.id)
                if mp:
                    ln = tuple_defs.get(mp, {}).get(f.attr)
                    if ln:
                        return "%s.%s" % (f.value.id, f.attr), (mp, ln)
            return None

        def examine(node):
            # `not f()` in a test is the same mistake as `f()`
            while isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                node = node.operand
            r = resolved(node)
            if r:
                hits.append((p, node.lineno, r[0], r[1][0], r[1][1]))

        for node in ast.walk(t):
            if isinstance(node, (ast.If, ast.While, ast.Assert, ast.IfExp)):
                examine(node.test)
            elif isinstance(node, ast.BoolOp):
                for v in node.values:
                    examine(v)
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                examine(node.operand)
            elif isinstance(node, ast.comprehension):
                for v in node.ifs:
                    examine(v)

    return sorted(set(hits))


def report(hits, root):
    for p, ln, name, dp, dl in hits:
        rel = os.path.relpath(p, root)
        drel = os.path.relpath(dp, root)
        print("%s:%d: `%s()` is tested for truthiness, but %s:%d always "
              "returns a tuple — a tuple is never falsy, so this test cannot "
              "fail. Unpack it: `ok, why = %s()`."
              % (rel, ln, name, drel, dl, name), file=sys.stderr)


# The two call sites as they stood at f8821f2, kept here so the check has a
# case it is known to catch. Fixed in the same commit that added this file.
SELFTEST = {
    "run_btoa.py": '''
def build():
    if os.path.exists(BIN):
        return True, None
    if not os.path.isdir(SRC):
        return False, None
    return False, why or "gcc exited"
''',
    "synth_os9.py": '''
import run_btoa
def kind_btoa():
    if not run_btoa.build():
        raise SystemExit(3)
''',
    "sitcrypt.py": '''
import run_btoa as RB
def grade_btoa(outdir, ascii_path):
    if RB.build():
        pass
''',
}


def selftest():
    trees = {}
    for name, src in SELFTEST.items():
        trees[os.path.join(ROOT, "tools", name)] = ast.parse(src)
    hits = scan(trees)
    got = sorted((os.path.basename(p), n) for p, _, n, _, _ in hits)
    want = [("sitcrypt.py", "RB.build"), ("synth_os9.py", "run_btoa.build")]
    if got != want:
        print("check_tuple_truth: SELFTEST FAILED — the check no longer "
              "catches the bug it was written for.\n  expected %s\n  got      %s"
              % (want, got), file=sys.stderr)
        return 1
    print("check_tuple_truth: selftest ok (2 known call sites still caught)")
    return 0


def main():
    if "--selftest" in sys.argv[1:]:
        return selftest()
    if selftest():                      # never trust a pass we cannot fail
        return 1
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    root = os.path.abspath(args[0]) if args else ROOT
    trees = parse_tree(root)
    hits = scan(trees)
    if hits:
        report(hits, root)
        print("check_tuple_truth: %d call site(s) test a tuple for truth"
              % len(hits), file=sys.stderr)
        return 1
    print("check_tuple_truth: ok (%d files)" % len(trees))
    return 0


if __name__ == "__main__":
    sys.exit(main())
