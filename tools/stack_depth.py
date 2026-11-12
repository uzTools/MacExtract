#!/usr/bin/env python3
"""stack_depth.py — the deepest call chains through the engine, and their frames.

CLAUDE.md's 68000 rule is "no recursion, call depth <= 4 KB — measure it, do
not assume it". This measures it: every function's frame and every call edge
come from the compiler itself (`-fcallgraph-info=su`, which writes the call
graph GCC actually emitted, after inlining, with each function's
`-fstack-usage` figure on its node), and the worst path is a longest-path sum
over that graph.

Two configurations:

  --config shipped (default)  what dist/ ships: the resident engine and shell
                              with mac/CMakeLists.txt's flags, every decoder
                              in the 'OVLY' image tools/overlay/mkoverlay.sh
                              builds it into, with mkoverlay's flags, and the
                              forwards and shims between them (mac/ovl_shim.c,
                              the generated ovl_forwards*_gen.c) as the real
                              frames they are.
  --config host               FORMATS.md *Stack*'s one command, `-Os
                              -std=c99`, every src/*.c in one namespace.

What a chain's bytes are: each function's `-fstack-usage` figure (locals,
saved registers and the most argument bytes it has pushed at once), plus 4
for the return address its caller's JSR pushed, plus 4 more when it opens
with LINK, whose saved frame pointer `-fstack-usage` does not count (both
measured on this compiler; see `--selftest`). The pushed-argument share is
the function's MAXIMUM, not what is pushed at the call taken, so a chain is
an upper bound by up to that much per level. A tail call (JRA/JMP to another
function) charges the callee in place of the caller's frame, not on top.

Indirect calls are resolved, not dropped. GCC reports every call through a
pointer with its source position; the callee expression found there (its
last member, `->write`, `->seek`, `emit`...) names a CLASS in the table
below, and each class lists the functions that can be behind it: the
per-format extract table, the probe table, the segment schemes, the UncIO
implementations the engine wraps itself in, the put/emit callbacks a
decoder hands a codec, and the shell's sink, IO, allocator, progress and
password callbacks. Two checks make the table fail rather than go stale:
an indirect call whose callee expression is in no class is an error, and so
is a function whose address is taken anywhere (a relocation to it outside a
call instruction, or from a data section) that no class lists.

A class alone over-approximates into paths the code cannot take — a
decoder reading through a joined set's stream when no set is open, the
envelope peek decoding DiskDoubler, a cipher in a format that has none —
and two of them are cycles (a wrapping stream under itself). EDGE_RULES
carries the facts that rule those out, each with the source it rests on,
and check_rules() re-reads the two that are lists. A cycle that survives
them is an error: recursion, or a class wider than the code.

"The engine's deepest chain" starts at the engine's own entry points
(unc_extract, unc_extract_segments...) and counts the shell's callbacks
(sink, file IO, progress, allocator) as nothing: those frames are the
shell's. --shell adds them, and the shell's own frames above the engine.

What it CANNOT see:

  * inline asm and Toolbox traps. A trap is one A-line word to this
    tool; the ROM's own frames under it (the File Manager inside
    FSWrite, the Dialog Manager inside ModalDialog) are not here at all.
    FORMATS.md *Stack*'s SAMPLE/PAINT measure those, on the machine.
  * alloca and variable-length arrays: a frame GCC reports as `dynamic`
    (unbounded) is printed with a warning and counted at its static
    part. None exists today; the run says so if one appears.
  * calls the call graph does not show: a function reached only through
    a pointer that is stored where the address-taken scan cannot see it
    (built by arithmetic, or passed in from outside the objects built
    here), and the precision of the class table itself — a class lists
    every function that CAN be behind its pointer, so a chain may
    combine a call site with a target that site never reaches.
  * library code: memcpy, memset and libgcc's arithmetic (__mulsi3,
    __divsi3...) are charged the frames in LIBRARY below, read off
    their disassembly, not compiled here.
  * the two shell images (ovl_destdlg, ovl_segsetup): the dialogs they
    hold run from the shell, not under the engine, and are not compiled
    here; the run lists the calls into them it did not follow.
  * a fact EDGE_RULES gets wrong. Each rule removes paths; a wrong one
    removes real ones, and nothing here can tell.

Usage:
    tools/stack_depth.py [--config shipped|host] [--top N] [--shell]
                         [--limit BYTES] [--extra-frame FUNC=BYTES]
                         [--extra-edge CALLER=CALLEE] [--selftest]
--limit makes the exit status 1 when the engine's deepest chain exceeds
it (CLAUDE.md's 4,096). --extra-frame and --extra-edge inject a frame or
an edge, so the tool can be shown to fail (TESTING.md, *The 68000
call depth*).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "overlay"))
import mkforwards  # noqa: E402  (CODECS / ZIPOLD: who the vector points at)

TOOL = os.path.join(os.environ.get("RETRO68", "/opt/Retro68-build/toolchain"),
                    "bin", "m68k-apple-macos-")

# The resident link's flags, as build/mac/CMakeFiles/.../flags.make has them
# for a Release build (tools/build_mac.sh): CMake's Release -O3 -DNDEBUG, then
# target_compile_options, whose -Os wins. check_flags() fails if
# mac/CMakeLists.txt's unconditional options stop matching this list.
RESIDENT_FLAGS = ["-O3", "-DNDEBUG", "-mcpu=68000", "-Os", "-Wno-multichar",
                  "-fno-tree-loop-distribute-patterns",
                  "-freorder-blocks-algorithm=simple", "-fipa-icf",
                  "-ffunction-sections", "-DUNC_AT_OVERLAY"]
# tools/overlay/mkoverlay.sh's ovl_cc(); check_flags() compares.
OVERLAY_FLAGS = ["-Os", "-mcpu=68000", "-mpcrel", "-ffunction-sections",
                 "-fdata-sections", "-fno-builtin",
                 "-fno-tree-loop-distribute-patterns"]
# FORMATS.md *Stack*'s command. -ffunction-sections changes no frame (checked
# 2026-11-09 on every src/*.c) and puts every call behind a relocation.
HOST_FLAGS = ["-mcpu=68000", "-Os", "-std=c99", "-ffunction-sections"]

SHELL_SRC = ["mac/macextract_mac.c", "mac/mac_start.c"]
GLUE_SRC = ["mac/ovl_shim.c", "mac/ovl_reloc.c", "mac/ovl_load_eager.c"]
# mac/ovl_shim.c's helpers that call an image for several shims. Each maps
# a shim to the (image, function) pairs it reaches; a shim not named
# reaches the one image defining its own name.
SHARED_SHIMS = {
    "ovl_run": {},
    "seg_id": {"unc_segment_match": [("sniff", "unc_segment_match"),
                                     ("cptdd", "unc_cptseg_match"),
                                     ("zipold", "unc_abk_match")]},
}

# Library routines the resident link takes from Retro68 (an image links
# tools/overlay/ovl_rt.c's own, which is compiled here). Bytes are the
# -fstack-usage equivalent (saved registers and pushes; the return address
# is added as for every function), read off `objdump -dr` of the
# toolchain's libgcc.a and m68k-apple-macos/lib/libc.a on 2026-11-09.
LIBRARY = {
    "memcpy": (0, []), "memmove": (32, []), "memset": (4, []),
    "memcmp": (12, []), "strlen": (0, []),
    "__mulsi3": (0, []), "__udivsi3": (4, []),
    "__divsi3": (12, ["__udivsi3"]),
    "__umodsi3": (8, ["__udivsi3", "__mulsi3"]),
    "__modsi3": (8, ["__divsi3", "__mulsi3"]),
}

# Indirect-call classes. Key: the callee expression's last identifier at the
# call site (`c->sink->write(` -> "write"). Value: the functions behind it,
# each "name" (a global anywhere) or "file.c:name" (a static). A class whose
# targets are all the shell's is empty in --config host and engine-only
# figures, which is what "the engine's deepest chain" means: the sink's own
# frames are the shell's, and counted only with --shell.
SH = "SHELL:"
CLASSES = {
    # UncIO (include/macextract.h): the engine's own streams, then the shell's
    "read": ["unc_segment.c:seg_read", "unc_peek.c:pw_read",
             "unc_peek.c:ph_read", SH + "macextract_mac.c:fio_read"],
    "seek": ["unc_segment.c:seg_seek", "unc_peek.c:pw_seek",
             "unc_peek.c:ph_seek", SH + "macextract_mac.c:fio_seek"],
    "tell": ["unc_segment.c:seg_tell", "unc_peek.c:pw_tell",
             "unc_peek.c:ph_tell", SH + "macextract_mac.c:fio_tell"],
    "size": ["unc_segment.c:seg_size", "unc_peek.c:pw_size",
             "unc_peek.c:ph_size", SH + "macextract_mac.c:fio_size"],
    # UncSink
    "begin_entry": ["unc_peek.c:ph_begin", SH + "macextract_mac.c:sink_begin"],
    "write": ["unc_peek.c:ph_write", SH + "macextract_mac.c:sink_write"],
    "end_entry": ["unc_peek.c:ph_end", SH + "macextract_mac.c:sink_end"],
    "comment": [SH + "macextract_mac.c:sink_comment"],
    # UncAlloc, and zlib's own pair (unc_inflate.c installs unc_z*)
    # The release's peek allocator is the set's setup image's since
    # 2026-11-11 (mac/release_plan.inc.c), which is not compiled here; it
    # runs before the engine, and calls NewPtr and nothing else.
    "alloc": [SH + "macextract_mac.c:mal_alloc"],
    "free": [SH + "macextract_mac.c:mal_free"],
    "ZALLOC": ["unc_inflate.c:unc_zalloc", "zutil.c:zcalloc"],
    "ZFREE": ["unc_inflate.c:unc_zfree", "zutil.c:zcfree"],
    # UncProgress, UncPasswordAsk, UncVolumeSource
    "tick": ["fmt_mime.c:mime_relay", SH + "macextract_mac.c:prog_tick"],
    "ask": [SH + "macextract_mac.c:MacAskPassword"],
    "need": [SH + "macextract_mac.c:seg_need"],
    "release": [SH + "macextract_mac.c:seg_release"],
    "vs.size": [SH + "macextract_mac.c:seg_part_size"],
    # OverlayHost's own crc32, for the crypt image (tools/overlay/overlay.h)
    "crc32": ["ovl_shim.c:ovl_host_crc32"],
    # the segment map a joined set hands its decoder (src/unc_internal.h)
    "seek_part": ["unc_segment.c:seg_seek_part"],
    "skip": ["unc_segment.c:seg_skip_fwd"],
    "part_size": ["unc_segment.c:seg_part_size"],
    # unc_segid.c's table, then unc_segment.c's
    "describe": ["unc_sitseg_describe", "unc_cptseg_describe",
                 "unc_ddseg_describe", "unc_zipseg_describe",
                 "unc_mimeseg_describe", "unc_abk_describe"],
    "match": ["unc_sitseg_match", "unc_cptseg_match", "unc_ddseg_match",
              "unc_abk_match"],
    "payload": ["unc_ddseg_payload"],
    "stored_crc": ["unc_sitseg_stored_crc", "unc_ddseg_stored_crc"],
    "crc_fold": ["unc_crc16_arc", "unc_crc16_xmodem"],
    "hdr": ["unc_mimeseg_head"],
    # the per-format extract table (unc_engine.c) and the schemes' own
    # (unc_segment.c): every unc_*_extract whose address each file takes,
    # filled in by resolve()
    "extract": [],
    "scheme.extract": [],
    # unc_sniff.c's probe tables: every unc_*_probe* taken there
    "order": [],
    # callbacks a decoder hands a codec
    "emit": ["fmt_exo.c:exo_emit", "fmt_exo.c:zip_emit", "fmt_exo.c:zip_put",
             "fmt_exo.c:zip_attr_emit"],
    "put": ["fmt_lzh.c:lzh_put_run", "fmt_sit.c:sit_put_run",
            "fmt_arc.c:arc_trim_put"],
    "rd": ["fmt_exo.c:zip_scan_read", "zs_io_read_at",
           "unc_encinfo.c:zip_read_at"],
}
for _op in ("read", "seek", "tell", "size"):
    # what a wrapping stream (PeekWin, a joined set's current part) wraps:
    # the file the shell opened, never another wrapper
    CLASSES["base." + _op] = [SH + "macextract_mac.c:fio_" + _op]
# Callbacks that wrap another of their own kind: a joined set's stream and
# the envelope peek's window wrap an UncIO, MIME's relay wraps the
# progress callback. A path never has one under itself (bit per file).
WRAPPERS = {"unc_segment.c": 1, "unc_peek.c": 2, "fmt_mime.c": 4}
WRAPPED = ("read", "seek", "tell", "size", "tick", "seek_part", "skip",
           "part_size")
# Which callbacks a path can meet depends on how it got there, and these
# rules say so (src/unc_segment.c's seg_schemes[] and unc_extract_segments;
# src/unc_peek.c's unc_envelope_peek). A joined set's stream (seg_read...)
# exists only under unc_extract_segments, which hands it to the scheme's
# extract — the MIME walk for message/partial, the only scheme with a
# hdr(); Compact Pro or zip, the two `addressed` schemes and the only ones
# given a segment map — or, for StuffIt's, DiskDoubler's and plain splits,
# to unc_sitseg_emit, which copies it out and is the only reader of their
# payload(), stored_crc() and crc_fold(). The peek's window and head exist
# only under unc_envelope_peek.
# The envelope peek decodes only an envelope (unc_sniff_envelope's
# answer), and input is decrypted (unc_bufin_next_slow -> unc_crypt_apply)
# only in a format that sets a cipher up: the files that call one of
# unc_crypt_zip/sit/cpt/packit_*/rc4/xor/pf/winzip_aes. check_rules()
# fails if either list stops matching the source.
ENVELOPES = ["gzip", "compressz", "lz4", "pf", "macbinary", "appledouble",
             "btoa", "uu", "binhex", "b64"]
CIPHER_FILES = {"fmt_arc.c": "arc", "fmt_cpt.c": "cpt", "fmt_exo.c": "zip",
                "fmt_sit5.c": "sit5", "fmt_packit.c": "packit",
                "fmt_pf.c": "pf", "fmt_sit.c": "sit"}
CIPHERED = sorted(CIPHER_FILES.values())
# Each rule: (edge kind: None any, "" direct, "*" any indirect, or a
# class; caller's file; caller regex; target's file; target regex; bits
# it sets; bits of which it needs one; bits it may not have).
JOINSET, MIMESET, ADDRSET, PEEKSET, CRYPTSET, MIMEWALK = \
    8, 16, 32, 64, 128, 256
ANYSET = JOINSET | MIMESET | ADDRSET
EDGE_RULES = [
    ("scheme.extract", None, None, None, r"^unc_mime_extract$",
     MIMESET, 0, 0),
    ("scheme.extract", None, None, None, r"^unc_(cpt|zip)_extract$",
     ADDRSET, 0, 0),
    ("", "unc_segment.c", r"^unc_extract_segments$", None,
     r"^unc_sitseg_emit$", JOINSET, 0, 0),
    ("hdr", None, None, None, None, 0, MIMESET, 0),
    ("seek_part", None, None, None, None, 0, ADDRSET, 0),
    ("skip", None, None, None, None, 0, ADDRSET, 0),
    ("part_size", None, None, None, None, 0, ADDRSET, 0),
    ("payload", None, None, None, None, 0, JOINSET, 0),
    ("stored_crc", None, None, None, None, 0, JOINSET, 0),
    ("crc_fold", None, None, None, None, 0, JOINSET, 0),
    ("*", None, None, "unc_segment.c", r"^seg_(read|seek|tell|size)$", 0,
     ANYSET, 0),
    ("", "unc_peek.c", r"^unc_envelope_peek$", None, None, PEEKSET, 0, 0),
    ("*", None, None, "unc_peek.c", r"^p[hw]_", 0, PEEKSET, 0),
    ("extract", None, None, None,
     r"^unc_(?!(%s)_extract$)" % "|".join(ENVELOPES), 0, 0, PEEKSET),
    (None, None, None, None, r"^unc_(%s)_extract$" % "|".join(CIPHERED),
     CRYPTSET, 0, 0),
    ("", None, r"^unc_bufin_next_slow$", None, r"^unc_crypt_apply$", 0,
     CRYPTSET, 0),
    # MIME's relay is the progress callback only under the MIME walk
    (None, None, None, None, r"^unc_mime_extract$", MIMEWALK, 0, 0),
    ("tick", None, None, "fmt_mime.c", None, 0, MIMEWALK, 0),
]

# Call sites whose class is not their last member's: (file, expression).
SITE_CLASS = {
    ("unc_peek.c", "w->io->read"): "base.read",
    ("unc_peek.c", "w->io->seek"): "base.seek",
    ("unc_peek.c", "w->io->tell"): "base.tell",
    ("unc_peek.c", "io->seek"): "base.seek",   # unc_envelope_peek's own io
    ("unc_peek.c", "hio.seek"): "peekhead.seek",
    ("unc_segment.c", "sc->reader"): "scheme.extract",
    ("unc_segment.c", "j->cur.read"): "base.read",
    ("unc_segment.c", "j->cur.seek"): "base.seek",
}
CLASSES["peekhead.seek"] = ["unc_peek.c:ph_seek"]
# Direct calls that stand for a class: in the shipped build every reader is
# one dispatch on UncCtx.fmt (mac/ovl_shim.c), so the engine's two calls
# through a pointer are calls to ovl_run, from unc_run_file (a format read
# as a file) and from unc_run (a set's reader, an alias). Each is followed
# as the class its pointer was: (file, caller, callee) -> class.
DIRECT_CLASS = {
    ("ovl_shim.c", "unc_run_file", "ovl_run"): "extract",
    ("ovl_shim.c", "unc_run", "ovl_run"): "scheme.extract",
}
# Indirect calls this tool knows it does not follow, by callee expression.
NOT_FOLLOWED = {
    "RETRO68_RELOCATE": "the startup relocation, before main",
    "e@macextract_mac.c": "the shell's dialog images (ovl_destdlg, "
                          "ovl_segsetup), not compiled here",
    "e@ovl_load_eager.c": "the release's plan, in the set's setup image "
                          "(ovl_segsetup), not compiled here; it runs "
                          "before the engine",
}
# Address-taken functions no class needs to list: (file the address is
# taken in, regex on the function's name, why).
TAKEN_OK = [
    ("ovl_shim.c", r".", "the host vector gOvlFns: the forwards' targets"),
    ("ovl_codecs.c", r".", "the codecs' exports, patched into the vector"),
    ("ovl_zipold.c", r".", "zip's old methods' exports, into the vector"),
    ("macextract_mac.c", r"^(Seg|My|unc_)",
     "gSegSetupFns: the set-up dialog image's host table"),
    ("macextract_mac.c", r"^[A-Z0-9]+$", "a Toolbox filter or user-item "
     "proc (pascal, upper case): called by the ROM, not modelled"),
    ("mac_start.c", r".", "the startup's own entry"),
]

def die(msg):
    sys.stderr.write("stack_depth: %s\n" % msg)
    sys.exit(2)


def run(cmd, **kw):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, **kw)
    if r.returncode:
        die("%s failed:\n%s" % (" ".join(cmd[:3]), r.stderr[-2000:]))
    return r.stdout


# ---------------------------------------------------------------- the build
def check_rules():
    """ENVELOPES and CIPHER_FILES are facts about the source; re-read them."""
    t = open(os.path.join(ROOT, "src", "unc_sniff.c")).read()
    m = re.search(r"unc_sniff_envelope_order\[\] = \{(.*?)\};", t, re.S)
    got = [p.replace("applesingle", "appledouble") for p in
           re.findall(r"unc_(\w+)_probe", m.group(1))]
    if sorted(got) != sorted(ENVELOPES):
        die("unc_sniff.c's envelope probes are %s; ENVELOPES says %s"
            % (sorted(got), sorted(ENVELOPES)))
    setup = re.compile(r"\bunc_crypt_(zip|sit|cpt|packit_des|packit_xor|rc4|"
                       r"xor|pf|winzip_aes)\s*\(")
    files = sorted(f for f in os.listdir(os.path.join(ROOT, "src"))
                   if f.endswith(".c") and f != "unc_crypt.c" and
                   setup.search(open(os.path.join(ROOT, "src", f)).read()))
    if files != sorted(CIPHER_FILES):
        die("the files that set a cipher up are %s; CIPHER_FILES says %s"
            % (files, sorted(CIPHER_FILES)))


def check_flags():
    """The two flag lists above must still be what the build passes."""
    t = open(os.path.join(ROOT, "mac", "CMakeLists.txt")).read()
    m = re.search(r"target_compile_options\(MacExtract PRIVATE(.*?)\)\n", t,
                  re.S)
    got = [w for line in m.group(1).splitlines()
           for w in [line.split("#")[0].strip()] if w
           for w in w.split() if w.startswith("-") and "$" not in w]
    want = [f for f in RESIDENT_FLAGS
            if f not in ("-O3", "-DNDEBUG", "-DUNC_AT_OVERLAY")]
    if got != want:
        die("mac/CMakeLists.txt's options are %s, this tool builds with %s"
            % (got, want))
    s = open(os.path.join(ROOT, "tools", "overlay", "mkoverlay.sh")).read()
    m = re.search(r'ovl_cc\(\) \{\n(.*?)\n\}', s, re.S)
    got = [w for w in m.group(1).replace("\\\n", " ").split()
           if w.startswith("-") and not w.startswith("-I")
           and w not in ("-c", "-o")]
    if got != OVERLAY_FLAGS:
        die("mkoverlay.sh's ovl_cc passes %s, this tool builds with %s"
            % (got, OVERLAY_FLAGS))


def overlay_images():
    """image -> [sources], parsed from mac/CMakeLists.txt's mkoverlay rules."""
    t = open(os.path.join(ROOT, "mac", "CMakeLists.txt")).read()
    out = {}
    for m in re.finditer(r"add_custom_command\(\s*OUTPUT\s+\$\{CMAKE_CURRENT_"
                         r"BINARY_DIR\}/ovl_(\w+)\.r(.*?)\n\s*DEPENDS", t,
                         re.S):
        mm = re.search(r"mkoverlay\.sh\s+\S+\.r\s+(.*)", m.group(2), re.S)
        if mm:
            out[m.group(1)] = [s.replace("${ENGINE_DIR}/", "")
                               .replace("${CMAKE_CURRENT_BINARY_DIR}/", "GEN/")
                               for s in mm.group(1).split()]
    if len(out) < 17:
        die("found %d overlay images in mac/CMakeLists.txt, expected 17"
            % len(out))
    return out


