# Build the Macintosh shell with Retro68:
#
#   cmake -B build-mac -S mac \
#     -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
#   cmake --build build-mac
#
# Produces unclassic.APPL/.bin/.dsk (mountable in Mini vMac; copy the
# application onto a System 6..9 boot disk to run). See tools/vmac/README.md.
cmake_minimum_required(VERSION 3.10)
project(unclassic_mac C)

set(ENGINE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/..)
file(GLOB ENGINE_SRC ${ENGINE_DIR}/src/*.c)
file(GLOB ZLIB_SRC ${ENGINE_DIR}/third_party/zlib/*.c)

add_application(unclassic
    unclassic_mac.c
    ${ENGINE_SRC}
    ${ZLIB_SRC}
    unclassic.r
)

target_include_directories(unclassic PRIVATE
    ${ENGINE_DIR}/include
    ${ENGINE_DIR}/src
    ${ENGINE_DIR}/third_party/zlib
)

# zlib's crc32.c compiles a set of "braided" tables whenever W is defined,
# and W defaults to 4 on anything that is not x86-64 or aarch64 — so the
# 68000 build carried them. Z_TESTW=0 leaves W undefined. The engine uses
# raw inflate (inflateInit2(&zs, -15)), so zlib never computes a CRC;
# unc_crc32 does. FORMATS.md, `Resident memory`, has the bytes.
set_source_files_properties(
    ${ZLIB_SRC} TARGET_DIRECTORY unclassic
    PROPERTIES COMPILE_DEFINITIONS Z_TESTW=0)

# Plain 68000 floor: no 68020+ instructions.
target_compile_options(unclassic PRIVATE -mcpu=68000 -Os -Wno-multichar
                       -ffunction-sections
                       # UNC_MAC_AUTOTEST builds a headless self-driving variant
                       # (no SFGetFile/alerts) used by the Mini vMac harness in
                       # tools/; see tools/vmac/README.md. Normal builds omit it.
                       $<$<BOOL:$ENV{UNC_MAC_AUTOTEST}>:-DUNC_MAC_AUTOTEST>
                       # UNC_AT_META: autotest reports the first file's on-Mac
                       # type/creator/Finder-flags instead of the CRC aggregate
                       # (the "launches by double-click" E2E check).
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
target_link_options(unclassic PRIVATE -Wl,-gc-sections)
