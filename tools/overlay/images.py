#!/usr/bin/env python3
"""images.py — which sources make up each overlay image, read from the BUILD.

`mac/CMakeLists.txt` is where the decoders' images are defined, one
`add_custom_command` each, and it is the only place that list may live: a
second copy is a host-side test grading images that are not the ones the
Macintosh runs. So this parses it rather than restating it, and fails loudly
if the shape it expects is gone.

    tools/overlay/images.py            # one line per image: ID source...
    tools/overlay/images.py --check    # just assert the parse
    tools/overlay/images.py --names    # their names, in id order (the build's)
    tools/overlay/images.py --count    # how many; --shell-count, the shell's
    tools/overlay/images.py --c-ids    # their ids as a C list (the loader test)
    tools/overlay/images.py --resident # the sources the images TAKE OUT of
                                       # the resident link, one per line

Used by tests/run_overlay_host.sh, which builds the same images with the
m68k-linux toolchain and runs the real loader against them off the Macintosh
(tests/ovlbox/README.md).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not os.path.isdir(os.path.join(ROOT, "mac")):
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMAKE = os.path.join(ROOT, "mac", "CMakeLists.txt")

HEADER = os.path.join(ROOT, "tools", "overlay", "overlay.h")

# The list is asserted against overlay.h's ids, not against a count kept
# here: an image added to the build and not to the host lane is exactly the
# drift this file exists to prevent, and a parse that silently finds
# thirteen would hide it. Every OVL_ID_* but the bundle's and the shell's
# own images (the build's `foreach(img ...)` rule, Toolbox code) must be
# one rule below, and every rule one id.


def header_ids(path=HEADER):
    """overlay.h's image ids, as {OVL_ID_*: number}, the bundle's left out."""
    text = open(path, encoding="utf-8").read()
    return {m.group(1): int(m.group(2)) for m in
            re.finditer(r"^#define\s+(OVL_ID_\w+)\s+(\d+)", text, re.M)
            if m.group(1) != "OVL_ID_BUNDLE"}


def shell_images(path=CMAKE):
    """The shell's own images: the names the build's one `foreach(img ...)`
    rule for them makes."""
    text = open(path, encoding="utf-8").read()
    m = re.search(r"foreach\(img ([a-z ]+)\)\s*\n\s*string\(TOUPPER", text)
    if not m:
        raise SystemExit("images.py: mac/CMakeLists.txt has no rule for the "
                         "shell's images")
    return m.group(1).split()


def images(path=CMAKE):
    text = open(path, encoding="utf-8").read()
    out = []
    # One rule per image: `OVL_ID=<name> ... mkoverlay.sh <out.r> <sources...>`
    # up to the DEPENDS that ends the COMMAND.
    for m in re.finditer(r"OVL_ID=(OVL_ID_\w+)(.*?)DEPENDS", text, re.S):
        ident, body = m.group(1), m.group(2)
        if "mkoverlay.sh" not in body:
            continue
        srcs = []
        for tok in re.findall(r"\$\{(?:ENGINE_DIR|CMAKE_CURRENT_BINARY_DIR)\}/([\w./-]+)",
                              body.split("mkoverlay.sh", 1)[1]):
            if tok.endswith(".r"):          # the output, not a source
                continue
            srcs.append(tok)
        if srcs:
            out.append((ident, srcs))
    return out


def excluded(path=CMAKE):
    """The engine sources the overlay build takes out of the resident link.

    Same reason as `images()`: mac/CMakeLists.txt is where this is decided, and
    a host lane that kept its own copy would link a decoder the Macintosh
    loads from an image — which is the one configuration neither side tests.
    """
    text = open(path, encoding="utf-8").read()
    return re.findall(r'list\(FILTER ENGINE_SRC EXCLUDE REGEX "([\w]+)\\\\\.c\$"\)',
                      text)


def main():
    if "--resident" in sys.argv:
        ex = excluded()
        if len(ex) < 20:
            print("images.py: parsed %d excluded sources, expected 20+"
                  % len(ex), file=sys.stderr)
            return 1
        for name in ex:
            print(name + ".c")
        return 0
    imgs = images()
    ids = header_ids()
    want = set(ids) - {"OVL_ID_" + n.upper() for n in shell_images()}
    got = set(i for i, _ in imgs)
    if got != want or len(imgs) < 10:
        print("images.py: mac/CMakeLists.txt builds %s; overlay.h has ids %s"
              % (sorted(got), sorted(want)), file=sys.stderr)
        print("images.py: an image in one and not the other, or a parse that "
              "broke — fix it before trusting any host-side overlay result",
              file=sys.stderr)
        return 1
    imgs.sort(key=lambda r: ids[r[0]])
    if "--names" in sys.argv:          # the build's lazy list, in id order
        print(" ".join(i[len("OVL_ID_"):].lower() for i, _ in imgs))
        return 0
    if "--count" in sys.argv:
        print(len(imgs))
        return 0
    if "--shell-count" in sys.argv:
        print(len(shell_images()))
        return 0
    if "--c-ids" in sys.argv:          # tests/ovlbox/ovl_load_test.c's kIds
        print("#define OVL_TEST_IDS " + ", ".join(i for i, _ in imgs))
        return 0
    seen = set()
    for ident, srcs in imgs:
        if ident in seen:
            print("images.py: %s is defined twice" % ident, file=sys.stderr)
            return 1
        seen.add(ident)
        if "--check" not in sys.argv:
            print("%s %s" % (ident, " ".join(srcs)))
    if "--check" in sys.argv:
        print("images.py: %d images, ok" % len(imgs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