def resident_engine():
    """src/*.c minus every file mac/CMakeLists.txt filters out of the link."""
    t = open(os.path.join(ROOT, "mac", "CMakeLists.txt")).read()
    gone = set(re.findall(r'list\(FILTER ENGINE_SRC EXCLUDE REGEX "(\w+)'
                          r'\\\\\.c\$"\)', t))
    srcs = sorted(f for f in os.listdir(os.path.join(ROOT, "src"))
                  if f.endswith(".c"))
    if not gone:
        die("no ENGINE_SRC filters found in mac/CMakeLists.txt")
    return ["src/" + f for f in srcs if f[:-2] not in gone]


class Unit:
    def __init__(self, image, src, flags, inc, out):
        self.image, self.src, self.flags, self.inc = image, src, flags, inc
        base = "%s__%s" % (image, os.path.basename(src)[:-2])
        self.obj = os.path.join(out, base + ".o")
        self.ci = os.path.join(out, base + ".ci")
        self.out, self.base = out, base


def compile_unit(u, gen):
    src = u.src.replace("GEN/", gen + "/")
    src = src if os.path.isabs(src) else os.path.join(ROOT, src)
    cmd = [TOOL + "gcc", "-c"] + u.flags + ["-I" + os.path.join(ROOT, i)
                                            for i in u.inc]
    cmd += ["-I" + gen, "-fcallgraph-info=su", "-dumpdir", u.out + "/",
            "-dumpbase", u.base, src, "-o", u.obj]
    run(cmd, cwd=ROOT)


