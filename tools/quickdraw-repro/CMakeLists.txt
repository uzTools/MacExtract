# Standalone reproduction for "QuickDraw bombs after File Manager activity".
#
#   cmake -B build -S . \
#     -DCMAKE_TOOLCHAIN_FILE=$RETRO68/m68k-apple-macos/cmake/retro68.toolchain.cmake
#   cmake --build build
#
# Produces qd_repro.APPL / .bin / .dsk. tools/quickdraw-repro/run.py builds
# every variant and drives them under Mini vMac; see README.md.
cmake_minimum_required(VERSION 3.10)
project(qd_repro C)

add_application(qd_repro qd_repro.c qd_repro.r)

# Plain 68000, matching the floor target the claim was made on.
#
# The two switches are read from the ENVIRONMENT rather than passed with -D so
# that run.py can configure a variant the same way tools/vmac/run.py configures
# the application's own build switches. A variant therefore needs its own build
# directory: CMake resolves these at configure time, and reusing a directory
# would silently keep the first variant for ever.
target_compile_options(qd_repro PRIVATE -mcpu=68000 -Os
                       $<$<BOOL:$ENV{QR_NO_MAXAPPLZONE}>:-DQR_NO_MAXAPPLZONE>
                       $<$<BOOL:$ENV{QR_NO_MOREMASTERS}>:-DQR_NO_MOREMASTERS>)
