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
)

target_include_directories(MacExtract PRIVATE
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
                       $<$<BOOL:$ENV{UNC_MAC_SLURP_ARCHIVE}>:-DUNC_MAC_SLURP_ARCHIVE>
                       # UNC_AT_LISTWALK: do selective extraction's LISTING
                       # walk before the extracting one, and then extract
                       # everything. The autotest has no box to choose in, so
                       # what this measures is the walk itself: the same
                       # fixture with the flag and without it is what the
                       # second pass costs on a 68000, which no Linux timing
                       # can stand in for.
                       $<$<BOOL:$ENV{UNC_AT_LISTWALK}>:-DUNC_AT_LISTWALK>)
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