def build(config, out, with_shell):
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    gen = os.path.join(out, "gen")
    os.makedirs(gen)
    run([sys.executable, os.path.join(ROOT, "tools", "overlay",
                                      "mkforwards.py"), gen])
    units = []
    if config == "host":
        for f in sorted(os.listdir(os.path.join(ROOT, "src"))):
            if f.endswith(".c"):
                units.append(Unit("engine", "src/" + f, HOST_FLAGS,
                                  ["include", "src"], out))
        for f in ("inflate", "inftrees", "inffast", "adler32", "crc32",
                  "zutil"):
            units.append(Unit("engine", "third_party/zlib/%s.c" % f,
                              HOST_FLAGS, ["include", "src"], out))
        images = {}
    else:
        check_flags()
        images = overlay_images()
        inc = ["tools/overlay", "include", "src", "third_party/zlib"]
        for s in resident_engine() + GLUE_SRC + (
                SHELL_SRC if with_shell else []):
            units.append(Unit("resident", s, RESIDENT_FLAGS, inc, out))
        for img, srcs in sorted(images.items()):
            for s in srcs + ["tools/overlay/ovl_rt.c"]:
                units.append(Unit(img, s, OVERLAY_FLAGS,
                                  ["tools/overlay", "include", "src"], out))
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as ex:
        list(ex.map(lambda u: compile_unit(u, gen), units))
    return units, images


