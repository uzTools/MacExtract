# Standalone reproduction for the Retro68 HOpen/HOpenDF/HOpenRF glue bug.
#
#   cmake -B build -S . \
#     -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
#   cmake --build build
#
# Produces hopen_repro.APPL / .bin / .dsk. Mount the .dsk in Mini vMac beside a
# System 6.0.8 boot disk (Mac Plus, 68000) and double-click the application.
cmake_minimum_required(VERSION 3.10)
project(hopen_repro C)

add_application(hopen_repro hopen_repro.c)

# Plain 68000, matching the floor target where the bug was found.
target_compile_options(hopen_repro PRIVATE -mcpu=68000 -Os)

# The ioMisc reproduction (ISSUE.md): the one to send upstream.
add_application(IOMisc iomisc_repro.c)
target_compile_options(IOMisc PRIVATE -mcpu=68000 -Os)

# The rest of the File Manager glue (README.md, glue_audit).
add_application(GlueAudit glue_audit.c)
target_compile_options(GlueAudit PRIVATE -mcpu=68000 -Os)
add_application(GlueAuditFixed glue_audit.c)
target_compile_options(GlueAuditFixed PRIVATE -mcpu=68000 -Os -DGLUE_FIXED)

# The issue's repro (ISSUE-glue-audit.md). It calls the real glue, so build it
# against the Retro68 being reported on: -DGLUE_LIB_DIR=<dir holding a
# libInterface.a> links that one instead of the toolchain's (README.md).
add_application(GlueRepro glue_repro.c)
target_compile_options(GlueRepro PRIVATE -mcpu=68000 -Os)
if(GLUE_LIB_DIR)
  target_link_options(GlueRepro PRIVATE -L${GLUE_LIB_DIR})
endif()
