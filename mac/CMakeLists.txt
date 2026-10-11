# Build the Macintosh shell with Retro68:
#
#   cmake -B build-mac -S mac \
#     -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
#   cmake --build build-mac
#
# Produces MacExtract.APPL/.bin/.dsk (mountable in Mini vMac; copy the
# application onto a System 6..9 boot disk to run). See tools/vmac/README.md.
cmake_minimum_required(VERSION 3.10)
project(macextract_mac C)

set(ENGINE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/..)
file(GLOB ENGINE_SRC ${ENGINE_DIR}/src/*.c)
file(GLOB ZLIB_SRC ${ENGINE_DIR}/third_party/zlib/*.c)

# OVERLAYS ARE THE BUILD. The engine's decoders and ciphers are flat
# position-independent images carried in 'OVLY' resources, so their CODE is
# not resident; one image per format family, so decoding the most expensive
# archive has the least code in memory. Compact Pro and DiskDoubler share one
# because fmt_dd calls fmt_cpt's fork readers. This is what `dist/` ships and
# what every tier is measured on, as of 2026-09-25.
#
# UNC_OVL_RESIDENT — the old monolithic application, every decoder linked in.
# NOT shipped and not the default, kept because it is the CONTROL every budget
# figure rests on: with all sixteen images resident the engine is granted the
# same heap whatever it decodes, and that is what says the 84-103 KB the
# overlay build gains belongs to the mechanism rather than to a month of other
# work (FORMATS.md, *Overlays*). An instrument, not a fallback.
#
# UNC_OVL_LAZY — WHEN an image is read, which is a whole loader:
#
#   unset (default)  EAGER: all sixteen in ONE resource, read at launch while
#                    the boot disk is certainly in, and everything the sniffed
#                    format cannot want released before the engine takes its
#                    budget. mac/ovl_load_eager.c, bundle by mkbundle.py.
#   set              LAZY: one resource per image, read when a format turns
#                    out to want it — no launch cost, one disk access per
#                    format AFTER the archive has been chosen, which on a
#                    one-drive Mac Plus is when its floppy may be out.
#                    mac/ovl_load_lazy.c, the per-image .r files linked.
#
# A boolean rather than a name, because every harness here passes build
# switches as `-D NAME` and sets them to "1" (tools/vmac/run.py,
# build_autotest_app). A lifetime spelled as a VALUE could not be driven from
# any of them, so the loader that is not the default could never be run on a
# Macintosh — which is the one thing a variant has to stay able to do.
#
# Both share every image, the relocation trailer, the instruction-cache flush
# and all ~340 lines of dispatch in mac/ovl_shim.c; they were two branches
# until 2026-09-25 and 21 of the 24 files under tools/overlay/ were
# byte-identical between them. FORMATS.md, *Overlays*, prices the two.
set(OVERLAY_R "")
set(OVERLAY_SHIM "")
if(DEFINED ENV{UNC_AT_OVERLAY})
    # Was the switch that turned overlays ON, until they became the build.
    # Accepted and ignored rather than failed: every harness command line and
    # half the write-ups in this repository pass it, and what it asked for is
    # what it now gets.
    message(STATUS "overlay: UNC_AT_OVERLAY is the default since 2026-09-25 "
                   "— switch ignored")
endif()
set(OVL_COMPILE_DEFS "")
if(DEFINED ENV{UNC_OVL_RESIDENT})
    message(STATUS "overlay: RESIDENT control build — no images, "
                   "not what dist/ ships")
else()
    set(OVL_COMPILE_DEFS "-DUNC_AT_OVERLAY")
    if(DEFINED ENV{UNC_OVL_LAZY})
        set(OVL_LIFETIME "lazy")
    else()
        set(OVL_LIFETIME "eager")
    endif()
    # Printed because the two differ by a disk access per format and by
    # nothing a build output would otherwise show.
    message(STATUS "overlay: sixteen images, ${OVL_LIFETIME}")
    # The dispatch, the relocation trailer and the cache flush are shared; the
    # loader is the lifetime.
    set(OVERLAY_SHIM ovl_shim.c ovl_reloc.c)
    if(OVL_LIFETIME STREQUAL "eager")
        list(APPEND OVERLAY_SHIM ovl_load_eager.c)
        # The per-image .r files are still built — they are where the images
        # come from — but only the bundle is linked in.
        set(OVERLAY_R ${CMAKE_CURRENT_BINARY_DIR}/ovl_bundle.r)
    else()
        list(APPEND OVERLAY_SHIM ovl_load_lazy.c)
        foreach(img crypt spacesaver cptdd lzh arc now superdisk packit text
                    stuffit exo codecs binhex btoa sqp zipold)
            list(APPEND OVERLAY_R ${CMAKE_CURRENT_BINARY_DIR}/ovl_${img}.r)
        endforeach()
    endif()
    # The DECODERS leave the resident link; every probe stays in it.
    list(FILTER ENGINE_SRC EXCLUDE REGEX "unc_crypt\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_spacesaver\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_cpt\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_dd\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_lzh\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_arc\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_now\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_superdisk\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_packit\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_sqp\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_mime\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_uu\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_btoa\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_b64\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_binhex\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_sit\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_sit5\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_pf\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "sit_arsenic\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "sit14\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "sit_ccube\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "fmt_exo\\.c$")
    # zlib and the inflate wrapper go with them: fmt_exo is their only caller,
    # so nothing resident is left needing deflate.
    list(FILTER ENGINE_SRC EXCLUDE REGEX "unc_inflate\\.c$")
    set(ZLIB_SRC "")
    # And unc_lzdyn is not shared either — LZH is its only caller — so it
    # moves into that overlay rather than staying resident for one format.
    list(FILTER ENGINE_SRC EXCLUDE REGEX "unc_lzdyn\\.c$")
    # The shared machinery leaves too — see tools/overlay/ovl_codecs.c for how
    # a blob can be called by other blobs at all.
    list(FILTER ENGINE_SRC EXCLUDE REGEX "unc_huffman\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "unc_lzw\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "unc_reduce\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "unc_shrink\\.c$")
    list(FILTER ENGINE_SRC EXCLUDE REGEX "unc_lzah\\.c$")
endif()

# CREATOR is not decoration: the Finder binds an icon family to an
# application by matching the 'BNDL' owner to the application's creator
# code, and Retro68 defaults that to '????'. Without this the icons are in
# the file and the Finder never shows them. Keep 'MExt' in step with the
# CREATOR constant in tools/icon/make_icon.py, which stamps the 'BNDL'.
add_application(MacExtract
    CREATOR "MExt"
    macextract_mac.c
    ${ENGINE_SRC}
    ${ZLIB_SRC}
    macextract.r
    # Icon family + 'FREF'/'BNDL', generated. A SEPARATE file from
    # macextract.r, which holds the dialogs, the alerts and 'SIZE'.
    macextract_icons.r
    ${OVERLAY_SHIM}
    ${OVERLAY_R}
)

# The generated host vector lands in the build directory, and ovl_shim.c
# includes it.
target_include_directories(MacExtract PRIVATE ${CMAKE_CURRENT_BINARY_DIR})

# What EVERY image is built from, in one list because it was in fifteen.
#
# Each rule below named its own sources and then repeated the shared ones, and
# the repetition had drifted two ways. overlay.h and overlay.ld were listed by
# 7 of the 15 rules, so `touch tools/overlay/overlay.h` regenerated 7 images
# and left 8 (measured 2026-09-25); and NO rule listed a single one of the 26
# headers its own sources include, counted with `gcc -MM`, so a field added to
# include/macextract.h or a change to src/unc_internal.h rebuilt the resident
# application and left every image as it was.
#
# Neither is a link error. overlay.h is where the OVL_* entry-point ids live
# and macextract.h is where UncEntryInfo lives, and an image compiles against
# both — a decoder overlay compiles the decoder. Stale bytes here are a host
# and an image disagreeing about a number or a struct layout, on a Macintosh.
#
# Headers come in by glob rather than by name, because the names are what
# drifted; CONFIGURE_DEPENDS re-globs at build time, so a header added
# tomorrow is covered without anybody remembering this line. The cost is that
# touching any header rebuilds every image — 9.4 s for the whole build,
# measured — and a no-op rebuild still regenerates nothing.
file(GLOB OVL_HDRS CONFIGURE_DEPENDS
     ${ENGINE_DIR}/src/*.h
     ${ENGINE_DIR}/include/*.h
     ${ENGINE_DIR}/third_party/zlib/*.h
     ${ENGINE_DIR}/tools/overlay/*.h)

set(OVL_DEPS ${ENGINE_DIR}/tools/overlay/overlay.ld
             ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
             ${ENGINE_DIR}/tools/overlay/mkreloctrailer.py
             ${ENGINE_DIR}/tools/overlay/ovlid.py
             ${ENGINE_DIR}/tools/overlay/ovl_rt.c
             ${OVL_HDRS})

# The host vector and its forwards are GENERATED from the engine's own
# prototypes: forty-odd functions written by hand is how a wrong argument list
# crosses the boundary silently (tools/overlay/mkforwards.py).
add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_gen.h
           ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_init_gen.h
           ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
           ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_codecs_gen.c
           ${CMAKE_CURRENT_BINARY_DIR}/ovl_codec_exports_gen.h
           ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_zipold_gen.c
           ${CMAKE_CURRENT_BINARY_DIR}/ovl_zipold_exports_gen.h
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}
    COMMAND python3 ${ENGINE_DIR}/tools/overlay/mkforwards.py
            ${CMAKE_CURRENT_BINARY_DIR}
    DEPENDS ${ENGINE_DIR}/tools/overlay/mkforwards.py
            ${ENGINE_DIR}/src/unc_internal.h
            ${ENGINE_DIR}/include/macextract.h)

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_crypt.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_CRYPT
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_crypt.r
            ${ENGINE_DIR}/tools/overlay/ovl_crypt.c
            ${ENGINE_DIR}/src/unc_crypt.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_crypt.c
            ${ENGINE_DIR}/src/unc_crypt.c
            ${OVL_DEPS})

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_spacesaver.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_SPACESAVER
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_spacesaver.r
            ${ENGINE_DIR}/tools/overlay/ovl_spacesaver.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_spacesaver.c
            ${ENGINE_DIR}/src/fmt_spacesaver_probe.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_spacesaver.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_codecs_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_gen.h
            ${ENGINE_DIR}/src/fmt_spacesaver.c
            ${ENGINE_DIR}/src/fmt_spacesaver_probe.c
            ${OVL_DEPS})

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_cptdd.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_CPTDD
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_cptdd.r
            ${ENGINE_DIR}/tools/overlay/ovl_cptdd.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_cpt.c
            ${ENGINE_DIR}/src/fmt_dd.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_cptdd.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_codecs_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_gen.h
            ${ENGINE_DIR}/src/fmt_cpt.c
            ${ENGINE_DIR}/src/fmt_dd.c
            ${OVL_DEPS})

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_lzh.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_LZH
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_lzh.r
            ${ENGINE_DIR}/tools/overlay/ovl_lzh.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_lzh.c
            ${ENGINE_DIR}/src/unc_lzdyn.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_lzh.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_codecs_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_gen.h
            ${ENGINE_DIR}/src/fmt_lzh.c
            ${ENGINE_DIR}/src/unc_lzdyn.c
            ${OVL_DEPS})

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_arc.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_ARC
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_arc.r
            ${ENGINE_DIR}/tools/overlay/ovl_arc.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_arc.c
            ${ENGINE_DIR}/src/fmt_arc_probe.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_arc.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_codecs_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_gen.h
            ${ENGINE_DIR}/src/fmt_arc.c
            ${ENGINE_DIR}/src/fmt_arc_probe.c
            ${OVL_DEPS})

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_now.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_NOW
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_now.r
            ${ENGINE_DIR}/tools/overlay/ovl_now.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_now.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_now.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_codecs_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_gen.h
            ${ENGINE_DIR}/src/fmt_now.c
            ${OVL_DEPS})

target_include_directories(MacExtract PRIVATE
    ${ENGINE_DIR}/tools/overlay
    ${ENGINE_DIR}/include
    ${ENGINE_DIR}/src
    ${ENGINE_DIR}/third_party/zlib
)

# Everything builds at -Os, sit_arsenic.c included, and that was TESTED
# rather than assumed: building that one file at -O2 costs 1,536 B and
# measured 1,304 s against -Os's 1,284 s on the fixture where it should
# show up most (FORMATS.md, `Per-file -O2`). Do not re-try it without a
# harness that resolves better than 20 s on a 22-minute run.

# zlib is used for ONE thing here, raw inflate, and two defines say so.
# Z_TESTW=0 drops crc32.c's braided tables (W defaults to 4 on anything
# that is not x86-64 or aarch64, so the 68000 build carried them); the
# engine's CRC is unc_crc32. NO_GZIP drops inflate.c's gzip-wrapper state
# machine, which fmt_exo.c makes unreachable by reading the gzip header
# and trailer itself. Neither modifies third_party/zlib. Together they are
# 8,704 B of the application — FORMATS.md, `Resident memory`.
set_source_files_properties(
    ${ZLIB_SRC} TARGET_DIRECTORY MacExtract
    PROPERTIES COMPILE_DEFINITIONS "Z_TESTW=0;NO_GZIP")

# The functions an extraction spends its time in carry UNC_HOT
# (src/unc_internal.h), which builds THEM at -O3 and leaves the rest of
# each file at -Os. What that is worth, on a 7 MHz Mac Plus over
# derived-EmpireBuilderDemo.sit (FORMATS.md, *What -O3 is worth, and
# where*):
#
#   -Os everywhere            70.4 s   182,144 B
#   -O2 unc_lzw + unc_huffman 58.8 s   +1,536 B   -16.5 %
#   -O2 four whole files      56.2 s   +5,504 B   -20.2 %
#   -O2 the whole engine      56.0 s  +40,192 B   -20.6 %
#   -O3 four whole files      52.5 s   +8,320 B   -25.4 %
#
# sit_arsenic.c has no UNC_HOT in it: -O2 was measured SLOWER there, and
# that measurement was taken on that file rather than inherited.

# Plain 68000 floor: no 68020+ instructions.
# Size flags. CODE is the only part of this application that costs the engine
# budget (FORMATS.md, *What the application costs the engine*), so bytes here
# are bytes the engine gets on a 1 MB Mac Plus — but they are NOT free, and
# each was priced in BOTH currencies on 2026-08-30. Bytes from
# `m68k-apple-macos-size`; ticks are gTkRun from `-D UNC_AT_TIMING` on
# derived-EmpireBuilderDemo.sit at authentic 7 MHz, which is DETERMINISTIC
# here — three runs per build gave identical counts — so one run prices a
# configuration. Baseline 148,048 B / 3,158 ticks (52.63 s):
#
#   -fno-tree-loop-distribute-patterns   -440 B    +1 tick   kept
#   -freorder-blocks-algorithm=simple    -336 B   +26 ticks  kept, and it is
#                                                            the whole cost
#   -fipa-icf                               0 B    0 ticks   kept: worth ~12 B
#                                                            only in combination
#   -fno-early-inlining                    +8 B    +2 ticks  REJECTED — worse
#                                                            on both axes
#
# Together: 147,268 B / 3,184 ticks — 780 B for +0.82 % of an extraction. That
# 780 B is what puts the budget at 566,164 B and brings the corpus's heaviest
# three archives (566,009 B) back inside a 1 MB Mac Plus, by 155 bytes. It is a
# real trade and it was made deliberately: an archive that will not open is a
# worse outcome than one that opens 0.4 s later on a 52.6 s job.
#
# Measured and rejected on size alone: -fno-inline-functions-called-once
# (+2,444 B), -fconserve-stack (+1,064 B), -flto (does not link on this
# toolchain), -Wl,--relax (no effect on this target), alignment flags,
# -fno-asynchronous-unwind-tables, -fmerge-all-constants, -fno-ident (no
# effect).
#
# -fno-inline-small-functions IS TIMED NOW, 2026-08-31, and it is the worst
# trade in this file: -248 B for **+448 ticks, +14.1 %** — 53.1 s to 60.5 s on
# the same fixture and instrument as the rows above, against the four kept
# flags' 780 B for +0.82 % between them. Rejected on measurement rather than
# on the absence of one, which is what BLOCKERS.md had recorded against it.
#
# Inlining is already at its size optimum here and pushing it either way
# costs: -finline-limit=30 is +8 B, =60 is -28 B, --param
# max-inline-insns-single=50 is -16 B, and none of them stack with anything —
# every combination lands on the same byte. Functions called once are inlined
# and that is what makes dd_fork 5,136 B and ExtractOne 5,884 B; separating
# them is the +2,444 B row above.
target_compile_options(MacExtract PRIVATE -mcpu=68000 -Os -Wno-multichar
                       -fno-tree-loop-distribute-patterns
                       -freorder-blocks-algorithm=simple
                       -fipa-icf
                       -ffunction-sections
                       # UNC_MAC_AUTOTEST builds a headless self-driving variant
                       # (no SFGetFile/alerts) used by the Mini vMac harness in
                       # tools/; see tools/vmac/README.md. Normal builds omit it.
                       $<$<BOOL:$ENV{UNC_MAC_AUTOTEST}>:-DUNC_MAC_AUTOTEST>
                       # UNC_OFF64: carry a container offset in 64 bits on the
                       # 68000 itself. Not a switch any release uses — the Mac
                       # cannot hold a file past 2 GB — but the only way to
                       # find out what the wider type does on a real 68000,
                       # where it means libgcc helper calls (DECISIONS.md
                       # 2026-08-28, *what a width costs*).
                       $<$<BOOL:$ENV{UNC_OFF64}>:-DUNC_OFF64>
                       # UNC_AT_META: autotest reports the first file's on-Mac
                       # type/creator/Finder-flags instead of the CRC aggregate
                       # (the "launches by double-click" E2E check).
                       # UNC_AT_RESERVE: track the low-water mark of FreeMem()
                       # across a run and print it in the completion alert, to
                       # price kMemReserveMax against what the shell actually
                       # uses. A probe, never shipped.
                       $<$<BOOL:$ENV{UNC_AT_RESERVE}>:-DUNC_AT_RESERVE>
                       # UNC_AT_STACK: paint the unused stack at launch and
                       # read the watermark back at the end — what kStackBump
                       # is actually worth, in a currency the engine spends.
                       # FORMATS.md, *Stack*.
                       $<$<BOOL:$ENV{UNC_AT_STACK}>:-DUNC_AT_STACK>
                       # UNC_AT_CONTIG: MaxBlock() at the moment each dialog
                       # is created — the reserve's real job is one contiguous
                       # block, and every other reserve figure measures volume.
                       # FORMATS.md, *What the reserve is NOT proven against*.
                       $<$<BOOL:$ENV{UNC_AT_CONTIG}>:-DUNC_AT_CONTIG>
                       # UNC_STACK_BUMP_KB: kStackBump in KB, so the stack
                       # size can be SWEPT without editing source. A
                       # requirement does not move when the stack does; a
                       # measurement that tracks the stack size is measuring
                       # the stack size. FORMATS.md, *Stack*.
                       $<$<BOOL:$ENV{UNC_STACK_BUMP_KB}>:-DUNC_STACK_BUMP_KB=$ENV{UNC_STACK_BUMP_KB}>
                       # UNC_AT_OVERLAY, the C macro, means "this build has
                       # images" and is now set by the CONFIGURATION rather
                       # than by an environment switch: the shell's preload
                       # and release call sites are guarded with it, and they
                       # are in every build but the resident control one.
                       ${OVL_COMPILE_DEFS}
                       $<$<BOOL:$ENV{UNC_AT_META}>:-DUNC_AT_META>
                       # UNC_AT_SEPARATE_BLOCKS: force the two-separate-NewPtr
                       # staging path (re-tests the old "3 blocks bomb" claim).
                       $<$<BOOL:$ENV{UNC_AT_SEPARATE_BLOCKS}>:-DUNC_AT_SEPARATE_BLOCKS>
                       # UNC_AT_NOCRC: skip the on-Mac fork read-back (isolate a
                       # write-path crash from a read-back crash).
                       $<$<BOOL:$ENV{UNC_AT_NOCRC}>:-DUNC_AT_NOCRC>
                       # UNC_AT_CANCEL: autotest aborts the extraction part-way
                       # and reports what the volume actually holds, proving an
                       # aborted entry leaves no partial file behind.
                       $<$<BOOL:$ENV{UNC_AT_CANCEL}>:-DUNC_AT_CANCEL>
                       # UNC_AT_PROGRESS: paint the engine's progress into the
                       # result grid as it runs, so a run that never finishes
                       # can still be interrogated by screenshot.
                       $<$<BOOL:$ENV{UNC_AT_PROGRESS}>:-DUNC_AT_PROGRESS>
                       # UNC_AT_WD: extract through a WORKING DIRECTORY made
                       # with PBOpenWD (vRefNum = WD, dirID = 0), which is the
                       # shape SFGetFile hands the interactive app on System 7
                       # and later, and report where the files actually landed.
                       $<$<BOOL:$ENV{UNC_AT_WD}>:-DUNC_AT_WD>
                       # UNC_AT_INTERLEAVE: read a file twice on one volume,
                       # the second time while creating files on that same
                       # volume between chunks, and compare the two CRCs. Tests
                       # the claim the whole-archive RAM slurp exists to avoid.
                       $<$<BOOL:$ENV{UNC_AT_INTERLEAVE}>:-DUNC_AT_INTERLEAVE>
                       # UNC_AT_SAMEVOL: extract onto the volume the archive
                       # is on, as the interactive app does, instead of onto a
                       # separate "Out" volume. The read-back CRC check is
                       # unchanged, so this proves the same-volume case
                       # byte-exact rather than assuming it.
                       $<$<BOOL:$ENV{UNC_AT_SAMEVOL}>:-DUNC_AT_SAMEVOL>
                       # UNC_AT_NOHIDECURSOR: draw the result grid WITHOUT
                       # hiding the cursor first, to test the claim that the
                       # cursor's saved background stamps over the grid.
                       $<$<BOOL:$ENV{UNC_AT_NOHIDECURSOR}>:-DUNC_AT_NOHIDECURSOR>
                       # UNC_AT_BUDGET: report FreeMem() and the engine's
                       # allowed budget in the grid's two length slots. The
                       # grid otherwise carries what the engine USED and never
                       # what it was ALLOWED, so a budget refusal and a real
                       # shortage are indistinguishable on screen.
                       $<$<BOOL:$ENV{UNC_AT_BUDGET}>:-DUNC_AT_BUDGET>
                       # UNC_AT_HANDLES: allocate engine memory as relocatable
                       # handles moved high and locked, instead of NewPtr, and
                       # report MaxBlock either side of MoveHHi. Tests whether
                       # MoveHHi does anything under System 6 at all.
                       $<$<BOOL:$ENV{UNC_AT_HANDLES}>:-DUNC_AT_HANDLES>
                       # UNC_AT_TIMING: split the extraction into File
                       # Manager reads, File Manager writes, the rest of the
                       # File Manager and what is left over — the engine — and
                       # put the four tick counts in the grid. A Linux profile
                       # sees only the last of the four.
                       $<$<BOOL:$ENV{UNC_AT_TIMING}>:-DUNC_AT_TIMING>
                       # UNC_MAC_STAGE_WRITES: go back to accumulating each
                       # whole fork in RAM and writing it in sink_end. The
                       # default streams straight to the File Manager; this
                       # keeps the older path buildable for comparison.
                       $<$<BOOL:$ENV{UNC_MAC_STAGE_WRITES}>:-DUNC_MAC_STAGE_WRITES>
                       # UNC_MAC_SLURP_ARCHIVE: go back to reading the whole
                       # archive into one NewPtr block before extracting. The
                       # default reads it off the file as the engine asks,
                       # which on the floor target hands the engine back the
                       # archive's size in budget; this keeps the older path
                       # buildable for comparison.
                       $<$<BOOL:$ENV{UNC_MAC_SLURP_ARCHIVE}>:-DUNC_MAC_SLURP_ARCHIVE>)
target_link_options(MacExtract PRIVATE -Wl,-gc-sections)

# The Finder ignores a 'BNDL' unless the file's hasBundle flag is set, and
# nothing in the Retro68 chain sets it — Rez takes -t and -c and has no
# option for the Finder flags. Hooked to the APPL target rather than to
# tools/build_mac.sh because run.py and interactive.py drive CMake
# directly, and the icon has to be right in the builds that photograph it.
add_custom_command(TARGET MacExtract_APPL POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "-- setting hasBundle"
    COMMAND python3 ${ENGINE_DIR}/tools/icon/set_bundle_bit.py
            $<TARGET_FILE_DIR:MacExtract>/MacExtract.bin
            $<TARGET_FILE_DIR:MacExtract>/MacExtract.dsk MacExtract
    VERBATIM)

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_superdisk.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_SUPERDISK
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_superdisk.r
            ${ENGINE_DIR}/tools/overlay/ovl_superdisk.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_superdisk.c
            ${ENGINE_DIR}/src/fmt_superdisk_probe.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_superdisk.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_codecs_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_gen.h
            ${ENGINE_DIR}/src/fmt_superdisk.c
            ${ENGINE_DIR}/src/fmt_superdisk_probe.c
            ${OVL_DEPS})

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_packit.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_PACKIT
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_packit.r
            ${ENGINE_DIR}/tools/overlay/ovl_packit.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_packit.c
            ${ENGINE_DIR}/src/fmt_packit_probe.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_packit.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_codecs_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_gen.h
            ${ENGINE_DIR}/src/fmt_packit.c
            ${ENGINE_DIR}/src/fmt_packit_probe.c
            ${OVL_DEPS})

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_text.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_TEXT
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_text.r
            ${ENGINE_DIR}/tools/overlay/ovl_text.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_mime.c
            ${ENGINE_DIR}/src/fmt_mime_probe.c
            ${ENGINE_DIR}/src/fmt_uu.c
            ${ENGINE_DIR}/src/fmt_uu_probe.c
            ${ENGINE_DIR}/src/fmt_b64.c
            ${ENGINE_DIR}/src/fmt_b64_probe.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_text.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_codecs_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_gen.h
            ${ENGINE_DIR}/src/fmt_mime.c
            ${ENGINE_DIR}/src/fmt_mime_probe.c
            ${ENGINE_DIR}/src/fmt_uu.c
            ${ENGINE_DIR}/src/fmt_uu_probe.c
            ${ENGINE_DIR}/src/fmt_b64.c
            ${ENGINE_DIR}/src/fmt_b64_probe.c
            ${OVL_DEPS})

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_stuffit.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_STUFFIT
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_stuffit.r
            ${ENGINE_DIR}/tools/overlay/ovl_stuffit.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_sit.c
            ${ENGINE_DIR}/src/fmt_sit_probe.c
            ${ENGINE_DIR}/src/fmt_sit5.c
            ${ENGINE_DIR}/src/fmt_sit5_probe.c
            ${ENGINE_DIR}/src/sit14.c
            ${ENGINE_DIR}/src/sit_arsenic.c
            ${ENGINE_DIR}/src/sit_ccube.c
            ${ENGINE_DIR}/src/fmt_pf.c
            ${ENGINE_DIR}/src/fmt_pf_probe.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_stuffit.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_codecs_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_gen.h
            ${ENGINE_DIR}/src/fmt_sit.c
            ${ENGINE_DIR}/src/fmt_sit_probe.c
            ${ENGINE_DIR}/src/fmt_sit5.c
            ${ENGINE_DIR}/src/fmt_sit5_probe.c
            ${ENGINE_DIR}/src/sit14.c
            ${ENGINE_DIR}/src/sit_arsenic.c
            ${ENGINE_DIR}/src/sit_ccube.c
            ${ENGINE_DIR}/src/fmt_pf.c
            ${ENGINE_DIR}/src/fmt_pf_probe.c
            ${OVL_DEPS})

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_exo.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_EXO
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_exo.r
            ${ENGINE_DIR}/tools/overlay/ovl_exo.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_exo.c
            ${ENGINE_DIR}/src/fmt_exo_probe.c
            ${ENGINE_DIR}/src/unc_inflate.c
            ${ENGINE_DIR}/third_party/zlib/inflate.c
            ${ENGINE_DIR}/third_party/zlib/inftrees.c
            ${ENGINE_DIR}/third_party/zlib/inffast.c
            ${ENGINE_DIR}/third_party/zlib/adler32.c
            ${ENGINE_DIR}/third_party/zlib/crc32.c
            ${ENGINE_DIR}/third_party/zlib/zutil.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_exo.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_exo.c
            ${ENGINE_DIR}/src/fmt_exo_probe.c
            ${ENGINE_DIR}/src/unc_inflate.c
            ${OVL_DEPS})

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_codecs.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_CODECS
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_codecs.r
            ${ENGINE_DIR}/tools/overlay/ovl_codecs.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_codecs_gen.c
            ${ENGINE_DIR}/src/unc_huffman.c
            ${ENGINE_DIR}/src/unc_lzw.c
            ${ENGINE_DIR}/src/unc_lzah.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_codecs.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_codecs_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_codec_exports_gen.h
            ${ENGINE_DIR}/src/unc_huffman.c
            ${ENGINE_DIR}/src/unc_lzw.c
            ${ENGINE_DIR}/src/unc_lzah.c
            ${OVL_DEPS})

# Zip's Shrink and Reduce, kept for zip alone (tools/overlay/ovl_zipold.c).
add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_zipold.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_ZIPOLD
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_zipold.r
            ${ENGINE_DIR}/tools/overlay/ovl_zipold.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_zipold_gen.c
            ${ENGINE_DIR}/src/unc_shrink.c
            ${ENGINE_DIR}/src/unc_reduce.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_zipold.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_zipold_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_zipold_exports_gen.h
            ${ENGINE_DIR}/src/unc_shrink.c
            ${ENGINE_DIR}/src/unc_reduce.c
            ${OVL_DEPS})

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_binhex.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_BINHEX
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_binhex.r
            ${ENGINE_DIR}/tools/overlay/ovl_binhex.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_binhex.c
            ${ENGINE_DIR}/src/fmt_binhex_probe.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_binhex.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_gen.h
            ${ENGINE_DIR}/src/fmt_binhex.c
            ${ENGINE_DIR}/src/fmt_binhex_probe.c
            ${OVL_DEPS})

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_btoa.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_BTOA
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_btoa.r
            ${ENGINE_DIR}/tools/overlay/ovl_btoa.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_btoa.c
            ${ENGINE_DIR}/src/fmt_btoa_probe.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_btoa.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_gen.h
            ${ENGINE_DIR}/src/fmt_btoa.c
            ${ENGINE_DIR}/src/fmt_btoa_probe.c
            ${OVL_DEPS})

# AppleLink packages. The PROBE is not in the image — it is resident, like
# every other probe — so this is the walk and the two fork readers alone,
# and the LZW they call is the codecs image's.
add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_sqp.r
    COMMAND ${CMAKE_COMMAND} -E env OVL_ID=OVL_ID_SQP
            OVL_INC=${CMAKE_CURRENT_BINARY_DIR}
            sh ${ENGINE_DIR}/tools/overlay/mkoverlay.sh
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_sqp.r
            ${ENGINE_DIR}/tools/overlay/ovl_sqp.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${ENGINE_DIR}/src/fmt_sqp.c
    DEPENDS ${ENGINE_DIR}/tools/overlay/ovl_sqp.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_forwards_gen.c
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_host_gen.h
            ${ENGINE_DIR}/src/fmt_sqp.c
            ${OVL_DEPS})
# The bundle. Depends on the per-format .r rules only so that their .bin
# side-products exist; mkoverlay.sh writes <out>.bin beside <out>.r.
#
# `--bin` writes the bundle's RAW bytes beside the Rez source, for
# tests/run_overlay_host.sh --shipped: it hands THESE bytes to the real loader
# off the Macintosh and checks every relocation at the address the image ends
# up at. The Rez source is what the application links; the raw copy is read by
# nothing else.
add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ovl_bundle.r
    COMMAND python3 ${ENGINE_DIR}/tools/overlay/mkbundle.py
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_bundle.r
            --bin ${CMAKE_CURRENT_BINARY_DIR}/ovl_bundle.bin
            OVL_ID_CRYPT:${CMAKE_CURRENT_BINARY_DIR}/ovl_crypt.bin
            OVL_ID_SPACESAVER:${CMAKE_CURRENT_BINARY_DIR}/ovl_spacesaver.bin
            OVL_ID_CPTDD:${CMAKE_CURRENT_BINARY_DIR}/ovl_cptdd.bin
            OVL_ID_LZH:${CMAKE_CURRENT_BINARY_DIR}/ovl_lzh.bin
            OVL_ID_ARC:${CMAKE_CURRENT_BINARY_DIR}/ovl_arc.bin
            OVL_ID_NOW:${CMAKE_CURRENT_BINARY_DIR}/ovl_now.bin
            OVL_ID_SUPERDISK:${CMAKE_CURRENT_BINARY_DIR}/ovl_superdisk.bin
            OVL_ID_PACKIT:${CMAKE_CURRENT_BINARY_DIR}/ovl_packit.bin
            OVL_ID_TEXT:${CMAKE_CURRENT_BINARY_DIR}/ovl_text.bin
            OVL_ID_STUFFIT:${CMAKE_CURRENT_BINARY_DIR}/ovl_stuffit.bin
            OVL_ID_EXO:${CMAKE_CURRENT_BINARY_DIR}/ovl_exo.bin
            OVL_ID_CODECS:${CMAKE_CURRENT_BINARY_DIR}/ovl_codecs.bin
            OVL_ID_BINHEX:${CMAKE_CURRENT_BINARY_DIR}/ovl_binhex.bin
            OVL_ID_BTOA:${CMAKE_CURRENT_BINARY_DIR}/ovl_btoa.bin
            OVL_ID_SQP:${CMAKE_CURRENT_BINARY_DIR}/ovl_sqp.bin
            OVL_ID_ZIPOLD:${CMAKE_CURRENT_BINARY_DIR}/ovl_zipold.bin
    DEPENDS
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_crypt.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_spacesaver.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_cptdd.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_lzh.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_arc.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_now.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_superdisk.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_packit.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_text.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_stuffit.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_exo.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_codecs.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_binhex.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_btoa.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_sqp.r
            ${CMAKE_CURRENT_BINARY_DIR}/ovl_zipold.r
            ${ENGINE_DIR}/tools/overlay/mkbundle.py
            ${ENGINE_DIR}/tools/overlay/ovlid.py
            ${ENGINE_DIR}/tools/overlay/overlay.h)