# ------------------------------------------------------------ the reading
NODE = re.compile(r'^node: \{ title: "([^"]+)" label: "([^"]*)"(.*)\}$')
EDGE = re.compile(r'^edge: \{ sourcename: "([^"]+)" targetname: "([^"]+)"'
                  r'(?: label: "([^"]*)")? \}$')


class Fn:
    __slots__ = ("key", "image", "unit", "name", "su", "kind", "link",
                 "calls", "tail", "indirect")

    def __init__(self, key, image, unit, name):
        self.key, self.image, self.unit, self.name = key, image, unit, name
        self.su, self.kind, self.link = 0, "static", False
        self.calls, self.tail, self.indirect = [], set(), []

    def frame(self):
        return self.su + 4 + (4 if self.link else 0)


def read_unit(u):
    """Functions defined in one object: frames, edges, indirect sites."""
    fns, local = {}, {}
    ext_edges = []
    for line in open(u.ci):
        m = NODE.match(line.strip())
        if m:
            title, label, rest = m.groups()
            if "ellipse" in rest:
                continue
            name = title.split(":")[-1]
            f = Fn(None, u.image, u, name)
            mm = re.search(r"\\n(\d+) bytes \(([^)]*)\)", label)
            if mm is None and "triangle" in rest:
                # An alias: another name for a function defined here, with
                # no frame of its own (mac/ovl_shim.c's decoder names, each
                # ovl_run since 2026-11-11). Its one edge is a tail call.
                f.kind = "alias"
            else:
                f.su, f.kind = int(mm.group(1)), mm.group(2)
            fns[title] = f
            local[name] = title
            continue
        m = EDGE.match(line.strip())
        if m:
            ext_edges.append(m.groups())
        elif line.startswith("edge:"):
            die("%s: cannot read %r" % (u.ci, line))
    for s, t, loc in ext_edges:
        f = fns.get(s)
        if f is None:
            die("%s: edge from undefined %s" % (u.ci, s))
        if t == "__indirect_call":
            if not loc:
                die("%s: an indirect call in %s with no source position"
                    % (u.ci, s))
            f.indirect.append(loc)
        else:
            f.calls.append(t)
    # LINK, tail calls and address-taken functions come from the object.
    dis = run([TOOL + "objdump", "-dr", u.obj])
    cur, sec, first = None, "", 0
    jsr_to, jmp_to = {}, {}
    taken = []
    ins = ops = ""
    for line in dis.splitlines():
        if line.startswith("Disassembly of section"):
            sec = line.split()[-1].rstrip(":")
            cur = None
            continue
        if "macsbug" in sec:
            continue
        m = re.match(r"^[0-9a-f]+ <(.+)>:$", line)
        if m:
            cur, first = m.group(1), 0
            continue
        m = re.match(r"^\s+[0-9a-f]+:\t[0-9a-f ]+\t(\S+)\s*(.*)$", line)
        if m and cur:
            ins, ops = m.group(1), m.group(2)
            if first < 2 and ins == "linkw" and cur in local:
                fns[local[cur]].link = True
            first += 1
            continue
        m = re.match(r"^\s+[0-9a-f]+: (R_68K_\w+)\s+(\S+)$", line)
        if m and cur:
            sym = m.group(2).split("+")[0]
            sym = sym[len(".text."):] if sym.startswith(".text.") else sym
            if ins in ("jsr", "jbsr", "bsrw", "bsrl", "bsrs"):
                jsr_to.setdefault(cur, set()).add(sym)
            elif ins in ("jmp", "jra", "braw", "bral", "bras"):
                jmp_to.setdefault(cur, set()).add(sym)
            elif re.search(r",%(a[0-7]|fp|d[0-7])$", ops) and \
                    ins in ("lea", "moveal", "movel"):
                taken.append((cur, sym, "reg"))   # a call through a register?
            elif re.search(r",%(sp|fp)@", ops) and ins == "movel":
                taken.append((cur, sym, "stack"))  # or kept on the stack
            else:
                taken.append((cur, sym, "mem"))
    for f in fns.values():
        for t in f.calls:
            n = t.split(":")[-1]
            if f.kind == "alias" or (n in jmp_to.get(f.name, ()) and
                                     n not in jsr_to.get(f.name, ())):
                f.tail.add(t)
    # data sections: relocations from initialised tables
    for line in run([TOOL + "objdump", "-r", u.obj]).splitlines():
        m = re.match(r"RELOCATION RECORDS FOR \[(.*)\]:", line)
        if m:
            sec = m.group(1)
            continue
        m = re.match(r"^[0-9a-f]+ (R_68K_\w+)\s+(\S+)$", line)
        if m and not sec.startswith(".text") and "debug" not in sec \
                and "macsbug" not in sec:
            sym = m.group(2).split("+")[0]
            sym = sym[len(".text."):] if sym.startswith(".text.") else sym
            taken.append(("<%s>" % sec, sym, "mem"))
    return fns, taken


