# Build the Macintosh shell with Retro68:
#
#   cmake -B build-mac -S mac \
#     -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
#   cmake --build build-mac
#
# Produces unclassic.APPL/.bin/.dsk (mountable in Mini vMac; copy the
# application onto a System 6..9 boot disk to run). See MANUAL_TESTS.md.
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

# Plain 68000 floor: no 68020+ instructions.
target_compile_options(unclassic PRIVATE -mcpu=68000 -Os -Wno-multichar
                       -ffunction-sections
                       # UNC_MAC_AUTOTEST builds a headless self-driving variant
                       # (no SFGetFile/alerts) used by the Mini vMac harness in
                       # tools/; see MANUAL_TESTS.md. Normal builds omit it.
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
                       # UNC_MAC_STAGE_WRITES: go back to accumulating each
                       # whole fork in RAM and writing it in sink_end. The
                       # default streams straight to the File Manager; this
                       # keeps the older path buildable for comparison.
                       $<$<BOOL:$ENV{UNC_MAC_STAGE_WRITES}>:-DUNC_MAC_STAGE_WRITES>)
target_link_options(unclassic PRIVATE -Wl,-gc-sections)
