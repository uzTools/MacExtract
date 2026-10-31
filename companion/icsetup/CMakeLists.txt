# The Internet Config setup helper (icsetup.c says what it changes):
#
#   cmake -B build/icsetup -S companion/icsetup \
#     -DCMAKE_TOOLCHAIN_FILE=/opt/Retro68-build/toolchain-universal/m68k-apple-macos/cmake/retro68.toolchain.cmake \
#     -DRETRO68_ROOT=/opt/Retro68-build/toolchain-universal
#   cmake --build build/icsetup
#
# The universal toolchain, because Apple's InternetConfig.h and its 68k
# glue (libICGlueFar.a: the near libICGlue.a cannot reach Gestalt) come with the Universal Interfaces.
cmake_minimum_required(VERSION 3.10)
project(icsetup C)

add_application(icsetup
    CREATOR "MExH"
    icsetup.c
    icsetup.r
)
target_link_libraries(icsetup ICGlueFar)
target_compile_options(icsetup PRIVATE -mcpu=68000 -Os -Wall -Wno-multichar
    -ffunction-sections)
# The universal libInterface.a is one object; without -gc-sections all of
# it is linked: 59,392 B as MacBinary, 10,624 B with these two flags.
target_link_options(icsetup PRIVATE -Wl,-gc-sections -Wl,--mac-strip-macsbug)