def source_readers():
    """The extractors src/unc_engine.c's F() rows name, and the readers
    src/unc_segment.c's seg_schemes rows name with SEG_READ()."""
    eng = open(os.path.join(ROOT, "src", "unc_engine.c")).read()
    seg = open(os.path.join(ROOT, "src", "unc_segment.c")).read()
    files = re.findall(r"\bF\(\s*UNC_FORMAT_\w+\s*,\s*\"[^\"]*\"\s*,\s*\d\s*,"
                       r"\s*(\w+)\s*\)", eng)
    sets = re.findall(r"\{\s*UNC_FORMAT_\w+\s*,[^{}\n]*SEG_READ\(\s*(\w+)\s*\)",
                      seg)
    if len(files) < 30 or len(sets) < 4:
        die("source_readers: parsed %d extractors and %d set readers — the "
            "tables changed shape" % (len(files), len(sets)))
    return files, sets


def callee_expr(loc):
    """The callee expression of the indirect call at file:line:col."""
    path, line, col = loc.rsplit(":", 2)
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    with open(p) as fh:
        text = fh.readlines()[int(line) - 1][int(col) - 1:]
    m = re.match(r"\(?\s*\*?\s*([A-Za-z_][\w.\->\[\]]*)\s*\)?\s*\(", text)
    if not m:
        die("cannot read the callee at %s: %r" % (loc, text[:60]))
    expr = m.group(1)
    last = re.split(r"->|\.", re.sub(r"\[[^\]]*\]", "", expr))[-1]
    return expr, last


