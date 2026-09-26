#!/usr/bin/env python3
"""images.py — which sources make up each overlay image, read from the BUILD.

`mac/CMakeLists.txt` is where the fourteen images are defined, one
`add_custom_command` each, and it is the only place that list may live: a
second copy is a host-side test grading images that are not the ones the
Macintosh runs. So this parses it rather than restating it, and fails loudly
if the shape it expects is gone.

    tools/overlay/images.py            # one line per image: ID source...
    tools/overlay/images.py --check    # just assert the parse
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

# The count is asserted, not derived: an image added to the build and not to
# the host lane is exactly the drift this file exists to prevent, and a parse
# that silently finds thirteen would hide it.
EXPECTED = 14


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
    if len(imgs) != EXPECTED:
        print("images.py: parsed %d images from mac/CMakeLists.txt, expected %d"
              % (len(imgs), EXPECTED), file=sys.stderr)
        print("images.py: the build's shape changed — fix this parse, and the "
              "count above, before trusting any host-side overlay result",
              file=sys.stderr)
        return 1
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
