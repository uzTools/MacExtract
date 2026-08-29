# Build the Macintosh MIME encoder used by tools/vmac/macmime.py:
#
#   cmake -B build/macmime -S tools/macmime \
#     -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
#   cmake --build build/macmime
#
# The harness does this itself. Nothing in ci.sh builds it: it exists to
# produce ONE specimen, and the specimen is what is graded afterwards.
#
# Everything that decides a byte of the message is compiled straight out
# of the read-only reference tree. reference/ is neither modified nor
# copied: the shim header that stands in for the application's own
# macmpack.h is found first because this directory comes first on the
# include path.
#
# gnu89 with warnings off, for the same reason tools/build_mpack.sh pins
# them: this is 1994 K&R C and it declares malloc() returning char *.
cmake_minimum_required(VERSION 3.10)
project(macmime C)

set(MPACK ${CMAKE_CURRENT_SOURCE_DIR}/../../reference/mpack)

# macfile.c says `#include "macmpack.h"`, and a quoted include is resolved
# from the including file's OWN directory before any -I, so compiling it
# where it lies would always find the application's header rather than the
# shim. It is COPIED — byte for byte, never edited — next to the shim
# instead. Same trick, same reason, as tools/build_mpack.sh copying the
# tree to build/ before building it. reference/ is not written to.
configure_file(${MPACK}/macfile.c ${CMAKE_CURRENT_BINARY_DIR}/mpack/macfile.c COPYONLY)
configure_file(${CMAKE_CURRENT_SOURCE_DIR}/macmpack.h ${CMAKE_CURRENT_BINARY_DIR}/mpack/macmpack.h COPYONLY)

add_application(macmime
    CREATOR "mMIM"
    macmime.c
    ${CMAKE_CURRENT_BINARY_DIR}/mpack/macfile.c
    ${MPACK}/encode.c
    ${MPACK}/codes.c
    ${MPACK}/magic.c
    ${MPACK}/md5c.c
    ${MPACK}/xmalloc.c
)

target_include_directories(macmime PRIVATE ${CMAKE_CURRENT_SOURCE_DIR} ${MPACK})
target_compile_options(macmime PRIVATE -mcpu=68000 -Os -std=gnu89 -w)