# ------------------------------------------------------------ the graph
class Graph:
    def __init__(self, config, units, images):
        self.config = config
        self.fns = {}            # key -> Fn; key = (image, .ci title)
        self.by_name = {}        # name -> [keys]
        self.taken = []          # (image, unit file, function, sym, how)
        self.notes = set()       # what was met and not followed
        self.edges = {}          # key -> [(key, tail?, why)]
        self.unresolved = set()
        for u in units:
            fns, taken = read_unit(u)
            for title, f in fns.items():
                f.key = (u.image, title)
                self.fns[f.key] = f
                self.by_name.setdefault(f.name, []).append(f.key)
            for g, sym, how in taken:
                self.taken.append((u.image, os.path.basename(u.src), g,
                                   sym, how))
        for name, (su, calls) in LIBRARY.items():
            f = Fn(("lib", name), "lib", None, name)
            f.su, f.calls = su, calls
            self.fns[f.key] = f
            self.by_name.setdefault(name, []).append(f.key)

    # -- naming
    @staticmethod
    def file_of(f):
        return os.path.basename(f.unit.src) if f.unit else ""

    def is_shell(self, f):
        return f.unit is not None and f.unit.src in SHELL_SRC

    def is_forward(self, f):
        return f.unit is not None and "ovl_forwards" in f.unit.src

    def label(self, k):
        f = self.fns[k]
        img = "" if f.image in ("engine", "resident", "lib") else f.image + ":"
        return img + f.name

    def lookup(self, spec, image):
        """Keys for a class target or a call: "name" or "file.c:name"."""
        shell = spec.startswith(SH)
        spec = spec[len(SH):] if shell else spec
        fname, _, name = spec.rpartition(":")
        keys = [k for k in self.by_name.get(name, ())
                if not fname or self.file_of(self.fns[k]) == fname]
        keys = [k for k in keys if not self.is_forward(self.fns[k])]
        same = [k for k in keys if k[0] == image]
        return same or keys

    def defining(self, name, image):
        """Where a global call from `image` lands, inside its own link."""
        k = (image, name)
        if k in self.fns:
            return [k]
        if ("lib", name) in self.fns:
            return [("lib", name)]
        return []

    # -- edges
    def resolve(self, with_shell):
        # The two auto-filled classes.
        for img, fil, g, sym, how in self.taken:
            if how != "mem":
                continue
            if re.match(r"unc_\w+_extract$", sym):
                if fil == "unc_engine.c":
                    CLASSES["extract"].append(sym)
                elif fil == "unc_segment.c":
                    CLASSES["scheme.extract"].append(sym)
            if fil == "unc_sniff.c" and re.match(r"unc_\w+_probe", sym):
                CLASSES["order"].append(sym)
        # The rows themselves, which the shipped build no longer takes the
        # addresses of (DIRECT_CLASS).
        CLASSES["extract"] += source_readers()[0]
        CLASSES["scheme.extract"] += source_readers()[1]
        for k in CLASSES:
            CLASSES[k] = sorted(set(CLASSES[k]))
        listed = set()
        for k, targets in CLASSES.items():
            for t in targets:
                if t.startswith(SH) and not with_shell:
                    continue
                found = self.lookup(t, None)
                glue = t.split(":")[0] in [os.path.basename(x)
                                           for x in GLUE_SRC]
                if not found and not ((t.startswith(SH) or glue) and
                                      self.config == "host"):
                    die("class %r names %s, which no object defines"
                        % (k, t))
                listed.update(found)
        self.check_taken(listed)
        clones = {}
        for key, f in list(self.fns.items()):
            out = []
            for t in f.calls:
                tail = t in f.tail
                cls = DIRECT_CLASS.get((self.file_of(f), f.name,
                                        t.split(":")[-1]))
                if cls:
                    for tt in CLASSES[cls]:
                        out += [(x, tail, cls)
                                for x in self.lookup(tt, f.image)]
                    continue
                if ":" in t:
                    out.append(((f.image, t), tail, ""))
                    continue
                d = self.defining(t, f.image)
                if not d:
                    if f.image == "lib":
                        d = [("lib", t)]
                    else:
                        self.unresolved.add(t)
                        continue
                out += [(x, tail, "") for x in d]
            for loc in f.indirect:
                out += [(x, False, why) for x, why in
                        self.indirect(f, loc, with_shell)]
            self.edges[key] = out
        self.clone_decoder_shims()

    def check_taken(self, listed):
        bad = []
        for img, fil, g, sym, how in self.taken:
            keys = [k for k in self.by_name.get(sym, ())
                    if k[0] == img and k[0] != "lib"]
            if not keys:
                continue           # data, or a function of another image
            caller = [k for k in self.by_name.get(g, ()) if k[0] == img]
            if how in ("reg", "stack") and any(sym in [c.split(":")[-1] for c in
                                            self.fns[c0].calls]
                                    for c0 in caller):
                continue           # loaded into a register to be called
            if any(k in listed for k in keys):
                continue
            if any(fil == ok[0] and re.search(ok[1], sym)
                   for ok in TAKEN_OK):
                continue
            if self.is_shell(self.fns[keys[0]]) and not self.with_shell:
                continue
            bad.append("%s's %s takes the address of %s" % (fil, g, sym))
        if bad:
            die("address-taken functions no class lists:\n  " +
                "\n  ".join(sorted(set(bad))))

    def indirect(self, f, loc, with_shell):
        expr, last = callee_expr(loc)
        fil = self.file_of(f)
        if self.is_forward(f):
            # g_ovl_fns->X: the vector entry for the forward's own name.
            n = f.name
            if n in mkforwards.CODECS and f.image != "codecs":
                img = "codecs"
            elif n in mkforwards.ZIPOLD and f.image != "zipold":
                img = "zipold"
            else:
                img = "resident"
            k = (img, n)
            if k not in self.fns:
                die("forward %s in %s: no %s in %s" % (n, f.image, n, img))
            return [(k, "vector")]
        if fil == "ovl_shim.c" and last in ("e", "OVL_CALL", "VOID_KEYED",
                                            "INT_KEYED_AL"):
            if f.name in SHARED_SHIMS:
                return []          # per shim: clone_decoder_shims()
            if f.name == "ovl_patched":
                return [(self.dispatch(img, None), "export")
                        for img in ("codecs", "zipold")]
            return [(self.dispatch(self.image_of(f.name), f.name), "image")]
        for nf in (last + "@" + fil, last):
            if nf in NOT_FOLLOWED:
                self.notes.add("%s at %s: %s" % (expr, loc, NOT_FOLLOWED[nf]))
                return []
        parts = re.split(r"->|\.", re.sub(r"\[[^\]]*\]", "", expr))
        key = parts[-2] + "." + last if len(parts) > 1 and \
            parts[-2] + "." + last in CLASSES else last
        key = SITE_CLASS.get((fil, expr), key)
        if key not in CLASSES:
            die("indirect call `%s(` at %s is in no class" % (expr, loc))
        out = []
        for t in CLASSES[key]:
            if t.startswith(SH) and not with_shell:
                continue
            out += [(x, key) for x in self.lookup(t, f.image)]
        return out

    def image_of(self, name):
        imgs = sorted(set(k[0] for k in self.by_name.get(name, ())
                          if k[0] not in ("resident", "lib")
                          and not self.is_forward(self.fns[k])))
        if len(imgs) != 1:
            die("shim %s: defined in images %s" % (name, imgs))
        return imgs[0]

    def dispatch(self, img, name):
        """ovl_main of `img`, as called for `name` (None: the export call)."""
        k = ("dispatch", img, name or "")
        if k in self.fns:
            return k
        base = self.fns.get((img, "ovl_main"))
        if base is None:
            die("image %s has no ovl_main" % img)
        f = Fn(k, img, base.unit, "ovl_main")
        f.su, f.link, f.kind = base.su, base.link, base.kind
        self.fns[k] = f
        self.edges[k] = [((img, name), False, "")] if name else []
        return k

    def clone_decoder_shims(self):
        """DECODER(fn): fn -> ovl_run -> ovl_main -> fn in its image, and
        the same for every helper in SHARED_SHIMS: a clone of the helper
        per shim that calls it, ending in the image(s) that shim reaches."""
        for helper in SHARED_SHIMS:
            runs = [k for k in self.by_name.get(helper, ())
                    if k[0] == "resident"]
            if not runs:
                continue
            run = runs[0]
            for key, f in list(self.fns.items()):
                if self.file_of(f) != "ovl_shim.c" or key == run:
                    continue
                es = self.edges.get(key, [])
                if not any(e[0] == run for e in es):
                    continue
                ck = ("clone", helper, f.name)
                c = Fn(ck, "resident", self.fns[run].unit, helper)
                base = self.fns[run]
                c.su, c.link, c.kind = base.su, base.link, base.kind
                self.fns[ck] = c
                targets = SHARED_SHIMS[helper].get(f.name) or \
                    [(self.image_of(f.name), f.name)]
                self.edges[ck] = list(self.edges[run]) + [
                    (self.dispatch(img, name), False, "image")
                    for img, name in targets]
                self.edges[key] = [(ck if e[0] == run else e[0], e[1], e[2])
                                   for e in es]

    # -- depth
    def step(self, mask, k, c, why):
        """The context bits after following k -> c, or None if the path is
        one the code cannot take: a wrapping callback under itself, or a
        scheme's callback in a set of another scheme (EDGE_RULES)."""
        fk, fc = self.fns[k], self.fns[c]
        for cls, kfil, krx, cfil, crx, sets, needs, forbids in EDGE_RULES:
            if cls == "*":
                if not why:
                    continue
            elif cls is not None and why != cls:
                continue
            if (kfil and self.file_of(fk) != kfil) or \
                    (krx and not re.search(krx, fk.name)) or \
                    (cfil and self.file_of(fc) != cfil) or \
                    (crx and not re.search(crx, fc.name)):
                continue
            if (needs and not mask & needs) or mask & forbids:
                return None
            mask |= sets
        g = WRAPPERS.get(self.file_of(self.fns[c])) \
            if why in WRAPPED else None
        if g is None:
            return mask
        if mask & g:
            return None
        return mask | g

    def depth(self):
        """Longest path, over (function, wrappers open) states."""
        memo, best, state = {}, {}, {}
        for root in list(self.fns):
            if (root, 0) in memo:
                continue
            stack = [((root, 0), 0)]
            while stack:
                st, i = stack.pop()
                k, mask = st
                if i == 0:
                    if st in memo:
                        continue
                    state[st] = 1
                es = self.edges.get(k, [])
                if i < len(es):
                    stack.append((st, i + 1))
                    c, tail, why = es[i]
                    if c not in self.fns:
                        continue
                    m2 = self.step(mask, k, c, why)
                    if m2 is None:
                        continue
                    if state.get((c, m2)) == 1:
                        die("a cycle: %s -> %s (recursion, or a class "
                            "wider than the code)" % (self.label(k),
                                                      self.label(c)))
                    if (c, m2) not in memo:
                        stack.append(((c, m2), 0))
                    continue
                f = self.fns[k]
                d, via = f.frame(), None
                for c, tail, why in es:
                    m2 = self.step(mask, k, c, why) if c in self.fns else None
                    if m2 is None or (c, m2) not in memo:
                        continue
                    v = memo[(c, m2)] + (0 if tail else f.frame())
                    if v > d:
                        d, via = v, ((c, m2), tail, why)
                memo[st], best[st], state[st] = d, via, 2
        self.memo = {k: memo[(k, 0)] for k in self.fns if (k, 0) in memo}
        self.smemo, self.best = memo, best

    def chain(self, k):
        out, st = [], (k, 0)
        while st is not None:
            out.append(st)
            v = self.best.get(st)
            st = v[0] if v else None
        return out

    def show(self, k, indent="  "):
        lines = []
        for st in self.chain(k):
            x = st[0]
            f = self.fns[x]
            v = self.best.get(st)
            how = ""
            if v and v[1]:
                how = "  (tail call: frame not kept)"
            elif v and v[2]:
                how = "  (through %s)" % v[2]
            lines.append("%s%-40s %5d B  [su %d%s]%s" % (
                indent, self.label(x), f.frame(), f.su,
                "+link" if f.link else "", how))
        return "\n".join(lines)


SELFTEST_C = """
int ext(int, int, int);
int leaf(int a) { return a + 1; }
int pushes(int a) { volatile char b[8]; b[0] = a; return ext(b[a], 1, 2); }
int linked(int a) { int x[4]; x[0] = a; return ext(a, (int)x, 3) + 1; }
int noargs(void);
int tail(void) { return noargs(); }
"""


def selftest(out):
    """What a frame's bytes are made of, on this compiler, re-measured:
    -fstack-usage counts locals and pushed arguments, not the return
    address and not the frame pointer a LINK saves. If GCC ever starts
    counting either, this fails rather than double-counting."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "selftest.c")
    with open(src, "w") as fh:
        fh.write(SELFTEST_C)
    u = Unit("engine", src, HOST_FLAGS, [], out)
    compile_unit(u, out)
    fns, _ = read_unit(u)
    got = {f.name: (f.su, f.link, sorted(f.tail)) for f in fns.values()}
    want = {"leaf": (0, False, []),       # rts only: return address not in
            "pushes": (20, False, []),    # 8 B of locals + 3 pushes
            "linked": (28, True, []),     # LINK #-16 + 3 pushes; FP not in
            "tail": (0, False, ["noargs"])}  # a JRA, no frame of its own
    for k, v in want.items():
        if got.get(k) != v:
            die("selftest: %s is %s, expected %s" % (k, got.get(k), v))
    print("stack_depth: selftest passed (%s)" % ", ".join(
        "%s su %d%s" % (k, v[0], " +link" if v[1] else "")
        for k, v in sorted(want.items())))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true",
                    help="re-measure what -fstack-usage counts, then exit")
    ap.add_argument("--config", choices=("shipped", "host"),
                    default="shipped")
    ap.add_argument("--shell", action="store_true",
                    help="add the Mac shell and its callbacks (shipped)")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0,
                    help="exit 1 if the engine's deepest chain exceeds this")
    ap.add_argument("--extra-frame", action="append", default=[],
                    metavar="FUNC=BYTES")
    ap.add_argument("--extra-edge", action="append", default=[],
                    metavar="CALLER=CALLEE")
    ap.add_argument("--out", default=os.path.join(ROOT, ".tmp",
                                                  "stack_depth"))
    a = ap.parse_args()
    if a.selftest:
        selftest(os.path.join(a.out, "selftest"))
        return 0
    if a.shell and a.config != "shipped":
        die("--shell needs --config shipped")
    check_rules()
    out = os.path.join(a.out, a.config + ("-shell" if a.shell else ""))
    units, images = build(a.config, out, a.shell)
    g = Graph(a.config, units, images)
    g.with_shell = a.shell
    for spec in a.extra_frame:
        name, b = spec.split("=")
        ks = g.by_name.get(name)
        if not ks:
            die("--extra-frame: no function %s" % name)
        for k in ks:
            g.fns[k].su += int(b)
    g.resolve(a.shell)
    for spec in a.extra_edge:
        x, y = spec.split("=")
        xs, ys = g.by_name.get(x), g.by_name.get(y)
        if not xs or not ys:
            die("--extra-edge: %s or %s not found" % (x, y))
        for k in xs:
            g.edges[k].append((ys[0], False, "injected"))
    g.depth()

    engine = [k for k, f in g.fns.items()
              if not g.is_shell(f) and f.image != "lib"]
    top = max(engine, key=lambda k: g.memo.get(k, 0))
    print("stack_depth: --config %s%s, %d functions, %d objects"
          % (a.config, " --shell" if a.shell else "", len(g.fns), len(units)))
    print("\nThe engine's deepest chain: %d B" % g.memo[top])
    print(g.show(top))
    su_sum = sum(g.fns[x[0]].su for x in g.chain(top))
    print("  (-fstack-usage figures alone: %d B, the way FORMATS.md *Stack* "
          "summed them)" % su_sum)

    print("\nEach format's extractor, from its own entry:")
    ext = {}
    for k, f in g.fns.items():
        if re.match(r"unc_\w+_extract$", f.name) and not g.is_forward(f) \
                and f.unit and "ovl_shim" not in f.unit.src and k[0] != "dispatch":
            ext[f.name] = max(ext.get(f.name, (0, None)), (g.memo[k], k))
    for name, (d, k) in sorted(ext.items(), key=lambda x: -x[1][0])[:a.top]:
        ch = g.chain(k)
        print("  %-28s %5d B  %s" % (name, d, " > ".join(
            g.fns[x[0]].name for x in ch[1:5]) + (" ..." if len(ch) > 5 else "")))

    print("\nLargest single frames:")
    seen = set()
    for k in sorted(engine, key=lambda k: -g.fns[k].frame()):
        f = g.fns[k]
        if (f.name, f.su) in seen or k[0] in ("clone", "dispatch"):
            continue
        seen.add((f.name, f.su))
        print("  %-40s %5d B  %s" % (g.label(k), f.frame(), g.file_of(f)))
        if len(seen) >= a.top:
            break
    if a.shell:
        shell = [k for k, f in g.fns.items() if g.is_shell(f)]
        for name in ("RunExtract", "ExtractOne", "main"):
            ks = [k for k in shell if g.fns[k].name.split(".")[0] == name]
            for k in ks:
                print("\nFrom the shell's %s: %d B" % (g.fns[k].name,
                                                       g.memo[k]))
                print(g.show(k))
        big = [k for k in shell if g.fns[k].frame() >= 256]
        print("\nShell frames of 256 B or more:")
        for k in sorted(big, key=lambda k: -g.fns[k].frame()):
            print("  %-40s %5d B" % (g.label(k), g.fns[k].frame()))
    dyn = [g.label(k) for k, f in g.fns.items()
           if "dynamic" in f.kind and "bounded" not in f.kind]
    if dyn:
        print("\nWARNING: unbounded (alloca/VLA) frames: %s" % ", ".join(dyn))
    if g.unresolved:
        print("\nCalls to code not built here (charged nothing): %s"
              % ", ".join(sorted(g.unresolved)))
    if g.notes:
        print("\nIndirect calls not followed:")
        for n in sorted(g.notes):
            print("  " + n)
    if a.limit and g.memo[top] > a.limit:
        print("\nstack_depth: FAILED — %d B exceeds --limit %d"
              % (g.memo[top], a.limit))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
